"""Launch exactly one registered fresh consumer and seal its original answer."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
NS = HERE.parent
RUNTIME = Path('D:/he_m4_source_region_consume_001')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main(case_id):
    began = time.perf_counter_ns()
    task_deadline = began + 450_000_000_000
    lifecycle_deadline = began + 600_000_000_000
    folder = RUNTIME / 'slots' / case_id
    folder.mkdir(parents=True, exist_ok=False)
    for previous in ('S1', 'S2', 'S3')[:int(case_id[1]) - 1]:
        if not (RUNTIME / 'slots' / previous / 'SLOT_PUBLICATION.json').is_file():
            raise ValueError('registered_serial_order_required')
    result = {'case_id': case_id, 'status': 'running', 'errors': [], 'started_ns': began,
              'task_deadline_ns': task_deadline, 'lifecycle_deadline_ns': lifecycle_deadline}
    save(folder / 'SLOT_STARTED.json', result)
    try:
        frozen = read(NS / 'FROZEN.json')
        for row in frozen['direct_inputs']:
            if sha(row['path']) != row['sha256']:
                raise ValueError('frozen_direct_input_changed/' + row['path'])
        case = next(row for row in read(NS / 'INPUTS.json')['cases'] if row['case_id'] == case_id)
        spec = importlib.util.spec_from_file_location('_formal_consumer_adapter', HERE / 'consumer_adapter.py')
        adapter = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = adapter
        spec.loader.exec_module(adapter)
        value = adapter.consume(folder, case, task_deadline, lifecycle_deadline, (NS / 'inputs/PROMPT.txt').read_bytes())
        record = value['record']
        save(folder / 'ADAPTER_PROOF.json', value['proof'])
        ledger = read(folder / 'owner/TOOLS.json') if (folder / 'owner/TOOLS.json').exists() else {'attempts': 0, 'admitted': 0}
        result.update(consumer_status=record['status'], valid_completion=record['valid_completion'],
            business_attempts=ledger['attempts'], business_admitted=ledger['admitted'],
            completed_tool_calls=len(record['tool_calls']), native_image_deliveries=record['public_image_count'],
            process_reaped=record['process_reaped'], readers_stopped=record['readers_stopped'],
            runtime_exit=record['runtime_exit'], CLI_thread_id=record['thread_id'],
            original_usage=record['raw_usage_events'], consumer_record_sha256=sha(folder / 'consumer/CONSUMER.json'))
        final = folder / 'consumer/PUBLIC_FINAL.txt'
        if final.exists():
            result['answer'] = {'path': str(final), 'sha256': sha(final), 'bytes': final.stat().st_size}
        if ledger['attempts'] > 4 or ledger['admitted'] > 4 or len(record['tool_calls']) > 4:
            raise ValueError('original_four_business_call_budget_exceeded')
        if not record['valid_completion']:
            raise RuntimeError('consumer_execution_or_delivery_not_completed')
        result['status'] = 'completed'
    except BaseException as error:
        result['status'] = 'failed'
        result['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        result['closed_ns'] = time.perf_counter_ns()
        result['wall_ns'] = result['closed_ns'] - began
        if result['closed_ns'] >= lifecycle_deadline:
            result['status'] = 'failed'
            result['errors'].append({'type': 'TimeoutError', 'message': 'original_600_second_process_lifecycle'})
        save(folder / 'SLOT_RESULT.json', result)
        save(folder / 'SLOT_PUBLICATION.json', {'case_id': case_id, 'status': result['status'],
             'started_ns': began, 'published_ns': time.perf_counter_ns(),
             'original_task_deadline_ns': task_deadline, 'original_lifecycle_deadline_ns': lifecycle_deadline,
             'result_sha256': sha(folder / 'SLOT_RESULT.json')})
    print(json.dumps({key: result.get(key) for key in ('case_id', 'status', 'business_attempts', 'native_image_deliveries', 'wall_ns')}))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=('S1', 'S2', 'S3'), required=True)
    options = parser.parse_args()
    raise SystemExit(main(options.case))
