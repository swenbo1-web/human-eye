"""The compact qualification example runs on the ordinary persistent Python tool."""


def pixel_evidence(frame, region):
    maps = buffers[frame['ref']]
    index = frame['object_names'].index(region['object_name'])
    offset = frame['source_face_offsets'][index]
    wanted = [offset + i for i in region['source_triangle_indices']]
    mask = (maps['owners'] == index) & np.isin(maps['triangle_ids'], wanted)
    image = np.asarray(maps['color'])[:, :, :3].astype(np.int32)
    edge = np.zeros(mask.shape, dtype=bool)
    for center, neighbor in ((np.s_[:, 1:], np.s_[:, :-1]), (np.s_[:, :-1], np.s_[:, 1:]),
                             (np.s_[1:, :], np.s_[:-1, :]), (np.s_[:-1, :], np.s_[1:, :])):
        delta = image[center] - image[neighbor]
        edge[center] |= mask[center] & ~mask[neighbor] & (np.sum(delta * delta, axis=2) >= 24 ** 2)
    return int(mask.sum()), int(edge.sum())


def diagnostic():
    capture = scene_data()
    objects = [{'name': mesh['name'], 'vertices': [tuple(F(float(c)) for c in p) for p in mesh['vertices']],
                'triangles': mesh['triangles'], 'visible': mesh['visible_get']} for mesh in capture['objects']]
    visible = [o for o in objects if o['visible']]
    regions = [part for o in visible for part in component_analysis(o['name'], o['vertices'], o['triangles'])
               if part['eligible']]
    directions = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1), 'RIGHT': (1, 0, 1),
                  'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}
    rows, refs = [], []
    for region in regions:
        normal = region['plane_normal_integer']
        length = sqrt(sum(c*c for c in normal))
        center = [float(c) for c in region['center_world_m']]
        record = {'object_name': region['object_name'], 'triangles': region['source_triangle_indices'],
                  'center_world_m': center, 'area_m2': sqrt(float(region['area_squared_m4'])),
                  'unit_normal': [float(c)/length for c in normal], 'status': 'unknown', 'directions': {}}
        for label, direction in directions.items():
            try:
                proof = prove(visible, region, direction)
            except ValueError as error:
                record['directions'][label] = str(error)
                continue
            frame = render_local(label, center, 0.25, include_image=False)
            surface, boundary = pixel_evidence(frame, region)
            record['directions'][label] = {'surface': surface, 'boundary': boundary}
            if surface >= 16 and boundary >= 4:
                record.update(status='covered', direction=label, ref=frame['ref'],
                              frame_identity=frame['frame_identity'], surface_pixels=surface,
                              contrasting_boundary_pixels=boundary, other_triangles=proof['occluder_triangles_checked'])
                refs.append(frame['ref'])
                break
        rows.append(record)
    read_images(refs)
    print(json.dumps({'source_ref': capture['source_ref'], 'objects': len(objects), 'regions': rows},
                     ensure_ascii=True, separators=(',', ':')))


diagnostic()
