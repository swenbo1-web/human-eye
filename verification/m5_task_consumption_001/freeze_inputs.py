"""Pin the fixed consumer inputs before qualification and formal dispatch."""

import argparse
import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
EXECUTION = ('bootstrap.py', 'bridge.py', 'launcher.py', 'native_tools.py',
             'native_consumer_audit.py')


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
    parser.add_argument('phase', choices=('qualification', 'formal'))
    phase = parser.parse_args().phase
    if phase == 'qualification':
        preparation = read(HERE / 'PREP_PLAN.json')
        baseline = read(HERE / 'BASELINE.json')
        plan = dict(preparation)
        plan.update(schema='m5-task-consumption-plan-v1', registered_ns=time.perf_counter_ns(),
                    sequence=[{'slot_id': name, 'group': name[0]} for name in baseline['formal_order']],
                    formal_batch_attempts=1, model_consumer_enabled=True,
                    requested_model='gpt-6.1-sol', requested_reasoning_effort='medium',
                    requested_service_tier='default',
                    common_task_sha256=pin(HERE / 'inputs/COMMON_TASK.txt')['sha256'],
                    answer_schema_sha256=pin(HERE / 'inputs/ANSWER_SCHEMA.json')['sha256'])
        files = {HERE / name for name in EXECUTION}
        files.update(path for path in (HERE / 'harness').rglob('*.py') if '__pycache__' not in path.parts)
        files.update(path for path in (HERE / 'inputs').rglob('*') if path.is_file())
        files.update(path for path in (HERE / 'public_schema').rglob('*') if path.is_file())
        files.update(HERE / name for name in ('BASELINE.json', 'PREP_PLAN.json', 'freeze_inputs.py',
                     'A_RUN_BINDING.json', 'B_RUN_BINDING.json', 'SHARED_DEPENDENCY.json',
                     'CLI_PREFLIGHT.json', 'fixtures/DEVICE_CAMERAS.json', 'fixtures/DEVICE_PREPARATION.json',
                     'fixtures/DEVICE_REUSE.json',
                     'admin/SCORING_CONTRACT.json', 'admin/TRUTH.json'))
        files.update(Path(name) for name in read(HERE / 'SHARED_DEPENDENCY.json')['files_sha256'])
        previous_freeze = HERE.parent / 'm4_target_task_consumption_001/FROZEN.json'
        for row in read(previous_freeze)['files']:
            actual = pin(row['path'])
            if actual['sha256'] != row['sha256']:
                raise ValueError('accepted_reused_dependency_changed/' + row['path'])
            files.add(Path(row['path']))
        files.add(previous_freeze)
        for group in ('A', 'B'):
            binding = read(HERE / (group + '_RUN_BINDING.json'))
            installation = Path(binding['install_root'])
            for row in binding['source_manifest']:
                path = installation / row['path']
                if pin(path)['sha256'] != row['sha256']:
                    raise ValueError('product_source_identity/' + group + '/' + row['path'])
                files.add(path)
        files.add(Path(read(HERE / 'CLI_PREFLIGHT.json')['binary']['path']))
        save('PLAN.json', plan)
        files.add(HERE / 'PLAN.json')
        result = {'schema': 'm5-task-consumption-qualification-freeze-v1',
                  'frozen_ns': time.perf_counter_ns(), 'files': [pin(path) for path in sorted(files)],
                  'scope': 'Both fixed installations, execution sources, common inputs, numerical/quality contract, dependencies and CLI. Private answers stay outside consumer context.'}
        save('QUALIFICATION_FREEZE.json', result)
    else:
        previous = read(HERE / 'QUALIFICATION_FREEZE.json')
        for row in previous['files']:
            if pin(row['path']) != row:
                raise ValueError('qualification_frozen_input_changed/' + row['path'])
        if read(HERE / 'admin/QUALIFICATION.json')['passed_checked_scope'] is not True:
            raise ValueError('actual_qualification_must_pass')
        extra = ('QUALIFICATION_FREEZE.json', 'admin/QUALIFICATION.json', 'QUALIFICATION_RUNTIME_REVIEW.json')
        result = {'schema': 'm5-task-consumption-formal-freeze-v1',
                  'frozen_ns': time.perf_counter_ns(),
                  'files': previous['files'] + [pin(HERE / name) for name in extra],
                  'formal_batch_attempts': 1, 'outer_retries': 0, 'replacement_samples': 0}
        save('FROZEN.json', result)
    print(json.dumps({'phase': phase, 'pinned_files': len(result['files'])}))


if __name__ == '__main__':
    main()
