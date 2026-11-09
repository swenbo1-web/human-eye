"""Fixed OPT bytes and complete affected-test denominator; no product run."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from human_eye_plugin.runtime_identity import runtime_identity
BASE='8935b78aa445b8050de07818658100a0de1f7e29'
PRODUCT='ba72c21614d9547ce48615d02f7f37389d22dd6f'
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT)
def sha(value):return hashlib.sha256(value).hexdigest()
def blobs(commit,names):
    data=subprocess.run(['git','cat-file','--batch'],cwd=ROOT,input=b''.join((commit+':'+name+'\n').encode() for name in names),capture_output=True,check=True).stdout
    result={}
    for name in names:
        header,data=data.split(b'\n',1);oid,kind,size=header.split();size=int(size)
        assert kind==b'blob';result[name],data=data[:size],data[size+1:]
    assert not data
    return result
identity=runtime_identity();names=[row['path'] for row in identity['source_files']]
assert len(names)==132
candidate=blobs(PRODUCT,names);baseline=blobs(BASE,names)
assert all((ROOT/name).read_bytes()==blob for name,blob in candidate.items())
assert [name for name in names if candidate[name]!=baseline[name]]==['human_eye_plugin/read_context.py']
old=git('ls-tree','-r','--name-only',BASE,'--','verification/arch_read_context_001').decode().splitlines()
assert len(old)==16 and all((ROOT/name).read_bytes()==blob for name,blob in blobs(BASE,old).items())
runs=[]
for name in ('selection_tests_01.log','task_regressions.log','nearest_regressions.log'):
    rows=re.findall(r'^(test_\S+) \(([^)]+)\) \.\.\. (ok|FAIL|ERROR|skipped.*)$',(OUT/name).read_text(encoding='utf8'),re.M)
    runs.append({'log':name,'executed':len(rows),'passed':sum(row[2]=='ok' for row in rows),
                 'methods':[{'name':row[1],'status':row[2]} for row in rows]})
assert [(row['executed'],row['passed']) for row in runs]==[(11,11),(12,12),(9,9)]
work=json.loads((OUT/'WORK_MEMORY.json').read_bytes())
value={'cycle_id':'ARCH-READ-CONTEXT-OPT-001','baseline_evidence':BASE,'baseline_product':'0414a9af8e74fe29df2e420fedb53700be94aaec',
       'product_commit':PRODUCT,'source_sha256':identity['source_sha256'],'source_count':132,
       'source_manifest':identity['source_files'],'source_matches_product_git':True,
       'changed_product_files':['human_eye_plugin/read_context.py'],'old_evidence_disk_bytes_unchanged':16,
       'test_runs':runs,'total_method_executions':32,'passed':32,'failed':0,'errors':0,'skipped':0,
       'accounting_scenarios_separate_from_unittest':['AB_AD_AB','AB_ABC_AB','capacity','task_nearest_alternation'],
       'work_and_memory':work,'new_blender_runs':0,'new_model_or_api_runs':0,'latency_benchmark_batches':0,
       'retention_limits':{'selections_per_global_generation':8,'results_per_selection':16,'max_result_bodies':128},
       'delegated_test_authors':1,'readonly_review_agents':1,
       'artifact_sha256':{path.name:sha(path.read_bytes()) for path in sorted(OUT.iterdir()) if path.is_file() and path.name!='RESULTS.json'}}
(OUT/'RESULTS.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
print(json.dumps({key:item for key,item in value.items() if key not in ('source_manifest','test_runs','work_and_memory','artifact_sha256')},indent=2))
