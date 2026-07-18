"""Regression tests for the blocked-task JSON-RPC reporting MCP server."""

import json
from pathlib import Path
import subprocess
import sys


_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "adad_source" / "blocked_report" / "report_blocked_mcp.py"


def _request(*requests: dict) -> list[dict]:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input="\n".join(json.dumps(request) for request in requests) + "\n",
        text=True,
        capture_output=True,
        cwd=_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def test_mcp_initialization_and_tool_schema_are_structured():
    initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    tools_list = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

    initialized, listed = _request(initialize, tools_list)

    assert initialized["id"] == 1
    assert initialized["result"]["serverInfo"]["name"] == "adad-blocked"
    tool = listed["result"]["tools"][0]
    assert tool["name"] == "report_blocked"
    assert tool["inputSchema"]["required"] == ["node_name", "reason"]


def test_mcp_report_blocked_returns_structured_error_for_unknown_task():
    call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "report_blocked",
            "arguments": {"node_name": "missing_node", "reason": "missing specification"},
        },
    }

    response = _request(call)[0]

    assert response["id"] == 3
    assert response["result"]["isError"] is True
    assert response["result"]["content"][0]["type"] == "text"
    assert "Failed:" in response["result"]["content"][0]["text"]
