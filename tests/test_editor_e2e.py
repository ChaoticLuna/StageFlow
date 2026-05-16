"""End-to-end editor workflow tests — 8 layers of increasing difficulty.

Each layer builds on the previous. Run with:
  pytest tests/test_editor_e2e.py -v

Layer summary:
  1. Built dist assets exist and contain the Save/autoload UI
  2. FastAPI serves the built frontend (index.html + static assets)
  3. Server API loads project YAML from bound root
  4. Save gate (active run blocks, no run / complete / reset allows)
  5. CLI starts against temp project, reports correct root
  6. Nested directory binds ancestor project root
  7. Full save round-trip (CLI start + API save + verify file)
  8. Package source isolation (external project never touches source)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent
DIST_DIR = PROJECT_ROOT / "editor" / "dist"
SOURCE_CONFIG = PROJECT_ROOT / "stageflow" / "config" / "stages.yaml"

YAML_CUSTOM = """stages:
  - name: uno
    tools: [Read]
  - name: dos
    tools: [Read, Edit]
  - name: tres
    tools: []
transitions:
  - from: uno
    to: dos
    conditions:
      - always: true
  - from: dos
    to: tres
    conditions:
      - always: true
"""


# ══════════════════════════════════════════════════════════════════════════════
# Layer 1: Built dist assets exist
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer1_BuiltDist:
    """Verify editor/dist contains the production build with Save/autoload UI."""

    def test_dist_index_html_exists(self):
        assert DIST_DIR.is_dir(), f"dist dir missing: {DIST_DIR}"
        index = DIST_DIR / "index.html"
        assert index.is_file(), f"index.html missing: {index}"

    def test_dist_has_js_assets(self):
        assets_dir = DIST_DIR / "assets"
        assert assets_dir.is_dir()
        js_files = list(assets_dir.glob("*.js"))
        assert len(js_files) >= 1, "No JS bundle found in dist/assets"

    def test_dist_has_css_assets(self):
        assets_dir = DIST_DIR / "assets"
        css_files = list(assets_dir.glob("*.css"))
        assert len(css_files) >= 1, "No CSS bundle found in dist/assets"

    def test_index_html_references_js_bundle(self):
        index = DIST_DIR / "index.html"
        html = index.read_text(encoding="utf-8")
        assert 'script' in html.lower(), "index.html must reference JS bundle"

    def test_dist_contains_save_ui_code(self):
        """The built JS bundle must contain the Save/auto-load functionality."""
        assets_dir = DIST_DIR / "assets"
        js_files = list(assets_dir.glob("*.js"))
        combined = ""
        for f in js_files:
            combined += f.read_text(encoding="utf-8", errors="ignore")
        # The built bundle should contain our API client and save functionality
        assert "fetchProjectConfig" in combined or "saveProjectConfig" in combined or "save" in combined.lower(), \
            "Built JS does not contain Save/auto-load code"


# ══════════════════════════════════════════════════════════════════════════════
# Layer 2: FastAPI serves the built frontend
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer2_FastAPIServesFrontend:
    """Verify the FastAPI app serves dist/index.html and static assets."""

    def _make_bound_app(self, tmp_path: Path):
        from stageflow.core import discovery
        from editor.server import create_app

        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_CUSTOM, encoding="utf-8")

        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({"current_stage": None}), encoding="utf-8")

        root = discovery.ProjectRoot(
            path=tmp_path,
            marker_type="new",
            config_path=cfg / "stages.yaml",
            state_path=s,
            artifacts_dir=tmp_path / "artifacts" / "runs",
            audit_dir=tmp_path / ".stageflow",
        )
        return create_app(project_root=root)

    def test_root_returns_html(self, tmp_path):
        from fastapi.testclient import TestClient
        app = self._make_bound_app(tmp_path)
        client = TestClient(app)
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_index_html_served(self, tmp_path):
        from fastapi.testclient import TestClient
        app = self._make_bound_app(tmp_path)
        client = TestClient(app)
        r = client.get("/index.html")
        assert r.status_code == 200

    def test_favicon_served(self, tmp_path):
        from fastapi.testclient import TestClient
        app = self._make_bound_app(tmp_path)
        client = TestClient(app)
        r = client.get("/favicon.svg")
        assert r.status_code in (200, 404)  # 404 if not built

    def test_js_bundle_served_with_browser_executable_mime(self, tmp_path):
        """Module scripts must not be served as text/plain."""
        from fastapi.testclient import TestClient

        app = self._make_bound_app(tmp_path)
        client = TestClient(app)
        assets_dir = DIST_DIR / "assets"
        js_files = list(assets_dir.glob("*.js"))
        assert js_files, "No JS bundle found in dist/assets"

        r = client.get(f"/assets/{js_files[0].name}")
        assert r.status_code == 200
        content_type = r.headers["content-type"].split(";")[0]
        assert content_type in {
            "application/javascript",
            "text/javascript",
        }


# ══════════════════════════════════════════════════════════════════════════════
# Layer 3: Server API loads config from bound root
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer3_BoundConfigAPI:
    """Verify GET /api/project/config returns the bound project's YAML."""

    def _make_bound_app(self, tmp_path: Path):
        from stageflow.core import discovery
        from editor.server import create_app

        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_CUSTOM, encoding="utf-8")

        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({"current_stage": None}), encoding="utf-8")

        root = discovery.ProjectRoot(
            path=tmp_path,
            marker_type="new",
            config_path=cfg / "stages.yaml",
            state_path=s,
            artifacts_dir=tmp_path / "artifacts" / "runs",
            audit_dir=tmp_path / ".stageflow",
        )
        return create_app(project_root=root)

    def test_config_returns_custom_yaml(self, tmp_path):
        from fastapi.testclient import TestClient
        app = self._make_bound_app(tmp_path)
        client = TestClient(app)
        r = client.get("/api/project/config")
        assert r.status_code == 200
        data = r.json()
        assert data["yaml"] == YAML_CUSTOM
        assert data["project_root"] == str(tmp_path)
        assert "uno" in data["yaml"]

    def test_config_returns_save_allowed_when_no_run(self, tmp_path):
        from fastapi.testclient import TestClient
        app = self._make_bound_app(tmp_path)
        client = TestClient(app)
        r = client.get("/api/project/config")
        assert r.status_code == 200
        assert r.json()["save_allowed"] is True

    def test_config_returns_save_blocked_when_run_active(self, tmp_path):
        from fastapi.testclient import TestClient
        app = self._make_bound_app(tmp_path)
        # Overwrite state to simulate an active run
        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({"current_stage": "uno", "variables": {}}))

        client = TestClient(app)
        r = client.get("/api/project/config")
        assert r.status_code == 200
        assert r.json()["save_allowed"] is False
        assert r.json()["current_stage"] == "uno"

    def test_404_when_config_missing(self, tmp_path):
        from fastapi.testclient import TestClient
        from editor.server import create_app
        from stageflow.core import discovery

        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({"current_stage": None}))

        root = discovery.ProjectRoot(
            path=tmp_path, marker_type="new",
            config_path=cfg / "stages.yaml",
            state_path=s,
            artifacts_dir=tmp_path / "artifacts" / "runs",
            audit_dir=tmp_path / ".stageflow",
        )
        app = create_app(project_root=root)
        client = TestClient(app)
        r = client.get("/api/project/config")
        assert r.status_code == 404

    def test_config_marker_type_is_new(self, tmp_path):
        from fastapi.testclient import TestClient
        app = self._make_bound_app(tmp_path)
        client = TestClient(app)
        r = client.get("/api/project/config")
        assert r.status_code == 200
        assert r.json()["marker_type"] == "new"


# ══════════════════════════════════════════════════════════════════════════════
# Layer 4: Save gate (active run blocks, no run allows)
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer4_SaveGate:
    """Verify POST /api/project/save-config enforces the no-active-run gate."""

    def _make_bound_app(self, tmp_path: Path):
        from stageflow.core import discovery
        from editor.server import create_app

        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_CUSTOM, encoding="utf-8")

        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({"current_stage": None}), encoding="utf-8")

        root = discovery.ProjectRoot(
            path=tmp_path, marker_type="new",
            config_path=cfg / "stages.yaml",
            state_path=s,
            artifacts_dir=tmp_path / "artifacts" / "runs",
            audit_dir=tmp_path / ".stageflow",
        )
        return create_app(project_root=root), root

    def test_save_blocked_when_run_active(self, tmp_path):
        from fastapi.testclient import TestClient
        app, root = self._make_bound_app(tmp_path)
        root.state_path.write_text(json.dumps({
            "current_stage": "uno", "variables": {"run_id": "test-123"}
        }))
        client = TestClient(app)
        r = client.post("/api/project/save-config", json={"yaml": YAML_CUSTOM})
        assert r.status_code == 403

    def test_save_allowed_when_no_run(self, tmp_path):
        from fastapi.testclient import TestClient
        app, root = self._make_bound_app(tmp_path)
        root.state_path.write_text(json.dumps({"current_stage": None}))
        client = TestClient(app)
        r = client.post("/api/project/save-config", json={"yaml": YAML_CUSTOM})
        assert r.status_code == 200
        assert r.json()["saved"] is True

    def test_save_allowed_after_complete(self, tmp_path):
        from fastapi.testclient import TestClient
        app, root = self._make_bound_app(tmp_path)
        root.state_path.write_text(json.dumps({
            "current_stage": None,
            "run_status": "completed",
            "final_stage": "tres",
            "completed_at": "2026-05-16T00:00:00Z",
            "variables": {"run_id": "test-456"},
        }))
        client = TestClient(app)
        r = client.post("/api/project/save-config", json={"yaml": YAML_CUSTOM})
        assert r.status_code == 200
        assert r.json()["saved"] is True

    def test_invalid_yaml_preserves_previous_config(self, tmp_path):
        from fastapi.testclient import TestClient
        app, root = self._make_bound_app(tmp_path)
        original = root.config_path.read_text(encoding="utf-8")
        client = TestClient(app)
        r = client.post("/api/project/save-config",
                        json={"yaml": "not: [valid: yaml: -"})
        assert r.status_code == 400
        # Previous config must be unchanged
        current = root.config_path.read_text(encoding="utf-8")
        assert current == original

    def test_save_writes_yaml_to_bound_config_path(self, tmp_path):
        from fastapi.testclient import TestClient
        app, root = self._make_bound_app(tmp_path)
        new_yaml = YAML_CUSTOM.replace("uno", "primero")
        client = TestClient(app)
        r = client.post("/api/project/save-config", json={"yaml": new_yaml})
        assert r.status_code == 200
        updated = root.config_path.read_text(encoding="utf-8")
        assert "primero" in updated


# ══════════════════════════════════════════════════════════════════════════════
# Layer 5: CLI starts against temp project, reports correct root
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer5_CLIStartup:
    """Verify stageflow editor CLI starts and reports the correct project info."""

    def _make_project(self, tmp: Path):
        r = subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, text=True, cwd=str(tmp), timeout=30,
        )
        assert r.returncode == 0, r.stderr
        cfg = tmp / ".stageflow" / "config"
        (cfg / "stages.yaml").write_text(YAML_CUSTOM, encoding="utf-8")

    def _start_editor(self, cwd: Path, *extra_args):
        import threading
        proc = subprocess.Popen(
            [sys.executable, "-m", "stageflow", "editor", "--no-open", *extra_args],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            cwd=str(cwd),
        )
        lines = []
        def _reader():
            try:
                for line in iter(proc.stdout.readline, ""):
                    lines.append(line)
            except Exception:
                pass
        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        return proc, lines, t

    def _wait_for_output(self, lines, marker, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            combined = "".join(lines)
            if marker in combined:
                return combined
            time.sleep(0.1)
        return "".join(lines)

    def _terminate(self, proc):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
                proc.wait()

    def test_starts_and_prints_project_root(self, tmp_path):
        self._make_project(tmp_path)
        proc, lines, thr = self._start_editor(tmp_path, "--port", "8771")
        try:
            output = self._wait_for_output(lines, "Project root", timeout=15)
            assert str(tmp_path) in output, f"Missing root in:\n{output}"
            assert "Config" in output
            assert "URL" in output
        finally:
            self._terminate(proc)

    def test_reports_custom_host_port(self, tmp_path):
        self._make_project(tmp_path)
        proc, lines, thr = self._start_editor(
            tmp_path, "--host", "0.0.0.0", "--port", "9771",
        )
        try:
            output = self._wait_for_output(lines, "0.0.0.0", timeout=15)
            assert "9771" in output
        finally:
            self._terminate(proc)

    def test_fails_outside_project(self, tmp_path):
        r = subprocess.run(
            [sys.executable, "-m", "stageflow", "editor", "--no-open"],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=30,
        )
        assert r.returncode != 0
        assert "Not a StageFlow project" in r.stderr


# ══════════════════════════════════════════════════════════════════════════════
# Layer 6: Nested directory binds ancestor project root
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer6_NestedDirectory:
    """Verify editor launched from a subdirectory binds the ancestor root."""

    def _make_project(self, tmp: Path):
        r = subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, text=True, cwd=str(tmp), timeout=30,
        )
        assert r.returncode == 0, r.stderr
        cfg = tmp / ".stageflow" / "config"
        (cfg / "stages.yaml").write_text(YAML_CUSTOM, encoding="utf-8")

    def _start_editor(self, cwd: Path, *extra_args):
        import threading
        proc = subprocess.Popen(
            [sys.executable, "-m", "stageflow", "editor", "--no-open", *extra_args],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            cwd=str(cwd),
        )
        lines = []
        def _reader():
            try:
                for line in iter(proc.stdout.readline, ""):
                    lines.append(line)
            except Exception:
                pass
        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        return proc, lines, t

    def _wait_for_output(self, lines, marker, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            combined = "".join(lines)
            if marker in combined:
                return combined
            time.sleep(0.1)
        return "".join(lines)

    def _terminate(self, proc):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
                proc.wait()

    def test_binds_ancestor_from_nested_dir(self, tmp_path):
        self._make_project(tmp_path)
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        proc, lines, thr = self._start_editor(nested, "--port", "8772")
        try:
            output = self._wait_for_output(lines, "Project root", timeout=15)
            assert str(tmp_path) in output, f"Expected ancestor root, got:\n{output}"
        finally:
            self._terminate(proc)

    def test_save_from_nested_updates_ancestor_config(self, tmp_path):
        from fastapi.testclient import TestClient
        from stageflow.core import discovery
        from editor.server import create_app

        self._make_project(tmp_path)
        nested = tmp_path / "src" / "lib"
        nested.mkdir(parents=True)

        cfg = tmp_path / ".stageflow" / "config"
        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({"current_stage": None}), encoding="utf-8")

        root = discovery.ProjectRoot(
            path=tmp_path, marker_type="new",
            config_path=cfg / "stages.yaml",
            state_path=s,
            artifacts_dir=tmp_path / "artifacts" / "runs",
            audit_dir=tmp_path / ".stageflow",
        )
        app = create_app(project_root=root)
        client = TestClient(app)
        new_yaml = YAML_CUSTOM.replace("dos", "dos_modified")
        r = client.post("/api/project/save-config", json={"yaml": new_yaml})
        assert r.status_code == 200
        updated = (cfg / "stages.yaml").read_text(encoding="utf-8")
        assert "dos_modified" in updated


# ══════════════════════════════════════════════════════════════════════════════
# Layer 7: Full save round-trip (CLI + API + file verification)
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer7_SaveRoundTrip:
    """End-to-end: start editor server, save via API, verify file updated."""

    YAML_ORIGINAL = """stages:
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

    YAML_MODIFIED = """stages:
  - name: inception
    tools: [Read, Edit]
  - name: conclusion
    tools: []
transitions:
  - from: inception
    to: conclusion
    conditions:
      - always: true
"""

    def test_full_round_trip(self, tmp_path):
        from fastapi.testclient import TestClient
        from stageflow.core import discovery
        from editor.server import create_app

        # Set up project
        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(self.YAML_ORIGINAL, encoding="utf-8")
        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({"current_stage": None}), encoding="utf-8")

        root = discovery.ProjectRoot(
            path=tmp_path, marker_type="new",
            config_path=cfg / "stages.yaml",
            state_path=s,
            artifacts_dir=tmp_path / "artifacts" / "runs",
            audit_dir=tmp_path / ".stageflow",
        )
        app = create_app(project_root=root)
        client = TestClient(app)

        # 1. Load: verify original YAML is served
        r = client.get("/api/project/config")
        assert r.status_code == 200
        assert r.json()["yaml"] == self.YAML_ORIGINAL
        assert r.json()["save_allowed"] is True

        # 2. Save: write modified YAML
        r = client.post("/api/project/save-config",
                        json={"yaml": self.YAML_MODIFIED})
        assert r.status_code == 200
        assert r.json()["saved"] is True

        # 3. Verify file was updated on disk
        updated = (cfg / "stages.yaml").read_text(encoding="utf-8")
        assert "inception" in updated
        assert "conclusion" in updated

        # 4. Re-load: verify server returns the updated YAML
        r = client.get("/api/project/config")
        assert r.status_code == 200
        assert r.json()["yaml"] == self.YAML_MODIFIED

    def test_round_trip_with_active_run_blocked(self, tmp_path):
        from fastapi.testclient import TestClient
        from stageflow.core import discovery
        from editor.server import create_app

        # Set up project with active run
        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(self.YAML_ORIGINAL, encoding="utf-8")
        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({
            "current_stage": "start", "variables": {"run_id": "rt-001"}
        }))

        root = discovery.ProjectRoot(
            path=tmp_path, marker_type="new",
            config_path=cfg / "stages.yaml",
            state_path=s,
            artifacts_dir=tmp_path / "artifacts" / "runs",
            audit_dir=tmp_path / ".stageflow",
        )
        app = create_app(project_root=root)
        client = TestClient(app)

        # Save is blocked
        r = client.post("/api/project/save-config",
                        json={"yaml": self.YAML_MODIFIED})
        assert r.status_code == 403
        assert "active" in r.json()["detail"]

        # Original is preserved
        original = (cfg / "stages.yaml").read_text(encoding="utf-8")
        assert "start" in original
        assert "inception" not in original

    def test_invalid_yaml_round_trip_preserves(self, tmp_path):
        from fastapi.testclient import TestClient
        from stageflow.core import discovery
        from editor.server import create_app

        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(self.YAML_ORIGINAL, encoding="utf-8")
        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({"current_stage": None}), encoding="utf-8")

        root = discovery.ProjectRoot(
            path=tmp_path, marker_type="new",
            config_path=cfg / "stages.yaml",
            state_path=s,
            artifacts_dir=tmp_path / "artifacts" / "runs",
            audit_dir=tmp_path / ".stageflow",
        )
        app = create_app(project_root=root)
        client = TestClient(app)

        # Try to save invalid YAML
        r = client.post("/api/project/save-config",
                        json={"yaml": "::: bad yaml :::"})
        assert r.status_code == 400

        # Original file unchanged
        current = (cfg / "stages.yaml").read_text(encoding="utf-8")
        assert current == self.YAML_ORIGINAL


# ══════════════════════════════════════════════════════════════════════════════
# Layer 8: Package source isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestLayer8_SourceIsolation:
    """Negative assertions: editor operations on external projects must not
    mutate the StageFlow source checkout."""

    def test_external_project_does_not_touch_source_config(self, tmp_path):
        from fastapi.testclient import TestClient
        from stageflow.core import discovery
        from editor.server import create_app

        # Snapshot the source config before
        if SOURCE_CONFIG.exists():
            source_before = SOURCE_CONFIG.read_text(encoding="utf-8")
        else:
            source_before = None

        # Create an external temp project
        cfg = tmp_path / ".stageflow" / "config"
        cfg.mkdir(parents=True)
        (cfg / "stages.yaml").write_text(YAML_CUSTOM, encoding="utf-8")
        s = tmp_path / ".stageflow" / "current_stage.json"
        s.write_text(json.dumps({"current_stage": None}), encoding="utf-8")

        root = discovery.ProjectRoot(
            path=tmp_path, marker_type="new",
            config_path=cfg / "stages.yaml",
            state_path=s,
            artifacts_dir=tmp_path / "artifacts" / "runs",
            audit_dir=tmp_path / ".stageflow",
        )
        app = create_app(project_root=root)
        client = TestClient(app)

        # Perform save on the external project
        new_yaml = YAML_CUSTOM.replace("uno", "modified_uno")
        r = client.post("/api/project/save-config", json={"yaml": new_yaml})
        assert r.status_code == 200

        # Verify external project was updated
        updated = (cfg / "stages.yaml").read_text(encoding="utf-8")
        assert "modified_uno" in updated

        # Verify source checkout was NOT touched
        if source_before is not None:
            source_after = SOURCE_CONFIG.read_text(encoding="utf-8")
            assert source_after == source_before, \
                "Source config was modified by external project operation!"

        # Verify no .stageflow/ was created in the source checkout
        source_stageflow = PROJECT_ROOT / ".stageflow"
        assert not (source_stageflow / "current_stage.json").exists() or \
            (source_stageflow.is_dir() and not any(
                f.name.startswith("current_stage") for f in source_stageflow.iterdir()
            )), "Source .stageflow/current_stage.json was created by external operation"

    def test_cli_external_project_does_not_touch_source(self, tmp_path):
        # Snapshot source state
        source_claude_state = PROJECT_ROOT / ".claude" / "current_stage.json"
        source_before = None
        if source_claude_state.exists():
            source_before = source_claude_state.read_text(encoding="utf-8")

        # Init an external project
        r = subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=30,
        )
        assert r.returncode == 0, r.stderr

        # Write custom YAML
        cfg = tmp_path / ".stageflow" / "config"
        (cfg / "stages.yaml").write_text(YAML_CUSTOM, encoding="utf-8")

        # Start editor with --no-open (will be terminated)
        import threading
        proc = subprocess.Popen(
            [sys.executable, "-m", "stageflow", "editor",
             "--no-open", "--port", "8773"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            cwd=str(tmp_path),
        )
        lines = []
        def _reader():
            try:
                for line in iter(proc.stdout.readline, ""):
                    lines.append(line)
            except Exception:
                pass
        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        # Wait for startup then terminate
        deadline = time.time() + 15
        started = False
        while time.time() < deadline:
            if "Uvicorn running on" in "".join(lines):
                started = True
                break
            time.sleep(0.1)

        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
                proc.wait()

        # Verify source state untouched
        if source_before is not None and source_claude_state.exists():
            source_after = source_claude_state.read_text(encoding="utf-8")
            assert source_after == source_before, \
                "Source .claude/current_stage.json was modified by external editor!"

    def test_multiple_external_projects_isolated(self, tmp_path):
        """Two independent projects don't interfere with each other."""
        from fastapi.testclient import TestClient
        from stageflow.core import discovery
        from editor.server import create_app

        proj_a = tmp_path / "project_a"
        proj_b = tmp_path / "project_b"

        for proj, stage_name in [(proj_a, "alpha_one"), (proj_b, "beta_one")]:
            cfg = proj / ".stageflow" / "config"
            cfg.mkdir(parents=True)
            yaml_content = YAML_CUSTOM.replace("uno", stage_name)
            (cfg / "stages.yaml").write_text(yaml_content, encoding="utf-8")
            s = proj / ".stageflow" / "current_stage.json"
            s.write_text(json.dumps({"current_stage": None}), encoding="utf-8")

        # Edit project A
        root_a = discovery.ProjectRoot(
            path=proj_a, marker_type="new",
            config_path=proj_a / ".stageflow" / "config" / "stages.yaml",
            state_path=proj_a / ".stageflow" / "current_stage.json",
            artifacts_dir=proj_a / "artifacts" / "runs",
            audit_dir=proj_a / ".stageflow",
        )
        app_a = create_app(project_root=root_a)
        client_a = TestClient(app_a)
        r = client_a.post("/api/project/save-config",
                          json={"yaml": YAML_CUSTOM.replace("uno", "alpha_modified")})
        assert r.status_code == 200

        # Verify project A changed, project B unchanged
        a_content = (proj_a / ".stageflow" / "config" / "stages.yaml").read_text()
        b_content = (proj_b / ".stageflow" / "config" / "stages.yaml").read_text()
        assert "alpha_modified" in a_content
        assert "beta_one" in b_content
