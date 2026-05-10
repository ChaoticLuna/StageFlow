"""Comprehensive tests for StageGuard and tool pattern matching."""

import pytest
from pathlib import Path

from stageflow.core.guard import StageGuard
from stageflow.core.engine import StateMachine
from stageflow.core.registry import StageRegistry


# ═══════════════════════════════════════════════════════════════════════════
# TestStageGuardCheck
# ═══════════════════════════════════════════════════════════════════════════

class TestStageGuardCheck:
    def test_check_with_allowed_tool(self, registry, temp_dir):
        """check with allowed tool returns (True, message)."""
        # Initialize state via a separate StateMachine (saves to disk)
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")  # tools: ["Read", "Write"]

        # Guard reads state from the same disk location
        guard = StageGuard(str(registry.config_path), str(temp_dir))
        allowed, msg = guard.check("Read")
        assert allowed is True
        assert "allowed" in msg.lower()

    def test_check_with_disallowed_tool(self, registry, temp_dir):
        """check with disallowed tool returns (False, message)."""
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")  # tools: ["Read", "Write"]

        guard = StageGuard(str(registry.config_path), str(temp_dir))
        allowed, msg = guard.check("Delete")
        assert allowed is False
        assert "NOT allowed" in msg

    def test_check_refreshes_state_from_disk(self, registry, temp_dir):
        """check refreshes state from disk."""
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")  # tools: ["Read", "Write"]

        guard = StageGuard(str(registry.config_path), str(temp_dir))

        # First check sees 'start' stage
        allowed, _ = guard.check("Read")
        assert allowed
        allowed, _ = guard.check("Edit")
        assert not allowed, "Edit should not be allowed in 'start' stage"

        # Now change state via a different StateMachine instance
        sm2 = StateMachine(registry, str(temp_dir))
        sm2.current_stage = "middle"  # tools: ["Edit", "Bash(git *)"]

        # Guard should reload from disk and see 'middle' stage
        allowed, _ = guard.check("Edit")
        assert allowed, "Guard should have reloaded state and allowed Edit in middle"

    def test_allowed_tools_returns_current_stage_tools(self, registry, temp_dir):
        """allowed_tools returns current stage's tool list."""
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")

        guard = StageGuard(str(registry.config_path), str(temp_dir))
        tools = guard.allowed_tools()
        assert tools == ["Read", "Write"]

    def test_allowed_tools_no_current_stage(self, registry, temp_dir):
        """allowed_tools returns empty list when no stage is set."""
        guard = StageGuard(str(registry.config_path), str(temp_dir))
        tools = guard.allowed_tools()
        assert tools == []


# ═══════════════════════════════════════════════════════════════════════════
# TestToolPatternMatching
# ═══════════════════════════════════════════════════════════════════════════

class TestToolPatternMatching:
    def test_bash_exact_pattern_match(self, state_machine):
        """Bash exact pattern match -- a tool name listed without wildcard
        must match exactly."""
        state_machine.registry.register_stage(
            "exact_stage", tools=["Bash(git status)", "Read"],
        )
        state_machine.initialize("exact_stage")
        allowed, msg = state_machine.is_tool_allowed("Bash(git status)")
        assert allowed, f"Exact match should pass: {msg}"

    def test_bash_wildcard_match(self, state_machine):
        """Bash wildcard match: Bash(git *) matches Bash(git diff)."""
        state_machine.registry.register_stage(
            "wildcard_stage", tools=["Bash(git *)", "Read"],
        )
        state_machine.initialize("wildcard_stage")

        allowed, msg = state_machine.is_tool_allowed("Bash(git diff)")
        assert allowed, f"Wildcard should match: {msg}"

        allowed, msg = state_machine.is_tool_allowed("Bash(git log --oneline)")
        assert allowed, f"Wildcard should match multi-arg git command: {msg}"

    def test_bash_no_match(self, state_machine):
        """Bash no-match: Bash(git *) does NOT match Bash(python test.py)."""
        state_machine.registry.register_stage(
            "git_only_stage", tools=["Bash(git *)", "Read"],
        )
        state_machine.initialize("git_only_stage")

        allowed, msg = state_machine.is_tool_allowed("Bash(python test.py)")
        assert not allowed, f"Should NOT match different command: {msg}"


class TestPathGuard:
    def test_write_to_artifacts_allowed(self, registry, temp_dir):
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")  # tools: [Read, Write]
        guard = StageGuard(str(registry.config_path), str(temp_dir))
        allowed, msg = guard.check("Write", {"file_path": "artifacts/test/output.md"})
        assert allowed, f"Write to artifacts/ should be allowed: {msg}"

    def test_write_to_dot_claude_allowed(self, registry, temp_dir):
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir))
        allowed, msg = guard.check("Write", {"file_path": ".claude/notes.md"})
        assert allowed, f"Write to .claude/ should be allowed: {msg}"

    def test_write_outside_denied(self, registry, temp_dir):
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir))
        allowed, msg = guard.check("Write", {"file_path": "stageflow/core/engine.py"})
        assert not allowed, f"Write to engine.py should be denied: {msg}"
        assert "denied" in msg.lower()

    def test_edit_outside_denied(self, registry, temp_dir):
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir))
        allowed, msg = guard.check("Edit", {"file_path": "pyproject.toml"})
        assert not allowed, f"Edit to pyproject.toml should be denied: {msg}"

    def test_read_always_allowed_if_in_tools(self, registry, temp_dir):
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir))
        allowed, msg = guard.check("Read", {"file_path": "stageflow/core/engine.py"})
        # Read is not in WRITE_TOOLS, so path guard doesn't apply
        assert allowed, f"Read should be allowed regardless of path: {msg}"

    def test_path_guard_can_be_disabled(self, registry, temp_dir):
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir),
                          enforce_path_guard=False)
        allowed, msg = guard.check("Write", {"file_path": "stageflow/core/engine.py"})
        assert allowed, f"Path guard disabled should allow write anywhere: {msg}"

    def test_notebook_edit_also_checked(self, registry, temp_dir):
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir))
        allowed, msg = guard.check("NotebookEdit", {"notebook_path": "scripts/evil.ipynb"})
        assert not allowed, f"NotebookEdit outside allowed roots: {msg}"

    def test_write_without_file_path(self, registry, temp_dir):
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir))
        allowed, msg = guard.check("Write", {})
        assert allowed, f"Write without file_path should pass: {msg}"
