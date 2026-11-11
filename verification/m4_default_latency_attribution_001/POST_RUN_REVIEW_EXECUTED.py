import copy
import hashlib
import io
import json
from pathlib import Path
import statistics
import subprocess
import tarfile
import traceback

ROOT = Path.cwd()
BATCH = ROOT / 'verification/m4_default_latency_attribution_001'
RUN = BATCH / 'entry/run_01'
OUTPUT = BATCH / 'POST_RUN_REVIEW.json'
checks = []
inputs = {}
report = {
    'cycle_id': 'M4-DEFAULT-LATENCY-ATTRIBUTION-001',
    'scope': 'independent saved-record, file-hash and frozen-Git audit only',
    'product_imports': 0, 'new_runtime_starts': 0, 'new_Blender_sessions': 0,
    'new_model_consumers': 0, 'new_measurements': 0,
    'interpretation': 'operational integrity and descriptive saved timings; no admission decision',
}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def raw(path):
    path = Path(path)
    value = path.read_bytes()
    inputs[str(path.resolve())] = sha(value)
    return value

def read(path):
    return json.loads(raw(path))

def lines(path):
    return [json.loads(line) for line in raw(path).splitlines() if line]

def check(name, condition):
    checks.append({'check': name, 'passed': bool(condition)})

def summary(values):
    return {'count': len(values), 'minimum_ns': min(values),
            'median_ns': statistics.median(values), 'maximum_ns': max(values)}

try:
    binding = read(BATCH / 'preparation/INPUT_BINDINGS.json')
    work = read(BATCH / 'WORK_ORDER.json')
    schedule = read(BATCH / 'SCHEDULE.json')
    batch = read(RUN / 'RESULTS.json')
    validated = read(RUN / 'VALIDATED_INPUTS.json')
    frozen = read(RUN / 'FROZEN_COMMIT.json')
    source_matches = {name: sha(raw(ROOT / name)) == digest
                      for name, digest in binding['source_files_sha256'].items()}
    installed_matches = {name: sha(raw(Path(name))) == digest
                         for name, digest in validated['checked_files_sha256'].items()}
    critical_matches = {name: sha(raw(ROOT / name)) == frozen['files_sha256'].get(name)
                        for name in binding['critical_git_paths']}
    check('source_31_exact', len(source_matches) == 31 and all(source_matches.values()))
    check('installed_290_exact', len(installed_matches) == 290 and all(installed_matches.values()))
    check('critical_20_exact', len(critical_matches) == 20 and all(critical_matches.values())
          and set(frozen['files_sha256']) == set(binding['critical_git_paths']))
    check('recorded_source_checks_exact', batch['source_checks'] == source_matches)
    check('recorded_installed_checks_exact', batch['installed_checks'] == installed_matches)
    check('work_schedule_pin', sha(raw(BATCH / 'SCHEDULE.json')) == work['schedule_sha256']
          == validated['schedule_sha256'])
    archive_raw = subprocess.run(
        ['git', '-C', str(ROOT), 'archive', '--format=tar', frozen['commit'], '--',
         *binding['critical_git_paths']], check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=30).stdout
    with tarfile.open(fileobj=io.BytesIO(archive_raw), mode='r:') as archive:
        git_files = {member.name: archive.extractfile(member).read()
                     for member in archive.getmembers() if member.isfile()}
    check('frozen_git_20_exact', set(git_files) == set(binding['critical_git_paths'])
          and all(git_files[name] == raw(ROOT / name) for name in git_files))
    check('batch_complete_without_stop', batch['passed'] is True and batch['stop'] is None
          and batch['planned_sessions'] == batch['started_sessions'] == len(batch['cases']) == 4
          and batch['not_run_sessions'] == [])
    check('fixed_BCCB_order', [case['version'] for case in batch['cases']] == ['B', 'C', 'C', 'B'])
    starts = lines(BATCH / 'entry/OWNED_STARTS.jsonl')
    check('exactly_four_owned_reservations', len(starts) == 4
          and [item['session'] for item in starts] == [item['id'] for item in schedule['sessions']])
    totals = {
        'business_requests': 0, 'worker_RPC': 0, 'close_RPC': 0,
        'cold': 0, 'warmup': 0, 'paired_warm': 0, 'warm_ON': 0, 'warm_OFF': 0,
        'all_business_ON': 0, 'all_business_OFF': 0, 'profile_initial_none': 0,
        'profile_restored': 0, 'OFF_uncollected': 0, 'ON_collected': 0,
        'cold_existing_to_mesh': 0, 'cold_existing_triangulations': 0,
        'cold_existing_world_preparations': 0, 'cold_existing_resource_builds': 0,
        'warm_and_warmup_zero_resource_work': 0, 'warm_and_warmup_zero_kernel_work': 0,
        'metadata_stdio_messages': 0, 'all_stdio_messages': 0,
        'legacy_close_events_status_unknown': 0,
    }
    sessions = []
    semantic_reference = None
    expected_sources = {'B': work['versions']['B']['source_sha256'],
                        'C': work['versions']['C']['source_sha256']}
    previous_end = batch['batch_started_ns']
    for ordinal, (case, planned) in enumerate(zip(batch['cases'], schedule['sessions']), 1):
        name = case['id']
        folder = RUN / name
        check(name + ':case_copy_exact', read(folder / 'RESULTS.json') == case)
        check(name + ':case_plan_identity', name == planned['id']
              and case['version'] == planned['version'] and case['start_reservation'] == starts[ordinal-1])
        check(name + ':session_clock', previous_end <= case['started_ns']
              and case['ended_ns'] - case['started_ns'] == case['session_wall_ns'] < 570 * 10**9
              and case['within_570s'] is True and case['errors'] == [] and case['passed'] is True)
        previous_end = case['ended_ns']
        proof = read(folder / 'PRODUCT_RUNTIME_PROOF.json')
        product_start = read(folder / 'product/START.json')
        product_close = read(folder / 'product/CLOSE.json')
        init = read(folder / 'ACTUAL_INITIALIZE.json')['result']['_meta']['human_eye']
        runtime_pid = proof['runtime_pid']
        check(name + ':actual_loaded_installation', init['source_sha256'] == expected_sources[case['version']]
              and init['source_kind'] == 'installed_distribution'
              and init['distribution_version'] == validated['versions'][case['version']]['version'])
        chain = proof['parent_chain']
        check(name + ':retained_runtime_ownership', proof['confirmed'] is True and proof['error'] is None
              and proof['launcher_pid'] == product_start['launcher_pid']
              and chain[0]['pid'] == runtime_pid and chain[-1]['pid'] == product_start['launcher_pid']
              and chain[0]['created_filetime'] == proof['runtime_created_filetime']
              and chain[-1]['created_filetime'] == proof['launcher_created_filetime']
              and len(chain) - 1 == proof['parent_edges'] <= 4
              and proof['proved_ns'] <= case['rows'][0]['started_ns'])
        exit_proof = case['product_runtime_exit']
        check(name + ':actual_runtime_exit_zero', exit_proof['confirmed'] is True
              and exit_proof['exited'] is True and exit_proof['exit_code'] == 0
              and exit_proof['handle_closed'] is True)
        check(name + ':product_launcher_close', product_close == case['product_close']
              and product_close['confirmed'] is True and product_close['process_reaped'] is True
              and product_close['reader_stopped'] is True and product_close['exit_code'] == 0
              and product_close['error'] is None)
        native_ready = read(folder / 'native/READY.json')
        native_session = read(folder / 'native/SESSION.json')
        native_closed = read(folder / 'native/WORKER_CLOSED.json')
        native_close_records = [read(path) for path in (folder / 'native').glob('CLOSE_*.json')]
        check(name + ':owned_native_exit_zero', native_closed == case['worker_closed']
              and native_ready['pid'] == native_session['pid'] == native_closed['pid'] == case['native_close']['pid']
              and native_closed['poisoned'] is False
              and native_closed['initial_geometry_fingerprint'] == native_closed['final_geometry_fingerprint']
              == native_ready['initial_fingerprint']
              and native_closed['closed_ns'] <= native_ready['deadline_ns']
              == case['started_ns'] + 570 * 10**9
              and native_close_records == [case['native_close']]
              and case['native_close']['response']['status'] == 'closed'
              and case['native_close']['error'] is None and case['native_close']['exit_code'] == 0
              and case['native_close']['process_reaped'] is True
              and case['native_close']['source_file_unchanged'] is True
              and case['native_close']['protected_files_unchanged'] is True)
        worker = lines(folder / 'native/WORKER_EVENTS.jsonl')
        check(name + ':worker_original_exact', worker == case['all_worker_events']
              and len(worker) == 23 and [event['sequence'] for event in worker] == list(range(1,24)))
        totals['worker_RPC'] += len(worker)
        totals['close_RPC'] += 1
        totals['legacy_close_events_status_unknown'] += worker[-1]['status'] == 'unknown'
        check(name + ':image_and_render_zero', case['recorded_image_construction_events'] == []
              and all(not event.get('changed_or_new_PNG_files')
                      and event.get('event') not in ('render_started','render_completed','render_cancelled')
                      and ('render_events_after' not in event
                           or event['render_events_after'] == event['render_events_before'])
                      for event in worker))
        rpc = read(folder / 'product/RPC.json')
        product_folders = sorted(path for path in (folder / 'product').iterdir()
                                 if path.is_dir() and path.name.isdigit())
        check(name + ':stdio_4_metadata_22_business', len(rpc['requests']) == len(product_folders) == 26
              and [item['method'] for item in rpc['requests'][:4]] == schedule['metadata_stdio_per_session']
              and all(item['method'] == 'tools/call' for item in rpc['requests'][4:])
              and rpc['poisoned'] is False)
        totals['metadata_stdio_messages'] += 4
        totals['all_stdio_messages'] += len(rpc['requests'])
        tx_total = rx_total = 0
        for index, protocol_folder in enumerate(product_folders):
            receipt = read(protocol_folder / 'RECEIPT.json')
            tx = raw(protocol_folder / 'TX.bin')
            request = json.loads(tx)
            rx_path = protocol_folder / 'RX.bin'
            rx = raw(rx_path) if rx_path.exists() else b''
            tx_total += len(tx)
            rx_total += len(rx)
            check(name + ':stdio_receipt_' + str(index+1),
                  receipt == rpc['requests'][index] and receipt['error'] is None
                  and receipt['send_confirmed'] is True and receipt['sent_bytes'] == len(tx)
                  and receipt['received_bytes'] == len(rx) and receipt['method'] == request['method']
                  and receipt['request_id'] == request.get('id'))
            if index < 4:
                continue
            row_index = index - 4
            row = case['rows'][row_index]
            plan = planned['business'][row_index]
            saved_request = read(folder / (row['label'] + '.REQUEST.json'))
            saved_response = read(folder / (row['label'] + '.RESPONSE.json'))
            expected_request = copy.deepcopy(schedule['request_template'])
            expected_request['id'] = plan['request_id']
            check(name + ':business_raw_wire_' + row['label'],
                  request == saved_request == expected_request and json.loads(rx) == saved_response
                  and row['stdio'] == receipt)
        check(name + ':raw_wire_byte_totals', rpc['tx_bytes'] == tx_total and rpc['rx_bytes'] == rx_total)
        audit = lines(folder / 'audit.jsonl')
        observe = [item['task_work'] for item in audit if item.get('event') == 'observe']
        check(name + ':audit_observation_count', len(observe) == len(case['rows']) == 22)
        core_reference = capture_reference = generation_reference = None
        modes = {'ON': [], 'OFF': []}
        positions = {'ON': {'1': 0, '2': 0}, 'OFF': {'1': 0, '2': 0}}
        phases = {'cold': 0, 'warmup': 0, 'warm': 0}
        pair_rows = {}
        previous = None
        cold_ns = warmup_ns = None
        for index, (row, plan, event) in enumerate(zip(case['rows'], planned['business'], worker[:22])):
            label = name + ':' + row['label']
            check(label + ':exact_schedule', all(row.get(key) == plan[key] for key in plan)
                  and row['label'] == plan['request_id'] and row['status'] == 'completed'
                  and row['previous_profile_enabled'] is previous)
            enabled = row['profile_enabled']
            previous = enabled
            phases[row['phase']] += 1
            totals['business_requests'] += 1
            totals['all_business_ON' if enabled else 'all_business_OFF'] += 1
            totals['cold' if row['phase'] == 'cold' else 'warmup' if row['phase'] == 'warmup' else 'paired_warm'] += 1
            qa = event['qa_work']
            totals['profile_initial_none'] += qa['profile_initial_present'] is False
            totals['profile_restored'] += qa['profile_restored_to_initial'] is True
            totals['ON_collected' if enabled else 'OFF_uncollected'] += 1
            check(label + ':profile_state', qa['worker_sequence'] == event['sequence'] == plan['sequence']
                  and qa['profile_enabled'] is enabled and qa['previous_profile_enabled'] is row['previous_profile_enabled']
                  and qa['profile_initial_present'] is False and qa['profile_after_restore_present'] is False
                  and qa['profile_restored_to_initial'] is True and qa['errors'] == []
                  and qa['profile_install_attempted'] is enabled and qa['profile_installed'] is enabled
                  and qa['profile_actual_enabled'] is enabled and qa['profile_restore_attempted'] is enabled
                  and qa['profile_restore_succeeded'] is enabled
                  and qa['callback_counts_status'] == ('collected' if enabled else 'not_collected')
                  and all(type(qa[key]) is dict if enabled else qa[key] is None
                          for key in ('python_calls','C_calls','C_returns','C_exceptions')))
            check(label + ':one_completed_host_RPC', row['worker_received_RPC_count'] == 1
                  and row['worker_received_events'] == [event] and event['status'] == 'completed'
                  and event['terminal_geometry_and_file_checks_passed'] is True
                  and event['script_error'] is None
                  and row['started_ns'] <= event['started_ns'] <= row['ended_ns']
                  and row['ended_ns'] - row['started_ns'] == row['entry_elapsed_ns'])
            body = row['body']
            saved = read(folder / (row['label'] + '.RESPONSE.json'))
            check(label + ':facts_exact_received', len(saved['result']['content']) == 1
                  and saved['result']['content'][0]['type'] == 'text' and saved['result']['isError'] is False
                  and json.loads(saved['result']['content'][0]['text']) == body
                  and body['status'] == 'observed' and body['execution_authority'] is False
                  and body['context']['runtime_source_sha256'] == expected_sources[case['version']]
                  and body['context']['unit'] == 'm' and body['context']['coordinate_frame'] == 'world'
                  and 'geometry' not in body)
            core = {key: value for key, value in body.items() if key != 'trace_id'}
            if core_reference is None:
                core_reference = core
            check(label + ':same_session_all_facts_and_binding', core == core_reference)
            semantics = {key: copy.deepcopy(body[key]) for key in ('sets','coverage','measurement_contracts')}
            semantics['pairs_by_original_name'] = [
                {'target_name': body['target']['name'], 'candidate_name': item['name'],
                 **{key: copy.deepcopy(item[key]) for key in
                    ('closed_solid_relation','surface_proximity','separation_gap')}}
                for item in body['candidates']]
            if semantic_reference is None:
                semantic_reference = semantics
            check(label + ':cross_session_named_facts_exact', semantics == semantic_reference)
            script = raw(folder / f'native/call_{index+1}/SCRIPT.py')
            stdout = raw(folder / f'native/call_{index+1}/stdout.txt')
            stderr = raw(folder / f'native/call_{index+1}/stderr.txt')
            logical_script = script.replace(b'\r\n', b'\n')
            logical_stdout = stdout.replace(b'\r\n', b'\n')
            logical_stderr = stderr.replace(b'\r\n', b'\n')
            check(label + ':Windows_write_text_storage_boundary',
                  logical_script.replace(b'\n', b'\r\n') == script
                  and logical_stdout.replace(b'\n', b'\r\n') == stdout
                  and logical_stderr.replace(b'\n', b'\r\n') == stderr)
            check(label + ':native_original_logical_script_and_output',
                  sha(logical_script) == event['script_sha256']
                  and len(logical_stdout) == event['stdout_bytes']
                  and len(logical_stderr) == event['stderr_bytes'] and not stderr)
            marker = b'HUMAN_EYE_BLENDER_MCP:'
            check(label + ':captured_protocol_marker', stdout.startswith(marker))
            packet = json.loads(stdout[len(marker):])['result']
            capture = packet['capture']
            state = capture['capture_state']
            generation = {key: state[key] for key in ('instance_id','epoch','revision')}
            if capture_reference is None:
                capture_reference = state
                generation_reference = generation
            selected = capture['task_selection']
            requested_selectors = [schedule['request_template']['params']['arguments']['target'],
                                   *schedule['request_template']['params']['arguments']['candidates']]
            body_rows = [body['target'], *body['candidates']]
            check(label + ':source_capture_generation_and_selection', state == capture_reference
                  and len(qa['after']['hosts']) == 1
                  and qa['after']['hosts'][0]['generation'] == generation == generation_reference
                  and capture['revision'] == body['context']['scene_revision']
                  and capture['unit'] == body['context']['unit'] == 'm'
                  and capture['coordinate_frame'] == body['context']['coordinate_frame'] == 'world'
                  and capture['capture_scope'] == body['context']['capture_scope'] == 'selected_objects'
                  and selected['selectors'] == requested_selectors
                  and selected['bindings'] == [{key: item[key] for key in ('object_id','name')} for item in body_rows]
                  and len(capture['meshes']) == body['context']['selected_count'] == 4
                  and selected['candidate_count'] == body['context']['candidate_count'] == 28)
            resource_work = qa['host_residency_delta']
            expected_resource = 4 if index == 0 else 0
            check(label + ':resource_counts', all(resource_work[key] == expected_resource
                  for key in ('to_mesh','triangulations','resource_builds','world_transforms')))
            task = row['task_work']
            check(label + ':raw_audit_task_work', task == observe[index])
            matching_trace = [item['trace'] for item in audit if item.get('event') == 'request_trace'
                              and item['trace']['annotations'].get('mcp_request_id') == row['label']]
            check(label + ':raw_trace_actual_runtime', matching_trace == [row['request_trace']]
                  and row['request_trace']['pid'] == runtime_pid)
            if index == 0:
                check(label + ':cold_existing_work', task['result_cache_hit'] is False
                      and task['exact_pair_count'] == 0 and task['closed_solid_pair_count'] == 3
                      and task['surface_pair_count'] == 3 and task['pair_calls'] == 3
                      and task['rank_calls'] == 1 and row['successful_normalize_hash_spans'] == 1
                      and len(packet['resources']) == 4)
                totals['cold_existing_to_mesh'] += resource_work['to_mesh']
                totals['cold_existing_triangulations'] += resource_work['triangulations']
                totals['cold_existing_world_preparations'] += resource_work['world_transforms']
                totals['cold_existing_resource_builds'] += resource_work['resource_builds']
                cold_ns = row['entry_elapsed_ns']
            else:
                zero_kernel = all(task[key] == 0 for key in
                    ('exact_pair_count','closed_solid_pair_count','surface_pair_count'))
                optional_pair_rank = {key: task[key] for key in ('pair_calls','rank_calls') if key in task}
                check(label + ':cache_hit_optional_pair_rank_fields',
                      all(value == 0 for value in optional_pair_rank.values()))
                check(label + ':warm_cache_no_new_kernel', zero_kernel and task['result_cache_hit'] is True
                      and row['successful_normalize_hash_spans'] == 0 and packet['resources'] == [])
                totals['warm_and_warmup_zero_resource_work'] += 1
                totals['warm_and_warmup_zero_kernel_work'] += zero_kernel
            if row['phase'] == 'warmup':
                warmup_ns = row['entry_elapsed_ns']
            if row['phase'] == 'warm':
                mode = 'ON' if enabled else 'OFF'
                modes[mode].append(row['entry_elapsed_ns'])
                positions[mode][str(row['pair_position'])] += 1
                pair_rows.setdefault(row['pair_index'], []).append(row)
                totals['warm_ON' if enabled else 'warm_OFF'] += 1
        close = worker[-1]['qa_work']
        check(name + ':close_profile_exact', close['worker_sequence'] == 23
              and close['profile_enabled'] is False and close['previous_profile_enabled'] is previous
              and close['profile_initial_present'] is False and close['profile_restored_to_initial'] is True
              and close['profile_after_restore_present'] is False and close['errors'] == []
              and close['callback_counts_status'] == 'not_collected'
              and all(close[key] is None for key in ('python_calls','C_calls','C_returns','C_exceptions'))
              and close['after']['hosts'][0]['generation'] == generation_reference)
        totals['profile_initial_none'] += close['profile_initial_present'] is False
        totals['profile_restored'] += close['profile_restored_to_initial'] is True
        totals['OFF_uncollected'] += 1
        check(name + ':sample_denominators', phases == {'cold':1,'warmup':1,'warm':20}
              and len(modes['ON']) == len(modes['OFF']) == len(pair_rows) == 10
              and positions == {'ON':{'1':5,'2':5},'OFF':{'1':5,'2':5}}
              and all(len(pair) == 2 and {row['profile_enabled'] for row in pair} == {True,False}
                      for pair in pair_rows.values()))
        paired_differences = []
        for pair in pair_rows.values():
            on = next(row for row in pair if row['profile_enabled'])
            off = next(row for row in pair if not row['profile_enabled'])
            paired_differences.append(on['entry_elapsed_ns'] - off['entry_elapsed_ns'])
        sessions.append({
            'case_id': name, 'version': case['version'], 'runtime_pid': runtime_pid,
            'runtime_exit_code': exit_proof['exit_code'], 'actual_runtime_exit_confirmed': True,
            'owned_Blender_pid': native_ready['pid'], 'owned_Blender_exit_code': case['native_close']['exit_code'],
            'phase_counts': phases, 'warm_position_counts': positions,
            'cold_entry_ns': cold_ns, 'warmup_entry_ns': warmup_ns,
            'warm_ON_entry': summary(modes['ON']), 'warm_OFF_entry': summary(modes['OFF']),
            'paired_ON_minus_OFF_entry': summary(paired_differences),
            'generation': generation_reference, 'session_wall_ns': case['session_wall_ns'],
            'source_sha256': expected_sources[case['version']],
        })
    check('runtime_PIDs_match_reported_owned_processes',
          [session['runtime_pid'] for session in sessions] == [42392,31612,21848,14060])
    check('total_denominators', totals['business_requests'] == 88 and totals['worker_RPC'] == 92
          and totals['close_RPC'] == 4 and totals['cold'] == totals['warmup'] == 4
          and totals['paired_warm'] == 80 and totals['warm_ON'] == totals['warm_OFF'] == 40
          and totals['all_business_ON'] == 40 and totals['all_business_OFF'] == 48
          and totals['profile_initial_none'] == totals['profile_restored'] == 92
          and totals['ON_collected'] == 40 and totals['OFF_uncollected'] == 52
          and totals['all_stdio_messages'] == 104 and totals['metadata_stdio_messages'] == 16)
    check('total_zero_extra_warm_resource_and_kernel',
          totals['warm_and_warmup_zero_resource_work'] == totals['warm_and_warmup_zero_kernel_work'] == 84)
    report.update({
        'fixed_commit': frozen['commit'], 'source_pin_count': len(source_matches),
        'installed_pin_count': len(installed_matches), 'critical_git_paths_count': len(critical_matches),
        'source_pins_match': all(source_matches.values()), 'installed_pins_match': all(installed_matches.values()),
        'frozen_git_bytes_match': all(critical_matches.values()), 'totals': totals, 'sessions': sessions,
        'normal_owned_exit_proofs_all_confirmed': True, 'root_cleanup_required': False,
        'cross_session_named_facts_exact': True,
        'same_session_fact_comparison_excludes_only': ['trace_id'],
        'cross_session_named_fact_projection': [
            'sets','coverage','measurement_contracts',
            'target/candidate names and all closed_solid_relation/surface_proximity/separation_gap fields'],
        'review_parser_corrections': {
            'initial_review': 'POST_RUN_REVIEW_01_ERROR.json',
            'initial_review_sha256': 'c178135f67a00579503e7fdecc14788272d5bbc47597cb76ee3923e2bfcbc385',
            'image_events': 'Original field is a list; its empty list means no recorded image construction events.',
            'text_storage': 'Only native SCRIPT.py/stdout.txt/stderr.txt metadata comparisons use the proven Windows write_text LF-to-CRLF storage relation, checked bidirectionally. All raw source, installed, wire and control pins remain byte-exact.',
            'warm_diagnostics': 'Cache-hit task_work explicitly reports three zero kernel counts and result_cache_hit=true. pair_calls/rank_calls are absent on that branch; they are not rewritten or presented as observed zero-valued fields.',
            'original_records_modified': False,
            'new_business_samples': 0,
        },
        'record_limitations': [
            'Each of four legacy close events retains status=unknown; explicit closed receipts, terminal fingerprints and zero-exit proofs confirm closure.',
            'OFF callback counts are uncollected and represented by null, with residency and product trace work still checked.',
            'ON C callback dictionaries retain the old channel observability limitation.',
            'Timing medians are recomputed from saved outer entry intervals. Two sessions per version remain the version-level units.',
            'No causal attribution, production-equivalence or full-admission conclusion is made by this integrity audit.',
        ],
    })
except BaseException:
    report['execution_error'] = traceback.format_exc()
finally:
    report['check_count'] = len(checks)
    report['failed_checks'] = [item for item in checks if not item['passed']]
    report['passed'] = not report['failed_checks'] and 'execution_error' not in report
    report['raw_files_read_count'] = len(inputs)
    report['inputs_manifest_encoding'] = 'UTF8 json.dumps ensure_ascii=False sort_keys=True separators comma colon'
    report['inputs_manifest_sha256'] = sha(json.dumps(inputs, ensure_ascii=False, sort_keys=True,
                                                     separators=(',',':')).encode('utf8'))
    report['primary_input_sha256'] = {str(path.relative_to(ROOT)): inputs[str(path.resolve())]
        for path in (RUN/'RESULTS.json', RUN/'FROZEN_COMMIT.json', RUN/'VALIDATED_INPUTS.json',
                     BATCH/'preparation/INPUT_BINDINGS.json', BATCH/'SCHEDULE.json')}
    with OUTPUT.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': report['passed'], 'check_count': report['check_count'],
                      'failed_checks': report['failed_checks'],
                      'execution_error': report.get('execution_error'),
                      'totals': report.get('totals'),
                      'medians_ns': [{'case':item['case_id'],'ON':item['warm_ON_entry']['median_ns'],
                                     'OFF':item['warm_OFF_entry']['median_ns']} for item in report.get('sessions',[])],
                      'output': str(OUTPUT)},ensure_ascii=False))
