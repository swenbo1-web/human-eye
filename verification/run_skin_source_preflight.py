"""Owned LBS assets and independent NumPy correspondence verification."""
import argparse,hashlib,importlib.util,json,math,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


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
    assert bpy.app.background and args.output.is_absolute() and args.output.resolve().is_relative_to(ROOT/'verification/fixes');args.output.mkdir(exist_ok=False)
    positive=['neutral','single_bone','mixed_bend','collapse','distinct_rest','parent_chain','world_offsets','millimetres',
        'weights_02_08','unweighted','all_unweighted','unused_group','max_mesh','bones64','influences8','coordinate10','world100','subframe']
    negative=['vertices129','triangles257','bones65','influences9','unnormalized','unknown_group','nondeform_bone','wrong_rig','DQ',
        'envelopes','mask','multi_modifier','disabled','extra_modifier','shape_key','original_quad','mesh_parent','rig_parent',
        'mesh_scale','bone_scale','bone_translation','inheritance','B_bone','mesh_animation','rig_driver','rig_constraint','REST',
        'bone_envelope_multiply','bone_envelope_neutral','coordinate_over10','world_over100']
    rows=[]
    for name in positive+negative:
        bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
        data=bpy.data.armatures.new('RigData');rig=bpy.data.objects.new('Rig',data);scene.collection.objects.link(rig)
        bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
        count=64 if name=='bones64' else 65 if name=='bones65' else 8 if name=='influences8' else 9 if name=='influences9' else 2
        heads=[];rolls=[0.]*count;rotations=[[0.,0.,0.] for _ in range(count)]
        if name not in ('neutral','bone_envelope_neutral'):rotations[0]=[35.,0.,0.];rotations[1]=[-20.,0.,0.]
        if name=='collapse':rotations[0]=[0.,90.,0.];rotations[1]=[0.,-90.,0.]
        if name=='single_bone':rotations[0]=[45.,0.,0.]
        for i in range(count):
            b=data.edit_bones.new('bone_%03d'%i);head=[0.,2. if name=='parent_chain' and i==1 else 1. if name=='distinct_rest' and i==1 else 0.,0.]
            b.head=head;b.tail=[head[0],head[1]+2,head[2]];heads.append(head)
            if name=='parent_chain' and i==1:b.parent=data.edit_bones['bone_000'];b.use_connect=True
        bpy.ops.object.mode_set(mode='OBJECT');rig.rotation_mode='XYZ'
        for i in range(count):b=rig.pose.bones['bone_%03d'%i];b.rotation_mode='XYZ';b.rotation_euler=[math.radians(v) for v in rotations[i]]
        vertices,faces=geometry(name in ('max_mesh','triangles257'),121 if name=='vertices129' else 0,name=='triangles257')
        if name in ('coordinate10','coordinate_over10'):
            for vertex in vertices:vertex[0]+=9.75 if name=='coordinate10' else 9.751
        if name=='original_quad':faces=[[0,1,2,3]]
        mesh=bpy.data.meshes.new('SkinData');mesh.from_pydata(vertices,[],faces);obj=bpy.data.objects.new('Skin',mesh);scene.collection.objects.link(obj)
        obj.rotation_mode='XYZ';groups=[obj.vertex_groups.new(name='bone_%03d'%i) for i in range(count)];weights=[]
        for i in range(len(vertices)):
            if name=='all_unweighted' or name=='unweighted' and i==0:values=[]
            elif name=='single_bone':values=[(0,1.)]
            elif name in ('influences8','influences9'):values=[(j,1./count) for j in range(count)]
            elif name=='unnormalized':values=[(0,.25),(1,.25)]
            elif name=='weights_02_08':values=[(0,.2),(1,.8)]
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
        world=dict(rig_deg=[20.,-15.,40.],rig_location=[1.,-2.,.5],mesh_deg=[-10.,30.,20.],mesh_location=[-1.,.3,.7]) if name=='world_offsets' else dict(rig_deg=[0.,0.,0.],rig_location=[0.,0.,0.],mesh_deg=[0.,0.,0.],mesh_location=[0.,0.,0.])
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
            parents=[None if name!='parent_chain' or i!=1 else 0 for i in range(count)],bones=count,world=world,
            unweighted=len(vertices) if name=='all_unweighted' else 1 if name=='unweighted' else 0,
            frame=dict(number=bpy.context.scene.frame_current,subframe=bpy.context.scene.frame_subframe),unit=.001 if name=='millimetres' else 1.,
            truth='authored geometry/rest/rotations/weights, independent NumPy replay and separate native propagated index marker')
        save(folder/'ORACLE.json',oracle);rows.append(dict(name=name,scene=str(path),scene_sha256=sha(path),oracle=oracle))
    save(args.output/'CASES.json',dict(rows=rows));print(json.dumps(dict(built=len(rows))))


def rotation(values):
    import numpy as np
    result=np.eye(4)
    for axis,deg in enumerate(values):
        a=math.radians(deg);c=math.cos(a);s=math.sin(a);m=np.eye(4);i,j=((1,2),(2,0),(0,1))[axis]
        m[i,i]=m[j,j]=c;m[i,j]=-s;m[j,i]=s;result=m@result
    return result


def independent_LBS(o):
    import numpy as np
    rest=[];pose=[];w=o['world'];rig=rotation(w['rig_deg']);rig[:3,3]=w['rig_location'];mesh=rotation(w['mesh_deg']);mesh[:3,3]=w['mesh_location']
    for i,head in enumerate(o['heads']):
        rm=np.eye(4);rm[:3,3]=head;basis=rotation(o['rotations_deg'][i]);parent=o['parents'][i]
        pm=rm@basis if parent is None else pose[parent]@np.linalg.inv(rest[parent])@rm@basis;rest.append(rm);pose.append(pm)
    bind=np.linalg.inv(rig)@mesh;unbind=np.linalg.inv(bind);result=[]
    for v,influences in zip(o['vertices'],o['weights']):
        if not influences:result.append(v);continue
        source=bind@np.array([*v,1.]);total=sum(weight for _,weight in influences)
        point=sum((weight/total)*(pose[group]@np.linalg.inv(rest[group])@source) for group,weight in influences)
        result.append((unbind@point)[:3].tolist())
    return np.array(result),mesh


def controller(args):
    import numpy as np
    sys.path.insert(0,str(args.core_root))
    if args.entry:
        spec=importlib.util.spec_from_file_location('_skin_fixed_target',args.entry.with_name('target_runtime_entry.py'));entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
        proof=entry.validate_binding(expected_python=sys.executable);assert Path(proof['module_root'])==args.core_root.resolve();entry.verify_imported_runtime(proof)
    from human_eye_plugin import skin_source as core
    from human_eye_plugin.skin_source_process import SkinSourceProcess
    from human_eye_plugin.runtime_identity import runtime_identity
    identity=runtime_identity();args.output.mkdir(exist_ok=False);binary=Path('D:/Tools/blender5.2/blender.exe');binary_sha=sha(binary);rows=[]
    for case in json.loads((args.fixtures/'CASES.json').read_bytes())['rows']:
        folder=args.output/case['name'];folder.mkdir();o=case['oracle'];profile=dict(schema='skin-source-operator-profile-v1',blender_executable=str(binary),blender_sha256=binary_sha,
            scene_file=case['scene'],scene_sha256=case['scene_sha256'],mesh_name='Skin',rig_name='Rig',expected_frame=o['frame'],runtime_source_sha256=identity['source_sha256'])
        save(folder/'PROFILE.json',profile);actor=None;report=None;first=None;second=None;error=None;started=time.perf_counter_ns()
        try:
            actor=SkinSourceProcess(folder/'PROFILE.json');first=actor.inspect();second=actor.inspect();report=core.analyze(second,deadline_ns=actor.deadline_ns)
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
        else:assert report is None and error and 'unsupported_' in error,(case['name'],report,error)
        assert sha(Path(case['scene']))==case['scene_sha256']
        row=dict(case=case['name'],supported=o['supported'],passed=True,first=first,second=second,report=report,error=error,elapsed_ns=time.perf_counter_ns()-started,
            original_file_unchanged=True);save(folder/'RESULT.json',row);rows.append(row);print(json.dumps(dict(case=case['name'],passed=True,supported=o['supported'])),flush=True)
    save(args.output/'RESULT.json',dict(cases=rows,total=len(rows),supported=sum(v['supported'] for v in rows),source_sha256=identity['source_sha256'],source_count=len(identity['source_files']),
        formal_model_trials=0,shared_GUI=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--builder',action='store_true');mode.add_argument('--controller',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures',type=Path);p.add_argument('--core-root',type=Path,default=ROOT);p.add_argument('--entry',type=Path)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:];args=p.parse_args(argv);builder(args) if args.builder else controller(args)
