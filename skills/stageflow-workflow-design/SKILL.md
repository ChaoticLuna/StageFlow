---
name: stageflow-workflow-design
description: "Design, review, or generate StageFlow workflow YAML files, especially stages.yaml for stageflow generate/editor/init workflows. Use when Codex needs to create a guarded workflow from a task description, define stages/transitions/conditions, assign Claude Code tool permissions, write access.read/access.write policies, protect StageFlow runtime files from manual LLM writes, or review a StageFlow YAML for ambiguous semantics and unsafe permissions."
---

# StageFlow Workflow Design

## Quick Workflow

Use this skill when creating or reviewing a StageFlow workflow.

1. Identify the project task and choose 3-7 concrete stages.
2. Put the first runnable stage first in `stages`; `stageflow start` defaults to the first stage unless a stage is specified.
3. Make terminal status structural: a terminal stage is any stage with no outgoing transition. Do not rely on names like `done`.
4. Add transitions with real conditions. Avoid `always: true` except for demos or deliberately manual stages.
5. Keep read access open by default. Deny only especially sensitive files, or files the user explicitly says the AI must not inspect. Keep write access narrow and explicit.
6. Preserve StageFlow runtime files: never ask the LLM to manually write state, audit, guard log, or workflow config files during an active run.
7. Validate the generated YAML and, for demos, run a tiny end-to-end StageFlow workflow rather than only inspecting the file.

For exact YAML shape, permission policy, examples, and protected file rules, read `references/stageflow-yaml.md`.

## Generation Rules

Prefer workflows that produce artifacts under `artifacts/runs/{{var.run_id}}/<stage>/...` and gate transitions on those artifacts. This prevents stale files from a previous run from unlocking a new run.

Use `access.write.allow` whenever a stage has `Write`, `Edit`, `MultiEdit`, or `NotebookEdit`. A write-capable stage without `access.write` is intentionally broad and should be treated as unsafe unless the user explicitly asks for it.

Read tools are normally default-open in StageFlow. Unless the user explicitly says the AI must not inspect something, assume ordinary project files are readable. Do not generate broad `access.read.allow` whitelists by default; use `access.read.deny` only for especially sensitive files such as `.env`, `secrets/**`, credentials, private keys, tokens, and local state.

Bash and PowerShell are not controlled by `access.write`; they can write files through the shell. Do not grant broad shell patterns such as `Bash(*)`, `PowerShell(*)`, `Bash(git *)`, or `Bash(python *)` just for convenience. Prefer narrow command patterns such as `Bash(pytest *)`, `Bash(python -m pytest *)`, or `Bash(npm test*)` when a stage genuinely needs them.

StageFlow globally allows simple read-only shell commands such as `ls`, `cat`, `head`, `tail`, `pwd`, `which`, `where`, `git status`, `git diff`, and `git log`. Do not add YAML tool permissions merely for those commands. Commands with shell control syntax such as redirection, pipes, chaining, command substitution, or `;` are not treated as safe read-only.

Avoid `tools: []` unless the stage is deliberately unrestricted. In the hook path, an empty tool list can allow all tools; if paired with access policy it still skips the tool-name gate and only file-tool access checks remain. Prefer explicit safe tools even for terminal stages.

When a user asks for a small demo workflow, include at least one condition that can actually fail before the correct artifact exists, and then pass after the agent performs the intended work.

## Protected Files

Do not generate instructions that tell an LLM to manually write these files during normal workflow execution:

- `.stageflow/current_stage.json`
- `.claude/current_stage.json`
- `.stageflow/guard_violations.jsonl`
- `.claude/guard_violations.jsonl`
- `.claude/audit.jsonl`
- `.stageflow/audit.jsonl` if present in older or migrated projects
- `.stageflow/config/stages.yaml` during an active run
- `stageflow/config/stages.yaml` during an active legacy run

`stages.yaml` may be created or edited during setup, `stageflow init`, `stageflow generate`, or `stageflow editor` save flows. During an active run, change workflow config only after completing/resetting the run or after explicit user approval.
