"""Run the native qualification in the ordinary persistent Python namespace."""


def counts(frame, region):
    arrays = buffers[frame['ref']]
    index = frame['object_names'].index(region['object_name'])
    first = frame['source_face_offsets'][index]
    wanted = [first + face for face in region['source_triangle_indices']]
    mask = (arrays['owners'] == index) & np.isin(arrays['triangle_ids'], wanted)
    rgb = np.asarray(arrays['color'])[:, :, :3].astype(np.int32)
    boundary = np.zeros(mask.shape, dtype=bool)
    for a, b in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[1:, :], np.s_[:-1, :]),
                 (np.s_[:, :-1], np.s_[:, 1:]), (np.s_[:, 1:], np.s_[:, :-1])):
        delta = rgb[a] - rgb[b]
        boundary[a] |= mask[a] & ~mask[b] & (np.sum(delta * delta, axis=2) >= 24**2)
    return int(mask.sum()), int(boundary.sum())


def in_frame(frame, region):
    pose = frame['pose']
    direction = np.asarray(DIRECTIONS[frame['view']], dtype=float)
    unit_direction = direction / np.linalg.norm(direction)
    view = np.asarray(pose['view_matrix'])
    projection = np.asarray(pose['projection_matrix'])
    points = np.asarray([[*point, 1.] for point in region['corners_world_m']])
    clip = points @ view.T @ projection.T
    return bool(pose['projection'] == 'orthographic' and np.isfinite(clip).all() and
                np.allclose(view[2, :3], unit_direction, atol=1e-8, rtol=0) and
                np.all(clip[:, 3] > 0) and np.all(np.abs(clip[:, :3] / clip[:, 3, None]) <= 1 + 1e-8))


def qualifies(frame, region, surface, boundary):
    return (frame['view'] in region['eligible_complete_views'] and surface >= 16 and boundary >= 4
            and in_frame(frame, region))


def native_case():
    capture = scene_data()
    objects = capture['objects']
    require(all(obj['visible_get'] for obj in objects), 'dense_fixture_visibility_changed')
    meshes = {obj['name']: (tuple(tuple(map(Fraction, p)) for p in obj['vertices']),
                           tuple(tuple(face) for face in obj['triangles'])) for obj in objects}
    counts_by_kind = {'objects': len(meshes), 'vertices': sum(len(v) for v, _ in meshes.values()),
                      'triangles': sum(len(f) for _, f in meshes.values())}
    require(counts_by_kind == COUNTS, 'dense_fixture_roster_or_denominator_changed')
    parts, regions = determine(meshes)
    frames = render_views(['LEFT', 'SCENE'])
    top, = [row for row in regions if row['plane_normal_integer'][2] > 0]

    def top_readable(candidates):
        return any(qualifies(frame, top, *counts(frame, top)) for frame in candidates)

    if not top_readable(frames):
        frames.extend(render_views(['TOP']))
    if not top_readable(frames):
        frames.append(render_local('TOP', top['center_world_m'], 2.0))
    read_images([frame['ref'] for frame in frames])
    rows = []
    for region in regions:
        pixel_rows = [list(counts(frame, region)) for frame in frames]
        witness = next((index for index, (frame, pair) in enumerate(zip(frames, pixel_rows, strict=True))
                        if qualifies(frame, region, *pair)), None)
        why = ('observed_readable' if witness is not None else 'pixel_evidence_insufficient' if
               region['eligible_complete_views'] else 'positive_area_occlusion_all_front_views')
        rows.append([region['object_name'], region['source_triangle_id_ranges'], region['center_world_m'],
                     region['area_m2'], region['unit_normal'],
                     [region['finite_direction_proofs'][view]['status'] for view in DIRECTIONS],
                     pixel_rows, witness, why])
    dependencies = {'Fraction': str(Fraction(1, 3) + Fraction(1, 6)),
                    'NumPy': int(np.arange(4).sum()), 'Shapely': float(Polygon(
                        [(0, 0), (1, 0), (1, 1), (0, 1)]).area)}
    print(json.dumps({'source_ref': capture['source_ref'], 'counts': counts_by_kind,
                      'component_count': len(parts), 'order': list(DIRECTIONS), 'dependencies': dependencies,
                      'frames': [[frame[key] for key in ('ref', 'view', 'scope_id', 'frame_identity')] for frame in frames],
                      'columns': ['object_name', 'source_triangle_ranges', 'center_world_m', 'area_m2',
                                  'unit_normal', 'directions', 'pixel_counts', 'witness_frame', 'reason'],
                      'rows': rows}, separators=(',', ':'), allow_nan=False))
    return capture['source_ref']


diagnostic_source_ref = native_case()
