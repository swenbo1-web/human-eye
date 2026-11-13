"""Local fresh-render smoke using the actual shared actor, without a model."""

import argparse
import importlib.util
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--group', choices=['N', 'P'], required=True)
    options = parser.parse_args()
    folder = HERE / 'local' / ('render_' + options.group)
    folder.mkdir(parents=True, exist_ok=False)
    specification = importlib.util.spec_from_file_location('_local_smoke_actor', HERE / 'actor.py')
    actor = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(actor)
    config = {'group': options.group, 'output': str(folder / 'o'),
              'endpoint': str(folder / 'ENDPOINT.json'),
              'worker_deadline_ns': time.perf_counter_ns() + 450_000_000_000,
              'input_manifest': str(HERE / 'inputs/SOURCES.json'),
              'max_tool_calls': 12, 'max_render_attempts': 6}
    owner = actor.Owner(config)
    errors = []
    checks = []
    replies = []

    def invoke(name, arguments):
        reply = owner.handle({'jsonrpc': '2.0', 'id': len(replies) + 1,
                              'method': 'tools/call',
                              'params': {'name': name, 'arguments': arguments}})
        replies.append(reply)
        if reply['result'].get('isError'):
            raise RuntimeError('local_tool_failed_' + name)
        return reply['result']

    try:
        if options.group == 'P':
            result = invoke('active_coverage', {'include_images': True})
            count = len(owner.session.attempts)
            checks.append({'check': 'fresh_active_observations', 'passed': count > 0})
            checks.append({'check': 'active_real_images', 'passed':
                           sum(block['type'] == 'image' for block in result['content']) == count})
            invoke('active_coverage', {'include_images': False})
            checks.append({'check': 'repeat_active_cache', 'passed': len(owner.session.attempts) == count})
            invoke('execute_python', {'code':
                   "rows = render_views(list(buffers), include_images=False)\n"
                   "assert all(row['cached'] for row in rows)\nprint(rows)"})
            checks.append({'check': 'shared_batch_cache', 'passed': len(owner.session.attempts) == count})
        else:
            result = invoke('execute_python', {'code':
                   "assert len(geometry['objects']) == 28\n"
                   "rows = render_views(['SCENE', 'BACK'], include_images=True)\n"
                   "assert set(buffers) == {'SCENE', 'BACK'}\n"
                   "assert buffers['SCENE']['owners'].shape == (512, 512)\nprint(rows)"})
            checks.append({'check': 'native_computation_batch_images_one_call', 'passed':
                           sum(block['type'] == 'image' for block in result['content']) == 2})
            invoke('render_views', {'names': ['SCENE', 'BACK'], 'include_images': False})
            checks.append({'check': 'native_repeat_batch_cache', 'passed': len(owner.session.attempts) == 2})
            checks.append({'check': 'native_no_private_entry', 'passed':
                           'active_coverage' not in {tool['name'] for tool in owner.tools}})
        checks.append({'check': 'no_runtime_faults', 'passed': not owner.session.runtime_faults})
    except BaseException as error:
        errors.append({'type': type(error).__name__, 'message': str(error)})
    finally:
        close = owner.close(True, errors)
    value = {'group': options.group, 'checks': checks, 'errors': errors,
             'passed': bool(checks) and all(row['passed'] for row in checks) and not errors,
             'metrics': close['metrics'], 'real_Pro_sessions': 0,
             'scope': 'Local actor calls, actual fresh common raster and image construction. No network image delivery or model.'}
    (folder / 'SMOKE_RESULT.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'group': options.group, 'passed': value['passed'],
                      'render_attempts': len(owner.session.attempts), 'errors': errors}))
    if not value['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
