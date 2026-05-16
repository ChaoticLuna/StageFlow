# Ralph Agent Configuration — StageFlow

## Build

```bash
# Install StageFlow in development mode
pip install -e .

# Install dev dependencies (testing)
pip install -e ".[dev]"

# Optional: install jsonschema for JSON Schema condition
pip install jsonschema
```

## Test

```bash
# Run all tests (1539 Python + 130 editor = 1669 total)
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_conditions.py

# Run tests with coverage
pytest --cov=stageflow --cov-report=term-missing

# Run tests matching a keyword
pytest -k "cache"

# Skip tests marked as stageflow (when no current stage is set)
pytest -m "not stageflow"
```

## Run

```bash
# Initialize a StageFlow project (like git init)
python -m stageflow init

# Start a new run at entry stage
python -m stageflow start

# Start at specific stage
python -m stageflow start analyze

# Check current stage status
python -m stageflow status
python -m stageflow status --verbose
python -m stageflow status --json

# List all stages and transitions
python -m stageflow list
python -m stageflow list --json

# Advance to next stage (framework-enforced conditions)
python -m stageflow next

# Advance to specific stage
python -m stageflow next plan

# Force advance (skip conditions)
python -m stageflow next --force implement

# Complete current run (terminal stage only)
python -m stageflow complete

# Check conditions without advancing
python -m stageflow next --dry-run verify
python -m stageflow check verify

# Generate Mermaid graph
python -m stageflow graph

# Start visual workflow editor (browser-based)
python -m stageflow editor
python -m stageflow editor --port 9000
python -m stageflow editor --no-open             # Headless (no browser)
python -m stageflow editor --no-open --port 8765 # Headless + custom port

# Reset current run (abandon/restart — NOT normal completion)
python -m stageflow reset
python -m stageflow reset --clean-artifacts
python -m stageflow reset --hard

# Jump to specific stage (admin/recovery only)
python -m stageflow jump verify --force --reason "emergency rollback"

# Migrate legacy project to new .stageflow/ format
python -m stageflow migrate

# Test a condition type
python -m stageflow cond file_exists --params '{"path": "README.md"}'
python -m stageflow cond --list

# Run demo
python demo/demo_workflow.py
```

## Hook Management

```bash
# Disable StageFlow tool hooks (for development)
python scripts/hooks_off.py

# Check hook status
python scripts/hooks_off.py --status

# Re-enable hooks
python scripts/hooks_on.py
```

## Environment Setup

```bash
# First time setup
git clone <repo>
cd auto_workflow
pip install -e .
pip install -e ".[dev]"

# Disable hooks for development
python scripts/hooks_off.py

# Verify everything works
pytest
python -m stageflow status
```

## Project Structure

```
stageflow/
├── core/
│   ├── conditions.py    # 30 condition types + caching + variable interpolation
│   ├── registry.py      # Stage/Transition CRUD + YAML loading + extends
│   ├── engine.py        # StateMachine: transitions, hooks, variables, retry
│   ├── guard.py         # Tool guard: Claude Code Hook integration
│   ├── audit.py         # Audit logger: JSONL trail + timing
│   ├── discovery.py     # Project root discovery (walk upward for .stageflow/)
│   ├── schema.py        # YAML config validation
│   └── mcp_server.py    # MCP Server (FastMCP)
├── config/
│   └── stages.yaml      # 10 stages + 11 transitions (default pipeline)
├── generator/           # LLM workflow generator
├── agent/               # Agent runtime (runner, hybrid, orchestrator)
├── integrations/        # Linear + Notion sync clients
└── __main__.py          # Git-like CLI entry point

editor/                  # Visual workflow editor (React + FastAPI)
├── server.py            # FastAPI backend (18 endpoints, project-scoped APIs)
├── src/                 # React + ReactFlow frontend (TypeScript)
│   ├── App.tsx          # Main app: auto-load, Save, theme
│   ├── components/      # Canvas, StageNode, PropertiesPanel, EdgeEditor
│   └── utils/           # YAML parser, API client, condition defs
└── dist/                # Built production assets (served by FastAPI)

scripts/
├── stage_next.py        # Legacy — use: stageflow next
├── stage_status.py      # Legacy — use: stageflow status
├── stage_reset.py       # Legacy — use: stageflow reset
├── stage_jump.py        # Legacy — use: stageflow jump
├── stage_back.py        # Legacy — use: stageflow back
├── hooks_off.py         # Disable tool hooks
└── hooks_on.py          # Re-enable tool hooks

tests/
├── conftest.py          # Fixtures + pytest plugin
├── test_conditions.py   # 291 tests
├── test_registry.py     # 116 tests
├── test_engine.py       # 114 tests
├── test_guard.py        # 30 tests
├── test_discovery.py    # 18 tests
├── test_main.py         # 236 tests (CLI)
├── test_server.py       # 80 tests
├── test_editor_e2e.py   # 30 tests
├── test_access_policy.py # 93 tests
├── test_e2e.py          # 25 tests
├── ...                  # 32 test files total

.claude/
├── settings.json        # Project hook config (PreToolUse → stageflow hook)
├── settings.local.json  # Local overrides (hooks disabled for dev)
├── current_stage.json   # Legacy state file (do NOT edit manually)
├── audit.jsonl          # Audit trail
├── guard_violations.jsonl  # Tool violation log (legacy)
└── hooks/
    └── stage_guard.py   # Legacy hook (use stageflow hook instead)

.stageflow/              # New project metadata directory
├── config/
│   └── stages.yaml      # Project stage configuration
├── current_stage.json   # Current run state
└── guard_violations.jsonl  # Tool violation log

.ralph/
├── fix_plan.md          # Ralph task list (read each loop)
├── PROMPT.md            # Ralph development instructions
├── AGENT.md             # This file — build/run/test commands
└── progress.json        # Progress tracking
```

## Notes

- StageFlow CLI 是 Git-like 的：所有命令从当前目录向上查找项目根，支持从任意子目录运行。
- 新项目使用 `.stageflow/` 作为元数据目录；旧项目使用 `stageflow/config/stages.yaml` + `.claude/current_stage.json`。
- 使用 `stageflow migrate` 将旧项目迁移到新格式（保留原文件）。
- The hooks system intercepts tool calls based on current stage. Run `python scripts/hooks_off.py` during active development.
- **Default read tools (Phase 42)**: `Read`, `Grep`, and `Glob` are default read-only tools that bypass the `stage.tools` name-check when a run is active. Write tools (`Write`, `Edit`, `MultiEdit`, `NotebookEdit`) remain strictly stage-gated. Sensitive stages can restrict reads via `access.read` policy.
- **File access policy**: Stages can define `access.read` and `access.write` with `allow`/`deny` glob lists relative to project root. Deny takes precedence over allow. Supports `{{var.run_id}}` interpolation. Paths outside project root are blocked. `Bash`/`PowerShell` commands are not sandboxed by the access policy — restrict those tools in sensitive stages.
- Run `stageflow init` to create a new project; `stageflow start` to begin a run; `stageflow next` to advance.
- State files are managed by the framework — never edit them manually.
- Tests use fixtures from `conftest.py`. The `stageflow_sm` fixture initializes at 'pick' stage.
- On Windows, `shell_test` uses `shell=True` which invokes cmd.exe — bash syntax may not work.
- The `http_status` condition may fail behind corporate firewalls.
- `json_schema` condition gracefully degrades if `jsonschema` package is not installed.

## Editor Lifecycle

```
stageflow init     →  stageflow editor  →  stageflow start  →  stageflow next  →  stageflow complete
                     (edit workflow)                                        ↓
                                                                   stageflow editor
                                                                   (edit for next run)
```

两种工作流配置方式：
1. **AI 生成**: `stageflow generate "description" --output .stageflow/config/stages.yaml --validate`
2. **可视化编辑**: `stageflow editor`（浏览器拖拽编辑节点、连线、条件）

**保存门控 (Save Gate)**：
- 仅当 `current_stage` 为 `null` 时允许保存（无活跃运行）
- 运行进行中保存会被阻止 → 先 `stageflow complete` 或 `stageflow reset`
- 无效 YAML 不会覆盖已有配置

**无头模式**: `stageflow editor --no-open --port <port>` 用于测试/CI，不打开浏览器。
