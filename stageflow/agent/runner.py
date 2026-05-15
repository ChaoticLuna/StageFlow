"""AgentRunner — executes tasks from a FIX_PLAN.md-style markdown file through
the StageFlow pipeline (pick→analyze→plan→implement→verify→wrap_up→done).

Usage:
    from stageflow.agent.runner import AgentRunner
    runner = AgentRunner(".ralph/fix_plan.md")
    task = runner.get_next_task()
    if task:
        runner.start_task(task["id"])
        runner.advance_stage("analyze")
        # ... do work ...
        runner.complete_task(task["id"])
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class AgentRunner:
    """Orchestrates autonomous task execution through the StageFlow pipeline.

    Each task follows the pipeline: pick → analyze → plan → implement → verify → wrap_up → done.
    Progress is tracked in a progress JSON file.
    """

    PIPELINE = ["pick", "analyze", "plan", "implement", "verify", "wrap_up", "done"]

    def __init__(
        self,
        plan_file: str,
        progress_file: Optional[str] = None,
        base_path: str = ".",
        commit_callback=None,
    ):
        self.plan_file = Path(base_path) / plan_file
        self.base_path = Path(base_path).resolve()
        self.progress_file = Path(
            progress_file or ".claude/agent_progress.json"
        )
        if not self.progress_file.is_absolute():
            self.progress_file = self.base_path / self.progress_file
        self.commit_callback = commit_callback
        self._progress = self._load_progress()

    # ── Progress Persistence ──────────────────────────────────────────

    def _load_progress(self) -> dict:
        if self.progress_file.exists():
            try:
                return json.loads(self.progress_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "plan_file": str(self.plan_file),
            "current_task": None,
            "current_stage": None,
            "tasks": {},
            "history": [],
        }

    def _save_progress(self):
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        self.progress_file.write_text(
            json.dumps(self._progress, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    # ── Task Parsing ──────────────────────────────────────────────────

    def read_plan(self) -> str:
        """Read the plan file content."""
        if not self.plan_file.exists():
            raise FileNotFoundError(f"Plan file not found: {self.plan_file}")
        return self.plan_file.read_text(encoding="utf-8")

    def parse_tasks(self) -> list[dict]:
        """Parse all checkbox tasks from the plan file."""
        content = self.read_plan()
        tasks = []
        for match in re.finditer(
            r"^[\s]*- \[([ x!])\]\s+\*\*(task-\S+)\*\*:\s*(.+)$",
            content, re.MULTILINE,
        ):
            checked = match.group(1) == "x"
            tasks.append({
                "id": match.group(2),
                "description": match.group(3).strip(),
                "completed": checked,
                "line_start": content[:match.start()].count("\n"),
            })
        return tasks

    def get_next_task(self) -> Optional[dict]:
        """Return the first incomplete task, or None."""
        tasks = self.parse_tasks()
        for t in tasks:
            if not t["completed"]:
                return t
        return None

    def get_tasks(self) -> list[dict]:
        """Return all tasks with status."""
        return self.parse_tasks()

    # ── Task Lifecycle ────────────────────────────────────────────────

    def start_task(self, task_id: str) -> bool:
        """Start working on a task. Sets current_task and initializes pipeline."""
        tasks = self.parse_tasks()
        task = next((t for t in tasks if t["id"] == task_id), None)
        if task is None:
            return False
        if task["completed"]:
            return False

        now = datetime.now(timezone.utc).isoformat()
        self._progress["current_task"] = task_id
        self._progress["current_stage"] = self.PIPELINE[0]
        self._progress.setdefault("tasks", {}).setdefault(task_id, {})
        self._progress["tasks"][task_id].update({
            "status": "in_progress",
            "started_at": self._progress["tasks"][task_id].get("started_at") or now,
            "stages_completed": self._progress["tasks"][task_id].get("stages_completed", []),
        })
        self._progress.setdefault("history", []).append({
            "action": "start_task",
            "task_id": task_id,
            "at": now,
        })
        self._save_progress()
        return True

    def advance_stage(self, target: str) -> tuple[bool, list[str]]:
        """Advance to a specific stage in the pipeline for the current task."""
        task_id = self._progress.get("current_task")
        if task_id is None:
            return False, ["No active task. Call start_task() first."]

        current = self._progress.get("current_stage")
        if current is None:
            return False, ["No current stage set."]

        if target not in self.PIPELINE:
            return False, [f"Unknown stage '{target}'. Pipeline: {self.PIPELINE}"]

        now = datetime.now(timezone.utc).isoformat()
        self._progress.setdefault("tasks", {}).setdefault(task_id, {})

        self._progress["current_stage"] = target
        self._progress.setdefault("history", []).append({
            "action": "advance_stage",
            "task_id": task_id,
            "from": current,
            "to": target,
            "at": now,
        })
        self._save_progress()
        return True, [f"Task '{task_id}': {current} -> {target}"]

    def complete_task(self, task_id: str) -> bool:
        """Mark a task as complete: updates progress, marks [x] in plan, commits."""
        if not self.mark_task_completed_in_file(task_id):
            return False

        now = datetime.now(timezone.utc).isoformat()
        self._progress["current_task"] = None
        self._progress["current_stage"] = None
        self._progress.setdefault("tasks", {}).setdefault(task_id, {})
        self._progress["tasks"][task_id].update({
            "status": "completed",
            "completed_at": now,
        })
        self._progress.setdefault("history", []).append({
            "action": "complete_task",
            "task_id": task_id,
            "at": now,
        })
        self._save_progress()

        if self.commit_callback:
            self.commit_callback(task_id)

        return True

    def fail_task(self, task_id: str, reason: str = "") -> bool:
        """Mark a task as failed/blocked."""
        now = datetime.now(timezone.utc).isoformat()
        self._progress.setdefault("tasks", {}).setdefault(task_id, {})
        self._progress["tasks"][task_id].update({
            "status": "blocked",
            "failed_at": now,
            "failure_reason": reason,
        })
        self._progress.setdefault("history", []).append({
            "action": "fail_task",
            "task_id": task_id,
            "reason": reason,
            "at": now,
        })
        self._save_progress()
        return True

    # ── Plan File Updates ─────────────────────────────────────────────

    def mark_task_completed_in_file(self, task_id: str) -> bool:
        """Update the plan file: change `- [ ]` to `- [x]` for the given task."""
        content = self.read_plan()
        pattern = rf"^([\s]*- )\[ \](\s*\*\*{re.escape(task_id)}\*\*)"
        new_content, count = re.subn(pattern, r"\g<1>[x]\g<2>", content,
                                     flags=re.MULTILINE)
        if count == 0:
            return False
        self.plan_file.write_text(new_content, encoding="utf-8")
        return True

    def mark_task_blocked_in_file(self, task_id: str) -> bool:
        """Update the plan file: change `- [ ]` to `- [!]` for the given task."""
        content = self.read_plan()
        pattern = rf"^([\s]*- )\[ \](\s*\*\*{re.escape(task_id)}\*\*)"
        new_content, count = re.subn(pattern, r"\g<1>[!]\g<2>", content,
                                     flags=re.MULTILINE)
        if count == 0:
            return False
        self.plan_file.write_text(new_content, encoding="utf-8")
        return True

    # ── Status / Info ─────────────────────────────────────────────────

    @property
    def current_task(self) -> Optional[str]:
        return self._progress.get("current_task")

    @property
    def current_stage(self) -> Optional[str]:
        return self._progress.get("current_stage")

    def get_stages_completed(self, task_id: str) -> list[str]:
        return self._progress.get("tasks", {}).get(task_id, {}).get(
            "stages_completed", []
        )

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """Return progress data for a specific task."""
        tasks = self.parse_tasks()
        task = next((t for t in tasks if t["id"] == task_id), None)
        if task is None:
            return None
        progress_data = self._progress.get("tasks", {}).get(task_id, {})
        return {**task, **progress_data}

    def status(self) -> dict:
        """Return full status of the agent runner."""
        tasks = self.parse_tasks()
        completed = sum(1 for t in tasks if t["completed"])
        return {
            "plan_file": str(self.plan_file),
            "total_tasks": len(tasks),
            "completed_tasks": completed,
            "remaining_tasks": len(tasks) - completed,
            "current_task": self._progress.get("current_task"),
            "current_stage": self._progress.get("current_stage"),
            "tasks": {t["id"]: t["completed"] for t in tasks},
            "history": self._progress.get("history", []),
        }

    def reset(self):
        """Reset all progress."""
        self._progress = {
            "plan_file": str(self.plan_file),
            "current_task": None,
            "current_stage": None,
            "tasks": {},
            "history": [],
        }
        if self.progress_file.exists():
            self.progress_file.unlink()
