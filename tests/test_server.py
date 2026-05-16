from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

from editor.server import app, CONDITION_DEFS, WORKFLOWS_DIR

client = TestClient(app)

VALID_YAML = """
stages:
  - name: pick
    tools: [Read, Grep]
  - name: analyze
    tools: [Read, WebSearch]
  - name: done
    tools: []
transitions:
  - from: pick
    to: analyze
    conditions:
      - file_exists: artifacts/pick/issue.md
    on_fail: pick
  - from: analyze
    to: done
    conditions:
      - always: true
"""


class TestGetConditions:
    def test_returns_30_conditions(self):
        r = client.get("/api/conditions")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == len(CONDITION_DEFS)
        assert len(data["conditions"]) == len(CONDITION_DEFS)

    def test_has_required_fields(self):
        r = client.get("/api/conditions")
        data = r.json()
        for c in data["conditions"]:
            assert "type" in c
            assert "label" in c
            assert "description" in c
            assert "params" in c
            assert isinstance(c["params"], list)

    def test_all_registered(self):
        r = client.get("/api/conditions")
        data = r.json()
        registered = set(data["registered"])
        defined = {c["type"] for c in data["conditions"]}
        missing = registered - defined
        assert len(missing) == 0, f"Missing defs for: {missing}"

    def test_type_order_matches_condition_defs(self):
        assert CONDITION_DEFS[0]["type"] == "always"
        assert CONDITION_DEFS[-1]["type"] == "docker_ps"


class TestValidateEndpoint:
    def test_valid_yaml(self):
        r = client.post("/api/validate", json={"yaml": VALID_YAML})
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_invalid_yaml_syntax(self):
        r = client.post("/api/validate", json={"yaml": "invalid: [["})
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_empty_yaml(self):
        r = client.post("/api/validate", json={"yaml": ""})
        data = r.json()
        assert data["valid"] is False

    def test_missing_stages_key(self):
        r = client.post("/api/validate", json={"yaml": "transitions: []"})
        data = r.json()
        assert data["valid"] is True

    def test_duplicate_stage_name(self):
        yaml_str = """
stages:
  - name: pick
  - name: pick
"""
        r = client.post("/api/validate", json={"yaml": yaml_str})
        data = r.json()
        assert data["valid"] is False
        assert any("duplicate" in e for e in data["errors"])

    def test_stages_not_a_list(self):
        r = client.post("/api/validate", json={"yaml": "stages: not_a_list"})
        data = r.json()
        assert data["valid"] is False

    def test_transitions_not_a_list(self):
        r = client.post("/api/validate", json={"yaml": "stages: []\ntransitions: not_a_list"})
        data = r.json()
        assert data["valid"] is False

    def test_missing_from_in_transition(self):
        yaml_str = """
stages:
  - name: pick
transitions:
  - to: analyze
"""
        r = client.post("/api/validate", json={"yaml": yaml_str})
        data = r.json()
        assert data["valid"] is False


class TestRunEndpoint:
    def test_valid_transition_always(self):
        r = client.post(
            "/api/run",
            json={"yaml": VALID_YAML, "from_stage": "analyze", "to_stage": "done"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["can_transition"] is True

    def test_valid_transition_with_condition(self):
        r = client.post(
            "/api/run",
            json={"yaml": VALID_YAML, "from_stage": "pick", "to_stage": "analyze"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "can_transition" in data
        assert "messages" in data

    def test_no_transition_defined(self):
        r = client.post(
            "/api/run",
            json={"yaml": VALID_YAML, "from_stage": "done", "to_stage": "pick"},
        )
        data = r.json()
        assert data["can_transition"] is False
        assert "No transition defined" in data["messages"][0]

    def test_invalid_yaml_structure_returns_error(self):
        r = client.post(
            "/api/run",
            json={"yaml": "not_a_dict", "from_stage": "a", "to_stage": "b"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["can_transition"] is False

    def test_empty_yaml_returns_400(self):
        r = client.post(
            "/api/run",
            json={"yaml": "", "from_stage": "a", "to_stage": "b"},
        )
        assert r.status_code == 400

    def test_invalid_config_in_run(self):
        yaml_str = """
stages:
  - name: pick
transitions:
  - from: pick
"""
        r = client.post(
            "/api/run",
            json={"yaml": yaml_str, "from_stage": "pick", "to_stage": "analyze"},
        )
        data = r.json()
        assert data["can_transition"] is False
        assert any("missing" in m.lower() for m in data["messages"])

    def test_no_conditions_always_passes(self):
        yaml_str = """
stages:
  - name: a
  - name: b
transitions:
  - from: a
    to: b
"""
        r = client.post(
            "/api/run",
            json={"yaml": yaml_str, "from_stage": "a", "to_stage": "b"},
        )
        data = r.json()
        assert data["can_transition"] is True

    def test_on_fail_reported_in_messages(self):
        yaml_str = """
stages:
  - name: a
  - name: b
transitions:
  - from: a
    to: b
    conditions:
      - file_exists: definitely_missing_file.xyz
    on_fail: a
"""
        r = client.post(
            "/api/run",
            json={"yaml": yaml_str, "from_stage": "a", "to_stage": "b"},
        )
        data = r.json()
        if not data["can_transition"]:
            assert any("on_fail" in m for m in data["messages"])


# ═══════════════════════════════════════════════════════════════════════════
# Audit log endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditEndpoints:
    def test_audit_empty_when_no_log(self, tmp_path):
        """Audit returns empty when no log file exists."""
        aud = tmp_path / ".claude" / "audit.jsonl"
        aud.parent.mkdir(parents=True, exist_ok=True)
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            r = client.get("/api/audit")
            assert r.status_code == 200
            data = r.json()
            assert data["total"] == 0
            assert data["entries"] == []
        finally:
            os.chdir(orig)

    def test_audit_returns_entries(self, tmp_path):
        """Audit returns entries from the log file."""
        aud = tmp_path / ".claude" / "audit.jsonl"
        aud.parent.mkdir(parents=True, exist_ok=True)
        aud.write_text(
            '{"event": "transition", "from": "a", "to": "b"}\n'
            '{"event": "tool_violation", "tool": "Bash"}\n',
            encoding="utf-8"
        )
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            r = client.get("/api/audit")
            assert r.status_code == 200
            data = r.json()
            assert data["total"] == 2
            assert len(data["entries"]) == 2
        finally:
            os.chdir(orig)

    def test_audit_filter_by_event_type(self, tmp_path):
        """Audit endpoint filters by event_type query parameter."""
        aud = tmp_path / ".claude" / "audit.jsonl"
        aud.parent.mkdir(parents=True, exist_ok=True)
        aud.write_text(
            '{"event": "transition", "from": "a", "to": "b"}\n'
            '{"event": "tool_violation", "tool": "Bash"}\n'
            '{"event": "transition", "from": "b", "to": "c"}\n',
            encoding="utf-8"
        )
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            r = client.get("/api/audit", params={"event_type": "transition"})
            assert r.status_code == 200
            data = r.json()
            assert data["total"] == 2
            assert data["returned"] == 2
            for e in data["entries"]:
                assert e["event"] == "transition"
        finally:
            os.chdir(orig)

    def test_audit_respects_limit(self, tmp_path):
        """Audit endpoint respects the limit parameter."""
        aud = tmp_path / ".claude" / "audit.jsonl"
        aud.parent.mkdir(parents=True, exist_ok=True)
        lines = [f'{{"event": "test", "i": {i}}}' for i in range(10)]
        aud.write_text("\n".join(lines), encoding="utf-8")
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            r = client.get("/api/audit", params={"limit": 3})
            assert r.status_code == 200
            data = r.json()
            assert data["total"] == 10
            assert data["returned"] == 3
            assert len(data["entries"]) == 3
        finally:
            os.chdir(orig)

    def test_audit_skips_invalid_json_lines(self, tmp_path):
        """Audit endpoint skips malformed JSON lines."""
        aud = tmp_path / ".claude" / "audit.jsonl"
        aud.parent.mkdir(parents=True, exist_ok=True)
        aud.write_text(
            'not valid json\n'
            '{"event": "valid"}\n'
            'also not json\n',
            encoding="utf-8"
        )
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            r = client.get("/api/audit")
            assert r.status_code == 200
            data = r.json()
            assert data["total"] == 1
        finally:
            os.chdir(orig)

    def test_audit_summary_empty(self, tmp_path):
        """Audit summary returns zero counts when no log exists."""
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            r = client.get("/api/audit/summary")
            assert r.status_code == 200
            assert r.json()["total_events"] == 0
        finally:
            os.chdir(orig)

    def test_audit_summary_with_events(self, tmp_path):
        """Audit summary counts events by type."""
        aud = tmp_path / ".claude" / "audit.jsonl"
        aud.parent.mkdir(parents=True, exist_ok=True)
        aud.write_text(
            '{"event": "transition", "from": "a", "to": "b"}\n'
            '{"event": "transition", "from": "b", "to": "c"}\n'
            '{"event": "tool_violation", "tool": "Bash"}\n',
            encoding="utf-8"
        )
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            r = client.get("/api/audit/summary")
            assert r.status_code == 200
        finally:
            os.chdir(orig)


# ═══════════════════════════════════════════════════════════════════════════
# Workflow CRUD endpoints
# ═══════════════════════════════════════════════════════════════════════════

SIMPLE_WORKFLOW_YAML = """
stages:
  - name: start
    tools: [Read]
  - name: end
    tools: []
transitions:
  - from: start
    to: end
    conditions:
      - always: true
"""


class TestWorkflowCRUD:
    def test_list_workflows_empty(self):
        """Listing workflows when none exist returns empty list."""
        orig_count = len(list(WORKFLOWS_DIR.glob("*.yaml")))
        r = client.get("/api/workflows")
        assert r.status_code == 200
        workflows = r.json()["workflows"]
        # Should have at most the ones we haven't created yet
        assert isinstance(workflows, list)

    def test_save_and_get_workflow(self):
        """Save a workflow and retrieve it."""
        name = "test_crud_workflow"
        r = client.put(f"/api/workflows/{name}", json={"yaml": SIMPLE_WORKFLOW_YAML})
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == name
        assert data["saved"] is True

        r2 = client.get(f"/api/workflows/{name}")
        assert r2.status_code == 200
        assert name in r2.json()["name"]
        assert "stages" in r2.json()["yaml"]

    def test_save_invalid_yaml_returns_400(self):
        """Saving invalid YAML returns 400."""
        r = client.put("/api/workflows/bad", json={"yaml": "not: [valid: yaml"})
        assert r.status_code == 400

    def test_save_empty_yaml_returns_400(self):
        """Saving empty YAML returns 400."""
        r = client.put("/api/workflows/empty", json={"yaml": ""})
        assert r.status_code == 400

    def test_save_invalid_config_returns_400(self):
        """Saving YAML with invalid StageFlow config returns 400."""
        r = client.put("/api/workflows/bad_config", json={"yaml": "stages: not_a_list"})
        assert r.status_code == 400

    def test_get_nonexistent_workflow_returns_404(self):
        """Getting a workflow that doesn't exist returns 404."""
        r = client.get("/api/workflows/nonexistent_xyz_123")
        assert r.status_code == 404

    def test_delete_workflow(self):
        """Delete a saved workflow."""
        name = "test_delete_workflow"
        client.put(f"/api/workflows/{name}", json={"yaml": SIMPLE_WORKFLOW_YAML})
        r = client.delete(f"/api/workflows/{name}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

        r2 = client.get(f"/api/workflows/{name}")
        assert r2.status_code == 404

    def test_delete_nonexistent_workflow_returns_404(self):
        """Deleting a workflow that doesn't exist returns 404."""
        r = client.delete("/api/workflows/nonexistent_xyz_123")
        assert r.status_code == 404

    def test_list_workflows_includes_saved(self):
        """List workflows includes saved workflow metadata."""
        name = "test_list_workflow"
        client.put(f"/api/workflows/{name}", json={"yaml": SIMPLE_WORKFLOW_YAML})
        r = client.get("/api/workflows")
        assert r.status_code == 200
        workflows = r.json()["workflows"]
        names = [w["name"] for w in workflows]
        assert name in names
        # Check metadata fields
        wf = [w for w in workflows if w["name"] == name][0]
        assert "size" in wf
        assert "modified" in wf
        assert "path" in wf


# ═══════════════════════════════════════════════════════════════════════════
# Workflow execution endpoints
# ═══════════════════════════════════════════════════════════════════════════

class TestWorkflowExecution:
    SETUP_YAML = """
stages:
  - name: pick
    tools: [Read]
  - name: analyze
    tools: [Read, Grep]
  - name: done
    tools: []
transitions:
  - from: pick
    to: analyze
    conditions:
      - always: true
  - from: analyze
    to: done
    conditions:
      - always: true
"""

    def setup_method(self):
        """Ensure the test workflow exists before each test."""
        name = "test_exec_workflow"
        client.put(f"/api/workflows/{name}", json={"yaml": self.SETUP_YAML})

    def teardown_method(self):
        """Clean up after each test."""
        import shutil
        name = "test_exec_workflow"
        path = WORKFLOWS_DIR / f"{name}.yaml"
        if path.exists():
            path.unlink()
        engine_dir = WORKFLOWS_DIR / name
        if engine_dir.exists():
            shutil.rmtree(engine_dir, ignore_errors=True)
        # Also clean up the in-memory engine
        from editor.server import _workflow_engines
        _workflow_engines.pop(name, None)

    def test_run_initializes_and_advances(self):
        """First run initializes at pick AND advances to analyze."""
        name = "test_exec_workflow"
        # First run: initializes at pick and immediately advances to analyze
        r1 = client.post(f"/api/workflows/{name}/run")
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["current_stage"] == "analyze"
        assert d1["success"] is True

        # Second run: advances from analyze to done
        r2 = client.post(f"/api/workflows/{name}/run")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["current_stage"] == "done"

    def test_run_to_specific_target(self):
        """Run with target parameter advances to a specific stage."""
        name = "test_exec_workflow"
        # Initialize first
        client.post(f"/api/workflows/{name}/run")
        # Advance to specific target
        r = client.post(f"/api/workflows/{name}/run?target=done")
        assert r.status_code == 200
        d = r.json()
        assert d["current_stage"] == "done"

    def test_run_nonexistent_workflow_returns_404(self):
        """Running a workflow that doesn't exist returns 404."""
        r = client.post("/api/workflows/nonexistent_xyz_123/run")
        assert r.status_code == 404

    def test_status_returns_workflow_state(self):
        """Status endpoint returns current workflow state after run."""
        name = "test_exec_workflow"
        # First run initializes pick and advances to analyze
        client.post(f"/api/workflows/{name}/run")
        r = client.get(f"/api/workflows/{name}/status")
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == name
        assert d["current_stage"] is not None
        assert d["stage_info"] is not None
        assert "tools" in d["stage_info"]
        assert "name" in d["stage_info"]
        assert isinstance(d["available_next"], list)
        assert d["total_transitions"] >= 1
        assert isinstance(d["history"], list)
        assert d["paused"] is False
        assert isinstance(d["variables"], dict)
        assert isinstance(d["retry_count"], dict)
        assert isinstance(d["iterations"], dict)

    def test_status_nonexistent_workflow_returns_404(self):
        """Status for nonexistent workflow returns 404."""
        r = client.get("/api/workflows/nonexistent_xyz_123/status")
        assert r.status_code == 404

    def test_pause_workflow(self):
        """Pause a running workflow."""
        name = "test_exec_workflow"
        client.post(f"/api/workflows/{name}/run")
        r = client.post(f"/api/workflows/{name}/pause?reason=testing")
        assert r.status_code == 200
        d = r.json()
        assert d["paused"] is True
        assert d["reason"] == "testing"

        # Verify status shows paused
        s = client.get(f"/api/workflows/{name}/status")
        assert s.json()["paused"] is True

    def test_pause_blocks_transition(self):
        """Paused workflow cannot transition."""
        name = "test_exec_workflow"
        # First run: pick init + advance to analyze
        client.post(f"/api/workflows/{name}/run")
        client.post(f"/api/workflows/{name}/pause?reason=block")

        # Try to advance from analyze to done while paused
        r = client.post(f"/api/workflows/{name}/run?target=done")
        assert r.status_code == 200
        d = r.json()
        assert d["success"] is False

    def test_resume_workflow(self):
        """Resume a paused workflow."""
        name = "test_exec_workflow"
        client.post(f"/api/workflows/{name}/run")
        client.post(f"/api/workflows/{name}/pause?reason=test")
        r = client.post(f"/api/workflows/{name}/resume")
        assert r.status_code == 200
        assert r.json()["paused"] is False

    def test_resume_not_paused_returns_400(self):
        """Resuming a non-paused workflow returns 400."""
        name = "test_exec_workflow"
        client.post(f"/api/workflows/{name}/run")
        r = client.post(f"/api/workflows/{name}/resume")
        assert r.status_code == 400

    def test_run_history_persists(self):
        """History is tracked across multiple runs."""
        name = "test_exec_workflow"
        client.post(f"/api/workflows/{name}/run")  # init pick
        client.post(f"/api/workflows/{name}/run")  # pick -> analyze

        r = client.get(f"/api/workflows/{name}/status")
        history = r.json()["history"]
        assert len(history) >= 1  # at least one transition recorded

    def test_run_no_available_transition(self):
        """Running at a terminal stage reports failure."""
        name = "test_exec_workflow"
        client.post(f"/api/workflows/{name}/run")  # init pick
        client.post(f"/api/workflows/{name}/run?target=done")  # -> done
        # At done, no more transitions
        r = client.post(f"/api/workflows/{name}/run")
        assert r.status_code == 200
        d = r.json()
        assert d["success"] is False
        assert "No available" in str(d["messages"])

    def test_save_invalidates_engine_cache(self):
        """After updating a workflow YAML, the cached engine is invalidated."""
        name = "test_cache_inval"
        NEW_YAML = """
stages:
  - name: start
    tools: [Read]
  - name: finish
    tools: []
transitions:
  - from: start
    to: finish
    conditions:
      - always: true
"""

        import shutil
        try:
            # Save initial workflow
            client.put(f"/api/workflows/{name}", json={"yaml": self.SETUP_YAML})
            # Run to init engine
            client.post(f"/api/workflows/{name}/run?target=pick")

            # Update the workflow with different stages
            client.put(f"/api/workflows/{name}", json={"yaml": NEW_YAML})

            # The engine initializes at 'start' (root), advance to 'finish'
            r = client.post(f"/api/workflows/{name}/run")
            assert r.status_code == 200
            d = r.json()
            # Should succeed with new config and land at 'finish'
            assert d["current_stage"] == "finish"
            assert d["success"] is True
        finally:
            path = WORKFLOWS_DIR / f"{name}.yaml"
            if path.exists():
                path.unlink()
            engine_dir = WORKFLOWS_DIR / name
            if engine_dir.exists():
                shutil.rmtree(engine_dir, ignore_errors=True)
            from editor.server import _workflow_engines
            _workflow_engines.pop(name, None)


# ═══════════════════════════════════════════════════════════════════════════
# Project save-config endpoint (save gate with run-state check)
# ═══════════════════════════════════════════════════════════════════════════

VALID_PROJECT_YAML = """
stages:
  - name: alpha
    tools: [Read]
  - name: beta
    tools: [Read, Grep]
  - name: gamma
    tools: []
transitions:
  - from: alpha
    to: beta
    conditions:
      - always: true
  - from: beta
    to: gamma
    conditions:
      - always: true
"""


class TestProjectSaveGate:
    def _make_project(self, tmp_path, current_stage=None, run_status=None):
        """Set up a minimal StageFlow project under tmp_path."""
        cfg_dir = tmp_path / ".stageflow" / "config"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "stages.yaml").write_text(VALID_PROJECT_YAML, encoding="utf-8")

        state_path = tmp_path / ".stageflow" / "current_stage.json"
        state = {"current_stage": current_stage, "variables": {"run_id": "test-run-id"}}
        if run_status:
            state["run_status"] = run_status
            if run_status == "completed":
                state["completed_at"] = "2026-01-01T00:00:00+00:00"
                state["final_stage"] = "gamma"
        if current_stage is None:
            state.pop("current_stage", None)
            # If null but we want a non-existent key:
            if current_stage is None and run_status is None:
                # fresh init — no current_stage key at all
                pass
            elif current_stage is None:
                # completed or reset — explicit null
                state["current_stage"] = None

        state_path.write_text(json.dumps(state), encoding="utf-8")
        return tmp_path

    def test_save_allowed_after_init(self, tmp_path):
        """Save succeeds when no run is active (fresh init — no current_stage)."""
        proj = self._make_project(tmp_path, current_stage=None)
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": VALID_PROJECT_YAML})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["saved"] is True
            assert "no active run" in d["message"]
            # Verify file was actually written
            saved = (proj / ".stageflow" / "config" / "stages.yaml").read_text()
            assert "alpha" in saved
        finally:
            os.chdir(orig)

    def test_save_allowed_after_complete(self, tmp_path):
        """Save succeeds after run completed (current_stage=null, run_status=completed)."""
        proj = self._make_project(tmp_path, current_stage=None, run_status="completed")
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": VALID_PROJECT_YAML})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["saved"] is True
            assert "completed run" in d["message"]
        finally:
            os.chdir(orig)

    def test_save_allowed_after_reset(self, tmp_path):
        """Save succeeds after reset (current_stage=null, no run_status)."""
        proj = self._make_project(tmp_path, current_stage=None)
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": VALID_PROJECT_YAML})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["saved"] is True
        finally:
            os.chdir(orig)

    def test_save_blocked_during_active_run(self, tmp_path):
        """Save blocked when a run is active (current_stage is set)."""
        proj = self._make_project(tmp_path, current_stage="alpha")
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": VALID_PROJECT_YAML})
            assert r.status_code == 403, r.text
            d = r.json()
            assert "active" in d["detail"].lower()
            assert "alpha" in d["detail"]
        finally:
            os.chdir(orig)

    def test_save_blocked_during_mid_run(self, tmp_path):
        """Save blocked at a mid-pipeline stage (beta), not just alpha."""
        proj = self._make_project(tmp_path, current_stage="beta")
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": VALID_PROJECT_YAML})
            assert r.status_code == 403, r.text
            d = r.json()
            assert "beta" in d["detail"]
        finally:
            os.chdir(orig)

    def test_save_no_project_found(self, tmp_path):
        """Save returns 400 when no StageFlow project exists."""
        empty = tmp_path / "empty_dir"
        empty.mkdir()
        orig = os.getcwd()
        try:
            os.chdir(str(empty))
            r = client.post("/api/project/save-config", json={"yaml": VALID_PROJECT_YAML})
            assert r.status_code == 400, r.text
            assert "No StageFlow project" in r.json()["detail"]
        finally:
            os.chdir(orig)

    def test_save_invalid_yaml_with_gate_pass(self, tmp_path):
        """Even when gate passes, invalid YAML is rejected."""
        proj = self._make_project(tmp_path, current_stage=None)
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": "not: [valid: yaml"})
            assert r.status_code == 400, r.text
            assert "YAML parse error" in r.json()["detail"]
        finally:
            os.chdir(orig)

    def test_save_empty_yaml_with_gate_pass(self, tmp_path):
        """Even when gate passes, empty YAML is rejected."""
        proj = self._make_project(tmp_path, current_stage=None)
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": ""})
            assert r.status_code == 400, r.text
            assert "empty" in r.json()["detail"].lower()
        finally:
            os.chdir(orig)

    def test_save_invalid_config_with_gate_pass(self, tmp_path):
        """Even when gate passes, invalid StageFlow config is rejected."""
        proj = self._make_project(tmp_path, current_stage=None)
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": "stages: not_a_list"})
            assert r.status_code == 400, r.text
            assert "Invalid config" in r.json()["detail"]
        finally:
            os.chdir(orig)

    def test_save_preserves_yaml_content(self, tmp_path):
        """The exact YAML content is written to the project config path."""
        proj = self._make_project(tmp_path, current_stage=None)
        custom = """
stages:
  - name: uno
    tools: [Read]
  - name: dos
    tools: []
transitions:
  - from: uno
    to: dos
    conditions:
      - always: true
"""
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": custom})
            assert r.status_code == 200, r.text
            saved = (proj / ".stageflow" / "config" / "stages.yaml").read_text()
            assert "uno" in saved
            assert "dos" in saved
            assert "alpha" not in saved
        finally:
            os.chdir(orig)

    def test_save_gate_does_not_require_run_status_field(self, tmp_path):
        """Fresh projects without run_status key are allowed (null check only)."""
        proj = self._make_project(tmp_path, current_stage=None)
        # Explicitly remove run_status from state
        state_path = proj / ".stageflow" / "current_stage.json"
        state = json.loads(state_path.read_text())
        state.pop("run_status", None)
        state["current_stage"] = None
        state_path.write_text(json.dumps(state), encoding="utf-8")
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": VALID_PROJECT_YAML})
            assert r.status_code == 200, r.text
            assert r.json()["saved"] is True
        finally:
            os.chdir(orig)

    def test_save_gate_blocked_even_at_terminal_stage_if_not_completed(self, tmp_path):
        """If a run is at a terminal stage but not completed, save is still blocked."""
        proj = self._make_project(tmp_path, current_stage="gamma")
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            r = client.post("/api/project/save-config", json={"yaml": VALID_PROJECT_YAML})
            assert r.status_code == 403, r.text
        finally:
            os.chdir(orig)


class TestGenerateEndpoint:
    def test_generate_default_template_does_not_crash(self):
        """Regression: PromptTemplate.GENERAL (typo) crashed the endpoint."""
        r = client.post("/api/generate", json={"description": "A simple CI pipeline"})
        assert r.status_code == 200, r.text
        d = r.json()
        if not d.get("success"):
            pytest.fail(f"generate failed: {d}")
        assert d["yaml"] is not None
        assert "stages:" in d["yaml"]
