"""End-to-end demo: run-scoped artifact isolation between sequential tasks.

Usage:
    python examples/run_scoped_artifacts/run_demo.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from stageflow.core.engine import StateMachine
from stageflow.core.registry import StageRegistry


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

    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        artifacts_dir = base_path / "artifacts"
        config_path = _write_config(base_path)

        # ── Demo 1: Task A ──────────────────────────────────────────
        print("Demo 1: Running task_a ...")
        reg1 = StageRegistry(str(config_path))
        sm1 = StateMachine(reg1, base_path=str(base_path))
        sm1.initialize("start")
        run_id_1 = sm1.get_var("run_id")
        print(f"  Run ID: {run_id_1}")

        # Write task_a context
        ctx_dir = artifacts_dir / "runs" / run_id_1 / "start"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "task_context.json").write_text(
            '{"task": "task_a", "input_file": "data_a.txt"}'
        )

        # Advance to build
        ok, msgs = sm1.transition_to("build")
        assert ok, f"start -> build failed: {msgs}"
        print("  start -> build: OK")

        # Write task_a output
        out_dir = artifacts_dir / "runs" / run_id_1 / "build"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "output.md").write_text(
            "# Task A Output\n\nProcessed data_a.txt successfully."
        )

        # Advance to done
        ok, msgs = sm1.transition_to("done")
        assert ok, f"build -> done failed: {msgs}"
        print("  build -> done: OK")
        print(f"  Demo 1 complete.  Run ID: {run_id_1}\n")

        # ── Demo 2: Task B ──────────────────────────────────────────
        print("Demo 2: Running task_b ...")
        sm2 = StateMachine(reg1, base_path=str(base_path))
        sm2.initialize("start")  # fresh run_id
        run_id_2 = sm2.get_var("run_id")
        print(f"  Run ID: {run_id_2}")

        # Assertion 1: different run_ids
        assert run_id_1 != run_id_2, "Run IDs should be different!"
        print("  [PASS] Different run IDs confirmed")

        # Assertion 2: Demo 1's artifact does NOT unlock Demo 2's transition
        ok, msgs = sm2.transition_to("build")
        assert not ok, (
            "Should NOT transition — task A artifacts must not satisfy task B "
            f"conditions (run_id in template is {run_id_2})"
        )
        print("  [PASS] Task A artifacts do NOT unlock task B transitions")

        # Now write task_b context to satisfy the condition
        ctx_dir_2 = artifacts_dir / "runs" / run_id_2 / "start"
        ctx_dir_2.mkdir(parents=True, exist_ok=True)
        (ctx_dir_2 / "task_context.json").write_text(
            '{"task": "task_b", "input_file": "data_b.txt"}'
        )

        ok, msgs = sm2.transition_to("build")
        assert ok, f"start -> build failed after writing task_b context: {msgs}"
        print("  start -> build (with task_b context): OK")

        # Write task_b output
        out_dir_2 = artifacts_dir / "runs" / run_id_2 / "build"
        out_dir_2.mkdir(parents=True, exist_ok=True)
        (out_dir_2 / "output.md").write_text(
            "# Task B Output\n\nProcessed data_b.txt successfully."
        )

        # Assertion 3: stale changes_requested.md blocks transition
        review_dir = artifacts_dir / "runs" / run_id_2 / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "changes_requested.md").write_text(
            "Changes requested for task_b"
        )
        ok, msgs = sm2.transition_to("done")
        assert not ok, "Should NOT advance with changes_requested.md present!"
        print("  [PASS] Stale changes_requested.md blocks task B transition")

        # Remove the blocking file
        (review_dir / "changes_requested.md").unlink()
        review_dir.rmdir()

        ok, msgs = sm2.transition_to("done")
        assert ok, f"build -> done failed after removing changes_requested: {msgs}"
        print("  build -> done (after cleanup): OK")

        # ── Final verification ──────────────────────────────────────
        dir_1 = artifacts_dir / "runs" / run_id_1
        dir_2 = artifacts_dir / "runs" / run_id_2
        assert dir_1.exists(), "Run 1 artifact dir should still exist"
        assert dir_2.exists(), "Run 2 artifact dir should exist"
        assert dir_1 != dir_2, "Artifact directories should be different"

        task_a_file = dir_1 / "start" / "task_context.json"
        assert task_a_file.exists()
        assert "task_a" in task_a_file.read_text()

        task_b_file = dir_2 / "start" / "task_context.json"
        assert task_b_file.exists()
        assert "task_b" in task_b_file.read_text()

        print(f"\n  [PASS] Independent artifact directories confirmed")
        print(f"    Run 1 ({run_id_1}): {dir_1}")
        print(f"    Run 2 ({run_id_2}): {dir_2}")

    print("\n=== ALL DEMOS PASSED ===")
    return True


if __name__ == "__main__":
    success = run_demo()
    sys.exit(0 if success else 1)
