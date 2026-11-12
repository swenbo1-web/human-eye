"""Create the fixed private G508 plus two-cube qualification derivative."""

import hashlib
import json
import os
from pathlib import Path
import sys
import time

import bpy


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / 'verification/scale_diag_001/fixtures/G508.blend'
SOURCE_JSON = SOURCE.with_suffix('.json')
DESTINATION = HERE / 'G508_control.blend'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def save(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def snapshot():
    graph = bpy.context.evaluated_depsgraph_get()
    scale = float(bpy.context.scene.unit_settings.scale_length)
    rows = []
    for obj in sorted(bpy.context.scene.objects, key=lambda item: item.name):
        if obj.type != 'MESH':
            raise ValueError('unexpected_nonmesh_object:' + obj.name)
        evaluated = obj.evaluated_get(graph)
        temporary = evaluated.to_mesh()
        try:
            temporary.calc_loop_triangles()
            local = [[float(x) for x in vertex.co] for vertex in temporary.vertices]
            matrix = [[float(x) for x in row] for row in evaluated.matrix_world]
            rows.append({'name': obj.name, 'name_full': obj.name_full,
                'logical_id': obj.get('scale_logical_id'),
                'object_id': 'blender:' + hashlib.sha256(json.dumps(['', obj.name_full], sort_keys=True,
                    separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
                'library_path': str(getattr(getattr(obj, 'library', None), 'filepath', '')),
                'vertices_local': local, 'matrix_world': matrix,
                'vertices_world': [[(sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3]) * scale
                    for r in range(3)] for point in local],
                'triangles': [list(triangle.vertices) for triangle in temporary.loop_triangles],
                'source_polygon_count': len(temporary.polygons)})
        finally:
            evaluated.to_mesh_clear()
    return {'unit': 'm', 'coordinate_frame': 'world', 'frame': int(bpy.context.scene.frame_current),
        'subframe': float(bpy.context.scene.frame_subframe), 'scale_length': scale, 'objects': rows}


def main():
    started = time.perf_counter_ns()
    original_sha = sha(SOURCE)
    assert original_sha == '04ec6907cb2384c7f8f248c7f7ad56373ca5203692deba20c1f6eae4ec0e1c6f'
    assert sha(SOURCE_JSON) == 'd1af83c191a9672e49fb5ff2e1f9b46fab0a87e39aa0ad6556ccc5bf6e4b834d'
    assert not DESTINATION.exists()
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    original = snapshot()
    assert len(original['objects']) == 12
    assert original['scale_length'] == 1.0
    vertices = [(x, y, z) for x, y, z in ((-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
        (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1))]
    faces = [(0,2,3),(0,3,1),(4,5,7),(4,7,6),(0,1,5),(0,5,4),
        (2,6,7),(2,7,3),(0,4,6),(0,6,2),(1,3,7),(1,7,5)]
    for name, logical_id, center in (('Control_A','control_a',(10,0,0)), ('Control_B','control_b',(13,0,0))):
        assert name not in bpy.data.objects
        mesh = bpy.data.meshes.new(name + 'Mesh')
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = center
        obj['scale_logical_id'] = logical_id
    bpy.context.view_layer.update()
    derived = snapshot()
    by_name = {row['name']: row for row in derived['objects']}
    for row in original['objects']:
        assert by_name[row['name']] == row, 'original_evaluated_object_changed:' + row['name']
    assert {key: derived[key] for key in ('unit','coordinate_frame','frame','subframe','scale_length')} == {
        key: original[key] for key in ('unit','coordinate_frame','frame','subframe','scale_length')}
    counts = {'mesh_objects': len(derived['objects']),
        'vertices': sum(len(row['vertices_local']) for row in derived['objects']),
        'triangles': sum(len(row['triangles']) for row in derived['objects'])}
    assert counts == {'mesh_objects':14, 'vertices':848, 'triangles':1640}, counts
    bpy.ops.wm.save_as_mainfile(filepath=str(DESTINATION), check_existing=False)
    assert sha(SOURCE) == original_sha
    save(HERE / 'ORIGINAL_EVALUATED.json', original)
    save(HERE / 'BUILD_SNAPSHOT.json', derived)
    save(HERE / 'DERIVED_MANIFEST.json', {'schema':'spatial-task-qualification-derived-asset-v1',
        'asset': str(DESTINATION), 'asset_sha256':sha(DESTINATION),
        'source_asset':str(SOURCE),'source_asset_sha256':original_sha,'source_asset_unchanged':True,
        'source_json':str(SOURCE_JSON),'source_json_sha256':sha(SOURCE_JSON),
        'original_evaluated_sha256':sha(HERE/'ORIGINAL_EVALUATED.json'),
        'build_snapshot_sha256':sha(HERE/'BUILD_SNAPSHOT.json'),
        'original_12_evaluated_values_unchanged':True,'frame':derived['frame'],'subframe':derived['subframe'],
        'scale_length':derived['scale_length'],'counts':counts,'blender_version':bpy.app.version_string,
        'builder_sha256':sha(Path(__file__)),'pid':os.getpid(),'started_ns':started,'ended_ns':time.perf_counter_ns(),
        'original_objects':[{'name':row['name'],'values_sha256':hashlib.sha256(encoded(row)).hexdigest()}
            for row in original['objects']],
        'scope':'existing synthetic engineering geometry with fixed analytic controls; no new generalization task'})


if __name__ == '__main__':
    main()
