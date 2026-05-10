"""Integration tests for stage lifecycle hooks (on_enter/on_exit).

Verifies: on_enter/on_exit hook execution, non-blocking failure,
multiple hooks per stage, and audit logging of hook events.
"""

from __future__ import annotations

import json
from pathlib import Path


class TestOnEnterShellHook:
    def test_shell_hook_creates_file(self, stageflow_temp_sm, tmp_path):
        marker = tmp_path / "shell_enter_marker.txt"
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"shell": f'echo done > "{marker}"'}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert marker.exists()
        content = marker.read_text()
        assert "done" in content

    def test_shell_hook_on_enter_then_transition(self, stageflow_temp_sm, tmp_path):
        marker = tmp_path / "enter_transition_test.txt"
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"shell": f'echo staged > "{marker}"'}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert marker.exists()
        stageflow_temp_sm.transition_to("omega")
        assert stageflow_temp_sm.current_stage == "omega"


class TestOnExitShellHook:
    def test_shell_hook_on_exit_creates_file(self, stageflow_temp_sm, tmp_path):
        marker = tmp_path / "shell_exit_marker.txt"
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_exit=[{"shell": f'echo departed > "{marker}"'}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert not marker.exists()  # Not yet — still in alpha
        stageflow_temp_sm.transition_to("omega")
        assert marker.exists()
        assert "departed" in marker.read_text()


class TestOnEnterPythonHook:
    def test_python_hook_on_enter_sets_var(self, stageflow_temp_sm):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"python": "sm.set_var('hooked', True)"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert stageflow_temp_sm.get_var("hooked") is True

    def test_python_hook_has_access_to_stage_name(self, stageflow_temp_sm):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"python": "sm.set_var('entered_stage', stage)"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert stageflow_temp_sm.get_var("entered_stage") == "alpha"


class TestOnExitPythonHook:
    def test_python_hook_on_exit_sets_var(self, stageflow_temp_sm):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_exit=[{"python": "sm.set_var('left_alpha', True)"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert stageflow_temp_sm.get_var("left_alpha") is None
        stageflow_temp_sm.transition_to("omega")
        assert stageflow_temp_sm.get_var("left_alpha") is True


class TestHookFailureNonBlocking:
    def test_shell_hook_failure_does_not_block_initialize(self, stageflow_temp_sm):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"shell": "nonexistent_command_xyz_123"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        ok, msgs = stageflow_temp_sm.initialize("alpha")
        assert ok
        assert stageflow_temp_sm.current_stage == "alpha"

    def test_shell_hook_failure_does_not_block_transition(self, stageflow_temp_sm):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_exit=[{"shell": "exit 1"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        ok, msgs = stageflow_temp_sm.transition_to("omega")
        assert ok
        assert stageflow_temp_sm.current_stage == "omega"

    def test_python_hook_error_does_not_block_initialize(self, stageflow_temp_sm):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"python": "raise RuntimeError('boom')"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        ok, msgs = stageflow_temp_sm.initialize("alpha")
        assert ok
        assert stageflow_temp_sm.current_stage == "alpha"

    def test_python_hook_syntax_error_does_not_block(self, stageflow_temp_sm):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"python": "this is not valid python *** !!!"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        ok, msgs = stageflow_temp_sm.initialize("alpha")
        assert ok


class TestMultipleHooksPerStage:
    def test_three_on_enter_hooks_all_execute(self, stageflow_temp_sm):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[], on_enter=[
            {"python": "sm.set_var('h1', True)"},
            {"python": "sm.set_var('h2', True)"},
            {"python": "sm.set_var('h3', True)"},
        ])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert stageflow_temp_sm.get_var("h1") is True
        assert stageflow_temp_sm.get_var("h2") is True
        assert stageflow_temp_sm.get_var("h3") is True

    def test_mixed_shell_and_python_hooks(self, stageflow_temp_sm, tmp_path):
        marker = tmp_path / "mixed_hook.txt"
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[], on_enter=[
            {"shell": f'echo shell_done > "{marker}"'},
            {"python": "sm.set_var('py_done', True)"},
        ])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert marker.exists()
        assert stageflow_temp_sm.get_var("py_done") is True

    def test_on_enter_and_on_exit_both_execute(self, stageflow_temp_sm):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"python": "sm.set_var('entered', True)"}],
                           on_exit=[{"python": "sm.set_var('exited', True)"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert stageflow_temp_sm.get_var("entered") is True
        assert stageflow_temp_sm.get_var("exited") is None

        stageflow_temp_sm.transition_to("omega")
        assert stageflow_temp_sm.get_var("exited") is True


class TestHookAuditLogging:
    def test_hook_execution_logged_to_audit(self, stageflow_temp_sm, tmp_path):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"python": "sm.set_var('audit_test', 42)"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        stageflow_temp_sm.transition_to("omega")

        audit_path = tmp_path / ".claude" / "audit.jsonl"
        assert audit_path.exists()

        events = []
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        hook_events = [e for e in events if e.get("event") == "hook_execution"]
        assert len(hook_events) >= 1, f"No hook_execution events in audit log; found: {[e.get('event') for e in events]}"

    def test_shell_hook_failure_logged_to_audit(self, stageflow_temp_sm, tmp_path):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"shell": "nonexistent_command_xyz"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")

        audit_path = tmp_path / ".claude" / "audit.jsonl"
        events = []
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        hook_events = [e for e in events if e.get("event") == "hook_execution"]
        assert len(hook_events) >= 1
        failure = hook_events[0]
        assert failure["success"] is False
        assert failure["hook_type"] == "on_enter"
        assert failure["hook_kind"] == "shell"

    def test_stage_enter_exit_audit_events(self, stageflow_temp_sm, tmp_path):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        stageflow_temp_sm.transition_to("omega")

        audit_path = tmp_path / ".claude" / "audit.jsonl"
        events = []
        with open(audit_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        enter_events = [e for e in events if e.get("event") == "stage_enter"]
        exit_events = [e for e in events if e.get("event") == "stage_exit"]
        transition_events = [e for e in events if e.get("event") == "transition"]

        assert len(enter_events) >= 2  # alpha init + omega
        assert len(exit_events) >= 1   # alpha exit
        assert len(transition_events) >= 1  # alpha -> omega


class TestForceTransitionSkipsHooks:
    def test_force_transition_skips_hooks(self, stageflow_temp_sm, tmp_path):
        reg = stageflow_temp_sm.registry
        reg.register_stage("alpha", tools=[],
                           on_enter=[{"python": "sm.set_var('hook_ran', True)"}],
                           on_exit=[{"python": "sm.set_var('exit_hook_ran', True)"}])
        reg.register_stage("omega", tools=[])
        reg.register_transition("alpha", "omega", [{"always": True}])

        stageflow_temp_sm.initialize("alpha")
        assert stageflow_temp_sm.get_var("hook_ran") is True  # init runs hooks

        stageflow_temp_sm.force_transition_to("omega")
        assert stageflow_temp_sm.get_var("exit_hook_ran") is None  # force skips exit hooks
