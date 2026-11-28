"""Bounded A or B sequence over the installed product's actual stdio transport."""
import hashlib
import json
from pathlib import Path
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

def sha(value):
    return hashlib.sha256(value).hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf8')

def run(site, blender, fixture, slot, arm):
    slot.mkdir(parents=True, exist_ok=False)
    copied = slot/'cube.blend'
    shutil.copyfile(fixture, copied)
    copied.chmod(0o444)
    records = []
    def observe(label, focus=None, image=True, detail='full'):
        query = {'mode':'active_observation'}
        if focus is not None:
            query.update(objects=[{'name':'Box'}], focus=focus)
        records.append((label, 'tools/call', {'name':'human_eye_scene_observe','arguments':{
            'query':query, 'include_image':image, 'response_detail':detail}}))
    records.append(('init','initialize',{'protocolVersion':'2024-11-05','capabilities':{},
                    'clientInfo':{'name':'directed-focus-engineering','version':'1'}}))
    records.append(('tools','tools/list',{}))
    if arm == 'A':
        observe('cold')
        observe('repeat')
    else:
        observe('cold','auto')
        observe('plan-top',{'source_triangle_index':2}, image=False,detail='brief')
        observe('cold-top',{'source_triangle_index':2})
        observe('repeat','auto',detail='brief')
    here = Path(__file__).resolve().parent
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    with (slot/'stderr.log').open('wb') as log:
        child = subprocess.Popen([sys.executable,'-I','-B',str(here/'serve.py'),str(site),
            str(blender),str(slot)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=env)
        lines = queue.Queue()
        def read_lines():
            for line in child.stdout:
                lines.put(line)
            lines.put(b'')
        reader = threading.Thread(target=read_lines,daemon=True)
        reader.start()
        ledger = []
        try:
            for i,(label,method,params) in enumerate(records,1):
                tx = json.dumps(dict(jsonrpc='2.0',id=i,method=method,params=params),separators=(',',':')).encode()+b'\n'
                prefix=slot/f'{i:02d}-{label}'
                prefix.with_suffix('.tx').write_bytes(tx)
                t0=time.perf_counter_ns()
                child.stdin.write(tx)
                child.stdin.flush()
                rx=lines.get(timeout=70)
                t1=time.perf_counter_ns()
                prefix.with_suffix('.rx').write_bytes(rx)
                assert rx, 'early_eof'
                reply=json.loads(rx)
                ledger.append(dict(label=label, tx=len(tx),rx=len(rx),tx_sha=sha(tx),rx_sha=sha(rx),
                    rtt_ms=round((t1-t0)/1e6,3)))
                assert reply.get('id')==i and 'result' in reply, reply
                if method=='tools/call':
                    assert not reply['result']['isError'], reply['result']['content'][0]
        finally:
            child.stdin.close()
            try:
                code=child.wait(timeout=45)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=10)
                raise
            reader.join(timeout=3)
            save(slot/'ledger.json',dict(arm=arm, requests=ledger, server_exit=code,
                stdout_eof=not reader.is_alive(),fixture_sha=sha(fixture.read_bytes())))
            child.stdout.close()
        assert code==0 and not reader.is_alive(), (code,reader.is_alive())
    print(slot.name, len(ledger), 'stdio calls, EOF, exit', code)

if __name__=='__main__':
    site, blender, fixture, slot = map(Path,sys.argv[1:5])
    arm=sys.argv[5]
    assert arm in ('A','B')
    run(site, blender, fixture, slot, arm)
