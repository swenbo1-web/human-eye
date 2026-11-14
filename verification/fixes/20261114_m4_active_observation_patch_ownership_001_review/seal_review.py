"""Seal independent review and the single next delivery work order."""
from pathlib import Path
import hashlib, json

ROOT = Path('D:/hefe')
OUT = Path(__file__).resolve().parent
REPORT = ROOT / 'docs/M4_ACTIVE_OBSERVATION_PATCH_OWNERSHIP_001_INDEPENDENT_REVIEW.md'
PLAN = ROOT / 'docs/M4_ACTIVE_OBSERVATION_REGION_ANCHORS_001_PLAN.md'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

parts = []
for file, count in [('IDENTITY.json', 6475), ('geometry/RESULTS.json', 16365),
                    ('pixel_delivery/RESULTS.json', 5289), ('cost/RESULTS.json', 523)]:
    value = json.loads((OUT / file).read_bytes())
    assert value['passed'] and value['check_count'] == count
    parts.append(dict(file=file, sha256=sha(OUT / file), checks=count, passed=True))
assert json.loads((OUT / 'geometry/FRUSTUM.json').read_bytes())['passed']
decision = {
    'schema': 'root-patch-ownership-review-decision-v1',
    'author_commit': 'efe7f77aabdab4f8de47fdb4f8714cb25f301503',
    'author_manifest_sha256': '44cbbfa1daf79b804c828aa2091cfd826acf34bf16632031e7053faec7fc2668',
    'decision': 'accept_scoped_multi_patch_ownership_capability; next fix concrete model localization gap',
    'independent_assertions': sum(p['checks'] for p in parts), 'parts': parts,
    'additional_frustum': {'views': 6, 'vertices_per_view': 1913, 'path': 'geometry/FRUSTUM.json',
                           'sha256': sha(OUT / 'geometry/FRUSTUM.json')},
    'actual_scope': {'world_scenes': 1, 'representations': 2, 'regions': 138, 'covered': 115,
                     'finite_pool_unknown': 23, 'supported_triangles': 3336, 'unsupported_triangles': 1,
                     'capture_calls': 5, 'prepare_calls': 2, 'new_rasters': 6,
                     'protocol_requests': 7, 'tool_requests': 5, 'native_image_deliveries': 15},
    'source_digest': '8490ad360d4c52850038ceb7c55576c0118f9f920dcbf5451de6808c141ebb40',
    'cost': {'cold_request_ms': [4346.2748, 4251.1099], 'hot_request_ms': [51.0646, 46.4293],
             'index_ms': [3233.0560, 3278.4676], 'aggregation_medians_ms': [4.2049, 1.0026],
             'kernel_saving_percent': (1 - 1.0026 / 4.2049) * 100,
             'meaning': 'Local fixed-buffer kernel timing; no model or native task benefit measured.'},
    'known_delivery_gap': '138 joined ROI rows share object 0; public brief/full lacks world geometry and image locations, so opaque IDs cannot be directly located without another source read.',
    'failure_history': ['R1 65 tests: 1 failure,1 error', 'R2 guard startup failure:0 tests',
                       'R3 65 tests passed; same R2 product', 'Host Bad Request after units_03; no rerun of successful units/build',
                       'Independent pixel audit initial five binding assumptions corrected; original retained'],
    'new_root_product_model_Blender_raster_benchmark_calls': 0,
    'not_measured': ['model usability', 'model task/native comparison', 'tokens', 'cash', 'RSS'],
    'report': {'path': REPORT.relative_to(ROOT).as_posix(), 'sha256': sha(REPORT)},
    'next_cycle': 'M4-ACTIVE-OBSERVATION-REGION-ANCHORS-001',
    'next_plan': {'path': PLAN.relative_to(ROOT).as_posix(), 'sha256': sha(PLAN)},
    'next_design_review': {'path': 'pixel_delivery/NEXT_ANCHORS_DESIGN.md',
                          'sha256': sha(OUT / 'pixel_delivery/NEXT_ANCHORS_DESIGN.md')},
    'next_scope': 'World center/half-edges/front direction once per ROI; actual owned-image anchors. One shared-pass optimization, one installed joined cold/hot/full, then model-use comparison gate.',
    'default_activation': False, 'google_paused': True,
}
(OUT / 'DECISION.json').write_text(json.dumps(decision, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
files = sorted([p for p in OUT.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'] + [REPORT, PLAN])
manifest = {'schema': 'root-patch-ownership-review-manifest-v1',
    'scope': 'Independent source, geometry, pixels, cost, retained failures, decision and next plan. Excludes itself.',
    'files': [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in files]}
(OUT / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
print(json.dumps(dict(files=len(files)+1, assertions=decision['independent_assertions'],
    decision_sha256=sha(OUT/'DECISION.json'), manifest_sha256=sha(OUT/'MANIFEST.json'),
    plan_sha256=sha(PLAN), report_sha256=sha(REPORT)), ensure_ascii=False))
