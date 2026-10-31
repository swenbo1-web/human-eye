"""Multi-dimensional comparison of Control vs Human-Eye Plugin across accuracy, tokens, latency, and efficiency."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from geometry import build_meshes
from human_eye_module1_operators import QuadCognitiveCanvasCompositor, SubFrustumMathEngine
from human_eye_plugin import HumanEyeLLMPlugin


def main() -> None:
    run = ROOT / "verification" / "blind_test" / "runs" / "20261021_02_vision_only"
    projcache = Path(os.path.expanduser("~/.dsh/storages/session_projcache/sessions"))
    tmap = {t["trial_id"]: t for t in json.loads((run / "private/trial_map.json").read_text(encoding="utf-8"))}
    cases = {c["scene_id"]: c for c in json.loads((run / "private/cases.json").read_text(encoding="utf-8"))}
    scores = {r["trial_id"]: r for r in json.loads((run / "blind_scores.json").read_text(encoding="utf-8"))["results"]}

    trial_sessions: dict[str, dict] = {}
    if projcache.exists():
        for f in projcache.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                rows = data.get("record", {}).get("rows", {})
                first_txt = rows.get("titleInput", {}).get("val", {}).get("first", {}).get("text", "")
                m = re.search(r"(T[0-9a-f]{16})", first_txt)
                if not m:
                    continue
                tid = m.group(1)
                if tid not in tmap:
                    continue
                created = data["record"]["identity"]["createdAt"]
                settled = rows.get("subagentTiming", {}).get("val", {}).get("settledMs")
                completed = bool(rows.get("subagentTiming", {}).get("val", {}).get("lastTurnCompleted", False))
                prev = trial_sessions.get(tid)
                if prev is None or (completed and not prev["completed"]) or (
                    completed == prev["completed"] and created > prev["createdAt"]
                ):
                    tok = rows.get("tokenUsage", {}).get("val", {}).get("totals", {})
                    st = rows.get("sessionStats", {}).get("val", {})
                    uncached_in = int(tok.get("uncachedInputTokens", 0))
                    cache_in = int(tok.get("cacheReadTokens", 0))
                    out_tok = int(tok.get("outputTokens", 0))
                    trial_sessions[tid] = {
                        "session_id": f.stem,
                        "createdAt": created,
                        "completed": completed,
                        "settledMs": settled,
                        "uncachedInputTokens": uncached_in,
                        "cacheReadTokens": cache_in,
                        "totalInputTokens": uncached_in + cache_in,
                        "outputTokens": out_tok,
                        "totalTokens": uncached_in + cache_in + out_tok,
                        "steps": int(st.get("steps", 0)),
                        "llmMs": int(st.get("llmMs", 0)),
                        "toolMs": int(st.get("toolMs", 0)),
                        "ttftMs": int(st.get("ttftMs", 0)),
                        "decodeMs": int(st.get("decodeMs", 0)),
                        "decodeTokens": int(st.get("decodeTokens", 0)),
                        "isSeeded": bool(data["record"]["identity"].get("isSeeded", False)),
                        "inheritedEventCount": int(data["record"]["identity"].get("inheritedEventCount", 0)),
                    }
            except Exception:
                continue

    # Measure CPU render & observation bundle token metrics per scene
    scene_render_bench = {}
    for sid, case in sorted(cases.items()):
        meshes = build_meshes(case)
        plugin = HumanEyeLLMPlugin(meshes=meshes, quad_size=384, enable_zero_copy_ipc=False)
        eye, target, fov = plugin.vlm_agent.default_cam_eye, plugin.vlm_agent.default_cam_target, plugin.vlm_agent.fov_y_deg
        single_renderer = QuadCognitiveCanvasCompositor(quad_size=768)
        view = SubFrustumMathEngine.build_look_at_view_matrix(eye, target)
        proj = SubFrustumMathEngine.build_perspective_matrix(fov_y_deg=fov, aspect=1.0, near=0.1, far=25.0)

        t0 = time.perf_counter()
        single_renderer._render_single_viewport(meshes, view, proj, title_banner="PERSPECTIVE | WORLD XYZ | METERS", probe_result=None)
        ctrl_render_ms = (time.perf_counter() - t0) * 1000.0

        plugin.vlm_agent.compositor._QUAD_FRAME_CACHE.clear()
        t1 = time.perf_counter()
        plugin.vlm_agent.compositor.render_quad_cognitive_canvas(meshes, eye, target, fov_y_deg=fov, yaw_symmetry_order=2)
        plg_cold_render_ms = (time.perf_counter() - t1) * 1000.0

        t2 = time.perf_counter()
        plugin.vlm_agent.compositor.render_quad_cognitive_canvas(meshes, eye, target, fov_y_deg=fov, yaw_symmetry_order=2)
        plg_hot_render_ms = (time.perf_counter() - t2) * 1000.0

        base_obs = plugin.build_llm_observation_bundle(meshes=meshes, enable_human_eye_plugin=False)
        plg_obs = plugin.build_llm_observation_bundle(meshes=meshes, enable_human_eye_plugin=True)
        scene_render_bench[sid] = {
            "control_single_render_ms": round(ctrl_render_ms, 3),
            "plugin_quad_cold_render_ms": round(plg_cold_render_ms, 3),
            "plugin_quad_hot_render_ms": round(plg_hot_render_ms, 4),
            "sdk_baseline_raw_json_obs_tokens": base_obs["total_tokens"],
            "sdk_plugin_quad_obs_tokens": plg_obs["total_tokens"],
        }

    per_trial = []
    for tid, meta in sorted(tmap.items(), key=lambda kv: (kv[1]["scene_id"], kv[1]["condition"])):
        sid = meta["scene_id"]
        cond = meta["condition"]
        sc = scores[tid]
        sess = trial_sessions.get(tid, {})
        img_bytes = Path(meta["image_path"]).stat().st_size
        pkt_bytes = Path(meta["packet_path"]).stat().st_size
        rms_mm = float(sc["raw"]["bottom_face_rms_mm"])
        rot_deg = float(sc["raw"]["rotation_error_deg"])
        pos_mm = float(sc["raw"]["position_error_mm"])
        out_tok = sess.get("outputTokens", 0)
        tot_tok = sess.get("totalTokens", 0)
        llm_s = sess.get("llmMs", 0) / 1000.0
        settled_s = (sess.get("settledMs") or (sess.get("llmMs", 0) + sess.get("toolMs", 0))) / 1000.0
        per_trial.append({
            "scene_id": sid,
            "category": cases[sid]["category"],
            "condition": cond,
            "trial_id": tid,
            "image_png_bytes": img_bytes,
            "packet_json_bytes": pkt_bytes,
            "visual_tokens_nominal": 256,
            "packet_text_tokens_est": (pkt_bytes + 3) // 4,
            "uncached_input_tokens": sess.get("uncachedInputTokens", 0),
            "cache_read_tokens": sess.get("cacheReadTokens", 0),
            "total_input_tokens": sess.get("totalInputTokens", 0),
            "output_decode_tokens": out_tok,
            "total_api_tokens": tot_tok,
            "agent_steps": sess.get("steps", 0),
            "llm_inference_s": round(llm_s, 2),
            "ttft_s": round(sess.get("ttftMs", 0) / 1000.0, 2),
            "decode_s": round(sess.get("decodeMs", 0) / 1000.0, 2),
            "tool_exec_s": round(sess.get("toolMs", 0) / 1000.0, 3),
            "settled_wall_s": round(settled_s, 2),
            "decode_tok_per_s": round(out_tok / max(sess.get("decodeMs", 1) / 1000.0, 1e-3), 2),
            "raw_bottom_rms_mm": round(rms_mm, 4),
            "raw_rotation_error_deg": round(rot_deg, 4),
            "raw_position_error_mm": round(pos_mm, 4),
            "raw_penetrating": bool(sc["raw"]["penetrating"]),
            "raw_success_0_5mm": bool(sc["raw"]["success"]),
            "raw_success_5mm": rms_mm <= 5.0,
            "raw_success_10mm": rms_mm <= 10.0,
            "raw_success_15mm": rms_mm <= 15.0,
            "assisted_success_0_5mm": bool(sc["assisted"]["success"]),
            "assisted_bottom_rms_mm": round(float(sc["assisted"]["bottom_face_rms_mm"]), 4),
        })

    summary = {}
    for cond in ("control", "plugin"):
        rows = [r for r in per_trial if r["condition"] == cond]
        summary[cond] = {
            "trials": len(rows),
            "mean_image_png_kb": round(statistics.mean(r["image_png_bytes"] for r in rows) / 1024.0, 2),
            "packet_json_bytes": rows[0]["packet_json_bytes"],
            "visual_tokens_nominal": 256,
            "median_total_input_tokens": statistics.median(r["total_input_tokens"] for r in rows),
            "mean_total_input_tokens": round(statistics.mean(r["total_input_tokens"] for r in rows), 1),
            "median_output_decode_tokens": statistics.median(r["output_decode_tokens"] for r in rows),
            "mean_output_decode_tokens": round(statistics.mean(r["output_decode_tokens"] for r in rows), 1),
            "median_total_api_tokens": statistics.median(r["total_api_tokens"] for r in rows),
            "mean_total_api_tokens": round(statistics.mean(r["total_api_tokens"] for r in rows), 1),
            "sum_total_api_tokens": sum(r["total_api_tokens"] for r in rows),
            "median_llm_inference_s": round(statistics.median(r["llm_inference_s"] for r in rows), 2),
            "mean_llm_inference_s": round(statistics.mean(r["llm_inference_s"] for r in rows), 2),
            "median_settled_wall_s": round(statistics.median(r["settled_wall_s"] for r in rows), 2),
            "mean_settled_wall_s": round(statistics.mean(r["settled_wall_s"] for r in rows), 2),
            "mean_decode_tok_per_s": round(statistics.mean(r["decode_tok_per_s"] for r in rows), 2),
            "median_agent_steps": statistics.median(r["agent_steps"] for r in rows),
            "mean_agent_steps": round(statistics.mean(r["agent_steps"] for r in rows), 2),
            "median_raw_bottom_rms_mm": round(statistics.median(r["raw_bottom_rms_mm"] for r in rows), 4),
            "mean_raw_bottom_rms_mm": round(statistics.mean(r["raw_bottom_rms_mm"] for r in rows), 4),
            "median_raw_rotation_error_deg": round(statistics.median(r["raw_rotation_error_deg"] for r in rows), 4),
            "mean_raw_rotation_error_deg": round(statistics.mean(r["raw_rotation_error_deg"] for r in rows), 4),
            "median_raw_position_error_mm": round(statistics.median(r["raw_position_error_mm"] for r in rows), 4),
            "mean_raw_position_error_mm": round(statistics.mean(r["raw_position_error_mm"] for r in rows), 4),
            "pass_rate_0_5mm_pct": round(sum(r["raw_success_0_5mm"] for r in rows) / len(rows) * 100.0, 1),
            "pass_rate_5mm_pct": round(sum(r["raw_success_5mm"] for r in rows) / len(rows) * 100.0, 1),
            "pass_rate_10mm_pct": round(sum(r["raw_success_10mm"] for r in rows) / len(rows) * 100.0, 1),
            "pass_rate_15mm_pct": round(sum(r["raw_success_15mm"] for r in rows) / len(rows) * 100.0, 1),
            "assisted_pass_rate_0_5mm_pct": round(sum(r["assisted_success_0_5mm"] for r in rows) / len(rows) * 100.0, 1),
            "penetrating_trials": sum(r["raw_penetrating"] for r in rows),
        }

    render_summary = {
        "mean_control_single_render_ms": round(statistics.mean(v["control_single_render_ms"] for v in scene_render_bench.values()), 3),
        "mean_plugin_quad_cold_render_ms": round(statistics.mean(v["plugin_quad_cold_render_ms"] for v in scene_render_bench.values()), 3),
        "mean_plugin_quad_hot_render_ms": round(statistics.mean(v["plugin_quad_hot_render_ms"] for v in scene_render_bench.values()), 4),
        "mean_sdk_baseline_raw_json_obs_tokens": round(statistics.mean(v["sdk_baseline_raw_json_obs_tokens"] for v in scene_render_bench.values()), 1),
        "mean_sdk_plugin_quad_obs_tokens": round(statistics.mean(v["sdk_plugin_quad_obs_tokens"] for v in scene_render_bench.values()), 1),
    }

    out = {
        "summary_by_condition": summary,
        "engine_render_and_sdk_token_summary": render_summary,
        "per_trial": per_trial,
    }
    target_path = run / "multidim_comparison.json"
    target_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "render": render_summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
