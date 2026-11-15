"""Create readable attention candidates and separate threshold predictions."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np
from region_common import (checked_identity, components, file_identity, geometry_facts, measure,
                           model_identity_values, process_resources, read_json, reference_for,
                           resolve_path, source_ids_digest, write_json)


def compact_text(report):
    attention, abnormal = report["attention"], report["threshold_anomaly_prediction"]
    lines = [f"来源 {report['source_id']}，观察 {report['observation_id']}。",
             f"检查范围为指定F的{report['inspection_scope']['points']}个源顶点。",
             f"坐标使用来源原生单位，面积使用其平方，物理单位状态为{report['inspection_scope'].get('physical_unit', 'unknown')}。",
             f"注意力候选为{attention['region_count']}个连通区域，共{attention['selected_points']}点，覆盖F面积{100*attention['selected_area_fraction_of_F']:.2f}%。候选待核查。"]
    for number, region in enumerate(attention["top_regions"], 1):
        geometry = region["geometry"]
        lines.append(f"候选{number}包含{region['points']}点，面积{region['area_native']:.8g}，当前质心{geometry['centroid_native']}，bbox最小{geometry['bbox_native']['min']}、最大{geometry['bbox_native']['max']}，分数均值{region['scores']['mean']:.6g}，模型分数不可用{region['unavailable_model_points']}点。引用 {region['reference']}。")
    if not attention["top_regions"]:
        lines.append("注意力预算内候选为空。")
    lines.append(f"其余候选{attention['remaining_region_count']}个，面积{attention['remaining_area_native']:.8g}，占F面积{100*attention['remaining_area_fraction_of_F']:.2f}%。")
    lines.append(f"异常阈值预测独立采用严格大于{abnormal['threshold']:.8g}，选中{abnormal['selected_points']}点、{abnormal['region_count']}个区域。")
    lines.append("疑似局部凹陷属于模型预测，当前事实由保存的几何计算。")
    if abnormal["selected_points"] == 0:
        lines.append("本观察没有分数超过异常报告阈值。")
    lines.append(f"完整区域及源ID可回读 {report['full_region_catalog']['path']}，每个引用可由resolve_region.py解析。")
    return "\n".join(lines) + "\n"


def main():
    started, cpu = time.perf_counter(), time.process_time()
    if (HERE / "REGION_REPORTS.json").exists():
        raise RuntimeError("region_reports_exist_inspect_before_explicit_recovery")
    timings, identities, references, results = {}, {}, {}, []
    with measure(timings, "selection_whitelist_model_index_read"):
        selections = read_json("SELECTION_INDEX.json")
        whitelist = {row["id"]: row for row in read_json("INPUT_WHITELIST.json")["cases"]}
        if sorted(row["id"] for row in selections["cases"]) != sorted(whitelist) or len(whitelist) != 348:
            raise ValueError("fixed348_region_case_denominator_mismatch")
        model_report = read_json("MODEL_IDENTITY.json")
        model = model_identity_values(model_report)
        threshold = float(selections["B_threshold"])
        if not np.isfinite(threshold):
            raise ValueError("nonfinite_abnormal_threshold")
        for name in ("SELECTION_INDEX.json", "INPUT_WHITELIST.json", "MODEL_IDENTITY.json"):
            record = file_identity(HERE / name)
            identities[record["path"]] = record
    snapshots = {}
    for selection in sorted(selections["cases"], key=lambda row: row["id"]):
        case_started, case_cpu, case_timings = time.perf_counter(), time.process_time(), {}
        case = whitelist[selection["id"]]
        if case["source"] == "Stanford_Bunny":
            raise ValueError("Bunny_region_generation_locked")
        with measure(case_timings, "current_geometry_selection_read_and_identity"):
            selected_model = model_identity_values(selection.get("model_identity", model_report))
            if selected_model != model:
                raise ValueError("selection_model_identity_mismatch")
            selection_record = checked_identity(selection["path"], selection["sha256"])
            identities[selection_record["path"]] = selection_record
            observed_record = checked_identity(case["observed"]["path"], case["observed"]["sha256"])
            identities[observed_record["path"]] = observed_record
            mapping_record = file_identity(case["mapping_path"])
            identities[mapping_record["path"]] = mapping_record
            if case["source"] not in snapshots:
                snapshot = checked_identity(case["snapshot"]["path"], case["snapshot"]["sha256"])
                identities[snapshot["path"]] = snapshot
                snapshots[case["source"]] = snapshot
            observed = np.load(case["observed"]["path"], allow_pickle=False)
            with np.load(case["mapping_path"], allow_pickle=False) as saved:
                context_ids = saved["context_source_ids"].astype(np.int64)
            with np.load(resolve_path(selection["path"]), allow_pickle=False) as saved:
                source_ids = saved["free_source_ids"].astype(np.int64)
                free_context = saved["free_context_ids"].astype(np.int64)
                edge_index = saved["free_edge_index"].astype(np.int64)
                scores = saved["new_score"].astype(np.float64)
                area = saved["area"].astype(np.float64)
                valid = saved["valid_mask"].astype(bool)
                masks = {"attention": saved["attention_mask"].astype(bool),
                         "threshold": saved["abnormal_mask"].astype(bool)}
            if not np.array_equal(context_ids[free_context], source_ids) or len(np.unique(source_ids)) != len(source_ids):
                raise ValueError("source_geometry_mapping_mismatch")
            if not np.array_equal(source_ids, np.sort(source_ids)):
                raise ValueError("source_ID_order_mismatch")
            if any(values.shape != (len(source_ids),) for values in (scores, area, valid, *masks.values())):
                raise ValueError("selection_array_shape_mismatch")
            if not np.isfinite(observed).all() or not np.isfinite(scores).all() or not np.isfinite(area).all() or np.any(area < 0):
                raise ValueError("invalid_current_geometry_or_score_or_area")
            if edge_index.ndim != 2 or edge_index.shape[0] != 2 or (edge_index.size and (edge_index.min() < 0 or edge_index.max() >= len(source_ids))):
                raise ValueError("invalid_F_edges")
            positions = observed[free_context]
            ell = float(selection["ell"])
            if not np.isfinite(ell) or ell <= 0:
                raise ValueError("invalid_observation_scale")
        F_area, F_digest = float(np.sum(area)), source_ids_digest(source_ids)
        catalog, summaries = {}, {}
        patch, sample = selection["id"].split("/")
        folder = HERE / "private/region_reports" / patch / sample
        folder.mkdir(parents=True, exist_ok=True)
        for mode, mask in masks.items():
            with measure(case_timings, mode + "_components_and_priority"):
                groups = components(mask, edge_index)
                groups.sort(key=lambda rows: (-float(np.sum(area[rows] * scores[rows])), int(source_ids[rows].min())))
            regions = []
            for rank, rows in enumerate(groups, 1):
                with measure(case_timings, mode + "_geometry_facts_and_reference"):
                    ids = source_ids[rows]
                    region_area = float(np.sum(area[rows]))
                    binding = {"contract": "m6-perception-region-v1", "source_id": case["source"],
                               "observation_id": case["id"], "observation_sha256": observed_record["sha256"],
                               "snapshot_sha256": snapshots[case["source"]]["sha256"],
                               "mapping_sha256": mapping_record["sha256"], "F_source_ids_sha256": F_digest,
                               "selection_payload_sha256": selection_record["sha256"], "model": model,
                               "selection_mode": mode, "region_source_ids_sha256": source_ids_digest(ids)}
                    reference = reference_for(binding)
                    facts = {"reference": reference, "source_id": case["source"], "observation_id": case["id"],
                             "rank": rank, "points": len(rows), "area_native": region_area,
                             "area_over_ell2": region_area / (ell * ell),
                             "area_fraction_of_F": region_area / F_area if F_area else 0.0,
                             "priority_native_area_times_score": float(np.sum(area[rows] * scores[rows])),
                             "geometry": geometry_facts(positions[rows], area[rows]),
                             "scores": {"min": float(scores[rows].min()), "mean": float(scores[rows].mean()),
                                        "max": float(scores[rows].max()), "p95": float(np.quantile(scores[rows], .95, method="linear")),
                                        "interpretation": "uncalibrated_model_score"},
                             "unavailable_model_points": int(np.count_nonzero(~valid[rows])),
                             "selection_method": "25_percent_F_area_ranked_prefix" if mode == "attention" else "strict_development_normal_q95_threshold",
                             "prediction": {"label": "疑似局部凹陷", "status": "model_prediction_unconfirmed"},
                             "source_id_min": int(ids.min()), "source_id_max": int(ids.max())}
                with measure(case_timings, mode + "_private_payload_save_and_hash"):
                    detail_path = folder / (mode + "_" + str(rank).zfill(4) + ".npz")
                    np.savez_compressed(detail_path, source_ids=ids, current_positions_native=positions[rows],
                                        area=area[rows], scores=scores[rows], valid_mask=valid[rows])
                    detail = file_identity(detail_path)
                    facts["read_more"] = {"resolver": "resolve_region.py", "reference": reference,
                                          "geometry_payload_path": detail["path"]}
                    record = {"identity": binding, "facts": facts, "detail": detail}
                    if reference in references:
                        raise ValueError("duplicate_region_reference")
                    references[reference] = record
                    regions.append(facts)
            selected_area = float(np.sum(area[mask]))
            shown = regions[:3] if mode == "attention" else []
            shown_area = sum(row["area_native"] for row in shown)
            remaining_area = sum(row["area_native"] for row in regions[len(shown):])
            summaries[mode] = {"region_count": len(regions), "selected_points": int(np.count_nonzero(mask)),
                               "selected_area_native": selected_area, "selected_area_over_ell2": selected_area / (ell * ell),
                               "selected_area_fraction_of_F": selected_area / F_area if F_area else 0.0,
                               "unavailable_model_points_selected": int(np.count_nonzero(mask & ~valid)),
                               "top_regions": shown, "reported_region_count": len(shown),
                               "reported_area_native": shown_area,
                               "remaining_region_count": len(regions) - len(shown),
                               "remaining_area_native": remaining_area,
                               "remaining_area_fraction_of_F": remaining_area / F_area if F_area else 0.0}
            catalog[mode] = regions
        with measure(case_timings, "catalog_structured_and_text_report_save"):
            catalog_path = folder / "all_regions.json"
            write_json(catalog_path, {"source_id": case["source"], "observation_id": case["id"],
                                    "model_identity": model, "regions": catalog})
            summaries["threshold"].update(threshold=threshold, comparison="strictly_greater",
                                           prediction_status="threshold_reported_model_prediction_unconfirmed",
                                           overlap_with_attention_points=int(np.count_nonzero(masks["attention"] & masks["threshold"])))
            facts = {"contract": "m6-perception-readable-facts-v1", "source_id": case["source"],
                     "observation_id": case["id"], "observation_version_sha256": observed_record["sha256"],
                     "model_identity": model, "inspection_scope": {"kind": "specified_task_F", "points": len(source_ids),
                         "source_ids_sha256": F_digest, "area_native": F_area, "area_over_ell2": F_area / (ell * ell),
                         "coordinate_space": "source_native", "area_unit": "source_native_squared", "physical_unit": "unknown"},
                     "attention": summaries["attention"], "threshold_anomaly_prediction": summaries["threshold"],
                     "full_region_catalog": file_identity(catalog_path),
                     "geometry_facts_status": "computed_from_current_observed_coordinates",
                     "scope": "offline_region_contract_for_specified_F", "LLM_consumer_evaluation": "not_run"}
            structured_path, text_path = folder / "facts.json", folder / "facts.md"
            write_json(structured_path, facts)
            text_path.write_text(compact_text(facts), encoding="utf8", newline="\n")
            record = {"id": case["id"], "source": case["source"], "patch_id": case["patch_id"],
                      "purpose": case["purpose"], "normal_control": case["normal_control"],
                      "position_group": case.get("position_group", "center"),
                      "structured_report": file_identity(structured_path), "text_report": file_identity(text_path),
                      "catalog": file_identity(catalog_path), "selection": selection_record,
                      "attention_regions": summaries["attention"]["region_count"],
                      "threshold_regions": summaries["threshold"]["region_count"],
                      "attention_points": summaries["attention"]["selected_points"],
                      "threshold_points": summaries["threshold"]["selected_points"]}
        record.update(timings=case_timings, body_wall_s=time.perf_counter() - case_started,
                      body_CPU_s=time.process_time() - case_cpu)
        results.append(record)
        for name, cost in case_timings.items():
            total = timings.setdefault(name, {"wall_s": 0.0, "CPU_s": 0.0, "calls": 0})
            for key in total:
                total[key] += cost[key]
    audit_cases = [min(row["id"] for row in results if row["purpose"] == "development_train_pool" and row["normal_control"])]
    for position in ("center", "offcenter"):
        audit_cases.append(min(row["id"] for row in results if row["purpose"] == "validation"
                               and not row["normal_control"] and row["position_group"] == position))
    with measure(timings, "global_reference_index_save"):
        write_json("REGION_REFERENCES.json", {"contract": "m6-perception-region-reference-index-v1",
                   "model_identity": model, "regions": references, "region_count": len(references)})
    report = {"cycle_id": "M6-PERCEPTION-001", "status": "completed348_readable_region_contracts",
              "cases": results, "case_count": len(results), "model_identity": model, "B_threshold": threshold,
              "reference_index": file_identity(HERE / "REGION_REFERENCES.json"), "reference_count": len(references),
              "audit_case_ids": audit_cases, "audit_selection": "lexicographic first development normal, validation center/offcenter nonnormal",
              "text_region_limit": 3, "complete_ID_lists": "private per-region source ID and current geometry payloads",
              "input_file_identities": list(identities.values()), "timings": timings,
              "source_sha256": {name: file_identity(HERE / name)["sha256"] for name in ("regions.py", "resolve_region.py", "region_common.py")},
              "wall_s_before_final_report": time.perf_counter() - started, "CPU_s_before_final_report": time.process_time() - cpu,
              "bootstrap_to_report_wall_s": time.perf_counter() - BOOT_WALL, "bootstrap_to_report_CPU_s": time.process_time() - BOOT_CPU,
              "own_process_before_report": process_resources(), "embedding_values_in_text": 0,
              "new_model_forwards": 0, "training": 0, "repair_outputs": 0, "Bunny_arrays": 0,
              "LLM_consumer_evaluations": 0, "product_integration": 0,
              "measurement_scope": "reads, components, facts, geometry payload and report saves included; final global report serialization/write/exit outside own window"}
    write_json("REGION_REPORTS.json", report)
    print(json.dumps({"status": report["status"], "cases": len(results), "references": len(references), "audit_cases": audit_cases}))


if __name__ == "__main__":
    main()
