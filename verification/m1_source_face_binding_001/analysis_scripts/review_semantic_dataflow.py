"""Read-only, source-quoted semantic and source-binding dataflow review."""

import argparse
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parents[1]
RUNTIME = Path('D:/he_source_face_001/formal')
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
INPUTS = {}
CHECKS = []


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read(path):
    return json.loads(raw(path))


def check(name, passed, detail=None):
    CHECKS.append(dict(check=name, passed=bool(passed), detail=detail))


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean(value):
    return value.replace('`', '').replace('*', '')


def parse_inventory(slot, text):
    entries = []
    short = dict(S='SCENE', L='LEFT', B='BACK')
    for line in text.splitlines():
        if not line.startswith('|'):
            continue
        cells = [clean(value.strip()) for value in line.strip('|').split('|')]
        if slot in ('A1', 'B1', 'B3'):
            match = re.fullmatch(r'(\d+)\s+([A-Za-z]+)', cells[0])
            if not match:
                continue
            oi, name = int(match[1]), match[2]
            for index, cell in enumerate(cells[1:]):
                if cell == '—':
                    continue
                entries.append(dict(object_index=oi, object_name=name, local_faces=[index*2, index*2+1],
                    state='covered' if cell in short else 'unknown',
                    view=short.get(cell), reason=None if cell in short else
                    'no_front_facing_candidate' if cell == 'N' else 'positive_area_occlusion_all_front_views',
                    excerpt=line))
        elif slot == 'B2':
            match = re.fullmatch(r'(\d+)\s+([A-Za-z]+)', cells[0])
            if not match:
                continue
            oi, name = int(match[1]), match[2]
            for index, cell in enumerate(cells[1:]):
                for found in re.finditer(r'\[(\d+),(\d+)\](?:\s+@([A-Z]+))?', cell):
                    entries.append(dict(object_index=oi, object_name=name, local_faces=[int(found[1]), int(found[2])],
                        state='covered' if index == 0 else 'unknown', view=found[3],
                        reason=None if index == 0 else 'positive_area_occlusion_all_front_views' if index == 1 else 'no_front_facing_candidate',
                        excerpt=line))
        elif slot == 'A2':
            match = re.fullmatch(r'([A-Za-z]+)\s+\((\d+)\)', cells[0])
            if not match:
                continue
            name, oi = match[1], int(match[2])
            for index, cell in enumerate(cells[1:]):
                for found in re.finditer(r'(\d+)[–-](\d+)(?:\s+([A-Z]+))?', cell):
                    entries.append(dict(object_index=oi, object_name=name, local_faces=[int(found[1]), int(found[2])],
                        state='covered' if index == 0 else 'unknown', view=found[3],
                        reason=None if index == 0 else 'positive_area_occlusion_all_front_views' if index == 1 else 'no_front_facing_candidate',
                        excerpt=line))
        else:
            match = re.fullmatch(r'(\d+)\s+/\s+([A-Za-z]+)', cells[0])
            if not match:
                continue
            oi, name = int(match[1]), match[2]
            if len(cells) == 5:
                faces = list(map(int, re.findall(r'\d+', cells[1])))
                entries.append(dict(object_index=oi, object_name=name, local_faces=faces,
                    state='covered', view=cells[2], reason=None, excerpt=line,
                    surface_pixels=int(cells[3].replace(',', '')), boundary_pixels=int(cells[4].replace(',', ''))))
            elif len(cells) == 3:
                for index, cell in enumerate(cells[1:]):
                    for found in re.finditer(r'\[(\d+),(\d+)\]', cell):
                        entries.append(dict(object_index=oi, object_name=name, local_faces=[int(found[1]), int(found[2])],
                            state='unknown', view=None,
                            reason='no_front_facing_candidate' if index == 0 else 'positive_area_occlusion_all_front_views', excerpt=line))
    return entries


def refs_from_final(text):
    result = {}
    for line in text.splitlines():
        values = re.findall(r'`([^`]+)`', line)
        for value in values:
            if value.startswith('active-host-image:'):
                for view in ('SCENE', 'LEFT', 'BACK'):
                    if view in line:
                        result[view] = value
            elif value == 'image-04' and 'TOP' in line:
                result['TOP'] = value
    return result


def sample_block(text, name):
    start = text.index(name)
    # Inventory prose contains neither sample label. The next sample/section
    # bounds the actual final localization paragraph.
    end = text.index('sample_B', start) if name == 'sample_A' else len(text)
    if name == 'sample_B':
        endings = [text.find(marker, start) for marker in ('## Original Source', '## Source-Face', '**Original Source')]
        available = [end for end in endings if end >= 0]
        if available:
            end = min(available)
    return text[start:end]


def tuples_in(value):
    return [tuple(Fraction(number.strip()) for number in match)
            for match in re.findall(r'\(([+−-]?\d+(?:\.\d+)?),\s*([+−-]?\d+(?:\.\d+)?),\s*([+−-]?\d+(?:\.\d+)?)\)', value.replace('−', '-'))]


def dataflow(slot, owner):
    records = []
    for path in sorted(owner.glob('tool_*/REQUEST.json')):
        value = read(path)['params']
        response = read(path.with_name('RESPONSE.json'))
        code = value['arguments'].get('code', '')
        check(slot + ':' + path.parent.name + ':actual_tool_success', response['result']['isError'] is False)
        records.append(dict(attempt=int(path.parent.name.split('_')[1]), name=value['name'],
            request_path=str(path), request_sha256=INPUTS[str(path.resolve())],
            response_path=str(path.with_name('RESPONSE.json')), response_sha256=INPUTS[str(path.with_name('RESPONSE.json').resolve())],
            code=code, response_text='\n'.join(b['text'] for b in response['result']['content'] if b.get('type') == 'text')))
    all_code = '\n'.join(record['code'] for record in records)
    reverse_attempt = {'A1': 5, 'A2': 4, 'A3': 5}.get(slot)
    range_attempt = {'B1': 4, 'B2': 5, 'B3': 4}.get(slot)
    pixel_attempt = {'A1': 5, 'A2': 4, 'A3': 5, 'B1': 4, 'B2': 5, 'B3': 5}[slot]
    by_attempt = {record['attempt']: record for record in records}
    if reverse_attempt:
        code = by_attempt[reverse_attempt]['code']
        check(slot + ':geometric_reverse_code_observed', "vertices" in code and 'np.cross' in code
              and ('allclose' in code or 'points-center' in code))
        operation_excerpt = code
    else:
        code = by_attempt[range_attempt]['code']
        check(slot + ':range_lookup_operation_observed', 'source_triangle_index_ranges' in code
              and ('triangle_ids' in code or 'face_to_region' in code))
        check(slot + ':no_geometric_reverse_in_any_call', 'np.cross' not in all_code
              and 'allclose' not in all_code and '(points-center)' not in all_code)
        check(slot + ':operation_executed_with_task_output', 'sample_A' in by_attempt[range_attempt]['response_text']
              or 'SAMPLE' in by_attempt[range_attempt]['response_text'])
        operation_excerpt = code
    pixel_code = by_attempt[pixel_attempt]['code']
    check(slot + ':full_witness_pixel_recomputation_observed', 'boundary' in pixel_code
          and "['color']" in pixel_code and ('complete_witness_pixel_index' in pixel_code or "status']=='covered'" in pixel_code))
    return dict(reviewed_tool_attempts=[record['attempt'] for record in records],
        geometry_reverse_lookup_observed=reverse_attempt is not None,
        geometry_reverse_lookup_attempt=reverse_attempt,
        current_source_ranges_received_and_used=range_attempt is not None,
        source_ranges_operation_attempt=range_attempt,
        source_ranges_operation='pixel_source_face_to_region' if slot == 'B1' else 'source_face_to_region_lookup' if slot == 'B2' else 'pixel_source_face_to_region' if slot == 'B3' else None,
        operation_excerpt=operation_excerpt,
        full_witness_pixel_recomputation_observed=True, full_witness_pixel_attempt=pixel_attempt,
        full_witness_pixel_excerpt=pixel_code,
        forward_corner_derivation_is_reverse_lookup=False,
        additional_source_vertex_read_observed=slot == 'B1',
        additional_source_vertex_read_scope='B1 prints the base source vertices after the range lookup; this is separate from recovering surface IDs.' if slot == 'B1' else None,
        source_binding_scoped_to_current_owner=True,
        necessity_of_pixel_recomputation='unmeasured', requests=records)


def raw_review():
    truth = read(HERE/'admin/TRUTH.json')
    pixel_truth = read(HERE/'admin/PIXEL_TRUTH.json')
    saved = load('_independent_source_binding_saved', HERE/'saved_evidence.py')
    regions = {(r['object_index'], tuple(r['source_triangle_indices'])): r for r in truth['regions']}
    wanted = set(pixel_truth['complete_readable_roi_ids'])
    results = []
    for slot in ORDER:
        owner = RUNTIME/slot/'o'
        text = raw(RUNTIME/slot/'c/PUBLIC_FINAL.txt').decode('utf-8')
        plain = clean(text)
        evidence = saved.evaluate_owner(owner, truth)
        check(slot + ':actual_product_facts_correct', evidence['product_errors'] == [], evidence['product_errors'])
        check(slot + ':candidate_source_field_capability', evidence['source_face_binding_delivered'] == slot.startswith('B'))
        entries = parse_inventory(slot, text)
        keys = [(e['object_index'], tuple(e['local_faces'])) for e in entries]
        check(slot + ':exact61surface_inventory', len(keys) == len(set(keys)) == 61 and set(keys) == set(regions))
        references = refs_from_final(text)
        check(slot + ':current_reference_views', set(references) == {'SCENE', 'TOP', 'LEFT', 'BACK'})
        for entry in entries:
            key = (entry['object_index'], tuple(entry['local_faces']))
            expected = regions.get(key)
            check(slot + ':source_identity:' + str(key), expected is not None and entry['object_name'] == expected['object_name'])
            if expected is None:
                continue
            identity = expected['roi_id']
            check(slot + ':surface_state:' + identity, entry['state'] == ('covered' if identity in wanted else 'unknown'))
            if identity in wanted:
                frame = evidence['by_ref'].get(references.get(entry['view']))
                row = next((r for r in frame['rows'] if r['roi_id'] == identity), None) if frame else None
                check(slot + ':current_complete_witness:' + identity, row is not None and row['complete_readable'])
                if 'surface_pixels' in entry:
                    check(slot + ':explicit_witness_counts:' + identity, row is not None
                          and (entry['surface_pixels'], entry['boundary_pixels']) == (row['surface_pixels'], row['boundary_pixels']))
            else:
                check(slot + ':unknown_reason:' + identity, entry['reason'] == pixel_truth['remaining_reasons'][identity])
        check(slot + ':counts_and_scope_explicit', '61' in plain and '18' in plain and '43' in plain
              and '33' in plain and '10' in plain and 'finite' in plain.lower()
              and all(view in plain for view in truth['view_names']))
        unsupported = next(line for line in text.splitlines() if 'ConnectedLBracket' in line and '[0,1,2,3]' in line)
        check(slot + ':explicit_unsupported_component', '11' in unsupported and 'unsupported' in unsupported.lower()
              and ('four_corners_required' in unsupported or 'L-shaped' in unsupported))
        check(slot + ':all_four_unsupported_triangles_bound',
              [r['source_triangle_index'] for r in truth['unsupported_source_triangles']] == [0,1,2,3])
        targets = []
        for target in truth['pixel_targets']:
            block = clean(sample_block(text, target['id']))
            expected = regions[(target['object_index'], tuple(target['source_triangle_indices']))]
            center_line = next(line for line in block.splitlines() if 'center:' in line.lower())
            check(slot + ':' + target['id'] + ':world_center', tuple(saved.vec(expected['center_world_m'])) in tuples_in(center_line))
            front_line = next(line for line in block.splitlines() if 'front orientation:' in line.lower())
            normals = tuples_in(front_line)
            check(slot + ':' + target['id'] + ':front_orientation', any(saved.same_normal(normal, expected['front_direction_world']) for normal in normals))
            corner_lines = [line for line in block.splitlines() if 'Rectangle corners:' in line]
            if corner_lines:
                corners = tuples_in(corner_lines[0])
                check(slot + ':' + target['id'] + ':corners', set(corners) == set(map(saved.vec, expected['quad_world_m'])))
            else:
                rectangle = next(line for line in block.splitlines() if 'Rectangle:' in line)
                required_values = ('z=6.5', 'x∈[-7,7]', 'y∈[-6,6]') if target['id'] == 'sample_A' else ('x=-7', 'y∈[-6,6]', 'z∈[-0.5,0]')
                check(slot + ':' + target['id'] + ':extent', all(value in rectangle for value in required_values))
            check(slot + ':' + target['id'] + ':source_identity_explicit', expected['object_name'] in block
                  and str(expected['source_triangle_indices']).replace(' ', '') in block.replace(' ', ''))
            frame = evidence['by_ref'].get(references.get(target['view_name']))
            actual = frame['raw_region_by_pixel'][target['y']*512+target['x']] if frame else None
            check(slot + ':' + target['id'] + ':actual_pixel_surface', actual == expected['region_index'])
            targets.append(dict(id=target['id'], specified_view=target['view_name'], actual_region_index=actual,
                                expected_region_id=expected['roi_id'], source_excerpt=block))
        for target in truth['source_targets']:
            start = plain.index(target['id'])
            snippet = plain[start:plain.find('\n', start)]
            expected_reason = pixel_truth['remaining_reasons'][target['region_id']]
            check(slot + ':' + target['id'] + ':unknown_reason_text', 'unknown' in snippet.lower()
                  and ('occlu' in snippet.lower() if target['id'] == 'target_C' else 'front-facing' in snippet.lower()))
            source_region = regions[(target['object_index'], tuple(target['source_triangle_indices']))]
            check(slot + ':' + target['id'] + ':source_reason_independent', expected_reason ==
                  ('positive_area_occlusion_all_front_views' if target['id'] == 'target_C' else 'no_front_facing_candidate'))
            if target['id'] == 'target_D':
                check(slot + ':downward_backfacing_in_all_six', all(not v['front_facing'] for v in source_region['views'].values()))
        # Optional explicit count tables receive additional checks in the finalizer.
        flow = dataflow(slot, owner)
        observations = read(owner/'OBSERVATIONS.json')
        for frame in observations['frames']:
            raw(frame['PNG']); raw(frame['NPZ'])
        raw(owner/'product_call_01/SERVICE_RESULT.json')
        results.append(dict(slot=slot, supported=len(entries), covered=sum(e['state']=='covered' for e in entries),
            unknown=sum(e['state']=='unknown' for e in entries), references=references, parsed_inventory=entries,
            pixel_targets=targets, source_binding_delivered=evidence['source_face_binding_delivered'],
            product_errors=evidence['product_errors'], dataflow=flow,
            frames=[{key:frame[key] for key in ('view_name','image_ref','rows')} for frame in evidence['frames']]))
    output = dict(schema='m1-source-binding-raw-semantic-dataflow-v1', checks=CHECKS,
        check_count=len(CHECKS), passed_checks=sum(c['passed'] for c in CHECKS),
        failed_checks=[c for c in CHECKS if not c['passed']], slots=results,
        inputs_sha256=INPUTS, normalization_review_pending=True, performance_cost_usage_consulted=False,
        actual_model_product_observe_raster_calls=0,
        association='Reviewer authored the new product projection and engineering microbenchmarks. Independent source truth and saved-buffer oracle predate this product change.')
    save(HERE/'analysis_scripts/SEMANTIC_RAW_DATAFLOW.json', output)
    print(json.dumps(dict(checks=output['check_count'], passed=output['passed_checks'], failures=output['failed_checks'])))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw-review', action='store_true', required=True)
    parser.parse_args()
    def guard(event, args):
        if event in ('subprocess.Popen', 'os.system', 'socket.connect'):
            raise RuntimeError('offline_semantic_review_only')
        if event == 'open' and isinstance(args[0], (str, bytes)):
            name = Path(args[0]).name
            if name in {'CONSUMER.json', 'COST.json', 'SLOT_TIMING.json', 'FINAL_TIMING.json', 'BATCH_TIMING.json', 'stdout.raw.bin'}:
                raise RuntimeError('performance_and_usage_reads_forbidden')
    sys.addaudithook(guard)
    raw_review()


if __name__ == '__main__':
    main()
