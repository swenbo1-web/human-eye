"""Qualify the held-out regions and common original-image route from sealed live captures."""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
import zipfile


HERE = Path(__file__).resolve().parent
V = HERE.parent
REPO = V.parent
PRIOR = V/'m4_yanyite_dual_curved_region_native_001'
RUNTIME = PRIOR/'runtime'
OLD = Path('D:/he_m2_resident_capture_direct_delta_001')
OUTPUT_ROOT = Path('D:/he_m4_yanyite_bilateral_region_native_001/preflight').resolve()
PRODUCT_PATH = V/'m2_resident_capture_direct_delta_001/install/PRODUCT_RUN_BINDING.json'
PRODUCT_GIT = '4104add44251b03a1eafc5af69502aa2575b632c'
EVIDENCE_GIT = '48899b41f592fc60b266b4b278bd7e4b9d5c8daa'
SOURCE_SHA = '5445ad313f43c2ed3e75c3efafa7e9982e03e8ef08d78374b65ddeae05a32fc9'
WHEEL_SHA = '40a3aab846f9213eeb536f8828bc20ef42f5ba09f2430a2438baad2275882807'
TERMINAL_SHA = '63b2ece7ee16f1a14083db12124d7a55354354fbcabcb40a56d13ea7af3cb399'
ASSET_SHA = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
PYTHON_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
TARGET = '0135bbc4-c6c7-4003-a402-6f2e0283497d'
CATALOGUE = V/'m4_dense_sweep_integrated_native_startup_001/inputs/EVIDENCE_TOOLS_SCHEMA.json'
BOXES = {'left': ((-.10, -.09, .65), (-.025, .09, .80)),
         'right': ((.025, -.09, .65), (.10, .09, .80))}
EXPECTED = {'left': (178, 125), 'right': (155, 98)}
VIEW_CASES = {'left': {'SCENE': (0, 0), 'LEFT': (93841, 146)},
              'right': {'SCENE': (110809, 149), 'RIGHT': (125550, 155)}}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        stream.write('\n')


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)}


def bind_inputs():
    def git_blob(path):
        return subprocess.check_output(['git', '-C', str(REPO), 'show',
            f'{EVIDENCE_GIT}:{path.relative_to(REPO).as_posix()}'])

    product, index = read(PRODUCT_PATH), read(OLD/'sealed/RAW_INDEX.json')
    result_file = PRODUCT_PATH.parents[1]/'RESULT.json'
    product_proof = read(result_file)
    require(all(path.read_bytes() == git_blob(path) for path in (PRODUCT_PATH, result_file))
            and (product['preparation_git'], product['source_sha256'], product['wheel_sha256'])
                == (PRODUCT_GIT, SOURCE_SHA, WHEEL_SHA)
            and pin(product['wheel_path'])['sha256'] == WHEEL_SHA, 'fixed_candidate_identity_changed')
    bundle = OLD/'sealed/ORIGINAL_RUNTIME.zip'
    require(pin(bundle) == index['archive'] == product_proof['raw_evidence_local'] and
            index['member_count'] == product_proof['raw_member_count'] == 673,
            'prior_closed_runtime_archive_changed')
    files = ['slots/A/TERMINAL_SOURCE.json', 'slots/B/TERMINAL_SOURCE.json',
             'slots/A/RUNTIME_CLOSE.json', 'slots/B/RUNTIME_CLOSE.json', 'SCORE.json']
    for step in ('002', '003'):
        files.extend(f'slots/B/native/WIRE/{step}/{name}' for name in ('REQUEST.bin', 'RESPONSE.bin'))
    paths = [PRODUCT_PATH, result_file, Path(product['wheel_path']), bundle, OLD/'sealed/RAW_INDEX.json']
    with zipfile.ZipFile(bundle) as z:
        for short in files:
            path = OLD/short
            proof = pin(path)
            require(z.read(short) == path.read_bytes() and
                    index['members'][short] == {key: proof[key] for key in ('bytes', 'sha256')},
                    'preserved_source_or_wire_not_archive_member/' + short)
            paths.append(path)
    require(pin(OLD/files[0])['sha256'] == TERMINAL_SHA and pin(OLD/files[0])['bytes'] == 9_614_509
            and read(OLD/'SCORE.json')['passed'], 'original_terminal_not_expected_proof')
    for path in (OLD/files[2], OLD/files[3]):
        close = read(path)
        require(close['errors'] == [] and close['Blender_exit']['confirmed'] and
                close['public_MCP_close']['production_eof_and_exit_verified'], 'prior_ownership_not_successfully_closed')
    return product, paths


def scene_truth(np):
    """Independently select the source rows and prove closest points to the full closed cube."""
    from human_eye_plugin.blender_mcp_host import RPC_PREFIX
    from human_eye_plugin.scene_residency import SceneDeltaDecoder

    oracle = run_path(str(PRIOR/'score/oracle.py'))
    terminal, donor = (read(OLD/f'slots/{arm}/TERMINAL_SOURCE.json') for arm in ('A', 'B'))
    require(terminal['source']['asset_sha256'] == donor['source']['asset_sha256'] == ASSET_SHA,
            'wrong_original_asset')
    require(terminal['display_object_mask'] == donor['display_object_mask'] == [True, False] and
            terminal['source_face_offsets'] == donor['source_face_offsets'] == [0, 53264, 53276],
            'full_native_display_or_source_offsets_changed')
    decoder = SceneDeltaDecoder()
    captures = []
    observed_resources = []
    for step in ('002', '003'):
        directory = OLD/f'slots/B/native/WIRE/{step}'
        request, response = (read(directory/name) for name in ('REQUEST.bin', 'RESPONSE.bin'))
        outer = response['result']['result']
        require(response['status'] == 'success' and response['result']['executed'] is True and outer.startswith(RPC_PREFIX),
                'prior_TPC_capture_not_successful')
        envelope = json.loads(outer[len(RPC_PREFIX):])
        require(envelope['id'] in request['params']['code'] and '"command":"capture"' in request['params']['code'],
                'prior_native_request_response_not_bound')
        observed_resources.append(len(envelope['result']['resources']))
        captures.append(decoder.apply(envelope['result']))
    cold, cap = captures
    require(observed_resources == [2, 0] and cold == cap, 'prior_same_capture_cold_and_warm_source_changed')
    require(cap['display_snapshot']['view_layer']['instance_id'] == donor['source']['view_layer_id'],
            'prior_wire_not_same_closed_view_layer')

    raw = {key: terminal[key] for key in ('source', 'display_object_mask', 'source_face_offsets', 'layer_collections', 'scene_cameras')}
    raw.update(source_ref='offline-preserved-48899b41-current-capture', objects=[])
    for a, b, mesh in zip(terminal['objects'], donor['objects'], cap['meshes'], strict=True):
        require(a['name'] == b['name'] == mesh['name'] and a['object_id'] == b['object_id'] == mesh['object_id']
                and a['evaluated'] == b['evaluated'] and a['visible_get'] is b['visible_get']
                and a['evaluated']['triangles'] == mesh['faces']
                and np.allclose(np.asarray(a['evaluated']['vertices_world_m']), np.asarray(mesh['vertices']),
                                rtol=0, atol=1e-7), 'different_ordered_evaluated_geometry_between_native_and_wire')
        row = {key: a[key] for key in ('object_id', 'instance_id', 'name', 'mesh_name', 'matrix_world', 'visible_get', 'display')}
        row.update(vertices=a['evaluated']['vertices_world_m'], triangles=a['evaluated']['triangles'],
                   polygon_count=a['evaluated']['polygon_count'])
        raw['objects'].append(row)
    target, cube = raw['objects']
    require((target['name'], cube['name']) == (TARGET, 'Cube'), 'unexpected_ordered_target_and_reference')
    source = {}
    for side, box in BOXES.items():
        a = oracle['region_truth'](target['vertices'], target['triangles'], cube['vertices'], cube['triangles'], box)
        b = oracle['region_truth'](cap['meshes'][0]['vertices'], target['triangles'], cube['vertices'], cube['triangles'], box)
        require((a['triangle_count'], a['vertex_count']) == (b['triangle_count'], b['vertex_count']) == EXPECTED[side]
                and a['triangle_ids'] == b['triangle_ids'] and a['vertex_ids'] == b['vertex_ids']
                and a['direction_world'] == b['direction_world'] == [0, 0, 1], 'dual_source_selection_or_direction_disagrees')
        source[side] = {'native': a, 'wire': b}
    left, right = (source[k]['wire'] for k in BOXES)
    require(left['distance_m'] >= .201 > right['distance_m'] and
            abs(left['distance_m'] - .201660157584) < 1e-10 and abs(right['distance_m'] - .200195311849) < 1e-10,
            'independent_threshold_order_or_exact_distance_changed')
    return raw, cap, source, observed_resources


def sample_pixels(np, triangles, owners, selected, offsets):
    chosen = (owners == 0) & np.isin(triangles, np.asarray(selected, dtype=np.int32) + offsets[0])
    matches = np.argwhere(chosen)
    count = len(np.unique(triangles[chosen]))
    if not len(matches):
        return {'selected_pixels': 0, 'sampled_source_rows': 0, 'sample_row_column_source': None}
    row, col = (int(n) for n in matches[len(matches)//2])
    return {'selected_pixels': len(matches), 'sampled_source_rows': count,
            'sample_row_column_source': [row, col, int(triangles[row, col])-offsets[0]]}


def product_views(root, np, cap, truth):
    from human_eye_plugin import source_region as sr

    proof = {}
    for side, views in VIEW_CASES.items():
        case = truth[side]['wire']
        prepared = sr.prepare_region(cap, {'region': {'object': {'name': TARGET},
                                     'source_triangle_indices': case['triangle_ids']}})
        measured = sr.measure_region(prepared, {'name': 'Cube'}, None)['facts']['surface_proximity']
        require(measured['status'] == 'measured' and abs(measured['value']['distance_m']-case['distance_m']) < 1e-12,
                'installed_selected_measurement_inconsistent_with_independent_truth/' + side)
        current = sr.observe_region(prepared, root/side, include_image=True)
        require(current['facts']['visibility']['selected_surface_pixels'] == views['SCENE'][0]
                and current['facts']['visibility']['complete_witness'] is None, 'source_region_unknown_or_first_view_drift')
        scoped = {}
        for view, expected in views.items():
            if view == 'SCENE':
                frame, = current['frames']
            else:
                frame = prepared.images.render_view(view)
            png, npz = pin(frame['image_path']), pin(frame['arrays_path'])
            require(png['sha256'] == frame['image_sha256'] and npz['sha256'] == frame['arrays_sha256'],
                    'installed_product_original_PNG_or_NPZ_changed')
            with np.load(npz['path'], allow_pickle=False) as arrays:
                values = sample_pixels(np, arrays['triangle_ids'], arrays['owners'], case['triangle_ids'], [0, 53264, 53276])
                require(not np.any(arrays['owners'] == 1) and arrays['display_object_mask'].tolist() == [True, False]
                        and arrays['display_identity'].item() == prepared.binding['display_identity'],
                        'product_frame_hidden_cube_or_source_binding_changed')
            require((values['selected_pixels'], values['sampled_source_rows']) == expected,
                    f'product_expected_sample_counts_changed/{side}/{view}/{values}')
            scoped[view] = {**values, 'PNG': png, 'NPZ': npz, 'view_name': frame['view_name']}
        proof[side] = {'current_product_measurement': measured, 'first_view_only': True, 'views': scoped}
    return proof


INIT = {'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26',
        'capabilities': {}, 'clientInfo': {'name': 'offline-closed-region-preflight', 'version': '1'}}}
NOTIFY = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
LIST = {'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'}


def ordinary(root, group, raw, truth, np):
    from bridge import Owner, PRODUCT_TOOL, TOOLS
    from frame_device import FrameDevice
    from runtime import transport

    def fail(*args, **kwargs):
        raise AssertionError('data_preflight_cannot_invoke_live_Blender_or_product_dispatch')

    class ArchivedDevice(FrameDevice):
        def _capture(self, *, terminal):
            require(not terminal, 'data_preflight_does_not_create_terminal_blender_snapshot')
            self.source_reads.append({'event': 'offline_sealed_current_source', 'source_ref': raw['source_ref']})
            return raw

    class Runtime:
        def __init__(self, folder):
            self.folder = folder
            self.device = ArchivedDevice(folder, ASSET_SHA, group, group+'1', fail)
            self.buffers = self.device.buffers
            self.cameras = self.device.cameras
            self.product_tools = read(CATALOGUE) if group == 'P' else []

        def __getattr__(self, name):
            if name in ('scene_data', 'render_views', 'render_local', 'image_specification'):
                return getattr(self.device, name)
            if name in ('native_run', 'public_request'):
                return fail
            raise AttributeError(name)

    root.mkdir()
    runtime = Runtime(root)
    deadline = time.perf_counter_ns() + 120_000_000_000
    owner = Owner(runtime, {'group': group, 'label': group+'1', 'phase': 'formal', 'worker_deadline_ns': deadline,
                            'output': str(root/'owner')})
    wire = None
    frames = {}
    try:
        endpoint = owner.start(root/'ENDPOINT.json')
        wire = transport.StdioClient([sys.executable, '-IB', '-X', 'utf8', str(RUNTIME/'thin_stdio.py'),
                '--endpoint', str(endpoint), '--audit', str(root/'attachment_audit')], root, root/'mcp', deadline)
        wire.call(INIT)
        wire.call(NOTIFY)
        tools = wire.call(LIST)['result']['tools']
        require([t for t in tools if t['name'] != PRODUCT_TOOL] == TOOLS and len(tools) == len(TOOLS)+(group == 'P'),
                'ordinary_path_catalogue_diverged')

        def call(label, tool, arguments, *, allowed=True):
            q = {'jsonrpc': '2.0', 'id': label, 'method': 'tools/call', 'params': {'name': tool, 'arguments': arguments}}
            answer = wire.call(q)
            require(answer['id'] == label and answer['result']['isError'] is (not allowed),
                    'ordinary_read_only_tool_error_or_reply_mismatch/' + label + '/' + str(answer['result']['content'][0])[:1200])
            return answer['result']['content']

        def execute(label, code):
            body, = call(label, 'execute_python', {'code': code})
            answer = json.loads(body['text'])
            require(answer['error'] is None and len(body['text'].encode()) <= 12000, 'ordinary_result_exceeds_compact_evidence')
            return json.loads(answer['stdout'])

        numeric = execute('source-rows-in-persistent-session', f"""
import json
source = scene_data()
actor, cube = source['objects']
vertices = np.asarray(actor['vertices'])
triangles = np.asarray(actor['triangles'])
cube_box = np.asarray(cube['vertices'])
minimum, maximum = cube_box.min(axis=0), cube_box.max(axis=0)
boxes = {BOXES!r}
ids = {{}}
counts = {{}}
for name, (lo, hi) in boxes.items():
    inside = ((vertices >= lo) & (vertices <= hi)).all(axis=1)
    rows = np.flatnonzero(inside[triangles].all(axis=1))
    ids[name] = rows
    vv = np.unique(triangles[rows])
    cloud = vertices[vv]
    gaps = np.concatenate((cloud-minimum, maximum-cloud), axis=1)
    which, face = np.unravel_index(np.argmin(gaps), gaps.shape)
    a = cloud[which].copy()
    b = a.copy()
    b[face%3] = minimum[face] if face < 3 else maximum[face-3]
    dist = float(np.linalg.norm(b-a))
    counts[name] = {{'triangle_count': len(rows), 'vertex_count': len(vv), 'triangle_ids': rows.tolist(), 'distance_m': dist,
                     'direction': ((b-a)/dist).tolist(), 'a': a.tolist(), 'b': b.tolist()}}
print(json.dumps(counts))
""")
        for side, actual in numeric.items():
            expected = truth[side]['native']
            require(actual['triangle_ids'] == expected['triangle_ids'] and actual['vertex_count'] == expected['vertex_count']
                    and actual['direction'] == expected['direction_world'] and abs(actual['distance_m']-expected['distance_m']) < 1e-12,
                    'ordinary_persistent_numerical_witness_disagrees/' + side)
        call('invalid-crop-rejected', 'render_local', {'direction': 'LEFT', 'target_world_m': [0, 0, 0],
                                                      'view_span_m': 0.0}, allowed=False)
        rendered = execute('local-both-and-pixel-source-from-buffer', """
images = {}
for name, direction in (('left','LEFT'), ('right','RIGHT')):
    points = vertices[np.unique(triangles[ids[name]])]
    focus = ((points.min(axis=0) + points.max(axis=0))/2).tolist()
    frame = render_local(direction, focus, 0.25)
    arrays = buffers[frame['ref']]
    triangle_ids = arrays['triangle_ids']
    owners = arrays['owners']
    included = (owners == 0) & np.isin(triangle_ids, ids[name])
    locations = np.argwhere(included)
    y, x = map(int, locations[len(locations)//2])
    images[name] = {'ref': frame['ref'], 'view': direction, 'selected_pixels': len(locations),
                    'sampled_source_rows': len(np.unique(triangle_ids[included])),
                    'sample_row_column_source': [y, x, int(triangle_ids[y,x])]}
print(json.dumps(images))
""")
        blocks = call('two-original-png-attachments', 'read_images', {'refs': [rendered[s]['ref'] for s in BOXES]})
        require(len(blocks) == 4, 'ordinary_two_original_mixed_image_blocks_required')
        for j, (side, capsule) in enumerate(rendered.items()):
            caption, image = blocks[2*j:2*j+2]
            require(caption['type'] == 'text' and caption['text'].split(' ', 1)[0] == capsule['ref']
                    and image['type'] == 'image' and image['mimeType'] == 'image/png', 'ordinary_image_order_or_ref_changed')
            delivery = json.loads(caption['text'].splitlines()[1])
            png = pin(delivery['local_image_path'])
            frame = runtime.device.by_ref[capsule['ref']]
            npz = pin(frame['NPZ'])
            require(Path(png['path']).is_relative_to(root) and Path(npz['path']).is_relative_to(root)
                    and delivery['local_image_path'] == Path(png['path']).as_posix()
                    and sha256(base64.b64decode(image['data'], validate=True)).hexdigest() == png['sha256']
                    == delivery['image_sha256'] == frame['PNG_sha256'] and npz['sha256'] == frame['NPZ_sha256'],
                    'ordinary_original_image_not_bound_to_same_slot_files')
            with np.load(npz['path'], allow_pickle=False) as value:
                witnessed = sample_pixels(np, value['triangle_ids'], value['owners'], truth[side]['native']['triangle_ids'],
                                          raw['source_face_offsets'])
                require(not np.any(value['owners'] == 1) and value['display_object_mask'].tolist() == [True, False]
                        and all(capsule[key] == val for key, val in witnessed.items()) and witnessed['selected_pixels'] > 0,
                        'ordinary_same_frame_current_source_pixel_not_verified/' + side)
            frames[side] = {**capsule, 'PNG': png, 'NPZ': npz}
        require(len(runtime.device.source_reads) == 1 and len([event for event in runtime.device.events
                if event['event'] == 'native_raster_attempt']) == 2, 'ordinary_offline_reads_and_raster_budget')
    finally:
        try:
            wire_close = wire.finish() if wire is not None else None
        finally:
            owner_close = owner.close()
        require(wire_close and wire_close['confirmed'] and wire_close['exit_code'] == 0 and
                owner_close['confirmed'] and not owner_close['errors'] and not owner_close['transport_errors'],
                'real_offline_ordinary_stdio_owner_close_failed')
    require(all(pin(frame['PNG']['path']) == frame['PNG'] for frame in frames.values()), 'closed_original_PNG_not_reopenable')
    return {'tools': tools, 'quantities': numeric, 'frames': frames, 'wire_closure': wire_close,
            'owner_closure': owner_close, 'calls': len(owner.rows), 'geometry_reads': 1, 'rasters': 2}


def main(output):
    require(sys.flags.isolated and sys.dont_write_bytecode and pin(sys.executable)['sha256'] == PYTHON_SHA,
            'fixed_offline_python_required')
    output = output.resolve()
    require(output.is_relative_to(OUTPUT_ROOT), 'current_preflight_output_required')
    product, sources = bind_inputs()
    sys.path[:0] = [str(RUNTIME), product['install_root'], product['dependency_root']]
    from common import add_paths

    add_paths()
    import numpy as np
    from human_eye_plugin import attention_raster

    require(Path(attention_raster.__file__).resolve().is_relative_to(Path(product['install_root']).resolve()),
            'exact_raster_runtime_source_not_loaded')
    output.mkdir(parents=True, exist_ok=False)
    raw, cap, truth, observed_resources = scene_truth(np)
    views = product_views(output/'product', np, cap, truth)
    arms = {group: ordinary(output/group, group, raw, truth, np) for group in ('N', 'P')}
    require(all(arms['N']['frames'][side]['PNG']['sha256'] == arms['P']['frames'][side]['PNG']['sha256'] and
                arms['N']['quantities'][side] == arms['P']['quantities'][side] for side in BOXES),
            'ordinary_equivalent_arms_different_data_or_image')
    sources.extend((Path(__file__), PRIOR/'score/oracle.py', RUNTIME/'thin_stdio.py', CATALOGUE, Path(sys.executable)))
    sources.extend(Path(m.__file__).resolve() for m in tuple(sys.modules.values()) if getattr(m, '__file__', None)
                   and Path(m.__file__).resolve().is_relative_to(V))
    save(output/'DATA_PREFLIGHT.json', {'passed': True, 'product_commit': PRODUCT_GIT,
          'source_pins': [pin(path) for path in sorted({Path(p).resolve() for p in sources})],
          'truth': truth, 'retained_native_delta_resources': observed_resources, 'product_views': views,
          'ordinary_arms': arms, 'actual_new_Blender': 0, 'actual_new_models': 0,
          'offline_product_rasters': 4, 'offline_common_rasters': 4, 'offline_ordinary_calls': 8})
    print('Both registered ordinary arms delivered the two sampled local original PNGs after real stdio closure.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
