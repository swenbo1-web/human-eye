"""Bind P2 quality evidence to delivered images, independent geometry and original calls."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
PILOT = NS.parent / 'perf050_readonly_product_pilot_001'
ACTIVE = NS.parent / 'm4_source_region_active_view_001'
PILOT_RUN = Path('D:/he_perf050_readonly_product_pilot_001')
ACTIVE_RUN = Path('D:/he_m4_source_region_active_view_001')
RUN = Path('D:/he_perf050_source_region_active_view_p2')
INSTALL = ACTIVE / 'install/PRODUCT_RUN_BINDING.json'
TRUTH = PILOT / 'truth/TRUTH.json'
ASSET = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
SOURCE = '2ad989728b7229934d164cf4c763eeb89b28e86d6fbfe7b90bace82055b2683c'
PROMPT_SHA = 'ee9e22bfef64fc8799b57f0569a320ebe93a16ff8862c7e3d6ed6236b92be98e'


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(data):
    return sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}


class Originals:
    def __init__(self, runtime, index, expected_sha, count):
        self.root = runtime.resolve()
        desc = read(index)
        archive = Path(desc['archive']['path']).resolve()
        require(archive == self.root / 'ORIGINAL_RUNTIME.zip', 'wrong_original_archive')
        arc = pin(archive)
        require((arc['bytes'], arc['sha256'], desc['archive']['sha256']) ==
                (desc['archive']['bytes'], expected_sha, expected_sha), 'original_archive_hash_changed')
        self.archive = ZipFile(archive)
        self.files = {row['path']: row for row in desc['files']}
        require(len(self.files) == desc['count'] == count and
                self.archive.namelist() == list(self.files), 'original_archive_index_changed')
        self.pins = [arc, pin(index)]

    def close(self):
        self.archive.close()

    def member(self, name):
        data = (self.root / name).read_bytes()
        row = self.files[name]
        require(len(data) == row['bytes'] and digest(data) == row['sha256'] and
                self.archive.read(name) == data, 'archive_original_changed/' + name)
        self.pins.append(pin(self.root / name))
        return data

    def json(self, name):
        return json.loads(self.member(name))


def response_body(result):
    if result.get('isError') is not False:
        return None
    for block in result.get('content', []):
        if block.get('type') != 'text':
            continue
        try:
            body = json.loads(block['text'])
        except (json.JSONDecodeError, KeyError):
            continue
        if isinstance(body, dict):
            return body
    return None


def scope_and_facts(body, query):
    """Classify only explicit whole-object and selected-source facts for this task."""
    if not body:
        return []
    if body.get('schema') in ('source-region-brief-v2', 'source-region-brief-v3') or body.get('result_kind') == 'source_region':
        task = body['task_result']
        region = body.get('region') or body['facts']['region']
        return [dict(scope=task['measurement_scope'], objects=[region['object_name'], task['reference'].get('name')],
                     proximity=task['facts'].get('surface_proximity'))]

    task = body.get('task_result', body)
    if not isinstance(task, dict) or task.get('result_kind') != 'task_query':
        return []
    request = query.get('task_query', query)
    binding = task.get('binding', {})
    pair = binding.get('objects', [])
    if binding.get('measurement_scope') == 'whole_objects' and binding.get('object_indices') is not None:
        directory = body.get('objects', [])
        if isinstance(directory, dict):
            directory = [dict(zip(directory['columns'], row, strict=True)) for row in directory['rows']]
        try:
            names = [directory[idx].get('object_name') or directory[idx].get('name') for idx in binding['object_indices']]
        except (IndexError, KeyError, TypeError):
            names = [selector.get('name') for selector in request.get('objects', [])]
        return [dict(scope='whole_objects', objects=names, proximity=task.get('facts', {}).get('surface_proximity'))]
    names = {row['object_id']: row.get('name', row.get('object_name')) for row in pair if 'object_id' in row}
    if task.get('schema_version') == 'task-query-set-v1' and 'target' in request:
        target = request['target']
        target_name = target.get('name') or names.get(target.get('id'))
        return [dict(scope='whole_objects', objects=[target_name, names.get(row['object_id'])],
                     proximity=row.get('facts', {}).get('surface_proximity'))
                for row in task.get('pairs', [])]
    if len(pair) == 2 and task.get('pair_order') == 'A_to_B' and len(request.get('objects', [])) == 2:
        return [dict(scope='whole_objects', objects=[row.get('name', row.get('object_name')) for row in pair],
                     proximity=task.get('facts', {}).get('surface_proximity'))]
    return []


def display_rows(body):
    scope = deepcopy(body['image_scope'])
    if body['schema'] == 'source-region-brief-v3':
        directory = scope['objects']
        columns, rows = directory['columns'], directory['rows']
        require(len(columns) == len(set(columns)) and all(len(row) == len(columns) for row in rows),
                'display_directory_is_not_lossless')
        scope['objects'] = [dict(zip(columns, row, strict=True)) for row in rows]
    return scope


def check_archived_pilot():
    archive = Originals(PILOT_RUN, PILOT / 'RUNTIME_INDEX.json',
                        'd138efe19891843244f1049e0fab61ea5b6f2d4b923742d632516743ff1a7e71', 555)
    files = [PILOT / 'QUALITY.json', PILOT / 'consumer/COSTS.json', PILOT / 'FROZEN.json',
             PILOT / 'RUBRIC.md', PILOT / 'inputs/PROMPT.txt', PILOT / 'quality_images.py', TRUTH]
    report = read(files[0])
    require(report['freeze_sha256'] == pin(files[2])['sha256'] and report['asset_sha256'] == ASSET and
            pin(files[4])['sha256'] == PROMPT_SHA and pin(files[4])['bytes'] == 387, 'old_task_or_rubric_changed')
    try:
        for row in report['rows']:
            label = row['label']
            stem = f'slots/{label}'
            actual = archive.json(stem + '/SLOT_RESULT.json')
            closed = archive.json(stem + '/SLOT_PUBLICATION.json')
            answer = archive.member(stem + '/consumer/PUBLIC_FINAL.txt')
            require(actual['status'] == closed['status'] == 'completed' and actual['freeze_sha256'] == report['freeze_sha256']
                    and actual['asset_sha256'] == ASSET and actual['model_consumers'] == 1 and
                    closed['result_sha256'] == digest(archive.member(stem + '/SLOT_RESULT.json')) and
                    row['answer_sha256'] == digest(answer) and row['figure_ref'].encode() in answer,
                    'old_consumer_publication_changed/' + label)
            device = archive.json(stem + '/DEVICE_EVIDENCE.json')
            frame, = (frame for frame in device['frames'] if frame['ref'] == row['figure_ref'])
            for field in ('PNG', 'NPZ'):
                frame_path = Path(frame[field]).resolve()
                raw = archive.member(frame_path.relative_to(PILOT_RUN.resolve()).as_posix())
                require(digest(raw) == frame[field + '_sha256'], 'old_scene_figure_changed/' + label)
        require([(r['label'], r['earned'], r['possible']) for r in report['rows']] == [('N1', 5, 5), ('P1', 3, 5)],
                'old_quality_values_changed')
        def facts(attempt):
            stem = f'slots/P1/owner/tool_{attempt:02d}'
            request = archive.json(stem + '/PRODUCT_REQUEST.json')
            response = archive.json(stem + '/PRODUCT_RESPONSE.json')
            return scope_and_facts(response_body(response['result']), request['params']['arguments']['query'])
        selected, = facts(3)
        whole, = facts(6)
        require(selected['scope'] == 'complete_selected_source_triangle_union_to_reference_triangle_surface'
                and whole['scope'] == 'whole_objects' and selected['objects'] == whole['objects'] == ['N15', 'N23']
                and selected['proximity']['value']['distance_m'] == whole['proximity']['value']['distance_m'],
                'historical_selected_and_whole_scope_controls_changed')
        return [*archive.pins, *map(pin, files)], {'scores': {r['label']: r['earned'] for r in report['rows']},
              'requested_pair': whole['objects'], 'selected_scope_control': selected['scope'],
              'whole_scope_control': whole['scope'], 'equal_distance_m': whole['proximity']['value']['distance_m']}
    finally:
        archive.close()


def check_archived_active():
    archive = Originals(ACTIVE_RUN, ACTIVE / 'RUNTIME_INDEX.json',
                        '7a2637ddfd2b751d40ed3b08515e0326c2f5147cfc84cc74e1d73975bedfec03', 293)
    review = ACTIVE / 'checks/LIVE_REVIEW_RECONCILED.json'
    report = read(review)
    require(report['passed'] is True and report['denominators']['qualified'] == 2, 'old_engineering_gate_changed')
    files = [review, ACTIVE / 'FROZEN.json', ACTIVE / 'checks/evidence.py',
             ACTIVE / 'checks/live_postfreeze.py', INSTALL]
    rows = []
    try:
        for label in ('A', 'B'):
            for turn in (1, 2):
                stem = f'slots/{label}/batch/rpc_{turn+2:02d}'
                tx = archive.member(stem + '/TCP_TX.bin')
                rx = archive.member(stem + '/TCP_RX.bin')
                receipt = archive.json(stem + '/RECEIPT.json')
                require(json.loads(tx)['args']['attempt'] == turn and digest(tx) == receipt['TX_sha256'] and
                        digest(rx) == receipt['RX_sha256'] and json.loads(rx)['result'] == receipt['response'],
                        'old_engineering_outer_attempt_changed')
                inner = archive.json(f'slots/{label}/product_calls/call_{turn:03d}/RESPONSE.json')
                producer = archive.json(f'slots/{label}/product_full/call_{turn:03d}/SERVICE_RESULT.json')
                require(inner['result'] == receipt['response']['result'], 'old_engineering_actual_public_content_changed')
                body = response_body(inner['result'])
                image = archive.member(stem + '/image_1.png')
                require(base64.b64decode(inner['result']['content'][1]['data'], validate=True) == image and
                        digest(image) == body['images'][0]['image_sha256'] == producer['frames'][0]['image_sha256'],
                        'old_engineering_original_png_changed')
                scope = display_rows(body)
                require(scope == producer['binding']['image_scope'] and len(scope['objects']) == 28,
                        'old_engineering_directory_not_lossless')
                witness = body['visibility']['complete_witness']
                if label == 'B':
                    require(body['schema'] == 'source-region-brief-v3' and
                            (witness['view_name'], witness['selected_surface_pixels'],
                             witness['contrasting_boundary_pixels']) == ('RIGHT', 86955, 1300),
                            'old_engineering_candidate_witness_changed')
                else:
                    require(body['schema'] == 'source-region-brief-v2' and witness is None,
                            'old_engineering_baseline_changed')
                rows.append({'label': label, 'attempt': turn, 'body_schema': body['schema'],
                             'images': 1, 'display_rows': len(scope['objects']),
                             'raster_attempts': producer['work']['raster_attempts']})
        require([row['raster_attempts'] for row in rows] == [1, 0, 2, 0], 'old_engineering_rasters_changed')
        return [*archive.pins, *map(pin, files)], rows
    finally:
        archive.close()


def preflight():
    original_pins, pilot = check_archived_pilot()
    active_pins, active = check_archived_active()
    pins = {entry['path']: entry for entry in (*original_pins, *active_pins, pin(Path(__file__)))}
    return {'schema': 'perf050-source-region-active-view-p2-review-preflight-v1', 'passed': True,
            'asset_sha256': ASSET, 'prompt_sha256': PROMPT_SHA, 'historical_pilot': pilot,
            'historical_engineering': active, 'source_pins': list(pins.values())}


def product_attempt(attempt, slot):
    row = attempt.get('product')
    if not row:
        return None
    idx = attempt['attempt']
    owner = slot / 'owner' / f'tool_{idx:02d}'
    request = read(owner / 'PRODUCT_REQUEST.json')
    query = request['params']['arguments']['query']
    if not (owner / 'PRODUCT_RESPONSE.json').is_file():
        return {'attempt': idx, 'mode': query.get('mode'), 'outcome': 'no_public_reply'}
    response = read(owner / 'PRODUCT_RESPONSE.json')
    parent = row.get('producer_archive')
    producer = None
    if parent:
        source = Path(parent['path']).resolve()
        require(source.is_relative_to(slot.resolve()) and digest(source.read_bytes()) == parent['sha256'],
                'actual_P2_producer_receipt_mismatch')
        producer = read(source)
    body = response_body(response['result'])
    wire = attempt.get('stdio_RX')
    delivered = (wire is not None and attempt.get('CLI_binding') == 'content_and_envelope_match')
    if delivered:
        raw_file = Path(wire['path']).resolve()
        require(raw_file.is_relative_to(slot.resolve()) and digest(raw_file.read_bytes()) == wire['sha256'] and
                read(raw_file)['result'] == response['result'], 'actual_product_and_consumer_wire_divergence')
    images = []
    source_region = (body and (body.get('result_kind') == 'source_region' or
                               body.get('schema') in ('source-region-brief-v2', 'source-region-brief-v3')))
    for image in body.get('images', []) if source_region else []:
        locator = image.get('image_block_index')
        if type(locator) is int and 0 <= locator < len(response['result']['content']):
            block = response['result']['content'][locator]
            raw = base64.b64decode(block['data'], validate=True)
            require(block['type'] == 'image' and block['mimeType'] == 'image/png' and
                    digest(raw) == image['image_sha256'], 'product_image_reference_mismatch')
            images.append(image)
    witness, bound_target = None, False
    if source_region:
        witness = (body.get('visibility') or body['facts']['visibility']).get('complete_witness')
        if witness is not None:
            region = body.get('region') or body['facts']['region']
            require(producer is not None and producer['facts']['visibility']['complete_witness'] == witness and
                    body['region_ref'] == producer['region_ref'], 'candidate_scope_or_witness_binding_mismatch')
            if body.get('schema') == 'source-region-brief-v3':
                require(display_rows(body) == producer['binding']['image_scope'] and len(images) == 1 and
                        (images[0]['image_ref'], images[0]['frame_identity']) ==
                        (witness['image_ref'], witness['frame_identity']), 'candidate_v3_display_or_frame_binding_mismatch')
            else:
                # The full form carries the producer's frame with its original reference.
                frames = [frame for frame in body.get('frames', []) if
                          (frame['image_ref'], frame['frame_identity']) ==
                          (witness['image_ref'], witness['frame_identity'])]
                require(len(frames) == 1, 'candidate_full_missing_original_frame')
            bound_target = (body['region_ref']['source_triangle_indices'] == [20, 21] and
                            region['object_name'] == 'N15')
    return {'attempt': idx, 'mode': query.get('mode'), 'schema': body.get('schema', body.get('schema_version')) if body else None,
            'query': query, 'outcome': 'accepted' if body is not None else 'is_error_or_no_json_result',
            'delivered_to_CLI': delivered, 'measurements': scope_and_facts(body, query), 'images': images,
            'complete_witness': witness, 'witness_targets_frozen_region': bound_target,
            'source_image_evidence': body.get('visibility') if body else None}


def review(run, costs_path):
    costs = read(costs_path)
    rows = [row for row in costs['slots'] if row['label'] == 'P2']
    require(len(rows) == 1, 'costs_must_contain_exactly_one_P2_row')
    arm, = rows
    slot = run / 'slots/P2'
    out = {'schema': 'perf050-source-region-active-view-p2-quality-evidence-v1',
           'costs_sha256': pin(costs_path)['sha256'], 'status': arm['status'], 'frames': [],
           'historical_denominator_excluded': True, 'product_attempts': []}
    if not slot.is_dir():
        require(arm['status'] == 'unrun', 'unexpected_record_for_unrun_slot')
        return out
    answer_path = slot / 'consumer/PUBLIC_FINAL.txt'
    answer = answer_path.read_text(encoding='utf-8') if answer_path.is_file() else ''
    out['answer'] = pin(answer_path) if answer_path.is_file() else None
    out['normal_initial_prompt'] = arm.get('initial_prompt_sha256') == PROMPT_SHA
    delivery = {}
    for attempt in arm.get('actual_requests', []):
        original = attempt['wire_content']['PNG']
        if attempt.get('CLI_binding') == 'content_and_envelope_match' and attempt.get('CLI_delivered_images') == len(original):
            for image in original:
                delivery.setdefault(image['sha256'], []).append(attempt['attempt'])
        try:
            product = product_attempt(attempt, slot)
        except (KeyError, OSError, TypeError, ValueError) as error:
            query = (attempt.get('arguments') or {}).get('query') or {}
            product = {'attempt': attempt['attempt'], 'mode': query.get('mode') if isinstance(query, dict) else None,
                       'outcome': 'evidence_binding_error', 'error': str(error)}
        if product is not None:
            out['product_attempts'].append(product)
    install = read(INSTALL)
    require(install['source_sha256'] == SOURCE, 'candidate_product_changed')
    sys.path.insert(0, install['dependency_root'])
    image_review = run_path(str(PILOT / 'quality_images.py'))
    oracle = run_path(str(PILOT / 'truth/oracle.py'))
    truth = read(TRUTH)
    evidence = slot / 'DEVICE_EVIDENCE.json'
    frames = read(evidence)['frames'] if evidence.is_file() else []
    for frame in frames:
        try:
            checked = image_review['inspect_frame'](slot, frame, truth, delivery, oracle)
        except (KeyError, OSError, TypeError, ValueError) as error:
            checked = {'ref': frame.get('ref'), 'origin': frame.get('origin'), 'view': frame.get('view'),
                       'qualifies': False, 'error': str(error)}
        checked['cited_literal_ref_in_answer'] = isinstance(checked['ref'], str) and checked['ref'] in answer
        out['frames'].append(checked)
    cited = {row['ref']: row for row in out['frames'] if row['cited_literal_ref_in_answer'] and row['qualifies']}
    opportunities = []
    for attempt in out['product_attempts']:
        witness = attempt.get('complete_witness')
        if witness is None:
            continue
        frame = next((row for row in out['frames'] if row['ref'] == witness['image_ref']), None)
        verified = (attempt['witness_targets_frozen_region'] and frame is not None and frame['qualifies'] and
                    frame['surface_pixels'] == witness['selected_surface_pixels'] and
                    frame['contrasting_boundary_pixels'] == witness['contrasting_boundary_pixels'])
        delivered = verified and attempt['delivered_to_CLI'] and attempt['attempt'] in frame['delivered_in_attempts']
        opportunities.append({'attempt': attempt['attempt'], 'ref': witness['image_ref'],
                              'verified_original': verified, 'delivered': delivered,
                              'same_ref_cited': delivered and witness['image_ref'] in cited})
    out['candidate_complete_frame_attempts'] = opportunities
    out['first_candidate_complete_delivery'] = next((x for x in opportunities if x['delivered']), None)
    out['quoted_candidate_complete_frame'] = any(row['same_ref_cited'] for row in opportunities)
    out['verified_ordinary_frames_cited'] = [ref for ref, row in cited.items()
                                            if row['origin'] == 'common_native' and row['delivered_in_attempts']]
    out['whole_object_proximity_attempts'] = [
        item['attempt'] for item in out['product_attempts'] if item.get('delivered_to_CLI') and
        any(row['scope'] == 'whole_objects' and set(row['objects']) == {'N15', 'N23'} and
            (row.get('proximity') or {}).get('status') == 'measured' for row in item['measurements'])]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--run', type=Path, default=RUN)
    parser.add_argument('--costs', type=Path, default=NS / 'consumer/COSTS.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_isolated_interpreter_required')
    data = preflight() if args.preflight else review(args.run, args.costs)
    output = args.output or HERE / ('PREFLIGHT.json' if args.preflight else 'P2_EVIDENCE.json')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(output, pin(output)['sha256'], data.get('passed', data.get('status')))


if __name__ == '__main__':
    main()
