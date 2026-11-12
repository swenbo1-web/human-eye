"""QA-only stdin wrapper around the unmodified installed Process worker."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path, expected):
    raw = Path(path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def main():
    import bpy
    config_path = Path(__file__).with_suffix('.json')
    config = json.loads(config_path.read_bytes())
    workspace = config_path.parent
    root = Path(sys.argv[sys.argv.index('--')+1]).resolve()
    assert root == Path(config['install_root']).resolve()
    assert Path(bpy.data.filepath).resolve() == Path(config['asset']).resolve()
    assert sha(config['asset']) == config['asset_sha256']
    assert sha(__file__) == config['wrapper_sha256']
    helper = load('_scan_process_qa_pose', config['pose_helper'], config['pose_helper_sha256'])
    worker_path = root/'human_eye_plugin/blender_worker.py'
    worker = load('_scan_installed_fixed_worker', worker_path, config['worker_sha256'])
    patch, _ = helper._load_qa_pose_patch(config['pose_patch'], config['pose_patch_sha256'])
    original = helper._scene_fingerprint(bpy)
    normal_commands, events = [], []
    order = ['capabilities', 'qa_snapshot', 'capture_surface_scan', 'capture_surface_scan',
             'qa_advance', 'qa_snapshot', 'capture_surface_scan', 'shutdown']
    raw_input = sys.stdin

    class QAInput:
        def __init__(self):
            self.index = 0
            self.current = original
            self.advanced = False

        def __iter__(self):
            return self

        def __next__(self):
            while True:
                raw = raw_input.readline()
                if not raw:
                    raise StopIteration
                request = json.loads(raw)
                command = request['command']
                assert self.index < len(order) and command == order[self.index]
                assert time.perf_counter_ns() < config['deadline_ns']
                assert sha(config['asset']) == config['asset_sha256']
                assert helper._scene_fingerprint(bpy) == self.current
                self.index += 1
                if command not in ('qa_snapshot', 'qa_advance'):
                    normal_commands.append(command)
                    return raw
                started = time.perf_counter_ns()
                if command == 'qa_snapshot':
                    expected_state = 'edit' if self.advanced else 'base'
                    assert request['params'] == {'state': expected_state}
                    source = Path(config['snapshot_exporter']).read_bytes()
                    assert hashlib.sha256(source).hexdigest() == config['snapshot_exporter_sha256']
                    stream = io.StringIO()
                    with contextlib.redirect_stdout(stream):
                        exec(compile(source, config['snapshot_exporter'], 'exec', dont_inherit=True), {})
                    result = json.loads(stream.getvalue())
                else:
                    assert not self.advanced
                    assert request['params'] == {'patch_sha256': config['pose_patch_sha256']}
                    result = helper._apply_qa_pose_patch(bpy, patch)
                    self.current = result['after_fingerprint']
                    self.advanced = True
                assert helper._scene_fingerprint(bpy) == self.current
                assert time.perf_counter_ns() < config['deadline_ns']
                events.append({'command': command, 'started_ns': started,
                    'ended_ns': time.perf_counter_ns(), 'scene_fingerprint': self.current})
                worker._emit({'id': request['id'], 'result': result})

    qa_input = QAInput()
    sys.stdin = qa_input
    error = None
    try:
        worker.run_worker(root)
    except BaseException as exc:
        error = repr(exc)
        raise
    finally:
        sys.stdin = raw_input
        closed = {'qa_wrapper': True, 'unmodified_product_worker_sha256': sha(worker_path),
            'normal_commands': normal_commands, 'QA_events': events, 'error': error,
            'strict_sequence_finished': qa_input.index == len(order), 'qa_advanced_once': qa_input.advanced,
            'initial_scene_fingerprint': original, 'accepted_scene_fingerprint': qa_input.current,
            'final_scene_fingerprint': helper._scene_fingerprint(bpy),
            'asset_unchanged': sha(config['asset']) == config['asset_sha256'],
            'scope': 'terminal geometry and file checks plus fixed wrapper code audit',
            'original_product_setter_calls': 0, 'file_save_calls': 0}
        with (workspace/'QA_CLOSED.json').open('x', encoding='utf8', newline='\n') as stream:
            json.dump(closed, stream, indent=2)
            stream.write('\n')


if __name__ == '__main__':
    main()
