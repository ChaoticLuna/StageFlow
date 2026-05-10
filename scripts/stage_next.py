#!/usr/bin/env python3
"""Advance to the next stage. Framework-enforced condition checking.

Usage:
    python scripts/stage_next.py              # Advance to default next stage
    python scripts/stage_next.py <target>     # Advance to specific stage
    python scripts/stage_next.py --force      # Force advance (skip conditions)
    python scripts/stage_next.py --list       # Show available next stages
    python scripts/stage_next.py --dry-run    # Check conditions without advancing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine


def main():
    parser = argparse.ArgumentParser(description="StageFlow: advance to next stage")
    parser.add_argument("target", nargs="?", help="Target stage name")
    parser.add_argument("--force", "-f", action="store_true", help="Force advance, skip conditions")
    parser.add_argument("--list", "-l", action="store_true", help="List available next stages")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Check conditions without advancing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    base_path = str(Path(__file__).resolve().parent.parent)
    config_path = str(Path(base_path) / "stageflow" / "config" / "stages.yaml")

    registry = StageRegistry(config_path)
    sm = StateMachine(registry, base_path)

    if args.list:
        current = sm.current_stage or "(not initialized)"
        available = registry.get_next_stages(current) if sm.current_stage else registry.stage_names
        result = {
            "current_stage": current,
            "available_next": available,
            "all_stages": registry.stage_names,
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Current stage: {current}")
            print(f"Available next stages: {available}")
            print(f"All stages: {registry.stage_names}")
        return 0

    if sm.current_stage is None:
        # Not initialized, need to pick first stage
        first_stage = registry.stage_names[0] if registry.stage_names else None
        if first_stage:
            print(f"State machine not initialized. Initializing at: {first_stage}")
            ok, msgs = sm.initialize(first_stage)
            for m in msgs:
                print(f"  {m}")
            return 0 if ok else 1
        else:
            print("ERROR: No stages configured.", file=sys.stderr)
            return 1

    if args.target is None:
        # Default: advance to first available next stage
        available = registry.get_next_stages(sm.current_stage)
        if not available:
            print(f"No transitions from current stage '{sm.current_stage}'", file=sys.stderr)
            return 1
        # Filter to forward-only transitions (exclude rollback paths)
        # Simple heuristic: first transition in order is the "main" path
        target = available[0]
    else:
        target = args.target

    if args.dry_run:
        ok, msgs = sm.can_transition_to(target)
        for m in msgs:
            print(m)
        print(f"\nResult: {'ALLOWED' if ok else 'BLOCKED'}")
        return 0 if ok else 1

    if args.force:
        ok, msgs = sm.force_transition_to(target)
    else:
        ok, msgs = sm.transition_to(target)

    for m in msgs:
        print(m)

    if ok:
        print(f"\nCurrent stage: {sm.current_stage}")
        # Show next steps
        available = registry.get_next_stages(sm.current_stage)
        if available:
            print(f"Next: {available}")
    else:
        print(f"\n[BLOCKED] Cannot transition {sm.current_stage} -> {target}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
