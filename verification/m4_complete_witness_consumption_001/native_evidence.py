"""Read optional saved native evidence using pinned NumPy and Pillow."""

import hashlib
import sys


def measure(frame, truth, dependency_root, oracle, cameras_by_name):
    sys.path.insert(0, str(dependency_root))
    import numpy as np
    from PIL import Image

    if frame['pose'] != cameras_by_name[frame['view_name']]:
        raise ValueError('native_frame_camera_binding')
    if oracle.sha(frame['PNG']) != frame['PNG_sha256'] or oracle.sha(frame['NPZ']) != frame['NPZ_sha256']:
        raise ValueError('native_frame_file_binding')
    with np.load(frame['NPZ'], allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    for name, metadata in frame['arrays'].items():
        values = arrays[name]
        if (str(values.dtype) != metadata['dtype'] or list(values.shape) != metadata['shape']
                or values.nbytes != metadata['nbytes']
                or hashlib.sha256(values.tobytes(order='C')).hexdigest() != metadata['sha256']):
            raise ValueError('native_array_metadata:' + name)
    color = arrays['color']
    raw = arrays['triangle_ids']
    owners = arrays['owners']
    if color.dtype != np.uint8 or color.shape != (512, 512, 3) or raw.dtype != np.int32 or raw.shape != (512, 512):
        raise ValueError('native_RGB_raw_schema')
    with Image.open(frame['PNG']) as image:
        image.load()
        if image.mode != 'RGB' or image.size != (512, 512) or image.tobytes() != color.tobytes():
            raise ValueError('native_PNG_RGB_binding')
    region_ids = np.full(raw.shape, -1, dtype=np.int8)
    for region in truth['regions']:
        mask = np.isin(raw, region['global_source_triangle_indices'])
        region_ids[mask] = region['object_index']
    foreground = raw >= 0
    if (np.any(region_ids[foreground] < 0) or np.any(owners[foreground] != region_ids[foreground])
            or np.any(raw[~foreground] != -1) or np.any(owners[~foreground] != -1)):
        raise ValueError('native_raw_object_source_relation')
    rgb = color.astype(np.int32)
    boundary = np.zeros(raw.shape, dtype=bool)
    horizontal = ((region_ids[:, :-1] != region_ids[:, 1:])
                  & (((rgb[:, :-1] - rgb[:, 1:]) ** 2).sum(axis=2) >= 576))
    vertical = ((region_ids[:-1] != region_ids[1:])
                & (((rgb[:-1] - rgb[1:]) ** 2).sum(axis=2) >= 576))
    boundary[:, :-1] |= horizontal
    boundary[:, 1:] |= horizontal
    boundary[:-1] |= vertical
    boundary[1:] |= vertical
    rows = []
    for region in truth['regions']:
        mask = region_ids == region['object_index']
        surface_count = int(np.count_nonzero(mask))
        boundary_count = int(np.count_nonzero(boundary & mask))
        ys, xs = np.nonzero(mask)
        bounds = None
        anchor = None
        if surface_count:
            bounds = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
            distances = (2*xs - bounds[0] - bounds[2])**2 + (2*ys - bounds[1] - bounds[3])**2
            selected = int(np.argmin(distances))
            anchor = [int(xs[selected]), int(ys[selected])]
        geometry = region['views'][frame['view_name']]
        readable = geometry['front_facing'] and surface_count >= 16 and boundary_count >= 4
        rows.append({'roi_id': region['roi_id'], 'object_index': region['object_index'],
                     'view': frame['view_name'], 'surface_pixels': surface_count,
                     'boundary_pixels': boundary_count, 'front_facing': geometry['front_facing'],
                     'readable': readable, 'complete': geometry['complete'],
                     'complete_readable': geometry['complete'] and readable,
                     'bounds': bounds, 'anchor': anchor})
    return {'view_name': frame['view_name'], 'image_ref': frame['ref'], 'rows': rows,
            'raw_region_by_pixel': region_ids.reshape(-1).tolist(), 'origin': 'native'}
