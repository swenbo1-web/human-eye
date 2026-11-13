"""Local protocol fixture; never contacts a provider or infers image content."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import uuid


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    args = sys.argv[1:]
    config = None
    for index, value in enumerate(args[:-1]):
        if value == '-c' and args[index + 1].startswith('mcp_servers.arm_engine='):
            config = tomllib.loads('value=' + args[index + 1].split('=', 1)[1])['value']
    if config is None:
        raise ValueError('actual_MCP_config_missing')
    sys.stdin.buffer.read()
    spec = importlib.util.spec_from_file_location('_fixture_handle', Path(__file__).resolve().parents[1] / 'm4_active_coverage_003/launch.py')
    launch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launch)
    process = subprocess.Popen([config['command'], *config['args']], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sequence = 0

    def rpc(method, params):
        nonlocal sequence
        sequence += 1
        process.stdin.write((json.dumps({'jsonrpc': '2.0', 'id': sequence, 'method': method, 'params': params}) + '\n').encode())
        process.stdin.flush()
        value = json.loads(process.stdout.readline())
        if value.get('id') != sequence or 'error' in value:
            raise ValueError('actual_stdio_rpc_receipt')
        return value['result']

    try:
        rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'local-fixture', 'version': '1'}})
        tools = rpc('tools/list', {})['tools']
        names = {tool['name'] for tool in tools}
        emit({'type': 'thread.started', 'thread_id': str(uuid.uuid4())})
        calls = [('execute_python', {'code': 'protocol_value = 6 * 7\nprint(protocol_value)'})]
        for index, (name, arguments) in enumerate(calls):
            item = {'id': 'tool-' + str(index), 'type': 'mcp_tool_call', 'server': 'arm_engine',
                    'tool': name, 'arguments': arguments, 'status': 'in_progress'}
            emit({'type': 'item.started', 'item': item})
            response = rpc('tools/call', {'name': name, 'arguments': arguments})
            item = dict(item, status='completed', error=None,
                        result={'content': response['content'], 'structured_content': None})
            emit({'type': 'item.completed', 'item': item})
        final = 'LOCAL_RUNTIME_HANDLE_FIXTURE_WITHOUT_MODEL'
        Path(args[args.index('-o') + 1]).write_text(final, encoding='utf8')
        emit({'type': 'item.completed', 'item': {'id': 'final', 'type': 'agent_message', 'text': final}})
        emit({'type': 'turn.completed', 'usage': {'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0}})
        binding = Path(args[args.index('-o') + 1]).parent / 'RUNTIME_BINDING.json'
        import time
        expires = time.perf_counter() + 15
        while not binding.exists():
            if time.perf_counter() >= expires:
                raise TimeoutError('local_controller_runtime_binding_handshake')
            time.sleep(.01)
        if 'active_coverage' in names:
            # Terminate only this fixture's retained thin Popen handle. The
            # original thin client cannot publish EXIT after forced exit.
            process.kill()
            process.wait(timeout=5)
        else:
            process.stdin.close()
            process.wait(timeout=5)
    finally:
        cleanup = launch.stop_process(process, timeout=5)
        if cleanup['confirmed'] is not True:
            raise RuntimeError('fixture_thin_handle_cleanup')


if __name__ == '__main__':
    main()
