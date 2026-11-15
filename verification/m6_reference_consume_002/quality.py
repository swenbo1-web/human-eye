"""Saved-geometry preservation and both fixed reference correspondences."""

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
    specification.loader.exec_module(module)
    return module


CORE = load_module("_consume002_exact_geometry", HERE.parent / "m6_refine_001/quality.py")
REFERENCE = load_module("_consume002_reference_sections", HERE.parent / "m6_reference_refine_001/reference_geometry.py")


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


def reference_inputs(spec):
    annotation_path = Path(spec["annotation_path"])
    observation_path = Path(spec["observation_path"])
    annotation = json.loads(annotation_path.read_bytes())
    observation = json.loads(observation_path.read_bytes())
    return annotation, observation


def current_sections(vertices, faces, spec):
    annotation, observation = reference_inputs(spec)
    projection = annotation["source_projection"]
    projected = np.asarray(vertices, dtype=np.float64) @ np.asarray(projection["affine_2_by_3"], dtype=float).T + np.asarray(projection["offset"], dtype=float)
    results = {}
    for label, key in (("primary", "primary_anchors"), ("alternative", "alternative_anchors")):
        anchors = observation[key]
        reference = REFERENCE.measure_polyline_sections(annotation["reference_foreground"]["inner_polyline"],
            annotation["reference_foreground"]["outer_polyline"], anchors["reference"]["E"], anchors["reference"]["W"], annotation["stations"])
        model = REFERENCE.measure_projected_sections(projected, faces, anchors["model"]["E"], anchors["model"]["W"], annotation["stations"])
        rows = []
        for original, current in zip(reference, model):
            first = {key:float(original[key]) for key in ("inner", "outer", "width")}
            second = {key:float(current[key]) for key in ("inner", "outer", "width")}
            first["centerline"] = .5*(first["outer"]+first["inner"])
            second["centerline"] = .5*(second["outer"]+second["inner"])
            rows.append(dict(t=float(original["t"]), reference=first, model=second,
                signed_residual={key:second[key]-first[key] for key in first},
                source_faces=dict(inner=int(current["inner_source_face"]), outer=int(current["outer_source_face"])),
                projected_components=current["projected_components"]))
        errors = {}
        for field in ("inner", "outer", "width", "centerline"):
            values = np.array([row["signed_residual"][field] for row in rows])
            errors[field] = dict(MAE=float(np.mean(np.abs(values))), maximum_absolute=float(np.max(np.abs(values))), signed_mean=float(np.mean(values)))
        reference_length = float(np.linalg.norm(np.asarray(anchors["reference"]["W"])-anchors["reference"]["E"]))
        results[label] = dict(anchors=anchors, stations=rows, errors=errors,
            reference_boundary_uncertainty_normalized=float(annotation["reference_foreground"]["boundary_uncertainty_pixels"])/reference_length,
            interpretation="Signed model-minus-reference distances normalized by this fixed correspondence's EW length. Positive outer points toward image right.")
    return dict(status="measured", definitions=results, projection=projection, station_fractions=annotation["stations"],
        coordinate_space="saved Blender world positions projected by the frozen initial camera", unit="EW_normalized",
        correspondence_truth="existing agent-marked hypotheses; user anatomical and artistic acceptance unmeasured")


def compare_contours(initial_vertices, initial_faces, current_vertices, current_faces, spec, changed_vertices):
    before = current_sections(initial_vertices, initial_faces, spec)
    after = current_sections(current_vertices, current_faces, spec)
    definitions = {}
    for name in before["definitions"]:
        first, second = before["definitions"][name], after["definitions"][name]
        improvements = {}
        for metric in ("inner", "outer", "width", "centerline"):
            initial = first["errors"][metric]
            current = second["errors"][metric]
            percent = 100*(initial["MAE"]-current["MAE"])/initial["MAE"] if initial["MAE"] else None
            improvements[metric] = dict(MAE_before=initial["MAE"], MAE_after=current["MAE"],
                MAE_decrease=initial["MAE"]-current["MAE"], MAE_decrease_percent=percent,
                maximum_before=initial["maximum_absolute"], maximum_after=current["maximum_absolute"],
                maximum_worsening=current["maximum_absolute"]-initial["maximum_absolute"])
        outer = improvements["outer"]
        established = bool(changed_vertices and outer["MAE_decrease"] > 1e-12)
        station_changes = [{"t":old["t"], **{field:new["model"][field]-old["model"][field] for field in ("inner", "outer", "width", "centerline")}}
            for old, new in zip(first["stations"], second["stations"])]
        definitions[name] = dict(before=first, after=second, improvements=improvements, station_model_changes=station_changes,
            improvement_established=established,
            suggested20percent_outer_MAE=bool(established and outer["MAE_decrease_percent"] >= 20 and outer["maximum_worsening"] <= second["reference_boundary_uncertainty_normalized"]))
    return dict(status="measured", definitions=definitions, changed_vertices=int(changed_vertices),
        geometry_improvement_established={name:row["improvement_established"] for name,row in definitions.items()},
        no_edit_result="geometric improvement not established" if not changed_vertices else None,
        technical_quality_scored_separately=True, artistic_acceptance=None)


def _same(first, second):
    return first is not None and second is not None and first.shape == second.shape and first.dtype == second.dtype and first.tobytes() == second.tobytes()


def geometry_quality(before, after, fixed, spec, before_scene=None, after_scene=None, *, deadline=None, check_intersections=True):
    started, cpu = time.perf_counter(), time.process_time()
    initial, current = before["vertices"], after["vertices"]
    native_before, native_after = before["vertices_local"], after["vertices_local"]
    faces, actual_faces = before["faces"], after["faces"]
    if initial.shape != current.shape or initial.ndim != 2 or initial.shape[1] != 3:
        raise ValueError("saved_full_source_coordinate_shape_mismatch")
    if not np.isfinite(initial).all() or not np.isfinite(current).all():
        raise ValueError("saved_coordinates_nonfinite")
    I = np.asarray(fixed["I_ids"], dtype=np.int64)
    F = np.asarray(fixed["F_source_ids"], dtype=np.int64)
    if len(np.unique(I)) != len(I) or not np.isin(I,F).all() or not len(I):
        raise ValueError("nonempty_unique_edit_domain_inside_F_required")
    outside = np.ones(len(initial), dtype=bool)
    outside[I] = False
    changed = np.any(native_before.view(np.uint32) != native_after.view(np.uint32), axis=1)
    changed_ids = np.flatnonzero(changed)
    active = np.union1d(I, changed_ids)
    delta = current-initial
    lengths = np.linalg.norm(delta, axis=1)
    diagonal = float(np.linalg.norm(np.ptp(initial, axis=0)))
    area_tolerance = 64*np.finfo(float).eps*diagonal**2
    template = CORE._face_changes(initial,current,faces,active,area_tolerance)
    before_keys, before_unique = CORE._triangle_keys(faces,before.get("triangle_polygon_ids"))
    after_keys, after_unique = CORE._triangle_keys(actual_faces,after.get("triangle_polygon_ids"))
    before_lookup = {key:index for index,key in enumerate(before_keys)}
    original_bad = {before_keys[index] for index in template["original_degenerate_face_ids"]}
    old_cross = np.cross(initial[faces[:,1]]-initial[faces[:,0]], initial[faces[:,2]]-initial[faces[:,0]])
    new_cross = np.cross(current[actual_faces[:,1]]-current[actual_faces[:,0]],current[actual_faces[:,2]]-current[actual_faces[:,0]])
    new_bad = np.flatnonzero(np.linalg.norm(new_cross,axis=1) <= area_tolerance)
    definite_bad = [int(index) for index in new_bad if after_keys[index] in before_lookup and after_keys[index] not in original_bad]
    unmapped_bad = [int(index) for index in new_bad if after_keys[index] not in before_lookup]
    reversed_actual, unmapped_affected = [], []
    for index in np.flatnonzero(np.isin(actual_faces,active).any(axis=1)):
        prior = before_lookup.get(after_keys[index])
        if prior is None:
            unmapped_affected.append(int(index))
        elif after_keys[index] not in original_bad and np.dot(old_cross[prior],new_cross[index]) <= 0:
            reversed_actual.append(int(index))
    edges = CORE._edges(faces)
    edges = edges[np.isin(edges,active).any(axis=1)]
    edge_lengths = np.linalg.norm(initial[edges[:,1]]-initial[edges[:,0]],axis=1)
    usable = edge_lengths > 64*np.finfo(float).eps*max(diagonal,1.)
    gradient = np.divide(np.linalg.norm(delta[edges[:,1]]-delta[edges[:,0]],axis=1),edge_lengths,
        out=np.full(len(edges),np.nan),where=usable)
    budget = float(spec.get("max_cumulative_displacement_m",spec.get("max_displacement",0.)))
    precision = float(spec["world_preservation_tol"])
    if budget <= 0 or precision < 0:
        raise ValueError("positive_displacement_budget_and_nonnegative_precision_required")
    checks = dict(outside_I_local_float32_bitwise=_same(native_before[outside],native_after[outside]),
        outside_I_world_save_precision=bool(np.max(np.abs(delta[outside])) <= precision) if outside.any() else True,
        source_vertex_ids=_same(before.get("source_ids"),after.get("source_ids")),
        native_polygon_offsets=_same(before.get("poly_offsets"),after.get("poly_offsets")),
        native_polygon_vertices=_same(before.get("poly_vertices"),after.get("poly_vertices")),
        target_matrix=_same(before.get("matrix_world"),after.get("matrix_world")),
        cumulative_displacement_budget=bool(lengths.max() <= budget+precision),
        no_new_template_degenerate=not template["new_degenerate_face_ids"], no_template_reversal=not template["reversed_face_ids"])
    checks["no_new_actual_degenerate"] = None if not(before_unique and after_unique) else False if definite_bad else None if unmapped_bad else True
    checks["no_actual_stable_key_reversal"] = False if reversed_actual else None if unmapped_affected or not(before_unique and after_unique) else True
    if "protected_ids" in fixed:
        protected = np.asarray(fixed["protected_ids"],dtype=np.int64)
        checks["explicit_protected_native_bitwise"] = _same(native_before[protected],native_after[protected])
    gates = spec.get("geometry_gates",spec.get("quality_gate",{}))
    if "max_gradient" in gates:
        checks["incident_edge_gradient"] = bool(np.nanmax(gradient) <= float(gates["max_gradient"])) if usable.all() else None
    if "max_normal_change_deg" in gates:
        maximum = template["affected_normal_angle_deg"]["maximum"]
        checks["affected_face_normal_change"] = bool(maximum <= float(gates["max_normal_change_deg"])) if maximum is not None and not template["unavailable_affected_normal_faces"] else None
    geometry_identical = _same(native_before,native_after) and _same(before.get("matrix_world"),after.get("matrix_world")) and _same(faces,actual_faces)
    if geometry_identical:
        contact = dict(status="pass",no_new_extra_pairs=True,reason="identical_saved_geometry_and_triangle_arrays",affected_changed_faces=0,
            scoped_allowed_points=len(I), exact_pair_scan_executed=False)
    elif check_intersections:
        contact = CORE.self_intersection_delta(initial,current,faces,actual_faces,active,before.get("triangle_polygon_ids"),after.get("triangle_polygon_ids"),deadline)
        contact["exact_pair_scan_executed"] = True
    else:
        contact = dict(status="unknown",no_new_extra_pairs=None,reason="explicit_local_test_skip",exact_pair_scan_executed=False)
    checks["no_new_extra_intersections"] = contact["no_new_extra_pairs"]
    scene_keys = ("other_objects_sha256","target_materials_sha256","scene_structure_sha256")
    scenes = {key: bool(before_scene[key] == after_scene[key]) if before_scene is not None and after_scene is not None and key in before_scene and key in after_scene else None for key in scene_keys}
    if spec.get("require_scene_preservation",True):
        checks.update(scenes)
    actual_record=dict(triangles=len(actual_faces),definite_new_degenerate=definite_bad,
        unmapped_degenerate=unmapped_bad,stable_key_reversed=reversed_actual,unmapped_affected=unmapped_affected,
        ordered_array_identical=_same(faces,actual_faces),stable_key_sets_identical=bool(before_unique and after_unique and set(before_keys)==set(after_keys)))
    contact_summary={key:contact[key] for key in ("status","no_new_extra_pairs","reason","exact_pair_scan_executed") if key in contact}
    contact_summary.update(new_pair_count=len(contact.get("new_pairs",[])),
        changed_relation_count=len(contact.get("changed_relations",[])),full_record="raw_geometry.self_intersection")
    return dict(status=status(checks),checks=checks,
        displacement=dict(maximum_world=float(lengths.max()),maximum_allowed_world=budget,save_precision_allowance=precision,
            changed_vertices=len(changed_ids),changed_outside_I=int(changed[outside].sum()),world_X_maximum_change=float(np.max(np.abs(delta[:,0]))),
            F_depth_X_extent_before=float(np.ptp(initial[F,0])),F_depth_X_extent_after=float(np.ptp(current[F,0]))),
        geometry=dict(source_points=len(initial),observation_points=len(F),allowed_points=len(I),
            template_faces=dict(triangles=len(faces),affected_triangles=template["affected_triangles"],
                original_degenerate_count=len(template["original_degenerate_face_ids"]),new_degenerate_count=len(template["new_degenerate_face_ids"]),
                reversed_count=len(template["reversed_face_ids"]),affected_normal_angle_deg=template["affected_normal_angle_deg"]),
            actual_faces=dict(triangles=len(actual_faces),definite_new_degenerate_count=len(definite_bad),unmapped_degenerate_count=len(unmapped_bad),
                stable_key_reversed_count=len(reversed_actual),unmapped_affected_count=len(unmapped_affected),
                ordered_array_identical=actual_record["ordered_array_identical"],stable_key_sets_identical=actual_record["stable_key_sets_identical"]),
            incident_edge_gradient=CORE._distribution(gradient),zero_or_tiny_incident_edges=int((~usable).sum()),
            scene_preservation=dict(status=status(scenes),checks=scenes),self_intersection=contact_summary),
        raw_geometry=dict(template_faces=template,actual_faces=actual_record,self_intersection=contact),
        identity=dict(initial_world=digest(initial),actual_world=digest(current),initial_local=digest(native_before),actual_local=digest(native_after),I=digest(I),F=digest(F)),
        wall_s=time.perf_counter()-started,cpu_s=time.process_time()-cpu)
