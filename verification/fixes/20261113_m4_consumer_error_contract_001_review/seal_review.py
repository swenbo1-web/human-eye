"""Seal this independent review only; no candidate or online workload runs."""
import hashlib
import json
from pathlib import Path

ROOT = Path('D:/hefe')
HERE = Path(__file__).resolve().parent
CANDIDATE = 'cb5c33a158a9dea06c8151248cc42d2b87c5697b'
DOCS = [
    ROOT / 'docs/M4_CONSUMER_ERROR_CONTRACT_001_INDEPENDENT_REVIEW.md',
    ROOT / 'docs/M4_ACTIVE_COVERAGE_CONSUMPTION_002_PLAN.md',
]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def info(path):
    data = path.read_bytes()
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def save(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


identity = read(HERE / 'IDENTITY.json')
semantics = read(HERE / 'semantics/RESULTS.json')
wiring = read(HERE / 'wiring/RESULTS.json')
replay = read(HERE / 'replay/RESULTS.json')
assert identity['commit'] == CANDIDATE
assert identity['checks'] == identity['passed'] == 4551 and not identity['failed']
assert semantics['author_commit'] == CANDIDATE
assert semantics['check_count'] == 59 and not semantics['failed']
assert semantics['pure_group_count'] == 1 and semantics['pure_candidate_calls'] == 22
assert wiring['candidate_commit'] == CANDIDATE
assert wiring['total'] == wiring['passed'] == 47 and wiring['all_passed']
assert not wiring['online_validated'] and not wiring['blocked_operation_attempts']
assert replay['author_commit'] == CANDIDATE
assert replay['checks_count'] == replay['passed'] == 1558 and not replay['failed']
assert replay['real_tools'] == 15 and replay['case_count'] == 47
assert replay['ZIP_count'] == 45 and replay['ZIP_members'] == 560
assert replay['actual_new_CLI_model_actor_Blender_renderer_calls'] == 0

decision = {
    'schema': 'independent-consumer-error-contract-review-v1',
    'cycle': 'M4-CONSUMER-ERROR-CONTRACT-001',
    'candidate_commit': CANDIDATE,
    'decision': 'accepted_protocol_fix; proceed_to_one_fixed_new_consumption_batch',
    'identity': {k: identity[k] for k in ['checks', 'passed', 'delivery_files',
        'member_bytes', 'frozen_files', 'old_delivery_files', 'old_runtime_files']},
    'independent_checks': {
        'semantics_checks': 59, 'pure_matcher_groups': 1, 'pure_matcher_calls': 22,
        'wiring_checks': 47, 'artifact_checks': 1558,
        'real_historical_transactions': 15, 'success_transactions': 13,
        'tool_error_transactions': 2, 'recorded_cases': 47,
        'pipeline_archives': 45, 'archive_members': 560,
        'denominator_note': 'Overlapping evidence checks, not independent scenes or online sessions.',
    },
    'current_review_online_calls': 0,
    'current_review_rasters': 0,
    'current_review_full_author_matrix_reruns': 0,
    'historical_consumption_001': {
        'completed': 4, 'failed': 2, 'not_run': 0,
        'N3_stream_failure_retained': True,
        'interrupted_usage_coverage': 'unknown',
        'formal_three_pair_performance_qualification': False,
        'regraded': False,
    },
    'accepted_semantics': [
        'State and full content jointly bind successful and legitimate tool-error results.',
        'Raw result equality cannot bypass contradictory status or RPC error.',
        'Actual archive/common callers use the candidate matcher in private globals.',
        'Old module globals, historical status, raw data and usage remain unchanged.',
    ],
    'limits': [
        'Offline checks do not establish online success or new performance benefit.',
        'The author 4.535146-second interval is an offline matrix window only.',
        'New online launcher must freeze candidate files plus inherited execution closure.',
        'Two child AL connections were unbound; no parent handle was borrowed.',
    ],
    'next_cycle': 'M4-ACTIVE-COVERAGE-CONSUMPTION-002',
    'next_plan': info(DOCS[1]),
    'next_scope': {
        'local_wiring_checks': 'N/P once each, zero raster; one correction retry per route only on real wiring failure',
        'fresh_Pro_sessions': 6, 'order': ['N1', 'P1', 'P2', 'N2', 'N3', 'P3'],
        'formal_raster_attempt_cap': 36,
        'task_geometry_prompt_model_and_gates_unchanged': True,
        'no_old_slot_replacement_or_regrading': True,
        'no_third_batch_to_fill_missing_pairs': True,
        'Google_paid_calls': 0,
    },
    'report': info(DOCS[0]),
    'evidence': [info(HERE / p) for p in [
        'IDENTITY.json', 'semantics/RESULTS.json', 'semantics/REVIEW.md',
        'wiring/RESULTS.json', 'wiring/REPORT.md', 'replay/RESULTS.json', 'replay/REVIEW.md',
    ]],
}
save(HERE / 'DECISION.json', decision)
members = sorted([p for p in HERE.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'] + DOCS,
                 key=lambda p: p.relative_to(ROOT).as_posix())
manifest = {'schema': 'independent-review-content-manifest-v1',
            'candidate_commit': CANDIDATE, 'files': [info(p) for p in members]}
save(HERE / 'MANIFEST.json', manifest)
print(json.dumps({'decision': info(HERE / 'DECISION.json'),
                  'manifest': info(HERE / 'MANIFEST.json'),
                  'next_plan': info(DOCS[1]), 'members': len(members)}, ensure_ascii=False))
