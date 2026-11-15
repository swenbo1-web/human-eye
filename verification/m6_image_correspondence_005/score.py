"""Private restoration scoring of final actual saved-file readback packets."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from evaluate import packet
import numpy as np


def identity(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def distribution(values):
    values = np.asarray(values, dtype=np.float64)
    if not len(values):
        return dict(points=0, RMSE_m=None, p95_m=None, maximum_m=None)
    return dict(points=len(values), RMSE_m=float(np.sqrt(np.mean(values**2))),
                p95_m=float(np.quantile(np.abs(values), .95)), maximum_m=float(np.max(np.abs(values))))


def paired_metrics(initial_error, final_error, ids):
    before = distribution(initial_error[ids])
    after = distribution(final_error[ids])
    baseline = before["RMSE_m"]
    fraction = (baseline - after["RMSE_m"]) / baseline if baseline else None
    return dict(before=before, after=after, RMSE_reduction_fraction=fraction)


def check_receipt(after_path, receipt_path):
    receipt = json.loads(Path(receipt_path).read_bytes())
    if receipt.get("status") != "read_actual_saved_blend" or receipt.get("input_unchanged") is not True:
        raise ValueError("actual_saved_blend_independent_read_receipt_required")
    readback = identity(after_path)
    expected = receipt["readback_npz"]
    if readback["sha256"] != expected["sha256"] or readback["bytes"] != expected["bytes"]:
        raise ValueError("scored_packet_does_not_match_saved_readback_receipt")
    saved = identity(receipt["input_blend"]["path"])
    if saved != receipt["input_blend"]:
        raise ValueError("scored_saved_blend_identity_changed")
    if receipt.get("writer_arrays_or_receipts_read") is not False:
        raise ValueError("readback_receipt_must_confirm_independent_mesh_export")
    return dict(independent_saved_readback_verified=True, reader_receipt=identity(receipt_path), saved_blend=saved)


def score_packet(after_path, target_path, output_path, *, receipt_path=None):
    started, cpu = time.perf_counter(), time.process_time()
    current, target = packet(after_path), packet(target_path)
    clean = np.asarray(target["clean_vertices_world"], dtype=np.float64)
    initial = np.asarray(target["initial_vertices_world"], dtype=np.float64)
    final = np.asarray(current["vertices_world"] if "vertices_world" in current else current["vertices"], dtype=np.float64)
    if clean.ndim != 2 or clean.shape[1] != 3 or clean.shape != initial.shape or clean.shape != final.shape:
        raise ValueError("private_target_and_saved_readback_coordinate_shape_mismatch")
    if not all(np.isfinite(value).all() for value in (clean, initial, final)):
        raise ValueError("private_score_coordinates_must_be_finite")
    ids = np.arange(len(clean), dtype=np.int64)
    if not np.array_equal(current["source_ids"], ids) or not np.array_equal(target["source_ids"], ids):
        raise ValueError("private_score_requires_preserved_full_source_index_mapping")
    F, I, support = (np.asarray(target[key], dtype=np.int64) for key in ("F_source_ids", "I_ids", "support_ids"))
    for selected in (F, I, support):
        if selected.ndim != 1 or not len(selected) or len(np.unique(selected)) != len(selected) or selected.min() < 0 or selected.max() >= len(clean):
            raise ValueError("private_score_source_domains_invalid")
    if not np.isin(support, I).all() or not np.isin(I, F).all():
        raise ValueError("private_support_inside_editable_inside_observation_required")
    if (len(F), len(I), len(support)) != (410, 274, 47):
        raise ValueError("fixed_sample05_scoring_domains_changed")
    normal = np.setdiff1d(F, support)
    normal_editable = np.setdiff1d(I, support)
    outside = np.setdiff1d(ids, I)
    initial_delta, final_delta = initial - clean, final - clean
    initial_error = np.linalg.norm(initial_delta, axis=1)
    final_error = np.linalg.norm(final_delta, axis=1)
    actual_displacement = np.linalg.norm(final - initial, axis=1)
    metrics = {name: paired_metrics(initial_error, final_error, selected) for name, selected in
        (("support_47", support), ("observation_410", F), ("normal_363", normal), ("normal_editable_227", normal_editable))}
    normal_misedit = distribution(actual_displacement[normal_editable])
    checks = dict(support_RMSE_decreases_at_least_30_percent=bool(metrics["support_47"]["RMSE_reduction_fraction"] >= .30),
        observation_RMSE_decreases=bool(metrics["observation_410"]["after"]["RMSE_m"] < metrics["observation_410"]["before"]["RMSE_m"]),
        normal_editable_displacement_RMS_at_most_0_10_mm=bool(normal_misedit["RMSE_m"] <= .00010))
    provenance = check_receipt(after_path, receipt_path) if receipt_path else dict(independent_saved_readback_verified=False,
        reason="caller_supplied_packet_without_reader_receipt")
    axis_metrics = {}
    for axis, name in enumerate(("X", "Y", "Z")):
        axis_metrics[name] = {label: dict(error_to_clean=distribution(final_delta[selected, axis]),
            change_from_damaged=distribution((final - initial)[selected, axis]))
            for label, selected in (("support", support), ("observation", F), ("normal", normal), ("normal_editable", normal_editable))}
    output = Path(output_path).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError("private_scoring_output_outside_current_batch")
    output.parent.mkdir(parents=True, exist_ok=True)
    points = output.with_name(output.stem + "_points.npz")
    np.savez_compressed(points, source_ids=ids, F_source_ids=F, I_ids=I, support_ids=support,
        normal_ids=normal, normal_editable_ids=normal_editable,
        initial_error_world=initial_delta, final_error_world=final_delta,
        initial_error_norm=initial_error, final_error_norm=final_error, displacement_world=final - initial,
        displacement_norm=actual_displacement)
    result = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", sample="sample_05", unit="m", checks=checks,
        restoration_quality_pass=bool(all(checks.values())), metrics=metrics,
        normal_editable_misedit=normal_misedit, normal_all_misedit=distribution(actual_displacement[normal]),
        outside_editable_displacement=distribution(actual_displacement[outside]),
        changed_vertices_world_above_1e_12_m=int((actual_displacement > 1e-12).sum()),
        depth_and_axis_observations=dict(depth_axis="world_X", per_axis=axis_metrics,
            bounds_interpretation="410-region world bounds. The front camera looks along -worldX and -worldY points toward the torso.",
            F_bbox_clean=dict(minimum=clean[F].min(axis=0).tolist(), maximum=clean[F].max(axis=0).tolist()),
            F_bbox_damaged=dict(minimum=initial[F].min(axis=0).tolist(), maximum=initial[F].max(axis=0).tolist()),
            F_bbox_final=dict(minimum=final[F].min(axis=0).tolist(), maximum=final[F].max(axis=0).tolist())),
        identities=dict(final_readback=identity(after_path), private_target=identity(target_path), point_evidence=identity(points)),
        provenance=provenance,
        coordinate_contract="Same-pose full-source IDs index world coordinates. Initial baseline is the actual saved damaged-file readback.",
        thresholds=dict(support_RMSE_reduction_fraction=.30, normal_editable_displacement_RMS_m=.00010,
            observation_RMSE_rule="strictly_below_damaged_baseline"),
        technical_quality="evaluated_separately_by_target_free_saved_geometry_QA",
        wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    return result


def score_session(session_dir, target_path, output_path, *, receipt_path):
    session = Path(session_dir).resolve()
    state = json.loads((session / "session.json").read_bytes())
    if state.get("pending"):
        raise ValueError("finish_pending_actual_save_readback_before_private_score")
    saved = identity(state["current_blend"])
    if saved != state["current_blend_identity"]:
        raise ValueError("session_final_saved_blend_identity_changed")
    receipt = json.loads(Path(receipt_path).read_bytes())
    if receipt["input_blend"]["sha256"] != saved["sha256"]:
        raise ValueError("private_score_receipt_is_not_last_session_saved_file")
    return score_packet(receipt["readback_npz"]["path"], target_path, output_path, receipt_path=receipt_path)


def main():
    parser = argparse.ArgumentParser()
    for name in ("after", "target", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = score_packet(args.after, args.target, args.output, receipt_path=args.receipt)
    print(json.dumps(dict(restoration_quality_pass=result["restoration_quality_pass"], checks=result["checks"])))


if __name__ == "__main__":
    main()
