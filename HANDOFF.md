# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-11
> **当前 Agent**: Ralph (Claude Code)
> **交接原因**: task-056 完成 — __main__.py coverage improvement

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
