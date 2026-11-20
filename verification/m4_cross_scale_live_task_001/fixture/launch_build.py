"""Start the single registered Blender authoring process and retain its original receipts."""

import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time
import traceback


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_cross_scale_live_task_001')
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
PROOF = HERE.parents[1] / 'm4_global_local_qualification_001/harness/reused/process_proof.py'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, result):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def prepare():
    truth, plan = HERE / 'STATIC_TRUTH.json', HERE / 'BUILD_PLAN.json'
    data = json.loads(truth.read_bytes())
    if sha(BLENDER) != BLENDER_SHA or not data['passed'] or data['current_blender_evaluated_readback']:
        raise ValueError('registered_prebuild_gate_failed')
    if sha(HERE / 'GEOMETRY.json') != data['geometry_sha256'] or sha(HERE / 'ROLE_MAP.json') != data['role_map_sha256']:
        raise ValueError('geometry_or_role_map_changed')
    if (RUNTIME / 'fixture/main.blend').exists():
        raise FileExistsError('the_registered_asset_already_exists')
    folder = RUNTIME / 'fixture_preparation'
    folder.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    deadline = started + 600_000_000_000
    command = [str(BLENDER), '--factory-startup', '--disable-autoexec', '--background', '--python-exit-code', '1',
               '--python', str(HERE / 'build_asset.py'), '--', '--plan', str(plan)]
    proof = runpy.run_path(str(PROOF))
    result = {'status': 'failed', 'started_ns': started, 'deadline_ns': deadline, 'command': command,
              'attempts': 1, 'qualification_starts': 0, 'raster_attempts': 0, 'model_consumers': 0,
              'paid_API_calls': 0, 'errors': []}
    save(folder / 'ADMISSION.json', {'started_ns': started, 'deadline_ns': deadline, 'command': command,
                                     'static_truth_sha256': sha(truth), 'plan_sha256': sha(plan)})
    process, handle = None, None
    with (folder / 'STDOUT.bin').open('xb') as out, (folder / 'STDERR.bin').open('xb') as err:
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err, cwd=folder,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            save(folder / 'SPAWN.json', {'pid': process.pid, 'parent_pid': os.getpid(), 'started_ns': started,
                                          'deadline_ns': deadline, 'recorded_ns': time.perf_counter_ns()})
            identity, handle = proof['_windows_runtime_proof'](process, process.pid, deadline)
            save(folder / 'RUNTIME_PROOF.json', identity)
            if not identity['confirmed']:
                raise RuntimeError('fixture_process_ownership_unconfirmed')
            while process.poll() is None:
                remaining = (deadline - time.perf_counter_ns()) / 1e9
                if remaining <= 0:
                    raise TimeoutError('fixture_preparation_deadline')
                try:
                    process.wait(timeout=min(30, remaining))
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode != 0:
                raise RuntimeError('fixture_builder_returned_nonzero')
            path = RUNTIME / 'fixture/ASSET_BINDING.json'
            binding = json.loads(path.read_bytes())
            if sha(RUNTIME / 'fixture/main.blend') != binding['asset_sha256']:
                raise ValueError('fixture_asset_identity_changed')
            with (HERE / 'ASSET_BINDING.json').open('xb') as stream:
                stream.write(path.read_bytes())
            result.update(status='completed', asset_binding_sha256=sha(path), asset_sha256=binding['asset_sha256'])
        except BaseException as error:
            result['errors'].append({'type': type(error).__name__, 'message': str(error),
                                     'traceback': traceback.format_exc()})
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                    result.update(forced_kill=True, status='failed')
                result.update(exit_code=process.returncode, process_reaped=process.poll() is not None)
                if handle is not None:
                    result['retained_exit'] = proof['_runtime_exit'](handle)
                process._handle.Close()
                result['Popen_handle_closed'] = bool(process._handle.closed)
    closed = time.perf_counter_ns()
    result.update(closed_ns=closed, complete_ns=closed - started, stdout_closed=out.closed, stderr_closed=err.closed)
    exit_proof = result.get('retained_exit', {})
    if not exit_proof.get('confirmed') or not exit_proof.get('handle_closed') or exit_proof.get('exit_code') != 0 or closed >= deadline:
        result['status'] = 'failed'
    save(folder / 'RESULT.json', result)
    print(json.dumps({'status': result['status'], 'errors': result['errors'], 'complete_ns': result['complete_ns']}))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(prepare())
