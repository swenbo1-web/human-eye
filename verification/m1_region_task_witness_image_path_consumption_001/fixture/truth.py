"""Recompute task truth and verify the historical delivered and constructed images."""

from fractions import Fraction
from hashlib import sha256
import base64
import io
import json
from math import sqrt
from pathlib import Path
from runpy import run_path
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
OLD = VERIFICATION / 'm4_cross_scale_live_task_formal_001'
RUNTIME = Path('D:/he_m4_cross_scale_live_task_formal_001')
FIXTURE = Path('D:/he_m4_cross_scale_live_task_001/fixture')
ASSET_SHA = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
READBACK_SHA = '836219a6cd00f81dc658b0277c4dfa82cfafba8d094570ec797dbc5eb8e12dee'
INDEX_SHA = 'aa0e6e76930b58e4928683e6318428b72cedf30a3af1008cb12595b1bfba27d3'
ARCHIVE_SHA = '38be66d67b301524de5594acab12158342da7c31e2aa75629109e2fe4ff8a89d'
ORACLE = VERIFICATION / 'm4_dense_panel_sweep_001/truth/panel_truth.py'
ORACLE_SHA = '2930b3651bede09c47a1e654c03212a45b85780c7cb316da225918d844b26ce6'
OLD_TRUTH_SHA = '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922'
COUNTS = {'objects': 21, 'vertices': 148, 'triangles': 184}
AREA = (Fraction(1, 128), Fraction(1, 32))
NZ = Fraction(3, 4)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def hash_bytes(data):
    return sha256(data).hexdigest()


def read_bound(path, digest):
    data = path.read_bytes()
    require(hash_bytes(data) == digest, 'frozen_bytes_changed/' + str(path))
    return data


def pins(path, data):
    return {'path': path.as_posix(), 'bytes': len(data), 'sha256': hash_bytes(data)}


class OriginalRuntime:
    """Read a named archived byte sequence and confirm the original disk copy."""

    def __init__(self, raw_index, bundle):
        entries = raw_index['files']
        self.index = {row['path']: row for row in entries}
        self.bundle = bundle
        self.used = {}
        require(len(entries) == len(self.index) == raw_index['count']
                and len(set(bundle.namelist())) == len(bundle.namelist()) == len(self.index)
                and set(bundle.namelist()) == self.index.keys(), 'archive_index_member_shape_changed')

    def read(self, path):
        absolute = path.resolve(strict=True)
        name = absolute.relative_to(RUNTIME.resolve()).as_posix()
        data = self.bundle.read(name)
        record = self.index[name]
        require((len(data), hash_bytes(data)) == (record['bytes'], record['sha256'])
                and data == absolute.read_bytes(), 'original_disk_archive_or_index_mismatch/' + name)
        self.used[name] = pins(path, data)
        return data

    def json(self, path):
        return json.loads(self.read(path))


def original_geometry(runtime, saved):
    rows = {o['name']: o for o in saved['objects']}
    require(len(rows) == len(saved['objects']) == COUNTS['objects']
            and [saved['frame'], saved['subframe'], saved['unit_system'], saved['scale_length']]
            == [1, 0.0, 'METRIC', 1.0], 'saved_scene_identity_changed')
    slots = {}
    for label in ('N1', 'P1'):
        folder = RUNTIME / 'slots' / label
        before = runtime.json(folder / 'initial_capture/TERMINAL_SOURCE.json')
        after_path = folder / 'TERMINAL_SOURCE.json'
        after = runtime.json(after_path)
        require(runtime.read(after_path) == runtime.read(folder / 'terminal_sources/live-source-002.json')
                and hash_bytes(runtime.read(folder / 'native/input.blend')) == ASSET_SHA,
                'historical_slot_asset_or_public_source_alias_changed/' + label)
        for key in ('schema', 'source', 'objects', 'display_object_mask', 'display_scope', 'layer_collections',
                    'scene_cameras', 'source_face_offsets'):
            require(before[key] == after[key], 'historical_slot_initial_final_changed/' + label + '/' + key)
        source = after['source']
        require(source['asset_sha256'] == ASSET_SHA
                and [source['frame'], source['subframe'], source['scale_length']] == [1, 0.0, 1.0]
                and source['unit_settings']['system'] == 'METRIC'
                and after['display_object_mask'] == [True] * COUNTS['objects'],
                'historical_slot_display_or_units_changed/' + label)
        require({o['name'] for o in after['objects']} == rows.keys(), 'historical_object_set_changed/' + label)
        offsets = [0]
        for obj in after['objects']:
            authored = rows[obj['name']]
            require(obj['visible_get'] is authored['visibility']['viewport'] is True
                    and obj['matrix_world'] == authored['evaluated_matrix_world']
                    and obj['native_matrix_world'] == authored['matrix_world']
                    and obj['modifiers'] == authored['modifiers'] and obj['parent'] == authored['parent'],
                    'historical_object_instance_scope_changed/' + obj['name'])
            for mode in ('native', 'evaluated'):
                a, b = obj[mode], authored[mode]
                for key, previous in (('vertices_world_m', 'vertices_world'), ('vertices', 'vertices_local'),
                                      ('triangles', 'triangles'), ('polygons', 'polygons'),
                                      ('triangle_polygons', 'triangle_polygon_indices')):
                    require(a[key] == b[previous], 'historical_source_array_changed/' + obj['name'] + '/' + key)
            offsets.append(offsets[-1] + len(obj['evaluated']['triangles']))
        require(offsets == after['source_face_offsets'] and offsets[-1] == COUNTS['triangles'],
                'historical_source_triangle_offsets_changed/' + label)
        slots[label] = after
    meshes = {name: (
        tuple(tuple(map(Fraction, point)) for point in row['evaluated']['vertices_world']),
        tuple(tuple(face) for face in row['evaluated']['triangles']),
    ) for name, row in rows.items()}
    require(sum(len(v) for v, _ in meshes.values()) == COUNTS['vertices']
            and sum(len(f) for _, f in meshes.values()) == COUNTS['triangles'], 'saved_source_counts_changed')
    return meshes, slots


def exact_truth(meshes, oracle):
    eligible, components, rectangles = {}, 0, 0
    expected = {
        'M02': ((0, 0, 1), (0, 0, 1), Fraction(1, 4096), '1/64', '1'),
        'M06': ((2, 2, 1), (0, 0, 1), Fraction(1, 4096), '1/64', '1'),
        'M09': ((-2, 0, 1), (0, -1, 3), Fraction(10, 65536), 'sqrt(10)/256', '3/sqrt(10)'),
    }
    for name, mesh in meshes.items():
        groups, normals = oracle['partition'](mesh)
        components += len(groups)
        for (normal, _), faces in groups:
            doubled = tuple(sum(normals[i][axis] for i in faces) for axis in range(3))
            rectangle = oracle['boundary_rectangle'](*mesh, faces, doubled)
            if rectangle is None:
                continue
            rectangles += 1
            area_squared = oracle['dot'](doubled, doubled) / 4
            norm_squared = oracle['dot'](normal, normal)
            if not AREA[0]**2 <= area_squared <= AREA[1]**2 or normal[2] < 0 or normal[2]**2 < NZ**2 * norm_squared:
                continue
            require(name in expected and name not in eligible, 'unexpected_exact_region/' + name)
            corners, corner_indices = rectangle
            center = tuple((a + b) / 2 for a, b in zip(corners[0], corners[2], strict=True))
            expected_center, expected_normal, expected_area, area, normal_z = expected[name]
            require((center, normal, area_squared, faces) == (expected_center, expected_normal, expected_area, [0, 1]),
                    'registered_exact_region_changed/' + name)
            proofs = {view: oracle['visibility'](meshes, name, faces, corners, normal, direction)
                      for view, direction in oracle['DIRECTIONS'].items()}
            for proof in proofs.values():
                proof['tested_other_triangles'] = COUNTS['triangles'] - len(faces)
            open_views = [view for view, proof in proofs.items() if proof['whole_region_clear']]
            eligible[name] = {
                'object_name': name, 'source_triangle_indices': faces, 'corner_vertex_indices': corner_indices,
                'center_world_m': oracle['numeric_vector'](center), 'center_world_m_exact': list(map(str, center)),
                'corners_world_m': [oracle['numeric_vector'](p) for p in corners],
                'area_m2': sqrt(area_squared), 'area_m2_exact': area, 'area_squared_m4_exact': str(area_squared),
                'unit_normal': [component / sqrt(norm_squared) for component in normal], 'unit_normal_z_exact': normal_z,
                'unit_normal_z': normal[2] / sqrt(norm_squared), 'finite_direction_proofs': proofs,
                'eligible_complete_views': open_views,
            }
    require(eligible.keys() == expected.keys() and (components, rectangles) == (87, 84),
            'whole_scene_rectangle_denominator_changed')
    require(eligible['M02']['eligible_complete_views'] == list(oracle['DIRECTIONS'])
            and eligible['M06']['eligible_complete_views'] == []
            and eligible['M09']['eligible_complete_views'] == ['LEFT', 'BACK'], 'finite_direction_truth_changed')
    require(all({hit['object_name'] for hit in proof['positive_area_occluders']} == {'M03'}
                for proof in eligible['M06']['finite_direction_proofs'].values()), 'unknown_blocker_source_changed')
    return eligible, components, rectangles


def frame_pixels(frame, truth, owner_index, offsets, array):
    import numpy as np

    source_ids = [offsets[owner_index] + i for i in truth['source_triangle_indices']]
    owners, triangles, rgb = (array[key] for key in ('owners', 'triangle_ids', 'color'))
    mask = (owners == owner_index) & np.isin(triangles, source_ids)
    require(np.isfinite(array['depth'][mask]).all(), 'owned_surface_depth_missing')
    color = rgb.astype(np.int32)
    edge = np.zeros(mask.shape, dtype=bool)
    for a, b in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[1:, :], np.s_[:-1, :]),
                 (np.s_[:, :-1], np.s_[:, 1:]), (np.s_[:, 1:], np.s_[:, :-1])):
        difference = color[a] - color[b]
        edge[a] |= mask[a] & ~mask[b] & (np.sum(difference * difference, axis=2) >= 24**2)
    pose = frame['pose']
    camera, projection = map(np.asarray, (pose['view_matrix'], pose['projection_matrix']))
    direction = np.array(pose['direction_rational'], dtype=float)
    require(pose['projection'] == 'orthographic' and pose['size_px'] == [512, 512]
            and np.allclose(camera[2, :3], direction / np.linalg.norm(direction), rtol=0.0, atol=1e-9),
            'historical_camera_direction_not_bound')
    points = np.asarray([[*coords, 1.0] for coords in truth['corners_world_m']])
    clip = points @ camera.T @ projection.T
    in_frame = bool(np.all(clip[:, 3] > 0) and np.all(np.abs(clip[:, :3] / clip[:, 3, None]) <= 1 + 1e-8))
    return {'visible_surface_pixels': int(mask.sum()), 'contrasting_boundary_pixels': int(edge.sum()),
            'all_corners_in_frame': in_frame, 'source_triangle_offsets': source_ids}


def historical_frames(runtime, terminal, eligible):
    import numpy as np
    from PIL import Image

    slot = RUNTIME / 'slots/P1'
    original = runtime.json(slot / 'product_full/call_001/SERVICE_RESULT.json')
    rpc = slot / 'mcp/rpc_04'
    request = runtime.json(rpc / 'TX.bin')
    raw = runtime.read(rpc / 'RX.bin')
    inner, receipt = json.loads(raw), runtime.json(rpc / 'RECEIPT.json')
    owner = slot / 'owner/tool_01'
    require(hash_bytes(raw) == receipt['RX_sha256'] and (request['id'], inner['id']) == (receipt['id'], receipt['id'])
            and runtime.json(owner / 'PRODUCT_REQUEST.json') == request
            and runtime.json(owner / 'PRODUCT_RESPONSE.json') == inner
            and runtime.json(owner / 'RESPONSE.json')['result'] == inner['result']
            and not inner['result']['isError'], 'old_production_delivery_changed')
    bindings = original['binding']['objects']
    require([(obj['object_name'], obj['host_id'], obj['instance_id']) for obj in bindings]
            == [(obj['name'], obj['object_id'], obj['instance_id']) for obj in terminal['objects']],
            'old_raster_source_order_changed')
    by_name = {obj['object_name']: obj['object_index'] for obj in bindings}
    selected = {frame['frame_identity']: i for i, frame in enumerate(original['frames'], 1)}
    scopes = {scope['scope_id']: scope for scope in original['scopes']}
    source_rows = {row['object_name']: row for row in original['facts']['region_task']['rows']}
    blocks = inner['result']['content']
    require(len(selected) == len(blocks) - 1 == 3 and len(original['constructed_frames']) == 4,
            'old_constructed_and_delivery_counts_changed')
    require(all(name in source_rows for name in eligible) and source_rows['M06']['complete_witness'] is None
            and source_rows['M06']['reason'] == 'positive_area_occlusion_all_front_views', 'old_observation_unknown_changed')
    require(all(row['complete_witness'] is not None and row['complete_witness']['scope_id'] != 'global'
                for row in (source_rows['M02'], source_rows['M09'])), 'old_observation_local_witnesses_missing')
    frames = []
    for index, frame in enumerate(original['constructed_frames']):
        identity = frame['frame_identity']
        scope = scopes[frame['scope_id']]
        digest = scope['binding']['binding_sha256']
        require(frame['host_binding_sha256'] == digest
                and scope['binding']['camera_identity'] == frame['camera_identity']
                and scope['binding']['capture_state'] == original['binding']['capture_state']
                and scope['frame_refs'].count(identity) == 1, 'historical_frame_scope_changed')
        ordinal = scope['frame_refs'].index(identity) + 1
        block_index = selected.get(identity)
        path, array_path = map(Path, (frame['image_path'], frame['arrays_path']))
        require(path.name.startswith(f'{ordinal:03d}-') and path.parent.name == digest
                and path.with_suffix('.npz') == array_path, 'historical_scope_construction_ordinal_changed')
        png, npz = runtime.read(path), runtime.read(array_path)
        require(hash_bytes(png) == frame['image_sha256'] and hash_bytes(npz) == frame['arrays_sha256'],
                'historical_PNG_or_NPZ_digest_changed')
        if block_index is not None:
            block = blocks[block_index]
            require(block['type'] == 'image' and block['mimeType'] == 'image/png'
                    and base64.b64decode(block['data'], validate=True) == png, 'historical_native_block_mismatch')
        targets = tuple(eligible) if frame['scope_id'] == 'global' else tuple(
            name for name, row in source_rows.items() if row['roi_id'] in frame['patch_roi_ids'])
        require(bool(targets), 'historical_scope_does_not_bind_its_region')
        with Image.open(io.BytesIO(png)) as image, np.load(io.BytesIO(npz), allow_pickle=False) as arrays:
            require(image.format == 'PNG' and image.size == (512, 512)
                    and np.array_equal(np.asarray(image.convert('RGB')), arrays['color'])
                    and arrays['face_patch_offsets'].tolist() == terminal['source_face_offsets']
                    and arrays['owner_mapping_identity'].item() == frame['owner_mapping_identity'],
                    'historical_owned_arrays_or_original_PNG_changed')
            checks = {name: frame_pixels(frame, eligible[name], by_name[name], terminal['source_face_offsets'], arrays)
                      for name in targets}
        for name, check in checks.items():
            witness = source_rows[name]['complete_witness']
            geometry = eligible[name]['finite_direction_proofs'][frame['view_name']]
            require(tuple(frame['pose']['direction_rational']) == geometry['direction'], 'historical_view_contract_changed')
            check['geometry_complete'] = geometry['whole_region_clear']
            check['qualified_complete'] = check['geometry_complete'] and check['all_corners_in_frame'] and (
                check['visible_surface_pixels'] >= 16 and check['contrasting_boundary_pixels'] >= 4)
            if witness is not None and witness['frame_identity'] == identity:
                require(check['qualified_complete'] and block_index is not None
                        and witness['image_ref'] == frame['image_ref'] and witness['scope_id'] == frame['scope_id']
                        and witness['view_name'] == frame['view_name'] and witness['selected_for_delivery'] is True,
                        'historical_qualified_witness_not_delivered')
                pix_index = witness['pixel_row_index']
                observations = [row for row in scope['facts']['observations'] if row['frame_identity'] == identity]
                require(len(observations) == 1 and type(pix_index) is int
                        and 0 <= pix_index < len(observations[0]['pixel_rows']), 'historical_scope_pixel_index_changed')
                pixel = observations[0]['pixel_rows'][pix_index]
                require(pixel['roi_id'] == source_rows[name]['roi_id']
                        and all(check[key] == pixel[key]
                                for key in ('visible_surface_pixels', 'contrasting_boundary_pixels')),
                        'historical_independently_counted_pixels_differ')
        frames.append({
            'constructed_index': index, 'scope_id': frame['scope_id'], 'view': frame['view_name'],
            'scope_sequence': ordinal, 'frame_identity': identity, 'image_ref': frame['image_ref'],
            'PNG': pins(path, png), 'NPZ': pins(array_path, npz),
            'native_content_block_index': block_index, 'pixel_results': checks,
        })
    require([(row['view'], row['scope_sequence'], row['native_content_block_index']) for row in frames]
            == [('SCENE', 1, 1), ('SCENE', 1, 2), ('SCENE', 1, None), ('LEFT', 2, 3)],
            'historical_constructed_only_demonstration_changed')
    return {'label': 'P1', 'constructed': 4, 'selected_and_delivered': 3, 'frames': frames,
            'scope': 'Historical readback and source verification only, not qualification of either new slot.'}


def generate():
    asset_path = FIXTURE / 'main.blend'
    asset = read_bound(asset_path, ASSET_SHA)
    before, after = (FIXTURE / name for name in ('READBACK_BEFORE_SAVE.json', 'READBACK_AFTER_RELOAD.json'))
    saved = read_bound(after, READBACK_SHA)
    require(saved == read_bound(before, READBACK_SHA), 'original_saved_reload_source_changed')
    read_bound(ORACLE, ORACLE_SHA)
    oracle = run_path(str(ORACLE))
    index_file, archive_file = OLD / 'RUNTIME_INDEX.json', RUNTIME / 'ORIGINAL_RUNTIME.zip'
    index = read_bound(index_file, INDEX_SHA)
    archive = read_bound(archive_file, ARCHIVE_SHA)
    with ZipFile(io.BytesIO(archive)) as bundle:
        runtime = OriginalRuntime(json.loads(index), bundle)
        meshes, slots = original_geometry(runtime, json.loads(saved))
        eligible, components, rectangles = exact_truth(meshes, oracle)
        historical = historical_frames(runtime, slots['P1'], eligible)
    prior = read_bound(OLD / 'fixture/CURRENT_TRUTH.json', OLD_TRUTH_SHA)
    for row in json.loads(prior)['eligible']:
        current = eligible[row['object_name']]
        require(current['center_world_m_exact'] == row['center_world_m']
                and all(current[key] == row[key] for key in ('source_triangle_indices', 'eligible_complete_views')),
                'independent_recompute_changed_historical_truth')
    difference = eligible['M02']['area_m2'] - eligible['M09']['area_m2']
    return {
        'schema': 'm1-region-task-witness-image-path-consumption-independent-truth-v1',
        'historical_commit': '9f743878d3a868575c5be43f00a9ba4e011b5161',
        'counts': COUNTS, 'component_count': components, 'rectangles': rectangles,
        'conditions': {'area_min_exact': str(AREA[0]), 'area_max_exact': str(AREA[1]),
                       'oriented_unit_normal_z_min': float(NZ), 'pixel_minimums': [16, 4, 24]},
        'eligible': eligible, 'directions': oracle['DIRECTIONS'],
        'comparison': {'area_larger': 'M02', 'area_smaller': 'M09', 'area_difference_m2_exact': '(4-sqrt(10))/256',
                       'area_difference_m2': difference, 'normal_more_positive_z': 'M02'},
        'historical_scopes': historical,
        'sources': {'asset': pins(asset_path, asset), 'saved_reopened': pins(after, saved), 'index': pins(index_file, index),
                    'archive': pins(archive_file, archive), 'independent_oracle_sha256': ORACLE_SHA,
                    'prior_truth_sha256': OLD_TRUTH_SHA, 'runtime_members_compared': runtime.used},
    }


if __name__ == '__main__':
    sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
    output = HERE / 'TRUTH.json'
    packed = (json.dumps(generate(), ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True) + '\n').encode()
    if sys.argv[1:] == ['--check']:
        require(output.read_bytes() == packed, 'frozen_truth_is_not_reproducible')
    else:
        require(not sys.argv[1:], 'unexpected_truth_arguments')
        with output.open('xb') as stream:
            stream.write(packed)
    print(json.dumps(pins(output, packed)))
