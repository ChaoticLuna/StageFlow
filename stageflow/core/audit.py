"""Audit logging system for StageFlow state machine.

Records all transitions, tool violations, condition evaluations, and stage
timing into a structured JSONL audit trail.

Usage:
    from stageflow.core.audit import AuditLogger
    logger = AuditLogger(base_path=".")
    logger.log_transition("pick", "analyze", True, ["file_exists: ok"])
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class AuditLogger:
    """Structured audit logger for StageFlow. Writes JSONL to .claude/audit.jsonl."""

    def __init__(self, base_path: str = ".", max_entries: int = 0):
        self.base_path = Path(base_path)
        self.log_path = self.base_path / ".claude" / "audit.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stage_timers: Dict[str, float] = {}
        self._max_entries = max_entries
        self._write_count = 0

    def _write(self, entry: dict):
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if self._max_entries > 0:
            self._write_count += 1
            if self._write_count >= self._max_entries * 2:
                self._truncate()

    def _truncate(self):
        if not self.log_path.exists():
            return
        lines = self.log_path.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) <= self._max_entries:
            self._write_count = len(lines)
            return
        keep = lines[-self._max_entries:]
        self.log_path.write_text("\n".join(keep) + "\n", encoding="utf-8")
        self._write_count = len(keep)

    def log_transition(self, from_stage: Optional[str], to_stage: str,
                       success: bool, messages: Optional[List[str]] = None,
                       forced: bool = False):
        """Log a stage transition attempt."""
        self._write({
            "event": "transition",
            "from": from_stage,
            "to": to_stage,
            "success": success,
            "forced": forced,
            "messages": messages or [],
        })

    def log_condition_check(self, transition: str, condition_type: str,
                            passed: bool, message: str):
        """Log a condition evaluation."""
        self._write({
            "event": "condition_check",
            "transition": transition,
            "condition_type": condition_type,
            "passed": passed,
            "message": message,
        })

    def log_tool_violation(self, tool_name: str, stage: str, reason: str):
        """Log a tool access violation."""
        self._write({
            "event": "tool_violation",
            "tool": tool_name,
            "stage": stage,
            "reason": reason,
        })

    def log_stage_enter(self, stage: str):
        """Log entering a stage and start timer."""
        self._stage_timers[stage] = time.time()
        self._write({
            "event": "stage_enter",
            "stage": stage,
        })

    def log_stage_exit(self, stage: str):
        """Log exiting a stage and record duration."""
        if stage in self._stage_timers:
            duration = time.time() - self._stage_timers.pop(stage)
            self._write({
                "event": "stage_exit",
                "stage": stage,
                "duration_seconds": round(duration, 3),
            })

    def log_hook_execution(self, stage: str, hook_type: str,
                           hook_kind: str, success: bool, message: str = ""):
        """Log a lifecycle hook execution."""
        self._write({
            "event": "hook_execution",
            "stage": stage,
            "hook_type": hook_type,
            "hook_kind": hook_kind,
            "success": success,
            "message": message,
        })

    def log_error(self, error_type: str, message: str, context: Optional[dict] = None):
        """Log a framework error."""
        self._write({
            "event": "error",
            "error_type": error_type,
            "message": message,
            "context": context or {},
        })

    def get_summary(self) -> dict:
        """Read the audit log and return a summary."""
        if not self.log_path.exists():
            return {"total_events": 0}

        events = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        transitions = [e for e in events if e.get("event") == "transition"]
        violations = [e for e in events if e.get("event") == "tool_violation"]
        stages_entered = [e for e in events if e.get("event") == "stage_enter"]
        stages_exited = [e for e in events if e.get("event") == "stage_exit"]

        # Calculate per-stage durations
        stage_durations: Dict[str, float] = {}
        for e in stages_exited:
            s = e.get("stage")
            d = e.get("duration_seconds", 0)
            if s:
                stage_durations[s] = stage_durations.get(s, 0) + d

        # Current stage time (not yet exited)
        current_timers = {}
        for s, start_time in self._stage_timers.items():
            current_timers[s] = time.time() - start_time

        return {
            "total_events": len(events),
            "transitions": len(transitions),
            "successful_transitions": len([t for t in transitions if t.get("success")]),
            "failed_transitions": len([t for t in transitions if not t.get("success")]),
            "tool_violations": len(violations),
            "stages_visited": len(stages_entered),
            "stage_durations": stage_durations,
            "current_stage_times": current_timers,
            "most_violated_stage": _mode([v.get("stage") for v in violations]),
        }


def _mode(lst):
    if not lst:
        return None
    from collections import Counter
    return Counter(lst).most_common(1)[0][0]
