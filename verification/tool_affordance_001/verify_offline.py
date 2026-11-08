"""One offline catalogue/description and original-parser verification.

Run with a SHA-bearing -c compile bootstrap, whose __main__ has no file below
the product root. This harness is outside the original product execution guard.
No candidate source tree is copied: baseline reuses its sealed engine; candidate
executes the exact workspace files through the unmodified verified loader.
"""
import ast
import copy
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback
import types
from types import MappingProxyType
from unittest.mock import patch

RUNNER = Path(__file__).resolve()
OUT = RUNNER.parent
ROOT = OUT.parents[1]
DEST = OUT/'offline_04'
BASE = 'bfcde7e739d61049271cc715e448fe849b10ef3e'
BASE_ROOT = ROOT/'verification/zero_witness_reuse_001/offline_01/engine'
BASE_SOURCE = 'ec3ac8c9dd83137e1d6cb5371fe4c2bc15ac56d34aafcb6933e8f76c07e897ae'
REL = 'human_eye_plugin/live_spatial_mcp.py'
sha = lambda b: hashlib.sha256(b).hexdigest()
started_ns = time.perf_counter_ns()
started_utc = datetime.now(timezone.utc).isoformat()
assert not DEST.exists(), 'single fresh offline invocation only'
DEST.mkdir()
save = lambda name,value: (DEST/name).write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode())


def git(*args, data=None):
    return subprocess.check_output(['git',*args],cwd=ROOT,input=data)


def constants(raw):
    return {node.targets[0].id:ast.literal_eval(node.value) for node in ast.parse(raw).body
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)
        and node.targets[0].id in ('BASE_VERSION','IMPLEMENTATION_REVISION','_ROOT_MODULES')}


def manifest(blobs):
    return [dict(path=p,sha256=sha(b)) for p,b in sorted(blobs.items())]


def canonical(blobs):
    c=constants(blobs['human_eye_plugin/runtime_identity.py'])
    return sha(json.dumps(dict(base_version=c['BASE_VERSION'],implementation_revision=c['IMPLEMENTATION_REVISION'],
        files=manifest(blobs)),sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())


def strip_description(value):
    if isinstance(value,dict):
        return {k:strip_description(v) for k,v in value.items() if k!='description'}
    if isinstance(value,list):return [strip_description(v) for v in value]
    return value


def description_map(value,path=''):
    result={}
    if isinstance(value,dict):
        for k,v in value.items():
            if k=='description':result[path+'/description']=v
            else:result.update(description_map(v,path+'/'+k))
    elif isinstance(value,list):
        for i,v in enumerate(value):result.update(description_map(v,path+'/'+str(i)))
    return result


class StripDescriptions(ast.NodeTransformer):
    def visit_Dict(self,node):
        pairs=[(k,v) for k,v in zip(node.keys,node.values)
            if not isinstance(k,ast.Constant) or k.value!='description']
        node.keys=[p[0] for p in pairs];node.values=[p[1] for p in pairs]
        return self.generic_visit(node)


def ast_proof(old,new):
    before=ast.parse(old);after=ast.parse(new)
    a=ast.dump(StripDescriptions().visit(before),include_attributes=False)
    b=ast.dump(StripDescriptions().visit(after),include_attributes=False)
    assert a==b,'only description dictionary entries may change'
    return dict(non_description_module_AST_equal=True,normalized_AST_sha256=sha(a.encode()),
        old_source_sha256=sha(old),new_source_sha256=sha(new))


def example_from(text):
    decoder=json.JSONDecoder()
    for index,char in enumerate(text):
        if char!='{':continue
        try:value,end=decoder.raw_decode(text[index:])
        except json.JSONDecodeError:continue
        if isinstance(value,dict) and isinstance(value.get('query'),dict) and value['query'].get('mode')=='task':
            return value,text[index:index+end]
    raise AssertionError('generic task JSON example absent')


def parser_cases(example):
    def observe(query,**extra):return dict(session_id='read-1',include_image=False,query=query,**extra)
    cases=[('generic_pair',example,True),
        ('surface_nearest_name',observe(dict(mode='surface_nearest',objects=[dict(name='A')])),True),
        ('surface_nearest_known_id',observe(dict(mode='surface_nearest'),focal_id='A'),True),
        ('task_aabb_four',observe(dict(mode='task',objects=[dict(name=x) for x in 'ABCD'],requested_facts=['aabb'])),True)]
    for mode in ('overview','exact_pairs','nearest','top1'):
        q=dict(mode=mode)
        if mode!='overview':q.update(object_ids=['B'],max_exact_pairs=1)
        cases.append((mode,observe(q,focal_id='A'),True))
    cases += [('mesh_structure_diagnose',observe(dict(mode='mesh_structure',operation='diagnose',request_id='read-1')),True),
        ('mesh_surface_diagnose',observe(dict(mode='mesh_surface',operation='diagnose',request_id='read-1')),True),
        ('pair_one_selector',observe(dict(mode='task',objects=[dict(name='A')],requested_facts=['closed_solid_relation','surface_proximity'])),False),
        ('pair_three_selectors',observe(dict(mode='task',objects=[dict(name=x) for x in 'ABC'],requested_facts=['closed_solid_relation'])),False),
        ('selector_name_and_id',observe(dict(mode='task',objects=[dict(name='A',id='A'),dict(name='B')],requested_facts=['surface_proximity'])),False),
        ('nearest_two_selectors',observe(dict(mode='surface_nearest',objects=[dict(name='A'),dict(name='B')])),False),
        ('nearest_selector_and_focal',observe(dict(mode='surface_nearest',objects=[dict(name='A')]),focal_id='A'),False),
        ('unknown_fact',observe(dict(mode='task',objects=[dict(name='A'),dict(name='B')],requested_facts=['identity'])),False)]
    return cases


def clear_guard(guard):
    sys.meta_path.remove(guard)
    for name in list(sys.modules):
        if guard._owned_name(name) or name=='_human_eye_verified_source_bootstrap':
            sys.modules.pop(name,None)


def arm(label,root,blobs,cases,example):
    helper=types.ModuleType('_human_eye_verified_source_bootstrap')
    helper.__file__=str(root/'human_eye_plugin/verified_source_loader.py')
    sys.modules[helper.__name__]=helper
    exec(compile(blobs['human_eye_plugin/verified_source_loader.py'],helper.__file__,'exec',dont_inherit=True),helper.__dict__)
    guard=helper.install(root,manifest(blobs),sources=MappingProxyType(blobs),bootstrap_module=helper)
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(root/'human_eye_plugin')]
    guard.allow_namespace(package);sys.modules[package.__name__]=package
    try:
        product=importlib.import_module('human_eye_plugin.live_spatial_mcp')
        runtime=importlib.import_module('human_eye_plugin.runtime_identity')
        wire=importlib.import_module('human_eye_plugin.mcp_transport')
        assert runtime.runtime_identity()['source_sha256']==canonical(blobs)
        class NoHost:
            def __getattr__(self,name):raise AssertionError('offline catalogue must not access service: '+name)
        request=dict(jsonrpc='2.0',id=1,method='tools/list')
        server=product.LiveSpatialMCPServer(NoHost(),default_session_id='offline-only')
        response=server.handle_jsonrpc_message(request)
        tools=response['result']['tools'];assert tools==product.LIVE_MCP_TOOLS_SCHEMA
        compact=json.dumps(tools,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
        production=wire.encode_response(response,request).encode('utf8')
        (DEST/(label+'_catalogue.compact.json')).write_bytes(compact)
        (DEST/(label+'_tools_list.production.json')).write_bytes(production)
        (DEST/(label+'_observe.compact.json')).write_bytes(json.dumps(tools[0],ensure_ascii=False,allow_nan=False,separators=(',',':')).encode())
        (DEST/(label+'_observe.production.json')).write_bytes(json.dumps(tools[0],ensure_ascii=True,allow_nan=False).encode())
        (DEST/(label+'_observe.inputSchema.json')).write_bytes(json.dumps(tools[0]['inputSchema'],ensure_ascii=False,allow_nan=False,separators=(',',':')).encode())
        save(label+'_manifest.json',manifest(blobs))
        rows=[]
        for name,args,expected in cases:
            try:product._validate_arguments('human_eye_scene_observe',copy.deepcopy(args))
            except ValueError as error:accepted=False;reason=str(error)
            else:accepted=True;reason=None
            assert accepted==expected,(label,name,accepted,expected,reason)
            rows.append(dict(name=name,arguments=args,expected_accepted=expected,accepted=accepted,reason=reason))
        normalized=product.validate_query(example['query'])
        assert normalized==example['query']
        assert guard.verify_loaded()
        loaded={name:guard._executed[id(module)][1] for name,module in list(sys.modules.items())
            if guard._owned_name(name) and id(module) in guard._executed}
        dependencies={name:dict(path=str(Path(module.__file__).resolve()),version=getattr(module,'__version__',None),
            file_sha256=sha(Path(module.__file__).read_bytes())) for name in ('numpy','PIL')
            if (module:=sys.modules.get(name)) is not None}
        save(label+'_execution_identity.json',dict(source_root=str(root),source_sha256=canonical(blobs),
            manifest=manifest(blobs),guard_protocol=helper.PROTOCOL,guard_verify_loaded=True,
            loaded_product_witnesses=loaded,runner_scope='outside product guard; exact runner bytes/hash separately recorded',
            product_execution='original verified_source_loader; unmodified exact source bytes',copied_candidate_source_tree=False,
            trusted_external_dependency_origins=dependencies))
        return dict(tools=tools,rows=rows,source_sha256=canonical(blobs),
            catalogue_compact_UTF8_bytes=len(compact),observe_compact_UTF8_bytes=len((DEST/(label+'_observe.compact.json')).read_bytes()),
            observe_production_UTF8_bytes=len((DEST/(label+'_observe.production.json')).read_bytes()),
            production_tools_list_UTF8_bytes=len(production),production_tools_list_sha256=sha(production))
    finally:clear_guard(guard)


forbidden=[]
def forbid(*args,**kwargs):
    forbidden.append('network/process/signal attempt')
    raise AssertionError(forbidden[-1])


try:
    assert git('rev-parse','HEAD').decode().strip()==BASE
    c=constants((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
    names=sorted(set(c['_ROOT_MODULES'])|{p.relative_to(ROOT).as_posix()
        for package in ('human_eye_plugin','human_eye_module1_operators') for p in (ROOT/package).glob('*.py')})
    assert len(names)==131
    baseline={p:(BASE_ROOT/p).read_bytes() for p in names}
    candidate={p:(ROOT/p).read_bytes() for p in names}
    # One batched local Git read before the execution/network/process guards.
    raw=git('cat-file','--batch',data=b''.join((BASE+':'+p+'\n').encode() for p in names));offset=0
    for p in names:
        end=raw.index(b'\n',offset);header=raw[offset:end].split();assert header[1]==b'blob'
        size=int(header[2]);offset=end+1
        assert raw[offset:offset+size]==baseline[p],p
        assert raw[offset+size:offset+size+1]==b'\n';offset+=size+1
    assert offset==len(raw) and canonical(baseline)==BASE_SOURCE
    changed=[p for p in names if baseline[p]!=candidate[p]];assert changed==[REL],changed
    ast_result=ast_proof(baseline[REL],candidate[REL])
    (DEST/'baseline_live_spatial_mcp.py').write_bytes(baseline[REL])
    (DEST/'candidate_live_spatial_mcp.py').write_bytes(candidate[REL])
    source_ast=ast.parse(candidate[REL]);description_literals=[]
    for node in ast.walk(source_ast):
        if isinstance(node,ast.Dict):
            for key,value in zip(node.keys,node.values):
                if isinstance(key,ast.Constant) and key.value=='description' and isinstance(value,ast.Constant):
                    description_literals.append(value.value)
    matches=[example_from(text) for text in description_literals if '"requested_facts"' in text and '"mode":"task"' in text]
    assert len(matches)==1
    example,example_text=matches[0]
    assert example==dict(session_id='read-1',include_image=False,query=dict(mode='task',objects=[dict(name='A'),dict(name='B')],requested_facts=['closed_solid_relation','surface_proximity']))
    (DEST/'generic_example.json').write_bytes(example_text.encode())
    cases=parser_cases(example)
    with ExitStack() as guards:
        for name in ('Popen','run','call','check_call','check_output'):guards.enter_context(patch.object(subprocess,name,side_effect=forbid))
        for name in ('kill','system'):guards.enter_context(patch.object(os,name,side_effect=forbid))
        guards.enter_context(patch.object(socket,'socket',side_effect=forbid))
        guards.enter_context(patch.object(socket,'create_connection',side_effect=forbid))
        old=arm('baseline',BASE_ROOT.resolve(),baseline,cases,example)
        new=arm('candidate',ROOT.resolve(),candidate,cases,example)
    assert strip_description(old['tools'])==strip_description(new['tools'])
    for field in ('catalogue_compact_UTF8_bytes','observe_compact_UTF8_bytes','observe_production_UTF8_bytes','production_tools_list_UTF8_bytes'):
        assert new[field]<=old[field],(field,old[field],new[field])
    old_desc=description_map(old['tools']);new_desc=description_map(new['tools'])
    differences=[dict(path=p,before=old_desc.get(p),after=new_desc.get(p))
        for p in sorted(set(old_desc)|set(new_desc)) if old_desc.get(p)!=new_desc.get(p)]
    assert differences and all(p['path'].startswith('/0/') for p in differences)
    save('description_changes.json',differences)
    save('structure_proof.json',dict(source_AST=ast_result,recursive_description_stripped_schemas_equal=True,
        normalized_structure_sha256=sha(json.dumps(strip_description(old['tools']),sort_keys=True,separators=(',',':')).encode()),
        changed_source_paths=changed,changed_description_paths=[p['path'] for p in differences]))
    save('parser_results.json',dict(baseline=old['rows'],candidate=new['rows'],
        identical_original_parser_outcomes=old['rows']==new['rows'],example_normalizes_identically=True))
    for p in names:assert (ROOT/p).read_bytes()==candidate[p],p
    result=dict(passed=True,started_utc=started_utc,ended_utc=datetime.now(timezone.utc).isoformat(),elapsed_ns=time.perf_counter_ns()-started_ns,
        source_count=131,baseline_source_sha256=old['source_sha256'],candidate_source_sha256=new['source_sha256'],
        bytes={key:dict(baseline=old[key],candidate=new[key],delta=new[key]-old[key]) for key in ('catalogue_compact_UTF8_bytes','observe_compact_UTF8_bytes','observe_production_UTF8_bytes','production_tools_list_UTF8_bytes')},
        original_parser_cases_per_arm=len(cases),original_parser_case_executions=2*len(cases),
        description_changes=len(differences),JSONSchema_validation='pending external native PowerShell Test-Json against archived actual inputSchema files; not implemented by this runner',
        forbidden_attempts=forbidden,Blender_sessions=0,field_RPC=0,model_consumers=0,performance_samples=0,
        inprocess_tools_list_dispatches=2,live_service_dispatches=0,
        runner=dict(path=str(RUNNER),sha256=sha(RUNNER.read_bytes()),compile_filename='sha256-bearing bootstrap recorded by outer invocation'))
    result['interpreter']=dict(path=str(Path(sys.executable).resolve()),sha256=sha(Path(sys.executable).read_bytes()),version=sys.version)
    save('RESULTS.json',result)
    print(json.dumps(result))
except BaseException:
    save('FAILURE.json',dict(started_utc=started_utc,ended_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_ns=time.perf_counter_ns()-started_ns,traceback=traceback.format_exc(),forbidden_attempts=forbidden,
        Blender_sessions=0,field_RPC=0,model_consumers=0,performance_samples=0))
    raise
