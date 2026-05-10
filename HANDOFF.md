# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-10
> **当前 Agent**: Claude (via Claude Code)
> **交接原因**: task-017 完成 — HybridWorkflow LLM + StageFlow 混合工作流

---

## 当前状态快照

```
Tests:           610 total (550 previous + 25 hybrid tests)
Framework files: 13 modules (~3,400 lines)
Agent Runtime:   stageflow/agent/ — 3 modules
  AgentRunner:    task parsing, lifecycle, plan file updates, progress persistence, commit callback (35 tests)
  HybridWorkflow: LLM stages + framework condition gates, 8 default stage prompts, run/advance/force_advance (25 tests)
Generator:       stageflow/generator/ — llm_generator.py + prompts.py (43 tests)
CLI:             python -m stageflow generate "desc" [--template TYPE] [--output PATH] [--validate]
Editor:          editor/ — Vite 8 + React 18 + TS 6.0 + React Flow 11 + FastAPI
Current stage:   plan
Ralph:           活跃 — task-017 done, task-018 next (WorkflowOrchestrator)
```

## 本次会话完成的工作

**task-016 完成** — AgentRunner 任务编排器

**task-017 完成** — HybridWorkflow LLM + StageFlow 混合工作流:
- **stageflow/agent/hybrid.py**: `HybridWorkflow` 类:
  - `run_llm_stage(stage_name, extra_context)`: 调用 LLM 执行 AI 推理阶段，保存结果
  - `advance()`: 检查条件门控并推进到下一阶段（自动寻找起始阶段）
  - `force_advance(target)`: 绕过条件强制推进
  - `run(description, max_stages, stop_at)`: 完整 pipeline 执行循环
  - `_find_start_stage()`: 寻找根节点（无入边的阶段）
  - `status()` / `reset()`: 状态查询和重置
  - `STAGE_PROMPTS`: 7 个默认阶段提示词（pick/analyze/plan/implement/verify/document/wrap_up）
- **tests/test_hybrid.py**: 25 个测试，7 个测试类
- **stageflow/agent/__init__.py**: 导出 HybridWorkflow

## 下一步

Ralph 自动从 task-018 开始（WorkflowOrchestrator — `stageflow/agent/orchestrator.py`）

## 已知问题

1. Hook 当前已关闭
2. test_cache.py + test_concurrency.py 预存失败（6 个）
3. Guard hook Windows 兼容性（Bash vs PowerShell）
4. `StageRegistry.stage_names` 按字母排序（非注册顺序），HybridWorkflow._find_start_stage() 通过入边分析规避了此问题
