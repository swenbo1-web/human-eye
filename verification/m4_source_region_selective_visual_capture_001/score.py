"""Score closed real stdio/TCP visual captures against independent current source."""

import ast
import base64
from fractions import Fraction
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'm4_source_region_visual_scope_proof_001'
INSTALL = Path('D:/he_m1_m2_source_region_scoped_measurement_001/candidate_install/product')
DEPENDENCIES = Path('D:/he_anchor_001/venv/Lib/site-packages')
for dependency in (str(DEPENDENCIES), str(INSTALL)):
    if dependency not in sys.path:
        sys.path.append(dependency)

import numpy as np
from PIL import Image

ASSET = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
ORDER = ('M21', 'M19')
VIEWS = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')
PLAN_SCOPE_SIZE = {'M21': 4, 'M19': 9}
SOURCE_INDEX_DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
HOST_PREFIX = 'HUMAN_EYE_BLENDER_MCP:'
LEGACY_REF_SCHEMA = 'human-eye-source-region-ref-v1'


def need(value, reason):
    if not value:
        raise ValueError(reason)


def digest(value):
    return {'bytes': len(value), 'sha256': sha256(value).hexdigest()}


def pin(path, raw=None):
    path = Path(path)
    return {'path': str(path), **digest(path.read_bytes() if raw is None else raw)}


def load(path):
    return json.loads(Path(path).read_bytes())


def checked_path(slot, name):
    path = Path(name)
    if not path.is_absolute():
        path = slot / path
    resolved = path.resolve(strict=True)
    need(str(path) == str(resolved) and resolved.is_relative_to(slot) and resolved.is_file(),
         'noncanonical_or_cross_slot_source')
    return resolved


def same_bits(left, right):
    if isinstance(left, float) or isinstance(right, float):
        return (type(left) in (int, float) and type(right) in (int, float)
                and struct.pack('=d', left) == struct.pack('=d', right))
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_bits(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_bits(a, b) for a, b in zip(left, right))
    return left == right


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf8')).hexdigest()


def _array_digest(values):
    return {'dtype': str(values.dtype), 'shape': list(values.shape),
            'nbytes': int(values.nbytes), 'sha256': sha256(values.tobytes(order='C')).hexdigest()}


def reference_inputs():
    """Load the prior Git-pinned public/host/raw source of both exact image cases."""
    sys.path.insert(0, str(PRIOR))
    try:
        from sources import load_formal, RAIL, RAIL_COMMIT
        cases = load_formal(RAIL, RAIL_COMMIT, ('M19', 'M21'))
    finally:
        sys.path.remove(str(PRIOR))
    by_name = {case['label']: case for case in cases}
    run = Path('D:/he_m4_source_region_visual_scope_proof_001')
    repo = HERE.parents[1]
    pinned = subprocess.check_output(('git','show',
        '789165b8f892afcd62ea1bb765a185eec1982e13:verification/m4_source_region_visual_scope_proof_001/RESULT.json'),
        cwd=repo)
    historical_raster = json.loads(pinned)
    for label in ORDER:
        row = by_name[label]
        prior_proof = historical_raster['cases'][label]['offline_proof']
        path = run/'cases/main'/label/'RESULT.json'
        need(pin(path) == prior_proof, 'prior_projection_roster_receipt_changed')
        stat = load(path)
        kept = stat['original_camera_tight_world']['kept_ordinals']
        need(stat['passed'] and len(kept) == PLAN_SCOPE_SIZE[label], 'prior_projection_roster_unavailable')
        row['expected_kept'] = kept
    return by_name


def host_exchange(tx, rx):
    """Bind the real native wire envelope to its registered executable request."""
    request, reply = json.loads(tx), json.loads(rx)
    need(request['type'] == 'execute_code' and reply['status'] == 'success', 'native_wire_execution_failed')
    tree = ast.parse(request['params']['code'])
    matches = [v.value for v in tree.body if isinstance(v, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == '_request' for t in v.targets)]
    need(len(matches) == 1, 'native_wire_request_literal_missing')
    literal = matches[0]
    need(isinstance(literal, ast.Call) and isinstance(literal.func, ast.Attribute)
         and literal.func.attr == 'loads' and isinstance(literal.func.value, ast.Name)
         and literal.func.value.id == '_json' and len(literal.args) == 1
         and isinstance(literal.args[0], ast.Constant) and isinstance(literal.args[0].value, str),
         'native_wire_request_literal_malformed')
    sent = json.loads(literal.args[0].value)
    payload = [line[len(HOST_PREFIX):] for line in reply['result']['result'].splitlines()
               if line.startswith(HOST_PREFIX)]
    need(len(payload) == 1, 'native_wire_unrecognized_stdout')
    enclosed = json.loads(payload[0])
    need(enclosed['id'] == sent['id'] and 'result' in enclosed, 'native_wire_reply_nonce_or_failure')
    return sent, enclosed['result']


def read_wire(slot, tx_path, rx_path):
    tx, rx = checked_path(slot, tx_path), checked_path(slot, rx_path)
    return tx.read_bytes(), rx.read_bytes(), tx, rx


def mcp_exchange(tx, rx, arguments, png):
    sent, received = json.loads(tx), json.loads(rx)
    need(sent.get('id') == received.get('id') and 'id' in sent and sent['method'] == 'tools/call'
         and sent['params']['name'] == 'human_eye_scene_observe' and sent['params']['arguments'] == arguments
         and received['result'].get('isError') is False, 'public_mcp_not_same_successful_call')
    blocks = received['result']['content']
    images = [(index, row) for index, row in enumerate(blocks) if row['type'] == 'image']
    need(len(images) == 1 and images[0][1]['mimeType'] == 'image/png'
         and base64.b64decode(images[0][1]['data'], validate=True) == png, 'public_png_not_actual_producer_bytes')
    bodies = []
    for row in blocks:
        if row['type'] != 'text' or not row['text'].lstrip().startswith('{'):
            continue
        body = json.loads(row['text'])
        if isinstance(body, dict) and ('schema' in body or 'result_kind' in body):
            bodies.append(body)
    need(len(bodies) == 1, 'public_mcp_observation_body_missing_or_ambiguous')
    return sent['id'], bodies[0], images[0][0]


def assert_no_old_refs(value):
    if isinstance(value, dict):
        need('region_ref' not in value and value.get('schema') != LEGACY_REF_SCHEMA
             and value.get('capture_scope') != 'complete_scene_meshes'
             and 'ordered_geometry_sha256' not in value, 'private_representation_claims_old_source_scope')
        for child in value.values():
            assert_no_old_refs(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            assert_no_old_refs(child)
    elif isinstance(value, str):
        need(not value.startswith(('source-region:', 'source-region-image:', 'active-image:')),
             'private_representation_reused_old_reference_namespace')


def same_source(before, current):
    """Match arrays and pose between reopened copies without cross-process pointers."""
    need(current['source']['asset_sha256'] == before['source']['asset_sha256'] == ASSET,
         'terminal_asset_hash_changed')
    stable_source = ('scene', 'frame', 'subframe', 'scale_length', 'unit_settings', 'view_layer')
    need(all(same_bits(before['source'][key], current['source'][key]) for key in stable_source),
         'terminal_document_frame_units_layer_changed')
    prev, now = before['objects'], current['objects']
    stable = ('name', 'object_id', 'mesh_name', 'matrix_world', 'native_matrix_world', 'native',
              'evaluated', 'visible_get', 'display', 'parent', 'modifiers')
    need(len(now) == len(prev) == 21, 'terminal_ordered_object_count_changed')
    for prior, row in zip(prev, now, strict=True):
        need(all(same_bits(prior[key], row[key]) for key in stable),
             'terminal_geometry_pose_or_display_changed/' + prior['name'])
    need(current['display_object_mask'] == before['display_object_mask']
         and current['source_face_offsets'] == before['source_face_offsets'],
         'terminal_display_or_exact_face_domain_changed')
    ids = [(row['object_id'], row['instance_id']) for row in now]
    need(len(set(ids)) == len({pair[0] for pair in ids}) == len(now)
         and all(all(isinstance(v, str) and v for v in pair) for pair in ids),
         'terminal_ambiguous_current_instances')
    return now


def case_selection(rows, query):
    region = query['region']
    target, reference = (
        next(i for i, item in enumerate(rows) if
             item['name' if 'name' in selector else 'object_id'] == next(iter(selector.values())))
        for selector in (region['object'], query['reference']))
    need(target != reference, 'reference_must_be_separate_whole_object')
    source = rows[target]['evaluated']
    box = region['world_box_m']
    verts, faces = source['vertices_world_m'], source['triangles']
    within = [all(low <= x <= high for low, x, high in zip(box['min'], pt, box['max'], strict=True))
              for pt in verts]
    chosen = [i for i, indices in enumerate(faces) if all(within[j] for j in indices)]
    return target, reference, chosen


def exact_triangle_member(point, vertices):
    a, b, c = (tuple(map(Fraction, v)) for v in vertices)
    p = tuple(map(Fraction, point))
    ab = tuple(y-x for x, y in zip(a, b))
    ac = tuple(y-x for x, y in zip(a, c))
    ap = tuple(y-x for x, y in zip(a, p))

    def dot(x, y):
        return sum(a*b for a, b in zip(x, y))

    def cross(x, y):
        return (x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0])

    normal = cross(ab, ac)
    if dot(normal, ap) != 0:
        return False
    u, v, w = dot(ab, ab), dot(ab, ac), dot(ac, ac)
    det = u*w - v*v
    if det == 0:
        # Test exact membership of the largest segment in a rank-deficient hull.
        first, last = max(((a, b), (a, c), (b, c)),
                          key=lambda pair: sum((x-y)**2 for x, y in zip(*pair)))
        direction = tuple(y-x for x, y in zip(first, last))
        relative = tuple(y-x for x, y in zip(first, p))
        return (not any(cross(direction, relative)) and
                (p == first if not any(direction) else 0 <= dot(direction, relative) <= dot(direction, direction)))
    s = dot(ap, ab)*w - dot(ap, ac)*v
    t = dot(ap, ac)*u - dot(ap, ab)*v
    return s >= 0 and t >= 0 and s + t <= det


def measurement(producer, historic, rows, target, reference, selected):
    task = producer['task_result']
    need(task['status'] == 'complete' and task['read_only'] is True
         and task['execution_authority'] is False, 'source_measurement_not_complete_readonly')
    fact = task['facts']['surface_proximity']
    prior = historic['task_result']['facts']['surface_proximity']
    need(fact['status'] == fact['direction_status'] == fact['witness_status'] == 'measured'
         and same_bits(fact['value'], prior['value']), 'source_measurement_distance_witness_changed')
    value = fact['value']
    witness = value['nearest_witness']
    ref = task['reference']
    terminal_reference = rows[reference]
    need(ref['object_id'] == terminal_reference['object_id']
         and ref['instance_id'] == terminal_reference['instance_id'],
         'measurement_reference_wrong_current_instance')
    delta = [b-a for a, b in zip(witness['a'], witness['b'], strict=True)]
    distance = math.hypot(*delta)
    need(distance > 0 and abs(distance - value['distance_m']) <= 2*math.ulp(distance)
         and all(abs(x/distance - y) <= 4*math.ulp(1.) for x, y in
                 zip(delta, witness['direction_a_to_b'], strict=True)), 'measurement_geometry_inconsistent')
    source = task['source_mapping']['nearest_witness']
    for side, ordinal in (('a', target), ('b', reference)):
        proof = source[side]
        in_source = proof['source_triangle_indices']
        available = rows[ordinal]['evaluated']
        vertices, triangles = available['vertices_world_m'], available['triangles']
        allowed = selected if side == 'a' else range(len(triangles))
        complete = [index for index in allowed if exact_triangle_member(
            witness[side], [vertices[j] for j in triangles[index]])]
        need(proof['exact_membership'] is True and proof['index_domain'] == SOURCE_INDEX_DOMAIN
             and in_source == complete and bool(complete), 'wrong_source_witness_triangle/' + side)
        need(proof['source_vertex_indices'] == [i for i, v in enumerate(vertices)
              if v == witness[side] and any(i in triangles[j] for j in allowed)],
             'wrong_source_witness_vertex/' + side)
    return {'distance_m':value['distance_m'], 'direction_a_to_b':witness['direction_a_to_b'],
            'point_a_m':witness['a'], 'point_b_m':witness['b'],
            'source_triangles_a':source['a']['source_triangle_indices'],
            'source_triangles_b':source['b']['source_triangle_indices']}


def full_offsets(rows):
    return np.cumsum([0, *(len(row['evaluated']['triangles']) for row in rows)], dtype=np.int64)


def producer_domain(producer, rows, kept, private):
    binding = producer['binding']
    objects = binding['objects']
    expected_all = [row['object_id'] for row in rows]
    need(len(objects) == len(kept), 'producer_retained_object_count_changed')
    if private:
        directory = binding['directory']
        need([d['object_id'] for d in directory] == expected_all
             and [d['instance_id'] for d in directory] == [row['instance_id'] for row in rows],
             'private_original_directory_missing_current_instances')
        need([r['original_object_ordinal'] for r in objects] == kept
             and [r['original_triangle_offset'] for r in objects] == full_offsets(rows)[kept].tolist(),
             'private_original_ordinal_or_face_offset_changed')
    for local, ordinal in enumerate(kept):
        row, obj = rows[ordinal], objects[local]
        need(obj['object_index'] == local and obj['host_id'] == row['object_id']
             and obj['instance_id'] == row['instance_id'], 'producer_scope_order_or_instance_mismatch')
        if private:
            need(obj['triangle_count'] == len(row['evaluated']['triangles']),
                 'private_retained_original_face_count_mismatch')
    return [rows[index]['visible_get'] for index in kept]


def unpack_frame_arrays(frame, png, npz, expected_vis, rows, kept):
    need(digest(png) == {'bytes':frame['PNG_bytes'], 'sha256':frame['image_sha256']}
         and digest(npz) == {'bytes':frame['compressed_array_file_bytes'], 'sha256':frame['arrays_sha256']},
         'frame_png_or_npz_sha_not_same_producer')
    with np.load(BytesIO(npz), allow_pickle=False) as loaded:
        need(set(loaded.files) == set(frame['arrays']) and len(loaded.files) == len(set(loaded.files)),
             'NPZ_array_table_not_same_producer')
        values = {key: loaded[key] for key in loaded.files}
    need(all(_array_digest(array) == frame['arrays'][key] for key, array in values.items()),
         'NPZ_array_bytes_not_same_producer')
    need(values['triangle_id_scope'].item() == frame['triangle_id_scope']
         and values['owner_mapping_identity'].item() == frame['owner_mapping_identity']
         and values['display_identity'].item() == frame['display_identity']
         and values['image_scope_identity'].item() == frame['image_scope_identity']
         and values['display_object_mask'].dtype == np.bool_
         and values['display_object_mask'].tolist() == expected_vis,
         'NPZ_metadata_scope_not_same_current_producer')
    need(frame['image_scope']['participation_mask'] == expected_vis and
         fingerprint(frame['image_scope']) == frame['image_scope_identity'],
         'frame_image_scope_not_same_current_producer')
    color, depth, owner, triangle = (values[key] for key in ('color','depth','owners','triangle_ids'))
    width,height = frame['pose']['size_px']
    shape = (height,width)
    need(color.shape == (*shape, 3) and color.dtype == np.uint8
         and depth.shape == owner.shape == triangle.shape == shape
         and depth.dtype == np.float64 and owner.dtype == triangle.dtype == np.int32,
         'NPZ_frame_raster_dimensions_or_dtype_invalid')
    with Image.open(BytesIO(png)) as image:
        need(image.mode == 'RGB' and image.size == (width, height) and np.array_equal(np.asarray(image), color),
             'PNG_rgb_disagrees_with_actual_NPZ_raster')

    full = full_offsets(rows)
    local = np.cumsum([0, *(int(full[k+1] - full[k]) for k in kept)],dtype=np.int64)
    need(values['face_patch_offsets'].dtype == np.int64
         and np.array_equal(values['face_patch_offsets'], local)
         and frame['all_object_count'] == len(kept) and frame['all_triangle_count'] == int(local[-1]),
         'NPZ_face_offsets_invalid_for_current_object_domain')
    foreground = owner >= 0
    need(np.all(owner >= -1) and np.all(owner < len(kept)) and np.all(triangle >= -1)
         and np.array_equal(foreground, triangle >= 0) and np.all(np.isposinf(depth[~foreground]))
         and np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0)),
         'NPZ_invalid_shared_depth_owner_surface')
    local_objects = owner[foreground]
    source_rows = triangle[foreground] - local[local_objects]
    need(np.all(np.asarray(expected_vis)[local_objects]) and
         np.all((source_rows >= 0) & (source_rows < local[local_objects+1] - local[local_objects])),
         'NPZ_source_row_not_in_actual_winning_object_or_display')
    original_owners = np.array(owner, dtype=np.int32, copy=True)
    original_sources = np.array(triangle, dtype=np.int32, copy=True)
    original_owners[foreground] = np.asarray(kept,dtype=np.int32)[local_objects]
    # Compare object-local source rows, then permit full offsets only from full terminal geometry.
    original_sources[foreground] = source_rows
    return {'color':color,'depth':depth,'owners':original_owners, 'source_rows':original_sources}


def same_raster(left, right, context):
    need(left.keys() == right.keys(), 'raster_metadata_changed/' + context)
    for name in left:
        a,b = left[name],right[name]
        need(a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(),
             'raster_bits_changed/' + context + '/' + name)


def roi_visibility(producer, frame, raster, target, selected, historic):
    v = producer['facts']['visibility']
    old = historic['facts']['visibility']
    names = ('view_name','status','visibility_scope','selected_source_triangle_count',
             'selected_object_participates','visible_source_triangle_indices','unseen_source_triangle_indices',
             'selected_surface_pixels','visible_pixel_bounds','sampled_pixel','unknown')
    need(all(same_bits(v[k], old[k]) for k in names)
         and v['image_ref'] == frame['image_ref'] and v['frame_identity'] == frame['frame_identity']
         and v['image_scope'] == frame['image_scope'], 'real_frame_ROI_visibility_changed')
    target_pixels = (raster['owners'] == target) & np.isin(raster['source_rows'], selected)
    y, x = np.nonzero(target_pixels)
    rows = np.unique(raster['source_rows'][target_pixels]).tolist()
    need(len(x) > 0 and v['selected_surface_pixels'] == len(x)
         and v['visible_source_triangle_indices'] == rows
         and v['unseen_source_triangle_indices'] == sorted(set(selected) - set(rows))
         and v['visible_pixel_bounds'] == [int(x.min()), int(y.min()), int(x.max()), int(y.max())],
         'real_frame_ROI_pixel_values_not_proven_by_NPZ')
    pixel = v.get('sampled_pixel')
    if pixel is not None:
        py, px = pixel['row'], pixel['column']
        need(0<=py<target_pixels.shape[0] and 0<=px<target_pixels.shape[1]
             and target_pixels[py, px] and raster['source_rows'][py, px] == pixel['source_triangle_index'],
             'actual_sampled_pixel_wrong_owner_or_source')
    return {'selected_pixels':len(x), 'visible_triangle_rows':rows,'sampled_pixel':pixel}


def camera_contract(producer, historic, frame):
    current = producer['binding']['camera_specification']['views']
    original = historic['binding']['camera_specification']['views']
    need(tuple(view['name'] for view in current) == VIEWS and same_bits(current, original),
         'registered_six_pose_binary64_mismatch')
    chosen, = (p for p in current if p['name'] == frame['view_name'])
    need(frame['view_name'] == historic['frames'][0]['view_name'] and same_bits(chosen, frame['pose']),
         'actual_frame_not_selected_historical_pose')
    a,b = (item['stages'].get('source_region_sparse_view_selection') for item in (producer, historic))
    need((a is None) == (b is None) and (a is None or
         (same_bits(a['votes'], b['votes']) and a['chosen_view'] == b['chosen_view'] == frame['view_name'])),
         'sparse_view_voting_or_final_pose_changed')
    return 6


def verify_a_host(decoder, wire, rows, binding):
    need(wire['schema'] == 'human-eye-scene-delta-v1', 'baseline_native_wire_missing_complete_delta')
    capture = decoder.apply(wire)
    meshes = capture['meshes']
    need(len(meshes) == len(rows) and capture['capture_state'] == binding['capture_state']
         and capture['revision'] == binding['scene_revision'],
         'baseline_native_delta_not_same_current_binding')
    for row, mesh in zip(rows, meshes, strict=True):
        need(mesh['object_id'] == row['object_id'] and mesh['name'] == row['name']
             and same_bits(mesh['vertices'], row['evaluated']['vertices_world_m'])
             and mesh['faces'] == row['evaluated']['triangles'],
             'baseline_actual_capture_not_same_terminal_geometry')
    return {'transmitted_objects':len(wire['resources']),
            'transmitted_vertices':sum(len(row['vertices_local']) for row in wire['resources']),
            'transmitted_triangles':sum(len(row['faces']) for row in wire['resources'])}



def validate_omitted(box, world, cameras):
    points = np.column_stack((np.asarray(world, dtype=np.float64), np.ones(len(world))))
    lo, hi = np.asarray(box, dtype=np.float64)
    need(np.all((lo <= points[:, :3]) & (points[:, :3] <= hi)), 'omitted_outward_bound_drops_real_point')
    with np.errstate(over='ignore', invalid='ignore'):
        for pose in cameras['views']:
            projection = np.asarray(pose['projection_matrix'],dtype=np.float64)
            view = np.asarray(pose['view_matrix'],dtype=np.float64)
            ndc = (points @ view.T) @ projection.T
            need(np.all(np.isfinite(ndc)) and np.all(ndc[:,3] == 1.),
                 'omitted_object_cannot_prove_finite_all_three_projected_axes')
            need(any(np.all(ndc[:,axis] < -1.) or np.all(ndc[:,axis] > 1.) for axis in range(2)),
                 'omitted_object_can_reach_registered_viewport')


def verify_b_host(sent, wire, rows, kept, query, terminal, selected, target, reference):
    request = {'target':query['region']['object'], 'reference':query['reference'],
               'world_box_m':query['region']['world_box_m']}
    need(sent['command'] == 'capture_source_region_visual' and same_bits(sent['params']['query'], request)
         and same_bits(wire['query'], request), 'private_native_request_not_registered_scope')
    need(wire['schema'] == 'human-eye-source-region-visual-capture-v1'
         and wire['capture_scope'] == 'source_region_visual_meshes' and wire['capture_state'] is None
         and wire['source_triangle_indices'] == selected and wire['retained_ordinals'] == kept
         and wire['execution_authority'] is False, 'private_wire_result_not_registered_scope')
    no_sha = {key:value for key,value in wire.items() if key != 'sha256'}
    no_revision = {key:value for key,value in no_sha.items() if key not in ('revision','work')}
    need(fingerprint([no_sha]) == wire['sha256']
         and wire['revision'] == 'source-region-visual:' + fingerprint([no_revision]),
         'private_native_result_digest_mismatch')
    directory, display, frame = (wire[key] for key in ('directory','display_snapshot','source_frame'))
    need(len(directory) == len(rows) == len(display['objects']) and display['status'] == 'captured'
         and display['view_layer'] == {'name':terminal['source']['view_layer'],
                                       'instance_id':terminal['source']['view_layer_id']}
         and frame['view_layer'] == terminal['source']['view_layer_id']
         and all(same_bits(frame[k], terminal['source'][k]) for k in ('frame','subframe','scale_length')),
         'private_capture_source_display_or_frame_mismatch')
    need(target in kept and reference in kept, 'private_capture_lost_target_or_full_reference')
    counts = full_offsets(rows)
    vertices = 0
    for ordinal, (row, descriptor, vis) in enumerate(zip(rows, directory, display['objects'], strict=True)):
        local = row['evaluated']
        vertices += len(local['vertices'])
        world = np.asarray(local['vertices_world_m'], dtype=np.float64)
        limits = [world.min(axis=0).tolist(), world.max(axis=0).tolist()]
        need(descriptor['object_id'] == row['object_id'] and descriptor['instance_id'] == row['instance_id']
             and descriptor['ordinal'] == ordinal and descriptor['name'] == row['name']
             and descriptor['triangle_offset'] == counts[ordinal]
             and descriptor['triangle_count'] == counts[ordinal+1]-counts[ordinal]
             and descriptor['vertex_count'] == len(world)
             and same_bits(descriptor['matrix_world'], row['matrix_world'])
             and same_bits(descriptor['world_bounds_m'], limits)
             and vis['host_id'] == row['object_id'] and vis['instance_id'] == row['instance_id']
             and vis['visible_get'] is row['visible_get']
             and all(vis[k] is row['display'][k] for k in ('hide_get','hide_viewport','hide_render')),
             'private_actual_directory_current_ordinal_transform_display_or_count_changed')
        if ordinal not in kept:
            validate_omitted(descriptor['bounds_world_m'], local['vertices_world_m'], wire['camera_plan'])
    for ordinal, mesh in zip(kept, wire['meshes'], strict=True):
        row = rows[ordinal]
        local = row['evaluated']
        need(mesh['object_id'] == row['object_id'] and mesh['name'] == row['name']
             and same_bits(mesh['vertices'], local['vertices_world_m']) and mesh['faces'] == local['triangles'],
             'private_retained_mesh_not_full_current_object')
    transmitted_vertices = sum(len(m['vertices']) for m in wire['meshes'])
    transmitted_faces = sum(len(m['faces']) for m in wire['meshes'])
    work = wire['work']
    expected = {
        'resident_before':0,'resident_after':0,'depsgraph_fetches':1,'source_objects':len(rows),
        'source_vertices':vertices,'source_triangles':int(counts[-1]),'retained_objects':len(kept),
        'omitted_objects':len(rows)-len(kept),'omitted_vertices_checked':vertices-transmitted_vertices,
        'omitted_polygons_checked':int(counts[-1])-transmitted_faces,
        'omitted_loop_indices_checked':3*(int(counts[-1])-transmitted_faces),
        'to_mesh':len(kept),'to_mesh_clear':len(kept),'triangulations':len(kept),
        'expanded_vertices':transmitted_vertices,'expanded_triangles':transmitted_faces,
        'world_vertices_transformed':transmitted_vertices,'sent_vertices':transmitted_vertices,
        'sent_triangles':transmitted_faces,
    }
    need(all(work[field] == value for field,value in expected.items()), 'private_actual_native_work_counts_changed')
    return {**expected, 'transmitted_objects':len(kept),
            'transmitted_vertices':transmitted_vertices, 'transmitted_triangles':transmitted_faces,
            'stages':work['stages']}


def publication_check(slot, manifest, terminal, publication):
    # Close fields are emitted directly by the actual owner and stdio launcher.
    close_path = checked_path(slot, manifest['close_path'])
    terminal_path = checked_path(slot, manifest['terminal_path'])
    need(publication['status'] == 'collected' and publication['safe_to_close']
         and publication['close'] == pin(close_path)
         and publication['terminal']['source'] == pin(terminal_path)
         and publication['actual_blender_starts'] == int(not manifest['offline'])
         and publication['started_ns'] <= publication['closed_ns'] <= publication['deadline_ns'],
         'publication_not_bound_to_close_terminal_and_registered_window')
    close = load(close_path)
    need(close['offline'] is manifest['offline'], 'actual_close_mode_disagrees_with_manifest')
    mcp_close = close['public_MCP_close']
    need(mcp_close['confirmed'] and mcp_close['production_eof_and_exit_verified']
         and mcp_close['stdout_eof_seen'] and mcp_close['exit_code'] == 0
         and not mcp_close['forced_kill'], 'actual_stdio_process_eof_exit_missing')
    for key in ('worker_eof','worker_exit'):
        receipt = mcp_close[key]
        path = checked_path(slot, receipt['path'])
        need(digest(path.read_bytes())['sha256'] == receipt['sha256'], 'closed_stdio_receipt_sha_mismatch')
    native_close = close['Blender_close']
    native_status = close['Blender_status']['closed']
    need(native_close['error'] is None and native_close['exit_code'] == 0 and native_close['process_reaped']
         and native_close['protected_files_unchanged'] and native_close['source_file_unchanged']
         and native_close['pid'] == native_status['pid'] and native_status['poisoned'] is False
         and native_status['initial_geometry_fingerprint'] == native_status['final_geometry_fingerprint'],
         'actual_native_owner_not_safely_reaped')
    if not manifest['offline']:
        post = publication['terminal']['receipt']
        need(native_close['pid'] == terminal['source']['pid'] == post['pid']
             and post['sha256'] == publication['terminal']['source']['sha256']
             and post['bytes'] == publication['terminal']['source']['bytes']
             and terminal['geometry_read_closed_ns'] <= native_status['closed_ns']
             <= native_close['original_deadline_ns'], 'terminal_source_outside_closed_native_window')
    return {'mcp_exit':0,'native_exit':0,'pid':native_close['pid']}


def native_cold_evidence(slot, terminal, closed, shots):
    original_asset = slot/'native/input.blend'
    need(digest(original_asset.read_bytes())['sha256'] == ASSET, 'cold_owned_asset_copy_hash_changed')
    policy_path = slot/'native/COLD_POLICY.json'
    events_path = slot/'native/WORKER_EVENTS.jsonl'
    index_path = slot/'native/WIRE/INDEX.json'
    policy = load(policy_path)
    events = list(map(json.loads, events_path.read_bytes().splitlines()))
    meter = load(index_path)
    need(policy['pid'] == closed['pid'] == terminal['source']['pid']
         and policy['geometry_array_reads_in_guards'] == policy['evaluated_depsgraph_or_to_mesh_in_guards'] == 0,
         'cold_pre_capture_guards_include_geometry')
    need([row['sequence'] for row in events] == [1,2,3,4]
         and [row['sequence'] for row in meter] == [1,2,3,4]
         and all(row['response_sendall_completed'] for row in meter), 'cold_unexpected_pre_read_or_missing_wire')
    for i, shot in enumerate(shots, 1):
        paths = slot/'native/WIRE'/f'{i:03}'
        x,y = paths/'REQUEST.bin', paths/'RESPONSE.bin'
        need(pin(x) == shot['pins']['host_TX'] and pin(y) == shot['pins']['host_RX']
             and x.stat().st_size == meter[i-1]['request_bytes']
             and y.stat().st_size == meter[i-1]['response_attempted_bytes'], 'cold_geometry_copy_probe_not_first_actual_wire')
        event = events[i-1]
        actual_script = json.loads(x.read_bytes())['params']['code'].encode('utf8')
        need(event['script_sha256'] == sha256(actual_script).hexdigest()
             and event['status'] == 'completed' and event['script_error'] is None
             and event['terminal_geometry_and_file_checks_passed']
             and event['render_events_before'] == event['render_events_after'] == 0,
             'cold_worker_qualification_not_bound_to_actual_native_script')
    need(events[0]['m2_work']['before'] == [] and policy['started_ns'] <= events[0]['started_ns']
         and events[1]['started_ns'] + events[1]['elapsed_ns'] <= events[2]['started_ns']
         <= terminal['started_ns'] <= terminal['geometry_read_closed_ns'] <= events[3]['started_ns'],
         'cold_geometry_was_resident_or_terminal_truth_not_captured_after_both')
    return {'first_before_residency_empty':True, 'native_wire_sequences':[1,2,3,4],
            'guard_geometry_reads':0, 'pins':{
                path.name:pin(path) for path in (policy_path,events_path,index_path,original_asset)}}


def verify_slot(slot_path, reference):
    slot = Path(slot_path).resolve(strict=True)
    manifest = load(slot / 'SHOOT.json')
    need(type(manifest['offline']) is bool and manifest['label'] in ('A','B')
         and manifest['asset_sha256'] == ASSET, 'slot_manifest_asset_or_condition_changed')
    need(tuple(row['label'] for row in manifest['queries']) == ORDER, 'slot_call_order_not_M21_then_M19')
    terminal_path, publication_path = (checked_path(slot, manifest[key])
                                      for key in ('terminal_path','publication_path'))
    terminal = load(terminal_path)
    publication = load(publication_path)
    closed = publication_check(slot, manifest, terminal, publication)
    rows = same_source(reference['M21']['terminal'], terminal)
    private = manifest['label'] == 'B'
    if not private:
        from human_eye_plugin.scene_residency import SceneDeltaDecoder
        decoder = SceneDeltaDecoder()
    raw_by_case = {}
    scores = {}
    for entry in manifest['queries']:
        label = entry['label']
        original = reference[label]
        prior = original['producer']
        args = entry['args']
        query = args['query']
        need(args['include_image'] is True and same_bits({**query, 'mode':'source_region'}, original['query']),
             'actual_request_not_frozen_closed_box')
        need(query['mode'] == ('source_region_visual' if private else 'source_region'),
             'actual_request_capture_mode_changed')
        target, reference_ordinal, selected = case_selection(rows, original['query'])
        kept = original['expected_kept'] if private else list(range(len(rows)))
        need(selected == prior['region_ref']['source_triangle_indices'], 'registered_selected_faces_changed')
        prod_file = checked_path(slot, entry['producer_path'])
        producer = load(prod_file)
        expected_kind = 'source_region_visual' if private else 'source_region'
        need(producer['result_kind'] == expected_kind and producer['status'] == 'complete'
             and producer['read_only'] is True and producer['execution_authority'] is False,
             'bad_result_kind_or_noncomplete_3d_evidence')
        need(producer['facts']['region']['source_triangle_indices'] == selected,
             'producer_roi_source_indices_changed')
        producer_region = producer['selection_ref' if private else 'region_ref']
        need(producer_region['source_triangle_indices'] == selected, 'producer_region_reference_wrong_source_rows')
        if private:
            assert_no_old_refs(producer)
        mcp_tx,mcp_rx,mt,mr = read_wire(slot, entry['mcp_tx_path'], entry['mcp_rx_path'])
        host_tx,host_rx,ht,hr = read_wire(slot, entry['host_tx_path'], entry['host_rx_path'])
        frame, = producer['frames']
        roi_scope = producer['binding']
        if private:
            need(frame['scope_id'] == roi_scope['scope_id']
                 and frame['triangle_id_scope'] == 'zero-based-retained-source-triangles-in-private-visual-mesh-order',
                 'private_producer_frame_identity_outside_private_scope')
        else:
            need(frame['host_binding_sha256'] == roi_scope['binding_sha256']
                 and frame['triangle_id_scope'] == 'zero-based-global-source-triangles-in-mesh-order',
                 'baseline_producer_frame_binding_changed')
        png_path,npz_path = (checked_path(slot,entry[k]) for k in ('png_path','npz_path'))
        need(checked_path(slot,frame['image_path']) == png_path
             and checked_path(slot,frame['arrays_path']) == npz_path, 'producer_frame_slot_path_mismatch')
        png,npz = png_path.read_bytes(),npz_path.read_bytes()
        req_id,body,content_index = mcp_exchange(mcp_tx,mcp_rx,args,png)
        if private:
            assert_no_old_refs(body)
        need(body.get('result_kind') == expected_kind and body['status'] == 'complete',
             'public_mcp_body_not_same_result_scope')
        scan = body.get('frames')
        if scan is not None:
            public_frame, = scan
            need(public_frame['frame_identity'] == frame['frame_identity']
                 and public_frame['image_ref'] == frame['image_ref']
                 and public_frame['image_sha256'] == frame['image_sha256']
                 and public_frame.get('native_content_block_index',content_index) == content_index,
                 'public_frame_id_bad_native_content_block')
        sent,wire = host_exchange(host_tx, host_rx)
        host_work = (verify_b_host(sent,wire,rows,kept,original['query'],terminal,selected,target,reference_ordinal)
                     if private else verify_a_host(decoder,wire,rows,roi_scope))
        if private:
            expected_scope = 'source-region-visual-scope:' + wire['revision'].split(':',1)[1]
            need(same_bits(wire['camera_plan']['views'], roi_scope['camera_specification']['views'])
                 and roi_scope['capture_sha256'] == wire['sha256']
                 and roi_scope['host_source_sha256'] == wire['host_source_sha256']
                 and roi_scope['source_frame'] == wire['source_frame'] and roi_scope['directory'] == wire['directory']
                 and frame['scope_id'] == producer_region['scope_id'] == expected_scope,
                 'host_packet_not_same_private_consumer_scope')
        else:
            need(sent['command'] == 'capture', 'baseline_request_wrong_native_capture')
        cam_views = camera_contract(producer,prior,frame)
        display = producer_domain(producer,rows,kept,private)
        raster = unpack_frame_arrays(frame,png,npz,display,rows,kept)
        roi = roi_visibility(producer,frame,raster,target,selected,prior)
        measured = measurement(producer,prior,rows,target,reference_ordinal,selected)
        old_frame, = prior['frames']
        old_png,old_npz = original['png'].read_bytes(),original['npz'].read_bytes()
        prior_rows = original['terminal']['objects']
        prior_kept = list(range(len(prior_rows)))
        prior_vis = [row['visible_get'] for row in prior_rows]
        old_raster = unpack_frame_arrays(old_frame,old_png,old_npz,prior_vis,prior_rows,prior_kept)
        need(png == old_png, 'new_visual_png_not_same_historical_original')
        same_raster(raster,old_raster,label+'-historical')
        raw_by_case[label]={'png':png,'raster':raster,'frame':frame}
        scores[label]={'public_id':req_id,'host_id':sent['id'],'cameras_bit_exact':cam_views,
                       'objects_retained':len(kept),'selected_source_triangles':selected,'ROI':roi,
                       'measurement':measured,'host_work':host_work,
                       'pins':{key:pin(value) for key,value in (
                           ('producer',prod_file),('actual_PNG',png_path),('actual_NPZ',npz_path),
                           ('mcp_TX',mt),('mcp_RX',mr),('host_TX',ht),('host_RX',hr))}}
    cold = None if manifest['offline'] else native_cold_evidence(
        slot, terminal, closed, [scores[name] for name in ORDER])
    return {'label':manifest['label'],'offline':manifest['offline'],'close':closed,'cases':scores,
            'cold_proof':cold,
            'terminal':pin(terminal_path),'publication':pin(publication_path),
            'shoot':pin(slot / 'SHOOT.json')}, raw_by_case


def verify_pair(slot_a, slot_b, reference=None):
    if reference is None:
        reference = reference_inputs()
    a,raw_a = verify_slot(slot_a,reference)
    b,raw_b = verify_slot(slot_b,reference)
    need(a['label'] == 'A' and b['label'] == 'B' and a['offline'] is b['offline']
         and a['close']['pid'] != b['close']['pid'], 'independent_AB_real_cold_slot_pair_required')
    for label in ORDER:
        left,right = raw_a[label],raw_b[label]
        need(left['frame']['frame_identity'] != right['frame']['frame_identity']
             and left['frame']['image_ref'] != right['frame']['image_ref']
             and left['frame']['arrays_sha256'] != right['frame']['arrays_sha256'],
             'private_and_full_scope_reused_same_frame_identity')
        need(left['png'] == right['png'], 'AB_exact_public_PNG_changed')
        same_raster(left['raster'],right['raster'],label+'-AB')
    return {'passed':True,'offline':a['offline'],'slot_order':['A','B'],'selected_order':list(ORDER),
            'same_PNG':2, 'same_RGB_depth_and_remapped_original_owner_face':2,
            'same_camera_views':12,'equal_measurements':2,'arms':{'A':a,'B':b}}
