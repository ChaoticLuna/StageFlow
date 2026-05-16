"""FastAPI backend for StageFlow Editor.

Serves the React app in production and provides API endpoints for
YAML validation, transition checking, and condition type listing.

Usage:
    python editor/server.py                    # production (serves dist/)
    python editor/server.py --dev              # development (CORS for Vite)
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stageflow.core.schema import validate_stages_config
from stageflow.core.conditions import evaluate_all, list_conditions
from stageflow.core.audit import AuditLogger
from stageflow.core.engine import StateMachine
from stageflow.core.registry import StageRegistry

import yaml

WORKFLOWS_DIR = Path(__file__).parent / "workflows"
WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = str(Path(__file__).resolve().parent.parent / "stageflow" / "config" / "stages.yaml")

DIST_DIR = Path(__file__).parent / "dist"

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")


def _resolve_project_root(request: Request):
    """Get the project root bound to the app, or discover from cwd.

    When the app was created with create_app(project_root=...), that bound
    root is used. Otherwise falls back to discover_project() from cwd.
    """
    from stageflow.core.discovery import discover_project
    bound = getattr(request.app.state, 'project_root', None)
    if bound is not None:
        return bound
    return discover_project()


def _get_project_root_or_raise(request: Request):
    """Resolve project root or raise HTTPException(400) if not found."""
    root = _resolve_project_root(request)
    if root is None:
        raise HTTPException(
            status_code=400,
            detail="No StageFlow project found. Run 'stageflow init' first.",
        )
    return root


CONDITION_DEFS = [
    {"type": "always", "label": "Always", "description": "Always passes (no-op condition)", "params": []},
    {"type": "never", "label": "Never", "description": "Always fails with a reason", "params": [
        {"name": "reason", "label": "Reason", "kind": "text", "placeholder": "Why this transition is blocked"}
    ]},
    {"type": "file_exists", "label": "File Exists", "description": "Check that a file exists on disk", "params": [
        {"name": "path", "label": "File path", "kind": "text", "placeholder": "artifacts/runs/<run_id>/analyze/findings.md", "required": True}
    ]},
    {"type": "file_not_exists", "label": "File Not Exists", "description": "Check that a file does NOT exist", "params": [
        {"name": "path", "label": "File path", "kind": "text", "placeholder": "artifacts/runs/<run_id>/temp/draft.md", "required": True}
    ]},
    {"type": "file_contains", "label": "File Contains", "description": "Check that a file contains a pattern (regex)", "params": [
        {"name": "path", "label": "File path", "kind": "text", "placeholder": "artifacts/runs/<run_id>/analyze/findings.md", "required": True},
        {"name": "pattern", "label": "Pattern (regex)", "kind": "text", "placeholder": "## Root Cause", "required": True}
    ]},
    {"type": "file_not_contains", "label": "File Not Contains", "description": "Check that a file does NOT contain a pattern", "params": [
        {"name": "path", "label": "File path", "kind": "text", "placeholder": "src/main.py", "required": True},
        {"name": "pattern", "label": "Pattern (regex)", "kind": "text", "placeholder": "eval\\(", "required": True}
    ]},
    {"type": "json_field", "label": "JSON Field", "description": "Check a field in a JSON file", "params": [
        {"name": "path", "label": "JSON file path", "kind": "text", "required": True},
        {"name": "field", "label": "Field name", "kind": "text", "required": True},
        {"name": "op", "label": "Operator", "kind": "select", "options": ["exists", "not_empty", "equals", "not_equals", "gt", "lt", "in", "matches"], "default": "exists"},
        {"name": "value", "label": "Expected value", "kind": "text", "placeholder": "(for comparison ops)"}
    ]},
    {"type": "yaml_field", "label": "YAML Field", "description": "Check a field in a YAML file", "params": [
        {"name": "path", "label": "YAML file path", "kind": "text", "required": True},
        {"name": "field", "label": "Field name", "kind": "text", "required": True},
        {"name": "op", "label": "Operator", "kind": "select", "options": ["exists", "not_empty", "equals"], "default": "exists"},
        {"name": "value", "label": "Expected value", "kind": "text", "placeholder": "(only for equals)"}
    ]},
    {"type": "shell_test", "label": "Shell Test", "description": "Run a shell command and check the result", "params": [
        {"name": "command", "label": "Command", "kind": "text", "placeholder": "pytest -q", "required": True},
        {"name": "op", "label": "Check", "kind": "select", "options": ["exit_zero", "stdout_contains", "stdout_not_empty", "stdout_matches", "gt", "lt", "eq"], "default": "exit_zero"},
        {"name": "value", "label": "Expected value", "kind": "text", "placeholder": "(pattern, number, or string to compare)"},
        {"name": "stream", "label": "Stream", "kind": "select", "options": ["stdout", "stderr"], "default": "stdout"}
    ]},
    {"type": "python_expr", "label": "Python Expression", "description": "Evaluate a Python expression (must return bool)", "params": [
        {"name": "expr", "label": "Expression", "kind": "textarea", "placeholder": "1 + 1 == 2", "required": True}
    ]},
    {"type": "env_var", "label": "Environment Variable", "description": "Check an environment variable", "params": [
        {"name": "name", "label": "Variable name", "kind": "text", "placeholder": "CI", "required": True},
        {"name": "op", "label": "Operator", "kind": "select", "options": ["exists", "not_empty", "equals"], "default": "exists"},
        {"name": "value", "label": "Expected value", "kind": "text", "placeholder": "(only for equals)"}
    ]},
    {"type": "all_of", "label": "All Of (AND)", "description": "All sub-conditions must pass", "params": [
        {"name": "conditions", "label": "Sub-conditions", "kind": "json", "placeholder": "[{\"always\": true}]", "required": True}
    ]},
    {"type": "any_of", "label": "Any Of (OR)", "description": "At least one sub-condition must pass", "params": [
        {"name": "conditions", "label": "Sub-conditions", "kind": "json", "placeholder": "[{\"always\": true}]", "required": True}
    ]},
    {"type": "not", "label": "Not (Negate)", "description": "Negate a sub-condition", "params": [
        {"name": "condition", "label": "Condition to negate", "kind": "json", "placeholder": "{\"file_exists\": \"x.md\"}", "required": True}
    ]},
    {"type": "git_status", "label": "Git Status", "description": "Check the git working tree status", "params": [
        {"name": "op", "label": "Check", "kind": "select", "options": ["clean", "files_changed", "branch"], "default": "clean"},
        {"name": "value", "label": "Expected value", "kind": "text", "placeholder": "(branch name for branch, min count for files_changed)"}
    ]},
    {"type": "http_status", "label": "HTTP Status", "description": "Check an HTTP endpoint response", "params": [
        {"name": "url", "label": "URL", "kind": "text", "placeholder": "https://api.example.com/health", "required": True},
        {"name": "method", "label": "Method", "kind": "select", "options": ["GET", "POST", "HEAD"], "default": "GET"},
        {"name": "op", "label": "Check", "kind": "select", "options": ["status", "body_contains", "header_equals"], "default": "status"},
        {"name": "expected", "label": "Expected value", "kind": "text", "placeholder": "status code (200) or body pattern"}
    ]},
    {"type": "time_range", "label": "Time Range", "description": "Check current time is within a range", "params": [
        {"name": "after", "label": "After (HH:MM)", "kind": "text", "placeholder": "09:00", "required": True},
        {"name": "before", "label": "Before (HH:MM)", "kind": "text", "placeholder": "17:00", "required": True}
    ]},
    {"type": "compare_files", "label": "Compare Files", "description": "Compare two files", "params": [
        {"name": "path1", "label": "File 1 path", "kind": "text", "required": True},
        {"name": "path2", "label": "File 2 path", "kind": "text", "required": True},
        {"name": "op", "label": "Comparison", "kind": "select", "options": ["identical", "different"], "default": "identical"}
    ]},
    {"type": "json_schema", "label": "JSON Schema", "description": "Validate a JSON file against a JSON Schema", "params": [
        {"name": "path", "label": "Data file path", "kind": "text", "required": True},
        {"name": "schema_path", "label": "Schema file path", "kind": "text", "required": True}
    ]},
    {"type": "hash_file", "label": "Hash File", "description": "Check a file hash", "params": [
        {"name": "path", "label": "File path", "kind": "text", "required": True},
        {"name": "expected", "label": "Expected hash", "kind": "text", "required": True},
        {"name": "algo", "label": "Algorithm", "kind": "select", "options": ["sha256", "md5", "sha1"], "default": "sha256"}
    ]},
    {"type": "file_age", "label": "File Age", "description": "Check last modification time of a file", "params": [
        {"name": "path", "label": "File path", "kind": "text", "required": True},
        {"name": "max_age", "label": "Max age (seconds)", "kind": "number", "default": 300}
    ]},
    {"type": "file_size", "label": "File Size", "description": "Check the size of a file in bytes", "params": [
        {"name": "path", "label": "File path", "kind": "text", "required": True},
        {"name": "min", "label": "Min size (bytes)", "kind": "number", "placeholder": "1"},
        {"name": "max", "label": "Max size (bytes)", "kind": "number", "placeholder": "1048576"}
    ]},
    {"type": "glob_count", "label": "Glob Count", "description": "Count files matching a glob pattern", "params": [
        {"name": "pattern", "label": "Glob pattern", "kind": "text", "placeholder": "**/*.py", "required": True},
        {"name": "min", "label": "Min count", "kind": "number", "placeholder": "1"},
        {"name": "max", "label": "Max count", "kind": "number", "placeholder": "100"}
    ]},
    {"type": "retry", "label": "Retry", "description": "Retry a sub-condition with delay", "params": [
        {"name": "condition", "label": "Condition to retry", "kind": "json", "placeholder": "{\"file_exists\": \"x.md\"}", "required": True},
        {"name": "max_attempts", "label": "Max attempts", "kind": "number", "default": 12},
        {"name": "delay", "label": "Delay (seconds)", "kind": "number", "default": 5}
    ]},
    {"type": "command_exists", "label": "Command Exists", "description": "Check that a CLI command is available", "params": [
        {"name": "command", "label": "Command name", "kind": "text", "placeholder": "pytest", "required": True},
        {"name": "op", "label": "Check", "kind": "select", "options": ["exists", "version"], "default": "exists"}
    ]},
    {"type": "diff_contains", "label": "Diff Contains", "description": "Check git diff for a pattern (security gate)", "params": [
        {"name": "pattern", "label": "Pattern (regex)", "kind": "text", "placeholder": "eval\\(", "required": True},
        {"name": "op", "label": "Check", "kind": "select", "options": ["contains", "not_contains"], "default": "not_contains"}
    ]},
    {"type": "json_count", "label": "JSON Count", "description": "Count elements in a JSON array or object", "params": [
        {"name": "path", "label": "JSON file path", "kind": "text", "required": True},
        {"name": "field", "label": "Field path (optional)", "kind": "text", "placeholder": "results.items"},
        {"name": "min", "label": "Min count", "kind": "number", "placeholder": "1"},
        {"name": "max", "label": "Max count", "kind": "number", "placeholder": "100"}
    ]},
    # Runtime / system conditions
    {"type": "port_open", "label": "Port Open", "description": "Check if a TCP port is listening", "params": [
        {"name": "port", "label": "Port number", "kind": "number", "required": True},
        {"name": "host", "label": "Host", "kind": "text", "placeholder": "127.0.0.1", "default": "127.0.0.1"},
        {"name": "timeout", "label": "Timeout (s)", "kind": "number", "default": 2.0}
    ]},
    {"type": "process_running", "label": "Process Running", "description": "Check if a process is running by name", "params": [
        {"name": "name", "label": "Process name", "kind": "text", "placeholder": "python", "required": True}
    ]},
    {"type": "docker_ps", "label": "Docker Container", "description": "Check if a Docker container is running", "params": [
        {"name": "name", "label": "Container name", "kind": "text", "placeholder": "postgres", "required": True}
    ]},
]


app = FastAPI(title="StageFlow Editor API", version="1.0.0")


class ValidateRequest(BaseModel):
    yaml: str


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str]


class RunRequest(BaseModel):
    yaml: str
    from_stage: str
    to_stage: str


class RunResponse(BaseModel):
    can_transition: bool
    messages: list[str]


class AuditQueryParams(BaseModel):
    limit: int = 50
    event_type: Optional[str] = None


class GenerateRequest(BaseModel):
    description: str
    template: Optional[str] = None


class GenerateResponse(BaseModel):
    yaml: str
    success: bool
    messages: list[str]


class WorkflowSaveRequest(BaseModel):
    yaml: str


class WorkflowRunResponse(BaseModel):
    success: bool
    messages: list[str]
    current_stage: Optional[str] = None
    history: list[dict] = []


class WorkflowStatusResponse(BaseModel):
    name: str
    current_stage: Optional[str] = None
    stage_info: Optional[dict] = None
    available_next: list[str] = []
    total_transitions: int = 0
    history: list[dict]
    paused: bool
    variables: dict
    retry_count: dict
    iterations: dict


@app.get("/api/conditions")
def get_conditions():
    registered = [t for t in list_conditions() if not t.startswith("_")]
    missing = [t for t in registered if not any(c["type"] == t for c in CONDITION_DEFS)]
    return {
        "conditions": CONDITION_DEFS,
        "registered": registered,
        "count": len(CONDITION_DEFS),
        "missing_defs": missing,
    }


@app.post("/api/validate", response_model=ValidateResponse)
def validate_yaml(req: ValidateRequest):
    try:
        doc = yaml.safe_load(req.yaml)
    except yaml.YAMLError as e:
        return ValidateResponse(valid=False, errors=[f"YAML parse error: {e}"])

    if doc is None:
        return ValidateResponse(valid=False, errors=["YAML document is empty"])

    valid, errors = validate_stages_config(doc)
    return ValidateResponse(valid=valid, errors=errors)


@app.post("/api/run", response_model=RunResponse)
def run_check(req: RunRequest):
    try:
        doc = yaml.safe_load(req.yaml)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML parse error: {e}")

    if doc is None:
        raise HTTPException(status_code=400, detail="YAML document is empty")

    valid, errors = validate_stages_config(doc)
    if not valid:
        return RunResponse(can_transition=False, messages=errors)

    stages = doc.get("stages", [])
    transitions = doc.get("transitions", [])

    target_trans = None
    for t in transitions:
        if t.get("from") == req.from_stage and t.get("to") == req.to_stage:
            target_trans = t
            break

    if target_trans is None:
        return RunResponse(
            can_transition=False,
            messages=[f"No transition defined from '{req.from_stage}' to '{req.to_stage}'"]
        )

    conditions = target_trans.get("conditions", [])
    if not conditions:
        return RunResponse(can_transition=True, messages=["No conditions — always passes"])

    on_fail = target_trans.get("on_fail")

    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        try:
            passed, msgs = evaluate_all(conditions, base_path=tmpdir, cache_ttl=0)
        finally:
            os.chdir(Path(__file__).parent.parent)

    result_messages = list(msgs)
    if on_fail and not passed:
        result_messages.append(f"on_fail target: {on_fail}")

    return RunResponse(can_transition=passed, messages=result_messages)


# ═══════════════════════════════════════════════════════════════════════════
# Audit log endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/audit")
def get_audit_log(limit: int = 50, event_type: Optional[str] = None):
    """Get recent audit log entries, optionally filtered by event type."""
    logger = AuditLogger(str(Path.cwd()))
    if not logger.log_path.exists():
        return {"entries": [], "total": 0}

    entries = []
    with open(logger.log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type and entry.get("event") != event_type:
                continue
            entries.append(entry)

    total = len(entries)
    entries = entries[-limit:] if limit > 0 else entries
    return {"entries": entries, "total": total, "returned": len(entries)}


@app.get("/api/audit/summary")
def get_audit_summary():
    """Get audit log summary statistics."""
    logger = AuditLogger(str(Path.cwd()))
    return logger.get_summary()


# ═══════════════════════════════════════════════════════════════════════════
# Workflow generation endpoint
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/generate", response_model=GenerateResponse)
def generate_workflow(req: GenerateRequest):
    """Generate a stages.yaml workflow from a natural language description."""
    try:
        from stageflow.generator.llm_generator import WorkflowGenerator

        # Use mock LLM that returns template-based YAML
        def api_llm(prompt: str) -> str:
            from stageflow.generator.prompts import get_template
            tmpl_name = req.template or "GENERIC"
            tmpl = get_template(tmpl_name)
            desc = req.description
            return (
                f"Based on the description '{desc}', here is a workflow:\n\n"
                f"```yaml\n{tmpl.example_yaml}\n```"
            )

        gen = WorkflowGenerator(llm_call=api_llm)
        yaml_str, history = gen.generate(req.description, template=req.template)

        msg_strings = [
            h["raw_response"][:200] for h in history
            if isinstance(h, dict) and h.get("raw_response")
        ]

        return GenerateResponse(
            yaml=yaml_str or "",
            success=yaml_str is not None and len(yaml_str) > 0,
            messages=msg_strings,
        )
    except Exception as e:
        return GenerateResponse(yaml="", success=False, messages=[str(e)])


# ═══════════════════════════════════════════════════════════════════════════
# Workflow CRUD endpoints
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/workflows")
def list_workflows():
    """List all saved workflows."""
    workflows = []
    for f in WORKFLOWS_DIR.glob("*.yaml"):
        workflows.append({
            "name": f.stem,
            "path": str(f),
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return {"workflows": sorted(workflows, key=lambda w: w["name"])}


@app.get("/api/workflows/{name}")
def get_workflow(name: str):
    """Get a saved workflow's YAML content."""
    path = WORKFLOWS_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    content = path.read_text(encoding="utf-8")
    return {"name": name, "yaml": content}


@app.put("/api/workflows/{name}")
def save_workflow(name: str, req: WorkflowSaveRequest):
    """Save or update a workflow YAML."""
    # Validate YAML first
    try:
        doc = yaml.safe_load(req.yaml)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML parse error: {e}")
    if doc is None:
        raise HTTPException(status_code=400, detail="YAML document is empty")

    valid, errors = validate_stages_config(doc)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid config: {'; '.join(errors)}")

    path = WORKFLOWS_DIR / f"{name}.yaml"
    path.write_text(req.yaml, encoding="utf-8")
    # Invalidate cached engine + state so the new config takes effect
    _workflow_engines.pop(name, None)
    import shutil
    engine_dir = WORKFLOWS_DIR / name
    if engine_dir.exists():
        shutil.rmtree(engine_dir, ignore_errors=True)
    return {"name": name, "saved": True, "valid": True}


class ProjectSaveRequest(BaseModel):
    yaml: str


class ProjectSaveResponse(BaseModel):
    saved: bool
    config_path: str
    message: str


@app.post("/api/project/save-config", response_model=ProjectSaveResponse)
def save_project_config(req: ProjectSaveRequest, request: Request):
    """Save workflow YAML to the StageFlow project config.

    Uses the bound project root when the app was created with
    create_app(project_root=...), otherwise discovers from cwd.

    Save gate: allowed only when current_stage is null (after init, after
    complete, or after reset). Blocked while a run is active.
    """
    root = _get_project_root_or_raise(request)

    # Read current state
    current_stage = None
    run_status = None
    if root.state_path.exists():
        try:
            state_data = json.loads(root.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            state_data = {}
        current_stage = state_data.get("current_stage")
        run_status = state_data.get("run_status")

    if current_stage is not None:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Cannot save workflow config while a run is active "
                f"(current stage: '{current_stage}'). "
                f"Complete the run with 'stageflow complete' (terminal stage) "
                f"or use 'stageflow reset' to abandon it before editing."
            ),
        )

    # Validate YAML
    try:
        doc = yaml.safe_load(req.yaml)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML parse error: {e}")
    if doc is None:
        raise HTTPException(status_code=400, detail="YAML document is empty")

    valid, errors = validate_stages_config(doc)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid config: {'; '.join(errors)}")

    # Write to project config
    root.config_path.parent.mkdir(parents=True, exist_ok=True)
    root.config_path.write_text(req.yaml, encoding="utf-8")

    return ProjectSaveResponse(
        saved=True,
        config_path=str(root.config_path),
        message=(
            f"Config saved to {root.config_path}. "
            f"Current state: {'completed run' if run_status == 'completed' else 'no active run'}."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Project-scoped endpoints (config, status, save)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/project/config")
def get_project_config(request: Request):
    """Load the current project's stages.yaml and return config + metadata.

    Uses the bound project root when available; otherwise discovers from cwd.
    """
    root = _get_project_root_or_raise(request)

    if not root.config_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Project config not found at {root.config_path}. "
            f"Run 'stageflow init' first or check your project setup.",
        )

    yaml_content = root.config_path.read_text(encoding="utf-8")

    # Read current state for save eligibility
    current_stage = None
    run_status = None
    if root.state_path.exists():
        try:
            state = json.loads(root.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            state = {}
        current_stage = state.get("current_stage")
        run_status = state.get("run_status")

    save_allowed = current_stage is None

    return {
        "yaml": yaml_content,
        "config_path": str(root.config_path),
        "project_root": str(root.path),
        "marker_type": root.marker_type,
        "current_stage": current_stage,
        "run_status": run_status,
        "save_allowed": save_allowed,
    }


@app.get("/api/project/status")
def get_project_status(request: Request):
    """Return the current project run state.

    Uses the bound project root when available; otherwise discovers from cwd.
    """
    root = _get_project_root_or_raise(request)

    current_stage = None
    run_status = None
    final_stage = None
    completed_at = None
    run_id = None
    history = []
    variables = {}
    retry_count = {}
    iterations = {}

    if root.state_path.exists():
        try:
            state = json.loads(root.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            state = {}
        current_stage = state.get("current_stage")
        run_status = state.get("run_status")
        final_stage = state.get("final_stage")
        completed_at = state.get("completed_at")
        variables = state.get("variables", {})
        run_id = variables.get("run_id")
        history = state.get("history", [])
        retry_count = state.get("retry_count", {})
        iterations = state.get("iterations", {})

    save_allowed = current_stage is None

    return {
        "project_root": str(root.path),
        "marker_type": root.marker_type,
        "current_stage": current_stage,
        "run_status": run_status,
        "final_stage": final_stage,
        "completed_at": completed_at,
        "run_id": run_id,
        "save_allowed": save_allowed,
        "history_count": len(history),
        "variable_keys": list(variables.keys()),
        "retry_count": retry_count,
        "iterations": iterations,
        "state_path": str(root.state_path),
        "config_path": str(root.config_path),
    }


@app.delete("/api/workflows/{name}")
def delete_workflow(name: str):
    """Delete a saved workflow."""
    path = WORKFLOWS_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    path.unlink()
    # Clean up cached engine + state
    _workflow_engines.pop(name, None)
    import shutil
    engine_dir = WORKFLOWS_DIR / name
    if engine_dir.exists():
        shutil.rmtree(engine_dir, ignore_errors=True)
    return {"name": name, "deleted": True}


# ═══════════════════════════════════════════════════════════════════════════
# Workflow execution endpoints
# ═══════════════════════════════════════════════════════════════════════════

_workflow_engines: dict[str, StateMachine] = {}


def _get_engine(name: str) -> StateMachine:
    """Get or create a StateMachine for a workflow."""
    if name not in _workflow_engines:
        config_path = WORKFLOWS_DIR / f"{name}.yaml"
        if not config_path.exists():
            raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
        registry = StageRegistry(str(config_path))
        base = str(WORKFLOWS_DIR / name)
        Path(base).mkdir(parents=True, exist_ok=True)
        _workflow_engines[name] = StateMachine(registry, base)
    return _workflow_engines[name]


@app.post("/api/workflows/{name}/run", response_model=WorkflowRunResponse)
def run_workflow(name: str, target: Optional[str] = None):
    """Advance a workflow to the next stage or a specific target stage."""
    sm = _get_engine(name)

    if sm.current_stage is None:
        # Initialize at first stage
        registry = StageRegistry(str(WORKFLOWS_DIR / f"{name}.yaml"))
        start_stages = _find_start_stages(registry)
        if not start_stages:
            raise HTTPException(status_code=400, detail="No start stages found in workflow")
        start = start_stages[0]
        ok, msgs = sm.initialize(start)
        if not ok:
            return WorkflowRunResponse(success=False, messages=msgs, current_stage=sm.current_stage)

    if target:
        ok, msgs = sm.transition_to(target)
    else:
        # Advance to any available next stage
        available = sm.registry.get_next_stages(sm.current_stage) if sm.current_stage else []
        if not available:
            return WorkflowRunResponse(
                success=False,
                messages=[f"No available transitions from '{sm.current_stage}'"],
                current_stage=sm.current_stage,
            )
        target = available[0]
        ok, msgs = sm.transition_to(target)

    return WorkflowRunResponse(
        success=ok,
        messages=msgs,
        current_stage=sm.current_stage,
        history=sm.history,
    )


def _find_start_stages(registry: StageRegistry) -> list[str]:
    """Find stages with no incoming transitions."""
    all_targets = {t.to_stage for t in registry.all_transitions}
    return [s for s in registry.stage_names if s not in all_targets]


@app.get("/api/workflows/{name}/status", response_model=WorkflowStatusResponse)
def get_workflow_status(name: str):
    """Get the current execution status of a workflow."""
    sm = _get_engine(name)
    stage_info = None
    available_next = []
    if sm.current_stage:
        stage = sm.registry.get_stage(sm.current_stage)
        if stage:
            stage_info = stage.to_dict()
        available_next = sm.registry.get_next_stages(sm.current_stage)
    return WorkflowStatusResponse(
        name=name,
        current_stage=sm.current_stage,
        stage_info=stage_info,
        available_next=available_next,
        total_transitions=len(sm.history),
        history=sm.history,
        paused=sm.is_paused,
        variables=sm.get_all_vars(),
        retry_count=sm._state.get("retry_count", {}),
        iterations=sm._state.get("iterations", {}),
    )


@app.post("/api/workflows/{name}/pause")
def pause_workflow(name: str, reason: str = ""):
    """Pause a running workflow."""
    sm = _get_engine(name)
    sm.pause(reason)
    return {"name": name, "paused": True, "reason": reason}


@app.post("/api/workflows/{name}/resume")
def resume_workflow(name: str):
    """Resume a paused workflow."""
    sm = _get_engine(name)
    if not sm.is_paused:
        raise HTTPException(status_code=400, detail="Workflow is not paused")
    sm.resume()
    return {"name": name, "paused": False}


if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="static")

# Module-level app defaults to no bound project root (uses discovery from cwd)
app.state.project_root = None


def create_app(project_root=None):
    """Create a FastAPI editor app bound to a specific StageFlow project root.

    When *project_root* (a ProjectRoot from stageflow.core.discovery) is
    provided, all project-scoped API endpoints (config, status, save) use
    it directly instead of discovering from the request cwd.  Use this
    factory when the server is launched for a known project, e.g. from
    ``stageflow editor``.

    Returns a fully configured FastAPI with all editor routes registered.
    """
    from copy import deepcopy
    new_app = FastAPI(title="StageFlow Editor API", version="1.0.0")
    new_app.state.project_root = project_root
    for route in app.routes:
        new_app.routes.append(route)
    return new_app


def main():
    import argparse
    parser = argparse.ArgumentParser(description="StageFlow Editor Server")
    parser.add_argument("--dev", action="store_true", help="Enable CORS for Vite dev server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--project-root", default=None, help="Path to StageFlow project root")
    args = parser.parse_args()

    target_app = app
    if args.project_root:
        from stageflow.core.discovery import discover_project
        root = discover_project(args.project_root)
        if root is None:
            print(f"Error: '{args.project_root}' is not a StageFlow project.")
            sys.exit(1)
        target_app = create_app(project_root=root)

    if args.dev:
        target_app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    import uvicorn
    uvicorn.run(target_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
