"""Owned factory Blender raw-read baseline. No sockets, UI, edits to user files.

Run with --blender /path/to/blender --output NEW_DIRECTORY. The worker creates
analytic assets in its own unsaved factory scene. It measures source access,
validation and serialization, NOT a diagnostic algorithm or a Codex endpoint.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verification.mesh_structure_fixtures import fixtures, grid
from verification.mesh_structure_contract import LIMITS


def encoded(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,
                      separators=(',',':')).encode('utf8')


def save(path, value):
    with Path(path).open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,ensure_ascii=False,allow_nan=False,indent=2)


def worker(output):
    import bpy
    assert bpy.app.background, 'factory background worker required'
    host_path=ROOT/'human_eye_plugin/blender_host.py'
    spec=importlib.util.spec_from_file_location('m1_baseline_host',host_path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    exec(compile(host_path.read_bytes(),str(host_path),'exec'),module.__dict__)
    host=module.BlenderSceneHost(execution_metadata=True,identity_metadata=True)

    def capture_raw(obj):
        mesh=obj.data
        return dict(vertices=[[float(v) for v in item.co] for item in mesh.vertices],
                    edges=[list(item.vertices) for item in mesh.edges],
                    polygons=[list(item.vertices) for item in mesh.polygons],
                    matrix_world=[[float(v) for v in row] for row in obj.matrix_world],
                    unit_scale=float(bpy.context.scene.unit_settings.scale_length))

    def validate_raw(raw):
        vertices,edges,polygons=raw['vertices'],raw['edges'],raw['polygons']
        counts=dict(vertices=len(vertices),edges=len(edges),polygons=len(polygons),
                    corners=sum(map(len,polygons)))
        assert all(counts[k]<=LIMITS[k] for k in counts)
        assert all(len(v)==3 for v in vertices)
        assert all(len(e)==2 and all(type(i) is int and 0<=i<len(vertices) for i in e) for e in edges)
        assert all(len(p)>=3 and all(type(i) is int and 0<=i<len(vertices) for i in p) for p in polygons)
        return counts

    def state(obj):
        return encoded(dict(raw=capture_raw(obj),selection=[o.name for o in bpy.context.selected_objects],
                            active=getattr(bpy.context.view_layer.objects.active,'name',None),
                            objects=sorted(o.name for o in bpy.context.scene.objects)))

    rows=[]; source_checks=[]
    cases=fixtures()+[grid(n) for n in (8,32,96)]
    for case in cases:
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        for mesh in list(bpy.data.meshes):
            if mesh.users==0:bpy.data.meshes.remove(mesh)
        mesh=bpy.data.meshes.new(case['id']);mesh.from_pydata(case['vertices'],case['edges'],case['polygons'])
        obj=bpy.data.objects.new(case['id'],mesh);bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.context.view_layer.update()
        before=state(obj);actual=capture_raw(obj)
        # Coordinates are simple exactly representable dyadics except the size
        # gradient. Compare gradient coordinates at Blender's binary32 precision.
        import struct
        f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
        wanted_vertices=[[f32(float(x)) for x in v] for v in case['vertices']]
        assert actual['vertices']==wanted_vertices and actual['polygons']==case['polygons'], case['id']
        expected_edges={tuple(sorted(edge)) for edge in case['edges']}
        for polygon in case['polygons']:
            expected_edges.update(tuple(sorted((polygon[i],polygon[(i+1)%len(polygon)]))) for i in range(len(polygon)))
        assert set(map(lambda e:tuple(sorted(e)),actual['edges']))==expected_edges,case['id']
        assert len(actual['edges'])==len(expected_edges), 'ambiguous duplicate edge indices'
        source_checks.append(dict(case=case['id'],original_vertices_and_polygons_exact=True,
                                  original_edge_membership_exact=True,
                                  source_edge_index_table=actual['edges'] if len(actual['edges'])<=32 else None,
                                  counts=validate_raw(actual)))
        for repetition in range(3):
            # Interleave orders, retain first read separately. No fictitious
            # equivalence: legacy emits a richer native/evaluated sidecar.
            for path in (('raw','legacy') if repetition%2==0 else ('legacy','raw')):
                begin=time.perf_counter_ns();spans={};error=None;raw_bytes=None;counts=None
                try:
                    t=time.perf_counter_ns()
                    payload=capture_raw(obj) if path=='raw' else host.capture_readonly_evidence()
                    spans['capture_ns']=time.perf_counter_ns()-t
                    t=time.perf_counter_ns()
                    if path=='raw':counts=validate_raw(payload)
                    spans['validation_ns']=time.perf_counter_ns()-t
                    t=time.perf_counter_ns();raw_bytes=encoded(payload)
                    spans['serialization_ns']=time.perf_counter_ns()-t
                    if path=='raw':assert len(raw_bytes)<=LIMITS['source_bytes']
                except Exception as exc:error=type(exc).__name__+': '+str(exc)
                end=time.perf_counter_ns()
                assert state(obj)==before, 'baseline changed source geometry/selection'
                rows.append(dict(case=case['id'],path=path,repetition=repetition,
                                 first_read=repetition==0,total_ns=end-begin,stages_ns=spans,
                                 output_bytes=None if raw_bytes is None else len(raw_bytes),
                                 error=error,counts=counts,state_unchanged=True))
    save(output,dict(blender_version=bpy.app.version_string,process_id=os.getpid(),
                     host_source_sha256=hashlib.sha256(host_path.read_bytes()).hexdigest(),
                     owned_factory_scene=True,user_gui_accessed=False,sockets_opened=0,
                     geometry_read_checks=source_checks,rows=rows))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--blender',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    started=time.time()
    save(output/'PREREGISTERED.json',dict(created_unix=started,repetitions=3,processes=3,
         cases=[c['id'] for c in fixtures()]+['grid_8','grid_32','grid_96'],
         script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         limits=LIMITS,scope='source_read_validation_serialization_only_no_diagnostic_candidate',
         full_task_timing='pending_M1-04_host_transport_and_render',
         success='raw geometry equals source fixture; no geometry or selection change; all workers exit',
         stopping='any source mismatch or unhandled worker failure stops publication'))
    processes=[];rows=[]
    for index in range(3):
        result_path=output/f'worker_{index}.json'
        command=[str(Path(args.blender).resolve()),'--background','--factory-startup','--disable-autoexec',
                 '--python',str(Path(__file__).resolve()),'--','--worker',str(result_path)]
        start=time.perf_counter_ns()
        with (output/f'worker_{index}.stdout').open('xb') as stdout, (output/f'worker_{index}.stderr').open('xb') as stderr:
            run=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=90,
                               creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        record=dict(index=index,returncode=run.returncode,process_wall_ns=time.perf_counter_ns()-start)
        processes.append(record)
        if run.returncode!=0 or not result_path.is_file():
            save(output/'FAILED.json',record);raise RuntimeError('owned Blender baseline failed')
        data=json.loads(result_path.read_text(encoding='utf8'))
        rows.extend(dict(row,process=index) for row in data['rows'])
        print(json.dumps(dict(worker=index,rows=len(data['rows']),returncode=run.returncode)),flush=True)
    summaries=[]
    for case in sorted({r['case'] for r in rows}):
        for path in ('raw','legacy'):
            selected=[r for r in rows if r['case']==case and r['path']==path]
            good=[r for r in selected if r['error'] is None]
            times=sorted(r['total_ns']/1e6 for r in good)
            summaries.append(dict(case=case,path=path,samples=len(selected),successes=len(good),
                 median_ms=statistics.median(times) if times else None,
                 p95_ms=times[max(0,__import__('math').ceil(.95*len(times))-1)] if times else None,
                 max_output_bytes=max((r['output_bytes'] for r in good),default=None),
                 errors=sorted({r['error'] for r in selected if r['error']})))
    assert all(s['successes']==s['samples'] for s in summaries if s['path']=='raw')
    save(output/'SUMMARY.json',dict(processes=processes,summaries=summaries,
         raw_source_cases=17,raw_reads=153,legacy_attempts=153,
         geometry_unchanged=True,diagnostic_algorithm_executed=False,model_trials=0,
         limits='9 samples per case/path; empirical p95 is an order statistic, not a population confidence bound; process wall covers the entire benchmark, not one task'))


if __name__=='__main__':
    if '--worker' in sys.argv:
        worker(Path(sys.argv[sys.argv.index('--worker')+1]))
    else:main()
