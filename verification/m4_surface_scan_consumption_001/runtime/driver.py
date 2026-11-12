"""Thin six-cell spatial-fact consumption adapter with original owner lifecycle.

The current parent plan authorizes preparation and the frozen formal sequence.
The default CLI only checks inputs. run_models reserves the six slots once.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import time
import traceback

HERE=Path(__file__).resolve().parent.parent
ROOT=HERE.parents[1]
CYCLE='M4-SURFACE-SCAN-CONSUMPTION-001'
SOURCE_BY_PROFILE={'P':'c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943'}
COMMIT_BY_PROFILE={'P':'c1cb2da32034e056a270384e691a2cde8dddbc0d'}
GROUP_ORDER=('N','P','P','N','N','P')
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(p):
    return json.loads(Path(p).read_bytes())

def save(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf8', newline='\n')

def load(name, p):
    spec = importlib.util.spec_from_file_location(name, p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def arm_runtime(plan, slot):
    """Pure external-arm selection; copied actor/transport still see only N/P."""
    external=slot['group'];assert external in ('N','P'), 'unsupported_external_group'
    arm=plan['arms'][external]
    profile='P'
    internal='N' if external=='N' else 'P'
    assert arm['actor_group']==internal and arm['installation_profile']==profile, 'arm_mapping_changed'
    expected=None if external=='N' else SOURCE_BY_PROFILE[profile]
    assert arm['source_sha256']==expected, 'arm_source_changed'
    ready=plan['installations'][profile]
    assert ready['source_sha256']==SOURCE_BY_PROFILE[profile] and ready['source_count']==138
    assert ready['commit']==COMMIT_BY_PROFILE[profile], 'installation_commit_changed'
    assert ready['dependency_python']==plan['installation_ready']['dependency_python'], 'common_dependency_changed'
    private_slot=dict(slot, group=internal, external_group=external)
    return private_slot,ready,profile


def go_contract(go,plan,plan_sha256):
    """Pure authorization/sampling contract; no dispatch or filesystem action."""
    assert go['task']==CYCLE and go['authorized'] is True, 'wrong_consumption_GO'
    assert go['plan_sha256']==plan_sha256 and go['max_consumers']==6, 'authorization_not_bound_to_six_frozen_slots'
    assert plan['cycle_id']==CYCLE and plan['batch']==CYCLE
    assert len(plan['sequence'])==6 and len({row['cell'] for row in plan['sequence']})==6
    assert [row['cell'] for row in plan['sequence']]==['N1','P1','P2','N2','N3','P3'], 'fresh_cycle_cell_ids_required'
    assert tuple(row['group'] for row in plan['sequence'])==GROUP_ORDER, 'fixed_group_order_changed'
    assert all(row['task']=='T1' and row['round']==index//2+1 for index,row in enumerate(plan['sequence']))
    assert plan['image_count']==0 and plan['new_images']==0
    assert set(plan['arms'])=={'N','P'} and set(plan['installations'])=={'P'}
    for row in plan['sequence']:arm_runtime(plan,row)


def prepare(slot, *, output, cell_started_ns=None):
    """Prepare one directly authorized cell with its original deadlines."""
    prepare_started_ns = time.perf_counter_ns()
    if cell_started_ns is None:
        cell_started_ns = prepare_started_ns
    cell_deadline_ns = cell_started_ns+570*10**9
    actor_startup_deadline_ns = min(cell_deadline_ns, prepare_started_ns+40*10**9)
    if time.perf_counter_ns() >= cell_deadline_ns:
        raise TimeoutError('original_full_cell_deadline_exceeded')
    plan = read(HERE/'PLAN.json')
    tasks = plan['tasks']
    internal_slot,expected_ready,profile = arm_runtime(plan,slot)
    ready = read(HERE/'installations'/(profile+'_READY.json'))
    assert ready==expected_ready, 'installation_READY_not_frozen'
    task, group = tasks[slot['task']], internal_slot['group']
    assert slot['task']=='T1', 'fixed_M4_task'
    assert task['asset']==plan['inputs']['scene'] and task['asset_sha256']==plan['inputs']['scene_sha256']
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=False)
    asset = HERE/task['asset']
    assert sha(asset) == task['asset_sha256']
    schemas = [] if group == 'N' else read(HERE/'schemas'/(profile+'_PUBLIC_TOOLS.json'))
    now = time.perf_counter_ns()
    if now >= cell_deadline_ns:
        raise TimeoutError('original_full_cell_deadline_exceeded')
    if now >= actor_startup_deadline_ns:
        raise TimeoutError('actor_startup_original_40s')
    config = {'group': group, 'task': slot['task'], 'output': str(folder/'owner'),
        'endpoint': str(folder/'ENDPOINT.json'), 'asset': str(asset), 'asset_sha256': task['asset_sha256'],
        'blender': 'D:/Tools/blender5.2/blender.exe', 'worker_deadline_ns': cell_deadline_ns,
        'dependency_python': ready['dependency_python'], 'read_schemas': schemas,
        'entry': None if group == 'N' else ready['entry'],
        'install_root': None if group == 'N' else ready['install_root'],
        'source_sha256': None if group == 'N' else ready['source_sha256'],
        'external_group':slot['group']}
    save(folder/'ACTOR_CONFIG.json', config)
    command = [ready['dependency_python'], '-I', '-B', str(HERE/'runtime/actor.py'), '--config', str(folder/'ACTOR_CONFIG.json')]
    with (folder/'actor_stdout.bin').open('wb') as out, (folder/'actor_stderr.bin').open('wb') as err:
        now = time.perf_counter_ns()
        if now >= cell_deadline_ns:
            raise TimeoutError('original_full_cell_deadline_exceeded')
        if now >= actor_startup_deadline_ns:
            raise TimeoutError('actor_startup_original_40s')
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        save(folder/'ACTOR_LAUNCH.json', {'pid': process.pid, 'argv': command, 'started_ns': cell_started_ns,
            'cell_started_ns': cell_started_ns, 'prepare_started_ns': prepare_started_ns,
            'worker_deadline_ns': cell_deadline_ns, 'actor_startup_deadline_ns': actor_startup_deadline_ns})
        while not (folder/'ENDPOINT.json').exists():
            if process.poll() is not None:
                raise RuntimeError('actor_start_failed')
            now = time.perf_counter_ns()
            if now >= cell_deadline_ns:
                raise TimeoutError('original_full_cell_deadline_exceeded')
            if now >= actor_startup_deadline_ns:
                raise TimeoutError('actor_startup_original_40s')
            time.sleep(.02)
        now = time.perf_counter_ns()
        if now >= cell_deadline_ns:
            raise TimeoutError('original_full_cell_deadline_exceeded')
        if now >= actor_startup_deadline_ns:
            raise TimeoutError('actor_startup_original_40s')
        save(folder/'cell.json', {'group': group, 'external_group':slot['group'],
            'endpoint': str(folder/'ENDPOINT.json'), 'audit_dir': str(folder/'owner')})
        return folder, process, cell_started_ns
    except BaseException:
        finish(folder, process)
        raise

def finish(folder, process):
    start = time.perf_counter_ns()
    signal_error = None
    try:
        if process.poll() is None:
            process.stdin.write(b'finish\n')
    except (OSError, ValueError) as error:
        signal_error = repr(error)
    finally:
        try:
            process.stdin.close()
        except (OSError, ValueError) as error:
            signal_error = signal_error or repr(error)
    try:
        process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=5)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    close = read(folder/'owner/CLOSE.json') if (folder/'owner/CLOSE.json').exists() else None
    value = {'actor_pid': process.pid, 'exit_code': process.returncode, 'close': close,
        'elapsed_ns': time.perf_counter_ns()-start, 'finish_signal_error': signal_error,
        'confirmed': bool(process.returncode == 0 and close and close.get('confirmed'))}
    save(folder/'OWNER_FINISH.json', value)
    return value

def snapshot_binding(actual, expected):
    def normalized(value):
        return {'unit_scale_m': value.get('unit_scale_m',value.get('scale_length')), 'objects': sorted([
            {'name': r['name'], 'vertices_local': r['vertices_local'], 'matrix_world': r['matrix_world'],
             'faces': r.get('faces', r.get('triangles'))} for r in value['objects']], key=lambda r: r['name'])}
    assert normalized(actual) == normalized(expected), 'full_registered_mesh_snapshot_mismatch'

def verify_frozen_inputs(plan):
    for name, digest in plan['dispatch_input_sha256'].items():
        assert sha(HERE/name) == digest, 'frozen_dispatch_input_changed: '+name
    for name, digest in plan.get('external_input_sha256', {}).items():
        assert sha(Path(name)) == digest, 'frozen_external_input_changed: '+name

def provider_unavailable(diagnostics):
    text = diagnostics.casefold()
    if any(word in text for word in ('quota', 'usage limit', 'rate limit')):
        return True
    return re.search(r'\b(?:http(?:/[\d.]+)?(?:\s+status)?|status(?:\s+code)?|error(?:\s+code)?)'
                     r'\s*[:=]?\s*(?:429|503)\b', text) is not None


def close_cell_accounting(folder, row, records, stop):
    """Observe completion after business receipts and owned cleanup have closed.

    These two controller timing receipts describe their own publication
    separately. Their final self-publication is outside the business window.
    File close is the existing durability level, with no fsync assertion.
    """
    folder.mkdir(parents=True, exist_ok=True)
    save(HERE/'RUN_RESULT.json', {'records': records, 'stop': stop,
        'started_cells': len(records), 'maximum_consumers': 6,
        'all_planned_dispatched': len(records) == 6, 'no_replacements': True})
    business_closed_ns = time.perf_counter_ns()
    elapsed = business_closed_ns-row['cell_started_ns']
    timing = {
        'cell': row['cell'], 'cell_started_ns': row['cell_started_ns'],
        'business_receipts_closed_ns': business_closed_ns,
        'full_cell_wall_ns': elapsed, 'within_570s': elapsed < 570*10**9,
        'owner_cleanup_confirmed': bool(row.get('finish') and row['finish'].get('confirmed')),
        'scope': 'Before cell input checks through final CONSUMER, OWNER_FINISH and per-cell RUN_RESULT write/close and owned cleanup; controller timing-receipt publication is separate',
        'durability': 'existing buffered write and close; fsync persistence unmeasured',
    }
    publication_started_ns = time.perf_counter_ns()
    save(folder/'CELL_FINAL_TIMING.json', timing)
    publication_closed_ns = time.perf_counter_ns()
    save(folder/'CELL_TIMING_PUBLICATION.json', {
        'cell': row['cell'], 'business_receipts_closed_ns': business_closed_ns,
        'timing_receipt_publication_started_ns': publication_started_ns,
        'timing_receipt_publication_closed_ns': publication_closed_ns,
        'timing_receipt_publication_ns': publication_closed_ns-publication_started_ns,
        'controller_tail_ns': publication_closed_ns-business_closed_ns,
        'scope': 'CELL_FINAL_TIMING serialization, write and close; this publication receipt itself and later batch summaries excluded',
    })
    return timing

def run_models():
    """Only this cycle's directly authorized frozen six-consumer receipt authorizes this entry."""
    batch_started_ns = time.perf_counter_ns()
    go, plan = read(HERE/'GO.json'), read(HERE/'PLAN.json')
    go_contract(go,plan,sha(HERE/'PLAN.json'))
    assert sha(HERE/'runtime/consumer_transport.py') == plan['consumer_transport_sha256']
    assert sha(HERE/'runtime/actor.py') == plan['actor_sha256'] and sha(Path(__file__)) == plan['preflight_driver_sha256']
    verify_frozen_inputs(plan)
    transport = load('_m4_fixed_consumer', HERE/'runtime/consumer_transport.py')
    assert sha(transport.EXE) == plan['CLI_sha256']
    with (HERE/'STARTED.json').open('x') as stream:
        json.dump({'started_ns': time.perf_counter_ns(), 'max_consumers': 6,
            'plan_sha256': sha(HERE/'PLAN.json')}, stream)
    records, stop = [], None
    for slot in plan['sequence']:
        cell_started_ns = time.perf_counter_ns()
        cell_deadline_ns = cell_started_ns+570*10**9
        folder, process = None, None
        row = {**slot, 'errors': [], 'consumer': None, 'finish': None,
            'cell_started_ns': cell_started_ns, 'worker_deadline_ns': cell_deadline_ns,
            'final_timing_receipt': 'cells/'+slot['cell']+'/CELL_FINAL_TIMING.json'}
        records.append(row)
        # Reserve this planned slot before any owner or consumer can start.
        # A later accounting failure retains its started identity in RUN_RESULT.
        save(HERE/'RUN_RESULT.json', {'records': records, 'stop': 'cell_in_progress',
            'started_cells': len(records), 'maximum_consumers': 6,
            'all_planned_dispatched': False, 'no_replacements': True})
        try:
            verify_frozen_inputs(plan)
            task = plan['tasks'][slot['task']]
            assert sha(HERE/task['snapshot']) == task['snapshot_sha256'], 'frozen_mesh_snapshot_changed'
            prompt = (HERE/plan['inputs']['prompt']).read_bytes()
            assert hashlib.sha256(prompt).hexdigest() == plan['inputs']['prompt_sha256']
            transport.initial_image_metadata(plan)
            if time.perf_counter_ns() >= cell_deadline_ns:
                raise TimeoutError('original_full_cell_deadline_exceeded')
            folder, process, _ = prepare(slot, output=HERE/'cells'/slot['cell'], cell_started_ns=cell_started_ns)
            snapshot_binding(read(folder/'owner/INITIAL.json'), read(HERE/task['snapshot']))
            internal_slot,ready,_ = arm_runtime(plan,slot)
            if time.perf_counter_ns() >= cell_deadline_ns:
                raise TimeoutError('original_full_cell_deadline_exceeded')
            row['consumer'] = transport.consume(internal_slot,
                {'python': ready['dependency_python']}, plan, prompt)
        except BaseException as exc:
            row['errors'].append({'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
            stop = 'launch_or_execution_state_requires_review; no replacement consumer'
        finally:
            folder = folder or HERE/'cells'/slot['cell']
            if process is not None:
                try:
                    row['finish'] = finish(folder, process)
                except BaseException as exc:
                    row['errors'].append({'type': type(exc).__name__, 'message': str(exc)})
            elif (folder/'OWNER_FINISH.json').exists():
                # prepare() owns cleanup when startup fails before returning.
                row['finish'] = read(folder/'OWNER_FINISH.json')
            row['cell_ended_ns'] = time.perf_counter_ns()
            row['cell_timing_scope'] = 'prefix through owned cleanup; final business accounting closes in CELL_FINAL_TIMING.json'
            row['full_cell_wall_ns'] = row['cell_ended_ns']-cell_started_ns
            row['within_570s'] = row['full_cell_wall_ns'] < 570*10**9
            row['within_570s_scope'] = 'prefix; authoritative business-close budget in CELL_FINAL_TIMING.json'
            if row['consumer'] is not None:
                consumer = row['consumer']
                consumer['owner_finish'] = row['finish']
                consumer['total_task_wall_ns'] = row['full_cell_wall_ns']
                consumer['total_task_wall_scope'] = row['cell_timing_scope']
                consumer['pre_consumer_setup_ns'] = consumer['started_ns']-cell_started_ns
                save(folder/'CONSUMER.json', consumer)
                if not consumer['safe_to_continue']:
                    stop = 'consumer_or_execution_state_uncertain'
                timed_out = bool(consumer.get('thread_id') and any(
                    e.get('type') == 'TimeoutError' and e.get('message') == 'original_absolute_session_deadline'
                    for e in consumer.get('errors', [])))
                if (not consumer.get('thread_id') or consumer.get('unexpected_tool_deviations')
                        or (consumer.get('errors') or consumer.get('exit_code') != 0) and not timed_out):
                    stop = 'CLI_launch_configuration_or_protocol_failure; no repeated consumers'
                diagnostics = json.dumps(consumer.get('errors', []))
                if (folder/'stderr.raw.bin').exists():
                    diagnostics += (folder/'stderr.raw.bin').read_text(encoding='utf8', errors='replace')
                if provider_unavailable(diagnostics):
                    stop = 'provider_availability_or_quota; no retry or replacement'
            if not row['finish'] or not row['finish'].get('confirmed'):
                stop = 'owner_backend_close_unconfirmed'
            if folder is not None:
                product_rpc = folder/'owner/plugin/RPC.json'
                if product_rpc.exists():
                    try:
                        row['product_channel_poisoned'] = read(product_rpc)['poisoned']
                        if row['product_channel_poisoned']:
                            stop = 'product_channel_poisoned; no replacement consumer'
                    except (OSError, ValueError, KeyError) as error:
                        row['errors'].append({'stage': 'product_channel_status', 'message': str(error)})
                        stop = 'product_channel_status_unknown'
            if not row['within_570s']:
                stop = 'original_full_cell_deadline_exceeded'
            timing = close_cell_accounting(folder, row, records, stop)
            if not timing['within_570s']:
                row['errors'].append({'type': 'TimeoutError', 'stage': 'final_business_accounting',
                    'message': 'original_full_cell_deadline_exceeded'})
                stop = 'original_full_cell_deadline_exceeded'
        if stop:
            break
    batch_ended_ns = time.perf_counter_ns()
    result = {'records': records, 'stop': stop,
        'started_cells': len(records), 'maximum_consumers': 6,
        'all_planned_dispatched': len(records) == 6, 'no_replacements': True,
        'batch_started_ns': batch_started_ns, 'batch_ended_ns': batch_ended_ns,
        'batch_wall_ns': batch_ended_ns-batch_started_ns,
        'batch_timing_scope': 'run_models entry through last per-cell RUN_RESULT publication; includes batch setup and cell accounting, excludes final timing-summary publication and caller overhead; not model reasoning time'}
    save(HERE/'RUN_RESULT.json', result)
    return result

def preflight_inputs():
    """No Popen, model or backend operation: file/hash/argv capability only."""
    plan=read(HERE/'PLAN.json')
    for group in ('N','P'):
        arm_runtime(plan,{'cell':'input-check','round':1,'task':'T1','group':group})
    prompt=(HERE/plan['inputs']['prompt']).read_bytes()
    assert hashlib.sha256(prompt).hexdigest()==plan['inputs']['prompt_sha256']
    transport=load('_m4_prepared_inputs',HERE/'runtime/consumer_transport.py')
    image=transport.initial_image_metadata(plan)
    return {'cycle_id':CYCLE,'phase':'PREPARATION_ONLY','prompt_sha256':plan['inputs']['prompt_sha256'],
        'prompt_utf8_bytes':len(prompt),'initial_image':image,'image_delivery':'no_images',
        'model_consumers':0,'tool_images':0,'new_images':0,
        'scope':'input bytes and zero-image CLI contract only; no model dispatch'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='PREPARED_INPUT.json',help='New runtime metadata receipt; no model dispatch')
    args=parser.parse_args()
    assert Path(args.output).name==args.output and args.output not in ('.','..')
    output=HERE/'runtime'/args.output
    if output.exists():raise FileExistsError('preserve_existing_preparation_receipt')
    result=preflight_inputs();save(output,result)
    print(json.dumps({'phase':'PREPARATION_ONLY','model_consumers':0,'output':str(output)}))
