"""Comprehensive tests for the StateMachine engine."""

import json
import pytest
from pathlib import Path

from stageflow.core.engine import StateMachine
from stageflow.core.registry import StageRegistry


# ═══════════════════════════════════════════════════════════════════════════
# TestInit
# ═══════════════════════════════════════════════════════════════════════════

class TestInit:
    def test_init_with_valid_stage(self, state_machine):
        """init with valid stage, current_stage matches."""
        ok, msgs = state_machine.initialize("start")
        assert ok
        assert state_machine.current_stage == "start"
        assert "Initialized at stage" in msgs[0]

    def test_init_with_unknown_stage(self, state_machine):
        """init with unknown stage returns error."""
        ok, msgs = state_machine.initialize("nonexistent")
        assert not ok
        assert state_machine.current_stage is None
        assert "Unknown stage" in msgs[0]

    def test_init_resets_retry_iteration_history(self, state_machine):
        """init resets retry/iteration/history."""
        # Artificially dirty the state
        state_machine.initialize("start")
        state_machine.set_var("dirty_key", "dirty_val")
        state_machine._state["history"].append({"from": "x", "to": "y", "at": "now"})
        state_machine._state["retry_count"]["start"] = 99
        state_machine._state["iterations"]["start"] = 99

        # Re-initialize at a different stage — clears everything
        ok, _ = state_machine.initialize("middle")
        assert ok
        assert state_machine.history == []
        assert state_machine.get_retry_count("middle") == 0
        assert state_machine.get_iterations("middle") == 1
        assert state_machine.get_var("dirty_key") is None


# ═══════════════════════════════════════════════════════════════════════════
# TestTransitions
# ═══════════════════════════════════════════════════════════════════════════

class TestTransitions:
    def test_transition_to_next_stage_passes_conditions_met(self, state_machine):
        """transition to next stage passes when conditions met, history updated."""
        state_machine.initialize("start")
        ok, msgs = state_machine.transition_to("middle")
        assert ok
        assert state_machine.current_stage == "middle"
        assert "Transitioned" in msgs[0]
        history = state_machine.history
        assert len(history) == 1
        assert history[0]["from"] == "start"
        assert history[0]["to"] == "middle"
        assert "at" in history[0]

    def test_transition_no_defined_path_fails(self, state_machine):
        """transition to stage with no defined path fails."""
        state_machine.initialize("start")
        ok, msgs = state_machine.transition_to("end")  # no start->end in sample config
        assert not ok
        assert "No transition" in msgs[0] or "Available" in msgs[0]

    def test_force_transition_skips_conditions(self, state_machine):
        """force_transition skips conditions."""
        state_machine.initialize("start")
        # Normal transition to end would fail (no defined path / failing conditions)
        ok, msgs = state_machine.force_transition_to("end")
        assert ok
        assert state_machine.current_stage == "end"

    def test_failing_conditions_returns_false_increments_retry(self, state_machine, registry):
        """transition with failing conditions returns false, increments retry_count."""
        state_machine.initialize("start")
        # Register a transition that always fails
        registry.register_transition(
            "start", "end",
            conditions=[{"never": "blocked"}],
        )
        assert state_machine.get_retry_count("start") == 0

        ok, msgs = state_machine.transition_to("end")
        assert not ok
        assert state_machine.get_retry_count("start") == 1

        # Fail again — retry count increments further
        state_machine.transition_to("end")
        assert state_machine.get_retry_count("start") == 2

    def test_rollback_on_fail(self, state_machine, registry):
        """set up a transition with on_fail, fail the transition,
        verify stage auto-rolls back."""
        state_machine.initialize("start")
        registry.register_transition(
            "start", "end",
            conditions=[{"never": "forced failure for rollback"}],
            on_fail="start",
        )
        ok, msgs = state_machine.transition_to("end")
        assert not ok

        # Verify rollback message
        combined = " ".join(msgs)
        assert ("ROLLBACK" in combined or "rollback" in combined.lower()
                or "Auto-rolled back" in combined)

        # Stage should be back at start
        assert state_machine.current_stage == "start"

        # History should record the rollback
        history = state_machine.history
        assert len(history) == 1
        assert history[0]["from"] == "start"
        assert history[0]["to"] == "start"
        assert "reason" in history[0]

    def test_retry_count_resets_on_successful_not_on_force(self, state_machine, registry):
        """retry count resets on successful transition but NOT on force transition."""
        state_machine.initialize("start")

        # Add a continually-failing transition to pump retry_count on 'start'
        registry.register_transition(
            "start", "end",
            conditions=[{"never": "always fails"}],
            on_fail="start",
        )
        state_machine.transition_to("end")
        state_machine.transition_to("end")
        assert state_machine.get_retry_count("start") == 2

        # Successful normal transition resets TARGET's retry_count
        state_machine.transition_to("middle")
        assert state_machine.get_retry_count("middle") == 0

        # Force-transition back to 'start' — retry_count["start"] should NOT be reset
        state_machine.force_transition_to("start")
        assert state_machine.get_retry_count("start") == 2


# ═══════════════════════════════════════════════════════════════════════════
# TestToolRestrictions
# ═══════════════════════════════════════════════════════════════════════════

class TestToolRestrictions:
    def test_exact_match(self, state_machine):
        """is_tool_allowed with exact match (tool name in allow list)."""
        state_machine.initialize("start")  # tools: ["Read", "Write"]
        allowed, msg = state_machine.is_tool_allowed("Read")
        assert allowed
        assert "allowed" in msg.lower()

    def test_bash_pattern_match(self, state_machine):
        """Bash(git *) matches Bash(git status) and Bash(git diff)."""
        state_machine.initialize("middle")  # tools: ["Edit", "Bash(git *)"]
        allowed1, _ = state_machine.is_tool_allowed("Bash(git status)")
        assert allowed1
        allowed2, _ = state_machine.is_tool_allowed("Bash(git diff)")
        assert allowed2

    def test_constraint_partial_match(self, state_machine, registry):
        """Bash(python *) matches Bash(python test.py) but not Bash(ls)."""
        registry.register_stage("py_stage", tools=["Bash(python *)", "Read"])
        state_machine.initialize("py_stage")

        allowed, _ = state_machine.is_tool_allowed("Bash(python test.py)")
        assert allowed, "Bash(python test.py) should match Bash(python *)"

        allowed2, msg = state_machine.is_tool_allowed("Bash(ls)")
        assert not allowed2, f"Bash(ls) should NOT match Bash(python *): {msg}"

        allowed3, _ = state_machine.is_tool_allowed("Read")
        assert allowed3

    def test_no_current_stage(self, state_machine):
        """is_tool_allowed when no current stage set returns False."""
        allowed, msg = state_machine.is_tool_allowed("Read")
        assert not allowed
        assert "No current stage" in msg

    def test_empty_tools_allows_all(self, state_machine):
        """is_tool_allowed with empty tools list (should allow all)."""
        state_machine.initialize("end")  # tools: []
        allowed, msg = state_machine.is_tool_allowed("AnyRandomTool")
        assert allowed
        assert "All tools allowed" in msg


# ═══════════════════════════════════════════════════════════════════════════
# TestStageVariables
# ═══════════════════════════════════════════════════════════════════════════

class TestStageVariables:
    def test_set_var_and_get_var(self, state_machine):
        """set_var and get_var persistence."""
        state_machine.initialize("start")
        state_machine.set_var("issue_id", "ISS-42")
        assert state_machine.get_var("issue_id") == "ISS-42"

    def test_get_var_with_default(self, state_machine):
        """get_var with default value."""
        state_machine.initialize("start")
        assert state_machine.get_var("nonexistent") is None
        assert state_machine.get_var("nonexistent", "fallback_default") == "fallback_default"
        assert state_machine.get_var("nonexistent", 0) == 0

    def test_get_all_vars_returns_dict(self, state_machine):
        """get_all_vars returns dict."""
        state_machine.initialize("start")
        state_machine.set_var("a", 1)
        state_machine.set_var("b", "two")
        all_vars = state_machine.get_all_vars()
        assert isinstance(all_vars, dict)
        assert all_vars == {"a": 1, "b": "two"}

    def test_variables_survive_reload(self, state_machine, registry, temp_dir):
        """variables survive state machine reload (new StateMachine instance
        reads same state file)."""
        state_machine.initialize("start")
        state_machine.set_var("persistent", True)
        state_machine.set_var("name", "test")

        # New StateMachine instance with the same base_path
        sm2 = StateMachine(registry, str(temp_dir))
        assert sm2.get_var("persistent") is True
        assert sm2.get_var("name") == "test"


# ═══════════════════════════════════════════════════════════════════════════
# TestState
# ═══════════════════════════════════════════════════════════════════════════

class TestState:
    def test_status_returns_all_keys(self, state_machine):
        """status() returns all keys: current_stage, stage_info, history,
        retry_count, iterations, variables, available_next."""
        state_machine.initialize("start")
        s = state_machine.status()

        assert "current_stage" in s
        assert s["current_stage"] == "start"
        assert "stage_info" in s
        assert s["stage_info"] is not None
        assert s["stage_info"]["name"] == "start"
        assert "history" in s
        assert isinstance(s["history"], list)
        assert "retry_count" in s
        assert isinstance(s["retry_count"], dict)
        assert "iterations" in s
        assert isinstance(s["iterations"], dict)
        assert "variables" in s
        assert isinstance(s["variables"], dict)
        assert "available_next" in s
        assert s["available_next"] == ["middle"]

    def test_status_includes_registered_conditions(self, state_machine):
        """status includes registered_conditions list."""
        state_machine.initialize("start")
        s = state_machine.status()
        assert "registered_conditions" in s
        assert isinstance(s["registered_conditions"], list)
        assert "always" in s["registered_conditions"]
        assert "never" in s["registered_conditions"]
        assert "file_exists" in s["registered_conditions"]

    def test_history_records_transitions_with_timestamps(self, state_machine):
        """history records all transitions with timestamps."""
        state_machine.initialize("start")
        state_machine.transition_to("middle")
        state_machine.transition_to("end")

        history = state_machine.history
        assert len(history) == 2

        for entry in history:
            assert "at" in entry
            assert entry["at"] is not None
            assert isinstance(entry["at"], str)
            assert "T" in entry["at"]  # ISO 8601 format

        assert history[0]["from"] == "start"
        assert history[0]["to"] == "middle"
        assert history[1]["from"] == "middle"
        assert history[1]["to"] == "end"


# ═══════════════════════════════════════════════════════════════════════════
# TestReset
# ═══════════════════════════════════════════════════════════════════════════

class TestReset:
    def test_reset_clears_all_state(self, state_machine):
        """reset clears all state."""
        state_machine.initialize("start")
        state_machine.set_var("x", 1)
        state_machine.transition_to("middle")

        state_machine.reset()

        assert state_machine.current_stage is None
        assert state_machine.history == []
        assert state_machine.get_retry_count("start") == 0
        assert state_machine.get_iterations("start") == 0
        assert state_machine.get_var("x") is None

    def test_after_reset_current_stage_is_none(self, state_machine):
        """after reset, current_stage is None."""
        state_machine.initialize("start")
        assert state_machine.current_stage == "start"
        state_machine.reset()
        assert state_machine.current_stage is None

    def test_after_reset_history_is_empty(self, state_machine):
        """after reset, history is empty."""
        state_machine.initialize("start")
        state_machine.transition_to("middle")
        assert len(state_machine.history) == 1
        state_machine.reset()
        assert state_machine.history == []

    def test_reset_deletes_state_file(self, state_machine):
        """reset deletes the state file from disk."""
        state_machine.initialize("start")
        assert state_machine.state_path.exists()
        state_machine.reset()
        assert not state_machine.state_path.exists()


# ═══════════════════════════════════════════════════════════════════════════
# TestLifecycleHooks  (CRITICAL)
# ═══════════════════════════════════════════════════════════════════════════

class TestLifecycleHooks:
    def test_on_enter_hook_creates_file(self, state_machine, registry, temp_dir):
        """Set up a stage with on_enter hook that creates a file.
        Verify file exists after entering that stage."""
        hook_file = temp_dir / "hook_enter_flag.txt"

        # Register a stage with an on_enter python hook
        registry.register_stage(
            "hooked_enter",
            tools=["Read"],
            on_enter=[{
                "python": (
                    "import os; "
                    "open(os.path.join(base_path, 'hook_enter_flag.txt'), 'w')"
                    ".write('entered')"
                )
            }],
        )
        registry.register_transition(
            "start", "hooked_enter",
            conditions=[{"always": True}],
        )

        state_machine.initialize("start")
        assert not hook_file.exists(), "Hook should not fire during initialize"

        ok, msgs = state_machine.transition_to("hooked_enter")
        assert ok, f"Transition failed: {msgs}"
        assert state_machine.current_stage == "hooked_enter"
        assert hook_file.exists(), "on_enter hook should have created the file"
        assert hook_file.read_text() == "entered"

    def test_on_exit_hook_creates_file(self, state_machine, registry, temp_dir):
        """Set up a stage with on_exit hook that creates a file.
        Verify file exists after leaving that stage."""
        hook_file = temp_dir / "hook_exit_flag.txt"

        # Register stage with on_exit hook
        registry.register_stage(
            "exit_stage",
            tools=["Read"],
            on_exit=[{
                "python": (
                    "import os; "
                    "open(os.path.join(base_path, 'hook_exit_flag.txt'), 'w')"
                    ".write('exited')"
                )
            }],
        )
        registry.register_transition(
            "start", "exit_stage",
            conditions=[{"always": True}],
        )
        registry.register_transition(
            "exit_stage", "middle",
            conditions=[{"always": True}],
        )

        # Enter the stage — on_exit should NOT fire yet
        state_machine.initialize("start")
        state_machine.transition_to("exit_stage")
        assert not hook_file.exists(), "on_exit hook should NOT fire on enter"

        # Leave the stage — on_exit should fire now
        ok, msgs = state_machine.transition_to("middle")
        assert ok, f"Transition failed: {msgs}"
        assert hook_file.exists(), "on_exit hook should have created the file"
        assert hook_file.read_text() == "exited"

    def test_force_transition_skips_hooks(self, state_machine, registry, temp_dir):
        """Force transition skips hooks."""
        hook_enter_file = temp_dir / "force_hook_enter.txt"
        hook_exit_file = temp_dir / "force_hook_exit.txt"

        # Register a stage with both on_enter and on_exit hooks
        registry.register_stage(
            "force_hook_stage",
            tools=["Read"],
            on_enter=[{
                "python": (
                    "import os; "
                    "open(os.path.join(base_path, 'force_hook_enter.txt'), 'w')"
                    ".write('entered')"
                )
            }],
            on_exit=[{
                "python": (
                    "import os; "
                    "open(os.path.join(base_path, 'force_hook_exit.txt'), 'w')"
                    ".write('exited')"
                )
            }],
        )

        state_machine.initialize("start")

        # Force transition TO the hooked stage — on_enter should be skipped
        ok, _ = state_machine.force_transition_to("force_hook_stage")
        assert ok
        assert state_machine.current_stage == "force_hook_stage"
        assert not hook_enter_file.exists(), (
            "Force transition should skip on_enter hooks"
        )

        # Force transition AWAY from it — on_exit should also be skipped
        ok, _ = state_machine.force_transition_to("end")
        assert ok
        assert not hook_exit_file.exists(), (
            "Force transition should skip on_exit hooks"
        )
