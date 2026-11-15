"""Independent current-frame pixel counts from raw triangle winners and RGB."""

from fractions import Fraction


def region_pixels(np, color, mask):
    if color.shape != (512, 512, 3) or mask.shape != (512, 512):
        raise ValueError('fixed_device_shape')
    color = color.astype(np.int32)
    boundary = np.zeros(mask.shape, dtype=bool)
    for inner, outer in (((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                         ((slice(None), slice(None, -1)), (slice(None), slice(1, None))),
                         ((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                         ((slice(None, -1), slice(None)), (slice(1, None), slice(None)))):
        differences = color[inner]-color[outer]
        contrast = (differences*differences).sum(axis=2) >= 24*24
        boundary[inner] |= mask[inner] & ~mask[outer] & contrast
    return {'surface_pixels': int(mask.sum()), 'boundary_pixels': int(boundary.sum())}


def evaluate(np, arrays, object_names, source_face_offsets, truth, view_name):
    color, depth = arrays['color'], arrays['depth']
    owners, triangles = arrays['owners'], arrays['triangle_ids']
    if owners.shape != (512, 512) or triangles.shape != owners.shape or depth.shape != owners.shape:
        raise ValueError('raw_buffer_shape')
    if len(source_face_offsets) != len(object_names)+1 or source_face_offsets[0] != 0:
        raise ValueError('source_face_offsets')
    if any(type(value) is not int for value in source_face_offsets):
        raise ValueError('source_face_offset_type')
    if any(a > b for a, b in zip(source_face_offsets, source_face_offsets[1:])):
        raise ValueError('source_face_offset_order')
    foreground = owners >= 0
    if not np.all((owners == -1) | ((owners >= 0) & (owners < len(object_names)))):
        raise ValueError('raw_object_owner_range')
    if not np.all(triangles[~foreground] == -1) or not np.all(np.isfinite(depth[foreground])):
        raise ValueError('raw_background_or_depth')
    for index, name in enumerate(object_names):
        selected = owners == index
        if not np.all((triangles[selected] >= source_face_offsets[index]) & (triangles[selected] < source_face_offsets[index+1])):
            raise ValueError('raw_triangle_owner_order')
    if object_names.count(truth['object_name']) != 1:
        raise ValueError('unique_target_owner')
    target_index = object_names.index(truth['object_name'])
    offset = source_face_offsets[target_index]
    directions = truth['directions'][view_name]
    result = {}
    for region in truth['regions']:
        global_ids = np.asarray([offset+index for index in region['source_triangle_indices']], dtype=np.int64)
        mask = (owners == target_index) & np.isin(triangles, global_ids)
        pixels = region_pixels(np, color, mask)
        front = sum(Fraction(value)*axis for value, axis in zip(region['unit_normal_world'], directions)) > 0
        complete = region['geometric_classifications'][view_name] == 'complete'
        result[region['id']] = {**pixels, 'front_facing': front, 'geometry_complete': complete,
                               'readable': front and pixels['surface_pixels'] >= 16 and pixels['boundary_pixels'] >= 4,
                               'complete_readable': complete and front and pixels['surface_pixels'] >= 16 and pixels['boundary_pixels'] >= 4}
    return result
