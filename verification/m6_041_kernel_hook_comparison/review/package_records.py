"""Seal the local primary evidence and package distributable output records and reproduction tools."""
from pathlib import Path
import gzip
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/"delivery"
read=lambda p: json.loads(p.read_bytes())
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()
def jsonbytes(obj):
    return (json.dumps(obj,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode("utf8")
def dump(p,obj):
    with p.open("x",encoding="utf8",newline="\n") as f:
        json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False)
        f.write("\n")
def roots():
    for folder in ("install","review","s0","s1","s2","s3"):
        yield ROOT/folder
def retained(direct,rel):
    parts=rel.parts
    if "__pycache__" in parts or ".git" in parts:
        return False
    if direct=="s0" and (parts[0] in ("source_032","source_R3","history_031") or rel.suffix==".tar"):
        return False
    if direct=="install" and ("source" in parts or "site-packages" in parts):
        return False
    return True
def scientific_records(out):
    def emit(label,path,payload):
        out.write(jsonbytes({"kind":label,"path":str(path.relative_to(ROOT)).replace("\\","/"),"sha256":sha(path),"value":payload}))
    for folder in sorted((ROOT/"s1").glob("slots*")):
        if not folder.is_dir():
            continue
        for run in sorted(folder.iterdir()):
            if not (run/"SLOT.json").exists():
                continue
            for req in sorted((run/"client").glob("*.TX.bin")):
                tx=read(req)
                if tx["method"]!="tools/call":
                    continue
                rx=req.with_name(req.name.replace(".TX.",".RX."))
                emit("S1-actual-stdio-request",req,tx)
                if rx.exists():
                    emit("S1-actual-stdio-response",rx,read(rx))
    for folder in [ROOT/"s2/formal", ROOT/"s2/preflight_001"]:
        for f in sorted(folder.rglob("RESULT.json")):
            r=read(f)
            emit("S2-slot",f,{k:v for k,v in r.items() if k!="samples"})
            for name in ["STDOUT.bin","STDERR.bin"]:
                p=f.parent/name
                if p.exists():
                    emit("S2-exit-stream",p,p.read_bytes().decode("utf-8",errors="replace"))
            a=f.parent/"audit.jsonl"
            if a.exists():
                emit("S2-audit",a,[json.loads(x) for x in a.read_bytes().splitlines()])
    for kind in ("warm_diagnostic","warm_scan_recovery"):
        for p in sorted((ROOT/"s1"/kind).glob("cells/*/CELL.json")):
            emit("S1-diagnostic-cell",p,read(p))
        for p in sorted((ROOT/"s1"/kind).glob("cells/*/client/*.TX.bin")):
            req=read(p)
            if req["method"]=="tools/call":
                emit("S1-diagnostic-request",p,req)
                rx=p.with_name(p.name.replace(".TX.",".RX."))
                if rx.is_file():
                    emit("S1-diagnostic-response",rx,read(rx))
    for p in sorted((ROOT/"s2/error_control/run").glob("*/*/RESULT.json")):
        emit("S2-error-exit",p,{k:v for k,v in read(p).items() if k!="samples"})
        for n in ("STDOUT.bin","STDERR.bin"):
            s=p.parent/n
            if s.is_file():
                emit("S2-error-stream",s,s.read_bytes().decode("utf-8",errors="replace"))
    for category in ("preflight01","screen01","resource01"):
        base=ROOT/"s3"/category
        for slot in sorted(p for p in base.iterdir() if p.is_dir()):
            for file in ["RECEIPT.json","JOB.json","hook/RETURN.json","native/TERMINAL_OWNERSHIP.json",
                         "mcp/CALLS.json","reference/CALLS.json"]:
                p=slot/file
                if p.is_file():
                    emit("S3-"+file.replace("/","-"),p,read(p))
            for sub in ("mcp","reference"):
                for p in sorted((slot/sub/"stdio").glob("*.json")):
                    if any(i in p.name for i in ("_nearest_","_scan_")):
                        emit("S3-actual-stdio",p,read(p))
def main():
    OUT.mkdir(exist_ok=True)
    idx=[]
    for d in roots():
        for p in sorted(d.rglob("*")):
            if not p.is_file() or not retained(d.name,p.relative_to(d)):
                continue
            idx.append({"path":p.relative_to(ROOT).as_posix(),"bytes":p.stat().st_size,"sha256":sha(p)})
    for name in ("PLAN.json",):
        p=ROOT/name
        idx.append({"path":name,"bytes":p.stat().st_size,"sha256":sha(p)})
    dump(OUT/"EVIDENCE.json",{"root":str(ROOT),"members":len(idx),"bytes":sum(x["bytes"] for x in idx),"files":idx,
         "scope":"All newly produced measurement folders including unsuccessful attempts, rerunnable scripts, audit, wires, OS usage, installation evidence and local fixtures. S0 duplicates of version-controlled source trees/tars, installed package source copies and bytecode omitted; verified Git/wheel/source manifests identify them. Complete native evidence stays on the workstation."})
    cp=[]
    def select(p):
        if p.is_file() and p not in cp:
            cp.append(p)
    for f in ("PLAN.json","install/PINS.json","install/build_installed.py",
              "s0/S0_REPORT.md","s0/S0_RESULTS.json","s0/S0_EVIDENCE.json",
              "s0/historical_replay.py","s0/consumer_controls.py","s0/summarize_s0.py",
              "s1/PLAN.json","s1/PLAN_recovery_01.json","s1/WINDOW.json","s1/COSTS.json","s1/RESULTS.json","s1/REPORT.md",
              "s1/AUDIT_2.json","s1/FIRST_ATTEMPT_OFFLINE.json","s1/YANYITE_RECOVERY.json",
              "s1/s1.py","s1/audit.py","s1/finish_yanyite.py","s1/driver_initial.py","s1/summarize.py","s1/warm_diagnostic.py","s1/review_warm.py","s1/warm_recovery.py",
              "s2/PLAN.json","s2/OWNER_WINDOW.json","s2/REPORT.md","s2/RESULTS.json","s2/READY.json","s2/EVIDENCE.json",
              "s2/formal/SUMMARY.json","s2/preflight_001/SUMMARY.json","s2/run_s2.py","s2/summarize_s2.py","s2/win_process.py","s2/error_control/run/SUMMARY.json",
              "s3/FROZEN.json","s3/workflow.py","s3/review.py","s3/REVIEW.json",
              "s3/preflight01/RESULT.json","s3/screen01/RESULT.json","s3/resource01/RESULT.json"):
        select(ROOT/f)
    for p in (ROOT/"review").glob("*"):
        if p.suffix in (".py",".json",".md"):
            select(p)
    for base in (ROOT/"s1/warm_diagnostic", ROOT/"s1/warm_scan_recovery", ROOT/"s2/error_control",ROOT/"s2/error_exit_control"):
        for p in sorted(base.glob("*")):
            if p.is_file() and p.suffix in (".py",".json",".md"):
                select(p)
    for p in cp:
        to=OUT/p.relative_to(ROOT)
        to.parent.mkdir(parents=True,exist_ok=True)
        if to.exists():
            assert sha(p)==sha(to)
        else:
            shutil.copyfile(p,to)
    dest=OUT/"WIRE_RECEIPTS.jsonl.gz"
    with dest.open("xb") as raw, gzip.GzipFile(filename="",fileobj=raw,mode="wb",mtime=0) as f:
        scientific_records(f)
    with gzip.open(dest,"rt",encoding="utf8") as f:
        types={}
        for line in f:
            r=json.loads(line)
            types[r["kind"]]=types.get(r["kind"],0)+1
    dump(OUT/"WIRE_INDEX.json",{"artifact":dest.name,"bytes":dest.stat().st_size,"sha256":sha(dest),
              "records":types,"scope":"Raw ordinary stdio business requests/responses, light command exits and audits, paired full-workflow and same-host reference receipts. Source meshes, full native captures and licensed assets remain in the local evidence store. For S2 Job samples refer to each sealed local RESULT; compressed S2 per-slot entries omit the samples array."})
    print(len(idx),len(cp),dest.stat().st_size,types)
if __name__=="__main__":
    main()

