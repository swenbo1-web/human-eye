"""Build and reopen one registered Blender fixture, using the prior mesh verifier."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
OUTPUT = Path('D:/he_m4_cross_scale_live_task_001/fixture').resolve()
COUNTS = {'objects': 21, 'vertices': 148, 'triangles': 184}
REUSED = HERE.parents[1] / 'm4_global_local_qualification_001/fixture/build_asset.py'
REUSED_SHA = 'be92f6a0bd11af3fe8812b643a7d0b20bdca3c0dba0d69c1addcd8eb711ade7f'


def read(path):
    return json.loads(Path(path).read_bytes())


def checked_inventory(bpy, helpers, recipe):
    snapshot = helpers['inventory'](bpy, recipe)
    helpers['verify'](snapshot, recipe)
    layer = bpy.context.view_layer
    for row in snapshot['objects']:
        obj = bpy.context.scene.objects[row['name']]
        visible = {'viewport': obj.visible_get(view_layer=layer), 'hide_render': obj.hide_render,
                   'hide_viewport': obj.hide_viewport, 'hide_get': obj.hide_get(view_layer=layer)}
        if visible != {'viewport': True, 'hide_render': False, 'hide_viewport': False, 'hide_get': False}:
            raise ValueError('registered_display_contract/' + row['name'])
        row['visibility'] = visible
    snapshot['display_layer'] = layer.name
    return snapshot


def build(plan_path):
    if hashlib.sha256(REUSED.read_bytes()).hexdigest() != REUSED_SHA:
        raise ValueError('reused_fixture_mesh_verifier_changed')
    helpers = runpy.run_path(str(REUSED))
    pin, check_pins, save = (helpers[name] for name in ('pin', 'check_pins', 'save'))
    plan = read(plan_path)
    if (Path(plan['output_directory']).resolve() != OUTPUT
            or plan['schema'] != 'm4-cross-scale-live-task-build-v1' or plan['counts'] != COUNTS):
        raise ValueError('registered_cross_scale_build_plan_required')
    check_pins(plan['inputs'])
    recipe_path = Path(plan['geometry_path']).resolve()
    recipe = read(recipe_path)
    if recipe['counts'] != COUNTS or recipe_path != HERE / 'GEOMETRY.json':
        raise ValueError('registered_recipe_counts_and_path_required')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    asset = OUTPUT / 'main.blend'
    if asset.exists():
        raise FileExistsError('the_registered_asset_already_exists')
    started = time.perf_counter_ns()
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene.frame_set(1, subframe=0)
    material = bpy.data.materials.new('Surface')
    material.diffuse_color = (0.65, 0.65, 0.65, 1)
    for row in recipe['objects']:
        expected = helpers['expected_record'](row)
        mesh = bpy.data.meshes.new(f'Mesh_{row["ordinal"] + 1:02d}')
        mesh.from_pydata(expected['vertices'], [], expected['triangles'])
        mesh.update()
        mesh.materials.append(material)
        obj = bpy.data.objects.new(row['name'], mesh)
        scene.collection.objects.link(obj)
        obj.color = material.diffuse_color
    bpy.context.view_layer.update()
    before = checked_inventory(bpy, helpers, recipe)
    before_path = OUTPUT / 'READBACK_BEFORE_SAVE.json'
    save(before_path, before)
    before_save_ns = time.perf_counter_ns()
    bpy.ops.wm.save_as_mainfile(filepath=str(asset), check_existing=False)
    saved_ns = time.perf_counter_ns()
    asset_pin = pin(asset)
    bpy.ops.wm.open_mainfile(filepath=str(asset), load_ui=False)
    reopened_ns = time.perf_counter_ns()
    after = checked_inventory(bpy, helpers, recipe)
    if after != before or pin(asset) != asset_pin:
        raise ValueError('fixture_readback_or_saved_asset_changed_on_reload')
    after_path = OUTPUT / 'READBACK_AFTER_RELOAD.json'
    save(after_path, after)
    check_pins(plan['inputs'])
    verified_ns = time.perf_counter_ns()
    result = {'schema': 'm4-cross-scale-live-task-asset-binding-v1', 'passed': True,
              'asset_path': str(asset), 'asset_sha256': asset_pin['sha256'], 'asset_bytes': asset_pin['bytes'],
              'geometry': pin(recipe_path), 'build_plan': pin(plan_path), 'builder': pin(Path(__file__)),
              'input_pins': plan['inputs'], 'readback_before_save': pin(before_path),
              'readback_after_reload': pin(after_path), 'counts': COUNTS, 'object_names': after['object_names'],
              'source_triangle_contract': 'Native and evaluated meshes have identical registered ordered arrays.',
              'frame': after['frame'], 'subframe': after['subframe'], 'unit': 'metre',
              'scale_length': after['scale_length'], 'builder_pid': os.getpid(), 'blender_version': bpy.app.version_string,
              'preparation_processes': 1, 'raster_attempts': 0, 'product_imports': 0,
              'clocks': {'started_ns': started, 'before_save_ns': before_save_ns, 'saved_ns': saved_ns,
                         'reopened_ns': reopened_ns, 'verified_ns': verified_ns,
                         'preparation_to_verified_ns': verified_ns - started}}
    save(OUTPUT / 'ASSET_BINDING.json', result)
    print(json.dumps({'passed': True, 'asset_sha256': asset_pin['sha256'], 'counts': COUNTS}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    options = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    try:
        build(options.plan)
    except BaseException as error:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        result = {'passed': False, 'type': type(error).__name__, 'error': str(error),
                  'traceback': traceback.format_exc(), 'pid': os.getpid()}
        with (OUTPUT / 'BUILD_FAILURE.json').open('x', encoding='utf8') as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
        raise
