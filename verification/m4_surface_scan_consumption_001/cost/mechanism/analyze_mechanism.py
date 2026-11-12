"""Read the six frozen cells and reconstruct receipt-level consumption evidence.

This stdlib-only analysis starts no consumer, server, Blender, or API request.
CLI item results are receipt evidence. Provider-rendered model inputs were not
recorded, so their content and any effective truncation remain unknown.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
ROOT = BATCH.parents[1]
SEQUENCE = ("N1", "P1", "P2", "N2", "N3", "P3")
NATIVE_ROW = re.compile(r"^(Obj_\d{3}) (Obj_\d{3}) ([0-9.eE+\-]+)(?:\s|$)", re.M)
FIRST_COMPLETE = {"N1": 3, "P1": 1, "P2": 1, "N2": 3, "N3": 2, "P3": 1}

# These annotations summarize the retained source and output, after manual read.
# They classify facts acquired, without attributing an unobserved mental state.
ANNOTATIONS = {
    "N1": [
        ("catalog", "读取单位、网格目录与实例数量。尚无距离清单。"),
        ("capture_and_bounds", "采集求值网格并缓存，按AABB下界留下112对。candidate_names中的数值是下界。"),
        ("first_surface_solution", "用缓存三角几何精算112候选，输出71对、41阴性候选及退化计数。"),
        ("validation_and_formatting", "补有限值、总三角数、最近排除下界与零值分组。复用已算距离。"),
    ],
    "P1": [
        ("first_surface_solution", "普通surface_scan返回完整71对、全部276对处置、零unknown及绑定。单位为米。"),
        ("repeat_with_brief", "请求brief，返回的匹配和字段仍相同。仅trace_id变化。"),
        ("failed_subset_query", "尝试以Obj_001为目标、其余23对象为候选，触发1..3候选上限。没有补得事实。"),
        ("catalog_after_complete_receipt", "原生重读24个对象名称和面数量，目录信息已在匹配及覆盖中部分出现。"),
        ("native_recompute_and_format", "重新采集全部网格，用新NumPy求解器计算阈值候选并输出71对毫米短表。"),
    ],
    "P2": [
        ("first_surface_solution", "普通surface_scan返回完整71对、全部276对处置、零unknown及绑定。单位为米。"),
        ("repeat_with_brief", "请求brief，返回的匹配和字段仍相同。仅trace_id变化。"),
        ("catalog_after_complete_receipt", "原生重读24个对象名称和顶点、面数量。"),
        ("native_recompute_and_format", "重新采集全部网格，用新NumPy求解器计算阈值候选并输出71对毫米短表。"),
    ],
    "N2": [
        ("catalog", "读取单位、对象类型和隐藏状态。"),
        ("capture_and_bounds", "采集求值网格并缓存，打印三角计数和包围界。"),
        ("first_surface_solution", "以对象及三角包围界筛选，精算20998三角对，输出71对和完整覆盖计数。"),
        ("same_solver_exhaustive_validation", "在同一缓存、同一求解器上无剪枝遍历436640三角对并验对称性，又为最近阴性遍历阴性对象对。"),
    ],
    "N3": [
        ("catalog", "读取单位、24个网格对象和modifier目录。"),
        ("first_surface_solution", "一次采集并缓存全部网格，以包围界筛选后精算20998三角对，输出71对和有限值、退化检查。"),
        ("same_solver_exhaustive_validation_and_format", "同一缓存、同一求解器无剪枝遍历436640三角对，输出最近阴性、阳性短表和零值分组。"),
    ],
    "P3": [
        ("first_surface_solution", "普通surface_scan返回完整71对、全部276对处置、零unknown及绑定。单位为米。"),
        ("repeat_with_brief", "请求brief，返回的匹配和字段仍相同。仅trace_id变化。"),
        ("failed_subset_query", "尝试23候选task查询，触发1..3候选上限。没有补得事实。"),
        ("failed_pagination_query", "尝试在surface_scan内增加indices分页，严格schema拒绝。没有补得事实。"),
        ("catalog_after_complete_receipt", "原生重读24对象名称和顶点、面数量。"),
        ("native_recompute_and_format", "重新采集全部网格，以扇形三角化和新NumPy求解器计算阈值候选，输出71对毫米短表。"),
    ],
}


def read(path):
    return json.loads(path.read_bytes())


def compact_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def text_content(result):
    return "\n".join(block["text"] for block in result.get("content", []) if block.get("type") == "text")


def native_text(value):
    return value.get("result", {}).get("result", "")


def pair_rows(item):
    value = json.loads(text_content(item["result"]))
    if item["tool"] == "human_eye_scene_observe" and value.get("result_kind") == "surface_scan":
        return {tuple(sorted(obj["name"] for obj in row["objects"])): row["distance_m"] * 1000 for row in value["matches"]}
    return {tuple(sorted((a, b))): float(number) for a, b, number in NATIVE_ROW.findall(native_text(value))}


def projection(value):
    """An offline size probe, not a changed or accepted product response."""
    return {
        key: value[key]
        for key in (
            "result_kind", "status", "scope", "threshold_m", "source_envelope", "unit", "coordinate_frame", "coverage",
            "scope_issues", "unsupported_objects", "unresolved", "measurement_semantics", "binding",
            "execution_authority", "delivery", "trace_id",
        )
    } | {
        "matches": [
            {"objects": [obj["name"] for obj in row["objects"]], "distance_m": row["distance_m"]}
            for row in value["matches"]
        ]
    }


def main():
    sources = {}
    checks = 0

    def frozen(path):
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        sources[relative] = {"bytes": len(data), "sha256": digest(data)}
        return data

    def check(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)

    for relative in (
        "runtime/actor.py", "runtime/consumer_transport.py", "runtime/pack_quality.py",
        "PREPARATION_COST.json", "private/PACKAGING_COST.json", "FORMAL_PUBLICATION.json",
    ):
        frozen(BATCH / relative)
    for relative in (
        "verification/native_plugin_complex_003/reused/stdio_attach.py",
        "human_eye_plugin/live_spatial_mcp.py", "human_eye_plugin/surface_scan.py",
    ):
        frozen(ROOT / relative)

    rows = []
    for cell in SEQUENCE:
        folder = BATCH / "cells" / cell
        consumer = json.loads(frozen(folder / "CONSUMER.json"))
        events = [json.loads(line) for line in frozen(folder / "events.jsonl").splitlines()]
        timing = json.loads(frozen(folder / "CELL_FINAL_TIMING.json"))
        completed = [event for event in events if event["event"].get("type") == "item.completed"
                     and event["event"].get("item", {}).get("type") == "mcp_tool_call"]
        starts = {event["event"]["item"]["id"]: event["perf_ns"] for event in events
                  if event["event"].get("type") == "item.started"
                  and event["event"].get("item", {}).get("type") == "mcp_tool_call"}
        check(len(completed) == len(consumer["tool_calls"]) == len(ANNOTATIONS[cell]), (cell, "attempt_count"))
        bridge = {}
        for path in sorted((folder / "attachments").glob("bridge_*/*/RX.bin")):
            rx = json.loads(frozen(path))
            if rx.get("id") is not None:
                bridge[rx["id"]] = (path, rx)
        product = {}
        for path in sorted((folder / "owner" / "plugin").glob("*/TX.bin")):
            tx = json.loads(path.read_bytes())
            if tx.get("method") == "tools/call":
                product[tx["id"]] = (path, tx)
        previous_end = consumer["prompt_submitted_ns"]
        attempts = []
        first_scan = None
        for index, (entry, annotation) in enumerate(zip(completed, ANNOTATIONS[cell]), 1):
            item = entry["event"]["item"]
            check(item == consumer["tool_calls"][index - 1]["item"], (cell, index, "raw_event_projection"))
            tool_folder = folder / "owner" / ("tool_" + str(index).zfill(2))
            request = json.loads(frozen(tool_folder / "REQUEST.json"))
            response_path = tool_folder / "RESPONSE.json"
            if not response_path.exists():
                response_path = tool_folder / "ERROR_RESPONSE.json"
            response = json.loads(frozen(response_path))
            attempt = json.loads(frozen(tool_folder / "ATTEMPT.json"))
            check(request["params"]["name"] == item["tool"], (cell, index, "request_name"))
            check(request["params"]["arguments"] == item["arguments"], (cell, index, "request_args"))
            check(response["result"]["content"] == item["result"]["content"], (cell, index, "owner_to_cli_exact_content"))
            check(response["result"].get("structuredContent") == item["result"].get("structured_content"), (cell, index, "owner_to_cli_structured_content"))
            check(item["status"] == ("failed" if response["result"].get("isError") else "completed"), (cell, index, "owner_to_cli_error_status"))
            bridge_path, bridged = bridge[request["id"]]
            check(bridged == response, (cell, index, "owner_to_stdio_exact_result"))
            text = text_content(item["result"])
            value = json.loads(text)
            started = starts[item["id"]]
            ended = entry["perf_ns"]
            check(previous_end <= started <= ended, (cell, index, "event_order"))
            category, note = annotation
            row = {
                "attempt": index,
                "tool": item["tool"],
                "item_id": item["id"],
                "category": category,
                "manual_interpretation": note,
                "event_started_ns": started,
                "event_completed_ns": ended,
                "event_tool_wall_ns": ended - started,
                "preceding_non_tool_gap_ns": started - previous_end,
                "owner_started_ns": attempt["started_ns"],
                "owner_elapsed_ns": attempt["elapsed_ns"],
                "tool_status": item["status"],
                "result_is_error": bool(response["result"].get("isError")),
                "text_chars": len(text),
                "text_utf8_bytes": len(text.encode("utf8")),
                "text_sha256": digest(text.encode("utf8")),
                "structured_content": item["result"].get("structured_content"),
                "pair_rows_present": len(pair_rows(item)),
                "response_source": response_path.relative_to(ROOT).as_posix(),
                "stdio_response_source": bridge_path.relative_to(ROOT).as_posix(),
                "business_content_equal_across_owner_stdio_cli": True,
                "cli_envelope_normalization": "isError becomes item.status; structuredContent becomes structured_content, null when absent",
            }
            if item["tool"] == "human_eye_scene_observe":
                product_tx_path, product_tx = product[request["id"]]
                frozen(product_tx_path)
                product_rx_path = product_tx_path.with_name("RX.bin")
                product_rx = json.loads(frozen(product_rx_path))
                check(product_tx == request, (cell, index, "owner_to_product_request"))
                check(product_rx == response, (cell, index, "product_to_owner_result"))
                row["product_response_source"] = product_rx_path.relative_to(ROOT).as_posix()
                row["arguments"] = item["arguments"]
                row["delivery"] = value.get("delivery")
                row["coverage"] = value.get("coverage")
                row["product_error"] = value.get("error")
                if value.get("result_kind") == "surface_scan":
                    check(len(value["matches"]) == 71, (cell, index, "all_scan_rows"))
                    check(len(pair_rows(item)) == 71, (cell, index, "unique_scan_rows"))
                    check(all(obj.get("name") and obj.get("id") for m in value["matches"] for obj in m["objects"]), (cell, index, "ids_and_names"))
                    reduced = projection(value)
                    dictionary = {obj["name"]: obj["id"] for m in value["matches"] for obj in m["objects"]}
                    identity_preserving = dict(reduced, object_ids=dictionary)
                    check(len(reduced["matches"]) == 71, (cell, index, "projection_count"))
                    check([m["distance_m"] for m in reduced["matches"]] == [m["distance_m"] for m in value["matches"]], (cell, index, "projection_distances_unrounded"))
                    check([m["objects"] for m in reduced["matches"]] == [[o["name"] for o in m["objects"]] for m in value["matches"]], (cell, index, "projection_names"))
                    check(all(dictionary[obj["name"]] == obj["id"] for m in value["matches"] for obj in m["objects"]), (cell, index, "identity_dictionary_roundtrip"))
                    if first_scan is None:
                        first_scan = value
                    row["equal_to_first_scan_except_trace_id"] = {
                        k: v for k, v in value.items() if k != "trace_id"
                    } == {k: v for k, v in first_scan.items() if k != "trace_id"}
                    row["offline_projection_size_probe"] = {
                        "raw_bytes": len(text.encode("utf8")),
                        "projected_bytes": len(compact_bytes(reduced)),
                        "projected_with_id_dictionary_bytes": len(compact_bytes(identity_preserving)),
                        "id_dictionary_entries": len(dictionary),
                        "removed_bytes": len(text.encode("utf8")) - len(compact_bytes(reduced)),
                        "scope": "same numeric facts/names/coverage/global binding; per-row IDs, witnesses and method removed; not a product or action-authority contract",
                        "projected_sha256": digest(compact_bytes(reduced)),
                        "actual_provider_render_bytes": None,
                        "token_or_time_savings_measured": False,
                    }
            else:
                code = item["arguments"]["code"]
                parsed = ast.parse(code)
                row["code_utf8_bytes"] = len(code.encode("utf8"))
                row["code_sha256"] = digest(code.encode("utf8"))
                row["code_attribute_calls"] = sorted({node.func.attr for node in ast.walk(parsed)
                                                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)})
                row["stdout_excerpt"] = native_text(value)[:450]
                native_receipt = json.loads(frozen(tool_folder / "NATIVE_RECEIPT.json"))
                row["native_elapsed_ns"] = native_receipt.get("elapsed_ns")
                check(native_receipt["response"] == value, (cell, index, "native_response"))
            previous_end = ended
            attempts.append(row)

        first = attempts[FIRST_COMPLETE[cell] - 1]
        final = consumer["final_received_ns"]
        check(first["pair_rows_present"] == 71, (cell, "first_complete_list_count"))
        tail_tools = sum(row["event_tool_wall_ns"] for row in attempts[FIRST_COMPLETE[cell]:])
        tail = final - first["event_completed_ns"]
        recompute_consistency = None
        if cell.startswith("P"):
            original = pair_rows(consumer["tool_calls"][0]["item"])
            recomputed = pair_rows(consumer["tool_calls"][-1]["item"])
            check(original.keys() == recomputed.keys(), (cell, "recompute_pair_set"))
            max_error = max(abs(original[pair] - recomputed[pair]) for pair in original)
            check(max_error <= 0.000500001, (cell, "recompute_distance_consistency"))
            recompute_consistency = {"matching_pair_count": len(original), "max_distance_difference_mm": max_error}
        rows.append({
            "cell": cell,
            "model_input_render": "unknown; provider request bodies and CLI postprocessing messages absent",
            "provider_requests": consumer["provider_requests"],
            "prompt_submitted_ns": consumer["prompt_submitted_ns"],
            "final_received_ns": final,
            "full_cell_wall_ns": timing["full_cell_wall_ns"],
            "first_complete_numeric_list_receipt_attempt": FIRST_COMPLETE[cell],
            "first_complete_numeric_list_receipt_ns": first["event_completed_ns"],
            "prompt_to_first_complete_list_receipt_ns": first["event_completed_ns"] - consumer["prompt_submitted_ns"],
            "first_complete_list_receipt_to_final_ns": tail,
            "later_tool_event_wall_ns": tail_tools,
            "remaining_non_tool_tail_ns": tail - tail_tools,
            "tail_scope": "observed interval; not a counterfactual saving, model-only time or proof of model visibility",
            "attempts": attempts,
            "recompute_consistency": recompute_consistency,
            "public_commentary": consumer["all_public_messages"][:-1],
            "final_sha256": digest(consumer["final"].encode("utf8")),
            "tool_error_count": sum(row["result_is_error"] for row in attempts),
        })
    output = {
        "schema": "m4_surface_scan_consumption_mechanism_review_v1",
        "delivery_commit": "e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3",
        "new_blender_model_api_runs": 0,
        "learning_context": {"context_bound": False, "host_epoch": 5, "rebind_required": True},
        "sources": sources,
        "source_file_count": len(sources),
        "assertions_passed": checks,
        "cells": rows,
        "limits": [
            "complete result at owner/stdio/CLI receipts does not prove complete model-rendered input",
            "P2/P3 truncation wording is consumer self-report; threshold and exact missing rows are unknown",
            "event tool and inter-tool intervals do not reveal internal model reasoning or network/service attribution",
            "same receipt facts followed by native recompute does not prove distrust or necessity",
            "offline projection byte reduction is not measured token, latency or quality benefit",
        ],
    }
    (HERE / "MECHANISM.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    print(json.dumps({"sources": len(sources), "checks": checks,
                      "cells": [{"cell": row["cell"],
                                 "first_complete_attempt": row["first_complete_numeric_list_receipt_attempt"],
                                 "post_list_seconds": row["first_complete_list_receipt_to_final_ns"] / 1e9,
                                 "later_tool_seconds": row["later_tool_event_wall_ns"] / 1e9,
                                 "remaining_tail_seconds": row["remaining_non_tool_tail_ns"] / 1e9}
                                for row in rows]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
