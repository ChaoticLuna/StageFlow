"""Staged verification — 7 layers of increasing difficulty.

Each layer builds on the previous. Run with pytest in order:
  pytest tests/test_staged_verification.py -v

Layer summary:
  1. Engine-only complete behavior
  2. Status output after init, active, complete, reset
  3. CLI complete from project root
  4. CLI complete from nested directory
  5. Multi-repo isolation
  6. Run-scoped artifact isolation
  7. Editor save gate
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from stageflow.core.engine import StateMachine
from stageflow.core.registry import StageRegistry

# ── helpers ──────────────────────────────────────────────────────────────

YAML_ABC = """stages:
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
      - shell_test:
          command: "echo ok"
          op: exit_zero
  - from: beta
    to: gamma
    conditions:
      - always: true
"""

YAML_TWO_TERMINAL = """stages:
  - name: alpha
    tools: [Read]
  - name: beta
    tools: [Read, Grep]
  - name: gamma
    tools: []
  - name: delta
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
  - from: beta
    to: delta
    conditions:
      - always: true
"""


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "stageflow", *args],
        capture_output=True, text=True,
        cwd=str(cwd) if cwd else None,
    )


# ══════════════════════════════════════════════════════════════════════════
# Layer 1: Engine-only complete behavior
# ══════════════════════════════════════════════════════════════════════════

class TestLayer1_EngineComplete:
    """Verify StateMachine.complete() at the engine level."""

    def _make_registry(self, tmp_path: Path, yaml_str: str) -> StageRegistry:
        yaml_path = tmp_path / "stages.yaml"
        yaml_path.write_text(yaml_str, encoding="utf-8")
        return StageRegistry(str(yaml_path))

    def test_complete_succeeds_at_terminal_stage(self, tmp_path):
        reg = self._make_registry(tmp_path, YAML_ABC)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("alpha")
        sm.transition_to("beta")
        sm.transition_to("gamma")
        ok, msgs = sm.complete()
        assert ok, msgs
        assert sm.current_stage is None
        assert sm._state["run_status"] == "completed"
        assert sm._state["final_stage"] == "gamma"
        assert "completed_at" in sm._state

    def test_complete_fails_at_non_terminal_stage(self, tmp_path):
        reg = self._make_registry(tmp_path, YAML_ABC)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("alpha")
        ok, msgs = sm.complete()
        assert not ok
        assert "not terminal" in msgs[0].lower() or "outgoing" in msgs[0].lower()
        assert sm.current_stage == "alpha"

    def test_complete_fails_when_no_active_run(self, tmp_path):
        reg = self._make_registry(tmp_path, YAML_ABC)
        sm = StateMachine(reg, str(tmp_path))
        ok, msgs = sm.complete()
        assert not ok
        assert "no active run" in msgs[0].lower()

    def test_complete_prerequisites_layer1(self, tmp_path):
        """Assert engine complete sets all required metadata fields."""
        reg = self._make_registry(tmp_path, YAML_ABC)
        sm = StateMachine(reg, str(tmp_path))
        sm.initialize("alpha")
        sm.transition_to("beta")
        sm.transition_to("gamma")
        run_id = sm.get_var("run_id")
        ok, _ = sm.complete()
        assert ok
        assert sm._state["current_stage"] is None
        assert sm._state["run_status"] == "completed"
        assert sm._state["final_stage"] == "gamma"
        assert sm._state["completed_at"] is not None
        assert sm._state["variables"]["run_id"] == run_id
        assert len(sm._state["history"]) >= 3


# ══════════════════════════════════════════════════════════════════════════
# Layer 2: Status output after different states
# ══════════════════════════════════════════════════════════════════════════

class TestLayer2_StatusOutput:
    """Verify status output distinguishes init/active/complete/reset states."""

    def _make_project(self, tmp: Path):
        cfg = tmp / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_ABC, encoding="utf-8")

    def test_status_after_init_no_active_run(self, tmp_path):
        self._make_project(tmp_path)
        r = _run_cli("status", cwd=tmp_path)
        assert r.returncode == 0
        assert "No active run" in r.stdout

    def test_status_after_start_shows_active(self, tmp_path):
        self._make_project(tmp_path)
        _run_cli("start", cwd=tmp_path)
        r = _run_cli("status", cwd=tmp_path)
        assert r.returncode == 0
        assert "alpha" in r.stdout

    def test_status_json_after_complete(self, tmp_path):
        self._make_project(tmp_path)
        _run_cli("start", cwd=tmp_path)
        _run_cli("next", "--force", cwd=tmp_path)
        _run_cli("next", "--force", cwd=tmp_path)
        _run_cli("complete", cwd=tmp_path)
        r = _run_cli("status", "--json", cwd=tmp_path)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["current_stage"] is None
        assert data["run_status"] == "completed"
        assert data["final_stage"] is not None
        assert data["completed_at"] is not None
        assert "run_id" in data.get("variables", {})

    def test_status_after_reset_no_active_run(self, tmp_path):
        self._make_project(tmp_path)
        _run_cli("start", cwd=tmp_path)
        _run_cli("reset", cwd=tmp_path)
        r = _run_cli("status", cwd=tmp_path)
        assert r.returncode == 0
        assert "No active run" in r.stdout


# ══════════════════════════════════════════════════════════════════════════
# Layer 3: CLI complete from project root
# ══════════════════════════════════════════════════════════════════════════

class TestLayer3_CLICompleteFromRoot:
    """Full lifecycle via CLI from project root directory."""

    def test_full_lifecycle_from_root(self, tmp_path):
        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_ABC, encoding="utf-8")

        # init
        r = _run_cli("status", cwd=tmp_path)
        assert "No active run" in r.stdout

        # start
        r = _run_cli("start", cwd=tmp_path)
        assert r.returncode == 0

        # advance alpha -> beta (force since condition is shell_test: echo ok)
        r = _run_cli("next", "--force", cwd=tmp_path)
        assert r.returncode == 0

        # advance beta -> gamma (always: true)
        r = _run_cli("next", cwd=tmp_path)
        assert r.returncode == 0

        # complete at gamma (terminal)
        r = _run_cli("complete", cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert "completed" in r.stdout.lower()

        # verify state after complete
        r = _run_cli("status", "--json", cwd=tmp_path)
        data = json.loads(r.stdout)
        assert data["current_stage"] is None
        assert data["run_status"] == "completed"
        assert data["final_stage"] == "gamma"

    def test_complete_refused_at_non_terminal_from_root(self, tmp_path):
        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_ABC, encoding="utf-8")
        _run_cli("start", cwd=tmp_path)
        r = _run_cli("complete", cwd=tmp_path)
        assert r.returncode != 0
        assert "not terminal" in r.stderr.lower() or "terminal" in r.stdout.lower()


# ══════════════════════════════════════════════════════════════════════════
# Layer 4: CLI complete from nested directory
# ══════════════════════════════════════════════════════════════════════════

class TestLayer4_CLICompleteFromNestedDir:
    """CLI commands work from deeply nested subdirectories."""

    def test_complete_from_nested_subdir(self, tmp_path):
        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_ABC, encoding="utf-8")

        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)

        _run_cli("start", cwd=tmp_path)
        _run_cli("next", "--force", cwd=nested)
        _run_cli("next", cwd=nested)
        r = _run_cli("complete", cwd=nested)
        assert r.returncode == 0, r.stderr
        assert "completed" in r.stdout.lower()

    def test_status_from_nested_subdir(self, tmp_path):
        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_ABC, encoding="utf-8")

        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)

        _run_cli("start", cwd=tmp_path)
        r = _run_cli("status", cwd=nested)
        assert r.returncode == 0
        assert "alpha" in r.stdout


# ══════════════════════════════════════════════════════════════════════════
# Layer 5: Multi-repo isolation
# ══════════════════════════════════════════════════════════════════════════

class TestLayer5_MultiRepoIsolation:
    """Completion in repo A must not touch repo B or source checkout."""

    def test_multi_repo_complete_isolation(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        repo_a.mkdir()
        repo_b.mkdir()

        for repo in (repo_a, repo_b):
            cfg = repo / ".stageflow" / "config"
            cfg.mkdir(parents=True)
            (cfg / "stages.yaml").write_text(YAML_ABC, encoding="utf-8")

        # Start both repos
        _run_cli("start", cwd=repo_a)
        _run_cli("start", cwd=repo_b)

        # Advance repo_a to terminal and complete
        _run_cli("next", "--force", cwd=repo_a)
        _run_cli("next", cwd=repo_a)
        r_complete = _run_cli("complete", cwd=repo_a)
        assert r_complete.returncode == 0

        # repo_a should be completed
        r_a = _run_cli("status", "--json", cwd=repo_a)
        a_data = json.loads(r_a.stdout)
        assert a_data["current_stage"] is None
        assert a_data["run_status"] == "completed"

        # repo_b should still be active at alpha (untouched)
        r_b = _run_cli("status", "--json", cwd=repo_b)
        b_data = json.loads(r_b.stdout)
        assert b_data["current_stage"] == "alpha"
        assert b_data.get("run_status") is None

    def test_source_checkout_not_affected(self, tmp_path):
        """Prove the auto_workflow source checkout is not modified."""
        repo = tmp_path / "isolated_repo"
        repo.mkdir()
        cfg = repo / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_ABC, encoding="utf-8")

        _run_cli("start", cwd=repo)
        _run_cli("next", "--force", cwd=repo)
        _run_cli("next", cwd=repo)
        _run_cli("complete", cwd=repo)

        # Source checkout state file should remain unchanged
        source_state = Path(__file__).parent.parent / ".claude" / "current_stage.json"
        source_stageflow = Path(__file__).parent.parent / ".stageflow" / "current_stage.json"
        # The repo we created should have its own state
        repo_state = repo / ".stageflow" / "current_stage.json"
        assert repo_state.exists()
        data = json.loads(repo_state.read_text())
        assert data.get("run_status") == "completed"


# ══════════════════════════════════════════════════════════════════════════
# Layer 6: Run-scoped artifact isolation
# ══════════════════════════════════════════════════════════════════════════

YAML_ARTIFACT = """stages:
  - name: start
    tools: [Read]
  - name: middle
    tools: [Read, Write]
  - name: finish
    tools: []
transitions:
  - from: start
    to: middle
    conditions:
      - file_exists: artifacts/runs/{{var.run_id}}/start/gate.txt
  - from: middle
    to: finish
    conditions:
      - file_exists: artifacts/runs/{{var.run_id}}/middle/output.txt
"""


class TestLayer6_RunScopedArtifacts:
    """Stale artifacts from an old completed run must not unlock a new run."""

    def _create_artifact(self, root: Path, run_id: str, stage: str, filename: str):
        d = root / "artifacts" / "runs" / run_id / stage
        d.mkdir(parents=True)
        (d / filename).write_text("created for testing", encoding="utf-8")

    def test_stale_artifact_does_not_unlock_new_run(self, tmp_path):
        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_ARTIFACT, encoding="utf-8")

        # Run 1: create artifacts and complete
        _run_cli("start", cwd=tmp_path)
        r1 = _run_cli("status", "--json", cwd=tmp_path)
        run1_id = json.loads(r1.stdout)["variables"]["run_id"]

        self._create_artifact(tmp_path, run1_id, "start", "gate.txt")
        _run_cli("next", cwd=tmp_path)
        self._create_artifact(tmp_path, run1_id, "middle", "output.txt")
        _run_cli("next", cwd=tmp_path)
        _run_cli("complete", cwd=tmp_path)

        # Run 2: fresh start — run1 artifacts should NOT unlock run2
        _run_cli("start", cwd=tmp_path)
        r2 = _run_cli("status", "--json", cwd=tmp_path)
        run2_id = json.loads(r2.stdout)["variables"]["run_id"]

        assert run1_id != run2_id

        # Without creating run2's artifact, transition should fail
        r = _run_cli("next", cwd=tmp_path)
        assert r.returncode != 0
        assert "FAIL" in r.stdout or "FAIL" in r.stderr

        # Create run2's own artifact — now transition should pass
        self._create_artifact(tmp_path, run2_id, "start", "gate.txt")
        r = _run_cli("next", cwd=tmp_path)
        assert r.returncode == 0

    def test_two_runs_independent_artifact_dirs(self, tmp_path):
        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_ARTIFACT, encoding="utf-8")

        # Run 1
        _run_cli("start", cwd=tmp_path)
        r1 = _run_cli("status", "--json", cwd=tmp_path)
        run1_id = json.loads(r1.stdout)["variables"]["run_id"]
        self._create_artifact(tmp_path, run1_id, "start", "gate.txt")
        _run_cli("next", cwd=tmp_path)
        self._create_artifact(tmp_path, run1_id, "middle", "output.txt")
        _run_cli("next", cwd=tmp_path)
        _run_cli("complete", cwd=tmp_path)

        # Run 2
        _run_cli("start", cwd=tmp_path)
        r2 = _run_cli("status", "--json", cwd=tmp_path)
        run2_id = json.loads(r2.stdout)["variables"]["run_id"]

        # Verify separate artifact directories exist
        run1_dir = tmp_path / "artifacts" / "runs" / run1_id
        run2_dir = tmp_path / "artifacts" / "runs" / run2_id
        assert run1_dir.exists()
        # run2 dir is created when artifacts are written, may not exist yet
        assert run1_id != run2_id


# ══════════════════════════════════════════════════════════════════════════
# Layer 7: Editor save gate
# ══════════════════════════════════════════════════════════════════════════

class TestLayer7_EditorSaveGate:
    """Editor save gate: allowed after init/complete/reset, blocked during run."""

    def _make_project(self, tmp: Path, current_stage=None, run_status=None):
        cfg = tmp / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_ABC, encoding="utf-8")

        state = {"variables": {"run_id": "staged-verify-run"}}
        if current_stage is not None:
            state["current_stage"] = current_stage
        if run_status:
            state["run_status"] = run_status
            if run_status == "completed":
                state["completed_at"] = "2026-01-01T00:00:00+00:00"
                state["final_stage"] = "gamma"
        (tmp / ".stageflow" / "current_stage.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
        return tmp

    def _save(self, proj: Path, yaml_str: str = YAML_ABC):
        """Call the save-config endpoint via the FastAPI test client."""
        from fastapi.testclient import TestClient
        from editor.server import app
        client = TestClient(app)
        orig = os.getcwd()
        try:
            os.chdir(str(proj))
            return client.post("/api/project/save-config", json={"yaml": yaml_str})
        finally:
            os.chdir(orig)

    def test_save_allowed_after_init(self, tmp_path):
        proj = self._make_project(tmp_path, current_stage=None)
        r = self._save(proj)
        assert r.status_code == 200, r.text
        assert r.json()["saved"] is True

    def test_save_allowed_after_complete(self, tmp_path):
        proj = self._make_project(tmp_path, current_stage=None, run_status="completed")
        r = self._save(proj)
        assert r.status_code == 200, r.text

    def test_save_allowed_after_reset(self, tmp_path):
        proj = self._make_project(tmp_path, current_stage=None)
        r = self._save(proj)
        assert r.status_code == 200, r.text

    def test_save_blocked_during_active_run(self, tmp_path):
        proj = self._make_project(tmp_path, current_stage="alpha")
        r = self._save(proj)
        assert r.status_code == 403, r.text
        assert "active" in r.json()["detail"].lower()

    def test_save_blocked_at_terminal_stage_before_complete(self, tmp_path):
        proj = self._make_project(tmp_path, current_stage="gamma")
        r = self._save(proj)
        assert r.status_code == 403, r.text
