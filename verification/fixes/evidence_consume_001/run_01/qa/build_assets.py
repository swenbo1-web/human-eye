"""One owned Blender build of frozen S/G specifications; no product solver calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_truth import NAMES, expected_geometry, validate_readback


def save(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for action in list(bpy.data.actions):
        if action.users == 0:
            bpy.data.actions.remove(action)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene.frame_set(1)


def add(name, source):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(source['vertices'], [], source['faces'])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if obj.animation_data is not None or mesh.animation_data is not None or len(obj.modifiers):
        raise ValueError('Unexpected animation or modifiers on newly authored object')
    return obj


def readback():
    return {obj.name: dict(vertices=[list(vertex.co) for vertex in obj.data.vertices],
        faces=[list(face.vertices) for face in obj.data.polygons],
        matrix=[list(row) for row in obj.matrix_world], modifiers=len(obj.modifiers))
        for obj in bpy.data.objects if obj.type == 'MESH'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root = args.root.resolve()
    frozen = {}
    for case in ('S', 'G'):
        author = root / 'author' / case
        geometry = json.loads((author / 'EXPECTED_GEOMETRY.json').read_text(encoding='utf8'))
        if geometry != expected_geometry(case):
            raise ValueError('Frozen geometry differs from assignment construction')
        if (author / 'scene.blend').exists() or (author / 'BUILD_READBACK.json').exists():
            raise FileExistsError('Fixture rebuild/overwrite refused: ' + case)
        truth = json.loads((author / 'TRUTH.json').read_text(encoding='utf8'))
        if truth['product_solver_calls'] != 0 or truth['fixture'] != case:
            raise ValueError('Independent truth missing before Blender build')
        frozen[case] = geometry
    records = []
    for case in ('S', 'G'):
        author = root / 'author' / case
        clear()
        for name in NAMES:
            add(name, frozen[case][name])
        actual = readback()
        checked = validate_readback(case, actual)
        save(author / 'BUILD_READBACK.json', actual)
        bpy.ops.wm.save_as_mainfile(filepath=str(author / 'scene.blend'))
        records.append(dict(case=case, checks=checked,
            scene_sha256=digest(author / 'scene.blend'),
            scene_bytes=(author / 'scene.blend').stat().st_size,
            expected_geometry_sha256=digest(author / 'EXPECTED_GEOMETRY.json'),
            truth_sha256=digest(author / 'TRUTH.json'),
            build_readback_sha256=digest(author / 'BUILD_READBACK.json'),
            unit_system=bpy.context.scene.unit_settings.system,
            scale_length=bpy.context.scene.unit_settings.scale_length,
            frame=bpy.context.scene.frame_current,
            object_animation_data_none=all(obj.animation_data is None for obj in bpy.data.objects),
            mesh_animation_data_none=all(mesh.animation_data is None for mesh in bpy.data.meshes)))
    save(root / 'ASSET_BUILD_MANIFEST.json', dict(schema='evidence-consume-fixtures-v1',
        source_assignment_sha256='f3c6742c062f5d9748ff66a9020447f88bee864b344323c4f977f6150a339842',
        blender_version=bpy.app.version_string, product_solver_calls=0,
        grid_order='i outer, j inner; index=i*nj+j',
        cell_triangles='(a,b,c),(a,c,d) on low-low to high-high diagonal', cases=records))
    print(json.dumps(dict(status='fixed_assets_built', cases=['S', 'G'],
                          product_solver_calls=0, blender_version=bpy.app.version_string)))


if __name__ == '__main__':
    main()
