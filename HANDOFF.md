# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-16
> **当前 Agent**: Ralph (Claude Code)
> **交接原因**: Phase 42 Complete — Default read tools with access-controlled sensitive stages

---

## task-141 会话总结 (2026-05-16)

### 做了什么
1. **Added 3 StageGuard tests** for write-tool omission with access.write:
   - `test_write_omitted_blocked_even_with_access_write_allow`
   - `test_multiedit_omitted_blocked_even_with_access_write_allow`
   - `test_notebook_edit_omitted_blocked_even_with_access_write_allow`
2. **Added 4 hook-level tests** for write-tool omission with access.write:
   - `test_edit_blocked_when_omitted_even_if_path_allowed`
   - `test_multiedit_blocked_when_omitted_even_if_path_allowed`
   - `test_notebook_edit_blocked_when_omitted_even_if_path_allowed`
   - `test_write_in_tools_still_obeys_access_write` — Write in tools but blocked by access.write.allow scope
3. **Updated CLAUDE.md** — 1669 tests (1539 Python + 130 editor), 1 skipped

### 当前状态
- task-141 complete: +7 tests (3 guard + 4 hook)
- Phase 42: tasks 139-141 done, 142-144 remain
- All 1669 tests pass, 1 skipped
- Write tools strictly stage-gated: tool-name check always enforced before access.write

### 下一步
task-142: Update docs and examples for default read tools

---

## task-140 会话总结 (2026-05-16)

### 做了什么
1. **Added 11 StageGuard tests** in `test_guard.py` (TestPathGuard class):
   - Default read tools allowed when omitted: Read, Grep, Glob without access policy
   - Read blocked by access.read.deny when omitted (deny-only: unlisted path still allowed)
   - Read blocked by access.read.allow when omitted (outside allow list → blocked)
   - Read allowed by access.read.allow when omitted (inside allow list → allowed)
   - Grep blocked by missing search root when read policy exists (fail-closed)
   - Grep blocked by access.read.deny directory coverage
   - Grep blocked by access.read.allow directory restrictions
   - Write-when-omitted still blocked
   - Edit-when-omitted still blocked
2. **Added 8 hook-level tests** in `test_main.py` (TestHookCommand class):
   - Glob allowed when omitted from tools
   - Read blocked/allowed by access.read.allow when omitted
   - Grep blocked by access.read.deny/allow dir when omitted
   - Grep blocked by missing search root when omitted
   - Glob blocked by access.read.deny when omitted
   - Write blocked when omitted even if path would pass access.write
3. **Updated CLAUDE.md** stats — 1662 tests (1532 Python + 130 editor), 1 skipped

### 当前状态
- task-140 complete: 19 new tests (11 guard + 8 hook), all passing
- Phase 42: tasks 139-140 done, 141-144 remain
- All 1532 Python + 130 editor = 1662 tests pass, 1 skipped

### 下一步
task-141: Preserve write-tool strictness — add/update tests proving Write/Edit/MultiEdit/NotebookEdit blocked when omitted from stage.tools

---

## task-139 会话总结 (2026-05-16)

### 做了什么
1. **Updated `stageflow/core/guard.py`** — `StageGuard.check()` now treats `Read`, `Grep`, `Glob` as default read tools:
   - When a run is active and the stage exists in the registry, read tools bypass the `stage.tools` name check
   - `access.read` policy still applies when present (deny/allow/path checks)
   - Write tools (`Write`, `Edit`, `MultiEdit`, `NotebookEdit`) remain strictly stage-gated
2. **Updated `stageflow/__main__.py`** `cmd_hook` — same default read-tool semantics in the hook entrypoint:
   - `Read`/`Grep`/`Glob` pass the tool-name allowlist gate even when omitted from `stage.tools`
   - Still checked against `access.read` when policy exists
3. **Updated `tests/test_main.py`** — replaced 2 old tests with 3 new tests:
   - `test_read_allowed_when_omitted_from_tools` — Read allowed without being in stage.tools
   - `test_read_blocked_by_access_read_deny_when_omitted_from_tools` — access.read.deny still blocks default reads
   - `test_grep_allowed_when_omitted_from_tools` — Grep allowed without being in stage.tools
4. **Updated `CLAUDE.md`** stats — 1643 tests (1513 Python + 130 editor), 1 skipped

### 当前状态
- task-139 complete: Phase 42 first task done
- All tests: 1513 passed, 1 skipped (Python), 130 passed (editor)
- No regressions
- Default read semantics: Read/Grep/Glob are baseline context tools; write tools remain explicit; sensitive stages add `access.read`

### 下一步
task-140: Update read-access tests — add hook-level and StageGuard tests proving both sides (allowed by default, blocked by access.read policy)

---

## task-134 会话总结 (2026-05-16)

### 做了什么
1. **Created `tests/test_access_layered.py`** — 44 layered tests across 8 layers of increasing difficulty:
   - Layer 1 (6 tests): Schema load — YAML with access policy parses into Stage.extra
   - Layer 2 (11 tests): Policy helper — AccessPolicy.check_read/check_write/check_search in isolation
   - Layer 3 (6 tests): StageGuard programmatic check with state file
   - Layer 4 (6 tests): Hook from project root via subprocess
   - Layer 5 (2 tests): Hook from nested CWD resolving relative paths
   - Layer 6 (4 tests): Windows/absolute path escapes blocked
   - Layer 7 (5 tests): YAML round-trip preserves access fields in Stage.extra
   - Layer 8 (4 tests): Old-workflow backward compatibility (no access policy)
2. **Created `docs/access_policy_verification.md`** — verification guide with exact commands and expected results for each layer, plus manual command examples
3. **Fixed initial test issues**: Layer 1 used wrong validation method (reg.validate() reports isolated stages), Layer 3/8 needed state file via StateMachine.initialize(), Layer 7 used wrong API (get_stage() not get_stage_info())

### 当前状态
- Phase 39: ALL 7 tasks complete (128-134) ✅
- All tests: 1499 passed, 1 skipped (was 1495; +44 from task-134)
- Editor tests: 130 passed (unchanged)
- New files: tests/test_access_layered.py (44 tests), docs/access_policy_verification.md
- All 8 layers pass independently and in sequence

### 已知问题
- None — Phase 39 is complete

---


### 做了什么
1. **Added `extra` field to `StageData` interface** (types.ts) — carries unknown YAML fields that aren't part of the standard stage shape
2. **Updated `exportToYaml`** (yaml.ts) — spreads `data.extra` into the output YAML stage dict, so fields like `access` survive serialization
3. **Updated `importFromYaml`** (yaml.ts) — captures any YAML keys other than name/tools/meta/on_enter/on_exit into `data.extra`
4. **Added 6 frontend round-trip tests** (yaml.test.ts):
   - access.read policy round-trip
   - access.write policy round-trip
   - empty access dict round-trip
   - unknown extra fields round-trip
   - stage without extra stays without extra
   - access alongside hooks round-trip

### 当前状态
- task-132 完成: editor YAML round-trip preserves access and all unknown fields
- Frontend tests: 136 passed (was 130, +6)
- Python tests: 865 passed, 1 skipped
- Phase 39: tasks 39.1-39.5 complete

### 下一步
task-133: Add checklist-completion condition demo — update or add example workflow showing verify→done blocked until task_plan.md has no unchecked items.

---

## task-131 会话总结 (2026-05-16)

### 做了什么
1. **Unified `StageGuard` with `cmd_hook`** — both now use `AccessPolicy`:
   - Removed hardcoded `_check_write_path` and `ALLOWED_WRITE_ROOTS` from guard.py
   - `StageGuard.check()` now imports and delegates to `AccessPolicy`
   - Same path resolution, same deny-over-allow, same variable interpolation
   - Both enforce identical access policy from `stage.extra.access`
   - `enforce_path_guard=False` still disables all path checking

2. **Updated 11 guard tests + added 4 new ones**:
   - Removed: old `test_read_always_allowed_if_in_tools` → replaced with `test_read_allowed_when_no_read_policy` and `test_read_blocked_by_read_policy`
   - Updated: write/Edit/NotebookEdit tests now use stages with access policy
   - Added: `test_write_missing_path_with_policy_fails_closed`
   - Added: `test_deny_overrides_allow` (programmatic guard deny precedence)
   - Added: `test_grep_search_root_checked` (programmatic guard search gating)

### 当前状态
- task-131 完成: guard.py unified with cmd_hook via AccessPolicy
- 全测试套件: 865 passed, 1 skipped, 0 failed (was 861, +4 guard tests)
- Phase 39: tasks 39.1-39.4 complete

### 下一步
task-132: Preserve access through editor import/export — ensure YAML round-trip doesn't drop access fields.

---

## task-130 会话总结 (2026-05-16)

### 做了什么
1. **Restructured `cmd_hook` in `__main__.py`** — wire AccessPolicy into the hook:
   - Split always-allow tools: non-file tools (TaskCreate, AskUserQuestion) always allowed; Read/Grep/Glob always tool-allowed but subject to read access policy
   - Project discovery moved before tool check so access policy can apply to Read
   - Added `_extract_file_path()` helper for NotebookEdit/Grep/Glob path extraction
   - Added `_log_hook_violation()` helper extracted from inline code
   - Added `_resolve_hook_path()` to resolve relative paths against CWD (fixes nested cwd)
   - Unrestricted stages (empty tools) with NO access policy still allow everything; with access policy, fall through to enforcement

2. **Added 18 hook-level access policy tests in `test_main.py`**:
   - Read allowed/blocked, deny-over-allow, missing path fails closed
   - Write allowed in run scope, blocked to source, missing path fails closed
   - Grep without path blocked, Grep in allowed dir works, Glob in denied dir blocked
   - Path escape blocked, absolute outside blocked
   - Nested CWD uses project root correctly
   - Old workflow no policy keeps behavior
   - NotebookEdit respects write policy (both allowed and blocked)
   - Edit respects write policy
   - Unrestricted stage with read policy still enforces access

### 修复的问题
- **Unrestricted stage early return**: restored when no access policy, so existing tests pass
- **Nested CWD path resolution**: relative paths now resolved against `Path.cwd()` before access check
- **Deny test path**: `config/secrets/db.yaml` → `secrets/db.yaml` to actually match `secrets/**` pattern

### 当前状态
- task-130 完成: `__main__.py` hook restructured + 18 hook tests
- 全测试套件: 861 passed, 1 skipped, 0 failed
- Phase 39: tasks 39.1/39.2/39.3 complete

### 下一步
task-131: Reconcile or remove duplicate guard behavior — unify StageGuard with cmd_hook.

---

## task-129 会话总结 (2026-05-16)

### 做了什么
1. **Created `stageflow/core/access_policy.py`** — core access policy evaluator:
   - `_interpolate()` — replaces `{{var.key}}` placeholders; unresolved vars → sentinel that never matches
   - `_normalize_path()` — resolves relative/absolute paths relative to project root, detects escapes
   - `_glob_to_regex()` — compiles path globs with `**` support to anchored regex
   - `_match_glob()` — uses regex for multi-segment patterns, fnmatch for single-segment filenames
   - `_pattern_prefix()` — extracts literal prefix from a glob pattern (stripping wildcards)
   - `_pattern_covers_dir()` — conservative check: only True when pattern provably covers entire directory
   - `AccessPolicy` class with `check_read()`, `check_write()`, `check_search()` public API
   - `has_policy`, `has_read_policy`, `has_write_policy` properties

2. **Created `tests/test_access_policy.py`** — 91 tests across 15 test classes:
   - TestInterpolate (7), TestNormalizePath (8), TestGlobToRegex (7), TestMatchGlob (9 plus fnmatch fallback fix)
   - TestPatternPrefix (4), TestPatternCoversDir (6), TestNoPolicy (3), TestDenyOnly (4), TestAllowOnly (4)
   - TestDenyOverAllow (2), TestVariableInterpolation (4), TestPathEscape (3), TestAbsolutePathInside (2)
   - TestCrossPlatform (3), TestCheckSearch (7), TestHasPolicy (5), TestIntegrationScenarios (6), TestFullPolicyExample (8)

### 修复的问题
- **SyntaxError**: raw string `r"...\"` — Python raw strings don't support escaped quotes. Fixed with regular string.
- **fnmatch Fallback leak**: fnmatch's `*` matches `/` on Windows; multi-segment patterns now always use regex, fnmatch only for single-segment filenames.
- **test_strips_double_star**: expected `"artifacts//plan"` but `_pattern_prefix` correctly produces `"artifacts/plan"` — updated test assertion.
- **test_prefix_under_dir**: expected True for pattern narrower than search root, but conservative implementation correctly returns False — updated test assertion.

### 当前状态
- task-129 完成: `access_policy.py` (296 lines) + `test_access_policy.py` (91 tests, all passing)
- 全测试套件: 729 passed, 1 skipped, 0 failed
- task-128 (schema) + task-129 (policy) = Phase 39.1 + 39.2 complete

### 下一步
task-130: Enforce access in `stageflow hook` entrypoint — wire `AccessPolicy` into `cmd_hook()`.

---

## task-128 会话总结 (2026-05-16)

### 做了什么
1. **Extended `stageflow/core/schema.py`** — added access policy validation:
   - `_validate_stage_access()` — validates `access` field on stage dicts
   - `_validate_access_section()` — validates `read`/`write` sub-sections (allow/deny lists)
   - Schema rejects: non-dict access, non-dict sections, non-list allows/denies, non-string items
   - Schema allows: missing access (backward compatible), empty access dict, empty sections
   - Validation integrated into the main `validate_stages_config()` loop
2. **Verified `Stage.extra` mechanism** in `registry.py` already preserves unknown fields like `access` through `__init__` and `to_dict()`
3. **Added 23 new tests** (116 total in test_registry.py, was 93):
   - **TestAccessPolicySchema** (20 tests): valid full policy, read-only, write-only, deny-only, empty access, empty sections, backward compat; invalid shapes (not dict, not list, non-string items); multiple errors reported; unknown fields preserved; access with hooks/max_iterations
   - **TestStageClass** (+3 tests): access preserved in extra, round-trip to_dict, no access is fine

### 当前状态
- Phase 39: task-128 complete
- Schema validates access policies: `access.read.allow`, `access.read.deny`, `access.write.allow`, `access.write.deny`
- Stage.extra preserves access through load→to_dict round-trip
- All 116 registry tests pass, mypy clean
- Next: task-129 — core path policy evaluation

### 已知问题
- Stage guard enforces analyze stage tools strictly; PowerShell/Bash access varies by environment
- For advancing stages: use `python -m stageflow next` (always-allowed in guard), create artifacts first if needed

---

## task-127 会话总结 (2026-05-16)

### 做了什么
1. **Updated `CLAUDE.md`**:
   - Added `stageflow editor` to CLI command table
   - Expanded "运行生命周期" section with editor as step 2 (two paths: AI generation + manual editing)
   - Added "工作流编辑器" subsection with save gate rules, both workflow paths, and CLI examples
2. **Updated `docs/api_reference.md`**:
   - Added `### editor` CLI reference section with all flags, project discovery, save gate
   - Added Editor Server API section documenting 6 endpoints: GET /api/project/config, GET /api/project/status, POST /api/project/save-config, GET /api/conditions, POST /api/validate, POST /api/run
3. **Updated `.ralph/AGENT.md`**:
   - Updated test count (1311 Python + 130 editor = 1441)
   - Added `stageflow editor` commands to Run section
   - Added "Editor Lifecycle" section with workflow diagram, dual paths, save gate, headless mode
   - Added `editor/` directory to project structure
   - Updated per-file test counts in project structure

### 当前状态
- Phase 38: all tasks (123-127) complete
- All tests: 1441 passed (1311 Python + 130 editor), 1 skipped
- fix_plan.md: all tasks marked [x], Phase 38 complete

### 已知问题
- None

---

## task-126 会话总结 (2026-05-16)

### 做了什么
1. **Created `tests/test_editor_e2e.py`** — 29 tests across 8 layers of increasing difficulty:
   - **Layer 1 (5 tests)**: Built dist exists — index.html, JS/CSS assets, index references JS, Save UI code in bundle
   - **Layer 2 (3 tests)**: FastAPI serves frontend — root returns HTML, index.html served, favicon
   - **Layer 3 (5 tests)**: Bound config API — custom YAML returned, save_allowed true/false based on run state, 404 when config missing, marker_type is "new"
   - **Layer 4 (5 tests)**: Save gate — blocked when active, allowed when no run, allowed after complete, invalid YAML preserves previous, save writes to bound path
   - **Layer 5 (3 tests)**: CLI startup — prints project root, reports custom host/port, fails outside project
   - **Layer 6 (2 tests)**: Nested directory — binds ancestor root, save from nested updates ancestor config
   - **Layer 7 (3 tests)**: Save round-trip — load→save→reload full cycle, active run blocks save, invalid YAML preserved
   - **Layer 8 (3 tests)**: Source isolation — external project doesn't touch source config, CLI doesn't mutate source state, multi-project isolation

### 当前状态
- Phase 38: tasks 123-126 complete
- All tests: 1311 passed, 1 skipped (was 1282; +29 from task-126)
- Editor tests: 130 passed (7 files, unchanged)
- Next: task-127 — update docs and usage examples

### 已知问题
- None

---

## task-125 会话总结 (2026-05-16)

### 做了什么
1. **Added `cmd_editor()` to `stageflow/__main__.py`** — discovers project root from cwd, rejects non-project/legacy projects, creates bound FastAPI app via `create_app(project_root=root)`, prints project info + URL, flushes stdout, opens browser (unless `--no-open`), starts uvicorn in foreground
2. **Added `editor` subparser** — `--host` (default 127.0.0.1), `--port` (default 8000), `--no-open` flag
3. **Added `sys.stdout.flush()`** before uvicorn startup — prevents pipe buffering from swallowing the startup banner in subprocess tests
4. **Added 8 CLI tests** (`TestCLIEditor` in test_main.py):
   - Help output: `test_editor_help`, `test_editor_in_main_help`
   - Outside project: `test_outside_project_fails`, `test_legacy_project_rejected`
   - Nested directory root binding: `test_nested_directory_shows_correct_root`
   - Port/host args: `test_custom_host_port_printed`
   - Port busy: `test_port_busy_fails_cleanly`
   - Startup info: `test_prints_project_info_at_startup`
5. **Subprocess pattern**: `_start_editor()` helper uses `stderr=subprocess.STDOUT` + background reader thread to avoid pipe-blocking; `_wait_for_output()` polls lines until marker appears

### 当前状态
- Phase 38: tasks 123-125 complete
- All tests: 1282 passed, 1 skipped (was 1255 Python; +27 from task-123/124/125)
- Editor tests: 130 passed (7 files, unchanged)
- Next: task-126 — end-to-end editor workflow tests

### 已知问题
- None

---

## task-124 会话总结 (2026-05-16)

### 做了什么
1. **Created `editor/src/utils/api.ts`** — typed API client with `fetchProjectConfig()`, `saveProjectConfig(yaml)`, `ApiError` class
2. **Added `loadFromYaml()` and `exportToYaml()` to Canvas imperative handle** — allows App to load project YAML into canvas and serialize current canvas to YAML
3. **Rewired `App.tsx`** — auto-loads project config on mount via `GET /api/project/config`, passes YAML to canvas; added Save button that serializes canvas to YAML and POSTs to `/api/project/save-config`; shows project root path in header; displays success/error/blocked status messages in the UI (not alerts)
4. **Added CSS** — `.save-btn`, `.app-save-status` (saved/error/blocked/saving), `.app-project-path`, `.app-load-error` with dark theme variants
5. **Built `editor/dist`** — tsc + vite build, 231 modules, dist updated with auto-load + Save UI
6. **Added 23 new frontend tests** (130 total, was 107):
   - `api.test.ts` (8 tests): fetchProjectConfig success/400/404/500, saveProjectConfig success/403/400/POST body
   - `App.test.tsx` (+15 tests): auto-load (fetch called, YAML loaded to canvas, project path shown, 500/404 errors, 400 silent), save button (renders, calls export+save, success/blocked/error states, disabled when not allowed, enabled when allowed), export preserved

### 当前状态
- Phase 38: tasks 123-124 complete
- Server tests: 80 passed
- Non-editor tests: 1194 passed, 1 skipped
- Editor tests: 130 passed (7 files)
- Editor build: tsc clean, vite build produces dist/
- Next: task-125 — add `stageflow editor` CLI command

### 已知问题
- Save button disabled title doesn't show the reason unless you hover (minor UX)

---

## task-123 会话总结 (2026-05-16)

### 做了什么
1. **Added `_resolve_project_root(request)` and `_get_project_root_or_raise(request)` helpers** to `editor/server.py` — checks `request.app.state.project_root` first (bound root), falls back to `discover_project()` from cwd
2. **Added `create_app(project_root=None)` factory** — creates a new FastAPI editor app bound to a specific StageFlow project root for its lifetime, sharing all routes from the reference app
3. **Added `GET /api/project/config` endpoint** — returns config YAML, config_path, project_root, marker_type, current_stage, run_status, and save_allowed boolean
4. **Added `GET /api/project/status` endpoint** — returns current_stage, run_status, final_stage, completed_at, run_id, save_allowed, history_count, variable_keys, retry_count, iterations, state_path, config_path, project_root, marker_type
5. **Updated `POST /api/project/save-config`** — now uses `_get_project_root_or_raise(request)` instead of inline `discover_project()`, so bound app uses its project root without rediscovery
6. **Updated `main()`** — added `--project-root` argument; when provided, discovers the project and creates a bound app via `create_app()`
7. **Set `app.state.project_root = None`** on the module-level app (backward compatible — discovery from cwd)
8. **Added 19 tests** (TestProjectBoundAPIs class in test_server.py):
   - Config: returns YAML, save_allowed true when no run, save_allowed false when active, 400 outside project, 404 missing file
   - Status: after init, after complete, during active run, outside project
   - Bound root: save targets bound root not cwd, save gate reads bound state, config loads from bound root, status from bound root
   - Invalid YAML: doesn't overwrite previous config (2 variants), bound app save failure preserves bytes
   - Legacy: config loading, status, save blocked active run

### 当前状态
- Phase 38: task-123 complete
- Test suite: 1274 passed (1194 non-editor + 80 server), 1 skipped
- Server tests: 80 passed (61 existing + 19 new), 0 failed
- Next: task-124 — wire frontend to project APIs and rebuild served assets

### 已知问题
- No regressions; editor frontend not yet calling /api/project/config or /api/project/status

---

## task-122 会话总结 (2026-05-16)

### 做了什么
1. **Created `tests/test_staged_verification.py`** — 21 staged verification tests across 7 layers of increasing difficulty
2. **Layer 1 (4 tests)**: Engine-only complete — succeeds at terminal, fails non-terminal, fails no run, metadata prerequisites
3. **Layer 2 (4 tests)**: Status output — no active run after init, active after start, JSON after complete, no active after reset
4. **Layer 3 (2 tests)**: CLI complete from project root — full lifecycle, refused at non-terminal
5. **Layer 4 (2 tests)**: CLI complete from nested directory — from src/lib/deep, status from a/b/c
6. **Layer 5 (2 tests)**: Multi-repo isolation — repo A complete doesn't touch repo B, source checkout unaffected
7. **Layer 6 (2 tests)**: Run-scoped artifacts — stale artifacts don't unlock new run, independent artifact dirs
8. **Layer 7 (5 tests)**: Editor save gate — allowed after init/complete/reset, blocked during active/terminal-before-complete
9. **Created `docs/staged_verification.md`** — exact commands and expected outputs for each layer, AI agent can replay
10. **1255 tests passing**, 1 skipped (unchanged)

### 当前状态
- Phase 37: ALL 5 tasks complete (118-122) ✅
- Test suite: 1255 passed, 1 skipped
- All Phase 37 hard acceptance rules verified across 7 layered tests

### 已知问题
- No remaining issues in Phase 37
- fix_plan.md has no more unchecked tasks — next phase needs to be defined

## task-121 会话总结 (2026-05-16)

### 做了什么
1. **Added `POST /api/project/save-config` endpoint** to `editor/server.py` — save gate using StageFlow project root discovery
2. **Save gate logic**: discovers project root from cwd, reads `current_stage` from state file, blocks save (403) when non-null, allows when null
3. **Gate allows**: after `init` (no current_stage), after `complete` (null + run_status="completed"), after `reset` (null, no run_status)
4. **Gate blocks**: any active run (current_stage set to any stage name, including terminal stage if not completed)
5. **Saves to** discovered `.stageflow/config/stages.yaml` (new-style) or legacy path
6. **12 new tests** in `test_server.py` (49→61): TestProjectSaveGate class covering all gate states
7. **1234 tests passing**, 1 skipped (unchanged)

### 当前状态
- Phase 37: 121/122 tasks complete
- Serving save-gate capability to the React editor via `/api/project/save-config`
- Next: task-122 — staged verification

### 已知问题
- Editor end-to-end component tests unchanged (107 passing) — frontend must call `/api/project/save-config` instead of `/api/workflows/{name}` to get save-gate protection

## task-120 会话总结 (2026-05-16)

### 做了什么
1. **Updated cmd_status** — human output now distinguishes three states:
   - Completed run: shows Run Status, Final Stage, Completed At, Run ID
   - No active run: shows guidance to use stageflow start
   - Active run: shows current stage, tools, available next, etc. (unchanged)
2. **Updated CLAUDE.md** — added complete command to CLI reference, added lifecycle documentation section (init -> start -> next -> complete -> reset)
3. **Updated docs/api_reference.md** — added complete command section, added complete() to StateMachine API table, added usage example
4. **Updated .ralph/AGENT.md** — added complete command to Run section, updated reset comment (abandon/restart), updated lifecycle note
5. **Fixed test** — test_status_verbose_uninitialized updated for new No active run message

### 测试结果
- test_main.py: 210/210 passed
- Full non-editor suite: 1173 passed, 1 skipped

### 下一步
- **task-121**: Connect completion semantics to workflow editor save behavior

---

## task-119 会话总结 (2026-05-16)

### 做了什么
1. **Added `cmd_complete()` to `__main__.py`**:
   - Uses `_require_sm()` for project discovery
   - Rejects no-active-run with guidance to `stageflow start`
   - Rejects non-terminal stages via `sm.complete()` return
   - Calls Python core API directly (no shell-out to scripts)
2. **Added `complete` subparser** — no positional args, no `--force`
3. **Updated `cmd_next`** — terminal-stage guidance now points to `stageflow complete`
4. **Added 10 CLI tests** (`TestCLIComplete` class in test_main.py):
   - complete from terminal stage (success, metadata verified)
   - complete fails: no active run, non-terminal, outside project
   - complete rejects positional arguments (no shortcut)
   - preserves run_id, preserves history
   - works from nested subdirectory
   - next guides to complete at terminal
   - multi-repo isolation (completion in repo A doesn't touch repo B)

### 测试结果
- TestCLIComplete: 10/10 passed
- test_main.py: 210/210 passed
- Full non-editor suite: 1173 passed, 1 skipped

### 下一步
- **task-120**: Update status output, docs, and agent instructions

---

## task-118 会话总结 (2026-05-16)

### 做了什么
1. **Added `StateMachine.complete()` method** to `engine.py`:
   - Validates run is active (`current_stage is not None`)
   - Validates current stage exists in registry config
   - Validates terminal status: zero outgoing transitions (structural, not name-based)
   - Runs terminal-stage `on_exit` hooks (consistent with normal transitions)
   - Records completion history entry: `{from: stage, to: null, reason: "run completed"}`
   - Persists metadata: `run_status: "completed"`, `completed_at` (ISO-8601 UTC), `final_stage`
   - Sets `current_stage` to `null` (without deleting state file)
   - Preserves `variables.run_id` and existing history
   - Writes `run_completed` audit event
2. **Updated `status()` method** to expose `run_status`, `final_stage`, `completed_at` when present in state
3. **Added 15 tests** in `TestComplete` class (test_engine.py):
   - Fails: no active run, non-terminal stage, stage missing from config
   - Succeeds: terminal stage, sets current_stage=null, preserves state file/run_id/history/artifacts
   - Records metadata (run_status, final_stage, completed_at)
   - Runs exit hooks, logs audit event
   - Fresh SM loads completed state correctly
   - Works with custom stage names (no hardcoded defaults)
   - Pause does not block completion

### 测试结果
- TestComplete: 15/15 passed
- test_engine.py: 112/112 passed (was 97, +15)
- Full non-editor suite: 1163 passed, 1 skipped

### 下一步
- **task-119**: Add `stageflow complete` CLI command

---

## task-100 会话总结 (2026-05-16)

### 做了什么
按照递进难度执行分层验证，每层通过后才进入下一层：

| Layer | 描述 | 命令 | 结果 |
|-------|------|------|------|
| 1 | Root discovery/init/start/reset | `pytest tests/test_discovery.py tests/test_main.py::TestNewInitAndStart tests/test_main.py::TestResetAndJumpHardening -v` | **44 passed** |
| 2 | CLI smoke | `pytest tests/test_main.py::TestCLISmoke -v` | **11 passed** |
| 3 | Nested/multi-repo | `pytest tests/test_main.py::TestNestedDirectoryCommands tests/test_main.py::TestMultiRepoIsolation -v` | **18 passed** |
| 4 | AI-style e2e | `pytest tests/test_main.py::TestAIWorkflowE2E -v` | **14 passed** |
| 5 | Full non-editor suite | `pytest tests/ --ignore=tests/test_server.py --ignore=tests/test_editor.py -q` | **1140 passed, 1 skipped** |
| 6 | Editor/server | `pytest tests/test_server.py -v` | **49 passed** |

**总计**: 1276 tests passed (across all layers, with overlap in full suite), 0 failures.

### Phase 29 完成总结
- **task-093**: Harden reset/jump semantics (8 tests)
- **task-094**: Global hook entrypoint `stageflow hook` (15 tests)
- **task-095**: Legacy migration `stageflow migrate` (15 tests)
- **task-096**: Documentation update (CLAUDE.md, AGENT.md, api_reference.md)
- **task-097**: CLI smoke-test layer (11 tests)
- **task-098**: Multi-repo isolation tests (10 tests)
- **task-099**: AI-style e2e workflow tests (14 tests)
- **task-100**: Staged verification — all layers pass

### 下一步
- **fix_plan.md 全部 100 任务完成** — 可进行项目全面审查或开始新 Phase

---

## task-099 会话总结 (2026-05-16)

### 做了什么
1. **新增 `TestAIWorkflowE2E` 测试类** (14 tests) 到 `tests/test_main.py`，使用 4 阶段自定义 YAML（stage 名称: investigate/implement/verify/deliver）:

   **场景 (1) — bootstrap and start:**
   - `test_bootstrap_and_start_first_stage` — init + start，验证 first stage="investigate" + run_id
   - `test_start_specific_stage` — 从指定 stage 启动

   **场景 (2) — artifacts and advance:**
   - `test_advance_through_two_stages_with_artifacts` — 创建 findings.md → advance to implement，创建 patch.diff → advance to verify
   - `test_transition_blocked_without_artifact` — 缺少 artifact 时 next 失败且不改变 stage
   - `test_full_pipeline_investigate_to_deliver` — 完整 4 阶段流水线，创建所有 artifacts

   **场景 (3) — resume from nested subdir:**
   - `test_resume_from_nested_subdir_in_new_process` — 从嵌套目录读取 status --json，验证相同 run_id，继续推进

   **场景 (4) — stale artifacts don't unlock new run:**
   - `test_stale_artifacts_dont_unlock_new_run` — reset + 新 run_id 后，使用 `{{var.run_id}}` 插值的条件不会被旧 run artifacts 满足

   **场景 (5) — hook blocks/permits by discovered root:**
   - `test_hook_permits_allowed_tool_in_investigate` — 允许 Read
   - `test_hook_blocks_disallowed_tool_in_investigate` — 阻止 Edit
   - `test_hook_allows_edit_in_implement_stage` — implement stage 允许 Edit
   - `test_hook_from_nested_subdir_uses_discovered_root` — 嵌套目录 hook 也使用发现的项目根
   - `test_hook_allows_everything_in_deliver_stage` — 空 tools list 允许所有工具
   - `test_hook_violation_logged` — 违规记录到 guard_violations.jsonl

   **Package isolation:**
   - `test_package_source_unchanged` — 完整 AI 工作流后源码包未被修改

2. **Transition 条件使用 `{{var.run_id}}` 变量插值**，实现按 run 隔离的 artifact 检查

3. **添加 `_run_hook` 辅助方法** — 支持 stdin 输入的 hook 子进程调用

### 测试结果
- **TestAIWorkflowE2E**: 14/14 passed
- **test_main.py 全部**: 192/192 passed
- **Full non-editor suite**: 1140 passed, 1 skipped

### 下一步
- **task-100**: Run staged verification — increasing difficulty layers, document results

---

## task-098 会话总结 (2026-05-16)

### 做了什么
1. **新增 `TestMultiRepoIsolation` 测试类** (10 tests) 到 `tests/test_main.py`:
   - `test_repo_a_deep_nested_touches_only_repo_a` — 从 `repo_a/src/lib/deep` 运行命令仅影响 repo_a
   - `test_repo_b_deep_nested_touches_only_repo_b` — 从 `repo_b/apps/nested/deep` 运行命令仅影响 repo_b
   - `test_reset_in_repo_a_does_not_affect_repo_b` — repo_a 的 reset 不影响 repo_b 状态
   - `test_start_from_nested_in_repo_a_after_reset` — reset 后从嵌套目录重新 start
   - `test_outside_both_projects_fails` — 两个项目之外的目录报 "Not a StageFlow project"
   - `test_package_source_not_mutated` — 运行多 repo 操作后，StageFlow 源码包的 `.claude/current_stage.json` 和 `.stageflow/` 未被修改
   - `test_multi_repo_status_json_from_nested` — 两个 repo 各自从嵌套目录获取 JSON 状态
   - `test_multi_repo_list_shows_correct_project` — list 命令只显示当前项目的 stages
   - `test_next_dry_run_from_each_project` — 两个项目各自 dry-run 互不干扰
   - `test_no_legacy_state_file_in_either_repo` — 两个新项目都不产生 legacy state 文件

2. **使用不同的 stage 名称区分两个项目**: repo_a 用 alpha/beta, repo_b 用 uno/dos

3. **添加 `_init` 辅助方法** — 一步完成目录创建 + init + 写入自定义 YAML

### 测试结果
- **TestMultiRepoIsolation**: 10/10 passed
- **test_main.py 全部**: 178/178 passed
- **Full non-editor suite**: 1126 passed, 1 skipped

### 下一步
- **task-099**: AI-style e2e workflow tests with progressively harder scenarios

---

## task-096 会话总结 (2026-05-16)

### 做了什么
1. **Updated `CLAUDE.md`** — comprehensive rewrite of user-facing sections:
   - 快速开始: replaced `python scripts/stage_next.py` with `stageflow start`/`stageflow next`, added Git-like explanation
   - CLI 命令: complete rewrite with all current commands (init, start, migrate, hook, etc.) organized by category
   - 阶段转移脚本: deprecated old scripts, mapped them to new CLI equivalents
   - 运行身份与产物隔离: updated to new reset/start semantics (no more `reset <stage>`)
   - 工具拦截: documented global `stageflow hook` entrypoint and discovery-based root resolution
   - 工作约束: updated to reference `stageflow next` instead of `stage_next.py`
   - 目录结构: added `.stageflow/`, discovery.py, updated test counts
   - 项目统计: updated to 1154 tests, 18 modules
2. **Updated `.ralph/AGENT.md`** — rewritten Run section with full CLI commands, updated project structure, added new-style project notes
3. **Updated `docs/api_reference.md`** — new commands documented (init as project bootstrap, start, migrate, hook), old reset syntax removed, jump --reason added

### 当前状态快照
```
Phase 29:        task-096 complete
Next task:       task-097 — CLI smoke-test layer
fix_plan.md:     96/100 tasks complete
Tests:           1154 passed, 1 skipped, 0 failed
```

---

## task-095 会话总结 (2026-05-16)

### 做了什么
1. **Added `cmd_migrate` to `__main__.py`** — `stageflow migrate` converts legacy projects to new-style:
   - Detects legacy project via discover_project()
   - Creates .stageflow/config/stages.yaml (copied from legacy config)
   - Creates .stageflow/current_stage.json (copied from legacy state)
   - Copies guard_violations.jsonl if present in legacy audit dir
   - Preserves all old files (manual cleanup)
   - Already new-style → prints "Already a new-style project"
   - Outside project → fails with actionable message
   - --force overwrites existing .stageflow/ directory
2. **Added `migrate` CLI subcommand** with optional path arg and --force flag
3. **Added TestLegacyCompatibility** (15 tests):
   - Basic commands on legacy projects: status, status --json, start, next, check, reset, list, graph
   - State writes to .claude/current_stage.json (not .stageflow/)
   - Status works from nested subdirectory
   - migrate: converts to new-style, preserves run_id, does not delete old files, idempotent, fails outside project
4. **Added TestMixedMarkerPrecedence** (3 tests):
   - .stageflow/ wins over legacy stageflow/config/stages.yaml + .claude/current_stage.json
   - .claude/current_stage.json alone works (legacy_state_only)
   - legacy_state_only next fails without config file

### 当前状态快照
```
Phase 29:        task-095 complete
Next task:       task-096 — update documentation for new usage model
fix_plan.md:     95/100 tasks complete
Tests:           1154 passed, 1 skipped, 0 failed
```

---

## task-094 会话总结 (2026-05-16)

### 做了什么
1. **Added `cmd_hook` to `__main__.py`** — Claude Code PreToolUse hook entrypoint:
   - Reads stdin JSON (hook protocol: `{"tool_name": "...", "tool_input": {...}}`)
   - Always-allow tools: TaskCreate, TaskUpdate, TaskList, TaskGet, TaskOutput, Read, AskUserQuestion
   - Always-allow Bash commands: `python -m stageflow *`, `python scripts/stage_*.py`, `python -c`
   - Discovers project root from cwd via `discover_project()`
   - Loads StageRegistry + StateMachine from discovered root
   - Checks stage tool allowlist (exact match + Bash(pattern) constraint matching)
   - Strips Windows `cd /d` prefix from commands before matching
   - Logs violations to `<root>/.stageflow/guard_violations.jsonl` (new-style) or `<root>/.claude/guard_violations.jsonl` (legacy)
   - Outputs `{"decision": "allow", ...}` or `{"decision": "block", "reason": "..."}` JSON
2. **Added `hook` CLI subcommand** — `python -m stageflow hook`
3. **Added 15 tests** in `TestHookCommand` class:
   - always-allowed tools (Read, TaskCreate)
   - block Edit in restricted alpha stage
   - allow Grep/Write in appropriate stages
   - violation logging under discovered root
   - hook works from nested subdirectory (block + allow)
   - allows everything outside project or in bootstrap mode
   - malformed input → allow (avoid deadlock)
   - Bash pattern matching (git allowed, npm blocked)
   - always-allow operational stageflow commands
   - unrestricted stage (empty tools) allows anything

### 设计决策
- Hook follows same protocol as existing `.claude/hooks/stage_guard.py` for drop-in replacement
- `stageflow init` already writes `.claude/settings.json` pointing to `stageflow hook` (from task-090)
- Violations logged to `.stageflow/guard_violations.jsonl` for new-style projects (audit_dir)
- Gracefully allows on parse errors, missing project, or missing state to prevent deadlock
- Uses `discover_project()` so hook works from any subdirectory

### 当前状态快照
```
Phase 29:        task-094 complete
Next task:       task-095 — migration and compatibility for legacy repos
fix_plan.md:     94/100 tasks complete
Tests:           1136 passed, 1 skipped, 0 failed
```

### 已知问题
- Stage guard keeps resetting state file to analyze during work
- Existing `.claude/hooks/stage_guard.py` still works for backward compatibility

---

## task-093 会话总结 (2026-05-16)

### 做了什么
1. **Removed stage positional arg from `stageflow reset`** — `cmd_reset` now only clears state, `--hard` differentiates output message ("fully reset" vs "cleared")
2. **Removed `--reuse-run` from `stageflow start`** — separated reset/start model makes reuse-run semantically impossible: `reset()` always clears state, so `start --reuse-run` has nothing to reuse. Users who want to restart the same run should not call reset first.
3. **Enforced `--reason` on `jump --force`** — `cmd_jump` now requires `--reason '...'` when `--force` is used, for audit trail
4. **Added TestResetAndJumpHardening** (8 tests):
   - test_reset_with_stage_fails_clear_error — reset <stage> rejected with usage error
   - test_plain_reset_clears_state_without_stage — plain reset clears run, prints guidance
   - test_reset_hard_clears_state — reset --hard clears state
   - test_forced_jump_requires_reason — jump --force without --reason fails
   - test_forced_jump_with_reason_works — jump --force --reason succeeds
   - test_jump_without_force_still_condition_gated — normal jump requires conditions
   - test_next_remains_condition_gated — normal next must pass conditions
   - test_next_force_succeeds — next --force bypasses conditions
5. **Updated 5 existing tests** for new semantics:
   - test_jump_force → added --reason flag
   - test_reset_hard → changed to accept new output message
   - test_status_json_output → added explicit reset+start before status check
   - test_resume_keeps_run_id_in_new_session → added reset before start
   - test_status_run_id_changes_after_reset → added explicit reset between runs
6. **Removed 3 tests** that used removed --reuse-run on start:
   - test_start_reuse_run_preserves_run_id (TestResetAndJumpHardening)
   - test_status_run_id_preserved_after_reset_reuse (TestStageflowCLI)
   - test_reset_reuse_run (TestMainInProcess)

### 设计决策
- `--reuse-run` on start removed because the separated reset/start model always clears state on reset, so there's nothing to reuse
- Keeping run_id across resets would require a different mechanism not exposed at CLI level yet
- Jump --force --reason provides audit trail without changing engine internals

### 当前状态快照
```
Phase 29:        task-093 complete
Next task:       task-094 — global hook entrypoint (stageflow hook command)
fix_plan.md:     93/100 tasks complete
Tests:           1121 passed, 1 skipped, 0 failed
```

### 已知问题
- Stage guard keeps resetting state file to analyze during work; need to force-advance after state mutations
- Legacy state file at .claude/current_stage.json conflicts with tests that manipulate state from PROJECT_ROOT

---

## task-092 会话总结 (2026-05-16)

### 做了什么
1. **Fixed cmd_status, cmd_graph, cmd_list** — now use _require_sm() instead of _get_sm(), so they fail closed with "Not a StageFlow project" when outside any project
2. **Added TestNestedDirectoryCommands** (8 tests) proving root isolation:
   - test_status_from_nested_subdir_sees_correct_stage — status from src/lib/deep sees project root stage
   - test_start_from_nested_subdir_mutates_only_project_root — start from deep subdir, state written only at root
   - test_next_dry_run_from_nested_subdir — next --dry-run works from nested dir
   - test_reset_from_nested_subdir_mutates_only_project_root — reset only touches root state
   - test_no_legacy_state_file_created_in_new_project — no .claude/current_stage.json in new-style projects
   - test_package_source_tree_not_mutated — negative assertion on package source isolation
   - test_outside_project_fails_from_any_dir — status/next outside project fail with actionable message
   - test_status_json_from_nested_subdir — JSON status from nested dir
3. **Verified all 1115 tests pass**

### 当前状态快照
Phase 29:        task-092 complete (implementation already in place from task-090, tests now added)
Next task:       task-093 — harden reset and recovery semantics
fix_plan.md:     92/100 tasks complete
Tests:           1115 passed, 1 skipped, 0 failed

### 已知问题
- Stage guard keeps resetting state file to analyze during work
- cmd_reset still accepts stage positional arg (will be changed in task-093)
- Next agent should work on task-093: remove stage arg from reset, add --reason to jump, etc.

---

## task-091 会话总结 (2026-05-16)

### 做了什么
1. **Reviewed cmd_start implementation** — already solid from task-090: discovers root, uses insertion-order entry stage, fails when run active, writes state to discovered path
2. **Added 2 custom YAML tests** to TestNewInitAndStart:
   - test_start_with_custom_yaml_enters_first_stage — replaces default YAML with custom stages (alpha/beta/gamma), verifies start enters "alpha" (first in YAML order)
   - test_start_custom_yaml_specific_stage — verifies start beta works with custom YAML
3. **Verified all 1107 tests pass**

### 当前状态快照
Phase 29:        task-091 complete
Next task:       task-092 — all CLI commands on discovered project root (partially implemented)
fix_plan.md:     91/100 tasks complete
Tests:           1107 passed, 1 skipped, 0 failed

### 已知问题
- Stage guard keeps resetting state file to analyze during work
- Tasks 092 is partially implemented (all commands already use _require_sm / _get_sm)
- Next agent should review task-092 against requirements, add tests from nested subdirectories, mark complete

---

## task-090 会话总结 (2026-05-16)

### 做了什么
1. **Rewrote cmd_init in __main__.py** — stageflow init is now project bootstrap:
   - Creates .stageflow/config/stages.yaml (default 10-stage pipeline)
   - Creates .claude/settings.json (PreToolUse hook pointing to stageflow hook)
   - Creates artifacts/runs/ directory
   - Does NOT create an active run unless --start is given
   - --force overwrites config while preserving existing state
   - Idempotent: prints already initialized on re-run
   - Blocks nested project creation inside parent project
2. **Added cmd_start** — explicit run startup:
   - stageflow start begins at first YAML stage (insertion order)
   - stageflow start <stage> starts at specific stage
   - Fails if run already active or outside project
3. **Added _get_sm() / _require_sm() helpers** — project-discovery-aware SM creation
4. **Updated all CLI commands** to use discovered project root
5. **Added state_file param to StateMachine.__init__** for custom state paths
6. **Changed stage_names from sorted to insertion order** — first YAML stage = entry
7. **Added TestNewInitAndStart** (15 tests): init, idempotent, force, start, nested blocking, etc.
8. **Fixed 6 legacy tests** for new init/start semantics and insertion-order stage_names

### 设计决策
- init <path> not init <stage> — positional arg is now a directory path
- --start convenience flag for bootstrap+run in one command
- Insertion order for stage_names critical for entry stage semantics

### 当前状态快照
Phase 29:        task-090 complete
Next task:       task-091 (partially implemented, needs review)
fix_plan.md:     90/100 tasks complete
Tests:           1105 passed, 1 skipped, 0 failed
Uncommitted:     4 files (__main__.py, engine.py, registry.py, test_main.py)

### 已知问题
- Stage guard keeps resetting state file to analyze during work
- Tasks 091-092 are partially implemented in uncommitted code
- Next agent should review and commit incrementally

---

## task-089 会话总结 (2026-05-16)

### 做了什么
1. **Marked task-088 as complete** in fix_plan.md (design doc was already written in prior session)
2. **Created `stageflow/core/discovery.py`** — project-root discovery module:
   - `ProjectRoot` frozen dataclass with fields: `path`, `marker_type`, `config_path`, `state_path`, `artifacts_dir`, `audit_dir`
   - `discover_project(start_path=None)` — walks upward from cwd finding StageFlow markers
   - Marker priority at each level: `.stageflow/` (new) > `stageflow/config/stages.yaml` (legacy) > `.claude/current_stage.json` (legacy_state_only)
   - Stops at filesystem root / Windows drive root
   - Symlink-safe: resolves start_path but not each parent
3. **Created `tests/test_discovery.py`** — 18 tests across 7 classes:
   - `TestDiscoverNewStyle` (6): from root, child dir, deeply nested, no project, artifacts_dir, audit_dir
   - `TestDiscoverLegacy` (3): config marker, from child, state-only marker
   - `TestMarkerPriority` (2): new beats legacy, legacy beats state-only
   - `TestNestedProjects` (2): nearest ancestor wins, deep nested falls back to outer
   - `TestFilesystemBoundaries` (3): stops at /, stops at C:\, temp dir no marker
   - `TestProjectRootImmutability` (1): frozen dataclass
   - `TestCurrentDirectoryDefault` (1): uses cwd when no start_path given

### 当前状态快照
```
Phase 29:        task-089 complete (discovery module + 18 tests)
Next task:       task-090 — redefine stageflow init as project bootstrap
fix_plan.md:     89/98 tasks complete
Tests:           1089 passed, 1 skipped, 0 failed
```

---

## task-088 会话总结 (2026-05-16)

### 做了什么
1. **Created `docs/git_like_design.md`** — comprehensive design and requirements document for Git-like StageFlow CLI (Phase 29):
   - Section 2: Project marker discovery algorithm (`.stageflow/` > `stageflow/config/stages.yaml` > `.claude/current_stage.json`)
   - Section 3: `stageflow init` redefined as project bootstrap (no more `init <stage>`)
   - Section 4: Command classification — which commands require a project vs. work anywhere
   - Section 5: Path resolution rules for new-style vs. legacy projects
   - Section 6: Global `stageflow hook` entrypoint design
   - Section 7: Nested project behavior (nearest ancestor wins)
   - Section 8: Migration path for legacy projects (automatic compatibility, opt-in migration)
   - Section 9: Safeguards — package source isolation, test strategy, discovery module purity
   - Section 10: Implementation order for tasks 088-098
   - Section 11: Non-goals (no state machine changes, no editor changes, no remote sync)
   - Section 12: Open decisions (template flag, `stageflow root` command, env var override, gitignore)

### 关键设计决策
- **New projects use `.stageflow/`** as the authoritative metadata directory
- **Legacy projects** (`stageflow/config/stages.yaml` + `.claude/current_stage.json`) continue working without migration
- **`stageflow init` means "create project"** not "set current stage" — use `stageflow reset <stage>` for that
- **Discovery walks upward from cwd** like Git, nearest marker wins
- **Commands outside a project fail closed** with actionable message
- **Global hook** (`stageflow hook`) eliminates need to copy hook scripts between projects

### 当前状态快照
```
Phase 29:        task-088 complete (design doc written)
Next task:       task-089 — implement root discovery module
fix_plan.md:     88/98 tasks complete
```

---

## task-087 会话总结 (2026-05-15)

### 做了什么
1. **Created `scripts/phase27_acceptance.py`** — Phase 27/28 targeted acceptance script:
   - Runs 5 pytest suites (76 tests) + editor fidelity verification
   - Each pytest suite gets a unique `--basetemp` subdirectory under `.tmp/` to avoid cross-suite file locking on Windows
   - Sets `TEMP`, `TMP`, `PYTEST_DEBUG_TEMPROOT` to repo `.tmp` on Windows
   - Cleans all temp content from previous runs on startup
   - UTF-8 stdout wrapper to avoid GBK encoding issues
   - Supports `--verbose`, `--json` flags
   - All 76 tests pass + editor fidelity ALL CHECKS PASSED

### Exact acceptance command
```bash
python scripts/phase27_acceptance.py
```

### Expected passing output
```
  [OK] Engine — Run Identity: PASS    (14 passed)
  [OK] E2E — Run-Scoped Artifacts: PASS (3 passed)
  [OK] Hybrid — Prompts & Status: PASS  (10 passed)
  [OK] CLI — Resume & Reset: PASS       (34 passed)
  [OK] Demo — Sequential Two-Task: PASS (15 passed)
  [OK] Editor Fidelity: PASS
-- ALL CHECKS PASSED --
Phase 27 acceptance criteria satisfied.
```

### Verification targets
| Suite | What | Tests |
|-------|------|-------|
| Engine — Run Identity | TestRunIdentity, TestCleanArtifacts, TestResumeSemantics | 14 |
| E2E — Run-Scoped Artifacts | TestRunScopedArtifacts (old-run isolation regression) | 3 |
| Hybrid — Prompts & Status | TestRunScopedPrompts, TestStagePrompts, TestStatus | 10 |
| CLI — Resume & Reset | 3 resume CLI tests + TestMainInProcess (31 in-process tests) | 34 |
| Demo — Sequential Two-Task | test_run_demo.py (all 6 classes) | 15 |
| Editor Fidelity | verify_editor_fidelity.py | 11 templates |

### 测试结果
- phase27_acceptance.py: 76 passed, 0 failed across 5 pytest suites
- Editor fidelity: ALL CHECKS PASSED
- JSON mode: working

### 已知问题
- Stage guard keeps resetting state file to "analyze" during test runs
- Shell tool name mismatch (Bash vs PowerShell) on Windows

---

## task-086 会话总结 (2026-05-15)

### 做了什么
1. **Created scripts/verify_editor_fidelity.py** — verification script that:
   - Reads default stageflow/config/stages.yaml (11 {{var.run_id}} templates)
   - Performs YAML round-trip (parse + re-serialize, simulating editor js-yaml import/export)
   - Verifies all 11 templates survive with no escaping, resolution, or deletion
   - Checks 6 expected run-scoped paths are present in output
   - Verifies no UUID was resolved from the template
   - Result: ALL CHECKS PASSED
2. **Built editor frontend** — 	sc && vite build:
   - TypeScript compiles clean
   - Vite produces: dist/index.html, dist/assets/index.css (18.99 kB), dist/assets/index.js (429.27 kB / 135.44 kB gzip)
   - Build: 230 modules transformed in 143ms

### 测试结果
- verify_editor_fidelity.py: ALL CHECKS PASSED
- Editor build: PASSED (tsc + vite)
- Full test suite: 1071 passed, 1 skipped

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

---

## task-142 会话总结 (2026-05-16)

**做了什么**: 更新了所有文档以反映 Phase 42 的语义变更：
- `.ralph/AGENT.md`: 更新测试计数 (1539+130=1669)、每个文件的测试计数、新增默认读取工具和文件访问策略说明
- `CLAUDE.md`: 已在上一会话中更新——新增"默认读取工具 (Phase 42)"和"细粒度文件访问控制 (access 策略)"子章节，附完整 YAML 示例
- `docs/api_reference.md`: 已在上一会话中更新——扩展 StageGuard 文档，附 enforce_path_guard 参数和工具检查顺序

**当前状态**: task-142 完成。处于 implement 阶段。
**下一步**: task-143 — 在 D:\2026_zju\test 下运行真实外部 CLI smoke demo
**提交**: 71483f6 ralph: task-142 — update docs for default read tools and access policy

---

## task-143/144 会话总结 (2026-05-16) — Phase 42 完成

**做了什么**:
- **task-143**: 在 `D:\2026_zju\test\stageflow_phase42_demo` 创建外部 CLI smoke demo。使用 `stageflow init` + 自定义 YAML (`inspect` 和 `build` 两个阶段)。11 项 hook 测试验证：默认读取工具可用、`.env`/`secrets/**` 被阻止、Write 被限制在工具列表中、`access.write.allow` 控制写入路径、嵌套 cwd 发现正常。
- **task-144**: QuixBugs QX_GCD 运行演练。从种子库复制 buggy_task.py + 测试文件。使用 inspect→fix→verify 工作流。修复前：4/4 失败（RecursionError）。一行修复：`gcd(a % b, b)` → `gcd(b, a % b)`。修复后：4/4 通过。Hook 检查验证了 inspect 中 Read 默认可用的行为。

**Phase 42 完成**: 全部 6 个任务（task-139 至 task-144）均已完成。
- 默认读取工具（Read, Grep, Glob）在省略时可用
- 访问策略 deny 阻止敏感文件
- 写入工具保持严格的阶段门控
- 文档已更新（CLAUDE.md、api_reference.md、AGENT.md）
- 外部 CLI 演示确认实际行为
- QuixBugs 演练证明端到端工作流

**提交**: 6c89a97 (task-143), 71f9184 (task-144)

