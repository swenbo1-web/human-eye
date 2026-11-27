"""Independent 044 check on archived native meshes, actual wire replies and work ledgers."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import struct
import subprocess
from fractions import Fraction
from pathlib import Path


RAW = Path("D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET")
WORK = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe")
ASSET = WORK/"verification/closed_solid_read_001/inputs"
COMMIT = "126f7fe0f77a4220fc639055caa3c959fffb1c26"
SRC = "verification/m6_r3_fresh_budget_044"
PINS = {"A":"a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d",
        "B":"ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e",
        "C":"b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e"}


def read(p):
    return json.loads(Path(p).read_bytes())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def integrity():
    index = RAW/"RAW_EVIDENCE.json"
    assert sha(index) == "cf894c450eeadb3aac47a49202a1913b5a0731e1e227f9b0404e856323e2177b"
    manifest = read(index)
    files = {Path(row["path"]).as_posix() for row in manifest["files"]}
    assert files == {p.relative_to(RAW).as_posix() for p in RAW.rglob("*") if p.is_file() and p != index}
    for row in manifest["files"]:
        p = RAW/row["path"]
        assert p.stat().st_size == row["bytes"] and sha(p) == row["sha256"]
    assert sum(row["bytes"] for row in manifest["files"]) == manifest["bytes"]
    git = subprocess.check_output(["git","-C",str(WORK),"ls-tree","-r",COMMIT,"--",SRC]).splitlines()
    for entry in git:
        hdr, name = entry.split(b"\t")
        blob = (WORK/name.decode()).read_bytes()
        assert hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest() == hdr.split()[-1].decode()
    source_files = 0
    for arm, pin in PINS.items():
        d = read(RAW/"pressure/final_plain_001"/arm/"RESULT.json")["source_verification"]
        binding = read(d["binding"]["path"])
        assert binding["identity"]["source_sha256"] == pin and len(binding["source_files"]) == 143
        for row in binding["source_files"]:
            assert sha(Path(d["site"])/row["path"]) == row["sha256"]
        source_files += len(binding["source_files"])
    return dict(raw_files=len(files),raw_bytes=manifest["bytes"],git_files=len(git),source_files=source_files)


def sub(p,q):
    return tuple(x-y for x,y in zip(p,q))


def dot(p,q):
    return sum(x*y for x,y in zip(p,q))


def project_difference(left,right):
    # The difference of two solid triangles is the convex hull of nine vertex differences.
    # Find a minimum-norm point on hull simplices and check its supporting plane against all nine.
    points = set(sub(a,b) for a in left for b in right)
    u = min(points,key=lambda p:dot(p,p))
    best, denominator, squared = u, 1, dot(u,u)

    def consider(candidate, denom):
        nonlocal best,denominator,squared
        score = dot(candidate,candidate)
        if score*denominator**2 < squared*denom**2:
            best,denominator,squared = candidate,denom,score

    for a,b in itertools.combinations(points,2):
        edge = sub(b,a)
        q = dot(edge,edge)
        n = -dot(a,edge)
        if 0 < n < q:
            consider(tuple(q*x+n*y for x,y in zip(a,edge)),q)
    for a,b,c in itertools.combinations(points,3):
        u,v = sub(b,a),sub(c,a)
        uu,uv,vv = dot(u,u),dot(u,v),dot(v,v)
        q = uu*vv-uv*uv
        au,av = -dot(a,u),-dot(a,v)
        s,t = au*vv-av*uv,av*uu-au*uv
        if s > 0 and t > 0 and s+t < q:
            consider(tuple(q*x+s*y+t*z for x,y,z in zip(a,u,v)),q)
    assert all(dot(best,v)*denominator >= squared for v in points)
    return Fraction(squared,denominator**2)


def bits(points):
    return b"".join(struct.pack("<3d",*p) for p in points)


def validate_snapshots(meshes, folders):
    for path in folders:
        by_name = {o["name"]:o for o in read(path)["objects"]}
        for name, (vertices,faces) in meshes.items():
            for kind in ("native","evaluated"):
                part = by_name[name][kind]
                assert bits(part["vertices_world_m"]) == bits(vertices) and part["triangles"] == faces
                assert part["source_triangle_rows"] == list(range(len(faces)))


def on_face(point, vertices):
    a,b,c = vertices
    u,v,w = sub(b,a),sub(c,a),sub(point,a)
    uu,uv,vv = dot(u,u),dot(u,v),dot(v,v)
    det = uu*vv-uv*uv
    s,t = (dot(w,u)*vv-dot(w,v)*uv)/det,(dot(w,v)*uu-dot(w,u)*uv)/det
    return s>=0 and t>=0 and s+t<=1 and all(x==s*y+t*z for x,y,z in zip(w,u,v))


def family():
    expected = {"scene.blend":"a1a593fc1591365bbbff0c62c535af90ab8b1cdd2dc5ce560d3922252c4e1fcb",
                "author_mesh_snapshots.json":"5a089d22faad7c90b9a28c6ea408ea8b73e8b939e47a3cb66a193ba85f23fc14",
                "TRUTH.json":"d01b0006ef1d4416c8b40663e8aabb7ba64730c7c833b516c3ee1631651a38ff"}
    assert all(sha(ASSET/name)==d for name,d in expected.items())
    names = ("Object_01","Object_02")
    meshes = {o["name"]:(o["world_vertices"],o["faces"])
              for o in read(ASSET/"author_mesh_snapshots.json")["initial"]["objects"] if o["name"] in names}
    root = RAW/"live_family/attempt_002"
    validate_snapshots(meshes,[root/"BEFORE.json",root/"AFTER.json"])
    # All binary64 coordinates are dyadic. Use one common integer lattice for exact feature tests.
    scale = max(float(x).as_integer_ratio()[1] for pts,_ in meshes.values() for p in pts for x in p)
    parts = []
    for name in names:
        vertices,faces = meshes[name]
        pts = [tuple(int(Fraction(x)*scale) for x in v) for v in vertices]
        parts.append([[pts[i] for i in f] for f in faces])
    scores = {(i,j):project_difference(a,b) for i,a in enumerate(parts[0]) for j,b in enumerate(parts[1])}
    low = min(scores.values())
    ties = sorted([list(pair) for pair,s in scores.items() if s==low])
    exact = low / scale**2
    archived = read(RAW/"oracle/TRUTH.json")
    assert ties == sorted(archived["all_minimizing_source_triangle_pairs"])
    assert exact == Fraction(archived["exact_distance_squared_world_m2"])
    witness = [tuple(map(Fraction,p)) for p in archived["exact_points_world_m"]]
    assert dot(sub(*witness),sub(*witness)) == exact
    for name,idx,p in zip(names,ties[0],witness):
        pts,faces = meshes[name]
        assert on_face(p,[list(map(Fraction,pts[k])) for k in faces[idx]])
    return dict(total_pairs=len(scores),ties=ties,square=str(exact),points=[list(map(float,p)) for p in witness])


def pressure():
    root = RAW/"pressure"
    freeze=read(root/"FINAL_FREEZE.json")
    assert sha(root/"FINAL_FREEZE.json")=="fabf8b50eec1f85e102bf3ad2ad78322fcf42bfc99e2adb976b1dd7336df8325"
    for key in ("calibration","selection_rule","geometry","exact_truth"):
        assert sha(freeze[key]["path"]) == freeze[key]["sha256"]
    calibration=read(freeze["calibration"]["path"])
    assert calibration["arm"]=="B" and calibration["prepaid"]==0 and calibration["work"]["narrow_phase_pairs"]==2304
    density = min(math.isqrt(cap*96*48**2//(100*calibration["work"][key]))
                  for key,cap in (("narrow_phase_pairs",16384),("work_units",1179648)))
    assert density==freeze["n"]==125
    doc = read(freeze["geometry"]["path"])
    meshes = {m["name"]:(m["vertices_world"],m["faces"]) for m in (doc["left"],doc["right"])}
    path=RAW/"live_pressure/attempt_001"
    validate_snapshots(meshes,[path/"SAVED_RAM.json",path/"BEFORE.json",path/"AFTER.json"])
    saved,reopened=read(path/"SAVED_ARTIFACT.json"),read(path/"reopen/READY.json")
    assert saved["writer_pid"]!=reopened["pid"] and sha(saved["asset"]["path"])==saved["asset"]["sha256"]
    # Lower bounds in two orthogonal directions add in squared length. Check all actual triangles.
    def intervals(m):
        vertices=[tuple(map(Fraction,v)) for v in m["vertices_world"]]
        out=[]
        for face in m["faces"]:
            pts=[vertices[i] for i in face]
            ranges=[]
            for axis in ((1,-1,0),(1,1,-2)):
                values=[dot(p,axis) for p in pts]
                ranges.append((min(values),max(values)))
            out.append(ranges)
        return out
    def squared_lower(a,b):
        return sum(max(xlo-yhi,ylo-xhi,0)**2/Fraction(norm)
                   for (xlo,xhi),(ylo,yhi),norm in zip(a,b,(2,6)))
    left,right=intervals(doc["left"]),intervals(doc["right"])
    lower={(i,j):squared_lower(a,b) for i,a in enumerate(left) for j,b in enumerate(right)}
    low=min(lower.values())
    possible=[pair for pair,x in lower.items() if x==low]
    assert low==Fraction(3,32768) and possible==[(124,124)]
    def extremum(m, index, choose):
        pts=[tuple(map(Fraction,m["vertices_world"][i])) for i in m["faces"][index]]
        x=[p for p in pts if dot(p,(1,-1,0))==choose(dot(v,(1,-1,0)) for v in pts)]
        assert len(x)==1
        return x[0]
    a,b=extremum(doc["left"],124,max),extremum(doc["right"],124,min)
    assert dot(a,(1,-1,0))==dot(b,(1,-1,0)) and dot(sub(a,b),sub(a,b))==low
    return dict(total_pairs=len(lower),strict_exclusions=len(lower)-len(possible),ties=[list(x) for x in possible],
                square=str(low),points=[list(map(float,p)) for p in (a,b)],density=density)


def queue_and_wire(case, root, diag, oracle):
    raw_arms, facts = {}, []
    for arm,pin in PINS.items():
        folder=root/arm/"client"
        hello=read(folder/"001.RX.bin")["result"]["_meta"]["human_eye"]
        assert hello["source_sha256"]==pin and hello["source_file_count"]==143
        assert read(folder/"CONFIG.json")["request_budget_s"] == 30
        tx,rx=read(folder/"004.TX.bin"),read(folder/"004.RX.bin")
        assert tx["id"]==rx["id"] and not rx["result"]["isError"]
        body=json.loads(rx["result"]["content"][0]["text"])
        wire=body["facts"]
        facts.append(wire)
        surface=wire["surface_proximity"]
        w=surface["value"]["nearest_witness"]
        assert surface["status"]=="measured" and [w["a"],w["b"]]==oracle["points"]
        assert surface["value"]["distance_m"]==math.sqrt(float(Fraction(oracle["square"])))
        if case=="family":
            assert wire["closed_solid_relation"]["value"]=="separated"
        [event]=[x for x in map(json.loads,(folder/"AUDIT.jsonl").read_text(encoding="utf8").splitlines()) if x.get("event")=="observe"]
        assert event["trace_id"]==body["trace_id"] and event["runtime_identity"]["build_id"]=="sha256:"+pin
        assert event["identity_check"]["compatible"] and event["identity_check"]["actual"]["source_sha256"]==pin
        task=event["task_work"]
        assert task["surface_pair_count"]==1 and not task["surface_pair_cache_hit"] and not task["result_cache_hit"]
        work=task["surface_work"]
        if case=="family":
            diagnostic=read(diag/arm/"RESULT.json")
            assert diagnostic["prepaid"]==0 and diagnostic["work"]==work
        else:
            plain=read(RAW/"pressure/final_plain_001"/arm/"RESULT.json")
            assert plain["prepaid"]==0 and plain["start_ns"]<plain["end_ns"]<=plain["deadline_ns"]
            assert plain["result"]["witness_triangle_indices"]==oracle["ties"][0]
            assert plain["work"]["work_units"]-work["work_units"]==2
            assert not plain["instrumented"]
        closed=read(folder/"CLOSE.json")
        assert closed["method"]=="eof" and closed["exit_code"]==0
        raw_arms[arm]={"narrow":work["narrow_phase_pairs"],"work":work["work_units"],
                       "leaf_pairs":work["leaf_pair_visits"],"candidate_pairs":work["triangle_pairs"],
                       "reported_witness_projection_pruned":work.get("witness_projection_pruned_pairs"),
                       "narrow_pct":100*work["narrow_phase_pairs"]/16384,"work_pct":100*work["work_units"]/1179648}
    assert facts[0]==facts[1]==facts[2]
    events=read(diag/"C/POP_EVENTS.json")
    changed=sum(e["serial"]!=e["original_rule_first"][2] for e in events)
    assert changed==read(diag/"C/RESULT.json")["queue"]["counters"]["pop_differs_from_original_rule_on_same_queue"]
    return dict(ordinary=raw_arms,separate_diagnostic_pops=len(events),different_pops=changed)


def cleanup_receipts():
    pids=set()
    for path in ("live_family/POST_PROCESS_CHECK_02.json","live_pressure/POST_PROCESS_CHECK.json"):
        check=read(RAW/path)
        assert check["all_expected_pids_absent"] and not check["currently_existing_expected_ids"]
        ids=set(check["expected_owned_pids"])
        assert pids.isdisjoint(ids)
        pids.update(ids)
    return sorted(pids)


if __name__=="__main__":
    evidence=integrity()
    a,b=family(),pressure()
    a.update(queue_and_wire("family",RAW/"live_family/attempt_002",RAW/"family_diagnostic_001",a))
    b.update(queue_and_wire("pressure",RAW/"live_pressure/attempt_001",RAW/"pressure/final_queue_diagnostic_001",b))
    assert b["ordinary"]["A"]["reported_witness_projection_pruned"] == 13955
    assert all(b["ordinary"][k]["candidate_pairs"] == b["ordinary"][k]["narrow"] == 125**2 for k in "BC")
    results=dict(commit=COMMIT,integrity=evidence,independent_family=a,independent_pressure=b,
                 archive_cleanup_absent_pids=cleanup_receipts(),
                 observed_fresh_B_known_C_unknown=0,actual_inputs=2)
    p=Path(__file__).with_name("INDEPENDENT_044.json")
    p.write_bytes((json.dumps(results,indent=2)+"\n").encode())
    print(p)
