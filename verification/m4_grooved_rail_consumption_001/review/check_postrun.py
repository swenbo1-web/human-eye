"""Read terminal lifecycle, hashes and anonymous envelope structure only."""

import hashlib
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
checks = {}


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(name, value):
    checks[name] = bool(value)


def normalized(value):
    return {'unit_scale_m': value.get('unit_scale_m', value.get('scale_length')),
            'objects': sorted([{
                'name': row['name'], 'vertices_local': row['vertices_local'],
                'matrix_world': row['matrix_world'], 'faces': row.get('faces', row.get('triangles')),
            } for row in value['objects']], key=lambda row: row['name'])}


def existing(path):
    return read(path) if path.is_file() else None


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf8')


def main():
    terminal = read(BATCH / 'FORMAL_PROCESS.json')
    if terminal['status'] != 'terminal':
        raise RuntimeError('formal_controller_still_running')
    public = BATCH / 'runtime/handoff_01/public'
    private = BATCH / 'runtime/handoff_01/private'
    if not (public / 'INDEX.json').is_file() or not (private / 'PROVENANCE.json').is_file():
        raise RuntimeError('anonymous_handoff_not_yet_published')
    plan = read(BATCH / 'PLAN.json')
    digest = sha(BATCH / 'PLAN.json')
    check('frozen_PLAN_FREEZE_GO', digest == read(BATCH / 'FREEZE.json')['plan_sha256'] == read(BATCH / 'GO.json')['plan_sha256'])
    check('all_frozen_dispatch_hashes', all(sha(BATCH / name) == value for name, value in plan['dispatch_input_sha256'].items()))
    check('all_frozen_external_hashes', all(sha(Path(name)) == value for name, value in plan['external_input_sha256'].items()))
    check('all_protected_and_qualification_57_hashes', all(sha(Path(name)) == value for name, value in read(BATCH / 'preflight/PROTECTED_BEFORE.json').items()))
    source = read(BATCH / 'preflight/SOURCE_BINDING.json')
    ready = read(BATCH / 'installations/P_READY.json')
    check('same_137_worktree_and_installed_sources', len(source['source_manifest']) == 137 and all(
        sha(ROOT / row['path']) == sha(Path(ready['install_root']) / row['path']) == row['sha256'] for row in source['source_manifest']))

    run = read(BATCH / 'RUN_RESULT.json')
    records = run['records']
    sequence = plan['sequence']
    check('unique_frozen_execution_prefix', len(records) <= len(sequence) == 6
          and len({row['cell'] for row in records}) == len(records)
          and all(all(row[key] == slot[key] for key in ('cell', 'group', 'round', 'task'))
                  for row, slot in zip(records, sequence, strict=False)))
    check('no_replacement_or_extra_slots', run['maximum_consumers'] == 6 and run['no_replacements'] is True)
    check('terminal_record_counts', run['started_cells'] == len(records)
          and terminal['started_cells'] == len(records)
          and run['all_planned_dispatched'] == (len(records) == 6))
    check('stopped_prefix_retains_stop', len(records) == 6 or run['stop'] is not None)
    expected_geometry = normalized(read(BATCH / 'scoring/ACTUAL_SNAPSHOT.json'))
    observations, anomalies = [], []
    completed = 0
    thin_unknown, thin_rejected, missing_exit_receipts = 0, 0, 0
    public_admin = {'group', 'external_group', 'cell', 'round', 'usage', 'usage_rows',
                    'elapsed_ns', 'started_ns', 'ended_ns', 'wall_ns', 'fees'}
    for record in records:
        cell = record['cell']
        folder = BATCH / 'cells' / cell
        consumer = existing(folder / 'CONSUMER.json')
        finish = existing(folder / 'OWNER_FINISH.json')
        close = existing(folder / 'owner/CLOSE.json')
        initial = existing(folder / 'owner/INITIAL.json')
        final = existing(folder / 'owner/FINAL.json')
        identity = existing(folder / 'owner/IDENTITY.json')
        config = existing(folder / 'ACTOR_CONFIG.json')
        launched = (folder / 'ACTOR_LAUNCH.json').exists() or finish is not None
        completed_here = bool(consumer and consumer.get('status') == 'completed'
                              and consumer.get('valid_completion') is True and not record['errors'])
        completed += completed_here
        item = {'cell': cell, 'execution_completed': completed_here,
                'driver_error_types': [row.get('type', row.get('stage')) for row in record['errors']],
                'within_original_cell_deadline': record.get('within_570s'),
                'actor_launch_or_finish_record_present': launched}
        if consumer is not None:
            check(cell + '_consumer_slot_binding', all(consumer[key] == record[key] for key in ('cell', 'group', 'round', 'task')))
            check(cell + '_prompt_and_zero_image_metadata', consumer['input_sha256'] == plan['inputs']['prompt_sha256']
                  and all(consumer.get(key) == 0 for key in ('public_image_count', 'public_image_bytes', 'input_image_count', 'input_image_bytes'))
                  and '--image' not in consumer['argv'])
            item['consumer_status'] = consumer.get('status')
            item['consumer_exit'] = {key: consumer.get(key) for key in ('exit_code', 'process_reaped', 'readers_stopped',
                'valid_completion', 'safe_to_continue', 'deadline_timer_fired', 'mutation_unknown', 'cli_output_matches_public_final')}
            item['consumer_protocol_errors_present'] = bool(consumer.get('bridge_protocol_errors'))
            item['unexpected_tool_deviation_present'] = bool(consumer.get('unexpected_tool_deviations'))
            cleanup = consumer.get('bridge_cleanup', {})
            thin_status = cleanup.get('receipt_status', 'unknown')
            item['thin_EXIT'] = {'confirmed': cleanup.get('confirmed'), 'receipt_status': thin_status,
                                 'missing_exit_count': cleanup.get('missing_exit_count')}
            thin_unknown += thin_status == 'unknown'
            thin_rejected += thin_status == 'rejected'
            missing_exit_receipts += cleanup.get('missing_exit_count', 0)
            check(cell + '_CLI_and_reader_reaped', consumer.get('process_reaped') is True and consumer.get('readers_stopped') is True)
            check(cell + '_protocol_state_recorded', not consumer.get('bridge_protocol_errors')
                  and not consumer.get('unexpected_tool_deviations') and not consumer.get('mutation_unknown'))
        if config is not None:
            check(cell + '_asset_config_binding', config['asset_sha256'] == plan['inputs']['scene_sha256'])
        if identity is not None:
            check(cell + '_owner_asset_and_ordinary_serve', identity['asset_sha256'] == plan['inputs']['scene_sha256']
                  and identity['product_spatial_task_only'] is False and identity['private_geometry_warmup'] is False)
        if launched:
            owner_confirmed = bool(finish and finish.get('confirmed') and finish.get('exit_code') == 0
                                   and close and close.get('confirmed'))
            item['independent_owner_close_confirmed'] = owner_confirmed
            check(cell + '_independent_owner_exit', owner_confirmed)
        if close is not None:
            native = close.get('native_close') or {}
            worker = close.get('worker_closed') or {}
            check(cell + '_native_owned_exit_and_files', native.get('process_reaped') is True and native.get('exit_code') == 0
                  and native.get('source_file_unchanged') is True and native.get('protected_files_unchanged') is True)
            check(cell + '_actual_initial_final_geometry', initial is not None and final is not None
                  and normalized(initial) == normalized(final) == expected_geometry
                  and close.get('geometry_unchanged') is True and close.get('asset_unchanged') is True
                  and worker.get('initial_geometry_fingerprint') == worker.get('final_geometry_fingerprint')
                  and worker.get('poisoned') is False)
            construction = close.get('image_construction') or {}
            check(cell + '_recorded_zero_new_images', close.get('zero_new_images_budget_met') is True
                  and construction.get('observed') is False and construction.get('status') == 'not_observed_in_recorded_scope')
            product = close.get('plugin_close')
            runtime = close.get('product_runtime_exit')
            if product is not None or runtime is not None:
                check(cell + '_actual_product_and_retained_runtime_exit', bool(product and runtime)
                      and product.get('confirmed') is True and product.get('process_reaped') is True
                      and product.get('reader_stopped') is True and product.get('exit_code') == 0
                      and all(runtime.get(key) is True for key in ('confirmed', 'exited', 'handle_closed'))
                      and runtime.get('exit_code') == 0)
            elif consumer is not None and record['group'] == 'P':
                check(cell + '_applicable_product_exit_proof_present', False)
        rpc = existing(folder / 'owner/plugin/RPC.json')
        if rpc is not None:
            check(cell + '_product_channel_not_poisoned', rpc.get('poisoned') is False)
        product_tools = existing(folder / 'owner/PLUGIN_TOOLS.json')
        if product_tools is not None:
            selected = [tool for tool in product_tools['result']['tools'] if tool['name'] == 'human_eye_scene_observe']
            check(cell + '_actual_product_declaration', selected == read(BATCH / 'schemas/P_PUBLIC_TOOLS.json'))
        list_observations = []
        for bridge in (folder / 'attachments').glob('bridge_*'):
            # Only inspect the request method and tools/list reply. Business
            # arguments, results, answers and usage are never selected here.
            for tx in sorted(bridge.glob('*/TX.bin')):
                request = read(tx)
                if request.get('method') == 'tools/list':
                    rx = tx.with_name('RX.bin')
                    match = rx.is_file() and read(rx).get('result', {}).get('tools') == read(BATCH / ('schemas/' + record['group'] + '_CONSUMER_TOOLS.json'))
                    list_observations.append(match)
        item['actual_tools_list_observed'] = bool(list_observations)
        if list_observations:
            check(cell + '_actual_consumer_tools_list', all(list_observations))
        if completed_here:
            check(cell + '_completed_execution_flags', consumer['safe_to_continue'] is True
                  and consumer['exit_code'] == 0 and record['within_570s'] is True)
            check(cell + '_completed_execution_has_actual_tool_declaration', bool(list_observations))
        else:
            anomalies.append({'cell': cell, 'kind': 'execution_failed_or_incomplete',
                              'consumer_status': None if consumer is None else consumer.get('status'),
                              'driver_error_types': item['driver_error_types']})
        observations.append(item)
    for slot in sequence[len(records):]:
        check(slot['cell'] + '_not_run_tail_has_no_cell_material', not (BATCH / 'cells' / slot['cell']).exists())

    provenance = read(private / 'PROVENANCE.json')
    index = read(public / 'INDEX.json')
    actual_public = {path.relative_to(public).as_posix(): sha(path) for path in public.rglob('*') if path.is_file()}
    check('public_exact_provenance_file_hashes', actual_public == provenance['public_files_sha256'])
    check('handoff_script_and_control_hashes', provenance['script_sha256'] == sha(BATCH / 'runtime/pack_quality.py')
          and all(sha(BATCH / name) == value == sha(private / 'control' / name) for name, value in provenance['control_sha256'].items()))
    mapping = read(BATCH / 'private/ANON_MAP.json')
    check('private_frozen_map_unchanged', provenance['fixed_anonymous_map'] == mapping)
    check('public_six_slots_and_no_scoring', index['fixed_slots'] == 6 and len(index['answers']) == 6
          and index['scoring_performed'] is False and not (set(index) & public_admin)
          and {row['anonymous_id'] for row in index['answers']} == {row['anonymous_id'] for row in mapping['rows']})
    rows_by_id = {row['mapping']['anonymous_id']: row for row in provenance['answers']}
    for entry in index['answers']:
        anonymous = entry['anonymous_id']
        audit = rows_by_id[anonymous]
        folder = BATCH / 'cells' / audit['mapping']['cell']
        originals = {path.relative_to(folder).as_posix(): sha(path) for path in folder.rglob('*') if path.is_file()} if folder.exists() else {}
        with zipfile.ZipFile(private / 'raw' / (anonymous + '.zip')) as archive:
            zipped = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}
        check(anonymous + '_complete_original_archive_hashes', originals == zipped == audit['source_files_sha256'])
        check(anonymous + '_public_administrative_envelope_masking', not (set(entry) & public_admin))
        evidence = read(public / anonymous / entry['evidence_file'])
        envelope_clear = not (set(evidence) & public_admin)
        for attempt in evidence['owner_attempts']:
            envelope_clear &= not bool(set(attempt) & public_admin)
            request = attempt.get('request')
            if isinstance(request, dict):
                envelope_clear &= not bool(set(request) & {'id', 'jsonrpc', '_meta'})
                envelope_clear &= '_meta' not in request.get('params', {})
            for response in attempt['responses']:
                envelope_clear &= not bool(set(response['value']) & {'id', 'jsonrpc', '_meta'})
        for event in evidence['public_tool_events']:
            envelope_clear &= not bool(set(event) & public_admin)
        check(anonymous + '_known_RPC_and_event_envelopes_masked', envelope_clear)
        consistency = read(public / anonymous / entry['source_consistency_file'])
        worker = consistency.get('CLOSE', {}).get('worker_closed')
        check(anonymous + '_known_worker_administrative_fields_masked', not isinstance(worker, dict)
              or not bool(set(worker) & {'pid', 'closed_ns', 'original_deadline_ns'}))
        if entry['answer_file'] is not None:
            check(anonymous + '_final_original_byte_hash', sha(public / anonymous / entry['answer_file'])
                  == entry['answer_original_sha256'] == originals.get('PUBLIC_FINAL.txt'))
        for name, expected in audit['files_sha256'].items():
            check(anonymous + '_published_file_' + name, sha(public / anonymous / name) == expected)
    for item in index['scoring_materials']:
        check(item['file'] + '_exact_frozen_scoring_bytes', sha(public / item['file']) == item['sha256'] == sha(BATCH / item['source_path']))
    check('public_common_prompt_exact', (public / index['tasks'][0]['prompt']).read_bytes() == (BATCH / plan['inputs']['prompt']).read_bytes())
    files = [{'path': name, 'bytes': (public / name).stat().st_size, 'sha256': value} for name, value in sorted(actual_public.items())]
    packet_sha = hashlib.sha256(json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8')).hexdigest()
    result = {
        'passed': all(checks.values()), 'checks': checks,
        'failed_checks': [name for name, value in checks.items() if not value],
        'plan_sha256': digest, 'public_packet_sha256': packet_sha,
        'execution_counts': {'completed': completed, 'execution_failed_or_incomplete': len(records) - completed,
                             'not_run': 6 - len(records), 'entered': len(records)},
        'execution_stop': run['stop'], 'execution_anomalies': anomalies,
        'thin_EXIT': {'unknown_cells': thin_unknown, 'rejected_cells': thin_rejected, 'missing_receipts': missing_exit_receipts},
        'lifecycle_observations': observations,
        'reviewer_source_sha256': sha(Path(__file__)),
        'model_Blender_product_CLI_launches': 0,
        'quality_scoring_performed': False, 'cost_or_adoption_analysis_performed': False,
        'scope': 'Only lifecycle, source and file hashes, zero-image metadata, actual declarations and known administrative envelope structure. Answers, business code/results, usage and cost fields were not selected or compared.',
    }
    with (HERE / 'POSTRUN_CHECK.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    summary = '\n'.join([
        '# 独立执行完整性复核', '',
        '复核' + ('通过。' if result['passed'] else '存在待处理项，见检查记录。'), '',
        f"执行记录保留完成 {completed}、失败或未完成 {len(records) - completed}、未运行 {6 - len(records)}。质量评分待独立质量审查。", '',
        f"全部 {len(plan['dispatch_input_sha256'])} 个本地冻结输入、{len(plan['external_input_sha256'])} 个外部依赖、资格保护文件及 137 个源码与安装文件已核对。实际声明、初末几何、owned 进程退出与图片记录按各自回执检查。", '',
        f'薄客户端 EXIT 的 unknown 格数为 {thin_unknown}，缺失回执 {missing_exit_receipts} 份，rejected 格数为 {thin_rejected}。这些状态单列保留，实际 owner、Blender worker 和适用产品 runtime 的退出依各自证据判断。', '',
        '匿名 public 文件与私有 PROVENANCE、原件归档及冻结映射的哈希对应一致性已检查。检查仅覆盖已知行政信封位置，业务正文保持未读。工具名称与业务内容仍可能暴露路线。', '',
        'public packet SHA256 为 `' + packet_sha + '`。', '',
        '本审查新增 CLI、模型、Blender 和产品运行均为 0。答案质量、分组行为、时间、usage、采用与收益留待后续阶段。', '',
        '失败检查为 `' + json.dumps(result['failed_checks'], ensure_ascii=False) + '`。',
        '必要执行异常为 `' + json.dumps(anomalies, ensure_ascii=False) + '`。', '',
        '检查源码 SHA256 为 `' + result['reviewer_source_sha256'] + '`。', '',
    ])
    with (HERE / 'POSTRUN_REVIEW.md').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(summary)
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'execution_counts': result['execution_counts'],
                      'thin_EXIT': result['thin_EXIT'], 'public_packet_sha256': packet_sha, 'failed_checks': result['failed_checks']}))


if __name__ == '__main__':
    main()
