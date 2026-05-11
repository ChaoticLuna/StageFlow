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


class TestMCPServe:
    """Test the serve() function without actually starting a blocking stdio server."""

    def test_serve_creates_mcp_and_calls_run(self):
        from unittest.mock import patch, MagicMock
        with patch('stageflow.mcp_server.create_mcp_server') as mock_create:
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            from stageflow.mcp_server import serve
            serve()
            mock_create.assert_called_once()
            mock_mcp.run.assert_called_once_with(transport="stdio")

    def test_serve_calls_run_with_stdio(self):
        from unittest.mock import patch
        with patch('mcp.server.fastmcp.FastMCP.run') as mock_run:
            from stageflow.mcp_server import serve
            serve()
            mock_run.assert_called_once_with(transport="stdio")


class TestMCPToolsInnerFunctions:
    """Exercise the tool closure bodies inside create_mcp_server() via fn directly."""

    def test_evaluate_tool_body_success(self):
        from stageflow.mcp_server import create_mcp_server
        mcp = create_mcp_server()
        tool = mcp._tool_manager.get_tool("stageflow_evaluate")
        result = tool.fn(name="always", params={"value": True})
        assert result["passed"] is True
        assert result["condition"] == "always"

    def test_evaluate_tool_body_failure(self):
        from stageflow.mcp_server import create_mcp_server
        mcp = create_mcp_server()
        tool = mcp._tool_manager.get_tool("stageflow_evaluate")
        result = tool.fn(name="never", params={"value": "no"})
        assert result["passed"] is False
        assert "no" in result["message"]

    def test_list_conditions_tool_body(self):
        from stageflow.mcp_server import create_mcp_server
        mcp = create_mcp_server()
        tool = mcp._tool_manager.get_tool("stageflow_list_conditions")
        result = tool.fn()
        assert isinstance(result, list)
        assert "always" in result
        assert "never" in result

    def test_evaluate_all_tool_body(self):
        from stageflow.mcp_server import create_mcp_server
        mcp = create_mcp_server()
        tool = mcp._tool_manager.get_tool("stageflow_evaluate_all")
        result = tool.fn(
            conditions=[{"always": True}, {"always": True}],
            base_path=".",
            parallel=False,
            timeout=0,
        )
        assert result["all_passed"] is True
        assert result["conditions_count"] == 2
        assert len(result["messages"]) == 2

    def test_evaluate_all_tool_body_with_parallel(self):
        from stageflow.mcp_server import create_mcp_server
        mcp = create_mcp_server()
        tool = mcp._tool_manager.get_tool("stageflow_evaluate_all")
        result = tool.fn(
            conditions=[{"always": True}, {"always": True}],
            parallel=True,
            timeout=5,
        )
        assert result["all_passed"] is True
        assert result["conditions_count"] == 2

    def test_evaluate_all_tool_body_mixed_result(self):
        from stageflow.mcp_server import create_mcp_server
        mcp = create_mcp_server()
        tool = mcp._tool_manager.get_tool("stageflow_evaluate_all")
        result = tool.fn(
            conditions=[{"always": True}, {"never": "fail"}],
            base_path=".",
        )
        assert result["all_passed"] is False
        assert len(result["messages"]) == 2


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
