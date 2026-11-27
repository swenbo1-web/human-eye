"""Check 048 receipts against the original 045 wire and exact source triangles."""
from fractions import Fraction as Q
from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path
import runpy


RAW = Path("D:/HumanEye/runs/M6-048-R3-WITNESS-PARITY")
OLD = Path("D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY/g60/main_001")
IMPL = Path.home() / ".codex/worktrees/m6-model-selection/hefe"
SCOPE = "verification/m6_r3_witness_parity_048"
HEAD = "0c50036f451ef28cdc95f8b1c9e0cb10a0bcd170"
PARENT = "568cbf023125cea2a7c2e57270cec31956435458"
REVIEWS = Path(__file__).resolve().parents[1]
CHECK47 = runpy.run_path(str(REVIEWS / "m6_r3_coverage_domain_047_review/recompute.py"))
CHECK44 = runpy.run_path(str(REVIEWS / "m6_r3_fresh_budget_044_review/recompute.py"))
read = CHECK47["read"]


def checked(row, base=Path()):
    CHECK47["check_record"](row, base)
    return base / row["path"]


def integrity(frozen, replay):
    git = CHECK47["git"]
    assert git("rev-parse", HEAD + "^").decode().strip() == PARENT
    names = git("diff", "--name-only", PARENT, HEAD).decode().splitlines()
    for name in names:
        assert name.startswith(SCOPE + "/") and git("show", HEAD + ":" + name) == (IMPL / name).read_bytes()
    index = RAW / "RAW_EVIDENCE.json"
    assert sha256(index.read_bytes()).hexdigest() == "acd52e7d9b42da5eab7feec3356afdaadcd20f6bb967ac002527ed2fa368cfe8"
    members = read(index)["files"]
    assert {checked(row, RAW).resolve() for row in members} == {
        p.resolve() for p in RAW.rglob("*") if p.is_file() and p != index}
    assert checked(replay["freeze"]) == RAW / "FREEZE.json"
    source_count = 0
    for arm, item in frozen["runtime"].items():
        binding = read(checked(item["binding"]))
        assert binding["identity"]["source_sha256"] == CHECK44["PINS"][arm]
        site = Path(binding["site_packages"])
        for row in binding["source_files"]:
            assert sha256((site / row["path"]).read_bytes()).hexdigest() == row["sha256"]
            source_count += 1
        exit_receipt = replay["closeout"][arm]
        assert exit_receipt["exit"] == 0 and not exit_receipt["forced"]
    assert not read(RAW / "TERMINAL_INVENTORY.json")["remaining_process_matches"]
    return {"commit": HEAD, "git_files": len(names), "manifest_files": len(members),
            "manifest_bytes": sum(row["bytes"] for row in members), "verified_sources": source_count}


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def member(point, vertices):
    a, b, c = vertices
    if any(cross(sub(b, a), sub(c, a))):
        return CHECK44["on_face"](point, vertices)
    lo, hi = min(vertices), max(vertices)
    delta = sub(hi, lo)
    if lo == hi:
        return point == lo
    return not any(cross(sub(point, lo), delta)) and 0 <= dot(sub(point, lo), delta) <= dot(delta, delta)


def triangle(v):
    edges = tuple(sub(v[(k+1)%3], v[k]) for k in range(3))
    bounds = tuple((min(d), max(d)) for d in zip(*v))
    return v, bounds, edges, cross(edges[0], edges[1])


def strict_gap(left, right):
    a, bounds_a, edges_a, na = left
    b, bounds_b, edges_b, nb = right
    if any(x[1] < y[0] or y[1] < x[0] for x, y in zip(bounds_a, bounds_b)):
        return True
    axes = [na, nb]
    axes.extend(cross(e, f) for e, f in product(edges_a, edges_b))
    if not any(cross(na, nb)):
        axes.extend(cross(na, e) for e in edges_a + edges_b)
    for axis in axes:
        if any(axis):
            x = [dot(p, axis) for p in a]
            y = [dot(p, axis) for p in b]
            if max(x) < min(y) or max(y) < min(x):
                return True
    return False  # Absence of a separating certificate is inconclusive.


def decode_square(result):
    n, d, e = result["_exact_distance_sq"]
    return Q(n, d)*Q(2)**e


def primitive_axis(direction):
    denom = math.lcm(*(Q(x).denominator for x in direction))
    axis = tuple(int(x*denom) for x in direction)
    divisor = math.gcd(*axis)
    return tuple(x//divisor for x in axis)


def positive_minima(first, second, axes, threshold):
    # A strict projected lower bound eliminates a triangle pair. All remaining
    # pairs get the independent exact Minkowski-hull calculation from review 044.
    def ranges(triangles, axis):
        dots = [[dot(p, axis) for p in triangle[0]] for triangle in triangles]
        return [(min(vals), max(vals)) for vals in dots]
    bounds = [(ranges(first, a), ranges(second, a), dot(a, a)*threshold.numerator) for a in axes]
    ties = []
    exact_pairs = 0
    for i, left in enumerate(first):
        for j, right in enumerate(second):
            for r, s, limit in bounds:
                gap = max(0, r[i][0]-s[j][1], s[j][0]-r[i][1])
                if gap*gap*threshold.denominator > limit:
                    break
            else:
                exact_pairs += 1
                value = CHECK44["project_difference"](left[0], right[0])
                assert value >= threshold
                if value == threshold:
                    ties.append((i, j))
    assert ties
    return ties, exact_pairs


def check_cases(frozen, replay, lower):
    geo = read(checked(frozen["g60_material"]["NATIVE_GEOMETRY.json"]))["objects"]
    meta = {row["id"]: row for row in frozen["g60_cases"]}
    scale = max(Q(v).denominator for item in geo.values() for p in item["vertices_world_m"] for v in p)
    meshes, integer_faces = {}, {}
    for name, item in geo.items():
        vertices = [tuple(map(Q, v)) for v in item["vertices_world_m"]]
        faces = item["triangles"]
        iv = [tuple(int(x*scale) for x in p) for p in vertices]
        meshes[name] = vertices, faces
        integer_faces[name] = [triangle([iv[k] for k in tri]) for tri in faces]
    family = read(checked(frozen["family"]["geometry"]))
    small = {row["id"]: row for row in read(checked(frozen["controls"]))["inputs"]}
    oracle = CHECK44["family"]()
    truth044 = read(checked(read(checked(frozen["family"]["truth"]))["original_independent_oracle"]))
    cases, by_id, zero_checks, positives = [], {}, {}, {}
    positive_oracles = {}
    for record in replay["paired_cases"]:
        ident = record["case"]
        normal, diag = (read(checked(record[k])) for k in ("normal", "diagnostic"))
        a = normal["A"]["result"]
        for arm in ("A", "C"):
            ordinary, diagnostic = normal[arm], diag[arm]
            assert ordinary["status"] == diagnostic["status"] == "returned"
            original, traced = ordinary["result"], diagnostic["result"]
            assert original.keys() == a.keys()
            assert original.keys() <= traced.keys()
            assert traced.keys()-original.keys() <= {"witness_triangle_indices", "exact_witness_triangles"}
            assert all(a[k] == original[k] == traced[k] for k in a if k != "work")
            assert normal["A"]["public_fact"] == ordinary["public_fact"] == diagnostic["public_fact"]
        assert a["measurement_valid"] is True
        sq = decode_square(a)
        wa, wc = (diag[arm]["witness"] for arm in ("A", "C"))
        for field in ("exact_world_witness", "winner_native_rows"):
            assert wa[field] == wc[field]
        points = [tuple(map(Q, q)) for q in wa["exact_world_witness"]]
        rows = tuple(wa["winner_native_rows"])
        diff = sub(points[1], points[0])
        assert dot(diff, diff) == sq
        if ident in meta:
            names = meta[ident]["ordered_names"]
            endpoints = [meshes[n] for n in names]
            by_id[tuple(meta[ident]["ordered_object_ids"])] = normal
        else:
            data = family if ident == "closed-044" else small[ident]
            endpoints = [([tuple(map(Q, p)) for p in data[k]["vertices_world"]], data[k]["faces"])
                         for k in ("left", "right")]
        for point, idx, (vertices, faces) in zip(points, rows, endpoints):
            assert member(point, [vertices[k] for k in faces[idx]])
        if a["witness_status"] == "measured":
            assert [list(map(float, q)) for q in points] == [a["point_a_world"], a["point_b_world"]]
        if ident in meta and sq == 0:
            left, right = (integer_faces[name] for name in names)
            earlier = [(i, j) for i, j in product(range(len(left)), range(len(right))) if (i, j) < rows]
            excluded = sum(strict_gap(left[i], right[j]) for i, j in earlier)
            zero_checks[ident] = {"earlier_rows": len(earlier), "strict_separations": excluded}
        elif ident in meta:
            assert 0 < lower[tuple(sorted(names))] <= sq
            x, y = endpoints[0][0], endpoints[1][0]
            # A common supporting direction and an attained upper bound establish exact minimality.
            positives[ident] = min(dot(diff, pt) for pt in y) - max(dot(diff, pt) for pt in x) >= sq
            pair = tuple(sorted(names))
            if pair not in positive_oracles:
                matrix = geo[pair[0]]["matrix_world"]
                axes = [(1, 0, 0), (0, 1, 0), (0, 0, 1), primitive_axis(diff)]
                axes.extend(primitive_axis(tuple(Q(matrix[i][j]) for i in range(3))) for j in range(3))
                ties, exact_pairs = positive_minima(integer_faces[pair[0]], integer_faces[pair[1]],
                                                    axes, sq*scale**2)
                positive_oracles[pair] = sq, ties, exact_pairs
            minimum, ties, _ = positive_oracles[pair]
            ordered = ties if tuple(names) == pair else [(j, i) for i, j in ties]
            assert sq == minimum and rows == min(ordered)
        elif ident == "closed-044":
            assert rows == tuple(min(oracle["ties"])) and sq == Q(oracle["square"])
            assert [list(map(str, q)) for q in points] == truth044["exact_points_world_m"]
        elif ident == "047_binary64_point_segment_rounding":
            assert sq == Q(1, 2**104 * ((2**50)**2 + (2**50+1)**2))
            assert sq > 0 and a["point_a_world"] is a["point_b_world"] is None
            assert a["witness_reason"] == "original_surface_witness_precision_exceeded"
            assert normal["A"]["public_fact"]["status"] == "unknown" and a["direction_status"] == "measured"
        else:
            assert ident == "coplanar_crossing_multifeature_tie" and rows == (0, 0)
            assert sq == 0 and points[0] == points[1] == (0, Q(3, 2), 0)
        cases.append(ident)
    assert len(cases) == len(set(cases)) == 79 and len(by_id) == 76
    assert len(zero_checks) == 55 and len(positives) == 21
    return by_id, {"matched_cases": len(cases), "g60_ordered": len(by_id),
        "g60_zero_pairs": len(zero_checks), "earlier_rows_checked": sum(x["earlier_rows"] for x in zero_checks.values()),
        "earlier_rows_strictly_separated": sum(x["strict_separations"] for x in zero_checks.values()),
        "zero_pairs_certified_lexicographic": sum(x["earlier_rows"] == x["strict_separations"] for x in zero_checks.values()),
        "positive_inputs": len(positives), "single_direction_full_mesh_certificates": sum(positives.values()),
        "positive_native_pair_obligations": sum(len(integer_faces[a])*len(integer_faces[b]) for a,b in positive_oracles),
        "positive_exact_primitive_evaluations": sum(v[2] for v in positive_oracles.values()),
        "positive_global_min_and_canonical_row_checked": len(positives),
        "zero_by_case": zero_checks, "family_oracle_pairs": oracle["total_pairs"],
        "family_minimizing_rows": oracle["ties"], "shared_rounding_control": True}


def compare_wire(by_id, lower):
    totals = {"nearest_replies": 0, "scan_replies": 0, "identical_work_dicts": 0}
    for host in sorted(OLD.glob("G??-*")):
        for arm in ("A", "C"):
            cell = host / arm / "client"
            traces = {x["trace_id"]: x for line in (cell / "AUDIT.jsonl").read_text(encoding="utf-8").splitlines()
                      if (x := json.loads(line))["event"] == "observe"}
            for number in (5, 6):
                reply = json.loads(read(cell / f"{number:03}.RX.bin")["result"]["content"][0]["text"])
                assert reply["status"] == "complete" and reply["unresolved"] == []
                work = traces[reply["trace_id"]]["task_work"]["pairs"]
                available = {}
                for key, item in work.items():
                    pair = (reply["focal"]["id"], key) if number == 5 else tuple(json.loads(key))
                    result = by_id[pair][arm]["result"]
                    assert not item["surface_pair_cache_hit"] and result["work"] == item["surface_work"]
                    totals["identical_work_dicts"] += 1
                    available[pair] = result
                if number == 5:
                    least = min(decode_square(v) for v in available.values())
                    winners = [p for p, v in available.items() if decode_square(v) == least]
                    assert len(work) == 11 and len(winners) == 1
                    assert [x["id"] for x in reply["nearest_objects"]] == [winners[0][1]]
                    assert reply["nearest_objects"][0]["name"] == "Peer_000"
                    assert all(v > least for p, v in lower.items() if "Peer_000" not in p)
                    ev = reply["best_known_evidence"][0]
                    for k in ("point_a_world", "point_b_world", "direction_a_to_b", "direction_status", "witness_status"):
                        assert ev[k] == available[winners[0]][k]
                    assert reply["distance_m"] == available[winners[0]]["distance_m"]
                    totals["nearest_replies"] += 1
                else:
                    hits = sorted(p for p, v in available.items() if decode_square(v) <= Q(reply["threshold_m"])**2)
                    assert len(work) == 66 and len(hits) == 57 and len(reply["matches"]) == len(hits)
                    assert reply["coverage"]["unknown"] == reply["coverage"]["deferred"] == 0
                    assert reply["coverage"]["measured_nonmatch"] == 9
                    for p, published in zip(hits, reply["matches"]):
                        assert tuple(x["id"] for x in published["objects"]) == p
                        for k in ("distance_m", "point_a_world", "point_b_world", "witness_status"):
                            assert published[k] == available[p][k]
                    totals["scan_replies"] += 1
    assert totals == {"nearest_replies": 12, "scan_replies": 12, "identical_work_dicts": 924}
    return totals


if __name__ == "__main__":
    frozen = read(RAW / "FREEZE.json")
    replay = read(RAW / "primary_001/REPLAY.json")
    base = integrity(frozen, replay)
    lower, _ = CHECK47["input_projections"]()
    by_id, cases = check_cases(frozen, replay, lower)
    boundary = CHECK47["previous_ordinary_runs"]()["boundary_129"]
    result = {"integrity": base, "cases": cases, "original_wire": compare_wire(by_id, lower),
              "ordinary_129": boundary, "new_product_kernel_calls_in_review": 0, "new_host_timing_samples": 0}
    print(json.dumps(result, indent=2))
