"""Three fixed-amplitude saved-file candidates selected by matched RGB error."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job
from session_api import load_state, session_lock, submit_edit
from image_metric import measure_images
import numpy as np


ALPHAS = (0.0, 0.5, 1.0)
TAGS = ("a0", "a05", "a1")
RUNTIME_SOURCES = ("calibrator.py", "calibration_protocol.py", "session_api.py", "background.py", "common.py", "blender_common.py",
    "blender_edit.py", "blender_read.py", "blender_render.py", "evaluate.py", "quality.py", "image_metric.py", "image_inputs.py")


def absolute(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (HERE / path).resolve()


def checked_identity(expected):
    path = absolute(expected["path"])
    actual = identity(path)
    if actual["sha256"] != expected["sha256"] or actual["bytes"] != expected["bytes"]:
        raise ValueError("bound_file_identity_changed_" + str(path))
    return path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def request_for(proposal_id, stage="v1"):
    source = read("SOURCE_BINDING.json")
    proposal = next((row for row in source["proposals"] if row["proposal_id"] == proposal_id), None)
    if proposal is None:
        raise ValueError("unknown_fixed_proposal")
    return dict(stage=stage, proposal_id=proposal_id, source_binding=identity(HERE / "SOURCE_BINDING.json"),
        initial_ref=source["initial"], proposal_ref=proposal["payload"], normal_refs=source["images"]["normal"],
        current_refs=source["images"]["current"], camera_views=source["views"])


def validate_request(request, *, extra_sources=()):
    stage, proposal_id = request.get("stage"), request.get("proposal_id")
    if stage not in ("v1", "v2"):
        raise ValueError("calibration_stage_requires_v1_or_v2")
    expected = request_for(proposal_id, stage)
    if request != expected:
        raise ValueError("request_references_differ_from_fixed_source_binding")
    source = read(checked_identity(request["source_binding"]))
    if tuple(source.get("alphas", ALPHAS)) != ALPHAS:
        raise ValueError("fixed_three_alpha_contract_changed")
    proposal = next(row for row in source["proposals"] if row["proposal_id"] == proposal_id)
    for item in request["initial_ref"].values():
        checked_identity(item)
    checked_identity(source["original"])
    payload_path = checked_identity(request["proposal_ref"])
    for row in request["normal_refs"] + request["current_refs"]:
        checked_identity(row)
    with np.load(payload_path, allow_pickle=False) as payload, np.load(checked_identity(request["initial_ref"]["packet"]), allow_pickle=False) as initial:
        if set(payload.files) != {"source_ids", "displacements_world"}:
            raise ValueError("fixed_proposal_requires_world_displacements")
        ids, delta = payload["source_ids"], payload["displacements_world"]
        if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer) or len(ids) != proposal["points"]:
            raise ValueError("fixed_proposal_source_domain_changed")
        if len(np.unique(ids)) != len(ids) or not np.isin(ids, initial["I_ids"]).all():
            raise ValueError("fixed_proposal_outside_edit_domain")
        if delta.shape != (len(ids), 3) or not np.isfinite(delta).all():
            raise ValueError("finite_fixed_displacements_required")
    sources = [identity(HERE / name) for name in RUNTIME_SOURCES + tuple(extra_sources)]
    binding = dict(request=request, alphas=list(ALPHAS), runtime_sources=sources,
        metric="Three matched 640x640 local views, all 3686400 RGB values, pooled absolute error sum, normalized to current",
        selection="Eligible technical pass with minimum integer RGB error sum, exact tie smaller alpha")
    return source, proposal, ids, delta, binding


def session_directory(stage, proposal_id, tag):
    return HERE / "private/sessions" / (stage + "_" + proposal_id + "_" + tag)


def initialize_session(source, stage, proposal_id, tag):
    directory = session_directory(stage, proposal_id, tag)
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "session.json"
    initial = source["initial"]
    if state_path.exists():
        state = read(state_path)
        if absolute(state["initial_npz"]) != checked_identity(initial["packet"]) or absolute(state["source_spec"]) != checked_identity(initial["spec"]):
            raise ValueError("owned_session_initial_binding_changed")
        if identity(directory / "before.blend")["sha256"] != initial["blend"]["sha256"]:
            raise ValueError("owned_session_initial_blend_changed")
        return directory
    (directory / "payloads").mkdir(exist_ok=True)
    before = directory / "before.blend"
    if before.exists():
        if identity(before)["sha256"] != initial["blend"]["sha256"]:
            raise ValueError("partial_session_initial_blend_changed")
    else:
        shutil.copyfile(checked_identity(initial["blend"]), before)
    write(state_path, dict(case_id="repair", route=proposal_id, stage=stage, calibration_alpha_tag=tag,
        version=0, source_spec=str(checked_identity(initial["spec"])), initial_npz=str(checked_identity(initial["packet"])),
        current_npz=str(checked_identity(initial["packet"])), current_scene=str(checked_identity(initial["scene"])),
        current_blend=str(before), current_blend_identity=identity(before), operations=[], pending=None, next_readback_attempt=1))
    return directory


def scaled_payload(directory, proposal, ids, delta, alpha):
    path = directory / "payloads/scaled.npz"
    expected = alpha * delta
    if path.exists():
        with np.load(path, allow_pickle=False) as payload:
            if set(payload.files) != {"source_ids", "displacements_world"} or payload["source_ids"].tobytes() != ids.tobytes() or payload["displacements_world"].tobytes() != expected.tobytes():
                raise ValueError("owned_scaled_payload_changed")
    elif alpha == 1.0:
        shutil.copyfile(checked_identity(proposal["payload"]), path)
    else:
        np.savez_compressed(path, source_ids=ids, displacements_world=expected)
    return path


def verify_native(initial_path, actual_path, ids, values, alpha):
    with np.load(initial_path, allow_pickle=False) as initial, np.load(actual_path, allow_pickle=False) as actual:
        expected = initial["vertices_local"].copy()
        inverse = np.linalg.inv(initial["matrix_world"])
        requested = initial["vertices_world"][ids] + values
        expected[ids] = (requested @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.float32)
        checks = dict(exact_requested_native_float32=expected.tobytes() == actual["vertices_local"].tobytes(),
            alpha_zero_is_current_native=alpha != 0 or initial["vertices_local"].tobytes() == actual["vertices_local"].tobytes())
        for key in ("source_ids", "matrix_world", "poly_offsets", "poly_vertices", "faces", "triangle_polygon_ids"):
            checks[key] = initial[key].dtype == actual[key].dtype and initial[key].shape == actual[key].shape and initial[key].tobytes() == actual[key].tobytes()
        maximum_error = float(np.linalg.norm(actual["vertices_world"][ids] - requested, axis=1).max())
    return dict(status="pass" if all(checks.values()) else "fail", checks=checks, maximum_saved_world_quantization_error_m=maximum_error)


def ensure_render(job, label):
    folder = HERE / "private/jobs" / label
    if not folder.exists():
        return run_job("blender_render.py", job, label), False
    expected = dict(job, receipt_path=str(folder / "receipt.json"))
    if read(folder / "job.json") != expected:
        raise ValueError("owned_render_job_binding_changed")
    if not (folder / "receipt.json").exists():
        raise RuntimeError("owned_render_receipt_missing_query_state_before_recovery")
    if (folder / "run.json").exists():
        record = read(folder / "run.json")
    else:
        process = read(HERE / "private/processes" / ("b_" + label + ".json"))
        if process.get("status") != "completed" or process.get("returncode") != 0:
            raise RuntimeError("owned_render_process_requires_inspection")
        record = dict(label=label, script=identity(HERE / "blender_render.py"), job=identity(folder / "job.json"),
            process=process, receipt=read(folder / "receipt.json"), receipt_path=str(folder / "receipt.json"),
            wall_s=process["full_process_wall_s"], recovered_from_completed_process_record=True)
        write(folder / "run.json", record)
    checked_identity(record["script"])
    checked_identity(record["job"])
    if record["process"].get("returncode") != 0 or record["receipt"] != read(folder / "receipt.json"):
        raise ValueError("owned_render_process_or_receipt_invalid")
    return record, True


def rendered_rows(record, source, saved_blend):
    receipt = record["receipt"]
    if receipt["status"] != "rendered_actual_saved_full_character" or receipt["current_blend"]["sha256"] != saved_blend["sha256"]:
        raise ValueError("render_receipt_saved_model_mismatch")
    if receipt["geometry_scale"] != 1 or receipt["displacement_scale"] != 1 or receipt["scene_changes_saved"]:
        raise ValueError("render_scale_or_saved_scene_mismatch")
    if len(receipt["views"]) != 3:
        raise ValueError("three_local_render_views_required")
    reference = {row["role"].removeprefix("normal_"): row for row in source["images"]["normal"]}
    rows = []
    for specification, view in zip(source["views"], receipt["views"]):
        camera = {key: view[key] for key in ("specification", "camera_matrix_world", "world_to_image_affine_2_by_3", "world_to_image_offset", "pixel_convention")}
        if view["specification"] != specification or camera != reference[specification["name"]]["camera"]:
            raise ValueError("candidate_camera_differs_from_frozen_reference")
        path = checked_identity(view["image"])
        rows.append(dict(path=str(path), bytes=view["image"]["bytes"], sha256=view["image"]["sha256"],
            role="current_" + specification["name"], camera=camera))
    return rows


def execute_candidate(source, proposal, ids, delta, stage, alpha, tag, progress):
    directory = initialize_session(source, stage, proposal["proposal_id"], tag)
    payload = scaled_payload(directory, proposal, ids, delta, alpha)
    operation_id = "calibrate_" + stage + "_" + proposal["proposal_id"] + "_" + tag
    progress.update(status="submit_or_recover", session=str(directory), payload=identity(payload))
    operation = submit_edit(directory, payload, 0, operation_id)
    if operation["status"] != "saved_and_independently_read":
        raise RuntimeError("candidate_write_failed_actual_state_preserved")
    state = load_state(directory)
    saved = operation["saved_blend"]
    checked_identity(saved)
    checked_identity(operation["readback"])
    native = verify_native(state["initial_npz"], absolute(operation["readback"]["path"]), ids, alpha * delta, alpha)
    progress.update(status="render_or_recover", operation=operation, native_verification=native)
    label = "cr" + hashlib.sha256((directory.name + ":" + saved["sha256"]).encode()).hexdigest()[:16]
    spec = read(state["source_spec"])
    job = dict(current_blend=str(absolute(saved["path"])), source_original=spec["source_original"],
        object_name=spec["object_name"], output_dir=str(directory / "calibration_render/images"), views=source["views"])
    render, reused = ensure_render(job, label)
    images = rendered_rows(render, source, saved)
    readback_path = absolute(operation["readback"]["path"])
    quality = identity(absolute(operation["quality_record"]))
    technical = operation["quality"]["status"] == "pass" and native["status"] == "pass"
    return dict(alpha=alpha, alpha_tag=tag, status="complete", technical_status="pass" if technical else "fail",
        session=str(directory), payload=identity(payload), saved_blend=saved, readback=identity(readback_path),
        scene=identity(readback_path.parent / "scene.json"), quality=quality, operation=operation,
        reader_receipt=identity(HERE / "private/jobs" / operation["reader_job"] / "receipt.json"),
        native_verification=native, images=images, render_job=label, render_reused=reused,
        render_receipt=identity(HERE / "private/jobs" / label / "receipt.json"),
        render_run=identity(HERE / "private/jobs" / label / "run.json"))


def select_candidate(candidates):
    eligible = [row for row in candidates if row.get("technical_status") == "pass" and row.get("image", {}).get("status") == "pass"]
    return min(eligible, key=lambda row: (row["image"]["absolute_error_sum"], row["alpha"])) if eligible else None


def verify_candidate(candidate):
    for key in ("payload", "saved_blend", "readback", "scene", "quality", "reader_receipt", "render_receipt", "render_run"):
        checked_identity(candidate[key])
    for row in candidate["images"]:
        checked_identity(row)
    checked_identity(candidate["image"]["decoded_RGB_npz"])


def verify_cached_result(result):
    for candidate in result["candidates"]:
        verify_candidate(candidate)


def selection_freeze(result_path, binding_sha256):
    name = result_path.name.replace("CALIBRATION_", "IMAGE_SELECTION_FREEZE_", 1)
    path = HERE / name
    if path.exists():
        frozen = read(path)
        checked_identity(frozen["image_result"])
        if frozen["binding_sha256"] != binding_sha256:
            raise ValueError("image_selection_freeze_binding_changed")
    else:
        write(path, dict(status="image_selection_frozen", image_result=identity(result_path),
            binding_sha256=binding_sha256, frozen_epoch=time.time(),
            inputs="Actual candidate images, fixed pooled RGB metric and technical status only",
            private_target_read_by_calibrator=False))
    return identity(path)


def status(request):
    validate_request(request)
    directory = HERE / "private/calibrations" / (request["stage"] + "_" + request["proposal_id"])
    path = directory / "STATE.json"
    sessions = {tag: read(session_directory(request["stage"], request["proposal_id"], tag) / "session.json")
        for tag in TAGS if (session_directory(request["stage"], request["proposal_id"], tag) / "session.json").exists()}
    return dict(status="not_started" if not path.exists() else "state_present", state=read(path) if path.exists() else None, sessions=sessions,
        result=identity(HERE / ("CALIBRATION_" + request["stage"] + "_" + request["proposal_id"] + ".json"))
        if (HERE / ("CALIBRATION_" + request["stage"] + "_" + request["proposal_id"] + ".json")).exists() else None)


def calibrate(request, *, candidate_executor=execute_candidate, extra_sources=(), image_cache=None):
    started, cpu = time.perf_counter(), time.process_time()
    source, proposal, ids, delta, binding = validate_request(request, extra_sources=extra_sources)
    stage, proposal_id = request["stage"], request["proposal_id"]
    if stage != "v1" and candidate_executor is execute_candidate:
        raise ValueError("stage_v2_requires_its_frozen_optimized_backend")
    directory = HERE / "private/calibrations" / (stage + "_" + proposal_id)
    directory.mkdir(parents=True, exist_ok=True)
    result_path = HERE / ("CALIBRATION_" + stage + "_" + proposal_id + ".json")
    with session_lock(directory):
        binding_path = directory / "BINDING.json"
        if binding_path.exists() and read(binding_path) != binding:
            raise ValueError("calibration_input_or_runtime_binding_changed")
        if not binding_path.exists():
            write(binding_path, binding)
        if result_path.exists():
            result = read(result_path)
            if result["binding_sha256"] != digest(binding):
                raise ValueError("cached_result_binding_changed")
            verify_cached_result(result)
            freeze = selection_freeze(result_path, digest(binding))
            return dict(reused=True, result_reference=identity(result_path), result=result,
                image_selection_freeze=freeze, call_wall_s=time.perf_counter() - started,
                call_CPU_s=time.process_time() - cpu, new_Blender_jobs=0)
        state_path = directory / "STATE.json"
        state = read(state_path) if state_path.exists() else dict(status="running", binding_sha256=digest(binding), candidates={})
        candidates = []
        for alpha, tag in zip(ALPHAS, TAGS):
            progress = state["candidates"].setdefault(tag, dict(alpha=alpha, status="not_started"))
            write(state_path, state)
            try:
                if progress["status"] == "complete":
                    row = progress["result"]
                    verify_candidate(row)
                else:
                    row = candidate_executor(source, proposal, ids, delta, stage, alpha, tag, progress)
                    write(state_path, state)
                    row["image"] = measure_images(source["images"]["normal"], row["images"],
                        output_dir=absolute(row["session"]) / "image_measurement", cache=image_cache)
                progress.update(status="complete", result=row)
            except Exception as error:
                row = dict(alpha=alpha, alpha_tag=tag, status="failed", technical_status="unknown",
                    error=dict(type=type(error).__name__, message=str(error)), actual_state=dict(progress))
                progress.update(status="failed", error=row["error"])
            candidates.append(row)
            write(state_path, state)
        if any(row["status"] != "complete" for row in candidates):
            state["status"] = "candidate_execution_incomplete_query_owned_state"
            write(state_path, state)
            raise RuntimeError("candidate_execution_incomplete_actual_state_preserved")
        baseline = next((row["image"] for row in candidates if row["alpha"] == 0 and row.get("image", {}).get("status") == "pass"), None)
        if baseline is None:
            baseline = measure_images(source["images"]["normal"], source["images"]["current"], output_dir=directory / "baseline_measurement", cache=image_cache)
        for row in candidates:
            if "image" in row:
                row["normalized_to_initial"] = row["image"]["absolute_error_sum"] / baseline["absolute_error_sum"] if baseline["absolute_error_sum"] else None
        selected = select_candidate(candidates)
        result = dict(cycle_id="M6-CALIBRATION-TRANSFER-007", stage=stage, proposal_id=proposal_id,
            status="image_selection_frozen" if selected else "no_technically_eligible_candidate", binding_sha256=digest(binding),
            binding=identity(binding_path), candidates=candidates, baseline_image=baseline,
            selected_alpha=selected["alpha"] if selected else None,
            selected=dict(alpha=selected["alpha"], saved_blend=selected["saved_blend"], payload=selected["payload"],
                readback=selected["readback"], images=selected["images"], technical_status=selected["technical_status"],
                absolute_error_sum=selected["image"]["absolute_error_sum"], normalized_to_initial=selected["normalized_to_initial"]) if selected else None,
            image_selection_frozen_epoch=time.time(), independent_geometry_scoring="pending_separate_private_scorer",
            source_model_assessment="Frozen original proposal from the single new Pro session; this caller is a deterministic protocol client",
            wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu,
            actual_Pro_calls=0, training_calls=0, paid_API_calls=0)
        write(result_path, result)
        freeze = selection_freeze(result_path, digest(binding))
        state.update(status=result["status"], result=identity(result_path), image_selection_freeze=freeze)
        write(state_path, state)
    return dict(reused=False, result_reference=identity(result_path), result=result,
        image_selection_freeze=freeze, call_wall_s=time.perf_counter() - started, call_CPU_s=time.process_time() - cpu)
