"""Seal the completed root-only offline review; do not execute product code."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path('D:/hefe')
OUT = ROOT / 'verification/fixes/20261114_m4_localization_consumption_001_review'
DOCS = [ROOT / 'docs/M4_REGION_LOCALIZATION_CONSUMPTION_001_INDEPENDENT_REVIEW.md',
        ROOT / 'docs/M4_EXPLICIT_OBSERVATION_CONSUMPTION_001_PLAN.md']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()

assert git('branch', '--show-current') == 'codex/perf010-direct-task-query'
assert git('rev-parse', 'HEAD') == '8b4cb6645e159122bc5f22b459f04f09750caf91'
assert not git('diff', '--cached', '--name-only')
expected = [('IDENTITY.json', 6778), ('quality/RESULTS.json', 9150),
            ('adoption/RESULTS.json', 1584), ('cost/RESULTS.json', 945)]
results = {}
for name, count in expected:
    path = OUT / name
    obj = json.loads(path.read_text(encoding='utf-8-sig'))
    assert obj['passed'] is True and obj['checks'] == count and not obj['failures'], name
    results[name] = {'sha256': digest(path), 'checks': count, 'passed': True}
decision = {
    'reviewed_commit': '21b2871df70c5fedde4a916c67983ee40c626f89',
    'product_commit': '7d42bb939c7881a98fe322c10c216398f6c7aecc',
    'product_source_sha256': '96d7da8c50680a73f251496406c9f0bbbf6b38bd4dfe848c931e45f094343b76',
    'root_scope': 'M4_only', 'expert_line_managed_elsewhere': True,
    'quality': {'passed_slots': 6, 'total_slots': 6, 'records': 828,
                'position_answers': 18, 'frames': 36,
                'per_slot': {'observed': 115, 'unobserved_backfacing': 22,
                             'unobserved_occluded': 1, 'unsupported_components': 1}},
    'adoption': {'P_active_slots': 0, 'P_total_slots': 3,
                 'formal_active_calls': 0, 'cause': 'not_established',
                 'automatic_hook': 'disabled_in_experiment_not_tested'},
    'product_consumption': 'not_established',
    'product_benefit': 'not_established_no_actual_product_call',
    'cost_records': 'independently_reconciled_descriptive_only',
    'normal_thin_EOF': 'unknown', 'held_thin_exit': 1,
    'new_root_product_model_Blender_raster_benchmark_calls': 0,
    'offline_checks': results,
    'next_cycle': 'M4-EXPLICIT-OBSERVATION-CONSUMPTION-001',
    'next_limits': {'fresh_real_consumers': 1, 'user_turns': 1, 'seconds': 450,
                    'tool_attempts': 12, 'formal_raster_attempts': 6,
                    'new_prep_raster_attempts': 0, 'external_retries': 0},
    'next_plan_sha256': digest(DOCS[1]),
    'plan_review_clarifications': ['session_count_not_provider_requests',
                                 'explicit_success_not_historical_cause_proof'],
    'paid_Google': 'paused', 'default_deployment': 'unchanged',
}
(OUT / 'DECISION.json').write_text(json.dumps(decision, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
paths = sorted([p for p in OUT.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'] + DOCS)
assert not any(p.suffix in ('.pyc', '.pyo') for p in paths)
manifest = {'files': [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
                       'sha256': digest(p)} for p in paths]}
(OUT / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'sealed_files_excluding_manifest': len(paths),
                  'next_plan_sha256': decision['next_plan_sha256'],
                  'manifest_sha256': digest(OUT / 'MANIFEST.json')}, ensure_ascii=False))
