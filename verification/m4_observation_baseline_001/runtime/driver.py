"""M4 preparation adapter; default CLI builds input receipts, never consumers.

prepare/finish/run_models reuse the accepted M1 timing/lifecycle contract.
Actual installation and Blender preflight belong to the separate test agent.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import traceback

HERE=Path(__file__).resolve().parent.parent
ROOT=HERE.parents[1]
CYCLE='M4-OBSERVATION-BASELINE-001'
CANONICAL='7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
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

def prepare(slot, *, output, cell_started_ns=None):
    """Also reusable after administrator GO; no consumer dispatch here."""
    prepare_started_ns = time.perf_counter_ns()
    if cell_started_ns is None:
        cell_started_ns = prepare_started_ns
    cell_deadline_ns = cell_started_ns+570*10**9
    actor_startup_deadline_ns = min(cell_deadline_ns, prepare_started_ns+40*10**9)
    if time.perf_counter_ns() >= cell_deadline_ns:
        raise TimeoutError('original_full_cell_deadline_exceeded')
    plan = read(HERE/'PLAN.json')
    tasks = plan['tasks']
    ready = read(HERE/'installation/READY.json')
    task, group = tasks[slot['task']], slot['group']
    assert slot['task']=='T1' and group in ('N','P'), 'fixed_M4_task_and_group'
    assert task['asset']==plan['inputs']['scene'] and task['asset_sha256']==plan['inputs']['scene_sha256']
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=False)
    assert ready['source_sha256'] == CANONICAL
    assert plan['candidate_source_sha256']==CANONICAL
    asset = HERE/task['asset']
    assert sha(asset) == task['asset_sha256']
    schemas = [] if group == 'N' else read(HERE/'preflight/P/PUBLIC_TOOLS.json')
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
        'source_sha256': None if group == 'N' else CANONICAL}
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
    save(folder/'ACTOR_LAUNCH.json', {'pid': process.pid, 'argv': command, 'started_ns': cell_started_ns,
        'cell_started_ns': cell_started_ns, 'prepare_started_ns': prepare_started_ns,
        'worker_deadline_ns': cell_deadline_ns, 'actor_startup_deadline_ns': actor_startup_deadline_ns})
    try:
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
        save(folder/'cell.json', {'group': group, 'endpoint': str(folder/'ENDPOINT.json'), 'audit_dir': str(folder/'owner')})
        return folder, process, cell_started_ns
    except BaseException:
        finish(folder, process)
        raise

def finish(folder, process):
    start = time.perf_counter_ns()
    if process.poll() is None:
        process.stdin.write(b'finish\n')
        process.stdin.close()
    try:
        process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=5)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    close = read(folder/'owner/CLOSE.json') if (folder/'owner/CLOSE.json').exists() else None
    value = {'actor_pid': process.pid, 'exit_code': process.returncode, 'close': close,
        'elapsed_ns': time.perf_counter_ns()-start,
        'confirmed': bool(process.returncode == 0 and close and close.get('confirmed'))}
    save(folder/'OWNER_FINISH.json', value)
    return value

def snapshot_binding(actual, expected):
    def normalized(value):
        return {'unit_scale_m': value['unit_scale_m'], 'objects': sorted([
            {'name': r['name'], 'vertices_local': r['vertices_local'], 'matrix_world': r['matrix_world'],
             'faces': r.get('faces', r.get('triangles'))} for r in value['objects']], key=lambda r: r['name'])}
    assert normalized(actual) == normalized(expected), 'full_registered_mesh_snapshot_mismatch'

def run_models():
    """Only the independent M4 six-consumer GO can authorize this entry."""
    batch_started_ns = time.perf_counter_ns()
    go, plan = read(HERE/'GO.json'), read(HERE/'PLAN.json')
    assert go['task'] == CYCLE and go['authorized'] is True
    assert go['plan_sha256'] == sha(HERE/'PLAN.json') and go['max_consumers'] == 6
    assert plan['fixed_product_commit'].startswith('107641ec')
    assert plan['candidate_source_sha256'] == CANONICAL and len(plan['sequence']) == 6
    assert len({row['cell'] for row in plan['sequence']})==6
    assert all(row['task']=='T1' and row['group'] in ('N','P') for row in plan['sequence'])
    assert sum(row['group']=='N' for row in plan['sequence'])==3 and sum(row['group']=='P' for row in plan['sequence'])==3
    assert plan['image_count']==1 and plan['new_images']==0
    assert sha(HERE/'runtime/consumer_transport.py') == plan['consumer_transport_sha256']
    assert sha(HERE/'runtime/actor.py') == plan['actor_sha256'] and sha(Path(__file__)) == plan['preflight_driver_sha256']
    for name, digest in plan['dispatch_input_sha256'].items():
        assert sha(HERE/name) == digest, 'frozen_dispatch_input_changed: '+name
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
            'cell_started_ns': cell_started_ns, 'worker_deadline_ns': cell_deadline_ns}
        try:
            for name, digest in plan['dispatch_input_sha256'].items():
                assert sha(HERE/name) == digest, 'frozen_dispatch_input_changed: '+name
            task = plan['tasks'][slot['task']]
            assert sha(HERE/task['snapshot']) == task['snapshot_sha256'], 'frozen_mesh_snapshot_changed'
            prompt = (HERE/plan['inputs']['prompt']).read_bytes()
            assert hashlib.sha256(prompt).hexdigest() == plan['inputs']['prompt_sha256']
            transport.initial_image_metadata(plan)
            if time.perf_counter_ns() >= cell_deadline_ns:
                raise TimeoutError('original_full_cell_deadline_exceeded')
            folder, process, _ = prepare(slot, output=HERE/'cells'/slot['cell'], cell_started_ns=cell_started_ns)
            snapshot_binding(read(folder/'owner/INITIAL.json'), read(HERE/task['snapshot']))
            if time.perf_counter_ns() >= cell_deadline_ns:
                raise TimeoutError('original_full_cell_deadline_exceeded')
            row['consumer'] = transport.consume(slot,
                {'python': plan['installation_ready']['dependency_python']}, plan, prompt)
        except BaseException as exc:
            row['errors'].append({'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
            stop = 'launch_or_execution_state_requires_review; no replacement consumer'
        finally:
            if process is not None:
                try:
                    row['finish'] = finish(folder, process)
                except BaseException as exc:
                    row['errors'].append({'type': type(exc).__name__, 'message': str(exc)})
            row['cell_ended_ns'] = time.perf_counter_ns()
            row['cell_timing_scope'] = 'before per-cell input validation through owner close; excludes subsequent cell accounting publication'
            row['full_cell_wall_ns'] = row['cell_ended_ns']-cell_started_ns
            row['within_570s'] = row['full_cell_wall_ns'] < 570*10**9
            if row['consumer'] is not None:
                consumer = row['consumer']
                consumer['owner_finish'] = row['finish']
                consumer['total_task_wall_ns'] = row['full_cell_wall_ns']
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
                if any(word in diagnostics.lower() for word in ('quota', 'usage limit', 'rate limit', '429', '503')):
                    stop = 'provider_availability_or_quota; no retry or replacement'
            if not row['finish'] or not row['finish'].get('confirmed'):
                stop = 'owner_backend_close_unconfirmed'
            if not row['within_570s']:
                stop = 'original_full_cell_deadline_exceeded'
            records.append(row)
            save(HERE/'RUN_RESULT.json', {'records': records, 'stop': stop,
                'started_cells': len(records), 'maximum_consumers': 6,
                'all_planned_dispatched': len(records) == 6, 'no_replacements': True})
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
    assert plan['candidate_source_sha256']==CANONICAL
    prompt=(HERE/plan['inputs']['prompt']).read_bytes()
    assert hashlib.sha256(prompt).hexdigest()==plan['inputs']['prompt_sha256']
    transport=load('_m4_prepared_inputs',HERE/'runtime/consumer_transport.py')
    image=transport.initial_image_metadata(plan)
    return {'cycle_id':CYCLE,'phase':'PREPARATION_ONLY','prompt_sha256':plan['inputs']['prompt_sha256'],
        'prompt_utf8_bytes':len(prompt),'initial_image':image,'image_delivery':'pending',
        'model_consumers':0,'tool_images':0,'new_images':0,
        'scope':'input bytes and CLI --image capability only; not provider delivery or model visual consumption'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='PREPARED_INPUT.json',help='New runtime metadata receipt; no model dispatch')
    args=parser.parse_args()
    assert Path(args.output).name==args.output and args.output not in ('.','..')
    output=HERE/'runtime'/args.output
    if output.exists():raise FileExistsError('preserve_existing_preparation_receipt')
    result=preflight_inputs();save(output,result)
    print(json.dumps({'phase':'PREPARATION_ONLY','model_consumers':0,'output':str(output)}))
