"""Independently recompute the sealed six-slot cost and limited decision."""

import ast
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import time
import zipfile


HERE = Path(__file__).resolve().parents[1]
EXTERNAL = Path('D:/he_source_face_001')
ORDER = ('A1','B1','B2','A2','A3','B3')
CHECKS = []
INPUTS = {}


def raw(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(data).hexdigest()
    return data


def read(path):
    return json.loads(raw(path))


def check(name, passed, detail=None):
    CHECKS.append(dict(check=name, passed=bool(passed), detail=detail))


def verify_seal(seal, phase):
    failures = []
    for row in seal['inputs']:
        if hashlib.sha256(raw(row['path'])).hexdigest() != row['sha256']:
            failures.append(row['path'])
    check('quality_seal_inputs_' + phase, not failures, dict(count=len(seal['inputs']), failures=failures))


def payloads(frame):
    result = {}
    with zipfile.ZipFile(frame['NPZ']) as archive:
        check('array_member_set:' + frame['NPZ'], set(archive.namelist()) == {name+'.npy' for name in frame['arrays']})
        for name, expected in frame['arrays'].items():
            data = archive.read(name+'.npy')
            width = 2 if data[6] == 1 else 4
            length = int.from_bytes(data[8:8+width], 'little')
            offset = 8+width+length
            header = ast.literal_eval(data[8+width:offset].decode('latin1'))
            body = data[offset:]
            check('array_payload:' + frame['NPZ'] + ':' + name,
                data[:6] == b'\x93NUMPY' and header['fortran_order'] is False
                and list(header['shape']) == expected['shape'] and header['descr'] == expected['dtype']
                and len(body) == expected['nbytes'] and hashlib.sha256(body).hexdigest() == expected['sha256'])
            result[name] = len(body)
    return result


def main():
    started = time.perf_counter_ns()
    seal = read(HERE/'admin/QUALITY_SEAL.json')
    check('quality_seal_unlocked', seal['cost_analysis_unlocked_after_this_seal'] is True)
    check('first_matrix_count', seal['first_content_scoring_matrix_invocations'] == 1)
    quality = read(seal['quality_path'])
    check('quality_hash', hashlib.sha256(raw(seal['quality_path'])).hexdigest() == seal['quality_sha256'])
    check('quality_six_correct', quality['denominator'] == 6 and all(row['final_quality_passed'] for row in quality['slots']))
    check('B_binding_adoption_three', quality['B_actual_source_binding_adoption_count'] == 3)
    verify_seal(seal, 'before')
    cost = read(HERE/'COST.json')
    check('cost_phase_no_new_calls', cost['new_model_product_raster_calls'] == 0)
    run = read(EXTERNAL/'formal/RUN_RESULT.json')
    check('six_route_denominator', [row['slot'] for row in run['records']] == list(ORDER)
          and run['actual_routes'] == run['actual_CLI_processes'] == 6 and run['outer_retries'] == 0)
    slots = []
    argv_specs, binary_hashes, usage_scopes = [], [], []
    for slot in ORDER:
        folder = EXTERNAL/'formal'/slot
        record = next(row for row in run['records'] if row['slot'] == slot)
        reported = next(row for row in cost['slots'] if row['slot_id'] == slot)
        consumer = read(folder/'c/CONSUMER.json')
        stdout = raw(folder/'c/stdout.raw.bin')
        check(slot + ':actual_stdout_hash', hashlib.sha256(stdout).hexdigest() == consumer['stdout_raw_sha256'])
        usage_events, agent_texts = [], []
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                continue
            if event.get('type') == 'turn.completed':
                usage_events.append(event['usage'])
            item = event.get('item')
            if isinstance(item, dict) and item.get('type') == 'agent_message' and event.get('type') == 'item.completed':
                agent_texts.append(item['text'])
        usage = consumer['usage']
        check(slot + ':one_actual_raw_usage', usage_events == [usage] == consumer['raw_usage_events'] == consumer['usage_rows'])
        check(slot + ':usage_report_equal', usage == reported['reported_usage'])
        check(slot + ':usage_valid_subsets', all(type(v) is int and v >= 0 for v in usage.values())
              and usage['cached_input_tokens'] <= usage['input_tokens'] and usage['reasoning_output_tokens'] <= usage['output_tokens'])
        check(slot + ':actual_agent_public_messages', agent_texts == [message['text'] for message in consumer['all_public_messages']])
        assistant_bytes = sum(len(text.encode('utf-8')) for text in agent_texts)
        check(slot + ':assistant_text_counter', assistant_bytes == consumer['public_text_bytes'] == reported['bytes']['assistant_public_text_UTF8'])
        argv = consumer['argv']
        argv_specs.append([value.replace(slot, '<slot>') for value in argv])
        binary_hashes.append(hashlib.sha256(raw(argv[0])).hexdigest())
        usage_scopes.append((consumer.get('usage_semantics'),json.dumps(consumer.get('usage_aggregation'),sort_keys=True)))
        check(slot + ':model_request_profile', consumer['model'] == 'gpt-6.1-sol' and consumer['requested_effort'] == 'medium'
              and 'service_tier="default"' in argv and 'model_reasoning_effort="medium"' in argv)
        timing = read(EXTERNAL/'formal/slot_records'/slot/'SLOT_TIMING.json')
        outer_start, outer_end = timing['started_ns'], timing['SLOT_RESULT_closed_ns']
        full_ns = outer_end-outer_start
        check(slot + ':complete_slot_clock', timing['elapsed_ns'] == full_ns == reported['full_slot_ns']
              and timing['slot'] == slot and timing['group'] == 'P' and not timing['publication_errors'])
        route_clock = read(folder/'FINAL_TIMING.json')
        cli_clock = read(folder/'c/FINAL_TIMING.json')
        check(slot + ':nested_clock_order', outer_start <= route_clock['started_ns'] <= cli_clock['started_ns']
              <= cli_clock['consumer_record_closed_ns'] <= route_clock['result_closed_ns'] <= outer_end)
        check(slot + ':nested_clock_differences', route_clock['elapsed_ns'] == route_clock['result_closed_ns']-route_clock['started_ns']
              and cli_clock['full_turn_wall_ns'] == cli_clock['consumer_record_closed_ns']-cli_clock['started_ns'])
        check(slot + ':original_450s', record['deadline_ns'] == route_clock['started_ns']+450_000_000_000)
        check(slot + ':actual_final_in_deadline', consumer['final_received_ns'] <= record['deadline_ns'])
        check(slot + ':slot_result_source', read(EXTERNAL/'formal/slot_records'/slot/'SLOT_RESULT.json')['source_unchanged'] is True)
        fact = read(EXTERNAL/'formal/slot_records'/slot/'FACT_CHECK.json')
        check(slot + ':fact_check_outside_slot', fact['started_ns'] >= outer_end and fact['passed'] is True)
        observations = read(folder/'o/OBSERVATIONS.json')
        metrics = read(folder/'o/METRICS.json')
        check(slot + ':arm_manifest', read(observations['source_inputs']['manifest_path'])['comparison_arm'] == slot[0]
              and observations['group'] == 'P' and record['comparison_arm'] == slot[0])
        text_bytes = 0
        images = []
        tool_count = len(consumer['tool_calls'])
        check(slot + ':actual_business_count', tool_count == len(metrics['tools']) <= 12)
        for index, call in enumerate(consumer['tool_calls'], 1):
            request = read(folder/'o'/('tool_'+str(index).zfill(2))/'REQUEST.json')
            response = read(folder/'o'/('tool_'+str(index).zfill(2))/'RESPONSE.json')
            receipt = metrics['tools'][index-1]
            check(slot + ':tool_response_bound:' + str(index), response['result']['content'] == call['item']['result']['content']
                  and request['params']['name'] == call['item']['tool'] == receipt['name'])
            actual_text = sum(len(block['text'].encode('utf-8')) for block in response['result']['content'] if block.get('type') == 'text')
            check(slot + ':tool_text_metric:' + str(index), actual_text == receipt['content_metrics']['text_UTF8_bytes']
                  == reported['tools'][index-1]['tool_reply_text_UTF8_bytes'])
            text_bytes += actual_text
            for block in response['result']['content']:
                if block.get('type') == 'image':
                    png = base64.b64decode(block['data'],validate=True)
                    images.append(dict(sha256=hashlib.sha256(png).hexdigest(), bytes=len(png), base64_chars=len(block['data'])))
        check(slot + ':tool_text_total', text_bytes == reported['bytes']['tool_reply_text_UTF8'])
        check(slot + ':delivered_image_count', len(images) == consumer['public_image_count'] == metrics['constructed_image_blocks']
              == metrics['server_socket_sent_image_blocks'] == reported['counts']['CLI_images'])
        check(slot + ':delivered_image_bytes', sum(image['bytes'] for image in images) == consumer['public_image_bytes']
              == reported['bytes']['CLI_PNG'])
        counts = Counter(image['sha256'] for image in images)
        duplicates = sum(value-1 for value in counts.values())
        duplicate_bytes = sum((value-1)*next(i['bytes'] for i in images if i['sha256']==digest) for digest,value in counts.items())
        diag = reported['observation_diagnostics']
        check(slot + ':duplicate_image_counters', duplicates == diag['duplicate_PNG_content_blocks']
              and duplicate_bytes == diag['duplicate_PNG_content_bytes'])
        product = read(folder/'o/product_call_01/SERVICE_RESULT.json')
        initial = [frame['view_name'] for frame in product['frames']]
        manifest = read(observations['source_inputs']['manifest_path'])
        tasks = read(manifest['tasks']['path'])
        check(slot + ':TOP_required_by_actual_input', any(sample['view_name']=='TOP' for sample in tasks['pixel_samples'])
              and diag['TOP_required_by_fixed_sample'] is True)
        check(slot + ':initial_view_policy', initial == ['SCENE','LEFT','BACK'] and 'TOP' not in initial
              and diag['TOP_in_initial_product_frames'] is False)
        native_top = sum(frame['origin']=='native' and frame['view_name']=='TOP' for frame in observations['frames'])
        check(slot + ':one_needed_native_TOP', native_top == 1 == diag['actual_native_TOP_constructions']
              and diag['new_TOP_needed_after_initial_product'] is True)
        four_bytes, mapping_bytes = 0, 0
        for frame in observations['frames']:
            check(slot + ':PNG_file:' + frame['ref'], hashlib.sha256(raw(frame['PNG'])).hexdigest() == frame['PNG_sha256'])
            check(slot + ':NPZ_file:' + frame['ref'], hashlib.sha256(raw(frame['NPZ'])).hexdigest() == frame['NPZ_sha256'])
            sizes = payloads(frame)
            four_names = ('color','depth','owners','patch_owners') if frame['origin']=='product' else ('color','depth','owners','triangle_ids')
            four = sum(sizes[name] for name in four_names)
            extra = sum(sizes.values())-four
            check(slot + ':array_payload_total:' + frame['ref'], four == frame['raster_returned_array_payload_bytes']
                  and four+extra == frame['array_payload_bytes'])
            four_bytes += four
            mapping_bytes += extra
        check(slot + ':array_cost_totals', four_bytes == reported['bytes']['four_buffers']
              and mapping_bytes == reported['bytes']['product_mapping']
              and four_bytes+mapping_bytes == reported['bytes']['all_saved_arrays'])
        check(slot + ':raster_counts', len(observations['render_attempts']) == metrics['new_renders'] == reported['counts']['rasters'] == 4)
        check(slot + ':no_business_errors', reported['counts']['business_errors'] == 0)
        slots.append(dict(slot=slot, arm=slot[0], full_slot_ns=full_ns, usage=usage,
            tool_reply_text_UTF8=text_bytes, assistant_public_text_UTF8=assistant_bytes,
            image_blocks=len(images), duplicate_image_blocks=duplicates, duplicate_image_bytes=duplicate_bytes,
            rasters=4, native_TOP_constructions=native_top, initial_views=initial,
            started_ns=outer_start, closed_ns=outer_end, between_slot_fact_check_ns=fact['elapsed_ns']))
    check('same_actual_binary', len(set(binary_hashes)) == 1)
    check('same_slot_normalized_argv', all(argv == argv_specs[0] for argv in argv_specs))
    check('same_usage_scope', len(set(usage_scopes)) == 1)
    totals = {}
    for arm in ('A','B'):
        rows = [row for row in slots if row['arm'] == arm]
        usage_sum = {key:sum(row['usage'][key] for row in rows) for key in rows[0]['usage']}
        total = usage_sum['input_tokens']+usage_sum['output_tokens']
        text_sum = sum(row['tool_reply_text_UTF8'] for row in rows)
        assistant_sum = sum(row['assistant_public_text_UTF8'] for row in rows)
        check(arm + ':group_usage_total', cost['groups'][arm]['usage_sum'] == usage_sum
              and cost['groups'][arm]['input_plus_output'] == total)
        check(arm + ':separate_tool_assistant_text', cost['groups'][arm]['tool_reply_text_UTF8'] == text_sum
              and cost['groups'][arm]['assistant_public_text_UTF8'] == assistant_sum)
        totals[arm] = dict(usage_sum=usage_sum,input_plus_output=total, tool_reply_text_UTF8=text_sum,
            assistant_public_text_UTF8=assistant_sum, image_blocks=sum(row['image_blocks'] for row in rows),
            rasters=sum(row['rasters'] for row in rows))
    pairs = []
    for index in (1,2,3):
        a,b = (next(row for row in slots if row['slot']==arm+str(index)) for arm in ('A','B'))
        ratio = b['full_slot_ns']/a['full_slot_ns']
        pair = dict(A_slot=a['slot'],B_slot=b['slot'],B_over_A=ratio,B_faster=b['full_slot_ns']<a['full_slot_ns'])
        actual = cost['decision']['pairs'][index-1]
        check('pair'+str(index)+':actual_complete_time_ratio', ratio == actual['B_over_A'] and pair['B_faster'] == actual['B_faster']
              and actual['both_correct_complete'] is True)
        pairs.append(pair)
    median = statistics.median(pair['B_over_A'] for pair in pairs)
    faster = sum(pair['B_faster'] for pair in pairs)
    check('all_registered_gates', median <= .90 and faster >= 2 and totals['B']['input_plus_output'] <= totals['A']['input_plus_output']
          and median == cost['decision']['median_B_over_A'] and faster == cost['decision']['B_faster_pairs']
          and all(cost['decision'][key] is True for key in ('quality_gate','B_actual_source_binding_adoption_gate','time_gate','usage_gate','CLI_usage_same_source_comparable','limited_positive_signal')))
    check('pair2_slower_preserved', pairs[1]['B_over_A'] > 1 and pairs[1]['B_faster'] is False)
    check('tool_text_increase_preserved', totals['B']['tool_reply_text_UTF8'] > totals['A']['tool_reply_text_UTF8'])
    ledger = [read(path) for path in sorted((EXTERNAL/'raster_budget').glob('attempt_*/INTENT.json'))]
    phases = Counter(row['phase'] for row in ledger)
    check('actual_global_raster_accounting', len(ledger)==30 and phases==dict(preparation=6,formal=24)
          and [row['global_attempt'] for row in ledger]==list(range(1,31)) and cost['raster_attempts']==dict(all=30,preparation=6,formal=24))
    check('both_formal_raster_counts', totals['A']['rasters']==totals['B']['rasters']==12)
    check('actual_group_image_counts', totals['A']['image_blocks']==12 and totals['B']['image_blocks']==11)
    batch = read(EXTERNAL/'formal/BATCH_TIMING.json')
    batch_ns = batch['aggregate_results_closed_ns']-batch['started_ns']
    full_sum = sum(row['full_slot_ns'] for row in slots)
    fact_sum = sum(row['between_slot_fact_check_ns'] for row in slots)
    check('batch_clock_and_nested_sum', batch_ns==batch['elapsed_ns']==cost['batch_timing']['elapsed_ns']
          and full_sum+fact_sum <= batch_ns)
    check('serial_slot_clocks', all(first['closed_ns'] <= second['started_ns'] for first,second in zip(slots,slots[1:])))
    archive = read(HERE/'RUNTIME_ARCHIVE.json')
    archive_errors = []
    for item in archive['files']:
        original = raw(item['original_path'])
        copied = raw(HERE/item['archive_path'])
        if original != copied or len(original)!=item['bytes'] or hashlib.sha256(original).hexdigest()!=item['sha256']:
            archive_errors.append(item['relative_path'])
    check('all_archive_copies_byte_exact', len(archive['files'])==970 and not archive_errors,
          dict(files=len(archive['files']),bytes=archive['bytes'],errors=archive_errors))
    check('archive_has_no_auth_paths', not any('auth.json' in row['relative_path'].lower() for row in archive['files']))
    verify_seal(seal,'after')
    failed = [c for c in CHECKS if not c['passed']]
    report = dict(schema='m1-source-face-binding-independent-cost-review-v1', passed=not failed,
        check_count=len(CHECKS), passed_checks=len(CHECKS)-len(failed),failed_checks=failed,checks=CHECKS,
        group_totals=totals, pairs=pairs, median_B_over_A=median, faster_pairs=faster,
        raw_input_plus_output_reduction=(totals['A']['input_plus_output']-totals['B']['input_plus_output'])/totals['A']['input_plus_output'],
        limited_positive_signal=True, whole_batch_ns=batch_ns, sum_full_slots_ns=full_sum,
        between_slot_fact_check_ns=fact_sum, batch_minus_full_slots_ns=batch_ns-full_sum,
        quality_seal_sha256=hashlib.sha256(raw(HERE/'admin/QUALITY_SEAL.json')).hexdigest(),
        cost_sha256=hashlib.sha256(raw(HERE/'COST.json')).hexdigest(), inputs_sha256=INPUTS,
        sealed_inputs_checked_before_and_after=len(seal['inputs']),archive_files_checked=len(archive['files']),
        review_started_ns=started,before_publication_ns=time.perf_counter_ns(),
        new_model_observe_raster_score_evaluator_calls=0,
        caveats=['One fixed synthetic task and three preregistered old/new pairs. Statistical and general-scene effects remain unmeasured.',
            'Raw same-CLI input+output is measured. Cached input and reasoning output are subsets. Provider turn/session aggregation remains unconfirmed.',
            'Cash, image-token breakdown, provider internal requests and complete preparation/review model costs remain unmeasured.',
            'Tool reply text increased while raw CLI tokens decreased. These are different measured quantities.',
            'Both arms constructed the required missing TOP frame. B1 omitted its additional image attachment as a consumer choice.'],
        reviewer_association='Product projection and engineering measurement author, reviewing saved cost arithmetic independently of cost_audit implementation. Parent independent review remains separate.')
    with (HERE/'COST_REVIEW.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,ensure_ascii=False,allow_nan=False,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=report['passed'],checks=report['check_count'],failures=failed,median=median,totals=totals)))


if __name__ == '__main__':
    main()
