# Ralph Fix Plan — StageFlow Agent Workflow

> **Last updated**: 2026-05-10
> **Mode**: Autonomous iterative development
> **Rule**: ONE task per loop. Pick the first unchecked `[ ]`, execute it, mark it `[x]`, commit.

---

## Phase 1: 完成测试体系

- [x] **task-001**: Write `tests/test_stress.py` — rapid consecutive transitions (500 round-trips, 100-stage chain), thread-safe variable access (concurrent set_var, get_all_vars), concurrent condition evaluation (always, file_exists, mixed), large state persistence (100KB vars, 500-entry history), state file integrity (JSON validity, no truncation), concurrent transitions (crash-free, status() under load). 17 tests covering all concurrency/stress scenarios.
- [x] **task-002**: Write `tests/test_cache.py` — verify `_CONDITION_CACHE` behavior: cache hit within TTL, cache miss after TTL, `cache_ttl=0` disables cache, `clear_cache()` works, variable change invalidates cache key, different base_path produces different key. Use `set_cache_ttl()` / `clear_cache()` from `stageflow.core.conditions`.
- [x] **task-003**: Write `tests/test_benchmark.py` — measure: 1000 condition evaluations/sec, 100 stage transitions/sec, 1000-stage graph validation time, state file read/write latency. Use `time.perf_counter()`. Print markdown summary table. Use `create_config_with_n_stages` helper.
- [x] **task-004**: Write `tests/test_hooks_integration.py` — verify: on_enter shell hook executes, on_exit python hook executes, hook failure does NOT block transition, multiple hooks per stage, hook execution is audit-logged. Use `stageflow_temp_sm` + `register_stage()`.

---

## Phase 2: 文档完善

- [x] **task-005**: Generate API reference. Read all docstrings from `stageflow/core/*.py`, write `docs/api_reference.md` with function signatures, parameter tables, return types, usage examples. Use Python introspection for accuracy.

---

## Phase 3: 可视化工作流编辑器 (Visual Workflow Editor)

- [x] **task-006**: Create `editor/` React+TypeScript+Vite project. `npm create vite@latest editor -- --template react-ts`, `cd editor && npm install reactflow @tanstack/react-query`. Set up: `Canvas.tsx`, `StageNode.tsx`, `EdgeEditor.tsx`, `PropertiesPanel.tsx`. Verify `npm run dev` works.
- [x] **task-007**: Implement `Canvas.tsx` with React Flow: "Add Stage" button, draggable nodes with stage name + tool count badge, color coding (normal=blue, terminal=gray). Custom `StageNode.tsx` component with handles.
- [x] **task-008**: Implement `PropertiesPanel.tsx`: click node → right panel with stage name, description, tool list (add/remove with tag input), on_enter/on_exit hook editors. Controlled form that updates React Flow data in real-time.
- [x] **task-009**: Implement `EdgeEditor.tsx`: click edge → modal showing condition editor with dropdown for condition type, dynamic form fields per type, add/remove conditions, AND/OR toggle, on_fail target selector. Edge label shows condition summary.
- [x] **task-010**: YAML import/export: "Export YAML" button serializes canvas to `stages.yaml` format. "Import YAML" file picker parses YAML → renders nodes/edges. Validation before export. Use `js-yaml`.
- [x] **task-011**: Mermaid preview toggle, dark/light theme, keyboard shortcuts (Delete, Ctrl+S, Ctrl+Z), minimap, auto-layout button.
- [x] **task-012**: Create `editor/server.py` FastAPI server: serve React app, `POST /api/validate` validates YAML, `POST /api/run` executes stageflow check, `GET /api/conditions` returns 27 condition types with param schemas.

---

## Phase 4: LLM 工作流生成器 (LLM Workflow Generator)

- [x] **task-013**: Create `stageflow/generator/` package with `llm_generator.py`. `WorkflowGenerator` class: takes NL description → builds Claude prompt → parses YAML response → validates with StageRegistry → retries up to 3x with error feedback. Prompt template in-code.
- [x] **task-014**: Create `stageflow/generator/prompts.py` — templates: CI_CD, CODE_REVIEW, DATA_PIPELINE, GENERIC. Each includes role, output format spec, condition type reference, examples.
- [x] **task-015**: Add `stageflow generate` CLI subcommand. `python -m stageflow generate "desc"` → YAML to stdout. Flags: `--output PATH`, `--validate`, `--template TYPE`. Write `tests/test_generator.py` (5+ tests).

---

## Phase 5: Agent 运行时 (Agent Runtime)

- [x] **task-016**: Create `stageflow/agent/` package with `runner.py`. `AgentRunner`: reads FIX_PLAN.md-style markdown, parses `- [ ] task-id: desc`, enters StageFlow pipeline per task (analyze→plan→implement→verify→document), marks `[x]` on completion, commits. Progress tracked in `.claude/agent_progress.json`.
- [x] **task-017**: Create `stageflow/agent/hybrid.py` — `HybridWorkflow`: LLM stages (analyze, plan use Claude API) + framework stages (implement, verify use condition gates). Transition conditions check both LLM output quality AND framework artifacts.
- [x] **task-018**: Create `stageflow/agent/orchestrator.py` — `WorkflowOrchestrator`: parallel agent execution with `asyncio`, dependency graph, shared variable store, aggregate audit trail. Test with 3 parallel agents.

---

## Phase 6: 高级特性

- [x] **task-019**: Add pause/resume to `engine.py`: `sm.pause(reason)`, `sm.resume()`, `sm.is_paused` property. Pause prevents all transitions. Audit log records pause/resume. Write tests.
- [x] **task-020**: Add webhook hook type: `on_enter: [{webhook: {url: "...", method: "POST", body: {...}}}]`. Support `{{var.key}}` interpolation. Webhook response logged to audit. Test with mock HTTP server.

---

## Phase 7: Harness 工程调研

- [x] **task-021**: WebSearch: "Dify workflow engine architecture", "LangGraph state machine agent", "n8n workflow automation", "Temporal.io durable execution", "Prefect workflow orchestration". Write comparison to `docs/harness_research.md`.
- [x] **task-022**: WebSearch: "Claude Code agent workflow patterns 2026", "AI coding agent state machine best practices", "autonomous AI developer loop patterns", "harness engineering agent framework". Append to `docs/harness_research.md`.
- [x] **task-023**: Design integration blueprint: how StageFlow wraps Dify/n8n/LangGraph as backends, MCP server exposing conditions, REST API for external editors. Write to `docs/integration_blueprint.md`.
- [x] **task-024**: Implement top 3 improvements from research. Pick most impactful features, implement in StageFlow, write tests, update docs.

---

## 🔄 最终迭代循环 (Time-Gated Loop)

- [x] **task-025-LOOP**:
  1. Run `python -c "from datetime import datetime; now=datetime.now(); print(f'{now.hour:02d}:{now.minute:02d}'); exit(0 if now.hour >= 21 else 1)"`
  2. **If exit 0 (≥21:00)**: mark this task `[x]`, print "Done for today.", signal EXIT.
  3. **If exit 1 (<21:00)**:
     - WebSearch "harness engineering AI agent workflow automation 2026"
     - Read 2-3 top results, extract actionable ideas
     - Also search: "Dify visual workflow editor architecture", "n8n condition node system", "Temporal workflow durable execution", "LangGraph state machine pattern"
     - If useful findings → implement a small improvement in StageFlow, run tests
     - If nothing → run test suite, look for edge cases to fix
     - Append one-line summary to `.ralph/harness_iterations.md`
     - **Leave this task unchecked** (<21:00) so next loop picks it up again
     - Recommend Ralph waits ~10 min between iterations

---

## Phase 12: 查漏补缺 (Quick Wins & Finishing)

- [x] **task-026**: Add `reason` parameter to `engine.transition_to()`. Write `reason` into the history record for structured audit trace. Update CONDITION_DEFS if needed. +tests.
- [x] **task-027**: Extend `http_status` condition with `body_contains` op — validate HTTP response body matches a pattern (string/regex). +tests. Update CONDITION_DEFS.
- [x] **task-028**: Add `header_equals` op to `http_status` — validate specific response headers match values. +tests. Update CONDITION_DEFS.
- [x] **task-029**: Run full test suite, fix any remaining edge cases or flaky tests. Target: 680+ tests, 0 failures.

---

## Phase 13: 并行与可观测性

- [x] **task-030**: Add `stream` param to `shell_test` — allow checking stderr output with all existing ops. +tests.
- [x] **task-031**: Add `timeout` parameter to `evaluate_all` — per-evaluation global timeout via ThreadPoolExecutor. +2 tests.
- [x] **task-032**: Write `tests/test_perf.py` — quick performance sanity checks: 100 transitions under 5s, 1000 condition evals under 2s, status() under 10ms. Small, fast, no hangs.
- [x] **task-033**: Fix `test_stress.py` hanging — investigate sleep/threading issues, rewrite problematic tests to use deterministic patterns, ensure suite completes.

---

## Phase 14: 打磨与生产就绪 (Polish & Production Readiness)

- [x] **task-034**: Fix `editor/server.py` line 348 — `PromptTemplate.GENERAL` → `PromptTemplate.GENERIC`. The `/api/generate` endpoint crashes because `GENERAL` doesn't exist. +1 regression test in test_server.py.
- [x] **task-035**: Create `scripts/stage_back.py` — CLI rollback script promised in CLAUDE.md. Should call `sm.transition_back()` or equivalent. Verify it works end-to-end.
- [x] **task-036**: Fix 5 empty `pass`-body tests in `test_engine.py` (lines ~565, 636, 687, 732, 778). Either implement proper assertions or remove them. Tests that do nothing create false coverage. **Result: false alarm — all 5 `pass` statements are `log_message` overrides in mock HTTP handlers, not empty test bodies. No fix needed.**
- [x] **task-037**: Add 3 new condition types: `port_open` (check TCP port is listening), `process_running` (check process by name/cmdline), `docker_ps` (check container running). +6 tests each = 18 tests.
- [x] **task-038**: Add audit log rotation — `max_entries` param on `AuditLogger.__init__` that truncates oldest entries when exceeded. Write ~10000 synthetic entries and verify count stays ≤ max. +3 tests.
- [x] **task-039**: Extend guard.py to inspect `tool_input` — deny `Write`/`Edit` operations targeting paths outside `artifacts/` or `.claude/` in restricted stages. +5 tests.
- [x] **task-040**: Update CLAUDE.md to match current state — fix test count (6→17), fix directory structure (test/→stageflow/), add missing `stage_back.py` reference if task-035 delivers it.

---

## Phase 15: 可靠性增强 (Reliability & Hardening)

- [x] **task-041**: Fix `scripts/hooks_off.py` and `scripts/hooks_on.py` — replace `sys.argv` scanning with `argparse`. Running `--help` currently triggers `disable_hooks()` as side effect. Add `--help`, `--json`, `--dry-run` flags.
- [x] **task-042**: Install `pytest-cov` and run coverage — `pip install -e ".[dev]"`, run `pytest --cov=stageflow --cov-report=term`, identify uncovered lines. Add targeted tests for weakest 3 modules. Target: 80%+ line coverage.
- [x] **task-043**: Strengthen `verify → document` transition in `stages.yaml` — add `shell_test: {command: "python -m pytest --tb=short", op: exit_zero}` condition to prevent bypassing test failures.
- [x] **task-044**: Add built-in LLM adapter in `llm_generator.py` — `AnthropicAdapter` wrapping `anthropic` SDK with prompt caching. Make generator work out-of-box. +5 tests.
- [x] **task-045**: Audit + update per-file test counts in CLAUDE.md by running `pytest --collect-only -q` and parsing counts per file.

---

## Phase 16: 代码质量与文档补齐 (Quality & Docs)

- [x] **task-046**: Improve `schema.py` coverage (80%→95%+) — add tests for non-dict stages, bad names, duplicate transitions, non-list tools/conditions, non-string on_fail, non-list groups. ~8 new tests targeting 10 uncovered lines.
- [x] **task-047**: Improve `guard.py` coverage (61%→80%+) — test absolute path resolution, `_check_write_path` edge cases (no path, empty parts), `claude_hook_main()` with mocked stdin. ~6 new tests.
- [x] **task-048**: Update `docs/api_reference.md` — add `port_open`, `process_running`, `docker_ps` condition types (added in task-037 but docs not updated). Verify all 30 condition types are documented with params and examples.
- [x] **task-049**: Audit `pyproject.toml` dev dependencies — verify `pytest-cov`, `pytest`, `pyyaml` properly declared. Ensure `pip install -e ".[dev]"` works end-to-end. Add any missing test deps.
- [x] **task-050**: Cross-platform audit of `conditions.py` — identify Unix-only subprocess calls (`which`, `ps`, `grep`), verify Windows fallbacks exist and are tested. Ensure `shell_test` defaults work cross-platform.

---

## Phase 17: CLI 增强与类型安全 (CLI & Type Safety)

- [x] **task-051**: Add `--json` flag to CLI `status`, `list`, `check` commands — structured JSON output for CI/CD and scripting. ~4 subprocess tests.
- [x] **task-052**: State file corruption recovery — in `engine._load_state()`, save corrupted JSON as `.bak` before resetting to defaults. Log recovery via audit. ~3 tests.
- [x] **task-053**: Fix all 25 mypy errors across 7 files — implicit Optional annotations, missing type hints, `llm_generator.py` potential None access. Add `mypy` to dev deps + `[tool.mypy]` config in pyproject.toml. Verify `mypy stageflow` passes clean.
- [x] **task-054**: Add `--dry-run` flag to `stageflow next` CLI — evaluate conditions for auto-selected next stage without executing transition. ~3 tests.
- [x] **task-055**: Add `--list` flag to `stageflow cond` CLI — list all registered condition types from terminal. Currently requires Python API. ~2 tests.

---

## Phase 18: 覆盖率与质量收尾 (Coverage & Quality Finishing)

- [x] **task-056**: Improve `__main__.py` coverage (29% → 50%+) — add subprocess tests for `graph` (verify mermaid output), `cond <type>` (test a condition with params), `back` (basic execution), `jump <target>`, `reset`, `init <stage>`. Currently 223 uncovered lines; target ~8-10 new subprocess tests. **Result: 24 new tests (56 total), 32→56 in test_main.py. Fixed cmd_cond base_path injection bug. Added fixtures for uninitialized/known state.**
- [x] **task-057**: Cover remaining `conditions.py` edge branches (88% → 92%+) — add tests for None-guard branches in gt/lt/eq ops (lines 273, 278, 295-296), file error paths (lines 342-345, 373-374), subprocess timeout/error handling (lines 504-512, 515-516, 532-544). ~10 targeted tests. **Result: 10 new tests (255→265 in test_conditions.py), coverage 88%→92% (82→53 missed). Added http_server fixture to conftest.py.**
- [x] **task-058**: Cover remaining `engine.py` missed lines (96% → 98%+) — add tests for uninitialized `can_transition_to` path (lines 140-142), error recovery paths (lines 314-316, 344-345), and pause edge cases (lines 397, 429, 461). ~5 targeted tests. **Result: 12 new tests (71→83 in test_engine.py), coverage 93%→100% (19→0 missed). Engine is now fully covered.**
- [x] **task-059**: Add `--verbose` output expansion to `stageflow status` — when `--verbose` is set, print tool list with descriptions, transition details from current stage, hook information, and variable store dump. Currently `--verbose` only shows tool names. ~3 tests. **Result: 3 new tests (56→58 in test_main.py). Verbose now shows transitions (conditions, on_fail), hooks (on_enter, on_exit), and variables. Tool list shows "(all allowed)" for empty tools. Fixed `__main__.py` cmd_status.**
- [x] **task-060**: Run full test suite, update CLAUDE.md stats (current: 825 tests, verify count), run `mypy stageflow` to confirm clean, run `pytest --cov=stageflow --cov-report=term` and record final coverage %. Fix any last issues found. **Result: 883 passed, 1 skipped, 0 failed. mypy clean (17 files). Coverage 84% overall (core: engine 100%, schema 100%, registry 97%, guard 97%, conditions 92%). CLAUDE.md stats and per-file counts updated.**

---

## Phase 19: 并行与 MCP (Parallel & MCP)

- [x] **task-061**: Implement parallel condition evaluation (TASK_PLAN 9.3). Add `parallel` param to `evaluate_all()`. Use `ThreadPoolExecutor` with `_evaluate_single()` + `_evaluate_parallel()`. Respect severity ordering in result processing. ~10-15 tests. **Result: 12 new tests (255→267 in test_conditions.py). Added `_evaluate_single`, `_evaluate_parallel` to conditions.py. 895 total tests passing.**
- [ ] **task-062**: MCP Server 集成 (TASK_PLAN 9.6) — FastMCP server exposing condition evaluation as tools.

---

## 图例

| 符号 | 含义 |
|------|------|
| `[ ]` | 待执行 — Ralph 取第一个执行 |
| `[x]` | 已完成 |
| `[!]` | 阻塞需人工介入 |

## Ralph 执行规则

1. **每循环一个任务** — 找第一个 `[ ]`，执行，标记 `[x]`
2. **提交规范** — `ralph: <task-id> — <summary>`
3. **状态报告** — 结束时输出 `---RALPH_STATUS---` 块
4. **失败 3 次** → 标记 `[!]` + 阻塞原因，继续下一个
5. **实现任务必须含测试**（纯文档/调研任务除外）
6. **不要修改** `.ralph/` 和 `.ralphrc`（除 fix_plan.md 的 checkbox）
