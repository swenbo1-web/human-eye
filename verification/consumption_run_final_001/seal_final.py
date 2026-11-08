"""Static source/plan verification and small final seal; no runtime launch."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
BASE=ROOT/'verification/consumption_run_001';FIX=ROOT/'verification/consumption_run_fix_001'
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(Path(p).read_bytes())
commit='34e5aa1da1c200ed9430d9074e1e61270b6711f4'
prep=load(HERE/'PREP_PLAN.json');plan=load(HERE/'PLAN.json')
assert prep['execution_ready'] is False and plan['execution_ready'] is True
a=dict(prep);b=dict(plan);a.pop('execution_ready');b.pop('execution_ready');assert a==b
for row in plan['runtime_components']:assert sha((HERE/row['path']).read_bytes())==row['sha256'],row['path']
assert len(plan['runtime_components'])==17
runtime=[]
for name in ('runner.py','he_bootstrap.py','bridge.py'):
    old=subprocess.check_output(['git','show',commit+':verification/consumption_run_fix_001/'+name],cwd=ROOT)
    current=(HERE/name).read_bytes()
    if name!='bridge.py':assert current==old
    else:
        needle=b"        (audit/'HE_CHILD_STARTED.json').write_bytes(encoded(dict(pid=self.process.pid, started_ns=time.perf_counter_ns())))\n        try: self.incoming = reader(self.process.stdout)"
        replacement=b"        try:\n            (audit/'HE_CHILD_STARTED.json').write_bytes(encoded(dict(pid=self.process.pid, started_ns=time.perf_counter_ns())))\n            self.incoming = reader(self.process.stdout)"
        assert old.count(needle)==1 and current==old.replace(needle,replacement)
    runtime.append(dict(path=name,bytes=len(current),sha256=sha(current),baseline_sha256=sha(old)))
oldpaths=[]
for folder in (BASE,FIX):
    index=load(folder/'EVIDENCE_INDEX.json');prefix=folder.relative_to(ROOT).as_posix()+'/'
    oldpaths += [prefix+r['path'] for r in index['members']]+[prefix+'EVIDENCE_INDEX.json']
oldpaths += [r['path'] for r in plan['product_manifest']]
raw=subprocess.check_output(['git','cat-file','--batch'],cwd=ROOT,input=''.join(commit+':'+p+'\n' for p in oldpaths).encode())
stream=io.BytesIO(raw)
for name in oldpaths:
    header=stream.readline().decode().split();assert header[1]=='blob'
    blob=stream.read(int(header[2]));assert stream.read(1)==b'\n' and blob==(ROOT/name).read_bytes(),name
assert stream.read()==b'' and len(oldpaths)==267
tests=load(HERE/'check_01/RESULTS.json');assert tests['passed'] and tests['methods']==3 and tests['candidate_unchanged']
assert tests['bridge_sha256']==sha((HERE/'bridge.py').read_bytes())
proof=dict(baseline_commit=commit,runtime=runtime,old_blobs_unchanged=267,components_checked=17,
    plan_sha256=sha((HERE/'PLAN.json').read_bytes()),prep_plan_sha256=sha((HERE/'PREP_PLAN.json').read_bytes()),
    plan_pair_only_difference='execution_ready',PLAN_true_is_not_authorization=True,
    current_mock_methods=3,passed=3,failures=0,real_processes=0,consumers=0,Blender=0,MCP_services=0,RPC=0,API=0,product_imports=0)
(HERE/'SOURCE_PROOF.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf8')
rows=[]
for file in sorted(HERE.rglob('*')):
    if not file.is_file() or '__pycache__' in file.parts:continue
    name=file.relative_to(HERE).as_posix()
    if name=='EVIDENCE_INDEX.json':continue
    data=file.read_bytes();rows.append(dict(path=name,bytes=len(data),sha256=sha(data)))
index=dict(cycle_id='CONSUMPTION-CHILD-RECEIPT-001',members=rows,member_count=len(rows),member_bytes=sum(r['bytes'] for r in rows),source_proof=proof,self_index='excluded; delivery reports SHA')
(HERE/'EVIDENCE_INDEX.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(member_count=len(rows),member_bytes=index['member_bytes'],index_sha256=sha((HERE/'EVIDENCE_INDEX.json').read_bytes()),plan_sha256=proof['plan_sha256'],runtime=runtime)))
if '--stage' in sys.argv:subprocess.run(['git','add','-f','--',*[str(HERE/r['path']) for r in rows],str(HERE/'EVIDENCE_INDEX.json')],cwd=ROOT,check=True)
