# StageFlow — Task Plan

> **最后更新**: 2026-05-10
> **当前阶段**: Phase 3 — 功能完善

---

## Phase 1: 核心框架 ✅

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 1.1 | 条件系统 `conditions.py` — 注册机制、评估、缓存 | ✅ | 27 种条件类型 |
| 1.2 | `registry.py` — Stage/Transition 动态 CRUD、YAML 加载 | ✅ | 完整 CRUD + 图验证 |
| 1.3 | `engine.py` — StateMachine、转移逻辑、变量、Hook | ✅ | 转移 + 回退 + 重试 + 生命周期 |
| 1.4 | `schema.py` — YAML 配置结构校验 | ✅ | 所有字段校验 |
| 1.5 | `audit.py` — 审计日志 JSONL | ✅ | 阶段计时 + 汇总 |
| 1.6 | 默认 `stages.yaml` — 10 阶段 + 11 转移 | ✅ | pick → done 管道 |
| 1.7 | CLI `__main__.py` — status/list/graph/next 等 | ✅ | 10+ 命令 |

## Phase 2: 安全与集成 ✅

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 2.1 | `guard.py` — Claude Code PreToolUse Hook | ✅ | 阶段工具白名单拦截 |
| 2.2 | `.claude/hooks/stage_guard.py` — Hook 入口 | ✅ | stdin JSON 读取 |
| 2.3 | `.claude/settings.json` — Hook 配置 | ✅ | PreToolUse + PostToolUse |
| 2.4 | 阶段脚本 `scripts/stage_*.py` | ✅ | next/status/reset/jump/back |
| 2.5 | `pyproject.toml` — pip 安装 | ✅ | pip install -e . |

## Phase 3: 功能完善 ✅

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 3.1 | 新增 9 种条件类型 | ✅ | file_age, file_size, glob_count, json_schema, hash_file, git_status, http_status, time_range, compare_files |
| 3.2 | 变量插值 `{{var.key}}` | ✅ | 条件参数动态解析 |
| 3.3 | retry 条件 | ✅ | 子条件重试 + 延迟 |
| 3.4 | diff_contains 条件 | ✅ | AI 安全门（检测 eval/exec） |
| 3.5 | json_count 条件 | ✅ | JSON 数组/对象元素计数 |
| 3.6 | command_exists 条件 | ✅ | CLI 工具检测 |
| 3.7 | 测试覆盖所有条件类型 | ✅ | 198 tests in test_conditions.py |
| 3.8 | Edge case 测试 | ✅ | test_edge_cases.py (15 tests) |
| 3.9 | Windows 跨平台修复 | ✅ | git 2>/dev/null 兼容性 |

## Phase 4: 测试体系 🔄

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 4.1 | E2E 管道测试 | ✅ | test_e2e.py (18 tests) |
| 4.2 | 100 阶段可扩展性验证 | ✅ | test_extensibility_quick.py |
| 4.3 | Pytest 插件 + stageflow marker | ✅ | conftest.py 插件 |
| 4.4 | 并发/压力测试 | ⬜ | 待实现 |
| 4.5 | 条件缓存命中率测试 | ⬜ | 待实现 |
| 4.6 | 性能基准测试 | ⬜ | 待实现 |
| 4.7 | Hook 集成测试 | ⬜ | 端到端 Hook 流程验证 |

## Phase 5: 文档与演示 🔄

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 5.1 | CLAUDE.md 完整文档 | ✅ | 架构 + API + 约束 |
| 5.2 | REQUIREMENTS.md 需求文档 | ✅ | 本文档 |
| 5.3 | TASK_PLAN.md 任务计划 | ✅ | 本文档 |
| 5.4 | HANDOFF.md 交接文档 | ✅ | 本文档 |
| 5.5 | Demo 脚本 | ✅ | demo/demo_workflow.py |
| 5.6 | API 参考文档 | ⬜ | docstrings → 自动生成 |

## Phase 6: 高级特性

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 6.1 | 暂停/恢复执行 | ⬜ | 引擎级 pause/resume |
| 6.2 | Webhook 通知（Slack/企业微信） | ⬜ | on_enter/on_exit webhook |
| 6.3 | 并行条件评估 | ⬜ | 多条件并发执行 |
| 6.4 | 软性门控（warn 不阻止） | ⬜ | condition severity 分级 |
| 6.5 | Web UI 状态面板 | ⬜ | Flask/FastAPI 仪表板 |
| 6.6 | MCP Server 集成 | ⬜ | 通过 MCP 协议暴露条件评估 |
| 6.7 | Stageflow Guard 作为 MCP Tool | ⬜ | 远程工具守卫 |

## Phase 7: 生态与集成

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 7.1 | GitHub Actions 集成示例 | ⬜ | CI/CD YAML 模板 |
| 7.2 | Docker 镜像 | ⬜ | 容器化部署 |
| 7.3 | VS Code 扩展 | ⬜ | 阶段状态栏指示器 |
| 7.4 | Linear/Notion 任务同步 | ⬜ | Issue 自动链接 |
| 7.5 | 多项目共享配置 | ⬜ | 继承/引用机制 |

---

**图例**: ✅ 完成 | 🔄 进行中 | ⬜ 待开始 | ❌ 阻塞
