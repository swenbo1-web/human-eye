"""041 private serial Hook -> MCP workflow and Windows group resource replay."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OLD = Path("D:/HumanEye/runs/M3-BVH-DEEP-COMPARE-040")
ART = OLD / "entry_runs/live_matrix_001/r1/032"
H1_TEMPLATE = OLD / "entry_runs/light_matrix_002/r1/prompt_unrelated/direct/direct_argv.json"
GUI = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_post032_profile_036/gui.py")
ASSET = Path("D:/he_b32g_release_acceptance/matrix/B_G60_D12/native/input.blend")
INSTALL = ROOT / "install/PINS.json"
PIN = "1fc144feb80a051252c47f24d1ff96d10d5e504c28d9669eae489ff254998b93"
PY = Path("D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe")
JOB = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_independent_pair_dual_spawn_039")
HOOK_HELPER = Path("D:/HumanEye/runs/b32g-hook-001/review/live/run_live.py")
T = time.perf_counter_ns
def need(test, reason):
    if not test:
        raise ValueError(reason)

def read(p):
    return json.loads(Path(p).read_bytes())

def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def module(name, p):
    spec = importlib.util.spec_from_file_location(name, p)
    val = importlib.util.module_from_spec(spec)
    sys.modules[name] = val
    spec.loader.exec_module(val)
    return val

def env_fixtures():
    prior = module("hook041prior", HOOK_HELPER)
    old,hooks,entry,_,scorer,snapshot,expected,_ = prior.setup()
    gui = module("gui041ordinary", GUI)
    gui.CYCLE = "M6-041-KERNEL-HOOK"
    gui.PRIVATE = HERE
    return prior,hooks,entry,scorer,snapshot,expected,gui

def freeze():
    need(sha(INSTALL)==PIN, "external installation manifest")
    prior,hooks,entry,scorer,snapshot,expected,gui = env_fixtures()
    plan=read(ROOT/"PLAN.json")
    support=gui.prepare()
    source=gui.artifact(ASSET)
    need(source["sha256"]==plan["inputs"]["G60"], "historical asset")
    reference={s:sha(ART/"MCP"/f"{s}_first.json") for s in ("nearest","scan")}
    plan_out={"plan_sha256":sha(ROOT/"PLAN.json"),"pins_sha256":PIN,"support":support,
              "asset":source,"historical_040":reference,"prior_hook_helper":sha(HOOK_HELPER),
              "direct_template":sha(H1_TEMPLATE),"archived_registered":sha(hooks.REGISTERED),
              "workflow_driver":sha(Path(__file__)),"job_helper":sha(JOB/"job.py"),
              "python":gui.artifact(PY),"orders":plan["s3"]["orders"],"arms":plan["arms"]}
    event={"session_id":"m6-041-g60-workflow","turn_id":"paired-g60-041","cwd":str(HERE),
           "transcript_path":str(HERE/"workflow-read-only.jsonl"),"permission_mode":"default",
           "hook_event_name":"UserPromptSubmit","prompt":"Inspect the current Blender scene. List the mesh objects, find which mesh is nearest to Target and report every pair within 5 mm. Only observe."}
    raw=json.dumps(event,separators=(",",":")).encode()
    with (HERE/"INPUT.bin").open("xb") as f:
        f.write(raw)
    plan_out["stdin_sha256"]=sha(HERE/"INPUT.bin")
    write(HERE/"FROZEN.json",plan_out)

def config(hooks, release, binding, name, parent, owner):
    p=parent/name
    p.mkdir()
    cfg=copy.deepcopy(hooks.read(hooks.LIVE_CONFIG))
    cfg.update(project_root=str(release/"site-packages"),state_file=str(p/"state.json"),
               audit_file=str(p/"audit.jsonl"), request_budget_s=30.0)
    cfg["blender"]={"host":owner.host,"port":owner.port,"timeout_s":30.0}
    for key in ("base_version","implementation_revision","build_id"):
        cfg["expected_identity"][key]=binding["identity"][key]
    if name!="hook":
        cfg["observe_on_prompt"]=False
    out=p/"connector.json"
    write(out,cfg)
    return out

def hookargs(dispatch,hooks,release,pin,cfg):
    if dispatch=="H0":
        reg=hooks.replace_registrations(hooks.read(hooks.REGISTERED),hooks.read(hooks.A/"admin/RUNTIME_BINDING.json"),
                                        release,pin,cfg)
        cmd=reg["hooks"][hooks.PROMPT][0]["hooks"][0]["command"]
        argv=cmd.split()
        need(len(argv)==5 and argv[-2]=="-EncodedCommand","registered wrapper shape")
        return argv
    value=read(H1_TEMPLATE)
    need(value[0]==pin["dependency_python"] and value[1:3]==["-I","-B"] and
         value[4:-1]==["hook","--agent","codex","--event","UserPromptSubmit","--config"],"040 direct template")
    value[3],value[-1]=str(release/"admin/target_runtime_entry.py"),str(cfg)
    return value

def invoke(argv, raw, folder):
    start=T()
    proc=subprocess.run(argv,input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=folder,
                        timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    end=T()
    (folder/"STDOUT.bin").write_bytes(proc.stdout)
    (folder/"STDERR.bin").write_bytes(proc.stderr)
    value=json.loads(proc.stdout)
    record={"returncode":proc.returncode,"stdout":proc.stdout.decode("utf-8-sig"),"stderr":proc.stderr.decode("utf-8-sig"),
            "output":value,"elapsed_ms":(end-start)/1e6}
    write(folder/"RETURN.json",record)
    need(proc.returncode==0 and not proc.stderr, "positive hook stdout/stderr/exit")
    return json.loads(value["hookSpecificOutput"]["additionalContext"]), end

def mcp_reads(MCP,entry,release,pin,cfg,selection):
    folder=cfg.parent
    marks={"start":T()}
    service=MCP(pin["dependency_python"],release/"admin/target_runtime_entry.py",cfg,folder/"stdio",False)
    values={}
    spans={}
    try:
        hello,_=service.call("initialize",{"protocolVersion":"2025-03-26","capabilities":{},
                                "clientInfo":{"name":"m6-041-workflow","version":"1"}})
        identity=hello["result"]["_meta"]["human_eye"]
        need(all(identity[k]==v for k,v in pin["identity"].items()), "MCP negotiated identity")
        tools,_=service.call("tools/list")
        need("human_eye_scene_observe" in {x["name"] for x in tools["result"]["tools"]},"tool discovery")
        marks["initialized"]=T()
        for name,query in (("nearest",{"mode":"surface_nearest","objects":[{"name":selection}]}),
                           ("scan",{"mode":"surface_scan","threshold_m":0.005})):
            output,timing=service.call("tools/call",{"name":"human_eye_scene_observe","arguments":{
                "session_id":"m6-041-g60-workflow","include_image":False,"response_detail":"full","query":query}},name)
            need(not output["result"].get("isError") and len(output["result"]["content"])==1,"MCP "+name)
            data=entry.metadata(output)
            need(data["result_kind"]==query["mode"] and data["binding"]["runtime_source_sha256"]==pin["identity"]["source_sha256"],"scoped receipt build")
            values[name]=data
            spans[name]=timing
            marks[name+"_receipt"]=T()
    finally:
        closed=service.close()
        marks["closed"]=T()
        write(folder/"CLOSED.json",closed)
        write(folder/"CALLS.json",service.calls)
    need(closed["process_reaped"] and closed["reader_joined"] and not closed["forced_kill"] and closed["exit_code"]==0,
         "stdio shutdown")
    for name,data in values.items():
        write(folder/(name+".json"),data)
    return values,spans,marks

def projection(value,source):
    data=copy.deepcopy(value)
    need(data["binding"]["runtime_source_sha256"]==source,"external identity projection")
    del data["binding"]["runtime_source_sha256"]
    need(isinstance(data["trace_id"],str) and len(data["trace_id"])==32,"per-request trace")
    del data["trace_id"]
    return data

def run_slot(slot,arm):
    pin_doc=read(INSTALL)
    frozen=read(HERE/"FROZEN.json")
    need(sha(INSTALL)==frozen["pins_sha256"] and sha(HERE/"INPUT.bin")==frozen["stdin_sha256"] and
         sha(Path(__file__))==frozen["workflow_driver"],"external slot plan")
    role,dispatch=frozen["arms"][arm]
    releases={k:Path(v) for k,v in pin_doc["releases"].items()}
    binding={k:read(p/"admin/RUNTIME_BINDING.json") for k,p in releases.items()}
    for k,p in releases.items():
        need(sha(p/"admin/RUNTIME_BINDING.json")==pin_doc["binding"][k]["sha256"] and
             binding[k]["identity"]==pin_doc["identities"][k],"verified pin "+k)
    prior,hooks,entry,scorer,snapshot,expected,gui=env_fixtures()
    owner=None
    timing={}
    result={"arm":arm,"role":role,"dispatch":dispatch,"stage":"setup","good":False}
    hpath=slot/"hook"
    try:
        epoch=T()
        owner=gui.Owned(slot/"native",frozen["asset"],frozen["support"],{"status":"available","cycle_id":gui.CYCLE,
                        "token":"041-serial-exclusive-"+slot.name},deadline_ns=epoch+130_000_000_000)
        first=scorer.receipt_payload(owner.run(snapshot,timeout_s=30))
        need(first==expected,"credential-independent G60 native snapshot")
        cfgH=config(hooks,releases[role],binding[role],"hook",slot,owner)
        cfgM=config(hooks,releases[role],binding[role],"mcp",slot,owner)
        cfgQ=config(hooks,releases["032"],binding["032"],"reference",slot,owner)
        argv=hookargs(dispatch,hooks,releases[role],binding[role],cfgH)
        write(hpath/"ARGV.json",argv)
        raw=(HERE/"INPUT.bin").read_bytes()
        MCP=prior.mcp_type(entry)
        result["stage"]="business"
        start=T()
        head,hook_exit=invoke(argv,raw,hpath)
        need(head["runtime_identity"]["build_id"]==binding[role]["identity"]["build_id"],"Hook build")
        target=next(x["name"] for x in head["observation"]["objects"] if x["name"]=="Target")
        measured,spans,times=mcp_reads(MCP,entry,releases[role],binding[role],cfgM,target)
        finish=times["closed"]
        timing.update(t0_ns=start,workflow_ms=(finish-start)/1e6,hook_ms=(hook_exit-start)/1e6,
                      through_reply_ms=(times["scan_receipt"]-start)/1e6,mcp_to_discovery_ms=(times["initialized"]-times["start"])/1e6,
                      nearest_ms=spans["nearest"]["rtt_ns"]/1e6,scan_ms=spans["scan"]["rtt_ns"]/1e6,
                      product_close_ms=(finish-times["scan_receipt"])/1e6,host_start_to_flow_ms=(start-epoch)/1e6)
        result["stage"]="review"
        hook_check,objects=prior.hook_eval(hooks,{"expected_build_id":binding[role]["identity"]["build_id"]},hpath,expected)
        archive_hook=json.loads(read(ART/"RETURN.json")["output"]["hookSpecificOutput"]["additionalContext"])
        need(objects==archive_hook["observation"]["objects"],"040 complete Hook directory")
        q0=T()
        reference,_,_=mcp_reads(MCP,entry,releases["032"],binding["032"],cfgQ,target)
        q1=T()
        checks={}
        for label in ("nearest","scan"):
            doc=projection(measured[label],binding[role]["identity"]["source_sha256"])
            ref=projection(reference[label],binding["032"]["identity"]["source_sha256"])
            need(doc==ref,"same actual document and 032 reference mismatch "+label)
            archived=read(ART/"MCP"/(label+"_first.json"))
            need(sha(ART/"MCP"/(label+"_first.json"))==frozen["historical_040"][label],"040 external oracle")
            historical=projection(archived,"0f9e6336ec54adf9e7b9a5379b02d2c2cab9f6d1f734138c3fde29e08ccee241")
            old_bind=historical.pop("binding")
            binding_current=doc.pop("binding")
            need(doc==historical,"historical full public geometry, sorting, coverage "+label)
            need(old_bind["host_source_sha256"]==binding_current["host_source_sha256"],"same host source")
            checks[label]={"historical_fact_sha256":digest(historical),"same_session_bound_reference_sha256":digest(ref),
                           "full_current_binding":binding_current,"coverage":doc["coverage"]}
        last=scorer.receipt_payload(owner.run(snapshot,timeout_s=30))
        need(last==first,"terminal geometry snapshot")
        result.update(checks=checks,hook=hook_check,baseline_on_same_live_host=True,good=True,stage="validated")
        timing["post_workflow_reference_ms"]=(q1-q0)/1e6
    except BaseException:
        result["error"]=traceback.format_exc()
    finally:
        if owner is not None:
            try:
                closure=owner.close()
                result.update(native_reaped=closure["process_reaped"],native_pid=owner.pid,port=owner.port,
                              source_unchanged=closure["source_unchanged"] and closure["owned_copy_unchanged"])
                timing["host_shutdown_ms"]=closure["elapsed_ns"]/1e6
            except BaseException:
                result["good"]=False
                result["close_error"]=traceback.format_exc()
        timing["actual_full_host_and_QA_ms"]=(T()-epoch)/1e6
        result["timing"]=timing
        write(slot/"RECEIPT.json",result)
    return result["good"]

def supervise(slot,arm,resource):
    import _winapi
    sys.path.insert(0,str(JOB))
    from job import Job
    slot.mkdir(parents=True)
    start=T()
    j=Job()
    ph=None
    samples=[]
    timeout=False
    try:
        ph,pid=j.launch([str(PY),"-I","-B","-X","utf8",str(Path(__file__)),"child",str(slot),arm],dict(os.environ),slot)
        while j.accounting()["active_processes"]:
            if T()-start>145_000_000_000:
                j.kill()
                timeout=True
                break
            if resource:
                samples.append(j.sample())
            _winapi.WaitForSingleObject(ph,20 if resource else 150)
            if _winapi.WaitForSingleObject(ph,0)==0 and j.accounting()["active_processes"]:
                time.sleep(.010)
        total=j.accounting()
        pids=j.pids()
        code=_winapi.GetExitCodeProcess(ph)
    finally:
        if ph is not None:
            _winapi.CloseHandle(ph)
        j.close()
    end=T()
    out={"arm":arm,"sampled":resource,"supervisor_wall_ms":(end-start)/1e6,"job":total,"pids_end":pids,"code":code,
         "timeout":timeout,"receipt_exists":(slot/"RECEIPT.json").exists(),"pid":pid}
    if samples:
        out["peak_group_working_set"]=max(x["group_working_bytes"] or 0 for x in samples)
        out["peak_group_private_bytes"]=max(x["group_private_bytes"] or 0 for x in samples)
        out["incomplete_samples"]=sum(bool(x["missing"]) for x in samples)
        write(slot/"MEMORY_SAMPLES.json",samples)
    write(slot/"JOB.json",out)
    return out

def matrix(folder,phase):
    orders={"preflight":["AD"],"screen":read(HERE/"FROZEN.json")["orders"],"resource":["BCAD"]}[phase]
    folder.mkdir(parents=True,exist_ok=False)
    expected=[(i,arm) for i,o in enumerate(orders,1) for arm in o]
    write(folder/"EXPECTED.json",expected)
    slots=[]
    for i,arm in expected:
        location=folder/f"{i:02d}{arm}"
        job=supervise(location,arm,phase=="resource")
        row=read(location/"RECEIPT.json") if job["receipt_exists"] else {"good":False,"arm":arm}
        good=row.get("good") is True and job["code"]==0 and not job["timeout"] and job["job"]["active_processes"]==0 and not job["pids_end"]
        slots.append({"block":i,"arm":arm,"valid":good,"path":location.name})
        print(phase,i,arm,good,round(row.get("timing",{}).get("workflow_ms",0),1),flush=True)
        if not good:
            print(row.get("error",row.get("close_error","driver failure")),flush=True)
            if phase=="preflight":
                break
    write(folder/"RESULT.json",{"phase":phase,"orders":orders,"slots":slots,"expected":expected})

if __name__=="__main__":
    mode=sys.argv[1]
    if mode=="freeze":
        freeze()
    elif mode=="child":
        sys.exit(0 if run_slot(Path(sys.argv[2]),sys.argv[3]) else 1)
    elif mode=="run":
        matrix(HERE/sys.argv[3],sys.argv[2])

