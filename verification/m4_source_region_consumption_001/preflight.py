"""Check the frozen CLI identity and direct MCP protocol with no model call."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m4_source_region_consume_001')
BASE = 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
CLI = 'C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began = time.perf_counter_ns()
    folder = RUNTIME / 'preflight'
    folder.mkdir(exist_ok=False)
    logs = []
    for suffix in (['--version'], ['login', 'status']):
        started = time.perf_counter_ns()
        result = subprocess.run([CLI, *suffix], capture_output=True, timeout=30)
        logs.append({'argv': [CLI, *suffix], 'started_ns': started, 'closed_ns': time.perf_counter_ns(),
                     'returncode': result.returncode, 'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                     'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
                     'logged_in_using_ChatGPT': b'ChatGPT' in result.stdout + result.stderr})
        if result.returncode != 0:
            raise RuntimeError('existing_Pro_CLI_login_or_version_unavailable')
    assert sha(CLI) == '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
    adapter = load('_sealed_consume_adapter_preflight', HERE / 'harness/consumer_adapter.py')
    consume, proof = adapter.consumer_adapter()
    assert proof['event_loop_code_reused'] and proof['unified_archive_reused'] and proof['safe_environment_reused']
    case = read(HERE / 'INPUTS.json')['cases'][0]
    deadline = time.perf_counter_ns() + 30_000_000_000
    transport = load('_sealed_stdio_preflight', HERE / 'harness/reused/stdio_checks.py')
    client = transport.StdioClient([BASE, '-I', '-B', '-X', 'utf8', str(HERE / 'harness/read_observation.py'),
        '--input', case['input_file'], '--input-sha256', case['input_sha256'], '--owner', str(folder / 'owner'),
        '--audit', str(folder / 'attachments'), '--deadline-ns', str(deadline)], folder, folder / 'stdio', deadline)
    checks = []
    try:
        initialized = client.call({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'pure-protocol-preflight', 'version': '1.0'}}})
        assert initialized['result']['protocolVersion'] == '2025-03-26'
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        listed = client.call({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        assert listed['result']['tools'] == [read(HERE / 'inputs/TOOL_SCHEMA.json')]
        for index in range(1, 6):
            response = client.call({'jsonrpc': '2.0', 'id': index + 2, 'method': 'tools/call',
                                   'params': {'name': 'read_observation', 'arguments': {}}})
            if index <= 4:
                assert response['result'] == read(case['input_file'])
                assert response['result']['content'][0]['text'].encode('utf8') == (HERE / 'inputs/S1/ORIGINAL_BRIEF.json').read_bytes()
            else:
                assert response['result']['isError'] is True
                assert response['result']['content'][0]['text'] == 'business_tool_budget_exhausted'
            checks.append({'attempt': index, 'original_returned': index <= 4})
    finally:
        closed = client.finish()
    assert closed['confirmed']
    ledger = read(folder / 'owner/TOOLS.json')
    assert ledger['attempts'] == 5 and ledger['admitted'] == 4
    loaded = []
    root = HERE.parents[1].resolve()
    for module in list(sys.modules.values()):
        source = getattr(module, '__file__', None)
        if source and Path(source).suffix == '.py' and Path(source).resolve().is_relative_to(root):
            path = Path(source).resolve()
            loaded.append({'path': str(path), 'sha256': sha(path)})
    record = {'status': 'passed', 'started_ns': began, 'closed_ns': time.perf_counter_ns(),
        'CLI_preflight': logs, 'CLI_sha256': sha(CLI), 'adapter_proof': proof,
        'direct_protocol_checks': checks, 'stdio_closure': closed,
        'loaded_execution_sources': sorted({row['path']: row for row in loaded}.values(), key=lambda row: row['path']),
        'formal_consumers_started': 0, 'protocol_test_processes': 1, 'protocol_image_deliveries_to_Python': 4,
        'PNG_or_NPZ_encoding': 0, 'new_Blender': 0, 'new_product_public_calls': 0, 'paid_API': 0}
    (HERE / 'PREFLIGHT.json').write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': 'passed', 'protocol_checks': len(checks), 'model_calls': 0}))


if __name__ == '__main__':
    main()
