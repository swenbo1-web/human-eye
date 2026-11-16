"""Construct and reload the fixed fixture in one root-owned Blender process."""

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback


OUTPUT = Path('D:/he_m4_global_local_001/fixture')
IDENTITY = [[float(i == j) for j in range(4)] for i in range(4)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def check_pins(records):
    for row in records:
        actual = pin(row['path'])
        if actual['sha256'] != row['sha256'] or actual['bytes'] != row['bytes']:
            raise ValueError('frozen_builder_source_changed/' + row['path'])


def expected_record(row):
    return dict(name=row['name'], ordinal=row['ordinal'],
                vertices=[[float(Fraction(value)) for value in point] for point in row['vertices_world_m']],
                triangles=row['triangles'])


def mesh_record(mesh, matrix):
    mesh.calc_loop_triangles()
    return dict(vertices_local=[[float(value) for value in vertex.co] for vertex in mesh.vertices],
        vertices_world=[[float(value) for value in matrix @ vertex.co] for vertex in mesh.vertices],
        polygons=[list(face.vertices) for face in mesh.polygons],
        triangles=[list(face.vertices) for face in mesh.loop_triangles],
        triangle_polygon_indices=[int(face.polygon_index) for face in mesh.loop_triangles])


def inventory(bpy, recipe):
    graph = bpy.context.evaluated_depsgraph_get()
    rows = []
    for original in recipe['objects']:
        obj = bpy.data.objects[original['name']]
        evaluated = obj.evaluated_get(graph)
        evaluated_mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
        try:
            rows.append(dict(name=obj.name, ordinal=original['ordinal'], type=obj.type,
                mesh_name=obj.data.name, matrix_world=[list(row) for row in obj.matrix_world],
                evaluated_matrix_world=[list(row) for row in evaluated.matrix_world],
                parent=obj.parent.name if obj.parent else None,
                modifiers=[modifier.type for modifier in obj.modifiers],
                native=mesh_record(obj.data, obj.matrix_world),
                evaluated=mesh_record(evaluated_mesh, evaluated.matrix_world)))
        finally:
            evaluated.to_mesh_clear()
    scene = bpy.context.scene
    return dict(schema='m4-global-local-asset-readback-v1',
        object_names=sorted(obj.name for obj in scene.objects),
        unit_system=scene.unit_settings.system, scale_length=float(scene.unit_settings.scale_length),
        frame=int(scene.frame_current), subframe=float(scene.frame_subframe), objects=rows)


def verify(actual, recipe):
    if (actual['object_names'] != sorted(row['name'] for row in recipe['objects'])
            or actual['unit_system'] != 'METRIC' or actual['scale_length'] != 1
            or actual['frame'] != 1 or actual['subframe'] != 0):
        raise ValueError('saved_fixture_scene_contract')
    for row, original in zip(actual['objects'], recipe['objects'], strict=True):
        expected = expected_record(original)
        if (row['name'] != expected['name'] or row['ordinal'] != expected['ordinal']
                or row['type'] != 'MESH' or row['parent'] is not None or row['modifiers']
                or row['matrix_world'] != IDENTITY or row['evaluated_matrix_world'] != IDENTITY):
            raise ValueError('saved_fixture_object_contract/' + row['name'])
        for mode in ('native', 'evaluated'):
            data = row[mode]
            if (data['vertices_local'] != expected['vertices'] or data['vertices_world'] != expected['vertices']
                    or data['polygons'] != expected['triangles'] or data['triangles'] != expected['triangles']
                    or data['triangle_polygon_indices'] != list(range(len(expected['triangles'])))):
                raise ValueError('saved_fixture_exact_source_order/' + row['name'] + '/' + mode)


def build(plan_path):
    started = time.perf_counter_ns()
    output = OUTPUT.resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan_path = Path(plan_path).resolve()
    plan = json.loads(plan_path.read_bytes())
    if (Path(plan['output_directory']).resolve() != output
            or plan['schema'] != 'm4-global-local-build-plan-v1'
            or plan['counts'] != dict(objects=9, vertices=54, triangles=56)):
        raise ValueError('fixed_fixture_build_plan')
    check_pins(plan['inputs'])
    recipe_path = Path(plan['geometry_path']).resolve()
    recipe = json.loads(recipe_path.read_bytes())
    if recipe['counts'] != plan['counts']:
        raise ValueError('fixed_fixture_recipe_counts')
    asset = output / 'main.blend'
    if asset.exists():
        raise FileExistsError('owned_fixture_asset_already_exists')
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
        expected = expected_record(row)
        mesh = bpy.data.meshes.new('Mesh_' + str(row['ordinal'] + 1).zfill(2))
        mesh.from_pydata(expected['vertices'], [], expected['triangles'])
        mesh.update()
        mesh.materials.append(material)
        obj = bpy.data.objects.new(row['name'], mesh)
        scene.collection.objects.link(obj)
        obj.color = (0.65, 0.65, 0.65, 1)
    bpy.context.view_layer.update()
    before = inventory(bpy, recipe)
    verify(before, recipe)
    before_path = output / 'READBACK_BEFORE_SAVE.json'
    save(before_path, before)
    before_save_ns = time.perf_counter_ns()
    bpy.ops.wm.save_as_mainfile(filepath=str(asset), check_existing=False)
    saved_ns = time.perf_counter_ns()
    asset_pin = pin(asset)
    bpy.ops.wm.open_mainfile(filepath=str(asset), load_ui=False)
    reopened_ns = time.perf_counter_ns()
    after = inventory(bpy, recipe)
    verify(after, recipe)
    if before != after:
        raise ValueError('fixture_readback_changed_after_reload')
    if pin(asset) != asset_pin:
        raise ValueError('fixture_saved_file_changed_during_reload')
    after_path = output / 'READBACK_AFTER_RELOAD.json'
    save(after_path, after)
    check_pins(plan['inputs'])
    closed = time.perf_counter_ns()
    binding = dict(schema='m4-global-local-asset-binding-v1', passed=True,
        asset_path=str(asset), asset_sha256=asset_pin['sha256'], asset_bytes=asset_pin['bytes'],
        geometry=pin(recipe_path), build_plan=pin(plan_path), builder=pin(__file__),
        readback_before_save=pin(before_path), readback_after_reload=pin(after_path),
        input_pins=plan['inputs'], counts=recipe['counts'],
        object_names=[row['name'] for row in recipe['objects']],
        source_triangle_contract='native polygons and evaluated loop triangles match frozen row order exactly',
        unit='metre', scale_length=1, matrices='identity', frame=1, subframe=0,
        blender_version=bpy.app.version_string, builder_pid=os.getpid(),
        preparation_processes=1, raster_attempts=0, product_imports=0,
        clocks=dict(builder_started_ns=started, before_save_ns=before_save_ns,
                    saved_ns=saved_ns, reopened_ns=reopened_ns, verified_ns=closed,
                    preparation_to_verified_ns=closed-started),
        source_author_association='Fixture author prepared the recipe and constructor. Independent qualification is separate.')
    save(output / 'ASSET_BINDING.json', binding)
    print(json.dumps(dict(passed=True, asset=str(asset), sha256=asset_pin['sha256'], counts=recipe['counts'])))


if __name__ == '__main__':
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    options = parser.parse_args(arguments)
    try:
        build(options.plan)
    except BaseException as error:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        failure = dict(passed=False, error_type=type(error).__name__, error=str(error),
                       traceback=traceback.format_exc(), pid=os.getpid())
        path = OUTPUT / ('BUILD_FAILURE_' + str(time.perf_counter_ns()) + '.json')
        save(path, failure)
        print(json.dumps(failure))
        raise
