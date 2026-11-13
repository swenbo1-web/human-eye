"""Local CLI protocol fixture. It never imports or contacts a model provider."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib


THREAD = '75e546be-1fb7-4e10-87e5-38ef4cd611c6'
OTHER_THREAD = '60047050-f87d-4bf1-850f-104089c73499'


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


def main():
    args = sys.argv[1:]
    command = args.index('exec')
    cli_args = args[command:]
    assert '--ephemeral' not in cli_args
    cwd = Path.cwd()
    assert Path(cli_args[cli_args.index('-C') + 1]).resolve() == cwd
    final = Path(cli_args[cli_args.index('-o') + 1])
    config = None
    for index, value in enumerate(cli_args):
        if value == '-c' and cli_args[index + 1].startswith('mcp_servers.arm_engine='):
            config = tomllib.loads('server=' + cli_args[index + 1].split('=', 1)[1])['server']
    assert config is not None
    marker = cwd / 'SYNTHETIC_THREAD.json'
    resumed = 'resume' in cli_args
    if resumed:
        old = json.loads(marker.read_bytes())
        assert cli_args[-2] == old['thread_id'] == THREAD
        turn = old['turn'] + 1
        marker_value = old['marker']
    else:
        assert not marker.exists()
        turn, marker_value = 1, 'synthetic-retained-workspace'
    prompt = sys.stdin.buffer.read()
    endpoint = Path(config['args'][config['args'].index('--endpoint') + 1])
    endpoint_value = json.loads(endpoint.read_bytes())
    scenario = endpoint_value.get('synthetic_scenario', 'normal')
    assert endpoint_value['host'] == '127.0.0.1'
    assert endpoint_value['chain_deadline_ns'] > time.perf_counter_ns()
    observed = OTHER_THREAD if scenario == 'wrong_thread' and turn == 2 else THREAD
    emit({'type': 'thread.started', 'thread_id': observed})
    emit({'type': 'turn.started'})
    if scenario == 'timeout' and turn == 2:
        time.sleep(10)
    name = 'human_eye_scene_observe' if 'human_eye_scene_observe' in config['tools'] else 'execute_blender_code'
    arguments = ({'session_id': 'synthetic-session', 'include_image': False,
                  'query': {'mode': 'surface_scan', 'threshold_m': .002}} if name == 'human_eye_scene_observe'
                 else {'code': "print('synthetic payload group/id/perf_ns remain business text')"})
    request = {'jsonrpc': '2.0', 'id': 'business-' + str(turn), 'method': 'tools/call',
               'params': {'name': name, 'arguments': arguments}}
    item = {'id': 'tool-' + str(turn), 'type': 'mcp_tool_call', 'server': 'arm_engine',
            'tool': name, 'arguments': arguments}
    emit({'type': 'item.started', 'item': item})
    messages = [
        {'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'}, request]
    wire = b''.join((json.dumps(message) + '\n').encode() for message in messages)
    child = subprocess.run([config['command'], *config['args']], input=wire, capture_output=True,
                           timeout=5, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if child.returncode != 0:
        sys.stderr.buffer.write(child.stderr)
        return child.returncode
    replies = [json.loads(line) for line in child.stdout.splitlines()]
    answer = next(row for row in replies if row.get('id') == request['id'])
    emit({'type': 'item.completed', 'item': {**item, 'result': answer['result']}})
    marker.write_text(json.dumps({'thread_id': THREAD, 'turn': turn, 'marker': marker_value}), encoding='utf8')
    (cwd / ('FAKE_TURN_' + str(turn) + '.json')).write_text(json.dumps({
        'synthetic': True, 'actual_pid': os.getpid(), 'cwd': str(cwd), 'resumed': resumed,
        'observed_thread': observed, 'requested_thread': cli_args[-2] if resumed else None,
        'endpoint': str(endpoint), 'endpoint_sha256': hashlib.sha256(endpoint.read_bytes()).hexdigest(),
        'prompt_sha256': hashlib.sha256(prompt).hexdigest(), 'marker': marker_value,
        'scenario': scenario, 'argv': cli_args, 'thin_returncode': child.returncode}), encoding='utf8')
    if scenario == 'recovered_error' and turn == 2:
        emit({'type': 'error', 'message': 'SYNTHETIC reconnect retained, group/id/perf_ns payload'})
    if scenario == 'malformed' and turn == 2:
        print('SYNTHETIC non-JSON stdout', flush=True)
        return 0
    if not (scenario == 'missing_final' and turn == 2):
        text = 'SYNTHETIC final for turn ' + str(turn)
        final.write_bytes(text.encode('utf8'))
        emit({'type': 'item.completed', 'item': {'id': 'final-' + str(turn), 'type': 'agent_message', 'text': text}})
    emit({'type': 'turn.completed', 'usage': {'input_tokens': 100 + turn, 'cached_input_tokens': 10,
        'cache_write_input_tokens': 0, 'output_tokens': 20 + turn, 'reasoning_output_tokens': 0}})
    return 3 if scenario == 'nonzero_exit' and turn == 2 else 0


if __name__ == '__main__':
    raise SystemExit(main())
