"""S1. Isolated standard Blender add-on, ordinary installed stdio and measured requests."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, sys, time, traceback
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
PLAN=ROOT/"PLAN_recovery_01.json"
SLOTS=ROOT/"slots_recovery_01"
PINS=ROOT.parent/"install/PINS.json"
PINS_SHA="1fc144feb80a051252c47f24d1ff96d10d5e504c28d9669eae489ff254998b93"
VER=Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification")
HIST=Path("D:/HumanEye/runs")
R36=VER/"m6_post032_profile_036"
MATRIX=Path("D:/he_b32g_release_acceptance/matrix")
OUT040=HIST/"M3-BVH-DEEP-COMPARE-040/entry_runs/live_matrix_001/r1/032/MCP"
ASSETS={"G60":MATRIX/"B_G60_D12/native/input.blend","D48":MATRIX/"B_D48/native/input.blend",
        "G508":VER/"scale_diag_001/fixtures/G508.blend","B02":HIST/"M6-037-BVH-DIRECTIONAL-BOUND/native/input/assembly_original.blend",
        "Yanyite":Path("D:/he_m1_m2_source_region_scoped_measurement_001/slots/YB/native/input.blend")}
INPUTS={"G60":VER/"scale_diag_001/fixtures/G60_D12.json","D48":VER/"scale_diag_001/fixtures/D48.json",
    "G508":VER/"scale_diag_001/fixtures/G508.json","B02":VER/"m4_surface_scan_001/qualification/BASE_SNAPSHOT.json",
    "D48_exact":HIST/"M6-037-BVH-DIRECTIONAL-BOUND/oracle/d48_actual_cold/RESULT.json",
    "B02_exact":HIST/"M6-038-NEAREST-WINDOWS-SPAWN/archive/ASSEMBLY_TRUTH.json",
    "B02_scan":VER/"m4_surface_scan_001/qualification/BASE_TRUTH.json",
    "D48_bundle":HIST/"M6-039-INDEPENDENT-PAIR-DUAL-SPAWN/freeze/D48.json",
    "B02_bundle":HIST/"M6-039-INDEPENDENT-PAIR-DUAL-SPAWN/freeze/Assembly.json",
    "G60_040_nearest":OUT040/"nearest_first.json","G60_040_scan":OUT040/"scan_first.json",
    "G60_relation":MATRIX/"B_G60_D12/mcp/05_observe_0_REQUEST.json",
    "scale_truth":VER/"scale_diag_001/ORACLE.json",
    "Yanyite":VER/"m6_same_frame_scoped_batch_034/private/inputs/FROZEN.json",
    "Yanyite_source":Path("D:/he_m1_m2_source_region_scoped_measurement_001/slots/YB/initial_capture/TERMINAL_SOURCE.json")}
SEQUENCES={"G60_nearest":["nearest","nearest_warm","nearest_unchanged","edit","nearest_edited","nearest_edited_warm"],
           "G60_scan":["scan","scan_warm"],"G60_reuse":["nearest","scan","relation","missing"],
           "D48":["nearest","nearest_warm"],"G508":["nearest","nearest_warm","scan","relation"],
           "B02":["nearest","scan"],"Yanyite":["high","same_box","low"]}
now=time.perf_counter_ns
def read(p):return json.loads(Path(p).read_bytes())
def dump(p,x):
    p=Path(p)
    with p.open('x',encoding='utf8',newline='\n') as f:json.dump(x,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')
def pin(p):
    p=Path(p).resolve(strict=True)
    return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
def need(ok,msg):
    if not ok:raise ValueError(msg)
def mod(name,p):
    spec=importlib.util.spec_from_file_location(name,p); obj=importlib.util.module_from_spec(spec); spec.loader.exec_module(obj);return obj
def asset_for(scenario):return scenario.split("_")[0]
def api():
    g=mod("s1_gui",R36/"gui.py");g.PRIVATE=ROOT;g.CYCLE="M6-041-KERNEL-HOOK"
    g.ASSET_SHAS={pin(p)['sha256']:k for k,p in ASSETS.items()}
    return g,mod("s1_mcp",R36/"run.py")
def source_plan():
    need(pin(PINS)['sha256']==PINS_SHA,"external install pins")
    p=read(PINS); arms={}
    for arm,source in p["releases"].items():
        rel=Path(source); ref=p["binding"][arm];need(pin(ref["path"])==ref,"binding changed")
        b=read(ref["path"]);idn=p["identities"][arm]
        need(b["identity"]==idn and len(b["source_files"])==143,"identity")
        for f in b["source_files"]:need(pin(rel/"site-packages"/f["path"])["sha256"]==f["sha256"],"source drift")
        launcher=rel/"admin/target_runtime_entry.py"
        need(pin(launcher)["sha256"]==b["launcher_sha256"],"launcher")
        arms[arm]=dict(source_sha256=idn["source_sha256"],version=idn["distribution_version"],role="S1 actual installed regular stdio",
            site_packages=b["site_packages"],command_prefix=[b["dependency_python"],"-I","-B",str(launcher)])
    return arms
def request(asset,label):
    if asset=="Yanyite":
        return read(INPUTS["Yanyite"])["requests_A"][int(label=="low")]
    if label=="relation":return read(INPUTS["G60_relation"])["params"]
    if label.startswith("scan"):
        query={"mode":"surface_scan","threshold_m":.002 if asset=="B02" else .005}
    else:
        name="041_missing_negative_control" if label=="missing" else "Obj_014" if asset=="B02" else "Target"
        query={"mode":"surface_nearest","objects":[{"name":name}]}
    return {"name":"human_eye_scene_observe","arguments":{"session_id":"m3-bvh-040","include_image":False,
        "response_detail":"full","query":query}}
def prep():
    g,svc=api(); arms=source_plan();support=g.prepare()
    plan={"schema":"M6-041-S1-v1","arms":arms,"source_pins":pin(PINS),"assets":{k:pin(v) for k,v in ASSETS.items()},
        "inputs":{k:pin(v) for k,v in INPUTS.items()},"support":support,
        "sources":{str(p):pin(p) for p in (Path(__file__),R36/"gui.py",R36/"gui_worker.py",R36/"snapshot.py",R36/"run.py",
                                            VER/"m6_bounded_surface_scan_027/driver.py",VER/"m6_bvh_entry_qualification_024/entry.py")},
        "slots":[[s,a] for i,s in enumerate(SEQUENCES) for a in (("032","r3") if not i%2 else ("r3","032"))],
        "sequence":SEQUENCES,"requests":{s:{k:request(asset_for(s),k) for k in seq if k not in ("edit",)} for s,seq in SEQUENCES.items()},
        "edit":"Only G60_nearest after three reads. Private open mesh, translate Target.location.z by exactly 0.03125 source units, update dependency graph, persist as a different .blend using save_as_mainfile(copy=True).",
        "negative":"Explicit invalid selector in G60_reuse. Missing is expected and its observed shape kept.",
        "S1_scope":"one slot per source and workload; identical source assets and ordinary installed Blender add-on, distinct host and MCP per slot; default ndarray, serial, no hook dispatch; descriptive RTT only",
        "work":"Record original request_trace/observe task work and their available kernel counts. Separate nested spans, bytes and lifecycle. Never infer per-pair business calls absent an audit ledger.",
        "accept":"Pin first; compare complete public bodies after validating both receipts. Allow trace/build and validated per-instance host identifiers only. Compare exact rank/witness to bound historical truth when supplied; hold conflicting evidence."}
    plan["recovery"]={"original":pin(ROOT/"PLAN.json"),"original_driver":pin(ROOT/"driver_initial.py"),"reason":"Read trace.runtime_identity.build_id and identity_check.actual.source_sha256; original strict property access failed after genuine first answers. New full cold sequences after cleanup, no fast-sample selection."}
    dump(PLAN,plan);print("prepared",pin(PLAN),flush=True)
def loadsnap(host,label,slot):
    rr=host.run((R36/"snapshot.py").read_text(encoding="utf8"),timeout_s=30)
    need(rr['response']['status']=='success','readback')
    raw=rr['response']['result']['result']
    line,=[x for x in raw.splitlines() if x.startswith("M6_036_SNAPSHOT:")]
    data=json.loads(line.split(":",1)[1])
    need(data["pid"]==host.pid and data["main_thread"] and data["background"] is False and
         Path(data["asset"]).resolve()==host.workspace/"input.blend","ordinary owned current mesh")
    dump(slot/(label+".json"),data)
    return data
def geokey(g):
    return {k:{field:row[field] for field in ("local_sha256","triangles_sha256","matrix","visible")} for k,row in g["geometry"].items() if row["type"]=="MESH"}
def check_input(asset,snap,svc):
    got=geokey(snap)
    if asset=="Yanyite":
        d=svc.fixture("Yanyite")
        return set(got)==set(d["expected"]) and all(all(snap["geometry"][n][k]==v for k,v in checks.items()) for n,checks in d["expected"].items())
    expected={r['name']:r for r in read(INPUTS[asset])['objects']}
    return set(expected)==set(got) and all(r['matrix_world']==got[n]['matrix'] and
        svc.hash_array(r['vertices_local'],"<f8")==got[n]['local_sha256'] and
        svc.hash_array(r['triangles'],"<i4")==got[n]['triangles_sha256'] for n,r in expected.items())
def edited(host,slot):
    dest=host.workspace/"041_private_edit.blend"
    code=("import bpy,json\nfrom pathlib import Path\nobj=bpy.data.objects['Target']\n"
          "z=float(obj.location.z)\nobj.location.z=z+0.03125\nbpy.context.view_layer.update()\n"
          "bpy.context.preferences.filepaths.save_version=0\n"
          f"result=bpy.ops.wm.save_as_mainfile(filepath={str(dest)!r},copy=True,check_existing=False)\n"
          "print(json.dumps({'z_before':z,'z_after':obj.location.z,'status':sorted(result),'open_filepath':bpy.data.filepath}))")
    reply=host.run(code)
    need(reply['response']['status']=='success' and dest.is_file(),"private edit and persistence")
    return {"file":pin(dest),"reply":reply['response']}
def brief_trace(client,r):
    logs=[json.loads(x) for x in client.audit.read_bytes().splitlines()]
    tr=[x for x in logs if x.get('event')=='request_trace' and str(x['trace']['annotations'].get('mcp_request_id'))==r["timing"]["id"]]
    need(len(tr)==1,"one trace per request")
    t=tr[0];need(t["pid"]==client.server_pid and t["runtime_identity"]["build_id"]=="sha256:"+client.source and t["identity_check"]["actual"]["source_sha256"]==client.source and t["identity_check"]["compatible"],"receipt unrelated to expected source")
    trace=t["trace"];body=r['result']
    if isinstance(body,dict) and "trace_id" in body:need(trace["trace_id"]==body["trace_id"],"response trace binding")
    if isinstance(body,dict) and "binding" in body:need(body['binding'].get("runtime_source_sha256")==client.source,"body binding")
    events=[x for x in logs if x.get("event")=="observe" and x.get("request_id")==trace["request_id"]]
    return {"trace_id":trace['trace_id'],"duration_ns":trace['duration_ns'],"spans":[[s['name'],s['duration_ns']] for s in trace['spans']],
            "work":[x['task_work'] for x in events if 'task_work' in x],"outcome":trace['outcome'],"source":client.source}
def execute(scenario,arm,window):
    p=read(PLAN);need(pin(PINS)==p["source_pins"],"pin manifest")
    for f in [*p["inputs"].values(),*p["sources"].values(),*p["assets"].values()]:need(pin(f["path"])==f,"frozen source "+f["path"])
    g,svc=api();asset=asset_for(scenario);folder=SLOTS/(scenario+"_"+arm)
    folder.mkdir(parents=True,exist_ok=False)
    host=client=None; rows=[]; errors=[]; cleanup={};stage="enter";started=now()
    out={"arm":arm,"scenario":scenario,"started_ns":started,"rows":rows,"errors":errors,"close":cleanup,"fresh_product":True}
    try:
        stage="GUI open";host=g.Owned(folder/"native",p['assets'][asset],p["support"],window);out["host_ready_ns"]=now()
        initial=loadsnap(host,"BEFORE",folder);out['geometry_binds']=check_input(asset,initial,svc)
        need(out['geometry_binds'],"asset source snapshot disagreement")
        stage="stdio open";client=svc.Client(folder/"client",host,asset,p['arms'][arm]);client.open(asset)
        out["stdio_ready_ns"]=now();out["server_pid"]=client.server_pid
        for label in p["sequence"][scenario]:
            stage=label
            if label=="edit":
                out['edit']=edited(host,folder);post=loadsnap(host,"EDITED",folder)
                a,b=geokey(initial),geokey(post);out['changed_objects']=[n for n in a if a[n]!=b[n]]
                need(out['changed_objects']==['Target'] and a['Target']['local_sha256']==b['Target']['local_sha256'] and
                     a['Target']['triangles_sha256']==b['Target']['triangles_sha256'],"edit bounded to transform")
                continue
            if label=="nearest_unchanged":
                need(geokey(loadsnap(host,"NO_CHANGE",folder))==geokey(initial),"unchanged control")
            before={k:svc.transport.counters(pid) for k,pid in (("host",host.pid),("product",client.server_pid))}
            r=client.observe(p['requests'][scenario][label]);end=now()
            row={"label":label,"value":r["result"],"timing":r["timing"],"tool_error":r["tool_error"],"rpc_error":r["rpc_error"],
                 "business_ns":end-r["timing"]["started_ns"],"os_before":before,
                 "os_after":{k:svc.transport.counters(pid) for k,pid in (("host",host.pid),("product",client.server_pid))}}
            rows.append(row)
            row['audit']=brief_trace(client,r)
            dump(folder/(label+".json"),row)
        final=loadsnap(host,"AFTER",folder)
        expected=post if "edit" in p["sequence"][scenario] else initial
        out['geometry_preserved']=geokey(final)==geokey(expected)
        need(out['geometry_preserved'],"unexpected mutation")
    except BaseException:
        errors.append({"stage":stage,"exception":traceback.format_exc()})
    finally:
        for key,obj in (("product",client),("GUI",host)):
            if obj:
                try:
                    start=now();ret=obj.close();cleanup[key]={"result":ret,"wall_ns":now()-start}
                    need((ret==0 and not obj.reader.is_alive() and read(folder/'client/CLOSE.json')['method']=='eof') if key=="product" else
                         ret["status"]=="pass" and ret["process_reaped"] and ret["forced"] is None,"cleanup")
                except BaseException:errors.append({"stage":"close "+key,"exception":traceback.format_exc()})
    out['end_ns']=now();out['completed']=not errors;dump(folder/"SLOT.json",out)
    print(scenario,arm,"complete" if not errors else errors[0],flush=True)
    return out
def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["prepare","run"]);p.add_argument("--window",type=Path)
    args=p.parse_args()
    if args.mode=="prepare":prep();return
    w=read(args.window);need(w.get("cycle_id")=="M6-041-KERNEL-HOOK" and w.get("status")=="available" and bool(w.get("token")),"exclusive window")
    plan=read(PLAN)
    for scenario,arm in plan["slots"]:execute(scenario,arm,w)
if __name__=="__main__":main()

