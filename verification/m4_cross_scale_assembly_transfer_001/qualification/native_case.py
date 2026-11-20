"""Execute on the persistent ordinary Python entry in qualification only."""


def counts(frame, region):
    arrays = buffers[frame['ref']]
    index = frame['object_names'].index(region['object_name'])
    source = [frame['source_face_offsets'][index] + i for i in region['source_triangle_indices']]
    mask = (arrays['owners'] == index) & np.isin(arrays['triangle_ids'], source)
    rgb = np.asarray(arrays['color'])[:, :, :3].astype(np.int32)
    boundary = np.zeros(mask.shape, dtype=bool)
    for center, neighbor in ((np.s_[:, 1:], np.s_[:, :-1]), (np.s_[:, :-1], np.s_[:, 1:]),
                             (np.s_[1:, :], np.s_[:-1, :]), (np.s_[:-1, :], np.s_[1:, :])):
        delta = rgb[center] - rgb[neighbor]
        boundary[center] |= mask[center] & ~mask[neighbor] & (np.sum(delta * delta, axis=2) >= 24**2)
    return int(mask.sum()), int(boundary.sum())


def diagnose():
    capture = scene_data()
    objects = [{'name': obj['name'], 'vertices': [tuple(map(F, v)) for v in obj['vertices']],
                'triangles': obj['triangles']} for obj in capture['objects'] if obj['visible_get']]
    regions = [row for obj in objects for row in component_analysis(obj['name'], obj['vertices'], obj['triangles'])
               if row['eligible']]
    directions = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1), 'RIGHT': (1, 0, 1),
                  'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}
    rows, refs = [], []
    for region in regions:
        axes = region['plane_normal_integer']
        length = sqrt(sum(c*c for c in axes))
        center = [float(x) for x in region['center_world_m']]
        lower, upper = region['bounds_world_m']
        span = 1.25 * sqrt(sum((hi-lo)**2 for lo, hi in zip(lower, upper)))
        row = {'object_name': region['object_name'], 'triangles': region['source_triangle_indices'],
               'center_world_m': center, 'area_m2': sqrt(float(region['area_squared_m4'])),
               'unit_normal': [float(c)/length for c in axes], 'directions': {}, 'status': 'unknown',
               'witness': None, 'probes': []}
        clear = []
        for view, direction in directions.items():
            try:
                prove(objects, region, direction)
            except ValueError as error:
                row['directions'][view] = str(error)
            else:
                clear.append(view)
                row['directions'][view] = 'complete_geometry'
        row['reason'] = 'pixel_evidence_insufficient' if clear else 'positive_area_occlusion_all_front_views'
        for view in clear:
            frame = render_local(view, center, span, include_image=False)
            surface, boundary = counts(frame, region)
            observation = {'direction': view, 'ref': frame['ref'], 'frame_identity': frame['frame_identity'],
                           'surface_pixels': surface, 'contrasting_boundary_pixels': boundary}
            row['probes'].append(observation)
            if surface >= 16 and boundary >= 4:
                row.update(status='covered', reason='observed_readable', witness=observation)
                refs.append(frame['ref'])
                break
        rows.append(row)
    read_images(refs)
    print(json.dumps({'source_ref': capture['source_ref'], 'objects': len(objects),
                      'vertices': sum(len(o['vertices']) for o in objects),
                      'triangles': sum(len(o['triangles']) for o in objects),
                      'regions': rows}, separators=(',', ':')))


diagnose()
