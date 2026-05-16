# StageFlow API Reference

> Auto-generated from source. Run `python _introspect.py` to refresh signatures.

## Table of Contents

- [Module: `stageflow.core.conditions`](#module-stageflowcoreconditions)
- [Module: `stageflow.core.registry`](#module-stageflowcoreregistry)
- [Module: `stageflow.core.engine`](#module-stageflowcoreengine)
- [Module: `stageflow.core.audit`](#module-stageflowcoreaudit)
- [Module: `stageflow.core.guard`](#module-stageflowcoreguard)
- [Module: `stageflow.core.schema`](#module-stageflowcoreschema)
- [CLI Reference](#cli-reference)

---

## Module: `stageflow.core.conditions`

Pluggable condition evaluation system with TTL caching and variable interpolation.

### Public API

#### `register(name: str)`

Decorator to register a custom condition evaluator.

```python
from stageflow.core.conditions import register

@register("my_check")
def my_check(params: dict) -> tuple[bool, str]:
    return True, "Condition passed"
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique condition name; used as the key in YAML condition dicts |

| Returns | Type | Description |
|---------|------|-------------|
| decorator | `Callable` | Wraps the function and registers it under `name` |

---

#### `evaluate(name: str, params: dict) -> Tuple[bool, str]`

Evaluate a single condition by name.

```python
from stageflow.core.conditions import evaluate

ok, msg = evaluate("file_exists", {"path": "README.md"})
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Registered condition name |
| `params` | `dict` | Parameters dict. Must include `base_path` for file-based conditions |

| Returns | Type | Description |
|---------|------|-------------|
| `ok` | `bool` | Whether the condition passed |
| `msg` | `str` | Human-readable result description |

---

#### `evaluate_all(conditions: list[dict], base_path: str = '.', cache_ttl: float | None = None, variables: dict = None) -> Tuple[bool, list[str]]`

Evaluate a list of conditions. Returns `(True, msgs)` only if all pass. Results are cached by SHA-256 key of `(conditions, base_path, variables)`.

```python
from stageflow.core.conditions import evaluate_all

ok, msgs = evaluate_all([
    {"file_exists": "artifacts/runs/{{var.run_id}}/analyze/findings.md"},
    {"file_contains": {"path": "artifacts/runs/{{var.run_id}}/analyze/findings.md", "pattern": "Root Cause"}},
], base_path=".", variables={"run_id": "550e8400-e29b-...", "issue_id": "BUG-42"})
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `conditions` | `list[dict]` | — | List of condition dicts, each with a single key (type) |
| `base_path` | `str` | `"."` | Root path for relative file references |
| `cache_ttl` | `float | None` | `None` | Override global cache TTL; `0` disables for this call |
| `variables` | `dict | None` | `None` | Dict for `{{var.key}}` interpolation in string params |

| Returns | Type | Description |
|---------|------|-------------|
| `ok` | `bool` | `True` if all conditions passed |
| `msgs` | `list[str]` | One `[PASS]`/`[FAIL]` message per evaluated condition |

---

#### `list_conditions() -> list[str]`

Return alphabetically sorted list of all registered condition type names.

```python
from stageflow.core.conditions import list_conditions
print(list_conditions())  # ['all_of', 'always', 'any_of', ...]
```

---

#### `set_cache_ttl(ttl: float)`

Set the global condition cache TTL in seconds. Pass `0` to disable caching entirely.

```python
from stageflow.core.conditions import set_cache_ttl
set_cache_ttl(30.0)   # Cache for 30 seconds
set_cache_ttl(0)      # Disable cache
```

---

#### `clear_cache()`

Clear all cached condition results immediately.

---

### Built-in Condition Types (30)

Each condition is used in YAML or via `evaluate()` with a single-key dict: `{type: params}`.

#### File Conditions

| Type | Params | Description |
|------|--------|-------------|
| `file_exists` | `path` | File exists on disk |
| `file_not_exists` | `path` | File does NOT exist |
| `file_contains` | `path`, `pattern` | File contains regex `pattern` (re.DOTALL re.MULTILINE) |
| `file_not_contains` | `path`, `pattern` | File does NOT contain regex `pattern` |
| `file_age` | `path`, `max_age?`, `min_age?` | File mtime within age bounds (seconds) |
| `file_size` | `path`, `min?`, `max?` | File size within byte bounds |
| `hash_file` | `path`, `expected?`, `algo?` | File hash; optionally compares to `expected` |

#### JSON / YAML Conditions

| Type | Params | Description |
|------|--------|-------------|
| `json_field` | `path`, `field`, `op`, `value?` | Query a JSON field (ops: `exists`, `not_empty`, `equals`, `not_equals`, `gt`, `lt`, `in`, `matches`) |
| `yaml_field` | `path`, `field`, `op`, `value?` | Query a YAML field (ops: `exists`, `not_empty`, `equals`) |
| `json_schema` | `path`, `schema_path?` | Validate JSON file against JSON Schema (requires `jsonschema`) |
| `json_count` | `path`, `field?`, `min?`, `max?`, `eq?` | Count items/keys in JSON array/object |

#### Shell & Command Conditions

| Type | Params | Description |
|------|--------|-------------|
| `shell_test` | `command`, `op?`, `value?` | Run shell command (ops: `exit_zero`, `stdout_contains`, `stdout_not_empty`, `gt`) |
| `command_exists` | `command`, `op?` | Check CLI tool on PATH (ops: `exists`, `version`) |
| `python_expr` | `expr`, `context?` | Evaluate Python expression in restricted sandbox |

#### Git Conditions

| Type | Params | Description |
|------|--------|-------------|
| `git_status` | `op`, `value?` | Git working tree check (ops: `clean`, `files_changed`, `branch`, `has_commits`) |
| `diff_contains` | `pattern`, `op?`, `staged_only?` | Search git diff for pattern (ops: `contains`, `not_contains`) |

#### Environment / Network Conditions

| Type | Params | Description |
|------|--------|-------------|
| `env_var` | `name`, `op?`, `value?` | Check environment variable (ops: `exists`, `equals`, `not_empty`) |
| `http_status` | `url`, `expected?`, `timeout?`, `method?` | Check HTTP status code |
| `time_range` | `after?`, `before?`, `tz?` | Check current time is within a window |

#### Process & Container Conditions

| Type | Params | Description |
|------|--------|-------------|
| `port_open` | `port`, `host?`, `timeout?` | Check TCP port is listening on host (default 127.0.0.1:2s timeout) |
| `process_running` | `name`, `cmdline?` | Check if a process is running by name or command line pattern (uses `psutil` if available, falls back to `tasklist`/`ps`) |
| `docker_ps` | `name?`, `filter?` | Check if Docker containers are running; filters by name if provided |

#### File System Conditions

| Type | Params | Description |
|------|--------|-------------|
| `glob_count` | `pattern`, `min?`, `max?`, `eq?` | Count glob-matching files |
| `compare_files` | `path1`, `path2`, `op?` | Compare two file contents (ops: `identical`, `different`) |

#### Logical Combinators

| Type | Params | Description |
|------|--------|-------------|
| `all_of` | `conditions` | ALL sub-conditions must pass (short-circuit on first failure) |
| `any_of` | `conditions` | ANY sub-condition must pass (short-circuit on first success) |
| `not` | `condition` | Negate a sub-condition |
| `retry` | `condition`, `max_attempts?`, `delay?` | Retry sub-condition with delay between attempts |
| `always` | — | Always passes |
| `never` | `reason?` | Always fails; `reason` string is shown in message |

---

## Module: `stageflow.core.registry`

Stage and transition registry. Loads YAML config and provides query + dynamic registration API.

### Class: `Stage`

A single stage (node) in the state machine graph.

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Stage identifier |
| `tools` | `list[str]` | Allowed tool patterns; empty = allow all |
| `description` | `str` | Human-readable description (from `meta.description`) |
| `meta` | `dict` | Raw `meta` dict from YAML |
| `extra` | `dict` | All other YAML keys (e.g., `on_enter`, `on_exit`) |

**`to_dict() -> dict`** — Serialize to dict.

---

### Class: `Transition`

A directed edge between two stages with optional conditions.

| Attribute | Type | Description |
|-----------|------|-------------|
| `from_stage` | `str` | Source stage name |
| `to_stage` | `str` | Target stage name |
| `conditions` | `list[dict]` | List of condition dicts to evaluate |
| `on_fail` | `str | None` | Rollback target stage on condition failure |
| `description` | `str` | Human-readable description |

**`evaluate(base_path: str = '.', cache_ttl: float = 0, variables: dict = None) -> tuple[bool, list[str]]`**

Evaluate all conditions for this transition. `cache_ttl=0` ensures fresh evaluation each call.

**`to_dict() -> dict`** — Serialize to dict.

---

### Class: `StageRegistry`

Central registry for all stages and transitions. Loads from `stages.yaml`.

```python
from stageflow.core.registry import StageRegistry
reg = StageRegistry("stageflow/config/stages.yaml")
```

**`__init__(config_path: str = "stageflow/config/stages.yaml")`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config_path` | `str` | `"stageflow/config/stages.yaml"` | Path to YAML config file |

**Query Methods:**

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `get_stage` | `(name: str)` | `Stage | None` | Lookup stage by name |
| `get_transitions_from` | `(stage_name: str)` | `list[Transition]` | All outgoing transitions |
| `get_transitions_to` | `(stage_name: str)` | `list[Transition]` | All incoming transitions |
| `get_next_stages` | `(stage_name: str)` | `list[str]` | Names of reachable stages |
| `stage_names` | (property) | `list[str]` | Sorted list of all stage names |
| `all_stages` | (property) | `dict[str, Stage]` | Dict copy of all stages |
| `all_transitions` | (property) | `list[Transition]` | List copy of all transitions |

**Registration Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_stage` | `(name: str, tools: list[str] = None, description: str = '', **kwargs) -> Stage` | Dynamically add a stage (not persisted to YAML). Extra kwargs go to `Stage.extra` |
| `unregister_stage` | `(name: str) -> bool` | Remove a stage and all its transitions |
| `register_transition` | `(from_stage: str, to_stage: str, conditions: list[dict] = None, on_fail: str = None, description: str = '') -> Transition` | Dynamically add a transition |
| `unregister_transition` | `(from_stage: str, to_stage: str) -> bool` | Remove a specific transition |

```python
# Example: dynamic stage + transition
reg.register_stage("deploy", tools=["Bash(kubectl *)"],
                   on_enter=[{"shell": "echo deploying"}])
reg.register_transition("wrap_up", "deploy", [{"always": True}],
                        on_fail="wrap_up")
```

**`validate() -> tuple[bool, list[str]]`**

Validate the graph: checks for unknown stage references, isolated stages, and duplicate transitions.

**`to_dict() -> dict`** — Serialize entire registry to dict (stages + transitions).

---

## Module: `stageflow.core.engine`

Central state machine. Manages current stage, validates transitions, enforces conditions, persists state.

```python
from stageflow.core.engine import StateMachine

sm = StateMachine(registry, base_path=".")
sm.initialize("pick")
ok, msgs = sm.transition_to("analyze")
```

### Class: `StateMachine`

**`__init__(registry: StageRegistry, base_path: str = ".")`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `registry` | `StageRegistry` | — | Stage/transition registry |
| `base_path` | `str` | `"."` | Root path for state file, audit log, and file-based conditions |

**State Management:**

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `initialize` | `(stage: str, reuse_run: bool = False)` | `Tuple[bool, list[str]]` | Set starting stage; generates a UUID `run_id` in variables. If `reuse_run=True`, preserves the existing `run_id` from current state |
| `reset` | `()` | — | Clear all state; delete state file from disk |
| `clean_run_artifacts` | `()` | — | Delete only the current run's artifact directory (`artifacts/runs/<run_id>/`); other runs and the `artifacts/` tree are left untouched. No-op when no `run_id` is set |

**Transition Methods:**

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `can_transition_to` | `(target: str)` | `Tuple[bool, list[str]]` | Dry-run: check if transition is allowed without executing it |
| `transition_to` | `(target: str, force: bool = False)` | `Tuple[bool, list[str]]` | Attempt transition. Runs `on_exit` hooks on current stage, `on_enter` on target. On failure applies `on_fail` rollback |
| `force_transition_to` | `(target: str)` | `Tuple[bool, list[str]]` | Bypass conditions and hooks; pure stage change |

**Variables:**

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `set_var` | `(key: str, value: Any)` | — | Set a scoped variable; persists to state file. Access in conditions via `{{var.key}}` |
| `get_var` | `(key: str, default=None)` | `Any` | Get a variable value |
| `get_all_vars` | `()` | `dict` | Return copy of all variables |

**Query Methods:**

| Method | Signature | Returns | Description |
|--------|-----------|---------|-------------|
| `status` | `()` | `dict` | Full status including current stage, history, retry count, iterations, variables, available next stages |
| `is_tool_allowed` | `(tool_name: str)` | `Tuple[bool, str]` | Check if tool is in current stage's allow list. Supports glob patterns like `Bash(git *)` |
| `get_retry_count` | `(stage: str)` | `int` | How many times this stage has been retried |
| `get_iterations` | `(stage: str)` | `int` | How many times this stage has been visited |

**Properties:**

| Property | Type | Description |
|----------|------|-------------|
| `current_stage` | `str | None` | Current stage name (setter persists to disk) |
| `history` | `list[dict]` | Transition history records `[{from, to, at}]` |
| `state_path` | `Path` | Path to `.claude/current_stage.json` |
| `registry` | `StageRegistry` | Associated registry |
| `audit` | `AuditLogger` | Audit logger instance |

```python
# Example: full transition flow
sm = StateMachine(reg, "/project")
sm.initialize("pick")                       # Sets stage, generates run_id
run_id = sm.get_var("run_id")               # e.g., "550e8400-e29b-..."
sm.set_var("issue_id", "BUG-42")
ok, msgs = sm.can_transition_to("analyze")  # Dry-run check
if ok:
    sm.transition_to("analyze")             # Real transition
print(sm.status()["current_stage"])         # "analyze"
print(sm.get_var("run_id"))                 # UUID persisted in state file

# Artifact cleanup (scoped to current run only)
sm.complete()                               # Complete run at terminal stage
sm.clean_run_artifacts()                    # Deletes artifacts/runs/<run_id>/

# Reuse the same run_id after reset
sm.initialize("pick", reuse_run=True)        # Keeps previous run_id
```

**Internal Methods** (for testing/framework use):

| Method | Description |
|--------|-------------|
| `_save_state()` | Persist current state dict to JSON file |
| `_load_state()` | Load state dict from JSON file (or return defaults) |
| `_run_hooks(stage_name, hook_type)` | Execute `on_enter`/`on_exit` hooks for a stage |
| `_handle_transition_failure(current, target, msgs)` | Increment retry count, apply `on_fail` rollback |
| `_match_tool_args(constraint, actual)` | Static: glob-match tool args (e.g., `python *` matches `python foo.py`) |

---

## Module: `stageflow.core.audit`

Structured audit logger. Writes JSONL to `.claude/audit.jsonl`.

### Class: `AuditLogger`

**`__init__(base_path: str = ".")`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_path` | `str` | `"."` | Root path; audit log is written to `<base_path>/.claude/audit.jsonl` |

**Logging Methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `log_transition` | `(from_stage: str | None, to_stage: str, success: bool, messages: list[str] = None, forced: bool = False)` | Log a transition attempt |
| `log_condition_check` | `(transition: str, condition_type: str, passed: bool, message: str)` | Log a single condition evaluation |
| `log_stage_enter` | `(stage: str)` | Log stage entry; starts internal timer |
| `log_stage_exit` | `(stage: str)` | Log stage exit; records `duration_seconds` |
| `log_hook_execution` | `(stage: str, hook_type: str, hook_kind: str, success: bool, message: str = '')` | Log a lifecycle hook execution |
| `log_tool_violation` | `(tool_name: str, stage: str, reason: str)` | Log an unauthorized tool access |
| `log_error` | `(error_type: str, message: str, context: dict = None)` | Log a framework error |

**`get_summary() -> dict`**

Parse the audit log and return statistics:

```python
{
    "total_events": 150,
    "transitions": 42,
    "successful_transitions": 38,
    "failed_transitions": 4,
    "tool_violations": 3,
    "stages_visited": 8,
    "stage_durations": {"analyze": 45.2, "implement": 120.7},
    "current_stage_times": {"verify": 15.3},
    "most_violated_stage": "implement",
}
```

---

## Module: `stageflow.core.guard`

Tool guard for Claude Code integration. Intercepts tool calls and validates against the current stage's allow list.

### Class: `StageGuard`

**`__init__(config_path: str = "stageflow/config/stages.yaml", base_path: str = ".", registry: StageRegistry = None, enforce_path_guard: bool = True)`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config_path` | `str` | `"stageflow/config/stages.yaml"` | Path to stages YAML |
| `base_path` | `str` | `"."` | Project root path |
| `registry` | `StageRegistry | None` | `None` | Pre-built registry (skips YAML load if provided) |
| `enforce_path_guard` | `bool` | `True` | Enable file-level access policy enforcement |

**`check(tool_name: str, tool_input: dict = None) -> tuple[bool, str]`**

Check if a tool is allowed in the current stage. Refreshes state from disk before checking.

Tool checking order:
1. **Default read tools**: `Read`, `Grep`, `Glob` pass the tool-name gate even if omitted from `stage.tools`
2. **Write tools**: `Write`, `Edit`, `MultiEdit`, `NotebookEdit` must be explicitly listed in `stage.tools`
3. **File access policy**: `access.read` and `access.write` glob patterns restrict file paths
4. **Deny overrides allow**: A path matching both `allow` and `deny` is blocked

**`allowed_tools() -> list[str]`**

Return the tool patterns allowed in the current stage.

**`log_violation(tool_name: str, reason: str)`**

Write a violation record to `.claude/guard_violations.jsonl`.

### `claude_hook_main()`

Entry point for Claude Code PreToolUse hook. Reads hook input from stdin (JSON), checks the tool against the current stage, prints allow/block decision.

---

## Module: `stageflow.core.schema`

Lightweight YAML schema validation (stdlib only, no jsonschema dependency).

### `validate_stages_config(config: dict) -> Tuple[bool, list[str]]`

Validate a parsed stages YAML config dict. Checks:

- `stages` is a list of dicts with unique `name` strings
- `tools` is a list if present
- `transitions` is a list of dicts with `from`/`to` strings
- No duplicate transitions
- `conditions` is a list if present
- `on_fail` is a string if present
- `groups` is a list if present

| Parameter | Type | Description |
|-----------|------|-------------|
| `config` | `dict` | Parsed YAML config (from `yaml.safe_load`) |

| Returns | Type | Description |
|---------|------|-------------|
| `valid` | `bool` | `True` if config passes all checks |
| `errors` | `list[str]` | List of validation error messages |

---

## CLI Reference

All commands via `python -m stageflow <command>` or `stageflow <command>` (if installed).

### `status`

Show current stage, description, allowed tools, available next stages, and history.

```
python -m stageflow status
python -m stageflow status --verbose    # Show individual allowed tools
```

### `next [target] [--force]`

Advance to the next stage (auto-selects first available if `target` omitted).

```
python -m stageflow next               # Auto-advance
python -m stageflow next implement     # Go to specific stage
python -m stageflow next --force       # Skip conditions
```

### `back [target]`

Go back to the previous stage (or specified target). Uses `force_transition_to`.

```
python -m stageflow back               # Back to first incoming stage
python -m stageflow back analyze       # Back to specific stage
```

### `jump <target> [--force] [--reason "..."]`

Jump directly to any stage. `--force` requires `--reason` for audit trail.

```
python -m stageflow jump verify
python -m stageflow jump implement --force --reason "emergency rollback"
```

### `reset [--hard] [--clean-artifacts]`

Clear the active run state. Use `stageflow start` to begin a new run afterward.

**⚠ Warning**: `reset` changes StageFlow state only; artifacts are preserved on disk unless `--clean-artifacts` is passed.

```
python -m stageflow reset                        # Clear current run state
python -m stageflow reset --hard                 # Full reset — delete state file
python -m stageflow reset --clean-artifacts      # Delete current run artifacts, then reset
```

### `graph`

Generate a Mermaid flowchart (markdown) of the full state machine. Current stage is highlighted green, terminal stages are gray.

```
python -m stageflow graph
```

### `list`

List all stages, transitions, and conditions. Runs `validate()` and shows errors if any.

```
python -m stageflow list
```

### `init [path] [--force] [--start]`

Bootstrap a new StageFlow project (like `git init`). Creates `.stageflow/config/stages.yaml`, `.claude/settings.json`, and `artifacts/runs/`. Does NOT start a run unless `--start` is given.

```
python -m stageflow init                        # Initialize current directory
python -m stageflow init /path/to/project       # Initialize specific directory
python -m stageflow init --force                # Overwrite existing config
python -m stageflow init --start                # Init and start a run at first stage
```

### `start [stage]`

Begin a new StageFlow run. Without a stage argument, starts at the first YAML stage.

```
python -m stageflow start                       # Start at entry (first YAML stage)
python -m stageflow start analyze               # Start at specific stage
```

### `migrate [--force]`

Convert a legacy StageFlow project (stageflow/config/stages.yaml + .claude/current_stage.json) to new-style (.stageflow/). Preserves old files.

```
python -m stageflow migrate                     # Migrate discovered project
python -m stageflow migrate --force             # Overwrite existing .stageflow/
```

### `check <target>`

Dry-run: evaluate conditions for a transition without executing it.

```
python -m stageflow check verify
```

### `cond <type> [--params JSON]`

Test a single condition type interactively.

```
python -m stageflow cond file_exists --params '{"path": "README.md"}'
python -m stageflow cond always
```

### `root [--json]`

Print the discovered project root path and metadata.

```
python -m stageflow root                         # Plain text output
python -m stageflow root --json                  # JSON output
```

Output fields: `root`, `marker_type` (new/legacy/legacy_state_only), `config_path`, `state_path`, `artifacts_dir`, `audit_dir`. Exits with code 1 and "Not a StageFlow project" message outside a project.

### `editor [--host HOST] [--port PORT] [--no-open]`

Start the visual workflow editor bound to the current StageFlow project.

```
stageflow editor                              # Start on 127.0.0.1:8000, open browser
stageflow editor --port 9000                  # Custom port
stageflow editor --host 0.0.0.0 --port 8080  # Custom host and port
stageflow editor --no-open                    # Headless (no browser)
stageflow editor --no-open --port 8765        # Headless + custom port
```

The editor discovers the project root from cwd (walking upward for `.stageflow/`). It must be run inside a StageFlow project — running outside a project exits with an error and guidance to run `stageflow init`.

Only new-style projects (`.stageflow/` marker) are supported. Legacy projects must be migrated first with `stageflow migrate`.

The editor server stays in the foreground. Use `Ctrl+C` to stop.

**Save gate**: The editor's Save button writes to `<project>/.stageflow/config/stages.yaml` only when no run is active (`current_stage` is null). While a run is active, Save is blocked with a 403 error and a message telling the user to run `stageflow complete` or `stageflow reset` first.

### Other Commands

```
python -m stageflow hook                        # Claude Code PreToolUse Hook entrypoint
python -m stageflow generate <desc>             # LLM workflow generator
python -m stageflow mcp                         # Start MCP server (stdio)
```

### Editor Server API

The visual workflow editor is backed by a FastAPI server (`editor/server.py`). When launched via `stageflow editor`, the server is bound to the discovered project root. Endpoints marked "project-scoped" use the bound root and do not rediscover from cwd.

#### `GET /api/project/config`

Load the current project's `stages.yaml` and metadata.

**Response** (200):
```json
{
  "yaml": "stages:\n  - name: alpha\n...",
  "config_path": "/proj/.stageflow/config/stages.yaml",
  "project_root": "/proj",
  "marker_type": "new",
  "current_stage": null,
  "run_status": null,
  "save_allowed": true
}
```

- `save_allowed` is `true` when `current_stage` is `null` (no active run)
- Returns 400 if no StageFlow project is found
- Returns 404 if the config file is missing

#### `GET /api/project/status`

Return detailed project run state.

**Response** (200):
```json
{
  "project_root": "/proj",
  "marker_type": "new",
  "current_stage": "alpha",
  "run_status": null,
  "final_stage": null,
  "completed_at": null,
  "run_id": "abc123-...",
  "save_allowed": false,
  "history_count": 3,
  "variable_keys": ["run_id"],
  "retry_count": {},
  "iterations": {},
  "state_path": "/proj/.stageflow/current_stage.json",
  "config_path": "/proj/.stageflow/config/stages.yaml"
}
```

#### `POST /api/project/save-config`

Save workflow YAML to the project config. Project-scoped — uses the bound root.

**Request**:
```json
{"yaml": "stages:\n  - name: alpha\n..."}
```

**Success** (200):
```json
{
  "saved": true,
  "config_path": "/proj/.stageflow/config/stages.yaml",
  "message": "Config saved to /proj/.stageflow/config/stages.yaml. Current state: no active run."
}
```

**Blocked** (403): Active run exists — `current_stage` is not null.
**Invalid** (400): YAML parse error or StageFlow schema validation failure.
**No project** (400): No StageFlow project found.

**Save gate**: The endpoint reads the current state file and blocks if `current_stage` is not null. Previous config bytes are preserved on validation failure.

#### `GET /api/conditions`

Return all 30 condition type definitions with parameter schemas (for the edge editor UI).

#### `POST /api/validate`

Validate arbitrary YAML against the StageFlow schema.

```json
// Request:  {"yaml": "..."}
// Response: {"valid": true, "errors": []}
```

#### `POST /api/run`

Dry-run a transition: evaluate conditions from the provided YAML without persisting state.

```json
// Request:  {"yaml": "...", "from_stage": "alpha", "to_stage": "beta"}
// Response: {"can_transition": true, "messages": ["always: passed"]}
```

### Legacy Scripts

Located in `scripts/` (recommended: use `stageflow <command>` CLI instead):

| Script | CLI Equivalent |
|--------|------------|
| `python scripts/stage_next.py [target]` | `stageflow next` |
| `python scripts/stage_status.py` | `stageflow status` |
| `python scripts/stage_reset.py` | `stageflow reset` |
| `python scripts/stage_jump.py <target>` | `stageflow jump` |
| `python scripts/stage_back.py` | `stageflow back` |
| `python scripts/hooks_off.py` | Disable Claude Code hooks via settings.local.json |
| `python scripts/hooks_on.py` | Restore hooks from settings.local.bak.json |
