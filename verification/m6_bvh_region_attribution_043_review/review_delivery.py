"""Recompute 043 from the pinned installation, raw geometry, wire replies and clocks."""
from __future__ import annotations

import hashlib
import itertools
import json
import statistics
import subprocess
import zipfile
from collections import Counter, defaultdict
from fractions import Fraction as F
from pathlib import Path

RAW = Path("D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION")
IMPL = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe")
COMMIT = "d54054f2792012aee8cc17ff9e949379720675ad"
REL = "verification/m6_r3_region_attribution_043"
PINS = {"A": "a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d",
        "B": "ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e",
        "C": "b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e"}
MED = statistics.median
ARMS = "ABC"


def read(p):
    return Path(p).read_text(encoding="utf-8-sig")


def data(p):
    return json.loads(read(p))


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def archive():
    index = RAW / "RAW_EVIDENCE.json"
    appendix = RAW / "RAW_EVIDENCE_APPENDIX.json"
    assert digest(index) == "a82ce9b658cec6646487bdb3f9d63c644384cfadf57fc82abf411508b0f89499"
    assert digest(appendix) == "3f8a7411c3e616bdf43e9681293fa013c141b3028617d5665e667a5e811f8c11"
    main, extra = data(index), data(appendix)
    assert extra["prior_inventory"]["sha256"] == digest(index)
    rows = main["files"] + extra["new_files"]
    names = {Path(row["path"]).as_posix() for row in rows}
    assert len(rows) == len(names)
    for row in rows:
        p = RAW / row["path"]
        assert p.stat().st_size == row["bytes"] and digest(p) == row["sha256"], p
    unlisted = sorted(p.relative_to(RAW).as_posix() for p in RAW.rglob("*")
                      if p.is_file() and p.relative_to(RAW).as_posix() not in names)
    assert len(main["files"]) == main["file_count"]
    assert sum(row["bytes"] for row in main["files"]) == main["total_bytes"]
    blobs = subprocess.check_output(["git", "-C", str(IMPL), "ls-tree", "-r", COMMIT, "--", REL]).splitlines()
    for line in blobs:
        head, path = line.split(b"\t", 1)
        payload = (IMPL / path.decode()).read_bytes()
        assert hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest() == head.split()[-1].decode()
    return dict(main=len(main["files"]), appendix=len(extra["new_files"]),
                bytes=sum(row["bytes"] for row in rows), git_files=len(blobs), unlisted=unlisted)


def installations():
    plan = data(RAW / "live/g60/PLAN_03.json")
    manifests = {}
    commands = {}
    for arm, row in plan["arms"].items():
        site = Path(row["site_packages"])
        binding = data(site.parent / "admin/RUNTIME_BINDING.json")
        assert binding["identity"]["source_sha256"] == row["source_sha256"] == PINS[arm]
        files = {item["path"]: item["sha256"] for item in binding["source_files"]}
        assert len(files) == 143
        for path, sha in files.items():
            assert digest(site / path) == sha
        commands[arm] = row["command_prefix"]
        manifests[arm] = files
    assert len({tuple(cmd[:3]) for cmd in commands.values()}) == 1
    templates = {read(cmd[3]).replace(PINS[a], "<SOURCE>")
                 .replace(plan["arms"][a]["version"], "<RELEASE>") for a,cmd in commands.items()}
    assert len(templates) == 1
    changed = [name for name in manifests["B"] if manifests["B"][name] != manifests["C"][name]]
    assert manifests["B"].keys() == manifests["C"].keys() and changed == ["human_eye_plugin/surface_proximity.py"]
    wheel = data(IMPL / REL / "candidate/PINS.json")["wheel"]
    assert digest(wheel["path"]) == wheel["sha256"]
    with zipfile.ZipFile(wheel["path"]) as z:
        for name, sha in manifests["C"].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == sha
    return dict(verified_sources=sum(map(len, manifests.values())), candidate_wheel_sources=len(manifests["C"]),
                source_ids=PINS, changed=changed, launcher_sha={a:digest(c[3]) for a,c in commands.items()})


def point_on_triangle(point, triangle):
    a, b, c = triangle
    u, v, w = [[j - i for i, j in zip(a, p)] for p in (b, c, point)]
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))
    uu, uv, vv, wu, wv = dot(u, u), dot(u, v), dot(v, v), dot(w, u), dot(w, v)
    det = uu * vv - uv * uv
    if not det:
        return False
    s, t = (wu * vv - wv * uv) / det, (wv * uu - wu * uv) / det
    return s >= 0 and t >= 0 and s+t <= 1 and all(x == s*y+t*z for x, y, z in zip(w, u, v))


def cube_oracle(capture, published):
    # For a triangle inside a rectangular box, each signed face clearance is affine.
    # Its minimum over the triangle is attained at a vertex.
    region, ref = capture["region"], capture["reference"]
    verts = [tuple(map(F, v)) for v in region["vertices"]]
    corners = [tuple(map(F, v)) for v in ref["vertices"]]
    ranges = [tuple(sorted(set(col))) for col in zip(*corners)]
    assert all(len(pair) == 2 for pair in ranges) and set(corners) == set(itertools.product(*ranges))
    ref_faces = [[corners[i] for i in t] for t in ref["faces"]]
    sides = defaultdict(list)
    for tri in ref_faces:
        constant = [(k, v) for k in range(3) for v in ranges[k] if all(p[k] == v for p in tri)]
        assert len(constant) == 1 and len(set(tri)) == 3
        sides[constant[0]].append(set(tri))
    assert len(sides) == 6
    for tris in sides.values():
        assert len(tris) == 2
        p, q = tris[0] & tris[1]
        assert sum(x != y for x, y in zip(p, q)) == 2
    cloud = [verts[i] for i in set(itertools.chain.from_iterable(region["faces"]))]
    gap = min(min(pt[k]-lo, hi-pt[k]) for pt in cloud for k, (lo, hi) in enumerate(ranges))
    assert gap > 0 and F(published["distance_m"]) == gap
    pa, pb = (tuple(map(F, published[name])) for name in ("point_a_m", "point_b_m"))
    assert sum((a-b)**2 for a,b in zip(pa,pb)) == gap**2
    assert [float((y-x)/gap) for x,y in zip(pa,pb)] == published["direction_a_to_b"]
    source_faces = dict(zip(region["source_triangle_indices"], region["faces"], strict=True))
    assert len(source_faces) == published["selected_triangle_count"]
    eligible = [i for i, face in source_faces.items() if any(min(verts[v][k]-lo, hi-verts[v][k]) == gap
                 for v in face for k, (lo, hi) in enumerate(ranges))]
    src = min(eligible)
    assert published["source_triangle_a"] == src and point_on_triangle(pa, [verts[i] for i in source_faces[src]])
    ref_idx = min(j for j, tri in enumerate(ref_faces) if point_on_triangle(pb, tri))
    assert ref_idx == published["source_triangle_b"]
    return dict(distance=str(gap), faces=len(source_faces), native_rows=[src,ref_idx])


def mechanism():
    rows = {}
    ev = {}
    for p in sorted((RAW/"mechanism").glob("*.json")):
        t = data(p)
        if "events" not in t:
            continue
        events = t["events"]
        pairs = [e for e in events if e["event"] == "exact_start"]
        assert len(pairs) == t["counters"]["narrow_phase_pairs"]
        accepted = [e for e in events if e["event"] == "best_accepted"]
        final = t["final"]
        assert F(final["square_m2"]) == F(1306219829081343,9007199254740992)**2
        assert final["native_pair"] == [49114,0]
        first = next(e for e in accepted if e["square_m2"] == final["square_m2"])
        canonical = next(e for e in accepted if e["square_m2"] == first["square_m2"] and e["native_pair"] == final["native_pair"])
        rows[p.stem] = dict(exact=len(pairs), first_upper=[first["exact"],first["pops"]],
                            first_canonical=[canonical["exact"],canonical["pops"]],
                            visits=t["counters"]["node_pair_visits"],work=t["counters"]["work_units"],
                            projections=t["counters"].get("witness_projection_tests",0))
        ev[p.stem] = events
    assert rows["B-native"] == rows["B-positive"] and ev["C-native"] == ev["B-zero"]
    return rows


def raw_response(folder, number):
    tx, rx = (data(folder / f"{number:03}.{kind}.bin") for kind in ("TX","RX"))
    assert tx["id"] == rx["id"] and not rx["result"]["isError"]
    content = rx["result"]["content"]
    assert len(content) == 1 and content[0]["type"] == "text"
    return json.loads(content[0]["text"])


def identity_and_eof(folder, arm):
    hello = data(folder / "001.RX.bin")["result"]["_meta"]["human_eye"]
    assert hello["source_sha256"] == PINS[arm] and hello["source_file_count"] == 143
    closed = data(folder / "CLOSE.json")
    assert closed["method"] == "eof" and closed["exit_code"] == 0
    return closed


def paired(groups, candidate="C", base="B"):
    diff = [(x[candidate] - x[base])/1e6 for x in groups]
    pct = [100*(x[candidate]/x[base]-1) for x in groups]
    return dict(delta_ms=MED(diff),delta_percent=MED(pct),faster=sum(x<0 for x in diff),
                n=len(diff),each_delta_ms=diff)


def replay():
    root = RAW / "timing/attempt_001"
    h3 = data(data(RAW / "mechanism/C-native.json")["capture"]["path"])
    raw_hi = data(root / "01_A/repeat.json")["public"]
    oracle = cube_oracle(h3, raw_hi)
    times, orders = [], []
    for i in range(1,13):
        warm, starts = {}, {}
        for arm in ARMS:
            folder = root / f"{i:02}_{arm}"
            process = data(folder/"PROCESS.json")
            starts[arm] = process["start_ns"]
            assert process["reaped"] and process["exit"] == 0
            assert data(folder/"CELL.json")["actual_identity"]["source_sha256"] == PINS[arm]
            for step in ("first","repeat"):
                row = data(folder / (step+".json"))
                assert raw_hi == row["public"]
                ns = row["finished_ns"] - row["started_ns"]
                assert ns == row["full_ns"] and process["start_ns"] < row["started_ns"] < row["finished_ns"] < process["closed_ns"]
                if step == "repeat":
                    warm[arm] = ns
        times.append(warm)
        orders.append("".join(sorted(starts,key=starts.get)))
    assert sorted(Counter(orders).values()) == [2]*6
    return dict(oracle=oracle, orders=orders, C_vs_B=paired(times),C_vs_A=paired(times,"C","A"))


def windows(folder, cell, t0, t1, t2, t3):
    startup = data(folder/"client/STARTUP.json")
    hello, catalog = startup["timing"], startup["tools_time"]
    assert t0 <= hello["started_ns"] < hello["closed_ns"] <= catalog["started_ns"] < catalog["closed_ns"] <= t1 < t2 < t3
    eof = data(folder/"client/CLOSE.json")["wall_ns"]
    return dict(total=t3-t0,business=t2-t1,start=t1-t0,tail=t3-t2,eof=eof,
                before_hello=hello["started_ns"]-t0,hello=hello["closed_ns"]-hello["started_ns"],
                catalog=catalog["closed_ns"]-catalog["started_ns"])


def stage_pairs(groups):
    return {k:paired([{a:x[a][k] for a in ARMS} for x in groups]) for k in groups[0]["C"]}


def yanyite():
    root = RAW/"live/yanyite/attempt_001"
    times, phases, orders = [], [], []
    for host in ("H1","H2","H3"):
        for i in range(1,5):
            clocks, group, starts, facts = {}, {}, {}, []
            for arm in ARMS:
                folder=root/host/f"{host}-P{i}-{arm}"
                cell=data(folder/"CELL.json")
                identity_and_eof(folder/"client",arm)
                assert not cell["errors"] and cell["observed_native_capture_calls"] == 2
                starts[arm] = cell["start_ns"]
                for step, num in (("first_high",4),("warm_high",5)):
                    row=data(folder/(step+".json"))
                    body=raw_response(folder/"client",num)
                    assert body == row["result"] and body["status"] == "complete" and body["selected_triangle_count"] == 262
                    assert body["source_triangle_a"] == 49114 and body["source_triangle_b"] == 0 and F(body["distance_m"]) == F(1306219829081343,9007199254740992)
                    facts.append(body)
                    ns=row["finished_ns"]-row["timing"]["started_ns"]
                    assert ns == row["business_ns"]
                    if step == "first_high":
                        start = row["timing"]["started_ns"]
                    else:
                        clocks[arm] = ns
                        group[arm]=windows(folder,cell,cell["start_ns"],start,row["finished_ns"],cell["end_ns"])
            assert all(x == facts[0] for x in facts)
            times.append(clocks)
            phases.append(group)
            orders.append("".join(sorted(starts,key=starts.get)))
    assert sorted(Counter(orders).values()) == [2]*6
    return dict(orders=orders, warm_C_vs_B=paired(times),warm_C_vs_A=paired(times,"C","A"),
                host_warm_C_minus_A_ms=[paired(times[i:i+4],"C","A")["delta_ms"] for i in range(0,12,4)],
                lifecycle_C_vs_B=stage_pairs(phases))


def g60():
    root=RAW/"live/g60/main_001"
    groups, by_group = [], {}
    for folder in sorted(root.glob("G0*")):
        group, starts = {}, {}
        same_host = defaultdict(list)
        for arm in ARMS:
            path=folder/arm
            cell=data(path/"CELL.json")
            identity_and_eof(path/"client",arm)
            assert cell["valid"] and not cell["errors"]
            for num,step in enumerate(("overview","nearest","scan"),4):
                row=data(path/(step+".json"))
                body=raw_response(path/"client",num)
                assert body == row["result"] and not row["tool_error"] and not row["rpc_error"]
                if step == "overview":
                    assert body["runtime_identity"]["source_sha256"] == PINS[arm]
                    same_host[step].append(body["objects"])
                else:
                    assert body["trace_id"] == row["observe"]["trace_id"]
                    assert body["binding"]["runtime_source_sha256"] == PINS[arm]
                    comparable = {k:v for k,v in body.items() if k != "trace_id"}
                    comparable["binding"] = {k:v for k,v in body["binding"].items() if k != "runtime_source_sha256"}
                    same_host[step].append(comparable)
                    cov=body["coverage"]
                    if step=="nearest":
                        assert (cov["distance_valid"],cov["unresolved"]) == (11,0)
                        assert [x["name"] for x in body["nearest_objects"]] == ["Peer_000"]
                    else:
                        assert [cov[k] for k in ("total_pairs","measured_match","measured_nonmatch","unknown","deferred")] == [66,57,9,0,0]
            t0,t1,t2,t3=(cell["workflow_start_ns"],cell["rows"][0]["timing"]["started_ns"],
                         cell["rows"][-1]["body_decoded_ns"],cell["workflow_end_ns"])
            w=windows(path,cell,t0,t1,t2,t3)
            assert w["total"] == cell["workflow_ns"] and w["business"] == cell["business_ns"]
            starts[arm]=t0
            group[arm]=w
        assert "".join(sorted(starts,key=starts.get)) == folder.name.split("-")[1]
        assert all(v[0]==v[1]==v[2] for v in same_host.values())
        groups.append(group)
        by_group[folder.name] = {a:{k:ns/1e6 for k,ns in g.items()} for a,g in group.items()}
    assert len(groups)==6
    return dict(C_vs_B=stage_pairs(groups),business_C_vs_A=paired([{a:g[a]["business"] for a in ARMS} for g in groups],"C","A"),
                total_C_vs_A=paired([{a:g[a]["total"] for a in ARMS} for g in groups],"C","A"),groups_ms=by_group)


def functional():
    root = RAW/"live/checks/attempt_02"
    out = {}
    for case, names in (("same_asset_low",["first","warm"]),
                        ("real_Cube_edit",["old_first","old_warm","after_edit","after_edit_warm"])):
        folder=root/case/"C"
        rows=[]
        for n,step in enumerate(names,1):
            capture=data(folder/"client/RETURN_OBSERVER"/f"CAPTURE_{n:03}.json")["capture"]
            body=raw_response(folder/"client",n+3)
            assert body==data(folder/(step+".json"))["result"]
            rows.append(dict(step=step,geometry=cube_oracle(capture,body),mode=capture["work"]["mode"],
                             payload=capture["payload_sha256"]))
        out[case]=rows
    edit=out["real_Cube_edit"]
    assert [row["mode"] for row in edit] == ["resident_capture","lease_hit","uncached_capture","resident_capture"]
    assert edit[0]["payload"]==edit[1]["payload"] and edit[2]["payload"]==edit[3]["payload"]!=edit[0]["payload"]
    assert F(edit[-1]["geometry"]["distance"])-F(edit[0]["geometry"]["distance"])==F(1,64)
    return out


def quality():
    results=data(RAW/"quality/RESULTS.json")
    checked=[]
    for ref in results["passed_case_receipts"]:
        p=Path(ref["path"])
        assert digest(p)==ref["sha256"]
        x=data(p)
        assert x["status"]=="pass" and set(x["arms"])==set(ARMS)
        for arm in ARMS:
            a=x["arms"][arm]
            r=a["result"]
            if r.get("measurement_valid"):
                n,d,e=r["_exact_distance_sq"]
                exact=F(n,d)*F(2)**e
                pa,pb=(list(map(F,v)) for v in a["exact_points_world"])
                assert sum((u-v)**2 for u,v in zip(pa,pb))==exact
                if "independent_oracle" in x:
                    assert exact==F(x["independent_oracle"]["distance_squared"])
                if "analytical_distance_squared" in x:
                    assert exact==F(x["analytical_distance_squared"])
            assert r.get("measurement_valid")==x["arms"]["B"]["result"].get("measurement_valid") or arm=="A"
        checked.append(p.stem)
    return dict(checked=checked,original_state_difference=results["explicit_original_status_difference"])


if __name__ == "__main__":
    result=dict(implementation=COMMIT,archive=archive(),installation=installations(),mechanism=mechanism(),
                quality=quality(),offline=replay(),yanyite=yanyite(),g60=g60(),functional=functional())
    path=Path(__file__).with_name("INDEPENDENT_DELIVERY_043.json")
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(path)
