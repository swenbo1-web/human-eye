"""M3-B1 source/scale profiling in owned scenes and real typed host calls.

No model calls or user GUI. Analytic, Blender-bundled and upstream assets are
separate. First process/first call is not a claim of cold OS disk caches.
"""
import argparse,base64,ctypes,hashlib,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verification.m3_asset_cases import cases,build


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,ensure_ascii=True,allow_nan=False,indent=2)


def memory(process=None):
    if os.name!='nt':return dict(working_set_bytes=None,lifetime_peak_bytes=None)
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
          ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
           'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.GetCurrentProcess.restype=ctypes.c_void_p
    kernel.K32GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),wintypes.DWORD]
    info=Counters();info.cb=ctypes.sizeof(info)
    handle=int(process._handle) if process is not None else kernel.GetCurrentProcess()
    if not kernel.K32GetProcessMemoryInfo(handle,ctypes.byref(info),info.cb):raise ctypes.WinError(ctypes.get_last_error())
    return dict(working_set_bytes=info.WorkingSetSize,lifetime_peak_bytes=info.PeakWorkingSetSize,gpu_memory_bytes=None)


def original(obj,scene):
    return dict(vertices=[[float(x) for x in v.co] for v in obj.data.vertices],
       edges=[[int(i) for i in e.vertices] for e in obj.data.edges],
       polygons=[[int(i) for i in p.vertices] for p in obj.data.polygons],
       matrix_world=[[float(x) for x in row] for row in obj.matrix_world],unit_scale=float(scene.unit_settings.scale_length))


def state(bpy):
    return dict(meshes={o.name:original(o,bpy.context.scene) for o in bpy.context.scene.objects if o.type=='MESH'},
                selected=sorted(o.name for o in bpy.context.selected_objects),
                active=getattr(bpy.context.view_layer.objects.active,'name',None),objects=sorted(o.name for o in bpy.context.scene.objects))


def builder(args):
    import bpy
    assert bpy.app.background and args.output.resolve().name.startswith('he-m3-')
    source=args.core_root/'human_eye_plugin/blender_host.py'
    spec=importlib.util.spec_from_file_location('_m3_asset_host',source);module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module;exec(compile(source.read_bytes(),str(source),'exec'),module.__dict__)
    rows=[]
    for case in cases(args.assets):
        bpy.ops.wm.read_factory_settings(use_empty=True);objects=build(bpy,case)
        host=module.BlenderSceneHost(execution_metadata=True,identity_metadata=True);m=host._raw_mesh_module()
        folder=args.output/case['id'];folder.mkdir(exist_ok=False);before=digest(state(bpy));targets=[]
        for index,obj in enumerate(objects):
            truth=original(obj,bpy.context.scene);obj.data.calc_loop_triangles()
            triangles=[[int(i) for i in tri.vertices] for tri in obj.data.loop_triangles]
            triangle_polygons=[int(tri.polygon_index) for tri in obj.data.loop_triangles]
            oid=host.object_id(obj);save(folder/('SOURCE_%d.json'%index),dict(raw=truth,triangles=triangles,triangle_polygons=triangle_polygons,
                 source_kind=case['provenance'],object_name=obj.name,object_id=oid,modifiers=[x.type for x in obj.modifiers]))
            spans=[]
            for repeat in range(3):
                timings={};prepared=None;result=None;reason=None;prepare=m.prepare_raw
                def preparation(*a,**kw):
                    start=time.perf_counter_ns()
                    try:return prepare(*a,**kw)
                    finally:timings['validation_and_source_hash_ns']=time.perf_counter_ns()-start
                m.prepare_raw=preparation;budget=m.WorkBudget();start=time.perf_counter_ns()
                try:
                    prepared=m.capture_raw(host,oid,budget=budget);timings['capture_with_validation_ns']=time.perf_counter_ns()-start
                    assert prepared['raw']==truth
                    start=time.perf_counter_ns();result=m.analyze_prepared(prepared,task_id='b1-direct',categories=m.SUPPORTED,budget=budget,region_summaries=True)
                    timings['scan_ns']=time.perf_counter_ns()-start
                    start=time.perf_counter_ns();wire=encoded(result);timings['serialization_ns']=time.perf_counter_ns()-start;timings['report_bytes']=len(wire)
                    if repeat==0:save(folder/('DIRECT_REPORT_%d.json'%index),result)
                except Exception as exc:reason=type(exc).__name__+':'+str(exc)[:200]
                finally:m.prepare_raw=prepare
                if 'capture_with_validation_ns' in timings:timings['capture_without_validation_ns']=timings['capture_with_validation_ns']-timings.get('validation_and_source_hash_ns',0)
                assert digest(state(bpy))==before,'read-only direct diagnostic changed geometry/selection'
                spans.append(dict(repeat=repeat,timings=timings,error=reason,work_used=budget.used,
                                  status=result.get('status') if result else None,
                                  checks={k:v['state'] for k,v in result['report']['checks'].items()} if result else None))
            raw=truth;delta=0.
            for vertex in obj.data.vertices:
                native=obj.matrix_world@vertex.co
                ideal=[sum(raw['matrix_world'][r][c]*vertex.co[c] for c in range(3))+raw['matrix_world'][r][3] for r in range(3)]
                delta=max(delta,max(abs(float(native[r])-ideal[r])*raw['unit_scale'] for r in range(3)))
            targets.append(dict(index=index,name=obj.name,object_id=oid,vertices=len(raw['vertices']),polygons=len(raw['polygons']),
                triangles=len(triangles),parented=obj.parent is not None,modifiers=[x.type for x in obj.modifiers],
                max_native_vs_binary64_forward_delta_m=delta,direct=spans))
        scene=folder/'fixture.blend';assert not scene.exists();bpy.ops.wm.save_as_mainfile(filepath=str(scene),check_existing=True)
        assert scene.is_file() and digest(state(bpy))==before
        row=dict(case=case,targets=targets,scene=str(scene),scene_sha256=hashlib.sha256(scene.read_bytes()).hexdigest(),source_unchanged=True,
                 builder_process_memory=memory(),loaded_host_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        save(folder/'CASE.json',row);rows.append(row);print(json.dumps(dict(case=case['id'],targets=len(targets),vertices=sum(t['vertices'] for t in targets))),flush=True)
    save(args.output/'ASSETS.json',dict(rows=rows,blender_version=bpy.app.version_string,user_GUI_accessed=False,model_calls=0))


def controller(args):
    module_spec=importlib.util.spec_from_file_location('_m3_profile_installed',args.entry)
    module=importlib.util.module_from_spec(module_spec);sys.modules[module_spec.name]=module;module_spec.loader.exec_module(module)
    proof=module.validate_binding(expected_python=sys.executable);sys.path.insert(0,proof['module_root']);identity,_=module.verify_imported_runtime(proof)
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    from human_eye_plugin import structure_task_control as control
    asset_rows=json.loads((args.output/'ASSETS.json').read_text(encoding='utf8'))['rows'];rows=[]
    pins={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind')}
    pins.update(protocol_version='2025-03-26',mode='live')
    for case in asset_rows:
        assert args.run_id.isascii() and args.run_id.isalnum() and 1<=len(args.run_id)<=16
        folder=Path(case['scene']).parent/('rpc-'+args.run_id);folder.mkdir(exist_ok=False);config=folder/'CONFIG.json'
        scene=Path(case['scene']).resolve()
        assert scene.name=='fixture.blend' and scene.parent.parent==args.output.resolve()
        assert hashlib.sha256(scene.read_bytes()).hexdigest()==case['scene_sha256']
        save(config,dict(schema_version='1.0',enabled=True,project_root=proof['module_root'],expected_identity=pins,
             state_file='STATE.json',audit_file='AUDIT.jsonl',structure_task_file='TASK.json',structure_task_control_file='CONTROL.json',
             structure_region_mode=args.region_mode,structure_patch_mode='nonplanar_dense_v1',quad_size=384,max_sessions=4))
        started=time.perf_counter_ns();host=BlenderProcessHost(args.blender,case['scene']);startup=time.perf_counter_ns()-started
        try:
            service=LiveSpatialService(config,host=host);server=LiveSpatialMCPServer(service)
            greeting=server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=1,method='initialize',params=dict(protocolVersion='2025-03-26',capabilities={})))
            save(folder/'HANDSHAKE.json',greeting)
            for target in case['targets'][:16]:
                registration=control.begin(config,'b1:'+str(target['index']),target['object_id']);ref=registration['task_ref'];calls=[];metadata=None
                for repeat in range(3):
                    arguments=dict(session_id='b1',focal_id=target['object_id'],include_image=False,response_detail='full',
                        query=dict(mode='mesh_structure',operation='diagnose',request_id='diagnose'+str(repeat),task_ref=ref))
                    begin=time.perf_counter_ns();reply=server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=100+repeat,method='tools/call',params=dict(name='human_eye_scene_observe',arguments=arguments)))
                    projected=time.perf_counter_ns();body=encoded(reply);ready=time.perf_counter_ns()
                    ns=ready-begin
                    texts=[x['text'] for x in reply.get('result',{}).get('content',[]) if x.get('type')=='text']
                    metadata=json.loads(texts[0]) if texts else None
                    save(folder/('MCP_%d_%d.json'%(target['index'],repeat)),reply)
                    calls.append(dict(repeat=repeat,total_rpc_and_mcp_projection_ns=ns,outer_serialization_ns=ready-projected,
                        elapsed_since_process_start_ns=ready-started,wire_bytes=len(body),isError=reply.get('result',{}).get('isError'),
                        status=metadata.get('status') if metadata else None,reason=metadata.get('error',metadata.get('reason')) if metadata else reply.get('error')))
                    if metadata is None or 'diagnostic' not in metadata:break
                image_status='no_source_patch';image_count=0;view_ns=None
                if metadata and metadata.get('patch_refs'):
                    selected=next((v for v in metadata['patch_refs'] if v['category']=='boundary_edges'),metadata['patch_refs'][0])
                    args_image=dict(session_id='b1',focal_id=target['object_id'],include_image=True,response_detail='full',query=dict(mode='mesh_structure',
                        operation='patch',request_id='patch1',task_ref=ref,patch_ref=selected['patch_ref']))
                    begin=time.perf_counter_ns();reply=server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=200,method='tools/call',params=dict(name='human_eye_scene_observe',arguments=args_image)))
                    view_ns=time.perf_counter_ns()-begin;save(folder/('IMAGE_WIRE_%d.json'%target['index']),reply)
                    for content in reply.get('result',{}).get('content',[]):
                        if content.get('type')=='image':
                            (folder/('IMAGE_%d_%d.png'%(target['index'],image_count))).write_bytes(base64.b64decode(content['data'],validate=True));image_count+=1
                        elif content.get('type')=='text':
                            picture=json.loads(content['text']);image_status=picture.get('image_status',picture.get('error',picture.get('status')))
                source_after_verified=None;close_error=None
                if metadata and metadata.get('diagnostic'):
                    initial_source=metadata['diagnostic']['report']['source']['raw_sha256']
                    checking=dict(session_id='b1',focal_id=target['object_id'],include_image=False,response_detail='full',
                        query=dict(mode='mesh_structure',operation='diagnose',request_id='verify_after',task_ref=ref))
                    after=server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=300,method='tools/call',params=dict(name='human_eye_scene_observe',arguments=checking)))
                    save(folder/('AFTER_%d.json'%target['index']),after)
                    texts=[x['text'] for x in after.get('result',{}).get('content',[]) if x.get('type')=='text']
                    value=json.loads(texts[0]) if texts else {}
                    source=value.get('diagnostic',{}).get('report',{}).get('source',{})
                    if source:source_after_verified=source['raw_sha256']==initial_source
                    assert source_after_verified is not False,'registered observation changed raw geometry'
                try:control.close(config,ref)
                except Exception as exc:close_error=type(exc).__name__+':'+str(exc)[:160]
                row=dict(case=case['case']['id'],provenance=case['case']['provenance'],target=target['name'],target_index=target['index'],
                    vertices=target['vertices'],triangles=target['triangles'],startup_ns=startup,calls=calls,
                    view_task_total_ns=view_ns,image_status=image_status,native_png_count=image_count,
                    child_memory=memory(host._process),controller_memory=memory(),asset_meshes=len(case['targets']),
                    omitted_meshes=max(0,len(case['targets'])-16),fixture_supplied_target_ids=True)
                row.update(source_after_rpc_verified=source_after_verified,close_error=close_error)
                rows.append(row);print(json.dumps(dict(case=row['case'],target=row['target'],status=calls[0]['status'],images=image_count,image_status=image_status)),flush=True)
                if close_error:
                    row['unexamined_remaining_targets']=len(case['targets'])-target['index']-1
                    break
        finally:host.close()
        assert host._process.poll()==0 and hashlib.sha256(Path(case['scene']).read_bytes()).hexdigest()==case['scene_sha256']
        save(folder/'LIFECYCLE.json',dict(child_exit_code=host._process.poll(),source_file_unchanged=True))
    save(args.output/('PROFILE-'+args.run_id+'.json'),dict(rows=rows,runtime_source=identity['source_sha256'],actual_Codex_consumption=False,
        source_only_vs_registered_task_paths_not_equivalent=True,formal_model_calls=0,user_GUI_accessed=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--builder',action='store_true');parser.add_argument('--controller',action='store_true')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--assets',type=Path);parser.add_argument('--core-root',type=Path)
    parser.add_argument('--entry',type=Path);parser.add_argument('--blender',type=Path)
    parser.add_argument('--run-id',default='r1');parser.add_argument('--region-mode',choices=('legacy','summary_v1'),default='summary_v1')
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];args=parser.parse_args(argv)
    builder(args) if args.builder else controller(args)
