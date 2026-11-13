"""Seal completed offline review and the bounded product-core integration plan."""
import hashlib
import json
from pathlib import Path

ROOT = Path('D:/hefe')
HERE = Path(__file__).resolve().parent
COMMIT = 'b638c499c049604902415965f500f50a9947d34f'
REPORT = ROOT / 'docs/M4_TRIANGULATION_INVARIANT_DISCOVERY_001_INDEPENDENT_REVIEW.md'
PLAN = ROOT / 'docs/M4_ACTIVE_OBSERVATION_CORE_INTEGRATION_001_PLAN.md'


def read(path):
    return json.loads(path.read_bytes())


def info(path):
    raw = path.read_bytes()
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, data):
    path.write_bytes((json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


identity = read(HERE / 'IDENTITY.json')
semantics = read(HERE / 'semantics/RESULTS.json')
geometry = read(HERE / 'geometry/RESULTS.json')
cost = read(HERE / 'cost/RESULTS.json')
assert identity['commit'] == semantics['candidate_commit'] == geometry['candidate_commit'] == cost['candidate_commit'] == COMMIT
assert identity['checks'] == identity['passed'] == 1160 and not identity['failed']
assert semantics['check_count'] == semantics['passed'] == 39 and not semantics['failed']
assert geometry['total'] == geometry['passed'] == 1420 and not geometry['failed']
assert cost['check_count'] == cost['passed'] == 585 and not cost['failed']
assert semantics['candidate_function_calls'] == semantics['author_matrix_or_timing_reruns'] == 0
assert geometry['candidate_or_author_validator_execution'] == geometry['new_model_CLI_actor_Blender_raster_calls'] == 0
assert cost['new_model_CLI_actor_Blender_raster_candidate_calls'] == 0
assert len(geometry['certificates']) == 32 and len(geometry['pixel_facts']) == 48
assert geometry['complete_indices'] == 24 and geometry['classification_rows'] == 864 and geometry['ROI_rows'] == 144
assert len(cost['pairs']) == 5

decision = {
    'schema': 'independent-triangulation-discovery-001-decision-v1',
    'cycle': 'M4-TRIANGULATION-INVARIANT-DISCOVERY-001', 'candidate_commit': COMMIT,
    'decision': 'accept_candidate_in_declared_rectangle_domain; stop_current_fixture_tuning',
    'selected_algorithm': 'candidate_projected_2D_determinant_after_exact_coplanarity',
    'identity': {k: identity[k] for k in ['checks', 'passed', 'delivery_files', 'member_bytes',
        'frozen_files', 'preparation_files', 'old_delivery_files']},
    'independent_checks': {'semantics': 39, 'geometry_pixels': 1420, 'cost_flow': 585,
        'note': 'Overlapping record checks, not independent scenes.'},
    'geometry': {'surface_certificates': 32, 'complete_indices': 24, 'classification_rows': 864,
        'ROI_rows': 144, 'pixel_rows': 48, 'new_images_in_author_batch': 8,
        'each_chain': {'views': ['SCENE', 'BACK'], 'increments': [2, 3], 'covered': 5, 'finite_pool_uncovered': 1},
        'depth_differences': geometry['depth_differences']},
    'cost': {k: cost[k] for k in ['pairs', 'median_ratio', 'full_index_totals_ns', 'total_ratio',
        'discovery_stage_medians_ns', 'full_time_regressions', 'payload_totals', 'phase_time', 'actual_recorded_counts']},
    'root_candidate_model_CLI_actor_Blender_raster_calls': 0,
    'default_product_changed': False,
    'limits': [
        'Single-object connected hole-free consistently wound exactly planar rectangular surface only.',
        'Per-object expected-linear work; whole discovery and geometry retain sorting costs.',
        'Current timings include instrumentation, and unchanged stages vary; not all 12.2% is determinant-only causality.',
        'First two timing regressions and all eight real depth arrays remain preserved.',
        'Historical harness API limitations did not invalidate the actual frozen single-controller sequence.',
        'Author three readback failures and root initial 24 frame-order parser failures are preserved.',
        'General surfaces, multi-patch objects, shared-object occlusion and semantic experts remain outside this acceptance.',
    ],
    'next_cycle': 'M4-ACTIVE-OBSERVATION-CORE-INTEGRATION-001',
    'next_plan': info(PLAN), 'report': info(REPORT),
    'next_scope': {'product_core_static_imports_and_explicit_parsed_geometry': True,
        'default_algorithm': 'candidate', 'default_fine_grained_audit_counters': False,
        'isolate_wheel_installation': True, 'default_MCP_Hook_installation_changed': False,
        'new_model_CLI_consumer_Blender_paid_API_calls': 0, 'expected_new_rasters': 6,
        'new_raster_cap': 8, 'fixed_engineering_pairs': 5,
        'MCP_host_scene_acquisition_in_this_batch': False},
    'evidence': [info(HERE / p) for p in ['IDENTITY.json', 'semantics/RESULTS.json', 'semantics/REVIEW.md',
        'geometry/RESULTS.json', 'geometry/REVIEW.md', 'cost/RESULTS.json', 'cost/REVIEW.md',
        'cost/INITIAL_RESULTS.json', 'cost/PARSE_ADAPTATION.json']],
}
save(HERE / 'DECISION.json', decision)
members = sorted([p for p in HERE.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'] + [REPORT, PLAN],
                 key=lambda p: p.relative_to(ROOT).as_posix())
save(HERE / 'MANIFEST.json', {'schema': 'independent-review-content-manifest-v1',
    'candidate_commit': COMMIT, 'files': [info(p) for p in members]})
print(json.dumps({'decision': info(HERE / 'DECISION.json'), 'manifest': info(HERE / 'MANIFEST.json'),
                  'next_plan': info(PLAN), 'members': len(members)}, ensure_ascii=False))
