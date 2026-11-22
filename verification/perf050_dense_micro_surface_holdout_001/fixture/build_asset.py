"""Derive the one registered micro-surface fixture and inspect it after reload."""

from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
OUTPUT = Path('D:/he_perf050_dense_micro_surface_holdout_001_fixture')
ASSET = Path('D:/he_m4_target_002/assets_01/main.blend')
GEOMETRY = ASSET.with_name('main.GEOMETRY.json')
ASSET_SHA = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
GEOMETRY_SHA = 'a48ef1b1634e1bbe66fbb49d47899581432d6bf4aebae5577ea5abdebf4b774d'
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
READBACK = HERE.parents[1] / 'm4_global_local_qualification_001/fixture/build_asset.py'
READBACK_SHA = 'be92f6a0bd11af3fe8812b643a7d0b20bdca3c0dba0d69c1addcd8eb711ade7f'
OLD_COUNTS = {'objects': 14, 'vertices': 3478, 'triangles': 6148}
COUNTS = {'objects': 21, 'vertices': 3506, 'triangles': 6162}
RECTANGLES = [
    ('S021', '9/2', '1/2', '15/8', '1/16', '1/16', 1),
    ('S034', '3/2', '1/2', '15/8', '1/16', '1/16', 1),
    ('S055', '15/2', '1/2', '15/8', '1/16', '1/16', 1),
    ('S012', '11/2', '1/2', '15/8', '1/16', '13/256', 1),
    ('S067', '19/2', '1/2', '15/8', '1/16', '19/256', 1),
    ('S041', '21/2', '1/2', '15/8', '1/16', '1/16', -1),
]
SCREEN_X = (Fraction('119/16'), Fraction('31/4'))
SCREEN_Y = (Fraction('1/4'), Fraction('9/16'))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path, expected=None):
    data = path.read_bytes()
    result = {'path': path.resolve().as_posix(), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}
    require(expected in (None, result['sha256']), f'fixed_input_changed/{path}')
    return result


def additions():
    def panel(name, x, y, z, winding):
        faces = [[0, 1, 2], [0, 2, 3]] if winding > 0 else [[0, 2, 1], [0, 3, 2]]
        return {'name': name, 'vertices_world_m': [[float(a), float(b), float(z)] for a, b in
                 ((x[0], y[0]), (x[1], y[0]), (x[1], y[1]), (x[0], y[1]))], 'triangles': faces}

    result = []
    for name, x, y, z, width, height, winding in RECTANGLES:
        x, y, z, width, height = map(Fraction, (x, y, z, width, height))
        result.append(panel(name, (x - width / 2, x + width / 2), (y - height / 2, y + height / 2),
                            z, winding))
    result.append(panel('S019', SCREEN_X, SCREEN_Y, 2, 1))
    return result


def count(rows, mode):
    return {'objects': len(rows), 'vertices': sum(len(row[mode]['vertices_local']) for row in rows),
            'triangles': sum(len(row[mode]['triangles']) for row in rows)}


def capture(bpy, inventory, scene_names):
    scene, layer = bpy.context.scene, bpy.context.view_layer
    layout = {'objects': [{'name': name, 'ordinal': i} for i, name in enumerate(scene_names)]}
    snapshot = inventory(bpy, layout)
    require(list(obj.name for obj in scene.objects) == scene_names, 'scene_object_order_changed')
    require((snapshot['frame'], snapshot['subframe'], snapshot['unit_system'], snapshot['scale_length'])
            == (1, 0., 'METRIC', 1.), 'saved_frame_units_changed')
    snapshot['display_layer'] = layer.name
    for row in snapshot['objects']:
        obj = scene.objects[row['name']]
        display = {'viewport': obj.visible_get(view_layer=layer), 'hide_render': obj.hide_render,
                   'hide_viewport': obj.hide_viewport, 'hide_get': obj.hide_get(view_layer=layer)}
        require(display == {'viewport': True, 'hide_render': False, 'hide_viewport': False, 'hide_get': False},
                f'object_display_changed/{obj.name}')
        row['visibility'] = display
        row['display_color'] = list(obj.color)
    return snapshot


def verify_original(snapshot, original):
    rows = snapshot['objects']
    for mode in ('native', 'evaluated'):
        require(count(rows, mode) == OLD_COUNTS, f'old_fixture_counts_changed/{mode}')
        for actual, expected in zip(rows, original['objects'], strict=True):
            mesh = actual[mode]
            matrix = 'matrix_world' if mode == 'native' else 'evaluated_matrix_world'
            require(actual['name'] == expected['name'] and actual['ordinal'] == expected['asset_object_ordinal']
                    and actual[matrix] == expected['matrix_world']
                    and all(mesh[k] == expected[k] for k in ('vertices_local', 'vertices_world', 'polygons'))
                    and mesh['triangles'] == expected['source_triangles'],
                    f'old_fixture_native_evaluated_source_changed/{mode}/{actual["name"]}')


def verify_complete(source, baseline, added):
    old_count = len(baseline['objects'])
    require(source['objects'][:old_count] == baseline['objects'], 'old_objects_or_visibility_changed')
    for mode in ('native', 'evaluated'):
        require(count(source['objects'], mode) == COUNTS, f'new_fixture_counts_changed/{mode}')
        for current, expected in zip(source['objects'][old_count:], added, strict=True):
            mesh = current[mode]
            require(current['name'] == current['name'].strip() == expected['name']
                    and current['parent'] is None and not current['modifiers']
                    and mesh['vertices_local'] == mesh['vertices_world'] == expected['vertices_world_m']
                    and mesh['polygons'] == mesh['triangles'] == expected['triangles']
                    and mesh['triangle_polygon_indices'] == [0, 1],
                    f'added_fixture_source_mismatch/{mode}/{current["name"]}')


def main():
    import bpy

    started = perf_counter_ns()
    asset, geometry = pin(ASSET, ASSET_SHA), pin(GEOMETRY, GEOMETRY_SHA)
    blender = pin(Path(bpy.app.binary_path), BLENDER_SHA)
    helper = pin(READBACK, READBACK_SHA)
    inventory = run_path(str(READBACK))['inventory']
    original = json.loads(GEOMETRY.read_bytes())
    original_names = [row['name'] for row in original['objects']]
    added = additions()
    names = original_names + [row['name'] for row in added]
    OUTPUT.mkdir(exist_ok=False)
    output_asset = OUTPUT / 'main.blend'
    bpy.ops.wm.open_mainfile(filepath=str(ASSET), load_ui=False, use_scripts=False)
    baseline = capture(bpy, inventory, original_names)
    verify_original(baseline, original)
    for row in added:
        mesh = bpy.data.meshes.new(row['name'] + 'Mesh')
        mesh.from_pydata(row['vertices_world_m'], [], row['triangles'])
        mesh.update()
        obj = bpy.data.objects.new(row['name'], mesh)
        bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.update()
    before = capture(bpy, inventory, names)
    verify_complete(before, baseline, added)
    bpy.context.preferences.filepaths.save_version = 0
    require(bpy.ops.wm.save_as_mainfile(filepath=str(output_asset), check_existing=False) == {'FINISHED'},
            'save_did_not_finish')
    saved = pin(output_asset)
    bpy.ops.wm.open_mainfile(filepath=str(output_asset), load_ui=False, use_scripts=False)
    reopened = capture(bpy, inventory, names)
    require(reopened == before and pin(output_asset) == saved, 'reopen_changed_native_or_evaluated_source')
    verify_complete(reopened, baseline, added)
    require(pin(ASSET) == asset and pin(GEOMETRY) == geometry, 'original_input_changed')
    readback = OUTPUT / 'REOPENED_SOURCE.json'
    with readback.open('x', encoding='utf-8', newline='\n') as out:
        json.dump(reopened, out, separators=(',', ':'), allow_nan=False)
    receipt = {'schema': 'perf050-dense-micro-asset-v1', 'asset': saved, 'reopened_source': pin(readback),
               'old_asset': asset, 'old_geometry': geometry, 'builder': pin(Path(__file__)), 'blender': blender,
               'blender_version': bpy.app.version_string, 'readback_helper': helper, 'counts': COUNTS,
               'original_counts': OLD_COUNTS, 'old_object_names': original_names,
               'added_object_names': names[len(original_names):], 'original_sources_unchanged': True,
               'native_and_evaluated_verified_before_save_and_after_reopen': True, 'save_count': 1,
               'raster_attempts': 0, 'elapsed_ns': perf_counter_ns() - started}
    with (OUTPUT / 'ASSET_BINDING.json').open('x', encoding='utf-8', newline='\n') as out:
        json.dump(receipt, out, indent=2, allow_nan=False)
        out.write('\n')
    print(json.dumps({'passed': True, 'asset': saved, 'counts': COUNTS}))


if __name__ == '__main__':
    main()
