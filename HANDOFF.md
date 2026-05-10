# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-10
> **当前 Agent**: Claude (via Claude Code)
> **交接原因**: task-015 完成 — CLI `stageflow generate` 子命令

---

## 当前状态快照

```
Tests:           550 total (507 existing + 43 generator tests)
Framework files: 10 modules (~2,700 lines)
Generator:       stageflow/generator/ — llm_generator.py + prompts.py
  4 templates:   GENERIC, CI_CD (7-stage), CODE_REVIEW (5-stage), DATA_PIPELINE (6-stage)
  CLI:           python -m stageflow generate "desc" [--template TYPE] [--output PATH] [--validate] [--prompt-only] [--list-templates]
  Tests:         43 (generator: 19 + templates: 13 + CLI: 9 + extract/validate: 5)
Editor:          editor/ — Vite 8 + React 18 + TS 6.0 + React Flow 11 + FastAPI
  Components:    6 files (App, Canvas, StageNode, EdgeEditor, PropertiesPanel, conditionDefs)
  Utils:         yaml.ts (export/import/validate)
  Backend:       editor/server.py — FastAPI + uvicorn
  Canvas:        toolbar, Add Stage, Export/Import YAML, Auto Layout, Mermaid preview
                 Ctrl+S export, Ctrl+Z undo (50-level stack), Delete node, minimap, theme
  Build:         tsc clean, vite build clean
Current stage:   plan
Ralph:           活跃 — task-015 done, task-016 next (Agent Runner)
```

## 本次会话完成的工作

**task-014 完成** — 提示词模板系统:
- **stageflow/generator/prompts.py**: 4 个 domain 模板（GENERIC, CI_CD, CODE_REVIEW, DATA_PIPELINE）
- **llm_generator.py**: `build_prompt()` / `generate()` 支持模板参数
- **tests/test_generator.py**: 34 个测试（含模板验证）

**task-015 完成** — CLI `stageflow generate` 子命令:
- **__main__.py**: 新增 `cmd_generate` + argparse 子解析器:
  - `python -m stageflow generate "desc"` → YAML 到 stdout（内置 mock LLM）
  - `--template` / `-t`: 选择模板（GENERIC/CI_CD/CODE_REVIEW/DATA_PIPELINE）
  - `--output` / `-o`: 写入文件而非 stdout
  - `--validate`: 输出前校验 YAML
  - `--prompt-only`: 仅打印 LLM prompt（不生成）
  - `--list-templates`: 列表可用模板
  - 内置 mock LLM 默认使用模板 example YAML，无模板时生成最小有效 YAML
- **tests/test_generator.py**: 9 个 CLI 集成测试（TestGenerateCLI）

## 下一步

Ralph 自动从 task-016 开始（Agent Runner — `stageflow/agent/runner.py`）

## 已知问题

1. Hook 当前已关闭
2. test_cache.py + test_concurrency.py 预存失败（6 个）
3. Guard hook Windows 兼容性（Bash vs PowerShell）
4. 当前 generate 命令使用内置 mock LLM（模板 example），真实 LLM 集成需用户提供 `llm_call` 函数
