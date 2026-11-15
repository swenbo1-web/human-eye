"""Construct the fixed shared-noise normal target and independently read current damage."""

import hashlib
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from background import run_job
import numpy as np
from scipy.sparse import csr_matrix


def current_normals(vertices, faces):
    triangles = vertices[faces]
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    sums = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(sums, faces[:, corner], cross)
    length = np.linalg.norm(sums, axis=1)
    unit = np.divide(sums, length[:, None], out=np.zeros_like(sums), where=length[:, None] > 0)
    edges = np.unique(np.sort(np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1), axis=0)
    adjacency = csr_matrix((np.ones(2 * len(edges)),
                            (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
                           shape=(len(vertices), len(vertices)))
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    neighbor = np.divide(adjacency @ unit, degree[:, None], out=np.zeros_like(unit), where=degree[:, None] > 0)
    averaged = 0.5 * unit + 0.5 * neighbor
    length = np.linalg.norm(averaged, axis=1)
    return np.divide(averaged, length[:, None], out=np.zeros_like(averaged), where=length[:, None] > 0)


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "CASE_BINDING.json").exists():
        raise RuntimeError("fixed_case_already_prepared")
    previous = HERE.parent / "m6_matched_refine_003"
    original_case = HERE.parent / "m6_refine_001/private/cases/s01"
    old_binding = read(previous / "CASE_BINDING.json")
    planning = read("PLANNING_PREFLIGHT.json")
    for expected in planning["source_files"]:
        if identity(expected["path"])["sha256"] != expected["sha256"]:
            raise ValueError("fixed_source_NPY_identity_changed")
    clean, damaged, fixed_faces = [np.load(row["path"], allow_pickle=False) for row in planning["source_files"]]
    with np.load(previous / "private/cases/matched/initial.npz", allow_pickle=False) as archive:
        previous_damage = dict(archive)
        F = archive["F_source_ids"].copy()
        I = archive["I_ids"].copy()
    with np.load(original_case / "initial.npz", allow_pickle=False) as archive:
        base = {key: archive[key] for key in ("vertices", "vertices_world", "vertices_local", "matrix_world",
            "faces", "source_ids", "poly_offsets", "poly_vertices", "triangle_polygon_ids")}
    if len(F) != 410 or len(I) != 274 or not np.array_equal(base["faces"], fixed_faces):
        raise ValueError("fixed_domain_or_source_topology_changed")
    support = np.flatnonzero(np.linalg.norm(damaged - clean, axis=1) > 0)
    if len(support) != 47 or not np.isin(support, I).all():
        raise ValueError("fixed_damage_support_changed")
    noise = np.zeros_like(clean)
    noise[F] = np.random.default_rng(2026111604).uniform(-1 / 8192, 1 / 8192, size=(len(F), 3))
    noise_hash = hashlib.sha256(noise.tobytes()).hexdigest()
    if noise_hash != "cd8e84d38618d3de642a7023ea02d3244a61d3353a94582747130fd12118e5fb":
        raise ValueError("fixed_noise_array_identity_mismatch")
    normal_requested = clean + noise
    damaged_requested = damaged + noise
    old_vectors = damaged - clean
    vector_error = float(np.max(np.abs((damaged_requested - normal_requested) - old_vectors)))
    if vector_error >= 1e-15:
        raise ValueError("shared_noise_changed_the_fixed_damage_vectors")
    hidden = HERE / "private/construction"
    case = HERE / "private/cases/repair"
    scoring = HERE / "private/scoring"
    for folder in (hidden, case, scoring):
        folder.mkdir(parents=True, exist_ok=False)
    original = Path(old_binding["original"]["path"])
    if identity(original)["sha256"] != old_binding["original"]["sha256"]:
        raise ValueError("original_asset_changed")
    base_blend = hidden / "base.blend"
    shutil.copyfile(original, base_blend)
    np.save(hidden / "noise.npy", noise)
    np.save(hidden / "normal_requested.npy", normal_requested)
    np.save(hidden / "damaged_requested.npy", damaged_requested)
    np.save(hidden / "old_damage_vectors.npy", old_vectors)
    construction_scope = dict(F_source_ids=F, I_ids=F, protected_ids=np.setdiff1d(base["source_ids"], F))
    np.savez_compressed(hidden / "base_normal.npz", **base, **construction_scope)
    previous_damage.update(construction_scope)
    np.savez_compressed(hidden / "old_damaged.npz", **previous_damage)
    shutil.copyfile(original_case / "baseline_scene.json", hidden / "base_scene.json")
    shutil.copyfile(previous / "private/cases/matched/baseline_scene.json", hidden / "old_damaged_scene.json")
    normal_payload = hidden / "normal_payload.npz"
    np.savez_compressed(normal_payload, source_ids=F, positions_world=normal_requested[F])
    object_name = read(previous / "private/cases/matched/spec.json")["object_name"]
    normal_blend = hidden / "normal.blend"
    jobs = []
    jobs.append(run_job("blender_edit.py", dict(current_blend=str(base_blend), output_blend=str(normal_blend),
        object_name=object_name, source_original=str(original), base_npz=str(hidden / "base_normal.npz"),
        allowed_ids_path=str(hidden / "base_normal.npz"), edit_payload=str(normal_payload),
        operation_id="construct_fixed_normal", expected_input_sha256=identity(base_blend)["sha256"]), "construct_fixed_normal"))
    normal_readback = hidden / "normal_readback.npz"
    jobs.append(run_job("blender_read.py", dict(current_blend=str(normal_blend), object_name=object_name,
        source_original=str(original), base_npz=str(hidden / "base_normal.npz"),
        expected_input_sha256=identity(normal_blend)["sha256"], readback_npz=str(normal_readback),
        scene_signature_json=str(hidden / "normal_scene.json"), local_obj=str(hidden / "normal_local.obj")), "read_fixed_normal"))
    with np.load(normal_readback, allow_pickle=False) as archive:
        normal_actual = dict(archive)
    outside_F = np.setdiff1d(base["source_ids"], F)
    if normal_actual["vertices_local"][outside_F].tobytes() != base["vertices_local"][outside_F].tobytes():
        raise ValueError("normal_construction_changed_outside_fixed_F")
    scope = dict(F_source_ids=F, I_ids=I, protected_ids=np.setdiff1d(base["source_ids"], I))
    np.savez_compressed(hidden / "damage_seed.npz", **normal_actual, **scope)
    damage_payload = hidden / "damage_payload.npz"
    np.savez_compressed(damage_payload, source_ids=support, positions_world=damaged_requested[support])
    current_blend = case / "before.blend"
    jobs.append(run_job("blender_edit.py", dict(current_blend=str(normal_blend), output_blend=str(current_blend),
        object_name=object_name, source_original=str(original), base_npz=str(hidden / "damage_seed.npz"),
        allowed_ids_path=str(hidden / "damage_seed.npz"), edit_payload=str(damage_payload),
        operation_id="construct_fixed_current", expected_input_sha256=identity(normal_blend)["sha256"]), "construct_fixed_current"))
    initial_readback = case / "actual_initial_readback.npz"
    scene = case / "baseline_scene.json"
    jobs.append(run_job("blender_read.py", dict(current_blend=str(current_blend), object_name=object_name,
        source_original=str(original), base_npz=str(hidden / "damage_seed.npz"),
        expected_input_sha256=identity(current_blend)["sha256"], readback_npz=str(initial_readback),
        scene_signature_json=str(scene), local_obj=str(case / "before_local.obj")), "read_fixed_current"))
    with np.load(initial_readback, allow_pickle=False) as archive:
        actual = dict(archive)
    unaffected = np.setdiff1d(base["source_ids"], support)
    if actual["vertices_local"][unaffected].tobytes() != normal_actual["vertices_local"][unaffected].tobytes():
        raise ValueError("damage_construction_changed_outside_fixed_support")
    for key in ("source_ids", "poly_offsets", "poly_vertices", "matrix_world"):
        if actual[key].tobytes() != base[key].tobytes() or normal_actual[key].tobytes() != base[key].tobytes():
            raise ValueError("construction_changed_native_topology_or_matrix_" + key)
    local_faces = actual["faces"][np.isin(actual["faces"], F).all(axis=1)]
    local_edges = np.unique(np.sort(np.concatenate((local_faces[:, [0, 1]], local_faces[:, [1, 2]], local_faces[:, [2, 0]])), axis=1), axis=0)
    with np.load(previous / "private/cases/matched/initial.npz", allow_pickle=False) as old:
        guards = {key: old[key] for key in ("B0_ids", "B1_ids")}
    initial = case / "initial.npz"
    np.savez_compressed(initial, **actual, **scope, **guards, local_edges=local_edges,
                        n0=current_normals(actual["vertices_world"], actual["faces"]))
    target = scoring / "target.npz"
    np.savez_compressed(target, clean_vertices_world=normal_actual["vertices_world"], initial_vertices_world=actual["vertices_world"],
        source_ids=actual["source_ids"], F_source_ids=F, I_ids=I, support_ids=support)
    np.savez_compressed(hidden / "control_restore.npz", source_ids=support, positions_world=normal_actual["vertices_world"][support])
    budget = 0.006893660855829761
    spec = dict(case_id="repair", unit="m", object_name=object_name, source_original=str(original),
        base_blend_path=str(current_blend), initial_npz=str(initial), baseline_scene=str(scene),
        max_operation_displacement_m=budget, max_cumulative_displacement_m=budget, max_displacement=budget,
        world_preservation_tol=1e-6, require_scene_preservation=True, geometry_gates={}, quality_gate={},
        normal_definition="Current actual saved-mesh area-weighted vertex normals, one equal one-ring averaging step and normalization")
    write((case / "spec.json").relative_to(HERE), spec)
    for stage, route in (("run", "facts"), ("run", "native"), ("control", "restore")):
        directory = HERE / "private/sessions" / (stage + "_repair_" + route)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "payloads").mkdir()
        before = directory / "before.blend"
        shutil.copyfile(current_blend, before)
        write((directory / "session.json").relative_to(HERE), dict(case_id="repair", route=route, stage=stage,
            version=0, source_spec=str(case / "spec.json"), initial_npz=str(initial), current_npz=str(initial),
            current_scene=str(scene), current_blend=str(before), current_blend_identity=identity(before),
            operations=[], pending=None, next_readback_attempt=1))
    actual_vectors = actual["vertices_world"] - normal_actual["vertices_world"]
    write("CASE_BINDING.json", dict(contract_commit="f974cf88ecdb0ccc3677aa204d7bba02521841ec",
        baseline_commit="c58e464d454c83b90b3c9baa026478c590e578e6", source_files=planning["source_files"],
        original=identity(original), fixed_F_sha256=hashlib.sha256(F.tobytes()).hexdigest(),
        seed=2026111604, half_width_m=1 / 8192, noise_array_sha256=noise_hash, private_noise=identity(hidden / "noise.npy"),
        noise_RMS_m=float(np.sqrt(np.mean(np.sum(noise[F] ** 2, axis=1)))),
        noise_maximum_m=float(np.linalg.norm(noise[F], axis=1).max()),
        ideal_damage_vector_maximum_change_m=vector_error,
        saved_damage_vector_maximum_error_m=float(np.linalg.norm(actual_vectors - old_vectors, axis=1).max()),
        normal_save_maximum_error_m=float(np.linalg.norm(normal_actual["vertices_world"] - normal_requested, axis=1).max()),
        current_save_maximum_error_m=float(np.linalg.norm(actual["vertices_world"] - damaged_requested, axis=1).max()),
        normal_blend=identity(normal_blend), normal_readback=identity(normal_readback), current_blend=identity(current_blend),
        actual_initial_readback=identity(initial_readback), public_initial=identity(initial), private_score_target=identity(target),
        current_from_actual_saved_blend=True, F_points=len(F), editable_points=len(I), private_support_points=len(support), budget_m=budget,
        actual_native_damaged_points=int(np.any(actual["vertices_local"] != normal_actual["vertices_local"], axis=1).sum()),
        normal_derived_triangles_equal_original=bool(np.array_equal(normal_actual["faces"], base["faces"])),
        damaged_derived_triangles_equal_normal=bool(np.array_equal(actual["faces"], normal_actual["faces"])),
        target_coordinate_contract="New normal target is its actual fresh Blender readback; current initial is the actual second saved-file readback.",
        Blender_jobs=[dict(label=row["label"], wall_s=row["wall_s"]) for row in jobs],
        wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu))
    print("fixed normal and current files independently saved/read, damaged-only public initial prepared", flush=True)


if __name__ == "__main__":
    main()
