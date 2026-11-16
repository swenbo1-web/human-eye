"""Hold the single fixture-authoring Blender separately from read-only qualification."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_global_local_001')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    static = read(HERE / 'oracle/STATIC_QUALIFICATION.json')
    if static.get('passed') is not True or static.get('status') != 'qualified':
        raise ValueError('fixed_recipe_static_not_realized_no_Blender_start')
    folder = RUNTIME / 'fixture_preparation'
    folder.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter_ns()
    deadline = started + 600_000_000_000
    command = ['D:/Tools/blender5.2/blender.exe', '--factory-startup', '--disable-autoexec', '--background', '--python-exit-code', '1',
               '--python', str(HERE / 'fixture/build_asset.py'), '--', '--plan', str(HERE / 'fixture/BUILD_PLAN.json')]
    result = dict(schema='m4-global-local-fixture-preparation-v1', started_ns=started, deadline_ns=deadline,
                  command=command, Blender_process_attempts=1, qualification_owned_starts=0,
                  raster_attempts=0, model_consumers=0, paid_API_calls=0, status='running', errors=[])
    process = None
    specification = importlib.util.spec_from_file_location('_fixture_process_proof', HERE / 'harness/reused/process_proof.py')
    proof = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(proof)
    handle = None
    with (folder / 'STDOUT.bin').open('xb') as out, (folder / 'STDERR.bin').open('xb') as err:
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                cwd=folder, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            save(folder / 'SPAWN.json', dict(pid=process.pid, parent_pid=os.getpid(), command=command,
                 started_ns=started, recorded_ns=time.perf_counter_ns(), original_deadline_ns=deadline))
            identity, handle = proof._windows_runtime_proof(process, process.pid, deadline)
            save(folder / 'RUNTIME_PROOF.json', identity)
            if identity.get('confirmed') is not True:
                raise RuntimeError('fixture_preparation_ownership_unconfirmed')
            while process.poll() is None:
                remaining = (deadline - time.perf_counter_ns()) / 1e9
                if remaining <= 0:
                    raise TimeoutError('fixture_preparation_original_deadline')
                try:
                    process.wait(timeout=min(30, remaining))
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode != 0:
                raise RuntimeError('fixture_preparation_Blender_error')
            binding = read(RUNTIME / 'fixture/ASSET_BINDING.json')
            if sha(RUNTIME / 'fixture/main.blend') != binding['asset_sha256']:
                raise ValueError('fixture_preparation_asset_binding')
            shutil.copyfile(RUNTIME / 'fixture/ASSET_BINDING.json', HERE / 'fixture/ASSET_BINDING.json')
            result['asset_binding_sha256'] = sha(HERE / 'fixture/ASSET_BINDING.json')
            result['asset_sha256'] = binding['asset_sha256']
            result['status'] = 'completed'
        except BaseException as error:
            result['status'] = 'failed'
            result['errors'].append(dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                    result['forced_kill'] = True
                    result['status'] = 'failed'
                result['exit_code'] = process.returncode
                result['process_reaped'] = process.poll() is not None
                result['retained_exit'] = proof._runtime_exit(handle)
                handle = None
                process._handle.Close()
                result['Popen_handle_closed'] = bool(process._handle.closed)
            if handle is not None:
                result['late_retained_exit'] = proof._runtime_exit(handle)
    result['stdout_closed'] = out.closed
    result['stderr_closed'] = err.closed
    result['closed_ns'] = time.perf_counter_ns()
    result['complete_ns'] = result['closed_ns'] - started
    exited = result.get('retained_exit', {})
    if (exited.get('confirmed') is not True or exited.get('exit_code') != 0
            or exited.get('handle_closed') is not True or result['closed_ns'] >= deadline):
        result['status'] = 'failed'
    save(folder / 'RESULT.json', result)
    print(json.dumps(dict(status=result['status'], errors=result['errors'], complete_ms=result['complete_ns']/1e6)))
    if result['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
