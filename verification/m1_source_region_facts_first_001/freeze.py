"""Freeze the selected product, every declared execution source and inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began = time.perf_counter_ns()
    inputs = json.loads((HERE / 'INPUTS.json').read_bytes())
    assert inputs['selected_candidate'] == 'B'
    for name in ('CLIENT_BUDGET_REVIEW.json', 'BRIDGE_PREFLIGHT.json', 'PRELAUNCH_REVIEW.json'):
        assert (HERE / 'checks' / name).is_file()
    source = HERE / 'harness/consumer_adapter.py'
    spec = importlib.util.spec_from_file_location('_final_frozen_consumer_adapter', source)
    adapter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = adapter
    spec.loader.exec_module(adapter)
    _, proof = adapter.consumer_adapter()
    version = subprocess.run([str(adapter.CLI), '--version'], capture_output=True, timeout=30)
    login = subprocess.run([str(adapter.CLI), 'login', 'status'], capture_output=True, timeout=30)
    assert version.returncode == login.returncode == 0
    cli_record = {'CLI_path': str(adapter.CLI), 'CLI_sha256': sha(adapter.CLI),
        'version_exit': version.returncode, 'version_stdout_sha256': hashlib.sha256(version.stdout).hexdigest(),
        'login_exit': login.returncode, 'login_output_sha256': hashlib.sha256(login.stdout + login.stderr).hexdigest(),
        'ChatGPT_login_reported': b'ChatGPT' in login.stdout + login.stderr, 'model_calls': 0}
    (HERE / 'CLI_PREFLIGHT.json').write_text(json.dumps(cli_record, sort_keys=True, indent=2) + '\n', encoding='utf8')
    paths = {HERE / name for name in ('BASELINE.json', 'INPUTS.json', 'BENCHMARK_CONTRACT.json',
        'BENCHMARK_RESULT.json', 'BENCHMARK_PUBLICATION.json', 'CLI_PREFLIGHT.json', 'A_RUN_BINDING.json', 'B_RUN_BINDING.json')}
    for folder in ('inputs', 'historical', 'scoring', 'harness'):
        paths.update(path.resolve() for path in (HERE / folder).rglob('*') if path.is_file() and path.suffix != '.pyc')
    paths.update(Path(row['path']).resolve() for row in proof['execution_sources'])
    paths.update({adapter.CLI.resolve(), adapter.BASE.resolve()})
    for name in ('CLIENT_BUDGET_REVIEW.json', 'BRIDGE_PREFLIGHT.json', 'PRELAUNCH_REVIEW.json'):
        paths.add(HERE / 'checks' / name)
    for label in ('A', 'B'):
        binding = json.loads((HERE / (label + '_RUN_BINDING.json')).read_bytes())
        for row in binding['source_manifest']:
            path = Path(binding['install_root']) / row['path']
            assert sha(path) == row['sha256']
            paths.add(path.resolve())
        for path in Path(binding['install_root']).glob('*.dist-info/*'):
            if path.is_file():
                paths.add(path.resolve())
    old = HERE.with_name('m4_source_region_consumption_001')
    for name in ('PROMPT.txt', 'TOOL_SCHEMA.json'):
        assert (HERE / 'inputs' / name).read_bytes() == (old / 'inputs' / name).read_bytes()
    for name in ('RUBRIC.json', 'CASE_ANSWERS.json', 'SCORE_METHOD.md'):
        assert (HERE / 'scoring' / name).read_bytes() == (old / 'scoring' / name).read_bytes()
    rows = [{'path': str(path.resolve()), 'bytes': path.stat().st_size, 'sha256': sha(path)} for path in sorted(paths)]
    value = {'schema': 'facts-first-consumption-freeze-v1', 'frozen_ns': time.perf_counter_ns(),
        'direct_inputs': rows, 'execution_source_count': len(proof['execution_sources']),
        'execution_sources': proof['execution_sources'], 'selected_candidate': 'B',
        'selected_source_sha256': json.loads((HERE / 'B_RUN_BINDING.json').read_bytes())['source_sha256'],
        'case_order': ['S1', 'S2', 'S3'], 'consumer_cap': 3, 'replacement_consumers': 0,
        'task_seconds': 450, 'process_seconds': 600, 'completed_CLI_tool_cap': 4,
        'model_profile': {'model': 'gpt-6.1-sol', 'reasoning_effort': 'medium', 'service_tier': 'default'},
        'freeze_started_ns': began, 'private_scoring_not_in_consumer_input': True}
    with (HERE / 'FROZEN.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write('\n')
    start = json.loads((HERE / 'PREPARATION_STARTED.json').read_bytes())
    (HERE / 'PREPARATION_CLOSED.json').write_text(json.dumps({'started_ns': start['started_ns'],
        'closed_ns': time.perf_counter_ns(), 'scope': start['scope'], 'freeze_sha256': sha(HERE / 'FROZEN.json')},
        sort_keys=True, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'frozen_files': len(rows), 'execution_sources': len(proof['execution_sources']), 'model_consumers': 0}))


if __name__ == '__main__':
    main()
