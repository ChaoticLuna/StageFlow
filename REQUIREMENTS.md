# StageFlow — 总需求文档

## 1. 项目愿景

构建一套**声明式、可扩展的阶段化状态机框架**，用于约束 AI Coding Agent 按照固定
工作周期执行 Issue 交付任务。核心原则：**框架负责所有阶段判定，AI 模型不参与规则判断。**

## 2. 核心需求

### 2.1 声明式阶段定义

- 阶段必须在 YAML 配置文件中定义，不允许硬编码
- 每个阶段指定允许的工具白名单（支持通配符如 `Bash(git *)`）
- 阶段支持 `on_enter` / `on_exit` 生命周期 Hook

### 2.2 条件门控转移

- 阶段之间的转移由条件（Condition）控制
- 条件由框架评估，AI 模型**不能自行判断**条件是否满足
- 条件必须可扩展：用户可通过 `@register()` 注册自定义条件类型
- 内置至少 20 种通用条件类型

### 2.3 工具拦截

- 通过 Claude Code PreToolUse Hook 实时拦截未授权工具调用
- 每个阶段的工具白名单动态生效
- 违规日志自动记录

### 2.4 状态持久化

- 当前阶段、历史记录、变量、重试计数持久化到 JSON 文件
- 支持跨会话恢复

### 2.5 回退与重试

- 条件失败时支持自动回退到 `on_fail` 指定阶段
- 每阶段独立重试计数
- 支持 verify → implement 重试循环

### 2.6 审计日志

- JSONL 格式记录所有转移、Hook 执行、工具违规
- 阶段耗时统计

### 2.7 变量系统

- 跨阶段持久化的 Key-Value 变量
- 条件参数支持 `{{var.key}}` 变量插值

## 3. 技术架构

```
Stage (节点) + Transition (连线) + Condition (条件) = 状态机
```

### 核心模块

| 模块 | 职责 |
|------|------|
| `conditions.py` | 条件系统：注册、评估、缓存、变量插值 |
| `registry.py` | 阶段注册表：Stage/Transition CRUD、图验证 |
| `engine.py` | 状态机引擎：转移判定、回退、生命周期 Hook、变量管理 |
| `guard.py` | 工具守卫：Claude Code Hook 集成，拦截未授权工具 |
| `audit.py` | 审计日志：JSONL 格式，阶段计时 |
| `schema.py` | YAML 配置校验 |

## 4. 默认管道阶段

```
pick → analyze → plan → implement → verify → document → mr → review → wrap_up → done
```

每个阶段指定允许的工具，如 `implement` 允许 `[Read, Write, Edit, Bash(git *), Bash(python *)]`。

## 5. 非功能性需求

- 跨平台兼容（Windows/Linux/macOS）
- 测试覆盖率 > 90%
- pip install -e . 一键安装
- CLI 入口 `python -m stageflow`
- 100 阶段的可扩展性

## 6. 约束条件

1. AI 模型**不能手动修改** `.claude/current_stage.json`
2. AI 模型**不能跳过阶段**
3. AI 模型**不能自行判定条件已满足**
4. 条件评估结果必须是客观证据，不可伪造
5. 新增阶段必须零代码改动（仅 YAML 配置）

## 7. 未来方向

- [ ] 工作流并发分支与聚合
- [ ] Webhook/通知集成（Slack、企业微信）
- [ ] Web UI 状态面板
- [ ] 暂停/恢复执行
- [ ] 并行条件评估
- [ ] 软性门控（warn 但不阻止）
- [ ] 与 Linear/Notion 的任务追踪集成
