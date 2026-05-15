"""WorkflowOrchestrator — parallel agent execution with asyncio, dependency graph,
shared variable store, and aggregate audit trail.

Usage:
    orch = WorkflowOrchestrator(registry, llm_call=my_llm)
    orch.add_task("t1", "Fix the login bug")
    orch.add_task("t2", "Add rate limiting", depends_on=["t1"])
    orch.add_task("t3", "Update docs", depends_on=["t1"])
    results = orch.run()  # t2 and t3 run in parallel after t1 completes
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from stageflow.core.registry import StageRegistry
from stageflow.agent.hybrid import HybridWorkflow


class TaskDef:
    """A task definition with optional dependencies."""

    def __init__(self, task_id: str, description: str, depends_on: list[str] | None = None):
        self.task_id = task_id
        self.description = description
        self.depends_on = depends_on or []

    def __repr__(self):
        deps = f" depends=[{', '.join(self.depends_on)}]" if self.depends_on else ""
        return f"TaskDef({self.task_id!r}{deps})"


class WorkflowOrchestrator:
    """Orchestrates parallel execution of multiple StageFlow workflows with
    dependency ordering and shared state.

    Independent tasks run concurrently via asyncio. Tasks with dependencies
    wait for all prerequisites to complete before starting.
    """

    def __init__(
        self,
        registry: StageRegistry,
        llm_call: Callable[[str], str],
        base_path: str = ".",
        max_workers: int = 4,
    ):
        self.registry = registry
        self.llm_call = llm_call
        self.base_path = Path(base_path).resolve()
        self.max_workers = max_workers
        self._tasks: dict[str, TaskDef] = {}
        self._shared_vars: dict[str, Any] = {}
        self._results: dict[str, dict] = {}
        self._audit: list[dict] = []

    # ── Task Registration ─────────────────────────────────────────────

    def add_task(self, task_id: str, description: str,
                 depends_on: list[str] | None = None):
        """Register a task. If depends_on is provided, those tasks must
        complete before this one starts."""
        self._tasks[task_id] = TaskDef(task_id, description, depends_on)

    def add_tasks(self, tasks: list[tuple[str, str, list[str]]]):
        """Register multiple tasks. Each tuple: (task_id, description, [depends_on])."""
        for task_id, desc, deps in tasks:
            self.add_task(task_id, desc, deps)

    def remove_task(self, task_id: str):
        self._tasks.pop(task_id, None)

    # ── Dependency Graph ──────────────────────────────────────────────

    def _validate_graph(self) -> tuple[bool, list[str]]:
        """Check for cycles and missing dependencies."""
        errors = []
        seen = set(self._tasks.keys())

        for t in self._tasks.values():
            for dep in t.depends_on:
                if dep not in seen:
                    errors.append(f"Task '{t.task_id}' depends on unknown task '{dep}'")

        if errors:
            return False, errors

        # Cycle detection via DFS
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {tid: WHITE for tid in self._tasks}

        def has_cycle(node: str, path: list[str]) -> bool:
            color[node] = GRAY
            for dep in self._tasks[node].depends_on:
                if color[dep] == GRAY:
                    errors.append(f"Cycle detected: {' -> '.join(path + [dep])}")
                    return True
                if color[dep] == WHITE and has_cycle(dep, path + [dep]):
                    return True
            color[node] = BLACK
            return False

        for tid in self._tasks:
            if color[tid] == WHITE:
                if has_cycle(tid, [tid]):
                    return False, errors

        return True, []

    def _ready_tasks(self, completed: set[str]) -> list[str]:
        """Return task ids whose dependencies are all in `completed`."""
        ready = []
        for tid, t in self._tasks.items():
            if tid not in completed:
                if all(d in completed for d in t.depends_on):
                    ready.append(tid)
        return ready

    # ── Execution ─────────────────────────────────────────────────────

    def run(self) -> dict:
        """Run all registered tasks respecting dependencies.

        Independent tasks run concurrently. Returns aggregate results.
        """
        ok, errors = self._validate_graph()
        if not ok:
            return {"success": False, "errors": errors, "results": {}}

        return asyncio.run(self._run_async())

    async def _run_async(self) -> dict:
        completed: set[str] = set()
        running: dict[str, asyncio.Future] = {}
        all_ids = set(self._tasks.keys())
        errors: list[str] = []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            loop = asyncio.get_running_loop()

            while len(completed) < len(all_ids):
                # Start ready tasks
                ready = self._ready_tasks(completed)
                for tid in ready:
                    if tid not in running:
                        task_def = self._tasks[tid]
                        running[tid] = loop.run_in_executor(
                            executor, self._execute_single_task, task_def
                        )

                if not running and len(completed) < len(all_ids):
                    remaining = [tid for tid in all_ids if tid not in completed]
                    pending = [tid for tid in remaining if tid not in running]
                    errors.append(
                        f"Deadlock: no tasks can proceed. "
                        f"Remaining: {remaining}, pending dependencies: {pending}"
                    )
                    break

                # Wait for at least one task to finish
                done, _ = await asyncio.wait(
                    list(running.values()),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for done_task in done:
                    tid, result = done_task.result()
                    completed.add(tid)
                    self._results[tid] = result
                    del running[tid]

        return {
            "success": len(completed) == len(all_ids),
            "completed": sorted(completed),
            "errors": errors if errors else None,
            "results": dict(self._results),
        }

    def _execute_single_task(self, task_def: TaskDef) -> tuple[str, dict]:
        """Execute one task through its own workflow (runs in thread pool)."""
        start_time = datetime.now(timezone.utc)

        base = self.base_path / f"agent_{task_def.task_id}"
        base.mkdir(parents=True, exist_ok=True)

        # Create a fresh registry clone for this task
        wf = HybridWorkflow(
            self.registry, llm_call=self.llm_call,
            base_path=str(base),
        )

        try:
            result = wf.run(description=task_def.description)
            self._shared_vars[task_def.task_id] = result

            end_time = datetime.now(timezone.utc)
            entry = {
                "task_id": task_def.task_id,
                "description": task_def.description,
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
                "duration_seconds": (end_time - start_time).total_seconds(),
                "success": result.get("completed", False),
                "final_stage": result.get("final_stage"),
            }
            self._audit.append(entry)
            return task_def.task_id, entry
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            entry = {
                "task_id": task_def.task_id,
                "started_at": start_time.isoformat(),
                "completed_at": end_time.isoformat(),
                "duration_seconds": (end_time - start_time).total_seconds(),
                "success": False,
                "error": str(e),
            }
            self._audit.append(entry)
            return task_def.task_id, entry

    # ── Shared State ──────────────────────────────────────────────────

    def set_shared(self, key: str, value: Any):
        self._shared_vars[key] = value

    def get_shared(self, key: str, default=None) -> Any:
        return self._shared_vars.get(key, default)

    def get_all_shared(self) -> dict:
        return dict(self._shared_vars)

    # ── Audit ─────────────────────────────────────────────────────────

    def get_audit_trail(self) -> list[dict]:
        """Return aggregate audit trail from all executed tasks."""
        return list(self._audit)

    def get_summary(self) -> dict:
        """Return a summary of all task results."""
        return {
            "total_tasks": len(self._tasks),
            "completed_tasks": len(self._results),
            "successful": sum(
                1 for r in self._results.values() if r.get("success")
            ),
            "failed": sum(
                1 for r in self._results.values() if not r.get("success")
            ),
            "tasks": {tid: r.get("success") for tid, r in self._results.items()},
            "shared_vars_keys": list(self._shared_vars.keys()),
        }

    def reset(self):
        self._shared_vars.clear()
        self._results.clear()
        self._audit.clear()
