"""Extensibility proof: create, connect, and exercise N stages dynamically.

This is the core test that validates the user's prime requirement: the framework
must support adding/removing any number of stages with zero code changes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine


def test_extensibility_n_stages(n: int = 15):
    """Create N stages dynamically, connect them with transitions,
    transition through all of them, then remove half and verify cleanup."""
    reg = StageRegistry.__new__(StageRegistry)
    reg._stages = {}
    reg._transitions = []
    reg._transitions_from = {}
    reg._transitions_to = {}
    reg.config_path = Path("nonexistent.yaml")

    # ── Phase 1: Register N stages ──────────────────────────────────────
    print(f"=== Phase 1: Registering {n} stages ===")
    for i in range(n):
        tools = [f"Tool_{i % 5}"]  # Each stage gets different tools
        reg.register_stage(f"stage_{i:03d}", tools=tools,
                           description=f"Test stage {i}")
    assert len(reg._stages) == n, f"Expected {n} stages, got {len(reg._stages)}"
    print(f"  OK: {n} stages registered")

    # ── Phase 2: Create transitions between consecutive stages ──────────
    print(f"=== Phase 2: Creating {n - 1} transitions ===")
    for i in range(n - 1):
        reg.register_transition(f"stage_{i:03d}", f"stage_{i + 1:03d}",
                                conditions=[{"always": True}])
    assert len(reg._transitions) == n - 1
    print(f"  OK: {n - 1} transitions created")

    # ── Phase 3: Validate ───────────────────────────────────────────────
    print(f"=== Phase 3: Validation ===")
    ok, errs = reg.validate()
    assert ok, f"Validation failed: {errs}"
    print(f"  OK: Graph is valid")

    # ── Phase 4: Transition through ALL stages ──────────────────────────
    print(f"=== Phase 4: Full traversal ===")
    sm = StateMachine(reg, str(Path(__file__).resolve().parent.parent))
    sm.initialize("stage_000")
    assert sm.current_stage == "stage_000"

    for i in range(1, n):
        ok, msgs = sm.transition_to(f"stage_{i:03d}")
        assert ok, f"Transition to stage_{i:03d} failed: {msgs}"
    assert sm.current_stage == f"stage_{n-1:03d}"
    assert len(sm.history) == n - 1
    print(f"  OK: Traversed all {n} stages ({n - 1} transitions)")

    # ── Phase 5: Tool access check per stage ────────────────────────────
    print(f"=== Phase 5: Tool access per stage ===")
    sm.initialize("stage_005")
    ok, _ = sm.is_tool_allowed("Tool_0")
    assert ok, f"Tool_0 should be allowed in stage_005 (5 % 5 = 0)"
    ok, _ = sm.is_tool_allowed("Tool_1")
    assert not ok, f"Tool_1 should NOT be allowed in stage_005"
    print(f"  OK: Per-stage tool restrictions work")

    # ── Phase 6: Remove middle stage ────────────────────────────────────
    print(f"=== Phase 6: Remove stage and verify cleanup ===")
    reg.unregister_stage("stage_007")
    assert "stage_007" not in reg._stages
    # Transitions involving the removed stage should be gone
    assert all(t.from_stage != "stage_007" and t.to_stage != "stage_007"
               for t in reg._transitions)
    print(f"  OK: Stage removed, transitions cleaned up")

    # ── Phase 7: Re-add and reconnect ───────────────────────────────────
    print(f"=== Phase 7: Re-add stage and reconnect ===")
    reg.register_stage("stage_007", tools=["Tool_2", "Tool_3"])
    reg.register_transition("stage_006", "stage_007", [{"always": True}])
    reg.register_transition("stage_007", "stage_008", [{"always": True}])
    assert "stage_007" in reg._stages
    assert len(reg.get_transitions_from("stage_007")) == 1
    print(f"  OK: Stage re-added and reconnected")

    # ── Phase 8: Verify traversable again ───────────────────────────────
    print(f"=== Phase 8: Verify traversal after re-add ===")
    sm.initialize("stage_006")
    ok, msgs = sm.transition_to("stage_007")
    assert ok, f"stage_006 -> stage_007 failed: {msgs}"
    ok, msgs = sm.transition_to("stage_008")
    assert ok, f"stage_007 -> stage_008 failed: {msgs}"
    print(f"  OK: Reconnected path traversable")

    # ── Phase 9: Idempotent removal ─────────────────────────────────────
    print(f"=== Phase 9: Idempotent removal ===")
    reg.unregister_stage("nonexistent_stage")  # Guaranteed non-existent
    assert len(reg._stages) == n  # Unchanged: remove was a no-op
    print(f"  OK: Non-existent stage removal is safe (no-op)")

    print(f"\n{'=' * 60}")
    print(f"ALL EXTENSIBILITY TESTS PASSED ({n} stages)")
    print(f"{'=' * 60}")
    # All assertions passed — if we reached here, the test succeeded.
    assert True


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    test_extensibility_n_stages(n)
