"""State machine engine. Manages current stage, validates transitions,
enforces conditions, and persists state to disk.

State file: .claude/current_stage.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .conditions import evaluate_all, list_conditions
from .registry import StageRegistry


class StateMachine:
    """The central state machine that tracks current stage and orchestrates transitions.

    Usage:
        sm = StateMachine(registry)
        sm.current_stage  # "pick"
        ok, msgs = sm.can_transition_to("analyze")
        if ok:
            sm.transition_to("analyze")
    """

    STATE_FILE = ".claude/current_stage.json"

    def __init__(self, registry: StageRegistry, base_path: str = "."):
        self.registry = registry
        self.base_path = Path(base_path).resolve()
        self._state = self._load_state()
        from .audit import AuditLogger
        self.audit = AuditLogger(str(self.base_path))

    # ── State Persistence ───────────────────────────────────────────────

    @property
    def state_path(self) -> Path:
        return self.base_path / self.STATE_FILE

    def _load_state(self) -> dict:
        """Load current state from disk, or return defaults."""
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                bak_path = self.state_path.with_suffix(".json.bak")
                try:
                    bak_path.write_bytes(self.state_path.read_bytes())
                    self.audit.log_error(
                        "state_corruption",
                        f"State file corrupted, saved backup to {bak_path}",
                    )
                except Exception:
                    pass
        return {
            "current_stage": None,
            "history": [],
            "retry_count": {},
            "iterations": {},
            "variables": {},
            "paused": False,
            "paused_reason": "",
        }

    def _save_state(self):
        """Persist current state to disk."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    # ── Stage Access ────────────────────────────────────────────────────

    @property
    def current_stage(self) -> Optional[str]:
        return self._state.get("current_stage")

    @current_stage.setter
    def current_stage(self, value: Optional[str]):
        self._state["current_stage"] = value
        self._save_state()

    @property
    def history(self) -> List[dict]:
        return self._state.get("history", [])

    def get_retry_count(self, stage: str) -> int:
        return self._state.get("retry_count", {}).get(stage, 0)

    def get_iterations(self, stage: str) -> int:
        return self._state.get("iterations", {}).get(stage, 0)

    @property
    def is_paused(self) -> bool:
        return self._state.get("paused", False)

    def pause(self, reason: str = ""):
        """Pause the state machine. No transitions allowed while paused."""
        self._state["paused"] = True
        self._state["paused_reason"] = reason
        self._save_state()
        self.audit._write({"event": "pause", "reason": reason})

    def resume(self):
        """Resume the state machine from a paused state."""
        self._state["paused"] = False
        self._state["paused_reason"] = ""
        self._save_state()
        self.audit._write({"event": "resume"})

    # ── Variables (like env vars but scoped to the state machine) ───────

    def set_var(self, key: str, value: Any):
        """Set a scoped variable accessible to conditions via `var.xxx`."""
        self._state.setdefault("variables", {})[key] = value
        self._save_state()

    def get_var(self, key: str, default=None) -> Any:
        return self._state.get("variables", {}).get(key, default)

    def get_all_vars(self) -> dict:
        return dict(self._state.get("variables", {}))

    # ── Transition Logic ────────────────────────────────────────────────

    def can_transition_to(self, target: str) -> Tuple[bool, List[str]]:
        """Check if transition from current stage to target is allowed.
        Returns (allowed, messages)."""
        if self.is_paused:
            return False, [f"State machine is paused: {self._state.get('paused_reason', '')}"]
        current = self.current_stage
        if current is None:
            # No current stage means not initialized
            if target in self.registry.stage_names:
                return True, ["Initial stage: no conditions required"]
            return False, [f"Unknown stage: {target}"]

        # Find matching transition
        transitions = self.registry.get_transitions_from(current)
        matching = [t for t in transitions if t.to_stage == target]

        if not matching:
            available = self.registry.get_next_stages(current)
            return False, [
                f"No transition {current} -> {target}. "
                f"Available: {available or '(none)'}"
            ]

        # Evaluate conditions on all matching transitions
        # (usually just one, but handle multiple)
        vars_ = self.get_all_vars()
        all_msgs = []
        for trans in matching:
            ok, msgs = trans.evaluate(str(self.base_path), variables=vars_)
            all_msgs.extend(msgs)
            if ok:
                return True, msgs

        return False, all_msgs

    def transition_to(self, target: str, force: bool = False,
                      reason: str = "") -> Tuple[bool, List[str]]:
        """Attempt to transition to target stage. Returns (success, messages).

        If force=True, bypass condition checks.
        On failure, applies on_fail logic (rollback).
        Pass reason to annotate the transition in history and audit log.
        """
        if self.is_paused:
            return False, [f"Cannot transition: state machine is paused. Reason: {self._state.get('paused_reason', 'none')}"]
        current = self.current_stage

        # Check max_iterations on target stage
        if not force:
            target_stage = self.registry.get_stage(target)
            if target_stage and target_stage.max_iterations is not None:
                current_count = self._state.get("iterations", {}).get(target, 0)
                if current_count >= target_stage.max_iterations:
                    return False, [
                        f"[ITERATION_CAP] Stage '{target}' has reached "
                        f"max_iterations ({target_stage.max_iterations}). "
                        f"Current: {current_count}. Transition blocked."
                    ]

        if not force:
            ok, msgs = self.can_transition_to(target)
            if not ok:
                return self._handle_transition_failure(current, target, msgs)

        # Execute transition
        now = datetime.now(timezone.utc).isoformat()
        record = {"from": current, "to": target, "at": now}
        if reason:
            record["reason"] = reason

        # Run on_exit hooks for current stage
        if current and not force:
            self.audit.log_stage_exit(current)
            self._run_hooks(current, "on_exit")

        self._state.setdefault("history", []).append(record)
        self._state["current_stage"] = target

        # Run on_enter hooks for target stage
        if not force:
            self._run_hooks(target, "on_enter")
            self.audit.log_stage_enter(target)

        # Reset retry count only on successful condition-checked transitions
        if not force:
            self._state.setdefault("retry_count", {})[target] = 0
        # Bump iterations
        self._state.setdefault("iterations", {})[target] = \
            self._state.get("iterations", {}).get(target, 0) + 1

        self._save_state()
        msg = f"Transitioned: {current} -> {target}"
        if reason:
            msg += f" ({reason})"
        self.audit.log_transition(current, target, True, [msg], forced=force)
        return True, [msg]

    def _handle_transition_failure(self, current: str | None, target: str,
                                   msgs: List[str]) -> Tuple[bool, List[str]]:
        """Handle failed transition: increment retry count and optionally rollback.
        Hard-blocked conditions prevent rollback."""
        # Check for hard-blocked conditions — no rollback allowed
        has_hard_fail = any("HARD_FAIL" in m for m in msgs)

        # Increment retry count for current stage
        current_str = current or ""
        self._state.setdefault("retry_count", {})
        self._state["retry_count"][current_str] = self._state["retry_count"].get(current_str, 0) + 1
        self._save_state()

        # Check if we should rollback
        transitions = self.registry.get_transitions_from(current_str)
        matching = [t for t in transitions if t.to_stage == target]

        rollback_target = None
        if not has_hard_fail:
            for t in matching:
                if t.on_fail:
                    rollback_target = t.on_fail

        if rollback_target:
            self.current_stage = rollback_target
            now = datetime.now(timezone.utc).isoformat()
            self._state.setdefault("history", []).append({
                "from": current, "to": rollback_target, "at": now,
                "reason": f"transition to {target} failed, auto-rollback"
            })
            self._save_state()
            msgs.append(f"[ROLLBACK] Auto-rolled back to: {rollback_target}")
        elif has_hard_fail:
            msgs.append("[HARD_BLOCK] Transition blocked by hard condition; no rollback")

        return False, msgs

    def _run_hooks(self, stage_name: str, hook_type: str):
        """Execute lifecycle hooks (on_enter/on_exit) for a stage.

        Hooks are defined in the stage config under `on_enter` or `on_exit`.
        Each hook is a dict with a single key: {'shell': 'command'}, {'python': 'expr'},
        or {'webhook': {url, method, body, headers}}.
        Hook failures are logged but do not block the transition.
        """
        stage = self.registry.get_stage(stage_name)
        if stage is None:
            return
        hooks = stage.extra.get(hook_type, [])
        if not hooks:
            return
        for hook in hooks:
            hook_kind = next(iter(hook))
            hook_value = hook[hook_kind]
            success = True
            message = ""
            try:
                if hook_kind == "shell":
                    import subprocess
                    result = subprocess.run(
                        hook_value, shell=True, capture_output=True,
                        timeout=30, cwd=str(self.base_path)
                    )
                    if result.returncode != 0:
                        success = False
                        message = result.stderr.decode("utf-8", errors="replace").strip()[:200]
                elif hook_kind == "python":
                    exec(hook_value, {"base_path": str(self.base_path), "stage": stage_name, "sm": self})
                elif hook_kind == "webhook":
                    success, message = self._execute_webhook(hook_value)
            except Exception as e:
                success = False
                message = str(e)[:200]
            self.audit.log_hook_execution(stage_name, hook_type, hook_kind, success, message)

    def _interpolate_vars(self, value):
        """Recursively replace {{var.key}} in strings, dicts, and lists."""
        vars_ = self.get_all_vars()
        if isinstance(value, str):
            result = value
            for key, val in vars_.items():
                result = result.replace(f"{{{{var.{key}}}}}", str(val))
            return result
        if isinstance(value, dict):
            return {k: self._interpolate_vars(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._interpolate_vars(v) for v in value]
        return value

    def _execute_webhook(self, config: dict) -> tuple[bool, str]:
        """Execute a webhook HTTP request. Returns (success, message)."""
        import json
        import urllib.request
        import urllib.error

        url = self._interpolate_vars(config.get("url", ""))
        method = config.get("method", "POST").upper()
        body = self._interpolate_vars(config.get("body", {}))
        headers = self._interpolate_vars(config.get("headers", {}))
        timeout = config.get("timeout", 10)

        data = None
        if body and method in ("POST", "PUT", "PATCH"):
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        for key, val in headers.items():
            req.add_header(key, str(val))

        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            resp_body = resp.read().decode("utf-8", errors="replace")[:500]
            return True, f"HTTP {resp.status}: {resp_body}"
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:200]
            return False, f"HTTP {e.code}: {err_body}"
        except Exception as e:
            return False, str(e)[:200]

    def force_transition_to(self, target: str, reason: str = "") -> Tuple[bool, List[str]]:
        """Force a transition without condition checks."""
        return self.transition_to(target, force=True, reason=reason)

    def initialize(self, stage: str, reuse_run: bool = False) -> Tuple[bool, List[str]]:
        """Initialize the state machine at a starting stage.

        If reuse_run is True, preserves the existing run_id from the current
        state (if any). Otherwise generates a new UUID for each initialize call.
        """
        if self.is_paused:
            return False, [f"Cannot initialize: state machine is paused. Reason: {self._state.get('paused_reason', 'none')}"]
        if stage not in self.registry.stage_names:
            return False, [f"Unknown stage: {stage}"]
        import uuid
        existing_run_id = None
        if reuse_run:
            existing_run_id = self._state.get("variables", {}).get("run_id")
        run_id = existing_run_id or str(uuid.uuid4())
        self._state = {
            "current_stage": stage,
            "history": [],
            "retry_count": {stage: 0},
            "iterations": {stage: 1},
            "variables": {"run_id": run_id},
            "paused": False,
            "paused_reason": "",
        }
        self._save_state()
        self._run_hooks(stage, "on_enter")
        self.audit.log_stage_enter(stage)
        return True, [f"Initialized at stage: {stage}"]

    def reset(self):
        """Reset the state machine completely."""
        self._state = {
            "current_stage": None,
            "history": [],
            "retry_count": {},
            "iterations": {},
            "variables": {},
            "paused": False,
            "paused_reason": "",
        }
        if self.state_path.exists():
            self.state_path.unlink()

    def clean_run_artifacts(self):
        """Delete the current run's artifact directory only.

        Removes artifacts/runs/<run_id>/ if a run_id is set.
        Other run directories and the artifacts/ tree are left untouched.
        """
        import shutil
        run_id = self.get_var("run_id")
        if run_id:
            run_dir = self.base_path / "artifacts" / "runs" / run_id
            if run_dir.exists():
                shutil.rmtree(run_dir)

    # ── Tool Access Check ───────────────────────────────────────────────

    def is_tool_allowed(self, tool_name: str) -> Tuple[bool, str]:
        """Check if a tool is allowed in the current stage."""
        current = self.current_stage
        if current is None:
            return False, "No current stage set"

        stage = self.registry.get_stage(current)
        if stage is None:
            return False, f"Unknown stage: {current}"

        # Empty tools list = allow all
        if not stage.tools:
            return True, "All tools allowed in this stage"

        # Check exact match first, then prefix match (for Bash(command) etc.)
        if tool_name in stage.tools:
            return True, f"Tool '{tool_name}' allowed in stage '{current}'"

        for allowed in stage.tools:
            if tool_name.startswith(allowed.split("(")[0].strip()):
                # Check sub-constraint like "Bash(python *)"
                constraint = allowed
                if "(" in allowed:
                    tool_base = allowed.split("(")[0].strip()
                    constraint_args = allowed[allowed.index("(")+1:allowed.rindex(")")].strip()
                    if tool_name.startswith(tool_base + "("):
                        actual_args = tool_name[len(tool_base)+1:tool_name.rindex(")")].strip()
                        if self._match_tool_args(constraint_args, actual_args):
                            return True, f"Tool '{tool_name}' matches constraint '{allowed}'"

        return False, (f"Tool '{tool_name}' NOT allowed in stage '{current}'. "
                       f"Allowed: {stage.tools}")

    @staticmethod
    def _match_tool_args(constraint: str, actual: str) -> bool:
        """Match tool arguments against a pattern.
        E.g., constraint='python *' matches actual='python stageflow/core/foo.py'
              constraint='git *' matches actual='git status'
        """
        if constraint == "*":
            return True
        # Convert glob-like pattern to regex
        pattern = "^" + constraint.replace("*", ".*").replace("?", ".") + "$"
        import re
        return bool(re.match(pattern, actual))

    # ── Status / Info ───────────────────────────────────────────────────

    def status(self) -> dict:
        """Return full status dict for inspection."""
        current = self.current_stage
        stage_info = None
        if current:
            s = self.registry.get_stage(current)
            if s:
                stage_info = s.to_dict()

        return {
            "current_stage": current,
            "stage_info": stage_info,
            "history": self.history,
            "total_transitions": len(self.history),
            "retry_count": dict(self._state.get("retry_count", {})),
            "iterations": dict(self._state.get("iterations", {})),
            "variables": dict(self._state.get("variables", {})),
            "available_next": self.registry.get_next_stages(current) if current else [],
            "state_file": str(self.state_path),
            "registered_stages": self.registry.stage_names,
            "registered_conditions": list_conditions(),
        }

    def __repr__(self):
        return f"StateMachine(stage={self.current_stage!r}, transitions={len(self.history)})"
