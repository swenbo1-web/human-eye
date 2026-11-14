"""Publish data denominators, measured cost boundaries and one training config."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent


def load(name):
    return json.loads((HERE / name).read_bytes())


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def main():
    selection, dataset, verification = load("PATCH_SELECTION.json"), load("DATASET_INDEX.json"), load("VERIFICATION.json")
    manifest, audit, render = load("SOURCE_MANIFEST.json"), load("SOURCE_AUDIT.json"), load("RENDER_LOG.json")
    cases = dataset["cases"]
    summary = {"cycle_id": "M6-SHAPE-DATA-001", "published_UTC": datetime.now(timezone.utc).isoformat(),
               "source_files": 4, "conservative_source_groups": 1, "verified_independent_lineages": 0,
               "patches": len(selection["patches"]), "observations": len(cases), "normal_controls": sum(case["normal_control"] for case in cases),
               "dents": sum(not case["normal_control"] for case in cases), "accepted": sum(case["accepted"] for case in cases),
               "rejected_after_generation": sum(not case["accepted"] for case in cases),
               "source_denominators": [], "patch_strata": dict(Counter(patch["stratum"] for patch in selection["patches"])),
               "candidate_checks": len(selection["candidate_checks"]),
               "candidate_rejections": dict(Counter(item["reason"] for item in selection["candidate_checks"] if not item["accepted"])),
               "maximum_patch_gap": 48 - len(selection["patches"]), "maximum_observation_gap": 336 - len(cases),
               "allowed_vertex_observations": sum(case["allowed_vertices"] for case in cases),
               "damaged_vertex_observations": sum(case["damaged_vertices"] for case in cases),
               "normal_allowed_vertex_observations": sum(case["normal_allowed_vertices"] for case in cases),
               "normal_free_vertex_observations": sum(case["normal_free_vertices"] for case in cases),
               "support_count_min_max": [min(case["damaged_vertices"] for case in cases if not case["normal_control"]), max(case["damaged_vertices"] for case in cases)],
               "max_damage_displacement_m": max(case["damage_max_m"] for case in cases),
               "overlap_pairs": len(selection["overlaps"]), "maximum_overlap_jaccard": max(item["jaccard"] for item in selection["overlaps"]),
               "input_vertices_min_max": [min(item["input_vertices"] for item in verification["graph_statistics"]), max(item["input_vertices"] for item in verification["graph_statistics"])],
               "directed_edges_min_max": [min(item["directed_edges"] for item in verification["graph_statistics"]), max(item["directed_edges"] for item in verification["graph_statistics"])],
               "H_clean_max": max(item["damaged_to_clean_max_hops"] for item in verification["graph_statistics"]),
               "H_fixed_max": verification["h_fixed_max"], "support_diameter_max": max(item["support_diameter_hops"] for item in verification["graph_statistics"]),
               "input_graph_diameter_max": max(item["input_graph_diameter_hops"] for item in verification["graph_statistics"]),
               "message_steps": verification["frozen_message_steps"], "independent_assertions": verification["assertion_count"],
               "zero_context_normal_occurrences": verification["zero_context_normals_over_observations"],
               "unmeasured_coupling": ["within selected full-source mesh endpoint intersections", "other scene objects and inter-object contacts", "containment/volume", "motion path and spacing"],
               "candidate_training_runs": 0, "repair_baseline_runs": 0, "contact_queries": 0,
               "independence_gap": load("SOURCE_GROUPS.json")["independence_gap"]}
    for source in manifest["sources"]:
        source_cases = [case for case in cases if case["source"] == source["name"]]
        patches = [patch for patch in selection["patches"] if patch["source"] == source["name"]]
        unique_allowed = set()
        for patch in patches:
            with np.load(Path(patch["private_directory"]) / "mapping.npz", allow_pickle=False) as saved:
                unique_allowed.update(saved["allowed_source_ids"].tolist())
        summary["source_denominators"].append({"source": source["name"], "patches": len(patches), "observations": len(source_cases),
                                               "normal_controls": sum(case["normal_control"] for case in source_cases),
                                               "dents": sum(not case["normal_control"] for case in source_cases),
                                               "unique_source_allowed_vertices": len(unique_allowed),
                                               "damaged_vertex_observations": sum(case["damaged_vertices"] for case in source_cases),
                                               "normal_allowed_vertex_observations": sum(case["normal_allowed_vertices"] for case in source_cases),
                                               "normal_free_vertex_observations": sum(case["normal_free_vertices"] for case in source_cases)})
    write("DATA_SUMMARY.json", summary)
    costs = {"cycle_id": "M6-SHAPE-DATA-001", "measurement_completeness": "incomplete",
             "current_batch_new_Blender_processes": manifest["new_Blender_processes"], "Yanyite_export": "reused previous frozen capture; incremental export0, previous acquisition cost retained in old batch",
             "acquisition": {"controller_wall_s": manifest["controller_wall_s"], "controller_cpu_s_excluding_children": manifest["controller_cpu_s"],
                             "children": [{"source": item["source"], "full_process_wall_s": item["full_process_wall_s"], "process_cpu": item["process_cpu"]} for item in manifest["attempts"]]},
             "collector_process_peaks": [],
             "separate_main_intervals": {"source_audit": {"wall_s": audit["wall_s"], "cpu_s": audit["cpu_s"]},
                                         "patch_preparation": {"wall_s": selection["wall_s"], "cpu_s": selection["cpu_s"]},
                                         "paired_generation": {"wall_s": dataset["wall_s_before_publication"], "cpu_s": dataset["cpu_s_before_publication"], "subintervals": dataset["timings"]},
                                         "verification": {"wall_s": verification["wall_s"], "cpu_s": verification["cpu_s"]},
                                         "rendering_two_attempts": {"wall_s": render["wall_s_total"], "cpu_s": render["cpu_s_total"]}},
             "failed_before_main_audit_shell_wall_s": .1719627,
             "private_bytes_at_summary": sum(file.stat().st_size for file in (HERE / "private").rglob("*") if file.is_file()),
             "candidate_training_calls": 0, "candidate_inference_calls": 0, "direct_repair_baseline_calls": 0, "contact_queries": 0,
             "online_cost_measured": False, "whole_pipeline_wall_s": None, "whole_pipeline_cpu_s": None, "whole_pipeline_peak_RSS_bytes": None,
             "missing": ["provenance document review wall/CPU", "complete authoring/metadata/commit/publication intervals", "whole-process CPU including imports/publication for non-Blender stages", "peak RSS outside collector processes", "online cold/warm candidate tasks and all coupling costs"],
             "timing_rule": "source acquisition includes child time; child time and generation subintervals are nested. Other stage main intervals run separately after imports. No complete end-to-end cost or performance claim.",
             "paid_API_calls": 0, "training": 0, "source_file_saves": 0, "shared_GUI_calls": 0, "M5_writes": 0}
    for source in manifest["sources"]:
        native = json.loads(Path(source["native"]["path"]).read_bytes())
        costs["collector_process_peaks"].append({"source": source["name"], "incremental_this_batch": source["name"] != "Yanyite",
                                               "memory_at_end": native["memory_at_end"], "collector_wall_s": native["collector_wall_s"],
                                               "collector_cpu_s": native.get("collector_cpu_s")})
    write("COSTS.json", costs)
    module_parameters = {"node_encoder": 792, "shared_edge_MLP": 1872, "shared_node_update": 2352,
                         "shared_layer_norm": 48, "alpha_head": 1201, "beta_head": 25}
    assert sum(module_parameters.values()) == 6290
    training = {"cycle_id": "M6-SHAPE-DATA-001", "status": "concrete_proposal_for_independent_review_no_training",
                "prerequisites": ["establish at least three independently evidenced source groups for train/validation/reserved test", "freeze PyTorch CPU wheel/version/hash and setup cost", "verify future model parameter tensors total6290"],
                "data_index": str(HERE / "DATASET_INDEX.json"), "accepted_observations_only": True,
                "current_split": load("SOURCE_GROUPS.json")["splits"],
                "input_file_whitelist": ["node_features", "edge_features", "positions", "normals"],
                "shared_graph_whitelist": ["edge_index", "allowed_mask", "boundary_mask", "free_mask"],
                "transform_sidecar": ["origin_world_m", "scale_m"], "metadata_and_labels_are_not_features": True,
                "source_ID_use": "trace/grouping/gather only, never numeric model features or embeddings",
                "dynamic_preparation_scope": "full current observed mesh normals and original-edge statistics, then gather two-ring context",
                "normalization": {"origin": "observed fixed/halo position mean", "scale": "observed context edge median", "continuous_feature_standardization": "train observations only,5 node+4 edge means/std,18 persisted scalars", "std_min": 1e-6},
                "model": {"name": "shared-cell local mesh residual expert", "width": 24, "message_steps": 12, "message_cell_weights_shared": True,
                          "node_features": 7, "edge_features": 4, "activations": "SiLU", "dropout": 0, "normalization": "shared LayerNorm24",
                          "module_dimensions": {"node_encoder": [7, 24, 24], "shared_edge_MLP": [52, 24, 24], "shared_node_update": [72, 24, 24], "alpha_head": [48, 24, 1], "beta_head_single_linear": [24, 1]},
                          "update": "h=LN(h+0.1*MLP72to24to24(concat(h,mean_edge_message,h0)))",
                          "head": "alpha_i*n_i + mean_j(beta_ij*(q_j-q_i))", "head_last_layers_zero_initialized": True,
                          "fixed_boundary_halo_and_external_output": "hard zero, add correction only to original binary64 writable observation copy",
                          "parameters_by_module": module_parameters, "estimated_parameters": 6290, "parameter_count_verified_by_formula_only": True,
                          "SO3_covariance": "analytic design; observation preprocessing verified on4source examples under rotation+scale; actual network implementation not yet tested"},
                "receptive_field": {"normal_observation_max_hops": summary["H_clean_max"], "fixed_halo_max_hops": summary["H_fixed_max"],
                                    "support_diameter_max_hops": summary["support_diameter_max"], "input_diameter_max_hops": summary["input_graph_diameter_max"],
                                    "all_damaged_points_reach_observed_clean_and_fixed_context_in_K": True, "full_graph_information_in_K": False},
                "supervision": {"target": "full context (reference-observed)/observed_scale, all allowed normal points explicitly zero", "loss_units": "dimensionless squared displacement",
                                "damaged_case_loss": "0.2*mean_A +0.4*mean_S +0.4*mean_normal_free, empty terms omitted with remaining weights normalized",
                                "normal_control_loss": "mean_A", "gradient_loss": "0.05*mean_directed_input_edges squared error of predicted-vs-target correction differences", "batch_reduction": "equal mean per graph",
                                "required_denominators": ["A", "S", "normal_allowed", "normal_free", "fixed", "directed_edges"]},
                "training": {"framework": "PyTorch CPU, setup pending", "dtype": "float32", "CPU_threads": 1, "seed": 1729,
                             "batch_graphs": 4, "normal_graphs_per_batch": 1, "dented_graphs_per_batch": 3,
                             "sampling": "source groups equal, patches uniform within training group, six radius/amplitude states in deterministic balanced cycle; overlaps retained in same group and reported",
                             "optimizer": "AdamW", "lr_initial": .001, "lr_final": .0001, "schedule": "cosine over1200steps", "betas": [.9, .999], "eps": 1e-8,
                             "weight_decay": 1e-5, "foreach": False, "fused": False, "gradient_norm_clip": 1., "steps": 1200,
                             "validation_steps": [0, 400, 800, 1200], "reported_checkpoint": 1200,
                             "maximum_wall_s": 1800, "maximum_RSS_bytes": 2 * 1024 ** 3, "budget_exhaustion": "incomplete, no success claim"},
                "one_optimization": "one evidence-based change after first round, same architecture/grouping/seed, if retraining at most1200more steps/1800s/2GiB",
                "baselines": {"no_op": True, "one_direct": "residual-gated robust quadratic MLS, observation-only simultaneous projection",
                              "graph_radius_scale_units": 8, "normal_dot_min": .5, "minimum_points": 12, "require_full_rank": True,
                              "neighborhood_scope": "same frozen two-ring context graph, observed edge-length geodesics",
                              "distance_weight": "exp(-(d_G/(4*scale))^2)", "IRLS_passes": 3, "Tukey_cutoff": 4.685,
                              "residual_scale": "max(1.4826*MAD,1e-4*observation_scale)", "gate": "train normal-control abs residual/scale percentile99.5, calibrated once",
                              "correction": "-sign(r)*max(abs(r)-tau*scale,0)*observed_normal", "numeric_failure": "zero correction and include failure in denominator"},
                "acceptance": {"aggregation": "compute each damaged-case ratio/improvement first, then median/p95/worst; report group and member-file denominators",
                               "support_RMSE_ratio_to_noop": {"overall_median_max": .70, "each_source_group_median_max": .85, "each_member_file_median_max": .85, "p95_max": 1.05, "worst_max": 1.25},
                               "allowed_RMSE_median_improvement_to_noop_min": .20, "support_median_improvement_to_MLS_min": .10,
                               "MLS_nearzero_denominator": "if MLS support RMSE<=1e-6*scale, case improvement=0 if model also<=threshold, else -model_RMSE/(1e-6*scale); report count and absolute errors",
                               "normal_point_gate_aggregation": "each case, for both normal_allowed and normal_free",
                               "normal_point_change_over_scale": {"p95_max": .02, "worst_max": .10},
                               "normal_control_change_over_scale": {"RMSE_max": .01, "p95_max": .02, "worst_max": .05},
                               "normal_denominators": "report both all normal allowed and normal free; inspect per group/member/radius/amplitude and worst cases",
                               "boundary_external_bitwise_preservation": True, "new_degenerate_or_reversed_faces": 0,
                               "coupling": "complete candidate impact-domain endpoint checks after full readback, zero new forbidden contacts and zero unresolved",
                               "extra_full_task_p95_wall_s_max_vs_preselected_MLS": 2., "online_peak_RSS_bytes_max": 2 * 1024 ** 3,
                               "cost_comparison_scope": "identical full prepare/readback/coupling chain, report MLS quality qualification separately",
                               "reserved_test": "open once after validation choice; no tuning from test labels"},
                "cost_contract": ["dependency setup", "offline acquisition/generation/exports", "shared topology prepare", "per-observation dynamic normals/features", "training forward/backward", "validation", "save/load and peak memory", "cold/warm inference", "full readback and coupling", "publication"],
                "speed_benefit_claimed": False, "actual_training_runs": 0, "actual_model_quality_results": None}
    write("TRAINING_CONTRACT.json", training)
    print(json.dumps({"patches": summary["patches"], "observations": summary["observations"], "private_bytes": costs["private_bytes_at_summary"],
                      "parameters": training["model"]["estimated_parameters"], "measurement_completeness": costs["measurement_completeness"]}))


if __name__ == "__main__":
    main()
