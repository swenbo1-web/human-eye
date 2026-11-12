"""Build two owned inputs and inventory the retained peripheral input."""
import hashlib
import itertools
import json
from pathlib import Path
import sys


def main():
    import bpy
    from mathutils import Euler, Matrix
    folder = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
    rows = []
    box_vertices = [(x, y, z) for x, y, z in
                    ((-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                     (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1))]
    box_faces = [(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)]
    for case in ('simple_boxes', 'peripheral', 'rotated_asymmetric'):
        asset = folder / (case + '.blend')
        if case == 'peripheral':
            bpy.ops.wm.open_mainfile(filepath=str(asset))
        else:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            scene = bpy.context.scene
            scene.unit_settings.system = 'METRIC'
            scene.unit_settings.scale_length = 1.
            scene.frame_set(1)
            for ordinal, name in enumerate(('M4_Focal', 'M4_Near', 'M4_Far_00')):
                if case == 'rotated_asymmetric' and ordinal < 2:
                    vertices = [(0.,0.,0.),(2.,0.,0.),(0.,1.,0.),(0.,0.,.5)]
                    faces = [(0,2,1),(0,1,3),(0,3,2),(1,2,3)]
                else:
                    vertices = [[.1 * v for v in point] for point in box_vertices]
                    faces = box_faces
                mesh = bpy.data.meshes.new(name + 'Mesh')
                mesh.from_pydata(vertices, [], faces)
                mesh.update()
                obj = bpy.data.objects.new(name, mesh)
                scene.collection.objects.link(obj)
                obj.matrix_world = Matrix.Translation((ordinal * 3., 0., 0.))
                if case == 'rotated_asymmetric':
                    rotation = Euler((.13,.19,.47)).to_matrix().to_4x4()
                    obj.matrix_world = Matrix.Translation((.4,-.3,.2)) @ rotation @ obj.matrix_world
            bpy.context.view_layer.objects.active = bpy.data.objects['M4_Focal']
            bpy.context.view_layer.update()
            bpy.ops.wm.save_as_mainfile(filepath=str(asset), check_existing=False)
        graph = bpy.context.evaluated_depsgraph_get()
        objects = []
        for obj in bpy.context.scene.objects:
            if obj.type != 'MESH':
                continue
            evaluated = obj.evaluated_get(graph)
            mesh = evaluated.to_mesh()
            try:
                local = [[float(x) for x in vertex.co] for vertex in mesh.vertices]
                matrix = [[float(x) for x in row] for row in evaluated.matrix_world]
                scale = float(bpy.context.scene.unit_settings.scale_length)
                world = [[(sum(matrix[r][c]*point[c] for c in range(3))+matrix[r][3])*scale
                          for r in range(3)] for point in local]
                lower = [min(point[k] for point in world) for k in range(3)]
                upper = [max(point[k] for point in world) for k in range(3)]
                local_bounds = [(min(point[k] for point in local), max(point[k] for point in local)) for k in range(3)]
                corners = [[(sum(matrix[r][c]*point[c] for c in range(3))+matrix[r][3])*scale
                            for r in range(3)] for point in itertools.product(*local_bounds)]
                objects.append({'name': obj.name, 'vertices_local': local, 'matrix_world': matrix,
                    'vertices_world': world, 'polygons': [list(face.vertices) for face in mesh.polygons],
                    'bbox_min': lower, 'bbox_max': upper,
                    'center': [(a+b)*.5 for a,b in zip(lower,upper)],
                    'corner_bbox_min': [min(point[k] for point in corners) for k in range(3)],
                    'corner_bbox_max': [max(point[k] for point in corners) for k in range(3)]})
            finally:
                evaluated.to_mesh_clear()
        if case == 'peripheral':
            assert len(objects) == 14 and sum(len(row['vertices_local']) for row in objects) == 3474
            assert sum(len(row['polygons']) for row in objects) == 6146
        if case == 'rotated_asymmetric':
            focal = next(row for row in objects if row['name'] == 'M4_Focal')
            assert (focal['bbox_min'], focal['bbox_max']) != (focal['corner_bbox_min'], focal['corner_bbox_max'])
        rows.append({'name': case, 'asset': str(asset), 'asset_sha256': hashlib.sha256(asset.read_bytes()).hexdigest(),
                     'object_count': len(objects), 'vertex_count': sum(len(row['vertices_local']) for row in objects),
                     'polygon_count': sum(len(row['polygons']) for row in objects),
                     'frame': bpy.context.scene.frame_current, 'scale_length': scale,
                     'selected_names': ['M4_Focal','M4_Near'], 'oracle': objects})
    (folder / 'INPUTS.json').write_text(json.dumps({'blender_version': bpy.app.version_string, 'inputs': rows},
                                                 indent=2, allow_nan=False)+'\n', encoding='utf8')


if __name__ == '__main__':
    main()
