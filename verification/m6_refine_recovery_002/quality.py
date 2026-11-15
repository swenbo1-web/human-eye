"""Readback-based local refinement measurements and exact scoped self contacts."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m6_shape_pretrain_001/private/deps"))
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

KERNEL_PATH = HERE.parent / "m6_coupled_probe_001/evaluate.py"
kernel_spec = importlib.util.spec_from_file_location("_refine_exact_coupled", KERNEL_PATH)
coupled = importlib.util.module_from_spec(kernel_spec)
kernel_spec.loader.exec_module(coupled)


def _digest(array):
    value = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(str(value.dtype).encode())
    digest.update(json.dumps(list(value.shape)).encode())
    digest.update(value.tobytes())
    return digest.hexdigest()


def _bits_equal(first, second):
    return first.shape == second.shape and first.dtype == second.dtype and first.tobytes() == second.tobytes()


def _edges(faces):
    if not len(faces):
        return np.empty((0, 2), dtype=np.int64)
    return np.unique(np.sort(np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1), axis=0)


def _distribution(values):
    values = np.asarray(values, dtype=float).ravel()
    finite = values[np.isfinite(values)]
    return dict(count=len(values), finite_count=len(finite), minimum=float(finite.min()) if len(finite) else None,
                maximum=float(finite.max()) if len(finite) else None,
                median=float(np.median(finite)) if len(finite) else None,
                p95=float(np.quantile(finite, .95)) if len(finite) else None,
                RMS=float(np.sqrt(np.mean(finite**2))) if len(finite) else None)


def _status(checks):
    values = list(checks.values())
    if any(value is False for value in values):
        return "fail"
    return "pass" if all(value is True for value in values) else "unknown"


def _face_changes(before, after, faces, active_ids, tolerance):
    old = before[faces]
    new = after[faces]
    old_cross = np.cross(old[:, 1] - old[:, 0], old[:, 2] - old[:, 0])
    new_cross = np.cross(new[:, 1] - new[:, 0], new[:, 2] - new[:, 0])
    old_length = np.linalg.norm(old_cross, axis=1)
    new_length = np.linalg.norm(new_cross, axis=1)
    old_bad = ~np.isfinite(old_length) | (old_length <= tolerance)
    new_bad = ~np.isfinite(new_length) | (new_length <= tolerance)
    affected = np.isin(faces, active_ids).any(axis=1)
    available = affected & ~old_bad & ~new_bad
    dot = np.einsum("ij,ij->i", old_cross, new_cross)
    angle = np.full(len(faces), np.nan)
    angle[available] = np.degrees(np.arctan2(np.linalg.norm(np.cross(old_cross[available], new_cross[available]), axis=1), dot[available]))
    return dict(triangles=len(faces), affected_triangles=int(affected.sum()),
                original_degenerate_face_ids=np.flatnonzero(old_bad).tolist(),
                new_degenerate_face_ids=np.flatnonzero(new_bad & ~old_bad).tolist(),
                reversed_face_ids=np.flatnonzero(affected & ~old_bad & (dot <= 0)).tolist(),
                unavailable_affected_normal_faces=np.flatnonzero(affected & (old_bad | new_bad)).tolist(),
                affected_normal_angle_deg=_distribution(angle[affected]),
                affected_normal_angles_deg=[float(value) if np.isfinite(value) else None for value in angle[affected]])


def _exact_scan(vertices, faces, active_ids, state_id, deadline):
    active = np.flatnonzero(np.isin(faces, active_ids).any(axis=1)).tolist()
    values = np.asarray(vertices, dtype=np.float64).tolist()
    triangles = np.asarray(faces, dtype=np.int64).tolist()
    factor = coupled.common_factor(values, [])
    state = dict(source_id=state_id, frame=0, coordinate_frame="saved_world_binary64_source_units")
    prepared = coupled.Prepared(values, triangles, active, factor, state, deadline)
    result = coupled.scan(prepared, deadline)
    # The existing scanner conservatively flags every source degenerate. Here a
    # disjoint exact AABB certifies its affected-domain pair as well.
    complete = bool(result["candidate_complete"] and not result["unresolved"] and result["unaccounted_domain_pairs"] == 0)
    result["legacy_scan_complete"] = result["scan_complete"]
    result["scan_complete"] = complete
    result["global_degenerate_faces_preserved"] = result["degenerate_face_ids"]
    result["degenerate_candidate_pairs"] = len(result["unresolved"])
    if complete and result["reason"] == "degenerate_faces_in_scoped_mesh":
        result["reason"] = "source_degenerates_exactly_AABB_separated_from_affected_pairs"
    result["preparation"] = prepared.preparation
    result["affected_face_ids"] = active
    result["scope"] = "all unordered face pairs with at least one incident to allowed or actually changed vertices"
    return result


def _triangle_keys(faces, polygon_ids):
    if polygon_ids is None:
        keys = [(tuple(sorted(int(i) for i in face)),) for face in faces]
    else:
        keys = [(int(polygon), tuple(sorted(int(i) for i in face))) for polygon, face in zip(polygon_ids, faces)]
    return keys, len(keys) == len(set(keys))


def _pair_key(pair, keys):
    return tuple(sorted((keys[pair[0]], keys[pair[1]])))


def _scan_json(scan):
    return {key: ([dict(pair=list(pair), **row) for pair, row in sorted(value.items())] if key == "intersections" else value)
            for key, value in scan.items()}


def self_intersection_delta(before, after, before_faces, after_faces, active_ids,
                            before_polygon_ids=None, after_polygon_ids=None, deadline=None):
    started, cpu = time.perf_counter(), time.process_time()
    local_deadline = min(time.perf_counter() + 180, deadline) if deadline is not None else time.perf_counter() + 180
    result = dict(status="unknown", no_new_extra_pairs=None, new_pairs=[], changed_relations=[],
                  before=None, after=None, reason=None)
    try:
        first = _exact_scan(before, before_faces, active_ids, "refine_before", local_deadline)
        second = _exact_scan(after, after_faces, active_ids, "refine_after", local_deadline)
    except coupled.Stopped as error:
        result["reason"] = str(error)
    else:
        before_keys, before_unique = _triangle_keys(before_faces, before_polygon_ids)
        after_keys, after_unique = _triangle_keys(after_faces, after_polygon_ids)
        before_key_set, after_key_set = set(before_keys), set(after_keys)
        keys_match = before_unique and after_unique and before_key_set == after_key_set
        old = {_pair_key(pair, before_keys): row for pair, row in first["intersections"].items()}
        new = {_pair_key(pair, after_keys): row for pair, row in second["intersections"].items()}
        old_unknown = {_pair_key(pair, before_keys) for pair in first["unresolved"]}
        new_known = sorted(set(new) - set(old) - old_unknown)
        comparable = [pair for pair in new_known if first["candidate_complete"] and before_unique and after_unique and all(key in before_key_set for key in pair)]
        changed = [dict(pair_key=pair, before=old[pair], after=new[pair]) for pair in sorted(set(old) & set(new)) if old[pair] != new[pair]]
        complete = first["scan_complete"] and second["scan_complete"] and keys_match
        ok = False if comparable else True if complete else None
        result.update(status="pass" if ok is True else "fail" if ok is False else "unknown", no_new_extra_pairs=ok,
            before=_scan_json(first), after=_scan_json(second), new_pairs=comparable,
            after_extra_pairs_with_no_before_triangle_key=[pair for pair in new_known if pair not in comparable],
            changed_relations=changed, triangle_key_sets_match=keys_match,
            before_triangle_keys_unique=before_unique, after_triangle_keys_unique=after_unique,
            reason=None if complete else "actual_tessellation_changed_or_scoped_exact_pairs_unresolved",
            original_extra_pair_count=len(old), after_extra_pair_count=len(new),
            source_geometric_predicate="exact dyadic coordinates, extra intersection beyond shared source simplex",
            normalization="independent positive power-of-two integer frames preserve each saved binary64 mesh exactly")
    result.update(wall_s=time.perf_counter()-started, cpu_s=time.process_time()-cpu,
        kernel_sources=[str(KERNEL_PATH), str(coupled.ROOT / "human_eye_plugin/surface_geometry.py")])
    return result


def evaluate_arrays(before_local_f32, after_local_f32, before_world, after_world, faces,
                    F, I, C, center, n0, h, ell, spec, *, after_faces=None,
                    before_poly_offsets=None, before_poly_vertices=None, after_poly_offsets=None,
                    after_poly_vertices=None, before_polygon_ids=None, after_polygon_ids=None,
                    before_matrix=None, after_matrix=None, before_state=None, after_state=None,
                    before_source_ids=None, after_source_ids=None, unreachable_ids=None,
                    deadline=None, check_intersections=True):
    started, cpu = time.perf_counter(), time.process_time()
    before = np.asarray(before_world, dtype=np.float64)
    after = np.asarray(after_world, dtype=np.float64)
    local_before = np.asarray(before_local_f32, dtype=np.float32)
    local_after = np.asarray(after_local_f32, dtype=np.float32)
    faces = np.asarray(faces, dtype=np.int64)
    actual_faces = faces if after_faces is None else np.asarray(after_faces, dtype=np.int64)
    F, I, C = (np.sort(np.asarray(ids, dtype=np.int64)) for ids in (F, I, C))
    normals = np.asarray(n0, dtype=np.float64)
    if before.shape != after.shape or before.ndim != 2 or before.shape[1] != 3 or local_before.shape != before.shape or local_after.shape != before.shape:
        raise ValueError("readback_coordinate_shape_mismatch")
    if normals.shape != before.shape or not np.isfinite(normals).all() or not np.isfinite(before).all() or not np.isfinite(after).all() or not np.isfinite(local_before).all() or not np.isfinite(local_after).all():
        raise ValueError("nonfinite_or_invalid_direction_field")
    if h <= 0 or ell <= 0 or not np.isfinite(h+ell) or not len(I) or not len(C) or center not in I:
        raise ValueError("invalid_fixed_refinement_specification")
    for ids in (F, I, C):
        if not len(ids) or ids[0] < 0 or ids[-1] >= len(before) or len(np.unique(ids)) != len(ids):
            raise ValueError("invalid_source_ID_set")
    if not np.isin(I, F).all() or not np.isin(C, I).all():
        raise ValueError("fixed_target_set_inclusion_mismatch")
    if faces.ndim != 2 or faces.shape[1] != 3 or actual_faces.ndim != 2 or actual_faces.shape[1] != 3:
        raise ValueError("triangles_required")
    if any(len(value) and (value.min() < 0 or value.max() >= len(before)) for value in (faces, actual_faces)):
        raise ValueError("triangle_vertex_out_of_range")
    delta = after-before
    axial = np.einsum("ij,ij->i", delta, normals)
    tangential = np.linalg.norm(delta-axial[:,None]*normals, axis=1)
    lengths = np.linalg.norm(delta, axis=1)
    normal_lengths = np.linalg.norm(normals[I], axis=1)
    outside = np.ones(len(before), dtype=bool)
    outside[I] = False
    changed_local = np.any(local_after.view(np.uint32) != local_before.view(np.uint32), axis=1)
    active_ids = np.union1d(I, np.flatnonzero(changed_local))
    all_edges = _edges(faces)
    incident_edges = all_edges[np.isin(all_edges, active_ids).any(axis=1)]
    edge_lengths = np.linalg.norm(before[incident_edges[:,1]]-before[incident_edges[:,0]], axis=1)
    diagonal = float(np.linalg.norm(np.ptp(before, axis=0)))
    length_tolerance = 64*np.finfo(float).eps*diagonal
    usable_edges = edge_lengths > length_tolerance
    gradient = np.linalg.norm(delta[incident_edges[:,1]]-delta[incident_edges[:,0]], axis=1)
    gradient[usable_edges] /= edge_lengths[usable_edges]
    gradient[~usable_edges] = np.nan
    current_edge_lengths = np.linalg.norm(after[incident_edges[:,1]]-after[incident_edges[:,0]], axis=1)
    strain = np.divide(current_edge_lengths-edge_lengths, edge_lengths, out=np.full_like(edge_lengths,np.nan), where=usable_edges)
    local_faces = faces[np.isin(faces, F).all(axis=1)]
    local_edges = _edges(local_faces)
    high = I[axial[I] > .5*h]
    lookup = np.full(len(before), -1, dtype=np.int64)
    lookup[high] = np.arange(len(high))
    high_edges = local_edges[np.isin(local_edges, high).all(axis=1)]
    if len(high):
        graph = csr_matrix((np.ones(len(high_edges)*2), (np.r_[lookup[high_edges[:,0]], lookup[high_edges[:,1]]], np.r_[lookup[high_edges[:,1]], lookup[high_edges[:,0]]])), shape=(len(high),len(high)))
        component_count, labels = connected_components(graph, directed=False)
        high_components = [high[labels==label].tolist() for label in range(component_count)]
    else:
        component_count, high_components = 0, []
    area_tolerance = 64*np.finfo(float).eps*diagonal**2
    template = _face_changes(before, after, faces, active_ids, area_tolerance)
    current_cross = np.cross(after[actual_faces[:,1]]-after[actual_faces[:,0]],after[actual_faces[:,2]]-after[actual_faces[:,0]])
    current_bad = ~np.isfinite(current_cross).all(axis=1) | (np.linalg.norm(current_cross,axis=1)<=area_tolerance)
    actual_keys_before, unique_before = _triangle_keys(faces,before_polygon_ids)
    actual_keys_after, unique_after = _triangle_keys(actual_faces,after_polygon_ids)
    prior_lookup = {key:index for index,key in enumerate(actual_keys_before)}
    prior_bad_keys = {actual_keys_before[index] for index in template["original_degenerate_face_ids"]}
    new_actual_bad = [index for index in np.flatnonzero(current_bad) if actual_keys_after[index] in prior_lookup and actual_keys_after[index] not in prior_bad_keys]
    unmapped_actual_bad = [index for index in np.flatnonzero(current_bad) if actual_keys_after[index] not in prior_lookup]
    old_triangles = before[faces]
    old_cross = np.cross(old_triangles[:,1]-old_triangles[:,0],old_triangles[:,2]-old_triangles[:,0])
    actual_reversed = []
    for index in np.flatnonzero(np.isin(actual_faces,active_ids).any(axis=1)):
        prior = prior_lookup.get(actual_keys_after[index])
        if prior is not None and actual_keys_after[index] not in prior_bad_keys and np.dot(old_cross[prior],current_cross[index])<=0:
            actual_reversed.append(int(index))
    normal_max = template["affected_normal_angle_deg"]["maximum"]
    gradient_max = _distribution(gradient)["maximum"]
    gate = spec.get("quality_gate", {})
    tangent_tolerance = max(float(spec["tangent_abs_tol"]), .01*h)
    world_preservation_tol = float(spec["world_preservation_tol"])
    if not np.isfinite(world_preservation_tol) or world_preservation_tol < 0:
        raise ValueError("invalid_frozen_world_preservation_tolerance")
    source_ids_ok = None
    if before_source_ids is not None and after_source_ids is not None:
        source_ids_ok = bool(np.asarray(before_source_ids).shape == (len(before),) and
            np.asarray(after_source_ids).shape == (len(after),) and
            np.array_equal(before_source_ids, after_source_ids) and
            len(np.unique(before_source_ids)) == len(before))
    poly_available = all(value is not None for value in (before_poly_offsets,before_poly_vertices,after_poly_offsets,after_poly_vertices))
    poly_ok = bool(np.array_equal(before_poly_offsets,after_poly_offsets) and np.array_equal(before_poly_vertices,after_poly_vertices)) if poly_available else None
    matrix_ok = bool(np.array_equal(before_matrix,after_matrix)) if before_matrix is not None and after_matrix is not None else None
    checks = dict(center_displacement=bool(.95*h<=axial[center]<=1.05*h), core_median=bool(np.median(axial[C])>=.6*h),
        maximum_displacement=bool(lengths.max()<=1.1*h), tangential_residual=bool(tangential[I].max()<=tangent_tolerance),
        fixed_directions_unit=bool(np.isfinite(normals[I]).all() and np.all(np.abs(normal_lengths-1)<=1e-6)),
        outside_I_local_float32_bitwise=_bits_equal(local_before[outside],local_after[outside]),
        outside_I_world_save_precision=bool(np.max(np.abs(delta[outside]))<=world_preservation_tol) if outside.any() else True,
        polygon_topology=poly_ok, source_vertex_ids=source_ids_ok, target_matrix=matrix_ok,
        high_displacement_contiguous=bool(component_count==1 and center in high and np.sum(axial[C]>.5*h)>=int(np.ceil(.5*len(C)))),
        displacement_gradient=bool(gradient_max<=float(gate.get("max_gradient",.2))) if gradient_max is not None and usable_edges.all() else None,
        face_normal_change=bool(normal_max<=float(gate.get("max_normal_change_deg",5.))) if normal_max is not None and not template["unavailable_affected_normal_faces"] else None,
        no_new_template_degenerate=not template["new_degenerate_face_ids"], no_template_reversal=not template["reversed_face_ids"])
    if unreachable_ids is not None:
        unreachable_ids = np.asarray(unreachable_ids, dtype=np.int64)
        if not np.isin(unreachable_ids, I).all():
            raise ValueError("unreachable_source_IDs_outside_I")
        checks["unreachable_I_local_float32_bitwise"] = _bits_equal(local_before[unreachable_ids],local_after[unreachable_ids])
    checks["no_new_actual_degenerate"] = None if not(unique_before and unique_after) else False if new_actual_bad else None if unmapped_actual_bad else True
    unmatched_affected = [int(index) for index in np.flatnonzero(np.isin(actual_faces,active_ids).any(axis=1)) if actual_keys_after[index] not in prior_lookup]
    checks["no_actual_stable_key_reversal"] = False if actual_reversed and unique_before and unique_after else None if unmatched_affected or not(unique_before and unique_after) else True
    if check_intersections:
        contact = self_intersection_delta(before,after,faces,actual_faces,active_ids,before_polygon_ids,after_polygon_ids,deadline)
    else:
        contact = dict(status="not_run",no_new_extra_pairs=None,reason="explicit_caller_skip")
    checks["no_new_actual_extra_intersections"] = contact["no_new_extra_pairs"]
    scene_keys = ("other_objects_sha256","target_materials_sha256","scene_structure_sha256")
    scene = {key:bool(before_state[key]==after_state[key]) if before_state is not None and after_state is not None and key in before_state and key in after_state else None for key in scene_keys}
    # Scene manifests are separate evidence and remain explicitly unknown when absent.
    if spec.get("require_scene_preservation", False):
        checks.update(scene)
    # A change in tessellation remains visible even when polygon topology is intact.
    identity = dict(before_vertices=_digest(before),after_vertices=_digest(after),before_local=_digest(local_before),after_local=_digest(local_after),
                    before_faces=_digest(faces),after_faces=_digest(actual_faces),I=_digest(I),C=_digest(C),n0=_digest(normals))
    return dict(status=_status(checks),checks=checks,identity=identity,unit=spec.get("unit","unspecified"),
        points=dict(full=len(before),F=len(F),allowed=len(I),core=len(C),high=len(high),changed_local=int(changed_local.sum()),changed_outside_I=int(changed_local[outside].sum())),
        fixed=dict(h=h,ell=ell,center_source_id=int(center),tangent_tolerance=tangent_tolerance,world_preservation_tolerance=world_preservation_tol,
            world_preservation_tolerance_source="spec.world_preservation_tol frozen before consumers",
            preparation_world_tolerance_formula="max(tangent_abs_tol, 8 * eps(float32) * max(abs(initial_world_coordinates)))",
            world_comparison="maximum absolute component difference outside I in source world units"),
        displacement=dict(center_axial=float(axial[center]),center_over_h=float(axial[center]/h),core_axial=_distribution(axial[C]),
            core_median_over_h=float(np.median(axial[C])/h),full_norm=_distribution(lengths),I_norm=_distribution(lengths[I]),I_tangential=_distribution(tangential[I]),
            outside_max_world_abs=float(np.max(np.abs(delta[outside]))) if outside.any() else 0.),
        transition=dict(incident_edges=len(incident_edges),zero_or_tiny_original_edges=incident_edges[~usable_edges].tolist(),
            edge_displacement_gradient=_distribution(gradient),edge_length_relative_strain=_distribution(strain),high_components=high_components,
            core_high_fraction=float(np.mean(axial[C]>.5*h))),
        template_faces=template,actual_faces=dict(triangles=len(actual_faces),degenerate_face_ids=np.flatnonzero(current_bad).tolist(),
            definite_new_degenerate_face_ids=[int(value) for value in new_actual_bad],unmapped_degenerate_face_ids=[int(value) for value in unmapped_actual_bad],
            stable_key_reversed_face_ids=actual_reversed,
            unmapped_affected_face_ids=unmatched_affected,
            ordered_array_identical=bool(np.array_equal(faces,actual_faces)),stable_triangle_key_sets_identical=bool(unique_before and unique_after and set(actual_keys_before)==set(actual_keys_after)),
            before_unique_keys=unique_before,after_unique_keys=unique_after),
        scene_preservation=dict(status=_status(scene),checks=scene),self_intersection=contact,
        limits=["Full contract success also needs independent scene/material readback evidence and consumer result references", "No artistic preference label inferred from curvature or geometry success", "Actual retessellation can make new-contact attribution unknown"],
        wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu)
