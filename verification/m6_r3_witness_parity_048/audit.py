"""Independently bind exact witness geometry, thresholds and public archived fields."""
from collections import Counter
from fractions import Fraction as Q
from pathlib import Path
from time import monotonic_ns, process_time_ns
import json
import math
import sys

from freeze import RAW, check, git_file, read, save
from replay import load_inputs


def subtract(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def on_hull(point, vertices):
    a, b, c = vertices
    u, v, p = subtract(b, a), subtract(c, a), subtract(point, a)
    for i, j in ((0, 1), (0, 2), (1, 2)):
        determinant = u[i] * v[j] - u[j] * v[i]
        if determinant:
            s = (p[i] * v[j] - p[j] * v[i]) / determinant
            t = (u[i] * p[j] - u[j] * p[i]) / determinant
            return s >= 0 and t >= 0 and s+t <= 1 and p == tuple(s*x+t*y for x, y in zip(u, v))
    lower, upper = min(vertices), max(vertices)
    if lower == upper:
        return point == lower
    edge, displacement = subtract(upper, lower), subtract(point, lower)
    index = next(i for i, x in enumerate(edge) if x)
    parameter = displacement[index] / edge[index]
    return 0 <= parameter <= 1 and displacement == tuple(parameter*x for x in edge)


def check_membership(result, diag, inputs):
    witness = diag["witness"]
    points = [tuple(map(Q, point)) for point in witness["exact_world_witness"]]
    rows = witness["winner_native_rows"]
    assert len(points) == len(rows) == 2
    for row, source, point in zip(rows, inputs, points):
        assert 0 <= row < len(source["faces"])
        corners = [tuple(map(Q, source["vertices_world"][i])) for i in source["faces"][row]]
        assert on_hull(point, corners), (source["name"], row, point)
    delta = subtract(*points[::-1])
    distance_sq = Q(result["semantic"]["_exact_distance_sq"])
    assert dot(delta, delta) == distance_sq
    out = result["result"]
    if out["witness_status"] == "measured":
        assert [out["point_a_world"], out["point_b_world"]] == [[float(v) for v in p] for p in points]
    return rows, points, distance_sq


def check_subset(observed, original, fields):
    assert {key: observed.get(key) for key in fields} == {key: original.get(key) for key in fields}


def original_public(frozen, case_rows):
    ledger = {tuple(case["ordered_object_ids"]): case["id"] for case in frozen["g60_cases"]}
    history = {entry["id"]: entry for case in frozen["g60_cases"] for entry in case["history"]}
    passed = []
    # Public replay requires all of the original request's actually measured pairs.
    for request in read(check(frozen["g60_material"]["REQUESTS.json"])):
        check(request["request"])
        packet = read(check(request["response"]))
        arm, mode = request["arm"], request["step"]
        if mode == "overview" or arm not in "AC":
            continue
        assert packet["result"].get("isError", False) is False
        raw = json.loads(packet["result"]["content"][0]["text"])
        cells = [row for cid, row in history.items() if cid.startswith(request["id"]+"/")]
        ids = [tuple(row["ordered_object_ids"]) for row in cells]
        needed = 11 if mode == "nearest" else 66
        assert len(ids) == needed
        missing = [ledger[k] for k in ids if ledger[k] not in case_rows]
        if missing:
            passed.append({"id": request["id"], "status": "incomplete_due_to_stop", "missing": missing})
            continue
        available = {key: case_rows[ledger[key]][arm] for key in ids}
        assert raw["status"] == "complete"
        assert raw["unresolved"] == []
        if mode == "nearest":
            assert raw["coverage"] == {"targets_excluding_focal": 11, "distance_valid": 11,
                                       "strictly_excluded": 0, "unresolved": 0}
            keys = {obj_ids[1]: Q(row["semantic"]["_exact_distance_sq"]) for obj_ids, row in available.items()}
            best = min(keys.values())
            equal = sorted(key for key, value in keys.items() if value == best)
            assert [row["id"] for row in raw["nearest_objects"]] == equal
            assert [row["id"] for row in raw["best_known_objects"]] == equal
            assert [row["candidate"]["id"] for row in raw["best_known_evidence"]] == equal
            for item in raw["best_known_evidence"]:
                pair = (raw["focal"]["id"], item["candidate"]["id"])
                row = available[pair]["result"]
                assert raw["distance_m"] == raw["best_known_distance_m"] == row["distance_m"]
                check_subset(row, item, ("point_a_world", "point_b_world", "direction_a_to_b",
                                         "witness_status", "witness_reason", "direction_status", "direction_reason"))
            count = len(equal)
        else:
            threshold = Q(raw["threshold_m"])**2
            hits = sorted(key for key, row in available.items()
                          if Q(row["semantic"]["_exact_distance_sq"]) <= threshold)
            assert raw["coverage"] == {"objects": 12, "total_pairs": 66, "bound_excluded": 0,
                                       "measured_match": len(hits), "measured_nonmatch": 66-len(hits),
                                       "unknown": 0, "deferred": 0, "catalog_scope_confirmed": True}
            got = [tuple(obj["id"] for obj in match["objects"]) for match in raw["matches"]]
            assert got == hits
            for pair, item in zip(got, raw["matches"]):
                fields = ("distance_m", "point_a_world", "point_b_world", "witness_status", "method")
                check_subset(available[pair]["result"], item, fields)
            count = len(got)
        passed.append({"id": request["id"], "status": "matches_archived_public_fields",
                       "reconstructed_from": needed, "published_witness_rows": count})
    return passed


def check_original_nonmatch_diagnostics(frozen, cases):
    rows = read(check(frozen["g60_material"]["PAIR_CALLS.json"]))
    by_ids = {tuple(row["ordered_object_ids"]): row["id"] for row in frozen["g60_cases"]}
    reproduced = 0
    for row in rows:
        if row["arm"] not in "AC" or row["step"] != "scan":
            continue
        case = by_ids[tuple(row["ordered_object_ids"])]
        if case not in cases:
            continue
        data = cases[case][row["arm"]]
        assert data["result"]["distance_m"] == row["per_call_public_distance_m"]
        reproduced += 1
    return reproduced


def main(freeze_path, replay_path):
    elapsed_start, start_cpu = monotonic_ns(), process_time_ns()
    frozen = read(freeze_path)
    replay = read(replay_path)
    assert check(replay["freeze"]) == freeze_path.resolve()
    material = load_inputs(frozen)
    comparison = {}
    for item in replay["paired_cases"]:
        case_id = item["case"]
        ordinary, diagnosed = read(check(item["normal"])), read(check(item["diagnostic"]))
        if any(arm["status"] != "returned" for group in (ordinary, diagnosed) for arm in group.values()):
            continue
        rows = {arm: check_membership(ordinary[arm], diagnosed[arm], material[case_id][1])
                for arm in "AC"}
        comparison[case_id] = {"rows": rows, "ordinary_geometry": ordinary,
                               "diagnostics": diagnosed, "binding": item}

    case_table = {key: item["ordinary_geometry"] for key, item in comparison.items()}
    recreated_public = original_public(frozen, case_table)
    disposition_distances = check_original_nonmatch_diagnostics(frozen, case_table)
    review_path = frozen["g60_independent_review"]["path"]
    review = json.loads(git_file(review_path))
    lower = {tuple(row["objects"]): Q(row["square"]) for row in review["input_geometry"]["lower_square_m2"]}
    assert len(lower) == 11 and sum(v > Q(0.005)**2 for v in lower.values()) == 9
    g60_validated = []
    work_matches = Counter()
    work_mismatches = []
    for item in frozen["g60_cases"]:
        case_id = item["id"]
        if case_id not in comparison:
            continue
        observed = comparison[case_id]
        ordered = item["ordered_names"]
        bound = lower.get(tuple(sorted(ordered)), Q(0))
        for arm, (rows, points, square) in observed["rows"].items():
            assert square >= bound
            if not bound:
                assert square == 0, (case_id, square)
        for row in item["history"]:
            arm = row["arm"]
            new = observed["ordinary_geometry"][arm]["result"]["work"]
            old = row["surface_work"]
            if new == old:
                work_matches[arm] += 1
            else:
                work_mismatches.append({"historical_call": row["id"],
                    "different": sorted(key for key in set(new)|set(old) if new.get(key) != old.get(key))})
        a, c = (observed["rows"][arm] for arm in "AC")
        g60_validated.append({"case": case_id, "ordered_names": ordered, "source_lower_square_m2": str(bound),
                             "A": {"rows": a[0], "exact_points": [[str(x) for x in p] for p in a[1]], "square": str(a[2])},
                             "C": {"rows": c[0], "exact_points": [[str(x) for x in p] for p in c[1]], "square": str(c[2])},
                             "kind": {arm: observed["diagnostics"][arm]["witness"]["descriptor_kind"] for arm in "AC"}})
    winners = [row for row in g60_validated if row["ordered_names"] == ["Target", "Peer_000"]]
    if winners:
        winner_bound = min(bound for pair, bound in lower.items() if "Peer_000" not in pair)
        assert all(Q(winners[0][arm]["square"]) < winner_bound for arm in "AC")

    control_reports = {}
    for control in read(check(frozen["controls"]))["inputs"]:
        case_id = control["id"]
        if case_id in comparison:
            observed = comparison[case_id]
            truth = control["independent_truth"]
            for arm, (rows, points, square) in observed["rows"].items():
                assert rows == truth["canonical_source_triangle_pair"]
                assert square == Q(truth["distance_squared_exact"])
                result = observed["ordinary_geometry"][arm]["result"]
                expected_kernel = control.get("expected_kernel_subset",
                                              control.get("expected_kernel_subset_derived_from_static_source"))
                for key, expected in expected_kernel.items():
                    assert result.get(key) == expected, (case_id, arm, key, result.get(key), expected)
                assert observed["diagnostics"][arm]["witness"]["search"] == "linear"
                public_expected = control.get("expected_public_fact_subset_derived_from_static_source")
                if public_expected:
                    assert points == [tuple(map(Q, truth[key])) for key in ("p_exact", "q_exact")]
                    assert result["direction_a_to_b"] == truth["rounded_direction_a_to_b"]
                    assert result["distance_m"].hex() == truth["distance_float_hex"]
                    public = observed["ordinary_geometry"][arm]["public_fact"]
                    witness = public["value"]["nearest_witness"]
                    assert public["status"] == public_expected["status"]
                    assert public["reason"] == public_expected["reason"]
                    assert public["value"]["distance_m"] == public_expected["distance_m_retained"]
                    assert [witness["a"], witness["b"]] == public_expected["nearest_witness_points"]
                    assert (witness["direction_a_to_b"] is not None) == public_expected["direction_retained"]
            control_reports[case_id] = {"valid": True, "diagnostics": observed["binding"],
                "public_fact": {arm: observed["ordinary_geometry"][arm]["public_fact"] for arm in "AC"}}

    family = None
    if "closed-044" in comparison:
        observed = comparison["closed-044"]
        truth = read(check(frozen["family"]["truth"]))
        for arm, (rows, points, square) in observed["rows"].items():
            assert rows == truth["canonical_source_triangle_pair"] == [90, 2]
            assert len(truth["all_minimizing_source_triangle_pairs"]) == 14
            assert square == Q(truth["exact_distance_squared_world_m2"])
            assert [list(point) for point in points] == [[Q(value) for value in point]
                                                         for point in truth["exact_points_world_m"]]
            archive = read(check(frozen["family"]["archive_inputs"]))
            original = read(check(archive["ordinary_public"][arm]))
            historical = original["ordinary_surface_fact"]["value"]
            result = observed["ordinary_geometry"][arm]["result"]
            assert historical["distance_m"] == result["distance_m"]
            assert [historical["nearest_witness"][key] for key in ("a", "b")] == [
                result[key] for key in ("point_a_world", "point_b_world")]
        family = {"truth": truth, "ordinary_exact": {
            arm: {"rows": row[0], "points": [[str(x) for x in p] for p in row[1]], "square": str(row[2])}
            for arm, row in observed["rows"].items()}}
    result = {
        "replay": replay["status"], "first_difference": replay["first_difference"], "not_run": replay["not_run"],
        "g60_qualified_directed_cases": len(g60_validated), "public_requests": recreated_public,
        "historical_scan_disposition_distances_reproduced": disposition_distances,
        "historical_kernel_work_dict_exact_match": dict(work_matches), "work_mismatches": work_mismatches,
        "g60_source_world_hull_membership_and_squared_distance": g60_validated,
        "g60_independently_verified_positive": sum(Q(e["source_lower_square_m2"]) > 0 for e in g60_validated),
        "g60_independently_verified_zero": sum(Q(e["source_lower_square_m2"]) == 0 for e in g60_validated),
        "native_family": family, "controls": control_reports,
        "audit_wall_ns": monotonic_ns()-elapsed_start, "audit_cpu_ns": process_time_ns()-start_cpu,
        "notes": "All world/source membership and point distances use fractions of original binary64 coordinates. "
                 "The 11 source lower bounds establish positive distances and nine threshold rejects; actual upper "
                 "witnesses certify the two positive matches and which candidate wins. Exact minima on nonwinning "
                 "positive pairs are cross-version comparisons, not an independent full enumeration.",
    }
    print(save(RAW / "AUDIT.json", result))


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:]))

