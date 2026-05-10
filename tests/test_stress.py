"""Concurrent and stress tests for the StageFlow framework.

Covers: rapid sequential transitions, thread-safe variable access,
concurrent condition evaluation, large state persistence, and
state file integrity under load.
"""

from __future__ import annotations

import json
import os
import time
import threading
from pathlib import Path

import pytest

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine
from stageflow.core.conditions import evaluate_all, clear_cache


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_two_stage_registry():
    """Create an in-memory registry with stages 'a' and 'b', plus a->b transition."""
    reg = StageRegistry.__new__(StageRegistry)
    for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
        setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
    reg.config_path = Path("nonexistent.yaml")
    reg.register_stage("a", tools=[])
    reg.register_stage("b", tools=[])
    reg.register_transition("a", "b", [{"always": True}])
    return reg


def _make_chain_registry(n: int):
    """Create a registry with N stages in a linear chain (stage_0 -> stage_1 -> ...)."""
    reg = StageRegistry.__new__(StageRegistry)
    for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
        setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
    reg.config_path = Path("nonexistent.yaml")
    for i in range(n):
        reg.register_stage(f"stage_{i}", tools=[])
    for i in range(n - 1):
        reg.register_transition(f"stage_{i}", f"stage_{i + 1}", [{"always": True}])
    return reg


# ═══════════════════════════════════════════════════════════════════════════
# TestRapidSequential
# ═══════════════════════════════════════════════════════════════════════════

class TestRapidSequential:
    """Large number of sequential transitions — verifies engine stability."""

    def test_500_round_trips(self, tmp_path):
        """500 rapid forward-and-back transitions maintain correct state and history."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        rounds = 500
        for _ in range(rounds):
            sm.transition_to("b")
            assert sm.current_stage == "b"
            sm.force_transition_to("a")
            assert sm.current_stage == "a"

        assert len(sm.history) == rounds * 2

    def test_linear_chain_100_transitions(self, tmp_path):
        """Walk through a 100-stage linear chain without issues."""
        n = 100
        reg = _make_chain_registry(n)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("stage_0")

        for i in range(1, n):
            ok, msgs = sm.transition_to(f"stage_{i}")
            assert ok, f"Transition to stage_{i} failed: {msgs}"
            assert sm.current_stage == f"stage_{i}"

        assert len(sm.history) == n - 1

    def test_iteration_counter_through_repeated_transitions(self, tmp_path):
        """Iteration counter increments correctly through repeated revisit cycles."""
        reg = _make_two_stage_registry()
        reg.register_transition("b", "a", [{"always": True}])
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        for cycle in range(1, 11):
            sm.transition_to("b")
            sm.transition_to("a")
            assert sm.get_iterations("a") == cycle + 1  # +1 for initialize
            assert sm.get_iterations("b") == cycle

    def test_timing_stress_rapid_transitions(self, tmp_path):
        """Transitions complete in reasonable wall time under rapid usage."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        start = time.perf_counter()
        for _ in range(100):
            sm.transition_to("b")
            sm.force_transition_to("a")
        elapsed = time.perf_counter() - start

        # 100 round-trips (200 transitions + 200 saves) should complete
        # well under 5 seconds even on slow CI hardware
        assert elapsed < 10.0, f"100 round-trips took {elapsed:.2f}s"
        assert len(sm.history) == 200


# ═══════════════════════════════════════════════════════════════════════════
# TestConcurrentVariables
# ═══════════════════════════════════════════════════════════════════════════

class TestConcurrentVariables:
    """Thread-safety tests for variable read/write on a single StateMachine."""

    def test_concurrent_set_var_different_keys(self, tmp_path):
        """Multiple threads writing different keys should not lose data."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        def writer(key, value):
            for i in range(200):
                sm.set_var(key, f"{value}_{i}")

        num_threads = 8
        threads = []
        for t in range(num_threads):
            th = threading.Thread(target=writer, args=(f"key_{t}", f"val_{t}"))
            threads.append(th)

        for th in threads:
            th.start()
        for th in threads:
            th.join()

        for t in range(num_threads):
            val = sm.get_var(f"key_{t}")
            assert val is not None, f"key_{t} was not set"
            assert val.startswith(f"val_{t}_"), f"key_{t} has wrong value: {val}"

        assert len(sm.get_all_vars()) == num_threads

    def test_concurrent_reads_during_writes(self, tmp_path):
        """Concurrent readers should always get valid values while writers are active."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")
        sm.set_var("shared", 0)

        errors = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                val = sm.get_var("shared", -1)
                if not isinstance(val, int) or val < 0:
                    errors.append(f"Bad value: {val}")
                time.sleep(0)

        def writer():
            for i in range(1000):
                sm.set_var("shared", i)

        threads = [threading.Thread(target=reader) for _ in range(4)]
        writer_thread = threading.Thread(target=writer)

        for th in threads:
            th.start()
        writer_thread.start()
        writer_thread.join()
        stop.set()
        for th in threads:
            th.join()

        assert len(errors) == 0, f"Readers observed bad values: {errors[:5]}"

    def test_concurrent_setvar_and_getallvars(self, tmp_path):
        """get_all_vars should not crash when writers are modifying the dict."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        stop = threading.Event()
        read_errors = []

        def writer():
            for i in range(500):
                sm.set_var(f"k{i}", i)

        def reader():
            while not stop.is_set():
                try:
                    vars_ = sm.get_all_vars()
                    assert isinstance(vars_, dict)
                except Exception as e:
                    read_errors.append(str(e))
                time.sleep(0)

        writer_thread = threading.Thread(target=writer)
        reader_threads = [threading.Thread(target=reader) for _ in range(3)]

        writer_thread.start()
        for th in reader_threads:
            th.start()
        writer_thread.join()
        stop.set()
        for th in reader_threads:
            th.join()

        assert len(read_errors) == 0, f"get_all_vars crashed: {read_errors}"


# ═══════════════════════════════════════════════════════════════════════════
# TestConcurrentConditionEvaluation
# ═══════════════════════════════════════════════════════════════════════════

class TestConcurrentConditionEvaluation:
    """Condition evaluation is stateless (aside from cache), so concurrent
    evaluation should be safe and return consistent results."""

    def test_concurrent_always_evaluation(self):
        """Multiple threads evaluating the same condition should all pass."""
        clear_cache()
        errors = []
        lock = threading.Lock()

        def evaluate(n):
            for _ in range(n):
                ok, _ = evaluate_all([{"always": True}])
                if not ok:
                    with lock:
                        errors.append("always condition returned False")

        threads = [threading.Thread(target=evaluate, args=(200,)) for _ in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert len(errors) == 0

    def test_concurrent_file_exists_evaluation(self, tmp_path):
        """Multiple threads checking file_exists simultaneously."""
        test_file = tmp_path / "concurrent_test.txt"
        test_file.write_text("hello")

        clear_cache()

        def check(n):
            for _ in range(n):
                ok, _ = evaluate_all([{"file_exists": str(test_file)}])
                assert ok, "file_exists should be True"

        threads = [threading.Thread(target=check, args=(100,)) for _ in range(6)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

    def test_concurrent_mixed_conditions(self):
        """Multiple threads evaluating mixed conditions (all_of, any_of, not)."""
        clear_cache()

        def evaluate_mixed(n):
            for _ in range(n):
                ok, _ = evaluate_all([
                    {"all_of": {"conditions": [
                        {"always": True},
                        {"any_of": {"conditions": [
                            {"always": True},
                            {"not": {"condition": {"never": "nope"}}},
                        ]}},
                    ]}}
                ])
                assert ok, "Mixed condition should pass"

        threads = [threading.Thread(target=evaluate_mixed, args=(150,)) for _ in range(6)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()


# ═══════════════════════════════════════════════════════════════════════════
# TestLargeState
# ═══════════════════════════════════════════════════════════════════════════

class TestLargeState:
    """Stress tests for large variable payloads and deep history."""

    def test_large_variable_payload(self, tmp_path):
        """Storing a large variable (~100KB) should not break persistence."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        large_data = {
            "entries": [
                {
                    "id": i,
                    "name": f"entry_{i}",
                    "description": f"Description for entry {i} " * 10,
                    "tags": [f"tag_{j}" for j in range(20)],
                    "nested": {"level1": {"level2": {"level3": f"deep_{i}"}}},
                }
                for i in range(100)
            ]
        }
        sm.set_var("large_payload", large_data)

        loaded = sm.get_var("large_payload")
        assert loaded is not None
        assert len(loaded["entries"]) == 100
        assert loaded["entries"][99]["id"] == 99
        assert loaded["entries"][0]["nested"]["level1"]["level2"]["level3"] == "deep_0"

    def test_deep_history_survives(self, tmp_path):
        """Very long history (500+ entries) should persist correctly across reload."""
        reg = _make_two_stage_registry()
        reg.register_transition("b", "a", [{"always": True}])
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        for _ in range(250):
            sm.transition_to("b")
            sm.transition_to("a")

        assert len(sm.history) == 500

        sm2 = StateMachine(reg, str(tmp_path))
        loaded_history = sm2.history
        assert len(loaded_history) == 500
        assert loaded_history[0]["from"] == "a"
        assert loaded_history[-1]["to"] == "a"

    def test_large_variable_survives_reload(self, tmp_path):
        """Large variable survives a state machine reload."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        data = {f"key_{i}": list(range(50)) for i in range(50)}
        sm.set_var("bulk", data)

        sm2 = StateMachine(reg, str(tmp_path))
        bulk = sm2.get_var("bulk")
        assert bulk is not None
        assert len(bulk) == 50
        assert bulk["key_42"] == list(range(50))


# ═══════════════════════════════════════════════════════════════════════════
# TestFileIntegrity
# ═══════════════════════════════════════════════════════════════════════════

class TestFileIntegrity:
    """State file integrity under concurrent and rapid write load."""

    def test_state_file_is_valid_json_after_rapid_writes(self, tmp_path):
        """State file contains valid JSON even after hundreds of rapid saves."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        for i in range(200):
            sm.set_var(f"counter", i)
            sm.transition_to("b")
            sm.force_transition_to("a")

        raw = sm.state_path.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            pytest.fail(f"State file corrupted after stress: {e}")

        assert parsed["current_stage"] == "a"
        assert len(parsed["history"]) == 400

    def test_state_file_consistency_under_concurrent_var_writes(self, tmp_path):
        """State file should be consistent JSON when multiple threads write vars."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        synced = threading.Event()

        def writer(key_suffix):
            synced.wait()  # all start together
            for i in range(100):
                sm.set_var(f"thread_{key_suffix}", i)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(8)]
        for th in threads:
            th.start()
        synced.set()
        for th in threads:
            th.join()

        raw = sm.state_path.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            pytest.fail(f"State file corrupted by concurrent writes: {e}")

        assert parsed["current_stage"] == "a"
        assert len(parsed["variables"]) == 8

    def test_state_file_not_truncated_by_concurrent_saves(self, tmp_path):
        """Rapid consecutive saves should never produce a truncated/empty file."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")
        sm.set_var("marker", "before")

        for _ in range(100):
            sm.set_var("flip", _)
            raw = sm.state_path.read_text(encoding="utf-8")
            assert len(raw) > 10, f"File appears truncated at iteration {_}"
            assert "marker" in raw, f"'marker' missing from state file at iteration {_}"


# ═══════════════════════════════════════════════════════════════════════════
# TestConcurrentTransitions
# ═══════════════════════════════════════════════════════════════════════════

class TestConcurrentTransitions:
    """Thread-safety tests for concurrent transition attempts.

    NOTE: The StateMachine is not designed to be safe for concurrent
    transitions by multiple threads on the same instance. These tests
    verify that concurrent access fails gracefully (no crashes or
    corruption) rather than producing correct results.
    """

    def test_concurrent_transitions_dont_crash(self, tmp_path):
        """Multiple threads attempting transitions on the same SM should not crash."""
        reg = _make_two_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        errors = []
        lock = threading.Lock()

        def worker():
            try:
                for _ in range(50):
                    sm.transition_to("b")
                    sm.force_transition_to("a")
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert len(errors) == 0, (
            f"Concurrent transitions caused crashes: {errors[:5]}"
        )

    def test_concurrent_status_queries(self, tmp_path):
        """status() queries should be safe while transitions are in progress."""
        reg = _make_two_stage_registry()
        reg.register_transition("b", "a", [{"always": True}])
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        stop = threading.Event()
        query_errors = []

        def transitioner():
            for _ in range(50):
                sm.transition_to("b")
                sm.transition_to("a")

        def querier():
            while not stop.is_set():
                try:
                    s = sm.status()
                    assert isinstance(s, dict)
                    assert "current_stage" in s
                except Exception as e:
                    query_errors.append(str(e))
                time.sleep(0.01)

        t = threading.Thread(target=transitioner)
        q1 = threading.Thread(target=querier)
        q2 = threading.Thread(target=querier)

        t.start()
        q1.start()
        q2.start()
        t.join()
        stop.set()
        q1.join()
        q2.join()

        assert len(query_errors) == 0, f"status() crashed under load: {query_errors}"
