"""Tests for run_scoped_artifacts end-to-end demos."""
import subprocess
import sys
from pathlib import Path


DEMO_DIR = Path(__file__).resolve().parent.parent / "examples" / "run_scoped_artifacts"
DEMO_PATH = DEMO_DIR / "run_demo.py"


def _run_demo():
    result = subprocess.run(
        [sys.executable, str(DEMO_PATH)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result


def test_run_demo_exit_code():
    """Demo exits 0 and prints success banner."""
    result = _run_demo()
    assert result.returncode == 0, (
        f"Demo failed (exit {result.returncode}):\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "ALL DEMOS PASSED" in result.stdout


def test_different_run_ids():
    """Demo confirms the two runs have different run_id values."""
    result = _run_demo()
    assert "Different run IDs confirmed" in result.stdout


def test_task_a_artifacts_do_not_unlock_task_b():
    """Demo proves stale task A artifacts cannot drive task B transitions."""
    result = _run_demo()
    assert "Task A artifacts do NOT unlock task B transitions" in result.stdout


def test_changes_requested_blocks_transition():
    """Demo verifies stale review/changes_requested.md blocks the done gate."""
    result = _run_demo()
    assert "Stale changes_requested.md blocks" in result.stdout


def test_independent_artifact_directories():
    """Demo confirms each run writes to its own artifact directory."""
    result = _run_demo()
    assert "Independent artifact directories confirmed" in result.stdout
