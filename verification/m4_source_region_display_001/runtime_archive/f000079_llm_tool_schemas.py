"""
Human-Eye (人类之眼) 全栈三维空间智能插件 — 跨厂商大模型（OpenAI / DeepSeek / Qwen-VL / Claude / Gemini / MCP）
统一工具 Schema 定义与转换器 (llm_tool_schemas.py)
"""

from __future__ import annotations

from typing import Any, Dict, List

HUMAN_EYE_CORE_TOOLS_SPEC: List[Dict[str, Any]] = [
    {
        "name": "human_eye_inspect_scene_quad_canvas",
        "description": (
            "Render the 768x768 Quad Cognitive Canvas (Q1:Top X-Y Ortho, Q2:Front X-Z Ortho, "
            "Q3:Global Gist Perspective, Q4:Co-Axial Foveal Sub-Frustum Zoom), compile the "
            "spatial grounding prompt, and return the PNG image, Set-of-Mark (SoM) 2D/3D anchors and token estimates."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focal_mark": {
                    "type": "string",
                    "description": "Set-of-Mark label of the focal moving part (e.g. '#B').",
                },
                "reference_mark": {
                    "type": "string",
                    "description": "Set-of-Mark label of the reference base part (e.g. '#A').",
                },
                "task_instruction": {
                    "type": "string",
                    "description": "High-level spatial assembly task instruction.",
                },
                "enable_human_eye_plugin": {
                    "type": "boolean",
                    "description": "True = full 4-quadrant foveated canvas + SE(3) probe; False = baseline single Q3 view for A/B comparison.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "human_eye_probe_spatial_clearance",
        "description": (
            "Execute narrow-phase 4-channel 3D clearance & 15-axis OBB-SAT collision sniffing "
            "plus 3D Spherical Inhibition-of-Return (IoR) multi-locus contact probing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focal_mark": {"type": "string", "description": "Focal part mark (e.g. '#B')."},
                "reference_mark": {"type": "string", "description": "Reference part mark (e.g. '#A')."},
                "enable_multi_locus_ior": {
                    "type": "boolean",
                    "description": "Whether to run 3D Spherical IoR multi-locus contact feature extraction.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "human_eye_sync_low_token_scene_delta",
        "description": (
            "Compute Merkle-DAG incremental scene state delta, task-conditioned horizon filtering, "
            "and compact ScenePatchDSL with an estimated token count for Blender & Unreal Engine."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focal_mark": {"type": "string", "description": "Focal part mark (e.g. '#B')."},
                "full_sync": {"type": "boolean", "description": "Include the full initial scene rather than only changed scene nodes."},
            },
            "required": [],
        },
    },
    {
        "name": "human_eye_apply_se3_closed_loop",
        "description": (
            "Execute 6-DoF SE(3) closed-loop alignment with Lie-group SO(3)/SE(3) hallucination firewall, "
            "Zero-Copy Shared-Memory IPC, 7-State Schmitt-Trigger FSM, Closed-Form Lagrangian ECBF safety shield, "
            "Smith delay predictor, and ghost_pre_mesh residual verification."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focal_mark": {"type": "string", "description": "Focal part mark (e.g. '#B')."},
                "reference_mark": {"type": "string", "description": "Reference part mark (e.g. '#A')."},
                "rotation_euler_deg_xyz": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": (
                        "Step-1 pivot-centered Euler XYZ rotation in degrees [d_roll, d_pitch, d_yaw]. "
                        "Convention is EXTRINSIC XYZ: R = Rz(yaw) * Ry(pitch) * Rx(roll). "
                        "Prefer rotation_quaternion_wxyz or posed_se3_4x4 when exact reproduction matters."
                    ),
                },
                "rotation_quaternion_wxyz": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Step-1 unit quaternion [w, x, y, z].",
                },
                "translation_xyz_m": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Step-2 coupled Euclidean translation in meters [dx, dy, dz].",
                },
                "enable_ecbf_shield": {
                    "type": "boolean",
                    "description": "Enable Closed-Form Lagrangian ECBF & Whitney anti-jamming safety shield.",
                },
                "damping_gain_alpha": {
                    "type": "number",
                    "description": "Lie-algebraic damping gain alpha in (0.05, 1.0].",
                },
                "detail_level": {
                    "type": "string",
                    "enum": ["compact", "full"],
                    "default": "compact",
                    "description": (
                        "compact (default) = minimal response, verify_mode only; "
                        "full = additionally returns applied_se3_action.posed_se3_4x4 and a verification block "
                        "for bit-exact offline reproduction."
                    ),
                },
            },
            "required": ["focal_mark", "reference_mark"],
        },
    },
    {
        "name": "human_eye_unproject_2d_click_to_3d",
        "description": (
            "Unproject 2D pixel or [0, 1000] normalized VLM coordinates (PIXEL_UV / NORM_1000_YX / NORM_1000_XY / NORM_01_UV) "
            "to exact 3D surface witness points and synthesize a 0.0 ULP 6-DoF SE(3) alignment prescription."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focal_click_or_box": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "2D click [u, v] or bounding box [x0, y0, x1, y1] on focal part.",
                },
                "reference_click_or_box": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Optional 2D click or box on reference part.",
                },
                "coord_convention": {
                    "type": "string",
                    "enum": ["PIXEL_UV", "NORM_1000_YX", "NORM_1000_XY", "NORM_01_UV"],
                    "description": "2D coordinate convention used by the VLM.",
                },
            },
            "required": ["focal_click_or_box"],
        },
    },
    {
        "name": "human_eye_issue_digital_twin_certificate",
        "description": (
            "Issue a deterministic hardware CRC32 + ASME Y14.5 GD&T + 6D force-closure + 13-point Unscented Sigma-Point "
            "yield + SHA-256 Digital Twin assembly quality certificate."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focal_mark": {"type": "string", "description": "Focal part mark (e.g. '#B')."},
                "reference_mark": {"type": "string", "description": "Reference part mark (e.g. '#A')."},
            },
            "required": [],
        },
    },
]

for _tool in HUMAN_EYE_CORE_TOOLS_SPEC:
    if _tool["name"] in {
        "human_eye_inspect_scene_quad_canvas", "human_eye_probe_spatial_clearance",
        "human_eye_apply_se3_closed_loop", "human_eye_unproject_2d_click_to_3d",
    }:
        _tool["parameters"]["properties"]["yaw_symmetry_order"] = {
            "type": "integer", "enum": [1, 2, 4], "default": 2,
            "description": "Allowed in-plane symmetry: 1=directed axis, 2=rectangle (0/180 degrees), 4=explicit quarter-turn symmetry. Use the same value for observation and execution.",
        }

MCP_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "name": item["name"],
        "description": item["description"],
        "inputSchema": item["parameters"],
    }
    for item in HUMAN_EYE_CORE_TOOLS_SPEC
]

OPENAI_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": item["name"],
            "description": item["description"],
            "parameters": item["parameters"],
        },
    }
    for item in HUMAN_EYE_CORE_TOOLS_SPEC
]

ANTHROPIC_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "name": item["name"],
        "description": item["description"],
        "input_schema": item["parameters"],
    }
    for item in HUMAN_EYE_CORE_TOOLS_SPEC
]

GEMINI_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "function_declarations": [
            {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["parameters"],
            }
            for item in HUMAN_EYE_CORE_TOOLS_SPEC
        ]
    }
]


def get_llm_tools_schema(vendor: str = "openai") -> List[Dict[str, Any]]:
    """根据目标大模型厂商标识返回对应的标准 Function-Calling / MCP 工具定义列表"""
    v = vendor.strip().lower()
    if v in ("openai", "deepseek", "qwen", "vllm", "gpt"):
        return OPENAI_TOOLS_SCHEMA
    if v in ("anthropic", "claude"):
        return ANTHROPIC_TOOLS_SCHEMA
    if v in ("gemini", "google"):
        return GEMINI_TOOLS_SCHEMA
    return MCP_TOOLS_SCHEMA
