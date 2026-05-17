# StageFlow YAML Reference

## File Locations

New-style project config:

```text
<project>/.stageflow/config/stages.yaml
<project>/.stageflow/current_stage.json
```

Legacy projects may use:

```text
<project>/stageflow/config/stages.yaml
<project>/.claude/current_stage.json
```

`stageflow` discovers the project root by walking upward, similar to git. Prefer operating from the intended project directory.

## YAML Shape

```yaml
stages:
  - name: inspect
    tools:
      - WebSearch
    access:
      read:
        deny:
          - .env
          - secrets/**
      write:
        allow:
          - artifacts/runs/{{var.run_id}}/inspect/**
    meta:
      description: "Understand the task and gather context"
    on_enter:
      - python: "print('[StageFlow] entering inspect')"
    on_exit:
      - python: "print('[StageFlow] leaving inspect')"

transitions:
  - from: inspect
    to: plan
    description: "Context gathered"
    conditions:
      - file_exists: artifacts/runs/{{var.run_id}}/inspect/context.md
    on_fail: inspect
```

Required:

- `stages` list with unique `name` values.
- `transitions` list, unless deliberately creating isolated/manual stages.
- Every `from`, `to`, and `on_fail` must reference an existing stage.

Optional:

- `tools`
- `access`
- `meta.description`
- `on_enter`
- `on_exit`
- transition `description`
- transition `conditions`
- transition `on_fail`

## Terminal Semantics

Terminal is structural:

```text
stage with zero outgoing transitions = terminal
```

Names like `done`, `finish`, or `verify` are only conventions. A stage named `done` with an outgoing transition is not terminal. A stage named `verify` with no outgoing transition is terminal.

After reaching a terminal stage, `stageflow complete` sets `current_stage` to `null`, records `run_status: completed`, and records `final_stage`.

## Tool Policy

Common tool names:

```yaml
tools:
  - Read
  - Grep
  - Glob
  - WebSearch
  - WebFetch
  - Write
  - Edit
  - MultiEdit
  - NotebookEdit
  - Bash(git *)
  - Bash(python *)
  - Bash(pytest *)
  - Bash(npm test*)
```

Guidelines:

- Read-only stages usually need no write tools.
- `Read`, `Grep`, and `Glob` are normally default-open. Unless the user explicitly says the AI must not inspect something, ordinary project files should be readable.
- Stages with `Write`, `Edit`, `MultiEdit`, or `NotebookEdit` should also define `access.write`.
- Prefer command-scoped Bash patterns like `Bash(python *)`, not broad `Bash(*)`.
- Keep `tools: []` rare. In StageFlow semantics it can mean unrestricted tools, depending on the hook path. Prefer explicit tools.

## Access Policy

Do not generate broad read allowlists by default. Use read deny rules only for especially sensitive files:

```yaml
access:
  read:
    deny:
      - .env
      - secrets/**
      - "**/*.pem"
      - "**/*token*"
```

Only use `access.read.allow` when the user explicitly wants a stage to inspect a narrow subset of files.

Use write allow rules for write-capable stages:

```yaml
access:
  write:
    allow:
      - src/**
      - tests/**
      - artifacts/runs/{{var.run_id}}/fix/**
    deny:
      - .env
      - secrets/**
      - .stageflow/**
      - .claude/**
```

For planning/documentation stages, prefer artifact-only writes:

```yaml
access:
  write:
    allow:
      - artifacts/runs/{{var.run_id}}/plan/**
```

For bug-fix demos, make writes as narrow as possible:

```yaml
access:
  write:
    allow:
      - buggy_task.py
      - artifacts/runs/{{var.run_id}}/fix/**
    deny:
      - .env
      - secrets/**
      - .stageflow/**
```

## Conditions

Prefer conditions that prove the expected work happened:

```yaml
conditions:
  - file_exists: artifacts/runs/{{var.run_id}}/plan/task_plan.md
  - file_contains:
      path: artifacts/runs/{{var.run_id}}/plan/task_plan.md
      pattern: "- \\[ \\]"
```

Useful condition types:

- `always`
- `never`
- `file_exists`
- `file_not_exists`
- `file_contains`
- `file_not_contains`
- `glob_count`
- `shell_test`
- `python_expr`
- `git_status`
- `diff_contains`
- `json_field`
- `yaml_field`
- `all_of`
- `any_of`
- `not`

Avoid relying only on `always: true` unless the transition is intentionally manual.

## Recommended Templates

### Small Bug Fix Demo

```yaml
stages:
  - name: inspect
    tools:
      - WebSearch
    access:
      read:
        deny:
          - .env
          - secrets/**
    meta:
      description: "Read the task and identify the bug; no code writes"

  - name: fix
    tools:
      - WebSearch
      - Write
      - Edit
    access:
      read:
        deny:
          - .env
          - secrets/**
      write:
        allow:
          - buggy_task.py
          - artifacts/runs/{{var.run_id}}/fix/**
        deny:
          - .env
          - secrets/**
          - .stageflow/**
          - .claude/**
    meta:
      description: "Apply the minimal code fix"

  - name: verify
    tools:
      - WebSearch
      - Bash(python *)
      - Bash(pytest *)
    access:
      read:
        deny:
          - .env
          - secrets/**
    meta:
      description: "Run tests and complete when green"

transitions:
  - from: inspect
    to: fix
    conditions:
      - always: true

  - from: fix
    to: verify
    conditions:
      - shell_test:
          command: "python -m pytest test_buggy_task.py -q"
          op: exit_zero
    on_fail: fix
```

### Task Plan With Checklist Gate

```yaml
stages:
  - name: plan
    tools:
      - Read
      - Grep
      - Glob
      - Write
    access:
      write:
        allow:
          - artifacts/runs/{{var.run_id}}/plan/**
    meta:
      description: "Write a task plan with checklist items"

  - name: implement
    tools:
      - Read
      - Grep
      - Glob
      - Write
      - Edit
      - Bash(python *)
    access:
      write:
        allow:
          - src/**
          - tests/**
          - artifacts/runs/{{var.run_id}}/implement/**
        deny:
          - .stageflow/**
          - .claude/**
          - .env
          - secrets/**

  - name: verify
    tools:
      - Read
      - Grep
      - Glob
      - Bash(python *)
      - Bash(pytest *)

transitions:
  - from: plan
    to: implement
    conditions:
      - file_exists: artifacts/runs/{{var.run_id}}/plan/task_plan.md
      - file_contains:
          path: artifacts/runs/{{var.run_id}}/plan/task_plan.md
          pattern: "- \\[ \\]"
    on_fail: plan

  - from: implement
    to: verify
    conditions:
      - file_not_contains:
          path: artifacts/runs/{{var.run_id}}/plan/task_plan.md
          pattern: "- \\[ \\]"
    on_fail: implement
```

## Protected Files

Never ask an LLM to manually write runtime files:

```text
.stageflow/current_stage.json
.claude/current_stage.json
.stageflow/audit.jsonl
.stageflow/guard_violations.jsonl
```

Avoid direct LLM writes to config while a run is active:

```text
.stageflow/config/stages.yaml
stageflow/config/stages.yaml
```

Allowed config update moments:

- Before `stageflow start`
- After `stageflow complete`
- After `stageflow reset`
- Through `stageflow editor` save
- Through explicit user-approved migration/generate flow
