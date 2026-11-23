"""Replay both production host read commands over a held local socket."""

import argparse
import json
from pathlib import Path
from runpy import run_path
import sys
from time import perf_counter_ns


HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent/'m2_source_region_selective_residency_001'
OLD = run_path(str(PRIOR/'replay_host.py'))
HOST = run_path(str(HERE/'host.py'))
consume = OLD['run']
require = OLD['require']


def execute(bench, request, script, command, arm, query):
    """Accept only a script reproduced by the pinned installed connector."""
    if arm == 'B':
        return OLD['checked_execution'](bench, request, script, command, arm, query)
    name, params, identity = command['command'], command['params'], command['id']
    require(name == 'capture' and not params, 'standard_full_scene_capture_required')
    require(script == bench.connector._observation_code(name, params, identity),
            'replay_will_only_execute_exact_installed_connector_script')
    response = bench.exchange(request)
    prefix = 'HUMAN_EYE_BLENDER_MCP:'
    text = response['result']['result']
    require(text.startswith(prefix) and text.endswith('\n'), 'replay_fixed_response_missing')
    sample = json.loads(text[len(prefix):])
    require(sample['id'] == identity and 'result' in sample and 'error' not in sample,
            'replay_real_host_command_failed/'+str(sample.get('error')))
    # Maintain only the installed script re-emitter's own expected baseline.
    # The separately owned caller still parses all real outer and inner wires.
    bench.connector._scene_decoder.apply(sample['result'])
    bench.connector._resident_ready = True
    return json.dumps(response, allow_nan=False, ensure_ascii=True, separators=(',', ':')).encode('utf8')


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_held_replay_runtime_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', choices=tuple(HOST['LABELS']), required=True)
    parser.add_argument('--slot-dir', type=Path, required=True)
    args = parser.parse_args()
    globals_ = consume.__globals__
    globals_.update({key:HOST[key] for key in ('RUN','LABELS','BINDINGS','BASE')})
    globals_['__file__'] = __file__
    OLD['serve'].__globals__['checked_execution'] = execute
    return consume(args.label, args.slot_dir.resolve())


if __name__ == '__main__':
    raise SystemExit(main())
