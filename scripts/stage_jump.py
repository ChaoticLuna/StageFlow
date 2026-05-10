#!/usr/bin/env python3
"""Jump to a specific stage (with condition checks by default).

Usage:
    python scripts/stage_jump.py <target>           # Jump with checks
    python scripts/stage_jump.py <target> --force   # Force jump
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine


def main():
    parser = argparse.ArgumentParser(description="StageFlow: jump to a stage")
    parser.add_argument("target", help="Target stage name")
    parser.add_argument("--force", "-f", action="store_true", help="Force jump, skip conditions")
    args = parser.parse_args()

    base_path = str(Path(__file__).resolve().parent.parent)
    config_path = str(Path(base_path) / "stageflow" / "config" / "stages.yaml")

    registry = StageRegistry(config_path)
    sm = StateMachine(registry, base_path)

    if sm.current_stage is None:
        ok, msgs = sm.initialize(args.target)
    elif args.force:
        ok, msgs = sm.force_transition_to(args.target)
    else:
        ok, msgs = sm.transition_to(args.target)

    for m in msgs:
        print(m)
    return 0 if ok else 1


if __name__ == "__main__":
    main()
