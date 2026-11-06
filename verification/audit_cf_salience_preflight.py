"""Root audit of CF-S source identity, train-only evidence and listed groups."""

from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(path):
    return json.loads(path.read_bytes())


def identity(path):
    content = path.read_bytes()
    return {'sha256': sha256(content).hexdigest(), 'bytes': len(content)}


def main():
    from verification.cf_salience_fixtures import manifest_document
    from verification import test_cf_salience_preflight as preflight

    source = ROOT / 'artifacts/cf/s_preflight_001'
    out = ROOT / 'artifacts/cf/s_root_review_001'
    out.mkdir(parents=True, exist_ok=True)
    receipt = source / 'source-identity.json'
    assert identity(receipt)['sha256'] == '3f42f40a4c67863dd4fcb7196a6ed095cd1b2229f17b0ebef62db58761c50497'
    document = load(receipt)
    checks = []
    for category in ('source', 'artifacts'):
        for item in document[category].values():
            assert identity(ROOT / item['path']) == {key: item[key] for key in ('sha256', 'bytes')}
            checks.append(item['path'])
    counts, groups, all_ids = {}, {}, set()
    for split in ('train', 'validation', 'evaluation', 'diagnostic'):
        actual = load(source / f'manifest-{split}.json')
        expected = json.loads(json.dumps(manifest_document(split=split)))
        assert actual == expected
        rows = actual['episodes']
        counts[split] = len(rows)
        groups[split] = {row['group_id'] for row in rows}
        ids = {row['episode_id'] for row in rows}
        assert len(ids) == len(rows) and all_ids.isdisjoint(ids)
        all_ids.update(ids)
    assert counts == {'train': 720, 'validation': 180, 'evaluation': 180, 'diagnostic': 18}
    assert len(set.union(*groups.values())) == 1089
    from itertools import combinations
    assert all(a.isdisjoint(b) for a, b in combinations(groups.values(), 2))

    materialized = []
    original = preflight.build_fixture
    def track(spec):
        assert spec.split == 'train'
        materialized.append(spec.episode_id)
        return original(spec)
    preflight.build_fixture = track
    try:
        regenerated = preflight.preflight_report()
    finally:
        preflight.build_fixture = original
    assert regenerated == load(source / 'train-and-analytic.json')
    assert sum(row['indexed_faces'] for row in regenerated['train']) == 598
    assert len(materialized) == 4
    result = {'status': 'SOURCE_AND_PREFLIGHT_REPLAY_PASS', 'source_receipt': identity(receipt),
              'source_and_artifact_checks': checks, 'manifest_counts': counts,
              'distinct_groups': 1089, 'distinct_episodes': len(all_ids),
              'materialized_train_ids': materialized, 'regenerated_train_and_analytic': regenerated,
              'scope': 'No training, selection, GPU or holdout/diagnostic geometry; no S performance claim'}
    (out / 'root_audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'identity_checks': len(checks),
                      'counts': counts, 'groups': 1089, 'materialized_train_cases': len(materialized)}))


if __name__ == '__main__':
    main()
