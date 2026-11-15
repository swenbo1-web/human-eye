"""One fixed two-description, five-neighbor diagnostic on the frozen cases."""

import os
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import ctypes
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import cases, load_case, sample_indices
from descriptors import Neighborhoods, describe
from metrics import binary_metrics, patch_macro, quantiles

METHODS = ("R0", "R1", "frozen_p")
DESCRIPTIONS = ("R0", "R1")
K = 5
BLOCK = 128


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8", newline="\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resources():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_observe_monitor", HERE.parent / "m6_shape_train_001/process_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    return module.process_metrics(ctypes.windll.kernel32.GetCurrentProcess())


def nearest_five(query, pool):
    """Float64 direct differences with exact distance/case/source tie ordering."""
    if len(pool["rows"]) < K:
        raise ValueError("reference_pool_contains_fewer_than_five_valid_rows")
    distances = np.zeros((len(query), len(pool["rows"])), dtype=np.float64)
    for column in range(query.shape[1]):
        difference = query[:, column, None] - pool["values"][None, :, column]
        np.square(difference, out=difference)
        distances += difference
    np.sqrt(distances, out=distances)
    indices = np.empty((len(query), K), dtype=np.int64)
    selected_distances = np.empty((len(query), K), dtype=np.float64)
    for ordinal, row in enumerate(distances):
        boundary = np.partition(row, K - 1)[K - 1]
        candidates = np.flatnonzero(row <= boundary)
        ordered = np.lexsort((pool["source_ids"][candidates], pool["case_indices"][candidates], row[candidates]))
        local = candidates[ordered[:K]]
        indices[ordinal] = pool["rows"][local]
        selected_distances[ordinal] = row[local]
    return indices, selected_distances


def point_metrics(labels, magnitudes, scores, valid_masks):
    common = np.logical_and.reduce([valid_masks[name] for name in METHODS])
    strong = (labels & (magnitudes > .1)) | ~labels
    output = {}
    for domain in ("method_valid", "common_valid"):
        output[domain] = {}
        for strength, selection in (("all_support", np.ones(len(labels), dtype=bool)),
                                    ("strong_support", strong)):
            output[domain][strength] = {}
            for method in METHODS:
                use = selection & (common if domain == "common_valid" else valid_masks[method])
                positive = labels[use]
                value = binary_metrics(positive, scores[method][use])
                value["excluded_invalid"] = int(np.count_nonzero(selection & ~use))
                value["excluded_weak_support"] = int(np.count_nonzero(~selection))
                output[domain][strength][method] = value
    return output, common


def selection_groups(case_rows):
    groups = {
        "development": [row["id"] for row in case_rows if row["purpose"] == "development_train_pool"],
        "validation_center": [row["id"] for row in case_rows if row["purpose"] == "validation" and row["position_group"] == "center"],
        "validation_offcenter": [row["id"] for row in case_rows if row["purpose"] == "validation" and row["position_group"] == "offcenter"],
    }
    for source in sorted({row["source"] for row in case_rows}):
        groups["source_" + source] = [row["id"] for row in case_rows if row["source"] == source]
    for primary in ("development", "validation_center", "validation_offcenter"):
        parent_ids = set(groups[primary])
        parent = [row for row in case_rows if row["id"] in parent_ids]
        for radius, amplitude in sorted({(row["radius_ratio"], row["amplitude_ratio"])
                                         for row in parent if not row["normal_control"]}):
            name = f"{primary}_r{radius}_a{amplitude}"
            groups[name] = [row["id"] for row in parent if row["radius_ratio"] == radius
                            and row["amplitude_ratio"] == amplitude]
        for amplitude in sorted({row["amplitude_ratio"] for row in parent if not row["normal_control"]}):
            groups[f"{primary}_amplitude_{amplitude}"] = [row["id"] for row in parent
                                                         if row["amplitude_ratio"] == amplitude]
    return groups


def summarize(case_rows, arrays, scores, valid_masks):
    groups = selection_groups(case_rows)
    summaries = {}
    for name, selected_ids in groups.items():
        selected_ids = set(selected_ids)
        rows = [row for row in case_rows if row["id"] in selected_ids]
        selected_case_indices = [row["case_index"] for row in rows]
        chosen = np.isin(arrays["case_index"], selected_case_indices)
        controls = chosen & np.isin(arrays["case_index"], [row["case_index"] for row in rows if row["normal_control"]])
        damaged = chosen & ~controls
        summary = {"cases": len(rows), "dented_cases": sum(not row["normal_control"] for row in rows),
                   "normal_controls": sum(row["normal_control"] for row in rows),
                   "sampled_points": int(chosen.sum()), "dented_sampled_points": int(damaged.sum()),
                   "invalid_queries": {method: int(np.count_nonzero(chosen & ~valid_masks[method])) for method in METHODS},
                   "invalid_query_fraction": {method: float(np.count_nonzero(chosen & ~valid_masks[method]) / chosen.sum())
                                              if chosen.sum() else None for method in METHODS},
                   "macro": {}, "pooled_dented": {}, "normal_control_score_tails": {}}
        pooled_metrics, common = point_metrics(arrays["label"][damaged], arrays["target_norm"][damaged],
                                               {method: scores[method][damaged] for method in METHODS},
                                               {method: valid_masks[method][damaged] for method in METHODS})
        summary["pooled_dented"] = pooled_metrics
        summary["common_valid_dented_points"] = int(common.sum())
        for domain in ("method_valid", "common_valid"):
            summary["macro"][domain] = {}
            for strength in ("all_support", "strong_support"):
                summary["macro"][domain][strength] = {
                    method: patch_macro(rows, method, domain, strength) for method in METHODS
                }
        for method in METHODS:
            summary["normal_control_score_tails"][method] = quantiles(scores[method][controls & valid_masks[method]])
        summaries[name] = summary
    return summaries


def witness_results(witnesses, witness_rows, pools, arrays, case_list):
    output = []
    for witness, entry in zip(witnesses, witness_rows):
        case = case_list[entry["case_index"]]
        pool_key = "all_development" if case["purpose"] == "validation" else "exclude_" + case["source"]
        record = {"evidence_id": witness["evidence_id"], "case_id": case["id"],
                  "local_index": int(witness["local_index"]), "source_vertex_id": int(witness["source_vertex_id"]),
                  "label": bool(witness["support_label"]), "methods": {}}
        for method in DESCRIPTIONS:
            reasons = entry["description"][method + "_invalid_reasons"][0]
            value = {"valid": bool(entry["description"][method + "_valid"][0]),
                     "invalid_reasons": reasons, "score": None, "neighbors": [], "nearest_opposite": None}
            if value["valid"]:
                pool = pools[method][pool_key]
                query = (entry["description"][method] - pool["mean"]) / pool["std"]
                neighbors, distances = nearest_five(query, pool)
                for row, distance in zip(neighbors[0], distances[0]):
                    neighbor_case = case_list[arrays["case_index"][row]]
                    neighbor = {"case_id": neighbor_case["id"], "source": neighbor_case["source"],
                                "source_vertex_id": int(arrays["source_vertex_id"][row]),
                                "local_index": int(arrays["local_index"][row]), "label": bool(arrays["label"][row]),
                                "distance": float(distance), "sampled_row": int(row)}
                    value["neighbors"].append(neighbor)
                value["score"] = float(np.mean([neighbor["label"] for neighbor in value["neighbors"]]))
                value["nearest_opposite"] = next((neighbor for neighbor in value["neighbors"]
                                                  if neighbor["label"] != record["label"]), None)
            record["methods"][method] = value
        output.append(record)
    return {"cycle_id": "M6-SHAPE-OBSERVE-001", "status": "completed", "evidence": output,
            "witness_points": len(output), "sampling_metrics_include_witnesses": False,
            "opposite_search_scope": "first opposite label among the same five ordered neighbors only"}


def main():
    full_started, full_cpu = time.perf_counter(), time.process_time()
    plan_path = HERE / "PLAN.json"
    plan = json.loads(plan_path.read_bytes())
    if plan["retrieval"]["k"] != K or plan["retrieval"]["query_block_limit"] != BLOCK:
        raise ValueError("fixed_plan_retrieval_constants_mismatch")
    marker = HERE / "RETRIEVAL_STARTED.json"
    with marker.open("x", encoding="utf-8") as saved:
        json.dump({"status": "started", "plan_SHA256": digest(plan_path), "k": K,
                   "descriptions": list(DESCRIPTIONS), "training_runs": 0, "threshold_searches": 0}, saved, indent=2)
        saved.write("\n")
    stage = {name: {"wall_s": 0.0, "cpu_s": 0.0} for name in
             ("load", "description_preparation", "reference_pool_preparation", "query", "witness_query", "metrics", "save")}
    report = {"cycle_id": "M6-SHAPE-OBSERVE-001", "status": "running", "plan_SHA256": digest(plan_path),
              "training_runs": 0, "new_model_forwards": 0, "threshold_searches": 0, "Bunny_arrays": 0,
              "stages": stage, "failures": []}
    try:
        case_list = cases()
        witnesses = json.loads((HERE / "EVIDENCE_PLAN.json").read_bytes())["evidence"]
        witness_by_case = {}
        for witness in witnesses:
            witness_by_case.setdefault(witness["case_id"], []).append(witness)
        descriptions = {method: [] for method in DESCRIPTIONS}
        validity = {method: [] for method in DESCRIPTIONS}
        fields = {name: [] for name in ("case_index", "local_index", "source_vertex_id", "label", "target_norm", "frozen_p", "ball_sizes")}
        topology_cache, case_rows, witness_rows = {}, [], []
        row_offset = 0
        invalid_details = []
        for case_index, case in enumerate(case_list):
            before, cpu = time.perf_counter(), time.process_time()
            sample = load_case(case)
            selected = sample_indices(sample)
            stage["load"]["wall_s"] += time.perf_counter() - before
            stage["load"]["cpu_s"] += time.process_time() - cpu
            before, cpu = time.perf_counter(), time.process_time()
            patch_id = case["patch_id"]
            if patch_id not in topology_cache:
                topology_cache[patch_id] = Neighborhoods(sample["graph"]["edge_index"], len(sample["observed"]))
            neighborhood = topology_cache[patch_id]
            description = describe(sample, selected, neighborhood)
            stage["description_preparation"]["wall_s"] += time.perf_counter() - before
            stage["description_preparation"]["cpu_s"] += time.process_time() - cpu
            support = sample["labels"]["damaged_mask"]
            magnitudes = np.linalg.norm(sample["target_float64"], axis=1)
            fields["case_index"].append(np.full(len(selected), case_index, dtype=np.int64))
            fields["local_index"].append(selected)
            fields["source_vertex_id"].append(sample["source_ids"][selected])
            fields["label"].append(support[selected])
            fields["target_norm"].append(magnitudes[selected])
            fields["frozen_p"].append(np.asarray(sample["p"][selected], dtype=np.float64))
            fields["ball_sizes"].append(description["ball_sizes"])
            for method in DESCRIPTIONS:
                descriptions[method].append(description[method])
                validity[method].append(description[method + "_valid"])
                for ordinal in np.flatnonzero(~description[method + "_valid"]):
                    invalid_details.append({"id": case["id"], "source_vertex_id": int(sample["source_ids"][selected[ordinal]]),
                                            "method": method, "reasons": description[method + "_invalid_reasons"][ordinal]})
            total_energy = float(np.sum(magnitudes[sample["graph"]["free_mask"]] ** 2))
            sampled_energy = float(np.sum(magnitudes[selected] ** 2))
            case_rows.append({"id": case["id"], "case_index": case_index, "patch_id": patch_id,
                              "source": case["source"], "source_group": case["source_group"], "purpose": case["purpose"],
                              "normal_control": case["normal_control"], "position_group": case.get("position_group", "center"),
                              "radius_ratio": case["radius_ratio"], "amplitude_ratio": case["amplitude_ratio"],
                              "sample_start": row_offset, "sample_end": row_offset + len(selected),
                              "free_points": int(sample["graph"]["free_mask"].sum()), "sampled_points": len(selected),
                              "sampled_support": int(support[selected].sum()), "sampled_normal": int((~support[selected]).sum()),
                              "sampled_strong_support": int(np.count_nonzero(support[selected] & (magnitudes[selected] > .1))),
                              "sampled_target_energy": sampled_energy, "full_free_target_energy": total_energy,
                              "target_energy_coverage": sampled_energy / total_energy if total_energy else None,
                              "neighborhood_sizes": {str(radius): quantiles(description["ball_sizes"][:, ordinal])
                                                     for ordinal, radius in enumerate((2, 4, 8))},
                              "invalid_queries": {method: int((~description[method + "_valid"]).sum()) for method in DESCRIPTIONS}})
            row_offset += len(selected)
            for witness in witness_by_case.get(case["id"], []):
                before, cpu = time.perf_counter(), time.process_time()
                one = describe(sample, [witness["local_index"]], neighborhood)
                stage["description_preparation"]["wall_s"] += time.perf_counter() - before
                stage["description_preparation"]["cpu_s"] += time.process_time() - cpu
                witness_rows.append({"evidence_id": witness["evidence_id"], "case_index": case_index, "description": one})
            if (case_index + 1) % 50 == 0:
                print(json.dumps({"description_cases": case_index + 1}), flush=True)
        witness_lookup = {row["evidence_id"]: row for row in witness_rows}
        witness_rows = [witness_lookup[row["evidence_id"]] for row in witnesses]
        arrays = {name: np.concatenate(values) for name, values in fields.items()}
        descriptions = {method: np.concatenate(values) for method, values in descriptions.items()}
        validity = {method: np.concatenate(values) for method, values in validity.items()}
        case_sources = np.asarray([case["source"] for case in case_list])
        development_cases = np.asarray([case["purpose"] == "development_train_pool" for case in case_list])
        development = development_cases[arrays["case_index"]]
        members = sorted({case["source"] for case in case_list if case["purpose"] == "development_train_pool"})
        pools, pool_reports = {}, {}
        before, cpu = time.perf_counter(), time.process_time()
        for method in DESCRIPTIONS:
            pools[method], pool_reports[method] = {}, {}
            for name, excluded in [("all_development", None)] + [("exclude_" + member, member) for member in members]:
                allowed = development.copy()
                if excluded is not None:
                    allowed &= case_sources[arrays["case_index"]] != excluded
                indices = np.flatnonzero(allowed & validity[method])
                values = descriptions[method][indices]
                mean = values.mean(axis=0, dtype=np.float64)
                raw_std = values.std(axis=0, dtype=np.float64)
                std = np.maximum(raw_std, 1e-6)
                pools[method][name] = {"rows": indices, "mean": mean, "std": std, "values": (values - mean) / std,
                                       "case_indices": arrays["case_index"][indices], "source_ids": arrays["source_vertex_id"][indices]}
                pool_reports[method][name] = {"allowed_reference_points": int(allowed.sum()), "valid_reference_points": len(indices),
                                             "invalid_reference_points": int(np.count_nonzero(allowed & ~validity[method])),
                                             "excluded_member": excluded, "mean": mean.tolist(), "population_std": raw_std.tolist(),
                                             "std_used": std.tolist(), "std_floor": 1e-6,
                                             "reference_case_ids": sorted({case_list[index]["id"] for index in arrays["case_index"][indices]})}
        stage["reference_pool_preparation"]["wall_s"] += time.perf_counter() - before
        stage["reference_pool_preparation"]["cpu_s"] += time.process_time() - cpu
        scores = {"frozen_p": arrays["frozen_p"]}
        neighbors, distances = {}, {}
        before, cpu = time.perf_counter(), time.process_time()
        for method in DESCRIPTIONS:
            scores[method] = np.full(row_offset, np.nan, dtype=np.float64)
            neighbors[method] = np.full((row_offset, K), -1, dtype=np.int64)
            distances[method] = np.full((row_offset, K), np.nan, dtype=np.float64)
            for row in case_rows:
                selected = np.arange(row["sample_start"], row["sample_end"], dtype=np.int64)
                selected = selected[validity[method][selected]]
                key = "all_development" if row["purpose"] == "validation" else "exclude_" + row["source"]
                pool = pools[method][key]
                for offset in range(0, len(selected), BLOCK):
                    query_rows = selected[offset:offset + BLOCK]
                    query = (descriptions[method][query_rows] - pool["mean"]) / pool["std"]
                    chosen, distance = nearest_five(query, pool)
                    neighbors[method][query_rows] = chosen
                    distances[method][query_rows] = distance
                    scores[method][query_rows] = arrays["label"][chosen].mean(axis=1)
            print(json.dumps({"queried_method": method, "queries": int(np.isfinite(scores[method]).sum())}), flush=True)
        stage["query"]["wall_s"] += time.perf_counter() - before
        stage["query"]["cpu_s"] += time.process_time() - cpu
        before, cpu = time.perf_counter(), time.process_time()
        witness_report = witness_results(witnesses, witness_rows, pools, arrays, case_list)
        stage["witness_query"]["wall_s"] += time.perf_counter() - before
        stage["witness_query"]["cpu_s"] += time.process_time() - cpu
        before, cpu = time.perf_counter(), time.process_time()
        valid_masks = {method: np.isfinite(scores[method]) for method in METHODS}
        for row in case_rows:
            use = slice(row["sample_start"], row["sample_end"])
            row["metrics"], common = point_metrics(arrays["label"][use], arrays["target_norm"][use],
                                                    {method: scores[method][use] for method in METHODS},
                                                    {method: valid_masks[method][use] for method in METHODS})
            row["common_valid_queries"] = int(common.sum())
            row["score_tails"] = {method: quantiles(scores[method][use][valid_masks[method][use]]) for method in METHODS}
        summaries = summarize(case_rows, arrays, scores, valid_masks)
        stage["metrics"]["wall_s"] += time.perf_counter() - before
        stage["metrics"]["cpu_s"] += time.process_time() - cpu
        before, cpu = time.perf_counter(), time.process_time()
        point_path = HERE / "RETRIEVAL_POINTS.npz"
        saved_arrays = dict(arrays)
        saved_arrays["case_ids"] = np.asarray([case["id"] for case in case_list])
        for method in DESCRIPTIONS:
            saved_arrays[method + "_description"] = descriptions[method]
            saved_arrays[method + "_valid"] = validity[method]
            saved_arrays[method + "_score"] = scores[method]
            saved_arrays[method + "_neighbor_rows"] = neighbors[method]
            saved_arrays[method + "_neighbor_distances"] = distances[method]
            labels = np.zeros_like(neighbors[method], dtype=bool)
            real = neighbors[method] >= 0
            labels[real] = arrays["label"][neighbors[method][real]]
            saved_arrays[method + "_neighbor_labels"] = labels
        np.savez_compressed(point_path, **saved_arrays)
        write(HERE / "WITNESS_RETRIEVAL.json", witness_report)
        stage["save"]["wall_s"] += time.perf_counter() - before
        stage["save"]["cpu_s"] += time.process_time() - cpu
        report.update(status="completed", observations=len(case_list), sampled_points=row_offset,
                      reference_development_points=int(development.sum()), k=K, query_block_limit=BLOCK,
                      case_ids=[case["id"] for case in case_list], cases=case_rows, summaries=summaries,
                      reference_pools=pool_reports, invalid_descriptions=invalid_details,
                      description_dimensions={"R0": 13, "R1": 19},
                      point_results={"path": str(point_path), "bytes": point_path.stat().st_size, "sha256": digest(point_path),
                                     "neighbor_row_semantics": "global sampled-row indices in this same NPZ; case_ids[case_index[row]] and source_vertex_id[row] identify each neighbor",
                                     "contains_geometry": False},
                      witness_results={"path": str(HERE / "WITNESS_RETRIEVAL.json"), "sha256": digest(HERE / "WITNESS_RETRIEVAL.json")},
                      metric_semantics={"macro": "within damaged case, equal damaged cases within patch, equal patches",
                                        "AP": "exact score ties grouped, precision at end of group times recall increment",
                                        "strong_support": "S with target norm>.10 versus clean free points; weaker S excluded",
                                        "normal_control_metrics": "undefined AUC/AP, score tails retained",
                                        "primary_comparison": "common_valid, same label-independent queries for all three scores"},
                      input_semantics="R0/R1 use raw saved observation features and same saved context q/n promoted float64; labels only in reference annotations and evaluation",
                      source_limitations="four development members share unknown upstream group; Armadillo one validation object; repeated synthetic observations share vertices")
        write(marker, {"status": "completed", "descriptions": list(DESCRIPTIONS), "k": K,
                       "observations": len(case_list), "sampled_points": row_offset, "training_runs": 0})
    except Exception as error:
        report["status"] = "failed"
        report["failures"].append({"type": type(error).__name__, "message": str(error)})
        raise
    finally:
        report["wall_s_after_imports_before_report"] = time.perf_counter() - full_started
        report["cpu_s_after_imports_before_report"] = time.process_time() - full_cpu
        report["process_metrics_before_report"] = resources()
        report["code_SHA256"] = {name: digest(HERE / name) for name in ("descriptors.py", "metrics.py", "retrieval.py", "common.py")}
        write(HERE / "RETRIEVAL_RESULTS.json", report)
    print(json.dumps({"status": report["status"], "sampled_points": report["sampled_points"],
                      "wall_s": report["wall_s_after_imports_before_report"],
                      "primary_macro": {name: {method: report["summaries"][name]["macro"]["common_valid"]["all_support"][method]["ROC_AUC"]
                                               for method in METHODS}
                                        for name in ("development", "validation_center", "validation_offcenter")}}), flush=True)


if __name__ == "__main__":
    main()
