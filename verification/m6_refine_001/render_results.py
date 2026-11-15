"""Render terminal consumer sessions with the frozen actual-scale cameras."""

import argparse
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from background import run_job
from common import identity, read, write


def absolute(path):
    path = Path(path)
    return path.resolve() if path.is_absolute() else (HERE / path).resolve()


def describe(path):
    return dict(identity(path), absolute_path=str(absolute(path)))


def copy_verified(source, destination):
    source, destination = absolute(source), absolute(destination)
    original = describe(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if identity(destination)["sha256"] != original["sha256"]:
            raise ValueError("existing_result_copy_differs_" + str(destination))
    else:
        shutil.copyfile(source, destination)
    copied = describe(destination)
    if copied["sha256"] != original["sha256"]:
        raise ValueError("result_copy_hash_mismatch")
    return dict(source=original, output=copied, sha256_equal=True,
                additional_Blender_render_wall_s=0.)


def verify_frozen(stage, spec_path):
    freeze = read("TOOL_FREEZE_v2.json" if stage == "v2" else "TOOL_FREEZE.json")
    required = {"common.py", "background.py", "blender_common.py", "blender_render.py", "blender_read.py"}
    rows = [row for row in freeze["files"] if row["path"] in required]
    if len(rows) != len(required):
        raise ValueError("render_backend_missing_from_stage_freeze")
    spec_relative = spec_path.relative_to(HERE).as_posix()
    rows += [row for row in read("PLAN_FREEZE.json")["files"] if row["path"] == spec_relative]
    if len(rows) != len(required) + 1:
        raise ValueError("camera_spec_missing_from_plan_freeze")
    for row in rows:
        if identity(absolute(row["path"]))["sha256"] != row["sha256"]:
            raise ValueError("frozen_render_dependency_changed_" + row["path"])
    return rows


def terminal_sessions(stage):
    routes = [("s01", "native"), ("s01", "facts"), ("s02", "facts"), ("s02", "native")]
    if stage == "v2":
        routes = [("s02", "facts"), ("s01", "facts")]
    sessions = []
    for case_id, route in routes:
        directory = HERE / "private/sessions" / (stage + "_" + case_id + "_" + route)
        consumer_path = HERE / "private/consumers" / stage / case_id / route / "CONSUMER.json"
        if not consumer_path.exists() or read(consumer_path).get("status") not in ("completed", "failed"):
            raise RuntimeError("consumer_session_still_active_or_unstarted_" + directory.name)
        state = read(directory / "session.json")
        if state.get("pending"):
            raise RuntimeError("consumer_session_has_pending_edit_" + directory.name)
        if (state["stage"], state["case_id"], state["route"]) != (stage, case_id, route):
            raise ValueError("session_identity_mismatch")
        current = identity(state["current_blend"])
        if current["sha256"] != state["current_blend_identity"]["sha256"]:
            raise ValueError("terminal_session_saved_blend_identity_mismatch")
        sessions.append((directory, consumer_path, state))
    return sessions


def publish_images(receipt, directory):
    copies = []
    for row in receipt["images"]:
        source = absolute(row["image"]["path"])
        if identity(source)["sha256"] != row["image"]["sha256"]:
            raise ValueError("rendered_png_changed_before_publication")
        copies.append(copy_verified(source, directory / source.name))
    return copies


def render_session(directory, consumer_path, state, reference_renders):
    started, cpu = time.perf_counter(), time.process_time()
    case_id = state["case_id"]
    output = HERE / "private/results" / directory.name
    result_path = output / "result.json"
    before_blend = directory / "before.blend"
    after_blend = absolute(state["current_blend"])
    spec_path = HERE / "private/reference" / case_id / "render_spec_v2_16_4.json"
    frozen = verify_frozen(state["stage"], spec_path)
    session_identity = identity(directory / "session.json")
    current_identity = identity(after_blend)
    if result_path.exists():
        result = read(result_path)
        if result["session_state"]["sha256"] != session_identity["sha256"] or result["after_blend"]["sha256"] != current_identity["sha256"]:
            raise ValueError("previously_rendered_terminal_session_changed")
        for row in result["before_images"] + result["after_images"]:
            if identity(absolute(row["output"]["path"]))["sha256"] != row["output"]["sha256"]:
                raise ValueError("previously_published_render_changed")
        return result
    output.mkdir(parents=True, exist_ok=True)
    attempt_number = len(list(output.glob("attempt_*")))
    attempt = output / ("attempt_" + str(attempt_number).zfill(2))
    attempt.mkdir()
    spec = read(state["source_spec"])
    common_job = dict(case_id=case_id, object_name=spec["object_name"],
        base_npz=state["initial_npz"], source_original=spec["source_original"], render_spec=str(spec_path))
    jobs = []
    baseline = reference_renders[case_id]
    same_before = identity(before_blend)["sha256"] == baseline["input_blend"]["sha256"]
    if same_before and baseline["render_spec"] == read(spec_path):
        before_images = publish_images(baseline, output / "before_views")
        before_method = dict(method="copied_verified_identical_baseline_render", full_blend_sha256_equal=True,
            baseline_blend=baseline["input_blend"], session_before_blend=describe(before_blend),
            source_render_spec_sha256=baseline["render_spec_sha256"], additional_Blender_render_wall_s=0.)
    else:
        job = run_job("blender_render.py", dict(common_job, current_blend=str(before_blend),
            output_dir=str(attempt / "before_views")), directory.name + "_result_before_a" + str(attempt_number))
        jobs.append(job)
        before_images = publish_images(job["receipt"], output / "before_views")
        before_method = dict(method="actual_session_before_blend_render", additional_Blender_render_wall_s=job["wall_s"])
    job = run_job("blender_render.py", dict(common_job, current_blend=str(after_blend),
        output_dir=str(attempt / "after_views")), directory.name + "_result_after_a" + str(attempt_number))
    jobs.append(job)
    after_images = publish_images(job["receipt"], output / "after_views")
    before_obj_source = HERE / "private/reference" / case_id / "before_local.obj"
    if not same_before:
        before_job = run_job("blender_read.py", dict(common_job, current_blend=str(before_blend),
            readback_npz=str(attempt / "before_readback.npz"), scene_signature_json=str(attempt / "before_scene.json"),
            local_obj=str(attempt / "before_local.obj")), directory.name + "_result_before_read_a" + str(attempt_number))
        jobs.append(before_job)
        before_obj_source = attempt / "before_local.obj"
    before_obj = copy_verified(before_obj_source, output / "before_local.obj")
    after_obj_source = absolute(state["current_npz"]).parent / "local.obj"
    if not after_obj_source.exists() and identity(after_blend)["sha256"] == identity(before_blend)["sha256"]:
        after_obj_source = before_obj_source
    if not after_obj_source.exists():
        after_job = run_job("blender_read.py", dict(common_job, current_blend=str(after_blend),
            readback_npz=str(attempt / "after_readback.npz"), scene_signature_json=str(attempt / "after_scene.json"),
            local_obj=str(attempt / "after_local.obj")), directory.name + "_result_after_read_a" + str(attempt_number))
        jobs.append(after_job)
        after_obj_source = attempt / "after_local.obj"
    after_obj = copy_verified(after_obj_source, output / "after_local.obj")
    if identity(directory / "session.json") != session_identity or identity(after_blend) != current_identity:
        raise RuntimeError("consumer_session_changed_during_result_render")
    result = dict(session=directory.name, stage=state["stage"], case_id=case_id, route=state["route"], version=state["version"],
        consumer_status=read(consumer_path)["status"], consumer_record=describe(consumer_path),
        session_state=dict(session_identity, absolute_path=str(directory / "session.json")),
        before_blend=describe(before_blend), after_blend=describe(after_blend),
        before_local_obj=before_obj, after_local_obj=after_obj, independent_current_packet=describe(state["current_npz"]),
        before_render=before_method, before_images=before_images, after_images=after_images,
        render_spec=describe(spec_path), renderer=describe(HERE / "blender_render.py"), frozen_dependencies=frozen,
        jobs=jobs, wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu,
        nested_Blender_wall_s=sum(row["wall_s"] for row in jobs),
        Blender_CPU_s=sum(row["process"]["full_process_cpu_s"] for row in jobs),
        peak_Blender_working_set_bytes=max(row["process"]["peak_working_set_bytes"] for row in jobs),
        session_state_unchanged=True, source_geometry_scale=1., displacement_scale=1.,
        display_style="clay_v2, key16/fill4/world.15, 32samples, frozen three initial cameras")
    write(result_path, result)
    print(directory.name, "rendered", len(after_images), "after views", "before", before_method["method"], flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2"), required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    sessions = terminal_sessions(args.stage)
    reference_renders = {}
    for job in read("RENDER_PREFLIGHT.json")["jobs"]:
        if "_before_" in job["label"]:
            reference_renders[job["label"][:3]] = job["receipt"]
    for directory, consumer_path, state in sessions:
        render_session(directory, consumer_path, state, reference_renders)
        rows = [read(path) for path in sorted((HERE / "private/results").glob("v[12]_s0*_*/result.json"))]
        write("VIEWABLES.json", dict(cycle_id="M6-REFINE-001", source=describe(__file__), last_stage=args.stage,
            sessions=rows, session_count=len(rows), image_count=sum(len(row["before_images"])+len(row["after_images"]) for row in rows),
            nested_Blender_wall_s=sum(row["nested_Blender_wall_s"] for row in rows),
            exclusive_result_session_wall_s=sum(row["wall_s"] for row in rows),
            last_invocation_wall_s=time.perf_counter()-started,
            baseline_reuse="full baseline blend SHA and exact render spec checked before copying verified PNGs, additional render cost zero",
            local_OBJ_coordinates="actual independent Blender readback, world coordinates, initial F-contained current loop triangles",
            geometry_scale=1., displacement_scale=1.))


if __name__ == "__main__":
    main()
