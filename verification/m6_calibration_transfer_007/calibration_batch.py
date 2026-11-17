"""Owned single-process backend for the fixed three-alpha calibration contract."""

import json
import os
from pathlib import Path
import subprocess
import time

import calibrator as base
from evaluate import evaluate_packets
from image_metric import PNGCache
from session_api import short_quality
import numpy as np


EXTRA_SOURCES = ("calibration_batch.py", "batch_worker.py")


def _batch_directory(stage, proposal_id):
    return base.HERE / "private/calibrations" / (stage + "_" + proposal_id)


def _query_process(pid):
    pid = int(pid)
    command = "$p=Get-CimInstance Win32_Process -Filter 'ProcessId=" + str(pid) + "' -ErrorAction Stop; "
    command += "if($null -eq $p){@{found=$false}|ConvertTo-Json -Compress}else{"
    command += "@{found=$true;pid=$p.ProcessId;name=$p.Name;command_line=$p.CommandLine;"
    command += "creation_epoch_ms=([DateTimeOffset]$p.CreationDate).ToUnixTimeMilliseconds()}|ConvertTo-Json -Compress}"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError("owned_batch_process_query_failed_" + result.stderr.decode("utf8", errors="replace"))
    return json.loads(result.stdout)


def _ensure_prior_exit(directory):
    attempt_path = directory / "BATCH_ATTEMPT.json"
    if not attempt_path.exists():
        return
    prior = base.read(attempt_path)
    label = prior.get("job_label")
    worker_path = directory / "BATCH_STATE.json"
    worker_pid = None
    if worker_path.exists():
        worker_state = base.read(worker_path)
        if worker_state.get("current_parent_job_label") == label:
            worker_pid = worker_state.get("current_PID")
    process_path = base.HERE / "private/processes" / ("b_" + label + ".json") if label else None
    if process_path and process_path.exists():
        process = base.read(process_path)
        if process.get("status") in ("completed", "failed") and type(process.get("returncode")) is int:
            return
        pid = process.get("pid") or worker_pid
        expected_job = str(base.HERE / "private/jobs" / label / "job.json")
    else:
        if label and (base.HERE / "private/jobs" / label).exists():
            pid = worker_pid
            expected_job = str(base.HERE / "private/jobs" / label / "job.json")
        else:
            pid, expected_job = prior.get("owner_PID"), None
        if pid == os.getpid() and (not label or not (base.HERE / "private/jobs" / label).exists()):
            return
    if pid is None:
        raise RuntimeError("owned_batch_process_state_unknown_query_before_retry")
    observed = _query_process(pid)
    query_path = directory / ("RECOVERY_PROCESS_QUERY_" + str(len(list(directory.glob("RECOVERY_PROCESS_QUERY_*.json")))).zfill(3) + ".json")
    base.write(query_path, dict(prior_attempt=prior, process=observed, queried_epoch=time.time()))
    if not observed.get("found"):
        return
    if expected_job:
        actual = observed.get("command_line")
        if not actual:
            raise RuntimeError("owned_batch_process_command_unknown_query_before_retry")
        normalized = actual.replace("/", "\\").casefold()
        if expected_job.replace("/", "\\").casefold() not in normalized:
            return
    elif observed.get("creation_epoch_ms", 0) > prior["updated_epoch"] * 1000:
        return
    raise RuntimeError("prior_owned_batch_process_still_running_query_before_retry")


def _prepare(source, proposal, ids, delta, stage, binding_sha):
    spec = base.read(base.checked_identity(source["initial"]["spec"]))
    candidates = []
    for alpha, tag in zip(base.ALPHAS, base.TAGS):
        directory = base.initialize_session(source, stage, proposal["proposal_id"], tag)
        payload = base.scaled_payload(directory, proposal, ids, delta, alpha)
        state_path = directory / "session.json"
        state = base.read(state_path)
        maximum = float(min(spec["max_operation_displacement_m"], spec["max_cumulative_displacement_m"]))
        if float(np.linalg.norm(alpha * delta, axis=1).max()) > maximum:
            raise ValueError("batch_candidate_exceeds_fixed_displacement_budget")
        operation_id = "calibrate_" + stage + "_" + proposal["proposal_id"] + "_" + tag
        pending = dict(operation_id=operation_id, payload_sha256=base.identity(payload)["sha256"], expected_version=0,
            directory=str(directory / "versions/001"), job_label="batch_" + proposal["proposal_id"],
            current_input_identity=base.identity(directory / "before.blend"), batch_binding_sha256=binding_sha)
        if state["version"] == 0:
            if state.get("operations"):
                raise ValueError("batch_session_has_prior_failed_operation_query_state")
            if state.get("pending") and state["pending"] != pending:
                raise ValueError("batch_session_pending_binding_changed")
            state["pending"] = pending
            base.write(state_path, state)
        elif state["version"] != 1 or len(state["operations"]) != 1 or state["operations"][0]["operation_id"] != operation_id or state["operations"][0]["payload_sha256"] != pending["payload_sha256"]:
            raise ValueError("batch_session_completed_operation_binding_changed")
        candidates.append(dict(alpha=alpha, alpha_tag=tag, directory=str(directory), operation_id=operation_id,
            initial_blend=dict(base.identity(directory / "before.blend"), path=str(directory / "before.blend")),
            initial_packet=dict(source["initial"]["packet"], path=str(base.checked_identity(source["initial"]["packet"]))),
            payload=dict(base.identity(payload), path=str(payload)), output_blend=str(directory / "versions/001/model.blend"),
            object_name=spec["object_name"], source_original=spec["source_original"], views=source["views"]))
    return candidates


def _check_step(step):
    for key in ("worker", "job", "receipt"):
        base.checked_identity(step[key])
    return base.read(base.checked_identity(step["receipt"]))


def _complete_rows(source, proposal, ids, delta, stage, job, worker_state):
    rows = {}
    for candidate in job["candidates"]:
        tag = candidate["alpha_tag"]
        entry = worker_state["candidates"][tag]
        if entry["status"] != "complete":
            raise ValueError("batch_candidate_incomplete_query_worker_state")
        reader = _check_step(entry["read"])
        renderer = _check_step(entry["render"])
        saved = reader["input_blend"]
        base.checked_identity(saved)
        readback = base.checked_identity(reader["readback_npz"])
        scene = base.checked_identity(reader["scene_signature_json"])
        if not reader["input_unchanged"] or reader["writer_arrays_or_receipts_read"]:
            raise ValueError("batch_reader_provenance_invalid")
        native = base.verify_native(base.checked_identity(source["initial"]["packet"]), readback, ids,
            candidate["alpha"] * delta, candidate["alpha"])
        if native["status"] != "pass":
            raise ValueError("batch_native_output_differs_from_requested_payload")
        directory = Path(candidate["directory"])
        quality_path = readback.parent / "QUALITY.json"
        if not quality_path.exists():
            quality = evaluate_packets(base.checked_identity(source["initial"]["packet"]), readback,
                base.checked_identity(source["initial"]["packet"]), base.checked_identity(source["initial"]["spec"]),
                before_state_path=base.checked_identity(source["initial"]["scene"]), after_state_path=scene)
            base.write(quality_path, quality)
        else:
            quality = base.read(quality_path)
        render_run_path = Path(entry["render"].get("run", {}).get("path", directory / "batch_render_run.json"))
        if not render_run_path.exists():
            base.write(render_run_path, entry["render"])
        render_record = dict(receipt=renderer)
        images = base.rendered_rows(render_record, source, saved)
        writer_PID, reader_PID = entry["edit"].get("PID"), entry["read"]["PID"]
        operation = dict(operation_id=candidate["operation_id"], payload_sha256=candidate["payload"]["sha256"],
            expected_version=0, version=1, status="saved_and_independently_read", saved_blend=saved,
            readback=base.identity(readback), quality_record=str(quality_path), quality=short_quality(quality),
            independently_reopened=True, exact_submitted_values=True,
            reader_job=entry["read"]["parent_job_label"], reader_suboperation_job=entry["read"]["job"],
            reader_suboperation_receipt=entry["read"]["receipt"],
            fresh_process=reader_PID != writer_PID if writer_PID is not None else None,
            dedicated_reader_process=False, fresh_disk_reopen=True, reader_PID=reader_PID,
            writer_PID=writer_PID, batch_worker_state=base.identity(Path(job["state_path"])),
            receipt_recovery="Existing saved file validated through fresh disk read" if entry["edit"]["status"] == "saved_receipt_missing" else None)
        state_path = directory / "session.json"
        state = base.read(state_path)
        state.update(version=1, current_blend=str(base.absolute(saved["path"])), current_npz=str(readback),
            current_scene=str(scene), current_blend_identity=saved, pending=None, operations=[operation])
        base.write(directory / "versions/001/OPERATION.json", operation)
        base.write(state_path, state)
        rows[tag] = dict(alpha=candidate["alpha"], alpha_tag=tag, status="complete",
            technical_status="pass" if quality["status"] == "pass" else "fail", session=str(directory),
            payload=candidate["payload"], saved_blend=saved, readback=base.identity(readback), scene=base.identity(scene),
            quality=base.identity(quality_path), operation=operation, reader_receipt=entry["read"]["receipt"],
            native_verification=native, images=images, render_job=entry["render"]["parent_job_label"],
            render_suboperation_job=entry["render"]["job"],
            render_reused=False, render_receipt=entry["render"]["receipt"], render_run=base.identity(render_run_path),
            batch_operations=dict(edit=entry["edit"], read=entry["read"], render=entry["render"]))
    return rows


def _execute_all(source, proposal, ids, delta, stage):
    directory = _batch_directory(stage, proposal["proposal_id"])
    _ensure_prior_exit(directory)
    workers = {kind: dict(base.identity(base.HERE / ("blender_" + kind + ".py")), path=str(base.HERE / ("blender_" + kind + ".py")))
        for kind in ("edit", "read", "render")}
    logical = dict(source_binding=base.identity(base.HERE / "SOURCE_BINDING.json"), proposal=proposal["payload"],
        stage=stage, alphas=list(base.ALPHAS), workers=workers,
        backend_sources=[base.identity(base.HERE / name) for name in EXTRA_SOURCES])
    binding_sha = base.digest(logical)
    state_path = directory / "BATCH_STATE.json"
    candidates = _prepare(source, proposal, ids, delta, stage, binding_sha)
    job = dict(current_blend=str(base.checked_identity(source["initial"]["blend"])), original=source["original"],
        binding_sha256=binding_sha, state_path=str(state_path), workers=workers, candidates=candidates)
    worker_state = base.read(state_path) if state_path.exists() else None
    if worker_state is None or worker_state.get("status") != "complete":
        attempt_path = directory / "BATCH_ATTEMPT.json"
        attempt = base.read(attempt_path).get("next_attempt", 0) if attempt_path.exists() else 0
        label = "batch_" + stage + "_" + proposal["proposal_id"] + "_" + str(attempt).zfill(3)
        job["batch_job_label"] = label
        base.write(attempt_path, dict(next_attempt=attempt + 1, binding_sha256=binding_sha,
            status="owned_batch_starting", attempt=attempt, job_label=label, owner_PID=os.getpid(), updated_epoch=time.time()))
        base.run_job("batch_worker.py", job, label, timeout_s=720)
        worker_state = base.read(state_path)
    if worker_state["binding_sha256"] != binding_sha:
        raise ValueError("batch_worker_state_binding_changed")
    return _complete_rows(source, proposal, ids, delta, stage, job, worker_state)


def calibrate(request):
    if request.get("stage") != "v2":
        raise ValueError("optimized_batch_backend_requires_stage_v2")
    completed, failure = None, None

    def execute(source, proposal, ids, delta, stage, alpha, tag, progress):
        nonlocal completed, failure
        if failure is not None:
            raise RuntimeError("batch_attempt_failed_query_owned_state_before_retry") from failure
        if completed is None:
            progress["status"] = "owned_batch_execute_or_recover"
            try:
                completed = _execute_all(source, proposal, ids, delta, stage)
            except Exception as error:
                failure = error
                raise
        return completed[tag]

    return base.calibrate(request, candidate_executor=execute, extra_sources=EXTRA_SOURCES, image_cache=PNGCache())


def status(request):
    if request.get("stage") != "v2":
        raise ValueError("optimized_batch_status_requires_stage_v2")
    _, _, _, _, binding = base.validate_request(request, extra_sources=EXTRA_SOURCES)
    directory = _batch_directory(request["stage"], request["proposal_id"])
    if (directory / "BINDING.json").exists() and base.read(directory / "BINDING.json") != binding:
        raise ValueError("calibration_input_or_runtime_binding_changed")
    result = base.status(request)
    worker_path = directory / "BATCH_STATE.json"
    result["batch_state"] = base.read(worker_path) if worker_path.exists() else None
    result["batch_state_reference"] = base.identity(worker_path) if worker_path.exists() else None
    return result
