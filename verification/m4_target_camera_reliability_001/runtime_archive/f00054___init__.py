"""
Human-Eye (人类之眼 V9.7) 全栈三维空间视觉与 6-DoF 闭环控制插件包 (human_eye_plugin)
====================================================================================
同时兼容：
1. 大语言模型 / 多模态大模型 (OpenAI / DeepSeek / Qwen-VL / Claude / Gemini) Function-Calling 插件；
2. Model Context Protocol (MCP JSON-RPC 2.0) 标准工具服务端插件；
3. Blender 4.x / 5.x 原生 Add-on 插件 (`bl_info` + `register` / `unregister`)；
4. Python SDK (`pip install` Wheel 包) 供大模型 A/B 效果对比测试直接导入。
"""

from __future__ import annotations

bl_info = {
    "name": "Human-Eye 3D Spatial Intelligence & 6-DoF Closed-Loop MCP Plugin",
    "author": "Human-Eye Spatial Intelligence Team",
    "version": (9, 7, 2),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Human-Eye MCP",
    "description": "256-Token Quad Cognitive Canvas, Lie-Group SE(3) Hallucination Firewall & Closed-Loop Servo Plugin for LLMs/VLMs",
    "category": "3D View",
}

from .llm_tool_schemas import (
    ANTHROPIC_TOOLS_SCHEMA,
    GEMINI_TOOLS_SCHEMA,
    HUMAN_EYE_CORE_TOOLS_SPEC,
    MCP_TOOLS_SCHEMA,
    OPENAI_TOOLS_SCHEMA,
    get_llm_tools_schema,
)
from .plugin_facade import (
    HumanEyeLLMPlugin,
    LLMABComparisonResult,
)

__version__ = "9.7.2"


def __getattr__(name: str):
    # Avoid importing the executable module before `python -m ...mcp_server`.
    if name in ("get_default_plugin", "handle_jsonrpc_message", "run_stdio_mcp_server"):
        from . import mcp_server
        return getattr(mcp_server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def register() -> None:
    """Blender 4.x/5.x Add-on 与宿主插件激活钩子"""
    from .mcp_server import get_default_plugin
    get_default_plugin()


def unregister() -> None:
    """Blender 4.x/5.x Add-on 与宿主插件卸载钩子"""
    pass


__all__ = [
    "bl_info",
    "__version__",
    "HUMAN_EYE_CORE_TOOLS_SPEC",
    "MCP_TOOLS_SCHEMA",
    "OPENAI_TOOLS_SCHEMA",
    "ANTHROPIC_TOOLS_SCHEMA",
    "GEMINI_TOOLS_SCHEMA",
    "get_llm_tools_schema",
    "HumanEyeLLMPlugin",
    "LLMABComparisonResult",
    "get_default_plugin",
    "handle_jsonrpc_message",
    "run_stdio_mcp_server",
    "register",
    "unregister",
]
