"""Independent measurement and current original-frame scoring for the first-packet task."""

import argparse
import base64
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from math import sqrt
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile


V = Path(__file__).resolve().parents[2]
Q1 = Path('D:/he_m4_cross_scale_live_qualification_001/slots/Q1')
Q1_VERIFICATION = V / 'm4_cross_scale_live_qualification_001'
ASSET_SHA = 'a2d55e9212a84d27489aa72a680092b4e91d94d9df27d29c5de40d8a4ca3d0c6'
Q1_ARCHIVE_SHA = '403b627419d158cee65d658571334ed66071a25e75b4be4be1a21294b4aec5c2'
PNG_SHA = 'b043791f7e0335ed711741202556816d81a501ac5cb4c4b15b86d3bf1c3464ca'
TARGET, REFERENCE = 'Obj_09', 'Obj_04'
SELECTED = (0, 1)
ATTAIN_A = tuple(map(F, ('-33/16', '-3/64', '63/64')))
ATTAIN_B = (F(-4), *ATTAIN_A[1:])
EPS = F('0.00005')
REGION = {
    'object_name': TARGET, 'boundary_loops': [[0, 1, 2, 3]],
    'source_triangle_indices': list(SELECTED), 'plane_normal_integer': (0, -1, 3),
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    raw = path.read_bytes()
    return {'path': path.resolve().as_posix(), 'bytes': len(raw), 'sha256': digest(raw)}


@lru_cache(maxsize=1)
def independent_math():
    return run_path(str(V / 'perf050_dual_region_occlusion_transfer_001/checks/truth.py'))


@lru_cache(maxsize=1)
def source():
    math = independent_math()
    index_path = Q1_VERIFICATION / 'RUNTIME_INDEX.json'
    index = read(index_path)
    zipped = Path(index['archive']['path'])
    zip_pin = pin(zipped)
    require(zip_pin['sha256'] == index['archive']['sha256'] == Q1_ARCHIVE_SHA,
            'historical_Q1_archive_digest_changed')
    entries = {row['path']: row for row in index['files']}
    members = []
    with ZipFile(zipped) as archive:
        require(set(archive.namelist()) == set(entries) and index['file_count'] == len(entries),
                'historical_Q1_entries_changed')

        def member(relative):
            name = 'slots/Q1/' + relative
            raw = archive.read(name)
            local = Q1 / relative
            receipt = pin(local)
            require((len(raw), digest(raw)) == (entries[name]['bytes'], entries[name]['sha256'])
                    == (receipt['bytes'], receipt['sha256']) and raw == local.read_bytes(),
                    'historical_Q1_member_changed/' + name)
            members.append(receipt)
            return raw

        packet = json.loads(member('INDEPENDENT_SCENE.json'))
        require(packet == json.loads(member('raw_sources/live-source-001.json')), 'archived_independent_capture_mismatch')
        geometry = math['meshes'](packet)
        asset = member('native/input.blend')
        require(digest(asset) == packet['source']['asset_sha256'] == ASSET_SHA,
                'asset_or_capture_digest_changed')
        closure = json.loads(member('SLOT_RESULT.json'))
        runtime = json.loads(member('RUNTIME_CLOSE.json'))
        require(closure['status'] == 'completed' and closure['cleanup']['bridge']['confirmed']
                and runtime['Blender_close']['process_reaped'] and runtime['Blender_close']['source_file_unchanged'],
                'archived_Q1_slot_not_completed_and_closed')
        request = json.loads(member('product_calls/call_001/REQUEST.json'))
        response = json.loads(member('product_calls/call_001/RESPONSE.json'))
        producer = json.loads(member('product_full/call_001/SERVICE_RESULT.json'))
        require(request['id'] == response['id'] and not response['result']['isError'],
                'archived_Q1_request_or_response_changed')
        frame, = [item for item in producer['frames'] if item['image_sha256'] == PNG_SHA]
        png_path = Path(frame['image_path']).relative_to(Q1).as_posix()
        npz_path = Path(frame['arrays_path']).relative_to(Q1).as_posix()
        png, arrays = member(png_path), member(npz_path)
        content, = [item for item in response['result']['content']
                    if item['type'] == 'image' and digest(base64.b64decode(item['data'], validate=True)) == PNG_SHA]
        require(base64.b64decode(content['data'], validate=True) == png and digest(png) == PNG_SHA
                and digest(arrays) == frame['arrays_sha256'] and frame['PNG_bytes'] == len(png) == 3600,
                'historical_original_ROI_bytes_changed')
    require(geometry == math['frozen_meshes'](), 'independent_repeated_world_geometry_changed')
    require((len(geometry), sum(len(m['vertices']) for m in geometry.values()),
             sum(len(m['triangles']) for m in geometry.values())) == (9, 54, 56), 'fixture_geometry_counts_changed')
    return {'packet': packet, 'geometry': geometry, 'frame': frame, 'png': png, 'arrays': arrays,
            'pins': {'index': pin(index_path), 'archive': zip_pin, 'members': members}}


def vector(value):
    return independent_math()['vector'](value)


def nearby_faces(point, mesh, ids, tolerance):
    point_oracle, _ = independent_math()['helpers']()
    distance_squared = point_oracle['triangle_distance_squared']
    return [i for i in ids if distance_squared(
        point, tuple(mesh['vertices'][j] for j in mesh['triangles'][i])) <= tolerance * tolerance]


def score_measurement(distance_m, direction, point_a, point_b, tolerance_m=EPS):
    """Check the actual submitted point pair on source triangles as well as the gap."""
    geometry = source()['geometry']
    distance = F(distance_m)
    a, b = vector(point_a), vector(point_b)
    source_faces = nearby_faces(a, geometry[TARGET], SELECTED, tolerance_m)
    reference_faces = nearby_faces(b, geometry[REFERENCE], range(len(geometry[REFERENCE]['triangles'])), tolerance_m)
    delta = tuple(q - p for p, q in zip(a, b, strict=True))
    gap = F(31, 16)
    enough = (gap - tolerance_m)**2 <= sum(d*d for d in delta) <= (gap + tolerance_m)**2
    vector_ok = abs(delta[0] + gap) <= tolerance_m and all(abs(d) <= tolerance_m for d in delta[1:])
    if isinstance(direction, str):
        direction_ok = direction.strip().upper().replace('\u2212', '-') == '-X'
    else:
        d = vector(direction)
        direction_ok = d[0] < 0 and all(abs(axis) <= -d[0]*tolerance_m for axis in d[1:])
    return {
        'distance': abs(distance - gap) <= tolerance_m,
        'direction': direction_ok,
        'actual_surface_points': bool(source_faces and reference_faces and enough and vector_ok),
        'point_a_source_faces': source_faces, 'point_b_source_faces': reference_faces,
        'point_pair_displacement_m': [str(d) for d in delta],
        'report_tolerance_m': str(tolerance_m), 'distance_m': str(distance),
    }


def verify_projection(pose, geometry):
    math = independent_math()
    direction = math['DIRECTIONS'].get(pose['name'])
    require(direction is not None and tuple(pose['direction_rational']) == direction
            and pose['projection'] == 'orthographic', 'view_not_in_registered_forward_pool')
    matrix, transform = [tuple(tuple(F(x) for x in row) for row in pose[key])
                         for key in ('view_matrix', 'projection_matrix')]
    require(all(len(item) == 4 and all(len(row) == 4 for row in item) and item[3] == (0, 0, 0, 1)
                for item in (matrix, transform)), 'bad_current_orthographic_matrices')
    norm = sqrt(sum(d*d for d in direction))
    require(all(abs(float(got) - expected/norm) <= 1e-12
                for got, expected in zip(matrix[2][:3], direction, strict=True)), 'view_matrix_direction_differs')

    def apply(rows, point):
        return tuple(sum(x*y for x, y in zip(row, point, strict=True)) for row in rows)

    ndc = [apply(transform, apply(matrix, point+(F(1),))) for point in geometry[TARGET]['vertices']]
    require(all(point[3] == 1 and all(-1 < c < 1 for c in point[:3]) for point in ndc),
            'current_selected_corners_not_all_in_frame')
    _, projection_oracle = math['helpers']()
    proof = projection_oracle['prove'](list(geometry.values()), REGION, direction)
    require(proof['occluder_triangles_checked'] == 54 and proof['whole_rectangle_geometrically_complete'],
            'current_geometric_complete_witness_unproved')
    return {'view': pose['name'], 'normal_dot_view': proof['front_dot_product'],
            'geometry_complete': True, 'nonselected_triangles_checked': proof['occluder_triangles_checked'],
            'corner_ndc': [[float(c) for c in point[:3]] for point in ndc]}


def pixel_proof(png, raw_arrays, names):
    import numpy as np
    from PIL import Image

    geometry = source()['geometry']
    require(set(names) == set(geometry) and len(names) == len(geometry), 'current_frame_mesh_roster_changed')
    offsets = [0]
    for name in names:
        offsets.append(offsets[-1] + len(geometry[name]['triangles']))
    with np.load(BytesIO(raw_arrays), allow_pickle=False) as arrays:
        rgb, owners, faces, depth = (arrays[key] for key in ('color', 'owners', 'triangle_ids', 'depth'))
        require(arrays['face_patch_offsets'].tolist() == offsets, 'current_triangle_owner_offsets_mismatch')
    with Image.open(BytesIO(png)) as picture:
        require(picture.format == 'PNG' and picture.mode == 'RGB'
                and picture.size == (512, 512) and np.array_equal(np.asarray(picture), rgb),
                'original_PNG_and_frame_rgb_differ')
    visible = owners >= 0
    require(owners.shape == faces.shape == depth.shape == (512, 512)
            and np.issubdtype(owners.dtype, np.signedinteger) and np.issubdtype(faces.dtype, np.signedinteger)
            and np.all(owners >= -1) and np.all(owners < len(names))
            and np.array_equal(visible, faces >= 0)
            and np.all(np.isfinite(depth[visible]) & (depth[visible] > 0)),
            'bad_current_triangle_or_owner_map')
    offsets_np = np.asarray(offsets)
    require(np.all(faces[visible] >= offsets_np[owners[visible]])
            and np.all(faces[visible] < offsets_np[owners[visible]+1]), 'current_face_index_is_outside_its_owner')
    target = names.index(TARGET)
    counts = {str(i): int(np.count_nonzero((owners == target) & (faces == offsets[target]+i))) for i in SELECTED}
    mask = (owners == target) & np.isin(faces, [offsets[target]+i for i in SELECTED])
    boundary = np.zeros(mask.shape, dtype=bool)
    for axis in range(2):
        front = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        back = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        delta = rgb[front].astype(np.int32) - rgb[back].astype(np.int32)
        pair = (mask[front] != mask[back]) & (np.sum(delta*delta, axis=2) >= 24**2)
        boundary[front] |= pair
        boundary[back] |= pair
    surface, contrast = int(np.count_nonzero(mask)), int(np.count_nonzero(mask & boundary))
    require(all(counts.values()) and surface >= 16 and contrast >= 4,
            'current_image_does_not_show_both_triangles_readably')
    return {'source_pixels_by_face': counts, 'selected_surface_pixels': surface,
            'contrasting_boundary_pixels': contrast, 'thresholds': [16, 4, 24]}


def verify_frame(slot_root, frame, binding, original_image_block, *, scene=None):
    """Verify a current source-region producer and its same-slot published original."""
    root = Path(slot_root).resolve(strict=True)
    png, npz = [Path(frame[key]).resolve(strict=True) for key in ('image_path', 'arrays_path')]
    require(png.is_relative_to(root) and npz.is_relative_to(root) and png.suffix == '.png' and npz.suffix == '.npz',
            'current_frame_files_outside_slot')
    source_binding = source()['geometry']
    rows = binding['objects']
    names = [row['object_name'] for row in rows]
    require(frame['host_binding_sha256'] == binding['binding_sha256']
            and frame['source_revision'] == binding['scene_revision']
            and frame['scene_identity'] == binding['geometry_identity']
            and frame['candidate_identity'] == binding['camera_identity']
            and frame['display_identity'] == binding['display_identity']
            and frame['image_scope'] == binding['image_scope']
            and binding['image_scope']['participation_mask'] == [True]*len(names)
            and frame['view_name'] == frame['pose']['name']
            and frame['all_triangle_count'] == 56, 'actual_frame_is_not_from_bound_current_full_display')
    if scene is not None:
        scene = read(Path(scene)) if not isinstance(scene, dict) else scene
        independent_math()['verify_geometry'](scene)
        source_rows = {obj['name']: obj for obj in scene['objects']}
        require(all(row['host_id'] == source_rows[row['object_name']]['object_id']
                    and row['instance_id'] == source_rows[row['object_name']]['instance_id'] for row in rows),
                'actual_frame_objects_do_not_match_independent_current_identities')
    raw_png, raw_npz = png.read_bytes(), npz.read_bytes()
    require(original_image_block['type'] == 'image' and original_image_block['mimeType'] == 'image/png'
            and base64.b64decode(original_image_block['data'], validate=True) == raw_png
            and digest(raw_png) == frame['image_sha256'] and len(raw_png) == frame['PNG_bytes']
            and digest(raw_npz) == frame['arrays_sha256'], 'actual_frame_block_or_arrays_do_not_match_same_slot_files')
    return {**verify_projection(frame['pose'], source_binding), **pixel_proof(raw_png, raw_npz, names),
            'image': pin(png), 'arrays': pin(npz), 'image_ref': frame['image_ref'],
            'frame_identity': frame['frame_identity'], 'independent_current_source_checked': scene is not None}


def load_truth():
    archived = source()
    geometry, frame = archived['geometry'], archived['frame']
    a, b = geometry[TARGET], geometry[REFERENCE]
    a_min, b_max = min(p[0] for p in a['vertices']), max(p[0] for p in b['vertices'])
    require(a_min == F(-33, 16) and b_max == F(-4) and a_min - b_max == F(31, 16)
            and len(a['triangles']) == 2 and len(b['triangles']) == 2, 'incorrect_axis_separation_or_scope')
    grade = score_measurement(F(31, 16), '-X', ATTAIN_A, ATTAIN_B, F(0))
    require(grade['distance'] and grade['direction'] and grade['actual_surface_points'],
            'exact_witness_does_not_attain_analytic_lower_bound')
    math = independent_math()
    _, oracle = math['helpers']()
    origin = a['vertices'][0]
    normal = REGION['plane_normal_integer']
    # The independent projection proof skips coplanar triangles behind the front plane.
    # The nonselected fixture has no triangle in that plane, ruling out positive-area depth ties.
    require(not any(all(sum(axis*(p-q) for axis,p,q in zip(normal, mesh['vertices'][i], origin, strict=True)) == 0
                        for i in face) for name, mesh in geometry.items() if name != TARGET
                    for face in mesh['triangles']), 'nonselected_coplanar_equal_depth_triangle')
    views = {}
    for name, direction in math['DIRECTIONS'].items():
        proof = oracle['prove'](list(geometry.values()), REGION, direction)
        require(proof['whole_rectangle_geometrically_complete'] and proof['occluder_triangles_checked'] == 54,
                'historical_exact_view_completeness_not_proved')
        views[name] = {'forward_dot': proof['front_dot_product'], 'nonselected_triangles': 54,
                       'full_geometric_scope': True}
    names = [row['name'] for row in archived['packet']['objects']]
    pixels = pixel_proof(archived['png'], archived['arrays'], names)
    require(pixels['selected_surface_pixels'] == 71531 and pixels['contrasting_boundary_pixels'] == 928,
            'historical_local_pixel_evidence_changed')
    return {
        'asset_sha256': ASSET_SHA, 'object_count': 9, 'vertex_count': 54, 'triangle_count': 56,
        'target': TARGET, 'source_triangles': list(SELECTED), 'reference_whole_object': REFERENCE,
        'source_min_X_m': str(a_min), 'reference_max_X_m': str(b_max),
        'exact_shortest_distance_m': '31/16', 'exact_world_direction': '-X',
        'one_attaining_pair_m': [[str(c) for c in point] for point in (ATTAIN_A, ATTAIN_B)],
        'exact_pair_classification': grade, 'finite_geometric_views': views,
        'same_depth_coplanar_triangle_count': 0,
        'historical_local_SCENE': {'projection': verify_projection(frame['pose'], geometry), **pixels,
                                   'png_sha256': PNG_SHA, 'bytes': len(archived['png'])},
        'historical_scope': 'old Q1 raster enables preflight; exact image and scope independently reverified per formal slot',
        'source_pins': archived['pins'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    truth = load_truth()
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(truth, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
