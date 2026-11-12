"""Reconstruct the fixed nine-cell consumption mechanism from retained receipts.

Stdlib only. No subprocess, server, Blender, provider, or model is started.
Output is written only beside this script. Source files are read without edits.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import statistics
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parents[1]
ROOT = BATCH.parents[1]
SEQUENCE = ("N1", "O1", "C1", "O2", "C2", "N2", "C3", "N3", "O3")
DELIVERY = "f5cfcf5e4768b1b6c31127b5d4a6c1227b8d7907"
SEAL = Path("D:/hefe/verification/fixes/20261113_m4_surface_scan_compact_quality_review/QUALITY_SEAL.json")
SEAL_SHA = "c054d8b5ea8ef672a9b3558c9fd33d485e87593fc53c87df6f2ec0ba6a82d9eb"
PLAN = Path("D:/hefe/docs/M4_SURFACE_SCAN_COMPACT_CONSUMPTION_001_COST_PLAN.md")
PLAN_SHA = "ef73d9a91d237141f7c90da4685a8207bdaf99fee82e05c19edd4a1af71193f5"
FIRST_COMPLETE = {"N1": 2, "O1": 1, "C1": 1, "O2": 1, "C2": 1,
                  "N2": 3, "C3": 1, "N3": 3, "O3": 1}
FINAL_FORMAT = {"N1": "zero_aggregate_plus_positive_table", "N2": "zero_aggregate_plus_positive_table",
                "N3": "object_a_aggregate", "O1": "flat_71_row_table", "O2": "flat_71_row_table",
                "O3": "flat_71_row_table", "C1": "flat_71_row_table", "C2": "flat_71_row_table", "C3": "flat_71_row_table"}
NATIVE_ROW = re.compile(r"^(Obj_\d{3}) (Obj_\d{3}) ([0-9.eE+\-]+)(?:\s|$)", re.M)
EXPECTED_SOURCE = {
    "O": "c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943",
    "C": "4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6",
}

# Manual source-reading classifications. The raw code, stdout and hashes remain
# bound below, so these labels can be checked independently of this summary.
ANNOTATIONS = {
    "N1": [
        ("catalog_and_capture", "采集24个求值网格并打印世界坐标包围界，尚无表面距离清单。"),
        ("first_surface_solution", "对276对象对做AABB筛选，精算112候选，输出71匹配和最近阴性。"),
        ("validation_and_formatting", "复用已有距离，补零值分组、正值毫米格式、三角面积与有限值检查。"),
    ],
    "O1": [
        ("first_surface_solution", "旧扫描OPT1完整返回71匹配、276对处置及零unknown。"),
        ("repeat_with_brief", "改请求brief，再次返回同一完整详细结果，除trace_id外一致。"),
        ("catalog_after_complete_receipt", "原生补读24对象名称、顶点及面数量。"),
        ("native_recompute_and_format", "重新采集全场求值几何，生成NumPy求解器，重算71匹配并输出毫米表。"),
    ],
    "C1": [("first_surface_solution", "显式brief返回完整71行紧凑任务表，随后直接发布最终答案。")],
    "O2": [
        ("first_surface_solution", "旧扫描OPT1完整返回71匹配、276对处置及零unknown。"),
        ("repeat_with_brief", "改请求brief，再次返回同一完整详细结果，除trace_id外一致。"),
        ("catalog_after_complete_receipt", "原生补读24对象名称与面数量。"),
        ("native_recompute_and_format", "重新采集全场求值几何，生成NumPy求解器，重算71匹配并输出毫米表。"),
    ],
    "C2": [("first_surface_solution", "显式brief返回完整71行紧凑任务表，随后直接发布最终答案。")],
    "N2": [
        ("catalog", "读取24对象、单位、顶点/面及modifier目录。"),
        ("capture_and_bounds", "采集并缓存求值三角几何，打印112候选的AABB下界及退化检查。"),
        ("first_surface_solution", "复用缓存几何精算112候选，输出71匹配及最近阴性。"),
        ("same_solver_exhaustive_validation", "复用同一缓存与mesh_distance，遍历全部276对象对，核对筛选和71集合，补有限值/空网格检查。"),
    ],
    "C3": [("first_surface_solution", "显式brief返回完整71行紧凑任务表，随后直接发布最终答案。")],
    "N3": [
        ("catalog", "读取24对象、单位、隐藏状态和modifier目录。"),
        ("capture_and_bounds", "采集并缓存求值三角几何，打印网格包围界与112候选AABB下界。"),
        ("first_surface_solution", "复用缓存精算112候选，输出71匹配和41测得阴性。"),
        ("same_solver_exhaustive_validation_and_format", "同一缓存与surface_distance遍历276对象对，验证71集合一致，补退化/空网格、最近阴性及分组格式。"),
    ],
    "O3": [
        ("first_surface_solution", "显式full的旧扫描OPT1完整返回71匹配、276对处置及零unknown。"),
        ("repeat_with_brief", "改请求brief，再次返回同一完整详细结果，除trace_id外一致。"),
        ("catalog_after_complete_receipt", "原生补读24对象名称与面数量。"),
        ("native_recompute_with_intermediate_error", "重新采集全场几何并生成NumPy求解器，首次输出仅70匹配且另有两对距离错误。"),
        ("native_solver_correction", "复用原生缓存，补反向边-三角相交检测，输出71匹配并修正零距离。"),
    ],
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def text_content(result):
    return "\n".join(block["text"] for block in result.get("content", []) if block.get("type") == "text")


def native_stdout(value):
    return value.get("result", {}).get("result", "")


def pairs(item):
    value = json.loads(text_content(item["result"]))
    if item["tool"] == "human_eye_scene_observe":
        if value.get("display_encoding") == "surface-scan-task-table-v1":
            return {tuple(sorted((row[0], row[1]))): row[4] * 1000 for row in value["matches"]}
        return {tuple(sorted(obj["name"] for obj in row["objects"])): row["distance_m"] * 1000
                for row in value.get("matches", [])}
    return {tuple(sorted((a, b))): float(number)
            for a, b, number in NATIVE_ROW.findall(native_stdout(value))}


def qualifying_pairs(item):
    return {pair: distance for pair, distance in pairs(item).items() if distance <= 2.0}


def pair_comparison(original, later):
    shared = original.keys() & later.keys()
    return {
        "original_count": len(original), "later_count": len(later),
        "missing": [list(pair) for pair in sorted(original.keys() - later.keys())],
        "extra": [list(pair) for pair in sorted(later.keys() - original.keys())],
        "max_shared_distance_difference_mm": max((abs(original[p] - later[p]) for p in shared), default=None),
        "differences_over_0_0005_mm": [
            {"pair": list(pair), "scan_mm": original[pair], "native_mm": later[pair],
             "absolute_difference_mm": abs(original[pair] - later[pair])}
            for pair in sorted(shared) if abs(original[pair] - later[pair]) > 0.000500001
        ],
    }


def main():
    sources = {}
    checks = []

    def source_name(path):
        try:
            return path.relative_to(ROOT).as_posix()
        except ValueError:
            return path.as_posix()

    def frozen(path):
        raw = path.read_bytes()
        sources[source_name(path)] = {"bytes": len(raw), "sha256": sha(raw)}
        return raw

    def read(path):
        return json.loads(frozen(path))

    def check(condition, *label):
        checks.append(list(label))
        if not condition:
            raise AssertionError(label)

    seal_raw = frozen(SEAL)
    check(sha(seal_raw) == SEAL_SHA, "fixed_quality_seal")
    seal = json.loads(seal_raw)
    check(sha(frozen(PLAN)) == PLAN_SHA, "fixed_cost_plan")
    check(seal["delivery_commit"] == DELIVERY, "delivery_binding")
    mapping = read(BATCH / "private" / "ANON_MAP.json")
    check(tuple(row["cell"] for row in mapping["rows"]) == SEQUENCE, "fixed_original_order")
    anonymous = {row["cell"]: row for row in mapping["rows"]}
    sealed = {row["anonymous_id"]: row for row in seal["answers"]}
    rows = []
    for cell in SEQUENCE:
        folder = BATCH / "cells" / cell
        consumer = read(folder / "CONSUMER.json")
        events = [json.loads(line) for line in frozen(folder / "events.jsonl").splitlines()]
        timing = read(folder / "CELL_FINAL_TIMING.json")
        identity = read(folder / "owner" / "IDENTITY.json")
        config = read(folder / "ACTOR_CONFIG.json")
        tools_ledger = read(folder / "owner" / "TOOLS.json")
        quality = sealed[anonymous[cell]["anonymous_id"]]
        final_raw = consumer["final"].encode("utf8")
        check(sha(final_raw) == quality["final_sha256"], cell, "sealed_final_hash")
        check(frozen(folder / "PUBLIC_FINAL.txt") == final_raw, cell, "public_final_exact")
        check(frozen(folder / "final.txt") == final_raw, cell, "cli_final_file_exact")
        check(consumer["valid_completion"] == quality["consumer_valid_completion"], cell, "validity_preserved")
        check(consumer["status"] == quality["execution_state"], cell, "status_preserved")
        check([row["event"] for row in consumer["errors"]] == [row["event"] for row in quality["execution_errors"]],
              cell, "errors_preserved")
        check(identity["external_group"] == cell[0], cell, "actual_external_group")
        if cell[0] in EXPECTED_SOURCE:
            check(identity["runtime_identity"]["source_sha256"] == EXPECTED_SOURCE[cell[0]], cell, "loaded_product_source")
        else:
            check(identity["runtime_identity"] is None and identity["product_serve_entry"] is None, cell, "native_no_product")

        bridge = {}
        declarations = None
        for tx_path in sorted((folder / "attachments").glob("bridge_*/*/TX.bin")):
            tx = read(tx_path)
            rx_path = tx_path.with_name("RX.bin")
            if not rx_path.exists():
                continue
            rx = read(rx_path)
            if tx.get("method") == "tools/list":
                declarations = rx["result"]["tools"]
            if tx.get("method") == "tools/call":
                check(tx["id"] == rx["id"], cell, "bridge_request_response_id", tx["id"])
                bridge[tx["id"]] = (tx_path, tx, rx_path, rx)
        check(declarations is not None, cell, "actual_cli_tools_list")
        check([tool["name"] for tool in declarations] == identity["exposed_tool_names"], cell, "actual_exposed_tools")
        scan_description = next((tool["description"] for tool in declarations if tool["name"] == "human_eye_scene_observe"), None)
        product = {}
        for tx_path in sorted((folder / "owner" / "plugin").glob("*/TX.bin")):
            tx = read(tx_path)
            if tx.get("method") == "tools/call":
                product[tx["id"]] = (tx_path, tx)
        completed = [row for row in events if row["event"].get("type") == "item.completed"
                     and row["event"].get("item", {}).get("type") == "mcp_tool_call"]
        starts = {row["event"]["item"]["id"]: row["perf_ns"] for row in events
                  if row["event"].get("type") == "item.started"
                  and row["event"].get("item", {}).get("type") == "mcp_tool_call"}
        check(len(completed) == len(consumer["tool_calls"]) == len(ANNOTATIONS[cell]) == tools_ledger["attempts"],
              cell, "attempt_count")
        previous_end = consumer["prompt_submitted_ns"]
        attempts = []
        first_scan = None
        for index, (entry, annotation) in enumerate(zip(completed, ANNOTATIONS[cell]), 1):
            item = entry["event"]["item"]
            check(item == consumer["tool_calls"][index - 1]["item"], cell, index, "raw_event_projection")
            tool_folder = folder / "owner" / ("tool_" + str(index).zfill(2))
            request = read(tool_folder / "REQUEST.json")
            response_path = tool_folder / "RESPONSE.json"
            if not response_path.exists():
                response_path = tool_folder / "ERROR_RESPONSE.json"
            response = read(response_path)
            attempt = read(tool_folder / "ATTEMPT.json")
            check(request["params"]["name"] == item["tool"], cell, index, "request_name")
            check(request["params"]["arguments"] == item["arguments"], cell, index, "request_arguments")
            check(response["result"]["content"] == item["result"]["content"], cell, index, "owner_cli_exact_content")
            check(response["result"].get("structuredContent") == item["result"].get("structured_content"),
                  cell, index, "owner_cli_structured_content")
            check(item["status"] == ("failed" if response["result"].get("isError") else "completed"),
                  cell, index, "owner_cli_error_status")
            tx_path, tx, rx_path, rx = bridge[request["id"]]
            check(tx == request and rx == response, cell, index, "owner_stdio_request_response_exact")
            started = starts[item["id"]]
            ended = entry["perf_ns"]
            check(previous_end <= started <= attempt["started_ns"] <= attempt["started_ns"] + attempt["elapsed_ns"] <= ended,
                  cell, index, "nested_event_owner_order")
            text = text_content(item["result"])
            value = json.loads(text)
            category, note = annotation
            row = {
                "attempt": index, "tool": item["tool"], "item_id": item["id"],
                "category": category, "manual_source_interpretation": note,
                "event_started_ns": started, "event_completed_ns": ended,
                "event_tool_wall_ns": ended - started,
                "preceding_non_tool_gap_ns": started - previous_end,
                "owner_started_ns": attempt["started_ns"], "owner_elapsed_ns": attempt["elapsed_ns"],
                "tool_status": item["status"], "is_error": bool(response["result"].get("isError")),
                "tool_text_utf8_bytes": len(text.encode("utf8")), "tool_text_sha256": sha(text.encode("utf8")),
                "owner_response_wire_bytes": sources[source_name(response_path)]["bytes"],
                "distance_pair_rows": len(pairs(item)), "qualifying_pair_rows": len(qualifying_pairs(item)),
                "request_source": source_name(tool_folder / "REQUEST.json"),
                "response_source": source_name(response_path),
                "stdio_request_source": source_name(tx_path), "stdio_response_source": source_name(rx_path),
                "exact_owner_stdio_cli_business_content": True,
                "cli_normalization": "isError maps to item.status; structuredContent maps to structured_content/null",
                "actual_provider_rendered_input": None, "actual_provider_truncation": None,
            }
            if item["tool"] == "human_eye_scene_observe":
                product_tx_path, product_tx = product[request["id"]]
                product_rx_path = product_tx_path.with_name("RX.bin")
                product_rx = read(product_rx_path)
                check(product_tx == request and product_rx == response, cell, index, "product_owner_exact")
                check(value["coverage"] == {"objects": 24, "total_pairs": 276, "bound_excluded": 164,
                      "measured_match": 71, "measured_nonmatch": 41, "unknown": 0, "deferred": 0,
                      "catalog_scope_confirmed": True}, cell, index, "full_coverage")
                check(len(value["matches"]) == len(qualifying_pairs(item)) == 71, cell, index, "complete_71_unique_matches")
                check(value["delivery"]["complete"] and value["delivery"]["delivered_matches"] == 71,
                      cell, index, "delivery_complete")
                check(value["binding"]["runtime_source_sha256"] == EXPECTED_SOURCE[cell[0]], cell, index, "response_source_identity")
                if first_scan is None:
                    first_scan = value
                row.update({
                    "product_response_source": source_name(product_rx_path),
                    "arguments": item["arguments"],
                    "response_detail_requested": item["arguments"].get("response_detail", "omitted"),
                    "display_encoding": value.get("display_encoding", "detailed_match_records"),
                    "coverage": value["coverage"], "delivery": value["delivery"], "binding": value["binding"],
                    "same_as_first_scan_except_trace_id": {k: v for k, v in value.items() if k != "trace_id"}
                        == {k: v for k, v in first_scan.items() if k != "trace_id"},
                    "new_unknown_resolution": False,
                })
                check(len(text.encode("utf8")) == (7911 if cell[0] == "C" else 34754),
                      cell, index, "observed_scan_text_bytes")
                check(row["same_as_first_scan_except_trace_id"], cell, index, "repeat_scan_facts_identical")
                if value.get("display_encoding") == "surface-scan-task-table-v1":
                    check(value["match_columns"] == ["object_a", "object_b", "object_a_ref", "object_b_ref", "distance_m", "distance_mm"],
                          cell, index, "compact_columns")
                    check(all(value["objects"][m[2]]["name"] == m[0] and value["objects"][m[3]]["name"] == m[1]
                              for m in value["matches"]), cell, index, "compact_endpoint_binding")
                    row["compact_columns"] = value["match_columns"]
                    row["common_metadata"] = value["match_metadata"]
                    row["match_exceptions"] = value["match_exceptions"]
            else:
                code = item["arguments"]["code"]
                parsed = ast.parse(code)
                stdout = native_stdout(value)
                native_receipt = read(tool_folder / "NATIVE_RECEIPT.json")
                check(native_receipt["response"] == value, cell, index, "native_receipt_exact_response")
                row.update({
                    "code_utf8_bytes": len(code.encode("utf8")), "code_sha256": sha(code.encode("utf8")),
                    "code_attribute_calls": sorted({node.func.attr for node in ast.walk(parsed)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}),
                    "code_function_definitions": [node.name for node in ast.walk(parsed) if isinstance(node, ast.FunctionDef)],
                    "code_evidence_lines": [{"line": n, "text": line} for n, line in enumerate(code.splitlines(), 1)
                        if any(token in line for token in ("evaluated_get", "to_mesh(", "calc_loop_triangles", "combinations(",
                           "mesh_distance(", "surface_distance(", "reverse_intersects", "EXHAUSTIVE", "same_pairs", "MATCHES_BROAD_PHASE"))],
                    "stdout": stdout, "stdout_lines": len(stdout.splitlines()),
                    "native_elapsed_ns": native_receipt.get("elapsed_ns"),
                })
            attempts.append(row)
            previous_end = ended

        first_index = FIRST_COMPLETE[cell]
        first = attempts[first_index - 1]
        first_pairs = qualifying_pairs(consumer["tool_calls"][first_index - 1]["item"])
        check(len(first_pairs) == 71, cell, "first_complete_qualifying_rows")
        public = consumer["all_public_messages"]
        check(public[-1]["text"] == consumer["final"] and public[-1]["perf_ns"] == consumer["final_received_ns"],
              cell, "last_public_message_is_sealed_final")
        check(all(not NATIVE_ROW.search(row["text"]) and len(row["text"]) < 100 for row in public[:-1]),
              cell, "earlier_public_messages_are_short_status")
        flat_rows = re.findall(r"^\|\s*Obj_\d{3}\s*\|\s*Obj_\d{3}\s*\|\s*[0-9.]+\s*\|", consumer["final"], re.M)
        if FINAL_FORMAT[cell] == "flat_71_row_table":
            check(len(flat_rows) == 71, cell, "visible_flat_71_rows")
        final_ns = consumer["final_received_ns"]
        tail = final_ns - first["event_completed_ns"]
        tail_tools = sum(row["event_tool_wall_ns"] for row in attempts[first_index:])
        comparison = None
        if cell[0] == "O":
            comparison = pair_comparison(first_pairs, qualifying_pairs(consumer["tool_calls"][-1]["item"]))
            check(not comparison["missing"] and not comparison["extra"] and not comparison["differences_over_0_0005_mm"],
                  cell, "last_native_matches_scan")
        error_positions = []
        for error in consumer["errors"]:
            moment = error["perf_ns"]
            error_positions.append({**error,
                "after_attempt": max((a["attempt"] for a in attempts if a["event_completed_ns"] <= moment), default=0),
                "during_attempt": next((a["attempt"] for a in attempts if a["event_started_ns"] <= moment <= a["event_completed_ns"]), None),
                "seconds_after_prompt": (moment - consumer["prompt_submitted_ns"]) / 1e9,
                "measured_reconnect_duration_ns": None,
                "treatment": "all original elapsed/usage retained; frozen failure preserved",
            })
        rows.append({
            "cell": cell, "group": cell[0], "anonymous_id": anonymous[cell]["anonymous_id"],
            "primary_classification": quality["primary_classification"],
            "content_classification": quality["final_content_classification"],
            "consumer_status": consumer["status"], "valid_completion": consumer["valid_completion"],
            "errors": error_positions, "final_sha256": sha(final_raw),
            "final_presentation": {
                "manual_source_classification": FINAL_FORMAT[cell],
                "flat_numeric_table_rows": len(flat_rows),
                "utf8_bytes": len(final_raw), "characters": len(consumer["final"]),
                "reported_cumulative_output_tokens": consumer["usage"]["output_tokens"],
                "reported_reasoning_output_tokens_subset": consumer["usage"]["reasoning_output_tokens"],
                "generated_native_code_utf8_bytes": sum(a.get("code_utf8_bytes", 0) for a in attempts),
                "usage_scope": "final reported cumulative turn usage; final-answer-only tokens unavailable; no extra addition of reasoning subset",
                "quality_scope": "formats accepted by original anonymous quality seal; no new grading or format requirement",
            },
            "runtime_identity": identity["runtime_identity"], "actual_exposed_tools": identity["exposed_tool_names"],
            "actual_scan_tool_description": scan_description,
            "scan_tool_description_sha256": sha(scan_description.encode("utf8")) if scan_description else None,
            "actual_actor_config_sha256": sources[source_name(folder / "ACTOR_CONFIG.json")]["sha256"],
            "config_read_schema_count": len(config.get("read_schemas", [])),
            "prompt_submitted_ns": consumer["prompt_submitted_ns"],
            "first_complete_facts_attempt": first_index,
            "first_complete_facts_cli_receipt_ns": first["event_completed_ns"],
            "first_complete_facts_owner_response_end_ns": first["owner_started_ns"] + first["owner_elapsed_ns"],
            "prompt_to_first_complete_cli_receipt_ns": first["event_completed_ns"] - consumer["prompt_submitted_ns"],
            "first_usable_public_answer_ns": final_ns,
            "last_final_public_answer_ns": final_ns,
            "first_complete_cli_receipt_to_final_ns": tail,
            "later_tool_event_wall_ns": tail_tools,
            "remaining_non_tool_tail_ns": tail - tail_tools,
            "prompt_to_last_final_ns": final_ns - consumer["prompt_submitted_ns"],
            "full_cell_wall_ns": timing["full_cell_wall_ns"],
            "tail_scope": "observed mixed elapsed interval; not counterfactual saving, pure reasoning, provider visibility, or network duration",
            "public_messages": public,
            "attempts": attempts, "last_native_scan_comparison": comparison,
            "model_input_rendered": None, "provider_requests": consumer["provider_requests"],
            "final_chain": "single_compact_scan_then_final" if cell[0] == "C" else
                "detailed_scan_repeat_then_native_recompute_then_final" if cell[0] == "O" else
                "native_capture_surface_solution_validation_then_final",
            "final_chain_inference_scope": "last available numerical outputs and final agreement; internal model dependence unknown",
            "tool_error_count": sum(row["is_error"] for row in attempts),
        })

    by_cell = {row["cell"]: row for row in rows}
    o3 = read(BATCH / "cells" / "O3" / "CONSUMER.json")
    scan_pairs = qualifying_pairs(o3["tool_calls"][0]["item"])
    wrong_pairs = qualifying_pairs(o3["tool_calls"][3]["item"])
    corrected_pairs = qualifying_pairs(o3["tool_calls"][4]["item"])
    correction = {
        "cell": "O3", "original_scan_attempt": 1, "first_native_attempt": 4, "corrected_native_attempt": 5,
        "first_native_comparison_to_scan": pair_comparison(scan_pairs, wrong_pairs),
        "corrected_native_comparison_to_scan": pair_comparison(scan_pairs, corrected_pairs),
        "algorithm_source_observation": "attempt4 surface_distance tests edges of first against triangles of second; attempt5 adds reverse_intersects(second,first) before original distance",
        "correction_event_wall_ns": by_cell["O3"]["attempts"][4]["event_tool_wall_ns"],
        "intermediate_receipt_to_corrected_receipt_ns": by_cell["O3"]["attempts"][4]["event_completed_ns"] - by_cell["O3"]["attempts"][3]["event_completed_ns"],
        "scope": "retained intermediate consumer-native solver error; final quality remains the sealed correct content",
    }
    check(len(wrong_pairs) == 70 and len(corrected_pairs) == 71, "O3", "70_to_71_retained")
    check(correction["first_native_comparison_to_scan"]["missing"] == [["Obj_010", "Obj_022"]], "O3", "specific_missing_pair")
    check([r["pair"] for r in correction["first_native_comparison_to_scan"]["differences_over_0_0005_mm"]]
          == [["Obj_006", "Obj_008"], ["Obj_009", "Obj_016"]], "O3", "two_specific_wrong_zero_pairs")
    group_summaries = {}
    for group in "NOC":
        group_rows = [row for row in rows if row["group"] == group]
        group_summaries[group] = {
            "cell_count": len(group_rows), "valid_correct": sum(row["primary_classification"] == "complete_correct" for row in group_rows),
            "content_correct": sum(row["content_classification"] == "complete_correct" for row in group_rows),
            "tool_calls": sum(len(row["attempts"]) for row in group_rows),
            "scan_calls": sum(a["tool"] == "human_eye_scene_observe" for row in group_rows for a in row["attempts"]),
            "native_calls": sum(a["tool"] == "execute_blender_code" for row in group_rows for a in row["attempts"]),
            "median_first_complete_receipt_to_final_s": statistics.median(row["first_complete_cli_receipt_to_final_ns"] / 1e9 for row in group_rows),
            "median_later_tool_s": statistics.median(row["later_tool_event_wall_ns"] / 1e9 for row in group_rows),
            "median_non_tool_tail_s": statistics.median(row["remaining_non_tool_tail_ns"] / 1e9 for row in group_rows),
            "observed_tool_text_bytes": sum(a["tool_text_utf8_bytes"] for row in group_rows for a in row["attempts"]),
            "actual_scan_description_sha256": sorted({row["scan_tool_description_sha256"] for row in group_rows
                if row["scan_tool_description_sha256"] is not None}),
        }
    check(len(group_summaries["O"]["actual_scan_description_sha256"]) == 1
          and len(group_summaries["C"]["actual_scan_description_sha256"]) == 1
          and group_summaries["O"]["actual_scan_description_sha256"] != group_summaries["C"]["actual_scan_description_sha256"],
          "actual_old_and_compact_descriptions_changed_together")
    check(group_summaries["N"]["tool_calls"] == 11 and group_summaries["O"]["tool_calls"] == 13
          and group_summaries["C"]["tool_calls"] == 3, "symmetric_27_attempts")
    output = {
        "schema": "m4_surface_scan_compact_consumption_mechanism_review_v1", "delivery_commit": DELIVERY,
        "sequence": list(SEQUENCE), "quality_seal_sha256": SEAL_SHA, "cost_plan_sha256": PLAN_SHA,
        "new_blender_model_api_runs": 0,
        "learning_context": {"context_bound": False, "host_epoch": 5, "rebind_required": True, "borrowed_handle": False},
        "source_inventory": sources, "source_file_count": len(sources),
        "assertions_passed": len(checks), "assertion_labels": checks,
        "group_summaries": group_summaries, "cells": rows, "O3_intermediate_correction": correction,
        "formal_comparison_quality_prerequisite": {"C_vs_N": False, "C_vs_O": False,
            "reason": "C 3/3, N 2/3, O 2/3 valid complete_correct; N2/O2 retained execution_failure"},
        "causal_scope": "whole compact display candidate including changed actual tool description and representation; bytes alone not isolated",
        "limits": [
            "exact owner/stdio/CLI content does not establish complete provider-rendered model input",
            "O1/O3 truncation wording is self-report; actual provider truncation, threshold and missing rows remain unknown",
            "non-tool intervals include provider/model generation, network, CLI transport and scheduling; pure reasoning unmeasured",
            "follow-up native computation does not establish model distrust or necessity",
            "N2/O2 reconnect costs retained; error attribution and isolated reconnect duration unknown",
            "final-chain attribution is bounded by retained outputs; model internal use cannot be directly observed",
            "brief explicit in all C calls; this batch does not independently test omitted response_detail consumption",
            "this is one fixed scene and task; no broader geometric coverage or product domain claim",
        ],
        "next_hypotheses": [],
    }
    (HERE / "MECHANISM.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
    report(output)
    print(json.dumps({"source_files": len(sources), "checks": len(checks), "groups": group_summaries,
        "O3_correction": correction, "timings": [{"cell": r["cell"], "first_attempt": r["first_complete_facts_attempt"],
        "prompt_to_complete_s": r["prompt_to_first_complete_cli_receipt_ns"] / 1e9,
        "complete_to_final_s": r["first_complete_cli_receipt_to_final_ns"] / 1e9,
        "later_tool_s": r["later_tool_event_wall_ns"] / 1e9,
        "non_tool_tail_s": r["remaining_non_tool_tail_ns"] / 1e9} for r in rows]}, ensure_ascii=False))


def report(output):
    rows = output["cells"]
    lines = [
        "# 同九格原件消费机制复核", "", "2026-11-13。本次离线读取固定交付原件，新增 Blender、模型及 API 调用均为零。", "",
        f"固定交付 `{DELIVERY}`，质量 seal SHA256 `{SEAL_SHA}`。私有匿名映射、九份 final 哈希、最后公开消息、owner、stdio 与 CLI 工具内容逐项绑定，共通过 {output['assertions_passed']} 项检查。",
        "", "## 结论与范围", "",
        "九份最终内容均与 seal 的 complete_correct 一致。执行口径仍为七格有效完整正确、N2 与 O2 两格 execution_failure。两格重连后有最终答案与正常退出，原始失败状态及其全部耗时仍保留。C/N、C/O 各需双方3/3有效正确的正式比较前提均未满足。以下描述使用同九原件，包含全部失败格。", "",
        "C 的三次消费均主动选择 surface_scan，并显式请求 brief。每次仅一条工具调用，得到7911字节工具文本中的71对事实后直接生成最终答案。没有 full 请求、原生目录补查或全场原生求解。", "",
        "O 为旧扫描 OPT1。三次均先取得完整详细扫描，再请求 brief，随后读原生目录并重新全场求解。O3 还发生原生中间结果70对到71对的修正。N 的三次全原生链分别使用3、4、4次调用，其中 N2/N3 在完整结果后又以同一缓存、同一求解器遍历全部对象对验证。", "",
        "本批支持整个紧凑展示候选的消费改善。真实工具描述和表示结构同时改变，无法单独分离字节长度的因果贡献。全部 C 实际调用为显式 brief，省略 response_detail 时的模型选择仍缺本批独立证据。", "",
        "## 原始时界", "",
        "首次完整事实到达以 CLI item.completed 为准。owner 结束时刻另存于 JSON，两者不合并。每格更早公开消息均为不足100字符的导语或状态，未发布任务所需完整清单，因此首次可用公开答案与最后 final 同时。", "",
        "| 格 | 执行 | 首次完整事实调用 | 提交至完整事实 s | 完整事实至 final s | 后续工具区间 s | 余下非工具区间 s |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['cell']} | {row['consumer_status']} | {row['first_complete_facts_attempt']} | "
            f"{row['prompt_to_first_complete_cli_receipt_ns']/1e9:.6f} | {row['first_complete_cli_receipt_to_final_ns']/1e9:.6f} | "
            f"{row['later_tool_event_wall_ns']/1e9:.6f} | {row['remaining_non_tool_tail_ns']/1e9:.6f} |")
    lines += ["", "上述是实际区间，不能直接当作可删除的反事实节省。非工具部分含生成、provider、网络、CLI 回传及调度，纯推理时间未测。嵌套 owner/native 区间仅用于来源定位，不与 CLI 工具区间相加。", "",
        "## 完整事实后的每次调用", ""]
    for row in rows:
        lines += [f"### {row['cell']}", "", f"匿名 ID `{row['anonymous_id']}`。首次完整事实为调用{row['first_complete_facts_attempt']}，CLI时刻 `{row['first_complete_facts_cli_receipt_ns']}`，最后公开 final 时刻 `{row['last_final_public_answer_ns']}`。", ""]
        for attempt in row["attempts"]:
            detail = f"，请求 {attempt['response_detail_requested']}" if "response_detail_requested" in attempt else ""
            lines.append(f"- 调用{attempt['attempt']} `{attempt['category']}`{detail}。{attempt['manual_source_interpretation']} 工具文本{attempt['tool_text_utf8_bytes']}字节，事件区间{attempt['event_tool_wall_ns']/1e9:.6f}秒。")
        lines.append("")
        for error in row["errors"]:
            lines += [f"原 error 时刻 `{error['perf_ns']}`，发生在已完成调用{error['after_attempt']}之后。消息 `{error['event']['message']}`。孤立重连时长未知，未扣减任何时间。", ""]
    correction = output["O3_intermediate_correction"]
    wrong = correction["first_native_comparison_to_scan"]
    lines += ["## O3 中间纠正", "",
        "原扫描调用1已返回完整71对。调用4重新采集全场并输出70对，缺少 `Obj_010–Obj_022`，又将原扫描的两个零距离算为正值，`Obj_009–Obj_016` 为0.247942039毫米，`Obj_006–Obj_008` 为1.350320876毫米。该调用的 surface_distance 对相交测试只遍历 first 的边穿过 second 的面。调用5新增 `reverse_intersects(second,first)`，保留原缓存及原距离函数，恢复71对与零距离。", "",
        f"调用5事件区间为 {correction['correction_event_wall_ns']/1e9:.6f} 秒，从错误中间回执到修正回执为 {correction['intermediate_receipt_to_corrected_receipt_ns']/1e9:.6f} 秒。两段均保留在原成本内。修正后71对与原扫描集合相同，最大距离差 {correction['corrected_native_comparison_to_scan']['max_shared_distance_difference_mm']:.12g} 毫米。", "",
        "具体代码及 stdout 绑定在 O3 的 `owner/tool_04/REQUEST.json`、`RESPONSE.json` 与 `owner/tool_05/REQUEST.json`、`RESPONSE.json`。JSON 记录两次代码SHA、相交相关行号、完整stdout及逐对差异。最终内容沿用根 seal 的正确结论。", "",
        "## 事实与补查性质", "",
        "O 的首次扫描 coverage 均为24对象、276对，164界限排除、71匹配、41测得阴性，unknown/deferred均为0，delivery明确71/71。其后 brief 与首次详细扫描除 trace_id 外完全一致。此后原生目录增加顶点/面数量，原生求解重新取得相同场景距离事实。输出中未出现为了处理未解决对象或 unknown 而追加查询的链路。", "",
        "N1 的末次调用从已有 qualifying 距离整理零值/正值并补几何和有限值检查。N2/N3 的末次调用复用已有几何与同一距离函数，取消对象级AABB筛选后遍历276对，核对71匹配集合，属于同求解器的完整性验证。它们没有形成另一套独立几何答案。", "",
        "C 的71行匹配包含名称、对象表引用、原始米距离及派生毫米距离，coverage、来源绑定、完整delivery、公共方法及异常项随结果保留。所有原工具尝试共27次，N为11、O为13、C为3，工具级拒绝为0。", "",
        "O 的最终答案前最后一条数值链来自原生重算，C 来自单次紧凑扫描，N 来自原生结果及验证。该归纳依据可见输出顺序和 final 一致性，模型内部究竟引用了哪条信息仍不可见。", "",
        "## 最终呈现与生成成本", "",
        "九份 final 的格式由模型自由选择，质量 seal 已接受相同事实的不同呈现。O和C共六份为71行独立对象对表，N1/N2为零值聚合加正值表，N3按对象A聚合。C 的累计输出token较少，其最终文本字节与O接近，N3最终文本更短。累计输出还涉及工具代码、其他生成和记录中的reasoning子项，final-only token无法从现有usage独立取出。不能把全部生成收益只归于最终格式、响应字节或避免重算中的某一项。", "",
        "| 格 | 最终格式 | final UTF8字节 | 累计output token | 其中reasoning子项 | 生成原生代码字节 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        presentation = row["final_presentation"]
        lines.append(f"| {row['cell']} | {presentation['manual_source_classification']} | {presentation['utf8_bytes']} | "
            f"{presentation['reported_cumulative_output_tokens']} | {presentation['reported_reasoning_output_tokens_subset']} | "
            f"{presentation['generated_native_code_utf8_bytes']} |")
    lines += ["", "原生代码字节只是可见生成内容的一部分。字节不换算为token，也不作为usage额外相加。输出呈现自由和模型选择属于整个候选的实际任务行为，本次没有重新评分或强制统一最终格式。", "",
        "## 可见性及诊断限制", "",
        "原生或产品响应在 owner、stdio 和 CLI 中的业务内容逐字一致。O1/O3 的状态消息提到列表截断，保留为消费者自述。真实 provider 渲染后的输入、截断位置、阈值及缺失行均为 unknown。CLI 收到完整71行只建立回执事实。", "",
        "N2/O2 都记录 response-body decoding 的重连错误，随后恢复并发布 final。全部错误、重连后的目录、重算、验证及纠正调用均计入原链。现有记录不能将错误归因于几何引擎或展示结构，也不能拆出可扣除网络延迟。", "",
        "本批没有形成必须继续更改算法或格式的新证据假设。后续决策应结合总成本账本及正式执行质量前提，当前机制分析不新增产品改动。", "",
        "## 复算", "",
        "在项目根目录以既有 Python 运行下列命令。脚本只读原件，仅在本目录写派生JSON和报告。", "",
        "```powershell", "& 'D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe' -I -B -X utf8 verification/m4_surface_scan_compact_consumption_001/cost/mechanism/analyze_mechanism.py", "```", "",
        f"本轮绑定 {output['source_file_count']} 份实际输入。`MECHANISM.json` 内有逐文件字节数与SHA256、匿名质量映射、实际工具描述、全部时刻、27次工具来源路径和O3纠正差异。未开启新消费者、未启动Blender或调用API，未改产品及原件。AL回执context_bound=false，无借用句柄。", "",
        "离线分析首版对O3缺项用了错误的预期断言，失败已保留在 `ANALYSIS_FAILURE_01.json`。对照原始逐对输出后，改正为缺Obj_010–Obj_022并完整保留两个错正值，随后复算通过。此次改正仅发生在派生分析，原正式九格保持原样。", "",
    ]
    (HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf8", newline="\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        failed = sorted(HERE.glob("ANALYSIS_FAILURE_*.json"))
        path = HERE / f"ANALYSIS_FAILURE_{len(failed) + 1:02d}.json"
        path.write_text(json.dumps({"scope": "offline analyzer failure, not a new formal cell", "traceback": traceback.format_exc()},
                                   ensure_ascii=False, indent=2) + "\n", encoding="utf8", newline="\n")
        raise
