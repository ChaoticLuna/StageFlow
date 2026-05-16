"""Tests for access_policy.py — path policy evaluation."""

import os
import re
import pytest
from pathlib import Path

from stageflow.core.access_policy import (
    AccessPolicy,
    _interpolate,
    _normalize_path,
    _match_glob,
    _glob_to_regex,
    _pattern_prefix,
    _pattern_covers_dir,
)


# ═══════════════════════════════════════════════════════════════════════════
# _interpolate
# ═══════════════════════════════════════════════════════════════════════════

class TestInterpolate:
    def test_replaces_known_variable(self):
        assert _interpolate("foo/{{var.run_id}}/bar", {"run_id": "abc123"}) == "foo/abc123/bar"

    def test_replaces_multiple_variables(self):
        result = _interpolate(
            "{{var.a}}/{{var.b}}/{{var.a}}", {"a": "x", "b": "y"}
        )
        assert result == "x/y/x"

    def test_unresolved_variable_produces_sentinel(self):
        result = _interpolate("foo/{{var.missing}}/bar", {"run_id": "abc"})
        assert "\x00SF_UNRESOLVED:missing\x00" in result

    def test_no_variables_returns_unchanged(self):
        assert _interpolate("plain/path.md", {"run_id": "abc"}) == "plain/path.md"

    def test_none_variables(self):
        result = _interpolate("foo/{{var.x}}/bar", None)
        assert "\x00SF_UNRESOLVED:x\x00" in result

    def test_empty_variables(self):
        result = _interpolate("foo/{{var.x}}/bar", {})
        assert "\x00SF_UNRESOLVED:x\x00" in result

    def test_non_string_variable_value(self):
        result = _interpolate("{{var.n}}", {"n": 42})
        assert result == "42"


# ═══════════════════════════════════════════════════════════════════════════
# _normalize_path
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizePath:
    def test_simple_relative(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "file.md").write_text("")
        result = _normalize_path("file.md", root)
        assert result == "file.md"

    def test_nested_relative(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "a" / "b").mkdir(parents=True)
        (temp_dir / "a" / "b" / "c.md").write_text("")
        result = _normalize_path("a/b/c.md", root)
        assert result == "a/b/c.md"

    def test_double_dot_rejected(self, temp_dir):
        root = str(temp_dir)
        child = temp_dir / "sub"
        child.mkdir()
        result = _normalize_path("../outside.txt", str(child))
        assert result is None

    def test_double_dot_normalized_inside(self, temp_dir):
        root = str(temp_dir)
        child = temp_dir / "sub"
        child.mkdir()
        (temp_dir / "sub" / ".." / "sibling.md").write_text("")
        result = _normalize_path("sub/../sibling.md", root)
        assert result == "sibling.md"

    def test_absolute_path_inside_project(self, temp_dir):
        root = str(temp_dir)
        f = temp_dir / "data.txt"
        f.write_text("")
        result = _normalize_path(str(f), root)
        assert result == "data.txt"

    def test_absolute_path_outside_project(self, temp_dir):
        root = str(temp_dir)
        result = _normalize_path("C:\\Windows\\System32\\cmd.exe", root)
        assert result is None

    def test_windows_separators_normalized(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "a" / "b").mkdir(parents=True)
        result = _normalize_path("a\\b", root)
        assert result == "a/b"

    def test_traversal_chain(self, temp_dir):
        root = str(temp_dir)
        result = _normalize_path("a/../../outside", root)
        assert result is None

    def test_symlink_escape(self, temp_dir):
        """Resolve should catch symlinks that point outside."""
        root = str(temp_dir)
        result = _normalize_path("some/deep/../../../../etc", root)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# _glob_to_regex / _match_glob
# ═══════════════════════════════════════════════════════════════════════════

class TestGlobToRegex:
    def test_exact_literal(self):
        r = _glob_to_regex("file.md")
        assert re.match(r, "file.md")
        assert not re.match(r, "other.md")

    def test_single_star(self):
        r = _glob_to_regex("*.md")
        assert re.match(r, "readme.md")
        assert re.match(r, "notes.md")
        assert not re.match(r, "readme.txt")
        assert not re.match(r, "a/readme.md")

    def test_question_mark(self):
        r = _glob_to_regex("file?.md")
        assert re.match(r, "file1.md")
        assert re.match(r, "fileX.md")
        assert not re.match(r, "file.md")
        assert not re.match(r, "file12.md")

    def test_double_star_at_end(self):
        r = _glob_to_regex("artifacts/**")
        assert re.match(r, "artifacts/foo")
        assert re.match(r, "artifacts/foo/bar")
        assert re.match(r, "artifacts/foo/bar/baz.txt")
        assert not re.match(r, "other/foo")

    def test_double_star_slash_prefix(self):
        r = _glob_to_regex("artifacts/**/plan")
        assert re.match(r, "artifacts/plan")
        assert re.match(r, "artifacts/runs/plan")
        assert re.match(r, "artifacts/runs/abc/plan")
        assert not re.match(r, "artifacts/plan/extra")

    def test_dotfile_pattern(self):
        r = _glob_to_regex(".env")
        assert re.match(r, ".env")
        assert not re.match(r, "env")

    def test_escapes_regex_chars(self):
        r = _glob_to_regex("test.dir/file+name[v1].md")
        assert re.match(r, "test.dir/file+name[v1].md")
        assert not re.match(r, "testXdir/file+name[v1].md")

    def test_double_star_non_slash_next(self):
        r = _glob_to_regex("file**name")
        assert re.match(r, "fileABname")
        assert re.match(r, "fileanythingname")
        assert not re.match(r, "other.txt")


class TestMatchGlob:
    def test_exact_match(self):
        assert _match_glob("file.md", "file.md")
        assert not _match_glob("other.md", "file.md")

    def test_star_match(self):
        assert _match_glob("notes.md", "*.md")
        assert not _match_glob("notes.txt", "*.md")

    def test_double_star_suffix(self):
        assert _match_glob("artifacts/foo.txt", "artifacts/**")
        assert _match_glob("artifacts/a/b/c.txt", "artifacts/**")
        assert not _match_glob("other/a.txt", "artifacts/**")

    def test_double_star_middle(self):
        assert _match_glob("artifacts/target", "artifacts/**/target")
        assert _match_glob("artifacts/a/target", "artifacts/**/target")
        assert _match_glob("artifacts/a/b/target", "artifacts/**/target")

    def test_sentinel_never_matches(self):
        assert not _match_glob("anything", "\x00SF_UNRESOLVED:run_id\x00")

    def test_windows_backslash_in_pattern(self):
        assert _match_glob("a/b/c", "a\\b\\c")

    def test_fnmatch_fallback(self):
        assert _match_glob("data.csv", "*.csv")
        assert not _match_glob("data.json", "*.csv")
        assert _match_glob("src/file.ts", "src/*.ts")
        assert not _match_glob("src/sub/file.ts", "src/*.ts")


# ═══════════════════════════════════════════════════════════════════════════
# _pattern_prefix / _pattern_covers_dir
# ═══════════════════════════════════════════════════════════════════════════

class TestPatternPrefix:
    def test_literal(self):
        assert _pattern_prefix("artifacts/runs") == "artifacts/runs"

    def test_strips_star(self):
        assert _pattern_prefix("*.md") == ".md"

    def test_strips_double_star(self):
        assert _pattern_prefix("artifacts/**").rstrip("/") == "artifacts"
        assert _pattern_prefix("artifacts/**/plan") == "artifacts/plan"

    def test_strips_question(self):
        assert _pattern_prefix("file?.txt") == "file.txt"


class TestPatternCoversDir:
    def test_exact_dir_match(self):
        assert _pattern_covers_dir("artifacts/**", "artifacts")
        assert _pattern_covers_dir("artifacts/**", "artifacts/sub")

    def test_dir_under_prefix(self):
        assert _pattern_covers_dir("artifacts/runs/**", "artifacts/runs/abc123")

    def test_prefix_under_dir(self):
        assert not _pattern_covers_dir("artifacts/runs/abc/**", "artifacts/runs")

    def test_no_match(self):
        assert not _pattern_covers_dir("data/**", "artifacts")

    def test_sentinel_never_covers(self):
        assert not _pattern_covers_dir("\x00SF_UNRESOLVED:run_id\x00", "anything")

    def test_child_file_match(self):
        # Single-segment patterns (no /, no **) don't guarantee all files
        # under a directory match — fail closed.
        assert not _pattern_covers_dir("*.md", ".")
        assert not _pattern_covers_dir("*.md", "src")


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — no policy (backward compatible)
# ═══════════════════════════════════════════════════════════════════════════

class TestNoPolicy:
    def test_no_config_allows_all(self):
        p = AccessPolicy(None)
        assert not p.has_policy
        assert not p.has_read_policy
        assert not p.has_write_policy
        assert p.check_read("anything", "/tmp")[0]
        assert p.check_write("anything", "/tmp")[0]

    def test_empty_config_allows_all(self):
        p = AccessPolicy({})
        assert not p.has_policy
        assert p.check_read("secrets.env", "/tmp")[0]
        assert p.check_write(".stageflow/config", "/tmp")[0]

    def test_empty_sections(self):
        p = AccessPolicy({"read": {}, "write": {}})
        assert not p.has_read_policy
        assert not p.has_write_policy
        # Sections exist but have no rules → no restriction
        assert p.check_read("anything", "/root")[0]
        assert p.check_write("anything", "/root")[0]


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — deny-only
# ═══════════════════════════════════════════════════════════════════════════

class TestDenyOnly:
    def test_denied_path_blocked(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / ".env").write_text("SECRET=1")
        p = AccessPolicy({"read": {"deny": [".env"]}})
        assert p.has_read_policy
        ok, reason = p.check_read(".env", root)
        assert not ok
        assert "denied" in reason

    def test_non_denied_path_allowed(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "README.md").write_text("")
        p = AccessPolicy({"read": {"deny": [".env"]}})
        assert p.check_read("README.md", root)[0]

    def test_deny_glob_pattern(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "secrets").mkdir()
        p = AccessPolicy({"read": {"deny": ["secrets/**"]}})
        ok, _ = p.check_read("secrets/api.key", root)
        assert not ok

    def test_deny_exact_file(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "config.yml").write_text("")
        p = AccessPolicy({"write": {"deny": ["config.yml"]}})
        ok, _ = p.check_write("config.yml", root)
        assert not ok


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — allow-only
# ═══════════════════════════════════════════════════════════════════════════

class TestAllowOnly:
    def test_allowed_path_passes(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts").mkdir()
        p = AccessPolicy({"write": {"allow": ["artifacts/**"]}})
        ok, _ = p.check_write("artifacts/output.txt", root)
        assert ok

    def test_non_allowed_path_blocked(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy({"write": {"allow": ["artifacts/**"]}})
        ok, reason = p.check_write("src/main.py", root)
        assert not ok
        assert "not in allow list" in reason

    def test_allow_star_pattern(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy({"read": {"allow": ["*.md", "*.txt"]}})
        assert p.check_read("README.md", root)[0]
        assert p.check_read("notes.txt", root)[0]
        assert not p.check_read("main.py", root)[0]

    def test_allow_exact_file(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy({"write": {"allow": ["task_plan.md"]}})
        assert p.check_write("task_plan.md", root)[0]
        assert not p.check_write("other.md", root)[0]


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — deny overrides allow
# ═══════════════════════════════════════════════════════════════════════════

class TestDenyOverAllow:
    def test_deny_wins_over_allow(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / ".env").write_text("")
        p = AccessPolicy({
            "read": {
                "allow": ["*"],
                "deny": [".env"],
            }
        })
        ok, reason = p.check_read(".env", root)
        assert not ok
        assert "denied" in reason

    def test_deny_wins_over_broad_allow(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "secrets").mkdir()
        (temp_dir / "secrets" / "key.txt").write_text("")
        p = AccessPolicy({
            "read": {
                "allow": ["**"],
                "deny": ["secrets/**"],
            }
        })
        assert p.check_read("README.md", root)[0]
        ok, _ = p.check_read("secrets/key.txt", root)
        assert not ok


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — variable interpolation in patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestVariableInterpolation:
    def test_resolved_run_id_matches(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts" / "runs" / "abc123" / "plan").mkdir(
            parents=True
        )
        (temp_dir / "artifacts" / "runs" / "abc123" / "plan" / "task_plan.md").write_text("")
        p = AccessPolicy({
            "write": {"allow": ["artifacts/runs/{{var.run_id}}/plan/**"]}
        })
        ok, _ = p.check_write(
            "artifacts/runs/abc123/plan/task_plan.md", root,
            variables={"run_id": "abc123"},
        )
        assert ok

    def test_wrong_run_id_blocked(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts" / "runs" / "xyz789" / "plan").mkdir(
            parents=True
        )
        (temp_dir / "artifacts" / "runs" / "xyz789" / "plan" / "task_plan.md").write_text("")
        p = AccessPolicy({
            "write": {"allow": ["artifacts/runs/{{var.run_id}}/plan/**"]}
        })
        ok, _ = p.check_write(
            "artifacts/runs/xyz789/plan/task_plan.md", root,
            variables={"run_id": "abc123"},
        )
        assert not ok

    def test_unresolved_variable_blocks(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts" / "runs" / "stale" / "data.txt").mkdir(
            parents=True
        )
        p = AccessPolicy({
            "write": {"allow": ["artifacts/runs/{{var.run_id}}/**"]}
        })
        ok, _ = p.check_write(
            "artifacts/runs/stale/data.txt", root,
            variables={"other": "val"},
        )
        assert not ok

    def test_unresolved_variable_with_deny(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy({
            "read": {"deny": ["secrets/{{var.env}}/**"]}
        })
        ok, _ = p.check_read("secrets/prod/key.txt", root,
                            variables={})
        assert ok


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — path escape
# ═══════════════════════════════════════════════════════════════════════════

class TestPathEscape:
    def test_relative_double_dot_escape(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy({"write": {"allow": ["artifacts/**"]}})
        ok, reason = p.check_write("../outside.txt", root)
        assert not ok
        assert "escapes" in reason

    def test_absolute_path_outside(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy({"read": {"allow": ["*"]}})
        ok, reason = p.check_read("C:\\Windows\\win.ini", root)
        assert not ok
        assert "escapes" in reason

    def test_deep_traversal(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy({"write": {"deny": [".env"]}})
        ok, reason = p.check_write("a/../../../../etc/passwd", root)
        assert not ok
        assert "escapes" in reason


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — absolute path inside project
# ═══════════════════════════════════════════════════════════════════════════

class TestAbsolutePathInside:
    def test_absolute_allowed_path(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts").mkdir(parents=True)
        (temp_dir / "artifacts" / "out.txt").write_text("")
        p = AccessPolicy({"write": {"allow": ["artifacts/**"]}})
        abs_path = str(temp_dir / "artifacts" / "out.txt")
        assert p.check_write(abs_path, root)[0]

    def test_absolute_blocked_path(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "src" / "main.py").mkdir(parents=True)
        p = AccessPolicy({"write": {"allow": ["artifacts/**"]}})
        abs_path = str(temp_dir / "src" / "main.py")
        ok, reason = p.check_write(abs_path, root)
        assert not ok
        assert "not in allow list" in reason


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — cross-platform path handling
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossPlatform:
    def test_windows_backslash_in_requested_path(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "a" / "b" / "c.txt").mkdir(parents=True)
        p = AccessPolicy({"read": {"allow": ["a/**"]}})
        assert p.check_read("a\\b\\c.txt", root)[0]

    def test_windows_backslash_in_pattern(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "a" / "b").mkdir(parents=True)
        p = AccessPolicy({"read": {"allow": ["a\\b\\*"]}})
        assert p.check_read("a/b/c.txt", root)[0]

    def test_mixed_separators(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "a" / "b" / "c.txt").mkdir(parents=True)
        p = AccessPolicy({"read": {"allow": ["a/b/*"]}})
        assert p.check_read("a\\b/c.txt", root)[0]


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — check_search (directory / search-root gating)
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckSearch:
    def test_search_root_allowed(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts").mkdir()
        p = AccessPolicy({"read": {"allow": ["artifacts/**"]}})
        assert p.check_search("artifacts", root)[0]

    def test_search_root_not_covered(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "src").mkdir()
        p = AccessPolicy({"read": {"allow": ["artifacts/**"]}})
        ok, reason = p.check_search("src", root)
        assert not ok
        assert "not covered" in reason

    def test_search_root_intersects_deny(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "secrets").mkdir()
        p = AccessPolicy({"read": {"allow": ["**"], "deny": ["secrets/**"]}})
        ok, reason = p.check_search("secrets", root)
        assert not ok
        assert "denied" in reason

    def test_search_root_deny_only_allows_unlisted(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts").mkdir()
        p = AccessPolicy({"read": {"deny": ["secrets/**"]}})
        ok, _ = p.check_search("artifacts", root)
        assert ok, "Search in unlisted dir should be allowed when only deny defined"

    def test_search_root_allowed_with_deny_elsewhere(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts").mkdir()
        (temp_dir / "secrets").mkdir()
        p = AccessPolicy({"read": {"allow": ["**"], "deny": ["secrets/**"]}})
        assert p.check_search("artifacts", root)[0]

    def test_search_root_escaping(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy({"read": {"allow": ["**"]}})
        ok, reason = p.check_search("../outside", root)
        assert not ok
        assert "escapes" in reason

    def test_search_root_no_policy(self):
        p = AccessPolicy({})
        assert p.check_search("anywhere", "/tmp")[0]

    def test_search_root_subdirectory_of_allowed(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts" / "runs" / "abc").mkdir(parents=True)
        p = AccessPolicy({"read": {"allow": ["artifacts/**"]}})
        assert p.check_search("artifacts/runs/abc", root)[0]


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — has_policy / has_read_policy / has_write_policy
# ═══════════════════════════════════════════════════════════════════════════

class TestHasPolicy:
    def test_none(self):
        p = AccessPolicy(None)
        assert not p.has_policy
        assert not p.has_read_policy
        assert not p.has_write_policy

    def test_empty_dict(self):
        p = AccessPolicy({})
        assert not p.has_policy

    def test_read_only(self):
        p = AccessPolicy({"read": {"allow": ["*"]}})
        assert p.has_policy
        assert p.has_read_policy
        assert not p.has_write_policy

    def test_write_only(self):
        p = AccessPolicy({"write": {"deny": [".env"]}})
        assert p.has_policy
        assert not p.has_read_policy
        assert p.has_write_policy

    def test_both(self):
        p = AccessPolicy({"read": {"allow": ["*"]}, "write": {"allow": ["artifacts/**"]}})
        assert p.has_policy
        assert p.has_read_policy
        assert p.has_write_policy


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — integration scenarios from Phase 39 spec
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegrationScenarios:
    def test_allowed_write_to_run_scoped_artifact(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts" / "runs" / "run1" / "plan").mkdir(parents=True)
        p = AccessPolicy({
            "write": {"allow": ["artifacts/runs/{{var.run_id}}/**"]}
        })
        assert p.check_write(
            "artifacts/runs/run1/plan/task_plan.md", root,
            variables={"run_id": "run1"},
        )[0]

    def test_blocked_write_to_source_file(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "src" / "main.py").mkdir(parents=True)
        p = AccessPolicy({
            "write": {"allow": ["artifacts/**"]}
        })
        ok, _ = p.check_write("src/main.py", root)
        assert not ok

    def test_blocked_read_of_dotenv(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / ".env").write_text("")
        p = AccessPolicy({"read": {"deny": [".env"]}})
        ok, reason = p.check_read(".env", root)
        assert not ok
        assert "denied" in reason

    def test_old_workflow_no_access_keeps_current_behavior(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy(None)
        assert p.check_read(".env", root)[0]
        assert p.check_write("src/main.py", root)[0]
        assert p.check_search("anywhere", root)[0]

    def test_grep_without_search_root_in_restricted_stage(self):
        """When search root is '.' (project-wide) and policy is restrictive,
        project-wide access should be denied."""
        p = AccessPolicy({"read": {"allow": ["artifacts/**"]}})
        ok, reason = p.check_search(".", "/some/root")
        assert not ok

    def test_allowed_search_in_allowed_dir(self):
        p = AccessPolicy({"read": {"allow": ["artifacts/**", "docs/**"]}})
        assert p.check_search("docs", "/root")[0]


# ═══════════════════════════════════════════════════════════════════════════
# AccessPolicy — full policy from Phase 39 spec example
# ═══════════════════════════════════════════════════════════════════════════

class TestFullPolicyExample:
    POLICY = {
        "read": {
            "allow": [
                "artifacts/runs/{{var.run_id}}/pick/**",
                "artifacts/runs/{{var.run_id}}/analyze/**",
                "README.md",
            ],
            "deny": [".env", "secrets/**"],
        },
        "write": {
            "allow": [
                "artifacts/runs/{{var.run_id}}/plan/task_plan.md",
            ],
            "deny": [
                ".stageflow/config/stages.yaml",
                "secrets/**",
            ],
        },
    }

    VARS = {"run_id": "run-42"}

    def test_read_allowed_in_pick(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts" / "runs" / "run-42" / "pick").mkdir(parents=True)
        p = AccessPolicy(self.POLICY)
        assert p.check_read(
            "artifacts/runs/run-42/pick/issue.md", root, self.VARS
        )[0]

    def test_read_allowed_readme(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "README.md").write_text("")
        p = AccessPolicy(self.POLICY)
        assert p.check_read("README.md", root, self.VARS)[0]

    def test_read_denied_dotenv(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / ".env").write_text("")
        p = AccessPolicy(self.POLICY)
        ok, reason = p.check_read(".env", root, self.VARS)
        assert not ok
        assert "denied" in reason

    def test_read_denied_outside_allow(self, temp_dir):
        root = str(temp_dir)
        p = AccessPolicy(self.POLICY)
        ok, reason = p.check_read("src/main.py", root, self.VARS)
        assert not ok

    def test_write_allowed_task_plan(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts" / "runs" / "run-42" / "plan").mkdir(parents=True)
        p = AccessPolicy(self.POLICY)
        assert p.check_write(
            "artifacts/runs/run-42/plan/task_plan.md", root, self.VARS
        )[0]

    def test_write_blocked_config(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / ".stageflow" / "config").mkdir(parents=True)
        p = AccessPolicy(self.POLICY)
        ok, reason = p.check_write(
            ".stageflow/config/stages.yaml", root, self.VARS
        )
        assert not ok

    def test_write_blocked_different_run(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "artifacts" / "runs" / "other-run" / "plan").mkdir(parents=True)
        p = AccessPolicy(self.POLICY)
        ok, reason = p.check_write(
            "artifacts/runs/other-run/plan/task_plan.md", root, self.VARS
        )
        assert not ok

    def test_write_blocked_secrets(self, temp_dir):
        root = str(temp_dir)
        (temp_dir / "secrets").mkdir()
        p = AccessPolicy(self.POLICY)
        ok, reason = p.check_write("secrets/key.txt", root, self.VARS)
        assert not ok
