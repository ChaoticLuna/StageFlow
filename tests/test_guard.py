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
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Read")
        assert allowed is True
        assert "allowed" in msg.lower()

    def test_check_with_disallowed_tool(self, registry, temp_dir):
        """check with disallowed tool returns (False, message)."""
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")  # tools: ["Read", "Write"]

        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Delete")
        assert allowed is False
        assert "NOT allowed" in msg

    def test_check_refreshes_state_from_disk(self, registry, temp_dir):
        """check refreshes state from disk."""
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")  # tools: ["Read", "Write"]

        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)

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

        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        tools = guard.allowed_tools()
        assert tools == ["Read", "Write"]

    def test_allowed_tools_no_current_stage(self, registry, temp_dir):
        """allowed_tools returns empty list when no stage is set."""
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
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
    """Path-level access control via AccessPolicy, unified with cmd_hook."""

    @staticmethod
    def _register_secured_stage(registry, name="secured", tools=None,
                                access=None):
        kwargs = {}
        if access is not None:
            kwargs["access"] = access
        registry.register_stage(name, tools=tools or ["Read", "Write", "Edit", "NotebookEdit"], **kwargs)

    def test_write_to_artifacts_allowed(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["artifacts/**", ".claude/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Write", {"file_path": "artifacts/test/output.md"})
        assert allowed, f"Write to artifacts/ should be allowed: {msg}"

    def test_write_to_dot_claude_allowed(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["artifacts/**", ".claude/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Write", {"file_path": ".claude/notes.md"})
        assert allowed, f"Write to .claude/ should be allowed: {msg}"

    def test_write_outside_denied(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["artifacts/**", ".claude/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Write", {"file_path": "stageflow/core/engine.py"})
        assert not allowed, f"Write to engine.py should be denied: {msg}"
        assert "denied" in msg.lower() or "not in allow" in msg.lower()

    def test_edit_outside_denied(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["artifacts/**", ".claude/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Edit", {"file_path": "pyproject.toml"})
        assert not allowed, f"Edit to pyproject.toml should be denied: {msg}"

    def test_read_allowed_when_no_read_policy(self, registry, temp_dir):
        """Read passes through when stage has no access.read policy."""
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Read", {"file_path": "stageflow/core/engine.py"})
        assert allowed, f"Read should be allowed when no read policy: {msg}"

    def test_read_blocked_by_read_policy(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"read": {"allow": ["artifacts/**", "*.md"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Read", {"file_path": "secret.env"})
        assert not allowed, f"Read outside allow list should be blocked: {msg}"

    def test_path_guard_can_be_disabled(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["artifacts/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry,
                          enforce_path_guard=False)
        allowed, msg = guard.check("Write", {"file_path": "stageflow/core/engine.py"})
        assert allowed, f"Path guard disabled should allow write anywhere: {msg}"

    def test_notebook_edit_also_checked(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["artifacts/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("NotebookEdit", {"notebook_path": "scripts/evil.ipynb"})
        assert not allowed, f"NotebookEdit outside allowed roots: {msg}"
        r = guard.check("NotebookEdit", {"notebook_path": "artifacts/ok.ipynb"})
        assert r[0], f"NotebookEdit in artifacts should be allowed: {r[1]}"

    def test_write_without_file_path(self, registry, temp_dir):
        """No access policy → write without file_path passes through."""
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Write", {"some_other_arg": "value"})
        assert allowed, f"Write without file_path should pass: {msg}"

    def test_write_missing_path_with_policy_fails_closed(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["artifacts/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Write", {"some_other_arg": "value"})
        assert not allowed, f"Write without file_path when policy exists should fail closed: {msg}"

    def test_write_absolute_path_outside_project(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Write", {"file_path": "C:/Windows/evil.ps1"})
        assert not allowed, f"Absolute path outside project should be denied: {msg}"
        assert "outside" in msg.lower() or "escape" in msg.lower()

    def test_write_absolute_path_inside_project(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        abs_path = str(Path(temp_dir).resolve() / "artifacts" / "ok.md")
        allowed, msg = guard.check("Write", {"file_path": abs_path})
        assert allowed, f"Absolute path inside project should be allowed: {msg}"

    def test_write_dot_path_allowed(self, registry, temp_dir):
        """No access policy → write to '.' passes through."""
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Write", {"file_path": "."})
        assert allowed, f"Write to '.' should be allowed: {msg}"

    def test_deny_overrides_allow(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            access={"write": {"allow": ["**"], "deny": ["secrets/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Write", {"file_path": "secrets/key.txt"})
        assert not allowed, f"Deny should override allow: {msg}"

    def test_grep_search_root_checked(self, registry, temp_dir):
        self._register_secured_stage(
            registry, "secured",
            tools=["Read", "Grep"],
            access={"read": {"allow": ["artifacts/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        allowed, msg = guard.check("Grep", {"pattern": "TODO", "path": "artifacts"})
        assert allowed, f"Grep in allowed dir should pass: {msg}"
        allowed, msg = guard.check("Grep", {"pattern": "TODO", "path": "stageflow"})
        assert not allowed, f"Grep outside allowed dir should be blocked: {msg}"

    def test_no_active_run_falls_through_to_base_result(self, registry, temp_dir):
        """Line 60: when current_stage is None (no state file), return base_result."""
        self._register_secured_stage(
            registry, "secured",
            tools=["Read"],
            access={"read": {"allow": ["artifacts/**"]}},
        )
        guard = StageGuard(
            str(registry.config_path), str(temp_dir), registry=registry,
        )
        allowed, msg = guard.check("Read", {"file_path": "artifacts/x.md"})
        assert not allowed, "No active run: is_tool_allowed should return False"

    def test_stage_not_in_registry_falls_through(self, registry, temp_dir):
        """Line 64: current_stage set to a stage not in the registry."""
        self._register_secured_stage(
            registry, "secured",
            tools=["Read"],
            access={"read": {"allow": ["artifacts/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        sm._state["current_stage"] = "ghost_stage"
        sm._save_state()
        guard = StageGuard(
            str(registry.config_path), str(temp_dir), registry=registry,
        )
        allowed, msg = guard.check("Read", {"file_path": "artifacts/x.md"})
        assert not allowed, f"Ghost stage not in registry should fail: {msg}"

    def test_read_missing_path_with_read_policy_fails_closed(self, registry, temp_dir):
        """Line 74: Read without file_path when read policy exists -> fail closed."""
        self._register_secured_stage(
            registry, "secured",
            tools=["Read", "Grep"],
            access={"read": {"allow": ["artifacts/**"]}},
        )
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("secured")
        guard = StageGuard(
            str(registry.config_path), str(temp_dir), registry=registry,
        )
        allowed, msg = guard.check("Read", {"not_a_path": 1})
        assert not allowed, f"Read without file_path should fail closed: {msg}"
        assert "read" in msg.lower()


class TestGuardLogViolation:
    def test_log_violation_writes_to_file(self, registry, temp_dir):
        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")
        guard = StageGuard(str(registry.config_path), str(temp_dir), registry=registry)
        guard.log_violation("Delete", "Not in tools list")
        log_path = Path(temp_dir) / ".claude" / "guard_violations.jsonl"
        assert log_path.exists()
        content = log_path.read_text()
        assert "Delete" in content
        assert "start" in content


class TestClaudeHookMain:
    def test_valid_input_allows_tool(self, monkeypatch, registry, temp_dir):
        import json
        from stageflow.core.guard import claude_hook_main

        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")

        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(
            json.dumps({"tool_name": "Read", "tool_input": {}})
        ))
        output_calls = []

        def capture_output(data):
            output_calls.append(json.loads(data))

        monkeypatch.setattr("builtins.print", capture_output)

        monkeypatch.setattr("stageflow.core.guard.StageGuard.__init__",
            lambda self, config_path=None, base_path=None: None)
        monkeypatch.setattr("stageflow.core.guard.StageGuard.check",
            lambda self, tn, ti=None: (True, "Read is allowed"))
        monkeypatch.setattr("stageflow.core.guard.StageGuard.log_violation",
            lambda self, tn, msg: None)

        try:
            claude_hook_main()
        except SystemExit as e:
            assert e.code == 0

        assert output_calls[0]["decision"] == "allow"

    def test_invalid_json_fallback_allows(self, monkeypatch):
        import json
        from stageflow.core.guard import claude_hook_main

        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("not valid json"))
        output_calls = []

        def capture_output(data):
            output_calls.append(json.loads(data))

        monkeypatch.setattr("builtins.print", capture_output)

        claude_hook_main()
        assert output_calls[0]["decision"] == "allow"
        assert "error" in output_calls[0]["reason"].lower()

    def test_blocked_tool_prints_block_and_logs(self, monkeypatch, registry, temp_dir):
        import json
        from stageflow.core.guard import claude_hook_main

        sm = StateMachine(registry, str(temp_dir))
        sm.initialize("start")

        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(
            json.dumps({"tool_name": "Delete", "tool_input": {}})
        ))
        output_calls = []

        def capture_output(data):
            output_calls.append(json.loads(data))

        monkeypatch.setattr("builtins.print", capture_output)

        monkeypatch.setattr("stageflow.core.guard.StageGuard.__init__",
            lambda self, config_path=None, base_path=None: None)
        monkeypatch.setattr("stageflow.core.guard.StageGuard.check",
            lambda self, tn, ti=None: (False, "Delete is NOT allowed"))
        monkeypatch.setattr("stageflow.core.guard.StageGuard.log_violation",
            lambda self, tn, msg: None)

        try:
            claude_hook_main()
        except SystemExit as e:
            assert e.code == 1

        assert output_calls[0]["decision"] == "block"
