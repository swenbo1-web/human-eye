"""One owned --factory-startup --background process, no user asset loads."""
import hashlib
import json
from pathlib import Path
import sys

CASES = ('peripheral', 'all_overlap', 'equal_ties', 'zero', 'rotated_nonuniform',
         'large_offset_units', 'isolated_vertex', 'degenerate', 'unsupported_modifier',
         'far_second_degenerate', 'loose_first_vertex')


def main():
    import bpy
    from mathutils import Matrix
    out = Path(sys.argv[sys.argv.index('--')+1]).resolve()
    out.mkdir(exist_ok=False)
    rows = []
    for case in CASES:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.unit_settings.system = 'METRIC'
        scene.unit_settings.scale_length = 1.
        scene.frame_set(1)
        objects = []
        def mesh(name, x=0., divisions=1, isolated=False, degenerate=False, custom=None, faces=None):
            if custom is not None:
                vertices = custom
            elif divisions == 1:
                vertices = [(0., 0., 0.), (0., 1., 0.), (0., 0., 0.) if degenerate else (0., 0., 1.)]
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
            data = bpy.data.meshes.new(name+'_mesh')
            data.from_pydata(vertices, [], faces)
            data.update()
            obj = bpy.data.objects.new(name, data)
            scene.collection.objects.link(obj)
            obj.matrix_world = Matrix.Translation((x, 0., 0.))
            objects.append(obj)
            return obj
        focal = mesh('M4_Focal', degenerate=case == 'degenerate')
        if case == 'far_second_degenerate':
            mesh('M4_Near', 2.)
            mesh('M4_Far_00', custom=[(100., 0., 0.), (100., 1., 0.), (100., 0., 1.),
                (100., 2., 0.), (100., 3., 0.), (100., 4., 0.)], faces=[(0, 1, 2), (3, 4, 5)])
        elif case == 'loose_first_vertex':
            mesh('M4_Near', custom=[(10., 0., 0.), (.01, 1., 0.), (.01, 0., 1.)], faces=[(0, 1, 2)])
            mesh('M4_Far_00', 2.)
        else:
            near_x = 64. if case == 'large_offset_units' else .004
            mesh('M4_Near', 0. if case in {'all_overlap', 'zero'} else near_x)
            if case in {'equal_ties', 'all_overlap', 'zero'}:
                mesh('M4_Tie', 0. if case in {'all_overlap', 'zero'} else near_x)
            for i in range(12 if case == 'peripheral' else 3):
                mesh('M4_Far_%02d' % i, 0. if case == 'all_overlap' else (4096.+i*64 if case == 'large_offset_units' else 1.+i),
                     divisions=16 if case == 'peripheral' else 1,
                     isolated=case == 'isolated_vertex' and i == 0)
            if case == 'rotated_nonuniform':
                transform = Matrix(((0., -3., .125, 8.), (2., 0., .5, -4.), (.25, 0., .75, 16.), (0., 0., 0., 1.)))
                for obj in objects: obj.matrix_world = transform @ obj.matrix_world
            if case == 'large_offset_units':
                scene.unit_settings.scale_length = 1e-6
                transform = Matrix.Translation((2.**28, -2.**28, 2.**28))
                for obj in objects: obj.matrix_world = transform @ obj.matrix_world
            if case == 'unsupported_modifier': objects[-1].modifiers.new('UnsupportedInCandidate', 'BEVEL')
        bpy.context.view_layer.objects.active = focal
        bpy.context.view_layer.update()
        asset = out/(case+'.blend')
        recipe = {'case': case, 'scale_length': scene.unit_settings.scale_length,
            'objects': [{'name': o.name, 'matrix': [list(r) for r in o.matrix_world],
                'vertices': [list(v.co) for v in o.data.vertices], 'faces': [list(p.vertices) for p in o.data.polygons]}
                for o in objects]}
        bpy.ops.wm.save_as_mainfile(filepath=str(asset), check_existing=False)
        rows.append({'case': case, 'asset': str(asset), 'sha256': hashlib.sha256(asset.read_bytes()).hexdigest(),
            'focal_name': focal.name, 'recipe_sha256': hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest(),
            'recipe': recipe})
    (out/'ASSETS.json').write_bytes((json.dumps({'cases': rows, 'blender_version': bpy.app.version_string,
        'builder_only_disposable_saves': len(rows), 'user_assets_loaded': 0}, indent=2)+'\n').encode())


if __name__ == '__main__': main()
