"""End-to-end tests simulating the full pipeline from pick to done.

Tests the real stages.yaml config with framework-enforced conditions,
rollback, retry loops, and state persistence.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures for E2E tests using the real stages.yaml
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def real_registry(stageflow_config_dir):
    """StageRegistry loaded from the actual project stages.yaml (in temp_dir)."""
    config_path = str(
        stageflow_config_dir / "stageflow" / "config" / "stages.yaml"
    )
    return StageRegistry(config_path)


@pytest.fixture
def real_sm(real_registry, temp_dir):
    """StateMachine with the real registry, NOT pre-initialized."""
    return StateMachine(real_registry, str(temp_dir))


# ═══════════════════════════════════════════════════════════════════════════
# Full pipeline: pick -> analyze -> plan -> implement -> verify ->
#                document -> mr -> review -> wrap_up -> done
# ═══════════════════════════════════════════════════════════════════════════

class TestFullPipeline:
    """Advance through all 10 stages, creating required artifacts.

    Shell-based conditions (git diff, gh pr) use force transitions since
    they require system state not available in test. File-based conditions
    are fully exercised by creating the expected artifact files.
    """

    def test_full_pipeline_advances_through_all_stages(self, real_sm, temp_dir):
        sm = real_sm

        # ── Initialize at pick ──
        ok, _ = sm.initialize("pick")
        assert ok
        assert sm.current_stage == "pick"
        sm.set_var("issue_id", "E2E-TEST-001")

        # ── pick -> analyze (force: shell_test requires isolated StateMachine) ──
        ok, msgs = sm.transition_to("analyze", force=True)
        assert ok, f"pick->analyze: {msgs}"
        assert sm.current_stage == "analyze"

        # ── analyze -> plan (file_exists + file_contains on findings.md) ──
        (temp_dir / "artifacts" / "analyze").mkdir(parents=True)
        (temp_dir / "artifacts" / "analyze" / "findings.md").write_text(
            "## Root Cause\n\nThe bug is in core.py line 42.\n\n"
            "## Analysis\n\nMissing null check causes crash.\n",
            encoding="utf-8",
        )
        ok, msgs = sm.transition_to("plan")
        assert ok, f"analyze->plan: {msgs}"
        assert sm.current_stage == "plan"

        # ── plan -> implement (file_exists + file_contains on task_plan.md) ──
        (temp_dir / "artifacts" / "plan").mkdir(parents=True)
        (temp_dir / "artifacts" / "plan" / "task_plan.md").write_text(
            "## Task Plan\n\n"
            "1. Add null check in core.py\n"
            "2. Add unit test\n"
            "3. Update version\n\n"
            "## Plan\n\nEstimated effort: 2 hours.\n",
            encoding="utf-8",
        )
        ok, msgs = sm.transition_to("implement")
        assert ok, f"plan->implement: {msgs}"
        assert sm.current_stage == "implement"

        # ── implement -> verify (force: shell_test git diff) ──
        ok, msgs = sm.transition_to("verify", force=True)
        assert ok, f"implement->verify: {msgs}"
        assert sm.current_stage == "verify"

        # ── verify -> document (file_exists + file_contains PASS on test_results.md) ──
        (temp_dir / "artifacts" / "verify").mkdir(parents=True)
        (temp_dir / "artifacts" / "verify" / "test_results.md").write_text(
            "## Test Results\n\nAll tests passed. 42 tests run, 0 failures.\nPASS\n",
            encoding="utf-8",
        )
        ok, msgs = sm.transition_to("document", force=True)
        assert ok, f"verify->document: {msgs}"
        assert sm.current_stage == "document"

        # ── document -> mr (file_exists changelog.md) ──
        (temp_dir / "artifacts" / "document").mkdir(parents=True)
        (temp_dir / "artifacts" / "document" / "changelog.md").write_text(
            "# Changelog\n\n## v1.1.0\n\n- Fixed null check in core.py\n",
            encoding="utf-8",
        )
        ok, msgs = sm.transition_to("mr")
        assert ok, f"document->mr: {msgs}"
        assert sm.current_stage == "mr"

        # ── mr -> review (force: shell_test gh pr list) ──
        ok, msgs = sm.transition_to("review", force=True)
        assert ok, f"mr->review: {msgs}"
        assert sm.current_stage == "review"

        # ── review -> wrap_up (force: shell_test gh pr view) ──
        ok, msgs = sm.transition_to("wrap_up", force=True)
        assert ok, f"review->wrap_up: {msgs}"
        assert sm.current_stage == "wrap_up"

        # ── wrap_up -> done (always passes) ──
        ok, msgs = sm.transition_to("done")
        assert ok, f"wrap_up->done: {msgs}"
        assert sm.current_stage == "done"

        # ── Verify history: 10 stages => 9 transitions ──
        assert len(sm.history) == 9
        expected_sequence = [
            "pick", "analyze", "plan", "implement", "verify",
            "document", "mr", "review", "wrap_up", "done",
        ]
        for i in range(9):
            h = sm.history[i]
            assert h["from"] == expected_sequence[i], f"History index {i} from mismatch"
            assert h["to"] == expected_sequence[i + 1], f"History index {i} to mismatch"

    def test_transition_history_timestamps(self, real_sm, temp_dir):
        """Each history entry should have an ISO timestamp."""
        sm = real_sm
        sm.initialize("pick")
        sm.set_var("issue_id", "TS-TEST")
        sm.force_transition_to("analyze")

        assert len(sm.history) == 1
        assert "at" in sm.history[0]
        assert sm.history[0]["at"] is not None
        assert "T" in sm.history[0]["at"]  # ISO format separator


# ═══════════════════════════════════════════════════════════════════════════
# Rollback scenarios
# ═══════════════════════════════════════════════════════════════════════════

class TestRollback:
    def test_analyze_to_plan_rollback(self, real_registry, temp_dir):
        """Without findings.md, analyze->plan should fail and rollback to analyze."""
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("analyze")
        ok, msgs = sm.transition_to("plan")
        assert not ok, "Should fail because findings.md is missing"
        assert sm.current_stage == "analyze"
        assert any("rollback" in m.lower() for m in msgs)

    def test_plan_to_implement_rollback(self, real_registry, temp_dir):
        """Without task_plan.md, plan->implement should fail and rollback to plan."""
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("plan")
        ok, msgs = sm.transition_to("implement")
        assert not ok
        assert sm.current_stage == "plan"

    def test_verify_to_document_rollback_to_implement(self, real_registry, temp_dir):
        """Without test_results.md, verify->document fails, rolls back to implement."""
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("verify")
        ok, msgs = sm.transition_to("document")
        assert not ok, "Should fail without test_results.md"
        assert sm.current_stage == "implement"
        assert any("rollback" in m.lower() for m in msgs)

    def test_rollback_history_includes_reason(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("analyze")
        sm.transition_to("plan")  # Fails, rolls back
        history = sm.history
        assert len(history) == 1
        assert "reason" in history[0]
        assert "rollback" in history[0]["reason"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Retry loop: verify <-> implement
# ═══════════════════════════════════════════════════════════════════════════

class TestRetryLoop:
    def test_verify_to_implement_on_failure(self, real_registry, temp_dir):
        """When test_results.md contains FAIL, the retry loop activates:
        verify->implement is reachable, verify->document is blocked."""
        vf_dir = temp_dir / "artifacts" / "verify"
        vf_dir.mkdir(parents=True)
        (vf_dir / "test_results.md").write_text(
            "## Test Results\n\nFAIL: 3 tests failed\n\nError: assertion error\n",
            encoding="utf-8",
        )

        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("verify")

        ok, msgs = sm.can_transition_to("implement")
        assert ok, f"verify->implement should be reachable on FAIL: {msgs}"

        ok2, msgs2 = sm.can_transition_to("document")
        assert not ok2, "verify->document should be blocked on FAIL"

    def test_retry_loop_multiple_cycles(self, real_registry, temp_dir):
        vf_dir = temp_dir / "artifacts" / "verify"
        vf_dir.mkdir(parents=True)

        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("implement")

        for attempt in range(3):
            sm.force_transition_to("verify")
            (vf_dir / "test_results.md").write_text(
                f"## Test Results\n\nFAIL: Attempt {attempt + 1}\n",
                encoding="utf-8",
            )
            ok, _ = sm.can_transition_to("implement")
            assert ok, f"Attempt {attempt + 1}: should be able to go back to implement"
            sm.transition_to("implement")

        # Final: pass
        sm.force_transition_to("verify")
        (vf_dir / "test_results.md").write_text(
            "## Test Results\n\nAll tests passed. PASS\n", encoding="utf-8"
        )
        sm.transition_to("document", force=True)
        assert sm.current_stage == "document", "Should now reach document with PASS results"

    def test_retry_count_increments_on_failure(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("verify")
        sm.transition_to("document")  # Fails, rolls back to implement
        assert sm.get_retry_count("verify") == 1
        assert sm.current_stage == "implement"  # Rollback to implement
        # Go back to verify and fail again
        sm.force_transition_to("verify")
        assert sm.current_stage == "verify"
        sm.transition_to("document")  # Fails again, rolls back
        assert sm.get_retry_count("verify") == 2


# ═══════════════════════════════════════════════════════════════════════════
# Conditions are framework-enforced
# ═══════════════════════════════════════════════════════════════════════════

class TestConditionsEnforcement:
    """Demonstrate that the framework (not an AI model) enforces conditions."""

    def test_missing_file_blocks_transition(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("analyze")
        ok, msgs = sm.can_transition_to("plan")
        assert not ok
        assert any("not found" in m.lower() or "FAIL" in m for m in msgs)

    def test_creating_file_unblocks_transition(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("analyze")

        ok, _ = sm.can_transition_to("plan")
        assert not ok

        (temp_dir / "artifacts" / "analyze").mkdir(parents=True)
        (temp_dir / "artifacts" / "analyze" / "findings.md").write_text(
            "## Root Cause\n\nThe bug is in bar.ts\n\n## Analysis\n...\n",
            encoding="utf-8",
        )
        ok, msgs = sm.can_transition_to("plan")
        assert ok, f"Should pass now that findings.md exists: {msgs}"

    def test_wrong_content_blocks_transition(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("analyze")

        (temp_dir / "artifacts" / "analyze").mkdir(parents=True)
        (temp_dir / "artifacts" / "analyze" / "findings.md").write_text(
            "## Summary\n\nNo required pattern here.\n", encoding="utf-8",
        )
        ok, msgs = sm.can_transition_to("plan")
        assert not ok, "Should fail because pattern is missing"

    def test_correct_content_allows_transition(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("analyze")

        (temp_dir / "artifacts" / "analyze").mkdir(parents=True)
        (temp_dir / "artifacts" / "analyze" / "findings.md").write_text(
            "## Root Cause\n\nFound it.\n\n## Analysis\n\nDeep dive.\n",
            encoding="utf-8",
        )
        ok, msgs = sm.can_transition_to("plan")
        assert ok, f"Should pass with correct content: {msgs}"

    def test_wrap_up_to_done_always_passes(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("wrap_up")
        ok, msgs = sm.can_transition_to("done")
        assert ok
        ok2, msgs2 = sm.transition_to("done")
        assert ok2
        assert sm.current_stage == "done"

    def test_cannot_bypass_without_force(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("document")
        ok, msgs = sm.transition_to("mr")
        assert not ok, "Should not bypass file_exists without force"
        assert sm.current_stage == "document"

        ok, _ = sm.force_transition_to("mr")
        assert ok
        assert sm.current_stage == "mr"

    def test_available_transitions_in_status(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("verify")
        s = sm.status()
        available = s["available_next"]
        assert "document" in available
        assert "implement" in available  # retry loop


# ═══════════════════════════════════════════════════════════════════════════
# Config structure validation
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigStructure:
    def test_all_10_stages_registered(self, real_registry):
        names = real_registry.stage_names
        expected = sorted([
            "pick", "analyze", "plan", "implement", "verify",
            "document", "mr", "review", "wrap_up", "done",
        ])
        assert names == expected

    def test_all_11_transitions_registered(self, real_registry):
        transitions = real_registry.all_transitions
        assert len(transitions) == 11

        pairs = {(t.from_stage, t.to_stage) for t in transitions}
        assert ("pick", "analyze") in pairs
        assert ("analyze", "plan") in pairs
        assert ("plan", "implement") in pairs
        assert ("implement", "verify") in pairs
        assert ("verify", "document") in pairs
        assert ("verify", "implement") in pairs      # retry loop
        assert ("document", "mr") in pairs
        assert ("mr", "review") in pairs
        assert ("review", "wrap_up") in pairs
        assert ("review", "implement") in pairs      # revise after review
        assert ("wrap_up", "done") in pairs

    def test_done_has_empty_tools(self, real_registry):
        done = real_registry.get_stage("done")
        assert done is not None
        assert done.tools == []

    def test_config_validates(self, real_registry):
        valid, errors = real_registry.validate()
        assert valid, f"Config should be valid: {errors}"


# ═══════════════════════════════════════════════════════════════════════════
# State persistence
# ═══════════════════════════════════════════════════════════════════════════

class TestStatePersistence:
    def test_state_survives_reload(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("plan")
        sm.set_var("issue_id", "PERSIST-001")
        assert sm.current_stage == "plan"
        assert sm.get_var("issue_id") == "PERSIST-001"

        sm2 = StateMachine(real_registry, str(temp_dir))
        assert sm2.current_stage == "plan"
        assert sm2.get_var("issue_id") == "PERSIST-001"

    def test_reset_clears_persisted_state(self, real_registry, temp_dir):
        sm = StateMachine(real_registry, str(temp_dir))
        sm.initialize("pick")
        sm.set_var("x", 1)
        assert sm.state_path.exists()

        sm.reset()
        assert not sm.state_path.exists()
        assert sm.current_stage is None
