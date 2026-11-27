"""Untimed original A/F work replay on the actual H3 materialized geometry."""
from __future__ import annotations

import argparse
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT/yanyite")
def read(p): return json.loads(Path(p).read_bytes())
def pin(p):
    p=Path(p).resolve(strict=True); b=p.read_bytes()
    return {"path":str(p),"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
def save(p,v):
    p=Path(p).resolve(); assert p.is_relative_to(RAW.resolve()); p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("x",encoding="utf8",newline="\n") as f: json.dump(v,f,indent=2,allow_nan=False);f.write("\n")
    return pin(p)
def child(intent_path):
    intent=read(intent_path); out=Path(intent_path).parent
    rec={"status":"failed","intent":pin(intent_path),"source":pin(__file__),"errors":[],"not_a_timing_sample":True}
    try:
        ref=intent["capture"]; assert pin(ref["path"])==ref
        captured=read(ref["path"])["capture"]
        binding=read(intent["binding"]["path"]);assert pin(intent["binding"]["path"])==intent["binding"]
        site=Path(binding["site_packages"])
        for row in binding["source_files"]: assert pin(site/row["path"])["sha256"]==row["sha256"]
        sys.path.insert(0,str(site))
        from human_eye_plugin import surface_proximity as k
        from human_eye_plugin.active_observation_images import _meshes_from_objects
        assert Path(k.__file__).resolve()==(site/"human_eye_plugin/surface_proximity.py").resolve()
        rec["identity"]=binding["identity"]
        region,reference=captured["region"],captured["reference"]
        meshes=_meshes_from_objects(tuple((m["vertices"],m["faces"],(captured["payload_sha256"],name),captured["binding"][name]["name"])
            for name,m in (("target",region),("reference",reference))))
        work,holder={},{};deadline=time.monotonic()+30;start=time.perf_counter_ns();cpu=time.process_time_ns()
        def cp(stage):
            rec["last_checkpoint"]=stage
            if time.monotonic()>=deadline:raise TimeoutError(stage)
        measured=k.measure_surface_proximity(*meshes,cp,diagnostics=work,_prepared_holder=holder,retain_witness_triangles=True)
        rec.update(result=measured,work=work,wall_ns=time.perf_counter_ns()-start,cpu_ns=time.process_time_ns()-cpu,
            source_geometry={"capture":ref,"original_region_rows":region["source_triangle_indices"],"faces":[len(m.faces) for m in meshes]})
        assert measured["measurement_valid"] and measured["witness_status"]=="measured"
        origin,factor=holder["pair"][2:4];pts=holder["witness_points"]
        exact=[[Q(origin[i])+Q(p[i])/factor for i in range(3)] for p in pts]
        rec["exact_world_points"]=[[str(v) for v in p] for p in exact]
        rec["exact_squared"]=str(sum((a-b)**2 for a,b in zip(*exact)))
        tri=measured.get("exact_witness_triangles",{}).get("indices",measured.get("witness_triangle_indices"))
        assert tri is not None
        native=[region["source_triangle_indices"][tri[0]],tri[1]]
        rec["native_pair"]=native
        expected=intent["public"]
        assert measured["distance_m"].hex()==expected["distance_m"].hex()
        assert measured["point_a_world"]==expected["point_a_m"] and measured["point_b_world"]==expected["point_b_m"]
        assert measured["direction_a_to_b"]==expected["direction_a_to_b"]
        assert native==[expected["source_triangle_a"],expected["source_triangle_b"]]
        rec["status"]="pass"
    except BaseException:rec["errors"].append(traceback.format_exc())
    print(json.dumps(save(out/"RESULTS.json",rec)),flush=True);return int(rec["status"]!="pass")

def run():
    plan=read(RAW/"PLAN.json"); main=read(RAW/"main_001/H3/functional/RESULTS.json")
    out=RAW/"H3_replay_001";out.mkdir()
    receipt={"status":"failed","source":pin(__file__),"functional":pin(RAW/"main_001/H3/functional/RESULTS.json"),
        "calls":[],"kernel_calls_planned":8,"performance_samples":0}
    rows=main["arms"]["F"]["rows"]
    for item in main.get("offline_inputs",[]):
        region=item["region"]
        for state in ("before","after"):
            capture=item[state]
            label=region+("_after" if state=="after" else "_first")
            public=next(r["result"] for r in rows if r["step"]==label)
            for arm in "AF":
                folder=out/(region+"_"+state+"_"+arm);folder.mkdir()
                intent={"capture":capture,"binding":plan["arms"][arm]["binding"],"public":public,"region":region,"state":state,"arm":arm}
                save(folder/"INTENT.json",intent)
                cmd=[plan["arms"][arm]["command_prefix"][0],"-I","-B",str(Path(__file__).resolve()),"--child",str(folder/"INTENT.json")]
                p=subprocess.run(cmd,capture_output=True,timeout=60)
                (folder/"STDOUT.bin").write_bytes(p.stdout);(folder/"STDERR.bin").write_bytes(p.stderr)
                receipt["calls"].append({"arm":arm,"region":region,"state":state,"command":cmd,"returncode":p.returncode,
                    "receipt":pin(folder/"RESULTS.json") if (folder/"RESULTS.json").is_file() else None,
                    "stdout":pin(folder/"STDOUT.bin"),"stderr":pin(folder/"STDERR.bin")})
    receipt["status"]="pass" if len(receipt["calls"])==8 and all(r["returncode"]==0 for r in receipt["calls"]) else "failed"
    print(json.dumps(save(out/"RESULTS.json",receipt)),flush=True);return int(receipt["status"]!="pass")

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--child",type=Path);args=parser.parse_args()
    raise SystemExit(child(args.child) if args.child else run())
