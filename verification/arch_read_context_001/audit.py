"""Fixed implementation identity, retained evidence and complete test counts."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from human_eye_plugin.runtime_identity import runtime_identity
BASE='bd1c2e4ed3be550cde8e096a9970ebc5e592463d'
PRODUCT='0414a9af8e74fe29df2e420fedb53700be94aaec'
OLD='2c3f36e50dff1b149fbced3c6419f0381c7f1e47'
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def sha(blob):return hashlib.sha256(blob).hexdigest()
def blobs(commit,names):
    data=subprocess.run(['git','cat-file','--batch'],cwd=ROOT,input=b''.join((commit+':'+name+'\n').encode() for name in names),capture_output=True,check=True).stdout
    answer={}
    for name in names:
        header,data=data.split(b'\n',1);oid,kind,size=header.split();size=int(size)
        assert kind==b'blob';answer[name],data=data[:size],data[size+1:]
    assert not data
    return answer
identity=runtime_identity()
assert len(identity['source_files'])==132
names=[row['path'] for row in identity['source_files']]
assert all((ROOT/name).read_bytes()==blob for name,blob in blobs(PRODUCT,names).items())
old_names=[name for name in names if name!='human_eye_plugin/read_context.py']
previous=blobs(BASE,old_names)
changed=[name for name in old_names if previous[name]!=(ROOT/name).read_bytes()]
assert set(changed)=={'human_eye_plugin/live_service.py','human_eye_plugin/task_query.py','human_eye_plugin/scene_cache.py'}
assert git('rev-parse','codex/nearest-integration').decode().strip()==OLD
protected=git('ls-tree','-r','--name-only',OLD,'--','verification/task_scope_impl_001','verification/task_scope_entry_opt_001',
              'verification/spatial_task_entry_001','verification/task_runtime_cleanup_001','verification/spatial_delivery_001').decode().splitlines()
assert len(protected)==148
old_evidence=blobs(OLD,protected)
disk_evidence={name:blob for name,blob in old_evidence.items() if not name.startswith('verification/spatial_delivery_001/')}
assert len(disk_evidence)==98
assert all((ROOT/name).read_bytes()==blob for name,blob in disk_evidence.items())
runs=[]
for name in ('task_tests_01.log','nearest_tests_01.log','nearest_tests_02.log','task_tests_02.log','regressions_01.log','nearest_tests_03.log'):
    text=(OUT/name).read_text(encoding='utf8')
    rows=re.findall(r'^(test_\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped.*)$',text,re.M)
    runs.append({'log':name,'executions':len(rows),'passed':sum(row[2]=='ok' for row in rows),
                 'failed':sum(row[2]=='FAIL' for row in rows),'methods':[{'name':row[1],'status':row[2]} for row in rows]})
assert sum(row['executions'] for row in runs)==101
assert sum(row['passed'] for row in runs)==100 and sum(row['failed'] for row in runs)==1
final_runs=[row for row in runs if row['log'] in ('task_tests_02.log','nearest_tests_03.log','regressions_01.log')]
assert sum(row['passed'] for row in final_runs)==71
plan=Path('D:/hefe/verification/fixes/20261109_architecture_completion/PLAN.md')
state_path=Path('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json')
state=json.loads(state_path.read_bytes())
value={'cycle_id':'ARCH-READ-CONTEXT-001','baseline_product':BASE,'baseline_source_sha256':'f0e146acfbf585f1f43ab31845bee0e2d52a55cf023d54da9c0e33638a07af44',
    'product_commit':PRODUCT,'source_sha256':identity['source_sha256'],'source_count':132,'source_manifest':identity['source_files'],
    'source_matches_product_git':True,'prior_evidence_disk_bytes_unchanged':len(disk_evidence),
    'old_branch_delivery_evidence_retained_in_git':len(protected)-len(disk_evidence),
    'product_files':changed+['human_eye_plugin/read_context.py'],'test_runs':runs,'total_method_executions':101,
    'passing_method_executions':100,'failed_method_executions':1,'final_candidate_passing_unique_methods':71,
    'plan_sha256':sha(plan.read_bytes()),'coordinator_active_work':state['coordinator']['active_work'],
    'state_lane':state['lanes']['M3'],'new_blender_runs':0,'new_model_or_api_runs':0,
    'task_test_delegate_agents':1,'readonly_review_agents':1,
    'remaining':'same-product M2 integration; actual host lifecycle tokens and transport; whole-version invalidation is initial design; M5 scheduler not connected',
    'assembled_epoch_s':time.time(),
    'artifact_sha256':{path.name:sha(path.read_bytes()) for path in sorted(OUT.iterdir()) if path.is_file() and path.name!='RESULTS.json'}}
(OUT/'RESULTS.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
print(json.dumps({key:item for key,item in value.items() if key not in ('source_manifest','test_runs','artifact_sha256','state_lane')},indent=2))
