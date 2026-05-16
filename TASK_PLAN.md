# StageFlow — Task Plan

> **最后更新**: 2026-05-16
> **当前阶段**: Phase 39 — Fine-grained file access policy 🔄 (task-128/129/130 complete, task-131 next)
> **Ralph 状态**: 活跃 — fix_plan.md 128/134 完成

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

## Phase 4: 测试体系 ✅

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 4.1 | E2E 管道测试 | ✅ | test_e2e.py (18 tests) |
| 4.2 | 100 阶段可扩展性验证 | ✅ | test_extensibility_quick.py |
| 4.3 | Pytest 插件 + stageflow marker | ✅ | conftest.py 插件 |
| 4.4 | 并发/压力测试 | ✅ | test_stress.py (17) + test_concurrency.py (21) |
| 4.5 | 条件缓存命中率测试 | ✅ | test_cache.py (31 tests) |
| 4.6 | 性能基准测试 | ✅ | test_benchmark.py → task-003 |
| 4.7 | Hook 集成测试 | ✅ | test_hooks_integration.py → task-004 |

## Phase 5: 文档与演示 ✅

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 5.1 | CLAUDE.md 完整文档 | ✅ | 架构 + API + 约束 |
| 5.2 | REQUIREMENTS.md 需求文档 | ✅ | 总需求 |
| 5.3 | TASK_PLAN.md 任务计划 | ✅ | 本文件 |
| 5.4 | HANDOFF.md 交接文档 | ✅ | Agent 交接记录 |
| 5.5 | Demo 脚本 | ✅ | demo/demo_workflow.py |
| 5.6 | API 参考文档 | ✅ | docs/api_reference.md → task-005 |

## Phase 6: 可视化工作流编辑器 🆕

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 6.1 | React+TS+Vite 项目初始化 | ✅ | editor/ → task-006 |
| 6.2 | 画布 + 拖拽节点 (React Flow) | ✅ | Canvas.tsx + StageNode.tsx → task-007 |
| 6.3 | 节点属性面板 | ✅ | PropertiesPanel.tsx → task-008 |
| 6.4 | 条件边编辑器 | ✅ | EdgeEditor.tsx → task-009 |
| 6.5 | YAML 导入/导出 | ✅ | js-yaml 序列化 → task-010 |
| 6.6 | Mermaid 预览 + 主题 + 快捷键 | ✅ | task-011 |
| 6.7 | FastAPI 后端桥接 | ✅ | editor/server.py → task-012 |

## Phase 7: LLM 工作流生成器 🆕

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 7.1 | 生成器核心 — NL → YAML via LLM | ✅ | stageflow/generator/ → task-013 |
| 7.2 | 提示词模板系统 (CI/CD, Review, ...) | ✅ | generator/prompts.py → task-014 |
| 7.3 | CLI `stageflow generate` + 测试 | ✅ | __main__.py + tests → task-015 |

## Phase 8: Agent 运行时 🆕

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 8.1 | Agent 循环引擎 | ✅ | stageflow/agent/runner.py → task-016 |
| 8.2 | LLM + StageFlow 混合工作流 | ✅ | agent/hybrid.py → task-017 |
| 8.3 | 多 Agent 编排器 | ✅ | agent/orchestrator.py → task-018 |

## Phase 9: 高级特性

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 9.1 | 暂停/恢复执行 | ✅ | engine pause/resume → task-019 |
| 9.2 | Webhook 通知 | ✅ | on_enter/on_exit webhook → task-020 |
| 9.3 | 并行条件评估 | ✅ | ThreadPoolExecutor + 12 tests → task-061 |
| 9.4 | 软性门控（warn 不阻止） | ✅ | condition severity 分级 → task-024 |
| 9.5 | Web UI 状态面板 | ✅ | FastAPI 状态/审计 API → task-024 |
| 9.6 | MCP Server 集成 | ✅ | FastMCP + 3 tools + 11 tests → task-062 |

## Phase 10: Harness 工程调研 🆕

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 10.1 | 竞品调研 (Dify, n8n, LangGraph, Temporal, Prefect) | ✅ | docs/harness_research.md → task-021 |
| 10.2 | Agent 模式调研 | ✅ | docs/harness_research.md → task-022 |
| 10.3 | 集成方案设计 | ✅ | docs/integration_blueprint.md → task-023 |
| 10.4 | 基于调研改进实现 | ✅ | Top 3 improvements → task-024 |
| 10.5-LOOP | 时间检查循环 (≥21:00 → 停止，<21:00 → 搜索+迭代) | ✅ | 8 iterations, 678 tests → task-025-LOOP |

## Phase 11: 生态与集成

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 11.1 | GitHub Actions 集成示例 | ✅ | CI/CD + Python matrix → task-063 |
| 11.2 | Docker 镜像 | ✅ | python:3.12-slim + entrypoint → task-063 |
| 11.3 | VS Code 扩展 | ✅ | vscode-extension/ — status bar + quick pick → task-074 |
| 11.4 | Linear/Notion 任务同步 | ✅ | Linear + Notion → tasks 075-076 |
| 11.5 | 多项目共享配置 | ✅ | config extends inheritance → task-064 |

## Phase 37: 显式运行完成语义 🆕

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 37.1 | `StateMachine.complete()` 核心实现 | ✅ | engine.py + 15 tests → task-118 |
| 37.2 | `stageflow complete` CLI 命令 | ✅ | task-119 |
| 37.3 | Status 输出、文档、Agent 指令更新 | ✅ | task-120 |
| 37.4 | Editor 保存门控连接完成语义 | ✅ | task-121 |
| 37.5 | 分层验证 | ✅ | task-122 |

## Phase 39: 细粒度文件访问控制 🆕

| # | 任务 | 状态 | 产出 |
|---|------|------|------|
| 39.1 | Access policy schema 定义与验证 | ✅ | schema.py + 23 tests → task-128 |
| 39.2 | 核心路径策略评估 | ✅ | access_policy.py + 91 tests → task-129 |
| 39.3 | 在 stageflow hook 中强制执行 access | ✅ | cmd_hook + 18 tests → task-130 |
| 39.4 | 统一 guard.py 与 hook 行为 | ⬜ | task-131 |
| 39.5 | Editor 导入/导出保留 access 字段 | ⬜ | task-132 |
| 39.6 | Checklist 完成条件演示 | ⬜ | task-133 |
| 39.7 | 文件访问控制分层验证 | ⬜ | task-134 |

---

**图例**: ✅ 完成 | 🔄 进行中 | ⬜ 待开始 | ❌ 阻塞 | 🆕 新阶段
