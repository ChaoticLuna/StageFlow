"""Tests for stageflow.core.discovery — project root detection."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from stageflow.core.discovery import discover_project, ProjectRoot


class TestDiscoverNewStyle:
    def test_from_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".stageflow" / "config").mkdir(parents=True)
            (root / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            result = discover_project(root)
            assert result is not None
            assert result.marker_type == "new"
            assert result.path == root.resolve()
            assert result.config_path == root.resolve() / ".stageflow" / "config" / "stages.yaml"
            assert result.state_path == root.resolve() / ".stageflow" / "current_stage.json"

    def test_from_child_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".stageflow" / "config").mkdir(parents=True)
            (root / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            child = root / "src" / "deep"
            child.mkdir(parents=True)
            result = discover_project(child)
            assert result is not None
            assert result.path == root.resolve()
            assert result.marker_type == "new"

    def test_from_deeply_nested_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".stageflow" / "config").mkdir(parents=True)
            (root / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            deep = root / "a" / "b" / "c" / "d" / "e"
            deep.mkdir(parents=True)
            result = discover_project(deep)
            assert result is not None
            assert result.path == root.resolve()

    def test_no_project_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = discover_project(Path(tmp))
            assert result is None

    def test_artifacts_dir_new_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".stageflow" / "config").mkdir(parents=True)
            (root / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            result = discover_project(root)
            assert result.artifacts_dir == root.resolve() / "artifacts" / "runs"

    def test_audit_dir_new_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".stageflow" / "config").mkdir(parents=True)
            (root / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            result = discover_project(root)
            assert result.audit_dir == root.resolve() / ".stageflow"


class TestDiscoverLegacy:
    def test_legacy_config_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stageflow" / "config").mkdir(parents=True)
            (root / "stageflow" / "config" / "stages.yaml").write_text("stages: []")
            result = discover_project(root)
            assert result is not None
            assert result.marker_type == "legacy"
            assert result.path == root.resolve()
            assert result.config_path == root.resolve() / "stageflow" / "config" / "stages.yaml"
            assert result.state_path == root.resolve() / ".claude" / "current_stage.json"
            assert result.artifacts_dir == root.resolve() / "artifacts" / "runs"
            assert result.audit_dir == root.resolve() / ".claude"

    def test_legacy_from_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stageflow" / "config").mkdir(parents=True)
            (root / "stageflow" / "config" / "stages.yaml").write_text("stages: []")
            child = root / "sub" / "dir"
            child.mkdir(parents=True)
            result = discover_project(child)
            assert result is not None
            assert result.path == root.resolve()
            assert result.marker_type == "legacy"

    def test_legacy_state_only_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude").mkdir(parents=True)
            (root / ".claude" / "current_stage.json").write_text('{"stage": "pick"}')
            result = discover_project(root)
            assert result is not None
            assert result.marker_type == "legacy_state_only"
            assert result.state_path == root.resolve() / ".claude" / "current_stage.json"


class TestMarkerPriority:
    def test_new_beats_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".stageflow" / "config").mkdir(parents=True)
            (root / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            (root / "stageflow" / "config").mkdir(parents=True)
            (root / "stageflow" / "config" / "stages.yaml").write_text("stages: []")
            (root / ".claude").mkdir(parents=True)
            (root / ".claude" / "current_stage.json").write_text("{}")
            result = discover_project(root)
            assert result.marker_type == "new"

    def test_legacy_beats_state_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "stageflow" / "config").mkdir(parents=True)
            (root / "stageflow" / "config" / "stages.yaml").write_text("stages: []")
            (root / ".claude").mkdir(parents=True)
            (root / ".claude" / "current_stage.json").write_text("{}")
            result = discover_project(root)
            assert result.marker_type == "legacy"


class TestNestedProjects:
    def test_nearest_ancestor_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outer = root / "project-a"
            inner = outer / "src" / "project-b"
            (outer / ".stageflow" / "config").mkdir(parents=True)
            (outer / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            (inner / ".stageflow" / "config").mkdir(parents=True)
            (inner / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            work_dir = inner / "deep"
            work_dir.mkdir(parents=True)
            result = discover_project(work_dir)
            assert result is not None
            assert result.path == inner.resolve()

    def test_deep_nested_goes_to_outer_when_inner_has_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outer = root / "project-a"
            inner = outer / "src" / "project-b"
            (outer / ".stageflow" / "config").mkdir(parents=True)
            (outer / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            inner.mkdir(parents=True)
            result = discover_project(inner)
            assert result is not None
            assert result.path == outer.resolve()


class TestFilesystemBoundaries:
    def test_stops_at_filesystem_root(self):
        import sys
        if sys.platform != "win32":
            result = discover_project(Path("/"))
            assert result is None

    def test_stops_at_drive_root(self):
        result = discover_project(Path("C:\\"))
        assert result is None

    def test_temp_dir_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = discover_project(Path(tmp))
            assert result is None


class TestProjectRootImmutability:
    def test_frozen_dataclass(self):
        root = ProjectRoot(
            path=Path("/tmp/test"),
            marker_type="new",
            config_path=Path("/tmp/test/.stageflow/config/stages.yaml"),
            state_path=Path("/tmp/test/.stageflow/current_stage.json"),
            artifacts_dir=Path("/tmp/test/artifacts/runs"),
            audit_dir=Path("/tmp/test/.stageflow"),
        )
        with pytest.raises(Exception):
            root.marker_type = "legacy"


class TestCurrentDirectoryDefault:
    def test_uses_cwd_when_no_start_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".stageflow" / "config").mkdir(parents=True)
            (root / ".stageflow" / "config" / "stages.yaml").write_text("stages: []")
            import os
            original_cwd = os.getcwd()
            try:
                os.chdir(str(root))
                result = discover_project()
                assert result is not None
                assert result.path == root.resolve()
            finally:
                os.chdir(original_cwd)
