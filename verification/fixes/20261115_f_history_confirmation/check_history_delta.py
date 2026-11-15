"""Bounded confirmation of an unchanged, already reviewed historical series."""
from collections import defaultdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT = Path('D:/hefe')
BASE = ROOT / 'verification/fixes/20261106_perf020_o4'
OUT = Path(__file__).parent
PINS = {
    'cost/formal_01/FREEZE.json': '0d81a37e894f4902407a20c71c6b9c12d6c05c9aa7ff23a5f3e3aa8b5bae354f',
    'cost/formal_01/SUMMARY.json': '4def42eca7c0ee521600487f4d912b7af6d8ea0e8b24ac9c3a890cb4502840f0',
    'QUALIFICATION_PLAN.json': 'b9890f96bf1e56dac72ba327dafa0203919c3ee7e3f932fc230a5b972e09d4aa',
    'MECHANISM_SCORE.json': '1ede9d31bf6bf917aa4a61fb6ddf73b24f3c0143def2844e1cdac6926bdda836',
    'FORMAL_SCORE.json': '3804a8827d3106af3ec4dc140a0f6a4d012920b5aa9399746a1416a4745bc81b',
    'RESTORED_E.json': '23e832c354aff3e0c2de2a31dddd64c161663dfaf825e833cd77139ef2a21e92',
}
inputs = {}
for relative, expected in PINS.items():
    data = (BASE / relative).read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected, relative
    inputs[relative] = json.loads(data)
freeze = inputs['cost/formal_01/FREEZE.json']
summary = inputs['cost/formal_01/SUMMARY.json']
plan = inputs['QUALIFICATION_PLAN.json']['mechanism_contract']
assert freeze['qualification_plan_sha256'] == PINS['QUALIFICATION_PLAN.json']
assert summary['freeze_sha256'] == PINS['cost/formal_01/FREEZE.json']
runs = summary['results']
assert len(runs) == 30 and not summary['remaining_registered_runs_unrun']
assert summary['formal_series_count'] == 1 and summary['no_retry'] is True
assert [(r['block'], r['tier'], r['arm'], r['folder'], r['run_nonce']) for r in runs] == [
    (r['block'], r['tier'], r['arm'], r['folder'], r['run_nonce']) for r in freeze['run_order']]
expected_source = {'A': 'e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163',
                   'B': '30b28aab341dcec6d7504a95a15089acda506af0a0c11bd14ffd6644ecdb258d'}
groups, blocks, cycles = defaultdict(list), defaultdict(list), defaultdict(dict)
for run in runs:
    assert run['status'] == 'passed' and len(run['calls']) == 10
    for call in run['calls']:
        assert call['received_ns'] - call['sent_ns'] == call['round_trip_ns']
        assert call['binding']['source_sha256'] == expected_source[run['arm']]
        assert call['status'] == 'passed'
        key = (run['tier'], call['category'], run['arm'])
        groups[key].append(call['round_trip_ns'])
        blocks[(*key, run['block'])].append(call['round_trip_ns'])
    cycles[(run['tier'], run['arm'])][run['block']] = sum(c['round_trip_ns'] for c in run['calls'])

def median(values):
    seq = sorted(map(F, values)); n = len(seq)
    return (seq[(n - 1) // 2] + seq[n // 2]) / 2

def stats(values):
    seq = sorted(values)
    return median(seq), F(seq[(95 * len(seq) + 99) // 100 - 1])

def limit(config, prefix, reference):
    return max(F(config[prefix + '_floor_ns']), reference * F(*config[prefix + '_fraction']))

records, failures = [], []
for tier in ('8', '64', '256'):
    for category in ('first', 'static', 'pose', 'geometry'):
        a, b = groups[(tier, category, 'A')], groups[(tier, category, 'B')]
        assert len(a) == len(b) == (5 if category == 'first' else 15)
        am, ap = stats(a); bm, bp = stats(b)
        cfg = plan['cold' if category == 'first' else 'warm']
        p95_limit = limit(cfg, 'p95_regression', ap)
        if bp - ap > p95_limit:
            failures.append({'tier': tier, 'category': category, 'metric': 'p95',
                             'regression_ns': bp-ap, 'allowed_ns': p95_limit})
        if category == 'first':
            median_limit = limit(cfg, 'median_regression', am)
            ok = bm - am <= median_limit and bp - ap <= p95_limit
            if bm - am > median_limit:
                failures.append({'tier': tier, 'category': category, 'metric': 'median',
                                 'regression_ns': bm-am, 'allowed_ns': median_limit})
        else:
            wins = sum(median(blocks[(tier, category, 'A', block)]) - median(blocks[(tier, category, 'B', block)]) >=
                       limit(cfg, 'gain', median(blocks[(tier, category, 'A', block)])) for block in range(5))
            ok = am - bm >= limit(cfg, 'gain', am) and wins >= cfg['minimum_block_wins'] and bp - ap <= p95_limit
        records.append({'tier':tier, 'category':category, 'E_median_ns':am, 'F_median_ns':bm,
                        'E_p95_ns':ap, 'F_p95_ns':bp, 'pass':ok})

cycle_records = []
for tier in ('8', '64', '256'):
    a, b = cycles[(tier,'A')], cycles[(tier,'B')]
    am, bm = median(a.values()), median(b.values())
    cfg = plan['cycle']
    wins = sum(a[i]-b[i] >= limit(cfg, 'gain', F(a[i])) for i in range(5))
    cycle_records.append({'tier':tier, 'E_median_ns':am, 'F_median_ns':bm,
                          'gain_fraction':(am-bm)/am, 'wins':wins,
                          'pass':am-bm >= limit(cfg,'gain',am) and wins >= cfg['minimum_pair_wins']})
assert {(r['tier'],r['category'],r['metric']) for r in failures} == {
    ('8','first','p95'),('64','first','median'),('256','pose','p95'),('256','geometry','p95')}
assert sum(r['pass'] for r in records if r['category'] != 'first') == 7
assert sum(r['pass'] for r in records if r['category'] == 'first') == 1
assert all(r['pass'] for r in cycle_records)
result = {'scope':'unchanged historical pins and saved SUMMARY arithmetic; no scorer/product execution',
          'pins':PINS, 'runs':len(runs), 'observations':sum(len(r['calls']) for r in runs),
          'classes':records, 'mechanism_failures':failures, 'cycles':cycle_records,
          'decision':'maintain historical F non-admission; no new rollback of current M4',
          'not_repeated':['1327-member historical archive full audit','actual product or Blender','default deployment identity'],
          'new_model_Blender_raster_calls':0}
(OUT/'RESULT.json').write_text(json.dumps(result,indent=2,default=str)+'\n',encoding='utf8')
print(json.dumps({'runs':len(runs),'observations':300,'failures':failures,'decision':result['decision']},default=str))
