# StageFlow — AI 驱动低风险 Issue 自动交付状态机

## Agent 协作规则（最高优先级）

1. **进入项目后，必须先读取 `TASK_PLAN.md`** 了解当前任务进度
2. **每完成一个 Task Plan Phase 中的步骤，必须更新 `TASK_PLAN.md`** 将该步骤标记为完成
3. **每完成一个步骤，必须追加 `HANDOFF.md`** 记录：做了什么、当前状态、下一步是什么、已知问题和决策
4. **不确定下一步时，读取 `TASK_PLAN.md`** 找到下一个未完成的任务
5. **交接给下一个 Agent 时，确保 `HANDOFF.md` 包含足够的上下文**让新 Agent 无需回溯整个会话历史即可继续工作

## 项目概述

StageFlow 是一套**声明式、可扩展的阶段化状态机框架**，用于约束 AI Coding Agent 按照
固定工作周期执行任务。框架负责所有阶段判定，AI 模型不参与规则判断。

**核心设计理念**：Stage（节点）+ Transition（连线）+ Condition（条件）= Dify 式的可扩展状态机

## 项目统计

```
Framework files:  18 modules (~2,500 lines)
Test files:      27 files (~14,000 lines)
Tests:           1441 passed, 0 failed (1311 Python + 130 editor), 1 skipped
Coverage:        84% overall (core: engine 100%, schema 100%, audit 100%, registry 100%)
mypy:            clean (17 source files, 0 issues)
Conditions:       30 types
Stages (default): 10 (pick → done)
Transitions:      11 (含回退/重试路径)
Extensibility:    1,000 stages verified
```

## 快速开始

```bash
# 安装（全局一次）
pip install -e .

# 在任何目录初始化 StageFlow 项目（类似 git init）
stageflow init

# 开始一个新的运行
stageflow start

# 查看当前状态
stageflow status

# 推进到下一阶段（框架自动判定条件）
stageflow next

# 可视化状态机
stageflow graph

# 列出所有阶段和条件类型
stageflow list
```

StageFlow 像 Git 一样工作——从当前目录向上查找项目根。你可以在仓库的任何子目录中运行命令。找不到项目时，命令会提示你运行 `stageflow init`。

## 核心架构

```
stageflow/
├── core/
│   ├── conditions.py    # 条件判断系统（30 种类型，插件注册）
│   ├── registry.py      # 阶段注册表（动态增删 Stage/Transition）
│   ├── engine.py        # 状态机引擎（转移判定、回退、变量、生命周期 Hook）
│   ├── guard.py         # 工具守卫（Claude Code Hook 集成）
│   ├── audit.py         # 审计日志（JSONL 格式，阶段计时）
│   └── discovery.py     # 项目根发现（向上查找 .stageflow/ 或 legacy 标记）
├── config/
│   └── stages.yaml      # 声明式阶段定义（默认配置）
├── artifacts/           # 各阶段产物目录
└── __main__.py          # CLI 入口（Git-like 命令）
```

## 声明式阶段配置

所有阶段、转移、条件定义在 `stageflow/config/stages.yaml`：

```yaml
stages:
  - name: analyze
    tools: [Read, Grep, Glob, WebSearch]
    meta:
      description: "分析 Issue 根因"
    on_enter:             # 可选：进入阶段时执行的 Hook
      - python: "print('Entering analyze')"

transitions:
  - from: analyze
    to: plan
    conditions:
      - file_exists: artifacts/analyze/findings.md
      - file_contains:
          path: artifacts/analyze/findings.md
          pattern: "## Root Cause"
    on_fail: analyze      # 失败自动回退目标
```

## 内置条件类型（30 种）

| 类型 | 用途 | 示例 |
|------|------|------|
| `file_exists` | 文件存在 | `{file_exists: path/to/file.md}` |
| `file_not_exists` | 文件不存在 | `{file_not_exists: path/to/temp}` |
| `file_contains` | 文件包含模式(正则) | `{file_contains: {path: f.md, pattern: "PASS"}}` |
| `file_not_contains` | 文件不包含模式 | `{file_not_contains: {path: f.md, pattern: "FAIL"}}` |
| `json_field` | JSON 字段检查 | `{json_field: {path: d.json, field: key, op: not_empty}}` |
| `yaml_field` | YAML 字段检查 | `{yaml_field: {path: d.yaml, field: key, op: exists}}` |
| `shell_test` | Shell 命令测试 | `{shell_test: {command: "pytest -q", op: exit_zero}}` |
| `python_expr` | Python 表达式 | `{python_expr: {expr: "1 + 1 == 2"}}` |
| `env_var` | 环境变量 | `{env_var: {name: CI, op: equals, value: true}}` |
| `all_of` | 所有条件满足 | `{all_of: {conditions: [...]}}` |
| `any_of` | 任一条件满足 | `{any_of: {conditions: [...]}}` |
| `not` | 取反 | `{not: {condition: {...}}}` |
| `always` | 始终通过 | `{always: true}` |
| `never` | 始终拒绝 | `{never: "原因"}` |
| `git_status` | Git 状态检查 | `{git_status: {op: clean}}` |
| `http_status` | HTTP 端点检查 | `{http_status: {url: "https://..."}}` |
| `time_range` | 时间范围检查 | `{time_range: {after: "09:00", before: "17:00"}}` |
| `compare_files` | 文件对比 | `{compare_files: {path1: a, path2: b, op: identical}}` |
| `json_schema` | JSON Schema 验证 | `{json_schema: {path: d.json, schema_path: s.json}}` |
| `hash_file` | 文件哈希校验 | `{hash_file: {path: f.zip, expected: abc123, algo: sha256}}` |
| `file_age` | 文件修改时间 | `{file_age: {path: log.txt, max_age: 300}}` |
| `file_size` | 文件大小检查 | `{file_size: {path: data.csv, min: 100, max: 1048576}}` |
| `glob_count` | Glob 文件计数 | `{glob_count: {pattern: "**/*.py", min: 5}}` |
| `retry` | 重试子条件 | `{retry: {condition: {file_exists: x}, max_attempts: 12, delay: 5}}` |
| `command_exists` | 命令是否存在 | `{command_exists: "pytest"}` |
| `diff_contains` | Git diff 模式检查 | `{diff_contains: {pattern: "eval\(", op: not_contains}}` |
| `json_count` | JSON 元素计数 | `{json_count: {path: results.json, min: 5}}` |
| `port_open` | TCP 端口监听检查 | `{port_open: {port: 8080, host: "127.0.0.1"}}` |
| `process_running` | 进程运行检查 | `{process_running: {name: "python"}}` |
| `docker_ps` | Docker 容器运行检查 | `{docker_ps: {name: "postgres"}}` |

## 变量插值

条件参数的字符串值中支持 `{{var.key}}` 语法引用阶段变量：

```yaml
transitions:
  - from: analyze
    to: plan
    conditions:
      - file_exists: "artifacts/runs/{{var.run_id}}/analyze/findings.md"
      - file_contains:
          path: "artifacts/runs/{{var.run_id}}/analyze/findings.md"
          pattern: "Root Cause"
```

变量由 StateMachine 的 `set_var()` 方法设置，`run_id` 在 `initialize()` 时自动生成：
```python
sm.initialize("analyze")  # 自动创建 variables.run_id
sm.set_var("issue_id", "BUG-42")
sm.transition_to("plan")  # 条件自动使用 run_id 和 BUG-42
```

## 自定义条件（注册机制）

```python
from stageflow.core.conditions import register

@register("my_check")
def my_check(params: dict) -> tuple[bool, str]:
    # params 来自 YAML 配置
    return True, "Condition passed"
```

## 扩展新阶段（零代码改动）

1. 在 `stages.yaml` 的 `stages` 下添加新条目：
```yaml
  - name: deploy
    tools: [Bash(kubectl *), Bash(helm *)]
    meta:
      description: "部署到 K8s 集群"
    on_enter:
      - shell: "echo 'Starting deploy'"
```

2. 在 `transitions` 下添加连线：
```yaml
  - from: wrap_up
    to: deploy
    conditions:
      - git_status: {op: branch, value: main}
      - time_range: {after: "09:00", before: "17:00"}
```

## 阶段修改 API（程序化扩展）

```python
from stageflow.core.registry import StageRegistry

reg = StageRegistry("stageflow/config/stages.yaml")

# 添加阶段
reg.register_stage("deploy", tools=["Bash(kubectl *)"], description="Deploy to K8s")

# 删除阶段（自动清理关联 Transition）
reg.unregister_stage("legacy_stage")

# 添加转移
reg.register_transition("wrap_up", "deploy", conditions=[{"always": True}])

# 验证图完整性
ok, errors = reg.validate()
```

## CLI 命令（Git-like）

所有命令从当前目录向上查找项目根，类似 Git。支持从仓库任意子目录运行。

### 项目管理

```bash
stageflow init [path] [--force] [--start]  # 初始化新项目（类似 git init）
stageflow migrate [--force]                # 迁移 legacy 项目到新 .stageflow/ 格式
```

### 运行控制

```bash
stageflow start [stage]                    # 开始新运行（默认使用 YAML 第一个阶段）
stageflow next [target] [--force] [--dry-run]  # 推进到下一阶段（框架判定条件）
stageflow back [target]                    # 回退到上一阶段
stageflow complete                         # 完成当前运行（仅限终端阶段）
stageflow jump <target> [--force --reason "..."]  # 跳转到指定阶段
stageflow reset [--hard] [--clean-artifacts]   # 清除当前运行状态（放弃/重启）
```

### 信息查询

```bash
stageflow status [--verbose | --json]      # 查看当前状态
stageflow list [--json]                    # 列出所有阶段和转移
stageflow check <target> [--json]          # 检查转移条件（dry-run）
stageflow graph                            # 生成 Mermaid 流程图
stageflow cond <type> [--params JSON] [--list]  # 测试条件类型
stageflow root [--json]                       # 打印发现的项目根路径
```

### 其他

```bash
stageflow hook                             # Claude Code PreToolUse Hook 入口
stageflow generate <desc> [--template T]   # LLM 工作流生成
stageflow editor [--host HOST] [--port PORT] [--no-open]  # 启动可视化工作流编辑器
stageflow mcp                              # 启动 MCP Server
```

### 兼容脚本（Legacy）

以下脚本保留以兼容旧工作流，推荐使用 CLI 命令替代：

| 脚本 | CLI 等价 |
|------|----------|
| `python scripts/stage_next.py` | `stageflow next` |
| `python scripts/stage_status.py` | `stageflow status` |
| `python scripts/stage_reset.py` | `stageflow reset` |
| `python scripts/stage_jump.py <target>` | `stageflow jump <target>` |
| `python scripts/stage_back.py` | `stageflow back` |

## 运行生命周期

StageFlow 运行遵循明确的生命周期：

1. **stageflow init** — 创建项目元数据，无活跃运行
2. **stageflow editor** 或 **stageflow generate** — 编辑工作流配置（两种路径，见下文）
3. **stageflow start** — 在 YAML 入口阶段开始新运行，创建 run_id
4. **stageflow next** — 通过条件门控的转移推进阶段
5. **stageflow complete** — 在终端阶段正常关闭运行，保留 current_stage: null 和完成元数据
6. **stageflow reset** — 放弃或清除状态，不是成功的正常结束路径

终端阶段是结构性的（零出站转移），不是基于名称判断的。

### 工作流编辑器 (Visual Workflow Editor)

`stageflow editor` 启动一个基于浏览器的可视化编辑器，用于创建和修改工作流配置。
提供两种工作流配置路径：

**路径 1: AI 辅助生成**
```bash
stageflow init                                                  # 1. 初始化项目
stageflow generate "CI/CD pipeline with test and deploy" \      # 2. 从描述生成
    --output .stageflow/config/stages.yaml --validate
stageflow editor                                                # 3. 可视化微调（可选）
stageflow start                                                 # 4. 开始运行
```

**路径 2: 手动可视化编辑**
```bash
stageflow init                                                  # 1. 初始化项目
stageflow editor                                                # 2. 在浏览器中拖拽编辑
stageflow start                                                 # 3. 开始运行
```

### 编辑器保存规则 (Save Gate)

- **允许保存**：无活跃运行时（`stageflow init` 后、`stageflow complete` 后、`stageflow reset` 后）
- **阻止保存**：运行进行中（任何 `current_stage` 非 null 时）
- **阻止时提示**：运行 `stageflow complete`（正常完成）或 `stageflow reset`（放弃运行）后再编辑
- **无效 YAML 保护**：验证失败的保存不会覆盖已有配置文件

### 编辑器命令行

```bash
stageflow editor                              # 启动编辑器（默认 127.0.0.1:8000，自动打开浏览器）
stageflow editor --port 9000                  # 指定端口
stageflow editor --host 0.0.0.0 --port 8080  # 指定主机和端口
stageflow editor --no-open                    # 不打开浏览器（用于测试/无头环境）
stageflow editor --no-open --port 8765        # 无头模式，指定端口（CI/测试友好）
```

编辑器自动发现项目根（从当前目录向上查找 `.stageflow/`），绑定到该项目的配置。
从子目录启动时，更新的是祖先项目的 `.stageflow/config/stages.yaml`。

## 框架特性

### 工具拦截
- 全局 Hook 入口 `stageflow hook` — 项目通过 `.claude/settings.json` 配置，无需复制 hook 脚本
- Claude Code PreToolUse Hook 自动拦截非授权工具
- 从当前工作目录发现项目根，支持在子目录中运行
- 每阶段独立的工具白名单（支持通配符 `Bash(git *)`）
- 违规日志自动记录到 `<项目根>/.stageflow/guard_violations.jsonl`

### 生命周期 Hook
- `on_enter`: 进入阶段时执行的 Shell/Python 命令
- `on_exit`: 离开阶段时执行的 Shell/Python 命令
- Hook 失败不阻塞转移

### 条件缓存
- TTL 缓存避免重复评估昂贵条件
- 转移时自动刷新
- 可通过 `cache_ttl=0` 禁用

### 审计日志
- JSONL 格式记录所有转移、Hook 执行、工具违规
- 阶段耗时统计
- 可通过 `AuditLogger.get_summary()` 获取汇总

### 变量系统
- `set_var(key, value)` / `get_var(key)` 存储阶段变量
- 变量跨阶段持久化
- 可在条件中通过 `python_expr` 访问

### 运行身份与产物隔离 (Run Identity)
- `stageflow start` 开始新运行，自动生成唯一 `run_id` (UUID4)，存储在 `variables.run_id`
- 所有默认产物路径使用 `artifacts/runs/{{var.run_id}}/<stage>/` 隔离不同运行
- `stageflow reset` — 清除当前运行状态（放弃/重启）（不创建新运行）
- `stageflow reset --clean-artifacts` — 清除状态并删除当前运行的产物目录
- `stageflow reset --hard` — 完全清除状态文件
- `stageflow start [stage]` — 在 reset 后开始新运行（新 `run_id`），旧产物保留在磁盘
- **警告**: `reset` 仅清除 StageFlow 状态；产物保留在磁盘上，除非显式传递 `--clean-artifacts`

### 重试与回退
- 每阶段独立的重试计数器
- `on_fail` 配置自动回退目标
- 支持 verify → implement 重试循环

### Pytest 插件
- `stageflow_registry` / `stageflow_sm` 等 Fixture
- `@pytest.mark.stageflow("analyze")` 标记——非当前阶段自动跳过
- `N` 阶段动态配置工厂函数

### Editor 前端测试 (vitest)
```bash
cd editor
npm run test:run       # 单次运行全部测试 (vitest --run)
npm test               # watch 模式 (vitest)
```
- 测试文件位于 `editor/src/**/*.test.{ts,tsx}`
- 使用 `@testing-library/react` + `vitest` + `jsdom`
- 当前覆盖: YAML 工具 (23 tests), 条件定义工具 (11 tests), StageNode (8 tests), PropertiesPanel (25 tests), EdgeEditor (26 tests), App (27 tests), API 工具 (10 tests) — 共 7 文件 130 tests

## 工作约束（Claude 模型须知）

1. **不能手动修改** 状态文件 — 状态由框架管理
2. **不能跳过阶段** — 必须通过 `stageflow next` 进入下一阶段
3. **阶段内工具受限** — 使用未授权工具会被 Hook 拦截
4. **条件由框架判断** — 模型不能自行决定"条件已满足"
5. **失败自动回退** — verify 失败回退 implement，多次失败回退 plan
6. **框架不会说谎** — 条件评估结果是客观证据，不可伪造

## 目录完整结构

```
auto_workflow/
├── stageflow/
│   ├── __init__.py
│   ├── __main__.py            # CLI（python -m stageflow）
│   ├── core/
│   │   ├── conditions.py      # 30 种条件 + 缓存
│   │   ├── registry.py        # StageRegistry + 动态 CRUD
│   │   ├── engine.py          # StateMachine + 多重重试 + 生命周期
│   │   ├── guard.py           # Tool Guard + Claude Hook
│   │   ├── audit.py           # AuditLogger
│   │   ├── discovery.py       # 项目根发现（向上查找 .stageflow/）
│   │   └── mcp_server.py      # MCP Server (FastMCP)
│   ├── config/
│   │   └── stages.yaml        # 10 阶段 + 11 转移声明
│   ├── generator/
│   │   ├── llm_generator.py   # LLM 工作流生成器
│   │   └── prompts.py         # 4 种领域模板
│   ├── agent/
│   │   ├── runner.py          # Agent 运行时
│   │   ├── hybrid.py          # 混合工作流
│   │   └── orchestrator.py    # 并行编排器
│   └── artifacts/
├── editor/
│   ├── server.py              # FastAPI 后端 (17 端点)
│   └── src/                   # React + ReactFlow 前端
├── scripts/
│   ├── stage_next.py
│   ├── stage_status.py
│   ├── stage_reset.py
│   ├── stage_jump.py
│   ├── stage_back.py          # CLI 回退
│   ├── hooks_off.py
│   └── hooks_on.py
├── tests/
│   ├── conftest.py            # Fixtures + Pytest 插件
│   ├── test_conditions.py     # 282 tests
│   ├── test_registry.py       # 93 tests
│   ├── test_engine.py         # 92 tests
│   ├── test_guard.py          # 23 tests
│   ├── test_discovery.py      # 18 tests
│   ├── test_edge_cases.py     # 11 tests
│   ├── test_e2e.py            # 25 tests
│   ├── test_extensibility.py  # 28 tests
│   ├── test_extensibility_quick.py # 1 test
│   ├── test_agent.py          # 35 tests
│   ├── test_benchmark.py      # 18 tests
│   ├── test_cache.py          # 31 tests
│   ├── test_concurrency.py    # 21 tests
│   ├── test_generator.py      # 50 tests
│   ├── test_hooks_integration.py # 17 tests
│   ├── test_hybrid.py         # 30 tests
│   ├── test_main.py           # 218 tests
│   ├── test_orchestrator.py   # 33 tests
│   ├── test_perf.py           # 7 tests
│   ├── test_editor_e2e.py     # 29 tests
│   ├── test_server.py         # 80 tests
│   ├── test_audit.py          # 18 tests
│   ├── test_mcp_server.py     # 19 tests
│   └── test_stress.py         # 18 tests
├── .claude/
│   ├── settings.json          # PreToolUse Hook 配置（指向 stageflow hook）
│   ├── settings.local.json
│   ├── current_stage.json     # Legacy 状态文件（新项目使用 .stageflow/）
│   └── hooks/
│       └── stage_guard.py     # Legacy Hook 入口（新项目使用 stageflow hook）
├── .stageflow/                # 新项目元数据目录
│   ├── config/
│   │   └── stages.yaml        # 项目阶段配置
│   ├── current_stage.json     # 当前运行状态
│   └── guard_violations.jsonl # 工具违规日志
├── .ralph/                    # Ralph Agent 数据
├── pyproject.toml             # pip install -e .
└── CLAUDE.md                  # 本文档
```
