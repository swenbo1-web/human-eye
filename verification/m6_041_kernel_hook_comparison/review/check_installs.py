"""Audit wheel and installed bytes against independent Git objects rather than receipt-provided identities."""
import hashlib
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parent.parent
GIT=Path("C:/Users/Administrator/.codex/worktrees/1212/hefe")
pins=json.loads((ROOT/"install/PINS.json").read_bytes())
plan=json.loads((ROOT/"PLAN.json").read_bytes())
read=lambda p:json.loads(p.read_bytes())
digest=lambda b:hashlib.sha256(b).hexdigest()
artifacts={}
for role,ref in (("032",plan["base"]),("r3",plan["r3"])):
    info=pins["arms"][role]
    binding=read(Path(info["binding"]["path"]))
    rows={s["path"]:s["sha256"] for s in binding["source_files"]}
    assert len(rows)==143
    paths=list(rows)
    lines=[(plan["hook_support"] if p=="human_eye_hook.py" else ref)+":"+p for p in paths]
    blobs=subprocess.check_output(["git","-C",str(GIT),"cat-file","--batch"],input=("\n".join(lines)+"\n").encode())
    pos=0
    new=[]
    with ZipFile(info["wheel"]["path"]) as z:
        for p in paths:
            e=blobs.index(b"\n",pos)
            oid,typ,sz=blobs[pos:e].split()
            assert typ==b"blob"
            end=e+1+int(sz)
            data=blobs[e+1:end]
            assert blobs[end:end+1]==b"\n"
            pos=end+1
            assert data==(Path(info["site"])/p).read_bytes()==z.read(p)
            assert rows[p]==digest(data)
            new.append((p,oid.decode(),rows[p]))
    assert pos==len(blobs)
    for key in ("wheel","launcher","admin","binding","build"):
        assert digest(Path(info[key]["path"]).read_bytes())==info[key]["sha256"]
    artifacts[role]={"commit":ref,"wheel":info["wheel"]["sha256"],"rows":new,
                     "verified_count":len(new),"source_set_sha256":pins["identities"][role]["source_sha256"]}
d={u[0] for u,v in zip(artifacts["032"]["rows"],artifacts["r3"]["rows"]) if u!=v}
expect={"human_eye_plugin/"+s+".py" for s in ("surface_proximity","surface_geometry","surface_scan","task_query")}
assert d==expect
with (ROOT/"review/GIT_WHEEL_INSTALL.json").open("x",encoding="utf8") as f:
    json.dump(dict(arms=artifacts,changed=sorted(d)),f,indent=2)
print("286 Git / wheel / installed byte matches",sorted(d))

