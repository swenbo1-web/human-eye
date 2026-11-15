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
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from consumer_bridge import verify_cli_image_event, verify_image_response
from consumer_runner import fixed_sequence
from image_inputs import image_inputs
spec = importlib.util.spec_from_file_location("_consume_reused_analysis", HERE.parent / "m6_refine_001/analyze_consumers.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
read, write = shared.read, shared.write
FIELDS = ("task_id", "decision_status", "modification_decision", "visual_evidence", "active_region",
    "operation_id", "version", "saved_blend", "readback", "target_result", "remaining_issues")


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
    return dict(parsed=True, format=formatting, missing_fields=[name for name in FIELDS if name not in final], field_checks=checks,
        all_artifact_references_verified=bool(checks["task_id"] and checks["version"] and checks["saved_blend"]["verified"] and checks["readback"]["verified"]),
        decision_matches_actual_mutation=checks["operation_decision"], final=final,
        structured_analysis_fields_present={key:bool(final.get(key)) for key in ("visual_evidence", "active_region", "target_result", "remaining_issues")},
        correctness_scope="Text presence and numerical consistency are measured here. Image interpretation and artistic judgement require independent review, with no user-labelled artistic ground truth.")


def image_audit(folder, events):
    case = HERE / "private/consumer_cases/repair"
    task = read(case / "task.json")
    initial_rows = image_inputs(case)
    stage, route = folder.parents[1].name, folder.name
    session = HERE / "private/sessions" / (stage + "_repair_" + route)
    state = read(session / "session.json")
    calls = []
    for directory in sorted((folder / "bridge").glob("tool_*")):
        request = read(directory / "REQUEST.json", {})
        if request.get("name") != "images":
            continue
        try:
            calls.append(verify_image_response(directory, task, initial_rows, session))
        except (ValueError, KeyError, OSError, StopIteration) as error:
            cost = read(directory / "COST.json", {})
            calls.append(dict(index=cost.get("index"), image_blocks=cost.get("public_image_count", 0),
                exact_source_PNG_bytes=False, error=str(error), PNG_bytes=cost.get("public_image_bytes", 0), base64_bytes=0))
    completed = [event.get("item", {}) for event in events if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "mcp_tool_call" and event.get("item", {}).get("tool") == "images"]
    for position, call in enumerate(calls):
        try:
            directory = folder / "bridge" / ("tool_" + str(call["index"]).zfill(2))
            call["CLI_event"] = verify_cli_image_event(completed[position], directory)
        except (ValueError, IndexError, KeyError, OSError) as error:
            call["CLI_event"] = dict(metadata_SHA256_verified=False, error=str(error))
    initial = [row for row in calls if row.get("delivery_kind") == "frozen_initial"]
    previews = [row for row in calls if row.get("delivery_kind") == "saved_version_preview"]
    verified = bool(calls and initial and calls[0].get("delivery_kind") == "frozen_initial"
        and all(row["exact_source_PNG_bytes"] and row["CLI_event"]["metadata_SHA256_verified"] for row in calls) and len(completed) >= len(calls))
    return dict(tool_calls=len(calls), exact_server_image_blocks=sum(row["image_blocks"] for row in calls),
        PNG_bytes=sum(row["PNG_bytes"] for row in calls), base64_bytes=sum(row["base64_bytes"] for row in calls),
        source_blocks_verified=all(row["exact_source_PNG_bytes"] for row in calls), CLI_image_tool_events=len(completed),
        CLI_truncated_result_events=sum("chars truncated" in json.dumps(item.get("result", {})) for item in completed),
        provider_internal_image_encoding=None, calls=calls, evidence_verified=verified,
        initial_image_deliveries=len(initial), preview_image_deliveries=len(previews),
        preview_render_calls=sum(bool(row.get("preview", {}).get("render_invoked")) for row in previews),
        preview_cache_hits=sum(bool(row.get("preview", {}).get("cache_hit")) for row in previews),
        final_saved_version_visualized=any(row.get("version") == state["version"] and
            row.get("saved_blend_sha256") == state.get("current_blend_identity", {}).get("sha256") for row in previews),
        interpretation="Frozen input PNGs and saved-version previews are verified against complete Bridge image bytes and completed CLI image events. Preview camera, saved SHA and actual render receipts are validated. Provider-internal image preprocessing is unmeasured.")


def file_access_audit(folder):
    rows = []
    for directory in sorted((folder / "bridge").glob("tool_*")):
        execution = directory / "python"
        audit_path = execution / "FILE_ACCESS.json"
        if not audit_path.exists():
            continue
        audit = read(audit_path)
        rows.append(dict(tool_directory=directory.name, code=identity(execution / "CODE.py"),
            audit=identity(audit_path), policy=audit["policy"], events=audit["events"]))
    return dict(executions_with_access_audit=len(rows),
        allowed_file_accesses=sum(event.get("allowed") is True for row in rows for event in row["events"]),
        denied_accesses=sum(event.get("allowed") is False for row in rows for event in row["events"]),
        OS_sandbox_certification=False, details=rows)


def analyze_session(stage, route):
    task_id = "repair"
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
    events = []
    for raw in (folder / "events.jsonl").read_text(encoding="utf8").splitlines():
        events.append(json.loads(raw)["event"])
    images = image_audit(folder, events)
    access = file_access_audit(folder)
    final = final_audit(task_id, consumer, state, receipts, quality)
    API = shared.api_metrics(HERE, session)
    artifact_ok = bool(latest and latest["saved_artifact_check"]["verified"])
    readback_ok = bool(latest and latest["readback_artifact_check"]["verified"] and latest.get("independently_reopened"))
    bridge = read(folder / "bridge/BRIDGE_RESULT.json", {})
    row.update(wall_s=consumer.get("wall_s"), usage=consumer.get("usage"), prompt_to_final_s=consumer.get("prompt_to_final_s"),
        modification_decision=final.get("final", {}).get("modification_decision") if final.get("final") else None,
        actual_saved_copy_verified=artifact_ok, actual_independent_readback=readback_ok, current_version=state["version"],
        saved_edit_operations=sum(record.get("status") == "saved_and_independently_read" for record in state.get("operations", [])),
        technical_status=quality.get("status"), technical_failed=[name for name,value in quality.get("checks", {}).items() if value is False],
        changed_vertices=quality.get("displacement", {}).get("changed_vertices"),
        current_geometry_observations=quality.get("geometry", {}), repair_quality="requires_independent_saved_file_evaluation", artistic_acceptance=None,
        images={key:value for key,value in images.items() if key != "calls"},
        final_references_verified=final.get("all_artifact_references_verified"), decision_matches_actual_mutation=final.get("decision_matches_actual_mutation"),
        structured_analysis_fields=final.get("structured_analysis_fields_present"),
        tools=len(tools["calls"]), tool_names=tools["counts"], tool_wall_s=tools["tool_wall_s"],
        public_text_UTF8_bytes=tools["public_response_UTF8_bytes"], facts_wall_s=tools["facts_wall_s"],
        facts_text_UTF8_bytes=tools["facts_public_response_UTF8_bytes"],
        python=tools["python"], failed_tools=tools["failed_calls"], truncated_tools=tools["truncated_calls"],
        file_access={key:value for key,value in access.items() if key != "details"},
        potential_redundancy=tools["potential_redundancy"], API={key:value for key,value in API.items() if key != "jobs"},
        cleanup=dict(process=consumer.get("process_cleanup"), readers_stopped=consumer.get("readers_stopped"),
            safe_to_continue=consumer.get("safe_to_continue"), bridge_closed=bridge.get("closed"), bridge_PID=bridge.get("process_id"), bridge_process_metrics=bridge.get("process_metrics")),
        provider_fees=consumer.get("fees"), immutable_inputs=consumer.get("source_unchanged") and consumer.get("images_unchanged"))
    return row, dict(summary=row, final=final, tool_details=tools, image_details=images, file_access=access, API=API, receipts=receipts,
        public_event_summary=shared.public_event_summary(folder / "events.jsonl"), consumer_errors=consumer.get("errors"), provider_retry_observations=consumer.get("provider_retry_observations"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("run",), default="run")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    started = time.perf_counter()
    rows, details = [], []
    for item in fixed_sequence(read(HERE / "PLAN.json")):
        row, detail = analyze_session(item["stage"], item["route"])
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
        wall_s=sum(row.get("wall_s") or 0 for row in rows), tool_calls=sum(row.get("tools", 0) for row in rows))
    report = dict(stage=args.stage, totals=totals, sessions=rows, incomplete=incomplete,
        artistic_ground_truth=None, interpretation="Actual saved-file receipts, image delivery and consumer costs are audited here. Repair quality is determined by the independent saved-file evaluator. Provider-internal image preprocessing and fees are unmeasured.",
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
