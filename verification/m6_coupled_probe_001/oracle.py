"""Independent exact control oracle using barycentric feasible-set vertices.

This file imports neither the product geometry nor the tested evaluator.  For
two triangles it solves five rational equality constraints in six nonnegative
barycentric variables.  Enumeration uses the matrix's actual rank, including
rank-four coplanar cases.  Feasible basic solutions give the intersection's
vertices.  Run only after CASE_PLAN.json has been frozen.

`oracle_case(case)` returns complete incident-scope geometric facts plus the
limited task status. `verify_plan(plan)` verifies the predeclared expectations.
"""
from fractions import Fraction
from itertools import combinations
import json
import math
from pathlib import Path
import sys


def _rank(matrix):
    work = [list(row) for row in matrix]
    pivot_row = 0
    for column in range(len(work[0])):
        pivot = next((row for row in range(pivot_row, len(work)) if work[row][column]), None)
        if pivot is None:
            continue
        work[pivot_row], work[pivot] = work[pivot], work[pivot_row]
        divisor = work[pivot_row][column]
        work[pivot_row] = [value / divisor for value in work[pivot_row]]
        for row in range(pivot_row + 1, len(work)):
            multiplier = work[row][column]
            work[row] = [value - multiplier * reference
                         for value, reference in zip(work[row], work[pivot_row])]
        pivot_row += 1
        if pivot_row == len(work):
            break
    return pivot_row


def _unique_solution(matrix, right):
    columns = len(matrix[0])
    work = [list(row) + [value] for row, value in zip(matrix, right)]
    pivots = []
    for column in range(columns):
        pivot = next((row for row in range(len(pivots), len(work)) if work[row][column]), None)
        if pivot is None:
            continue
        row_index = len(pivots)
        work[row_index], work[pivot] = work[pivot], work[row_index]
        divisor = work[row_index][column]
        work[row_index] = [value / divisor for value in work[row_index]]
        for row in range(len(work)):
            if row == row_index:
                continue
            multiplier = work[row][column]
            work[row] = [value - multiplier * reference
                         for value, reference in zip(work[row], work[row_index])]
        pivots.append(column)
    if len(pivots) != columns or any(not any(row[:columns]) and row[-1] for row in work):
        return None
    solution = [Fraction(0)] * columns
    for row_index, column in enumerate(pivots):
        solution[column] = work[row_index][-1]
    return solution


def _point(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 3 or
            any(type(number) not in (int, float) or not math.isfinite(number) for number in value)):
        raise ValueError("invalid_coordinate")
    return tuple(Fraction(number) for number in value)


def _nondegenerate(triangle):
    differences = [[point[axis] - triangle[0][axis] for axis in range(3)] for point in triangle[1:]]
    return _rank(differences) == 2


def triangle_intersection(first, second):
    """Return exact intersection vertices; reject a degenerate input face."""
    if not _nondegenerate(first) or not _nondegenerate(second):
        raise ValueError("degenerate_triangle")
    matrix = [[Fraction(1)] * 3 + [Fraction(0)] * 3,
              [Fraction(0)] * 3 + [Fraction(1)] * 3]
    matrix.extend([[first[index][axis] for index in range(3)] +
                   [-second[index][axis] for index in range(3)] for axis in range(3)])
    right = [Fraction(1), Fraction(1), Fraction(0), Fraction(0), Fraction(0)]
    rank = _rank(matrix)
    points = set()
    for basis in combinations(range(6), rank):
        solution = _unique_solution([[row[column] for column in basis] for row in matrix], right)
        if solution is None or any(value < 0 for value in solution):
            continue
        coefficients = [Fraction(0)] * 6
        for column, value in zip(basis, solution):
            coefficients[column] = value
        point = tuple(sum(coefficients[index] * first[index][axis] for index in range(3))
                      for axis in range(3))
        points.add(point)
    return sorted(points)


def _within_shared_simplex(points, shared, vertices):
    if len(shared) == 1:
        return all(point == vertices[shared[0]] for point in points)
    if len(shared) == 2:
        first, second = (vertices[index] for index in shared)
        axis = next((index for index in range(3) if first[index] != second[index]), None)
        if axis is None:
            return False
        for point in points:
            parameter = (point[axis] - first[axis]) / (second[axis] - first[axis])
            if not 0 <= parameter <= 1:
                return False
            if any(point[index] != first[index] + parameter * (second[index] - first[index])
                   for index in range(3)):
                return False
        return True
    return False


def _surface_facts(vertices, triangles, affected):
    found = []
    details = []
    degenerate = [index for index, triangle in enumerate(triangles)
                  if not _nondegenerate([vertices[i] for i in triangle])]
    unknown_pairs = []
    for left, right in combinations(range(len(triangles)), 2):
        if left not in affected and right not in affected:
            continue
        if left in degenerate or right in degenerate:
            unknown_pairs.append([left, right])
            continue
        first = [vertices[index] for index in triangles[left]]
        second = [vertices[index] for index in triangles[right]]
        points = triangle_intersection(first, second)
        if not points:
            continue
        shared = sorted(set(triangles[left]) & set(triangles[right]))
        legal = _within_shared_simplex(points, shared, vertices)
        if not legal:
            found.append([left, right])
        dimension = _rank([[point[axis] - points[0][axis] for axis in range(3)]
                           for point in points[1:]]) if len(points) > 1 else 0
        details.append({"pair": [left, right], "extra_intersection": not legal,
                        "dimension": ("point", "line", "area")[dimension],
                        "vertices_rational": [[str(coordinate) for coordinate in point] for point in points]})
    return {"pairs": found, "details": details, "degenerate_faces": degenerate,
            "unknown_pairs": unknown_pairs}


def oracle_case(case):
    """Evaluate the fixture's complete geometric reference and task booleans."""
    raw_before = case["vertices_before"]
    raw_after = case["vertices_candidate"]
    vertex_ids = case.get("vertex_ids", list(range(len(raw_before))))
    candidate_ids = case.get("candidate_vertex_ids", vertex_ids)
    result = {"name": case["name"], "joint_status": "invalid"}
    if case.get("candidate_state", case["state"]) != case["state"]:
        return result | {"input_error": "state_mismatch"}
    if candidate_ids != vertex_ids or vertex_ids != list(range(len(raw_before))):
        return result | {"input_error": "source_id_mismatch"}
    try:
        before = [_point(point) for point in raw_before]
        after = [_point(point) for point in raw_after]
    except ValueError:
        return result | {"input_error": "nonfinite_or_invalid_coordinate"}
    if len(before) != len(after):
        return result | {"input_error": "vertex_count_mismatch"}
    triangles = case["triangles"]
    writes = set(case["write_ids"])
    affected = {index for index, triangle in enumerate(triangles) if writes.intersection(triangle)}
    scope = set(case.get("scope_face_ids", affected))
    scope_complete = affected.issubset(scope)
    old = _surface_facts(before, triangles, affected)
    new = _surface_facts(after, triangles, affected)
    new_pairs = sorted([list(pair) for pair in set(map(tuple, new["pairs"])) - set(map(tuple, old["pairs"]))])
    geometry_unknown = bool(old["unknown_pairs"] or new["unknown_pairs"] or
                            affected.intersection(old["degenerate_faces"]) or
                            affected.intersection(new["degenerate_faces"]))
    violation = (case.get("require_no_new_intersections", True) and bool(new_pairs) or
                 case.get("forbid_all_intersections", False) and bool(new["pairs"]))
    contact_ok = None
    if scope_complete:
        contact_ok = False if violation else None if geometry_unknown else True
    target = case["target_vertices"]
    shape_ok = None
    shape_error = None
    max_error_squared = None
    if target is not None:
        try:
            errors = [sum((after[int(index)][axis] - coordinate)**2
                          for axis, coordinate in enumerate(_point(point)))
                      for index, point in target.items()]
            if not errors:
                raise ValueError("empty_target")
            max_error_squared = max(errors)
            shape_ok = max_error_squared <= Fraction(case["shape_tolerance_m"])**2
        except (ValueError, TypeError, IndexError, AttributeError):
            shape_error = "invalid_shape_target"
    protected = set(case["protected_ids"]) | (set(range(len(before))) - writes)
    keep_errors = [sum((before[index][axis] - after[index][axis])**2 for axis in range(3))
                   for index in protected]
    preservation_ok = max(keep_errors, default=Fraction(0)) <= Fraction(case["preservation_tolerance_m"])**2
    items = [shape_ok, preservation_ok, contact_ok]
    status = "fail" if False in items else "unknown" if None in items else "pass"
    return {"name": case["name"], "joint_status": status,
            "before_pairs": old["pairs"], "after_pairs": new["pairs"], "new_pairs": new_pairs,
            "affected_face_ids": sorted(affected), "scope_complete": scope_complete,
            "shape_ok": shape_ok, "shape_error": shape_error,
            "shape_max_error_squared_rational": str(max_error_squared) if max_error_squared is not None else None,
            "preservation_ok": preservation_ok, "contact_ok": contact_ok,
            "before_geometry": old, "after_geometry": new}


def verify_plan(plan):
    results = []
    for case in plan["cases"]:
        result = oracle_case(case)
        for key, expected in case["expected"].items():
            if key in ("reason", "analytic_derivation"):
                continue
            if result.get(key) != expected:
                raise AssertionError({"case": case["name"], "field": key,
                                      "expected": expected, "actual": result.get(key)})
        results.append(result)
    return {"status": "passed", "cases": len(results), "method": "independent_exact_barycentric_basic_solutions",
            "results": results}


if __name__ == "__main__":
    plan = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("CASE_PLAN.json")).read_bytes())
    print(json.dumps(verify_plan(plan), indent=2, allow_nan=False))
