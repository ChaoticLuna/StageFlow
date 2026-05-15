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
        r = _stageflow("init", "analyze")
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
