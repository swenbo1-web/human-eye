"""Five fixed paired pure-formatting windows and actual installed exports."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNTIME = Path('D:/he_m1_source_region_facts_first_001')
BASE = 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    began = time.perf_counter_ns()
    contract = read(HERE / 'BENCHMARK_CONTRACT.json')
    spec = importlib.util.spec_from_file_location('_pure_projection_stdio', ROOT / 'verification/m4_source_region_display_001/harness/reused/stdio_checks.py')
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    clients, calls, exports, closures = {}, [], {}, {}
    folder = RUNTIME / 'projection_benchmark'
    folder.mkdir(exist_ok=False)
    try:
        for label, binding in [('A', HERE / 'A_RUN_BINDING.json'), ('B', HERE / 'B_RUN_BINDING.json'),
                               ('OLD', HERE / 'historical/PRODUCT_BINDING.json')]:
            work = folder / label
            work.mkdir()
            clients[label] = transport.StdioClient([BASE, '-I', '-B', '-X', 'utf8', str(HERE / 'projection_worker.py'),
                '--binding', str(binding.resolve())], work, work / 'stdio', began + 300_000_000_000)
        def invoke(label, case, operation, iterations=1, detail=None):
            client = clients[label]
            response = client.call({'jsonrpc': '2.0', 'id': len(client.records) + 1, 'method': operation,
                'params': {'case': case, 'iterations': iterations, 'detail': detail}})
            if 'error' in response:
                raise RuntimeError('pure_formatter_error/' + json.dumps(response['error']))
            result = response['result']
            calls.append({'candidate': label, 'case': case, 'operation': operation,
                          'iterations': iterations, 'detail': detail, 'rpc_index': client.records[-1]['index'],
                          'elapsed_ns': result['elapsed_ns'], 'text_sha256': result['text_sha256'],
                          'counters': result['counters'], 'memory': result['Python_tracemalloc_current_peak_bytes']})
            return result
        pairs = []
        for case in ('S1', 'S2', 'S3'):
            for label in 'AB':
                invoke(label, case, 'warmup', contract['warmup_calls_per_case_per_candidate'])
            for pair, order in enumerate(contract['pair_order'], 1):
                values = {label: invoke(label, case, 'timed', contract['calls_per_window']) for label in order}
                assert values['A']['text'] == values['B']['text']
                assert values['A']['native_images'] == values['B']['native_images']
                pairs.append({'case': case, 'pair': pair, 'order': order,
                    'A_elapsed_ns': values['A']['elapsed_ns'], 'B_elapsed_ns': values['B']['elapsed_ns'],
                    'A_window_elapsed_ns': values['A']['window_elapsed_ns'],
                    'B_window_elapsed_ns': values['B']['window_elapsed_ns'],
                    'iterations': contract['calls_per_window'], 'text_bytes': values['B']['text_UTF8_bytes'],
                    'text_sha256': values['B']['text_sha256'], 'JSON_and_native_images_equal': True})
            exports[case] = {label: invoke(label, case, 'export') for label in 'AB'}
            assert exports[case]['A']['tool_result'] == exports[case]['B']['tool_result']
            full = {label: invoke(label, case, 'export', detail='full') for label in ('OLD', 'A', 'B')}
            assert full['OLD']['tool_result'] == full['A']['tool_result'] == full['B']['tool_result']
            profiles = {label: invoke(label, case, 'profile') for label in 'AB'}
            memory = {label: invoke(label, case, 'memory') for label in 'AB'}
            save(folder / (case + '_PROFILES.json'), {'profiles': profiles, 'memory': memory,
                'full_text_sha256': {label: result['text_sha256'] for label, result in full.items()},
                'full_and_old_entry_equal': True})
        summaries = []
        for case in ('S1', 'S2', 'S3'):
            rows = [row for row in pairs if row['case'] == case]
            a = statistics.median(row['A_elapsed_ns'] for row in rows)
            b = statistics.median(row['B_elapsed_ns'] for row in rows)
            profile = read(folder / (case + '_PROFILES.json'))
            work_less = profile['profiles']['B']['counters']['deepcopy_argument_JSON_UTF8_bytes'] < profile['profiles']['A']['counters']['deepcopy_argument_JSON_UTF8_bytes']
            summaries.append({'case': case, 'A_median_ns': a, 'B_median_ns': b,
                              'B_time_improvement_fraction': 1 - b / a, 'B_copy_argument_work_less': work_less})
        keep = all(row['B_median_ns'] < row['A_median_ns'] and row['B_copy_argument_work_less'] for row in summaries)
        selected = 'B' if keep else 'A'
        projected_inputs = []
        for case in ('S1', 'S2', 'S3'):
            result = exports[case][selected]['tool_result']
            historical = read(HERE / 'historical' / case / 'TOOL_RESULT.json')
            assert result['content'][1:] == historical['content'][1:]
            assert len(result['content'][0]['text'].encode()) <= 10000
            target = HERE / 'inputs' / case
            target.mkdir(exist_ok=False)
            save(target / 'TOOL_RESULT.json', result)
            (target / 'ORIGINAL_BRIEF.json').write_bytes(result['content'][0]['text'].encode('utf8'))
            (target / 'ORIGINAL_IMAGE.png').write_bytes(base64.b64decode(result['content'][1]['data'], validate=True))
            projected_inputs.append({'case_id': case, 'consumer_group': 'F',
                'input_file': str((target / 'TOOL_RESULT.json').resolve()), 'input_sha256': sha(target / 'TOOL_RESULT.json'),
                'brief_UTF8_bytes': len(result['content'][0]['text'].encode()),
                'PNG_sha256': sha(target / 'ORIGINAL_IMAGE.png'),
                'historical_full_sha256': sha(HERE / 'historical' / case / 'SERVICE_RESULT.json'),
                'projection_source_binding': str((HERE / (selected + '_RUN_BINDING.json')).resolve()),
                'projection_source_sha256': read(HERE / (selected + '_RUN_BINDING.json'))['source_sha256']})
        save(HERE / 'INPUTS.json', {'consumer_group': 'F', 'cases': projected_inputs,
            'selected_candidate': selected, 'prompt_sha256': sha(HERE / 'inputs/PROMPT.txt'),
            'tool_schema_sha256': sha(HERE / 'inputs/TOOL_SCHEMA.json'),
            'capture_scope': 'Historical DISPLAY001 captures; current installed formatter projection only.'})
        save(HERE / 'BENCHMARK_RESULT.json', {'status': 'passed', 'selected_candidate': selected,
            'contract_sha256': sha(HERE / 'BENCHMARK_CONTRACT.json'), 'pairs': pairs, 'summary': summaries,
            'calls': calls, 'started_ns': began, 'closed_before_worker_cleanup_ns': time.perf_counter_ns(),
            'timing_scope': 'Sum of installed formatter call intervals; loop equivalence checks, guards and stdio are outside these intervals and inside total wall time.',
            'instrumentation_scope': 'Formatter-local top-level deepcopy arguments and json.dumps only. JSON byte sizes measure copy argument work, not physical allocated bytes. Separate tracemalloc call reports Python peak.',
            'new_PNG_NPZ_encodes': 0, 'raster': 0, 'models': 0})
    finally:
        for label, client in clients.items():
            closures[label] = client.finish()
        save(folder / 'CLOSURES.json', closures)
    assert all(value['confirmed'] for value in closures.values())
    save(HERE / 'BENCHMARK_PUBLICATION.json', {'started_ns': began, 'closed_ns': time.perf_counter_ns(),
         'result_sha256': sha(HERE / 'BENCHMARK_RESULT.json'), 'all_workers_closed': True})
    print(json.dumps({'status': 'passed', 'selected_candidate': selected, 'pairs': len(pairs), 'summary': summaries}))


if __name__ == '__main__':
    main()
