# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-10
> **当前 Agent**: Claude (via Claude Code)
> **交接原因**: task-010 完成 — YAML 导入/导出

---

## 当前状态快照

```
Tests:           441 total
Framework files: 7 modules (~2,000 lines)
Editor:          editor/ — Vite 8 + React 18 + TS 6.0 + React Flow 11
  Components:    6 files (App, Canvas, StageNode, EdgeEditor, PropertiesPanel, conditionDefs)
  Utils:         yaml.ts (export/import/validate)
  Canvas:        toolbar, Add Stage, Export YAML, Import YAML, edge labels, minimap, delete key
  EdgeEditor:    27 condition types, dynamic param forms, AND/OR toggle, on_fail selector
  PropertiesPanel: full CRUD for stage name/desc/tools/hooks
  YAML:          round-trip serialization (ConditionDef ↔ YAML-native format)
  Build:         tsc clean, vite build clean
Current stage:   plan
Ralph:           活跃 — task-011 next (Mermaid preview, theme, shortcuts, minimap)
```

## 本次会话完成的工作

**task-010 完成** — YAML 导入/导出:

- **editor/src/utils/yaml.ts** — YAML 序列化工具:
  - `exportToYaml(nodes, edges)` — 将画布序列化为 `stages.yaml` 格式（stages + transitions）
  - `importFromYaml(yamlString)` — 解析 YAML，返回 nodes/edges（含错误处理）
  - `validateYaml(yamlString)` — 验证 YAML 结构
  - `conditionToYaml()` — 条件序列化：`{type, params}` → `{type: value}` (标量) 或 `{type: {params...}}` (对象)
  - `conditionFromYaml()` — 条件反序列化：YAML 原生格式 → `{type, params}`
  - Hook 序列化：`{shell, python}` ↔ `[{shell: "..."}, {python: "..."}]`
  - 26 种条件的标量参数映射表（`FIRST_PARAMS`）
- **Canvas.tsx** 更新:
  - 工具栏新增 "Export YAML" 和 "Import YAML" 按钮
  - `handleExport`: 序列化 → Blob → 触发浏览器下载 `stages.yaml`
  - `handleImport`: 隐藏 `<input type="file">` → FileReader → 解析 → setNodes/setEdges
  - 导入错误通过 `alert()` 提示
  - 导入节点自动计算 `_nodeCounter` 避免 ID 冲突

## 下一步

Ralph 自动从 task-011 开始（Mermaid 预览、深/浅主题切换、键盘快捷键、minimap、自动布局）

## 已知问题

1. Hook 当前已关闭
2. test_cache.py + test_concurrency.py 预存失败（6 个）
3. Guard hook Windows 兼容性（Bash vs PowerShell）
