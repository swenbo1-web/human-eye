"""Freeze novel paired assembly scenes and render anonymized observation packets.

The private directory is experiment administration data and must never be read by
participants. Scene targets are constructed from box geometry, independently of
the observation provider and its suggested actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import re
import sys
import time
from typing import Any

import numpy as np

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(pathlib.Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from geometry import LIMITS, build_meshes, score_pose
from human_eye_module1_operators import QuadCognitiveCanvasCompositor, SubFrustumMathEngine
from human_eye_plugin import HumanEyeLLMPlugin


SEED = 2026102102
CATEGORIES = ("floating", "tilted", "near_contact", "occluded", "penetrating", "inclined")
COMPLEX_CATEGORIES = ("tilted", "occluded", "penetrating", "inclined", "near_contact")
DEFAULT_RUN = PROJECT_ROOT / "verification" / "blind_test" / "runs" / "20261021_02_vision_only"
EXPERIMENT_MODES = ("vision_only", "full_product")


def rotation_xyz(angles_deg: Any) -> np.ndarray:
    """Active world rotation, column bases, Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
    x, y, z = np.deg2rad(angles_deg)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return np.array([
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy, cy * sx, cy * cx],
    ], dtype=np.float64)


def _plain(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pathlib.Path):
        return str(value.resolve())
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _write_json(path: pathlib.Path, value: Any) -> None:
    path.write_text(json.dumps(_plain(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def make_cases(
    seed: int = SEED,
    cases_per_category: int = 5,
    categories: tuple[str, ...] = CATEGORIES,
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    cases: list[dict[str, Any]] = []
    for category in categories:
        for index in range(cases_per_category):
            base_center = np.array([0.0, 0.0, 0.175])
            base_size = np.array([1.4, 1.2, 0.35])
            base_rotation = np.eye(3)
            if category == "inclined":
                base_rotation = rotation_xyz([
                    rng.choice([-1, 1]) * rng.uniform(7, 18),
                    rng.choice([-1, 1]) * rng.uniform(10, 22),
                    rng.uniform(-30, 30),
                ])
            focal_size = np.array([rng.uniform(.25, .31), rng.uniform(.17, .22), rng.uniform(.12, .16)])
            relative_euler = np.zeros(3)
            if category == "floating":
                gap = rng.uniform(.015, .085)
            elif category == "tilted":
                relative_euler = np.array([
                    rng.choice([-1, 1]) * rng.uniform(4, 19),
                    rng.choice([-1, 1]) * rng.uniform(3, 16),
                    rng.choice([-1, 1]) * rng.uniform(12, 65),
                ])
                gap = rng.uniform(.008, .045)
            elif category == "near_contact":
                # Keep 1 flush negative control when cases_per_category == 2, or 2 when >= 3.
                neg_ctrl_count = 1 if cases_per_category == 2 else min(2, cases_per_category)
                if index < neg_ctrl_count:
                    # Exactly flush negative controls; 180 degrees is equivalent.
                    relative_euler[2] = 180.0 if index == 1 else 0.0
                    gap = 0.0
                else:
                    gap = rng.uniform(.0012, .0045)
                    relative_euler = rng.uniform(-1.5, 1.5, size=3)
            elif category == "occluded":
                gap = rng.uniform(.025, .065)
                relative_euler = np.array([rng.uniform(-7, 7), rng.uniform(-8, 8), rng.uniform(-30, 30)])
            elif category == "penetrating":
                gap = -rng.uniform(.006, .025)
                relative_euler = np.array([rng.uniform(-6, 6), rng.uniform(-6, 6), rng.uniform(-25, 25)])
            else:
                gap = rng.uniform(.008, .045)
                relative_euler = np.array([rng.uniform(-10, 10), rng.uniform(-10, 10), rng.uniform(-40, 40)])

            focal_rotation = base_rotation @ rotation_xyz(relative_euler)
            normal = base_rotation[:, 2]
            plane_point = base_center + normal * base_size[2] * .5
            in_plane = base_rotation[:, 0] * rng.uniform(-.14, .14) + base_rotation[:, 1] * rng.uniform(-.12, .12)
            # Initial support uses all OBB corners. The target instead uses the
            # desired bottom face and is never obtained from a plugin probe.
            support = float(np.sum(np.abs(normal @ focal_rotation) * focal_size) * .5)
            focal_center = plane_point + in_plane + normal * (support + gap)
            target_center = plane_point + in_plane + normal * focal_size[2] * .5
            occluders = []
            if category == "occluded":
                # A distant box lies on the initial camera ray, while remaining
                # far from the assembly plane and the focal part's target volume.
                camera = np.array([2.4, -2.5, 1.85])
                occluder_center = focal_center + (camera - focal_center) * rng.uniform(.31, .37)
                occluders.append({
                    "center": occluder_center.tolist(),
                    "rotation": np.eye(3).tolist(),
                    "size": [float(rng.uniform(.31, .38)), float(rng.uniform(.31, .38)), .34],
                })
            neg_ctrl_count = 1 if cases_per_category == 2 else min(2, cases_per_category)
            case = {
                "scene_id": f"S{len(cases) + 1:03d}",
                "category": category,
                "reference": {"center": base_center.tolist(), "rotation": base_rotation.tolist(), "size": base_size.tolist()},
                "focal": {"center": focal_center.tolist(), "rotation": focal_rotation.tolist(), "size": focal_size.tolist()},
                "occluders": occluders,
                "target": {"plane_point": plane_point.tolist(), "normal": normal.tolist(), "rotation": base_rotation.tolist(), "center": target_center.tolist()},
                "construction": {
                    "seed": seed,
                    "initial_minimum_plane_clearance_m": float(gap),
                    "relative_euler_deg": relative_euler.tolist(),
                    "no_action_negative_control": category == "near_contact" and index < neg_ctrl_count,
                    "target_basis": "independent_analytic_box_geometry",
                },
            }
            cases.append(case)
    return cases


def _anonymize(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"human[ _-]?eye|\bplugin\b|\bcontrol\b", "spatial", value, flags=re.IGNORECASE)
    if isinstance(value, dict):
        return {k: _anonymize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_anonymize(v) for v in value]
    return _plain(value)


def make_packet(
    trial_id: str,
    case: dict[str, Any],
    image_path: pathlib.Path,
    mode: str = "vision_only",
) -> dict[str, Any]:
    if mode not in EXPERIMENT_MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    base = case["reference"]
    base_rotation = np.array(base["rotation"])
    task_suffix = (
        "请严格根据图像及给定标定信息判断动作。"
        if mode == "vision_only"
        else "以图像及给定标定信息判断动作，允许利用观测中的测量建议。"
    )
    return {
        "trial_id": trial_id,
        "image_path": str(image_path.resolve()),
        "task": (
            "对图中的 #B 长方体进行一次刚体旋转和平移，使其局部 -Z 底面完整贴合 #A 顶面；"
            "#B 的局部 X 长边应平行 #A 的局部 X 方向（相差180度也合格）。"
            "保持 #B 当前中心在目标平面内的投影不变，避免终态穿入任何物体。"
            f"仅移动 #B。若已满足条件，应输出零动作。{task_suffix}"
        ),
        "action_convention": {
            "units": "世界坐标位置和平移使用米；角度使用度；右手坐标系。",
            "rotation": "主动旋转 R=Rz(yaw) @ Ry(pitch) @ Rx(roll)，rotation_euler_deg_xyz=[roll,pitch,yaw]。",
            "pivot": "围绕 #B 当前几何中心旋转，然后在世界坐标下按 translation_xyz_m 平移。",
            "output": {
                "trial_id": trial_id,
                "focal_mark": "#B",
                "reference_mark": "#A",
                "rotation_euler_deg_xyz": "三个数值，依次roll,pitch,yaw",
                "translation_xyz_m": "三个数值，依次dx,dy,dz",
                "confidence": "0至1数值",
                "note": "简短说明",
            },
            "response_rule": "只返回以上字段构成的单个JSON对象，不调用其他动作工具，不使用Markdown围栏。",
        },
        "reference_calibration": {
            "mark": "#A",
            "dimensions_local_xyz_m": base["size"],
            "center_world_m": base["center"],
            "top_plane_point_world_m": case["target"]["plane_point"],
            "top_plane_outward_normal_world": case["target"]["normal"],
            "local_x_direction_world": base_rotation[:, 0].tolist(),
            "local_y_direction_world": base_rotation[:, 1].tolist(),
            "initial_camera_eye_world_m": [2.4, -2.5, 1.85],
            "camera_look_at_world_m": [0.0, 0.0, .55],
            "perspective_vertical_fov_deg": 45.0,
        },
        "focal_dimensions": {"mark": "#B", "dimensions_local_xyz_m": case["focal"]["size"], "bottom_face": "local -Z", "long_edge": "local X"},
    }


def _normalize_packet_identity(pkt: dict[str, Any]) -> dict[str, Any]:
    cloned = json.loads(json.dumps(pkt, ensure_ascii=False))
    cloned["trial_id"] = "<TRIAL_ID>"
    cloned["image_path"] = "<IMAGE_PATH>"
    if isinstance(cloned.get("action_convention"), dict) and isinstance(cloned["action_convention"].get("output"), dict):
        cloned["action_convention"]["output"]["trial_id"] = "<TRIAL_ID>"
    return cloned


def _assert_vision_only_packet_invariance(
    control_packet: dict[str, Any],
    plugin_packet: dict[str, Any],
    scene_id: str,
) -> None:
    forbidden = {"observation", "suggested_action", "canonical_mcp_tool_call", "measurements", "som_anchor_table", "telemetry"}
    for label, pkt in (("control", control_packet), ("plugin", plugin_packet)):
        leaked = forbidden.intersection(pkt.keys())
        if leaked:
            raise AssertionError(f"Forbidden non-visual key(s) {leaked} found in {label} packet for {scene_id}")
    c_norm = _normalize_packet_identity(control_packet)
    p_norm = _normalize_packet_identity(plugin_packet)
    if json.dumps(c_norm, sort_keys=True, ensure_ascii=False) != json.dumps(p_norm, sort_keys=True, ensure_ascii=False):
        raise AssertionError(f"Non-visual packet fields differ between control and plugin for {scene_id}")


def generate(
    run_dir: pathlib.Path,
    seed: int = SEED,
    mode: str = "vision_only",
    cases_per_category: int = 2,
    complex_only: bool = True,
) -> dict[str, Any]:
    if mode not in EXPERIMENT_MODES:
        raise ValueError(f"Unsupported mode: {mode}; expected one of {EXPERIMENT_MODES}")
    run_dir = run_dir.resolve()
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing run: {run_dir}")
    active_categories = COMPLEX_CATEGORIES if complex_only else CATEGORIES
    cases = make_cases(seed, cases_per_category=cases_per_category, categories=active_categories)
    for case in cases:
        target_check = score_pose(case, case["target"]["rotation"], case["target"]["center"])
        if not target_check["success"]:
            raise AssertionError(f"Geometric target precheck failed for {case['scene_id']}: {target_check}")
        if case["construction"]["no_action_negative_control"]:
            if not score_pose(case, case["focal"]["rotation"], case["focal"]["center"])["success"]:
                raise AssertionError(f"Negative control is not already solved: {case['scene_id']}")
        case["target_precheck"] = target_check
    run_dir.mkdir(parents=True, exist_ok=False)
    for dirname in ("private", "public", "responses"):
        (run_dir / dirname).mkdir()
    rng = np.random.default_rng(seed + 1)
    trial_map = []
    for case in cases:
        for condition in ("control", "plugin"):
            trial_id = "T" + hashlib.sha256(rng.bytes(24)).hexdigest()[:16]
            packet_dir = run_dir / "public" / trial_id
            packet_dir.mkdir()
            trial_map.append({
                "trial_id": trial_id,
                "scene_id": case["scene_id"],
                "condition": condition,
                "response_path": str((run_dir / "responses" / f"{trial_id}.json").resolve()),
                "packet_path": str((packet_dir / "packet.json").resolve()),
                "image_path": str((packet_dir / "view.png").resolve()),
            })
    rng.shuffle(trial_map)
    # Freeze all cases and condition assignments before invoking the provider.
    _write_json(run_dir / "private" / "cases.json", cases)
    _write_json(run_dir / "private" / "trial_map.json", trial_map)
    _write_json(run_dir / "private" / "evaluation_index.json", [
        {"trial_id": t["trial_id"], "scene_id": t["scene_id"]} for t in trial_map
    ])
    records = {(t["scene_id"], t["condition"]): t for t in trial_map}

    for scene_index, case in enumerate(cases):
        start = time.perf_counter()
        meshes = build_meshes(case)
        observer = HumanEyeLLMPlugin(meshes=meshes, quad_size=384, enable_zero_copy_ipc=False)
        agent = observer.vlm_agent
        eye, target, fov = agent.default_cam_eye, agent.default_cam_target, agent.fov_y_deg

        record_ctrl = records[(case["scene_id"], "control")]
        ctrl_image_path = pathlib.Path(record_ctrl["image_path"])
        renderer = QuadCognitiveCanvasCompositor(quad_size=768)
        view = SubFrustumMathEngine.build_look_at_view_matrix(eye, target)
        projection = SubFrustumMathEngine.build_perspective_matrix(fov_y_deg=fov, aspect=1.0, near=.1, far=25.0)
        ctrl_image = renderer._render_single_viewport(
            meshes=meshes, view_matrix=view, proj_matrix=projection,
            title_banner="PERSPECTIVE | WORLD XYZ | METERS", probe_result=None,
        )
        if ctrl_image.size != (768, 768):
            raise AssertionError(f"Unexpected native image size: {ctrl_image.size}")
        ctrl_image.save(ctrl_image_path)
        ctrl_packet = make_packet(record_ctrl["trial_id"], case, ctrl_image_path, mode=mode)
        _write_json(pathlib.Path(record_ctrl["packet_path"]), ctrl_packet)

        record_plg = records[(case["scene_id"], "plugin")]
        plg_image_path = pathlib.Path(record_plg["image_path"])
        plg_packet = make_packet(record_plg["trial_id"], case, plg_image_path, mode=mode)
        if mode == "vision_only":
            quad_image, telemetry = agent.compositor.render_quad_cognitive_canvas(
                meshes=meshes, cam_eye=eye, cam_target=target, fov_y_deg=fov, yaw_symmetry_order=2,
            )
            if quad_image.size != (768, 768):
                raise AssertionError(f"Unexpected quad canvas size: {quad_image.size}")
            quad_image.save(plg_image_path)
            _assert_vision_only_packet_invariance(ctrl_packet, plg_packet, case["scene_id"])
            measured_reference = "#A"
        else:
            observation = observer.build_llm_observation_bundle(task_instruction=plg_packet["task"])
            observation["canvas_image"].save(plg_image_path)
            prompt = observation["prompt_bundle"]
            frame_state = agent.compositor._ensure_quad_frame_state(meshes, eye, target, fov_y_deg=fov)
            telemetry = frame_state[1]
            plg_packet["observation"] = _anonymize({
                "canvas_legend": "Q1:顶视X-Y；Q2:前视X-Z；Q3:全局透视；Q4:同轴局部放大。",
                "measurements": prompt.user_prompt_markdown,
                "som_anchor_table": observation["som_anchor_table"],
                "suggested_action": prompt.canonical_mcp_tool_call["arguments"],
                "telemetry": telemetry,
            })
            measured_reference = prompt.canonical_mcp_tool_call["arguments"].get("reference_mark")
        _write_json(pathlib.Path(record_plg["packet_path"]), plg_packet)
        pixel_diff = int(np.max(np.abs(np.asarray(ctrl_image, dtype=np.int16) - np.asarray(
            quad_image if mode == "vision_only" else observation["canvas_image"], dtype=np.int16
        ))))
        if pixel_diff == 0:
            raise AssertionError(f"Control and plugin images are identical for {case['scene_id']}")
        case["render_metadata"] = {
            "experiment_mode": mode,
            "initial_camera_eye_world": eye.tolist(),
            "initial_camera_target_world": target.tolist(),
            "condition_images_native_resolution": [768, 768],
            "max_pixel_diff_between_conditions": pixel_diff,
            "non_visual_packet_fields_identical": mode == "vision_only",
            "suggested_action_in_public_packet": mode != "vision_only",
            "measurement_reference_mark": measured_reference,
            "measurement_reference_matches_task": measured_reference == "#A",
            "camera_auto_orbited": bool(telemetry.get("camera_auto_orbited_to_avoid_occlusion", False)),
            "active_camera_eye_world": telemetry.get("active_camera_eye_world"),
            "render_duration_seconds": time.perf_counter() - start,
            "no_selection_or_exclusion_after_observation": True,
        }
        _write_json(run_dir / "private" / "cases.json", cases)
        print(f"Rendered {scene_index + 1}/{len(cases)} scenes ({mode})", flush=True)
    blind_dir = pathlib.Path(__file__).resolve().parent
    source_paths = [
        blind_dir / "geometry.py",
        blind_dir / "score.py",
        blind_dir / "generate.py",
        blind_dir / "aggregate.py",
        blind_dir / "write_report.py",
    ]
    source_paths += sorted(PROJECT_ROOT.glob("human_eye_module1_operators/*.py"))
    source_paths += sorted(PROJECT_ROOT.glob("human_eye_plugin/*.py"))
    source_paths += sorted(PROJECT_ROOT.glob("module_*_*.py"))
    source_paths.append(PROJECT_ROOT / "human_eye_foveated_renderer.py")
    source_paths.append(PROJECT_ROOT / "native_3d_spatial_scratchpad.py")
    frozen_rel_sha256 = {
        p.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source_paths if p.exists()
    }
    protocol = {
        "version": 3,
        "registered_at_utc_epoch": time.time(),
        "experiment_mode": mode,
        "single_variable": (
            "3d_visual_engine_canvas_only (768x768 single perspective vs 768x768 Human-Eye quad foveated + active anti-occlusion canvas)"
            if mode == "vision_only"
            else "full_product_assistance"
        ),
        "participant_model_configuration": "fresh isolated participant subagent per trial (max 2 concurrent); parent settings inherited without overrides; Agent Learning disabled",
        "seed": seed,
        "trials": len(trial_map),
        "paired_scenes": len(cases),
        "categories": {cat: sum(1 for c in cases if c["category"] == cat) for cat in active_categories},
        "primary_endpoint": (
            {"control": "raw.success", "plugin": "raw.success"}
            if mode == "vision_only"
            else {"control": "raw.success", "plugin": "assisted.success"}
        ),
        "secondary_endpoints": [
            "raw.success in both arms",
            "assisted.success in both arms",
            "bottom face RMS (mm)",
            "orientation error (deg)",
            "tangential drift (mm)",
            "terminal collision",
            "assistance changed action",
        ],
        "limits": LIMITS,
        "symmetry": "rectangle yaw 0 or 180 degrees (yaw_symmetry_order=2), local bottom face only",
        "steps_per_trial": 1,
        "fallback_for_invalid_answers": "none; invalid/missing/non-finite answers count as failure",
        "participant_blinding": "randomized T<16-hex> trial IDs; shuffled order; no condition or scene labels in public packets; identical JSON structure across arms in vision_only mode",
        "scorer_blinding": "score.py reads evaluation_index and geometry, never condition labels; computes both raw and assisted endpoints for every answer; labels revealed only after all answers are locked",
        "information_scope": (
            "vision-only single-variable ablation: public packet.json files are byte-identical across paired conditions except trial_id and image_path; zero suggested_action or text telemetry leakage"
            if mode == "vision_only"
            else "full product assistance, including geometric recommendations and optional camera movement"
        ),
        "frozen_source_sha256": frozen_rel_sha256,
    }
    _write_json(run_dir / "protocol.json", protocol)
    artifact_paths = sorted((run_dir / "public").glob("*/*"))
    artifact_paths += [run_dir / "private" / name for name in ("cases.json", "trial_map.json", "evaluation_index.json")]
    _write_json(run_dir / "private" / "generation_manifest.json", {
        "seed": seed,
        "experiment_mode": mode,
        "scene_count": len(cases),
        "trial_count": len(trial_map),
        "target_prechecks_passed": len(cases),
        "source_sha256": {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths if p.exists()},
        "artifact_sha256": {str(p.relative_to(run_dir)): hashlib.sha256(p.read_bytes()).hexdigest() for p in artifact_paths},
    })
    return {
        "run_dir": str(run_dir),
        "experiment_mode": mode,
        "seed": seed,
        "scene_count": len(cases),
        "trial_count": len(trial_map),
        "packet_paths": [t["packet_path"] for t in trial_map],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=pathlib.Path, default=DEFAULT_RUN)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--mode", choices=EXPERIMENT_MODES, default="vision_only")
    parser.add_argument("--cases-per-category", type=int, default=2)
    parser.add_argument("--all-categories", action="store_true")
    args = parser.parse_args()
    print(json.dumps(generate(
        args.run_dir, args.seed, mode=args.mode,
        cases_per_category=args.cases_per_category,
        complex_only=not args.all_categories,
    ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
