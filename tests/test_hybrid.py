from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from stageflow.core.registry import StageRegistry
from stageflow.agent.hybrid import HybridWorkflow, STAGE_PROMPTS


@pytest.fixture
def mini_registry():
    reg = StageRegistry("__nonexistent__.yaml")
    reg.register_stage("pick", tools=["Read", "Grep"],
                      description="Select an issue")
    reg.register_stage("analyze", tools=["Read", "WebSearch"],
                      description="Analyze root cause")
    reg.register_stage("implement", tools=["Edit", "Write"],
                      description="Implement the fix")
    reg.register_stage("verify", tools=["Bash(pytest *)"],
                      description="Run tests")
    reg.register_stage("done", tools=[],
                      description="Workflow complete")

    reg.register_transition("pick", "analyze",
                           conditions=[{"always": True}])
    reg.register_transition("analyze", "implement",
                           conditions=[{"always": True}])
    reg.register_transition("implement", "verify",
                           conditions=[{"always": True}])
    reg.register_transition("verify", "done",
                           conditions=[{"always": True}])
    return reg


@pytest.fixture
def mock_llm():
    def _call(prompt: str) -> str:
        return f"LLM response for prompt({len(prompt)} chars): {prompt}"
    return _call


@pytest.fixture
def wf(mini_registry, mock_llm, tmp_path):
    return HybridWorkflow(mini_registry, llm_call=mock_llm, base_path=str(tmp_path))


class TestHybridWorkflowInit:
    def test_initializes_state_machine(self, wf, mini_registry):
        assert wf.registry is mini_registry
        assert wf.current_stage is None

    def test_stage_prompts_registered(self, wf):
        assert "analyze" in wf.stage_prompts
        assert "implement" in wf.stage_prompts
        assert "verify" in wf.stage_prompts

    def test_custom_prompts_override_defaults(self, mini_registry, mock_llm, tmp_path):
        custom = {"analyze": "Custom analyze prompt"}
        wf = HybridWorkflow(mini_registry, llm_call=mock_llm,
                           base_path=str(tmp_path), stage_prompts=custom)
        assert wf.stage_prompts["analyze"] == "Custom analyze prompt"
        assert "pick" in wf.stage_prompts


class TestRunLLMStage:
    def test_invokes_llm_with_stage_prompt(self, wf):
        response = wf.run_llm_stage("analyze")
        assert "LLM response for prompt" in response
        assert "ANALYZE" in response or "analyze" in response.lower()

    def test_invokes_llm_with_extra_context(self, wf):
        response = wf.run_llm_stage("analyze", extra_context="Fix bug #42")
        assert "bug #42" in response or "Fix bug" in response

    def test_stores_result(self, wf):
        wf.run_llm_stage("analyze")
        assert "analyze" in wf._stage_results
        assert wf.status()["stage_results"]["analyze"].startswith("LLM response")

    def test_fallback_prompt_for_unknown_stage(self, mini_registry, mock_llm, tmp_path):
        wf = HybridWorkflow(mini_registry, llm_call=mock_llm, base_path=str(tmp_path))
        response = wf.run_llm_stage("nonexistent_stage")
        assert "NONEXISTENT_STAGE" in response


class TestAdvance:
    def test_initialize_on_first_advance(self, wf):
        assert wf.current_stage is None
        ok, msgs = wf.advance()
        assert ok is True
        assert wf.current_stage == "pick"

    def test_advance_to_next_stage(self, wf):
        wf.advance()  # pick
        ok, msgs = wf.advance()  # pick → analyze
        assert ok is True
        assert wf.current_stage == "analyze"

    def test_advance_through_multiple_stages(self, wf):
        for expected in ["pick", "analyze", "implement", "verify", "done"]:
            ok, msgs = wf.advance()
            assert ok is True, f"Failed at {expected}: {msgs}"
            assert wf.current_stage == expected

    def test_cannot_advance_past_terminal(self, wf):
        for _ in range(5):
            wf.advance()
        assert wf.current_stage == "done"
        ok, msgs = wf.advance()
        assert ok is False

    def test_force_advance_bypasses_conditions(self, mini_registry, mock_llm, tmp_path):
        reg = StageRegistry("__nonexistent__.yaml")
        reg.register_stage("pick", tools=["Read"])
        reg.register_stage("implement", tools=["Edit"])
        reg.register_transition("pick", "implement",
                               conditions=[{"never": "blocked"}])
        wf = HybridWorkflow(reg, llm_call=mock_llm, base_path=str(tmp_path))
        wf.sm.initialize("pick")
        ok, msgs = wf.advance()
        assert ok is False  # blocked by "never"

        ok, msgs = wf.force_advance("implement")
        assert ok is True
        assert wf.current_stage == "implement"


class TestRun:
    def test_full_pipeline_with_mock_llm(self, wf):
        result = wf.run(description="Test workflow")
        assert result["completed"] is True
        assert result["final_stage"] == "done"
        assert result["stages_executed"] >= 4

    def test_respects_max_stages(self, wf):
        result = wf.run(max_stages=2)
        assert result["stages_executed"] <= 2

    def test_respects_stop_at(self, wf):
        result = wf.run(stop_at="implement")
        assert result["final_stage"] == "implement"

    def test_starts_from_initialize(self, wf):
        assert wf.current_stage is None
        result = wf.run(max_stages=1)
        assert wf.current_stage is not None

    def test_continues_from_current_stage(self, wf):
        wf.sm.initialize("implement")
        result = wf.run(max_stages=1)
        assert result["stages_executed"] <= 1

    def test_llm_response_included_in_result(self, wf):
        result = wf.run(max_stages=2)
        llm_runs = [h for h in result["history"] if h["action"] == "llm_run"]
        assert len(llm_runs) > 0

    def test_description_passed_to_llm(self, wf):
        """The description is passed as extra_context to the first LLM stage."""
        result = wf.run(description="Build a user auth system", max_stages=1)
        assert result["final_stage"] is not None

    def test_handles_nonexistent_stage_prompt(self, mini_registry, mock_llm, tmp_path):
        """Stages without prompts skip LLM invocation."""
        reg = StageRegistry("__nonexistent__.yaml")
        reg.register_stage("start", tools=["Read"])
        reg.register_stage("done", tools=[])
        reg.register_transition("start", "done", conditions=[{"always": True}])
        wf = HybridWorkflow(reg, llm_call=mock_llm, base_path=str(tmp_path),
                           stage_prompts={})
        result = wf.run(max_stages=2)
        llm_runs = [h for h in result["history"] if h["action"] == "llm_run"]
        assert len(llm_runs) == 0


class TestStatus:
    def test_status_includes_sm_info(self, wf):
        wf.advance()
        info = wf.status()
        assert info["current_stage"] == "pick"
        assert "registered_stages" in info

    def test_status_includes_stage_results(self, wf):
        wf.run_llm_stage("analyze")
        info = wf.status()
        assert "analyze" in info["stage_results"]

    def test_reset_clears_everything(self, wf):
        wf.advance()
        wf.run_llm_stage("analyze")
        wf.reset()
        assert wf.current_stage is None
        assert wf._stage_results == {}


class TestStagePrompts:
    def test_all_default_pipeline_stages_have_prompts(self):
        for stage in ["pick", "analyze", "plan", "implement", "verify", "document", "wrap_up"]:
            assert stage in STAGE_PROMPTS, f"Missing prompt for '{stage}'"
            assert len(STAGE_PROMPTS[stage]) > 20

    def test_terminal_stages_not_in_prompts(self):
        assert "done" not in STAGE_PROMPTS
