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
- [ ] **task-036**: Fix 5 empty `pass`-body tests in `test_engine.py` (lines ~565, 636, 687, 732, 778). Either implement proper assertions or remove them. Tests that do nothing create false coverage.
- [ ] **task-037**: Add 3 new condition types: `port_open` (check TCP port is listening), `process_running` (check process by name/cmdline), `docker_ps` (check container running). +6 tests each = 18 tests.
- [ ] **task-038**: Add audit log rotation — `max_entries` param on `AuditLogger.__init__` that truncates oldest entries when exceeded. Write ~10000 synthetic entries and verify count stays ≤ max. +3 tests.
- [ ] **task-039**: Extend guard.py to inspect `tool_input` — deny `Write`/`Edit` operations targeting paths outside `artifacts/` or `.claude/` in restricted stages. +5 tests.
- [ ] **task-040**: Update CLAUDE.md to match current state — fix test count (6→17), fix directory structure (test/→stageflow/), add missing `stage_back.py` reference if task-035 delivers it.

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
