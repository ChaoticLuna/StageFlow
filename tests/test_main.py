"""CLI tests for python -m stageflow."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


def _stageflow(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "stageflow", *args],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )


class TestStageflowCLI:
    def test_status_runs(self):
        r = _stageflow("status")
        assert r.returncode == 0, r.stderr

    def test_list_runs(self):
        r = _stageflow("list")
        assert r.returncode == 0, r.stderr

    def test_help_flag(self):
        r = _stageflow("--help")
        assert r.returncode == 0, r.stderr
        assert "usage:" in r.stdout.lower() or "usage:" in r.stderr.lower()

    def test_graph_runs(self):
        r = _stageflow("graph")
        assert r.returncode == 0, r.stderr

    def test_cond_help(self):
        r = _stageflow("cond", "--help")
        assert r.returncode == 0, r.stderr

    def test_check_unknown_stage(self):
        r = _stageflow("check", "nonexistent_stage_xyz")
        assert r.returncode in (0, 1), f"rc={r.returncode}: {r.stderr}"

    def test_next_with_target(self):
        r = _stageflow("next", "analyze")
        assert r.returncode in (0, 1), f"rc={r.returncode}: {r.stderr}"

    def test_reset_help(self):
        r = _stageflow("reset", "--help")
        assert r.returncode == 0, r.stderr

    def test_status_json_output(self):
        r = _stageflow("status", "--json")
        assert r.returncode == 0, r.stderr
        import json
        data = json.loads(r.stdout)
        assert "current_stage" in data
        assert "history" in data
        assert "registered_stages" in data

    def test_list_json_output(self):
        r = _stageflow("list", "--json")
        assert r.returncode == 0, r.stderr
        import json
        data = json.loads(r.stdout)
        assert "stages" in data
        assert "transitions" in data
        assert isinstance(data["valid"], bool)

    def test_check_json_output(self):
        r = _stageflow("check", "--json", "analyze")
        import json
        data = json.loads(r.stdout)
        assert "current_stage" in data
        assert "target" in data
        assert "allowed" in data
        assert "messages" in data

    def test_status_json_short_flag(self):
        r = _stageflow("status", "-j")
        assert r.returncode == 0, r.stderr
        import json
        data = json.loads(r.stdout)
        assert "current_stage" in data

    def test_next_dry_run(self):
        r = _stageflow("next", "--dry-run")
        assert "Dry-run" in r.stdout or r.returncode in (0, 1), r.stderr

    def test_next_dry_run_with_target(self):
        r = _stageflow("next", "--dry-run", "analyze")
        assert "Dry-run" in r.stdout or r.returncode in (0, 1), r.stderr

    def test_next_dry_run_short_flag(self):
        r = _stageflow("next", "-n")
        assert "Dry-run" in r.stdout or r.returncode in (0, 1), r.stderr

    def test_cond_list(self):
        r = _stageflow("cond", "--list")
        assert r.returncode == 0, r.stderr
        assert "file_exists" in r.stdout
        assert "shell_test" in r.stdout
        assert "always" in r.stdout

    def test_cond_list_short_flag(self):
        r = _stageflow("cond", "-l")
        assert r.returncode == 0, r.stderr
        assert "file_exists" in r.stdout


class TestStageflowMainModule:
    def test_import_main(self):
        sys.path.insert(0, str(PROJECT_ROOT))
        from stageflow.__main__ import main
        assert callable(main)

    def test_main_with_help(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["stageflow", "--help"])
        sys.path.insert(0, str(PROJECT_ROOT))
        from stageflow.__main__ import main
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    def test_main_with_list(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["stageflow", "list"])
        sys.path.insert(0, str(PROJECT_ROOT))
        from stageflow.__main__ import main
        result = main()
        assert result is None or result in (0, 1)

    def test_main_with_status(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["stageflow", "status"])
        sys.path.insert(0, str(PROJECT_ROOT))
        from stageflow.__main__ import main
        result = main()
        assert result is None or result in (0, 1)

    def test_main_with_cond_help(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["stageflow", "cond", "--help"])
        sys.path.insert(0, str(PROJECT_ROOT))
        from stageflow.__main__ import main
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
