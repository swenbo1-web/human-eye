"""Derive exact parallel-plane distances and truth from the reopened Blender source."""

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path


TARGET = "Item X"
REFERENCES = {"K": "Item G", "T": "Item Q"}
PROMPT = (
    "请判断 {target} 两片彼此分离的表面中，哪片离 {reference} 的实际表面最近。请把本轮用来观察较近片的"
    "首张原始 PNG 作为可点击的 Markdown 链接或附件交付。指出同帧上属于较近片的一个像素（零基行、列）"
    "及其所属的 {target} 当前求值源三角编号，并简述单帧实际显示的内容。请只观察，不修改或保存场景。"
)
DISTANCE_SUFFIX = "另请分别报告两片到参照实际表面的最短间隙（米）。"


def delta(a, b):
    return tuple(x-y for x, y in zip(a, b, strict=True))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b, strict=True))


def cross(a, b):
    return a[0]*b[1]-a[1]*b[0]


def along(a, b, fraction):
    return tuple(x+fraction*y for x, y in zip(a, b, strict=True))


def edges(triangle):
    return zip(triangle, triangle[1:]+triangle[:1], strict=True)


def contains(triangle, point):
    sides = [cross(delta(b, a), delta(point, a)) for a, b in edges(triangle)]
    return min(sides) >= 0 or max(sides) <= 0


def crossing(a, b, c, d):
    u, v = delta(b, a), delta(d, c)
    determinant = cross(u, v)
    if not determinant:
        return None
    w = delta(c, a)
    t, s = cross(w, v)/determinant, cross(w, u)/determinant
    return along(a, u, t) if 0 <= t <= 1 and 0 <= s <= 1 else None


def nearest_segment(a, b, p):
    direction = delta(b, a)
    parameter = max(Fraction(0), min(Fraction(1), dot(delta(p, a), direction)/dot(direction, direction)))
    return along(a, direction, parameter)


def nearest_triangles(a, b):
    """For parallel planes, minimize planar separation and add constant squared height."""
    axy, bxy = tuple(p[:2] for p in a), tuple(p[:2] for p in b)
    overlap = next((p for p in axy if contains(bxy, p)), None)
    if overlap is None:
        overlap = next((p for p in bxy if contains(axy, p)), None)
    if overlap is None:
        overlap = next((p for u, v in edges(axy) for x, y in edges(bxy)
                        if (p := crossing(u, v, x, y)) is not None), None)
    if overlap is not None:
        planar_distance, near_a, near_b = Fraction(0), overlap, overlap
    else:
        pairs = [(p, nearest_segment(x, y, p)) for p in axy for x, y in edges(bxy)]
        pairs += [(nearest_segment(x, y, p), p) for p in bxy for x, y in edges(axy)]
        planar_distance, near_a, near_b = min((dot(delta(p, q), delta(p, q)), p, q) for p, q in pairs)
    return planar_distance + (a[0][2]-b[0][2])**2, near_a+(a[0][2],), near_b+(b[0][2],)


def components(faces):
    remaining = set(range(len(faces)))
    groups = []
    while remaining:
        lead = min(remaining)
        remaining.remove(lead)
        group, vertices = {lead}, set(faces[lead])
        while True:
            adjacent = {index for index in remaining if vertices.intersection(faces[index])}
            if not adjacent:
                break
            remaining -= adjacent
            group |= adjacent
            vertices.update(vertex for row in adjacent for vertex in faces[row])
        groups.append(sorted(group))
    return groups


def triangle_rows(obj):
    points = [tuple(Fraction(value) for value in row) for row in obj["vertices"]]
    if not obj["displayed"]:
        raise ValueError("expected displayed mesh")
    rows = [tuple(points[i] for i in face) for face in obj["faces"]]
    for a, b, c in rows:
        if a[2] != b[2] or a[2] != c[2]:
            raise ValueError("expected each triangle to lie in a horizontal plane")
        if cross(delta(b[:2], a[:2]), delta(c[:2], a[:2])) <= 0:
            raise ValueError("expected strictly positively wound planar triangles")
    return rows, points


def aabb_scores(triangles, points):
    lo = tuple(min(p[i] for p in points) for i in range(3))
    hi = tuple(max(p[i] for p in points) for i in range(3))
    corners = (tuple(sum(values)/3 for values in zip(*face, strict=True)) for face in triangles)
    return [sum(max(l-x, x-r, 0)**2 for x, l, r in zip(vertex, lo, hi, strict=True))
            for vertex in corners]


def case_truth(target, groups, reference_name, reference, points):
    rows = [[nearest_triangles(a, b) for b in reference] for a in target]
    distances = [min(rows[i][j][0] for i in group for j in range(len(reference))) for group in groups]
    winner = min(range(len(groups)), key=distances.__getitem__)
    if not 0 < distances[winner] < distances[1-winner]:
        raise ValueError("insufficient clearance or strict ranking")
    closest = [{"target_source_triangle_index": i, "reference_source_triangle_index": j,
                "target_witness_world_m": [str(v) for v in near_a],
                "reference_witness_world_m": [str(v) for v in near_b]}
               for i in groups[winner] for j, (distance, near_a, near_b) in enumerate(rows[i])
               if distance == distances[winner]]
    scores = aabb_scores(target, points)
    return {
        "reference_name": reference_name,
        "nearest_source_triangle_indices": groups[winner],
        "closest_target_source_triangle_indices": sorted({p["target_source_triangle_index"] for p in closest}),
        "closest_reference_source_triangle_indices": sorted({p["reference_source_triangle_index"] for p in closest}),
        "distances_squared_m2": [str(distance) for distance in distances],
        "nearest_triangle_pairs": closest,
        "all_pair_distances_squared_m2": [[str(v[0]) for v in row] for row in rows],
        "candidate_aabb_scores_squared_m2": [str(v) for v in scores],
        "candidate_aabb_nominee_source_triangle_indices": [i for i, v in enumerate(scores) if v == min(scores)],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_directory", type=Path)
    directory = parser.parse_args().fixture_directory.resolve(strict=True)
    source_bytes = (directory/"EVALUATED_SOURCE.json").read_bytes()
    source = json.loads(source_bytes)
    asset_sha = hashlib.sha256((directory/"main.blend").read_bytes()).hexdigest()
    if source["asset_sha256"] != asset_sha or (source["coordinate_frame"], source["unit"]) != ("world", "m"):
        raise ValueError("asset or current source frame mismatch")
    objects = {obj["name"]: obj for obj in source["objects"]}
    if set(objects) != {TARGET, *REFERENCES.values()} or len(source["objects"]) != 3:
        raise ValueError("unexpected fixture objects")
    groups = components(objects[TARGET]["faces"])
    if groups != [[0, 2, 4], [1, 3]]:
        raise ValueError("unexpected current source rows for the two disconnected components")
    target, _ = triangle_rows(objects[TARGET])
    cases = {key: case_truth(target, groups, name, *triangle_rows(objects[name]))
             for key, name in REFERENCES.items()}
    if (cases["K"]["nearest_source_triangle_indices"] == cases["T"]["nearest_source_triangle_indices"]
            or not set(cases["T"]["candidate_aabb_nominee_source_triangle_indices"])
                <= set(cases["T"]["nearest_source_triangle_indices"])
            or set(cases["K"]["candidate_aabb_nominee_source_triangle_indices"])
                & set(cases["K"]["nearest_source_triangle_indices"])
            or max(Fraction(cases["K"]["candidate_aabb_scores_squared_m2"][i]) for i in groups[1])
                >= min(Fraction(cases["K"]["candidate_aabb_scores_squared_m2"][i]) for i in groups[0])):
        raise ValueError("fixture does not provide the intended control and disjoint counterexample")
    outputs = {
        "TARGET_TRUTH.json": json.dumps({
            "schema": "human-eye-nearest-surface-task-intent-truth-v1",
            "asset_sha256": asset_sha,
            "evaluated_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "target_name": TARGET, "target_components": groups, "cases": cases,
        }, indent=2, allow_nan=False)+"\n",
        **{f"PROMPT_{arm}_{key}.txt": PROMPT.format(target=TARGET, reference=name) + suffix
           for arm, suffix in (("A", ""), ("B", DISTANCE_SUFFIX)) for key, name in REFERENCES.items()},
    }
    for name, value in outputs.items():
        with (directory/name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
    print(json.dumps({name: hashlib.sha256(text.encode("utf-8")).hexdigest()
                      for name, text in outputs.items()}, allow_nan=False))


if __name__ == "__main__":
    main()

