"""Finite M1-02 candidate gate in new factory Blender processes only.

Quality/fixture preparation and tracemalloc are outside timed samples. All
timing failures are retained. This is not an installed Codex/model trial.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,os,statistics,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verification.mesh_structure_fixtures import fixtures,grid
from verification.mesh_structure_contract import validate_report,score

def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
def save(path,value):
    with Path(path).open('x',encoding='utf8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)

def worker(output):
    import bpy,tracemalloc
    assert bpy.app.background
    source=ROOT/'human_eye_plugin/blender_host.py'
    spec=importlib.util.spec_from_file_location('m1_candidate_host',source)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
    exec(compile(source.read_bytes(),str(source),'exec'),module.__dict__)
    host=module.BlenderSceneHost(execution_metadata=True,identity_metadata=True)
    def raw(obj):
        mesh=obj.data
        return dict(vertices=[[float(v) for v in x.co] for x in mesh.vertices],
            edges=[list(x.vertices) for x in mesh.edges],polygons=[list(x.vertices) for x in mesh.polygons],
            matrix_world=[[float(v) for v in row] for row in obj.matrix_world],
            unit_scale=float(bpy.context.scene.unit_settings.scale_length))
    def reference(obj):
        value=raw(obj);v,e,p=value['vertices'],value['edges'],value['polygons']
        assert len(v)<=16384 and len(e)<=32768 and len(p)<=16384 and sum(map(len,p))<=65536
        assert all(len(x)==3 for x in v)
        assert all(len(x)==2 and all(type(i) is int and 0<=i<len(v) for i in x) for x in e)
        assert all(len(x)>=3 and all(type(i) is int and 0<=i<len(v) for i in x) for x in p)
        return encode(value)
    rows=[];quality=[];memory=[]
    for case in fixtures()+[grid(n) for n in (8,32,96)]:
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        for mesh in list(bpy.data.meshes):
            if mesh.users==0:bpy.data.meshes.remove(mesh)
        mesh=bpy.data.meshes.new(case['id']);mesh.from_pydata(case['vertices'],case['edges'],case['polygons'])
        obj=bpy.data.objects.new(case['id'],mesh);bpy.context.scene.collection.objects.link(obj)
        obj.select_set(True);bpy.context.view_layer.objects.active=obj;bpy.context.view_layer.update()
        before=encode(raw(obj));selection=[o.name for o in bpy.context.selected_objects]
        oid=host.object_id(obj);first=None
        for repetition in range(10):
            for path in (('reference','candidate') if repetition%2==0 else ('candidate','reference')):
                begin=time.perf_counter_ns();error=None;result=None;output_bytes=None
                try:
                    if path=='reference':output_bytes=len(reference(obj))
                    else:
                        result=host.observe_mesh_structure('test-'+str(repetition),oid,
                            ['boundary_edges','loose_edges','isolated_vertices'],time.perf_counter_ns()+30_000_000_000)
                        output_bytes=len(encode(result))
                except Exception as exc:error=type(exc).__name__+': '+str(exc)
                elapsed=time.perf_counter_ns()-begin
                assert encode(raw(obj))==before and [o.name for o in bpy.context.selected_objects]==selection
                if path=='candidate' and repetition==0:first=result
                rows.append(dict(case=case['id'],path=path,repetition=repetition,total_ns=elapsed,
                    error=error,output_bytes=output_bytes,status=None if result is None else result['status'],
                    work_units=None if result is None else result['accounting']['work_units']))
        if first is not None:
            validate_report(first['report'])
            expected={c:v for c,v in case.get('expected',{}).items() if c in ('boundary_edges','loose_edges','isolated_vertices')}
            metrics=score(expected,first['report']['checks']) if expected else None
            for patch in first['patches']:
                category=patch['category'];ordinal=patch['cluster_ordinal']
                if category=='isolated_vertices':continue
                actual=[list(mesh.edges[i].vertices) for i in patch['source_indices']]
                assert actual in first['report']['checks'][category]['regions']
            quality.append(dict(case=case['id'],metrics=metrics,source_indices_verified=True,
                                geometry_unchanged=True,report=first))
        tracemalloc.start()
        try:
            host.observe_mesh_structure('memory',oid,['boundary_edges','loose_edges','isolated_vertices'],
                                        time.perf_counter_ns()+30_000_000_000)
            current,peak=tracemalloc.get_traced_memory();memory.append(dict(case=case['id'],python_peak_bytes=peak))
        except Exception as exc:memory.append(dict(case=case['id'],error=type(exc).__name__+': '+str(exc)))
        finally:tracemalloc.stop()
    save(output,dict(blender=bpy.app.version_string,pid=os.getpid(),owned_factory=True,rows=rows,quality=quality,memory=memory))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--blender',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    gate_path=ROOT/'verification/fixtures/mesh_structure_acceptance_v1.json'
    gates=json.loads(gate_path.read_text(encoding='utf8'))
    save(output/'REGISTRATION.json',dict(gates_sha256=hashlib.sha256(gate_path.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (ROOT/'human_eye_plugin/blender_host.py',ROOT/'human_eye_plugin/mesh_structure.py')},
        samples='3 workers x 10 interleaved pairs; first and warm separate',algorithm_optimized_after_registration=False))
    all_rows=[];all_quality=[];all_memory=[];processes=[]
    for i in range(3):
        dest=output/f'worker_{i}.json'
        command=[args.blender,'--background','--factory-startup','--disable-autoexec','--python',str(Path(__file__).resolve()),'--','--worker',str(dest)]
        with (output/f'worker_{i}.stdout').open('xb') as out,(output/f'worker_{i}.stderr').open('xb') as err:
            run=subprocess.run(command,stdout=out,stderr=err,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        processes.append(dict(index=i,returncode=run.returncode))
        if run.returncode or not dest.exists():save(output/'FAILED.json',processes);raise RuntimeError('worker failed')
        data=json.loads(dest.read_text(encoding='utf8'))
        all_rows.extend(dict(r,worker=i) for r in data['rows']);all_quality.extend(data['quality']);all_memory.extend(data['memory'])
        print(json.dumps(dict(worker=i,rows=len(data['rows']))),flush=True)
    limits={r['case']:r['candidate_pipeline_p95_limit_ms'] for r in gates['numerical_gates']}
    rows=[]
    for case in limits:
        for cold in (True,False):
            selected=[r for r in all_rows if r['case']==case and r['path']=='candidate' and (r['repetition']==0)==cold]
            good=[r for r in selected if r['error'] is None and r['status']=='observed']
            times=sorted(r['total_ns']/1e6 for r in good)
            p95=times[math.ceil(.95*len(times))-1] if times else None
            rows.append(dict(case=case,first=cold,samples=len(selected),successes=len(good),
                median_ms=statistics.median(times) if times else None,p95_ms=p95,limit_ms=limits[case],
                passed=len(good)==len(selected) and p95<=limits[case],
                errors=sorted({r['error'] for r in selected if r['error']})))
    quality_ok=all(q['metrics'] is None or (q['metrics']['fp']==q['metrics']['fn']==0 and q['metrics']['answer_coverage']==1.) for q in all_quality)
    memory_ok=all('error' not in r and r['python_peak_bytes']<=gates['memory']['python_traced_temporary_peak_limit_bytes'] for r in all_memory)
    save(output/'RESULT.json',dict(processes=processes,quality_passed=quality_ok,memory_passed=memory_ok,
         max_python_peak_bytes=max((r.get('python_peak_bytes',0) for r in all_memory),default=0),
         cost_passed=all(r['passed'] for r in rows),cost_rows=rows,
         candidate_calls=510,raw_reference_calls=510,actual_model_trials=0,
         formal_codex_entry=False,quality_cases_with_oracles=11))
    print(json.dumps(dict(quality=quality_ok,memory=memory_ok,cost=all(r['passed'] for r in rows))))

if __name__=='__main__':
    if '--worker' in sys.argv:worker(Path(sys.argv[sys.argv.index('--worker')+1]))
    else:main()
