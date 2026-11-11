"""Exact-source query schema/runtime contrast using explicit static rules.

No external validator dependency is installed. The bounded evaluator below
implements only the JSON Schema keywords visited by these three fixed inputs;
an unhandled keyword fails the audit instead of silently accepting it.
"""
import copy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import types
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ENGINE=HERE/'candidate_replay/e'
IDENTITY=json.loads((HERE/'candidate_replay/EXECUTION_IDENTITY.json').read_bytes())
MANIFEST=IDENTITY['manifest']
blobs={row['path']:(ENGINE/row['path']).read_bytes() for row in MANIFEST}
assert all(hashlib.sha256(blobs[row['path']]).hexdigest()==row['sha256'] for row in MANIFEST)
loader='human_eye_plugin/verified_source_loader.py'
helper=types.ModuleType('_human_eye_verified_source_bootstrap')
helper.__file__=str(ENGINE/loader);sys.modules[helper.__name__]=helper
exec(compile(blobs[loader],helper.__file__,'exec',dont_inherit=True),helper.__dict__)
guard=helper.install(ENGINE.resolve(),MANIFEST,sources=blobs,bootstrap_module=helper)
package=types.ModuleType('human_eye_plugin');package.__path__=[str(ENGINE/'human_eye_plugin')]
guard.allow_namespace(package);sys.modules[package.__name__]=package

def forbidden(*a,**kw):raise AssertionError('external action forbidden')
with patch.object(socket,'socket',side_effect=forbidden),patch.object(subprocess,'Popen',side_effect=forbidden):
    from human_eye_plugin import live_spatial_mcp as mcp
    from human_eye_plugin.query_policy import validate_query

VISITED=set()
def accepts(schema,value):
    if isinstance(schema,bool):return schema
    supported={'type','properties','required','additionalProperties','oneOf','anyOf','allOf','if','then',
               'enum','const','minItems','maxItems','uniqueItems','items','contains','minLength','maxLength',
               'description','default'}
    unknown=set(schema)-supported
    if unknown:raise AssertionError('unsupported visited schema keyword '+str(unknown))
    VISITED.update(schema)
    kind=schema.get('type')
    if kind is not None:
        tests={'object':type(value) is dict,'array':type(value) is list,'string':type(value) is str,
               'boolean':type(value) is bool,'number':type(value) in (int,float),'integer':type(value) is int}
        if kind not in tests:raise AssertionError('unknown type')
        if not tests[kind]:return False
    if 'enum' in schema and value not in schema['enum']:return False
    if 'const' in schema and value!=schema['const']:return False
    if isinstance(value,dict):
        if any(key not in value for key in schema.get('required',())):return False
        properties=schema.get('properties',{})
        if schema.get('additionalProperties') is False and set(value)-set(properties):return False
        if any(not accepts(properties[key],item) for key,item in value.items() if key in properties):return False
    if isinstance(value,list):
        if len(value)<schema.get('minItems',0) or len(value)>schema.get('maxItems',float('inf')):return False
        if schema.get('uniqueItems') and len({json.dumps(item,sort_keys=True) for item in value})!=len(value):return False
        if 'items' in schema and any(not accepts(schema['items'],item) for item in value):return False
        if 'contains' in schema and not any(accepts(schema['contains'],item) for item in value):return False
    if isinstance(value,str):
        if len(value)<schema.get('minLength',0) or len(value)>schema.get('maxLength',float('inf')):return False
    if 'allOf' in schema and not all(accepts(item,value) for item in schema['allOf']):return False
    if 'anyOf' in schema and not any(accepts(item,value) for item in schema['anyOf']):return False
    if 'oneOf' in schema and sum(accepts(item,value) for item in schema['oneOf'])!=1:return False
    if 'if' in schema and accepts(schema['if'],value) and 'then' in schema and not accepts(schema['then'],value):return False
    return True

requests={
    'overview_geometry':{'mode':'overview','geometry':{'objects':[{'id':'a'}]}},
    'legacy_task_AABB_geometry':{'mode':'task','objects':[{'id':'a'}],'requested_facts':['aabb'],
                                'geometry':{'objects':[{'id':'a'}]}},
    'valid_target_candidates_geometry':{'mode':'task','target':{'id':'a'},'candidates':[{'id':'b'}],
        'requested_facts':['closed_solid_relation','surface_proximity'],'geometry':{'objects':[{'id':'a'}]}},
}
records=[]
for name,query in requests.items():
    schema_accepts=accepts(mcp._QUERY_SCHEMA,query)
    try:
        normalized=validate_query(copy.deepcopy(query));runtime_accepts=True;error=None
    except ValueError as exc:normalized=None;runtime_accepts=False;error=str(exc)
    # This is the actual generic tool runtime validator, before service/host.
    try:
        mcp._validate_arguments('human_eye_scene_observe',{'query':copy.deepcopy(query),'include_image':False})
        tool_accepts=True;tool_error=None
    except ValueError as exc:tool_accepts=False;tool_error=str(exc)
    records.append({'name':name,'actual_tool_arguments':{'query':query,'include_image':False},
        'actual_query_schema_accepts_by_explicit_static_rules':schema_accepts,
        'runtime_validate_query_accepts':runtime_accepts,'runtime_error':error,
        'actual_tool_runtime_validator_accepts':tool_accepts,'tool_error':tool_error,'normalized':normalized})

# Exact baseline is the preserved source checked by its old execution identity.
BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_relation_selected_evidence_001/offline/b2')
base_identity=json.loads((BASE/'EXECUTION_IDENTITY.json').read_bytes())
base_blob=(BASE/'e/human_eye_plugin/live_spatial_mcp.py').read_bytes()
base_manifest={row['path']:row['sha256'] for row in base_identity['manifest']}
assert hashlib.sha256(base_blob).hexdigest()==base_manifest['human_eye_plugin/live_spatial_mcp.py']
baseline_query_text=base_blob.decode().split('_QUERY_SCHEMA = {',1)[1].split('_GOAL_SCHEMA = {',1)[0]
assert "'geometry'" not in baseline_query_text and '"geometry"' not in baseline_query_text
assert '"additionalProperties": False' in baseline_query_text
assert all(row['actual_query_schema_accepts_by_explicit_static_rules'] for row in records)
assert [row['runtime_validate_query_accepts'] for row in records]==[False,False,True]
assert [row['actual_tool_runtime_validator_accepts'] for row in records]==[False,False,True]
assert guard.verify_loaded()
result={'confirmed':True,'records':records,'validation_method':'bounded independent evaluator of explicitly listed static JSON Schema rules; no third-party validator installed',
        'visited_keywords':sorted(VISITED),'candidate_source_sha256':IDENTITY['runtime_source_sha256'],
        'introduced_by_new_global_geometry_property':True,
        'baseline_proof':'fixed baseline query properties do not contain geometry and additionalProperties is false; these inputs were rejected by old schema',
        'scope':'generic human_eye_scene_observe query schema; compact relation tool unaffected; zero host calls',
        'minimal_fix':'Restrict geometry to mode=task with target and candidates in generic query schema; retain runtime normalization and legacy rejection unchanged',
        'host_calls':0,'Blender':0,'consumers':0,'dependency_installs':0}
with (HERE/'SCHEMA_SCOPE_REPRO.json').open('x',encoding='utf8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
with (HERE/'CANDIDATE_QUERY_SCHEMA.json').open('x',encoding='utf8') as stream:json.dump(mcp._QUERY_SCHEMA,stream,ensure_ascii=False,indent=2)
print(json.dumps({'confirmed':True,'cases':[{k:r[k] for k in ('name','actual_query_schema_accepts_by_explicit_static_rules','actual_tool_runtime_validator_accepts')} for r in records]}))
