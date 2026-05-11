"""MCP (Model Context Protocol) server exposing StageFlow conditions as tools.

Usage:
    python -m stageflow mcp       # Start MCP server on stdio
    python stageflow/mcp_server.py  # Direct execution

Or programmatically:
    from stageflow.mcp_server import create_mcp_server
    mcp = create_mcp_server()
    mcp.run(transport="stdio")
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def create_mcp_server():
    """Create and return a FastMCP server with StageFlow condition tools registered."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="StageFlow",
        instructions="Evaluate StageFlow conditions via MCP protocol. "
        "Use stageflow_evaluate to check a single condition, "
        "stageflow_evaluate_all to check multiple conditions, "
        "and stageflow_list_conditions to list all available condition types.",
    )

    @mcp.tool(
        name="stageflow_evaluate",
        title="Evaluate Condition",
        description="Evaluate a single StageFlow condition by name with given parameters.",
    )
    def evaluate_condition(name: str, params: dict) -> dict:
        from stageflow.core.conditions import evaluate
        passed, message = evaluate(name, params)
        return {"condition": name, "params": params, "passed": passed, "message": message}

    @mcp.tool(
        name="stageflow_list_conditions",
        title="List Conditions",
        description="List all registered StageFlow condition types.",
    )
    def list_condition_types() -> list[str]:
        from stageflow.core.conditions import list_conditions
        return list_conditions()

    @mcp.tool(
        name="stageflow_evaluate_all",
        title="Evaluate All Conditions",
        description="Evaluate a list of StageFlow conditions. Returns overall pass/fail with messages.",
    )
    def evaluate_all_conditions(
        conditions: list[dict],
        base_path: str = ".",
        parallel: bool = False,
        timeout: float = 0,
    ) -> dict:
        from stageflow.core.conditions import evaluate_all
        ok, messages = evaluate_all(
            conditions,
            base_path=base_path,
            parallel=parallel,
            timeout=timeout if timeout > 0 else None,
        )
        return {"all_passed": ok, "messages": messages, "conditions_count": len(conditions)}

    return mcp


def serve():
    """Create MCP server and run on stdio transport."""
    mcp = create_mcp_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    serve()
