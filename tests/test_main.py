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

    def test_register_help(self):
        r = _stageflow("register", "--help")
        assert r.returncode == 0, r.stderr
        assert "--bin-dir" in r.stdout
        assert "--machine" in r.stdout
        assert "--no-path" in r.stdout
        assert "--build-editor" in r.stdout

    def test_register_no_path_writes_wrappers(self, tmp_path):
        bin_dir = tmp_path / "bin"
        r = _stageflow("register", "--bin-dir", str(bin_dir), "--no-path")
        assert r.returncode == 0, r.stderr
        assert "Registered StageFlow wrappers" in r.stdout
        shell_wrapper = bin_dir / "stageflow"
        assert shell_wrapper.exists()
        assert "-m stageflow" in shell_wrapper.read_text(encoding="utf-8")
        if sys.platform.startswith("win"):
            cmd_wrapper = bin_dir / "stageflow.cmd"
            assert cmd_wrapper.exists()
            assert "-m stageflow" in cmd_wrapper.read_text(encoding="utf-8")

    def test_status_json_output(self):
        _stageflow("reset")
        _stageflow("start", "pick")
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
        _stageflow("reset")
        r1 = _stageflow("start", "pick")
        assert r1.returncode == 0, r1.stderr
        data1 = json.loads(_stageflow("status", "--json").stdout)
        rid1 = data1["variables"]["run_id"]

        data2 = json.loads(_stageflow("status", "--json").stdout)
        assert data2["variables"]["run_id"] == rid1

    def test_status_run_id_changes_after_reset(self):
        """Reset + start creates a new run_id (CLI-level)."""
        _stageflow("reset")
        _stageflow("start", "pick")
        data1 = json.loads(_stageflow("status", "--json").stdout)
        rid1 = data1["variables"]["run_id"]

        _stageflow("reset")
        r = _stageflow("start", "pick")
        assert r.returncode == 0, r.stderr
        data2 = json.loads(_stageflow("status", "--json").stdout)
        rid2 = data2["variables"]["run_id"]

        assert rid1 != rid2, (
            f"Reset + start must create new run_id: {rid1} -> {rid2}"
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
        _stageflow("reset")
        r = _stageflow("start", "analyze")
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
        assert "No active run" in r.stdout

    # ── force / hard reset paths ──────────────────────────────────────

    def test_next_force(self, known_state_file):
        r = _stageflow("next", "--force", "verify")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"

    def test_reset_hard(self):
        r = _stageflow("reset", "--hard")
        assert r.returncode == 0, f"rc={r.returncode}: {r.stderr}"
        assert "fully reset" in r.stdout

    def test_jump_force(self, known_state_file):
        r = _stageflow("jump", "--force", "--reason", "test force jump", "verify")
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
        result = self._run(monkeypatch, "jump", "--force", "--reason", "test force jump", "verify")
        assert result in (0, None)

    # ── reset ────────────────────────────────────────────────────────

    def test_reset(self, monkeypatch):
        result = self._run(monkeypatch, "reset")
        assert result in (0, 1, None)

    def test_reset_hard(self, monkeypatch):
        result = self._run(monkeypatch, "reset", "--hard")
        assert result in (0, None)

    def test_reset_clean_artifacts(self, monkeypatch):
        result = self._run(monkeypatch, "reset", "--clean-artifacts")
        assert result in (0, 1, None)

    # ── graph / init / check ─────────────────────────────────────────

    def test_graph(self, monkeypatch):
        result = self._run(monkeypatch, "graph")
        assert result in (0, None)

    def test_init(self, monkeypatch):
        result = self._run(monkeypatch, "start", "analyze")
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
    def _stageflow_hook_entry():
        return {
            "matcher": "*",
            "hooks": [
                {"type": "command", "command": "stageflow hook", "timeout": 10}
            ],
        }

    @staticmethod
    def _is_stageflow_hook_entry(entry):
        return (
            isinstance(entry, dict)
            and entry.get("matcher") == "*"
            and isinstance(entry.get("hooks"), list)
            and any(
                isinstance(h, dict)
                and h.get("type") == "command"
                and h.get("command") == "stageflow hook"
                for h in entry["hooks"]
            )
        )

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

    def test_init_merges_existing_claude_settings(self, tmp_path):
        import json
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({
            "permissionMode": "default",
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash(*)", "command": "echo existing", "timeout": 5}
                ],
                "PostToolUse": [
                    {"matcher": "Write", "command": "echo post"}
                ],
            },
        }), encoding="utf-8")

        r = self._run(tmp_path, "init")
        assert r.returncode == 0, r.stderr
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert data["permissionMode"] == "default"
        assert data["hooks"]["PostToolUse"] == [
            {"matcher": "Write", "command": "echo post"}
        ]
        pre = data["hooks"]["PreToolUse"]
        assert {"matcher": "Bash(*)", "command": "echo existing", "timeout": 5} in pre
        assert self._stageflow_hook_entry() in pre

    def test_init_does_not_duplicate_stageflow_hook(self, tmp_path):
        import json
        self._run(tmp_path, "init")
        r = self._run(tmp_path, "init", "--force")
        assert r.returncode == 0, r.stderr
        settings_path = tmp_path / ".claude" / "settings.json"
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks = [
            h for h in data["hooks"]["PreToolUse"]
            if self._is_stageflow_hook_entry(h)
        ]
        assert len(hooks) == 1

    def test_init_normalizes_existing_stageflow_hook(self, tmp_path):
        import json
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({
            "hooks": {
                "PreToolUse": [
                    {"matcher": "", "hooks": [{"type": "command", "command": "stageflow hook"}]},
                    {"matcher": "", "command": "stageflow hook", "timeout": 10},
                ]
            }
        }), encoding="utf-8")

        r = self._run(tmp_path, "init")
        assert r.returncode == 0, r.stderr
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        pre = data["hooks"]["PreToolUse"]
        assert pre == [self._stageflow_hook_entry()]

    def test_init_refuses_invalid_claude_settings(self, tmp_path):
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text("{ invalid json", encoding="utf-8")

        r = self._run(tmp_path, "init")
        assert r.returncode == 1
        assert "Refusing to overwrite invalid JSON" in r.stderr
        assert settings_path.read_text(encoding="utf-8") == "{ invalid json"

    def test_init_merges_claude_settings_with_utf8_bom(self, tmp_path):
        import json
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash(*)", "command": "echo existing"}
                ]
            }
        }), encoding="utf-8-sig")

        r = self._run(tmp_path, "init")
        assert r.returncode == 0, r.stderr
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        pre = data["hooks"]["PreToolUse"]
        assert {"matcher": "Bash(*)", "command": "echo existing"} in pre
        assert self._stageflow_hook_entry() in pre

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
        r = self._run(nested, "reset")
        assert r.returncode == 0, r.stderr
        assert "StageFlow state cleared" in r.stdout
        assert not (nested / ".stageflow").exists()
        assert not (nested / ".claude").exists()
        assert not (tmp_path / ".stageflow" / "current_stage.json").exists()

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


class TestResetAndJumpHardening:
    """Reset must not accept stage arg; jump --force requires --reason."""

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    def test_reset_with_stage_fails_clear_error(self, tmp_path):
        """reset <stage> must fail with a clear usage error."""
        self._run(tmp_path, "init")
        r = self._run(tmp_path, "reset", "pick")
        assert r.returncode != 0, f"reset pick should fail, got rc={r.returncode}"
        assert "unrecognized" in r.stderr.lower() or "usage" in r.stderr.lower()

    def test_plain_reset_clears_state_without_stage(self, tmp_path):
        """Plain reset clears active run and prints guidance."""
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "reset")
        assert r.returncode == 0, r.stderr
        assert "StageFlow state cleared" in r.stdout
        assert "stageflow start" in r.stdout

    def test_reset_hard_clears_state(self, tmp_path):
        """reset --hard fully clears the state file."""
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "reset", "--hard")
        assert r.returncode == 0, r.stderr

    def test_forced_jump_requires_reason(self, tmp_path):
        """jump --force without --reason fails."""
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "jump", "verify", "--force")
        assert r.returncode == 1, f"jump --force without --reason should fail, rc={r.returncode}"
        assert "--reason" in r.stderr

    def test_forced_jump_with_reason_works(self, tmp_path):
        """jump --force --reason '...' succeeds."""
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "jump", "verify", "--force", "--reason", "emergency rollback")
        assert r.returncode == 0, r.stderr

    def test_jump_without_force_still_condition_gated(self, tmp_path):
        """Normal jump (no --force) must still pass conditions."""
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "jump", "verify")
        assert r.returncode == 1, f"jump without force should be condition-gated, rc={r.returncode}"

    def test_next_remains_condition_gated(self, tmp_path):
        """Normal next must not bypass conditions."""
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "next")
        assert r.returncode == 1, f"next should be condition-gated, rc={r.returncode}"

    def test_next_force_succeeds(self, tmp_path):
        """next --force bypasses conditions."""
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")
        r = self._run(tmp_path, "next", "--force")
        assert r.returncode == 0, r.stderr


class TestHookCommand:
    """Claude Code PreToolUse hook via stageflow hook command."""

    @staticmethod
    def _hook(cwd, tool_name, tool_input=None):
        import subprocess, sys, json
        hook_input = json.dumps({"tool_name": tool_name, "tool_input": tool_input or {}})
        return subprocess.run(
            [sys.executable, "-m", "stageflow", "hook"],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
            input=hook_input,
        )

    @staticmethod
    def _permission_decision(result):
        import json
        data = json.loads(result.stdout)
        return data["hookSpecificOutput"]["permissionDecision"]

    @staticmethod
    def _make_stages_yaml(yaml_path, stages=None, transitions=None):
        import yaml
        config = {
            "stages": [
                {"name": "alpha", "tools": ["Read", "Grep", "Bash(git *)"], "meta": {"description": "First"}},
                {"name": "beta", "tools": ["Read", "Edit", "Write"], "meta": {"description": "Second"}},
                {"name": "gamma", "tools": [], "meta": {"description": "Terminal"}},
            ] if stages is None else stages,
            "transitions": [
                {"from": "alpha", "to": "beta", "conditions": [{"always": True}]},
                {"from": "beta", "to": "gamma", "conditions": [{"always": True}]},
            ] if transitions is None else transitions,
        }
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(yaml.dump(config), encoding="utf-8")


    # ── Always-allowed tools ──────────────────────────────────────────

    def test_always_allows_read(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        r = self._hook(tmp_path, "Read")
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_always_allows_taskcreate(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "TaskCreate")
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    # ── Block/allow based on stage ─────────────────────────────────────

    def test_blocks_edit_in_alpha_stage(self, tmp_path):
        import json, subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Edit", {"file_path": "some/file.py"})
        assert r.returncode == 0, f"Edit should emit deny JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"
        data = json.loads(r.stdout)
        assert data["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert data["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_allows_grep_in_alpha_stage(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Grep")
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_read_allowed_when_omitted_from_tools(self, tmp_path):
        """Read is a default read tool — allowed even when omitted from stage.tools."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            stages=[{"name": "locked", "tools": ["Write"], "meta": {"description": "No read in tools"}}],
            transitions=[],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "locked"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "README.md"})
        assert r.returncode == 0, f"Read should be allowed as default read tool, rc={r.returncode}"
        assert "allow" in r.stdout

    def test_read_blocked_by_access_read_deny_when_omitted_from_tools(self, tmp_path):
        """Default read tools still obey access.read.deny."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            stages=[{"name": "locked", "tools": ["Write"],
                     "access": {"read": {"deny": ["secrets/**"]}},
                     "meta": {"description": "No read but access.deny"}}],
            transitions=[],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "locked"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "secrets/key.txt"})
        assert r.returncode == 0, f"Read deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_grep_allowed_when_omitted_from_tools(self, tmp_path):
        """Grep is a default read tool — allowed even when omitted from stage.tools."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            stages=[{"name": "locked", "tools": ["Read"], "meta": {"description": "No grep in tools"}}],
            transitions=[],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "locked"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Grep", {"pattern": "TODO", "path": "."})
        assert r.returncode == 0, f"Grep should be allowed as default read tool, rc={r.returncode}"
        assert "allow" in r.stdout

    def test_allows_write_in_beta_stage(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "beta"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Write", {"file_path": "some/file.py"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    # ── Violation logging ──────────────────────────────────────────────

    def test_violation_logged_under_discovered_root(self, tmp_path):
        import json
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Edit", {"file_path": "some/file.py"})
        assert r.returncode == 0
        viol_path = tmp_path / ".stageflow" / "guard_violations.jsonl"
        assert viol_path.is_file(), f"Expected violation log at {viol_path}"
        lines = viol_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["tool"] == "Edit"
        assert entry["stage"] == "alpha"

    # ── Hook from nested subdirectory ──────────────────────────────────

    def test_hook_from_nested_subdir(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        r = self._hook(nested, "Edit", {"file_path": "some/file.py"})
        assert r.returncode == 0, f"Edit deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_hook_allows_from_nested_subdir(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        r = self._hook(nested, "Grep")
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    # ── No project / bootstrap mode ────────────────────────────────────

    def test_allows_when_no_project(self, tmp_path):
        r = self._hook(tmp_path, "Edit", {"file_path": "some/file.py"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout
        assert "not a StageFlow project" in r.stdout

    def test_allows_when_no_active_run(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        r = self._hook(tmp_path, "Edit", {"file_path": "some/file.py"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout
        assert "no stage set" in r.stdout

    # ── Input error handling ───────────────────────────────────────────

    def test_allows_on_malformed_input(self, tmp_path):
        import subprocess, sys
        r = subprocess.run(
            [sys.executable, "-m", "stageflow", "hook"],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=30,
            input="not valid json {{{",
        )
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    # ── Bash pattern matching ──────────────────────────────────────────

    def test_allows_bash_git_in_alpha(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Bash", {"command": "git status"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_blocks_bash_npm_in_alpha(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Bash", {"command": "npm install"})
        assert r.returncode == 0, f"npm deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    # ── Always-allowed operational commands ────────────────────────────

    def test_always_allows_stageflow_commands(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Bash", {"command": "python -m stageflow status"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_always_allows_registered_stageflow_command(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))

        r = self._hook(tmp_path, "Bash", {"command": "stageflow next"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

        r = self._hook(tmp_path, "PowerShell", {"command": "stageflow.cmd status"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_stageflow_prefix_does_not_allow_other_commands(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))

        r = self._hook(tmp_path, "Bash", {"command": "stageflow-malicious next"})
        assert r.returncode == 0
        assert self._permission_decision(r) == "deny"

    def test_safe_readonly_shell_commands_allowed_without_bash_tool(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            stages=[{"name": "locked", "tools": ["Read"], "meta": {"description": "No Bash"}}],
            transitions=[],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "locked"], capture_output=True, cwd=str(tmp_path))

        for command in [
            "ls",
            "cat README.md",
            "head -n 20 README.md",
            "tail README.md",
            "pwd",
            "echo hello",
            "which python",
            "where stageflow",
            "git status",
            "git diff -- src/app.py",
            "git log --oneline -5",
            "git --no-pager diff",
        ]:
            r = self._hook(tmp_path, "Bash", {"command": command})
            assert r.returncode == 0, r.stderr
            assert self._permission_decision(r) == "allow", command

    def test_safe_readonly_powershell_commands_allowed_without_powershell_tool(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            stages=[{"name": "locked", "tools": ["Read"], "meta": {"description": "No PowerShell"}}],
            transitions=[],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "locked"], capture_output=True, cwd=str(tmp_path))

        for command in ["Get-ChildItem", "Get-Content README.md", "Get-Command stageflow"]:
            r = self._hook(tmp_path, "PowerShell", {"command": command})
            assert r.returncode == 0, r.stderr
            assert self._permission_decision(r) == "allow", command

    def test_safe_readonly_shell_commands_reject_control_syntax(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            stages=[{"name": "locked", "tools": ["Read"], "meta": {"description": "No Bash"}}],
            transitions=[],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "locked"], capture_output=True, cwd=str(tmp_path))

        for command in [
            "cat README.md > out.txt",
            "echo secret > .env",
            "ls && rm -rf .",
            "git diff | cat",
            "echo $(cat .env)",
            "cat README.md; rm README.md",
        ]:
            r = self._hook(tmp_path, "Bash", {"command": command})
            assert r.returncode == 0
            assert self._permission_decision(r) == "deny", command

    def test_unsafe_shell_commands_still_blocked_without_bash_tool(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            stages=[{"name": "locked", "tools": ["Read"], "meta": {"description": "No Bash"}}],
            transitions=[],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "locked"], capture_output=True, cwd=str(tmp_path))

        for command in [
            "mkdir out",
            "rm -rf out",
            "git add .",
            "git commit -m x",
            "pip install fastapi",
            "python -c \"open('x.txt', 'w').write('x')\"",
        ]:
            r = self._hook(tmp_path, "Bash", {"command": command})
            assert r.returncode == 0
            assert self._permission_decision(r) == "deny", command

    # ── Unrestricted stage (empty tools) ───────────────────────────────

    def test_allows_anything_in_unrestricted_stage(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "gamma"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Write", {"file_path": "anything.py"})
        assert r.returncode == 0, r.stderr
        assert "unrestricted" in r.stdout

    # ── Access policy enforcement ─────────────────────────────────────

    @staticmethod
    def _make_access_stages_yaml(yaml_path, access_config, tools=None):
        import yaml
        stage = {
            "name": "secured",
            "tools": ["Read", "Write", "Edit", "Grep", "Glob"] if tools is None else tools,
            "meta": {"description": "Stage with access policy"},
        }
        if access_config is not None:
            stage["access"] = access_config
        config = {
            "stages": [stage],
            "transitions": [],
        }
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(yaml.dump(config), encoding="utf-8")

    def test_access_read_allowed_in_allow_list(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "README.md"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_access_read_blocked_outside_allow_list(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "secret.env"})
        assert r.returncode == 0, f"Read deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_access_read_denied_overrides_allow(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["**"], "deny": ["*.env", "secrets/**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "secrets/db.yaml"})
        assert r.returncode == 0, r.stderr or "blocked"
        assert self._permission_decision(r) == "deny"

    def test_access_read_missing_path_fails_closed(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {})
        assert r.returncode == 0, f"Read deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_access_write_allowed_in_run_scope(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Write", {"file_path": "artifacts/output.txt"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_access_write_blocked_to_source_file(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Write", {"file_path": "stageflow/core/engine.py"})
        assert r.returncode == 0, f"Write deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_access_write_missing_path_fails_closed(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Write", {})
        assert r.returncode == 0, f"Write deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_access_grep_without_path_in_restricted_stage(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Grep", {"pattern": "TODO"})
        assert r.returncode == 0, f"Grep deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_access_grep_allowed_in_allowed_dir(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Grep", {"pattern": "TODO", "path": "artifacts"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_access_glob_denied_in_restricted_dir(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**"], "deny": ["artifacts/secrets/**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Glob", {"pattern": "*.key", "path": "artifacts/secrets"})
        assert r.returncode == 0, f"Glob deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_access_path_escape_blocked(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "../../etc/passwd"})
        assert r.returncode == 0, f"Path escape deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_access_absolute_path_outside_blocked(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["**"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "C:/Windows/System32/config/SAM"})
        assert r.returncode == 0, f"Absolute path deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_access_from_nested_cwd(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["src/**", "*.md"]}},
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        nested = tmp_path / "src" / "components"
        nested.mkdir(parents=True)
        r = self._hook(nested, "Read", {"file_path": "Button.tsx"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_access_old_workflow_no_policy_keeps_behavior(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        subprocess.run([sys.executable, "-m", "stageflow", "start", "alpha"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "stageflow/core/engine.py"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout
        r = self._hook(tmp_path, "Write", {"file_path": "any_file.py"})
        assert r.returncode == 0, "Write deny should emit JSON with rc=0"

    def test_access_notebook_edit_respects_write_policy(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
            tools=["Read", "Write", "NotebookEdit"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "NotebookEdit", {"notebook_path": "artifacts/notes.ipynb"})
        assert r.returncode == 0, r.stderr

    def test_access_notebook_edit_blocked_outside(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
            tools=["Read", "Write", "NotebookEdit"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "NotebookEdit", {"notebook_path": "scripts/bad.ipynb"})
        assert r.returncode == 0, f"NotebookEdit deny should emit JSON with rc=0, got rc={r.returncode}"

    def test_access_edit_respects_write_policy(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
            tools=["Read", "Edit"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Edit", {"file_path": "artifacts/file.txt"})
        assert r.returncode == 0, r.stderr
        r = self._hook(tmp_path, "Edit", {"file_path": "stageflow/core/engine.py"})
        assert r.returncode == 0, f"Edit deny should emit JSON with rc=0, got rc={r.returncode}"

    def test_access_multiedit_respects_write_policy(self, tmp_path):
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
            tools=["Read", "MultiEdit"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "MultiEdit", {"file_path": "artifacts/file.txt", "edits": []})
        assert r.returncode == 0, r.stderr
        r = self._hook(tmp_path, "MultiEdit", {"file_path": "stageflow/core/engine.py", "edits": []})
        assert r.returncode == 0, f"MultiEdit deny should emit JSON with rc=0, got rc={r.returncode}"

    def test_access_unrestricted_stage_with_read_policy(self, tmp_path):
        """Unrestricted tools (empty list) with access policy still enforces access."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**"]}},
            tools=[],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "secret.env"})
        assert r.returncode == 0, f"Read deny should emit JSON with rc=0, got rc={r.returncode}"
        r = self._hook(tmp_path, "Read", {"file_path": "artifacts/data.txt"})
        assert r.returncode == 0, r.stderr

    # ── Default read tools (Phase 42) ──────────────────────────────────

    def test_glob_allowed_when_omitted_from_tools(self, tmp_path):
        """Glob is a default read tool — allowed even when omitted from stage.tools."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            stages=[{"name": "locked", "tools": ["Read"], "meta": {"description": "No glob"}}],
            transitions=[],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "locked"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Glob", {"pattern": "**/*.py"})
        assert r.returncode == 0, f"Glob should be allowed as default read tool, rc={r.returncode}"
        assert "allow" in r.stdout

    def test_read_blocked_by_access_read_allow_when_omitted(self, tmp_path):
        """Read omitted from tools, access.read.allow restricts → blocked outside allow."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"]}},
            tools=["Write"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "secret.env"})
        assert r.returncode == 0, f"Read deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_read_allowed_by_access_read_allow_when_omitted(self, tmp_path):
        """Read omitted from tools, access.read.allow → allowed inside allow list."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"]}},
            tools=["Write"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Read", {"file_path": "artifacts/data.txt"})
        assert r.returncode == 0, f"Read inside allow list should be allowed: {r.stderr}"
        assert "allow" in r.stdout

    def test_grep_blocked_by_access_read_deny_dir_when_omitted(self, tmp_path):
        """Grep omitted from tools, access.read.deny covers dir → blocked."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"deny": ["secrets/**", "*.env"]}},
            tools=["Write"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Grep", {"pattern": "KEY", "path": "secrets"})
        assert r.returncode == 0, f"Grep deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_grep_blocked_by_missing_search_root_when_omitted(self, tmp_path):
        """Grep omitted from tools, access.read policy, no path → fail closed."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**"]}},
            tools=["Write"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Grep", {"pattern": "TODO"})
        assert r.returncode == 0, f"Grep deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_grep_blocked_by_dir_not_in_allow_when_omitted(self, tmp_path):
        """Grep omitted from tools, access.read.allow restricts → dir outside blocked."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"]}},
            tools=["Write"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Grep", {"pattern": "TODO", "path": "stageflow"})
        assert r.returncode == 0, f"Grep deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_glob_blocked_by_access_read_deny_when_omitted(self, tmp_path):
        """Glob omitted from tools, access.read.deny → blocked for denied path."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"deny": ["secrets/**", "*.env"]}},
            tools=["Write"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Glob", {"pattern": "**/*.key", "path": "secrets"})
        assert r.returncode == 0, f"Glob deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_write_blocked_when_omitted_even_if_path_allowed(self, tmp_path):
        """Write omitted from tools → blocked even when access.write would allow."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
            tools=["Read"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Write", {"file_path": "artifacts/output.txt"})
        assert r.returncode == 0, f"Write deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_edit_blocked_when_omitted_even_if_path_allowed(self, tmp_path):
        """Edit omitted from tools → blocked even when access.write would allow."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
            tools=["Read", "Write"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Edit", {"file_path": "artifacts/output.txt"})
        assert r.returncode == 0, f"Edit deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_multiedit_blocked_when_omitted_even_if_path_allowed(self, tmp_path):
        """MultiEdit omitted from tools → blocked even when access.write would allow."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
            tools=["Read", "Write", "Edit"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "MultiEdit", {"file_path": "artifacts/output.txt", "edits": []})
        assert r.returncode == 0, f"MultiEdit deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_notebook_edit_blocked_when_omitted_even_if_path_allowed(self, tmp_path):
        """NotebookEdit omitted from tools → blocked even when access.write would allow."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
            tools=["Read", "Write", "Edit"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "NotebookEdit", {"notebook_path": "artifacts/notes.ipynb"})
        assert r.returncode == 0, f"NotebookEdit deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"

    def test_write_in_tools_still_obeys_access_write(self, tmp_path):
        """Write in stage.tools + access.write blocks path outside allow."""
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "stageflow", "init"], capture_output=True, cwd=str(tmp_path))
        self._make_access_stages_yaml(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
            tools=["Read", "Write"],
        )
        subprocess.run([sys.executable, "-m", "stageflow", "start", "secured"], capture_output=True, cwd=str(tmp_path))
        r = self._hook(tmp_path, "Write", {"file_path": "stageflow/core/engine.py"})
        assert r.returncode == 0, f"Write deny should emit JSON with rc=0, got rc={r.returncode}"
        assert self._permission_decision(r) == "deny"


class TestLegacyCompatibility:
    """CLI commands work against legacy projects (stageflow/config/stages.yaml + .claude/current_stage.json)."""

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    @staticmethod
    def _make_legacy_project(root):
        """Create a legacy project with custom stages."""
        import yaml, json
        config_dir = root / "stageflow" / "config"
        config_dir.mkdir(parents=True)
        yaml_path = config_dir / "stages.yaml"
        yaml_path.write_text(yaml.dump({
            "stages": [
                {"name": "alpha", "tools": ["Read", "Bash(git *)"], "meta": {"description": "First"}},
                {"name": "beta", "tools": ["Read", "Edit", "Write"], "meta": {"description": "Second"}},
                {"name": "gamma", "tools": [], "meta": {"description": "Terminal"}},
            ],
            "transitions": [
                {"from": "alpha", "to": "beta", "conditions": [{"always": True}]},
                {"from": "beta", "to": "gamma", "conditions": [{"always": True}]},
            ],
        }), encoding="utf-8")
        state_dir = root / ".claude"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "current_stage.json"
        state_path.write_text(json.dumps({
            "current_stage": None, "history": [], "retry_count": {},
            "iterations": {}, "variables": {}, "paused": False, "paused_reason": "",
        }))
        (root / "artifacts" / "runs").mkdir(parents=True)

    # ── Basic commands ──────────────────────────────────────────────────

    def test_legacy_status_works(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        r = self._run(tmp_path, "status")
        assert r.returncode == 0, r.stderr
        assert "alpha" in r.stdout

    def test_legacy_status_json_works(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        r = self._run(tmp_path, "status", "--json")
        assert r.returncode == 0, r.stderr
        import json
        data = json.loads(r.stdout)
        assert data["current_stage"] == "alpha"

    def test_legacy_start_works(self, tmp_path):
        self._make_legacy_project(tmp_path)
        r = self._run(tmp_path, "start", "alpha")
        assert r.returncode == 0, r.stderr
        state = tmp_path / ".claude" / "current_stage.json"
        import json
        data = json.loads(state.read_text())
        assert data["current_stage"] == "alpha"
        assert "run_id" in data.get("variables", {})

    def test_legacy_next_works(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        r = self._run(tmp_path, "next")
        assert r.returncode == 0, r.stderr
        state = tmp_path / ".claude" / "current_stage.json"
        import json
        data = json.loads(state.read_text())
        assert data["current_stage"] == "beta"

    def test_legacy_check_works(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        r = self._run(tmp_path, "check", "beta")
        assert r.returncode == 0, r.stderr
        assert "ALLOWED" in r.stdout

    def test_legacy_reset_works(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        r = self._run(tmp_path, "reset")
        assert r.returncode == 0, r.stderr
        assert "StageFlow state cleared" in r.stdout

    def test_legacy_list_works(self, tmp_path):
        self._make_legacy_project(tmp_path)
        r = self._run(tmp_path, "list")
        assert r.returncode == 0, r.stderr
        assert "alpha" in r.stdout
        assert "beta" in r.stdout
        assert "gamma" in r.stdout

    def test_legacy_graph_works(self, tmp_path):
        self._make_legacy_project(tmp_path)
        r = self._run(tmp_path, "graph")
        assert r.returncode == 0, r.stderr
        assert "flowchart TD" in r.stdout

    def test_legacy_state_writes_to_claude_dir(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        assert (tmp_path / ".claude" / "current_stage.json").is_file()
        assert not (tmp_path / ".stageflow" / "current_stage.json").exists()

    # ── Nested directory ────────────────────────────────────────────────

    def test_legacy_status_from_nested_subdir(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        r = self._run(nested, "status")
        assert r.returncode == 0, r.stderr
        assert "alpha" in r.stdout

    # ── Migration ───────────────────────────────────────────────────────

    def test_migrate_converts_legacy_to_new(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        r = self._run(tmp_path, "migrate")
        assert r.returncode == 0, r.stderr
        assert "Migrated" in r.stdout
        assert (tmp_path / ".stageflow" / "config" / "stages.yaml").is_file()
        assert (tmp_path / ".stageflow" / "current_stage.json").is_file()
        import json
        new_state = json.loads((tmp_path / ".stageflow" / "current_stage.json").read_text())
        assert new_state["current_stage"] == "alpha"

    def test_migrate_preserves_run_id(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        import json
        old_state = json.loads((tmp_path / ".claude" / "current_stage.json").read_text())
        old_run_id = old_state["variables"]["run_id"]
        self._run(tmp_path, "migrate")
        new_state = json.loads((tmp_path / ".stageflow" / "current_stage.json").read_text())
        assert new_state["variables"]["run_id"] == old_run_id

    def test_migrate_does_not_delete_old_files(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "migrate")
        assert (tmp_path / "stageflow" / "config" / "stages.yaml").is_file()
        assert (tmp_path / ".claude" / "current_stage.json").is_file()

    def test_migrate_idempotent_detects_new_style(self, tmp_path):
        self._make_legacy_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "migrate")
        r = self._run(tmp_path, "migrate")
        assert r.returncode == 0, r.stderr
        assert "Already a new-style project" in r.stdout

    def test_migrate_outside_project_fails(self, tmp_path):
        r = self._run(tmp_path, "migrate")
        assert r.returncode == 1
        assert "Not a StageFlow project" in r.stderr


class TestMixedMarkerPrecedence:
    """When both .stageflow/ and legacy markers exist, .stageflow/ wins."""

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    def test_new_marker_wins_over_legacy(self, tmp_path):
        import yaml, json

        # Create legacy project with stage "legacy_stage"
        (tmp_path / "stageflow" / "config").mkdir(parents=True)
        legacy_config = {
            "stages": [
                {"name": "legacy_stage", "tools": ["Read"], "meta": {"description": "Legacy"}},
            ],
            "transitions": [],
        }
        (tmp_path / "stageflow" / "config" / "stages.yaml").write_text(
            yaml.dump(legacy_config), encoding="utf-8")
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "current_stage.json").write_text(json.dumps({
            "current_stage": "legacy_stage", "history": [], "retry_count": {},
            "iterations": {}, "variables": {}, "paused": False, "paused_reason": "",
        }))

        # Now run init which creates .stageflow/
        self._run(tmp_path, "init")
        self._run(tmp_path, "start", "pick")

        r = self._run(tmp_path, "status")
        assert r.returncode == 0, r.stderr
        assert "pick" in r.stdout
        assert "legacy_stage" not in r.stdout

    def test_legacy_state_only_beats_nothing(self, tmp_path):
        import json
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "current_stage.json").write_text(json.dumps({
            "current_stage": "analyze", "history": [], "retry_count": {},
            "iterations": {}, "variables": {"run_id": "test-run-id"},
            "paused": False, "paused_reason": "",
        }))

        r = self._run(tmp_path, "status")
        assert r.returncode == 0, r.stderr
        assert "analyze" in r.stdout

    def test_legacy_state_only_next_fails_without_config(self, tmp_path):
        import json
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "current_stage.json").write_text(json.dumps({
            "current_stage": "analyze", "history": [], "retry_count": {},
            "iterations": {}, "variables": {"run_id": "test-run-id"},
            "paused": False, "paused_reason": "",
        }))

        r = self._run(tmp_path, "next")
        assert r.returncode == 1


class TestCLISmoke:
    """Focused smoke tests with custom stage names — verifies the simplest happy path."""

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    CUSTOM_YAML = {
        "stages": [
            {"name": "alpha", "tools": ["Read", "Grep"], "meta": {"description": "Investigation"}},
            {"name": "beta", "tools": ["Read", "Edit", "Write"], "meta": {"description": "Implementation"}},
            {"name": "gamma", "tools": [], "meta": {"description": "Terminal"}},
        ],
        "transitions": [
            {"from": "alpha", "to": "beta", "conditions": [{"always": True}]},
            {"from": "beta", "to": "gamma", "conditions": [{"always": True}]},
        ],
    }

    @staticmethod
    def _write_custom_yaml(yaml_path):
        import yaml
        yaml_path.write_text(yaml.dump(TestCLISmoke.CUSTOM_YAML), encoding="utf-8")

    def test_init_creates_expected_files(self, tmp_path):
        self._run(tmp_path, "init")
        assert (tmp_path / ".stageflow" / "config" / "stages.yaml").is_file()
        assert (tmp_path / ".claude" / "settings.json").is_file()
        assert (tmp_path / "artifacts" / "runs").is_dir()
        assert not (tmp_path / ".stageflow" / "current_stage.json").exists()
        assert not (tmp_path / ".claude" / "current_stage.json").exists()

    def test_init_start_creates_state_with_run_id(self, tmp_path):
        import json
        self._run(tmp_path, "init")
        self._write_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start")
        state = tmp_path / ".stageflow" / "current_stage.json"
        assert state.is_file()
        data = json.loads(state.read_text())
        assert data["current_stage"] == "alpha"
        assert "run_id" in data.get("variables", {})

    def test_status_shows_custom_stage_name(self, tmp_path):
        self._run(tmp_path, "init")
        self._write_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "beta")
        r = self._run(tmp_path, "status")
        assert r.returncode == 0
        assert "beta" in r.stdout

    def test_list_shows_custom_stages_not_default(self, tmp_path):
        self._run(tmp_path, "init")
        self._write_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        r = self._run(tmp_path, "list")
        assert r.returncode == 0
        assert "alpha" in r.stdout
        assert "beta" in r.stdout
        assert "gamma" in r.stdout
        assert "pick" not in r.stdout

    def test_next_dry_run_allowed(self, tmp_path):
        self._run(tmp_path, "init")
        self._write_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        r = self._run(tmp_path, "next", "--dry-run")
        assert r.returncode == 0
        assert "ALLOWED" in r.stdout

    def test_next_advances_to_next_custom_stage(self, tmp_path):
        import json
        self._run(tmp_path, "init")
        self._write_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "next")
        state = json.loads((tmp_path / ".stageflow" / "current_stage.json").read_text())
        assert state["current_stage"] == "beta"

    def test_no_legacy_state_file_created(self, tmp_path):
        self._run(tmp_path, "init")
        self._write_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "next")
        assert not (tmp_path / ".claude" / "current_stage.json").exists()

    def test_start_unknown_stage_fails(self, tmp_path):
        self._run(tmp_path, "init")
        self._write_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        r = self._run(tmp_path, "start", "nonexistent_xyz")
        assert r.returncode != 0

    def test_next_without_run_fails_with_guidance(self, tmp_path):
        self._run(tmp_path, "init")
        self._write_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        r = self._run(tmp_path, "next")
        assert r.returncode != 0
        assert "No active run" in r.stderr

    def test_outside_project_fails(self, tmp_path):
        r = self._run(tmp_path, "status")
        assert r.returncode != 0
        assert "Not a StageFlow project" in r.stderr

    def test_package_source_isolation(self, tmp_path):
        import os
        pkg_stageflow = os.path.join(os.path.dirname(__file__), "..", ".stageflow")
        pkg_claude_state = os.path.join(os.path.dirname(__file__), "..", ".claude", "current_stage.json")
        before_sf = os.path.isdir(pkg_stageflow)
        before_claude = os.path.exists(pkg_claude_state)

        self._run(tmp_path, "init")
        self._write_custom_yaml(tmp_path / ".stageflow" / "config" / "stages.yaml")
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "next")
        self._run(tmp_path, "reset")
        self._run(tmp_path, "start", "beta")
        self._run(tmp_path, "next")

        assert os.path.isdir(pkg_stageflow) == before_sf
        assert os.path.exists(pkg_claude_state) == before_claude


class TestMultiRepoIsolation:
    """Two independent projects side by side — commands from one don't affect the other."""

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    @classmethod
    def _init(cls, project_dir, stages_config):
        """Create directory, run init, write custom YAML."""
        project_dir.mkdir(parents=True, exist_ok=True)
        cls._run(project_dir, "init")
        cls._write_yaml(project_dir / ".stageflow" / "config" / "stages.yaml", stages_config)

    STAGES_A = {
        "stages": [
            {"name": "alpha", "tools": ["Read"], "meta": {"description": "Repo A first"}},
            {"name": "beta", "tools": ["Write"], "meta": {"description": "Repo A second"}},
        ],
        "transitions": [
            {"from": "alpha", "to": "beta", "conditions": [{"always": True}]},
        ],
    }

    STAGES_B = {
        "stages": [
            {"name": "uno", "tools": ["Read"], "meta": {"description": "Repo B first"}},
            {"name": "dos", "tools": ["Write"], "meta": {"description": "Repo B second"}},
        ],
        "transitions": [
            {"from": "uno", "to": "dos", "conditions": [{"always": True}]},
        ],
    }

    @staticmethod
    def _write_yaml(path, config):
        import yaml
        path.write_text(yaml.dump(config), encoding="utf-8")

    @staticmethod
    def _read_state(project_dir):
        import json
        return json.loads(
            (project_dir / ".stageflow" / "current_stage.json").read_text()
        )

    # ── two projects, commands from each deep subdir ──

    def test_repo_a_deep_nested_touches_only_repo_a(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)
        self._run(repo_a, "start", "alpha")
        self._run(repo_b, "start", "uno")

        deep = repo_a / "src" / "lib" / "deep"
        deep.mkdir(parents=True)

        r = self._run(deep, "status")
        assert r.returncode == 0, r.stderr
        assert "alpha" in r.stdout

        self._run(deep, "next")
        a_state = self._read_state(repo_a)
        assert a_state["current_stage"] == "beta"

        b_state = self._read_state(repo_b)
        assert b_state["current_stage"] == "uno"

        assert not (deep / ".stageflow").exists()
        assert not (deep / ".claude").exists()

    def test_repo_b_deep_nested_touches_only_repo_b(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)
        self._run(repo_a, "start", "alpha")
        self._run(repo_b, "start", "uno")

        deep = repo_b / "apps" / "nested" / "deep"
        deep.mkdir(parents=True)

        r = self._run(deep, "status")
        assert r.returncode == 0, r.stderr
        assert "uno" in r.stdout

        self._run(deep, "next")
        b_state = self._read_state(repo_b)
        assert b_state["current_stage"] == "dos"

        a_state = self._read_state(repo_a)
        assert a_state["current_stage"] == "alpha"

        assert not (deep / ".stageflow").exists()
        assert not (deep / ".claude").exists()

    def test_reset_in_repo_a_does_not_affect_repo_b(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)
        self._run(repo_a, "start", "alpha")
        self._run(repo_b, "start", "uno")

        deep = repo_a / "src" / "deep"
        deep.mkdir(parents=True)
        r = self._run(deep, "reset")
        assert r.returncode == 0, r.stderr

        assert not (repo_a / ".stageflow" / "current_stage.json").exists()
        b_state = self._read_state(repo_b)
        assert b_state["current_stage"] == "uno"

    def test_start_from_nested_in_repo_a_after_reset(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)
        self._run(repo_b, "start", "uno")

        self._run(repo_a, "reset")
        deep = repo_a / "packages" / "core"
        deep.mkdir(parents=True)
        r = self._run(deep, "start", "beta")
        assert r.returncode == 0, r.stderr

        a_state = self._read_state(repo_a)
        assert a_state["current_stage"] == "beta"
        b_state = self._read_state(repo_b)
        assert b_state["current_stage"] == "uno"

    def test_outside_both_projects_fails(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)

        nowhere = tmp_path / "random_dir"
        nowhere.mkdir()
        r = self._run(nowhere, "status")
        assert r.returncode == 1
        assert "Not a StageFlow project" in r.stderr

        deep = nowhere / "x" / "y" / "z"
        deep.mkdir(parents=True)
        r2 = self._run(deep, "next")
        assert r2.returncode == 1
        assert "Not a StageFlow project" in r2.stderr

    def test_package_source_not_mutated(self, tmp_path):
        import os
        tests_dir = os.path.dirname(__file__)
        pkg_root = os.path.join(tests_dir, "..")
        pkg_state = os.path.join(pkg_root, ".claude", "current_stage.json")
        pkg_stageflow = os.path.join(pkg_root, ".stageflow")

        before_state = os.path.exists(pkg_state)
        before_sf = os.path.isdir(pkg_stageflow)

        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)
        self._run(repo_a, "start", "alpha")
        self._run(repo_b, "start", "uno")

        deep_a = repo_a / "src" / "deep"
        deep_a.mkdir(parents=True)
        self._run(deep_a, "next")
        self._run(deep_a, "status")
        self._run(deep_a, "list")

        deep_b = repo_b / "lib" / "nested"
        deep_b.mkdir(parents=True)
        self._run(deep_b, "next")
        self._run(deep_b, "status")

        self._run(repo_a, "reset")
        self._run(repo_b, "reset")

        assert os.path.exists(pkg_state) == before_state, \
            "Package .claude/current_stage.json was mutated"
        assert os.path.isdir(pkg_stageflow) == before_sf, \
            "Package .stageflow/ was mutated"

    def test_multi_repo_status_json_from_nested(self, tmp_path):
        import json
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)
        self._run(repo_a, "start", "alpha")
        self._run(repo_b, "start", "dos")

        deep_a = repo_a / "src" / "deep"
        deep_a.mkdir(parents=True)
        r1 = self._run(deep_a, "status", "--json")
        assert r1.returncode == 0
        data1 = json.loads(r1.stdout)
        assert data1["current_stage"] == "alpha"

        deep_b = repo_b / "apps" / "sub"
        deep_b.mkdir(parents=True)
        r2 = self._run(deep_b, "status", "--json")
        assert r2.returncode == 0
        data2 = json.loads(r2.stdout)
        assert data2["current_stage"] == "dos"

    def test_multi_repo_list_shows_correct_project(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)
        self._run(repo_a, "start", "alpha")
        self._run(repo_b, "start", "uno")

        deep_a = repo_a / "a" / "deep"
        deep_a.mkdir(parents=True)
        r1 = self._run(deep_a, "list")
        assert "alpha" in r1.stdout
        assert "beta" in r1.stdout
        assert "uno" not in r1.stdout
        assert "dos" not in r1.stdout

        deep_b = repo_b / "b" / "deep"
        deep_b.mkdir(parents=True)
        r2 = self._run(deep_b, "list")
        assert "uno" in r2.stdout
        assert "dos" in r2.stdout
        assert "alpha" not in r2.stdout
        assert "beta" not in r2.stdout

    def test_next_dry_run_from_each_project(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)
        self._run(repo_a, "start", "alpha")
        self._run(repo_b, "start", "uno")

        deep_a = repo_a / "deep"
        deep_a.mkdir()
        r1 = self._run(deep_a, "next", "--dry-run")
        assert r1.returncode == 0
        assert "ALLOWED" in r1.stdout

        deep_b = repo_b / "deep"
        deep_b.mkdir()
        r2 = self._run(deep_b, "next", "--dry-run")
        assert r2.returncode == 0
        assert "ALLOWED" in r2.stdout

        assert self._read_state(repo_a)["current_stage"] == "alpha"
        assert self._read_state(repo_b)["current_stage"] == "uno"

    def test_no_legacy_state_file_in_either_repo(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        self._init(repo_a, self.STAGES_A)
        self._init(repo_b, self.STAGES_B)
        self._run(repo_a, "start", "alpha")
        self._run(repo_b, "start", "uno")
        self._run(repo_a, "next")
        self._run(repo_b, "next")

        assert not (repo_a / ".claude" / "current_stage.json").exists()
        assert not (repo_b / ".claude" / "current_stage.json").exists()


class TestAIWorkflowE2E:
    """End-to-end AI-style workflow tests with progressively harder scenarios.

    Uses a custom 4-stage YAML with artifact-based transitions. Stage names
    are deliberately different from the built-in example workflow.

    Scenarios (each is a separate test, increasing in difficulty):
      (1) bootstrap a fresh repo and start at the first custom stage
      (2) create current-run artifacts and advance through two custom stages
      (3) resume from a nested directory in a new Python process, same run_id
      (4) assert stale artifacts from an old run do not unlock a new run
      (5) assert the global hook command blocks/permits based on discovered root
    """

    AI_STAGES = {
        "stages": [
            {"name": "investigate", "tools": ["Read", "Grep", "Glob", "WebSearch"],
             "meta": {"description": "Investigation phase"}},
            {"name": "implement", "tools": ["Read", "Edit", "Write"],
             "meta": {"description": "Implementation phase"}},
            {"name": "verify", "tools": ["Read"],
             "meta": {"description": "Verification phase — read-only"}},
            {"name": "deliver", "tools": [],
             "meta": {"description": "Delivery complete"}},
        ],
        "transitions": [
            {"from": "investigate", "to": "implement", "conditions": [
                {"file_exists": "artifacts/runs/{{var.run_id}}/investigate/findings.md"}
            ]},
            {"from": "implement", "to": "verify", "conditions": [
                {"file_exists": "artifacts/runs/{{var.run_id}}/implement/patch.diff"}
            ]},
            {"from": "verify", "to": "deliver", "conditions": [
                {"file_exists": "artifacts/runs/{{var.run_id}}/verify/test_report.md"}
            ]},
        ],
    }

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    @staticmethod
    def _run_hook(cwd, stdin_str):
        """Run stageflow hook with stdin input."""
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", "hook"],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
            input=stdin_str,
        )

    @staticmethod
    def _write_yaml(path, config):
        import yaml
        path.write_text(yaml.dump(config), encoding="utf-8")

    @staticmethod
    def _read_state(project_dir):
        import json
        return json.loads(
            (project_dir / ".stageflow" / "current_stage.json").read_text()
        )

    @staticmethod
    def _get_run_id(project_dir):
        return TestAIWorkflowE2E._read_state(project_dir)["variables"]["run_id"]

    def _init_project(self, project_dir):
        project_dir.mkdir(parents=True, exist_ok=True)
        self._run(project_dir, "init")
        self._write_yaml(
            project_dir / ".stageflow" / "config" / "stages.yaml", self.AI_STAGES
        )

    # ── scenario (1): bootstrap fresh repo and start at first custom stage ──

    def test_bootstrap_and_start_first_stage(self, tmp_path):
        """Init a fresh repo, write custom YAML, start at first stage."""
        import json
        self._init_project(tmp_path)

        r = self._run(tmp_path, "start")
        assert r.returncode == 0, r.stderr

        state = self._read_state(tmp_path)
        assert state["current_stage"] == "investigate", \
            f"Expected 'investigate' as first stage, got {state['current_stage']}"
        assert "run_id" in state.get("variables", {}), "Missing run_id"
        assert len(state["variables"]["run_id"]) == 36  # UUID4

        # Verify state file location
        assert (tmp_path / ".stageflow" / "current_stage.json").is_file()

    def test_start_specific_stage(self, tmp_path):
        """Start at a named custom stage, not just the first."""
        self._init_project(tmp_path)
        r = self._run(tmp_path, "start", "implement")
        assert r.returncode == 0, r.stderr
        state = self._read_state(tmp_path)
        assert state["current_stage"] == "implement"

    # ── scenario (2): create artifacts and advance through two custom stages ──

    def test_advance_through_two_stages_with_artifacts(self, tmp_path):
        """Create investigation artifact → advance to implement,
        create implementation artifact → advance to verify."""
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "investigate")

        run_id = self._get_run_id(tmp_path)
        investigate_dir = tmp_path / "artifacts" / "runs" / run_id / "investigate"
        investigate_dir.mkdir(parents=True)
        (investigate_dir / "findings.md").write_text("## Root Cause\nBug found in parser.\n", encoding="utf-8")

        # Advance: investigate → implement
        r = self._run(tmp_path, "next")
        assert r.returncode == 0, f"next failed: {r.stderr}"
        state = self._read_state(tmp_path)
        assert state["current_stage"] == "implement", \
            f"Expected 'implement', got {state['current_stage']}"

        # Create implement artifact
        impl_dir = tmp_path / "artifacts" / "runs" / run_id / "implement"
        impl_dir.mkdir(parents=True)
        (impl_dir / "patch.diff").write_text("@@ -1,3 +1,4 @@\n fix parser\n", encoding="utf-8")

        # Advance: implement → verify
        r2 = self._run(tmp_path, "next")
        assert r2.returncode == 0, f"next failed: {r2.stderr}"
        state2 = self._read_state(tmp_path)
        assert state2["current_stage"] == "verify", \
            f"Expected 'verify', got {state2['current_stage']}"

    def test_transition_blocked_without_artifact(self, tmp_path):
        """Next fails when required artifact doesn't exist."""
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "investigate")

        # No artifact created — should fail
        r = self._run(tmp_path, "next")
        assert r.returncode != 0, "Expected next to fail without artifact"
        state = self._read_state(tmp_path)
        assert state["current_stage"] == "investigate", "Stage should not have changed"

    def test_full_pipeline_investigate_to_deliver(self, tmp_path):
        """Advance through all 4 stages by creating all required artifacts."""
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "investigate")
        run_id = self._get_run_id(tmp_path)
        base = tmp_path / "artifacts" / "runs" / run_id

        # investigate → implement
        (base / "investigate").mkdir(parents=True)
        (base / "investigate" / "findings.md").write_text("# Findings\nDone.\n", encoding="utf-8")
        self._run(tmp_path, "next")

        # implement → verify
        (base / "implement").mkdir(parents=True)
        (base / "implement" / "patch.diff").write_text("diff content\n", encoding="utf-8")
        self._run(tmp_path, "next")

        # verify → deliver
        (base / "verify").mkdir(parents=True)
        (base / "verify" / "test_report.md").write_text("# All tests passed\n", encoding="utf-8")
        self._run(tmp_path, "next")

        state = self._read_state(tmp_path)
        assert state["current_stage"] == "deliver", \
            f"Expected 'deliver', got {state['current_stage']}"

    # ── scenario (3): resume from nested subdir in new process, same run_id ──

    def test_resume_from_nested_subdir_in_new_process(self, tmp_path):
        """Start a run, then from a new Python process in a nested subdir,
        verify the same run_id and continue advancing."""
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "investigate")
        run_id = self._get_run_id(tmp_path)

        # Create investigate artifact
        inv_dir = tmp_path / "artifacts" / "runs" / run_id / "investigate"
        inv_dir.mkdir(parents=True)
        (inv_dir / "findings.md").write_text("# Found it\n", encoding="utf-8")

        # Advance to implement from root
        self._run(tmp_path, "next")

        # Now simulate "resume" — a new process checks state from nested dir
        nested = tmp_path / "src" / "module" / "deep"
        nested.mkdir(parents=True)
        import json
        r = self._run(nested, "status", "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["current_stage"] == "implement"
        assert data["variables"]["run_id"] == run_id

        # Create implement artifact from the nested dir
        impl_dir = tmp_path / "artifacts" / "runs" / run_id / "implement"
        impl_dir.mkdir(parents=True)
        (impl_dir / "patch.diff").write_text("patch\n", encoding="utf-8")

        # Advance from nested dir
        r2 = self._run(nested, "next")
        assert r2.returncode == 0, f"next failed: {r2.stderr}"
        state = self._read_state(tmp_path)
        assert state["current_stage"] == "verify"

    # ── scenario (4): stale artifacts from old run don't unlock new run ──

    def test_stale_artifacts_dont_unlock_new_run(self, tmp_path):
        """Old run's artifacts should not satisfy conditions for a new run."""
        self._init_project(tmp_path)

        # First run — create artifacts and advance
        self._run(tmp_path, "start", "investigate")
        run_id_1 = self._get_run_id(tmp_path)
        inv_dir = tmp_path / "artifacts" / "runs" / run_id_1 / "investigate"
        inv_dir.mkdir(parents=True)
        (inv_dir / "findings.md").write_text("# First run\n", encoding="utf-8")
        self._run(tmp_path, "next")
        assert self._read_state(tmp_path)["current_stage"] == "implement"

        # Reset and start a NEW run
        self._run(tmp_path, "reset")
        assert not (tmp_path / ".stageflow" / "current_stage.json").exists()

        self._run(tmp_path, "start", "investigate")
        run_id_2 = self._get_run_id(tmp_path)
        assert run_id_2 != run_id_1, "New run should have different run_id"

        # Stale artifacts from run_id_1 exist, but conditions use {{var.run_id}}
        # which resolves to run_id_2 — so old artifacts should NOT unlock
        r = self._run(tmp_path, "next")
        assert r.returncode != 0, \
            "Expected next to fail — stale artifacts from old run should not unlock new run"
        state = self._read_state(tmp_path)
        assert state["current_stage"] == "investigate", \
            "Stage should not advance with stale artifacts"

        # But creating artifacts for the CURRENT run_id should work
        inv_dir_2 = tmp_path / "artifacts" / "runs" / run_id_2 / "investigate"
        inv_dir_2.mkdir(parents=True)
        (inv_dir_2 / "findings.md").write_text("# Second run\n", encoding="utf-8")
        r2 = self._run(tmp_path, "next")
        assert r2.returncode == 0, \
            f"Should advance with correct-run artifacts: {r2.stderr}"
        assert self._read_state(tmp_path)["current_stage"] == "implement"

    # ── scenario (5): global hook blocks/permits based on discovered root ──

    def test_hook_permits_allowed_tool_in_investigate(self, tmp_path):
        """Hook should allow Read in investigate stage."""
        import json
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "investigate")

        hook_input = json.dumps({"tool_name": "Read", "tool_input": {}})
        r = self._run_hook(tmp_path, hook_input)
        assert r.returncode == 0, r.stderr
        result = json.loads(r.stdout)
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow", \
            f"Expected allow, got {result}"

    def test_hook_blocks_disallowed_tool_in_investigate(self, tmp_path):
        """Hook should block Edit in investigate stage (only Read/Grep/Glob/WebSearch allowed)."""
        import json
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "investigate")

        hook_input = json.dumps({"tool_name": "Edit", "tool_input": {}})
        r = self._run_hook(tmp_path, hook_input)
        # Blocking emits deny JSON with exit code 0 so Claude Code parses stdout.
        result = json.loads(r.stdout)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_hook_allows_edit_in_implement_stage(self, tmp_path):
        """Hook should allow Edit in implement stage."""
        import json
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "implement")

        hook_input = json.dumps({"tool_name": "Edit", "tool_input": {}})
        r = self._run_hook(tmp_path, hook_input)
        assert r.returncode == 0, r.stderr
        result = json.loads(r.stdout)
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow", \
            f"Expected allow, got {result}"

    def test_hook_from_nested_subdir_uses_discovered_root(self, tmp_path):
        """Hook run from nested subdir should enforce the discovered project's rules."""
        import json
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "investigate")

        nested = tmp_path / "src" / "deep"
        nested.mkdir(parents=True)

        # Edit is disallowed in investigate stage — even from nested dir
        hook_input = json.dumps({"tool_name": "Edit", "tool_input": {}})
        r = self._run_hook(nested, hook_input)
        result = json.loads(r.stdout)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny", \
            f"Expected block from nested dir, got {result}"

        # Read should be allowed
        hook_input2 = json.dumps({"tool_name": "Read", "tool_input": {}})
        r2 = self._run_hook(nested, hook_input2)
        assert r2.returncode == 0, r2.stderr
        result2 = json.loads(r2.stdout)
        assert result2["hookSpecificOutput"]["permissionDecision"] == "allow", \
            f"Expected allow from nested dir, got {result2}"

    def test_hook_allows_everything_in_deliver_stage(self, tmp_path):
        """Deliver stage has empty tools list — everything should be allowed."""
        import json
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "deliver")

        for tool in ["Edit", "Write", "Bash", "PowerShell", "Grep"]:
            hook_input = json.dumps({"tool_name": tool, "tool_input": {}})
            r = self._run_hook(tmp_path, hook_input)
            assert r.returncode == 0, r.stderr
            result = json.loads(r.stdout)
            assert result["hookSpecificOutput"]["permissionDecision"] == "allow", \
                f"Expected allow for {tool} in deliver, got {result}"

    def test_hook_violation_logged(self, tmp_path):
        """Blocked tool calls should be logged to guard_violations.jsonl."""
        import json
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "investigate")

        hook_input = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}})
        self._run_hook(tmp_path, hook_input)
        self._run_hook(tmp_path, hook_input)

        violations_path = tmp_path / ".stageflow" / "guard_violations.jsonl"
        assert violations_path.is_file(), "Violations log should exist"
        lines = violations_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 2, f"Expected at least 2 violations logged, got {len(lines)}"
        for line in lines:
            entry = json.loads(line)
            assert entry["tool"] == "Edit"

    # ── package source isolation ──

    def test_package_source_unchanged(self, tmp_path):
        """Running the full AI workflow in a temp project must not mutate
        the StageFlow package source tree."""
        import os
        tests_dir = os.path.dirname(__file__)
        pkg_root = os.path.join(tests_dir, "..")
        pkg_state = os.path.join(pkg_root, ".claude", "current_stage.json")
        pkg_stageflow = os.path.join(pkg_root, ".stageflow")

        before_state = os.path.exists(pkg_state)
        before_sf = os.path.isdir(pkg_stageflow)

        self._init_project(tmp_path)
        self._run(tmp_path, "start", "investigate")
        run_id = self._get_run_id(tmp_path)
        base = tmp_path / "artifacts" / "runs" / run_id
        (base / "investigate").mkdir(parents=True)
        (base / "investigate" / "findings.md").write_text("# ok\n", encoding="utf-8")
        self._run(tmp_path, "next")
        (base / "implement").mkdir(parents=True)
        (base / "implement" / "patch.diff").write_text("ok\n", encoding="utf-8")
        self._run(tmp_path, "next")
        (base / "verify").mkdir(parents=True)
        (base / "verify" / "test_report.md").write_text("ok\n", encoding="utf-8")
        self._run(tmp_path, "next")
        self._run(tmp_path, "reset")

        assert os.path.exists(pkg_state) == before_state, \
            "Package .claude/current_stage.json was mutated by AI workflow"
        assert os.path.isdir(pkg_stageflow) == before_sf, \
            "Package .stageflow/ was mutated by AI workflow"


class TestRootCommand:
    """Tests for stageflow root — prints discovered project root path."""

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    def test_root_from_project_root(self, tmp_path):
        self._run(tmp_path, "init")
        r = self._run(tmp_path, "root")
        assert r.returncode == 0, r.stderr
        assert "Project root:" in r.stdout
        assert str(tmp_path.resolve()) in r.stdout
        assert "Marker type:" in r.stdout
        assert "new" in r.stdout

    def test_root_from_nested_subdir(self, tmp_path):
        self._run(tmp_path, "init")
        nested = tmp_path / "src" / "lib" / "deep"
        nested.mkdir(parents=True)
        r = self._run(nested, "root")
        assert r.returncode == 0, r.stderr
        assert str(tmp_path.resolve()) in r.stdout

    def test_root_json_output(self, tmp_path):
        import json
        self._run(tmp_path, "init")
        r = self._run(tmp_path, "root", "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["marker_type"] == "new"
        for key in ("root", "config_path", "state_path", "artifacts_dir", "audit_dir"):
            assert key in data, f"Missing key: {key}"

    def test_root_json_short_flag(self, tmp_path):
        import json
        self._run(tmp_path, "init")
        r = self._run(tmp_path, "root", "-j")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["marker_type"] == "new"

    def test_root_outside_project_fails(self, tmp_path):
        r = self._run(tmp_path, "root")
        assert r.returncode == 1
        assert "Not a StageFlow project" in r.stderr

    def test_root_from_legacy_project(self, tmp_path):
        import json
        (tmp_path / "stageflow" / "config").mkdir(parents=True)
        (tmp_path / "stageflow" / "config" / "stages.yaml").write_text(
            "stages: []\ntransitions: []\n", encoding="utf-8"
        )
        r = self._run(tmp_path, "root", "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["marker_type"] == "legacy"

    def test_root_new_beats_legacy_in_same_dir(self, tmp_path):
        import json
        self._run(tmp_path, "init")
        (tmp_path / "stageflow" / "config").mkdir(parents=True)
        (tmp_path / "stageflow" / "config" / "stages.yaml").write_text(
            "stages: []\ntransitions: []\n", encoding="utf-8"
        )
        r = self._run(tmp_path, "root", "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["marker_type"] == "new"

    def test_root_from_nested_outside_project_fails(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        r = self._run(nested, "root")
        assert r.returncode == 1
        assert "Not a StageFlow project" in r.stderr


class TestCLIComplete:
    """Tests for stageflow complete — run completion with custom stage names."""

    COMPLETE_STAGES = {
        "stages": [
            {"name": "alpha", "tools": ["Read"],
             "meta": {"description": "Starting stage"}},
            {"name": "beta", "tools": ["Read", "Edit"],
             "meta": {"description": "Middle stage"}},
            {"name": "gamma", "tools": [],
             "meta": {"description": "Terminal stage"}},
        ],
        "transitions": [
            {"from": "alpha", "to": "beta", "conditions": [{"always": True}]},
            {"from": "beta", "to": "gamma", "conditions": [{"always": True}]},
        ],
    }

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    @staticmethod
    def _write_yaml(path, config):
        import yaml
        path.write_text(yaml.dump(config), encoding="utf-8")

    @staticmethod
    def _read_state(project_dir):
        import json
        return json.loads(
            (project_dir / ".stageflow" / "current_stage.json").read_text()
        )

    def _init_project(self, project_dir):
        project_dir.mkdir(parents=True, exist_ok=True)
        self._run(project_dir, "init")
        self._write_yaml(
            project_dir / ".stageflow" / "config" / "stages.yaml",
            self.COMPLETE_STAGES,
        )

    def test_complete_from_terminal_stage(self, tmp_path):
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "next")  # alpha -> beta
        self._run(tmp_path, "next")  # beta -> gamma
        r = self._run(tmp_path, "complete")
        assert r.returncode == 0, r.stderr
        assert "Run completed" in r.stdout
        state = self._read_state(tmp_path)
        assert state["current_stage"] is None
        assert state["run_status"] == "completed"
        assert state["final_stage"] == "gamma"
        assert "completed_at" in state

    def test_complete_fails_when_no_active_run(self, tmp_path):
        self._init_project(tmp_path)
        r = self._run(tmp_path, "complete")
        assert r.returncode != 0
        assert "No active run" in r.stderr

    def test_complete_fails_from_non_terminal_stage(self, tmp_path):
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        r = self._run(tmp_path, "complete")
        assert r.returncode != 0
        assert "not terminal" in r.stdout or "not terminal" in r.stderr

    def test_complete_outside_project_fails(self, tmp_path):
        r = self._run(tmp_path, "complete")
        assert r.returncode != 0
        assert "Not a StageFlow project" in r.stderr

    def test_complete_rejects_positional_args(self, tmp_path):
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "next")
        self._run(tmp_path, "next")
        r = self._run(tmp_path, "complete", "gamma")
        assert r.returncode != 0

    def test_complete_preserves_run_id(self, tmp_path):
        import json
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        s1 = json.loads(
            (tmp_path / ".stageflow" / "current_stage.json").read_text()
        )
        run_id = s1["variables"]["run_id"]
        self._run(tmp_path, "next")
        self._run(tmp_path, "next")
        self._run(tmp_path, "complete")
        s2 = self._read_state(tmp_path)
        assert s2["variables"]["run_id"] == run_id

    def test_complete_from_nested_subdir(self, tmp_path):
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "next")
        self._run(tmp_path, "next")
        nested = tmp_path / "src" / "deep"
        nested.mkdir(parents=True)
        r = self._run(nested, "complete")
        assert r.returncode == 0, r.stderr
        state = self._read_state(tmp_path)
        assert state["current_stage"] is None
        assert state["final_stage"] == "gamma"

    def test_next_guides_to_complete_at_terminal(self, tmp_path):
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "next")
        self._run(tmp_path, "next")
        r = self._run(tmp_path, "next")
        assert r.returncode != 0
        assert "stageflow complete" in r.stderr

    def test_complete_preserves_history(self, tmp_path):
        self._init_project(tmp_path)
        self._run(tmp_path, "start", "alpha")
        self._run(tmp_path, "next")
        self._run(tmp_path, "next")
        history_before = len(self._read_state(tmp_path).get("history", []))
        self._run(tmp_path, "complete")
        state = self._read_state(tmp_path)
        assert len(state["history"]) == history_before + 1

    def test_multi_repo_complete_isolation(self, tmp_path):
        import json
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        repo_a.mkdir(exist_ok=True)
        repo_b.mkdir(exist_ok=True)
        self._run(repo_a, "init")
        self._write_yaml(
            repo_a / ".stageflow" / "config" / "stages.yaml",
            self.COMPLETE_STAGES,
        )
        self._run(repo_b, "init")
        self._write_yaml(
            repo_b / ".stageflow" / "config" / "stages.yaml",
            {
                "stages": [
                    {"name": "uno", "tools": ["Read"]},
                    {"name": "dos", "tools": []},
                ],
                "transitions": [
                    {"from": "uno", "to": "dos",
                     "conditions": [{"always": True}]},
                ],
            },
        )
        self._run(repo_a, "start", "alpha")
        self._run(repo_a, "next")
        self._run(repo_a, "next")
        self._run(repo_b, "start", "uno")
        self._run(repo_b, "next")

        r = self._run(repo_a, "complete")
        assert r.returncode == 0, r.stderr
        a_state = self._read_state(repo_a)
        assert a_state["current_stage"] is None
        assert a_state["run_status"] == "completed"

        b_state = self._read_state(repo_b)
        assert b_state["current_stage"] == "dos"
        assert "run_status" not in b_state


class TestCLIEditor:
    """Tests for stageflow editor — visual workflow editor command."""

    EDITOR_STAGES = {
        "stages": [
            {"name": "alpha", "tools": ["Read"],
             "meta": {"description": "First stage"}},
            {"name": "beta", "tools": [],
             "meta": {"description": "Terminal stage"}},
        ],
        "transitions": [
            {"from": "alpha", "to": "beta", "conditions": [{"always": True}]},
        ],
    }

    @staticmethod
    def _run(cwd, *args):
        import subprocess, sys
        return subprocess.run(
            [sys.executable, "-m", "stageflow", *args],
            capture_output=True, text=True, cwd=str(cwd), timeout=30,
        )

    @staticmethod
    def _write_yaml(path, config):
        import yaml
        path.write_text(yaml.dump(config), encoding="utf-8")

    def _init_project(self, project_dir):
        project_dir.mkdir(parents=True, exist_ok=True)
        self._run(project_dir, "init")
        self._write_yaml(
            project_dir / ".stageflow" / "config" / "stages.yaml",
            self.EDITOR_STAGES,
        )

    @staticmethod
    def _start_editor(cwd, *extra_args):
        """Start editor as a subprocess, return (proc, output_lines).

        Uses a background thread to read stdout (merged with stderr) so the
        pipe buffer never fills.  Caller must terminate the process.
        """
        import subprocess, sys, threading
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

    @staticmethod
    def _wait_for_output(lines, marker, timeout=15):
        """Poll *lines* (filled by reader thread) until *marker* appears."""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            combined = "".join(lines)
            if marker in combined:
                return combined
            time.sleep(0.1)
        return "".join(lines)

    # ── Help output ───────────────────────────────────────────────────

    def test_editor_help(self):
        """stageflow editor --help shows editor-specific options."""
        r = _stageflow("editor", "--help")
        assert r.returncode == 0, r.stderr
        assert "--host" in r.stdout
        assert "--port" in r.stdout
        assert "--no-open" in r.stdout

    def test_editor_in_main_help(self):
        """stageflow --help lists the editor command."""
        r = _stageflow("--help")
        assert r.returncode == 0, r.stderr
        assert "editor" in r.stdout

    # ── Outside project ───────────────────────────────────────────────

    def test_outside_project_fails(self, tmp_path):
        """stageflow editor outside a project fails with guidance."""
        r = self._run(tmp_path, "editor", "--no-open")
        assert r.returncode != 0
        assert "Not a StageFlow project" in r.stderr

    def test_legacy_project_rejected(self, tmp_path):
        """Editor rejects legacy (non-.stageflow/) projects with migration guidance."""
        import json
        # Create a legacy-style project
        (tmp_path / "stageflow" / "config").mkdir(parents=True)
        import yaml
        (tmp_path / "stageflow" / "config" / "stages.yaml").write_text(
            yaml.dump(self.EDITOR_STAGES), encoding="utf-8"
        )
        (tmp_path / ".claude").mkdir(parents=True)
        (tmp_path / ".claude" / "current_stage.json").write_text(
            json.dumps({"current_stage": None}), encoding="utf-8"
        )
        r = self._run(tmp_path, "editor", "--no-open")
        assert r.returncode != 0, f"Expected non-zero exit, got {r.returncode}"
        assert "migrate" in r.stderr.lower(), f"Expected migration guidance in: {r.stderr}"

    # ── Nested directory root binding ─────────────────────────────────

    def test_nested_directory_shows_correct_root(self, tmp_path):
        """Editor launched from a nested directory binds the ancestor root."""
        import time
        self._init_project(tmp_path)
        nested = tmp_path / "src" / "sub" / "deep"
        nested.mkdir(parents=True)
        proc, lines, thr = self._start_editor(nested, "--port", "8765")
        try:
            output = self._wait_for_output(lines, "Started server process", timeout=15)
            # Terminate once started
            proc.terminate()
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                    proc.wait()
        assert str(tmp_path) in output, f"Missing project root in output:\n{output}"
        assert "Project root" in output, f"Missing 'Project root' in:\n{output}"

    # ── Host / port argument parsing ──────────────────────────────────

    def test_custom_host_port_printed(self, tmp_path):
        """Custom --host and --port appear in the startup banner."""
        import time
        self._init_project(tmp_path)
        proc, lines, thr = self._start_editor(
            tmp_path, "--host", "0.0.0.0", "--port", "9876",
        )
        try:
            output = self._wait_for_output(lines, "0.0.0.0", timeout=15)
            proc.terminate()
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                    proc.wait()
        assert "0.0.0.0" in output, f"Expected 0.0.0.0 in output:\n{output}"
        assert "9876" in output, f"Expected 9876 in output:\n{output}"

    # ── Port busy ─────────────────────────────────────────────────────

    def test_port_busy_fails_cleanly(self, tmp_path):
        """Editor fails when the selected port is busy."""
        import subprocess, sys, socket
        self._init_project(tmp_path)

        # Bind a socket to hold the port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 9877))
        sock.listen(1)

        try:
            r = subprocess.run(
                [sys.executable, "-m", "stageflow", "editor",
                 "--port", "9877", "--no-open"],
                capture_output=True, text=True, cwd=str(tmp_path), timeout=20,
            )
            # uvicorn exits non-zero when the port is in use
            combined = (r.stdout or "") + (r.stderr or "")
            assert r.returncode != 0 or "ERROR" in combined.upper() or "address already in use" in combined.lower(), \
                f"Expected failure on busy port, got rc={r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        finally:
            sock.close()

    # ── Prints project info at startup ────────────────────────────────

    def test_prints_project_info_at_startup(self, tmp_path):
        """Editor prints project root and config path at startup."""
        import time
        self._init_project(tmp_path)
        proc, lines, thr = self._start_editor(tmp_path, "--port", "8766")
        try:
            output = self._wait_for_output(lines, "Project root", timeout=15)
            proc.terminate()
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
                    proc.wait()
        assert "Project root" in output, f"Missing 'Project root' in:\n{output}"
        assert str(tmp_path) in output, f"Missing project path in:\n{output}"
        assert "Config" in output, f"Missing 'Config' in:\n{output}"
        assert "URL" in output, f"Missing 'URL' in:\n{output}"
