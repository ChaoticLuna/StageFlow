"""Concurrency and stress tests for StageFlow state machine.

Verifies state integrity under rapid consecutive transitions,
state file persistence correctness, and performance baselines.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine


def _setup_5_stage_pipeline(reg: StageRegistry):
    """Register 5 stages (a→b→c→d→e) with always conditions."""
    for name in ("a", "b", "c", "d", "e"):
        reg.register_stage(name, tools=[])
    for src, dst in (("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")):
        reg.register_transition(src, dst, [{"always": True}])


def _setup_10_stage_pipeline(reg: StageRegistry):
    """Register 10 stages (s0→s1→...→s9) with always conditions."""
    for i in range(10):
        reg.register_stage(f"s{i}", tools=[])
    for i in range(9):
        reg.register_transition(f"s{i}", f"s{i+1}", [{"always": True}])


# ═══════════════════════════════════════════════════════════════════════════
# Rapid transition stress tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRapidConsecutiveTransitions:
    """Stress tests for many rapid consecutive transitions."""

    def test_50_forward_transitions_maintain_state(self, stageflow_empty_registry, tmp_path):
        _setup_10_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("s0")

        for _ in range(50):
            sm.force_transition_to("s1")
            assert sm.current_stage == "s1"
            sm.force_transition_to("s2")
            assert sm.current_stage == "s2"
            sm.force_transition_to("s3")
            assert sm.current_stage == "s3"
            sm.force_transition_to("s2")
            assert sm.current_stage == "s2"
            sm.force_transition_to("s0")
            assert sm.current_stage == "s0"

        assert len(sm.history) == 250

    def test_100_round_trips_no_corruption(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        for i in range(100):
            sm.transition_to("b")
            assert sm.current_stage == "b", f"Iteration {i}: expected b, got {sm.current_stage}"
            sm.transition_to("c")
            assert sm.current_stage == "c", f"Iteration {i}: expected c, got {sm.current_stage}"
            sm.force_transition_to("a")
            assert sm.current_stage == "a", f"Iteration {i}: expected a, got {sm.current_stage}"

        assert len(sm.history) == 300

    def test_history_accurate_after_200_transitions(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        expected = ["a"]
        for _ in range(40):
            sm.transition_to("b"); expected.append("b")
            sm.transition_to("c"); expected.append("c")
            sm.transition_to("d"); expected.append("d")
            sm.transition_to("e"); expected.append("e")
            sm.force_transition_to("a"); expected.append("a")

        assert len(sm.history) == 200
        for i, (h, exp) in enumerate(zip(sm.history, expected[1:])):
            assert h["to"] == exp, f"History[{i}]: expected to={exp}, got to={h['to']}"

    def test_state_file_integrity_after_each_transition(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        stages = ["b", "c", "d", "e", "d", "c", "b", "a"]
        for target in stages:
            # Forward transitions use normal transition_to; backward uses force
            if (sm.current_stage, target) in (("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")):
                sm.transition_to(target)
            else:
                sm.force_transition_to(target)
            assert sm.current_stage == target

            # Verify state file integrity
            sm2 = StateMachine(stageflow_empty_registry, str(tmp_path))
            assert sm2.current_stage == target, f"State file mismatch: expected {target}, got {sm2.current_stage}"

    def test_state_json_is_valid_after_rapid_writes(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        for _ in range(50):
            sm.transition_to("b")
            sm.force_transition_to("a")

        raw = sm.state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert data["current_stage"] == "a"
        assert len(data["history"]) == 100


# ═══════════════════════════════════════════════════════════════════════════
# Performance benchmarks
# ═══════════════════════════════════════════════════════════════════════════

class TestTransitionPerformance:
    """Performance benchmarks for transition speed."""

    def test_5_transitions_under_half_second(self, stageflow_empty_registry, tmp_path):
        _setup_10_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("s0")

        start = time.perf_counter()
        sm.transition_to("s1")
        sm.transition_to("s2")
        sm.transition_to("s3")
        sm.transition_to("s4")
        sm.transition_to("s5")
        elapsed = time.perf_counter() - start

        assert sm.current_stage == "s5"
        assert elapsed < 0.5, f"5 transitions took {elapsed:.4f}s, expected < 0.5s"

    def test_100_transitions_under_10_seconds(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        start = time.perf_counter()
        for _ in range(25):
            sm.transition_to("b")
            sm.transition_to("c")
            sm.transition_to("d")
            sm.transition_to("e")
            sm.force_transition_to("a")
        elapsed = time.perf_counter() - start

        assert sm.current_stage == "a"
        assert elapsed < 10.0, f"100 transitions took {elapsed:.4f}s, expected < 10s"

    def test_force_vs_conditional_transition_speed(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))

        # Measure conditional (always-pass) transition
        sm.initialize("a")
        start = time.perf_counter()
        sm.transition_to("b")
        cond_time = time.perf_counter() - start

        # Measure force transition
        sm.force_transition_to("a")
        start = time.perf_counter()
        sm.force_transition_to("b")
        force_time = time.perf_counter() - start

        assert force_time <= cond_time * 2, (
            f"Force ({force_time:.6f}s) should not be much slower than "
            f"conditional ({cond_time:.6f}s)"
        )

    def test_state_file_write_latency(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        latencies = []
        for _ in range(20):
            start = time.perf_counter()
            sm.force_transition_to("b")
            sm.force_transition_to("a")
            latencies.append(time.perf_counter() - start)

        avg = sum(latencies) / len(latencies)
        assert avg < 0.05, f"Average round-trip latency {avg:.6f}s, expected < 0.05s"


# ═══════════════════════════════════════════════════════════════════════════
# State integrity under stress
# ═══════════════════════════════════════════════════════════════════════════

class TestStateIntegrityUnderStress:
    """State integrity and persistence under rapid operations."""

    def test_variables_survive_rapid_transitions(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")
        sm.set_var("count", 0)
        sm.set_var("key", "value")

        for i in range(50):
            sm.transition_to("b")
            sm.set_var("count", i + 1)
            sm.force_transition_to("a")

        assert sm.get_var("count") == 50
        assert sm.get_var("key") == "value"

    def test_retry_count_survives_rapid_failures(self, stageflow_empty_registry, tmp_path):
        reg = stageflow_empty_registry
        reg.register_stage("src", tools=[])
        reg.register_stage("blocked", tools=[])
        reg.register_transition("src", "blocked", [{"never": "always blocked"}], on_fail="src")

        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("src")

        for i in range(25):
            sm.transition_to("blocked")
            assert sm.current_stage == "src"
            assert sm.get_retry_count("src") == i + 1

    def test_iterations_tracked_across_transitions(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        sm.transition_to("b")
        sm.transition_to("c")
        sm.force_transition_to("b")
        sm.transition_to("c")

        assert sm.get_iterations("b") == 2
        assert sm.get_iterations("c") == 2

    def test_state_reload_after_many_writes(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")
        sm.set_var("x", 42)

        for _ in range(30):
            sm.transition_to("b")
            sm.force_transition_to("a")

        sm2 = StateMachine(stageflow_empty_registry, str(tmp_path))
        assert sm2.current_stage == "a"
        assert sm2.get_var("x") == 42
        assert len(sm2.history) == 60

    def test_no_duplicate_history_entries(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        for _ in range(20):
            sm.transition_to("b")
            sm.force_transition_to("a")

        assert len(sm.history) == 40
        # Verify all entries are correct (from/to pattern alternates a<->b)
        for i, (h, expected_to) in enumerate(zip(sm.history, ["b", "a"] * 20)):
            assert h["to"] == expected_to, f"History[{i}]: expected to={expected_to}"
        # Timestamps should be non-decreasing
        for i in range(1, len(sm.history)):
            assert sm.history[i]["at"] >= sm.history[i - 1]["at"]

    def test_history_order_is_sequential(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        sequence = ["b", "c", "d", "e", "d", "c", "b", "a"] * 10
        for target in sequence:
            if target in stageflow_empty_registry.get_next_stages(sm.current_stage):
                sm.transition_to(target)
            else:
                sm.force_transition_to(target)

        assert len(sm.history) == len(sequence)
        for i, (h, expected_to) in enumerate(zip(sm.history, sequence)):
            assert h["to"] == expected_to, f"History[{i}]: expected to={expected_to}, got to={h['to']}"


# ═══════════════════════════════════════════════════════════════════════════
# Rapid initialization and reset cycles
# ═══════════════════════════════════════════════════════════════════════════

class TestRapidInitReset:
    """Stress tests for rapid initialize/reset cycles."""

    def test_rapid_initialize_reset_cycle(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)

        for _ in range(20):
            sm = StateMachine(stageflow_empty_registry, str(tmp_path))
            sm.initialize("a")
            assert sm.current_stage == "a"
            sm.transition_to("b")
            assert sm.current_stage == "b"
            sm.reset()
            assert sm.current_stage is None

    def test_reinitialize_clears_old_state(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")
        sm.transition_to("b")
        sm.set_var("old", "data")
        assert sm.current_stage == "b"
        assert sm.get_var("old") == "data"

        sm.initialize("c")
        assert sm.current_stage == "c"
        assert sm.get_var("old") is None
        assert len(sm.history) == 0

    def test_state_file_clean_after_reset(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")
        sm.transition_to("b")
        assert sm.state_path.exists()

        sm.reset()
        assert not sm.state_path.exists()


# ═══════════════════════════════════════════════════════════════════════════
# Concurrent-style interleaved operations
# ═══════════════════════════════════════════════════════════════════════════

class TestInterleavedOperations:
    """Tests that simulate concurrent-style interleaved operations."""

    def test_interleaved_read_write_no_corruption(self, stageflow_empty_registry, tmp_path):
        """Simulate multiple "agents" reading/writing state alternately."""
        _setup_5_stage_pipeline(stageflow_empty_registry)
        sm = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm.initialize("a")

        for i in range(50):
            # Write
            sm.force_transition_to("b")
            sm.set_var(f"k{i}", i)
            # Read back via fresh SM
            reader = StateMachine(stageflow_empty_registry, str(tmp_path))
            assert reader.current_stage == "b"
            assert reader.get_var(f"k{i}") == i
            # Write again
            sm.force_transition_to("a")

        assert sm.current_stage == "a"
        for i in range(50):
            assert sm.get_var(f"k{i}") == i

    def test_sequential_sm_instances_share_state(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)

        sm1 = StateMachine(stageflow_empty_registry, str(tmp_path))
        sm1.initialize("a")
        sm1.set_var("shared", [1, 2, 3])

        sm2 = StateMachine(stageflow_empty_registry, str(tmp_path))
        assert sm2.current_stage == "a"
        assert sm2.get_var("shared") == [1, 2, 3]

        sm2.transition_to("b")
        sm2.set_var("shared", [1, 2, 3, 4])

        sm3 = StateMachine(stageflow_empty_registry, str(tmp_path))
        assert sm3.current_stage == "b"
        assert sm3.get_var("shared") == [1, 2, 3, 4]

    def test_multiple_state_machines_no_cross_contamination(self, stageflow_empty_registry, tmp_path):
        _setup_5_stage_pipeline(stageflow_empty_registry)

        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir(); dir_b.mkdir()

        sm_a = StateMachine(stageflow_empty_registry, str(dir_a))
        sm_b = StateMachine(stageflow_empty_registry, str(dir_b))

        sm_a.initialize("a")
        sm_b.initialize("c")

        sm_a.set_var("owner", "alpha")
        sm_b.set_var("owner", "beta")

        sm_a.transition_to("b")
        sm_b.transition_to("d")

        assert sm_a.current_stage == "b"
        assert sm_b.current_stage == "d"
        assert sm_a.get_var("owner") == "alpha"
        assert sm_b.get_var("owner") == "beta"
