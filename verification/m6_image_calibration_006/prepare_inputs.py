"""Bind fixed historical proposals and minimal owned calibration inputs."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
import numpy as np


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "SOURCE_BINDING.json").exists():
        raise RuntimeError("fixed_inputs_already_bound")
    old = HERE.parent / "m6_image_correspondence_005"
    commit = "644012279d8c0d43e2bee9d8b5d38ea30195e5da"
    manifest_raw = subprocess.check_output(["git", "show", commit + ":verification/m6_image_correspondence_005/MANIFEST.json"], cwd=HERE.parents[1])
    manifest = {row["path"]: row for row in json.loads(manifest_raw)["files"]}

    def fixed(path):
        actual = identity(old / path)
        expected = manifest[path]
        if any(actual[key] != expected[key] for key in ("bytes", "sha256")):
            raise ValueError("fixed_005_source_changed_" + path)
        return actual

    directory = HERE / "private/input"
    directory.mkdir(parents=True, exist_ok=False)
    proposals = []
    source_rows = []
    for proposal_id, session_name, count in (("v1_native", "v1_repair_native", 40), ("v2_facts", "v2_repair_facts", 107)):
        state_name = "private/sessions/" + session_name + "/session.json"
        source_rows.append(fixed(state_name))
        state = read(old / state_name)
        operation = state["operations"][0]
        if len(state["operations"]) != 1 or state["version"] != 1:
            raise ValueError("fixed_single_proposal_operation_required")
        paths = sorted(name for name, row in manifest.items() if row["sha256"] == operation["payload_sha256"]
                       and name.startswith("private/sessions/" + session_name + "/payloads/") and name.endswith(".npz"))
        if len(paths) != 1:
            raise ValueError("unique_manifest_payload_required")
        source = fixed(paths[0])
        destination = directory / "proposals" / (proposal_id + ".npz")
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(old / paths[0], destination)
        with np.load(destination, allow_pickle=False) as archive:
            if set(archive.files) != {"source_ids", "displacements_world"} or len(archive["source_ids"]) != count:
                raise ValueError("fixed_proposal_schema_or_count_changed")
        proposals.append(dict(proposal_id=proposal_id, payload=identity(destination), source_payload=source, points=count,
            source_session=source_rows[-1], source_operation=operation))
    original_case = read(old / "CASE_BINDING.json")
    original = original_case["original"]
    if identity(original["path"])["sha256"] != original["sha256"]:
        raise ValueError("original_asset_changed")
    blend = directory / "before.blend"
    base_source = fixed("private/cases/repair/before.blend")
    shutil.copyfile(old / "private/cases/repair/before.blend", blend)
    packet, scene = fixed("private/cases/repair/initial.npz"), fixed("private/cases/repair/baseline_scene.json")
    source_spec = fixed("private/cases/repair/spec.json")
    spec = read(old / "private/cases/repair/spec.json")
    spec.update(base_blend_path=str(blend), initial_npz=packet["path"], baseline_scene=scene["path"])
    write(directory / "spec.json", spec)
    images_binding = read(old / "IMAGE_BINDING.json")
    source_image_binding = fixed("IMAGE_BINDING.json")
    rows = images_binding["images"]
    selected = {}
    views = []
    for role in ("normal", "current"):
        selected[role] = []
        for view in ("forearm_front", "forearm_side", "forearm_45"):
            row = next(item for item in rows if item["role"] == role + "_" + view)
            path = Path(row["path"])
            source = fixed(path.relative_to(old).as_posix())
            if source["sha256"] != row["sha256"]:
                raise ValueError("fixed_PNG_binding_changed")
            selected[role].append(row)
            if role == "current":
                views.append(row["camera"]["specification"])
    if any(selected["normal"][index]["camera"] != selected["current"][index]["camera"] for index in range(3)):
        raise ValueError("matched_camera_required")
    binding = dict(cycle_id="M6-IMAGE-CALIBRATION-006", baseline_commit=commit,
        contract_commit="0b681d1315f99be1856835fa4336e8e852d14a2b", original=original,
        initial=dict(blend=identity(blend), packet=packet, scene=scene, spec=identity(directory / "spec.json")),
        source_initial_blend=base_source, source_initial_spec=source_spec,
        proposals=proposals, images=selected, views=views, source_image_binding=source_image_binding,
        source_case_binding=fixed("CASE_BINDING.json"), alphas=[0, .5, 1],
        displacement_budget_m=.006893660855829761, observed_F_points=410, editable_I_points=274,
        image_sample_count=3686400, actual_Pro_calls=0, actual_Blender_calls=0,
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu)
    write("SOURCE_BINDING.json", binding)
    target = fixed("private/scoring/target.npz")
    write("SCORING_BINDING.json", dict(cycle_id="M6-IMAGE-CALIBRATION-006", target=target,
        fixed_source_commit=commit, isolation="Only the independent private scorer reads this binding after image selection is frozen."))
    planning = Path("C:/Users/Administrator/.codex/worktrees/1212/hefe/verification/m6_image_correspondence_005_review")
    midpoint_rows = []
    for row in read("MIDPOINT_MANIFEST.json")["files"]:
        source = planning / row["path"]
        actual = identity(source)
        if actual["bytes"] != row["bytes"] or actual["sha256"] != row["sha256"]:
            raise ValueError("fixed_MIDPOINT_member_changed_" + row["path"])
        midpoint_rows.append(actual)
    write("MIDPOINT_SOURCE_BINDING.json", dict(planning_commit="0b681d1315f99be1856835fa4336e8e852d14a2b",
        source_directory=str(planning), files=midpoint_rows, file_count=len(midpoint_rows),
        bytes=sum(row["bytes"] for row in midpoint_rows), copied_private_history=False,
        image_result=identity(HERE / "MIDPOINT_IMAGE_RESULT.json"),
        actual_Pro_calls=0, actual_Blender_calls=0))
    print("two fixed proposals, shared inputs and 27 MIDPOINT reference identities bound")


if __name__ == "__main__":
    main()
