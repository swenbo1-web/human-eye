"""Audit the actual consumer-recorded fit supports against isolated private labels."""

import argparse
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import identity, read, write
from delivery_common import session_names
import numpy as np

REQUIRED = {"fit_target_ids", "fit_offsets", "fit_source_ids", "fit_design_rank", "fit_estimated_amplitude_m"}


def validate_arrays(arrays, source_count):
    targets, offsets, ids = (arrays[key] for key in ("fit_target_ids", "fit_offsets", "fit_source_ids"))
    if targets.ndim != 1 or not np.issubdtype(targets.dtype, np.integer) or np.any((targets < -1) | (targets >= source_count)):
        raise ValueError("invalid_fit_target_source_IDs")
    if offsets.shape != (len(targets) + 1,) or not np.issubdtype(offsets.dtype, np.integer):
        raise ValueError("invalid_fit_offsets_shape_or_dtype")
    if offsets[0] != 0 or offsets[-1] != len(ids) or np.any(np.diff(offsets) < 0):
        raise ValueError("invalid_fit_offsets_partition")
    if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer) or np.any((ids < 0) | (ids >= source_count)):
        raise ValueError("invalid_fit_support_source_IDs")
    for key in ("fit_design_rank", "fit_estimated_amplitude_m"):
        if arrays[key].shape != targets.shape or not np.isfinite(arrays[key]).all():
            raise ValueError("invalid_fit_per_target_field_" + key)


def audit_record(path, initial, target, metadata):
    with np.load(path, allow_pickle=False) as archive:
        arrays = dict(archive)
    validate_arrays(arrays, len(initial["vertices_world"]))
    version = metadata.get("observed_version", metadata.get("version"))
    if type(version) is not int or version < 0:
        return dict(status="current_geometry_version_unknown", diagnostic=identity(path), metadata=metadata)
    current_path = HERE / "private/cases/repair/initial.npz"
    if version != 0:
        session = path.parents[1]
        current_path = session / "versions" / str(version).zfill(3) / "independent00/readback.npz"
    if not current_path.exists():
        return dict(status="current_geometry_version_missing", diagnostic=identity(path), metadata=metadata)
    with np.load(current_path, allow_pickle=False) as archive:
        current = dict(archive)
    vertices = current["vertices_world"]
    normals = initial["n0"] if version == 0 else None
    if normals is None:
        triangles = vertices[current["faces"]]
        cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        normals = np.zeros_like(vertices)
        for corner in range(3):
            np.add.at(normals, current["faces"][:, corner], cross)
        norms = np.linalg.norm(normals, axis=1)
        normals = np.divide(normals, norms[:, None], out=np.zeros_like(normals), where=norms[:, None] > 0)
    support, clean = target["support_ids"], target["clean_vertices_world"]
    exclusions_path = HERE / "private/correspondence_preflight/baseline/ARRAYS.npz"
    positive_exclusion = None
    if version == 0 and exclusions_path.exists():
        with np.load(exclusions_path, allow_pickle=False) as archive:
            positive_exclusion = archive["positive_attention_source_ids"]
    rows = []
    for index, target_id in enumerate(arrays["fit_target_ids"]):
        start, end = arrays["fit_offsets"][index:index + 2]
        used = arrays["fit_source_ids"][start:end]
        positions, normal_values = vertices[used], normals[used]
        center = np.zeros(3)
        if len(positions):
            center = positions.mean(axis=0)
        if target_id >= 0:
            center = vertices[target_id]
        relative = positions - center
        singular = np.linalg.svd(relative, compute_uv=False) if len(used) else np.empty(0)
        row = dict(target_source_id=int(target_id), used_support_count=len(used), unique_support_count=len(np.unique(used)),
            damaged_support_count=int(np.isin(used, support).sum()),
            damaged_support_fraction=float(np.isin(used, support).mean()) if len(used) else None,
            support_source_ids=used.tolist(), reported_design_rank=int(arrays["fit_design_rank"][index]),
            reported_estimated_amplitude_m=float(arrays["fit_estimated_amplitude_m"][index]),
            actual_support_positive_attention_count=int(np.isin(used, positive_exclusion).sum()) if positive_exclusion is not None else None,
            positive_attention_exclusion_fully_observed=bool(not np.isin(used, positive_exclusion).any()) if positive_exclusion is not None else None,
            spatial_singular_values_m=singular.tolist(), spatial_rank=int(np.linalg.matrix_rank(relative)) if len(used) else 0,
            maximum_support_distance_m=float(np.linalg.norm(relative, axis=1).max()) if len(used) else None,
            support_bbox_world=dict(minimum=positions.min(axis=0).tolist(), maximum=positions.max(axis=0).tolist()) if len(used) else None)
        if target_id >= 0:
            normal = arrays["fit_normals"][index] if "fit_normals" in arrays else normals[target_id]
            normal_length = np.linalg.norm(normal)
            normal = normal / normal_length if normal_length > 0 else normals[target_id]
            reference_axis = np.eye(3)[int(np.argmin(np.abs(normal)))]
            tangent0 = np.cross(normal, reference_axis)
            tangent0 /= max(np.linalg.norm(tangent0), 1e-30)
            tangent1 = np.cross(normal, tangent0)
            xy = np.column_stack((relative @ tangent0, relative @ tangent1))
            scale = max(float(np.linalg.norm(xy, axis=1).max()), 1e-12) if len(used) else 1.
            x, y = (xy / scale).T
            design = np.column_stack((np.ones(len(used)), x, y, x * x, x * y, y * y))
            actual_amplitude = float((clean[target_id] - vertices[target_id]) @ normal)
            angular = normal_values @ normal
            row.update(current_normal_target_amplitude_m=actual_amplitude,
                estimated_amplitude_error_m=float(arrays["fit_estimated_amplitude_m"][index] - actual_amplitude),
                target_is_damaged=bool(target_id in support),
                canonical_unweighted_quadratic_design_rank=int(np.linalg.matrix_rank(design)) if len(used) else 0,
                canonical_design_role="Independent unweighted current tangent-plane quadratic coverage observation; recorded consumer rank may use another basis or weights.",
                tangent_direction_quadrants_occupied=int(len(set(map(tuple, (xy >= 0).tolist())))) if len(used) else 0,
                support_normal_dot_target_minimum=float(angular.min()) if len(used) else None,
                support_normal_dot_target_maximum=float(angular.max()) if len(used) else None)
        rows.append(row)
    return dict(status="audited", diagnostic=identity(path), metadata=metadata, observed_version=version,
        current_geometry=identity(current_path), target_fits=len(rows), fits=rows,
        positive_attention_exclusion_evidence=identity(exclusions_path) if positive_exclusion is not None else None,
        distinct_actual_fit_support_points=len(np.unique(arrays["fit_source_ids"])),
        distinct_damaged_fit_support_points=len(np.intersect1d(arrays["fit_source_ids"], support)),
        consumer_reported_usage="Diagnostic records contain caller-supplied actual-used arrays. Code and final payload linkage require the retained consumer trace.")


def audit_session(name):
    session = HERE / "private/sessions" / name
    if not session.exists():
        return dict(session=name, status="not_started", diagnostics=[])
    with np.load(HERE / "private/cases/repair/initial.npz", allow_pickle=False) as archive:
        initial = dict(archive)
    with np.load(HERE / "private/scoring/target.npz", allow_pickle=False) as archive:
        target = dict(archive)
    records = []
    for path in sorted((session / "payloads").glob("*.npz")):
        with np.load(path, allow_pickle=False) as archive:
            selected = REQUIRED.issubset(archive.files)
        if not selected:
            continue
        metadata_path = path.with_suffix(".json")
        metadata = read(metadata_path) if metadata_path.exists() else {}
        try:
            records.append(audit_record(path, initial, target, metadata))
        except (ValueError, KeyError, IndexError) as error:
            records.append(dict(status="invalid_record", diagnostic=identity(path), error=dict(type=type(error).__name__, message=str(error))))
    return dict(session=name, status="audited" if records else "missing_actual_fit_diagnostics", diagnostics=records,
        recorded_fit_count=sum(row.get("target_fits", 0) for row in records))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("v1", "v2", "all"), default="v1")
    args = parser.parse_args()
    started, cpu = time.perf_counter(), time.process_time()
    rows = [audit_session(name) for name in session_names(args.stage)]
    result = dict(cycle_id="M6-IMAGE-CORRESPONDENCE-005", stage=args.stage, sessions=rows,
        status="complete" if all(row["status"] == "audited" for row in rows) else "incomplete_evidence",
        wall_s=time.perf_counter() - started, CPU_s=time.process_time() - cpu, actual_Blender_calls=0, actual_Pro_calls=0,
        private_scoring_scope="Only the independent audit loads clean coordinates or support labels. Missing diagnostics retain missing status.")
    write("FIT_AUDIT_" + args.stage + ".json", result)
    print(dict(status=result["status"], sessions=len(rows), recorded_fits=sum(row.get("recorded_fit_count", 0) for row in rows)))


if __name__ == "__main__":
    main()
