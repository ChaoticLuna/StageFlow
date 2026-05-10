# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-10
> **当前 Agent**: Claude (via Claude Code)
> **交接原因**: task-013 完成 — LLM 工作流生成器

---

## 当前状态快照

```
Tests:           507 total (487 existing + 20 server API)
Framework files: 8 modules (~2,000 lines)
Editor:          editor/ — Vite 8 + React 18 + TS 6.0 + React Flow 11 + FastAPI
  Components:    6 files (App, Canvas, StageNode, EdgeEditor, PropertiesPanel, conditionDefs)
  Utils:         yaml.ts (export/import/validate)
  Backend:       editor/server.py — FastAPI + uvicorn
  Canvas:        toolbar, Add Stage, Export/Import YAML, Auto Layout, Mermaid preview
                 Ctrl+S export, Ctrl+Z undo (50-level stack), Delete node, minimap, theme
  Build:         tsc clean, vite build clean
Current stage:   plan
Ralph:           活跃 — task-013 next (LLM Workflow Generator)
```

## 本次会话完成的工作

**task-012 完成** — FastAPI 后端桥接:

- **editor/server.py**: FastAPI 应用，3 个 API 端点 + 静态文件服务:
  - `GET /api/conditions` — 返回 27 种条件类型定义（含 param schemas: name, label, kind, options, default, placeholder, required），同时返回 `list_conditions()` 的已注册类型列表和缺失定义
  - `POST /api/validate` — 接收 `{yaml: string}`，使用 `yaml.safe_load()` + `validate_stages_config()` 校验，返回 `{valid: bool, errors: [string]}`
  - `POST /api/run` — 接收 `{yaml, from_stage, to_stage}`，加载配置，查找匹配的 transition，使用 `evaluate_all()` 评估条件（`cache_ttl=0`），返回 `{can_transition: bool, messages: [string]}`
  - 生产模式：`StaticFiles` 挂载 `editor/dist/`（如果存在）
  - 开发模式：`--dev` 标志启用 CORS（`http://localhost:5173`）
  - CLI: `python editor/server.py [--dev] [--host HOST] [--port PORT]`
- **pyproject.toml**: 新增 `[project.optional-dependencies] editor = ["fastapi>=0.100", "uvicorn>=0.20"]`
- **tests/test_server.py**: 20 个 API 测试（4 类）:
  - `TestGetConditions` (4): 27 条件, 必填字段, 全部已注册, 顺序
  - `TestValidateEndpoint` (8): 有效 YAML, 语法错误, 空文档, 缺少 stages, 重复名称, stages 非列表, transitions 非列表, 缺少 from
  - `TestRunEndpoint` (8): always 转移, 条件转移, 无定义转移, 无效 YAML, 空 YAML, 无效配置, 无条件转移, on_fail 报告

## 下一步

Ralph 自动从 task-013 开始（LLM 工作流生成器 — `stageflow/generator/llm_generator.py`）

## 已知问题

1. Hook 当前已关闭
2. test_cache.py + test_concurrency.py 预存失败（6 个）
3. Guard hook Windows 兼容性（Bash vs PowerShell）
