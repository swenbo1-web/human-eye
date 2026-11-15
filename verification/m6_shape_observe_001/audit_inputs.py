"""Audit the fixed observations, labels and six numeric forward inputs."""

import time

BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

from collections import deque
import ctypes
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "m6_shape_data_001"
TRAIN = HERE.parent / "m6_shape_train_001"
OPT = HERE.parent / "m6_shape_opt_001"
sys.path.insert(0, str(DATA))
sys.path.insert(0, str(TRAIN))
from data_io import cases_at, forward_arrays, load_sample
from features import prepare_topology
from geometry import normals

FORWARD_NAMES = ("node_features", "edge_features", "positions", "normals", "edge_index", "free_mask")
BINS = ((0.0, .02), (.02, .10), (.10, np.inf))
TAU = .7364127039909363


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def stamp():
    return time.perf_counter(), time.process_time()


def charge(stages, name, before):
    stages[name]["wall_s"] += time.perf_counter() - before[0]
    stages[name]["cpu_s"] += time.process_time() - before[1]


def array_identity(value):
    value = np.ascontiguousarray(value)
    return {"shape": list(value.shape), "dtype": str(value.dtype), "bytes": value.nbytes,
            "sha256": hashlib.sha256(value.tobytes()).hexdigest()}


def distribution(value):
    value = np.asarray(value, dtype=np.float64)
    if not value.size:
        return {"count": 0, "minimum": None, "median": None, "p95": None, "maximum": None}
    return {"count": int(value.size), "minimum": float(value.min()),
            "median": float(np.median(value)), "p95": float(np.quantile(value, .95)),
            "maximum": float(value.max())}


def difference(first, second, selected):
    """Summarize vector changes over a declared node or edge-origin domain."""
    delta = first.astype(np.float64) - second.astype(np.float64)
    if delta.ndim == 1:
        delta = delta[:, None]
    delta = delta[selected]
    lengths = np.linalg.norm(delta, axis=1)
    count = len(lengths)
    return {"rows": count, "changed_rows": int(np.count_nonzero(np.any(delta != 0, axis=1))),
            "changed_components": int(np.count_nonzero(delta)),
            "sum_squared_difference": float(np.square(delta).sum()),
            "mean_row_L2": float(lengths.mean()) if count else None,
            "rmse_row_L2": float(np.sqrt(np.square(lengths).mean())) if count else None,
            "p95_row_L2": float(np.quantile(lengths, .95)) if count else None,
            "maximum_row_L2": float(lengths.max()) if count else None,
            "component_abs_max": np.abs(delta).max(axis=0).tolist() if count else None}


def hops(edge_index, count, seed_mask):
    adjacency = [[] for _ in range(count)]
    for first, second in edge_index.T:
        adjacency[int(first)].append(int(second))
    distances = np.full(count, -1, dtype=np.int64)
    queue = deque(int(value) for value in np.flatnonzero(seed_mask))
    for value in queue:
        distances[value] = 0
    while queue:
        first = queue.popleft()
        for second in adjacency[first]:
            if distances[second] < 0:
                distances[second] = distances[first] + 1
                queue.append(second)
    return distances


def raw_observation(vertices, triangles, topology):
    """Recompute the frozen features.py equations before their float32 casts.

    Full-source normals and neighborhood reductions precede context gathering.
    This independently retains the float64 values discarded by serialization.
    """
    context = topology["context_ids"]
    points = vertices[context]
    origin = points[~topology["free_mask"]].mean(axis=0)
    edges = topology["world_edges"]
    scale = float(np.median(np.linalg.norm(vertices[edges[:, 0]] - vertices[edges[:, 1]], axis=1)))
    unit_normals, _, _, _ = normals(vertices, triangles)
    full_edges = topology["full_edges"]
    delta = (vertices[full_edges[:, 1]] - vertices[full_edges[:, 0]]) / scale
    lengths = np.linalg.norm(delta, axis=1)
    variation = 1 - np.clip(np.einsum("ij,ij->i", unit_normals[full_edges[:, 0]],
                                     unit_normals[full_edges[:, 1]]), -1, 1)
    degree = np.zeros(len(vertices))
    laplacian = np.zeros_like(vertices)
    mean_length = np.zeros(len(vertices))
    normal_variation = np.zeros(len(vertices))
    for corner, sign in ((0, 1), (1, -1)):
        ids = full_edges[:, corner]
        np.add.at(degree, ids, 1)
        np.add.at(laplacian, ids, sign * delta)
        np.add.at(mean_length, ids, lengths)
        np.add.at(normal_variation, ids, variation)
    divisor = np.maximum(degree, 1)
    signed_laplacian = np.einsum("ij,ij->i", laplacian / divisor[:, None], unit_normals)
    positions = (points - origin) / scale
    local_normals = unit_normals[context]
    node = np.column_stack((np.linalg.norm(positions, axis=1), signed_laplacian[context],
                            (normal_variation / divisor)[context], (mean_length / divisor)[context],
                            np.log1p(degree[context]), topology["allowed_mask"], ~topology["free_mask"]))
    first, second = topology["edge_index"]
    edge_delta = positions[second] - positions[first]
    edge = np.column_stack((np.einsum("ij,ij->i", edge_delta, edge_delta),
                            np.einsum("ij,ij->i", local_normals[first], local_normals[second]),
                            np.einsum("ij,ij->i", local_normals[first], edge_delta),
                            np.einsum("ij,ij->i", local_normals[second], edge_delta)))
    return {"positions": positions, "normals": local_normals,
            "node_features": node, "edge_features": edge, "origin": origin, "scale": scale}


def support_bins(support, magnitude, scores):
    energy = magnitude * magnitude
    selected = scores.astype(np.float64) > TAU
    total_points = int(support.sum())
    total_energy = float(energy[support].sum())
    rows = []
    for low, high in BINS:
        mask = support & (magnitude > low) & (magnitude <= high)
        count = int(mask.sum())
        hit = mask & selected
        missed = mask & ~selected
        subtotal = float(energy[mask].sum())
        rows.append({"low_exclusive": low, "high_inclusive": high if np.isfinite(high) else None,
                     "points": count, "point_fraction_of_support": count / total_points if total_points else None,
                     "target_squared_sum": subtotal,
                     "energy_fraction_of_support": subtotal / total_energy if total_energy else None,
                     "tau_selected_points": int(hit.sum()), "tau_missed_points": int(missed.sum()),
                     "recall": int(hit.sum()) / count if count else None,
                     "missed_target_squared_sum": float(energy[missed].sum()),
                     "missed_energy_fraction_within_bin": float(energy[missed].sum()) / subtotal if subtotal else None,
                     "missed_energy_fraction_of_all_support": float(energy[missed].sum()) / total_energy if total_energy else None})
    return rows


def group_keys(case):
    purpose = "development" if case["purpose"] == "development_train_pool" else "validation"
    position = case.get("position_group", "center")
    return ["all", purpose + "_" + position, "source_" + case["source"],
            purpose + "_" + position + "_amplitude_" + str(case.get("amplitude_ratio")),
            "source_" + case["source"] + "_amplitude_" + str(case.get("amplitude_ratio"))]


def summarize(rows):
    support_count = sum(row["denominators"]["support"] for row in rows)
    energy = sum(row["target_squared_sum"] for row in rows)
    summary = {"observations": len(rows), "normal_controls": sum(row["normal_control"] for row in rows),
               "denominators": {name: sum(row["denominators"][name] for row in rows)
                                for name in ("context", "allowed", "free", "support", "normal_allowed", "normal_free", "fixed")},
               "target_squared_sum": energy, "bins": []}
    for index, (low, high) in enumerate(BINS):
        bins = [row["bins"][index] for row in rows]
        count = sum(value["points"] for value in bins)
        subtotal = sum(value["target_squared_sum"] for value in bins)
        hits = sum(value["tau_selected_points"] for value in bins)
        missed_energy = sum(value["missed_target_squared_sum"] for value in bins)
        summary["bins"].append({"low_exclusive": low, "high_inclusive": high if np.isfinite(high) else None,
                                "points": count, "point_fraction_of_support": count / support_count if support_count else None,
                                "target_squared_sum": subtotal, "energy_fraction_of_support": subtotal / energy if energy else None,
                                "tau_selected_points": hits, "tau_missed_points": count - hits,
                                "recall": hits / count if count else None,
                                "missed_target_squared_sum": missed_energy,
                                "missed_energy_fraction_within_bin": missed_energy / subtotal if subtotal else None,
                                "missed_energy_fraction_of_all_support": missed_energy / energy if energy else None})
    for name in ("to_label_normal", "to_input_fixed"):
        distances = [row["graph_distances"][name] for row in rows]
        summary[name] = {"support_points": support_count,
                         "unreachable_support_points": sum(value["unreachable_support_points"] for value in distances),
                         "case_maximum_reachable_hops": distribution([value["reachable_hops"]["maximum"]
                                                                     for value in distances if value["reachable_hops"]["count"]]),
                         "support_points_over_K12": sum(value["support_points_over_K12"] for value in distances),
                         "target_squared_sum_over_K12": sum(value["target_squared_sum_over_K12"] for value in distances)}
    summary["paired_difference_pooled_moments"] = {}
    for domain in ("support", "normal_free", "fixed"):
        summary["paired_difference_pooled_moments"][domain] = {}
        for name in rows[0]["paired_differences"][domain]:
            parts = [row["paired_differences"][domain][name] for row in rows]
            count = sum(part["rows"] for part in parts)
            squared = sum(part["sum_squared_difference"] for part in parts)
            summary["paired_difference_pooled_moments"][domain][name] = {
                "rows": count, "changed_rows": sum(part["changed_rows"] for part in parts),
                "changed_components": sum(part["changed_components"] for part in parts),
                "sum_squared_difference": squared,
                "pooled_rmse_row_L2": float(np.sqrt(squared / count)) if count else None,
                "maximum_row_L2": max((part["maximum_row_L2"] for part in parts if part["rows"]), default=None),
                "case_p95_row_L2_distribution": distribution([part["p95_row_L2"] for part in parts if part["rows"]])}
    return summary


def own_resources():
    path = TRAIN / "process_runner.py"
    spec = importlib.util.spec_from_file_location("_audit_old_process_metrics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return module.process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def main():
    if not (HERE / "PLAN.json").exists():
        raise RuntimeError("frozen_PLAN_required_before_input_audit")
    if (HERE / "INPUT_AUDIT.json").exists():
        raise RuntimeError("input_audit_already_completed_inspect_before_retry")
    stages = {name: {"wall_s": 0.0, "cpu_s": 0.0} for name in
              ("metadata_and_stats_read", "source_snapshot_read", "sample_array_read", "topology_preparation",
               "full_source_feature_recompute", "pair_comparison_and_input_hashes", "labels_and_graph_distances",
               "private_point_array_save", "summary_and_conflicts")}
    before = stamp()
    cases = cases_at(DATA / "DATASET_INDEX.json") + cases_at(TRAIN / "PUBLIC_DATASET_INDEX.json", "validation")
    cases = sorted(cases, key=lambda case: case["id"])
    assert len(cases) == 348 and all(case["purpose"] != "reserved_test" for case in cases)
    roots = {case["id"]: DATA / "private/patches" if case["purpose"] == "development_train_pool"
             else TRAIN / "private/public_data/patches" for case in cases}
    initial = read(OPT / "EVAL_FINAL_HARD.json")
    old_results = {row["id"]: row for row in initial["development"]["cases"] + initial["validation"]["cases"]}
    with np.load(OPT / "private/normalization.npz", allow_pickle=False) as saved:
        stats = {key: saved[key].copy() for key in saved.files}
    assert sum(value.size for value in stats.values()) == 18
    assert read(OPT / "LOC_CALIBRATION.json")["tau"] == TAU
    charge(stages, "metadata_and_stats_read", before)
    before = stamp()
    source_paths = {row["name"]: Path(row["snapshot"]["path"]) for row in read(DATA / "SOURCE_AUDIT.json")["sources"]}
    source_paths["Stanford_Armadillo"] = TRAIN / "private/public_data/sources/Stanford_Armadillo/snapshot.npz"
    sources = {}
    for name, path in source_paths.items():
        with np.load(path, allow_pickle=False) as saved:
            sources[name] = {key: saved[key].copy() for key in ("vertices", "triangles")}
    charge(stages, "source_snapshot_read", before)
    references, topologies = {}, {}
    all_rows, input_groups, saved_forward = [], {}, {}
    point_folder = HERE / "private/audit"
    point_folder.mkdir(parents=True, exist_ok=True)
    extraction_checks = []
    for ordinal, case in enumerate(cases):
        before = stamp()
        sample = load_sample(case, roots[case["id"]])
        with np.load(old_results[case["id"]]["component_path"], allow_pickle=False) as saved:
            scores = saved["p"].copy()
        patch = case["patch_id"]
        if patch not in references:
            normal_case = next(row for row in cases if row["patch_id"] == patch and row["normal_control"])
            normal_sample = load_sample(normal_case, roots[normal_case["id"]])
            references[patch] = {"sample": normal_sample, "forward": forward_arrays(normal_sample, stats)}
        pair = references[patch]["sample"]
        pair_forward = references[patch]["forward"]
        values = forward_arrays(sample, stats)
        charge(stages, "sample_array_read", before)
        before = stamp()
        graph = sample["graph"]
        mapping = sample["mapping"]
        context = mapping["context_source_ids"]
        source = sources[case["source"]]
        if patch not in topologies:
            topologies[patch] = prepare_topology(source["triangles"], len(source["vertices"]), mapping["allowed_source_ids"])
        topology = topologies[patch]
        assert np.array_equal(topology["context_ids"], context)
        for name in ("edge_index", "allowed_mask", "boundary_mask", "free_mask"):
            assert np.array_equal(topology[name], graph[name]), (case["id"], name)
        charge(stages, "topology_preparation", before)
        before = stamp()
        full_observed = source["vertices"].copy()
        full_observed[context] = sample["observed"]
        raw = raw_observation(full_observed, source["triangles"], topology)
        feature_exact = {name: bool(np.array_equal(raw[name].astype(np.float32), sample["inputs"][name]))
                         for name in ("positions", "normals", "node_features", "edge_features")}
        extraction_checks.append({"id": case["id"], "arrays_exact": feature_exact,
                                  "origin_exact": bool(np.array_equal(raw["origin"], sample["origin"])),
                                  "scale_exact": raw["scale"] == sample["scale"]})
        charge(stages, "full_source_feature_recompute", before)
        before = stamp()
        support = sample["labels"]["damaged_mask"]
        free = graph["free_mask"]
        domains = {"support": support, "normal_free": free & ~support, "fixed": ~free}
        target64 = (sample["reference"] - sample["observed"]) / sample["scale"]
        magnitude = np.linalg.norm(target64, axis=1)
        energy = magnitude * magnitude
        assert not np.any(support & ~free)
        assert np.array_equal(support, np.any(sample["labels"]["target_world_m"] != 0, axis=1))
        assert np.array_equal(sample["reference"], pair["observed"])
        assert np.array_equal(sample["labels"]["target_world_m"], sample["reference"] - sample["observed"])
        label_float32_error = target64 - sample["labels"]["target_normalized"].astype(np.float64)
        paired = {}
        origin, neighbor = graph["edge_index"]
        for name, mask in domains.items():
            paired[name] = {
                "native_geometry_over_current_scale": difference((sample["observed"] - pair["observed"]) / sample["scale"],
                                                                 np.zeros_like(sample["observed"]), mask),
                "geometry_shared_reference_frame_label_assisted": difference((sample["observed"] - pair["observed"]) / pair["scale"],
                                                                             np.zeros_like(sample["observed"]), mask),
                "positions_float32_own_frames": difference(sample["inputs"]["positions"], pair["inputs"]["positions"], mask),
                "normals_float32": difference(sample["inputs"]["normals"], pair["inputs"]["normals"], mask),
                "node5_raw_float32": difference(sample["inputs"]["node_features"][:, :5], pair["inputs"]["node_features"][:, :5], mask),
                "node5_network_standardized_float32": difference(values[0][:, :5], pair_forward[0][:, :5], mask),
                "edge4_raw_float32_by_receiver": difference(sample["inputs"]["edge_features"], pair["inputs"]["edge_features"], mask[origin]),
                "edge4_network_standardized_float32_by_receiver": difference(values[1], pair_forward[1], mask[origin]),
                "positions_cast_roundoff": difference(sample["inputs"]["positions"], raw["positions"], mask),
                "normals_cast_roundoff": difference(sample["inputs"]["normals"], raw["normals"], mask),
                "node5_cast_roundoff": difference(sample["inputs"]["node_features"][:, :5], raw["node_features"][:, :5], mask),
                "edge4_cast_roundoff_by_receiver": difference(sample["inputs"]["edge_features"], raw["edge_features"], mask[origin]),
            }
        identities = {name: array_identity(value) for name, value in zip(FORWARD_NAMES, values)}
        combined = hashlib.sha256(json.dumps(identities, sort_keys=True).encode()).hexdigest()
        input_groups.setdefault(combined, []).append(case["id"])
        target_identity = array_identity(sample["labels"]["target_normalized"])
        support_identity = array_identity(support)
        saved_forward[case["id"]] = {"arrays": values, "target": sample["labels"]["target_normalized"].copy(),
                                      "support": support.copy()}
        charge(stages, "pair_comparison_and_input_hashes", before)
        before = stamp()
        bins = support_bins(support, magnitude, scores)
        to_normal = hops(graph["edge_index"], len(support), ~support)
        to_fixed = hops(graph["edge_index"], len(support), ~free)
        distances = {}
        for name, values_hops in (("to_label_normal", to_normal), ("to_input_fixed", to_fixed)):
            selected_hops = values_hops[support]
            over_k = support & (values_hops > 12)
            distances[name] = {"unreachable_support_points": int(np.count_nonzero(selected_hops < 0)),
                               "reachable_hops": distribution(selected_hops[selected_hops >= 0]),
                               "support_points_over_K12": int(over_k.sum()),
                               "target_squared_sum_over_K12": float(energy[over_k].sum())}
        row = {"id": case["id"], "patch_id": patch, "source": case["source"],
               "source_group": case["source_group"], "purpose": case["purpose"],
               "position_group": case.get("position_group", "center"), "normal_control": case["normal_control"],
               "amplitude_ratio": case.get("amplitude_ratio"), "radius_ratio": case.get("radius_ratio"),
               "denominators": {"context": len(support), "allowed": int(graph["allowed_mask"].sum()),
                                "free": int(free.sum()), "support": int(support.sum()),
                                "normal_allowed": int((graph["allowed_mask"] & ~support).sum()),
                                "normal_free": int((free & ~support).sum()), "fixed": int((~free).sum())},
               "target_squared_sum": float(energy[support].sum()), "support_magnitude": distribution(magnitude[support]),
               "bins": bins, "target64_vs_saved_normalized_float32_abs_max": float(np.abs(label_float32_error).max()),
               "zero_float32_target_support_points": int(np.count_nonzero(support & ~np.any(sample["labels"]["target_normalized"] != 0, axis=1))),
               "support_positions_changed_float32_from_normal": int(np.count_nonzero(support & np.any(sample["inputs"]["positions"] != pair["inputs"]["positions"], axis=1))),
               "origin_delta_over_current_scale_L2": float(np.linalg.norm(sample["origin"] - pair["origin"]) / sample["scale"]),
               "scale_ratio_to_normal": sample["scale"] / pair["scale"],
               "paired_differences": paired, "graph_distances": distances,
               "forward_inputs": identities, "combined_forward_identity": combined,
               "normalized_target_identity": target_identity, "support_identity": support_identity,
               "source_input_path": str(sample["folder"] / "inputs" / (sample["sample_name"] + ".npz"))}
        charge(stages, "labels_and_graph_distances", before)
        before = stamp()
        output = point_folder / patch / (sample["sample_name"] + ".npz")
        output.parent.mkdir(parents=True, exist_ok=True)
        np.savez(output, source_vertex_ids=context, support=support, normal_free=free & ~support, fixed=~free,
                 target_normalized_float64=target64, magnitude=magnitude, squared_target=energy, frozen_p=scores,
                 to_label_normal_hops=to_normal, to_input_fixed_hops=to_fixed,
                 geometric_displacement_over_current_scale=(sample["observed"] - pair["observed"]) / sample["scale"],
                 positions_float32_delta=sample["inputs"]["positions"] - pair["inputs"]["positions"],
                 positions_cast_roundoff=sample["inputs"]["positions"].astype(np.float64) - raw["positions"])
        row["private_point_diagnostics"] = str(output.resolve())
        row["private_point_diagnostics_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        all_rows.append(row)
        charge(stages, "private_point_array_save", before)
        if (ordinal + 1) % 50 == 0:
            print(json.dumps({"audit_observations_completed": ordinal + 1, "wall_s": time.perf_counter() - BOOT_WALL}), flush=True)
    before = stamp()
    summaries = {}
    group_ids = sorted({key for case in cases for key in group_keys(case)})
    case_lookup = {case["id"]: case for case in cases}
    for group in group_ids:
        selected = [row for row in all_rows if group in group_keys(case_lookup[row["id"]])]
        summaries[group] = summarize(selected)
    duplicate_groups, conflicts = [], []
    for combined, ids in input_groups.items():
        if len(ids) < 2:
            continue
        anchor = saved_forward[ids[0]]
        for name in ids[1:]:
            current = saved_forward[name]
            assert all(first.dtype == second.dtype and first.shape == second.shape and first.tobytes() == second.tobytes()
                       for first, second in zip(anchor["arrays"], current["arrays"]))
            target_equal = np.array_equal(anchor["target"], current["target"])
            support_equal = np.array_equal(anchor["support"], current["support"])
            if not target_equal or not support_equal:
                conflicts.append({"first": ids[0], "second": name, "targets_equal": target_equal,
                                  "supports_equal": support_equal, "combined_forward_identity": combined})
        duplicate_groups.append({"case_ids": ids, "combined_forward_identity": combined})
    extraction_passed = all(all(row["arrays_exact"].values()) and row["origin_exact"] and row["scale_exact"]
                            for row in extraction_checks)
    charge(stages, "summary_and_conflicts", before)
    report = {"cycle_id": "M6-SHAPE-OBSERVE-001", "status": "completed_input_audit",
              "observations": 348, "frozen_tau": TAU, "new_model_forwards": 0, "training_updates": 0,
              "threshold_candidates_tried": 0, "Bunny_arrays_loaded": 0, "source_snapshots_loaded": list(sources),
              "data_path": {"numeric_forward_inputs": list(FORWARD_NAMES),
                            "node7": ["normalized_radius", "signed_laplacian", "normal_variation", "mean_edge", "log_degree", "allowed", "fixed"],
                            "edge4": ["squared_normalized_edge_length", "normal_dot", "origin_normal_dot_delta", "neighbor_normal_dot_delta"],
                            "localization_access": "node scalars and directed-edge scalars through shared hidden states; six-input positions/normals contribute to conditional vector output",
                            "full_source_then_context": True,
                            "network_standardization": "original training-only node first5/edge4 mean/std; 18 scalars unchanged"},
              "units": "all geometric diagnostic errors and target energy use each observation scale; public physical units unconfirmed",
              "pairing": "same-patch sample00 exact source-vertex alignment; shared-reference-frame deltas are label-assisted attribution only",
              "edge_domain_definition": "directed edge classified by receiving origin vertex",
              "full_source_extraction_recomputed_observations": 348,
              "independent_equation_reconstruction_exact": extraction_passed, "extraction_checks": extraction_checks,
              "complete_input_exact_duplicate_groups": duplicate_groups, "complete_input_conflicts": conflicts,
              "conflict_interpretation": "exact numeric identity checked over all six input arrays, shapes and dtypes; exact-conflict absence leaves approximate identifiability unresolved",
              "cases": all_rows, "summaries": summaries,
              "normal_reference_semantics": "shape before this synthetic perturbation; artistic quality and deployment availability unspecified",
              "timings": stages, "measurement_scope": "Python bootstrap after importing time through report serialization start; external interpreter startup and final write excluded",
              "wall_s_before_final_report_write": time.perf_counter() - BOOT_WALL,
              "cpu_s_before_final_report_write": time.process_time() - BOOT_CPU,
              "process_metrics_before_final_report_write": own_resources()}
    write(HERE / "INPUT_AUDIT.json", report)
    print(json.dumps({"status": report["status"], "observations": 348, "extraction_exact": extraction_passed,
                      "complete_input_conflicts": len(conflicts), "wall_s": report["wall_s_before_final_report_write"]}), flush=True)


if __name__ == "__main__":
    main()
