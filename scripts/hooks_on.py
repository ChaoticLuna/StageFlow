#!/usr/bin/env python3
"""Re-enable StageFlow hooks (convenience wrapper around hooks_off.py --on).

Usage:
    python scripts/hooks_on.py            # Re-enable hooks
    python scripts/hooks_on.py --status   # Show current state
    python scripts/hooks_on.py --json     # JSON output
    python scripts/hooks_on.py --dry-run  # Print what would change
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hooks_off import enable_hooks, show_status


def main():
    parser = argparse.ArgumentParser(
        description="StageFlow: re-enable PreToolUse/PostToolUse hooks"
    )
    parser.add_argument("--status", "-s", action="store_true", help="Show current hook state")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Print what would change without doing it")
    args = parser.parse_args()

    if args.status:
        show_status(as_json=args.json)
        return 0

    enable_hooks(dry_run=args.dry_run)
    show_status(as_json=args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
