"""Independent public-only review; never imports an author scorer or executes evidence code.

Interpretation is manually fixed from all six original finals. The small parser only
expands their unambiguous Markdown tables (including explicitly defined zero groups).
Numeric decisions use exact rational squared distances, not rounded oracle sqrt.
"""
import ast
import csv
import hashlib
import itertools
import json
import math
import re
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

PUBLIC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_surface_scan_consumption_001/runtime/handoff_01/public')
OUT = Path(__file__).resolve().parent
TOL = Fraction('0.000500001')
THRESHOLD = Fraction(0.002)
DECIMAL_RE = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
MANUAL = {
 'answer_007886c1beefd7c6': {
  'complete_quote': '检查完整', 'format': 'explicit_zero_groups_and_positive_table',
  'basis': 'The statement defines each left-hand object paired independently with every listed right-hand object at 0 mm. It does not assert right-hand mutual pairs. The positive table gives six decimal places in mm.',
  'extra_claims': ['24 objects', '978 triangles', '276 unordered pairs', '43 zero and 28 positive', '164 bound-excluded / 112 candidates / 41 measured nonmatches', 'no extra instances', 'finite nondegenerate nonempty geometry', 'readonly'],
 },
 'answer_16df3f049c011e05': {
  'complete_quote': '检查完整', 'format': 'one_pair_per_row',
  'basis': 'The final itself contains all 71 object pairs; nonzero mm values have six decimals and zero is explicitly defined. Hidden-object wording describes inclusion scope, not an assertion that hidden objects exist.',
  'extra_claims': ['24 objects', '276 unordered pairs', '164 bound-excluded / 41 measured nonmatches', 'unknown/deferred/unsupported zero', 'readonly'],
 },
 'answer_3b74126ed5f72eba': {
  'complete_quote': '本次检查完整覆盖当前场景的全部网格对象', 'format': 'positive_table_and_explicit_zero_groups',
  'basis': 'The final explicitly excludes mutual right-hand pairs from the zero-group interpretation. Its 28 positive rows and 43 expanded zero rows are the complete asserted list.',
  'extra_claims': ['24 objects', '978 triangles', '276 unordered pairs', '43 zero and 28 positive', '436640 cross-object triangle pairs', '205 nonmatches', 'nearest nonmatch Obj_002--Obj_008 = 2.249999 mm', 'METRIC scale_length 1', 'finite nondegenerate nonempty geometry', 'readonly'],
 },
 'answer_7958cbdd56ce7e5d': {
  'complete_quote': '检查完整', 'format': 'one_pair_per_row',
  'basis': 'The final itself contains all 71 pairs. Three decimal places in mm satisfy the prompt; six decimals are not required. Zero is explicitly defined and is an allowed representation for exact zero.',
  'extra_claims': ['24 objects', '276 unordered pairs', '164 bound-excluded / 41 measured nonmatches', 'unknown/deferred/unsupported zero', 'all omitted pairs above threshold', 'readonly'],
 },
 'answer_a5958c6899df02aa': {
  'complete_quote': '对当前场景几何的本次检查完整', 'format': 'one_pair_per_row',
  'basis': 'The final supplies the complete list directly, all nonzero distances in mm to six decimal places. Failed intermediate calls are retained; they do not negate the final supported facts.',
  'extra_claims': ['24 objects', '276 unordered pairs', '164 bound-excluded / 41 measured nonmatches', 'unknown/deferred/unsupported zero', 'all omitted pairs above threshold', 'readonly'],
 },
 'answer_b9ec064a37f1c4a1': {
  'complete_quote': '检查完整', 'format': 'one_pair_per_row',
  'basis': 'All 71 final rows state mm values at the requested precision. The separate 2.249999 mm statement is a nonmatch example, not an additional threshold match.',
  'extra_claims': ['24 objects', '978 triangles', '276 unordered pairs', '436640 cross-object triangle pairs', '205 nonmatches', 'nearest nonmatch Obj_002--Obj_008 = 2.249999 mm', 'nondegenerate geometry', 'readonly'],
 },
}


def read_json(relative):
    return json.loads((PUBLIC / relative).read_text(encoding='utf-8'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sq(pair):
    v = pair['exact_squared_distance_m2']
    return Fraction(int(v['numerator']), int(v['denominator']))


def numeric_ok(value_mm, exact_m2):
    lo = max(Fraction(0), value_mm - TOL) / 1000
    hi = (value_mm + TOL) / 1000
    return value_mm >= 0 and lo * lo <= exact_m2 <= hi * hi


def presentation_ok(token, exact_m2):
    if Fraction(token) == 0 and exact_m2 == 0:
        return True
    return Decimal(token).as_tuple().exponent <= -3


def parse_final(txt):
    result = []
    table_lines = []
    for number, line in enumerate(txt.splitlines(), 1):
        if not re.match(r'^\|\s*Obj_\d{3}\s*\|', line):
            continue
        table_lines.append(number)
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(cells) == 3:
            if not re.fullmatch(r'Obj_\d{3}', cells[1]) or not re.fullmatch(DECIMAL_RE, cells[2]):
                raise ValueError(('Unparsed table row', number, line))
            result.append({'pair': tuple(sorted(cells[:2])), 'token': cells[2], 'line': number, 'kind': 'explicit_mm_row'})
        elif len(cells) == 2:
            names = cells[1].split('、')
            if not all(re.fullmatch(r'Obj_\d{3}', n) for n in names):
                raise ValueError(('Unparsed zero group', number, line))
            for other in names:
                result.append({'pair': tuple(sorted((cells[0], other))), 'token': '0', 'line': number, 'kind': 'explicit_zero_group'})
        else:
            raise ValueError(('Unknown row shape', number, line))
    return result, table_lines


def approx_mm(exact_m2):
    with localcontext() as context:
        context.prec = 70
        return (Decimal(exact_m2.numerator) / Decimal(exact_m2.denominator)).sqrt() * 1000


def decode_event_blocks(event):
    for i, block in enumerate((event.get('result') or {}).get('content', [])):
        if block.get('type') == 'text':
            try:
                yield i, json.loads(block['text'])
            except ValueError:
                yield i, {'unparsed_text': block['text']}


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def audit_snapshot(snapshot):
    facts = {'object_names': [], 'triangles': 0, 'vertices': 0, 'nonfinite_vertices': [], 'empty_triangle_objects': [], 'degenerate_triangles': [], 'coordinate_frame': snapshot['coordinate_frame'], 'unit': snapshot['unit'], 'unit_system': snapshot['unit_system'], 'scale_length': snapshot['scale_length']}
    tri_counts = []
    for obj in snapshot['objects']:
        facts['object_names'].append(obj['name'])
        verts = obj['vertices_world']
        # Snapshot vertices are bare coordinate arrays; inspect rather than execute any embedded code.
        xyz = [v['co'] if isinstance(v, dict) else v for v in verts]
        facts['vertices'] += len(xyz)
        triangles = obj['triangles']
        facts['triangles'] += len(triangles)
        tri_counts.append(len(triangles))
        if not triangles:
            facts['empty_triangle_objects'].append(obj['name'])
        for j, v in enumerate(xyz):
            if not all(math.isfinite(c) for c in v):
                facts['nonfinite_vertices'].append([obj['name'], j])
        for j, tri in enumerate(triangles):
            indices = tri['vertices'] if isinstance(tri, dict) else tri
            a, b, c = [tuple(Fraction(v) for v in xyz[k]) for k in indices]
            if cross(sub(b, a), sub(c, a)) == (0, 0, 0):
                facts['degenerate_triangles'].append([obj['name'], j])
    facts['objects'] = len(facts['object_names'])
    facts['unordered_pairs'] = math.comb(facts['objects'], 2)
    facts['cross_object_triangle_pairs'] = sum(a*b for a,b in itertools.combinations(tri_counts, 2))
    facts['geometry_units_consistent'] = facts['coordinate_frame'] == 'world' and facts['unit'] == 'm' and facts['unit_system'] == 'METRIC' and facts['scale_length'] == 1.0
    return facts


def audit_evidence(answer_id, truth_by_pair):
    evidence = read_json(answer_id + '/tool_evidence.json')
    consistency = read_json(answer_id + '/source_consistency.json')
    reviewed = {'completed_public_events': [], 'failed_public_events': [], 'owner_failed_or_missing_attempts': [], 'business_summaries': [], 'code_readonly_review': [], 'source_records': {}}
    for i, attempt in enumerate(evidence['owner_attempts']):
        if attempt.get('is_error') or attempt.get('owner_exception') or attempt.get('request_missing') or attempt.get('response_missing'):
            reviewed['owner_failed_or_missing_attempts'].append({'index': i, 'is_error': attempt.get('is_error'), 'owner_exception': attempt.get('owner_exception'), 'request_missing': attempt.get('request_missing'), 'response_missing': attempt.get('response_missing')})
    for i, wrapper in enumerate(evidence['public_tool_events']):
        event = wrapper['event']
        if event.get('status') == 'in_progress':
            continue
        reference = f'{answer_id}/tool_evidence.json#/public_tool_events/{i}/event'
        if event.get('status') == 'completed':
            reviewed['completed_public_events'].append(reference)
        code = (event.get('arguments') or {}).get('code')
        if code:
            parsed = ast.parse(code)
            calls = sorted(set(ast.unparse(node.func) for node in ast.walk(parsed) if isinstance(node, ast.Call)))
            assignments = sorted(set(ast.unparse(target) for node in ast.walk(parsed) if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) for target in (node.targets if isinstance(node, ast.Assign) else [node.target])))
            reviewed['code_readonly_review'].append({'reference': reference + '/arguments/code', 'call_names': calls, 'assignment_targets': assignments})
        for block_i, payload in decode_event_blocks(event):
            pointer = reference + f'/result/content/{block_i}/text (JSON decoded)'
            if event.get('status') == 'failed' or payload.get('status') == 'error' or event.get('error'):
                reviewed['failed_public_events'].append({'reference': pointer, 'event_status': event.get('status'), 'event_error': event.get('error'), 'result': payload})
            if payload.get('result_kind') == 'surface_scan':
                matches = payload['matches']
                rows = []
                for match in matches:
                    key = tuple(sorted(x['name'] for x in match['objects']))
                    exact = sq(truth_by_pair[key]) if key in truth_by_pair else None
                    rows.append({'pair': key, 'threshold_match': key in truth_by_pair and truth_by_pair[key]['matches_threshold'], 'distance_mm_numeric_ok': exact is not None and numeric_ok(Fraction(str(match['distance_m']))*1000, exact)})
                reviewed['business_summaries'].append({'reference': pointer, 'status': payload['status'], 'coverage': payload['coverage'], 'scope_issues': payload.get('scope_issues'), 'unsupported_objects': payload.get('unsupported_objects'), 'unresolved': payload.get('unresolved'), 'matches': rows})
            native = payload.get('result')
            if isinstance(native, dict) and isinstance(native.get('result'), str):
                lines = native['result'].replace('\\n', '\n').splitlines()
                keep = []
                for line in lines:
                    if any(word in line.lower() for word in ('elapsed', 'timing', 'duration', 'seconds', 'usage', 'cost')):
                        continue
                    if 'Obj_' in line and (line.startswith('Obj_') or len(line) > 1200):
                        continue
                    keep.append(line)
                reviewed['business_summaries'].append({'reference': pointer, 'native_executed': native.get('executed'), 'business_stdout_selected_lines': keep})
    close = consistency['CLOSE']
    reviewed['source_records'] = {
      'initial_final_record_sha256_equal': consistency['INITIAL_original_file_sha256'] == consistency['FINAL_original_file_sha256'],
      'initial_final_record_sha256': consistency['INITIAL_original_file_sha256'],
      'configured_identity_asset_sha256_equal': consistency['ACTOR_CONFIG']['asset_sha256'] == consistency['owner_IDENTITY']['asset_sha256'],
      'asset_sha256': consistency['ACTOR_CONFIG']['asset_sha256'],
      'producer_close': close,
      'scope_limit': consistency['scope'],
    }
    return reviewed


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = read_json('INDEX.json')
    contract = read_json('scoring/SCORING_CONTRACT.json')
    truth = read_json('scoring/TRUTH.json')
    snapshot = read_json('scoring/ACTUAL_SNAPSHOT.json')
    manifest = {str(p.relative_to(PUBLIC)).replace('\\','/'): sha(p.read_bytes()) for p in sorted(PUBLIC.rglob('*')) if p.is_file()}
    assert len(manifest) == 30
    for source in index['scoring_materials']:
        assert manifest[source['file']] == source['sha256']
    assert manifest['scoring/ACTUAL_SNAPSHOT.json'] == truth['snapshot_sha256']
    assert truth['state'] == 'base'
    assert Fraction(contract['distance_policy']['absolute_error_mm']) == TOL
    truth_by_pair = {tuple(sorted((p['object_a'], p['object_b']))): p for p in truth['pairs']}
    assert len(truth_by_pair) == len(truth['pairs']) == 276
    threshold_checks = {key: (sq(pair) <= THRESHOLD**2) == pair['matches_threshold'] for key, pair in truth_by_pair.items()}
    assert all(threshold_checks.values())
    true_keys = {key for key, pair in truth_by_pair.items() if pair['matches_threshold']}
    assert len(true_keys) == 71
    geometry = audit_snapshot(snapshot)
    assert geometry['objects'] == 24 and geometry['triangles'] == 978 and geometry['cross_object_triangle_pairs'] == 436640
    assert not geometry['nonfinite_vertices'] and not geometry['empty_triangle_objects'] and not geometry['degenerate_triangles']
    closest_key, closest = min(((key,pair) for key,pair in truth_by_pair.items() if not pair['matches_threshold']), key=lambda item: sq(item[1]))
    assert closest_key == ('Obj_002', 'Obj_008')
    assert numeric_ok(Fraction('2.249999'), sq(closest))
    assert truth['candidate_count'] == 112
    summaries, cells, evidence_reviews = [], [], {}
    for entry in index['answers']:
        answer_id = entry['anonymous_id']
        manual = MANUAL[answer_id]
        txt = (PUBLIC / answer_id / 'answer.txt').read_text(encoding='utf-8')
        assert manifest[answer_id + '/answer.txt'] == entry['answer_original_sha256'] == entry['source_provenance']['public_final_sha256']
        assert manual['complete_quote'] in txt
        parsed, table_lines = parse_final(txt)
        counts = Counter(row['pair'] for row in parsed)
        by_pair = {row['pair']: row for row in parsed}
        present = set(by_pair)
        false_positive = sorted(present - true_keys)
        omissions = sorted(true_keys - present)
        duplicates = [key for key,count in counts.items() if count != 1]
        numerical_errors, precision_errors, zero_false_claims = [], [], []
        errors = []
        for key, pair in sorted(truth_by_pair.items()):
            row = by_pair.get(key)
            exact = sq(pair)
            if row:
                value = Fraction(row['token'])
                numeric = numeric_ok(value, exact)
                presentation = presentation_ok(row['token'], exact)
                if not numeric: numerical_errors.append(key)
                if not presentation: precision_errors.append(key)
                if value == 0 and exact != 0: zero_false_claims.append(key)
                abs_error = abs(Decimal(row['token']) - approx_mm(exact))
                errors.append(abs_error)
            cells.append({'answer_id': answer_id, 'object_a': key[0], 'object_b': key[1], 'true_threshold_match': pair['matches_threshold'], 'asserted_threshold_match': row is not None, 'pair_membership_correct': (row is not None) == pair['matches_threshold'], 'answer_line': row['line'] if row else '', 'source_kind': row['kind'] if row else '', 'stated_mm': row['token'] if row else '', 'exact_m2_numerator': exact.numerator, 'exact_m2_denominator': exact.denominator, 'truth_mm_display_only': str(approx_mm(exact)), 'numeric_tolerance_exact_pass': numeric if row else '', 'display_precision_pass': presentation if row else '', 'exact_zero_claim_pass': (value != 0 or exact == 0) if row else '', 'absolute_error_mm_display_only': str(abs_error) if row else ''})
        usable = entry['answer_state'] == 'present' and entry['consumer_valid_completion'] and entry['owner_finish_confirmed']
        category = 'complete_correct'
        if not usable: category = 'execution_failed' if entry['execution_record_state'] != 'not_run' else 'not_run'
        elif false_positive or omissions or duplicates or numerical_errors or zero_false_claims: category = 'incorrect'
        elif precision_errors: category = 'incomplete'
        evidence_reviews[answer_id] = audit_evidence(answer_id, truth_by_pair)
        summaries.append({'anonymous_id': answer_id, 'status': category, 'confirmed_usable_final': usable, 'explicit_completeness': True, 'unknown_reported': 0, 'unknown_assessment': 'No unresolved geometry fact found in frozen truth or successful evidence; auxiliary failed requests retained separately.', 'asserted_pair_rows': len(parsed), 'unique_pairs': len(present), 'true_pairs_covered': len(present & true_keys), 'false_positives': false_positive, 'omissions': omissions, 'duplicates': duplicates, 'incorrect_distances': numerical_errors, 'presentation_incomplete_pairs': precision_errors, 'false_exact_zero_claims': zero_false_claims, 'max_abs_error_mm_display_only': str(max(errors)), 'extra_deterministic_errors': [], 'manual_interpretation': manual, 'all_object_table_lines_parsed': table_lines, 'auxiliary_failed_public_event_count': len(evidence_reviews[answer_id]['failed_public_events'])})
    report = {'schema':'independent-manual-quality-review-v1', 'input_root': str(PUBLIC), 'writes_only': str(OUT), 'no_author_scorer_imported': True, 'no_evidence_code_executed': True, 'threshold_binary64_fraction':str(THRESHOLD), 'tolerance_mm_exact':str(TOL), 'manifest':manifest, 'truth_integrity': {'state':truth['state'], 'all_pairs':len(truth_by_pair), 'true_matches':len(true_keys), 'exact_zero_pairs':sum(sq(p)==0 for p in truth_by_pair.values()), 'all_exact_threshold_classifications_agree':all(threshold_checks.values()), 'closest_nonmatch_pair':closest_key, 'closest_nonmatch_mm_display_only':str(approx_mm(sq(closest)))}, 'snapshot_checks':geometry, 'status_counts':dict(Counter(s['status'] for s in summaries)), 'answers':summaries}
    (OUT/'quality_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'business_evidence_review.json').write_text(json.dumps(evidence_reviews,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for filename, rows in [('all_276_pair_cells.csv',cells), ('true_71_pair_cells.csv',[row for row in cells if row['true_threshold_match']])]:
        with (OUT/filename).open('w',newline='',encoding='utf-8-sig') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({'status_counts':report['status_counts'], 'answers':[{k:a[k] for k in ['anonymous_id','status','true_pairs_covered','max_abs_error_mm_display_only','auxiliary_failed_public_event_count']} for a in summaries], 'all_pair_cells':len(cells),'true_pair_cells':sum(row['true_threshold_match'] for row in cells)},indent=2))


if __name__ == '__main__':
    main()
