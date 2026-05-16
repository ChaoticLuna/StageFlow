"""Tool guard. Called by Claude Code PreToolUse hook to check if a tool is
allowed in the current stage. Also used by the framework for programmatic checking.

Path-level access control delegates to :class:`AccessPolicy` so the
programmatic ``StageGuard`` and the ``stageflow hook`` CLI enforce the
same policy from the same stage ``access`` configuration.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .engine import StateMachine
from .registry import StageRegistry
from .access_policy import AccessPolicy


_READ_TOOLS = {"Read", "Grep", "Glob"}
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _extract_file_path(tool_name: str, tool_input: dict) -> str | None:
    if tool_name == "NotebookEdit":
        return tool_input.get("notebook_path") or tool_input.get("file_path")
    if tool_name in ("Grep", "Glob"):
        return tool_input.get("path")
    return tool_input.get("file_path")


class StageGuard:
    """Intercepts tool calls and validates against current stage's allow list.

    Can be used:
      1. As a Claude Code PreToolUse hook (reads stdin JSON)
      2. Programmatically via check() method
      3. As a context manager for testing
    """

    def __init__(self, config_path: str = "stageflow/config/stages.yaml",
                 base_path: str = ".", registry: StageRegistry | None = None,
                 enforce_path_guard: bool = True):
        self.registry = registry if registry is not None else StageRegistry(config_path)
        self.machine = StateMachine(self.registry, base_path)
        self._enforce_path_guard = enforce_path_guard

    def check(self, tool_name: str, tool_input: dict | None = None) -> tuple[bool, str]:
        """Check if a tool call is allowed. Returns (allowed, message)."""
        self.machine._state = self.machine._load_state()
        current = self.machine.current_stage
        base_result = self.machine.is_tool_allowed(tool_name)

        # Default read tools bypass the stage.tools name check when a run is
        # active and the stage exists. access.read still applies below.
        if not base_result[0] and tool_name in _READ_TOOLS and current is not None:
            if self.registry.get_stage(current) is not None:
                base_result = (True, f"'{tool_name}' is a default read tool")

        if not base_result[0]:
            return base_result

        if not self._enforce_path_guard or not tool_input:
            return base_result

        if current is None:
            return base_result

        stage = self.registry.get_stage(current)
        if stage is None:
            return base_result

        access_config = stage.extra.get("access") if stage.extra else None
        policy = AccessPolicy(access_config)
        variables = self.machine.get_all_vars()
        project_root = str(self.machine.base_path)

        if tool_name in _READ_TOOLS and policy.has_read_policy:
            path = _extract_file_path(tool_name, tool_input)
            if path is None:
                return False, (
                    f"access.read: '{tool_name}' requires a file path or "
                    f"search root when stage '{current}' has a read policy"
                )
            if tool_name in ("Grep", "Glob"):
                return policy.check_search(path, project_root, variables)
            return policy.check_read(path, project_root, variables)

        if tool_name in _WRITE_TOOLS and policy.has_write_policy:
            path = _extract_file_path(tool_name, tool_input)
            if path is None:
                return False, (
                    f"access.write: '{tool_name}' requires a file_path when "
                    f"stage '{current}' has a write policy"
                )
            return policy.check_write(path, project_root, variables)

        return base_result

    def allowed_tools(self) -> list[str]:
        """Return list of tools allowed in the current stage."""
        current = self.machine.current_stage
        if current is None:
            return []
        stage = self.registry.get_stage(current)
        return stage.tools if stage else []

    def log_violation(self, tool_name: str, reason: str):
        """Log a tool access violation."""
        log_entry = {
            "tool": tool_name,
            "stage": self.machine.current_stage,
            "reason": reason,
            "timestamp": None,
        }
        log_path = Path(self.machine.base_path) / ".claude" / "guard_violations.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


def claude_hook_main():
    """Entry point for Claude Code PreToolUse hook.

    Reads hook input from stdin (JSON with tool_name and tool_input),
    checks against current stage, and outputs allow/block decision.

    .. deprecated::
        Prefer ``stageflow hook`` (``cmd_hook`` in ``__main__.py``) which
        enforces the full tool + access policy in a unified entrypoint.
        This function remains for backward compatibility with legacy hook
        configurations that invoke ``python .claude/hooks/stage_guard.py``.
    """
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, IOError) as e:
        print(json.dumps({"decision": "allow", "reason": f"Hook input error: {e}"}))
        return

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    guard = StageGuard()
    allowed, message = guard.check(tool_name, tool_input)

    if allowed:
        output = {"decision": "allow", "message": message}
    else:
        guard.log_violation(tool_name, message)
        output = {"decision": "block", "message": message, "reason": message}

    print(json.dumps(output))
    sys.exit(0 if allowed else 1)


if __name__ == "__main__":
    claude_hook_main()
