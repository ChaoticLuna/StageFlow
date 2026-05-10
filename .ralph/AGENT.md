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
# Run all tests (362 currently passing)
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
# Check current stage status
python -m stageflow status

# List all stages and transitions
python -m stageflow list

# Advance to next stage (framework-enforced conditions)
python scripts/stage_next.py

# Advance to specific stage
python scripts/stage_next.py plan

# Force advance (skip conditions)
python scripts/stage_next.py --force implement

# Check conditions without advancing
python scripts/stage_next.py --dry-run verify

# Show available next stages
python scripts/stage_next.py --list

# Generate Mermaid graph
python -m stageflow graph

# Test a condition type
python -m stageflow cond file_exists --params '{"path": "README.md"}'

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
│   ├── conditions.py    # 27 condition types + caching + variable interpolation
│   ├── registry.py      # Stage/Transition CRUD + YAML loading
│   ├── engine.py        # StateMachine: transitions, hooks, variables, retry
│   ├── guard.py         # Tool guard: Claude Code Hook integration
│   ├── audit.py         # Audit logger: JSONL trail + timing
│   └── schema.py        # YAML config validation
├── config/
│   └── stages.yaml      # 10 stages + 11 transitions (default pipeline)
└── __main__.py          # CLI entry point

scripts/
├── stage_next.py        # Advance to next stage
├── stage_status.py      # Show current stage
├── stage_reset.py       # Reset state machine
├── stage_jump.py        # Jump to specific stage
├── stage_back.py        # Go back to previous stage
├── hooks_off.py         # Disable tool hooks
└── hooks_on.py          # Re-enable tool hooks

tests/
├── conftest.py          # Fixtures + pytest plugin
├── test_conditions.py   # 198 tests
├── test_registry.py     # 65 tests
├── test_engine.py       # 28 tests
├── test_guard.py        # 8 tests
├── test_edge_cases.py   # 15 tests
├── test_e2e.py          # 18 tests
└── test_extensibility_quick.py  # 100-stage proof

.claude/
├── settings.json        # Project hook config (PreToolUse + PostToolUse)
├── settings.local.json  # Local overrides (hooks disabled for dev)
├── current_stage.json   # Current stage state (do NOT edit manually)
├── audit.jsonl          # Audit trail
├── guard_violations.jsonl  # Tool violation log
└── hooks/
    └── stage_guard.py   # Claude Code PreToolUse hook entry point

.ralph/
├── fix_plan.md          # Ralph task list (read each loop)
├── PROMPT.md            # Ralph development instructions
├── AGENT.md             # This file — build/run/test commands
└── progress.json        # Progress tracking
```

## Notes

- The hooks system intercepts tool calls based on current stage. Run `python scripts/hooks_off.py` during active development.
- State file `.claude/current_stage.json` is managed by the framework — never edit it manually.
- Tests use fixtures from `conftest.py`. The `stageflow_sm` fixture initializes at 'pick' stage.
- On Windows, `shell_test` uses `shell=True` which invokes cmd.exe — bash syntax may not work.
- The `http_status` condition may fail behind corporate firewalls.
- `json_schema` condition gracefully degrades if `jsonschema` package is not installed.
