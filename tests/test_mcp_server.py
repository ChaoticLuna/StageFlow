"""Tests for the StageFlow MCP server integration."""

from __future__ import annotations

import pytest


class TestMCPServerCreation:
    def test_create_mcp_server_returns_fastmcp_instance(self):
        from stageflow.mcp_server import create_mcp_server
        from mcp.server.fastmcp import FastMCP
        mcp = create_mcp_server()
        assert isinstance(mcp, FastMCP)
        assert mcp.name == "StageFlow"

    def test_create_mcp_server_has_three_tools(self):
        from stageflow.mcp_server import create_mcp_server
        mcp = create_mcp_server()
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "stageflow_evaluate" in tool_names
        assert "stageflow_list_conditions" in tool_names
        assert "stageflow_evaluate_all" in tool_names


class TestMCPToolsDirectly:
    """Test the tool functions directly (not through MCP protocol)."""

    def test_evaluate_condition_passes(self):
        from stageflow.core.conditions import evaluate
        passed, msg = evaluate("always", {"value": True})
        assert passed is True

    def test_evaluate_condition_fails(self):
        from stageflow.core.conditions import evaluate
        passed, msg = evaluate("never", {"value": "test reason"})
        assert passed is False

    def test_list_conditions_includes_always(self):
        from stageflow.core.conditions import list_conditions
        names = list_conditions()
        assert "always" in names
        assert "never" in names
        assert "file_exists" in names

    def test_evaluate_all_with_parallel(self, temp_dir):
        from stageflow.core.conditions import evaluate_all
        ok, msgs = evaluate_all(
            [{"always": True}, {"always": True}],
            str(temp_dir),
            parallel=True,
        )
        assert ok
        assert len(msgs) == 2


class TestMCPModuleImports:
    def test_serve_function_exists(self):
        from stageflow.mcp_server import serve
        assert callable(serve)

    def test_create_mcp_server_function_exists(self):
        from stageflow.mcp_server import create_mcp_server
        assert callable(create_mcp_server)


class TestMCPCLIIntegration:
    """Test that mcp subcommand is registered and help doesn't crash."""

    def test_mcp_subcommand_help(self):
        import subprocess, sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        r = subprocess.run(
            [sys.executable, "-m", "stageflow", "mcp", "--help"],
            capture_output=True, text=True,
            cwd=str(project_root),
            timeout=15,
        )
        assert r.returncode == 0, r.stderr
        assert "mcp" in r.stdout.lower()

    def test_mcp_is_listed_in_main_help(self):
        import subprocess, sys
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        r = subprocess.run(
            [sys.executable, "-m", "stageflow", "--help"],
            capture_output=True, text=True,
            cwd=str(project_root),
            timeout=15,
        )
        assert r.returncode == 0, r.stderr
        assert "mcp" in r.stdout.lower()

    def test_mcp_module_runs_without_error_when_imported(self):
        import importlib
        mod = importlib.import_module("stageflow.mcp_server")
        assert hasattr(mod, "create_mcp_server")
        assert hasattr(mod, "serve")
