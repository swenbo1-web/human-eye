"""Seal existing root and independent quality before private unblinding."""
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path('D:/hefe')
BASE = Path(__file__).resolve().parent


def record(path):
    data = path.read_bytes()
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    root = json.loads((BASE/'ROOT_RESULTS.json').read_bytes())
    independent = json.loads((BASE/'independent/quality_results.json').read_bytes())
    a = {x['anonymous_id']: x['status'] for x in root['scores']}
    b = {x['anonymous_id']: x['status'] for x in independent['answers']}
    assert a == b and len(a) == 6 and set(a.values()) == {'complete_correct'}
    assert json.loads((BASE/'integrity/RESULTS.json').read_bytes())['passed'] is True
    assert json.loads((BASE/'contract/RESULTS.json').read_bytes())['all_passed'] is True
    anchors = ['ROOT_RESULTS.json', 'ROOT_MANUAL_REVIEW.md', 'ROOT_PAIR_CHECKS.json',
               'independent/quality_results.json', 'independent/REPORT.md',
               'independent/true_71_pair_cells.csv', 'independent/all_276_pair_cells.csv',
               'integrity/RESULTS.json', 'integrity/REPORT.md',
               'contract/RESULTS.json', 'contract/REPORT.md']
    seal = {
        'schema': 'm4_surface_scan_consumer_quality_seal_v1',
        'cycle': 'M4-SURFACE-SCAN-CONSUMPTION-001',
        'delivery_commit': 'e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3',
        'preparation_commit': 'bedcc827ec548e3afab816c0986db0c99eb42bb8',
        'product_commit': 'c1cb2da32034e056a270384e691a2cde8dddbc0d',
        'runtime_source_sha256': 'c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943',
        'anonymous_zip_sha256': '05638c8d324c661e7d8c816fe737045516dd7440d1018023c83149dc549f1051',
        'public_manifest_canonical_sha256': '1c58a4b2ecc758b27764a5c500ad38825b6acb9894b5677bce2def666076b23f',
        'stage': 'quality_sealed_before_private_group_cost_usage_unblinding',
        'private_semantic_read_count': 0,
        'blindness': 'imperfect; business tool content reveals route; no mapping or cost accessed',
        'quality': root['totals'], 'answers': root['scores'],
        'root_independent_status_agreement': True,
        'fixed_scenes': 1, 'model_slots': 6,
        'additional_runs': {'Blender': 0, 'model_consumers': 0, 'API': 0},
        'evidence': [record(BASE/name) for name in anchors],
        'deferred_source_checks': [
            'private model final/event projections and anonymous mapping',
            'six actual fresh threads and 12 actual initial/final snapshots',
            'actual runtime source per process and start order',
            'actual full timing and usage',
            'thin-client EXIT remains unknown until evidence exists'],
        'next': 'M4-SURFACE-SCAN-CONSUMPTION-001_COST_READY; existing records only; no rerun',
    }
    seal_path = BASE/'QUALITY_SEAL.json'
    seal_path.write_text(json.dumps(seal, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    manifest_path = BASE/'REVIEW_MANIFEST.json'
    docs = [ROOT/'docs/M4_SURFACE_SCAN_CONSUMPTION_001_QUALITY_REVIEW.md',
            ROOT/'docs/M4_SURFACE_SCAN_CONSUMPTION_001_COST_PLAN.md']
    paths = [p for p in BASE.rglob('*') if p.is_file() and p != manifest_path and '__pycache__' not in p.parts]+docs
    paths.sort(key=lambda p: p.relative_to(ROOT).as_posix())
    for path in paths:
        if path.suffix == '.json':
            json.loads(path.read_bytes())
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    files = [record(path) for path in paths]
    manifest = {'cycle': 'M4-SURFACE-SCAN-CONSUMPTION-001-QUALITY-REVIEW',
                'files': files, 'file_count': len(files), 'total_bytes': sum(x['bytes'] for x in files)}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'seal': record(seal_path), 'manifest': record(manifest_path),
                      'file_count': len(files), 'docs': [record(path) for path in docs]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
