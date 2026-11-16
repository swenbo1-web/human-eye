"""Run three isolated save, disk-reopen/read and render sequences in one Blender."""

import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy
import numpy as np
from blender_common import file_identity, output_path, resources


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = output_path(path)
    temporary = path.with_name(path.name + ".next")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    temporary.replace(path)


def check_identity(expected):
    actual = file_identity(expected["path"])
    if actual["bytes"] != expected["bytes"] or actual["sha256"] != expected["sha256"]:
        raise ValueError("batch_bound_file_changed_" + str(expected["path"]))
    return Path(actual["path"])


def reopen(expected, role):
    path = check_identity(expected)
    started, cpu = time.perf_counter(), time.process_time()
    bpy.ops.wm.open_mainfile(filepath=str(path))
    if Path(bpy.data.filepath).resolve() != path.resolve():
        raise ValueError("batch_disk_reopen_path_mismatch")
    check_identity(expected)
    return dict(role=role, path=str(path), identity=expected, PID=os.getpid(),
        fresh_disk_reopen=True, new_process=False,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)


def invoke(script, job_path):
    old_arguments = sys.argv
    try:
        sys.argv = [str(script), "--", "--job", str(job_path)]
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv = old_arguments


def verify_native(candidate, packet):
    with np.load(candidate["initial_packet"]["path"], allow_pickle=False) as initial, np.load(candidate["payload"]["path"], allow_pickle=False) as payload, np.load(packet, allow_pickle=False) as actual:
        ids = payload["source_ids"]
        values = payload["displacements_world"]
        expected = initial["vertices_local"].copy()
        inverse = np.linalg.inv(initial["matrix_world"])
        requested = initial["vertices_world"][ids] + values
        expected[ids] = (requested @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
        checks = dict(exact_requested_native_float32=expected.tobytes() == actual["vertices_local"].tobytes())
        for key in ("source_ids", "matrix_world", "poly_offsets", "poly_vertices", "faces", "triangle_polygon_ids"):
            checks[key] = initial[key].dtype == actual[key].dtype and initial[key].shape == actual[key].shape and initial[key].tobytes() == actual[key].tobytes()
    if not all(checks.values()):
        raise ValueError("batch_saved_geometry_differs_from_bound_payload")
    return dict(status="pass", checks=checks)


def verify_step(step, candidate, kind):
    check_identity(step["job"])
    check_identity(step["worker"])
    job = read(step["job"]["path"])
    receipt = read(check_identity(step["receipt"]))
    if kind == "edit":
        check_identity(receipt["input_blend"])
        check_identity(receipt["output_blend"])
        check_identity(receipt["submitted_payload"])
        if receipt["input_blend"]["sha256"] != candidate["initial_blend"]["sha256"] or receipt["submitted_payload"]["sha256"] != candidate["payload"]["sha256"]:
            raise ValueError("batch_edit_receipt_binding_mismatch")
        if receipt["status"] != "saved":
            raise ValueError("batch_edit_receipt_status_mismatch")
        expected_paths = ((receipt["input_blend"]["path"], candidate["initial_blend"]["path"]),
            (receipt["output_blend"]["path"], candidate["output_blend"]),
            (receipt["submitted_payload"]["path"], candidate["payload"]["path"]))
    elif kind == "read":
        if receipt["status"] != "read_actual_saved_blend" or not receipt["input_unchanged"] or receipt["writer_arrays_or_receipts_read"]:
            raise ValueError("batch_read_receipt_status_mismatch")
        check_identity(receipt["input_blend"])
        check_identity(receipt["readback_npz"])
        check_identity(receipt["scene_signature_json"])
        verify_native(candidate, receipt["readback_npz"]["path"])
        expected_paths = ((receipt["input_blend"]["path"], candidate["output_blend"]),
            (receipt["readback_npz"]["path"], job["readback_npz"]),
            (receipt["scene_signature_json"]["path"], job["scene_signature_json"]))
    else:
        if receipt["status"] != "rendered_actual_saved_full_character" or receipt["scene_changes_saved"] or receipt["geometry_scale"] != 1 or receipt["displacement_scale"] != 1:
            raise ValueError("batch_render_receipt_status_mismatch")
        check_identity(receipt["current_blend"])
        if [row["specification"] for row in receipt["views"]] != candidate["views"]:
            raise ValueError("batch_render_views_changed")
        for row in receipt["views"]:
            check_identity(row["image"])
            if Path(row["image"]["path"]).resolve().parent != Path(job["output_dir"]).resolve():
                raise ValueError("batch_render_image_directory_mismatch")
        expected_paths = ((receipt["current_blend"]["path"], candidate["output_blend"]),)
    if any(Path(actual).resolve() != Path(expected).resolve() for actual, expected in expected_paths):
        raise ValueError("batch_step_receipt_path_mismatch")
    if receipt["execution"]["script"]["sha256"] != step["worker"]["sha256"]:
        raise ValueError("batch_worker_receipt_source_mismatch")
    return receipt


def run_step(kind, candidate, entry, state, state_path, workers, counters):
    prior = entry.get(kind)
    if prior and prior.get("status") == "complete":
        verify_step(prior, candidate, kind)
        counters["reused_steps"] += 1
        return prior
    if prior and prior.get("receipt_path") and Path(prior["receipt_path"]).exists():
        try:
            recovered = dict(prior, status="complete", receipt=file_identity(prior["receipt_path"]))
            verify_step(recovered, candidate, kind)
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
        else:
            recovered["recovered_existing_receipt"] = True
            entry[kind] = recovered
            write(state_path, state)
            counters["reused_steps"] += 1
            return recovered
    model_path = Path(candidate["output_blend"])
    if kind == "edit" and model_path.exists():
        if prior:
            entry.setdefault("retired_attempts", []).append(dict(prior))
        entry[kind] = dict(status="saved_receipt_missing", saved_blend=file_identity(model_path),
            recovery="Validate the existing saved bytes through a fresh disk read and native-coordinate reconstruction")
        write(state_path, state)
        counters["recovered_saved_outputs"] += 1
        return entry[kind]
    if prior:
        entry.setdefault("retired_attempts", []).append(dict(prior))
    attempt = entry.get("next_" + kind + "_attempt", 0)
    entry["next_" + kind + "_attempt"] = attempt + 1
    directory = output_path(Path(candidate["directory"]) / "batch_attempts" / (kind + str(attempt).zfill(2)))
    directory.mkdir(parents=True, exist_ok=False)
    worker = check_identity(workers[kind])
    job = dict(object_name=candidate["object_name"], source_original=candidate["source_original"],
        base_npz=candidate["initial_packet"]["path"], receipt_path=str(directory / "receipt.json"))
    if kind == "edit":
        job.update(current_blend=candidate["initial_blend"]["path"], expected_input_sha256=candidate["initial_blend"]["sha256"],
            output_blend=str(model_path), allowed_ids_path=candidate["initial_packet"]["path"],
            edit_payload=candidate["payload"]["path"], operation_id=candidate["operation_id"])
        input_identity = candidate["initial_blend"]
    else:
        input_identity = file_identity(model_path)
        job.update(current_blend=str(model_path), expected_input_sha256=input_identity["sha256"])
        if kind == "read":
            job.update(readback_npz=str(directory / "readback.npz"), scene_signature_json=str(directory / "scene.json"),
                local_obj=str(directory / "local.obj"))
        else:
            job.update(output_dir=str(directory / "images"), views=candidate["views"])
    job_path = directory / "job.json"
    write(job_path, job)
    step = dict(status="running", attempt=attempt, PID=os.getpid(), worker=file_identity(worker),
        parent_job_label=state.get("current_parent_job_label"), job=file_identity(job_path),
        receipt_path=job["receipt_path"], dedicated_process_per_step=False)
    entry[kind] = step
    write(state_path, state)
    started, cpu = time.perf_counter(), time.process_time()
    step["disk_reopen"] = reopen(input_identity, kind)
    write(state_path, state)
    counters["worker_invocations"][kind] += 1
    try:
        invoke(worker, job_path)
        step.update(status="complete", receipt=file_identity(job["receipt_path"]))
        verify_step(step, candidate, kind)
    except BaseException as error:
        step.update(status="failed", error=dict(type=type(error).__name__, message=str(error)))
        raise
    finally:
        step.update(wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
            process_cumulative_resources=resources())
        write(directory / "operation_run.json", step)
        step["run"] = file_identity(directory / "operation_run.json")
        write(state_path, state)
    return step


def execute(job):
    started, cpu = time.perf_counter(), time.process_time()
    state_path = output_path(job["state_path"])
    check_identity(job["original"])
    candidates = job["candidates"]
    if [row["alpha"] for row in candidates] != [0., .5, 1.]:
        raise ValueError("batch_requires_fixed_alpha_sequence")
    for row in candidates:
        check_identity(row["initial_blend"])
        check_identity(row["initial_packet"])
        check_identity(row["payload"])
    for value in job["workers"].values():
        check_identity(value)
    state = read(state_path) if state_path.exists() else dict(binding_sha256=job["binding_sha256"], status="running", candidates={})
    if state["binding_sha256"] != job["binding_sha256"]:
        raise ValueError("batch_existing_state_binding_changed")
    counters = dict(worker_invocations=dict(edit=0, read=0, render=0), reused_steps=0, recovered_saved_outputs=0)
    state.update(status="running", current_PID=os.getpid(), current_parent_job_label=job["batch_job_label"])
    write(state_path, state)
    try:
        for candidate in candidates:
            entry = state["candidates"].setdefault(candidate["alpha_tag"], dict(alpha=candidate["alpha"], status="running"))
            run_step("edit", candidate, entry, state, state_path, job["workers"], counters)
            run_step("read", candidate, entry, state, state_path, job["workers"], counters)
            actual = read(entry["read"]["receipt"]["path"])
            entry["native_verification"] = verify_native(candidate, actual["readback_npz"]["path"])
            run_step("render", candidate, entry, state, state_path, job["workers"], counters)
            entry["status"] = "complete"
            write(state_path, state)
        state["status"] = "complete"
    except BaseException as error:
        state.update(status="partial_query_owned_state", error=dict(type=type(error).__name__, message=str(error)))
        raise
    finally:
        state.update(last_invocation=dict(PID=os.getpid(), counters=counters, wall_s=time.perf_counter() - started,
            CPU_s=time.process_time() - cpu, resources=resources()))
        write(state_path, state)
    return dict(status="complete", binding_sha256=job["binding_sha256"], state=file_identity(state_path),
        PID=os.getpid(), operation_counts=counters, wall_s=time.perf_counter() - started,
        CPU_s=time.process_time() - cpu, resources=resources(), fresh_read_mode="Owned batch process, explicit disk reopen per read",
        process_accounting="One Blender process. Worker resource observations are cumulative snapshots, while operation CPU and wall values are per-step deltas.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    job = read(args.job)
    try:
        result = execute(job)
    except BaseException as error:
        write(job["receipt_path"], dict(status="partial_query_owned_state", binding_sha256=job["binding_sha256"],
            state=file_identity(job["state_path"]) if Path(job["state_path"]).exists() else None,
            PID=os.getpid(), error=dict(type=type(error).__name__, message=str(error))))
        raise
    write(job["receipt_path"], result)
    print(json.dumps(dict(status=result["status"], PID=os.getpid(), operation_counts=result["operation_counts"])), flush=True)


if __name__ == "__main__":
    main()
