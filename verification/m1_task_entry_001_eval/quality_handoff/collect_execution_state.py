"""Offline private execution/PID evidence inventory; run only after the batch.

Selects execution fields from runner metadata; no answer assessment, scoring,
usage export or performance ranks.
Does not query, terminate, restart or delete any process or backend.
Importing this module performs no collection. The root owns the explicit call.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path


def valid_pid(value):
    return type(value) is int and value>0


def read_metadata(path,errors):
    path=Path(path)
    if not path.exists():return None
    try:
        raw=path.read_bytes();value=json.loads(raw)
        if type(value) is not dict:raise ValueError('metadata_object_required')
        return value
    except (OSError,ValueError,TypeError) as exc:
        errors.append({'path':str(path),'error':type(exc).__name__+': '+str(exc)})
        return None


def collect(batch_root):
    """Build evidence only. Numeric PIDs are not a current-process identity."""
    root=Path(batch_root).resolve();read_errors=[]
    plan=read_metadata(root/'PLAN.json',read_errors)
    if plan is None:raise ValueError('PLAN_unreadable')
    sequence=plan.get('sequence')
    if type(sequence) is not list or len(sequence)!=27:raise ValueError('fixed_27_sequence_required')
    cell_ids=[slot.get('cell') for slot in sequence if type(slot) is dict]
    if len(cell_ids)!=27 or any(type(c) is not str or Path(c).name!=c or c in ('.','..') for c in cell_ids):
        raise ValueError('invalid_fixed_cell_identifiers')
    if len(set(cell_ids))!=27:raise ValueError('duplicate_fixed_cell_identifiers')
    run=read_metadata(root/'RUN_RESULT.json',read_errors) or {}
    rows_by_cell=defaultdict(list)
    run_rows=run.get('records',[])
    if type(run_rows) is not list:raise ValueError('RUN_RESULT_records_must_be_list')
    for index,row in enumerate(run_rows):
        if type(row) is dict and type(row.get('cell')) is str:rows_by_cell[row['cell']].append((index,row))
        else:read_errors.append({'path':str(root/'RUN_RESULT.json'),'error':'invalid_record_at_index_'+str(index)})
    cells=[];pid_index=[]
    def index_pid(cell,role,pid,source,binding,ownership):
        if valid_pid(pid):
            pid_index.append({'cell':cell,'role':role,'pid':pid,'source':str(source),
                'binding':binding,'ownership_evidence':ownership,'current_OS_state':None,
                'process_creation_time':None})
    for slot in sequence:
        cell_id=slot['cell'];folder=root/'cells'/cell_id;owner=folder/'owner'
        errors=[];issues=[];matched=rows_by_cell.get(cell_id,[])
        for _,row in matched:
            for key in ('task','group'):
                if row.get(key)!=slot.get(key):issues.append('RUN_RESULT_'+key+'_does_not_match_PLAN')
        if len(matched)>1:issues.append('duplicate_RUN_RESULT_cell_records')
        launch=read_metadata(folder/'ACTOR_LAUNCH.json',errors) or {}
        identity=read_metadata(owner/'IDENTITY.json',errors) or {}
        owner_close=read_metadata(owner/'CLOSE.json',errors) or {}
        finish=read_metadata(folder/'OWNER_FINISH.json',errors) or {}
        consumer=read_metadata(folder/'CONSUMER.json',errors)
        consumer_source=folder/'CONSUMER.json'
        if consumer is None and len(matched)==1 and type(matched[0][1].get('consumer')) is dict:
            consumer=matched[0][1]['consumer'];consumer_source=root/'RUN_RESULT.json'
        consumer=consumer or {}
        for key in ('cell','task','group'):
            if key in consumer and consumer[key]!=slot.get(key):issues.append('CONSUMER_'+key+'_does_not_match_PLAN')
        for key in ('group',):
            if key in identity and identity[key]!=slot.get(key):issues.append('IDENTITY_'+key+'_does_not_match_PLAN')
        launcher_pid=launch.get('pid')
        index_pid(cell_id,'actor_launcher',launcher_pid,folder/'ACTOR_LAUNCH.json',
            'direct runner Popen PID record','recorded_launcher')
        actual_pid=identity.get('actor_pid',owner_close.get('actor_pid'))
        parent_pid=identity.get('actor_parent_pid',owner_close.get('actor_parent_pid'))
        if valid_pid(actual_pid) and valid_pid(launcher_pid):
            if actual_pid==launcher_pid:actor_binding='same_PID_as_recorded_launcher'
            elif parent_pid==launcher_pid:actor_binding='actual_actor_parent_matches_recorded_launcher'
            else:actor_binding='unknown'
        else:actor_binding='unknown'
        if actual_pid and actor_binding=='unknown':issues.append('actual_actor_not_bound_to_recorded_launcher')
        if identity.get('actor_pid') and owner_close.get('actor_pid') and identity['actor_pid']!=owner_close['actor_pid']:
            issues.append('actual_actor_identity_close_PID_mismatch')
        index_pid(cell_id,'actual_actor',actual_pid,owner/'IDENTITY.json' if identity else owner/'CLOSE.json',
            actor_binding,'receipt_bound' if actor_binding!='unknown' else 'observed_only')
        # Do not index arbitrary parent_pid as owned. Only the explicit launcher
        # record above can supply that launcher's ownership evidence.
        native_ready=read_metadata(owner/'native/READY.json',errors) or {}
        native_session=read_metadata(owner/'native/SESSION.json',errors) or {}
        native_closed=read_metadata(owner/'native/WORKER_CLOSED.json',errors) or {}
        native_pid=native_session.get('pid',native_ready.get('pid'))
        native_binding=bool(valid_pid(native_pid) and native_ready.get('pid')==native_pid
            and native_session.get('pid')==native_pid)
        native_close=owner_close.get('native_close') if type(owner_close.get('native_close')) is dict else {}
        if native_pid and native_ready.get('pid') and native_ready['pid']!=native_pid:issues.append('native_READY_SESSION_PID_mismatch')
        if native_closed.get('pid') and native_closed['pid']!=native_pid:issues.append('native_WORKER_CLOSED_PID_mismatch')
        index_pid(cell_id,'native_worker',native_pid,owner/'native/SESSION.json' if native_session else owner/'native/READY.json',
            'SESSION_and_READY_PID_match; original helper binds READY to its Popen' if native_binding else 'unknown',
            'receipt_bound' if native_binding else 'observed_only')
        product_start=read_metadata(owner/'plugin/START.json',errors) or {}
        product_close=read_metadata(owner/'plugin/CLOSE.json',errors) or {}
        product_pid=product_start.get('launcher_pid')
        index_pid(cell_id,'product_python_launcher',product_pid,owner/'plugin/START.json',
            'direct product Peer Popen PID record','recorded_launcher')
        consumer_pid=consumer.get('consumer_pid')
        index_pid(cell_id,'consumer_process',consumer_pid,consumer_source,
            'direct consumer transport Popen PID record','recorded_launcher')
        cleanup=consumer.get('process_cleanup') if type(consumer.get('process_cleanup')) is dict else {}
        thin=[]
        # Only the formal consumer attachments, never earlier private probes.
        for bridge in sorted((folder/'attachments').glob('bridge_*')):
            started=read_metadata(bridge/'STARTED.json',errors)
            ended=read_metadata(bridge/'EXIT.json',errors)
            pid=started.get('pid') if started else None
            matched_exit=bool(started and ended and valid_pid(pid) and ended.get('pid')==pid
                and type(started.get('instance_nonce')) is str and started['instance_nonce']
                and ended.get('instance_nonce')==started['instance_nonce']
                and type(started.get('started_ns')) is int and ended.get('started_ns')==started['started_ns']
                and type(ended.get('ended_ns')) is int and ended['ended_ns']>=started['started_ns'])
            normal=bool(matched_exit and ended.get('normal_exit') is True
                and ended.get('backend_close_requested') is False)
            thin.append({'directory':str(bridge),'pid':pid,
                'receipt_state':'observed_matching_receipt' if matched_exit else 'unknown',
                'normal_exit_reported':normal if matched_exit else None,
                'ownership':'observed_only; no launcher ancestry proof in formal thin receipt',
                'OS_exit_confirmed':None})
            index_pid(cell_id,'formal_thin_observed',pid,bridge/'STARTED.json',
                'STARTED/EXIT same PID+nonce+start' if matched_exit else 'unknown',
                'observed_only')
        consumer_record_bound=bool(consumer) and all(consumer.get(key)==slot.get(key) for key in ('cell','task','group'))
        thread_marker_observed=type(consumer.get('thread_id')) is str and bool(consumer['thread_id'])
        thread_observed=bool(consumer_record_bound and thread_marker_observed)
        # Inspect presence/size only, never read a public final's answer bytes.
        final_path=folder/'PUBLIC_FINAL.txt'
        try:final_bytes=final_path.stat().st_size if final_path.is_file() else None
        except OSError as exc:errors.append({'path':str(final_path),'error':repr(exc)});final_bytes=None
        final_marker=type(consumer.get('final_received_ns')) is int or (final_bytes is not None and final_bytes>0)
        attempted_cell=bool(matched or launch or identity or owner_close or finish or consumer
            or (folder/'ACTOR_CONFIG.json').exists() or (folder/'ACTOR_ERROR.json').exists())
        if thread_observed:state='attempted' if final_marker else 'no_answer'
        elif attempted_cell:state='infrastructure_block'
        else:state='not_run'
        # The RUN_RESULT may embed answers and usage. Export only selected
        # execution fields, never whole nested consumer/final/error objects.
        record_indices=[index for index,_ in matched]
        finish_bound=valid_pid(launcher_pid) and finish.get('actor_pid')==launcher_pid
        product_bound=valid_pid(product_pid) and product_close.get('launcher_pid')==product_pid
        consumer_bound=valid_pid(consumer_pid) and cleanup.get('pid')==consumer_pid
        native_close_bound=valid_pid(native_pid) and native_close.get('pid')==native_pid
        cells.append({'cell':cell_id,'task':slot.get('task'),'group':slot.get('group'),
            'execution_state':state,'cell_dispatch_observed':attempted_cell,
            'consumer_launch_observed':valid_pid(consumer_pid),'consumer_record_bound_to_PLAN':consumer_record_bound,
            'model_thread_marker_in_record':thread_marker_observed,'model_thread_observed':thread_observed,
            'answer_presence_observed':bool(final_marker),'final_artifact_bytes':final_bytes,
            'provider_request_count':None,'provider_cost':None,'RUN_RESULT_record_indices':record_indices,
            'PID_evidence':{'actor_launcher':launcher_pid,'actual_actor':actual_pid,
                'actual_actor_parent':parent_pid,'actual_actor_binding':actor_binding,
                'native_worker':native_pid,'native_worker_binding':native_binding,
                'product_python_launcher':product_pid,'consumer_process':consumer_pid},
            'exit_receipts':{
                'actor_launcher':{'PID_matches_launch':finish_bound,
                    'exit_code':finish.get('exit_code') if finish_bound else None,
                    'recorded_close_confirmed':finish.get('confirmed') if finish_bound else None},
                'actual_actor':{'close_PID_matches_identity':bool(valid_pid(actual_pid) and owner_close.get('actor_pid')==actual_pid),
                    'recorded_close_confirmed':owner_close.get('confirmed'),'OS_exit_confirmed':None},
                'native_worker':{'close_PID_matches_worker':native_close_bound,
                    'process_reaped_reported':native_close.get('process_reaped') if native_close_bound else None,
                    'exit_code':native_close.get('exit_code') if native_close_bound else None,
                    'WORKER_CLOSED_PID_matches':bool(valid_pid(native_pid) and native_closed.get('pid')==native_pid)},
                'product_python_launcher':{'PID_matches_start':product_bound,
                    'process_reaped_reported':product_close.get('process_reaped') if product_bound else None,
                    'exit_code':product_close.get('exit_code') if product_bound else None,
                    'recorded_close_confirmed':product_close.get('confirmed') if product_bound else None},
                'consumer_process':{'cleanup_PID_matches_consumer':consumer_bound,
                    'process_reaped_reported':consumer.get('process_reaped') if consumer_bound else None,
                    'exit_code':consumer.get('exit_code') if consumer_bound else None},
                'formal_thin':thin},
            'binding_issues':issues,'metadata_read_errors':errors})
    counts=Counter(row['execution_state'] for row in cells)
    return {'schema':'m1-private-execution-state-v1','batch_root':str(root),
        'scope':'offline private metadata inventory; no process query, ownership promotion, cleanup, answer scoring or timing/token comparison',
        'PLAN_sha256':hashlib.sha256((root/'PLAN.json').read_bytes()).hexdigest(),
        'planned_cells':27,'inventory_cells':len(cells),
        'batch_end_record_present':type(run.get('batch_ended_ns')) is int,
        'recorded_stop':run.get('stop'),
        'execution_state_definition':{
            'attempted':'model thread observed and answer presence marker observed; no correctness judgment',
            'no_answer':'model thread observed without answer presence marker',
            'infrastructure_block':'cell dispatch/preparation observed but model thread not evidenced; provider requests remain unknown',
            'not_run':'no dispatch/preparation/consumer evidence for this planned cell; not a model consumption failure'},
        'execution_state_counts':{name:counts[name] for name in ('attempted','no_answer','infrastructure_block','not_run')},
        'consumer_launches_observed':sum(r['consumer_launch_observed'] for r in cells),
        'model_threads_observed':sum(r['model_thread_observed'] for r in cells),
        'provider_request_count':None,'provider_cost':None,
        'extra_RUN_RESULT_cell_ids':sorted(set(rows_by_cell)-set(cell_ids)),
        'metadata_read_errors':read_errors,'cells':cells,'PID_index':pid_index,
        'PID_query_values':sorted({row['pid'] for row in pid_index}),
        'PID_query_scope':'numeric PID list for root-only follow-up; no current OS state or creation-time binding is supplied; never treat an arbitrary matching parent PID as owned'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='New private JSON path; never overwrite existing evidence')
    args=parser.parse_args()
    report=collect(args.batch_root)
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(report,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.write('\n')
    print(json.dumps({'output':str(args.output),'planned_cells':27,'inventory_cells':len(report['cells']),
        'scope':'private execution inventory only; no correctness or performance ranking'},ensure_ascii=False))
