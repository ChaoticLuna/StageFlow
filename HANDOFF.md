# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-10
> **当前 Agent**: Claude (via Claude Code)
> **交接原因**: 新会话开始

---

## 当前状态快照

```
Tests:           362 passed, 0 failed
Conditions:      27 types
Framework files: 7 modules (~2,000 lines)
Test files:      7 files
Current stage:   implement (根据 .claude/current_stage.json)
Hook status:     活跃 — PreToolUse Hook 正在拦截工具调用
```

## 最近完成的工作

### 会话 1 (2026-05-09)
- 搭建完整框架：conditions, registry, engine, guard, audit, schema
- 默认 10 阶段管道配置
- CLI 入口 `python -m stageflow`
- 5 个阶段转移脚本
- Pytest 插件 + conftest fixtures
- 270 个测试通过
- Hook 系统上线并拦截工具

### 会话 2 (2026-05-10) — 当前
1. **新增 6 种条件类型的测试** — git_status, http_status, time_range, compare_files, json_schema, hash_file
2. **修复 Windows 跨平台 bug** — git_status 中 `2>/dev/null` 在 cmd.exe 上失败，已移除
3. **新增 7 种条件类型** — file_age, file_size, glob_count, retry, command_exists, diff_contains, json_count
4. **变量插值系统** — 条件参数支持 `{{var.key}}`，自动从 StateMachine 变量存储解析
5. **更新 CLAUDE.md** — 统计数据和条件表同步更新
6. **创建项目文档** — REQUIREMENTS.md, TASK_PLAN.md, HANDOFF.md

## 下一步任务

按 TASK_PLAN.md 优先级：

1. **Phase 4.4 — 并发/压力测试** — 测试快速连续转移、多线程变量读写
2. **Phase 4.5 — 条件缓存命中率测试** — 验证 _CONDITION_CACHE 行为
3. **Phase 4.6 — 性能基准测试** — 条件评估吞吐量
4. **Phase 5.6 — API 参考文档** — 从 docstrings 生成
5. **Phase 6.1 — 暂停/恢复执行** — 引擎级 pause/resume

## 已知问题

1. **`shell_test` 在 Windows 上可能受 cmd.exe 限制** — shell=True 使用 cmd.exe，bash 语法不支持
2. **`http_status` 测试依赖网络** — 连接被拒绝测试可能在防火墙后行为不一致
3. **`yaml_field` 测试需要 PyYAML** — 已作为项目依赖安装
4. **`json_schema` 测试需要 jsonschema** — 未安装则跳过 Schema 验证，仅检查 JSON 有效性
5. **Hook 在测试环境中不活跃** — 测试使用直接 API 调用，绕过 Hook

## 重要文件和路径

| 文件 | 说明 |
|------|------|
| `CLAUDE.md` | **必读** — 项目架构 + Agent 协作规则 |
| `REQUIREMENTS.md` | 总需求文档 |
| `TASK_PLAN.md` | 任务计划 + 进度跟踪 |
| `HANDOFF.md` | 本文档 — Agent 交接记录 |
| `stageflow/core/conditions.py` | 27 种条件实现 |
| `stageflow/core/engine.py` | 状态机引擎 |
| `stageflow/core/registry.py` | 阶段注册表 |
| `stageflow/core/guard.py` | 工具守卫 |
| `stageflow/config/stages.yaml` | 默认管道配置 |
| `tests/conftest.py` | Fixtures + Pytest 插件 |
| `.claude/current_stage.json` | 当前阶段状态（不可手动修改） |

## 关键决策记录

1. **条件缓存默认关闭于转移时** — Transition.evaluate() 默认 cache_ttl=0，避免文件变更后返回过期结果
2. **force_transition_to 不重置重试计数** — 只有条件检查成功的转移才重置
3. **变量插值在 evaluate_all 入口处解析** — 递归解析整个条件列表，确保嵌套条件也得到处理
4. **git diff 使用 HEAD 比较** — diff_contains 条件比较 HEAD 与工作目录，不包含未跟踪文件
5. **Hook 始终允许 TaskCreate/TaskUpdate 等管理工具** — ALWAYS_ALLOW 列表中的工具不受阶段限制
