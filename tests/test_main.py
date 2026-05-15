"""CLI tests for python -m stageflow."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
STATE_FILE = PROJECT_ROOT / ".claude" / "current_stage.json"


def _stageflow(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "stageflow", *args],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
        timeout=30,
    )


@pytest.fixture
def uninitialized_state():
    """Temporarily remove state file so StateMachine starts uninitialized."""
    backup = None
    if STATE_FILE.exists():
        backup = STATE_FILE.read_bytes()
        STATE_FILE.unlink()
    yield
    if backup is not None:
        STATE_FILE.write_bytes(backup)


@pytest.fixture
def known_state_file():
    """Write a specific current_stage.json for testing, restore after."""
    backup = None
    if STATE_FILE.exists():
        backup = STATE_FILE.read_bytes()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "current_stage": "implement",
        "history": [
            {"from": "pick", "to": "analyze"}, {"from": "analyze", "to": "plan"},
            {"from": "plan", "to": "implement"}
        ],
        "retry_count": {}, "iterations": {}, "variables": {},
        "paused": False, "paused_reason": ""
    }))
    yield
    if backup is not None:
        STATE_FILE.write_bytes(backup)
    else:
        STATE_FILE.unlink()


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
        assert "variables" in data
        assert "run_id" in data["variables"]

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



    # ── resume / session-change (task-085) ────────────────────────────

    def test_resume_keeps_run_id_in_new_session(self):
        """A new StateMachine session retains the same run_id from disk."""
        r1 = _stageflow("reset", "pick")
        assert r1.returncode == 0, r1.stderr
        data1 = json.loads(_stageflow("status", "--json").stdout)
        rid1 = data1["variables"]["run_id"]

        data2 = json.loads(_stageflow("status", "--json").stdout)
        assert data2["variables"]["run_id"] == rid1

    def test_status_run_id_changes_after_reset(self):
        """Plain reset creates a new run_id (CLI-level)."""
        _stageflow("reset", "pick")
        data1 = json.loads(_stageflow("status", "--json").stdout)
        rid1 = data1["variables"]["run_id"]

        r = _stageflow("reset", "pick")
        assert r.returncode == 0, r.stderr
        data2 = json.loads(_stageflow("status", "--json").stdout)
        rid2 = data2["variables"]["run_id"]

        assert rid1 != rid2, (
            f"Plain reset must create new run_id: {rid1} -> {rid2}"
        )

    def test_status_run_id_preserved_after_reset_reuse(self):
        """reset --reuse-run preserves the same run_id (CLI-level)."""
        _stageflow("reset", "pick")
        data1 = json.loads(_stageflow("status", "--json").stdout)
        rid1 = data1["variables"]["run_id"]

        r = _stageflow("reset", "pick", "--reuse-run")
        assert r.returncode == 0, r.stderr
        data2 = json.loads(_stageflow("status", "--json").stdout)
        rid2 = data2["variables"]["run_id"]

        assert rid1 == rid2, (
            f"reset --reuse-run must preserve run_id: {rid1} != {rid2}"
        )

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

    def test_graph_mermaid_output(self):
        r = _stageflow("graph")
        assert r.returncode == 0, r.stderr
        assert "flowchart TD" in r.stdout
        assert "```mermaid" in r.stdout

    def test_cond_always_passes(self):
        r = _stageflow("cond", "always")
        assert r.returncode == 0, r.stderr
        assert "PASS" in r.stdout

    def test_cond_with_params(self):
        r = _stageflow("cond", "never", "--params", '{"reason": "test"}')
        assert r.returncode in (0, 1), r.stderr
        assert "FAIL" in r.stdout

    def test_cond_bare_shows_usage(self):
        r = _stageflow("cond")
        assert r.returncode == 1, r.stderr
        assert "Usage:" in r.stderr or "usage:" in r.stderr.lower()

    def test_back_runs(self):
        r = _stageflow("back")
        assert r.returncode in (0, 1), f"rc={r.returncode}: {r.stderr}"

    def test_jump_runs(self):
        r = _stageflow("jump", "analyze")
        assert r.returncode in (0, 1), f"rc={r.returncode}: {r.stderr}"

    def test_reset_runs(self):
        r = _stageflow("reset")
        assert r.returncode in (0, 1), f"rc={r.returncode}: {r.stderr}"

    def test_init_runs(self):
        r = _stageflow("reset", "analyze")
        assert r.returncode in (0, 1), f"rc={r.returncode}: {r.stderr}"

    def test_check_plain_output(self):
        r = _stageflow("check", "analyze")
        assert r.returncode in (0, 1), f"rc={r.returncode}: {r.stderr}"

    def test_status_verbose_shows_details(self):
        """--verbose shows transitions, hooks, and variables sections."""
        r = _stageflow("status", "--verbose")
        assert r.returncode == 0, r.stderr
        assert "Transitions from" in r.stdout
        assert "Conditions" in r.stdout or "No transitions" in r.stdout
        assert "Hooks" in r.stdout
        assert "Variables" in r.stdout

    def test_status_verbose_short_flag(self):
        """-v short flag should work same as --verbose."""
        r = _stageflow("status", "-v")
        assert r.returncode == 0, r.stderr
        assert "Transitions from" in r.stdout or "No transitions" in r.stdout

    def test_status_verbose_uninitialized(self, uninitialized_state):
        """--verbose with uninitialized state should not error."""
        r = _stageflow("status", "--verbose")
        assert r.returncode == 0, r.stderr
        assert "(not initialized)" in r.stdout

    # ── force / hard reset paths ──────────────────────────────────────

    def test_next_force(self, known_state_file):
        r = _stageflow("next", "--force", "verify")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"

    def test_reset_hard(self):
        r = _stageflow("reset", "--hard")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"
        assert "fully reset" in r.stdout

    def test_jump_force(self, known_state_file):
        r = _stageflow("jump", "--force", "verify")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"

    # ── uninitialized paths ───────────────────────────────────────────

    def test_back_uninitialized(self, uninitialized_state):
        r = _stageflow("back")
        assert r.returncode in (0, 1), f"rc={r.returncode}: {r.stderr}"

    def test_jump_uninitialized(self, uninitialized_state):
        r = _stageflow("jump", "analyze")
        assert r.returncode in (0, 1), f"rc={r.returncode}: {r.stderr}"

    def test_check_uninitialized(self, uninitialized_state):
        r = _stageflow("check", "analyze")
        assert r.returncode == 1, f"rc={r.returncode}: {r.stderr}"
        assert "Not initialized" in r.stderr

    def test_check_uninitialized_json(self, uninitialized_state):
        r = _stageflow("check", "--json", "analyze")
        assert r.returncode == 1, f"rc={r.returncode}: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["current_stage"] is None
        assert "error" in data

    # ── cond with valid params (pass + fail) ───────────────────────────

    def test_cond_file_exists_pass(self):
        r = _stageflow("cond", "file_exists", "--params",
                        '{"path": "pyproject.toml"}')
        assert r.returncode == 0, r.stderr
        assert "PASS" in r.stdout

    def test_cond_file_exists_fail(self):
        r = _stageflow("cond", "file_exists", "--params",
                        '{"path": "nonexistent_file_xyzzz.xyz"}')
        assert r.returncode in (0, 1), r.stderr
        assert "FAIL" in r.stdout

    def test_cond_file_not_exists_pass(self):
        r = _stageflow("cond", "file_not_exists", "--params",
                        '{"path": "nonexistent_file_xyzzz.xyz"}')
        assert r.returncode == 0, r.stderr
        assert "PASS" in r.stdout

    def test_cond_env_var(self):
        r = _stageflow("cond", "env_var", "--params",
                        '{"name": "PATH", "op": "exists"}')
        assert r.returncode == 0, r.stderr
        assert "PASS" in r.stdout

    def test_cond_command_exists_pass(self):
        r = _stageflow("cond", "command_exists", "--params", '{"command": "python"}')
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"
        assert "PASS" in r.stdout

    def test_cond_command_exists_fail(self):
        r = _stageflow("cond", "command_exists", "--params",
                        '{"command": "nonexistent_cmd_xyzzz_abc"}')
        assert r.returncode in (0, 1), r.stderr
        assert "FAIL" in r.stdout

    def test_cond_always_passes_direct(self):
        r = _stageflow("cond", "always")
        assert r.returncode == 0, r.stderr
        assert "PASS" in r.stdout

    # ── graph with current stage highlighting ─────────────────────────

    def test_graph_with_known_stage(self, known_state_file):
        r = _stageflow("graph")
        assert r.returncode == 0, r.stderr
        assert "flowchart TD" in r.stdout
        assert ":::current" in r.stdout


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

    def test_main_no_command_shows_help(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["stageflow"])
        sys.path.insert(0, str(PROJECT_ROOT))
        from stageflow.__main__ import main
        result = main()
        assert result == 1


class TestGenerateCLI:
    def test_list_templates(self):
        r = _stageflow("generate", "--list-templates")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"
        assert "GENERIC" in r.stdout
        assert "CI_CD" in r.stdout

    def test_basic_generation(self):
        r = _stageflow("generate", "test workflow")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"
        assert "stages:" in r.stdout

    def test_prompt_only(self):
        r = _stageflow("generate", "test", "--prompt-only")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"
        assert len(r.stdout) > 0

    def test_with_template(self):
        r = _stageflow("generate", "ci pipeline", "--template", "CI_CD")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"
        assert "stages:" in r.stdout

    def test_with_bad_template(self):
        r = _stageflow("generate", "test", "--template", "NONEXISTENT")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"

    def test_with_validate(self):
        r = _stageflow("generate", "test workflow", "--validate")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"
        assert "stages:" in r.stdout

    def test_with_output_file(self, tmp_path):
        out = tmp_path / "generated.yaml"
        r = _stageflow("generate", "test", "--output", str(out))
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"
        assert out.exists()
        content = out.read_text()
        assert "stages:" in content

    def test_generate_no_args(self):
        r = _stageflow("generate")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"


class TestMainInProcess:
    """Call main() directly via monkeypatch for coverage tracking."""

    def _run(self, monkeypatch, *args):
        monkeypatch.setattr(sys, "argv", ["stageflow"] + list(args))
        sys.path.insert(0, str(PROJECT_ROOT))
        from stageflow.__main__ import main
        try:
            return main()
        except SystemExit as e:
            return int(e.code) if e.code is not None else 0

    # ── status ──────────────────────────────────────────────────────

    def test_status_json(self, monkeypatch):
        result = self._run(monkeypatch, "status", "--json")
        assert result in (0, None)

    def test_status_verbose(self, monkeypatch):
        result = self._run(monkeypatch, "status", "--verbose")
        assert result in (0, None)

    # ── list ─────────────────────────────────────────────────────────

    def test_list_json(self, monkeypatch):
        result = self._run(monkeypatch, "list", "--json")
        assert result in (0, None)

    # ── next ─────────────────────────────────────────────────────────

    def test_next_basic(self, monkeypatch):
        result = self._run(monkeypatch, "next")
        assert result in (0, 1, None)

    def test_next_force(self, monkeypatch, known_state_file):
        result = self._run(monkeypatch, "next", "--force", "verify")
        assert result in (0, None)

    def test_next_dry_run(self, monkeypatch):
        result = self._run(monkeypatch, "next", "--dry-run")
        assert result in (0, 1, None)

    def test_next_dry_run_target(self, monkeypatch, known_state_file):
        result = self._run(monkeypatch, "next", "--dry-run", "verify")
        assert result in (0, 1, None)

    # ── back / jump ──────────────────────────────────────────────────

    def test_back(self, monkeypatch):
        result = self._run(monkeypatch, "back")
        assert result in (0, 1, None)

    def test_jump(self, monkeypatch):
        result = self._run(monkeypatch, "jump", "analyze")
        assert result in (0, 1, None)

    def test_jump_force(self, monkeypatch, known_state_file):
        result = self._run(monkeypatch, "jump", "--force", "verify")
        assert result in (0, None)

    # ── reset ────────────────────────────────────────────────────────

    def test_reset(self, monkeypatch):
        result = self._run(monkeypatch, "reset")
        assert result in (0, 1, None)

    def test_reset_hard(self, monkeypatch):
        result = self._run(monkeypatch, "reset", "--hard")
        assert result in (0, None)

    def test_reset_reuse_run(self, monkeypatch):
        result = self._run(monkeypatch, "reset", "pick", "--reuse-run")
        assert result in (0, 1, None)

    def test_reset_clean_artifacts(self, monkeypatch):
        result = self._run(monkeypatch, "reset", "pick", "--clean-artifacts")
        assert result in (0, 1, None)

    # ── graph / init / check ─────────────────────────────────────────

    def test_graph(self, monkeypatch):
        result = self._run(monkeypatch, "graph")
        assert result in (0, None)

    def test_init(self, monkeypatch):
        result = self._run(monkeypatch, "reset", "analyze")
        assert result in (0, 1, None)

    def test_check(self, monkeypatch):
        result = self._run(monkeypatch, "check", "analyze")
        assert result in (0, 1, None)

    def test_check_json(self, monkeypatch):
        result = self._run(monkeypatch, "check", "--json", "analyze")
        assert result in (0, 1, None)

    def test_check_uninitialized(self, monkeypatch, uninitialized_state):
        result = self._run(monkeypatch, "check", "analyze")
        assert result == 1

    # ── cond ─────────────────────────────────────────────────────────

    def test_cond_list(self, monkeypatch):
        result = self._run(monkeypatch, "cond", "--list")
        assert result == 0

    def test_cond_always(self, monkeypatch):
        result = self._run(monkeypatch, "cond", "always")
        assert result in (0, None)

    def test_cond_with_params(self, monkeypatch):
        result = self._run(monkeypatch, "cond", "file_exists", "--params",
                           '{"path": "pyproject.toml"}')
        assert result in (0, None)

    def test_cond_bare(self, monkeypatch):
        result = self._run(monkeypatch, "cond")
        assert result == 1

    # ── generate ─────────────────────────────────────────────────────

    def test_generate_basic(self, monkeypatch):
        result = self._run(monkeypatch, "generate", "test workflow")
        assert result in (0, None)

    def test_generate_list_templates(self, monkeypatch):
        result = self._run(monkeypatch, "generate", "--list-templates")
        assert result == 0

    def test_generate_prompt_only(self, monkeypatch):
        result = self._run(monkeypatch, "generate", "test", "--prompt-only")
        assert result in (0, None)

    def test_generate_with_template(self, monkeypatch):
        result = self._run(monkeypatch, "generate", "ci test", "--template", "CI_CD")
        assert result in (0, None)

    def test_generate_bad_template(self, monkeypatch):
        result = self._run(monkeypatch, "generate", "test", "--template", "NONEXISTENT")
        assert result in (0, None)

    def test_generate_with_validate(self, monkeypatch):
        result = self._run(monkeypatch, "generate", "test", "--validate")
        assert result in (0, None)

    def test_generate_with_output(self, monkeypatch, tmp_path):
        out = tmp_path / "out.yaml"
        result = self._run(monkeypatch, "generate", "test", "--output", str(out))
        assert result in (0, None)

    # ── mcp ──────────────────────────────────────────────────────────

    def test_mcp_help(self, monkeypatch):
        result = self._run(monkeypatch, "mcp", "--help")
        assert result == 0


class TestNewInitAndStart:
    """Tests for the new stageflow init (project bootstrap) and stageflow start."""

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    def test_init_creates_structure(self, tmp_path):
        r = self._run(tmp_path, "init")
        assert r.returncode == 0, r.stderr
        assert (tmp_path / ".stageflow" / "config" / "stages.yaml").is_file()
        assert (tmp_path / ".claude" / "settings.json").is_file()
        assert (tmp_path / "artifacts" / "runs").is_dir()
        assert not (tmp_path / ".stageflow" / "current_stage.json").exists()

    def test_init_idempotent(self, tmp_path):
        r1 = self._run(tmp_path, "init")
        assert r1.returncode == 0
        r2 = self._run(tmp_path, "init")
        assert r2.returncode == 0
        assert "already initialized" in r2.stdout

    def test_init_force_overwrite(self, tmp_path):
        self._run(tmp_path, "init")
        yaml_path = tmp_path / ".stageflow" / "config" / "stages.yaml"
        original = yaml_path.read_text(encoding="utf-8")
        yaml_path.write_text("# modified", encoding="utf-8")
        r = self._run(tmp_path, "init", "--force")
        assert r.returncode == 0
        restored = yaml_path.read_text(encoding="utf-8")
        assert restored == original

    def test_init_start_starts_run(self, tmp_path):
        r = self._run(tmp_path, "init", "--start")
        assert r.returncode == 0, r.stderr
        state = tmp_path / ".stageflow" / "current_stage.json"
        assert state.is_file()
        import json
        data = json.loads(state.read_text())
        assert data["current_stage"] == "pick"
        assert "run_id" in data.get("variables", {})

    def test_init_inside_existing_project_blocked(self, tmp_path):
        self._run(tmp_path, "init")
        inner = tmp_path / "subdir"
        inner.mkdir()
        r = self._run(inner, "init")
        assert r.returncode == 1
        assert "Already inside" in r.stderr

    def test_start_after_init(self, tmp_path):
        self._run(tmp_path, "init")
        r = self._run(tmp_path, "start")
        assert r.returncode == 0
        import json
        data = json.loads((tmp_path / ".stageflow" / "current_stage.json").read_text())
        assert data["current_stage"] == "pick"

    def test_start_with_custom_stage(self, tmp_path):
        self._run(tmp_path, "init")
        r = self._run(tmp_path, "start", "analyze")
        assert r.returncode == 0
        import json
        data = json.loads((tmp_path / ".stageflow" / "current_stage.json").read_text())
        assert data["current_stage"] == "analyze"

    def test_start_fails_when_run_active(self, tmp_path):
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "start", "pick")
        assert r.returncode == 1
        assert "already active" in r.stderr

    def test_start_outside_project_fails(self, tmp_path):
        r = self._run(tmp_path, "start", "pick")
        assert r.returncode == 1
        assert "Not a StageFlow project" in r.stderr

    def test_start_unknown_stage_rejected(self, tmp_path):
        self._run(tmp_path, "init")
        r = self._run(tmp_path, "start", "nonexistent_stage_xyz")
        assert r.returncode == 1

    def test_next_without_run_fails(self, tmp_path):
        self._run(tmp_path, "init")
        r = self._run(tmp_path, "next")
        assert r.returncode == 1
        assert "No active run" in r.stderr

    def test_init_creates_valid_stages_yaml(self, tmp_path):
        self._run(tmp_path, "init")
        import yaml
        yaml_path = tmp_path / ".stageflow" / "config" / "stages.yaml"
        config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert "stages" in config
        assert "transitions" in config
        assert len(config["stages"]) >= 2

    def test_status_works_in_new_project(self, tmp_path):
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "status")
        assert r.returncode == 0
        assert "pick" in r.stdout

    def test_status_json_in_new_project(self, tmp_path):
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "status", "--json")
        assert r.returncode == 0
        import json
        data = json.loads(r.stdout)
        assert data["current_stage"] == "pick"

    def test_next_advances_in_new_project(self, tmp_path):
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        import json
        state = json.loads((tmp_path / ".stageflow" / "current_stage.json").read_text())
        run_id = state["variables"]["run_id"]
        (tmp_path / "artifacts" / "runs" / run_id / "pick").mkdir(parents=True)
        (tmp_path / "artifacts" / "runs" / run_id / "pick" / "issue_context.md").write_text("test")
        r = self._run(tmp_path, "next")
        assert r.returncode == 0


    def test_start_with_custom_yaml_enters_first_stage(self, tmp_path):
        self._run(tmp_path, "init")
        yaml_path = tmp_path / ".stageflow" / "config" / "stages.yaml"
        import yaml
        config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        config["stages"] = [
            {"name": "alpha", "tools": ["Read"], "meta": {"description": "First custom stage"}},
            {"name": "beta", "tools": ["Write"], "meta": {"description": "Second custom stage"}},
            {"name": "gamma", "tools": [], "meta": {"description": "Terminal custom stage"}},
        ]
        config["transitions"] = [
            {"from": "alpha", "to": "beta", "conditions": [{"always": True}]},
            {"from": "beta", "to": "gamma", "conditions": [{"always": True}]},
        ]
        yaml_path.write_text(yaml.dump(config), encoding="utf-8")
        r = self._run(tmp_path, "start")
        assert r.returncode == 0, r.stderr
        import json
        state = json.loads((tmp_path / ".stageflow" / "current_stage.json").read_text())
        assert state["current_stage"] == "alpha"

    def test_start_custom_yaml_specific_stage(self, tmp_path):
        self._run(tmp_path, "init")
        yaml_path = tmp_path / ".stageflow" / "config" / "stages.yaml"
        import yaml
        config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        config["stages"] = [
            {"name": "alpha", "tools": ["Read"], "meta": {"description": "First custom stage"}},
            {"name": "beta", "tools": ["Write"], "meta": {"description": "Second custom stage"}},
            {"name": "gamma", "tools": [], "meta": {"description": "Terminal custom stage"}},
        ]
        config["transitions"] = [
            {"from": "alpha", "to": "beta", "conditions": [{"always": True}]},
            {"from": "beta", "to": "gamma", "conditions": [{"always": True}]},
        ]
        yaml_path.write_text(yaml.dump(config), encoding="utf-8")
        r = self._run(tmp_path, "start", "beta")
        assert r.returncode == 0, r.stderr
        import json
        state = json.loads((tmp_path / ".stageflow" / "current_stage.json").read_text())
        assert state["current_stage"] == "beta"

    def test_init_preserves_existing_state_on_force(self, tmp_path):
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "init", "--force")
        assert r.returncode == 0
        import json
        state = json.loads((tmp_path / ".stageflow" / "current_stage.json").read_text())
        assert state["current_stage"] == "pick"


class TestNestedDirectoryCommands:
    """Commands operate on discovered project root, not cwd or package source."""

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    @staticmethod
    def _make_custom_yaml(yaml_path):
        import yaml
        config = {
            "stages": [
                {"name": "alpha", "tools": ["Read"], "meta": {"description": "First custom"}},
                {"name": "beta", "tools": ["Write"], "meta": {"description": "Second custom"}},
                {"name": "gamma", "tools": [], "meta": {"description": "Terminal custom"}},
            ],
            "transitions": [
                {"from": "alpha", "to": "beta", "conditions": [{"always": True}]},
                {"from": "beta", "to": "gamma", "conditions": [{"always": True}]},
            ],
        }
        yaml_path.write_text(yaml.dump(config), encoding="utf-8")

    def test_status_from_nested_subdir_sees_correct_stage(self, tmp_path):
        self._run(tmp_path, "init")
        self._make_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        r = self._run(nested, "status")
        assert r.returncode == 0, r.stderr
        assert "alpha" in r.stdout

    def test_start_from_nested_subdir_mutates_only_project_root(self, tmp_path):
        self._run(tmp_path, "init")
        self._make_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        r = self._run(nested, "start", "alpha")
        assert r.returncode == 0, r.stderr
        state = tmp_path / ".stageflow" / "current_stage.json"
        assert state.is_file()
        import json
        data = json.loads(state.read_text())
        assert data["current_stage"] == "alpha"
        assert "run_id" in data.get("variables", {})
        assert not (nested / ".stageflow").exists()
        assert not (nested / ".claude").exists()

    def test_next_dry_run_from_nested_subdir(self, tmp_path):
        self._run(tmp_path, "init")
        self._make_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        r = self._run(nested, "next", "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "ALLOWED" in r.stdout

    def test_reset_from_nested_subdir_mutates_only_project_root(self, tmp_path):
        self._run(tmp_path, "init")
        self._make_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        r = self._run(nested, "reset", "alpha")
        assert r.returncode == 0, r.stderr
        state = tmp_path / ".stageflow" / "current_stage.json"
        assert state.is_file()
        assert not (nested / ".stageflow").exists()
        assert not (nested / ".claude").exists()

    def test_no_legacy_state_file_created_in_new_project(self, tmp_path):
        self._run(tmp_path, "init")
        self._make_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        assert not (tmp_path / ".claude" / "current_stage.json").exists()

    def test_package_source_tree_not_mutated(self, tmp_path):
        import os
        pkg_state = os.path.join(os.path.dirname(__file__), "..", ".claude", "current_stage.json")
        pkg_stageflow_dir = os.path.join(os.path.dirname(__file__), "..", ".stageflow")
        before_state_exists = os.path.exists(pkg_state)
        before_stageflow_exists = os.path.isdir(pkg_stageflow_dir)
        self._run(tmp_path, "init")
        self._make_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        assert os.path.exists(pkg_state) == before_state_exists
        assert os.path.isdir(pkg_stageflow_dir) == before_stageflow_exists

    def test_outside_project_fails_from_any_dir(self, tmp_path):
        r = self._run(tmp_path, "status")
        assert r.returncode == 1
        assert "Not a StageFlow project" in r.stderr
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        r2 = self._run(nested, "next")
        assert r2.returncode == 1
        assert "Not a StageFlow project" in r2.stderr

    def test_status_json_from_nested_subdir(self, tmp_path):
        self._run(tmp_path, "init")
        self._make_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        r = self._run(nested, "status", "--json")
        assert r.returncode == 0, r.stderr
        import json
        data = json.loads(r.stdout)
        assert data["current_stage"] == "alpha"
