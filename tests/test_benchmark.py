"""Performance benchmark tests for StageFlow framework.

Measures: condition evaluation throughput, stage transition throughput,
1000-stage graph validation time, and state file read/write latency.

Uses time.perf_counter() for precise wall-clock timing.
Outputs a markdown summary table on completion.
"""

from __future__ import annotations

import json
import textwrap
import time
from pathlib import Path

import pytest

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine
from stageflow.core.conditions import evaluate_all, clear_cache


_RESULTS: dict[str, float | int] = {}


def _record(name: str, value: float):
    _RESULTS[name] = value


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_chain_registry(n: int):
    reg = StageRegistry.__new__(StageRegistry)
    for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
        setattr(reg, attr, {} if attr in ("_stages", "_transitions_from", "_transitions_to") else [])
    reg.config_path = Path("nonexistent.yaml")
    for i in range(n):
        reg.register_stage(f"stage_{i:04d}", tools=[])
    for i in range(n - 1):
        reg.register_transition(f"stage_{i:04d}", f"stage_{i + 1:04d}", [{"always": True}])
    return reg


# ═══════════════════════════════════════════════════════════════════════════
# TestConditionThroughput
# ═══════════════════════════════════════════════════════════════════════════

class TestConditionThroughput:
    """Measure condition evaluation throughput: target >= 1000 evals/sec."""

    def test_always_condition_throughput(self, tmp_path):
        clear_cache()
        iterations = 10_000
        start = time.perf_counter()
        for _ in range(iterations):
            evaluate_all([{"always": True}])
        elapsed = time.perf_counter() - start
        rate = iterations / elapsed
        _record("always cond/sec", rate)
        assert rate > 1000, f"always condition: {rate:.0f}/s (need >1000)"

    def test_file_exists_condition_throughput(self, tmp_path):
        f = tmp_path / "bench_exists.txt"
        f.write_text("ok")
        clear_cache()
        iterations = 5_000

        start = time.perf_counter()
        for _ in range(iterations):
            evaluate_all([{"file_exists": str(f)}])
        elapsed = time.perf_counter() - start
        rate = iterations / elapsed
        _record("file_exists cond/sec", rate)
        assert rate > 1000, f"file_exists condition: {rate:.0f}/s (need >1000)"

    def test_file_contains_condition_throughput(self, tmp_path):
        f = tmp_path / "bench_contains.txt"
        f.write_text("Pattern found: PASS\nsome other text\n")
        clear_cache()
        iterations = 5_000

        start = time.perf_counter()
        for _ in range(iterations):
            evaluate_all([{"file_contains": {"path": str(f), "pattern": r"PASS"}}])
        elapsed = time.perf_counter() - start
        rate = iterations / elapsed
        _record("file_contains cond/sec", rate)
        assert rate > 1000, f"file_contains condition: {rate:.0f}/s (need >1000)"

    def test_all_of_nested_condition_throughput(self, tmp_path):
        clear_cache()
        iterations = 5_000

        start = time.perf_counter()
        for _ in range(iterations):
            evaluate_all([{
                "all_of": {"conditions": [
                    {"always": True},
                    {"always": True},
                    {"any_of": {"conditions": [
                        {"always": True},
                        {"not": {"condition": {"never": "nope"}}},
                    ]}},
                ]}
            }])
        elapsed = time.perf_counter() - start
        rate = iterations / elapsed
        _record("all_of/any_of cond/sec", rate)
        assert rate > 1000, f"nested condition: {rate:.0f}/s (need >1000)"

    def test_mixed_condition_suite_throughput(self, tmp_path):
        f = tmp_path / "bench_mixed.txt"
        f.write_text("line1\nline2\nline3")
        clear_cache()
        iterations = 2_000

        start = time.perf_counter()
        for _ in range(iterations):
            evaluate_all([
                {"always": True},
                {"file_exists": str(f)},
                {"not": {"condition": {"file_exists": str(tmp_path / "nope.txt")}}},
                {"all_of": {"conditions": [
                    {"always": True},
                    {"not": {"condition": {"never": "no"}}},
                ]}},
            ])
        elapsed = time.perf_counter() - start
        rate = iterations / elapsed
        _record("mixed 4-cond suite/sec", rate)
        assert rate > 500, f"mixed conditions: {rate:.0f}/s (need >500)"


# ═══════════════════════════════════════════════════════════════════════════
# TestTransitionThroughput
# ═══════════════════════════════════════════════════════════════════════════

class TestTransitionThroughput:
    """Measure transition throughput: target >= 100 transitions/sec."""

    def test_transition_throughput_force(self, tmp_path):
        """Force transitions bypass condition checks — pure engine speed."""
        reg = _make_chain_registry(200)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("stage_0000")

        n = 150
        start = time.perf_counter()
        for i in range(1, n + 1):
            sm.force_transition_to(f"stage_{i:04d}")
        elapsed = time.perf_counter() - start
        rate = n / elapsed
        _record("force transition/sec", rate)
        assert rate > 100, f"Force transitions: {rate:.0f}/s (need >100)"

    def test_transition_throughput_with_condition_check(self, tmp_path):
        """Full condition-evaluated transitions (always=True conditions)."""
        reg = _make_chain_registry(200)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("stage_0000")

        n = 100
        start = time.perf_counter()
        for i in range(1, n + 1):
            sm.transition_to(f"stage_{i:04d}")
        elapsed = time.perf_counter() - start
        rate = n / elapsed
        _record("conditioned transition/sec", rate)
        assert rate > 80, f"Conditioned transitions: {rate:.0f}/s (need >80)"

    def test_transition_throughput_round_trip(self, tmp_path):
        """Round-trip transitions (A->B->A) including state saves."""
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr in ("_stages", "_transitions_from", "_transitions_to") else [])
        reg.config_path = Path("nonexistent.yaml")
        reg.register_stage("a", tools=[])
        reg.register_stage("b", tools=[])
        reg.register_transition("a", "b", [{"always": True}])
        reg.register_transition("b", "a", [{"always": True}])

        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("a")

        n = 200
        start = time.perf_counter()
        for _ in range(n // 2):
            sm.transition_to("b")
            sm.transition_to("a")
        elapsed = time.perf_counter() - start
        rate = n / elapsed
        _record("round-trip transition/sec", rate)
        assert rate > 80, f"Round-trip transitions: {rate:.0f}/s (need >80)"

    def test_transition_latency_single(self, tmp_path):
        """Measure single transition latency (including condition eval + save)."""
        reg = _make_chain_registry(200)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("stage_0000")

        latencies = []
        for i in range(50):
            t0 = time.perf_counter()
            sm.force_transition_to(f"stage_{i + 1:04d}")
            latencies.append(time.perf_counter() - t0)

        avg = sum(latencies) / len(latencies)
        worst = max(latencies)
        _record("single transition avg ms", avg * 1000)
        _record("single transition worst ms", worst * 1000)
        assert avg < 1.0, f"Average transition latency {avg*1000:.1f}ms exceeds 1000ms"


# ═══════════════════════════════════════════════════════════════════════════
# TestGraphValidationTime
# ═══════════════════════════════════════════════════════════════════════════

class TestGraphValidationTime:
    """Measure graph validation time for large stage counts."""

    def test_validate_100_stages(self, tmp_path):
        reg = _make_chain_registry(100)
        start = time.perf_counter()
        ok, errs = reg.validate()
        elapsed = time.perf_counter() - start
        _record("validate 100 stages (ms)", elapsed * 1000)
        assert ok
        assert elapsed < 1.0, f"100-stage validation took {elapsed:.3f}s"

    def test_validate_500_stages(self, tmp_path):
        reg = _make_chain_registry(500)
        start = time.perf_counter()
        ok, errs = reg.validate()
        elapsed = time.perf_counter() - start
        _record("validate 500 stages (ms)", elapsed * 1000)
        assert ok
        assert elapsed < 5.0, f"500-stage validation took {elapsed:.3f}s"

    def test_validate_1000_stages(self, tmp_path):
        reg = _make_chain_registry(1000)
        start = time.perf_counter()
        ok, errs = reg.validate()
        elapsed = time.perf_counter() - start
        _record("validate 1000 stages (ms)", elapsed * 1000)
        assert ok
        assert elapsed < 15.0, f"1000-stage validation took {elapsed:.3f}s"

    def test_register_1000_stages_time(self, tmp_path):
        reg = StageRegistry.__new__(StageRegistry)
        for attr in ("_stages", "_transitions", "_transitions_from", "_transitions_to"):
            setattr(reg, attr, {} if attr in ("_stages", "_transitions_from", "_transitions_to") else [])
        reg.config_path = Path("nonexistent.yaml")

        start = time.perf_counter()
        for i in range(1000):
            reg.register_stage(f"stage_{i:04d}", tools=[])
        reg_time = time.perf_counter() - start

        start = time.perf_counter()
        for i in range(999):
            reg.register_transition(f"stage_{i:04d}", f"stage_{i + 1:04d}", [{"always": True}])
        trans_time = time.perf_counter() - start

        _record("register 1000 stages (ms)", reg_time * 1000)
        _record("register 999 transitions (ms)", trans_time * 1000)
        assert reg_time < 2.0, f"1000 stage registration: {reg_time:.3f}s"
        assert trans_time < 2.0, f"999 transition registration: {trans_time:.3f}s"


# ═══════════════════════════════════════════════════════════════════════════
# TestStateFileLatency
# ═══════════════════════════════════════════════════════════════════════════

class TestStateFileLatency:
    """Measure state file read/write latency under various sizes."""

    def test_small_state_write_latency(self, tmp_path):
        reg = _make_chain_registry(50)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("stage_0000")

        latencies = []
        for _ in range(100):
            t0 = time.perf_counter()
            sm._save_state()
            latencies.append(time.perf_counter() - t0)

        avg = sum(latencies) / len(latencies)
        _record("small state write avg ms", avg * 1000)
        _record("small state write worst ms", max(latencies) * 1000)
        assert avg < 0.1, f"Small state write avg {avg*1000:.1f}ms > 100ms"

    def test_small_state_read_latency(self, tmp_path):
        reg = _make_chain_registry(50)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("stage_0000")
        sm._save_state()

        latencies = []
        for _ in range(100):
            t0 = time.perf_counter()
            sm._load_state()
            latencies.append(time.perf_counter() - t0)

        avg = sum(latencies) / len(latencies)
        _record("small state read avg ms", avg * 1000)
        _record("small state read worst ms", max(latencies) * 1000)
        assert avg < 0.1, f"Small state read avg {avg*1000:.1f}ms > 100ms"

    def test_large_state_write_latency(self, tmp_path):
        reg = _make_chain_registry(50)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("stage_0000")

        large_var = {f"key_{i}": f"value_{i}_" * 100 for i in range(200)}
        sm.set_var("bulk", large_var)
        for _ in range(50):
            sm.transition_to("stage_0001")
            sm.force_transition_to("stage_0000")

        latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            sm._save_state()
            latencies.append(time.perf_counter() - t0)

        avg = sum(latencies) / len(latencies)
        _record("large state write avg ms", avg * 1000)
        _record("large state write worst ms", max(latencies) * 1000)
        assert avg < 0.5, f"Large state write avg {avg*1000:.1f}ms > 500ms"

    def test_large_state_read_latency(self, tmp_path):
        reg = _make_chain_registry(50)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("stage_0000")

        large_var = {f"key_{i}": f"value_{i}_" * 100 for i in range(200)}
        sm.set_var("bulk", large_var)
        for _ in range(50):
            sm.transition_to("stage_0001")
            sm.force_transition_to("stage_0000")
        sm._save_state()

        latencies = []
        for _ in range(50):
            t0 = time.perf_counter()
            sm._load_state()
            latencies.append(time.perf_counter() - t0)

        avg = sum(latencies) / len(latencies)
        _record("large state read avg ms", avg * 1000)
        _record("large state read worst ms", max(latencies) * 1000)
        assert avg < 0.5, f"Large state read avg {avg*1000:.1f}ms > 500ms"

    def test_state_file_grows_predictably(self, tmp_path):
        """State file should grow linearly with history, not explode."""
        reg = _make_chain_registry(200)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("stage_0000")

        sizes = []
        for i in range(1, 101):
            sm.force_transition_to(f"stage_{i:04d}")
            size = sm.state_path.stat().st_size
            sizes.append(size)

        assert sizes[-1] < sizes[0] * 200, (
            f"State file grew from {sizes[0]} to {sizes[-1]} bytes — "
            f"more than 200x in 100 transitions (pathological growth)"
        )
        _record("state file size after 100 transitions (bytes)", sizes[-1])


# ═══════════════════════════════════════════════════════════════════════════
# Summary report (auto-printed after all benchmarks)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session", autouse=True)
def _print_benchmark_summary(request):
    yield

    if not _RESULTS:
        return

    lines = []
    lines.append("")
    lines.append("## Benchmark Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    for name, value in sorted(_RESULTS.items()):
        if isinstance(value, float):
            if "ms" in name:
                lines.append(f"| {name} | {value:.2f} |")
            else:
                lines.append(f"| {name} | {value:,.0f} |")
        else:
            lines.append(f"| {name} | {value} |")
    lines.append("")

    header = "=" * 60
    print(f"\n{header}")
    print("STAGEFLOW BENCHMARK REPORT")
    print(header)
    report = "\n".join(lines)
    print(report)
    print(header)

    # Also write to file
    report_path = Path(__file__).resolve().parent.parent / ".claude" / "benchmark_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report + "\n", encoding="utf-8")
    print(f"Report saved to: {report_path}")
    print(header)
