"""Seal completed public-only reviews before cost/map access. No product execution."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path('D:/hefe')
OUT = Path(__file__).resolve().parent
DOC = ROOT / 'docs/M4_SPATIAL_FACT_CONSUMPTION_001_QUALITY_REVIEW.md'
TARGET = OUT / 'QUALITY_SEAL.json'
assert not TARGET.exists(), 'Existing seal must not be replaced.'
scores = json.loads((OUT / 'root_quality/SCORES.json').read_text(encoding='utf-8'))
assert len(scores['scores']) == 6
assert all(s['status'] == 'complete_correct' for s in scores['scores'])
required = [OUT / d / f for d, f in [
    ('independent_quality', 'REPORT.md'), ('independent_quality', 'SCORES.json'),
    ('witness', 'REVIEW.md'), ('witness', 'WITNESS_RESULTS.json'),
    ('source', 'REPORT.md'), ('source', 'RESULTS.json')]]
assert all(p.is_file() for p in required)
paths = sorted([p for p in OUT.rglob('*') if p.is_file()] + [DOC], key=lambda p: p.as_posix())
records = []
for p in paths:
    raw = p.read_bytes()
    records.append({'path': p.relative_to(ROOT).as_posix(), 'bytes': len(raw),
                    'sha256': hashlib.sha256(raw).hexdigest()})
seal = {
    'schema': 'm4-quality-before-cost-seal-v1',
    'sealed_at_utc': datetime.now(timezone.utc).isoformat(),
    'cycle': 'M4-SPATIAL-FACT-CONSUMPTION-001',
    'author_evidence_commit': '5cdf62f311f94890ca569d06c1a858f1578225e4',
    'root_plan_commit': 'bd174a29a9f6d524f8b7bab1851982600be1cfbb',
    'root_plan_sha256': 'aa6b4ffaf6eb6ca93c4fec28a3134fedd25a0c5be54582f9f47fdbd044ed040a',
    'public_packet_sha256': 'efc074849f20b15f6ad1702467c765dbb576f5846b68e7a00754c776abd1fb9f',
    'private_map_cost_usage_read_before_seal': False,
    'blindness': 'group labels and cost withheld; business tool names may reveal route',
    'quality': {'complete_correct': 6, 'incomplete': 0, 'incorrect': 0,
                'execution_failed': 0, 'not_run': 0, 'facts_correct': 78, 'facts_required': 78},
    'root_and_independent_scorer_agree': True,
    'execution_receipt_limitation': '6 thin-client EXIT receipts absent; actual shutdown subject to raw evidence review',
    'files': records,
    'file_manifest_sha256': hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    'next': 'Commit and push this seal before authorizing saved-data cost/map unseal; no additional consumers.'
}
TARGET.write_text(json.dumps(seal, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps({'sealed_files': len(records), 'seal_sha256': hashlib.sha256(TARGET.read_bytes()).hexdigest(), 'quality': seal['quality']}))
