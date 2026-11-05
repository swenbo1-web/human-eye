"""Root review of public VG PNGs against frozen native-ray evidence.

This CPU audit does not rerun Blender's native oracle. It independently
recomputes public target support and gap visibility from that oracle's raw
hits, actual encoded pixels, and actual GPU matrix records. Author verdicts
(`passed`, `matched`, and `is_gap`) are never used to decide these checks.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import floor
from pathlib import Path

import numpy as np
from PIL import Image


SIZE = 512
COLORS = ((.82, .24, .15, 1.), (.16, .60, .90, 1.))
OBSTACLE = (.36, .40, .45, 1.)
BACKGROUND = (.08, .10, .14, 1.)


def _color(pixel, color):
    expected = np.rint(np.asarray(color) * 255).astype(np.int16)
    return bool(np.all(np.abs(np.asarray(pixel, dtype=np.int16) - expected) <= 1))


def _line(first, last):
    x, y = (floor(value + .5) for value in first)
    end_x, end_y = (floor(value + .5) for value in last)
    dx, dy = abs(end_x - x), -abs(end_y - y)
    sx, sy = (1 if x < end_x else -1), (1 if y < end_y else -1)
    error = dx + dy
    result = []
    while True:
        result.append((x, y))
        if (x, y) == (end_x, end_y):
            return result
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x += sx
        if doubled <= dx:
            error += dx
            y += sy


def _circle(point):
    u, v = point
    return {(x, y) for x in range(max(0, floor(u) - 3), min(SIZE, floor(u) + 5))
            for y in range(max(0, floor(v) - 3), min(SIZE, floor(v) + 5))
            if (x - u) ** 2 + (y - v) ** 2 <= 9}


def _longest(values):
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def verify_public_pixels(case, method, hud, bottom):
    """Audit one positive-gap fixture, ignoring the author's verdict flags."""
    metadata = case["first_observation"]["methods"][method]["observation"]
    evidence = case["quality"][method]
    target_ids = tuple(case["target_ids"])
    witness = case["witness"]
    positions = np.array([witness["point_a"], witness["point_b"]], dtype=np.float64)
    gpu = metadata["views"]["local"]["gpu"]
    points = np.column_stack((positions, np.ones(2)))
    clip = points @ np.asarray(gpu["view_projection"], dtype=np.float64).T
    pixels = (clip[:, :2] / clip[:, 3, None] * (1, -1) + 1) * (SIZE / 2) - .5
    depths = -(points @ np.asarray(gpu["view"], dtype=np.float64)[2])
    delta = pixels[1] - pixels[0]
    separation = float(np.linalg.norm(delta))
    tolerance = evidence["depth_tolerance_m"]
    palette = {key: OBSTACLE for key in case["meshes"]}
    palette.update(zip(target_ids, COLORS))
    palette[None] = BACKGROUND
    checks = {
        "png_dimensions": hud.shape == (SIZE, 2 * SIZE, 4) and bottom.shape == hud.shape,
        "binding": tuple(metadata["target_ids"]) == target_ids
                   and metadata["frame_id"] == case["frame_id"]
                   and metadata["mode"] == case["mode"],
        "projected_witnesses": bool(np.all(pixels >= -.5) and np.all(pixels < SIZE - .5)
                                    and separation >= 4),
        "raw_ray_coverage": True,
        "raw_hit_identity": True,
        "raw_pixels_match_bottom": True,
    }
    if not checks["png_dimensions"]:
        return {"passed": False, "checks": checks}

    def inspect(record):
        x, y = record["pixel"]
        owner, face, depth = record["object"], record["face"], record["depth_m"]
        hit_valid = ((owner is None and face is None and depth is None) or
                     (owner in case["meshes"] and isinstance(face, int)
                      and 0 <= face < case["meshes"][owner]["triangles"]
                      and isinstance(depth, (int, float)) and np.isfinite(depth) and depth > 0))
        checks["raw_hit_identity"] &= hit_valid
        if not (0 <= x < SIZE and 0 <= y < SIZE) or owner not in palette:
            checks["raw_ray_coverage"] = False
            return None, None, False, False
        actual_bottom, actual_hud = bottom[y, x + SIZE], hud[y, x + SIZE]
        checks["raw_pixels_match_bottom"] &= bool(np.array_equal(record["rgba"], actual_bottom))
        return owner, depth, _color(actual_bottom, palette[owner]), _color(actual_hud, palette[owner])

    support = {}
    for point, target_id in zip(pixels, target_ids):
        records = evidence["witness_neighborhood_rays"].get(target_id, [])
        sampled = [tuple(record["pixel"]) for record in records]
        checks["raw_ray_coverage"] &= len(sampled) == len(set(sampled)) and set(sampled) == _circle(point)
        bottom_hits = public_hits = 0
        for record in records:
            owner, _, bottom_match, public_match = inspect(record)
            bottom_hits += owner == target_id and bottom_match
            public_hits += owner == target_id and bottom_match and public_match
        support[target_id] = {"bottom": bottom_hits, "public": public_hits}
    checks["public_target_surface_pixels"] = all(item["public"] >= 2 for item in support.values())

    expected_line = _line(*pixels)[1:-1] if checks["projected_witnesses"] else []
    records = evidence["interior_gap_rays"]
    checks["raw_ray_coverage"] &= [tuple(record["pixel"]) for record in records] == expected_line
    bottom_gap, public_gap = [], []
    for record in records:
        owner, depth, bottom_match, public_match = inspect(record)
        fraction = float(np.clip((np.asarray(record["pixel"]) - pixels[0]) @ delta /
                                 (separation * separation), 0., 1.))
        expected_depth = depths[0] + fraction * (depths[1] - depths[0])
        clear = owner not in target_ids and (depth is None or depth > expected_depth + tolerance)
        bottom_gap.append(clear and bottom_match)
        public_gap.append(clear and bottom_match and public_match)
    checks["public_consecutive_gap_pixels"] = _longest(public_gap) >= 3
    return {
        "passed": bool(all(checks.values())),
        "checks": {key: bool(value) for key, value in checks.items()},
        "target_support": support,
        "bottom_gap_run": _longest(bottom_gap), "public_gap_run": _longest(public_gap),
        "projected_gap_px": separation,
    }


def read_images(case, method):
    files = case["first_observation"]["methods"][method]["artifacts"]
    checked = all(sha256(Path(item["path"]).read_bytes()).hexdigest() == item["sha256"]
                  for item in files.values())
    images = {key: np.asarray(Image.open(item["path"]).convert("RGBA"))
              for key, item in files.items()}
    return images["hud"], np.concatenate((images["global"], images["local"]), axis=1), checked


def audit_run(directory):
    """Audit all 24 × 2 × 3 public images, preserving failed baseline cases."""
    records = []
    for path in sorted(Path(directory).glob("process_*/raw.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        cases = []
        for case in raw["cases"]:
            methods = {}
            for method in ("fixed", "active"):
                hud, bottom, digest_matches = read_images(case, method)
                result = verify_public_pixels(case, method, hud, bottom)
                result["checks"]["artifact_digests"] = digest_matches
                result["passed"] &= digest_matches
                methods[method] = result
            cases.append({"scene_id": case["scene_id"], "family": case["family"],
                          "mode": case["mode"], "methods": methods})
        sets = {method: [case["scene_id"] for case in cases if case["methods"][method]["passed"]]
                for method in ("fixed", "active")}
        records.append({"worker": raw["worker"], "pid": raw["pid"], "cases": cases,
                        "public_pass_sets": sets,
                        "gain": len(sets["active"]) - len(sets["fixed"]),
                        "lost": sorted(set(sets["fixed"]) - set(sets["active"]))})
    complete = len(records) == 3 and all(
        Counter(case["scene_id"] for case in record["cases"]) == Counter(range(24)) for record in records)
    return {"scope": "Public PNG critical pixels; frozen native-ray evidence, no new Blender execution",
            "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "complete": complete, "processes": records,
            "public_quality_gate_passed": complete and all(record["gain"] >= 5 and not record["lost"]
                                                            for record in records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_run(args.run)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"complete": result["complete"], "passed": result["public_quality_gate_passed"],
                      "processes": [{"worker": p["worker"], "gain": p["gain"], "lost": p["lost"],
                                     "counts": {m: len(ids) for m, ids in p["public_pass_sets"].items()}}
                                    for p in result["processes"]]}))
    return 0 if result["public_quality_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
