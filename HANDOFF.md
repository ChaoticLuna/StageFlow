# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-10
> **当前 Agent**: Claude (via Claude Code)
> **交接原因**: task-011 完成 — Mermaid 预览 + 主题切换 + 快捷键 + 自动布局

---

## 当前状态快照

```
Tests:           441 total
Framework files: 7 modules (~2,000 lines)
Editor:          editor/ — Vite 8 + React 18 + TS 6.0 + React Flow 11
  Components:    6 files (App, Canvas, StageNode, EdgeEditor, PropertiesPanel, conditionDefs)
  Utils:         yaml.ts (export/import/validate)
  Canvas:        toolbar, Add Stage, Export/Import YAML, Auto Layout, Mermaid preview
                 Ctrl+S export, Ctrl+Z undo (50-level stack), Delete node
                 minimap, edge labels, dark/light theme
  Theme:         38 CSS variables, light + dark modes, localStorage persistence
  EdgeEditor:    27 condition types, dynamic param forms, AND/OR toggle, on_fail selector
  Build:         tsc clean, vite build clean
Current stage:   plan
Ralph:           活跃 — task-012 next (FastAPI backend bridge)
```

## 本次会话完成的工作

**task-011 完成** — Mermaid 预览 + 主题切换 + 快捷键 + 自动布局:

- **App.tsx**: 主题系统 — 从 localStorage 加载，`applyTheme()` 设置 `data-theme` 属性，toggle 按钮在 header（☾/☀ 图标），`prefers-color-scheme` 检测
- **App.css**: 完整的 CSS 变量主题系统（38 个变量）：`:root` (light) + `[data-theme="dark"]` 覆盖。深色主题背景 #1e1e2e，所有组件通过变量引用颜色。Mermaid 预览 modal 样式。Undo toast 样式。工具栏分隔线。按钮 hover 变为实心。
- **Canvas.tsx**: 
  - **Undo 栈**: `useRef<Snapshot[]>` max 50 层，每次用户操作前 `pushUndo()`，Ctrl+Z 弹出恢复，含 toast 提示
  - **Ctrl+S**: 阻止默认浏览器保存对话框 → 触发 YAML 导出下载
  - **Ctrl+Z**: 恢复上一个快照（nodes + edges + _nodeCounter）
  - **自动布局**: 拓扑排序分层算法（BFS 从入度为 0 的根节点），X_GAP=240/Y_GAP=100，按钮在工具栏
  - **Mermaid 预览**: `flowchart LR` 生成，节点含描述，边含条件标签，modal 中含 Copy 按钮，`navigator.clipboard.writeText()`
  - **pushUndo** 集成到所有变更点: addStage, Delete key, onConnect, handleEdgeUpdate, handleFileChange, autoLayout, updateNodeData, updateEdgeData

## 下一步

Ralph 自动从 task-012 开始（FastAPI 后端桥接 — editor/server.py + API 端点）

## 已知问题

1. Hook 当前已关闭
2. test_cache.py + test_concurrency.py 预存失败（6 个）
3. Guard hook Windows 兼容性（Bash vs PowerShell）
