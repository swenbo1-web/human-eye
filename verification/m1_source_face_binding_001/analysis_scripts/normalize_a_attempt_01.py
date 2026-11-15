"""Transcribe the three actual A answers using current sources only."""

import hashlib
import json
from pathlib import Path
import re
import time


HERE = Path(__file__).resolve().parents[1]
RUNTIME = Path('D:/he_source_face_001/formal')
VIEWS = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')


def raw(path):
    return path.read_bytes().decode('utf-8-sig')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def quote(source, excerpt):
    return [{'source_id': source, 'excerpt': excerpt}]


def numeric(text):
    value = float(text.strip().replace('−', '-'))
    return int(value) if value.is_integer() else value


def vector(text):
    match = re.search(r'\(([^()]+)\)', text)
    values = [numeric(value) for value in match[1].split(',')]
    if len(values) != 3:
        raise ValueError('source_vector_requires_three_explicit_coordinates')
    return values


def source_pairs(text):
    return [[int(a), int(b)] for a, b in re.findall(r'\[(\d+),\s*(\d+)\]', text)]


def identity(index, name, faces):
    return {'object_index': index, 'object_name': name, 'source_triangle_indices': faces}


def add_panel(row, panel):
    row['panels'].append(panel)
    if panel['status'] == 'unknown':
        row['remaining'].append(panel['identity'])


def references(answer):
    result = {}
    evidence = {}
    for line in answer.splitlines():
        found = re.search(r'`((?:active-host-image:|image-)[^`]+)`', line)
        if found is None:
            continue
        for view in VIEWS:
            if line.startswith('| ' + view + ' |') or line.startswith('- **' + view):
                result[view] = found[1]
                evidence[view] = line
    return result, evidence


def add_source(row, name, kind, path):
    row['sources'].append({'id': name, 'kind': kind, 'path': str(path), 'sha256': sha(path)})


def base(slot):
    folder = RUNTIME / slot
    answer_path = folder / 'c/PUBLIC_FINAL.txt'
    answer = raw(answer_path)
    row = {'slot_id': slot, 'raw_answer_path': str(answer_path), 'raw_answer_sha256': sha(answer_path),
           'sources': [], 'panels': [], 'remaining': [], 'unsupported': [], 'pixel_targets': [],
           'source_targets': [], 'finite_pool_only': True, 'global_invisibility_overclaim': False,
           'contradictions': [], 'extra_tool_classification': [], 'product_adoption': {'claims': []},
           'source_binding_use': {'claims': []}, 'process_diagnostics': {}}
    row['coverage_use_excerpt'] = next(line for line in answer.splitlines() if '61' in line and '18' in line)
    finite = next(line for line in answer.splitlines() if 'only' in line.lower() and ('pool' in line.lower() or 'camera' in line.lower()))
    row['finite_pool_support'] = quote('final', finite)
    requests = sorted((folder / 'o').glob('tool_*/REQUEST.json'))
    actual = read(folder / 'o/TOOLS.json')
    attempts = [int(path.parent.name.split('_')[1]) for path in requests]
    if attempts != list(range(1, actual['calls'] + 1)):
        raise ValueError('all_actual_tool_requests_required')
    for path in requests:
        number = int(path.parent.name.split('_')[1])
        add_source(row, 'request_' + str(number), 'tool_request', path)
        request = read(path)['params']
        if number == 1:
            if request['name'] != 'active_observation':
                raise ValueError('actual_product_first_entry')
            continue
        if request['name'] == 'render_views' or 'render_views(' in request['arguments'].get('code', ''):
            category = 'new_native_observation'
        elif number == (4 if slot == 'A2' else 5):
            category = 'native_computation'
        elif slot == 'A3' and number == 6:
            category = 'public_json_query'
        else:
            category = 'raw_source_read'
        row['extra_tool_classification'].append({'attempt': number, 'category': category,
                                                 'support': quote('request_' + str(number), raw(path))})
    product_path = folder / 'o/tool_01/RESPONSE.json'
    product_text = read(product_path)['result']['content'][0]['text']
    public = json.loads(product_text)
    if public['schema'] != 'active-observation-brief-v4' or 'source_triangle_index_ranges' in public['regions']['columns']:
        raise ValueError('old_A_default_capability_requires_v4_without_new_range_field')
    add_source(row, 'active', 'tool_result', product_path)
    public_values = public['regions']['rows'][0]
    declared = dict(zip(public['regions']['columns'], public_values))
    product_excerpt = next(candidate for candidate in (
        json.dumps(public_values, ensure_ascii=False, separators=(',', ':')),
        json.dumps(public_values, ensure_ascii=False)) if candidate in product_text)
    object_names = {obj[0]: obj[3] for obj in public['objects']['rows']}
    final_use = next(line for line in answer.splitlines() if line.startswith('| ') and object_names[declared['object_index']] in line)
    row['product_adoption']['claims'].append({'identity': {'roi_id': declared['roi_id']},
        'product_support': quote('active', product_excerpt), 'final_use_excerpt': final_use})
    reverse_attempt = 4 if slot == 'A2' else 5
    request_path = folder / 'o' / ('tool_' + str(reverse_attempt).zfill(2)) / 'REQUEST.json'
    response_path = request_path.with_name('RESPONSE.json')
    response = read(response_path)['result']
    text = response['content'][0]['text']
    executed = json.loads(text)
    if response['isError'] or executed['error'] is not None:
        raise ValueError('diagnostic_algorithm_did_not_complete')
    add_source(row, 'algorithm_result', 'tool_result', response_path)
    diagnostic_support = quote('request_' + str(reverse_attempt), raw(request_path)) + quote('algorithm_result', text)
    reverse_reasons = {
        'A1': 'Tool5 computes source-pair vertices, centers and cross-product normals, then matches current regions with np.allclose.',
        'A2': 'Tool4 scans source triangles for each region using a plane-distance tolerance and positive face-normal dot product.',
        'A3': 'Tool5 scans source triangles against current region centers and normals with a plane-distance tolerance.',
    }
    row['process_diagnostics']['geometry_reverse_lookup'] = {
        'observed': True, 'review_complete': True, 'reviewed_tool_attempts': attempts,
        'support': diagnostic_support, 'reason': reverse_reasons[slot]}
    row['process_diagnostics']['full_witness_pixel_recomputation'] = {
        'observed': True, 'review_complete': True, 'reviewed_tool_attempts': attempts,
        'support': diagnostic_support,
        'reason': 'The completed algorithm merges raw source-triangle pixels by surface, recomputes RGB-contrast boundary masks, and computes all covered-witness pixel counts. This is separate from geometry visibility solving.'}
    return row, answer, attempts


def matrix_inventory(row, answer, refs):
    legend_start = answer.index('- **S / L / B:**')
    legend_end = answer.index('| Object index / name |')
    legend = answer[legend_start:legend_end].strip()
    names = {}
    for line in answer.splitlines():
        found = re.match(r'\| (\d+) ([A-Za-z]+) \| (.+) \|$', line)
        if found is None:
            continue
        index, name = int(found[1]), found[2]
        names[index] = name
        for position, cell in enumerate(found[3].split(' | ')):
            if cell == '—':
                continue
            panel = {'identity': identity(index, name, [position*2, position*2+1]), 'finite_pool_only': True,
                     'support': quote('final', line) + quote('final', legend)}
            if cell in ('S', 'L', 'B'):
                view = {'S': 'SCENE', 'L': 'LEFT', 'B': 'BACK'}[cell]
                panel.update(status='covered', views=[{'view': view, 'ref': refs[view]}])
            elif cell in ('N', 'O'):
                panel.update(status='unknown', reason_code='no_front_facing_candidate' if cell == 'N' else 'positive_area_occlusion_all_front_views')
            else:
                raise ValueError('unrecognized_explicit_matrix_state')
            add_panel(row, panel)
    return names


def set_inventory(row, answer, refs):
    names = {}
    heading = next(line for line in answer.splitlines() if line.startswith('| Object (index) |'))
    for line in answer.splitlines():
        found = re.match(r'\| ([A-Za-z]+) \((\d+)\) \| (.+) \|$', line)
        if found is None:
            continue
        name, index = found[1], int(found[2])
        names[index] = name
        cells = found[3].split(' | ')
        if len(cells) != 3:
            raise ValueError('complete_set_table_columns')
        for column, cell in enumerate(cells):
            if cell == '—':
                continue
            for piece in cell.split('; '):
                entry = re.fullmatch(r'(\d+)[–-](\d+)(?:\s+(SCENE|TOP|LEFT|RIGHT|FRONT|BACK))?', piece)
                if entry is None:
                    raise ValueError('explicit_surface_pair_and_view')
                panel = {'identity': identity(index, name, [int(entry[1]), int(entry[2])]), 'finite_pool_only': True,
                         'support': quote('final', line) + quote('final', heading)}
                if column == 0:
                    if entry[3] is None:
                        raise ValueError('covered_witness_not_stated')
                    panel.update(status='covered', views=[{'view': entry[3], 'ref': refs[entry[3]]}])
                else:
                    panel.update(status='unknown', reason_code='positive_area_occlusion_all_front_views' if column == 1 else 'no_front_facing_candidate')
                add_panel(row, panel)
    return names


def split_inventory(row, answer, refs):
    names = {}
    covered_heading = next(line for line in answer.splitlines() if line.startswith('| Object index / name | Local triangles |'))
    remaining_heading = next(line for line in answer.splitlines() if line.startswith('| Object index / name | No front-facing candidate |'))
    for line in answer.splitlines():
        found = re.match(r'\| (\d+) / ([A-Za-z]+) \| (.+) \|$', line)
        if found is None:
            continue
        index, name = int(found[1]), found[2]
        names[index] = name
        cells = found[3].split(' | ')
        if len(cells) == 4:
            faces = source_pairs(cells[0])[0]
            view = cells[1]
            if view not in VIEWS:
                raise ValueError('registered_witness_view')
            panel = {'identity': identity(index, name, faces), 'finite_pool_only': True, 'status': 'covered',
                     'views': [{'view': view, 'ref': refs[view], 'surface_pixels': int(cells[2].replace(',', '')),
                                'boundary_pixels': int(cells[3].replace(',', ''))}],
                     'support': quote('final', line) + quote('final', covered_heading)}
            add_panel(row, panel)
        elif len(cells) == 2:
            for column, cell in enumerate(cells):
                if cell == '—':
                    continue
                pairs = source_pairs(cell)
                if not pairs:
                    raise ValueError('remaining_identity_not_explicit')
                for faces in pairs:
                    add_panel(row, {'identity': identity(index, name, faces), 'status': 'unknown', 'finite_pool_only': True,
                        'reason_code': 'no_front_facing_candidate' if column == 0 else 'positive_area_occlusion_all_front_views',
                        'support': quote('final', line) + quote('final', remaining_heading)})
        else:
            raise ValueError('unrecognized_inventory_table_shape')
    return names


def object_index(text):
    for pattern in (r'object\s+\**(\d+)', r'\((\d+)\)', r'\b(\d+) / RackBase'):
        match = re.search(pattern, text, re.IGNORECASE)
        if match is not None:
            return int(match[1])
    raise ValueError('explicit_object_index_missing')


def targets(row, answer, names, refs, ref_evidence):
    start_a, start_b = answer.index('**sample_A'), answer.index('**sample_B')
    sections = {'sample_A': answer[start_a:start_b].strip(), 'sample_B': answer[start_b:answer.index('target_C', start_b)].strip()}
    for target_id, section in sections.items():
        lines = section.splitlines()
        source_line = next(line for line in lines if 'Source:' in line or 'Surface:' in line or ('hits object' in line))
        index = object_index(source_line)
        if names[index] not in source_line:
            raise ValueError('pixel_object_alias_conflict')
        faces = source_pairs(source_line)[0]
        center_line = next(line for line in lines if 'Center:' in line)
        center = vector(center_line.split(';')[0])
        normal = vector(center_line[center_line.index('front orientation:'):])
        view = next(view for view in VIEWS if view in lines[0])
        item = {'id': target_id, 'identity': identity(index, names[index], faces),
                'center_world_m': center, 'front_direction_world': normal,
                'view': view, 'ref': refs[view], 'support': quote('final', section) + quote('final', ref_evidence[view])}
        corner_line = next((line for line in lines if 'Rectangle corners:' in line), None)
        if corner_line is not None:
            corners = [vector('(' + content + ')') for content in re.findall(r'\(([^()]+)\)', corner_line)]
            if len(corners) != 4:
                raise ValueError('four_explicit_rectangle_corners')
            item['quad_world_m'] = corners
        else:
            rectangle = next(line for line in lines if 'Rectangle:' in line)
            limits = []
            for axis in ('x', 'y', 'z'):
                part = re.search(axis + r'\s*(?:=|∈)\s*(?:\[([^\]]+)\]|([+-]?\d+(?:\.\d+)?))', rectangle)
                if part is None:
                    raise ValueError('explicit_equivalent_extent_missing_axis')
                limits.append([numeric(v) for v in part[1].split(',')] if part[1] is not None else [numeric(part[2])]*2)
            item['bounds_world_m'] = [[limits[k][end] for k in range(3)] for end in (0, 1)]
        row['pixel_targets'].append(item)
    for target_id in ('target_C', 'target_D'):
        line = next(line for line in answer.splitlines() if target_id in line)
        index = object_index(line)
        if names[index] not in line or 'unknown' not in line.lower():
            raise ValueError('source_target_identity_or_state_missing')
        faces = source_pairs(line)[0]
        lower = line.lower()
        if 'positive-area occlusion' in lower:
            reason = 'positive_area_occlusion_all_front_views'
        elif 'no front-facing candidate' in lower:
            reason = 'no_front_facing_candidate'
        else:
            raise ValueError('source_target_reason_not_explicit')
        row['source_targets'].append({'id': target_id, 'identity': identity(index, names[index], faces),
            'status': 'unknown', 'reason_code': reason, 'finite_pool_only': True, 'support': quote('final', line)})
    unsupported = next(line for line in answer.splitlines() if 'ConnectedLBracket' in line)
    if '[0,1,2,3]' not in unsupported or 'L-shaped' not in unsupported:
        raise ValueError('unsupported_component_source_or_shape_missing')
    row['unsupported'] = [{'identity': {'object_index': 11, 'object_name': 'ConnectedLBracket', 'source_triangle_indices': [0,1,2,3]},
        'status': 'unsupported', 'domain': 'outside_supported_rectangle_domain', 'shape': 'nonrectangular',
        'component_count': 1, 'support': quote('final', unsupported)}]


def validate_sources(row):
    answer_path = Path(row['raw_answer_path'])
    sources = {'final': raw(answer_path)}
    for source in row['sources']:
        path = Path(source['path'])
        if source['sha256'] != sha(path):
            raise ValueError('source_bytes_changed')
        if source['kind'] == 'tool_result':
            body = '\n'.join(block['text'] for block in read(path)['result']['content'] if block.get('type') == 'text')
        else:
            body = raw(path)
        sources[source['id']] = body
    count = 0
    def walk(value):
        nonlocal count
        if type(value) is dict:
            if 'source_id' in value and 'excerpt' in value:
                if not value['excerpt'] or value['excerpt'] not in sources[value['source_id']]:
                    raise ValueError('exact_source_excerpt_not_found')
                count += 1
            for child in value.values():
                walk(child)
        elif type(value) is list:
            for child in value:
                walk(child)
    walk(row)
    if row['coverage_use_excerpt'] not in sources['final']:
        raise ValueError('final_coverage_excerpt_not_found')
    return count


def main():
    started = time.perf_counter_ns()
    rows = []
    summaries = []
    for slot in ('A1', 'A2', 'A3'):
        row, answer, attempts = base(slot)
        refs, evidence = references(answer)
        if slot == 'A1':
            names = matrix_inventory(row, answer, refs)
        elif slot == 'A2':
            names = set_inventory(row, answer, refs)
        else:
            names = split_inventory(row, answer, refs)
        targets(row, answer, names, refs, evidence)
        if len(row['panels']) != 61 or len(row['remaining']) != 43:
            raise ValueError('source_inventory_transcription_incomplete')
        fragments = validate_sources(row)
        summaries.append({'slot': slot, 'panels': len(row['panels']), 'covered': sum(p['status']=='covered' for p in row['panels']),
            'remaining': len(row['remaining']), 'pixel_targets': len(row['pixel_targets']), 'source_targets': len(row['source_targets']),
            'reviewed_tool_attempts': attempts, 'exact_fragments_checked': fragments,
            'new_default_source_binding_received': False, 'new_default_binding_claims': 0,
            'geometry_reverse_lookup_observed': True, 'full_witness_pixel_recomputation_observed': True,
            'existing_buffer_source_mapping_consumed': False,
            'existing_mapping_explanation': 'Buffer names or keys are printed, but the actual triangle-to-region relation is built from source geometry center/normal matching. Raw triangle_ids are used after that custom reverse lookup.'})
        rows.append(row)
    output = HERE / 'admin/NORMALIZED_A.json'
    value = {'schema': 'source-face-binding-normalized-A-part-v1', 'slots': rows,
             'source_only_transcription': True, 'truth_or_cost_or_usage_read': False}
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    review = {'schema': 'source-face-binding-A-normalization-review-v1', 'passed': True, 'slots': summaries,
        'normalized_sha256': sha(output), 'script_sha256': sha(Path(__file__)),
        'source_files_sha256': {source['path']: source['sha256'] for row in rows for source in row['sources']},
        'finals_sha256': {row['raw_answer_path']: row['raw_answer_sha256'] for row in rows},
        'source_extent_note': 'A1 sample ranges are normalized as explicit bounding extents. A2/A3 use their explicitly stated four corners.',
        'quality_correctness_unscored': True, 'independent_entailment_review_required': True,
        'new_content_grading_calls': 0, 'new_observe_raster_model_calls': 0,
        'cost_usage_and_ranking_consulted': False,
        'association': 'Source transcription by directed-acceptance author, separate from root scorer and product implementation.',
        'started_ns': started, 'before_publication_ns': time.perf_counter_ns()}
    with (HERE / 'admin/NORMALIZATION_A_REVIEW.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(review, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'slots': [r['slot_id'] for r in rows], 'exact_fragments': sum(r['exact_fragments_checked'] for r in summaries),
                      'normalized_sha256': sha(output)}))


if __name__ == '__main__':
    main()
