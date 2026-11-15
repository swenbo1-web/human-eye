"""Actual saved-Blender recovery after a reserved reader job fails prelaunch."""

import copy
import json
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job
from tool_preflight import prepare_session
import session_api
import numpy as np


def main():
    started, cpu = time.perf_counter(), time.process_time()
    source_paths = [HERE / name for name in ("recovery_regression.py", "session_api.py", "quality.py", "evaluate.py",
        "background.py", "blender_edit.py", "blender_read.py", "blender_common.py", "tool_preflight.py")]
    source_before = [identity(path) for path in source_paths]
    report = dict(status="running", checks={}, jobs=[], fault_attempts=[],
        Pro_calls=0, training_runs=0, requested_displacement="0.2h times frozen center normal, one source vertex")
    try:
        directory = prepare_session("recovery_preflight", "s01", "native")
        report["session_directory"] = str(directory)
        state = read(directory / "session.json")
        spec = read(state["source_spec"])
        original_identity = identity(spec["source_original"])
        initial_identity = identity(directory / "before.blend")
        with np.load(state["initial_npz"], allow_pickle=False) as package:
            initial = {name:package[name] for name in package.files}
        center = int(spec["center_source_id"])
        displacement = .2*float(spec["h"])*initial["n0"][center]
        payload = directory / "payloads/recovery_center.npz"
        payload.parent.mkdir()
        np.savez_compressed(payload, source_ids=np.array([center], dtype=np.int64), displacements_world=displacement[None, :])
        report["payload"] = identity(payload)
        report["center_source_id"] = center
        report["submitted_displacement_world"] = displacement.tolist()
        operation = "recover_reader_prelaunch_failure"

        def controlled_job(script_name, job, label, **kwargs):
            if script_name == "blender_read.py" and not report["fault_attempts"]:
                folder = HERE / "private/jobs" / label
                folder.mkdir(parents=True, exist_ok=False)
                saved_job = dict(job, receipt_path=str(folder / "receipt.json"))
                write(folder / "job.json", saved_job)
                (folder / script_name).write_bytes((HERE / script_name).read_bytes())
                pending_state = read(directory / "session.json")
                fault = dict(label=label, script=script_name, status="injected_failure_before_Blender_launch",
                    actual_Blender_processes=0, reserved_job=identity(folder / "job.json"),
                    saved_blend=identity(job["current_blend"]), pending_at_failure=copy.deepcopy(pending_state["pending"]),
                    output_directory_existed=Path(job["readback_npz"]).parent.exists())
                write(folder / "FAULT_INJECTION.json", fault)
                report["fault_attempts"].append(fault)
                raise RuntimeError("regression_reader_failed_after_job_reservation_before_Blender_launch")
            result = run_job(script_name, job, label, **kwargs)
            report["jobs"].append(result)
            return result

        with patch.object(session_api, "run_job", side_effect=controlled_job):
            try:
                session_api.submit_edit(directory, payload, 0, operation)
            except RuntimeError as error:
                report["injected_exception"] = dict(type=type(error).__name__, message=str(error))
            after_fault = read(directory / "session.json")
            write(directory / "STATE_AFTER_FAULT.json", after_fault)
            checks = report["checks"]
            checks["expected_prelaunch_fault_raised"] = report.get("injected_exception", {}).get("message") == "regression_reader_failed_after_job_reservation_before_Blender_launch"
            pending = after_fault.get("pending")
            checks["saved_blend_retained_after_reader_fault"] = bool(pending and (Path(pending["directory"]) / "model.blend").exists())
            checks["read_attempt_persisted_before_launch"] = bool(pending and pending.get("next_read_attempt") == 1 and
                report["fault_attempts"][0]["pending_at_failure"].get("next_read_attempt") == 1)
            checks["failed_reader_did_not_commit_version"] = after_fault["version"] == 0 and len(after_fault["operations"]) == 0
            recovered = session_api.load_state(directory)
            write(directory / "STATE_AFTER_RECOVERY.json", recovered)
            checks["one_recovered_version_committed"] = recovered["version"] == 1 and len(recovered["operations"]) == 1 and recovered["pending"] is None
            checks["recovery_selected_new_attempt_r1"] = recovered["operations"][0]["reader_job"] == pending["job_label"]+"r1"
            checks["recovery_used_independent01"] = Path(recovered["current_npz"]).parent.name == "independent01"
            checks["independent00_packet_never_created"] = not (Path(pending["directory"]) / "independent00").exists()
            jobs_before_replay = len(report["jobs"])
            replay = session_api.submit_edit(directory, payload, 0, operation)
            checks["same_operation_replay_idempotent"] = replay.get("idempotent_receipt") is True and replay["version"] == 1
            checks["replay_started_no_job"] = len(report["jobs"]) == jobs_before_replay

        actual_jobs = report["jobs"]
        writers = [job for job in actual_jobs if Path(job["script"]["path"]).name == "blender_edit.py"]
        readers = [job for job in actual_jobs if Path(job["script"]["path"]).name == "blender_read.py"]
        checks["exactly_one_actual_writer_and_one_actual_reader"] = len(writers) == 1 and len(readers) == 1
        checks["actual_reader_reopened_saved_blend"] = bool(readers and readers[0]["receipt"].get("input_unchanged") and
            readers[0]["receipt"].get("writer_arrays_or_receipts_read") is False)
        checks["recovery_preserved_saved_writer_bytes"] = bool(writers and identity(recovered["current_blend"])["sha256"] == writers[0]["receipt"]["output_blend"]["sha256"])
        checks["independent_before_copy_unchanged"] = identity(directory / "before.blend") == initial_identity
        checks["original_asset_unchanged"] = identity(spec["source_original"]) == original_identity
        with np.load(recovered["current_npz"], allow_pickle=False) as package:
            actual = {name:package[name] for name in package.files}
        inverse = np.linalg.inv(initial["matrix_world"])
        requested_world = initial["vertices"][center]+displacement
        expected_native = (requested_world @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
        checks["submitted_center_matches_float32_quantization"] = expected_native.tobytes() == actual["vertices_local"][center].tobytes()
        other = np.arange(len(actual["vertices_local"])) != center
        checks["all_unsubmitted_native_coordinates_bitwise_preserved"] = initial["vertices_local"][other].tobytes() == actual["vertices_local"][other].tobytes()
        checks["native_polygon_topology_preserved"] = bool(np.array_equal(initial["poly_offsets"], actual["poly_offsets"]) and
            np.array_equal(initial["poly_vertices"], actual["poly_vertices"]))
        report["quality"] = read(Path(recovered["operations"][0]["quality_record"]))
        report["replay_receipt"] = replay
        report["final_state"] = identity(directory / "session.json")
        checks["frozen_sources_unchanged_during_regression"] = source_before == [identity(path) for path in source_paths]
        report["status"] = "pass" if all(checks.values()) else "fail"
    except Exception:
        report.update(status="failed", traceback=traceback.format_exc())
        raise
    finally:
        report.update(wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu, source_files=source_before,
            actual_Blender_processes=len(report["jobs"]), prelaunch_fault_attempts=len(report["fault_attempts"]),
            actual_writer_calls=sum(Path(job["script"]["path"]).name == "blender_edit.py" for job in report["jobs"]),
            actual_reader_calls=sum(Path(job["script"]["path"]).name == "blender_read.py" for job in report["jobs"]),
            nested_Blender_wall_s=sum(job["wall_s"] for job in report["jobs"]))
        if report.get("session_directory"):
            paths = [path for path in Path(report["session_directory"]).rglob("*") if path.is_file()]
            report["saved_session_file_bytes"] = sum(path.stat().st_size for path in paths)
        write(HERE / "RECOVERY_REGRESSION.json", report)
        print(json.dumps(dict(status=report["status"], checks=report["checks"], actual_Blender_processes=report["actual_Blender_processes"],
            prelaunch_fault_attempts=report["prelaunch_fault_attempts"], wall_s=report["wall_s"], cpu_s=report["cpu_s"])))
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
