"""Functional-only pure return observer around the original installed bootstrap.

No product function/argument is replaced. Not used for any timing denominator.
The original stdio bytes remain the production entry's stdout.
"""
from __future__ import annotations
from collections import Counter
from fractions import Fraction as Q
import copy
import hashlib
import json
from pathlib import Path
import runpy
import sys
import traceback


def dump(path,value):
    def array(value):
        if type(value).__module__.startswith('numpy'):
            return value.tolist() if hasattr(value,'tolist')else value.item()
        if isinstance(value,Q):return str(value)
        raise TypeError(type(value).__name__)
    with path.open('x',encoding='utf8',newline='\n')as f:json.dump(value,f,ensure_ascii=False,allow_nan=False,indent=2,default=array);f.write('\n')


def main():
    entry=Path(sys.argv[1]).resolve();args=sys.argv[2:]
    config=Path(args[args.index('--config')+1]).resolve();folder=config.parent/'RETURN_OBSERVER'
    folder.mkdir(exist_ok=False)
    packets=[];tasks=[];trees=[];surfaces=[];active={}
    def observe(frame,event,arg):
        module=frame.f_globals.get('__name__');name=frame.f_code.co_name
        if module=='human_eye_plugin.blender_mcp_host' and name=='_materialize_selective_capture' and event=='return' and type(arg)is dict:
            packets.append({'capture':copy.deepcopy(arg),
                'residency_reply':copy.deepcopy(frame.f_locals.get('reply')),
                'function_file':frame.f_code.co_filename})
        if module=='human_eye_plugin.blender_mcp_host' and name=='capture_task_scene'and event=='return'and type(arg)is dict:
            tasks.append({'capture':copy.deepcopy(arg),'function_file':frame.f_code.co_filename})
        if module!='human_eye_plugin.surface_proximity':return
        if name=='measure_surface_proximity' and event=='return' and type(arg)is dict:
            v=frame.f_locals;points=v.get('points');origin=v.get('origin');factor=v.get('factor')
            exact=None
            if points is not None and origin is not None and factor is not None:
                exact=[[str(Q(origin[k])+Q(p[k])/factor)for k in range(3)]for p in points]
            surfaces.append({'function_file':frame.f_code.co_filename,'value':copy.deepcopy(arg),
                             'exact_world_points':exact})
        if name=='_nearest_tree' and event=='call':active[id(frame)]=Counter()
        elif name=='push_pair' and event=='return' and 'secondary'in frame.f_locals:
            v=frame.f_locals;counter=active.get(id(frame.f_back))
            if counter is not None and v.get('contained_zero_fifo') and v.get('key')==0:
                counter['zero_key_FIFO_enqueues']+=1
                if v.get('cdist')!=0:counter['changed_secondary_enqueues']+=1
        elif name=='_nearest_tree' and event=='return':
            v=frame.f_locals;roots=v.get('roots')
            trees.append({'function_file':frame.f_code.co_filename,'shift':v.get('shift'),
                'contained_zero_fifo':v.get('contained_zero_fifo'),'best_pair':v.get('best_pair'),
                'integer_root_bounds':[[list(r[0]),list(r[1])]for r in roots]if roots else None,
                'enqueue':dict(active.pop(id(frame),{}))})
    previous=sys.getprofile();error=None
    try:
        sys.setprofile(observe);sys.argv=[str(entry),*args]
        runpy.run_path(str(entry),run_name='__main__')
    except BaseException as exc:
        if not isinstance(exc,SystemExit) or exc.code not in (None,0):error=traceback.format_exc()
        raise
    finally:
        sys.setprofile(previous)
        refs=[]
        for i,value in enumerate(packets,1):
            path=folder/f'CAPTURE_{i:03d}.json';dump(path,value);b=path.read_bytes()
            refs.append({'path':str(path),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
        dump(folder/'TREES.json',trees)
        dump(folder/'TASK_CAPTURES.json',tasks)
        dump(folder/'SURFACE_RETURNS.json',surfaces)
        dump(folder/'INDEX.json',{'schema':'m6-043-functional-return-observer-v1','entry':str(entry),
            'config':str(config),'captures':refs,'tree_returns':len(trees),'error':error,
            'methods_or_arguments_modified':False,'stdout_source':'original installed production stdio',
            'performance_sample':False})


if __name__=='__main__':main()
