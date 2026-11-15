"""Versioned sparse edits with actual Blender save and independent readback."""

from contextlib import contextmanager
import hashlib
import msvcrt
import os
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job
import numpy as np


@contextmanager
def session_lock(directory):
    lock = directory / "edit.lock"
    stream = lock.open("a+b")
    try:
        if stream.seek(0, 2) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        stream.close()


def state_path(directory):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(HERE / "private/sessions"):
        raise ValueError("session_outside_current_batch")
    return directory / "session.json"


def short_quality(result):
    # This task's evaluator owns the contour targets and geometric acceptance.
    # Large exact-pair and face-angle evidence stays in the complete QUALITY file.
    return {key: result[key] for key in ("status", "checks", "contours", "contour", "geometry", "displacement", "identity") if key in result}


def read_actual(directory, state, blend, label, output):
    from evaluate import evaluate_packets
    spec = read(Path(state["source_spec"]))
    result = run_job("blender_read.py", dict(current_blend=str(blend), object_name=spec["object_name"],
        source_original=spec["source_original"], base_npz=state["initial_npz"],
        expected_input_sha256=identity(blend)["sha256"], readback_npz=str(output / "readback.npz"),
        scene_signature_json=str(output / "scene.json"), local_obj=str(output / "local.obj")), label)
    quality = evaluate_packets(state["initial_npz"], output / "readback.npz", state["initial_npz"],
        state["source_spec"], before_state_path=spec["baseline_scene"], after_state_path=output / "scene.json")
    write(output / "QUALITY.json", quality)
    return result, quality


def finish_pending(directory, state, writer_error=None):
    pending = state["pending"]
    output = Path(pending["directory"])
    blend = output / "model.blend"
    if not blend.exists():
        raise RuntimeError("pending_output_absent_inspect_owned_job_before_replaying")
    attempt = pending.get("next_read_attempt", 0)
    pending["next_read_attempt"] = attempt + 1
    write(state_path(directory), state)
    read_directory = output / ("independent" + str(attempt).zfill(2))
    result, quality = read_actual(directory, state, blend, pending["job_label"] + "r" + str(attempt), read_directory)
    final = dict(operation_id=pending["operation_id"], payload_sha256=pending["payload_sha256"],
        expected_version=pending["expected_version"], version=state["version"] + 1,
        status="saved_and_independently_read", saved_blend=identity(blend),
        readback=identity(read_directory / "readback.npz"), quality_record=str(read_directory / "QUALITY.json"),
        quality=short_quality(quality), independently_reopened=True, exact_submitted_values=True,
        receipt_recovery=writer_error, reader_job=pending["job_label"] + "r" + str(attempt))
    write(output / "OPERATION.json", final)
    state.update(version=final["version"], current_blend=str(blend), current_npz=str(read_directory / "readback.npz"),
        current_scene=str(read_directory / "scene.json"), current_blend_identity=identity(blend), pending=None)
    state["operations"].append(final)
    write(state_path(directory), state)
    return final


def load_state(directory):
    directory = Path(directory).resolve()
    state = read(state_path(directory))
    if state.get("pending"):
        with session_lock(directory):
            state = read(state_path(directory))
            if state.get("pending"):
                finish_pending(directory, state, "recovered_saved_output_after_interrupted_receipt")
        state = read(state_path(directory))
    actual = identity(state["current_blend"])
    if state.get("current_blend_identity") and actual["sha256"] != state["current_blend_identity"]["sha256"]:
        raise ValueError("current_saved_blend_changed_outside_versioned_edit")
    state["current_blend_identity"] = actual
    return state


def submit_edit(directory, payload_path, expected_version, operation_id):
    directory, payload_path = Path(directory).resolve(), Path(payload_path).resolve()
    if not payload_path.is_relative_to(directory / "payloads"):
        raise ValueError("payload_must_belong_to_this_session")
    if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", operation_id):
        raise ValueError("operation_id_requires_1_to64_safe_characters")
    started = time.perf_counter()
    with session_lock(directory):
        state = read(state_path(directory))
        digest = identity(payload_path)["sha256"]
        for previous in state["operations"]:
            if previous["operation_id"] == operation_id:
                if previous["payload_sha256"] != digest or previous["expected_version"] != expected_version:
                    raise ValueError("operation_id_already_bound_to_other_payload_or_version")
                return dict(previous, idempotent_receipt=True)
        if state.get("pending"):
            pending = state["pending"]
            if (pending["operation_id"], pending["payload_sha256"], pending["expected_version"]) != (operation_id, digest, expected_version):
                raise ValueError("another_edit_pending_inspect_state")
            return finish_pending(directory, state, "same_operation_receipt_recovery")
        if type(expected_version) is not int or state["version"] != expected_version:
            raise ValueError("stale_expected_version")
        if identity(state["current_blend"])["sha256"] != state["current_blend_identity"]["sha256"]:
            raise ValueError("current_saved_blend_changed_outside_versioned_edit")
        with np.load(state["initial_npz"], allow_pickle=False) as initial, np.load(payload_path, allow_pickle=False) as payload:
            ids = payload["source_ids"]
            modes = [key for key in ("positions_world", "displacements_world") if key in payload]
            if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer) or not len(ids) or len(np.unique(ids)) != len(ids) or not np.isin(ids, initial["I_ids"]).all():
                raise ValueError("sparse_source_ids_require_unique_nonempty_subset_of_I")
            if len(modes) != 1 or payload[modes[0]].shape != (len(ids), 3) or not np.isfinite(payload[modes[0]]).all():
                raise ValueError("one_finite_world_coordinate_payload_required")
            initial_positions = np.asarray(initial["vertices_world"] if "vertices_world" in initial else initial["vertices"], dtype=np.float64)
            submitted_values = np.asarray(payload[modes[0]], dtype=np.float64)
        spec = read(Path(state["source_spec"]))
        maximum_cumulative = float(spec["max_cumulative_displacement_m"])
        maximum_operation = float(spec.get("max_operation_displacement_m", maximum_cumulative))
        if not np.isfinite(maximum_cumulative + maximum_operation) or min(maximum_cumulative, maximum_operation) <= 0:
            raise ValueError("positive_finite_displacement_budgets_required")
        with np.load(state["current_npz"], allow_pickle=False) as current:
            current_positions = np.asarray(current["vertices_world"] if "vertices_world" in current else current["vertices"], dtype=np.float64)
        requested = submitted_values if modes[0] == "positions_world" else current_positions[ids] + submitted_values
        if np.linalg.norm(requested-current_positions[ids], axis=1).max() > maximum_operation:
            raise ValueError("submitted_operation_exceeds_fixed_displacement_budget")
        if np.linalg.norm(requested-initial_positions[ids], axis=1).max() > maximum_cumulative:
            raise ValueError("submitted_cumulative_displacement_exceeds_fixed_budget")
        number = len(state["operations"]) + 1
        output = directory / "versions" / str(number).zfill(3)
        output.mkdir(parents=True, exist_ok=False)
        label = hashlib.sha256((directory.name + ":" + operation_id).encode()).hexdigest()[:16]
        state["pending"] = dict(operation_id=operation_id, payload_sha256=digest, expected_version=expected_version,
            directory=str(output), job_label="e" + label, current_input_identity=identity(state["current_blend"]))
        write(state_path(directory), state)
        try:
            run_job("blender_edit.py", dict(current_blend=state["current_blend"], output_blend=str(output / "model.blend"),
                object_name=spec["object_name"], source_original=spec["source_original"], base_npz=state["initial_npz"],
                allowed_ids_path=state["initial_npz"], edit_payload=str(payload_path), operation_id=operation_id,
                expected_input_sha256=state["pending"]["current_input_identity"]["sha256"]), "e" + label)
        except BaseException as exception:
            error = dict(type=type(exception).__name__, message=str(exception))
            write(output / "WRITER_EXCEPTION.json", error)
            if not (output / "model.blend").exists():
                failure = dict(operation_id=operation_id, payload_sha256=digest, expected_version=expected_version,
                    version=state["version"], status="writer_failed_without_saved_output", error=error)
                state["operations"].append(failure)
                state["pending"] = None
                write(state_path(directory), state)
                return failure
            final = finish_pending(directory, state, error)
        else:
            final = finish_pending(directory, state)
        state = read(state_path(directory))
        state["current_blend_identity"] = identity(state["current_blend"])
        write(state_path(directory), state)
        final["submit_wall_s"] = time.perf_counter() - started
        write(output / "OPERATION.json", final)
        return final


def save_readback(directory):
    directory = Path(directory).resolve()
    with session_lock(directory):
        state = read(state_path(directory))
        if state.get("pending"):
            raise RuntimeError("pending_edit_requires_state_recovery")
        number = state.get("next_readback_attempt", 1)
        if type(number) is not int or number < 1:
            raise ValueError("invalid_next_readback_attempt")
        while True:
            output = directory / "readbacks" / str(number).zfill(3)
            label = "q" + hashlib.sha256((directory.name + ":" + str(number)).encode()).hexdigest()[:16]
            if not output.exists() and not (HERE / "private/jobs" / label).exists():
                break
            number += 1
        state["next_readback_attempt"] = number + 1
        write(state_path(directory), state)
        result, quality = read_actual(directory, state, state["current_blend"], label, output)
        final = dict(version=state["version"], saved_blend=identity(state["current_blend"]),
            readback=identity(output / "readback.npz"), independently_reopened=True, quality=short_quality(quality),
            quality_record=str(output / "QUALITY.json"), reader_job=label)
        write(output / "READBACK.json", final)
        return final


def focus(directory):
    from facts_api import focus as current_focus
    return current_focus(Path(directory), load_state(directory))


def resolve_ref(directory, reference):
    from facts_api import resolve_ref as current_resolve
    return current_resolve(Path(directory), load_state(directory), reference)


def project_sections(directory):
    from facts_api import project_sections as current_sections
    return current_sections(Path(directory), load_state(directory))
