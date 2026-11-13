"""Recount existing 003 evidence with the Python standard library only.

This script never imports the experiment, starts children, or changes its inputs.
"""

import ast
import hashlib
import json
import math
import statistics
import struct
import zipfile
from collections import Counter
from fractions import Fraction
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
CHECKS = 0
INPUTS = {}


def check(condition, description):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise ValueError(description)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = digest(data)
    return data


def load(path):
    return json.loads(read(path).decode("utf-8"))


def fraction_record(value):
    return {"numerator": value.numerator, "denominator": value.denominator,
            "value": float(value)}


def check_fraction(record, value, label):
    check(record["numerator"] == value.numerator and
          record["denominator"] == value.denominator and
          record["value"] == float(value), label)


def interval(value, label):
    check(value["closed_ns"] >= value["started_ns"], label + " order")
    check(value["elapsed_ns"] == value["closed_ns"] - value["started_ns"],
          label + " difference")
    return value["elapsed_ns"]


def cleanup(value, pid, label):
    interval(value, label)
    check(value["pid"] == pid, label + " original PID")
    check(value["confirmed"] is True and value["reaped"] is True,
          label + " confirmed reap")
    check(value["process_handle_closed"] is True, label + " original handle closed")
    check(value["pipes_closed"] == {"stdin": True, "stdout": True, "stderr": True},
          label + " all three pipes closed")
    check(value["errors"] == [], label + " no cleanup errors")


def npz_payload(data, expected, label):
    """Decode only .npy headers and hash existing raw array payloads."""
    import io

    total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        check(sorted(archive.namelist()) == ["color.npy", "depth.npy", "owners.npy"],
              label + " exact array members")
        for name, metadata in expected.items():
            raw = archive.read(name + ".npy")
            check(raw[:6] == b"\x93NUMPY", label + " NPY magic " + name)
            version = tuple(raw[6:8])
            check(version in {(1, 0), (2, 0), (3, 0)}, label + " NPY version " + name)
            width = 2 if version == (1, 0) else 4
            header_length = struct.unpack("<H" if width == 2 else "<I", raw[8:8 + width])[0]
            header_end = 8 + width + header_length
            header = ast.literal_eval(raw[8 + width:header_end].decode("utf-8"))
            payload = raw[header_end:]
            check(header["fortran_order"] is False, label + " C-order " + name)
            check(list(header["shape"]) == metadata["shape"], label + " shape " + name)
            check(header["descr"] == metadata["dtype_str"], label + " dtype " + name)
            check(len(payload) == metadata["nbytes"], label + " nbytes " + name)
            check(digest(payload) == metadata["sha256"], label + " raw array hash " + name)
            itemsize = int(header["descr"][2:])
            check(math.prod(header["shape"]) * itemsize == len(payload),
                  label + " shape times itemsize " + name)
            total += len(payload)
    return total


def trace_records(directory):
    data = read(directory / "TRACE.jsonl")
    lines = data.splitlines(keepends=True)
    records = [json.loads(line) for line in lines]
    check([value["sequence"] for value in records] == list(range(1, len(records) + 1)),
          str(directory) + " trace sequence")
    check([value["monotonic_ns"] for value in records] ==
          sorted(value["monotonic_ns"] for value in records), str(directory) + " trace order")
    return data, lines, records


def recount_run(row, frozen):
    label = row["id"]
    directory = Path(row["output_directory"]).resolve()
    result_bytes = read(directory / "RESULT.json")
    result = json.loads(result_bytes)
    publication_bytes = read(directory / "RESULT_PUBLICATION.json")
    publication = json.loads(publication_bytes)
    trace_bytes, trace_lines, trace = trace_records(directory)
    check(row["status"] == result["status"] == "completed", label + " completed")
    check(row["returncode"] == 0 and result["exceptions"] == [], label + " successful exit")
    for key in ("arm", "scenario", "process_id"):
        check(row[key] == result[key], label + " binding " + key)
    pid = row["process_id"]
    check(result["launch_environment"]["process_id"] == pid, label + " launch PID")
    check(all(value["process_id"] == pid and value["arm"] == row["arm"] and
              value["scenario"] == row["scenario"] for value in trace), label + " trace identity")
    check(Path(result["output_directory"]).resolve() == directory, label + " output binding")
    cleanup(row["cleanup"], pid, label + " cleanup")
    check(row["cleanup"]["exit_code"] == row["returncode"] and
          row["cleanup"]["kill_requested"] is False, label + " ordinary clean exit")
    interval(row, label + " parent window")
    interval(publication, label + " RESULT publication")
    check(row["started_ns"] <= result["started_ns"] <= result["work_closed_ns"] <=
          publication["started_ns"] <= publication["closed_ns"] <=
          row["process_exited_ns"] <= row["cleanup"]["started_ns"] <=
          row["cleanup"]["closed_ns"] <= row["cleanup_exited_ns"] <= row["closed_ns"],
          label + " full parent/child/publication/cleanup ordering")
    check(result["elapsed_before_result_publication_ns"] ==
          result["work_closed_ns"] - result["started_ns"], label + " child work delta")
    check(publication["RESULT_sha256"] == digest(result_bytes) and
          publication["RESULT_bytes"] == len(result_bytes), label + " RESULT receipt")
    check(trace[-1]["event"] == "process_complete" and
          trace[-1]["RESULT_sha256"] == digest(result_bytes), label + " final trace RESULT receipt")
    check(trace[-1]["monotonic_ns"] <= row["process_exited_ns"], label + " trace before exit")
    before_publication = sum(len(line) for line, event in zip(trace_lines, trace)
                             if event["event"] != "process_complete")
    check(before_publication == result["trace_bytes_before_result_publication"],
          label + " trace publication byte boundary")
    intents = [value for value in trace if value["event"] == "render_attempt"]
    completions = [value for value in trace if value["event"] == "render_complete"]
    frames_complete = [value for value in trace if value["event"] == "frame_complete"]
    ids = [value["attempt_id"] for value in intents]
    check(ids == list(range(1, len(ids) + 1)), label + " unique render attempts")
    check([value["attempt_id"] for value in completions] == ids and
          [value["attempt_id"] for value in frames_complete] == ids, label + " all attempts accounted")
    check(len(ids) == len(result["render_attempts"]) == len(result["frames"]) ==
          len(result["steps"]) == row["render_attempts"], label + " exact row counts")
    for attempt, intent, completion in zip(result["render_attempts"], intents, completions):
        check(attempt["attempt_id"] == intent["attempt_id"] == completion["attempt_id"] and
              attempt["view_name"] == intent["view_name"] == completion["view_name"],
              label + " render trace correspondence")
        check(attempt["status"] == "completed" and
              intent["monotonic_ns"] == attempt["intent_ns"] <=
              attempt["render_started_ns"] <= attempt["render_closed_ns"] <=
              completion["monotonic_ns"] <= attempt["completed_ns"], label + " render intent before work")
        check(completion["started_ns"] == attempt["render_started_ns"] and
              completion["closed_ns"] == attempt["render_closed_ns"], label + " raster boundaries")
        check(intent["sequence"] == attempt["intent_trace_sequence"], label + " intent sequence")
    audit = result["audit"]
    check(audit["installed_before_dynamic_imports"] is True and
          audit["forbidden_old_evidence_reads"] == audit["forbidden_old_writes"] == 0 and
          audit["old_evidence_read_attempts"] == audit["old_write_attempts"] == [],
          label + " old evidence audit")
    check(not any(value["event"].startswith("forbidden_") for value in trace), label + " trace old audit")
    environment = result["launch_environment"]
    launch = frozen["launch_contract"]
    for key in ("base_executable", "base_executable_sha256", "bootstrap_path",
                "bootstrap_sha256", "explicit_site_packages", "product_install_root",
                "dependency_manifest_path", "dependency_manifest_sha256"):
        check(environment[key] == launch[key], label + " launch source " + key)
    for key in ("numpy", "pillow"):
        check(environment[key] == launch["expected_dependencies"][key], label + " dependency " + key)
    check(environment["product_binding"] == result["dependencies"], label + " product binding")
    for path, expected in environment["baseline_sources_sha256"].items():
        check(frozen["runtime_sources"][path] == expected, label + " unchanged baseline source")
    for stage_name, stage in result["stages"].items():
        interval(stage, label + " stage " + stage_name)
        check(result["started_ns"] <= stage["started_ns"] <= stage["closed_ns"] <=
              result["work_closed_ns"], label + " stage in child work " + stage_name)

    index = result["index"]
    roi_ids = index["roi_ids"]
    check(len(roi_ids) == len(set(roi_ids)) == 6, label + " discovered six unique regions")
    universe = set(roi_ids)
    masks = index["view_masks"]
    mask_ids = {name: {identity for bit, identity in enumerate(roi_ids) if mask & (1 << bit)}
                for name, mask in masks.items()}
    pool_uncovered = universe - set().union(*mask_ids.values())
    covered = set()
    history = set()
    bytes_count = Counter()
    previous_views = []
    sequence = []
    seen_files = set()
    for frame, step, intent in zip(result["frames"], result["steps"], intents):
        name = frame["view_name"]
        check(frame["attempt_id"] == step["attempt_id"] == intent["attempt_id"] and
              name == step["view_name"] == intent["view_name"], label + " frame binding")
        check(name not in previous_views, label + " no repeated render")
        if row["arm"] == "B" and previous_views:
            remaining = [view for view in index["view_order"] if view not in previous_views]
            gains = {view: len(mask_ids[view] - covered) for view in remaining}
            best = max(gains.values(), default=0)
            chosen = next((view for view in remaining if gains[view] == best), None)
            check(best > 0 and name == chosen, label + " finite greedy mask ordering")
        elif row["arm"] == "B":
            check(name == index["view_order"][0], label + " initial scene view")
        else:
            check(name == index["view_order"][len(previous_views)], label + " exhaustive order")
        previous_views.append(name)
        rows = frame["pixel_rows"]
        check(rows == step["pixel_rows"] and len(rows) == len(roi_ids) and
              {value["roi_id"] for value in rows} == universe, label + " complete pixel rows")
        for pixel in rows:
            check(pixel["minimum_surface_pixels"] == 16 and pixel["minimum_boundary_pixels"] == 4 and
                  pixel["minimum_rgb_boundary_contrast"] == 24, label + " unchanged thresholds")
            readable = pixel["front_facing"] and pixel["visible_surface_pixels"] >= 16 and \
                pixel["contrasting_boundary_pixels"] >= 4
            check(pixel["readable"] is readable and pixel["view"] == name,
                  label + " pixel threshold status")
        readable_ids = {value["roi_id"] for value in rows if value["readable"]}
        complete = mask_ids[name]
        shortfall = complete - readable_ids
        new = (complete & readable_ids) - covered
        covered.update(new)
        history.update(shortfall)
        for key, actual in (("geometry_complete_roi_ids", complete), ("readable_roi_ids", readable_ids),
                            ("pixel_shortfall_roi_ids", shortfall), ("new_roi_ids", new),
                            ("covered_roi_ids", covered), ("unresolved_roi_ids", universe - covered)):
            check(step[key] == sorted(actual), label + " step state " + key)
        receipt = frame["receipt"]
        check(receipt == step["receipt"] and receipt["actual_image_delivered"] is True and
              receipt["scene_identity"] == index["scene_identity"] and
              receipt["candidate_identity"] == index["candidate_identity"] and
              receipt["view_name"] == name and receipt["readable_roi_ids"] == sorted(readable_ids),
              label + " bound local PNG receipt")
        for field, size_field, hash_field, category in (
                ("PNG", "PNG_bytes", "PNG_sha256", "PNG_bytes"),
                ("owner_depth_RGB_arrays", "compressed_array_file_bytes", "arrays_sha256", "NPZ_bytes"),
                ("metadata_path", "metadata_bytes", "metadata_sha256", "frame_metadata_bytes")):
            path = Path(frame[field]).resolve()
            check(path.is_relative_to(directory) and path not in seen_files, label + " owned unique file " + field)
            seen_files.add(path)
            data = read(path)
            check(len(data) == frame[size_field] and digest(data) == frame[hash_field],
                  label + " byte/hash " + category)
            bytes_count[category] += len(data)
            if category == "NPZ_bytes":
                payload = npz_payload(data, frame["arrays"], label + " " + name)
                check(payload == frame["array_payload_bytes"], label + " frame raw payload")
                bytes_count["array_payload_bytes"] += payload
            if category == "frame_metadata_bytes":
                metadata = json.loads(data)
                for key, value in metadata.items():
                    if key == "metadata_stage_scope":
                        continue
                    if key == "stages":
                        check(value == {stage: entry for stage, entry in frame["stages"].items()
                                        if stage != "metadata"}, label + " metadata pre-close stages")
                    else:
                        check(frame[key] == value, label + " metadata field " + key)
        check(receipt["image_path"] == frame["PNG"] and receipt["image_sha256"] == frame["PNG_sha256"],
              label + " image receipt exact file")
        sequence.append({"view": name, "new_count": len(new), "shortfall_count": len(shortfall),
                         "shortfall_roi_ids": sorted(shortfall), "new_roi_ids": sorted(new)})

    final = result["final_state"]
    unresolved = universe - covered
    final_shortfall = history & unresolved
    check(final["covered_roi_ids"] == sorted(covered) and
          final["unresolved_roi_ids"] == sorted(unresolved) and
          final["candidate_pool_uncovered_roi_ids"] == sorted(pool_uncovered) and
          final["observed_views"] == previous_views and final["state_updates"] == len(intents),
          label + " independent final state")
    check(result["pixel_shortfall_history_roi_ids"] == sorted(history) and
          result["final_pixel_shortfall_roi_ids"] == sorted(final_shortfall), label + " history/final distinction")
    repeat = result["repeat_query"]
    check(repeat["render_attempts_before"] == repeat["render_attempts_after"] == len(intents) and
          repeat["new_render_attempts"] == 0 and repeat["state_before"] == repeat["state_after"] == final and
          repeat["reuse_update"]["reused"] is True and repeat["reuse_update"]["new_roi_ids"] == [],
          label + " repeat zero new frames")
    check(repeat["next_view"] is None and unresolved == pool_uncovered,
          label + " finite pool termination")
    check(len(covered) == 5 and len(pool_uncovered) == 1 and final_shortfall == set(),
          label + " expected actual coverage")
    if row["scenario"] == "main":
        check(previous_views == (index["view_order"] if row["arm"] == "A" else ["SCENE", "BACK"]),
              label + " registered main views")
    else:
        back_position = previous_views.index("BACK")
        back_shortfall = set(sequence[back_position]["shortfall_roi_ids"])
        check(bool(back_shortfall), label + " control real geometric/pixel shortfall")
        if row["arm"] == "B":
            later_new = set().union(*(set(value["new_roi_ids"]) for value in sequence[back_position + 1:]))
            check(bool(back_shortfall & later_new) and back_shortfall <= later_new,
                  label + " control later actual recovery")

    bytes_count["RESULT_bytes"] = len(result_bytes)
    bytes_count["publication_bytes"] = len(publication_bytes)
    bytes_count["TRACE_bytes"] = len(trace_bytes)
    for stem in ("STDOUT", "STDERR"):
        data = read(directory / (stem + ".bin"))
        check(len(data) == row[stem.lower() + "_bytes"] and
              digest(data) == row[stem.lower() + "_sha256"], label + " " + stem + " bytes")
        bytes_count[stem + "_bytes"] = len(data)
    bytes_count["text_bytes"] = sum(bytes_count[key] for key in
        ("frame_metadata_bytes", "RESULT_bytes", "publication_bytes", "TRACE_bytes", "STDOUT_bytes", "STDERR_bytes"))
    bytes_count["disk_bytes"] = bytes_count["text_bytes"] + bytes_count["PNG_bytes"] + bytes_count["NPZ_bytes"]
    files = [path for path in directory.rglob("*") if path.is_file()]
    check(sum(path.stat().st_size for path in files) == bytes_count["disk_bytes"] and
          len(files) == 5 + 3 * len(intents), label + " full run file inventory")
    metrics = result["metrics"]
    for key, expected in (("raster_attempts", len(intents)), ("raster_completed", len(completions)),
                          ("frames_completed", len(frames_complete)), ("pixel_tests", len(intents) * len(roi_ids)),
                          ("pixel_test_attempts", len(intents) * len(roi_ids))):
        check(metrics[key] == expected, label + " child metric " + key)
    for key in ("PNG_bytes", "NPZ_bytes", "array_payload_bytes", "frame_metadata_bytes"):
        check(metrics[key] == bytes_count[key], label + " metric bytes " + key)
    facts = row["facts"]
    for key, expected in (("render_attempts", len(intents)), ("render_completed", len(completions)),
                          ("views", previous_views), ("pixel_tests", len(intents) * len(roi_ids)),
                          ("PNG_bytes", bytes_count["PNG_bytes"]), ("NPZ_bytes", bytes_count["NPZ_bytes"]),
                          ("array_payload_bytes", bytes_count["array_payload_bytes"]),
                          ("metadata_bytes", bytes_count["frame_metadata_bytes"]), ("result_bytes", len(result_bytes)),
                          ("publication_bytes", len(publication_bytes)), ("trace_bytes", len(trace_bytes)),
                          ("covered_roi_ids", sorted(covered)), ("unresolved_roi_ids", sorted(unresolved)),
                          ("pixel_shortfall_history_roi_ids", sorted(history)),
                          ("final_pixel_shortfall_roi_ids", sorted(final_shortfall)),
                          ("recovered_pixel_shortfall_roi_ids", sorted(history - final_shortfall))):
        check(facts[key] == expected, label + " parent fact " + key)
    phase_ns = {
        "parent_before_child_start": result["started_ns"] - row["started_ns"],
        "child_work": result["work_closed_ns"] - result["started_ns"],
        "work_close_to_process_exit": row["process_exited_ns"] - result["work_closed_ns"],
        "process_exit_to_cleanup_boundary": row["cleanup_exited_ns"] - row["process_exited_ns"],
        "parent_readback_after_cleanup": row["closed_ns"] - row["cleanup_exited_ns"],
    }
    check(sum(phase_ns.values()) == row["elapsed_ns"], label + " disjoint primary cost regions")
    return {"id": label, "pair": row["pair"], "arm": row["arm"], "scenario": row["scenario"],
            "process_id": pid, "primary_ns": row["elapsed_ns"], "started_ns": row["started_ns"],
            "closed_ns": row["closed_ns"], "cleanup_confirmed": True, "views": previous_views,
            "render_attempts": len(intents), "pixel_tests": len(intents) * len(roi_ids),
            "covered_roi_ids": sorted(covered), "unresolved_roi_ids": sorted(unresolved),
            "candidate_pool_uncovered_roi_ids": sorted(pool_uncovered), "feedback": sequence,
            "history_shortfall_roi_ids": sorted(history), "final_shortfall_roi_ids": sorted(final_shortfall),
            "bytes": dict(bytes_count), "phase_ns": phase_ns,
            "child_stages_ns": {key: value["elapsed_ns"] for key, value in result["stages"].items()},
            "RESULT_publication_ns": publication["elapsed_ns"]}


def aggregate(rows):
    byte_totals = Counter()
    phase_totals = Counter()
    for row in rows:
        byte_totals.update(row["bytes"])
        phase_totals.update(row["phase_ns"])
    times = [row["primary_ns"] for row in rows]
    return {"runs": len(rows), "render_attempts": sum(row["render_attempts"] for row in rows),
            "pixel_tests": sum(row["pixel_tests"] for row in rows), "primary_sum_ns": sum(times),
            "primary_median_ns": statistics.median(times), "primary_min_ns": min(times),
            "primary_max_ns": max(times), "bytes": dict(byte_totals), "phase_ns": dict(phase_totals)}


def recount_qualification(qualification, frozen, formal_start):
    check(qualification["all_passed"] is True and qualification["errors"] == [], "four qualification outcomes")
    check(qualification["actual_child_processes"] == len(qualification["cases"]) == 4,
          "qualification denominator four")
    check(qualification["new_raster_calls"] == qualification["new_model_provider_Blender_API_runs"] == 0,
          "qualification no raster/external calls")
    check(qualification["source_files_sha256"] == frozen["runtime_sources"] and
          qualification["source_unchanged"] is True, "qualification exact frozen sources")
    expected = {"normal": (0, "completed", 0, True),
                "nonzero": (1, "failed", 0, False),
                "timeout": (1, "waiting", 0, False),
                "receipt_failure": (0, "action_executed_receipt_omitted", 1, False)}
    check([case["scenario"] for case in qualification["cases"]] == list(expected), "qualification order")
    records = []
    for case in qualification["cases"]:
        label = "qualification " + case["scenario"]
        exitcode, phase, actions, receipt_ok = expected[case["scenario"]]
        check(case["Popen_pid"] == case["actual_pid"] == case["child_state"]["process_id"] ==
              case["launch_environment"]["process_id"], label + " strict PID")
        cleanup(case["cleanup"], case["Popen_pid"], label + " cleanup")
        check(case["passed"] is True and case["state"] == "completed" and
              case["exit_code"] == exitcode and case["child_state"]["phase"] == phase and
              case["action_count"] == actions and
              case["receipt_validation"]["passed"] is receipt_ok, label + " registered expected outcome")
        if "marker_actions" in case["child_state"]:
            check(case["child_state"]["marker_actions"] == actions, label + " reported marker count")
        else:
            check(case["scenario"] == "nonzero", label + " registered exception state has no action field")
        check(case["started_ns"] <= case["before_Popen_ns"] <= case["Popen_returned_ns"] <=
              case["handshake_confirmed_ns"] <= case["wait_boundary_ns"] <=
              case["cleanup"]["started_ns"] <= case["cleanup"]["closed_ns"] <=
              case["streams_closed_ns"] <= case["readback_closed_ns"], label + " complete timing order")
        for path, expected_hash in case["files_sha256"].items():
            evidence_path = Path(case["output_directory"]) / path
            check(digest(read(evidence_path)) == expected_hash, label + " preserved evidence file")
        trace = [json.loads(line) for line in read(Path(case["output_directory"]) / "TRACE.jsonl").splitlines()]
        check(not any(value["event"] == "render_attempt" for value in trace), label + " zero trace raster attempts")
        marker_events = [value for value in trace if value["event"] == "marker_written"]
        check(len(marker_events) == actions, label + " raw marker event count")
        marker_path = Path(case["output_directory"]) / "MARKER.json"
        check(marker_path.exists() == bool(actions), label + " raw marker presence")
        if actions:
            marker_bytes = read(marker_path)
            marker = json.loads(marker_bytes)
            check(marker["action_count"] == 1 and marker["process_id"] == case["actual_pid"] and
                  digest(marker_bytes) == marker_events[0]["marker_sha256"], label + " actual marker binding")
        if case["scenario"] == "timeout":
            check(case["timeout_after_handshake"] is True and case["cleanup"]["kill_requested"] is True and
                  case["wait_boundary_ns"] >= case["registered_wait_deadline_ns"], label + " actual registered timeout")
        records.append({"scenario": case["scenario"], "expected_outcome_verified": True,
                        "actual_pid": case["actual_pid"], "child_exit_code": exitcode,
                        "child_phase": phase, "receipt_valid": receipt_ok,
                        "receipt_validation": case["receipt_validation"], "marker_actions": actions,
                        "cleanup_confirmed": True,
                        "full_case_ns": case["readback_closed_ns"] - case["started_ns"],
                        "Popen_to_readback_ns": case["readback_closed_ns"] - case["before_Popen_ns"]})
    timing = qualification["timing"]
    elapsed = timing["work_closed_before_result_publication_ns"] - timing["started_ns"]
    check(elapsed > 0 and timing["work_closed_before_result_publication_ns"] <= formal_start,
          "qualification ends before formal batch")
    check(sum(record["marker_actions"] for record in records) == qualification["marker_actions"] == 1,
          "one qualification marker action")
    final_timing = load(BATCH / "qualification" / "FINAL_TIMING.json")
    interval(final_timing, "qualification including RESULTS publication")
    check(final_timing["started_ns"] == timing["started_ns"] and
          timing["work_closed_before_result_publication_ns"] <= final_timing["closed_ns"] <= formal_start,
          "qualification final publication boundary")
    return {"elapsed_ns": elapsed, "including_RESULTS_publication_ns": final_timing["elapsed_ns"],
            "timing": timing, "final_timing": final_timing, "cases": records,
            "expected_outcome_case_count": 4, "successful_business_actions_claimed": 0,
            "marker_actions": 1, "raster_attempts": 0,
            "publication_scope": "Both pre-summary and including-RESULTS intervals retained. FINAL_TIMING self-publication unmeasured."}


def main():
    original = load(BATCH / "RESULTS.json")
    plan = load(BATCH / "PREREGISTRATION.json")
    frozen = load(BATCH / "FROZEN.json")
    qualification = load(BATCH / "qualification" / "RESULTS.json")
    check(original["freeze_sha256"] == INPUTS[str((BATCH / "FROZEN.json").resolve())], "frozen manifest hash")
    check(original["qualification_result_sha256"] == INPUTS[str((BATCH / "qualification" / "RESULTS.json").resolve())],
          "qualification RESULT hash")
    check(len(frozen["runtime_sources"]) == 158, "158 frozen source records")
    for path, expected in frozen["runtime_sources"].items():
        check(digest(read(path)) == expected, "unchanged frozen source " + path)
    check(original["stop"] is None and original["preparation_render_attempts"] == 0 and
          original["new_experimental_model_provider_Blender_API_runs"] == 0, "no stop/preparation raster/external calls")
    source_rows = original["rows"] + original["controls"]
    planned = plan["main"] + plan["control"]
    check(len(source_rows) == len(planned) == 14, "14 planned formal/control entries")
    for row, expected in zip(source_rows, planned):
        check({key: row[key] for key in ("id", "pair", "arm", "scenario")} == expected,
              "ordered registration " + expected["id"])
    rows = [recount_run(row, frozen) for row in source_rows]
    main_rows = rows[:12]
    controls = rows[12:]
    for left, right in zip(rows, rows[1:]):
        check(left["closed_ns"] <= right["started_ns"], "sequential primary windows")
    check(len({row["process_id"] for row in rows}) == 14, "14 distinct formal/control process IDs")
    for scenario_rows in (main_rows, controls):
        first = scenario_rows[0]
        check(all(row["covered_roi_ids"] == first["covered_roi_ids"] and
                  row["unresolved_roi_ids"] == first["unresolved_roi_ids"] for row in scenario_rows),
              "cross-arm actual coverage equivalence")
    pairs = []
    ratios = []
    for pair in range(1, 7):
        members = [row for row in main_rows if row["pair"] == pair]
        check([row["arm"] for row in members] == (["A", "B"] if pair % 2 else ["B", "A"]),
              "AB/BA order pair " + str(pair))
        by_arm = {row["arm"]: row for row in members}
        ratio = Fraction(by_arm["B"]["primary_ns"], by_arm["A"]["primary_ns"])
        ratios.append(ratio)
        pair_record = {"pair": pair, "order": "".join(row["arm"] for row in members),
                       "A_ns": by_arm["A"]["primary_ns"], "B_ns": by_arm["B"]["primary_ns"],
                       "B_over_A": fraction_record(ratio)}
        source_pair = original["summary"]["pairs"][pair - 1]
        check(source_pair["pair"] == pair and source_pair["A_ns"] == pair_record["A_ns"] and
              source_pair["B_ns"] == pair_record["B_ns"], "raw pair times")
        check_fraction(source_pair["B_over_A"], ratio, "raw exact pair ratio")
        pairs.append(pair_record)
    a_times = [row["primary_ns"] for row in main_rows if row["arm"] == "A"]
    b_times = [row["primary_ns"] for row in main_rows if row["arm"] == "B"]
    med_a = statistics.median(a_times)
    med_b = statistics.median(b_times)
    median_pair = statistics.median(ratios)
    ratio_medians = Fraction(int(med_b), int(med_a))
    summary = original["summary"]
    check_fraction(summary["A_median_ns"], Fraction(int(med_a)), "raw A arm median")
    check_fraction(summary["B_median_ns"], Fraction(int(med_b)), "raw B arm median")
    check_fraction(summary["median_pair_ratio"], median_pair, "exact median paired ratio")
    check_fraction(summary["ratio_of_medians"], ratio_medians, "exact ratio of arm medians")
    main_attempts = sum(row["render_attempts"] for row in main_rows)
    control_attempts = sum(row["render_attempts"] for row in controls)
    check(main_attempts == summary["main_render_attempts"] == 48 and
          control_attempts == summary["control_render_attempts"] == 10,
          "formal main/control render attempts")
    old = load(BATCH.with_name("m4_active_coverage_002") / "RESULTS.json")
    old_attempts = 0
    for old_row in old["rows"] + old["controls"]:
        if "output_directory" not in old_row:
            check(old_row["status"] == "not_run", "002 unstarted entry has no output")
            continue
        trace_path = Path(old_row["output_directory"]) / "TRACE.jsonl"
        if trace_path.exists():
            events = [json.loads(line) for line in read(trace_path).splitlines()]
            old_ids = [event["attempt_id"] for event in events if event["event"] == "render_attempt"]
            check(len(set(old_ids)) == len(old_ids), "002 unique prior attempt identifiers")
            old_attempts += len(old_ids)
    check(old_attempts == summary["historical_002_render_attempts"] == 6, "six preserved failed 002 attempts")
    check(main_attempts + control_attempts == summary["new_render_attempts"] == 58 and
          main_attempts + control_attempts + old_attempts == summary["cross_002_003_render_attempts"] == 64,
          "cross-batch all-attempt ledger")
    check(main_attempts <= plan["limits"]["main_render_attempts"] and
          control_attempts <= plan["limits"]["control_render_attempts"] and
          main_attempts + control_attempts <= plan["limits"]["all_render_attempts_including_preparation_and_failures"],
          "frozen render caps")
    setup_ns = interval(original["common_parent_setup"], "common parent setup")
    whole_ns = original["batch_closed_before_publication_ns"] - original["batch_started_ns"]
    check(whole_ns == original["whole_batch_through_analysis_ns"], "whole batch subtraction")
    check(original["batch_started_ns"] <= original["common_parent_setup"]["started_ns"] <=
          original["common_parent_setup"]["closed_ns"] <= rows[0]["started_ns"] and
          rows[-1]["closed_ns"] <= original["batch_closed_before_publication_ns"], "whole batch enclosing boundaries")
    primary_sum = sum(row["primary_ns"] for row in rows)
    other_batch_ns = whole_ns - setup_ns - primary_sum
    check(other_batch_ns >= 0, "whole batch residual nonnegative")
    q = recount_qualification(qualification, frozen, original["batch_started_ns"])
    check(original["qualification_cost_separate"] == qualification["timing"], "qualification separately quoted interval")
    grouped = {scenario + "_" + arm: aggregate([row for row in rows if row["scenario"] == scenario and row["arm"] == arm])
               for scenario in ("main", "pixel_shortfall") for arm in ("A", "B")}
    arm_totals = {arm: aggregate([row for row in rows if row["arm"] == arm]) for arm in ("A", "B")}
    result = {"schema": "m4-active-coverage-003-cost-review-v1", "status": "passed",
              "review_kind": "author-side independent standard-library evidence and arithmetic audit",
              "administrator_review": original["administrator_review"], "checks_passed": CHECKS,
              "source_preparation_commit": "ca33b639", "frozen_source_count": len(frozen["runtime_sources"]),
              "source_manifest_sha256": original["freeze_sha256"],
              "script_sha256": digest(Path(__file__).read_bytes()), "pairs": pairs,
              "A_median_ns": med_a, "B_median_ns": med_b,
              "median_pair_ratio": fraction_record(median_pair), "ratio_of_medians": fraction_record(ratio_medians),
              "formal_run_count": 12, "control_run_count": 2, "strict_PID_cleanup_confirmed": 14,
              "main_render_attempts": main_attempts, "control_render_attempts": control_attempts,
              "qualification_render_attempts": 0, "old_002_render_attempts": old_attempts,
              "cross_002_003_render_attempts": main_attempts + control_attempts + old_attempts,
              "qualification": q, "grouped": grouped, "arm_totals_including_control": arm_totals,
              "all_formal_and_control": aggregate(rows), "rows": rows,
              "batch": {"started_ns": original["batch_started_ns"],
                        "closed_before_final_publication_ns": original["batch_closed_before_publication_ns"],
                        "whole_batch_ns": whole_ns, "common_parent_setup_ns": setup_ns,
                        "primary_intervals_sum_ns": primary_sum, "other_inclusive_batch_work_ns": other_batch_ns,
                        "qualification_plus_formal_measured_intervals_ns": q["including_RESULTS_publication_ns"] + whole_ns,
                        "gap_after_qualification_before_formal_ns": original["batch_started_ns"] -
                            q["final_timing"]["closed_ns"]},
              "scope": {"primary": original["timing_scope"],
                        "batch": original["controller_bootstrap_scope"],
                        "cold_scope": plan["time_contract"]["cold_scope"],
                        "text_bytes": "UTF-8 result, publication, TRACE and frame JSON plus stdout/stderr files.",
                        "array_payload": "Uncompressed .npy data bytes decoded and hashed from existing NPZ. RSS unmeasured.",
                        "model_consumption": "No model/provider/Blender/API test. Local PNG receipts only.",
                        "audit_method": "Existing JSON/JSONL, raw file bytes and .npy headers only. No experiment or product imports.",
                        "unknown": ["Controller process startup, stdlib imports and initial FROZEN read",
                                    "Final batch summary and qualification FINAL_TIMING self-publication",
                                    "RSS, OS cache cold-start effects, GPU costs and model task benefit",
                                    "Other geometry, camera pools, environments or production entry points"]},
              "inputs_sha256": dict(sorted(INPUTS.items()))}
    (HERE / "RESULTS.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(result)
    print(json.dumps({"status": result["status"], "checks_passed": CHECKS,
                      "median_pair_ratio": float(median_pair), "ratio_of_medians": float(ratio_medians),
                      "whole_batch_seconds": whole_ns / 1e9, "qualification_seconds": q["elapsed_ns"] / 1e9}))


def write_report(result):
    lines = ["# M4-ACTIVE-COVERAGE-003 独立成本复算", "",
             f"标准库离线复算通过 {result['checks_passed']} 项。冻结的 158 份来源逐份哈希一致。管理员终审状态为 {result['administrator_review']}。本记录为作者侧独立算术和证据核对。", "",
             "## 配对与完整时界", "",
             "12 个主场景按预注册的 AB、BA 交替顺序完成，两个控制场景完成。14 个业务子进程均核对原始 PID、退出、回收、三条管道和原句柄关闭。", "",
             "| 配对 | 顺序 | A 毫秒 | B 毫秒 | B/A |", "|---|---|---:|---:|---:|"]
    for pair in result["pairs"]:
        lines.append(f"| {pair['pair']} | {pair['order']} | {pair['A_ns']/1e6:.4f} | {pair['B_ns']/1e6:.4f} | {pair['B_over_A']['value']:.10f} |")
    lines += ["", f"A 中位数为 {result['A_median_ns']/1e6:.5f} 毫秒，B 为 {result['B_median_ns']/1e6:.5f} 毫秒。六个配对比值的中位数为 {result['median_pair_ratio']['value']:.10f}，约减少 {(1-result['median_pair_ratio']['value'])*100:.4f}%。两组中位数之比为 {result['ratio_of_medians']['value']:.10f}。精确有理数保存在 RESULTS.json。", ""]
    batch = result["batch"]
    lines += [f"主窗口从 {batch['started_ns']} 到 {batch['closed_before_final_publication_ns']}，完整批次为 {batch['whole_batch_ns']/1e9:.7f} 秒。其中公共父侧准备为 {batch['common_parent_setup_ns']/1e6:.4f} 毫秒，14 个完整子进程及回读窗口合计 {batch['primary_intervals_sum_ns']/1e9:.7f} 秒，其余登记、完整性检查、进度及汇总开销合计 {batch['other_inclusive_batch_work_ns']/1e6:.4f} 毫秒。", "",
              "每个主计时从 Popen 前起，覆盖子进程启动和导入、计算、全部生成文件、退出、清理，以及父侧完整回读校验。子阶段与回执发布时间已单独保存，它们位于主窗口内。批次窗口外的控制器启动、标准库导入、首次冻结清单读取，以及最终批次汇总自发布仍未计时。", "",
              "## 计数和控制反馈", "",
              f"主场景实际生成 {result['main_render_attempts']} 张图，控制场景实际生成 {result['control_render_attempts']} 张图。四个资格进程生成 0 张。加上保留的 002 失败轮 6 次尝试，累计为 {result['cross_002_003_render_attempts']} 次。每个主场景 A 生成 6 张、36 行像素判定，B 生成 2 张、12 行像素判定。两组实际覆盖均为 5/6，几何候选池未覆盖 1 个，相同状态重查新增 0 张。", ""]
    for row in result["rows"]:
        if row["scenario"] == "pixel_shortfall":
            lines.append(f"控制 {row['arm']} 的实际视图顺序为 {' → '.join(row['views'])}，每步新增覆盖为 {' / '.join(str(step['new_count']) for step in row['feedback'])}。历史像素不足 {len(row['history_shortfall_roi_ids'])} 个，最终像素不足 {len(row['final_shortfall_roi_ids'])} 个，终态覆盖 {len(row['covered_roi_ids'])}/6。")
            lines.append("")
    lines += ["控制 B 的 BACK 具有真实几何完整但像素不足的目标，后续视图把这些目标全部补回。A/B 终态集合逐项一致。候选视角池尚不能完整观察的 1 个目标保留为未解决。", "",
              "## 磁盘字节与数组载荷", "",
              "下表按实际生成文件计数。文字包含结果、发布回执、TRACE、帧元数据和 stdout/stderr。原始数组载荷从 NPZ 内 .npy 数据区解出后逐份哈希，它与内存峰值具有不同计量含义。", "",
              "| 场景/组 | PNG | NPZ | 帧元数据 | RESULT | TRACE | 发布回执 | 全部文字 | 原始数组载荷 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for key, group in result["grouped"].items():
        size = group["bytes"]
        lines.append(f"| {key} | {size['PNG_bytes']} | {size['NPZ_bytes']} | {size['frame_metadata_bytes']} | {size['RESULT_bytes']} | {size['TRACE_bytes']} | {size['publication_bytes']} | {size['text_bytes']} | {size['array_payload_bytes']} |")
    lines += ["", "逐组、含控制的逐 arm 合计、14 轮总计、每轮离散时段、各 child stage 与 RESULT 发布成本均在 RESULTS.json 中。磁盘文件总量由完整目录清单复算。", "",
              "## 启动资格成本", "",
              f"四个资格结果按预期处理，汇总发布前窗口为 {result['qualification']['elapsed_ns']/1e9:.7f} 秒，包含 RESULTS 写关后的窗口为 {result['qualification']['including_RESULTS_publication_ns']/1e9:.7f} 秒。FINAL_TIMING 自发布仍在其窗口外。资格与正式批次独立列账，后一个资格窗口与正式批次相加为 {batch['qualification_plus_formal_measured_intervals_ns']/1e9:.7f} 秒。两者之间间隔另列，包含审查与准备，未记作连续运算时间。", "",
              "| 资格 | 原始 PID | 子退出码 | 子阶段 | 回执有效 | 标记动作 | 完整资格毫秒 |", "|---|---:|---:|---|---|---:|---:|"]
    for case in result["qualification"]["cases"]:
        lines.append(f"| {case['scenario']} | {case['actual_pid']} | {case['child_exit_code']} | {case['child_phase']} | {case['receipt_valid']} | {case['marker_actions']} | {case['full_case_ns']/1e6:.4f} |")
    lines += ["", "normal 完成。nonzero 保留预期异常，timeout 保留等待后超时并回收，receipt_failure 保留执行一次标记后缺失回执的状态。四项资格验收通过，累计只有 1 次受控标记动作。", "",
              "## 适用范围与待证内容", "",
              "结果限于本次固定几何、有限相机池、512 像素尺寸和登记环境。每轮使用新进程与空应用图像缓存，操作系统缓存保持原状。当前记录证明实际像素反馈、有限池回补及这组完整计时的净收益。", "",
              "尚未测量模型消费与任务质量、生产入口整体收益、RSS、GPU、其他资产及相机池。图片回执止于本地 PNG 文件，尚无模型读取证明。本复算仅读既有记录，没有新增渲染、产品调用或子进程试验。", ""]
    (HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
