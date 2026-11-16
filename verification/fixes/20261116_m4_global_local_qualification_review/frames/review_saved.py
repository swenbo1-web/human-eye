"""Independent offline review of original public replies and saved image arrays.

The reviewer participated in fixture design. This program imports no product or
author checker and performs no live, Blender, renderer, or model operations.
"""

import ast
import base64
import copy
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, 'D:/he_anchor_001/venv/Lib/site-packages')
import numpy as np
from PIL import Image

AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_global_local_qualification_001')
RUNTIME = Path('D:/he_m4_global_local_001/sessions')
OUTPUT = Path(__file__).resolve().parent
SOURCE = '7d2d4352f462c64a46e6fccf447c6f030c08b96e95517a3b2b6776ed50b69a6a'
PINS = {}
CHECKS = []


def load(path):
    path = Path(path)
    content = path.read_bytes()
    PINS[str(path)] = hashlib.sha256(content).hexdigest()
    return json.loads(content)


def require(value, message):
    if not value:
        raise AssertionError(message)
    CHECKS.append(message)


def digest(value):
    content = json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()
    return hashlib.sha256(content).hexdigest()


def capture_from_original_wire(session, binding):
    resources = {}
    matches = []
    packets = []
    for folder in sorted((session / 'native/WIRE').glob('[0-9]*')):
        request = load(folder / 'REQUEST.bin')
        response = load(folder / 'RESPONSE.bin')
        code = request.get('params', {}).get('code', '')
        command = re.search(r'_request = _json.loads\((.+)\)\n', code)
        if command is None:
            continue
        command = json.loads(ast.literal_eval(command.group(1)))
        markers = [line for line in response.get('result', {}).get('result', '').splitlines()
                   if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
        require(response.get('status') == 'success' and len(markers) == 1,
                f'{session.name} wire {folder.name} successful unique packet')
        packet = json.loads(markers[0].split(':', 1)[1])
        require(packet.get('error') is None, f'{session.name} wire no packet error')
        value = packet.get('result')
        if not isinstance(value, dict):
            continue
        for resource in value.get('resources', []):
            key = resource['id'], resource['revision']
            require(key not in resources or resources[key] == resource,
                    f'{session.name} immutable resource identity')
            resources[key] = resource
        capture = copy.deepcopy(value.get('capture', value))
        if not capture.get('meshes'):
            continue
        for mesh in capture['meshes']:
            reference = mesh.pop('_scene_resource', None)
            if reference:
                resource = resources[reference['id'], reference['revision']]
                matrix, scale = reference['matrix'], reference['scale']
                mesh['vertices'] = [[sum(matrix[axis][part] * point[part] for part in range(3))
                                     * scale + matrix[axis][3] * scale
                                     for axis in range(3)] for point in resource['vertices_local']]
                mesh['faces'] = resource['faces']
                mesh['edges'] = resource['edges']
        if (capture.get('revision') == binding['scene_revision']
                and capture.get('capture_scope', 'complete_scene_meshes') == binding['capture_scope']):
            matches.append(capture)
        packets.append(dict(sequence=folder.name, command=command))
    require(len(matches) == 1, f'{session.name} unique current capture in original native wire')
    return matches[0], packets


def boundary_mask(color, patches):
    result = np.zeros(patches.shape, dtype=bool)
    for axis in (0, 1):
        before = [slice(None), slice(None)]
        after = [slice(None), slice(None)]
        before[axis], after[axis] = slice(None, -1), slice(1, None)
        before, after = tuple(before), tuple(after)
        delta = color[before].astype(np.int32) - color[after].astype(np.int32)
        edge = (patches[before] != patches[after]) & ((delta * delta).sum(axis=2) >= 24 ** 2)
        result[before] |= edge
        result[after] |= edge
    return result


def ray_review(frame, meshes, arrays):
    """Evaluate existing pixel-centre world rays without constructing an image.

    The 1e-8 author band is reconstructed for attribution, while target evidence
    is also checked at 1e-12 barycentric and 1e-10 metre allowances.
    """
    pose = frame['pose']
    camera = np.asarray(pose['view_matrix'])
    inverse = np.linalg.inv(camera)
    projection = np.asarray(pose['projection_matrix'])
    rows, cols = np.indices((512, 512), dtype=float)
    x = (2 * (cols.ravel() + .5) / 511 - 1) / projection[0, 0]
    y = (1 - 2 * (rows.ravel() + .5) / 511) / projection[1, 1]
    in_frustum = ((np.abs(x * projection[0, 0]) <= 1)
                  & (np.abs(y * projection[1, 1]) <= 1))
    origin = inverse[:3, 3] + x[:, None] * inverse[:3, 0] + y[:, None] * inverse[:3, 1]
    direction = -inverse[:3, 2]
    actual_triangle = arrays['triangle_ids'].ravel()
    actual_object = arrays['owners'].ravel()
    actual_depth = arrays['depth'].ravel()
    actual_patch = arrays['patch_owners'].ravel()
    foreground = actual_object >= 0
    best = np.full(len(x), np.inf)
    best_object = np.full(len(x), -1)
    best_triangle = np.full(len(x), -1)
    author_ambiguous = np.zeros(len(x), dtype=bool)
    actual_min_weight = np.full(len(x), -np.inf)
    actual_depth_error = np.full(len(x), np.inf)
    actual_eligible = np.zeros(len(x), dtype=bool)
    index = 0
    for object_index, mesh in enumerate(meshes):
        vertices = np.asarray(mesh['vertices'], dtype=float)
        for face in mesh['faces']:
            a, b, c = vertices[face]
            first, second = b - a, c - a
            normal = np.cross(first, second)
            denominator = normal @ direction
            if denominator == 0:
                index += 1
                continue
            depth = ((a - origin) @ normal) / denominator
            delta = origin + depth[:, None] * direction - a
            gram = np.asarray([[first @ first, first @ second], [first @ second, second @ second]])
            uv = (np.linalg.inv(gram) @ np.stack((delta @ first, delta @ second))).T
            minimum = np.minimum(np.minimum(uv[:, 0], uv[:, 1]), 1 - uv[:, 0] - uv[:, 1])
            valid = in_frustum & (minimum >= -1e-8) & (depth >= pose['near']) & (depth <= pose['far'])
            author_ambiguous |= valid & (minimum <= 1e-8)
            finite = np.isfinite(best)
            near = np.zeros(len(x), dtype=bool)
            near[finite] = np.abs(depth[finite] - best[finite]) <= 1e-8
            author_ambiguous |= valid & near
            closer = valid & (depth < best)
            best[closer], best_object[closer], best_triangle[closer] = depth[closer], object_index, index
            claimed = actual_triangle == index
            actual_min_weight[claimed] = minimum[claimed]
            actual_depth_error[claimed] = np.abs(depth[claimed] - actual_depth[claimed])
            actual_eligible[claimed] = valid[claimed] & (actual_object[claimed] == object_index)
            index += 1
    require(np.array_equal(np.isfinite(best), foreground), f'{frame["view_name"]} all pixel foreground rays')
    require(bool(np.all(actual_eligible[foreground])), f'{frame["view_name"]} all claimed actual source memberships')
    max_depth_error = float(np.max(actual_depth_error[foreground])) if np.any(foreground) else 0
    max_nearer_error = float(np.max(np.abs(actual_depth[foreground] - best[foreground]))) if np.any(foreground) else 0
    require(max_depth_error <= 1e-10 and max_nearer_error <= 1e-10,
            f'{frame["view_name"]} all source depths and nearest depth within 1e-10m')
    certain = foreground & ~author_ambiguous
    require(np.array_equal(actual_object[certain], best_object[certain])
            and np.array_equal(actual_triangle[certain], best_triangle[certain]),
            f'{frame["view_name"]} unambiguous exact object and triangle')
    target_details = []
    for patch, roi in enumerate(arrays['patch_roi_ids'].tolist()):
        if roi not in TARGET_ROIS:
            continue
        mask = actual_patch == patch
        weight = actual_min_weight[mask]
        target_details.append(dict(roi_id=roi, pixels=int(mask.sum()),
            author_ambiguous_pixels=int(np.count_nonzero(mask & author_ambiguous)),
            boundary_pixels_outside_author_band=int(np.count_nonzero(mask & ~author_ambiguous
                & boundary_mask(arrays['color'], arrays['patch_owners']).ravel())),
            strict_membership_failures=int(np.count_nonzero(weight < -1e-12)),
            minimum_actual_triangle_weight=float(weight.min()) if len(weight) else None,
            maximum_actual_source_depth_error_m=float(actual_depth_error[mask].max()) if np.any(mask) else None,
            source_triangles=sorted(set(actual_triangle[mask].tolist())),
            object_indices=sorted(set(actual_object[mask].tolist()))))
        require(not len(weight) or np.all(weight >= -1e-12), f'{roi} strict actual target source membership')
    cross_object_ambiguity = foreground & author_ambiguous & (actual_object != best_object)
    cross_patch_ambiguity = foreground & author_ambiguous & (actual_patch != arrays['face_patch_ids'][best_triangle])
    return dict(foreground_pixels=int(foreground.sum()), author_ambiguity_pixels=int(author_ambiguous.sum()),
                ambiguous_actual_best_object_differences=int(cross_object_ambiguity.sum()),
                ambiguous_actual_best_patch_differences=int(cross_patch_ambiguity.sum()),
                maximum_depth_error_m=max_depth_error, maximum_nearest_depth_error_m=max_nearer_error,
                ambiguous_cross_patch_samples=[dict(x=int(pixel % 512), y=int(pixel // 512),
                    actual_object=int(actual_object[pixel]), actual_source_triangle=int(actual_triangle[pixel]),
                    ray_source_triangle=int(best_triangle[pixel]), actual_patch=int(actual_patch[pixel]),
                    ray_patch=int(arrays['face_patch_ids'][best_triangle[pixel]]))
                    for pixel in np.flatnonzero(cross_patch_ambiguity)[:10]],
                target_pixels=target_details)


def review_slot(label):
    session = RUNTIME / label
    full = load(session / 'product_full/call_001/SERVICE_RESULT.json')
    calls = [json.loads(line) for line in (session / 'PUBLIC_REQUESTS.jsonl').read_text().splitlines() if line]
    require(len(calls) == 1, f'{label} exactly one public call')
    call = calls[0]
    request = load(call['actual_TX_path'])
    response = load(call['actual_RX_path'])
    require(request == load(call['request_path']) == call['request'], f'{label} actual request bytes')
    require(response == load(call['response_path']) == call['response'], f'{label} actual response bytes')
    require(response['id'] == request['id'] and response['result']['isError'] is False, f'{label} successful reply id')
    arguments = request['params']['arguments']
    require(arguments['include_image'] is True and arguments['response_detail'] == 'full', f'{label} full native image entry')
    blocks = response['result']['content']
    public = [json.loads(block['text']) for block in blocks if block['type'] == 'text']
    require(len(public) == 1, f'{label} one public JSON block')
    public = public[0]
    require(public['facts'] == full['facts'], f'{label} same producer full facts transparently delivered')
    require(public['binding'] == {key: value for key, value in full['binding'].items() if key != 'camera_specification'},
            f'{label} full public binding projection')
    binding = full['binding']
    core = {key: value for key, value in binding.items() if key not in
            ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope')}
    require(binding['runtime_source_sha256'] == SOURCE
            and binding['source_status'] == 'loaded_generation' and binding['disk_status'] == 'disk_not_checked'
            and binding['source_check_scope'] == 'bound_generation_identity', f'{label} runtime source metadata attestation')
    require(digest({key: value for key, value in core.items() if key != 'binding_sha256'}) == core['binding_sha256'],
            f'{label} original core full binding hash preimage')
    excluded = ('source_binding_sha256', 'binding_sha256', 'geometry_identity', 'camera_identity', 'camera_specification')
    require(digest({key: value for key, value in core.items() if key not in excluded}) == core['source_binding_sha256'],
            f'{label} original core source binding hash preimage')
    capture, wire_packets = capture_from_original_wire(session, binding)
    source = load(session / 'raw_sources/live-source-001.json')
    raw_objects = {row['object_id']: row for row in source['objects']}
    require(binding['document_epoch'] == capture['host_identity']['document_epoch']
            and binding['capture_state'] == capture['capture_state'], f'{label} current generation binding')
    for index, mesh in enumerate(capture['meshes']):
        original = raw_objects[mesh['object_id']]
        require(mesh['vertices'] == original['vertices'] and mesh['faces'] == original['triangles'],
                f'{label} captured source original geometry {mesh["name"]}')
        require(binding['objects'][index] == dict(object_index=index, host_id=mesh['object_id'],
                instance_id=original['instance_id'], object_name=mesh['name']), f'{label} current ordered host mapping {index}')
    frames = full['frames']
    images = [block for block in blocks if block['type'] == 'image']
    require(len(frames) == len(images) == len(public['frames']) == (6 if label == 'global' else 1),
            f'{label} actual frame and public image denominator')
    regions = full['facts']['scope']['patch_support']['regions']
    face_offsets = np.cumsum([0] + [len(mesh['faces']) for mesh in capture['meshes']])
    expected_patch = np.full(face_offsets[-1], -1, dtype=np.int32)
    for patch, region in enumerate(regions):
        indices = face_offsets[region['object_index']] + np.asarray(region['triangle_indices'])
        require(np.all(expected_patch[indices] == -1), f'{label} source faces assigned once')
        expected_patch[indices] = patch
    result = []
    for number, frame in enumerate(frames):
        require(all(frame[key] == value for key, value in public['frames'][number].items()), f'{label} public frame metadata exact')
        png = Path(frame['image_path']).read_bytes()
        npz = Path(frame['arrays_path']).read_bytes()
        PINS[frame['image_path']] = hashlib.sha256(png).hexdigest()
        PINS[frame['arrays_path']] = hashlib.sha256(npz).hexdigest()
        require(hashlib.sha256(png).hexdigest() == frame['image_sha256']
                and hashlib.sha256(npz).hexdigest() == frame['arrays_sha256'], f'{label} current frame file hashes')
        require(base64.b64decode(images[number]['data'], validate=True) == png, f'{label} actual native PNG delivery')
        with np.load(BytesIO(npz), allow_pickle=False) as saved:
            arrays = {key: saved[key] for key in saved.files}
        require(np.array_equal(np.asarray(Image.open(BytesIO(png))), arrays['color']), f'{label} PNG equals actual RGB')
        require(np.array_equal(arrays['face_patch_offsets'], face_offsets)
                and np.array_equal(arrays['face_patch_ids'], expected_patch)
                and arrays['patch_roi_ids'].tolist() == [row['roi_id'] for row in regions], f'{label} source to patch index mapping')
        ordered_geometry = [(tuple(tuple(Fraction(value) for value in point) for point in mesh['vertices']),
                            tuple(tuple(face) for face in mesh['faces'])) for mesh in capture['meshes']]
        local_patch_rows = [expected_patch[face_offsets[index]:face_offsets[index + 1]].tolist()
                            for index in range(len(capture['meshes']))]
        mapping = digest(dict(version='active-patch-owner-v1', roi_ids=tuple(row['roi_id'] for row in regions),
                              ordered_geometry=ordered_geometry, face_patch_ids=local_patch_rows))
        owner_mapping = digest(('active-dual-owner-v1',
                'zero-based-global-source-triangles-in-mesh-order', mapping, face_offsets.tolist()))
        require(arrays['patch_mapping_identity'].item() == frame['patch_mapping_identity'] == mapping
                and arrays['owner_mapping_identity'].item() == frame['owner_mapping_identity'] == owner_mapping,
                f'{label} original geometry patch and owner hash preimages')
        image_identity = digest(((frame['scene_identity'], frame['candidate_identity']),
            frame['owner_schema'], owner_mapping, frame['view_name'], number + 1, frame['image_sha256']))
        require(frame['frame_identity'] == image_identity, f'{label} current frame identity preimage')
        reference = digest((binding['binding_sha256'], frame['view_name'], frame['image_sha256'], mapping,
                            frame['owner_schema'], owner_mapping, image_identity))
        require(frame['image_ref'] == 'active-host-image:' + reference, f'{label} current host image reference preimage')
        for key, metadata in frame['arrays'].items():
            value = arrays[key]
            require(metadata == dict(dtype=str(value.dtype), shape=list(value.shape), nbytes=value.nbytes,
                    sha256=hashlib.sha256(value.tobytes()).hexdigest()), f'{label} raw array metadata {key}')
        owners, triangles, patches = arrays['owners'], arrays['triangle_ids'], arrays['patch_owners']
        foreground = owners >= 0
        require(np.array_equal(triangles >= 0, foreground)
                and np.all(triangles[foreground] >= face_offsets[owners[foreground]])
                and np.all(triangles[foreground] < face_offsets[owners[foreground] + 1])
                and np.array_equal(patches[foreground], expected_patch[triangles[foreground]]), f'{label} all actual owner triangle patch indices')
        require(np.isposinf(arrays['depth'][~foreground]).all()
                and (arrays['color'][~foreground] == [18, 22, 30]).all(), f'{label} true background')
        require(frame['host_binding_sha256'] == binding['binding_sha256']
                and frame['source_revision'] == binding['scene_revision'], f'{label} frame current capture parent')
        pose = next(view for view in binding['camera_specification']['views'] if view['name'] == frame['view_name'])
        require(frame['pose'] == pose, f'{label} actual frame published camera')
        observation = full['facts']['observations'][number]
        require(observation['image_ref'] == frame['image_ref'] and observation['image_sha256'] == frame['image_sha256'],
                f'{label} actual observation current image reference')
        boundary = boundary_mask(arrays['color'], patches)
        pixel_rows = {row['roi_id']: row for row in observation['pixel_rows']}
        actual_counts = []
        for patch, region in enumerate(regions):
            mask = patches == patch
            surface, contrast = int(mask.sum()), int(np.count_nonzero(mask & boundary))
            row = pixel_rows[region['roi_id']]
            require(surface == row['visible_surface_pixels'] and contrast == row['contrasting_boundary_pixels'],
                    f'{label} pixel counts {region["roi_id"]}')
            require(row['readable'] == (row['front_facing'] and surface >= 16 and contrast >= 4),
                    f'{label} actual readability {region["roi_id"]}')
            if region['roi_id'] in TARGET_ROIS:
                actual_counts.append(dict(roi_id=region['roi_id'], object_index=region['object_index'],
                    surface=surface, boundary=contrast, readable=row['readable']))
        result.append(dict(view=frame['view_name'], target_counts=actual_counts,
                           ray_review=ray_review(frame, capture['meshes'], arrays),
                           PNG=str(frame['image_path']), NPZ=str(frame['arrays_path'])))
    return dict(label=label, capture=capture, public_regions=full['facts']['regions'], frames=result,
                wire_packets=wire_packets, source_scope=binding['capture_scope'], current_state_exists=(session/'product_state.json').exists())


TARGET_ROIS = set()
global_full = load(RUNTIME / 'global/product_full/call_001/SERVICE_RESULT.json')
for region in global_full['facts']['regions']:
    if region['object_name'] in ('Obj_02', 'Obj_06', 'Obj_09'):
        TARGET_ROIS.add(region['roi_id'])
results = [review_slot(slot) for slot in ('global', 'local_open', 'local_covered')]
global_rows = {row['object_name']: row for row in results[0]['public_regions'] if row['roi_id'] in TARGET_ROIS}
cross_scope = []
for slot in results[1:]:
    region = slot['public_regions'][0]
    original = global_rows[region['object_name']]
    source = {mesh['name']: mesh for mesh in slot['capture']['meshes']}[region['object_name']]
    cross_scope.append(dict(object_name=region['object_name'], global_object_index=original['object_index'],
        local_object_index=region['object_index'], global_roi=original['roi_id'], local_roi=region['roi_id'],
        global_instance=original['instance_id'], local_instance=region['instance_id'],
        source_triangle_rows=list(range(len(source['faces'])))))
    require(original['host_id'] == region['host_id'] and original['roi_id'] == region['roi_id'],
            f'{slot["label"]} stable host and region geometry across distinct sessions')
report = dict(passed=True, reviewer_association='Reviewer proposed this fixture and task; did not author qualification execution or its saved-frame checker.',
              new_live_operations=0, new_rasters=0, new_models=0,
              check_count=len(CHECKS), checks=CHECKS, sessions=results, cross_scope=cross_scope, input_pins=PINS)
with (OUTPUT/'RESULT_R2.json').open('x', encoding='utf-8') as output:
    json.dump(report, output, ensure_ascii=False, indent=2)
print(json.dumps(dict(passed=True, checks=len(CHECKS), output=str(OUTPUT/'RESULT_R2.json'))))
