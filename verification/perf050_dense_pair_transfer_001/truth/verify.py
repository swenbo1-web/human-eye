"""Independent dense rectangular-region and whole-surface witness checks."""

import argparse
from copy import deepcopy
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
from runpy import run_path
import sys


HERE = Path(__file__).resolve().parent
ASSET = Path('D:/he_m4_target_002/assets_01/main.blend')
ASSET_SHA = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
FROZEN_SOURCE = ASSET.with_name('main.GEOMETRY.json')
FROZEN_SOURCE_SHA = 'a48ef1b1634e1bbe66fbb49d47899581432d6bf4aebae5577ea5abdebf4b774d'
ARCHIVE = 'm4_dense_panel_sweep_formal_001'
ARCHIVE_ROOT = Path('D:/he_' + ARCHIVE)
ARCHIVE_SHA = '31c389c0815507a2a71c01073e99f9f445758e0d4f3afb2409bd3672fecd0dbf'
ORDINARY = 'perf050_target_observation_first_image_p2'
CANDIDATE = 'm1_pair_distance_entry_001'
PLANE = 'm4_dense_panel_sweep_001/truth/panel_truth.py'
ORIGIN = 'm5_observe_measure_001/oracle.py'
DECODER = 'm4_cross_scale_discovery_001/oracle/check_saved.py'
OLD_INSTALL = 'm4_dense_region_brief_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE_INSTALL = CANDIDATE + '/install/PRODUCT_RUN_BINDING.json'
TARGET = 'M4_Far_00'
REFERENCE = 'M4_Focal'
TARGET_FACES = (512, 513)
COUNTS = {'objects': 14, 'vertices': 3478, 'triangles': 6148}
EXPECTED_ARCHIVED_IMAGES = {
    'N2': ('TOP', 8, '999cef092eb9e6f49735804bc65739784396776d7d1cd304e78b4c84bc89cf7d', 1521, 152),
    'P1': ('SCENE', 1, '21ed0afc6e7a78b49364f5b888f1f0e03800616b4567f839411efaf5c820fa47', 1197, 138),
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(raw):
    return sha256(raw).hexdigest()


def pin(path, expected=None):
    real = Path(path).resolve(strict=True)
    raw = real.read_bytes()
    checksum = digest(raw)
    require(expected is None or checksum == expected, 'pinned_input_changed/' + str(real))
    return {'path': str(real), 'sha256': checksum, 'bytes': len(raw)}


def repo_path(repo):
    if repo is not None:
        return Path(repo).resolve()
    near = [folder for folder in HERE.parents if (folder / 'verification').is_dir()]
    return near[0] if near else Path.cwd().resolve()


@lru_cache(maxsize=4)
def independent(repo):
    v = Path(repo) / 'verification'
    panel = run_path(str(v / PLANE))
    point = run_path(str(v / ORIGIN))
    pin(FROZEN_SOURCE, FROZEN_SOURCE_SHA)
    meshes = panel['load_meshes'](FROZEN_SOURCE.read_bytes())
    vertices, faces = meshes[TARGET]
    partitions, normals = panel['partition']((vertices, faces))
    (normal, offset), part = next((plane, group) for plane, group in partitions if 512 in group)
    exact_twice_area = tuple(sum(normals[i][axis] for i in part) for axis in range(3))
    corners, vertex_indices = panel['boundary_rectangle'](vertices, faces, part, exact_twice_area)
    require((normal, offset, part, exact_twice_area) == ((0, 0, 1), 2, [512, 513], (0, 0, 2))
            and set(corners) == {(1, 0, 2), (2, 0, 2), (2, 1, 2), (1, 1, 2)},
            'source_target_not_maximal_upward_exact_rectangle')
    lower_x = min(row[0] for row in vertices)
    fv, ff = meshes[REFERENCE]
    pair = ((1, 0, 0), (0, 0, 0))
    top_pair = ((1, 0, 2), (0, 0, 1))
    require(lower_x == 1 and set(p[0] for p in fv) == {0} and max(p[2] for p in fv) == 1
            and all(c[2] == 2 for c in corners), 'source_pair_lower_bound_changed')
    pair_proof = [point['membership'](q, *meshes[o]) for q, o in zip(pair, (TARGET, REFERENCE), strict=True)]
    scope_good = point['membership'](top_pair[0], vertices, [faces[i] for i in TARGET_FACES])
    target_ref = point['membership'](top_pair[1], fv, ff)
    require(all(row['exact_source_triangle_indices'] for row in pair_proof)
            and scope_good['exact_source_triangle_indices'] and target_ref['exact_source_triangle_indices']
            and sum((b-a)**2 for a, b in zip(*pair, strict=True)) == 1
            and sum((b-a)**2 for a, b in zip(*top_pair, strict=True)) == 2,
            'pair_attainment_or_scope_distinction_changed')
    truth = {'pair': [TARGET, REFERENCE], 'whole_distance_m_exact': '1',
             'whole_distance_m': 1.0, 'whole_direction_world': [-1, 0, 0], 'whole_witness_world_m': pair,
             'whole_witness_membership': pair_proof,
             'top_distance_m': math.sqrt(2), 'top_distance_squared_exact': '2',
             'top_witness_world_m': top_pair, 'top_points_membership': [scope_good, target_ref],
             'independent_lower_bound': {'far_min_x': '1', 'focal_x_all': '0',
                 'top_plane_z': '2', 'focal_max_z': '1'},
             'top': {'object_name': TARGET, 'source_triangle_ids': list(TARGET_FACES),
                     'vertex_indices': vertex_indices, 'positive_normal': [0, 0, 1], 'area_m2': 1,
                     'corners_world_m': [[int(x) for x in q] for q in corners]}}
    return panel, point, meshes, truth


def verify_scene(packet, repo=None):
    root = repo_path(repo)
    _, _, wanted, _ = independent(str(root))
    source = packet['source']
    require(source['asset_sha256'] == ASSET_SHA and source['frame'] == 1 and source['subframe'] == 0
            and source['scale_length'] == 1 and source['unit_settings']['system'] == 'METRIC',
            'actual_dense_asset_frame_or_units_changed')
    rows = {row['name']: row for row in packet['objects']}
    require(len(packet['objects']) == len(rows) == 14 and set(rows) == set(wanted)
            and packet['display_object_mask'] == [True] * 14
            and all(row['visible_get'] for row in rows.values()), 'actual_source_roster_or_display_changed')
    for name, row in rows.items():
        obs = row['evaluated']
        expected = (tuple(tuple(map(F, point)) for point in obs['vertices_world_m']),
                    tuple(tuple(face) for face in obs['triangles']))
        require(expected == wanted[name], 'actual_ordered_evaluated_geometry_changed/' + name)
    return {'passed': True, 'counts': COUNTS, 'asset_sha256': ASSET_SHA, 'source_objects': rows}


def frame_direction(frame):
    pose = frame['pose']
    direction = frame['direction_rational']
    require(isinstance(direction, (list, tuple)) and len(direction) == 3 and direction == pose['direction_rational']
            and all(type(value) in (int, float) and math.isfinite(value) for value in direction)
            and any(direction) and pose['projection'] == 'orthographic',
            'actual_frame_direction_or_projection_not_supported')
    d = math.hypot(*direction)
    view = pose['view_matrix']
    require(all(math.isclose(float(coeff), delta/d, rel_tol=0, abs_tol=1e-8)
                for coeff, delta in zip(view[2][:3], direction, strict=True)),
            'actual_frame_direction_disagrees_with_camera_axes')
    return tuple(map(F, direction))


def in_frame(frame, corners):
    pose = frame['pose']
    view, proj = (tuple(tuple(map(F, axis)) for axis in pose[name])
                  for name in ('view_matrix', 'projection_matrix'))
    for point in corners:
        world = (*map(F, point), F(1))
        viewed = tuple(sum(a*b for a, b in zip(row, world, strict=True)) for row in view)
        clip = tuple(sum(a*b for a, b in zip(row, viewed, strict=True)) for row in proj)
        if clip[3] <= 0 or any(abs(coord) > clip[3] for coord in clip[:3]):
            return False
    return True


def qualify_frame(frame, packet, png=None, npz=None, repo=None):
    """Evaluate one actual frame/PNG/arrays against both scoped and full current truth."""
    import numpy as np
    from PIL import Image

    v = repo_path(repo)
    scene = verify_scene(packet, v)
    panel, _, geometry, truth = independent(str(v))
    names = frame['object_names']
    actual = scene['source_objects']
    require(len(set(names)) == len(names) and TARGET in names and set(names) <= set(actual)
            and frame['object_ids'] == [actual[name]['object_id'] for name in names]
            and frame['object_instance_ids'] == [actual[name]['instance_id'] for name in names]
            and frame['display_object_mask'] == [actual[name]['visible_get'] for name in names],
            'actual_frame_mesh_selection_not_bound_to_current_terminal_geometry')
    index = names.index(TARGET)
    offsets = [0]
    for name in names:
        offsets.append(offsets[-1] + len(actual[name]['evaluated']['triangles']))
    require(offsets == frame['source_face_offsets'], 'actual_frame_triangle_offset_table_not_current')
    png = Path(frame['PNG']).read_bytes() if png is None else png
    npz = Path(frame['NPZ']).read_bytes() if npz is None else npz
    require(digest(png) == frame['PNG_sha256'] and digest(npz) == frame['NPZ_sha256'],
            'actual_original_image_or_native_buffers_SHA_differs')
    direction = frame_direction(frame)
    corners = truth['top']['corners_world_m']
    occlusion = panel['visibility'](geometry, TARGET, TARGET_FACES,
                                   [tuple(map(F, point)) for point in corners], (0, 0, 1), direction)
    occlusion['direction'] = list(map(str, direction))
    fitted = in_frame(frame, corners)
    with Image.open(BytesIO(png)) as image, np.load(BytesIO(npz), allow_pickle=False) as arrays:
        require(image.format == 'PNG' and image.size == (512, 512)
                and np.array_equal(np.asarray(image.convert('RGB')), arrays['color'][:, :, :3]),
                'actual_PNG_is_not_original_raster_color_buffer')
        owners, ids, depth = (arrays[key] for key in ('owners', 'triangle_ids', 'depth'))
        require(owners.shape == ids.shape == depth.shape == (512, 512),
                'actual_owner_depth_or_triangle_axis_shapes_differ')
        wanted = [offsets[index] + n for n in TARGET_FACES]
        mask = (owners == index) & np.isin(ids, wanted)
        indices = [int(n) - offsets[index] for n in np.unique(ids[mask])]
        require(np.isfinite(depth[mask]).all(), 'actual_source_selection_depth_not_finite')
        surface = int(np.count_nonzero(mask))
        color = arrays['color'][:, :, :3].astype(np.int32)
        edges = np.zeros(mask.shape, dtype=bool)
        for a, b in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[1:, :], np.s_[:-1, :]),
                     (np.s_[:, :-1], np.s_[:, 1:]), (np.s_[:, 1:], np.s_[:, :-1])):
            delta = color[a] - color[b]
            edges[a] |= mask[a] & ~mask[b] & (np.sum(delta * delta, axis=2) >= 24**2)
        contrast = int(np.count_nonzero(edges))
        outer_border = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())
    return {'qualifies': fitted and occlusion['whole_region_clear'] and surface >= 16 and contrast >= 4
                and not outer_border and indices == list(TARGET_FACES),
            'in_frame': fitted and not outer_border, 'whole_geometry_clear': occlusion['whole_region_clear'],
            'surface_pixels': surface, 'contrasting_boundary_pixels': contrast, 'both_target_triangles': indices,
            'origin': frame['origin'], 'view': frame['view'], 'scope': frame['scope_id'],
            'frame_identity': frame['frame_identity'], 'ref': frame['ref'], 'PNG_sha256': frame['PNG_sha256'],
            'image_bytes': len(png), 'carried_objects': len(names), 'full_geometry_verified': True,
            'missing_positive_area_blockers': [item for item in occlusion['positive_area_occluders']
                if item['object_name'] not in names], 'exact_visibility': occlusion}


def verify_pair(packet, distance_m, direction, points, repo=None, tolerance_m=0.00005, direction_degrees=.5):
    """Accept every exact-optimal point pair to tolerance, with actual named surface membership."""
    root = repo_path(repo)
    scene = verify_scene(packet, root)
    _, membership, _, _ = independent(str(root))
    points = [points[k] for k in ('a', 'b')] if isinstance(points, dict) else points
    pair = [membership['vector'](q) for q in points]
    require(len(pair) == 2, 'pair_requires_two_points')
    rows = scene['source_objects']
    proof = [membership['membership'](q, rows[name]['evaluated']['vertices_world_m'],
                                     rows[name]['evaluated']['triangles'])
             for q, name in zip(pair, (TARGET, REFERENCE), strict=True)]
    delta = [b-a for a, b in zip(*pair, strict=True)]
    length = math.sqrt(float(sum(x*x for x in delta)))
    d = [float(x) for x in membership['vector'](direction)]
    magnitude = math.hypot(*d)
    stated_angle = math.degrees(math.acos(max(-1., min(1., -d[0]/magnitude)))) if magnitude else None
    actual_angle = math.degrees(math.acos(max(-1., min(1., -float(delta[0])/length)))) if length else None
    measured = math.isfinite(float(distance_m)) and abs(float(distance_m)-1.) <= tolerance_m
    fixed_points = all(row['within_publication_tolerance_source_triangle_indices'] for row in proof)
    return {'distance_correct': measured, 'points_on_current_surfaces': fixed_points,
            'world_direction_correct': stated_angle is not None and stated_angle <= direction_degrees,
            'points_attain_whole_minimum': fixed_points and abs(length-1.) <= tolerance_m
                and actual_angle is not None and actual_angle <= direction_degrees,
            'closest_points_delta_m_exact': list(map(str, delta)), 'closest_points_distance_m': length,
            'reported_direction_angle_to_minus_x_deg': stated_angle, 'points_angle_to_minus_x_deg': actual_angle,
            'distance_tolerance_m': tolerance_m, 'direction_tolerance_deg': direction_degrees,
            'membership': proof}


class Adapter:
    def __init__(self, index):
        self.index = index

    def read(self, path, digest=None, within=None):
        path = Path(path).resolve(strict=True)
        require(within is None or path.is_relative_to(within.resolve()), 'native_packet_outside_original_slot')
        raw = self.index.member(path)
        require(digest is None or sha256(raw).hexdigest() == digest, 'cached_native_packet_digest_changed')
        return json.loads(raw)

    check = staticmethod(require)


def verify_originals(repo, binding=None):
    """Read the real old terminal, host decoded full capture and two proven original CLI packets."""
    root = repo_path(repo); v = root / 'verification'
    candidate = Path(binding) if binding is not None else v / CANDIDATE_INSTALL
    dependency = json.loads(candidate.read_bytes())['dependency_root']
    if dependency not in sys.path:
        sys.path.insert(0, dependency)
    archives = run_path(str(v / ORDINARY / 'harness/archives.py'))
    dec = run_path(str(v / DECODER))
    old_install = json.loads((v / OLD_INSTALL).read_bytes())
    old, frames = {}, {}
    with archives['Archive'](ARCHIVE_ROOT, v / ARCHIVE / 'RUNTIME_INDEX.json', ARCHIVE_SHA, 1287) as index:
        for label, (view, attempt, image_sha, surface, contrast) in EXPECTED_ARCHIVED_IMAGES.items():
            label_root = ARCHIVE_ROOT / 'slots' / label
            rel = 'slots/' + label
            terminal = index.json(label_root / 'TERMINAL_SOURCE.json')
            initial = index.json(label_root / 'initial_capture/TERMINAL_SOURCE.json')
            slot_result = index.json(label_root / 'SLOT_RESULT.json')
            publication = index.json(label_root / 'SLOT_PUBLICATION.json')
            require(terminal['objects'] == initial['objects']
                    and terminal['display_object_mask'] == initial['display_object_mask']
                    and slot_result['closure_verification']['passed'] and slot_result['independent_before_after']['passed']
                    and slot_result['status'] == publication['status'] == 'completed'
                    and pin(label_root / 'SLOT_RESULT.json')['sha256'] == publication['result_sha256'],
                    'historical_slot_file_or_current_terminal_closure_changed')
            require(digest(index.member(label_root / 'native/input.blend')) == ASSET_SHA,
                    'historical_native_slot_not_exact_asset')
            validated = verify_scene(terminal, root)
            rec = index.json(label_root / 'DEVICE_EVIDENCE.json')
            frame, = (row for row in rec['frames'] if row['view'] == view and row['PNG_sha256'] == image_sha)
            png, npz = (index.member(frame[key]) for key in ('PNG', 'NPZ'))
            proof = qualify_frame(frame, terminal, png, npz, root)
            require(proof['qualifies'] and (proof['surface_pixels'], proof['contrasting_boundary_pixels']) ==
                    (surface, contrast), 'actual_archived_view_lacks_complete_target_readability')
            contracts = index.json(label_root / 'consumer/BUSINESS_SOURCE_BINDING.json')['result_contracts']
            raw = archives['rows'](index.member(label_root / 'consumer/stdout.raw.bin'))
            request, response, evidence = archives['outer_packet'](index, rel, attempt, contracts, raw)
            content = archives['images'](response['result'])
            require(content.count(png) == 1 and not response['result']['isError'],
                    'verified_old_original_PNG_never_reached_CLI_tool_receipt')
            entry = {'proof': proof, 'routing': evidence, 'original_frame': frame,
                     'PNG': pin(frame['PNG']), 'NPZ': pin(frame['NPZ']), 'closed': True,
                     'source_geometry': pin(label_root / 'TERMINAL_SOURCE.json')}
            frames[label] = {'metadata': frame, 'png': png, 'npz': npz, 'entries': entry}
            old[label] = {'terminal': terminal, 'geometry': validated['source_objects'], 'request': request,
                          'reply': response['result']}
        require({name: row['evaluated'] for name, row in old['N2']['geometry'].items()}
                == {name: row['evaluated'] for name, row in old['P1']['geometry'].items()},
                'old_native_and_product_Evaluated_source_scope_diverged')
        p1 = ARCHIVE_ROOT / 'slots/P1'
        value = index.json(p1 / 'product_full/call_001/SERVICE_RESULT.json')
        known = Adapter(index)
        captures, commands = dec['decode_captures'](p1, old_install, known)
        capture = dec['current_capture'](captures, value['binding'], known)
        terminal = old['P1']['geometry']
        current = capture['meshes']
        require(capture.get('capture_scope', 'complete_scene_meshes') == capture['host_identity']['capture_scope']
                == 'complete_scene_meshes' and len(current) == 14
                and sum(len(row['faces']) for row in current) == 6148
                and all(mesh['object_id'] == terminal[mesh['name']]['object_id'] and
                    capture['host_identity']['object_instances'][mesh['object_id']] == terminal[mesh['name']]['instance_id']
                    and mesh['vertices'] == terminal[mesh['name']]['evaluated']['vertices_world_m']
                    and mesh['faces'] == terminal[mesh['name']]['evaluated']['triangles'] for mesh in current),
                'complete_archived_product_host_capture_differs_from_terminal_geometry')
        innermost = index.json(p1 / 'owner/tool_01/PRODUCT_RECEIPT.json')
        raw_reply = index.member(p1 / 'mcp' / f"rpc_{innermost['receipt']['index']:02d}" / 'RX.bin')
        require(json.loads(raw_reply)['result'] == old['P1']['reply']
                and digest(raw_reply) == innermost['receipt']['RX_sha256'], 'archived_product_inner_wire_changed')
        pins = list(index.pins.values())
    pins += [pin(path) for path in (Path(__file__), candidate, v / PLANE, v / ORIGIN, v / DECODER,
                                    v / OLD_INSTALL, v / ORDINARY / 'harness/archives.py')]
    return {'arm_originals': old, 'frames': frames, 'capture': capture, 'producer_result': value,
            'native_command_count': len(commands), 'pins': pins,
            'actual_product_inner_RX_sha256': digest(raw_reply)}


def main(repo, output):
    qualified = verify_originals(repo)
    _, _, _, facts = independent(str(repo_path(repo)))
    checks = [verify_pair(arm['terminal'], 1.0, [-1, 0, 0], facts['whole_witness_world_m'], repo)
              for arm in qualified['arm_originals'].values()]
    missed = verify_pair(qualified['arm_originals']['P1']['terminal'], facts['top_distance_m'],
                         [-1., 0., -1.], facts['top_witness_world_m'], repo)
    require(not missed['distance_correct'] and not missed['points_attain_whole_minimum']
            and missed['points_on_current_surfaces']
            and all(check['distance_correct'] and check['world_direction_correct'] and
                    check['points_attain_whole_minimum'] for check in checks), 'whole_vs_top_scope_counterexample_failed')
    pins = qualified['pins'] + [pin(ASSET, ASSET_SHA), pin(FROZEN_SOURCE, FROZEN_SOURCE_SHA)]
    with output.open('x', encoding='utf8', newline='\n') as sink:
        json.dump({'schema': 'perf050-dense-pair-transfer-independent-truth-v1', 'passed': True, 'source_counts': COUNTS,
                   'target_and_pair': facts, 'whole_current_checks': checks, 'incorrect_top_only_control': missed,
                   'prior_original_tool_images': {label: row['entries'] for label, row in qualified['frames'].items()},
                   'current_archived_full_host_geometry_matches_both_terminal_sources': True,
                   'actual_product_inner_RX_sha256': qualified['actual_product_inner_RX_sha256'],
                   'archived_native_commands': qualified['native_command_count'],
                   'source_pins': list({p['path']: p for p in pins}.values()),
                   'Blender_starts': 0, 'models': 0, 'new_rasters': 0}, sink,
                  ensure_ascii=False, allow_nan=False, indent=2)
        sink.write('\n')
    print(pin(output), flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'run_with_-I_-B')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--repo', type=Path, required=True)
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    main(args.repo, args.output)
