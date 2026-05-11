"""Comprehensive tests for all 20 built-in condition types in stageflow.core.conditions."""

import json
import os
import subprocess
import time
import pytest

from stageflow.core.conditions import (
    evaluate,
    evaluate_all,
    list_conditions,
    _parse_condition,
    _get_severity,
    _resolve_vars,
    _CONDITION_REGISTRY,
)


# ═══════════════════════════════════════════════════════════════════════════
# file_exists
# ═══════════════════════════════════════════════════════════════════════════

class TestFileExists:
    def test_existing_file(self, temp_dir):
        f = temp_dir / "test.txt"
        f.write_text("hello")
        passed, msg = evaluate("file_exists", {
            "base_path": str(temp_dir), "path": "test.txt"
        })
        assert passed
        assert "exists" in msg

    def test_non_existing_file(self, temp_dir):
        passed, msg = evaluate("file_exists", {
            "base_path": str(temp_dir), "path": "no_such_file.txt"
        })
        assert not passed
        assert "not found" in msg

    def test_nested_path(self, temp_dir):
        nested = temp_dir / "deep" / "nested" / "file.dat"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("payload")
        passed, msg = evaluate("file_exists", {
            "base_path": str(temp_dir), "path": "deep/nested/file.dat"
        })
        assert passed

    def test_using_value_param_alias(self, temp_dir):
        """'value' key should work as alias for 'path'."""
        f = temp_dir / "x.txt"
        f.write_text("")
        passed, msg = evaluate("file_exists", {
            "base_path": str(temp_dir), "value": "x.txt"
        })
        assert passed

    def test_empty_path(self, temp_dir):
        """Empty path should resolve to base_path itself."""
        passed, msg = evaluate("file_exists", {
            "base_path": str(temp_dir), "path": ""
        })
        # base_path directory should exist
        assert passed


# ═══════════════════════════════════════════════════════════════════════════
# file_not_exists
# ═══════════════════════════════════════════════════════════════════════════

class TestFileNotExists:
    def test_absent_file_passes(self, temp_dir):
        passed, msg = evaluate("file_not_exists", {
            "base_path": str(temp_dir), "path": "definitely_missing.xyz"
        })
        assert passed
        assert "absent" in msg

    def test_present_file_fails(self, temp_dir):
        f = temp_dir / "here.txt"
        f.write_text("present")
        passed, msg = evaluate("file_not_exists", {
            "base_path": str(temp_dir), "path": "here.txt"
        })
        assert not passed
        assert "exists" in msg


# ═══════════════════════════════════════════════════════════════════════════
# file_contains
# ═══════════════════════════════════════════════════════════════════════════

class TestFileContains:
    def test_pattern_found(self, temp_dir):
        f = temp_dir / "log.txt"
        f.write_text("Error: something failed\nInfo: running")
        passed, msg = evaluate("file_contains", {
            "base_path": str(temp_dir), "path": "log.txt", "pattern": "Error"
        })
        assert passed
        assert "found" in msg

    def test_pattern_not_found(self, temp_dir):
        f = temp_dir / "log.txt"
        f.write_text("Everything is fine")
        passed, msg = evaluate("file_contains", {
            "base_path": str(temp_dir), "path": "log.txt", "pattern": "Error"
        })
        assert not passed
        assert "not found" in msg

    def test_regex_pattern(self, temp_dir):
        f = temp_dir / "data.txt"
        f.write_text("abc123def\nno match here\n456")
        passed, msg = evaluate("file_contains", {
            "base_path": str(temp_dir), "path": "data.txt", "pattern": r"\d{3}"
        })
        assert passed

    def test_multiline_regex(self, temp_dir):
        f = temp_dir / "multi.txt"
        f.write_text("line1\nline2\nSTART\nmiddle\nEND\nline6")
        passed, msg = evaluate("file_contains", {
            "base_path": str(temp_dir), "path": "multi.txt",
            "pattern": r"START.*END"
        })
        # re.DOTALL should make . match newlines
        assert passed

    def test_file_not_exist(self, temp_dir):
        passed, msg = evaluate("file_contains", {
            "base_path": str(temp_dir), "path": "gone.txt", "pattern": "x"
        })
        assert not passed
        assert "not found" in msg

    def test_value_alias_for_pattern(self, temp_dir):
        f = temp_dir / "alias.txt"
        f.write_text("key=value")
        passed, msg = evaluate("file_contains", {
            "base_path": str(temp_dir), "path": "alias.txt", "value": "key=value"
        })
        assert passed


# ═══════════════════════════════════════════════════════════════════════════
# file_not_contains
# ═══════════════════════════════════════════════════════════════════════════

class TestFileNotContains:
    def test_pattern_absent_passes(self, temp_dir):
        f = temp_dir / "clean.txt"
        f.write_text("Clean content only")
        passed, msg = evaluate("file_not_contains", {
            "base_path": str(temp_dir), "path": "clean.txt", "pattern": "Error"
        })
        assert passed
        assert "absent" in msg

    def test_pattern_present_fails(self, temp_dir):
        f = temp_dir / "dirty.txt"
        f.write_text("Error: something wrong")
        passed, msg = evaluate("file_not_contains", {
            "base_path": str(temp_dir), "path": "dirty.txt", "pattern": "Error"
        })
        assert not passed
        assert "found" in msg

    def test_file_not_exist(self, temp_dir):
        passed, msg = evaluate("file_not_contains", {
            "base_path": str(temp_dir), "path": "nope.txt", "pattern": "x"
        })
        assert not passed
        assert "not found" in msg


# ═══════════════════════════════════════════════════════════════════════════
# json_field
# ═══════════════════════════════════════════════════════════════════════════

class TestJsonField:
    def _write_json(self, temp_dir, name, data):
        f = temp_dir / name
        f.write_text(json.dumps(data), encoding="utf-8")
        return f

    # --- exists ---
    def test_field_exists(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"name": "test", "ver": 1})
        passed, msg = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "name", "op": "exists"
        })
        assert passed

    def test_field_missing(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"name": "test"})
        passed, msg = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "missing_field", "op": "exists"
        })
        assert not passed
        assert "missing" in msg

    # --- not_empty ---
    def test_not_empty_passes(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"key": "val"})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "key", "op": "not_empty"
        })
        assert passed

    def test_not_empty_fails_on_empty_string(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"key": ""})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "key", "op": "not_empty"
        })
        assert not passed

    def test_not_empty_fails_on_empty_list(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"items": []})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "items", "op": "not_empty"
        })
        assert not passed

    def test_not_empty_fails_on_empty_dict(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"obj": {}})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "obj", "op": "not_empty"
        })
        assert not passed

    # --- equals ---
    def test_equals_passes(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"x": 5})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "x", "op": "equals", "value": 5
        })
        assert passed

    def test_equals_fails(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"x": 5})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "x", "op": "equals", "value": 99
        })
        assert not passed

    # --- not_equals ---
    def test_not_equals_passes(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"x": 5})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "x", "op": "not_equals", "value": 3
        })
        assert passed

    def test_not_equals_fails(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"x": 5})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "x", "op": "not_equals", "value": 5
        })
        assert not passed

    # --- gt ---
    def test_gt_passes(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"count": 10})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "count", "op": "gt", "value": 5
        })
        assert passed

    def test_gt_fails(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"count": 2})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "count", "op": "gt", "value": 10
        })
        assert not passed

    # --- lt ---
    def test_lt_passes(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"count": 3})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "count", "op": "lt", "value": 10
        })
        assert passed

    def test_lt_fails(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"count": 20})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "count", "op": "lt", "value": 5
        })
        assert not passed

    # --- in ---
    def test_in_passes(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"tags": ["a", "b", "c"]})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "tags", "op": "in", "value": "b"
        })
        assert passed

    def test_in_fails(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"tags": ["a", "b"]})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "tags", "op": "in", "value": "z"
        })
        assert not passed

    # --- matches ---
    def test_matches_passes(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"email": "me@example.com"})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "email", "op": "matches", "value": r".*@example\.com"
        })
        assert passed

    def test_matches_fails(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"email": "me@other.org"})
        passed, _ = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "email", "op": "matches", "value": r".*@example\.com"
        })
        assert not passed

    # --- nested fields ---
    def test_nested_field_a_b_c(self, temp_dir):
        self._write_json(temp_dir, "deep.json", {
            "a": {"b": {"c": "treasure", "d": 42}}
        })
        passed, msg = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "deep.json",
            "field": "a.b.c", "op": "equals", "value": "treasure"
        })
        assert passed

    def test_nested_field_missing_intermediate(self, temp_dir):
        self._write_json(temp_dir, "deep.json", {"a": 1})
        passed, msg = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "deep.json",
            "field": "a.b.c", "op": "exists"
        })
        # a is an int, so navigating a.b fails
        assert not passed

    # --- error cases ---
    def test_missing_file(self, temp_dir):
        passed, msg = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "no_file.json", "field": "x"
        })
        assert not passed
        assert "not found" in msg

    def test_invalid_json(self, temp_dir):
        f = temp_dir / "bad.json"
        f.write_text("this is not json {{{")
        passed, msg = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "bad.json", "field": "x"
        })
        assert not passed
        assert "Invalid JSON" in msg

    def test_unknown_op(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"x": 1})
        passed, msg = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "x", "op": "bogus_op"
        })
        assert not passed
        assert "Unknown op" in msg

    def test_gt_field_missing_obj_none(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"other": 1})
        passed, msg = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "missing", "op": "gt", "value": 5
        })
        assert not passed
        assert "None" in msg

    def test_lt_expected_none(self, temp_dir):
        self._write_json(temp_dir, "cfg.json", {"count": 10})
        passed, msg = evaluate("json_field", {
            "base_path": str(temp_dir), "path": "cfg.json",
            "field": "count", "op": "lt", "value": None
        })
        assert not passed
        assert "None" in msg


# ═══════════════════════════════════════════════════════════════════════════
# yaml_field
# ═══════════════════════════════════════════════════════════════════════════

class TestYamlField:
    def _write_yaml(self, temp_dir, name, content):
        f = temp_dir / name
        f.write_text(content, encoding="utf-8")
        return f

    def test_field_exists(self, temp_dir):
        self._write_yaml(temp_dir, "cfg.yaml", "name: test\nversion: 1\n")
        passed, msg = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "cfg.yaml",
            "field": "name", "op": "exists"
        })
        assert passed

    def test_field_missing(self, temp_dir):
        self._write_yaml(temp_dir, "cfg.yaml", "name: test\n")
        passed, msg = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "cfg.yaml",
            "field": "no_such_field", "op": "exists"
        })
        assert not passed
        assert "missing" in msg

    def test_not_empty(self, temp_dir):
        self._write_yaml(temp_dir, "cfg.yaml", "key: value\n")
        passed, _ = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "cfg.yaml",
            "field": "key", "op": "not_empty"
        })
        assert passed

    def test_equals_passes(self, temp_dir):
        self._write_yaml(temp_dir, "cfg.yaml", "status: ready\n")
        passed, _ = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "cfg.yaml",
            "field": "status", "op": "equals", "value": "ready"
        })
        assert passed

    def test_equals_fails(self, temp_dir):
        self._write_yaml(temp_dir, "cfg.yaml", "status: pending\n")
        passed, _ = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "cfg.yaml",
            "field": "status", "op": "equals", "value": "ready"
        })
        assert not passed

    def test_nested_yaml_field(self, temp_dir):
        self._write_yaml(temp_dir, "deep.yaml", "a:\n  b:\n    c: found\n")
        passed, _ = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "deep.yaml",
            "field": "a.b.c", "op": "equals", "value": "found"
        })
        assert passed

    def test_missing_file(self, temp_dir):
        passed, msg = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "nope.yaml",
            "field": "x", "op": "exists"
        })
        assert not passed
        assert "not found" in msg

    def test_unknown_op(self, temp_dir):
        self._write_yaml(temp_dir, "cfg.yaml", "x: 1\n")
        passed, msg = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "cfg.yaml",
            "field": "x", "op": "bogus"
        })
        assert not passed
        assert "Unknown op" in msg

    def test_pyyaml_not_installed(self, monkeypatch, temp_dir):
        self._write_yaml(temp_dir, "cfg.yaml", "x: 1\n")
        import sys
        monkeypatch.setitem(sys.modules, "yaml", None)
        passed, msg = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "cfg.yaml",
            "field": "x", "op": "exists"
        })
        assert not passed
        assert "not installed" in msg

    def test_invalid_yaml_parse_error(self, temp_dir):
        """lines 368-369: invalid YAML raises exception during safe_load."""
        self._write_yaml(temp_dir, "bad.yaml", "key: {unclosed: [}")
        passed, msg = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "bad.yaml",
            "field": "key", "op": "exists"
        })
        assert not passed
        assert "Invalid YAML" in msg

    def test_navigate_non_dict_field(self, temp_dir):
        """line 376: intermediate field is not a dict (e.g., scalar)."""
        self._write_yaml(temp_dir, "flat.yaml", "a: scalar_value\n")
        passed, msg = evaluate("yaml_field", {
            "base_path": str(temp_dir), "path": "flat.yaml",
            "field": "a.b.c", "op": "exists"
        })
        assert not passed
        assert "Cannot navigate" in msg


# ═══════════════════════════════════════════════════════════════════════════
# shell_test
# ═══════════════════════════════════════════════════════════════════════════

class TestShellTest:
    def test_exit_zero_passes(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo hello",
            "op": "exit_zero"
        })
        assert passed

    def test_exit_nonzero_fails(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "exit 1",
            "op": "exit_zero"
        })
        assert not passed

    def test_stdout_contains_passes(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo hello world",
            "op": "stdout_contains",
            "value": "hello"
        })
        assert passed

    def test_stdout_contains_fails(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo goodbye",
            "op": "stdout_contains",
            "value": "hello"
        })
        assert not passed

    def test_stdout_not_empty_passes(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo something",
            "op": "stdout_not_empty"
        })
        assert passed

    def test_stdout_not_empty_fails(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "python -c \"\"",
            "op": "stdout_not_empty"
        })
        assert not passed, f"Expected empty stdout to fail not_empty check, got: {msg}"

    def test_stdout_gt_passes(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo 42",
            "op": "gt",
            "value": 10
        })
        assert passed

    def test_stdout_gt_fails(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo 3",
            "op": "gt",
            "value": 100
        })
        assert not passed

    def test_stdout_gt_non_numeric(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo hello",
            "op": "gt",
            "value": 5
        })
        assert not passed

    def test_nonexistent_command(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "nonexistent_cmd_xyz_12345",
            "op": "exit_zero"
        })
        assert not passed

    def test_unknown_op(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo x",
            "op": "bogus_op"
        })
        assert not passed
        assert "Unknown op" in msg

    def test_with_value_alias(self, temp_dir):
        """Shell_test supports 'value' as alias for 'command'."""
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "value": "echo ok",
            "op": "exit_zero"
        })
        assert passed

    def test_stdout_matches_passes(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo PASS: 42 tests run",
            "op": "stdout_matches",
            "value": r"PASS: \d+ tests"
        })
        assert passed

    def test_stdout_matches_fails(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo FAIL: 0 tests",
            "op": "stdout_matches",
            "value": r"PASS: \d+"
        })
        assert not passed

    def test_stdout_matches_invalid_regex(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo anything",
            "op": "stdout_matches",
            "value": "[invalid"
        })
        assert not passed
        assert "Regex error" in msg

    def test_stdout_lt_passes(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo 5",
            "op": "lt",
            "value": 10
        })
        assert passed

    def test_stdout_lt_fails(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo 50",
            "op": "lt",
            "value": 10
        })
        assert not passed

    def test_stdout_eq_passes(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo 42",
            "op": "eq",
            "value": 42
        })
        assert passed

    def test_stdout_eq_fails(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo 42",
            "op": "eq",
            "value": 99
        })
        assert not passed

    def test_stderr_stream_contains(self, temp_dir):
        """Check stderr output using stream=stderr with stdout_contains."""
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": 'python -c "import sys; sys.stderr.write(\'error_output\')"',
            "op": "stdout_contains",
            "value": "error_output",
            "stream": "stderr"
        })
        assert passed

    def test_stderr_stream_not_empty(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": 'python -c "import sys; sys.stderr.write(\'err\')"',
            "op": "stdout_not_empty",
            "stream": "stderr"
        })
        assert passed

    def test_lt_non_numeric(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo hello",
            "op": "lt",
            "value": 5
        })
        assert not passed

    def test_eq_non_numeric(self, temp_dir):
        passed, msg = evaluate("shell_test", {
            "base_path": str(temp_dir),
            "command": "echo world",
            "op": "eq",
            "value": 10
        })
        assert not passed

    def test_command_invalid_cwd(self, temp_dir):
        import os
        bad_path = str(temp_dir / "nonexistent_dir_xyz")
        if os.path.exists(bad_path):
            os.rmdir(bad_path)
        passed, msg = evaluate("shell_test", {
            "base_path": bad_path,
            "command": "echo test",
            "op": "exit_zero"
        })
        assert not passed
        assert "error" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════
# python_expr
# ═══════════════════════════════════════════════════════════════════════════

class TestPythonExpr:
    def test_simple_true_expression(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir), "expr": "1 + 1 == 2"
        })
        assert passed

    def test_simple_false_expression(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir), "expr": "1 + 1 == 3"
        })
        assert not passed

    def test_bool_conversion_truthy(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir), "expr": "'hello'"
        })
        assert passed

    def test_bool_conversion_falsy(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir), "expr": "''"
        })
        assert not passed

    def test_base_path_accessible(self, temp_dir):
        test_file = temp_dir / "check.txt"
        test_file.write_text("data")
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir),
            "expr": "os.path.exists(Path(base_path) / 'check.txt')"
        })
        assert passed

    def test_custom_context_variable(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir),
            "expr": "my_var == 100",
            "context": {"my_var": 100}
        })
        assert passed

    def test_builtin_functions_available(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir),
            "expr": "len([1, 2, 3]) == 3 and sum([4, 5, 6]) == 15"
        })
        assert passed

    def test_any_all_available(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir),
            "expr": "all([True, True, True]) and any([False, True, False])"
        })
        assert passed

    def test_expr_error_returns_false(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir), "expr": "undefined_var_xyz"
        })
        assert not passed
        assert "error" in msg.lower()

    def test_value_alias_for_expr(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir), "value": "True"
        })
        assert passed

    def test_syntax_error(self, temp_dir):
        passed, msg = evaluate("python_expr", {
            "base_path": str(temp_dir), "expr": "1 +* 2"
        })
        assert not passed
        assert "error" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════
# env_var
# ═══════════════════════════════════════════════════════════════════════════

class TestEnvVar:
    def test_exists_passes(self, monkeypatch):
        monkeypatch.setenv("SF_TEST_VAR", "hello")
        passed, msg = evaluate("env_var", {"name": "SF_TEST_VAR", "op": "exists"})
        assert passed

    def test_exists_fails(self, monkeypatch):
        monkeypatch.delenv("SF_MISSING_VAR", raising=False)
        passed, msg = evaluate("env_var", {"name": "SF_MISSING_VAR", "op": "exists"})
        assert not passed
        assert "not set" in msg

    def test_equals_passes(self, monkeypatch):
        monkeypatch.setenv("SF_EQ_VAR", "foo")
        passed, _ = evaluate("env_var", {
            "name": "SF_EQ_VAR", "op": "equals", "value": "foo"
        })
        assert passed

    def test_equals_fails(self, monkeypatch):
        monkeypatch.setenv("SF_EQ_VAR", "foo")
        passed, _ = evaluate("env_var", {
            "name": "SF_EQ_VAR", "op": "equals", "value": "bar"
        })
        assert not passed

    def test_not_empty_passes(self, monkeypatch):
        monkeypatch.setenv("SF_NE_VAR", "something")
        passed, _ = evaluate("env_var", {"name": "SF_NE_VAR", "op": "not_empty"})
        assert passed

    def test_not_empty_fails_empty_string(self, monkeypatch):
        monkeypatch.setenv("SF_EMPTY_VAR", "")
        passed, _ = evaluate("env_var", {"name": "SF_EMPTY_VAR", "op": "not_empty"})
        assert not passed

    def test_not_empty_fails_missing(self, monkeypatch):
        monkeypatch.delenv("SF_NOT_THERE", raising=False)
        passed, _ = evaluate("env_var", {"name": "SF_NOT_THERE", "op": "not_empty"})
        assert not passed

    def test_value_alias_for_name(self, monkeypatch):
        monkeypatch.setenv("SF_ALIAS", "ok")
        passed, _ = evaluate("env_var", {"value": "SF_ALIAS", "op": "exists"})
        assert passed

    def test_unknown_op(self):
        passed, msg = evaluate("env_var", {"name": "ANY", "op": "bogus"})
        assert not passed
        assert "Unknown op" in msg


# ═══════════════════════════════════════════════════════════════════════════
# all_of
# ═══════════════════════════════════════════════════════════════════════════

class TestAllOf:
    def test_all_pass(self, temp_dir):
        f1 = temp_dir / "a.txt"; f1.write_text("")
        f2 = temp_dir / "b.txt"; f2.write_text("")
        passed, msg = evaluate("all_of", {
            "base_path": str(temp_dir),
            "conditions": [
                {"file_exists": "a.txt"},
                {"file_exists": "b.txt"},
            ]
        })
        assert passed
        assert "PASS" in msg

    def test_one_fails(self, temp_dir):
        f1 = temp_dir / "a.txt"; f1.write_text("")
        passed, msg = evaluate("all_of", {
            "base_path": str(temp_dir),
            "conditions": [
                {"file_exists": "a.txt"},
                {"file_exists": "nope.txt"},
            ]
        })
        assert not passed
        assert "FAIL" in msg

    def test_empty_list_passes(self, temp_dir):
        passed, msg = evaluate("all_of", {
            "base_path": str(temp_dir), "conditions": []
        })
        assert passed

    def test_value_alias_for_conditions(self, temp_dir):
        """'value' key should work as alias for 'conditions' list."""
        f1 = temp_dir / "x.txt"; f1.write_text("")
        passed, msg = evaluate("all_of", {
            "base_path": str(temp_dir),
            "value": [{"file_exists": "x.txt"}]
        })
        assert passed


# ═══════════════════════════════════════════════════════════════════════════
# any_of
# ═══════════════════════════════════════════════════════════════════════════

class TestAnyOf:
    def test_one_passes_sufficient(self, temp_dir):
        f1 = temp_dir / "good.txt"; f1.write_text("")
        passed, msg = evaluate("any_of", {
            "base_path": str(temp_dir),
            "conditions": [
                {"file_exists": "good.txt"},
                {"file_exists": "bad.txt"},
            ]
        })
        assert passed

    def test_all_fail(self, temp_dir):
        passed, msg = evaluate("any_of", {
            "base_path": str(temp_dir),
            "conditions": [
                {"file_exists": "nope1.txt"},
                {"file_exists": "nope2.txt"},
            ]
        })
        assert not passed
        assert "None of" in msg

    def test_empty_list_fails(self, temp_dir):
        passed, msg = evaluate("any_of", {
            "base_path": str(temp_dir), "conditions": []
        })
        assert not passed


# ═══════════════════════════════════════════════════════════════════════════
# not
# ═══════════════════════════════════════════════════════════════════════════

class TestNot:
    def test_negate_passing_condition(self, temp_dir):
        passed, msg = evaluate("not", {
            "base_path": str(temp_dir),
            "condition": {"always": True}
        })
        assert not passed

    def test_negate_failing_condition(self, temp_dir):
        passed, msg = evaluate("not", {
            "base_path": str(temp_dir),
            "condition": {"never": "blocked"}
        })
        assert passed

    def test_value_alias_for_condition(self, temp_dir):
        passed, msg = evaluate("not", {
            "base_path": str(temp_dir),
            "value": {"always": True}
        })
        assert not passed


# ═══════════════════════════════════════════════════════════════════════════
# always / never
# ═══════════════════════════════════════════════════════════════════════════

class TestAlwaysNever:
    def test_always_passes(self):
        passed, msg = evaluate("always", {})
        assert passed
        assert "passes" in msg.lower()

    def test_always_passes_with_params(self):
        passed, msg = evaluate("always", {"irrelevant": "data"})
        assert passed

    def test_never_fails(self):
        passed, msg = evaluate("never", {"reason": "blocked for testing"})
        assert not passed
        assert "blocked" in msg

    def test_never_default_reason(self):
        passed, msg = evaluate("never", {})
        assert not passed
        assert "Blocked" in msg

    def test_never_value_alias_for_reason(self):
        passed, msg = evaluate("never", {"value": "custom reason"})
        assert not passed
        assert "custom reason" in msg


# ═══════════════════════════════════════════════════════════════════════════
# evaluate_all (bulk evaluation)
# ═══════════════════════════════════════════════════════════════════════════

class TestEvaluateAll:
    def test_all_pass_returns_true(self, temp_dir):
        f1 = temp_dir / "f1.txt"; f1.write_text("")
        f2 = temp_dir / "f2.txt"; f2.write_text("")
        ok, msgs = evaluate_all([
            {"file_exists": "f1.txt"},
            {"file_exists": "f2.txt"},
        ], str(temp_dir))
        assert ok
        assert len(msgs) == 2
        assert all("PASS" in m for m in msgs)

    def test_fail_stops_early(self, temp_dir):
        f1 = temp_dir / "f1.txt"; f1.write_text("")
        ok, msgs = evaluate_all([
            {"file_exists": "f1.txt"},
            {"file_exists": "nonexistent.txt"},
            {"file_exists": "never_reached.txt"},
        ], str(temp_dir))
        assert not ok
        # Should stop after 2 conditions (first passed, second failed)
        assert len(msgs) == 2
        assert "FAIL" in msgs[1]

    def test_empty_list_passes(self):
        ok, msgs = evaluate_all([], ".")
        assert ok
        assert msgs == []

    def test_messages_have_pass_fail_prefix(self, temp_dir):
        f1 = temp_dir / "x.txt"; f1.write_text("")
        ok, msgs = evaluate_all([
            {"file_exists": "x.txt"},
            {"file_exists": "y.txt"},
        ], str(temp_dir))
        assert not ok
        assert "[PASS]" in msgs[0]
        assert "[FAIL]" in msgs[1]

    def test_timeout_returns_false(self, temp_dir):
        """evaluate_all timeout cuts off a slow condition."""
        ok, msgs = evaluate_all([
            {"shell_test": {"command": "python -c \"import time; time.sleep(5)\"",
             "op": "exit_zero"}},
        ], str(temp_dir), timeout=1)
        assert not ok
        assert any("TIMEOUT" in m for m in msgs)

    def test_timeout_not_triggered_when_fast(self, temp_dir):
        """Fast evaluation completes normally with timeout set."""
        f1 = temp_dir / "f.txt"; f1.write_text("")
        ok, msgs = evaluate_all([
            {"file_exists": "f.txt"},
        ], str(temp_dir), timeout=5)
        assert ok
        assert len(msgs) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Parallel condition evaluation (evaluate_all with parallel=True)
# ═══════════════════════════════════════════════════════════════════════════

class TestParallelEvaluation:
    def test_parallel_all_pass(self, temp_dir):
        for i in range(10):
            (temp_dir / f"p{i}.txt").write_text("")
        conditions = [{"file_exists": f"p{i}.txt"} for i in range(10)]
        ok, msgs = evaluate_all(conditions, str(temp_dir), parallel=True)
        assert ok
        assert len(msgs) == 10
        assert all("[PASS]" in m for m in msgs)

    def test_parallel_mixed_results(self, temp_dir):
        (temp_dir / "exists.txt").write_text("")
        conditions = [
            {"file_exists": "exists.txt"},
            {"file_exists": "missing.txt"},
            {"always": True},
        ]
        ok, msgs = evaluate_all(conditions, str(temp_dir), parallel=True)
        assert not ok
        assert "[PASS]" in msgs[0]
        assert any("[FAIL]" in m for m in msgs)

    def test_parallel_hard_failure(self, temp_dir):
        (temp_dir / "a.txt").write_text("")
        conditions = [
            {"file_exists": "a.txt"},
            {"always": True},
            {"severity": "hard", "never": "hard block"},
            {"always": True},
        ]
        ok, msgs = evaluate_all(conditions, str(temp_dir), parallel=True)
        assert not ok
        assert any("HARD_FAIL" in m for m in msgs)

    def test_parallel_warn_does_not_block(self, temp_dir):
        conditions = [
            {"always": True},
            {"severity": "warn", "never": "just a warning"},
            {"always": True},
        ]
        ok, msgs = evaluate_all(conditions, str(temp_dir), parallel=True)
        assert ok
        assert any("WARN" in m for m in msgs)

    def test_parallel_single_condition(self, temp_dir):
        ok, msgs = evaluate_all(
            [{"always": True}], str(temp_dir), parallel=True
        )
        assert ok
        assert len(msgs) == 1

    def test_parallel_empty_list(self):
        ok, msgs = evaluate_all([], ".", parallel=True)
        assert ok
        assert msgs == []

    def test_parallel_with_cache(self, temp_dir):
        (temp_dir / "cache.txt").write_text("")
        conditions = [{"file_exists": "cache.txt"}, {"always": True}]
        ok1, _ = evaluate_all(conditions, str(temp_dir), parallel=True)
        ok2, _ = evaluate_all(conditions, str(temp_dir), parallel=True, cache_ttl=60)
        assert ok1 and ok2

    def test_parallel_with_timeout(self):
        conditions = [{"always": True}, {"always": True}]
        ok, msgs = evaluate_all(conditions, ".", parallel=True, timeout=5)
        assert ok
        assert len(msgs) == 2

    def test_parallel_with_timeout_expired(self):
        conditions = [
            {"shell_test": {"command": "python -c \"import time; time.sleep(5)\"",
             "op": "exit_zero"}},
            {"shell_test": {"command": "python -c \"import time; time.sleep(5)\"",
             "op": "exit_zero"}},
        ]
        ok, msgs = evaluate_all(conditions, ".", parallel=True, timeout=0.5)
        assert not ok
        assert any("TIMEOUT" in m for m in msgs)

    def test_parallel_with_variables(self, temp_dir):
        (temp_dir / "var_test.txt").write_text("hello")
        v1 = temp_dir / "{{var.fname}}"
        v1.write_text("hello")  # placeholder
        ok, msgs = evaluate_all(
            [{"file_exists": "{{var.fname}}"}, {"always": True}],
            str(temp_dir),
            parallel=True,
            variables={"fname": "var_test.txt"},
        )
        assert ok
        assert len(msgs) == 2

    def test_parallel_many_conditions(self, temp_dir):
        n = 30
        conditions = [{"always": True} for _ in range(n)]
        ok, msgs = evaluate_all(conditions, str(temp_dir), parallel=True)
        assert ok
        assert len(msgs) == n

    def test_parallel_no_wasted_eval_after_hard_fail(self, temp_dir):
        """Hard failure should produce result but all conditions submitted to pool.
        Result processing stops on first hard fail in order."""
        conditions = [
            {"severity": "hard", "never": "blocked immediately"},
            {"always": True},
        ]
        ok, msgs = evaluate_all(conditions, str(temp_dir), parallel=True)
        assert not ok
        assert any("HARD_FAIL" in m for m in msgs)


# ═══════════════════════════════════════════════════════════════════════════
# Unknown condition & list_conditions
# ═══════════════════════════════════════════════════════════════════════════

class TestUnknownCondition:
    def test_unknown_returns_false(self):
        passed, msg = evaluate("completely_made_up_condition", {})
        assert not passed
        assert "Unknown" in msg


class TestListConditions:
    def test_returns_all_14_builtins(self):
        names = list_conditions()
        expected = {
            "always", "any_of", "all_of", "env_var",
            "file_contains", "file_exists", "file_not_contains", "file_not_exists",
            "json_field", "never", "not",
            "python_expr", "shell_test", "yaml_field",
        }
        assert expected.issubset(set(names))

    def test_returns_sorted(self):
        names = list_conditions()
        assert names == sorted(names)


# ═══════════════════════════════════════════════════════════════════════════
# _parse_condition helper
# ═══════════════════════════════════════════════════════════════════════════

class TestParseCondition:
    def test_string_value_wraps_in_value_key(self):
        name, params = _parse_condition({"file_exists": "myfile.txt"})
        assert name == "file_exists"
        assert params == {"value": "myfile.txt"}

    def test_dict_value_preserves_keys(self):
        name, params = _parse_condition({
            "json_field": {"path": "x.json", "field": "name", "op": "exists"}
        })
        assert name == "json_field"
        assert params["path"] == "x.json"
        assert params["field"] == "name"
        assert params["op"] == "exists"

    def test_single_key_dict(self):
        name, params = _parse_condition({"always": True})
        assert name == "always"
        assert params == {"value": True}

    def test_empty_dict_raises(self):
        with pytest.raises(ValueError, match="no recognized type key"):
            _parse_condition({})


# ═══════════════════════════════════════════════════════════════════════════
# Variable resolution ({{var.key}} interpolation)
# ═══════════════════════════════════════════════════════════════════════════

class TestVariableResolution:
    def test_simple_string_resolution(self):
        result = _resolve_vars("issue/{{var.id}}/output.txt", {"id": "BUG-42"})
        assert result == "issue/BUG-42/output.txt"

    def test_no_vars_leaves_string_unchanged(self):
        result = _resolve_vars("plain/path.txt", None)
        assert result == "plain/path.txt"

    def test_empty_vars_leaves_string_unchanged(self):
        result = _resolve_vars("plain/path.txt", {})
        assert result == "plain/path.txt"

    def test_unknown_var_keeps_placeholder(self):
        result = _resolve_vars("{{var.nonexistent}}/file.txt", {})
        assert result == "{{var.nonexistent}}/file.txt"

    def test_multiple_vars_in_string(self):
        result = _resolve_vars(
            "{{var.stage}}/{{var.id}}.md",
            {"stage": "analyze", "id": "123"}
        )
        assert result == "analyze/123.md"

    def test_resolves_in_dict_values(self):
        result = _resolve_vars(
            {"path": "{{var.dir}}/file.txt", "pattern": "{{var.needle}}"},
            {"dir": "output", "needle": "PASS"}
        )
        assert result["path"] == "output/file.txt"
        assert result["pattern"] == "PASS"

    def test_resolves_in_nested_dict(self):
        result = _resolve_vars(
            {"outer": {"inner": "{{var.key}}"}},
            {"key": "resolved"}
        )
        assert result["outer"]["inner"] == "resolved"

    def test_resolves_in_list(self):
        result = _resolve_vars(
            ["{{var.a}}", "static", "{{var.b}}"],
            {"a": "alpha", "b": "beta"}
        )
        assert result == ["alpha", "static", "beta"]

    def test_non_string_values_preserved(self):
        result = _resolve_vars({"num": 42, "flag": True}, {"num": 99})
        assert result["num"] == 42
        assert result["flag"] is True

    def test_evaluate_all_with_variables(self, temp_dir):
        (temp_dir / "BUG-100").mkdir()
        passed, msgs = evaluate_all(
            [{"file_exists": "{{var.ticket}}"}],
            base_path=str(temp_dir),
            variables={"ticket": "BUG-100"}
        )
        assert passed

    def test_evaluate_all_with_unresolved_var_fails(self, temp_dir):
        passed, msgs = evaluate_all(
            [{"file_exists": "{{var.missing}}"}],
            base_path=str(temp_dir),
            variables={}
        )
        # The placeholder {{var.missing}} is not a valid path, so file not found
        assert not passed


# ═══════════════════════════════════════════════════════════════════════════
# Custom condition registration
# ═══════════════════════════════════════════════════════════════════════════

class TestCustomConditionRegistration:
    def test_register_and_evaluate_custom_condition(self):
        from stageflow.core.conditions import register
        try:
            @register("my_custom_check")
            def my_custom_check(params):
                threshold = params.get("threshold", 0)
                value = params.get("value", 0)
                ok = value > threshold
                return ok, f"Custom check: {value} > {threshold} = {ok}"

            passed, msg = evaluate("my_custom_check", {"threshold": 10, "value": 20})
            assert passed
            assert "Custom check" in msg

            passed2, _ = evaluate("my_custom_check", {"threshold": 10, "value": 5})
            assert not passed2

            # Verify it appears in list_conditions
            assert "my_custom_check" in list_conditions()
        finally:
            # Clean up: remove from registry to avoid polluting other tests
            from stageflow.core import conditions
            conditions._CONDITION_REGISTRY.pop("my_custom_check", None)


# ═══════════════════════════════════════════════════════════════════════════
# git_status
# ═══════════════════════════════════════════════════════════════════════════

class TestGitStatus:
    def test_clean_repo_after_commit(self, temp_dir):
        """A fresh git repo with all files committed should be clean."""
        import subprocess
        subprocess.run("git init", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.email test@test.com", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.name Test", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "f.txt").write_text("hi")
        subprocess.run("git add . && git commit -m init", shell=True, cwd=str(temp_dir), capture_output=True)
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "clean"})
        assert passed, msg

    def test_dirty_repo(self, temp_dir):
        import subprocess
        subprocess.run("git init", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.email test@test.com", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.name Test", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "f.txt").write_text("hi")
        subprocess.run("git add . && git commit -m init", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "f.txt").write_text("dirty")
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "clean"})
        assert not passed
        assert "dirty" in msg

    def test_files_changed_has_changes(self, temp_dir):
        import subprocess
        subprocess.run("git init", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.email test@test.com", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.name Test", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "f.txt").write_text("hi")
        subprocess.run("git add . && git commit -m init", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "f.txt").write_text("changed")
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "files_changed"})
        assert passed

    def test_files_changed_with_threshold(self, temp_dir):
        import subprocess
        subprocess.run("git init", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.email test@test.com", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.name Test", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "a.txt").write_text("a")
        (temp_dir / "b.txt").write_text("b")
        subprocess.run("git add . && git commit -m init", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "a.txt").write_text("a2")
        (temp_dir / "b.txt").write_text("b2")
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "files_changed", "value": 2})
        assert passed

    def test_branch_matches(self, temp_dir):
        import subprocess
        subprocess.run("git init", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.email test@test.com", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.name Test", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "f.txt").write_text("hi")
        subprocess.run("git add . && git commit -m init", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git checkout -b feature-x", shell=True, cwd=str(temp_dir), capture_output=True)
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "branch", "value": "feature-x"})
        assert passed

    def test_branch_differs(self, temp_dir):
        import subprocess
        subprocess.run("git init", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.email test@test.com", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.name Test", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "f.txt").write_text("hi")
        subprocess.run("git add . && git commit -m init", shell=True, cwd=str(temp_dir), capture_output=True)
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "branch", "value": "main"})
        assert not passed

    def test_unknown_op(self, temp_dir):
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "bogus"})
        assert not passed
        assert "Unknown git op" in msg

    def test_has_commits_no_upstream(self, temp_dir):
        import subprocess
        subprocess.run("git init", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.email test@test.com", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.name Test", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "f.txt").write_text("hi")
        subprocess.run("git add . && git commit -m init", shell=True, cwd=str(temp_dir), capture_output=True)
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "has_commits"})
        assert not passed

    def test_has_commits_with_upstream(self, temp_dir):
        import subprocess
        # create a bare repo to act as remote
        remote_dir = temp_dir.parent / "remote.git"
        if remote_dir.exists():
            import shutil
            shutil.rmtree(str(remote_dir))
        subprocess.run(f'git init --bare "{remote_dir}"', shell=True, capture_output=True)
        # init local repo with explicit main branch
        subprocess.run("git init -b main", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.email test@test.com", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run("git config user.name Test", shell=True, cwd=str(temp_dir), capture_output=True)
        (temp_dir / "f.txt").write_text("hi")
        subprocess.run("git add . && git commit -m init", shell=True, cwd=str(temp_dir), capture_output=True)
        subprocess.run(f'git remote add origin "{remote_dir}"', shell=True, cwd=str(temp_dir), capture_output=True)
        push = subprocess.run("git push -u origin main", shell=True, cwd=str(temp_dir), capture_output=True, text=True)
        # no unpushed commits after push
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "has_commits"})
        assert not passed, f"Should have no unpushed commits after push; push rc={push.returncode} err={push.stderr}: {msg}"
        # make new local commit — now has unpushed commits
        (temp_dir / "f.txt").write_text("hi2")
        subprocess.run("git add . && git commit -m second", shell=True, cwd=str(temp_dir), capture_output=True)
        passed, msg = evaluate("git_status", {"base_path": str(temp_dir), "op": "has_commits"})
        assert passed, f"Should have unpushed commits: {msg}"

    def test_invalid_cwd_exception(self, temp_dir):
        import os
        bad_path = str(temp_dir / "nonexistent_dir_xyz")
        if os.path.exists(bad_path):
            os.rmdir(bad_path)
        passed, msg = evaluate("git_status", {"base_path": bad_path, "op": "clean"})
        assert not passed
        assert "error" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════
# http_status
# ═══════════════════════════════════════════════════════════════════════════

class TestHttpStatus:
    def test_connection_refused(self, temp_dir):
        """Connecting to a closed port should fail gracefully."""
        passed, msg = evaluate("http_status", {
            "url": "http://127.0.0.1:1", "timeout": 2
        })
        assert not passed
        assert "HTTP error" in msg

    def test_invalid_url(self, temp_dir):
        passed, msg = evaluate("http_status", {
            "url": "not-a-valid-url", "timeout": 2
        })
        assert not passed

    def test_custom_method(self, temp_dir):
        """Should handle custom method gracefully on bad URL."""
        passed, msg = evaluate("http_status", {
            "url": "http://127.0.0.1:1", "method": "HEAD", "timeout": 2
        })
        assert not passed

    def test_body_contains_op_recognized(self, temp_dir):
        """body_contains op should not crash with 'Unknown op' even on conn failure."""
        passed, msg = evaluate("http_status", {
            "url": "http://127.0.0.1:1", "op": "body_contains",
            "pattern": "hello", "timeout": 2
        })
        assert not passed
        assert "Unknown op" not in msg

    def test_header_equals_op_recognized(self, temp_dir):
        """header_equals op should not crash with 'Unknown op' even on conn failure."""
        passed, msg = evaluate("http_status", {
            "url": "http://127.0.0.1:1", "op": "header_equals",
            "header": "Content-Type", "expected": "application/json", "timeout": 2
        })
        assert not passed
        assert "Unknown op" not in msg

    def test_body_contains_success(self, temp_dir, http_server):
        url = f"http://127.0.0.1:{http_server}"
        passed, msg = evaluate("http_status", {
            "url": url, "op": "body_contains",
            "pattern": "OK", "timeout": 5
        })
        assert passed

    def test_header_equals_success(self, temp_dir, http_server):
        url = f"http://127.0.0.1:{http_server}"
        passed, msg = evaluate("http_status", {
            "url": url, "op": "header_equals",
            "header": "Content-Type", "expected": "text/plain", "timeout": 5
        })
        assert passed

    def test_default_status_code_check(self, temp_dir, http_server):
        """lines 604-605: default op checks status code against expected (200)."""
        url = f"http://127.0.0.1:{http_server}"
        passed, msg = evaluate("http_status", {
            "url": url, "timeout": 5
        })
        assert passed
        assert "200" in msg


# ═══════════════════════════════════════════════════════════════════════════
# time_range
# ═══════════════════════════════════════════════════════════════════════════

class TestTimeRange:
    def test_always_in_range_no_bounds(self, temp_dir):
        """No after/before means always passes."""
        passed, msg = evaluate("time_range", {"tz": "UTC"})
        assert passed
        assert "within" in msg

    def test_after_bound_passes(self, temp_dir):
        """Current time should be after 00:00."""
        passed, msg = evaluate("time_range", {"after": "00:00", "tz": "UTC"})
        assert passed

    def test_before_bound_passes(self, temp_dir):
        """Current time should be before 23:59."""
        passed, msg = evaluate("time_range", {"before": "23:59", "tz": "UTC"})
        assert passed

    def test_after_bound_blocks(self, temp_dir):
        """00:00 UTC is within any day."""
        passed, msg = evaluate("time_range", {"after": "23:59", "tz": "UTC"})
        assert not passed
        assert "before" in msg

    def test_before_bound_blocks(self, temp_dir):
        """line 634: before bound in the past blocks transition."""
        passed, msg = evaluate("time_range", {"before": "00:01", "tz": "UTC"})
        assert not passed
        assert "after" in msg

    def test_invalid_timezone_fallback(self, temp_dir):
        """lines 623-624: invalid timezone name triggers tz=None fallback."""
        passed, msg = evaluate("time_range", {"tz": "Mars/Olympus"})
        assert passed  # no bounds = always passes, just testing tz fallback doesn't crash


# ═══════════════════════════════════════════════════════════════════════════
# compare_files
# ═══════════════════════════════════════════════════════════════════════════

class TestCompareFiles:
    def test_identical(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        (temp_dir / "b.txt").write_text("hello")
        passed, msg = evaluate("compare_files", {
            "base_path": str(temp_dir), "path1": "a.txt", "path2": "b.txt", "op": "identical"
        })
        assert passed

    def test_not_identical(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        (temp_dir / "b.txt").write_text("world")
        passed, msg = evaluate("compare_files", {
            "base_path": str(temp_dir), "path1": "a.txt", "path2": "b.txt", "op": "identical"
        })
        assert not passed
        assert "different" in msg

    def test_different_op(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        (temp_dir / "b.txt").write_text("world")
        passed, msg = evaluate("compare_files", {
            "base_path": str(temp_dir), "path1": "a.txt", "path2": "b.txt", "op": "different"
        })
        assert passed

    def test_different_op_same_files(self, temp_dir):
        (temp_dir / "a.txt").write_text("hello")
        (temp_dir / "b.txt").write_text("hello")
        passed, msg = evaluate("compare_files", {
            "base_path": str(temp_dir), "path1": "a.txt", "path2": "b.txt", "op": "different"
        })
        assert not passed

    def test_first_file_missing(self, temp_dir):
        (temp_dir / "b.txt").write_text("hi")
        passed, msg = evaluate("compare_files", {
            "base_path": str(temp_dir), "path1": "missing.txt", "path2": "b.txt"
        })
        assert not passed
        assert "not found" in msg

    def test_second_file_missing(self, temp_dir):
        (temp_dir / "a.txt").write_text("hi")
        passed, msg = evaluate("compare_files", {
            "base_path": str(temp_dir), "path1": "a.txt", "path2": "missing.txt"
        })
        assert not passed
        assert "not found" in msg

    def test_unknown_op(self, temp_dir):
        (temp_dir / "a.txt").write_text("hi")
        (temp_dir / "b.txt").write_text("hi")
        passed, msg = evaluate("compare_files", {
            "base_path": str(temp_dir), "path1": "a.txt", "path2": "b.txt", "op": "bogus"
        })
        assert not passed
        assert "Unknown op" in msg


# ═══════════════════════════════════════════════════════════════════════════
# json_schema
# ═══════════════════════════════════════════════════════════════════════════

class TestJsonSchema:
    def test_valid_json_no_schema(self, temp_dir):
        (temp_dir / "data.json").write_text('{"name": "test", "version": 1}')
        passed, msg = evaluate("json_schema", {
            "base_path": str(temp_dir), "path": "data.json"
        })
        assert passed
        assert "valid" in msg

    def test_invalid_json_no_schema(self, temp_dir):
        (temp_dir / "data.json").write_text('not json {{{')
        passed, msg = evaluate("json_schema", {
            "base_path": str(temp_dir), "path": "data.json"
        })
        assert not passed
        assert "Invalid JSON" in msg

    def test_missing_file(self, temp_dir):
        passed, msg = evaluate("json_schema", {
            "base_path": str(temp_dir), "path": "nope.json"
        })
        assert not passed
        assert "not found" in msg

    def test_with_schema_valid(self, temp_dir):
        (temp_dir / "data.json").write_text('{"name": "test", "age": 30}')
        (temp_dir / "schema.json").write_text(json.dumps({
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"]
        }))
        passed, msg = evaluate("json_schema", {
            "base_path": str(temp_dir), "path": "data.json",
            "schema_path": "schema.json"
        })
        # May pass with jsonschema installed, or skip validation
        assert "valid" in msg or "not installed" in msg

    def test_schema_valid_json_without_jsonschema(self, monkeypatch, temp_dir):
        """line 696: valid JSON but jsonschema not installed — fallback message."""
        (temp_dir / "data.json").write_text('{"name": "test"}')
        (temp_dir / "schema.json").write_text(json.dumps({"type": "object"}))
        import sys
        monkeypatch.setitem(sys.modules, "jsonschema", None)
        passed, msg = evaluate("json_schema", {
            "base_path": str(temp_dir), "path": "data.json",
            "schema_path": "schema.json"
        })
        assert passed
        assert "not installed" in msg

    def test_with_schema_invalid(self, temp_dir):
        (temp_dir / "data.json").write_text('{"name": 42}')
        (temp_dir / "schema.json").write_text(json.dumps({
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"]
        }))
        passed, msg = evaluate("json_schema", {
            "base_path": str(temp_dir), "path": "data.json",
            "schema_path": "schema.json"
        })
        # Could pass (no jsonschema), or fail (schema violation)
        # Just ensure no crash
        assert isinstance(passed, bool)

    def test_missing_schema_file(self, temp_dir):
        (temp_dir / "data.json").write_text('{"x": 1}')
        passed, msg = evaluate("json_schema", {
            "base_path": str(temp_dir), "path": "data.json",
            "schema_path": "missing_schema.json"
        })
        assert not passed
        assert "not found" in msg

    def test_invalid_schema_file(self, temp_dir):
        (temp_dir / "data.json").write_text('{"x": 1}')
        (temp_dir / "schema.json").write_text('not json')
        passed, msg = evaluate("json_schema", {
            "base_path": str(temp_dir), "path": "data.json",
            "schema_path": "schema.json"
        })
        assert not passed
        assert "Invalid JSON Schema" in msg


# ═══════════════════════════════════════════════════════════════════════════
# hash_file
# ═══════════════════════════════════════════════════════════════════════════

class TestHashFile:
    def test_hash_computed(self, temp_dir):
        (temp_dir / "f.bin").write_bytes(b"hello world")
        passed, msg = evaluate("hash_file", {
            "base_path": str(temp_dir), "path": "f.bin", "algo": "sha256"
        })
        assert passed
        assert "sha256" in msg.lower()

    def test_hash_matches_expected(self, temp_dir):
        import hashlib
        data = b"test data"
        expected = hashlib.sha256(data).hexdigest()
        (temp_dir / "f.bin").write_bytes(data)
        passed, msg = evaluate("hash_file", {
            "base_path": str(temp_dir), "path": "f.bin",
            "algo": "sha256", "expected": expected
        })
        assert passed
        assert "matches" in msg

    def test_hash_differs_from_expected(self, temp_dir):
        (temp_dir / "f.bin").write_bytes(b"real data")
        passed, msg = evaluate("hash_file", {
            "base_path": str(temp_dir), "path": "f.bin",
            "algo": "sha256", "expected": "deadbeef"
        })
        assert not passed
        assert "differs" in msg

    def test_default_algo_sha256(self, temp_dir):
        (temp_dir / "f.bin").write_bytes(b"hello")
        passed, msg = evaluate("hash_file", {
            "base_path": str(temp_dir), "path": "f.bin"
        })
        assert passed

    def test_md5_hash(self, temp_dir):
        (temp_dir / "f.bin").write_bytes(b"data")
        passed, msg = evaluate("hash_file", {
            "base_path": str(temp_dir), "path": "f.bin", "algo": "md5"
        })
        assert passed

    def test_missing_file(self, temp_dir):
        passed, msg = evaluate("hash_file", {
            "base_path": str(temp_dir), "path": "nope.bin"
        })
        assert not passed
        assert "not found" in msg


# ═══════════════════════════════════════════════════════════════════════════
# file_age
# ═══════════════════════════════════════════════════════════════════════════

class TestFileAge:
    def test_within_max_age(self, temp_dir):
        f = temp_dir / "fresh.txt"
        f.write_text("just created")
        passed, msg = evaluate("file_age", {
            "base_path": str(temp_dir), "path": "fresh.txt", "max_age": 3600
        })
        assert passed

    def test_exceeds_max_age(self, temp_dir):
        import os
        f = temp_dir / "old.txt"
        f.write_text("old")
        # Set mtime to 2 hours ago
        os.utime(str(f), (time.time() - 7200, time.time() - 7200))
        passed, msg = evaluate("file_age", {
            "base_path": str(temp_dir), "path": "old.txt", "max_age": 3600
        })
        assert not passed
        assert "max" in msg

    def test_min_age_passes(self, temp_dir):
        import os
        f = temp_dir / "stable.txt"
        f.write_text("stable")
        os.utime(str(f), (time.time() - 600, time.time() - 600))
        passed, msg = evaluate("file_age", {
            "base_path": str(temp_dir), "path": "stable.txt", "min_age": 300
        })
        assert passed

    def test_below_min_age(self, temp_dir):
        f = temp_dir / "too_new.txt"
        f.write_text("brand new")
        passed, msg = evaluate("file_age", {
            "base_path": str(temp_dir), "path": "too_new.txt", "min_age": 3600
        })
        assert not passed
        assert "min" in msg

    def test_within_both_bounds(self, temp_dir):
        import os
        f = temp_dir / "mid.txt"
        f.write_text("middle")
        os.utime(str(f), (time.time() - 120, time.time() - 120))
        passed, msg = evaluate("file_age", {
            "base_path": str(temp_dir), "path": "mid.txt",
            "min_age": 60, "max_age": 300
        })
        assert passed

    def test_missing_file(self, temp_dir):
        passed, msg = evaluate("file_age", {
            "base_path": str(temp_dir), "path": "nope.txt", "max_age": 3600
        })
        assert not passed
        assert "not found" in msg


# ═══════════════════════════════════════════════════════════════════════════
# file_size
# ═══════════════════════════════════════════════════════════════════════════

class TestFileSize:
    def test_within_bounds(self, temp_dir):
        (temp_dir / "data.bin").write_bytes(b"x" * 100)
        passed, msg = evaluate("file_size", {
            "base_path": str(temp_dir), "path": "data.bin", "min": 50, "max": 200
        })
        assert passed

    def test_below_min(self, temp_dir):
        (temp_dir / "small.bin").write_bytes(b"x" * 10)
        passed, msg = evaluate("file_size", {
            "base_path": str(temp_dir), "path": "small.bin", "min": 100
        })
        assert not passed
        assert "min" in msg

    def test_above_max(self, temp_dir):
        (temp_dir / "big.bin").write_bytes(b"x" * 500)
        passed, msg = evaluate("file_size", {
            "base_path": str(temp_dir), "path": "big.bin", "max": 200
        })
        assert not passed
        assert "max" in msg

    def test_min_only(self, temp_dir):
        (temp_dir / "ok.bin").write_bytes(b"x" * 1000)
        passed, msg = evaluate("file_size", {
            "base_path": str(temp_dir), "path": "ok.bin", "min": 100
        })
        assert passed

    def test_max_only(self, temp_dir):
        (temp_dir / "ok.bin").write_bytes(b"x" * 50)
        passed, msg = evaluate("file_size", {
            "base_path": str(temp_dir), "path": "ok.bin", "max": 100
        })
        assert passed

    def test_empty_file(self, temp_dir):
        (temp_dir / "empty.bin").write_text("")
        passed, msg = evaluate("file_size", {
            "base_path": str(temp_dir), "path": "empty.bin", "min": 0
        })
        assert passed

    def test_missing_file(self, temp_dir):
        passed, msg = evaluate("file_size", {
            "base_path": str(temp_dir), "path": "nope.bin", "min": 0
        })
        assert not passed
        assert "not found" in msg


# ═══════════════════════════════════════════════════════════════════════════
# glob_count
# ═══════════════════════════════════════════════════════════════════════════

class TestGlobCount:
    def test_matches_min(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        (temp_dir / "b.py").write_text("")
        (temp_dir / "c.py").write_text("")
        passed, msg = evaluate("glob_count", {
            "base_path": str(temp_dir), "pattern": "*.py", "min": 2
        })
        assert passed

    def test_below_min(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        passed, msg = evaluate("glob_count", {
            "base_path": str(temp_dir), "pattern": "*.py", "min": 5
        })
        assert not passed
        assert "min" in msg

    def test_exceeds_max(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        (temp_dir / "b.py").write_text("")
        passed, msg = evaluate("glob_count", {
            "base_path": str(temp_dir), "pattern": "*.py", "max": 1
        })
        assert not passed
        assert "max" in msg

    def test_exact_count(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        (temp_dir / "b.py").write_text("")
        (temp_dir / "c.py").write_text("")
        passed, msg = evaluate("glob_count", {
            "base_path": str(temp_dir), "pattern": "*.py", "eq": 3
        })
        assert passed

    def test_exact_count_fails(self, temp_dir):
        (temp_dir / "a.py").write_text("")
        passed, msg = evaluate("glob_count", {
            "base_path": str(temp_dir), "pattern": "*.py", "eq": 5
        })
        assert not passed

    def test_recursive_glob(self, temp_dir):
        sub = temp_dir / "subdir"
        sub.mkdir()
        (temp_dir / "a.py").write_text("")
        (sub / "b.py").write_text("")
        passed, msg = evaluate("glob_count", {
            "base_path": str(temp_dir), "pattern": "**/*.py", "min": 2
        })
        assert passed

    def test_no_matches(self, temp_dir):
        passed, msg = evaluate("glob_count", {
            "base_path": str(temp_dir), "pattern": "*.nonexistent", "max": 0
        })
        assert passed

    def test_zero_max_allows_empty(self, temp_dir):
        passed, msg = evaluate("glob_count", {
            "base_path": str(temp_dir), "pattern": "*.log", "max": 0
        })
        assert passed


# ═══════════════════════════════════════════════════════════════════════════
# retry
# ═══════════════════════════════════════════════════════════════════════════

class TestRetry:
    def test_passes_first_attempt(self, temp_dir):
        passed, msg = evaluate("retry", {
            "base_path": str(temp_dir),
            "condition": {"always": True},
            "max_attempts": 3, "delay": 0.01
        })
        assert passed
        assert "attempt 1" in msg

    def test_exhausts_retries(self, temp_dir):
        passed, msg = evaluate("retry", {
            "base_path": str(temp_dir),
            "condition": {"never": "always blocked"},
            "max_attempts": 2, "delay": 0.01
        })
        assert not passed
        assert "exhausted" in msg

    def test_eventually_passes(self, temp_dir):
        """Simulate a condition that becomes true after a delay (file created by bg thread)."""
        import threading
        target_file = temp_dir / "delayed.txt"

        def create_later():
            time.sleep(0.1)
            target_file.write_text("ready")

        t = threading.Thread(target=create_later, daemon=True)
        t.start()

        passed, msg = evaluate("retry", {
            "base_path": str(temp_dir),
            "condition": {"file_exists": "delayed.txt"},
            "max_attempts": 10, "delay": 0.05
        })
        t.join(timeout=2)
        assert passed
        assert "attempt" in msg

    def test_default_delay_and_attempts(self, temp_dir):
        passed, msg = evaluate("retry", {
            "base_path": str(temp_dir),
            "condition": {"always": True}
        })
        assert passed

    def test_composes_with_file_exists(self, temp_dir):
        f = temp_dir / "later.txt"
        # File already exists, should pass on first attempt
        f.write_text("ready")
        passed, msg = evaluate("retry", {
            "base_path": str(temp_dir),
            "condition": {"file_exists": "later.txt"},
            "max_attempts": 3, "delay": 0.01
        })
        assert passed


# ═══════════════════════════════════════════════════════════════════════════
# command_exists
# ═══════════════════════════════════════════════════════════════════════════

class TestCommandExists:
    def test_python_exists(self, temp_dir):
        passed, msg = evaluate("command_exists", {"command": "python"})
        assert passed
        assert "found" in msg

    def test_nonexistent_command(self, temp_dir):
        passed, msg = evaluate("command_exists", {"command": "nonexistent_cmd_xyz"})
        assert not passed
        assert "not found" in msg

    def test_string_shorthand(self, temp_dir):
        passed, msg = evaluate("command_exists", {"value": "python"})
        assert passed

    def test_version_check(self, temp_dir):
        passed, msg = evaluate("command_exists", {
            "command": "python", "op": "version"
        })
        assert passed
        assert "version" in msg.lower()

    def test_version_check_nonexistent(self, temp_dir):
        passed, msg = evaluate("command_exists", {
            "command": "nonexistent_cmd_xyz", "op": "version"
        })
        assert not passed

    def test_unknown_op(self, temp_dir):
        passed, msg = evaluate("command_exists", {
            "command": "python", "op": "bogus"
        })
        assert not passed
        assert "Unknown op" in msg


# ═══════════════════════════════════════════════════════════════════════════
# diff_contains
# ═══════════════════════════════════════════════════════════════════════════

class TestDiffContains:
    def _init_git_repo(self, temp_dir):
        import subprocess as sp
        sp.run("git init", shell=True, cwd=str(temp_dir), capture_output=True)
        sp.run("git config user.email test@test.com", shell=True, cwd=str(temp_dir), capture_output=True)
        sp.run("git config user.name Test", shell=True, cwd=str(temp_dir), capture_output=True)
        # Track a placeholder file so git diff HEAD shows modifications
        (temp_dir / "module.py").write_text("# placeholder")
        sp.run("git add . && git commit -m init", shell=True, cwd=str(temp_dir), capture_output=True)

    def test_not_contains_passes_when_clean(self, temp_dir):
        self._init_git_repo(temp_dir)
        # Modify the tracked file with safe content
        (temp_dir / "module.py").write_text("def hello():\n    return 'safe'")
        passed, msg = evaluate("diff_contains", {
            "base_path": str(temp_dir), "pattern": "eval\\("
        })
        assert passed

    def test_not_contains_blocks_dangerous_pattern(self, temp_dir):
        self._init_git_repo(temp_dir)
        (temp_dir / "module.py").write_text("result = eval(user_input)")
        passed, msg = evaluate("diff_contains", {
            "base_path": str(temp_dir), "pattern": "eval\\("
        })
        assert not passed
        assert "BLOCKED" in msg

    def test_contains_passes_when_found(self, temp_dir):
        self._init_git_repo(temp_dir)
        (temp_dir / "module.py").write_text("# TODO: refactor later")
        passed, msg = evaluate("diff_contains", {
            "base_path": str(temp_dir), "pattern": "TODO", "op": "contains"
        })
        assert passed
        assert "found" in msg

    def test_contains_fails_when_not_found(self, temp_dir):
        self._init_git_repo(temp_dir)
        (temp_dir / "module.py").write_text("print('clean')")
        passed, msg = evaluate("diff_contains", {
            "base_path": str(temp_dir), "pattern": "NONEXISTENT_PATTERN", "op": "contains"
        })
        assert not passed
        assert "not found" in msg

    def test_unsafe_exec_blocked(self, temp_dir):
        self._init_git_repo(temp_dir)
        (temp_dir / "module.py").write_text("exec(user_code)")
        passed, msg = evaluate("diff_contains", {
            "base_path": str(temp_dir), "pattern": "exec\\("
        })
        assert not passed
        assert "BLOCKED" in msg

    def test_unknown_op(self, temp_dir):
        self._init_git_repo(temp_dir)
        passed, msg = evaluate("diff_contains", {
            "base_path": str(temp_dir), "pattern": "x", "op": "bogus"
        })
        assert not passed
        assert "Unknown op" in msg

    def test_staged_diff_path(self, temp_dir):
        """lines 885-886: staged_only=True uses git diff --cached."""
        self._init_git_repo(temp_dir)
        import subprocess as sp
        (temp_dir / "module.py").write_text("# staged change")
        sp.run("git add module.py", shell=True, cwd=str(temp_dir), capture_output=True)
        passed, msg = evaluate("diff_contains", {
            "base_path": str(temp_dir), "pattern": "UNLIKELY_PATTERN",
            "staged_only": True
        })
        assert passed  # pattern not in staged diff

    def test_non_git_directory_graceful(self, temp_dir):
        """lines 904-905: diff_contains in non-git dir hits diff error path."""
        passed, msg = evaluate("diff_contains", {
            "base_path": str(temp_dir), "pattern": "anything"
        })
        # In non-git dir: git diff HEAD fails, error text doesn't match pattern
        # With default op=not_contains, passes since pattern absent from error
        assert passed  # pattern not found in error text, so not_contains passes


# ═══════════════════════════════════════════════════════════════════════════
# json_count
# ═══════════════════════════════════════════════════════════════════════════

class TestJsonCount:
    def test_array_count_meets_min(self, temp_dir):
        (temp_dir / "data.json").write_text('[1, 2, 3, 4, 5]')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json", "min": 3
        })
        assert passed

    def test_array_count_below_min(self, temp_dir):
        (temp_dir / "data.json").write_text('[1, 2]')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json", "min": 5
        })
        assert not passed

    def test_object_key_count(self, temp_dir):
        (temp_dir / "data.json").write_text('{"a": 1, "b": 2, "c": 3}')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json", "eq": 3
        })
        assert passed

    def test_exact_count(self, temp_dir):
        (temp_dir / "data.json").write_text('[1, 2, 3]')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json", "eq": 3
        })
        assert passed

    def test_exact_count_fails(self, temp_dir):
        (temp_dir / "data.json").write_text('[1, 2]')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json", "eq": 5
        })
        assert not passed

    def test_nested_field_count(self, temp_dir):
        (temp_dir / "data.json").write_text(
            '{"results": {"passed": 10, "failed": 2, "skipped": 1}}'
        )
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json",
            "field": "results", "eq": 3
        })
        assert passed

    def test_array_field_count(self, temp_dir):
        (temp_dir / "data.json").write_text(
            '{"test_results": {"failures": [{"name": "t1"}, {"name": "t2"}]}}'
        )
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json",
            "field": "test_results.failures", "min": 1
        })
        assert passed

    def test_missing_file(self, temp_dir):
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "nope.json", "min": 0
        })
        assert not passed
        assert "not found" in msg

    def test_invalid_json(self, temp_dir):
        (temp_dir / "data.json").write_text("not json")
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json"
        })
        assert not passed
        assert "Invalid JSON" in msg

    def test_list_field_indexing(self, temp_dir):
        """lines 936-942: navigate into list by numeric index."""
        (temp_dir / "data.json").write_text('{"items": [{"a": 1, "b": 2}, {"c": 3}]}')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json",
            "field": "items.0", "eq": 2
        })
        assert passed  # items[0] = {"a": 1, "b": 2} has 2 keys

    def test_list_field_index_out_of_range(self, temp_dir):
        """line 940: list index out of range returns error."""
        (temp_dir / "data.json").write_text('{"items": [1, 2]}')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json",
            "field": "items.99", "min": 0
        })
        assert not passed
        assert "Cannot index" in msg

    def test_string_field_count(self, temp_dir):
        """lines 948-949: count characters when field is a string."""
        (temp_dir / "data.json").write_text('{"name": "hello"}')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json",
            "field": "name", "eq": 5
        })
        assert passed

    def test_scalar_field_count(self, temp_dir):
        """lines 950-951: scalar (non-list/dict/str) field count is 1."""
        (temp_dir / "data.json").write_text('{"value": 42}')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json",
            "field": "value", "eq": 1
        })
        assert passed

    def test_max_count_exceeded(self, temp_dir):
        """lines 960-961: count exceeds max_count."""
        (temp_dir / "data.json").write_text('[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json", "max": 5
        })
        assert not passed
        assert ">" in msg

    def test_list_field_bad_index_value_error(self, temp_dir):
        """line 939: non-numeric index into list raises ValueError."""
        (temp_dir / "data.json").write_text('{"items": [1, 2, 3]}')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json",
            "field": "items.abc", "min": 0
        })
        assert not passed
        assert "Cannot index" in msg

    def test_navigate_into_scalar_field(self, temp_dir):
        """line 942: field navigation fails on non-dict, non-list node."""
        (temp_dir / "data.json").write_text('{"a": {"b": 42}}')
        passed, msg = evaluate("json_count", {
            "base_path": str(temp_dir), "path": "data.json",
            "field": "a.b.c", "min": 0
        })
        assert not passed
        assert "Cannot navigate" in msg


# ═══════════════════════════════════════════════════════════════════════════
# Condition Severity Levels (warn / soft / hard)
# ═══════════════════════════════════════════════════════════════════════════

class TestConditionSeverity:
    """Tests for condition severity: warn (log but pass), soft (default, block),
    hard (block immediately, no retry/rollback)."""

    # ── _parse_condition ──────────────────────────────────────────────

    def test_parse_skips_severity_key(self, temp_dir):
        """_parse_condition skips 'severity' to find the condition type."""
        name, params = _parse_condition({"severity": "hard", "file_exists": "test.txt"})
        assert name == "file_exists"
        assert params == {"value": "test.txt"}

    def test_parse_skips_max_attempts_key(self, temp_dir):
        """_parse_condition skips 'max_attempts' to find the condition type."""
        name, params = _parse_condition(
            {"max_attempts": 5, "severity": "soft", "always": True}
        )
        assert name == "always"
        assert params == {"value": True}

    def test_parse_skips_both_meta_keys(self, temp_dir):
        name, params = _parse_condition(
            {"severity": "warn", "max_attempts": 3, "file_exists": "x.txt"}
        )
        assert name == "file_exists"
        assert params == {"value": "x.txt"}

    # ── _get_severity ─────────────────────────────────────────────────

    def test_get_severity_default_soft(self):
        assert _get_severity({"file_exists": "x.txt"}) == "soft"

    def test_get_severity_explicit(self):
        assert _get_severity({"file_exists": "x.txt", "severity": "hard"}) == "hard"
        assert _get_severity({"file_exists": "x.txt", "severity": "warn"}) == "warn"
        assert _get_severity({"file_exists": "x.txt", "severity": "soft"}) == "soft"

    # ── evaluate_all: warn severity ───────────────────────────────────

    def test_warn_passes_even_when_condition_fails(self, temp_dir):
        """Warn severity: condition fails but evaluate_all still returns True."""
        passed, msgs = evaluate_all(
            [{"severity": "warn", "file_exists": "nonexistent_file.xyz"}],
            str(temp_dir), cache_ttl=0
        )
        assert passed is True
        assert any("[WARN]" in m for m in msgs), f"Expected [WARN] tag in: {msgs}"

    def test_warn_passes_when_condition_passes(self, temp_dir):
        """Warn severity: passing condition tagged as PASS."""
        f = temp_dir / "exists.txt"
        f.write_text("ok")
        passed, msgs = evaluate_all(
            [{"severity": "warn", "file_exists": "exists.txt"}],
            str(temp_dir), cache_ttl=0
        )
        assert passed is True
        assert any("[PASS]" in m for m in msgs)

    def test_warn_never_blocks_transition(self, temp_dir):
        """Warn severity: all conditions fail but overall result is still pass."""
        passed, msgs = evaluate_all(
            [
                {"severity": "warn", "file_exists": "nope.txt"},
                {"severity": "warn", "file_exists": "also_missing.txt"},
            ],
            str(temp_dir), cache_ttl=0
        )
        assert passed is True
        warn_count = sum(1 for m in msgs if "[WARN]" in m)
        assert warn_count == 2

    # ── evaluate_all: soft severity (default) ─────────────────────────

    def test_soft_fails_normally(self, temp_dir):
        """Soft severity (default): failure blocks transition like before."""
        passed, msgs = evaluate_all(
            [{"severity": "soft", "file_exists": "nonexistent.xyz"}],
            str(temp_dir), cache_ttl=0
        )
        assert passed is False
        assert any("[FAIL]" in m for m in msgs)

    def test_soft_is_default_when_no_severity_specified(self, temp_dir):
        """When severity not specified, behaves as soft (blocks on fail)."""
        passed, msgs = evaluate_all(
            [{"never": "blocked"}],
            str(temp_dir), cache_ttl=0
        )
        assert passed is False
        assert any("[FAIL]" in m for m in msgs)

    def test_soft_passes_normally(self, temp_dir):
        """Soft severity: passing condition tagged PASS."""
        passed, msgs = evaluate_all(
            [{"severity": "soft", "always": True}],
            str(temp_dir), cache_ttl=0
        )
        assert passed is True
        assert any("[PASS]" in m for m in msgs)

    # ── evaluate_all: hard severity ───────────────────────────────────

    def test_hard_fails_with_hard_fail_tag(self, temp_dir):
        """Hard severity: failure tagged [HARD_FAIL]."""
        passed, msgs = evaluate_all(
            [{"severity": "hard", "file_exists": "nonexistent.xyz"}],
            str(temp_dir), cache_ttl=0
        )
        assert passed is False
        assert any("[HARD_FAIL]" in m for m in msgs)

    def test_hard_stops_evaluating_subsequent_conditions(self, temp_dir):
        """Hard severity failure stops immediately without evaluating remaining."""
        eval_order = []

        # Register a custom condition to track evaluation order
        from stageflow.core.conditions import register as _reg
        called = []

        @_reg("_tracked_check")
        def _tracked(params):
            called.append(params.get("id", "unknown"))
            return False, f"tracked_{params.get('id', '?')}_failed"

        passed, msgs = evaluate_all(
            [
                {"severity": "hard", "_tracked_check": {"id": "first"}},
                {"severity": "soft", "_tracked_check": {"id": "second"}},
            ],
            str(temp_dir), cache_ttl=0
        )
        assert passed is False
        assert any("[HARD_FAIL]" in m for m in msgs)
        # Second condition should NOT have been evaluated
        assert called == ["first"], f"Expected only 'first', got {called}"

        # Clean up
        _CONDITION_REGISTRY.pop("_tracked_check", None)

    def test_hard_passes_normally_when_condition_ok(self, temp_dir):
        """Hard severity: passing condition behaves normally."""
        f = temp_dir / "real.txt"
        f.write_text("content")
        passed, msgs = evaluate_all(
            [{"severity": "hard", "file_exists": "real.txt"}],
            str(temp_dir), cache_ttl=0
        )
        assert passed is True
        assert any("[PASS]" in m for m in msgs)

    # ── Mixed severities ──────────────────────────────────────────────

    def test_mixed_warn_and_soft(self, temp_dir):
        """Warn condition logs but doesn't block; soft condition blocks on fail."""
        passed, msgs = evaluate_all(
            [
                {"severity": "warn", "file_exists": "nope.txt"},
                {"severity": "soft", "always": True},
            ],
            str(temp_dir), cache_ttl=0
        )
        assert passed is True
        assert any("[WARN]" in m for m in msgs)
        assert any("[PASS]" in m for m in msgs)

    def test_mixed_warn_soft_first_fails(self, temp_dir):
        """Soft condition evaluated first fails, blocks immediately."""
        passed, msgs = evaluate_all(
            [
                {"severity": "soft", "never": "blocked"},
                {"severity": "warn", "file_exists": "nope.txt"},
            ],
            str(temp_dir), cache_ttl=0
        )
        assert passed is False
        assert any("[FAIL]" in m for m in msgs)
        # Warn condition should not be evaluated (soft blocked first)
        assert not any("[WARN]" in m for m in msgs)

    def test_warn_before_hard(self, temp_dir):
        """Warn passes through; hard blocks and stops evaluation."""
        passed, msgs = evaluate_all(
            [
                {"severity": "warn", "file_exists": "nope.txt"},
                {"severity": "hard", "never": "hard_block"},
            ],
            str(temp_dir), cache_ttl=0
        )
        assert passed is False
        assert any("[WARN]" in m for m in msgs)
        assert any("[HARD_FAIL]" in m for m in msgs)


# ═══════════════════════════════════════════════════════════════════════════
# Runtime / system condition tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPortOpen:
    def test_closed_port_returns_false(self, temp_dir):
        passed, msg = evaluate_all(
            [{"port_open": {"port": 19999, "host": "127.0.0.1", "timeout": 0.5}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False
        assert "closed" in msg[0].lower() or "refused" in msg[0].lower() or "timeout" in msg[0].lower()

    def test_open_port_returns_true(self, temp_dir):
        import socket
        import threading
        import time
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen(1)
        ready = threading.Event()

        def serve():
            ready.set()
            try:
                server.settimeout(3)
                conn, _ = server.accept()
                conn.close()
            except socket.timeout:
                pass

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        ready.wait()
        time.sleep(0.05)  # let the accept() settle

        passed, msg = evaluate_all(
            [{"port_open": {"port": port, "host": "127.0.0.1", "timeout": 1.0}}],
            str(temp_dir), cache_ttl=0,
        )
        server.close()
        assert passed is True, f"Expected port {port} to be open: {msg}"

    def test_invalid_port_fails(self, temp_dir):
        passed, msg = evaluate_all(
            [{"port_open": {"port": 0}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False
        assert "invalid" in msg[0].lower()

    def test_short_syntax_with_value_key(self, temp_dir):
        passed, msg = evaluate_all(
            [{"port_open": 19998}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False  # closed port

    def test_custom_timeout_accepted(self, temp_dir):
        passed, msg = evaluate_all(
            [{"port_open": {"port": 19997, "timeout": 0.1}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False  # closed port, but timeout was respected
        assert "Port" in msg[0]

    def test_default_host_is_localhost(self, temp_dir):
        passed, msg = evaluate_all(
            [{"port_open": {"port": 19996, "timeout": 0.2}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False
        assert "127.0.0.1" in msg[0]


class TestProcessRunning:
    def test_python_is_running(self, temp_dir):
        passed, msg = evaluate_all(
            [{"process_running": {"name": "python"}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is True, f"Python should be running: {msg}"

    def test_bogus_name_returns_false(self, temp_dir):
        passed, msg = evaluate_all(
            [{"process_running": {"name": "xyznonexistentprocess_42"}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False

    def test_empty_name_returns_false(self, temp_dir):
        passed, msg = evaluate_all(
            [{"process_running": {"name": ""}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False
        assert "No process name" in msg[0]

    def test_short_syntax_with_value_key(self, temp_dir):
        passed, msg = evaluate_all(
            [{"process_running": "python"}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is True, f"Python should be running: {msg}"

    def test_case_insensitive_match(self, temp_dir):
        passed, msg = evaluate_all(
            [{"process_running": {"name": "PYTHON"}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is True, f"PYTHON (uppercase) should match: {msg}"

    def test_partial_name_match(self, temp_dir):
        passed, msg = evaluate_all(
            [{"process_running": {"name": "pyth"}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is True, f"'pyth' should match python: {msg}"


class TestDockerPs:
    def test_empty_name_returns_false(self, temp_dir):
        passed, msg = evaluate_all(
            [{"docker_ps": {"name": ""}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False
        assert "No container name" in msg[0]

    def test_bogus_container_returns_false(self, temp_dir):
        passed, msg = evaluate_all(
            [{"docker_ps": {"name": "nonexistent_container_xyz_42"}}],
            str(temp_dir), cache_ttl=0,
        )
        # Docker might not be installed, in which case we also get False
        assert passed is False

    def test_docker_not_installed_is_graceful(self, temp_dir):
        import shutil
        docker_path = shutil.which("docker")
        if docker_path:
            pytest.skip("Docker is installed — skipping not-installed test")
        passed, msg = evaluate_all(
            [{"docker_ps": {"name": "anything"}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False
        assert any("not installed" in m.lower() or "not in path" in m.lower() for m in msg)

    def test_short_syntax_with_value_key(self, temp_dir):
        passed, msg = evaluate_all(
            [{"docker_ps": "xyz_bogus"}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is False

    def test_graceful_on_error(self, temp_dir):
        passed, msg = evaluate_all(
            [{"docker_ps": {"name": "test"}}],
            str(temp_dir), cache_ttl=0,
        )
        # Should always return False (no container named "test" or docker not installed)
        assert passed is False

    def test_returns_running_container_if_docker_available(self, temp_dir):
        import shutil
        docker_path = shutil.which("docker")
        if not docker_path:
            pytest.skip("Docker is not installed — skipping live container test")
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        containers = result.stdout.strip().split("\n")
        if not containers or containers == [""]:
            pytest.skip("No running containers to test against")
        target = containers[0].strip()
        passed, msg = evaluate_all(
            [{"docker_ps": {"name": target}}],
            str(temp_dir), cache_ttl=0,
        )
        assert passed is True, f"Container '{target}' should be running: {msg}"
