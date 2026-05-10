# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-10
> **当前 Agent**: Claude (via Claude Code)
> **交接原因**: task-016 完成 — AgentRunner 任务编排器

---

## 当前状态快照

```
Tests:           585 total (550 previous + 35 agent tests)
Framework files: 12 modules (~3,000 lines)
Generator:       stageflow/generator/ — llm_generator.py + prompts.py
  CLI:           python -m stageflow generate "desc" [--template TYPE] [--output PATH] [--validate]
  Tests:         43 (generator + templates + CLI)
Agent:           stageflow/agent/ — runner.py (AgentRunner task orchestrator)
  Pipeline:      pick → analyze → plan → implement → verify → wrap_up → done
  Features:      task parsing, lifecycle (start/advance/complete/fail), plan file updates,
                 progress persistence (JSON), commit callback, status reporting
  Tests:         35 (parsing: 6, lifecycle: 11, file marks: 3, persistence: 3, status: 5,
                 pipeline: 2, commit callback: 2, next task: 3)
Editor:          editor/ — Vite 8 + React 18 + TS 6.0 + React Flow 11 + FastAPI
Current stage:   plan
Ralph:           活跃 — task-016 done, task-017 next (HybridWorkflow)
```

## 本次会话完成的工作

**task-015 完成** — CLI `stageflow generate` 子命令:
- **__main__.py**: `cmd_generate` + argparse 子解析器，9 个 CLI 集成测试

**task-016 完成** — AgentRunner 任务编排器:
- **stageflow/agent/__init__.py**: Package init，导出 AgentRunner
- **stageflow/agent/runner.py**: `AgentRunner` 类:
  - `parse_tasks()`: 解析 FIX_PLAN.md 风格 checkbox 任务（支持 `[ ]`/`[x]`/`[!]`）
  - `get_next_task()`: 返回第一个未完成任务
  - `start_task(task_id)`: 开始任务，设置 current_task + current_stage = "pick"
  - `advance_stage(target)`: 推进阶段（pick→analyze→plan→implement→verify→wrap_up→done）
  - `complete_task(task_id)`: 标记完成 → 更新 markdown `[x]` → 清除 current → 保存 progress → 调用 commit_callback
  - `fail_task(task_id, reason)`: 标记失败/阻塞
  - `mark_task_completed_in_file()` / `mark_task_blocked_in_file()`: 直接更新 markdown checkbox
  - `status()`: 完整状态（总任务数、已完成、当前任务/阶段、历史记录）
  - `reset()`: 清除所有进度
  - Progress 持久化到 `.claude/agent_progress.json`
- **tests/test_agent.py**: 35 个测试，7 个测试类

## 下一步

Ralph 自动从 task-017 开始（HybridWorkflow — `stageflow/agent/hybrid.py`）

## 已知问题

1. Hook 当前已关闭
2. test_cache.py + test_concurrency.py 预存失败（6 个）
3. Guard hook Windows 兼容性（Bash vs PowerShell）
4. AgentRunner 目前不直接使用 StageFlow StateMachine 做阶段门控 — 它是独立的任务追踪层。HybridWorkflow (task-017) 将桥接两者
