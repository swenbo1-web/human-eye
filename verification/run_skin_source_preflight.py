"""Owned LBS assets and independent NumPy correspondence verification."""
import argparse,hashlib,importlib.util,json,math,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
REGISTRATION=ROOT/'verification/fixes/20261102_m4_deformation_closeout/CASES_PREREGISTERED.json'
LEGACY_POSITIVE=('neutral','single_bone','mixed_bend','collapse','distinct_rest','parent_chain','world_offsets','millimetres',
    'weights_02_08','unweighted','all_unweighted','unused_group','max_mesh','bones64','influences8','coordinate10','world100','subframe')
B1_COMBINATIONS=('gradient_weights','rest_roll','parent_combo','distinct_rig_mesh_world')
# Written from the intended refusal contract before the new native run. A
# different unsupported error is a failing test, never an interchangeable pass.
NEGATIVE_REASONS={
    'vertices129':'unsupported_skin_vertex_limit',
    'triangles257':'unsupported_skin_triangle_limit',
    'bones65':'unsupported_skin_bone_limit',
    'influences9':'unsupported_skin_influence_limit',
    'unnormalized':'unsupported_skin_nonunit_weight_sum',
    'unknown_group':'unsupported_skin_unknown_or_nondeform_group',
    'nondeform_bone':'unsupported_skin_unknown_or_nondeform_group',
    'wrong_rig':'unsupported_skin_modifier_rig',
    'DQ':'unsupported_skin_modifier_use_deform_preserve_volume',
    'envelopes':'unsupported_skin_modifier_use_bone_envelopes',
    'mask':'unsupported_skin_modifier_vertex_group',
    'multi_modifier':'unsupported_skin_modifier_use_multi_modifier',
    'disabled':'unsupported_skin_modifier_show_viewport',
    'extra_modifier':'unsupported_skin_modifier_count',
    'shape_key':'unsupported_skin_shape_keys',
    'original_quad':'unsupported_skin_original_nontriangles',
    'mesh_parent':'unsupported_skin_mesh_dependencies:object_parent',
    'rig_parent':'unsupported_skin_rig_domain:object_parent',
    'mesh_scale':'unsupported_skin_object_transform',
    'bone_scale':'unsupported_skin_rig_domain:bone_scale_or_shear',
    'bone_translation':'unsupported_skin_raw_bone_translation_or_scale',
    'inheritance':'unsupported_skin_rig_domain:nondefault_inheritance',
    'B_bone':'unsupported_skin_rig_domain:B_bone_segments',
    'mesh_animation':'unsupported_skin_mesh_dependencies:animation',
    'rig_driver':'unsupported_skin_rig_domain:drivers',
    'rig_constraint':'unsupported_skin_rig_domain:constraints',
    'REST':'unsupported_skin_rig_domain:rest_display_mode',
    'bone_envelope_multiply':'unsupported_skin_bone_envelope_multiply',
    'bone_envelope_neutral':'unsupported_skin_bone_envelope_multiply',
    'coordinate_over10':'unsupported_skin_coordinate_domain',
    'world_over100':'unsupported_skin_object_transform',
}
B2_CASES=('surface_rigid_rotation','surface_rigid_translation','surface_stretch','surface_compress','surface_shear','surface_fold',
    'surface_collapsed','surface_original_zero','surface_near_original','surface_tiny_representable','surface_tiny_offset',
    'surface_near_current','surface_unweighted')

def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def surface_spec(name):
    """Authored finite geometry, not production diagnostic output.

    Per-vertex exact half-turns around distinct pivots implement the planar
    affine examples with rigid bones only; no bone translation/scale/modifier
    expansion is needed. Quaternion half-turns avoid an approximate sin(pi)
    turning the deliberately exact collapsed example into a near collapse.
    """
    if name not in B2_CASES:return None
    vertices=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]];faces=[[0,1,2]]
    target=[v[:] for v in vertices];state='measured';reason=None
    heads=[[0.,0.,0.]];rotations=[[0.,0.,0.]];quaternions=None
    weights=[[[0,1.]] for _ in vertices]
    if name=='surface_rigid_rotation':rotations=[[25.,-35.,40.]]
    if name=='surface_original_zero':vertices=[[0.,0.,0.],[1.,0.,0.],[2.,0.,0.]];state='unknown';reason='original_zero_area'
    if name=='surface_near_original':vertices=[[0.,0.,0.],[1.,0.,0.],[1.,2**-24,0.]];state='unknown';reason='reference_ill_conditioned'
    if name=='surface_tiny_representable':vertices=[[0.,0.,0.],[2**-30,0.,0.],[0.,2**-30,0.]]
    if name=='surface_tiny_offset':
        vertices=[[1.,1.,0.],[1.+2**-22,1.,0.],[1.,1.+2**-22,0.]];state='unknown';reason='reference_below_coordinate_resolution'
    if name=='surface_unweighted':weights[0]=[];state='unknown';reason='unweighted_vertex_source'
    if name=='surface_fold':
        vertices=[[-1.,0.,0.],[0.,0.,0.],[0.,1.,0.],[1.,0.,0.]];faces=[[0,1,2],[1,3,2]]
        heads=[[0.,0.,0.],[0.,0.,0.]];rotations=[[0.,0.,0.],[0.,60.,0.]];weights=[[[0,1.]],[[0,1.]],[[0,1.]],[[1,1.]]]
    affine={
        'surface_rigid_translation':([[1.,0.],[0.,1.]],[.25,-.125]),
        'surface_stretch':([[1.5,0.],[0.,1.]],[0.,0.]),
        'surface_compress':([[.5,0.],[0.,.8]],[0.,0.]),
        'surface_shear':([[1.,.5],[0.,1.]],[0.,0.]),
        'surface_collapsed':([[0.,0.],[0.,0.]],[0.,0.]),
        'surface_near_current':([[1.,0.],[0.,2**-18]],[0.,0.]),
    }
    if name in affine:
        a,t=affine[name];target=[[sum(a[k][j]*v[j] for j in range(2))+t[k] for k in range(2)]+[v[2]] for v in vertices]
        heads=[[(v[k]+w[k])/2 for k in range(3)] for v,w in zip(vertices,target)]
        rotations=[[0.,0.,180.] for _ in heads];quaternions=[[0.,0.,0.,1.] for _ in heads];weights=[[[i,1.]] for i in range(len(vertices))]
    if name=='surface_collapsed':state='collapsed';reason='current_zero_area'
    if name=='surface_near_current':state='unknown';reason='current_near_degenerate'
    return dict(vertices=vertices,triangles=faces,heads=heads,rolls_deg=[0.]*len(heads),rotations_deg=rotations,
        quaternions=quaternions,weights=weights,parents=[None]*len(heads),
        expected_diagnostics=[dict(triangle=i,state=state,reason=reason) for i in range(len(faces))],
        authored_affine=list(affine[name]) if name in affine else None,intent='geometric facts only, including benign rigid motion/fold; no damage label')


def catalog():
    return dict(schema='finite-skin-deformation-cases-v1',legacy_positive=list(LEGACY_POSITIVE),legacy_negative=dict(NEGATIVE_REASONS),
        B1_combinations=list(B1_COMBINATIONS),B2={name:surface_spec(name) for name in B2_CASES},
        B1_combination_inputs=dict(gradient='w0=(index+1)/(vertices+1), w1=1-w0 on adjacent authored vertices',
            rest_roll_deg=[37.,-23.],rest_roll_pose_deg=[[27.,11.,-9.],[-19.,31.,7.]],
            parent_roll_deg=[15.,-25.],parent_pose_deg=[[30.,20.,-15.],[-10.,40.,25.]],
            distinct_world=dict(rig_deg=[20.,-15.,40.],rig_location=[1.,-2.,.5],mesh_deg=[-10.,30.,20.],mesh_location=[-1.,.3,.7])),
        oracle='authored rigid bones/pivots/weights, independent NumPy LBS and QR/SVD, separate native index witness',
        comparison=dict(position_atol=2e-5,stretch_atol=5e-5,area_atol=5e-5),
        scope='owned background factory fixtures; no GUI, no product geometry setters, no source self-answer',formal_model_trials=0)


def verify_registration(path):
    value=json.loads(path.read_bytes())
    if value!=catalog():raise ValueError('case_registration_changed')
    return sha(path)


def verify_negative(name,report,error):
    expected='rig_pose_skin_reply:rig_pose_'+NEGATIVE_REASONS[name]
    if report is not None or error!=expected:raise AssertionError((name,'wrong_refusal_reason',expected,error))


def geometry(torus=False,extra_vertices=0,extra_face=False):
    if torus:
        vertices=[];faces=[]
        for i in range(8):
            a=2*math.pi*i/8
            for j in range(16):
                b=2*math.pi*j/16;radius=1+.2*math.cos(b);vertices.append([radius*math.cos(a),radius*math.sin(a),.2*math.sin(b)])
        for i in range(8):
            for j in range(16):
                a=i*16+j;b=((i+1)%8)*16+j;c=((i+1)%8)*16+(j+1)%16;d=i*16+(j+1)%16;faces.extend([[a,b,c],[a,c,d]])
        if extra_face:faces.append([0,2,17])
    else:
        vertices=[[x,y,z] for y in (0.,1.) for x,z in ((-.25,-.25),(.25,-.25),(.25,.25),(-.25,.25))]
        faces=[]
        for i in range(4):a=i;b=(i+1)%4;faces.extend([[a,b,b+4],[a,b+4,a+4]])
        faces.extend([[0,2,1],[0,3,2],[4,5,6],[4,6,7]])
        vertices.extend([[i*.001,.5,.1] for i in range(extra_vertices)])
    return vertices,faces


def builder(args):
    import bpy
    registration_sha=verify_registration(args.registration)
    assert bpy.app.background and args.output.is_absolute() and args.output.resolve().is_relative_to(ROOT/'verification/fixes');args.output.mkdir(exist_ok=False)
    positive=LEGACY_POSITIVE+B1_COMBINATIONS+B2_CASES;negative=tuple(NEGATIVE_REASONS)
    rows=[]
    for name in positive+negative:
        surface=surface_spec(name);parented=name in ('parent_chain','parent_combo','distinct_rig_mesh_world')
        bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
        data=bpy.data.armatures.new('RigData');rig=bpy.data.objects.new('Rig',data);scene.collection.objects.link(rig)
        bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
        count=len(surface['heads']) if surface else 64 if name=='bones64' else 65 if name=='bones65' else 8 if name=='influences8' else 9 if name=='influences9' else 2
        heads=[];rolls=[0.]*count;rotations=[[0.,0.,0.] for _ in range(count)]
        if not surface and name not in ('neutral','bone_envelope_neutral'):rotations[0]=[35.,0.,0.];rotations[1]=[-20.,0.,0.]
        if name=='collapse':rotations[0]=[0.,90.,0.];rotations[1]=[0.,-90.,0.]
        if name=='single_bone':rotations[0]=[45.,0.,0.]
        if name=='rest_roll':rolls=[37.,-23.];rotations=[[27.,11.,-9.],[-19.,31.,7.]]
        if name in ('parent_combo','distinct_rig_mesh_world'):rolls=[15.,-25.];rotations=[[30.,20.,-15.],[-10.,40.,25.]]
        if surface:rolls=surface['rolls_deg'];rotations=surface['rotations_deg']
        for i in range(count):
            b=data.edit_bones.new('bone_%03d'%i);head=surface['heads'][i] if surface else [0.,2. if parented and i==1 else 1. if name=='distinct_rest' and i==1 else 0.,0.]
            b.head=head;b.tail=[head[0],head[1]+2,head[2]];b.roll=math.radians(rolls[i]);heads.append(head)
            if parented and i==1:b.parent=data.edit_bones['bone_000'];b.use_connect=True
        bpy.ops.object.mode_set(mode='OBJECT');rig.rotation_mode='XYZ'
        for i in range(count):
            b=rig.pose.bones['bone_%03d'%i];b.rotation_mode='XYZ';b.rotation_euler=[math.radians(v) for v in rotations[i]]
            if surface and surface['quaternions'] is not None:b.rotation_mode='QUATERNION';b.rotation_quaternion=surface['quaternions'][i]
        vertices,faces=(surface['vertices'],surface['triangles']) if surface else geometry(name in ('max_mesh','triangles257'),121 if name=='vertices129' else 0,name=='triangles257')
        if name in ('coordinate10','coordinate_over10'):
            for vertex in vertices:vertex[0]+=9.75 if name=='coordinate10' else 9.751
        if name=='original_quad':faces=[[0,1,2,3]]
        mesh=bpy.data.meshes.new('SkinData');mesh.from_pydata(vertices,[],faces);obj=bpy.data.objects.new('Skin',mesh);scene.collection.objects.link(obj)
        obj.rotation_mode='XYZ';groups=[obj.vertex_groups.new(name='bone_%03d'%i) for i in range(count)];weights=[]
        for i in range(len(vertices)):
            if surface:values=surface['weights'][i]
            elif name=='all_unweighted' or name=='unweighted' and i==0:values=[]
            elif name=='single_bone':values=[(0,1.)]
            elif name in ('influences8','influences9'):values=[(j,1./count) for j in range(count)]
            elif name=='unnormalized':values=[(0,.25),(1,.25)]
            elif name=='weights_02_08':values=[(0,.2),(1,.8)]
            elif name in ('gradient_weights','parent_combo','distinct_rig_mesh_world'):w=(i+1)/(len(vertices)+1);values=[(0,w),(1,1-w)]
            else:values=[(0,.5),(1,.5)]
            for group,weight in values:groups[group].add([i],weight,'REPLACE')
            weights.append([[g,w] for g,w in values])
        if name in ('unused_group','unknown_group'):extra=obj.vertex_groups.new(name='Decoration')
        if name=='unknown_group':
            groups[0].add([0],.45,'REPLACE');groups[1].add([0],.45,'REPLACE');extra.add([0],.1,'REPLACE')
            weights[0]=[[0,.45],[1,.45],[count,.1]]
        if name=='nondeform_bone':data.bones['bone_001'].use_deform=False
        if name in ('bone_envelope_multiply','bone_envelope_neutral'):
            data.bones['bone_000'].use_envelope_multiply=True;data.bones['bone_000'].envelope_distance=.1
            data.bones['bone_000'].head_radius=.01;data.bones['bone_000'].tail_radius=.01
        mod=obj.modifiers.new('Skinning','ARMATURE');mod.object=rig;mod.use_vertex_groups=True;mod.use_bone_envelopes=False
        if name=='wrong_rig':other=bpy.data.objects.new('WrongRig',data.copy());scene.collection.objects.link(other);mod.object=other
        if name=='DQ':mod.use_deform_preserve_volume=True
        if name=='envelopes':mod.use_bone_envelopes=True
        if name=='mask':mod.vertex_group='bone_000'
        if name=='multi_modifier':mod.use_multi_modifier=True
        if name=='disabled':mod.show_viewport=False
        if name=='extra_modifier':obj.modifiers.new('Subdivision','SUBSURF')
        if name=='shape_key':obj.shape_key_add(name='Basis');obj.shape_key_add(name='Key')
        if name in ('mesh_parent','rig_parent'):
            parent=bpy.data.objects.new('Parent',None);scene.collection.objects.link(parent);(obj if name=='mesh_parent' else rig).parent=parent
        if name=='mesh_scale':obj.scale=(2,1,1)
        if name=='bone_scale':rig.pose.bones['bone_000'].scale=(1,2,1)
        if name=='bone_translation':rig.pose.bones['bone_000'].location.y=.1
        if name=='inheritance':data.bones['bone_000'].inherit_scale='NONE'
        if name=='B_bone':data.bones['bone_000'].bbone_segments=4
        if name=='mesh_animation':obj.keyframe_insert(data_path='location',frame=1)
        if name=='rig_driver':rig.pose.bones['bone_000'].driver_add('rotation_euler',1).driver.expression='0.2'
        if name=='rig_constraint':rig.pose.bones['bone_000'].constraints.new('LIMIT_ROTATION')
        if name=='REST':data.pose_position='REST'
        world=dict(rig_deg=[20.,-15.,40.],rig_location=[1.,-2.,.5],mesh_deg=[-10.,30.,20.],mesh_location=[-1.,.3,.7]) if name in ('world_offsets','distinct_rig_mesh_world') else dict(rig_deg=[0.,0.,0.],rig_location=[0.,0.,0.],mesh_deg=[0.,0.,0.],mesh_location=[0.,0.,0.])
        if name in ('world100','world_over100'):world['rig_location']=world['mesh_location']=[100. if name=='world100' else 100.01,0.,0.]
        for item,prefix in ((rig,'rig'),(obj,'mesh')):item.rotation_euler=[math.radians(v) for v in world[prefix+'_deg']];item.location=world[prefix+'_location']
        if name=='millimetres':scene.unit_settings.scale_length=.001
        if name=='subframe':scene.frame_set(12,subframe=.25)
        marker=mesh.attributes.new('he_oracle_vertex_id','INT','POINT')
        for i,entry in enumerate(marker.data):entry.value=i
        bpy.context.view_layer.update();folder=args.output/name;folder.mkdir();path=folder/'fixture.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=True)
        bpy.ops.wm.open_mainfile(filepath=str(path));obj=bpy.context.scene.objects['Skin'];rig=bpy.context.scene.objects['Rig'];ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        # Independent native index witness created only by this test builder.
        ids=[v.value for v in ev.data.attributes['he_oracle_vertex_id'].data] if 'he_oracle_vertex_id' in ev.data.attributes else None
        native=dict(vertices=[list(v.co) for v in ev.data.vertices],triangles=[list(p.vertices) for p in ev.data.polygons],marker_ids=ids,
            original_marker_ids=[v.value for v in obj.data.attributes['he_oracle_vertex_id'].data],
            modifier_RNA_fields=[p.identifier for p in obj.modifiers[0].bl_rna.properties if p.identifier!='rna_type' and not p.is_readonly])
        save(folder/'NATIVE_WITNESS.json',native)
        oracle=dict(supported=name in positive,vertices=vertices,triangles=faces,weights=weights,heads=heads,rotations_deg=rotations,
            parents=[None if not parented or i!=1 else 0 for i in range(count)],rolls_deg=rolls,quaternions=surface['quaternions'] if surface else None,bones=count,world=world,
            unweighted=sum(not any(w>0 for _,w in values) for values in weights),expected_rejection=NEGATIVE_REASONS.get(name),
            surface=surface,
            frame=dict(number=bpy.context.scene.frame_current,subframe=bpy.context.scene.frame_subframe),unit=.001 if name=='millimetres' else 1.,
            truth='authored geometry/rest/rotations/weights, independent NumPy replay and separate native propagated index marker')
        save(folder/'ORACLE.json',oracle);rows.append(dict(name=name,scene=str(path),scene_sha256=sha(path),oracle=oracle))
    save(args.output/'CASES.json',dict(rows=rows,registration_sha256=registration_sha,builder_sha256=sha(Path(__file__))));print(json.dumps(dict(built=len(rows))))


def rotation(values):
    import numpy as np
    result=np.eye(4)
    for axis,deg in enumerate(values):
        a=math.radians(deg);c=math.cos(a);s=math.sin(a);m=np.eye(4);i,j=((1,2),(2,0),(0,1))[axis]
        m[i,i]=m[j,j]=c;m[i,j]=-s;m[j,i]=s;result=m@result
    return result


def quaternion_rotation(values):
    import numpy as np
    w,x,y,z=np.array(values,dtype=float)/np.linalg.norm(values)
    result=np.eye(4);result[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
        [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
    return result


def independent_LBS(o):
    import numpy as np
    rest=[];pose=[];w=o['world'];rig=rotation(w['rig_deg']);rig[:3,3]=w['rig_location'];mesh=rotation(w['mesh_deg']);mesh[:3,3]=w['mesh_location']
    for i,head in enumerate(o['heads']):
        rm=rotation([0.,o.get('rolls_deg',[0.]*len(o['heads']))[i],0.]);rm[:3,3]=head
        quaternions=o.get('quaternions');basis=quaternion_rotation(quaternions[i]) if quaternions is not None else rotation(o['rotations_deg'][i]);parent=o['parents'][i]
        pm=rm@basis if parent is None else pose[parent]@np.linalg.inv(rest[parent])@rm@basis;rest.append(rm);pose.append(pm)
    bind=np.linalg.inv(rig)@mesh;unbind=np.linalg.inv(bind);result=[]
    for v,influences in zip(o['vertices'],o['weights']):
        if not influences:result.append(v);continue
        source=bind@np.array([*v,1.]);total=sum(weight for _,weight in influences)
        point=sum((weight/total)*(pose[group]@np.linalg.inv(rest[group])@source) for group,weight in influences)
        result.append((unbind@point)[:3].tolist())
    return np.array(result),mesh


def independent_surface(original,current):
    """A second numerical route: NumPy QR reference chart then 3x2 SVD.

    No production validator/metric function or thresholds are imported here.
    Condition/unknown expectations are authored in surface_spec, not inferred
    by this oracle. Metrics remain available for checking known-safe examples.
    """
    import numpy as np
    a=np.array(original,dtype=float);b=np.array(current,dtype=float)
    reference=np.column_stack((a[1]-a[0],a[2]-a[0]));deformed=np.column_stack((b[1]-b[0],b[2]-b[0]))
    reference_area=np.linalg.norm(np.cross(reference[:,0],reference[:,1]));current_area=np.linalg.norm(np.cross(deformed[:,0],deformed[:,1]))
    if reference_area==0:return dict(stretches=None,area_ratio=None)
    _,chart=np.linalg.qr(reference,mode='reduced');surface_map=np.linalg.solve(chart.T,deformed.T).T
    return dict(stretches=np.linalg.svd(surface_map,compute_uv=False).tolist(),area_ratio=float(current_area/reference_area))


def verify_surface_report(report,packet,oracle):
    import numpy as np
    expected,world=independent_LBS(oracle);vertices=oracle['vertices'];triangles=oracle['triangles'];unit=oracle['unit']
    assert report['assessment']=='geometric_facts_not_damage' and report['damage_classification']=='not_inferred' and report['execution_authority'] is False
    assert report['source_sha256']==packet['source_sha256']
    assert report['source_summary']['vertices_total']==len(vertices) and report['triangles_total']==len(triangles)
    assert report['triangles_omitted']==0 and len(report['triangles'])==len(triangles)
    assert report['source_summary']['unweighted_vertices_total']==oracle['unweighted']
    actual={row['triangle']:row for row in report['triangles']};assert len(actual)==len(triangles)
    counts={'measured':0,'collapsed':0,'unknown':0};reasons={};truth=[]
    for spec in oracle['surface']['expected_diagnostics']:
        i=spec['triangle'];tri=triangles[i];row=actual[i];counts[spec['state']]+=1
        assert row['state']==spec['state'] and row['reason']==spec['reason'],(i,spec,row)
        assert row['vertices']==tri and row['region_kind']=='original_triangle'
        if spec['state']=='unknown':
            reasons[spec['reason']]=reasons.get(spec['reason'],0)+1
            assert row['principal_stretches'] is None and row['area_ratio'] is None and row['engineering_strains'] is None
        else:
            value=independent_surface([vertices[j] for j in tri],[expected[j] for j in tri]);truth.append(dict(triangle=i,**value))
            assert np.max(np.abs(np.array(row['principal_stretches'])-value['stretches']))<=5e-5,(i,'stretches',row,value)
            assert np.max(np.abs(np.array(row['engineering_strains'])-(np.array(value['stretches'])-1)))<=5e-5
            assert abs(row['area_ratio']-value['area_ratio'])<=5e-5,(i,'area',row,value)
        points=np.array([(world@np.array([*expected[j],1.]))[:3]*unit for j in tri])
        assert np.max(np.abs(np.array(row['centroid_world_m'])-points.mean(axis=0)))<=2e-5*unit
        assert np.max(np.abs(np.array(row['bounds_world_m'])-np.array([points.min(axis=0),points.max(axis=0)])))<=2e-5*unit
    assert [report['triangles_'+k] for k in ('measured','collapsed','unknown')]==[counts[k] for k in ('measured','collapsed','unknown')]
    assert report['unknown_reasons']==reasons and report['status']==('partial' if counts['unknown'] else 'observed')
    return truth


def controller(args):
    import numpy as np
    sys.path.insert(0,str(args.core_root))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_skin_fixed_target',args.entry.with_name('target_runtime_entry.py'));entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
        proof=entry.validate_binding(expected_python=sys.executable);assert Path(proof['module_root'])==args.core_root.resolve();entry.verify_imported_runtime(proof)
    from human_eye_plugin import skin_source as core
    from human_eye_plugin import surface_deformation
    from human_eye_plugin.skin_source_process import SkinSourceProcess
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity();registration_sha=verify_registration(args.registration)
    fixtures=json.loads((args.fixtures/'CASES.json').read_bytes());expected_names=LEGACY_POSITIVE+B1_COMBINATIONS+B2_CASES+tuple(NEGATIVE_REASONS)
    assert fixtures['registration_sha256']==registration_sha and fixtures['builder_sha256']==sha(Path(__file__))
    assert [v['name'] for v in fixtures['rows']]==list(expected_names),'fixture_case_matrix_changed'
    args.output.mkdir(exist_ok=False);binary=Path('D:/Tools/blender5.2/blender.exe');binary_sha=sha(binary);rows=[]
    for case in fixtures['rows']:
        folder=args.output/case['name'];folder.mkdir();o=case['oracle'];profile=dict(schema='skin-source-operator-profile-v1',blender_executable=str(binary),blender_sha256=binary_sha,
            scene_file=case['scene'],scene_sha256=case['scene_sha256'],mesh_name='Skin',rig_name='Rig',expected_frame=o['frame'],runtime_source_sha256=identity['source_sha256'])
        assert o['supported']==(case['name'] not in NEGATIVE_REASONS) and o['expected_rejection']==NEGATIVE_REASONS.get(case['name'])
        assert o['surface']==surface_spec(case['name'])
        save(folder/'PROFILE.json',profile);actor=None;report=None;surface_report=None;surface_truth=None;first=None;second=None;error=None;started=time.perf_counter_ns()
        try:
            actor=SkinSourceProcess(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect();report=core.analyze(second,deadline_ns=actor.deadline_ns)
            if o['surface'] is not None:surface_report=surface_deformation.analyze(second,deadline_ns=actor.deadline_ns)
        except Exception as exc:error=str(exc)
        finally:
            if actor is not None:actor.close()
        if o['supported']:
            assert report is not None,(case['name'],error)
            expected,world=independent_LBS(o);m=second['mesh'];assert np.max(np.abs(expected-np.array(m['evaluated_vertices'])))<=2e-5,(case['name'],'independent LBS')
            assert np.max(np.abs(np.array(o['vertices'])-np.array(m['vertices'])))<1e-6
            witness=json.loads((args.fixtures/case['name']/'NATIVE_WITNESS.json').read_bytes());assert witness['marker_ids']==list(range(len(o['vertices'])))==witness['original_marker_ids']
            assert np.max(np.abs(expected-np.array(witness['vertices'])))<=2e-5
            assert report['unweighted_vertices_total']==o['unweighted'] and report['vertices_total']==len(o['vertices'])
            assert report['vertices_omitted']==max(0,len(o['vertices'])-16)
            assert report['status']==('partial' if o['unweighted'] else 'observed') and report['assessment']=='source_facts_only'
            for fact in report['vertices']:
                index=fact['vertex'];before=world@np.array([*o['vertices'][index],1.]);after=world@np.array([*expected[index],1.])
                assert abs(fact['displacement_m']-float(np.linalg.norm(after[:3]-before[:3]))*o['unit'])<2e-5*o['unit']
            assert first['source_sha256']==second['source_sha256'] and report['geometry_setters']==0 and not report['original_file_saved']
            save(folder/'SOURCE_PACKET.json',second)
            if o['surface'] is not None:
                assert surface_report is not None,(case['name'],error)
                surface_truth=verify_surface_report(surface_report,second,o)
                save(folder/'SURFACE_REPORT.json',surface_report);save(folder/'NUMPY_SURFACE_TRUTH.json',surface_truth)
        else:verify_negative(case['name'],report,error)
        assert sha(Path(case['scene']))==case['scene_sha256']
        row=dict(case=case['name'],supported=o['supported'],passed=True,first=first,second=second,report=report,surface_report=surface_report,surface_truth=surface_truth,error=error,elapsed_ns=time.perf_counter_ns()-started,
            original_file_unchanged=True);save(folder/'RESULT.json',row);rows.append(row);print(json.dumps(dict(case=case['name'],passed=True,supported=o['supported'])),flush=True)
    save(args.output/'RESULT.json',dict(cases=rows,total=len(rows),supported=sum(v['supported'] for v in rows),source_sha256=identity['source_sha256'],source_count=len(identity['source_files']),
        registration_sha256=registration_sha,fixtures_sha256=sha(args.fixtures/'CASES.json'),B2_cases=len(B2_CASES),formal_model_trials=0,shared_GUI=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--builder',action='store_true');mode.add_argument('--controller',action='store_true');mode.add_argument('--preregister',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures',type=Path);p.add_argument('--core-root',type=Path,default=ROOT);p.add_argument('--entry',type=Path)
    p.add_argument('--registration',type=Path,default=REGISTRATION)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];args=p.parse_args(argv)
    if args.preregister:
        assert args.output.is_absolute() and args.output.resolve().is_relative_to(ROOT/'verification/fixes');save(args.output,catalog());print(args.output)
    else:builder(args) if args.builder else controller(args)
