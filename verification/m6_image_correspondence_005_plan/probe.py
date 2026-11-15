"""One fixed image/current-mesh correspondence probe, followed by isolated scoring."""
import hashlib
import json
from pathlib import Path
import struct
import time
import zlib

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '_m6dg4/batch'
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe/verification/m6_degrid_004')


def read_png(path):
    raw = path.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    offset = 8
    blocks = []
    while offset < len(raw):
        size = struct.unpack('>I', raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        data = raw[offset + 8:offset + 8 + size]
        offset += size + 12
        if kind == b'IHDR':
            width, height, bits, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
        if kind == b'IDAT':
            blocks.append(data)
    assert bits == 8 and color in (2, 6) and compression == filtering == interlace == 0
    channels = 4 if color == 6 else 3
    stride = width * channels
    stream = zlib.decompress(b''.join(blocks))
    assert len(stream) == height * (stride + 1)
    image = np.zeros((height, stride), np.uint8)
    for row_index in range(height):
        start = row_index * (stride + 1)
        mode = stream[start]
        row = np.frombuffer(stream[start + 1:start + stride + 1], dtype=np.uint8).astype(np.int32)
        previous = image[row_index - 1].astype(np.int32) if row_index else np.zeros(stride, np.int32)
        if mode == 1:
            for channel in range(channels):
                row[channel::channels] = np.cumsum(row[channel::channels]) % 256
        elif mode == 2:
            row = (row + previous) % 256
        elif mode in (3, 4):
            for column in range(stride):
                left = int(row[column - channels]) if column >= channels else 0
                up = int(previous[column])
                upper_left = int(previous[column - channels]) if column >= channels else 0
                predictor = (left + up) // 2
                if mode == 4:
                    estimate = left + up - upper_left
                    distances = (abs(estimate - left), abs(estimate - up), abs(estimate - upper_left))
                    predictor = (left, up, upper_left)[int(np.argmin(distances))]
                row[column] = (int(row[column]) + predictor) % 256
        else:
            assert mode == 0
        image[row_index] = row
    return image.reshape(height, width, channels)[:, :, :3]


def raster(vertices, faces, camera, width, height):
    affine = np.asarray(camera['world_to_image_affine_2_by_3'])
    pixel_offset = np.asarray(camera['world_to_image_offset'])
    pixels = vertices @ affine.T + pixel_offset
    matrix = np.asarray(camera['camera_matrix_world'])
    triangles = pixels[faces]
    triangle_depths = (vertices @ matrix[:3, 2])[faces]
    depth = np.full((height, width), -np.inf)
    face_ids = np.full((height, width), -1, np.int32)
    lower = np.maximum(np.ceil(triangles.min(axis=1) - .5).astype(int), [0, 0])
    upper = np.minimum(np.floor(triangles.max(axis=1) - .5).astype(int), [width - 1, height - 1])
    eligible = np.flatnonzero(np.all(lower <= upper, axis=1))
    for face_id in eligible:
        first, second, third = triangles[face_id]
        denominator = ((second[1] - third[1]) * (first[0] - third[0])
                       + (third[0] - second[0]) * (first[1] - third[1]))
        if abs(denominator) < 1e-10:
            continue
        left, top = lower[face_id]
        right, bottom = upper[face_id]
        x = np.arange(left, right + 1)[None, :] + .5
        y = np.arange(top, bottom + 1)[:, None] + .5
        weight0 = ((second[1] - third[1]) * (x - third[0]) + (third[0] - second[0]) * (y - third[1])) / denominator
        weight1 = ((third[1] - first[1]) * (x - third[0]) + (first[0] - third[0]) * (y - third[1])) / denominator
        weight2 = 1 - weight0 - weight1
        candidate_depth = weight0 * triangle_depths[face_id, 0] + weight1 * triangle_depths[face_id, 1] + weight2 * triangle_depths[face_id, 2]
        target = depth[top:bottom + 1, left:right + 1]
        keep = ((weight0 >= -1e-9) & (weight1 >= -1e-9) & (weight2 >= -1e-9) & (candidate_depth > target))
        target[keep] = candidate_depth[keep]
        face_ids[top:bottom + 1, left:right + 1][keep] = face_id
    return face_ids


def attention_probe():
    entries = json.loads((BASE / 'IMAGE_BINDING.json').read_bytes())['images']
    by_role = {entry['role']: entry for entry in entries}
    with np.load(BASE / 'private/cases/repair/initial.npz') as packet:
        vertices, faces = packet['vertices_world'], packet['faces']
        region, editable = packet['F_source_ids'], packet['I_ids']
    scores, visible, details = [], [], []
    touches_region = np.isin(faces, region).any(axis=1)
    for view in ('forearm_front', 'forearm_side', 'forearm_45'):
        current, normal = by_role['current_' + view], by_role['normal_' + view]
        assert current['camera'] == normal['camera']
        images = []
        for entry in (current, normal):
            path = BASE / Path(entry['path']).relative_to(AUTHOR)
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
            images.append(read_png(path))
        difference = np.max(np.abs(images[0].astype(np.int16) - images[1].astype(np.int16)), axis=2)
        energy = np.maximum(difference.astype(float) - 2, 0)
        face_ids = raster(vertices, faces, current['camera'], images[0].shape[1], images[0].shape[0])
        mapped, changed = face_ids >= 0, energy > 0
        area = np.bincount(face_ids[mapped], minlength=len(faces))
        signal = np.bincount(face_ids[mapped], weights=energy[mapped], minlength=len(faces))
        vertex_area, vertex_signal = np.zeros(len(vertices)), np.zeros(len(vertices))
        for corner in range(3):
            np.add.at(vertex_area, faces[:, corner], area / 3)
            np.add.at(vertex_signal, faces[:, corner], signal / 3)
        scores.append(np.divide(vertex_signal, vertex_area, out=np.zeros(len(vertices)), where=vertex_area > 0))
        visible.append(vertex_area > 0)
        altered_faces = face_ids[changed & mapped]
        details.append(dict(view=view, changed_pixels=int(changed.sum()),
            changed_outside_region=int(np.sum(~touches_region[altered_faces])),
            changed_without_current_mesh=int(np.sum(changed & ~mapped))))
    attention = np.max(scores, axis=0)
    observed = np.any(visible, axis=0)
    ranked = editable[np.lexsort((editable, -attention[editable]))]
    return dict(vertices=vertices, faces=faces, editable=editable, attention=attention,
                visible=observed, ranked=ranked, details=details)


def main():
    started = time.perf_counter()
    result = attention_probe()
    derived_wall = time.perf_counter() - started
    output = HERE / 'private/attention.npz'
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, attention=result['attention'], visible=result['visible'], ranked=result['ranked'])
    output_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    # Hidden labels are loaded only after the image/current-mesh result is frozen.
    with np.load(BASE / 'private/scoring/target.npz') as target:
        support = target['support_ids']
    chosen = result['ranked'][:int(np.ceil(.25 * len(result['editable'])))]
    true_positive = np.intersect1d(chosen, support)
    triangles = result['vertices'][result['faces']]
    triangle_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1) / 2
    lumped_area = np.zeros(len(result['vertices']))
    for corner in range(3):
        np.add.at(lumped_area, result['faces'][:, corner], triangle_area / 3)
    summary = dict(
        rule='RGBmax difference minus2DN; current full-mesh pixel-center zbuffer; visible-area normalized source scores; max of three local views',
        source_commit='6ed6c88e2ae91d08cff1e80fed436d2e3572bf77', candidate_budget=len(chosen),
        TP=len(true_positive), FP=len(np.setdiff1d(chosen, support)), FN=len(np.setdiff1d(support, chosen)),
        precision=len(true_positive) / len(chosen), recall=len(true_positive) / len(support),
        area_recall=float(lumped_area[true_positive].sum() / lumped_area[support].sum()),
        visible_editable_points=int(result['visible'][result['editable']].sum()),
        visibility_definition='Incident source triangle has visible pixel area. Vertex-point visibility is not inferred.',
        positive_attention_points=int(np.count_nonzero(result['attention'][result['editable']] > 0)),
        positive_attention_points_full_mesh=int(np.count_nonzero(result['attention'] > 0)),
        native_misselected24272_score=float(result['attention'][24272]),
        score_peak_source_id=int(result['editable'][np.argmax(result['attention'][result['editable']])]),
        derived_result_SHA256=output_hash, details=result['details'], input_to_attention='current geometry, six matched PNGs and camera metadata only',
        fitting_support_exclusion_and_amplitude='not_run', independent_raster_vs_renderer_validation='not_run',
        wall_s_before_hidden_scoring=derived_wall, new_Pro=0, new_Blender=0, new_training=0,
    )
    (HERE / 'PREFLIGHT.json').write_bytes((json.dumps(summary, indent=2) + '\n').encode())
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
