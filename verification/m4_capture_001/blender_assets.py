"""Future exclusive-window disposable scenes. Not executed in offline batch."""
import hashlib
import json

KEY = '_human_eye_m4_capture_001_assets'
CASES = ('peripheral', 'all_overlap', 'equal_ties', 'zero', 'rotated_nonuniform',
         'large_offset_units', 'isolated_vertex', 'degenerate', 'unsupported_modifier')


def original_state(bpy, scene):
    return {'scene': scene.name, 'frame': scene.frame_current,
            'scale_length': scene.unit_settings.scale_length,
            'filepath': bpy.data.filepath,
            'objects': {str(o.session_uid): {'name': o.name, 'matrix': [list(r) for r in o.matrix_world]}
                        for o in scene.objects}}


def setup(case, host_source_path, expected_host_source_sha256):
    import bpy
    from pathlib import Path
    import types
    from mathutils import Matrix
    if case not in CASES or bpy.context.window is None or KEY in bpy.app.driver_namespace:
        raise RuntimeError('fixture_not_available')
    old = bpy.context.window.scene
    state = {'original': old, 'before': original_state(bpy, old), 'objects': [], 'meshes': []}
    bpy.app.driver_namespace[KEY] = state
    scene = bpy.data.scenes.new('HumanEye_M4_001_' + case)
    state['scene'] = scene
    bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.
    scene.frame_set(1)

    def mesh(name, x, divisions=1, isolated=False, degenerate=False):
        if divisions == 1:
            vertices = [(0., 0., 0.), (0., 1., 0.), (0., 0. if degenerate else 1., 0. if degenerate else 1.)]
            # Non-degenerate triangle lies in the local YZ plane.
            if not degenerate: vertices[2] = (0., 0., 1.)
            faces = [(0, 1, 2)]
        else:
            vertices = [(0., y/divisions, z/divisions) for y in range(divisions+1) for z in range(divisions+1)]
            faces = []
            for y in range(divisions):
                for z in range(divisions):
                    a = y*(divisions+1)+z
                    faces.extend(((a, a+1, a+divisions+2), (a, a+divisions+2, a+divisions+1)))
        if isolated:
            vertices.insert(0, (-x, 0., 0.))
            faces = [tuple(i+1 for i in f) for f in faces]
        data = bpy.data.meshes.new(scene.name + '_' + name + '_mesh')
        state['meshes'].append(data)
        data.from_pydata(vertices, [], faces)
        data.update()
        obj = bpy.data.objects.new(name, data)
        state['objects'].append(obj)
        scene.collection.objects.link(obj)
        obj.matrix_world = Matrix.Translation((x, 0., 0.))
        return obj

    focal = mesh('M4_Focal', 0., degenerate=case == 'degenerate')
    near_x = 64. if case == 'large_offset_units' else .004
    mesh('M4_Near', 0. if case in {'all_overlap', 'zero'} else near_x)
    if case in {'equal_ties', 'all_overlap', 'zero'}:
        mesh('M4_Tie', 0. if case in {'all_overlap', 'zero'} else near_x)
    count = 12 if case == 'peripheral' else 3
    for i in range(count):
        mesh('M4_Far_%02d' % i, 0. if case == 'all_overlap' else (4096.+i*64 if case == 'large_offset_units' else 1.+i),
             divisions=16 if case == 'peripheral' else 1,
             isolated=case == 'isolated_vertex' and i == 0)
    if case == 'rotated_nonuniform':
        transform = Matrix(((0., -3., .125, 8.), (2., 0., .5, -4.), (.25, 0., .75, 16.), (0., 0., 0., 1.)))
        for obj in state['objects']: obj.matrix_world = transform @ obj.matrix_world
    if case == 'large_offset_units':
        scene.unit_settings.scale_length = 1e-6
        transform = Matrix.Translation((2.**28, -2.**28, 2.**28))
        for obj in state['objects']: obj.matrix_world = transform @ obj.matrix_world
    if case == 'unsupported_modifier':
        state['objects'][-1].modifiers.new('UnsupportedInCandidate', 'BEVEL')
    bpy.context.view_layer.objects.active = focal
    bpy.context.view_layer.update()
    asset = {'case': case, 'scale_length': scene.unit_settings.scale_length,
        'objects': [{'name': o.name, 'matrix': [list(r) for r in o.matrix_world],
                     'vertices': [list(v.co) for v in o.data.vertices],
                     'polygons': [list(p.vertices) for p in o.data.polygons]} for o in state['objects']]}
    host_blob = Path(host_source_path).read_bytes()
    if hashlib.sha256(host_blob).hexdigest() != expected_host_source_sha256:
        raise RuntimeError('fixture_host_source_changed')
    host_module = types.ModuleType('m4_fixture_object_binding')
    exec(compile(host_blob, host_source_path, 'exec'), host_module.__dict__)
    return {'case': case, 'focal_name': focal.name,
            'focal_id': host_module.BlenderSceneHost.object_id(focal), 'blender_version': bpy.app.version_string,
            'asset_sha256': hashlib.sha256(json.dumps(asset, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'objects': len(state['objects']), 'fixture_only_writes': True, 'file_saved': False}


def cleanup():
    import bpy
    state = bpy.app.driver_namespace.get(KEY)
    if state is None:
        return {'no_fixture': True, 'file_saved': False}
    bpy.context.window.scene = state['original']
    after = original_state(bpy, state['original'])
    for obj in state['objects']: bpy.data.objects.remove(obj, do_unlink=True)
    for data in state['meshes']:
        if data.users == 0: bpy.data.meshes.remove(data)
    if 'scene' in state: bpy.data.scenes.remove(state['scene'])
    bpy.app.driver_namespace.pop(KEY)
    if after != state['before']:
        raise RuntimeError('original_scene_metadata_changed')
    return {'original_scene_metadata_equal': True, 'fixture_removed': True, 'file_saved': False,
            'original_mesh_contents_independently_hashed': False}
