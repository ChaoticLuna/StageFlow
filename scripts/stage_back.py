#!/usr/bin/env python3
"""Go back to the previous stage using history.

Usage:
    python scripts/stage_back.py              # Go back to previous stage
    python scripts/stage_back.py <target>     # Go back to specific stage
    python scripts/stage_back.py --force      # Force back (skip conditions)
    python scripts/stage_back.py --history    # Show transition history
    python scripts/stage_back.py --dry-run    # Check conditions without moving
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
    parser = argparse.ArgumentParser(description="StageFlow: go back to previous stage")
    parser.add_argument("target", nargs="?", help="Target stage name (default: previous from history)")
    parser.add_argument("--force", "-f", action="store_true", help="Force transition, skip conditions")
    parser.add_argument("--history", action="store_true", help="Show transition history")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Check conditions without moving")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--steps", "-s", type=int, default=1, help="Number of steps to go back (default: 1)")
    args = parser.parse_args()

    base_path = str(Path(__file__).resolve().parent.parent)
    config_path = str(Path(base_path) / "stageflow" / "config" / "stages.yaml")

    registry = StageRegistry(config_path)
    sm = StateMachine(registry, base_path)

    if args.history:
        result = {
            "current_stage": sm.current_stage,
            "history": sm.history,
            "total_transitions": len(sm.history),
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Current stage: {sm.current_stage}")
            print(f"Total transitions: {len(sm.history)}")
            for i, h in enumerate(sm.history[-20:], 1):
                print(f"  {i}. {h.get('from', '?')} -> {h.get('to', '?')}  ({h.get('at', '?')})")
        return 0

    if sm.current_stage is None:
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
        history = sm.history
        target = None
        steps_back = args.steps
        # Walk history backwards to find distinct source stages
        for i in range(len(history) - 1, -1, -1):
            h = history[i]
            if h.get("to") == sm.current_stage:
                steps_back -= 1
                if steps_back == 0:
                    target = h.get("from")
                    break

        if target is None:
            # Fallback: find the last entry where current stage was the target
            for h in reversed(history):
                if h.get("to") == sm.current_stage:
                    target = h.get("from")
                    break

        if target is None:
            print("No previous stage found in history.", file=sys.stderr)
            if args.json:
                print(json.dumps({"error": "No previous stage found"}))
            return 1
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
        for m in msgs:
            print(m)
    else:
        # Try normal transition first
        ok, msgs = sm.transition_to(target)
        for m in msgs:
            print(m)
        if not ok:
            # Fallback: try force transition for back-navigation
            print("Normal transition blocked, trying force transition...")
            ok, msgs = sm.force_transition_to(target)
            for m in msgs:
                print(m)

    if ok:
        print(f"\nBack to stage: {sm.current_stage}")
        if args.verbose:
            available = registry.get_next_stages(sm.current_stage)
            if available:
                print(f"Available next: {available}")
    else:
        print(f"\n[BLOCKED] Cannot go back {sm.current_stage} -> {target}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
