"""Current saved-geometry safeguards for the matched-reference restoration task."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m6_shape_pretrain_001/private/deps"))
import numpy as np


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


CORE = load_module("_matched003_exact_geometry", HERE.parent / "m6_refine_001/quality.py")


def digest(array):
    value = np.ascontiguousarray(array)
    result = hashlib.sha256(str(value.dtype).encode())
    result.update(json.dumps(list(value.shape)).encode())
    result.update(value.tobytes())
    return result.hexdigest()


def status(checks):
    values = list(checks.values())
    if any(value is False for value in values):
        return "fail"
    return "pass" if values and all(value is True for value in values) else "unknown"


def _same(first, second):
    return (first is not None and second is not None and first.shape == second.shape
            and first.dtype == second.dtype and first.tobytes() == second.tobytes())


def validate_packet(packet):
    vertices = packet["vertices"]
    local = packet["vertices_local"]
    if vertices.ndim != 2 or vertices.shape[1] != 3 or local.shape != vertices.shape:
        raise ValueError("saved_source_coordinate_shape_mismatch")
    if local.dtype != np.float32 or not np.isfinite(local).all() or not np.isfinite(vertices).all():
        raise ValueError("finite_native_float32_and_world_coordinates_required")
    if "vertices_world" in packet and not np.array_equal(vertices, packet["vertices_world"]):
        raise ValueError("saved_world_coordinate_aliases_disagree")
    faces = packet["faces"]
    if faces.ndim != 2 or faces.shape[1] != 3 or not np.issubdtype(faces.dtype, np.integer):
        raise ValueError("integer_triangle_array_required")
    if len(faces) and (faces.min() < 0 or faces.max() >= len(vertices)):
        raise ValueError("triangle_vertex_out_of_range")
    matrix = packet["matrix_world"]
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise ValueError("finite_saved_matrix_required")
    source_ids = packet["source_ids"]
    if source_ids.shape != (len(vertices),) or not np.issubdtype(source_ids.dtype, np.integer):
        raise ValueError("full_integer_source_ID_vector_required")
    reconstructed = local.astype(np.float64) @ matrix[:3, :3].T + matrix[:3, 3]
    return dict(source_index_mapping=bool(np.array_equal(source_ids, np.arange(len(vertices)))),
                world_matches_saved_native_and_matrix=bool(np.allclose(vertices, reconstructed, rtol=0, atol=1e-14)))


def geometry_quality(before, after, fixed, spec, before_scene=None, after_scene=None,
                     *, deadline=None, check_intersections=True):
    started, cpu = time.perf_counter(), time.process_time()
    initial_checks = validate_packet(before)
    current_checks = validate_packet(after)
    initial, current = before["vertices"], after["vertices"]
    native_before, native_after = before["vertices_local"], after["vertices_local"]
    faces, actual_faces = before["faces"], after["faces"]
    if initial.shape != current.shape:
        raise ValueError("saved_full_source_coordinate_shape_mismatch")
    I = np.asarray(fixed["I_ids"], dtype=np.int64)
    F = np.asarray(fixed["F_source_ids"], dtype=np.int64)
    for ids in (I, F):
        if ids.ndim != 1 or not len(ids) or len(np.unique(ids)) != len(ids) or ids.min() < 0 or ids.max() >= len(initial):
            raise ValueError("nonempty_unique_in_range_source_domain_required")
    if not np.isin(I, F).all():
        raise ValueError("edit_domain_inside_observation_domain_required")
    outside = np.ones(len(initial), dtype=bool)
    outside[I] = False
    changed = np.any(native_before.view(np.uint32) != native_after.view(np.uint32), axis=1)
    changed_ids = np.flatnonzero(changed)
    active = np.union1d(I, changed_ids)
    delta = current - initial
    lengths = np.linalg.norm(delta, axis=1)
    diagonal = float(np.linalg.norm(np.ptp(initial, axis=0)))
    area_tolerance = 64 * np.finfo(float).eps * diagonal**2
    template = CORE._face_changes(initial, current, faces, active, area_tolerance)
    before_keys, before_unique = CORE._triangle_keys(faces, before.get("triangle_polygon_ids"))
    after_keys, after_unique = CORE._triangle_keys(actual_faces, after.get("triangle_polygon_ids"))
    before_lookup = {key: index for index, key in enumerate(before_keys)}
    original_bad = {before_keys[index] for index in template["original_degenerate_face_ids"]}
    old_cross = np.cross(initial[faces[:, 1]] - initial[faces[:, 0]], initial[faces[:, 2]] - initial[faces[:, 0]])
    new_cross = np.cross(current[actual_faces[:, 1]] - current[actual_faces[:, 0]], current[actual_faces[:, 2]] - current[actual_faces[:, 0]])
    new_bad = np.flatnonzero(np.linalg.norm(new_cross, axis=1) <= area_tolerance)
    definite_bad = [int(index) for index in new_bad if after_keys[index] in before_lookup and after_keys[index] not in original_bad]
    unmapped_bad = [int(index) for index in new_bad if after_keys[index] not in before_lookup]
    reversed_actual, unmapped_affected = [], []
    for index in np.flatnonzero(np.isin(actual_faces, active).any(axis=1)):
        prior = before_lookup.get(after_keys[index])
        if prior is None:
            unmapped_affected.append(int(index))
        elif after_keys[index] not in original_bad and np.dot(old_cross[prior], new_cross[index]) <= 0:
            reversed_actual.append(int(index))
    edges = CORE._edges(faces)
    edges = edges[np.isin(edges, active).any(axis=1)]
    edge_lengths = np.linalg.norm(initial[edges[:, 1]] - initial[edges[:, 0]], axis=1)
    usable = edge_lengths > 64 * np.finfo(float).eps * max(diagonal, 1.)
    gradient = np.divide(np.linalg.norm(delta[edges[:, 1]] - delta[edges[:, 0]], axis=1), edge_lengths,
                         out=np.full(len(edges), np.nan), where=usable)
    after_lengths = np.linalg.norm(current[edges[:, 1]] - current[edges[:, 0]], axis=1)
    strain = np.divide(after_lengths - edge_lengths, edge_lengths, out=np.full(len(edges), np.nan), where=usable)
    budget = float(spec["max_cumulative_displacement_m"])
    precision = float(spec["world_preservation_tol"])
    if not np.isfinite(budget + precision) or budget <= 0 or precision < 0:
        raise ValueError("positive_finite_budget_and_nonnegative_precision_required")
    checks = dict(outside_I_local_float32_bitwise=_same(native_before[outside], native_after[outside]),
        outside_I_world_save_precision=bool(np.max(np.abs(delta[outside])) <= precision) if outside.any() else True,
        source_vertex_ids=_same(before.get("source_ids"), after.get("source_ids")),
        native_polygon_offsets=_same(before.get("poly_offsets"), after.get("poly_offsets")),
        native_polygon_vertices=_same(before.get("poly_vertices"), after.get("poly_vertices")),
        target_matrix=_same(before.get("matrix_world"), after.get("matrix_world")),
        cumulative_displacement_budget=bool(lengths.max() <= budget + precision),
        initial_source_index_mapping=initial_checks["source_index_mapping"],
        current_source_index_mapping=current_checks["source_index_mapping"],
        initial_world_from_saved_native=initial_checks["world_matches_saved_native_and_matrix"],
        current_world_from_saved_native=current_checks["world_matches_saved_native_and_matrix"],
        no_new_template_degenerate=not template["new_degenerate_face_ids"],
        no_template_reversal=not template["reversed_face_ids"])
    checks["no_new_actual_degenerate"] = None if not (before_unique and after_unique) else False if definite_bad else None if unmapped_bad else True
    checks["no_actual_stable_key_reversal"] = False if reversed_actual else None if unmapped_affected or not (before_unique and after_unique) else True
    if "protected_ids" in fixed:
        protected = np.asarray(fixed["protected_ids"], dtype=np.int64)
        checks["explicit_protected_native_bitwise"] = _same(native_before[protected], native_after[protected])
    geometry_identical = (_same(native_before, native_after) and _same(before.get("matrix_world"), after.get("matrix_world"))
                          and _same(faces, actual_faces))
    if geometry_identical:
        contact = dict(status="pass", no_new_extra_pairs=True, reason="identical_saved_geometry_and_triangle_arrays",
                       affected_changed_faces=0, scoped_allowed_points=len(I), exact_pair_scan_executed=False)
    elif check_intersections:
        contact = CORE.self_intersection_delta(initial, current, faces, actual_faces, active,
                    before.get("triangle_polygon_ids"), after.get("triangle_polygon_ids"), deadline)
        contact["exact_pair_scan_executed"] = True
    else:
        contact = dict(status="unknown", no_new_extra_pairs=None, reason="explicit_local_test_skip", exact_pair_scan_executed=False)
    checks["no_new_extra_intersections"] = contact["no_new_extra_pairs"]
    scene_keys = ("other_objects_sha256", "target_materials_sha256", "scene_structure_sha256", "target_topology_sha256")
    scenes = {key: bool(before_scene[key] == after_scene[key]) if before_scene is not None and after_scene is not None
              and key in before_scene and key in after_scene else None for key in scene_keys}
    if spec.get("require_scene_preservation", True):
        checks.update(scenes)
    actual_record = dict(triangles=len(actual_faces), definite_new_degenerate=definite_bad, unmapped_degenerate=unmapped_bad,
        stable_key_reversed=reversed_actual, unmapped_affected=unmapped_affected, ordered_array_identical=_same(faces, actual_faces),
        stable_key_sets_identical=bool(before_unique and after_unique and set(before_keys) == set(after_keys)))
    contact_summary = {key: contact[key] for key in ("status", "no_new_extra_pairs", "reason", "exact_pair_scan_executed") if key in contact}
    contact_summary.update(new_pair_count=len(contact.get("new_pairs", [])), changed_relation_count=len(contact.get("changed_relations", [])),
                           full_record="raw_geometry.self_intersection")
    transition = np.isin(edges, I).sum(axis=1) == 1
    return dict(status=status(checks), checks=checks,
        displacement=dict(maximum_world=float(lengths.max()), maximum_allowed_world=budget, save_precision_allowance=precision,
            changed_vertices=len(changed_ids), changed_outside_I=int(changed[outside].sum()),
            outside_I_maximum_world_abs=float(np.max(np.abs(delta[outside]))) if outside.any() else 0.,
            world_X_maximum_change=float(np.max(np.abs(delta[:, 0]))),
            F_depth_X_extent_before=float(np.ptp(initial[F, 0])), F_depth_X_extent_after=float(np.ptp(current[F, 0]))),
        geometry=dict(source_points=len(initial), observation_points=len(F), allowed_points=len(I),
            template_faces=dict(triangles=len(faces), affected_triangles=template["affected_triangles"],
                original_degenerate_count=len(template["original_degenerate_face_ids"]), new_degenerate_count=len(template["new_degenerate_face_ids"]),
                reversed_count=len(template["reversed_face_ids"]), affected_normal_angle_deg=template["affected_normal_angle_deg"]),
            actual_faces=dict(triangles=len(actual_faces), definite_new_degenerate_count=len(definite_bad),
                unmapped_degenerate_count=len(unmapped_bad), stable_key_reversed_count=len(reversed_actual),
                unmapped_affected_count=len(unmapped_affected), ordered_array_identical=actual_record["ordered_array_identical"],
                stable_key_sets_identical=actual_record["stable_key_sets_identical"]),
            incident_edge_gradient=CORE._distribution(gradient), zero_or_tiny_incident_edges=int((~usable).sum()),
            gradient_and_normal_role="observation", scene_preservation=dict(status=status(scenes), checks=scenes),
            self_intersection=contact_summary),
        transition=dict(incident_edges=len(edges), boundary_crossing_edges=int(transition.sum()),
            edge_displacement_gradient=CORE._distribution(gradient), edge_length_relative_strain=CORE._distribution(strain),
            boundary_crossing_gradient=CORE._distribution(gradient[transition])),
        raw_geometry=dict(template_faces=template, actual_faces=actual_record, self_intersection=contact,
            incident_edges=edges.tolist(), edge_displacement_gradient=[float(value) if np.isfinite(value) else None for value in gradient],
            edge_length_relative_strain=[float(value) if np.isfinite(value) else None for value in strain]),
        identity=dict(initial_world=digest(initial), actual_world=digest(current), initial_local=digest(native_before),
                      actual_local=digest(native_after), I=digest(I), F=digest(F)),
        wall_s=time.perf_counter() - started, cpu_s=time.process_time() - cpu)
