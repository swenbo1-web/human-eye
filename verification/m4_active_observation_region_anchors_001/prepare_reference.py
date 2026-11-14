"""Freeze independent world and saved-pixel location answers before execution.

Only stdlib, NumPy and PIL are used. No product module, discovery, renderer,
provider or subprocess is imported or called. Old records are copied through
their sealed archive mapping and retain their original bytes.
"""

from fractions import Fraction
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE.with_name('m4_active_observation_patch_ownership_001')
WORLD_FIELDS = ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def compact(value):
    return json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode('utf-8')


def save_bytes(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def save_json(path, value):
    save_bytes(path, (json.dumps(value, ensure_ascii=True, allow_nan=False,
                               sort_keys=True, indent=2) + '\n').encode('utf-8'))


def scalar(value):
    if value.denominator == 1:
        return value.numerator
    try:
        number = float(value)
    except OverflowError:
        return str(value)
    return number if math.isfinite(number) and number.as_integer_ratio() == (value.numerator, value.denominator) else str(value)


def world_reference(patch):
    quad = [tuple(Fraction(x) for x in point) for point in patch['quad']]
    center = tuple(sum(point[k] for point in quad) / 4 for k in range(3))
    u = tuple((quad[1][k] - quad[0][k]) / 2 for k in range(3))
    v = tuple((quad[3][k] - quad[0][k]) / 2 for k in range(3))
    normal = [Fraction(x) for x in patch['normal']]
    maximum = max(abs(x) for x in normal)
    direction = tuple(value / maximum for value in normal)
    result = {name: [scalar(value) for value in values]
              for name, values in zip(WORLD_FIELDS, (center, u, v, direction))}
    decoded = {name: [Fraction(value) for value in result[name]] for name in WORLD_FIELDS}
    reconstructed = [tuple(decoded[WORLD_FIELDS[0]][k] + a * decoded[WORLD_FIELDS[1]][k]
                           + b * decoded[WORLD_FIELDS[2]][k] for k in range(3))
                     for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    if reconstructed != quad:
        raise ValueError('independent_vectors_must_reconstruct_frozen_source_quad')
    return {'roi_id': patch['roi_id'], 'object_index': 0, 'source_object_name': patch['source_object_name'],
            'source_quad': patch['quad'], **result}


def boundary_reference(color, patch_owners):
    boundary = np.zeros(patch_owners.shape, dtype=bool)
    for axis in (0, 1):
        first = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        second = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        delta = color[first].astype(np.int32) - color[second].astype(np.int32)
        edge = (patch_owners[first] != patch_owners[second]) & (np.sum(delta * delta, axis=2) >= 576)
        boundary[first] |= edge
        boundary[second] |= edge
    return boundary


def pixel_reference(color, patch_owners, patches, pose):
    """One simple full target-mask scan per ROI, integer nearest owned pixel."""
    boundary = boundary_reference(color, patch_owners)
    rows = []
    for ordinal, patch in enumerate(patches):
        target = patch_owners == ordinal
        y, x = np.nonzero(target)
        surface = len(x)
        bounds = anchor = None
        if surface:
            xmin, xmax, ymin, ymax = int(x.min()), int(x.max()), int(y.min()), int(y.max())
            bounds = [xmin, ymin, xmax, ymax]
            distance = (2 * x.astype(np.int64) - xmin - xmax) ** 2 + (2 * y.astype(np.int64) - ymin - ymax) ** 2
            selected = int(np.argmin(distance))
            anchor = [int(x[selected]), int(y[selected])]
            if int(patch_owners[anchor[1], anchor[0]]) != ordinal:
                raise ValueError('reference_anchor_must_be_actual_owned_pixel')
        contrasting = int(np.count_nonzero(target & boundary))
        front = sum(Fraction(n) * Fraction(float(d)) for n, d in zip(patch['normal'], pose['target_to_eye_unit'])) > 0
        rows.append({'roi_id': patch['roi_id'], 'object_index': 0, 'view': pose['name'],
                     'front_facing': front, 'visible_surface_pixels': surface,
                     'contrasting_boundary_pixels': contrasting,
                     'readable': front and surface >= 16 and contrasting >= 4,
                     'visible_pixel_bounds': bounds, 'visible_pixel_anchor': anchor})
    return rows


def main():
    started = time.perf_counter_ns()
    archive_raw = (OLD / 'EXTERNAL_ARCHIVE.json').read_bytes()
    archive = json.loads(archive_raw)
    records = {row['original_relative_path']: row for row in archive['files']}
    by_original = {row['original_path'].replace('\\', '/').casefold(): row for row in archive['files']}
    copied = []

    def archived_copy(record, destination):
        raw = (ROOT / record['archive_path']).read_bytes()
        if digest(raw) != record['sha256'] or len(raw) != record['bytes']:
            raise ValueError('sealed_archive_bytes_changed')
        save_bytes(HERE / destination, raw)
        copied.append({'path': destination, 'bytes': len(raw), 'sha256': digest(raw),
                       'archive_path': record['archive_path'], 'original_path': record['original_path']})
        return raw

    source_inputs = {'EXTERNAL_ARCHIVE_sha256': digest(archive_raw)}
    for name in ('SPLIT.json', 'JOINED.json', 'EXPECTED_PATCHES.json', 'FIXTURE.json'):
        record = records['payload/inputs/' + name]
        raw = archived_copy(record, 'inputs/' + name)
        if raw != (OLD / 'inputs' / name).read_bytes():
            raise ValueError('original_input_and_archive_disagree')
        source_inputs[name[:-5] + '_sha256'] = digest(raw)
    expected = json.loads((HERE / 'inputs/EXPECTED_PATCHES.json').read_bytes())
    fixture = json.loads((HERE / 'inputs/FIXTURE.json').read_bytes())
    historical = {'capture_path': 'inputs/historical/JOINED_CAPTURE.json',
                  'index_path': 'inputs/historical/JOINED_INDEX.json',
                  'service_result_path': 'inputs/historical/JOINED_SERVICE_RESULT.json',
                  'brief_response_path': 'inputs/historical/JOINED_BRIEF_RESPONSE.json',
                  'full_response_path': 'inputs/historical/JOINED_FULL_RESPONSE.json',
                  'brief_path': 'inputs/historical/JOINED_BRIEF.txt',
                  'full_path': 'inputs/historical/JOINED_FULL.txt',
                  'manifest_path': 'inputs/historical/MANIFEST.json'}
    history_sources = [('server/CAPTURE_03.json', 'capture_path'), ('server/INDEX_02.json', 'index_path'),
                       ('server/RESULT_03.json', 'service_result_path'),
                       ('stdio/rpc_05/RESPONSE.json', 'brief_response_path'),
                       ('stdio/rpc_07/RESPONSE.json', 'full_response_path')]
    for suffix, name in history_sources:
        archived_copy(records['run/acceptance_01/' + suffix], historical[name])
    capture, index, result = [json.loads((HERE / historical[name]).read_bytes())
                              for name in ('capture_path', 'index_path', 'service_result_path')]
    capture_sha = digest((HERE / historical['capture_path']).read_bytes())
    if index['actual_capture_sha256'] != capture_sha or len(capture['meshes']) != 1:
        raise ValueError('joined_capture_index_source_binding')
    if [row['roi_id'] for row in index['regions']] != [row['roi_id'] for row in expected['regions']]:
        raise ValueError('historical_index_and_independent_ROIs')
    for description in ('brief', 'full'):
        response = json.loads((HERE / historical[description + '_response_path']).read_bytes())
        contents = response['result']['content']
        if response['result']['isError'] is not False or contents[0]['type'] != 'text':
            raise ValueError('historical_normal_text_response_required')
        text = contents[0]['text'].encode('utf-8')
        save_bytes(HERE / historical[description + '_path'], text)
        copied.append({'path': historical[description + '_path'], 'bytes': len(text), 'sha256': digest(text),
                       'derived_from_path': historical[description + '_response_path'],
                       'derivation': 'Exact first text content UTF-8 bytes, no JSON reformatting.'})
    brief_text = (HERE / historical['brief_path']).read_bytes()
    full_text = (HERE / historical['full_path']).read_bytes()
    if len(brief_text) != 24081:
        raise ValueError('historical_joined_brief_denominator_24081')
    missing_fields = WORLD_FIELDS + ('visible_pixel_bounds', 'visible_pixel_anchor')
    if any(('"' + name + '"').encode() in text for text in (brief_text, full_text) for name in missing_fields):
        raise ValueError('historical_missing_location_counterexample_changed')
    world_started = time.perf_counter_ns()
    worlds = [world_reference(patch) for patch in expected['regions']]
    world_closed = time.perf_counter_ns()
    roi_ids = [patch['roi_id'] for patch in expected['regions']]
    if len(worlds) != 138 or roi_ids != sorted(set(roi_ids)):
        raise ValueError('independent_world_denominator')
    mesh = capture['meshes'][0]
    vertices = [tuple(Fraction(value) for value in point) for point in mesh['vertices']]
    faces = mesh['faces']
    world_triangles = [[[str(value) for value in vertices[i]] for i in face] for face in faces]
    if digest(compact(world_triangles)) != expected['draw_order_world_triangles_sha256']:
        raise ValueError('actual_capture_matches_frozen_source_world_geometry')
    face_ids = np.full(len(faces), -1, dtype=np.int32)
    for ordinal, patch in enumerate(expected['regions']):
        for triangle_index in patch['joined_triangle_indices']:
            if face_ids[triangle_index] != -1:
                raise ValueError('independent_expected_face_mapping_overlap')
            face_ids[triangle_index] = ordinal
    if np.flatnonzero(face_ids < 0).tolist() != [expected['unsupported_joined_triangle_index']]:
        raise ValueError('frozen_nonrectangular_remainder')
    pixels_started = time.perf_counter_ns()
    frames = []
    for frame in result['frames']:
        view = frame['view_name']
        local = dict(frame)
        for field, extension in (('image_path', '.png'), ('arrays_path', '.npz')):
            path = 'inputs/historical/' + view + extension
            record = by_original[frame[field].replace('\\', '/').casefold()]
            archived_copy(record, path)
            local[field] = path
        png_raw, array_raw = ((HERE / local[field]).read_bytes() for field in ('image_path', 'arrays_path'))
        if digest(png_raw) != frame['image_sha256'] or digest(array_raw) != frame['arrays_sha256']:
            raise ValueError('historical_frame_descriptors')
        with np.load(BytesIO(array_raw), allow_pickle=False) as loaded:
            arrays = {name: loaded[name].copy() for name in loaded.files}
        if set(arrays) != set(frame['arrays']) or len(arrays) != 9:
            raise ValueError('historical_nine_array_keys')
        for name, array in arrays.items():
            meta = frame['arrays'][name]
            if (str(array.dtype) != meta['dtype'] or list(array.shape) != meta['shape']
                    or array.nbytes != meta['nbytes'] or digest(array.tobytes(order='C')) != meta['sha256']):
                raise ValueError('historical_raw_array_metadata_' + name)
        if (arrays['color'].dtype != np.uint8 or arrays['color'].shape != (512, 512, 3)
                or arrays['patch_owners'].dtype != np.int32 or arrays['patch_owners'].shape != (512, 512)):
            raise ValueError('historical_RGB_patch_owner_format')
        if arrays['patch_roi_ids'].tolist() != roi_ids or not np.array_equal(arrays['face_patch_ids'], face_ids):
            raise ValueError('independent_frozen_patch_mapping')
        with Image.open(BytesIO(png_raw)) as image:
            if image.mode != 'RGB' or image.size != (512, 512) or not np.array_equal(np.asarray(image), arrays['color']):
                raise ValueError('historical_PNG_equals_RGB')
        rows = pixel_reference(arrays['color'], arrays['patch_owners'], expected['regions'], frame['pose'])
        old_rows = next(row['pixel_rows'] for row in result['facts']['observations'] if row['view_name'] == view)
        if len(old_rows) != 138:
            raise ValueError('historical_feedback_denominator')
        by_roi = {row['roi_id']: row for row in old_rows}
        for row in rows:
            for name in ('object_index', 'view', 'front_facing', 'visible_surface_pixels', 'contrasting_boundary_pixels', 'readable'):
                if by_roi[row['roi_id']][name] != row[name]:
                    raise ValueError('independent_old_pixel_fact_' + name)
        frames.append({'view_name': view, 'arrays_path': local['arrays_path'], 'image_path': local['image_path'],
                       'arrays_sha256': frame['arrays_sha256'], 'image_sha256': frame['image_sha256'],
                       'frame': local, 'rows': rows})
    pixels_closed = time.perf_counter_ns()
    if [frame['view_name'] for frame in frames] != ['SCENE', 'BACK', 'LEFT'] or sum(len(f['rows']) for f in frames) != 414:
        raise ValueError('historical_three_views_and_414_rows')
    scene_rows = {row['roi_id']: row for row in frames[0]['rows']}
    world_by_id = {row['roi_id']: row for row in worlds}
    front_id = expected['checkpoints']['SCENE_visible_front']['roi_id']
    rear_id = expected['checkpoints']['SCENE_hidden_same_object_rear']['roi_id']
    bottom_id = expected['checkpoints']['all_six_back_facing']['roi_id']
    if (not scene_rows[front_id]['readable'] or scene_rows[front_id]['visible_surface_pixels'] <= 0
            or scene_rows[rear_id]['visible_surface_pixels'] != 0 or not scene_rows[rear_id]['front_facing']):
        raise ValueError('independent_SCENE_front_and_hidden_rear')
    if any(next(row for row in f['rows'] if row['roi_id'] == bottom_id)['front_facing'] for f in frames):
        raise ValueError('independent_back_face_direction')
    unsupported = fixture['added_once_before_candidate_execution']
    unsupported_center = [scalar(sum(Fraction(p[k]) for p in unsupported['vertices']) / 3) for k in range(3)]
    questions = {'schema': 'region-anchors-frozen-location-questions-v1',
                 'scope': 'Administrator/reference answers; never part of product scene or camera inputs.',
                 'reference_path': 'REFERENCE.json', 'questions': [
        {'id': 'world_front_to_actual_SCENE_pixel',
         'question': 'Locate the +Z face centered at the supplied world position and identify one actual owned pixel in SCENE. Report the bounds, anchor and readability.',
         'given': {'center_world_m': world_by_id[front_id]['center_world_m'], 'front_direction_world': [0, 0, 1], 'view': 'SCENE'},
         'expected': {'world': world_by_id[front_id], 'pixel': scene_rows[front_id]}},
        {'id': 'forward_hidden_rear_is_zero_pixel',
         'question': 'At the supplied world center, identify the +Z panel and determine whether SCENE gives it an owned pixel. Distinguish a forward-facing occluded face from a back face.',
         'given': {'center_world_m': world_by_id[rear_id]['center_world_m'], 'front_direction_world': [0, 0, 1], 'view': 'SCENE'},
         'expected': {'world': world_by_id[rear_id], 'pixel': scene_rows[rear_id], 'per_view_status': 'not_readable',
                      'geometric_occlusion_basis': expected['checkpoints']['SCENE_hidden_same_object_rear']}},
        {'id': 'back_face_unknown_with_no_anchor',
         'question': 'Identify the -Z face at the supplied center. Explain its front-facing and readability facts in the registered views and preserve its finite-pool unknown state.',
         'given': {'center_world_m': world_by_id[bottom_id]['center_world_m'], 'front_direction_world': [0, 0, -1]},
         'expected': {'world': world_by_id[bottom_id], 'pixels': [next(row for row in f['rows'] if row['roi_id'] == bottom_id) for f in frames],
                      'status': 'unknown', 'basis': expected['checkpoints']['all_six_back_facing']}},
        {'id': 'joined_nonrectangular_remainder_remains_unknown',
         'question': 'At the supplied triangle center, determine whether the joined object has a supported rectangular region. Preserve the unsupported remainder instead of assigning another face location.',
         'given': {'triangle_center_world_m': unsupported_center, 'triangle_vertices_world_m': unsupported['vertices']},
         'expected': {'object_index': 0, 'source_triangle_indices': [expected['unsupported_joined_triangle_index']],
                      'supported': False, 'status': 'unknown', 'scope': 'One nonrectangular triangular remainder, outside the rectangular patch domain.'}}]}
    manifest = {'schema': 'region-anchors-historical-input-manifest-v1', 'previous_archive_path': str((OLD / 'EXTERNAL_ARCHIVE.json').resolve()),
                'previous_archive_sha256': digest(archive_raw), 'files': copied}
    save_json(HERE / historical['manifest_path'], manifest)
    reference = {'schema': 'region-anchors-independent-reference-v1', 'reference_path_base': 'task_namespace',
                 'source_inputs': source_inputs, 'historical': historical, 'world_regions': worlds, 'pixel_frames': frames,
                 'old_counterexample': {'brief_UTF8_bytes': len(brief_text), 'full_UTF8_bytes': len(full_text),
                                        'all_location_fields_absent': True, 'new_default_joined_text_limit_bytes': 48162},
                 'source_binding': {'capture_sha256': capture_sha, 'index_sha256': digest((HERE / historical['index_path']).read_bytes()),
                                    'service_result_sha256': digest((HERE / historical['service_result_path']).read_bytes()),
                                    'world_triangle_sequence_sha256': expected['draw_order_world_triangles_sha256']},
                 'counts': {'world_regions': len(worlds), 'historical_frames': len(frames), 'pixel_rows': 414,
                            'nonempty_anchors': sum(row['visible_pixel_anchor'] is not None for f in frames for row in f['rows']),
                            'null_anchors': sum(row['visible_pixel_anchor'] is None for f in frames for row in f['rows'])},
                 'location_conventions': {'world_unit': 'm', 'front_direction': 'Parallel to the source normal, maximum absolute component one.',
                                          'pixel_origin': 'top_left', 'pixel_index_base': 0, 'pixel_axes': ['x', 'y'],
                                          'image_size_px': [512, 512], 'bounds': 'inclusive [xmin,ymin,xmax,ymax], containing actual owned pixels',
                                          'anchor': 'Owned pixel nearest bounds center by exact integer squared distance; equal distances use row-major order.'},
                 'timing': {'started_ns': started, 'world_started_ns': world_started, 'world_closed_ns': world_closed,
                            'world_reference_ns': world_closed - world_started, 'pixel_started_ns': pixels_started,
                            'pixel_closed_ns': pixels_closed, 'pixel_reference_and_archive_reads_ns': pixels_closed - pixels_started,
                            'closed_before_publication_ns': time.perf_counter_ns()},
                 'execution': {'python_executable': sys.executable, 'new_product_functions': 0, 'new_rasters': 0,
                               'new_Blender_processes': 0, 'new_models': 0,
                               'human_eye_modules_imported': [name for name in sys.modules if name.startswith('human_eye')]},
                 'reference_method': 'Frozen axis source quads reconstructed from exact vectors; independent full perROI masks, actual saved winners and integer nearest-point selection.'}
    if reference['execution']['human_eye_modules_imported']:
        raise ValueError('reference_must_not_import_product')
    save_json(HERE / 'QUESTIONS.json', questions)
    save_json(HERE / 'REFERENCE.json', reference)
    print(json.dumps({'world_regions': 138, 'pixel_rows': 414, 'old_brief_bytes': len(brief_text),
                      'historical_frames': 3, 'new_product_calls': 0, 'new_rasters': 0,
                      'REFERENCE_sha256': digest((HERE / 'REFERENCE.json').read_bytes()),
                      'QUESTIONS_sha256': digest((HERE / 'QUESTIONS.json').read_bytes())}))


if __name__ == '__main__':
    main()
