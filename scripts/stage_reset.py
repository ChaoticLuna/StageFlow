#!/usr/bin/env python3
"""Reset the state machine to a specific stage or clear entirely.

Usage:
    python scripts/stage_reset.py            # Reset to initial state
    python scripts/stage_reset.py <stage>    # Reset to specific stage
    python scripts/stage_reset.py --hard     # Completely wipe state
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine


def main():
    parser = argparse.ArgumentParser(description="StageFlow: reset state machine")
    parser.add_argument("stage", nargs="?", help="Reset to this stage (default: first stage)")
    parser.add_argument("--hard", action="store_true", help="Completely wipe state")
    parser.add_argument("--reuse-run", action="store_true", help="Keep existing run_id instead of creating a new one")
    parser.add_argument("--clean-artifacts", action="store_true", help="Delete the current run's artifact directory before resetting")
    args = parser.parse_args()

    base_path = str(Path(__file__).resolve().parent.parent)
    config_path = str(Path(base_path) / "stageflow" / "config" / "stages.yaml")

    registry = StageRegistry(config_path)
    sm = StateMachine(registry, base_path)

    if args.clean_artifacts:
        sm.clean_run_artifacts()
    if args.hard:
        sm.reset()
        print("State machine fully reset.")
        return

    target = args.stage
    if target is None:
        target = registry.stage_names[0] if registry.stage_names else "pick"

    if not args.reuse_run:
        sm.reset()
    ok, msgs = sm.initialize(target, reuse_run=args.reuse_run)
    for m in msgs:
        print(m)
    return 0 if ok else 1


if __name__ == "__main__":
    main()
