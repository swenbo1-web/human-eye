"""Audit completed image-conditioned decisions without invoking a model or Blender."""

import argparse
import base64
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("_consume_reused_analysis", HERE.parent / "m6_refine_001/analyze_consumers.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
read, write = shared.read, shared.write
SEQUENCE = dict(v1=("native", "facts"), v2=("facts", "native"))
FIELDS = ("task_id", "decision_status", "modification_decision", "adopted_correspondence", "correct_part_visual_evidence",
    "wrist_structure_interpretation", "axis_vs_width", "local_recommendation", "operation_id", "version", "saved_blend",
    "readback", "reference_metrics", "remaining_uncertainties")
COLUMNS = ("inner", "outer", "width", "centerline")


def identity(path):
    path = Path(path)
    raw = path.read_bytes()
    return dict(path=str(path.resolve()), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def collect_receipts(session, state):
    rows = [dict(row, receipt_file=str(session / "versions" / str(row["version"]).zfill(3) / "OPERATION.json"))
        for row in state.get("operations", []) if row.get("status") == "saved_and_independently_read"]
    rows += [dict(read(path), receipt_file=str(path)) for path in sorted((session / "readbacks").glob("*/READBACK.json"))]
    for row in rows:
        row["saved_artifact_check"] = shared.artifact_identity(HERE, row.get("saved_blend"))
        row["readback_artifact_check"] = shared.artifact_identity(HERE, row.get("readback"))
    return rows


def compare_number(claim, actual):
    valid = type(claim) in (int, float) and math.isfinite(claim)
    return dict(verified=bool(valid and math.isclose(claim, actual, abs_tol=5e-6, rel_tol=1e-6)),
        claimed=claim, actual=actual, tolerance="EW-normalized absolute5e-6 or relative1e-6, allowing ordinary six-decimal reporting")


def metric_claims(supplied, quality):
    checks, unsupported = {}, []
    definitions = quality.get("contours", {}).get("definitions", {})
    if not isinstance(supplied, dict):
        return dict(verified_numeric_claims=0, numeric_claims_checked=0, all_checked_claims_consistent=None,
            both_definitions_structured=False, unsupported=["reference_metrics is narrative or absent, retained for human review"])
    columns = supplied.get("columns", supplied.get("column_order", list(COLUMNS)))
    if not isinstance(columns, list) or set(columns) != set(COLUMNS):
        columns = list(COLUMNS)
    supplied_definitions = supplied.get("definitions", supplied)
    found = []
    for label, name in (("A", "primary"), ("B", "alternative")):
        observed = next((supplied_definitions[key] for key in (label, name) if key in supplied_definitions), None)
        actual = definitions.get(name, {}).get("after")
        if not isinstance(observed, dict) or actual is None:
            continue
        found.append(label)
        for field, actual_key in (("reference", "reference"), ("model", "model"), ("residual", "signed_residual")):
            matrix = observed.get(field)
            if matrix is None:
                continue
            if isinstance(matrix, dict) and set(COLUMNS).issubset(matrix):
                if all(isinstance(matrix[key], list) and len(matrix[key]) == len(actual["stations"]) for key in COLUMNS):
                    matrix = [{key:matrix[key][index] for key in COLUMNS} for index in range(len(actual["stations"]))]
            if not isinstance(matrix, list) or len(matrix) != len(actual["stations"]):
                unsupported.append(label+"."+field+" matrix shape")
                continue
            for index, row in enumerate(matrix):
                if isinstance(row, dict):
                    cells = {key:row[key] for key in COLUMNS if key in row}
                elif isinstance(row, list) and len(row) == len(columns):
                    cells = dict(zip(columns, row))
                else:
                    unsupported.append(label+"."+field+" row"+str(index))
                    continue
                for metric, value in cells.items():
                    checks[label+"."+field+"."+str(index)+"."+metric] = compare_number(value, actual["stations"][index][actual_key][metric])
        for field, actual_key in (("MAE", "MAE"), ("mean_absolute_error", "MAE"), ("maximum_absolute_error", "maximum_absolute")):
            values = observed.get(field)
            if values is None:
                continue
            cells = values if isinstance(values, dict) else dict(zip(columns, values)) if isinstance(values, list) and len(values) == len(columns) else {}
            if not cells:
                unsupported.append(label+"."+field+" shape")
            for metric, value in cells.items():
                if metric in COLUMNS:
                    checks[label+"."+field+"."+metric] = compare_number(value, actual["errors"][metric][actual_key])
        for metric in COLUMNS:
            key = metric+"_MAE"
            if key in observed:
                checks[label+"."+key] = compare_number(observed[key], actual["errors"][metric]["MAE"])
    return dict(verified_numeric_claims=sum(row["verified"] for row in checks.values()), numeric_claims_checked=len(checks),
        all_checked_claims_consistent=all(row["verified"] for row in checks.values()) if checks else None,
        both_definitions_structured=len(found) == 2, checks=checks, unsupported=unsupported,
        scope="Recognized matrix and error-summary fields checked mechanically. Free-text observations and additional prose numbers remain for independent review.")


def final_audit(task_id, consumer, state, receipts, quality):
    final, formatting = shared.parse_final(consumer.get("final", ""))
    if final is None:
        return dict(parsed=False, format=formatting, all_artifact_references_verified=False, metrics={}, final=None)
    matching = [row for row in receipts if row.get("version") == state.get("version") and row.get("independently_reopened")
        and row["saved_artifact_check"]["verified"] and row["readback_artifact_check"]["verified"]]
    saved = [row["saved_blend"] for row in matching]
    readbacks, labels = [], []
    for row in matching:
        readbacks += [row["readback"], dict(path=row["receipt_file"])]
        if row.get("quality_record"):
            readbacks.append(dict(path=row["quality_record"]))
        if row.get("reader_job"):
            labels.append(row["reader_job"])
    checks = dict(task_id=final.get("task_id") == task_id,
        version=type(final.get("version")) is int and final["version"] == state.get("version"),
        saved_blend=shared.reference_matches(HERE, final.get("saved_blend"), saved),
        readback=shared.reference_matches(HERE, final.get("readback"), readbacks, labels))
    decision = final.get("modification_decision")
    saved_operations = [row for row in state.get("operations", []) if row.get("status") == "saved_and_independently_read"]
    if decision == "no_edit":
        checks["operation_decision"] = final.get("operation_id") is None and not saved_operations and quality.get("displacement", {}).get("changed_vertices") == 0
    else:
        checks["operation_decision"] = decision == "edit" and any(row["operation_id"] == final.get("operation_id") for row in saved_operations)
    metrics = metric_claims(final.get("reference_metrics"), quality)
    return dict(parsed=True, format=formatting, missing_fields=[name for name in FIELDS if name not in final], field_checks=checks,
        all_artifact_references_verified=bool(checks["task_id"] and checks["version"] and checks["saved_blend"]["verified"] and checks["readback"]["verified"]),
        decision_matches_actual_mutation=checks["operation_decision"], metrics=metrics, final=final,
        structured_analysis_fields_present={key:bool(final.get(key)) for key in ("correct_part_visual_evidence", "wrist_structure_interpretation", "axis_vs_width", "local_recommendation", "remaining_uncertainties")},
        correctness_scope="Text presence and numerical consistency are measured here. Image interpretation and artistic judgement require independent review, with no user-labelled artistic ground truth.")


def image_audit(folder, events):
    case = HERE / "private/consumer_cases/forearm"
    expected = read(case / "task.json")["images"]
    result = dict(tool_calls=0, exact_server_image_blocks=0, PNG_bytes=0, base64_bytes=0, source_blocks_verified=True,
        CLI_image_tool_events=0, CLI_truncated_result_events=0, provider_internal_image_encoding=None)
    calls = []
    for directory in sorted((folder / "bridge").glob("tool_*")):
        request = read(directory / "REQUEST.json", {})
        if request.get("name") != "images":
            continue
        response = read(directory / "RESPONSE.json", {})
        blocks = [block for block in response.get("content", []) if block.get("type") == "image"]
        verified = len(blocks) == len(expected)
        encoded_bytes = 0
        for block, metadata in zip(blocks, expected):
            raw = base64.b64decode(block["data"], validate=True)
            source = Path(metadata["path"])
            source = source if source.is_absolute() else case / source
            verified = verified and raw == source.read_bytes() and hashlib.sha256(raw).hexdigest() == metadata["sha256"]
            encoded_bytes += len(block["data"])
        cost = read(directory / "COST.json", {})
        calls.append(dict(index=cost.get("index"), image_blocks=len(blocks), exact_original_PNG_bytes=verified,
            PNG_bytes=sum(row["bytes"] for row in expected), base64_bytes=encoded_bytes,
            stdio_response_UTF8_bytes=cost.get("stdio_response_UTF8_bytes"), wall_s=cost.get("wall_s"), response=identity(directory / "RESPONSE.json")))
        result["tool_calls"] += 1
        result["exact_server_image_blocks"] += len(blocks)
        result["PNG_bytes"] += sum(row["bytes"] for row in expected)
        result["base64_bytes"] += encoded_bytes
        result["source_blocks_verified"] = bool(result["source_blocks_verified"] and verified)
    for event in events:
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "mcp_tool_call" and item.get("tool") == "images":
            result["CLI_image_tool_events"] += 1
            if "chars truncated" in json.dumps(item.get("result", {}), ensure_ascii=False):
                result["CLI_truncated_result_events"] += 1
    result.update(calls=calls, evidence_verified=bool(result["tool_calls"] and result["source_blocks_verified"] and result["CLI_image_tool_events"] >= result["tool_calls"]),
        interpretation="Exact9 native MCP image blocks verified at the bridge, with matching completed CLI images calls. CLI JSON events can middle-truncate the serialized image body at1MiB. Provider-internal image preprocessing is unmeasured.")
    return result


def contour_summary(quality):
    contours = quality.get("contours", {})
    return {label:dict(errors=data["after"]["errors"], stations=data["after"]["stations"], improvements=data["improvements"],
        improvement_established=data["improvement_established"]) for label, data in contours.get("definitions", {}).items()}


def analyze_session(stage, route):
    task_id = "forearm"
    folder = HERE / "private/consumers" / stage / task_id / route
    consumer = read(folder / "CONSUMER.json", {})
    row = dict(stage=stage, task_id=task_id, route=route, transport_status=consumer.get("status", "not_started"))
    if row["transport_status"] in ("not_started", "running"):
        return row, dict(summary=row)
    session = HERE / "private/sessions" / (stage+"_"+task_id+"_"+route)
    state = read(session / "session.json")
    receipts = collect_receipts(session, state)
    latest = next((record for record in reversed(receipts) if record.get("version") == state["version"] and record.get("independently_reopened")), {})
    quality = read(Path(latest["quality_record"]), {}) if latest.get("quality_record") else latest.get("quality", {})
    tools = shared.tool_metrics(folder)
    for tool in tools["calls"]:
        cost = read(folder / "bridge" / ("tool_"+str(tool["index"]).zfill(2)) / "COST.json", {})
        tool.update(image_blocks=cost.get("public_image_count", 0), image_PNG_bytes=cost.get("public_image_bytes", 0),
            image_base64_bytes=cost.get("image_base64_bytes", 0), stdio_response_UTF8_bytes=cost.get("stdio_response_UTF8_bytes"))
    projection_calls = [tool for tool in tools["calls"] if tool["name"] == "project_sections"]
    events = []
    for raw in (folder / "events.jsonl").read_text(encoding="utf8").splitlines():
        events.append(json.loads(raw)["event"])
    images = image_audit(folder, events)
    final = final_audit(task_id, consumer, state, receipts, quality)
    API = shared.api_metrics(HERE, session)
    artifact_ok = bool(latest and latest["saved_artifact_check"]["verified"])
    readback_ok = bool(latest and latest["readback_artifact_check"]["verified"] and latest.get("independently_reopened"))
    bridge = read(folder / "bridge/BRIDGE_RESULT.json", {})
    row.update(wall_s=consumer.get("wall_s"), usage=consumer.get("usage"), prompt_to_final_s=consumer.get("prompt_to_final_s"),
        modification_decision=final.get("final", {}).get("modification_decision") if final.get("final") else None,
        adopted_correspondence=final.get("final", {}).get("adopted_correspondence") if final.get("final") else None,
        actual_saved_copy_verified=artifact_ok, actual_independent_readback=readback_ok, current_version=state["version"],
        saved_edit_operations=sum(record.get("status") == "saved_and_independently_read" for record in state.get("operations", [])),
        technical_status=quality.get("status"), technical_failed=[name for name,value in quality.get("checks", {}).items() if value is False],
        changed_vertices=quality.get("displacement", {}).get("changed_vertices"), contours=contour_summary(quality),
        geometry_improvement_established=quality.get("contours", {}).get("geometry_improvement_established"), artistic_acceptance=None,
        images={key:value for key,value in images.items() if key != "calls"},
        final_references_verified=final.get("all_artifact_references_verified"), decision_matches_actual_mutation=final.get("decision_matches_actual_mutation"),
        numeric_claims_checked=final.get("metrics", {}).get("numeric_claims_checked", 0), numeric_claims_verified=final.get("metrics", {}).get("verified_numeric_claims", 0),
        structured_analysis_fields=final.get("structured_analysis_fields_present"),
        tools=len(tools["calls"]), tool_names=tools["counts"], tool_wall_s=tools["tool_wall_s"],
        public_text_UTF8_bytes=tools["public_response_UTF8_bytes"], facts_wall_s=tools["facts_wall_s"]+sum(tool["wall_s"] or 0 for tool in projection_calls),
        facts_text_UTF8_bytes=tools["facts_public_response_UTF8_bytes"]+sum(tool["public_response_UTF8_bytes"] for tool in projection_calls),
        python=tools["python"], failed_tools=tools["failed_calls"], truncated_tools=tools["truncated_calls"],
        potential_redundancy=tools["potential_redundancy"], API={key:value for key,value in API.items() if key != "jobs"},
        cleanup=dict(process=consumer.get("process_cleanup"), readers_stopped=consumer.get("readers_stopped"),
            safe_to_continue=consumer.get("safe_to_continue"), bridge_closed=bridge.get("closed"), bridge_PID=bridge.get("process_id"), bridge_process_metrics=bridge.get("process_metrics")),
        provider_fees=consumer.get("fees"), immutable_inputs=consumer.get("source_unchanged") and consumer.get("images_unchanged"))
    return row, dict(summary=row, final=final, tool_details=tools, image_details=images, API=API, receipts=receipts,
        public_event_summary=shared.public_event_summary(folder / "events.jsonl"), consumer_errors=consumer.get("errors"), provider_retry_observations=consumer.get("provider_retry_observations"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2", "all"), default="v1")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    if args.stage == "v1" and (HERE / "OPTIMIZATION_BINDING.json").exists() and (HERE / "CONSUMER_STATS_v1.json").exists():
        raise RuntimeError("bound_v1_analysis_is_immutable_use_stage_all")
    started = time.perf_counter()
    rows, details = [], []
    for stage in SEQUENCE if args.stage == "all" else (args.stage,):
        for route in SEQUENCE[stage]:
            row, detail = analyze_session(stage, route)
            rows.append(row)
            details.append(detail)
    incomplete = [dict(stage=row["stage"], route=row["route"], status=row["transport_status"]) for row in rows if row["transport_status"] in ("running", "not_started")]
    if incomplete and not args.allow_partial:
        raise RuntimeError("all_selected_consumers_must_be_terminal_"+json.dumps(incomplete))
    totals = dict(sessions=len(rows), terminal_sessions=len(rows)-len(incomplete),
        modification_decisions=dict(Counter(row.get("modification_decision", row["transport_status"]) for row in rows)),
        image_delivery_verified=sum(row.get("images", {}).get("evidence_verified", False) for row in rows),
        server_image_blocks=sum(row.get("images", {}).get("exact_server_image_blocks", 0) for row in rows),
        raw_PNG_bytes=sum(row.get("images", {}).get("PNG_bytes", 0) for row in rows),
        independent_readbacks=sum(row.get("actual_independent_readback", False) for row in rows),
        verified_final_references=sum(row.get("final_references_verified", False) for row in rows),
        numeric_claims_checked=sum(row.get("numeric_claims_checked", 0) for row in rows), numeric_claims_verified=sum(row.get("numeric_claims_verified", 0) for row in rows),
        wall_s=sum(row.get("wall_s") or 0 for row in rows), tool_calls=sum(row.get("tools", 0) for row in rows))
    report = dict(stage=args.stage, totals=totals, sessions=rows, incomplete=incomplete,
        artistic_ground_truth=None, interpretation="Model decisions and their agreement are observations, not artistic correctness. Technical saved-file QA and dual reference measurements are separate. Provider-internal image preprocessing and fees are unmeasured.",
        detail_path="private/analysis/"+args.stage+"/DETAIL.json", analyzer_wall_s=time.perf_counter()-started)
    destination = HERE / ("CONSUMER_STATS_"+args.stage+".json")
    if destination.exists():
        history = HERE / "private/analysis" / args.stage / "history"
        history.mkdir(parents=True, exist_ok=True)
        serial = len(list(history.glob("*.json")))+1
        (history / (str(serial).zfill(3)+"_summary.json")).write_bytes(destination.read_bytes())
        old_detail = HERE / "private/analysis" / args.stage / "DETAIL.json"
        if old_detail.exists():
            (history / (str(serial).zfill(3)+"_detail.json")).write_bytes(old_detail.read_bytes())
        old_table = HERE / ("CONSUMER_STATS_"+args.stage+".md")
        if old_table.exists():
            (history / (str(serial).zfill(3)+"_table.md")).write_bytes(old_table.read_bytes())
    write(HERE / report["detail_path"], dict(sessions=details))
    write(destination, report)
    lines=["| Stage | Route | Decision | Image blocks | Readback | Technical | Final refs | Wall s | Tools |", "|---|---|---|---:|---|---|---|---:|---:|"]
    for row in rows:
        lines.append("| "+" | ".join(str(value) for value in (row["stage"],row["route"],row.get("modification_decision",row["transport_status"]),
            row.get("images",{}).get("exact_server_image_blocks",0),row.get("actual_independent_readback"),row.get("technical_status"),
            row.get("final_references_verified"),round(row.get("wall_s") or 0,3),row.get("tools",0)))+" |")
    (HERE / ("CONSUMER_STATS_"+args.stage+".md")).write_text("\n".join(lines)+"\n",encoding="utf8",newline="\n")
    print(json.dumps(totals,ensure_ascii=False))


if __name__ == "__main__":
    main()
