"""Reuse the fixed 004 saved case and independently validate both saved states."""

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
from background import run_job
import numpy as np


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "CASE_BINDING.json").exists():
        raise RuntimeError("fixed_case_already_prepared")
    previous = HERE.parent / "m6_degrid_004"
    commit = "6ed6c88e2ae91d08cff1e80fed436d2e3572bf77"
    manifest_bytes = subprocess.check_output(["git", "show", commit + ":verification/m6_degrid_004/MANIFEST.json"], cwd=HERE.parents[1])
    old_manifest = {row["path"]: row for row in json.loads(manifest_bytes)["files"]}
    reused = []

    def copy_fixed(source, destination):
        original = previous / source
        expected = old_manifest[source]
        raw = original.read_bytes()
        if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise ValueError("fixed_004_evidence_changed_" + source)
        target = HERE / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        reused.append(dict(source=identity(original), copied=identity(target)))
        return target

    hidden = HERE / "private/construction"
    case = HERE / "private/cases/repair"
    normal_blend = copy_fixed("private/construction/normal.blend", "private/construction/normal.blend")
    current_blend = copy_fixed("private/cases/repair/before.blend", "private/cases/repair/before.blend")
    initial = copy_fixed("private/cases/repair/initial.npz", "private/cases/repair/initial.npz")
    scene = copy_fixed("private/cases/repair/baseline_scene.json", "private/cases/repair/baseline_scene.json")
    target = copy_fixed("private/scoring/target.npz", "private/scoring/target.npz")
    copy_fixed("private/construction/control_restore.npz", "private/construction/control_restore.npz")
    old_binding = read(previous / "CASE_BINDING.json")
    original = Path(old_binding["original"]["path"])
    if identity(original)["sha256"] != old_binding["original"]["sha256"]:
        raise ValueError("original_asset_changed")
    spec = read(previous / "private/cases/repair/spec.json")
    spec.update(base_blend_path=str(current_blend), initial_npz=str(initial), baseline_scene=str(scene))
    write("private/cases/repair/spec.json", spec)
    jobs = []
    for role, blend, output in (("normal", normal_blend, hidden), ("current", current_blend, case)):
        packet = output / ("normal_readback.npz" if role == "normal" else "actual_initial_readback.npz")
        signature = output / ("normal_scene.json" if role == "normal" else "fresh_scene.json")
        jobs.append(run_job("blender_read.py", dict(current_blend=str(blend), object_name=spec["object_name"],
            source_original=str(original), base_npz=str(initial), expected_input_sha256=identity(blend)["sha256"],
            readback_npz=str(packet), scene_signature_json=str(signature), local_obj=str(output / (role + "_local.obj"))),
            "read_fixed_" + role))
        old_packet = previous / ("private/construction/normal_readback.npz" if role == "normal" else "private/cases/repair/actual_initial_readback.npz")
        with np.load(packet, allow_pickle=False) as actual, np.load(old_packet, allow_pickle=False) as expected:
            if set(actual.files) != set(expected.files):
                raise ValueError("fresh_readback_field_mismatch")
            for key in actual.files:
                if actual[key].dtype != expected[key].dtype or actual[key].shape != expected[key].shape or actual[key].tobytes() != expected[key].tobytes():
                    raise ValueError("fresh_readback_changed_" + role + "_" + key)
    sessions = (("v1", "native"), ("v1", "facts"), ("v2", "facts"), ("v2", "native"), ("control", "restore"))
    for stage, route in sessions:
        directory = HERE / "private/sessions" / (stage + "_repair_" + route)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "payloads").mkdir()
        before = directory / "before.blend"
        shutil.copyfile(current_blend, before)
        write(directory / "session.json", dict(case_id="repair", route=route, stage=stage,
            version=0, source_spec=str(case / "spec.json"), initial_npz=str(initial), current_npz=str(initial),
            current_scene=str(scene), current_blend=str(before), current_blend_identity=identity(before),
            operations=[], pending=None, next_readback_attempt=1))
    with np.load(initial, allow_pickle=False) as current:
        F, I = current["F_source_ids"], current["I_ids"]
    write("CASE_BINDING.json", dict(contract_commit="b6a03e79807b494352eca71fd44dec9204780ecd",
        baseline_commit=commit, source_cycle="M6-DEGRID-004", original=identity(original),
        source_files=old_binding["source_files"], fixed_F_sha256=hashlib.sha256(F.tobytes()).hexdigest(),
        normal_blend=identity(normal_blend), normal_readback=identity(hidden / "normal_readback.npz"),
        current_blend=identity(current_blend), actual_initial_readback=identity(case / "actual_initial_readback.npz"),
        public_initial=identity(initial), private_score_target=identity(target),
        current_from_actual_saved_blend=True, F_points=len(F), editable_points=len(I), private_support_points=47,
        budget_m=spec["max_operation_displacement_m"], source_004_case_binding=identity(previous / "CASE_BINDING.json"),
        reused_files=reused, fresh_readbacks_array_exact=True, actual_Blender_calls=2, actual_Pro_calls=0,
        Blender_jobs=[dict(label=row["label"], wall_s=row["wall_s"]) for row in jobs],
        wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu))
    print("fixed 004 saved states copied and independently reread; four untouched sessions prepared", flush=True)


if __name__ == "__main__":
    main()
