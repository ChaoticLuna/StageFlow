"""HybridWorkflow — alternates between LLM-powered stages and framework-validated
condition gates.

Usage:
    wf = HybridWorkflow(registry, llm_call=my_llm)
    wf.run("Fix the login bug in auth.py")  # runs full pipeline
    # Or step-by-step:
    wf.run_llm_stage("analyze", context={"issue": "bug description"})
    ok, msgs = wf.advance()
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine

STAGE_PROMPTS = {
    "pick": (
        "You are in the PICK stage. Select an issue/task from the backlog. "
        "Read the context, identify what needs to be done. "
        "Save your findings to {run_artifact_dir}/pick/issue_context.md."
    ),
    "analyze": (
        "You are in the ANALYZE stage. Analyze the root cause, impact scope, "
        "and relevant code paths. Write a thorough analysis to {run_artifact_dir}/analyze/findings.md "
        "with sections: ## Root Cause, ## Impact, ## Affected Files."
    ),
    "plan": (
        "You are in the PLAN stage. Design a solution approach, task breakdown, "
        "and rollback strategy. Write the plan to {run_artifact_dir}/plan/task_plan.md "
        "with sections: ## Task Plan, ## Implementation Notes, ## Rollback Strategy."
    ),
    "implement": (
        "You are in the IMPLEMENT stage. Execute the code changes according to "
        "the task plan. Commit your changes with descriptive messages."
    ),
    "verify": (
        "You are in the VERIFY stage. Run tests, collect evidence, and record results "
        "to {run_artifact_dir}/verify/test_results.md. If tests fail, go back to implement."
    ),
    "document": (
        "You are in the DOCUMENT stage. Write changelog entries to "
        "{run_artifact_dir}/document/changelog.md and update any relevant docs."
    ),
    "wrap_up": (
        "You are in the WRAP_UP stage. Clean up branches, update status, archive artifacts. "
        "Mark the task as complete."
    ),
}

TERMINAL_STAGES = {"done"}


class HybridWorkflow:
    """Orchestrates a workflow that alternates between LLM reasoning stages
    and framework-validated condition-gated transitions.

    LLM stages produce artifacts (analysis, plans, code).
    Framework transitions validate those artifacts with conditions.
    """

    def __init__(
        self,
        registry: StageRegistry,
        llm_call: Callable[[str], str],
        base_path: str = ".",
        stage_prompts: Optional[dict] = None,
    ):
        self.registry = registry
        self.llm_call = llm_call
        self.base_path = Path(base_path).resolve()
        self.sm = StateMachine(registry, str(self.base_path))
        self.stage_prompts = {**STAGE_PROMPTS, **(stage_prompts or {})}
        self._stage_results: dict[str, str] = {}

    # ── Pipeline Execution ────────────────────────────────────────────

    def run_llm_stage(self, stage_name: str, extra_context: str = "") -> str:
        """Invoke the LLM for a stage that requires AI reasoning.

        Injects the current run_id so the agent writes to the correct
        run-scoped artifact directory.
        Returns the LLM's response text.
        """
        prompt = self.stage_prompts.get(
            stage_name,
            f"You are in the {stage_name.upper()} stage. "
            f"Complete the work for this stage.",
        )
        if extra_context:
            prompt = f"{prompt}\n\n## Additional Context\n{extra_context}"

        run_id = self.sm.get_var("run_id") or "unknown-run"
        artifact_dir = f"artifacts/runs/{run_id}"
        prompt = prompt.replace("{run_artifact_dir}", artifact_dir)

        response = self.llm_call(prompt)
        self._stage_results[stage_name] = response
        return response

    def advance(self) -> tuple[bool, list[str]]:
        """Check conditions on available transitions and advance if any pass.

        Returns (advanced, messages). Tries each available transition in order;
        advances on the first one whose conditions pass.
        """
        current = self.sm.current_stage
        if current is None:
            first = self._find_start_stage()
            return self.sm.initialize(first)

        available = self.registry.get_next_stages(current)
        if not available:
            return False, [f"No transitions available from '{current}'"]

        for target in available:
            ok, msgs = self.sm.can_transition_to(target)
            if ok:
                self.sm.transition_to(target)
                return True, msgs

        return False, [f"No transition conditions passed from '{current}'"]

    def force_advance(self, target: str) -> tuple[bool, list[str]]:
        """Advance to a specific stage, bypassing condition checks."""
        return self.sm.force_transition_to(target)

    def run(
        self,
        description: str = "",
        max_stages: Optional[int] = None,
        stop_at: Optional[str] = None,
    ) -> dict:
        """Run the full pipeline: LLM stages with condition-gated advances.

        For each stage:
          1. If it's an LLM stage (has a prompt), invoke the LLM
          2. Try to advance to the next stage via condition checks
          3. Repeat until terminal stage or max_stages reached

        Returns execution summary dict.
        """
        current = self.sm.current_stage
        if current is None:
            self.sm.initialize(self._find_start_stage())

        stage_count = 0
        history: list[dict] = []

        while True:
            if max_stages is not None and stage_count >= max_stages:
                break

            current = self.sm.current_stage
            if current is None:
                break
            if current in TERMINAL_STAGES:
                break
            if stop_at and current == stop_at:
                break

            # Run LLM for this stage if applicable
            if current in self.stage_prompts:
                try:
                    response = self.run_llm_stage(current, description)
                    history.append({
                        "stage": current,
                        "action": "llm_run",
                        "response_length": len(response),
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as e:
                    history.append({
                        "stage": current,
                        "action": "llm_error",
                        "error": str(e),
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                    break

            # Try to advance
            ok, msgs = self.advance()
            history.append({
                "stage": current,
                "action": "advance",
                "success": ok,
                "messages": msgs[:5],
                "at": datetime.now(timezone.utc).isoformat(),
            })

            if not ok:
                break

            stage_count += 1

        return {
            "completed": self.sm.current_stage in TERMINAL_STAGES,
            "final_stage": self.sm.current_stage,
            "stages_executed": stage_count,
            "history": history,
        }

    def _find_start_stage(self) -> str:
        """Find the first stage (root node) — the one with no incoming transitions."""
        all_targets = {t.to_stage for t in self.registry.all_transitions}
        for name in self.registry.stage_names:
            if name not in all_targets:
                return name
        return self.registry.stage_names[0] if self.registry.stage_names else "pick"

    # ── Status ────────────────────────────────────────────────────────

    def status(self) -> dict:
        sm_status = self.sm.status()
        sm_status["stage_results"] = dict(self._stage_results)
        return sm_status

    def reset(self):
        self.sm.reset()
        self._stage_results.clear()

    @property
    def current_stage(self) -> Optional[str]:
        return self.sm.current_stage
