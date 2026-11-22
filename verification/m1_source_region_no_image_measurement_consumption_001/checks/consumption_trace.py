"""Audit natural measurement exposure, repeat work and costs from closed formal slots."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
RUNTIME = Path('D:/he_m1_source_region_no_image_measurement_consumption_001')
ASSET = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
TOOL = 'human_eye_scene_observe'
FACT = 'surface_proximity'
FULL = 'human-eye-source-region-observation-v1'
BRIEF = 'source-region-brief-v2'
GUIDE = 'response_detail=full on the standard endpoint'
SCOPE = 'complete_selected_source_triangle_union_to_reference_triangle_surface'
TARGET, REFERENCE = 'M15', 'M14'
FACES = [6, 7]
LABELS = ('A1', 'B1')
COSTS = V / 'perf050_readonly_product_pilot_001/consumer/costs.py'
PRODUCT_SOURCES = {
    'A1': 'cdee32540b54f3278619305b23f28a646dba90d80212708ed3baf928514e2acd',
    'B1': '338f4841654335fb6b567ae3ccba214bf370717925c6abe5592984c23b2905ac',
}


def read(path):
    return json.loads(path.read_bytes()) if path.is_file() else {}


def raw_sha(data):
    return sha256(data).hexdigest()


def fingerprint(value):
    return raw_sha(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def checked(path, digest):
    raw = path.read_bytes()
    require(raw_sha(raw) == digest, 'wrong_original_artifact_digest/' + path.name)
    return raw


def inside(slot, path):
    path = Path(path).resolve(strict=True)
    require(path.is_relative_to(slot), 'artifact_belongs_to_different_slot/' + path.name)
    return path


def snapshot(slot, result):
    sources = {}
    for key, relative in (('initial_source', 'initial_capture/TERMINAL_SOURCE.json'),
                          ('terminal_source', 'TERMINAL_SOURCE.json')):
        reference = result[key]
        path = inside(slot, reference['path'])
        require(path == (slot / relative).resolve() and reference['status'] == 'complete'
                and reference['terminal'] is True, 'same_closed_source_required/' + key)
        sources[key] = json.loads(checked(path, reference['sha256']))
    before, after = sources.values()
    require(all(before[key] == after[key] for key in
                ('objects', 'source', 'source_face_offsets', 'display_object_mask')),
            'initial_and_terminal_sources_differ')
    require(after['source']['asset_sha256'] == result['asset_sha256'] == ASSET,
            'terminal_source_asset_mismatch')
    objects = {obj['name']: obj for obj in after['objects']}
    require(len(objects) == len(after['objects']) == 21 and {TARGET, REFERENCE} <= objects.keys(),
            'unexpected_current_object_roster')
    return objects


def selected_name(selector, objects):
    if not isinstance(selector, dict) or len(selector) != 1 or type(next(iter(selector.values()))) is not str:
        return None
    if 'name' in selector:
        return selector['name'] if selector['name'] in objects else None
    if 'id' in selector:
        return next((name for name, row in objects.items() if row['object_id'] == selector['id']), None)
    return None


def requested_scope(tool, arguments, objects):
    if tool != TOOL or not isinstance(arguments, dict):
        return None
    query = arguments.get('query')
    if not isinstance(query, dict):
        return None
    if query.get('mode') == 'source_region' and selected_name(query.get('reference'), objects) == REFERENCE:
        region, ref = query.get('region'), query.get('region_ref')
        if isinstance(region, dict):
            ids = region.get('source_triangle_indices')
            target = selected_name(region.get('object'), objects)
            via = 'explicit_region'
        elif isinstance(ref, dict):
            ids = ref.get('source_triangle_indices')
            target = next((name for name, row in objects.items()
                           if (row['object_id'], row['instance_id']) == (ref.get('host_id'), ref.get('instance_id'))), None)
            via = 'current_region_ref'
        else:
            return None
        if target == TARGET and type(ids) is list and all(type(i) is int for i in ids) and sorted(ids) == FACES:
            return {'scope': 'selected_region', 'via': via, 'order': [TARGET, REFERENCE],
                    'source_triangle_indices': FACES, 'sole_surface_proximity': query.get('requested_facts') == [FACT]}
        return None
    mode = query.get('mode')
    pair = query if mode == 'task' else query.get('task_query') if mode == 'active_observation' else None
    if (not isinstance(pair, dict) or type(pair.get('requested_facts')) is not list
            or FACT not in pair['requested_facts'] or type(pair.get('objects')) is not list):
        return None
    names = [selected_name(key, objects) for key in pair['objects']]
    if names in ([TARGET, REFERENCE], [REFERENCE, TARGET]):
        return {'scope': 'whole_objects', 'order': names,
                'via': 'ordered_pair' if mode == 'task' else 'embedded_ordered_pair'}
    return None


def checked_product(slot, outer_request, outer_response, product_row):
    request_path = inside(slot, product_row['request_file']['path'])
    request = json.loads(checked(request_path, product_row['request_file']['sha256']))
    response_link = product_row['response_file']
    require(response_link is not None, 'missing_installed_product_response_receipt')
    response_path = inside(slot, response_link['path'])
    response = json.loads(checked(response_path, response_link['sha256']))
    # CLI correlation metadata belongs to the outer envelope, not tool arguments.
    require(request['params'] == {key: outer_request['params'][key] for key in ('name', 'arguments')}
            and response['result'] == outer_response['result'],
            'natural_tool_parameters_or_content_changed_in_forwarding')
    producer_id = product_row.get('producer_archive')
    # Invalid requests and normal product errors may return before creating a producer.
    envelope = next(row for line in (slot / 'PUBLIC_REQUESTS.jsonl').read_bytes().splitlines()
                    if line.strip() and (row := json.loads(line))['request']['id'] == request['id'])
    receipt = envelope['receipt']
    wire = slot / 'mcp' / f'rpc_{receipt["index"]:02d}'
    tx, rx = ((wire / file).read_bytes() for file in ('TX.bin', 'RX.bin'))
    require(request == json.loads(tx) == envelope['request'] and response == json.loads(rx) == envelope['response']
            and len(tx) == receipt['TX_bytes'] and len(rx) == receipt['RX_bytes']
            and receipt['RX_sha256'] == raw_sha(rx), 'actual_installed_product_wire_binding_differed')
    proof = {'TX_sha256': raw_sha(tx), 'RX_sha256': raw_sha(rx), 'TX_bytes': len(tx), 'RX_bytes': len(rx),
             'wire_index': receipt['index'], 'wire_root': wire.as_posix()}
    producer = None
    if producer_id is not None:
        require(producer_id == envelope['producer_archive'], 'same_invocation_producer_archive_changed')
        path = inside(slot, producer_id['path'])
        producer = json.loads(checked(path, producer_id['sha256']))
        proof['producer'] = {'path': path.as_posix(), 'sha256': producer_id['sha256'], 'index': producer_id['index']}
    return proof, producer


def selected_geometry_digest(binding, objects):
    by_host = {obj['object_id']: obj for obj in objects.values()}
    bound = binding['objects']
    require(len(bound) == len(by_host) and {row['host_id'] for row in bound} == by_host.keys()
            and all(row['object_name'] == by_host[row['host_id']]['name']
                    and row['instance_id'] == by_host[row['host_id']]['instance_id'] for row in bound),
            'complete_selected_geometry_roster_changed')
    return fingerprint([{'host_id': row['host_id'], 'instance_id': row['instance_id'],
                         'vertices': by_host[row['host_id']]['evaluated']['vertices_world_m'],
                         'faces': by_host[row['host_id']]['evaluated']['triangles']} for row in bound])


def observed_measurement(scope, producer, body, objects, request, image_blocks):
    scope_type = scope['scope']
    if scope_type == 'selected_region':
        require(producer['result_kind'] == 'source_region' and body.get('schema') in (FULL, BRIEF),
                'selected_request_used_different_result_contract')
        value = producer['task_result']
        actual = body['task_result']
        ref = producer['region_ref']
        region = producer['facts']['region']
        target, reference = (objects[name] for name in scope['order'])
        require(region['object_name'] == TARGET and region['source_triangle_indices'] == FACES
                and (ref['host_id'], ref['instance_id']) == (target['object_id'], target['instance_id'])
                and ref['source_triangle_indices'] == FACES and ref == value['region_ref'] == body['region_ref'],
                'selected_measurement_was_bound_to_different_source_rows')
        require((value['reference']['name'], value['reference']['object_id'], value['reference']['instance_id'])
                == (REFERENCE, reference['object_id'], reference['instance_id'])
                and actual['reference'] == value['reference']
                and actual['measurement_scope'] == value['measurement_scope'] == SCOPE
                and actual['facts'] == value['facts'] and actual['status'] == value['status'],
                'selected_measurement_reference_scope_or_facts_changed')
        if scope['via'] == 'current_region_ref':
            require(request['query']['region_ref'] == ref, 'returned_region_ref_is_not_requested_current_selection')
        require(actual['source_mapping']['nearest_witness'] == value['source_mapping']['nearest_witness'],
                'selected_measurement_witness_mapping_changed')
        binding = producer['binding']
        capture = binding.get('capture_state')
        require(isinstance(capture, dict) and all(ref['capture_generation'][key] == capture[key]
                    for key in ('instance_id', 'epoch', 'revision'))
                and ref['document_epoch'] == binding['document_epoch']
                and ref['ordered_geometry_sha256'] == selected_geometry_digest(binding, objects)
                and ref['region_id'] == 'source-region:' + fingerprint(
                    {key: value for key, value in ref.items() if key != 'region_id'}),
                'selected_measurement_not_same_capture_generation')
        evidence = value['source_mapping']['nearest_witness']
        measurement = actual['facts'][FACT]
        measured = (producer['status'] == value['status'] == 'complete' and measurement['status'] == 'measured'
                    and all(evidence[key]['status'] == 'measured' and evidence[key]['exact_membership'] is True
                            for key in ('a', 'b')))
        if measured:
            require(bool(evidence['a']['source_triangle_indices'])
                    and set(evidence['a']['source_triangle_indices']) <= set(FACES)
                    and bool(evidence['b']['source_triangle_indices'])
                    and all(type(i) is int and 0 <= i < len(reference['evaluated']['triangles'])
                            for i in evidence['b']['source_triangle_indices']),
                    'measured_surface_witness_escaped_requested_selection_or_reference')
        return {'measurement_status': measurement['status'], 'complete_scope_measurement': measured,
                'fact': measurement, 'source_mapping': evidence, 'region_ref': ref,
                'canonical_measurement_signature': fingerprint([ref, measurement, evidence]),
                'full_face_mapping_present': 'region' in actual['source_mapping'],
                'image_not_requested': producer['observation_status'] == 'image_not_requested'
                and producer['frames'] == [] and not producer.get('constructed_frames') and image_blocks == 0,
                'packet_kind': 'brief' if body['schema'] == BRIEF else 'full',
                'standard_endpoint_diagnostics_guide': body.get('details') == GUIDE}

    # Order is preserved here. The independent answer scorer handles reversal of
    # direction and endpoints, as well as any proven equivalent native solution.
    embedded = scope['via'] == 'embedded_ordered_pair'
    original = producer['task_result'] if embedded else producer
    actual = body['task_result'] if embedded else body
    binding = original['binding']
    require(original['result_kind'] == actual['result_kind'] == 'task_query'
            and original['pair_order'] == actual['pair_order'] == 'A_to_B'
            and original['facts'][FACT] == actual['facts'][FACT], 'whole_control_result_is_not_same_ordered_fact')
    expected = [(name, objects[name]['object_id']) for name in scope['order']]
    require([(row['name'], row['object_id']) for row in binding['objects']] == expected,
            'whole_control_result_is_not_requested_object_pair')
    if embedded:
        require(binding['observation_source']['measurement_scope'] == 'whole_objects',
                'embedded_control_result_is_not_whole_object_scope')
    measured = actual['facts'][FACT]
    return {'measurement_status': measured['status'], 'complete_scope_measurement': measured['status'] == 'measured',
            'fact': measured, 'canonical_measurement_signature': fingerprint(measured)}


def analyze_attempt(slot, row, objects, contracts):
    request_file = inside(slot, row['stdio_TX']['path'])
    request = json.loads(checked(request_file, row['stdio_TX']['sha256']))
    args = row.get('arguments')
    flags = args if isinstance(args, dict) else {}
    result = {'attempt': row['attempt'], 'tool': row['tool'], 'requested_detail': flags.get('response_detail', 'omitted'),
              'explicit_no_image': flags.get('include_image') is False,
              'classification': 'no_returned_tool_evidence', 'wire_error': row['wire_content']['error'],
              'delivered_PNG_sha256': [image['sha256'] for image in row['wire_content']['PNG']],
              'wire_text_bytes': row['wire_content']['text_bytes'],
              'wire_PNG_bytes': sum(image['bytes'] for image in row['wire_content']['PNG']),
              'CLI_delivered_text_bytes': row['CLI_delivered_text_bytes'],
              'original_public_TX': row['stdio_TX'], 'original_public_RX': row['stdio_RX'],
              'tool_wire_RTT_ms': row['tool_wire_RTT_ms'],
              'dispatch_to_CLI_result_ms': row['dispatch_to_CLI_result_ms'],
              'requested_scope': requested_scope(row['tool'], args, objects) if objects else None}
    require(request['method'] == 'tools/call' and request['params'].get('arguments') == args,
            'original_outer_tool_arguments_changed')
    if row['stdio_RX'] is None:
        return result
    response_file = inside(slot, row['stdio_RX']['path'])
    response = json.loads(checked(response_file, row['stdio_RX']['sha256']))
    require(request['id'] == response['id'], 'outer_request_response_id_mismatch')
    if row['origin'] == 'owner':
        owner = slot / 'owner' / f'tool_{row["attempt"]:02d}'
        require(read(owner / 'REQUEST.json') == request and read(owner / 'RESPONSE.json') == response,
                'original_authorized_owner_request_or_response_differs')
    contract = contracts.get(row['attempt'])
    result['bound_public_CLI_reply'] = bool(contract and contract['matched'] is True
        and contract['TX_sha256'] == row['stdio_TX']['sha256'] and contract['RX_sha256'] == row['stdio_RX']['sha256']
        and type(contract.get('CLI_received_ns')) is int)
    result['CLI_match_reason'] = contract.get('reason') if contract else None
    producer = None
    if row['product'] is not None:
        result['inner_wire'], producer = checked_product(slot, request, response, row['product'])
    if 'error' in response:
        result['classification'] = 'original_protocol_rejection'
        return result
    output = response['result']
    if output.get('isError') is True:
        result['classification'] = 'original_tool_rejection'
    elif result['requested_scope'] and producer is not None:
        require(output['content'][0]['type'] == 'text', 'first_public_measurement_block_should_be_JSON_text')
        body = json.loads(output['content'][0]['text'])
        if body.get('status') not in ('complete', 'observed', 'unknown', 'partial'):
            result['classification'] = 'returned_unproven_measurement'
            return result
        observed = observed_measurement(result['requested_scope'], producer, body, objects, args,
                                        len(row['wire_content']['PNG']))
        result['observed'] = observed
        result['classification'] = ('bound_' + result['requested_scope']['scope'] + '_measurement'
                                    if observed['complete_scope_measurement'] and result['bound_public_CLI_reply']
                                    else 'returned_unproven_measurement')
        result['task_result_cache_hit'] = (row['product'].get('new_work') or {}).get('task_query', {}).get('result_cache_hit')
    elif row['tool'] in ('execute_python', 'execute_blender_code'):
        result['classification'] = 'ordinary_read_or_calculation_content_review_required'
        result['ordinal_and_original_reply_for_independent_classification'] = {
            'attempt': row['attempt'], 'public_reply_file': row['stdio_RX']}
    else:
        result['classification'] = 'other_successful_tool_delivery'
    return result


def scope_events(rows):
    selected = [row for row in rows if (row.get('requested_scope') or {}).get('scope') == 'selected_region']
    confirmed = [row for row in rows if row['classification'] == 'bound_selected_region_measurement']
    exact = [row for row in confirmed if row['explicit_no_image'] and row['requested_scope']['sole_surface_proximity']
             and row['observed']['image_not_requested']]
    repeats, additional, repeats_with_evidence = [], [], []
    seen, mapped, images = set(), set(), set()
    for row in rows:
        pngs = set(row.get('delivered_PNG_sha256', ()))
        new_images = sorted(pngs - images)
        images.update(pngs)
        if row['classification'] != 'bound_selected_region_measurement':
            continue
        observed = row['observed']
        key = observed['canonical_measurement_signature']
        new_mapping = observed['full_face_mapping_present'] and key not in mapped
        if key in seen:
            repeat = {'attempt': row['attempt'], 'cache_hit': row['task_result_cache_hit'],
                      'requested_detail': row['requested_detail'], 'packet_kind': observed['packet_kind']}
            if new_images or new_mapping:
                repeats_with_evidence.append({**repeat, 'new_PNG_sha256': new_images,
                                              'new_full_face_mapping': new_mapping})
            else:
                repeats.append(repeat)
        elif seen:
            additional.append({'attempt': row['attempt'], 'reason': 'same_range_different_capture_fact_or_witness'})
        if observed['full_face_mapping_present']:
            mapped.add(key)
        seen.add(key)
    return {'first_selected_request': selected[0] if selected else None,
            'first_selected_measured_reply': confirmed[0] if confirmed else None,
            'first_explicit_no_image_reply': exact[0] if exact else None,
            'repeated_same_scope_fact': repeats, 'same_scope_distinct_fact_review': additional,
            'same_scope_fact_with_additional_PNG_or_full_mapping': repeats_with_evidence,
            'selected_bound_attempts': [row['attempt'] for row in confirmed],
            'legitimate_ordered_whole_control_attempts': [row['attempt'] for row in rows
                                                         if row['classification'] == 'bound_whole_objects_measurement']}


def totals(account):
    attempts = account['actual_requests']
    usage = account['raw_CLI_usage']
    usage = usage[0] if len(usage) == 1 else {}
    clocks = account['clock_ms']
    raster_claims = [row for row in (account.get('budget') or {}).get('records', [])
                     if row['claim']['kind'] == 'raster_attempt' and row['claim']['label'] == account['label']]
    actual_rasters = [(row.get('settlement') or {}).get('actual_attempts') for row in raster_claims]
    return {
        'business_attempts': len(attempts), 'tool_rejections': sum(row['wire_content']['error'] for row in attempts),
        'raster_attempts_reserved': sum(row['claim']['reserved_upper_bound'] for row in raster_claims),
        'raster_attempts_confirmed': sum(actual_rasters) if all(type(value) is int for value in actual_rasters) else None,
        'actually_delivered_images': sum(len(row['wire_content']['PNG']) for row in attempts),
        'outer_TX_bytes': sum(row['stdio_TX']['bytes'] for row in attempts),
        'outer_RX_bytes': sum((row['stdio_RX'] or {}).get('bytes', 0) for row in attempts),
        'tool_wire_text_bytes': account['tool_wire_text_total_bytes'], 'tool_wire_PNG_bytes': account['tool_wire_PNG_bytes'],
        'CLI_input_tokens': usage.get('input_tokens'), 'CLI_cached_input_tokens': usage.get('cached_input_tokens'),
        'CLI_output_tokens': usage.get('output_tokens'), 'CLI_input_plus_output_tokens': account['input_plus_output_tokens'],
        'tool_wire_RTT_total_ms': sum(row['tool_wire_RTT_ms'] for row in attempts if row['tool_wire_RTT_ms'] is not None),
        'tool_dispatch_to_CLI_total_ms': sum(row['dispatch_to_CLI_result_ms'] for row in attempts
                                           if row['dispatch_to_CLI_result_ms'] is not None),
        'complete_slot_ms': clocks['full_window'], 'prompt_to_final_ms': clocks['prompt_to_final'],
        'tool_gap_total_ms': clocks['between_tool_wait'],
    }


def analyze_slot(slot, freeze_sha256=None, prompt_sha256=None):
    slot = Path(slot).resolve()
    account = run_path(str(COSTS))['summarize'](slot, freeze_sha256)
    if not slot.is_dir():
        return {**account, 'formal_slot_created': False}
    result = read(slot / 'SLOT_RESULT.json')
    public = read(slot / 'consumer/BUSINESS_SOURCE_BINDING.json')
    contracts = {row['attempt']: row for row in public.get('result_contracts', [])}
    failures = []
    objects = {}
    if result.get('status') == 'completed':
        try:
            objects = snapshot(slot, result)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            failures.append(str(exc))
        if prompt_sha256 and account['initial_prompt_sha256'] != prompt_sha256:
            failures.append('formal_prompt_does_not_bind_frozen_common_bytes')
    traced = []
    for row in account.get('actual_requests', []):
        try:
            traced.append(analyze_attempt(slot, row, objects, contracts))
        except (KeyError, OSError, IndexError, StopIteration, TypeError, ValueError) as exc:
            failures.append(f'tool_{row["attempt"]}: {exc}')
            traced.append({'attempt': row['attempt'], 'tool': row['tool'], 'classification': 'unverified_tool_evidence',
                           'error': str(exc)})
    return {**account, 'formal_slot_created': True, 'product_source_sha256': result.get('product_source_sha256'),
            'scope_trace_errors': failures, 'scope_trace': traced,
            'measurement_events': scope_events(traced), 'totals': totals(account)}


def analyze_pair(root=RUNTIME, quality=None):
    root = Path(root)
    freeze_path = NS / 'FROZEN.json'
    freeze = read(freeze_path)
    token = raw_sha(freeze_path.read_bytes()) if freeze else None
    slots = {label: analyze_slot(root / 'slots' / label, token, freeze.get('prompt_sha256')) for label in LABELS}
    complete = all(row['status'] == 'completed' and row.get('cost_evidence_verified') is True
                   and not row.get('scope_trace_errors') for row in slots.values())
    profiles = [row.get('requested_consumer_configuration') or {} for row in slots.values()]
    fixed_products = all(slots[label].get('product_source_sha256') == PRODUCT_SOURCES[label] for label in LABELS)
    fixed_model = all((p.get('requested_model'), p.get('requested_effort'), p.get('requested_service_tier'))
                      == ('gpt-6.1-sol', 'medium', 'default') for p in profiles)
    cli_paths = [p.get('requested_cli_overrides_and_argv', []) for p in profiles]
    fixed_cli = all(argv and any(part.startswith('0.152.1-') for part in Path(argv[0]).parts) for argv in cli_paths)
    select = [row.get('measurement_events', {}).get('first_selected_measured_reply') for row in slots.values()]
    a, b = select
    first_current = a and b and all(row['explicit_no_image'] and row['requested_scope']['sole_surface_proximity']
                                   and row['observed']['image_not_requested'] for row in select)
    a_full = bool(first_current and a['requested_detail'] == 'full' and a['observed']['packet_kind'] == 'full')
    b_compact = bool(first_current and b['observed']['packet_kind'] == 'brief'
                     and b['observed']['standard_endpoint_diagnostics_guide'])
    b_override = bool(b_compact and b['requested_detail'] == 'full')
    apparent_shape = bool(complete and fixed_products and fixed_model and fixed_cli and a_full and b_compact)
    # Optional assertions from the independent score review, never inferred
    # from substring matches in the final prose or model provider internals.
    verified_quality = bool(quality and all(
        quality.get(label, {}).get('passed') is True
        and quality[label].get('selected_scope_measured_answer_adopted') is True
        and quality[label].get('whole_scope_measured_answer_adopted') is True
        and type(quality[label].get('score')) is int and quality[label]['score'] > 0
        and quality[label].get('score') == quality[label].get('ordered_total')
        for label in LABELS) and quality['A1']['score'] == quality['B1']['score'])
    differences = {}
    if all('totals' in row for row in slots.values()):
        left, right = (slots[label]['totals'] for label in LABELS)
        differences = {key: right[key] - value for key, value in left.items()
                       if type(value) in (int, float) and type(right[key]) in (int, float)}
    assess = apparent_shape and verified_quality
    if assess:
        duplicate_delta = (len(slots['B1']['measurement_events']['repeated_same_scope_fact'])
                           - len(slots['A1']['measurement_events']['repeated_same_scope_fact']))
        observed = {'same_scope_repeat_count_delta_B_minus_A': duplicate_delta,
                    'repeat_reduction': duplicate_delta < 0,
                    'complete_time_reduction': differences.get('complete_slot_ms', 0) < 0,
                    'CLI_input_output_reduction': differences.get('CLI_input_plus_output_tokens', 0) < 0}
    else:
        observed = None
    return {
        'schema': 'm1-source-region-no-image-measurement-consumption-actual-trace-v1',
        'slots': slots, 'freeze_sha256': token,
        'formal_slots_planned': 2, 'formal_slots_created': sum(row['formal_slot_created'] for row in slots.values()),
        'models_launched': sum(row['model_consumers_launched'] for row in slots.values()),
        'exposure': {'formal_evidence_verified': complete, 'first_scope_measured_on_both_sides': bool(a and b),
                     'fixed_formal_products': fixed_products, 'fixed_model_request_profile': fixed_model,
                     'fixed_CLI_profile': fixed_cli,
                     'first_measurement_was_explicit_no_image_on_both_sides': bool(first_current),
                     'A_natural_full_and_delivered_full': a_full, 'B_delivered_candidate_task_packet': b_compact,
                     'B_natural_explicit_full_projection_triggered': b_override,
                     'paired_shape_difference_observed': apparent_shape,
                     'paired_first_text_bytes_delta_B_minus_A': b['wire_text_bytes'] - a['wire_text_bytes']
                     if apparent_shape else None},
        'independent_quality': quality, 'comparable_equal_quality_and_adoption': verified_quality,
        'all_actual_cost_deltas_B_minus_A': differences, 'qualified_one_pair_outcome': observed,
        'provider_internal_time': None, 'provider_bill': None,
        'scope': 'Use the original public event, tool and process receipts. Provider-side exposure and causes of retries are unmeasured.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=RUNTIME)
    parser.add_argument('--quality', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = analyze_pair(args.root, read(args.quality) if args.quality else None)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')
