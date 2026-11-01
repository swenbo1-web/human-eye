"""Owned native capability preflight; deliberately not an HE-versus-native trial."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def save(path,value):
    with Path(path).open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,allow_nan=False)


def verify_worker_asset(asset):
    if set(asset)!={'id','objects','task','asset_task_sha256'}:raise ValueError('private_oracle_in_worker_input')
    if type(asset['id']) is not str or re.fullmatch('[a-z0-9_]{1,64}',asset['id']) is None:
        raise ValueError('asset_id')
    raw=json.dumps(dict(objects=asset['objects'],task=asset['task']),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if hashlib.sha256(raw).hexdigest()!=asset['asset_task_sha256']:raise ValueError('asset_task_changed')


def complete_preflight(assets,scored,processes,rounds):
    expected={(repeat,case['id']) for repeat in range(rounds) for case in assets}
    actual=[(row['round'],row['case']) for row in scored]
    return (rounds>=3 and len(processes)==rounds and len(actual)==len(expected)
        and set(actual)==expected and all(r['quality_passed'] is True for r in scored)
        and all(p['exit_code']==0 and p['reaped'] and not p['timed_out'] for p in processes))


def worker(input_path,folder):
    import bpy
    from verification.native_engineering_baseline import observe
    if not bpy.app.background:raise ValueError('owned_background_required')
    spec=json.loads(input_path.read_text());baseline=ROOT/'verification/native_engineering_baseline.py'
    if hashlib.sha256(baseline.read_bytes()).hexdigest()!=spec['baseline_sha256']:raise ValueError('baseline_source_changed')
    def snapshot(scene):
        return dict(objects=[dict(name=obj.name,color=list(obj.color),selected=obj.select_get(),
            hide_render=obj.hide_render,hide_viewport=obj.hide_viewport,
            matrix=[list(row) for row in obj.matrix_world],vertices=[list(v.co) for v in obj.data.vertices],
            edges=[list(e.vertices) for e in obj.data.edges],faces=[list(f.vertices) for f in obj.data.polygons])
            for obj in sorted(scene.objects,key=lambda obj:obj.name) if obj.type=='MESH'],
            scenes=sorted(s.name for s in bpy.data.scenes),cameras=sorted(c.name for c in bpy.data.cameras),
            scene_camera=None if scene.camera is None else scene.camera.name,
            resolution=[scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage],
            engine=scene.render.engine,view=scene.view_settings.view_transform,
            active=None if bpy.context.view_layer.objects.active is None else bpy.context.view_layer.objects.active.name)
    rows=[]
    for asset in spec['assets']:
        verify_worker_asset(asset)
        for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
        for mesh in list(bpy.data.meshes):
            if not mesh.users:bpy.data.meshes.remove(mesh)
        scene=bpy.context.scene;scene.camera=None;prepared=time.perf_counter_ns()
        for value in asset['objects']:
            mesh=bpy.data.meshes.new(value['object_id']);mesh.from_pydata(value['world_vertices'],value.get('edges',[]),value['faces']);mesh.update()
            obj=bpy.data.objects.new(value['object_id'],mesh);scene.collection.objects.link(obj)
            obj.color=(.04,.15,.8,1.) if obj.name=='target' else (.25,.25,.25,1.)
        bpy.context.view_layer.update();preparation_ms=(time.perf_counter_ns()-prepared)/1e6
        target=scene.objects[asset['task']['object_id']];before=snapshot(scene)
        output=folder/asset['id'];output.mkdir();begin=time.perf_counter_ns()
        try:
            value=observe(scene,target,asset['task'],output)
            error=None
        except Exception as exc:value=None;error=type(exc).__name__+': '+str(exc)
        elapsed=(time.perf_counter_ns()-begin)/1e6
        after=snapshot(scene);restored=after==before
        fingerprint=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        rows.append(dict(case=asset['id'],value=value,error=error,preservation_passed=restored,
                         actual_mesh_sha256=fingerprint(before['objects']),state_before_sha256=fingerprint(before),
                         state_after_sha256=fingerprint(after),input_asset_sha256=asset['asset_task_sha256'],
                         call_wall_ms=elapsed,scene_preparation_ms=preparation_ms))
        save(output/'RESULT.json',rows[-1])
    loaded=[name for name in sys.modules if name.startswith('human_eye_plugin')]
    if loaded:raise ValueError('HE_modules_loaded_in_native_worker')
    save(folder/'WORKER_RESULT.json',dict(pid=__import__('os').getpid(),rows=rows,HE_modules_loaded=loaded,
        baseline_sha256=spec['baseline_sha256'],blender_version=bpy.app.version_string))


def pixel_check(case,value):
    from PIL import Image
    from verification.nonplanar_patch_fixtures import oracle_samples
    images=value.get('images',[])
    for frame in images:
        path=Path(frame['path']);raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=frame['sha256']:raise ValueError('image_hash')
        with Image.open(path) as image:
            if image.size!=(384,384):raise ValueError('image_dimensions')
        actual_camera(frame)
    truth=case['pixel_truth']
    if truth is None:return dict(status='not_scored',readable_pairs=None)
    if not images:return dict(status='scored',readable_pairs=0)
    frame=images[-1];matrix=frame['camera_matrix'];span=frame['actual_ortho_scale']
    direction=[matrix[k][2] for k in range(3)];length=math.hypot(*direction)
    # The analytic aperture oracle supports front/back projections only. Do not
    # turn an unregistered side view into either a visual pass or a failure.
    if length<=0 or abs(direction[0])/length<1-1e-8:return dict(status='unsupported_oracle_view',readable_pairs=None)
    with Image.open(frame['path']) as picture:picture=picture.convert('RGBA')
    center=[matrix[k][3] for k in range(3)];axes=[[matrix[k][column] for k in range(3)] for column in (0,1)]
    def at(point):
        xy=[sum((point[k]-center[k])*axis[k] for k in range(3))/span for axis in axes]
        x,y=round((xy[0]+.5)*384-.5),round((.5-xy[1])*384-.5)
        return picture.getpixel((x,y)) if 0<=x<384 and 0<=y<384 else None
    def blue(pixel):return pixel is not None and pixel[3]>128 and pixel[2]>pixel[0]+40 and pixel[2]>pixel[1]+20
    rows=[]
    for sample in oracle_samples(truth,3*span/384):
        a,b=map(at,sample['pair'])
        readable=blue(a) and not blue(b) and b is not None and sum(abs(x-y) for x,y in zip(a[:3],b[:3]))>=80
        rows.append(dict(analytic_visible=sample['visible'],readable=bool(readable)))
    return dict(status='scored',readable_pairs=sum(r['readable'] for r in rows),
        false_visible=sum(r['readable'] and not r['analytic_visible'] for r in rows),samples=rows)


def actual_camera(frame):
    """Check actual RNA for every image, independently of requested framing."""
    matrix=frame['camera_matrix'];span=frame['actual_ortho_scale']
    if (type(span) not in (float,int) or not math.isfinite(span) or span<=0
        or type(matrix) is not list or len(matrix)!=4 or any(type(row) is not list or len(row)!=4 for row in matrix)
        or any(type(v) not in (float,int) or not math.isfinite(v) for row in matrix for v in row)
        or matrix[3]!=[0,0,0,1]):raise ValueError('actual_camera_metadata')
    for index,key in enumerate(('right','up','direction')):
        if any(abs(matrix[k][index]-frame[key][k])>2e-6 for k in range(3)):raise ValueError('actual_camera_basis_disagrees')
    if abs(span-frame['span'])>2e-6*max(span,frame['span']):raise ValueError('actual_camera_scale_disagrees')
    if any(abs(matrix[k][3]-frame['location'][k])>2e-6*max(1,abs(matrix[k][3])) for k in range(3)):
        raise ValueError('actual_camera_position_disagrees')
    return True


def parent(blender,folder,rounds):
    from verification.engineering_baseline_cases import cases,validate_facts,digest
    if rounds<3:raise ValueError('three_fresh_processes_required')
    folder=folder.resolve();folder.mkdir(parents=True,exist_ok=False)
    assets=cases();baseline=ROOT/'verification/native_engineering_baseline.py'
    inputs=dict(baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
        assets=[{k:case[k] for k in ('id','objects','task','asset_task_sha256')} for case in assets])
    for asset in inputs['assets']:verify_worker_asset(asset)
    save(folder/'REGISTERED_INPUT.json',inputs);save(folder/'PRIVATE_ORACLES.json',assets)
    records=[];scored=[]
    for repeat in range(rounds):
        target=folder/('process_'+str(repeat));target.mkdir()
        out=(target/'stdout').open('xb');err=(target/'stderr').open('xb');begin=time.perf_counter_ns()
        process=subprocess.Popen([str(blender),'--factory-startup','--background','--disable-autoexec',
            '--python-exit-code','3','--python',str(Path(__file__).resolve()),'--','--worker',
            str(folder/'REGISTERED_INPUT.json'),str(target)],stdout=out,stderr=err,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        expired=False
        try:code=process.wait(timeout=180)
        except subprocess.TimeoutExpired:expired=True;process.kill();process.wait(timeout=10);code=process.returncode
        out.close();err.close()
        record=dict(round=repeat,pid=process.pid,exit_code=code,timed_out=expired,reaped=process.poll() is not None,
            process_wall_ms=(time.perf_counter_ns()-begin)/1e6)
        records.append(record);save(target/'PROCESS.json',record)
        if code or expired:continue
        data=json.loads((target/'WORKER_RESULT.json').read_text())
        for case,row in zip(assets,data['rows']):
            quality_error=None;pixels=None
            try:
                if row['case']!=case['id'] or not row['preservation_passed']:raise ValueError('scene_or_order_changed')
                validate_facts(case,row['value']);pixels=pixel_check(case,row['value'])
                if case['id'] in ('nonplanar_clear','center_blocked','dense1808'):
                    if pixels['status']!='scored' or pixels['readable_pairs']<8 or pixels['false_visible']:
                        raise ValueError('local_pixel_quality')
                if case['id']=='feature_blocked' and row['value']['images']:raise ValueError('blocked_feature_claimed_useful')
            except Exception as exc:quality_error=type(exc).__name__+': '+str(exc)
            metrics=None
            if row['value'] is not None:
                metrics=dict(facts_json_utf8_bytes=len(json.dumps(row['value']['facts'],separators=(',',':')).encode()),
                    native_value_json_utf8_bytes=len(json.dumps(row['value'],separators=(',',':')).encode()),
                    png_bytes=sum(frame['bytes'] for frame in row['value']['images']))
            scored.append(dict(round=repeat,**row,pixels=pixels,metrics=metrics,quality_error=quality_error,quality_passed=quality_error is None))
    passed=complete_preflight(assets,scored,records,rounds)
    result=dict(stage='M2-A0 native baseline feasibility only',preflight_passed=passed,
        value_gate_passed=False,model_trials=0,release_gate_changed=False,worker_input_sha256=digest(inputs),
        rows=scored,processes=records,expected_task_denominator=rounds*len(assets),
        cost_scope='native function and file PNG output only; process wall includes setup and shutdown; no stdio/TCP/lifecycle comparison')
    save(folder/'RESULT.json',result)
    print(json.dumps(dict(passed=passed,tasks=len(scored),expected=rounds*len(assets),
        failures=[dict(case=r['case'],round=r['round'],error=r['quality_error'],host_error=r['error']) for r in scored if not r['quality_passed']])))
    return passed


if __name__=='__main__':
    if '--worker' in sys.argv:
        index=sys.argv.index('--worker');worker(Path(sys.argv[index+1]),Path(sys.argv[index+2]))
    else:
        parser=argparse.ArgumentParser();parser.add_argument('--blender',required=True,type=Path)
        parser.add_argument('--output',required=True,type=Path);parser.add_argument('--rounds',default=3,type=int)
        args=parser.parse_args();raise SystemExit(0 if parent(args.blender,args.output,args.rounds) else 1)
