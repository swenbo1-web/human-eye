"""Root check of anonymous final tables and fixed denominator, without cost inputs."""
from fractions import Fraction
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import re

ROOT = Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_quality_review')
PACKAGE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_continuous_consumption_001/quality/ANONYMOUS_QUALITY.zip')
raw = PACKAGE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'c062e993a1c46d7f7b77215120cafb1d973bf003b5c04436f848be814ec4939d'
results = []
with ZipFile(PACKAGE) as archive:
    original_truth = archive.read('scoring/BASE_TRUTH.json')
    assert hashlib.sha256(original_truth).hexdigest() == 'a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7'
    truth = json.loads(original_truth)
    pair_truth = {tuple(sorted((p['object_a'], p['object_b']))): p for p in truth['pairs']}
    matches = {p for p, v in pair_truth.items() if v['matches_threshold']}
    assert len(pair_truth) == 276 and len(matches) == 71
    index = json.loads(archive.read('INDEX.json'))
    assert index['counts'] == {'completed': 0, 'failed': 6, 'not_run': 12}
    for episode in index['anonymous_episode_order']:
        text = archive.read(episode + '/turn_1/answer.txt').decode('utf-8')
        rows = re.findall(r'^\|\s*(Obj_\d+)\s*\|\s*(Obj_\d+)\s*\|\s*([0-9.]+)\s*\|', text, re.M)
        normalized = [(tuple(sorted((a, b))), d) for a, b, d in rows]
        assert len(normalized) == len({p for p, _ in normalized}) == 71
        assert {p for p, _ in normalized} == matches
        for pair, displayed_mm in normalized:
            exact = pair_truth[pair]['exact_squared_distance_m2']
            squared = Fraction(int(exact['numerator']), int(exact['denominator']))
            distance = Fraction(displayed_mm) / 1000
            tolerance = Fraction('0.000500001') / 1000
            assert max(Fraction(0), distance - tolerance) ** 2 <= squared <= (distance + tolerance) ** 2
            assert distance == 0 or len(displayed_mm.split('.')[1]) >= 3
        assert '完整' in text and ('mm' in text or '毫米' in text)
        for turn in (2, 3):
            slot = json.loads(archive.read(f'{episode}/turn_{turn}/TURN.json'))
            assert slot['execution_state'] == 'not_run'
        results.append({'anonymous_episode_id': episode, 'BASE_table': 'complete_correct', 'matched_pairs': 71,
                        'execution': 'failed_retained', 'later_turns': 'not_run',
                        'manual_read': 'Reviewed full final prose and public code/tool response; surface/solid distinction and additional quantitative claims supported.'})

result = {'package_sha256': hashlib.sha256(raw).hexdigest(), 'episodes': results,
          'actual_answer_count': 6, 'actual_positive_facts': 426, 'planned_turns': 18,
          'execution_completed': 0, 'execution_failed': 6, 'not_run': 12,
          'scope': 'Independent table and denominator crosscheck; full source/closure and detailed current-state evidence reviewed separately. No private mapping, model usage or administrative timing inputs.'}
(ROOT / 'ROOT_CROSSCHECK.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps({'answers': 6, 'facts': 426, 'execution_completed': 0, 'failed': 6, 'not_run': 12}))
