"""Native qualification and independent checks of current geometry and each original frame."""

import base64
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from math import sqrt
from pathlib import Path
from runpy import run_path


VERIFICATION = Path(__file__).resolve().parents[2]
EXPECTED_COUNTS = [21, 3506, 6162]
EXPECTED_TARGETS = {'S021', 'S034', 'S055'}
REFERENCE = 'M4_Far_00'
RANGE = (F(7, 2048), F(9, 2048))
NATIVE_READ = """import json
from hashlib import sha256
qualification_capture = scene_data()
qualification_rows = sorted([[obj['name'], obj['object_id'], obj['instance_id'], obj['visible_get'],
                              obj['vertices'], obj['triangles']] for obj in qualification_capture['objects']])
print(json.dumps({'source_ref': qualification_capture['source_ref'], 'source': qualification_capture['source'],
                  'sha256': sha256(json.dumps(qualification_rows, separators=(',', ':')).encode()).hexdigest(),
                  'counts': [len(qualification_rows), sum(len(row[4]) for row in qualification_rows),
                             sum(len(row[5]) for row in qualification_rows)]}))"""


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


@lru_cache(maxsize=1)
def _oracle():
    return run_path(str(VERIFICATION / 'm4_dense_panel_sweep_001/truth/panel_truth.py'))


def live_rows(source):
    rows = []
    for obj in source['objects']:
        evaluated = obj.get('evaluated', obj)
        vertices = evaluated.get('vertices_world_m', evaluated['vertices'])
        rows.append([obj['name'], obj['object_id'], obj['instance_id'], obj['visible_get'], vertices, evaluated['triangles']])
    return sorted(rows)


def read_current(call, source):
    result = call('execute_python', {'code': NATIVE_READ})
    data = json.loads(json.loads(result['content'][0]['text'])['stdout'])
    keys = ('asset_sha256', 'asset_copy', 'frame', 'subframe', 'scale_length', 'pid', 'scene', 'view_layer_id')
    require(all(data['source'][key] == source['source'][key] for key in keys), 'ordinary_scene_identity_changed')
    digest = sha256(json.dumps(live_rows(source), separators=(',', ':')).encode()).hexdigest()
    require(data['sha256'] == digest and data['counts'] == EXPECTED_COUNTS and data['source_ref'],
            'ordinary_ordered_evaluated_geometry_or_identity_changed')
    return data


def present_geometry(source):
    rows = live_rows(source)
    dimensions = [len(rows), sum(len(row[4]) for row in rows), sum(len(row[5]) for row in rows)]
    require(dimensions == EXPECTED_COUNTS and all(len({row[key] for row in rows}) == len(rows) for key in (0, 1, 2)),
            'qualified_mesh_dimensions_or_identity_changed')
    require(source['display_object_mask'] == [True] * len(rows) and all(row[3] is True for row in rows),
            'qualified_fixture_requires_complete_display')
    stamp = source['source']
    require((stamp['frame'], stamp['subframe'], stamp['scale_length']) == (1, 0, 1), 'qualified_mesh_frame_or_units_changed')
    return {name: (tuple(tuple(map(F, point)) for point in vertices), tuple(tuple(face) for face in triangles))
            for name, _, _, _, vertices, triangles in rows}


def measure(geometry, target):
    source = target['center_exact']
    xmin, ymin, z = target['corners'][0]
    xmax, ymax, _ = target['corners'][2]
    bounds = [(min(c), max(c)) for c in zip(*target['corners'], strict=True)]
    require(all(a < b for a, b in ((xmin, xmax), (ymin, ymax))) and source[2] == z,
            'source_measurement_patch_axes_changed')
    vertices, faces = geometry[REFERENCE]
    cap_z = z + F(1, 8)
    witness = source[:2] + (cap_z,)
    cap_faces = []
    lower_bounds = []
    oracle = _oracle()
    for index, face in enumerate(faces):
        a, b, c = (vertices[i] for i in face)
        face_bounds = [(min(axis), max(axis)) for axis in zip(a, b, c, strict=True)]
        lower = sum(max(0, lo - limit_hi, limit_lo - hi) ** 2
                    for (lo, hi), (limit_lo, limit_hi) in zip(bounds, face_bounds, strict=True))
        lower_bounds.append(lower)
        if a[2] == b[2] == c[2] == cap_z:
            sides = [oracle['cross'](oracle['sub'](q, p), oracle['sub'](witness, p))[2]
                     for p, q in ((a, b), (b, c), (c, a))]
            if min(sides) >= 0 or max(sides) <= 0:
                cap_faces.append(index)
    require(cap_faces and min(lower_bounds) == F(1, 64), 'exact_whole_reference_bound_or_witness_changed')
    return {'object': target['object_name'], 'source_triangle_indices': target['source_triangle_indices'],
            'reference': REFERENCE, 'distance_m': 0.125, 'distance_exact_m': '1/8',
            'direction_world': [0, 0, 1], 'a': list(map(float, source)), 'b': list(map(float, witness)),
            'attaining_reference_triangles': cap_faces, 'reference_triangles_checked': len(faces)}


def certify_cover(geometry, target, blocker, views):
    """Prove all target rays in each direction reach the interior of a real cover."""
    oracle = _oracle()
    vertices, triangles = geometry[blocker]
    height = max(vertex[2] for vertex in vertices)
    faces = [i for i, face in enumerate(triangles) if all(vertices[j][2] == height for j in face)]
    normal_sum = [0, 0, 0]
    for i in faces:
        a, b, c = (vertices[j] for j in triangles[i])
        normal = oracle['cross'](oracle['sub'](b, a), oracle['sub'](c, a))
        normal_sum = [u + v for u, v in zip(normal_sum, normal, strict=True)]
    rectangle = oracle['boundary_rectangle'](vertices, triangles, faces, tuple(normal_sum))
    require(rectangle is not None, 'named_cover_is_not_a_current_rectangle/' + blocker)
    corners, _ = rectangle
    xs, ys = ({point[axis] for point in corners} for axis in (0, 1))
    require(len(xs) == len(ys) == 2 and height > target['corners'][0][2], 'named_cover_footprint_or_depth_changed/' + blocker)
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    proofs = {}
    for view in views:
        dx, dy, dz = oracle['DIRECTIONS'][view]
        distances = [(height - z) / dz for x, y, z in target['corners']]
        ray_hits = [(x + depth * dx, y + depth * dy)
                    for (x, y, _), depth in zip(target['corners'], distances, strict=True)]
        margins = [min(x - xmin, xmax - x, y - ymin, ymax - y) for x, y in ray_hits]
        require(min(margins) > 0, 'target_projection_not_strictly_covered/' + blocker + '/' + view)
        proofs[view] = {'cover_object_name': blocker, 'cover_triangles': faces,
                        'cover_height_exact_m': str(height), 'minimum_containment_margin_exact_m': str(min(margins))}
    return proofs


def certify_geometry(source):
    geometry = present_geometry(source)
    oracle = _oracle()
    rows = {}
    for name, mesh in geometry.items():
        components, normals = oracle['partition'](mesh)
        for (normal, _), component in components:
            if normal != (0, 0, 1):
                continue
            twice_area = sum(normals[index][2] for index in component)
            area = twice_area / 2
            if not RANGE[0] <= area <= RANGE[1]:
                continue
            rectangle = oracle['boundary_rectangle'](*mesh, component, (0, 0, twice_area))
            if rectangle is None:
                continue
            corners, _indices = rectangle
            require(name not in rows, 'unexpected_multiple_target_areas_for_object/' + name)
            direction_proofs = {}
            for view, direction in oracle['DIRECTIONS'].items():
                proof = oracle['visibility'](geometry, name, component, corners, normal, direction)
                direction_proofs[view] = proof | {'tested_other_triangles': EXPECTED_COUNTS[2] - len(component)}
            center = tuple((a + b) / 2 for a, b in zip(corners[0], corners[2], strict=True))
            rows[name] = {'object_name': name, 'source_triangle_indices': component, 'area_exact_m2': str(area),
                          'center_world_m': list(map(float, center)), 'center_exact': center, 'corners': corners,
                          'directions': direction_proofs}
    require(set(rows) == EXPECTED_TARGETS and all(row['source_triangle_indices'] == [0, 1]
            and row['area_exact_m2'] == '1/256' for row in rows.values()), 'actual_full_scene_target_components_changed')
    occluded = rows['S034']['directions']
    require(all(not proof['whole_region_clear'] and any(hit['object_name'] == REFERENCE for hit in proof['positive_area_occluders'])
                for proof in occluded.values()), 'six_views_require_current_reference_cover_positive_area')
    switch = rows['S055']['directions']
    require(switch['LEFT']['whole_region_clear'] and all(any(hit['object_name'] == 'S019'
            for hit in switch[view]['positive_area_occluders']) for view in ('SCENE', 'TOP')), 'current_occluded_then_LEFT_switch_changed')
    require(rows['S021']['directions']['TOP']['whole_region_clear'], 'current_open_target_TOP_changed')
    covering = {'S034': certify_cover(geometry, rows['S034'], REFERENCE, occluded),
                'S055': certify_cover(geometry, rows['S055'], 'S019', ('SCENE', 'TOP'))}
    target = min(rows.values(), key=lambda row: row['center_exact'][0])
    require(target['object_name'] == 'S034', 'leftmost_target_identity_changed')
    distance = measure(geometry, target)
    for row in rows.values():
        row.pop('center_exact')
        row['corners'] = [list(map(float, corner)) for corner in row['corners']]
    return {'counts': EXPECTED_COUNTS, 'regions': rows, 'measurement': distance, 'strict_covering': covering}


def _content_blocks(content):
    return content['content'] if isinstance(content, dict) else content


def _check_attachment(content, ref, path, raw_bytes, digest):
    blocks = _content_blocks(content)
    indices = [i for i, block in enumerate(blocks) if block['type'] == 'text' and block['text'].startswith(ref + ' ')]
    require(len(indices) == 1 and indices[0] + 1 < len(blocks), 'no_unique_caption_for_current_frame/' + ref)
    index = indices[0]
    caption = json.loads(blocks[index]['text'].split('\n', 1)[1])
    image = blocks[index + 1]
    declared = Path(caption['local_image_path'])
    require(declared.is_absolute() and str(declared) == str(path)
            and caption['image_sha256'] == digest and image['type'] == 'image' and image['mimeType'] == 'image/png'
            and base64.b64decode(image['data'], validate=True) == raw_bytes, 'same_slot_attachment_original_bytes_or_caption_changed')


def prove_image(folder, owner, ref, target, content=None, *, source, geometry=None):
    """Return geometry and actual pixels separately, including failed pixel gates."""
    import numpy as np
    from PIL import Image

    folder = Path(folder).resolve(strict=True)
    row = owner.runtime.device.by_ref[ref]
    names = row['object_names']
    objects = {o[0]: o[1:] for o in live_rows(source)}
    require(len(names) == len(objects) and set(names) == set(objects)
            and row['object_ids'] == [objects[name][0] for name in names]
            and row['object_instance_ids'] == [objects[name][1] for name in names]
            and row['display_object_mask'] == [objects[name][2] for name in names], 'original_frame_current_roster_or_viewport_identity_changed')
    offsets = [0]
    for name in names:
        offsets.append(offsets[-1] + len(objects[name][-1]))
    require(row['source_face_offsets'] == offsets, 'original_frame_source_face_offsets_changed')
    view = row['view_name']
    pose = row['pose']
    direction = _oracle()['DIRECTIONS'][view]
    geometry = geometry if geometry is not None else certify_geometry(source)
    region = geometry['regions'][target]
    require(tuple(pose['direction_rational']) == direction and pose['name'] == view
            and pose.get('projection', 'orthographic') == 'orthographic', 'rational_frame_view_mismatch')
    modelview, projection = [np.asarray(pose[key], dtype=np.float64) for key in ('view_matrix', 'projection_matrix')]
    require(modelview.shape == projection.shape == (4, 4) and np.isfinite(modelview).all() and np.isfinite(projection).all()
            and np.allclose(modelview[2, :3], np.asarray(direction) / sqrt(sum(i*i for i in direction)),
                            atol=1e-12, rtol=0), 'actual_frame_camera_direction_mismatch')
    points = np.asarray([corner + [1.0] for corner in region['corners']])
    ndc = points @ modelview.T @ projection.T
    inside = bool(np.all(ndc[:, 3] > 0) and np.all(np.abs(ndc[:, :3]) < ndc[:, 3, None]))
    png, npz = (Path(row[key]).resolve(strict=True) for key in ('PNG', 'NPZ'))
    require(all(path.is_relative_to(folder) for path in (png, npz)), 'original_frame_artifact_outside_slot')
    raw_png, raw_npz = png.read_bytes(), npz.read_bytes()
    digest, arrays_digest = sha256(raw_png).hexdigest(), sha256(raw_npz).hexdigest()
    require((digest, arrays_digest) == (row['PNG_sha256'], row['NPZ_sha256']), 'original_frame_artifact_hash_changed')
    if content is not None:
        _check_attachment(content, ref, png, raw_png, digest)
    with np.load(BytesIO(raw_npz), allow_pickle=False) as data:
        rgb, owners, ids, depth = (data[key] for key in ('color', 'owners', 'triangle_ids', 'depth'))
        require(data['face_patch_offsets'].tolist() == offsets
                and data['display_object_mask'].tolist() == row['display_object_mask'], 'original_array_scope_mismatch')
    with Image.open(BytesIO(raw_png)) as image:
        require(image.format == 'PNG' and image.mode == 'RGB' and list(image.size) == pose['size_px']
                and np.array_equal(np.asarray(image), rgb), 'original_PNG_does_not_match_raster_RGB')
    require(owners.shape == ids.shape == depth.shape == rgb.shape[:2]
            and np.issubdtype(owners.dtype, np.signedinteger) and np.issubdtype(ids.dtype, np.signedinteger)
            and np.all((owners >= -1) & (owners < len(names))) and np.array_equal(owners >= 0, ids >= 0),
            'invalid_original_raster_pixel_ownership')
    fg = owners >= 0
    limits = np.asarray(offsets)
    require(np.all((ids[fg] >= limits[owners[fg]]) & (ids[fg] < limits[owners[fg] + 1]))
            and np.all(np.isfinite(depth[fg]) & (depth[fg] > 0)), 'pixel_depth_or_source_faces_differ_from_owner')
    slot = names.index(target)
    selected = region['source_triangle_indices']
    per_face = {str(face): int(np.count_nonzero((owners == slot) & (ids == offsets[slot] + face))) for face in selected}
    mask = (owners == slot) & np.isin(ids, [offsets[slot] + face for face in selected])
    boundary = np.zeros_like(mask)
    rgb_i32 = rgb.astype(np.int32)
    for a, b in (((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                 ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
        delta = rgb_i32[a] - rgb_i32[b]
        edges = (mask[a] != mask[b]) & (np.sum(delta * delta, axis=2) >= 24**2)
        boundary[a] |= edges
        boundary[b] |= edges
    surface_pixels, contrast = sum(per_face.values()), int(np.count_nonzero(mask & boundary))
    unoccluded = region['directions'][view]['whole_region_clear']
    return {'ref': ref, 'frame_identity': row['frame_identity'], 'view': view, 'scope_id': row['scope_id'],
            'origin': row['origin'], 'object_name': target, 'source_triangle_indices': selected,
            'path': png.as_posix(), 'bytes': len(raw_png), 'sha256': digest, 'arrays_sha256': arrays_digest,
            'selected_surface_pixels': surface_pixels, 'contrasting_boundary_pixels': contrast,
            'per_face_pixels': per_face, 'all_corners_in_frame': inside, 'geometrically_unoccluded': unoccluded,
            'pixel_gate_passed': surface_pixels >= 16 and contrast >= 4,
            'complete': inside and unoccluded and surface_pixels >= 16 and contrast >= 4,
            'verified_native_image_block': content is not None}


def solve_native(call, owner, source, folder):
    current = read_current(call, source)
    geometry = certify_geometry(source)
    common = call('render_views', {'names': ['SCENE'], 'include_images': True})
    frame, = json.loads(common['content'][0]['text'])['frames']
    full = prove_image(folder, owner, frame['ref'], 'S021', common, source=source, geometry=geometry)
    require(frame['source_ref'] == current['source_ref'] and full['all_corners_in_frame'] and full['geometrically_unoccluded']
            and not full['pixel_gate_passed'], 'global_SCENE_needs_real_pixel_shortfall_on_geometrically_available_patch')
    images = {'global_S021_pixel_shortfall': full}
    for target, view in (('S021', 'SCENE'), ('S055', 'LEFT')):
        center = geometry['regions'][target]['center_world_m']
        local = call('render_local', {'direction': view, 'target_world_m': center, 'view_span_m': 0.125, 'include_image': True})
        frame = json.loads(local['content'][0]['text'])['frame']
        check = prove_image(folder, owner, frame['ref'], target, local, source=source, geometry=geometry)
        require(frame['source_ref'] == current['source_ref'] and check['complete'], 'ordinary_local_original_incomplete/' + target)
        images[f'local_{target}_{view}'] = check
    return {'passed': True, 'common_source': current, 'geometry': geometry, 'images': images, 'rasters': 3}
