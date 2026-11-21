"""Independent source-geometry and image witness checks for the new task."""

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
ASSEMBLY = V / 'm4_cross_scale_assembly_transfer_001'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
SOURCE_SHA = 'd0d2294f5e5fe006d2f3f23deaf34290dba696b39424585b7cd5e4494d8ffa90'
ARCHIVE_SHA = 'bf7be101396593b151411e567b05af32e0e0754ac18dc733a6a10191fcae3627'
TARGET, REFERENCE = 'N26', 'N07'
SELECTED = (4, 5)
REGION = {'object_name': TARGET, 'boundary_loops': [[0, 4, 5, 1]],
          'source_triangle_indices': list(SELECTED), 'plane_normal_integer': (0, -1, 0)}
EXACT = {'selected': F('21474841/1073741824'), 'whole': F('6442455/1073741824')}
EPS = F('0.00005')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path)
    raw = path.read_bytes()
    return {'path': path.resolve().as_posix(), 'bytes': len(raw), 'sha256': digest(raw)}


@lru_cache(maxsize=1)
def independent_math():
    return run_path(str(V / 'perf050_dual_region_occlusion_transfer_001/checks/truth.py'))


@lru_cache(maxsize=1)
def source():
    index_path = ASSEMBLY / 'RUNTIME_INDEX.json'
    index = read(index_path)
    archive_path = Path(index['archive']['path'])
    archive_pin = pin(archive_path)
    require(archive_pin['sha256'] == index['archive']['sha256'] == ARCHIVE_SHA
            and archive_pin['bytes'] == index['archive']['bytes'], 'historical_source_archive_digest_changed')
    members = {row['path']: row for row in index['files']}
    proof = []
    with ZipFile(archive_path) as z:
        require(set(z.namelist()) == set(members) and len(members) == index['count'], 'historical_archive_roster_changed')

        def take(relative):
            name = 'slots/P1/' + relative
            raw = z.read(name)
            local = archive_path.parent / name
            expected = members[name]
            require((len(raw), digest(raw)) == (expected['bytes'], expected['sha256'])
                    and raw == local.read_bytes(), 'historical_member_digest_changed/' + name)
            proof.append({'member': name, 'actual': pin(local)})
            return raw

        asset = take('native/input.blend')
        terminal = take('TERMINAL_SOURCE.json')
        require(digest(asset) == ASSET_SHA and digest(terminal) == SOURCE_SHA, 'historical_fixed_asset_or_terminal_changed')
        packet = json.loads(terminal)
        before = json.loads(take('initial_capture/TERMINAL_SOURCE.json'))
        result = json.loads(take('SLOT_RESULT.json'))
        require(result['status'] == 'completed' and result['closure_verification']['passed'],
                'historical_source_slot_did_not_close_safely')
    math = independent_math()
    geometry = math['meshes'](packet)
    require(geometry == math['meshes'](before), 'historical_evaluated_geometry_changed_during_slot')
    require((len(geometry), sum(len(x['vertices']) for x in geometry.values()),
             sum(len(x['triangles']) for x in geometry.values())) == (28, 416, 744),
            'historical_source_counts_changed')
    return {'packet': packet, 'geometry': geometry, 'pins': {
        'index': pin(index_path), 'archive': archive_pin, 'members': proof}}


def verify_source(packet):
    """Require the actual independently captured source, units, and display participation."""
    scene = read(packet) if not isinstance(packet, dict) else packet
    stamp = scene['source']
    require(stamp['asset_sha256'] == ASSET_SHA and stamp['kind'] == 'actual_owned_Blender_evaluated_mesh'
            and (stamp['frame'], stamp['subframe'], stamp['scale_length']) == (1, 0, 1)
            and stamp['unit_settings']['scale_length'] == 1, 'live_fixture_asset_frame_or_world_units_changed')
    rows = scene['objects']
    ids, instances = ([row[key] for row in rows] for key in ('object_id', 'instance_id'))
    require(len(set(ids)) == len(set(instances)) == len(rows) == 28 and all(ids) and all(instances)
            and scene['display_object_mask'] == [True]*len(rows)
            and all(row['visible_get'] is True for row in rows), 'live_current_identity_or_display_incomplete')
    math = independent_math()
    fresh = math['meshes'](scene)
    require(fresh == source()['geometry'], 'live_evaluated_geometry_differs_from_fixed_source')
    return {'asset_sha256': stamp['asset_sha256'], 'ordered_geometry_comparison': True,
            'full_display': True, 'instances': dict(zip(ids, instances, strict=True)),
            'geometry_sha256': math['geometry_digest'](fresh)}


def nearest_faces(point, mesh, face_ids, tolerance):
    point_oracle, _ = independent_math()['helpers']()
    distance_squared = point_oracle['triangle_distance_squared']
    return [i for i in face_ids if distance_squared(point, tuple(
        mesh['vertices'][j] for j in mesh['triangles'][i])) <= tolerance*tolerance]


def score_measurement(scope, distance_m, direction, point_a, point_b, tolerance_m=EPS):
    """Accept any real point pair that attains the corresponding exact scoped bound."""
    expected = EXACT[scope]
    reported = F(distance_m) if distance_m is not None else None
    vector = independent_math()['vector']
    if isinstance(direction, str):
        direction_ok = direction.strip().upper() in ('+Y', 'Y+')
    else:
        d = vector(direction) if direction is not None else (0, 0, 0)
        direction_ok = d[1] > 0 and all(abs(d[axis]) <= d[1]*tolerance_m for axis in (0, 2))
    target, reference = (source()['geometry'][key] for key in (TARGET, REFERENCE))
    a_faces, b_faces, delta = [], [], None
    if point_a is not None and point_b is not None:
        a, b = vector(point_a), vector(point_b)
        a_faces = nearest_faces(a, target, SELECTED if scope == 'selected' else range(len(target['triangles'])), tolerance_m)
        b_faces = nearest_faces(b, reference, range(len(reference['triangles'])), tolerance_m)
        delta = tuple(q-p for p, q in zip(a, b, strict=True))
        displacement = sum(d*d for d in delta)
        gap_attained = (expected-tolerance_m)**2 <= displacement <= (expected+tolerance_m)**2
        direction_consistent = abs(delta[1]-expected) <= tolerance_m and all(abs(delta[axis]) <= tolerance_m for axis in (0,2))
    else:
        gap_attained = direction_consistent = False
    return {
        'scope': scope, 'reported_distance_m': str(reported) if reported is not None else None,
        'exact_distance_m': str(expected), 'tolerance_m': str(tolerance_m),
        'distance_correct': reported is not None and abs(reported-expected) <= tolerance_m,
        'world_direction_correct': direction_ok,
        'actual_attaining_pair': bool(a_faces and b_faces and gap_attained and direction_consistent),
        'point_a_evaluated_faces': a_faces, 'point_b_evaluated_faces': b_faces,
        'pair_displacement_m': [str(d) for d in delta] if delta is not None else None,
    }


def verify_projection(pose, geometry=None):
    geometry = source()['geometry'] if geometry is None else geometry
    math = independent_math()
    direction = math['DIRECTIONS'].get(pose['name'])
    require(pose['name'] in ('SCENE', 'FRONT') and tuple(pose['direction_rational']) == direction
            and pose['projection'] == 'orthographic', 'unregistered_or_nonforward_current_view')
    view, projection = [tuple(tuple(F(x) for x in row) for row in pose[key])
                        for key in ('view_matrix', 'projection_matrix')]
    require(all(len(m) == 4 and all(len(row) == 4 for row in m) and m[3] == (0,0,0,1)
                for m in (view, projection)), 'malformed_render_matrices')
    norm = sqrt(sum(d*d for d in direction))
    require(all(abs(float(actual)-axis/norm) <= 1e-12 for actual,axis in zip(view[2][:3],direction,strict=True)),
            'render_matrix_and_reported_view_disagree')
    vertices = geometry[TARGET]['vertices']
    signs = lambda matrix, point: tuple(sum(x*y for x,y in zip(row,point,strict=True)) for row in matrix)
    ndc = [signs(projection, signs(view, vertices[i]+(F(1),))) for i in REGION['boundary_loops'][0]]
    require(all(row[3] == 1 and all(-1 < coordinate < 1 for coordinate in row[:3]) for row in ndc),
            'one_or_more_selected_corners_outside_image')
    _, oracle = math['helpers']()
    proof = oracle['prove'](list(geometry.values()), REGION, direction)
    require(proof['whole_rectangle_geometrically_complete'] and proof['occluder_triangles_checked'] == 742,
            'current_complete_geometry_not_proved')
    return {'view': pose['name'], 'finite_world_direction': list(direction), 'geometry_complete': True,
            'other_triangles_checked': proof['occluder_triangles_checked'],
            'clip_space_corners': [[float(x) for x in row[:3]] for row in ndc]}


def offsets(names):
    geometry = source()['geometry']
    require(len(names) == len(geometry) and set(names) == set(geometry), 'current_owner_directory_does_not_cover_assembly')
    result = [0]
    for name in names:
        result.append(result[-1]+len(geometry[name]['triangles']))
    return result


def pixel_proof(raw_png, raw_npz, names):
    import numpy as np
    from PIL import Image

    source_offsets = offsets(names)
    with np.load(BytesIO(raw_npz), allow_pickle=False) as a:
        rgb, owner, triangle, depth = (a[name] for name in ('color', 'owners', 'triangle_ids', 'depth'))
        require(a['face_patch_offsets'].tolist() == source_offsets, 'archived_triangle_offsets_disagree_with_meshes')
    with Image.open(BytesIO(raw_png)) as picture:
        require(picture.format == 'PNG' and picture.mode == 'RGB' and np.array_equal(np.asarray(picture), rgb),
                'image_pixels_are_not_the_bound_rgb_array')
    require(rgb.dtype == np.uint8 and owner.shape == triangle.shape == depth.shape == rgb.shape[:2]
            and np.issubdtype(owner.dtype, np.signedinteger) and np.issubdtype(triangle.dtype, np.signedinteger)
            and np.all(owner >= -1) and np.all(owner < len(names))
            and np.array_equal(owner >= 0, triangle >= 0), 'invalid_pixel_owner_and_face_arrays')
    fg = owner >= 0
    by_owner = np.asarray(source_offsets)
    require(np.all(triangle[fg] >= by_owner[owner[fg]]) and np.all(triangle[fg] < by_owner[owner[fg]+1])
            and np.all(np.isfinite(depth[fg]) & (depth[fg] > 0)), 'one_or_more_pixels_detached_from_evaluated_triangle')
    index = names.index(TARGET)
    indices = [source_offsets[index]+i for i in SELECTED]
    counts = {str(i): int(np.count_nonzero((owner == index) & (triangle == j))) for i,j in zip(SELECTED,indices,strict=True)}
    mask = (owner == index) & np.isin(triangle, indices)
    boundary = np.zeros(mask.shape, dtype=bool)
    for axis in range(2):
        front = (slice(None,-1),slice(None)) if axis == 0 else (slice(None),slice(None,-1))
        back = (slice(1,None),slice(None)) if axis == 0 else (slice(None),slice(1,None))
        delta = rgb[front].astype(np.int32)-rgb[back].astype(np.int32)
        edge = (mask[front] != mask[back]) & (np.sum(delta*delta,axis=2) >= 24**2)
        boundary[front] |= edge
        boundary[back] |= edge
    pixels, contrast = int(np.count_nonzero(mask)), int(np.count_nonzero(mask&boundary))
    require(all(counts.values()) and pixels >= 16 and contrast >= 4,
            'current_png_lacks_surface_samples_or_contrasting_boundaries')
    return {'surface_by_evaluated_triangle': counts, 'selected_surface_pixels': pixels,
            'contrasting_boundary_pixels': contrast, 'thresholds': [16, 4, 24]}


def verify_frame(slot_root, frame, binding, original_image_block, *, scene):
    """Audit the product's exact current frame, same-slot PNG and original MCP image."""
    root = Path(slot_root).resolve(strict=True)
    png, npz = [Path(frame[key]).resolve(strict=True) for key in ('image_path','arrays_path')]
    require(png.is_relative_to(root) and npz.is_relative_to(root) and png.suffix == '.png' and npz.suffix == '.npz',
            'render_artifact_is_outside_its_current_slot')
    scene = read(scene) if not isinstance(scene, dict) else scene
    verify_source(scene)
    real = {row['name']: row for row in scene['objects']}
    rows = binding['objects']
    names = [row['object_name'] for row in rows]
    require(all(row['host_id'] == real[row['object_name']]['object_id'] and
                row['instance_id'] == real[row['object_name']]['instance_id'] for row in rows)
            and frame['host_binding_sha256'] == binding['binding_sha256']
            and frame['source_revision'] == binding['scene_revision']
            and frame['scene_identity'] == binding['geometry_identity']
            and frame['candidate_identity'] == binding['camera_identity']
            and frame['display_identity'] == binding['display_identity']
            and frame['image_scope'] == binding['image_scope']
            and frame['view_name'] == frame['pose']['name']
            and frame['all_triangle_count'] == 744
            and binding['image_scope']['participation_mask'] == [True]*len(names),
            'frame_does_not_match_current_full_scope_and_binding')
    raw_png, raw_npz = png.read_bytes(), npz.read_bytes()
    require(original_image_block['type'] == 'image' and original_image_block['mimeType'] == 'image/png'
            and base64.b64decode(original_image_block['data'],validate=True) == raw_png
            and digest(raw_png) == frame['image_sha256'] and len(raw_png) == frame['PNG_bytes']
            and digest(raw_npz) == frame['arrays_sha256'], 'original_image_or_arrays_do_not_match_live_frame')
    return {**verify_projection(frame['pose']), **pixel_proof(raw_png,raw_npz,names),
            'image': pin(png), 'arrays': pin(npz), 'image_ref': frame['image_ref'],
            'frame_identity': frame['frame_identity']}


def load_truth():
    frozen = source()
    verify_source(frozen['packet'])
    g = frozen['geometry']
    a, b = g[TARGET], g[REFERENCE]
    selected_vertices = {a['vertices'][i] for face in SELECTED for i in a['triangles'][face]}
    selected_y, = {point[1] for point in selected_vertices}
    y_max, y_ref = max(p[1] for p in a['vertices']), min(p[1] for p in b['vertices'])
    output = {}
    for scope,y in (('selected',selected_y),('whole',y_max)):
        require(y_ref-y == EXACT[scope] > 0, 'incorrect_exact_axis_lower_bound/' + scope)
        p,q = (F(-1,8),y,F(1,2)),(F(-1,8),y_ref,F(1,2))
        proof = score_measurement(scope, EXACT[scope], '+Y', p, q, F(0))
        require(proof['actual_attaining_pair'], 'exact_attainment_pair_not_on_required_surfaces/' + scope)
        output[scope] = {'source_y_upper_bound_m': str(y), 'reference_y_lower_bound_m': str(y_ref),
                         'exact_distance_m': str(EXACT[scope]), 'direction_world': '+Y',
                         'one_attaining_point_pair_m': [[str(c) for c in point] for point in (p,q)],
                         'exact_point_membership': proof}
    math = independent_math()
    _,oracle = math['helpers']()
    aperture = {}
    for name,direction in math['DIRECTIONS'].items():
        facing = -direction[1]
        row = {'direction_world': direction, 'front_normal_dot': facing}
        if facing > 0:
            proof = oracle['prove'](list(g.values()), REGION, direction)
            require(proof['whole_rectangle_geometrically_complete'] and proof['occluder_triangles_checked'] == 742,
                    'required_forward_candidate_not_complete/' + name)
            row.update(geometry_complete=True, other_triangles_checked=742)
        else:
            row['geometry_complete'] = False
            row['reason'] = 'edge_on' if facing == 0 else 'back_facing'
        aperture[name] = row
    # Coincident nonselected triangles touching the same plane along an edge are allowed.
    # No nonselected triangle lies entirely in the selected plane in this capture.
    require(not any(all(mesh['vertices'][i][1] == selected_y for i in face)
                    for name,mesh in g.items() for index,face in enumerate(mesh['triangles'])
                    if name != TARGET or index not in SELECTED), 'equal_depth_coplanar_candidate_needs_independent_check')
    return {'asset_sha256': ASSET_SHA, 'terminal_source_sha256': SOURCE_SHA, 'counts': [28,416,744],
            'target': TARGET, 'selected_evaluated_triangles': list(SELECTED), 'reference_whole': REFERENCE,
            'distances': output, 'finite_views': aperture, 'source_pins': frozen['pins'],
            'view_evidence_contract': 'source geometry prequalifies directions only; each formal slot must show its own PNG'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    evidence = load_truth()
    with args.output.open('x', encoding='utf-8', newline='\n') as file:
        file.write(json.dumps(evidence, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
