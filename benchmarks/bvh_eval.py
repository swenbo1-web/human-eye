"""M3 BVH correctness, work-funnel, memory, and latency benchmark suite.

Usage:
    python -B benchmarks/bvh_eval.py --save-baseline benchmarks/baseline_032.json
    python -B benchmarks/bvh_eval.py --compare benchmarks/baseline_032.json
"""
from __future__ import annotations

import argparse
import copy
from fractions import Fraction
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
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


def _stable_hash(obj):
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(raw).hexdigest()


def _mesh_sha256(mesh):
    return _stable_hash({
        "object_id": getattr(mesh, "object_id", None),
        "vertices": [[float(c) for c in p] for p in mesh.vertices],
        "faces": [[int(i) for i in f] for f in mesh.faces],
    })


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
        "witness_reason": res.get("witness_reason"),
        "direction_status": res.get("direction_status"),
        "direction_reason": res.get("direction_reason"),
        "topology": res.get("topology"),
        "witness_triangle_indices": res.get("witness_triangle_indices"),
        "exact_witness_triangles": res.get("exact_witness_triangles"),
    }


def _spatial_sig(res):
    spatial = res.get("spatial") or {}
    return {
        "spatial": {
            "measurement_valid": spatial.get("measurement_valid"),
            "relation": spatial.get("relation"),
            "certificate": spatial.get("certificate"),
            "reason": spatial.get("reason"),
        },
        "surface": _surface_sig(res.get("surface") or {}),
    }


def _closed_sig(res):
    return {k: copy.deepcopy(v) for k, v in res.items() if k != "work"}


def _analyze_sig(res):
    ignored = {"spatial_work", "work", "exact_pair_tests", "work_used"}
    out = {k: copy.deepcopy(v) for k, v in res.items() if k not in ignored}
    out["complete"] = (res.get("status") == "complete")
    return out


def _nearest_sig(out):
    ignored = {"binding"}
    return {k: copy.deepcopy(v) for k, v in out.items() if k not in ignored}


def _scan_sig(out, diag):
    ignored = {"binding"}
    sig = {k: copy.deepcopy(v) for k, v in out.items() if k not in ignored}
    disps = sorted(
        copy.deepcopy(diag.get("dispositions", [])),
        key=lambda row: tuple(row.get("object_ids") or ()),
    )
    sig["dispositions"] = disps
    return sig


def _work_summary(work):
    keys = (
        "work_units", "validated_faces", "referenced_vertices", "prepared_triangles",
        "tree_builds", "tree_build_units",
        "node_pair_visits", "queue_pushes", "subtree_pruned_pairs",
        "leaf_pair_visits", "aabb_bound_tests", "aabb_pruned_pairs",
        "plane_bound_tests", "plane_pruned_pairs",
        "witness_projection_tests", "witness_projection_pruned_pairs",
        "witness_projection_direction_builds", "witness_projection_directions",
        "witness_projection_invalidations", "witness_projection_budget_deferrals",
        "witness_projection_credit_credit_deferrals",
        "mesh_cache_hits", "mesh_cache_misses", "mesh_cache_tree_builds",
        "mesh_cache_tree_build_units", "mesh_cache_tree_reuses",
        "mesh_cache_translate_units", "mesh_cache_fallbacks",
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
    res = None
    try:
        for _ in range(repeats):
            t0 = time.perf_counter_ns()
            res = fn()
            times_ns.append(time.perf_counter_ns() - t0)
    finally:
        gc.enable()
    raw_ms = [t / 1e6 for t in times_ns]
    times_ms = sorted(raw_ms)
    n = len(times_ms)
    idx95 = min(n - 1, max(0, int(math.ceil(0.95 * n)) - 1))
    q1 = times_ms[n // 4] if n else 0.0
    q3 = times_ms[(3 * n) // 4] if n else 0.0
    cpu_time_ms = 0.0
    peak_bytes = 0
    if measure_mem:
        # Separate instrumentation pass so tracemalloc/process_time never pollute timed wall runs.
        c0 = time.process_time_ns()
        fn()
        cpu_time_ms = (time.process_time_ns() - c0) / 1e6
        tracemalloc.start()
        fn()
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return {
        "raw_samples_ms": raw_ms,
        "median_ms": statistics.median(times_ms),
        "min_ms": times_ms[0],
        "max_ms": times_ms[-1],
        "iqr_ms": q3 - q1,
        "p95_ms": times_ms[idx95],
        "p95_note": "p95_nearest_rank" if n >= 30 else f"empirical_max_of_{n}_samples",
        "cpu_time_ms": cpu_time_ms,
        "peak_alloc_bytes": peak_bytes,
    }, res


def run_correctness_gates(objects):
    """Verify exact equivalence against G508 oracle, analytic counterexamples, and boundaries."""
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
            if "certificate" in truth:
                assert res["spatial"].get("certificate") == truth["certificate"], (case["id"], res)
            if "distance_m" in truth:
                assert math.isclose(res["surface"]["distance_m"], truth["distance_m"], rel_tol=0.0, abs_tol=1e-9), (case["id"], res)

    # 3. Scalability designed cases: plane bounds, work boundaries, static limits, cancellation
    scal = json.loads(SCALABILITY_CASES_PATH.read_bytes())
    for name in ("cube12", "cube192_same_world_boundary"):
        l_raw, r_raw = scal[name]
        left = _make_mesh("l", l_raw.get("vertices_world", l_raw.get("vertices")), l_raw.get("triangles", l_raw.get("faces")))
        right = _make_mesh("r", r_raw.get("vertices_world", r_raw.get("vertices")), r_raw.get("triangles", r_raw.get("faces")))
        res = sp.measure_surface_proximity(left, right, NOOP, retain_exact_rank=True)
        assert res["measurement_valid"] is True and res["distance_m"] == 1.0, (name, res)

    # 3b. Work & static face boundaries
    work = sp._Work(NOOP, {})
    work.counts["work_units"] = sp.MAX_WORK_UNITS - 1
    work.consume(1, "gate_boundary")
    assert work.counts["work_units"] == sp.MAX_WORK_UNITS
    try:
        work.consume(1, "gate_boundary")
    except sp._DomainError as exc:
        assert str(exc) == "surface_work_budget"
    else:
        raise AssertionError("work budget limit did not refuse over-budget unit")

    over_a = _make_mesh("oa", [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [[0, 1, 2]] * sp.MAX_FACES)
    over_b = _make_mesh("ob", [[2.0, 0.0, 0.0], [3.0, 0.0, 0.0], [2.0, 1.0, 0.0]], [[0, 1, 2]])
    over_res = sp.measure_surface_proximity(over_a, over_b, NOOP)
    assert over_res["measurement_valid"] is False and over_res.get("reason") == "surface_geometry_work_limit", over_res

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


def _file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_benchmark(warmup=1, repeats=3, quick=False, measure_mem=True):
    workloads = build_workloads(quick=quick)
    gates = run_correctness_gates(workloads["g508_objects"])

    results = {
        "schema": "m3-bvh-eval-v2",
        "runtime_identity_sha256": runtime_identity()["source_sha256"],
        "environment": {
            "python_version": sys.version.split()[0],
            "numpy_version": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "gc_policy": "collect_before_and_disable_during_timed_repeats",
            "warmup": warmup,
            "repeats": repeats,
            "quick": bool(quick),
            "measure_mem": bool(measure_mem),
        },
        "inputs_sha256": {
            "snapshot": _file_sha256(SNAPSHOT_PATH),
            "oracle": _file_sha256(ORACLE_PATH),
            "scalability_cases": _file_sha256(SCALABILITY_CASES_PATH),
            "sufficient_cases": _file_sha256(SUFFICIENT_CASES_PATH),
        },
        "solver_options": {
            "surface_single": {"retain_exact_rank": True, "retain_witness_triangles": True},
            "surface_batch": {"retain_exact_rank": True, "retain_witness_triangles": False},
            "spatial_relation": {"retain_exact_rank": True},
            "surface_analyze": {"near_m": 0.0},
        },
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
            "input_sha256": [_mesh_sha256(left), _mesh_sha256(right)],
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
            "input_sha256": [_mesh_sha256(target)] + [_mesh_sha256(p) for p in peers],
            "batch_ids": [p.object_id for p in peers],
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
            "input_sha256": [_mesh_sha256(left), _mesh_sha256(right)],
            "timing": timing,
            "work": _work_summary(res["surface"]["work"]),
            "relation": res["spatial"]["relation"],
            "certificate": res["spatial"].get("certificate"),
            "closed_calls": diag.get("closed_solid_pair_count", 0),
            "signature": _spatial_sig(res),
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
            "input_sha256": [_mesh_sha256(left), _mesh_sha256(right)],
            "timing": timing,
            "work": {k: res["work"].get(k, 0) for k in (
                "work_units", "node_pair_visits", "leaf_pair_visits", "aabb_pruned_pairs",
                "self_pair_tests", "cross_pair_tests", "ray_tests",
                "strict_plane_rejections", "simplex_node_certificates", "simplex_covered_pairs",
            )},
            "signature": _closed_sig(res),
        }

    # 5. Surface analyze (self-intersection BVH)
    for name, prep, faces in workloads["surface_analyze"]:
        print(f"  running {name}...", flush=True)
        def run_an(p=prep, f=faces):
            from human_eye_plugin import mesh_structure as ms
            return sg.analyze(p, f, list(range(len(f))), budget=ms.WorkBudget(), near_m=0.0)
        timing, res = _time_fn(run_an, warmup=warmup, repeats=repeats, measure_mem=measure_mem)
        an_work = dict(res.get("spatial_work", {}))
        an_work["exact_pair_tests"] = res.get("exact_pair_tests")
        if "work_used" in res:
            an_work["work_used"] = res.get("work_used")
        results["surface_analyze"][name] = {
            "input_sha256": _stable_hash({"faces": faces}),
            "timing": timing,
            "work": an_work,
            "signature": _analyze_sig(res),
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
            "input_sha256": _stable_hash(nearest_packet),
            "timing": t_near,
            "work": {"kernel_calls": diag_near["kernel_calls"], "pair_calls": diag_near["pair_calls"]},
            "signature": _nearest_sig(out_near),
        }

        print("  running G508_surface_scan_5mm...", flush=True)
        t_scan, (out_scan, diag_scan) = _time_fn(run_scan, warmup=warmup, repeats=repeats, measure_mem=measure_mem)
        results["e2e_entries"]["G508_surface_scan_5mm"] = {
            "input_sha256": _stable_hash(scan_packet),
            "timing": t_scan,
            "work": {"kernel_calls": diag_scan["kernel_calls"], "bound_excluded": out_scan["coverage"]["bound_excluded"]},
            "signature": _scan_sig(out_scan, diag_scan),
        }

    return results


def _canonical_row_sig(section, row):
    if section == "spatial_relation":
        sig = copy.deepcopy(row.get("signature"))
        if isinstance(sig, dict) and "spatial" in sig and "surface" in sig:
            if "relation" in row and row["relation"] != sig["spatial"].get("relation"):
                return {"_internal_inconsistency": ("relation", row["relation"], sig["spatial"].get("relation"))}
            if "certificate" in row and row["certificate"] != sig["spatial"].get("certificate"):
                return {"_internal_inconsistency": ("certificate", row["certificate"], sig["spatial"].get("certificate"))}
            return sig
        return {
            "spatial": {
                "relation": row.get("relation"),
                "certificate": row.get("certificate"),
            },
            "surface": sig,
        }
    return row["signature"]


def _compare_signatures(baseline, current, partial=False):
    mismatches = []
    if baseline.get("schema") != current.get("schema"):
        mismatches.append(f"schema mismatch: baseline={baseline.get('schema')} current={current.get('schema')}")
        return mismatches

    sections = ("surface_single", "spatial_relation", "closed_solid", "surface_analyze", "e2e_entries")
    for section in sections:
        if section not in baseline or section not in current:
            mismatches.append(f"missing section {section} in baseline or current")
            continue
        b_sec = baseline[section]
        c_sec = current[section]
        b_keys = set(b_sec)
        c_keys = set(c_sec)
        for extra in sorted(c_keys - b_keys):
            mismatches.append(f"extra candidate-only workload {section}.{extra}")
        if not partial:
            for missing in sorted(b_keys - c_keys):
                mismatches.append(f"missing baseline workload {section}.{missing}")
        for name in sorted(b_keys & c_keys):
            b_row, c_row = b_sec[name], c_sec[name]
            if "input_sha256" in b_row and "input_sha256" in c_row and b_row["input_sha256"] != c_row["input_sha256"]:
                mismatches.append(f"input_sha256 mismatch in {section}.{name}")
            b_sig = _canonical_row_sig(section, b_row)
            c_sig = _canonical_row_sig(section, c_row)
            if b_sig != c_sig:
                mismatches.append(f"signature mismatch in {section}.{name}:\n  baseline={b_sig}\n  current ={c_sig}")

    if "surface_batch" not in baseline or "surface_batch" not in current:
        mismatches.append("missing section surface_batch in baseline or current")
        return mismatches
    b_batches = baseline["surface_batch"]
    c_batches = current["surface_batch"]
    for extra in sorted(set(c_batches) - set(b_batches)):
        mismatches.append(f"extra candidate-only workload surface_batch.{extra}")
    if not partial:
        for missing in sorted(set(b_batches) - set(c_batches)):
            mismatches.append(f"missing baseline workload surface_batch.{missing}")
    for name in sorted(set(b_batches) & set(c_batches)):
        b_row, c_row = b_batches[name], c_batches[name]
        if "input_sha256" in b_row and "input_sha256" in c_row and b_row["input_sha256"] != c_row["input_sha256"]:
            mismatches.append(f"input_sha256 mismatch in surface_batch.{name}")
        if b_row.get("batch_ids") != c_row.get("batch_ids"):
            mismatches.append(f"batch_ids mismatch in surface_batch.{name}: {b_row.get('batch_ids')} != {c_row.get('batch_ids')}")
        b_sigs = b_row["signatures"]
        c_sigs = c_row["signatures"]
        if len(b_sigs) != len(c_sigs):
            mismatches.append(f"batch length mismatch in surface_batch.{name}: baseline={len(b_sigs)} current={len(c_sigs)}")
            continue
        if b_sigs != c_sigs:
            for idx, (bs, cs) in enumerate(zip(b_sigs, c_sigs)):
                if bs != cs:
                    mismatches.append(f"signature mismatch in surface_batch.{name}[{idx}]:\n  baseline={bs}\n  current ={cs}")
                    break
    return mismatches


def verify_comparator_negative_controls():
    """Verify _compare_signatures catches every injected semantic/structural mismatch."""
    base = {
        "schema": "m3-bvh-eval-v2",
        "surface_single": {
            "P1": {
                "input_sha256": ["a", "b"],
                "signature": {
                    "measurement_valid": True, "reason": None, "distance_m": 1.0,
                    "_exact_distance_sq": [1, 1, 0], "point_a_world": [0.0, 0.0, 0.0],
                    "point_b_world": [0.0, 0.0, 1.0], "direction_a_to_b": [0.0, 0.0, 1.0],
                    "witness_status": "measured", "witness_reason": None,
                    "direction_status": "measured", "direction_reason": None,
                    "topology": [{"boundary_edge_count": 0}],
                    "witness_triangle_indices": [0, 0], "exact_witness_triangles": None,
                },
            }
        },
        "surface_batch": {
            "B1": {
                "input_sha256": ["t", "p0", "p1"],
                "batch_ids": ["p0", "p1"],
                "signatures": [{"distance_m": 1.0}, {"distance_m": 2.0}],
            }
        },
        "spatial_relation": {
            "SR1": {
                "input_sha256": ["a", "b"],
                "relation": "separated",
                "certificate": "strict_all_referenced_vertex_support",
                "signature": {
                    "spatial": {"measurement_valid": True, "relation": "separated", "certificate": "strict_all_referenced_vertex_support", "reason": None},
                    "surface": {"distance_m": 1.0},
                },
            }
        },
        "closed_solid": {"C1": {"signature": {"measurement_valid": True, "relation": "separated", "certificate": "c1", "reason": None}}},
        "surface_analyze": {"A1": {"signature": {"status": "complete", "complete": True, "total": 0, "regions": [], "degenerate_triangles": []}}},
        "e2e_entries": {
            "G508_surface_nearest": {"signature": {"status": "complete", "nearest_ids": ["Peer_000"], "distance_m": 0.003, "unresolved": {}, "excluded": [], "measurement_notes": {}, "best_known_evidence": []}},
            "G508_surface_scan_5mm": {"signature": {"status": "complete", "coverage": {"bound_excluded": 0}, "matches": [], "dispositions": [{"object_ids": ["a", "b"], "status": "measured_match", "distance_m": 0.003}]}},
        },
    }
    assert _compare_signatures(base, copy.deepcopy(base), partial=False) == []

    def expect_caught(label, mutator, *, partial=False):
        cand = copy.deepcopy(base)
        mutator(cand)
        errs = _compare_signatures(base, cand, partial=partial)
        if not errs:
            raise AssertionError(f"Comparator negative control failed to catch: {label}")
        return {"control": label, "caught": True, "message": errs[0].splitlines()[0]}

    checks = [
        expect_caught("missing_workload_full", lambda c: c["surface_single"].pop("P1"), partial=False),
        expect_caught("extra_candidate_only_workload", lambda c: c["surface_single"].__setitem__("Extra", copy.deepcopy(base["surface_single"]["P1"])), partial=False),
        expect_caught("extra_candidate_only_workload_partial", lambda c: c["surface_single"].__setitem__("Extra", copy.deepcopy(base["surface_single"]["P1"])), partial=True),
        expect_caught("batch_length_truncated", lambda c: (c["surface_batch"]["B1"]["batch_ids"].pop(), c["surface_batch"]["B1"]["signatures"].pop())),
        expect_caught("batch_length_prefix_match_partial", lambda c: (c["surface_batch"]["B1"]["batch_ids"].pop(), c["surface_batch"]["B1"]["signatures"].pop()), partial=True),
        expect_caught("batch_order_swapped", lambda c: c["surface_batch"]["B1"].__setitem__("batch_ids", ["p1", "p0"])),
        expect_caught("spatial_relation_changed", lambda c: (c["spatial_relation"]["SR1"].__setitem__("relation", "penetrating"), c["spatial_relation"]["SR1"]["signature"]["spatial"].__setitem__("relation", "penetrating"))),
        expect_caught("spatial_certificate_changed", lambda c: (c["spatial_relation"]["SR1"].__setitem__("certificate", "closed_solid_fallback"), c["spatial_relation"]["SR1"]["signature"]["spatial"].__setitem__("certificate", "closed_solid_fallback"))),
        expect_caught("witness_point_shifted", lambda c: c["surface_single"]["P1"]["signature"].__setitem__("point_a_world", [0.001, 0.0, 0.0])),
        expect_caught("nearest_ranking_notes_changed", lambda c: c["e2e_entries"]["G508_surface_nearest"]["signature"]["measurement_notes"].__setitem__("Peer_000", {"witness_status": "unknown"})),
        expect_caught("scan_disposition_distance_changed", lambda c: c["e2e_entries"]["G508_surface_scan_5mm"]["signature"]["dispositions"][0].__setitem__("distance_m", 0.004)),
        expect_caught("analyze_regions_changed", lambda c: c["surface_analyze"]["A1"]["signature"]["regions"].append({"faces": [0, 1]})),
        expect_caught("analyze_degenerate_changed", lambda c: c["surface_analyze"]["A1"]["signature"]["degenerate_triangles"].append(3)),
    ]
    return {"passed": True, "controls_checked": len(checks), "details": checks}


def print_report(results, baseline=None):
    print(f"=== M3 BVH Eval (schema={results.get('schema')}, source_sha={results['runtime_identity_sha256'][:12]}) ===")
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
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--no-mem", action="store_true")
    parser.add_argument("--save-baseline", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--verify-comparator", action="store_true")
    args = parser.parse_args()

    comp_check = verify_comparator_negative_controls()
    if args.verify_comparator:
        print(json.dumps(comp_check, indent=2))
        if not args.save_baseline and not args.compare:
            return

    results = run_benchmark(
        warmup=args.warmup, repeats=args.repeats, quick=args.quick, measure_mem=not (args.no_mem or args.quick)
    )
    results["comparator_negative_controls"] = comp_check
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
