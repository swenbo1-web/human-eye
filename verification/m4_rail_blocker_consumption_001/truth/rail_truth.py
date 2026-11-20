"""Freeze rail endface and blocker truth from existing sealed Blender captures."""

from fractions import Fraction
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import runpy
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
VERIFICATION = HERE.parents[1]
SLOT = Path('D:/he_m4_cross_scale_cold_frustum_001/slots/B1')
MEMBER = 'slots/B1/'
ASSET = Path('D:/he_m4_cross_scale_live_task_001/fixture/main.blend')
ASSET_SHA = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
ARCHIVE_SHA = 'd6cde91c2fa1e92a9c8ec092cc2a70f660f2d9fe541e26ab6085492e0f631236'
INITIAL_SHA = 'd6e3f17c88f8564f72c556c26f2f236c0d56d325c5129ee05b2bf0de2da2171e'
TERMINAL_SHA = '31e69a857baf1f66e33722dec5ef63086565c0fbf3029c39071415782c7a0233'
HELPER = VERIFICATION / 'm4_dense_panel_sweep_001/truth/panel_truth.py'
HELPER_SHA = '2930b3651bede09c47a1e654c03212a45b85780c7cb316da225918d844b26ce6'
PIXEL_HELPER = VERIFICATION / 'm4_cross_scale_live_task_formal_001/scoring/formal.py'
PIXEL_HELPER_SHA = '9489564ac3ac48040a54dbadca2429ec5de29da856e518f78c198b5890d5e041'
COUNTS = {'objects': 21, 'vertices': 148, 'triangles': 184}
AREA = Fraction(1, 4)
BEFORE_AFTER_FIELDS = ('source', 'objects', 'source_face_offsets', 'display_object_mask',
                       'layer_collections', 'scene_cameras')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path, expected=None):
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    require(expected is None or digest == expected, 'fixed_evidence_changed/' + str(path))
    label = path.relative_to(VERIFICATION.parent) if path.is_relative_to(VERIFICATION.parent) else path
    return {'path': label.as_posix(), 'bytes': len(raw), 'sha256': digest}, raw


def read_archived(archive, path, expected=None):
    receipt, raw = pin(path, expected)
    member = MEMBER + path.relative_to(SLOT).as_posix()
    require(archive.read(member) == raw, 'archive_member_does_not_match/' + member)
    return receipt, raw


def load_scene(packet):
    source = packet['source']
    require(source['kind'] == 'actual_owned_Blender_evaluated_mesh' and source['asset_sha256'] == ASSET_SHA
            and source['frame'] == 1 and source['subframe'] == 0 and source['scale_length'] == 1.0
            and source['unit_settings'] == {'length_unit': 'METERS', 'scale_length': 1.0, 'system': 'METRIC'}
            and source['source_index_domain'] == 'zero_based_object_local_current_evaluated_capture_triangle_rows',
            'geometry_source_unbound')
    meshes = {}
    offsets = [0]
    for row in packet['objects']:
        name, evaluated = row['name'], row['evaluated']
        require(name and name not in meshes and row['visible_get'] is True, 'unexpected_display_or_object_identity')
        vertices = tuple(tuple(map(Fraction, point)) for point in evaluated['vertices_world_m'])
        faces = tuple(tuple(face) for face in evaluated['triangles'])
        require(all(len(point) == 3 for point in vertices) and all(len(face) == len(set(face)) == 3 and
                all(type(i) is int and 0 <= i < len(vertices) for i in face) for face in faces),
                'invalid_evaluated_geometry/' + name)
        meshes[name] = (vertices, faces)
        offsets.append(offsets[-1] + len(faces))
    require(offsets == packet['source_face_offsets'] and all(packet['display_object_mask'])
            and len(packet['display_object_mask']) == len(meshes), 'display_or_source_offsets_changed')
    require({'objects': len(meshes), 'vertices': sum(len(v) for v, _ in meshes.values()),
             'triangles': offsets[-1]} == COUNTS, 'fixed_geometry_counts_changed')
    return meshes


def determine(meshes, math):
    partition, make_rectangle = math['partition'], math['boundary_rectangle']
    dot, ranges, vector = math['dot'], math['source_ranges'], math['numeric_vector']
    visibility, directions = math['visibility'], math['DIRECTIONS']
    math['COUNTS']['triangles'] = COUNTS['triangles']
    examined, eligible = [], []
    for name, mesh in meshes.items():
        components, triangle_normals = partition(mesh)
        for (normal, offset), component in components:
            twice_area = tuple(sum(triangle_normals[i][axis] for i in component) for axis in range(3))
            squared = dot(twice_area, twice_area) / 4
            rectangle = make_rectangle(*mesh, component, twice_area)
            qualifies = rectangle is not None and squared == AREA * AREA and normal[2] >= 0
            row = {'object_name': name, 'source_triangle_index_ranges': ranges(component),
                   'plane_normal_integer': normal, 'plane_offset_exact': str(offset),
                   'area_squared_m4_exact': str(squared), 'rectangle_supported': rectangle is not None,
                   'eligible': qualifies}
            examined.append(row)
            if not qualifies:
                continue
            corners, vertex_indices = rectangle
            require(normal in ((1, 0, 0), (-1, 0, 0)), 'eligible_rectangle_is_not_an_X_endface')
            center = tuple((a + c) / 2 for a, c in zip(corners[0], corners[2], strict=True))
            proofs = {name_of_view: visibility(meshes, name, component, corners, normal, direction)
                      for name_of_view, direction in directions.items()}
            for proof in proofs.values():
                for hit in proof['positive_area_occluders']:
                    # The reused overlap routine returns area in the unit rectangle chart.
                    chart_area = Fraction(hit.pop('projected_area_m2_per_basis'))
                    hit['projected_target_plane_area_m2_exact'] = str(AREA * chart_area)
            complete = [view for view, proof in proofs.items() if proof['status'] == 'complete']
            eligible.append(row | {'source_triangle_indices': component, 'vertex_indices': vertex_indices,
                                   'corners_world_m': [vector(point) for point in corners],
                                   'center_world_m': vector(center), 'unit_normal': list(normal),
                                   'area_m2': float(AREA), 'area_squared_m4': str(squared),
                                   'finite_direction_proofs': proofs,
                                   'eligible_complete_views': complete,
                                   'expected_unknown_reason': (
                                       None if complete else 'positive_area_occlusion_all_front_views')})
    return examined, eligible


def paired_ends(eligible):
    by_object = {}
    for region in eligible:
        by_object.setdefault(region['object_name'], []).append(region)
    require(len(eligible) == 4 and len(by_object) == 2, 'rail_roster_outside_expected_domain')
    output = []
    for name, entries in by_object.items():
        left, right = sorted(entries, key=lambda row: row['unit_normal'][0])
        blocked = left['finite_direction_proofs']
        require(left['unit_normal'] == [-1, 0, 0] and right['unit_normal'] == [1, 0, 0]
                and left['center_world_m'][0] < right['center_world_m'][0]
                and left['center_world_m'][1:] == right['center_world_m'][1:],
                'eligible_endfaces_do_not_pair/' + name)
        require([view for view, proof in blocked.items() if Fraction(proof['normal_dot_direction']) > 0] == ['LEFT']
                and blocked['LEFT']['status'] == 'positive_area_occlusion'
                and 'SCENE' in right['eligible_complete_views'], 'fixed_geometric_directions_changed/' + name)
        output.append({'object_name': name, 'negative_x_source_triangle_indices': left['source_triangle_indices'],
                       'positive_x_source_triangle_indices': right['source_triangle_indices']})
    return output


def verify_historic_scene_pixels(archive, terminal, eligible, pins, expected_ref):
    import numpy as np
    from PIL import Image

    device_pin, data = read_archived(archive, SLOT / 'DEVICE_EVIDENCE.json')
    device = json.loads(data)
    require(device['asset_sha256'] == ASSET_SHA and device['terminal_source']['sha256'] == TERMINAL_SHA,
            'historic_device_source_unbound')
    frames = [frame for frame in device['frames'] if frame['view'] == 'SCENE' and frame['scope_id'] == 'global']
    require(len(frames) == 1, 'historic_global_scene_frame_missing_or_ambiguous')
    frame = frames[0]
    require(frame['direction_rational'] == [4, -4, 3] and frame['origin'] == 'product', 'historic_camera_changed')
    png_pin, png = read_archived(archive, Path(frame['PNG']), frame['PNG_sha256'])
    npz_pin, npz = read_archived(archive, Path(frame['NPZ']), frame['NPZ_sha256'])
    require(frame['PNG_bytes'] == len(png) and frame['NPZ_bytes'] == len(npz) and frame['ref'] == expected_ref,
            'historic_frame_identity_changed')
    helper_pin, _ = pin(PIXEL_HELPER, PIXEL_HELPER_SHA)
    helper = runpy.run_path(str(PIXEL_HELPER))
    output = []
    with np.load(BytesIO(npz), allow_pickle=False) as arrays, Image.open(BytesIO(png)) as image:
        require(np.array_equal(np.asarray(image.convert('RGB')), arrays['color'][:, :, :3]), 'historic_png_rgb_differs')
        for row in eligible:
            if row['unit_normal'] != [1, 0, 0]:
                continue
            surface, boundary, points = helper['pixels'](frame, row, terminal, arrays)
            require(helper['in_frame'](frame['pose'], points, (4, -4, 3)), 'historic_endface_outside_camera')
            output.append({'object_name': row['object_name'], 'source_triangle_indices': row['source_triangle_indices'],
                           'surface_pixels': surface, 'contrast_boundary_pixels': boundary,
                           'readable': surface >= 16 and boundary >= 4})
    require(sorted((row['surface_pixels'], row['contrast_boundary_pixels']) for row in output)
            == [(10, 3), (11, 6)], 'historic_global_scene_pixel_counts_changed')
    pins.extend([device_pin, png_pin, npz_pin, helper_pin])
    return {'frame_ref': frame['ref'], 'view': 'SCENE', 'scope_id': 'global', 'rows': output,
            'minimum_surface_pixels': 16, 'minimum_contrast_boundary_pixels': 4, 'minimum_rgb_euclidean': 24}


def main(output):
    asset_pin, _ = pin(ASSET, ASSET_SHA)
    helper_pin, _ = pin(HELPER, HELPER_SHA)
    archive_pin, archive_data = pin(SLOT.parents[1] / 'ORIGINAL_RUNTIME.zip', ARCHIVE_SHA)
    self_pin, _ = pin(Path(__file__).resolve())
    with ZipFile(BytesIO(archive_data)) as archive:
        initial_pin, initial = read_archived(archive, SLOT / 'initial_capture/TERMINAL_SOURCE.json', INITIAL_SHA)
        terminal_pin, terminal = read_archived(archive, SLOT / 'TERMINAL_SOURCE.json', TERMINAL_SHA)
        pins = [self_pin, helper_pin, asset_pin, archive_pin, initial_pin, terminal_pin]
        initial = json.loads(initial)
        terminal = json.loads(terminal)
        require(all(initial[key] == terminal[key] for key in BEFORE_AFTER_FIELDS), 'historic_capture_changed_between_reads')
        meshes = load_scene(terminal)
        math = runpy.run_path(str(HELPER))
        examined, eligible = determine(meshes, math)
        pairs = paired_ends(eligible)
        historic = verify_historic_scene_pixels(archive, terminal, eligible, pins,
            'active-host-image:a79f267430f2db8f9d7bd8616743c14ef2b342f8207bdbb1f59ba7329096bf34')
    document = {'schema': 'm4-rail-blocker-consumption-independent-frozen-truth-v1', 'passed': True,
                'asset_sha256': ASSET_SHA, 'initial_source_sha256': INITIAL_SHA, 'terminal_sha256': TERMINAL_SHA,
                'source_pins': pins, 'initial_terminal_equal_fields': BEFORE_AFTER_FIELDS, 'counts': COUNTS,
                'directions': math['DIRECTIONS'], 'conditions': {'area_m2_exact': str(AREA), 'unit_normal_z_min': 0},
                'all_components': examined, 'eligible': eligible, 'pairs': pairs,
                'historic_global_scene_pixels': historic,
                'source_triangles': 'Object-local zero-based evaluated triangle rows. Each range is inclusive.',
                'visibility': 'Orthographic, positive blocker depth and positive overlap projected to the target plane.'}
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'file': output.as_posix(), 'sha256': pin(output)[0]['sha256'], 'pairs': pairs,
                      'blocker_counts': {row['object_name']: len(row['finite_direction_proofs']['LEFT']['positive_area_occluders'])
                                         for row in eligible if row['unit_normal'] == [-1, 0, 0]},
                      'historic_global_scene_pixels': historic['rows']}, sort_keys=True))


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) == 2 else HERE / 'CURRENT_TRUTH.json')
