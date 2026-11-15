"""Review fixed task-definition evidence without loading geometry or weights."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
COMMIT='29e81ed1d1b2fde2464cdbf856f96086f9ae4b46'
BASE='66e171ceb72c930ba534e1eb8317791d00bd2dba'
REL='verification/m6_shape_task_001'
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda b:hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=AUTHOR)
def save(relative,b):
    p=HERE/'snapshot'/relative;p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():assert p.read_bytes()==b
    else:p.write_bytes(b)

start,cpu=time.perf_counter(),time.process_time()
assert git('rev-parse','HEAD').decode().strip()==COMMIT
assert not git('status','--porcelain').strip()
changed=git('diff','--name-status',BASE,COMMIT).decode().splitlines()
assert len(changed)==17 and all(x.startswith('A\t'+REL+'/') for x in changed)
records=[]
for row in changed:
    relative=row.split('\t')[1];b=git('show',COMMIT+':'+relative)
    assert b==(AUTHOR/relative).read_bytes();save(relative,b)
    records.append({'relative':relative,'bytes':len(b),'sha256':sha(b)})
b=HERE/'snapshot'/REL
manifest=read(b/'EVIDENCE_MANIFEST.json')
for row in manifest['public_delivery_files']:
    data=Path(row['path']).read_bytes()
    assert len(data)==row['bytes'] and sha(data)==row['sha256'],row['path']
sources=read(b/'SOURCE_MANIFEST.json')
for row in sources['source_files']:
    relative=Path(row['path']).relative_to(AUTHOR).as_posix();data=git('show',BASE+':'+relative)
    assert data==Path(row['path']).read_bytes() and len(data)==row['bytes'] and sha(data)==row['sha256']
    save(relative,data)
old=read(HERE.parent/'m6_shape_observe_001_review/snapshot/verification/m6_shape_observe_001/REUSED_INPUTS.json')
oldids={r['path']:r for r in old['reused_input_files']}
for row in sources['inherited_geometry_file_identities']:
    expected=oldids[row['path']]
    assert all(row[k]==expected[k] for k in ('path','bytes','sha256'))
task=read(b/'CONCRETE_TASK.json');obs=read(HERE.parent/'m6_shape_observe_001_review/snapshot/verification/m6_shape_observe_001/INPUT_AUDIT.json')
case=next(c for c in obs['cases'] if c['id']==task['case_id']);d=case['denominators'];counts=task['counts']
for name,key in [('context','context'),('allowed','allowed'),('free','free'),('true_support_evaluation_only','support'),('normal_allowed','normal_allowed'),('normal_free','normal_free')]:assert counts[name]==d[key]
assert counts['boundary']==d['allowed']-d['free'] and counts['free_coordinate_unknowns']==3*d['free']
source=(HERE/'snapshot/human_eye_plugin/surface_reference.py').read_text(encoding='utf8')
tree=ast.parse(source);preview=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='preview_restore')
segment=ast.get_source_segment(source,preview)
assert "raw['vertices'][i]=reference['vertices'][i][:]" in segment
assert "len(indices)<=64" in segment
intent=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ReferenceIntent')
assert {n.target.id for n in intent.body if isinstance(n,ast.AnnAssign)}=={'provenance','semantic_target','correspondence'}
out={'status':'source_and_saved_facts_passed_decision_scope_correction_required','commit':COMMIT,
     'new_files':records,'manifest_records':len(manifest['public_delivery_files']),
     'baseline_text_sources_checked':len(sources['source_files']),'inherited_geometry_metadata_only':len(sources['inherited_geometry_file_identities']),
     'representative_task_counts':counts,'reference_assignment_source_verified':True,
     'accepted_decision':'No additional training or new model is presently justified; trusted indexed target has a direct coordinate solution',
     'scope_finding':'Available synthetic unperturbed references remain valid training/evaluation targets for the authorized synthetic inverse task even when excluded from inference. Real artistic acceptance evidence is a separate product gap, not a mandatory prerequisite for all subsequent synthetic research.',
     'planner_contract_clarification_needed':True,'geometry_arrays_opened':0,'weight_arrays_opened':0,
     'training':0,'Bunny_arrays':0,'actual_restore_calls':0,
     'wall_s_before_final_write':time.perf_counter()-start,'CPU_s_before_final_write':time.process_time()-cpu}
(HERE/'INDEPENDENT_RESULTS.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({k:v for k,v in out.items() if k!='new_files'},indent=2))
