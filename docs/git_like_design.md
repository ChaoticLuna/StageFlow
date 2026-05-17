# StageFlow Git-like CLI — Design & Requirements

> **Status**: Draft — Phase 29 design document
> **Goal**: Make StageFlow usable like Git from any working directory after a single `pip install`

---

## 1. Core Principle

StageFlow must behave like Git: one global install, many local projects. After `pip install -e D:\Tool\stageflow`, the user can run `stageflow init` in any directory to bootstrap a project, then `stageflow status`, `stageflow next`, `stageflow reset`, etc. from anywhere inside that project tree. All state, config, and artifacts belong to the discovered project root — never to the package source checkout.

---

## 2. Project Marker Discovery

### 2.1 Discovery Algorithm

Starting at `Path.cwd()`, walk upward directory-by-directory until a marker is found. Check markers in this priority order **at each directory level**:

| Priority | Marker | Project Type | Config Path | State Path |
|----------|--------|-------------|-------------|------------|
| 1 (highest) | `.stageflow/` directory exists | **new-style** | `<root>/.stageflow/config/stages.yaml` | `<root>/.stageflow/current_stage.json` |
| 2 | `stageflow/config/stages.yaml` file exists | **legacy** | `<root>/stageflow/config/stages.yaml` | `<root>/.claude/current_stage.json` |
| 3 (lowest) | `.claude/current_stage.json` file exists | **legacy** (state-only) | `<root>/stageflow/config/stages.yaml` | `<root>/.claude/current_stage.json` |

Stop at the first match. If no marker is found before hitting the filesystem root (or a Windows drive root), the command is running **outside any project**.

### 2.2 Return Value

The discovery function returns a `ProjectRoot` namedtuple:

```python
ProjectRoot(
    path=Path("/home/user/my-project"),
    marker_type="new" | "legacy" | "legacy_state_only",
    config_path=Path("/home/user/my-project/.stageflow/config/stages.yaml"),
    state_path=Path("/home/user/my-project/.stageflow/current_stage.json"),
    artifacts_dir=Path("/home/user/my-project/artifacts/runs"),
    audit_dir=Path("/home/user/my-project/.stageflow"),
)
```

### 2.3 Edge Cases

- **Symlinks**: Resolve `Path.cwd()` before walking. Do not resolve each parent — only the cwd.
- **Windows drive roots**: `C:\` is the stop point (`path.parent == path`).
- **Nested projects**: Nearest ancestor wins. A project inside another project shadows the parent.
- **No project found**: Return `None` or raise `ProjectNotFoundError`.

---

## 3. `stageflow init` — Project Bootstrap

### 3.1 Syntax

```
stageflow init              # Bootstrap current directory
stageflow init [path]       # Bootstrap specified directory
stageflow init --force      # Overwrite config if already initialized
```

### 3.2 Behavior

**On first run** (no marker found at or above cwd):

1. Create `.stageflow/` directory at the target path
2. Write `.stageflow/config/stages.yaml` — a copy of the default 10-stage pipeline config, with all artifact paths using `{{var.run_id}}` templates
3. Do NOT create `.stageflow/current_stage.json` — project has no active run until `stageflow reset <stage>` is called
4. Write `.claude/settings.json` — PreToolUse hook config pointing to `stageflow hook` global command
5. Create `artifacts/runs/` directory
6. Print: `Initialized StageFlow project at <path>`

**On re-run** (`.stageflow/` already exists at target):

- Print: `StageFlow project already initialized at <path>`
- Exit 0 (idempotent)

**On re-run with `--force`**:

- Overwrite `.stageflow/config/stages.yaml` with default config
- Do NOT touch `.stageflow/current_stage.json` (preserve active run state)
- Overwrite `.claude/settings.json`

**Inside an existing project** (parent directory has a marker):

- Print: `Already inside a StageFlow project at <parent_root>`
- Exit 1
- Rationale: nested projects are valid but must be explicitly created from outside the parent

### 3.3 Rejected Syntax

`stageflow init pick` (and any `init <stage>`) is rejected with:

```
Error: 'stageflow init' creates a new project. To start a workflow run, use:
  stageflow reset pick
```

This is a breaking change from the old `stageflow init <stage>` behavior. The old syntax is NOT supported for new-style projects.

---

## 4. Command Classification

### 4.1 Commands Requiring a Project

These commands discover the project root and fail if outside a project:

| Command | Behavior |
|---------|----------|
| `stageflow status` | Show current stage in discovered project |
| `stageflow next [target]` | Advance stage in discovered project |
| `stageflow back [target]` | Roll back stage in discovered project |
| `stageflow jump <target>` | Jump to stage in discovered project |
| `stageflow reset [stage]` | Reset stage in discovered project |
| `stageflow graph` | Generate graph from discovered project config |
| `stageflow list` | List stages from discovered project config |
| `stageflow check <target>` | Check conditions in discovered project |
| `stageflow hook` | Enforce tool guard from discovered project |

**Error message when outside a project:**

```
Error: Not a StageFlow project (or any parent directory).
Run 'stageflow init' to create one here.
```

Modeled after Git's "not a git repository" message — familiar and actionable.

### 4.2 Commands NOT Requiring a Project

These work anywhere, with no root discovery:

| Command | Behavior |
|---------|----------|
| `stageflow cond <type>` | Test a condition type (uses cwd for file paths) |
| `stageflow cond --list` | List all registered condition types |
| `stageflow generate [desc]` | Generate workflow YAML to stdout |
| `stageflow generate --help` | Show generator help |
| `stageflow --help` | Show top-level help |
| `stageflow mcp` | Start MCP server |

---

## 5. Path Resolution Rules

### 5.1 Config Loading

```
if marker_type == "new":
    config = load_yaml(root / ".stageflow" / "config" / "stages.yaml")
elif marker_type in ("legacy", "legacy_state_only"):
    config = load_yaml(root / "stageflow" / "config" / "stages.yaml")
```

### 5.2 State Loading

```
if marker_type == "new":
    state = load_json(root / ".stageflow" / "current_stage.json")
elif marker_type in ("legacy", "legacy_state_only"):
    state = load_json(root / ".claude" / "current_stage.json")
```

### 5.3 Artifact Paths

Both project types use `<root>/artifacts/runs/<run_id>/...`. The `{{var.run_id}}` template in conditions resolves to the current run's UUID. The artifacts root is always `<project_root>/artifacts/runs/` — never inside `.stageflow/` or `.claude/`.

### 5.4 Audit Logs

- New-style: `<root>/.stageflow/audit.jsonl`
- Legacy: `<root>/.claude/audit.jsonl`

### 5.5 Hook Configuration

`stageflow init` writes `<root>/.claude/settings.json` with:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "stageflow hook",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

The `stageflow hook` command discovers the project root from its own working directory (set by Claude Code to the workspace root), reads config and state, and enforces the tool allowlist.

---

## 6. `stageflow hook` — Global Hook Entrypoint

### 6.1 Rationale

Currently each project copies `.claude/hooks/stage_guard.py`. With Git-like operation, the hook command is installed globally with the package. No file copying needed.

### 6.2 Behavior

1. Read JSON from stdin (Claude Code hook protocol)
2. Discover project root from `cwd` (set by Claude Code to workspace root)
3. Load current stage and tool allowlist from discovered project
4. If tool is disallowed: write violation to audit log, return `{"allow": false, "message": "..."}`
5. If tool is allowed: return `{"allow": true}`
6. If not in a project: allow all tools (no guard active)

### 6.3 Compatibility

Existing projects with `.claude/hooks/stage_guard.py` continue to work. The global hook and the local hook script are independent — if a project has a local hook script, it takes precedence because that project's `settings.json` points to it directly.

---

## 7. Nested Project Behavior

```
/home/user/
  project-a/           # .stageflow/ exists -> project A
    src/
      project-b/       # .stageflow/ exists -> project B (nested)
        deep/          # Running commands here discovers project B
```

Rules:
- **Commands always discover the nearest ancestor with a marker.**
- Running `stageflow status` from `project-a/src/project-b/deep/` operates on project B.
- Running `stageflow status` from `project-a/src/` operates on project A.
- Running `stageflow init` from inside project A (or its children) is rejected.
- This matches Git's behavior with nested `.git` directories.

---

## 8. Migration Path for Legacy Projects

### 8.1 Automatic Compatibility

Legacy projects (using `stageflow/config/stages.yaml` + `.claude/current_stage.json`) are detected by marker priority 2 or 3 and **continue to work without changes**. No migration is required.

### 8.2 Opt-in Migration

A future `stageflow migrate` command (not in Phase 29) could:
1. Create `.stageflow/` directory
2. Copy `stageflow/config/stages.yaml` -> `.stageflow/config/stages.yaml`
3. Move `.claude/current_stage.json` -> `.stageflow/current_stage.json`
4. Update `.claude/settings.json` to use global hook command
5. Leave original files in place with deprecation warning

### 8.3 Precedence

If both `.stageflow/` AND `stageflow/config/stages.yaml` exist, the new-style `.stageflow/` wins (priority 1). This means creating `.stageflow/` is an implicit migration.

---

## 9. Safeguards

### 9.1 Package Source Isolation

Tests must prove that running StageFlow commands from a temp directory does not mutate:
- `D:\Tool\stageflow\.claude\current_stage.json`
- `D:\Tool\stageflow\.stageflow\` (if it exists)
- `D:\Tool\stageflow\stageflow\config\stages.yaml`

### 9.2 Test Strategy

All task-089 through task-098 tests must:
- Use `tmp_path` or `tempfile.mkdtemp()` for project directories
- NOT use the package source checkout as the working directory
- Assert file existence at expected paths within the temp project
- Assert non-existence of files at the package source paths

### 9.3 Discovery Module Purity

The root-discovery function must:
- Accept `cwd: Path` as a parameter (testable)
- Default to `Path.cwd()` at runtime
- Have zero side effects (no file creation, no config mutation)
- Be importable without triggering any StageFlow state changes

---

## 10. Implementation Order

| Task | What | Depends On |
|------|------|------------|
| task-088 | This design document | — |
| task-089 | `stageflow/core/discovery.py` — root discovery module | task-088 |
| task-090 | `stageflow init` — project bootstrap CLI | task-089 |
| task-091 | Update all CLI commands for discovered root | task-089, task-090 |
| task-092 | `stageflow hook` — global hook entrypoint | task-089 |
| task-093 | Legacy compatibility + migration support | task-089, task-090 |
| task-094 | Documentation updates (CLAUDE.md, api_reference.md) | task-090, task-092 |
| task-095 | CLI smoke tests (external temp repo) | task-090, task-091 |
| task-096 | Nested + multi-repo tests | task-095 |
| task-097 | AI-style E2E workflow tests | task-096 |
| task-098 | Staged verification pipeline | task-095, task-096, task-097 |

---

## 11. Non-Goals (for Phase 29)

- **No changes to state machine semantics** — transitions, conditions, variables, run_id lifecycle unchanged
- **No changes to visual editor** — the editor continues to work on its own project
- **No changes to LLM generator** — generator works project-independently as before
- **No remote/multi-machine sync** — projects are local to a single machine
- **No package publishing** — StageFlow remains installable via `pip install -e .` from source
- **No `stageflow migrate` command** — migration is automatic via marker detection; explicit migration is deferred

---

## 12. Open Decisions

1. **Should `stageflow init` accept a `--template` flag?** Defer. Default 10-stage pipeline is sufficient.
2. **Should `stageflow root` be a command that prints the discovered root?** Yes — useful for debugging and scripting. Include in task-091.
3. **Should `STAGEFLOW_ROOT` env var override discovery?** Defer. Useful for CI/CD but adds complexity. Revisit if needed.
4. **Should `.stageflow/` be committed to version control?** Yes for config, no for state. `stageflow init` should generate a `.gitignore` entry for `.stageflow/current_stage.json` and `.stageflow/audit.jsonl`.
