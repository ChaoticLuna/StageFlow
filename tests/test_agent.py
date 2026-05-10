from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from stageflow.agent.runner import AgentRunner

FIX_PLAN_CONTENT = """# Test Fix Plan

## Phase 1

- [x] **task-001**: First completed task
- [ ] **task-002**: Second pending task
- [ ] **task-003**: Third pending task
- [!] **task-004**: Blocked task

## Phase 2

- [ ] **task-005**: Fifth task in phase 2
"""


@pytest.fixture
def plan_file(tmp_path):
    p = tmp_path / "fix_plan.md"
    p.write_text(FIX_PLAN_CONTENT, encoding="utf-8")
    return p


@pytest.fixture
def runner(plan_file, tmp_path):
    return AgentRunner(str(plan_file), base_path=str(tmp_path))


class TestParseTasks:
    def test_parses_all_tasks(self, runner):
        tasks = runner.parse_tasks()
        assert len(tasks) == 5
        ids = [t["id"] for t in tasks]
        assert ids == ["task-001", "task-002", "task-003", "task-004", "task-005"]

    def test_parses_completed_status(self, runner):
        tasks = runner.parse_tasks()
        statuses = {t["id"]: t["completed"] for t in tasks}
        assert statuses["task-001"] is True
        assert statuses["task-002"] is False
        assert statuses["task-003"] is False

    def test_parses_descriptions(self, runner):
        tasks = runner.parse_tasks()
        descs = {t["id"]: t["description"] for t in tasks}
        assert descs["task-001"] == "First completed task"
        assert descs["task-002"] == "Second pending task"

    def test_empty_file_returns_empty_list(self, tmp_path):
        p = tmp_path / "empty.md"
        p.write_text("", encoding="utf-8")
        runner = AgentRunner(str(p), base_path=str(tmp_path))
        assert runner.parse_tasks() == []

    def test_no_checkboxes_returns_empty_list(self, tmp_path):
        p = tmp_path / "no_tasks.md"
        p.write_text("# Just a header\nSome text\n- not a checkbox\n", encoding="utf-8")
        runner = AgentRunner(str(p), base_path=str(tmp_path))
        assert runner.parse_tasks() == []

    def test_file_not_found_raises(self, tmp_path):
        runner = AgentRunner(str(tmp_path / "nonexistent.md"), base_path=str(tmp_path))
        with pytest.raises(FileNotFoundError):
            runner.parse_tasks()


class TestGetNextTask:
    def test_returns_first_incomplete(self, runner):
        task = runner.get_next_task()
        assert task is not None
        assert task["id"] == "task-002"

    def test_returns_none_when_all_done(self, tmp_path):
        p = tmp_path / "all_done.md"
        p.write_text("- [x] **task-001**: Done\n- [x] **task-002**: Also done\n", encoding="utf-8")
        runner = AgentRunner(str(p), base_path=str(tmp_path))
        assert runner.get_next_task() is None

    def test_returns_none_when_no_tasks(self, tmp_path):
        p = tmp_path / "empty.md"
        p.write_text("# Nothing here\n", encoding="utf-8")
        runner = AgentRunner(str(p), base_path=str(tmp_path))
        assert runner.get_next_task() is None


class TestTaskLifecycle:
    def test_start_task_sets_current(self, runner):
        assert runner.start_task("task-002") is True
        assert runner.current_task == "task-002"
        assert runner.current_stage == "pick"

    def test_start_already_completed_task_fails(self, runner):
        assert runner.start_task("task-001") is False

    def test_start_nonexistent_task_fails(self, runner):
        assert runner.start_task("task-999") is False

    def test_advance_stage_moves_forward(self, runner):
        runner.start_task("task-002")
        ok, msgs = runner.advance_stage("analyze")
        assert ok is True
        assert runner.current_stage == "analyze"

    def test_advance_stage_unknown_stage_fails(self, runner):
        runner.start_task("task-002")
        ok, msgs = runner.advance_stage("nonexistent")
        assert ok is False

    def test_advance_stage_without_active_task_fails(self, runner):
        ok, msgs = runner.advance_stage("analyze")
        assert ok is False
        assert any("No active task" in m for m in msgs)

    def test_complete_task_updates_plan_file(self, runner, plan_file):
        runner.start_task("task-002")
        runner.advance_stage("analyze")
        assert runner.complete_task("task-002") is True

        content = plan_file.read_text(encoding="utf-8")
        assert "- [x] **task-002**" in content
        assert "- [ ] **task-003**" in content

    def test_complete_task_clears_current(self, runner):
        runner.start_task("task-002")
        runner.complete_task("task-002")
        assert runner.current_task is None
        assert runner.current_stage is None

    def test_complete_already_completed_task(self, runner):
        """Should return False because mark_task_completed_in_file finds no [ ] to replace."""
        result = runner.complete_task("task-001")
        assert result is False

    def test_fail_task_records_reason(self, runner):
        runner.fail_task("task-003", "Blocked by external dependency")
        status = runner.get_task_status("task-003")
        assert status["status"] == "blocked"
        assert "external dependency" in status["failure_reason"]

    def test_fail_task_on_completed_task(self, runner):
        runner.fail_task("task-001", "Already done but failed retroactively")
        status = runner.get_task_status("task-001")
        assert status["status"] == "blocked"


class TestMarkTaskInFile:
    def test_mark_completed_updates_checkbox(self, runner, plan_file):
        assert runner.mark_task_completed_in_file("task-002") is True
        content = plan_file.read_text(encoding="utf-8")
        assert "- [x] **task-002**" in content

    def test_mark_completed_non_existent(self, runner):
        assert runner.mark_task_completed_in_file("task-999") is False

    def test_mark_blocked_updates_checkbox(self, runner, plan_file):
        assert runner.mark_task_blocked_in_file("task-002") is True
        content = plan_file.read_text(encoding="utf-8")
        assert "- [!] **task-002**" in content


class TestProgressPersistence:
    def test_progress_saved_to_disk(self, runner, tmp_path):
        runner.start_task("task-002")
        progress_path = tmp_path / ".claude" / "agent_progress.json"
        assert progress_path.exists()
        data = json.loads(progress_path.read_text(encoding="utf-8"))
        assert data["current_task"] == "task-002"
        assert data["current_stage"] == "pick"

    def test_progress_loaded_on_reinit(self, runner, plan_file, tmp_path):
        runner.start_task("task-002")
        runner.advance_stage("plan")

        runner2 = AgentRunner(str(plan_file), base_path=str(tmp_path))
        assert runner2.current_task == "task-002"
        assert runner2.current_stage == "plan"

    def test_reset_clears_progress(self, runner, tmp_path):
        runner.start_task("task-002")
        runner.reset()
        assert runner.current_task is None
        assert runner.current_stage is None
        progress_path = tmp_path / ".claude" / "agent_progress.json"
        assert not progress_path.exists()


class TestStatus:
    def test_status_shows_summary(self, runner):
        info = runner.status()
        assert info["total_tasks"] == 5
        assert info["completed_tasks"] == 1
        assert info["remaining_tasks"] == 4

    def test_status_shows_all_tasks(self, runner):
        info = runner.status()
        assert "task-001" in info["tasks"]
        assert info["tasks"]["task-001"] is True
        assert info["tasks"]["task-002"] is False

    def test_status_includes_history(self, runner):
        runner.start_task("task-002")
        runner.advance_stage("analyze")
        info = runner.status()
        assert len(info["history"]) == 2

    def test_get_task_status_returns_merged_data(self, runner):
        runner.start_task("task-002")
        status = runner.get_task_status("task-002")
        assert status["id"] == "task-002"
        assert status["status"] == "in_progress"
        assert status["completed"] is False

    def test_get_task_status_nonexistent(self, runner):
        assert runner.get_task_status("task-999") is None


class TestPipeline:
    def test_full_pipeline_walkthrough(self, runner, plan_file):
        """Simulate a complete task workflow through all pipeline stages."""
        task = runner.get_next_task()
        assert task["id"] == "task-002"

        assert runner.start_task(task["id"]) is True
        assert runner.current_stage == "pick"

        for stage in ["analyze", "plan", "implement", "verify", "wrap_up", "done"]:
            ok, msgs = runner.advance_stage(stage)
            assert ok is True, f"Failed to advance to {stage}: {msgs}"
            assert runner.current_stage == stage

        assert runner.complete_task(task["id"]) is True
        assert runner.current_task is None

        content = plan_file.read_text(encoding="utf-8")
        assert "- [x] **task-002**" in content

    def test_pipeline_resets_between_tasks(self, runner, plan_file):
        """Complete task-002, then start task-003 from fresh pipeline."""
        runner.start_task("task-002")
        runner.advance_stage("analyze")
        runner.advance_stage("done")
        runner.complete_task("task-002")

        next_task = runner.get_next_task()
        assert next_task["id"] == "task-003"

        assert runner.start_task("task-003") is True
        assert runner.current_stage == "pick"


class TestCommitCallback:
    def test_commit_callback_called_on_complete(self, tmp_path, plan_file):
        calls = []
        def callback(task_id):
            calls.append(task_id)

        runner = AgentRunner(str(plan_file), base_path=str(tmp_path),
                           commit_callback=callback)
        runner.start_task("task-002")
        runner.complete_task("task-002")
        assert calls == ["task-002"]

    def test_commit_callback_not_called_when_complete_fails(self, tmp_path, plan_file):
        calls = []
        def callback(task_id):
            calls.append(task_id)

        runner = AgentRunner(str(plan_file), base_path=str(tmp_path),
                           commit_callback=callback)
        runner.complete_task("task-999")
        assert calls == []
