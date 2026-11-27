"""Independent high-box geometry check for the fixed Yanyite scene, using the Python standard library."""

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path


TERMINAL_SHA = "9c915abfae62deae475186c801c5573f4200361357124bd1f101f82b60211c95"
ASSET_SHA = "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"
HIGH = {"min": [-0.03, -0.055, 0.81], "max": [0.03, 0.055, 0.855]}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def orient_xy(a, b, p):
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def on_top_triangle(point, vertices):
    if any(v[2] != point[2] for v in vertices):
        return False
    a, b, c = vertices
    require(orient_xy(a, b, c) != 0, "degenerate reference top triangle")
    turns = orient_xy(a, b, point), orient_xy(b, c, point), orient_xy(c, a, point)
    return min(turns) >= 0 or max(turns) <= 0


def exact_reference(terminal_path, asset_path):
    packet = terminal_path.read_bytes()
    require(hashlib.sha256(packet).hexdigest() == TERMINAL_SHA, "terminal capture identity")
    require(hashlib.sha256(asset_path.read_bytes()).hexdigest() == ASSET_SHA, "asset identity")
    doc = json.loads(packet)
    require(doc["source"]["asset_sha256"] == ASSET_SHA and doc["source"]["frame"] == 1
            and doc["source"]["subframe"] == 0 and doc["source"]["scale_length"] == 1, "frame or unit")
    target, cube = doc["objects"]
    require(cube["name"] == "Cube" and target["name"] != cube["name"], "object selection")
    mesh, ref = target["evaluated"], cube["evaluated"]
    coords = mesh["vertices_world_m"]
    inside = [all(lo <= x <= hi for x, lo, hi in zip(v, HIGH["min"], HIGH["max"], strict=True))
              for v in coords]
    selected = {i: f for i, f in enumerate(mesh["triangles"]) if all(inside[j] for j in f)}
    used = {j for f in selected.values() for j in f}
    xyz = {j: tuple(map(Fraction, coords[j])) for j in used}
    ref_points = [tuple(map(Fraction, v)) for v in ref["vertices_world_m"]]
    require(len(ref_points) == len(set(ref_points)) == 8 and len(ref["triangles"]) == 12
            and all(abs(x) == 1 for v in ref_points for x in v), "unit cube")

    # Each reference triangle lies on a single cube plane. A point on any selected
    # triangle is a convex combination of its vertices. The axis extrema thus
    # give exact lower bounds for the distance to every reference triangle.
    planes = []
    for f in ref["triangles"]:
        a, b, c = (ref_points[j] for j in f)
        fixed = [(k, a[k]) for k in range(3) if a[k] == b[k] == c[k]]
        require(len(fixed) == 1, "invalid cube surface")
        planes.append(fixed[0])
    require(len(set(planes)) == 6, "missing cube face")
    bounds = {plane: min(abs(v[plane[0]] - plane[1]) for v in xyz.values()) for plane in planes}
    gap = min(bounds.values())
    require([p for p in bounds if bounds[p] == gap] == [(2, 1)], "expected unique top plane")
    top_vertices = [j for j, v in xyz.items() if 1 - v[2] == gap]
    require(len(top_vertices) == 1 and gap > 0, "expected unique closest source point")
    top_id = top_vertices[0]
    a = xyz[top_id]
    b = (a[0], a[1], Fraction(1))
    rows_a = [i for i, face in selected.items() if top_id in face]
    rows_b = [i for i, face in enumerate(ref["triangles"]) if
              on_top_triangle(b, [ref_points[j] for j in face])]
    require(rows_a and rows_b, "attained bound must have native source triangles")
    canonical_pair = [min(rows_a), min(rows_b)]
    expected = {
        "schema": "human-eye-source-region-scoped-measurement-v1", "status": "complete",
        "measurement_scope": "complete_selected_source_triangle_union_to_reference_triangle_surface",
        "coordinate_frame": "world", "unit": "m", "world_box_m": HIGH, "read_only": True,
        "selected_triangle_count": len(selected), "distance_m": float(gap),
        "direction_status": "measured", "direction_a_to_b": [0.0, 0.0, 1.0],
        "point_a_m": list(map(float, a)), "point_b_m": list(map(float, b)),
        "source_triangle_index_domain": doc["source"]["source_index_domain"],
        "source_triangle_a": canonical_pair[0], "source_triangle_b": canonical_pair[1],
    }
    return {"terminal_sha256": TERMINAL_SHA, "asset_sha256": ASSET_SHA,
            "world_vertices": len(coords), "world_triangles": len(mesh["triangles"]),
            "selected_vertices": len(used), "source_vertex": top_id, "distance_exact_m": str(gap),
            "source_ties": rows_a, "reference_ties": rows_b,
            "target_name": target["name"], "reference_name": cube["name"], "expected": expected}


def verify_response(path, oracle):
    wire = json.loads(path.read_bytes())
    require("error" not in wire and not wire["result"].get("isError", False), "error reply")
    blocks = wire["result"]["content"]
    require(len(blocks) == 1 and blocks[0]["type"] == "text", "expected one geometry reply")
    value = json.loads(blocks[0]["text"])
    for key, expected in oracle["expected"].items():
        # Canonical JSON also detects signed zero and bool/int substitutions.
        options = {"sort_keys": True, "allow_nan": False}
        require(json.dumps(value[key], **options) == json.dumps(expected, **options),
                f"{path.name} geometry mismatch in {key}")
    require(value["region_object"]["name"] == oracle["target_name"]
            and value["reference_object"]["name"] == oracle["reference_name"], "selector mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("terminal", type=Path)
    parser.add_argument("asset", type=Path)
    parser.add_argument("responses", nargs="*", type=Path)
    args = parser.parse_args()
    oracle = exact_reference(args.terminal, args.asset)
    for path in args.responses:
        verify_response(path, oracle)
    print(json.dumps({"geometry": oracle, "native_wire_responses_checked": len(args.responses)}, indent=2))


if __name__ == "__main__":
    main()
