"""Independent exact fixture, measurement and visibility audit for the dual-region task."""

import argparse
import base64
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from math import isfinite, sqrt
from pathlib import Path
from runpy import run_path


HERE = Path(__file__).resolve().parent
V = HERE.parents[1]
SLOT = Path('D:/he_m4_cross_scale_live_qualification_001/slots/Q1')
SCENE = SLOT/'INDEPENDENT_SCENE.json'
COMPACT_SOURCE = SLOT/'raw_sources/live-source-001.json'
SAVED = SLOT/'SAVED_EVIDENCE.json'
MEMBERSHIP = V/'m5_observe_measure_001/oracle.py'
WITNESS = V/'m4_cross_scale_discovery_001/oracle/geometry_witness.py'
PLAN = 'af7087b90f39f9269f2d3d28e86a338ccba3a22b'
ASSET_SHA = 'a2d55e9212a84d27489aa72a680092b4e91d94d9df27d29c5de40d8a4ca3d0c6'
TARGETS = ('Obj_02', 'Obj_06')
REFERENCE = 'Obj_03'
SELECTED = (0, 1)
REPORT_TOLERANCE_M = F('0.00005')
DIRECTIONS = {
    'SCENE': (4, -4, 3), 'TOP': (0, 0, 1),
    'LEFT': (-1, 0, 1), 'RIGHT': (1, 0, 1),
    'FRONT': (0, -1, 1), 'BACK': (0, 1, 1),
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path, expected=None):
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    require(expected is None or expected == digest, 'frozen_source_digest_changed/' + str(path))
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest}


def read(path):
    return json.loads(path.read_bytes())


@lru_cache(maxsize=1)
def helpers():
    pin(MEMBERSHIP, '0133b8e69b34e9347cb48cf9220f9a880065f6dc95517e300295afd2c96a9acb')
    pin(WITNESS, '29138a145c6a04bccce7ae950f43e3546efc2d71a533b73105bb4a05277558a0')
    return run_path(str(MEMBERSHIP)), run_path(str(WITNESS))


def vector(value):
    require(type(value) in (list, tuple) and len(value) == 3
            and all(type(axis) in (str, int, float, F) for axis in value), 'finite_three_coordinate_point_required')
    return tuple(F(axis) for axis in value)


def meshes(packet):
    result = {}
    for row in packet['objects']:
        name = row['name']
        evaluated = row.get('evaluated', row)
        vertices = tuple(vector(point) for point in (evaluated.get('vertices_world_m') or evaluated['vertices']))
        triangles = tuple(tuple(face) for face in evaluated['triangles'])
        require(name not in result and all(len(face) == 3 and all(type(i) is int and 0 <= i < len(vertices) for i in face)
                                          for face in triangles), 'invalid_ordered_evaluated_triangle_stream/' + name)
        result[name] = {'name': name, 'vertices': vertices, 'triangles': triangles}
    return result


def geometry_digest(objects):
    canonical = [[name, [[str(axis) for axis in point] for point in mesh['vertices']], mesh['triangles']]
                 for name, mesh in sorted(objects.items())]
    return sha256(json.dumps(canonical, separators=(',', ':')).encode()).hexdigest()


@lru_cache(maxsize=1)
def frozen_meshes():
    pin(SCENE, 'a0f7816e83c852094acaa0c1424bf711c15aa467f1da14ac581d1c213c9392ad')
    pin(COMPACT_SOURCE, '0923bdee507dfa3bd50de144d8fcf6c5ca006130b5f61a58f388e6f0dcf01f19')
    independent, compact = read(SCENE), read(COMPACT_SOURCE)
    require(independent == compact, 'independent_ordered_source_scan_differs_from_raw')
    source = independent['source']
    require(source['asset_sha256'] == ASSET_SHA and source['kind'] == 'actual_owned_Blender_evaluated_mesh'
            and (source['frame'], source['subframe'], source['scale_length']) == (1, 0, 1), 'archived_frame_or_units_changed')
    result = meshes(independent)
    require((len(result), sum(len(m['vertices']) for m in result.values()), sum(len(m['triangles']) for m in result.values()))
            == (9, 54, 56), 'frozen_mesh_counts_changed')
    return result


def verify_geometry(packet, *, require_display=True):
    source = packet['source']
    require(source['asset_sha256'] == ASSET_SHA and (source['frame'], source['subframe'], source['scale_length']) == (1, 0, 1),
            'current_asset_frame_or_units_changed')
    units = source.get('unit_settings')
    require(units is None or units.get('scale_length') == 1, 'current_unit_scale_changed')
    rows = packet['objects']
    object_ids = [obj['object_id'] for obj in rows]
    instances = [obj['instance_id'] for obj in rows]
    require(len(set(object_ids)) == len(set(instances)) == len(rows) == 9 and all(object_ids) and all(instances),
            'ambiguous_current_source_instances')
    if require_display:
        mask = packet['display_object_mask']
        require(isinstance(mask, list) and len(mask) == 9 and all(value is True for value in mask)
                and all(row.get('visible_get', True) is True for row in rows), 'current_display_not_complete')
    actual = meshes(packet)
    require(actual == frozen_meshes(), 'current_world_geometry_changed')
    return {'passed': True, 'asset_sha256': ASSET_SHA, 'object_count': 9, 'vertex_count': 54, 'triangle_count': 56,
            'geometry_sha256': geometry_digest(actual),
            'object_ids_and_instances': dict(zip(object_ids, instances, strict=True)),
            'display_checked': require_display}


def rectangle(mesh, ids, *, positive_front=False):
    faces = [mesh['triangles'][i] for i in ids]
    used = set(faces[0]) | set(faces[1])
    flat = [mesh['vertices'][i] for i in used]
    xs, ys, zs = (sorted({p[axis] for p in flat}) for axis in range(3))
    require(len(used) == 4 and len(xs) == len(ys) == 2 and len(zs) == 1 and
            set(flat) == {(x, y, zs[0]) for x in xs for y in ys}, 'non_rectangular_independent_fixture/' + mesh['name'])
    shared = [mesh['vertices'][i] for i in set(faces[0]) & set(faces[1])]
    require(len(shared) == 2 and shared[0][0] != shared[1][0] and shared[0][1] != shared[1][1],
            'triangles_do_not_partition_rectangle_along_its_diagonal/' + mesh['name'])
    if positive_front:
        for face in faces:
            a, b, c = (mesh['vertices'][i] for i in face)
            require((b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]) > 0,
                    'target_is_not_positive_facing/' + mesh['name'])
    corners = [(xs[0], ys[0], zs[0]), (xs[1], ys[0], zs[0]), (xs[1], ys[1], zs[0]), (xs[0], ys[1], zs[0])]
    return xs, ys, zs[0], corners, [mesh['vertices'].index(point) for point in corners]


def measure_truth(name):
    require(name in TARGETS, 'unsupported_scoring_selection')
    source = frozen_meshes()
    x, y, z, _, _ = rectangle(source[name], SELECTED, positive_front=True)
    rx, ry, rz, _, _ = rectangle(source[REFERENCE], SELECTED)
    require(min(point[2] for point in source[REFERENCE]['vertices']) == rz > z
            and all(rx[0] <= p[0] <= rx[1] and ry[0] <= p[1] <= ry[1] for p in source[REFERENCE]['vertices']),
            'reference_not_above_its_asserted_bottom_rectangle')
    def clamp(value,bounds):
        return min(max(value,bounds[0]),bounds[1])
    a = (clamp(rx[0], x), clamp(ry[0], y), z)
    b = (clamp(a[0], rx), clamp(a[1], ry), rz)
    gaps = (max(F(0), rx[0]-x[1], x[0]-rx[1]), max(F(0), ry[0]-y[1], y[0]-ry[1]), rz-z)
    lower = sum(gap*gap for gap in gaps)
    require(lower == sum((p-q)**2 for p,q in zip(a,b,strict=True)), 'chosen_fixture_witness_fails_exact_lower_bound')
    return lower, a, b, gaps


def qualify_measurement(name, distance, a, b):
    low, _, _, _ = measure_truth(name)
    point_math, _ = helpers()
    selection = frozen_meshes()[name]
    other = frozen_meshes()[REFERENCE]
    eps = REPORT_TOLERANCE_M
    try:
        reported = float(distance)
        require(type(distance) is not bool and isfinite(reported) and reported >= 0, 'finite_nonnegative_distance_required')
        a, b = vector(a), vector(b)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return {'passed': False, 'object_name': name, 'distance_passed': False,
                'point_a_source_triangles': [], 'point_b_source_triangles': [], 'witness_distance_passed': False}
    distance_ok = abs(reported-sqrt(low)) <= float(eps)
    triangle_d2 = point_math['triangle_distance_squared']
    a_faces = [i for i in SELECTED if triangle_d2(a, tuple(selection['vertices'][j] for j in selection['triangles'][i])) <= eps*eps]
    b_faces = [i for i, face in enumerate(other['triangles']) if triangle_d2(b, tuple(other['vertices'][j] for j in face)) <= eps*eps]
    witness_distance = sqrt(sum((p-q)**2 for p,q in zip(a,b,strict=True)))
    witness_ok = abs(witness_distance-sqrt(low)) <= float(eps) and abs(witness_distance-reported) <= float(eps)
    return {'passed': bool(distance_ok and a_faces and b_faces and witness_ok), 'object_name': name, 'distance_passed': distance_ok,
            'point_a_source_triangles': a_faces, 'point_b_source_triangles': b_faces, 'witness_distance_passed': witness_ok,
            'reported_distance_m': reported, 'witness_distance_m': witness_distance, 'truth_distance_squared_m2': str(low)}


def occlusion_proof(packet=None):
    if packet is not None:
        verify_geometry(packet)
    geometry = frozen_meshes()
    _, _, z, corners, _ = rectangle(geometry['Obj_06'], SELECTED, positive_front=True)
    bx, by, bz, _, _ = rectangle(geometry[REFERENCE], SELECTED)
    results = {}
    for name,(dx,dy,dz) in DIRECTIONS.items():
        depth = (bz-z)/dz
        projected = [(x+depth*dx, y+depth*dy, bz) for x,y,_ in corners]
        margin = min(min(x-bx[0], bx[1]-x, y-by[0], by[1]-y) for x,y,_ in projected)
        require(depth > 0 and margin > 0, 'invalid_whole_rectangle_occlusion_proof/' + name)
        results[name] = {'view': name, 'direction': [dx,dy,dz], 'ray_parameter_to_cover': str(depth),
            'min_clearance_inside_cover_xy_m': str(margin),
            'cover_plane_intersections_m': [[str(c) for c in point] for point in projected],
            'fully_occluded': True}
    return {'passed': True, 'target': 'Obj_06', 'selected_indices': list(SELECTED), 'blocker': REFERENCE,
            'blocker_bottom_surface_triangle_indices': [0,1],
            'reason': 'positive depth and strict convex containment in actual cover bottom rectangle for each registered view',
            'views': results}


def verify_projection(frame, target):
    """Require geometric completeness and inclusion in the actual orthographic frame."""
    geometry = frozen_meshes()
    _, _, _, corners, ids = rectangle(geometry[target], SELECTED, positive_front=True)
    pose = frame.get('pose') or frame['producer']['pose']
    reported = frame.get('view_name', frame.get('view'))
    name = pose['name']
    direction = DIRECTIONS.get(name)
    require(direction is not None and reported == name and tuple(pose['direction_rational']) == direction
            and pose['projection'] == 'orthographic', 'unregistered_evidence_view')
    view = tuple(tuple(F(axis) for axis in row) for row in pose['view_matrix'])
    project = tuple(tuple(F(axis) for axis in row) for row in pose['projection_matrix'])
    require(len(view) == len(project) == 4 and all(len(row) == 4 for row in (*view,*project))
            and view[3] == project[3] == (0,0,0,1), 'invalid_orthographic_view_or_projection')
    n = sqrt(sum(axis*axis for axis in direction))
    require(all(abs(float(value)-axis/n)<1e-12 for value,axis in zip(view[2][:3],direction,strict=True)),
            'advertised_direction_differs_from_view_matrix')
    def mul(rows, point):
        return tuple(sum(x*y for x,y in zip(row,point,strict=True)) for row in rows)
    ndc = [mul(project,mul(view, point+(F(1),))) for point in corners]
    require(all(p[3] == 1 and all(-1 < axis < 1 for axis in p[:3]) for p in ndc), 'selected_rectangle_not_fully_in_frame')
    _, visibility = helpers()
    proof = visibility['prove'](list(geometry.values()), {'object_name': target, 'boundary_loops': [ids],
        'source_triangle_indices': list(SELECTED), 'plane_normal_integer': (0,0,1)}, direction)
    return {'passed': True, 'view': name, 'direction': list(direction), 'geometrically_unoccluded': proof['whole_rectangle_geometrically_complete'],
        'nonselected_triangles_checked': proof['occluder_triangles_checked'],
        'ndc_corners': [[float(c) for c in point[:3]] for point in ndc]}


def verify_image(slot_root, frame, *, target='Obj_02', packet=None, image_block=None):
    """Validate an existing original local PNG against its triangle-owner evidence."""
    import numpy as np
    from PIL import Image

    slot_root = Path(slot_root).resolve(strict=True)
    proof = verify_projection(frame, target)
    mapped = frame['object_names']
    geometry = frozen_meshes()
    require(len(mapped) == len(geometry) and set(mapped) == set(geometry), 'incomplete_or_duplicate_frame_object_roster')
    offsets = [0]
    for name in mapped:
        offsets.append(offsets[-1]+len(geometry[name]['triangles']))
    require(offsets == frame['source_face_offsets'], 'actual_frame_source_triangle_map_changed')
    if packet is not None:
        verify_geometry(packet)
        rows = {row['name']: row for row in packet['objects']}
        require(frame.get('object_ids') == [rows[name]['object_id'] for name in mapped]
                and frame.get('object_instance_ids') == [rows[name]['instance_id'] for name in mapped]
                and frame['display_object_mask'] == [True]*len(mapped), 'frame_identity_or_display_not_current')
    png = Path(frame['PNG']).resolve(strict=True)
    npz = Path(frame['NPZ']).resolve(strict=True)
    require(png.is_relative_to(slot_root) and npz.is_relative_to(slot_root)
            and png.suffix.lower() == '.png' and npz.suffix.lower() == '.npz', 'frame_artifact_outside_current_slot')
    p_pin, a_pin = pin(png, frame['PNG_sha256']), pin(npz, frame['NPZ_sha256'])
    raw = png.read_bytes()
    if image_block is not None:
        require(image_block.get('type') == 'image' and image_block.get('mimeType') == 'image/png'
                and base64.b64decode(image_block['data'], validate=True) == raw, 'published_image_not_same_original_png')
    with np.load(npz, allow_pickle=False) as archive:
        color, owners, triangles, depth = (archive[name] for name in ('color','owners','triangle_ids','depth'))
        if 'face_patch_offsets' in archive.files:
            require(archive['face_patch_offsets'].tolist() == offsets, 'NPZ_source_triangle_offsets_changed')
    with Image.open(BytesIO(raw)) as image:
        require(image.format == 'PNG' and image.mode == 'RGB' and image.size == (512,512)
                and color.dtype == np.uint8 and np.array_equal(np.asarray(image), color), 'PNG_bytes_do_not_match_archive_rgb')
    require(owners.shape == triangles.shape == depth.shape == (512,512)
            and np.issubdtype(owners.dtype,np.signedinteger) and np.issubdtype(triangles.dtype,np.signedinteger)
            and np.all(owners >= -1) and np.all(owners < len(mapped)) and np.array_equal(owners >= 0, triangles >= 0),
            'invalid_frame_owner_arrays')
    fg = owners >= 0
    base = np.asarray(offsets)
    require(np.all(triangles[fg] >= base[owners[fg]]) and np.all(triangles[fg] < base[owners[fg]+1])
            and np.all(np.isfinite(depth[fg]) & (depth[fg] > 0)), 'triangle_and_depth_do_not_match_owner')
    obj = mapped.index(target)
    counts = {str(i): int(np.count_nonzero((owners==obj)&(triangles==offsets[obj]+i))) for i in SELECTED}
    mask = (owners==obj)&np.isin(triangles,[offsets[obj]+i for i in SELECTED])
    boundary = np.zeros(mask.shape, dtype=bool)
    for vertical in (True,False):
        a = (slice(None,-1),slice(None)) if vertical else (slice(None),slice(None,-1))
        b = (slice(1,None),slice(None)) if vertical else (slice(None),slice(1,None))
        diff = color[a].astype(np.int32)-color[b].astype(np.int32)
        edge = (mask[a]!=mask[b])&(np.sum(diff*diff,axis=2)>=24**2)
        boundary[a] |= edge
        boundary[b] |= edge
    pixels, contrast = sum(counts.values()), int(np.count_nonzero(mask&boundary))
    require(all(counts.values()) and pixels >= 16 and contrast >= 4, 'inadequate_complete_readable_original_evidence')
    return {**proof, 'target': target, 'path': str(png),'sha256': p_pin['sha256'],'bytes': p_pin['bytes'],'image': p_pin,'arrays': a_pin,
            'ref': frame.get('ref',frame.get('image_ref')),'surface_pixels': pixels,'boundary_pixels': contrast,
            'contrast_boundary_pixels': contrast,'per_face_pixels': counts,'object_ids_checked': packet is not None,
            'opaque_image_block_verified': image_block is not None}


def canonical_truth():
    saved = read(SAVED)
    require(saved['asset_sha256'] == ASSET_SHA and saved['label'] == 'Q1', 'wrong_historical_saved_frame_source')
    image = verify_image(SLOT, saved['frames'][1])
    require(image['surface_pixels'] == 50557 and image['boundary_pixels'] == 926
            and image['sha256'] == '33e798129d7352ddc9eaa01ee3998e22ab221a79e8e71f1b7d3940cbf8b43341',
            'historical_local_pixel_geometry_changed')
    import numpy as np
    global_frame = saved['frames'][0]
    g_path = Path(global_frame['NPZ'])
    g_pin = pin(g_path, global_frame['NPZ_sha256'])
    index = global_frame['object_names'].index('Obj_02')
    offsets = global_frame['source_face_offsets']
    with np.load(g_path,allow_pickle=False) as g:
        global_pixels = int(np.count_nonzero((g['owners']==index)&np.isin(g['triangle_ids'],[offsets[index]+i for i in SELECTED])))
    require(global_pixels == 1, 'historical_global_target_count_changed')
    measurements = {}
    for name in TARGETS:
        d2, a, b, gaps = measure_truth(name)
        grade = qualify_measurement(name, sqrt(d2), a, b)
        require(grade['passed'], 'analytic_attaining_point_not_on_triangles')
        measurements[name] = {'source_triangle_indices': list(SELECTED),'distance_squared_m2': str(d2),'distance_m': sqrt(d2),
            'exact_witness_a': [str(x) for x in a],'exact_witness_b': [str(x) for x in b],
            'nonnegative_axis_gap_lower_bound_m': [str(x) for x in gaps],
            'attainment_a_source_triangles': grade['point_a_source_triangles'],
            'attainment_b_source_triangles': grade['point_b_source_triangles']}
    return {'schema':'perf050-dual-region-independent-truth-v1','passed':True,'plan_git':PLAN,
            'source_pins': {'asset': pin(SLOT/'native/input.blend', ASSET_SHA),'independent_scan': pin(SCENE),
                'raw_capture': pin(COMPACT_SOURCE),'saved_evidence': pin(SAVED,'62c0135883b6eb5ca4e778f83a9bc40fab917e00fc6504df4c8676eb33093b3b'),
                'slot_result': pin(SLOT/'SLOT_RESULT.json','b6c42d4b4008985c3ade19a8f7a6f6c5869a9b56ce9c77d93b21cad6bdb7f6fb'),
                'oracle': pin(Path(__file__).resolve()),'triangle_distance': pin(MEMBERSHIP),'directional_surface': pin(WITNESS),
                'global_npz': g_pin,'local_png': image['image'],'local_npz': image['arrays']},
            'capture': verify_geometry(read(SCENE),require_display=False),'qualification_scope':'private historical Q1 evidence with no model calls',
            'reference_object': REFERENCE,'report_tolerance_m': str(REPORT_TOLERANCE_M),'measurements': measurements,
            'six_forward_directions': {name:list(v) for name,v in DIRECTIONS.items()},'occlusion': occlusion_proof(),
            'historical_Obj_02_local_frame': image,'historical_Obj_02_global_selected_pixels': global_pixels,
            'diagnostic_local_view': {'direction':'SCENE','target_world_m':[0,0,1],'view_span_m':0.1944543648263006}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    answer = canonical_truth()
    with args.output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(answer,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': answer['passed'],'geometry_sha256': answer['capture']['geometry_sha256'],
                      'truth_sha256': pin(args.output)['sha256']}))
