"""Independent Fraction axis-separation proofs, with no intersection solver."""
from collections import Counter
from fractions import Fraction


def box(points):
    return tuple(min(point[axis] for point in points) for axis in range(3)), tuple(max(point[axis] for point in points) for axis in range(3))


def separation(first, second):
    for axis in range(3):
        if first[1][axis] < second[0][axis]:
            return axis, second[0][axis] - first[1][axis]
        if second[1][axis] < first[0][axis]:
            return axis, first[0][axis] - second[1][axis]
    return None


def degenerate(points):
    a = [points[1][axis] - points[0][axis] for axis in range(3)]
    b = [points[2][axis] - points[0][axis] for axis in range(3)]
    return all(a[(axis + 1) % 3] * b[(axis + 2) % 3] == a[(axis + 2) % 3] * b[(axis + 1) % 3] for axis in range(3))


def case_reference(case):
    proofs = {}
    for stage, field in (("before", "vertices_before"), ("after", "vertices_candidate")):
        values = [tuple(Fraction(value) for value in point) for point in case[field]]
        triangles = [[values[index] for index in face] for face in case["triangles"]]
        assert not degenerate(triangles[0]) and degenerate(triangles[1])
        witness = separation(box(triangles[0]), box(triangles[1]))
        proofs[stage] = {"axis": witness[0] if witness else None, "strict_gap_rational_m": str(witness[1]) if witness else None,
                         "candidates": 0 if witness else 1, "query_complete": witness is not None,
                         "degenerate_face_ids": [1]}
    assert all(tuple(Fraction(value) for value in case["vertices_candidate"][int(index)]) == tuple(Fraction(value) for value in target)
               for index, target in case["target_vertices"].items())
    assert all(case["vertices_before"][index] == case["vertices_candidate"][index] for index in case["protected_ids"])
    return {"proofs": proofs, "new_contact_ok": True if all(row["query_complete"] for row in proofs.values()) else None,
            "new_joint_status": "pass" if all(row["query_complete"] for row in proofs.values()) else "unknown"}


def real_witnesses(vertices, faces, affected, degenerate_ids):
    assert not set(affected).intersection(degenerate_ids)
    needed = {index for face_id in affected + degenerate_ids for index in faces[face_id]}
    values = {index: tuple(Fraction(float(value)) for value in vertices[index]) for index in needed}
    boxes = {index: box([values[vertex] for vertex in faces[index]]) for index in affected + degenerate_ids}
    assert all(degenerate([values[vertex] for vertex in faces[index]]) for index in degenerate_ids)
    rows = []
    counts = Counter()
    for bad in degenerate_ids:
        for active in affected:
            witness = separation(boxes[active], boxes[bad])
            if witness is None:
                raise AssertionError("degenerate_pair_lacks_strict_separation")
            counts[witness[0]] += 1
            rows.append([active, bad, witness[0], str(witness[1])])
    return rows, {"pair_witnesses": len(rows), "by_first_axis": [counts[axis] for axis in range(3)],
                  "fraction_vertices_prepared": len(values), "fraction_faces_prepared": len(boxes)}
