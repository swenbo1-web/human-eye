"""
Human-Eye (人类之眼 V9.7) 标准 Model Context Protocol (MCP JSON-RPC 2.0) 服务端入口 (mcp_server.py)
支持 stdio 标准输入输出流式交互与进程内直接 JSON-RPC 字典调用，供任意大语言模型宿主接入。
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from .llm_tool_schemas import MCP_TOOLS_SCHEMA
from .plugin_facade import HumanEyeLLMPlugin

_DEFAULT_PLUGIN_INSTANCE: Optional[HumanEyeLLMPlugin] = None


def get_default_plugin() -> HumanEyeLLMPlugin:
    global _DEFAULT_PLUGIN_INSTANCE
    if _DEFAULT_PLUGIN_INSTANCE is None:
        _DEFAULT_PLUGIN_INSTANCE = HumanEyeLLMPlugin()
    return _DEFAULT_PLUGIN_INSTANCE


def handle_jsonrpc_message(
    req: Dict[str, Any],
    plugin: Optional[HumanEyeLLMPlugin] = None,
) -> Optional[Dict[str, Any]]:
    """处理单条标准 MCP JSON-RPC 2.0 请求消息"""
    plg = get_default_plugin() if plugin is None else plugin
    method = str(req.get("method", ""))
    req_id = req.get("id")

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "human-eye-spatial-plugin",
                    "version": HumanEyeLLMPlugin.VERSION,
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS_SCHEMA},
        }

    if method == "tools/call":
        params = req.get("params") or {}
        t_name = str(params.get("name", ""))
        t_args = params.get("arguments") or {}
        try:
            out = plg.dispatch_tool_call(t_name, t_args)
            text_result = dict(out)
            image_content = text_result.pop("mcp_image_content", None)
            content = [{"type": "text", "text": json.dumps(text_result, ensure_ascii=False)}]
            if image_content is not None:
                content.append(image_content)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": content,
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Tool execution error: {exc}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_stdio_mcp_server() -> None:
    """启动基于标准输入输出 (stdio) 的 MCP JSON-RPC 2.0 守护进程"""
    plg = get_default_plugin()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_jsonrpc_message(req, plugin=plg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
            sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_mcp_server()
