from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from stageflow.core.registry import StageRegistry
from stageflow.agent.orchestrator import WorkflowOrchestrator, TaskDef


@pytest.fixture
def orch_registry():
    reg = StageRegistry("__nonexistent__.yaml")
    reg.register_stage("pick", tools=["Read"])
    reg.register_stage("analyze", tools=["Read", "WebSearch"])
    reg.register_stage("implement", tools=["Edit", "Write"])
    reg.register_stage("done", tools=[])

    reg.register_transition("pick", "analyze", conditions=[{"always": True}])
    reg.register_transition("analyze", "implement", conditions=[{"always": True}])
    reg.register_transition("implement", "done", conditions=[{"always": True}])
    return reg


@pytest.fixture
def mock_llm():
    def _call(prompt: str) -> str:
        return f"LLM response({len(prompt)} chars)"
    return _call


@pytest.fixture
def orchestrator(orch_registry, mock_llm, tmp_path):
    return WorkflowOrchestrator(orch_registry, llm_call=mock_llm,
                               base_path=str(tmp_path))


class TestTaskRegistration:
    def test_add_single_task(self, orchestrator):
        orchestrator.add_task("t1", "Fix login bug")
        assert "t1" in orchestrator._tasks
        assert orchestrator._tasks["t1"].description == "Fix login bug"
        assert orchestrator._tasks["t1"].depends_on == []

    def test_add_task_with_dependencies(self, orchestrator):
        orchestrator.add_task("t1", "First task")
        orchestrator.add_task("t2", "Second task", depends_on=["t1"])
        assert orchestrator._tasks["t2"].depends_on == ["t1"]

    def test_add_tasks_batch(self, orchestrator):
        orchestrator.add_tasks([
            ("t1", "Task one", []),
            ("t2", "Task two", ["t1"]),
            ("t3", "Task three", ["t1"]),
        ])
        assert len(orchestrator._tasks) == 3

    def test_remove_task(self, orchestrator):
        orchestrator.add_task("t1", "Test")
        orchestrator.remove_task("t1")
        assert "t1" not in orchestrator._tasks


class TestGraphValidation:
    def test_valid_graph_passes(self, orchestrator):
        orchestrator.add_task("t1", "First")
        orchestrator.add_task("t2", "Second", depends_on=["t1"])
        ok, errors = orchestrator._validate_graph()
        assert ok is True
        assert errors == []

    def test_missing_dependency(self, orchestrator):
        orchestrator.add_task("t1", "Bad task", depends_on=["nonexistent"])
        ok, errors = orchestrator._validate_graph()
        assert ok is False
        assert any("unknown task" in e.lower() for e in errors)

    def test_cycle_detection(self, orchestrator):
        orchestrator.add_task("t1", "Task 1", depends_on=["t2"])
        orchestrator.add_task("t2", "Task 2", depends_on=["t1"])
        ok, errors = orchestrator._validate_graph()
        assert ok is False
        assert any("cycle" in e.lower() for e in errors)

    def test_self_cycle(self, orchestrator):
        orchestrator.add_task("t1", "Self-referential", depends_on=["t1"])
        ok, errors = orchestrator._validate_graph()
        assert ok is False

    def test_empty_graph(self, orchestrator):
        ok, errors = orchestrator._validate_graph()
        assert ok is True

    def test_three_node_cycle(self, orchestrator):
        orchestrator.add_task("t1", "First", depends_on=["t3"])
        orchestrator.add_task("t2", "Second", depends_on=["t1"])
        orchestrator.add_task("t3", "Third", depends_on=["t2"])
        ok, errors = orchestrator._validate_graph()
        assert ok is False
        assert any("cycle" in e.lower() for e in errors)


class TestReadyTasks:
    def test_all_ready_when_no_dependencies(self, orchestrator):
        orchestrator.add_tasks([
            ("t1", "A", []),
            ("t2", "B", []),
            ("t3", "C", []),
        ])
        ready = orchestrator._ready_tasks(set())
        assert set(ready) == {"t1", "t2", "t3"}

    def test_only_independent_ready(self, orchestrator):
        orchestrator.add_task("t1", "First")
        orchestrator.add_task("t2", "Second", depends_on=["t1"])
        ready = orchestrator._ready_tasks(set())
        assert ready == ["t1"]

    def test_dependent_ready_after_completion(self, orchestrator):
        orchestrator.add_task("t1", "First")
        orchestrator.add_task("t2", "Second", depends_on=["t1"])
        ready = orchestrator._ready_tasks({"t1"})
        assert "t2" in ready

    def test_multiple_dependencies(self, orchestrator):
        orchestrator.add_task("t1", "First")
        orchestrator.add_task("t2", "Second")
        orchestrator.add_task("t3", "Third", depends_on=["t1", "t2"])
        ready_before = orchestrator._ready_tasks(set())
        assert "t3" not in ready_before
        ready_after = orchestrator._ready_tasks({"t1", "t2"})
        assert "t3" in ready_after


class TestRun:
    def test_single_task_run(self, orchestrator):
        orchestrator.add_task("t1", "Single task")
        result = orchestrator.run()
        assert result["success"] is True
        assert "t1" in result["completed"]

    def test_sequential_tasks(self, orchestrator):
        orchestrator.add_task("t1", "First task")
        orchestrator.add_task("t2", "Second task", depends_on=["t1"])
        result = orchestrator.run()
        assert result["success"] is True
        assert result["completed"] == ["t1", "t2"]

    def test_parallel_independent_tasks(self, orchestrator):
        orchestrator.add_tasks([
            ("t1", "Task A", []),
            ("t2", "Task B", []),
            ("t3", "Task C", []),
        ])
        result = orchestrator.run()
        assert result["success"] is True
        assert len(result["completed"]) == 3

    def test_diamond_dependency(self, orchestrator):
        orchestrator.add_task("t1", "Root")
        orchestrator.add_task("t2", "Branch A", depends_on=["t1"])
        orchestrator.add_task("t3", "Branch B", depends_on=["t1"])
        orchestrator.add_task("t4", "Merge", depends_on=["t2", "t3"])
        result = orchestrator.run()
        assert result["success"] is True
        assert len(result["completed"]) == 4

    def test_chain_dependency(self, orchestrator):
        tasks = [("t1", "First", []), ("t2", "Second", ["t1"]),
                 ("t3", "Third", ["t2"]), ("t4", "Fourth", ["t3"])]
        orchestrator.add_tasks(tasks)
        result = orchestrator.run()
        assert result["success"] is True
        assert len(result["completed"]) == 4

    def test_invalid_graph_returns_errors(self, orchestrator):
        orchestrator.add_task("t1", "Bad", depends_on=["nonexistent"])
        result = orchestrator.run()
        assert result["success"] is False
        assert len(result["errors"]) > 0

    def test_cycle_returns_errors(self, orchestrator):
        orchestrator.add_task("t1", "A", depends_on=["t2"])
        orchestrator.add_task("t2", "B", depends_on=["t1"])
        result = orchestrator.run()
        assert result["success"] is False

    def test_results_contain_task_data(self, orchestrator):
        orchestrator.add_task("t1", "Test task")
        result = orchestrator.run()
        assert "t1" in result["results"]
        assert "final_stage" in result["results"]["t1"]

    def test_audit_trail_recorded(self, orchestrator):
        orchestrator.add_task("t1", "Auditable task")
        orchestrator.run()
        audit = orchestrator.get_audit_trail()
        assert len(audit) == 1
        assert audit[0]["task_id"] == "t1"


class TestSharedState:
    def test_set_and_get_shared(self, orchestrator):
        orchestrator.set_shared("key1", "value1")
        assert orchestrator.get_shared("key1") == "value1"

    def test_get_shared_default(self, orchestrator):
        assert orchestrator.get_shared("missing", "default") == "default"

    def test_get_all_shared(self, orchestrator):
        orchestrator.set_shared("a", 1)
        orchestrator.set_shared("b", 2)
        all_vars = orchestrator.get_all_shared()
        assert all_vars == {"a": 1, "b": 2}

    def test_reset_clears_shared(self, orchestrator):
        orchestrator.set_shared("x", "y")
        orchestrator.reset()
        assert orchestrator.get_all_shared() == {}


class TestSummary:
    def test_summary_after_run(self, orchestrator):
        orchestrator.add_task("t1", "Passing task")
        orchestrator.run()
        summary = orchestrator.get_summary()
        assert summary["total_tasks"] == 1
        assert summary["completed_tasks"] == 1
        assert summary["successful"] == 1
        assert summary["failed"] == 0

    def test_summary_empty(self, orchestrator):
        summary = orchestrator.get_summary()
        assert summary["total_tasks"] == 0
        assert summary["completed_tasks"] == 0

    def test_summary_with_mixed_results(self, orchestrator):
        # Only one valid task
        orchestrator.add_task("t1", "Works")
        orchestrator.run()
        summary = orchestrator.get_summary()
        assert "t1" in summary["tasks"]


class TestTaskDef:
    def test_repr(self):
        t = TaskDef("task-001", "Do something")
        assert "task-001" in repr(t)

    def test_repr_with_deps(self):
        t = TaskDef("t2", "Second", depends_on=["t1"])
        assert "t1" in repr(t)

    def test_default_depends(self):
        t = TaskDef("t3", "Third")
        assert t.depends_on == []
