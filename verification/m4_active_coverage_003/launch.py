"""One direct base-interpreter command and original-handle cleanup path."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
BASE = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
BASE_SHA256 = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
SITE = Path('D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Lib/site-packages')
BOOTSTRAP = HERE / 'bootstrap.py'
PRODUCT = HERE.parents[1] / '.human-eye/releases/9.7.2+m4.surface.scan.compact.r1/site-packages'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def describe():
    """Read the static contract without importing calculation dependencies."""
    if sha(BASE) != BASE_SHA256:
        raise ValueError('bound_base_interpreter_sha256_changed')
    manifest_path = HERE / 'inputs/DEPENDENCIES.json'
    manifest = json.loads(manifest_path.read_bytes())
    return {'base_executable': str(BASE.resolve()), 'base_executable_sha256': BASE_SHA256,
            'bootstrap_path': str(BOOTSTRAP.resolve()), 'bootstrap_sha256': sha(BOOTSTRAP),
            'explicit_site_packages': str(SITE.resolve()), 'product_install_root': str(PRODUCT.resolve()),
            'dependency_manifest_path': str(manifest_path.resolve()), 'dependency_manifest_sha256': sha(manifest_path),
            'expected_dependencies': {
                'numpy': {'path': str((SITE / 'numpy/__init__.py').resolve()), 'version': manifest['numpy_version'],
                          'init_sha256': sha(SITE / 'numpy/__init__.py')},
                'pillow': {'path': str((SITE / 'PIL/__init__.py').resolve()), 'version': manifest['Pillow_version'],
                           'init_sha256': sha(SITE / 'PIL/__init__.py')}}}


def python_command(entry, arguments):
    contract = describe()
    return [contract['base_executable'], '-I', '-B', '-X', 'utf8',
            contract['bootstrap_path'], str(Path(entry).resolve()), *[str(value) for value in arguments]]


def stop_process(process, timeout=5):
    """Reap and finally close the held process handle without PID lookup."""
    started = time.perf_counter_ns()
    result = {'pid': process.pid, 'kill_requested': False, 'exit_code': None, 'reaped': False,
              'wait_timeout_s': timeout, 'pipes_closed': {}, 'process_handle_closed': False, 'errors': []}
    try:
        if process.poll() is None:
            result['kill_requested'] = True
            process.kill()
    except BaseException as error:
        result['errors'].append({'stage': 'kill', 'type': type(error).__name__, 'message': str(error)})
    try:
        result['exit_code'] = process.wait(timeout=timeout)
        result['reaped'] = process.poll() is not None
    except BaseException as error:
        result['errors'].append({'stage': 'kill_wait', 'type': type(error).__name__, 'message': str(error)})
        result['exit_code'] = process.returncode
    for name in ('stdin', 'stdout', 'stderr'):
        stream = getattr(process, name, None)
        try:
            if stream is not None:
                stream.close()
            result['pipes_closed'][name] = stream is None or stream.closed
        except BaseException as error:
            result['pipes_closed'][name] = False
            result['errors'].append({'stage': 'close_' + name, 'type': type(error).__name__, 'message': str(error)})
    if result['reaped']:
        try:
            handle = getattr(process, '_handle', None)
            if handle is not None:
                handle.Close()
                result['process_handle_closed'] = handle.closed is True
            else:
                result['process_handle_closed'] = os.name != 'nt'
        except BaseException as error:
            result['errors'].append({'stage': 'process_handle_close', 'type': type(error).__name__, 'message': str(error)})
    result['confirmed'] = bool(result['reaped'] and result['process_handle_closed']
        and all(result['pipes_closed'].values()) and not result['errors'])
    result['started_ns'] = started
    result['closed_ns'] = time.perf_counter_ns()
    result['elapsed_ns'] = result['closed_ns'] - started
    return result
