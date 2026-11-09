"""Operation and retained-array accounting only; no latency benchmark."""
import copy
import gc
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import weakref
from unittest.mock import patch
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from human_eye_plugin import live_service as ls, task_query as tq, auto_router
from human_eye_module1_operators import MeshEntity3D
from verification.arch_read_context_001.test_resident_task import TokenSelectedHost,compact
from verification.nearest_integration_001.tests.test_integration import packet_for

def forbidden(*a,**kw):raise AssertionError('No network, subprocess or host mutation')
def query(candidates):
    return {'mode':'task','target':{'id':'a'},'candidates':[{'id':oid} for oid in candidates],
            'requested_facts':['closed_solid_relation','surface_proximity','aabb']}
def memory(context):
    meshes={id(mesh):mesh for state in context._selections.values() if state['normalized'] is not None
            for mesh in state['normalized'][1]}
    arrays={}
    for mesh in meshes.values():
        for value in vars(mesh).values():
            if isinstance(value,np.ndarray):
                while isinstance(value.base,np.ndarray):value=value.base
                arrays[id(value)]=value
    return {'selection_count':len(context._selections),'mesh_entity_count':len(meshes),
            'numpy_root_array_count':len(arrays),'numpy_payload_bytes':sum(value.nbytes for value in arrays.values()),
            'result_body_count':sum(len(state['results']) for state in context._selections.values())}

def service(folder,host):
    config=folder/'config.json'
    config.write_bytes(compact({'schema_version':'1.0','project_root':str(ROOT),'state_file':'action.json',
        'audit_file':'audit.jsonl','quad_size':64,'enabled':True}))
    return ls.LiveSpatialService(config,host=host)

def sequence(candidates):
    with tempfile.TemporaryDirectory() as temporary:
        host=TokenSelectedHost();reader=service(Path(temporary),host)
        rows=[]
        with patch.object(ls,'_validated_scene',wraps=ls._validated_scene) as normalize, \
             patch.object(tq,'task_result',wraps=tq.task_result) as result, \
             patch.object(tq,'classify_closed_solids',wraps=tq.classify_closed_solids) as closed, \
             patch.object(tq,'measure_surface_proximity',wraps=tq.measure_surface_proximity) as surface, \
             patch.object(auto_router.MeshEntity3D,'from_dict',wraps=auto_router.MeshEntity3D.from_dict) as build:
            counts=lambda:[normalize.call_count,result.call_count,closed.call_count,surface.call_count,build.call_count]
            for selected in candidates:
                before=counts()
                answer=reader.observe('s',query=query(selected),include_image=False)
                after=counts()
                rows.append({'selection':selected,'work':dict(zip(('normalize','task_result','closed_kernel','surface_kernel','mesh_build'),
                    [right-left for left,right in zip(before,after)])),'memory':memory(reader._read_context),
                    'status':answer['status']})
        assert [row['work']['normalize'] for row in rows]==[1,1,0]
        assert [row['work']['task_result'] for row in rows]==[1,1,0]
        assert rows[2]['work']['mesh_build']==0
        return rows

def capacity():
    with tempfile.TemporaryDirectory() as temporary:
        host=TokenSelectedHost();reader=service(Path(temporary),host);rows=[]
        refs=[]
        for index in range(9):
            host.selection_nonce=str(index)
            reader.observe('s',query=query(('b',)),include_image=False)
            if index==0:refs=[weakref.ref(mesh) for mesh in reader._read_context._normalized[1]]
            if index in (0,7,8):rows.append({'after_selection':index+1,**memory(reader._read_context)})
        gc.collect()
        assert all(ref() is None for ref in refs),'Evicted selection retains mesh objects'
        host.capture_revision+=1
        reader.observe('s',query=query(('b',)),include_image=False)
        rows.append({'after_global_revision_change':True,**memory(reader._read_context)})
        assert rows[1]['selection_count']==rows[2]['selection_count']==8 and rows[-1]['selection_count']==1
        return {'snapshots':rows,'evicted_first_meshes_collected':True}

class DualHost(TokenSelectedHost):
    def __init__(self):
        super().__init__();self.scene['source']='blender'
        meshes={item['object_id']:MeshEntity3D.from_dict(item) for item in self.scene['meshes']}
        self.packet=packet_for(meshes['a'],[meshes[oid] for oid in ('b','c','d')])
        full=self.packet['binding']['host_identity']
        self.document=full['document_epoch'];self.instances=full['object_instances']
    def capture_nearest_candidates(self,*a,**kw):
        packet=copy.deepcopy(self.packet)
        packet['capture']['capture_state']={'instance_id':self.capture_instance,'epoch':self.capture_epoch,
            'revision':self.capture_revision,'selection_key':'nearest-a'}
        return packet

def isolation():
    with tempfile.TemporaryDirectory() as temporary:
        host=DualHost();reader=service(Path(temporary),host)
        with patch.object(ls,'_validated_scene',wraps=ls._validated_scene) as normalize, \
             patch.object(tq,'task_result',wraps=tq.task_result) as task, \
             patch.object(tq,'surface_nearest_result',wraps=tq.surface_nearest_result) as nearest:
            first=reader.observe('s',query=query(('b',)),include_image=False)
            read=reader.observe('s',query={'mode':'surface_nearest'},focal_id='a',include_image=False)
            again=reader.observe('s',query=query(('b',)),include_image=False)
            read_again=reader.observe('s',query={'mode':'surface_nearest'},focal_id='a',include_image=False)
        assert normalize.call_count==2 and task.call_count==nearest.call_count==1
        assert first['pairs']==again['pairs'] and read['nearest_objects']==read_again['nearest_objects']
        return {'normalize':normalize.call_count,'task_result':task.call_count,'nearest_result':nearest.call_count,
                'memory':memory(reader._read_context),'task_and_nearest_isolated':True}

if __name__=='__main__':
    with patch.object(socket,'socket',side_effect=forbidden),patch.object(socket,'create_connection',side_effect=forbidden),patch.object(subprocess,'Popen',side_effect=forbidden):
        output={'AB_AD_AB':sequence([('b',),('d',),('b',)]),'AB_ABC_AB':sequence([('b',),('b','c'),('b',)]),
                'capacity':capacity(),'task_nearest_alternation':isolation(),
                'memory_scope':'deduplicated retained MeshEntity and root NumPy array payload, excludes scene dict/list/results/Python overhead and RSS; no latency sampling',
                'baseline_normalize_and_task_result_calls':3,'baseline_evidence':'root READ_CONTEXT_001_REVIEW.md accepted independent counts; not rerun',
                'review_sha256':hashlib.sha256(Path('D:/hefe/verification/fixes/20261109_architecture_completion/READ_CONTEXT_001_REVIEW.md').read_bytes()).hexdigest()}
    (OUT/'WORK_MEMORY.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf8')
    print(json.dumps(output,indent=2))
