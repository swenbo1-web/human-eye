"""Parameter matrix for M3, separate analytic/bundled/external provenance."""
import math

UPSTREAM_COMMIT='8f492390ddc7a2ae221a1369ef560589cf8c70fb'
UPSTREAM_SHA256={
    'Avocado':'ccc9c3ce56423720b09399c2351537207cd5a65f859f9e6e2f30922762f3abd4',
    'Lantern':'a79458c4b02d695187a952f23a63b8bf278e7bc3d316a3c2a314f2d6974181f1',
    'BoomBox':'f8b918445ebdd006768232205a62f5182d2208ca57f84c6ccc084943c0bc8f15'}


def cases(external_directory=None):
    rows=[dict(id='suzanne',kind='suzanne',subdivisions=0),
          dict(id='suzanne_subdiv1',kind='suzanne',subdivisions=1),
          dict(id='suzanne_subdiv2',kind='suzanne',subdivisions=2),
          dict(id='suzanne_over_source_limit',kind='suzanne',subdivisions=3),
          dict(id='coiled_tube_loose',kind='tube',rings=64,sides=12,pitch=.10),
          dict(id='coiled_tube_tight',kind='tube',rings=96,sides=12,pitch=.01),
          dict(id='coiled_tube_dense',kind='tube',rings=256,sides=32,pitch=.04),
          dict(id='intersecting_icospheres',kind='intersecting_spheres'),
          dict(id='parallel_sheets',kind='sheet',n=9,parallel_gap=.000005),
          dict(id='dented_sheet',kind='sheet',n=17,dent=.002),
          dict(id='cracked_sheet',kind='sheet',n=17,crack=True),
          dict(id='unapplied_modifier',kind='suzanne',subdivisions=0,modifier=True),
          dict(id='millimetre_units',kind='suzanne',subdivisions=0,unit_scale=.001),
          dict(id='far_origin',kind='suzanne',subdivisions=0,translation=[1e6,-1e6,1e6]),
          dict(id='singular_transform',kind='suzanne',subdivisions=0,scale=[0.,1.,1.]),
          dict(id='transform_locks',kind='suzanne',subdivisions=0,locked=True)]
    for row in rows:
        row['provenance']='Blender_builtin' if row['kind']=='suzanne' else 'owned_analytic_fixture'
        row['semantic_damage_truth']='not_inferred_from_structural_facts'
    if external_directory is not None:
        from pathlib import Path
        for model in ('Avocado','Lantern','BoomBox'):
            rows.append(dict(id='external_'+model,kind='external_glb',model=model,
                path=str(Path(external_directory)/(model+'.glb')),provenance='external_Khronos_CC0',
                semantic_damage_truth='unknown',working_units='declared_glTF_metre_convention_not_physical_scan_calibration'))
    return rows


def tube(rings,sides,pitch):
    vertices=[];turns=3;major=.10;minor=.015
    for i in range(rings):
        u=i/(rings-1);angle=turns*2*math.pi*u
        center=[major*math.cos(angle),major*math.sin(angle),pitch*turns*u]
        tangent=[-major*math.sin(angle)*turns*2*math.pi,major*math.cos(angle)*turns*2*math.pi,pitch*turns]
        length=math.sqrt(sum(x*x for x in tangent));tangent=[x/length for x in tangent]
        normal=[math.cos(angle),math.sin(angle),0.]
        binormal=[tangent[1]*normal[2]-tangent[2]*normal[1],tangent[2]*normal[0]-tangent[0]*normal[2],tangent[0]*normal[1]-tangent[1]*normal[0]]
        for j in range(sides):
            a=j*2*math.pi/sides
            vertices.append([center[k]+minor*(math.cos(a)*normal[k]+math.sin(a)*binormal[k]) for k in range(3)])
    faces=[[i*sides+j,i*sides+(j+1)%sides,(i+1)*sides+(j+1)%sides,(i+1)*sides+j]
           for i in range(rings-1) for j in range(sides)]
    faces += [list(reversed(range(sides))),[(rings-1)*sides+j for j in range(sides)]]
    return vertices,faces


def sheet(n,*,dent=0.,crack=False,parallel_gap=None):
    vertices=[]
    for j in range(n):
        for i in range(n):
            x=(i/(n-1)-.5)*.20;y=(j/(n-1)-.5)*.20
            z=-dent*math.exp(-(x*x+y*y)/(.025**2))
            vertices.append([x,y,z])
    faces=[[j*n+i,j*n+i+1,(j+1)*n+i+1,(j+1)*n+i] for j in range(n-1) for i in range(n-1)
           if not (crack and i==n//2 and j in (n//2-1,n//2))]
    if parallel_gap is not None:
        count=len(vertices);vertices += [[x,y,z+parallel_gap] for x,y,z in vertices]
        faces += [[v+count for v in p] for p in faces]
    return vertices,faces


def build(bpy,case):
    """Only called after factory reset in an owned background process."""
    assert bpy.app.background
    if case['kind']=='external_glb':
        from pathlib import Path
        import hashlib
        with Path(case['path']).open('rb') as stream:blob=stream.read(32*1024*1024+1)
        assert len(blob)<=32*1024*1024 and hashlib.sha256(blob).hexdigest()==UPSTREAM_SHA256[case['model']], 'unverified upstream asset'
        bpy.ops.import_scene.gltf(filepath=case['path'])
    elif case['kind']=='suzanne':
        bpy.ops.mesh.primitive_monkey_add();obj=bpy.context.object;obj.name='M3Asset'
        if case.get('subdivisions'):
            mod=obj.modifiers.new('FixtureAppliedSubdivision','SUBSURF');mod.levels=case['subdivisions']
            bpy.ops.object.modifier_apply(modifier=mod.name)
        if case.get('modifier'):
            mod=obj.modifiers.new('IntentionalUnappliedModifier','SUBSURF');mod.levels=1
    elif case['kind']=='intersecting_spheres':
        vertices=[];faces=[]
        for x in (-.06,.06):
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=.10)
            obj=bpy.context.object;offset=len(vertices)
            vertices += [[v.co.x+x,v.co.y,v.co.z] for v in obj.data.vertices]
            faces += [[offset+i for i in p.vertices] for p in obj.data.polygons]
            bpy.data.objects.remove(obj,do_unlink=True)
        mesh=bpy.data.meshes.new('M3Asset_mesh');mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new('M3Asset',mesh);bpy.context.scene.collection.objects.link(obj)
    else:
        if case['kind']=='tube':vertices,faces=tube(case['rings'],case['sides'],case['pitch'])
        else:vertices,faces=sheet(case['n'],dent=case.get('dent',0.),crack=case.get('crack',False),parallel_gap=case.get('parallel_gap'))
        mesh=bpy.data.meshes.new('M3Asset_mesh');mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new('M3Asset',mesh);bpy.context.scene.collection.objects.link(obj)
    meshes=sorted((o for o in bpy.context.scene.objects if o.type=='MESH'),key=lambda o:o.name)
    assert meshes
    for obj in meshes:
        if 'translation' in case:obj.location=case['translation']
        if 'scale' in case:obj.scale=case['scale']
        if case.get('locked'):obj.lock_location=[True]*3;obj.lock_rotation=[True]*3;obj.lock_scale=[True]*3
        obj.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0]
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=case.get('unit_scale',1.)
    bpy.context.view_layer.update()
    return meshes
