"""Independent, standard-library audit of saved evidence; never import/run product code.

All evidence is read from fixed Git blobs and compared to the named saved copies.
Only this script's directory receives outputs. No geometry is recomputed.
"""
import datetime as dt
import hashlib
import json
import statistics
import subprocess
from pathlib import Path

ROOT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
QUALITY_ROOT = Path('D:/hefe')
OUT = Path(__file__).resolve().parent
BASE = 'verification/m4_spatial_fact_consumption_001'
EVIDENCE = '5cdf62f311f94890ca569d06c1a858f1578225e4'
ANALYSIS = 'a44a6138b9d354ecc98a4fbd76095f0536d6973f'
SEAL_COMMIT = '3a4b090532e01920110e6ee2be1702bc1c45c265'
SEAL_PREFIX = 'verification/fixes/20261112_m4_spatial_fact_consumption_review'
INPUTS = {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def raw(path, commit=EVIDENCE, root=ROOT):
    key = commit + ':' + path
    data = git('show', key)
    assert (root / path).read_bytes() == data, ('working file differs', key)
    INPUTS[key] = dict(commit=commit, relative_path=path,
                       actual_verification_path=str(root / path), bytes=len(data),
                       sha256=sha(data), matches_fixed_blob=True)
    return data


def read(path, commit=EVIDENCE, root=ROOT):
    return json.loads(raw(path, commit, root).decode('utf-8-sig'))


def saved(path):
    return read(BASE + '/' + path)


def lines(path):
    return [json.loads(x) for x in raw(BASE + '/' + path).splitlines() if x]


def stats(values):
    return dict(count=len(values), minimum=min(values), median=statistics.median(values),
                maximum=max(values), total=sum(values))


def delta(n, p):
    return dict(N=n, P=p, P_minus_N=p-n, reduction_percent=(n-p)*100/n)


def main():
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    # The original author's analysis is not the calculation input.
    seal = read(SEAL_PREFIX + '/QUALITY_SEAL.json', SEAL_COMMIT, QUALITY_ROOT)
    seal_copy = read(BASE + '/cost_review_01/quality_source/QUALITY_SEAL.json', ANALYSIS)
    assert seal_copy == seal
    assert seal['author_evidence_commit'] == EVIDENCE
    assert not seal['private_map_cost_usage_read_before_seal']
    assert seal['quality']['complete_correct'] == 6
    root_plan = (QUALITY_ROOT / 'docs/M4_SPATIAL_FACT_CONSUMPTION_001_PLAN.md').read_bytes()
    assert sha(root_plan) == seal['root_plan_sha256']
    assert root_plan == raw(BASE + '/ROOT_PLAN.md')
    score_files = {}
    for kind in ('independent_quality', 'root_quality'):
        path = SEAL_PREFIX + '/' + kind + '/SCORES.json'
        data = raw(path, SEAL_COMMIT, QUALITY_ROOT)
        expected = next(x['sha256'] for x in seal['files'] if x['path'] == path)
        assert sha(data) == expected
        score_files[kind] = json.loads(data)
    scores = {x['anonymous_id']: x for x in score_files['independent_quality']['answers']}
    root_scores = {x['anonymous_id']: x for x in score_files['root_quality']['scores']}
    seq = saved('SEQUENCE.json')['sequence']
    amap = saved('private/ANON_MAP.json')
    freeze = saved('FREEZE.json')
    assert sha(raw(BASE + '/private/ANON_MAP.json')) == freeze['anonymous_map_sha256']
    assert [{k: r[k] for k in ('cell', 'group', 'round', 'task')} for r in amap['rows']] == seq
    assert [(r['group'], r['round']) for r in seq] == [('N',1),('P',1),('P',2),('N',2),('N',3),('P',3)]
    mapping = {r['cell']: r for r in amap['rows']}
    run = saved('RUN_RESULT.json')
    contract = saved('BENEFIT_CONTRACT.json')
    plan = saved('PLAN.json')
    assert run['stop'] is None and run['started_cells'] == run['maximum_consumers'] == 6
    assert run['all_planned_dispatched'] and run['no_replacements']
    assert len(run['records']) == 6
    # Verify the saved source defining timestamp semantics; do not execute it.
    for rel in ('runtime/driver.py', 'runtime/consumer_transport.py', 'runtime/actor.py'):
        raw(BASE + '/' + rel)
    names = git('ls-tree', '-r', '--name-only', EVIDENCE, '--', BASE + '/cells').decode().splitlines()
    cells = []
    for spec, r in zip(seq, run['records']):
        cell = spec['cell']
        pre = 'cells/' + cell + '/'
        assert all(r[k] == v for k, v in spec.items())
        c = saved(pre + 'CONSUMER.json')
        launch = saved(pre + 'ACTOR_LAUNCH.json')
        config = saved(pre + 'ACTOR_CONFIG.json')
        finish = saved(pre + 'OWNER_FINISH.json')
        close = saved(pre + 'owner/CLOSE.json')
        native = saved(pre + 'owner/native/SESSION.json')
        worker = saved(pre + 'owner/native/WORKER_CLOSED.json')
        ev = lines(pre + 'events.jsonl')
        assert c == r['consumer'] and finish == r['finish'] and finish['close'] == close
        assert c['owner_finish'] == finish and close['worker_closed'] == worker
        assert c['status'] == 'completed' and c['valid_completion'] and not r['errors']
        assert not c['errors'] and not c['unexpected_tool_deviations']
        assert len([e for e in ev if e['event']['type'] == 'turn.started']) == 1
        turns = [e for e in ev if e['event']['type'] == 'turn.completed']
        assert len(turns) == 1, 'No summing cumulative snapshots allowed'
        usage = turns[0]['event']['usage']
        assert usage == c['usage'] and c['usage_rows'] == [usage]
        assert all(type(v) is int and v >= 0 for v in usage.values())
        assert usage['cached_input_tokens'] <= usage['input_tokens']
        assert usage['reasoning_output_tokens'] <= usage['output_tokens']
        assert usage['cache_write_input_tokens'] == 0
        assert turns[0]['perf_ns'] == c['turn_completed_ns']
        final_events = [e for e in ev if e['event']['type'] == 'item.completed'
                        and e['event'].get('item', {}).get('type') == 'agent_message']
        assert final_events[-1]['perf_ns'] == c['final_received_ns']
        assert final_events[-1]['event']['item']['text'] == c['final']
        final_raw = raw(BASE + '/' + pre + 'PUBLIC_FINAL.txt')
        assert final_raw.decode('utf-8') == c['final']
        assert final_raw == raw(BASE + '/' + pre + 'final.txt')
        anonymous = mapping[cell]['anonymous_id']
        public = 'runtime/handoff_01/public/' + anonymous + '/'
        assert final_raw == raw(BASE + '/' + public + 'answer.txt')
        for file_name, expected in scores[anonymous]['file_sha256'].items():
            assert sha(raw(BASE + '/' + public + file_name)) == expected
        tool_public = saved(public + 'tool_evidence.json')
        assert scores[anonymous]['quality_status'] == root_scores[anonymous]['status'] == 'complete_correct'
        assert scores[anonymous]['requested_fact_counts']['total_correct'] == 13
        start, end, deadline = r['cell_started_ns'], r['cell_ended_ns'], r['worker_deadline_ns']
        assert start == launch['cell_started_ns'] == launch['started_ns']
        assert deadline == launch['worker_deadline_ns'] == native['deadline_ns'] == worker['original_deadline_ns']
        assert deadline-start == 570 * 10**9
        assert c['deadline_ns']-c['started_ns'] == 450 * 10**9
        assert launch['actor_startup_deadline_ns'] == min(deadline, launch['prepare_started_ns']+40*10**9)
        timeline = [start, c['started_ns'], c['popen_ns'], c['prompt_submitted_ns'],
                    c['final_received_ns'], c['turn_completed_ns'], c['process_exit_ns'],
                    c['cleanup_end_ns'], end]
        assert all(a <= b for a, b in zip(timeline, timeline[1:]))
        duration = end-start
        assert duration == r['full_cell_wall_ns'] == c['total_task_wall_ns']
        assert c['pre_consumer_setup_ns'] == c['started_ns']-start
        assert c['wall_ns'] == c['cleanup_end_ns']-c['started_ns']
        assert c['prompt_to_final_ns'] == c['final_received_ns']-c['prompt_submitted_ns']
        assert end < deadline and c['process_exit_ns'] < c['deadline_ns']
        assert c['process_reaped'] and c['exit_code'] == 0 and c['readers_stopped']
        assert not c['deadline_timer_fired'] and finish['confirmed'] and finish['exit_code'] == 0
        assert close['confirmed'] and not close['errors']
        assert close['native_close']['process_reaped'] and close['native_close']['exit_code'] == 0
        assert c['cleanup_end_ns'] <= worker['closed_ns'] <= close['ended_ns'] <= end
        nc_names = [p for p in names if p.startswith(BASE+'/'+pre+'owner/native/CLOSE_') and p.endswith('.json')]
        assert len(nc_names) == 1
        assert read(nc_names[0]) == close['native_close']
        if spec['group'] == 'P':
            assert close['plugin_close']['confirmed'] and close['plugin_close']['process_reaped']
            assert close['plugin_close']['exit_code'] == 0
            runtime = close['product_runtime_exit']
            assert runtime['confirmed'] and runtime['exited'] and runtime['exit_code'] == 0
            assert c['cleanup_end_ns'] <= close['plugin_close']['ended_ns'] <= runtime['observed_ns'] <= end
        else:
            assert close['product_runtime_exit'] is None
        bridge = c['bridge_cleanup']
        assert bridge['confirmed'] is None and bridge['receipt_status'] == 'unknown' and bridge['missing_exit_count'] == 1
        assert not [p for p in names if p.startswith(BASE+'/'+pre+'attachments/') and p.endswith('/EXIT.json')]
        attempts = close['tools']
        public_attempts = []
        open_calls = {}
        complete_calls = []
        for event in ev:
            item = event['event'].get('item', {})
            if item.get('type') != 'mcp_tool_call':
                continue
            if event['event']['type'] == 'item.started':
                assert item['id'] not in open_calls
                open_calls[item['id']] = event
            elif event['event']['type'] == 'item.completed':
                prior = open_calls.pop(item['id'])
                assert prior['perf_ns'] <= event['perf_ns']
                public_attempts.append(dict(id=item['id'], tool=item['tool'], status=item['status'],
                    start_ns=prior['perf_ns'], end_ns=event['perf_ns'], elapsed_ns=event['perf_ns']-prior['perf_ns']))
                complete_calls.append(event)
        assert not open_calls
        assert len(attempts) == close['tool_attempts'] == len(public_attempts) == len(tool_public['owner_attempts'])
        for attempt, public_attempt, anon_attempt in zip(attempts, public_attempts, tool_public['owner_attempts']):
            folder = pre + 'owner/tool_' + str(attempt['attempt']).zfill(2) + '/'
            assert saved(folder + 'ATTEMPT.json') == attempt
            for name in ('REQUEST.json', 'RESPONSE.json'):
                data = raw(BASE + '/' + folder + name)
                assert sha(data) == next(x['original_sha256'] for x in anon_attempt['source_files'] if x['kind'] == name)
            assert c['prompt_submitted_ns'] <= attempt['started_ns'] <= attempt['started_ns']+attempt['elapsed_ns'] <= c['final_received_ns']
            assert anon_attempt['is_error'] == attempt['is_error']
            assert public_attempt['tool'] == attempt['name']
        assert all(a['end_ns'] <= b['start_ns'] for a, b in zip(public_attempts,public_attempts[1:]))
        # Exact recorded consumer stdio byte counts, including the failed request.
        wire_calls, wire_catalog = [], []
        txs = [p for p in names if p.startswith(BASE+'/'+pre+'attachments/') and p.endswith('/TX.bin')]
        for txp in txs:
            tx = raw(txp); msg = json.loads(tx)
            rxp = txp[:-6] + 'RX.bin'
            rx = raw(rxp) if rxp in names else b''
            if msg.get('method') == 'tools/call':
                wire_calls.append(dict(tx_bytes=len(tx),rx_bytes=len(rx),request_id=msg.get('id')))
            if msg.get('method') == 'tools/list':
                wire_catalog.append(dict(tx_bytes=len(tx),rx_bytes=len(rx),tool_count=len(json.loads(rx)['result']['tools'])))
        assert len(wire_calls) == len(attempts) and len(wire_catalog) == 1
        phases = dict(zip(('input_checks_and_owner_setup','consumer_setup','popen_to_prompt','prompt_to_final',
                          'final_to_turn','turn_to_consumer_exit','consumer_exit_to_cleanup','cleanup_to_full_cell_end'),
                         [b-a for a,b in zip(timeline,timeline[1:])]))
        assert sum(phases.values()) == duration
        cells.append(dict(**spec, anonymous_id=anonymous, quality='complete_correct',
            quality_sources=['independent_quality/SCORES.json','root_quality/SCORES.json'],
            usage=usage, token_total=usage['input_tokens']+usage['output_tokens'], turn_completed_count=len(turns),
            full_cell_ns=duration, prompt_to_final_ns=c['prompt_to_final_ns'],
            timestamps_ns=dict(cell_start=start, original_cell_deadline=deadline, actor_prepare_start=launch['prepare_started_ns'],
                actor_startup_deadline=launch['actor_startup_deadline_ns'], consumer_start=c['started_ns'],
                original_consumer_deadline=c['deadline_ns'], prompt_submitted=c['prompt_submitted_ns'],
                final_received=c['final_received_ns'], turn_completed=c['turn_completed_ns'],
                consumer_exit_observed=c['process_exit_ns'], consumer_cleanup_end=c['cleanup_end_ns'],
                worker_closed=worker['closed_ns'], owner_close_end=close['ended_ns'], cell_end=end),
            phases_ns=phases, exit_evidence=dict(consumer_reaped=True,owner_wait_return_code=finish['exit_code'],
                native_reaped=True, product_runtime_exit=close['product_runtime_exit'],
                thin_client_exit=bridge, full_cell_end_is_post_owner_wait=True),
            attempts=attempts, public_tool_intervals=public_attempts,
            tool_attempts=len(attempts), tool_failures=sum(x['is_error'] for x in attempts),
            actor_handler_ns=sum(x['elapsed_ns'] for x in attempts),
            public_tool_intervals_ns=sum(x['elapsed_ns'] for x in public_attempts),
            prompt_interval_unattributed_ns=c['prompt_to_final_ns']-sum(x['elapsed_ns'] for x in public_attempts),
            tool_tx_bytes=sum(x['tx_bytes'] for x in wire_calls),tool_rx_bytes=sum(x['rx_bytes'] for x in wire_calls),
            catalog=wire_catalog[0], consumer_errors=c['errors'], provider_retry_observations=c['provider_retry_observations'],
            provider_requests=c['provider_requests'], fees=c['fees'], resolved_effort=c['resolved_effort']))
    groups = {}
    for group in ('N','P'):
        rows = [c for c in cells if c['group'] == group]
        assert len(rows) == 3
        groups[group] = dict(complete_correct=3, full_cell_ns=stats([c['full_cell_ns'] for c in rows]),
            prompt_to_final_ns=stats([c['prompt_to_final_ns'] for c in rows]),
            token_total=stats([c['token_total'] for c in rows]),
            usage_sums={k:sum(c['usage'][k] for c in rows) for k in rows[0]['usage']},
            tool_attempts=sum(c['tool_attempts'] for c in rows), tool_failures=sum(c['tool_failures'] for c in rows),
            actor_handler_ns=sum(c['actor_handler_ns'] for c in rows),
            tool_tx_bytes=sum(c['tool_tx_bytes'] for c in rows),tool_rx_bytes=sum(c['tool_rx_bytes'] for c in rows))
    pairs = []
    for round_ in (1,2,3):
        n=next(c for c in cells if c['round']==round_ and c['group']=='N')
        p=next(c for c in cells if c['round']==round_ and c['group']=='P')
        pairs.append(dict(round=round_,N_cell=n['cell'],P_cell=p['cell'],full_cell_ns=delta(n['full_cell_ns'],p['full_cell_ns']),
                          token_total=delta(n['token_total'],p['token_total'])))
    time_cmp=delta(groups['N']['full_cell_ns']['median'],groups['P']['full_cell_ns']['median'])
    token_cmp=delta(groups['N']['token_total']['total'],groups['P']['token_total']['total'])
    gate=dict(quality_both_three_of_three=True,all_six_retained=True,all_usage_present=True,
              time_noninferior=time_cmp['P']<=time_cmp['N'],token_noninferior=token_cmp['P']<=token_cmp['N'],
              improvement_at_least_ten_percent=max(time_cmp['reduction_percent'],token_cmp['reduction_percent'])>=10)
    gate['passes']=all(gate.values())
    prep=saved('PREPARATION_COST.json'); order=saved('WORK_ORDER.json'); install=saved('installations/P_READY.json')
    prep_ns=int((dt.datetime.fromisoformat(prep['freeze_utc'])-dt.datetime.fromisoformat(prep['recorded_start_utc'])).total_seconds()*1e9)
    assert prep['recorded_start_utc'] == order['recorded_utc']
    assert all(prep[k]==0 for k in ('Blender_sessions','installation_rebuilds','live_product_processes','model_consumers','smoke_sessions'))
    process=saved('FORMAL_PROCESS.json')
    sum_cells=sum(c['full_cell_ns'] for c in cells)
    batch_ns=run['batch_ended_ns']-run['batch_started_ns']
    assert batch_ns==run['batch_wall_ns']
    outer_ns=process['ended_ns']-process['started_ns']
    assert process['started_ns']<=run['batch_started_ns']<=run['records'][0]['cell_started_ns']
    assert run['records'][-1]['cell_ended_ns']<=run['batch_ended_ns']<=process['ended_ns']
    analysis_order=read(BASE+'/cost_review_01/WORK_ORDER.json',ANALYSIS)
    assert dt.datetime.fromisoformat(seal['sealed_at_utc'])<dt.datetime.fromisoformat(analysis_order['recorded_utc'])
    # Author values are checked only after independent aggregates are complete.
    authored=read(BASE+'/cost_review_01/cost/RESULTS.json',ANALYSIS)
    assert all(authored['comparison']['median_full_cell'][k] == v for k,v in time_cmp.items())
    assert all(authored['comparison']['cumulative_input_plus_output'][k] == v for k,v in token_cmp.items())
    for own, author in zip(cells, authored['cells']):
        assert own['cell'] == author['cell'] and own['group'] == author['group']
        assert own['full_cell_ns'] == author['timing']['full_cell_ns']
        assert own['prompt_to_final_ns'] == author['timing']['prompt_to_final_ns']
        assert all(author['usage'][k] == v for k,v in own['usage'].items())
        assert own['token_total'] == author['usage']['input_plus_output_tokens']
    claims={'N_median_seconds':68.8254483,'P_median_seconds':28.9515239,'N_tokens':91958,'P_tokens':50567}
    calculated={'N_median_seconds':time_cmp['N']/1e9,'P_median_seconds':time_cmp['P']/1e9,
                'N_tokens':token_cmp['N'],'P_tokens':token_cmp['P']}
    assert claims==calculated
    result=dict(schema='independent-m4-cost-review-v1',started_utc=started,
        completed_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        source_commit=EVIDENCE,author_analysis_commit=ANALYSIS,quality_seal_commit=SEAL_COMMIT,
        quality_seal_sha256=sha(raw(SEAL_PREFIX+'/QUALITY_SEAL.json',SEAL_COMMIT,QUALITY_ROOT)),
        actual_evidence_root=str(ROOT),actual_quality_root=str(QUALITY_ROOT),
        calculation_inputs='Raw unique turn.completed usage; original cell start/deadline/end and exit receipts; fixed score/mapping bindings',
        source_timing_semantics=dict(driver='138-163 wait/reap; 200 before validation; 230 after finish',
            consumer_transport='209-214 cumulative final usage; 224-225 wait then exit timestamp; 235-259 cleanup'),
        frozen_contract=contract,cells=cells,groups=groups,pairs=pairs,
        comparison=dict(full_cell_median_ns=time_cmp,cumulative_input_plus_output=token_cmp),gate=gate,
        gate_scope='Registered input-check-to-post-owner-wait boundary; not proof that every thin-client process exited. Six thin-client EXIT receipts remain unknown.',
        author_claim_comparison=dict(claims=claims,independent_calculation=calculated,exact_match=True),
        stages=dict(preparation=dict(original=prep,recorded_wall_ns=prep_ns),
            historic_installation=dict(version=install['version'],elapsed_ns=install['elapsed_ns'],counted_as_current_rebuild=False),
            formal=dict(sum_cell_ns=sum_cells,batch_ns=batch_ns,batch_outside_cells_ns=batch_ns-sum_cells,
                outer_process_ns=outer_ns,outer_minus_batch_ns=outer_ns-batch_ns,
                overlap_rule='Cells are nested within batch within outer process; never add all three'),
            independent_quality_review=dict(time=None,tokens=None,fees=None,status='unmeasured'),
            author_saved_data_review=dict(time=None,tokens=None,fees=None,status='unmeasured'),
            current_independent_review=dict(new_consumer_runs=0,new_Blender_runs=0,new_product_runs=0,
                geometry_reruns=0,model_tokens=None,fees=None,status='full review wall and coordination costs unmeasured')),
        limitations=[
            'Only one repeated synthetic scene and three samples per group; no cross-task/generalization/statistical-stability claim.',
            'All six thin-client EXIT.json receipts are absent. Their exit is unknown, not proved by other processes. Backend/consumer owned exits have separate evidence; no all-process exit claim.',
            'process_exit_ns is observation after wait; owner cell end is after wait/receipt publication, not an exact kernel exit instant.',
            'Post-cell accounting publication is outside each registered cell; included in batch, which is reported separately.',
            'Cached input and reasoning output are subitems of input/output. Only input+output summed; no cumulative snapshot duplication.',
            'Provider request/retry count, resolved model/effort, monetary fees, cache memory, provider latency decomposition not measured.',
            'Non-tool wall time remains unattributed; it must not be labelled model thinking.',
            'Preparation window excludes preceding reading/delegation; coordinator and independent-review resources are unmeasured.',
            'Geometry scores are consumed from the fixed seal without rerunning geometry.',
            'This audit verifies selected cost/mapping/quality/source-timing evidence bytes, not every product/source/configuration file.'
        ],script_sha256=sha(Path(__file__).read_bytes()))
    (OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'INPUTS.json').write_text(json.dumps(list(INPUTS.values()),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(gate=gate,comparison=result['comparison'],inputs_verified=len(INPUTS),
                         stages=result['stages'],output=str(OUT/'RESULTS.json')),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
