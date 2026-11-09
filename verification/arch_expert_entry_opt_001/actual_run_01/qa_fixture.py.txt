"""Generated arm patch, isolated control and native oracle helpers for QA only."""
import gzip
import json
import math
from pathlib import Path
import socket
import sys
import time

STATE={}

def write(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def loaded():
    names=[]
    for name,module in tuple(sys.modules.items()):
        path=str(getattr(module,'__file__','')).replace('\\','/')
        if name=='numpy' or name.startswith('numpy.') or any(path.endswith('/'+part+'.py')
            for part in ('arm_twist_source','arm_twist_expert','arm_twist_weights')):
            names.append(name)
    return sorted(names)

def construct(root,fixture,spec_path):
    import bpy
    from mathutils import Matrix
    rows=json.loads(gzip.decompress((Path(root)/'verification/m6_arm_expert_001/run_01/dataset.json.gz').read_bytes()))
    initial=next(row for row in rows if len(row['packet']['bone_chain'])==2
        and row['metadata']['pose_family']=='anomalous_twist' and row['metadata']['angle_deg']==120.)
    alternatives=[row for row in rows if row['metadata']['asset_id']==initial['metadata']['asset_id']
        and row['metadata']['pose_family']=='anomalous_twist' and row['metadata']['angle_deg']!=120.]
    other=min(alternatives,key=lambda row:abs(row['metadata']['angle_deg']-60.))
    packet=initial['packet'];factor=4;sections=[];points=[];weights=[]
    for old_section in packet['sections']:
        section=[]
        for position,index in enumerate(old_section):
            next_index=old_section[(position+1)%len(old_section)]
            for sub in range(factor):
                ratio=sub/factor;section.append(len(points))
                points.append([(1-ratio)*a+ratio*b for a,b in zip(packet['rest_vertices'][index],packet['rest_vertices'][next_index])])
                weights.append([(1-ratio)*a+ratio*b for a,b in zip(packet['weights'][index],packet['weights'][next_index])])
        sections.append(section)
    cap_ids=[]
    for section in (sections[0],sections[-1]):
        cap_ids.append(len(points));points.append([sum(points[i][k] for i in section)/len(section) for k in range(3)])
        weights.append(list(weights[section[0]]))
    triangles=[]
    for left,right in zip(sections,sections[1:]):
        for j in range(len(left)):
            k=(j+1)%len(left);triangles.extend([[left[j],right[j],right[k]],[left[j],right[k],left[k]]])
    for j in range(len(sections[0])):
        k=(j+1)%len(sections[0]);triangles.extend([[cap_ids[0],sections[0][k],sections[0][j]],
            [cap_ids[1],sections[-1][j],sections[-1][k]]])
    ids=[20000+3*i for i in range(len(points))]
    all_points=[(100.+i*.0001,100.,100.) for i in range(ids[-1]+1)]
    padding_faces=[]
    for index in range(0,19998,3):
        x=100.+index*.0001
        all_points[index:index+3]=[(x,100.,100.),(x+.0001,100.001,100.),(x,100.,100.001)]
        padding_faces.append([index,index+1,index+2])
    for index,point in zip(ids,points):all_points[index]=point
    for obj in tuple(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
    all_faces=padding_faces+[[ids[i] for i in t] for t in triangles]
    data=bpy.data.meshes.new('QAArmMeshData');data.from_pydata(all_points,[],all_faces);data.update()
    mesh=bpy.data.objects.new('QAArmMesh',data);scene.collection.objects.link(mesh)
    rig_data=bpy.data.armatures.new('QARigData');rig=bpy.data.objects.new('QARig',rig_data);scene.collection.objects.link(rig)
    mesh.matrix_world=Matrix.Translation((5.,0.,0.));rig.matrix_world=Matrix.Translation((5.,0.,0.))
    bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    for row in packet['bone_chain']:
        bone=rig_data.edit_bones.new(row['name']);bone.head=(0.,0.,0.);bone.tail=(0.,.25,0.)
        if row['parent'] is not None:bone.parent=rig_data.edit_bones[row['parent']]
        bone.use_connect=False;bone.matrix=Matrix(row['rest_matrix']);bone.length=.25
    bpy.ops.object.mode_set(mode='OBJECT')
    for bone in rig_data.bones:
        bone.use_deform=True;bone.use_envelope_multiply=False;bone.bbone_segments=1;bone.inherit_scale='FULL'
    groups=[mesh.vertex_groups.new(name=bone['name']) for bone in packet['bone_chain']]
    for index,row in zip(ids,weights):
        for group,weight in zip(groups,row):
            if weight:group.add([index],float(weight),'REPLACE')
    modifier=mesh.modifiers.new('QAArmature','ARMATURE');modifier.object=rig
    for field,value in (('use_vertex_groups',True),('use_bone_envelopes',False),('use_deform_preserve_volume',False),
        ('use_multi_modifier',False),('invert_vertex_group',False),('vertex_group',''),('show_viewport',True),('show_render',True)):
        setattr(modifier,field,value)
    for row in packet['bone_chain']:
        rig.pose.bones[row['name']].matrix=Matrix(row['pose_matrix']);bpy.context.view_layer.update()
    def cube(name,center,half):
        vertices=[(x*half[0],y*half[1],z*half[2]) for x,y,z in
            ((-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),(1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1))]
        faces=[(0,2,3),(0,3,1),(4,5,7),(4,7,6),(0,1,5),(0,5,4),(2,6,7),(2,7,3),(0,4,6),(0,6,2),(1,3,7),(1,7,5)]
        value=bpy.data.meshes.new(name+'Data');value.from_pydata(vertices,[],faces);value.update()
        obj=bpy.data.objects.new(name,value);scene.collection.objects.link(obj);obj.location=center
    cube('BluePart',(0.,0.,.009),(.01,.01,.005));cube('GreyBase',(0.,0.,-.005),(.04,.04,.005))
    bpy.context.view_layer.update()
    selection=dict(mesh_name=mesh.name,armature_name=rig.name,bone_names=[b['name'] for b in packet['bone_chain']],
        vertex_indices=ids,sections=[[ids[i] for i in row] for row in sections])
    spec=dict(selection=selection,fixture=str(Path(fixture).resolve()),total_vertices=len(all_points),
        selected_vertices=len(ids),selected_triangles=len(triangles),total_triangles=len(all_faces),selection_bytes=len(json.dumps(selection,separators=(',',':')).encode()),
        initial_case=initial['metadata']['case_id'],pose_case=other['metadata']['case_id'],
        pose_matrices=[b['pose_matrix'] for b in other['packet']['bone_chain']],
        dataset_sha256=__import__('hashlib').sha256((Path(root)/'verification/m6_arm_expert_001/run_01/dataset.json.gz').read_bytes()).hexdigest())
    assert spec['selection_bytes']>16384,spec['selection_bytes']
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(fixture).resolve()));write(spec_path,spec)
    return spec

def configure(spec_path):STATE.update(json.loads(Path(spec_path).read_text(encoding='utf8')))

def control(value):
    import bpy
    from mathutils import Matrix
    op=value['op'];selection=STATE['selection']
    if op=='stats':return dict(pid=__import__('os').getpid(),loaded=loaded(),scene=bpy.context.scene.name,profile_none=sys.getprofile() is None)
    if op=='inspect':
        event=STATE['last_event'];folder=Path(STATE['observer_folder'])
        with (folder/'blender_events.jsonl').open('a',encoding='utf8') as stream:stream.write(json.dumps(event,ensure_ascii=False)+'\n')
        oracle=direct(STATE['host'],event['selection']);oracle_path=folder/('oracle_'+str(event['index'])+'.json')
        write(oracle_path,oracle)
        return dict(event=event,oracle_file=str(oracle_path),scope='separate verification request after tool RTT')
    if op=='unknown':
        rig=bpy.data.objects[selection['armature_name']]
        rig.pose.bones[selection['bone_names'][0]].matrix=rig.data.bones[selection['bone_names'][0]].matrix_local.copy()
        bpy.context.view_layer.update()
        name=selection['bone_names'][1]
        rig.pose.bones[name].matrix=rig.data.bones[name].matrix_local @ Matrix.Diagonal((1.,-1.,-1.,1.))
        bpy.context.view_layer.update()
        return dict(ok=True,op=op,profile_none=sys.getprofile() is None)
    if op=='ordinary_scene':
        for name in (selection['mesh_name'],selection['armature_name']):
            obj=bpy.data.objects[name]
            if bpy.context.scene.objects.get(name) is not None:bpy.context.scene.collection.objects.unlink(obj)
        bpy.context.view_layer.update()
    elif op=='expert_scene':
        for name in (selection['armature_name'],selection['mesh_name']):
            if bpy.context.scene.objects.get(name) is None:bpy.context.scene.collection.objects.link(bpy.data.objects[name])
        bpy.context.view_layer.update()
    elif op=='pose':
        rig=bpy.data.objects[selection['armature_name']]
        for name,matrix in zip(selection['bone_names'],STATE['pose_matrices']):
            rig.pose.bones[name].matrix=Matrix(matrix);bpy.context.view_layer.update()
    elif op=='static':
        mesh=bpy.data.objects[selection['mesh_name']]
        for index in selection['vertex_indices']:mesh.data.vertices[index].co*=1.001
        mesh.data.update();bpy.context.view_layer.update()
    elif op=='unsupported':
        bpy.data.objects[selection['mesh_name']].modifiers[0].use_deform_preserve_volume=True;bpy.context.view_layer.update()
    elif op=='restore':
        bpy.data.objects[selection['mesh_name']].modifiers[0].use_deform_preserve_volume=False;bpy.context.view_layer.update()
    elif op=='load':bpy.ops.wm.open_mainfile(filepath=STATE['fixture'])
    else:raise ValueError('Unknown isolated QA control: '+op)
    return dict(ok=True,op=op,loaded=loaded(),scene=bpy.context.scene.name)

def direct(host,selection):
    """Independent RNA input construction; same already-loaded model instance."""
    import bpy
    import importlib
    module=host._arm_twist_module
    expert=importlib.import_module(module.__package__+'.arm_twist_expert')
    np=expert.np;mesh=bpy.context.scene.objects[selection['mesh_name']];rig=bpy.context.scene.objects[selection['armature_name']]
    graph=bpy.context.evaluated_depsgraph_get();em=mesh.evaluated_get(graph);er=rig.evaluated_get(graph)
    scale=float(bpy.context.scene.unit_settings.scale_length)
    relative=np.linalg.inv(np.asarray(rig.matrix_world,dtype=float))@np.asarray(mesh.matrix_world,dtype=float)
    current_relative=np.linalg.inv(np.asarray(er.matrix_world,dtype=float))@np.asarray(em.matrix_world,dtype=float)
    ids=selection.get('vertex_indices') or sorted({i for row in selection['sections'] for i in row});local={index:i for i,index in enumerate(ids)};selected=set(ids)
    def point(matrix,value):return ((matrix@np.r_[np.asarray(value,dtype=float),1.])[:3]*scale).tolist()
    def metre(value):
        matrix=np.asarray(value,dtype=float).copy();matrix[:3,3]*=scale;return matrix.tolist()
    bones=selection['bone_names'];weights=[]
    for index in ids:
        row=[0.]*len(bones)
        for member in mesh.data.vertices[index].groups:
            name=mesh.vertex_groups[member.group].name
            if name in bones:row[bones.index(name)]+=float(member.weight)
        total=math.fsum(row);weights.append([value/total for value in row])
    triangles=[]
    for poly in mesh.data.polygons:
        face=list(poly.vertices)
        if all(index in selected for index in face):
            assert len(face)==3;triangles.append([local[index] for index in face])
    packet=dict(schema='arm-twist-patch-v1',unit='m',vertex_ids=ids,
        rest_vertices=[point(relative,mesh.data.vertices[i].co) for i in ids],
        current_vertices=[point(current_relative,em.data.vertices[i].co) for i in ids],weights=weights,triangles=triangles,
        sections=[[local[i] for i in section] for section in selection['sections']],bone_chain=[dict(name=name,
            parent=bones[i-1] if i else None,rest_matrix=metre(rig.data.bones[name].matrix_local),
            pose_matrix=metre(er.pose.bones[name].matrix)) for i,name in enumerate(bones)])
    model=expert.get_default_expert();report=model.predict(packet)
    return dict(report=report,packet=packet,model_identity=id(model),expert_module=expert.__name__,
        basis='direct native RNA selected original/evaluated vertices, vertex groups and bone matrices; same default model')

def main():
    import bpy
    args=sys.argv[sys.argv.index('--')+1:]
    mode=args[0]
    if mode=='create':construct(Path(args[1]),Path(args[2]),Path(args[3]));return
    if mode!='serve':raise ValueError(mode)
    configure(args[1]);ready=Path(args[2])
    observer={'__name__':'expert_qa_observer','__file__':str(Path(__file__).with_name('qa_observer.py'))}
    exec(compile(Path(observer['__file__']).read_bytes(),observer['__file__'],'exec'),observer)
    controller=observer['install'](args[3],args[1],owned=False)
    server=socket.socket();server.bind(('127.0.0.1',0));server.listen()
    write(ready,dict(port=server.getsockname()[1],pid=__import__('os').getpid()))
    while True:
        connection,_=server.accept()
        with connection:
            raw=bytearray()
            while True:
                block=connection.recv(65536)
                if not block:raise EOFError('QA fixture request ended')
                raw.extend(block)
                try:request=json.loads(raw);break
                except json.JSONDecodeError:pass
            try:
                if request['type']=='test_control':response={'control':controller(request['params'])}
                else:
                    import io,contextlib
                    output=io.StringIO()
                    with contextlib.redirect_stdout(output):exec(request['params']['code'],{'bpy':bpy})
                    response={'status':'success','result':{'executed':True,'result':output.getvalue()}}
            except Exception as exc:response={'status':'error','message':repr(exc)}
            connection.sendall(json.dumps(response,allow_nan=False).encode('utf8'))

if __name__=='__main__':main()
