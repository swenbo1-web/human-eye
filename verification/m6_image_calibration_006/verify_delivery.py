"""Verify actual calibration evidence while preserving restoration outcomes."""

import argparse
import ast
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from evaluate import packet
import numpy as np


def absolute(value):
    path = Path(value)
    return path if path.is_absolute() else HERE / path


def same_array(first, second):
    return first.dtype == second.dtype and first.shape == second.shape and first.tobytes() == second.tobytes()


def verify():
    started, cpu = time.perf_counter(), time.process_time()
    checks = []

    def check(name, passed):
        checks.append(dict(name=name, passed=bool(passed)))

    def bound_file(name, expected):
        actual = identity(absolute(expected["path"]))
        check(name, actual["sha256"] == expected["sha256"] and actual["bytes"] == expected["bytes"])
        return absolute(expected["path"])

    for row in read("PLAN_FREEZE.json")["files"]:
        bound_file("fixed input " + row["path"], row)
    for stage in ("v1", "v2"):
        for row in read("TOOL_FREEZE_" + stage + ".json")["files"]:
            bound_file(stage + " exact runtime archive " + row["path"], row["archived"])
            if stage == "v2":
                bound_file("final runtime " + row["path"], row)
    for name in ("STAGE_V1_SNAPSHOT.json", "STAGE_V1_SCORING_SNAPSHOT.json"):
        snapshot = read(name)
        for row in snapshot["files"]:
            bound_file(name + " " + row["path"], row)
        check(name + " file count", len(snapshot["files"]) == snapshot["file_count"])
    source = read("SOURCE_BINDING.json")
    bound_file("original asset", source["original"])
    for name, row in source["initial"].items():
        bound_file("fixed initial " + name, row)
    initial = packet(absolute(source["initial"]["packet"]["path"]))
    proposals = {row["proposal_id"]: row for row in source["proposals"]}
    for proposal in proposals.values():
        bound_file("fixed proposal copy " + proposal["proposal_id"], proposal["payload"])
        bound_file("fixed original proposal " + proposal["proposal_id"], proposal["source_payload"])
    outcomes, candidate_count = [], 0
    for stage in ("v1", "v2"):
        scored = read("CALIBRATION_SCORES_" + stage + ".json")
        check(stage + " independent scorer integrity", scored["status"] == "pass")
        check(stage + " six private scores", len(scored["candidates"]) == 6)
        by_candidate = {(row["proposal_id"], row["alpha"]): row for row in scored["candidates"]}
        for proposal_id, proposal in proposals.items():
            result_name = "CALIBRATION_" + stage + "_" + proposal_id + ".json"
            result = read(result_name)
            freeze = read("IMAGE_SELECTION_FREEZE_" + stage + "_" + proposal_id + ".json")
            result_path = bound_file(stage + " " + proposal_id + " image result", freeze["image_result"])
            check(stage + " " + proposal_id + " result path", result_path.resolve() == (HERE / result_name).resolve())
            check(stage + " " + proposal_id + " selection precedes private score", freeze["frozen_epoch"] <= scored["private_scoring_started_epoch"])
            check(stage + " " + proposal_id + " image-only selector", freeze["private_target_read_by_calibrator"] is False)
            check(stage + " " + proposal_id + " binding", result["binding_sha256"] == freeze["binding_sha256"])
            check(stage + " " + proposal_id + " coefficients", [row["alpha"] for row in result["candidates"]] == [0., .5, 1.])
            check(stage + " " + proposal_id + " new Pro zero", result["actual_Pro_calls"] == 0)
            check(stage + " " + proposal_id + " training/API zero", result["training_calls"] == result["paid_API_calls"] == 0)
            original_payload = packet(absolute(proposal["payload"]["path"]))
            ids, original_delta = original_payload["source_ids"], original_payload["displacements_world"]
            inverse = np.linalg.inv(initial["matrix_world"])
            for candidate in result["candidates"]:
                candidate_count += 1
                alpha = candidate["alpha"]
                prefix = stage + " " + proposal_id + " alpha" + str(alpha)
                paths = {name: bound_file(prefix + " " + name, candidate[name]) for name in
                    ("saved_blend", "payload", "readback", "scene", "quality", "reader_receipt", "render_receipt", "render_run")}
                for row in candidate["images"]:
                    bound_file(prefix + " image " + row["role"], row)
                bound_file(prefix + " raw decoded RGB", candidate["image"]["decoded_RGB_npz"])
                payload, actual = packet(paths["payload"]), packet(paths["readback"])
                check(prefix + " original source IDs", same_array(payload["source_ids"], ids))
                check(prefix + " exact scalar proposal", same_array(payload["displacements_world"], alpha * original_delta))
                if alpha == 1.:
                    check(prefix + " original payload bytes", paths["payload"].read_bytes() == absolute(proposal["payload"]["path"]).read_bytes())
                requested = initial["vertices_world"][ids] + alpha * original_delta
                expected_native = initial["vertices_local"].copy()
                expected_native[ids] = (requested @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
                check(prefix + " exact requested native float32", same_array(actual["vertices_local"], expected_native))
                outside = np.setdiff1d(initial["source_ids"], ids)
                check(prefix + " unsubmitted native points", same_array(actual["vertices_local"][outside], initial["vertices_local"][outside]))
                if alpha == 0.:
                    check(prefix + " alpha zero is initial", same_array(actual["vertices_local"], initial["vertices_local"]))
                for field in ("source_ids", "matrix_world", "poly_offsets", "poly_vertices", "faces", "triangle_polygon_ids"):
                    check(prefix + " native identity " + field, same_array(actual[field], initial[field]))
                reader, render = read(paths["reader_receipt"]), read(paths["render_receipt"])
                check(prefix + " reader actual file", reader["status"] == "read_actual_saved_blend" and reader["input_unchanged"] is True and
                    reader["writer_arrays_or_receipts_read"] is False and reader["input_blend"]["sha256"] == candidate["saved_blend"]["sha256"] and
                    reader["readback_npz"]["sha256"] == candidate["readback"]["sha256"])
                check(prefix + " renderer actual file", render["status"] == "rendered_actual_saved_full_character" and
                    render["current_blend"]["sha256"] == candidate["saved_blend"]["sha256"] and render["scene_changes_saved"] is False and
                    render["geometry_scale"] == render["displacement_scale"] == 1)
                check(prefix + " fixed image denominator", candidate["image"]["sample_count"] == 3686400)
                score = by_candidate[(proposal_id, alpha)]
                bound_file(prefix + " independently scored readback", score["artifacts"]["readback"])
                for artifact_name in ("quality", "score", "points"):
                    bound_file(prefix + " independent " + artifact_name, score["artifacts"][artifact_name])
                check(prefix + " technical result agreement", score["technical_status"] == candidate["technical_status"])
                outcomes.append(dict(stage=stage, proposal_id=proposal_id, alpha=alpha,
                    selected=score["selected"], technical_status=score["technical_status"], image=score["image"],
                    restoration_quality_pass=score["restoration_quality_pass"], restoration_checks=score["restoration_checks"],
                    support=score["metrics"]["support_47"], normal_editable_misedit=score["normal_editable_misedit"]))
            eligible = [row for row in result["candidates"] if row["technical_status"] == "pass" and row["image"]["status"] == "pass"]
            chosen = min(eligible, key=lambda row: (row["image"]["absolute_error_sum"], row["alpha"])) if eligible else None
            check(stage + " " + proposal_id + " exact selector and tie", result["selected_alpha"] == (chosen["alpha"] if chosen else None))
    check("twelve actual candidates", candidate_count == 12)
    comparison = read("CALIBRATION_COMPARISON.json")
    check("two-stage mathematical comparison", comparison["status"] == "pass")
    check("twenty-one exact RGBA comparisons", len(comparison["pixel_pairs"]) == 21 and all(row["RGBA_equal"] for row in comparison["pixel_pairs"]))
    for name in ("MIDPOINT_QA.json", "IMAGE_METRIC_PREFLIGHT.json", "CALIBRATION_PREFLIGHT.json"):
        check(name + " integrity pass", read(name)["status"] == "pass")
    clients = [read(path) for path in sorted((HERE / "private/protocol").rglob("RESULT.json"))]
    actual_clients = [row for row in clients if row.get("protocol_client") is True]
    check("actual protocol clients recorded", bool(actual_clients))
    check("protocol clients new Pro zero", all(row["actual_Pro_calls"] == 0 for row in actual_clients))
    for stage in ("v1", "v2"):
        for proposal_id in proposals:
            check(stage + " " + proposal_id + " actual protocol entrypoint", any(row.get("method") == "calibrate" and
                row["request"]["params"].get("stage") == stage and row["request"]["params"].get("proposal_id") == proposal_id and
                row.get("process_returncode") == 0 and "error" not in row["response"] for row in actual_clients))
    costs = read("COSTS.json")
    check("new Pro consumers zero", costs["new_Pro_consumers"] == 0)
    check("training API deployment zero", costs["training"] == costs["Google_API_calls"] == costs["new_paid_API_calls"] == costs["formal_deployment"] == 0)
    cleanup = read("PROCESS_CLEANUP.json")
    check("owned runtime processes absent", cleanup["query_succeeded"] and cleanup["owned_process_count"] == 0)
    for path in sorted(HERE.glob("*.py")):
        ast.parse(path.read_text(encoding="utf8"), filename=str(path))
        check("AST " + path.name, True)
    result = dict(cycle_id="M6-IMAGE-CALIBRATION-006", status="pass" if all(row["passed"] for row in checks) else "fail",
        checks=checks, passed=sum(row["passed"] for row in checks), total=len(checks), candidate_count=candidate_count,
        outcomes=outcomes, new_Pro_consumers=0, new_Blender_calls=0,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        scope="Input and source identity, actual protocol/save/read/render evidence and mathematical comparison. Technical, image and independent restoration outcomes retain separate fields.")
    write("DELIVERY_VERIFICATION.json", result)
    print({key: result[key] for key in ("status", "passed", "total", "candidate_count", "wall_s")})
    if result["status"] != "pass":
        raise SystemExit(1)


def manifest():
    files = [identity(path) for path in sorted(HERE.rglob("*"))
        if path.is_file() and path.name not in {"MANIFEST.json", "HANDOFF.json"}]
    write("MANIFEST.json", dict(cycle_id="M6-IMAGE-CALIBRATION-006", files=files,
        file_count=len(files), bytes=sum(row["bytes"] for row in files), original=read("SOURCE_BINDING.json")["original"],
        scope="All batch-local evidence except this manifest and ignored postcommit HANDOFF. Historical 005 and root midpoint evidence remain fixed external references."))
    print(dict(files=len(files), bytes=sum(row["bytes"] for row in files)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("verify", "manifest"), nargs="?", default="verify")
    {"verify": verify, "manifest": manifest}[parser.parse_args().action]()
