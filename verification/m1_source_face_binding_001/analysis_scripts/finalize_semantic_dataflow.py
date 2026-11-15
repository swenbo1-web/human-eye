"""Finalize source entailment after the source-only normalization is fixed."""

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
CHECKS = []
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    value = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(value).hexdigest()
    return value


def read(path):
    return json.loads(raw(path))


def check(name, passed, detail=None):
    CHECKS.append(dict(check=name, passed=bool(passed), detail=detail))


def load(path):
    spec = importlib.util.spec_from_file_location('_semantic_finalize_helper', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--normalized', type=Path, required=True)
    args = parser.parse_args()
    def guard(event, arguments):
        if event in ('subprocess.Popen', 'os.system', 'socket.connect'):
            raise RuntimeError('read_only_semantic_analysis')
        if event == 'open' and isinstance(arguments[0], (str, bytes)):
            if Path(arguments[0]).name in {'CONSUMER.json','COST.json','SLOT_TIMING.json','FINAL_TIMING.json','BATCH_TIMING.json','stdout.raw.bin'}:
                raise RuntimeError('performance_and_usage_reads_forbidden')
    sys.addaudithook(guard)
    prior = read(HERE/'analysis_scripts/SEMANTIC_RAW_DATAFLOW.json')
    for path, expected in prior['inputs_sha256'].items():
        check('original_source_unchanged:' + path, hashlib.sha256(raw(path)).hexdigest() == expected)
    CHECKS.extend(prior['checks'])
    normalized = read(args.normalized)
    rows = normalized['slots']
    check('six_unique_normalized_slots', len(rows) == 6 and {row['slot_id'] for row in rows} == set(ORDER))
    truth = read(HERE/'admin/TRUTH.json')
    targets = {(r['object_index'], tuple(r['source_triangle_indices'])): r for r in truth['regions']}
    cameras = read(read(HERE/'inputs/SOURCES_A.json')['cameras']['path'])
    directions = {p['name']: tuple(Fraction(v) for v in p['direction_rational']) for p in cameras['views']}
    raw_slots = {row['slot']: row for row in prior['slots']}
    summaries = []
    support_count = 0
    source_count = 0
    for slot in ORDER:
        row = next(value for value in rows if value['slot_id'] == slot)
        earlier = raw_slots[slot]
        text = raw(RUNTIME/slot/'c/PUBLIC_FINAL.txt').decode('utf-8')
        public = json.loads(read(RUNTIME/slot/'o/tool_01/RESPONSE.json')['result']['content'][0]['text'])
        mapping = read(RUNTIME/slot/'o/product_call_01/SERVICE_RESULT.json')['facts']['scope']['patch_support']['regions']
        roi_to_key = {r['roi_id']: (r['object_index'], tuple(r['triangle_indices'])) for r in mapping}
        source_bodies = {'final': text}
        for source in row['sources']:
            body = raw(source['path'])
            check(slot + ':source_hash:' + source['id'], hashlib.sha256(body).hexdigest() == source['sha256'])
            if source['kind'] == 'tool_result':
                source_bodies[source['id']] = '\n'.join(b['text'] for b in json.loads(body)['result']['content'] if b.get('type') == 'text')
            else:
                source_bodies[source['id']] = body.decode('utf-8-sig')
            source_count += 1
        def walk(value):
            nonlocal support_count
            if isinstance(value, dict):
                if 'source_id' in value and 'excerpt' in value:
                    check(slot + ':literal_support:' + str(support_count),
                          value['source_id'] in source_bodies and value['excerpt']
                          and value['excerpt'] in source_bodies[value['source_id']])
                    support_count += 1
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(row)
        def identity(value):
            key = (value.get('object_index'), tuple(value.get('source_triangle_indices', [])))
            target = targets.get(key)
            if target is None:
                return None
            if 'object_name' in value and value['object_name'] != target['object_name']:
                return None
            if 'roi_id' in value and roi_to_key.get(value['roi_id']) != key:
                return None
            return key
        expected = {(e['object_index'], tuple(e['local_faces'])):e for e in earlier['parsed_inventory']}
        actual_keys = [identity(panel['identity']) for panel in row['panels']]
        check(slot + ':normalized_exact_inventory_source', len(actual_keys) == len(set(actual_keys)) == 61 and set(actual_keys) == set(expected))
        for panel in row['panels']:
            key = identity(panel['identity'])
            original = expected.get(key)
            check(slot + ':normalized_state:' + str(key), original is not None and panel['status'] == original['state'])
            if original is None:
                continue
            check(slot + ':table_row_source_entails:' + str(key), any(original['excerpt'] in p['excerpt']
                or p['excerpt'] in original['excerpt'] for p in panel['support'] if p['source_id'] == 'final'))
            if original['state'] == 'covered':
                check(slot + ':normalized_declared_witness:' + str(key), bool(panel['views']) and all(
                    view['view'] == original['view'] and view['ref'] == earlier['references'][original['view']] for view in panel['views']))
            else:
                check(slot + ':normalized_declared_unknown_reason:' + str(key), panel['reason_code'] == original['reason'])
        check(slot + ':normalized_exact_remaining', {identity(item) for item in row['remaining']} ==
              {key for key, value in expected.items() if value['state'] == 'unknown'})
        check(slot + ':finite_scope_and_no_false_claims', row['finite_pool_only'] is True
              and row['global_invisibility_overclaim'] is False and row['contradictions'] == [])
        # All explicit witness count tables are bound from their own final rows.
        measured_frames = {f['view_name']: {r['roi_id']:r for r in f['rows']} for f in earlier['frames']}
        count_entries = []
        for line in text.splitlines():
            cells = [part.strip().replace('*','').replace('`','') for part in line.strip('|').split('|')]
            if not line.startswith('|') or len(cells) != 4:
                continue
            found = re.fullmatch(r'([A-Za-z]+)(?:\s+/)?\s+\[(\d+),(\d+)\]', cells[0])
            if not found:
                continue
            region = next(r for r in truth['regions'] if r['object_name'] == found[1]
                          and r['source_triangle_indices'] == [int(found[2]),int(found[3])])
            view = dict(S='SCENE',L='LEFT',B='BACK').get(cells[1],cells[1])
            actual = measured_frames[view][region['roi_id']]
            counts = [int(cells[2].replace(',','')), int(cells[3].replace(',',''))]
            check(slot + ':extra_count_row:' + region['roi_id'], counts == [actual['surface_pixels'],actual['boundary_pixels']])
            count_entries.append(dict(region_id=region['roi_id'],view=view,counts=counts,source_excerpt=line))
        if slot in ('B1','B3'):
            check(slot + ':all18_explicit_witness_counts_checked', len(count_entries) == 18)
        if slot == 'A1':
            witnesses = [measured_frames[e['view']][targets[key]['roi_id']] for key,e in expected.items() if e['state'] == 'covered']
            check(slot + ':explicit_witness_minima', min(r['surface_pixels'] for r in witnesses) == 67
                  and min(r['boundary_pixels'] for r in witnesses) == 9
                  and 'minimum visible count is 67 and minimum boundary count is 9' in text)
        for pixel in row['pixel_targets']:
            name = pixel['id']
            original = next(t for t in earlier['pixel_targets'] if t['id'] == name)
            target = next(t for t in truth['pixel_targets'] if t['id'] == name)
            region = targets[(target['object_index'], tuple(target['source_triangle_indices']))]
            wanted_normal = [0,0,1] if name == 'sample_A' else [-1,0,0]
            check(slot + ':' + name + ':faithful_front_value', pixel['front_direction_world'] == wanted_normal)
            check(slot + ':' + name + ':faithful_pixel_identity', identity(pixel['identity']) ==
                  (target['object_index'], tuple(target['source_triangle_indices'])))
            check(slot + ':' + name + ':faithful_center_and_ref', pixel['center_world_m'] == region['center_world_m']
                  and pixel['view'] == original['specified_view'] and pixel['ref'] == earlier['references'][original['specified_view']])
            block = original['source_excerpt'].replace(',','')
            witness = measured_frames['LEFT'][region['roi_id']]
            check(slot + ':' + name + ':explicit_localization_witness_counts',
                  str(witness['surface_pixels']) in block and str(witness['boundary_pixels']) in block)
        # Signed facing independently checks the stronger final "all back" and
        # "all six front" declarations, including edge-on discrimination.
        signed = {}
        for name, faces, sign in [('target_C',[2,3],1), ('target_D',[0,1],-1)]:
            region = targets[(0,tuple(faces))]
            normal = tuple(Fraction(str(v)) for v in region['front_direction_world'])
            dots = {view:sum(a*b for a,b in zip(normal,direction)) for view,direction in directions.items()}
            check(slot + ':' + name + ':signed_all_camera_facing', all(value*sign > 0 for value in dots.values()))
            if name == 'target_C':
                check(slot + ':target_C:all_front_occluded', all(Fraction(str(v['positive_shadow_area'])) > 0 for v in region['views'].values()))
            signed[name] = {view:str(value) for view,value in dots.items()}
        flow = earlier['dataflow']
        for diagnostic, expected_observed in [('geometry_reverse_lookup',slot.startswith('A')), ('full_witness_pixel_recomputation',True)]:
            current = row['process_diagnostics'][diagnostic]
            check(slot + ':dataflow_diagnostic_entailment:' + diagnostic,
                  current['observed'] == expected_observed and current['review_complete'] is True
                  and current['reviewed_tool_attempts'] == flow['reviewed_tool_attempts'])
        claims = row['source_binding_use']['claims']
        if slot.startswith('B'):
            check(slot + ':actual_binding_use_claims', bool(claims) and earlier['source_binding_delivered'])
            for index, claim in enumerate(claims):
                check(slot + ':actual_binding_operation:' + str(index),
                      identity(claim['identity']) in expected and claim['operation'] == 'pixel_source_face_to_region'
                      and claim['binding_scoped'] is True and claim['dataflow_confirmed_by_review'] is True)
                operation = next(record for record in flow['requests'] if record['attempt'] == flow['source_ranges_operation_attempt'])
                source_id = next(s['id'] for s in row['sources'] if Path(s['path']).resolve() == Path(operation['request_path']).resolve())
                check(slot + ':actual_binding_operation_source:' + str(index), any(s['source_id'] == source_id for s in claim['operation_support']))
                check(slot + ':actual_binding_task_use:' + str(index), any(s['source_id'] == 'final' and 'sample_A' in s['excerpt'] for s in claim['task_use_support']))
        else:
            check(slot + ':old_A_no_new_field_use_claim', claims == [] and not earlier['source_binding_delivered'])
        summaries.append(dict(slot=slot, core_claims_correct=True, complete_final_semantically_correct=True,
            unsupported_additional_false_claims=[], source_binding_received_and_used=slot.startswith('B'),
            geometric_reverse_lookup_observed=slot.startswith('A'), full_witness_pixel_recomputation_observed=True,
            reviewed_tool_attempts=flow['reviewed_tool_attempts'], source_binding_operation_attempt=flow['source_ranges_operation_attempt'],
            geometry_reverse_attempt=flow['geometry_reverse_lookup_attempt'], pixel_recomputation_attempt=flow['full_witness_pixel_attempt'],
            additional_source_vertex_read_scope=flow['additional_source_vertex_read_scope'],
            necessity_of_pixel_recomputation='unmeasured', explicit_count_rows=count_entries, signed_source_target_facing=signed))
    failures = [c for c in CHECKS if not c['passed']]
    report = dict(schema='m1-source-face-binding-semantic-dataflow-review-v1', passed=not failures,
        check_count=len(CHECKS), passed_checks=len(CHECKS)-len(failures), failed_checks=failures,
        checks=CHECKS, formal_denominator=6, actual_slots_reviewed=6, slot_results=summaries,
        normalized_path=str(args.normalized.resolve()), normalized_sha256=hashlib.sha256(raw(args.normalized)).hexdigest(),
        inputs_sha256=INPUTS, source_fragments_checked=support_count, sources_checked=source_count,
        source_binding_use_B=3, geometric_reverse_A=3, geometric_reverse_B=0,
        full_witness_pixel_recomputation_A=3, full_witness_pixel_recomputation_B=3,
        previous_B_normalization_correction='B1/B2 initially transcribed center into front_direction_world. Independent raw review caught four fields before scoring. The corrected normalization must match all six actual front-orientation statements. Original outputs and correction events are retained.',
        performance_usage_cost_ranking_consulted=False, new_model_product_observe_raster_calls=0,
        association='Reviewer authored candidate source projection and engineering measurements. This semantic review uses prior independent truth and saved-buffer arithmetic; it does not establish independent authorship of the candidate.')
    save(HERE/'admin/SEMANTIC_DATAFLOW_REVIEW.json', report)
    print(json.dumps(dict(passed=report['passed'],checks=report['check_count'],failures=failures)))


if __name__ == '__main__':
    main()
