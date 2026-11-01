"""Owned counterfactual renders for pixel QA, separate from product budgets.

Run inside factory Blender. Recreates only this harness's hashed fixtures;
historical frames supply camera geometry, never an action grant. QA edits are
explicit fixture construction in a separate process, not observation setters.
"""
import argparse,base64,hashlib,importlib.util,json,sys,time
from pathlib import Path
sys.dont_write_bytecode=True


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2)


def main(args):
    import bpy
    assert bpy.app.background and args.output.resolve().is_relative_to(Path(__file__).resolve().parents[1]/'verification/fixes/20261102_m3_surface_views')
    args.output.mkdir(exist_ok=False)
    source=args.core_root/'human_eye_plugin/blender_host.py';spec=importlib.util.spec_from_file_location('_reference_pixel_qa_host',source)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;exec(compile(source.read_bytes(),str(source),'exec'),module.__dict__)
    cases=json.loads((args.cases/'CASES.json').read_text(encoding='utf8'))['rows'];rows=[]
    for case in cases:
        name=case['case']['name']
        if name not in ('clear','curved','center_mask','millimetre_units'):continue
        scene=Path(case['scene']).resolve();assert scene.parent.parent==args.cases.resolve()
        assert hashlib.sha256(scene.read_bytes()).hexdigest()==case['scene_sha256']
        reference_file=scene.parent/'REFERENCE.json';assert hashlib.sha256(reference_file.read_bytes()).hexdigest()==case['reference_sha256']
        previous_path=args.cases/('rpc-'+args.source_run)/name/'PRIVATE_VIEW_0.json'
        previous=json.loads(previous_path.read_text(encoding='utf8'));assert len(previous['frames'])==2
        bpy.ops.wm.open_mainfile(filepath=str(scene),load_ui=False,use_scripts=False)
        host=module.BlenderSceneHost(execution_metadata=True,identity_metadata=True)
        renderer=host._readonly_native_module();store=host._readonly_observation_store(create=True)
        obj=next(o for o in bpy.context.scene.objects if host.object_id(o)==case['object_id'])
        current=host._raw_mesh_module().capture_raw(host,case['object_id']);assert current['raw']==case['current_raw']
        native=host.capture_readonly_evidence()['native_scene'];assert native==previous['evidence']['native_scene']
        folder=args.output/name;folder.mkdir(exist_ok=False);captures=[];fixture_writes=0
        for pose in ('current','reference'):
            if pose=='reference':
                intended=json.loads(reference_file.read_text(encoding='utf8'))['raw']
                assert intended['edges']==current['raw']['edges'] and intended['polygons']==current['raw']['polygons']
                for vertex,value in zip(obj.data.vertices,intended['vertices']):vertex.co=value;fixture_writes+=1
                obj.data.update();bpy.context.view_layer.update()
            evidence=host.capture_readonly_evidence()
            for row in previous['frames']:
                public=row['frame'];proof=row['frustum'];scale=proof['unit_scale_m'];matrix=proof['camera_matrix_host_units']
                frame=dict(center_bu=[x/scale for x in public['center_world_m']],direction=public['eye_direction_world'],
                    right=public['right_world'],up=public['up_world'],camera_location_bu=[matrix[k][3] for k in range(3)],
                    ortho_scale_bu=proof['ortho_scale_bu'],clip_start_bu=proof['clip_start_bu'],clip_end_bu=proof['clip_end_bu'])
                audits=[];frustums=[];started=time.perf_counter_ns()
                image=host._readonly_render_view(renderer,store,'SCENE',frame=frame,coverage=public['screen_coverage'],
                    expected_evidence=evidence,audit_sink=audits,frustum_sink=frustums)
                assert len(audits)==len(frustums)==1 and audits[0]['restored']
                blob=base64.b64decode(image['image_base64'],validate=True)
                (folder/(pose+'_'+row['kind']+'.png')).write_bytes(blob)
                captures.append(dict(pose=pose,kind=row['kind'],audit=audits[0],frustum=frustums[0],elapsed_ns=time.perf_counter_ns()-started,
                    png_sha256=hashlib.sha256(blob).hexdigest(),original_mcp_png_sha256=row['png_sha256']))
        assert hashlib.sha256(scene.read_bytes()).hexdigest()==case['scene_sha256']
        result=dict(case=name,captures=captures,fixture_vertex_assignments=fixture_writes,source_file_unchanged=True,
            original_private_view_sha256=hashlib.sha256(previous_path.read_bytes()).hexdigest(),
            role='separate_counterfactual_QA_not_product_task_or_restored_execution',formal_model_calls=0)
        save(folder/'RESULT.json',result);rows.append(result);print(json.dumps(dict(case=name,qa_renders=len(captures))),flush=True)
    save(args.output/'RESULT.json',dict(rows=rows,loaded_host_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),user_GUI_accessed=False))


def analyze(args):
    import numpy as np
    from PIL import Image
    rows=[]
    for case in ('clear','curved','center_mask','millimetre_units'):
        folder=args.output/case;stats={};match=True
        for index,kind in enumerate(('overview','detail')):
            current=np.array(Image.open(folder/('current_'+kind+'.png')).convert('RGB'),dtype=np.int16)
            reference=np.array(Image.open(folder/('reference_'+kind+'.png')).convert('RGB'),dtype=np.int16)
            old=args.cases/('rpc-'+args.source_run)/case/('picture-1-'+str(index)+'.png')
            previous=np.array(Image.open(old).convert('RGB'),dtype=np.int16)
            equal=bool(np.array_equal(current,previous));match=match and equal
            difference=np.max(np.abs(current-reference),axis=2)
            stats[kind]=dict(original_current_pixels_equal=equal,max_difference=int(difference.max()),
                changed={str(t):int(np.sum(difference>=t)) for t in (1,3,8,16)},
                RMSE=float(np.sqrt(np.mean((current.astype(float)-reference)**2))))
        ratio=stats['detail']['changed']['3']/stats['overview']['changed']['3'] if stats['overview']['changed']['3'] else None
        row=dict(case=case,stats=stats,original_current_pixels_equal=match,detail_changed_ge3_ratio=ratio,
            pixel_gate=bool(match and ratio is not None and ratio>=4));rows.append(row)
    result=dict(rows=rows,all_cases_completed=True,all_pixel_gates_passed=all(r['pixel_gate'] for r in rows),formal_model_calls=0)
    save(args.output/args.metrics_file,result)
    print(json.dumps(dict(cases=len(rows),passed=result['all_pixel_gates_passed'])))
    if not result['all_pixel_gates_passed']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--core-root',type=Path);p.add_argument('--cases',type=Path,required=True)
    p.add_argument('--source-run',default='r3');p.add_argument('--analyze',action='store_true');p.add_argument('--metrics-file',default='PIXEL_METRICS.json')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:])
    if args.analyze:analyze(args)
    elif args.core_root is None:p.error('--core-root is required for Blender renders')
    else:main(args)
