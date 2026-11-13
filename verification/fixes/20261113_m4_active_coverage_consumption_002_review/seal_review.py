"""Seal independent offline review and bounded next task; no experiment execution."""
import hashlib
import json
from pathlib import Path

ROOT = Path('D:/hefe')
HERE = Path(__file__).resolve().parent
COMMIT = 'c556d29156e7d65fc02238dca63321ac062d2c1a'
REPORT = ROOT / 'docs/M4_ACTIVE_COVERAGE_CONSUMPTION_002_INDEPENDENT_REVIEW.md'
PLAN = ROOT / 'docs/M4_TRIANGULATION_INVARIANT_DISCOVERY_001_PLAN.md'


def read(path):
    return json.loads(path.read_bytes())


def info(path):
    data = path.read_bytes()
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def save(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


identity = read(HERE / 'IDENTITY.json')
quality = read(HERE / 'quality/RESULTS.json')
protocol = read(HERE / 'protocol/RESULTS.json')
cost = read(HERE / 'cost/RESULTS.json')
assert identity['commit'] == quality['candidate_commit'] == protocol['author_commit'] == cost['candidate_commit'] == COMMIT
assert identity['checks'] == identity['passed'] == 3670 and not identity['failed']
assert quality['total'] == quality['passed'] == 655 and not quality['failed']
assert protocol['checks_count'] == protocol['passed'] == 1187 and not protocol['failed']
assert cost['check_count'] == cost['passed'] == 651 and not cost['failed']
assert len(quality['slots']) == 6 and len(cost['slots']) == 6
assert quality['new_model_CLI_actor_renderer_Blender_calls'] == 0
assert protocol['new_CLI_model_actor_Blender_raster_calls'] == 0
assert cost['new_model_CLI_actor_raster_Blender_calls'] == 0
assert protocol['ZIP_count'] == 16 and protocol['ZIP_members'] == 784
assert protocol['formal_tool_successes'] == 14 and protocol['formal_tool_errors'] == 0
assert protocol['local_tool_errors'] == protocol['local_success_recoveries'] == 2
assert cost['paired_time_P_over_N']['numerator'] == 92618391
assert cost['paired_time_P_over_N']['denominator'] == 242856571
assert cost['totals']['N']['reported_input_plus_output'] == 183789
assert cost['totals']['P']['reported_input_plus_output'] == 40733

decision = {
    'schema': 'independent-active-coverage-consumption-002-decision-v1',
    'cycle': 'M4-ACTIVE-COVERAGE-CONSUMPTION-002', 'candidate_commit': COMMIT,
    'decision': 'accept_fixed_task_quality_and_dual_metric_benefit; close_this_model_benchmark',
    'same_version': {k: identity[k] for k in ['checks', 'passed', 'delivery_files', 'member_bytes',
                                           'frozen_files', 'preparation_files', 'old_files']},
    'independent_check_counts': {'quality': 655, 'protocol': 1187, 'cost': 651,
                                 'note': 'Overlapping assertions, not independent scenes.'},
    'formal_execution': {'completed': 6, 'failed': 0, 'not_run': 0, 'fresh_sessions': 6, 'complete_pairs': 3},
    'quality': {'N_passed': 3, 'N_total': 3, 'P_passed': 3, 'P_total': 3,
                'geometric_visibility_entries': 36, 'PNG_NPZ_pairs': 24,
                'explicit_pixel_scalars': 72, 'occluder_claims': 18},
    'paired_time_P_over_N': cost['paired_time_P_over_N'],
    'relative_time_reduction': cost['relative_time_reduction'],
    'reported_input_plus_output': {'N': 183789, 'P': 40733},
    'reported_usage_P_over_N': cost['reported_usage_P_over_N'],
    'relative_reported_usage_reduction': cost['relative_reported_usage_reduction'],
    'formal_consumption': {'tools_N': 11, 'tools_P': 3, 'rasters_N': 18, 'rasters_P': 6,
                           'constructed_sent_received_images': 6, 'PNG_bytes': 20850, 'base64_chars': 27804},
    'timing': cost['timing'],
    'lifecycle': {'CLI_actor_exit0': 6, 'held_stdio_actual_exit1_and_closed': 6,
                  'formal_EXIT_EOF_receipts_unknown': 6, 'actual_process_terminal_state_unknown': 0,
                  'local_normal_EOF_exit0_error_recovery': 2},
    'historical_001_unchanged': {'completed': 4, 'failed': 2, 'N3_interrupted_usage_coverage': 'unknown'},
    'root_new_model_CLI_actor_Blender_raster_calls': 0,
    'scope': 'Isolated prototype, fixed six orthographic views, rectangular target panels and closed-box occluders.',
    'limitations': [
        'No default product installation or original asset changed.',
        'Savings are fixed-task operation time and raw CLI-reported usage, not total R&D workflow or cash fees.',
        'Tool-external time includes backend/network/client waits, not only inference.',
        'Provider model/effort, internal request count, image tokens and cash fees unmeasured.',
        'General surface discovery, self-occlusion, adaptive camera generation and semantic experts not accepted by this batch.',
        'Initial root cost-parser mistaken raw-event equality checks are retained and corrected by known redaction SHA/byte rules.',
    ],
    'next_cycle': 'M4-TRIANGULATION-INVARIANT-DISCOVERY-001',
    'next_plan': info(PLAN), 'report': info(REPORT),
    'next_scope': {'single_object_single_planar_rectangle': True,
                   'problem': 'Equivalent internal triangulation currently changes the discovered target set.',
                   'new_model_or_CLI_consumer_calls': 0, 'new_Blender_or_paid_API_calls': 0,
                   'new_raster_cap': 16, 'fixed_engineering_timing_pairs': 5,
                   'one_evidence_based_simplification_review': True,
                   'third_model_benchmark_batch': False},
    'evidence': [info(HERE / path) for path in ['IDENTITY.json', 'quality/RESULTS.json',
        'quality/REVIEW.md', 'protocol/RESULTS.json', 'protocol/REVIEW.md',
        'cost/RESULTS.json', 'cost/REVIEW.md', 'cost/INITIAL_RESULTS.json', 'cost/PARSE_ADAPTATION.json']],
}
save(HERE / 'DECISION.json', decision)
members = sorted([p for p in HERE.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'] + [REPORT, PLAN],
                 key=lambda p: p.relative_to(ROOT).as_posix())
save(HERE / 'MANIFEST.json', {'schema': 'independent-review-content-manifest-v1',
                            'candidate_commit': COMMIT, 'files': [info(p) for p in members]})
print(json.dumps({'decision': info(HERE / 'DECISION.json'), 'manifest': info(HERE / 'MANIFEST.json'),
                  'next_plan': info(PLAN), 'members': len(members)}, ensure_ascii=False))
