"""End-to-end demo: run-scoped artifact isolation between sequential tasks.

Each task reads from its own input environment (task_a/ or task_b/) and writes
artifacts to a run-scoped directory. The demo proves that artifacts from run A
do not unlock, steer, or block transitions in run B.

Usage:
    python examples/run_scoped_artifacts/run_demo.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from stageflow.core.engine import StateMachine
from stageflow.core.registry import StageRegistry

EXAMPLES_DIR = Path(__file__).resolve().parent
TASK_A_DIR = EXAMPLES_DIR / "task_a"
TASK_B_DIR = EXAMPLES_DIR / "task_b"


def _write_config(base_path: Path) -> Path:
    config = base_path / "demo_config.yaml"
    config.write_text(
        """stages:
  - name: start
    tools: []
    meta:
      description: "Pick task and capture context"
  - name: build
    tools: [Write, Edit]
    meta:
      description: "Build task output from input files"
  - name: done
    tools: []
    meta:
      description: "Complete"

transitions:
  - from: start
    to: build
    conditions:
      - file_exists: "artifacts/runs/{{var.run_id}}/start/task_context.json"
  - from: build
    to: done
    conditions:
      - file_exists: "artifacts/runs/{{var.run_id}}/build/output.md"
      - file_not_exists: "artifacts/runs/{{var.run_id}}/review/changes_requested.md"
"""
    )
    return config


def run_demo() -> bool:
    """Run two sequential tasks and prove artifact isolation via run_id scoping."""
    print("=== Run-Scoped Artifact Isolation Demo ===\n")

    # Verify real input environments exist and are distinct
    assert TASK_A_DIR.exists(), f"task_a/ not found at {TASK_A_DIR}"
    assert TASK_B_DIR.exists(), f"task_b/ not found at {TASK_B_DIR}"
    input_a = (TASK_A_DIR / "input.txt").read_text()
    input_b = (TASK_B_DIR / "input.txt").read_text()
    assert input_a != input_b, "Task inputs must be distinct"
    print(f"Task A input environment: task_a/input.txt")
    print(f"  Content ({len(input_a)} bytes): {input_a.strip()}")
    print(f"Task B input environment: task_b/input.txt")
    print(f"  Content ({len(input_b)} bytes): {input_b.strip()}")
    print()

    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        artifacts_dir = base_path / "artifacts"
        config_path = _write_config(base_path)
        reg = StageRegistry(str(config_path))

        # ── Demo 1: Task A ──────────────────────────────────────────
        print("Demo 1: Processing task_a environment ...")
        sm1 = StateMachine(reg, base_path=str(base_path))
        sm1.initialize("start")
        run_id_1 = sm1.get_var("run_id")
        print(f"  Run ID: {run_id_1}")

        # Write task_a context referencing the real input environment
        ctx_dir = artifacts_dir / "runs" / run_id_1 / "start"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "task_context.json").write_text(
            f'{{"task": "task_a", "input_file": "task_a/input.txt", '
            f'"content": "{input_a.strip()}"}}'
        )

        # Advance start -> build
        ok, msgs = sm1.transition_to("build")
        assert ok, f"start -> build failed: {msgs}"
        print("  start -> build: OK")

        # Build output from task_a's real input file
        out_dir = artifacts_dir / "runs" / run_id_1 / "build"
        out_dir.mkdir(parents=True, exist_ok=True)
        processed_a = f"Processed task_a data: {input_a.strip()}"
        (out_dir / "output.md").write_text(f"# Task A Output\n\n{processed_a}")

        # Advance build -> done (passes: no review/changes_requested.md in run A)
        ok, msgs = sm1.transition_to("done")
        assert ok, f"build -> done failed: {msgs}"
        print("  build -> done: OK")

        # After done, create a stale changes_requested.md in run A
        # (simulates a post-done review that should never affect other runs)
        review_a = artifacts_dir / "runs" / run_id_1 / "review"
        review_a.mkdir(parents=True, exist_ok=True)
        (review_a / "changes_requested.md").write_text(
            "Changes requested for task_a — STALE (post-done)"
        )
        print(f"  Created stale review/changes_requested.md in run A dir")
        print(f"  Demo 1 complete. Run ID: {run_id_1}\n")

        # ── Demo 2: Task B ──────────────────────────────────────────
        print("Demo 2: Processing task_b environment ...")
        sm2 = StateMachine(reg, base_path=str(base_path))
        sm2.initialize("start")
        run_id_2 = sm2.get_var("run_id")
        print(f"  Run ID: {run_id_2}")

        # Assertion 1: different run_ids
        assert run_id_1 != run_id_2, "Run IDs should be different!"
        print("  [PASS] Assertion 1: Different run IDs confirmed")

        # Assertion 2: run A's artifacts do NOT unlock run B's transitions
        ok, msgs = sm2.transition_to("build")
        assert not ok, (
            "Run A artifacts must not satisfy run B conditions "
            f"(run_id in template is {run_id_2})"
        )
        print("  [PASS] Assertion 2: Run A artifacts do NOT unlock run B transitions")

        # Write task_b context (different environment, different content)
        ctx_dir_2 = artifacts_dir / "runs" / run_id_2 / "start"
        ctx_dir_2.mkdir(parents=True, exist_ok=True)
        (ctx_dir_2 / "task_context.json").write_text(
            f'{{"task": "task_b", "input_file": "task_b/input.txt", '
            f'"content": "{input_b.strip()}"}}'
        )

        ok, msgs = sm2.transition_to("build")
        assert ok, f"start -> build failed: {msgs}"
        print("  start -> build (with task_b context): OK")

        # Build output from task_b's real input file
        out_dir_2 = artifacts_dir / "runs" / run_id_2 / "build"
        out_dir_2.mkdir(parents=True, exist_ok=True)
        processed_b = f"Processed task_b data: {input_b.strip()}"
        (out_dir_2 / "output.md").write_text(f"# Task B Output\n\n{processed_b}")

        # Assertion 3: run A's stale changes_requested.md does NOT block run B
        # file_not_exists checks artifacts/runs/<run_id_2>/review/changes_requested.md
        # which is a different path than run A's review dir
        ok, msgs = sm2.transition_to("done")
        assert ok, (
            f"Run A's stale review must NOT block run B — "
            f"run_id scoping isolates the check! {msgs}"
        )
        print("  [PASS] Assertion 3: Run A's stale changes_requested.md "
              "does NOT block run B done gate")

        # Assertion 4: but run B's own changes_requested.md DOES block
        sm2.transition_to("build", force=True)  # rollback to test self-blocking

        review_b = artifacts_dir / "runs" / run_id_2 / "review"
        review_b.mkdir(parents=True, exist_ok=True)
        (review_b / "changes_requested.md").write_text(
            "Changes requested for task_b"
        )
        ok, msgs = sm2.transition_to("done")
        assert not ok, "Run B's own changes_requested.md MUST block done gate!"
        print("  [PASS] Assertion 4: Run B's own changes_requested.md "
              "blocks done gate")

        # Clean up run B's review file and advance
        (review_b / "changes_requested.md").unlink()
        review_b.rmdir()
        ok, msgs = sm2.transition_to("done")
        assert ok, f"build -> done failed after cleanup: {msgs}"
        print("  build -> done (clean): OK")

        # ── Assertion 5: Output files contain correct task-specific data ──
        output_a = (artifacts_dir / "runs" / run_id_1 / "build" / "output.md").read_text()
        output_b = (artifacts_dir / "runs" / run_id_2 / "build" / "output.md").read_text()
        assert "task_a" in output_a, f"Run A output must reference task_a"
        assert "task_b" in output_b, f"Run B output must reference task_b"
        assert input_a.strip() in output_a, "Run A output must embed task_a input content"
        assert input_b.strip() in output_b, "Run B output must embed task_b input content"
        assert input_a.strip() not in output_b, (
            "Run B output must NOT contain task_a input content"
        )
        print("  [PASS] Assertion 5: Output files contain correct task-specific data")
        print(f"    Run A output references task_a: OK")
        print(f"    Run B output references task_b: OK")
        print(f"    Cross-contamination check: NONE")

        # ── Final verification ──────────────────────────────────────
        dir_1 = artifacts_dir / "runs" / run_id_1
        dir_2 = artifacts_dir / "runs" / run_id_2
        assert dir_1.exists(), "Run A artifact dir should still exist"
        assert dir_2.exists(), "Run B artifact dir should exist"
        assert dir_1 != dir_2, "Artifact directories should be different"

        task_a_ctx = dir_1 / "start" / "task_context.json"
        task_b_ctx = dir_2 / "start" / "task_context.json"
        assert task_a_ctx.exists() and "task_a" in task_a_ctx.read_text()
        assert task_b_ctx.exists() and "task_b" in task_b_ctx.read_text()

        # Verify stale review from run A is still on disk (intact)
        stale_review = dir_1 / "review" / "changes_requested.md"
        assert stale_review.exists(), (
            "Run A's stale review file should remain for audit"
        )

        print(f"\n  [PASS] Independent artifact directories confirmed")
        print(f"    Run A ({run_id_1}): {dir_1}")
        print(f"    Run B ({run_id_2}): {dir_2}")
        print(f"    Run A stale review intact: {stale_review}")

    print("\n=== ALL DEMOS PASSED ===")
    return True


if __name__ == "__main__":
    success = run_demo()
    sys.exit(0 if success else 1)
