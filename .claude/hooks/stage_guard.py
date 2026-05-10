#!/usr/bin/env python3
"""Claude Code PreToolUse Hook — intercepts tool calls and enforces stage-based access control.

This hook reads the current stage from .claude/current_stage.json and the stage
definitions from stageflow/config/stages.yaml. If a tool is not allowed in the
current stage, the call is blocked.

Hook input (stdin JSON):
    {"tool_name": "Edit", "tool_input": {"file_path": "..."}}

Hook output (stdout JSON):
    {"decision": "allow"} or {"decision": "block", "reason": "..."}

Integration in settings.json (via update-config skill or manual):
    {
      "hooks": {
        "PreToolUse": [
          {
            "matcher": "",
            "hooks": [
              {
                "type": "command",
                "command": "python .claude/hooks/stage_guard.py"
              }
            ]
          }
        ]
      }
    }

Special tools that are ALWAYS allowed (to prevent deadlocks):
    - Bash(python scripts/*) — operational scripts need to run
    - TaskCreate, TaskUpdate, TaskList — task management
    - Read — always safe
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Always-allow tools (to prevent deadlocks)
ALWAYS_ALLOW = {
    "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TaskOutput",
    "Read", "AskUserQuestion",
}
# Always-allow Bash commands (operational scripts)
ALWAYS_ALLOW_BASH = {
    "python scripts/stage_next.py",
    "python scripts/stage_status.py",
    "python scripts/stage_reset.py",
    "python scripts/stage_jump.py",
    "python scripts/stage_back.py",
    "python -c",  # For time checks etc
}


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, IOError):
        # Can't parse input: allow to avoid deadlock
        print(json.dumps({"decision": "allow", "reason": "hook input parse error — allowing"}))
        return 0

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Always allow certain tools
    if tool_name in ALWAYS_ALLOW:
        print(json.dumps({"decision": "allow", "reason": f"{tool_name} is always allowed"}))
        return 0

    # Always allow operational scripts via Bash
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        for prefix in ALWAYS_ALLOW_BASH:
            if cmd.strip().startswith(prefix):
                print(json.dumps({"decision": "allow",
                                  "reason": f"Bash({cmd[:60]}) is always allowed"}))
                return 0

    # Load current stage
    state_path = PROJECT_ROOT / ".claude" / "current_stage.json"
    current_stage = None
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            current_stage = state.get("current_stage")
        except (json.JSONDecodeError, IOError):
            pass

    # No stage set: allow everything (bootstrap mode)
    if current_stage is None:
        print(json.dumps({"decision": "allow", "reason": "no stage set (bootstrap mode)"}))
        return 0

    # Load stage definitions
    config_path = PROJECT_ROOT / "stageflow" / "config" / "stages.yaml"
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        print(json.dumps({"decision": "allow",
                          "reason": f"config load error: {e} — allowing"}))
        return 0

    # Find current stage definition
    stages = {s["name"]: s for s in config.get("stages", [])}
    stage_def = stages.get(current_stage)

    if stage_def is None:
        print(json.dumps({"decision": "allow",
                          "reason": f"stage '{current_stage}' not found in config — allowing"}))
        return 0

    allowed_tools = stage_def.get("tools", [])

    # Empty tools list = allow all
    if not allowed_tools:
        print(json.dumps({"decision": "allow",
                          "reason": f"stage '{current_stage}' has unrestricted tools"}))
        return 0

    # Check exact match
    if tool_name in allowed_tools:
        print(json.dumps({"decision": "allow",
                          "reason": f"'{tool_name}' allowed in stage '{current_stage}'"}))
        return 0

    # Check pattern match (e.g., "Bash(git *)" matches "Bash(git status)")
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        for allowed in allowed_tools:
            if allowed.startswith("Bash("):
                pattern = allowed[5:-1].strip()  # Extract pattern inside Bash(...)
                if _match_pattern(pattern, cmd.strip()):
                    print(json.dumps({"decision": "allow",
                                      "reason": f"Bash({cmd[:60]}) matches '{allowed}' in stage '{current_stage}'"}))
                    return 0

    # Blocked
    reason = (f"Tool '{tool_name}' is NOT allowed in stage '{current_stage}'. "
              f"Allowed tools: {allowed_tools}")
    print(json.dumps({"decision": "block", "reason": reason}))
    _log_violation(tool_name, current_stage, reason)
    return 1


def _match_pattern(pattern: str, actual: str) -> bool:
    """Match a glob-like pattern against a command string."""
    import re
    regex = "^" + pattern.replace("*", ".*").replace("?", ".") + "$"
    return bool(re.match(regex, actual))


def _log_violation(tool_name: str, stage: str, reason: str):
    """Log tool access violations for audit."""
    log_path = PROJECT_ROOT / ".claude" / "guard_violations.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "tool": tool_name,
        "stage": stage,
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    sys.exit(main())
