"""Exact two-scope truth and partial current-frame oracle for the holdout."""

import argparse
import base64
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from math import sqrt
from pathlib import Path
import re
from runpy import run_path


V = Path(__file__).resolve().parents[2]
OLD_TRUTH = V / 'perf050_source_scope_rank_transfer_recovery_001/checks/truth.py'
DIRECTIONS = {
    'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1),
    'RIGHT': (1, 0, 1), 'FRONT': (0, -1, 1), 'BACK': (0, 1, 1),
}
ASSET_SHA = 'b9cf3671bc8cd5b88ed23118f229a6e753eda40802d35a3ad297961e0a9edcf9'
READBACK_SHA = '70baebb4994c57a13c145a79627abb0671aafb161f4837e793ac869e6fd9c62c'
TARGET, REFERENCE = 'Obj_08', 'Obj_04'
BOTTOM, SIDE = (0, 1), (8, 9)
SELECTED = BOTTOM + SIDE
EXACT_SQUARED = {'selected': F(14978, 256), 'whole': F(14753, 256)}
ATTAIN_B = (F(-4), F(-1,16), F(15,16))
ATTAIN = {'selected': (F(3), F(-3), F(0)), 'whole': (F(3), F(-3), F(15,16))}
SIDE_RECTANGLE = {'object_name': TARGET, 'boundary_loops': [[1,2,6,5]], 'source_triangle_indices': list(SIDE),
                  'plane_normal_integer': (1,0,0)}
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
def source():
    old = run_path(str(OLD_TRUTH))
    meshes, pins = old['frozen_meshes']()
    require(pins['asset']['sha256'] == ASSET_SHA == old['ASSET_SHA']
            and pins['readback_after_reload']['sha256'] == READBACK_SHA == old['READBACK_SHA'],
            'original_holdout_asset_or_reopen_digest_changed')
    index_path = V/'m4_m5_source_region_001/RUNTIME_ARCHIVE.json'
    index = read(index_path)
    receipts = {}
    for label in ('asset', 'readback_after_reload'):
        original = pins[label]
        member = 'fixture/' + Path(original['path']).name
        record, = [row for row in index['files'] if row['relative'] == member]
        sealed = pin(index_path.parent/record['copy'])
        require((sealed['sha256'], sealed['bytes']) == (record['sha256'], record['bytes'])
                == (original['sha256'],original['bytes']), 'archived_current_fixture_or_readback_changed/'+label)
        receipts[label] = sealed
    membership = run_path(str(V/'m5_observe_measure_001/oracle.py'))
    oracle_path = V/'m4_cross_scale_discovery_001/oracle/geometry_witness.py'
    oracle_pin = pin(oracle_path)
    require(oracle_pin['sha256'] == '29138a145c6a04bccce7ae950f43e3546efc2d71a533b73105bb4a05277558a0',
            'independent_projection_oracle_changed')
    return {'meshes': meshes, 'raw_meshes': [
        {'name': name, 'vertices': vertices, 'triangles': triangles}
        for name,(vertices,triangles) in meshes.items()], 'points': membership,
        'view': run_path(str(oracle_path)), 'old': old, 'pins': {**pins, 'projection': oracle_pin,
            'archive_index':pin(index_path), 'sealed_asset_and_readback_copies':receipts}}


def verify_source(packet):
    packet = read(packet) if not isinstance(packet,dict) else packet
    s = source()
    return s['old']['verifies_geometry'](packet, s['meshes'])


def verify_geometry_closed_box(vertices, faces):
    bounds = (tuple(sorted({p[index] for p in vertices})) for index in range(3))
    x, y, z = bounds
    require((x,y,z) == ((3,4),(-4,-3),(0,2))
            and len(vertices) == len(set(vertices)) == 8
            and set(vertices) == {(a,b,c) for a in x for b in y for c in z}
            and len(faces) == 12, 'obj08_does_not_have_frozen_box_vertices')
    by_plane = {}
    for index, face in enumerate(faces):
        a,b,c = [vertices[i] for i in face]
        u,v = [[q-p for p,q in zip(a, point, strict=True)] for point in (b,c)]
        normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        axis, = [i for i in range(3) if normal[i] != 0]
        bound = (x,y,z)[axis]
        level = a[axis]
        require(a[axis] == b[axis] == c[axis] and level in bound
                and (normal[axis] > 0) == (level == bound[1]), 'box_face_not_on_outward_plane')
        by_plane.setdefault((axis, level),[]).append((index,set(face),abs(normal[axis])))
    require(len(by_plane) == 6 and all(len(rows) == 2 for rows in by_plane.values()), 'box_faces_do_not_cover_all_sides')
    for (axis, level),rows in by_plane.items():
        face_vertices = {i for i,p in enumerate(vertices) if p[axis] == level}
        face_a,face_b = rows[0][1],rows[1][1]
        inplane = [j for j in range(3) if j != axis]
        side = [(max(p[j] for p in vertices)-min(p[j] for p in vertices)) for j in inplane]
        pair = [vertices[i] for i in face_a & face_b]
        require(face_a | face_b == face_vertices and len(pair) == 2
                and all(pair[0][j] != pair[1][j] for j in inplane)
                and rows[0][2] == rows[1][2] == side[0]*side[1], 'box_faces_do_not_partition_rectangle')
    require([item[0] for item in by_plane[(2,0)]] == list(BOTTOM)
            and [item[0] for item in by_plane[(0,4)]] == list(SIDE), 'selected_group_does_not_match_box_planes')
    return {'x_world_m': [3,4], 'y_world_m': [-4,-3], 'z_world_m': [0,2],
            'six_outward_closed_rectangles': True, 'bottom_faces': list(BOTTOM), 'positive_x_faces': list(SIDE)}


def exact_word(value):
    if value is None:
        return None
    if isinstance(value,str):
        candidate = re.fullmatch(r'sqrt\((\d+)\)/(\d+)', value.strip())
        if candidate:
            return sqrt(int(candidate[1]))/int(candidate[2])
    return float(F(value))


def score_measurement(scope, distance_m, point_a, point_b, tolerance=EPS):
    """Check exact triangle membership, the pair length, and reported distance independently."""
    s = source()
    distance_squared = EXACT_SQUARED[scope]
    approx = sqrt(distance_squared)
    reported = exact_word(distance_m)
    d_ok = reported is not None and abs(reported-approx) <= float(tolerance)
    left,right = (s['meshes'][name] for name in (TARGET,REFERENCE))
    first = SELECTED if scope == 'selected' else range(len(left[1]))
    faces_a, faces_b, delta = [], [], None
    length_pass = False
    if point_a is not None and point_b is not None:
        a,b = (s['old']['vector'](p) for p in (point_a,point_b))
        distance = s['points']['triangle_distance_squared']

        def containing(point,mesh,indices):
            vertices,faces = mesh
            return [i for i in indices if distance(point,tuple(vertices[j] for j in faces[i])) <= tolerance*tolerance]

        faces_a = containing(a,left,first)
        faces_b = containing(b,right,range(len(right[1])))
        delta = tuple(q-p for p,q in zip(a,b,strict=True))
        square = sum(c*c for c in delta)
        length_pass = square == distance_squared if not tolerance else abs(sqrt(square)-approx) <= float(tolerance)
    return {'scope':scope, 'expected_squared_distance_m2':str(distance_squared),
            'expected_distance_approx_m':approx, 'reported_distance_m':reported,
            'distance_correct':d_ok, 'actual_attaining_pair':bool(faces_a and faces_b and length_pass),
            'point_a_evaluated_faces':faces_a, 'point_b_evaluated_faces':faces_b,
            'point_a_to_b_delta_m':[str(c) for c in delta] if delta is not None else None,
            'world_m_tolerance':str(tolerance)}


def projection_proof(pose):
    name = pose['name']
    direction = DIRECTIONS.get(name)
    require(direction is not None and tuple(pose['direction_rational']) == direction
            and pose['projection'] == 'orthographic', 'unknown_or_nonconforming_image_direction')
    view,projection = [tuple(tuple(F(x) for x in row) for row in pose[key])
                       for key in ('view_matrix','projection_matrix')]
    require(all(len(m) == 4 and all(len(row) == 4 for row in m) and m[3] == (0,0,0,1)
                for m in (view,projection)), 'actual_render_matrix_is_not_orthographic')
    norm = sqrt(sum(d*d for d in direction))
    require(all(abs(float(got)-axis/norm) <= 1e-12 for got,axis in zip(view[2][:3],direction,strict=True)),
            'actual_render_direction_does_not_agree_with_view')
    s = source()
    own = s['meshes'][TARGET][0]

    def mul(matrix,point):
        return tuple(sum(x*y for x,y in zip(row,point,strict=True)) for row in matrix)

    corners = {}
    for group,ids in (('bottom',(0,3,2,1)),('side',(1,2,6,5))):
        ndc = [mul(projection,mul(view,own[i]+(F(1),))) for i in ids]
        corners[group] = sum(row[3] == 1 and all(-1 < x < 1 for x in row[:3]) for row in ndc)
    side = direction[0] > 0
    occluders_checked = 0
    if side:
        found = s['view']['prove'](s['raw_meshes'],SIDE_RECTANGLE,direction)
        require(found['whole_rectangle_geometrically_complete'] and found['occluder_triangles_checked'] == 60,
                'side_geometry_could_not_be_independently_accounted_for')
        occluders_checked = found['occluder_triangles_checked']
    return {'view':name, 'direction_world':list(direction), 'selected_group_corners_in_frame':corners,
            'complete_selection_geometry':False, 'side_clear_geometry_candidate':side,
            'nonselected_side_occluder_triangles_checked':occluders_checked,
            'bottom_interior_rays_enter_obj08':direction[2] > 0}


def offsets(names):
    meshes = source()['meshes']
    require(len(names) == len(meshes) and set(names) == set(meshes), 'different_current_image_mesh_roster')
    result = [0]
    for name in names:
        result.append(result[-1]+len(meshes[name][1]))
    return result


def pixel_proof(png, raw_npz, names):
    import numpy as np
    from PIL import Image

    boundaries = offsets(names)
    with np.load(BytesIO(raw_npz),allow_pickle=False) as archive:
        rgb,owner,tri,depth = [archive[k] for k in ('color','owners','triangle_ids','depth')]
        require(archive['face_patch_offsets'].tolist() == boundaries, 'frame_triangle_offsets_do_not_match_source')
    with Image.open(BytesIO(png)) as image:
        require(image.format == 'PNG' and image.mode == 'RGB' and np.array_equal(np.asarray(image),rgb),
                'original_PNG_differs_from_bound_pixel_array')
    present = owner >= 0
    require(rgb.dtype == np.uint8 and owner.shape == tri.shape == depth.shape == rgb.shape[:2]
            and np.issubdtype(owner.dtype,np.signedinteger) and np.issubdtype(tri.dtype,np.signedinteger)
            and np.all(owner >= -1) and np.all(owner < len(names)) and np.array_equal(present,tri >= 0),
            'pixel_owner_maps_are_invalid')
    start = np.asarray(boundaries)
    require(np.all(tri[present] >= start[owner[present]]) and np.all(tri[present] < start[owner[present]+1])
            and np.all(np.isfinite(depth[present]) & (depth[present] > 0)), 'raster_face_owner_and_depth_disagree')
    owner_index = names.index(TARGET)
    counts = {str(i):int(np.count_nonzero((owner == owner_index) & (tri == start[owner_index]+i))) for i in SELECTED}
    side_count = sum(counts[str(i)] for i in SIDE)
    bottom_count = sum(counts[str(i)] for i in BOTTOM)
    size = [int(rgb.shape[1]),int(rgb.shape[0])]
    return {'pixels_by_evaluated_triangle':counts, 'bottom_pixels':bottom_count, 'side_pixels':side_count,
            'selected_surface_pixels':bottom_count+side_count, 'size_px':size}


def verify_frame(slot_root, frame, binding, original_image_block, *, scene):
    slot = Path(slot_root).resolve(strict=True)
    scene = read(scene) if not isinstance(scene,dict) else scene
    verify_source(scene)
    objects = {row['name']:row for row in scene['objects']}
    rows = binding['objects']
    names = [row['object_name'] for row in rows]
    require(all(row['host_id'] == objects[row['object_name']]['object_id'] and
                row['instance_id'] == objects[row['object_name']]['instance_id'] for row in rows)
            and frame['host_binding_sha256'] == binding['binding_sha256']
            and frame['source_revision'] == binding['scene_revision']
            and frame['scene_identity'] == binding['geometry_identity']
            and frame['candidate_identity'] == binding['camera_identity']
            and frame['display_identity'] == binding['display_identity']
            and frame['image_scope'] == binding['image_scope']
            and frame['view_name'] == frame['pose']['name'] and frame['all_triangle_count'] == 62
            and binding['image_scope']['participation_mask'] == [True]*len(names),
            'frame_does_not_match_same_current_source_or_display')
    png, arrays = [Path(frame[key]).resolve(strict=True) for key in ('image_path','arrays_path')]
    require(png.is_relative_to(slot) and arrays.is_relative_to(slot), 'current_image_or_arrays_outside_slot')
    raw, npz = png.read_bytes(), arrays.read_bytes()
    require(original_image_block['type'] == 'image' and original_image_block['mimeType'] == 'image/png'
            and base64.b64decode(original_image_block['data'],validate=True) == raw
            and digest(raw) == frame['image_sha256'] and len(raw) == frame['PNG_bytes']
            and digest(npz) == frame['arrays_sha256'], 'actual_original_PNG_or_arrays_digest_changed')
    geometry = projection_proof(frame['pose'])
    pixels = pixel_proof(raw,npz,names)
    return {**geometry, **pixels, 'useful_partial_side_image':bool(geometry['side_clear_geometry_candidate'] and pixels['side_pixels']),
            'image':pin(png),'arrays':pin(arrays),'image_ref':frame['image_ref'],'frame_identity':frame['frame_identity']}


def load_truth():
    s = source()
    own,ref = (s['meshes'][key] for key in (TARGET,REFERENCE))
    box = verify_geometry_closed_box(*own)
    ref_pts = ref[0]
    require({p[0] for p in ref_pts} == {-4}
            and sorted({p[1] for p in ref_pts}) == [F(-1,16),F(1,16)]
            and sorted({p[2] for p in ref_pts}) == [F(15,16),F(17,16)]
            and len(ref[1]) == 2, 'selected_reference_plane_bounds_changed')
    bottom = {own[0][i] for row in BOTTOM for i in own[1][row]}
    require({p[2] for p in bottom} == {0}, 'selected_bottom_plane_changed')
    side = {own[0][i] for row in SIDE for i in own[1][row]}
    require({p[0] for p in side} == {4} and 8**2 > EXACT_SQUARED['selected'],
            'selected_side_does_not_have_independently_larger_bound')
    distances = {}
    for scope,points in (('selected',bottom),('whole',own[0])):
        separations = [max(F(0), min(p[i] for p in points)-max(p[i] for p in ref_pts),
                           min(p[i] for p in ref_pts)-max(p[i] for p in points)) for i in range(3)]
        lower = sum(gap*gap for gap in separations)
        require(lower == EXACT_SQUARED[scope], 'linear_separation_does_not_certify_exact_squared_bound/'+scope)
        proof = score_measurement(scope,None,ATTAIN[scope],ATTAIN_B,F(0))
        require(proof['actual_attaining_pair'], 'proposed_attainment_point_not_a_true_triangle_point/'+scope)
        distances[scope] = {'axis_separations_m':[str(x) for x in separations], 'squared_exact_m2':str(lower),
                            'distance_m':f"sqrt({14978 if scope == 'selected' else 14753})/16",
                            'distance_approx_m':sqrt(lower),
                            'attaining_pair_m':[[str(x) for x in p] for p in (ATTAIN[scope],ATTAIN_B)],
                            'point_membership':proof}
    views = {}
    for name,direction in DIRECTIONS.items():
        d = direction[0]
        require(direction[2] > 0, 'upper_direction_pool_changed/'+name)
        row = {'direction_world':list(direction),'selected_bottom_outward_dot':-direction[2],
               'bottom_interior_rays_enter_obj08':True,'selected_side_outward_dot':d,
               'whole_selection_complete_visibility':False}
        if d > 0:
            check = s['view']['prove'](s['raw_meshes'],SIDE_RECTANGLE,direction)
            require(check['occluder_triangles_checked'] == 60 and check['whole_rectangle_geometrically_complete'],
                    'unexpected_side_occluding_geometry/'+name)
            row.update(side_geometric_candidate=True,triangles_checked=60)
        else:
            row.update(side_geometric_candidate=False,reason='edge_on' if d == 0 else 'back_facing')
        views[name] = row
    return {'asset_sha256':ASSET_SHA,'readback_sha256':READBACK_SHA,
            'counts':s['old']['COUNTS'],'target':TARGET,'reference_whole':REFERENCE,'selected_triangles':list(SELECTED),
            'box_closure':box,'selected_side_lower_bound_m':'8','distances':distances,'finite_views':views,
            'source_pins':s['pins'],'visibility_scope':'positive-z rays through any point in the bottom interior enter the closed box for a nonzero depth; actual useful side pixels are verified only on current original frames'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    with args.output.open('x',encoding='utf-8',newline='\n') as destination:
        destination.write(json.dumps(load_truth(),indent=2,ensure_ascii=False,allow_nan=False)+'\n')
