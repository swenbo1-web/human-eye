"""Actual owned reference feature views through the registered MCP route.

Only creates and reads new factory scenes. Reference intent and correspondence
come from this owner builder, not from tool arguments or a model inference.
"""
import argparse,base64,copy,hashlib,importlib.util,json,math,subprocess,sys,time,types
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def cases(extra_poses=False):
    result=[dict(name='clear',dent=.002),dict(name='curved',dent=.002,curvature=.3),
        dict(name='center_mask',dent=.002,mask='center'),dict(name='feature_mask',dent=.002,offset=.05,mask='feature'),
        dict(name='fully_blocked',dent=.002,mask='full'),dict(name='already_large',dent=.004),
        dict(name='subpixel',dent=.0002,threshold=.00001),dict(name='normal_groove',dent=.002,normal_groove=True),
        dict(name='millimetre_units',dent=.002,unit_scale=.001),dict(name='far_origin',dent=.002,translation=[1e6,-1e6,1e6])]
    if extra_poses:
        for name,rotation in (('rotate_x90',[90,0,0]),('rotate_y90',[0,90,0]),('rotate_x180',[180,0,0]),
            ('rotate_y120',[0,120,0]),('rotate_y_near120',[0,119.99,0]),('rotate_oblique',[23,-41,70])):
            result.append(dict(name=name,dent=.002,rotation_degrees=rotation))
        result.append(dict(name='two_regions',dent=.002,two_regions=True))
        for angle in (114.9,115.1,124.9,125.1):result.append(dict(name='pole_boundary_'+str(angle).replace('.','_'),dent=.002,rotation_degrees=[0,angle,0]))
    return result


def builder(args):
    import bpy,bmesh
    assert bpy.app.background and args.output.resolve().is_relative_to(ROOT/'verification/fixes/20261102_m3_surface_views')
    args.output.mkdir(exist_ok=False)
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(args.core_root/'human_eye_plugin')];sys.modules['human_eye_plugin']=package
    from human_eye_plugin import mesh_structure as m
    source=args.core_root/'human_eye_plugin/blender_host.py';spec=importlib.util.spec_from_file_location('_reference_builder_host',source)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;exec(compile(source.read_bytes(),str(source),'exec'),module.__dict__)
    from verification.m3_asset_cases import build
    rows=[]
    for case in cases(args.extra_poses):
        bpy.ops.wm.read_factory_settings(use_empty=True);target=build(bpy,dict(kind='sheet',n=9,unit_scale=case.get('unit_scale',1.)))[0]
        if case.get('translation'):target.location=case['translation']
        if case.get('rotation_degrees'):target.rotation_euler=[math.radians(x) for x in case['rotation_degrees']]
        target.color=[.2,.4,.7,1.]
        bm=bmesh.new();bm.from_mesh(target.data);bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.to_mesh(target.data);bm.free()
        def height(vertex,include_dent):
            x,y=vertex.co.x,vertex.co.y;curve=case.get('curvature',0.)*(x*x+y*y)
            if case.get('two_regions'):
                return curve-sum(case['dent']*math.exp(-((x-center)**2+y*y)/(.012**2)) for center in (-.05,.05)) if include_dent else curve
            return curve-case['dent']*math.exp(-((x-case.get('offset',0.))**2+y*y)/(.025**2)) if include_dent else curve
        for vertex in target.data.vertices:vertex.co.z=height(vertex,case.get('normal_groove',False))
        target.data.update();bpy.context.view_layer.update();host=module.BlenderSceneHost(execution_metadata=True,identity_metadata=True);oid=host.object_id(target)
        reference=m.capture_raw(host,oid)
        for vertex in target.data.vertices:vertex.co.z=height(vertex,True)
        target.data.update()
        if case.get('mask'):
            if case['mask']=='center':center=(0.,0.,.006);half=(.0125,.0125,.0025)
            elif case['mask']=='feature':center=(.05,0.,.014);half=(.035,.08,.010)
            else:center=(0.,0.,.014);half=(.30,.30,.010)
            vertices=[[center[k]+sign[k]*half[k] for k in range(3)] for sign in
                ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
            faces=[[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]
            mesh=bpy.data.meshes.new('OwnedMaskMesh');mesh.from_pydata(vertices,[],faces);mesh.update()
            mask=bpy.data.objects.new('OwnedMask',mesh);bpy.context.scene.collection.objects.link(mask);mask.color=[.6,.6,.6,1.]
        bpy.context.view_layer.update();current=m.capture_raw(host,oid);target.data.calc_loop_triangles()
        triangles=[[int(i) for i in t.vertices] for t in target.data.loop_triangles];mapping=[int(t.polygon_index) for t in target.data.loop_triangles]
        folder=args.output/case['name'];folder.mkdir(exist_ok=False)
        save(folder/'REFERENCE.json',dict(raw=reference['raw'],source=reference['source'],triangles=triangles,triangle_polygons=mapping))
        path=folder/'fixture.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=True)
        row=dict(case=case,scene=str(path),scene_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),object_id=oid,
            current_raw=current['raw'],reference_sha256=hashlib.sha256((folder/'REFERENCE.json').read_bytes()).hexdigest())
        save(folder/'CASE.json',row);rows.append(row)
    save(args.output/'CASES.json',dict(rows=rows,owned_factory_only=True,blender_version=bpy.app.version_string))


def controller(args):
    folder=args.output/('rpc-'+args.run_id);folder.mkdir(exist_ok=False)
    spec=importlib.util.spec_from_file_location('_reference_view_entry',args.entry);entry=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=entry;spec.loader.exec_module(entry);proof=entry.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root']);identity,_=entry.verify_imported_runtime(proof)
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    from human_eye_plugin import mesh_structure as m,structure_task_control as control
    from human_eye_plugin.surface_reference import ReferenceRegistry,ReferenceIntent
    from human_eye_plugin.surface_task_service import consume_packet
    from human_eye_plugin import reference_view as view,native_observation as native_check
    from human_eye_plugin import reference_view_consumer as consumer
    from human_eye_plugin.surface_reference import make_view_patch
    rows=[]
    for case in json.loads((args.output/'CASES.json').read_text(encoding='utf8'))['rows']:
        root=folder/case['case']['name'];root.mkdir(exist_ok=False);config=root/'CONFIG.json';scene=Path(case['scene']).resolve()
        assert scene.parent.parent==args.output.resolve() and hashlib.sha256(scene.read_bytes()).hexdigest()==case['scene_sha256']
        reference_file=scene.parent/'REFERENCE.json';assert hashlib.sha256(reference_file.read_bytes()).hexdigest()==case['reference_sha256']
        pins={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind')};pins.update(protocol_version='2025-03-26',mode='live')
        save(config,dict(schema_version='1.0',enabled=True,project_root=proof['module_root'],expected_identity=pins,state_file='STATE.json',audit_file='AUDIT.jsonl',
            structure_task_file='TASK.json',structure_task_control_file='CONTROL.json',surface_diagnostics_enabled=True,surface_reference_images_enabled=True,
            quad_size=384,max_sessions=4))
        host=BlenderProcessHost(args.blender,scene)
        try:
            current,packet,_=consume_packet(host,case['object_id'],time.perf_counter_ns()+30_000_000_000,0,geometry=False)
            assert current['raw']==case['current_raw']
            original=json.loads(reference_file.read_text(encoding='utf8'))
            reference=m.prepare_raw(original['raw'],{k:original['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')})
            assert reference['source']['raw_sha256']==original['source']['raw_sha256']
            registry=ReferenceRegistry();ref=registry.bind(reference,current,original['triangles'],original['triangle_polygons'],
                intent=ReferenceIntent('owned_builder_same_index_before_authored_change','inspect change from authored intended surface','same_index_from_owned_copy'))
            service=LiveSpatialService(config,host=host,surface_references=registry);server=LiveSpatialMCPServer(service)
            captured=[];mutations=[];original_observe=host.observe_reference_patch
            def audited_observe(request_id,object_id,patch,deadline_ns):
                response=original_observe(request_id,object_id,patch,deadline_ns)
                save(root/('PRIVATE_VIEW_%d.json'%len(captured)),response);captured.append(response)
                if args.mutations and response['frames']:
                    caps=host.reference_view_capabilities()
                    changes=[lambda x:x.__setitem__('request_id','wrong'),lambda x:x.__setitem__('object_id','wrong'),
                        lambda x:x['patch'].__setitem__('reference_raw_sha256','wrong'),lambda x:x['packet']['raw']['vertices'][0].__setitem__(0,123),
                        lambda x:x['plan'].__setitem__('selected_ordinal',None),lambda x:x['plan'].__setitem__('producer_triangle_tests',0),
                        lambda x:x['plan']['candidates'][x['plan']['selected_ordinal']]['visible'].__setitem__(0,not x['plan']['candidates'][x['plan']['selected_ordinal']]['visible'][0]),
                        lambda x:x.__setitem__('frames',[]),lambda x:x['frames'][0]['frame'].__setitem__('span_m',123),
                        lambda x:x['frames'][0]['frustum'].__setitem__('clip_end_bu',.00001),
                        lambda x:x['frames'][0]['audit'].__setitem__('restored',False),
                        lambda x:x['frames'][0]['picture'].__setitem__('image_base64','AAAA'),
                        lambda x:x.__setitem__('deadline_ns',deadline_ns+1),lambda x:x['display']['objects'][0].__setitem__('alpha',.5),
                        lambda x:x['evidence']['native_scene']['objects'][0].__setitem__('faces',[]),lambda x:x.__setitem__('execution_authority',True)]
                    for ordinal,change in enumerate(changes):
                        altered=copy.deepcopy(response);change(altered)
                        try:consumer.validate_result(altered,object_id=object_id,patch=patch,request_id=request_id,deadline_ns=deadline_ns,capabilities=caps)
                        except (ValueError,KeyError,TypeError):mutations.append(ordinal)
                        else:raise AssertionError('mutated private view accepted: '+str(ordinal))
                return response
            host.observe_reference_patch=audited_observe
            save(root/'INITIALIZE.json',server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=1,method='initialize',params=dict(protocolVersion='2025-03-26',capabilities={}))))
            task=control.begin(config,'reference-view',case['object_id']);records=[]
            def call(request,operation,include_image=False,**fields):
                query=dict(mode='mesh_surface',operation=operation,request_id=request,task_ref=task['task_ref']);query.update(fields);start=time.perf_counter_ns()
                reply=server.handle_jsonrpc_message(dict(jsonrpc='2.0',id=request,method='tools/call',params=dict(name='human_eye_scene_observe',
                    arguments=dict(session_id='reference-view',focal_id=case['object_id'],include_image=include_image,query=query,response_detail='full'))))
                elapsed=time.perf_counter_ns()-start;storage=request+'-'+str(len(records));save(root/(storage+'.json'),reply)
                content=reply['result']['content'];value=json.loads(next(c['text'] for c in content if c['type']=='text'));pictures=[c for c in content if c['type']=='image']
                for index,picture in enumerate(pictures):(root/(storage+'-'+str(index)+'.png')).write_bytes(base64.b64decode(picture['data'],validate=True))
                records.append(dict(request=request,elapsed_ns=elapsed,text_bytes=sum(len(c['text'].encode()) for c in content if c['type']=='text'),
                    images=len(pictures),isError=reply['result']['isError'],metadata=value));return value
            threshold=case['case'].get('threshold',.0002)*case['case'].get('unit_scale',1.)
            first=call('reference','reference',reference_ref=ref,threshold_m=threshold)
            qa=None
            if first.get('feature_refs'):
                # Additional trusted QA source read is separately counted. It
                # is not an extra model query or a production latency claim.
                evidence=host.capture_readonly_evidence();save(root/'QA_NATIVE.json',evidence)
                binding=registry.resolve(ref,current);patch=make_view_patch(binding,current,first['diagnostic'],0,ref,budget=m.WorkBudget())
                _,candidates,_=view.plan(packet,patch,evidence['native_scene'],time.perf_counter_ns()+30_000_000_000)
                obj=next(o for o in evidence['native_scene']['objects'] if o['object_id']==case['object_id'])
                object_center=min(range(len(current['raw']['vertices'])),key=lambda i:sum(current['raw']['vertices'][i][k]**2 for k in (0,1)))
                peak=max(range(len(current['raw']['vertices'])),key=lambda i:sum((current['raw']['vertices'][i][k]-reference['raw']['vertices'][i][k])**2 for k in range(3)))
                qa=[]
                for candidate in candidates:
                    row=dict(candidate=candidate['ordinal'])
                    for name,index in (('object_center',object_center),('peak_change',peak)):
                        try:
                            depth,ids,epsilon=native_check._dense_focus_ray_readback(evidence['native_scene'],obj['world_vertices'][index],candidate['right'],candidate['up'],candidate['eye'])
                            row[name+'_visible']=depth is not None and abs(depth)<=epsilon and ids=={case['object_id']}
                        except ValueError:row[name+'_visible']=None
                    qa.append(row)
                selected=first['feature_refs'][0]['patch_ref'];call('picture','reference_patch',include_image=True,patch_ref=selected)
                # Same id must return only its receipt and never render again.
                receipt=call('picture','reference_patch',include_image=True,patch_ref=selected)
                assert receipt['status']=='receipt' and records[-1]['images']==0
                other=first['feature_refs'][1]['patch_ref'] if len(first['feature_refs'])>1 else selected
                call('second_attempt','reference_patch',include_image=True,patch_ref=other)
            count=sum(r['images'] for r in records);name=case['case']['name']
            expected=2 if name in ('clear','curved','center_mask','millimetre_units','two_regions') or 'rotation_degrees' in case['case'] else 0
            if not args.exploratory_poses:assert count==expected,(name,records)
            if name=='two_regions':assert first['diagnostic']['cluster_count']==2 and len(first['feature_refs'])==2
            if name=='center_mask':
                visual=records[1]['metadata']['visual_evidence'];assert visual['actual_witness_visibility'][0] is False and sum(visual['actual_witness_visibility'])>=2
                assert all(r['peak_change_visible'] is False for r in qa),qa
            if name=='feature_mask':assert all(r['object_center_visible'] is True and r['peak_change_visible'] is False for r in qa),qa
            after,_,_=consume_packet(host,case['object_id'],time.perf_counter_ns()+30_000_000_000,0,geometry=False)
            assert after['raw']==current['raw'],'observation changed source geometry'
            control.close(config,task['task_ref'])
            row=dict(case=case['case'],records=records,raw_source_unchanged=True,fixture_reference_verified=True,model_calls=0,
                independent_point_visibility=qa,extra_QA_native_capture=1 if qa is not None else 0,
                private_frames_captured=len(captured),mutations_rejected=mutations,mutation_instrumented_latency=args.mutations)
            row.update(expected_images=expected,actual_images=count,image_expectation_met=count==expected,exploratory_pose_run=args.exploratory_poses)
            rows.append(row);save(root/'RESULT.json',row)
            print(json.dumps(dict(case=case['case']['name'],changed=first.get('diagnostic',{}).get('changed_count'),
                images=sum(r['images'] for r in records),image_status=[r['metadata'].get('image_status') for r in records],
                reasons=[r['metadata'].get('reason') for r in records])),flush=True)
        finally:host.close()
        assert host._process.poll()==0 and hashlib.sha256(scene.read_bytes()).hexdigest()==case['scene_sha256']
        save(root/'LIFECYCLE.json',dict(exit_code=0,source_file_unchanged=True))
    save(folder/'RESULT.json',dict(rows=rows,runtime_source=identity['source_sha256'],user_GUI_accessed=False,formal_model_calls=0))
    if any(not row['image_expectation_met'] for row in rows):raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--builder',action='store_true');p.add_argument('--controller',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--core-root',type=Path);p.add_argument('--entry',type=Path);p.add_argument('--blender',type=Path)
    p.add_argument('--run-id',default='r1');argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    p.add_argument('--mutations',action='store_true')
    p.add_argument('--extra-poses',action='store_true');p.add_argument('--exploratory-poses',action='store_true')
    args=p.parse_args(argv);builder(args) if args.builder else controller(args)
