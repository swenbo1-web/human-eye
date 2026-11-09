"""Read-only fixture observer preceding the unchanged verified default worker.

Counts actual Python host entries. No RNA proxy, C-call probe or extra update.
Native snapshots read direct bpy RNA after a product request has returned.
"""
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time
import bpy

DEST=Path(os.environ['M5_QA_WORKER_OBSERVER'])
COUNTS=Counter()
ATTACHED=False
HOST_NAMES={'_capture','_resident_capture','capture_evidence','capture_delta',
            'capture_scene','capture_task_scene','capture_nearest_candidates',
            'apply_transform','_assign_translation','_assign_matrix','_verify_readback',
            'begin_motion_goal','motion_goal_status','end_motion_goal'}

def emit(value):
    with DEST.open('a',encoding='utf8') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')

def snapshot(host, method, result):
    started=time.perf_counter_ns()
    meshes=[]
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH': continue
        if obj.modifiers or obj.constraints or obj.parent:
            raise ValueError('QA native oracle only accepts plain independent meshes')
        meshes.append({'name':obj.name,'vertices':[list(obj.matrix_world @ v.co) for v in obj.data.vertices],
            'local_vertices':[list(v.co) for v in obj.data.vertices],
            'faces':[list(p.vertices) for p in obj.data.polygons],
            'matrix':[[float(obj.matrix_world[r][c]) for c in range(4)] for r in range(4)],
            'color':list(obj.color)})
    emit({'event':'native_snapshot','method':method,'pid':os.getpid(),
        'host_calls':dict(COUNTS),'resident_work':host.residency_work(),
        'native':{'meshes':meshes,'scale':bpy.context.scene.unit_settings.scale_length,
            'basis':'direct native bpy RNA after product return; no extra depsgraph update'},
        'observer_ms_before_append':(time.perf_counter_ns()-started)/1e6})

def profile(frame,event,arg):
    global ATTACHED
    code=frame.f_code
    path=code.co_filename.replace('\\','/')
    if path.endswith('/blender_host.py') and event=='call' and code.co_name in HOST_NAMES:
        COUNTS[code.co_name]+=1
    if ATTACHED or event!='return' or code.co_name!='__init__': return
    host=frame.f_locals.get('self')
    if host is None or type(host).__name__!='BlenderSceneHost': return
    ATTACHED=True
    # A successful scheduler ends with end_motion_goal after its final capture
    # and status check; publish counters after that last real host traversal.
    for name in ('capture_evidence','capture_delta','apply_transform','end_motion_goal'):
        original=getattr(host,name)
        def wrapped(*a,_original=original,_name=name,**kw):
            result=_original(*a,**kw)
            snapshot(host,_name,result)
            return result
        setattr(host,name,wrapped)
    emit({'event':'observer_attached','pid':os.getpid(),'module':type(host).__module__,
          'source':sys.modules[type(host).__module__].__file__,
          'scope':'Python host entry counters + resident counters; nonresident to_mesh/triangulation unknown'})

emit({'event':'observer_armed','pid':os.getpid()})
sys.setprofile(profile)
