"""Shared immutable artifacts and resumable jobs for final delivery helpers."""

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write


def absolute(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (HERE / path).resolve()


def verify_identity(expected):
    actual = identity(absolute(expected["path"]))
    if actual["sha256"] != expected["sha256"] or actual["bytes"] != expected["bytes"]:
        raise ValueError("delivery_artifact_identity_changed_" + expected["path"])
    return actual


def session_names(stage):
    return [version + "_matched_" + route for version, routes in
            (("v1", ("native", "facts")), ("v2", ("facts", "native")))
            if stage in (version, "all") for route in routes]


def snapshot_session(name):
    if name not in session_names("all"):
        raise ValueError("delivery_requires_one_of_the_four_fixed_sessions")
    stage, case_id, route = name.split("_")
    directory = HERE / "private/sessions" / name
    consumer_path = HERE / "private/consumers" / stage / case_id / route / "CONSUMER.json"
    state = read(directory / "session.json")
    consumer = read(consumer_path)
    if state.get("pending") or consumer["status"] == "running":
        raise ValueError("delivery_waits_for_terminal_consumer_and_completed_edit_" + name)
    verify_identity(state["current_blend_identity"])
    if absolute(state["current_blend"]) != absolute(state["current_blend_identity"]["path"]):
        raise ValueError("session_saved_blend_path_identity_mismatch")
    snapshot = dict(session=name, stage=stage, route=route, version=state["version"],
        state=identity(directory / "session.json"), consumer=identity(consumer_path),
        consumer_status=consumer["status"], saved_blend=identity(absolute(state["current_blend"])),
        initial_packet=identity(absolute(state["initial_npz"])),
        consumer_final_packet=identity(absolute(state["current_npz"])), spec=identity(absolute(state["source_spec"])))
    return state, snapshot


def verify_snapshot(snapshot):
    for key in ("state", "consumer", "saved_blend", "initial_packet", "consumer_final_packet", "spec"):
        verify_identity(snapshot[key])


def existing_job(script_name, job, label):
    folder = HERE / "private/jobs" / label
    expected = dict(job, receipt_path=str(folder / "receipt.json"))
    if read(folder / "job.json") != expected:
        raise ValueError("fixed_delivery_job_has_different_inputs_" + label)
    receipt = read(folder / "receipt.json")
    run_path = folder / "run.json"
    if run_path.exists():
        record = read(run_path)
        if record.get("receipt") != receipt:
            raise ValueError("delivery_job_receipt_changed_" + label)
        verify_identity(record["job"])
        verify_identity(record["script"])
    else:
        process = read(HERE / "private/processes" / ("b_" + label + ".json"))
        if process.get("status") != "completed" or process.get("returncode") != 0:
            raise ValueError("existing_delivery_process_requires_inspection_" + label)
        record = dict(label=label, script=identity(HERE / script_name), job=identity(folder / "job.json"),
            wall_s=process.get("full_process_wall_s"), process=process, receipt_path=str(folder / "receipt.json"),
            receipt=receipt, recovered_from_completed_process_record=True)
        write(run_path, record)
    if record["process"].get("returncode") != 0:
        raise ValueError("existing_delivery_job_failed_" + label)
    if record["script"]["sha256"] != identity(HERE / script_name)["sha256"]:
        raise ValueError("delivery_script_changed_since_job_" + label)
    execution = receipt["execution"]
    for key, filename in (("script", script_name), ("shared_helper", "blender_common.py")):
        if execution[key]["sha256"] != identity(HERE / filename)["sha256"]:
            raise ValueError("delivery_execution_source_changed_" + filename)
    return record


def ensure_job(script_name, job, label):
    folder = HERE / "private/jobs" / label
    reused = folder.exists()
    if not reused:
        from background import run_job
        run_job(script_name, job, label)
    return existing_job(script_name, job, label), reused


def job_cost(record):
    process = record["process"]
    return dict(wall_s=record["wall_s"], tree_CPU_s=process.get("tree_cpu_s"),
                process_CPU_s=process.get("full_process_cpu_s"),
                tree_sampled_peak_RSS_bytes=process.get("tree_sampled_peak_working_set_bytes"),
                process_peak_RSS_bytes=process.get("peak_working_set_bytes"))


def merge_index(path, stage, rows):
    previous = read(path) if path.exists() else dict(sessions=[])
    retained = [row for row in previous["sessions"] if stage != "all" and row["stage"] != stage]
    by_name = {row["session"]: row for row in retained + rows}
    return [by_name[name] for name in session_names("all") if name in by_name]
