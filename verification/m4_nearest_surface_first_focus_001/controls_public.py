"""Run installed production MCP in fresh stdio processes with sealed-source controls."""
import argparse
import base64
import copy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
BATCH = 'M4-NEAREST-SURFACE-FIRST-FOCUS-001'
ROOT = Path(os.environ['HE_NEAREST_FOCUS_ROOT']).resolve(strict=True)
OLD = ROOT.parent / 'M4-REFERENCE-ONLY-INTENT-HOLDOUT-001'
BASE_CUSTODY = ROOT.parent / 'M4-TASK-REGION-FOCUS-FEEDBACK-001/preflight/CANDIDATE_INSTALL_CUSTODY.json'
CONTRACT = 'human_eye_scene_observe'
RESULT = ROOT / 'preflight/CANDIDATE_CONTROLS.json'
OUT = ROOT / 'preflight/candidate-controls'
EXPECTED_COMMIT = 'b7fe4bb0dc2ce277ff5dd7a6198365253b716c09'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
LEGACY = ('auto', 'explicit', 'normal', 'boxed', 'reference_only')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_bytes())


def encode(value, *, canonical=False, ensure_ascii=True):
    return json.dumps(value, sort_keys=canonical, ensure_ascii=ensure_ascii, allow_nan=False,
                      separators=(',', ':')).encode('utf8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    path = Path(path).resolve(strict=True)
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}


def dump(path, value):
    with Path(path).open('xb') as stream:
        stream.write(encode(value) + b'\n')


def verified(pin_value):
    need(pin(pin_value['path']) == pin_value, 'frozen_input_changed')
    return Path(pin_value['path'])


def row_by_name(capture, name):
    return next(mesh for mesh in capture['meshes'] if mesh['name'] == name)


def changed(capture, suffix, *, replaced_instance=False, geometries=None):
    value = copy.deepcopy(capture)
    value['capture_state']['revision'] += suffix
    value['revision'] = sha((value['revision'] + '/offline-control/' + str(suffix)).encode())
    if replaced_instance:
        host_id = row_by_name(value, 'Fixture K')['object_id']
        new = 'offline-replacement-instance'
        value['host_identity']['object_instances'][host_id] = new
        next(row for row in value['display_snapshot']['objects'] if row['host_id'] == host_id)['instance_id'] = new
        display = value['display_snapshot']
        unsigned = {key: val for key, val in display.items() if key != 'sha256'}
        display['sha256'] = sha(encode(unsigned, canonical=True, ensure_ascii=False))
    if geometries:
        for name, (points, faces) in geometries.items():
            mesh = row_by_name(value, name)
            mesh['vertices'], mesh['faces'] = points, faces
            mesh['edges'] = [list(edge) for edge in sorted({tuple(sorted((a,b))) for face in faces
                             for a,b in zip(face, face[1:]+face[:1])})]
    return value


def source_controls(original):
    unversioned = {**changed(original, 10), 'capture_state': None}
    rational = changed(original, 11, geometries={
        'Part M': ([[0,0,0],[-1,0,0],[0,1,0]], [[0,1,2]]),
        'Fixture K': ([[1,-1,1],[2,1,1],[3,-1,1]], [[0,1,2]]),
    })
    equal = changed(original, 12, geometries={
        'Part M': ([[-2,-1,0],[-2,1,0],[-3,-1,0],[2,-1,0],[2,1,0],[3,-1,0]], [[0,1,2],[3,5,4]]),
        'Fixture K': ([[0,-1,1],[0,1,1],[0,0,2]], [[0,1,2]]),
    })
    return {'sealed': original, 'generation': changed(original, 1),
            'replacement': changed(original, 2, replaced_instance=True), 'unversioned': unversioned,
            'rational': rational, 'equal': equal, 'projection_only': changed(original, 13),
            'work_limit': changed(original, 14)}


def observation(focus, image=True):
    return {'query': {'mode': 'active_observation', 'objects': [{'name': 'Part M'}], 'focus': focus},
            'include_image': image, 'response_detail': 'full'}


def nearest(reference='Fixture K', *, image=True):
    return observation({'task_region': {'reference': {'name': reference}, 'relation': 'nearest_surface'}}, image)


def fixtures(candidate):
    box = {'min': [-5,-1,0], 'max': [-3,1,0]}
    normal = observation({'normal_world': [0,0,1]})
    legacy = [('auto', observation('auto')), ('explicit', observation({'source_triangle_index': 2})),
              ('normal', normal), ('boxed', observation({'task_region': {'reference': {'name': 'Fixture K'},
                                             'world_box_m': box}})),
              ('reference_only', observation({'task_region': {'reference': {'name': 'Fixture T'}}}))]
    if not candidate:
        return [(name, args, 'sealed') for name, args in legacy]
    extra = [('K-first', nearest(), 'sealed'), ('K-warm', nearest(), 'sealed'),
             ('T-first', nearest('Fixture T'), 'sealed'), ('new_generation', nearest(image=False), 'generation'),
             ('new_instance', nearest(image=False), 'replacement'), ('unversioned', nearest(), 'unversioned'),
             ('equal', nearest(image=False), 'equal'), ('rational', nearest(image=False), 'rational'),
             ('no_witness', nearest(), 'projection_only'), ('work_limit', nearest(), 'work_limit'),
             ('self_reference', nearest('Part M'), 'sealed')]
    mixed = nearest()
    mixed['query']['focus']['task_region']['world_box_m'] = box
    extra += [('mixed_box_relation', mixed, 'sealed'), ('after_rejections', nearest(image=False), 'sealed')]
    return [*[(name, args, 'sealed') for name, args in legacy], *extra]


class Meter:
    def __init__(self, folder, captures, schedule):
        self.folder, self.sources, self.schedule = folder, captures, schedule
        self.current = None
        self.events = []
        self.producers = {}

    def event(self, kind, **fields):
        self.events.append({'case': self.current, 'kind': kind, **fields, 'at_ns': time.perf_counter_ns()})

    def capture_scene(self):
        self.event('capture')
        return copy.deepcopy(self.sources[self.schedule[self.current]])

    def close(self):
        self.event('production_stdio_close')

    def install(self):
        from human_eye_plugin import active_observation_images, _surface_proximity_032, surface_proximity
        self.modules = (surface_proximity, _surface_proximity_032)
        self.default_work = {module: module.MAX_WORK_UNITS for module in self.modules}
        for module in self.modules:
            original = module._nearest
            module._nearest = self.search(original, module.__name__)
        original = surface_proximity.measure_surface_proximity

        def measured(*args, **kwargs):
            self.event('M3_measurement', retain_witness_triangles=kwargs.get('retain_witness_triangles'))
            result = original(*args, **kwargs)
            if self.current == 'no_witness':
                need(result['measurement_valid'] is True and result['witness_status'] == 'measured',
                     'no_witness_control_requires_real_measured_source')
                result = {key: val for key, val in result.items()
                          if key not in ('witness_triangle_indices', 'exact_witness_triangles')}
                result.update(witness_status='unknown', witness_reason='surface_witness_bit_budget')
                self.event('injected_output_provenance_unavailable')
            self.event('M3_return', reason=result.get('reason'), work=result.get('work'))
            return result

        surface_proximity.measure_surface_proximity = measured
        # Service initialization may have loaded task_query before this
        # instrumentator, so wire the exact already-imported alias as well.
        for name in ('human_eye_plugin.task_query', 'human_eye_plugin.source_region'):
            module = sys.modules.get(name)
            if module is not None and getattr(module, 'measure_surface_proximity', None) is original:
                module.measure_surface_proximity = measured
        raster = active_observation_images.rasterize_attention

        def rasterized(*args, **kwargs):
            self.event('software_raster')
            return raster(*args, **kwargs)

        active_observation_images.rasterize_attention = rasterized

    def search(self, original, module):
        def wrapped(*args, **kwargs):
            self.event('M3_actual_search', module=module)
            return original(*args, **kwargs)
        return wrapped

    def readline(self, size=-1):
        raw = sys.stdin.readline(size)
        if raw:
            self.current = json.loads(raw)['id']
            for module in self.modules:
                module.MAX_WORK_UNITS = 0 if self.current == 'work_limit' else self.default_work[module]
        return raw


def worker(folder, custody_path, input_path, candidate):
    custody = read(custody_path)
    site = Path(custody['installation']['path']).resolve(strict=True)
    sys.path.insert(0, str(site))
    captures = read(input_path)
    schedule = {name: source for name, _, source in fixtures(candidate)}
    meter = Meter(folder, captures, schedule)
    meter.install()
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import run_stdio_mcp_server
    from human_eye_plugin.runtime_identity import runtime_identity
    identity = runtime_identity()
    need(identity['source_kind'] == 'installed_distribution' and identity['source_sha256'] == custody['source_sha256']
         and identity['source_files'] == custody['source_manifest'], 'actual_installed_runtime_drift')
    config = folder / 'CONTROL_CONFIG.json'
    dump(config, {'schema_version': '1.0', 'enabled': True, 'project_root': str(folder),
                  'state_file': 'state.json', 'audit_file': 'audit.jsonl', 'request_budget_s': 30,
                  'expected_identity': {'source_sha256': identity['source_sha256']}})
    service = LiveSpatialService(config, host=meter, production_mode=True)
    service.close = meter.close
    original = service._observe_active_observation

    def observed(*args, **kwargs):
        value = original(*args, **kwargs)
        meter.producers[meter.current] = value
        return value

    service._observe_active_observation = observed
    try:
        run_stdio_mcp_server(service, input_stream=meter)
    finally:
        dump(folder/'PRODUCER.json', meter.producers)
        dump(folder/'COUNTS.json', meter.events)


def invoke(folder, custody_path, captures_path, candidate):
    folder.mkdir()
    protocol = [{'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {
                 'protocolVersion': '2025-03-26', 'capabilities': {},
                 'clientInfo': {'name': 'installed-controls', 'version': '1'}}},
                {'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list', 'params': {}}]
    protocol.extend({'jsonrpc': '2.0', 'id': name, 'method': 'tools/call',
                     'params': {'name': CONTRACT, 'arguments': args}} for name, args, _ in fixtures(candidate))
    data = b''.join(encode(row) + b'\n' for row in protocol)
    (folder/'TX.bin').write_bytes(data)
    command = [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), '--worker',
               str(folder), str(custody_path), str(captures_path), 'B' if candidate else 'A']
    started = time.perf_counter_ns()
    proc = subprocess.run(command, input=data, capture_output=True, cwd=folder, timeout=65, creationflags=NO_WINDOW)
    closed = time.perf_counter_ns()
    (folder/'RX.bin').write_bytes(proc.stdout)
    (folder/'STDERR.bin').write_bytes(proc.stderr)
    dump(folder/'PROCESS.json', {'command': command, 'exit_code': proc.returncode,
                                'started_ns': started, 'closed_ns': closed, 'EOF': True})
    need(proc.returncode == 0, 'production_stdio_failed/' + str(folder))
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    need([r['id'] for r in replies] == [r['id'] for r in protocol], 'complete_public_reply_inventory_required')
    events = read(folder/'COUNTS.json')
    need(sum(e['kind']=='production_stdio_close' for e in events) == 1, 'EOF_missing_production_close')
    return {r['id']: r for r in replies}, events, read(folder/'PRODUCER.json')


def get_body(reply, *, error=False):
    result = reply['result']
    blocks = result['content']
    need(result['isError'] is error and blocks and blocks[0]['type'] == 'text', 'unexpected_public_response')
    return json.loads(blocks[0]['text'])


def vector(row):
    return tuple(Fraction(v) for v in row)


def subtract(a, b):
    return tuple(x-y for x,y in zip(a,b))


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def cross(a,b):
    return tuple(a[(i+1)%3]*b[(i+2)%3] - a[(i+2)%3]*b[(i+1)%3] for i in range(3))


def on_triangle(point, points):
    a,b,c = points
    n = cross(subtract(b,a), subtract(c,a))
    if dot(n, subtract(point,a)) != 0 or not any(n):
        return False
    return all(dot(n, cross(subtract(q,p), subtract(point,p))) >= 0 for p,q in ((a,b),(b,c),(c,a)))


def validate_witness(body, capture, reference, allowed, exact_sq):
    focus = body['facts']['focus']
    result = focus['nearest_surface']
    w = result['witness']
    instances = capture['host_identity']['object_instances']
    ordered = [{'host_id': m['object_id'], 'instance_id': instances[m['object_id']],
                'vertices': m['vertices'], 'faces': m['faces']} for m in capture['meshes']]
    need(w['ordered_geometry_sha256'] == sha(encode(ordered, canonical=True))
         and w['scope'] == 'one_current_triangle_per_endpoint_non_exhaustive'
         and body['binding']['capture_state'] == capture['capture_state']
         and body['binding']['scene_revision'] == capture['revision'], 'result_not_bound_to_current_source')
    need(result['status'] == 'measured' and focus['primary_source_triangle_index'] == w['a']['source_triangle_index']
         and w['a']['source_triangle_index'] in allowed and focus['task_source_triangle_indices'] == [
             w['a']['source_triangle_index']], 'incorrect_primary_source_row')
    points, rows = [], []
    for side, name in (('a','Part M'), ('b',reference)):
        mesh = row_by_name(capture, name)
        point = vector(w[side]['point_m'])
        row = w[side]['source_triangle_index']
        expected_host = mesh['object_id']
        need(w[side]['host_id'] == expected_host and w[side]['instance_id'] == instances[expected_host]
             and type(row) is int and 0 <= row < len(mesh['faces'])
             and on_triangle(point, [vector(mesh['vertices'][i]) for i in mesh['faces'][row]]),
             'invalid_endpoint_source_membership')
        rows.append(row)
        points.append(point)
    delta = subtract(*points)
    rounded = math.sqrt(float(exact_sq))
    need(dot(delta,delta) == exact_sq and abs(result['distance_m'] - rounded) <= math.ulp(rounded),
         'wrong_exact_distance_or_point_pair')
    return {'rows': rows, 'points': [list(map(str, point)) for point in points],
            'distance_sq': str(exact_sq), 'encoding': w['point_encoding']}


def frame_assets(folder, reply, raw, case, capture):
    import numpy as np
    body = get_body(reply)
    frame, = raw['frames']
    image_path, npz_path = (Path(frame[k]).resolve(strict=True) for k in ('image_path', 'arrays_path'))
    need(image_path.is_relative_to(folder) and npz_path.is_relative_to(folder), 'frame_escaped_current_slot')
    images = [base64.b64decode(b['data'], validate=True) for b in reply['result']['content'] if b['type']=='image']
    need(images == [image_path.read_bytes()] and sha(images[0]) == frame['image_sha256']
         and sha(npz_path.read_bytes()) == frame['arrays_sha256'], 'frame_is_not_original_MCP_PNG_NPZ')
    sample = body['facts']['focus']['sample']
    need(sample['frame_identity'] == frame['frame_identity'] and sample['image_ref'] == frame['image_ref'],
         'sample_frame_ref_mismatch')
    if sample['selected_surface_pixels']:
        anchor = sample['sampled_pixel']
        y,x = anchor['row'],anchor['column']
        oid, = [i for i,m in enumerate(capture['meshes']) if m['name']=='Part M']
        with np.load(npz_path, allow_pickle=False) as data:
            local = int(data['triangle_ids'][y,x]) - int(data['face_patch_offsets'][oid])
            need(data['owners'][y,x] == oid and np.isfinite(data['depth'][y,x])
                 and local == anchor['source_triangle_index'], 'sample_not_in_original_NPZ/' + case)
    return {'PNG': pin(image_path), 'NPZ': pin(npz_path), 'frame_identity': frame['frame_identity'],
            'frame_view': frame['view_name']}


def validate(base, candidate, captures):
    a, ae, ap = base
    b, be, bp = candidate
    schemas = [next(t for t in arm['tools']['result']['tools'] if t['name']==CONTRACT) for arm in (a,b)]
    a_focus = schemas[0]['inputSchema']['properties']['query']['properties']['focus']
    b_focus = schemas[1]['inputSchema']['properties']['query']['properties']['focus']
    need(a_focus != b_focus and 'nearest_surface' in json.dumps(b_focus)
         and 'nearest_surface' not in json.dumps(a_focus), 'actual_new_registry_option_unproven')
    checks = {}
    for name in LEGACY:
        old,new = get_body(a[name]),get_body(b[name])
        need(all(old[k] == new[k] for k in ('facts','status','observation_status','read_only','execution_authority')),
             'legacy_public_fact_drift/' + name)
        before = frame_assets(OUT/'A', a[name], ap[name], name, captures['sealed'])
        after = frame_assets(OUT/'B', b[name], bp[name], name, captures['sealed'])
        need(all(before[k]['sha256'] == after[k]['sha256'] for k in ('PNG','NPZ')),
             'legacy_original_frame_drift/' + name)
        checks[name] = {'passed': True, 'legacy_same_facts': True, 'frames': [before,after]}
    expected = {
        'K-first': ('sealed','Fixture K',{0},Fraction(1,2)),
        'K-warm': ('sealed','Fixture K',{0},Fraction(1,2)),
        'T-first': ('sealed','Fixture T',{2,3},Fraction(11,16)),
        'new_generation': ('generation','Fixture K',{0},Fraction(1,2)),
        'new_instance': ('replacement','Fixture K',{0},Fraction(1,2)),
        'equal': ('equal','Fixture K',{0,1},Fraction(5)),
        'rational': ('rational','Fixture K',{0},Fraction(14,5)),
        'after_rejections': ('sealed','Fixture K',{0},Fraction(1,2)),
    }
    for name, (kind, ref, allowed, value) in expected.items():
        body = get_body(b[name])
        witness = validate_witness(body, captures[kind], ref, allowed, value)
        if name == 'rational':
            need(witness['encoding'] == 'rational_world_m'
                 and witness['points'] == [['0','0','0'],['6/5','-3/5','1']], 'rational_pair_not_exact')
        checks[name] = {'passed': True, 'witness': witness, 'work': body['work']}
        if name in ('K-first','K-warm','T-first'):
            checks[name]['frame'] = frame_assets(OUT/'B', b[name], bp[name], name, captures[kind])
            need(body['facts']['focus']['sample']['selected_surface_pixels'] >= 16,
                 'positive_control_below_16_pixels/' + name)
    for name, reason in [('unversioned','capture_generation_unavailable'),
                         ('no_witness','surface_witness_bit_budget'), ('work_limit','surface_work_budget')]:
        body = get_body(b[name])
        focus = body['facts']['focus']
        need(focus['nearest_surface'] == {'status':'unknown','reason':reason}
             and focus['primary_source_triangle_index'] is None and focus['region_ref'] is None
             and focus['sample'] is None and not body['frames'] and body['status'] == 'unknown',
             'fail_closed_control/' + name)
        checks[name] = {'passed': True, 'reason': reason, 'work': body['work']}
    for name, text in [('self_reference','focus_task_region_distinct_reference_required'),
                       ('mixed_box_relation','world_box_m')]:
        body = get_body(b[name], error=True)
        need(text in body['error'], 'wrong_rejection_reason/' + name)
        checks[name] = {'passed': True, 'error': body['error']}
    measured = ('K-first','T-first','new_generation','new_instance','equal','rational','no_witness')
    for name in checks:
        counts = {key:sum(event['case'] == name and event['kind'] == key for event in be)
                  for key in ('capture','M3_measurement','M3_actual_search','software_raster')}
        checks[name]['actual'] = counts
        if name in measured:
            need(counts['M3_measurement'] == counts['M3_actual_search'] == 1, 'wrong_real_search_count/' + name)
        if name in (*LEGACY,'K-warm','unversioned','self_reference','mixed_box_relation'):
            need(not counts['M3_measurement'] and not counts['M3_actual_search'], 'unexpected_M3_search/' + name)
        if name not in (*LEGACY,'K-first','T-first'):
            need(not counts['software_raster'], 'unexpected_software_raster/' + name)
    need(checks['K-first']['frame']['frame_identity'] == checks['K-warm']['frame']['frame_identity'],
         'warm_original_frame_not_reused')
    need(checks['work_limit']['actual']['M3_measurement'] == 1, 'work_limit_did_not_reach_M3')
    need(sum(e['kind']=='injected_output_provenance_unavailable' for e in be) == 1, 'non_vacuous_witness_negative')
    return checks, len(ae), len(be)


def run(custody_path):
    need(read(ROOT/'preflight/PHASE1_ACCEPTANCE.json')['passed'] is True, 'unaccepted_phase1')
    base, candidate = read(BASE_CUSTODY), read(custody_path)
    need(base['candidate_commit'] == EXPECTED_COMMIT and candidate['candidate_commit'] != EXPECTED_COMMIT,
         'wrong_control_installed_versions')
    source = OLD/'slots/DIAGNOSTIC/post_capture.json'
    admission = read(ROOT/'preflight/registration/REGISTRATION_FREEZE.json')
    pin_source = admission['old_custody']['members']['slots/DIAGNOSTIC/post_capture.json']
    need(pin(source) == pin_source, 'old_scene_outside_sealed_source')
    OUT.mkdir()
    captures = source_controls(read(source))
    captures_path = OUT/'CAPTURES.json'
    dump(captures_path, captures)
    a = invoke(OUT/'A', BASE_CUSTODY, captures_path, False)
    b = invoke(OUT/'B', custody_path, captures_path, True)
    checks, ae, be = validate(a,b,captures)
    dump(RESULT, {'batch': BATCH, 'passed': True, 'old_sealed_capture': pin_source,
                  'candidate': pin(custody_path), 'baseline': pin(BASE_CUSTODY), 'controls_script': pin(__file__),
                  'fixture': pin(captures_path), 'checks': checks, 'checks_passed': len(checks),
                  'active_requests': {'A': len(fixtures(False)), 'B': len(fixtures(True))},
                  'software_rasters': {'A':sum(x['kind']=='software_raster' for x in a[1]),
                                       'B':sum(x['kind']=='software_raster' for x in b[1])},
                  'zero_model_or_Blender': True, 'event_counts': {'A':ae,'B':be},
                  'scope': {'unavailable_witness':'real M3 solve with published provenance removed in fixture',
                            'work_bound':'actual M3 work allowance set to zero in fixture; default unchanged'},
                  'receipts': [pin(OUT/arm/name) for arm in ('A','B') for name in
                               ('TX.bin','RX.bin','STDERR.bin','PROCESS.json','PRODUCER.json','COUNTS.json')]})


if __name__ == '__main__':
    need(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_interpreter_required')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', nargs=4)
    parser.add_argument('custody', nargs='?', type=Path, default=ROOT/'preflight/INSTALL_CUSTODY.json')
    args = parser.parse_args()
    if args.worker:
        f,p,s,arm = args.worker
        worker(Path(f),Path(p),Path(s),arm=='B')
    else:
        run(args.custody)
