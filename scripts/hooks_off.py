#!/usr/bin/env python3
"""Disable StageFlow PreToolUse/PostToolUse hooks by overriding in settings.local.json.

Usage:
    python scripts/hooks_off.py           # Disable hooks
    python scripts/hooks_off.py --status  # Show current hook state
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_SETTINGS = PROJECT_ROOT / ".claude" / "settings.local.json"
BACKUP_FILE = PROJECT_ROOT / ".claude" / "settings.local.bak.json"


def is_hooks_enabled() -> bool:
    """Check if hooks are currently enabled."""
    if not LOCAL_SETTINGS.exists():
        return True  # No local override = project hooks active

    try:
        data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return True

    hooks = data.get("hooks", None)
    if hooks is None:
        return True  # No hook override = project hooks active
    if hooks == {}:
        return False  # Explicitly disabled
    return True


def disable_hooks():
    """Set hooks to empty dict in settings.local.json to override project hooks."""
    if not is_hooks_enabled():
        print("Hooks are already DISABLED.")
        return

    # Backup existing local settings if present
    if LOCAL_SETTINGS.exists():
        import shutil
        shutil.copy(LOCAL_SETTINGS, BACKUP_FILE)
        print(f"  Backed up existing local settings to {BACKUP_FILE.name}")

    # Read current local settings or create defaults
    if LOCAL_SETTINGS.exists():
        try:
            data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            data = {}
    else:
        data = {"permissionMode": "bypassPermissions"}

    # Override hooks with empty dict
    data["hooks"] = {}
    data.setdefault("permissions", {})
    data.setdefault("permissionMode", "bypassPermissions")

    LOCAL_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("Hooks DISABLED. All tools unrestricted.")
    print(f"  (Modified: {LOCAL_SETTINGS})")


def enable_hooks():
    """Restore hooks by removing the hooks override from settings.local.json."""
    if is_hooks_enabled():
        print("Hooks are already ENABLED.")
        return

    if not LOCAL_SETTINGS.exists():
        print("No local settings file found — hooks should already be enabled.")
        return

    try:
        data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        print("Cannot read local settings — deleting it to restore project defaults.")
        LOCAL_SETTINGS.unlink()
        print("Hooks ENABLED (local settings removed).")
        return

    # Remove hooks override
    if "hooks" in data:
        del data["hooks"]

    if data:
        LOCAL_SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("Hooks ENABLED (hooks override removed from local settings).")
    else:
        LOCAL_SETTINGS.unlink()
        print("Hooks ENABLED (empty local settings deleted).")


def show_status():
    state = "DISABLED" if not is_hooks_enabled() else "ENABLED"
    print(f"Hook status: {state}")
    if LOCAL_SETTINGS.exists():
        try:
            data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
            hooks = data.get("hooks", "not set (project hooks active)")
            print(f"  Local hooks override: {hooks}")
        except Exception:
            pass
    else:
        print("  No local settings file — project hooks active.")


def main():
    if "--status" in sys.argv or "-s" in sys.argv:
        show_status()
        return 0

    if "--on" in sys.argv or "-on" in sys.argv:
        enable_hooks()
        return 0

    # Default: disable hooks
    disable_hooks()
    return 0


if __name__ == "__main__":
    sys.exit(main())
