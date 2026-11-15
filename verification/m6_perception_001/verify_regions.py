"""Independently check all readable reports and source-ID reference round trips."""

import time
BOOT_WALL, BOOT_CPU = time.perf_counter(), time.process_time()

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np
from region_common import checked_identity, file_identity, measure, process_resources, read_json, resolve_path, write_json
from resolve_region import resolve_region


def independent_components(mask, edges, source_ids):
    chosen = set(int(source_id) for source_id in source_ids[mask])
    adjacency = {int(source_id): set() for source_id in source_ids}
    for pair in edges.T:
        first, second = int(source_ids[pair[0]]), int(source_ids[pair[1]])
        adjacency[first].add(second)
        adjacency[second].add(first)
    groups = []
    while chosen:
        start = min(chosen)
        chosen.remove(start)
        pending, group = [start], []
        while pending:
            source_id = pending.pop()
            group.append(source_id)
            for neighbor in adjacency[source_id]:
                if neighbor in chosen:
                    chosen.remove(neighbor)
                    pending.append(neighbor)
        groups.append(sorted(group))
    return groups


def main():
    started, cpu = time.perf_counter(), time.process_time()
    check_count, failures, timings, used = 0, [], {}, {}
    largest_difference = 0.0

    def check(name, condition):
        nonlocal check_count
        check_count += 1
        if not bool(condition):
            failures.append(name)

    def close(name, actual, expected):
        nonlocal largest_difference
        actual, expected = np.asarray(actual), np.asarray(expected)
        if actual.shape != expected.shape:
            check(name + "_shape", False)
            return
        difference = float(np.max(np.abs(actual - expected))) if actual.size else 0.0
        largest_difference = max(largest_difference, difference)
        check(name, np.allclose(actual, expected, atol=1e-12, rtol=1e-12))

    def old_record(path, sha=None):
        record = checked_identity(path, sha)
        used[record["path"]] = record
        return record

    with measure(timings, "report_selection_and_whitelist_identity"):
        report = read_json("REGION_REPORTS.json")
        reference_record = checked_identity(report["reference_index"]["path"], report["reference_index"]["sha256"])
        references = read_json(reference_record["path"])
        selections = {row["id"]: row for row in read_json("SELECTION_INDEX.json")["cases"]}
        whitelist = {row["id"]: row for row in read_json("INPUT_WHITELIST.json")["cases"]}
        case_rows = {row["id"]: row for row in report["cases"]}
        check("all348_case_IDs", sorted(case_rows) == sorted(selections) == sorted(whitelist) and len(case_rows) == 348)
        check("global_reference_count", report["reference_count"] == len(references["regions"]))
        threshold = float(report["B_threshold"])
    sources, patches = {}, {}
    seen_refs, F_points, selected_counts, empty_counts = set(), 0, {"attention": 0, "threshold": 0}, {"attention": 0, "threshold": 0}
    for case_id in sorted(case_rows):
        row, selection, case = case_rows[case_id], selections[case_id], whitelist[case_id]
        with measure(timings, "saved_report_and_current_geometry_read"):
            for key in ("structured_report", "text_report", "catalog", "selection"):
                checked_identity(row[key]["path"], row[key]["sha256"])
            facts = read_json(row["structured_report"]["path"])
            catalog = read_json(row["catalog"]["path"])
            text = resolve_path(row["text_report"]["path"]).read_text(encoding="utf8")
            old_record(case["observed"]["path"], case["observed"]["sha256"])
            observed = np.load(case["observed"]["path"], allow_pickle=False)
            old_record(case["mapping_path"])
            with np.load(case["mapping_path"], allow_pickle=False) as package:
                context = package["context_source_ids"].astype(np.int64)
            old_record(case["graph_path"])
            with np.load(case["graph_path"], allow_pickle=False) as package:
                original_free = package["free_mask"].astype(bool)
            with np.load(resolve_path(selection["path"]), allow_pickle=False) as package:
                source_ids = package["free_source_ids"].astype(np.int64)
                free_context = package["free_context_ids"].astype(np.int64)
                edge_index = package["free_edge_index"].astype(np.int64)
                score, area = package["new_score"].astype(np.float64), package["area"].astype(np.float64)
                valid = package["valid_mask"].astype(bool)
                masks = {"attention": package["attention_mask"].astype(bool), "threshold": package["abnormal_mask"].astype(bool)}
            check(case_id + "_original_F_IDs", np.array_equal(source_ids, np.sort(context[original_free])))
            check(case_id + "_context_map", np.array_equal(source_ids, context[free_context]))
            check(case_id + "_case_binding", facts["source_id"] == case["source"] and facts["observation_id"] == case_id)
            check(case_id + "_observation_version", facts["observation_version_sha256"] == case["observed"]["sha256"])
            check(case_id + "_scope_points", facts["inspection_scope"]["points"] == len(source_ids))
            check(case_id + "_ordinary_facts_no_label_fields", not set(facts).intersection({"normal_control", "damaged_mask", "reference", "features", "embedding", "amplitude_ratio", "position_group"}))
            check(case_id + "_prediction_wording", "模型预测" in text and "候选待核查" in text)
            check(case_id + "_no_invented_parts", not any(term in text for term in ("左脸", "右脸", "眼窝", "关节部位", "保证修复")))
            F_points += len(source_ids)
        with measure(timings, "independent_current_area_and_source_edges"):
            if case["source"] not in sources:
                old_record(case["snapshot"]["path"], case["snapshot"]["sha256"])
                with np.load(case["snapshot"]["path"], allow_pickle=False) as package:
                    sources[case["source"]] = (package["vertices"].astype(np.float64), package["triangles"].astype(np.int64))
            base_vertices, triangles = sources[case["source"]]
            current = base_vertices.copy()
            current[context] = observed
            if case["patch_id"] not in patches:
                point_in_F = np.zeros(len(current), dtype=bool)
                point_in_F[source_ids] = True
                incident = triangles[np.any(point_in_F[triangles], axis=1)]
                source_pairs = np.concatenate((incident[:, [0, 1]], incident[:, [1, 2]], incident[:, [2, 0]]))
                source_pairs.sort(axis=1)
                source_pairs = np.unique(source_pairs, axis=0)
                source_pairs = source_pairs[source_pairs[:, 0] != source_pairs[:, 1]]
                source_pairs = source_pairs[np.all(point_in_F[source_pairs], axis=1)]
                patches[case["patch_id"]] = incident, source_pairs
            incident, source_pairs = patches[case["patch_id"]]
            point_values = current[incident]
            triangle_area = np.linalg.norm(np.cross(point_values[:, 1] - point_values[:, 0], point_values[:, 2] - point_values[:, 0]), axis=1) / 2.0
            full_area = np.zeros(len(current), dtype=np.float64)
            for corner in range(3):
                np.add.at(full_area, incident[:, corner], triangle_area / 3.0)
            close(case_id + "_lumped_current_area", area, full_area[source_ids])
            from_edges = np.sort(source_ids[edge_index.T], axis=1)
            from_edges = from_edges[np.lexsort((from_edges[:, 1], from_edges[:, 0]))]
            check(case_id + "_complete_source_F_edges", np.array_equal(from_edges, source_pairs))
            close(case_id + "_F_area", facts["inspection_scope"]["area_native"], area.sum())
        with measure(timings, "independent_A_prefix_and_B_threshold"):
            order = np.lexsort((source_ids, -score))
            expected_attention = np.zeros(len(source_ids), dtype=bool)
            allowance, spent = float(np.sum(area)) * .25, 0.0
            for index in order:
                if spent + float(area[index]) > allowance:
                    break
                expected_attention[index] = True
                spent += float(area[index])
            check(case_id + "_A_prefix", np.array_equal(masks["attention"], expected_attention))
            check(case_id + "_B_threshold", np.array_equal(masks["threshold"], score > threshold))
        for mode in ("attention", "threshold"):
            with measure(timings, "independent_components_and_report_coverage"):
                mask = masks[mode]
                independent = independent_components(mask, edge_index, source_ids)
                lookup = {int(source_id): index for index, source_id in enumerate(source_ids)}
                independent.sort(key=lambda ids: (-float(np.sum([area[lookup[source_id]] * score[lookup[source_id]] for source_id in ids], dtype=np.float64)), min(ids)))
                regions = catalog["regions"][mode]
                selected_counts[mode] += int(np.count_nonzero(mask))
                empty_counts[mode] += int(not np.any(mask))
                summary = facts["attention"] if mode == "attention" else facts["threshold_anomaly_prediction"]
                check(case_id + mode + "_region_count", len(regions) == len(independent) == summary["region_count"])
                check(case_id + mode + "_selected_point_count", summary["selected_points"] == int(np.count_nonzero(mask)))
                close(case_id + mode + "_selected_area", summary["selected_area_native"], area[mask].sum())
                check(case_id + mode + "_empty_is_readable", bool(regions) or summary["selected_points"] == 0)
                if mode == "attention":
                    check(case_id + "_top3_limit", len(summary["top_regions"]) == min(3, len(regions)))
                    check(case_id + "_top3_order", [r["reference"] for r in summary["top_regions"]] == [r["reference"] for r in regions[:3]])
                    check(case_id + "_remaining_count", summary["remaining_region_count"] == max(0, len(regions) - 3))
                    close(case_id + "_remaining_area", summary["remaining_area_native"], sum(r["area_native"] for r in regions[3:]))
                for region, expected_ids in zip(regions, independent):
                    reference = region["reference"]
                    check(case_id + "_reference_unique", reference not in seen_refs)
                    seen_refs.add(reference)
                    resolved = resolve_region(reference, reference_index=references)
                    check(reference + "_IDs", resolved["source_ids"] == expected_ids)
                    check(reference + "_model_binding", resolved["identity"]["model"] == report["model_identity"])
                    check(reference + "_observation_binding", resolved["identity"]["observation_id"] == case_id)
                    check(reference + "_source_binding", resolved["identity"]["source_id"] == case["source"])
                    check(reference + "_mode_binding", resolved["identity"]["selection_mode"] == mode)
                    rows = np.array([lookup[source_id] for source_id in expected_ids], dtype=np.int64)
                    actual_points = np.asarray(resolved["current_positions_native"], dtype=np.float64)
                    check(reference + "_current_positions_bitwise", np.array_equal(actual_points.view(np.uint64), current[source_ids[rows]].view(np.uint64)))
                    close(reference + "_area_payload", resolved["lumped_area_native"], area[rows])
                    close(reference + "_score_payload", resolved["model_scores"], score[rows])
                    check(reference + "_availability", resolved["model_score_available"] == valid[rows].tolist())
                    close(reference + "_priority", region["priority_native_area_times_score"], np.sum(area[rows] * score[rows]))
                    close(reference + "_bboxmin", region["geometry"]["bbox_native"]["min"], actual_points.min(axis=0))
                    close(reference + "_bboxmax", region["geometry"]["bbox_native"]["max"], actual_points.max(axis=0))
                    centroid = np.average(actual_points, axis=0, weights=area[rows]) if area[rows].sum() > 0 else actual_points.mean(axis=0)
                    close(reference + "_centroid", region["geometry"]["centroid_native"], centroid)
                    close(reference + "_score_summary", [region["scores"]["min"], region["scores"]["mean"], region["scores"]["max"]],
                          [score[rows].min(), score[rows].mean(), score[rows].max()])
                    check(reference + "_catalog_facts_roundtrip", resolved["facts"] == region)
    check("all_region_references_accounted", seen_refs == set(references["regions"]))
    check("all109443_F_points", F_points == 109443)
    expected_audit = [min(row["id"] for row in report["cases"] if row["purpose"] == "development_train_pool" and row["normal_control"])]
    for position in ("center", "offcenter"):
        expected_audit.append(min(row["id"] for row in report["cases"] if row["purpose"] == "validation"
                                  and not row["normal_control"] and row["position_group"] == position))
    check("fixed_three_report_audit_IDs", report["audit_case_ids"] == expected_audit)
    try:
        resolve_region("m6perception://v1/region/" + "0" * 64, reference_index=references)
        check("unknown_reference_rejected", False)
    except KeyError:
        check("unknown_reference_rejected", True)
    output = {"cycle_id": "M6-PERCEPTION-001", "status": "passed_region_reference_contract_verification" if not failures else "failed_region_reference_contract_verification",
              "check_count": check_count, "failures": failures, "coverage": {"cases": len(case_rows), "F_points": F_points,
                  "references": len(seen_refs), "selected_point_observations": selected_counts, "empty_case_counts": empty_counts},
              "audit_case_ids": expected_audit, "largest_compared_absolute_difference": largest_difference,
              "input_file_identities": list(used.values()), "timings": timings,
              "source_sha256": {name: file_identity(HERE / name)["sha256"] for name in ("verify_regions.py", "resolve_region.py", "region_common.py")},
              "wall_s_before_final_report": time.perf_counter() - started, "CPU_s_before_final_report": time.process_time() - cpu,
              "bootstrap_to_report_wall_s": time.perf_counter() - BOOT_WALL, "bootstrap_to_report_CPU_s": time.process_time() - BOOT_CPU,
              "own_process_before_report": process_resources(), "model_forwards": 0, "training": 0,
              "new_scores_or_repairs": 0, "LLM_consumer_evaluation": 0,
              "measurement_scope": "saved report/reference and current geometry arithmetic only, final JSON write/exit outside self window"}
    write_json("REGION_VERIFY.json", output)
    print(json.dumps({"status": output["status"], "checks": check_count, "failures": failures[:10]}))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
