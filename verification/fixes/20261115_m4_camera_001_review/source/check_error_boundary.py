"""Fixed AST error boundary, real serializer; no live server or host calls."""
import ast
import contextvars
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
from typing import Any

TREE=Path('C:/Users/Administrator/.codex/worktrees/m4-camera-001/hefe')
OUT=Path(__file__).parent
COMMIT='4f8c41f89c9b40b3f310cf3f8e8b711bf09864a6'
pins={}
def source(name):
    rel='human_eye_plugin/'+name+'.py'
    b=subprocess.check_output(['git','-C',str(TREE),'show',COMMIT+':'+rel])
    pins[rel]=hashlib.sha256(b).hexdigest()
    assert b==(TREE/rel).read_bytes()
    assert b==(Path('D:/he_m4_camera_001/candidate/product')/rel).read_bytes()
    return ast.parse(b.decode('utf8'))
def execute(nodes,ns,label):
    exec(compile(ast.Module(body=nodes,type_ignores=[]),COMMIT+':'+label,'exec'),ns)

pkg=types.ModuleType('camera_audit_pkg');pkg.__path__=[];sys.modules[pkg.__name__]=pkg
host_tree=source('blender_host');process_tree=source('blender_process');service_tree=source('live_service')
for name,tree,names,extra in [
    ('blender_host',host_tree,{'BlenderHostError'},{}),
    ('blender_process',process_tree,{'HostRemoteError'},{'Any':Any}),
    ('live_service',service_tree,{'StateBindingError','RequestBudgetError','_request_error_fields'},
     {'copy':copy,'_REQUEST_BUDGET':contextvars.ContextVar('review_budget',default=None),'_REQUEST_BUDGET_SCOPE':'unused'})]:
    module=types.ModuleType(pkg.__name__+'.'+name);module.__dict__.update(extra)
    execute([n for n in tree.body if getattr(n,'name',None) in names],module.__dict__,name)
    sys.modules[module.__name__]=module;setattr(pkg,name,module)
mcp_tree=source('live_spatial_mcp')
server=next(n for n in mcp_tree.body if getattr(n,'name',None)=='LiveSpatialMCPServer')
method=next(n for n in server.body if getattr(n,'name',None)=='_error_result')
nodes=[n for n in mcp_tree.body if getattr(n,'name',None) in
       {'_tool_result','_project_capability_aliases','_project_support_plane_discovery_aliases'}]+[method]
artifact_records=[]
ns={'__package__':pkg.__name__,'copy':copy,'json':json,'Any':Any,
    'record_image_artifact':lambda *a,**k:artifact_records.append((a,k))}
execute(nodes,ns,'live_spatial_mcp')
class Boundary:
    def request_error_fields(self,error):return pkg.live_service._request_error_fields(error)
reason='active_observation_target_camera_numeric_insufficient'
BH=pkg.blender_host.BlenderHostError;HR=pkg.blender_process.HostRemoteError
class OtherHostError(BH):pass
base_remote={'type':'BlenderHostError','message':reason,'mutation_uncertain':False}
cases=[('exact_local',lambda:BH(reason),True),
       ('exact_remote',lambda:HR(dict(base_remote)),True),
       ('uncertain_remote',lambda:HR({**base_remote,'mutation_uncertain':True}),False),
       ('extra_receipt',lambda:HR({**base_remote,'mutation_receipt':{'executed':True}}),False),
       ('different_class',lambda:OtherHostError(reason),False),
       ('ordinary_same_text',lambda:ValueError(reason),False)]
records=[]
for name,make,match in cases:
    for executed in (False,True,None):
        saved={'executed':executed,'verified':False,'execution_verified':False,
            'execution_status':'not_executed' if executed is False else 'execution_uncertain',
            'operation_status':'committed' if executed is True else 'unknown',
            'host_mutation_started':executed,'execution_authority':False,'allow_action':False,
            'retry_authorized':False,'connector_state_write_committed':executed,
            'connector_state_write_unknown':executed is None}
        error=make();error._human_eye_request_fields=copy.deepcopy(saved)
        reply=ns['_error_result'](Boundary(),error)
        assert reply['isError'] is True and len(reply['content'])==1
        assert reply['content'][0]['type']=='text'
        value=json.loads(reply['content'][0]['text'])
        assert all(value[k]==v for k,v in saved.items())
        assert value['automatic_retry'] is False and value['tool_outcome']=='unknown'
        assert value['status']==('unknown' if match else 'error')
        assert (value.get('observation_status')=='numeric_insufficient')==match
        assert value['error']==str(error)
        assert error._human_eye_request_fields==saved
        records.append({'case':name,'executed':executed,'status':value['status'],'preserved_execution_fields':True})
assert len(artifact_records)==18 and all(r[1]['native_block_count']==0 for r in artifact_records)
result={'scope':'Fixed-source AST boundary + actual _tool_result serializer; saved execution metadata injected via real _request_error_fields',
        'source_pins':pins,'passed':True,'case_count':18,'records':records,
        'not_run':['live MCP','real side effects','host mutation','Blender'],
        'new_product_entry_Blender_raster_models':0}
(OUT/'ERROR_RESULT.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps({'cases':len(records),'passed':True,'new_live_calls':0}))
