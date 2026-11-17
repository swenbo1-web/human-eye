"""Qualify a metadata-only MCP repair and preserve the original failed case."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

NS = Path(__file__).resolve().parent.parent
RUNTIME = Path('D:/he_m4_source_region_consume_001')
BASE = 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began = time.perf_counter_ns()
    old = read(NS / 'FROZEN.json')
    allowed = {str((NS / 'harness' / name).resolve()) for name in ('read_observation.py', 'run_slot.py')}
    changed = [row['path'] for row in old['direct_inputs'] if sha(row['path']) != row['sha256']]
    assert set(changed) == allowed
    for name in ('read_observation.py', 'run_slot.py'):
        previous = next(row for row in old['direct_inputs'] if Path(row['path']).name == name)
        assert sha(NS / 'protocol_revisions' / ('R0_' + name + '.txt')) == previous['sha256']
    case = read(NS / 'INPUTS.json')['cases'][0]
    folder = RUNTIME / 'preflight_r1'
    folder.mkdir(exist_ok=False)
    deadline = time.perf_counter_ns() + 30_000_000_000
    source = NS / 'harness/reused/stdio_checks.py'
    spec = importlib.util.spec_from_file_location('_metadata_stdio_preflight', source)
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    client = transport.StdioClient([BASE, '-I', '-B', '-X', 'utf8', str(NS / 'harness/read_observation.py'),
        '--input', case['input_file'], '--input-sha256', case['input_sha256'],
        '--owner', str(folder / 'owner'), '--audit', str(folder / 'attachments'),
        '--deadline-ns', str(deadline)], folder, folder / 'stdio', deadline)
    try:
        client.call({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}})
        tools = client.call({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
        assert tools['result']['tools'] == [read(NS / 'inputs/TOOL_SCHEMA.json')]
        for index, method in enumerate(('resources/list', 'resources/templates/list'), 3):
            response = client.call({'jsonrpc': '2.0', 'id': index, 'method': method})
            assert list(response['result'].values()) == [[]]
        for attempt in range(1, 6):
            params = {'name': 'read_observation', 'arguments': {}}
            if attempt != 2:
                params['_meta'] = {'callId': 'pure-metadata', 'progressToken': attempt,
                    'x-codex-turn-metadata': {'model': 'gpt-6.1-sol', 'reasoning_effort': 'medium'}}
            response = client.call({'jsonrpc': '2.0', 'id': attempt + 4, 'method': 'tools/call', 'params': params})
            if attempt <= 4:
                assert response['result'] == read(case['input_file'])
            else:
                assert response['result']['isError']
    finally:
        closed = client.finish()
    assert closed['confirmed']
    ledger = read(folder / 'owner/TOOLS.json')
    assert ledger['attempts'] == 5 and ledger['admitted'] == 4
    assert read(folder / 'owner/BRIDGE_RESULT.json')['admitted'] == 4
    revision = {'schema': 'source-region-consumption-protocol-revision-v1',
        'status': 'qualified', 'started_ns': began, 'closed_ns': time.perf_counter_ns(),
        'reason': 'Original server rejected standard tools/call params._meta. Actual S1 made two calls and received no observation.',
        'S1_slot_result_sha256': sha(RUNTIME / 'slots/S1/SLOT_RESULT.json'),
        'S1_replacement_consumers': 0, 'completed_case_preserved': 'S1',
        'next_cases': ['S2', 'S3'], 'changed_frozen_source_paths': changed,
        'semantics_and_scoring_inputs_byte_identical': True,
        'protocol_changes': ['Accept and preserve optional transport _meta alongside the same name and empty arguments.',
            'Answer optional resource enumeration with empty lists.',
            'Persist read-only delivery ledger before returning content, including abrupt CLI shutdown cases.',
            'Select a separately recorded revised execution freeze.'],
        'preflight_model_calls': 0, 'preflight_tool_admissions_to_Python': 4,
        'new_Blender': 0, 'new_product_public_calls': 0, 'raster': 0, 'image_encoding': 0,
        'preflight_closure': closed}
    path = NS / 'protocol_revisions/REVISION_01.json'
    path.write_text(json.dumps(revision, sort_keys=True, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    revised = dict(old)
    revised['frozen_ns'] = time.perf_counter_ns()
    revised['original_freeze_sha256'] = sha(NS / 'FROZEN.json')
    revised['protocol_revision_sha256'] = sha(path)
    revised['direct_inputs'] = [dict(row, sha256=sha(row['path']), bytes=Path(row['path']).stat().st_size)
                                for row in old['direct_inputs']]
    with (NS / 'FROZEN_PROTOCOL_R1.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(revised, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write('\n')
    with (NS / 'ACTIVE_FREEZE.json').open('x', encoding='utf8') as stream:
        json.dump({'name': 'FROZEN_PROTOCOL_R1.json', 'sha256': sha(NS / 'FROZEN_PROTOCOL_R1.json')}, stream)
    print(json.dumps({'status': 'qualified', 'S1_preserved': True, 'new_model_calls': 0}))


if __name__ == '__main__':
    main()
