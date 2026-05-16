"""Layered file access control verification.

Exercises every layer from raw schema validation up through end-to-end
hook enforcement, increasing difficulty at each step.  Designed so that
a failure at layer N does not prevent investigation of layer N+1.

Layers (Phase 39 task-134):
  1. Schema load       — YAML with access policy is schema-valid
  2. Policy helper     — AccessPolicy.check_read / check_write in isolation
  3. StageGuard check  — programmatic guard enforces access rules
  4. Hook from root    — ``stageflow hook`` enforces access from project root
  5. Hook from nested  — ``stageflow hook`` resolves relative paths against CWD
  6. Win / absolute    — absolute paths & escapes are always blocked
  7. YAML round-trip   — serialise -> parse preserves access fields
  8. No-policy compat  — stages *without* access keep existing behaviour
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


# =============================================================================
# helpers
# =============================================================================

def _hook(cwd, tool_name, tool_input=None):
    hook_input = json.dumps({"tool_name": tool_name, "tool_input": tool_input or {}})
    return subprocess.run(
        [sys.executable, "-m", "stageflow", "hook"],
        capture_output=True, text=True, cwd=str(cwd), timeout=30,
        input=hook_input,
    )


def _write_access_config(path, access_config, tools=None, transitions=None,
                         extra_top=None):
    """Write a minimal stages.yaml with one *secured* stage carrying an access policy."""
    stage = {
        "name": "secured",
        "tools": tools or ["Read", "Write", "Edit", "Grep", "Glob"],
        "meta": {"description": "Stage with access policy"},
    }
    if access_config is not None:
        stage["access"] = access_config
    if extra_top:
        stage.update(extra_top)
    config = {"stages": [stage], "transitions": transitions or []}
    path.write_text(yaml.dump(config, sort_keys=False), encoding="utf-8")


def _init_state(temp_dir, registry, stage="secured"):
    """Create a state file so StageGuard has a current_stage to work with."""
    from stageflow.core.engine import StateMachine
    sm = StateMachine(registry, str(temp_dir))
    sm.initialize(stage)
    return sm


# =============================================================================
# Layer 1 — Schema load
# =============================================================================

class TestLayer1SchemaLoad:
    """YAML with ``access.read`` and ``access.write`` passes schema validation."""

    def test_read_allow_is_valid(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        _write_access_config(
            temp_dir / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"]}},
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        assert stage is not None
        assert stage.extra.get("access", {}).get("read", {}).get("allow") == \
            ["artifacts/**", "*.md"]

    def test_read_allow_and_deny_is_valid(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        _write_access_config(
            temp_dir / "stages.yaml",
            {"read": {"allow": ["**"], "deny": ["*.env", "secrets/**"]}},
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        access = stage.extra.get("access", {})
        assert access.get("read", {}).get("deny") == ["*.env", "secrets/**"]

    def test_write_allow_is_valid(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        _write_access_config(
            temp_dir / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        assert stage.extra.get("access", {}).get("write", {}).get("allow") == \
            ["artifacts/**"]

    def test_both_read_and_write_is_valid(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        _write_access_config(
            temp_dir / "stages.yaml",
            {
                "read": {"allow": ["src/**"]},
                "write": {"allow": ["artifacts/**"]},
            },
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        access = stage.extra.get("access", {})
        assert access.get("read", {}).get("allow") == ["src/**"]
        assert access.get("write", {}).get("allow") == ["artifacts/**"]

    def test_missing_access_has_empty_extra(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        _write_access_config(temp_dir / "stages.yaml", None)
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        assert stage.extra == {}

    def test_access_round_trips_through_to_dict(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        _write_access_config(
            temp_dir / "stages.yaml",
            {"read": {"allow": ["artifacts/**"]}},
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        d = reg.to_dict()
        stage_d = d["stages"][0]
        assert stage_d["access"]["read"]["allow"] == ["artifacts/**"]


# =============================================================================
# Layer 2 — Policy helper (pure AccessPolicy, no registry / state machine)
# =============================================================================

class TestLayer2PolicyHelper:
    """AccessPolicy.check_read / check_write in isolation."""

    def test_read_allowed_in_allow_list(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        (temp_dir / "artifacts").mkdir()
        (temp_dir / "artifacts" / "f.md").write_text("")
        policy = AccessPolicy({"read": {"allow": ["artifacts/**", "*.md"]}})
        ok, reason = policy.check_read("README.md", root)
        assert ok, f"README.md should be allowed, got: {reason}"

    def test_read_blocked_outside_allow_list(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"read": {"allow": ["artifacts/**", "*.md"]}})
        ok, reason = policy.check_read("secret.env", root)
        assert not ok, f"secret.env should be blocked, got: {reason!r}"
        assert "not in allow" in reason

    def test_deny_overrides_allow(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"read": {"allow": ["**"], "deny": ["*.env"]}})
        ok, reason = policy.check_read("config.env", root)
        assert not ok, f".env should be blocked by deny, got: {reason!r}"
        assert "denied" in reason

    def test_write_allowed(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"write": {"allow": ["artifacts/**"]}})
        ok, reason = policy.check_write("artifacts/output.txt", root)
        assert ok, f"Write to artifacts should be allowed, got: {reason}"

    def test_write_blocked(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"write": {"allow": ["artifacts/**"]}})
        ok, reason = policy.check_write("src/main.py", root)
        assert not ok, f"Write to src should be blocked, got: {reason!r}"

    def test_no_policy_allows_everything(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy(None)
        assert policy.check_read("anything.txt", root) == (True, "")
        assert policy.check_write("any/path.py", root) == (True, "")

    def test_empty_policy_allows_everything(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({})
        assert policy.check_read("anything.txt", root) == (True, "")
        assert policy.check_write("any/path.py", root) == (True, "")

    def test_only_deny_allows_unlisted(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"read": {"deny": ["secrets/**"]}})
        ok, _ = policy.check_read("public/file.md", root)
        assert ok, "File outside denylist should be allowed when only deny defined"
        ok2, _ = policy.check_read("secrets/key.pem", root)
        assert not ok2

    def test_variable_interpolation(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"read": {"allow": ["artifacts/runs/{{var.run_id}}/**"]}})
        ok, _ = policy.check_read("artifacts/runs/abc123/report.md", root,
                                  variables={"run_id": "abc123"})
        assert ok, "Interpolated variable should resolve"

    def test_search_root_allowed_under_allow(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"read": {"allow": ["artifacts/**"]}})
        ok, _ = policy.check_search("artifacts", root)
        assert ok, "Search under allowed dir should pass"

    def test_search_root_blocked_when_not_covered(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"read": {"allow": ["artifacts/**"]}})
        ok, reason = policy.check_search("src", root)
        assert not ok, f"Search under unallowed dir should be blocked: {reason!r}"


# =============================================================================
# Layer 3 — StageGuard programmatic check
# =============================================================================

class TestLayer3StageGuard:
    """StageGuard.check() enforces access policy when called in-process."""

    def test_read_allowed(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        from stageflow.core.guard import StageGuard
        _write_access_config(
            temp_dir / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"]}},
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        _init_state(temp_dir, reg)
        guard = StageGuard(
            str(temp_dir / "stages.yaml"), str(temp_dir), registry=reg,
        )
        ok, msg = guard.check("Read", {"file_path": "README.md"})
        assert ok, f"Read README.md should be allowed: {msg}"

    def test_read_blocked(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        from stageflow.core.guard import StageGuard
        _write_access_config(
            temp_dir / "stages.yaml",
            {"read": {"allow": ["artifacts/**"]}},
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        _init_state(temp_dir, reg)
        guard = StageGuard(
            str(temp_dir / "stages.yaml"), str(temp_dir), registry=reg,
        )
        ok, msg = guard.check("Read", {"file_path": "secret.env"})
        assert not ok, f"Read secret.env should be blocked: {msg}"

    def test_write_allowed(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        from stageflow.core.guard import StageGuard
        _write_access_config(
            temp_dir / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        _init_state(temp_dir, reg)
        guard = StageGuard(
            str(temp_dir / "stages.yaml"), str(temp_dir), registry=reg,
        )
        ok, msg = guard.check("Write", {"file_path": "artifacts/output.txt"})
        assert ok, f"Write to artifacts should be allowed: {msg}"

    def test_write_blocked(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        from stageflow.core.guard import StageGuard
        _write_access_config(
            temp_dir / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        _init_state(temp_dir, reg)
        guard = StageGuard(
            str(temp_dir / "stages.yaml"), str(temp_dir), registry=reg,
        )
        ok, msg = guard.check("Write", {"file_path": "src/main.py"})
        assert not ok, f"Write to src should be blocked: {msg}"

    def test_tool_not_in_allowlist_still_blocked(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        from stageflow.core.guard import StageGuard
        _write_access_config(
            temp_dir / "stages.yaml",
            {"read": {"allow": ["**"]}},
            tools=["Read"],
        )
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        _init_state(temp_dir, reg)
        guard = StageGuard(
            str(temp_dir / "stages.yaml"), str(temp_dir), registry=reg,
        )
        ok, msg = guard.check("Write", {"file_path": "artifacts/x.txt"})
        assert not ok, f"Write not in tools should be blocked: {msg}"

    def test_no_policy_uses_tool_allowlist_only(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        from stageflow.core.guard import StageGuard
        _write_access_config(temp_dir / "stages.yaml", None, tools=["Read", "Grep"])
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        _init_state(temp_dir, reg)
        guard = StageGuard(
            str(temp_dir / "stages.yaml"), str(temp_dir), registry=reg,
        )
        ok, _ = guard.check("Read", {"file_path": "any/file.md"})
        assert ok
        ok2, _ = guard.check("Write", {"file_path": "any/file.md"})
        assert not ok2, "Write not in tools should be blocked"


# =============================================================================
# Layer 4 — Hook from project root
# =============================================================================

class TestLayer4HookFromRoot:
    """``stageflow hook`` enforces access when invoked from project root."""

    def test_read_allowed_in_artifacts(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Read", {"file_path": "README.md"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_read_blocked_on_secret(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Read", {"file_path": ".env"})
        assert r.returncode != 0, f"Read of .env should be blocked: {r.stdout}"
        assert "block" in r.stdout

    def test_write_allowed_in_artifacts(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Write", {"file_path": "artifacts/out.txt"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_write_blocked_outside_artifacts(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Write", {"file_path": "src/app.py"})
        assert r.returncode != 0, f"Write to src should be blocked: {r.stdout}"
        assert "block" in r.stdout

    def test_grep_allowed_in_allowed_dir(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Grep", {"pattern": "TODO", "path": "artifacts"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_grep_without_path_blocked(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["artifacts/**"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Grep", {"pattern": "TODO"})
        assert r.returncode != 0, f"Grep without path should be blocked: {r.stdout}"
        assert "block" in r.stdout


# =============================================================================
# Layer 5 — Hook from nested CWD
# =============================================================================

class TestLayer5HookNestedCwd:
    """``stageflow hook`` resolves relative paths against CWD, not project root."""

    def test_relative_path_resolves_from_nested_dir(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["src/**", "*.md"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        nested = tmp_path / "src" / "components"
        nested.mkdir(parents=True)
        r = _hook(nested, "Read", {"file_path": "Button.tsx"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_read_blocked_from_nested_dir_outside_scope(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["src/**"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        nested = tmp_path / "tests"
        nested.mkdir(parents=True)
        r = _hook(nested, "Read", {"file_path": "test_secret.py"})
        assert r.returncode != 0, f"Read from tests/ should be blocked: {r.stdout}"
        assert "block" in r.stdout


# =============================================================================
# Layer 6 — Windows / absolute paths
# =============================================================================

class TestLayer6WindowsAbsolutePaths:
    """Absolute paths and escapes are always denied regardless of policy."""

    def test_path_escape_blocked(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["**"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Read", {"file_path": "../../etc/passwd"})
        assert r.returncode != 0, f"Path escape should be blocked: {r.stdout}"
        assert "block" in r.stdout

    def test_absolute_path_outside_blocked(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        _write_access_config(
            tmp_path / ".stageflow" / "config" / "stages.yaml",
            {"read": {"allow": ["**"]}},
        )
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "secured"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Read", {"file_path": "C:/Windows/System32/config/SAM"})
        assert r.returncode != 0, f"Absolute outside path should be blocked: {r.stdout}"
        assert "block" in r.stdout

    def test_policy_absolute_path_escape(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"read": {"allow": ["**"]}})
        ok, reason = policy.check_read("/etc/passwd", root)
        assert not ok, f"Absolute path should be blocked: {reason!r}"

    def test_policy_relative_escape(self, temp_dir):
        from stageflow.core.access_policy import AccessPolicy
        root = str(temp_dir)
        policy = AccessPolicy({"read": {"allow": ["**"]}})
        ok, reason = policy.check_read("../../etc/passwd", root)
        assert not ok, f"Relative escape should be blocked: {reason!r}"


# =============================================================================
# Layer 7 — YAML round-trip preserves access fields
# =============================================================================

class TestLayer7YamlRoundTrip:
    """Serialise -> parse preserves ``access`` in the Stage ``extra`` field."""

    def test_preserves_read_access(self, temp_dir):
        _write_access_config(
            temp_dir / "stages.yaml",
            {"read": {"allow": ["artifacts/**", "*.md"], "deny": ["*.env"]}},
        )
        from stageflow.core.registry import StageRegistry
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        extra = stage.extra
        access = extra.get("access", {})
        read_policy = access.get("read", {})
        assert read_policy.get("allow") == ["artifacts/**", "*.md"]
        assert read_policy.get("deny") == ["*.env"]

    def test_preserves_write_access(self, temp_dir):
        _write_access_config(
            temp_dir / "stages.yaml",
            {"write": {"allow": ["artifacts/**"]}},
        )
        from stageflow.core.registry import StageRegistry
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        extra = stage.extra
        assert extra.get("access", {}).get("write", {}).get("allow") == ["artifacts/**"]

    def test_preserves_empty_access(self, temp_dir):
        _write_access_config(temp_dir / "stages.yaml", {})
        from stageflow.core.registry import StageRegistry
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        assert stage.extra.get("access") == {}

    def test_preserves_access_with_other_fields(self, temp_dir):
        _write_access_config(
            temp_dir / "stages.yaml",
            {"read": {"allow": ["src/**"]}, "write": {"allow": ["artifacts/**"]}},
            extra_top={"on_enter": [{"shell": "echo start"}],
                       "on_exit": [{"python": "cleanup()"}]},
        )
        from stageflow.core.registry import StageRegistry
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        d = stage.to_dict()
        assert d["on_enter"] == [{"shell": "echo start"}]
        assert d["on_exit"] == [{"python": "cleanup()"}]
        access = d.get("access", {})
        assert access.get("read", {}).get("allow") == ["src/**"]
        assert access.get("write", {}).get("allow") == ["artifacts/**"]

    def test_no_access_in_to_dict_when_no_access(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        _write_access_config(temp_dir / "stages.yaml", None)
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        stage = reg.get_stage("secured")
        assert stage.extra == {}
        d = stage.to_dict()
        assert "access" not in d


# =============================================================================
# Layer 8 — Old-workflow backward compatibility
# =============================================================================

class TestLayer8BackwardCompat:
    """Stages *without* an access policy keep the same behaviour as before."""

    def test_no_policy_reads_all_work(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        yaml_path = tmp_path / ".stageflow" / "config" / "stages.yaml"
        config = {
            "stages": [{"name": "alpha", "tools": ["Read", "Grep"],
                        "meta": {"description": "No access policy"}}],
            "transitions": [],
        }
        yaml_path.write_text(yaml.dump(config, sort_keys=False), encoding="utf-8")
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "alpha"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Read", {"file_path": "any/file.md"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_no_policy_write_still_needs_tool_allow(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        yaml_path = tmp_path / ".stageflow" / "config" / "stages.yaml"
        config = {
            "stages": [{"name": "alpha", "tools": ["Read"],
                        "meta": {"description": "Read-only stage"}}],
            "transitions": [],
        }
        yaml_path.write_text(yaml.dump(config, sort_keys=False), encoding="utf-8")
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "alpha"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Write", {"file_path": "any_file.py"})
        assert r.returncode != 0, "Write not in alpha's tools should still be blocked"

    def test_no_policy_allows_anything_when_tools_empty(self, tmp_path):
        subprocess.run(
            [sys.executable, "-m", "stageflow", "init"],
            capture_output=True, cwd=str(tmp_path),
        )
        yaml_path = tmp_path / ".stageflow" / "config" / "stages.yaml"
        config = {
            "stages": [{"name": "unrestricted", "tools": [],
                        "meta": {"description": "No restrictions"}}],
            "transitions": [],
        }
        yaml_path.write_text(yaml.dump(config, sort_keys=False), encoding="utf-8")
        subprocess.run(
            [sys.executable, "-m", "stageflow", "start", "unrestricted"],
            capture_output=True, cwd=str(tmp_path),
        )
        r = _hook(tmp_path, "Write", {"file_path": "anything.py"})
        assert r.returncode == 0, r.stderr
        assert "allow" in r.stdout

    def test_guard_check_no_policy(self, temp_dir):
        from stageflow.core.registry import StageRegistry
        from stageflow.core.guard import StageGuard
        _write_access_config(temp_dir / "stages.yaml", None, tools=["Read", "Write"])
        reg = StageRegistry(str(temp_dir / "stages.yaml"))
        _init_state(temp_dir, reg)
        guard = StageGuard(
            str(temp_dir / "stages.yaml"), str(temp_dir), registry=reg,
        )
        ok, _ = guard.check("Read", {"file_path": "any/file.py"})
        assert ok, "Read should be allowed without access policy"
        ok2, _ = guard.check("Write", {"file_path": "any/file.py"})
        assert ok2, "Write should be allowed without access policy"
        ok3, _ = guard.check("Delete", {})
        assert not ok3, "Delete not in tools should still be blocked"
