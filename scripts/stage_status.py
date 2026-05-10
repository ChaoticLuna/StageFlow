#!/usr/bin/env python3
"""Show current stage status and state machine info.

Usage:
    python scripts/stage_status.py           # Human-readable status
    python scripts/stage_status.py --json    # JSON output
    python scripts/stage_status.py --short   # Just the stage name
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
    parser = argparse.ArgumentParser(description="StageFlow: show current status")
    parser.add_argument("--json", "-j", action="store_true")
    parser.add_argument("--short", "-s", action="store_true")
    args = parser.parse_args()

    base_path = str(Path(__file__).resolve().parent.parent)
    config_path = str(Path(base_path) / "stageflow" / "config" / "stages.yaml")

    registry = StageRegistry(config_path)
    sm = StateMachine(registry, base_path)

    info = sm.status()

    if args.short:
        print(info["current_stage"] or "(none)")
        return

    if args.json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return

    # Human-readable output
    stage = info["current_stage"] or "(not initialized)"
    print(f"StageFlow Status")
    print(f"{'=' * 50}")
    print(f"  Current Stage : {stage}")

    if info["stage_info"]:
        print(f"  Description   : {info['stage_info'].get('description', 'N/A')}")
        print(f"  Tools Allowed : {len(info['stage_info'].get('tools', []))} tools")
        if args.verbose:
            for t in info['stage_info'].get('tools', []):
                print(f"    - {t}")

    print(f"  Available Next: {info['available_next']}")
    print(f"  Total Transitions: {info['total_transitions']}")
    if info["retry_count"]:
        print(f"  Retry Counts  : {info['retry_count']}")
    if info["iterations"]:
        print(f"  Iterations    : {info['iterations']}")
    print(f"  State File    : {info['state_file']}")
    print(f"  Registered Conditions: {len(info['registered_conditions'])} types")

    if info["history"]:
        print(f"\n  Transition History:")
        for h in info["history"][-5:]:  # Last 5
            print(f"    {h.get('from','-')} -> {h.get('to','-')} @ {h.get('at','?')}")
            if h.get("reason"):
                print(f"      reason: {h['reason']}")


if __name__ == "__main__":
    main()
