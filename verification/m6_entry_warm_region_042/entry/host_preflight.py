"""042 E read-only Codex identity/schema preflight; no turn, hook trust or model."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import time

STAGE=Path(__file__).resolve().parent
RAW=Path('D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION/entry')
WORKTREE=STAGE.parents[2]
BINARIES={
    'standalone':Path('C:/Users/Administrator/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe'),
    'desktop_bundled':Path('C:/Program Files/WindowsApps/OpenAI.Codex_26.1120.6357.0_x64__2p2nqsd0c76g0/app/resources/codex.exe'),
}

def pin(path):
    p=Path(path).resolve(strict=True)
    with p.open('rb')as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(p),bytes=p.stat().st_size,sha256=sha)

def main():
    out=RAW/'host_preflight_001';out.mkdir(parents=True,exist_ok=False)
    records=[]
    for name,binary in BINARIES.items():
        folder=out/name;folder.mkdir()
        calls=[('version',['--version']),('app_server_help',['app-server','--help']),
            ('schema',['app-server','generate-json-schema','--experimental','--out',str(folder/'schema')])]
        for label,args in calls:
            started=time.perf_counter_ns();done=subprocess.run([str(binary),*args],cwd=WORKTREE,capture_output=True,timeout=30)
            for kind,body in(('stdout',done.stdout),('stderr',done.stderr)):
                with (folder/(label+'.'+kind+'.bin')).open('xb')as stream:stream.write(body)
            records.append(dict(binary=name,label=label,argv=[str(binary),*args],returncode=done.returncode,
                elapsed_ns=time.perf_counter_ns()-started,stdout=pin(folder/(label+'.stdout.bin')),stderr=pin(folder/(label+'.stderr.bin'))))
    result=dict(schema='m6-042-E-host-schema-preflight-v1',status='completed',binaries={k:pin(p)for k,p in BINARIES.items()},
        commands=records,source=pin(__file__),turn_started=False,model_requested=False,hook_trust_written=False,
        production_config_written=False,Blender_started=False,scope='identity/help/schema generation only; no automatic Hook qualification yet')
    path=out/'RESULT.json'
    with path.open('x',encoding='utf8')as stream:json.dump(result,stream,indent=2)
    print(json.dumps(pin(path)))

if __name__=='__main__':main()
