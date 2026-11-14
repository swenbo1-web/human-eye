"""Offline finite shape and endpoint-surface evaluation on saved world arrays."""
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("m6_fixed_surface_geometry", ROOT / "human_eye_plugin/surface_geometry.py")
surface = importlib.util.module_from_spec(spec)
spec.loader.exec_module(surface)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Stopped(RuntimeError):
    pass


class Work:
    def __init__(self, deadline=None):
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.deadline = min(self.started + 180, deadline) if deadline is not None else self.started + 180
        self.counts = Counter()
        self.used = 0

    def consume(self, amount, stage):
        self.used += amount
        self.counts[stage] += amount
        if self.used > 20000000:
            raise Stopped("offline_work_limit")
        if time.perf_counter() > self.deadline:
            raise Stopped("offline_phase_deadline")

    def summary(self):
        return {"units": self.used, "counts": dict(self.counts),
                "wall_s": time.perf_counter() - self.started, "cpu_s": time.process_time() - self.cpu_started}


def coordinates(value, count=None):
    if not isinstance(value, list) or count is not None and len(value) != count:
        raise ValueError("coordinate_count")
    if any(not isinstance(row, (list, tuple)) or len(row) != 3 or
           any(type(x) not in (float, int) or not math.isfinite(x) for x in row) for row in value):
        raise ValueError("nonfinite_or_malformed_coordinate")
    return [tuple(float(x) for x in row) for row in value]


def validate(packet):
    before = coordinates(packet["vertices_before"])
    after = coordinates(packet["vertices_candidate"], len(before))
    ids = packet.get("vertex_ids", list(range(len(before))))
    candidate_ids = packet.get("candidate_vertex_ids", ids)
    if ids != list(range(len(before))) or candidate_ids != ids or any(type(i) is not int for i in ids + candidate_ids):
        raise ValueError("source_id_mismatch")
    if not isinstance(packet["state"], dict) or not isinstance(packet["state"].get("source_id"), str) or not packet["state"]["source_id"] or type(packet["state"].get("frame")) is not int:
        raise ValueError("source_state_fields")
    if packet.get("candidate_state", packet["state"]) != packet["state"]:
        raise ValueError("source_state_mismatch")
    if packet["state"].get("coordinate_frame") != "saved_world_binary64_m":
        raise ValueError("coordinate_semantics")
    triangles = packet["triangles"]
    if not isinstance(triangles, list) or not triangles or any(
        not isinstance(row, list) or len(row) != 3 or len(set(row)) != 3 or
        any(type(i) is not int or i < 0 or i >= len(before) for i in row) for row in triangles):
        raise ValueError("source_triangle_ids")
    writes = packet["write_ids"]
    if not isinstance(writes, list) or len(set(writes)) != len(writes) or any(type(i) is not int or not 0 <= i < len(before) for i in writes):
        raise ValueError("write_ids")
    write_set = set(writes)
    if any(a != b for i, (a, b) in enumerate(zip(before, after)) if i not in write_set):
        raise ValueError("changed_outside_declared_writes")
    affected = [i for i, triangle in enumerate(triangles) if write_set.intersection(triangle)]
    scope = packet.get("scope_face_ids", affected)
    if len(set(scope)) != len(scope) or any(type(i) is not int or not 0 <= i < len(triangles) for i in scope):
        raise ValueError("scope_face_ids")
    return before, after, triangles, writes, affected, sorted(scope)


def common_factor(before, after):
    exponent = max(float(value).as_integer_ratio()[1].bit_length() - 1 for point in before + after for value in point)
    return 1 << exponent


def integer_point(point, factor):
    result = []
    for value in point:
        numerator, denominator = float(value).as_integer_ratio()
        if factor % denominator:
            raise ValueError("shared_integer_frame_mismatch")
        integer = numerator * (factor // denominator)
        if abs(integer).bit_length() > surface.LIMITS["bits"]:
            raise ValueError("coordinate_bit_budget")
        result.append(integer)
    return tuple(result)


def face_geometry(points, face):
    triangle = tuple(points[index] for index in face)
    normal = surface.normal(triangle)
    box = (tuple(min(point[axis] for point in triangle) for axis in range(3)),
           tuple(max(point[axis] for point in triangle) for axis in range(3)))
    return triangle, normal, box


class Prepared:
    def __init__(self, values, triangles, affected, factor, state, deadline=None):
        work = Work(deadline)
        self.factor = factor
        self.state = json.loads(json.dumps(state, allow_nan=False))
        work.consume(3 * (len(values) + len(triangles)), "offline_source_fingerprint_scalars")
        self.source = digest({"state": state, "vertices": values, "triangles": triangles})
        self.faces = triangles
        self.affected = list(affected)
        active = set(affected)
        self.unaffected = [i for i in range(len(triangles)) if i not in active]
        self.vertices = []
        for point in values:
            work.consume(3, "offline_coordinate_conversion")
            self.vertices.append(integer_point(point, factor))
        self.points, self.normals, self.bounds = [], [], []
        for face in triangles:
            work.consume(1, "offline_face_geometry")
            points, normal, box = face_geometry(self.vertices, face)
            self.points.append(points)
            self.normals.append(normal)
            self.bounds.append(box)
        self.active_tree = surface._bvh(self.bounds, work, list(self.affected)) if self.affected else None
        self.static_tree = surface._bvh(self.bounds, work, list(self.unaffected)) if self.unaffected else None
        self.preparation = work.summary() | {"converted_vertices": len(values), "updated_faces": len(triangles),
                                           "built_trees": int(bool(self.affected)) + int(bool(self.unaffected)),
                                           "reused_static_faces": 0, "copied_reference_slots": 0}

    def updated(self, values, writes, deadline=None):
        work = Work(deadline)
        result = object.__new__(Prepared)
        result.factor, result.state, result.faces = self.factor, self.state, self.faces
        work.consume(3 * (len(values) + len(self.faces)), "offline_source_fingerprint_scalars")
        result.source = digest({"state": self.state, "vertices": values, "triangles": self.faces})
        result.affected, result.unaffected = self.affected, self.unaffected
        result.vertices = self.vertices.copy()
        result.points, result.normals, result.bounds = self.points.copy(), self.normals.copy(), self.bounds.copy()
        work.consume(len(self.vertices) + 3 * len(self.faces), "offline_reference_copy")
        for index in writes:
            work.consume(3, "offline_coordinate_conversion")
            result.vertices[index] = integer_point(values[index], self.factor)
        for index in self.affected:
            work.consume(1, "offline_face_geometry")
            result.points[index], result.normals[index], result.bounds[index] = face_geometry(result.vertices, self.faces[index])
        result.active_tree = surface._bvh(result.bounds, work, list(self.affected)) if self.affected else None
        result.static_tree = self.static_tree
        result.preparation = work.summary() | {"converted_vertices": len(writes), "updated_faces": len(self.affected),
                                               "built_trees": int(bool(self.affected)), "reused_static_faces": len(self.unaffected),
                                               "copied_reference_slots": len(self.vertices) + 3 * len(self.faces)}
        return result

    def binding(self):
        return {"geometry_sha256": self.source, "integer_factor": self.factor,
                "face_scope_sha256": digest(self.affected)}


def scan(prepared, deadline=None):
    work = Work(deadline)
    count = len(prepared.faces)
    active_count = len(prepared.affected)
    denominator = active_count * (count - active_count) + active_count * (active_count - 1) // 2
    statistics = {"node_pair_visits": 0, "leaf_pair_visits": 0, "aabb_pruned_pairs": 0}
    pairs = []
    candidate_complete = True
    reason = None
    try:
        if prepared.active_tree and prepared.static_tree:
            pairs.extend(tuple(sorted(pair)) for pair in surface.candidate_pairs(
                prepared.bounds, 0, work, statistics, other_bounds=prepared.bounds,
                roots=(prepared.active_tree, prepared.static_tree)))
        if prepared.active_tree:
            pairs.extend(surface.candidate_pairs(prepared.bounds, 0, work, statistics,
                                                roots=(prepared.active_tree, prepared.active_tree)))
    except Stopped as exc:
        candidate_complete, reason = False, str(exc)
    if len(set(pairs)) != len(pairs):
        raise AssertionError("duplicate_spatial_pair")
    pairs.sort()
    if candidate_complete and len(pairs) + statistics["aabb_pruned_pairs"] != denominator:
        raise AssertionError("pair_domain_accounting")
    intersections, legal, known_empty, unresolved = {}, 0, 0, []
    tested = 0
    for ordinal, (left, right) in enumerate(pairs):
        try:
            if tested >= 250000:
                raise Stopped("offline_exact_pair_limit")
            work.consume(1, "offline_exact_pair")
            tested += 1
            if not any(prepared.normals[left]) or not any(prepared.normals[right]):
                unresolved.append([left, right])
                continue
            witness = surface.intersection(prepared.points[left], prepared.points[right], work)
            if not witness:
                known_empty += 1
                continue
            shared = sorted(set(prepared.faces[left]) & set(prepared.faces[right]))
            if surface.legal_simplex(witness, shared, prepared.vertices):
                legal += 1
            else:
                intersections[(left, right)] = {"dimension": surface.dimension(witness),
                                               "relation": surface.relation(witness, prepared.points[left], prepared.points[right]),
                                               "shared_source_vertices": shared}
        except Stopped as exc:
            unresolved.extend([list(pair) for pair in pairs[ordinal:]])
            reason = str(exc)
            break
    degenerates = [i for i, normal in enumerate(prepared.normals) if not any(normal)]
    good_active = sum(i not in degenerates for i in prepared.affected)
    good_unaffected = sum(i not in degenerates for i in prepared.unaffected)
    qualified_domain = good_active * good_unaffected + good_active * (good_active - 1) // 2
    if unresolved and reason is None:
        reason = "degenerate_candidate_pairs_unresolved"
    complete = candidate_complete and not unresolved
    return {"prepared_binding": prepared.binding(), "intersections": intersections, "candidates": pairs, "unresolved": unresolved,
            "scan_complete": complete, "candidate_complete": candidate_complete,
            "degenerate_face_ids": degenerates, "reason": reason,
            "pairs_involving_degenerate_faces": denominator - qualified_domain,
            "pair_domain": denominator, "aabb_pruned": statistics["aabb_pruned_pairs"],
            "spatial_candidates": len(pairs), "exact_tests": tested, "legal_simplex_pairs": legal,
            "empty_pairs": known_empty, "unknown_pairs": len(unresolved),
            "unstarted_exact_pairs": len(pairs) - tested,
            "unaccounted_domain_pairs": denominator - statistics["aabb_pruned_pairs"] - len(pairs),
            "spatial_work": statistics, "work": work.summary()}


def goals(packet, before, after):
    target = packet.get("target_vertices")
    shape = {"status": "missing", "ok": None, "reason": "target_missing"}
    if target is not None:
        try:
            if not isinstance(target, dict) or not target:
                raise ValueError("target_mapping")
            errors = []
            for key, point in target.items():
                index = int(key)
                if str(index) != str(key) or not 0 <= index < len(after):
                    raise ValueError("target_source_id")
                goal = coordinates([point])[0]
                errors.append(math.dist(after[index], goal))
            if not all(math.isfinite(error) for error in errors):
                raise ValueError("shape_metric_overflow")
            tolerance = packet.get("shape_tolerance_m", 0.)
            if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or tolerance < 0:
                raise ValueError("shape_tolerance")
            shape = {"status": "evaluated", "ok": max(errors) <= tolerance, "max_error_m": max(errors),
                     "rms_error_m": math.hypot(*errors) / math.sqrt(len(errors)), "tolerance_m": tolerance}
        except (ValueError, TypeError, IndexError, OverflowError) as exc:
            shape = {"status": "error", "ok": None, "reason": str(exc)}
    try:
        protected = packet.get("protected_ids", [])
        if any(type(i) is not int or not 0 <= i < len(before) for i in protected):
            raise ValueError("protected_source_id")
        tolerance = packet.get("preservation_tolerance_m", 0.)
        if type(tolerance) not in (float, int) or not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("preservation_tolerance")
        error = max((math.dist(before[i], after[i]) for i in protected), default=0.)
        if not math.isfinite(error):
            raise ValueError("preservation_metric_overflow")
        preservation = {"status": "evaluated", "ok": error <= tolerance, "max_error_m": error, "tolerance_m": tolerance}
    except (ValueError, TypeError, OverflowError) as exc:
        preservation = {"status": "error", "ok": None, "reason": str(exc)}
    return shape, preservation


def combine(packet, before_scan, after_scan, scope_complete, shape, preservation):
    before_pairs = set(before_scan["intersections"])
    after_pairs = set(after_scan["intersections"])
    unresolved_before = {tuple(pair) for pair in before_scan["unresolved"]}
    unresolved_after = {tuple(pair) for pair in after_scan["unresolved"]}
    new = sorted(after_pairs - before_pairs - unresolved_before) if before_scan["candidate_complete"] else []
    removed = sorted(before_pairs - after_pairs - unresolved_after) if after_scan["candidate_complete"] else []
    changed = [{"pair": list(pair), "before": before_scan["intersections"][pair], "after": after_scan["intersections"][pair]}
               for pair in sorted(before_pairs & after_pairs)
               if before_scan["intersections"][pair] != after_scan["intersections"][pair]]
    complete = scope_complete and before_scan["scan_complete"] and after_scan["scan_complete"]
    if packet.get("forbid_all_intersections", False):
        contact_ok = False if after_pairs else True if complete else None
        requirement = "no_after_extra_intersections"
    else:
        contact_ok = False if new and packet.get("require_no_new_intersections", True) else True if complete else None
        requirement = "no_new_extra_intersection_pairs"
    conditions = [shape["ok"], preservation["ok"], contact_ok]
    joint = "fail" if False in conditions else "pass" if all(value is True for value in conditions) else "unknown"
    return {"before_pairs": [list(pair) for pair in sorted(before_pairs)], "after_pairs": [list(pair) for pair in sorted(after_pairs)],
            "new_pairs": [list(pair) for pair in new], "removed_pairs": [list(pair) for pair in removed],
            "changed_relations": changed, "contact_ok": contact_ok, "contact_requirement": requirement,
            "shape_ok": shape["ok"], "preservation_ok": preservation["ok"], "joint_status": joint,
            "shape": shape, "preservation": preservation, "contact_complete": complete}


def invalid_result(reason):
    return {"joint_status": "invalid", "reason": reason, "shape_ok": None, "contact_ok": None,
            "preservation_ok": None, "before_pairs": [], "after_pairs": [], "new_pairs": []}, None, None


def evaluate(packet, *, shared=False, prepared_before=None, scan_before=None, deadline=None):
    started, cpu_started = time.perf_counter(), time.process_time()
    try:
        before, after, triangles, writes, affected, scope = validate(packet)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return invalid_result(str(exc))
    factor = common_factor(before, after)
    if prepared_before is None:
        prepared_before = Prepared(before, triangles, scope, factor, packet["state"], deadline)
    elif prepared_before.factor != factor or prepared_before.affected != scope or prepared_before.source != digest(
            {"state": packet["state"], "vertices": before, "triangles": triangles}):
        return invalid_result("prepared_source_or_frame_mismatch")
    if scan_before is not None and scan_before.get("prepared_binding") != prepared_before.binding():
        return invalid_result("cached_scan_source_frame_or_scope_mismatch")
    before_scan = scan_before if scan_before is not None else scan(prepared_before, deadline)
    candidate = prepared_before.updated(after, writes, deadline) if shared else Prepared(after, triangles, scope, factor, packet["state"], deadline)
    after_scan = scan(candidate, deadline)
    shape, preservation = goals(packet, before, after)
    result = combine(packet, before_scan, after_scan, scope == affected, shape, preservation)
    result.update(affected_face_ids=affected, evaluated_face_ids=scope, scope_complete=scope == affected,
                  candidate_preparation=candidate.preparation, before_preparation=prepared_before.preparation,
                  before_scan=before_scan, after_scan=after_scan, shared_static_preparation=shared,
                  integer_factor_exponent=factor.bit_length() - 1,
                  total_evaluation_wall_s=time.perf_counter() - started, total_evaluation_cpu_s=time.process_time() - cpu_started)
    return result, prepared_before, before_scan


def serializable_scan(value):
    return {key: ([{"pair": list(pair), **row} for pair, row in sorted(item.items())] if key == "intersections" else item)
            for key, item in value.items()}


def serializable_result(result):
    return {key: serializable_scan(value) if key in ("before_scan", "after_scan") else value for key, value in result.items()}
