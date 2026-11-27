"""Independent readback of 047 and exact projections of the archived G60 source."""
import ast
from collections import Counter, defaultdict
from fractions import Fraction as F
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path
import runpy
import struct
import subprocess
import sys
from types import ModuleType


RUNS = Path("D:/HumanEye/runs")
RAW = RUNS / "M6-047-R3-COVERAGE-DOMAIN"
OLD = RUNS / "M6-045-R3-REPLACEMENT-ENTRY/g60"
IMPL = Path.home() / ".codex/worktrees/m6-model-selection/hefe"
CYCLE = "verification/m6_r3_coverage_domain_047"
HEAD = "568cbf023125cea2a7c2e57270cec31956435458"
PARENT = "c010b07be6352b1f15e39fd2c8227a05bb7690cd"


def read(path):
    return json.loads(path.read_bytes())


def check_record(row, base=Path()):
    path = base / row["path"]
    payload = path.read_bytes()
    assert len(payload) == row["bytes"] and sha256(payload).hexdigest() == row["sha256"], path
    return len(payload)


def git(*args):
    return subprocess.check_output(["git", "-C", str(IMPL), *args])


def integrity():
    assert git("rev-parse", HEAD + "^").decode().strip() == PARENT
    files = git("diff", "--name-only", PARENT, HEAD).decode().splitlines()
    for name in files:
        assert name.startswith(CYCLE + "/")
        assert git("show", HEAD + ":" + name) == (IMPL / name).read_bytes(), name
    index = RAW / "RAW_EVIDENCE.json"
    assert sha256(index.read_bytes()).hexdigest() == "164ad9155f147ca7efe5cbae95ea7ddd9a4d58a00241d654b83bbac46c5f34b3"
    members = read(index)["files"]
    assert {r["path"].replace("\\", "/") for r in members} == {
        p.relative_to(RAW).as_posix() for p in RAW.rglob("*") if p.is_file() and p != index}
    archived = read(RAW / "g60/ARCHIVE_FREEZE.json")["archive_files"]
    assert len(archived) == len({r["path"] for r in archived}) == 622
    return {"implementation": HEAD, "parent": PARENT, "committed_files": len(files),
            "raw_members": len(members), "raw_bytes": sum(check_record(r, RAW) for r in members),
            "archive_members": len(archived), "archive_bytes": sum(map(check_record, archived))}


def bounds():
    matrix = read(RAW / "MATRIX.json")
    cases = {k: matrix[k] for k in ("ordinary_125", "ordinary_129", "assembly")}
    cases.update(matrix["Yanyite"])
    cases["G60"] = {"faces": [60, 60], "work_remaining": 1179648, "narrow_remaining": 16384}
    result = {}
    for case, row in cases.items():
        n, m = row["faces"]
        pairs, faces = n*m, n+m
        tree = n*n + m*m + 7*faces + 124*pairs + 6
        loose = n*n + m*m + 8*faces + 124*pairs + 4
        assert loose - tree == faces-2
        gates = [pairs <= row["narrow_remaining"], loose <= row["work_remaining"]]
        assert (tree <= row["work_remaining"]) == gates[1]
        if case != "G60":
            assert loose == row["C_work_upper_if_ordinary_clean"] and gates == [
                row["narrow_bound_pass"], row["conditional_work_bound_pass"]]
        result[case] = {"potential": pairs, "tree_upper": tree, "report_upper": loose,
                        "narrow_and_work_sufficient": gates}
    return result


def publication_control(arm):
    # Bind source bytes for the two modules used by the helper, outside the product entry.
    rec = read(OLD / "PLAN.json")["release_bindings"][arm]
    check_record(rec)
    binding = read(Path(rec["path"]))
    site = Path(binding["site_packages"])
    allowed = {r["path"].replace("\\", "/"): r["sha256"] for r in binding["source_files"]}
    package = ModuleType("human_eye_plugin")
    package.__path__ = []
    sys.modules[package.__name__] = package
    for short in ("telemetry", "surface_proximity"):
        relative = f"human_eye_plugin/{short}.py"
        data = (site / relative).read_bytes()
        assert sha256(data).hexdigest() == allowed[relative]
        module = ModuleType(f"human_eye_plugin.{short}")
        module.__package__ = "human_eye_plugin"
        module.__file__ = str(site / relative)
        sys.modules[module.__name__] = module
        exec(compile(data, module.__file__, "exec"), module.__dict__)
    surface = sys.modules["human_eye_plugin.surface_proximity"]
    h, length = F(1, 2**52), 2**50
    p = (1+h, 1+h, F(0))
    t = F(2*length+1, length**2+(length+1)**2)
    q = (1+t*length*h, 1+t*(length+1)*h, F(0))
    sq = sum((a-b)**2 for a, b in zip(p, q))
    assert 0 < t < 1 and sq == h*h/(length**2+(length+1)**2)
    distance = surface._rounded_distance(sq.numerator, sq.denominator, 1)
    origin = (F(0),)*3
    assert distance > 0 and tuple(map(float, p)) == tuple(map(float, q))
    assert surface._publish_points((p, q), origin, 1, distance) is None
    other = (p[0]+F(1, 65536), p[1], p[2])
    assert surface._publish_points((p, other), origin, 1, 1/65536) == [list(map(float, point)) for point in (p, other)]
    return {"positive_distance_hex": distance.hex(), "rounded_coincidence_rejected": True,
            "distinct_exactly_representable_control_published": True}


def source_comparison():
    plan = read(OLD / "PLAN.json")
    function_sets = {"surface_proximity": ("_publish_points", "_rounded_distance", "_witness",
        "_exact_distance_key", "_witness_triangle_provenance", "_rank_surface_results", "_boundary_witness"),
        "task_query": ("_surface_proximity_fact", "_fact")}
    signatures, controls, bindings = {}, {}, {}
    for arm in ("A", "C"):
        rec = plan["release_bindings"][arm]
        check_record(rec)
        binding = read(Path(rec["path"]))
        site = Path(binding["site_packages"])
        for row in binding["source_files"]:
            assert sha256((site / row["path"]).read_bytes()).hexdigest() == row["sha256"]
        bindings[arm] = {"files": len(binding["source_files"]), "sha256": binding["identity"]["source_sha256"]}
        for module, functions in function_sets.items():
            source = site / "human_eye_plugin" / (module + ".py")
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for name in functions:
                node = next(node for node in tree.body if getattr(node, "name", None) == name)
                signatures.setdefault(name, {})[arm] = sha256(ast.dump(node).encode()).hexdigest()
        command = [sys.executable, "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()),
                   "--publication", arm]
        controls[arm] = json.loads(subprocess.check_output(command))
    assert all(v["A"] == v["C"] for v in signatures.values()) and controls["A"] == controls["C"]
    return {"releases": bindings, "identical_function_ast_sha256": {k: v["A"] for k, v in signatures.items()},
            "pinned_publication_helper_controls": controls}


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def input_projections():
    data = read(RAW / "g60/NATIVE_GEOMETRY.json")
    objects = data["objects"]
    world, axes = {}, {}
    for name, item in objects.items():
        for field, dtype, digest in (("vertices_world_m", "3d", "world_sha256"),
                                     ("vertices_local", "3d", "local_sha256"),
                                     ("triangles", "3i", "triangles_sha256")):
            payload = b"".join(struct.pack("<"+dtype, *v) for v in item[field])
            assert sha256(payload).hexdigest() == item["hashes"][digest]
        world[name] = [tuple(map(F, p)) for p in item["vertices_world_m"]]
        axes[name] = tuple(tuple(F(row[c]) for row in item["matrix_world"][:3]) for c in range(3))
        assert len(world[name]) == 32 and len(item["triangles"]) == 60
    before = data["matched_actual_ordinary_snapshots"]
    archived = read(RAW / "g60/ARCHIVE_FREEZE.json")["archive_files"]
    snapshots = [r for r in archived if Path(r["path"]).name in ("BEFORE.json", "AFTER.json")
                 and Path(r["path"]).parent.parent == OLD / "main_001"]
    assert {r["sha256"] for r in before} == {r["sha256"] for r in snapshots
                                                if Path(r["path"]).name == "BEFORE.json"}
    for ref in snapshots:
        check_record(ref)
        scene = read(Path(ref["path"]))["geometry"]
        assert set(scene) == set(objects)
        for name, item in objects.items():
            assert item["matrix_world"] == scene[name]["matrix"]
            assert all(scene[name][k] == v for k, v in item["hashes"].items())
    assert len(objects) == len(snapshots) == 12
    world_axes = tuple(tuple(F(i == j) for i in range(3)) for j in range(3))
    intervals = {}
    def interval(name, axis):
        key = (name, axis)
        if key not in intervals:
            values = [dot(vertex, axis) for vertex in world[name]]
            intervals[key] = (min(values), max(values))
        return intervals[key]

    def lower_square(a, b, basis):
        squared = []
        for axis in basis:
            al, ar = interval(a, axis)
            bl, br = interval(b, axis)
            gap = max(F(0), al-br, bl-ar)
            squared.append(gap*gap/dot(axis, axis))
        return max(squared)

    radius = 1
    while radius < max(abs(v) for points in world.values() for pt in points for v in pt):
        radius *= 2
    ulp = F(math.ulp(float(radius)))
    results = {}
    for a, b in combinations(sorted(objects), 2):
        assert lower_square(a, b, world_axes) == 0
        sq = lower_square(a, b, axes[a])
        if sq:
            assert sq > 12*ulp**2 and "Target" in (a, b)
            results[(a, b)] = sq
    assert len(results) == 11
    assert len({axes[name] for name in objects}) == 1
    return results, {"objects": len(objects), "native_snapshots": len(snapshots), "pairs": 66,
        "world_axis_separated": 0, "common_matrix_axes": 3, "vertices_per_object": 32,
        "local_axis_vertex_dots_with_reuse": 12*32*3, "coordinate_bound_metres": radius,
        "safe_coordinate_ulp_metres": float(ulp), "nonzero_local_lower_bounds": len(results),
        "lower_square_m2": [{"objects": list(pair), "square": str(sq), "metres": math.sqrt(sq)}
                            for pair, sq in results.items()],
        "above_5mm_from_source": sum(sq > F(5, 1000)**2 for sq in results.values())}


def receipts(separated):
    rows = read(RAW / "g60/PAIR_CALLS.json")
    def key(row):
        return row["group"], row["arm"], row["step"], tuple(row["ordered_object_ids"])
    by_key = {key(row): row for row in rows}
    assert len(by_key) == len(rows) == 1386
    body_count = 0
    counts = Counter()
    ranges = defaultdict(list)
    for group in sorted((OLD / "main_001").glob("G[0-9][0-9]-*")):
        group_no = int(group.name[1:3])
        common = None
        for arm in ("A", "B", "C"):
            client = group / arm / "client"
            bodies = [json.loads(read(client / f"{k:03}.RX.bin")["result"]["content"][0]["text"])
                      for k in (4, 5, 6)]
            body_count += len(bodies)
            overview, nearest, scan = bodies
            assert overview["status"] == "overview" and nearest["status"] == scan["status"] == "complete"
            assert nearest["coverage"] == {"targets_excluding_focal": 11, "distance_valid": 11,
                "strictly_excluded": 0, "unresolved": 0}
            assert scan["coverage"] == {"objects": 12, "total_pairs": 66, "bound_excluded": 0,
                "measured_match": 57, "measured_nonmatch": 9, "unknown": 0, "deferred": 0,
                "catalog_scope_confirmed": True}
            assert nearest["focal"]["name"] == "Target" and [x["name"] for x in nearest["nearest_objects"]] == ["Peer_000"]
            published = {tuple(sorted(obj["name"] for obj in m["objects"])): m for m in scan["matches"]}
            assert all(m["witness_status"] == "measured" for m in published.values())
            public_facts = (nearest["distance_m"], nearest["best_known_evidence"], published)
            if common is not None:
                assert public_facts == common
            common = public_facts
            events = [json.loads(s) for s in (client / "AUDIT.jsonl").read_text(encoding="utf-8").splitlines()]
            audit = {e["trace_id"]: e for e in events if e["event"] == "observe"}
            names_by_step = {}
            for step, body in (("nearest", nearest), ("scan", scan)):
                names = set()
                for label, native in audit[body["trace_id"]]["task_work"]["pairs"].items():
                    ids = (body["focal"]["id"], label) if step == "nearest" else tuple(json.loads(label))
                    row = by_key.pop((group_no, arm, step, ids))
                    assert native["surface_work"] == row["surface_work"] and row["per_call_compute_ns"] is None
                    assert native["surface_pair_count"] == row["actual_compute_calls"] == 1
                    assert native["surface_pair_cache_hit"] is row["pair_cache_hit"] is False
                    if step == "scan":
                        assert native["surface_dependency_key"] == row["cache_key_digest"]
                    else:
                        assert row["cache_key_digest"] is None
                    pair = tuple(sorted(row["ordered_names"]))
                    names.add(pair)
                    counts[arm] += 1
                    for k in ("work_units", "narrow_phase_pairs"):
                        ranges[arm, k].append(native["surface_work"][k])
                names_by_step[step] = names
            assert names_by_step["nearest"] == set(separated)
            zeros = {p for p, m in published.items() if m["distance_m"] == 0}
            assert len(zeros) == 55 and zeros == names_by_step["scan"] - set(separated)
            assert all(float(published[p]["distance_m"]) + 1e-12 >= math.sqrt(sq)
                       for p, sq in separated.items() if p in published)
    assert body_count == 54 and not by_key and set(counts.values()) == {462}
    return {"ordinary_receipts": body_count, "calls_by_version": dict(counts),
        "actual_calls_each_cell": {"nearest": 11, "scan": 66, "same_unordered_geometry_in_both": 11},
        "scan_zero_witnesses_in_all_cells": 55, "scan_positive_matches": 2, "scan_nonmatches": 9,
        "per_call_timestamps": None, "ranges": {"/".join(k): [min(v), max(v)] for k, v in ranges.items()},
        "public_scan_match_points_and_nearest_evidence_equal_across_arms": True}


def previous_ordinary_runs():
    previous = Path(__file__).resolve().parents[1] / "m6_r3_replacement_entry_045_review"
    code = runpy.run_path(str(previous / "recompute.py"))
    archived = read(previous / "INDEPENDENT_045.json")
    public = code["public_boundary"](code["independent_geometry"]())
    g60 = code["live_g60"]()
    assert public == archived["public"] and g60["deltas"] == archived["g60"]["deltas"]
    return {"source_batch": "045", "new_timing_samples": 0, "boundary_129": public,
            "G60_business_C_vs_A": g60["deltas"]["business"]["C_vs_A"],
            "G60_process_C_vs_A": g60["deltas"]["process"]["C_vs_A"]}


if __name__ == "__main__":
    if sys.argv[1:2] == ["--publication"]:
        print(json.dumps(publication_control(sys.argv[2])))
    else:
        proof, geometry = input_projections()
        output = {"integrity": integrity(), "bounds": bounds(), "sources": source_comparison(),
                  "input_geometry": geometry, "original_calls": receipts(proof),
                  "historical_ordinary": previous_ordinary_runs()}
        print(json.dumps(output, indent=2))
