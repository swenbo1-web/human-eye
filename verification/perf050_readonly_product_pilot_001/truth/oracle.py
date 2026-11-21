"""Recompute the pilot truth from sealed evaluated Blender meshes and frame bytes."""

from fractions import Fraction as F
from hashlib import sha256
from io import BytesIO
import json
from math import isclose, sqrt
from pathlib import Path
import runpy
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
RECOVERY = V / 'm5_joint_brief_source_projection_recovery_001'
PROJECTION = V / 'm5_joint_brief_source_projection_001'
INSTALL = PROJECTION / 'install/PRODUCT_RUN_BINDING.json'
RUNTIME = Path('D:/he_m5_joint_brief_source_projection_recovery_001')
SLOT = RUNTIME / 'slots/B'
ASSET = SLOT / 'native/input.blend'
TERMINAL = SLOT / 'TERMINAL_SOURCE.json'
PRODUCER = SLOT / 'product_full/call_001/SERVICE_RESULT.json'
TOPOLOGY = V / 'm4_cross_scale_live_task_001/fixture/oracle.py'
CAPTURE = V / 'm4_cross_scale_discovery_001/oracle/check_saved.py'
REPLAY = PROJECTION / 'checks/offline_dense.py'
ASSET_SHA = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
PRODUCT = '3e6a41afc151162bdde1d4ba2247541a4c9616b4'
SOURCE = '4064a22157012db95522501f66cba05f60ee17a34bb3b98ee8e51df8486490bd'
WHEEL = '8808035c973d2193dd32777c2166855402314f6be0f93ca3479c9f1a7ca85e45'
SOURCE_TRIANGLES = (20, 21)
QUERY = {'mode': 'task', 'objects': [{'name': 'N15'}, {'name': 'N23'}],
         'requested_facts': ['surface_proximity']}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    data = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


class Originals:
    def __init__(self, archive, rows):
        self.archive = archive
        self.rows = {row['path']: row for row in rows}
        self.path_pins = {}

    def member(self, path):
        path = Path(path)
        name = path.relative_to(RUNTIME).as_posix()
        row = self.rows[name]
        data = self.archive.read(name)
        current = pin(path)
        require(len(data) == row['bytes'] == current['bytes'] and
                sha256(data).hexdigest() == row['sha256'] == current['sha256'],
                'archived_current_bytes_changed/' + name)
        self.path_pins[str(path.resolve())] = current
        return data

    def read(self, path, digest=None, within=None):
        require(within == SLOT and path.is_relative_to(SLOT) and digest is None, 'foreign_raw_capture')
        return json.loads(self.member(path))

    check = staticmethod(require)


def independent_regions(objects):
    helpers = runpy.run_path(str(TOPOLOGY))
    topology, geometry = helpers['helpers']()
    target = next(row for row in objects if row['name'] == 'N15')
    up = [row for row in topology['component_analysis'](
        target['name'], target['vertices'], target['triangles'])
        if row['rectangle_supported'] and tuple(row['plane_normal_integer']) == (0, 0, 1)]
    ranked = sorted(up, key=lambda row: F(row['area_squared_m4']), reverse=True)
    require(len(ranked) >= 2 and F(ranked[0]['area_squared_m4']) > F(ranked[1]['area_squared_m4']) and
            tuple(ranked[0]['source_triangle_indices']) == SOURCE_TRIANGLES, 'target_rectangle_not_unique')
    region = ranked[0]
    center = tuple(float(F(x)) for x in region['center_world_m'])
    visibility = {}
    tested = sum(len(row['triangles']) for row in objects) - len(SOURCE_TRIANGLES)
    for name, direction in topology['VIEWS'].items():
        hits = helpers['occluders'](objects, region, direction, geometry)
        if not hits:
            geometry['prove'](objects, region, direction)
        visibility[name] = {'target_to_eye_direction': list(direction),
                            'tested_other_triangles': tested, 'clear': not hits, 'occluders': hits}
    require({row['object_name'] for row in visibility['SCENE']['occluders']} == {'N23'} and
            visibility['TOP']['clear'] and visibility['RIGHT']['clear'], 'positive_with_default_blocker_missing')
    return {**region, 'area_m2': sqrt(F(region['area_squared_m4'])), 'center_world_m_numeric': center,
            'next_rectangle_area_m2': sqrt(F(ranked[1]['area_squared_m4'])),
            'corners_world_m': [tuple(map(float, target['vertices'][i])) for i in region['boundary_loops'][0]]}, visibility


def independent_measurement(objects):
    left, right = (next(row for row in objects if row['name'] == name) for name in ('N15', 'N23'))
    a = left['vertices'][3]
    q, r = (right['vertices'][i] for i in (2, 6))
    require(a[1] == min(p[1] for p in left['vertices']) and a[2] == max(p[2] for p in left['vertices']) and
            q[1] == r[1] == max(p[1] for p in right['vertices']) < a[1] and
            q[2] == r[2] == min(p[2] for p in right['vertices']) > a[2], 'axis_lower_bounds_changed')
    require(any(3 in face for face in left['triangles']) and any({2, 6} <= set(face) for face in right['triangles']),
            'nearest_features_not_on_triangle_surface')
    factor = (a[0] - q[0]) / (r[0] - q[0])
    require(0 <= factor <= 1, 'nearest_edge_overlap_missing')
    b = tuple(s + factor * (t - s) for s, t in zip(q, r, strict=True))
    displacement = tuple(t - s for s, t in zip(a, b, strict=True))
    require(displacement[0] == 0, 'pair_does_not_attain_axis_lower_bound')
    squared = sum(value * value for value in displacement)
    distance = sqrt(squared)
    return {'objects': ['N15', 'N23'], 'scope': 'whole_current_evaluated_triangle_surfaces',
            'distance_m': distance, 'squared_distance_m2_exact': str(squared),
            'direction_a_to_b_world': [float(x) / distance for x in displacement],
            'displacement_exact_m': list(map(str, displacement)),
            'witness_a_exact_m': list(map(str, a)), 'witness_b_exact_m': list(map(str, b)),
            'source_features': {'N15_vertex': 3, 'N23_edge_vertices': [2, 6]},
            'proof': 'Signed independent axis bounds over all surface triangles, attained with equal X.',
            'scoring_tolerance': {'distance_m': 0.00005, 'direction_deg': 0.5}}


def pixels(rgb, owners, triangles, object_index):
    import numpy as np

    mask = (owners == object_index) & np.isin(triangles, SOURCE_TRIANGLES)
    boundary = np.zeros(mask.shape, dtype=bool)
    rgb = rgb.astype(np.int32)
    neighbors = set()
    for center, adjacent in ((np.s_[:, 1:], np.s_[:, :-1]), (np.s_[:, :-1], np.s_[:, 1:]),
                             (np.s_[1:, :], np.s_[:-1, :]), (np.s_[:-1, :], np.s_[1:, :])):
        distinct = mask[center] & ~mask[adjacent]
        neighbors.update(np.unique(owners[adjacent][distinct]).tolist())
        boundary[center] |= distinct & (np.sum((rgb[center] - rgb[adjacent]) ** 2, axis=2) >= 24 ** 2)
    return {'surface_pixels': int(mask.sum()), 'contrasting_boundary_pixels': int(boundary.sum()),
            'neighbor_owner_indices': sorted(neighbors)}


def prove_images(terminal, producer, originals, region):
    import numpy as np
    from PIL import Image
    from human_eye_plugin.active_observation import geometry
    from human_eye_plugin.active_observation_host import freeze_cameras
    from human_eye_plugin.active_observation_images import _meshes_from_objects
    from human_eye_plugin.attention_raster import rasterize_attention
    from human_eye_plugin.attention_rendering import _attention_camera

    objects = terminal['objects']
    index = next(i for i, row in enumerate(objects) if row['name'] == 'N15')
    historical = {}
    for frame in producer['constructed_frames'][:2]:
        name = frame['view_name']
        png, npz = (Path(frame[key]) for key in ('image_path', 'arrays_path'))
        saved_png, saved_npz = originals.member(png), originals.member(npz)
        require(sha256(saved_png).hexdigest() == frame['image_sha256'] and
                sha256(saved_npz).hexdigest() == frame['arrays_sha256'], 'frame_bound_artifacts_changed')
        with np.load(BytesIO(saved_npz), allow_pickle=False) as arrays:
            rgb = arrays['color']
            require(np.array_equal(rgb, np.asarray(Image.open(BytesIO(saved_png)))), 'actual_png_arrays_differ')
            historical[name] = {**pixels(rgb, arrays['owners'], arrays['triangle_ids'], index),
                                'original_png': pin(png), 'archived_blender_source': True, 'fresh_offline_raster': False}
    require((historical['SCENE']['surface_pixels'], historical['TOP']['surface_pixels'],
             historical['TOP']['contrasting_boundary_pixels']) == (0, 912, 0), 'historical_pixel_truth_changed')
    meshes, _, _ = geometry({'objects': [
        {'name': row['name'], 'vertices': row['evaluated']['vertices_world_m'], 'triangles': row['evaluated']['triangles']}
        for row in objects]})
    meshes = _meshes_from_objects(meshes)
    pose = next(p for p in freeze_cameras(meshes)['views'] if p['name'] == 'RIGHT')
    offsets = terminal['source_face_offsets']
    ids = tuple(np.arange(a, b, dtype=np.int32) for a, b in zip(offsets, offsets[1:]))
    right = {}
    for name in ('RIGHT', 'RIGHT_LOCAL'):
        local = name == 'RIGHT_LOCAL'
        if local:
            view, projection, _, _ = _attention_camera(meshes, {
                'target_world_m': region['center_world_m_numeric'], 'view_span_m': .19,
                'direction': np.array(pose['target_to_eye_unit']), 'up': np.array(pose['up_seed'])})
        else:
            view, projection = (np.array(pose[field]) for field in ('view_matrix', 'projection_matrix'))
        rgb, _, owners, triangles = rasterize_attention(meshes, view, projection, 512,
            return_owner=True, return_patch_owner=True, face_patch_ids=ids,
            object_mask=tuple(terminal['display_object_mask']))
        result = pixels(rgb, owners, triangles, index)
        expect = (28569, 744) if local else (416, 86)
        require((result['surface_pixels'], result['contrasting_boundary_pixels']) == expect,
                'same_source_alternate_view_pixels_changed/' + name)
        result.update(fresh_offline_raster=True, archived_blender_source=False, raster_size=512)
        png = HERE / f'{name}.png'
        buffer = BytesIO()
        Image.fromarray(rgb).save(buffer, format='PNG')
        if png.is_file():
            require(png.read_bytes() == buffer.getvalue(), 'reconstructed_png_bytes_changed')
        else:
            with png.open('xb') as output:
                output.write(buffer.getvalue())
        result['reconstructed_png'] = pin(png)
        right[name] = result
    return {**historical, **right}


def main():
    binding = read(INSTALL)
    require((binding['preparation_git'], binding['source_sha256'], binding['wheel_sha256'],
             len(binding['source_manifest'])) == (PRODUCT, SOURCE, WHEEL, 143), 'wrong_installed_candidate')
    sys.path[:0] = [binding['install_root'], binding['dependency_root'], str(REPLAY.parent)]
    index_path = RECOVERY / 'RUNTIME_INDEX.json'
    index = read(index_path)
    archive = Path(index['archive']['path'])
    archive_pin = pin(archive)
    require(archive_pin['sha256'] == index['archive']['sha256'] and archive_pin['bytes'] == index['archive']['bytes'],
            'sealed_runtime_archive_changed')
    with ZipFile(archive) as original:
        evidence = Originals(original, index['files'])
        require(sha256(evidence.member(ASSET)).hexdigest() == ASSET_SHA, 'assembly_source_changed')
        terminal = json.loads(evidence.member(TERMINAL))
        producer = json.loads(evidence.member(PRODUCER))
        initial = json.loads(evidence.member(SLOT / 'initial_capture/TERMINAL_SOURCE.json'))
        rows = terminal['objects']
        counts = len(rows), sum(len(r['evaluated']['vertices_world_m']) for r in rows), sum(
            len(r['evaluated']['triangles']) for r in rows)
        require(counts == (28, 416, 744) and terminal['display_object_mask'] == [True] * 28 and
                initial['objects'] == rows and terminal['source']['scale_length'] == 1, 'whole_current_scene_changed')
        capture_helpers = runpy.run_path(str(CAPTURE))
        captures, _ = capture_helpers['decode_captures'](SLOT, binding, evidence)
        capture = capture_helpers['current_capture'](captures, producer['binding'], evidence)
        capture_helpers['source_binding_checks'](capture, producer['binding'], binding, evidence)
        require(all(mesh['name'] == row['name'] and mesh['object_id'] == row['object_id'] and
                    mesh['vertices'] == row['evaluated']['vertices_world_m'] and
                    mesh['faces'] == row['evaluated']['triangles']
                    for mesh, row in zip(capture['meshes'], rows, strict=True)), 'public_parent_not_actual_terminal_source')
        objects = [{'name': r['name'], 'vertices': [tuple(map(F, p)) for p in r['evaluated']['vertices_world_m']],
                    'triangles': r['evaluated']['triangles']} for r in rows]
        region, visibility = independent_regions(objects)
        measurement = independent_measurement(objects)
        frames = prove_images(terminal, producer, evidence, region)
        replay = runpy.run_path(str(REPLAY))['measurement']
        replay.__globals__['QUERY'] = QUERY
        task = replay(producer, capture, binding)
        result = task['facts']['surface_proximity']
        require(result['status'] == 'measured' and
                isclose(result['value']['distance_m'], measurement['distance_m'], rel_tol=0, abs_tol=1e-14) and
                all(isclose(x, y, rel_tol=0, abs_tol=1e-14) for x, y in zip(
                    result['value']['nearest_witness']['direction_a_to_b'], measurement['direction_a_to_b_world'], strict=True)),
                'same_install_current_capture_product_measurement_disagrees')
    source_paths = [Path(__file__), NS / 'inputs/PROMPT.txt', INSTALL, index_path, archive, TOPOLOGY, CAPTURE, REPLAY,
                    PROJECTION / 'checks/offline_decode.py', PROJECTION / 'checks/live_wire_adapter.py',
                    *(V / name for name in runpy.run_path(str(TOPOLOGY))['SOURCES']),
                    HERE / 'RIGHT.png', HERE / 'RIGHT_LOCAL.png']
    pins = {row['path']: row for row in [*(pin(path) for path in source_paths), *evidence.path_pins.values()]}
    result = {'passed': True, 'asset_sha256': ASSET_SHA, 'terminal_source': pin(TERMINAL),
              'asset_origin': 'previously authorized synthetic assembly; unchanged evaluated Blender source',
              'asset_counts': {'objects': counts[0], 'vertices': counts[1], 'triangles': counts[2]},
              'region': region, 'visibility': visibility, 'image_evidence': frames, 'measurement': measurement,
              'product_support': {'same_install_complete_parent_measurement': True, 'whole_surface_fact': task['facts'],
                                  'actual_three_dimensional_source_qualification': True,
                                  'positive_witness_uses_same_install_renderer': True,
                                  'new_Blender_starts': 0, 'new_models': 0, 'offline_rasterizations': 2},
              'source_pins': [pins[path] for path in sorted(pins)]}
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False, default=str).encode() + b'\n'
    path = HERE / 'TRUTH.json'
    if path.is_file():
        require(payload == path.read_bytes(), 'recomputed_receipt_changed')
    else:
        with path.open('xb') as output:
            output.write(payload)
    print('Pilot truth', sha256(payload).hexdigest())


if __name__ == '__main__':
    main()
