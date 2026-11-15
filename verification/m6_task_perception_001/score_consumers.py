"""Author-side checks of the fixed 24 consumer results, with raw evidence retained."""

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
from interfaces import TaskPerception


def read(path):
    return json.loads(Path(path).read_bytes())


def identity(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=path.relative_to(HERE).as_posix(), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def vector3(value):
    return isinstance(value, list) and len(value) == 3 and all(finite_number(item) for item in value)


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_JSON_key_" + key)
        result[key] = value
    return result


def reject_nonfinite_constant(value):
    raise ValueError("nonfinite_JSON_constant_" + value)


def parse_answer(text):
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    method = "single_complete_JSON_code_fence" if fence else "complete_JSON_text"
    candidate = fence.group(1) if fence else stripped
    try:
        answer = json.loads(candidate, object_pairs_hook=unique_json_object, parse_constant=reject_nonfinite_constant)
        if not isinstance(answer, dict):
            raise ValueError("answer_must_be_JSON_object")
        return answer, dict(status="parsed", method=method, error=None)
    except (ValueError, TypeError) as error:
        return None, dict(status="failed", method=method, error=dict(type=type(error).__name__, message=str(error)))


def schema_check(answer, required):
    if answer is None:
        return dict(complete=False, missing_fields=list(required), type_errors=["unparsed_answer"])
    missing = [key for key in required if key not in answer]
    errors = []
    for key in ("task_id", "entrypoint"):
        if key in answer and not isinstance(answer[key], str):
            errors.append(key)
    if "selected_source_ids" in answer:
        ids = answer["selected_source_ids"]
        if not isinstance(ids, list) or any(type(value) is not int for value in ids):
            errors.append("selected_source_ids")
    if "region_reference" in answer and answer["region_reference"] is not None and not isinstance(answer["region_reference"], str):
        errors.append("region_reference")
    if "centroid_native" in answer and not vector3(answer["centroid_native"]):
        errors.append("centroid_native")
    if "lumped_area_native" in answer and not finite_number(answer["lumped_area_native"]):
        errors.append("lumped_area_native")
    if "bbox_native" in answer:
        bbox = answer["bbox_native"]
        if not isinstance(bbox, dict) or not vector3(bbox.get("min")) or not vector3(bbox.get("max")):
            errors.append("bbox_native")
    for key in ("anomaly_asserted", "protection_respected", "editing_executed"):
        if key in answer and type(answer[key]) is not bool:
            errors.append(key)
    for key in ("evidence", "missing_information", "operation_plan"):
        if key in answer and not isinstance(answer[key], list):
            errors.append(key)
    return dict(complete=not missing and not errors, missing_fields=missing, type_errors=errors,
                extra_fields=sorted(set(answer) - set(required)))


def current_task(task, truth):
    if truth["geometry_alias"] != task["geometry_alias"] or truth["entrypoint"] != task["entrypoint"]:
        raise ValueError("scoring_truth_task_identity_mismatch_" + task["task_id"])
    directory = HERE / "private/consumer_cases" / task["task_id"]
    with np.load(directory / "input.npz", allow_pickle=False) as data:
        vertices, faces = data["vertices"], data["faces"].astype(np.int64)
        F = data["F_ids"].astype(np.int64)
        target, protected = data["target_ids"].astype(np.int64), data["protected_ids"].astype(np.int64)
    with np.load(HERE / truth["truth_file"], allow_pickle=False) as labels:
        mask = np.asarray(labels["maskF"] if "maskF" in labels else labels["mask"], dtype=bool)
        if not np.array_equal(labels["F_source_ids"], F) or mask.shape != F.shape:
            raise ValueError("scoring_truth_current_F_mapping_mismatch_" + task["task_id"])
    triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    area = np.zeros(len(vertices), dtype=np.float64)
    normal_sum = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(area, faces[:, corner], np.linalg.norm(cross, axis=1) / 6)
        np.add.at(normal_sum, faces[:, corner], cross)
    lengths = np.linalg.norm(normal_sum, axis=1)
    normals = np.divide(normal_sum, lengths[:, None], out=np.zeros_like(normal_sum), where=lengths[:, None] > 0)
    return dict(vertices=vertices, faces=faces, F=F, target=target, protected=protected, area=area, normals=normals,
                mask=mask, diagonal=float(np.linalg.norm(np.ptp(vertices, axis=0))),
                input_identity=identity(directory / "input.npz"), task_identity=identity(directory / "task.json"), truth_identity=identity(HERE / truth["truth_file"]))


def geometry_check(answer, task, current):
    raw_ids = answer.get("selected_source_ids") if answer else None
    integer_ids = isinstance(raw_ids, list) and all(type(value) is int for value in raw_ids)
    in_range = integer_ids and all(0 <= value < len(current["vertices"]) for value in raw_ids)
    ids = np.asarray(sorted(set(raw_ids)), dtype=np.int64) if in_range else np.empty(0, dtype=np.int64)
    unique = integer_ids and len(ids) == len(raw_ids)
    nonempty = bool(in_range and len(ids))
    area = current["area"]
    F_area = float(area[current["F"]].sum())
    exact = dict(selected_points=len(ids) if in_range else None, scope_lumped_area_native=F_area,
                 selected_lumped_area_native=float(area[ids].sum()) if in_range else None,
                 centroid_native=None, bbox_native=None, mean_normal=None)
    coordinate_tolerance = 1e-6 * current["diagonal"]
    area_tolerance = 1e-6 * max(exact["selected_lumped_area_native"] or 0., np.finfo(float).tiny)
    defined = False
    if nonempty and exact["selected_lumped_area_native"] > 0:
        points = current["vertices"][ids]
        centroid = np.sum(points * area[ids, None], axis=0) / exact["selected_lumped_area_native"]
        weighted_normal = np.sum(current["normals"][ids] * area[ids, None], axis=0)
        normal_length = float(np.linalg.norm(weighted_normal))
        exact.update(centroid_native=centroid.tolist(), bbox_native=dict(min=points.min(axis=0).tolist(), max=points.max(axis=0).tolist()),
                     mean_normal=(weighted_normal / normal_length).tolist() if normal_length else None)
        defined = True
    reported_centroid = answer.get("centroid_native") if answer else None
    reported_area = answer.get("lumped_area_native") if answer else None
    reported_bbox = answer.get("bbox_native") if answer else None
    centroid_error = float(np.max(np.abs(np.asarray(reported_centroid) - exact["centroid_native"]))) if defined and vector3(reported_centroid) else None
    bbox_error = None
    if defined and isinstance(reported_bbox, dict) and vector3(reported_bbox.get("min")) and vector3(reported_bbox.get("max")):
        bbox_error = max(float(np.max(np.abs(np.asarray(reported_bbox[key]) - exact["bbox_native"][key]))) for key in ("min", "max"))
    area_error = abs(reported_area - exact["selected_lumped_area_native"]) if finite_number(reported_area) and in_range else None
    measurements = dict(defined_for_nonempty_selection=defined, reported_centroid_defined=vector3(reported_centroid),
        reported_area_defined=finite_number(reported_area), reported_bbox_defined=isinstance(reported_bbox, dict)
        and vector3(reported_bbox.get("min")) and vector3(reported_bbox.get("max")),
        centroid_max_abs_error_native=centroid_error, bbox_max_abs_error_native=bbox_error, area_abs_error_native_squared=area_error,
        coordinate_tolerance_native=coordinate_tolerance, area_relative_tolerance=1e-6, area_abs_tolerance_native_squared=area_tolerance,
        centroid_correct=centroid_error is not None and centroid_error <= coordinate_tolerance,
        bbox_correct=bbox_error is not None and bbox_error <= coordinate_tolerance,
        area_correct=area_error is not None and area_error <= area_tolerance,
        exact_current_values=exact)
    measurements["all_nonempty_geometry_correct"] = defined and all(measurements[key] for key in ("centroid_correct", "bbox_correct", "area_correct"))
    inside_F = bool(in_range and np.isin(ids, current["F"]).all())
    exact_target = bool(in_range and np.array_equal(ids, np.sort(current["target"])))
    budget_tolerance = 1e-12 * max(F_area, np.finfo(float).tiny)
    selected_area = exact["selected_lumped_area_native"]
    under_budget = bool(in_range and selected_area <= .25 * F_area + budget_tolerance)
    role = dict(integer_source_IDs=integer_ids, unique_source_IDs=unique, source_IDs_in_range=bool(in_range), empty_selection=bool(in_range and not len(ids)),
                selected_subset_F=inside_F, selected_area_fraction_of_F=selected_area/F_area if in_range and F_area else None,
                inspect_area_budget_satisfied=under_budget, focus_exact_explicit_target=exact_target,
                requested_target_points=len(current["target"]), requested_protected_points=len(current["protected"]),
                selected_protected_points=int(np.isin(ids, current["protected"]).sum()) if in_range else None,
                target_and_protection_overlap_points=int(np.intersect1d(current["target"], current["protected"]).size))
    role["entrypoint_location_correct"] = bool(integer_ids and unique and in_range and (inside_F and under_budget if task["entrypoint"] == "inspect" else exact_target))
    return ids, role, measurements


def reference_check(answer, task, route, ids, location, current, resolver):
    reference = answer.get("region_reference") if answer else None
    result = dict(provided=reference is not None, reference=reference, status="absent", exact_selected_ID_set=False,
                  current_observation_matches=False, current_geometry_matches=False, focus_target_role_matches=None, error=None)
    if reference is None:
        result["status"] = "native_explicit_source_ID_form" if route == "native" and len(ids) and location["source_IDs_in_range"] else "absent"
    elif isinstance(reference, str) and reference:
        try:
            resolved = resolver.resolve(reference, include_geometry=True)
            positions = np.asarray(resolved["current_positions_native"], dtype=np.float64)
            geometry_matches = (positions.shape == current["vertices"][ids].shape
                and positions.tobytes() == current["vertices"][ids].tobytes()
                and resolved["identity"]["topology_sha256"] == hashlib.sha256(np.ascontiguousarray(current["faces"]).tobytes()).hexdigest()
                and resolved["identity"]["F_source_ids_sha256"] == hashlib.sha256(np.ascontiguousarray(current["F"], dtype="<i8").tobytes()).hexdigest())
            result.update(status="resolved", exact_selected_ID_set=np.array_equal(np.asarray(resolved["source_ids"], dtype=np.int64), ids),
                          current_observation_matches=resolved["identity"]["observation_alias"] == task["geometry_alias"],
                          current_geometry_matches=geometry_matches,
                          focus_target_role_matches=resolved["identity"]["kind"] == "user_target" if task["entrypoint"] == "focus" else None,
                          identity=resolved["identity"], resolution_cost=resolved["cost"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            result.update(status="failed", error=dict(type=type(error).__name__, message=str(error)))
    else:
        result["status"] = "invalid_reference_type_or_empty_string"
    result["criterion_satisfied"] = bool(result["status"] == "native_explicit_source_ID_form" or (
        result["status"] == "resolved" and result["exact_selected_ID_set"] and result["current_observation_matches"]
        and result["current_geometry_matches"]
        and (task["entrypoint"] != "focus" or result["focus_target_role_matches"])))
    return result


def consumer_costs(folder, receipt):
    bridge_path = folder / "bridge/BRIDGE_RESULT.json"
    bridge = read(bridge_path) if bridge_path.exists() else receipt.get("bridge", {})
    tools = []
    for tool_path in sorted((folder / "bridge").glob("tool_*/COST.json")):
        cost = read(tool_path)
        item = dict(index=cost.get("index"), name=cost.get("name"), status=cost.get("status"), wall_s=cost.get("wall_s"),
                    public_text_UTF8_bytes=cost.get("public_text_UTF8_bytes"), truncated=cost.get("truncated"), evidence=identity(tool_path))
        complete = tool_path.parent / "COMPLETE_RESULT.json"
        if complete.exists():
            result = read(complete)
            if isinstance(result, dict) and isinstance(result.get("cost"), dict):
                item["interface_timing_tree_included_in_tool_wall"] = result["cost"]
        execution_path = tool_path.parent / "python/EXECUTION.json"
        if execution_path.exists():
            execution = read(execution_path)
            worker = execution.get("worker") or {}
            item["python_execution"] = dict(wall_s=execution.get("wall_s"), status=execution.get("status"), returncode=execution.get("returncode"),
                outer_error=execution.get("error"), worker_error=worker.get("error"), worker_wall_s_before_write=worker.get("worker_wall_s_before_write"),
                worker_process=worker.get("process"), evidence=identity(execution_path))
        tools.append(item)
    python_rows = [row["python_execution"] for row in tools if "python_execution" in row]
    measured_tool_wall = [row["wall_s"] for row in tools if finite_number(row["wall_s"])]
    measured_python_wall = [row["wall_s"] for row in python_rows if finite_number(row["wall_s"])]
    measured_python_CPU = [(row.get("worker_process") or {}).get("CPU_s") for row in python_rows]
    measured_python_CPU = [value for value in measured_python_CPU if finite_number(value)]
    return dict(consumer_wall_s=receipt.get("wall_s"), prompt_to_final_s=receipt.get("prompt_to_final_s"),
        usage=receipt.get("usage"), usage_rows=receipt.get("usage_rows"), fees=receipt.get("fees"), fees_measurement="unknown" if receipt.get("fees") is None else "reported",
        provider_requests=receipt.get("provider_requests"), provider_retry_observations=receipt.get("provider_retry_observations"),
        recorded_CLI_tool_rounds=receipt.get("tool_count"), bridge_tool_rounds=len(bridge.get("calls", [])) if bridge else None,
        tool_round_budget_respected=receipt.get("tool_round_budget_respected"), bridge_session_wall_s=bridge.get("wall_s"), tool_costs=tools,
        measured_bridge_tool_wall_sum_s=sum(measured_tool_wall), measured_bridge_tool_wall_rows=len(measured_tool_wall),
        measured_python_subprocess_wall_sum_s=sum(measured_python_wall), measured_python_subprocess_wall_rows=len(measured_python_wall),
        measured_fresh_python_process_CPU_sum_s=sum(measured_python_CPU), measured_fresh_python_process_CPU_rows=len(measured_python_CPU),
        input_prompt_UTF8_bytes=receipt.get("input_prompt_UTF8_bytes"), output_text_UTF8_bytes=receipt.get("output_text_UTF8_bytes"),
        public_image_count=receipt.get("public_image_count"), public_image_bytes=receipt.get("public_image_bytes"),
        accounting="consumer_wall is the end-to-end observed session. Bridge wall, tool wall, Python wall and interface timing trees overlap and are diagnostic subdivisions, never added to consumer_wall. Cumulative interface process CPU snapshots are not additional per-tool CPU.",
        shared_preparation="Full feature/model preparation, cache storage and initial runtime cold-load costs are reported by root COSTS separately. Cache reads here do not represent full pipeline cost.")


def score_case(task, route, truth, current, required, resolver, recovery):
    folder = HERE / "private/consumers" / task["task_id"] / route
    receipt_path = folder / "CONSUMER.json"
    receipt = read(receipt_path) if receipt_path.exists() else {}
    final_path = next((folder / name for name in ("PUBLIC_FINAL.txt", "final.txt") if (folder / name).exists()), None)
    text = final_path.read_text(encoding="utf8") if final_path else receipt.get("final")
    answer, parsing = parse_answer(text) if isinstance(text, str) else (None, dict(status="missing", method=None, error=None))
    schema = schema_check(answer, required)
    ids, location, measurements = geometry_check(answer, task, current)
    reference = reference_check(answer, task, route, ids, location, current, resolver)
    task_identity_matches = bool(answer and answer.get("task_id") == task["task_id"] and answer.get("entrypoint") == task["entrypoint"])
    actual_sha = current["input_identity"]["sha256"]
    task_sha = current["task_identity"]["sha256"]
    source_unchanged = bool(receipt.get("source_unchanged") is True
        and receipt.get("current_input_identity", {}).get("sha256") == actual_sha
        and receipt.get("current_input_identity_after", {}).get("sha256") == actual_sha
        and receipt.get("task_identity", {}).get("sha256") == task_sha and receipt.get("task_identity_after", {}).get("sha256") == task_sha)
    editing_false = bool(answer and answer.get("editing_executed") is False)
    state, entry = truth["state"], task["entrypoint"]
    support_area = float(current["area"][current["F"]][current["mask"]].sum())
    supported_ids = current["F"][current["mask"]]
    hit_area = float(current["area"][np.intersect1d(ids, supported_ids)].sum()) if location["source_IDs_in_range"] else None
    recall = hit_area / support_area if entry == "inspect" and support_area > 0 and hit_area is not None else None
    anomaly = answer.get("anomaly_asserted") if answer else None
    assertion_defined = type(anomaly) is bool
    affected = recovery is not None and recovery.get("affected_completed_task") == task["task_id"] + "/" + route
    automatic_success = bool(receipt.get("valid_completion") is True and schema["complete"] and task_identity_matches
        and location["entrypoint_location_correct"] and measurements["all_nonempty_geometry_correct"]
        and reference["criterion_satisfied"] and source_unchanged and editing_false)
    return dict(task_id=task["task_id"], route=route, entrypoint=entry, state_for_scoring=state,
        consumer_status=receipt.get("status", "not_executed_or_missing_record"), valid_completion=receipt.get("valid_completion") is True,
        infrastructure_affected=affected, infrastructure_evidence=identity(HERE / "private/consumers/recovery/RECOVERY.json") if affected else None,
        infrastructure_tool_error_count=len(recovery.get("actual_tool_errors", [])) if affected else 0,
        infrastructure_errors=recovery.get("actual_tool_errors") if affected else None,
        consumer_errors=receipt.get("errors"), unexpected_tool_events=receipt.get("unexpected_tool_events"),
        final_evidence=identity(final_path) if final_path else None, receipt_evidence=identity(receipt_path) if receipt_path.exists() else None,
        raw_answer_evidence=[identity(folder/name) for name in ("PUBLIC_FINAL.txt", "final.txt") if (folder/name).exists()],
        chosen_answer_source=final_path.name if final_path else ("CONSUMER.json.final" if isinstance(text,str) else None),
        chosen_answer_matches_receipt_final=text == receipt.get("final") if isinstance(text,str) and isinstance(receipt.get("final"),str) else None,
        parsing=parsing, parsed_answer=answer, schema=schema, answer_task_identity_matches=task_identity_matches,
        location=location, geometry_measurements=measurements, reference=reference,
        source_unchanged_verified=source_unchanged, editing_executed_flag_false=editing_false,
        complete_nonempty_geometry_delivery=automatic_success,
        inspect_truth=dict(support_points=int(current["mask"].sum()), support_lumped_area_native=support_area,
            selected_support_lumped_area_native=hit_area, area_recall=recall,
            selection_eligible_for_budget_comparison=location["entrypoint_location_correct"],
            budget_compliant_area_recall=recall if location["entrypoint_location_correct"] else None,
            zero_hit=recall == 0 if recall is not None else None) if entry == "inspect" else None,
        anomaly_assertion=dict(defined=assertion_defined, asserted=anomaly if assertion_defined else None,
            normal_inspect_false_assertion=anomaly is True if state == "normal" and entry == "inspect" and assertion_defined else None,
            interpretation="Only the explicit anomaly_asserted boolean is scored as an anomaly assertion. Natural concavity or attention-candidate descriptions in evidence are not converted into assertions."),
        author_review_pending=dict(status="pending_author_review", original_answer_path=final_path.relative_to(HERE).as_posix() if final_path else (receipt_path.relative_to(HERE).as_posix() if isinstance(text,str) else None),
            fields=["evidence", "missing_information", "operation_plan", "protection_respected"],
            reported_protection_respected=answer.get("protection_respected") if answer else None,
            rubric="Review whether the stated plan uses the requested target and protects user background, preserves measured/predicted distinctions, requests missing artistic constraints and adds warranted reads. This script supplies no independent or semantic plan grade."),
        costs=consumer_costs(folder, receipt), input_identity=current["input_identity"], scoring_truth_identity=current["truth_identity"])


def aggregate(cases):
    rows = []
    for route in ("native", "facts", "learned"):
        for entry in ("inspect", "focus"):
            group = [row for row in cases if row["route"] == route and row["entrypoint"] == entry]
            damaged = [row for row in group if row["state_for_scoring"] == "damaged"]
            normal = [row for row in group if row["state_for_scoring"] == "normal"]
            raw_recalls = [row["inspect_truth"]["area_recall"] for row in damaged if row["inspect_truth"] and row["inspect_truth"]["area_recall"] is not None]
            recalls = [row["inspect_truth"]["budget_compliant_area_recall"] for row in damaged if row["inspect_truth"] and row["inspect_truth"]["budget_compliant_area_recall"] is not None]
            walls = [row["costs"]["consumer_wall_s"] for row in group if finite_number(row["costs"]["consumer_wall_s"])]
            usage_keys = sorted({key for row in group for key in (row["costs"]["usage"] or {})})
            usages = {key: dict(measured_sum=sum(row["costs"]["usage"][key] for row in group if finite_number((row["costs"]["usage"] or {}).get(key))),
                               measured_cases=sum(finite_number((row["costs"]["usage"] or {}).get(key)) for row in group), denominator=len(group)) for key in usage_keys}
            rows.append(dict(route=route, entrypoint=entry, denominator=len(group), consumer_status_counts=dict(Counter(row["consumer_status"] for row in group)),
                valid_completions=sum(row["valid_completion"] for row in group), parsed_answers=sum(row["parsing"]["status"] == "parsed" for row in group),
                schema_complete=sum(row["schema"]["complete"] for row in group), empty_selections=sum(row["location"]["empty_selection"] for row in group),
                complete_nonempty_geometry_deliveries=sum(row["complete_nonempty_geometry_delivery"] for row in group),
                infrastructure_affected=sum(row["infrastructure_affected"] for row in group),
                damaged_task_denominator=len(damaged), normal_task_denominator=len(normal),
                damaged_inspect_raw_recall_measured_cases=len(raw_recalls), damaged_inspect_raw_recall_measured_only_mean=float(np.mean(raw_recalls)) if raw_recalls else None,
                damaged_inspect_budget_compliant_recall_cases=len(recalls), damaged_inspect_budget_compliant_recall_mean=float(np.mean(recalls)) if recalls else None,
                damaged_inspect_primary_mean_recall=sum(recalls)/len(damaged) if entry == "inspect" and damaged else None,
                primary_recall_missing_policy="unscorable delivered localization contributes no achieved recall, measured-only results and missing cases retained separately",
                measured_damaged_inspect_zero_hits=sum(row["inspect_truth"]["zero_hit"] is True for row in damaged if row["inspect_truth"]),
                normal_inspect_false_assertions=sum(row["anomaly_assertion"]["normal_inspect_false_assertion"] is True for row in normal),
                normal_inspect_assertion_unmeasured=sum(not row["anomaly_assertion"]["defined"] for row in normal) if entry == "inspect" else None,
                focus_exact_target_count=sum(row["location"]["focus_exact_explicit_target"] for row in group) if entry == "focus" else None,
                measured_consumer_wall_sum_s=sum(walls), measured_consumer_wall_cases=len(walls),
                measured_consumer_wall_mean_s=float(np.mean(walls)) if walls else None, usage=usages,
                monetary_fees_known_cases=sum(row["costs"]["fees"] is not None for row in group),
                monetary_fees_total=None,
                reported_fee_records=[row["costs"]["fees"] for row in group],
                monetary_fee_aggregation="unknown unless measured records establish matching currency and scope, no imputed zero",
                author_plan_reviews_pending=len(group)))
    return rows


def main():
    started, cpu = time.perf_counter(), time.process_time()
    plan = read(HERE / "PLAN.json")
    tasks = read(HERE / "TASKS.json")["tasks"]
    if len(tasks) != 8 or plan["consumer"]["routes"] != ["native", "facts", "learned"]:
        raise ValueError("fixed8tasks3routes_required")
    expected = [(task, route) for task in tasks for route in plan["consumer"]["routes"]]
    for task, route in expected:
        path = HERE / "private/consumers" / task["task_id"] / route / "CONSUMER.json"
        if path.exists() and read(path).get("status") == "running":
            raise RuntimeError("consumers_still_running_no_partial_scoring")
    truth_rows = read(HERE / "private/scoring/TASK_TRUTH.json")["cases"]
    truths = {row["task_id"]: row for row in truth_rows}
    if len(truths) != 8 or set(truths) != {task["task_id"] for task in tasks}:
        raise ValueError("fixed8task_truth_denominator_required")
    recovery_path = HERE / "private/consumers/recovery/RECOVERY.json"
    recovery = read(recovery_path) if recovery_path.exists() else None
    resolver = TaskPerception()
    currents = {task["task_id"]: current_task(task, truths[task["task_id"]]) for task in tasks}
    cases = [score_case(task, route, truths[task["task_id"]], currents[task["task_id"]], plan["consumer"]["answer_schema"], resolver, recovery)
             for task, route in expected]
    output = dict(cycle_id="M6-TASK-PERCEPTION-001", status="completed_author_automatic_consumer_checks", primary_denominator=24,
        actual_consumer_records=sum(row["receipt_evidence"] is not None for row in cases), cases=cases, route_by_entrypoint=aggregate(cases),
        actual_CLAIM_files=len(list((HERE/"private/consumers").glob("*/*/CLAIM.json"))),
        infrastructure_comparison_caveat="t01/native remains in the primary denominator. Its original execution errors and exhausted tool budget affect the first-task route comparison. No prompt or CLAIM is replayed.",
        scoring_role="author automatic geometry/schema/reference/cost checks, with all plan/evidence/protection-content judgments pending author review and later independent blinded review",
        empty_selection_policy="Empty IDs and undefined centroid/bbox are retained explicitly and cannot count as complete nonempty geometry delivery. Normal negative anomaly assertions are scored separately.",
        exact_geometry_definition="current full-source triangle area distributed one third to each vertex, area-weighted selected centroid, selected bbox and normalized area-weighted current vertex normal",
        tolerance_definition=dict(position_over_full_current_bbox_diagonal=1e-6, area_relative=1e-6, area_budget_numeric_slack_over_F_area=1e-12),
        shared_pipeline_cost_scope="root COSTS includes whole shared preparation/training/inference/cache and first cold-load. This report retains consumer sessions and overlapping local timing subdivisions without adding nested spans.",
        monetary_fees="unknown where source receipts contain null, never imputed as zero", training_runs=0, model_forwards=0, Pro_calls=0,
        wall_s_before_write=time.perf_counter()-started, CPU_s_before_write=time.process_time()-cpu)
    def json_scalar(value):
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError("unsupported_score_JSON_type_" + type(value).__name__)

    (HERE / "CONSUMER_SCORES.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False, default=json_scalar) + "\n", encoding="utf8", newline="\n")
    print("author automatic consumer checks",len(cases),"cases",sum(row["complete_nonempty_geometry_delivery"] for row in cases),"complete nonempty geometry deliveries",flush=True)


if __name__ == "__main__":
    main()
