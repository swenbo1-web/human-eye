"""Read the fixed 045 artifacts, verify public results, and test two observed projection directions."""
import hashlib
import itertools
import json
import math
import runpy
import statistics
import subprocess
from fractions import Fraction
from pathlib import Path


HERE = Path(__file__).resolve().parent
helpers = runpy.run_path(str(HERE.parent / "m6_r3_fresh_budget_044_review" / "recompute.py"))
read, sha, dot, sub = (helpers[name] for name in ("read", "sha", "dot", "sub"))
PINS, WORK = helpers["PINS"], helpers["WORK"]
RAW = Path("D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY")
CASE = RAW / "boundary/attempt_001"
G60 = RAW / "g60/main_001"
OLD = Path("D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/live/g60/main_001/G01-ABC/A/client")
COMMIT = "83897bc2fa626bc86a141e3e63fff3c9f59ab75a"
SCOPE = "verification/m6_r3_replacement_entry_045"


def bound(record):
    path = Path(record["path"])
    assert sha(path) == record["sha256"] and path.stat().st_size == record["bytes"]
    return path


def integrity():
    path = RAW / "RAW_EVIDENCE.json"
    assert sha(path) == "516f5fc62e944482c6a35d5c89980ebad9359a7ac915322a23a3c62b5a83d149"
    index = read(path)
    names = {row["path"] for row in index["files"]}
    assert len(names) == index["file_count"] == 748
    assert names == {f.relative_to(RAW).as_posix() for f in RAW.rglob("*") if f.is_file() and f != path}
    for row in index["files"]:
        bound(dict(row, path=RAW / row["path"]))
    assert sum(row["bytes"] for row in index["files"]) == index["total_bytes"]
    entries = subprocess.check_output(["git", "-C", str(WORK), "ls-tree", "-r", COMMIT, "--", SCOPE]).splitlines()
    for entry in entries:
        meta, name = entry.split(b"\t")
        data = (WORK / name.decode()).read_bytes()
        oid = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert oid == meta.split()[-1].decode()
    plan = read(RAW / "g60/PLAN.json")
    for arm, pin in PINS.items():
        manifest = read(bound(plan["release_bindings"][arm]))
        assert manifest["identity"]["source_sha256"] == pin and len(manifest["source_files"]) == 143
        site = Path(plan["arms"][arm]["site_packages"])
        for row in manifest["source_files"]:
            assert sha(site / row["path"]) == row["sha256"]
    return dict(files=len(names), bytes=index["total_bytes"], implementation_blobs=len(entries), installed_sources=429)


def vertex_witness(left, right):
    # A supporting pair on both convex hulls establishes the minimum without calling any tested kernel.
    for a, b in itertools.product(left, right):
        direction = sub(b, a)
        if all(dot(direction, sub(v, a)) <= 0 for v in left) and all(dot(direction, sub(v, b)) >= 0 for v in right):
            return direction, (a, b)
    raise AssertionError("Missing vertex support in one of the first two observed pairs")


def independent_geometry():
    freeze = read(RAW / "oracle/FINAL_FREEZE.json")
    assert freeze["n"] == math.isqrt(16384) + 1 and freeze["limits"]["work_units"] == 1179648
    for name in ("plan", "generator", "geometry", "exact_truth"):
        bound(freeze[name])
    doc = read(freeze["geometry"]["path"])
    original = {doc[k]["name"]: (doc[k]["vertices_world"], doc[k]["faces"]) for k in ("left", "right")}
    helpers["validate_snapshots"](original, [CASE / k for k in ("SAVED_RAM.json", "BEFORE.json", "AFTER.json")])
    saved, opened = read(CASE / "SAVED_ARTIFACT.json"), read(CASE / "reopen/READY.json")
    assert saved["writer_pid"] != opened["pid"]
    bound(saved["asset"])

    def mesh(side):
        vertices = [tuple(map(Fraction, v)) for v in doc[side]["vertices_world"]]
        return [[vertices[i] for i in face] for face in doc[side]["faces"]]

    left, right = mesh("left"), mesh("right")
    attempts = {arm: read(RAW / "boundary_diagnostic" / arm / "NARROW_ATTEMPTS.json") for arm in PINS}
    seed = [e["pair"] for e in attempts["B"][:2]]
    assert seed == [e["pair"] for e in attempts["C"][:2]] == [[127, 128], [128, 128]]
    assert all(e["completed"] for arm in ("B", "C") for e in attempts[arm][:2])
    previous, current = [vertex_witness(left[i], right[j]) for i, j in seed]
    axis, points = current
    upper = dot(axis, axis)
    assert upper == Fraction(3, 32768)

    def census(direction):
        norm = dot(direction, direction)
        def span(triangle):
            projected = [dot(direction, p) for p in triangle]
            return min(projected), max(projected)
        ls, rs = list(map(span, left)), list(map(span, right))
        strict, equal, survivors = 0, 0, []
        for (i, (lo, hi)), (j, (low, high)) in itertools.product(enumerate(ls), enumerate(rs)):
            gap = max(0, lo - high, low - hi)
            diff = gap * gap - norm * upper
            strict += diff > 0
            equal += diff == 0
            if diff <= 0:
                survivors.append([i, j])
        return int(strict), int(equal), survivors

    strict, equal, remaining = census(previous[0])
    assert (strict, equal, remaining) == (16640, 0, [seed[-1]])
    now_strict, now_equal, _ = census(axis)
    assert (now_strict, now_equal) == (0, 129)
    # The previous axis excludes all other pairs strictly. Unique attaining points on
    # the winning faces follow from their unique touching extrema along the tangent.
    tangent = (1, -1, 0)
    lv = [dot(tangent, v) for v in left[128]]
    rv = [dot(tangent, v) for v in right[128]]
    assert lv.count(max(lv)) == rv.count(min(rv)) == 1 and max(lv) == min(rv)
    assert dot(points[0], tangent) == dot(points[1], tangent) == max(lv)
    assert attempts["A"][-1]["pair"] == remaining[0] and len(attempts["A"]) == 1918
    exact = read(freeze["exact_truth"]["path"])
    assert str(upper) == exact["distance_squared_exact"] and remaining == exact["all_minimizing_source_triangle_pairs"]
    return dict(square=str(upper), points=[list(map(float, p)) for p in points], winner=remaining[0], pairs=len(left)*len(right),
                observed_first_two=seed, first_witness_square=str(dot(previous[0], previous[0])),
                first_direction=[str(x) for x in previous[0]], final_direction=[str(x) for x in axis],
                first_axis_at_current_upper_strict=strict, first_axis_equal=equal,
                final_axis_at_current_upper_strict=now_strict, final_axis_equal=now_equal,
                writer_pid=saved["writer_pid"], reader_pid=opened["pid"])


def wire(folder, message):
    tx, rx = (read(folder / f"{message:03}.{way}.bin") for way in ("TX", "RX"))
    assert tx["id"] == rx["id"] and tx["method"] == "tools/call" and not rx["result"]["isError"]
    return tx["params"], json.loads(rx["result"]["content"][0]["text"])


def identity(folder, arm):
    info = read(folder / "001.RX.bin")["result"]["_meta"]["human_eye"]
    assert info["source_sha256"] == PINS[arm] and info["source_file_count"] == 143
    assert read(folder / "CLOSE.json")["exit_code"] == 0


def public_boundary(geometry):
    output, requests = {}, []
    for arm in PINS:
        client = CASE / arm / "client"
        identity(client, arm)
        request, body = wire(client, 4)
        assert read(client / "CONFIG.json")["request_budget_s"] == 30
        requests.append(request)
        fact = body["facts"]["surface_proximity"]
        audit = [json.loads(line) for line in (client / "AUDIT.jsonl").read_text(encoding="utf8").splitlines()]
        [event] = [e for e in audit if e.get("event") == "observe"]
        assert event["trace_id"] == body["trace_id"] and event["identity_check"]["actual"]["source_sha256"] == PINS[arm]
        task = event["task_work"]
        assert task["surface_pair_count"] == 1 and not task["surface_pair_cache_hit"] and not task["result_cache_hit"]
        w = task["surface_work"]
        diag = read(RAW / "boundary_diagnostic" / arm / "RESULT.json")
        assert w == diag["work"] and w["work_units"] < 1179648
        if arm == "A":
            witness = fact["value"]["nearest_witness"]
            assert fact["status"] == "measured" and body["status"] == "observed"
            assert [witness["a"], witness["b"]] == geometry["points"]
            assert fact["value"]["distance_m"] == math.sqrt(float(Fraction(geometry["square"])))
            assert w["narrow_phase_pairs"] + w["witness_projection_pruned_pairs"] == geometry["pairs"]
        else:
            assert body["status"] == "partial" and fact["status"] == "unknown" and fact["reason"] == "surface_pair_budget"
            assert set(fact["value"]) == {"topology"}
            assert w["narrow_phase_pairs"] == 16384 and w["leaf_pair_visits"] == 16385
            assert w["witness_projection_directions"] == 1 and w.get("witness_projection_pruned_pairs", 0) == 0
        output[arm] = dict(fact=fact["status"], reason=fact.get("reason"), exact=w["narrow_phase_pairs"],
                           strict_or_tie_projection_prunes=w.get("witness_projection_pruned_pairs", 0),
                           work=w["work_units"], first_denied=diag["first_cap_guard"])
    assert requests[0] == requests[1] == requests[2]
    return output


def normalized(request, body, n):
    if n == 4:
        return request, body["status"], [v["name"] for v in body["objects"]]
    keys = (("status", "coverage", "nearest_objects", "distance_m", "best_known_evidence", "unresolved")
            if n == 5 else ("status", "coverage", "threshold_m", "matches", "unresolved"))
    return request, {k: body[k] for k in keys}


def live_g60():
    anchors = {n: normalized(*wire(OLD, n), n) for n in (4, 5, 6)}
    groups, file_counts, file_bytes, archival_ms, orders = [], 0, 0, [], []
    for group in sorted(G60.glob("G??-*")):
        receipt = read(group / "GROUP.json")
        assert receipt["gui_close"]["process_reaped"] and receipt["gui_close"]["released_port"]
        orders.append(receipt["order"])
        slots = {}
        for arm in receipt["order"]:
            cell = read(group / arm / "CELL.json")
            client = group / arm / "client"
            identity(client, arm)
            for n in anchors:
                request, result = wire(client, n)
                assert normalized(request, result, n) == anchors[n]
            life = cell["lifecycle"]
            events = {e["name"]: e for e in life["events"]}
            ws = life["processes"]
            wrapper, service = ws["wrapper"], ws["service"]
            for process in (wrapper, service):
                assert process["owned_held_handle"] and process["alive_at_bind"] and process["exit_code"] == 0
                assert process["bind_times"]["creation_time_100ns"] == process["creation_time_100ns"]
            assert wrapper["pid"] == cell["wrapper_pid"] == service["parent_pid"]
            assert service["pid"] == cell["product_pid"] and wrapper["pid"] != service["pid"]
            exited = max(p["exit_time_100ns"] for p in (wrapper, service))
            assert exited <= events["archive_begin"]["filetime_100ns"]
            assert life["reader"]["joined_and_inactive"] and events["reader_join_end"]["at_ns"] <= events["archive_begin"]["at_ns"]
            files = list(client.glob("*.bin"))
            assert len(files) == 11
            file_counts += len(files)
            file_bytes += sum(f.stat().st_size for f in files)
            archival_ms.append((events["archive_end"]["at_ns"] - events["archive_begin"]["at_ns"]) / 1e6)
            # Retain the original instrument's final decoded-business boundary. Do not move
            # the endpoint to the inner decoder return or to the timestamp written to disk.
            business = cell["last_reply_ns"] - cell["rows"][0]["timing"]["started_ns"]
            survival = (exited - wrapper["creation_time_100ns"]) * 100
            client_ns = cell["workflow_end_ns"] - cell["workflow_start_ns"]
            assert (business, survival, client_ns) == (cell["business_ns"], life["os_survival_ns"], cell["workflow_ns"])
            slots[arm] = dict(business=business/1e6, process=survival/1e6, client=client_ns/1e6)
        groups.append(slots)
    assert sorted(orders) == ["".join(v) for v in itertools.permutations("ABC")]
    rows = {}
    for metric in ("business", "process", "client"):
        item = {}
        for baseline, candidate in (("A","B"), ("A","C"), ("B","C")):
            gains = [(1 - g[candidate][metric]/g[baseline][metric])*100 for g in groups]
            item[candidate+"_vs_"+baseline] = dict(reduction_pct=gains, median=statistics.median(gains),
                                                   faster=sum(v > 0 for v in gains))
        rows[metric] = item
    freed = read(RAW / "G60_RELEASE_CHECK.json")
    assert all(r["gone"] for r in freed["actual"]) and len(freed["actual"]) == 44 and freed["released_owned_GUI_ports"] == 6
    assert read(RAW / "boundary/POST_PROCESS_CHECK.json")["all_expected_pids_absent"]
    return dict(cells=groups, orders=orders, deltas=rows, wire_replies=18*3,
                archive_files=file_counts, archive_bytes=file_bytes, max_archive_ms=max(archival_ms))


if __name__ == "__main__":
    digests = integrity()
    geometry = independent_geometry()
    result = dict(commit=COMMIT, integrity=digests, geometry=geometry, public=public_boundary(geometry), g60=live_g60())
    print(json.dumps(result, indent=2, allow_nan=False))
