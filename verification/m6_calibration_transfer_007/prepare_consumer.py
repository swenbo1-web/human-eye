"""Prepare neutral current-only consumer inputs without starting a model."""

import hashlib
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
import numpy as np


def absolute(value):
    path = Path(value)
    return path if path.is_absolute() else HERE / path


def main():
    started, cpu = time.perf_counter(), time.process_time()
    source = read("SOURCE_INPUT_BINDING.json")
    case = HERE / "private/consumer_cases/sample_07"
    session = HERE / "private/sessions/raw_sample_07_facts"
    case.mkdir(parents=True, exist_ok=False)
    images = case / "images"
    images.mkdir()
    rows = []
    for item in source["all_images"]:
        path = absolute(item["path"])
        if identity(path)["sha256"] != item["sha256"]:
            raise ValueError("input_image_identity_changed")
        destination = images / (item["role"] + ".png")
        shutil.copyfile(path, destination)
        rows.append(dict(item, path=destination.relative_to(case).as_posix()))
    initial = source["initial"]
    packet = absolute(initial["packet"]["path"])
    with np.load(packet, allow_pickle=False) as archive:
        arrays = dict(archive)
    forbidden = {"target", "clean_vertices", "reference_vertices", "support_mask", "damage_mask", "generation_parameters"}
    if forbidden.intersection(arrays):
        raise ValueError("private_fields_in_current_input")
    F, I = arrays["F_source_ids"], arrays["I_ids"]
    spec = read(absolute(initial["spec"]["path"]))
    task = dict(task_id="sample_07", objective="Repair the local depression inside the supplied target region from the normal PNG reference and submit one calibratable proposal.",
        input_source="Actual saved current mesh, freshly read from its isolated Blender file", input_reference="input.npz",
        source_points=len(arrays["source_ids"]), triangles=len(arrays["faces"]), observation_points=len(F), editable_points=len(I),
        units=dict(length="source_native", physical_scale="unlabelled", legacy_length_fields="The suffix _m denotes source_native values in this case."),
        region_scope="F_ids is the provided target scope. I_ids is its editable interior. Determine the visible part and active subset from the supplied views and current geometry.",
        max_operation_displacement_m=spec["max_operation_displacement_m"],
        max_cumulative_displacement_m=spec["max_cumulative_displacement_m"],
        image_count=len(rows), images=rows,
        view_aliases="whole_front and forearm_* are inherited protocol aliases for whole-object and three local cameras. They do not identify a body part.",
        numerical_image_access="read_image_pixels(role) returns bound normal/current uint8 RGB. image_cameras includes each actual orthographic projection and camera matrix in continuous top-left image-edge coordinates.",
        available_geometry="Current full V, initial damaged V0, source_ids, faces, F_ids, I_ids, protected_ids and measured current n0. Only I_ids are editable.",
        analysis_requirements="Inspect actual PNGs, calculate a sparse proposal from current data, retain actual code and diagnostics, make one final submission, and inspect the actual saved readback and saved-model images.",
        final_answer="Report execution and visual target assessment with actual operation/version/save/readback references, active subset, calculation basis and remaining uncertainty. Private target scoring runs after this session.")
    write(case / "task.json", task)
    shutil.copyfile(packet, case / "input.npz")
    session.mkdir(parents=True, exist_ok=False)
    (session / "payloads").mkdir()
    shutil.copyfile(absolute(initial["blend"]["path"]), session / "before.blend")
    write(session / "session.json", dict(case_id="sample_07", route="facts", stage="raw", version=0,
        source_spec=str(absolute(initial["spec"]["path"])), initial_npz=str(packet), current_npz=str(packet),
        current_scene=str(absolute(initial["scene"]["path"])), current_blend=str(session / "before.blend"),
        current_blend_identity=identity(session / "before.blend"), operations=[], pending=None, next_readback_attempt=1))
    config = dict(model="gpt-6.1-sol", reasoning_effort="medium", max_tool_calls=12, max_session_seconds=600,
        image_transport="mcp", python_timeout_s=45, python_output_chars=5000, fact_output_chars=18000,
        answer_schema=dict(task_id="sample_07", execution_status="complete or incomplete with actual operation evidence",
            decision_status="observed visual restoration or incomplete/unknown", modification_decision="edit or no_edit",
            visual_evidence="matched PNG observations and visible part name", active_region="computed source subset or region reference",
            fit_audit="actual diagnostic files and solver basis, or reason unused", operation_id="actual ID or null",
            version="actual final saved version", saved_blend="actual saved artifact", readback="independent actual saved mesh",
            target_result="observed result", remaining_issues="remaining uncertainty"))
    write("CONSUMER_PLAN.json", dict(cycle_id="M6-CALIBRATION-TRANSFER-007", consumer=config,
        sequence=[dict(stage="raw", task_id="sample_07", route="facts")], actual_session_limit=1,
        unit="source_native_physical_length_unlabelled", inherited_correspondence_core_budget=69,
        candidate_domain=274, inherited_correspondence_radius_source_native=.032, hidden_geometry_in_consumer=False))
    input_files = [case / "task.json", case / "input.npz", session / "before.blend", HERE / "CAMERAS.json"]
    input_files += [case / row["path"] for row in rows]
    write("CONSUMER_INPUT_FREEZE.json", dict(files=[identity(path) for path in input_files],
        scope="Neutral task, actual damaged current packet, owned initial blend, actual bound PNG bytes and frozen cameras. Mutable session state is excluded."))
    write("CONSUMER_PREPARATION.json", dict(status="pass", task=identity(case / "task.json"), input=identity(case / "input.npz"),
        initial_blend=identity(session / "before.blend"), image_count=len(rows), hidden_geometry_in_public_packet=False,
        array_names=sorted(arrays), neutral_task_id="sample_07", raw_session=str(session), new_Pro_sessions=0, new_Blender_calls=0,
        wall_s=time.perf_counter()-started, CPU_s=time.process_time()-cpu))
    print("neutral consumer case and untouched raw session prepared")


if __name__ == "__main__":
    main()
