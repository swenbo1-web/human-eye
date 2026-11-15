"""Read-only source, lifecycle, arm delivery and archive review."""
import base64
import hashlib
import json
from pathlib import Path
import re
import time
import zipfile

HERE = Path(__file__).resolve().parents[1]
EXTERNAL = Path('D:/he_source_face_001')
ORDER = ('A1', 'B1', 'B2', 'A2', 'A3', 'B3')
INPUTS = {}
CHECKS = []


def sha(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    result = digest.hexdigest()
    INPUTS[str(path)] = result
    return result


def read(path):
    sha(path)
    return json.loads(Path(path).read_bytes())


def check(name, condition, details=None):
    CHECKS.append({'name': name, 'passed': bool(condition), 'details': details})


def pins(mapping):
    return [path for path, expected in mapping.items() if sha(path) != expected]


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    started = time.perf_counter_ns()
    plan = read(HERE/'PLAN.json')
    frozen = read(HERE/'FROZEN.json')
    qualification_seal = read(HERE/'admin/QUALIFICATION_SEAL.json')
    baseline = read(HERE/'BASELINE.json')
    archive = read(HERE/'RUNTIME_ARCHIVE.json')
    check('2708_frozen_sources', len(frozen['files_sha256']) == 2708 and not pins(frozen['files_sha256']))
    check('126_qualification_pins', len(qualification_seal['files_sha256']) == 126 and not pins(qualification_seal['files_sha256']))
    check('9_protected_old_manifests', len(baseline['old_protected_manifests']) == 9 and not pins(baseline['old_protected_manifests']))
    bindings, manifests, product_maps = {}, {}, {}
    for arm, specification in plan['products'].items():
        check(arm+'_binding_file', sha(specification['path']) == specification['sha256'])
        binding = read(specification['path'])
        bindings[arm] = binding
        installed = Path(binding['install_root']).resolve()
        valid = True
        product_maps[arm] = {r['path']: r['sha256'] for r in binding['source_manifest']}
        for record in binding['source_manifest']:
            path = (installed/record['path']).resolve()
            valid = valid and path.is_relative_to(installed) and sha(path) == record['sha256']
        check(arm+'_141_installed_sources', len(binding['source_manifest']) == 141 and valid)
        identity = {'base_version': binding['base_version'], 'implementation_revision': binding['implementation_revision'], 'files': binding['source_manifest']}
        computed = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
        check(arm+'_aggregate_source_hash', computed == binding['source_sha256'])
        manifest = read(plan['inputs']['manifests'][arm])
        manifests[arm] = manifest
        check(arm+'_actual_manifest', manifest['comparison_arm'] == arm and manifest['product_binding'] == specification and manifest['expected_product_source_sha256'] == binding['source_sha256'])
        check(arm+'_current_inputs', all(sha(manifest[name]['path']) == manifest[name]['sha256'] for name in ('scene','capture','cameras','tasks','product_binding')))
        check(arm+'_12_36_48_6_limits', tuple(manifest['budget_contract'][name] for name in ('preparation_cap','formal_cap','total_cap','per_slot_cap')) == (12,36,48,6))
    changed = [path for path in product_maps['A'].keys() | product_maps['B'].keys() if product_maps['A'].get(path) != product_maps['B'].get(path)]
    check('only_projection_product_source_diff', changed == ['human_eye_plugin/live_spatial_mcp.py'], changed)
    check('same_scene_and_dependencies', all(manifests['A'][name] == manifests['B'][name] for name in ('scene','capture','cameras','tasks')) and bindings['A']['dependency_root'] == bindings['B']['dependency_root'])
    runtime = EXTERNAL/'formal'
    run, launch = read(runtime/'RUN_RESULT.json'), read(runtime/'LAUNCH_RESULT.json')
    check('actual_producer_schemas', run['schema'] == 'source-face-binding-six-route-v1' and launch['schema'] == 'source-face-binding-launch-v1')
    check('six_exact_records', [row['slot'] for row in run['records']] == list(ORDER) and run['planned_routes'] == run['planned_user_turns'] == 6)
    check('six_actual_routes_CLI', type(run['actual_routes']) is int and type(run['actual_CLI_processes']) is int and run['actual_routes'] == run['actual_CLI_processes'] == 6)
    check('completed_zero_retry', all(row['execution_state'] == 'completed' for row in run['records']) and run['outer_retries'] == launch['outer_retries'] == 0 and not run['terminal_errors'] and not launch['terminal_errors'] and not run['stop_remaining_reasons'])
    check('formal36_task48', run['maximum_formal_raster_attempts'] == 36 and run['maximum_qualification_and_formal_raster_attempts'] == 48)
    prompt = sha(plan['inputs']['prompt'])
    check('current_common_prompt', prompt == plan['expected_prompt_sha256'])
    summaries, tool_schemas, cli_profiles, threads, product_images = [], [], [], [], []
    attempts = {}
    terminal_handles = 0
    tool_names = ['active_observation','execute_python','read_images','render_views','scene_data']
    for row in run['records']:
        slot, arm = row['slot'], row['comparison_arm']
        folder, owner = runtime/slot, runtime/slot/'o'
        config = read(folder/'ACTOR_CONFIG.json')
        consumer = read(folder/'c/CONSUMER.json')
        observations, metrics = read(owner/'OBSERVATIONS.json'), read(owner/'METRICS.json')
        dependencies, tools = read(owner/'DEPENDENCIES.json'), read(owner/'TOOLS_SCHEMA.json')
        tool_schemas.append(tools)
        check(slot+'_P_role_and_arm', row['group'] == config['group'] == observations['group'] == 'P' and arm == config['comparison_arm'] == slot[0])
        check(slot+'_manifest_product', Path(config['input_manifest']).resolve() == Path(plan['inputs']['manifests'][arm]).resolve() and config['runtime_binding']['binding'] == plan['products'][arm] and config['expected_product_source_sha256'] == bindings[arm]['source_sha256'])
        check(slot+'_actual_limits', (config['max_tool_calls'],config['max_render_attempts'],config['phase_render_cap'],config['whole_render_cap']) == (12,6,36,48) and config['phase'] == 'formal' and config['worker_deadline_ns'] == row['deadline_ns'])
        check(slot+'_actual_actor_entry', str(HERE/'bootstrap.py') in row['actor_command'] and str(HERE/'bridge.py') in row['actor_command'])
        check(slot+'_prompt', consumer['input_sha256'] == prompt)
        check(slot+'_requested_CLI_profile', consumer['model'] == 'gpt-6.1-sol' and consumer['requested_effort'] == 'medium' and 'service_tier="default"' in consumer['argv'] and 'model_reasoning_effort="medium"' in consumer['argv'])
        check(slot+'_frozen_CLI_argv', consumer['argv'] == consumer['frozen_cli_argv'])
        cli_profiles.append([re.sub(r'\b[AB][123]\b', '<SLOT>', item) for item in consumer['argv']])
        options = ['--ignore-user-config','--ignore-rules','--strict-config','features.hooks=false','features.apps=false','features.memories=false','features.multi_agent=false','features.shell_tool=false','skills.bundled.enabled=false','approval_policy="never"','sandbox_mode="read-only"','forced_login_method="chatgpt"']
        check(slot+'_isolation_options', all(option in consumer['argv'] for option in options))
        check(slot+'_five_tools', consumer['expected_tool_names'] == tool_names and sorted(tool['name'] for tool in tools) == tool_names)
        dependency_root = Path(bindings[arm]['dependency_root']).resolve()
        check(slot+'_numeric_dependencies', dependencies['numpy_version'] == '2.3.5' and dependencies['PIL_version'] == '12.3.0' and dependencies['product_source_sha256'] == bindings[arm]['source_sha256'] and Path(dependencies['numpy_path']).resolve().is_relative_to(dependency_root) and Path(dependencies['PIL_path']).resolve().is_relative_to(dependency_root))
        check(slot+'_consumer_valid', consumer['valid_completion'] is True and row['outer_valid_completion'] is True and consumer['process_reaped'] is True and consumer['readers_stopped'] is True and consumer['consumer_pid'] == row['consumer_pid'])
        for key in ('owner_process_cleanup','consumer_process_cleanup'):
            value = row[key]
            pid = row['owner_pid'] if key.startswith('owner') else row['consumer_pid']
            valid = value['pid'] == pid and value['confirmed'] is True and value['reaped'] is True and value['process_handle_closed'] is True and value['exit_code'] == 0 and not value['errors'] and all(value['pipes_closed'][name] is True for name in ('stdin','stdout','stderr'))
            check(slot+'_'+key, valid)
            terminal_handles += int(valid)
        binding, exit_record = row['runtime_binding'], row['runtime_exit']
        actual_start = read(binding['STARTED_path'])
        check(slot+'_thin_actual_binding', binding['confirmed'] is True and binding['runtime_pid'] == actual_start['pid'] and binding['launcher_pid'] == row['consumer_pid'] and binding['actual_executable_sha256'] == sha(binding['actual_executable']) and binding == consumer['runtime_binding'])
        check(slot+'_thin_retained_handle', exit_record['confirmed'] is True and exit_record['handle_closed'] is True and exit_record['exited'] is True and exit_record['exit_code'] == 1 and exit_record == consumer['runtime_exit'])
        terminal_handles += int(exit_record['confirmed'] is True and exit_record['handle_closed'] is True)
        receipt = row['bridge_cleanup']
        check(slot+'_thin_self_EXIT_distinct', receipt['receipt_status'] == 'unknown' and receipt['missing_exit_count'] == 1 and receipt['confirmed'] is None)
        close = read(owner/'CLOSE.json')
        check(slot+'_owner_service_closed', close['confirmed'] is True and close['server_thread_stopped'] is True and not close['errors'] and row['owner_close_confirmed'] is True)
        check(slot+'_fresh_thread', consumer['thread_id'] == row['observed_thread_id'] and consumer['expected_thread_id'] is None)
        threads.append(consumer['thread_id'])
        check(slot+'_CLI_raw_and_final_bound', sha(folder/'c/stdout.raw.bin') == consumer['stdout_raw_sha256'] and (folder/'c/PUBLIC_FINAL.txt').read_bytes().decode('utf-8') == consumer['final'] and consumer['cli_output_matches_public_final'] is True)
        check(slot+'_source_and_wrapper_clear', row['input_readback_unchanged'] is True and not row['errors'] and not row['slot_wrapper_errors'] and not row['slot_wrapper_publication_errors'] and not row['batch_stop_reasons'])
        for suffix in ('BEFORE','AFTER'):
            proof = read(runtime/'slot_records'/slot/('ENTRY_PROOF_'+suffix+'.json'))
            check(slot+'_entry_proof_'+suffix, all(value is True for value in proof['checks'].values()))
        fact = row['between_slot_fact_check']
        fact_value = read(fact['path'])
        check(slot+'_bound_FACT_CHECK', sha(fact['path']) == fact['sha256'] and fact['passed'] is True and fact_value['passed'] is True and not fact_value['errors'] and not fact_value['stop_reasons'])
        private = observations['audit']
        check(slot+'_private_audit_clear', private['forbidden_old_evidence_reads'] == private['forbidden_old_writes'] == 0 and private['forbidden_product_calls'] == private['old_evidence_read_attempts'] == private['old_write_attempts'] == [])
        check(slot+'_owner_identity', observations['process_id'] == row['owner_pid'] and observations['source_inputs']['manifest_sha256'] == sha(plan['inputs']['manifests'][arm]))
        check(slot+'_business_limits', type(metrics['tool_attempts']) is int and len(metrics['tools']) == metrics['tool_attempts'] == len(consumer['tool_calls']) <= 12 and [tool['attempt'] for tool in metrics['tools']] == list(range(1,metrics['tool_attempts']+1)))
        reply_valid = True
        for tool, call in zip(metrics['tools'], consumer['tool_calls']):
            tool_root = owner/('tool_'+str(tool['attempt']).zfill(2))
            request = read(tool_root/'REQUEST.json')
            response_path = tool_root/'RESPONSE.json'
            response = read(response_path if response_path.exists() else tool_root/'ERROR_RESPONSE.json')
            item = call['item']
            reply_valid = reply_valid and request['params']['name'] == item['tool'] and request['params']['arguments'] == item['arguments'] and response['result']['content'] == item['result']['content']
            if not response['result']['isError']:
                reply_valid = reply_valid and item['error'] is None and item['status'] == 'completed'
        check(slot+'_actual_MCP_deliveries', reply_valid)
        check(slot+'_raster_limits', len(observations['render_attempts']) == metrics['new_renders'] == metrics['common']['render_attempts'] <= 6 and len(observations['frames']) == len(observations['render_attempts']) and not observations['runtime_faults'])
        request = read(owner/'tool_01/REQUEST.json')
        response = read(owner/'tool_01/RESPONSE.json')
        raw = read(owner/'product_call_01/SERVICE_RESULT.json')
        public = json.loads(response['result']['content'][0]['text'])
        check(slot+'_default_active_entry', request['params']['name'] == 'active_observation' and request['params']['arguments'].get('include_images', True) is True and response['result']['isError'] is False)
        expected_schema = 'active-observation-brief-v4' if arm == 'A' else 'active-observation-brief-v5'
        check(slot+'_actual_product_version', public['schema'] == expected_schema and raw['binding']['runtime_source_sha256'] == bindings[arm]['source_sha256'] and row['comparison_product_source_sha256'] == bindings[arm]['source_sha256'])
        regions = [dict(zip(public['regions']['columns'], values)) for values in public['regions']['rows']]
        source_regions = {region['roi_id']: region for region in raw['facts']['scope']['patch_support']['regions']}
        if arm == 'A':
            range_valid = 'source_triangle_index_ranges_semantics' not in public and all('source_triangle_index_ranges' not in region for region in regions)
        else:
            range_valid = public.get('source_triangle_index_ranges_semantics') == 'zero_based_object_local_inclusive; object_index_in_objects; scoped_to_this_binding'
            for region in regions:
                source = source_regions[region['roi_id']]
                expanded, previous = [], -2
                for start, stop in region['source_triangle_index_ranges']:
                    valid = type(start) is int and type(stop) is int and 0 <= start <= stop and start > previous+1 and stop-start+1 <= len(source['triangle_indices'])-len(expanded)
                    range_valid = range_valid and valid
                    if valid:
                        expanded.extend(range(start,stop+1))
                    previous = stop
                range_valid = range_valid and source['object_index'] == region['object_index'] and expanded == sorted(source['triangle_indices']) and len(expanded) == region['triangle_count']
        check(slot+'_actual_default_source_binding', range_valid and len(regions) == len(source_regions) == 61)
        image_rows = [dict(zip(public['images']['columns'], values)) for values in public['images']['rows']]
        image_valid = len(raw['frames']) == len(image_rows)
        for frame, image in zip(raw['frames'], image_rows):
            block = response['result']['content'][image['native_content_block_index']]
            image_valid = image_valid and frame['image_ref'] == image['image_ref'] and sha(frame['image_path']) == image['image_sha256'] and base64.b64decode(block['data'],validate=True) == Path(frame['image_path']).read_bytes()
        check(slot+'_actual_product_images', image_valid)
        product_images.append([(frame['view_name'],frame['image_sha256']) for frame in raw['frames']])
        for attempt in observations['render_attempts']:
            check(slot+'_completed_attempt_'+str(attempt['attempt_id']), attempt['status'] == 'completed' and attempt['process_id'] == row['owner_pid'] and attempt['group'] == 'P' and attempt['phase'] == 'formal' and attempt['completed_ns'] < config['worker_deadline_ns'] and sha(attempt['PNG']) == attempt['PNG_sha256'] and sha(attempt['NPZ']) == attempt['NPZ_sha256'])
            attempts[attempt['global_attempt']] = attempt
        summaries.append({'slot':slot,'comparison_arm':arm,'actual_group':'P','product_source_sha256':bindings[arm]['source_sha256'],'actual_brief_schema':public['schema'],'default_binding_received':arm=='B','region_bindings_checked':len(regions),'business_tools':metrics['tool_attempts'],'business_errors':sum(tool['is_error'] for tool in metrics['tools']),'rasters':len(observations['render_attempts']),'owner_pid':row['owner_pid'],'CLI_pid':row['consumer_pid'],'thin_pid':binding['runtime_pid'],'owner_exit':row['owner_process_cleanup']['exit_code'],'CLI_exit':row['consumer_process_cleanup']['exit_code'],'thin_handle_exit':exit_record['exit_code'],'thin_self_EXIT_status':receipt['receipt_status'],'provider_resolved_effort':consumer['resolved_effort']})
    check('same_public_tool_schemas', all(schema == tool_schemas[0] for schema in tool_schemas))
    check('same_actual_CLI_config_and_permissions', all(profile == cli_profiles[0] for profile in cli_profiles))
    check('six_unique_conversation_threads', len(threads) == len(set(threads)) == 6)
    check('same_product_view_selection_and_PNGs', all(images == product_images[0] for images in product_images))
    qualification = read(HERE/'admin/QUALIFICATION.json')
    check('final_qualification_bound', qualification['passed'] is True and qualification['status'] == 'qualified' and qualification['source_freeze_sha256'] == sha(HERE/'FROZEN.json') and sha(qualification['qualification_run']['path']) == qualification['qualification_run']['sha256'])
    qualification_rasters, qualification_handles = 0, 0
    for path in sorted((EXTERNAL/'preparation').glob('Q*/QUALIFICATION_RUN.json')):
        pair = read(path)
        check(path.parent.name+'_qualification_transport', pair['transport_passed'] is True and not pair['errors'] and pair['actual_model_calls'] == 0 and pair['actual_owners'] == 2 and pair['outer_retries'] == 0)
        for record in pair['records']:
            arm = record['comparison_arm']
            cleanup = record['process_cleanup']
            check(path.parent.name+'_'+arm+'_qualification_owner', record['transport_passed'] is True and record['group'] == 'P' and record['product_source_sha256'] == bindings[arm]['source_sha256'] and cleanup['confirmed'] is True and cleanup['reaped'] is True and cleanup['process_handle_closed'] is True and cleanup['exit_code'] == 0 and record['owner_close']['confirmed'] is True)
            qualification_handles += int(cleanup['confirmed'] is True and cleanup['process_handle_closed'] is True)
            config = read(path.parent/('Q'+arm)/'ACTOR_CONFIG.json')
            check(path.parent.name+'_'+arm+'_qualification_caps', config['whole_render_cap'] == 48 and config['phase_render_cap'] == 12 and config['max_render_attempts'] == 6)
            observations = read(Path(record['owner_output'])/'OBSERVATIONS.json')
            check(path.parent.name+'_'+arm+'_qualification_count', len(observations['render_attempts']) == record['actual_rasters'] <= 6)
            qualification_rasters += len(observations['render_attempts'])
            for attempt in observations['render_attempts']:
                attempts[attempt['global_attempt']] = attempt
    ledger = [read(path) for path in sorted((EXTERNAL/'raster_budget').glob('attempt_*/INTENT.json'))]
    formal_rasters = sum(row['rasters'] for row in summaries)
    check('cumulative_ledger_sequence', len(ledger) == qualification_rasters+formal_rasters and [row['global_attempt'] for row in ledger] == list(range(1,len(ledger)+1)) and set(attempts) == set(range(1,len(ledger)+1)))
    check('actual_phase_caps', qualification_rasters <= 12 and formal_rasters <= 36 and len(ledger) <= 48 and qualification_rasters == run['preparation_raster_attempts'] == qualification['cumulative_qualification_rasters'])
    reservation_valid, product_reservations, native_reservations = True, 0, 0
    for reserved in ledger:
        actual = attempts[reserved['global_attempt']]
        for key in ('global_attempt','attempt_id','phase','group','owner_output','process_id','view_name','origin','source_capture_sha256','source_scene_sha256'):
            reservation_valid = reservation_valid and reserved[key] == actual[key]
        if reserved['origin'] == 'native':
            reservation_valid = reservation_valid and reserved['ref'] == actual['ref']
            native_reservations += 1
        else:
            source = read(Path(actual['owner_output'])/'product_call_01/SERVICE_RESULT.json')
            reservation_valid = reservation_valid and reserved['ref'] == 'image-'+str(reserved['attempt_id']).zfill(2) and any(frame['view_name'] == actual['view_name'] and frame['image_ref'] == actual['ref'] and frame['image_sha256'] == actual['PNG_sha256'] and frame['arrays_sha256'] == actual['NPZ_sha256'] for frame in source['frames'])
            product_reservations += 1
    check('all_reservations_bind_real_registered_frames', reservation_valid)
    check('18_formal_handles_2_qualification_handles', terminal_handles == 18 and qualification_handles == 2)
    archive_errors, credential_paths, containers = [], [], 0
    credential_pattern = r'(^|[/\\])(auth\.json|credentials|\.env|secrets)([/\\]|$)'
    for record in archive['files']:
        source, target = Path(record['original_path']), HERE/record['archive_path']
        if source.stat().st_size != record['bytes'] or target.stat().st_size != record['bytes'] or sha(source) != record['sha256'] or sha(target) != record['sha256']:
            archive_errors.append(record['relative_path'])
        if re.search(credential_pattern, record['relative_path'], re.I):
            credential_paths.append(record['relative_path'])
        if source.suffix.lower() in ('.zip','.whl','.npz'):
            with zipfile.ZipFile(source) as package:
                containers += 1
                for member in package.namelist():
                    if re.search(credential_pattern,member,re.I):
                        credential_paths.append(record['relative_path']+'::'+member)
    check('970_archived_files_byte_exact', archive['file_count'] == len(archive['files']) == 970 and not archive_errors)
    check('25394343_archive_bytes', archive['bytes'] == sum(record['bytes'] for record in archive['files']) == 25394343)
    check('no_auth_paths_in_archive_and_containers', not credential_paths, {'containers_checked':containers})
    check('protected_sources_unchanged_after_review', not pins(frozen['files_sha256']) and not pins(qualification_seal['files_sha256']) and not pins(baseline['old_protected_manifests']))
    result = {'schema':'source-face-binding-independent-runtime-review-v1','passed':all(record['passed'] for record in CHECKS),'checks':CHECKS,'check_count':len(CHECKS),'passed_checks':sum(record['passed'] for record in CHECKS),'failed_checks':[record for record in CHECKS if not record['passed']],'source_files_checked':len(frozen['files_sha256']),'qualification_pins_checked':len(qualification_seal['files_sha256']),'old_protected_manifests_checked':len(baseline['old_protected_manifests']),'product_sources_checked':{arm:len(binding['source_manifest']) for arm,binding in bindings.items()},'changed_product_source_paths':changed,'formal_terminal_handles_confirmed':terminal_handles,'qualification_owner_handles_confirmed':qualification_handles,'slots':summaries,'actual_counts':{'formal_routes':6,'formal_CLI':6,'unrun':sum(record['execution_state']=='not_run' for record in run['records']),'qualification_rasters':qualification_rasters,'formal_rasters':formal_rasters,'all_rasters':len(ledger),'product_reserved_refs_bound_to_producer':product_reservations,'native_reserved_refs_unchanged':native_reservations,'archive_files':archive['file_count'],'archive_bytes':archive['bytes']},'credential_paths':credential_paths,'thin_exit_interpretation':'Six self EXIT receipts are missing/unknown. Six retained process handles independently confirm actual exit1 and handle closure.','review_scope':'Read-only saved source, arm delivery, isolated CLI configuration, protocol replies, retained process proofs, quota ledger and archive bytes. No answer scoring, saved-evidence evaluation, usage-field analysis or time ranking.','association':'Reviewer authored directed acceptance and A normalization, independently reviewing runtime wiring written by a separate author.','new_calls':{'score':0,'evaluator':0,'model':0,'observe':0,'raster':0},'limitations':['Provider resolved_effort remains null while the request explicitly sets medium/default.','This review checks retained proof records and does not reopen finished processes.'],'inputs_sha256':dict(sorted(INPUTS.items())),'review_started_ns':started,'before_publication_ns':time.perf_counter_ns()}
    save(HERE/'FINAL_RUNTIME_REVIEW.json',result)
    print(json.dumps({'passed':result['passed'],'checks':len(CHECKS),'failed':[record['name'] for record in result['failed_checks']],'actual_counts':result['actual_counts'],'sha256':sha(HERE/'FINAL_RUNTIME_REVIEW.json')}))


if __name__ == '__main__':
    main()
