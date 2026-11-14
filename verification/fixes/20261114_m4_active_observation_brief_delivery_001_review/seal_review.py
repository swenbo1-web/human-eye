"""Seal this offline root review and its next bounded work order."""
from pathlib import Path
import hashlib, json

ROOT = Path('D:/hefe')
OUT = Path(__file__).resolve().parent
REPORT = ROOT / 'docs/M4_ACTIVE_OBSERVATION_BRIEF_DELIVERY_001_INDEPENDENT_REVIEW.md'
PLAN = ROOT / 'docs/M4_ACTIVE_OBSERVATION_PATCH_OWNERSHIP_001_PLAN.md'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

parts = []
for name, expected in [('IDENTITY.json', 3379), ('semantics_result.json', 1249),
                       ('transport_results.json', 685), ('cost_audit.json', 685)]:
    data = json.loads((OUT / name).read_bytes())
    count = data.get('check_count', data.get('checks_count', data.get('assertion_count')))
    if count is None and isinstance(data.get('checks'), list):
        count = len(data['checks'])
    elif count is None and type(data.get('checks')) is int:
        count = data['checks']
    assert data['passed'] is True and count == expected, (name, count)
    parts.append({'file': name, 'sha256': sha(OUT / name), 'checks': count, 'passed': True})
decision = {
    'schema': 'root-active-brief-delivery-review-decision-v1',
    'author_commit': 'cdd2b11693a2586cfea07528c6bca27b93d02499',
    'author_manifest_sha256': '32d1ba995eac5cd84d05a00f16e5fc0ec7da8ae3976ee30cc1d8a52a053fff52',
    'decision': 'accept_scoped_brief_delivery_and_close_P2',
    'independent_assertions': sum(r['checks'] for r in parts),
    'independent_parts': parts,
    'author_test_receipt': {'unit_tests': 33, 'protocol_requests': 17, 'tool_requests': 15,
                            'new_root_business_executions': 0},
    'fixed_historical_cases': 5,
    'text_bytes': {'before': 101824, 'after': 27745, 'saved': 74079, 'saved_fraction': 74079 / 101824},
    'native_image_blocks': 24,
    'not_measured': ['model consumption', 'new current Host capture', 'tokens', 'cash', 'RSS', 'end-to-end model task speed'],
    'annotations': ['Contract nested static hash is a stale pre-freeze read; final freeze/Git/wheel/install independently agree.',
                    'Root cost compact-reencoding assumption corrected against raw RX; initial record retained.',
                    'Existing whole-object geometry limits retained; this delivery change does not expand domain.'],
    'new_root_product_model_Blender_raster_calls': 0,
    'report': {'path': REPORT.relative_to(ROOT).as_posix(), 'sha256': sha(REPORT)},
    'next_cycle': 'M4-ACTIVE-OBSERVATION-PATCH-OWNERSHIP-001',
    'next_plan': {'path': PLAN.relative_to(ROOT).as_posix(), 'sha256': sha(PLAN)},
    'next_design_review': {'path': (OUT / 'semantics_next_patch_design.md').relative_to(ROOT).as_posix(),
                           'sha256': sha(OUT / 'semantics_next_patch_design.md')},
    'next_scope': 'One capability: planar patches, same-object blockers, winning-patch pixels and partial domain scope; one integrated trial and one saved-buffer optimization.',
    'default_activation': False, 'google_paused': True,
}
(OUT / 'DECISION.json').write_text(json.dumps(decision, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
files = sorted([p for p in OUT.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'] + [REPORT, PLAN])
manifest = {'schema': 'root-active-brief-delivery-review-manifest-v1',
    'scope': 'Root independent checks, retained corrections, review decision and next plan; excludes itself.',
    'files': [{'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in files]}
(OUT / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps({'files': len(files) + 1, 'assertions': decision['independent_assertions'],
    'decision_sha256': sha(OUT / 'DECISION.json'), 'manifest_sha256': sha(OUT / 'MANIFEST.json'),
    'plan_sha256': sha(PLAN), 'report_sha256': sha(REPORT)}, ensure_ascii=False))
