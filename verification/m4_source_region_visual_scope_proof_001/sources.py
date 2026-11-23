"""Recover exact original image-bearing source captures from sealed runs."""

import ast
import base64
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SLOT = 'slots/P1'
PRE = 'preflight/product'
ASSEMBLY = 'm4_assembly_cross_asset_product_native_001'
RAIL = 'm4_rail_source_region_product_native_001'
ASSEMBLY_COMMIT = '4bc6b7d6da32a4204f57465f4311723e0836faff'
RAIL_COMMIT = 'a374e3dcde0334991a63c15d594604c068b0b614'
HISTORY = Path('D:/he_m4_cross_scale_assembly_transfer_001')
HISTORY_COMMIT = '39fd39cdad162bbe7e5eb68243881d39bb67d285'
PREFIX = 'HUMAN_EYE_BLENDER_MCP:'
VIEWS = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(data):
    return {'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def pinned_json(commit, name):
    return subprocess.check_output(('git', 'show', f'{commit}:verification/{name}'), cwd=REPO)


class SealedRun:
    """Check the Git–bound archive once and bind each used member to loose bytes."""

    def __init__(self, name, commit):
        self.root = Path('D:/he_' + name).resolve(strict=True)
        self.commit = commit
        result = pinned_json(commit, name + '/RESULT.json')
        self.result = json.loads(result)
        self.commit_result = digest(result)
        if 'raw_archive' in self.result:
            published = self.result['raw_archive']
            self.archive_pin = published['archive']
            count = published['member_count']
        else:
            published = self.result['raw_local_archive']
            self.archive_pin = {k: published[k] for k in ('bytes', 'path', 'sha256')}
            count = published['members']
        self.index_path = self.root / 'sealed/RAW_INDEX.json'
        index_bytes = self.index_path.read_bytes()
        self.index_pin = {'path': str(self.index_path), **digest(index_bytes)}
        if 'index' in published:
            require(self.index_pin == published['index'], 'historical_local_index_changed')
        index = json.loads(index_bytes)
        path = self.root / 'sealed/ORIGINAL_RUNTIME.zip'
        require(Path(self.archive_pin['path']) == path and index['archive'] == self.archive_pin
                and digest(path.read_bytes()) == {k: self.archive_pin[k] for k in ('bytes', 'sha256')},
                'historical_runtime_archive_changed')
        self.members = index['members']
        self.used = {}
        self.zip = ZipFile(path)
        try:
            require(len(self.zip.namelist()) == count == index['member_count'] == len(self.members)
                    and set(self.zip.namelist()) == set(self.members),
                    'historical_runtime_archive_members_changed')
        except BaseException:
            self.zip.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.zip.close()

    def take(self, name):
        path = Path(name)
        path = path if path.is_absolute() else self.root / path
        actual = path.resolve(strict=True)
        require(path == actual and actual.is_relative_to(self.root), 'archive_source_scope_changed')
        name = actual.relative_to(self.root).as_posix()
        data = actual.read_bytes()
        observed = digest(data)
        require(observed == self.members[name] and data == self.zip.read(name),
                'sealed_source_member_changed/' + name)
        self.used[name] = observed
        return data

    def json(self, name):
        return json.loads(self.take(name))

    def check_pin(self, record):
        data = self.take(record['path'])
        observed = digest(data)
        require(observed['sha256'] == record['sha256']
                and ('bytes' not in record or observed['bytes'] == record['bytes']),
                'historical_file_pin_changed/' + record['path'])
        return data

    def proof(self):
        return {'evidence_commit': self.commit, 'committed_result': self.commit_result,
                'archive': self.archive_pin, 'raw_index': self.index_pin,
                'verified_members': dict(self.used)}


def native_packet(tx, rx):
    """Bind the encoded original host reply to its command without running script."""
    request, reply = json.loads(tx), json.loads(rx)
    require(request['type'] == 'execute_code' and reply['status'] == 'success', 'native_capture_wire_shape')
    tree = ast.parse(request['params']['code'])
    assignments = [n.value for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '_request' for t in n.targets)]
    node, = assignments
    require(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'loads' and isinstance(node.func.value, ast.Name)
            and node.func.value.id == '_json' and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str),
            'native_capture_request_literal')
    fixed = json.loads(node.args[0].value)
    enclosed = reply['result']['result']
    require(enclosed.startswith(PREFIX), 'native_capture_wire_prefix')
    inner = json.loads(enclosed[len(PREFIX):])
    require(inner['id'] == fixed['id'] and fixed['command'] == 'capture'
            and inner['result']['schema'] == 'human-eye-scene-delta-v1', 'native_capture_nonce_or_schema')
    return fixed, inner['result']


class Captures:
    """Materialize the historical ordered capture and retain native local arrays."""

    def __init__(self):
        from human_eye_plugin.scene_residency import SceneDeltaDecoder
        self.decoder = SceneDeltaDecoder()
        self.resources = {}

    def apply(self, packet):
        capture = self.decoder.apply(packet)
        self.resources.update({resource['id']: resource for resource in packet['resources']})
        self.resources = {key: self.resources[key] for key in packet['live_resources']}
        local = []
        for mesh in packet['capture']['meshes']:
            ref = mesh['_scene_resource']
            resource = self.resources[ref['id']]
            require(resource['revision'] == ref['revision'], 'native_local_resource_revision')
            local.append({'object_id': mesh['object_id'], 'vertices': resource['vertices_local'],
                          'matrix': ref['matrix'], 'scale': ref['scale']})
        return capture, local


def check_capture(capture, local, terminal, producer, query):
    """Cross-check the closed independent source, select faces, and bind old camera."""
    from human_eye_plugin.active_observation import fingerprint
    from human_eye_plugin.active_observation_host import source_binding
    from human_eye_plugin.source_region import display_state, ordered_geometry_identity

    meshes = capture['meshes']
    objects = {row['object_id']: row for row in terminal['objects']}
    require(len(meshes) == len(objects) == len(local)
            and {mesh['object_id'] for mesh in meshes} == set(objects), 'terminal_roster_changed')
    source = terminal['source']
    display = capture['display_snapshot']
    require(display['view_layer'] == {'name': source['view_layer'], 'instance_id': source['view_layer_id']},
            'original_view_layer_changed')
    current = {row['host_id']: row for row in display['objects']}
    require(len(current) == len(objects), 'original_display_roster_changed')
    for mesh, loc in zip(meshes, local, strict=True):
        host_id = mesh['object_id']
        row = objects[host_id]
        evaluated = row['evaluated']
        flags = current[host_id]
        require(loc['object_id'] == host_id and mesh['name'] == row['name']
                and loc['matrix'] == row['matrix_world'] and loc['scale'] == source['scale_length']
                and loc['vertices'] == evaluated['vertices'] and mesh['faces'] == evaluated['triangles']
                and mesh['vertices'] == evaluated['vertices_world_m']
                and flags['instance_id'] == row['instance_id'] and flags['visible_get'] is row['visible_get']
                and all(flags[k] is row['display'][k] for k in ('hide_get', 'hide_viewport', 'hide_render')),
                'terminal_local_world_order_or_display_changed/' + row['name'])
    binding = source_binding(capture)
    prior = producer['binding']
    keys = ('scene_revision', 'document_epoch', 'capture_scope', 'unit', 'coordinate_frame',
            'source', 'capture_state', 'objects')
    require(all(prior[key] == binding[key] for key in keys)
            and ordered_geometry_identity(capture, binding) == prior['ordered_geometry_sha256'],
            'original_producer_ordered_geometry_or_generation_changed')
    current_display = display_state(capture, binding)
    require(current_display == prior['image_scope'] and current_display['status'] == 'captured',
            'original_producer_display_identity_changed')
    spec = prior['camera_specification']
    require(tuple(row['name'] for row in spec['views']) == VIEWS and fingerprint(spec) == prior['camera_identity'],
            'original_six_camera_identity_changed')
    region = query['region']
    target, = [mesh for mesh in meshes if mesh['name'] == region['object']['name']]
    reference, = [mesh for mesh in meshes if mesh['name'] == query['reference']['name']]
    box = region['world_box_m']
    lo, hi = box['min'], box['max']
    within = [all(a <= x <= b for a, x, b in zip(lo, pt, hi, strict=True)) for pt in target['vertices']]
    rows = [i for i, face in enumerate(target['faces']) if all(within[v] for v in face)]
    vertices = sorted({v for i in rows for v in target['faces'][i]})
    fact = producer['facts']['region']
    require(fact['host_id'] == target['object_id'] and fact['source_triangle_indices'] == rows
            and fact['source_vertex_indices'] == vertices
            and fact['triangles_source_vertices'] == [target['faces'][i] for i in rows]
            and fact['vertices_world_m'] == [target['vertices'][v] for v in vertices]
            and producer['task_result']['reference']['object_id'] == reference['object_id']
            and producer['region_ref']['source_triangle_indices'] == rows,
            'producer_selection_or_reference_not_original')
    return {'original_scene_revision': binding['scene_revision'],
            'ordered_geometry_sha256': prior['ordered_geometry_sha256'],
            'camera_identity': prior['camera_identity'], 'display_identity': current_display['identity'],
            'object_count': len(meshes), 'selected_source_triangle_count': len(rows)}


def frame_binding(run, prefix, producer, reply):
    frame, = producer['frames']
    visibility = producer['facts']['visibility']
    require(frame['frame_identity'] == visibility['frame_identity'] and frame['image_ref'] == visibility['image_ref']
            and frame['image_scope'] == producer['binding']['image_scope'], 'historical_frame_scope_changed')
    pose, = [p for p in producer['binding']['camera_specification']['views'] if p['name'] == frame['view_name']]
    require(frame['pose'] == pose and visibility['view_name'] == pose['name'],
            'historical_frame_pose_not_in_original_six')
    png, npz = map(Path, (frame['image_path'], frame['arrays_path']))
    require(png.is_relative_to(run.root / prefix) and npz.is_relative_to(run.root / prefix),
            'historical_frame_crossed_run_scope')
    original_png, original_npz = run.take(png), run.take(npz)
    require(digest(original_png) == {'bytes': frame['PNG_bytes'], 'sha256': frame['image_sha256']}
            and digest(original_npz) == {'bytes': frame['compressed_array_file_bytes'],
                                         'sha256': frame['arrays_sha256']}, 'historical_frame_byte_pins_changed')
    images = [item for item in reply['result']['content'] if item['type'] == 'image']
    require(len(images) == 1 and images[0]['mimeType'] == 'image/png'
            and base64.b64decode(images[0]['data'], validate=True) == original_png,
            'historical_frame_not_same_public_MCP_image')
    height, width, channels = frame['arrays']['color']['shape']
    require(height == width and channels == 3, 'historical_color_shape_changed')
    return png, npz, width, {'frame_identity': frame['frame_identity'], 'view': pose['name'],
                            'PNG': digest(original_png), 'NPZ': digest(original_npz),
                            'selected_pixels': visibility['selected_surface_pixels']}


def held_wire(run, prefix, receipt, expected=None):
    n = receipt['index']
    d = f'{prefix}/mcp/rpc_{n:02d}'
    tx, rx = (run.take(f'{d}/{field}.bin') for field in ('TX', 'RX'))
    raw_receipt = run.json(f'{d}/RECEIPT.json')
    require(all(receipt[k] == val for k, val in raw_receipt.items()), 'historical_mcp_receipt_changed')
    meter, = [row for row in map(json.loads, run.take(prefix+'/mcp_io/MCP_IO.jsonl').splitlines())
              if row['id'] == receipt['id'] and row['method'] == 'tools/call']
    require(digest(tx) == {'bytes': receipt['TX_bytes'], 'sha256': meter['TX_sha256']}
            and len(tx) == meter['TX_bytes']
            and digest(rx) == {'bytes': receipt['RX_bytes'], 'sha256': receipt['RX_sha256']},
            'historical_mcp_wire_pins_changed')
    tx, rx = json.loads(tx), json.loads(rx)
    require(tx['id'] == rx['id'] == receipt['id'] and tx['method'] == 'tools/call'
            and tx['params']['name'] == 'human_eye_scene_observe'
            and rx['result']['isError'] is False, 'historical_mcp_wire_ids')
    if expected is not None:
        require(tx == expected['request'] and rx == expected['response'], 'historical_mcp_journal_changed')
    args = tx['params']['arguments']
    require(args['include_image'] is True and args['query']['mode'] == 'source_region'
            and args['query']['requested_facts'] == ['surface_proximity'], 'historical_image_request_changed')
    return args['query'], rx


def load_formal(run_name, commit, labels):
    """Load the two actually completed image-bearing observations from original P1."""
    with SealedRun(run_name, commit) as run:
        closure = run.json(SLOT+'/SLOT_RESULT.json')
        publication = run.json(SLOT+'/SLOT_PUBLICATION.json')
        asset = run.take(SLOT+'/native/input.blend')
        terminal = run.check_pin(closure['terminal_source'])
        initial = run.check_pin(closure['initial_source'])
        terminal, initial = map(json.loads, (terminal, initial))
        require(closure['status'] == publication['status'] == 'completed'
                and closure['closure_verification']['passed'] and closure['independent_before_after']['passed']
                and run.used[SLOT+'/SLOT_RESULT.json']['sha256'] == publication['result_sha256']
                and closure['asset_sha256'] == terminal['source']['asset_sha256'] == digest(asset)['sha256']
                and terminal['objects'] == initial['objects'], 'formal_source_or_closure_changed')
        held_close = run.json(SLOT+'/mcp/HELD_CLOSE.json')
        require(held_close['confirmed'] and held_close['production_eof_and_exit_verified']
                and held_close['exit_code'] == 0, 'formal_MCP_EOF_unverified')
        wire_index = {row['sequence']: row for row in run.json(SLOT+'/native/WIRE/INDEX.json')}
        meter = run.json(SLOT+'/mcp_io/REAL_HOST_STAGES.json')['requests']
        journal = list(map(json.loads, run.take(SLOT+'/PUBLIC_REQUESTS.jsonl').splitlines()))
        require(len(journal) == len(meter) == len(labels) == 2, 'formal_observation_count_changed')
        decoder = Captures()
        recovered = []
        for i, (label, row, observed) in enumerate(zip(labels, journal, meter, strict=True), 1):
            query, reply = held_wire(run, SLOT, row['receipt'], row)
            timing = observed['stages']['host_request']
            require(row['started_ns'] <= timing['started_ns'] <= timing['closed_ns'] <= row['client_returned_ns'],
                    'formal_tcp_not_inside_actual_call')
            n = i + 1
            tx, rx = (run.take(f'{SLOT}/native/WIRE/{n:03d}/{field}.bin') for field in ('REQUEST', 'RESPONSE'))
            fixed, packet = native_packet(tx, rx)
            require(fixed['id'] == observed['host_request_id'] and wire_index[n]['response_sendall_completed']
                    and len(tx) == observed['request_bytes'] == wire_index[n]['request_bytes']
                    and len(rx) == wire_index[n]['response_attempted_bytes']
                    and observed['outcome'] == 'success' and observed['command'] == 'capture'
                    and observed['decoder']['capture_state'] == packet['capture']['capture_state'],
                    'formal_tcp_not_paired_with_original_call')
            capture, local = decoder.apply(packet)
            require(Path(row['producer_archive']['path']).is_relative_to(run.root / SLOT),
                    'original_producer_crossed_slot')
            producer = json.loads(run.check_pin(row['producer_archive']))
            source = check_capture(capture, local, terminal, producer, query)
            png, npz, size, frame = frame_binding(run, SLOT, producer, reply)
            recovered.append({'label': label, 'capture': capture, 'query': query, 'producer': producer,
                              'terminal': terminal, 'local_geometry': local, 'png': png, 'npz': npz, 'size': size,
                              'proof': {'role': 'original_formal_P1', 'asset_sha256': closure['asset_sha256'],
                                        'public_request_id': row['id'], 'native_sequence': n,
                                        'native_host_request_id': fixed['id'], 'terminal': closure['terminal_source'],
                                        'source': source, 'frame': frame}})
        for case in recovered:
            case['proof']['custody'] = run.proof()
        return recovered


def load_n12():
    with SealedRun(ASSEMBLY, ASSEMBLY_COMMIT) as run:
        summary = run.json(PRE+'/SUMMARY.json')
        row, = [item for item in summary['requests'] if item['stage'] == 'N12']
        query, reply = held_wire(run, PRE, row['wire'])
        prior = run.json(PRE+'/REPLAY_CLOSE.json')
        held_close = run.json(PRE+'/mcp/HELD_CLOSE.json')
        require(summary['passed'] and prior['old_sources_unchanged'] and prior['actual_Blender_starts'] == 0
                and prior['actual_models'] == 0 and held_close['confirmed']
                and held_close['production_eof_and_exit_verified'] and held_close['exit_code'] == 0,
                'N12_historical_replay_did_not_close')
        expected = json.loads(run.check_pin(row['capture']))
        producer = json.loads(run.check_pin(row['producer']))
        path = HISTORY/'ORIGINAL_RUNTIME.zip'
        index_record = pinned_json(HISTORY_COMMIT, HISTORY.name.removeprefix('he_')+'/RUNTIME_INDEX.json')
        index = json.loads(index_record)
        require(digest(path.read_bytes()) == {k: index['archive'][k] for k in ('bytes', 'sha256')},
                'historical_source_for_N12_changed')
        members = {item['path']: item for item in index['files']}
        used = {}
        with ZipFile(path) as archive:
            def take(name):
                raw = archive.read(name)
                proof = digest(raw)
                require(proof == {k: members[name][k] for k in ('bytes','sha256')}
                        and raw == (HISTORY/name).read_bytes(), 'N12_original_host_member_changed/'+name)
                used[name] = proof
                return raw
            decoder = Captures()
            for n in (2, 3):
                args, packet = native_packet(*(take(f'{SLOT}/native/WIRE/{n:03d}/{f}.bin')
                                               for f in ('REQUEST','RESPONSE')))
                capture, local = decoder.apply(packet)
            terminal = json.loads(take(SLOT+'/TERMINAL_SOURCE.json'))
            actual = json.loads(take(SLOT+'/SLOT_RESULT.json'))
            asset = digest(take(SLOT+'/native/input.blend'))['sha256']
            require(actual['status'] == 'completed' and actual['closure_verification']['passed']
                    and actual['independent_before_after']['passed']
                    and asset == terminal['source']['asset_sha256'] == run.result['asset_SHA256'],
                    'N12_original_host_did_not_close')
        require(capture == expected and prior['calls'][2]['capture_state'] == capture['capture_state'],
                'N12_offline_capture_not_same_as_original_native_delta')
        source = check_capture(capture, local, terminal, producer, query)
        png, npz, size, frame = frame_binding(run, PRE, producer, reply)
        require(frame['selected_pixels'] == row['selected_pixels'] == 0
                and producer['facts']['visibility']['status'] == 'unknown',
                'N12_historical_zero_sample_control_changed')
        return {'label': 'N12', 'capture': capture, 'query': query, 'producer': producer, 'terminal': terminal,
                'local_geometry': local, 'png': png, 'npz': npz, 'size': size,
                'proof': {'role': 'original_zero_model_assembly_product_qualification',
                          'asset_sha256': asset, 'public_request_id': reply['id'],
                          'historical_native_delta_id': args['id'], 'source': source, 'frame': frame,
                          'registered_zero_sample_views': summary['registered_zero_sample_controls']['N12'],
                          'custody': run.proof(), 'historical_native_custody': {'evidence_commit': HISTORY_COMMIT,
                              'committed_index': digest(index_record), 'archive': index['archive'],
                              'verified_members': used}}}


def load_main():
    return (load_formal(ASSEMBLY, ASSEMBLY_COMMIT, ('N19', 'N25')) + [load_n12()]
            + load_formal(RAIL, RAIL_COMMIT, ('M19', 'M21')))
