"""Performance sanity checks. Fast, deterministic, no sleeps or threads."""
from __future__ import annotations

import time

import pytest

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine
from stageflow.core.conditions import evaluate_all, set_cache_ttl, clear_cache


def _make_10_stage_registry():
    reg = StageRegistry.__new__(StageRegistry)
    for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
        setattr(reg, attr, {} if attr == "_stages" or "from" in attr or "to" in attr else [])
    from pathlib import Path
    reg.config_path = Path("nonexistent.yaml")
    for i in range(10):
        reg.register_stage(f"s{i}", tools=[])
    for i in range(9):
        reg.register_transition(f"s{i}", f"s{i+1}", [{"always": True}])
    return reg


class TestTransitionPerf:
    def test_100_transitions_under_5s(self, tmp_path):
        reg = _make_10_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("s0")
        t0 = time.perf_counter()
        for i in range(9):
            sm.transition_to(f"s{i+1}")
            sm.force_transition_to("s0")
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, f"18 transitions took {elapsed:.2f}s"

    def test_force_transition_is_faster_than_conditional(self, tmp_path):
        reg = _make_10_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("s0")
        sm.force_transition_to("s1")

        t0 = time.perf_counter()
        sm.transition_to("s2")
        t_cond = time.perf_counter() - t0

        sm.force_transition_to("s3")
        t0 = time.perf_counter()
        sm.force_transition_to("s4")
        t_force = time.perf_counter() - t0

        assert t_force < 0.1, f"Force transition: {t_force:.4f}s"


class TestConditionPerf:
    def test_1000_always_evals_under_2s(self, tmp_path):
        set_cache_ttl(0)
        t0 = time.perf_counter()
        for _ in range(1000):
            evaluate_all([{"always": True}], str(tmp_path))
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, f"1000 always evals: {elapsed:.2f}s"

    def test_100_file_exists_evals_under_1s(self, tmp_path):
        f = tmp_path / "perf_test.txt"
        f.write_text("ok")
        set_cache_ttl(0)
        t0 = time.perf_counter()
        for _ in range(100):
            evaluate_all([{"file_exists": "perf_test.txt"}], str(tmp_path))
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"100 file_exists evals: {elapsed:.2f}s"


class TestStatusPerf:
    def test_status_under_10ms(self, tmp_path):
        reg = _make_10_stage_registry()
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("s5")
        t0 = time.perf_counter()
        s = sm.status()
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.01, f"status(): {elapsed*1000:.2f}ms"
        assert s["current_stage"] == "s5"


class TestCachePerf:
    def test_cached_evals_faster_than_uncached(self, tmp_path):
        f = tmp_path / "cache_perf_test.txt"
        f.write_text("ok")

        clear_cache()
        set_cache_ttl(60.0)
        t0 = time.perf_counter()
        for _ in range(200):
            evaluate_all([{"file_exists": "cache_perf_test.txt"}], str(tmp_path))
        t_cached = time.perf_counter() - t0

        set_cache_ttl(0)
        t0 = time.perf_counter()
        for _ in range(200):
            evaluate_all([{"file_exists": "cache_perf_test.txt"}], str(tmp_path))
        t_uncached = time.perf_counter() - t0

        assert t_cached < t_uncached, (
            f"cached: {t_cached:.4f}s, uncached: {t_uncached:.4f}s"
        )


class TestRegistryPerf:
    def test_1000_stage_registry_validates(self):
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if "_stages" in attr or "from" in attr or "to" in attr else [])
        from pathlib import Path
        reg.config_path = Path("nonexistent.yaml")
        t0 = time.perf_counter()
        for i in range(1000):
            reg.register_stage(f"stage_{i}", tools=[])
        for i in range(999):
            reg.register_transition(f"stage_{i}", f"stage_{i+1}", [{"always": True}])
        elapsed = time.perf_counter() - t0
        assert elapsed < 3.0, f"1000-stage registry: {elapsed:.2f}s"
        ok, errs = reg.validate()
        assert ok, f"Validation errors: {errs}"
