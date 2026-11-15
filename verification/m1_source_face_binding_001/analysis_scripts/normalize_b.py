"""Transcribe the three actual B answers and actual range-use dataflow only.

This post-run script reads finals and current request/response artifacts. It
never reads truth, pixel truth, timing, usage, cost or ranking records.
"""

import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parents[1]
FORMAL = Path('D:/he_source_face_001/formal')
INPUTS = {}


def source_bytes(path):
    value = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(value).hexdigest()
    return value


def source_text(path):
    return source_bytes(path).decode('utf-8-sig')


def source_json(path):
    return json.loads(source_bytes(path))


def support(source_id, excerpt):
    return {'source_id': source_id, 'excerpt': excerpt}


def table_records(value):
    return [dict(zip(value['columns'], row)) for row in value['rows']]


def identity(index, name, faces):
    return dict(object_index=index, object_name=name, source_triangle_indices=faces)


def frame_references(answer):
    result = {}
    for line in answer.splitlines():
        reference = re.search(r'`(active-host-image:[0-9a-f]+|image-\d+)`', line)
        if reference:
            views = [view for view in ('SCENE', 'LEFT', 'BACK', 'TOP') if view in line]
            if len(views) == 1:
                result[views[0]] = reference[1]
    return result


def parse_inventory(answer, references):
    lines = answer.splitlines()
    header = next(line for line in lines if line.startswith('| Object index / name |'))
    header_faces = [[int(a), int(b)] for a, b in re.findall(r'\[(\d+),(\d+)\]', header)]
    rows = []
    names = {}
    short = {'S': 'SCENE', 'L': 'LEFT', 'B': 'BACK'}
    if header_faces:
        legend_start = answer.index('- **S / L / B')
        legend = answer[legend_start:answer.index(header)].strip()
    else:
        legend = next(line for line in lines if line.startswith('Each bracketed pair'))

    for line in lines:
        if not line.startswith('| '):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        obj = re.fullmatch(r'(\d+)\s+`?([A-Za-z]+)`?', cells[0])
        if obj is None:
            continue
        index, name = int(obj[1]), obj[2]
        names[index] = name
        common = [support('final', line), support('final', header), support('final', legend)]
        if header_faces:
            assert len(cells) == len(header_faces) + 1
            for faces, state in zip(header_faces, cells[1:]):
                if state == '—':
                    continue
                panel = dict(identity=identity(index, name, faces), finite_pool_only=True, support=common)
                if state in short:
                    view = short[state]
                    panel.update(status='covered', views=[dict(view=view, ref=references[view])])
                else:
                    assert state in ('O', 'N')
                    panel.update(status='unknown', reason_code='no_front_facing_candidate'
                                 if state == 'N' else 'positive_area_occlusion_all_front_views')
                rows.append(panel)
        else:
            assert len(cells) == 4
            for column, text in enumerate(cells[1:]):
                if text == '—':
                    continue
                found = list(re.finditer(r'\[(\d+),(\d+)\](?:\s+@(SCENE|LEFT|BACK|TOP|RIGHT|FRONT))?', text))
                assert found
                for match in found:
                    panel = dict(identity=identity(index, name, [int(match[1]), int(match[2])]),
                                 finite_pool_only=True, support=common)
                    if column == 0:
                        view = match[3]
                        assert view is not None
                        panel.update(status='covered', views=[dict(view=view, ref=references[view])])
                    else:
                        panel.update(status='unknown', reason_code='positive_area_occlusion_all_front_views'
                                     if column == 1 else 'no_front_facing_candidate')
                    rows.append(panel)

    # Preserve every explicitly stated count in the B1/B3 witness tables.
    lookup = {(row['identity']['object_name'], tuple(row['identity']['source_triangle_indices'])): row for row in rows}
    pattern = r'\| ([A-Za-z]+)(?: / | `)\[(\d+),(\d+)\]`? \| ([SLB]) \| ([\d,]+) \| ([\d,]+) \|'
    for line in lines:
        match = re.fullmatch(pattern, line)
        if match is None:
            continue
        panel = lookup[match[1], (int(match[2]), int(match[3]))]
        view = short[match[4]]
        witness = next(item for item in panel['views'] if item['view'] == view)
        witness.update(surface_pixels=int(match[5].replace(',', '')),
                       boundary_pixels=int(match[6].replace(',', '')))
        panel['support'].append(support('final', line))
    return rows, names


def tuple_values(text):
    result = []
    for value in text.split(','):
        value = value.strip().replace('−', '-')
        number = float(value)
        result.append(int(number) if number.is_integer() else number)
    assert len(result) == 3
    return result


def pixel_targets(answer, names, references):
    starts = [match for match in re.finditer(r'(?m)^(?:### )?\*\*(sample_[AB])\b.*|^### (sample_[AB])\b.*', answer)]
    assert len(starts) == 2
    result = []
    for position, start in enumerate(starts):
        name = start[1] or start[2]
        end = starts[position + 1].start() if position + 1 < len(starts) else len(answer)
        # Source targets start a new section after the second sample.
        section_end = re.search(r'\n## (?:Original source-face targets|Original Source-Face Targets)', answer[start.start():end])
        if section_end:
            end = start.start() + section_end.start()
        block = answer[start.start():end].strip()
        header = block.splitlines()[0]
        view = next(view for view in ('TOP', 'LEFT') if view in header)
        object_match = re.search(r'object\s+[*`\s]*(\d+)', block, re.IGNORECASE)
        face_match = re.search(r'\[(\d+),(\d+)\]', block)
        assert object_match and face_match
        obj = int(object_match[1])
        center_line = next(line for line in block.splitlines() if 'world center' in line.lower())
        normal_line = next(line for line in block.splitlines() if 'front orientation' in line.lower())
        corners_line = next(line for line in block.splitlines() if 'rectangle corners' in line.lower())
        center = tuple_values(re.search(r'\(([^()]+)\)', center_line)[1])
        orientation = normal_line[normal_line.lower().index('front orientation') + len('front orientation'):]
        normal = tuple_values(re.search(r'\(([^()]+)\)', orientation)[1])
        corners = [tuple_values(text) for text in re.findall(r'\(([^()]+)\)', corners_line)]
        assert len(corners) == 4
        result.append(dict(id=name, identity=identity(obj, names[obj], [int(face_match[1]), int(face_match[2])]),
            center_world_m=center, front_direction_world=normal, quad_world_m=corners,
            view=view, ref=references[view], support=[support('final', block)]))
    return result


def add_source(row, source_id, kind, path):
    row['sources'].append(dict(id=source_id, kind=kind, path=str(path), sha256=hashlib.sha256(source_bytes(path)).hexdigest()))


def normalize(slot):
    owner = FORMAL / slot / 'o'
    answer_path = FORMAL / slot / 'c/PUBLIC_FINAL.txt'
    answer = source_text(answer_path)
    references = frame_references(answer)
    panels, names = parse_inventory(answer, references)
    pixels = pixel_targets(answer, names, references)
    coverage = next(line for line in answer.splitlines() if '61' in line and '18' in line and '43' in line)
    finite = next(line for line in answer.splitlines() if 'finite' in line.lower() and ('only' in line.lower() or 'registered finite pool' in line.lower()))
    row = dict(slot_id=slot, raw_answer_path=str(answer_path), raw_answer_sha256=hashlib.sha256(source_bytes(answer_path)).hexdigest(),
        sources=[], coverage_use_excerpt=coverage, panels=panels,
        remaining=[panel['identity'] for panel in panels if panel['status'] == 'unknown'],
        pixel_targets=pixels, source_targets=[], finite_pool_only=True, global_invisibility_overclaim=False,
        finite_pool_support=[support('final', finite)], contradictions=[], extra_tool_classification=[])
    unsupported_line = next(line for line in answer.splitlines() if line.startswith('**Unsupported'))
    row['unsupported'] = [dict(identity=identity(11, 'ConnectedLBracket', [0, 1, 2, 3]),
        status='unsupported', domain='outside_supported_rectangle_domain', component_count=1,
        shape='nonrectangular', support=[support('final', unsupported_line)])]
    for name in ('target_C', 'target_D'):
        line = next(line for line in answer.splitlines() if line.startswith('- **' + name) or line.startswith('| **' + name))
        obj = int(re.search(r'object\s+[*`\s]*(\d+)', line, re.IGNORECASE)[1])
        match = re.search(r'\[(\d+),(\d+)\]', line)
        faces = [int(match[1]), int(match[2])]
        panel = next(panel for panel in panels if panel['identity']['object_index'] == obj
                     and panel['identity']['source_triangle_indices'] == faces)
        row['source_targets'].append(dict(id=name, identity=identity(obj, names[obj], faces),
            status=panel['status'], reason_code=panel['reason_code'], finite_pool_only=True,
            support=[support('final', line)]))

    requests = sorted(owner.glob('tool_*/REQUEST.json'))
    process_support = []
    request_bodies = {}
    for path in requests:
        attempt = int(path.parent.name.split('_')[1])
        source_id = 'request_' + str(attempt)
        body = source_text(path)
        request_bodies[attempt] = body
        add_source(row, source_id, 'tool_request', path)
        process_support.append(support(source_id, body))
        if attempt == 1:
            continue
        # Categories describe the dominant observed operation, preserving all
        # code for mixed calls. The whole-witness recomputation is separate.
        if slot == 'B1':
            category = {2: 'raw_source_read', 3: 'new_native_observation', 4: 'native_computation'}[attempt]
        else:
            category = {2: 'raw_source_read', 3: 'new_native_observation',
                        4: 'existing_buffer_lookup', 5: 'native_computation'}[attempt]
        row['extra_tool_classification'].append(dict(attempt=attempt, category=category,
                                                    support=[support(source_id, body)]))

    row['process_diagnostics'] = {}
    for key, observed, reason in (
        ('geometry_reverse_lookup', False,
         'Every actual request reviewed. Object names and triangle counts are read. Region associations use the supplied source ranges. No vertex/normal/coplarity matching loop reconstructs the region map. B1 additionally prints base vertices without using them for reverse matching.'),
        ('full_witness_pixel_recomputation', True,
         'The final computation reads complete RGB/raw-triangle buffers, builds merged masks/labels and recomputes all covered witnesses surface and contrasting-boundary counts.')):
        row['process_diagnostics'][key] = dict(observed=observed, review_complete=True,
            reviewed_tool_attempts=list(range(1, len(requests) + 1)), support=process_support, reason=reason)

    product_path = owner / 'tool_01/RESPONSE.json'
    product_text = source_json(product_path)['result']['content'][0]['text']
    product = json.loads(product_text)
    product_rows = product['regions']['rows']
    regions = table_records(product['regions'])
    sample = next(pixel for pixel in pixels if pixel['id'] == 'sample_A')
    chosen = next(index for index, region in enumerate(regions)
                  if region['object_index'] == sample['identity']['object_index']
                  and region['source_triangle_index_ranges'] == [sample['identity']['source_triangle_indices']])
    public_row = product_rows[chosen]
    encoded_row = next(value for value in (json.dumps(public_row, ensure_ascii=False, separators=(',', ':')),
                                          json.dumps(public_row, ensure_ascii=False)) if value in product_text)
    add_source(row, 'product', 'tool_result', product_path)
    product_support = [support('product', '"source_triangle_index_ranges"'), support('product', encoded_row)]
    operation = 5 if slot == 'B2' else 4
    result_path = owner / ('tool_' + str(operation).zfill(2)) / 'RESPONSE.json'
    response = source_json(result_path)
    assert response['result']['isError'] is False
    result_text = response['result']['content'][0]['text']
    executed = json.loads(result_text)
    assert executed['error'] is None
    sample_line = next(line for line in executed['stdout'].splitlines()
                       if line.startswith('sample_A') or line.startswith('SAMPLE TOP'))
    escaped_line = json.dumps(sample_line, ensure_ascii=False)[1:-1]
    assert escaped_line in result_text
    add_source(row, 'operation_result', 'tool_result', result_path)
    evidence_identity = dict(sample['identity'], roi_id=regions[chosen]['roi_id'])
    row['product_adoption'] = dict(claims=[dict(identity=evidence_identity,
        product_support=product_support, final_use_excerpt=sample['support'][0]['excerpt'])])
    row['source_binding_use'] = dict(claims=[dict(identity=evidence_identity,
        operation='pixel_source_face_to_region', binding_scoped=True, dataflow_confirmed_by_review=True,
        product_support=product_support,
        operation_support=[support('request_' + str(operation), request_bodies[operation]),
                           support('operation_result', escaped_line)],
        task_use_support=sample['support'])])
    return row


def main():
    rows = [normalize(slot) for slot in ('B1', 'B2', 'B3')]
    source_count = 0
    fragment_count = 0
    for row in rows:
        bodies = {'final': source_text(Path(row['raw_answer_path']))}
        for source in row['sources']:
            raw = source_bytes(Path(source['path']))
            assert hashlib.sha256(raw).hexdigest() == source['sha256']
            if source['kind'] == 'tool_result':
                body = '\n'.join(block['text'] for block in json.loads(raw)['result']['content'] if block.get('type') == 'text')
            else:
                body = raw.decode('utf-8-sig')
            assert source['id'] not in bodies
            bodies[source['id']] = body
            source_count += 1

        def verify(value):
            nonlocal fragment_count
            if isinstance(value, dict):
                if 'source_id' in value and 'excerpt' in value:
                    assert value['excerpt'] and value['excerpt'] in bodies[value['source_id']]
                    fragment_count += 1
                for child in value.values():
                    verify(child)
            elif isinstance(value, list):
                for child in value:
                    verify(child)

        verify(row)
        assert row['coverage_use_excerpt'] in bodies['final']
        assert len(row['panels']) == 61 and len(row['remaining']) == 43
        assert len(row['pixel_targets']) == len(row['source_targets']) == 2
    after = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in INPUTS}
    assert after == INPUTS
    value = dict(schema='source-face-binding-normalized-B-part-v1', slots=rows,
                 source_only=True, truth_pixel_truth_cost_usage_read=False)
    output = HERE / 'admin/NORMALIZED_B_R1.json'
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    review = dict(schema='source-face-binding-B-transcription-review-v1',
        normalization_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        source_files_sha256=INPUTS, source_records=source_count, exact_source_fragments=fragment_count,
        slots=[dict(slot_id=row['slot_id'], panels=len(row['panels']), remaining=len(row['remaining']),
                    actual_tool_attempts=row['process_diagnostics']['geometry_reverse_lookup']['reviewed_tool_attempts'],
                    source_binding_operation='Actual range lookup code and executed point result followed by final sample_A.',
                    geometry_reverse_lookup=False, full_witness_pixel_recomputation=True) for row in rows],
        source_files_unchanged=True, new_model_observe_raster_calls=0, full_content_scoring_calls=0,
        author_association='Transcriber authored scorer/cost adapters. Root independent semantic and dataflow review remains required.',
        scope='Only actual B finals and current request/response artifacts. Complete task quality has not been graded here.')
    review['normalizer_source_path'] = str(Path(__file__).resolve())
    review['normalizer_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    review['source_read_class'] = 'Actual finals and current tool request/response files only.'
    with (HERE / 'admin/NORMALIZATION_B_REVIEW_R1.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(review, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(slots=[row['slot_id'] for row in rows], sources=source_count,
                          fragments=fragment_count, source_binding_use=3, geometry_reverse_lookup=0,
                          full_witness_pixel_recomputation=3)))


if __name__ == '__main__':
    main()
