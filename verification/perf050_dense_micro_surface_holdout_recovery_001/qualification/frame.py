"""Independently verify original product pixels against a closed capture and frame scope."""

from hashlib import sha256
from io import BytesIO
import json
from math import sqrt
from pathlib import Path
from runpy import run_path


PRIOR = Path(__file__).resolve().parents[2] / 'perf050_dense_micro_surface_holdout_001/qualification'
NATIVE = run_path(str(PRIOR / 'native.py'))
require = NATIVE['require']


def digest(data):
    return sha256(data).hexdigest()


def fingerprint(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode('utf8'))


def frame_participants(row, frame, binding, capture, source, parent=None):
    """Return the effective display order only when source, scope and view layer agree."""
    keys = ('capture_state', 'document_epoch', 'scene_revision', 'objects')
    require(type(row.get('scope_id')) is str and frame.get('scope_id', 'global') == row['scope_id']
            and frame['host_binding_sha256'] == binding['binding_sha256']
            and row['source_ref'] == 'product-binding:' + binding['binding_sha256']
            and frame['frame_identity'] == row['frame_identity'] and frame['image_ref'] == row['ref']
            and row['view_name'] == frame['view_name'] and row['pose'] == frame['pose'],
            'product_frame_scope_identity_mismatch')
    if parent is not None:
        require(parent['capture_scope'] == 'complete_scene_meshes' and binding['capture_scope'] == 'same_capture_region_view'
                and binding['parent_binding_sha256'] == parent['binding_sha256']
                and binding['parent_source_binding_sha256'] == parent['source_binding_sha256']
                and all(binding[key] == parent[key] for key in keys), 'product_local_scope_parent_binding_mismatch')
    else:
        require(binding['capture_scope'] == 'complete_scene_meshes', 'product_global_or_explicit_scope_required')
    shape = capture['host_identity']
    require(binding['capture_state'] == capture['capture_state'] and binding['scene_revision'] == capture['revision']
            and binding['document_epoch'] == shape['document_epoch']
            and shape['capture_scope'] == 'complete_scene_meshes',
            'product_frame_capture_generation_mismatch')
    if 'source_revision' in frame:
        require(frame['source_revision'] == capture['revision'], 'product_frame_source_revision_mismatch')

    scope_objects = binding['objects']
    names = [item['object_name'] for item in scope_objects]
    ids = [item['host_id'] for item in scope_objects]
    instances = [item['instance_id'] for item in scope_objects]
    require([item['object_index'] for item in scope_objects] == list(range(len(names)))
            and (row['object_names'], row['object_ids'], row['object_instance_ids']) == (names, ids, instances)
            and shape['object_instances'] == dict(zip(ids, instances, strict=True))
            and [(item['name'], item['object_id']) for item in capture['meshes']] == list(zip(names, ids, strict=True)),
            'product_scope_object_or_instance_mapping_mismatch')
    native = {item['object_id']: item for item in source['objects']}
    require(len(native) == len(source['objects']) == len(ids) == len(set(ids)) and set(native) == set(ids),
            'product_scope_native_roster_mismatch')
    snapshot = capture.get('display_snapshot') or {}
    require(snapshot.get('schema') == 'blender-viewport-display-v1' and snapshot.get('scope') == 'active_view_layer'
            and snapshot.get('status') == 'captured'
            and snapshot['sha256'] == fingerprint({key:value for key,value in snapshot.items() if key != 'sha256'})
            and snapshot['view_layer'] == {'name':source['source']['view_layer'], 'instance_id':source['source']['view_layer_id']},
            'current_closed_capture_display_snapshot_unknown')
    shown = {item['host_id']: item for item in snapshot['objects']}
    require(len(shown) == len(snapshot['objects']) and set(shown) == set(ids), 'current_display_instance_roster_mismatch')
    native_mask = dict(zip((item['object_id'] for item in source['objects']), source['display_object_mask'], strict=True))
    mask, offsets = [], [0]
    for mesh, name, host, instance in zip(capture['meshes'], names, ids, instances, strict=True):
        display, terminal = shown[host], native[host]
        require(display['instance_id'] == terminal['instance_id'] == instance and terminal['name'] == name
                and type(display['visible_get']) is bool
                and display['visible_get'] is terminal['visible_get'] is native_mask[host]
                and mesh['vertices'] == terminal['evaluated']['vertices_world_m']
                and mesh['faces'] == terminal['evaluated']['triangles'], 'current_display_or_ordered_geometry_mismatch/' + name)
        mask.append(display['visible_get'])
        offsets.append(offsets[-1] + len(mesh['faces']))
    require(offsets == row['source_face_offsets'] and mask == row['display_object_mask'],
            'product_frame_participation_or_ordered_source_offsets_mismatch')

    explicit = binding.get('image_scope')
    if explicit is not None:
        require(explicit.get('status') == 'captured' and explicit['identity'] == snapshot['sha256']
                and explicit['view_layer'] == snapshot['view_layer'] and explicit['participation_mask'] == mask
                and frame.get('image_scope') == explicit and frame.get('display_identity') == snapshot['sha256'],
                'explicit_product_image_scope_disagrees_with_current_display')
    else:
        require(not any(key in frame for key in ('image_scope', 'display_identity', 'image_scope_identity')) and all(mask),
                'unmasked_scene_product_cannot_prove_partial_display')
    return mask, offsets, snapshot['sha256'], explicit is not None


def prove_frame(folder, row, frame, binding, capture, native_source, target, content=None, *, geometry=None, parent=None):
    import numpy as np
    from PIL import Image

    participants, offsets, display_sha, masked_form = frame_participants(row, frame, binding, capture, native_source, parent)
    folder = Path(folder).resolve(strict=True)
    png, npz = (Path(frame[key]).resolve(strict=True) for key in ('image_path', 'arrays_path'))
    require(all(path.is_relative_to(folder) for path in (png, npz)) and png == Path(row['PNG']) and npz == Path(row['NPZ']),
            'original_product_frame_outside_slot_or_device_binding')
    png_bytes, arrays = png.read_bytes(), npz.read_bytes()
    png_sha, arrays_sha = digest(png_bytes), digest(arrays)
    require(png_sha == row['PNG_sha256'] == frame['image_sha256'] and arrays_sha == row['NPZ_sha256'] == frame['arrays_sha256'],
            'original_product_frame_artifact_hash_changed')
    if content is not None:
        NATIVE['_check_attachment'](content, row['ref'], png, png_bytes, png_sha)
    with np.load(BytesIO(arrays), allow_pickle=False) as data:
        rgb, owners, ids, depth = (data[key] for key in ('color', 'owners', 'triangle_ids', 'depth'))
        has_mask = 'display_object_mask' in data.files
        if has_mask:
            raw_mask = data['display_object_mask']
            require(raw_mask.dtype == np.bool_ and raw_mask.tolist() == participants, 'NPZ_display_object_mask_disagrees')
        else:
            require(not masked_form and all(participants), 'product_frame_missing_required_explicit_display_mask')
        require(data['face_patch_offsets'].tolist() == offsets, 'original_NPZ_scope_offset_mismatch')

    view, pose = row['view_name'], row['pose']
    direction = NATIVE['_oracle']()['DIRECTIONS'][view]
    require(tuple(pose['direction_rational']) == direction and pose['name'] == view
            and pose['projection'] == 'orthographic', 'product_frame_registered_camera_mismatch')
    candidates = [item for item in binding['camera_specification']['views'] if item['name'] == view]
    camera_keys = ('name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')
    require(len(candidates) == 1 and all(pose[key] == candidates[0][key] for key in camera_keys),
            'product_frame_pose_does_not_match_bound_camera')
    modelview, projection = [np.asarray(pose[key], dtype=np.float64) for key in ('view_matrix','projection_matrix')]
    require(modelview.shape == projection.shape == (4, 4) and np.isfinite(modelview).all() and np.isfinite(projection).all()
            and np.allclose(modelview[2,:3], np.asarray(direction) / sqrt(sum(i*i for i in direction)), atol=1e-12, rtol=0),
            'invalid_original_product_camera_direction')
    with Image.open(BytesIO(png_bytes)) as image:
        require(image.format == 'PNG' and image.mode == 'RGB' and list(image.size) == pose['size_px']
                and np.array_equal(np.asarray(image), rgb), 'product_original_PNG_does_not_match_raster_RGB')

    geometry = geometry or NATIVE['certify_geometry'](native_source)
    region = geometry['regions'][target]
    if parent is not None:
        selected = binding['region_source']
        index = row['object_names'].index(target)
        mesh = capture['meshes'][index]
        require(selected['object_index'] == index and selected['host_id'] == row['object_ids'][index]
                and selected['instance_id'] == row['object_instance_ids'][index]
                and selected['source_triangle_indices'] == region['source_triangle_indices']
                and selected['ordered_geometry_sha256'] == fingerprint({'vertices':mesh['vertices'],'faces':mesh['faces']})
                and selected['parent_binding_sha256'] == parent['binding_sha256']
                and selected['parent_source_binding_sha256'] == parent['source_binding_sha256']
                and all(selected[key] == parent[key] for key in ('capture_state','document_epoch','scene_revision')),
                'product_local_scope_selected_source_mismatch')
    ndc = np.asarray([corner + [1.] for corner in region['corners']]) @ modelview.T @ projection.T
    inside = bool(np.all(ndc[:,3] > 0) and np.all(np.abs(ndc[:,:3]) < ndc[:,3,None]))
    names = row['object_names']
    require(owners.shape == ids.shape == depth.shape == rgb.shape[:2]
            and np.issubdtype(owners.dtype,np.signedinteger) and np.issubdtype(ids.dtype,np.signedinteger)
            and np.all((owners >= -1) & (owners < len(names))) and np.array_equal(owners >= 0, ids >= 0),
            'invalid_product_raster_pixel_ownership')
    fg = owners >= 0
    limits = np.asarray(offsets)
    require(np.all(np.asarray(participants)[owners[fg]]) and np.all((ids[fg] >= limits[owners[fg]]) & (ids[fg] < limits[owners[fg]+1]))
            and np.all(np.isfinite(depth[fg]) & (depth[fg] > 0)), 'product_pixel_sources_depth_or_participation_mismatch')
    slot = names.index(target)
    selected = region['source_triangle_indices']
    per_face = {str(face):int(np.count_nonzero((owners == slot) & (ids == offsets[slot]+face))) for face in selected}
    mask = (owners == slot) & np.isin(ids, [offsets[slot]+face for face in selected])
    boundary = np.zeros_like(mask)
    rgb_i32 = rgb.astype(np.int32)
    for a,b in (((slice(None,-1),slice(None)), (slice(1,None),slice(None))),
                ((slice(None),slice(None,-1)), (slice(None),slice(1,None)))):
        delta = rgb_i32[a] - rgb_i32[b]
        edges = (mask[a] != mask[b]) & (np.sum(delta*delta, axis=2) >= 24**2)
        boundary[a] |= edges
        boundary[b] |= edges
    surface, contrast = sum(per_face.values()), int(np.count_nonzero(mask & boundary))
    clear = region['directions'][view]['whole_region_clear']
    pixels = surface >= 16 and contrast >= 4
    return {'ref':row['ref'],'frame_identity':row['frame_identity'],'scope_id':row['scope_id'],'view':view,'origin':'product',
            'path':png.as_posix(),'sha256':png_sha,'arrays_sha256':arrays_sha,'bytes':len(png_bytes),
            'object_name':target,'source_triangle_indices':selected,'selected_surface_pixels':surface,
            'contrasting_boundary_pixels':contrast,'per_face_pixels':per_face,'all_corners_in_frame':inside,
            'geometrically_unoccluded':clear,'pixel_gate_passed':pixels,'complete':inside and clear and pixels,
            'verified_native_image_block':content is not None,'NPZ_display_mask_present':has_mask,
            'verified_capture_display_sha256':display_sha}
