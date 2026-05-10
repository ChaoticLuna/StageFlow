#!/usr/bin/env python3
"""Disable StageFlow PreToolUse/PostToolUse hooks by overriding in settings.local.json.

Usage:
    python scripts/hooks_off.py           # Disable hooks
    python scripts/hooks_off.py --status  # Show current hook state
    python scripts/hooks_off.py --on      # Re-enable hooks
    python scripts/hooks_off.py --json    # JSON output (for scripting)
    python scripts/hooks_off.py --dry-run # Print what would change without doing it
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCAL_SETTINGS = PROJECT_ROOT / ".claude" / "settings.local.json"
BACKUP_FILE = PROJECT_ROOT / ".claude" / "settings.local.bak.json"


def is_hooks_enabled() -> bool:
    if not LOCAL_SETTINGS.exists():
        return True
    try:
        data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return True
    hooks = data.get("hooks", None)
    if hooks is None:
        return True
    if hooks == {}:
        return False
    return True


def disable_hooks(dry_run: bool = False):
    if not is_hooks_enabled():
        print("Hooks are already DISABLED.")
        return
    if dry_run:
        print("[DRY-RUN] Would disable hooks.")
        return
    if LOCAL_SETTINGS.exists():
        import shutil
        shutil.copy(LOCAL_SETTINGS, BACKUP_FILE)
        print(f"  Backed up existing local settings to {BACKUP_FILE.name}")
    if LOCAL_SETTINGS.exists():
        try:
            data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            data = {}
    else:
        data = {"permissionMode": "bypassPermissions"}
    data["hooks"] = {}
    data.setdefault("permissions", {})
    data.setdefault("permissionMode", "bypassPermissions")
    LOCAL_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("Hooks DISABLED. All tools unrestricted.")
    print(f"  (Modified: {LOCAL_SETTINGS})")


def enable_hooks(dry_run: bool = False):
    if is_hooks_enabled():
        print("Hooks are already ENABLED.")
        return
    if dry_run:
        print("[DRY-RUN] Would enable hooks.")
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
    if "hooks" in data:
        del data["hooks"]
    if data:
        LOCAL_SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("Hooks ENABLED (hooks override removed from local settings).")
    else:
        LOCAL_SETTINGS.unlink()
        print("Hooks ENABLED (empty local settings deleted).")


def show_status(as_json: bool = False):
    state = "DISABLED" if not is_hooks_enabled() else "ENABLED"
    hooks_override = None
    if LOCAL_SETTINGS.exists():
        try:
            data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
            hooks_override = data.get("hooks", "not set (project hooks active)")
        except Exception:
            pass
    if as_json:
        print(json.dumps({"status": state, "hooks_override": str(hooks_override)}))
    else:
        print(f"Hook status: {state}")
        if hooks_override is not None:
            print(f"  Local hooks override: {hooks_override}")
        else:
            print("  No local settings file — project hooks active.")


def main():
    parser = argparse.ArgumentParser(
        description="StageFlow: enable/disable PreToolUse/PostToolUse hooks"
    )
    parser.add_argument("--status", "-s", action="store_true", help="Show current hook state")
    parser.add_argument("--on", action="store_true", help="Re-enable hooks")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Print what would change without doing it")
    args = parser.parse_args()

    if args.status:
        show_status(as_json=args.json)
        return 0

    if args.on:
        enable_hooks(dry_run=args.dry_run)
        return 0

    # Default: disable hooks
    disable_hooks(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
