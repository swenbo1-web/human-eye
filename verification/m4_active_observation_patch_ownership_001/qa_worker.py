"""Private, temporary Blender owner for the split/join patch contract.

The controller launches this script in its own background Blender. Importing
the module creates no scene. The sole private geometry change replaces the
frozen split input with its frozen joined representation once.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import socket
import sys
import time
import traceback
from fractions import Fraction
from pathlib import Path


MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_BYTES = 32 * 1024 * 1024


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')


def save(path, value):
    with Path(path).open('xb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def append(path, value):
    with Path(path).open('ab') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def check(deadline):
    if time.perf_counter_ns() >= deadline:
        raise TimeoutError('original_QA_deadline_exceeded')


def snapshot(bpy):
    return {
        'unit_system': bpy.context.scene.unit_settings.system,
        'scale_length': bpy.context.scene.unit_settings.scale_length,
        'objects': [
            {'name': obj.name, 'vertices': [list(vertex.co) for vertex in obj.data.vertices],
             'faces': [list(face.vertices) for face in obj.data.polygons],
             'matrix_world': [list(row) for row in obj.matrix_world]}
            for obj in sorted(bpy.context.scene.objects, key=lambda obj: obj.name) if obj.type == 'MESH'
        ],
    }


def create_mesh(bpy, name, vertices, triangles):
    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata([[float(Fraction(value)) for value in vertex] for vertex in vertices], [], triangles)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def clear_scene(bpy):
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def load_fixture(config, name):
    raw = Path(config[name + '_fixture']).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != config[name + '_fixture_sha256']:
        raise ValueError(name + '_fixture_sha256_changed')
    return json.loads(raw)


def build_fixture(bpy, fixture):
    clear_scene(bpy)
    for obj in fixture['objects']:
        create_mesh(bpy, obj['name'], obj['vertices'], obj['triangles'])
    bpy.context.view_layer.update()


def read_request(connection, deadline):
    raw = bytearray()
    while True:
        check(deadline)
        connection.settimeout(min(30, (deadline - time.perf_counter_ns()) / 1e9))
        chunk = connection.recv(65536)
        if not chunk:
            break
        raw.extend(chunk)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError('QA_request_bytes_exceeded')
        try:
            return json.loads(raw), bytes(raw)
        except (ValueError, UnicodeDecodeError):
            continue
    return json.loads(raw), bytes(raw)


def run(config_path):
    import bpy

    config = json.loads(Path(config_path).read_bytes())
    folder = Path(config['workspace']).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    deadline = config['deadline_ns']
    check(deadline)
    split_fixture = load_fixture(config, 'split')
    joined_fixture = load_fixture(config, 'joined')
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.0
    build_fixture(bpy, split_fixture)
    initial = snapshot(bpy)
    save(folder / 'INITIAL.json', initial)
    stage = 'split'
    namespace = {'__name__': '__owned_patch_ownership_QA__', 'bpy': bpy}
    sequence = 0
    close_requested = False
    poisoned = False
    failure = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(('127.0.0.1', 0))
            server.listen(2)
            save(folder / 'READY.json', {
                'host': '127.0.0.1', 'port': server.getsockname()[1], 'pid': os.getpid(),
                'deadline_ns': deadline, 'worker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'split_fixture_sha256': config['split_fixture_sha256'],
                'joined_fixture_sha256': config['joined_fixture_sha256'], 'stage': stage,
            })
            while not close_requested and not poisoned:
                check(deadline)
                server.settimeout(min(30, (deadline - time.perf_counter_ns()) / 1e9))
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue
                with connection:
                    started = time.perf_counter_ns()
                    sequence += 1
                    call = folder / ('rpc_' + str(sequence).zfill(3))
                    call.mkdir()
                    row = {'sequence': sequence, 'started_ns': started, 'stage_before': stage, 'mutation_scope': 'private_QA_only'}
                    try:
                        request, tx = read_request(connection, deadline)
                        (call / 'TX.bin').write_bytes(tx)
                        row['request_read_closed_ns'] = time.perf_counter_ns()
                        assert sequence <= config.get('max_calls', 64)
                        assert type(request) is dict and set(request) == {'type', 'params'}
                        kind, params = request['type'], request['params']
                        row['type'] = kind
                        row['readonly_guard_started_ns'] = time.perf_counter_ns()
                        before = snapshot(bpy)
                        row['readonly_guard_before_closed_ns'] = time.perf_counter_ns()
                        if kind == 'execute_code':
                            assert type(params) is dict and set(params) == {'code'} and type(params['code']) is str
                            code = params['code']
                            (call / 'SCRIPT.py').write_text(code, encoding='utf8')
                            output = io.StringIO()
                            row['execution_started_ns'] = time.perf_counter_ns()
                            with contextlib.redirect_stdout(output):
                                exec(compile(code, str(call / 'SCRIPT.py'), 'exec'), namespace)
                            row['execution_closed_ns'] = time.perf_counter_ns()
                            assert snapshot(bpy) == before, 'readonly_host_changed_geometry_or_names'
                            row['readonly_guard_after_closed_ns'] = time.perf_counter_ns()
                            response = {'status': 'success', 'result': {'executed': True, 'result': output.getvalue()}}
                        else:
                            assert params == {}
                            if kind == 'qa_snapshot':
                                response = {'status': 'success', 'result': {'stage': stage, 'snapshot': before}}
                            elif kind == 'qa_join':
                                assert stage == 'split', 'QA_join_once_after_split'
                                build_fixture(bpy, joined_fixture)
                                stage = 'joined'
                                response = {'status': 'success', 'result': {'stage': stage, 'snapshot': snapshot(bpy)}}
                            elif kind == 'close':
                                close_requested = True
                                response = {'status': 'closed', 'pid': os.getpid(), 'stage': stage}
                            else:
                                raise ValueError('unknown_private_QA_operation')
                        check(deadline)
                        row['status'] = 'completed'
                    except BaseException as exc:
                        poisoned = True
                        row['status'] = 'failed'
                        row['error'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
                        response = {'status': 'error', 'error': row['error']}
                    wire = encoded(response)
                    assert len(wire) <= MAX_RESPONSE_BYTES
                    (call / 'RX.bin').write_bytes(wire)
                    row['response_archived_ns'] = time.perf_counter_ns()
                    connection.sendall(wire)
                    row.update(stage_after=stage, received_bytes=(call / 'TX.bin').stat().st_size if (call / 'TX.bin').exists() else None,
                               response_bytes=len(wire), closed_ns=time.perf_counter_ns())
                    row['elapsed_ns'] = row['closed_ns'] - started
                    append(folder / 'EVENTS.jsonl', row)
    except BaseException as exc:
        failure = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
        raise
    finally:
        save(folder / 'CLOSE.json', {'pid': os.getpid(), 'closed_ns': time.perf_counter_ns(), 'close_requested': close_requested,
                                   'poisoned': poisoned, 'stage': stage, 'requests': sequence, 'failure': failure, 'final_snapshot': snapshot(bpy),
                                   'split_fixture_sha256': config['split_fixture_sha256'],
                                   'joined_fixture_sha256': config['joined_fixture_sha256'],
                                   'Blender_render_calls': 0, 'file_saves': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None
    run(parser.parse_args(arguments).config)
