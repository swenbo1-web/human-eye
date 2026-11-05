"""Independent native ray evidence and a separate Pillow consumer for CF views."""

from __future__ import annotations

import base64
from dataclasses import replace
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verification.test_cerebellar_flash import _native_directions
from verification.test_raycast_saccade_gpu import (
    BACKGROUND, CAMERA_TOLERANCE, EPS32, FIXED_DIRECTION, OBSTACLE, SIZE, TARGET_COLORS,
    _Camera, _clip_polygon, _close, _digital_line, _longest_run, _neighbors, _witness_points,
)


ORDER = tuple(range(16))
_GRID_AXIS = np.linspace(8, SIZE - 9, 25).astype(np.int32)
_GRID = np.column_stack((np.tile(_GRID_AXIS, 25), np.repeat(_GRID_AXIS, 25)))
_NEIGHBOR_OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1))
_HEADER = struct.Struct("<II")


def validate_order(order):
    """Check the experimental arm before passing its permutation to trusted VG."""
    order = tuple(order)
    if any(not isinstance(index, (int, np.integer)) or isinstance(index, bool) for index in order):
        raise ValueError("canonical directions are integer indices")
    order = tuple(map(int, order))
    if sorted(order) != list(ORDER):
        raise ValueError("a CF arm must supply each canonical direction exactly once")
    return order


def _pack(array, dtype):
    return base64.b64encode(np.ascontiguousarray(array, dtype=dtype)).decode("ascii")


def _unpack(value, dtype, shape):
    return np.frombuffer(base64.b64decode(value), dtype=dtype).reshape(shape)


def _matches(pixels, expected):
    return (np.abs(pixels.astype(np.int16) - expected.astype(np.int16)) <= 1).all(axis=-1)


def _json_witness(witness):
    return {"distance_m": witness.distance_m, "face_a": witness.triangle_a,
            "face_b": witness.triangle_b, "point_a": list(witness.point_a),
            "point_b": list(witness.point_b)}


class _RayIndex:
    """Build independent natural or per-triangle clipped original-face rays."""

    def __init__(self, triangles, owners, face_ids, section=None):
        from mathutils.bvhtree import BVHTree

        indices = np.arange(len(triangles), dtype=np.int32)
        if section is not None:
            center, normal = section
            kept = (triangles - center) @ normal <= 0
            full = kept.all(axis=1)
            clipped, sources = [], []
            for source in np.flatnonzero(kept.any(axis=1) & ~full):
                polygon = _clip_polygon(triangles[source], center, normal)
                for i in range(1, len(polygon) - 1):
                    clipped.append((polygon[0], polygon[i], polygon[i + 1]))
                    sources.append(source)
            indices = indices[full]
            triangles = triangles[full]
            if clipped:
                indices = np.r_[indices, np.asarray(sources, dtype=np.int32)]
                order = np.argsort(indices, kind="stable")
                triangles = np.concatenate((triangles, np.asarray(clipped)))[order]
                indices = indices[order]
        valid = np.cross(triangles[:, 1] - triangles[:, 0],
                         triangles[:, 2] - triangles[:, 0]).any(axis=1)
        indices = indices[valid]
        triangles = triangles[valid]
        self.owners = owners[indices]
        self.faces = face_ids[indices]
        self.bvh = BVHTree.FromPolygons(
            triangles.reshape(-1, 3).tolist(),
            np.arange(triangles.size // 3).reshape(-1, 3).tolist(),
            all_triangles=True,
        )

    def cast(self, camera, pixels, *, depth=False):
        from mathutils import Vector

        pixels = np.asarray(pixels, dtype=float).reshape(-1, 2)
        ndc_xy = ((2 * pixels + 1) / SIZE - 1) * (1, -1)
        origins = ndc_xy @ camera.inverse[:3, :2].T + (
            camera.inverse[:3, 3] - camera.inverse[:3, 2])
        direction = Vector(camera.ray_direction)
        ray_cast = self.bvh.ray_cast
        hits = [ray_cast(Vector(origin), direction, camera.ray_length) for origin in origins.tolist()]
        hit_indices = np.asarray([hit[2] if hit[2] is not None else -1 for hit in hits], dtype=np.int32)
        found = hit_indices >= 0
        owner = np.zeros(len(hits), dtype=np.int32)
        owner[found] = self.owners[hit_indices[found]]
        if not depth:
            return owner
        face = np.full(len(hits), -1, dtype=np.int32)
        face[found] = self.faces[hit_indices[found]]
        depths = [None] * len(hits)
        for i in np.flatnonzero(found):
            depths[i] = float(-(camera.view[2, :3] @ np.asarray(hits[i][0]) + camera.view[2, 3]))
        return owner, face, depths


class _Trace:
    def __init__(self, prepared):
        self.cast = prepared.rays.ray_cast
        self.owners = prepared.triangle_owners
        self.rays = []

    def ray_cast(self, origin, direction):
        hit = self.cast(origin, direction)
        index, depth = hit[2:]
        self.rays.append({
            "origin_m": list(origin), "direction": list(direction), "triangle": index,
            "owner": None if index is None else self.owners[index], "depth_m": depth,
        })
        return hit


def _ray_evidence(trace, selection, canonical, order, audit, prepared):
    probes = selection["probes"]
    if not order:
        assert not probes and not trace and selection["ray_count"] == 0
        return None, False, None
    assert 0 < len(probes) <= len(order)
    a, b = np.asarray((audit.witness.point_a, audit.witness.point_b))
    center = (a + b) * .5
    axis = (b - a) / audit.witness.distance_m
    from mathutils import Vector

    # Reconstruct the engine's native metric comparison at its recorded precision.
    native_center = (Vector(audit.witness.point_a) + Vector(audit.witness.point_b)) / 2
    radius = prepared.radius + (native_center - prepared.center).length
    witness_depth = 0. if audit.mode == "SECTION" else 2.5 * radius
    threshold = witness_depth + 8 * EPS32 * prepared.max_side
    offset = 0
    scores = []
    for candidate, probe in zip(order, probes):
        count = probe["ray_count"]
        calls = trace[offset:offset + count]
        offset += count
        direction = canonical[candidate]
        np.testing.assert_allclose(probe["direction"], direction, rtol=0, atol=2e-6)
        np.testing.assert_allclose(np.asarray([ray["direction"] for ray in calls]),
                                   np.broadcast_to(-direction, (len(calls), 3)), rtol=0, atol=2e-6)
        opened = 0
        for call in calls[:9]:
            call.update(candidate=candidate, purpose="aperture")
            if call["owner"] is not None and (
                    call["owner"] in audit.targets or call["depth_m"] <= threshold):
                break
            opened += 1
        assert opened == probe["aperture_taps"]
        supported = 0
        if opened == 9:
            along = (np.asarray([ray["origin_m"] for ray in calls[9:]]) - center) @ axis
            halves = (along < 0, along > 0)
            assert len(along) >= 4 and np.all(along != 0)
            first_count = int(halves[0].sum())
            assert halves[0][:first_count].all() and halves[1][first_count:].all()
            for phase, target, mask in zip(("support_a", "support_b"), audit.targets, halves):
                support = [call for call, in_half in zip(calls[9:], mask) if in_half]
                hits = sum(call["owner"] == target for call in support)
                assert 2 <= len(support) <= 6 and hits <= 2
                assert len(support) == 6 or (hits == 2 and support[-1]["owner"] == target)
                for call in support:
                    call.update(candidate=candidate, purpose=phase)
                supported += hits == 2
        else:
            assert count == opened + 1
        assert supported == probe["target_support"]
        scores.append((supported, opened))
    assert offset == len(trace) == selection["ray_count"]
    assert all(score[0] < 2 for score in scores[:-1])
    native_stop = scores[-1][0] == 2
    assert native_stop or len(probes) == len(order)
    best = len(scores) - 1 if native_stop else max(range(len(scores)), key=scores.__getitem__)
    chosen = order[best]
    np.testing.assert_allclose(selection["direction"], canonical[chosen], rtol=0, atol=2e-6)
    return chosen, native_stop, list(scores[best])


class VisualAudit:
    """Reuse geometry and the unchanged world view within one native episode."""

    def __init__(self, native_meshes, targets, frame_id, mode, scale_length, witness):
        self.meshes = native_meshes
        self.targets = tuple(targets)
        self.frame_id = frame_id
        self.mode = mode
        self.scale_length = scale_length
        self.witness = witness
        self.ids = (None, *native_meshes)
        colors = {key: OBSTACLE for key in native_meshes}
        colors[None] = BACKGROUND
        colors.update(zip(self.targets, TARGET_COLORS))
        self.palette = np.rint(255 * np.asarray([colors[key] for key in self.ids])).astype(np.uint8)
        self.positions = np.concatenate([vertices for vertices, _ in native_meshes.values()])
        self.max_side = float(np.ptp(self.positions, axis=0).max())
        self.depth_tolerance = float(8 * EPS32 * self.max_side)
        self.triangles = np.concatenate([vertices[faces] for vertices, faces in native_meshes.values()])
        self.owners = np.concatenate([np.full(len(faces), i, dtype=np.int32)
                                     for i, (_, faces) in enumerate(native_meshes.values(), 1)])
        self.face_ids = np.concatenate([np.arange(len(faces), dtype=np.int32)
                                       for _, faces in native_meshes.values()])
        self.original = _RayIndex(self.triangles, self.owners, self.face_ids)
        self.global_cache = None

    def _grid(self, camera, index, image, center_owner=None):
        owners = index.cast(camera, _GRID) if center_owner is None else center_owner
        bottom = image[_GRID[:, 1], _GRID[:, 0]]
        differences = np.flatnonzero(~_matches(bottom, self.palette[owners]))
        near = _GRID[differences, None, :] + np.asarray(_NEIGHBOR_OFFSETS)
        edge_owners = index.cast(camera, near.reshape(-1, 2)).reshape(-1, 4)
        return {"owners_i32le": _pack(owners, "<i4"), "bottom_rgba": _pack(bottom, "u1"),
                "edge_owners": [[int(i), choices.tolist()]
                                for i, choices in zip(differences, edge_owners)]}

    def _samples(self, camera, index, bottom, points):
        points = np.asarray(points, dtype=np.int32).reshape(-1, 2)
        owner, face, depth = index.cast(camera, points, depth=True)
        pixels = bottom[points[:, 1], points[:, 0]]
        return {"pixels": points.tolist(), "owners": owner.tolist(), "faces": face.tolist(),
                "depth_m": depth, "bottom_rgba": _pack(pixels, "u1")}

    def record(self, observation, *, order, candidate, native_stop, native_score, trace, relation):
        metadata = observation.metadata
        views = metadata["views"]
        if self.global_cache is None or self.global_cache[0] != views["global"]:
            camera = _Camera(views["global"], self.scale_length)
            self.global_cache = (views["global"], camera, self.original.cast(camera, _GRID))
        _, global_camera, global_owner = self.global_cache
        local_camera = _Camera(views["local"], self.scale_length)
        fixture = SimpleNamespace(witness=self.witness, target_ids=self.targets)
        points, witness_bound = _witness_points(fixture, self, metadata["witness"])
        center = points.mean(axis=0)
        gap = self.witness.distance_m
        section = None
        declared = metadata["section"]
        section_ok = self.mode == "NATURAL" and declared is None
        if self.mode == "SECTION":
            axis = (points[1] - points[0]) / gap
            direction = local_camera.backward
            normal = direction - (direction @ axis) * axis
            normal /= np.linalg.norm(normal)
            section_ok = (declared is not None and declared["kept_side"] == "<=0"
                          and _close(declared["point_m"], center, self.depth_tolerance)
                          and _close(declared["normal"], normal))
            # Once independently bound, preserve the actual shader-plane
            # coordinates when evaluating edge ownership at float32 precision.
            section = ((np.asarray(declared["point_m"]), np.asarray(declared["normal"]))
                       if section_ok else (center, normal))
        local_index = (self.original if section is None else
                       _RayIndex(self.triangles, self.owners, self.face_ids, section))
        bottom = np.asarray(observation.bottom_rgba)
        assert bottom.shape == (SIZE, 2 * SIZE, 4) and bottom.dtype == np.uint8
        global_bottom, local_bottom = bottom[:, :SIZE], bottom[:, SIZE:]
        global_points, _ = global_camera.project(points)
        local_points, _ = local_camera.project(points)
        global_scene_pixels, global_depths = global_camera.project(self.positions)
        _, local_depths = local_camera.project(self.positions)
        projected = (np.all(local_points >= -.5) and np.all(local_points < SIZE - .5)
                     and np.linalg.norm(local_points[1] - local_points[0]) >= 4)
        samples = ({} if not gap else {
            "supports": [self._samples(local_camera, local_index, local_bottom, list(_neighbors(point)))
                         for point in local_points],
            "interior": self._samples(local_camera, local_index, local_bottom,
                                      _digital_line(*local_points)[1:-1] if projected else []),
        })
        return {
            "metadata": metadata,
            "expected": {"target_ids": list(self.targets), "frame_id": self.frame_id,
                         "mode": self.mode, "scale_length": self.scale_length,
                         "witness": _json_witness(self.witness),
                         "status": "POSITIVE_GAP" if gap else relation or "ZERO_GAP"},
            "mesh_ids": list(self.ids), "face_counts": [0, *(len(f) for _, f in self.meshes.values())],
            "depth_tolerance_m": self.depth_tolerance,
            "order": list(order), "candidate": candidate, "native_stop": native_stop,
            "native_score": native_score, "ray_count": len(trace), "trace": trace,
            "selected_rays": sum(call["candidate"] == candidate for call in trace),
            "native_checks": {
                "witness_on_surface": witness_bound,
                "section_declaration": section_ok,
                "viewports": (global_camera.viewport == [0, 0, SIZE, SIZE]
                              and local_camera.viewport == [SIZE, 0, SIZE, SIZE]),
                "global_camera_matrices": all(global_camera.agreement.values()),
                "local_camera_matrices": all(local_camera.agreement.values()),
                "directions": (_close(global_camera.backward, FIXED_DIRECTION)
                               and _close(local_camera.backward, metadata["selection"]["direction"])),
                "local_center_width": (
                    _close(local_camera.width, 32 * gap if gap else .25 * self.max_side,
                           self.depth_tolerance)
                    and _close(local_camera.project(center[None])[0][0],
                               ((SIZE - 1) / 2, (SIZE - 1) / 2), .005)),
                "global_complete_frame": bool(np.all(global_scene_pixels >= -.5)
                                              and np.all(global_scene_pixels <= SIZE - .5)),
                "camera_full_depth": all(
                    camera.near - self.depth_tolerance <= depths.min() <= depths.max()
                    <= camera.far + self.depth_tolerance and depths.min() > 0
                    for camera, depths in ((global_camera, global_depths),
                                           (local_camera, local_depths))),
            },
            "grid": {"global": self._grid(global_camera, self.original, global_bottom, global_owner),
                     "local": self._grid(local_camera, local_index, local_bottom)},
            "samples": samples,
            "witness_pixels": {"global": global_points.tolist(), "local": local_points.tolist()},
        }


def observe(renderer, prepared, audit, rank_directions=None, *, canonical_order=None, relation=None):
    """Call production VG and independently attribute every ray to its canonical candidate."""
    trace = _Trace(prepared)
    positive = audit.witness.distance_m > 0
    canonical = _native_directions(audit.witness) if positive else None
    order = ORDER if positive else ()
    forced = None if canonical_order is None else tuple(canonical_order)
    if forced is not None and (len(forced) != 1 or type(forced[0]) is not int or forced[0] not in ORDER):
        raise ValueError("offline canonical_order must contain one direction")

    def rank(directions):
        nonlocal order
        np.testing.assert_allclose(np.asarray(directions), canonical, rtol=0, atol=2e-6)
        proposed = forced if rank_directions is None else tuple(rank_directions(directions))
        if forced is None:
            order = validate_order(proposed)
        else:
            assert proposed == forced
            order = forced
        return order

    observation = renderer.observe(
        replace(prepared, rays=trace), audit.witness, target_ids=audit.targets, frame_id=audit.frame_id,
        scale_length=audit.scale_length, mode=audit.mode, relation=relation, audit=True,
        rank_directions=rank if rank_directions is not None or forced is not None else None,
    )
    chosen, stopped, score = _ray_evidence(trace.rays, observation.metadata["selection"],
                                            canonical, order, audit, prepared)
    return observation, audit.record(observation, order=order, candidate=chosen, native_stop=stopped,
                                     native_score=score, trace=trace.rays, relation=relation)


def _palette(record):
    targets = dict(zip(record["expected"]["target_ids"], TARGET_COLORS))
    colors = [BACKGROUND, *(targets.get(key, OBSTACLE) for key in record["mesh_ids"][1:])]
    return np.rint(255 * np.asarray(colors)).astype(np.uint8)


def _score_grid(image, raw, palette, witness_pixels, panel):
    n = len(_GRID)
    owner = _unpack(raw["owners_i32le"], "<i4", (n,))
    bottom = _unpack(raw["bottom_rgba"], "u1", (n, 4))
    bottom_matches = _matches(bottom, palette[owner])
    mismatches = set(np.flatnonzero(~bottom_matches).tolist())
    edge_match = 0
    for i, options in raw["edge_owners"]:
        if i in mismatches and _matches(bottom[i], palette[options]).any():
            mismatches.remove(i)
            edge_match += 1
    # The HUD may overwrite its banner and witness markers. Require the
    # remaining distributed samples to match the original GPU bottom readback.
    outside = (_GRID[:, 1] >= 64) & (_GRID[:, 1] <= 447)
    outside &= (_GRID[:, 0] < SIZE - 1) if panel == 0 else (_GRID[:, 0] > 0)
    for point in witness_pixels:
        outside &= np.square(_GRID - point).sum(axis=1) > 32 ** 2
    public = image[_GRID[:, 1], _GRID[:, 0] + panel * SIZE]
    hud_drift = int(np.count_nonzero(outside & ~np.equal(public, bottom).all(axis=1)))
    return {"passed": not mismatches and hud_drift == 0, "rays": n, "edges": edge_match,
            "edge_rays": 4 * len(raw["edge_owners"]), "mismatches": len(mismatches),
            "first_mismatch_pixels": _GRID[sorted(mismatches)[:16]].tolist(),
            "public_drift_pixels": hud_drift}


def _project(record):
    witness = record["expected"]["witness"]
    points = np.column_stack((np.asarray((witness["point_a"], witness["point_b"])), np.ones(2)))
    gpu = record["metadata"]["views"]["local"]["gpu"]
    clip = points @ np.asarray(gpu["view_projection"], dtype=float).T
    pixels = ((clip[:, :2] / clip[:, 3, None]) * (1, -1) + 1) * (SIZE / 2) - .5
    depth = -(points @ np.asarray(gpu["view"], dtype=float)[2])
    return pixels, depth


def _score_samples(image, palette, record):
    pixels, witness_depth = _project(record)
    delta = pixels[1] - pixels[0]
    separation = float(np.linalg.norm(delta))
    if record["expected"]["witness"]["distance_m"] == 0:
        return {"coincident_projection": bool(separation <= CAMERA_TOLERANCE),
                "no_reported_gap_pixels": record["metadata"]["selection"]["gap_pixels"] == 0}, {}
    projected = bool((pixels >= -.5).all() and (pixels < SIZE - .5).all() and separation >= 4)
    checks = {"projected_witnesses": projected, "raw_ray_coverage": True,
              "raw_hit_identity": True}
    target_ids = record["expected"]["target_ids"]
    target_codes = [record["mesh_ids"].index(key) for key in target_ids]
    face_counts = np.asarray(record["face_counts"])

    def inspect(raw, expected):
        xy = np.asarray(raw["pixels"], dtype=np.int32).reshape(-1, 2)
        checks["raw_ray_coverage"] &= np.array_equal(xy, np.asarray(expected).reshape(-1, 2))
        owner = np.asarray(raw["owners"], dtype=np.int32)
        face = np.asarray(raw["faces"], dtype=np.int32)
        depth = np.asarray([np.inf if value is None else value for value in raw["depth_m"]])
        hit = owner != 0
        checks["raw_hit_identity"] &= bool(
            ((hit & (face >= 0) & (face < face_counts[owner]) & np.isfinite(depth) & (depth > 0))
             | (~hit & (face == -1) & np.isposinf(depth))).all()
        )
        bottom = _unpack(raw["bottom_rgba"], "u1", (len(xy), 4))
        actual = image[xy[:, 1], xy[:, 0] + SIZE]
        return xy, owner, depth, _matches(bottom, palette[owner]), _matches(actual, palette[owner])

    support = {}
    for point, target, code, sample in zip(pixels, target_ids, target_codes, record["samples"]["supports"]):
        _, owner, _, bottom, hud = inspect(sample, list(_neighbors(point)))
        support[target] = {"bottom": int(np.count_nonzero((owner == code) & bottom)),
                           "public": int(np.count_nonzero((owner == code) & bottom & hud))}
    xy, owner, depth, bottom, hud = inspect(
        record["samples"]["interior"], _digital_line(*pixels)[1:-1] if projected else [])
    if separation > 0:
        fraction = np.clip((xy - pixels[0]) @ delta / separation ** 2, 0, 1)
    else:
        fraction = np.zeros(len(xy))
    interpolated = witness_depth[0] + fraction * (witness_depth[1] - witness_depth[0])
    clear = ~np.isin(owner, target_codes) & (depth > interpolated + record["depth_tolerance_m"])
    bottom_run = _longest_run(clear & bottom)
    public_run = _longest_run(clear & bottom & hud)
    checks["public_target_surface_pixels"] = all(value["public"] >= 2 for value in support.values())
    checks["public_consecutive_gap_pixels"] = public_run >= 3
    checks["reported_projected_separation"] = abs(
        separation - record["metadata"]["selection"]["gap_pixels"]) <= .005
    return checks, {"target_support": support, "bottom_gap_run": bottom_run,
                    "public_gap_run": public_run, "projected_gap_px": separation}


def score_png(png, record):
    """Decode actual public bytes in Pillow and check them against independent evidence."""
    from PIL import Image

    with Image.open(io.BytesIO(png), formats=("PNG",)) as image:
        public = np.asarray(image.convert("RGBA"))
    meta, expected = record["metadata"], record["expected"]
    checks = dict(record["native_checks"])
    checks["png_dimensions"] = public.shape == (SIZE, 2 * SIZE, 4)
    checks["binding"] = (
        meta["target_ids"] == expected["target_ids"] and meta["frame_id"] == expected["frame_id"]
        and meta["mode"] == expected["mode"] and meta["method"] == "active"
        and meta["meters_per_blender_unit"] == expected["scale_length"]
        and sorted(meta["mesh_ids"]) == sorted(record["mesh_ids"][1:])
        and meta["witness"] == {**expected["witness"], "status": expected["status"]}
    )
    probes = meta["selection"]["probes"]
    calls = record["trace"]
    checks["native_ray_accounting"] = (
        len(calls) == record["ray_count"] == meta["selection"]["ray_count"]
        == sum(probe["ray_count"] for probe in probes)
        and record["selected_rays"] == sum(call["candidate"] == record["candidate"] for call in calls)
    )
    grid, detail = {}, {}
    if checks["png_dimensions"]:
        palette = _palette(record)
        for panel, side in enumerate(("global", "local")):
            grid[side] = _score_grid(public, record["grid"][side], palette,
                                     record["witness_pixels"][side], panel)
            checks[side + "_image_rays"] = grid[side]["passed"]
        sample_checks, detail = _score_samples(public, palette, record)
        checks.update(sample_checks)
    passed = bool(all(checks.values()))
    return {
        "passed": passed, "pixel_success": bool(passed and expected["witness"]["distance_m"] > 0),
        "safe": bool(passed and record["native_stop"]), "checks": checks, "grid": grid,
        "png_sha256": sha256(png).hexdigest(), **detail,
    }


def _erase_witness(png):
    from PIL import Image

    with Image.open(io.BytesIO(png), formats=("PNG",)) as image:
        forged = image.convert("RGB")
        forged.paste((0, 0, 0), (SIZE + 200, 200, SIZE + 312, 312))
        buffer = io.BytesIO()
        forged.save(buffer, format="PNG")
    return buffer.getvalue()


def _read_exact(stream, length):
    data = stream.read(length)
    if len(data) != length:
        raise EOFError("truncated CF visual worker message")
    return data


class PillowWorker:
    """Run the independent scorer under the project's venv without staging bottom images."""

    def __init__(self, python_exe):
        self.python_exe = os.fspath(python_exe)
        self.process = None

    def __enter__(self):
        self.process = subprocess.Popen(
            (self.python_exe, "-B", os.fspath(Path(__file__).resolve()), "--worker"),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return self

    def score(self, png, record, *, erase=False):
        meta = json.dumps({"record": record, "erase": erase}, allow_nan=False,
                          separators=(",", ":")).encode()
        self.process.stdin.write(_HEADER.pack(len(meta), len(png)))
        self.process.stdin.write(meta)
        self.process.stdin.write(png)
        self.process.stdin.flush()
        size, _ = _HEADER.unpack(_read_exact(self.process.stdout, _HEADER.size))
        return json.loads(_read_exact(self.process.stdout, size))

    def __exit__(self, exc_type, exc, traceback):
        self.process.stdin.close()
        self.process.stdout.close()
        result = self.process.wait()
        if result and exc_type is None:
            raise RuntimeError(f"CF Pillow worker exited with status {result}")


def _worker():
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    while header := stdin.read(_HEADER.size):
        meta_size, png_size = _HEADER.unpack(header)
        request = json.loads(_read_exact(stdin, meta_size))
        png = _read_exact(stdin, png_size)
        if request["erase"]:
            png = _erase_witness(png)
        response = json.dumps(score_png(png, request["record"]), allow_nan=False,
                              separators=(",", ":")).encode()
        stdout.write(_HEADER.pack(len(response), 0))
        stdout.write(response)
        stdout.flush()


def negative_controls(renderer, prepared, audit, scorer, observation, record, *, out=None):
    """Reject independent metadata, ray, pixel, and actual shader-plane forgeries."""
    if audit.mode != "SECTION":
        raise ValueError("the predeclared SECTION positive supplies both clip counterexamples")
    results = {}
    for label, key, value, check in (
        ("wrong_frame", "frame_id", audit.frame_id + 1, "binding"),
        ("wrong_object_order", "target_ids", list(reversed(audit.targets)), "binding"),
        ("wrong_ray_count", "selection",
         {**record["metadata"]["selection"], "ray_count": record["ray_count"] + 1},
         "native_ray_accounting"),
    ):
        forged = {**record, "metadata": {**record["metadata"], key: value}}
        results[label] = scorer.score(observation.png, forged)
        assert not results[label]["checks"][check] and not results[label]["passed"]
    results["erased_witness"] = scorer.score(observation.png, record, erase=True)
    assert not results["erased_witness"]["passed"]
    for label, invalid in (("missing_direction", ORDER[:-1]), ("duplicate_direction", (0, *ORDER[:-1])),
                           ("out_of_range_direction", (*ORDER[:-1], 16))):
        try:
            observe(renderer, prepared, audit, rank_directions=lambda _: invalid)
        except ValueError:
            results[label] = {"rejected": True}
        else:
            raise AssertionError(f"accepted invalid order {label}")
    section = observation.metadata["section"]
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
    from mathutils import Vector

    for label, panel in (("wrong_global_cut", 0), ("missing_local_cut", SIZE)):
        surface = renderer._surface

        def forged_surface(prepared, matrix, x, point, normal):
            if x == panel:
                if panel == 0:
                    point, normal = Vector(section["point_m"]), Vector(section["normal"])
                else:
                    point = normal = (0., 0., 0.)
            return surface(prepared, matrix, x, point, normal)

        renderer._surface = forged_surface
        try:
            wrong, evidence = observe(renderer, prepared, audit,
                                      rank_directions=lambda _: tuple(record["order"]))
        finally:
            del renderer._surface
        results[label] = scorer.score(wrong.png, evidence)
        side = "global" if panel == 0 else "local"
        assert not results[label]["grid"][side]["passed"] and not results[label]["passed"]
        if out is not None:
            (out / f"{label}.png").write_bytes(wrong.png)
            (out / f"{label}.json").write_text(json.dumps(evidence, allow_nan=False), encoding="utf-8")
    return results


if __name__ == "__main__" and sys.argv[1:] == ["--worker"]:
    _worker()
