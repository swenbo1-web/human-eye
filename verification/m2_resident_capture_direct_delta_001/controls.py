"""Verify and time the installed resident dispatch on sealed real capture inputs."""

import argparse
import ast
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
import gc
from io import StringIO
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from threading import Thread
from time import perf_counter_ns
from types import SimpleNamespace
import zipfile


HISTORY = Path('D:/he_m2_source_region_shared_normalization_live_001')
SEALED_SHA = '534a0d0a584a0c29544d11acac1475dfa30adb952f8bb0215944c92253506960'
BASELINE_GIT = 'ee385e9842b9ea413f9d63dea6b74e88c8a051da'
PREFIX = 'HUMAN_EYE_BLENDER_MCP:'
GEOMETRY = ('vertices', 'faces', 'edges')
RESOURCE_COUNTS = (27312, 53276, 80453)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def stable(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('ascii')


def digest(data):
    return sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def fingerprint(value):
    if 'live_resources' in value:
        value = {**value, 'live_resources': sorted(value['live_resources'])}
    return digest(stable(value))


def fixture_packets():
    index = read(HISTORY/'sealed/RAW_INDEX.json')
    archive = HISTORY/'sealed/ORIGINAL_RUNTIME.zip'
    require(digest(archive.read_bytes()) == index['archive']['sha256'] == SEALED_SHA, 'old_closed_archive_changed')
    sources = {}
    packets = []
    with zipfile.ZipFile(archive) as bundle:
        for sequence in ('002', '003'):
            paths = [f'slots/B/native/WIRE/{sequence}/{kind}.bin' for kind in ('REQUEST', 'RESPONSE')]
            data = []
            for path in paths:
                original = bundle.read(path)
                bind = {'bytes': len(original), 'sha256': digest(original)}
                require(bind == index['members'][path] and original == (HISTORY/path).read_bytes(),
                        'wire_member_does_not_match_closed_slot/' + path)
                sources[path] = bind
                data.append(json.loads(original))
            request, response = data
            tree = ast.parse(request['params']['code'])
            assignment, = [row for row in tree.body if isinstance(row, ast.Assign)
                           and isinstance(row.targets[0], ast.Name) and row.targets[0].id == '_request']
            command = json.loads(ast.literal_eval(assignment.value.args[0]))
            output = response['result']['result']
            require(output.startswith(PREFIX) and output.endswith('\n'), 'old_native_envelope_invalid')
            envelope = json.loads(output[len(PREFIX):])
            require(command['id'] == envelope['id'] and command['command'] == 'capture' and command['params'] == {}
                    and request['type'] == 'execute_code' and response['status'] == 'success'
                    and envelope['protocol_version'] == '1.0', 'old_native_capture_not_bound_to_request')
            packets.append(envelope['result'])
    cold, warm = packets
    require(len(cold['resources']) == 2 and not warm['resources'] and cold['capture'] == warm['capture']
            and sorted(cold['live_resources']) == sorted(warm['live_resources']), 'old_scene_not_a_cold_to_warm_pair')
    return cold, warm, sources


class ResidentFixture:
    """Replace only Blender acquisition and the socket in this offline runner."""

    def __init__(self, install, connector_type, decoder_type, cold):
        self.connector = connector_type(install)
        self.connector._exchange = self.exchange
        self.decoder_type = decoder_type
        self.cold = cold
        self.host = self.scene = self.packet = self.sample = None
        self.enabled = True
        self.fail_capture = False
        self.samples = []
        self.history_scene = decoder_type().apply(cold)
        self.scope = {'bpy': SimpleNamespace(context=SimpleNamespace(scene=object(), view_layer=object()),
                                           app=SimpleNamespace(handlers=SimpleNamespace(depsgraph_update_post=[]))),
                      '_offline_attach_fixture': self.attach}

    def attach(self, host):
        self.host = host
        host._capture = self.capture
        encode = host.capture_delta

        def timed_encode(capture, known=None):
            started = perf_counter_ns()
            output = encode(capture, known)
            closed = perf_counter_ns()
            if self.sample is not None:
                input_meshes = capture['meshes']
                actual = {row['object_id']: row for row in self.scene['meshes']}
                self.sample.update(encode_started_ns=started, encode_closed_ns=closed,
                                   copy_encode_ns=closed-self.sample['capture_return_ns'],
                                   encode_ns=closed-started,
                                   copied_geometry_buffers=sum(row[key] is not actual[row['object_id']][key]
                                                               for row in input_meshes for key in GEOMETRY),
                                   encoded_under_host_lock=host._lock._is_owned())
                self.samples.append(self.sample)
            return output

        host.capture_delta = timed_encode
        self.load(self.cold)

    def load(self, packet):
        """Restore the exact world geometry and wire bindings from a full capture."""
        self.scene = self.decoder_type().apply(packet)
        token = self.scene.pop('capture_state')
        state = self.host._residency
        state.instance_id, state.epoch, state.revision = (token[k] for k in ('instance_id', 'epoch', 'revision'))
        resources = {row['id']: {'resource_id': row['id'], 'revision': row['revision'],
                     **{k: tuple(map(tuple, row[k])) for k in ('vertices_local', 'faces', 'edges')}} for row in packet['resources']}
        state.wire = {}
        for mesh in packet['capture']['meshes']:
            ref = mesh['_scene_resource']
            state.wire[mesh['object_id']] = (resources[ref['id']], deepcopy(ref['matrix']), ref['scale'])
        state.enabled = self.enabled

    def capture(self, *, _resident=False, _task_selectors=None):
        require(_resident and self.host._lock._is_owned(), 'capture_left_real_host_lock')
        if self.fail_capture:
            raise ValueError('offline_fixture_capture_exception')
        scene = self.scene
        if _task_selectors is not None:
            name, = [_task_selectors[0]['name']]
            scene = {**scene, 'meshes': [row for row in scene['meshes'] if row['name'] == name]}
        if self.sample is not None:
            self.sample['capture_return_ns'] = perf_counter_ns()
        return scene

    def exchange(self, request):
        parsed = json.loads(request)
        require(parsed['type'] == 'execute_code', 'actual_connector_not_execute_code')
        code = parsed['params']['code']
        if not self.connector._resident_ready:
            # The owned Blender normally fills `_capture` following bootstrap.
            # Install only fixture acquisition after the real cold setup.
            anchor = '    _host = _module._mcp_resident_host\n'
            require(code.count(anchor) == 1, 'generated_host_fixture_anchor')
            code = code.replace(anchor, anchor + '    _offline_attach_fixture(_host)\n')
        self.scope.pop('_result', None)
        with redirect_stdout(StringIO()) as stream:
            exec(compile(code, '<actual-installed-capture-dispatch>', 'exec'), self.scope)
        self.packet = self.scope.get('_result')
        return {'status': 'success', 'result': {'executed': True, 'result': stream.getvalue()}}

    def capture_scene(self, known=...):
        decoder = self.connector._scene_decoder
        if known is ...:
            return self.connector.capture_scene()
        decoder.baseline = lambda: known
        try:
            return self.connector.capture_scene()
        finally:
            del decoder.baseline

    def operation(self, scenario, *, known=..., expect=None):
        output = self.capture_scene(known)
        packet = self.packet
        resources = len(packet['resources']) if 'resources' in packet else None
        require(resources == expect, 'unexpected_live_delta_resource_count/' + scenario)
        if 'capture' in packet:
            require(output.get('capture_state') == packet['capture']['capture_state'], 'capture_token_not_preserved')
        return {'encoded_sha256': fingerprint(packet), 'decoded_sha256': fingerprint(output), 'resources': resources}

    def timed_capture(self, arm, expected):
        self.sample = {}
        try:
            actual = self.operation('timed_warm', expect=0)
            require(actual == expected, 'timed_warm_response_changed')
            sample = self.samples[-1]
            require(sample['copied_geometry_buffers'] == (6 if arm == 'A' else 0)
                    and sample['encoded_under_host_lock'] is (arm == 'B'), 'wrong_geometry_copy_or_lock_path')
            return sample
        finally:
            self.sample = None


def verify_controls(fixture, arm, cold, warm, decoder_type, remote_error):
    rows = {}
    rows['actual_cold'] = fixture.operation('actual_cold', expect=2)
    require(rows['actual_cold']['encoded_sha256'] == fingerprint(cold), 'real_cold_content_not_preserved')
    cold_scene = fingerprint(fixture.history_scene)
    require(rows['actual_cold']['decoded_sha256'] == cold_scene and
            tuple(sum(len(mesh[k]) for mesh in fixture.scene['meshes']) for k in GEOMETRY) == RESOURCE_COUNTS,
            'real_decoded_geometry_not_preserved')
    # Check the encoder's pre-JSON packet as well as the RPC caller result.
    fixture.packet['capture']['meshes'][0]['local_axes'][0][0] = -112.0
    fixture.packet['capture']['capture_state']['epoch'] = -1
    require(fixture.operation('cold_packet_ownership', expect=0)['encoded_sha256'] == fingerprint(warm),
            'producer_packet_mutation_leaked_to_host')
    rows['actual_warm'] = fixture.operation('actual_warm', expect=0)
    require(rows['actual_warm']['encoded_sha256'] == fingerprint(warm)
            and rows['actual_warm']['decoded_sha256'] == cold_scene, 'real_delta_content_not_preserved')
    output = fixture.capture_scene()
    output['meshes'][0]['vertices'][0][0] = -112.0
    output['display_snapshot']['status'] = 'wrong'
    require(fixture.operation('public_rpc_ownership', expect=0) == rows['actual_warm'], 'caller_result_mutated_host')
    public = fixture.host.capture_scene()
    require(fingerprint(public) == cold_scene and public['meshes'][0]['faces'] is not fixture.scene['meshes'][0]['faces'],
            'public_capture_copy_not_preserved')
    public['meshes'][0]['faces'][0][0] = -1
    require(fingerprint(fixture.host.capture_scene()) == cold_scene, 'public_capture_mutation_leaked')
    rows['public_capture_is_independent'] = True

    known = fixture.connector._scene_decoder.baseline()
    rows['no_client_baseline'] = fixture.operation('no_client_baseline', known=None, expect=2)
    rows['wrong_client_instance'] = fixture.operation('wrong_client_instance', known={**known, 'instance_id': 'other'}, expect=2)
    rows['wrong_client_epoch'] = fixture.operation('wrong_client_epoch', known={**known, 'epoch': known['epoch'] + 1}, expect=2)
    stale = dict(known['resources'])
    stale.pop(next(iter(stale)))
    rows['partial_client_baseline'] = fixture.operation('partial_client_baseline', known={**known, 'resources': stale}, expect=1)
    rows['missing_then_recovered'] = fixture.operation('missing_then_recovered', expect=0)

    # Changed real capture rows, with correct current resource bindings intact.
    changed = deepcopy(cold)
    changed['capture']['capture_state']['revision'] += 1
    changed['capture']['revision'] = 'blender:' + digest(b'geometry control')
    changed['resources'][1]['revision'] += 1
    changed['resources'][1]['vertices_local'][0][0] += .125
    changed['capture']['meshes'][1]['_scene_resource']['revision'] += 1
    fixture.load(changed)
    rows['geometry_revision'] = fixture.operation('geometry_revision', expect=1)
    require(rows['geometry_revision']['decoded_sha256'] == fingerprint(decoder_type().apply(changed)), 'changed_geometry_not_used')
    posed = deepcopy(changed)
    posed['capture']['capture_state']['revision'] += 1
    posed['capture']['revision'] = 'blender:' + digest(b'pose control')
    posed['capture']['meshes'][1]['_scene_resource']['matrix'][0][3] += .125
    fixture.load(posed)
    rows['pose_refresh'] = fixture.operation('pose_refresh', expect=0)
    require(rows['pose_refresh']['decoded_sha256'] == fingerprint(decoder_type().apply(posed)), 'changed_pose_not_used')
    shown = deepcopy(posed)
    display = shown['capture']['display_snapshot']
    display['view_layer']['instance_id'] = 'rna:987654321'
    display['sha256'] = digest(stable({k: v for k, v in display.items() if k != 'sha256'}))
    fixture.load(shown)
    rows['display_refresh'] = fixture.operation('display_refresh', expect=0)
    require(rows['display_refresh']['decoded_sha256'] == fingerprint(decoder_type().apply(shown)), 'current_display_not_used')
    new = deepcopy(shown)
    new['capture']['capture_state']['epoch'] += 1
    fixture.load(new)
    rows['new_epoch'] = fixture.operation('new_epoch', expect=2)

    state = fixture.host._residency
    oid = next(iter(state.wire))
    saved = state.wire.pop(oid)
    rows['missing_host_binding'] = fixture.operation('missing_host_binding', expect=None)
    require(rows['missing_host_binding']['decoded_sha256'] == fingerprint(fixture.host.capture_scene()),
            'missing_binding_fallback_not_public_shape')
    fixture.packet['meshes'][0]['vertices'][0][0] = -112.0
    require(rows['missing_host_binding']['decoded_sha256'] == fingerprint(fixture.host.capture_scene()),
            'missing_binding_fallback_not_detached')
    state.wire[oid] = saved
    rows['binding_restored'] = fixture.operation('binding_restored', expect=2)

    # Public fallback remains independent even without residency or current token.
    fixture.host._residency = None
    rows['no_host_residency'] = fixture.operation('no_host_residency', expect=None)
    fixture.packet['meshes'][0]['faces'][0][0] = -1
    require(rows['no_host_residency']['decoded_sha256'] == fingerprint(fixture.host.capture_scene()), 'absent_resident_fallback_alias')
    fixture.host._residency = state
    state.enabled = False
    rows['disabled_host_residency'] = fixture.operation('disabled_host_residency', expect=None)
    fixture.packet['meshes'][0]['vertices'][0][0] = -112.0
    require(rows['disabled_host_residency']['decoded_sha256'] == fingerprint(fixture.host.capture_scene()), 'disabled_resident_fallback_alias')
    state.enabled = True
    old = fixture.host.capture_scene()
    old['capture_state']['revision'] += 1
    detached = fixture.host.capture_delta(old, fixture.connector._scene_decoder.baseline())
    require(detached == old and detached['meshes'][0]['edges'] is not old['meshes'][0]['edges'], 'stale_token_fallback')
    rows['stale_token_fallback'] = True

    fixture.fail_capture = True
    baseline = fixture.connector._scene_decoder.baseline()
    try:
        fixture.capture_scene()
    except remote_error as exc:
        require('offline_fixture_capture_exception' in str(exc) and fixture.connector.is_alive
                and fixture.connector._scene_decoder.baseline() == baseline, 'capture_exception_changed_connector_state')
    else:
        raise ValueError('expected_read_only_capture_error')
    finally:
        fixture.fail_capture = False
    rows['read_only_exception_then_recovery'] = fixture.operation('read_only_exception_then_recovery', expect=2)

    decoder = decoder_type()
    malformed = {**cold, 'resources': cold['resources'][:1]}
    try:
        decoder.apply(malformed)
    except ValueError as exc:
        require(str(exc) == 'scene_delta_missing_resource' and decoder.baseline() is None, 'failed_decode_published_partial_result')
    else:
        raise ValueError('partial_delta_without_baseline_unexpectedly_accepted')
    require(fingerprint(decoder.apply(cold)) == fingerprint(decoder.apply(warm)) == cold_scene, 'clean_decoder_recovery_changed')
    rows['incomplete_decoder_reject_and_recovers'] = True

    captured = []
    def off_main():
        try:
            call = fixture.host.capture_scene if arm == 'A' else fixture.host._capture_scene_delta
            call()
        except ValueError as error:
            captured.append(str(error))
    thread = Thread(target=off_main)
    thread.start()
    thread.join()
    require(captured == ['Blender host operations require the main thread'], 'main_thread_contract_changed')
    rows['main_thread_guard'] = True

    task = fixture.connector.capture_task_scene([{'name': 'Cube'}])
    require([mesh['name'] for mesh in task['meshes']] == ['Cube'] and task['capture_state']['selection_key'] !=
            new['capture']['capture_state']['selection_key'], 'ordinary_selected_task_dispatch_changed')
    rows['ordinary_selected_task'] = fingerprint(task)
    fixture.load(cold)
    fixture.operation('reset_to_warm_timings', known=None, expect=2)
    require(fixture.operation('before_samples', expect=0) == rows['actual_warm'], 'timing_input_not_original_hot')
    return rows


def worker(binding_path, arm):
    binding = read(binding_path)
    install = Path(binding['install_root']).resolve(strict=True)
    sys.path[:0] = [str(install), binding['dependency_root']]
    from human_eye_plugin import blender_host, blender_mcp_host, scene_residency

    manifest = {row['path']: row['sha256'] for row in binding['source_manifest']}
    consumed = {}
    for module in (blender_host, blender_mcp_host, scene_residency):
        path = Path(module.__file__).resolve(strict=True)
        rel = path.relative_to(install).as_posix()
        checksum = digest(path.read_bytes())
        require(checksum == manifest[rel], 'actual_installed_file_not_manifest_bound/' + rel)
        consumed[rel] = checksum
    require((binding['preparation_git'] == BASELINE_GIT) is (arm == 'A')
            and hasattr(blender_host.BlenderSceneHost, '_capture_scene_delta') is (arm == 'B'), 'wrong_isolated_arm')

    cold, warm, sources = fixture_packets()
    fixture = ResidentFixture(install, blender_mcp_host.BlenderMCPHost, scene_residency.SceneDeltaDecoder, cold)
    cases = verify_controls(fixture, arm, cold, warm, scene_residency.SceneDeltaDecoder, blender_mcp_host.HostRemoteError)
    gc_before = {'enabled': gc.isenabled(), 'thresholds': list(gc.get_threshold())}
    require(gc_before['enabled'], 'normal_GC_required')
    events, active = [], {}

    def observe(phase, info):
        start = active.get(info['generation'])
        if phase == 'start':
            active[info['generation']] = perf_counter_ns()
        elif start is not None:
            events.append({'generation': info['generation'], 'started_ns': start, 'closed_ns': perf_counter_ns()})
            del active[info['generation']]

    print(json.dumps({'cases': cases, 'source_sha256': binding['source_sha256'], 'commit': binding['preparation_git'],
                      'consumed': consumed, 'prior_seal': SEALED_SHA, 'prior_wire': sources, 'gc': gc_before}), flush=True)
    gc.callbacks.append(observe)
    try:
        for line in sys.stdin:
            require(line.strip() == 'sample', 'unknown_offline_sample_command')
            sample = fixture.timed_capture(arm, cases['actual_warm'])
            sample['GC_in_copy_and_encode'] = [event for event in events if
                                              sample['capture_return_ns'] < event['closed_ns'] and
                                              sample['encode_closed_ns'] > event['started_ns']]
            events.clear()
            print(json.dumps(sample), flush=True)
    finally:
        gc.callbacks.remove(observe)
    require(gc_before == {'enabled': gc.isenabled(), 'thresholds': list(gc.get_threshold())}, 'GC_settings_changed')


def experiment(options):
    options.output.mkdir(parents=True, exist_ok=False)
    arms = {}
    with (options.output/'worker_stderr.bin').open('xb') as stderr:
        try:
            for arm, binding in (('A', options.baseline), ('B', options.candidate)):
                arms[arm] = subprocess.Popen([sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()),
                                             '--worker', arm, '--binding', str(binding.resolve(strict=True))],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True, encoding='utf8')
            receipts = {arm: json.loads(proc.stdout.readline()) for arm, proc in arms.items()}
            require(receipts['A']['cases'] == receipts['B']['cases'] and receipts['A']['gc'] == receipts['B']['gc']
                    and receipts['A']['prior_wire'] == receipts['B']['prior_wire'], 'isolated_AB_contract_difference')
            schedule = list('ABBA' * 4)
            samples = {'A': [], 'B': []}
            for arm in schedule:
                proc = arms[arm]
                proc.stdin.write('sample\n')
                proc.stdin.flush()
                samples[arm].append(json.loads(proc.stdout.readline()))
        finally:
            for proc in arms.values():
                proc.stdin.close()
            for proc in arms.values():
                proc.stdout.close()
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    require(all(proc.returncode == 0 for proc in arms.values()), 'offline_workers_not_closed')
    middle = {arm: median(row['copy_encode_ns'] for row in values) for arm, values in samples.items()}
    reduction = 1 - middle['B']/middle['A']
    report = {'passed': reduction >= .80, 'cases_per_arm': len(receipts['A']['cases']), 'arms': receipts,
              'schedule': schedule, 'samples': samples, 'copy_encode_medians_ns': middle,
              'paired_gate_minimum_reduction': .80, 'reduction': reduction, 'Blender': 0, 'models': 0,
              'timing_scope': 'actual generated capture from fixture acquisition return through original delta encode; '
                              'timer excludes JSON transport and decoder, warm GC stays enabled'}
    with (options.output/'RESULT.json').open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=True)
        stream.write('\n')
    require(report['passed'], 'offline_copy_encode_timing_gate_failed')


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_flags')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--worker', choices=('A', 'B'))
    for option in ('binding', 'baseline', 'candidate', 'output'):
        cli.add_argument('--' + option, type=Path)
    opts = cli.parse_args()
    if opts.worker:
        worker(opts.binding, opts.worker)
    else:
        experiment(opts)
