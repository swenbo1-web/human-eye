"""Prepare and preflight frozen M1 tasks; this command never starts a model."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANONICAL = '0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


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
    tasks = read(HERE/'TASKS.json')
    ready = read(HERE/'installation/READY.json')
    task, group = tasks[slot['task']], slot['group']
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=False)
    assert ready['source_sha256'] == CANONICAL
    asset = HERE/task['asset']
    assert sha(asset) == task['asset_sha256']
    schemas = [] if group == 'N' else read(HERE/'catalogues'/group/'PUBLIC_TOOLS.json')
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
    command = [ready['dependency_python'], '-I', '-B', str(HERE/'actor.py'), '--config', str(folder/'ACTOR_CONFIG.json')]
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


def check_distance(value, interval, tolerance):
    assert type(value) in (int, float) and math.isfinite(value)
    assert max(abs(value-end) for end in interval) <= tolerance, 'outside_independent_distance_tolerance'


def check_fact(task, group, value):
    assert value['execution_authority'] is False
    binding = value['context'] if task['kind'] == 'relations' and group == 'S' else value['binding']
    assert binding['runtime_source_sha256'] == CANONICAL
    if task['kind'] == 'nearest':
        assert value['result_kind'] == 'surface_nearest' and value['status'] == 'complete'
        assert value['focal']['name'] == task['target']
        assert sorted(r['name'] for r in value['nearest_objects']) == sorted(task['nearest_names'])
        check_distance(value['distance_m'], task['distance_interval_m'], task['tolerance_m'])
        c = value['coverage']
        assert c['targets_excluding_focal'] == task['candidate_count'] and c['unresolved'] == 0 and value['unresolved'] == []
        assert c['distance_valid']+c['strictly_excluded'] == task['candidate_count']
        return {'kind': 'global_unsigned_nearest', 'winner_names': task['nearest_names'],
            'distance_m': value['distance_m'], 'coverage': c, 'independent_truth_sha256': task['truth_sha256']}
    assert value['status'] == 'observed'
    if group == 'S':
        assert value['target']['name'] == task['target']
        rows = value['candidates']
        assert [r['name'] for r in rows] == task['candidates']
        penetrating = [rows[i]['name'] for i in value['sets']['penetrating']['candidate_indices']]
        nearest = [rows[i]['name'] for i in value['sets']['nearest_separated']['candidate_indices']]
        assert value['sets']['penetrating']['complete'] and value['sets']['nearest_separated']['complete']
        distance = value['sets']['nearest_separated']['distance_m']
    else:
        objects = value['binding']['objects']
        assert objects[0]['name'] == task['target'] and [r['name'] for r in objects[1:]] == task['candidates']
        rows = [{'name': task['candidates'][i], **r['facts'], 'separation_gap': r['separation_gap']} for i, r in enumerate(value['pairs'])]
        names = {r['object_id']: r['name'] for r in objects}
        penetrating = [names[i] for i in value['summary']['penetrating_ids']]
        nearest = [names[i] for i in value['summary']['nearest_separated_ids']]
        assert value['summary']['penetration_set_complete'] and value['summary']['nearest_separated_complete']
        distance = value['summary']['distance_m']
    assert sorted(penetrating) == sorted(task['penetrating_names']) and sorted(nearest) == sorted(task['nearest_names'])
    for row in rows:
        expected = task['facts'][row['name']]
        assert row['closed_solid_relation']['status'] == 'measured' and row['closed_solid_relation']['value'] == expected['relation']
        if expected['relation'] == 'separated':
            assert row['separation_gap']['status'] == 'measured'
            check_distance(row['separation_gap']['value'], expected['distance_interval_m'], task['tolerance_m'])
        else:
            assert row['separation_gap']['status'] == 'not_applicable' and row['separation_gap']['value'] is None
    check_distance(distance, task['distance_interval_m'], task['tolerance_m'])
    return {'kind': 'selected_relations', 'nearest_names': nearest, 'penetrating_names': penetrating,
        'distance_m': distance, 'independent_truth_sha256': task['truth_sha256']}


def preflight(output, selected):
    output.mkdir(exist_ok=False)
    tasks = read(HERE/'TASKS.json')
    ready = read(HERE/'installation/READY.json')
    client = load('_m1_eval_preflight_client', HERE/'preflight_client.py')
    results = []
    for task_id in selected:
        task = tasks[task_id]
        assert sha(HERE/task['truth']) == task['truth_sha256']
        for group in ('N', 'C', 'S'):
            folder, process, start = None, None, time.perf_counter_ns()
            row = {'task': task_id, 'group': group, 'passed': False, 'started_ns': start, 'errors': [], 'models': 0}
            try:
                folder, process, start = prepare({'task': task_id, 'group': group}, output=output/(task_id+'_'+group))
                snapshot_binding(read(folder/'owner/INITIAL.json'), read(HERE/task['snapshot']))
                messages = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'no-model-m1-preflight', 'version': '001'}}},
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                    {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'execute_blender_code', 'arguments': None}},
                    {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'execute_blender_code', 'arguments': {'code': "import json\nprint(json.dumps({'unit_scale_m':bpy.context.scene.unit_settings.scale_length,'objects':[{'name':o.name,'vertices':len(o.data.vertices),'faces':len(o.data.polygons)} for o in bpy.context.scene.objects if o.type=='MESH']}))"}}}]
                if group != 'N':
                    query = ({'mode': 'task', 'target': {'name': task['target']}, 'candidates': [{'name': n} for n in task['candidates']], 'requested_facts': ['closed_solid_relation', 'surface_proximity']}
                        if task['kind'] == 'relations' else {'mode': 'surface_nearest', 'objects': [{'name': task['target']}]})
                    name = 'human_eye_scene_observe' if group == 'C' else 'human_eye_spatial_relations' if task['kind'] == 'relations' else 'human_eye_surface_nearest'
                    arguments = {'session_id': 'current-scene', 'include_image': False, 'query': query} if group == 'C' else {
                        'target': {'name': task['target']}, **({'candidates': [{'name': n} for n in task['candidates']]} if task['kind'] == 'relations' else {})}
                    messages.append({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})
                probe = client.probe(ready['dependency_python'], folder/'ENDPOINT.json', folder/'thin_probe', messages)
                assert probe['confirmed'], 'thin_stdio_close_not_confirmed'
                replies = {r['id']: r for r in probe['responses']}
                expected_names = {'execute_blender_code'} | (set() if group == 'N' else {t['name'] for t in read(HERE/'catalogues'/group/'PUBLIC_TOOLS.json')})
                assert {t['name'] for t in replies[2]['result']['tools']} == expected_names
                assert replies[3]['result']['isError'] is True, 'null_guard_not_rejected'
                assert replies[4]['result']['isError'] is False, 'common_native_read_failed'
                if group != 'N':
                    assert replies[5]['result']['isError'] is False, 'product_query_not_successful'
                    blocks = replies[5]['result']['content']
                    assert len(blocks) == 1 and blocks[0]['type'] == 'text', 'zero_image_or_single_fact_contract'
                    row['facts'] = check_fact(task, group, json.loads(blocks[0]['text']))
                assert read(folder/'owner/tool_01/ATTEMPT.json')['is_error'] is True
                assert read(folder/'owner/TOOLS.json')['attempts'] == (2 if group == 'N' else 3)
                row['null_rejection_accounted'] = True
                row['thin_pid'] = probe['thin_pid']
                row['thin_exit_confirmed'] = probe['client_exit_confirmed']
                row['tool_bytes'] = probe['tool_response_bytes']
                row['snapshot_matches_independent_truth'] = True
            except BaseException as exc:
                row['errors'].append({'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()})
            finally:
                if process is not None:
                    try:
                        row['finish'] = finish(folder, process)
                        assert row['finish']['confirmed'], 'actor_worker_close_unconfirmed'
                    except BaseException as exc:
                        row['errors'].append({'type': type(exc).__name__, 'message': str(exc)})
                row['ended_ns'] = time.perf_counter_ns()
                row['passed'] = not row['errors'] and bool(row.get('finish', {}).get('confirmed')) and row['ended_ns'] < start+570*10**9
                if folder is not None:
                    save(folder/'PREFLIGHT_RESULT.json', row)
                results.append(row)
                save(output/'RESULTS.json', {'passed': len(results) == len(selected)*3 and all(r['passed'] for r in results), 'cases': results, 'model_calls': 0})
                print(json.dumps({'task': task_id, 'group': group, 'passed': row['passed'], 'errors': [e['message'] for e in row['errors']]}), flush=True)
            if not row['passed']:
                return False
    return True


def run_models():
    """Explicit later-phase entry only; this preparation batch never calls it."""
    batch_started_ns = time.perf_counter_ns()
    go, plan = read(HERE/'GO.json'), read(HERE/'PLAN.json')
    assert go['task'] == 'M1-TASK-ENTRY-001_EVAL' and go['authorized'] is True
    assert go['plan_sha256'] == sha(HERE/'PLAN.json') and go['max_consumers'] == 27
    assert plan['fixed_product_commit'] == '7411ac7aa9338f17355ffe5cdf4df113ce862aed'
    assert plan['candidate_source_sha256'] == CANONICAL and len(plan['sequence']) == 27
    assert sha(HERE/'consumer_transport.py') == plan['consumer_transport_sha256']
    assert sha(HERE/'actor.py') == plan['actor_sha256'] and sha(Path(__file__)) == plan['preflight_driver_sha256']
    for name, digest in plan['dispatch_input_sha256'].items():
        assert sha(HERE/name) == digest, 'frozen_dispatch_input_changed: '+name
    transport = load('_m1_eval_fixed_consumer', HERE/'consumer_transport.py')
    assert sha(transport.EXE) == plan['CLI_sha256']
    with (HERE/'STARTED.json').open('x') as stream:
        json.dump({'started_ns': time.perf_counter_ns(), 'max_consumers': 27,
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
            prompt = (HERE/'SESSION_RULES.txt').read_bytes()+b'\n'+(HERE/task['prompt']).read_bytes()
            assert hashlib.sha256(prompt).hexdigest() == task['model_input_sha256']
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
                'started_cells': len(records), 'maximum_consumers': 27,
                'all_planned_dispatched': len(records) == 27, 'no_replacements': True})
        if stop:
            break
    batch_ended_ns = time.perf_counter_ns()
    result = {'records': records, 'stop': stop,
        'started_cells': len(records), 'maximum_consumers': 27,
        'all_planned_dispatched': len(records) == 27, 'no_replacements': True,
        'batch_started_ns': batch_started_ns, 'batch_ended_ns': batch_ended_ns,
        'batch_wall_ns': batch_ended_ns-batch_started_ns,
        'batch_timing_scope': 'run_models entry through last per-cell RUN_RESULT publication; includes batch setup and cell accounting, excludes final timing-summary publication and caller overhead; not model reasoning time'}
    save(HERE/'RUN_RESULT.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='Fresh immediate child directory')
    parser.add_argument('--tasks', nargs='+', choices=('T1', 'T2', 'T3'), default=['T1', 'T2', 'T3'])
    args = parser.parse_args()
    assert Path(args.output).name == args.output and args.output not in ('.', '..')
    raise SystemExit(0 if preflight(HERE/args.output, args.tasks) else 1)
