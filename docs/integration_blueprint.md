# StageFlow — Integration Blueprint

> **Created**: 2026-05-10
> **Source**: task-023 — based on framework and agent pattern research (task-021/022)
> **Status**: Design proposal — top 3 improvements to be implemented in task-024

---

## 1. Overview

This blueprint defines three integration paths that make StageFlow interoperable with the broader agent/AI ecosystem:

| # | Integration | Pattern | Priority | Effort |
|---|-------------|---------|----------|--------|
| **A** | Condition severity levels (warn/soft/hard) | n8n condition taxonomy | **High** | Small |
| **B** | MCP Server — expose conditions as tools | Temporal/LangGraph pattern | **Medium** | Medium |
| **C** | REST API for external workflow editors | n8n/Dify pattern | **Medium** | Medium |

---

## 2. Blueprint A: Condition Severity Levels

**Inspiration**: n8n's IF/Switch/Filter node taxonomy and Prefect's state hooks with different failure modes.

**Problem**: Currently all StageFlow condition failures block transitions equally. In practice, different conditions should have different severity:
- Some conditions are **informational** (log a warning but proceed)
- Some require **retries** (try again N times before blocking)
- Some are **hard gates** (block immediately, no retry)

**Design**:

```yaml
transitions:
  - from: implement
    to: verify
    conditions:
      - file_exists: dist/
        severity: warn              # log but don't block
      - shell_test:
          command: "pytest -q"
          op: exit_zero
        severity: soft              # retry 3x before blocking (default)
      - diff_contains:
          pattern: "eval\\("
          op: not_contains
        severity: hard              # block immediately, no retry
    on_fail: implement
```

**Implementation plan**:
1. Add `severity` field to condition evaluation (default: `soft`)
2. `warn`: always returns True, logs warning message
3. `soft`: retries up to `max_attempts` (configurable), then blocks
4. `hard`: fails immediately on first check
5. Extend `evaluate_all()` to handle severity tiers
6. Tests: ~8 new tests

**Files**: `stageflow/core/conditions.py`

---

## 3. Blueprint B: MCP Server for Condition Evaluation

**Inspiration**: Temporal's MCP tool durability pattern and LangGraph's tool-as-node architecture.

**Problem**: StageFlow conditions can only be used within StageFlow workflows. External systems (CI/CD pipelines, monitoring tools, other agent frameworks) can't leverage StageFlow's 27 condition types.

**Design**: Expose StageFlow conditions via Model Context Protocol (MCP), allowing any MCP-compatible agent to evaluate conditions.

```
┌──────────────────────┐     MCP Protocol     ┌──────────────────────┐
│  External Agent      │ ◄──────────────────► │  StageFlow MCP Server │
│  (Claude, Cursor,    │                      │                       │
│   VS Code, etc.)     │  evaluate_condition  │  27 condition types   │
│                      │  list_conditions     │  Variable interpolation│
│                      │  validate_config     │  Audit logging        │
└──────────────────────┘                      └──────────────────────┘
```

**MCP Tools**:
| Tool | Description |
|------|-------------|
| `stageflow_evaluate_condition` | Evaluate a single condition with params |
| `stageflow_evaluate_all` | Evaluate all conditions on a transition |
| `stageflow_list_conditions` | List all 27 condition types with param schemas |
| `stageflow_validate_config` | Validate a stages.yaml configuration |
| `stageflow_get_status` | Get current workflow status (stage, history, retries) |
| `stageflow_check_transition` | Check if a transition is allowed from current stage |

**Implementation plan**:
1. Create `stageflow/mcp/server.py` using `mcp` Python SDK
2. Register MCP tools wrapping existing condition functions
3. Support variable interpolation from MCP context
4. Tests: mock MCP client, ~10 tests
5. CLI: `python -m stageflow mcp-serve` to start the server

**Files**: `stageflow/mcp/__init__.py`, `stageflow/mcp/server.py`

---

## 4. Blueprint C: REST API for External Workflow Editors

**Inspiration**: Dify's API + n8n's node API pattern.

**Problem**: StageFlow's React editor (`editor/`) has a FastAPI backend with basic endpoints. Expanding the API makes StageFlow embeddable in any external editor, CI/CD system, or dashboard.

**Design**: Extend the existing `editor/server.py` API with workflow management endpoints.

```
GET    /api/health                    Health check
GET    /api/conditions                List 27 condition types with schemas (existing)
POST   /api/validate                  Validate YAML config (existing)
POST   /api/run                       Check transition conditions (existing)
POST   /api/generate                  Generate workflow from NL description (new)
GET    /api/workflows                 List saved workflows
GET    /api/workflows/{name}          Get workflow YAML
PUT    /api/workflows/{name}          Save/update workflow YAML
DELETE /api/workflows/{name}          Delete workflow
POST   /api/workflows/{name}/run      Execute workflow through pipeline
GET    /api/workflows/{name}/status   Get current stage + history
POST   /api/workflows/{name}/pause    Pause workflow
POST   /api/workflows/{name}/resume   Resume workflow
GET    /api/audit                     Get recent audit log entries
GET    /api/audit/summary             Get audit summary statistics
```

**Implementation plan**:
1. Extend `editor/server.py` with workflow CRUD endpoints (in-memory or file-based storage)
2. Add `POST /api/generate` using `WorkflowGenerator`
3. Add workflow execution endpoints using `StateMachine` + `HybridWorkflow`
4. Add audit log query endpoints
5. Tests: ~15 new tests
6. OpenAPI/Swagger docs auto-generated by FastAPI

**Files**: `editor/server.py`

---

## 5. Top 3 Improvements for Immediate Implementation (task-024)

Based on research impact-to-effort ratio, the top 3 to implement:

### #1: Condition Severity Levels (Blueprint A)
- **Impact**: High — addresses the "80% problem" by allowing non-critical checks without blocking
- **Effort**: Small — localized to `conditions.py`
- **Tests**: ~8

### #2: Audit Log Query API (Blueprint C subset)
- **Impact**: Medium — enables external dashboards and monitoring
- **Effort**: Small — 2-3 new endpoints in existing server.py
- **Tests**: ~6

### #3: Workflow Run API with Stage Advance (Blueprint C subset)
- **Impact**: High — enables external orchestration of StageFlow pipelines
- **Effort**: Medium — 3 new endpoints
- **Tests**: ~8

---

## 6. Future Integrations (Phase 11+)

These are documented in `TASK_PLAN.md` Phase 11 and remain as future work:

- **GitHub Actions integration**: CI/CD YAML templates using StageFlow conditions
- **Docker image**: Containerized StageFlow + editor deployment
- **VS Code extension**: Stage status bar indicator + YAML validation
- **Linear/Notion sync**: Auto-link issues to StageFlow workflow stages
- **Multi-project shared config**: Inheritance/reference mechanism for stages.yaml

---

## 7. Architecture Decision Records

### ADR-001: Why MCP over direct REST for conditions?
- MCP provides standardized tool discovery and execution for AI agents
- REST is better for human-facing dashboards and CI/CD systems
- **Decision**: Build both — MCP for agent integration, REST for dashboard/CI integration

### ADR-002: Why in-memory workflow storage initially?
- StageFlow targets single-agent workflows first
- File-based persistence (.claude/current_stage.json) is sufficient
- PostgreSQL/Redis adds deployment complexity disproportionate to current scope
- **Decision**: File-based persistence for v1; add SQL backend as optional in Phase 11

### ADR-003: Why severity levels over full condition taxonomy?
- n8n's IF/Switch/Code/Filter/Loop/Merge taxonomy is powerful but complex
- 3-tier severity (warn/soft/hard) covers 90% of use cases with minimal complexity
- Full taxonomy can be added later as an extension
- **Decision**: 3-tier severity for v1
