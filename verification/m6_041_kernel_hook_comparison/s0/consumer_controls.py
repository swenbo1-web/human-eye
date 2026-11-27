"""Fixed local S0 consumer fixture, independent external pair/run pins."""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from fractions import Fraction
import hashlib
import inspect
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import historical_replay as history

PEER_IDS = ("b", "c")
EXPECTED_SCAN = {
    ("a", "b"): "measured_match",
    ("a", "c"): "measured_match",
    ("a", "d"): "bound_excluded",
    ("b", "c"): "bound_excluded",
    ("b", "d"): "bound_excluded",
    ("c", "d"): "bound_excluded",
}
POSITIONS = {"a": 0., "b": 0.125, "c": -0.125, "d": 1.}
OPTIONS = {"retain_exact_rank": True, "retain_witness_triangles": True}
BENCH = ROOT / "source_R3/benchmarks/bvh_eval.py"
BENCH_HASH = "db9cde085c7accb5a626ccc4a4cea0ae5f280ab82a1bff80252dce061d15d0b3"


def coords(z):
    return [(0., 0., z), (1., 0., z), (0., 1., z)]


def code_subset(names, env):
    tree = ast.parse(BENCH.read_text(encoding="utf-8"))
    functions = [item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name in names]
    assert sorted(item.name for item in functions) == sorted(names)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(BENCH), "exec"), env)
    return env


def sha(value):
    return hashlib.sha256(history.canonical(value)).hexdigest()


def load_entry_helpers():
    import numpy as np
    from human_eye_module1_operators import MeshEntity3D
    from human_eye_plugin.blender_host import _acquisition_lower, _acquisition_upper, _digest
    from human_eye_plugin.runtime_identity import runtime_identity

    return code_subset({"_triangulate", "_make_entity", "_build_nearest_packet", "_build_scan_packet"},
        dict(np=np, math=math, MeshEntity3D=MeshEntity3D, _acquisition_lower=_acquisition_lower,
             _acquisition_upper=_acquisition_upper, _digest=_digest, runtime_identity=runtime_identity))


def case_options(kernel):
    if "_mesh_cache" not in inspect.signature(kernel.measure_surface_proximity).parameters:
        return {}, {}
    memo = {}
    return {"_mesh_cache": memo}, memo


def mutation(kernel):
    import numpy as np

    a = SimpleNamespace(vertices=np.array(coords(0.)), faces=np.array([[0, 1, 2]]))
    b = SimpleNamespace(vertices=np.array(coords(.125)), faces=np.array([[0, 1, 2]]))
    options, memo = case_options(kernel)
    rows = []
    for k, value in enumerate((.125, .25, .375)):
        if k == 1:
            b.vertices[:, 2] = value
        if k == 2:
            b.vertices = np.array(coords(value))
            b.faces = np.array([[0, 2, 1]])
        row = kernel.measure_surface_proximity(a, b, lambda _: None, **OPTIONS, **options)
        assert row["measurement_valid"] and row["distance_m"] == value
        assert row["work"].get("mesh_cache_hits", 0) == 0 and not memo
        rows.append(row)
    return rows


def topology(kernel):
    a = SimpleNamespace(vertices=tuple(coords(0.)), faces=((0, 1, 2),))
    b = SimpleNamespace(vertices=tuple(coords(.125)), faces=((0, 1, 2),))
    options, memo = case_options(kernel)
    first = kernel.measure_surface_proximity(a, b, lambda _: None, **OPTIONS, **options)
    assert first["topology"][0]["boundary_edge_count"] == 3
    first["topology"][0]["boundary_edge_count"] = 999
    second = kernel.measure_surface_proximity(a, b, lambda _: None, **OPTIONS, **options)
    assert [m["boundary_edge_count"] for m in second["topology"]] == [3, 3]
    if options:
        assert second["work"]["mesh_cache_hits"] == 2 and len(memo) == 2
    return second


def record_consumer(arm, installed):
    kernel, _, identity, constants = history.selected_runtime(arm, installed)
    from human_eye_plugin.scene_cache import SpatialSceneCache
    from human_eye_plugin.surface_scan import surface_scan_result
    from human_eye_plugin.task_query import surface_nearest_result

    _, original40, _, _, _ = history.verify_history()
    probe_direct = original40.direct_test(kernel)
    assert probe_direct["outcome"] == "completed"
    original40_nearest = original40.nearest_tests(sys.modules[surface_nearest_result.__module__], identity)
    assert original40_nearest["outcome"] == "completed"
    assert not any(row["event"] == "full_tolist" for row in original40_nearest["vertex_access"])
    old40_cancel = original40.cancel_test(kernel)
    assert old40_cancel["outcome"] == "cancelled"
    assert old40_cancel["state_at_cancellation"] == {"vertex_access": [], "prepared_meshes": []}
    fixed = load_entry_helpers()
    mesh_inputs = {key: fixed["_make_entity"](key, coords(z), [(0, 1, 2)])
                   for key, z in POSITIONS.items()}
    neph, _ = fixed["_build_nearest_packet"](list(mesh_inputs.values()))
    scp = fixed["_build_scan_packet"](list(mesh_inputs.values()), threshold=.125)

    def prepared_pair(name):
        return tuple(tuple(coords(POSITIONS[obj])) for obj in name)

    nearest_diag, scan_diag = {}, {}
    near = surface_nearest_result(neph, SpatialSceneCache(), lambda _: None, diagnostics=nearest_diag)
    scan = surface_scan_result(scp, SpatialSceneCache(), lambda _: None, diagnostics=scan_diag)
    assert near["status"] == "complete" and tuple(near["nearest_ids"]) == PEER_IDS and near["distance_m"] == .125
    assert near["coverage"] == {"targets_excluding_focal": 3, "distance_valid": 2, "strictly_excluded": 1, "unresolved": 0}
    assert scan["status"] == "complete"
    assert {tuple(row["object_ids"]): row["status"] for row in scan_diag["dispositions"]} == EXPECTED_SCAN
    assert [tuple(obj["id"] for obj in row["objects"]) for row in scan["matches"]] == [("a", "b"), ("a", "c")]
    assert all(row["distance_m"] == .125 for row in scan["matches"])
    if arm == "r3":
        for diag in (nearest_diag, scan_diag):
            assert len(diag["pairs"]) == 2
            for row in diag["pairs"].values():
                work = row["surface_work"]
                assert work["witness_projection_mode"] == "settled_credit_031_ref"
                assert work["witness_projection_credit_reference"] == "mandatory_031_dequeue_aabb"
                assert work.get("mesh_cache_hits", 0) == 0

    for endpoint, packet in ((surface_nearest_result, neph), (surface_scan_result, scp)):
        bad = deepcopy(packet)
        bad["binding"]["host_source_sha256"] = "0" * 64
        try:
            endpoint(bad, SpatialSceneCache(), lambda _: None)
        except ValueError as error:
            assert "binding" in str(error).lower()
        else:
            raise AssertionError("wrong host-source binding accepted")

    class Cancelled(RuntimeError):
        pass

    cache = SpatialSceneCache()
    attempted = []
    def checkpoint(stage):
        attempted.append(stage)
        if stage == "surface_proximity_validated_faces":
            raise Cancelled(stage)

    try:
        surface_nearest_result(neph, cache, checkpoint)
    except Cancelled:
        pass
    else:
        raise AssertionError("cancelled nearest request returned")
    resume_diag = {}
    resumed = surface_nearest_result(neph, cache, lambda _: None, diagnostics=resume_diag)
    assert resumed == near and resume_diag["kernel_calls"] == 2

    pairs = {}
    for pair in (("a", "b"), ("a", "c")):
        value = kernel.measure_surface_proximity(*(mesh_inputs[obj] for obj in pair), lambda _: None, **OPTIONS)
        n, d, e = value["_exact_distance_sq"]
        assert Fraction(n, d) * Fraction(2) ** e == Fraction(1, 64)
        pairs["/".join(pair)] = {"raw": value, "input_sha256": sha(prepared_pair(pair))}
    return dict(identity=identity, constants=constants,
                normal_nearest=near, normal_scan=scan, nearest_diagnostics=nearest_diag,
                scan_diagnostics=scan_diag, independently_expected_ids=list(PEER_IDS),
                independently_expected_scan={"/".join(k): v for k, v in EXPECTED_SCAN.items()},
                frozen_geometry_sha256=sha(POSITIONS), pairs=pairs, consumer_cancel_checkpoints=attempted,
                resume_diagnostics=resume_diag, unreferenced_direct=probe_direct, unreferenced_nearest=original40_nearest,
                first_face_cancel=old40_cancel, direct_ndarray_mutation_and_rebind=mutation(kernel),
                immutable_cache_topology_isolation=topology(kernel))


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("arm", choices=("032", "r3"))
    cli.add_argument("--installed", action="store_true")
    args = cli.parse_args()
    assert history.digest(BENCH) == BENCH_HASH
    row = record_consumer(args.arm, args.installed)
    prefix = "installed" if args.installed else "source"
    path = ROOT / f"CONSUMER_{prefix}_{args.arm}.json"
    history.save(path, row)
    print(json.dumps({"arm": args.arm, "runtime": prefix, "file": str(path),
                     "sha256": history.digest(path), "policy": list(row["nearest_diagnostics"]["pairs"].values())[0]["surface_work"].get("witness_projection_mode")}), flush=True)


if __name__ == "__main__":
    main()
