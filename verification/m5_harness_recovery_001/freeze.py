"""Freeze only this recovery chain, its migration and direct dependencies."""

import argparse
import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve()
    blob = path.read_bytes()
    return {'path': str(path), 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}


def save(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readiness', nargs='+', type=Path, required=True)
    args = parser.parse_args()
    files = {}
    for document in args.readiness:
        ready = read(document)
        rows = ready.get('source_pins', ready.get('input_pins', []))
        if not rows:
            raise ValueError('nonempty_readiness_pins/' + str(document))
        rows = rows + ready.get('accepted_readonly_reference_pins', [])
        for row in rows:
            current = pin(row['path'])
            if current['sha256'] != row['sha256'] or ('bytes' in row and current['bytes'] != row['bytes']):
                raise ValueError('prepared_source_changed/' + row['path'])
            files[current['path']] = current
        files[str(document.resolve())] = pin(document)
    for name in ('BASELINE.json', 'A_RUN_BINDING.json', 'B_RUN_BINDING.json', 'EXPECTATIONS.json', 'freeze.py'):
        row = pin(HERE / name)
        files[row['path']] = row
    baseline = read(HERE / 'BASELINE.json')
    for row in baseline['protected_direct_seals'] + [baseline['candidate'], baseline['asset']]:
        current = pin(row['path'])
        if current['sha256'] != row['sha256']:
            raise ValueError('direct_prior_input_changed/' + row['path'])
        files[current['path']] = current
    plan = {'schema': 'm5-harness-recovery-plan-v1', 'registered_ns': time.perf_counter_ns(),
            'baseline_git': baseline['baseline_git'], 'limits': baseline['limits'],
            'session_order': [{'logical_id': 'A_recovery', 'group': 'A', 'directory': 'sessions/A'},
                              {'logical_id': 'B_recovery', 'group': 'B', 'directory': 'sessions/B'}],
            'internal_request_sequence': baseline['internal_request_sequence'],
            'expected_archive_indices': baseline['expected_archive_indices'],
            'actual_attempts_retained': True, 'product_or_model_benefit_comparison': False,
            'acceptance_scope': 'Recovery transport, current source and image delivery, budget and owned closure only.',
            'expectations_sha256': pin(HERE / 'EXPECTATIONS.json')['sha256']}
    save('PLAN.json', plan)
    row = pin(HERE / 'PLAN.json')
    files[row['path']] = row
    frozen = {'schema': 'm5-harness-recovery-frozen-v1', 'frozen_ns': time.perf_counter_ns(),
              'files': [files[name] for name in sorted(files)],
              'scope': 'Direct sources and context used by two zero-model recovery sessions. Historical matrices remain referenced.'}
    save('FROZEN.json', frozen)
    print(json.dumps({'frozen_files': len(files), 'consumer_models': 0}))


if __name__ == '__main__':
    main()
