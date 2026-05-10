# StageFlow — Harness Engineering Research

> **Last updated**: 2026-05-10
> **Source**: task-021 — competing framework analysis

---

## 1. Executive Summary

StageFlow sits at the intersection of **workflow orchestration** (Dify, n8n, Prefect), **durable execution** (Temporal), and **agent state management** (LangGraph). This document compares five leading frameworks, identifies StageFlow's unique positioning, and recommends improvements.

---

## 2. Framework Comparison

### 2.1 Dify (langgenius/dify)

**Type**: Visual AI workflow builder with backend engine
**Language**: Python + TypeScript
**License**: Apache 2.0 (open source)

**Architecture Highlights**:
- **DAG-based execution**: Topological sort for dependency management
- **Queue-based Graph Engine** (v1.9.0): Unified task queue → dispatcher → auto-scaling worker pool
- **Stateful pause/resume** (v1.13.0): Human-in-the-Loop via Redis Pub/Sub + Celery workers
- **Plugin architecture**: GraphEngineLayer for monitoring, command injection, observability
- **Event system**: Graph-level and node-level events (RunStarted, RunSucceeded, RunFailed, RunRetry, StreamChunk)
- **Execution limits**: 500 max steps, 1200s max time, 10 max call depth

**Relevance to StageFlow**: Dify's condition evaluation is **LLM-driven** (the AI decides routing). StageFlow inverts this — **framework conditions are deterministic**, the AI only acts. Dify's event system and GraphEngineLayer are directly applicable patterns.

### 2.2 LangGraph (LangChain)

**Type**: Graph-based agent state machine framework
**Language**: Python + TypeScript
**License**: MIT

**Architecture Highlights**:
- **StateGraph model**: Nodes (LLM calls/tools) + Edges (static/conditional) + Structured State
- **Pregel execution engine**: Message-passing graph computation with supersteps (inspired by Google Pregel)
- **Checkpointing**: State snapshots at every superstep; pause/resume/retry from known-good points
- **Memory stores**: InMemorySaver (dev), Aerospike (sub-ms production), SQL, message queues
- **Execution modes**: Sequential, parallel (within superstep), conditional routing, fixed/condition-terminated/dynamic looping
- **Human-in-the-Loop**: `interruptBefore` / `interruptAfter` — pause at specified nodes
- **LangSmith integration**: Tracing, visualization, debugging

**Relevance to StageFlow**: LangGraph and StageFlow share the **state-machine-as-agent-controller** philosophy. Key difference: LangGraph puts LLM *inside* the graph logic (routing decisions are LLM-driven). StageFlow keeps LLM *outside* the state machine — conditions are deterministic checks. This makes StageFlow more suitable for environments where **auditability and non-repudiation** matter.

**Industry note** (April 2026): Thoughtworks moved LangGraph from "Adopt" to "Trial", noting that global shared state graphs are not always the best pattern. Simpler agent-to-agent communication via code execution (Pydantic AI pattern) is gaining traction.

### 2.3 n8n

**Type**: Visual node-based workflow automation (fair-code)
**Language**: TypeScript
**License**: Sustainable Use License (source-available)

**Architecture Highlights**:
- **Node-based DAG**: Triggers → Actions → Utility nodes connected by directed edges
- **Condition system**: IF node (binary branch), Switch node (multi-way routing), Code node (arbitrary JavaScript logic), Filter node (data gating)
- **Expression language**: JSONata for data querying and transformation across nodes
- **400+ official nodes, ~2,000 community nodes**: PostgreSQL, REST, GraphQL, Kafka, LLMs, etc.
- **Error handling**: Node-level retry with exponential backoff → workflow-level error handler → alerting
- **AI integration pattern**: Pre-process (validate data) → AI step → Post-process (validate/route AI outputs with rule-based logic)

**Relevance to StageFlow**: n8n's **condition node taxonomy** (IF/Switch/Code/Filter/Loop/Merge) maps closely to StageFlow's transition condition system. n8n's "deterministic gates around AI steps" pattern is exactly StageFlow's core design principle. n8n is visual-first; StageFlow is **code/YAML-first** — better for agentic CI/CD pipelines.

### 2.4 Temporal.io

**Type**: Durable execution platform
**Language**: Go + SDKs for Python, TypeScript, Java, .NET
**License**: MIT

**Architecture Highlights**:
- **Deterministic execution model**: Workflows (orchestration logic, deterministic) + Activities (side effects, non-deterministic — API calls, LLM invocations, DB writes)
- **Event sourcing**: All state changes captured in Event History. Worker crash → replay from history with saved Activity results → resume exactly where left off
- **Serverless Workers** (May 2026): Lambda-based, no idle compute
- **Workflow Streams**: Durable streaming for live monitoring and AI guardrails
- **Primitives**: Workflows, Activities, Signals (push data to running workflows), Queries (inspect state), Updates (process + return + validate), Timers (survive restarts — days/weeks/months)
- **Versioning**: Worker Versioning with Build IDs, GetVersion/Patching APIs, Replay Testing in CI/CD
- **Limits**: 51,200 events or 50 MB per run; Continue-As-New for infinite workflows

**AI Agent Integration**: Temporal is positioning as the **reliability layer for AI agents**. Each MCP tool → backed by a Temporal Workflow. Agent chain reliability: 5 steps at 95% each = 77% overall. Temporal provides checkpoints, auto-retry, and self-healing at each step.

**Relevance to StageFlow**: Temporal's durability model is the **gold standard** for workflow reliability. StageFlow could benefit from: (a) Event History-based replay for audit/debugging, (b) Signal/Query patterns for external interaction during a stage, (c) Continue-As-New for long-running agent loops. However, Temporal is heavy infrastructure — StageFlow's JSON-file persistence is appropriate for single-agent CI/CD use cases.

### 2.5 Prefect

**Type**: Pythonic workflow orchestration
**Language**: Python
**License**: Apache 2.0 (open source)

**Architecture Highlights**:
- **Hybrid architecture**: Server (REST API + orchestration) + Workers (poll work pools, execute flows) + PostgreSQL + Web UI
- **Dynamic DAGs**: Task graph derived from normal Python control flow (`@flow` + `@task` decorators) — not static like Airflow
- **`.serve()` deployment**: Zero-infrastructure — run Python anywhere, no Docker/K8s required
- **Task Runners**: ThreadPool, Dask-based, mapped tasks via `.map()`
- **Caching**: `task_input_hash` → auto cache keys from inputs; `cache_expiration` TTL
- **State hooks**: `on_completion`, `on_failure`, `on_cancellation`, `on_crashed`, `on_running`
- **Pydantic AI integration**: `PrefectAgent` wraps AI agents as Prefect flows; model requests + tool calls become discrete Prefect tasks

**Critical gap identified** (March 2026): Prefect's execution model is still fundamentally **task scheduling** — tasks fire when dependencies are satisfied. It provides retrospective **observability** but lacks **prospective semantic governance** — validating whether a task *should* run given agent confidence, memory state, trust slope. This is exactly the gap StageFlow fills with its condition-gated transitions.

---

## 3. StageFlow's Unique Positioning

| Feature | Dify | LangGraph | n8n | Temporal | Prefect | **StageFlow** |
|---------|------|-----------|-----|----------|---------|---------------|
| **Condition author** | LLM | LLM + code | Human (visual) | Code | Code | **Framework (deterministic)** |
| **State machine** | Implicit | Explicit (StateGraph) | Implicit (DAG) | Workflow (deterministic) | DAG (dynamic) | **Explicit (Stage+Transition)** |
| **LLM integration** | Built-in | Core feature | Plugin nodes | Activity pattern | Pydantic AI | **Pluggable (llm_call)** |
| **Persistence** | Redis + DB | Checkpoint stores | DB | Event History | PostgreSQL | **JSON files (.claude/)** |
| **Visual editor** | Full canvas | LangSmith (tracing) | Full canvas | Temporal UI | Prefect UI | **React Flow editor** |
| **Open source** | Apache 2.0 | MIT | Fair-code | MIT | Apache 2.0 | **MIT-compatible** |
| **Agent-native** | Yes (AI workflows) | Yes (StateGraph) | Via plugins | Yes (durable) | Emerging | **Yes (AgentRunner + HybridWorkflow)** |
| **Deploy complexity** | Medium | Low (CLI) | Low (Docker) | High (Server + Workers) | Medium | **Zero (pip install)** |

**StageFlow's niche**: A **lightweight, deterministic, auditable state machine** that wraps AI agent execution with **framework-evaluated condition gates**. Unlike every other system where the AI decides routing, StageFlow ensures **the framework decides, the AI obeys**.

---

## 4. Recommended Improvements from Research

### 4.1 High Priority (from Temporal/Dify)

1. **Event History Replay** (Temporal pattern): Store full condition evaluation results in audit trail for deterministic replay. Already partially implemented via AuditLogger — extend to support replay debugging.

2. **External Signals/Queries** (Temporal pattern): Allow external processes to send signals (pause, resume, inject data) into a running workflow. The pause/resume added in task-019 is a first step.

3. **Graph-level event hooks** (Dify pattern): `on_stage_enter`, `on_stage_exit`, `on_transition_fail`, `on_workflow_complete` — beyond current `on_enter`/`on_exit` per stage. Dify's `GraphEngineLayer` plugin pattern is applicable.

### 4.2 Medium Priority (from n8n/Prefect)

4. **Condition severity levels** (n8n pattern): Not all condition failures should block — add "warn" (log but proceed), "soft_block" (retry N times), "hard_block" (stop). Currently all failures block.

5. **Task caching with hash keys** (Prefect pattern): `task_input_hash` for caching expensive condition evaluations. StageFlow's existing `_CONDITION_CACHE` with TTL is comparable but less granular.

6. **Expression language in conditions** (n8n pattern): JSONata-style expressions for data transformation in conditions. StageFlow's `{{var.key}}` interpolation is simpler but adequate for current use.

### 4.3 Lower Priority (from LangGraph)

7. **Checkpoint-based resume** (LangGraph pattern): State snapshots at each stage boundary for rollback. StageFlow's `reset()` is coarse-grained; per-stage checkpointing would be more surgical.

8. **Multiple execution backends** (LangGraph pattern): InMemorySaver (dev) → SQLite (small) → PostgreSQL (production). StageFlow's JSON file persistence is fine for single-agent but limits multi-agent scenarios.

---

## 5. Key Takeaway

StageFlow is **not a Dify/n8n competitor** (visual AI workflow builder) nor a **Temporal competitor** (heavy-duty durable execution). It occupies a unique position: **a developer-facing, YAML-declarative, deterministic condition-gating layer for AI coding agents**. Its closest conceptual peer is LangGraph's StateGraph, but with the critical inversion: **conditions are framework-evaluated, not LLM-evaluated**.

This distinction makes StageFlow particularly suited for:
- **CI/CD pipelines** where audit trails must be non-repudiable
- **Compliance-sensitive workflows** where AI decisions need deterministic verification
- **Autonomous AI developer loops** (like Ralph) where the harness must prevent the agent from skipping steps or using unauthorized tools
