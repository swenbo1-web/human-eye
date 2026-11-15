"""Construct one fixed damaged case, then derive every public 3D input from Blender."""

from pathlib import Path
import hashlib
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
        raise RuntimeError("case_already_prepared")
    old = HERE.parent / "m6_refine_001/private/cases/s01"
    pairs = HERE.parent / "m6_shape_pairs_001/private"
    planning = read("PLANNING_PREFLIGHT.json")
    for row in planning["source_files"]:
        if identity(pairs / row["name"])["sha256"] != row["sha256"]:
            raise ValueError("fixed_pair_source_identity_changed")
    original_spec = read(old / "spec.json")
    original = Path(original_spec["source_original"])
    source_identity = identity(original)
    if source_identity["sha256"] != "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d":
        raise ValueError("original_blend_changed")
    clean = np.load(pairs / "reference_vertices.npy", allow_pickle=False)
    damaged = np.load(pairs / "sample_05_abnormal.npy", allow_pickle=False)
    faces = np.load(pairs / "triangles.npy", allow_pickle=False)
    with np.load(old / "initial.npz", allow_pickle=False) as packet:
        old_arrays = dict(packet)
    selected, editable = old_arrays["F_source_ids"], old_arrays["I_ids"]
    support = np.flatnonzero(np.linalg.norm(damaged - clean, axis=1) > 0)
    if len(support) != 47 or not np.isin(support, editable).all():
        raise ValueError("fixed_support_or_domain_changed")
    if not np.array_equal(faces, old_arrays["faces"]):
        raise ValueError("pair_and_native_triangle_order_differ")
    edges = old_arrays["local_edges"]
    edge_lengths = np.linalg.norm(old_arrays["vertices_world"][edges[:, 0]] - old_arrays["vertices_world"][edges[:, 1]], axis=1)
    budget = float(np.mean(edge_lengths))
    if not np.isclose(budget, 0.006893660855829761, rtol=0, atol=1e-15):
        raise ValueError("fixed_normal_region_mean_edge_budget_changed")
    hidden = HERE / "private/construction"
    case = HERE / "private/cases/matched"
    scoring = HERE / "private/scoring"
    hidden.mkdir(parents=True, exist_ok=False)
    case.mkdir(parents=True, exist_ok=False)
    scoring.mkdir(parents=True, exist_ok=False)
    normal_blend = hidden / "normal.blend"
    shutil.copyfile(original, normal_blend)
    seed = hidden / "domain_seed.npz"
    np.savez_compressed(seed, **old_arrays)
    payload = hidden / "construction_payload.npz"
    np.savez_compressed(payload, source_ids=support, positions_world=damaged[support])
    current_blend = case / "before.blend"
    writer = run_job("blender_edit.py", {
        "current_blend": str(normal_blend), "output_blend": str(current_blend),
        "object_name": original_spec["object_name"], "source_original": str(original),
        "base_npz": str(seed), "allowed_ids_path": str(seed), "edit_payload": str(payload),
        "operation_id": "construct_fixed_current", "expected_input_sha256": source_identity["sha256"],
    }, "construct_fixed_current")
    raw = case / "actual_initial_readback.npz"
    scene = case / "baseline_scene.json"
    reader = run_job("blender_read.py", {
        "current_blend": str(current_blend), "object_name": original_spec["object_name"],
        "source_original": str(original), "base_npz": str(seed),
        "expected_input_sha256": identity(current_blend)["sha256"],
        "readback_npz": str(raw), "scene_signature_json": str(scene),
        "local_obj": str(case / "before_local.obj"),
    }, "actual_damaged_initial_read")
    with np.load(raw, allow_pickle=False) as packet:
        actual = dict(packet)
    if not np.array_equal(actual["source_ids"], np.arange(len(clean))):
        raise ValueError("source_ID_index_mapping_changed")
    if not np.array_equal(actual["faces"], faces):
        raise ValueError("saved_damaged_triangle_order_changed")
    if actual["vertices_local"][np.setdiff1d(np.arange(len(clean)), support)].tobytes() != old_arrays["vertices_local"][np.setdiff1d(np.arange(len(clean)), support)].tobytes():
        raise ValueError("construction_changed_outside_fixed_support")
    public = dict(actual)
    public.update(F_source_ids=selected, I_ids=editable,
                  protected_ids=np.setdiff1d(actual["source_ids"], editable),
                  B0_ids=old_arrays["B0_ids"], B1_ids=old_arrays["B1_ids"],
                  local_edges=edges, n0=current_normals(actual["vertices_world"], actual["faces"]))
    initial = case / "initial.npz"
    np.savez_compressed(initial, **public)
    np.savez_compressed(scoring / "target.npz", clean_vertices_world=clean,
                        initial_vertices_world=actual["vertices_world"], source_ids=actual["source_ids"],
                        F_source_ids=selected, I_ids=editable, support_ids=support)
    control = hidden / "control_restore.npz"
    np.savez_compressed(control, source_ids=support, positions_world=clean[support])
    spec = {
        "case_id": "matched", "unit": "m", "object_name": original_spec["object_name"],
        "source_original": str(original), "base_blend_path": str(current_blend),
        "initial_npz": str(initial), "baseline_scene": str(scene),
        "max_operation_displacement_m": budget, "max_cumulative_displacement_m": budget,
        "max_displacement": budget, "world_preservation_tol": 1e-6,
        "require_scene_preservation": True, "geometry_gates": {}, "quality_gate": {},
        "normal_definition": "Current actual saved-mesh area-weighted unit vertex normals, followed by one equal one-ring averaging step and normalization",
        "topology_definition": "Native polygon loops and source IDs preserved, actual derived loop triangles reported separately",
    }
    write((case / "spec.json").relative_to(HERE), spec)
    for stage, route in [("v1", "native"), ("v1", "facts"), ("v2", "facts"), ("v2", "native"), ("control", "restore")]:
        directory = HERE / "private/sessions" / (stage + "_matched_" + route)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "payloads").mkdir()
        before = directory / "before.blend"
        shutil.copyfile(current_blend, before)
        write((directory / "session.json").relative_to(HERE), {
            "case_id": "matched", "route": route, "stage": stage, "version": 0,
            "source_spec": str(case / "spec.json"), "initial_npz": str(initial),
            "current_npz": str(initial), "current_scene": str(scene),
            "current_blend": str(before), "current_blend_identity": identity(before),
            "operations": [], "pending": None, "next_readback_attempt": 1,
        })
    write("CASE_BINDING.json", {
        "contract_commit": "99497e8ea6a9f57fd9ac31ad2b98abf80422fba6",
        "baseline_commit": "159181eede633063e8a5becbaa33210ebb4223a0",
        "source_files": [identity(pairs / row["name"]) for row in planning["source_files"]],
        "original": source_identity, "normal_blend": identity(normal_blend),
        "current_blend": identity(current_blend), "actual_initial_readback": identity(raw),
        "public_initial": identity(initial), "private_score_target": identity(scoring / "target.npz"),
        "current_from_actual_saved_blend": True, "F_points": len(selected), "editable_points": len(editable),
        "private_support_points": len(support), "budget_m": budget,
        "budget_definition": "Mean of the 1158 undirected edges in the fixed old normal 410-point region",
        "saved_vs_requested_maximum_world_error_m": float(np.linalg.norm(actual["vertices_world"] - damaged, axis=1).max()),
        "normal_source_maximum_world_error_m": float(np.linalg.norm(old_arrays["vertices_world"] - clean, axis=1).max()),
        "fresh_normal_array_SHA": hashlib.sha256(public["n0"].tobytes()).hexdigest(),
        "Blender_jobs": [{"label": job["label"], "wall_s": job["wall_s"]} for job in [writer, reader]],
        "consumer_truth_access": "Only initial.npz is delivered as 3D, no construction/scoring packet or source path is in task inputs",
        "wall_s": time.perf_counter() - started, "cpu_s": time.process_time() - cpu,
    })
    print("fixed case saved and independently read, F410/I274, 4 consumers plus isolated control prepared", flush=True)


if __name__ == "__main__":
    main()
