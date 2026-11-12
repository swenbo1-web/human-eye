"""Own one factory builder and the existing read-only QA session through reap."""

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
ASSET = BATCH / 'asset' / 'grooved_rail.blend'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
HELPER = ROOT / 'verification/native_plugin_complex_003/reused/accepted_native.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    started = time.perf_counter_ns()
    started_utc = datetime.now(timezone.utc).isoformat()
    freeze = json.loads((BATCH / 'FREEZE.json').read_bytes())
    assert freeze['cycle'] == 'M4-GROOVED-RAIL-TRANSFER-001'
    assert freeze['consumer_allowance'] == freeze['product_pretest_allowance'] == freeze['images'] == 0
    for specification in freeze['specifications']:
        assert sha(BATCH / specification['copy']) == specification['sha256']
    assert not ASSET.exists() and not (HERE / 'PREPARATION.json').exists()
    save(HERE / 'PREPARATION_STARTED.json', {
        'started_ns': started, 'started_utc': started_utc, 'freeze_sha256': sha(BATCH / 'FREEZE.json'),
        'blender_sha256': sha(BLENDER), 'helper_sha256': sha(HELPER),
        'controller_sha256': sha(Path(__file__)),
        'build_script_sha256': sha(BATCH / 'asset/build_assets.py'),
        'export_script_sha256': sha(BATCH / 'asset/export_snapshot.py'),
        'authorized_sessions': ['factory_private_build', 'existing_exclusive_QA_readback'],
        'models': 0, 'product_processes': 0, 'images': 0})
    sessions_started = 0
    builder = None
    qa = None
    build_record = None
    close = None
    errors = []
    try:
        argv = [str(BLENDER), '--factory-startup', '--disable-autoexec', '--background',
                '--python-exit-code', '1', '--python', str(BATCH / 'asset/build_assets.py')]
        mark = time.perf_counter_ns()
        with (HERE / 'builder_stdout.bin').open('xb') as stdout, (HERE / 'builder_stderr.bin').open('xb') as stderr:
            builder = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       cwd=str(BATCH / 'asset'), shell=False,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            sessions_started += 1
            save(HERE / 'BUILDER_STARTED.json', {'pid': builder.pid, 'argv': argv, 'started_ns': mark})
            try:
                exit_code = builder.wait(timeout=90)
            finally:
                if builder.poll() is None:
                    builder.kill()
                    builder.wait(timeout=5)
            build_record = {'pid': builder.pid, 'exit_code': builder.returncode,
                            'process_reaped': builder.poll() is not None,
                            'elapsed_ns': time.perf_counter_ns() - mark,
                            'stdout_sha256': sha(HERE / 'builder_stdout.bin'),
                            'stderr_sha256': sha(HERE / 'builder_stderr.bin')}
            save(HERE / 'BUILDER_CLOSED.json', build_record)
            assert exit_code == 0, 'factory_build_failed'
        expected_asset = sha(ASSET)
        specification = importlib.util.spec_from_file_location('_grooved_rail_exclusive_qa', HELPER)
        helper = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(helper)
        deadline = time.perf_counter_ns() + 120 * 10**9
        # NativeSession.start has its own existing cleanup protection when
        # initialization fails before this owner receives the returned object.
        sessions_started += 1
        qa = helper.NativeSession.start(blender=BLENDER, asset=ASSET,
                                       workspace=HERE / 'qa', deadline_ns=deadline,
                                       condition='N', expected_asset_sha256=expected_asset, max_calls=4)
        export_code = (BATCH / 'asset/export_snapshot.py').read_text(encoding='utf-8')
        receipt = qa.run(export_code, timeout_s=30)
        save(HERE / 'EXPORT_RECEIPT.json', receipt)
        response = receipt['response']
        assert response['status'] == 'success' and response['result']['executed'] is True
        actual = json.loads(response['result']['result'])
        assert actual['pid'] == qa.process.pid
        assert actual['counts'] == {'objects': 4, 'vertices': 26, 'triangles': 36}
        assert {o['name'] for o in actual['objects']} == {'Target', 'Part_A', 'Part_B', 'Part_C'}
        assert actual['scale_length'] == 1.0
        assert sha(ASSET) == expected_asset == sha(HERE / 'qa/input.blend')
        for obj in actual['objects']:
            assert not obj['modifiers'] and not obj['constraints'] and not obj['animation_present']
            assert obj['parent'] is None and not obj['shape_keys_present']
            assert not obj['object_custom_properties'] and not obj['mesh_custom_properties']
            assert not obj['material_names'] and obj['faces'] == obj['triangles']
            for local, world in zip(obj['vertices_local'], obj['vertices_world']):
                for row in range(3):
                    matrix = obj['matrix_world'][row]
                    assert ((matrix[0] * local[0] + matrix[1] * local[1])
                            + matrix[2] * local[2]) + matrix[3] == world[row]
        save(BATCH / 'asset/ACTUAL_SNAPSHOT.json', actual)
        save(BATCH / 'asset/ASSET_BINDING.json', {
            'asset': 'asset/grooved_rail.blend', 'asset_sha256': expected_asset,
            'QA_asset_copy': 'worker/qa/input.blend', 'QA_asset_copy_sha256': sha(HERE / 'qa/input.blend'),
            'snapshot': 'asset/ACTUAL_SNAPSHOT.json', 'snapshot_sha256': sha(BATCH / 'asset/ACTUAL_SNAPSHOT.json'),
            'build_result_sha256': sha(BATCH / 'asset/BUILD_RESULT.json'),
            'export_receipt_sha256': sha(HERE / 'EXPORT_RECEIPT.json'),
            'counts': actual['counts'], 'specifications': freeze['specifications'],
            'representation': freeze['implementation_representation'],
            'qualification': 'independent oracle pending'})
    except BaseException as error:
        errors.append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
        save(HERE / 'FAILURE.json', {'errors': errors, 'failed_ns': time.perf_counter_ns()})
        raise
    finally:
        if qa is not None:
            close = qa.close()
            save(HERE / 'QA_CLOSE.json', close)
        if builder is not None and builder.poll() is None:
            builder.kill()
            builder.wait(timeout=5)
        ended = time.perf_counter_ns()
        save(HERE / 'PREPARATION.json', {
            'started_ns': started, 'ended_ns': ended, 'elapsed_ns': ended - started,
            'started_utc': started_utc, 'ended_utc': datetime.now(timezone.utc).isoformat(),
            'window_scope': 'controller specification check through private build, QA export and owned close',
            'Blender_sessions_started_or_attempted': sessions_started,
            'builder': build_record, 'QA_close': close, 'errors': errors,
            'asset_sha256': sha(ASSET) if ASSET.is_file() else None,
            'snapshot_sha256': sha(BATCH / 'asset/ACTUAL_SNAPSHOT.json') if (BATCH / 'asset/ACTUAL_SNAPSHOT.json').is_file() else None,
            'models': 0, 'product_processes': 0, 'images': 0,
            'status': 'exported_pending_independent_oracle' if not errors and close and close.get('process_reaped') else 'failed_or_incomplete'})
    assert close['process_reaped'] and close['exit_code'] == 0 and close['error'] is None
    assert qa.status()['closed'] is not None
    print(json.dumps({'status': 'asset_exported_worker_closed', 'asset_sha256': sha(ASSET),
                      'snapshot_sha256': sha(BATCH / 'asset/ACTUAL_SNAPSHOT.json'),
                      'Blender_sessions': sessions_started}))


if __name__ == '__main__':
    main()
