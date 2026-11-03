"""Finite, paired cost disclosure for two immutable installed releases.

No live connector, production state, cache or source is edited. The TCP fixture
implements only the addon wire envelope and exact fixed read templates; it is
not a qualification of an arbitrary third-party addon. Cold means a new process,
not a cold filesystem. Native images must come from the real engine/Blender.
"""
from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import queue
import socket
import statistics
import subprocess
import sys
import threading
import time
import types

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'verification/fixes/20261103_deployment_core_projection'
PYTHON = ROOT / '.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
ARMS = {
    'old': {'release': '9.7.2+20261031.dense.focus.r1', 'count': 78,
            'sha': '22fb2523bdbfb68d6e7227ea3df3b4373daa1a76461344bc1755406c5feeec8a'},
    'candidate': {'release': '9.7.2+20261103.safety.source.r1', 'count': 124,
                  'sha': '3fa7dfb05b6796044b2b4d37e2e67e7def8957ce3a471879d2e9b8f142006ef2'},
}
PAIRS = 8
HOT = 3
MAX_RESPONSE = 64 * 1024 * 1024
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def save(path, value):
    """Exclusive publication; close/flush is included, no extra fsync claim."""
    with Path(path).open('xb') as stream:
        stream.write(encode(value))
        stream.write(b'\n')


def strict_loads(raw):
    def unique(pairs):
        value = {}
        for key,child in pairs:
            if key in value:
                raise ValueError('duplicate_response_key')
            value[key] = child
        return value
    def constant(value):
        raise ValueError('nonfinite_response')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=constant)


def nearest_rank(values, fraction=.95):
    if not values or not 0 < fraction <= 1:
        raise ValueError('nonempty values and 0<fraction<=1 required')
    return sorted(values)[math.ceil(len(values) * fraction) - 1]


def order(pair):
    return ('old', 'candidate') if pair % 2 == 0 else ('candidate', 'old')


def arm_paths(name):
    release = ROOT / '.human-eye/releases' / ARMS[name]['release']
    return release, release / 'site-packages', release / 'admin/target_runtime_entry.py'


def object_id(name):
    return 'blender:' + digest(json.dumps(['', name], sort_keys=True, ensure_ascii=False,
                                       separators=(',', ':'), allow_nan=False).encode())


def validate_identity(identity, arm):
    expected = ARMS[arm]
    if (identity.get('source_sha256') != expected['sha'] or
            identity_count(identity) != expected['count'] or
            identity.get('source_kind') != 'installed_distribution'):
        raise ValueError('unexpected_runtime_identity:' + arm)


def identity_count(identity):
    count=identity.get('source_file_count')
    manifest=identity.get('source_files')
    if isinstance(manifest,list):
        if count is not None and count != len(manifest):
            raise ValueError('identity_manifest_count_disagrees')
        return len(manifest)
    return count


def preregister(output, lanes='both'):
    output.mkdir(parents=True, exist_ok=True)
    # Only the explicit two local receipts and executable are examined.
    bindings = {}
    for name in ARMS:
        release, site, entry = arm_paths(name)
        receipt = entry.with_name('RUNTIME_BINDING.json')
        binding = json.loads(receipt.read_text(encoding='utf8'))
        if (binding['identity']['source_sha256'] != ARMS[name]['sha'] or
                len(binding['source_files']) != ARMS[name]['count']):
            raise ValueError('fixed_receipt_changed')
        bindings[name] = {'release': str(release), 'site': str(site), 'entry': str(entry),
                          'binding_sha256': digest(receipt.read_bytes()),
                          'entry_sha256': digest(entry.read_bytes()), **ARMS[name]}
    contract = dict(schema='deployment-complete-cost-v1', pairs=PAIRS, hot_per_kind=HOT,
        pair_orders=[list(order(i)) for i in range(PAIRS)], arms=bindings,
        python=str(PYTHON), blender=str(BLENDER), expected_blender_version=[5, 2, 1],
        harness_sha256=digest(Path(__file__).read_bytes()), quad_size=384,
        gap_m=.004, gap_tolerance_m=1e-6, python_flags=['-I', '-B'],
        request_budget_s=None, tcp_timeout_s=10, native_visual_timeout_s=10,
        observer_wait_s=60, owned_rpc_timeout_s=30, owned_startup_timeout_s=60,
        selected_lanes=lanes,
        counts_per_arm={'cold_service': 8 if lanes!='owned' else 0, 'cold_first_native_observation': 8 if lanes!='owned' else 0,
                        'hot_native_observation': 24 if lanes!='owned' else 0, 'ordinary_gap_text': 24 if lanes!='owned' else 0,
                        'status': 24 if lanes!='owned' else 0,
                        'owned_worker_start_capture_close': 8 if lanes!='tcp' else 0},
        lanes=['default_fixed_entry_external_qa_tcp', 'external_qa_blender_fixture',
               'owned_fixed_file_worker'],
        timing={'rtt': 'before stdin write through complete JSON response arrival',
                'call_complete': 'before write through strict parse, identity/behavior checks and archive close',
                'cold_service': 'before fixed-entry Popen through initialize verification and archive close',
                'cold_first_native': 'same Popen through first image response verification and archive close',
                'service_cycle': 'before Popen through all calls, EOF, wait and local log/state digest publication',
                'owned_cycle': 'before helper Popen through fixed bootstrap imports, worker startup, captures, persistence, close and helper exit',
                'external_fixture': 'before Blender Popen through READY; shutdown STOP through exit'},
        native_images='actual fixed engine native multiscale rendering, PNG 384x384; projection does not pass native lane',
        persistence='original engine state/audit close semantics retained; verifier archive close, no fsync durability upgrade/downgrade',
        cold_scope='fresh process only; OS cache retained; no pyc deletion; Python -B prevents new pyc',
        compatibility='same static 8-vertex/twelve-face boxes, fixed-file owned copy; external TCP read envelopes only. No real third-party addon, GUI, arbitrary assets or live Hook qualification.',
        outcomes='all registered attempts retained; refused/unknown/environment unsupported are not passed or dropped',
        stop='identity, geometry mutation, deadline, parsing or early exit stops affected independent lane; unsupported image lane is reported and other lanes continue; no replacing failed samples',
        analysis='median, nearest-rank p95, absolute/relative paired deltas; n=8 p95 is maximum and not significance. Correctness cost disclosure only; historical M1/M2 failed gates unchanged.',
        cost='local elapsed time and archive bytes only; no model/API calls, monetary or token claim',
        no_production_mutation=True, source_setters=0,
        prior_invalid_harness_run=(dict(path=str(EVIDENCE/'DEPLOYMENT_COST_RESULT.json'),
            reasons=['QA normal package import requires Pillow absent in Blender; use bounded empty-package QA template loader',
                     'full runtime identity has source_files list while initialize uses source_file_count; initial harness only accepted latter'],
            valid_product_cost_samples=0,no_overwrite=True) if output != EVIDENCE else None),
        prior_R2_tcp_harness_refusal=(dict(path=str(EVIDENCE/'DEPLOYMENT_COST_R2/DEPLOYMENT_COST_RESULT.json'),
            reason='observation_scope capture uses the exact _observation_code fixed read branch; QA initially checked only _code',
            valid_owned_pairs=8,valid_tcp_observations=0,new_run_tcp_only=True) if lanes=='tcp' else None))
    save(output / 'DEPLOYMENT_COST_PREREGISTRATION.json', contract)
    (output/'DEPLOYMENT_COST_HARNESS.py').write_bytes(Path(__file__).read_bytes())
    return contract


def load_fixed(arm):
    """Same bound bootstrap functions, before any engine import in this child."""
    _, site, entry = arm_paths(arm)
    spec = importlib.util.spec_from_file_location('_deployment_fixed_entry', entry)
    module = importlib.util.module_from_spec(spec)
    raw = entry.read_bytes()
    binding = json.loads(entry.with_name('RUNTIME_BINDING.json').read_text(encoding='utf8'))
    if digest(raw) != binding['launcher_sha256']:
        raise ValueError('launcher_changed')
    exec(compile(raw, str(entry), 'exec', dont_inherit=True), module.__dict__)
    proof = module.validate_binding(expected_python=sys.executable)
    sys.path.insert(0, str(site))
    module.verify_imported_runtime(proof)
    return module, proof


def snapshot(bpy):
    scene = bpy.context.scene
    raw = dict(frame=scene.frame_current, unit=scene.unit_settings.scale_length,
        objects=[dict(name=obj.name, vertices=[list(v.co) for v in obj.data.vertices],
                      faces=[list(f.vertices) for f in obj.data.polygons],
                      matrix=[list(row) for row in obj.matrix_world],
                      color=list(obj.color), selected=obj.select_get(),
                      hide_render=obj.hide_render, hide_viewport=obj.hide_viewport)
                 for obj in sorted(scene.objects, key=lambda obj: obj.name) if obj.type == 'MESH'])
    return digest(encode(raw))


def create_fixture(path):
    import bpy
    if path.exists() or not path.resolve().is_relative_to(EVIDENCE):
        raise ValueError('new_qa_fixture_only')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.
    signs = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
    faces = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(3,7,6),(3,6,2),(0,4,7),(0,7,3),(1,2,6),(1,6,5)]
    for name, size, z in [('GreyBase',(.2,.2,.2),0.), ('BluePart',(.1,.1,.1),.154)]:
        mesh = bpy.data.meshes.new(name + '_mesh')
        mesh.from_pydata([[s[k]*size[k]/2 for k in range(3)] for s in signs], [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        obj.location.z = z
        obj.color = (.04,.15,.8,1) if name == 'BluePart' else (.25,.25,.25,1)
        obj.select_set(name == 'BluePart')
        if name == 'BluePart':
            bpy.context.view_layer.objects.active = obj
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=True)


def qa_server(arm, folder):
    """Own process, loopback random port, fixed readonly code only, no setters."""
    import bpy
    if not bpy.app.background or tuple(bpy.app.version) != (5, 2, 1):
        raise ValueError('expected_headless_Blender_5_2_1')
    _, site, _ = arm_paths(arm)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(site))
    # Blender's environment intentionally has no Pillow. The addon executes
    # standalone fixed host templates, not the client facade package initializer.
    # Match that existing contract; this shim is solely the QA template verifier.
    package=types.ModuleType('human_eye_plugin')
    package.__path__=[str(site/'human_eye_plugin')]
    sys.modules['human_eye_plugin']=package
    from human_eye_plugin.blender_mcp_host import BlenderMCPHost, _READONLY_COMMANDS
    from human_eye_plugin.blender_host import BlenderSceneHost
    template = BlenderMCPHost(site, port=1)
    original = snapshot(bpy)
    renderer = BlenderSceneHost()._readonly_native_module()
    display_before = renderer.native_render_state(bpy, bpy.context.scene, bpy.context.view_layer)
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind(('127.0.0.1', 0))
    sock.listen(4)
    sock.settimeout(.1)
    port = sock.getsockname()[1]
    if port == 9876:
        raise ValueError('production_port_forbidden')
    save(folder/'READY.json', dict(port=port, pid=os.getpid(), scene_sha256=original,
                                   blender_version=list(bpy.app.version), readonly_templates=True))
    rows = []
    deadline = time.monotonic() + 300
    try:
        while not (folder/'STOP').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('qa_server_deadline')
            try:
                connection, _ = sock.accept()
            except socket.timeout:
                continue
            with connection:
                connection.settimeout(30)
                raw = bytearray()
                while True:
                    part = connection.recv(65536)
                    if not part:
                        raise ValueError('incomplete_read_request')
                    raw.extend(part)
                    if len(raw) > 32*1024:
                        raise ValueError('request_size')
                    try:
                        value = json.loads(raw)
                        break
                    except json.JSONDecodeError:
                        continue
                if set(value) != {'type','params'} or value['type'] != 'execute_code' or set(value['params']) != {'code'}:
                    raise ValueError('unadmitted_wire')
                code = value['params']['code']
                tree = ast.parse(code)
                assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and
                    isinstance(n.targets[0], ast.Name) and n.targets[0].id == '_request')
                request = json.loads(ast.literal_eval(assignment.value.args[0]))
                expected = [template._code(request['command'], request['params'], request['id'])]
                if request['command'] in {'capture','capture_evidence'}:
                    expected.append(template._observation_code(request['command'],request['params'],request['id']))
                if (request['command'] not in _READONLY_COMMANDS or code not in expected):
                    raise ValueError('unadmitted_fixed_readonly_template')
                if snapshot(bpy) != original:
                    raise ValueError('geometry_changed_before')
                output = io.StringIO()
                start = time.perf_counter_ns()
                with contextlib.redirect_stdout(output):
                    exec(compile(code, '<fixed-readonly-qa>', 'exec'), {'bpy': bpy})
                if (snapshot(bpy) != original or
                        renderer.native_render_state(bpy,bpy.context.scene,bpy.context.view_layer) != display_before):
                    raise ValueError('scene_or_display_mutation')
                result = dict(status='success', result=dict(executed=True,result=output.getvalue()))
                connection.sendall(encode(result))
                rows.append(dict(command=request['command'], elapsed_ns=time.perf_counter_ns()-start,
                                 original_deadline_ns=request['params'].get('deadline_ns'),
                                 geometry_unchanged=True, display_restored=True))
    finally:
        sock.close()
        save(folder/'SERVER_RESULT.json',dict(requests=rows, scene_unchanged=snapshot(bpy)==original,
            display_restored=renderer.native_render_state(bpy,bpy.context.scene,bpy.context.view_layer)==display_before,
            setters=0, source_saved=False))


def owned_child(arm, fixture, folder):
    starts = time.perf_counter_ns()
    bootstrap, proof = load_fixed(arm)
    imported = time.perf_counter_ns()
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.runtime_identity import runtime_identity
    validate_identity(runtime_identity(mode='live'), arm)
    host = None
    try:
        before_host = time.perf_counter_ns()
        host = BlenderProcessHost(BLENDER, fixture, timeout=30, startup_timeout=60)
        ready = time.perf_counter_ns()
        captured = host.capture_scene()
        capture_end = time.perf_counter_ns()
        save(folder/'OWNED_CAPTURE.json', captured)
        persisted = time.perf_counter_ns()
        second = host.capture_scene()
        if encode(captured) != encode(second):
            raise ValueError('owned_capture_changed')
        bootstrap.verify_imported_runtime(proof)
    finally:
        closing = time.perf_counter_ns()
        if host is not None:
            host.close()
    closed = time.perf_counter_ns()
    if host is None or host._process.poll() != 0:
        raise ValueError('owned_worker_not_cleanly_reaped')
    save(folder/'OWNED_RESULT.json', dict(status='passed', runtime_identity=runtime_identity(mode='live'),
        bootstrap_import_ns=imported-starts, worker_start_ns=ready-before_host,
        first_capture_ns=capture_end-ready, through_persist_ns=persisted-starts,
        close_ns=closed-closing, child_total_ns=closed-starts, process_reaped=True,
        original_timeout_s=30, original_startup_timeout_s=60, captures=2, geometry_unchanged=True, setters=0))


class JsonProcess:
    def __init__(self, command, cwd, folder):
        self.folder = folder
        self.started = time.perf_counter_ns()
        self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, creationflags=FLAGS)
        self.responses = queue.Queue()
        self.stderr = bytearray()
        self.stdout = bytearray()
        self.threads = []
        try:
            self.threads = [threading.Thread(target=self._read_stdout,daemon=True),
                            threading.Thread(target=self._read_stderr,daemon=True)]
            for thread in self.threads:
                thread.start()
        except BaseException:
            self.process.kill()
            self.process.wait(timeout=5)
            raise

    def _read_stdout(self):
        while True:
            value = self.process.stdout.readline(MAX_RESPONSE+1)
            if not value:
                self.responses.put(None)
                return
            self.stdout.extend(value)
            self.responses.put(value)

    def _read_stderr(self):
        while True:
            part = self.process.stderr.read(65536)
            if not part:
                return
            self.stderr.extend(part)

    def call(self, request):
        start = time.perf_counter_ns()
        self.process.stdin.write(encode(request)+b'\n')
        self.process.stdin.flush()
        raw = self.responses.get(timeout=60)
        arrived = time.perf_counter_ns()
        if raw is None or len(raw)>MAX_RESPONSE:
            raise ValueError('early_exit_or_response_size')
        value = strict_loads(raw)
        if value.get('id') != request['id'] or 'error' in value:
            raise ValueError('mcp_error_or_correlation')
        return value, raw, start, arrived

    def close(self):
        start = time.perf_counter_ns()
        try:
            self.process.stdin.close()
            self.process.wait(timeout=15)
        except BaseException:
            self.process.kill()
            self.process.wait(timeout=5)
            raise
        finally:
            for thread in self.threads:
                thread.join(timeout=3)
            for stream in (self.process.stdout,self.process.stderr):
                stream.close()
            (self.folder/'STDOUT.bin').write_bytes(self.stdout)
            (self.folder/'STDERR.bin').write_bytes(self.stderr)
        if self.process.returncode != 0:
            raise ValueError('mcp_exit_nonzero')
        return time.perf_counter_ns()-start


def tool_metadata(response):
    result = response['result']
    texts = [x['text'] for x in result.get('content',[]) if x.get('type')=='text']
    if len(texts) != 1:
        raise ValueError('one_text_metadata_required')
    return json.loads(texts[0]), result


def all_values(value):
    if isinstance(value,dict):
        for key,child in value.items():
            yield key,child
            if key == 'context_text' and isinstance(child,str):
                yield from all_values(json.loads(child))
            else:
                yield from all_values(child)
    elif isinstance(value,list):
        for child in value:
            yield from all_values(child)


def check_tool(response, arm, kind):
    metadata, result = tool_metadata(response)
    validate_identity(metadata.get('runtime_identity',{}), arm)
    if result.get('isError') is True:
        return 'refused', metadata
    if kind == 'status':
        if metadata.get('inflight_operation') or metadata.get('quarantined'):
            raise ValueError('unexpected_busy_or_quarantined')
        return 'passed', metadata
    if metadata.get('status') not in ('observed','partial'):
        return 'unknown', metadata
    gaps = [v for k,v in all_values(metadata) if k in ('signed_clearance_meters','signed_clearance_m')
            and type(v) in (int,float)]
    if not gaps or not any(abs(x-.004)<=1e-6 for x in gaps):
        raise ValueError('ordinary_4mm_not_measured')
    if kind in ('cold_native','hot_native'):
        visual = metadata.get('visual_delivery',{})
        images = [x for x in result.get('content',[]) if x.get('type')=='image']
        if visual.get('source') != 'blender_native_multiscale' or visual.get('status') != 'delivered' or not images:
            return 'unsupported_native_image', metadata
        for image in images:
            raw = base64.b64decode(image['data'],validate=True)
            if raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[16:24] != b'\x00\x00\x01\x80'*2:
                raise ValueError('invalid_native_384_png')
    return 'passed', metadata


def launch_server(arm, fixture, folder):
    stdout = (folder/'BLENDER_STDOUT.txt').open('wb')
    stderr = (folder/'BLENDER_STDERR.txt').open('wb')
    start = time.perf_counter_ns()
    command = [str(BLENDER),'--factory-startup','--disable-autoexec','--background',str(fixture),
               '--python',str(Path(__file__).resolve()),'--','qa-server','--arm',arm,'--output',str(folder)]
    process = None
    try:
        process = subprocess.Popen(command,stdout=stdout,stderr=stderr,creationflags=FLAGS)
        until = time.monotonic()+60
        while not (folder/'READY.json').exists():
            if process.poll() is not None or time.monotonic()>until:
                raise RuntimeError('qa_server_start_failed')
            time.sleep(.01)
        ready = json.loads((folder/'READY.json').read_text(encoding='utf8'))
        return process,stdout,stderr,ready,time.perf_counter_ns()-start
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        stdout.close()
        stderr.close()
        raise


def tcp_sample(arm, pair, fixture, folder):
    folder.mkdir()
    total_start = time.perf_counter_ns()
    server = None
    client = None
    rows = []
    outcome = {'arm':arm,'pair':pair,'lane':'default_fixed_entry_external_qa_tcp'}
    try:
        server,out,err,ready,server_start = launch_server(arm,fixture,folder)
        _,site,entry = arm_paths(arm)
        config = folder/'config.json'
        save(config,dict(schema_version='1.0',enabled=True,observe_on_prompt=True,project_root=str(site),
            state_file='state.json',audit_file='events.jsonl',quad_size=384,max_sessions=16,readback_atol_m=1e-6,
            blender=dict(host='127.0.0.1',port=ready['port'],timeout_s=10)))
        client = JsonProcess([str(PYTHON),'-I','-B',str(entry),'serve','--config',str(config)],site,folder)
        response,raw,start,arrived = client.call(dict(jsonrpc='2.0',id=1,method='initialize'))
        identity = response['result']['_meta']['human_eye']
        validate_identity(identity,arm)
        (folder/'INITIALIZE.json').write_bytes(raw)
        init_complete = time.perf_counter_ns()
        outcome['cold_service_complete_ns'] = init_complete-client.started
        requests = [('cold_native',0)] + [('hot_native',i) for i in range(HOT)] + \
            [('ordinary_gap_text',i) for i in range(HOT)] + [('status',i) for i in range(HOT)]
        image_stopped = False
        for index,(kind,repetition) in enumerate(requests,2):
            if image_stopped and kind == 'hot_native':
                rows.append(dict(kind=kind,repetition=repetition,status='not_run_after_native_refusal',registered=True))
                continue
            args = {} if kind == 'status' else dict(session_id='deployment-cost',
                task_instruction='Check the gap between BluePart and GreyBase; observe only, do not move.',
                focal_id=object_id('BluePart'),reference_id=object_id('GreyBase'),
                include_image=kind in ('cold_native','hot_native'))
            if kind in ('cold_native','hot_native'):
                args['query'] = {'native_visual':{'mode':'multiscale','view':'SCENE'}}
            request = dict(jsonrpc='2.0',id=index,method='tools/call',params=dict(
                name='human_eye_connection_status' if kind=='status' else 'human_eye_scene_observe',arguments=args))
            response,raw,start,arrived = client.call(request)
            status,metadata = check_tool(response,arm,kind)
            (folder/(str(index)+'_'+kind+'.json')).write_bytes(raw)
            complete = time.perf_counter_ns()
            rows.append(dict(kind=kind,repetition=repetition,status=status,rtt_ns=arrived-start,
                complete_ns=complete-start,response_bytes=len(raw),
                runtime_source_sha256=metadata['runtime_identity']['source_sha256'],
                runtime_source_count=identity_count(metadata['runtime_identity']),
                scene_revision=metadata.get('routing',{}).get('scene_revision'),
                visual_delivery=metadata.get('visual_delivery')))
            if kind == 'cold_native':
                outcome['cold_first_native_complete_ns'] = complete-client.started
            if kind in ('cold_native','hot_native') and status != 'passed':
                image_stopped = True
        outcome['service_close_ns'] = client.close()
        client = None
        # State/audit persistence is already inside calls; include verified publication.
        outcome['state_audit'] = {name:dict(bytes=(folder/name).stat().st_size,
            sha256=digest((folder/name).read_bytes())) for name in ('state.json','events.jsonl') if (folder/name).exists()}
        save(folder/'SERVICE_ACCOUNT.json',outcome['state_audit'])
        outcome['service_complete_cycle_ns'] = time.perf_counter_ns()-init_complete+outcome['cold_service_complete_ns']
        outcome.update(status='completed',external_blender_start_ns=server_start)
    except BaseException as exc:
        outcome.update(status='stopped',error=type(exc).__name__+':'+str(exc))
    finally:
        if client is not None:
            try:
                client.close()
            except BaseException as exc:
                outcome['close_error'] = type(exc).__name__+':'+str(exc)
        if server is not None:
            close_start = time.perf_counter_ns()
            (folder/'STOP').touch(exist_ok=False)
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            out.close()
            err.close()
            outcome['external_blender_close_ns'] = time.perf_counter_ns()-close_start
            outcome['external_blender_exit_code'] = server.returncode
            if server.returncode != 0:
                outcome['status'] = 'stopped'
            result_path = folder/'SERVER_RESULT.json'
            if result_path.exists():
                server_result = json.loads(result_path.read_text(encoding='utf8'))
                if not server_result.get('scene_unchanged') or not server_result.get('display_restored'):
                    outcome.update(status='stopped',error='scene_or_display_mutated')
                outcome['server_request_count'] = len(server_result['requests'])
            else:
                outcome.update(status='stopped',error='server_final_result_missing')
    outcome['full_qa_cycle_ns'] = time.perf_counter_ns()-total_start
    outcome['calls'] = rows
    save(folder/'RESULT.json',outcome)
    return outcome


def owned_sample(arm,pair,fixture,folder):
    folder.mkdir()
    start = time.perf_counter_ns()
    row = dict(arm=arm,pair=pair,lane='owned_fixed_file_worker')
    try:
        result = subprocess.run([str(PYTHON),'-I','-B',str(Path(__file__).resolve()),'owned-child',
            '--arm',arm,'--fixture',str(fixture),'--output',str(folder)],
            cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90,creationflags=FLAGS)
        (folder/'STDOUT.bin').write_bytes(result.stdout)
        (folder/'STDERR.bin').write_bytes(result.stderr)
        if result.returncode != 0:
            raise ValueError('owned_helper_exit:'+str(result.returncode))
        detail = json.loads((folder/'OWNED_RESULT.json').read_text(encoding='utf8'))
        validate_identity(detail['runtime_identity'],arm)
        row.update(status='passed',detail=detail)
    except BaseException as exc:
        row.update(status='stopped',error=type(exc).__name__+':'+str(exc))
    row['complete_cycle_ns'] = time.perf_counter_ns()-start
    save(folder/'RESULT.json',row)
    return row


def summarize(rows):
    metrics = {}
    for row in rows:
        if row['status'] not in ('completed','passed'):
            continue
        arm = row['arm']
        for key,value in row.items():
            if key.endswith('_ns') and type(value) is int:
                metrics.setdefault(row['lane']+'.'+key,{}).setdefault(arm,[]).append((row['pair'],value))
        for call in row.get('calls',[]):
            if call['status'] == 'passed':
                for field in ('rtt_ns','complete_ns'):
                    metrics.setdefault('call.'+call['kind']+'.'+field,{}).setdefault(arm,[]).append(
                        ((row['pair'],call['repetition']),call[field]))
    report = {}
    for key,arms in metrics.items():
        result = {}
        for arm,values in arms.items():
            samples = [v for _,v in values]
            result[arm] = dict(n=len(samples),median_ns=statistics.median(samples),p95_ns=nearest_rank(samples))
        if set(arms) == {'old','candidate'}:
            old,new = dict(arms['old']),dict(arms['candidate'])
            matched = sorted(set(old)&set(new))
            deltas = [new[i]-old[i] for i in matched]
            relative = [(new[i]/old[i]-1)*100 for i in matched]
            result['paired'] = dict(n=len(matched),delta_median_ns=statistics.median(deltas),
                delta_p95_ns=nearest_rank(deltas),relative_median_percent=statistics.median(relative),
                relative_p95_percent=nearest_rank(relative))
        report[key] = result
    return report


def run(output):
    contract = json.loads((output/'DEPLOYMENT_COST_PREREGISTRATION.json').read_text(encoding='utf8'))
    if contract['harness_sha256'] != digest(Path(__file__).read_bytes()):
        raise ValueError('harness_changed_since_registration')
    if (output/'DEPLOYMENT_COST_RUN_STARTED.json').exists():
        raise ValueError('no_resampling_or_overwrite')
    save(output/'DEPLOYMENT_COST_RUN_STARTED.json',dict(start_wall_ns=time.time_ns(),registration_sha256=digest(
        (output/'DEPLOYMENT_COST_PREREGISTRATION.json').read_bytes())))
    fixture = output/'DEPLOYMENT_COST_fixture.blend'
    creator = subprocess.run([str(BLENDER),'--factory-startup','--disable-autoexec','--background',
        '--python',str(Path(__file__).resolve()),'--','create-fixture','--fixture',str(fixture)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,creationflags=FLAGS)
    (output/'FIXTURE_CREATE_STDOUT.bin').write_bytes(creator.stdout)
    (output/'FIXTURE_CREATE_STDERR.bin').write_bytes(creator.stderr)
    if creator.returncode != 0 or not fixture.exists():
        raise ValueError('fixture_creation_failed')
    fixture_hash = digest(fixture.read_bytes())
    rows = []
    stopped = set()
    for pair in range(PAIRS):
        for arm in order(pair):
            for lane,runner in (('tcp',tcp_sample),('owned',owned_sample)):
                if contract['selected_lanes'] != 'both' and lane != contract['selected_lanes']:
                    continue
                if (arm,lane) in stopped:
                    rows.append(dict(arm=arm,pair=pair,lane=lane,status='not_run_after_stop',registered=True))
                    continue
                folder = output/(f'DEPLOYMENT_COST_{pair:02d}_{arm}_{lane}')
                row = runner(arm,pair,fixture,folder)
                rows.append(row)
                if row['status'] == 'stopped':
                    stopped.add((arm,lane))
                if digest(fixture.read_bytes()) != fixture_hash:
                    raise ValueError('immutable_qa_fixture_changed')
                print(json.dumps(dict(pair=pair,arm=arm,lane=lane,status=row['status'])),flush=True)
    result = dict(schema='deployment-complete-cost-result-v1',registration=contract,
        fixture_sha256=fixture_hash,rows=rows,metrics=summarize(rows),
        all_registered_rows=len(rows),source_setters=0,model_api_calls=0,
        gate='correctness_cost_disclosure_only_not_performance_qualification',
        old_M1_M2_failed_gates_unchanged=True,
        p95_warning='nearest rank; n=8 is the sample maximum; n=24 is second largest; no significance claim')
    save(output/'DEPLOYMENT_COST_RESULT.json',result)
    lines = ['# Fixed installed deployment cost disclosure','',
        'Fresh processes with retained OS caches. Eight paired AB/BA blocks; p95 is nearest rank. n=8 p95 is the maximum. This is correctness cost disclosure; old M1/M2 failures remain.', '',
        '| Metric | Old median / p95 ms (n) | Candidate median / p95 ms (n) | Paired median delta ms / % |',
        '| --- | ---: | ---: | ---: |']
    for metric,values in result['metrics'].items():
        def cell(arm):
            v=values.get(arm)
            return f"{v['median_ns']/1e6:.3f} / {v['p95_ns']/1e6:.3f} ({v['n']})" if v else 'unavailable'
        paired=values.get('paired')
        delta=f"{paired['delta_median_ns']/1e6:+.3f} / {paired['relative_median_percent']:+.2f}%" if paired else 'unmatched'
        lines.append(f'| {metric} | {cell("old")} | {cell("candidate")} | {delta} |')
    lines += ['', 'All registered attempts and refused/unknown outcomes remain in the JSON. TCP lane uses a bounded addon-compatible QA endpoint, not the real third-party addon. Owned worker and external fixture costs are separate domains. Archives retain original deadline metadata and exact response bytes. No model/API cost was measured.']
    (output/'DEPLOYMENT_COST_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')


def main():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['preregister','run','qa-server','owned-child','create-fixture'])
    parser.add_argument('--output',type=Path,default=EVIDENCE)
    parser.add_argument('--arm',choices=ARMS)
    parser.add_argument('--fixture',type=Path)
    parser.add_argument('--lanes',choices=['both','tcp','owned'],default='both')
    args=parser.parse_args(argv)
    if args.mode=='preregister':preregister(args.output.resolve(),args.lanes)
    elif args.mode=='run':run(args.output.resolve())
    elif args.mode=='qa-server':qa_server(args.arm,args.output.resolve())
    elif args.mode=='owned-child':owned_child(args.arm,args.fixture,args.output.resolve())
    else:create_fixture(args.fixture)


if __name__ == '__main__':
    main()
