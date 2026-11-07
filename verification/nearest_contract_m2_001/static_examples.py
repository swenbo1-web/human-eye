"""Four mathematical input examples, NOT Blender behavior or product tests."""
import json
import math
from pathlib import Path


def in_box(point, box):
    return all(math.isfinite(value) and lo <= value <= hi
               for value, (lo, hi) in zip(point, box))


def directory_projection(vertices, faces, box):
    first = faces[0]
    valid = len(first) == 3 and all(type(index) is int and 0 <= index < len(vertices) for index in first)
    witness = [vertices[index] for index in first] if valid else []
    finite = valid and all(all(math.isfinite(x) for x in point) for point in witness)
    if finite:
        a, b, c = witness
        ab, ac = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        nondegenerate = any(ab[i] * ac[(i + 1) % 3] - ab[(i + 1) % 3] * ac[i] for i in range(3))
    else:
        nondegenerate = False
    return {"vertex_count": len(vertices), "face_count": len(faces),
            "loop_count": sum(map(len, faces)),
            "three_loops_per_face_total": sum(map(len, faces)) == 3 * len(faces),
            "finite_box": all(math.isfinite(x) for pair in box for x in pair),
            "first_triangle_finite_nondegenerate_inside": bool(finite and nondegenerate and all(in_box(p, box) for p in witness))}


def run():
    base = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (.2, .2, 0), (.4, .2, 0), (.2, .4, 0)]
    faces = [(0, 1, 2), (3, 4, 5)]
    box = [(0, 1), (0, 1), (0, 0)]
    results = []

    # 1. Hypothetical finite bounds plus a later nonfinite referenced coordinate.
    vertices = list(base)
    vertices[3] = (math.nan, .2, 0)
    projection = directory_projection(vertices, faces, box)
    assert projection["first_triangle_finite_nondegenerate_inside"]
    assert not all(math.isfinite(v) for face in faces for i in face for v in vertices[i])
    results.append({"id": "later_nonfinite_reference", "directory_facts": projection,
                    "conclusion": "finite first-face and box facts do not imply a finite entire triangle surface",
                    "actual_blender_nan_bound_behavior": "not_tested"})

    # 2. A same-count modification outside an old box; not a claim of a bpy cache bug.
    old_projection = directory_projection(base, faces, box)
    vertices = list(base)
    vertices[3] = (10, .2, 0)
    new_projection = directory_projection(vertices, faces, box)
    assert old_projection == new_projection
    assert not in_box(vertices[3], box)
    results.append({"id": "same_counts_hypothetical_stale_box", "directory_facts": new_projection,
                    "frozen_directory_facts_equal": True, "surface_vertex_outside_old_box": True,
                    "conclusion": "counts and first witness cannot independently detect all changed content",
                    "actual_blender_cache_staleness": "not_demonstrated"})

    # 3. A degenerate face is bounded; an isolated finite point only loosens the box.
    vertices = list(base) + [(100, 100, 100)]
    degenerate_faces = [(0, 1, 2), (3, 3, 3)]
    broad_box = [(0, 100), (0, 100), (0, 100)]
    used = {i for face in degenerate_faces for i in face}
    assert all(in_box(vertices[i], broad_box) for i in used)
    assert 6 not in used and in_box(vertices[6], broad_box)
    assert all(vertices[i] == vertices[3] for i in degenerate_faces[1])
    results.append({"id": "bounded_degenerate_face_and_isolated_finite_vertex",
                    "all_triangle_vertices_enclosed": True, "second_face_degenerate": True,
                    "isolated_vertex_is_not_surface_witness": True,
                    "conclusion": "metric rejection of degeneration does not imply enclosure failure; isolated finite vertices may loosen bounds"})

    # 4. Later out-of-range indices cannot be validated through total counts.
    invalid_faces = [(0, 1, 2), (3, 4, 99)]
    projection = directory_projection(base, invalid_faces, box)
    assert projection["three_loops_per_face_total"] and projection["first_triangle_finite_nondegenerate_inside"]
    assert any(not 0 <= i < len(base) for face in invalid_faces for i in face)
    results.append({"id": "later_invalid_index", "directory_facts": projection,
                    "conclusion": "counts and a valid first triangle do not define the whole surface without the topology validity premise",
                    "actual_bpy_acceptance_of_invalid_mesh": "not_tested"})

    assert len(results) == 4
    return {"scope": "stdlib logical examples only; no product import or Blender execution",
            "example_count": len(results), "examples": results, "all_assertions_passed": True}


if __name__ == "__main__":
    result = run()
    target = Path(__file__).resolve().parent / "STATIC_RESULTS.json"
    target.write_bytes((json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    print(json.dumps({key: value for key, value in result.items() if key != "examples"}))
