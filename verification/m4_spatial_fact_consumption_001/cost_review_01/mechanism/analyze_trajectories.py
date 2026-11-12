"""Review saved six-cell evidence. This script never imports or runs the product."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


OUTPUT = Path(__file__).resolve().parent
BATCH = OUTPUT.parents[1]
SOURCES: dict[str, dict] = {}


def source(path: Path) -> dict:
    resolved = path.resolve()
    raw = resolved.read_bytes()
    item = {
        "path": resolved.as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    SOURCES[item["path"]] = item
    return item


def read_json(path: Path):
    source(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict]:
    source(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]


def compact(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


ANNOTATIONS = {
    ("spc01", 1): {
        "category": "directory_or_identity",
        "role": "核对四个指定对象的类型、世界矩阵、尺寸、modifier 和单位。",
        "before": "尚无当前几何和任务距离。",
        "after": "对象存在且为 MESH，单位已知，尚无表面距离。",
        "mesh_evaluations": 0,
    },
    ("spc01", 2): {
        "category": "new_information",
        "role": "求值四份网格，双精度转换到世界坐标，缓存几何，并将 Target 的全部 256 个世界顶点输出给消费者。",
        "before": "仅有对象身份、尺寸和单位。",
        "after": "四份完整网格可供同进程下次调用使用，尚无任务距离。",
        "mesh_evaluations": 4,
    },
    ("spc01", 3): {
        "category": "new_information",
        "role": "复用 geo，以双向点面、边边和边面测试首次计算三个表面距离、见证点和交叉检查。",
        "before": "已有完整几何，尚无任务距离。",
        "after": "三个表面距离和见证点已输出。封存质量评分确认最终 13 项要求完整正确。",
        "mesh_evaluations": 0,
    },
    ("spc02", 1): {
        "category": "new_information",
        "role": "尝试获取事实，将 nearest_witness 作为独立 requested_fact，合同校验拒绝。",
        "before": "尚无本次任务事实。",
        "after": "获得不执行的参数错误，未采集 Blender 网格。",
        "mesh_evaluations": 0,
        "outcome": "invalid_request",
    },
    ("spc02", 2): {
        "category": "new_information",
        "role": "删去无效 nearest_witness，保留 spatial_relation、surface_proximity 和额外 closed_solid_relation，获取三组任务事实。",
        "before": "上次请求已被拒绝，尚无任务事实。",
        "after": "必要关系、距离、见证点和最近者完整，三个额外 closed 结果为工作预算 unknown。",
        "mesh_evaluations": 4,
    },
    ("spc03", 1): {
        "category": "new_information",
        "role": "自然请求 spatial_relation、surface_proximity 和额外 closed_solid_relation，一次获取三组任务事实。",
        "before": "尚无本次任务事实。",
        "after": "必要关系、距离、见证点和最近者完整，三个额外 closed 结果为工作预算 unknown。",
        "mesh_evaluations": 4,
    },
    ("spc04", 1): {
        "category": "directory_or_identity",
        "role": "核对四个对象的类型、矩阵、原网格计数、modifier 和单位。",
        "before": "尚无当前几何和任务距离。",
        "after": "身份、原网格计数和单位已知，尚无任务距离。",
        "mesh_evaluations": 0,
    },
    ("spc04", 2): {
        "category": "new_information",
        "role": "求值四份完整几何，双精度转换，计算双向点面和边边距离、边面交叉，并以双向单顶点 winding 补充包含检查。",
        "before": "只有对象身份、计数和单位。",
        "after": "本次一次调用给出三个表面距离、见证点、无交叉和 winding 数据。",
        "mesh_evaluations": 4,
    },
    ("spc05", 1): {
        "category": "directory_or_identity",
        "secondary_categories": ["new_information"],
        "role": "核对对象和单位，同时求值四份网格，先用 mathutils 世界坐标转换后装入 float64 数组。",
        "before": "尚无当前几何和任务距离。",
        "after": "身份和第一份世界坐标缓存已知，尚无任务距离。",
        "mesh_evaluations": 4,
    },
    ("spc05", 2): {
        "category": "new_information",
        "role": "重读四份网格，改为局部坐标和世界矩阵均以 float64 运算，再以三角形笛卡尔积首次求距、见证点和交叉数。",
        "before": "有第一份几何缓存，尚无已回答的表面距离。",
        "after": "三个表面距离和见证点已知，后续仍补查包含关系。",
        "mesh_evaluations": 4,
        "repeat_geometry_refresh": {
            "meshes": 4,
            "vertices": 576,
            "triangles": 1136,
            "reason_in_saved_code": "Read mesh coordinates and apply the stored world matrices in double precision.",
            "refresh_only_duration_ns": None,
        },
    },
    ("spc05", 3): {
        "category": "unresolved_verification",
        "role": "复用 geo，检查四网格边流形，并对三个候选的双方全部顶点计算 solid-angle winding，补充排除包含。",
        "before": "已知正表面距离和无表面交叉，包含关系仍待补证。",
        "after": "输出流形和 winding 数据。封存评分确认最终答案完整正确。",
        "mesh_evaluations": 0,
    },
    ("spc06", 1): {
        "category": "new_information",
        "role": "自然请求 closed_solid_relation、surface_proximity 和 spatial_relation，一次获取三组任务事实。",
        "before": "尚无本次任务事实。",
        "after": "必要关系、距离、见证点和最近者完整，三个额外 closed 结果为工作预算 unknown。",
        "mesh_evaluations": 4,
    },
}


def review_cell(cell_name: str) -> dict:
    cell_dir = BATCH / "cells" / cell_name
    owner = cell_dir / "owner"
    consumer = read_json(cell_dir / "CONSUMER.json")
    worker_file = owner / "native" / "WORKER_EVENTS.jsonl"
    worker_events = read_jsonl(worker_file)
    audit_file = owner / "audit.jsonl"
    audit = read_jsonl(audit_file) if audit_file.exists() else []
    rpc_file = owner / "plugin" / "RPC.json"
    rpc = read_json(rpc_file) if rpc_file.exists() else None
    final_file = cell_dir / "PUBLIC_FINAL.txt"
    final_source = source(final_file)
    final_text = final_file.read_text(encoding="utf-8-sig")
    source(owner / "INITIAL.json")
    source(owner / "FINAL.json")
    source(owner / "TOOLS.json")
    steps = []
    last_end = consumer["started_ns"]
    assigned_sequences = set()
    for tool_dir in sorted(owner.glob("tool_*")):
        attempt_file = tool_dir / "ATTEMPT.json"
        request_file = tool_dir / "REQUEST.json"
        response_file = tool_dir / "RESPONSE.json"
        attempt = read_json(attempt_file)
        request = read_json(request_file)
        response = read_json(response_file)
        image = read_json(tool_dir / "IMAGE_CONSTRUCTION.json")
        step = dict(ANNOTATIONS[(cell_name, attempt["attempt"])])
        args = request["params"]["arguments"]
        start = attempt["started_ns"]
        end = start + attempt["elapsed_ns"]
        step.update({
            "attempt": attempt["attempt"],
            "tool": attempt["name"],
            "arguments": args,
            "request_source": source(request_file),
            "response_source": source(response_file),
            "attempt_source": source(attempt_file),
            "actor_clock": "perf_counter_ns",
            "actor_started_ns": start,
            "actor_ended_ns": end,
            "actor_elapsed_ns": attempt["elapsed_ns"],
            "offset_from_consumer_started_ns": start - consumer["started_ns"],
            "preceding_unassigned_wall_gap_ns": start - last_end,
            "actor_accounted_response_envelope_bytes": attempt["response_bytes"],
            "produced_response_envelope_bytes": attempt["produced_response_bytes"],
            "arguments_compact_json_utf8_bytes": len(compact(args)),
            "image_construction": image,
            "is_error": attempt["is_error"],
            "exception": attempt["exception"],
            "native_recompute_of_already_complete_task_facts": False,
        })
        last_end = end
        host_events = [
            event for event in worker_events
            if "script_sha256" in event and start <= event["started_ns"] <= end
        ]
        assert len(host_events) == (0 if step.get("outcome") == "invalid_request" else 1)
        step["host_business_executions"] = []
        for event in host_events:
            seq = event["sequence"]
            assigned_sequences.add(seq)
            call_dir = owner / "native" / f"call_{seq}"
            script_source = source(call_dir / "SCRIPT.py")
            logical_script_sha = hashlib.sha256((call_dir / "SCRIPT.py").read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            assert logical_script_sha == event["script_sha256"]
            step["host_business_executions"].append({
                "event": event,
                "event_source": source(worker_file),
                "script_source": script_source,
                "script_logical_text_sha256": logical_script_sha,
                "script_hash_semantics": "Worker hashes logical UTF-8 script text. SCRIPT.py is written with Windows newline translation. Raw file hash is retained separately.",
                "stdout_source": source(call_dir / "stdout.txt"),
                "stderr_source": source(call_dir / "stderr.txt"),
            })
        if attempt["name"] == "execute_blender_code":
            step["code_utf8_bytes"] = len(args["code"].encode("utf-8"))
            receipt_file = tool_dir / "NATIVE_RECEIPT.json"
            receipt = read_json(receipt_file)
            step["native_receipt_source"] = source(receipt_file)
            step["native_receipt_elapsed_ns"] = receipt["elapsed_ns"]
            step["native_stdout"] = receipt["response"]["result"]["result"]
        else:
            text = response["result"]["content"][0]["text"]
            body = json.loads(text)
            step["product_business_result"] = body
            step["product_body_text_utf8_bytes"] = len(text.encode("utf-8"))
            matches = [r for r in rpc["requests"] if r["method"] == "tools/call" and r["request_id"] == request["id"]]
            assert len(matches) == 1
            step["product_rpc"] = matches[0]
            step["product_rpc_source"] = source(rpc_file)
            trace_matches = [
                item["trace"] for item in audit
                if item.get("event") == "request_trace"
                and item["trace"].get("annotations", {}).get("mcp_request_id") == request["id"]
            ]
            assert len(trace_matches) == 1
            step["product_trace"] = trace_matches[0]
            step["product_trace_source"] = source(audit_file)
            if not attempt["is_error"]:
                observed = [r for r in audit if r.get("event") == "observe" and r.get("trace_id") == body["trace_id"]]
                assert len(observed) == 1
                step["product_task_work"] = observed[0]["task_work"]
                step["product_task_work_source"] = source(audit_file)
                assert len(body["pairs"]) == 3
                for pair in body["pairs"]:
                    facts = pair["facts"]
                    assert facts["spatial_relation"]["status"] == "measured"
                    assert facts["spatial_relation"]["value"] == "separated"
                    assert facts["surface_proximity"]["status"] == "measured"
                    assert facts["closed_solid_relation"]["reason"] == "closed_solid_work_budget"
                assert body["summary"]["nearest_separated_complete"] is True
                assert body["summary"]["unresolved_relations"] == []
                assert body["summary"]["unresolved_distances"] == {}
                assert compact(body).decode("utf-8") == text
        steps.append(step)
    qa_events = [e for e in worker_events if "script_sha256" in e and e["sequence"] not in assigned_sequences]
    assert len(qa_events) == 2
    assert qa_events[0]["script_sha256"] == qa_events[1]["script_sha256"]
    for event in qa_events:
        call_dir = owner / "native" / f"call_{event['sequence']}"
        for name in ("SCRIPT.py", "stdout.txt", "stderr.txt"):
            source(call_dir / name)
    p_success = [s for s in steps if s["tool"] == "human_eye_scene_observe" and not s["is_error"]]
    requested_required = any(
        {"spatial_relation", "surface_proximity"} <= set(s["arguments"]["query"]["requested_facts"])
        for s in p_success
    )
    return {
        "cell": cell_name,
        "group": consumer["group"],
        "round": consumer["round"],
        "task": consumer["task"],
        "consumer_source": source(cell_dir / "CONSUMER.json"),
        "consumer_started_ns": consumer["started_ns"],
        "final_received_ns": consumer["final_received_ns"],
        "unassigned_last_tool_to_final_ns": consumer["final_received_ns"] - last_end,
        "quality": "complete_correct_from_administrator_seal_no_rescoring",
        "steps": steps,
        "qa_snapshot_executions_excluded_from_consumer_tool_count": qa_events,
        "final": {"source": final_source, "text": final_text},
        "mechanism": {
            "naturally_requested_both_required_facts": requested_required if consumer["group"] == "P" else None,
            "used_correctly": True if consumer["group"] == "P" else None,
            "correct_use_basis": "Complete raw final manually compared with successful body, administrator quality seal confirms all 13 required facts. No new scorer was run.",
            "native_tool_calls": sum(s["tool"] == "execute_blender_code" for s in steps),
            "native_recompute_after_complete_answer_count": 0,
        },
    }


def main() -> None:
    plan = read_json(BATCH / "PLAN.json")
    work_order = read_json(OUTPUT.parent / "WORK_ORDER.json")
    frozen = read_json(BATCH / "MECHANISM_CLASSIFICATION.json")
    seal = read_json(Path("D:/hefe/verification/fixes/20261112_m4_spatial_fact_consumption_review/QUALITY_SEAL.json"))
    source(Path("D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_QUALITY_REVIEW.md"))
    source(BATCH / "runtime" / "actor.py")
    source(BATCH.parent / "native_plugin_complex_003" / "actor.py")
    source(BATCH / "runtime" / "consumer_transport.py")
    source(BATCH / "scoring" / "SCORING_CONTRACT.json")
    source(BATCH / "scoring" / "TRUTH.json")
    snapshot = read_json(BATCH / "scoring" / "ACTUAL_SNAPSHOT.json")
    assert work_order["new_consumer_allowance"] == 0
    assert work_order["new_Blender_or_product_run_allowance"] == 0
    assert seal["quality"]["complete_correct"] == 6
    assert seal["private_map_cost_usage_read_before_seal"] is False
    cells = [review_cell(f"spc{i:02}") for i in range(1, 7)]
    steps = [s for c in cells for s in c["steps"]]
    product_successes = [s for s in steps if s["tool"] == "human_eye_scene_observe" and not s["is_error"]]
    closed = []
    for cell in cells:
        for step in cell["steps"]:
            if "product_task_work" not in step:
                continue
            body = step["product_business_result"]
            for pair, work_pair in zip(body["pairs"], step["product_task_work"]["pairs"], strict=True):
                fact = pair["facts"]["closed_solid_relation"]
                closed.append({
                    "cell": cell["cell"],
                    "attempt": step["attempt"],
                    "candidate_index": pair["candidate_index"],
                    "fact": fact,
                    "fact_standalone_compact_json_bytes": len(compact(fact)),
                    "closed_solid_work": work_pair["closed_solid_work"],
                    "separately_measured_closed_duration_ns": None,
                })
    category_counts = Counter(s["category"] for s in steps)
    route_totals = {}
    for group in ("N", "P"):
        route_steps = [s for c in cells if c["group"] == group for s in c["steps"]]
        route_totals[group] = {
            "consumer_tool_attempts": len(route_steps),
            "actor_tool_handler_elapsed_ns_sum": sum(s["actor_elapsed_ns"] for s in route_steps),
            "actor_accounted_response_envelope_bytes_sum": sum(s["actor_accounted_response_envelope_bytes"] for s in route_steps),
            "native_calls": sum(s["tool"] == "execute_blender_code" for s in route_steps),
            "product_calls": sum(s["tool"] == "human_eye_scene_observe" for s in route_steps),
        }
    selected = [o for o in snapshot["objects"] if o["name"] in {"Target", "Peer_000", "Competing_001", "Near_003"}]
    geometry = [{
        "name": o["name"], "vertices": len(o["vertices_world"]), "triangles": len(o["triangles"]),
        "unique_triangle_edges": len({tuple(sorted((t[i], t[(i + 1) % 3]))) for t in o["triangles"] for i in range(3)}),
    } for o in selected]
    assert len(steps) == 12 and len(product_successes) == 3 and len(closed) == 9
    assert route_totals["N"]["native_calls"] == 8 and route_totals["P"]["native_calls"] == 0
    invalid = cells[1]["steps"][0]
    invalid_rpc = invalid["product_rpc"]
    result = {
        "schema": "m4-saved-spatial-consumption-mechanism-review-v1",
        "scope": "Existing six cells only. Standard-library saved-data extraction, no new consumers, Blender, product, training, or quality scoring.",
        "frozen_classification": frozen,
        "quality_seal": {"source": source(Path("D:/hefe/verification/fixes/20261112_m4_spatial_fact_consumption_review/QUALITY_SEAL.json")), "quality": seal["quality"]},
        "fixed_identity": {
            "product_commit": plan["fixed_product_commit"],
            "candidate_source_sha256": plan["candidate_source_sha256"],
            "plan_sha256": source(BATCH / "PLAN.json")["sha256"],
            "evidence_commit": work_order["author_commit"],
            "quality_review_commit": work_order["quality_review_commit"],
        },
        "measurement_semantics": {
            "actor_elapsed": "ATTEMPT perf_counter_ns inclusive handler wall window, including enclosed transport/host work. This is not full-task or exclusive algorithm latency.",
            "actor_response_bytes": "actor.py len(encoded(response)), compact UTF-8 JSON RPC envelope with LF charged to actor budget. The inherited base.encoded uses separators=(',', ':') plus one LF. Distinct from private product stdio framing and saved pretty-JSON file byte counts.",
            "product_rpc_bytes": "RPC.json confirmed sent_bytes/received_bytes on the private product stdio boundary, including framing.",
            "saved_file_bytes": "Exact on-disk file bytes, may include administrative metadata and pretty formatting.",
            "standalone_fact_bytes": "Compact JSON value footprint inside actual body. Not an observed counterfactual response size or predicted wire saving.",
            "nested_spans": "Inclusive durations share nested work. Never sum parent and children as independent costs.",
            "unassigned_gaps": "Observed wall gaps between actor windows or final delivery. Attribution to model reasoning, provider, transport, queue, or other work is unavailable here.",
            "closed_duration": "No independent closed-only span exists. task_facts contains surface, support, closed and ranking work. No causal full-task time saving is estimated.",
        },
        "geometry_from_frozen_snapshot": geometry,
        "cells": cells,
        "classification_counts_primary": {category: category_counts[category] for category in frozen["categories"]},
        "route_tool_totals": route_totals,
        "mechanism_verdict": {
            "passed": True,
            "eligible_P_consumers": 3,
            "qualified_P_consumers": 3,
            "required_minimum": 2,
            "P_native_calls": 0,
            "P_native_recomputations_of_complete_facts": 0,
            "generality": "One fixed named-object task repeated three times per route, without images. No evidence of unseen-task transfer or general 3D advantage.",
        },
        "invalid_nearest_witness_request": {
            "cell": "spc02", "attempt": 1,
            "actor_elapsed_ns": invalid["actor_elapsed_ns"],
            "actor_response_envelope_bytes": invalid["actor_accounted_response_envelope_bytes"],
            "arguments_compact_json_utf8_bytes": invalid["arguments_compact_json_utf8_bytes"],
            "rpc_sent_bytes": invalid_rpc["sent_bytes"],
            "rpc_received_bytes": invalid_rpc["received_bytes"],
            "rpc_elapsed_ns": invalid_rpc["elapsed_ns"],
            "host_executions": len(invalid["host_business_executions"]),
            "unassigned_gap_to_correction_ns": cells[1]["steps"][1]["preceding_unassigned_wall_gap_ns"],
            "counterfactual_whole_task_saving": None,
        },
        "optional_closed": {
            "requests_adding_closed": 3,
            "facts_unknown": len(closed),
            "facts": closed,
            "total_work_units": sum(f["closed_solid_work"]["work_units"] for f in closed),
            "total_standalone_fact_value_compact_json_bytes": sum(f["fact_standalone_compact_json_bytes"] for f in closed),
            "observed_task_facts_span_ns": [
                {"trace_id": s["product_trace"]["trace_id"], "duration_ns": next(p["duration_ns"] for p in s["product_trace"]["spans"] if p["name"] == "observation.task_facts")}
                for s in product_successes
            ],
            "closed_only_duration_ns": None,
            "whole_task_saving_if_omitted": None,
            "interpretation": "All required pair relations/proximity/nearest facts completed using measured support and surface results. Extra closed attempts exhausted budget and did not add closed classification in this task.",
        },
        "simplified_analysis": {
            "available_without_new_execution": {
                "unnecessary_invalid_request_count": 1,
                "optional_closed_unknown_count": 9,
                "P_native_recompute_count": 0,
                "N_precision_geometry_refresh": {"cell": "spc05", "attempt": 2, "meshes": 4, "vertices": 576, "triangles": 1136},
            },
            "limits": [
                "There was no valid required-facts-only request in this batch, so its duration and final result are unobserved.",
                "Omitting invalid or closed requests could alter consumer behavior, request packing, cache use and later timing. Saved evidence cannot yield causal total-task savings.",
                "The spc05 geometry refresh preceded the first answer and changed numeric conversion precision. Its separate cost is unavailable.",
                "The spc05 final winding call adds containment evidence and does not repeat already complete surface distances.",
                "QA initial/final snapshot executions are retained separately and excluded from consumer native-call counts.",
            ],
        },
        "single_next_direction": {
            "direction": "Unseen-task transfer under a newly frozen limited contract, conditional on the parent whole-task cost admission verdict.",
            "now": "No new experiment, implementation, interface change or training. Record optional closed work as an unmeasured opportunity within the current evidence.",
        },
    }
    (OUTPUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT / "SOURCES.json").write_text(json.dumps({"schema": "saved-input-sha256-manifest-v1", "files": sorted(SOURCES.values(), key=lambda s: s["path"])}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(result)
    print(json.dumps({"cells": len(cells), "steps": len(steps), "P_qualified": 3, "closed_unknown": len(closed), "source_files": len(SOURCES)}, ensure_ascii=False))


def write_report(result: dict) -> None:
    cells = result["cells"]
    lines = [
        "# 已封存六格的调用机制复查",
        "",
        "本次仅分析既有六格原件。质量沿用管理员已封存的 6/6 完整正确、78/78 必要事实结果，分组和成本在封存后解封。未新增模型、Blender、产品运行、训练或质量评分。工具名称和业务内容可能透露路线，本批遮蔽范围为分组标签与成本。",
        "",
        "## 冻结准则的结果",
        "",
        "P 三格均自然请求 spatial_relation 与 surface_proximity，随后正确使用返回的当前关系、距离和见证点。P 共四次产品尝试，其中一次参数拒绝、三次成功，原生工具调用为零，满足预登记的至少 2/3 采用条件。每格的最终答案及来源都完整保存在 RESULTS.json。",
        "",
        "这项结果限定为同一指定对象任务的三次重复消费，图像为零。未见任务迁移、一般三维优势以及整任务成本准入由各自证据判定。",
        "",
        "## 逐步轨迹",
        "",
        "下表列出全部十二次业务工具尝试。处理时长来自 ATTEMPT 的包含式 handler 墙钟窗口，响应字节来自 actor 对 UTF-8 JSON 响应包络的实际记账。完整单调时钟起止、请求参数和代码、响应、内部 RPC、host 执行、trace、最终答案及 SHA 均列入 RESULTS.json 与 SOURCES.json。",
        "",
        "| 格与顺序 | 路线 | 主分类 | handler 毫秒 | 响应包络字节 | 本步作用及原件 |",
        "|---|---|---|---:|---:|---|",
    ]
    for cell in cells:
        for s in cell["steps"]:
            request_path = s["request_source"]["path"]
            response_path = s["response_source"]["path"]
            role = s["role"]
            lines.append(f"| {cell['cell']}/{s['attempt']:02} | {cell['group']} | {s['category']} | {s['actor_elapsed_ns']/1e6:.4f} | {s['actor_accounted_response_envelope_bytes']} | {role} [请求]({request_path}) [响应]({response_path}) |")
    lines += [
        "",
        "spc05 第二步重读 4 份几何、576 点和 1136 三角形，代码明确把坐标转换改为双精度。该步发生在首次距离答案之前。第三步补充全顶点 winding 包含检查，复用已有几何。两步分别归入新增信息和未决核验，已完整回答事实后的原生重算计数为零。",
        "",
        "spc01 第二步将 Target 的 256 个世界顶点整体输出给消费者，响应包络达到 17036 字节。其余几何缓存在 host 进程供下一步求距。该数据体积是实测消费轨迹，独立删减后的行为和收益未观测。",
        "",
        "每格前后各有一次 QA 几何快照，共 12 次，已单列保留。它们与消费者业务工具调用分别计数。P 的成功产品调用内部各有一次 host 采集，共 3 次，仍属于其产品调用的内部工作。",
        "",
        "## 无效请求与修正",
        "",
    ]
    invalid = result["invalid_nearest_witness_request"]
    lines += [
        f"spc02 首次将 nearest_witness 作为独立 requested_fact。请求校验返回 executed=false 和 not_executed，host 执行为 0。该次额外尝试确认为 handler {invalid['actor_elapsed_ns']/1e6:.4f} 毫秒、响应包络 {invalid['actor_response_envelope_bytes']} 字节，产品 stdio 边界发送 {invalid['rpc_sent_bytes']} 字节、接收 {invalid['rpc_received_bytes']} 字节，内部 RPC 窗口为 {invalid['rpc_elapsed_ns']/1e6:.4f} 毫秒。",
        "",
        f"下一次请求删去该项，并保留其余三类事实。首次 handler 结束至修正 handler 开始间隔为 {invalid['unassigned_gap_to_correction_ns']/1e6:.4f} 毫秒。它是可见的未归因墙钟间隔，无法确定各环节的耗时份额，也无法据此预测避免该错误后的整题节省。",
        "",
        "## 九项额外 closed unknown",
        "",
        "三次成功 P 请求都额外要求 closed_solid_relation。每次三个候选均返回 closed_solid_work_budget unknown，共九项。必要的 spatial_relation 与 surface_proximity 均为 measured，最近者 summary 为完整，整体 partial 来自额外事实。最终答案保留了这一限制，封存评分确认必要任务完成。",
        "",
        "| 格 | closed 项数 | closed work_units | closed pair_tests | closed node_pair_visits | task_facts 包含式毫秒 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for cell in cells:
        successful = [s for s in cell["steps"] if "product_task_work" in s]
        if not successful:
            continue
        step = successful[0]
        closed = [p["closed_solid_work"] for p in step["product_task_work"]["pairs"]]
        span = next(p for p in step["product_trace"]["spans"] if p["name"] == "observation.task_facts")
        lines.append(f"| {cell['cell']} | 3 | {sum(p['work_units'] for p in closed)} | {sum(p['pair_tests'] for p in closed)} | {sum(p['node_pair_visits'] for p in closed)} | {span['duration_ns']/1e6:.4f} |")
    lines += [
        "",
        f"共确认 {result['optional_closed']['total_work_units']} 个 closed work_units。各候选复用了已准备的 pair/trees，但仍进行闭壳验证，最终触及工作预算。九个 closed 值按实际正文的紧凑 JSON 单独计量，各 229 字节，共 {result['optional_closed']['total_standalone_fact_value_compact_json_bytes']} 字节。这是既有正文组件的大小，删字段后的实际包络和传输大小尚未发生。",
        "",
        "现有 trace 只给出 surface、support、closed、ranking 等共用的 task_facts 窗口，缺少 closed 独立时段。上表的全部 task_facts 时长不能归为额外 closed 耗时。原件中没有一次仅请求必要事实的成功反事实运行，因此无法测得去除 closed 后的整题耗时、token 或成本变化。",
        "",
        "## 可确认的局部成本及归因边界",
        "",
        "| 路线 | 业务尝试 | 原生调用 | 产品调用 | handler 总毫秒 | 响应包络总字节 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for group, values in result["route_tool_totals"].items():
        lines.append(f"| {group} | {values['consumer_tool_attempts']} | {values['native_calls']} | {values['product_calls']} | {values['actor_tool_handler_elapsed_ns_sum']/1e6:.4f} | {values['actor_accounted_response_envelope_bytes_sum']} |")
    lines += [
        "",
        "这里的 handler 合计仅覆盖工具处理窗口。模型任务的完整耗时、启动清理、输出入 token 与费用由成本报告独立统计。内部 RPC、host 采集及 trace 与外层 handler 含有嵌套工作，分别保留后不相加。空档时间保留为未归因，未命名为推理或插件延迟。",
        "",
        "## 一次简化分析与下一方向",
        "",
        "当前保存数据已足以识别一次无效参数往返、九项未增加闭壳结论的额外请求工量，以及原生路线的一次精度刷新。P 的零原生重算说明本题事实交付被实际消费。以上均为本批观测，尚不能计算删去这些步骤后的因果收益。",
        "",
        "建议仅保留一个后续方向。在整任务成本满足父报告准入后，冻结一个未见的小范围任务，验证必要事实的自然消费能否迁移。当前不实施改动或训练。额外 closed 工量作为本批待证机会保留，后续评审可结合迁移任务判断。",
        "",
        "## 证据与可重放性",
        "",
        f"分析脚本只读取既有文件，并输出本目录的 JSON 和报告。[分析脚本]({(OUTPUT/'analyze_trajectories.py').as_posix()}) [完整结果]({(OUTPUT/'RESULTS.json').as_posix()}) [输入 SHA 清单]({(OUTPUT/'SOURCES.json').as_posix()})",
        "",
        f"质量结论直接引用管理员封存件。[质量报告](D:/hefe/docs/M4_SPATIAL_FACT_CONSUMPTION_001_QUALITY_REVIEW.md) [封存件](D:/hefe/verification/fixes/20261112_m4_spatial_fact_consumption_review/QUALITY_SEAL.json)",
        "",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
