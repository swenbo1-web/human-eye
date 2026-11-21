"""Independent source-region replay, pixel evidence, and wire policy utilities."""

import base64
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
PILOT = V / 'perf050_readonly_product_pilot_001'
PILOT_RUN = Path('D:/he_perf050_readonly_product_pilot_001')
PILOT_P = PILOT_RUN / 'slots/P1'
RUN = Path('D:/he_m4_source_region_active_view_001')
BASE = V / 'm5_joint_brief_source_projection_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
CAPTURE = V / 'm4_cross_scale_discovery_001/oracle/check_saved.py'
TOPOLOGY = V / 'm4_cross_scale_live_task_001/fixture/oracle.py'
POLICY = V / 'm4_cross_scale_live_qualification_001/checks/delivery.py'
LEGACY_WIRE = V / 'm5_global_observe_measure_qualification_001/checks/live_wire.py'
ASSET = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
PILOT_ZIP = 'd138efe19891843244f1049e0fab61ea5b6f2d4b923742d632516743ff1a7e71'
REQUEST_PATH = PILOT_P / 'product_calls/call_002/REQUEST.json'
PRODUCER_PATH = PILOT_P / 'product_full/call_002/SERVICE_RESULT.json'
POSITIVE = (86955, 1300)
TOP = (61845, 0)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return sha256(value).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode()


def pin(path):
    path = Path(path).resolve()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path.read_bytes())}


def save(path, value):
    def exact(item):
        if isinstance(item, Fraction):
            return str(item)
        raise TypeError('unexpected_evidence_type/' + type(item).__name__)

    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=exact).encode() + b'\n'
    with Path(path).open('xb') as output:
        output.write(data)
    return digest(data)


def load_install(path):
    binding = read(path)
    require(len(binding['source_manifest']) == 143, 'unexpected_runtime_source_manifest_size')
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    return binding


class Originals:
    def __init__(self):
        index = read(PILOT / 'RUNTIME_INDEX.json')
        descriptor = index['archive']
        require(descriptor['sha256'] == PILOT_ZIP, 'registered_pilot_archive_changed')
        path = Path(descriptor['path'])
        require(pin(path) == {**descriptor, 'path': str(path.resolve())}, 'sealed_pilot_zip_changed')
        self.archive = ZipFile(path)
        self.rows = {row['path']: row for row in index['files']}
        self.pins = {str(path.resolve()): pin(path)}
        require(len(self.rows) == 555 and set(self.archive.namelist()) == self.rows.keys(),
                'sealed_pilot_archive_membership_changed')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.archive.close()

    def member(self, path):
        path = Path(path).resolve()
        name = path.relative_to(PILOT_RUN.resolve()).as_posix()
        raw = path.read_bytes()
        row = self.rows[name]
        require(len(raw) == row['bytes'] and digest(raw) == row['sha256'] and raw == self.archive.read(name),
                'pilot_original_bytes_changed/' + name)
        self.pins[str(path)] = {'path': str(path), 'bytes': len(raw), 'sha256': row['sha256']}
        return raw

    def read(self, path, digest=None, within=None):
        path = Path(path)
        require(within is None or path.resolve().is_relative_to(Path(within).resolve()),
                'cross_slot_reference')
        value = self.member(path)
        require(digest is None or sha256(value).hexdigest() == digest, 'original_digest_mismatch')
        return json.loads(value)

    check = staticmethod(require)


def pilot_source(binding, originals):
    require(digest(originals.member(PILOT_P / 'native/input.blend')) == ASSET, 'pilot_asset_changed')
    request = originals.read(REQUEST_PATH)
    producer = originals.read(PRODUCER_PATH)
    response = originals.read(PILOT_P / 'product_calls/call_002/RESPONSE.json')
    terminal = originals.read(PILOT_P / 'TERMINAL_SOURCE.json')
    initial = originals.read(PILOT_P / 'initial_capture/TERMINAL_SOURCE.json')
    require(initial['objects'] == terminal['objects'] and
            initial['display_object_mask'] == terminal['display_object_mask'] == [True] * 28,
            'original_scene_changed_during_pilot')
    check = run_path(str(CAPTURE))
    captures, commands = check['decode_captures'](PILOT_P, binding, originals)
    capture = check['current_capture'](captures, producer['binding'], originals)
    require(len(commands) >= 2 and request['params']['name'] == 'human_eye_scene_observe' and
            request['params']['arguments'] == {'include_image': True, 'response_detail': 'brief', 'query': {
                'mode': 'source_region', 'region': {'object': {'name': 'N15'}, 'source_triangle_indices': [20, 21]},
                'reference': {'name': 'N23'}, 'requested_facts': ['surface_proximity']}},
            'expected_real_P1_source_region_request_changed')
    verify_capture(capture, terminal)
    return {'request': request, 'response': response['result'],
            'producer': producer, 'terminal': terminal, 'capture': capture}


def verify_capture(capture, terminal):
    rows = terminal['objects']
    require(len(capture['meshes']) == len(rows) == 28 and
            sum(len(row['faces']) for row in capture['meshes']) == 744 and
            sum(len(row['vertices']) for row in capture['meshes']) == 416 and
            terminal['source']['scale_length'] == 1 and
            all(mesh['name'] == row['name'] and mesh['object_id'] == row['object_id'] and
                mesh['vertices'] == row['evaluated']['vertices_world_m'] and
                mesh['faces'] == row['evaluated']['triangles']
                for mesh, row in zip(capture['meshes'], rows, strict=True)),
            'parent_capture_does_not_equal_current_independent_terminal_source')


def region_and_geometry(terminal):
    oracle = run_path(str(PILOT / 'truth/oracle.py'))
    objects = [{'name': row['name'], 'vertices': [tuple(map(Fraction, p)) for p in
                row['evaluated']['vertices_world_m']], 'triangles': row['evaluated']['triangles']}
               for row in terminal['objects']]
    target, directions = oracle['independent_regions'](objects)
    require(target['source_triangle_indices'] == [20, 21]
            and {name for name, row in directions.items() if row['clear']} == {'TOP', 'RIGHT'},
            'registered_exact_selection_or_clear_direction_changed')
    return target, directions, oracle['independent_measurement'](objects)


def split_pixels(rgb, owners, triangle_ids, selected, object_index):
    """Count each selected-region boundary pixel once in each contrast class."""
    import numpy as np

    region = (owners == object_index) & np.isin(triangle_ids, selected)
    symmetric = ((np.s_[:, 1:], np.s_[:, :-1]), (np.s_[:, :-1], np.s_[:, 1:]),
                 (np.s_[1:, :], np.s_[:-1, :]), (np.s_[:-1, :], np.s_[1:, :]))
    same = np.zeros(region.shape, dtype=bool)
    different = np.zeros(region.shape, dtype=bool)
    rgb = rgb.astype(np.int32)
    for center, adjacent in symmetric:
        qualifies = (region[center] & ~region[adjacent]) & (
            np.sum((rgb[center] - rgb[adjacent]) ** 2, axis=2) >= 24 ** 2)
        same[center] |= qualifies & (owners[adjacent] == object_index)
        different[center] |= qualifies & (owners[adjacent] != object_index)
    return {'surface': int(region.sum()), 'contrast': int((same | different).sum()),
            'same_owner_contrast': int(same.sum()), 'different_owner_contrast': int(different.sum()),
            'visible_source_ids': sorted(map(int, np.unique(triangle_ids[region])))}


def frame_metrics(frame, producer, original_bytes=None, slot=None):
    import numpy as np
    from PIL import Image

    paths = [Path(frame[key]).resolve() for key in ('image_path', 'arrays_path')]
    if slot is not None:
        require(all(path.is_relative_to(slot.resolve()) for path in paths), 'frame_references_a_different_slot')
    png, archive = [original_bytes(path) if original_bytes else path.read_bytes() for path in paths]
    hashes = [digest(png), digest(archive)]
    require(hashes == [frame['image_sha256'], frame['arrays_sha256']] and
            len(png) == frame['PNG_bytes'] and len(archive) == frame['compressed_array_file_bytes'],
            'original_frame_digests_changed')
    source = producer['facts']['region']
    binding = producer['binding']
    current = next(row for row in binding['objects'] if row['host_id'] == source['host_id'])
    view = frame['view_name']
    pose, = (pose for pose in binding['camera_specification']['views'] if pose['name'] == view)
    require(frame['pose'] == pose and frame['display_identity'] == binding['display_identity'] and
            frame['host_binding_sha256'] == binding['binding_sha256'] and
            frame['source_revision'] == binding['scene_revision'], 'current_frame_binding_mismatch')
    with np.load(BytesIO(archive), allow_pickle=False) as arrays, Image.open(BytesIO(png)) as image:
        rgb, owners, triangles = (arrays[k] for k in ('color', 'owners', 'triangle_ids'))
        require(np.array_equal(np.asarray(image.convert('RGB')), rgb) and
                arrays['display_object_mask'].tolist() == binding['image_scope']['participation_mask'],
                'pixel_archive_or_display_mask_changed')
        index = current['object_index']
        offsets = arrays['face_patch_offsets']
        metric = split_pixels(rgb, owners, triangles - int(offsets[index]), source['source_triangle_indices'], index)
        array_hashes = {key: digest(arrays[key].tobytes(order='C'))
                        for key in ('color', 'depth', 'owners', 'triangle_ids')}
    corners = np.c_[source['vertices_world_m'], np.ones(len(source['vertices_world_m']))]
    clip = (np.asarray(pose['projection_matrix']) @ np.asarray(pose['view_matrix']) @ corners.T).T
    corners_inside = bool(np.all(clip[:, 3] > 0) and np.all(np.abs(clip[:, :3]) <= clip[:, 3:4]))
    return {**metric, 'view_name': view, 'pose': pose, 'corners_inside_clip': corners_inside,
            'array_sha256': array_hashes, 'PNG_sha256': hashes[0], 'NPZ_sha256': hashes[1],
            'PNG_bytes': len(png), 'NPZ_bytes': len(archive), 'image_ref': frame['image_ref'],
            'frame_identity': frame['frame_identity'], 'PNG': str(paths[0]), 'NPZ': str(paths[1])}


def replay_cli(content):
    helpers, limits = run_path(str(POLICY))['budget_helpers']()
    sys.path.insert(0, str(LEGACY_WIRE.parent))
    paths = run_path(str(LEGACY_WIRE))['omitted_paths']
    text, = [row['text'] for row in content['content'] if row['type'] == 'text']
    stages = []
    for sec, header in zip(('0.0000', '10.0000', '100.0000'), (33, 34, 35), strict=True):
        initial = helpers['model_items'](content, sec)
        require(len(initial[0]['text'].encode()) == header and
                (limits['MCP_bytes'], limits['history_approximate_tokens']) == (12000, 3000),
                'fixed_CLI_wire_read_limits_changed')
        mcp = helpers['truncate_items'](initial, 12000)
        history = helpers['truncate_items'](mcp, 3000, token_mode=True)
        images = [row for row in initial if row['type'] == 'input_image']
        for name, actual in [('MCP', mcp), ('history', history)]:
            words = [row['text'] for row in actual if row['type'] == 'input_text']
            kept = words[1] if len(words) > 1 else ''
            omitted = paths(text, kept)
            required_roots = {'schema', 'region', 'region_ref', 'task_result', 'visibility', 'images',
                              'observation_status', 'binding', 'image_delivery'}
            stages.append({'header': header, 'stage': name, 'body_bytes': len(kept.encode()),
                           'body_exact': actual == initial, 'omitted_leaf_count': len(omitted),
                           'omitted_required_leaves': [list(item) for item in omitted if item[0] in required_roots],
                           'PNG_exact': [row for row in actual if row['type'] == 'input_image'] == images})
    return {'body_bytes': len(text.encode()), 'passed': all(stage['body_exact'] and stage['PNG_exact'] for stage in stages),
            'required_payload_and_PNG_preserved': all(not row['omitted_required_leaves'] and row['PNG_exact'] for row in stages),
            'stages': stages}


def parse_public(response, frame):
    require(response['isError'] is False, 'public_source_region_error')
    text, png = response['content']
    require(text['type'] == 'text' and png['type'] == 'image' and png['mimeType'] == 'image/png',
            'exactly_one_native_PNG_required')
    raw = base64.b64decode(png['data'], validate=True)
    body = json.loads(text['text'])
    require(len(body['images']) == 1 and body['images'][0]['image_block_index'] == 1 and
            body['images'][0]['image_ref'] == frame['image_ref'] and
            body['images'][0]['frame_identity'] == frame['frame_identity'] and
            body['images'][0]['image_sha256'] == frame['PNG_sha256'] == digest(raw) and
            body['region_ref']['source_triangle_indices'] == [20, 21], 'public_PNG_or_selected_source_not_bound')
    return body, raw
