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

    def test_can_transition_to_uninitialized_valid_stage(self, state_machine):
        ok, msgs = state_machine.can_transition_to("start")
        assert ok is True
        assert "Initial stage" in msgs[0]

    def test_can_transition_to_uninitialized_unknown_stage(self, state_machine):
        ok, msgs = state_machine.can_transition_to("ghost_stage")
        assert ok is False
        assert "Unknown stage" in msgs[0]


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

    def test_tool_allowed_star_wildcard(self, state_machine, registry):
        registry.register_stage("star_stage", tools=["Bash(*)"])
        state_machine.initialize("star_stage")
        allowed1, _ = state_machine.is_tool_allowed("Bash(git status)")
        assert allowed1
        allowed2, _ = state_machine.is_tool_allowed("Bash(ls -la)")
        assert allowed2

    def test_tool_allowed_unknown_current_stage(self, registry, temp_dir):
        state_path = temp_dir / ".claude" / "current_stage.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"current_stage": "ghost"}), encoding="utf-8")
        sm = StateMachine(registry, str(temp_dir))
        allowed, msg = sm.is_tool_allowed("Read")
        assert not allowed
        assert "Unknown stage" in msg


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
        assert all_vars["a"] == 1
        assert all_vars["b"] == "two"
        assert "run_id" in all_vars  # auto-generated by initialize()

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

    def test_interpolate_vars_in_list(self, state_machine):
        state_machine.initialize("start")
        state_machine.set_var("x", "alpha")
        state_machine.set_var("y", "beta")
        result = state_machine._interpolate_vars(
            ["{{var.x}}/path", "{{var.y}}/other", "static"]
        )
        assert result == ["alpha/path", "beta/other", "static"]

    def test_interpolate_vars_scalar_passthrough(self, state_machine):
        state_machine.initialize("start")
        assert state_machine._interpolate_vars(42) == 42
        assert state_machine._interpolate_vars(None) is None
        assert state_machine._interpolate_vars(True) is True


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
# TestStateCorruptionRecovery
# ═══════════════════════════════════════════════════════════════════════════

class TestStateCorruptionRecovery:
    def test_corrupted_json_recovers_to_defaults(self, temp_dir, registry):
        state_path = temp_dir / ".claude" / "current_stage.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("this is not valid json {{{", encoding="utf-8")
        sm = StateMachine(registry, str(temp_dir))
        assert sm.current_stage is None
        assert sm.history == []

    def test_corrupted_json_creates_backup(self, temp_dir, registry):
        state_path = temp_dir / ".claude" / "current_stage.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        original_content = "corrupted state file {{{"
        state_path.write_text(original_content, encoding="utf-8")
        StateMachine(registry, str(temp_dir))
        bak_path = temp_dir / ".claude" / "current_stage.json.bak"
        assert bak_path.exists()
        assert "corrupted" in bak_path.read_text()

    def test_valid_json_loads_normally(self, temp_dir, registry):
        state_path = temp_dir / ".claude" / "current_stage.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        state_path.write_text(json.dumps({
            "current_stage": "analyze",
            "history": [{"from": "pick", "to": "analyze", "at": "2026-01-01T00:00:00"}],
            "retry_count": {}, "iterations": {}, "variables": {}, "paused": False,
        }), encoding="utf-8")
        sm = StateMachine(registry, str(temp_dir))
        assert sm.current_stage == "analyze"
        assert len(sm.history) == 1


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

    def test_shell_hook_executes_successfully(self, state_machine, registry, temp_dir):
        hook_file = temp_dir / "shell_hook_flag.txt"
        registry.register_stage(
            "shell_hook_stage",
            tools=["Read"],
            on_enter=[{
                "shell": f"echo entered > {hook_file}"
            }],
        )
        registry.register_transition(
            "start", "shell_hook_stage",
            conditions=[{"always": True}],
        )
        state_machine.initialize("start")
        ok, msgs = state_machine.transition_to("shell_hook_stage")
        assert ok, f"Transition failed: {msgs}"
        assert hook_file.exists(), "Shell hook should have created the file"

    def test_shell_hook_failure_does_not_block_transition(self, state_machine, registry):
        registry.register_stage(
            "bad_shell_stage",
            tools=["Read"],
            on_enter=[{
                "shell": "exit 1"
            }],
        )
        registry.register_transition(
            "start", "bad_shell_stage",
            conditions=[{"always": True}],
        )
        state_machine.initialize("start")
        ok, msgs = state_machine.transition_to("bad_shell_stage")
        assert ok is True
        assert state_machine.current_stage == "bad_shell_stage"

    def test_python_hook_exception_does_not_block(self, state_machine, registry):
        registry.register_stage(
            "bad_py_stage",
            tools=["Read"],
            on_enter=[{
                "python": "raise RuntimeError('hook exploded')"
            }],
        )
        registry.register_transition(
            "start", "bad_py_stage",
            conditions=[{"always": True}],
        )
        state_machine.initialize("start")
        ok, msgs = state_machine.transition_to("bad_py_stage")
        assert ok is True
        assert state_machine.current_stage == "bad_py_stage"


class TestPauseResume:
    def test_not_paused_by_default(self, state_machine):
        state_machine.initialize("start")
        assert state_machine.is_paused is False

    def test_pause_sets_flag(self, state_machine):
        state_machine.initialize("start")
        state_machine.pause("Maintenance window")
        assert state_machine.is_paused is True

    def test_resume_clears_flag(self, state_machine):
        state_machine.initialize("start")
        state_machine.pause("break")
        state_machine.resume()
        assert state_machine.is_paused is False

    def test_pause_persists_across_reload(self, state_machine, registry, temp_dir):
        state_machine.initialize("start")
        state_machine.pause("system upgrade")
        sm2 = StateMachine(registry, str(temp_dir))
        assert sm2.is_paused is True
        assert sm2._state["paused_reason"] == "system upgrade"

    def test_resume_persists_across_reload(self, state_machine, registry, temp_dir):
        state_machine.initialize("start")
        state_machine.pause("test")
        state_machine.resume()
        sm2 = StateMachine(registry, str(temp_dir))
        assert sm2.is_paused is False

    def test_paused_transition_to_blocked(self, state_machine):
        state_machine.initialize("start")
        state_machine.pause("blocking test")
        ok, msgs = state_machine.transition_to("middle")
        assert ok is False
        assert any("paused" in m.lower() for m in msgs)

    def test_paused_force_transition_blocked(self, state_machine):
        state_machine.initialize("start")
        state_machine.pause("no force allowed")
        ok, msgs = state_machine.force_transition_to("middle")
        assert ok is False

    def test_paused_can_transition_to_blocked(self, state_machine):
        state_machine.initialize("start")
        state_machine.pause("test")
        ok, msgs = state_machine.can_transition_to("middle")
        assert ok is False

    def test_paused_initialize_blocked(self, state_machine):
        state_machine.pause("testing init block")
        ok, msgs = state_machine.initialize("start")
        assert ok is False

    def test_resume_allows_transitions_again(self, state_machine):
        state_machine.initialize("start")
        state_machine.pause("temporary")
        state_machine.resume()
        ok, msgs = state_machine.transition_to("middle")
        assert ok is True

    def test_reset_clears_paused_state(self, state_machine):
        state_machine.initialize("start")
        state_machine.pause("will reset")
        state_machine.reset()
        assert state_machine.is_paused is False

    def test_pause_with_reason_stores_reason(self, state_machine):
        state_machine.initialize("start")
        state_machine.pause("deploy in progress")
        assert "deploy in progress" in str(state_machine._state.get("paused_reason", ""))

    def test_pause_error_message_includes_reason(self, state_machine):
        state_machine.initialize("start")
        state_machine.pause("maintenance window")
        ok, msgs = state_machine.transition_to("middle")
        assert any("maintenance window" in m for m in msgs)

    def test_pause_audit_logged(self, state_machine, temp_dir):
        state_machine.initialize("start")
        state_machine.pause("audit test")
        audit_path = temp_dir / ".claude" / "audit.jsonl"
        assert audit_path.exists()
        content = audit_path.read_text(encoding="utf-8")
        assert '"event": "pause"' in content

    def test_resume_audit_logged(self, state_machine, temp_dir):
        state_machine.initialize("start")
        state_machine.pause("test")
        state_machine.resume()
        audit_path = temp_dir / ".claude" / "audit.jsonl"
        content = audit_path.read_text(encoding="utf-8")
        assert '"event": "resume"' in content


class TestWebhookHooks:
    def test_webhook_on_enter_is_called(self, state_machine, registry, temp_dir):
        import json
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler

        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                length = int(inner.headers.get("Content-Length", 0))
                body = inner.rfile.read(length).decode("utf-8") if length else ""
                received.append({"path": inner.path, "body": body, "headers": dict(inner.headers)})
                inner.send_response(200)
                inner.send_header("Content-Type", "application/json")
                inner.end_headers()
                inner.wfile.write(b'{"status":"ok"}')
            def log_message(inner, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        registry.register_stage(
            "webhook_stage",
            tools=["Read"],
            on_enter=[{
                "webhook": {
                    "url": f"http://127.0.0.1:{port}/hook",
                    "method": "POST",
                    "body": {"stage": "webhook_stage", "action": "entered"},
                }
            }],
        )
        registry.register_transition("start", "webhook_stage",
                                    conditions=[{"always": True}])

        state_machine.initialize("start")
        state_machine.transition_to("webhook_stage")

        import time
        time.sleep(0.1)
        thread.join(timeout=2)
        server.server_close()

        assert state_machine.current_stage == "webhook_stage"
        assert len(received) == 1, f"Expected 1 webhook call, got {len(received)}"
        body = json.loads(received[0]["body"])
        assert body["stage"] == "webhook_stage"
        assert body["action"] == "entered"

    def test_webhook_failure_does_not_block_transition(self, state_machine, registry, temp_dir):
        registry.register_stage(
            "bad_webhook_stage",
            tools=["Read"],
            on_enter=[{
                "webhook": {
                    "url": "http://127.0.0.1:1/nonexistent",  # nothing listening
                    "method": "POST",
                    "timeout": 1,
                }
            }],
        )
        registry.register_transition("start", "bad_webhook_stage",
                                    conditions=[{"always": True}])

        state_machine.initialize("start")
        ok, msgs = state_machine.transition_to("bad_webhook_stage")
        assert ok is True
        assert state_machine.current_stage == "bad_webhook_stage"

    def test_webhook_variable_interpolation_url(self, state_machine, registry, temp_dir):
        import json
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler

        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                length = int(inner.headers.get("Content-Length", 0))
                body = inner.rfile.read(length).decode("utf-8") if length else ""
                received.append({"path": inner.path, "body": body})
                inner.send_response(200)
                inner.send_header("Content-Type", "application/json")
                inner.end_headers()
                inner.wfile.write(b'{}')
            def log_message(inner, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        registry.register_stage(
            "var_stage",
            tools=["Read"],
            on_enter=[{
                "webhook": {
                    "url": f"http://127.0.0.1:{port}/{{{{var.task_id}}}}",
                    "method": "POST",
                    "body": {"msg": "Processing {{var.task_id}}"},
                }
            }],
        )
        registry.register_transition("start", "var_stage",
                                    conditions=[{"always": True}])

        state_machine.initialize("start")
        state_machine.set_var("task_id", "TASK-042")
        state_machine.transition_to("var_stage")

        import time
        time.sleep(0.1)
        thread.join(timeout=2)
        server.server_close()

        assert len(received) == 1
        assert received[0]["path"] == "/TASK-042"
        body = json.loads(received[0]["body"])
        assert body["msg"] == "Processing TASK-042"

    def test_webhook_variable_interpolation_headers(self, state_machine, registry, temp_dir):
        import json
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler

        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                length = int(inner.headers.get("Content-Length", 0))
                body = inner.rfile.read(length).decode("utf-8") if length else ""
                received.append({"headers": dict(inner.headers), "body": body})
                inner.send_response(200)
                inner.send_header("Content-Type", "application/json")
                inner.end_headers()
                inner.wfile.write(b'{}')
            def log_message(inner, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        registry.register_stage(
            "header_stage",
            tools=["Read"],
            on_enter=[{
                "webhook": {
                    "url": f"http://127.0.0.1:{port}/hook",
                    "method": "POST",
                    "body": {},
                    "headers": {"X-Token": "{{var.api_token}}"},
                }
            }],
        )
        registry.register_transition("start", "header_stage",
                                    conditions=[{"always": True}])

        state_machine.initialize("start")
        state_machine.set_var("api_token", "secret-123")
        state_machine.transition_to("header_stage")

        import time
        time.sleep(0.1)
        thread.join(timeout=2)
        server.server_close()

        assert len(received) == 1
        assert received[0]["headers"].get("X-Token") == "secret-123"

    def test_webhook_audit_logged_on_enter(self, state_machine, registry, temp_dir):
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler

        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                inner.send_response(200)
                inner.send_header("Content-Type", "application/json")
                inner.end_headers()
                inner.wfile.write(b'{"ok":true}')
            def log_message(inner, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        registry.register_stage(
            "audit_webhook",
            tools=["Read"],
            on_enter=[{
                "webhook": {
                    "url": f"http://127.0.0.1:{port}/audit",
                    "method": "POST",
                }
            }],
        )
        registry.register_transition("start", "audit_webhook",
                                    conditions=[{"always": True}])

        state_machine.initialize("start")
        state_machine.transition_to("audit_webhook")

        import time
        time.sleep(0.1)
        thread.join(timeout=2)
        server.server_close()

        audit_path = temp_dir / ".claude" / "audit.jsonl"
        content = audit_path.read_text(encoding="utf-8")
        assert '"hook_type": "on_enter"' in content
        assert '"hook_kind": "webhook"' in content

    def test_webhook_http_error_handled(self, state_machine, registry, temp_dir):
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler

        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                inner.send_response(500)
                inner.send_header("Content-Type", "text/plain")
                inner.end_headers()
                inner.wfile.write(b"Internal Server Error")
            def log_message(inner, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        registry.register_stage(
            "http_error_stage",
            tools=["Read"],
            on_enter=[{
                "webhook": {
                    "url": f"http://127.0.0.1:{port}/error",
                    "method": "POST",
                    "timeout": 2,
                }
            }],
        )
        registry.register_transition("start", "http_error_stage",
                                    conditions=[{"always": True}])

        state_machine.initialize("start")
        ok, msgs = state_machine.transition_to("http_error_stage")
        assert ok is True
        assert state_machine.current_stage == "http_error_stage"

        import time
        time.sleep(0.1)
        thread.join(timeout=2)
        server.server_close()

    def test_webhook_default_method_is_post(self, state_machine, registry, temp_dir):
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler

        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                received.append(inner.command)
                inner.send_response(200)
                inner.send_header("Content-Type", "application/json")
                inner.end_headers()
                inner.wfile.write(b'{}')
            def log_message(inner, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        registry.register_stage(
            "default_method_stage",
            tools=["Read"],
            on_enter=[{
                "webhook": {
                    "url": f"http://127.0.0.1:{port}/test",
                }
            }],
        )
        registry.register_transition("start", "default_method_stage",
                                    conditions=[{"always": True}])

        state_machine.initialize("start")
        state_machine.transition_to("default_method_stage")

        import time
        time.sleep(0.1)
        thread.join(timeout=2)
        server.server_close()

        assert len(received) == 1


# ═══════════════════════════════════════════════════════════════════════════
# TestSeverityInEngine — severity levels integrated with StateMachine
# ═══════════════════════════════════════════════════════════════════════════

class TestSeverityInEngine:
    def test_hard_failure_prevents_rollback(self, state_machine, registry):
        """When a hard-severity condition fails, engine does NOT rollback."""
        state_machine.initialize("start")
        registry.register_transition(
            "start", "end",
            conditions=[{"severity": "hard", "never": "hard safety gate"}],
            on_fail="start",
        )
        ok, msgs = state_machine.transition_to("end")
        assert ok is False
        combined = " ".join(msgs)
        assert "HARD_BLOCK" in combined, f"Expected [HARD_BLOCK] in: {msgs}"
        assert state_machine.current_stage == "start"

    def test_hard_failure_increments_retry_count(self, state_machine, registry):
        """Hard failure still increments retry count."""
        state_machine.initialize("start")
        registry.register_transition(
            "start", "end",
            conditions=[{"severity": "hard", "never": "blocked"}],
        )
        assert state_machine.get_retry_count("start") == 0
        state_machine.transition_to("end")
        assert state_machine.get_retry_count("start") == 1

    def test_soft_failure_with_rollback_still_works(self, state_machine, registry):
        """Soft severity (default) failure with on_fail still triggers rollback."""
        state_machine.initialize("start")
        registry.register_transition(
            "start", "end",
            conditions=[{"severity": "soft", "never": "soft block"}],
            on_fail="start",
        )
        ok, msgs = state_machine.transition_to("end")
        assert ok is False
        combined = " ".join(msgs)
        assert "ROLLBACK" in combined or "Auto-rolled back" in combined
        assert state_machine.current_stage == "start"

    def test_hard_failure_multiple_conditions(self, state_machine, registry):
        """With multiple conditions, a hard failure prevents rollback even
        if earlier conditions passed."""
        state_machine.initialize("start")
        registry.register_transition(
            "start", "end",
            conditions=[
                {"always": True},
                {"severity": "hard", "never": "hard gate"},
            ],
            on_fail="start",
        )
        ok, msgs = state_machine.transition_to("end")
        assert ok is False
        combined = " ".join(msgs)
        assert "HARD_BLOCK" in combined or "HARD_FAIL" in combined

    def test_warn_condition_via_evaluate_all_passes_transition(self, state_machine, registry, temp_dir):
        """A warn-severity condition that fails does NOT block the transition."""
        state_machine.initialize("start")
        registry.register_transition(
            "start", "end",
            conditions=[{"severity": "warn", "file_exists": "does_not_exist.txt"}],
        )
        ok, msgs = state_machine.transition_to("end")
        assert ok is True, f"Warn condition should not block: {msgs}"
        assert state_machine.current_stage == "end"

    def test_mixed_severity_warn_and_pass(self, state_machine, registry, temp_dir):
        """Mixed: warn (fails but passes) + always (passes) -> transition succeeds."""
        state_machine.initialize("start")
        registry.register_transition(
            "start", "end",
            conditions=[
                {"severity": "warn", "file_exists": "nope.txt"},
                {"always": True},
            ],
        )
        ok, msgs = state_machine.transition_to("end")
        assert ok is True

    def test_force_transition_bypasses_hard_condition(self, state_machine, registry):
        """Force transition skips conditions including hard severity."""
        state_machine.initialize("start")
        registry.register_transition(
            "start", "end",
            conditions=[{"severity": "hard", "never": "hard gate"}],
        )
        ok, msgs = state_machine.force_transition_to("end")
        assert ok is True
        assert state_machine.current_stage == "end"

    def test_no_rollback_when_no_on_fail_configured(self, state_machine, registry):
        """Without on_fail, any severity failure just blocks without rollback."""
        state_machine.initialize("start")
        registry.register_transition(
            "start", "end",
            conditions=[{"severity": "soft", "never": "blocked"}],
        )
        ok, msgs = state_machine.transition_to("end")
        assert ok is False
        assert state_machine.current_stage == "start"
        history = state_machine.history
        assert len(history) == 0


# ═══════════════════════════════════════════════════════════════════════════
# TestMaxIterations — iteration caps per stage
# ═══════════════════════════════════════════════════════════════════════════

class TestMaxIterations:
    def test_no_cap_by_default(self, state_machine, registry):
        """Without max_iterations, stage can be entered unlimited times."""
        state_machine.initialize("start")
        for _ in range(5):
            ok, _ = state_machine.transition_to("middle")
            assert ok
            state_machine.force_transition_to("start")

    def test_cap_blocks_transition_when_exceeded(self, state_machine, registry):
        """When max_iterations is set, exceeding it blocks the transition."""
        registry.register_stage("capped_stage", tools=["Read"],
                                max_iterations=2)
        registry.register_transition(
            "start", "capped_stage",
            conditions=[{"always": True}],
        )
        state_machine.initialize("start")

        # Enter capped_stage twice — should work
        ok1, _ = state_machine.transition_to("capped_stage")
        assert ok1
        state_machine.force_transition_to("start")

        ok2, _ = state_machine.transition_to("capped_stage")
        assert ok2

        # Third time — blocked
        state_machine.force_transition_to("start")
        ok3, msgs = state_machine.transition_to("capped_stage")
        assert ok3 is False
        assert any("ITERATION_CAP" in m for m in msgs)

    def test_cap_message_includes_limit_and_count(self, state_machine, registry):
        """ITERATION_CAP message includes the limit and current count."""
        registry.register_stage("limited", tools=["Read"],
                                max_iterations=1)
        registry.register_transition(
            "start", "limited",
            conditions=[{"always": True}],
        )
        state_machine.initialize("start")
        state_machine.transition_to("limited")
        state_machine.force_transition_to("start")
        ok, msgs = state_machine.transition_to("limited")
        assert not ok
        combined = " ".join(msgs)
        assert "1" in combined

    def test_force_bypasses_iteration_cap(self, state_machine, registry):
        """Force transition bypasses max_iterations check."""
        registry.register_stage("capped", tools=["Read"],
                                max_iterations=1)
        state_machine.initialize("start")
        state_machine.transition_to("capped")
        state_machine.force_transition_to("start")
        # Force should work even though cap is exceeded
        ok, _ = state_machine.force_transition_to("capped")
        assert ok is True

    def test_cap_per_stage_independent(self, state_machine, registry):
        """Each stage has its own independent iteration cap."""
        registry.register_stage("capped_a", tools=["Read"],
                                max_iterations=1)
        registry.register_stage("capped_b", tools=["Read"],
                                max_iterations=3)
        registry.register_transition(
            "start", "capped_a", conditions=[{"always": True}])
        registry.register_transition(
            "start", "capped_b", conditions=[{"always": True}])

        state_machine.initialize("start")

        # capped_a: 1 entry works
        ok, _ = state_machine.transition_to("capped_a")
        assert ok
        state_machine.force_transition_to("start")
        ok, _ = state_machine.transition_to("capped_a")
        assert not ok  # capped_a limit reached

        # capped_b: still has room
        state_machine.force_transition_to("start")
        for _ in range(3):
            state_machine.force_transition_to("start")
            ok, _ = state_machine.transition_to("capped_b")
            assert ok
        state_machine.force_transition_to("start")
        ok, _ = state_machine.transition_to("capped_b")
        assert not ok  # capped_b limit reached

    def test_iterations_count_tracks_entries(self, state_machine, registry):
        """iterations field in state tracks entry count for capped stages."""
        registry.register_stage("tracked", tools=["Read"],
                                max_iterations=5)
        registry.register_transition(
            "start", "tracked", conditions=[{"always": True}])
        state_machine.initialize("start")
        assert state_machine.get_iterations("tracked") == 0
        state_machine.transition_to("tracked")
        assert state_machine.get_iterations("tracked") == 1


class TestTransitionReason:
    """transition_to(reason=...) writes reason into history and audit."""

    def test_reason_in_history(self, state_machine, registry):
        registry.register_transition(
            "start", "next", conditions=[{"always": True}])
        state_machine.initialize("start")
        state_machine.transition_to("next", reason="analysis complete")
        assert state_machine.history[-1]["reason"] == "analysis complete"

    def test_reason_optional(self, state_machine, registry):
        """Backward compatible: omitting reason still works."""
        registry.register_transition(
            "start", "next", conditions=[{"always": True}])
        state_machine.initialize("start")
        ok, _ = state_machine.transition_to("next")
        assert ok
        assert "reason" not in state_machine.history[-1]

    def test_reason_in_force_transition(self, state_machine, registry):
        registry.register_stage("target", tools=[])
        state_machine.initialize("start")
        state_machine.force_transition_to("target", reason="manual override")
        assert state_machine.history[-1]["reason"] == "manual override"

    def test_reason_in_audit_log(self, state_machine, registry):
        registry.register_transition(
            "start", "next", conditions=[{"always": True}])
        state_machine.initialize("start")
        state_machine.transition_to("next", reason="test audit reason")
        log_path = state_machine.base_path / ".claude" / "audit.jsonl"
        assert log_path.exists()
        raw = log_path.read_text()
        assert "test audit reason" in raw

    def test_empty_reason_not_in_record(self, state_machine, registry):
        """Empty reason string is not written to history record."""
        registry.register_transition(
            "start", "next", conditions=[{"always": True}])
        state_machine.initialize("start")
        state_machine.transition_to("next", reason="")
        assert "reason" not in state_machine.history[-1]


# ═══════════════════════════════════════════════════════════════════════════
# TestRepr — __repr__ coverage (line 461)
# ═══════════════════════════════════════════════════════════════════════════

class TestRepr:
    def test_repr_uninitialized(self, state_machine):
        assert repr(state_machine) == "StateMachine(stage=None, transitions=0)"

    def test_repr_with_stage_and_history(self, state_machine):
        state_machine.initialize("start")
        state_machine.transition_to("middle")
        r = repr(state_machine)
        assert "stage='middle'" in r
        assert "transitions=1" in r


# ═══════════════════════════════════════════════════════════════════════════
# TestRunIdentity — run_id lifecycle (task-077)
# ═══════════════════════════════════════════════════════════════════════════

class TestRunIdentity:
    def test_initialize_creates_run_id(self, state_machine):
        state_machine.initialize("start")
        run_id = state_machine.get_var("run_id")
        assert run_id is not None
        assert len(run_id) == 36  # UUID format
        # Verify persistence across a fresh StateMachine load
        sm2 = StateMachine(state_machine.registry, str(state_machine.base_path))
        assert sm2.get_var("run_id") == run_id

    def test_two_default_resets_create_different_run_ids(self, state_machine):
        state_machine.initialize("start")
        run_id_1 = state_machine.get_var("run_id")
        state_machine.reset()
        state_machine.initialize("start")
        run_id_2 = state_machine.get_var("run_id")
        assert run_id_1 != run_id_2

    def test_reuse_run_preserves_run_id(self, state_machine):
        state_machine.initialize("start")
        run_id_1 = state_machine.get_var("run_id")
        # initialize with reuse_run=True keeps the existing run_id
        state_machine.initialize("start", reuse_run=True)
        run_id_2 = state_machine.get_var("run_id")
        assert run_id_1 == run_id_2

    def test_reuse_run_missing_old_run_id_creates_one(self, state_machine):
        # Manually set state without a run_id
        state_machine._state = {
            "current_stage": None,
            "history": [],
            "retry_count": {},
            "iterations": {},
            "variables": {},
            "paused": False,
            "paused_reason": "",
        }
        state_machine.initialize("start", reuse_run=True)
        run_id = state_machine.get_var("run_id")
        assert run_id is not None
        assert len(run_id) == 36  # UUID format


# ═══════════════════════════════════════════════════════════════════════════
# TestCleanArtifacts — --clean-artifacts (task-080)
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanArtifacts:
    def test_clean_removes_current_run_artifacts(self, state_machine):
        state_machine.initialize("start")
        run_id = state_machine.get_var("run_id")
        run_dir = state_machine.base_path / "artifacts" / "runs" / run_id
        adir = run_dir / "analyze"
        adir.mkdir(parents=True)
        (adir / "findings.md").write_text("test", encoding="utf-8")
        assert run_dir.exists()

        state_machine.clean_run_artifacts()
        assert not run_dir.exists(), "Current run dir should be deleted"

    def test_clean_preserves_old_run_dirs(self, state_machine):
        state_machine.initialize("start")
        run_id_1 = state_machine.get_var("run_id")
        # Create artifacts for run 1
        run_dir_1 = state_machine.base_path / "artifacts" / "runs" / run_id_1
        run_dir_1.mkdir(parents=True)
        (run_dir_1 / "data.txt").write_text("run 1 data", encoding="utf-8")

        # Start a fresh run (different run_id)
        state_machine.reset()
        state_machine.initialize("start")
        run_id_2 = state_machine.get_var("run_id")
        assert run_id_1 != run_id_2
        run_dir_2 = state_machine.base_path / "artifacts" / "runs" / run_id_2
        run_dir_2.mkdir(parents=True)
        (run_dir_2 / "data.txt").write_text("run 2 data", encoding="utf-8")

        # Clean current (run 2) artifacts
        state_machine.clean_run_artifacts()
        assert not run_dir_2.exists(), "Current run dir should be deleted"
        assert run_dir_1.exists(), "Old run dir must remain"
        assert (run_dir_1 / "data.txt").read_text(encoding="utf-8") == "run 1 data"

    def test_clean_noop_when_no_run_id(self, state_machine):
        # No run_id set — clean should not crash
        state_machine._state["variables"] = {}
        state_machine.clean_run_artifacts()  # Should not raise

    def test_clean_noop_when_dir_does_not_exist(self, state_machine):
        state_machine.initialize("start")
        # Don't create any artifacts
        state_machine.clean_run_artifacts()  # Should not raise

    def test_no_cleanup_without_flag(self, state_machine):
        state_machine.initialize("start")
        run_id = state_machine.get_var("run_id")
        run_dir = state_machine.base_path / "artifacts" / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "data.txt").write_text("keep me", encoding="utf-8")

        # Normal reset without cleaning
        state_machine.reset()
        assert run_dir.exists(), "Artifacts preserved without --clean-artifacts flag"


# =============================================================================
# TestResumeSemantics — session-change resume (task-085)
# =============================================================================

class TestResumeSemantics:
    def test_fresh_sm_loads_existing_state(self, state_machine):
        state_machine.initialize("start")
        run_id_1 = state_machine.get_var("run_id")
        state_machine.transition_to("middle")

        sm2 = StateMachine(state_machine.registry, str(state_machine.base_path))
        assert sm2.current_stage == "middle"
        assert sm2.get_var("run_id") == run_id_1

    def test_resume_can_continue_work(self, state_machine):
        state_machine.initialize("start")
        state_machine.transition_to("middle")

        sm2 = StateMachine(state_machine.registry, str(state_machine.base_path))
        ok, msgs = sm2.transition_to("end")
        assert ok, f"Resumed session should continue transitions: {msgs}"
        assert sm2.current_stage == "end"

    def test_reset_creates_new_run_id_cross_session(self, state_machine):
        state_machine.initialize("start")
        run_id_1 = state_machine.get_var("run_id")
        state_machine.transition_to("middle")

        sm2 = StateMachine(state_machine.registry, str(state_machine.base_path))
        sm2.reset()
        sm2.initialize("start")
        run_id_2 = sm2.get_var("run_id")
        assert run_id_1 != run_id_2

    def test_reuse_run_preserves_id_cross_session(self, state_machine):
        state_machine.initialize("start")
        run_id_1 = state_machine.get_var("run_id")
        state_machine.transition_to("middle")

        sm2 = StateMachine(state_machine.registry, str(state_machine.base_path))
        sm2.initialize("start", reuse_run=True)
        run_id_2 = sm2.get_var("run_id")
        assert run_id_1 == run_id_2

    def test_multiple_session_reloads_keep_same_run_id(self, state_machine):
        state_machine.initialize("start")
        run_id_1 = state_machine.get_var("run_id")

        sm2 = StateMachine(state_machine.registry, str(state_machine.base_path))
        assert sm2.get_var("run_id") == run_id_1

        sm3 = StateMachine(state_machine.registry, str(state_machine.base_path))
        assert sm3.get_var("run_id") == run_id_1

        sm3.transition_to("middle")
        sm4 = StateMachine(state_machine.registry, str(state_machine.base_path))
        assert sm4.current_stage == "middle"
        ok, _ = sm4.transition_to("end")
        assert ok
