"""Read-only image evidence review for the fixed Obj_07 selection."""

import argparse
import base64
from collections import Counter
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image


ASSET = 'b9cf3671bc8cd5b88ed23118f229a6e753eda40802d35a3ad297961e0a9edcf9'
READBACK = Path('D:/he_m4_m5_source_region_001/fixture/READBACK_AFTER_RELOAD.json')
READBACK_SHA = '70baebb4994c57a13c145a79627abb0671aafb161f4837e793ac869e6fd9c62c'
TARGET = 'Obj_07'
FACE_IDS = (0, 1, 2, 3)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def current_geometry(terminal, record=READBACK):
    raw = record.read_bytes()
    require(sha(raw) == READBACK_SHA, 'frozen_readback_changed')
    frozen = {obj['name']: obj for obj in json.loads(raw)['objects']}
    current = {obj['name']: obj for obj in terminal['objects']}
    require(current.keys() == frozen.keys() and len(current) == len(terminal['objects']) == 11,
            'current_geometry_missing_objects')
    for name, obj in current.items():
        for stage in ('native', 'evaluated'):
            mesh, expected = obj[stage], frozen[name][stage]
            world = mesh.get('vertices_world_m', mesh.get('vertices_world'))
            require(world == expected['vertices_world'] and mesh['triangles'] == expected['triangles'],
                    'current_geometry_changed/' + name + '/' + stage)
    return current


def signed(a, b, point):
    return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])


def clip(subject, level):
    if not subject:
        return []
    output = []
    prior = subject[-1]
    before = level(prior)
    for point in subject:
        after = level(point)
        if (before < 0) != (after < 0):
            shift = before / (before - after)
            output.append(tuple(a + shift * (b - a) for a, b in zip(prior, point, strict=True)))
        if after >= 0:
            output.append(point)
        prior, before = point, after
    return output


def area2(polygon):
    return sum(a[0] * b[1] - b[0] * a[1]
               for a, b in zip(polygon, polygon[1:] + polygon[:1]))


def index_meshes(frame, rows):
    names = frame['object_names']
    require(Counter(names) == Counter(rows.keys()), 'full_scene_owner_mapping_required')
    offsets = [0]
    for name in names:
        offsets.append(offsets[-1] + len(rows[name]['evaluated']['triangles']))
    require(offsets == frame['source_face_offsets'], 'current_source_triangle_offsets_changed')
    if all('object_id' in rows[name] for name in names):
        require(frame['object_ids'] == [rows[name]['object_id'] for name in names]
                and frame['object_instance_ids'] == [rows[name]['instance_id'] for name in names]
                and frame['display_object_mask'] == [rows[name]['visible_get'] for name in names],
                'owner_mapping_or_display_not_bound_to_current_terminal')
    require(len(frame['display_object_mask']) == len(names)
            and all(type(flag) is bool for flag in frame['display_object_mask']), 'invalid_display_mask')
    index = names.index(TARGET)
    return index, offsets


def independent_camera_visibility(frame, rows):
    """Compare full projected polygons and depth; sample counts are separate."""
    index_meshes(frame, rows)
    pose = frame['pose']
    view, proj = (np.asarray(pose[key]) for key in ('view_matrix', 'projection_matrix'))
    if (pose['projection'] != 'orthographic' or view.shape != (4, 4) or proj.shape != (4, 4)
            or not np.isfinite(view).all() or not np.isfinite(proj).all()
            or not np.array_equal(view[3], [0, 0, 0, 1])
            or not np.array_equal(proj[:2], [[proj[0, 0], 0, 0, 0], [0, proj[1, 1], 0, 0]])
            or not np.array_equal(proj[3], [0, 0, 0, 1])
            or not (proj[0, 0] > 0 and proj[1, 1] > 0)):
        return {'status': 'unknown', 'reason': 'unsupported_orthographic_camera'}
    coefficients = [list(map(Fraction, row)) for row in view[:3].tolist()]
    near = Fraction(pose.get('near_m', pose.get('near')))
    far = Fraction(pose.get('far_m', pose.get('far')))
    x_half, y_half = (1 / Fraction(float(proj[axis, axis])) for axis in (0, 1))
    faces = {}
    for name, displayed in zip(frame['object_names'], frame['display_object_mask'], strict=True):
        if not displayed:
            continue
        mesh = rows[name]['evaluated']
        positions = mesh.get('vertices_world_m', mesh.get('vertices_world'))
        projected = []
        for point in positions:
            world = tuple(map(Fraction, point)) + (1,)
            x, y, z = (sum(a * b for a, b in zip(row, world, strict=True)) for row in coefficients)
            projected.append((x, y, -z))
        for i, face in enumerate(mesh['triangles']):
            faces[(name, i)] = [projected[k] for k in face]
    blocked, ties, incomplete = [], [], []
    for index in FACE_IDS:
        key = TARGET, index
        selected = faces.get(key)
        if selected is None or area2(selected) == 0 or any(
                not (-x_half < x < x_half and -y_half < y < y_half and near < d < far)
                for x, y, d in selected):
            incomplete.append(index)
            continue
        turn = area2(selected)
        edges = [(a, b) for a, b in zip(selected, selected[1:] + selected[:1])]

        def depth_at(point):
            return sum(v[2] * signed(a, b, point) for v, (a, b) in
                       zip(selected, edges[1:] + edges[:1], strict=True)) / turn

        for other_key, other in faces.items():
            if other_key == key or area2(other) == 0:
                continue
            overlap = clip(clip(other, lambda p: p[2] - near), lambda p: far - p[2])
            for a, b in edges:
                sign = 1 if turn > 0 else -1
                overlap = clip(overlap, lambda p: sign * signed(a, b, p))
            if area2(overlap) == 0:
                continue
            deltas = [p[2] - depth_at(p) for p in overlap]
            if min(deltas) < 0:
                blocked.append({'selection_triangle': index, 'object': other_key[0], 'triangle': other_key[1]})
            elif all(delta == 0 for delta in deltas):
                ties.append({'selection_triangle': index, 'object': other_key[0], 'triangle': other_key[1]})
    return {'status': 'positive_area_occlusion' if blocked else 'unknown' if incomplete or ties else
            'projected_open_interiors_clear', 'occlusion_witnesses': blocked,
            'equal_depth_overlap': ties, 'out_of_frustum_or_zero_projected_area_triangles': incomplete,
            'scope': 'full participating scene; independent rational polygon clipping of the actual orthographic frame; clear open interiors do not settle all projected edge ties or establish model reasoning'}


def frame_arrays(frame, rows, slot):
    index, offsets = index_meshes(frame, rows)
    png, npz = (Path(frame[key]) for key in ('PNG', 'NPZ'))
    for path in (png, npz):
        require(path.is_absolute() and path.resolve(strict=True).is_relative_to(slot),
                'frame_artifact_outside_current_slot')
    raw, data = png.read_bytes(), npz.read_bytes()
    require(sha(raw) == frame['PNG_sha256'] and sha(data) == frame['NPZ_sha256'],
            'original_PNG_or_owner_arrays_digest_changed')
    with Image.open(BytesIO(raw)) as image, np.load(BytesIO(data), allow_pickle=False) as arrays:
        require(image.format == 'PNG' and image.size == (512, 512)
                and np.array_equal(np.asarray(image.convert('RGB')), arrays['color']),
                'PNG_is_not_the_bound_original_color_buffer')
        owners, ids, depth = (arrays[key] for key in ('owners', 'triangle_ids', 'depth'))
        require(owners.shape == ids.shape == depth.shape == (512, 512)
                and owners.dtype == ids.dtype == np.int32 and depth.dtype == np.float64
                and arrays['face_patch_offsets'].tolist() == offsets,
                'raster_buffer_mapping_cannot_be_rebuilt')
        if 'display_object_mask' in arrays:
            require(arrays['display_object_mask'].tolist() == frame['display_object_mask'],
                    'display_mask_changed')
        mask = (owners == index) & np.isin(ids, [offsets[index] + face for face in FACE_IDS])
        require(np.isfinite(depth[mask]).all(), 'selection_depth_must_be_finite')
        counts = Counter(int(face) - offsets[index] for face in ids[mask])
        y, x = np.nonzero(mask)
        bounds = [int(x.min()), int(y.min()), int(x.max()), int(y.max())] if x.size else None
    return raw, {'pixels_by_source_triangle': {i: counts.get(i, 0) for i in FACE_IDS},
                 'visible_source_triangle_indices': sorted(counts),
                 'unseen_source_triangle_indices': sorted(set(FACE_IDS) - counts.keys()),
                 'selected_surface_pixels': sum(counts.values()), 'visible_pixel_bounds': bounds}


def packet_refs(packet, frame, original):
    """Find actual image blocks tied to this ref or an explicitly delivered path."""
    body = packet.get('result', packet)
    blocks = body.get('content', [])
    if body.get('isError') is True:
        return []
    matches = []
    for index, block in enumerate(blocks):
        if block['type'] != 'text':
            continue
        text = block['text']
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            line, _, rest = text.partition('\n')
            if line.startswith(frame['ref'] + ' (') and rest:
                try:
                    declaration = json.loads(rest)
                except json.JSONDecodeError:
                    continue
                if declaration.get('image_sha256') == frame['PNG_sha256']:
                    matches.append((index + 1, declaration.get('local_image_path')))
            continue
        if type(value) is not dict:
            continue
        for sequence, entry in enumerate(value.get('frames', []), 1):
            if entry.get('image_ref') == frame['ref'] and entry.get('image_sha256') == frame['PNG_sha256']:
                matches.append((sequence, entry.get('image_path')))
        images = value.get('images', [])
        if isinstance(images, list):
            for entry in images:
                if entry.get('image_ref') == frame['ref'] and entry.get('image_sha256') == frame['PNG_sha256']:
                    matches.append((entry['image_block_index'], entry.get('local_image_path')))
    return [{'content_image_index': i, 'declared_path': p} for i, p in matches
            if 0 <= i < len(blocks) and blocks[i].get('type') == 'image'
            and blocks[i].get('mimeType') == 'image/png'
            and base64.b64decode(blocks[i]['data'], validate=True) == original]


def same_path(path, frame, slot, raw):
    if path is None:
        return None
    p = Path(path)
    return (p.is_absolute() and p.exists() and p.resolve(strict=True) == Path(frame['PNG']).resolve(strict=True)
            and p.resolve(strict=True).is_relative_to(slot) and p.read_bytes() == raw)


def review(slot, ref, packets=(), explicit_path=None):
    slot = slot.resolve(strict=True)
    device = read(slot / 'DEVICE_EVIDENCE.json')
    closed = read(slot / 'RUNTIME_CLOSE.json')
    result = read(slot / 'SLOT_RESULT.json')
    terminal = read(slot / 'TERMINAL_SOURCE.json')
    source = terminal['source']
    require(device['asset_sha256'] == source['asset_sha256'] == result['asset_sha256'] == ASSET
            and device['label'] == result['label'] == slot.name
            and not closed['errors'] and result['closure_verification']['passed']
            and result['independent_before_after']['passed'],
            'same_slot_not_closed_or_wrong_asset')
    rows = current_geometry(terminal)
    frame, = [row for row in device['frames'] if row['ref'] == ref]
    raw, samples = frame_arrays(frame, rows, slot)
    require(all(p.resolve(strict=True).is_relative_to(slot) for p in packets), 'reply_outside_same_slot')
    delivery = [dict(packet=str(p), **found) for p in packets for found in packet_refs(read(p), frame, raw)]
    for record in delivery:
        record['declared_path_matches_original'] = same_path(record['declared_path'], frame, slot, raw)
    return {'origin': frame['origin'], 'view': frame['view_name'], 'source_ref': frame['source_ref'],
            'ref': frame['ref'], 'frame_identity': frame['frame_identity'], 'sha256': sha(raw),
            'PNG': frame['PNG'], 'original_PNG_NPZ_RGB_and_current_source_bound': True,
            'bound_actual_image_deliveries': delivery,
            'explicit_final_path_resolves_to_same_original_PNG': same_path(explicit_path, frame, slot, raw),
            'samples': samples, 'independent_continuous_geometry': independent_camera_visibility(frame, rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', type=Path, required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--reply', type=Path, action='append', default=[])
    parser.add_argument('--final-image-path')
    args = parser.parse_args()
    print(json.dumps(review(args.slot, args.ref, args.reply, args.final_image_path), indent=2))


if __name__ == '__main__':
    main()
