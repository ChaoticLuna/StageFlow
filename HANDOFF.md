# StageFlow — Agent Handoff 文档

> **最后更新**: 2026-05-10
> **当前 Agent**: Claude (via Claude Code)
> **交接原因**: task-014 完成 — 提示词模板系统

---

## 当前状态快照

```
Tests:           541 total (507 existing + 34 generator tests)
Framework files: 10 modules (~2,500 lines)
Generator:       stageflow/generator/ — llm_generator.py + prompts.py
  4 templates:   GENERIC, CI_CD (7-stage), CODE_REVIEW (5-stage), DATA_PIPELINE (6-stage)
  Tests:         34 (generator: 19 + templates: 12 + extract/validate: 5)
Editor:          editor/ — Vite 8 + React 18 + TS 6.0 + React Flow 11 + FastAPI
  Components:    6 files (App, Canvas, StageNode, EdgeEditor, PropertiesPanel, conditionDefs)
  Utils:         yaml.ts (export/import/validate)
  Backend:       editor/server.py — FastAPI + uvicorn
  Canvas:        toolbar, Add Stage, Export/Import YAML, Auto Layout, Mermaid preview
                 Ctrl+S export, Ctrl+Z undo (50-level stack), Delete node, minimap, theme
  Build:         tsc clean, vite build clean
Current stage:   plan
Ralph:           活跃 — task-014 done, task-015 next (CLI `stageflow generate`)
```

## 本次会话完成的工作

**task-013 完成** — LLM 工作流生成器核心:

- **stageflow/generator/__init__.py**: Package init
- **stageflow/generator/llm_generator.py**: `WorkflowGenerator` 类:
  - `build_prompt(description, template=None)`: 构建 LLM prompt，可选 domain template
  - `_extract_yaml(response)`: 从 LLM 响应提取 YAML（```yaml fences → generic ``` → raw text）
  - `validate(yaml_str)`: 双层校验 — `yaml.safe_load()` + `validate_stages_config()` + `StageRegistry.validate()`（交叉引用检查）
  - `generate(description, template=None)`: 3x 重试循环，每次将错误反馈给 LLM，返回 `(yaml_str | None, history)`
  - `CONDITION_REFERENCE`: 27 种条件类型 Markdown 参考表
  - `SYSTEM_PROMPT` / `USER_PROMPT` / `RETRY_PROMPT`: 内置 prompt 模板

**task-014 完成** — 提示词模板系统:

- **stageflow/generator/prompts.py**: `PromptTemplate` 类 + 注册/查询系统:
  - `PromptTemplate(name, label, role, guide, example_yaml, example_desc)`: 域特定模板
  - `format_prompt(condition_reference, description)`: 组装完整 prompt（role + guide + reference + example + task）
  - `register_template()` / `get_template(name)` / `list_templates()`: 全局注册表，大小写不敏感
  - 4 个模板:
    1. **GENERIC**: 通用 4-stage（analyze→plan→implement→done），file_exists/file_contains/shell_test/git_status
    2. **CI_CD**: 7-stage（checkout→lint→test→build→deploy→verify→done），shell_test/http_status/time_range/command_exists/file_size
    3. **CODE_REVIEW**: 5-stage（submit→review→revise→approve→done），diff_contains 安全门，gh CLI 条件，all_of 组合
    4. **DATA_PIPELINE**: 6-stage（extract→transform→validate→load→report→done），json_schema/json_count/glob_count/hash_file/compare_files
  - 所有 4 个 example_yaml 均通过 `WorkflowGenerator.validate()` 校验

- **llm_generator.py 更新**: `build_prompt()` 和 `generate()` 现在接受可选 `template` 参数；`WorkflowGenerator.__init__()` 接受 `template` 作为默认值

- **tests/test_generator.py**: 34 个测试（TestBuildPrompt: 4, TestExtractYaml: 5, TestValidate: 5, TestGenerate: 7, TestTemplates: 13）

## 下一步

Ralph 自动从 task-015 开始（CLI `stageflow generate` + 测试）

## 已知问题

1. Hook 当前已关闭
2. test_cache.py + test_concurrency.py 预存失败（6 个）
3. Guard hook Windows 兼容性（Bash vs PowerShell）
4. CODE_REVIEW 模板 example 修复：`"eval\("` → `'eval('` 避免 YAML 非法转义序列
