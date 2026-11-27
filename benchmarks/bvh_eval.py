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
    closed = res.get("closed")
    return {
        "measurement_valid": res.get("measurement_valid"),
        "budget_stopped": res.get("budget_stopped"),
        "stop_reason": res.get("stop_reason"),
        "closed": _closed_sig(closed) if isinstance(closed, dict) else closed,
        "spatial": {
            "measurement_valid": spatial.get("measurement_valid"),
            "relation": spatial.get("relation"),
            "certificate": spatial.get("certificate"),
            "reason": spatial.get("reason"),
            "support_evidence": copy.deepcopy(spatial.get("support_evidence")),
            "local_evidence": copy.deepcopy(spatial.get("local_evidence")),
        },
        "surface": _surface_sig(res.get("surface") or {}),
    }


def _closed_sig(res):
    return {k: copy.deepcopy(v) for k, v in res.items() if k != "work"}


def _analyze_sig(res):
    ignored = {"spatial_work", "work", "exact_pair_tests", "work_used"}
    out = {k: copy.deepcopy(v) for k, v in res.items() if k not in ignored}
    scan_ok = res.get("scan_complete") is True
    acct_ok = res.get("pair_accounting_complete") is True
    out["complete"] = bool(scan_ok and acct_ok and res.get("status") == "observed")
    return out


def _is_sha256_hex(val):
    return isinstance(val, str) and len(val) == 64 and all(c in "0123456789abcdef" for c in val)


def _binding_sig(out):
    binding = out.get("binding")
    if not isinstance(binding, dict):
        return None
    sig = copy.deepcopy(binding)
    sig["runtime_source_sha256_valid"] = _is_sha256_hex(binding.get("runtime_source_sha256"))
    return sig


def _nearest_sig(out):
    ignored = {"binding"}
    sig = {k: copy.deepcopy(v) for k, v in out.items() if k not in ignored}
    sig["binding"] = _binding_sig(out)
    return sig


def _scan_sig(out, diag):
    ignored = {"binding"}
    sig = {k: copy.deepcopy(v) for k, v in out.items() if k not in ignored}
    sig["binding"] = _binding_sig(out)
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
        "witness_projection_node_pruned_pairs", "witness_projection_tri_pruned_pairs",
        "witness_projection_box_pruned_pairs",
        "witness_projection_direction_builds", "witness_projection_directions",
        "dequeue_reused_aabb_bounds",
        "witness_projection_invalidations", "witness_projection_budget_deferrals",
        "witness_projection_upper_calls",
        "witness_projection_slab_admitted", "witness_projection_slab_deferred",
        "witness_projection_slab_reserved_units", "witness_projection_slab_actual_units",
        "witness_projection_credit_deferrals", "witness_projection_credit_credit_deferrals",
        "witness_projection_credit_budget_deferrals",
        "witness_projection_credit_attempts",
        "witness_projection_credit_node_units", "witness_projection_credit_narrow_units",
        "witness_projection_credit_node_prune_units",
        "witness_projection_credit_spent_units", "witness_projection_credit_balance",
        "witness_projection_credit_upper_units",
        "witness_projection_mode", "witness_projection_credit_reference",
        "witness_projection_tri_dots", "witness_projection_node_visits",
        "witness_projection_vertex_slabs", "witness_projection_vertex_slab_pruned_pairs",
        "witness_projection_cache_lookups", "witness_projection_cache_hits",
        "mesh_cache_hits", "mesh_cache_misses", "mesh_cache_tree_builds",
        "mesh_cache_tree_build_units", "mesh_cache_tree_reuses",
        "mesh_cache_translate_units", "mesh_cache_fallbacks",
        "narrow_phase_pairs", "intersection_tests",
        "point_face_tests", "point_edge_tests", "edge_edge_tests",
        "shared_trees",
    )
    return {k: work.get(k, 0) for k in keys}


def _time_fn(fn, warmup, repeats, measure_mem=True, *, check_sig=None):
    if repeats <= 0:
        raise ValueError(f"repeats must be positive, got {repeats}")
    for _ in range(warmup):
        fn()
    gc.collect()
    gc.disable()
    times_ns = []
    ref_sig = None
    verified_count = 0
    last_res = None
    try:
        for idx in range(repeats):
            t0 = time.perf_counter_ns()
            res = fn()
            times_ns.append(time.perf_counter_ns() - t0)
            if check_sig is not None:
                cur_sig = copy.deepcopy(check_sig(res))
                if ref_sig is None:
                    ref_sig = cur_sig
                elif cur_sig != ref_sig:
                    raise RuntimeError(f"Non-deterministic timed repeat output at index {idx}")
                verified_count += 1
            if idx == repeats - 1:
                last_res = copy.deepcopy(res)
    finally:
        gc.enable()
    res = last_res
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
        mem_out = fn()
        cpu_time_ms = (time.process_time_ns() - c0) / 1e6
        if check_sig is not None and copy.deepcopy(check_sig(mem_out)) != ref_sig:
            raise RuntimeError("Instrumentation pass signature mismatch")
        tracemalloc.start()
        tm_out = fn()
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if check_sig is not None and copy.deepcopy(check_sig(tm_out)) != ref_sig:
            raise RuntimeError("Tracemalloc pass signature mismatch")
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
        "peak_tracemalloc_bytes": peak_bytes,
        "memory_metric_scope": "python_tracemalloc_only_not_process_rss",
        "timed_outputs_verified": verified_count,
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

    solver_options = {
        "surface_single": {"retain_exact_rank": True, "retain_witness_triangles": True},
        "surface_batch": {"retain_exact_rank": True, "retain_witness_triangles": False},
        "spatial_relation": {"retain_exact_rank": True},
        "surface_analyze": {"near_m": 0.0},
    }
    results = {
        "schema": "m3-bvh-eval-v4",
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
        "solver_options": solver_options,
        "options_sha256": _stable_hash(solver_options),
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
            check_sig=_surface_sig,
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
            run_batch, warmup=warmup, repeats=max(1, repeats - 1) if quick else repeats, measure_mem=measure_mem,
            check_sig=lambda pair: [_surface_sig(r) for r in pair[0]],
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
        timing, (res, diag) = _time_fn(
            run_sr, warmup=warmup, repeats=repeats, measure_mem=measure_mem,
            check_sig=lambda pair: _spatial_sig(pair[0]),
        )
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
            check_sig=_closed_sig,
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
        timing, res = _time_fn(
            run_an, warmup=warmup, repeats=repeats, measure_mem=measure_mem,
            check_sig=_analyze_sig,
        )
        an_work = dict(res.get("spatial_work", {}))
        an_work["exact_pair_tests"] = res.get("exact_pair_tests")
        if "work_used" in res:
            an_work["work_used"] = res.get("work_used")
        results["surface_analyze"][name] = {
            "input_sha256": _stable_hash({"raw": prep.get("raw"), "faces": faces, "near_m": 0.0}),
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
        t_near, (out_near, diag_near) = _time_fn(
            run_nearest, warmup=warmup, repeats=repeats, measure_mem=measure_mem,
            check_sig=lambda pair: _nearest_sig(pair[0]),
        )
        results["e2e_entries"]["G508_surface_nearest"] = {
            "input_sha256": _stable_hash(nearest_packet),
            "timing": t_near,
            "work": {"kernel_calls": diag_near["kernel_calls"], "pair_calls": diag_near["pair_calls"]},
            "signature": _nearest_sig(out_near),
        }

        print("  running G508_surface_scan_5mm...", flush=True)
        t_scan, (out_scan, diag_scan) = _time_fn(
            run_scan, warmup=warmup, repeats=repeats, measure_mem=measure_mem,
            check_sig=lambda pair: _scan_sig(pair[0], pair[1]),
        )
        results["e2e_entries"]["G508_surface_scan_5mm"] = {
            "input_sha256": _stable_hash(scan_packet),
            "timing": t_scan,
            "work": {"kernel_calls": diag_scan["kernel_calls"], "bound_excluded": out_scan["coverage"]["bound_excluded"]},
            "signature": _scan_sig(out_scan, diag_scan),
        }

    return results


def _nonempty_str(val):
    return isinstance(val, str) and len(val) > 0


def _validate_input_sha(section, row):
    val = row.get("input_sha256")
    if section in ("surface_single", "spatial_relation", "closed_solid"):
        return isinstance(val, list) and len(val) == 2 and all(_is_sha256_hex(x) for x in val)
    if section == "surface_batch":
        ids = row.get("batch_ids")
        if not isinstance(ids, list) or not ids:
            return False
        return isinstance(val, list) and len(val) == 1 + len(ids) and all(_is_sha256_hex(x) for x in val)
    return _is_sha256_hex(val) or (isinstance(val, list) and len(val) >= 1 and all(_is_sha256_hex(x) for x in val))


def _valid_nested_sha256(obj):
    if isinstance(obj, dict) and obj:
        return all(_is_sha256_hex(v) or _valid_nested_sha256(v) for v in obj.values())
    return False


def _validate_surface_sig_struct(prefix, sig, *, options=None):
    errors = []
    req = (
        "measurement_valid", "reason", "distance_m", "_exact_distance_sq",
        "point_a_world", "point_b_world", "direction_a_to_b",
        "witness_status", "direction_status",
        "witness_triangle_indices", "exact_witness_triangles",
    )
    for k in req:
        if k not in sig:
            errors.append(f"{prefix}: missing required surface signature key {k!r}")
    if errors:
        return errors

    mv = sig.get("measurement_valid")
    if type(mv) is not bool:
        return [f"{prefix}: measurement_valid must be bool, got {mv!r}"]

    ws = sig.get("witness_status")
    ds = sig.get("direction_status")
    if ws not in ("measured", "unknown"):
        errors.append(f"{prefix}: invalid witness_status {ws!r}")
    if ds not in ("measured", "not_applicable", "unknown"):
        errors.append(f"{prefix}: invalid direction_status {ds!r}")

    dm = sig.get("distance_m")
    ek = sig.get("_exact_distance_sq")
    want_exact_rank = True if (isinstance(options, dict) and options.get("retain_exact_rank") is True) else False

    def _is_vec3(v):
        return (
            isinstance(v, (list, tuple)) and len(v) == 3
            and all(type(c) in (int, float) and math.isfinite(c) for c in v)
        )

    if mv is True:
        if type(dm) not in (int, float) or not math.isfinite(dm) or dm < 0.0:
            errors.append(f"{prefix}: measurement_valid=True with invalid distance_m={dm!r}")
        if want_exact_rank:
            if not (
                isinstance(ek, (list, tuple)) and len(ek) == 3
                and all(type(x) is int for x in ek) and ek[0] >= 0 and ek[1] > 0
            ):
                errors.append(f"{prefix}: retain_exact_rank requested with invalid _exact_distance_sq={ek!r}")
        if ws == "measured":
            if not _is_vec3(sig.get("point_a_world")) or not _is_vec3(sig.get("point_b_world")):
                errors.append(f"{prefix}: witness_status='measured' with invalid witness points")
        elif ws == "unknown":
            if not _nonempty_str(sig.get("witness_reason")):
                errors.append(f"{prefix}: witness_status='unknown' without witness_reason")
        if ds == "measured":
            if not _is_vec3(sig.get("direction_a_to_b")) or (type(dm) in (int, float) and dm <= 0.0):
                errors.append(f"{prefix}: direction_status='measured' inconsistent with direction/distance")
        elif ds == "not_applicable":
            if dm != 0.0 or not _nonempty_str(sig.get("direction_reason")):
                errors.append(f"{prefix}: direction_status='not_applicable' inconsistent with distance/reason")
        elif ds == "unknown":
            if not _nonempty_str(sig.get("direction_reason")):
                errors.append(f"{prefix}: direction_status='unknown' without direction_reason")
        wti = sig.get("witness_triangle_indices")
        if wti is not None and not (
            isinstance(wti, (list, tuple)) and len(wti) == 2 and all(type(x) is int and x >= 0 for x in wti)
        ):
            errors.append(f"{prefix}: invalid witness_triangle_indices={wti!r}")
    else:
        if not _nonempty_str(sig.get("reason")):
            errors.append(f"{prefix}: measurement_valid=False without reason")
        if dm is not None:
            errors.append(f"{prefix}: measurement_valid=False with non-None distance_m={dm!r}")
        if ws != "unknown" or ds != "unknown":
            errors.append(f"{prefix}: measurement_valid=False requires unknown witness/direction status")
    return errors


def check_entry_receipts(ref_sig, cand_sig, *, ref_runtime_sha, cand_runtime_sha, entry_kind):
    """Verify two cross-arm entry receipts against independent runtime pins before normalization."""
    errors = []
    if not _is_sha256_hex(ref_runtime_sha):
        errors.append(f"invalid ref_runtime_sha: {ref_runtime_sha!r}")
    if not _is_sha256_hex(cand_runtime_sha):
        errors.append(f"invalid cand_runtime_sha: {cand_runtime_sha!r}")
    if entry_kind not in ("nearest", "scan"):
        errors.append(f"unsupported entry_kind: {entry_kind!r}")
    if not isinstance(ref_sig, dict) or not isinstance(cand_sig, dict):
        errors.append("entry receipts must be dicts")
        return errors

    for label, sig, pin in (("baseline", ref_sig, ref_runtime_sha), ("current", cand_sig, cand_runtime_sha)):
        b = sig.get("binding")
        if not isinstance(b, dict):
            errors.append(f"{label}.{entry_kind}: missing binding dict")
        else:
            if b.get("runtime_source_sha256_valid") is not True:
                errors.append(f"{label}.{entry_kind}: invalid runtime_source_sha256_valid")
            raw_rt = b.get("runtime_source_sha256")
            if not _is_sha256_hex(raw_rt):
                errors.append(f"{label}.{entry_kind}: missing/malformed binding runtime_source_sha256")
            elif _is_sha256_hex(pin) and raw_rt != pin:
                errors.append(f"{label}.{entry_kind}: binding runtime_source_sha256 {raw_rt} != expected pin {pin}")
        if entry_kind == "nearest":
            if not _nonempty_str(sig.get("status")) or not isinstance(sig.get("nearest_ids"), list):
                errors.append(f"{label}.nearest: missing status or nearest_ids list")
            dm = sig.get("distance_m")
            if dm is not None and (type(dm) not in (int, float) or not math.isfinite(dm) or dm < 0.0):
                errors.append(f"{label}.nearest: invalid distance_m={dm!r}")
            if "unresolved" not in sig or "excluded" not in sig:
                errors.append(f"{label}.nearest: missing unresolved/excluded keys")
        elif entry_kind == "scan":
            if not _nonempty_str(sig.get("status")) or not isinstance(sig.get("coverage"), dict):
                errors.append(f"{label}.scan: missing status or coverage dict")
            disps = sig.get("dispositions")
            if not isinstance(disps, list):
                errors.append(f"{label}.scan: missing dispositions list")
            else:
                oid_keys = [tuple(d.get("object_ids") or ()) for d in disps if isinstance(d, dict) and d.get("object_ids")]
                if len(oid_keys) != len(disps) or len(set(oid_keys)) != len(oid_keys):
                    errors.append(f"{label}.scan: invalid or duplicate scan dispositions")
    if errors:
        return errors

    norm_ref = copy.deepcopy(ref_sig)
    norm_cand = copy.deepcopy(cand_sig)
    norm_ref["binding"].pop("runtime_source_sha256", None)
    norm_cand["binding"].pop("runtime_source_sha256", None)
    if norm_ref != norm_cand:
        errors.append(f"{entry_kind} semantic mismatch after verified runtime pin normalization")
    return errors


def assert_entry_receipts_equal(ref_sig, cand_sig, *, ref_runtime_sha, cand_runtime_sha, entry_kind):
    errs = check_entry_receipts(
        ref_sig, cand_sig,
        ref_runtime_sha=ref_runtime_sha,
        cand_runtime_sha=cand_runtime_sha,
        entry_kind=entry_kind,
    )
    if errs:
        raise RuntimeError("; ".join(errs))


def _validate_row(side, section, name, row, *, arm_runtime_sha=None, expected_batch_manifest=None, section_options=None):
    errors = []
    if not isinstance(row, dict):
        return [f"{side}.{section}.{name}: row must be a dict"]
    if section == "surface_batch":
        ids = row.get("batch_ids")
        sigs = row.get("signatures")
        if not isinstance(ids, list) or not ids or not all(_nonempty_str(x) for x in ids):
            errors.append(f"{side}.{section}.{name}: batch_ids must be a non-empty list of strings")
        elif len(set(ids)) != len(ids):
            errors.append(f"{side}.{section}.{name}: duplicate entries in batch_ids: {ids}")
        if not isinstance(sigs, list) or not sigs or any(not isinstance(s, dict) for s in sigs):
            errors.append(f"{side}.{section}.{name}: signatures must be a non-empty list of dicts")
        else:
            if isinstance(ids, list) and len(sigs) != len(ids):
                errors.append(f"{side}.{section}.{name}: len(signatures)={len(sigs)} != len(batch_ids)={len(ids)}")
            for idx, s in enumerate(sigs):
                errors.extend(_validate_surface_sig_struct(f"{side}.{section}.{name}.signatures[{idx}]", s, options=section_options))
        if "expected_batch_ids" in row and row["expected_batch_ids"] != ids:
            errors.append(f"{side}.{section}.{name}: batch_ids {ids} != expected_batch_ids {row['expected_batch_ids']}")
        if expected_batch_manifest is not None:
            if name not in expected_batch_manifest:
                errors.append(f"{side}.{section}.{name}: batch missing from expected_batch_manifest")
            elif expected_batch_manifest[name] != ids:
                errors.append(f"{side}.{section}.{name}: batch_ids {ids} != expected_batch_manifest {expected_batch_manifest[name]}")
        if not _validate_input_sha(section, row):
            errors.append(f"{side}.{section}.{name}: missing or invalid input_sha256")
        return errors
    if not _validate_input_sha(section, row):
        errors.append(f"{side}.{section}.{name}: missing or invalid input_sha256")

    sig = row.get("signature")
    if not isinstance(sig, dict):
        errors.append(f"{side}.{section}.{name}: missing or non-dict signature")
        return errors

    if section == "surface_single":
        errors.extend(_validate_surface_sig_struct(f"{side}.{section}.{name}.signature", sig, options=section_options))
    elif section == "spatial_relation":
        spatial = sig.get("spatial")
        surface = sig.get("surface")
        if not isinstance(spatial, dict) or not isinstance(surface, dict):
            errors.append(f"{side}.{section}.{name}: signature missing spatial or surface dict")
            return errors
        errors.extend(_validate_surface_sig_struct(f"{side}.{section}.{name}.signature.surface", surface, options=section_options))
        if "relation" in row and row["relation"] != spatial.get("relation"):
            errors.append(f"{side}.{section}.{name}: top-level relation {row['relation']!r} != spatial.relation {spatial.get('relation')!r}")
        if "certificate" in row and row["certificate"] != spatial.get("certificate"):
            errors.append(f"{side}.{section}.{name}: top-level certificate {row['certificate']!r} != spatial.certificate {spatial.get('certificate')!r}")
        top_ok = sig.get("measurement_valid")
        sp_ok = spatial.get("measurement_valid")
        sf_ok = surface.get("measurement_valid")
        if type(top_ok) is not bool or type(sp_ok) is not bool or type(sf_ok) is not bool:
            errors.append(f"{side}.{section}.{name}: spatial measurement_valid flags must all be bool")
        elif top_ok != (sp_ok and sf_ok):
            errors.append(f"{side}.{section}.{name}: top measurement_valid={top_ok} != (spatial={sp_ok} and surface={sf_ok})")
        if sp_ok is True:
            if spatial.get("relation") not in ("separated", "touching", "penetrating") or not _nonempty_str(spatial.get("certificate")):
                errors.append(f"{side}.{section}.{name}: spatial measurement_valid=True missing valid relation/certificate")
        elif sp_ok is False:
            if spatial.get("relation") is not None or not _nonempty_str(spatial.get("reason")):
                errors.append(f"{side}.{section}.{name}: spatial measurement_valid=False with non-None relation or missing reason")
        if sig.get("budget_stopped") is True and not _nonempty_str(sig.get("stop_reason")):
            errors.append(f"{side}.{section}.{name}: budget_stopped=True without stop_reason")
    elif section == "closed_solid":
        mv = sig.get("measurement_valid")
        if type(mv) is not bool or "relation" not in sig or "certificate" not in sig:
            errors.append(f"{side}.{section}.{name}: missing required closed_solid fields")
        elif mv is True and (sig.get("relation") not in ("separated", "touching", "penetrating") or not _nonempty_str(sig.get("certificate"))):
            errors.append(f"{side}.{section}.{name}: closed_solid valid=True invalid relation/certificate")
        elif mv is False and (sig.get("relation") is not None or not _nonempty_str(sig.get("reason"))):
            errors.append(f"{side}.{section}.{name}: closed_solid valid=False invalid relation/reason")
    elif section == "surface_analyze":
        if "status" not in sig or "scan_complete" not in sig or "pair_accounting_complete" not in sig:
            errors.append(f"{side}.{section}.{name}: analyze missing required completeness/status fields")
        claimed_complete = sig.get("complete") is True or sig.get("status") == "complete"
        if claimed_complete:
            if sig.get("status") != "observed" or sig.get("scan_complete") is not True or sig.get("pair_accounting_complete") is not True:
                errors.append(f"{side}.{section}.{name}: analyze claims complete without observed+scan_complete+pair_accounting_complete")
    elif section == "e2e_entries":
        b = sig.get("binding")
        if not isinstance(b, dict):
            errors.append(f"{side}.{section}.{name}: e2e signature missing binding dict")
        else:
            if b.get("runtime_source_sha256_valid") is not True:
                errors.append(f"{side}.{section}.{name}: e2e binding missing or invalid runtime_source_sha256_valid")
            raw_rt = b.get("runtime_source_sha256")
            if not _is_sha256_hex(raw_rt):
                errors.append(f"{side}.{section}.{name}: e2e binding missing valid runtime_source_sha256")
            elif arm_runtime_sha is not None and raw_rt != arm_runtime_sha:
                errors.append(f"{side}.{section}.{name}: e2e binding runtime_source_sha256 {raw_rt} != arm pin {arm_runtime_sha}")
        if "scan" in name:
            disps = sig.get("dispositions")
            if not isinstance(disps, list):
                errors.append(f"{side}.{section}.{name}: scan e2e entry missing dispositions list")
            else:
                oid_keys = [tuple(d.get("object_ids") or ()) for d in disps if isinstance(d, dict) and d.get("object_ids")]
                if len(oid_keys) != len(disps) or len(set(oid_keys)) != len(oid_keys):
                    errors.append(f"{side}.{section}.{name}: invalid or duplicate scan dispositions")
    return errors


def _canonical_row_sig(section, row):
    sig = copy.deepcopy(row["signature"])
    if section == "e2e_entries" and isinstance(sig.get("binding"), dict):
        # Cross-arm runtime_source_sha256 pinning is verified per arm BEFORE this normalization.
        sig["binding"].pop("runtime_source_sha256", None)
    return sig


def _compare_signatures(baseline, current, partial=False, *, expected_batch_manifest=None,
                        expected_workload_manifest=None, expected_arm_pins=None):
    mismatches = []
    if not isinstance(baseline, dict) or not isinstance(current, dict):
        return ["baseline and current must be dicts"]
    if baseline.get("schema") != "m3-bvh-eval-v4" or current.get("schema") != "m3-bvh-eval-v4":
        mismatches.append(f"schema mismatch (expected m3-bvh-eval-v4): baseline={baseline.get('schema')} current={current.get('schema')}")
        return mismatches
    b_rt = baseline.get("runtime_identity_sha256")
    c_rt = current.get("runtime_identity_sha256")
    if not _is_sha256_hex(b_rt):
        mismatches.append(f"baseline missing valid 64-hex runtime_identity_sha256: {b_rt!r}")
    if not _is_sha256_hex(c_rt):
        mismatches.append(f"current missing valid 64-hex runtime_identity_sha256: {c_rt!r}")
    if isinstance(expected_arm_pins, dict):
        exp_b = expected_arm_pins.get("baseline")
        exp_c = expected_arm_pins.get("current")
        if exp_b is not None and b_rt != exp_b:
            mismatches.append(f"baseline runtime_identity_sha256 {b_rt} != expected external pin {exp_b}")
        if exp_c is not None and c_rt != exp_c:
            mismatches.append(f"current runtime_identity_sha256 {c_rt} != expected external pin {exp_c}")
    for label, doc in (("baseline", baseline), ("current", current)):
        sopt = doc.get("solver_options")
        osha = doc.get("options_sha256")
        if not isinstance(sopt, dict):
            mismatches.append(f"{label} missing solver_options dict")
        elif not _is_sha256_hex(osha):
            mismatches.append(f"{label} missing valid 64-hex options_sha256: {osha!r}")
        elif _stable_hash(sopt) != osha:
            mismatches.append(f"{label} options_sha256 does not match _stable_hash(solver_options)")
    if baseline.get("options_sha256") != current.get("options_sha256"):
        mismatches.append(f"options_sha256 mismatch: baseline={baseline.get('options_sha256')} current={current.get('options_sha256')}")
    for label, doc in (("baseline", baseline), ("current", current)):
        if not _valid_nested_sha256(doc.get("inputs_sha256")):
            mismatches.append(f"{label} missing valid 64-hex inputs_sha256 manifest")
    if baseline.get("inputs_sha256") != current.get("inputs_sha256"):
        mismatches.append("inputs_sha256 mismatch between baseline and current")

    def _sec_opts(doc, sec):
        sopt = doc.get("solver_options")
        if not isinstance(sopt, dict):
            return None
        if sec in sopt and isinstance(sopt[sec], dict):
            return sopt[sec]
        if "retain_exact_rank" in sopt:
            return sopt
        return None

    compared_items = 0
    sections = ("surface_single", "spatial_relation", "closed_solid", "surface_analyze", "e2e_entries")
    for section in sections:
        if section not in baseline or section not in current:
            mismatches.append(f"missing section {section} in baseline or current")
            continue
        b_sec = baseline[section]
        c_sec = current[section]
        if not isinstance(b_sec, dict) or not isinstance(c_sec, dict):
            mismatches.append(f"section {section} must be a dict in baseline and current")
            continue
        b_keys = set(b_sec)
        c_keys = set(c_sec)
        if isinstance(expected_workload_manifest, dict) and section in expected_workload_manifest:
            exp_keys = set(expected_workload_manifest[section])
            if not exp_keys:
                mismatches.append(f"expected_workload_manifest[{section}] must be non-empty")
            for missing in sorted(exp_keys - b_keys):
                mismatches.append(f"baseline missing manifest workload {section}.{missing}")
            for missing in sorted(exp_keys - c_keys):
                mismatches.append(f"current missing manifest workload {section}.{missing}")
            for extra in sorted(b_keys - exp_keys):
                mismatches.append(f"baseline unregistered workload {section}.{extra}")
            for extra in sorted(c_keys - exp_keys):
                mismatches.append(f"current unregistered workload {section}.{extra}")
        for extra in sorted(c_keys - b_keys):
            mismatches.append(f"extra candidate-only workload {section}.{extra}")
        if not partial:
            for missing in sorted(b_keys - c_keys):
                mismatches.append(f"missing baseline workload {section}.{missing}")
        b_sopt = _sec_opts(baseline, section)
        c_sopt = _sec_opts(current, section)
        for name in sorted(b_keys):
            mismatches.extend(_validate_row("baseline", section, name, b_sec[name], arm_runtime_sha=b_rt, section_options=b_sopt))
        for name in sorted(c_keys):
            mismatches.extend(_validate_row("current", section, name, c_sec[name], arm_runtime_sha=c_rt, section_options=c_sopt))
        for name in sorted(b_keys & c_keys):
            compared_items += 1
            b_row, c_row = b_sec[name], c_sec[name]
            if not isinstance(b_row, dict) or not isinstance(c_row, dict):
                continue
            if b_row.get("input_sha256") != c_row.get("input_sha256"):
                mismatches.append(f"input_sha256 mismatch in {section}.{name}")
            if isinstance(b_row.get("signature"), dict) and isinstance(c_row.get("signature"), dict):
                b_sig = _canonical_row_sig(section, b_row)
                c_sig = _canonical_row_sig(section, c_row)
                if b_sig != c_sig:
                    mismatches.append(f"signature mismatch in {section}.{name}:\n  baseline={b_sig}\n  current ={c_sig}")

    if "surface_batch" not in baseline or "surface_batch" not in current:
        mismatches.append("missing section surface_batch in baseline or current")
        return mismatches
    b_batches = baseline["surface_batch"]
    c_batches = current["surface_batch"]
    if not isinstance(b_batches, dict) or not isinstance(c_batches, dict):
        mismatches.append("section surface_batch must be a dict in baseline and current")
        return mismatches
    if isinstance(expected_workload_manifest, dict) and "surface_batch" in expected_workload_manifest:
        exp_b_keys = set(expected_workload_manifest["surface_batch"])
        for missing in sorted(exp_b_keys - set(b_batches)):
            mismatches.append(f"baseline missing manifest workload surface_batch.{missing}")
        for missing in sorted(exp_b_keys - set(c_batches)):
            mismatches.append(f"current missing manifest workload surface_batch.{missing}")
        for extra in sorted(set(b_batches) - exp_b_keys):
            mismatches.append(f"baseline unregistered workload surface_batch.{extra}")
        for extra in sorted(set(c_batches) - exp_b_keys):
            mismatches.append(f"current unregistered workload surface_batch.{extra}")
    for extra in sorted(set(c_batches) - set(b_batches)):
        mismatches.append(f"extra candidate-only workload surface_batch.{extra}")
    if not partial:
        for missing in sorted(set(b_batches) - set(c_batches)):
            mismatches.append(f"missing baseline workload surface_batch.{missing}")
    b_sb_opt = _sec_opts(baseline, "surface_batch")
    c_sb_opt = _sec_opts(current, "surface_batch")
    for name in sorted(b_batches):
        mismatches.extend(_validate_row("baseline", "surface_batch", name, b_batches[name], arm_runtime_sha=b_rt, expected_batch_manifest=expected_batch_manifest, section_options=b_sb_opt))
    for name in sorted(c_batches):
        mismatches.extend(_validate_row("current", "surface_batch", name, c_batches[name], arm_runtime_sha=c_rt, expected_batch_manifest=expected_batch_manifest, section_options=c_sb_opt))
    for name in sorted(set(b_batches) & set(c_batches)):
        compared_items += 1
        b_row, c_row = b_batches[name], c_batches[name]
        if not isinstance(b_row, dict) or not isinstance(c_row, dict):
            continue
        if b_row.get("input_sha256") != c_row.get("input_sha256"):
            mismatches.append(f"input_sha256 mismatch in surface_batch.{name}")
        if b_row.get("batch_ids") != c_row.get("batch_ids"):
            mismatches.append(f"batch_ids mismatch in surface_batch.{name}: {b_row.get('batch_ids')} != {c_row.get('batch_ids')}")
        b_sigs = b_row.get("signatures")
        c_sigs = c_row.get("signatures")
        if not isinstance(b_sigs, list) or not isinstance(c_sigs, list):
            continue
        if len(b_sigs) != len(c_sigs):
            mismatches.append(f"batch length mismatch in surface_batch.{name}: baseline={len(b_sigs)} current={len(c_sigs)}")
            continue
        if b_sigs != c_sigs:
            for idx, (bs, cs) in enumerate(zip(b_sigs, c_sigs)):
                if bs != cs:
                    mismatches.append(f"signature mismatch in surface_batch.{name}[{idx}]:\n  baseline={bs}\n  current ={cs}")
                    break
    if compared_items == 0:
        mismatches.append("empty comparison: 0 items compared (partial mode requires >= 1 common item)")
    return mismatches


def verify_comparator_negative_controls():
    """Verify _compare_signatures and signature extractors catch every injected semantic/structural mismatch."""
    def _require(cond, msg):
        if not cond:
            raise RuntimeError(msg)

    valid_rt_sha = "a" * 64
    cand_rt_sha = "e" * 64
    sha_b = "b" * 64
    sha_c = "c" * 64
    sha_d = "d" * 64
    sha_f = "f" * 64
    sha_0 = "0" * 64
    sha_1 = "1" * 64
    sopt = {"retain_exact_rank": True}
    surf_row_ok = {
        "measurement_valid": True, "reason": None, "distance_m": 1.0,
        "_exact_distance_sq": [1, 1, 0], "point_a_world": [0.0, 0.0, 0.0],
        "point_b_world": [0.0, 0.0, 1.0], "direction_a_to_b": [0.0, 0.0, 1.0],
        "witness_status": "measured", "witness_reason": None,
        "direction_status": "measured", "direction_reason": None,
        "topology": [{"boundary_edge_count": 0}],
        "witness_triangle_indices": [0, 0], "exact_witness_triangles": None,
    }
    base = {
        "schema": "m3-bvh-eval-v4",
        "runtime_identity_sha256": valid_rt_sha,
        "solver_options": copy.deepcopy(sopt),
        "options_sha256": _stable_hash(sopt),
        "inputs_sha256": {"snapshot": sha_b},
        "surface_single": {
            "P1": {
                "input_sha256": [sha_0, sha_1],
                "signature": copy.deepcopy(surf_row_ok),
            }
        },
        "surface_batch": {
            "B1": {
                "input_sha256": [sha_0, sha_1, sha_b],
                "batch_ids": ["p0", "p1"],
                "signatures": [copy.deepcopy(surf_row_ok), {**copy.deepcopy(surf_row_ok), "distance_m": 2.0}],
            }
        },
        "spatial_relation": {
            "SR1": {
                "input_sha256": [sha_0, sha_1],
                "relation": "separated",
                "certificate": "strict_all_referenced_vertex_support",
                "signature": {
                    "measurement_valid": True,
                    "budget_stopped": False,
                    "stop_reason": None,
                    "closed": None,
                    "spatial": {
                        "measurement_valid": True, "relation": "separated",
                        "certificate": "strict_all_referenced_vertex_support", "reason": None,
                        "support_evidence": {"direction": [0, 0, 1]}, "local_evidence": None,
                    },
                    "surface": copy.deepcopy(surf_row_ok),
                },
            }
        },
        "closed_solid": {
            "C1": {
                "input_sha256": [sha_0, sha_1],
                "signature": {"measurement_valid": True, "relation": "separated", "certificate": "c1", "reason": None},
            }
        },
        "surface_analyze": {
            "A1": {
                "input_sha256": sha_d,
                "signature": {
                    "status": "observed", "scan_complete": True, "pair_accounting_complete": True,
                    "complete": True, "total": 0, "regions": [], "degenerate_triangles": [],
                },
            }
        },
        "e2e_entries": {
            "G508_surface_nearest": {
                "input_sha256": sha_f,
                "signature": {
                    "status": "complete", "nearest_ids": ["Peer_000"], "distance_m": 0.003,
                    "unresolved": {}, "excluded": [], "measurement_notes": {}, "best_known_evidence": [],
                    "binding": {
                        "scene_revision": "r1", "scene_fingerprint": "fp1", "document_epoch": "e1",
                        "directory_sha256": sha_0, "host_source_sha256": sha_c,
                        "runtime_source_sha256": valid_rt_sha,
                        "runtime_source_sha256_valid": True,
                    },
                },
            },
            "G508_surface_scan_5mm": {
                "input_sha256": sha_f,
                "signature": {
                    "status": "complete", "coverage": {"bound_excluded": 0}, "matches": [],
                    "dispositions": [{"object_ids": ["a", "b"], "status": "measured_match", "distance_m": 0.003}],
                    "binding": {
                        "scene_revision": "r1", "scene_fingerprint": "fp1", "document_epoch": "e1",
                        "directory_sha256": sha_1, "host_source_sha256": sha_c,
                        "runtime_source_sha256": valid_rt_sha,
                        "runtime_source_sha256_valid": True,
                    },
                },
            },
        },
    }
    _require(_compare_signatures(base, copy.deepcopy(base), partial=False) == [], "identical v4 comparison failed")

    # Positive control: cross-arm with DIFFERENT valid pinned source hashes passes when each matches its own arm pin
    cross_cand = copy.deepcopy(base)
    cross_cand["runtime_identity_sha256"] = cand_rt_sha
    cross_cand["e2e_entries"]["G508_surface_nearest"]["signature"]["binding"]["runtime_source_sha256"] = cand_rt_sha
    cross_cand["e2e_entries"]["G508_surface_scan_5mm"]["signature"]["binding"]["runtime_source_sha256"] = cand_rt_sha
    _require(_compare_signatures(base, cross_cand, partial=False) == [], "cross-arm pinned SHAs failed")

    # Positive control: registered partial subset with matching expected_batch_manifest
    part_cand = copy.deepcopy(cross_cand)
    part_cand["surface_single"] = {}
    _require(
        _compare_signatures(base, part_cand, partial=True, expected_batch_manifest={"B1": ["p0", "p1"]}) == [],
        "registered partial comparison with manifest failed",
    )

    # Positive control: valid resource-limited surface receipt & optional-provenance-None pass
    rl_cand = copy.deepcopy(cross_cand)
    rl_base = copy.deepcopy(base)
    res_lim_sig = {
        "measurement_valid": False, "reason": "surface_work_budget", "distance_m": None,
        "_exact_distance_sq": None, "point_a_world": None, "point_b_world": None,
        "direction_a_to_b": None, "witness_status": "unknown", "witness_reason": None,
        "direction_status": "unknown", "direction_reason": None,
        "topology": None, "witness_triangle_indices": None, "exact_witness_triangles": None,
    }
    rl_base["surface_single"]["P1"]["signature"] = copy.deepcopy(res_lim_sig)
    rl_cand["surface_single"]["P1"]["signature"] = copy.deepcopy(res_lim_sig)
    _require(_compare_signatures(rl_base, rl_cand, partial=False) == [], "valid resource-limited receipt rejected")
    no_prov_base = copy.deepcopy(base)
    no_prov_cand = copy.deepcopy(cross_cand)
    no_prov_base["surface_single"]["P1"]["signature"]["witness_triangle_indices"] = None
    no_prov_cand["surface_single"]["P1"]["signature"]["witness_triangle_indices"] = None
    _require(_compare_signatures(no_prov_base, no_prov_cand, partial=False) == [], "valid distance with omitted provenance rejected")

    # Shared cross-arm entry receipt comparator positive + negative controls (R3-F03)
    near_ref = copy.deepcopy(base["e2e_entries"]["G508_surface_nearest"]["signature"])
    near_cand = copy.deepcopy(cross_cand["e2e_entries"]["G508_surface_nearest"]["signature"])
    assert_entry_receipts_equal(near_ref, near_cand, ref_runtime_sha=valid_rt_sha, cand_runtime_sha=cand_rt_sha, entry_kind="nearest")
    scan_ref = copy.deepcopy(base["e2e_entries"]["G508_surface_scan_5mm"]["signature"])
    scan_cand = copy.deepcopy(cross_cand["e2e_entries"]["G508_surface_scan_5mm"]["signature"])
    assert_entry_receipts_equal(scan_ref, scan_cand, ref_runtime_sha=valid_rt_sha, cand_runtime_sha=cand_rt_sha, entry_kind="scan")
    for bad_label, fn_bad in (
        ("entry_wrong_digest", lambda: assert_entry_receipts_equal(near_ref, near_cand, ref_runtime_sha=valid_rt_sha, cand_runtime_sha=sha_b, entry_kind="nearest")),
        ("entry_missing_binding", lambda: assert_entry_receipts_equal(near_ref, {**near_cand, "binding": None}, ref_runtime_sha=valid_rt_sha, cand_runtime_sha=cand_rt_sha, entry_kind="nearest")),
        ("entry_semantic_drift_scan", lambda: assert_entry_receipts_equal(scan_ref, {**scan_cand, "dispositions": [{"object_ids": ["a", "b"], "status": "measured_match", "distance_m": 0.999}]}, ref_runtime_sha=valid_rt_sha, cand_runtime_sha=cand_rt_sha, entry_kind="scan")),
    ):
        try:
            fn_bad()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(f"Entry receipt negative control failed to catch: {bad_label}")

    def expect_caught(label, mutator, *, partial=False, mutate_both=False, manifest=None, wk_manifest=None, arm_pins=None):
        b_doc = copy.deepcopy(base)
        cand = copy.deepcopy(base)
        if mutate_both:
            mutator(b_doc)
        mutator(cand)
        errs = _compare_signatures(
            b_doc, cand, partial=partial,
            expected_batch_manifest=manifest,
            expected_workload_manifest=wk_manifest,
            expected_arm_pins=arm_pins,
        )
        if not errs:
            raise RuntimeError(f"Comparator negative control failed to catch: {label}")
        return {"control": label, "caught": True, "message": errs[0].splitlines()[0]}

    def make_empty(doc):
        for s in ("surface_single", "surface_batch", "spatial_relation", "closed_solid", "surface_analyze", "e2e_entries"):
            doc[s] = {}

    # Extractor unit assertions for R3 C04 (must survive python -O via explicit raise)
    an_obs_incomplete = _analyze_sig({"status": "observed", "scan_complete": False, "pair_accounting_complete": True, "total": 0, "regions": [], "degenerate_triangles": []})
    _require(an_obs_incomplete["complete"] is False, f"expected complete=False, got {an_obs_incomplete}")
    an_missing_acct = _analyze_sig({"status": "observed", "scan_complete": True, "total": 0, "regions": [], "degenerate_triangles": []})
    _require(an_missing_acct["complete"] is False, f"missing pair_accounting_complete returned True: {an_missing_acct}")
    an_legacy_word = _analyze_sig({"status": "complete", "scan_complete": True, "pair_accounting_complete": True})
    _require(an_legacy_word["complete"] is False, f"legacy status=complete returned True: {an_legacy_word}")
    ns_bad_rt = _nearest_sig({"status": "complete", "binding": {"scene_revision": "r1", "runtime_source_sha256": "not-a-sha"}})
    _require(ns_bad_rt["binding"]["runtime_source_sha256_valid"] is False, ns_bad_rt)
    ns_good_rt = _nearest_sig({"status": "complete", "binding": {"scene_revision": "r1", "runtime_source_sha256": valid_rt_sha}})
    _require(ns_good_rt["binding"]["runtime_source_sha256_valid"] is True and ns_good_rt["binding"]["runtime_source_sha256"] == valid_rt_sha, ns_good_rt)

    # _time_fn at-return snapshot catches reused mutable result dict aliasing & check_sig=None reports 0 verified
    mut_box = {"val": 0}
    step_box = [0]
    def mut_ret():
        step_box[0] += 1
        mut_box["val"] = step_box[0]
        return mut_box
    caught_alias = False
    try:
        _time_fn(mut_ret, warmup=0, repeats=3, measure_mem=False, check_sig=lambda r: {"v": r["val"]})
    except RuntimeError:
        caught_alias = True
    _require(caught_alias, "_time_fn failed to catch reused mutable dict aliasing")
    t_unverified, _ = _time_fn(lambda: {"ok": True}, warmup=0, repeats=3, measure_mem=False, check_sig=None)
    _require(t_unverified["timed_outputs_verified"] == 0, f"expected timed_outputs_verified=0, got {t_unverified}")

    checks = [
        expect_caught("missing_workload_full", lambda c: c["surface_single"].pop("P1"), partial=False),
        expect_caught("extra_candidate_only_workload", lambda c: c["surface_single"].__setitem__("Extra", copy.deepcopy(base["surface_single"]["P1"])), partial=False),
        expect_caught("extra_candidate_only_workload_partial", lambda c: c["surface_single"].__setitem__("Extra", copy.deepcopy(base["surface_single"]["P1"])), partial=True),
        expect_caught("batch_length_truncated", lambda c: (c["surface_batch"]["B1"]["batch_ids"].pop(), c["surface_batch"]["B1"]["signatures"].pop(), c["surface_batch"]["B1"]["input_sha256"].pop())),
        expect_caught("batch_length_prefix_match_partial", lambda c: (c["surface_batch"]["B1"]["batch_ids"].pop(), c["surface_batch"]["B1"]["signatures"].pop(), c["surface_batch"]["B1"]["input_sha256"].pop()), partial=True),
        expect_caught("batch_order_swapped", lambda c: c["surface_batch"]["B1"].__setitem__("batch_ids", ["p1", "p0"])),
        expect_caught("spatial_relation_changed", lambda c: (c["spatial_relation"]["SR1"].__setitem__("relation", "penetrating"), c["spatial_relation"]["SR1"]["signature"]["spatial"].__setitem__("relation", "penetrating"))),
        expect_caught("spatial_certificate_changed", lambda c: (c["spatial_relation"]["SR1"].__setitem__("certificate", "closed_solid_fallback"), c["spatial_relation"]["SR1"]["signature"]["spatial"].__setitem__("certificate", "closed_solid_fallback"))),
        expect_caught("witness_point_shifted", lambda c: c["surface_single"]["P1"]["signature"].__setitem__("point_a_world", [0.001, 0.0, 0.0])),
        expect_caught("nearest_ranking_notes_changed", lambda c: c["e2e_entries"]["G508_surface_nearest"]["signature"]["measurement_notes"].__setitem__("Peer_000", {"witness_status": "unknown"})),
        expect_caught("scan_disposition_distance_changed", lambda c: c["e2e_entries"]["G508_surface_scan_5mm"]["signature"]["dispositions"][0].__setitem__("distance_m", 0.004)),
        expect_caught("analyze_regions_changed", lambda c: c["surface_analyze"]["A1"]["signature"]["regions"].append({"faces": [0, 1]})),
        expect_caught("analyze_degenerate_changed", lambda c: c["surface_analyze"]["A1"]["signature"]["degenerate_triangles"].append(3)),
        expect_caught("missing_input_sha256_one_side", lambda c: c["surface_single"]["P1"].pop("input_sha256")),
        expect_caught("missing_input_sha256_both_sides", lambda c: c["surface_single"]["P1"].pop("input_sha256"), mutate_both=True),
        expect_caught("options_sha256_missing", lambda c: c.pop("options_sha256")),
        expect_caught("options_sha256_mismatch", lambda c: c.__setitem__("options_sha256", "changed")),
        expect_caught("missing_batch_ids_both_sides", lambda c: c["surface_batch"]["B1"].pop("batch_ids"), mutate_both=True),
        expect_caught("duplicate_batch_ids_both_sides", lambda c: c["surface_batch"]["B1"].__setitem__("batch_ids", ["p0", "p0"]), mutate_both=True),
        expect_caught("identical_inconsistent_spatial_rows_both_sides", lambda c: c["spatial_relation"]["SR1"].__setitem__("relation", "penetrating"), mutate_both=True),
        expect_caught("identical_inconsistent_spatial_valid_both_sides", lambda c: c["spatial_relation"]["SR1"]["signature"]["spatial"].__setitem__("measurement_valid", False), mutate_both=True),
        expect_caught("empty_partial_zero_items", make_empty, partial=True),
        expect_caught("analyze_observed_incomplete_spoof_both", lambda c: c["surface_analyze"]["A1"]["signature"].__setitem__("scan_complete", False), mutate_both=True),
        expect_caught("nearest_binding_field_mutated", lambda c: c["e2e_entries"]["G508_surface_nearest"]["signature"]["binding"].__setitem__("scene_revision", "r2")),
        expect_caught("scan_binding_runtime_sha_invalid", lambda c: c["e2e_entries"]["G508_surface_scan_5mm"]["signature"]["binding"].__setitem__("runtime_source_sha256_valid", False), mutate_both=True),
        expect_caught("spatial_support_evidence_changed", lambda c: c["spatial_relation"]["SR1"]["signature"]["spatial"]["support_evidence"].__setitem__("direction", [1, 0, 0])),
        expect_caught("spatial_top_measurement_valid_changed", lambda c: c["spatial_relation"]["SR1"]["signature"].__setitem__("measurement_valid", False)),
        # New R3 C04 fail-closed controls:
        expect_caught("short_malformed_input_sha_both", lambda c: c["surface_single"]["P1"].__setitem__("input_sha256", ["a", "not-a-hash"]), mutate_both=True),
        expect_caught("uppercase_hex_input_sha_rejected", lambda c: c["surface_single"]["P1"].__setitem__("input_sha256", ["A" * 64, sha_1]), mutate_both=True),
        expect_caught("missing_top_level_inputs_sha256_both", lambda c: c.pop("inputs_sha256"), mutate_both=True),
        expect_caught("options_sha256_recompute_mismatch_both", lambda c: c["solver_options"].__setitem__("retain_exact_rank", False), mutate_both=True),
        expect_caught("e2e_binding_unpinned_valid_sha_mismatch", lambda c: c["e2e_entries"]["G508_surface_nearest"]["signature"]["binding"].__setitem__("runtime_source_sha256", cand_rt_sha)),
        expect_caught("e2e_binding_missing_runtime_sha", lambda c: c["e2e_entries"]["G508_surface_nearest"]["signature"]["binding"].pop("runtime_source_sha256"), mutate_both=True),
        expect_caught("expected_batch_manifest_truncated_both", lambda c: (c["surface_batch"]["B1"]["batch_ids"].pop(), c["surface_batch"]["B1"]["signatures"].pop(), c["surface_batch"]["B1"]["input_sha256"].pop()), mutate_both=True, manifest={"B1": ["p0", "p1"]}),
        expect_caught("surface_single_missing_required_field_both", lambda c: c["surface_single"]["P1"]["signature"].pop("distance_m"), mutate_both=True),
        expect_caught("scan_duplicate_disposition_both", lambda c: c["e2e_entries"]["G508_surface_scan_5mm"]["signature"]["dispositions"].append({"object_ids": ["a", "b"], "status": "measured_match", "distance_m": 0.003}), mutate_both=True),
        # New R3-F04 / R3-F05 controls:
        expect_caught("surface_negative_distance_both", lambda c: c["surface_single"]["P1"]["signature"].__setitem__("distance_m", -1.0), mutate_both=True),
        expect_caught("surface_infinite_distance_both", lambda c: c["surface_single"]["P1"]["signature"].__setitem__("distance_m", float("inf")), mutate_both=True),
        expect_caught("surface_bogus_witness_status_both", lambda c: c["surface_single"]["P1"]["signature"].__setitem__("witness_status", "bogus"), mutate_both=True),
        expect_caught("surface_missing_exact_rank_when_requested_both", lambda c: c["surface_single"]["P1"]["signature"].__setitem__("_exact_distance_sq", None), mutate_both=True),
        expect_caught("spatial_top_false_contradicts_both_true", lambda c: c["spatial_relation"]["SR1"]["signature"].__setitem__("measurement_valid", False), mutate_both=True),
        expect_caught("scan_missing_dispositions_field_both", lambda c: c["e2e_entries"]["G508_surface_scan_5mm"]["signature"].pop("dispositions"), mutate_both=True),
        expect_caught("expected_workload_manifest_both_omitted", lambda c: c["surface_single"].pop("P1"), mutate_both=True, wk_manifest={"surface_single": ["P1"]}),
        expect_caught("expected_arm_pins_wrong_external_pin", lambda c: None, arm_pins={"baseline": valid_rt_sha, "current": cand_rt_sha}),
    ]
    return {
        "passed": True,
        "controls_checked": len(checks) + 10,
        "alias_caught": caught_alias,
        "details": checks,
    }


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
    parser.add_argument("--expected-baseline-sha", type=str, default=None)
    parser.add_argument("--expected-current-sha", type=str, default=None)
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
        pins = None
        if args.expected_baseline_sha or args.expected_current_sha:
            pins = {"baseline": args.expected_baseline_sha, "current": args.expected_current_sha}
        mismatches = _compare_signatures(baseline, results, partial=args.quick, expected_arm_pins=pins)
        if mismatches:
            print("EQUIVALENCE CHECK FAILED:")
            for msg in mismatches:
                print(msg)
            raise SystemExit(1)
        print("EQUIVALENCE CHECK PASSED: all exact distance keys, witnesses, relations, and entries match baseline.")


if __name__ == "__main__":
    main()
