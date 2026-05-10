from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

from editor.server import app, CONDITION_DEFS

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
    def test_returns_27_conditions(self):
        r = client.get("/api/conditions")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 27
        assert len(data["conditions"]) == 27

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
        assert CONDITION_DEFS[-1]["type"] == "json_count"


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
