"""M3 BVH correctness, work-funnel, memory, and latency benchmark suite.

Usage:
    python -B benchmarks/bvh_eval.py --save-baseline benchmarks/baseline_032.json
    python -B benchmarks/bvh_eval.py --compare benchmarks/baseline_032.json
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import gc
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys
import time
import tracemalloc
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import surface_geometry as sg
from human_eye_plugin import surface_proximity as sp
from human_eye_plugin.blender_host import _acquisition_lower, _acquisition_upper, _digest
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.scene_cache import SpatialSceneCache
from human_eye_plugin.surface_scan import surface_scan_result
from human_eye_plugin.task_query import surface_nearest_result
from verification import m3_asset_cases as asset_cases
from verification import test_surface_geometry as tsg
from verification.m3_pair_scalability_001.testing import witness_oracle


NOOP = lambda _stage: None
SNAPSHOT_PATH = ROOT / "verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json"
ORACLE_PATH = ROOT / "verification/spatial_task_qualification_001/oracle/formal_replay_01/ORACLE.json"
SCALABILITY_CASES_PATH = ROOT / "verification/m3_pair_scalability_001/testing/DESIGNED_CASES.json"
SUFFICIENT_CASES_PATH = ROOT / "verification/m3_sufficient_separation_001/testing/DESIGNED_CASES.json"


def _triangulate(faces):
    tris = []
    for f in faces:
        if len(f) == 3:
            tris.append(tuple(int(i) for i in f))
        elif len(f) == 4:
            tris.append((int(f[0]), int(f[1]), int(f[2])))
            tris.append((int(f[0]), int(f[2]), int(f[3])))
        else:
            for k in range(1, len(f) - 1):
                tris.append((int(f[0]), int(f[k]), int(f[k + 1])))
    return tris


def _make_mesh(oid, vertices, faces):
    verts = [[float(c) for c in p] for p in vertices]
    tris = _triangulate(faces)
    return SimpleNamespace(object_id=oid, name=oid, vertices=verts, faces=tris)


def _make_entity(oid, vertices, faces):
    verts = np.asarray(vertices, dtype=np.float64)
    tris = np.asarray(_triangulate(faces), dtype=np.int64)
    return MeshEntity3D(
        oid, oid, oid, verts, tris, None, (128, 128, 128), False,
        local_axes=np.eye(3), pivot_world=np.zeros(3),
        axes_source="bench", axes_confidence="explicit", axes_reason="bench",
    )


def _translate_verts(vertices, offset):
    dx, dy, dz = offset
    return [[v[0] + dx, v[1] + dy, v[2] + dz] for v in vertices]


def _rotate_z_verts(vertices, angle_rad):
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return [[c * v[0] - s * v[1], s * v[0] + c * v[1], v[2]] for v in vertices]


def _icosphere_like(radius, subdiv_rings=8, sectors=12, center=(0.0, 0.0, 0.0)):
    """Closed triangle sphere with non-trivial curved topology."""
    cx, cy, cz = center
    verts = [[cx, cy, cz + radius]]
    for i in range(1, subdiv_rings):
        phi = math.pi * i / subdiv_rings
        sp_v, cp_v = math.sin(phi), math.cos(phi)
        for j in range(sectors):
            theta = 2.0 * math.pi * j / sectors
            verts.append([cx + radius * sp_v * math.cos(theta),
                          cy + radius * sp_v * math.sin(theta),
                          cz + radius * cp_v])
    verts.append([cx, cy, cz - radius])
    faces = []
    # Top cap
    for j in range(sectors):
        faces.append([0, 1 + j, 1 + (j + 1) % sectors])
    # Middle bands
    for i in range(subdiv_rings - 2):
        r0 = 1 + i * sectors
        r1 = 1 + (i + 1) * sectors
        for j in range(sectors):
            jn = (j + 1) % sectors
            faces.append([r0 + j, r1 + j, r1 + jn])
            faces.append([r0 + j, r1 + jn, r0 + jn])
    # Bottom cap
    bottom = len(verts) - 1
    r_last = 1 + (subdiv_rings - 2) * sectors
    for j in range(sectors):
        faces.append([r_last + j, bottom, r_last + (j + 1) % sectors])
    return verts, faces


def _d48_sleeve_target():
    """60-face non-convex L-bracket/sleeve with wide enclosing AABB (gap=0 to inner peers)."""
    # Build a 16-segment L-channel / C-sleeve prism (~60 triangles)
    profile = [
        (0.0, 0.0), (1.0, 0.0), (1.0, 0.15), (0.15, 0.15),
        (0.15, 0.85), (1.0, 0.85), (1.0, 1.0), (0.0, 1.0),
    ]
    # Subdivide edges to hit ~60 triangles cleanly
    verts = []
    n = len(profile)
    layers = 3
    for iz in range(layers + 1):
        z = iz * (1.0 / layers)
        for x, y in profile:
            verts.append([x, y, z])
    faces = []
    for iz in range(layers):
        for i in range(n):
            inext = (i + 1) % n
            a = iz * n + i
            b = iz * n + inext
            c = (iz + 1) * n + inext
            d = (iz + 1) * n + i
            faces.append([a, b, c])
            faces.append([a, c, d])
    # Add end triangles (simple fan strips on thick bars so vertex/face count ~60)
    # 3 * 8 * 2 = 48 side tris + 12 cap tris = 60 tris
    # Cap bottom z=0 (6 tris covering C-shape) and top z=1 (6 tris)
    # 0..7 on bottom: (0,1,2), (0,2,3), (0,3,4), (0,4,7), (4,5,6), (4,6,7)
    for tri in ((0, 2, 1), (0, 3, 2), (0, 4, 3), (0, 7, 4), (4, 6, 5), (4, 7, 6)):
        faces.append(list(tri))
    top = layers * n
    for tri in ((0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 7), (4, 6, 5), (4, 7, 6)):
        faces.append([top + idx for idx in tri])
    return _make_mesh("D48_Target", verts, faces)


def _d48_peer(idx):
    """60-face closed curved mesh overlapping Target's AABB [0,1]^3 at varied distances."""
    # Place inside C-cavity [0.22..0.95] x [0.22..0.78] x [0.1..0.9] -> object AABB gap = 0!
    rng = random.Random(48000 + idx)
    radius = 0.06 + 0.04 * (idx % 5) / 4.0
    # Ensure minimum distance ~0.003 at idx=0 and varied gaps up to ~0.35
    if idx == 0:
        cx, cy, cz = 0.15 + radius + 0.003, 0.50, 0.50
    else:
        cx = rng.uniform(0.25 + radius, 0.90 - radius)
        cy = rng.uniform(0.25 + radius, 0.75 - radius)
        cz = rng.uniform(0.15 + radius, 0.85 - radius)
    verts, faces = _icosphere_like(radius, subdiv_rings=5, sectors=6, center=(0.0, 0.0, 0.0))
    verts = _rotate_z_verts(verts, 0.37 * idx)
    verts = _translate_verts(verts, (cx, cy, cz))
    return _make_mesh(f"D48_Peer_{idx:03d}", verts, faces)


def _load_snapshot():
    snap = json.loads(SNAPSHOT_PATH.read_bytes())
    return {row["name"]: row for row in snap["objects"]}


def _snapshot_mesh(row):
    return _make_mesh(row["name"], row["vertices_world"], row["triangles"])


def build_workloads(quick=False):
    objects = _load_snapshot()
    g_target = _snapshot_mesh(objects["Target"])
    g_peer = _snapshot_mesh(objects["Peer_000"])
    g_comp = _snapshot_mesh(objects["Competing_001"])
    g_near3 = _snapshot_mesh(objects["Near_003"])
    g_all_peers = [
        _snapshot_mesh(objects[name])
        for name in ["Peer_000", "Competing_001"] + [f"Near_{k:03d}" for k in range(3, 12)]
    ]
    ctrl_a = _snapshot_mesh(objects["Control_A"])
    ctrl_b = _snapshot_mesh(objects["Control_B"])

    # Analytic coiled tubes (28 rings x 12 sides -> 672 quads? No: 27*12*2 + 2*(10) = 668 tris per mesh)
    tv1, tf1 = asset_cases.tube(28, 12, 0.08)
    tube_a = _make_mesh("tube_a", tv1, tf1)
    tube_b = _make_mesh("tube_b", _translate_verts(tv1, (0.04, 0.0, 0.015)), tf1)

    # Parallel sheets 5um gap (n=17 -> 512 tris per side)
    sv, sf = asset_cases.sheet(17, parallel_gap=None)
    sheet_a = _make_mesh("sheet_a", sv, sf)
    sheet_b = _make_mesh("sheet_b", _translate_verts(sv, (0.0, 0.0, 5e-6)), sf)

    # Dented sheet vs flat reference (n=17 -> 512 tris per side)
    dv, df = asset_cases.sheet(17, dent=0.002)
    dent_a = _make_mesh("dent_a", dv, df)
    dent_b = _make_mesh("dent_b", _translate_verts(sv, (0.0, 0.0, 0.005)), sf)

    # Rotated 30deg overlapping boxes / spheres (768F vs 768F or 240F vs 240F)
    rv1, rf1 = _icosphere_like(0.25, subdiv_rings=10, sectors=12, center=(0.0, 0.0, 0.0))
    rv2, rf2 = _icosphere_like(0.25, subdiv_rings=10, sectors=12, center=(0.0, 0.0, 0.0))
    rot_a = _make_mesh("rot_a", _rotate_z_verts(rv1, math.radians(30)), rf1)
    rot_b = _make_mesh("rot_b", _translate_verts(_rotate_z_verts(rv2, math.radians(30)), (0.52, 0.0, 0.02)), rf2)

    # Large shift 2**30 + small scale 2**-20
    scale_small = math.ldexp(1.0, -20)
    shift_big = 2.0 ** 30
    ls_v1 = [[shift_big + p[0] * scale_small, shift_big + p[1] * scale_small, shift_big + p[2] * scale_small]
             for p in objects["Near_003"]["vertices_world"]]
    ls_v2 = [[shift_big + (p[0] + 0.05) * scale_small, shift_big + p[1] * scale_small, shift_big + p[2] * scale_small]
             for p in objects["Near_003"]["vertices_world"]]
    large_shift_a = _make_mesh("ls_a", ls_v1, objects["Near_003"]["triangles"])
    large_shift_b = _make_mesh("ls_b", ls_v2, objects["Near_003"]["triangles"])

    # High-res pair (~1500F vs ~1500F -> 3000F <= 4096)
    hv1, hf1 = _icosphere_like(0.4, subdiv_rings=25, sectors=32, center=(0.0, 0.0, 0.0))
    hv2, hf2 = _icosphere_like(0.4, subdiv_rings=25, sectors=32, center=(0.85, 0.05, 0.02))
    hi_a = _make_mesh("hi_a", hv1, hf1)
    hi_b = _make_mesh("hi_b", hv2, hf2)

    # D48 synthetic 47-pair set
    d48_target = _d48_sleeve_target()
    d48_peers = [_d48_peer(i) for i in range(12 if quick else 47)]

    # Closed solid meshes
    cv1, cf1 = _icosphere_like(0.20, subdiv_rings=9, sectors=14, center=(0.0, 0.0, 0.0))
    cv2, cf2 = _icosphere_like(0.20, subdiv_rings=9, sectors=14, center=(0.45, 0.0, 0.0))
    closed_a = _make_mesh("closed_a", cv1, cf1)
    closed_b = _make_mesh("closed_b", cv2, cf2)

    # Self-intersection analyze mesh (~668F)
    analyze_tris = [list(tri) for tri in tube_a.faces]
    analyze_raw = tsg.prepared(tube_a.vertices, analyze_tris)

    return {
        "surface_single": [
            ("G508_Control_12F", ctrl_a, ctrl_b),
            ("G508_Competing_001", g_target, g_comp),
            ("G508_Near_003", g_target, g_near3),
            ("G508_Peer_000", g_target, g_peer),
            ("Tube_Coiled_Loose", tube_a, tube_b),
            ("Sheet_Parallel_5um", sheet_a, sheet_b),
            ("Sheet_Dented_2mm", dent_a, dent_b),
            ("Rotated_30deg_Spheres", rot_a, rot_b),
            ("LargeShift_2pow30", large_shift_a, large_shift_b),
            ("HighRes_1536F_Pair", hi_a, hi_b),
        ],
        "surface_batch": [
            ("G508_Target_vs_All11", g_target, g_all_peers),
            ("D48_Sim_47pairs" if not quick else "D48_Sim_12pairs", d48_target, d48_peers),
        ],
        "spatial_relation": [
            ("Spatial_G508_Peer_000", g_target, g_peer),
            ("Spatial_G508_Competing", g_target, g_comp),
            ("Spatial_G508_Near_003", g_target, g_near3),
            ("Spatial_Control_12F", ctrl_a, ctrl_b),
        ],
        "closed_solid": [
            ("Closed_Spheres_224F", closed_a, closed_b),
            ("Closed_G508_Control", ctrl_a, ctrl_b),
        ],
        "surface_analyze": [
            ("Analyze_Tube_668F", analyze_raw, analyze_tris),
        ],
        "g508_objects": objects,
    }


def _build_nearest_packet(meshes):
    identity = runtime_identity()
    host_sha = next(row["sha256"] for row in identity["source_files"]
                    if row["path"] == "human_eye_plugin/blender_host.py")
    focal = meshes[0].object_id
    rows = []
    for m in meshes:
        verts = m.vertices
        lo = [min(float(p[k]) for p in verts) for k in range(3)]
        hi = [max(float(p[k]) for p in verts) for k in range(3)]
        tri = m.faces[0]
        tri_pts = [[float(c) for c in verts[idx]] for idx in tri]
        rows.append({
            "object_id": m.object_id,
            "name": m.name,
            "bounds_world_m": [lo, hi],
            "bounds_status": "enclosed",
            "witness": {
                "triangle_world_m": tri_pts,
                "triangle_vertex_indices": [int(i) for i in tri],
                "point_world_m": tri_pts[0],
            },
        })
    focal_w = rows[0]["witness"]["triangle_world_m"]
    upper, seed = math.inf, None
    for row in rows[1:]:
        for pa in focal_w:
            for pb in row["witness"]["triangle_world_m"]:
                d = _acquisition_upper(pa, pb)
                if d < upper:
                    upper, seed = d, row["object_id"]
    retained = []
    for row in rows:
        lower = _acquisition_lower(rows[0]["bounds_world_m"], row["bounds_world_m"])
        excluded = row["object_id"] not in (focal, seed) and lower > upper
        row["lower_bound_m"] = lower
        row["disposition"] = "excluded_strict_bound" if excluded else "retained"
        if not excluded:
            retained.append(row["object_id"])
    retained_set = set(retained)
    full_id = {
        "schema_version": "1.0",
        "capture_scope": "complete_scene_meshes",
        "document_epoch": "bench-epoch-1",
        "object_instances": {m.object_id: "inst-" + m.object_id for m in meshes},
    }
    cap_id = dict(full_id, capture_scope="surface_nearest_candidates",
                  object_instances={k: v for k, v in full_id["object_instances"].items() if k in retained_set})
    capture = {
        "revision": "bench-r1",
        "unit": "m",
        "coordinate_frame": "world",
        "source": "blender",
        "capture_scope": "surface_nearest_candidates",
        "host_identity": cap_id,
        "meshes": [m.to_dict() for m in meshes if m.object_id in retained_set],
    }
    packet = {
        "protocol": "single-read-surface-candidates-v1",
        "result_kind": "acquisition_only_not_nearest_result",
        "scope": "independent_static_triangle_meshes_current_evaluated_surfaces",
        "M3_qualification_performed": False,
        "execution_authority": False,
        "focal_id": focal,
        "upper_seed_id": seed,
        "witness_upper_bound_m": upper if math.isfinite(upper) else None,
        "coverage": rows,
        "capture": capture,
        "binding": {
            "host_source_sha256": host_sha,
            "host_identity": full_id,
            "frame": 1,
            "scale_length": 1.0,
            "unit": "m",
            "coordinate_frame": "world",
            "same_main_thread_read": True,
            "directory_sha256": _digest(rows),
        },
    }
    return packet, meshes


def _build_scan_packet(meshes, threshold=0.005):
    from itertools import combinations
    identity = runtime_identity()
    host_sha = next(row["sha256"] for row in identity["source_files"]
                    if row["path"] == "human_eye_plugin/blender_host.py")
    rows = []
    for m in meshes:
        verts = m.vertices
        lo = [min(float(p[k]) for p in verts) for k in range(3)]
        hi = [max(float(p[k]) for p in verts) for k in range(3)]
        rows.append({
            "object_id": m.object_id,
            "name": m.name,
            "bounds_world_m": [lo, hi],
            "bounds_status": "enclosed",
            "source_status": "supported",
            "source_mode": "evaluated_static",
            "reason": None,
        })
    by_id = {r["object_id"]: r for r in rows}
    pairs, retained = [], set()
    for a, b in combinations(sorted(by_id), 2):
        lower = _acquisition_lower(by_id[a]["bounds_world_m"], by_id[b]["bounds_world_m"])
        disp = "excluded_strict_bound" if lower > threshold else "retained"
        pairs.append({"object_ids": [a, b], "lower_bound_m": lower, "disposition": disp})
        if disp == "retained":
            retained.update((a, b))
    full_id = {
        "schema_version": "1.0",
        "capture_scope": "complete_scene_meshes",
        "document_epoch": "bench-scan-epoch-1",
        "object_instances": {m.object_id: "inst-" + m.object_id for m in meshes},
    }
    cap_id = dict(full_id, capture_scope="surface_scan_candidates",
                  object_instances={k: v for k, v in full_id["object_instances"].items() if k in retained})
    capture = {
        "revision": "bench-scan-r1",
        "unit": "m",
        "coordinate_frame": "world",
        "source": "blender",
        "capture_scope": "surface_scan_candidates",
        "host_identity": cap_id,
        "meshes": [m.to_dict() for m in meshes if m.object_id in retained],
    }
    return {
        "protocol": "single-read-surface-scan-v1",
        "result_kind": "acquisition_only_not_surface_scan_result",
        "scope": "independent_static_triangle_meshes_current_evaluated_surfaces",
        "M3_qualification_performed": False,
        "execution_authority": False,
        "threshold_m": threshold,
        "coverage": rows,
        "pairs": pairs,
        "scope_issues": [],
        "capture": capture,
        "binding": {
            "host_source_sha256": host_sha,
            "host_identity": full_id,
            "frame": 1,
            "scale_length": 1.0,
            "unit": "m",
            "coordinate_frame": "world",
            "same_main_thread_read": True,
            "directory_sha256": _digest(rows),
        },
    }


def _surface_sig(res):
    return {
        "measurement_valid": res.get("measurement_valid"),
        "reason": res.get("reason"),
        "distance_m": res.get("distance_m"),
        "_exact_distance_sq": res.get("_exact_distance_sq"),
        "point_a_world": res.get("point_a_world"),
        "point_b_world": res.get("point_b_world"),
        "direction_a_to_b": res.get("direction_a_to_b"),
        "witness_status": res.get("witness_status"),
        "direction_status": res.get("direction_status"),
        "topology": res.get("topology"),
        "witness_triangle_indices": res.get("witness_triangle_indices"),
    }


def _work_summary(work):
    keys = (
        "work_units", "tree_builds", "tree_build_units",
        "node_pair_visits", "queue_pushes", "subtree_pruned_pairs",
        "leaf_pair_visits", "aabb_bound_tests", "aabb_pruned_pairs",
        "plane_bound_tests", "plane_pruned_pairs",
        "witness_projection_tests", "witness_projection_pruned_pairs",
        "witness_projection_credit_credit_deferrals",
        "narrow_phase_pairs", "intersection_tests",
        "point_face_tests", "point_edge_tests", "edge_edge_tests",
    )
    return {k: work.get(k, 0) for k in keys}


def _time_fn(fn, warmup, repeats, measure_mem=True):
    for _ in range(warmup):
        fn()
    gc.collect()
    gc.disable()
    times_ns = []
    try:
        for _ in range(repeats):
            t0 = time.perf_counter_ns()
            res = fn()
            times_ns.append(time.perf_counter_ns() - t0)
    finally:
        gc.enable()
    times_ms = sorted(t / 1e6 for t in times_ns)
    idx95 = min(len(times_ms) - 1, max(0, int(math.ceil(0.95 * len(times_ms))) - 1))
    peak_bytes = 0
    if measure_mem:
        tracemalloc.start()
        fn()
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return {
        "median_ms": statistics.median(times_ms),
        "p95_ms": times_ms[idx95],
        "min_ms": times_ms[0],
        "peak_alloc_bytes": peak_bytes,
    }, res


def run_correctness_gates(objects):
    """Verify exact equivalence against G508 oracle and analytic counterexamples."""
    oracle = json.loads(ORACLE_PATH.read_bytes())
    oracle_by_name = {row["candidate_name"]: row for row in oracle["pairs"]}
    target_row = objects["Target"]
    target_mesh = _snapshot_mesh(target_row)

    # 1. G508 exact oracle & witness membership proof
    for name in ("Peer_000", "Competing_001", "Near_003"):
        cand_row = objects[name]
        cand_mesh = _snapshot_mesh(cand_row)
        res = sp.measure_surface_proximity(target_mesh, cand_mesh, NOOP, retain_exact_rank=True, retain_witness_triangles=True)
        assert res["measurement_valid"] is True, (name, res)
        o_row = oracle_by_name[name]
        assert o_row["distance_lower_m"] - 1e-12 <= res["distance_m"] <= o_row["distance_upper_m"] + 1e-12, (name, res["distance_m"], o_row)
        proof = witness_oracle.certify_pair(
            res["point_a_world"], res["point_b_world"], res["distance_m"],
            target_row, cand_row, position_tolerance_m=1e-9, distance_tolerance_m=1e-6,
        )
        assert proof["passed"], (name, proof)

    # 2. Sufficient separation designed analytic pairs (all 14 cases)
    suf = json.loads(SUFFICIENT_CASES_PATH.read_bytes())
    for case in suf["analytic_pairs"]:
        l_raw, r_raw = case["left"], case["right"]
        left = _make_mesh("l", l_raw["vertices_world"], l_raw["triangles"])
        right = _make_mesh("r", r_raw["vertices_world"], r_raw["triangles"])
        res = sp.measure_spatial_relation(left, right, NOOP, retain_exact_rank=True)
        truth = case["independent_truth"]
        if truth.get("new_expected") == "unknown":
            assert res["spatial"]["measurement_valid"] is False, (case["id"], res)
        else:
            assert res["measurement_valid"] is True, (case["id"], res)
            assert res["spatial"]["relation"] == truth["relation"], (case["id"], res)

    # 3. Scalability designed cases: plane bounds, work boundaries, cancellation
    scal = json.loads(SCALABILITY_CASES_PATH.read_bytes())
    for name in ("cube12", "cube192_same_world_boundary"):
        l_raw, r_raw = scal[name]
        left = _make_mesh("l", l_raw.get("vertices_world", l_raw.get("vertices")), l_raw.get("triangles", l_raw.get("faces")))
        right = _make_mesh("r", r_raw.get("vertices_world", r_raw.get("vertices")), r_raw.get("triangles", r_raw.get("faces")))
        res = sp.measure_surface_proximity(left, right, NOOP, retain_exact_rank=True)
        assert res["measurement_valid"] is True and res["distance_m"] == 1.0, (name, res)

    # 4. Collaborative cancellation propagation must remain intact
    l_raw, r_raw = scal["cube192_same_world_boundary"]
    left = _make_mesh("l", l_raw.get("vertices_world", l_raw.get("vertices")), l_raw.get("triangles", l_raw.get("faces")))
    right = _make_mesh("r", r_raw.get("vertices_world", r_raw.get("vertices")), r_raw.get("triangles", r_raw.get("faces")))
    for stage in ("surface_proximity_surface_bvh_build", "surface_proximity_node_pair_visits", "surface_proximity_narrow_phase_pairs"):
        class _Cancelled(RuntimeError):
            pass
        def cp(s, target_stage=stage):
            if s == target_stage:
                raise _Cancelled(s)
        try:
            sp.measure_surface_proximity(left, right, cp)
        except _Cancelled:
            pass
        else:
            raise AssertionError(f"Checkpoint cancellation swallowed for {stage}")

    return {"g508_oracle": "pass", "analytic_pairs": len(suf["analytic_pairs"]), "scalability_controls": "pass"}


def run_benchmark(warmup=1, repeats=3, quick=False, measure_mem=True):
    workloads = build_workloads(quick=quick)
    gates = run_correctness_gates(workloads["g508_objects"])

    results = {
        "schema": "m3-bvh-eval-v1",
        "runtime_identity_sha256": runtime_identity()["source_sha256"],
        "gates": gates,
        "surface_single": {},
        "surface_batch": {},
        "spatial_relation": {},
        "closed_solid": {},
        "surface_analyze": {},
        "e2e_entries": {},
    }

    # 1. Single-pair surface proximity
    single_cases = workloads["surface_single"]
    if quick:
        keep = {"G508_Control_12F", "G508_Peer_000", "Tube_Coiled_Loose", "Sheet_Parallel_5um", "LargeShift_2pow30"}
        single_cases = [row for row in single_cases if row[0] in keep]
    for name, left, right in single_cases:
        print(f"  running {name}...", flush=True)
        timing, res = _time_fn(
            lambda l=left, r=right: sp.measure_surface_proximity(
                l, r, NOOP, retain_exact_rank=True, retain_witness_triangles=True
            ),
            warmup=warmup,
            repeats=repeats,
            measure_mem=measure_mem,
        )
        results["surface_single"][name] = {
            "timing": timing,
            "work": _work_summary(res["work"]),
            "signature": _surface_sig(res),
        }

    # 2. Batch 1-to-N surface proximity
    batch_cases = workloads["surface_batch"]
    if quick:
        batch_cases = [row for row in batch_cases if row[0].startswith("D48_Sim")]
    for name, target, peers in batch_cases:
        print(f"  running {name}...", flush=True)
        def run_batch(t=target, ps=peers):
            outs = []
            agg = {}
            for p in ps:
                r = sp.measure_surface_proximity(t, p, NOOP, retain_exact_rank=True)
                outs.append(r)
                for k, v in _work_summary(r["work"]).items():
                    agg[k] = agg.get(k, 0) + v
            return outs, agg
        timing, (outs, agg) = _time_fn(
            run_batch, warmup=warmup, repeats=max(1, repeats - 1) if quick else repeats, measure_mem=measure_mem
        )
        results["surface_batch"][name] = {
            "timing": timing,
            "work": agg,
            "signatures": [_surface_sig(r) for r in outs],
        }

    # 3. Spatial relation (surface + vertex support / closed fallback)
    spatial_cases = workloads["spatial_relation"]
    if quick:
        spatial_cases = [row for row in spatial_cases if row[0] in {"Spatial_G508_Peer_000", "Spatial_Control_12F"}]
    for name, left, right in spatial_cases:
        print(f"  running {name}...", flush=True)
        def run_sr(l=left, r=right):
            diag = {}
            res = sp.measure_spatial_relation(l, r, NOOP, diagnostics=diag, retain_exact_rank=True)
            return res, diag
        timing, (res, diag) = _time_fn(run_sr, warmup=warmup, repeats=repeats, measure_mem=measure_mem)
        results["spatial_relation"][name] = {
            "timing": timing,
            "work": _work_summary(res["surface"]["work"]),
            "relation": res["spatial"]["relation"],
            "certificate": res["spatial"].get("certificate"),
            "closed_calls": diag.get("closed_solid_pair_count", 0),
            "signature": _surface_sig(res["surface"]),
        }

    # 4. Closed solid BVH
    for name, left, right in workloads["closed_solid"]:
        print(f"  running {name}...", flush=True)
        timing, res = _time_fn(
            lambda l=left, r=right: sg.classify_closed_solids(l, r, NOOP),
            warmup=warmup,
            repeats=repeats,
            measure_mem=measure_mem,
        )
        results["closed_solid"][name] = {
            "timing": timing,
            "work": {k: res["work"].get(k, 0) for k in (
                "work_units", "node_pair_visits", "leaf_pair_visits", "aabb_pruned_pairs",
                "self_pair_tests", "cross_pair_tests", "ray_tests",
                "strict_plane_rejections", "simplex_node_certificates", "simplex_covered_pairs",
            )},
            "signature": {
                "measurement_valid": res.get("measurement_valid"),
                "relation": res.get("relation"),
                "certificate": res.get("certificate"),
                "reason": res.get("reason"),
            },
        }

    # 5. Surface analyze (self-intersection BVH)
    for name, prep, faces in workloads["surface_analyze"]:
        print(f"  running {name}...", flush=True)
        def run_an(p=prep, f=faces):
            from human_eye_plugin import mesh_structure as ms
            return sg.analyze(p, f, list(range(len(f))), budget=ms.WorkBudget(), near_m=0.0)
        timing, res = _time_fn(run_an, warmup=warmup, repeats=repeats, measure_mem=measure_mem)
        results["surface_analyze"][name] = {
            "timing": timing,
            "work": res.get("spatial_work", {}),
            "signature": {
                "status": res.get("status"),
                "total": res.get("total"),
                "exact_pair_tests": res.get("exact_pair_tests"),
                "counts_by_relation": res.get("counts_by_relation"),
            },
        }

    # 6. End-to-end surface_nearest_result & surface_scan_result (cold cache per run)
    if not quick:
        objects = workloads["g508_objects"]
        g_entities = [_make_entity(name, objects[name]["vertices_world"], objects[name]["triangles"])
                      for name in ["Target", "Peer_000", "Competing_001"] + [f"Near_{k:03d}" for k in range(3, 12)]]
        nearest_packet, _ = _build_nearest_packet(g_entities)
        scan_packet = _build_scan_packet(g_entities, threshold=0.005)

        def run_nearest():
            diag = {}
            out = surface_nearest_result(nearest_packet, SpatialSceneCache(), NOOP, diagnostics=diag)
            return out, diag

        def run_scan():
            diag = {}
            out = surface_scan_result(scan_packet, SpatialSceneCache(), NOOP, diagnostics=diag)
            return out, diag

        print("  running G508_surface_nearest...", flush=True)
        t_near, (out_near, diag_near) = _time_fn(run_nearest, warmup=warmup, repeats=repeats, measure_mem=measure_mem)
        results["e2e_entries"]["G508_surface_nearest"] = {
            "timing": t_near,
            "work": {"kernel_calls": diag_near["kernel_calls"], "pair_calls": diag_near["pair_calls"]},
            "signature": {
                "status": out_near["status"],
                "nearest_ids": out_near["nearest_ids"],
                "distance_m": out_near["distance_m"],
                "coverage": out_near["coverage"],
            },
        }

        print("  running G508_surface_scan_5mm...", flush=True)
        t_scan, (out_scan, diag_scan) = _time_fn(run_scan, warmup=warmup, repeats=repeats, measure_mem=measure_mem)
        results["e2e_entries"]["G508_surface_scan_5mm"] = {
            "timing": t_scan,
            "work": {"kernel_calls": diag_scan["kernel_calls"], "bound_excluded": out_scan["coverage"]["bound_excluded"]},
            "signature": {
                "status": out_scan["status"],
                "coverage": out_scan["coverage"],
                "match_ids": [[o["id"] for o in m["objects"]] for m in out_scan["matches"]],
            },
        }

    return results


def _compare_signatures(baseline, current, partial=False):
    mismatches = []
    for section in ("surface_single", "spatial_relation", "closed_solid", "surface_analyze", "e2e_entries"):
        for name, c_row in current[section].items():
            b_row = baseline[section].get(name)
            if b_row is None:
                continue
            b_sig = b_row["signature"] if "signature" in b_row else {"relation": b_row["relation"], "certificate": b_row["certificate"]}
            c_sig = c_row["signature"] if "signature" in c_row else {"relation": c_row["relation"], "certificate": c_row["certificate"]}
            if b_sig != c_sig:
                mismatches.append(f"signature mismatch in {section}.{name}:\n  baseline={b_sig}\n  current ={c_sig}")
        if not partial:
            for name in baseline[section]:
                if name not in current[section]:
                    mismatches.append(f"missing {section}.{name}")
    for name, c_row in current["surface_batch"].items():
        b_row = baseline["surface_batch"].get(name)
        if b_row is None:
            continue
        if b_row["signatures"] != c_row["signatures"]:
            for idx, (bs, cs) in enumerate(zip(b_row["signatures"], c_row["signatures"])):
                if bs != cs:
                    mismatches.append(f"signature mismatch in surface_batch.{name}[{idx}]:\n  baseline={bs}\n  current ={cs}")
                    break
    if not partial:
        for name in baseline["surface_batch"]:
            if name not in current["surface_batch"]:
                mismatches.append(f"missing surface_batch.{name}")
    return mismatches


def print_report(results, baseline=None):
    print(f"=== M3 BVH Eval (source_sha={results['runtime_identity_sha256'][:12]}) ===")
    print("Correctness gates:", results["gates"])
    print()

    def fmt_row(name, cur, base=None):
        t = cur["timing"]
        w = cur["work"]
        med = t["median_ms"]
        p95 = t["p95_ms"]
        mem_kib = t["peak_alloc_bytes"] / 1024.0
        narrow = w.get("narrow_phase_pairs", w.get("pair_calls", w.get("exact_pair_tests", w.get("kernel_calls", 0))))
        nodes = w.get("node_pair_visits", 0)
        leaves = w.get("leaf_pair_visits", 0)
        units = w.get("work_units", 0)
        if base is None:
            return (f"{name:<24} | med={med:8.3f}ms p95={p95:8.3f}ms | mem={mem_kib:7.1f}KiB | "
                    f"nodes={nodes:7d} leaves={leaves:7d} narrow={narrow:6d} work={units:8d}")
        b_med = base["timing"]["median_ms"]
        speedup = b_med / med if med > 0 else float("inf")
        pct = (1.0 - med / b_med) * 100.0 if b_med > 0 else 0.0
        b_narrow = base["work"].get("narrow_phase_pairs", base["work"].get("pair_calls", base["work"].get("exact_pair_tests", base["work"].get("kernel_calls", 0))))
        return (f"{name:<24} | {b_med:8.3f} -> {med:8.3f}ms ({pct:+6.2f}%, {speedup:5.2f}x) | "
                f"narrow {b_narrow:6d}->{narrow:6d} | nodes {base['work'].get('node_pair_visits',0):6d}->{nodes:6d} | "
                f"leaves {base['work'].get('leaf_pair_visits',0):7d}->{leaves:7d}")

    for section in ("surface_single", "surface_batch", "spatial_relation", "closed_solid", "surface_analyze", "e2e_entries"):
        print(f"--- {section} ---")
        for name, cur in results[section].items():
            base = baseline[section].get(name) if baseline else None
            print(fmt_row(name, cur, base))
        print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--no-mem", action="store_true")
    parser.add_argument("--save-baseline", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()

    results = run_benchmark(
        warmup=args.warmup, repeats=args.repeats, quick=args.quick, measure_mem=not (args.no_mem or args.quick)
    )
    baseline = None
    if args.compare is not None:
        baseline = json.loads(args.compare.read_bytes())

    print_report(results, baseline=baseline)

    if args.save_baseline is not None:
        args.save_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.save_baseline.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf8")
        print(f"Saved baseline to {args.save_baseline}")

    if baseline is not None:
        mismatches = _compare_signatures(baseline, results, partial=args.quick)
        if mismatches:
            print("EQUIVALENCE CHECK FAILED:")
            for msg in mismatches:
                print(msg)
            raise SystemExit(1)
        print("EQUIVALENCE CHECK PASSED: all exact distance keys, witnesses, relations, and entries match baseline.")


if __name__ == "__main__":
    main()
