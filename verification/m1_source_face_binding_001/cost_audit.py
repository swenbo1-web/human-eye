"""Saved complete-slot costs, unlocked only by a published quality seal."""

import argparse
import ast
import base64
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import statistics
import zipfile


HERE = Path(__file__).resolve().parent
EXTERNAL = Path('D:/he_source_face_001')
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read(path):
    return json.loads(raw(path))


def require(value, reason):
    if not value:
        raise ValueError(reason)


def clock(value, finish='closed_ns', elapsed='elapsed_ns'):
    start, end = value['started_ns'], value[finish]
    require(type(start) is int and type(end) is int and end >= start, 'saved_clock_order')
    require(value[elapsed] == end-start, 'saved_clock_difference')
    return {'started_ns': start, 'closed_ns': end, 'elapsed_ns': end-start, 'scope': value.get('scope')}


def bind_manifest(slot, observations):
    plan = read(HERE / 'PLAN.json')
    path = Path(observations['source_inputs']['manifest_path']).resolve()
    require(path == Path(plan['inputs']['manifests'][slot[0]]).resolve(), 'actual_owner_arm_manifest')
    require(observations['group'] == 'P'
            and hashlib.sha256(raw(path)).hexdigest() == observations['source_inputs']['manifest_sha256'],
            'actual_owner_manifest_identity')
    manifest = read(path)
    require(manifest['comparison_arm'] == slot[0]
            and manifest['product_binding'] == plan['products'][slot[0]], 'actual_arm_product_binding')
    return manifest


def frame_cost(frame):
    png, npz = raw(frame['PNG']), raw(frame['NPZ'])
    require(hashlib.sha256(png).hexdigest() == frame['PNG_sha256'] and len(png) == frame['PNG_bytes'], 'PNG_binding')
    require(hashlib.sha256(npz).hexdigest() == frame['NPZ_sha256'] and len(npz) == frame['NPZ_bytes'], 'NPZ_binding')
    arrays = {}
    with zipfile.ZipFile(io.BytesIO(npz)) as archive:
        require(set(archive.namelist()) == {name+'.npy' for name in frame['arrays']}, 'saved_array_members')
        for name, metadata in frame['arrays'].items():
            data = archive.read(name+'.npy')
            require(data[:6] == b'\x93NUMPY', 'NPY_magic')
            length_size = 2 if data[6] == 1 else 4
            header_size = int.from_bytes(data[8:8+length_size], 'little')
            offset = 8+length_size+header_size
            header = ast.literal_eval(data[8+length_size:offset].decode('latin1'))
            payload = data[offset:]
            require(not header['fortran_order'] and list(header['shape']) == metadata['shape']
                    and len(payload) == metadata['nbytes']
                    and hashlib.sha256(payload).hexdigest() == metadata['sha256'], 'array_metadata_binding')
            arrays[name] = {'dtype': header['descr'], 'shape': list(header['shape']), 'nbytes': len(payload),
                            'sha256': hashlib.sha256(payload).hexdigest()}
    four_names = {'color', 'depth', 'owners', 'patch_owners' if frame['origin'] == 'product' else 'triangle_ids'}
    require(four_names <= set(arrays), 'four_returned_buffers')
    four = sum(arrays[name]['nbytes'] for name in four_names)
    mapping = sum(v['nbytes'] for name, v in arrays.items() if name not in four_names)
    require(four == frame['raster_returned_array_payload_bytes']
            and four+mapping == frame['array_payload_bytes'], 'frame_payload_metric')
    return {k: frame[k] for k in ('attempt_id', 'global_attempt', 'origin', 'view_name', 'ref')} | {
        'PNG_bytes': len(png), 'NPZ_bytes': len(npz), 'arrays': arrays,
        'four_buffer_payload_bytes': four, 'mapping_payload_bytes': mapping,
        'all_saved_array_payload_bytes': four+mapping,
        'original_raster_call_ns': frame['render_closed_ns']-frame['render_started_ns'],
        'intent_to_registration_ns': frame['completed_ns']-frame['started_ns']}


def slot_cost(slot, quality, run):
    route = next(r for r in run['records'] if r['slot'] == slot)
    output = {'slot_id': slot, 'group': slot[0], 'execution_state': route['execution_state'],
              'quality_passed': quality['final_quality_passed'], 'errors': [], 'full_slot_ns': None,
              'usage_comparable_record': False, 'reported_usage': None}
    if route['execution_state'] == 'not_run':
        return output
    folder = EXTERNAL / 'formal' / slot
    try:
        timing = read(EXTERNAL / 'formal/slot_records' / slot / 'SLOT_TIMING.json')
        outer = clock(timing, 'SLOT_RESULT_closed_ns')
        output['full_slot_ns'] = outer['elapsed_ns']
        output['clocks'] = {'outer': outer}
        result = read(EXTERNAL / 'formal/slot_records' / slot / 'SLOT_RESULT.json')
        consumer = read(folder / 'c/CONSUMER.json')
        consumer_clock = clock(read(folder / 'c/FINAL_TIMING.json'), 'consumer_record_closed_ns', 'full_turn_wall_ns')
        route_clock = clock(read(folder / 'FINAL_TIMING.json'), 'result_closed_ns')
        require(outer['started_ns'] <= route_clock['started_ns'] <= consumer_clock['started_ns']
                <= consumer_clock['closed_ns'] <= route_clock['closed_ns'] <= outer['closed_ns'], 'common_nested_clock')
        require(route['deadline_ns'] == route_clock['started_ns']+450_000_000_000, 'original_450_second_route_deadline')
        require(timing['slot'] == slot and timing['group'] == 'P' and route['group'] == 'P'
                and route['comparison_arm'] == slot[0] and not timing['publication_errors']
                and result['source_unchanged'] is True, 'complete_slot_source_and_publication')
        consumer_raw = raw(folder / 'c/stdout.raw.bin')
        require(hashlib.sha256(consumer_raw).hexdigest() == consumer['stdout_raw_sha256'], 'actual_CLI_stdout')
        usage = consumer.get('usage')
        raw_events, rows = consumer.get('raw_usage_events', []), consumer.get('usage_rows', [])
        actual_usage_events = []
        for line in consumer_raw.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if type(event) is dict and event.get('type') == 'turn.completed':
                actual_usage_events.append(event.get('usage'))
        usage_ok = (actual_usage_events == [usage] and type(usage) is dict and len(raw_events) == len(rows) == 1
                    and usage == raw_events[0] == rows[0]
                    and all(type(v) is int and v >= 0 for v in usage.values())
                    and all(k in usage for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_output_tokens'))
                    and usage['cached_input_tokens'] <= usage['input_tokens']
                    and usage['reasoning_output_tokens'] <= usage['output_tokens'])
        metrics, observations = read(folder / 'o/METRICS.json'), read(folder / 'o/OBSERVATIONS.json')
        tools = []
        require(len(metrics['tools']) == len(consumer['tool_calls']) <= 12, 'all_business_call_count')
        for row, public in zip(metrics['tools'], consumer['tool_calls']):
            tool_folder = folder / 'o' / ('tool_' + str(row['attempt']).zfill(2))
            request = read(tool_folder / 'REQUEST.json')
            response_path = tool_folder / 'RESPONSE.json'
            if not response_path.exists():
                response_path = tool_folder / 'ERROR_RESPONSE.json'
            response = read(response_path)
            require(request['params']['name'] == public['item']['tool'] == row['name'], 'actual_tool_name')
            require(response['result']['content'] == public['item']['result']['content'], 'actual_tool_content')
            actual_text_bytes = sum(len(block['text'].encode('utf-8'))
                for block in response['result']['content'] if block.get('type') == 'text')
            require(actual_text_bytes == row['content_metrics']['text_UTF8_bytes'], 'actual_tool_reply_text')
            tools.append({'tool_reply_text_UTF8_bytes': actual_text_bytes, 'attempt': row['attempt'], 'name': row['name'], **clock(row),
                          'is_error': row['is_error'], 'error': row['error'],
                          'content_metrics': row['content_metrics'], 'compact_response_bytes': row['response_bytes'],
                          'request_bytes': len(raw(tool_folder / 'REQUEST.json')), 'response_bytes': len(raw(response_path))})
        frames = [frame_cost(frame) for frame in observations['frames']]
        require(len(observations['render_attempts']) == metrics['new_renders'] <= 6, 'all_raster_attempt_count')
        images = []
        for call in consumer['tool_calls']:
            for block in call['item']['result']['content']:
                if block.get('type') == 'image':
                    image = base64.b64decode(block['data'], validate=True)
                    images.append({'PNG_bytes': len(image), 'PNG_sha256': hashlib.sha256(image).hexdigest(),
                                   'base64_chars': len(block['data']),
                                   'JSON_bytes': len(json.dumps(block, ensure_ascii=False, separators=(',', ':')).encode())})
        require(len(images) == consumer['public_image_count'] == metrics['constructed_image_blocks']
                == metrics['server_socket_sent_image_blocks'], 'actual_CLI_image_receipts')
        require(sum(i['PNG_bytes'] for i in images) == consumer['public_image_bytes'], 'actual_CLI_image_bytes')
        replays = []
        for replay in observations['replays']:
            data = raw(replay['path'])
            require(hashlib.sha256(data).hexdigest() == replay['sha256'] and len(data) == replay['bytes'], 'capture_replay_bytes')
            replays.append(replay)
        assistant_text_bytes = sum(len(message['text'].encode('utf-8'))
            for message in consumer['all_public_messages'])
        require(assistant_text_bytes == consumer['public_text_bytes'], 'actual_assistant_public_text')
        manifest = bind_manifest(slot, observations)
        tasks = read(manifest['tasks']['path'])
        products = []
        for index in range(1, len(observations['active'])+1):
            call_root = folder / 'o' / ('product_call_' + str(index).zfill(2))
            product = read(call_root / 'SERVICE_RESULT.json')
            binding = read(manifest['product_binding']['path'])
            require(product['binding']['runtime_source_sha256'] == binding['source_sha256'], 'actual_product_version')
            products.append({'CALL': read(call_root / 'CALL.json'),
                             'product_source_sha256': binding['source_sha256'],
                             'work': product['work'], 'generation_work': product['generation_work'],
                             'stages': product['stages'], 'generation_stages': product['generation_stages'],
                             'per_frame_stages': [{'view_name': f['view_name'], 'stages': f['stages'],
                                                   'feedback_stages': f['feedback_stages']} for f in product['frames']]})
        first_product = read(folder / 'o/product_call_01/SERVICE_RESULT.json') if products else None
        initial_views = [] if first_product is None else [f['view_name'] for f in first_product['frames']]
        image_counts = Counter(image['PNG_sha256'] for image in images)
        top_required = any(sample['view_name'] == 'TOP' for sample in tasks['pixel_samples'])
        four = sum(f['four_buffer_payload_bytes'] for f in frames)
        mapping = sum(f['mapping_payload_bytes'] for f in frames)
        output.update(full_slot_ns=outer['elapsed_ns'], clocks={'outer': outer, 'route': route_clock, 'consumer': consumer_clock},
                      prompt_to_final_ns=consumer['final_received_ns']-consumer['prompt_submitted_ns'],
                      original_deadline_ns=route['deadline_ns'], reported_usage=usage,
                      usage_comparable_record=bool(usage_ok), raw_usage_event_count=len(raw_events),
                      usage_semantics=consumer.get('usage_semantics'), usage_aggregation=consumer.get('usage_aggregation'),
                      CLI={'argv': consumer['argv'], 'model': consumer['model'], 'effort': consumer['requested_effort']},
                      tools=tools, frames=frames, image_deliveries=images, product=products,
                      capture_replays=replays, cache_requests=observations.get('cache_requests', []),
                      metrics_original=metrics, startup_stages=observations['stages'],
                      observation_diagnostics={'TOP_required_by_fixed_sample': top_required,
                          'TOP_in_initial_product_frames': 'TOP' in initial_views,
                          'new_TOP_needed_after_initial_product': top_required and 'TOP' not in initial_views,
                          'actual_native_TOP_constructions': sum(f['origin'] == 'native' and f['view_name'] == 'TOP' for f in frames),
                          'duplicate_PNG_content_blocks': sum(count-1 for count in image_counts.values()),
                          'duplicate_PNG_content_bytes': sum((count-1)*next(i['PNG_bytes'] for i in images if i['PNG_sha256']==digest) for digest,count in image_counts.items())},
                      counts={'tools': len(tools), 'rasters': len(observations['render_attempts']),
                              'completed_frames': len(frames), 'business_errors': sum(t['is_error'] for t in tools),
                              'product_calls': len(products), 'capture_replays': len(replays), 'CLI_images': len(images)},
                      bytes={'source_capture': len(raw(manifest['capture']['path'])),
                             'source_scene': len(raw(manifest['scene']['path'])),
                             'four_buffers': four, 'product_mapping': mapping, 'all_saved_arrays': four+mapping,
                             'generated_PNG': sum(f['PNG_bytes'] for f in frames), 'generated_NPZ': sum(f['NPZ_bytes'] for f in frames),
                             'CLI_PNG': sum(i['PNG_bytes'] for i in images),
                             'tool_reply_text_UTF8': sum(t['tool_reply_text_UTF8_bytes'] for t in tools),
                             'assistant_public_text_UTF8': assistant_text_bytes, 'MCP_stdio_TX': consumer['MCP_stdio_TX_bytes'],
                             'MCP_stdio_RX': consumer['MCP_stdio_RX_bytes']})
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        output['errors'].append({'type': type(error).__name__, 'message': str(error)})
    return output


def build(args):
    seal = read(args.quality_seal)
    require(seal['cost_analysis_unlocked_after_this_seal'] is True, 'quality_must_be_published_before_cost')
    quality_path = Path(seal['quality_path']).resolve()
    require(quality_path.is_relative_to(HERE) and hashlib.sha256(raw(quality_path)).hexdigest() == seal['quality_sha256'], 'sealed_quality_identity')
    for row in seal['inputs']:
        require(hashlib.sha256(raw(row['path'])).hexdigest() == row['sha256'], 'sealed_quality_input_changed')
    quality = read(quality_path)
    require(quality['denominator'] == 6 and quality['cost_analysis_performed'] is False, 'frozen_six_slot_quality')
    run = read(EXTERNAL / 'formal/RUN_RESULT.json')
    require([r['slot'] for r in run['records']] == list(ORDER), 'all_six_route_denominator')
    by_quality = {r['slot_id']: r for r in quality['slots']}
    slots = [slot_cost(slot, by_quality[slot], run) for slot in ORDER]
    groups = {}
    for group in ('A', 'B'):
        rows = [r for r in slots if r['group'] == group]
        have_usage = all(r['usage_comparable_record'] and not r['errors'] for r in rows)
        usages = [r['reported_usage'] for r in rows]
        same_keys = have_usage and len({tuple(sorted(value)) for value in usages}) == 1
        usage_sum = {key: sum(value[key] for value in usages) for key in usages[0]} if same_keys else None
        groups[group] = {'denominator': 3, 'quality_passed': sum(r['quality_passed'] for r in rows),
                         'completed': sum(r['execution_state'] == 'completed' for r in rows),
                         'usage_sum': usage_sum,
                         'input_plus_output': usage_sum['input_tokens']+usage_sum['output_tokens'] if usage_sum else None,
                         'tool_reply_text_UTF8': sum(r.get('bytes', {}).get('tool_reply_text_UTF8', 0) for r in rows),
                         'assistant_public_text_UTF8': sum(r.get('bytes', {}).get('assistant_public_text_UTF8', 0) for r in rows)}
    pairs = []
    for number in (1, 2, 3):
        a, b = (next(r for r in slots if r['slot_id'] == group+str(number)) for group in ('A', 'B'))
        valid = bool(a['quality_passed'] and b['quality_passed'] and not a['errors'] and not b['errors']
                     and a['full_slot_ns'] and b['full_slot_ns'])
        pairs.append({'A_slot': a['slot_id'], 'B_slot': b['slot_id'], 'both_correct_complete': valid,
                      'A_full_slot_ns': a['full_slot_ns'], 'B_full_slot_ns': b['full_slot_ns'],
                      'B_over_A': b['full_slot_ns']/a['full_slot_ns'] if valid else None,
                      'B_faster': b['full_slot_ns'] < a['full_slot_ns'] if valid else None})
    paired = all(pair['both_correct_complete'] for pair in pairs)
    median = statistics.median(pair['B_over_A'] for pair in pairs) if paired else None
    comparable = (all(r['usage_comparable_record'] and not r['errors'] for r in slots)
                  and len({tuple(sorted(r['reported_usage'])) for r in slots}) == 1
                  and len({r.get('usage_semantics') for r in slots}) == 1
                  and len({json.dumps(r.get('usage_aggregation')) for r in slots}) == 1
                  and len({r.get('CLI', {}).get('argv', [''])[0] for r in slots}) == 1
                  and all(r.get('CLI', {}).get('model') == 'gpt-6.1-sol'
                          and r.get('CLI', {}).get('effort') == 'medium'
                          and 'service_tier="default"' in r.get('CLI', {}).get('argv', []) for r in slots))
    quality_gate = groups['A']['quality_passed'] == groups['B']['quality_passed'] == 3
    adoption_gate = quality['B_actual_source_binding_adoption_count'] == 3
    time_gate = bool(paired and median <= .90 and sum(pair['B_faster'] for pair in pairs) >= 2)
    usage_gate = bool(comparable and groups['B']['input_plus_output'] is not None
                      and groups['A']['input_plus_output'] is not None
                      and groups['B']['input_plus_output'] <= groups['A']['input_plus_output'])
    decision = {'quality_gate': quality_gate, 'B_actual_source_binding_adoption_gate': adoption_gate,
                'pairs': pairs, 'median_B_over_A': median, 'required_median_max': .90,
                'B_faster_pairs': sum(pair['B_faster'] is True for pair in pairs), 'required_faster_pairs': 2,
                'time_gate': time_gate, 'CLI_usage_same_source_comparable': comparable, 'usage_gate': usage_gate,
                'limited_positive_signal': quality_gate and adoption_gate and time_gate and usage_gate,
                'scope': 'One fixed source-face-delivery candidate and three preregistered old/new product pairs. Statistical generalization remains unmeasured.'}
    ledger = [read(p) for p in sorted((EXTERNAL / 'raster_budget').glob('attempt_*/INTENT.json'))]
    require(len(ledger) <= 48 and [r['global_attempt'] for r in ledger] == list(range(1, len(ledger)+1)), 'whole_batch_raster_ledger')
    phases = {phase: sum(r['phase'] == phase for r in ledger) for phase in ('preparation', 'formal')}
    require(phases['preparation'] <= 12 and phases['formal'] <= 36, 'phase_raster_caps')
    output = {'schema': 'source-face-binding-cost-v1', 'decision': decision, 'groups': groups, 'slots': slots,
              'raster_attempts': {'all': len(ledger), **phases}, 'durable_intents': ledger,
              'batch_timing': read(EXTERNAL / 'formal/BATCH_TIMING.json'),
              'qualification_timings': [read(path) for path in sorted((EXTERNAL / 'preparation').glob('Q[0-9][0-9]/QUALIFICATION_RUN.json'))],
              'usage_scope': 'Actual same-CLI raw input+output. Cached and reasoning are subsets. Provider turn/session aggregation remains unconfirmed.',
              'unknowns': {'cash': None, 'image_tokens': None, 'provider_requests': None,
                           'complete_human_cost': None, 'peak_memory': None, 'total_temporary_arrays': None},
              'nested_costs': 'All buffer/PNG/NPZ/base64/JSON byte representations and clocks are retained separately. They are never summed as total network traffic or outer duration.',
              'new_model_product_raster_calls': 0, 'inputs_sha256': dict(sorted(INPUTS.items()))}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quality-seal', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.output.resolve().is_relative_to(HERE), 'new_namespace_output')
    report = build(args)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(report['decision']))


if __name__ == '__main__':
    main()
