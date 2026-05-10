#!/usr/bin/env python3
"""StageFlow Demo - Complete end-to-end workflow simulation.

This script demonstrates the full StageFlow pipeline from scratch:
  1. Define stages dynamically
  2. Initialize state machine
  3. Advance through all stages with conditions
  4. Handle rollback and retry
  5. Visualize the graph
  6. Show audit trail

Run: python demo/demo_workflow.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine
from stageflow.core.conditions import list_conditions


def demo():
    print("=" * 60)
    print("  StageFlow Demo - AI-Driven Issue Delivery Pipeline")
    print("=" * 60)

    # ── Setup ──────────────────────────────────────────────────────
    workdir = Path(tempfile.mkdtemp())
    reg = StageRegistry.__new__(StageRegistry)
    reg._stages = {}
    reg._transitions = []
    reg._transitions_from = {}
    reg._transitions_to = {}
    reg.config_path = Path("nonexistent.yaml")
    sm = StateMachine(reg, str(workdir))

    # ── Define stages ──────────────────────────────────────────────
    print("\n[1] Defining stages...")
    stages = [
        ("pick", ["Read", "Grep", "Glob", "WebSearch"]),
        ("analyze", ["Read", "Grep", "Glob", "WebSearch", "Bash(python *)"]),
        ("plan", ["Read", "Write", "Edit", "Grep"]),
        ("implement", ["Read", "Write", "Edit", "Bash(git *)"]),
        ("verify", ["Read", "Bash(pytest *)", "Bash(python *)"]),
        ("document", ["Read", "Write", "Edit"]),
        ("mr", ["Read", "Bash(git *)", "Bash(gh *)"]),
        ("review", ["Read", "Grep", "Bash(git *)"]),
        ("wrap_up", ["Read", "Write", "Bash(git *)"]),
    ]
    for name, tools in stages:
        reg.register_stage(name, tools=tools)
    print(f"   Registered {len(stages)} stages")

    # ── Define transitions with conditions ─────────────────────────
    print("\n[2] Defining transitions with conditions...")
    transitions = [
        ("pick", "analyze", [{"always": True}]),
        ("analyze", "plan", [{"file_exists": "FAKE_artifacts/findings.md"}], "analyze"),
        ("plan", "implement", [{"file_exists": "FAKE_artifacts/task_plan.md"}], "plan"),
        ("implement", "verify", [{"always": True}], "implement"),
        ("verify", "document", [{"file_exists": "FAKE_artifacts/test_results.md"}], "implement"),
        ("verify", "implement", [{"never": "test failed - retry implement"}]),  # retry path
        ("document", "mr", [{"always": True}]),
        ("mr", "review", [{"always": True}]),
        ("review", "wrap_up", [{"always": True}]),
        ("review", "implement", [{"never": "changes requested"}]),  # revise path
    ]
    for from_s, to_s, conds, *fail in transitions:
        reg.register_transition(from_s, to_s, conds,
                                on_fail=fail[0] if fail else None)
    print(f"   Defined {len(transitions)} transitions")

    # ── Validate ───────────────────────────────────────────────────
    ok, errs = reg.validate()
    print(f"\n[3] Graph validation: {'PASS' if ok else 'FAIL'}")
    for e in errs:
        print(f"   - {e}")

    # ── Walk through pipeline ──────────────────────────────────────
    print("\n[4] Walking through pipeline...\n")
    sm.initialize("pick")
    print(f"   [INIT]  {sm.current_stage}")

    pipeline = ["analyze", "plan", "implement", "verify", "document", "mr", "review", "wrap_up"]
    for target in pipeline:
        ok, msgs = sm.transition_to(target)
        status = "OK" if ok else "FAIL"
        print(f"   [{status}] {sm.history[-1]['from']} -> {sm.history[-1].get('to','?')}")
        if not ok:
            for m in msgs[-2:]:
                print(f"          {m}")
            # Use force for demo purposes (real pipeline would create artifacts)
            sm.force_transition_to(target)
            print(f"   [FORCE] -> {sm.current_stage}")

    # ── Show history ───────────────────────────────────────────────
    print(f"\n[5] Transition history ({len(sm.history)} steps):")
    for h in sm.history:
        print(f"   {h['from']:>10} -> {h.get('to', '?'):<10}  ({h.get('at','?')[:19]})")

    # ── Show stats ─────────────────────────────────────────────────
    print(f"\n[6] Statistics:")
    print(f"   Current stage    : {sm.current_stage}")
    print(f"   Total transitions: {len(sm.history)}")
    print(f"   Available conditions: {len(list_conditions())} types")
    status = sm.status()
    if status.get("retry_count"):
        print(f"   Retry counts: {status['retry_count']}")
    if status.get("iterations"):
        print(f"   Iterations : {status['iterations']}")

    # ── Audit summary ──────────────────────────────────────────────
    print(f"\n[7] Audit trail:")
    summary = sm.audit.get_summary()
    for k, v in summary.items():
        print(f"   {k}: {v}")

    # ── Show stage graph ───────────────────────────────────────────
    print(f"\n[8] Stage graph (Mermaid):")
    print(f"   Run 'python -m stageflow graph' to visualize")

    print(f"\n{'=' * 60}")
    print(f"  Demo complete. StageFlow is ready for production use.")
    print(f"  Working directory: {workdir}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
