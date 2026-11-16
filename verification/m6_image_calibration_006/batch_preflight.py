"""Pure fixtures for batch state, disk-reopen calls and receipt recovery."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import calibrator
import calibration_batch
from calibration_preflight import absolute_descriptors, fixture_environment
from common import identity, read, write
import numpy as np


def main():
    started, cpu = time.perf_counter(), time.process_time()
    output = HERE / "private/batch_preflight" / uuid.uuid4().hex[:6]
    output.mkdir(parents=True)
    source = absolute_descriptors(read("SOURCE_BINDING.json"))
    checks, expected_errors = {}, []
    counters = dict(batch_launches=0, opens=[], invocations=[], measurements=[], fail_read=False, fail_consumed=False)
    fake_bpy = SimpleNamespace(data=SimpleNamespace(filepath=""))

    def fake_open(*, filepath):
        fake_bpy.data.filepath = filepath
        counters["opens"].append(filepath)

    fake_bpy.ops = SimpleNamespace(wm=SimpleNamespace(open_mainfile=fake_open))
    sys.modules["bpy"] = fake_bpy
    import batch_worker

    def check(name, passed):
        checks[name] = bool(passed)

    def reject(name, action):
        try:
            action()
        except (ValueError, RuntimeError, FileNotFoundError) as error:
            expected_errors.append(dict(name=name, type=type(error).__name__, message=str(error)))
            check(name, True)
        else:
            check(name, False)

    def fake_invoke(script, job_path):
        job = batch_worker.read(job_path)
        kind = Path(script).stem.removeprefix("blender_")
        counters["invocations"].append(dict(kind=kind, job=str(job_path), PID=os.getpid()))
        execution = dict(script=batch_worker.file_identity(script))
        if kind == "edit":
            destination = Path(job["output_blend"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise FileExistsError("fixture_edit_attempted_to_overwrite_saved_output")
            shutil.copyfile(job["current_blend"], destination)
            receipt = dict(status="saved", input_blend=batch_worker.file_identity(job["current_blend"]),
                output_blend=batch_worker.file_identity(destination), submitted_payload=batch_worker.file_identity(job["edit_payload"]), execution=execution)
        elif kind == "read":
            with np.load(job["base_npz"], allow_pickle=False) as archive:
                arrays = {key: archive[key].copy() for key in ("vertices", "vertices_world", "vertices_local", "matrix_world", "faces", "source_ids", "poly_offsets", "poly_vertices", "triangle_polygon_ids")}
            directory = Path(job["current_blend"]).parents[2]
            with np.load(directory / "payloads/scaled.npz", allow_pickle=False) as payload:
                ids, values = payload["source_ids"], payload["displacements_world"]
            inverse = np.linalg.inv(arrays["matrix_world"])
            requested = arrays["vertices_world"][ids] + values
            arrays["vertices_local"][ids] = (requested @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
            native = arrays["vertices_local"].astype(np.float64)
            homogeneous = np.column_stack((native, np.ones(len(native))))
            arrays["vertices"] = arrays["vertices_world"] = (arrays["matrix_world"] @ homogeneous.T).T[:, :3]
            path = Path(job["readback_npz"])
            if path.exists():
                raise FileExistsError("fixture_read_attempted_to_overwrite_prior_packet")
            np.savez_compressed(path, **arrays)
            shutil.copyfile(source["initial"]["scene"]["path"], job["scene_signature_json"])
            Path(job["local_obj"]).write_text("# Identity-only batch fixture OBJ\n", encoding="utf8")
            if counters["fail_read"] and not counters["fail_consumed"]:
                counters["fail_consumed"] = True
                raise RuntimeError("fixture_read_output_before_receipt_failure")
            receipt = dict(status="read_actual_saved_blend", input_blend=batch_worker.file_identity(job["current_blend"]),
                input_unchanged=True, writer_arrays_or_receipts_read=False, readback_npz=batch_worker.file_identity(path),
                scene_signature_json=batch_worker.file_identity(job["scene_signature_json"]), execution=execution)
        else:
            directory = Path(job["output_dir"])
            directory.mkdir(parents=True, exist_ok=False)
            rows = []
            by_view = {row["role"].removeprefix("current_"): row for row in source["images"]["current"]}
            for specification in job["views"]:
                view = specification["name"]
                destination = directory / (view + ".png")
                destination.write_bytes(("Identity-only mocked PNG " + view).encode())
                rows.append(dict(by_view[view]["camera"], image=batch_worker.file_identity(destination)))
            receipt = dict(status="rendered_actual_saved_full_character", current_blend=batch_worker.file_identity(job["current_blend"]),
                scene_changes_saved=False, geometry_scale=1., displacement_scale=1., views=rows, execution=execution)
        batch_worker.write(job["receipt_path"], receipt)

    def fake_run_job(script, job, label, timeout_s=0):
        counters["batch_launches"] += 1
        folder = calibrator.HERE / "private/jobs" / label
        folder.mkdir(parents=True)
        full_job = dict(job, receipt_path=str(folder / "receipt.json"))
        batch_worker.write(folder / "job.json", full_job)
        process_path = calibrator.HERE / "private/processes" / ("b_" + label + ".json")
        try:
            result = batch_worker.execute(full_job)
            batch_worker.write(full_job["receipt_path"], result)
        except BaseException:
            calibrator.write(process_path, dict(status="failed", returncode=23, pid=os.getpid(), scope="Mocked process record"))
            raise
        calibrator.write(process_path, dict(status="completed", returncode=0, pid=os.getpid(), scope="Mocked process record"))
        return dict(receipt=result)

    def fake_quality(*args, **kwargs):
        return dict(status="pass", checks={}, geometry={}, displacement={}, transition={}, identity={})

    def fake_measure(reference, candidate, *, output_dir=None, cache=None):
        counters["measurements"].append(id(cache))
        path = Path(output_dir) / "RGB.npz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"Identity-only RGB fixture")
        return dict(status="pass", absolute_error_sum=10, sample_count=3686400, decoded_RGB_npz=calibrator.identity(path))

    old_invoke = batch_worker.invoke
    old_run, old_measure, old_quality = calibrator.run_job, calibrator.measure_images, calibration_batch.evaluate_packets
    batch_worker.invoke = fake_invoke
    calibrator.run_job, calibrator.measure_images, calibration_batch.evaluate_packets = fake_run_job, fake_measure, fake_quality
    try:
        fixture = output / "unit"
        with fixture_environment(fixture, source):
            for name in calibration_batch.EXTRA_SOURCES:
                (fixture / name).write_text("# Identity-only batch backend fixture\n", encoding="utf8")
            request = calibrator.request_for("v1_native", "v2")
            first = calibration_batch.calibrate(request)
            check("cold_one_owned_process_request", counters["batch_launches"] == 1)
            check("cold_three_writes_reads_renders", [sum(row["kind"] == kind for row in counters["invocations"]) for kind in ("edit", "read", "render")] == [3, 3, 3])
            check("each_step_disk_reopen_called", len(counters["opens"]) == 9)
            check("fixed_alpha_order", [row["alpha"] for row in first["result"]["candidates"]] == [0., .5, 1.])
            check("exact_image_tie_smaller_alpha", first["result"]["selected_alpha"] == 0.)
            check("shared_per_request_RGB_cache", len(set(counters["measurements"])) == 1)
            check("all_native_payload_reconstructions_pass", all(row["native_verification"]["status"] == "pass" for row in first["result"]["candidates"]))
            check("all_three_sessions_version_one", all(calibrator.read(calibrator.session_directory("v2", "v1_native", tag) / "session.json")["version"] == 1 for tag in calibrator.TAGS))
            check("reader_writer_PID_recorded", all(row["operation"]["writer_PID"] == row["operation"]["reader_PID"] == os.getpid() for row in first["result"]["candidates"]))
            check("disk_reopen_separate_from_fresh_process", all(row["operation"]["fresh_disk_reopen"] and row["operation"]["fresh_process"] is False for row in first["result"]["candidates"]))
            before = copy.deepcopy(counters)
            warm = calibration_batch.calibrate(request)
            check("warm_zero_process_and_decode", counters == before and warm["reused"] and warm["new_Blender_jobs"] == 0)
            check("warm_same_result_identity", warm["result_reference"] == first["result_reference"])
            status = calibration_batch.status(request)
            check("status_reads_completed_batch", status["batch_state"]["status"] == "complete")
            worker_file = fixture / "batch_worker.py"
            original = worker_file.read_bytes()
            worker_file.write_bytes(original + b"# changed source\n")
            reject("changed_worker_rejected_before_execution", lambda: calibration_batch.calibrate(request))
            reject("changed_worker_status_binding_rejected", lambda: calibration_batch.status(request))
            worker_file.write_bytes(original)
            image = calibrator.checked_identity(first["result"]["candidates"][0]["images"][0])
            original_png = image.read_bytes()
            image.write_bytes(original_png + b"changed")
            reject("changed_candidate_image_rejected_on_reuse", lambda: calibration_batch.calibrate(request))
            image.write_bytes(original_png)
            counters.update(fail_read=True, fail_consumed=False)
            partial_request = calibrator.request_for("v2_facts", "v2")
            before_launch = counters["batch_launches"]
            reject("partial_read_failure_preserves_actual_state", lambda: calibration_batch.calibrate(partial_request))
            check("same_call_never_blind_retries_batch", counters["batch_launches"] == before_launch + 1)
            partial_status = calibration_batch.status(partial_request)
            check("status_preserves_partial_worker_state", partial_status["batch_state"]["status"] == "partial_query_owned_state")
            batch_directory = fixture / "private/calibrations/v2_v2_facts"
            prior_attempt = calibrator.read(batch_directory / "BATCH_ATTEMPT.json")
            process_path = fixture / "private/processes" / ("b_" + prior_attempt["job_label"] + ".json")
            process_bytes = process_path.read_bytes()
            calibrator.write(process_path, dict(status="running", pid=987654))
            old_query = calibration_batch._query_process
            owned_job = str(fixture / "private/jobs" / prior_attempt["job_label"] / "job.json")
            calibration_batch._query_process = lambda pid: dict(found=True, pid=pid, command_line="blender.exe --job " + owned_job)
            before_live_guard = counters["batch_launches"]
            reject("live_prior_worker_blocks_new_batch", lambda: calibration_batch.calibrate(partial_request))
            check("live_guard_prevents_second_process", counters["batch_launches"] == before_live_guard)
            calibrator.write(process_path, dict(status="running"))
            reject("missing_monitor_PID_uses_matching_worker_state", lambda: calibration_batch._ensure_prior_exit(batch_directory))
            calibration_batch._query_process = lambda pid: dict(found=False, pid=pid)
            calibration_batch._ensure_prior_exit(batch_directory)
            check("matching_worker_PID_confirmed_exit_allows_resume", True)
            calibrator.write(process_path, dict(status="running", pid=987654))
            calibration_batch._query_process = lambda pid: dict(found=True, pid=pid, command_line="other.exe unrelated_job")
            calibration_batch._ensure_prior_exit(batch_directory)
            check("PID_reuse_with_other_command_records_prior_exit", True)
            calibration_batch._query_process = old_query
            process_path.write_bytes(process_bytes)
            first_entry = partial_status["batch_state"]["candidates"]["a0"]
            failed_packet = Path(first_entry["read"]["receipt_path"]).parent / "readback.npz"
            failed_sha = hashlib.sha256(failed_packet.read_bytes()).hexdigest()
            failed_model = Path(calibrator.session_directory("v2", "v2_facts", "a0") / "versions/001/model.blend")
            model_sha = hashlib.sha256(failed_model.read_bytes()).hexdigest()
            edit_count = sum(row["kind"] == "edit" for row in counters["invocations"])
            resumed = calibration_batch.calibrate(partial_request)
            check("resume_completes_same_three_candidates", all(row["status"] == "complete" for row in resumed["result"]["candidates"]))
            check("resume_does_not_rewrite_saved_first_model", sum(row["kind"] == "edit" for row in counters["invocations"]) == edit_count + 2 and hashlib.sha256(failed_model.read_bytes()).hexdigest() == model_sha)
            check("failed_packet_bytes_preserved", failed_packet.exists() and hashlib.sha256(failed_packet.read_bytes()).hexdigest() == failed_sha)
            resumed_first = resumed["result"]["candidates"][0]
            check("read_recovery_uses_next_attempt_directory", Path(resumed_first["readback"]["path"]).parent.name == "read01")
            check("partial_attempt_history_retained", len(calibration_batch.status(partial_request)["batch_state"]["candidates"]["a0"]["retired_attempts"]) >= 1)
            entry = calibration_batch.status(partial_request)["batch_state"]["candidates"]["a0"]
            candidate = dict(directory=str(calibrator.session_directory("v2", "v2_facts", "a0")),
                output_blend=str(failed_model), initial_blend=source["initial"]["blend"], payload=entry["edit"].get("payload", {}))
            direct_state = dict(candidates={})
            recovered_entry = {}
            zero = dict(worker_invocations=dict(edit=0, read=0, render=0), reused_steps=0, recovered_saved_outputs=0)
            batch_worker.run_step("edit", candidate, recovered_entry, direct_state, fixture / "saved_recovery.json", {}, zero)
            check("saved_model_without_receipt_is_retained_for_read_validation", recovered_entry["edit"]["status"] == "saved_receipt_missing" and zero["recovered_saved_outputs"] == 1)
    finally:
        batch_worker.invoke = old_invoke
        calibrator.run_job, calibrator.measure_images, calibration_batch.evaluate_packets = old_run, old_measure, old_quality
    result = dict(cycle_id="M6-IMAGE-CALIBRATION-006", status="pass" if all(checks.values()) else "fail", checks=checks,
        passed=sum(checks.values()), total=len(checks), expected_errors=expected_errors,
        scope="Pure state/geometry fixtures with mocked Blender operations and identity-only PNG/quality data. Actual Blender equivalence is evaluated separately.",
        counters=counters, source_identities=[identity(HERE / name) for name in ("calibration_batch.py", "batch_worker.py", "batch_preflight.py")],
        evidence_directory=str(output.relative_to(HERE)), wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
        actual_Blender_calls=0, actual_Pro_calls=0)
    write(output / "RESULT.json", result)
    write("BATCH_PREFLIGHT.json", result)
    print(json.dumps({key: result[key] for key in ("status", "passed", "total", "wall_s")}))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
