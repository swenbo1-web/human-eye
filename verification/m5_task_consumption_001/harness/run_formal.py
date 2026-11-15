"""Run the one frozen six-consumer sequence with retained failures and suffix."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import traceback


HERE = Path(__file__).resolve().parent
NAMESPACE = HERE.parent
EXTERNAL = Path('D:/he_m5_task_consume_001')
SEQUENCE = [('A1', 'A'), ('B1', 'B'), ('B2', 'B'), ('A2', 'A'), ('A3', 'A'), ('B3', 'B')]


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def continuation_blocker(result):
    cleanup = result['cleanup']
    expected = ('native', 'mcp')
    if cleanup.get('actor_exit_code') != 0 or cleanup.get('actor_process_handle_closed') is not True:
        return 'actor_exit_or_handle_unknown'
    for kind in expected:
        row = cleanup.get(kind, {})
        if (row.get('confirmed') is not True or row.get('exit_code') != 0
                or row.get('handle_closed') is not True or row.get('forced_by_root')):
            return 'owned_child_exit_unknown_or_forced_' + kind
    actor = cleanup.get('actor_close') or {}
    runtime = actor.get('runtime') or {}
    native_status = runtime.get('Blender_status') or {}
    closed = native_status.get('closed') or {}
    if (runtime.get('errors') or runtime.get('runtime', {}).get('errors')
            or native_status.get('source_file_unchanged') is not True
            or native_status.get('protected_files_unchanged') is not True or closed.get('poisoned')
            or closed.get('initial_geometry_fingerprint') != closed.get('final_geometry_fingerprint')):
        return 'shared_source_or_runtime_failure'
    if not result.get('consumer_record'):
        return 'consumer_not_started_or_no_original_record'
    consumer = read(result['consumer_record'])
    if consumer.get('safe_to_continue') is not True:
        return 'consumer_or_thin_runtime_state_unconfirmed'
    if consumer.get('archive', {}).get('business_binding_errors'):
        return 'actual_tool_contract_mismatch'
    timeout = any('timeout' in str(row).lower() or 'deadline' in str(row).lower()
                  for row in consumer.get('errors', []))
    if consumer.get('final') is None and not timeout:
        return 'consumer_service_or_protocol_failure_without_final'
    return None


def main():
    plan = read(NAMESPACE / 'PLAN.json')
    frozen = read(NAMESPACE / 'FROZEN.json')
    if [(row['slot_id'], row['group']) for row in plan['sequence']] != SEQUENCE:
        raise ValueError('fixed_six_slot_order')
    if (plan['formal_batch_attempts'] != 1 or plan['outer_retries'] != 0
            or plan['replacement_samples'] != 0):
        raise ValueError('fixed_single_formal_execution')
    for row in frozen['files']:
        if sha(row['path']) != row['sha256']:
            raise ValueError('frozen_source_changed_' + row['path'])
    if read(NAMESPACE / 'admin/QUALIFICATION.json')['passed_checked_scope'] is not True:
        raise ValueError('actual_qualification_required')
    specification = importlib.util.spec_from_file_location('_root_six_target_slots', HERE / 'run_slot.py')
    controller = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(controller)
    EXTERNAL.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter_ns()
    marker = dict(schema='target-task-consumption-formal-once-v1', started_ns=started,
                  order=plan['sequence'], plan_sha256=sha(NAMESPACE / 'PLAN.json'),
                  freeze_sha256=sha(NAMESPACE / 'FROZEN.json'), formal_attempts=1,
                  outer_retries=0, replacement_samples=0)
    save(EXTERNAL / 'FORMAL_STARTED.json', marker)
    records = [dict(slot_id=slot, group=group, status='not_run', reason='pending_frozen_order',
                    result_path=None, publication_path=None) for slot, group in SEQUENCE]
    blocker = None
    for index, (slot, group) in enumerate(SEQUENCE):
        folder = EXTERNAL / 'formal' / slot
        dispatched = time.perf_counter_ns()
        try:
            result = controller.run_slot(slot, group, 'formal')
            records[index] = dict(slot_id=slot, group=group, status=result['status'],
                result_path=str(folder / 'SLOT_RESULT.json'), publication_path=str(folder / 'SLOT_PUBLICATION.json'),
                consumer_path=result.get('consumer_path'), consumer_record=result.get('consumer_record'),
                dispatched_ns=dispatched, closed_ns=time.perf_counter_ns(),
                result_sha256=sha(folder / 'SLOT_RESULT.json'), publication_sha256=sha(folder / 'SLOT_PUBLICATION.json'))
            blocker = continuation_blocker(result)
        except BaseException as error:
            records[index] = dict(slot_id=slot, group=group, status='failed',
                result_path=str(folder / 'SLOT_RESULT.json') if (folder / 'SLOT_RESULT.json').exists() else None,
                publication_path=str(folder / 'SLOT_PUBLICATION.json') if (folder / 'SLOT_PUBLICATION.json').exists() else None,
                dispatched_ns=dispatched, closed_ns=time.perf_counter_ns(),
                error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()))
            blocker = 'root_dispatch_or_record_failure'
        with (EXTERNAL / 'FORMAL_PROGRESS.jsonl').open('ab') as stream:
            stream.write((json.dumps(records[index], ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8'))
            stream.flush()
        print(json.dumps(dict(slot_id=slot, status=records[index]['status'], blocker=blocker)), flush=True)
        if blocker:
            for row in records[index + 1:]:
                row['reason'] = blocker
            break
    consumer_attempts = sum((EXTERNAL / 'formal' / slot / 'CONSUMER_START.json').exists() for slot, _ in SEQUENCE)
    actual_consumers = 0
    for slot, _ in SEQUENCE:
        path = EXTERNAL / 'formal' / slot / 'consumer/CONSUMER.json'
        if path.exists() and read(path).get('image_delivery', {}).get('CLI_process_launched') is True:
            actual_consumers += 1
    final = dict(schema='target-task-consumption-run-v1', started_ns=started, closed_ns=time.perf_counter_ns(),
                 planned_slots=6, consumer_attempts=consumer_attempts, actual_consumers=actual_consumers,
                 outer_retries=0, replacement_samples=0,
                 formal_batch_attempts=1, plan_sha256=sha(NAMESPACE / 'PLAN.json'),
                 frozen_sha256=sha(NAMESPACE / 'FROZEN.json'), records=records, blocker=blocker,
                 quality='pending_saved_answer_source_and_image_review',
                 cost='unranked_until_quality_sealed')
    save(EXTERNAL / 'RUN_RESULT.json', final)
    print(json.dumps(dict(actual_consumers=actual_consumers, slots=len(records), blocker=blocker)), flush=True)


if __name__ == '__main__':
    main()
