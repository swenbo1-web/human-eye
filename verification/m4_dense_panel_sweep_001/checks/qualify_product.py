"""Audit the sole product qualification and fixed CLI presentation against source truth."""

import argparse
from collections import Counter
from fractions import Fraction
from itertools import accumulate
import json
from os.path import commonprefix
from pathlib import Path
import runpy
import sys
import time


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
RUN = Path('D:/he_m4_dense_panel_sweep_001')
ASSET = Path('D:/he_m4_target_002/assets_01/main.blend')
ASSET_SHA = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
GEOMETRY = ASSET.with_name('main.GEOMETRY.json')
GEOMETRY_SHA = 'a48ef1b1634e1bbe66fbb49d47899581432d6bf4aebae5577ea5abdebf4b774d'
PRODUCT_SHA = '6f2fc9762f9410f968c4768545c14077ca944f75416fb04aa9d14145a4c630d8'
BINDING = V / 'm4_cross_scale_projected_bounds_001/install/PRODUCT_RUN_BINDING.json'
REQUEST = {'query': {'mode': 'active_observation', 'region_task': {
    'area_min_m2': 1, 'area_max_m2': 1, 'normal_z_min': 0}}, 'include_image': True, 'response_detail': 'brief'}
PIXEL = runpy.run_path(str(V / 'm4_cross_scale_pixel_evidence_001/checks/assess_live.py'))
POLICY = runpy.run_path(str(V / 'm4_cross_scale_live_qualification_001/checks/delivery.py'))
FORMAL = runpy.run_path(str(V / 'm4_cross_scale_live_task_formal_001/scoring/formal.py'))
prior, capture_check = PIXEL['prior'], PIXEL['checker']
read, require, verified, write, digest, rows, ms, stage_ms = (PIXEL[k] for k in
    ('read', 'require', 'verified', 'write', 'digest', 'rows', 'ms', 'stage_ms'))


def spans(text, prefix=()):
    """Index complete JSON fields by their exact lexical extent, including member names."""
    decoder = json.JSONDecoder()
    index = {}

    def skip(at):
        while at < len(text) and text[at].isspace():
            at += 1
        return at

    def descend(at, path, field_start):
        at = skip(at)
        char = text[at]
        if char not in '{[':
            _, end = decoder.raw_decode(text, at)
        else:
            close = '}' if char == '{' else ']'
            cursor, ordinal = skip(at + 1), 0
            while text[cursor] != close:
                start = cursor
                if char == '{':
                    key, cursor = decoder.raw_decode(text, cursor)
                    require(type(key) is str and skip(cursor) < len(text) and text[skip(cursor)] == ':',
                            'CLI_original_JSON_member_syntax')
                    cursor = skip(cursor) + 1
                else:
                    key, ordinal = ordinal, ordinal + 1
                path_next = (*path, key)
                require(path_next not in index, 'CLI_original_JSON_member_duplicated')
                cursor = skip(descend(cursor, path_next, start))
                require(text[cursor] in (close, ','), 'CLI_original_JSON_separator_syntax')
                if text[cursor] == ',':
                    cursor = skip(cursor + 1)
            end = cursor + 1
        index[path] = field_start, end
        return end

    require(skip(descend(0, prefix, skip(0))) == len(text), 'CLI_original_JSON_not_one_value')
    return index


def byte_span(text, extent):
    start, end = extent
    return [len(text[:start].encode()), len(text[:end].encode())]


def region_key(row):
    return row['object_name'], tuple(row['source_triangle_indices'])


def region_label(key):
    name, triangles = key
    return f'{name}[{triangles[0]}–{triangles[-1]}]'


def row_delivery(body, retained, public, original_images, present_images):
    index = spans(body)
    is_exact = body == retained
    head = len(commonprefix((body, retained)))
    tail = len(body) - len(commonprefix((body[::-1], retained[::-1])))
    marker = 'truncated…' in retained
    require(is_exact or not retained or marker and head < tail, 'CLI_replay_not_original_middle_truncation')

    def survived(path):
        start, stop = index[path]
        return is_exact or stop <= head or start >= tail

    mandatory = []
    row_reports = []
    top_paths = (('schema',), ('binding',), ('region_task', 'conditions'), ('region_task', 'summary'))
    for path in top_paths:
        if not survived(path):
            mandatory.append('.'.join(path))
    images_by_ref = {image['ref']: image for image in original_images}
    all_witnesses = public['witness_pixels']
    roi_column = all_witnesses['columns'].index('roi_id')
    witness_ordinal = {row[roi_column]: i for i, row in enumerate(all_witnesses['rows'])}

    for i, row in enumerate(public['region_task']['rows']):
        root = ('region_task', 'rows', i)
        alternatives = [root + ('source_triangle_indices',), root + ('source', 'source_triangle_indices')]
        required = {name: survived(root + (name,)) for name in (
            'object_name', 'center_world_m', 'status', 'reason', 'complete_witness', 'view_reasons')}
        if not required['object_name']:
            required['object_name'] = (survived(root + ('object_index',))
                and survived(('objects', 'columns')) and survived(('objects', 'rows', row['object_index'])))
        required['source_triangles'] = any(survived(path) for path in alternatives)
        witness = row['complete_witness']
        if witness is not None:
            image = images_by_ref.get(witness['image_ref'])
            required['bound_image_and_pixels'] = (image is not None and image['PNG_sha256'] in present_images
                and all(survived(path) for path in (('images', 'columns'),
                    ('images', 'rows', image['content_index'] - 1), ('witness_pixels', 'columns'),
                    ('witness_pixels', 'rows', witness_ordinal[row['roi_id']]))))
        missing = [name for name, ok in required.items() if not ok]
        if missing:
            mandatory.extend(f'rows[{i}].{name}' for name in missing)
        row_reports.append({'object_name': row['object_name'], 'region': region_label(region_key(row)), 'ordinal': i,
            'raw_byte_span': byte_span(body, index[root]),
            'required_facts_available': required, 'missing_required_facts': missing,
            'source_alternatives': [{'path': list(path), 'raw_byte_span': byte_span(body, index[path]),
                                     'preserved': survived(path)} for path in alternatives]})
    return {'text_exact': is_exact, 'structured_JSON_recoverable': is_exact,
            'body_UTF8_bytes': len(retained.encode()), 'raw_prefix_bytes': len(body[:head].encode()),
            'raw_suffix_bytes': len(body[tail:].encode()) if not is_exact else 0,
            'required_facts_lost': mandatory, 'rows': row_reports}


def replay(result, public, images, output):
    helpers, limits = POLICY['budget_helpers']()
    image_receipts = [row for row, _ in images]
    body = result['content'][0]['text']
    spans_index = spans(body)
    source_bytes = Counter()
    for i in range(len(public['region_task']['rows'])):
        prefix = ('region_task', 'rows', i)
        for suffix, name in ((('source_triangle_indices',), 'outer'), (('source','source_triangle_indices'), 'nested')):
            lo, hi = byte_span(body, spans_index[prefix + suffix])
            source_bytes[name] += hi - lo
    stages = []
    output.mkdir(parents=True, exist_ok=True)
    for seconds in ('0.0000', '10.0000', '100.0000'):
        raw = helpers['model_items'](result, seconds)
        mcp = helpers['truncate_items'](raw, limits['MCP_bytes'])
        history = helpers['truncate_items'](mcp, limits['history_approximate_tokens'], token_mode=True)
        report = {'sample_wall_seconds': seconds, 'header_bytes': len(raw[0]['text'].encode())}
        for key, contents in (('MCP', mcp), ('history', history)):
            delivered_images = [item for item in contents if item['type'] == 'input_image']
            image_exact = delivered_images == [item for item in raw if item['type'] == 'input_image']
            text_items = [item['text'] for item in contents if item['type'] == 'input_text']
            hashes = [digest(PIXEL['typed']['DECODE']({
                'mimeType': item['image_url'].split(';', 1)[0][5:],
                'data': item['image_url'].split(',', 1)[1]})) for item in delivered_images]
            stage = row_delivery(body, text_items[1] if len(text_items) > 1 else '', public, image_receipts, set(hashes))
            report[key] = {**stage, 'images_exact': image_exact, 'retained_PNG_sha256': hashes}
            path = output / f'{seconds}_{key}.json'
            write(path, {'text_items': text_items, 'PNG_sha256': hashes})
            report[key]['retained_representation_sha256'] = digest(path.read_bytes())
        stages.append(report)
    return {'limits': limits, 'full_body_bytes': len(body.encode()), 'source_triangle_field_bytes': dict(source_bytes),
            'stages': stages, 'passed': all(not s[key]['required_facts_lost'] and s[key]['images_exact']
                                            for s in stages for key in ('MCP', 'history')),
            'live_model_or_provider_input_observed': False}


def current_source(slot, result):
    startup, ready, closed = FORMAL['generic_process'](
        slot, ASSET.resolve(), (slot / 'native/input.blend').resolve(), ASSET_SHA, result['owned_deadline_ns'])
    initial, terminal = result['initial_source'], result['terminal_source']
    pid = startup['pid']
    first = FORMAL['read_capture'](slot, slot / 'initial_capture/TERMINAL_SOURCE.json', initial, pid, ASSET_SHA)
    last = FORMAL['read_capture'](slot, slot / 'TERMINAL_SOURCE.json', terminal, pid, ASSET_SHA)
    require(startup['created_after_ns'] <= first['started_ns'] <= initial['worker']['file_closed_ns'] <=
            result['ready_ns'] <= result['cleanup_started_ns'] <= last['started_ns'] <=
            terminal['worker']['file_closed_ns'] <= closed['closed_ns'] <= result['owned_deadline_ns'],
            'current_source_readbacks_do_not_bracket_request')
    fields = ('source', 'objects', 'source_face_offsets', 'display_object_mask', 'display_scope',
              'display_read', 'layer_collections', 'scene_cameras')
    require(all(first[field] == last[field] for field in fields), 'current_source_or_display_changed')
    fixture = json.loads(verified(GEOMETRY, GEOMETRY_SHA, ASSET.parent))
    saved = {item['name']: item for item in fixture['objects']}
    current = {item['name']: item for item in last['objects']}
    require(len(saved) == len(last['objects']) == len(current) == 14 and saved.keys() == current.keys() and
            last['source']['unit_settings']['system'] == fixture['unit_system'] and
            last['source_face_offsets'] == [0, *accumulate(len(item['evaluated']['triangles']) for item in last['objects'])] and
            last['display_object_mask'] == [item['visible_get'] for item in last['objects']],
            'current_fixture_order_denominator_or_visibility_invalid')
    for name, mesh in current.items():
        ref = saved[name]
        for role in ('native', 'evaluated'):
            actual = mesh[role]
            require(actual['vertices_world_m'] == ref['vertices_world'] and
                    actual['triangles'] == ref['source_triangles'] and actual['vertices'] == ref['vertices_local'] and
                    actual['polygons'] == ref['polygons'], 'current_mesh_arrays_differ/' + name + '/' + role)
        require(mesh['native_matrix_world'] == mesh['matrix_world'] == ref['matrix_world'],
                'current_mesh_transform_differ/' + name)
    return last, {'initial_sha256': initial['sha256'], 'terminal_sha256': terminal['sha256'],
                  'unchanged_fingerprint': ready['initial_fingerprint'], 'visible_objects': sum(last['display_object_mask']),
                  'current_geometry_sha256': GEOMETRY_SHA, 'owned_copy_sha256': ASSET_SHA}


def audit_wire(slot, started, result, published):
    event, = rows(slot / 'PUBLIC_REQUESTS.jsonl')
    meter, = [item for item in rows(slot / 'mcp_io/MCP_IO.jsonl') if item['method'] == 'tools/call']
    req, receipt = event['request'], event['receipt']
    require(req['params'] == {'name': PIXEL['PRODUCT'], 'arguments': REQUEST} and
            req['method'] == 'tools/call' and req['id'] == receipt['id'] == meter['id'] == meter['response_id'] and
            receipt['error'] is None and event['index'] == 1, 'wrong_frozen_qualification_request_or_RPC_error')
    folder = slot / 'mcp' / f"rpc_{receipt['index']:02d}"
    tx, rx = ((folder / filename).read_bytes() for filename in ('TX.bin', 'RX.bin'))
    raw_lf = rx.replace(b'\r\n', b'\n')
    call = slot / 'product_calls/call_001'
    reply = json.loads(rx)
    require(json.loads(tx) == req == read(call / 'REQUEST.json') and read(folder / 'RECEIPT.json') == receipt and
            reply == read(call / 'RESPONSE.json') == event['response'] and reply['id'] == req['id'] and
            len(tx) == meter['TX_bytes'] == receipt['TX_bytes'] and digest(tx) == meter['TX_sha256'] and
            len(rx) == receipt['RX_bytes'] and digest(rx) == receipt['RX_sha256'] and
            len(raw_lf) == meter['RX_text_UTF8_LF_bytes'] and digest(raw_lf) == meter['RX_text_UTF8_LF_sha256'],
            'owned_stdio_original_bytes_disagree')
    wire = {'TX_sha256': digest(tx), 'RX_sha256': digest(rx), 'TX_bytes': len(tx), 'RX_bytes': len(rx)}
    timings = {'owned_window_ms': ms(started['started_ns'], published['published_ns']),
               'startup_to_ready_ms': ms(started['started_ns'], result['ready_ns']),
               'request_window_ms': ms(event['started_ns'], event['closed_ns']),
               'request_server_RPC_ms': ms(meter['request_received_ns'], meter['reply_completed_ns']),
               'request_client_RPC_ms': ms(receipt['started_ns'], receipt['closed_ns']),
               'request_end_to_publication_ms': ms(event['closed_ns'], published['published_ns'])}
    require(result['ready_ns'] <= event['started_ns'] <= event['closed_ns'] <= result['cleanup_started_ns']
            <= published['published_ns'] < result['owned_deadline_ns'] and
            event['closed_ns'] < result['task_deadline_ns'], 'qualification_original_deadline_or_clock_binding')
    return reply, event, meter, wire, timings


def verify_available_result(slot, reply, event, meter, installed, terminal, truth, outcome):
    public, texts, images = PIXEL['typed']['verify_content'](reply, contract='active_region_task')
    raw_text, = texts
    archive = event['producer_archive']
    raw = verified(archive['path'], archive['sha256'], slot)
    require(archive['index'] == 1 and archive['new_observations_for_archive'] == 0,
            'producer_archive_not_same_request')
    producer = json.loads(raw)
    audit = rows(slot / 'product_audit.jsonl')
    trace, = [row for row in audit if row['event'] == 'request_trace' and
              row['trace']['annotations'].get('mcp_request_id') == event['request']['id']]
    relevant = [row for row in audit if row.get('request_id') == trace['request_id']]
    formatter, = [row['image_delivery'] for row in relevant if row['event'] == 'active_observation_mcp_content']
    attempts = [row for row in relevant if row['event'] == 'active_observation_render_attempt']
    frames, selected = producer['constructed_frames'], producer['frames']
    require(len(attempts) == len(frames) == meter['raster_actual'] <= 6 and
            formatter['projection_status'] == 'brief' and raw_text['UTF8_bytes'] == formatter['public_text_bytes'] and
            formatter['native_blocks_constructed'] == len(selected) == len(images) and
            formatter['PNG_bytes'] == sum(len(data) for _, data in images) and
            all(row['identity_check']['compatible'] is True for row in relevant), 'actual_brief_or_raster_audit_changed')
    outcome['wire'].update(body_UTF8_bytes=raw_text['UTF8_bytes'], body_sha256=raw_text['UTF8_sha256'],
                           producer_archive_bytes=len(raw), producer_archive_sha256=digest(raw),
                           PNG_bytes=formatter['PNG_bytes'])
    outcome['timing'].update(archive_producer_snapshot_ms=ms(archive['producer_returned_ns'], archive['saved_ns']),
        formatting_ms=stage_ms(formatter),
        producer_stages_ms={key: stage_ms(value) for key, value in producer['stages'].items()})
    outcome['work'] = producer['work']
    outcome['images'] = [item for item, _ in images]
    outcome['CLI'] = replay(reply['result'], public, images, outcome['cli_path'])
    binding = producer['binding']
    require(public['read_only'] is producer['read_only'] is True and
            public['execution_authority'] is producer['execution_authority'] is False and
            public['status'] == producer['status'] == 'complete' and
            public['observation_status'] == producer['observation_status'] == 'region_task_observed' and
            public['session_id'] == producer['session_id'] and public['binding'] ==
            {key: item for key, item in binding.items()
             if key not in ('schema', 'objects', 'camera_policy', 'camera_specification')},
            'public_body_is_not_the_same_current_read_only_producer_result')
    source_audit = capture_check['Audit']()
    captures, _ = capture_check['decode_captures'](slot, installed, source_audit)
    capture = capture_check['current_capture'](captures, binding, source_audit)
    capture_check['source_binding_checks'](capture, binding, installed, source_audit)
    terminal_by_name = {row['name']: row for row in terminal['objects']}
    require(len(capture['meshes']) == len(terminal_by_name) and
            {mesh['name'] for mesh in capture['meshes']} == set(terminal_by_name), 'product_capture_roster_differs')
    for mesh in capture['meshes']:
        original = terminal_by_name[mesh['name']]
        require(mesh['object_id'] == original['object_id'] and
                capture['host_identity']['object_instances'][mesh['object_id']] == original['instance_id'] and
                mesh['faces'] == original['evaluated']['triangles'] and
                mesh['vertices'] == original['evaluated']['vertices_world_m'], 'product_source_not_current/' + mesh['name'])
    task = producer['facts']['region_task']
    original_rows = {region_key(row): row for row in task['rows']}
    public_rows = {region_key(row): row for row in public['region_task']['rows']}
    true_rows = {region_key(row): row for row in truth['eligible']}
    outcome['raw_roster'] = {key: [region_label(label) for label in roster] for key, roster in
                            (('truth', true_rows), ('producer', original_rows), ('brief', public_rows))}
    require(len(true_rows) == len(truth['eligible']) == len(original_rows) == len(task['rows']) ==
            len(public_rows) == len(public['region_task']['rows']) and
            set(true_rows) == set(original_rows) == set(public_rows) and
            public['region_task']['summary'] == task['summary'] and
            public['region_task']['conditions'] == task['conditions'] == REQUEST['query']['region_task'],
            'raw_exact_task_roster_or_conditions_differs')
    measure_evidence(slot, truth, selected, frames, images, binding, source_audit,
                     producer['scopes'], original_rows, public_rows, true_rows, terminal, capture, outcome)


def measure_evidence(slot, truth, selected, frames, images, binding, audit, scopes, original_rows, public_rows,
                     true_rows, terminal, capture, outcome):
    by_scope = {row['scope_id']: row for row in scopes}
    require(len(by_scope) == len(scopes) and by_scope['global']['binding'] == binding and
            all(scope is not None for scope in (by_scope.get(frame['scope_id']) for frame in frames)),
            'raw_frame_and_capture_scopes_differ')
    by_ref = {item['ref']: (item, raw) for item, raw in images}
    terminal_objects = {obj['name']: obj for obj in terminal['objects']}
    require(list(by_ref) == [frame['image_ref'] for frame in selected], 'raw_selected_image_order_different')
    scope_target = {}
    for scope, value in by_scope.items():
        expected = [frame['frame_identity'] for frame in frames if frame['scope_id'] == scope]
        require(expected == value['frame_refs'] ==
                [row['frame_identity'] for row in value['facts']['observations']], 'raw_scope_observation_order_different')
        if scope != 'global':
            source = value['binding']['region_source']
            target = binding['objects'][source['object_index']]['object_name']
            key = target, tuple(source['source_triangle_indices'])
            scope_target[scope] = key
            capture_check['local_binding_checks'](value, binding, original_rows[key]['source'], audit)
    # The reused frame reviewer indexes per object. Split same-object panels
    # into batches so each independent rectangle retains its source address.
    truth_by_occurrence = []
    counts = Counter()
    for key, target in true_rows.items():
        name, _ = key
        ordinal = counts[name]
        if ordinal == len(truth_by_occurrence):
            truth_by_occurrence.append([])
        truth_by_occurrence[ordinal].append(target)
        counts[name] += 1
    observed = {}
    for frame in frames:
        scope = by_scope[frame['scope_id']]
        raw_png = by_ref.get(frame['image_ref'], (None, None))[1]
        all_pixels = {}
        for batch in truth_by_occurrence:
            measurement = prior['frame_payload'](slot, frame, scope, terminal, {**truth, 'eligible': batch}, raw_png)
            all_pixels.update({region_label(region_key(target)): measurement['independent_pixels'][target['object_name']]
                               for target in batch})
        measurement['independent_pixels'] = all_pixels
        require(frame['image_ref'] not in observed, 'raw_duplicate_frame_reference')
        observed[frame['image_ref']] = measurement
    outcome['frames'] = list(observed.values())
    outcome['original_regions'] = {}
    positives = set()
    blocked = 0
    for key, target in true_rows.items():
        name, _ = key
        label = region_label(key)
        row, shown = original_rows[key], public_rows[key]
        normalized = dict(shown)
        witness = normalized['complete_witness']
        if witness is not None:
            normalized['complete_witness'] = {key: item for key, item in witness.items()
                                              if key != 'native_content_block_index'}
        shortfall = normalized.pop('pixel_shortfall', None)
        require(normalized == row and row['source'] == capture_check['source_row'](target, capture, binding),
                'raw_exact_source_row_differs/' + label)
        geometry = prior['same_geometry'](row, target, terminal_objects[name], binding)
        probes = [item for item in observed.values() if item['scope_id'] == 'global'
                  or scope_target[item['scope_id']] == key]
        found = {item['ref'] for item in probes if item['independent_pixels'][label]['qualifies']}
        if witness:
            ref = witness['image_ref']
            image = by_ref.get(ref)
            require(row['status'] == 'covered' and row['reason'] == 'observed_readable' and ref in found and
                    witness['frame_identity'] == observed[ref]['frame_identity'] and
                    witness['scope_id'] == observed[ref]['scope_id'] and witness['view_name'] == observed[ref]['view'],
                    'raw_complete_witness_does_not_match_current_finite_view_and_pixels/' + label)
            if image is None or witness['native_content_block_index'] != image[0]['content_index']:
                outcome['issues'].append('actual_readable_region_PNG_not_delivered/' + label)
            else:
                normal = [Fraction(value) for value in target['unit_normal']]
                positives.add('top' if normal[2] > 0 else 'side')
            scope = by_scope[witness['scope_id']]
            observation, = [item for item in scope['facts']['observations']
                            if item['frame_identity'] == witness['frame_identity']]
            pixel = observation['pixel_rows'][witness['pixel_row_index']]
            independent = observed[ref]['independent_pixels'][label]
            require(pixel['roi_id'] == row['roi_id'] and
                    pixel['visible_surface_pixels'] == independent['target_surface_pixels'] and
                    pixel['contrasting_boundary_pixels'] == independent['contrasting_boundary_pixels'],
                    'actual_witness_misstates_independent_RGB_owners/' + label)
        else:
            require(row['status'] == 'unknown' and not found, 'raw_unknown_has_complete_witness/' + label)
            if not target['eligible_complete_views']:
                occluded = {view for view, proof in target['finite_direction_proofs'].items()
                            if proof['status'] == 'positive_area_occlusion'}
                require(row['reason'] == 'positive_area_occlusion_all_front_views' and
                        set(row['view_reasons'].get('positive_area_occlusion', [])) == occluded and occluded,
                        'raw_geometric_unknown_not_tied_to_independent_occlusion/' + label)
                blocked += 1
            else:
                require(row['reason'] in ('pixel_evidence_insufficient', 'unobserved_geometric_candidates'),
                        'raw_pixel_or_unobserved_unknown_conflates_geometric_blocking/' + label)
        if shortfall is not None:
            matched = [probe for probe in probes if probe['scope_id'] == shortfall['scope_id'] and
                       probe['view'] == shortfall['view_name']]
            require(len(matched) == 1 and row['reason'] == 'pixel_evidence_insufficient' and
                    shortfall['view_name'] in target['eligible_complete_views'],
                    'raw_pixel_shortfall_missing_geometrically_clear_scope_frame/' + label)
            probe = matched[0]
            pixel = probe['independent_pixels'][label]
            attached = by_ref.get(probe['ref'])
            index = None if attached is None else attached[0]['content_index']
            require(shortfall['visible_surface_pixels'] == pixel['target_surface_pixels'] and
                    shortfall['contrasting_boundary_pixels'] == pixel['contrasting_boundary_pixels'] and
                    (shortfall['minimum_surface_pixels'], shortfall['minimum_boundary_pixels'],
                     shortfall['minimum_rgb_boundary_contrast']) == (16, 4, 24) and
                    shortfall['native_content_block_index'] == index and
                    shortfall['image_delivered'] is (index is not None), 'raw_pixel_shortfall_binding_differs/' + label)
        outcome['original_regions'][label] = {'geometry': geometry, 'complete_witness': witness,
            'view_reasons': row['view_reasons'], 'pixel_shortfall': shortfall,
            'independent_complete_views': target['eligible_complete_views'],
            'measured_pixels': {item['ref']: item['independent_pixels'][label] for item in probes}}
    outcome['independent_actual_positive_axes'] = sorted(positives)
    outcome['proven_geometric_unknowns'] = blocked
    if positives != {'top', 'side'} or blocked == 0:
        outcome['issues'].append('missing_top_side_positive_or_independent_occlusion_negative')


def qualify(runtime, truth_path, freeze_path, outcome):
    slot = runtime / 'slots/QP'
    result_path = slot / 'SLOT_RESULT.json'
    publication_path = slot / 'SLOT_PUBLICATION.json'
    truth = read(truth_path)
    require(truth['asset_sha256'] == ASSET_SHA and read(NS / 'inputs/REQUEST.json') == REQUEST,
            'fixed_independent_truth_or_request_changed')
    result = read(result_path)
    published = read(publication_path)
    started = read(slot / 'SLOT_STARTED.json')
    freeze = digest(freeze_path.read_bytes())
    outcome.update(freeze_sha256=freeze, independent_truth_sha256=digest(truth_path.read_bytes()),
                   slot_result_sha256=digest(result_path.read_bytes()),
                   publication_sha256=digest(publication_path.read_bytes()),
                   owned_slot_status=published['status'], original_slot_errors=result.get('errors', []),
                   denominator=result.get('budget', {}).get('counts', {}))
    require(all(record['label'] == 'QP' for record in (started, result, published)) and
            published['result_sha256'] == outcome['slot_result_sha256'] and
            started['freeze_sha256'] == result['freeze_sha256'] == freeze and
            result['asset_sha256'] == ASSET_SHA and result['model_consumers'] == result['paid_API_calls'] == 0 and
            result['product_source_sha256'] == PRODUCT_SHA, 'sole_original_qualification_binding_invalid')
    if published['status'] != 'completed':
        outcome['issues'].append('owned_product_slot_failed_before_qualification')
        archived_response = slot / 'product_calls/call_001/RESPONSE.json'
        if archived_response.is_file():
            reply, _, _, outcome['wire'], outcome['timing'] = audit_wire(slot, started, result, published)
            returned = reply.get('result', {})
            texts = [block['text'] for block in returned.get('content', []) if block.get('type') == 'text']
            outcome['actual_error_response'] = {'isError': returned.get('isError'), 'JSON_RPC_error': reply.get('error'),
                'text_blocks': [{'bytes': len(value.encode()), 'sha256': digest(value.encode()), 'prefix': value[:300]}
                                for value in texts]}
        return
    require(result['status'] == 'completed' and not result['errors'] and
            published['owned_budget_passed'] is True, 'owned_qualification_close_or_budget_not_confirmed')
    counts = outcome['denominator']
    require(counts['Blender_start_attempts'] == counts['business_admissions'] == 1 and
            counts['consumer_admissions'] == 0 and 0 <=
            counts['all_raster_actual'] == counts['all_raster_upper'] <= 6, 'registered_qualification_denominator_exceeded')
    installed = read(BINDING)
    sys.path.insert(0, installed['dependency_root'])
    identity, ready = [read(slot / name) for name in ('MCP_IDENTITY.json', 'RUNTIME_READY.json')]
    require(identity['source_kind'] == 'installed_distribution' and identity['source_file_count'] == 143 and
            identity['source_sha256'] == installed['source_sha256'] == ready['product_source_sha256'] == PRODUCT_SHA and
            result['product_binding_sha256'] == digest(BINDING.read_bytes()), 'actual_product_install_identity_differs')
    closed = read(slot / 'RUNTIME_CLOSE.json')
    exit_ = closed['public_MCP_exit']
    require(not closed['errors'] and exit_['exited'] and exit_['confirmed'] and exit_['handle_closed'] and
            exit_['exit_code'] == 0, 'actual_MCP_exit_unconfirmed')
    terminal, outcome['current_source'] = current_source(slot, result)
    reply, event, meter, outcome['wire'], outcome['timing'] = audit_wire(slot, started, result, published)
    verify_available_result(slot, reply, event, meter, installed, terminal, truth, outcome)
    if not outcome['CLI']['passed']:
        outcome['issues'].append('fixed_CLI_replay_lost_required_facts_or_original_images')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--truth', type=Path, default=NS / 'truth/CURRENT_TRUTH.json')
    parser.add_argument('--freeze', type=Path, default=NS / 'FROZEN.json')
    parser.add_argument('--output', type=Path, default=HERE / 'QUALIFICATION_QP.json')
    args = parser.parse_args()
    started = time.perf_counter_ns()
    outcome = {'schema': 'm4-dense-panel-sweep-QP-qualification-v1', 'label': 'QP', 'issues': [],
               'runtime_source_sha256': PRODUCT_SHA, 'cli_path': args.runtime / 'preflight/product_cli'}
    try:
        qualify(args.runtime, args.truth, args.freeze, outcome)
    except Exception as error:
        outcome['issues'].append('product_or_qualification_semantic_evidence_failed')
        outcome['error'] = {'type': type(error).__name__, 'message': str(error)}
    outcome['cli_path'] = str(outcome['cli_path'])
    outcome['passed'] = not outcome['issues']
    outcome['reason'] = 'qualified' if outcome['passed'] else outcome['issues'][0]
    outcome['assessment_ms'] = ms(started, time.perf_counter_ns())
    write(args.output, outcome)
    print(json.dumps({key: outcome.get(key) for key in ('passed', 'reason', 'issues', 'error', 'wire',
                     'denominator', 'independent_actual_positive_axes')}, ensure_ascii=False))
    raise SystemExit(0 if outcome['passed'] else 1)


if __name__ == '__main__':
    main()
