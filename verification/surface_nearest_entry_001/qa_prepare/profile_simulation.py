"""Stdlib-only exercise of the exact QA hook body; no Blender/product import."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import types

FOLDER = Path(__file__).resolve().parent
source = (FOLDER/'fixture_setup.py').read_bytes()
tree = ast.parse(source)
profile_node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_qa_profile')
module = ast.Module(body=[profile_node],type_ignores=[])
path = '<stdlib-only-QA-standin-host>'
class Coordinate:
    def __init__(self,values): self.values=list(values)
    @property
    def x(self): return self.values[0]
    @x.setter
    def x(self,value): self.values[0]=value
    def __iter__(self): return iter(self.values)
class Vertex:
    def __init__(self,values): self.co=values
    @property
    def co(self): return self.value
    @co.setter
    def co(self,value): self.value=Coordinate(value)
original=[(100.,float(i),0.) for i in range(6)]
results=[]
for state in (1,2,3):
    for outcome in ('normal','unwind'):
        receipt=dict(calls=0,returns=0,restored=False,events=[],profile_overhead_ns=0)
        mesh=types.SimpleNamespace(vertices=[Vertex(p) for p in original],update=lambda:None)
        def coordinates(): return [tuple(v.co) for v in mesh.vertices]
        def restore():
            for vertex,coordinate in zip(mesh.vertices,original): vertex.co=coordinate
            receipt['restored']=coordinates()==original
        snapshots=[]
        def persist(): snapshots.append(copy.deepcopy(receipt))
        namespace=dict(STATE=state,PLAN=dict(host_sha256='frozen-host-sha'),_qa_host_path=path,
            _READONLY_LOADED_HOST_SHA256='frozen-host-sha',_surface_entry_fixture=receipt,
            _qa_mesh=mesh,_qa_snapshot=coordinates,_qa_restore_geometry=restore,_qa_persist=persist,
            bpy=types.SimpleNamespace(context=types.SimpleNamespace(view_layer=types.SimpleNamespace(update=lambda:None))),
            sys=sys,time=time,traceback=traceback,outcome=outcome)
        exec(compile(module,str(FOLDER/'fixture_setup.py'),'exec'),namespace)
        target_source='def capture_nearest_candidates():\n    observed = _qa_snapshot()\n    assert observed != _qa_original_expected if STATE in (2,3) else observed == _qa_original_expected\n    if outcome == "unwind": raise ValueError("standin-exception")\n    return {"standin": True}\n'
        namespace['_qa_original_expected']=original
        exec(compile(target_source,path,'exec'),namespace)
        foreign={}; exec(compile('def capture_nearest_candidates():\n    return 5\n','<unrelated-file>','exec'),foreign)
        assert sys.getprofile() is None
        sys.setprofile(namespace['_qa_profile'])
        try:
            assert foreign['capture_nearest_candidates']()==5 and receipt['calls']==0
            try: namespace['capture_nearest_candidates']()
            except ValueError:
                assert outcome=='unwind'
        finally:
            ended_profile=sys.getprofile(); sys.setprofile(None); restore()
        assert ended_profile is None and receipt['calls']==receipt['returns']==1 and receipt['restored']
        assert not receipt.get('hook_error') and receipt['before']==receipt['after']==original
        assert receipt['events'][1]['returned_packet']==(outcome=='normal')
        results.append(dict(state=state,outcome=outcome,passed=True,receipt=receipt,persist_count=len(snapshots)))
result=dict(passed=True,stdlib_only=True,Blender_executions=0,NativeSession_executions=0,RPC=0,
    product_imports=0,qa_hook_source_sha256=hashlib.sha256(source).hexdigest(),
    scope='exact QA callback body against an explicit standin function; bpy compatibility remains unmeasured until authorized real batch',cases=results)
(FOLDER/'PROFILE_SIMULATION.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(passed=True,cases=len(results),Blender=0,NativeSession=0,RPC=0)))
