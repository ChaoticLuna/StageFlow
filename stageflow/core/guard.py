"""Tool guard. Called by Claude Code PreToolUse hook to check if a tool is
allowed in the current stage. Also used by the framework for programmatic checking.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .engine import StateMachine
from .registry import StageRegistry


class StageGuard:
    """Intercepts tool calls and validates against current stage's allow list.

    Can be used:
      1. As a Claude Code PreToolUse hook (reads stdin JSON)
      2. Programmatically via check() method
      3. As a context manager for testing
    """

    def __init__(self, config_path: str = "stageflow/config/stages.yaml",
                 base_path: str = ".", registry: StageRegistry = None):
        self.registry = registry if registry is not None else StageRegistry(config_path)
        self.machine = StateMachine(self.registry, base_path)

    def check(self, tool_name: str, tool_input: dict = None) -> tuple[bool, str]:
        """Check if a tool call is allowed. Returns (allowed, message)."""
        # Refresh state from disk in case it changed
        self.machine._state = self.machine._load_state()
        return self.machine.is_tool_allowed(tool_name)

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
            "timestamp": None,  # Will be set by hook
        }
        log_path = Path(self.machine.base_path) / ".claude" / "guard_violations.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


def claude_hook_main():
    """Entry point for Claude Code PreToolUse hook.

    Reads hook input from stdin (JSON with tool_name and tool_input),
    checks against current stage, and outputs allow/block decision.

    Hook config in settings.json:
        "PreToolUse": [
            {
                "matcher": "",
                "hooks": [{"command": "python .claude/hooks/stage_guard.py"}]
            }
        ]
    """
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, IOError) as e:
        # If we can't read hook input, allow by default to avoid deadlock
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
