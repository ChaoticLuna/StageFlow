# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-15
> **当前 Agent**: Ralph (Claude Code)
> **交接原因**: task-085 — resume semantics tests for session-change scenarios

---

## task-085 会话总结 (2026-05-15)

### 做了什么
1. **Added TestResumeSemantics** to 	ests/test_engine.py (5 tests):
   - 	est_fresh_sm_loads_existing_state — new SM instance loads same stage + run_id
   - 	est_resume_can_continue_work — fresh SM continues transitions from saved state
   - 	est_reset_creates_new_run_id_cross_session — plain reset generates new run_id
   - 	est_reuse_run_preserves_id_cross_session — initialize(reuse_run=True) keeps same run_id
   - 	est_multiple_session_reloads_keep_same_run_id — any number of reloads preserve run_id
2. **Added CLI-level resume tests** to 	ests/test_main.py (3 tests):
   - 	est_resume_keeps_run_id_in_new_session — status --json shows same run_id across calls
   - 	est_status_run_id_changes_after_reset — plain reset pick creates new run_id
   - 	est_status_run_id_preserved_after_reset_reuse — reset pick --reuse-run preserves run_id

### 测试结果
- TestResumeSemantics: 5/5 passed
- CLI resume tests: 3/3 passed
- Full suite: 1071 passed, 1 skipped

### 已知问题
- Stage guard keeps resetting state file to analyze during test runs

---

## task-084 会话总结 (2026-05-15)

### 做了什么
1. **Created real input environments** under examples/run_scoped_artifacts/:
   - 	ask_a/input.txt — Alpha pipeline data
   - 	ask_b/input.txt — Beta pipeline data (distinct content)
2. **Rewrote 
un_demo.py** — now reads from real task dirs, embeds input content in artifacts, proves 5 assertions:
   - Assertion 1: Different run IDs
   - Assertion 2: Run A artifacts do NOT unlock run B transitions
   - Assertion 3: Run A stale review does NOT block run B done gate
   - Assertion 4: Run B own changes_requested DOES block done gate
   - Assertion 5: Output files contain correct task-specific data, no cross-contamination
3. **Expanded 	ests/test_run_demo.py** from 5 to 15 tests across 6 classes:
   - TestDemoExitAndBanner (2), TestInputEnvironments (3), TestRunIdentity (2),
   - TestArtifactIsolation (3), TestOutputCorrectness (3), TestArtifactDirectories (2)

### 测试结果
- run_demo.py: ALL DEMOS PASSED (5/5 assertions)
- test_run_demo.py: 15/15 passed
- Full suite: 1063 passed, 1 skipped

--- — Phase 27 audit + 31 in-process CLI tests + coverage push

---

## task-083 会话总结 (2026-05-15)

### 做了什么
1. **Audited Phase 27** — reviewed all components for correctness:
   - `StateMachine.initialize()`: run_id creation + reuse_run correct
   - `StateMachine.reset()`: proper state clearing
   - `StateMachine.clean_run_artifacts()`: scoped to current run only
   - CLI `cmd_reset`: --hard, --reuse-run, --clean-artifacts all correct
   - stages.yaml: all 11 paths use {{var.run_id}}
   - HybridWorkflow: {run_artifact_dir} interpolation correct
   - Editor: templates + placeholders preserve {{var.run_id}}
   - No bugs found. All behavior matches intended model.
2. **Added `TestMainInProcess` class** — 31 in-process tests calling `main()` directly:
   - Tests cover all CLI commands: status, list, next, back, jump, reset, graph, init, check, cond, generate, mcp
   - Uses monkeypatch for sys.argv + SystemExit handling
   - Contributes to coverage (subprocess tests don't)

### 测试结果
- 1053 passed, 1 skipped, 0 failed
- __main__.py: 28% → 89% coverage
- Overall: 86% → 96% coverage

---

## cleanup 会话总结 (2026-05-15)

### 做了什么
修复 `tests/test_main.py` 中重复的 `TestStageflowMainModule` 类定义。该文件原本已有此类（第 303 行），未提交的更改又在第 391 行添加了完全相同的第二个定义。删除了重复的类定义，保留了新的 `TestMainInProcess` 类（提供全面的进程内 CLI 测试覆盖）。

### 测试结果
- 1053 passed, 1 skipped, 0 failed
- 89 个 test_main.py 测试全部通过

---

## task-082 会话总结 (2026-05-15)

### 完成了什么
创建 `examples/run_scoped_artifacts/run_demo.py` 和 `tests/test_run_demo.py`。

### Demo 设计
- 使用临时目录中的 3 阶段迷你工作流 (start → build → done)
- Demo 1: 运行 task_a，写入 task_a 专属 artifacts，推进到 done
- Demo 2: 运行 task_b (新 run_id)，验证:
  1. 两个 run_id 不同
  2. task_a 的产物不会解锁 task_b 的转换（条件使用 `{{var.run_id}}`）
  3. 错误的 `changes_requested.md` 会阻塞 done 门控
  4. 每个 run 有独立的产物目录

### 文件
- `examples/run_scoped_artifacts/run_demo.py` — 168 行，可直接 `python run_demo.py` 运行
- `tests/test_run_demo.py` — 5 个测试，subprocess 包装器验证 demo 输出

### 测试结果
- run_demo.py: 手动运行通过，ALL DEMOS PASSED
- test_run_demo.py: 5/5 通过

### 下一步
Phase 27 (6 个任务，077-082) 现已完成。TASK_PLAN.md 应更新为 82/82 且 Phase 27 标记为 ✅。

---

## task-081 会话总结 (2026-05-15)

### 做了什么
1. **Updated `CLAUDE.md`**:
   - Added "运行身份与产物隔离" section explaining run_id lifecycle, --reuse-run, --clean-artifacts
   - Added warning: reset changes state only; artifacts preserved unless --clean-artifacts
   - Updated CLI commands section with all new flags
   - Updated scripts table with --reuse-run, --clean-artifacts, --hard entries
   - Updated variable interpolation example to use run-scoped paths
   - Updated test counts (1017 passed) and per-file counts (engine 92, e2e 25, hybrid 30)
2. **Updated `docs/api_reference.md`**:
   - Updated `initialize()` signature to include `reuse_run=False`
   - Added `clean_run_artifacts()` method documentation
   - Updated CLI `reset` section with --reuse-run, --clean-artifacts examples and warning
   - Updated example code to demonstrate run_id and clean_run_artifacts()
   - Updated evaluate_all example to use run-scoped paths

### 当前状态快照
```
Tests:           1017 passed, 0 failed, 1 skipped
Docs updated:    CLAUDE.md + api_reference.md
fix_plan.md:     81/82 tasks complete
```

---

## task-080 会话总结 (2026-05-15)

### 做了什么
1. **Added `clean_run_artifacts()` to `engine.py`** — deletes only `artifacts/runs/<run_id>/` directory, never the whole `artifacts/` tree. No-op when no run_id or directory doesn't exist.
2. **Added `--clean-artifacts` flag to CLI** (`__main__.py`) — `python -m stageflow reset pick --clean-artifacts` cleans current run's artifacts before resetting. Works with `--reuse-run` and `--hard`.
3. **Added `--clean-artifacts` flag to `scripts/stage_reset.py`** — same behavior as CLI.
4. **Added 5 tests** in `TestCleanArtifacts` class (test_engine.py):
   - `test_clean_removes_current_run_artifacts`
   - `test_clean_preserves_old_run_dirs`
   - `test_clean_noop_when_no_run_id`
   - `test_clean_noop_when_dir_does_not_exist`
   - `test_no_cleanup_without_flag`

### 当前状态快照
```
Tests:           1017 passed, 0 failed, 1 skipped (1018 collected)
New method:      StateMachine.clean_run_artifacts()
CLI:             reset --clean-artifacts flag added
fix_plan.md:     80/82 tasks complete
```

---

## task-079 会话总结 (2026-05-15)

### 做了什么
1. **Updated `stageflow/agent/hybrid.py` STAGE_PROMPTS** — all artifact paths now use `{run_artifact_dir}` placeholder (pick, analyze, plan, verify, document stages)
2. **Added run_id interpolation to `run_llm_stage()`** — replaces `{run_artifact_dir}` with `artifacts/runs/<run_id>` before calling the LLM; falls back to `unknown-run` when run_id is missing
3. **Updated `tests/test_main.py` `test_status_json_output`** — now asserts `variables.run_id` is present in JSON output
4. **Added 5 tests**:
   - `TestRunScopedPrompts` (3 tests): prompt includes run-scoped path for analyze, pick; fallback when run_id missing
   - `TestStagePrompts.test_prompts_use_run_artifact_dir_placeholder` — verifies all artifact-producing stages use the placeholder
   - `TestStatus.test_status_includes_run_id` — status dict includes variables.run_id (UUID format)

### 当前状态快照
```
Tests:           1012 passed, 0 failed, 1 skipped (1013 collected)
hybrid.py:       STAGE_PROMPTS + run_llm_stage() now run-scoped
Status JSON:     variables.run_id verified in test
fix_plan.md:     79/82 tasks complete
```

---

## task-078 会话总结 (2026-05-15)

### 做了什么
1. **Updated `stageflow/config/stages.yaml`** — all 8 default artifact paths now use `artifacts/runs/{{var.run_id}}/...`:
   - `pick/issue_context.md`, `analyze/findings.md`, `plan/task_plan.md`, `verify/test_results.md` (x2), `document/changelog.md`, `review/changes_requested.md`
2. **Updated `editor/server.py`** — CONDITION_DEFS placeholders now show run-scoped examples (`artifacts/runs/<run_id>/...`)
3. **Updated `editor/src/components/Canvas.tsx`** — default sample edges use `{{var.run_id}}` templates
4. **Updated `editor/src/components/conditionDefs.ts`** — placeholder text uses run-scoped paths with `{{var.run_id}}`
5. **Updated `tests/test_e2e.py`** — all E2E tests now write artifacts to run-scoped paths (5 test methods updated)
6. **Added 3 regression tests** in `TestRunScopedArtifacts` class (test_e2e.py):
   - `test_old_run_artifact_does_not_satisfy_new_run_transition`
   - `test_current_run_artifact_satisfies_transition`
   - `test_two_runs_have_independent_artifact_dirs`

### 当前状态快照
```
Tests:           1007 passed, 0 failed, 1 skipped (1008 collected)
E2E tests:       25 (was 22, +3 regression)
Editor:          All placeholders + sample edges run-scoped
stages.yaml:     8 artifact paths updated to {{var.run_id}} templates
fix_plan.md:     78/82 tasks complete
```

---

## task-077 会话总结 (2026-05-15)

### 做了什么
1. **Added run_id lifecycle to `StateMachine.initialize()`** — generates a UUID on each initialize call, stored as `variables.run_id` and persisted in `.claude/current_stage.json`
2. **Added `reuse_run: bool = False` parameter** to `initialize()` — when True, preserves the existing `run_id` from current state instead of generating a new one
3. **Updated CLI reset flow** — `python -m stageflow reset <stage>` starts a fresh run (new UUID); `python -m stageflow reset <stage> --reuse-run` keeps the existing `run_id`
4. **Updated `scripts/stage_reset.py`** — same `--reuse-run` flag support
5. **Added 4 tests** in `TestRunIdentity` class (test_engine.py):
   - `test_initialize_creates_run_id` — UUID generated and persisted
   - `test_two_default_resets_create_different_run_ids` — fresh run_ids on each reset
   - `test_reuse_run_preserves_run_id` — `reuse_run=True` keeps the same run_id
   - `test_reuse_run_missing_old_run_id_creates_one` — graceful fallback when no prior run_id
6. **Fixed 3 existing tests** that broke due to auto-generated `run_id` in variables:
   - `test_get_all_vars_returns_dict` — now checks individual keys instead of exact dict match
   - `test_concurrent_set_var_different_keys` — accounts for +1 run_id key
   - `test_state_file_consistency_under_concurrent_var_writes` — accounts for +1 run_id key

### 当前状态快照
```
Tests:           1004 passed, 0 failed, 1 skipped (1005 collected)
fix_plan.md:     76/82 tasks complete (task-077 just completed)
New behavior:    initialize() always creates variables.run_id (UUID4)
CLI:             reset --reuse-run flag added
Script:          stage_reset.py --reuse-run flag added
```

---

## 100% integration coverage 会话总结 (2026-05-11)

### 做了什么
1. **Added `test_load_env_default_path` to `test_linear.py`** — covers default `Path(".env")` branch (line 32) via `monkeypatch.chdir`. Linear: 100% coverage (109 stmts, 0 missed).
2. **Added `test_load_env_default_path` to `test_notion.py`** — same pattern. Notion: 100% coverage (76 stmts, 0 missed).
3. **Both integrations now at 100%** — 33 linear tests, 24 notion tests.

### 当前状态快照
```
Tests:           1000 passed, 0 failed, 1 skipped (1001 collected)
fix_plan.md:     76/76 tasks complete
All TASK_PLAN:   100% complete
Coverage:        linear 100%, notion 100%, core modules 95-100%
```

---

## Coverage 补充 + Bug Fix 会话总结 (2026-05-11)

### 做了什么
1. **Added 8 coverage tests to `tests/test_linear.py`** — `TestLinearCoverage` class:
   - `test_get_issue_by_identifier_error`, `test_update_issue_with_description_and_state`
   - `test_update_issue_error`, `test_sync_stage_issue_not_found_null`
   - `test_sync_stage_no_team_id`, `test_sync_stage_team_states_error`
   - `test_add_comment_error`, `test_search_issues_error`
   - Linear coverage: 99% (109 stmts, 1 miss at _load_env import line)
2. **Added 3 coverage tests to `tests/test_notion.py`**:
   - `test_create_page_with_children`, `test_query_database_with_sorts`, `test_sync_stage_page_error`
   - Notion coverage: 99% (76 stmts, 1 miss)
3. **Fixed bug in `linear.py:209`** — `issue.get("team", {}).get("id")` crashed when `team` is `None`
   because `dict.get()` returns the default only for missing keys, not for `None` values.
   Fixed to: `(issue.get("team") or {}).get("id")`

### 当前状态快照
```
Tests:           998 passed, 0 failed, 1 skipped (999 collected)
fix_plan.md:     76/76 tasks complete
All TASK_PLAN:   100% complete
```

---

## task-076 会话总结 (2026-05-11)

### 做了什么
1. **Created `stageflow/integrations/notion.py`** — Notion REST API integration:
   - `NotionClient(api_key)` — reads key from param, `NOTION_API_KEY` env var, or `.env`
   - `get_page(id)` — fetch page by ID
   - `update_page_properties(id, props)` — PATCH page properties
   - `query_database(db_id, filter, sorts)` — query database pages
   - `get_database(db_id)` — get database schema
   - `create_page(db_id, properties)` — create new page in database
   - `sync_stage_to_status(page_id, stage)` — map StageFlow stage → Notion status
   - `append_blocks(page_id, blocks)` — append content blocks
   - `search_pages(query)` — search across workspace
2. **Created `tests/test_notion.py`** — 20 tests (init, get page, not found, update, query, filter, database schema, create, sync, missing property, custom map, append blocks, search, status map, env loading)

### 当前状态快照
```
Tests:           987 passed, 0 failed, 1 skipped
fix_plan.md:     76/76 tasks complete
All TASK_PLAN:   Phase 11 now 100% complete
```

---

## task-075 会话总结 (2026-05-11)

### 做了什么
1. **Created `stageflow/integrations/linear.py`** — Linear.app GraphQL API integration:
   - `LinearClient(api_key)` class — reads key from param, `LINEAR_API_KEY` env var, or `.env` file
   - `get_issue(id)` — fetch issue by UUID or key
   - `get_issue_by_identifier(identifier)` — fetch by human-readable ID (e.g., "ENG-42")
   - `get_team_states(team_id)` — fetch workflow states for a team
   - `update_issue_state(issue_id, state_id)` — move issue to a workflow state
   - `update_issue(issue_id, title, description, state_id)` — general update
   - `sync_stage_to_state(issue_id, stage_name)` — map StageFlow stage → Linear state automaticaly
   - `add_comment(issue_id, body)` — add a comment to an issue
   - `search_issues(query_str, limit)` — search issues by text
   - `DEFAULT_STAGE_STATE_MAP` — sensible defaults (analyze→In Progress, verify→In Review, done→Done)
2. **Created `tests/test_linear.py`** — 24 tests covering:
   - Client initialization (explicit key, env var, dotenv, missing key raises)
   - Get issue by ID/identifier, GraphQL error handling
   - Get team states, error path
   - Update issue state/fields, GraphQL error
   - Sync: success, unknown state name, issue not found, custom map
   - Comment, search, HTTP error handling
   - `_load_env`: valid, missing, comments/blanks, malformed lines
3. **Uses `urllib.request`** (stdlib) — no external HTTP dependency

### 当前状态快照
```
Tests:           967 passed, 0 failed, 1 skipped
fix_plan.md:     75/75 tasks complete
New module:      stageflow/integrations/linear.py (LinearClient)
New tests:       tests/test_linear.py (24 tests)
```

---

## task-074 会话总结 (2026-05-11)

### 做了什么
1. **Created VS Code extension** under `vscode-extension/`:
   - `package.json` — activation on `onStartupFinished`, contributes `stageflow.showNextStages` and `stageflow.forceNext` commands
   - `tsconfig.json` — strict TypeScript, ES2020, commonjs module
   - `.vscodeignore` — excludes source files from package
   - `src/extension.ts` — full extension logic:
     - Finds `.claude/current_stage.json` in workspace root
     - Displays current stage in VS Code status bar (left aligned, priority 100)
     - Color-coded per stage: analyze=blue, implement=orange, verify=green, done=gray
     - FileSystemWatcher updates status bar on state file changes
     - Click handler: QuickPick shows current stage, available next stages, recent history (last 3), and Force Next option
     - `Force Next Stage` command with modal confirmation
     - `runStageflowCommand()` helper executes `python scripts/stage_next.py` in workspace root
2. **Dependencies**: `@types/vscode`, `@types/node`, `typescript` — compiles clean with `tsc -p ./`
3. **TASK_PLAN.md**: Marked 11.3 (VS Code 扩展) as ✅ complete

### 当前状态快照
```
Tests:           943 passed, 0 failed, 1 skipped
fix_plan.md:     74/74 tasks complete
New files:       vscode-extension/{package.json, tsconfig.json, .vscodeignore, src/extension.ts}
TypeScript:      compiles clean, 0 errors
```

---

## task-073 会话总结 (2026-05-11)

### 做了什么
1. **Fixed `git_status` has_commits bug** in `stageflow/core/conditions.py` line 565:
   - Changed `"git rev-list --count HEAD..@{u}"` to `"git rev-list --count @{u}..HEAD"`
   - `HEAD..@{u}` counts commits in upstream NOT in HEAD (behind count) — semantically wrong
   - `@{u}..HEAD` counts commits in HEAD NOT in upstream (ahead count) — unpushed commits
2. **Added `test_has_commits_with_upstream`** test:
   - Creates bare remote repo, sets up tracking, pushes initial commit
   - Verifies `has_commits` returns False after push (no unpushed)
   - Makes new local commit, verifies `has_commits` returns True (unpushed detected)
   - Uses `git init -b main` for explicit branch name
   - Covers conditions.py line 571 (successful upstream resolution path)

### 当前状态快照
```
Tests:           928 passed, 0 failed, 1 skipped
fix_plan.md:     73/73 tasks complete
conditions.py:   git_status has_commits now correctly counts unpushed commits
```

---

## task-068 会话总结 (2026-05-11)

### 做了什么
1. **Updated TASK_PLAN.md** — marked 9.3, 9.6, 11.1, 11.2, 11.5 as complete (already done via fix_plan.md tasks 061-064)
2. **Added Phase 22 to fix_plan.md** — 4 coverage improvement tasks
3. **task-065: mcp_server.py 58% → 96%** (+8 tests, 11→19 total):
   - TestMCPServe: 2 tests mocking FastMCP.run and create_mcp_server
   - TestMCPToolsInnerFunctions: 6 tests calling tool closure bodies via `_tool_manager.get_tool().fn()`
   - Only missed: `if __name__ == "__main__"` guard (line 80)
4. **task-066: audit.py 95% → 100%** (+3 tests, 15→18 total):
   - `_truncate()` early return when log file doesn't exist (line 43)
   - `_truncate()` reset count when entries under max limit (lines 46-47)
   - `get_summary()` current_stage_times for un-exited stages (line 155)
5. **task-067: guard.py 97% → 99%** (fixed 1 test):
   - `test_write_without_file_path` now passes non-empty dict to trigger `_check_write_path` line 38
   - Only missed: `if __name__ == "__main__"` guard (line 130)
6. **task-068: registry.py 96% → 100%** (+3 tests, 90→93 total):
   - `test_to_dict_with_max_iterations` — Stage.to_dict with max_iterations (line 36)
   - `test_extends_depth_exceeded_warns` — 7-file chain exceeding MAX_EXTENDS_DEPTH=5 (lines 123-125)
   - `test_load_invalid_config_warns_through_registry` — duplicate stage name triggers schema validation warnings in _load (lines 146-148)

### 当前状态快照
```
Tests:           927 passed, 0 failed, 1 skipped
Coverage:        84% overall
Core coverage:   engine 100%, schema 100%, audit 100%, registry 100%
                 guard 99%, mcp_server 96%, conditions 92%
mypy:            clean
fix_plan.md:     68/68 tasks complete
TASK_PLAN:       only 11.3 (VS Code ext) + 11.4 (Linear/Notion) remain
```

### 已知问题
- Stage guard keeps resetting state file to "analyze" during test runs

---


## task-064 会话总结 (2026-05-11)

### 做了什么
1. **Added config inheritance (`extends`) to StageRegistry** — `registry.py`:
   - `_resolve_extends(config, depth)` — recursively resolves parent configs (max depth 5)
   - `_merge_configs(parent, child)` — merges stages (by name), transitions (by from,to), groups (concatenation)
   - Child overrides parent; missing parent warns gracefully
2. **Added 7 tests** to `tests/test_registry.py` (83 → 90):
   - Inherits parent stages and transitions
   - Child overrides parent stage (tools, description)
   - Child overrides parent transition (conditions, description)
   - Missing parent warns with UserWarning
   - Depth limit respected across 3-level chain
   - Static `_merge_configs` method tested directly
   - Groups concatenation from parent + child

### 当前状态快照
```
Tests:           913 passed, 0 failing, 1 skipped
registry.py:     +_resolve_extends, +_merge_configs, +_MAX_EXTENDS_DEPTH
test_registry:   90 tests (was 83)
```

---

## task-063 会话总结 (2026-05-11)

### 做了什么
1. **Created `.github/workflows/ci.yml`** — GitHub Actions CI:
   - Triggers on push/PR to main
   - Python 3.10/3.11/3.12 matrix
   - Steps: install deps, pytest, mypy, coverage
2. **Created `Dockerfile`** — python:3.12-slim, installs stageflow via `pip install -e .`
   - Entrypoint: `python -m stageflow`, default CMD: `status`
3. **Created `.dockerignore`** — excludes __pycache__, .git, .claude, node_modules, etc.
4. **Updated `pyproject.toml`** — added `mcp` optional dependency group

### 当前状态快照
```
Tests:           906 passed, 0 failing, 1 skipped
New files:       .github/workflows/ci.yml, Dockerfile, .dockerignore
pyproject.toml:  +mcp optional dep
```

---

## task-062 会话总结 (2026-05-11)

### 做了什么
1. **Created `stageflow/mcp_server.py`** — MCP server exposing StageFlow conditions as tools:
   - `stageflow_evaluate(name, params)` — evaluate a single condition
   - `stageflow_list_conditions()` — list all registered condition types
   - `stageflow_evaluate_all(conditions, base_path, parallel, timeout)` — evaluate batch
2. **CLI integration**: `python -m stageflow mcp` starts the server on stdio transport
3. **Installed `mcp` SDK** as a runtime dependency
4. **Added 11 tests** to `tests/test_mcp_server.py`:
   - MCPServerCreation: FastMCP instance, tool registration (2 tests)
   - MCPToolsDirectly: evaluate pass/fail, list_conditions, evaluate_all parallel (4 tests)
   - MCPModuleImports: serve/create_mcp_server callable (2 tests)
   - MCPCLIIntegration: subprocess help, main help listing, import safety (3 tests)

### 当前状态快照
```
Tests:           906 passed, 0 failing, 1 skipped
New module:      stageflow/mcp_server.py (3 MCP tools)
New test file:   tests/test_mcp_server.py (11 tests)
CLI:             python -m stageflow mcp
```

### 已知问题
- Stage guard keeps resetting state file to "analyze"

---

## task-061 会话总结 (2026-05-11)

### 做了什么
1. **Added `parallel` parameter to `evaluate_all()`** — when `parallel=True` and len(conditions) > 1, conditions are evaluated concurrently via `ThreadPoolExecutor`
2. **Added `_evaluate_single()`** — extracts evaluation logic for a single condition, thread-safe
3. **Added `_evaluate_parallel()`** — submits all conditions to thread pool, collects results in original order, applies severity rules (hard/warn/normal) in order
4. **Timeout integration** — existing timeout wrapper works with both sequential and parallel evaluators via the `evaluator` variable pattern
5. **Worker count**: `min(len(conditions), os.cpu_count() or 4)`
6. **Added 12 tests** to `tests/test_conditions.py` (255 → 267):
   - `test_parallel_all_pass` — 10 file_exists conditions
   - `test_parallel_mixed_results` — mixed pass/fail
   - `test_parallel_hard_failure` — hard severity stops processing
   - `test_parallel_warn_does_not_block` — warn severity doesn't stop
   - `test_parallel_single_condition` — single condition falls through
   - `test_parallel_empty_list` — empty conditions list
   - `test_parallel_with_cache` — caching works with parallel
   - `test_parallel_with_timeout` — timeout fast path
   - `test_parallel_with_timeout_expired` — timeout cuts off slow parallel
   - `test_parallel_with_variables` — variable resolution before parallelization
   - `test_parallel_many_conditions` — 30 conditions in parallel
   - `test_parallel_no_wasted_eval_after_hard_fail` — hard fail result processing

### 当前状态快照
```
Tests:           895 passed, 0 failing, 1 skipped (907 collected)
conditions.py:   +_evaluate_single, +_evaluate_parallel
test_conditions: 267 tests (was 255)
```

### 已知问题
- Stage guard keeps resetting state file to "analyze" during test runs

---

## task-060 会话总结 (2026-05-11)

### 做了什么
1. **Ran full test suite**: 883 passed, 0 failed, 1 skipped (884 collected)
2. **Ran mypy**: clean — 17 source files, 0 issues
3. **Ran coverage**: 84% overall (2137 stmts, 352 missed)
   - Core coverage: engine 100%, schema 100%, registry 97%, guard 97%, conditions 92%, audit 95%
4. **Updated CLAUDE.md stats**: test counts, framework files, coverage, mypy status
5. **Updated per-file test counts in CLAUDE.md**: conditions 256, registry 83, engine 83, guard 23, main 58

### 当前状态快照
```
Tests:           883 passed, 0 failed, 1 skipped (884 collected)
mypy:            clean
Coverage:        84% overall
Core coverage:   engine 100%, schema 100%
fix_plan.md:     ALL tasks [x] — all 60 tasks complete
```

### fix_plan.md 状态
All 60 tasks from Phase 1 through Phase 18 are complete. The project is in a well-tested, stable state.

### 已知问题
- Stage guard keeps resetting state file to "analyze" during test runs
- test_stress.py has some timing-sensitive tests
- Hook currently disabled

---

## task-059 会话总结 (2026-05-11)

### 做了什么
1. **Expanded `--verbose` output** in `stageflow/__main__.py` cmd_status:
   - **Transition details**: conditions listed per transition (with flat key=value rendering for dict params), on_fail targets, descriptions
   - **Hook information**: on_enter and on_exit hooks shown with type and value
   - **Variable dump**: all variables with their values
   - **Empty tools**: now shows "(all allowed)" instead of "0 allowed"
   - Extracted `_print_verbose_details()` helper function for clean separation
2. **Added 3 tests** to `tests/test_main.py` (56 → 58):
   - `test_status_verbose_shows_details` — verifies transitions/hooks/variables sections present
   - `test_status_verbose_short_flag` — `-v` short flag works
   - `test_status_verbose_uninitialized` — no crash when state is uninitialized

### 当前状态快照
```
Tests:           883 passing, 0 failing, 1 skipped
test_main.py:    58 tests (was 56)
__main__.py:     cmd_status + _print_verbose_details helper
```

### 已知问题
- Stage guard keeps resetting state file to "analyze" during test runs

---

## task-058 会话总结 (2026-05-11)

### 做了什么
1. **Added 12 tests** to `tests/test_engine.py` (71 → 83):
   - `test_can_transition_to_uninitialized_valid_stage` — lines 140-141 (uninitialized state, valid target)
   - `test_can_transition_to_uninitialized_unknown_stage` — lines 140-142 (uninitialized state, unknown target)
   - `test_shell_hook_executes_successfully` — lines 287-294 (shell hook subprocess.run path)
   - `test_shell_hook_failure_does_not_block_transition` — lines 287-294 (shell hook non-zero exit)
   - `test_python_hook_exception_does_not_block` — lines 299-301 (Exception handler in hooks)
   - `test_interpolate_vars_in_list` — line 315 (list interpolation)
   - `test_interpolate_vars_scalar_passthrough` — line 316 (scalar passthrough)
   - `test_webhook_http_error_handled` — lines 344-345 (HTTPError handler for webhooks)
   - `test_tool_allowed_star_wildcard` — line 429 (_match_tool_args "*" constraint)
   - `test_tool_allowed_unknown_current_stage` — line 397 (registry.get_stage returns None)
   - `test_repr_uninitialized` + `test_repr_with_stage_and_history` — line 461 (__repr__)

### 当前状态快照
```
Tests:           881 passing, 0 failing, 1 skipped
Coverage:        engine.py 93% → 100% (19 → 0 missed lines)
test_engine.py:  83 tests (was 71)
```

### 已知问题
- Stage guard keeps resetting state file to "analyze" during test runs
- Need to force-advance after running tests that modify state

---

## task-057 会话总结 (2026-05-11)

### 做了什么
1. **新增 10 tests** 到 `tests/test_conditions.py` (255 → 265):
   - `TestJsonField::test_gt_field_missing_obj_none` — gt op with obj=None (line 273)
   - `TestJsonField::test_lt_expected_none` — lt op with expected=None (line 278)
   - `TestYamlField::test_pyyaml_not_installed` — ImportError handler (lines 295-296)
   - `TestShellTest::test_lt_non_numeric` — lt op ValueError catch (lines 373-374)
   - `TestShellTest::test_eq_non_numeric` — eq op ValueError catch (lines 379-380)
   - `TestShellTest::test_command_invalid_cwd` — generic Exception handler (lines 344-345)
   - `TestGitStatus::test_has_commits_no_upstream` — has_commits error path (lines 504-509)
   - `TestGitStatus::test_invalid_cwd_exception` — generic Exception handler (lines 515-516)
   - `TestHttpStatus::test_body_contains_success` — body_contains success path (lines 532-536)
   - `TestHttpStatus::test_header_equals_success` — header_equals success path (lines 537-542)
2. **Added `http_server` fixture** to `tests/conftest.py` — starts a minimal HTTP server on a random port for http_status success-path testing

### 当前状态快照
```
Tests:           869 passing, 0 failing, 1 skipped
Coverage:        conditions.py 88% → 92% (82 → 53 missed)
test_conditions: 265 tests (was 255)
conftest.py:     +1 fixture (http_server)
```

### 已知问题
- Stage guard keeps resetting state file to "analyze" during test runs
- Need to force-advance after running tests that modify state

---

## task-056 会话总结 (2026-05-11)

### 做了什么
1. **新增 24 tests** 到 `tests/test_main.py` (32 → 56 tests):
   - 3 force/reset paths: `test_next_force`, `test_reset_hard`, `test_jump_force`
   - 3 uninitialized paths: `test_back_uninitialized`, `test_jump_uninitialized`, `test_check_uninitialized` (+JSON variant)
   - 7 cond tests with valid params: `file_exists` (pass/fail), `file_not_exists`, `env_var`, `command_exists` (pass/fail), `always`
   - 1 graph test with current stage highlighting: `test_graph_with_known_stage`
   - 1 main module test: `test_main_no_command_shows_help`
   - 8 generate CLI tests: list-templates, basic, prompt-only, template, bad template, validate, output file, no-args
2. **Fixed `cmd_cond` in `__main__.py`**: Now injects `base_path` into params and handles non-dict JSON values (matching `_evaluate_loop` behavior)
3. **Added 2 pytest fixtures**: `uninitialized_state` (temp remove state file), `known_state_file` (write known state for graph highlighting test)

### 当前状态快照
```
Tests:           859 passing, 0 failing, 1 skipped
test_main.py:    56 tests (was 32)
__main__.py:     cmd_cond now injects base_path + handles non-dict params
```

### 已知问题
- Stage guard keeps resetting state file to "analyze" during test runs (test_reset_hard/reset_runs touch state file)
- Need to force-advance after running tests that modify state

---


---

## 当前状态快照

```
Tests:           678 passing, 0 failing (excluding stress/benchmark)
Framework:       7 core modules + 1 editor server
Conditions:      27 types, 7 shell_test ops (exit_zero, stdout_contains, stdout_not_empty, stdout_matches, gt, lt, eq)
Severity:        warn/soft/hard tiers, hard blocks prevent rollback
Server API:      15 endpoints
CONDITION_DEFS:  All 27 entries audited and synced with actual handler ops
Ralph:           task-025-LOOP complete (8 iterations today)
```

## task-025-LOOP 会话总结 (8 iterations)

| # | Time | Work |
|---|------|------|
| 1 | 19:56 | max_iterations per-stage hard cap (+6 tests) |
| 2 | 20:03 | MCP research + engine cache invalidation fix (+1 test) |
| 3 | 20:08 | Enhanced status API (stage_info, available_next, total_transitions) |
| 4 | 20:20 | Fixed 3 bugs: clear_cache rebinding, cache key drift, concurrency backward transitions |
| 5 | 20:42 | Added shell_test stdout_matches regex op (+3 tests) |
| 6 | 20:47 | Added shell_test lt/eq ops (+4 tests), fixed flaky test_no_duplicate_history_entries |
| 7 | 20:53 | Audited all 27 CONDITION_DEFS → fixed 6 condition type op mismatches |
| 8 | 20:58 | Research: ARF framework, 5-state model, idempotency patterns (no code) |

## 最终代码变更

- **stageflow/core/conditions.py**: clear_cache() .clear() fix, evaluate_all cache key computed once, any_of defensive copy, shell_test stdout_matches/lt/eq ops
- **editor/server.py**: Filter _-prefixed internal conditions, fix 6 CONDITION_DEFS op mismatches (shell_test, env_var, git_status, compare_files, json_field, yaml_field, command_exists)
- **tests/test_conditions.py**: +10 tests (stdout_matches x3, lt x2, eq x2 — already had gt x3)
- **tests/test_concurrency.py**: Fix backward transition logic, fix flaky timestamp test
- **.ralph/fix_plan.md**: task-025-LOOP marked [x]

## 已知问题

1. test_stress.py 挂起（sleep/threading-based 测试，需调查）
2. Guard hook Windows 兼容性（Bash vs PowerShell）
3. Hook 当前已关闭

## 未来工作建议

### 短期（源自 Loop 8 调研）
- **transition_reason 字段**: 在 engine.py transition_to() 添加可选 `reason` 参数，写入 history record
- **http_status body_contains**: 扩展 http_status handler 支持响应体内容匹配
- **idempotency key**: 绑定工具调用到状态迁移

### 中期（Phase 9 遗留）
- 9.3 并行条件评估（concurrent.futures 或 asyncio）
- 9.6 MCP Server 集成 (FastMCP @mcp.tool() 暴露条件)

### 长期（Phase 11）
- GitHub Actions CI、Docker 镜像、VS Code 扩展、Linear/Notion 同步
