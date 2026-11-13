"""Independent anonymous table check; no private mapping or cost inputs."""
from fractions import Fraction
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import re

OUT = Path(__file__).parent
PACKAGE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_continuous_consumption_002/quality/ANONYMOUS_QUALITY.zip')
EXPECTED_PACKAGE = '21198b498acbbe0eb3ef68e399b468629094b325eb8cdd75eef532755b068610'
EXPECTED_TRUTH = {
    'BASE': 'a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7',
    'EDIT': 'ccbc66e4071dd3fc8f7fc4c7195e29a6a5a58db39fa1e0a86457b2a8929b1e91',
}


def parse_table(text):
    result = []
    zero_header = False
    for line in text.splitlines():
        if not line.startswith('|'):
            continue
        cols = [c.strip().replace('`', '') for c in line.strip('|').split('|')]
        if not re.fullmatch('Obj_[0-9]{3}', cols[0]):
            if any('对象' in c for c in cols):
                zero_header = len(cols) == 2 and '0' in cols[1]
            continue
        partners = re.findall('Obj_[0-9]{3}', cols[1])
        assert partners and re.fullmatch(r'Obj_\d{3}(?:、Obj_\d{3})*', cols[1]), line
        if len(cols) == 2:
            assert zero_header, line
            number = '0'
        else:
            assert len(cols) == 3 and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', cols[2]), line
            number = cols[2]
        if len(partners) > 1:
            assert Fraction(number) == 0 and ('每个对象' in text or '每一个对象' in text), line
        for partner in partners:
            pair = tuple(sorted([cols[0], partner]))
            assert pair[0] != pair[1]
            result.append((pair, number))
    assert len(result) == len({p for p, _ in result}), 'duplicate pairs'
    return result


def run():
    raw = PACKAGE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_PACKAGE
    records = []
    with ZipFile(PACKAGE) as z:
        truth = {}
        for state, sha in EXPECTED_TRUTH.items():
            body = z.read('scoring/' + state + '_TRUTH.json')
            assert hashlib.sha256(body).hexdigest() == sha
            obj = json.loads(body)
            truth[state] = {tuple(sorted([p['object_a'], p['object_b']])): p for p in obj['pairs']}
            assert len(truth[state]) == 276
        index = json.loads(z.read('INDEX.json'))
        assert index['counts'] == {'completed': 18, 'failed': 0, 'not_run': 0}
        assert len(index['anonymous_episode_order']) == 6
        for episode in index['anonymous_episode_order']:
            prior = None
            for turn, state in enumerate(('BASE', 'BASE', 'EDIT'), 1):
                prefix = f'{episode}/turn_{turn}/'
                body = z.read(prefix + 'answer.txt')
                text = body.decode('utf-8')
                rows = parse_table(text)
                expected = {p for p, v in truth[state].items() if v['matches_threshold']}
                assert len(rows) == (72 if state == 'EDIT' else 71)
                assert {p for p, _ in rows} == expected
                for pair, number in rows:
                    q = truth[state][pair]['exact_squared_distance_m2']
                    squared = Fraction(int(q['numerator']), int(q['denominator']))
                    distance = Fraction(number) / 1000
                    tolerance = Fraction('0.000500001') / 1000
                    assert max(Fraction(0), distance - tolerance) ** 2 <= squared <= (distance + tolerance) ** 2, (episode, turn, pair, number)
                    assert distance == 0 or len(number.split('.')[1]) >= 3
                assert '完整' in text and '276' in text and ('mm' in text or '毫米' in text)
                slot = json.loads(z.read(prefix + 'TURN.json'))
                assert slot['execution_state'] == 'completed' and slot['valid_completion']
                assert not slot['errors'] and not slot['source_consistency_issues']
                assert slot['continuity']['observed_context_matches_events']
                if turn > 1:
                    assert slot['continuity']['expected_matches_observed']
                else:
                    assert slot['continuity']['expected_context'] is None
                assert slot['continuity']['resume_requested'] == (turn > 1)
                current = {p: n for p, n in rows}
                if turn == 2:
                    assert current == prior
                if turn == 3:
                    assert set(current) - set(prior) == {('Obj_002', 'Obj_008')}
                    assert not (set(prior) - set(current))
                    changes = {p for p in current.keys() & prior.keys() if Fraction(current[p]) != Fraction(prior[p])}
                    assert changes == {('Obj_008', 'Obj_013'), ('Obj_008', 'Obj_014')}
                records.append({'episode': episode, 'turn': turn, 'state': ('BASE','REPEAT','EDIT')[turn-1],
                                'answer_sha256': hashlib.sha256(body).hexdigest(), 'matched_facts': len(rows),
                                'primary': 'complete_correct', 'explicit_completeness': True,
                                'execution_public_projection': 'completed',
                                'basis': 'separate full business evidence review; not inferred from table'})
                prior = current
    result = {'package_sha256': EXPECTED_PACKAGE, 'turns': records, 'answers': len(records),
              'matched_facts': sum(r['matched_facts'] for r in records), 'pair_classifications': len(records)*276,
              'primary_complete_correct': 18, 'reference_only': 0, 'delta_only': 0,
              'scope': 'Exact rational squared-interval distance and membership checks of all displayed tables. Grouped zero rows explicitly expanded. Does not substitute for full prose, current-state or private source checks. No timing/usage/mapping read.'}
    (OUT/'ROOT_CROSSCHECK.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'turns'}, ensure_ascii=False))


if __name__ == '__main__':
    run()
