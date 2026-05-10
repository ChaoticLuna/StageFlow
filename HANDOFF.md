# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-10
> **当前 Agent**: Claude (via Claude Code)
> **交接原因**: task-018 完成 — WorkflowOrchestrator 多 Agent 编排器

---

## 当前状态快照

```
Tests:           643 total (610 previous + 33 orchestrator tests)
Framework files: 14 modules (~3,800 lines)
Agent Runtime:   stageflow/agent/ — 4 modules, 93 tests
  AgentRunner:         task parsing, lifecycle, plan file updates, progress persistence (35 tests)
  HybridWorkflow:      LLM stages + framework condition gates, 8 prompts (25 tests)
  WorkflowOrchestrator: parallel execution, dependency DAG, shared state, audit (33 tests)
Generator:       stageflow/generator/ — llm_generator.py + prompts.py (43 tests)
CLI:             python -m stageflow generate "desc" [--template TYPE] [--output PATH]
Editor:          editor/ — Vite 8 + React 18 + TS 6.0 + React Flow 11 + FastAPI
Phase 8:         ✅ All 3 tasks complete
Ralph:           活跃 — task-019 next (pause/resume engine)
```

## 本次会话完成的工作

**task-017 完成** — HybridWorkflow LLM + StageFlow 混合工作流

**task-018 完成** — WorkflowOrchestrator 多 Agent 编排器:
- **stageflow/agent/orchestrator.py**: `WorkflowOrchestrator` 类:
  - `add_task(task_id, description, depends_on)`: 注册任务及依赖关系
  - `add_tasks(tasks)`: 批量注册
  - `_validate_graph()`: DFS 环检测 + 缺失依赖验证
  - `_ready_tasks(completed)`: 计算依赖已满足的就绪任务
  - `run()`: 异步执行所有任务，遵守依赖顺序，独立任务并行（ThreadPoolExecutor）
  - `_execute_single_task()`: 单任务执行（线程池），为每个任务创建独立 HybridWorkflow
  - 共享变量存储 (`set_shared`/`get_shared`/`get_all_shared`)
  - 聚合审计追踪 (`get_audit_trail`/`get_summary`)
  - 支持 diamond/chain/complex 依赖图
- **tests/test_orchestrator.py**: 33 个测试，7 个测试类
- **stageflow/agent/__init__.py**: 导出 WorkflowOrchestrator

## 下一步

Ralph 自动从 task-019 开始（pause/resume 引擎 — `engine.py`）

## 已知问题

1. Hook 当前已关闭
2. test_cache.py + test_concurrency.py 预存失败（6 个）
3. Guard hook Windows 兼容性（Bash vs PowerShell）
