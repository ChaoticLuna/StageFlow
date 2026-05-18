#!/usr/bin/env python3
"""StageFlow CLI — unified command-line interface for the state machine.

Usage:
    stageflow init [path]         Bootstrap a StageFlow project
    stageflow start [stage]       Begin a new run
    stageflow status              Show current stage and status
    stageflow next [target]       Advance to next stage
    stageflow back [target]       Go back to previous stage
    stageflow jump <target>       Jump to a specific stage
    stageflow reset [stage]       Reset to initial or specified stage
    stageflow editor              Start the visual workflow editor
    stageflow graph               Generate Mermaid graph of the state machine
    stageflow list                List all stages and transitions
    stageflow check <target>      Dry-run: check conditions without advancing
    stageflow cond <type>         Test a condition type
"""

from __future__ import annotations

import json as _json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine
from stageflow.core.conditions import evaluate, list_conditions
from stageflow.core.access_policy import AccessPolicy



def _get_sm():
    """Create a StateMachine using project discovery for correct config/state paths."""
    from stageflow.core.discovery import discover_project
    root = discover_project()
    if root is not None:
        reg = StageRegistry(str(root.config_path))
        rel_state = str(root.state_path.relative_to(root.path))
        return reg, StateMachine(reg, str(root.path), state_file=rel_state)
    else:
        reg = StageRegistry()
        return reg, StateMachine(reg)


def _require_sm():
    """Get StateMachine for a project-requiring command, or print error and return None."""
    from stageflow.core.discovery import discover_project
    root = discover_project()
    if root is None:
        print("Not a StageFlow project (or any parent directory).", file=sys.stderr)
        print("Run 'stageflow init' to create one here.", file=sys.stderr)
        return None, None, None
    reg = StageRegistry(str(root.config_path))
    rel_state = str(root.state_path.relative_to(root.path))
    sm = StateMachine(reg, str(root.path), state_file=rel_state)
    return reg, sm, root


def cmd_status(args):
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    info = sm.status()
    if getattr(args, 'json', False):
        print(_json.dumps(info, indent=2, default=str))
        return

    current = info["current_stage"]
    run_status = info.get("run_status")

    if run_status == "completed":
        print(f"  Run Status    : completed")
        print(f"  Final Stage   : {info.get('final_stage', 'N/A')}")
        print(f"  Completed At  : {info.get('completed_at', 'N/A')}")
        print(f"  Run ID        : {info.get('variables', {}).get('run_id', 'N/A')}")
        print(f"  History       : {info['total_transitions']} transitions")
        print()
        print("Use 'stageflow start' to begin a new run.")
        return 0

    if current is None:
        print("No active run. Use 'stageflow start' to begin a run.")
        return 0

    print(f"  Current Stage : {current}")
    if info["stage_info"]:
        print(f"  Description   : {info['stage_info'].get('description', 'N/A')}")
        tools = info['stage_info'].get('tools', [])
        if not tools:
            print(f"  Tools         : (all allowed)")
        else:
            print(f"  Tools         : {len(tools)} allowed")
        if hasattr(args, 'verbose') and args.verbose:
            for t in tools:
                print(f"    - {t}")
    print(f"  Available Next: {info['available_next']}")
    print(f"  History       : {info['total_transitions']} transitions")
    if info["retry_count"]:
        print(f"  Retry Counts  : {info['retry_count']}")
    if info["iterations"]:
        print(f"  Iterations    : {info['iterations']}")

    if hasattr(args, 'verbose') and args.verbose and info["current_stage"]:
        _print_verbose_details(reg, sm, info)


def _print_verbose_details(reg, sm, info):
    current = info["current_stage"]
    si = info.get("stage_info", {}) or {}

    # ── Transitions from current stage ──
    transitions = reg.get_transitions_from(current)
    if transitions:
        print(f"\n  ── Transitions from '{current}' ──")
        for t in transitions:
            print(f"  {t.from_stage} -> {t.to_stage}:")
            if t.description:
                print(f"    Description: {t.description}")
            if t.conditions:
                print(f"    Conditions ({len(t.conditions)}):")
                for c in t.conditions:
                    key = next(iter(c))
                    val = c[key]
                    if isinstance(val, dict):
                        flat = ", ".join(f"{k}={v}" for k, v in val.items())
                        print(f"      - {key}: {flat}")
                    else:
                        print(f"      - {key}: {val}")
            if t.on_fail:
                print(f"    On Fail: rollback to '{t.on_fail}'")
    else:
        print(f"\n  ── No transitions from '{current}' ──")

    # ── Lifecycle hooks ──
    for hook_type in ("on_enter", "on_exit"):
        hooks = si.get(hook_type, [])
        label = "On Enter" if hook_type == "on_enter" else "On Exit"
        if hooks:
            print(f"\n  ── {label} Hooks ({len(hooks)}) ──")
            for h in hooks:
                kind = next(iter(h))
                val = h[kind]
                if isinstance(val, dict):
                    from json import dumps
                    print(f"    - {kind}: {dumps(val, default=str)}")
                else:
                    print(f"    - {kind}: {val}")
        else:
            print(f"\n  ── {label} Hooks: (none) ──")

    # ── Variable dump ──
    variables = info.get("variables", {})
    if variables:
        print(f"\n  ── Variables ({len(variables)}) ──")
        for key, val in variables.items():
            print(f"    {key}: {val}")
    else:
        print(f"\n  ── Variables: (none) ──")


def cmd_next(args):
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    if sm.current_stage is None:
        print("No active run. Use 'stageflow start' to begin a run.", file=sys.stderr)
        return 1
    elif args.force:
        target = args.target or reg.get_next_stages(sm.current_stage)[0]
        ok, msgs = sm.force_transition_to(target)
    elif getattr(args, 'dry_run', False):
        target = args.target
        if target is None:
            available = reg.get_next_stages(sm.current_stage)
            if not available:
                print(f"No transitions from '{sm.current_stage}'", file=sys.stderr)
                print("Use 'stageflow complete' to close this terminal run.", file=sys.stderr)
                return 1
            target = available[0]
        ok, msgs = sm.can_transition_to(target)
        print(f"Dry-run: checking conditions for {sm.current_stage} -> {target}")
        for m in msgs:
            print(f"  {m}")
        print(f"\nResult: {'ALLOWED' if ok else 'BLOCKED'}")
        return 0 if ok else 1
    else:
        target = args.target
        if target is None:
            available = reg.get_next_stages(sm.current_stage)
            if not available:
                print(f"No transitions from '{sm.current_stage}'", file=sys.stderr)
                print("Use 'stageflow complete' to close this terminal run.", file=sys.stderr)
                return 1
            target = available[0]
        ok, msgs = sm.transition_to(target)
    for m in msgs:
        print(f"  {m}")
    return 0 if ok else 1


def cmd_back(args):
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    if sm.current_stage is None:
        print("No active run. Use 'stageflow start' to begin a run.", file=sys.stderr)
        return 1
    incoming = reg.get_transitions_to(sm.current_stage)
    target = args.target or (incoming[0].from_stage if incoming else reg.stage_names[0])
    ok, msgs = sm.force_transition_to(target)
    for m in msgs:
        print(f"  {m}")
    return 0 if ok else 1


def cmd_jump(args):
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    if args.force and not getattr(args, 'reason', None):
        print("Error: --force requires --reason '...' for audit trail.", file=sys.stderr)
        return 1
    if sm.current_stage is None:
        ok, msgs = sm.initialize(args.target)
    elif args.force:
        ok, msgs = sm.force_transition_to(args.target)
        sm.audit.log_transition(
            sm.current_stage, args.target, success=ok, forced=True,
            messages=[f"reason: {args.reason}"],
        )
    else:
        ok, msgs = sm.transition_to(args.target)
    for m in msgs:
        print(f"  {m}")
    return 0 if ok else 1


def cmd_reset(args):
    """Clear the active run. Use stageflow start to begin a new run."""
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    if getattr(args, 'clean_artifacts', False):
        sm.clean_run_artifacts()
    sm.reset()
    if getattr(args, 'hard', False):
        print("State fully reset. Use 'stageflow start' to begin a new run.")
    else:
        print("StageFlow state cleared. Use 'stageflow start' to begin a new run.")


def cmd_complete(args):
    """Complete the current run if the current stage is terminal."""
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    if sm.current_stage is None:
        print("No active run to complete.", file=sys.stderr)
        print("Use 'stageflow start' to begin a run.", file=sys.stderr)
        return 1
    ok, msgs = sm.complete()
    for m in msgs:
        print(f"  {m}")
    if ok:
        print(f"\nRun completed at stage '{sm._state['final_stage']}'.")
        print(f"State preserved — use 'stageflow start' to begin a new run.")
    return 0 if ok else 1


def cmd_editor(args):
    """Start the visual workflow editor bound to the current StageFlow project."""
    from stageflow.core.discovery import discover_project

    root = discover_project()
    if root is None:
        print("Not a StageFlow project (or any parent directory).", file=sys.stderr)
        print("Run 'stageflow init' to create one here.", file=sys.stderr)
        return 1

    # Only new-style projects (.stageflow/) are supported
    if root.marker_type != "new":
        print("Editor requires a new-style project (.stageflow/).", file=sys.stderr)
        print("Run 'stageflow migrate' to convert this project, then try again.", file=sys.stderr)
        return 1

    frontend_index = _editor_frontend_index()
    if not frontend_index.exists():
        print("Editor frontend is not built.", file=sys.stderr)
        print(f"Expected: {frontend_index}", file=sys.stderr)
        print("Build it from the StageFlow repository root:", file=sys.stderr)
        print("  cd editor", file=sys.stderr)
        print("  npm install", file=sys.stderr)
        print("  npm run build", file=sys.stderr)
        print("Or run:", file=sys.stderr)
        print("  python -m stageflow register --build-editor", file=sys.stderr)
        return 1

    from editor.server import create_app

    target_app = create_app(project_root=root)

    url = f"http://{args.host}:{args.port}"

    print(f"StageFlow Editor")
    print(f"  Project root: {root.path}")
    print(f"  Config:       {root.config_path}")
    print(f"  URL:          {url}")
    sys.stdout.flush()

    if not getattr(args, 'no_open', False):
        import webbrowser
        webbrowser.open(url)

    import uvicorn
    uvicorn.run(target_app, host=args.host, port=args.port)
    return 0


def cmd_graph(args):
    """Generate Mermaid flowchart of all stages and transitions."""
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    current_stage = sm.current_stage

    print("```mermaid")
    print("flowchart TD")
    print("    %% StageFlow State Machine")
    print("    %% Generated by: python -m stageflow graph")
    print()

    # Node definitions with styling
    terminal_stages = {
        name
        for name in reg.stage_names
        if not reg.get_transitions_from(name)
    }
    for name in reg.stage_names:
        stage = reg.get_stage(name)
        desc = stage.description[:50] if stage.description else name
        # Style current stage differently
        if name == current_stage:
            print(f'    {name}["<b>{name}</b><br/>{desc}"]:::current')
        elif name in terminal_stages:
            print(f'    {name}["{name}<br/>{desc}"]:::terminal')
        else:
            print(f'    {name}["{name}<br/>{desc}"]')

    print()

    # Transition edges with conditions
    for t in reg.all_transitions:
        label_parts = []
        for cond in t.conditions:
            ctype = next(iter(cond)) if cond else "?"
            label_parts.append(ctype)
        label = ", ".join(label_parts) if label_parts else ""
        if t.on_fail:
            label += f" [fail→{t.on_fail}]" if label else f"[fail→{t.on_fail}]"

        if t.to_stage == t.on_fail:
            # This IS a rollback edge
            print(f'    {t.from_stage} -->|"&#10060; retry/rollback: {label}"| {t.to_stage}')
        else:
            arrow = "==>" if not t.on_fail else "==>"
            fail_note = f" [on_fail: {t.on_fail}]" if t.on_fail else ""
            print(f'    {t.from_stage} {arrow}|"{label}{fail_note}"| {t.to_stage}')

    # Style definitions
    print()
    print("    classDef current fill:#4CAF50,stroke:#2E7D32,color:#fff,font-weight:bold")
    print("    classDef terminal fill:#607D8B,stroke:#37474F,color:#fff")
    print("    classDef default fill:#E3F2FD,stroke:#1565C0")
    print("```")

    # Legend
    print()
    print("Legend:")
    print("  **bold** = current stage")
    print("  ==> = forward transition with conditions")
    print("  --> = rollback/retry path")


def cmd_list(args):
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    if getattr(args, 'json', False):
        stages_list = []
        for name in reg.stage_names:
            stage = reg.get_stage(name)
            stages_list.append(stage.to_dict())
        transitions_list = [t.to_dict() for t in reg.all_transitions]
        ok, errs = reg.validate()
        print(_json.dumps({
            "stages": stages_list,
            "transitions": transitions_list,
            "valid": ok,
            "errors": errs,
        }, indent=2, default=str))
        return
    print(f"Stages ({len(reg.stage_names)}):")
    for name in reg.stage_names:
        stage = reg.get_stage(name)
        desc = stage.description[:80] if stage.description else "(no description)"
        n_tools = len(stage.tools)
        print(f"  {name:15s} | {n_tools:2d} tools | {desc}")
    print(f"\nTransitions ({len(reg.all_transitions)}):")
    for t in reg.all_transitions:
        n_cond = len(t.conditions)
        cond_str = ", ".join(next(iter(c)) for c in t.conditions) if t.conditions else "none"
        fail_str = f" [on_fail: {t.on_fail}]" if t.on_fail else ""
        print(f"  {t.from_stage:15s} -> {t.to_stage:15s} | {n_cond} cond(s): {cond_str}{fail_str}")
    ok, errs = reg.validate()
    if not ok:
        print(f"\nWARNING: Validation errors:")
        for e in errs:
            print(f"  - {e}")


STAGEFLOW_CLAUDE_HOOK_COMMAND = "stageflow hook"


def _stageflow_claude_pre_tool_hook() -> dict:
    """Return the current Claude Code hook shape.

    Claude Code's current settings schema nests command hooks under a
    per-event matcher entry.  Use "*" instead of "" for match-all because some
    real Windows/Claude Code setups have treated the empty matcher as inert.
    """
    return {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": STAGEFLOW_CLAUDE_HOOK_COMMAND,
                "timeout": 10,
            }
        ],
    }


def _entry_has_stageflow_hook(entry) -> bool:
    """Detect both old flat and current nested StageFlow hook entries."""
    if not isinstance(entry, dict):
        return False
    if entry.get("command") == STAGEFLOW_CLAUDE_HOOK_COMMAND:
        return True
    nested = entry.get("hooks")
    if isinstance(nested, list):
        return any(
            isinstance(h, dict) and h.get("command") == STAGEFLOW_CLAUDE_HOOK_COMMAND
            for h in nested
        )
    return False


def _merge_claude_settings(settings_path: Path) -> tuple[bool, str]:
    """Create or update Claude Code settings without deleting existing hooks."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            settings = _json.loads(settings_path.read_text(encoding="utf-8-sig"))
        except _json.JSONDecodeError:
            return False, (
                f"Refusing to overwrite invalid JSON in {settings_path}. "
                "Fix it manually or move it aside, then rerun stageflow init."
            )
        if not isinstance(settings, dict):
            return False, (
                f"Refusing to overwrite non-object JSON in {settings_path}. "
                "Claude settings must be a JSON object."
            )
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return False, f"Refusing to modify {settings_path}: 'hooks' must be a JSON object."

    pre_tool = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre_tool, list):
        return False, f"Refusing to modify {settings_path}: hooks.PreToolUse must be a list."

    canonical = _stageflow_claude_pre_tool_hook()
    new_pre_tool = []
    found = False
    changed = False
    for entry in pre_tool:
        if _entry_has_stageflow_hook(entry):
            if not found:
                new_pre_tool.append(canonical)
                found = True
            changed = True
        else:
            new_pre_tool.append(entry)
    if not found:
        new_pre_tool.append(canonical)
        changed = True

    if changed:
        hooks["PreToolUse"] = new_pre_tool
    settings_path.write_text(_json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return True, "Claude settings updated with StageFlow hook"


def cmd_init(args):
    """Bootstrap a StageFlow project in the target directory.

    Creates .stageflow/config/stages.yaml, .claude/settings.json,
    and artifacts/runs/. Does NOT start an active run unless --start is given.
    """
    target = Path(args.path).resolve() if args.path else Path.cwd().resolve()

    from stageflow.core.discovery import discover_project

    existing = discover_project(target)
    if existing is not None and existing.path != target:
        print(f"Already inside a StageFlow project at {existing.path}", file=sys.stderr)
        print("Nested projects must be created from outside the parent project.", file=sys.stderr)
        return 1

    stageflow_dir = target / ".stageflow"
    if stageflow_dir.is_dir() and not getattr(args, 'force', False):
        print(f"StageFlow project already initialized at {target}")
        (target / "artifacts" / "runs").mkdir(parents=True, exist_ok=True)
        settings_path = target / ".claude" / "settings.json"
        ok, message = _merge_claude_settings(settings_path)
        if not ok:
            print(message, file=sys.stderr)
            return 1
        print(message)
        return 0

    stageflow_dir.mkdir(parents=True, exist_ok=True)
    (stageflow_dir / "config").mkdir(parents=True, exist_ok=True)
    (target / "artifacts" / "runs").mkdir(parents=True, exist_ok=True)

    default_yaml = _get_default_stages_yaml()
    (stageflow_dir / "config" / "stages.yaml").write_text(default_yaml, encoding="utf-8")

    settings_path = target / ".claude" / "settings.json"
    ok, message = _merge_claude_settings(settings_path)
    if not ok:
        print(message, file=sys.stderr)
        return 1

    print(f"Initialized StageFlow project at {target}")
    print(message)

    if getattr(args, 'start', False):
        reg = StageRegistry(str(stageflow_dir / "config" / "stages.yaml"))
        sm = StateMachine(reg, str(target), state_file=".stageflow/current_stage.json")
        first_stage = reg.stage_names[0] if reg.stage_names else "pick"
        ok, msgs = sm.initialize(first_stage)
        for m in msgs:
            print(f"  {m}")
        if not ok:
            return 1

    return 0


def cmd_start(args):
    """Begin a new StageFlow run at the specified or first stage."""
    from stageflow.core.discovery import discover_project

    root = discover_project()
    if root is None:
        print("Not a StageFlow project (or any parent directory).", file=sys.stderr)
        print("Run 'stageflow init' to create one here.", file=sys.stderr)
        return 1

    reg = StageRegistry(str(root.config_path))
    rel_state = str(root.state_path.relative_to(root.path))
    sm = StateMachine(reg, str(root.path), state_file=rel_state)

    if sm.current_stage is not None:
        print(f"A run is already active (stage: {sm.current_stage}).", file=sys.stderr)
        print("Use 'stageflow next' to advance or 'stageflow reset' to start over.", file=sys.stderr)
        return 1

    target = args.stage if args.stage else (reg.stage_names[0] if reg.stage_names else None)
    if target is None:
        print("No stages defined in project config.", file=sys.stderr)
        return 1

    ok, msgs = sm.initialize(target)
    for m in msgs:
        print(f"  {m}")
    return 0 if ok else 1


def _get_default_stages_yaml() -> str:
    """Return the default stages.yaml content shipped with the package."""
    pkg_yaml = Path(__file__).resolve().parent / "config" / "stages.yaml"
    if pkg_yaml.exists():
        return pkg_yaml.read_text(encoding="utf-8")
    # Fallback: minimal built-in config
    return """# StageFlow Default Configuration
stages:
  - name: pick
    tools:
      - Read
      - Grep
      - Glob
      - WebSearch
      - WebFetch
      - Bash(git *)
      - TaskCreate
      - TaskUpdate
    meta:
      description: "Select an issue and gather context"

  - name: analyze
    tools:
      - Read
      - Grep
      - Glob
      - WebSearch
      - Bash(git *)
      - Bash(python *)
      - TaskCreate
      - TaskUpdate
    meta:
      description: "Analyze root cause and scope"

  - name: plan
    tools:
      - Read
      - Grep
      - Glob
      - Write
      - Edit
      - Bash(python *)
      - Bash(git *)
      - TaskCreate
      - TaskUpdate
    meta:
      description: "Design solution and write task plan"

  - name: implement
    tools:
      - Read
      - Edit
      - Write
      - Grep
      - Glob
      - Bash(git *)
      - Bash(python *)
      - TaskCreate
      - TaskUpdate
    meta:
      description: "Implement code changes"

  - name: verify
    tools:
      - Read
      - Grep
      - Glob
      - Bash(git *)
      - Bash(python *)
      - Bash(pytest *)
      - TaskCreate
      - TaskUpdate
    meta:
      description: "Run tests and verify"

  - name: document
    tools:
      - Read
      - Write
      - Edit
      - Grep
      - Glob
      - Bash(git *)
      - TaskCreate
      - TaskUpdate
    meta:
      description: "Write changelog and docs"

  - name: done
    tools: []
    meta:
      description: "Workflow complete"

transitions:
  - from: pick
    to: analyze
    conditions:
      - file_exists: artifacts/runs/{{var.run_id}}/pick/issue_context.md

  - from: analyze
    to: plan
    conditions:
      - file_exists: artifacts/runs/{{var.run_id}}/analyze/findings.md
      - file_contains:
          path: artifacts/runs/{{var.run_id}}/analyze/findings.md
          pattern: "## (根因|Root Cause|Analysis|分析)"
    on_fail: analyze

  - from: plan
    to: implement
    conditions:
      - file_exists: artifacts/runs/{{var.run_id}}/plan/task_plan.md
    on_fail: plan

  - from: implement
    to: verify
    conditions:
      - shell_test:
          command: "git diff --name-only HEAD"
          op: gt
          value: 0
    on_fail: implement

  - from: verify
    to: document
    conditions:
      - file_exists: artifacts/runs/{{var.run_id}}/verify/test_results.md
      - file_contains:
          path: artifacts/runs/{{var.run_id}}/verify/test_results.md
          pattern: "(PASS|通过|All tests passed)"
    on_fail: implement

  - from: verify
    to: implement
    conditions:
      - file_exists: artifacts/runs/{{var.run_id}}/verify/test_results.md
      - file_contains:
          path: artifacts/runs/{{var.run_id}}/verify/test_results.md
          pattern: "(FAIL|失败|Error)"

  - from: document
    to: done
    conditions:
      - always: true
"""


def cmd_check(args):
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    if sm.current_stage is None:
        if getattr(args, 'json', False):
            print(_json.dumps({"error": "Not initialized", "current_stage": None}))
        else:
            print("Not initialized.", file=sys.stderr)
        return 1
    ok, msgs = sm.can_transition_to(args.target)
    if getattr(args, 'json', False):
        print(_json.dumps({
            "current_stage": sm.current_stage,
            "target": args.target,
            "allowed": ok,
            "messages": msgs,
        }, indent=2, default=str))
        return 0 if ok else 1
    for m in msgs:
        print(m)
    print(f"\nResult: {'ALLOWED' if ok else 'BLOCKED'}")
    return 0 if ok else 1


def cmd_cond(args):
    """Test a condition type interactively or list all registered types."""
    if getattr(args, 'list', False):
        for c in list_conditions():
            print(c)
        return 0
    if not args.type:
        print("Usage: stageflow cond <type> [--params JSON] | stageflow cond --list", file=sys.stderr)
        return 1
    name = args.type
    params = {}
    if args.params:
        import json
        params = json.loads(args.params)
    if not isinstance(params, dict):
        params = {"value": params}
    params.setdefault("base_path", str(PROJECT_ROOT))
    ok, msg = evaluate(name, params)
    print(f"Condition '{name}': {'PASS' if ok else 'FAIL'}")
    print(f"  {msg}")


def cmd_generate(args):
    from stageflow.generator.llm_generator import WorkflowGenerator
    from stageflow.generator.prompts import get_template, list_templates

    if args.list_templates:
        for t in list_templates():
            print(f"  {t.name:20s} | {t.label}")
        return 0

    description = args.description
    template = args.template

    if args.prompt_only:
        gen = WorkflowGenerator()
        prompt = gen.build_prompt(description, template)
        print(prompt)
        return 0

    tmpl = None
    example = None
    if template:
        try:
            tmpl = get_template(template)
            example = tmpl.example_yaml
        except KeyError:
            print(f"Unknown template '{template}'. Using GENERIC.", file=sys.stderr)
            template = "GENERIC"
            tmpl = get_template(template)
            example = tmpl.example_yaml

    if example is None:
        try:
            tmpl = get_template("GENERIC")
            example = tmpl.example_yaml
        except KeyError:
            pass

    def mock_llm(prompt: str) -> str:
        if example:
            return f"```yaml\n{example}\n```"
        return f"```yaml\nstages:\n  - name: {description.replace(' ', '_').lower()[:30]}\n    tools: [Read, Grep]\ntransitions: []\n```"

    gen = WorkflowGenerator(llm_call=mock_llm, template=template)
    yaml_str, history = gen.generate(description, template=template)

    if yaml_str is None:
        print("Generation failed after retries:", file=sys.stderr)
        for entry in history:
            print(f"  Attempt {entry['attempt']}: {', '.join(entry['errors'])}", file=sys.stderr)
        return 1

    if args.validate:
        valid, errors = gen.validate(yaml_str)
        if not valid:
            print("Generated YAML has validation errors:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 1

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml_str, encoding="utf-8")
        print(f"Written to {out_path.resolve()}")
    else:
        print(yaml_str)

    return 0


def cmd_mcp(args):
    from .mcp_server import serve
    serve()
    return 0


def cmd_root(args):
    """Print the discovered StageFlow project root path."""
    import json as _json
    from stageflow.core.discovery import discover_project

    root = discover_project()
    if root is None:
        print("Not a StageFlow project. Run 'stageflow init' to create one.", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(_json.dumps({
            "root": str(root.path),
            "marker_type": root.marker_type,
            "config_path": str(root.config_path),
            "state_path": str(root.state_path),
            "artifacts_dir": str(root.artifacts_dir),
            "audit_dir": str(root.audit_dir),
        }))
        return 0

    print(f"Project root: {root.path}")
    print(f"Marker type:  {root.marker_type}")
    print(f"Config:       {root.config_path}")
    print(f"State:        {root.state_path}")
    print(f"Artifacts:    {root.artifacts_dir}")
    print(f"Audit:        {root.audit_dir}")
    return 0


def cmd_migrate(args):
    """Convert a legacy StageFlow project to new-style (.stageflow/)."""
    from stageflow.core.discovery import discover_project

    root = discover_project()
    if root is None:
        print("Not a StageFlow project (or any parent directory).", file=sys.stderr)
        print("Run 'stageflow init' to create one here.", file=sys.stderr)
        return 1

    if root.marker_type == "new":
        print(f"Already a new-style project at {root.path}")
        return 0

    target = Path(args.path).resolve() if getattr(args, 'path', None) else root.path

    stageflow_dir = target / ".stageflow"
    if stageflow_dir.is_dir() and not getattr(args, 'force', False):
        print(f".stageflow/ already exists at {target} — use --force to overwrite", file=sys.stderr)
        return 1

    stageflow_dir.mkdir(parents=True, exist_ok=True)
    (stageflow_dir / "config").mkdir(parents=True, exist_ok=True)

    if root.config_path.is_file():
        (stageflow_dir / "config" / "stages.yaml").write_text(
            root.config_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    if root.state_path.is_file():
        (stageflow_dir / "current_stage.json").write_text(
            root.state_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    audit_dir = stageflow_dir
    if root.audit_dir != stageflow_dir:
        old_violations = root.audit_dir / "guard_violations.jsonl"
        if old_violations.is_file():
            audit_dir.mkdir(parents=True, exist_ok=True)
            (audit_dir / "guard_violations.jsonl").write_text(
                old_violations.read_text(encoding="utf-8"), encoding="utf-8"
            )

    print(f"Migrated legacy project at {target} to new-style (.stageflow/)")
    print("Old files preserved — remove them manually when ready:")
    if root.config_path.is_file():
        print(f"  {root.config_path}")
    if root.state_path.is_file():
        print(f"  {root.state_path}")
    return 0


# ── Tool classification for access policy enforcement ──

# Non-file tools that never need access policy checks
_NON_FILE_ALWAYS_ALLOW = {
    "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TaskOutput",
    "AskUserQuestion",
}

# Read/search-family tools subject to access.read policy
_READ_TOOLS = {"Read", "Grep", "Glob"}

# Write-family tools subject to access.write policy
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

ALWAYS_ALLOW_COMMANDS = [
    "stageflow ",
    "stageflow.cmd ",
    "python -m stageflow",
    "python scripts/stage_next.py",
    "python scripts/stage_status.py",
    "python scripts/stage_reset.py",
    "python scripts/stage_jump.py",
    "python scripts/stage_back.py",
    "python -c",
]


def _strip_cd_prefix(cmd: str) -> str:
    import re
    return re.sub(
        r'^(cd\s+(/d\s+)?["\']?[A-Za-z]:[^;]*["\']?\s*;\s*)+',
        '', cmd.strip(), flags=re.IGNORECASE
    )


def _match_bash_pattern(pattern: str, cmd: str) -> bool:
    import re
    stripped = _strip_cd_prefix(cmd)
    regex = "^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return bool(re.search(regex, stripped))


def _extract_file_path(tool_name: str, tool_input: dict) -> str | None:
    """Extract the file or directory path from a tool's input dict."""
    if tool_name == "NotebookEdit":
        return tool_input.get("notebook_path") or tool_input.get("file_path")
    if tool_name in ("Grep", "Glob"):
        return tool_input.get("path")
    return tool_input.get("file_path")


def _log_hook_violation(root, tool_name: str, stage: str, reason: str):
    """Log an access violation to the project's guard violation log."""
    import json as _json
    from datetime import datetime, timezone

    violation_path = root.audit_dir / "guard_violations.jsonl"
    violation_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "tool": tool_name,
        "stage": stage,
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    with open(violation_path, "a", encoding="utf-8") as f:
        f.write(_json.dumps(entry) + "\n")


def _print_hook_decision(decision: str, reason: str) -> None:
    """Print Claude Code hook output with legacy fields for compatibility.

    Hook callers must return exit code 0 after printing this JSON. Claude Code
    only parses stdout JSON for exit code 0; exit code 1 is non-blocking.
    """
    permission_decision = "allow" if decision == "allow" else "deny"
    print(_json.dumps({
        "decision": decision,
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": permission_decision,
            "permissionDecisionReason": reason,
        },
    }))


def cmd_hook(args):
    """Claude Code PreToolUse hook entrypoint. Discovers project root from cwd
    and enforces stage tool allowlist and file access policy.
    Outputs allow/block JSON to stdout.
    """
    import json as _json

    try:
        input_data = _json.loads(sys.stdin.read())
    except (_json.JSONDecodeError, IOError):
        _print_hook_decision("allow", "hook input parse error - allowing")
        return 0

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Always allow operational stageflow commands via Bash/PowerShell
    if tool_name in ("Bash", "PowerShell"):
        cmd = tool_input.get("command", "")
        stripped = _strip_cd_prefix(cmd)
        for prefix in ALWAYS_ALLOW_COMMANDS:
            if stripped.startswith(prefix):
                _print_hook_decision("allow", f"Bash({cmd[:60]}) is always allowed")
                return 0

    # Discover project root (before always-allow so we can apply access policy)
    from stageflow.core.discovery import discover_project
    root = discover_project()
    if root is None:
        _print_hook_decision("allow", "not a StageFlow project - allowing")
        return 0

    # Load registry and state from discovered root
    try:
        rel_state = str(root.state_path.relative_to(root.path))
        reg = StageRegistry(str(root.config_path))
        sm = StateMachine(reg, str(root.path), state_file=rel_state)
    except Exception:
        _print_hook_decision("allow", "config load error - allowing")
        return 0

    current_stage = sm.current_stage
    if current_stage is None:
        _print_hook_decision("allow", "no stage set (bootstrap mode)")
        return 0

    stage = reg.get_stage(current_stage)
    if stage is None:
        _print_hook_decision("allow", f"stage '{current_stage}' not found - allowing")
        return 0

    # ── Non-file tools: always allowed, no access policy needed ──
    if tool_name in _NON_FILE_ALWAYS_ALLOW:
        _print_hook_decision("allow", f"{tool_name} is always allowed")
        return 0

    # ── Build access policy from stage extras ──
    access_config = stage.extra.get("access") if stage.extra else None
    policy = AccessPolicy(access_config)

    # ── Unrestricted stage with no access policy: allow everything ──
    allowed_tools = stage.tools
    if not allowed_tools and not policy.has_policy:
        _print_hook_decision("allow", f"stage '{current_stage}' has unrestricted tools")
        return 0

    # ── Tool allowlist check ──
    variables = sm.get_all_vars() if hasattr(sm, 'get_all_vars') else {}
    project_root_str = str(root.path)

    if allowed_tools:
        tool_ok = False

        # Default read tools pass the tool-name gate even if omitted from stage.tools
        if tool_name in _READ_TOOLS:
            tool_ok = True
        elif tool_name in allowed_tools:
            tool_ok = True
        elif tool_name in ("Bash", "PowerShell"):
            cmd = tool_input.get("command", "")
            for allowed in allowed_tools:
                if "(" in allowed and (allowed.startswith("Bash(") or allowed.startswith("PowerShell(")):
                    prefix = allowed.split("(")[0]
                    if tool_name == prefix:
                        start = allowed.index("(")
                        pattern = allowed[start + 1:-1].strip()
                        if _match_bash_pattern(pattern, cmd):
                            tool_ok = True
                            break

        if not tool_ok:
            reason = (f"Tool '{tool_name}' is NOT allowed in stage '{current_stage}'. "
                      f"Allowed tools: {allowed_tools}")
            _print_hook_decision("block", reason)
            _log_hook_violation(root, tool_name, current_stage, reason)
            return 0
    # else: empty allowed_tools with access policy → all tools allowed
    # but still check access policy below

    # ── File access policy check ──
    # Resolve relative paths against CWD before checking (the user's paths
    # are relative to wherever Claude Code is running, not project root).
    def _resolve_hook_path(path_str: str) -> str:
        p = Path(path_str)
        if not p.is_absolute():
            p = Path.cwd() / p
        return str(p)

    if tool_name in _READ_TOOLS:
        if policy.has_read_policy:
            path = _extract_file_path(tool_name, tool_input)
            if path is None:
                reason = (
                    f"access.read: '{tool_name}' requires a file path or "
                    f"search root when stage '{current_stage}' has a read policy"
                )
                _print_hook_decision("block", reason)
                _log_hook_violation(root, tool_name, current_stage, reason)
                return 0
            path = _resolve_hook_path(path)
            if tool_name in ("Grep", "Glob"):
                allowed, reason = policy.check_search(path, project_root_str, variables)
            else:
                allowed, reason = policy.check_read(path, project_root_str, variables)
            if not allowed:
                _print_hook_decision("block", reason)
                _log_hook_violation(root, tool_name, current_stage, reason)
                return 0

    elif tool_name in _WRITE_TOOLS:
        if policy.has_write_policy:
            path = _extract_file_path(tool_name, tool_input)
            if path is None:
                reason = (
                    f"access.write: '{tool_name}' requires a file_path when "
                    f"stage '{current_stage}' has a write policy"
                )
                _print_hook_decision("block", reason)
                _log_hook_violation(root, tool_name, current_stage, reason)
                return 0
            path = _resolve_hook_path(path)
            allowed, reason = policy.check_write(path, project_root_str, variables)
            if not allowed:
                _print_hook_decision("block", reason)
                _log_hook_violation(root, tool_name, current_stage, reason)
                return 0

    # All checks passed
    _print_hook_decision("allow", f"'{tool_name}' allowed in stage '{current_stage}'")
    return 0


def _default_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def _cmd_quote(path: str) -> str:
    return '"' + path.replace('"', '""') + '"'


def _bash_path(path: str) -> str:
    if os.name != "nt":
        return path
    p = Path(path)
    drive = p.drive.rstrip(":").lower()
    rest = p.as_posix().split(":", 1)[-1]
    return f"/{drive}{rest}" if drive else p.as_posix()


def _split_path(value: str | None) -> list[str]:
    if not value:
        return []
    return [part for part in value.split(os.pathsep) if part]


def _path_has(value: str | None, target: Path) -> bool:
    needle = str(target).rstrip("\\/").lower()
    return any(part.rstrip("\\/").lower() == needle for part in _split_path(value))


def _write_stageflow_wrappers(bin_dir: Path, python_executable: str) -> list[Path]:
    bin_dir.mkdir(parents=True, exist_ok=True)
    shell_path = bin_dir / "stageflow"
    cmd_path = bin_dir / "stageflow.cmd"

    shell_path.write_text(
        "#!/usr/bin/env bash\n"
        "# Wrapper for StageFlow CLI - generated by stageflow register.\n"
        f"exec {_bash_path(python_executable)!r} -m stageflow \"$@\"\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        shell_path.chmod(shell_path.stat().st_mode | 0o111)
    except OSError:
        pass

    paths = [shell_path]
    if os.name == "nt":
        cmd_path.write_text(
            "@ECHO off\r\n"
            "REM Wrapper for StageFlow CLI - generated by stageflow register.\r\n"
            f"{_cmd_quote(python_executable)} -m stageflow %*\r\n",
            encoding="utf-8",
            newline="\r\n",
        )
        paths.append(cmd_path)
    return paths


def _broadcast_env_change() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None,
        )
    except Exception:
        pass


def _register_windows_path(bin_dir: Path, machine: bool) -> tuple[int, str]:
    import winreg

    if machine:
        root = winreg.HKEY_LOCAL_MACHINE
        key_path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        scope = "system"
    else:
        root = winreg.HKEY_CURRENT_USER
        key_path = "Environment"
        scope = "user"

    try:
        with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                current, value_type = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current, value_type = "", winreg.REG_EXPAND_SZ
            if _path_has(current, bin_dir):
                return 0, f"{bin_dir} is already in {scope} PATH"
            updated = os.pathsep.join(_split_path(current) + [str(bin_dir)])
            winreg.SetValueEx(key, "Path", 0, value_type, updated)
    except PermissionError:
        return 1, (
            f"Permission denied writing {scope} PATH. "
            "Run from an elevated terminal or retry without --machine."
        )

    os.environ["PATH"] = os.pathsep.join(_split_path(os.environ.get("PATH")) + [str(bin_dir)])
    _broadcast_env_change()
    return 0, f"Added {bin_dir} to {scope} PATH"


def _register_path(bin_dir: Path, machine: bool) -> tuple[int, str]:
    if os.name == "nt":
        return _register_windows_path(bin_dir, machine)
    if machine:
        return 1, "--machine PATH registration is only supported on Windows"
    return 0, f"Add {bin_dir} to PATH in your shell profile if it is not already there"


def _editor_dir() -> Path:
    return PROJECT_ROOT / "editor"


def _editor_frontend_index() -> Path:
    return _editor_dir() / "dist" / "index.html"


def _build_editor_frontend() -> int:
    editor_dir = _editor_dir()
    package_json = editor_dir / "package.json"
    if not package_json.exists():
        print(f"Editor package.json not found: {package_json}", file=sys.stderr)
        return 1

    npm = shutil.which("npm")
    if npm is None:
        print("npm was not found on PATH; install Node.js/npm, then retry.", file=sys.stderr)
        return 1

    print(f"Building StageFlow editor frontend in {editor_dir}", flush=True)
    for command in (["install"], ["run", "build"]):
        printable = "npm " + " ".join(command)
        print(f"  {printable}", flush=True)
        result = subprocess.run([npm, *command], cwd=editor_dir)
        if result.returncode != 0:
            print(f"{printable} failed with exit code {result.returncode}", file=sys.stderr)
            return result.returncode

    index = _editor_frontend_index()
    if not index.exists():
        print(f"Editor build finished, but {index} was not created.", file=sys.stderr)
        return 1
    print(f"Editor frontend built: {index}", flush=True)
    return 0


def cmd_register(args):
    """Create Ralph-style wrapper commands for global StageFlow usage."""
    bin_dir = Path(args.bin_dir).expanduser() if args.bin_dir else _default_bin_dir()
    wrappers = _write_stageflow_wrappers(bin_dir, sys.executable)

    print("Registered StageFlow wrappers:", flush=True)
    print(f"  Python : {sys.executable}", flush=True)
    print(f"  Bin dir: {bin_dir}", flush=True)
    for path in wrappers:
        print(f"  - {path}", flush=True)

    if args.build_editor:
        rc = _build_editor_frontend()
        if rc != 0:
            return rc

    if args.no_path:
        print("PATH registration skipped (--no-path).")
        return 0

    rc, message = _register_path(bin_dir, args.machine)
    print(message)
    if rc == 0:
        print("Restart terminals so they inherit the updated PATH.")
    return rc


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="StageFlow CLI — Declarative State Machine Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m stageflow status
  python -m stageflow next
  python -m stageflow next implement --force
  python -m stageflow jump verify
  python -m stageflow graph
  python -m stageflow list
  python -m stageflow cond file_exists --params '{"path": "README.md"}'
        """,
    )
    sub = parser.add_subparsers(dest="command", help="Commands")

    p = sub.add_parser("status", help="Show current stage and status")
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--json", "-j", action="store_true", help="JSON output")

    p = sub.add_parser("next", help="Advance to next stage")
    p.add_argument("target", nargs="?", help="Target stage name")
    p.add_argument("--force", "-f", action="store_true")
    p.add_argument("--dry-run", "-n", action="store_true", help="Check conditions without executing")

    p = sub.add_parser("back", help="Go back to previous stage")
    p.add_argument("target", nargs="?", help="Target stage to go back to")

    p = sub.add_parser("jump", help="Jump to a specific stage")
    p.add_argument("target", help="Target stage name")
    p.add_argument("--force", "-f", action="store_true")
    p.add_argument("--reason", "-r", help="Reason for forced jump (required with --force)")

    p = sub.add_parser("reset", help="Reset the active run (clears state)")
    p.add_argument("--hard", action="store_true")
    p.add_argument("--clean-artifacts", action="store_true", help="Delete the current run's artifact directory before resetting")

    p = sub.add_parser("complete", help="Complete the current run (terminal stage only)")

    p = sub.add_parser("graph", help="Generate Mermaid flowchart")

    p = sub.add_parser("list", help="List all stages and transitions")
    p.add_argument("--json", "-j", action="store_true", help="JSON output")

    p = sub.add_parser("init", help="Bootstrap a StageFlow project")
    p.add_argument("path", nargs="?", help="Target directory (default: current directory)")
    p.add_argument("--force", "-f", action="store_true", help="Overwrite existing config")
    p.add_argument("--start", "-s", action="store_true", help="Start a run after initialization")

    p = sub.add_parser("start", help="Begin a new StageFlow run")
    p.add_argument("stage", nargs="?", help="Stage to start at (default: first stage in config)")

    p = sub.add_parser("check", help="Dry-run: check conditions for transition")
    p.add_argument("target", help="Target stage to check")
    p.add_argument("--json", "-j", action="store_true", help="JSON output")

    p = sub.add_parser("cond", help="Test a condition type")
    p.add_argument("type", nargs="?", help="Condition type name")
    p.add_argument("--params", help="JSON params for condition")
    p.add_argument("--list", "-l", action="store_true", help="List all registered condition types")

    p = sub.add_parser("generate", help="Generate stages.yaml from description")
    p.add_argument("description", nargs="?", help="Natural language workflow description")
    p.add_argument("--template", "-t", help="Template: GENERIC, CI_CD, CODE_REVIEW, DATA_PIPELINE")
    p.add_argument("--output", "-o", help="Write YAML to file instead of stdout")
    p.add_argument("--validate", action="store_true", help="Validate generated YAML before output")
    p.add_argument("--prompt-only", action="store_true", help="Print the LLM prompt instead of generating")
    p.add_argument("--list-templates", action="store_true", help="List available templates and exit")

    p = sub.add_parser("hook", help="Claude Code PreToolUse hook entrypoint")

    p = sub.add_parser("migrate", help="Convert legacy project to new-style (.stageflow/)")
    p.add_argument("path", nargs="?", help="Target directory (default: discovered project root)")
    p.add_argument("--force", "-f", action="store_true", help="Overwrite existing .stageflow/ directory")

    p = sub.add_parser("root", help="Print the discovered project root path")
    p.add_argument("--json", "-j", action="store_true", help="JSON output")

    p = sub.add_parser("editor", help="Start the visual workflow editor")
    p.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    p.add_argument("--no-open", action="store_true", help="Don't open browser automatically")

    p = sub.add_parser("register", help="Register stageflow as a global CLI command")
    p.add_argument("--bin-dir", help="Directory for wrapper scripts (default: ~/.local/bin)")
    p.add_argument("--machine", action="store_true", help="Add bin dir to system PATH on Windows")
    p.add_argument("--no-path", action="store_true", help="Create wrappers without modifying PATH")
    p.add_argument("--build-editor", action="store_true", help="Run npm install and npm run build for the visual editor")

    p = sub.add_parser("mcp", help="Start MCP server (stdio transport)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "status": cmd_status, "next": cmd_next, "back": cmd_back,
        "jump": cmd_jump, "reset": cmd_reset, "complete": cmd_complete, "graph": cmd_graph,
        "list": cmd_list, "init": cmd_init, "start": cmd_start,
        "check": cmd_check,
        "cond": cmd_cond, "generate": cmd_generate, "hook": cmd_hook, "migrate": cmd_migrate,
        "root": cmd_root, "editor": cmd_editor, "register": cmd_register, "mcp": cmd_mcp,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
