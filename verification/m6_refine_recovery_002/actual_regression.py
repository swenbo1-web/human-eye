"""Exercise standalone and pending read recovery on new full Blender copies."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "m6_refine_001"
PYTHON = HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"
RUNTIME_FILES = ("common.py", "background.py", "blender_common.py", "blender_read.py", "blender_edit.py", "quality.py", "evaluate.py")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")


def read_json(path):
    return json.loads(Path(path).read_bytes())


def file_identity(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def stable_state(state):
    return {key:value for key,value in state.items() if key != "next_readback_attempt"}


def import_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def bootstrap():
    sys.path.insert(0, str(HERE))
    # Exact runtime source bytes run with the new batch root, so every write
    # remains in002 while the original cases and their evidence stay read-only.
    for name in ("common", "background", "quality", "evaluate"):
        import_module(name, HERE / (name + ".py"))
    api = import_module("_recovery002_actual_api", OLD / "session_api.py")
    api.HERE = HERE
    return api


def clone_session(name, original_name, initial=False):
    source = read_json(OLD / "private/sessions" / original_name / "session.json")
    spec = read_json(source["source_spec"])
    directory = HERE / "private/sessions" / name
    directory.mkdir(parents=True, exist_ok=False)
    blend = Path(spec["base_blend_path"] if initial else source["current_blend"])
    shutil.copyfile(blend, directory / "model.blend")
    state = dict(source, current_blend=str(directory / "model.blend"),
        current_blend_identity=file_identity(directory / "model.blend"))
    state.pop("next_readback_attempt", None)
    if initial:
        state.update(version=0, operations=[], pending=None, current_npz=source["initial_npz"], current_scene=spec["baseline_scene"])
    write_json(directory / "session.json", state)
    return directory, state


def attempt_label(directory, number):
    return "q" + hashlib.sha256((directory.name + ":" + str(number)).encode()).hexdigest()[:16]


def compare_packets(first_path, second_path):
    import numpy as np
    with np.load(first_path, allow_pickle=False) as first, np.load(second_path, allow_pickle=False) as second:
        names = ("vertices", "vertices_world", "vertices_local", "matrix_world", "faces", "source_ids", "poly_offsets", "poly_vertices", "triangle_polygon_ids")
        checks = {name: first[name].dtype == second[name].dtype and first[name].shape == second[name].shape and first[name].tobytes() == second[name].tobytes() for name in names}
    return dict(pass_all=all(checks.values()), arrays=checks, first=file_identity(first_path), second=file_identity(second_path))


def make_inventory():
    paths = [OLD / name for name in ("MANIFEST.json", "PLAN.json", "PLAN_FREEZE.json", "CONSUMER_STATS_v1.json", "CONSUMER_STATS_v2.json", "CONSUMER_STATS_all.json", "OPTIMIZATION_BINDING.json")]
    for source in (OLD / "private/sessions").glob("v[12]_*/session.json"):
        state = read_json(source)
        paths += [source, Path(state["current_blend"]), Path(state["current_npz"])]
    for case in read_json(OLD / "SOURCES.json")["cases"]:
        paths.append(Path(case["source_original"]))
    return [file_identity(path) for path in dict.fromkeys(paths)]


def worker():
    started, cpu = time.perf_counter(), time.process_time()
    api = bootstrap()
    import numpy as np
    checks, records, faults = {}, [], []
    before_inventory = make_inventory()
    source_before = file_identity(OLD / "session_api.py")
    real_run_job = api.run_job

    def assert_read(directory, before, result, name):
        state = read_json(directory / "session.json")
        packet = HERE / result["readback"]["path"] if not Path(result["readback"]["path"]).is_absolute() else Path(result["readback"]["path"])
        compared = compare_packets(before["current_npz"], packet)
        preserved = stable_state(state) == stable_state(before)
        unchanged = file_identity(before["current_blend"])["sha256"] == before["current_blend_identity"]["sha256"]
        checks[name+"_saved_state_except_attempt_unchanged"] = preserved
        checks[name+"_saved_blend_unchanged"] = unchanged
        checks[name+"_actual_saved_coordinates_topology_matrix_equal"] = compared["pass_all"]
        checks[name+"_fresh_reader_success"] = result["independently_reopened"] and result["quality"]["status"] == "pass"
        records.append(dict(name=name, directory=str(directory), state_before=before, state_after=state,
            response=result, packet_comparison=compared))

    def install_fault(directory, mode):
        armed = True
        def injected(script_name, job, label, timeout_s=240):
            nonlocal armed
            if armed and script_name == "blender_read.py":
                armed = False
                state = read_json(directory / "session.json")
                row = dict(mode=mode, label=label, script_name=script_name,
                    before_output_exists=Path(job["readback_npz"]).parent.exists(), persisted_state=state,
                    started_at_UTC=datetime.now(timezone.utc).isoformat())
                if mode == "prelaunch":
                    folder = HERE / "private/jobs" / label
                    folder.mkdir(parents=True, exist_ok=False)
                    row.update(actual_process_started=False, job=job,
                        event="job identity reserved, exception injected before Blender launch")
                    write_json(folder / "PRELAUNCH_FAULT.json", row)
                else:
                    result = real_run_job(script_name, job, label, timeout_s)
                    receipt = Path(result["receipt_path"])
                    delayed = receipt.with_name("receipt.delayed.json")
                    receipt.rename(delayed)
                    row.update(actual_process_started=True, saved_readback_exists=Path(job["readback_npz"]).exists(),
                        receipt_preserved_as=file_identity(delayed), process_record=result["process"],
                        event="actual Blender read completed, receipt deliberately made unavailable")
                faults.append(row)
                write_json(HERE / "private/actual/FAULTS.json", faults)
                raise RuntimeError("injected_"+mode+"_reader_fault")
            return real_run_job(script_name, job, label, timeout_s)
        api.run_job = injected

    y_directory, y_before = clone_session("actual_yanyite", "v1_s01_facts")
    y_first = api.save_readback(y_directory)
    assert_read(y_directory, y_before, y_first, "normal_yanyite")
    install_fault(y_directory, "prelaunch")
    try:
        api.save_readback(y_directory)
    except RuntimeError as error:
        checks["prelaunch_fault_observed"] = str(error) == "injected_prelaunch_reader_fault"
    else:
        checks["prelaunch_fault_observed"] = False
    failed_state = read_json(y_directory / "session.json")
    checks["prelaunch_attempt_persisted_before_failure"] = failed_state["next_readback_attempt"] == 3
    checks["prelaunch_failed_output_absent"] = not (y_directory / "readbacks/002").exists()
    checks["prelaunch_saved_state_preserved"] = stable_state(failed_state) == stable_state(y_before)
    api.run_job = real_run_job
    recovered = api.save_readback(y_directory)
    checks["prelaunch_recovered_new_job_label"] = recovered["reader_job"] == attempt_label(y_directory, 3) != faults[-1]["label"]
    assert_read(y_directory, y_before, recovered, "prelaunch_recovery_yanyite")

    f_directory, f_before = clone_session("actual_face", "v1_s02_facts")
    f_first = api.save_readback(f_directory)
    assert_read(f_directory, f_before, f_first, "normal_face")
    install_fault(f_directory, "missing_receipt")
    try:
        api.save_readback(f_directory)
    except RuntimeError as error:
        checks["missing_receipt_fault_observed"] = str(error) == "injected_missing_receipt_reader_fault"
    else:
        checks["missing_receipt_fault_observed"] = False
    failed_state = read_json(f_directory / "session.json")
    checks["missing_receipt_output_retained"] = (f_directory / "readbacks/002/readback.npz").exists()
    checks["missing_receipt_attempt_persisted"] = failed_state["next_readback_attempt"] == 3
    checks["missing_receipt_saved_state_preserved"] = stable_state(failed_state) == stable_state(f_before)
    api.run_job = real_run_job
    recovered = api.save_readback(f_directory)
    checks["missing_receipt_recovery_new_job_label"] = recovered["reader_job"] == attempt_label(f_directory, 3)
    assert_read(f_directory, f_before, recovered, "missing_receipt_recovery_face")

    legacy_directory, legacy_before = clone_session("legacy_face", "v2_s02_facts")
    old_label = attempt_label(legacy_directory, 1)
    reserved = HERE / "private/jobs" / old_label
    reserved.mkdir(parents=True, exist_ok=False)
    write_json(reserved / "LEGACY_PRELAUNCH_FAULT.json", dict(label=old_label, actual_process_started=False,
        existing_state_has_counter=False, output_exists=False, purpose="legacy job reservation without readback output"))
    checks["legacy_counter_absent_at_entry"] = "next_readback_attempt" not in legacy_before
    legacy_result = api.save_readback(legacy_directory)
    checks["legacy_reserved_label_skipped"] = legacy_result["reader_job"] == attempt_label(legacy_directory, 2)
    checks["legacy_attempt_progress_saved"] = read_json(legacy_directory / "session.json")["next_readback_attempt"] == 3
    checks["legacy_failed_output_remains_absent"] = not (legacy_directory / "readbacks/001").exists()
    assert_read(legacy_directory, legacy_before, legacy_result, "legacy_face")

    pending_directory, pending_before = clone_session("pending_yanyite", "v1_s01_facts", initial=True)
    payload = pending_directory / "payloads/probe.npz"
    payload.parent.mkdir()
    spec = read_json(pending_before["source_spec"])
    center = spec["center_source_id"]
    with np.load(pending_before["initial_npz"], allow_pickle=False) as initial:
        vector = .2*spec["h"]*initial["n0"][center]
        np.savez_compressed(payload, source_ids=np.array([center], dtype=np.int64), displacements_world=vector[None,:])
    install_fault(pending_directory, "prelaunch")
    operation_id = "recovery002_pending_probe"
    try:
        api.submit_edit(pending_directory, payload, 0, operation_id)
    except RuntimeError as error:
        checks["pending_prelaunch_fault_observed"] = str(error) == "injected_prelaunch_reader_fault"
    else:
        checks["pending_prelaunch_fault_observed"] = False
    pending = read_json(pending_directory / "session.json")
    saved = Path(pending["pending"]["directory"]) / "model.blend"
    saved_identity = file_identity(saved)
    checks["pending_saved_output_retained"] = saved.exists() and pending["version"] == 0 and pending["operations"] == []
    checks["pending_existing_read_attempt_persisted"] = pending["pending"]["next_read_attempt"] == 1
    api.run_job = real_run_job
    state = api.load_state(pending_directory)
    checks["pending_recovery_commits_once"] = state["version"] == 1 and state["pending"] is None and len(state["operations"]) == 1
    checks["pending_recovery_retains_writer_bytes"] = file_identity(saved) == saved_identity
    checks["pending_recovery_new_reader_label"] = state["operations"][0]["reader_job"].endswith("r1")
    before_jobs = sorted(path.name for path in (HERE / "private/jobs").iterdir())
    replay = api.submit_edit(pending_directory, payload, 0, operation_id)
    after_jobs = sorted(path.name for path in (HERE / "private/jobs").iterdir())
    checks["operation_replay_idempotent"] = replay["idempotent_receipt"] and replay["version"] == 1
    checks["operation_replay_starts_no_job"] = before_jobs == after_jobs
    checks["operation_replay_state_unchanged"] = read_json(pending_directory / "session.json") == state
    with np.load(pending_before["initial_npz"], allow_pickle=False) as initial, np.load(state["current_npz"], allow_pickle=False) as current:
        inverse = np.linalg.inv(initial["matrix_world"])
        desired = initial["vertices"][center] + vector
        expected_native = (desired @ inverse[:3,:3].T + inverse[:3,3]).astype(np.float32)
        outside = np.setdiff1d(np.arange(len(initial["vertices"])), [center])
        checks["pending_exact_requested_float32_result"] = expected_native.tobytes() == current["vertices_local"][center].tobytes()
        checks["pending_unsubmitted_native_bitwise"] = initial["vertices_local"][outside].tobytes() == current["vertices_local"][outside].tobytes()
    records.append(dict(name="pending_edit_recovery_and_replay", directory=str(pending_directory), state_before=pending_before,
        state_after=state, saved_before_recovery=saved_identity, replay=replay,
        interpretation="Tiny single-center probe validates protocol recovery. Its full-region refinement quality status is expected fail."))

    after_inventory = make_inventory()
    checks["all_old_models_sources_sessions_and_results_unchanged"] = before_inventory == after_inventory
    checks["patched_API_unchanged_during_actual_run"] = source_before == file_identity(OLD / "session_api.py")
    jobs = [read_json(path) for path in sorted((HERE / "private/jobs").glob("*/run.json"))]
    checks["eight_actual_Blender_processes"] = len(jobs) == 8
    checks["all_actual_processes_successful"] = all(row["process"]["returncode"] == 0 for row in jobs)
    checks["prelaunch_fault_process_count_zero"] = sum(row["actual_process_started"] is False for row in faults) == 2
    detail = dict(checks=checks, sessions=records, injected_faults=faults, actual_jobs=jobs,
        old_evidence_before=before_inventory, old_evidence_after=after_inventory, api_source=source_before,
        runtime_sources=[file_identity(HERE / name) for name in RUNTIME_FILES],
        adaptation="Exact copied runtime bytes and API implementation execute under new batch root by module preload and api.HERE rebinding. Source inputs remain original read-only paths.")
    write_json(HERE / "private/actual/DETAIL.json", detail)
    result = dict(status="pass" if all(checks.values()) else "fail", checks=checks, checks_passed=sum(checks.values()), checks_total=len(checks),
        actual_Blender_processes=len(jobs), actual_Blender_reads=sum(row["script"]["path"] == "blender_read.py" for row in jobs),
        actual_Blender_edits=sum(row["script"]["path"] == "blender_edit.py" for row in jobs),
        prelaunch_injected_faults=2, output_present_receipt_faults=1, legacy_reserved_labels=1,
        all_source_or_old_final_blend_modifications=0, Pro_sessions=0, training_runs=0, render_calls=0,
        wall_s=time.perf_counter()-started, parent_cpu_s=time.process_time()-cpu,
        nested_Blender_wall_s=sum(row["wall_s"] for row in jobs),
        nested_Blender_tree_CPU_s=sum(row["process"].get("tree_cpu_s",0.) for row in jobs),
        peak_Blender_tree_RSS_bytes=max(row["process"].get("tree_sampled_peak_working_set_bytes",0) for row in jobs),
        detail=file_identity(HERE / "private/actual/DETAIL.json"), api_source=source_before,
        copied_runtime_sources=[dict(source=file_identity(OLD / name), copy=file_identity(HERE / name)) for name in RUNTIME_FILES])
    write_json(HERE / "ACTUAL_SUMMARY.json", result)
    print(json.dumps(dict(status=result["status"], checks=result["checks_total"], wall_s=result["wall_s"], Blender_processes=len(jobs))), flush=True)
    if result["status"] != "pass":
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker()
        return
    for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[variable] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    for name in RUNTIME_FILES:
        destination = HERE / name
        if destination.exists() and destination.read_bytes() != (OLD / name).read_bytes():
            raise ValueError("runtime_copy_differs_"+name)
        if not destination.exists():
            shutil.copyfile(OLD / name, destination)
    monitor = import_module("_recovery002_actual_monitor", HERE.parent / "m6_shape_train_001/process_runner.py")
    monitor.HERE = HERE
    if (HERE / "private/processes/actual_regression.json").exists():
        raise ValueError("actual_regression_already_attempted_preserve_prior_artifacts")
    record = monitor.run([str(PYTHON), "-I", "-B", "-X", "utf8", str(Path(__file__)), "--worker"],
        "actual_regression", timeout_s=1800, rss_limit_bytes=4*1024**3)
    write_json(HERE / "ACTUAL_PROCESS.json", record)
    if record["returncode"]:
        raise SystemExit(record["returncode"])


if __name__ == "__main__":
    main()
