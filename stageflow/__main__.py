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
    stageflow graph               Generate Mermaid graph of the state machine
    stageflow list                List all stages and transitions
    stageflow check <target>      Dry-run: check conditions without advancing
    stageflow cond <type>         Test a condition type
"""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine
from stageflow.core.conditions import evaluate, list_conditions



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
    reg, sm = _get_sm()
    info = sm.status()
    if getattr(args, 'json', False):
        print(_json.dumps(info, indent=2, default=str))
        return
    stage = info["current_stage"] or "(not initialized)"
    print(f"  Current Stage : {stage}")
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
    if sm.current_stage is None:
        ok, msgs = sm.initialize(args.target)
    elif args.force:
        ok, msgs = sm.force_transition_to(args.target)
    else:
        ok, msgs = sm.transition_to(args.target)
    for m in msgs:
        print(f"  {m}")
    return 0 if ok else 1


def cmd_reset(args):
    reg, sm, root = _require_sm()
    if sm is None:
        return 1
    if getattr(args, 'clean_artifacts', False):
        sm.clean_run_artifacts()
    if args.hard:
        sm.reset()
        print("State machine fully reset.")
    else:
        target = args.stage or (reg.stage_names[0] if reg.stage_names else "pick")
        reuse_run = getattr(args, 'reuse_run', False)
        if not reuse_run:
            sm.reset()
        ok, msgs = sm.initialize(target, reuse_run=reuse_run)
        for m in msgs:
            print(f"  {m}")
        return 0 if ok else 1


def cmd_graph(args):
    """Generate Mermaid flowchart of all stages and transitions."""
    reg, sm = _get_sm()
    current_stage = sm.current_stage

    print("```mermaid")
    print("flowchart TD")
    print("    %% StageFlow State Machine")
    print("    %% Generated by: python -m stageflow graph")
    print()

    # Node definitions with styling
    for name in reg.stage_names:
        stage = reg.get_stage(name)
        desc = stage.description[:50] if stage.description else name
        # Style current stage differently
        if name == current_stage:
            print(f'    {name}["<b>{name}</b><br/>{desc}"]:::current')
        elif name == "done":
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
    reg, sm = _get_sm()
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
        return 0

    stageflow_dir.mkdir(parents=True, exist_ok=True)
    (stageflow_dir / "config").mkdir(parents=True, exist_ok=True)
    (target / "artifacts" / "runs").mkdir(parents=True, exist_ok=True)

    default_yaml = _get_default_stages_yaml()
    (stageflow_dir / "config" / "stages.yaml").write_text(default_yaml, encoding="utf-8")

    hook_settings = {
        "hooks": {
            "PreToolUse": [{
                "command": "stageflow hook",
                "matcher": "",
                "timeout": 10
            }]
        }
    }
    settings_path = target / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(_json.dumps(hook_settings, indent=2) + "\n", encoding="utf-8")

    print(f"Initialized StageFlow project at {target}")

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
    import os
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
    from stageflow.generator.llm_generator import WorkflowGenerator, CONDITION_REFERENCE
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

    p = sub.add_parser("reset", help="Reset state machine")
    p.add_argument("stage", nargs="?", help="Stage to reset to")
    p.add_argument("--hard", action="store_true")
    p.add_argument("--reuse-run", action="store_true", help="Keep existing run_id instead of creating a new one")
    p.add_argument("--clean-artifacts", action="store_true", help="Delete the current run's artifact directory before resetting")

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

    p = sub.add_parser("mcp", help="Start MCP server (stdio transport)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "status": cmd_status, "next": cmd_next, "back": cmd_back,
        "jump": cmd_jump, "reset": cmd_reset, "graph": cmd_graph,
        "list": cmd_list, "init": cmd_init, "start": cmd_start,
        "check": cmd_check,
        "cond": cmd_cond, "generate": cmd_generate, "mcp": cmd_mcp,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
