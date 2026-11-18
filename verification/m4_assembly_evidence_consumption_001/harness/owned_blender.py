"""Single-use read-only Blender host for the fixed assembly scene."""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import traceback
import uuid

sys.dont_write_bytecode = True
MAX_CODE = 256 * 1024
MAX_REQUEST = 6 * MAX_CODE + 4096
MAX_OUTPUT = 8 * 1024 * 1024
MAX_WIRE = 20 * 1024 * 1024
NAMES = {f'N{number:02d}' for number in range(1, 29)}
WIRE_METER = Path(__file__).resolve().parents[2] / 'm4_live_assembly_relation_task_001/harness/reused/wire_meter.py'


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode('ascii') + b'\n'


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value, mode='xb'):
    with path.open(mode) as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def check(deadline_ns):
    if time.perf_counter_ns() >= deadline_ns:
        raise TimeoutError('owned_Blender_deadline')


def read_only_sources(config):
    copy = Path(config['asset_copy'])
    return (not copy.stat().st_mode & stat.S_IWRITE
            and sha(config['asset']) == sha(copy) == config['asset_sha256'])


def publish_ready(path, value, deadline):
    stage = path.with_name(path.name + '.ready-stage-' + uuid.uuid4().hex)
    check(deadline)
    try:
        write(stage, value)
        if stage.read_bytes() != encoded(value):
            raise ValueError('Blender_ready_staging_readback')
        check(deadline)
        os.link(stage, path)
        if path.read_bytes() != encoded(value):
            raise ValueError('Blender_ready_published_readback')
        check(deadline)
    finally:
        stage.unlink(missing_ok=True)


def _layer_state(layer):
    return {'name': layer.name, 'collection': layer.collection.name, 'exclude': layer.exclude,
            'hide_viewport': layer.hide_viewport, 'holdout': layer.holdout,
            'indirect_only': layer.indirect_only, 'children': [_layer_state(child) for child in layer.children]}


def _scene_state(bpy, *, detailed):
    scene, layer = bpy.context.scene, bpy.context.view_layer
    objects = []
    for obj in sorted(scene.objects, key=lambda item: item.name):
        row = {'name': obj.name, 'type': obj.type, 'instance_id': str(obj.session_uid),
               'matrix_world': [list(vector) for vector in obj.matrix_world],
               'parent': None if obj.parent is None else obj.parent.name,
               'visible_get': obj.visible_get(view_layer=layer), 'hide_get': obj.hide_get(view_layer=layer),
               'hide_viewport': obj.hide_viewport, 'hide_render': obj.hide_render,
               'display_type': obj.display_type, 'collections': sorted(item.name for item in obj.users_collection)}
        if obj.type == 'MESH':
            mesh = obj.data
            row.update(mesh=mesh.name, vertex_count=len(mesh.vertices), polygon_count=len(mesh.polygons),
                       modifiers=[(mod.type, mod.name, mod.show_viewport, mod.show_render) for mod in obj.modifiers])
            if detailed:
                row.update(vertices=[list(vertex.co) for vertex in mesh.vertices],
                           edges=[list(edge.vertices) for edge in mesh.edges],
                           polygons=[list(face.vertices) for face in mesh.polygons])
        objects.append(row)
    return {'objects': objects, 'scene': scene.name, 'frame': scene.frame_current,
            'subframe': scene.frame_subframe, 'scale_length': scene.unit_settings.scale_length,
            'view_layer': layer.name, 'view_layer_id': 'rna:' + str(layer.as_pointer()),
            'layer_collections': _layer_state(layer.layer_collection),
            'asset_copy': bpy.data.filepath}


class _LimitedText(io.StringIO):
    def __init__(self):
        super().__init__()
        self.count = 0

    def write(self, value):
        self.count += len(value.encode('utf8'))
        if self.count > MAX_OUTPUT:
            raise ValueError('Blender_script_output_limit')
        return super().write(value)


def _read_request(connection, deadline):
    raw = bytearray()
    while len(raw) < MAX_REQUEST:
        check(deadline)
        connection.settimeout(max(0.001, (deadline - time.perf_counter_ns()) / 1e9))
        chunk = connection.recv(min(65536, MAX_REQUEST - len(raw)))
        if not chunk:
            raise ValueError('Blender_request_incomplete')
        raw.extend(chunk)
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            continue
    raise ValueError('Blender_request_byte_limit')


def _execute(request, workspace, sequence, namespace):
    params = request.get('params')
    if (set(request) != {'type', 'params'} or request['type'] != 'execute_code'
            or type(params) is not dict or set(params) != {'code'}):
        raise ValueError('Blender_execute_code_request_required')
    code = params['code']
    if type(code) is not str or len(code.encode('utf8')) > MAX_CODE:
        raise ValueError('Blender_request_code_limit')
    folder = workspace / f'call_{sequence}'
    folder.mkdir()
    script = folder / 'SCRIPT.py'
    script.write_text(code, encoding='utf8', newline='\n')
    stdout, stderr = _LimitedText(), _LimitedText()
    error = None
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(compile(code, str(script), 'exec'), namespace)
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    out, err = stdout.getvalue(), stderr.getvalue()
    (folder / 'stdout.txt').write_text(out, encoding='utf8', newline='\n')
    (folder / 'stderr.txt').write_text(err, encoding='utf8', newline='\n')
    return out, err, error, sha(script)


def worker(config_path):
    import bpy

    config = json.loads(config_path.read_bytes())
    workspace, deadline = Path(config['workspace']), config['deadline_ns']
    check(deadline)
    if not read_only_sources(config) or Path(bpy.data.filepath).resolve() != Path(config['asset_copy']):
        raise ValueError('Blender_loaded_source_file_binding')
    spec = importlib.util.spec_from_file_location('_assembly_wire_meter', WIRE_METER)
    meter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(meter)
    startup = _scene_state(bpy, detailed=False)
    if {obj['name'] for obj in startup['objects'] if obj['type'] == 'MESH'} != NAMES:
        raise ValueError('fixed_assembly_mesh_inventory_required')
    audit = workspace / 'WORKER_EVENTS.jsonl'
    prohibited = []

    def record_callback(name):
        def callback(*_):
            prohibited.append(name)
            write(audit, {'event': name, 'at_ns': time.perf_counter_ns()}, 'ab')
        return callback

    for name in ('render_pre', 'save_pre', 'load_pre'):
        getattr(bpy.app.handlers, name).append(record_callback(name))
    stopped = threading.Event()

    def watchdog():
        while not stopped.is_set():
            remaining = (deadline - time.perf_counter_ns()) / 1e9
            if remaining <= 0:
                os._exit(124)
            if any((workspace / name).stat().st_size > 64 * 1024 * 1024
                   for name in ('worker_stdout.txt', 'worker_stderr.txt')):
                os._exit(125)
            stopped.wait(min(0.05, remaining))

    watch = threading.Thread(target=watchdog, daemon=True, name='owned-assembly-watchdog')
    namespace = {'__name__': '__owned_assembly_task__', 'bpy': bpy}
    poison_path = workspace / 'POISONED.json'
    initial = None
    poisoned = False
    watch.start()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(('127.0.0.1', 0))
            server.listen(2)
            publish_ready(workspace / 'READY.json', {'host': '127.0.0.1', 'port': server.getsockname()[1],
                          'pid': os.getpid(), 'deadline_ns': deadline, 'initial_fingerprint': digest(startup),
                          'helper_sha256': sha(__file__)}, deadline)
            sequence = 0
            while not poisoned and not poison_path.exists():
                check(deadline)
                server.settimeout(max(0.001, (deadline - time.perf_counter_ns()) / 1e9))
                network, _ = server.accept()
                sequence += 1
                with meter.WireSocket(network, sequence) as connection:
                    started = time.perf_counter_ns()
                    before = meter.host_work()
                    event = {'sequence': sequence, 'started_ns': started}
                    closing = False
                    try:
                        request = _read_request(connection, deadline)
                        closing = request == {'type': 'close'}
                        if closing:
                            response = {'status': 'closed', 'pid': os.getpid(), 'deadline_ns': deadline}
                            event['status'] = 'closed'
                        else:
                            if sequence > config['max_calls']:
                                raise ValueError('Blender_host_request_limit')
                            if initial is None:
                                initial = _scene_state(bpy, detailed=True)
                                if _scene_state(bpy, detailed=False) != startup:
                                    raise RuntimeError('scene_changed_before_first_request')
                                event['geometry_guard_established_ns'] = time.perf_counter_ns()
                            if _scene_state(bpy, detailed=True) != initial or not read_only_sources(config):
                                raise RuntimeError('scene_or_source_changed_before_request')
                            out, err, error, script_sha = _execute(request, workspace, sequence, namespace)
                            check(deadline)
                            intact = (not prohibited and not poison_path.exists() and read_only_sources(config)
                                      and _scene_state(bpy, detailed=True) == initial)
                            if not intact:
                                poisoned = True
                                error = {'type': 'StateChanged', 'message': 'owned read-only state protection failed'}
                            event.update(script_sha256=script_sha, stdout_bytes=len(out.encode()),
                                         stderr_bytes=len(err.encode()), script_error=error,
                                         terminal_geometry_and_file_checks_passed=intact,
                                         status='completed' if error is None else 'script_failed' if intact else 'state_changed')
                            response = ({'status': 'success', 'result': {'executed': True, 'result': out}}
                                        if error is None else {'status': 'error', 'error': error, 'stdout': out,
                                                               'stderr': err, 'poisoned': poisoned})
                    except BaseException as exc:
                        poisoned |= isinstance(exc, (RuntimeError, TimeoutError))
                        error = {'type': type(exc).__name__, 'message': str(exc)}
                        event.update(status='transport_or_guard_error', error=error)
                        response = {'status': 'error', 'error': error}
                    finally:
                        event['m2_work'] = meter.finish_rpc(before, namespace)
                        event['elapsed_ns'] = time.perf_counter_ns() - started
                        write(audit, event, 'ab')
                    wire = encoded(response)
                    if len(wire) > MAX_WIRE:
                        poisoned = True
                        wire = encoded({'status': 'error', 'error': {'type': 'ValueError', 'message': 'Blender_response_byte_limit'}})
                    try:
                        connection.sendall(wire)
                    except OSError as exc:
                        poisoned = True
                        write(audit, {'event': 'response_send_unknown', 'sequence': sequence,
                                      'error_type': type(exc).__name__, 'at_ns': time.perf_counter_ns()}, 'ab')
                    if closing:
                        break
        final = _scene_state(bpy, detailed=initial is not None)
        baseline = startup if initial is None else initial
        if poisoned and not poison_path.exists():
            write(poison_path, {'reason': 'worker_state_or_transport_unconfirmed', 'at_ns': time.perf_counter_ns()})
        meter.flush(workspace)
        write(workspace / 'WORKER_CLOSED.json', {'pid': os.getpid(), 'closed_ns': time.perf_counter_ns(),
              'original_deadline_ns': deadline, 'poisoned': poisoned or poison_path.exists(),
              'initial_geometry_fingerprint': digest(baseline), 'final_geometry_fingerprint': digest(final),
              'full_initial_state': baseline, 'full_final_state': final, 'scene_unchanged': final == baseline,
              'prohibited_events': prohibited, 'protected_files_unchanged': read_only_sources(config)})
    finally:
        stopped.set()
        watch.join(timeout=1)


class NativeSession:
    @classmethod
    def start(cls, *, blender, asset, workspace, deadline_ns, condition, expected_asset_sha256, max_calls):
        started = time.perf_counter_ns()
        startup_deadline = min(deadline_ns, started + 30_000_000_000)
        check(startup_deadline)
        if deadline_ns - started > 600_000_000_000 or condition not in ('A', 'B') or not 1 <= max_calls <= 128:
            raise ValueError('owned_Blender_session_parameters')
        self = cls()
        self.workspace, self.process = Path(workspace).resolve(), None
        self.workspace.mkdir(parents=True)
        try:
            asset, blender = Path(asset).resolve(strict=True), Path(blender).resolve(strict=True)
            if sha(asset) != expected_asset_sha256:
                raise ValueError('original_assembly_asset_digest_mismatch')
            copied = self.workspace / 'input.blend'
            shutil.copyfile(asset, copied)
            copied.chmod(stat.S_IREAD)
            worker_path = Path(__file__).resolve()
            self.config = {'schema': 'm4-live-assembly-native-session-v1', 'workspace': str(self.workspace),
                           'asset': str(asset), 'asset_copy': str(copied), 'asset_sha256': expected_asset_sha256,
                           'blender': str(blender), 'blender_sha256': sha(blender), 'helper_sha256': sha(worker_path),
                           'deadline_ns': deadline_ns, 'condition': condition, 'max_calls': max_calls, 'started_ns': started}
            if not read_only_sources(self.config):
                raise ValueError('read_only_assembly_copy_required')
            configuration = self.workspace / 'CONFIG.json'
            write(configuration, self.config)
            command = [str(blender), '--factory-startup', '--disable-autoexec', '--background', str(copied),
                       '--python-exit-code', '1', '--python', str(worker_path), '--', '--worker', str(configuration)]
            check(startup_deadline)
            with (self.workspace / 'worker_stdout.txt').open('xb') as out, (self.workspace / 'worker_stderr.txt').open('xb') as err:
                self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                    cwd=self.workspace, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), shell=False)
            write(self.workspace / 'SPAWN.json', {'pid': self.process.pid, 'parent_pid': os.getpid(),
                  'created_after_ns': started, 'recorded_ns': time.perf_counter_ns(), 'command': command,
                  'image_sha256': self.config['blender_sha256'], 'helper_sha256': self.config['helper_sha256'],
                  'asset_sha256': expected_asset_sha256, 'original_deadline_ns': deadline_ns})
            ready = self.workspace / 'READY.json'
            while not ready.exists():
                check(startup_deadline)
                if self.process.poll() is not None:
                    raise RuntimeError('Blender_worker_start_failed')
                time.sleep(0.01)
            self.ready = json.loads(ready.read_bytes())
            self.host, self.port = self.ready['host'], self.ready['port']
            if (self.host != '127.0.0.1' or type(self.port) is not int or not 1 <= self.port <= 65535
                    or self.ready['pid'] != self.process.pid or self.ready['deadline_ns'] != deadline_ns
                    or self.ready['helper_sha256'] != self.config['helper_sha256']
                    or self.config['helper_sha256'] != sha(worker_path)
                    or not read_only_sources(self.config) or self.process.poll() is not None):
                raise RuntimeError('owned_Blender_ready_binding')
            self.config.update(pid=self.process.pid, host=self.host, port=self.port,
                               startup_ns=time.perf_counter_ns() - started)
            write(self.workspace / 'SESSION.json', self.config)
            check(startup_deadline)
            return self
        except BaseException as exc:
            try:
                self._kill()
                write(self.workspace / 'START_FAILURE.json', {'type': type(exc).__name__, 'reason': str(exc),
                      'elapsed_ns': time.perf_counter_ns() - started})
            except BaseException as cleanup:
                exc.add_note('Blender startup cleanup failed: ' + repr(cleanup))
            raise

    def _exchange(self, request, timeout_s):
        if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError('Blender_call_timeout_required')
        deadline = min(self.config['deadline_ns'], time.perf_counter_ns() + int(timeout_s * 1e9))
        check(deadline)
        raw = bytearray()
        with socket.create_connection((self.host, self.port), timeout=(deadline - time.perf_counter_ns()) / 1e9) as connection:
            connection.settimeout(max(0.001, (deadline - time.perf_counter_ns()) / 1e9))
            connection.sendall(encoded(request))
            connection.shutdown(socket.SHUT_WR)
            while True:
                check(deadline)
                connection.settimeout(max(0.001, (deadline - time.perf_counter_ns()) / 1e9))
                chunk = connection.recv(65536)
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > MAX_WIRE:
                    raise ValueError('Blender_response_byte_limit')
        check(deadline)
        return json.loads(raw)

    def run(self, code, *, timeout_s):
        poison = self.workspace / 'POISONED.json'
        if poison.exists():
            raise RuntimeError('owned_Blender_state_unconfirmed')
        try:
            response = self._exchange({'type': 'execute_code', 'params': {'code': code}}, timeout_s)
        except (OSError, ValueError) as exc:
            try:
                if not poison.exists():
                    write(poison, {'reason': 'client_transport_unknown', 'type': type(exc).__name__,
                          'message': str(exc), 'at_ns': time.perf_counter_ns()})
            finally:
                self._kill()
            raise
        return {'response': response}

    def _kill(self):
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)

    def close(self):
        response = error = None
        try:
            response = self._exchange({'type': 'close'}, timeout_s=5)
        except Exception as exc:
            error = {'type': type(exc).__name__, 'reason': str(exc)}
        finally:
            try:
                self.process.wait(timeout=min(5, max(0.001, (self.config['deadline_ns'] - time.perf_counter_ns()) / 1e9)))
            except subprocess.TimeoutExpired:
                self._kill()
        result = {'schema': 'm4-live-assembly-native-close-v1', 'pid': self.process.pid,
                  'response': response, 'error': error, 'exit_code': self.process.poll(),
                  'process_reaped': self.process.poll() is not None, 'original_deadline_ns': self.config['deadline_ns'],
                  'source_file_unchanged': sha(self.config['asset']) == self.config['asset_sha256'],
                  'protected_files_unchanged': read_only_sources(self.config)}
        write(self.workspace / ('CLOSE_' + uuid.uuid4().hex + '.json'), result)
        return result

    def status(self):
        closed = self.workspace / 'WORKER_CLOSED.json'
        return {'config': self.config, 'ready': self.ready,
                'closed': json.loads(closed.read_bytes()) if closed.exists() else None,
                'protected_files_unchanged': read_only_sources(self.config)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    worker(parser.parse_args(sys.argv[sys.argv.index('--') + 1:]).worker)
