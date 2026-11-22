"""Build the registered fixture once, then reopen it in a separate Blender process."""

from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
OUTPUT = Path('D:/he_m1_region_task_first_packet_consumption_holdout_001/fixture')
SOURCE = Path('D:/he_m4_target_002/assets_01/main.blend')
SOURCE_SHA = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
GEOMETRY = SOURCE.with_name('main.GEOMETRY.json')
GEOMETRY_SHA = 'a48ef1b1634e1bbe66fbb49d47899581432d6bf4aebae5577ea5abdebf4b774d'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
PRIOR_BUILDER = HERE.parents[1] / 'perf050_dense_micro_surface_holdout_001/fixture/build_asset.py'
PRIOR_BUILDER_SHA = 'cc8c70399c22bf66155fac11be657f59376e59414f4361d12bb554df42e02e69'
COUNTS = {'objects': 20, 'vertices': 3502, 'triangles': 6160}
FACES = [[0, 1, 2], [0, 2, 3]]
RECIPE = (
    ('Component_417', ('3/2', '1/2', '7/4'), ('1/16', '0', '-3/64'), ('0', '1/16', '0')),
    ('Component_736', ('15/2', '2', '3/2'), ('3/64', '0', '5/256'), ('0', '25/256', '0')),
    ('Component_582', ('19/2', '5/8', '5/4'), ('1/16', '0', '0'), ('0', '5/64', '0')),
    ('Component_294', ('7/4', '3/8', '3/2'), ('0', '3/8', '0'), ('0', '0', '5/8')),
    ('Component_865', ('119/16', '13/8', '7/4'), ('9/16', '0', '0'), ('0', '3/4', '0')),
    ('Component_163', ('2', '16', '0'), ('2', '0', '0'), ('0', '0', '2')),
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path, expected=None):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        digest = sha256()
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    actual = digest.hexdigest()
    require(expected in (None, actual), f'fixed_input_changed/{path}')
    return {'path': path.as_posix(), 'bytes': path.stat().st_size, 'sha256': actual}


def read(path):
    return json.loads(path.read_bytes())


def save(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        stream.write('\n')


def additions():
    for name, *basis in RECIPE:
        o, u, v = [tuple(map(Fraction, row)) for row in basis]
        vertices = [[float(a + i * b + j * c) for a, b, c in zip(o, u, v, strict=True)]
                    for i, j in ((0, 0), (1, 0), (1, 1), (0, 1))]
        yield name, vertices


def helpers():
    pin(PRIOR_BUILDER, PRIOR_BUILDER_SHA)
    prior = run_path(str(PRIOR_BUILDER))
    prior['pin'](prior['READBACK'], prior['READBACK_SHA'])
    inventory = run_path(str(prior['READBACK']))['inventory']
    return prior, inventory


def verify_derived(snapshot, baseline, prior):
    n = len(baseline['objects'])
    rows = snapshot['objects']
    require(rows[:n] == baseline['objects'], 'original_native_evaluated_display_mismatch')
    identity = [[float(i == j) for j in range(4)] for i in range(4)]
    for mode in ('native', 'evaluated'):
        require(prior['count'](rows, mode) == COUNTS, f'derived_counts_changed/{mode}')
        for actual, (name, vertices) in zip(rows[n:], additions(), strict=True):
            mesh = actual[mode]
            require(actual['name'] == name and actual['parent'] is None and not actual['modifiers']
                    and actual['matrix_world'] == actual['evaluated_matrix_world'] == identity
                    and mesh['vertices_local'] == mesh['vertices_world'] == vertices
                    and mesh['polygons'] == mesh['triangles'] == FACES
                    and mesh['triangle_polygon_indices'] == [0, 1],
                    f'derived_native_evaluated_source_mismatch/{name}/{mode}')


def record_blender_stage(stage):
    import bpy

    started = perf_counter_ns()
    prior, inventory = helpers()
    original_names = [row['name'] for row in read(GEOMETRY)['objects']]
    names = original_names + [name for name, _ in additions()]
    asset = OUTPUT / 'main.blend'
    froze = read(OUTPUT / 'PREPARATION.json')
    require(pin(Path(bpy.app.binary_path), BLENDER_SHA) == froze['blender']
            and pin(SOURCE, SOURCE_SHA) == froze['original_asset']
            and pin(GEOMETRY, GEOMETRY_SHA) == froze['original_geometry'],
            'frozen_file_changed_before_blender_stage')
    require(stage in ('build', 'reopen'), 'invalid_blender_stage')
    if stage == 'build':
        require(not asset.exists(), 'registered_fixture_already_exists')
        bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False, use_scripts=False)
        baseline = prior['capture'](bpy, inventory, original_names)
        prior['verify_original'](baseline, read(GEOMETRY))
        save(OUTPUT / 'ORIGINAL.json', baseline)
        for name, vertices in additions():
            mesh = bpy.data.meshes.new(name + '_Mesh')
            mesh.from_pydata(vertices, [], FACES)
            mesh.update()
            bpy.context.scene.collection.objects.link(bpy.data.objects.new(name, mesh))
        bpy.context.view_layer.update()
        snapshot = prior['capture'](bpy, inventory, names)
        verify_derived(snapshot, baseline, prior)
        save(OUTPUT / 'BEFORE_SAVE.json', snapshot)
        bpy.context.preferences.filepaths.save_version = 0
        require(bpy.ops.wm.save_as_mainfile(filepath=str(asset), check_existing=False) == {'FINISHED'},
                'single_fixture_save_failed')
        save_count = 1
    else:
        built = read(OUTPUT / 'BUILD.json')
        require(pin(asset) == built['asset'], 'derived_asset_changed_between_processes')
        require(os.getpid() != built['pid'], 'reopen_process_not_independent')
        bpy.ops.wm.open_mainfile(filepath=str(asset), load_ui=False, use_scripts=False)
        snapshot = prior['capture'](bpy, inventory, names)
        baseline = read(OUTPUT / 'ORIGINAL.json')
        prior['verify_original'](baseline, read(GEOMETRY))
        verify_derived(snapshot, baseline, prior)
        require(snapshot == read(OUTPUT / 'BEFORE_SAVE.json'), 'separate_reopen_captured_different_source')
        require(pin(asset) == built['asset'], 'separate_reopen_changed_asset_bytes')
        save(OUTPUT / 'REOPEN.json', snapshot)
        save_count = 0
    receipt = {
        'stage': stage, 'pid': os.getpid(), 'asset': pin(asset), 'blender_version': bpy.app.version_string,
        'save_count': save_count, 'raster_count': 0, 'counts': COUNTS, 'elapsed_ns': perf_counter_ns() - started,
        'snapshot': pin(OUTPUT / 'BEFORE_SAVE.json'),
    }
    if stage == 'reopen':
        receipt['reopened_source'] = pin(OUTPUT / 'REOPEN.json')
    save(OUTPUT / ('BUILD.json' if stage == 'build' else 'REOPEN_STAGE.json'), receipt)


def run_blender(stage, command):
    began = perf_counter_ns()
    stdout = OUTPUT / f'{stage.upper()}_STDOUT.bin'
    stderr = OUTPUT / f'{stage.upper()}_STDERR.bin'
    timed_out = False
    with stdout.open('xb') as out, stderr.open('xb') as err, subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=OUTPUT,
            creationflags=subprocess.CREATE_NO_WINDOW) as process:
        try:
            process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait()
        pid, status = process.pid, process.returncode
    receipt = {
        'pid': pid, 'exit_code': status, 'timed_out': timed_out, 'exit_observed': True,
        'io_files_closed': out.closed and err.closed, 'stdout': pin(stdout), 'stderr': pin(stderr),
        'elapsed_ns': perf_counter_ns() - began,
    }
    save(OUTPUT / f'{stage.upper()}_CLOSE.json', receipt)
    require(status == 0 and not timed_out, f'blender_{stage}_failed/{status}')
    recorded = OUTPUT / ('BUILD.json' if stage == 'build' else 'REOPEN_STAGE.json')
    require(read(recorded)['pid'] == pid, f'blender_{stage}_receipt_not_process_bound')
    return receipt


def main():
    prior, _ = helpers()
    truth = run_path(str(HERE / 'derive_truth.py'))
    preview = truth['preview']()
    commands = {stage: [str(BLENDER), '--background', '--factory-startup', '--disable-autoexec',
                        '--python-exit-code', '40', '--python', str(Path(__file__).resolve()), '--', stage]
                for stage in ('build', 'reopen')}
    preparation = {
        'plan_commit': '1e8d52ae',
        'original_asset': pin(SOURCE, SOURCE_SHA), 'original_geometry': pin(GEOMETRY, GEOMETRY_SHA),
        'blender': pin(BLENDER, BLENDER_SHA), 'builder': pin(__file__),
        'truth_program': pin(HERE / 'derive_truth.py'), 'pinned_inventory_helpers': [
            pin(PRIOR_BUILDER, PRIOR_BUILDER_SHA), pin(prior['READBACK'], prior['READBACK_SHA'])],
        'operations': commands, 'counts': COUNTS,
    }
    OUTPUT.mkdir(parents=True, exist_ok=False)
    save(OUTPUT / 'PREPARATION.json', preparation)
    save(OUTPUT / 'GEOMETRY_PREFLIGHT.json', preview)
    closed = {stage: run_blender(stage, command) for stage, command in commands.items()}
    asset, reopened = OUTPUT / 'main.blend', OUTPUT / 'REOPEN.json'
    require(pin(SOURCE) == preparation['original_asset'] and pin(GEOMETRY) == preparation['original_geometry'],
            'original_asset_or_geometry_changed')
    require(pin(asset) == read(OUTPUT / 'BUILD.json')['asset'] == read(OUTPUT / 'REOPEN_STAGE.json')['asset'],
            'one_build_asset_binding_changed')
    evaluated = truth['evaluate'](read(reopened))
    require(evaluated == preview, 'separately_reopened_geometry_changed_from_independent_preflight')
    save(OUTPUT / 'TRUTH.json', {
        **evaluated, 'asset': pin(asset), 'reopened_source': pin(reopened), 'truth_program': preparation['truth_program'],
    })
    save(OUTPUT / 'ASSET_BINDING.json', {
        'schema': 'region-task-first-packet-holdout-asset-v1',
        'asset': pin(asset), 'reopened_source': pin(reopened), 'truth': pin(OUTPUT / 'TRUTH.json'),
        'original_asset': preparation['original_asset'], 'original_geometry': preparation['original_geometry'],
        'original_source': pin(OUTPUT / 'ORIGINAL.json'), 'original_sources_unchanged': True,
        'counts': COUNTS, 'one_build': read(OUTPUT / 'BUILD.json'), 'reopen': read(OUTPUT / 'REOPEN_STAGE.json'),
        'closed_processes': closed, 'preparation': pin(OUTPUT / 'PREPARATION.json'),
    })
    print(json.dumps({'asset': pin(asset), 'counts': COUNTS, 'truth': pin(OUTPUT / 'TRUTH.json')}))


if __name__ == '__main__':
    if '--' in sys.argv:
        stage, = sys.argv[sys.argv.index('--') + 1:]
        record_blender_stage(stage)
    else:
        require(len(sys.argv) == 1, 'unexpected_driver_arguments')
        main()
