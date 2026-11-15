"""Independently reopen final saved consumer files and score private restoration."""

import argparse
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from delivery_common import (absolute, ensure_job, existing_job, job_cost, merge_index,
                             session_names, snapshot_session, verify_identity, verify_snapshot)
from evaluate import evaluate_packets, packet
from score import score_packet

READBACK_KEYS = ("vertices", "vertices_world", "vertices_local", "matrix_world", "faces", "source_ids",
                 "poly_offsets", "poly_vertices", "triangle_polygon_ids")


def read_job(state, snapshot, output):
    spec = read(absolute(state["source_spec"]))
    return dict(current_blend=str(absolute(state["current_blend"])), object_name=spec["object_name"],
        source_original=spec["source_original"], expected_input_sha256=snapshot["saved_blend"]["sha256"],
        base_npz=str(absolute(state["initial_npz"])), readback_npz=str(output / "readback.npz"),
        scene_signature_json=str(output / "scene.json"), local_obj=str(output / "local.obj"))


def verify_result(result, snapshot, state, output):
    if result["snapshot"] != snapshot:
        raise ValueError("final_verification_snapshot_changed_" + snapshot["session"])
    verify_snapshot(snapshot)
    for expected in result["artifacts"].values():
        verify_identity(expected)
    existing_job("blender_read.py", read_job(state, snapshot, output), result["job_label"])
    return result


def verify_session(name):
    started, cpu = time.perf_counter(), time.process_time()
    state, snapshot = snapshot_session(name)
    output = HERE / "private/final_verify" / name
    result_path = output / "AUDIT.json"
    if result_path.exists():
        result = verify_result(read(result_path), snapshot, state, output)
        return result, True
    output.mkdir(parents=True, exist_ok=True)
    label = "final_verify_" + name
    record, reused_job = ensure_job("blender_read.py", read_job(state, snapshot, output), label)
    receipt = record["receipt"]
    spec = read(absolute(state["source_spec"]))
    quality = evaluate_packets(absolute(state["initial_npz"]), output / "readback.npz", absolute(state["initial_npz"]),
        absolute(state["source_spec"]), before_state_path=absolute(spec["baseline_scene"]), after_state_path=output / "scene.json")
    write(output / "QUALITY.json", quality)
    binding = read("CASE_BINDING.json")
    verify_identity(binding["private_score_target"])
    verify_identity(binding["public_initial"])
    target = absolute(binding["private_score_target"]["path"])
    scored = score_packet(output / "readback.npz", target, output / "SCORE.json", receipt_path=absolute(record["receipt_path"]))
    exported = packet(output / "readback.npz")
    final_consumer = packet(absolute(state["current_npz"]))
    checks = {}
    for key in READBACK_KEYS:
        first, second = exported[key], final_consumer[key]
        checks["fresh_readback_matches_consumer_" + key] = bool(first.shape == second.shape and first.dtype == second.dtype
                                                               and first.tobytes() == second.tobytes())
    checks.update(fresh_process_actual_saved_blocks=bool(receipt["input_unchanged"]
                  and receipt["writer_arrays_or_receipts_read"] is False and record["process"]["returncode"] == 0),
        saved_blend_matches_final_session=receipt["input_blend"]["sha256"] == snapshot["saved_blend"]["sha256"],
        scoring_verified_actual_saved_provenance=scored["provenance"]["independent_saved_readback_verified"] is True,
        original_damaged_initial_matches_binding=snapshot["initial_packet"]["sha256"] == binding["public_initial"]["sha256"])
    verify_snapshot(snapshot)
    checks["session_and_saved_file_preserved"] = True
    artifacts = dict(fresh_readback=identity(output / "readback.npz"), scene=identity(output / "scene.json"),
        local_OBJ=identity(output / "local.obj"), quality=identity(output / "QUALITY.json"),
        private_score=identity(output / "SCORE.json"), private_points=identity(output / "SCORE_points.npz"),
        reader_receipt=identity(absolute(record["receipt_path"])), job=identity(HERE / "private/jobs" / label / "run.json"),
        private_target=identity(target))
    result = dict(session=name, stage=snapshot["stage"], route=snapshot["route"], version=state["version"],
        audit_status="pass" if all(checks.values()) else "fail", checks=checks, snapshot=snapshot, artifacts=artifacts,
        technical_status=quality["status"], restoration_quality_pass=scored["restoration_quality_pass"],
        geometry_changed_vertices=quality["displacement"]["changed_vertices"],
        quality_checks=scored["checks"], metrics=scored["metrics"], normal_editable_misedit=scored["normal_editable_misedit"],
        transition=quality["transition"], geometry=quality["geometry"], depth_and_axis_observations=scored["depth_and_axis_observations"],
        saved_model=snapshot["saved_blend"], job_label=label, Blender_cost=job_cost(record),
        job_reused_at_first_evaluation=reused_job, wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        score_input="Fresh independent export of this session's last actual saved blend", actual_Pro_calls=0)
    write(result_path, result)
    return result, reused_job


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2", "all"), required=True)
    args = parser.parse_args()
    started, cpu = time.perf_counter(), time.process_time()
    rows, reused, new_jobs = [], [], []
    for name in session_names(args.stage):
        result, cached = verify_session(name)
        rows.append(result)
        (reused if cached else new_jobs).append(result["job_label"])
        print(name, result["audit_status"], "technical", result["technical_status"],
              "restoration", result["restoration_quality_pass"], flush=True)
    combined = merge_index(HERE / "FINAL_VERIFICATION.json", args.stage, rows)
    summary = dict(cycle_id="M6-MATCHED-REFINE-003", stage=args.stage,
        status="pass" if all(row["audit_status"] == "pass" for row in combined) else "fail", sessions=combined,
        new_Blender_reads=len(new_jobs), new_job_labels=new_jobs, reused_job_labels=reused,
        unique_Blender_read_labels=[row["job_label"] for row in combined],
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        unique_nested_Blender_wall_s=sum(row["Blender_cost"]["wall_s"] for row in combined), actual_Pro_calls=0,
        source_identities=[identity(HERE / name) for name in ("independent_verify.py", "delivery_common.py", "blender_read.py", "evaluate.py", "quality.py", "score.py")])
    write("FINAL_VERIFICATION_" + args.stage + ".json", summary)
    write("FINAL_VERIFICATION.json", summary)
    if summary["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
