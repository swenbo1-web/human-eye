"""Normalize three actual N answers from final text and its cited artifact.

No administrator truth, qualification, scorer, usage, timing or cost is read.
The N2 candidate-direction contradiction is retained with current tool proof.
"""

import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent.parent
FORMAL = Path('D:/he_occluded_transfer_001/formal')
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def text(path):
    return raw(path).decode('utf-8')


def read(path):
    return json.loads(raw(path))


def support(excerpt, source='final'):
    return {'source_id': source, 'excerpt': excerpt}


def identity(name, faces, index=None):
    result = {'object_name': name, 'source_triangle_indices': faces}
    if index is not None:
        result['object_index'] = index
    return result


def line_containing(body, token):
    rows = [line for line in body.splitlines() if token in line]
    if len(rows) != 1:
        raise ValueError('one_actual_line_required:' + token)
    return rows[0]


def base(slot):
    path = FORMAL / slot / 'c/PUBLIC_FINAL.txt'
    body = text(path)
    row = {'slot_id': slot, 'raw_answer_path': str(path.resolve()),
           'raw_answer_sha256': INPUTS[str(path.resolve())], 'sources': [],
           'coverage_use_excerpt': line_containing(body, '61 supported'),
           'panels': [], 'remaining': [], 'unsupported': [], 'pixel_targets': [], 'source_targets': [],
           'finite_pool_only': True, 'global_invisibility_overclaim': False,
           'contradictions': [], 'product_adoption': {'claims': []}, 'extra_tool_classification': []}
    scope = line_containing(body, 'These conclusions apply')
    row['finite_pool_support'] = [support(scope)]
    return row, body


def frames(body):
    pairs = re.findall(r'(SCENE|TOP|LEFT|RIGHT|FRONT|BACK)[^A-Za-z0-9]{0,8}(image-\d\d)', body)
    mapping = dict(pairs)
    if len(mapping) != 6:
        raise ValueError('six_explicit_final_frame_bindings')
    return mapping


def reason(code):
    return {'N': 'no_front_facing_candidate', 'O': 'positive_area_occlusion_all_front_views'}[code]


def add_panel(row, name, faces, code, citation, witness=None, index=None):
    panel = {'identity': identity(name, faces, index), 'status': 'covered' if code == 'C' else 'unknown',
             'views': [witness] if witness else [], 'support': citation}
    if code != 'C':
        panel.update(reason_code=reason(code), finite_pool_only=True)
    row['panels'].append(panel)
    if code != 'C':
        row['remaining'].append(panel['identity'])


def explicit_targets(row, body, slot):
    # Each coordinate below is present verbatim in this slot's own final.
    # The exact target paragraphs accompany each extracted claim.
    if slot == 'N1':
        sample_a = body[body.index('**sample_A —'):body.index('**sample_B —')]
        sample_b = body[body.index('**sample_B —'):body.index('## Original Source-Face Targets')]
    else:
        sample_a = line_containing(body, '| **sample_A**:')
        sample_b = line_containing(body, '| **sample_B**:')
    row['pixel_targets'] = [
        {'id': 'sample_A', 'identity': identity('RackRoof', [2, 3], 1),
         'center_world_m': [0, 0, 6.5], 'front_direction_world': [0, 0, 1],
         'quad_world_m': [[-7, -6, 6.5], [7, -6, 6.5], [7, 6, 6.5], [-7, 6, 6.5]],
         'view': 'TOP', 'ref': 'image-02', 'support': [support(sample_a)]},
        {'id': 'sample_B', 'identity': identity('RackBase', [10, 11], 0),
         'center_world_m': [-7, 0, -.25], 'front_direction_world': [-1, 0, 0],
         'quad_world_m': [[-7, -6, -.5], [-7, 6, -.5], [-7, 6, 0], [-7, -6, 0]],
         'view': 'LEFT', 'ref': 'image-03', 'support': [support(sample_b)]}]
    row['source_targets'] = [
        {'id': 'target_C', 'identity': identity('RackBase', [2, 3], 0), 'status': 'unknown',
         'reason_code': reason('O'), 'finite_pool_only': True,
         'support': [support(line_containing(body, '**target_C —'))]},
        {'id': 'target_D', 'identity': identity('RackBase', [0, 1], 0), 'status': 'unknown',
         'reason_code': reason('N'), 'finite_pool_only': True,
         'support': [support(line_containing(body, '**target_D —'))]}]
    row['unsupported'] = [{'status': 'unsupported', 'domain': 'outside_supported_rectangle_domain',
                           'component_count': 1, 'shape': 'nonrectangular',
                           'identity': identity('ConnectedLBracket', [0, 1, 2, 3], 11),
                           'support': [support(line_containing(body, '**ConnectedLBracket**' if slot == 'N1' else 'Object **11 / ConnectedLBracket**'))]}]


def n1():
    row, body = base('N1')
    refs = frames(body)
    witnesses = {}
    for line in body.splitlines():
        match = re.fullmatch(r'\| (\w+) \[([\d,]+)\] \| (\w+) \| ([\d,]+) \| ([\d,]+) \|', line)
        if match:
            name, faces, view, surface, boundary = match.groups()
            witnesses[name, tuple(map(int, faces.split(',')))] = (
                {'view': view, 'ref': refs[view], 'surface_pixels': int(surface.replace(',', '')),
                 'boundary_pixels': int(boundary.replace(',', ''))}, line)
    if len(witnesses) != 18:
        raise ValueError('N1_actual_witness_rows')
    headers = [[int(value) for value in token.split(',')] for token in re.findall(r'\[([\d,]+)\]', line_containing(body, '| Object |'))]
    legend = [line_containing(body, '- **' + letter + ':') for letter in ('C', 'N', 'O')]
    for line in body.splitlines():
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if len(cells) != 7 or not all(cell in {'N', 'O', 'C', '—'} for cell in cells[1:]):
            continue
        name = cells[0]
        for faces, code in zip(headers, cells[1:]):
            if code == '—':
                continue
            cited = [support(line), support(legend[{'C': 0, 'N': 1, 'O': 2}[code]])]
            witness = None
            if code == 'C':
                witness, witness_line = witnesses[name, tuple(faces)]
                cited.append(support(witness_line))
            add_panel(row, name, faces, code, cited, witness)
    explicit_targets(row, body, 'N1')
    return row


def n2():
    row, body = base('N2')
    refs = frames(body)
    headers = [[int(value) for value in token.split(',')] for token in re.findall(r'\[([\d,]+)\]', line_containing(body, '| Object index / name |'))]
    counts = {}
    for line in body.splitlines():
        matches = re.findall(r'\[([\d,]+)\] → (\d+)/(\d+)', line)
        if matches:
            name = line.split('|')[1].strip()
            for faces, surface, boundary in matches:
                counts[name, tuple(map(int, faces.split(',')))] = (int(surface), int(boundary), line)
    for line in body.splitlines():
        match = re.match(r'\| (\d+) / (\w+) \|', line)
        if not match:
            continue
        index, name = int(match[1]), match[2]
        cells = [cell.strip() for cell in line.strip('|').split('|')][1:]
        for faces, state in zip(headers, cells):
            cited, witness = [support(line)], None
            code = state if state in {'N', 'O'} else 'C'
            if code == 'C':
                surface, boundary, count_line = counts[name, tuple(faces)]
                witness = {'view': state, 'ref': refs[state], 'surface_pixels': surface, 'boundary_pixels': boundary}
                cited.append(support(count_line))
            else:
                cited.append(support(line_containing(body, '- **' + code + '** means')))
            add_panel(row, name, faces, code, cited, witness, index)
    slanted_line = line_containing(body, 'The remaining supported rectangle')
    surface, boundary, count_line = counts['SlantedIndicator', (0, 1)]
    add_panel(row, 'SlantedIndicator', [0, 1], 'C', [support(slanted_line), support(count_line)],
              {'view': 'RIGHT', 'ref': refs['RIGHT'], 'surface_pixels': surface, 'boundary_pixels': boundary}, 10)
    explicit_targets(row, body, 'N2')
    path = FORMAL / 'N2/o/tool_04/RESPONSE.json'
    response = read(path)
    tool_body = '\n'.join(b['text'] for b in response['result']['content'] if b.get('type') == 'text')
    stdout = json.loads(tool_body)['stdout']
    normal_line = line_containing(stdout, '9:6,7 TurnedUnit')
    row['sources'].append({'id': 'tool_04_result', 'kind': 'tool_result', 'path': str(path),
                           'sha256': INPUTS[str(path.resolve())]})
    row['contradictions'].append({
        'kind': 'unretracted_wrong_front_candidate_in_final',
        'final_excerpt': line_containing(body, 'TurnedUnit differs for'),
        'incorrect_subclaim': 'TurnedUnit [6,7] lists SCENE as a front-facing candidate.',
        'current_tool_fact_excerpt': normal_line,
        'current_tool_fact_source_id': 'tool_04_result',
        'current_tool_fact_escaped_excerpt': json.dumps(normal_line, ensure_ascii=False)[1:-1],
        'derivation': 'The current tool reports front unit normal (0.6,0.8,0). Its dot with the registered SCENE direction (4,-4,3) is -0.8. This is back-facing.',
        'scope': 'Inventory unknown state remains the stated claim; this extra front-candidate explanation conflicts with the current source.'})
    return row


def elements(body, name):
    token = json.dumps(name) + ': ['
    pos = body.index(token)+len(token)
    decoder = json.JSONDecoder()
    result = []
    while True:
        while body[pos].isspace() or body[pos] == ',':
            pos += 1
        if body[pos] == ']':
            return result
        start = pos
        value, pos = decoder.raw_decode(body, pos)
        result.append((value, body[start:pos]))


def n3():
    row, body = base('N3')
    path = FORMAL / 'N3/o/scratch/equipment_rack_inspection.json'
    artifact_text = text(path)
    artifact = json.loads(artifact_text)
    citation = line_containing(body, 'equipment_rack_inspection.json')
    row['sources'].append({'id': 'cited_report', 'kind': 'cited_artifact', 'path': str(path),
                           'sha256': INPUTS[str(path.resolve())], 'final_citation_excerpt': citation})
    by_surface = {}
    for value, excerpt in elements(artifact_text, 'surfaces'):
        source_identity = identity(value['object'], value['local_source_triangle_indices'], value['object_index'])
        by_surface[value['surface_id']] = source_identity
        panel = {'identity': source_identity, 'status': value['state'],
                 'views': [{'view': w['view'], 'ref': w['image_ref'], 'surface_pixels': w['visible_surface_pixels'],
                            'boundary_pixels': w['contrasting_boundary_pixels']} for w in value['complete_readable_witnesses']],
                 'support': [support(excerpt, 'cited_report')]}
        if value['state'] == 'unknown':
            panel.update(finite_pool_only=True, reason_code=reason('N' if value['reason'].startswith('No front-facing') else 'O'))
        row['panels'].append(panel)
    row['remaining'] = [by_surface[name] for name in artifact['remaining_supported_set']]
    for value, excerpt in elements(artifact_text, 'unsupported'):
        row['unsupported'].append({'identity': {'object_index': value['object_index'], 'object_name': value['object'],
                                   'source_triangle_indices': value['local_source_triangle_indices'],
                                   'global_source_triangle_indices': value['global_source_triangle_indices']},
                                   'status': value['state'], 'domain': 'outside_supported_rectangle_domain',
                                   'component_count': 1, 'shape': 'nonrectangular', 'support': [support(excerpt, 'cited_report')]})
    for value, excerpt in elements(artifact_text, 'pixel_targets'):
        row['pixel_targets'].append({'id': value['target_id'],
            'identity': identity(value['object'], value['local_source_triangle_indices'], value['object_index']),
            'center_world_m': value['world_center_m'], 'front_direction_world': value['front_normal_proportional'],
            'quad_world_m': value['world_rectangle_corners_m'], 'view': value['specified_view'],
            'ref': value['specified_view_image_ref'], 'support': [support(excerpt, 'cited_report')]})
    for value, excerpt in elements(artifact_text, 'source_targets'):
        row['source_targets'].append({'id': value['target_id'],
            'identity': identity(value['object'], value['local_source_triangle_indices'], value['object_index']),
            'status': value['state'], 'reason_code': reason('N' if value['reason'].startswith('No front-facing') else 'O'),
            'finite_pool_only': True, 'support': [support(excerpt, 'cited_report')]})
    return row


def classify(row):
    categories = {
        'N1': ['raw_source_read', 'new_native_observation', 'raw_source_read', 'native_computation', 'native_computation', 'native_computation'],
        'N2': ['raw_source_read', 'new_native_observation', 'native_computation', 'native_computation', 'cached_image_read', 'native_computation'],
        'N3': ['raw_source_read', 'new_native_observation', 'raw_source_read', 'native_computation', 'native_computation', 'native_computation', 'format_artifact']}
    requests = sorted((FORMAL / row['slot_id'] / 'o').glob('tool_*/REQUEST.json'))
    if len(requests) != len(categories[row['slot_id']]):
        raise ValueError('all_actual_N_requests_classified')
    for number, (path, category) in enumerate(zip(requests, categories[row['slot_id']]), 1):
        body = text(path)
        source = 'request_' + str(number).zfill(2)
        row['sources'].append({'id': source, 'kind': 'tool_request', 'path': str(path), 'sha256': INPUTS[str(path.resolve())]})
        row['extra_tool_classification'].append({'attempt': number, 'category': category, 'support': [support(body, source)]})


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    rows = [n1(), n2(), n3()]
    for row in rows:
        classify(row)
        if len(row['panels']) != 61 or len(row['remaining']) != 43:
            raise ValueError('actual_answer_inventory_rows')
    result = {'schema': 'occluded-scene-transfer-normalized-v1', 'slots': rows,
              'scope': 'Three N source-only normalizations. Root combines six slots before formal scoring.'}
    save(HERE / 'admin/NORMALIZED_N.json', result)
    review = {'schema': 'occluded-transfer-N-normalization-review-v1',
              'roles': 'Scoring implementation author normalizes actual N source claims. Root independent entailment review remains required.',
              'slots': [{'slot_id': r['slot_id'], 'panels': len(r['panels']), 'covered_claims': sum(p['status']=='covered' for p in r['panels']),
                         'unknown_claims': len(r['remaining']), 'pixel_targets': len(r['pixel_targets']), 'source_targets': len(r['source_targets']),
                         'contradictions': r['contradictions'], 'tool_classifications': r['extra_tool_classification']} for r in rows],
              'N2_unretracted_conflict_retained': True,
              'extra_claims_for_independent_review': [
                  'N1 final gives specific sufficient blockers for every O face with five exceptions, and gives a six-corner unsupported boundary.',
                  'N2 final gives per-face candidate sets, approximate projected occluded areas for target_C, and a six-corner +Z unsupported boundary.',
                  'N3 cited report includes per-view source-face occluders and multiple witness rows for each covered surface.'],
              'missing_or_truth_filled_claims': [], 'administrator_truth_read': False,
              'usage_or_cost_rank_read': False, 'content_scoring_executed': False,
              'inputs_sha256': dict(sorted(INPUTS.items())),
              'normalized_N_sha256': hashlib.sha256((HERE / 'admin/NORMALIZED_N.json').read_bytes()).hexdigest()}
    save(HERE / 'admin/NORMALIZATION_N_REVIEW.json', review)
    print(json.dumps({'slots': len(rows), 'panel_claims': sum(len(r['panels']) for r in rows),
                      'contradictions': {r['slot_id']:len(r['contradictions']) for r in rows}}))


if __name__ == '__main__':
    main()
