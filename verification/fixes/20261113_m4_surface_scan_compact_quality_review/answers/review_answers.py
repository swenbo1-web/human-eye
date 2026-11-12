"""Independent anonymous final-answer scorer; public quality materials only.

This script does not import any author scorer or product code and does not
open cells, runtime, private, cost, usage, or group-map files.
"""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal
import hashlib
import json
import re
from collections import Counter

PUBLIC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_compact_consumption_001/quality/public')
OUT = Path(__file__).resolve().parent
PLAN = Path('D:/hefe/docs/M4_SURFACE_SCAN_COMPACT_CONSUMPTION_001_PLAN.md')
HASHES = {}
EPS = F('0.000500001')
NUM = r'[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?'


def read(path):
    path = path.resolve()
    assert path == PLAN or path.is_relative_to(PUBLIC.resolve())
    data = path.read_bytes()
    HASHES[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def obj(path): return json.loads(read(path))


def parse_final(text):
    rows = []
    unparsed = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not re.match(r'^\|\s*Obj_\d{3}\s*\|', line): continue
        cells = [part.strip() for part in line.strip('|').split('|')]
        a = cells[0]
        parsed = []
        if len(cells) == 3 and re.fullmatch(r'Obj_\d{3}', cells[1]) and re.fullmatch(NUM, cells[2]):
            parsed = [(cells[1], cells[2])]
        elif len(cells) == 2 and re.search(r'Obj_\d{3}[：:]', cells[1]):
            matches = list(re.finditer(r'(Obj_\d{3})\s*[：:]\s*(' + NUM + ')', cells[1]))
            remaining = re.sub(r'(Obj_\d{3})\s*[：:]\s*(' + NUM + ')', '', cells[1]).strip('；; 、,')
            if not remaining: parsed = [m.group(1, 2) for m in matches]
        elif len(cells) == 2:
            names = re.findall(r'Obj_\d{3}', cells[1])
            remaining = re.sub(r'Obj_\d{3}', '', cells[1]).strip('、, ;；')
            # This format is manually confirmed by both relevant finals as
            # A paired individually with every B, all at zero millimetres.
            if names and not remaining: parsed = [(name, '0') for name in names]
        if not parsed:
            unparsed.append({'line': lineno, 'text': line})
        for b, number in parsed:
            rows.append({'pair': sorted([a, b]), 'distance_mm': number, 'line': lineno,
                         'presentation_resolution_mm': str(Decimal(10) ** Decimal(number).as_tuple().exponent)})
    return rows, unparsed


def qvalue(pair):
    q = pair['exact_squared_distance_m2']
    return F(int(q['numerator']), int(q['denominator']))


def in_tolerance(number, q):
    distance = F(number)
    return distance >= 0 and (max(F(0), distance-EPS)/1000)**2 <= q <= ((distance+EPS)/1000)**2


def nested(value):
    yield value
    if isinstance(value, dict):
        for key, sub in value.items():
            if key not in {'usage', 'timing', 'elapsed_ms', 'duration_ms', 'latency_ms'}:
                yield from nested(sub)
    elif isinstance(value, list):
        for sub in value: yield from nested(sub)
    elif isinstance(value, str) and value.lstrip().startswith(('{', '[')):
        try: parsed = json.loads(value)
        except (ValueError, TypeError): return
        yield from nested(parsed)


def evidence_summary(evidence):
    summaries = []
    for attempt in evidence['owner_attempts']:
        req = attempt.get('request') or {}
        args = req.get('params', {}).get('arguments', {})
        facts = []
        outputs = []
        for response in attempt.get('responses', []):
            for node in nested(response.get('value')):
                if not isinstance(node, dict): continue
                if node.get('result_kind') == 'surface_scan':
                    matches = node.get('matches', [])
                    pairs = []
                    if node.get('display_encoding'):
                        for vector in matches:
                            row = dict(zip(node['match_columns'], vector))
                            pairs.append([row['object_a'], row['object_b'], row['distance_m']])
                    else:
                        for row in matches:
                            pairs.append([row['objects'][0]['name'], row['objects'][1]['name'], row['distance_m']])
                    facts.append({'status': node.get('status'), 'threshold_m': node.get('threshold_m'),
                                  'coverage': node.get('coverage'), 'delivery': node.get('delivery'),
                                  'scope': node.get('scope'), 'binding': node.get('binding'), 'pairs': pairs,
                                  'scope_issues': node.get('scope_issues'), 'unsupported_objects': node.get('unsupported_objects'),
                                  'unresolved': node.get('unresolved')})
                if node.get('executed') is True and isinstance(node.get('result'), str):
                    outputs.append(node['result'])
        # Preserve business stdout while avoiding accidental local timing display.
        displayed = ['\n'.join(line for line in s.splitlines() if not re.search(
            r'(elapsed|duration|wall.?time|latency|tokens|usage|\bseconds\b|\bsecs\b)', line, re.I)) for s in outputs]
        summaries.append({'order': attempt['order'], 'is_error': attempt.get('is_error'),
                          'request_missing': attempt.get('request_missing'), 'response_missing': attempt.get('response_missing'),
                          'code': args.get('code'), 'query': args.get('query'),
                          'scan_business_facts': facts, 'native_business_stdout': displayed})
    return summaries


def main():
    index = obj(PUBLIC/'INDEX.json')
    contract = obj(PUBLIC/'scoring/SCORING_CONTRACT.json')
    truth = obj(PUBLIC/'scoring/TRUTH.json')
    snapshot = obj(PUBLIC/'scoring/ACTUAL_SNAPSHOT.json')
    read(PUBLIC/'README.md'); read(PUBLIC/'tasks/T1.txt'); read(PLAN)
    assert len(index['answers']) == index['fixed_slots'] == 9
    actual_snapshot_hash = HASHES[str((PUBLIC/'scoring/ACTUAL_SNAPSHOT.json').resolve())]['sha256']
    assert actual_snapshot_hash == contract['input_materials']['actual_snapshot_sha256']
    assert HASHES[str((PUBLIC/'scoring/TRUTH.json').resolve())]['sha256'] == contract['input_materials']['independent_truth_sha256']
    all_pairs = {tuple(sorted([p['object_a'], p['object_b']])): qvalue(p) for p in truth['pairs']}
    selected = {pair: q for pair, q in all_pairs.items() if q <= F(0.002)**2}
    assert len(all_pairs) == 276 and len(selected) == 71
    assert all(p['matches_threshold'] == (qvalue(p) <= F(0.002)**2) for p in truth['pairs'])
    assert sum(q == 0 for q in selected.values()) == 43
    assert snapshot['counts']['objects'] == 24 and snapshot['counts']['triangles'] == 978
    summaries = {}; results = []
    for slot in index['answers']:
        aid = slot['anonymous_id']; folder = PUBLIC/slot['directory']
        final_bytes = read(folder/slot['answer_file'])
        assert hashlib.sha256(final_bytes).hexdigest() == slot['answer_original_sha256']
        text = final_bytes.decode('utf8'); rows, unparsed = parse_final(text)
        counts = Counter(tuple(row['pair']) for row in rows)
        missing = sorted(set(selected)-set(counts))
        extra = sorted(set(counts)-set(selected))
        duplicates = {str(pair): n for pair, n in counts.items() if n != 1}
        wrong_distances = []; presentation = []
        for row in rows:
            pair = tuple(row['pair']); q = all_pairs.get(pair)
            if q is None or not in_tolerance(row['distance_mm'], q): wrong_distances.append(row)
            if F(row['distance_mm']) != 0 and F(row['presentation_resolution_mm']) > F('0.001'): presentation.append(row)
            if F(row['distance_mm']) == 0 and q != 0: wrong_distances.append({'false_zero': row})
        source = obj(folder/slot['source_consistency_file'])
        summaries[aid] = evidence_summary(obj(folder/slot['evidence_file']))
        consistent = source.get('INITIAL_original_file_sha256') == source.get('FINAL_original_file_sha256')
        close = source.get('CLOSE', {})
        asset_bound = source.get('ACTOR_CONFIG', {}).get('asset_sha256') == '7f6452d1d706a9f2db31126eb3aa7d08622e37a28abb9610992006bad5f5ad66'
        mathematical = not any([missing, extra, duplicates, wrong_distances, presentation, unparsed]) and len(rows)==71
        results.append({'anonymous_id': aid, 'execution_state': slot['cell_execution_state'],
                        'consumer_valid_completion': slot['consumer_valid_completion'],
                        'execution_errors': slot['consumer_execution_errors'],
                        'final_pair_count': len(rows), 'unique_pair_count': len(counts),
                        'missing': missing, 'extra': extra, 'duplicates': duplicates,
                        'distance_errors': wrong_distances, 'presentation_errors': presentation,
                        'unparsed_rows': unparsed, 'pair_distance_presentation_pass': mathematical,
                        'producer_source_records': {'asset_bound': asset_bound, 'initial_final_equal': consistent,
                            'asset_unchanged': close.get('asset_unchanged'), 'geometry_unchanged': close.get('geometry_unchanged')},
                        'manual_semantic_review_pending': True, 'parsed_rows': rows})
    nonmatches = {pair:q for pair,q in all_pairs.items() if pair not in selected}
    nearest_nonmatch = min(nonmatches.values())
    extras = {'minimum_nonmatch_pairs': [list(pair) for pair,q in nonmatches.items() if q == nearest_nonmatch],
              '2.250_mm_within_tolerance': in_tolerance('2.250', nearest_nonmatch),
              'zero_matches': 43, 'positive_matches': 28, 'nonmatches': 205,
              'snapshot_counts': snapshot['counts']}
    report = {'scope': 'anonymous final content and public business evidence, no groups or performance',
              'execution_denominator': dict(Counter(s['cell_execution_state'] for s in index['answers'])),
              'all_pairs': 276, 'matching_pairs': 71, 'answers': results, 'extra_claim_reference': extras}
    for name, value in [('NUMERIC_RESULTS.json', report), ('BUSINESS_EVIDENCE_REVIEW.json', summaries), ('INPUT_HASHES.json', HASHES)]:
        (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'execution_denominator': report['execution_denominator'],
        'results': [{k:v for k,v in r.items() if k not in {'parsed_rows','execution_errors','producer_source_records'}} for r in results],
        'extra_claim_reference': extras}, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
