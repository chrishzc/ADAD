#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_blocked_mcp.py — 最小化 MCP 伺服器，只實作 report_blocked 工具
ponytail: 不依賴任何 mcp SDK（標準庫實作 json-rpc），直接透過 stdio 溝通。
"""
import sys
import json
import os
import traceback

def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
            
        try:
            req = json.loads(line)
        except Exception:
            continue
            
        req_id = req.get("id")
        method = req.get("method")
        
        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "adad-blocked", "version": "1.0.0"}
                }
            }
            print(json.dumps(resp), flush=True)
            
        elif method == "notifications/initialized":
            # Just ignore
            pass
            
        elif method == "tools/list":
            # 讀取 schema
            schema_path = os.path.join(os.path.dirname(__file__), "blocked_report.schema.json")
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
            except Exception:
                schema = {
                    "type": "object",
                    "properties": {
                        "node_name": {"type": "string"},
                        "reason": {"type": "string"}
                    },
                    "required": ["node_name", "reason"]
                }
                
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [{
                        "name": "report_blocked",
                        "description": "Report that a task is blocked and freeze it. Use this when missing specs or interfaces.",
                        "inputSchema": schema
                    }]
                }
            }
            print(json.dumps(resp), flush=True)
            
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            
            if name == "report_blocked":
                node_name = args.get("node_name", "")
                reason = args.get("reason", "")
                
                # 動態載入 adad_core 執行 task_block
                script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents", "skills", "adad-workflow", "scripts"))
                if script_dir not in sys.path:
                    sys.path.insert(0, script_dir)
                    
                try:
                    from adad_core import ADADCore
                    core = ADADCore()
                    res = core.task_block(node_name, reason)
                    if res.get("success"):
                        text = f"Task '{node_name}' successfully marked as blocked."
                        is_error = False
                    else:
                        text = f"Failed: {res.get('error')}"
                        is_error = True
                except Exception as e:
                    text = f"Internal Error: {traceback.format_exc()}"
                    is_error = True
                    
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": text}],
                        "isError": is_error
                    }
                }
                print(json.dumps(resp), flush=True)

if __name__ == "__main__":
    main()
