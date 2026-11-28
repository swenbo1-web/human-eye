"""Drive the installed MCP and one Blender subprocess in each frozen arm."""
import argparse
from collections import deque
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
BATCH = 'M4-NEAREST-FOCUS-OCCLUSION-MOVE-001'
PRIOR = HERE.parent / 'm4_task_region_focus_feedback_001/runner.py'
spec = importlib.util.spec_from_file_location('prior_task_focus_runner', PRIOR)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
pin, read, save, need = prior.pin, prior.read, prior.save, prior.need
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
CASES = ('OPEN_POS_X','OPEN_POS_X_WARM','OPEN_POS_X_NO_IMAGE','OPEN_NEG_X','VISIBLE','SEALED')
BASELINE = 'ad35b150b1cdc3d90a9de894d49ebaf2148efc88'
BASELINE_SOURCE = 'ba95b60a131613f723bdb4a0ff8cbade5ab39af0903c2269a5548fefc0de7c04'
BASELINE_WHEEL = '7e7f1e30ec4bc0b36f9fa88728a37dae9984a4cee85f6316a28f849d759d9262'
BASELINE_CUSTODY = 'ea7995594709e4922168e73672085e4a40ceedfd32847ef43f6763104aacbed2'
MAX_LINE = 64*1024*1024
PROFILE = {'request_budget_s': 30, 'startup_timeout_s': 45, 'wire_timeout_s': 50,
           'slot_window_ns': 190_000_000_000, 'two_actual_rasters_per_request': 2, 'blender_hosts_per_arm': 1, 'models': 0}


def confirmed(item):
    path = Path(item['path']).resolve(strict=True)
    actual = pin(path)
    need(all(actual[k] == item[k] for k in ('bytes','sha256')), 'frozen_input_changed/' + str(path))
    return path


def fixture_for(root):
    folder = root/'preflight/fixture'
    receipt = folder/'ASSET_BINDING.json'
    value = read(receipt)
    need(value['save_count'] == 1 and value['rasters'] == 0 and value['reopened_source_exact']
         and confirmed(value['builder']) == HERE/'build_fixture.py'
         and confirmed(value['plan']) == root/'preflight/ADMIN_PLAN.md', 'wrong_blender_fixture_receipt')
    files = {k:confirmed(value[k]) for k in ('asset','source','truth','requests')}
    need(files == {'asset':folder/'main.blend','source':folder/'CURRENT_SOURCE.json',
                   'truth':folder/'TRUTH.json','requests':folder/'REQUESTS.json'}, 'wrong_fixture_artifact_path')
    corpus = read(files['requests'])
    need([row['label'] for row in corpus] == list(CASES)
         and [row['arguments']['include_image'] for row in corpus] == [True,True,False,True,True,True]
         and corpus[0]['arguments']==corpus[1]['arguments']
         and read(files['truth'])['asset_sha256']==pin(files['asset'])['sha256'], 'fixture_request_corpus_drift')
    return {'blend':pin(files['asset']),'source':pin(files['source']),'truth':pin(files['truth']),
            'requests':pin(files['requests']),'asset_binding':pin(receipt)}, corpus


def install_for(root, arm):
    path = (root.parent/'M4-NEAREST-SURFACE-COMPONENT-REF-001/preflight/INSTALL_CUSTODY.json'
            if arm == 'A' else root/'preflight/INSTALL_CUSTODY.json')
    custody = read(path)
    if arm == 'A':
        need(pin(path)['sha256']==BASELINE_CUSTODY and custody['candidate_commit']==BASELINE
             and custody['source_sha256']==BASELINE_SOURCE and custody['wheel']['sha256']==BASELINE_WHEEL,
             'baseline_identity_changed')
    else:
        build = read(confirmed(custody['build']))
        need(build['parent_commit']==BASELINE and build['candidate_commit']==custody['candidate_commit']
             and custody['source_sha256'] != BASELINE_SOURCE, 'candidate_not_built_from_fixed_baseline')
    site = Path(custody['installation']['path']).resolve(strict=True)
    need(custody['passed'] and custody['runtime_sources']==len(custody['source_manifest'])==146
         and confirmed(custody['python'])==Path(sys.executable).resolve() and sys.flags.isolated
         and sys.dont_write_bytecode, 'runtime_or_installation_invalid')
    for field in ('wheel','blender','build'):
        confirmed(custody[field])
    for dep in custody['dependencies'].values():
        confirmed(dep['module'])
    loaded = [pin(site/row['path'])['sha256'] for row in custody['source_manifest']]
    need(loaded==[row['sha256'] for row in custody['source_manifest']], 'installed_runtime_source_changed')
    return pin(path), custody, site


def check_freeze(root, arm, fixture, installation):
    path = root / ('preflight/FROZEN_BASELINE.json' if arm=='A' else 'preflight/FROZEN_CANDIDATE.json')
    freeze = read(path)
    need(freeze['batch']==BATCH, 'freeze_wrong_batch')
    file = freeze['baseline_installation'] if arm=='A' else freeze['candidate_installation']
    need(confirmed(file)==Path(installation['path']).resolve(), 'freeze_wrong_installation')
    need(all(confirmed(freeze['fixture'][k]) == Path(record['path']).resolve()
             for k,record in fixture.items()), 'freeze_wrong_fixture')
    for item in freeze.get('inputs', ()):
        confirmed(item)
    return pin(path)


def packets(corpus):
    rows = [('initialize',{'protocolVersion':'2024-11-05','capabilities':{},
                           'clientInfo':{'name':'owned-mirrored-focus-check','version':'1'}},'INITIALIZE'),
            ('tools/list',{},'DIRECTORY')]
    rows.extend(('tools/call',{'name':'human_eye_scene_observe','arguments':r['arguments']},r['label']) for r in corpus)
    return [(label,{'jsonrpc':'2.0','id':i,'method':method,'params':params})
            for i,(method,params,label) in enumerate(rows,1)]


def encode(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')+b'\n'


def verify_initial_source(capture, source):
    wanted = {r['name']:r['evaluated'] for r in source['objects']}
    actual = {r['name']:{'vertices_world':r['vertices'],'triangles':r['faces']} for r in capture['meshes']}
    need(actual==wanted and capture['unit']=='m' and capture['coordinate_frame']=='world' and capture['source']=='blender'
         and capture['capture_state'] is not None and capture['display_snapshot']['status']=='captured',
         'actual_blender_source_differs_from_frozen_readback')


def instrument(service, folder, corpus):
    from human_eye_plugin import active_observation_images, observation_focus
    original_observe = service._observe_active_observation
    original_capture = observation_focus._capture_region_frame
    original_raster = active_observation_images.rasterize_attention
    active, next_cases = None, deque(corpus)

    def observe(session, **kwargs):
        nonlocal active
        need(active is None and next_cases, 'unregistered_service_dispatch')
        row = next_cases.popleft()
        args = row['arguments']
        need(kwargs.get('include_image') is args['include_image']
             and [kwargs.get('selector')]==args['query']['objects']
             and kwargs.get('focus')==args['query']['focus']
             and kwargs.get('task_query') is None and kwargs.get('region_task') is None,
             'original_argument_normalization_changed')
        case = folder/'cases'/row['label']
        case.mkdir(parents=True)
        frames = []
        work = {'label':row['label'],'raster_calls':[], 'service_started_ns':time.perf_counter_ns(),
                'completion_error':None}
        active = (work, frames)
        try:
            result = original_observe(session, **kwargs)
            work['service_returned_ns'] = time.perf_counter_ns()
            save(case/'PRODUCER.json',result)
            return result
        except BaseException as err:
            work['completion_error'] = type(err).__name__ + ': ' + str(err)
            raise
        finally:
            work.setdefault('service_returned_ns',time.perf_counter_ns())
            save(case/'WORK.json', work)
            save(case/'FRAMES.json', frames)
            active = None

    def capture(*args, **kwargs):
        need(active is not None, 'source_frame_without_active_request')
        started = time.perf_counter_ns()
        frame, sample = original_capture(*args, **kwargs)
        completed = time.perf_counter_ns()
        prepared = args[0]
        offsets = prepared.images._patch_mapping['arrays']['face_patch_offsets']
        active[1].append({'frame':frame,'sample':sample,'object_index':prepared.object_index,
            'source_triangle_indices':list(prepared.source_triangle_indices),
            'face_patch_offsets':[int(value) for value in offsets],
            'source_mapping':prepared.source_mapping,'started_ns':started,'completed_ns':completed,
            'png':pin(frame['image_path']),'npz':pin(frame['arrays_path'])})
        return frame, sample

    def raster(*args, **kwargs):
        need(active is not None and len(active[0]['raster_calls'])<PROFILE['two_actual_rasters_per_request'],
             'two_actual_rasters_per_request')
        event = {'started_ns':time.perf_counter_ns(),'completed':False}
        active[0]['raster_calls'].append(event)
        try:
            result = original_raster(*args, **kwargs)
            event['completed'] = True
            return result
        finally:
            event['closed_ns'] = time.perf_counter_ns()

    service._observe_active_observation = observe
    observation_focus._capture_region_frame = capture
    active_observation_images.rasterize_attention = raster
    return next_cases


def worker(root, arm, stage):
    fixture, corpus = fixture_for(root)
    installed_pin, install, site = install_for(root,arm)
    folder = root / ('slots' if stage == 'real' else 'preflight/real_entry_probe_final') / arm
    if stage == 'real':
        registration = read(folder/'REGISTERED.json')
        need(registration == {'arm':arm,'freeze':check_freeze(root,arm,fixture,installed_pin),'profile':PROFILE},
             'worker_without_frozen_registration')
    sys.path.insert(0,str(site))
    from human_eye_plugin import blender_process, live_spatial_mcp
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity
    ident = runtime_identity()
    need(ident['source_kind']=='installed_distribution' and ident['source_sha256']==install['source_sha256']
         and ident['source_files']==install['source_manifest'], 'worker_import_is_not_frozen_installed_product')
    config_path = folder/'config.json'
    save(config_path,{'schema_version':'1.0','enabled':True,'project_root':str(folder),'state_file':'state.json',
                      'audit_file':'audit.jsonl','request_budget_s':PROFILE['request_budget_s'],
                      'expected_identity':{'source_sha256':ident['source_sha256']}})
    copy = prior.prior.copied_input(folder, {'fixture': fixture['blend']})
    real_subprocess = blender_process.subprocess
    launch = prior.Launch(folder,'formal' if stage=='real' else 'cold',
                          {'blender':install['blender'],'candidate_site':str(site)},copy)
    blender_process.subprocess = launch
    host,initial,post,failure=None,None,None,None
    try:
        if stage == 'probe':
            trial = LiveSpatialService(config_path,host=object(),production_mode=True)
            entered = []
            def boundary(session, **kwargs):
                entered.append(kwargs)
                raise ValueError('offline_preflight_boundary_after_parameter_normalization')
            trial._observe_active_observation = boundary
            malformed = {'label':'MALFORMED','arguments':{
                **corpus[0]['arguments'], 'query':{**corpus[0]['arguments']['query'], 'focus':{'task_region':{}}}}}
            input_stream = io.StringIO(b''.join(encode(req) for _,req in packets([malformed,*corpus])).decode())
            output_stream = io.StringIO()
            live_spatial_mcp.run_stdio_mcp_server(trial,input_stream,output_stream)
            rx = [json.loads(line) for line in output_stream.getvalue().splitlines()]
            need(len(rx) == 9 and len(entered)==6 and rx[2]['result']['isError']
                 and rx[0]['result']['_meta']['human_eye']['source_sha256']==install['source_sha256']
                 and all('offline_preflight_boundary_after_parameter_normalization' in item['result']['content'][0]['text']
                         for item in rx[3:]), 'actual_installed_public_tool_preflight_failed')
            save(folder/'PUBLIC_ENTRY.json',{'replies':rx,'normalized':entered,'product_identity':ident,
                                            'candidate_site':str(site),'host_launches':0})
        try:
            host = blender_process.BlenderProcessHost(install['blender']['path'],copy,timeout=25,
                                                      startup_timeout=PROFILE['startup_timeout_s'])
        except prior.prior.AtReservation:
            need(stage=='probe' and launch.process is None, 'unexpected_launch_reservation')
            return
        need(stage=='real' and host._process is launch.process, 'unexpected_or_unowned_actual_host')
        service = LiveSpatialService(config_path,host=host,production_mode=True)
        initial = host.capture_scene()
        verify_initial_source(initial,read(fixture['source']['path']))
        save(folder/'initial_capture.json',initial)
        before = pin(folder/'initial_capture.json')
        save(folder/'ready.json',{'pid':host._process.pid,'initial_capture':before,'source':ident,
                                 'fixture':pin(copy)})
        pending = instrument(service,folder,corpus)
        def finish():
            nonlocal post
            post = host.capture_scene()
            save(folder/'post_capture.json',post)
        service.close = finish
        live_spatial_mcp.run_stdio_mcp_server(service)
        need(not pending and post is not None,'public_stream_closed_before_all_cases_or_capture')
    except BaseException as error:
        failure = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        blender_process.subprocess = real_subprocess
        if stage == 'real':
            proc = launch.process
            try:
                if host is not None:
                    host.close()
                elif proc is not None and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
                if launch.wire is not None:
                    launch.wire.publish()
            finally:
                after = pin(copy)
                save(folder/'closed.json',{'pid':proc.pid if proc else None,'native_spawned':proc is not None,
                    'blender_exit':proc.poll() if proc else None,'failure':failure,
                    'same_before_after_capture':initial is not None and initial==post,
                    'fixture_sha256_before':fixture['blend']['sha256'],'fixture_sha256_after':after['sha256'],
                    'post_capture':pin(folder/'post_capture.json') if post is not None else None})


def run(root,arm,stage):
    fixture, corpus = fixture_for(root)
    install_pin, _, _ = install_for(root,arm)
    if stage == 'run':
        freeze = check_freeze(root,arm,fixture,install_pin)
        folder = root/'slots'/arm
        folder.mkdir(parents=True,exist_ok=False)
        save(folder/'REGISTERED.json',{'arm':arm,'freeze':freeze,'profile':PROFILE})
        worker_stage = 'real'
    else:
        folder = root/'preflight/real_entry_probe_final'/arm
        folder.mkdir(parents=True,exist_ok=False)
        worker_stage = 'probe'
    command = [sys.executable,'-IB','-X','utf8',str(Path(__file__).resolve()),str(root),'worker',arm,worker_stage]
    with (folder/'stderr.bin').open('xb') as err:
        slot_started = time.perf_counter_ns()
        deadline = slot_started + PROFILE['slot_window_ns']
        process = subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                    stderr=err,creationflags=NO_WINDOW,env=prior.prior.process_env())
        replies = queue.Queue()
        wire = []
        failed = None
        def receive():
            try:
                while raw := process.stdout.readline(MAX_LINE+1):
                    replies.put(raw)
            except (OSError,ValueError) as exc:
                replies.put(exc)
            finally:
                replies.put(None)
        reader = threading.Thread(target=receive,daemon=True)
        try:
            reader.start()
            if stage=='run':
                for label, packet in packets(corpus):
                    index = packet['id']
                    path = folder/'wire'/f'{index:03d}'
                    path.mkdir(parents=True)
                    tx = encode(packet)
                    (path/'TX.bin').write_bytes(tx)
                    start = time.perf_counter_ns()
                    process.stdin.write(tx)
                    process.stdin.flush()
                    remaining = (deadline-time.perf_counter_ns())/1e9
                    need(remaining > 0, 'absolute_slot_window_exhausted')
                    rx = replies.get(timeout=min(remaining,PROFILE['wire_timeout_s']))
                    received = time.perf_counter_ns()
                    need(type(rx) is bytes and len(rx)<=MAX_LINE and rx.endswith(b'\n'),
                         'public_response_not_complete/' + label)
                    (path/'RX.bin').write_bytes(rx)
                    response = json.loads(rx)
                    need(response['id']==index and response['jsonrpc']=='2.0','public_response_id_mismatch')
                    wire.append({'label':label,'id':index,'tx':pin(path/'TX.bin'),'rx':pin(path/'RX.bin'),
                                 'sent_ns':start,'received_ns':received,
                                 'success':not ('error' in response or response.get('result',{}).get('isError'))})
        except BaseException as exc:
            failed = type(exc).__name__ + ': ' + str(exc)
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=35)
            except subprocess.TimeoutExpired:
                failed = 'worker_close_timeout' if failed is None else failed
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            if reader.ident is not None:
                reader.join(timeout=5)
            process.stdout.close()
    if stage=='run':
        with (folder/'wire/INDEX.jsonl').open('xb') as stream:
            for item in wire:
                stream.write(encode(item))
        closed = read(folder/'closed.json') if (folder/'closed.json').is_file() else None
        complete_ns = time.perf_counter_ns()-slot_started
        success = failed is None and complete_ns<=PROFILE['slot_window_ns'] and process.returncode==0 and len(wire)==8 and all(r['success'] for r in wire) \
            and closed is not None and closed['blender_exit']==0 and closed['same_before_after_capture'] \
            and closed['fixture_sha256_after']==fixture['blend']['sha256']
        save(folder/'RESULT.json',{'arm':arm,'passed':success,'worker_exit':process.returncode,'closed':closed,
                 'failure':failed,'model_consumers':0,'profile':PROFILE,'complete_slot_ns':complete_ns,'confirmed_wire_exchanges':len(wire)})
    else:
        success = failed is None and process.returncode==0 and (folder/'PUBLIC_ENTRY.json').is_file() \
            and (folder/'AT_APPOINTMENT.json').is_file() and not (folder/'Blender_SPAWN.json').exists()
        save(folder/'RESULT.json',{'arm':arm,'passed':success,'worker_exit':process.returncode,
                 'failure':failed,'fixture':fixture,'installed':install_pin,'blender_starts':0,'model_consumers':0})
    need(success,'public_runner_did_not_complete/' + arm + '/' + stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('stage',choices=('worker','run','probe'))
    parser.add_argument('arm',choices=('A','B'))
    parser.add_argument('worker_stage',nargs='?',choices=('probe','real'))
    options=parser.parse_args()
    root=options.root.resolve(strict=True)
    need(root.name==BATCH, 'only_the_frozen_batch_root_is_supported')
    if options.stage=='worker':
        worker(root,options.arm,options.worker_stage)
    else:
        run(root,options.arm,options.stage)
