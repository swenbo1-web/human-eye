"""Recheck actual scene-image delivery against the frozen N15 surface."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import sys


NS = Path(__file__).resolve().parent
RUN = Path('D:/he_perf050_readonly_product_pilot_001')
INSTALL = NS.parent / 'm5_joint_brief_source_projection_001/install/PRODUCT_RUN_BINDING.json'


def read(path):
    return json.loads(path.read_bytes())


def inspect_frame(slot, frame, truth, delivery, oracle):
    import numpy as np
    from PIL import Image

    png, npz = (Path(frame[key]).resolve() for key in ('PNG', 'NPZ'))
    if not all(path.is_relative_to(slot.resolve()) for path in (png, npz)):
        raise ValueError('frame_references_a_different_slot')
    digests = [sha256(path.read_bytes()).hexdigest() for path in (png, npz)]
    if digests != [frame['PNG_sha256'], frame['NPZ_sha256']]:
        raise ValueError('original_PNG_or_NPZ_mismatch')
    view = frame['view_name']
    origin = frame['origin']
    name = truth['region']['object_name']
    out = {'ref': frame['ref'], 'view': view, 'origin': origin, 'scope_id': frame['scope_id'],
           'PNG_sha256': digests[0], 'NPZ_sha256': digests[1], 'native_PNG': str(png),
           'delivered_in_attempts': delivery.get(digests[0], [])}
    if name not in frame['object_names']:
        return {**out, 'qualifies': False, 'reason': 'target_not_in_frame_directory'}
    index = frame['object_names'].index(name)
    if frame['triangle_id_scope'] != 'zero-based-global-source-triangles-in-mesh-order':
        raise ValueError('frame_triangle_addressing_contract_changed')
    offsets = frame['source_face_offsets']
    with np.load(npz, allow_pickle=False) as data, Image.open(png) as image:
        rgb = data['color']
        if not np.array_equal(rgb, np.asarray(image.convert('RGB'))):
            raise ValueError('displayed_RGB_differs_from_raster_buffers')
        metric = oracle['pixels'](rgb, data['owners'], data['triangle_ids'] - offsets[index], index)
    directions = truth['visibility']
    direction = frame.get('direction_rational')
    established = [row for row in directions.values()
                   if direction is not None and np.linalg.norm(np.cross(direction, row['target_to_eye_direction'])) < 1e-12
                   and np.dot(direction, row['target_to_eye_direction']) > 0]
    clear = established[0]['clear'] if len(established) == 1 else None
    corners = np.c_[truth['region']['corners_world_m'], np.ones(4)]
    pose = frame['pose']
    clip = (np.asarray(pose['projection_matrix']) @ np.asarray(pose['view_matrix']) @ corners.T).T
    positive_w = bool(np.all(clip[:, 3] > 0))
    inside = positive_w and bool(np.all(np.abs(clip[:, :3]) <= clip[:, 3:4]))
    return {**out, **metric, 'direction_rational': direction, 'exact_clear_registered_direction': clear,
            'all_four_corners_inside_clip': inside,
            'qualifies': clear is True and inside and metric['surface_pixels'] >= 16 and
                         metric['contrasting_boundary_pixels'] >= 4}


def review(run, costs, output):
    binding = read(INSTALL)
    sys.path.insert(0, binding['dependency_root'])
    oracle = run_path(str(NS / 'truth/oracle.py'))
    truth = read(NS / 'truth/TRUTH.json')
    rows = []
    for arm in read(costs)['slots']:
        label = arm['label']
        slot = run / 'slots' / label
        evidence = slot / 'DEVICE_EVIDENCE.json'
        delivery = {}
        for attempt in arm.get('actual_requests', []):
            images = attempt['wire_content']['PNG']
            if images and attempt['CLI_binding'] == 'content_and_envelope_match' and attempt['CLI_delivered_images'] == len(images):
                for item in images:
                    delivery.setdefault(item['sha256'], []).append(attempt['attempt'])
        frames = read(evidence)['frames'] if evidence.is_file() else []
        inspected = []
        for frame in frames:
            try:
                inspected.append(inspect_frame(slot, frame, truth, delivery, oracle))
            except (KeyError, OSError, ValueError) as error:
                inspected.append({'ref': frame.get('ref'), 'view': frame.get('view'), 'qualifies': False, 'error': str(error)})
        rows.append({'label': label, 'frames': inspected})
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump({'costs_sha256': sha256(costs.read_bytes()).hexdigest(), 'slots': rows}, stream,
                  ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUN)
    parser.add_argument('--costs', type=Path, default=NS / 'consumer/COSTS.json')
    parser.add_argument('--output', type=Path, default=NS / 'IMAGE_REVIEW.json')
    args = parser.parse_args()
    review(args.runtime, args.costs, args.output)
