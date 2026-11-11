"""Independent saved-record audit. No imports from product or QA code."""
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import statistics
import struct

WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
B = WT / 'verification/m4_relation_selected_evidence_001'
OUT = Path(__file__).resolve().parent
load = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
data = load(B / 'entry/run_01/RESULTS.json')
fixed = load(B / 'entry/run_01/FIXED_INPUTS.json')
assert fixed == load(B / 'entry/INPUT_BINDINGS.json')
counts = Counter()
comparisons = []
cold = []
sessions = []
work_keys = ('to_mesh', 'triangulations', 'resource_builds', 'world_transforms')
call_keys = ('capture_scene', 'capture_task_scene', '_capture', '_resident_capture')
kernel_keys = ('exact_pair_count', 'closed_solid_pair_count', 'surface_pair_count', 'pair_calls', 'rank_calls')

def vector(row):
    evs = row['worker_received_events']
    out = {'RPC': len(evs)}
    for name in work_keys:
        out[name] = sum(e['qa_work']['after']['totals'].get(name, 0)
                        - e['qa_work']['before']['totals'].get(name, 0) for e in evs)
        assert out[name] == sum(e['qa_work']['host_residency_delta'][name] for e in evs)
    for name in call_keys:
        out[name] = sum(e['qa_work']['python_calls'].get(name, 0) for e in evs)
    out['normalize_completed'] = sum(s['name'] == 'scene.hash' and s['outcome'] == 'completed'
                                    for s in row['request_trace']['spans'])
    assert out['normalize_completed'] == row['successful_normalize_hash_spans']
    for name in kernel_keys:
        out[name] = row['task_work'].get(name, 0)
    return out

for case in data['cases']:
    cid = case['case']['id']
    folder = B / 'entry/run_01' / cid
    events = [json.loads(x) for x in (folder / 'native/WORKER_EVENTS.jsonl').read_bytes().splitlines()]
    received = [e for e in events if type(e.get('sequence')) is int and type(e.get('started_ns')) is int]
    assert len({e['sequence'] for e in received}) == len(received)
    counts['RPC'] += len(received)
    conf = load(folder / 'native/CONFIG.json')
    assert conf['helper_sha256'] == sha(B / 'entry/qa_native.py')
    assert conf['qa_instrumentation_sha256'] == sha(B / 'entry/qa_instrumentation.py')
    rows = {r['label']: r for r in case['rows']}
    assigned = set()
    for row in case['rows']:
        selected = [e for e in received if row['started_ns'] <= e['started_ns'] <= row['ended_ns']]
        assert selected == row['worker_received_events']
        assert not assigned.intersection(e['sequence'] for e in selected)
        assigned.update(e['sequence'] for e in selected)
        counts[row['kind']] += 1
        counts['C_profile_nonempty_events'] += sum(bool(e['qa_work'][k]) for e in selected
                                                    for k in ('C_calls', 'C_returns', 'C_exceptions'))
        if row['kind'] == 'relation':
            actual = load(folder / (row['label'] + '.RESPONSE.json'))
            assert json.loads(actual['result']['content'][0]['text']) == row['body']
    counts['unassigned_control'] += len(received) - len(assigned)
    cold.append({'case': cid, 'work': vector(rows['cold'])})
    warm = [r for label, r in rows.items() if re.fullmatch(r'warm_\d+_OFF', label)]
    sessions.append({'case': cid, 'role': case['case']['role'], 'transformed': case['case']['transformed'],
                     'warm_OFF_n': len(warm),
                     'warm_OFF_median_ms': statistics.median(r['entry_elapsed_ns'] for r in warm) / 1e6})
    if case['case']['role'] == 'candidate':
        for off in warm:
            prefix = off['label'][:-3]
            for mode in ('vertices', 'full'):
                other = rows[prefix + mode]
                lv, rv = vector(off), vector(other)
                delta = {k: rv[k] - lv[k] for k in lv}
                assert set(delta.values()) == {0}
                core = lambda body: {k: v for k, v in body.items() if k not in ('trace_id', 'geometry')}
                assert core(off['body']) == core(other['body'])
                assert other['task_work']['result_cache_hit'] is True
                gens = lambda row: [h['generation'] for e in row['worker_received_events'] for h in e['qa_work']['after']['hosts']]
                assert gens(off) == gens(other)
                comparisons.append({'case': cid, 'mode': mode, 'label': other['label'], 'delta': delta})
    if case['case']['mutation']:
        a, b = rows['changed_OFF'], rows['changed_full']
        av, bv = vector(a), vector(b)
        assert all(bv[k] == 0 for k in (*work_keys, *kernel_keys, 'normalize_completed'))
        assert av['to_mesh'] == 1 and av['normalize_completed'] == 1
        assert av['closed_solid_pair_count'] == av['surface_pair_count'] == 3
        for k in ('scene_revision', 'scene_fingerprint'):
            assert a['body']['context'][k] != rows['cold']['body']['context'][k]
            assert a['body']['context'][k] == b['body']['context'][k]
        mutation = {'OFF': av, 'full': bv}

assert len(comparisons) == 42
assert counts['RPC'] == 138
assert counts['relation'] == 92 and counts['native_supplement'] == 38
assert counts['registered_QA_change'] == 1 and counts['unassigned_control'] == 7

frozen = load(WT / 'verification/m4_observation_baseline_001/scoring/source/qual001/admin/world_geometry.json')
original = {x['name']: x for x in frozen['objects']}
patch = load(B / 'entry/MUTATION_PATCH.json')
source_rows = []
for case in data['cases']:
    for row in case['rows']:
        if not row.get('oracle_retained'):
            continue
        sources = row['worker_received_events'][0]['qa_work']['native_supplement_work']['independent_host_oracle']
        geometry = {o['name']: o for o in row['geometry']['objects']}
        for src in sources:
            old = original[src['name']]
            expected = old['local_vertices']
            if row['label'] == 'changed_oracle' and src['name'] == patch['target_name']:
                expected = [p[:] for p in expected]
                for p in patch['vertices']:
                    expected[p['index']] = [struct.unpack('<f', struct.pack('<f', x))[0] for x in p['co']]
            assert src['vertices_local'] == expected
            assert src['triangles'] == old['triangles'] == geometry[src['name']]['triangles']
            pts = [[float((sum(Fraction(src['matrix_world'][r][c]) * Fraction(p[c]) for c in range(3))
                           + Fraction(src['matrix_world'][r][3])) * Fraction(src['unit_scale_m'])) for r in range(3)]
                   for p in src['vertices_local']]
            err = max(abs(a-b) for p,q in zip(pts,geometry[src['name']]['vertices_world']) for a,b in zip(p,q))
            assert err <= 1e-14
            source_rows.append({'case': case['case']['id'], 'oracle': row['label'], 'object': src['name'], 'error_m': err})

report = {'saved_only': True, 'product_or_Blender_or_model_calls': 0,
          'entry_results_sha256': sha(B / 'entry/run_01/RESULTS.json'),
          'sessions': sessions, 'counts': dict(counts), 'warm_comparisons': comparisons,
          'cold': cold, 'mutation': mutation, 'independent_source_rows': source_rows,
          'helper_and_instrumentation_hashes_match_all_seven_runtime_configs': True,
          'fixed_inputs_match_pre_execution_code_load': True,
          'rigid_tolerance_in_fixed_inputs': fixed['rigid_coordinate_tolerance_m']}
with (OUT / 'RECOMPUTED.json').open('x', encoding='utf8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(json.dumps({'counts': dict(counts), 'pairs': len(comparisons), 'source_rows': len(source_rows), 'sessions': sessions}))
