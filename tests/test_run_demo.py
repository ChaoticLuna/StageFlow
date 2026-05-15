"""Tests for run_scoped_artifacts end-to-end demos."""
import json
import subprocess
import sys
import tempfile
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


class TestDemoExitAndBanner:
    def test_demo_exit_zero(self):
        result = _run_demo()
        assert result.returncode == 0, (
            f"Demo failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    def test_all_demos_passed_banner(self):
        result = _run_demo()
        assert "ALL DEMOS PASSED" in result.stdout


class TestInputEnvironments:
    def test_task_input_dirs_exist(self):
        assert (DEMO_DIR / "task_a").is_dir(), "task_a/ dir missing"
        assert (DEMO_DIR / "task_b").is_dir(), "task_b/ dir missing"

    def test_input_files_exist_and_are_distinct(self):
        a = (DEMO_DIR / "task_a" / "input.txt").read_text()
        b = (DEMO_DIR / "task_b" / "input.txt").read_text()
        assert len(a) > 0 and len(b) > 0
        assert a != b, "task_a and task_b input files must differ"

    def test_demo_reports_input_environments(self):
        result = _run_demo()
        assert "Task A input environment" in result.stdout
        assert "Task B input environment" in result.stdout
        assert "task_a/input.txt" in result.stdout
        assert "task_b/input.txt" in result.stdout


class TestRunIdentity:
    def test_different_run_ids(self):
        result = _run_demo()
        assert "Assertion 1: Different run IDs confirmed" in result.stdout

    def test_stale_review_intact_in_run_a(self):
        result = _run_demo()
        assert "Run A stale review intact" in result.stdout


class TestArtifactIsolation:
    def test_task_a_artifacts_do_not_unlock_task_b(self):
        result = _run_demo()
        assert "Assertion 2: Run A artifacts do NOT unlock run B transitions" in result.stdout

    def test_stale_review_does_not_block_run_b_done(self):
        result = _run_demo()
        assert "Assertion 3: Run A's stale changes_requested.md does NOT block" in result.stdout

    def test_own_changes_requested_blocks_done(self):
        result = _run_demo()
        assert "Assertion 4: Run B's own changes_requested.md blocks done gate" in result.stdout


class TestOutputCorrectness:
    def test_output_files_contain_correct_task_data(self):
        result = _run_demo()
        assert "Assertion 5: Output files contain correct task-specific data" in result.stdout

    def test_no_cross_contamination(self):
        result = _run_demo()
        assert "Cross-contamination check: NONE" in result.stdout

    def test_run_outputs_reference_correct_tasks(self):
        result = _run_demo()
        assert "Run A output references task_a: OK" in result.stdout
        assert "Run B output references task_b: OK" in result.stdout


class TestArtifactDirectories:
    def test_independent_dirs_confirmed(self):
        result = _run_demo()
        assert "Independent artifact directories confirmed" in result.stdout

    def test_run_a_b_dirs_different(self):
        result = _run_demo()
        assert "Run A (" in result.stdout
        assert "Run B (" in result.stdout
