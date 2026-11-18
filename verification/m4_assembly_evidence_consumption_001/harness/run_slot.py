"""Execute one registered slot and close its owned processes before publication."""

import argparse
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import EXTERNAL, NS, product_binding, read, save, sha
from owned_runtime import Runtime


def load_slot_dependencies(dependency_root, shared_dependency_root):
    """Load the formal bridge with both registered library roots."""
    sys.path[:0] = [str(NS), str(Path(dependency_root).resolve()), str(Path(shared_dependency_root).resolve())]
    from bridge import Owner
    from consumer_adapter import consume_slot
    return Owner, consume_slot


def ensure_closure(closure):
    native = closure['Blender_close']
    terminal = closure['Blender_status']['closed']
    if (closure['errors'] or native['exit_code'] != 0 or not native['process_reaped'] or not terminal
            or terminal['poisoned'] or not terminal['scene_unchanged']
            or terminal['initial_geometry_fingerprint'] != terminal['final_geometry_fingerprint']
            or not native['source_file_unchanged'] or not native['protected_files_unchanged']
            or not closure['Blender_exit']['exited'] or not closure['Blender_exit']['handle_closed']):
        raise RuntimeError('owned_Blender_closure_or_scene_identity_failed')
    if (not closure['public_MCP_close']['confirmed'] or not closure['public_MCP_exit']['exited']
            or not closure['public_MCP_exit']['handle_closed']):
        raise RuntimeError('installed_public_MCP_close_failed')


def run(label):
    began = time.perf_counter_ns()
    task_deadline = began + 450_000_000_000
    owned_deadline = began + 600_000_000_000
    group = label[0]
    folder = EXTERNAL / 'slots' / label
    if label == 'B1' and not (folder.parent / 'A1/SLOT_PUBLICATION.json').is_file():
        raise ValueError('A1_publication_required_before_B1')
    folder.mkdir(parents=True, exist_ok=False)
    result = {'slot': label, 'group': group, 'status': 'failed', 'errors': [], 'started_ns': began,
              'task_deadline_ns': task_deadline, 'owned_deadline_ns': owned_deadline,
              'actual_model_admitted': False}
    save(folder / 'SLOT_STARTED.json', result)
    runtime = owner = None
    try:
        frozen_path = NS / 'FROZEN.json'
        frozen = read(frozen_path)
        result['freeze_sha256'] = sha(frozen_path)
        for row in frozen['direct_inputs']:
            path = Path(row['path'])
            if path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
                raise ValueError('frozen_input_changed/' + str(path))
        _, binding = product_binding(label)
        Owner, consume_slot = load_slot_dependencies(binding['dependency_root'], frozen['shared_dependency_root'])

        runtime = Runtime(folder, label, group, task_deadline, owned_deadline)
        runtime.start()
        output = folder / 'owner'
        assembly = NS / 'inputs/ASSEMBLY.json'
        config = {'label': label, 'group': group, 'phase': 'formal',
                  'worker_deadline_ns': task_deadline, 'output': str(output),
                  'assembly_path': str(assembly), 'assembly_sha256': sha(assembly)}
        owner = Owner(runtime, config, budget=runtime.budget)
        result['actual_dependency_modules'] = {
            name: {'path': str(Path(sys.modules[name].__file__).resolve()), 'version': sys.modules[name].__version__}
            for name in ('numpy', 'PIL', 'shapely')}
        runtime.prepare_device()
        endpoint = owner.start(folder / 'ENDPOINT.json')
        result['ready_ns'] = time.perf_counter_ns()
        runtime.budget.reserve('consumer_task', label, 'formal')
        result['actual_model_admitted'] = True
        envelope = consume_slot(slot_id=label, group=group, slot_root=folder, endpoint=endpoint,
                                owner_output=output, deadline_ns=task_deadline, owned_deadline_ns=owned_deadline,
                                model_consumer_enabled=True)
        save(folder / 'CONSUMER_ENVELOPE.json', envelope)
        result['consumer_returned_ns'] = time.perf_counter_ns()
        consumer = read(folder / 'consumer/CONSUMER.json')
        result['consumer'] = {key: consumer.get(key) for key in ('status', 'valid_completion', 'final_received_ns',
            'prompt_submitted_ns', 'raw_usage_events', 'thread_id', 'tool_accounting', 'public_image_count',
            'public_image_bytes', 'bridge_public_text_bytes', 'errors', 'exit_code', 'runtime_exit',
            'process_reaped', 'readers_stopped')}
        if (not consumer.get('valid_completion') or result['consumer_returned_ns'] >= task_deadline
                or consumer.get('public_image_count') != 0):
            raise RuntimeError('formal_consumer_completion_or_original_deadline_failed')
        result['status'] = 'completed'
    except BaseException as error:
        result['errors'].append({'stage': 'consumer', 'type': type(error).__name__,
                                 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        def capture(stage, action):
            try:
                return action()
            except BaseException as error:
                result['status'] = 'failed'
                result['errors'].append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})

        if owner is not None:
            closed = capture('owner_close', owner.close)
            if closed is not None and closed.get('confirmed') is not True:
                result['status'] = 'failed'
                result['errors'].append({'stage': 'owner_close', 'detail': closed})
        if runtime is not None:
            if runtime.device is not None:
                result['terminal_source'] = capture('terminal_export', runtime.device.export_terminal)
            closure = capture('runtime_close', lambda: runtime.close(result['status']))
            if closure is not None:
                capture('closure_verification', lambda: ensure_closure(closure))
            result['budget'] = capture('budget_snapshot', runtime.budget.snapshot)
        answer = folder / 'consumer/PUBLIC_FINAL.txt'
        if answer.is_file():
            result['answer'] = {'path': str(answer), 'sha256': sha(answer), 'bytes': answer.stat().st_size}
        result['closed_ns'] = time.perf_counter_ns()
        if result['closed_ns'] >= owned_deadline:
            result['status'] = 'failed'
            result['errors'].append({'stage': 'publication', 'message': 'owned_deadline_exceeded'})
        save(folder / 'SLOT_RESULT.json', result)
        save(folder / 'SLOT_PUBLICATION.json', {'slot': label, 'status': result['status'], 'started_ns': began,
             'published_ns': time.perf_counter_ns(), 'result_sha256': sha(folder / 'SLOT_RESULT.json')})
    print(label, result['status'], round((result['closed_ns'] - began) / 1e9, 3), 'seconds',
          'errors:', [error['stage'] for error in result['errors']])
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slot', choices=('A1', 'B1'))
    raise SystemExit(run(parser.parse_args().slot))
