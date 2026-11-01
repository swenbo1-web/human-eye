"""Owned read-only TCP endpoint for common native/HE transport experiments."""
import ast,base64,contextlib,hashlib,io,json,os,re,socket,sys,time,types,uuid
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def main(folder):
    import bpy
    if not bpy.app.background:raise ValueError('owned_background_required')
    asset=json.loads((folder/'ASSET.json').read_text());setup=json.loads((folder/'SERVER_SPEC.json').read_text())
    if 'qualification_registration' in setup:
        sys.path.append(str(ROOT))
        from verification.engineering_qualification import admit,digest,ASSETS
        admit(setup)
        if (set(asset)!={'id','objects','task','asset_task_sha256'} or asset['id']!=setup['case_id']
                or asset['asset_task_sha256']!=ASSETS[asset['id']]
                or digest(dict(objects=asset['objects'],task=asset['task']))!=asset['asset_task_sha256']):
            raise ValueError('qualification_host_asset_changed')
    site=Path(setup['site']);sys.path[:0]=[str(site),str(ROOT)]
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(site/'human_eye_plugin')];sys.modules['human_eye_plugin']=package
    from human_eye_plugin.blender_host import BlenderSceneHost
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost,RPC_PREFIX,_STRUCTURE_COMMANDS
    from human_eye_plugin.forward_deadline import counter_descriptor
    from verification.native_engineering_baseline import observe,topology
    for name,expected in setup['helpers'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=expected:raise ValueError('helper_changed')
    for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
    scene=bpy.context.scene
    for value in asset['objects']:
        mesh=bpy.data.meshes.new(value['object_id']);mesh.from_pydata(value['world_vertices'],value.get('edges',[]),value['faces']);mesh.update()
        obj=bpy.data.objects.new(value['object_id'],mesh);scene.collection.objects.link(obj)
        obj.color=(.04,.15,.8,1.) if obj.name==asset['task']['object_id'] else (.25,.25,.25,1.)
    bpy.context.view_layer.update();target=scene.objects[asset['task']['object_id']]
    host=BlenderSceneHost(execution_metadata=True,identity_metadata=True);object_id=host.object_id(target)
    template=BlenderMCPHost(site,port=1);renderer=host._readonly_native_module()
    def snapshot():
        raw=[dict(name=obj.name,vertices=[list(v.co) for v in obj.data.vertices],edges=[list(e.vertices) for e in obj.data.edges],
            faces=[list(f.vertices) for f in obj.data.polygons],matrix=[list(row) for row in obj.matrix_world],color=list(obj.color),
            hide_render=obj.hide_render,hide_viewport=obj.hide_viewport,selected=obj.select_get())
            for obj in sorted(scene.objects,key=lambda obj:obj.name) if obj.type=='MESH']
        return hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    before=snapshot();display=renderer.native_render_state(bpy,scene,bpy.context.view_layer);nonce=uuid.uuid4().hex
    def save(name,value):
        with (folder/name).open('x',encoding='utf8') as f:json.dump(value,f,indent=2)
    listener=socket.socket();listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    listener.bind(('127.0.0.1',0));listener.listen(4);listener.settimeout(.1);port=listener.getsockname()[1]
    if port==9876:raise ValueError('shared_port_forbidden')
    save('READY.json',dict(pid=os.getpid(),port=port,peer_nonce=nonce,source_sha256=before,object_id=object_id))
    records=[];end=time.monotonic()+180
    try:
        while time.monotonic()<end and not (folder/'STOP').exists():
            try:connection,_=listener.accept()
            except socket.timeout:continue
            with connection:
                connection.settimeout(30);wire=b''
                while True:
                    part=connection.recv(65536)
                    if not part:raise ValueError('incomplete_request')
                    wire+=part
                    if len(wire)>32768:raise ValueError('request_budget')
                    try:outer=json.loads(wire);break
                    except json.JSONDecodeError:continue
                if set(outer)!={'type','params'}:raise ValueError('envelope')
                started=time.perf_counter_ns();source_before=snapshot()
                if source_before!=before:raise ValueError('frozen_scene_changed')
                if outer['type']=='native_benchmark':
                    req=outer['params'];key=req['request_id']
                    if re.fullmatch('[a-f0-9]{32}',key) is None or req['peer_nonce']!=nonce or req['object_id']!=object_id:
                        raise ValueError('native_request_binding')
                    if set(req)!={'request_id','operation','object_id','deadline_ns','include_images','region','peer_nonce'}:
                        raise ValueError('native_request_fields')
                    native=None;error=None
                    try:
                        if type(req['deadline_ns']) is not int or not started<req['deadline_ns']<=started+30_000_000_000:
                            raise ValueError('original_deadline')
                        output=folder/('native_'+key);output.mkdir()
                        if req['operation']=='diagnose':
                            facts,*_=topology(target);native=dict(status='observed',damage='not_inferred',facts=facts,images=[],image_status='not_requested')
                        elif req['operation']=='patch' and req['include_images'] is True:
                            native=observe(scene,target,asset['task'],output,deadline_ns=req['deadline_ns'],focus_edges=req['region']['edges'])
                        else:raise ValueError('native_operation')
                        points=[target.matrix_world@v.co for v in target.data.vertices];regions=[]
                        for edges in native['facts']['boundary_edges']:
                            selected={v for edge in edges for v in edge};positions=[points[v] for v in selected]
                            bounds=[[min(p[k] for p in positions) for k in range(3)],[max(p[k] for p in positions) for k in range(3)]]
                            regions.append(dict(edges=edges,bounds=bounds))
                        native['regions']=regions
                        for frame in native['images']:
                            frame['data']=base64.b64encode(Path(frame.pop('path')).read_bytes()).decode()
                        if time.perf_counter_ns()>=req['deadline_ns']:raise ValueError('native_deadline')
                    except Exception as exc:error=type(exc).__name__+': '+str(exc)
                    result=dict(request_id=key,peer_nonce=nonce,deadline_ns=req['deadline_ns'],clock=counter_descriptor(),
                        source_before=source_before,source_after=snapshot(),native=native,error=error)
                elif outer['type']=='execute_code':
                    if set(outer['params'])!={'code'}:raise ValueError('code_fields')
                    code=outer['params']['code'];tree=ast.parse(code)
                    assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='_request')
                    req=json.loads(ast.literal_eval(assignment.value.args[0]))
                    if req['command'] not in _STRUCTURE_COMMANDS or code!=template._structure_code(req['command'],req['params'],req['id']):
                        raise ValueError('unadmitted_template')
                    output=io.StringIO()
                    with contextlib.redirect_stdout(output):exec(compile(code,'<fixed-owned-read-template>','exec'),{'bpy':bpy})
                    result=dict(status='success',result=dict(executed=True,result=output.getvalue()))
                else:raise ValueError('unadmitted_message')
                if snapshot()!=before or renderer.native_render_state(bpy,scene,bpy.context.view_layer)!=display:
                    raise ValueError('scene_or_display_changed')
                # Same one-envelope archive policy for both arms, including
                # capabilities. Older baselines retain their frozen helper.
                save('WIRE_'+str(len(records))+'.json',result)
                encoded=json.dumps(result,allow_nan=False).encode();connection.sendall(encoded)
                records.append(dict(kind=outer['type'],request_bytes=len(wire),response_bytes=len(encoded),
                    elapsed_ns=time.perf_counter_ns()-started,source_unchanged=True,display_restored=True))
        if not (folder/'STOP').exists():raise ValueError('owned_window_expired')
    finally:
        listener.close();save('SERVER_RESULT.json',dict(records=records,pid=os.getpid(),source_unchanged=snapshot()==before,
            display_restored=renderer.native_render_state(bpy,scene,bpy.context.view_layer)==display))


if __name__=='__main__':main(Path(sys.argv[sys.argv.index('--')+1]).resolve())
