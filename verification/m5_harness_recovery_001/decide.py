"""Root check of the two delivered recovery chains and their saved audits."""

import hashlib
import json
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent
RUNTIME = Path('D:/he_m5_harness_recovery_001')
PINS = {}


def raw(path):
    path = Path(path).resolve()
    blob = path.read_bytes()
    PINS[str(path)] = {'path': str(path), 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}
    return blob


def read(path):
    return json.loads(raw(path))


def verify(row):
    blob = raw(row['path'])
    if hashlib.sha256(blob).hexdigest() != row['sha256'] or ('bytes' in row and len(blob) != row['bytes']):
        raise ValueError('saved_input_changed/' + row['path'])


def same_json(a, b):
    return json.dumps(a, sort_keys=True, ensure_ascii=False, separators=(',', ':')) == json.dumps(b, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def main():
    started = time.perf_counter_ns()
    qualification = read(HERE / 'QUALIFICATION.json')
    runtime = read(HERE / 'RUNTIME_REVIEW.json')
    for path, digest in qualification['inputs_sha256'].items():
        verify({'path': path, 'sha256': digest})
    for row in runtime['input_pins']:
        verify(row)
    checks = []
    observations = []
    expected = read(HERE / 'EXPECTATIONS.json')
    for group in ('A', 'B'):
        folder = RUNTIME / 'sessions' / group
        result = read(folder / 'SLOT_RESULT.json')
        publication = read(folder / 'SLOT_PUBLICATION.json')
        requests = [json.loads(line) for line in raw(folder / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
        markers = []
        for attempt in range(1, 5):
            response = read(folder / 'owner' / ('tool_' + str(attempt).zfill(2)) / 'RESPONSE.json')
            checks.append(response['result']['isError'] is False)
            text = next(block['text'] for block in response['result']['content'] if block['type'] == 'text')
            wrapped = json.loads(text)
            checks.append(wrapped['error'] is None)
            for line in wrapped['stdout'].splitlines():
                if line.startswith('M5_RECOVERY_PUBLIC:'):
                    markers.append(json.loads(line[len('M5_RECOVERY_PUBLIC:'):]))
        checks.append(len(markers) == len(requests) == 5)
        indices = [request['producer_archive_index'] for request in requests]
        flags = [request['response']['result']['isError'] for request in requests]
        checks.append(indices == expected['expected_service_archive_indices'])
        checks.append(flags == expected['expected_original_MCP_isError'])
        for marker, request in zip(markers, requests):
            reply = request['response']['result']
            public = json.loads(next(block['text'] for block in reply['content'] if block['type'] == 'text'))
            checks.append(marker['isError'] is reply['isError'] and same_json(marker['public_result'], public))
            checks.append(0 <= request['closed_ns']-request['started_ns'] <= 30_000_000_000)
        checks.append(result['status'] == publication['status'] == 'completed' and not result['errors'])
        checks.append(result['clocks']['owned_deadline_ns'] == publication['slot_started_ns'] + 600_000_000_000)
        checks.append(publication['complete_slot_ns'] < 600_000_000_000)
        observations.append({'group': group, 'archive_indices': indices, 'original_isError': flags,
                             'actual_outer_tools': 4, 'actual_public_requests': 5,
                             'complete_slot_ns': publication['complete_slot_ns'],
                             'post_rejection_delivered_statuses': [marker['public_result']['status'] for marker in markers[2:]],
                             'last_frame_reuses': markers[-1]['public_result']['image_delivery']['frame_reuses'],
                             'last_new_rasters': markers[-1]['public_result']['image_delivery']['new_raster_attempts']})
    budget = runtime['budget']
    checks.append(budget['owned_start_attempts'] == 2 and budget['raster_attempts_actual'] <= 12
                  and budget['consumer_admissions'] == budget['paid_API_calls'] == budget['pending'] == 0)
    checks.append(qualification['passed_checked_scope'] is True and qualification['denominator'] == 2)
    checks.append(runtime['passed_checked_scope'] is True and not runtime['failed_checks']
                  and not runtime['failed_or_unrun_sessions'])
    raw(Path(__file__))
    accepted = all(checks)
    decision = {'schema': 'm5-harness-recovery-decision-v1', 'accepted_harness_recovery': accepted,
                'disposition': 'two_zero_model_recovery_sessions_passed' if accepted else 'recovery_acceptance_failed',
                'qualification_sha256': PINS[str((HERE / 'QUALIFICATION.json').resolve())]['sha256'],
                'runtime_review_sha256': PINS[str((HERE / 'RUNTIME_REVIEW.json').resolve())]['sha256'],
                'product_or_model_benefit_claim': False, 'administrator_review': 'pending',
                'checks': len(checks), 'failed_checks': sum(not value for value in checks),
                'sessions': observations, 'budget': budget, 'failed_or_unrun_sessions': runtime['failed_or_unrun_sessions'],
                'started_ns': started, 'closed_ns': time.perf_counter_ns(),
                'scope': 'Recovery of the external test harness under the frozen two-session contract. Prior consumer batch stays sealed.',
                'input_pins': sorted(PINS.values(), key=lambda row: row['path'])}
    with (HERE / 'DECISION.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(decision, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'accepted_harness_recovery': accepted, 'checks': len(checks), 'actual_consumers': 0}))


if __name__ == '__main__':
    main()
