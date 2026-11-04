"""Six fixed VISUAL-BENEFIT-004A assets and analytic, non-HE references.

Freeze is pure Python. Blender build is explicit and only writes new owned
fixture files. No product imports, solver calls, live scene or model consumers.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,math,os,random,sys,time
from pathlib import Path

CYCLE='VISUAL-BENEFIT-004A'
SEED=20261104004
COLORS=dict(cyan=[.04,.72,.82,1.],orange=[.95,.34,.035,1.],purple=[.55,.12,.77,1.],
    yellow=[.93,.79,.035,1.],blue=[.035,.21,.82,1.],red=[.83,.035,.025,1.],
    green=[.035,.58,.19,1.],white=[.86,.86,.83,1.],gray=[.28,.30,.32,1.],
    dark=[.085,.09,.10,1.],brown=[.40,.21,.075,1.])
DEFAULT_OUTPUT=Path('D:/hefe/verification/fixes/20261104_visual_benefit004a/assets')

def need(value,reason):
    if not value:raise ValueError('visual004_assets_'+reason)
def blob(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
def digest(value):return hashlib.sha256(blob(value)).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(blob(value));stream.flush();os.fsync(stream.fileno())
    need(path.read_bytes()==blob(value),'write_readback')
def load(path):return json.loads(Path(path).read_bytes())

def box(lo,hi):
    vertices=[[lo[0],lo[1],lo[2]],[hi[0],lo[1],lo[2]],[hi[0],hi[1],lo[2]],[lo[0],hi[1],lo[2]],
        [lo[0],lo[1],hi[2]],[hi[0],lo[1],hi[2]],[hi[0],hi[1],hi[2]],[lo[0],hi[1],hi[2]]]
    return vertices,[[0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]]

def prism(points,lo,hi,plane='XY'):
    """Extrude one CCW, simple polygon; concave n-gons remain real mesh faces."""
    need(len(points)>=3 and hi>lo and plane in ('XY','XZ'),'prism')
    need(sum(points[i][0]*points[(i+1)%len(points)][1]-points[(i+1)%len(points)][0]*points[i][1]
        for i in range(len(points)))>0,'ccw_polygon')
    vertices=[[x,y,z] if plane=='XY' else [x,z,y] for z in (lo,hi) for x,y in points]
    n=len(points);faces=[list(reversed(range(n))),list(range(n,2*n))]
    faces.extend([[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)])
    if plane=='XZ':faces=[list(reversed(face)) for face in faces]
    return vertices,faces

def cylinder(center,radius,zlo,zhi,n=8,angle=0.):
    return prism([[center[0]+radius*math.cos(angle+2*math.pi*i/n),center[1]+radius*math.sin(angle+2*math.pi*i/n)]
        for i in range(n)],zlo,zhi)

def ring(center,inner_apothem,outer_apothem,zlo,zhi,n=16):
    vertices=[]
    for z in (zlo,zhi):
        for r in (outer_apothem/math.cos(math.pi/n),inner_apothem/math.cos(math.pi/n)):
            vertices.extend([[center[0]+r*math.cos((2*i+1)*math.pi/n),center[1]+r*math.sin((2*i+1)*math.pi/n),z] for i in range(n)])
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces.extend([[i,j,j+2*n,i+2*n],[i+n,i+3*n,j+3*n,j+n],
            [j,i,i+n,j+n],[i+2*n,j+2*n,j+3*n,i+3*n]])
    return vertices,faces

def closed_shell(outer_lo,outer_hi,inner_lo,inner_hi):
    v,f=box(outer_lo,outer_hi);inner,faces=box(inner_lo,inner_hi)
    return v+inner,f+[[index+len(v) for index in reversed(face)] for face in faces]

def u_outline(xlo,xhi,ylo,yhi,inner_left,inner_right,inner_bottom):
    return [[xlo,ylo],[xhi,ylo],[xhi,yhi],[inner_right,yhi],[inner_right,inner_bottom],
        [inner_left,inner_bottom],[inner_left,yhi],[xlo,yhi]]

def item(role,color,mesh,description):
    vertices,faces=mesh
    return dict(private_role=role,color=color,rgba=COLORS[color][:],vertices=vertices,faces=faces,
        private_descriptor=description)

def distractors(rng,count):
    positions=[[-1.6,-1.],[1.55,-1.],[-1.55,.8],[1.5,.8],[-.7,1.5],[.8,1.55],[-1.85,1.5],[1.9,1.5],[1.95,-.25]]
    colors=['cyan','orange','purple','yellow','blue','red','green','white','brown']
    out=[]
    for i,(x,y) in enumerate(positions[:count]):
        radius=.10+.025*(i%3);zlo=0.;zhi=.30+.09*(i%4)
        mesh=cylinder([x,y],radius,zlo,zhi,n=(6,8,4)[i%3],angle=rng.choice([0.,math.pi/8]))
        out.append(item('decoy_'+str(i),colors[(i+2)%len(colors)],mesh,'background faceted post'))
    return out

def fact(name,kind,value,*,tolerance=None,objects=(),region=None):
    name={'gap':'minimum_gap_m','region':'closest_region','opposite_gap':'opposite_gap_m',
        'center_direction':'centroid_direction','vertical_gap':'vertical_clearance_m',
        'not_euclidean':'vertical_is_not_euclidean','image_limit':'visual_visibility'}.get(name,name)
    result=dict(fact_id=name,kind=kind,value=value,object_roles=list(objects))
    if tolerance is not None:result['tolerance']=tolerance
    if region is not None:result['accepted_values']=[value,*region]
    elif kind=='target_to_reference_world_axis':result['accepted_values']=[value]
    elif kind in ('separation_class','pin_location_relative_to_hole'):result['accepted_values']=[value]
    return result

def cases():
    out=[]
    common=dict(units='metres',world_axes='right-handed XYZ, +Z up; directions are world axes, not screen left/right',
        identity='Report exact neutral Blender mesh object names after identifying them from geometry/color/context.',
        numerical_evidence='May read complete original geometry. Distinguish visual evidence from mesh-based numerical evidence.',
        scope='Read-only analysis; no object/mesh/frame edits or saves; temporary QA camera/view/render only.',
        answer_requirements=['identified object names and their roles','all requested spatial facts and local side/feature',
            'evidence modality actually used','uncertainty and visible/occluded limits; unknown is not false'])
    def add(case_id,stratum,question,objects,truth,camera=None):
        rng=random.Random(SEED+len(out))
        floor=item('floor','gray',box([-2.5,-1.8,-.06],[2.5,1.9,0.]),'ground slab')
        objects=[floor,*objects,*distractors(rng,7)]
        numbers=list(range(1,len(objects)+1));rng.shuffle(numbers)
        for obj,number in zip(objects,numbers):obj['name']='Object_'+str(number).zfill(2)
        roles={obj['private_role']:obj['name'] for obj in objects}
        required_roles=truth.pop('required_object_roles')
        truth['facts']={row['fact_id']:{k:v for k,v in row.items() if k!='fact_id'} for row in truth['facts']}
        truth.update(case_id=case_id,expected_objects={role:roles[role] for role in required_roles},
            identity_alternatives='exactly the named objects; no ties or interchangeable target objects',
            all_fact_ids_required=True,omission_standard='Every requested identity and fact is separately scored; omissions, wrong source objects, unsupported certainty and modality-inconsistent unknown are retained, never silently dropped.',
            uncertainty_scoring='unsupported assertions or silent omission fail that fact; honest image-only unknown remains safe but incomplete where full geometry can answer',
            reference_method='independent analytic frozen geometry/support planes, not Human Eye success or a product solver',
            position_tolerance_model='absolute metres, includes binary32 authored coordinate quantization; not physical metrology')
        truth['unknown_by_modality']=truth.pop('acceptable_unknown_by_modality',dict(
            external_images_only='unknown permitted when unresolved/occluded, but not a full geometric answer',
            complete_mesh='all requested geometry facts supported by this finite authored source'))
        public=dict(schema='visual004-public-task-v1',case_id=case_id,question=question,
            required_roles=required_roles,required_fact_ids=list(truth['facts']),**copy.deepcopy(common))
        spec=dict(schema='visual004-scene-spec-v1',case_id=case_id,stratum=stratum,seed=SEED+len(out),objects=objects,
            camera=camera or dict(position=[4.,-6.,4.2],target=[0.,0.,.65],ortho_scale=5.2),
            render=dict(engine='BLENDER_WORKBENCH',width=768,height=768,resolution_percentage=100,
                color_type='MATERIAL',transparent=False,format='PNG'),unit_scale_m=1.,frame=1,
            public=public,private_truth=truth)
        out.append(spec)

    L=[[-.45,-.25],[.3,-.25],[.3,-.1],[-.15,-.1],[-.15,.35],[-.45,.35]]
    U=u_outline(-.65,.55,-.45,.55,-.5,.3015,-.3)
    add('V01','occluded_local_center_hidden_edge_visible',
        '找到灰色挡板后仍露出边缘的青色L形件及其所在的橙色U形框。两者是否接触或穿插？最小净间隙是否小于2毫米，位于L件的哪个局部、朝哪个世界轴方向？量化间隙，并区分当前图中可见证据和被挡部分。',
        [item('target','cyan',prism(L,.45,.70),'cyan L-shaped solid'),item('reference','orange',prism(U,.40,.80),'orange U frame'),
         item('occluder','gray',box([-.12,-.68,.22],[.42,-.57,1.05]),'opaque frontal panel')],
        dict(required_object_roles=['target','reference','occluder'],facts=[
            fact('relation','separation_class','separated',objects=['target','reference']),
            fact('gap','minimum_surface_distance_m',.0015,tolerance=.00015,objects=['target','reference']),
            fact('direction','target_to_reference_world_axis','+X',objects=['target','reference']),
            fact('region','closest_local_region','right end of cyan short horizontal arm facing orange right inner wall',
                region=['L短横臂右端/右侧面','橙框右内壁对应短横臂端部'])],
            analytic_certificate=dict(closest_points=[[.3,-.175,.575],[.3015,-.175,.575]],normal=[1,0,0],
                competing_axis_clearances_m=dict(left=.05,bottom=.05)),image_only_limit='panel hides central/right patch; alternate view or full geometry needed for exact gap'),
        dict(position=[0.,-8.,1.8],target=[0.,0.,.60],ortho_scale=4.8))

    wedge=[[-.45,.35],[.45,.35],[.45,.80]]
    notch=[[-.35,.28],[.5,.28],[.5,.9],[.25,.9],[.25,.6],[-.08,.6],[-.08,.9],[-.35,.9]]
    add('V02','occluded_local_projected_overlap_not_contact',
        '检查灰色遮挡片后露出的紫色斜楔与黄色缺口立柱：画面中轮廓重叠是否代表实体接触或穿插？给出两者真实最小表面间隔、从斜楔到立柱的世界轴方向及对应局部面，并说明单张图仍不能确定什么。',
        [item('target','purple',prism(wedge,-.25,.20,'XZ'),'purple triangular wedge'),
         item('reference','yellow',prism(notch,.24,.42,'XZ'),'yellow notched upright'),
         item('occluder','gray',box([-.1,-.55,.2],[.42,-.44,.95]),'opaque frontal strip')],
        dict(required_object_roles=['target','reference','occluder'],facts=[
            fact('relation','separation_class','separated',objects=['target','reference']),
            fact('gap','minimum_surface_distance_m',.04,tolerance=.001,objects=['target','reference']),
            fact('direction','target_to_reference_world_axis','+Y',objects=['target','reference']),
            fact('region','closest_local_region','purple rear flat face to yellow front flat face',region=['紫楔后平面/黄色前平面','沿世界Y正方向的平行侧面'])],
            analytic_certificate=dict(closest_points=[[.15,.2,.45],[.15,.24,.45]],normal=[0,1,0]),
            image_only_limit='2D contour overlap is not 3D intersection; front view hides depth separation'),
        dict(position=[.25,-8.,1.7],target=[0.,0.,.58],ortho_scale=4.9))

    add('V03','multiobject_small_feature_annular_gap',
        '在多物体平台中，定位蓝色套环附近的红色短销。它实际位于孔内、孔外还是与环相交？是否接触内壁？报告最窄净间隙的毫米数、它位于孔的哪一侧，并指出该结论来自图像还是完整几何。',
        [item('target','red',cylinder([.412,.1],.075,.52,.70,16),'red short faceted pin'),
         item('reference','blue',ring([.4,.1],.09,.16,.50,.72,16),'blue polygonal annulus'),
         item('red_decoy','red',cylinder([.9,.65],.075,0.,.18,16),'another red short pin outside the ring'),
         item('support','white',box([.1,-.2,0.],[.7,.4,.50]),'small raised plinth')],
        dict(required_object_roles=['target','reference'],facts=[
            fact('containment','pin_location_relative_to_hole','inside_hole_without_contact',objects=['target','reference']),
            fact('relation','separation_class','separated',objects=['target','reference']),
            fact('gap','minimum_surface_distance_m',.003,tolerance=.00015,objects=['target','reference']),
            fact('direction','target_to_reference_world_axis','+X',objects=['target','reference'])],
            analytic_certificate=dict(closest_points=[[.487,.1,.60],[.49,.1,.60]],normal=[1,0,0],
                derivation='regular16-gon hole apothem .09 - pin support .075 - +X offset .012 = .003; all other wall supports give >.003',
                hole_wall_normals=[[math.cos(2*math.pi*i/16),math.sin(2*math.pi*i/16),0.] for i in range(16)],
                all_wall_support_clearances_m=[.09-.075-.012*math.cos(2*math.pi*i/16) for i in range(16)],
                all_minimizing_wall_indices=[0],contact_feature='pin +X vertex against ring +X inner face; continuous overlapping z in [.52,.70]'),
            image_only_limit='AABB overlap is not contact; a tiny apparent dark rim does not certify3mm'))

    add('V04','multiobject_microgap_two_sides',
        '找到白色八角柱周围的绿色U形支架。哪一侧内壁离柱最近，是否接触？量化该侧最小净间隙，并与相反侧的间隙比较。使用世界轴方向描述局部位置，不能把框的包围盒重叠误作实体穿插。',
        [item('target','white',cylinder([0.,0.],.10,.15,.90,8),'white octagonal post'),
         item('reference','green',prism(u_outline(-.32,.32,-.3,.33,-.1008,.104,-.13),.20,.80),'green U bracket'),
         item('support','brown',box([-.45,-.45,0.],[.45,.45,.15]),'base plate')],
        dict(required_object_roles=['target','reference'],facts=[
            fact('relation','separation_class','separated',objects=['target','reference']),
            fact('gap','minimum_surface_distance_m',.0008,tolerance=.00010,objects=['target','reference']),
            fact('direction','target_to_reference_world_axis','-X',objects=['target','reference']),
            fact('opposite_gap','opposite_side_clearance_m',.004,tolerance=.00015,objects=['target','reference'])],
            analytic_certificate=dict(closest_points=[[-.1,0.,.5],[-.1008,0.,.5]],normal=[-1,0,0],
                competing_axis_clearances_m=dict(right=.004,bottom=.03),
                derivation='Each octagon vertex lies strictly inside the U cavity. Compare all8 octagon edges against all8 U-outline edges; unique closest U boundary is x=-.1008, reached from octagon x=-.1 vertex with overlapping extrusion z.',
                all_minimizing_U_outline_edge_indices=[5],contact_feature='white -X vertex to green left inner wall; continuous overlapping z in [.20,.80]'),
            image_only_limit='submillimetre contact claim requires sufficient resolved evidence or complete geometry'))

    add('V05','overview_sufficient_no_local_detail_required',
        '从全景定位橙色三角楔、紫色八角柱和青色斜梁。按完整几何包围盒中心，橙楔相对紫柱在世界X/Y/Z各轴哪一侧？橙楔最高处到青梁最低处的竖直净空是多少？说明这个竖直量是否等于两者最短三维距离、是否可单凭它判断接触。',
        [item('target','orange',prism([[0.,0.],[.4,0.],[.4,.4]],-1.,-.6,'XZ'),'orange triangular wedge'),
         item('reference','purple',cylinder([-1.,0.],.15,0.,1.3,8),'purple octagonal post'),
         item('third','cyan',prism([[.65,.95],[1.35,1.10],[1.35,1.35],[.65,1.20]],.45,.8,'XZ'),'cyan sloping beam'),
         item('support','white',box([1.05,.45,0.],[1.25,.8,1.10]),'beam support')],
        dict(required_object_roles=['target','reference','third'],facts=[
            fact('center_direction','aabb_center_direction_xyz',['+X','-Y','-Z'],objects=['target','reference']),
            fact('vertical_gap','vertical_clearance_m',.55,tolerance=.002,objects=['target','third']),
            fact('not_euclidean','vertical_is_not_minimum_3d_distance',True,objects=['target','third'])],
            analytic_certificate=dict(target_aabb_center=[.2,-.8,.2],reference_aabb_center=[-1.,0.,.65],
                target_top_z=.4,third_bottom_z=.95,xy_disjoint=True),
            image_only_limit='overview provides broad relations; world-axis signs still require axis orientation or coordinate evidence'))

    add('V06','fully_occluded_local_view_no_visible_gain',
        '深灰色封闭壳体内有橙色六角内芯。内芯与壳内壁接触、穿插还是分离？最窄间隙在哪一侧、是多少？请分别说明外部图像可以支持的结论，以及读取完整内部几何后可以支持的结论；不要把“看不见”直接当作不存在或已知相离。',
        [item('target','orange',cylinder([.1,0.],.38,.25,.75,6),'orange internal hexagonal core'),
         item('reference','dark',closed_shell([-.65,-.65,0.],[.65,.65,1.],[-.5,-.5,.2],[.5,.5,.8]),'closed opaque hollow shell'),
         item('orange_decoy','orange',cylinder([1.3,-.55],.12,0.,.4,8),'external orange octagonal decoy')],
        dict(required_object_roles=['target','reference'],facts=[
            fact('relation','separation_class','separated',objects=['target','reference']),
            fact('gap','minimum_surface_distance_m',.02,tolerance=.001,objects=['target','reference']),
            fact('direction','target_to_reference_world_axis','+X',objects=['target','reference']),
            fact('image_limit','internal_surface_not_visible_from_external_opaque_view',True,objects=['target','reference'])],
            analytic_certificate=dict(closest_points=[[.48,0.,.5],[.5,0.,.5]],normal=[1,0,0],
                other_clearances_m=dict(left=.22,top=.05,bottom=.05,y_wall=.5-.38*math.sin(math.pi/3))),
            acceptable_unknown_by_modality=dict(external_images_only=dict(relation='unknown',gap=None,full_answer=False),
                complete_mesh=dict(relation='separated',gap_m=.02,full_answer=True)),
            image_only_limit='closed opaque shell fully encloses target; outside camera zoom alone cannot reveal its internal surfaces'))
    return out

def calibration_spec():
    return dict(schema='visual004-neutral-calibration-scene-v1',case_id='calibration',
        objects=[dict(item('floor','gray',box([-1.7,-1.3,-.04],[1.7,1.3,0.]),'ground'),name='Object_01'),
            dict(item('shape_a','red',box([-.9,-.2,0.],[-.5,.2,.45]),'simple block'),name='Object_02'),
            dict(item('shape_b','blue',cylinder([0.,.1],.25,0.,.6,8),'simple octagonal post'),name='Object_03'),
            dict(item('shape_c','green',prism([[.45,0.],[1.05,0.],[.8,.6]],-.2,.2,'XZ'),'simple triangle'),name='Object_04')],
        camera=dict(position=[3.5,-5.,3.5],target=[0.,0.,.25],ortho_scale=3.5),
        render=dict(engine='BLENDER_WORKBENCH',width=768,height=768,resolution_percentage=100,color_type='MATERIAL',transparent=False,format='PNG'),
        scope='transport/viewport calibration only, no task, no target pair or solver, not one of six formal cases')

def freeze(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    spec=cases();members=[]
    for case in spec:
        folder=output/case['case_id']
        for name,value in [('SCENE_SPEC.json',case),('PUBLIC_TASK.json',case['public']),('PRIVATE_TRUTH.json',case['private_truth'])]:
            path=folder/name;save(path,value);members.append(dict(path=path.relative_to(output).as_posix(),sha256=sha(path),bytes=path.stat().st_size))
    path=output/'calibration/SCENE_SPEC.json';save(path,calibration_spec())
    members.append(dict(path=path.relative_to(output).as_posix(),sha256=sha(path),bytes=path.stat().st_size))
    package=dict(schema='visual004-six-case-frozen-package-v1',cycle_id=CYCLE,seed=SEED,
        case_ids=[case['case_id'] for case in spec],calibration_case_id='calibration',members=members,
        source_script_sha256=sha(Path(__file__)),product_used_for_reference=False,
        supported_check_or_formal_results_used_to_choose_assets=False)
    save(output/'CASESET_SPEC.json',package)
    save(output/'SPEC_SEAL.json',dict(schema='visual004-case-spec-seal-v1',sha256=sha(output/'CASESET_SPEC.json'),
        bytes=(output/'CASESET_SPEC.json').stat().st_size,immutable_before_support_checks=True))
    return package

def verify(output):
    output=Path(output).resolve();seal=load(output/'SPEC_SEAL.json')
    need(sha(output/'CASESET_SPEC.json')==seal['sha256'],'case_spec_seal')
    package=load(output/'CASESET_SPEC.json')
    need(sha(Path(__file__))==package['source_script_sha256'],'generator_changed_after_freeze')
    for member in package['members']:
        path=output/member['path'];need(sha(path)==member['sha256'] and path.stat().st_size==member['bytes'],'case_member_changed')
    return package

def build_all(output):
    """Execute only inside a new background Blender; preserve every failure."""
    import bpy
    from mathutils import Vector
    output=Path(output).resolve();package=verify(output)
    need(output.is_relative_to(DEFAULT_OUTPUT.parent.resolve()),'owned_output_root')
    need(not (output/'BUILD_RESULT.json').exists() and not (output/'BUILD_ATTEMPT.json').exists(),'single_build_attempt')
    started=time.perf_counter_ns();save(output/'BUILD_ATTEMPT.json',dict(cycle_id=CYCLE,started_ns=started,case_ids=package['case_ids']))
    built=[]
    try:
        for case_id in [package['calibration_case_id'],*package['case_ids']]:
            phase=time.perf_counter_ns();folder=output/case_id;spec=load(folder/'SCENE_SPEC.json')
            need(not (folder/'scene.blend').exists() and not (folder/'initial.png').exists(),'asset_already_exists')
            bpy.ops.wm.read_factory_settings(use_empty=True)
            scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.;scene.frame_set(1)
            for record in spec['objects']:
                mesh=bpy.data.meshes.new('Mesh_'+record['name']);mesh.from_pydata(record['vertices'],[],record['faces']);mesh.update()
                obj=bpy.data.objects.new(record['name'],mesh);scene.collection.objects.link(obj)
                material=bpy.data.materials.new('Material_'+record['name']);material.diffuse_color=record['rgba'];obj.data.materials.append(material)
            camera_data=bpy.data.cameras.new('CameraData');camera=bpy.data.objects.new('Camera_01',camera_data);scene.collection.objects.link(camera)
            camera.location=spec['camera']['position'];direction=Vector(spec['camera']['target'])-camera.location
            camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler();camera_data.type='ORTHO';camera_data.ortho_scale=spec['camera']['ortho_scale']
            camera_data.clip_start=.01;camera_data.clip_end=100.;scene.camera=camera
            scene.render.engine=spec['render']['engine'];scene.render.resolution_x=768;scene.render.resolution_y=768;scene.render.resolution_percentage=100
            scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
            scene.world=bpy.data.worlds.new('World');scene.world.color=(.055,.055,.065)
            scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=True
            scene.display.shading.show_cavity=True;scene.display.shading.cavity_type='BOTH';scene.display.shading.show_object_outline=True
            scene.display.shading.background_type='WORLD';scene.view_settings.view_transform='Standard'
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type=='VIEW_3D':area.spaces.active.region_3d.view_perspective='CAMERA'
            scene.render.filepath=str(folder/'initial.png')
            bpy.ops.wm.save_as_mainfile(filepath=str(folder/'scene.blend'),check_existing=False)
            bpy.ops.render.render(write_still=True)
            actual={obj.name:obj for obj in scene.objects if obj.type=='MESH'}
            need(set(actual)=={record['name'] for record in spec['objects']},'saved_mesh_names')
            max_error=0.
            for record in spec['objects']:
                obj=actual[record['name']];need(len(obj.data.vertices)==len(record['vertices']),'saved_mesh_vertices')
                for got,want in zip(obj.data.vertices,record['vertices']):max_error=max(max_error,max(abs(float(got.co[k])-want[k]) for k in range(3)))
            need(max_error<=2e-7,'binary32_coordinate_bound')
            built.append(dict(case_id=case_id,scene_sha256=sha(folder/'scene.blend'),initial_png_sha256=sha(folder/'initial.png'),
                initial_dimensions=[768,768],mesh_objects=len(actual),vertices=sum(len(o.data.vertices) for o in actual.values()),
                measured_max_coordinate_rounding_m=max_error,complete_build_render_ns=time.perf_counter_ns()-phase,
                geometry_setters_scope='initial fixture creation only; formal consumers analysis-only',original_user_asset_reads=0))
        verify(output);save(output/'BUILD_RESULT.json',dict(cycle_id=CYCLE,passed=True,
            cases=[row for row in built if row['case_id']!='calibration'],calibration=next(row for row in built if row['case_id']=='calibration'),
            complete_build_wall_ns=time.perf_counter_ns()-started,product_calls=0,model_consumers=0,source_spec_sha256=sha(output/'CASESET_SPEC.json')))
    except BaseException as exc:
        save(output/'BUILD_FAILURE.json',dict(cycle_id=CYCLE,type=type(exc).__name__,reason=str(exc),built=built,
            complete_wall_ns=time.perf_counter_ns()-started,no_automatic_retry=True));raise

def main():
    argslist=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--freeze',action='store_true');group.add_argument('--verify',action='store_true');group.add_argument('--build-all',action='store_true')
    args=parser.parse_args(argslist)
    if args.freeze:result=freeze(args.output);print(json.dumps(dict(frozen=True,cases=result['case_ids'],spec_sha256=sha(args.output/'CASESET_SPEC.json'))))
    elif args.verify:result=verify(args.output);print(json.dumps(dict(verified=True,cases=result['case_ids'])))
    else:build_all(args.output)

if __name__=='__main__':main()
