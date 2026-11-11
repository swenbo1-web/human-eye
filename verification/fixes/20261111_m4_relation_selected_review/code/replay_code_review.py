"""Fixed isolated source replay and targeted attachment checks, no real host.

Only the reviewed finite offline runner is called. The entry/installation
runners are not imported. Temporary and output paths stay under this directory.
"""
from contextlib import ExitStack
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH=ROOT/'verification/m4_relation_selected_evidence_001'
EVIDENCE_COMMIT='be2de48bd9656787c4cdfbc5767c2551defcaada'
PRODUCT_COMMIT='a81e530a03460f93846e3bef4c45ebaa9347531b'
SOURCE_SHA='9f287f28a9be9ad0a06c0689b1fda3b15e9181efae0e280c0f2bcfed2d3ef504'
sha=lambda blob:hashlib.sha256(blob).hexdigest()
checks=[]

def save(name,value):
    with (HERE/name).open('x',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')

def check(value,name):
    checks.append({'check':name,'passed':bool(value)})

# Pin only inspected artifacts before executing a copy. The reviewed runner
# creates its own new physical 137-source package and bans external operations.
files={}
for relative in ('offline/run_offline.py','tests/test_selected_geometry.py','CONTRACT.md'):
    blob=(BATCH/relative).read_bytes()
    files[relative]={'sha256':sha(blob),'bytes':len(blob)}
runner_blob=(BATCH/'offline/run_offline.py').read_bytes()
assert sha(runner_blob)=='e44fb7bb07f73e57f418927fecee6358e7f316b603b31564bf547d7654cc8a56'
assert files['tests/test_selected_geometry.py']['sha256']=='6999e1d5bd2f42d117ac108a2966423c1ae0fa988eb2c9aba653af0222212338'
copy_path=HERE/'run_offline.copied.py'
with copy_path.open('xb') as stream:stream.write(runner_blob)
save('SOURCE_PINS.json',{'evidence_commit':EVIDENCE_COMMIT,'product_commit':PRODUCT_COMMIT,
                        'runtime_source_sha256':SOURCE_SHA,'files':files,
                        'adaptation':'copied runner ROOT points to fixed checkout; HERE points to independent review directory'})
spec=importlib.util.spec_from_file_location('reviewed_offline_runner',copy_path)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.ROOT,runner.HERE=ROOT,HERE
sys.argv=['run_offline.py','--role','candidate','--expected-source-sha256',SOURCE_SHA,'--output','candidate_replay']
exit_status=runner.main()
check(exit_status==0,'candidate_22_method_replay')

# The verified product package remains the same isolated package from the runner.
from human_eye_plugin import task_query
from human_eye_plugin.runtime_identity import runtime_identity
check(runtime_identity()['source_sha256']==SOURCE_SHA,'same_guarded_candidate_for_additional_checks')

class ListSpy:
    def __init__(self,values,forbidden=False):self.values=values;self.calls=0;self.forbidden=forbidden
    def tolist(self):
        self.calls+=1
        if self.forbidden:raise AssertionError('unrequested array conversion')
        return copy.deepcopy(self.values)

def reject(*args,**kwargs):raise AssertionError('no external operations allowed')
def absent(call):
    try:call()
    except ValueError:return True
    return False

with ExitStack() as guards:
    guards.enter_context(patch.object(subprocess,'Popen',side_effect=reject))
    guards.enter_context(patch.object(socket,'socket',side_effect=reject))
    guards.enter_context(patch.object(socket,'create_connection',side_effect=reject))
    # A normalized full-capture fallback may include unrelated objects.
    # Only original task binding identities may be projected from those meshes.
    a=SimpleNamespace(object_id='a',vertices=ListSpy([[1.,2.,3.]]),faces=ListSpy([[0,0,0]],True))
    outsider=SimpleNamespace(object_id='b',vertices=ListSpy([[9.,9.,9.]],True),faces=ListSpy([[0,0,0]],True))
    relation={'binding':{'objects':[{'object_id':'a','name':'b'}]},'facts':{'closed_solid_relation':{'status':'unknown'}}}
    original=copy.deepcopy(relation)
    result=task_query.project_task_geometry(relation,[a,outsider],{'objects':[{'name':'b'},{'id':'a'}],'include_triangles':False},lambda phase:None)
    check([row['object_id'] for row in result['objects']]==['a','a'],'name_alias_does_not_reinterpret_as_ID')
    check(a.faces.calls==0 and outsider.vertices.calls==0 and outsider.faces.calls==0,'vertices_only_does_not_convert_triangles_or_outsider')
    check(absent(lambda:task_query.project_task_geometry(relation,[a,outsider],{'objects':[{'id':'b'}],'include_triangles':False},lambda phase:None)),
          'full_capture_fallback_cannot_expose_unbound_ID')
    result['objects'][0]['vertices_world'][0][0]=900.
    check(result['objects'][1]['vertices_world'][0][0]==1. and a.vertices.values[0][0]==1.,'repeated_geometry_rows_have_no_mutable_alias')
    check(relation==original,'attachment_does_not_mutate_original_unknown_fact_or_binding')
    unresolved={'binding':{'objects':[{'object_id':'a','name':'b'},
                  {'status':'unknown','selector':{'name':'b'},'reason':'object_name_ambiguous'}]}}
    unknown=task_query.project_task_geometry(unresolved,[a,outsider],{'objects':[{'name':'b'}],'include_triangles':False},lambda phase:None)
    check(unknown['objects']==[{'selector':{'name':'b'},'status':'unknown','reason':'object_name_ambiguous'}],
          'original_unknown_remains_prior_to_successful_alias')
    checkpoint=[]
    a.faces.forbidden=False
    repeat=task_query.project_task_geometry(relation,[a,outsider],{'objects':[{'id':'a'},{'name':'b'}],'include_triangles':True},checkpoint.append)
    repeat['objects'][0]['triangles'][0][0]=99
    check(repeat['objects'][1]['triangles']==[[0,0,0]] and a.faces.values==[[0,0,0]],'triangles_detached_between_rows_and_mesh')
    check(checkpoint==['before_task_geometry_object','before_task_geometry_object','after_task_geometry'],'original_deadline_checkpoint_per_requested_object_and_end')
    raw={'mode':'task','target':{'id':'a'},'candidates':[{'id':'b'}],
         'requested_facts':['closed_solid_relation','surface_proximity'],
         'geometry':{'objects':[{'id':'a'}]}}
    normal=task_query.validate_task_query(raw)
    normal['geometry']['objects'][0]['id']='changed'
    check(raw['geometry']['objects']==[{'id':'a'}],'normalization_does_not_alias_user_selector')
    wrong=copy.deepcopy(raw);wrong['geometry']['objects']=[{'name':'界'*86}]
    check(absent(lambda:task_query.validate_task_query(wrong)),'geometry_uses_existing_UTF8_selector_limit')
    legacy={'mode':'task','objects':[{'id':'a'}],'requested_facts':['aabb'],'geometry':{'objects':[{'id':'a'}]}}
    check(absent(lambda:task_query.validate_task_query(legacy)),'legacy_AABB_query_does_not_accept_new_attachment')
    nearest={'mode':'surface_nearest','objects':[{'id':'a'}],'geometry':{'objects':[{'id':'a'}]}}
    from human_eye_plugin.query_policy import validate_query
    check(absent(lambda:validate_query(nearest)),'nearest_does_not_accept_new_attachment')

summary={'passed':all(row['passed'] for row in checks),'checks':checks,
         'independent_checks':len(checks),'runtime_source_sha256':SOURCE_SHA,
         'scope':'guarded physical source; copied reviewed offline runner plus pure attachment checks',
         'real_Blender':0,'model_consumers':0,'network':0,'installation':0,'default_changes':0,
         'performance_measurements':0}
save('ADDITIONAL_CHECKS.json',summary)
print(json.dumps({'additional_passed':summary['passed'],'checks':len(checks)}))
raise SystemExit(0 if summary['passed'] else 1)
