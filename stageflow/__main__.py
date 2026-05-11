#!/usr/bin/env python3
"""StageFlow CLI — unified command-line interface for the state machine.

Usage:
    stageflow status              Show current stage and status
    stageflow next [target]       Advance to next stage
    stageflow back [target]       Go back to previous stage
    stageflow jump <target>       Jump to a specific stage
    stageflow reset [stage]       Reset to initial or specified stage
    stageflow graph               Generate Mermaid graph of the state machine
    stageflow list                List all stages and transitions
    stageflow init <stage>        Initialize state machine at a stage
    stageflow check <target>      Dry-run: check conditions without advancing
    stageflow cond <type>         Test a condition type
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stageflow.core.registry import StageRegistry
from stageflow.core.engine import StateMachine
from stageflow.core.conditions import evaluate, list_conditions


import json as _json

def cmd_status(args):
    reg = StageRegistry()
    sm = StateMachine(reg)
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
    reg = StageRegistry()
    sm = StateMachine(reg)
    if sm.current_stage is None:
        first = reg.stage_names[0] if reg.stage_names else "pick"
        ok, msgs = sm.initialize(first)
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
    reg = StageRegistry()
    sm = StateMachine(reg)
    if sm.current_stage is None:
        return cmd_init(args)
    incoming = reg.get_transitions_to(sm.current_stage)
    target = args.target or (incoming[0].from_stage if incoming else reg.stage_names[0])
    ok, msgs = sm.force_transition_to(target)
    for m in msgs:
        print(f"  {m}")
    return 0 if ok else 1


def cmd_jump(args):
    reg = StageRegistry()
    sm = StateMachine(reg)
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
    reg = StageRegistry()
    sm = StateMachine(reg)
    if args.hard:
        sm.reset()
        print("State machine fully reset.")
    else:
        target = args.stage or (reg.stage_names[0] if reg.stage_names else "pick")
        sm.reset()
        ok, msgs = sm.initialize(target)
        for m in msgs:
            print(f"  {m}")
        return 0 if ok else 1


def cmd_graph(args):
    """Generate Mermaid flowchart of all stages and transitions."""
    reg = StageRegistry()

    # Determine current stage from state file
    state_file = PROJECT_ROOT / ".claude" / "current_stage.json"
    import json
    current_stage = None
    if state_file.exists():
        try:
            current_stage = json.loads(state_file.read_text()).get("current_stage")
        except Exception:
            pass

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
    reg = StageRegistry()
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
    reg = StageRegistry()
    sm = StateMachine(reg)
    ok, msgs = sm.initialize(args.stage)
    for m in msgs:
        print(f"  {m}")
    return 0 if ok else 1


def cmd_check(args):
    reg = StageRegistry()
    sm = StateMachine(reg)
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

    p = sub.add_parser("graph", help="Generate Mermaid flowchart")

    p = sub.add_parser("list", help="List all stages and transitions")
    p.add_argument("--json", "-j", action="store_true", help="JSON output")

    p = sub.add_parser("init", help="Initialize state machine")
    p.add_argument("stage", help="Starting stage name")

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

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "status": cmd_status, "next": cmd_next, "back": cmd_back,
        "jump": cmd_jump, "reset": cmd_reset, "graph": cmd_graph,
        "list": cmd_list, "init": cmd_init, "check": cmd_check,
        "cond": cmd_cond, "generate": cmd_generate,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
