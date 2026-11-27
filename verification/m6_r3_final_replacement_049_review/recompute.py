"""Independent final review. Run with the project dependency Python and -I -B."""
import base64
import csv
import hashlib
import io
import itertools
import json
import math
import re
import runpy
import statistics
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from fractions import Fraction as Q
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
IMPL = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe")
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT")
BASE = "6c93f2375d1073b33e721a168f1fcf610ac6dbdc"
COMMIT = "a5323d6df54ddcbd953b132a305ba9eb2d4db304"
PARENT = "0c50036f451ef28cdc95f8b1c9e0cb10a0bcd170"
SCOPE = "verification/m6_r3_final_replacement_049"
INDEX = "d57ff7b42bf63661c5de88c5ffd168df21b96a91198658a1563fe5983e97cc3a"
read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda blob: hashlib.sha256(blob).hexdigest()
pins = read(RAW / "candidate/PINS.json")


def git(*args):
    return subprocess.check_output(["git", "-C", str(IMPL), *args])


def integrity():
    path = RAW / "RAW_EVIDENCE.json"
    assert sha(path.read_bytes()) == INDEX
    manifest = read(path)["files"]
    names = {v["path"].replace("\\", "/") for v in manifest}
    actual = {f.relative_to(RAW).as_posix() for f in RAW.rglob("*") if f.is_file()}
    assert actual == names | {path.name} and len(names) == len(manifest)
    for v in manifest:
        blob = (RAW / v["path"]).read_bytes()
        assert len(blob) == v["bytes"] and sha(blob) == v["sha256"], v["path"]
    assert git("rev-parse", COMMIT+"^").decode().strip() == PARENT
    files = git("diff", "--name-only", PARENT, COMMIT).decode().splitlines()
    for name in files:
        assert name.startswith(SCOPE+"/")
        assert (IMPL/name).read_bytes() == git("show", f"{COMMIT}:{name}"), name
    wheel = Path(pins["wheel"]["path"])
    assert sha(wheel.read_bytes()) == pins["wheel"]["sha256"] == "308dd624cb4916b28bbe2decae87ac0a80d05dfad793da5afecebc65ac698964"
    site = Path(pins["site"])
    src = Path(pins["source"])
    tracked = pins["source_manifest"]
    key = dict(files=tracked, **{k:pins["identity"][k] for k in ("base_version","implementation_revision")})
    assert sha(json.dumps(key, sort_keys=True, separators=(",", ":")).encode()) == pins["source_sha256"]
    assert {row["path"] for row in tracked} == {f.relative_to(site).as_posix() for f in site.rglob("*.py")}
    with zipfile.ZipFile(wheel) as z:
        [record] = [n for n in z.namelist() if n.endswith(".dist-info/RECORD")]
        entries = list(csv.reader(io.StringIO(z.read(record).decode())))
        assert len(entries) == len(set(z.namelist())) == len(z.namelist())
        assert {v[0] for v in entries} == set(z.namelist())
        for n, h, size in entries:
            blob = z.read(n)
            assert blob == (site/n).read_bytes()
            if n != record:
                assert int(size) == len(blob) and h == "sha256="+base64.urlsafe_b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
        for row in tracked:
            blob = z.read(row["path"])
            assert blob == (src/row["path"]).read_bytes() and sha(blob) == row["sha256"]
    # Compare the packaged fallback to the original Git objects, allowing only private import names.
    for mod in ("surface_geometry","surface_proximity"):
        blob = git("show", f"{BASE}:human_eye_plugin/{mod}.py").decode().splitlines()
        renamed = (site/f"human_eye_plugin/_{mod}_032.py").read_text("utf8").replace(
            "from ._surface_geometry_032 import", "from .surface_geometry import").replace(
            "from . import _surface_proximity_032 as exact", "from . import surface_proximity as exact")
        assert renamed.splitlines() == blob, mod
    hook_names = [v["path"] for v in tracked if "hook" in v["path"].lower()]
    comparison_site = Path(pins["baseline_A"]["path"]).parents[1]/"site-packages"
    hook_git_differences = []
    for n in hook_names:
        assert (site/n).read_bytes() == (comparison_site/n).read_bytes(), n
        if (site/n).read_bytes().splitlines() != git("show", f"{BASE}:{n}").splitlines():
            hook_git_differences.append(n)
    recovery=read(RAW/"isolated_baseline/RECOVERY.json")
    for k in ("baseline_wheel","baseline_launcher","baseline_binding","startup_receipt"):
        ref=recovery[k]
        assert sha(Path(ref["path"]).read_bytes())==ref["sha256"]
    # Local protected config observation only, never executed or modified by this review.
    hook_config=Path("D:/hefe/.codex/hooks.json")
    registered=[]
    for event, groups in read(hook_config)["hooks"].items():
        for group in groups:
            for hook in group["hooks"]:
                command=hook["command"]
                m=re.search(r"(?i)-EncodedCommand\s+([A-Za-z0-9+/=]+)",command)
                if not m:
                    continue
                decoded=base64.b64decode(m.group(1)).decode("utf-16-le")
                for name in re.findall("'([^']+)'",decoded):
                    if name.endswith("target_runtime_entry.py"):
                        launcher=Path(name)
                        registered.append(dict(event=event,release=launcher.parents[1].name,
                                               hook_sha=sha((launcher.parents[1]/"site-packages/human_eye_hook.py").read_bytes())))
    return dict(raw_files=len(manifest), raw_bytes=sum(v["bytes"] for v in manifest), raw_index=INDEX,
                git_files=len(files), wheel_sha=pins["wheel"]["sha256"], wheel_entries=len(entries),
                identity=pins["source_sha256"], python_files=len(tracked), same_as_matched_hook_install=hook_names,
                hook_files_different_from_historical_032_git=hook_git_differences,
                candidate_hook_sha=sha((site/"human_eye_hook.py").read_bytes()),
                existing_desktop_project_hook_sha=sha(hook_config.read_bytes()),registered_project_hook_entries=registered,
                baseline_recovery_package_verified=True)


def install_child(site):
    # Isolated target of a normal local pip install. All Human Eye modules must be served by this directory.
    sys.path.insert(0, str(site))
    import importlib.abc
    import importlib.machinery
    import importlib.metadata
    class LocalOnly(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.startswith("human_eye"):
                spec = importlib.machinery.PathFinder.find_spec(fullname, path)
                if not spec or not Path(spec.origin).resolve().is_relative_to(site):
                    raise ImportError("Plugin import outside the wheel: "+fullname)
                return spec
            return None
    sys.meta_path.insert(0, LocalOnly())
    if sys.argv[1]=="--stdio":
        [entry]=[ep for ep in importlib.metadata.distribution("human-eye-spatial-plugin").entry_points
                 if ep.group=="console_scripts" and ep.name=="human-eye-mcp-server"]
        raise SystemExit(entry.load()(["--config",sys.argv[3]]))
    from human_eye_plugin import surface_proximity
    from human_eye_plugin.runtime_identity import runtime_identity
    identity = runtime_identity(mode="live")
    assert identity["source_sha256"] == pins["source_sha256"] and len(identity["source_files"]) == 145
    assert importlib.metadata.version("human-eye-spatial-plugin") == pins["version"]
    outcomes = {}
    for c in read(RAW/"coverage/offline/CASES_02.json"):
        if c["id"] not in ("pressure129", "pressure125", "original031_different_pair129", "old048_closed-044", "old048_g60-01", "analytic_unique_zero_plain"):
            continue
        meshes = [SimpleNamespace(name=v["name"], object_id=v["name"], vertices=v["vertices_world"], faces=v["faces"]) for v in c["endpoints"]]
        result = surface_proximity.measure_surface_proximity(*meshes, lambda *_: None, retain_exact_rank=True, retain_witness_triangles=True)
        expected = read(RAW/"coverage/offline/attempt_001/F"/c["id"]/"DIAGNOSTIC.json")["result"]
        for field in ("measurement_valid", "distance_m","point_a_world", "point_b_world", "direction_a_to_b","reason","_exact_distance_sq"):
            assert json.dumps(result.get(field)) == json.dumps(expected.get(field)), (c["id"],field)
        tri = result.get("exact_witness_triangles",{}).get("indices",result.get("witness_triangle_indices"))
        if c.get("canonical") and result["measurement_valid"]:
            assert list(tri) == c["canonical"]
        w = result["work"]
        outcomes[c["id"]] = dict(route=w["solver_path"], distance_m=result.get("distance_m"), reason=result.get("reason"),
                                 triangles=tri, narrow=w["narrow_phase_pairs"], work=w["work_units"])
    modules = {k for k,v in sys.modules.items() if k.startswith("human_eye") and getattr(v,"__file__",None)}
    assert all(Path(sys.modules[k].__file__).resolve().is_relative_to(site) for k in modules)
    return dict(fresh_install=True, imported_from_this_wheel=len(modules), calls=outcomes)


def isolated_install():
    with tempfile.TemporaryDirectory(prefix="he049_review_") as tmp:
        dest = Path(tmp).resolve()/"site"
        subprocess.run([sys._base_executable,"-I","-B","-m","pip","--isolated","--disable-pip-version-check",
                        "install","--no-index","--no-deps","--no-compile","--target",str(dest),pins["wheel"]["path"]],
                       check=True, stdout=subprocess.DEVNULL)
        result = subprocess.check_output([sys.executable,"-I","-B", str(Path(__file__).resolve()),"--installed",str(dest)])
        info=json.loads(result)
        config=read(RAW/"g60_b02/G60/main_001/G01-ABF/F/client/CONFIG.json")
        config.update(project_root=str(dest),state_file=str(Path(tmp)/"state.json"),audit_file=str(Path(tmp)/"audit.jsonl"))
        config["blender"]["port"]=1
        cfg=Path(tmp)/"private_config.json"
        cfg.write_text(json.dumps(config),encoding="utf8")
        frames=[{"id":"1","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},
                     "clientInfo":{"name":"049-review","version":"1"}}},{"method":"notifications/initialized"},
                {"id":"2","method":"tools/list"},{"id":"3","method":"ping"}]
        msg="".join(json.dumps(dict(jsonrpc="2.0",**frame))+"\n" for frame in frames).encode()
        stdout=subprocess.check_output([sys.executable,"-I","-B",str(Path(__file__).resolve()),"--stdio",str(dest),str(cfg)],
                                       input=msg,timeout=30)
        replies=[json.loads(s) for s in stdout.splitlines() if s.strip()]
        assert [r["id"] for r in replies]==["1","2","3"] and all("result" in r for r in replies)
        identity=replies[0]["result"]["_meta"]["human_eye"]
        assert identity["source_sha256"]==pins["source_sha256"] and identity["source_file_count"]==145
        info["console_entry_registration"]=[v["name"] for v in replies[1]["result"]["tools"]]
        info["stdio_initialize_list_ping_eof"]=True
        return info


def wire(folder, n):
    tx, rx = (read(folder/f"{n:03}.{direction}.bin") for direction in ("TX","RX"))
    assert tx["method"] == "tools/call" and tx["id"] == rx["id"] and not rx["result"]["isError"]
    return tx["params"], json.loads(rx["result"]["content"][0]["text"])


def pressure_oracle(snapshot, case):
    # Bounds from two perpendicular directions. Only the minimizing face pair can
    # attain the exact bound, and one original vertex from each face attains it.
    axes = ((1,-1,0),(1,1,-2))
    intervals = []
    meshes = []
    for spec in case["endpoints"]:
        native = next(o["evaluated"] for o in snapshot["objects"] if o["name"]==spec["name"])
        faces, verts = native["triangles"], native["vertices_world_m"]
        assert (faces,verts)==(spec["faces"],spec["vertices_world"])
        assert native["source_triangle_rows"]==list(range(len(faces)))
        tris = [[tuple(map(Q,verts[i])) for i in f] for f in faces]
        meshes.append(tris)
        def interval(tri, axis):
            values=[sum(x*y for x,y in zip(pt,axis)) for pt in tri]
            return min(values),max(values)
        intervals.append([[interval(tri,axis) for axis in axes] for tri in tris])
    minimum=Q(3,32768);possible=[]
    for i,l in enumerate(intervals[0]):
        for j,r in enumerate(intervals[1]):
            lower=sum(Q(max(0,a-d,c-b)**2,n) for (a,b),(c,d),n in zip(l,r,(2,6)))
            assert lower>=minimum
            if lower==minimum:
                possible.append([i,j])
    assert possible==[case["canonical"]]
    i,j=possible[0]
    pairs=[(a,b) for a,b in itertools.product(meshes[0][i],meshes[1][j]) if sum((x-y)**2 for x,y in zip(a,b))==minimum]
    assert len(pairs)==1
    return dict(source_faces=possible[0], native_pairs=len(meshes[0])*len(meshes[1]), square=str(minimum),
                points=[list(map(float,pt)) for pt in pairs[0]])


def exact_geometry():
    member = runpy.run_path(str(HERE.parent/"m6_r3_witness_parity_048_review/recompute.py"))["member"]
    cases = read(RAW/"coverage/offline/CASES_02.json")
    out = {}
    checked = 0
    positive_lost = []
    for c in cases:
        cid = c["id"]
        arms = {}
        for a in "ACF":
            src = RAW/"coverage/offline/attempt_001"/a/cid
            normal, diag = (read(src/f"{n}.json") for n in ("ORDINARY","DIAGNOSTIC"))
            val, dv = normal["result"], diag["result"]
            factual = {k:v for k,v in val.items() if k not in ("work","witness_triangle_indices","exact_witness_triangles")}
            assert all(dv[k] == v for k,v in factual.items()), (cid,a)
            assert normal["public_fact"] == diag["public_fact"]
            rows = (dv.get("exact_witness_triangles",{}).get("indices") or dv.get("witness_triangle_indices")
                    or diag.get("witness",{}).get("winner_native_rows"))
            points = (diag.get("witness",{}).get("exact_world_witness") or dv.get("exact_witness_triangles",{}).get("points_m")
                      or (c.get("unique_exact_points") if dv["measurement_valid"] else None))
            if dv["measurement_valid"]:
                assert rows is not None and points is not None,(cid,a)
                exact = [tuple(map(Q,pt)) for pt in points]
                for point, row, mesh in zip(exact,rows,c["endpoints"],strict=True):
                    triangle = [tuple(map(Q,mesh["vertices_world"][i])) for i in mesh["faces"][row]]
                    assert member(point,triangle), (cid,a,row)
                    checked += 1
                sq = sum((u-v)**2 for u,v in zip(*exact))
                num,den,exp = dv["_exact_distance_sq"]
                assert sq == Q(num,den)*Q(2)**exp
                if c.get("expected_q") is not None:
                    assert sq == Q(c["expected_q"])
                if c.get("canonical") is not None:
                    assert rows == c["canonical"]
                if c["kind"]=="shared":
                    assert diag["closed_fact"]["value"]=="touching" and rows == [9,4] and exact == [(1,1,1)]*2
                    assert all(diag["graph"]["surface_pre"].values()) and diag["graph"]["closed_post"]["contact_pair_identity"]
            else:
                assert val["distance_m"] is None and val["point_a_world"] is None and val["point_b_world"] is None
            arms[a] = (factual, normal["public_fact"], rows)
        assert arms["F"] == arms["A"],cid
        if c.get("old048_ordinary"):
            ref=c["old048_ordinary"]
            data=Path(ref["path"]).read_bytes()
            assert sha(data)==ref["sha256"]
            old=json.loads(data)["A"]["result"]
            assert all(old.get(k)==arms["F"][0].get(k) for k in ("distance_m","point_a_world","point_b_world","direction_a_to_b","_exact_distance_sq"))
        if arms["C"][0]["measurement_valid"] and not arms["F"][0]["measurement_valid"]:
            positive_lost.append(cid)
        out[cid] = (arms["F"][0]["measurement_valid"], arms["F"][2])
    assert len(out)==84 and checked==498 and positive_lost==["original031_different_pair129"]
    pressure, truth = {}, {}
    for size in (125,129):
        d=RAW/f"coverage/live/attempt_001/{size}"
        before,after=read(d/"BEFORE.json"),read(d/"AFTER.json")
        assert before["objects"]==after["objects"]
        truth[size]=pressure_oracle(before,next(c for c in cases if c["id"]==f"pressure{size}"))
        measurements={}
        for arm in "ACF":
            client=d/arm/"client"
            _,body=wire(client,4)
            fact=body["facts"]["surface_proximity"]
            [event]=[v for line in (client/"AUDIT.jsonl").read_text("utf8").splitlines() if (v:=json.loads(line)).get("event")=="observe"]
            assert event["trace_id"]==body["trace_id"] and not event["task_work"]["surface_pair_cache_hit"]
            w=event["task_work"]["surface_work"]
            if arm=="C" and size==129:
                assert fact["status"]=="unknown" and fact["reason"]=="surface_pair_budget" and "distance_m" not in fact["value"]
            else:
                assert fact["value"]["distance_m"]==math.sqrt(3/32768)
                raw=read(RAW/f"coverage/offline/attempt_001/{arm}/pressure{size}/DIAGNOSTIC.json")["result"]
                witness=fact["value"]["nearest_witness"]
                assert [witness["a"],witness["b"]]==[raw["point_a_world"],raw["point_b_world"]]
                assert [witness["a"],witness["b"]]==truth[size]["points"]
            measurements[arm]=[fact["status"],w["narrow_phase_pairs"],w["work_units"]]
        assert measurements["A"]==measurements["F"]
        pressure[size]=measurements
    controls={}
    for arm in "ACF":
        c=read(RAW/f"coverage/offline/attempt_001/{arm}/REJECTION_LIFECYCLE_CONTROLS.json")
        assert c["cancel"]=={"same_exception_propagated":True,"returned_result":False}
        assert c["expiry"]["code"]=="live_request_expired" and c["expiry"]["same_fixed_deadline"]
        for name in ("invalid_indices","empty_source"):
            assert not c[name]["measurement_valid"]
        for name in ("immutable_source_replaced","mutable_source_changed"):
            assert c[name]["before"]["distance_m"]!=c[name]["after"]["distance_m"]
        controls[arm]={k:c[k]["reason"] for k in ("invalid_indices","empty_source")}
    assert controls["F"]==controls["A"]
    g10=read(RAW/"g10_existing_rejection/RESULTS.json")
    for attempt in g10["arms"].values():
        obs=attempt["observations"]
        assert attempt["exit_code"]==0 and obs["bit_width"]["result"]["reason"]=="surface_exact_bit_budget"
        assert obs["face_limit"]["result"]["reason"]=="surface_geometry_work_limit"
    return dict(cases=len(out),primary_and_diagnostic=6*len(out), exact_point_memberships=checked,
                A_F_cases_equal=sum(1 for _ in out), A_F_distance_known=sum(v[0] for v in out.values()),
                C_only_known=positive_lost, normal_host_pressure=pressure, independent_pressure_minima=truth,
                controls=controls, bit_width_and_face_caps="preserved")


if __name__ == "__main__":
    if sys.argv[1:2] in (["--installed"],["--stdio"]):
        print(json.dumps(install_child(Path(sys.argv[2]))))
    else:
        outputs = {"integrity": integrity, "install": isolated_install, "coverage": exact_geometry}
        if sys.argv[1:]==["--save"]:
            scenes=runpy.run_path(str(HERE/"scene_receipts.py"))
            report={key: test() for key,test in outputs.items()}
            report["host"]={k:scenes["group_data"](k) for k in ("G60","B02")}
            report["host"].update(Yanyite=scenes["yanyite"](),spots=scenes["spots"]())
            report["reviewed_commit"]=COMMIT
            report["decision"]="qualified_for_existing_BVH_with_current_Hook_registration"
            (HERE/"RESULTS.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n",encoding="utf8",newline="\n")
        else:
            print(json.dumps({key: outputs[key]() for key in (sys.argv[1:] or outputs)}, indent=2))
