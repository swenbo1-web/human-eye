"""Admin-only exact geometry truth and current-session localization grading.

No product, renderer or model modules are imported. Preparation reads the
frozen source and historical buffers. Formal grading reads each slot's own
recorded artifacts and an answer normalization bound to its original bytes.
"""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
ANCHORS = ROOT / 'verification/m4_active_observation_region_anchors_001'
CAPTURE = Path('D:/he_anchor_001/run/acceptance_01/server/CAPTURE_01.json')
CAMERAS = Path('D:/he_anchor_001/run/acceptance_01/server/INDEX_01.json')
SLOTS = ('N1', 'P1', 'P2', 'N2', 'N3', 'P3')
INPUTS = {}
LEGACY_GRADER = ROOT/'verification/m4_active_coverage_consumption_001/admin/score_answers.py'
LEGACY_GRADER_SHA = '76f0157254f54425e9354f7dbf292f00e5bb719fecdbd2252eaa84608ee06a9e'
RESULT_CONTRACT = ROOT/'verification/m4_consumer_error_contract_001/result_contract.py'
RULES = {
    'schema': 'region-localization-frozen-scoring-v1',
    'administrator_only': True,
    'slots': list(SLOTS),
    'criteria': [
        'Exact supported target set with no omitted, extra or duplicate region.',
        'Every finite-pool-reachable region covered by actual current-slot complete front-facing readable frame evidence.',
        'All finite-pool-unreachable regions have accurate bounded reasons and the unsupported source remainder is retained.',
        'SCENE click identifies its actual surface center, front direction, extent and current image ref.',
        'Origin +Z face is correctly distinguished from a back face and its SCENE visibility and any actually observed readable witness are correct.',
        'Specified bottom -Z face remains unknown within the finite six-view pool, without an all-viewpoint impossibility claim.',
    ],
    'thresholds': {'surface_pixels': 16, 'boundary_pixels': 4, 'rgb_euclidean_contrast': 24},
    'region_identity': ['exact source triangle-index set', 'exact oriented world quad',
                        'uniquely identifying world center and front direction', 'P roi_id alias'],
    'native_identity': 'Source geometry and source faces qualify directly. ROI hash is optional.',
    'evidence': 'Original current-session tool result, or current-session generated machine-readable artifact explicitly cited by final answer.',
    'normalization': 'Claims require exact source excerpts and immutable raw answer or cited artifact hashes. Missing claims remain missing.',
    'completion': 'All six criteria and original lifecycle/result-binding contracts must pass. All-unknown or unfinished reachable scan cannot pass.',
    'views': 'Any correct registered view set and native algorithm is accepted. No optimal-view-count score.',
    'render_budget': 'At most six actual attempts per slot, including repeat and failed construction. Twelve actual tool attempts.',
    'pixel_truth': 'Recomputed from each formal slot own PNG, depth and triangle/patch owner evidence. Historical images cannot qualify a formal observation.',
    'error_contract': 'Reuse m4_consumer_error_contract_001/result_contract.py content+envelope binding and retain recoverable tool errors.',
    'quality_before_cost': True,
    'model_gain': 'All six slots enter results. Cost rankings remain hidden until quality is recorded.',
    'numeric_comparison': 'Exact finite rational values, allowing equivalent decimal or Fraction encodings and positive normal scaling.',
    'unsupported_remainder': 'Preserve one nonrectangular unsupported component. A precise source triangle claim must equal [48], but its exact ID need not be volunteered.',
    'answer_review': 'Administrator normalization quotes original final/tool/artifact text and is independently reviewed for entailment. The scorer verifies immutable binding and numeric facts, not natural-language entailment.',
}


def raw(path):
    path = Path(path).resolve()
    value = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(value).hexdigest()
    return value


def read(path):
    return json.loads(raw(path).decode('utf-8-sig'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                          encoding='utf8', newline='\n')


def vec(values):
    return tuple(Fraction(value) for value in values)


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def side(a, b, point):
    return (b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0])


def signed_area(polygon):
    return sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(polygon, polygon[1:]+polygon[:1]))/2


def intersection(subject, clip):
    result = list(subject)
    for a, b in zip(clip, clip[1:]+clip[:1]):
        source, result = result, []
        if not source:
            break
        for first, last in zip(source, source[1:]+source[:1]):
            d0, d1 = side(a, b, first), side(a, b, last)
            if d0 >= 0:
                result.append(first)
            if (d0 < 0) != (d1 < 0):
                ratio = d0/(d0-d1)
                result.append(tuple(x+ratio*(y-x) for x, y in zip(first, last)))
    return result


def projection(polygon, direction):
    kx, ky = direction[0]/direction[2], direction[1]/direction[2]
    points = [(x-kx*z, y-ky*z) for x, y, z in polygon]
    area = signed_area(points)
    return list(reversed(points)) if area < 0 else points


def depth_function(polygon, direction):
    normal = cross(sub(polygon[1], polygon[0]), sub(polygon[2], polygon[0]))
    kx, ky = direction[0]/direction[2], direction[1]/direction[2]
    denominator = normal[0]*kx+normal[1]*ky+normal[2]
    if denominator == 0:
        return None
    return (-normal[0]/denominator, -normal[1]/denominator,
            dot(normal, polygon[0])/denominator)


def bounding_box(polygon):
    return tuple((min(p[k] for p in polygon), max(p[k] for p in polygon)) for k in range(2))


def overlaps(a, b):
    return all(max(x[0], y[0]) < min(x[1], y[1]) for x, y in zip(a, b))


def inside_camera(quad, camera):
    view = tuple(map(vec, camera['view_matrix']))
    projection_matrix = tuple(map(vec, camera['projection_matrix']))
    for point in quad:
        p = point+(Fraction(1),)
        camera_point = tuple(dot(row, p) for row in view)
        ndc = tuple(dot(row, camera_point) for row in projection_matrix)
        if camera_point[2] >= 0 or any(not -1 <= value <= 1 for value in ndc[:3]):
            return False
    return True


def exact_visibility(targets, other_triangles, cameras):
    occluders = [(target['key'], target['quad']) for target in targets] + other_triangles
    for camera in cameras:
        name, direction = camera['name'], vec(camera['direction_rational'])
        if direction[2] <= 0:
            raise ValueError('frozen_positive_z_camera_pool_required')
        projected = []
        for identity, polygon in occluders:
            screen = projection(polygon, direction)
            depth = depth_function(polygon, direction)
            if signed_area(screen) and depth is not None:
                projected.append((identity, screen, bounding_box(screen), depth))
        for target in targets:
            front = dot(target['normal'], direction) > 0
            inside = inside_camera(target['quad'], camera)
            blockers = []
            if front and inside:
                screen = projection(target['quad'], direction)
                box = bounding_box(screen)
                own_depth = depth_function(target['quad'], direction)
                for identity, other, other_box, other_depth in projected:
                    if identity == target['key'] or not overlaps(box, other_box):
                        continue
                    clipped = intersection(screen, other)
                    if len(clipped) < 3 or signed_area(clipped) == 0:
                        continue
                    difference = tuple(a-b for a, b in zip(other_depth, own_depth))
                    if any(difference[0]*p[0]+difference[1]*p[1]+difference[2] > 0 for p in clipped):
                        blockers.append(identity)
            target['by_view'][name] = {'front_facing': front, 'inside_viewport': inside,
                'positive_area_blockers': blockers,
                'geometry_complete': bool(front and inside and not blockers)}


def boundaries(color, labels):
    boundary = np.zeros(labels.shape, dtype=bool)
    for first, last in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[:, :-1], np.s_[:, 1:])):
        difference = color[first].astype(np.int32)-color[last].astype(np.int32)
        changed = (labels[first] != labels[last]) & ((difference*difference).sum(axis=2) >= 576)
        boundary[first] |= changed
        boundary[last] |= changed
    return boundary


def prepare_truth():
    if (HERE/'TRUTH.json').exists():
        raise FileExistsError('truth_already_frozen')
    expected = read(ANCHORS/'inputs/EXPECTED_PATCHES.json')
    capture, index = read(CAPTURE), read(CAMERAS)
    source = capture['meshes'][0]
    vertices = tuple(map(vec, source['vertices']))
    faces = source['faces']
    if len(capture['meshes']) != 1 or len(vertices) != 1913 or len(faces) != 3337:
        raise ValueError('fixed_joined_source_shape')
    targets, claimed = [], set()
    for number, source_region in enumerate(expected['regions']):
        quad = tuple(map(vec, source_region['quad']))
        normal = cross(sub(quad[1], quad[0]), sub(quad[3], quad[0]))
        if dot(sub(quad[1], quad[0]), sub(quad[3], quad[0])) != 0 or normal == (0, 0, 0):
            raise ValueError('independent_source_rectangle')
        indices = source_region['joined_triangle_indices']
        if claimed.intersection(indices):
            raise ValueError('source_faces_overlap')
        claimed.update(indices)
        area_vector = [Fraction(0)]*3
        for face_index in indices:
            points = tuple(vertices[i] for i in faces[face_index])
            for point in points:
                offset = sub(point, quad[0])
                u, v = sub(quad[1], quad[0]), sub(quad[3], quad[0])
                if (dot(offset, normal) != 0 or not 0 <= dot(offset, u) <= dot(u, u)
                        or not 0 <= dot(offset, v) <= dot(v, v)):
                    raise ValueError('source_face_outside_exact_quad')
            triangle_normal = cross(sub(points[1], points[0]), sub(points[2], points[0]))
            if dot(triangle_normal, normal) <= 0:
                raise ValueError('source_face_orientation')
            area_vector = [a+b for a, b in zip(area_vector, triangle_normal)]
        if tuple(area_vector) != tuple(2*x for x in normal):
            raise ValueError('source_quad_exact_area')
        targets.append({'key': f'face_{number:03}', 'roi_alias': source_region['roi_id'],
            'quad': quad, 'normal': normal, 'source_triangle_indices': list(indices),
            'center': tuple((a+b)/2 for a, b in zip(quad[0], quad[2])), 'by_view': {}})
    remainder = sorted(set(range(len(faces)))-claimed)
    if remainder != [48]:
        raise ValueError('fixed_unsupported_remainder')
    other = [('unsupported_triangle_48', tuple(vertices[i] for i in faces[48]))]
    cameras = index['cameras']['views']
    exact_visibility(targets, other, cameras)
    geom_reachable = {t['key'] for t in targets if any(v['geometry_complete'] for v in t['by_view'].values())}
    historical_witnesses = set()
    for name in ('SCENE', 'BACK', 'LEFT'):
        path = ANCHORS/'inputs/historical'/f'{name}.npz'
        raw(path)
        with np.load(path, allow_pickle=False) as archive:
            labels, color = archive['patch_owners'], archive['color']
            aliases = archive['patch_roi_ids'].tolist()
            boundary = boundaries(color, labels)
            for target in targets:
                mask = labels == aliases.index(target['roi_alias'])
                if (target['by_view'][name]['geometry_complete'] and np.count_nonzero(mask) >= 16
                        and np.count_nonzero(mask & boundary) >= 4):
                    historical_witnesses.add(target['key'])
    if geom_reachable != historical_witnesses:
        raise ValueError('geometric_reachable_set_needs_pixel_reference_review')
    output_targets = []
    for target in targets:
        normal = target['normal']
        output_targets.append({**{k: target[k] for k in ('key', 'roi_alias', 'source_triangle_indices', 'by_view')},
            'quad_world_m': [[str(x) for x in p] for p in target['quad']],
            'center_world_m': [str(x) for x in target['center']],
            'front_direction_world': [str(x/max(map(abs, normal))) for x in normal],
            'reachable': target['key'] in geom_reachable,
            'valid_geometric_views': [name for name, v in target['by_view'].items() if v['geometry_complete']]})
    truth = {'schema': 'region-localization-admin-truth-v1', 'administrator_only': True,
        'source_capture_sha256': INPUTS[str(CAPTURE.resolve())],
        'scene_vertices_sha256': hashlib.sha256(json.dumps(source['vertices'], separators=(',', ':')).encode()).hexdigest(),
        'source_faces_sha256': hashlib.sha256(json.dumps(faces, separators=(',', ':')).encode()).hexdigest(),
        'cameras': cameras, 'targets': output_targets,
        'reachable_keys': sorted(geom_reachable), 'finite_pool_unknown_keys': sorted(set(t['key'] for t in targets)-geom_reachable),
        'unsupported_triangle_indices': remainder,
        'questions': location_truth(output_targets),
        'thresholds': RULES['thresholds'], 'inputs_sha256': dict(INPUTS),
        'method': 'Exact rational projected convex intersections and strict ahead-depth halfspaces, independent of product discovery/index answers.',
        'historical_pixel_use': 'Validate existence of readable witnesses for complete geometric target set. Formal evidence must use each slot own arrays.',
        'new_product_calls': 0, 'new_rasters': 0, 'new_model_calls': 0}
    save(HERE/'TRUTH.json', truth)
    save(HERE/'FROZEN_SCORING.json', RULES)
    prose = ['# 冻结评分规则', '', '评分先于速度与模型用量排名。六个正式槽全部进入分母。', '']
    prose += [f'{i}. {rule}' for i, rule in enumerate(RULES['criteria'], 1)]
    prose += ['', '原生身份可用源三角形集合、世界四角或唯一中心和朝向。机器可读集合由本次工具结果或最终答明确引用的本次文件承载。', '',
              '覆盖必须具有该槽实际完整几何、正向、至少16表面像素、4个RGB距离至少24的边界像素及当前图引用。任意正确视角组合均可。', '',
              '有限池未知与域外余量应保留。缺失、重复、多算或仍可补齐的未观察面都会影响完整巡检判定。三项定位分别核对图像像素归属、世界位置和有限相机池范围。', '',
              '原始答文、引用文件、工具请求与结果、当前帧及生命周期均核不可变字节。普通工具业务错误保留并允许原合同内恢复。', '',
              '旧图像只用于管理员真值准备。正式像素与图片归属读取各槽自己的新原件。图像实际交付与数组证据资格分别记录。']
    (HERE/'FROZEN_SCORING.md').write_text('\n'.join(prose)+'\n', encoding='utf8', newline='\n')
    print(json.dumps({'truth_ready': True, 'targets': len(targets), 'reachable': len(geom_reachable),
                      'unknown': len(targets)-len(geom_reachable), 'new_rasters': 0}))


def location_truth(targets):
    def find(center, direction):
        wanted = vec(center), vec(direction)
        found = [target for target in targets
                 if (vec(target['center_world_m']), vec(target['front_direction_world'])) == wanted]
        if len(found) != 1:
            raise ValueError('location_target_not_unique')
        return found[0]['key']
    return {
        'click': {'view': 'SCENE', 'pixel_xy': [109, 247],
                  'target': find(['5/32', '-5/32', '243/2048'], [0, 0, 1])},
        'origin': {'target': find([0, 0, 0], [0, 0, 1]), 'SCENE_visible_pixels': 0,
                   'SCENE_front_facing': True, 'SCENE_occluded': True},
        'bottom': {'target': find(['5/32', '-5/32', '237/2048'], [0, 0, -1]),
                   'finite_pool_no_front_readable': True, 'global_invisibility_claim_valid': False},
    }


def load_pure_module(name, path, expected=None):
    data = raw(path)
    if expected is not None and hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('inherited_contract_changed')
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def shader_rgb(triangle):
    light = np.array([.4, -.5, 1.], dtype=np.float64)
    light /= np.linalg.norm(light)
    first, second = triangle[1]-triangle[0], triangle[2]-triangle[0]
    scale = max(float(np.max(np.abs(first))), float(np.max(np.abs(second))))
    normal = np.cross(first/scale, second/scale) if scale else np.zeros(3)
    length = float(np.linalg.norm(normal))
    shade = .45+.55*abs(float(normal@light)/length) if length else .45
    return np.clip(np.array([180, 190, 205], dtype=np.float64)*shade, 0, 255).astype(np.uint8)


class Grader:
    def __init__(self, truth):
        self.truth = truth
        self.targets = {row['key']: row for row in truth['targets']}
        self.aliases = {row['roi_alias']: row['key'] for row in truth['targets']}
        self.face_sets = {tuple(sorted(row['source_triangle_indices'])): row['key'] for row in truth['targets']}
        capture_bytes = raw(CAPTURE)
        if hashlib.sha256(capture_bytes).hexdigest() != truth['source_capture_sha256']:
            raise ValueError('administrator_shader_source_capture_changed')
        mesh = json.loads(capture_bytes)['meshes'][0]
        vertices = np.asarray([[float(Fraction(value)) for value in point] for point in mesh['vertices']], dtype=np.float64)
        self.triangle_rgb = np.asarray([shader_rgb(vertices[face]) for face in mesh['faces']], dtype=np.uint8)
        self.region_rgb = np.asarray([self.triangle_rgb[target['source_triangle_indices'][0]]
                                      for target in truth['targets']], dtype=np.uint8)
        for number, target in enumerate(truth['targets']):
            if np.any(self.triangle_rgb[target['source_triangle_indices']] != self.region_rgb[number]):
                raise ValueError('source_patch_shader_not_constant')
        self.contract = load_pure_module('_localization_result_contract', RESULT_CONTRACT)
        # The inherited immutable-byte and per-owner confinement checks are reused.
        self.legacy = load_pure_module('_localization_inherited_grader', LEGACY_GRADER, LEGACY_GRADER_SHA).Grader({
            'targets': []})
        self.sources = {}

    def artifact(self, owner, value, digest):
        result = self.legacy.artifact(owner, value, digest)
        INPUTS.update(self.legacy.inputs)
        return result

    def identity(self, value):
        if type(value) is str:
            return self.aliases.get(value)
        if type(value) is not dict:
            return None
        matches = []
        if 'roi_id' in value:
            matches.append(self.aliases.get(value['roi_id']))
        if 'source_triangle_indices' in value:
            indices = value['source_triangle_indices']
            if (type(indices) is not list or any(type(x) is not int for x in indices)
                    or len(indices) != len(set(indices))):
                return None
            matches.append(self.face_sets.get(tuple(sorted(indices))))
        if 'quad_world_m' in value:
            quad = set(map(vec, value['quad_world_m']))
            found = [key for key, target in self.targets.items()
                     if quad == set(map(vec, target['quad_world_m']))]
            matches.append(found[0] if len(found) == 1 else None)
        if 'center_world_m' in value and 'front_direction_world' in value:
            center, normal = vec(value['center_world_m']), vec(value['front_direction_world'])
            found = [key for key, target in self.targets.items()
                     if center == vec(target['center_world_m'])
                     and cross(normal, vec(target['front_direction_world'])) == (0, 0, 0)
                     and dot(normal, vec(target['front_direction_world'])) > 0]
            matches.append(found[0] if len(found) == 1 else None)
        return matches[0] if matches and None not in matches and len(set(matches)) == 1 else None

    def bind_sources(self, row, owner, consumer, answer, tool_paths):
        sources = {'final': answer}
        source_ids = []
        for item in row.get('sources', []):
            source_ids.append(item['id'])
            kind = item['kind']
            path = Path(item['path']).resolve()
            data = raw(path)
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('normalized_source_SHA')
            if kind == 'tool_result':
                if str(path) not in tool_paths:
                    raise ValueError('source_not_matched_current_tool_result')
            elif kind == 'cited_artifact':
                if not path.is_relative_to(owner.resolve()):
                    raise ValueError('cited_artifact_outside_current_owner')
                citation = item.get('final_citation_excerpt', '')
                if not citation or citation not in answer or path.name not in citation:
                    raise ValueError('artifact_not_explicitly_cited_in_final')
            else:
                raise ValueError('normalized_source_kind')
            body = data.decode('utf-8-sig')
            if kind == 'tool_result':
                response = json.loads(body)
                body = '\n'.join(block['text'] for block in response['result']['content'] if block.get('type') == 'text')
            sources[item['id']] = body
        if len(source_ids) != len(set(source_ids)) or 'final' in source_ids:
            raise ValueError('duplicate_normalized_source_id')
        self.sources = sources
        excerpt = row.get('coverage_use_excerpt', '')
        if not excerpt or excerpt not in answer:
            raise ValueError('final_does_not_use_coverage_facts')

    def support(self, value):
        supports = value if type(value) is list else [value]
        return bool(supports) and all(type(item) is dict and type(item.get('excerpt')) is str
            and bool(item['excerpt']) and item.get('source_id') in self.sources
            and item['excerpt'] in self.sources[item['source_id']] for item in supports)

    def tool_binding(self, owner, consumer):
        record = read(consumer/'CONSUMER.json')
        tools = read(owner/'TOOLS.json')['tools']
        observed = record['tool_calls']
        if len(tools) != len(observed) or len(tools) > 12:
            raise ValueError('actual_tool_attempt_budget_or_receipt_count')
        if [item['attempt'] for item in tools] != list(range(1, len(tools)+1)):
            raise ValueError('actual_tool_attempt_sequence')
        paths, image_hashes = set(), set()
        for tool, public in zip(tools, observed):
            folder = owner/('tool_'+str(tool['attempt']).zfill(2))
            request = read(folder/'REQUEST.json')
            path = folder/'RESPONSE.json'
            if not path.exists():
                path = folder/'ERROR_RESPONSE.json'
            response = read(path)
            item = public['item']
            if request['params']['name'] != item['tool'] or request['params']['arguments'] != item['arguments']:
                raise ValueError('actual_tool_request_binding')
            if type(request.get('id')) is not type(response.get('id')) or request.get('id') != response.get('id'):
                raise ValueError('actual_tool_response_id')
            bound = self.contract.bind_tool_result(response, item)
            if not bound['matched']:
                raise ValueError('actual_tool_result_'+bound['reason'])
            paths.add(str(path.resolve()))
            for block in item['result']['content']:
                if block.get('type') == 'image':
                    import base64
                    image_hashes.add(hashlib.sha256(base64.b64decode(block['data'], validate=True)).hexdigest())
        return record, paths, image_hashes, len(tools)

    def frames(self, owner, outer, delivered):
        observations = read(owner/'OBSERVATIONS.json')
        if observations['schema'] != 'region-localization-observations-v1':
            raise ValueError('current_observation_schema')
        manifest_path = BATCH/'inputs/SOURCES.json'
        manifest = read(manifest_path)
        binding = observations['source_inputs']
        for name in ('scene', 'cameras', 'capture', 'product_binding'):
            if binding[name+'_sha256'] != manifest[name]['sha256']:
                raise ValueError('current_observation_source_'+name)
        if binding['capture_sha256'] != self.truth['source_capture_sha256']:
            raise ValueError('current_observation_capture')
        attempts = observations['render_attempts']
        if len(attempts) > 6:
            raise ValueError('six_actual_render_attempt_budget')
        attempt_map = {item['attempt_id']: item for item in attempts}
        if len(attempt_map) != len(attempts):
            raise ValueError('duplicate_render_attempt_identity')
        triangle_map = np.full(3337, -2, dtype=np.int32)
        for number, target in enumerate(self.truth['targets']):
            triangle_map[target['source_triangle_indices']] = number
        evidence = {}
        cameras = {camera['name']: camera for camera in self.truth['cameras']}
        for frame in observations['frames']:
            view, ref = frame['view_name'], frame['ref']
            attempt = attempt_map[frame['attempt_id']]
            if ref in evidence or view not in cameras or frame['status'] != 'completed':
                raise ValueError('current_frame_identity')
            if attempt['view_name'] != view or attempt['ref'] != ref:
                raise ValueError('current_frame_attempt_binding')
            times = [attempt.get('intent_ns', attempt.get('started_ns'))]+[
                attempt[key] for key in ('render_started_ns', 'render_closed_ns', 'completed_ns')]
            if any(type(value) is not int for value in times) or times != sorted(times):
                raise ValueError('current_frame_time_order')
            if not outer['started_ns'] <= times[0] <= times[-1] < outer['deadline_ns']:
                raise ValueError('current_frame_outside_original_deadline')
            png_path, png = self.artifact(owner, frame['PNG'], frame['PNG_sha256'])
            npz_path, _ = self.artifact(owner, frame['NPZ'], frame['NPZ_sha256'])
            if 'metadata_path' in frame:
                _, metadata_raw = self.artifact(owner, frame['metadata_path'], frame['metadata_sha256'])
                metadata = json.loads(metadata_raw)
            else:
                metadata = frame
            if metadata['ref'] != ref or metadata['view_name'] != view:
                raise ValueError('current_frame_metadata_identity')
            if frame.get('source_capture_sha256', metadata.get('source_capture_sha256')) != self.truth['source_capture_sha256']:
                raise ValueError('current_frame_capture_binding')
            if frame.get('pose') != cameras[view]:
                raise ValueError('current_frame_registered_camera_binding')
            with np.load(npz_path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files}
            for name, array in arrays.items():
                actual = {'dtype': str(array.dtype), 'shape': list(array.shape), 'nbytes': array.nbytes,
                          'sha256': hashlib.sha256(array.tobytes(order='C')).hexdigest()}
                if 'dtype_str' in frame['arrays'][name]:
                    actual['dtype_str'] = array.dtype.str
                if frame['arrays'][name] != actual:
                    raise ValueError('current_frame_array_binding_'+name)
            color, depth, owners = (arrays[name] for name in ('color', 'depth', 'owners'))
            if color.shape != (512, 512, 3) or color.dtype != np.uint8 or depth.shape != (512, 512) or owners.shape != (512, 512):
                raise ValueError('current_frame_array_shape')
            with Image.open(png_path) as image:
                if image.mode != 'RGB' or image.size != (512, 512) or image.tobytes() != color.tobytes(order='C'):
                    raise ValueError('current_PNG_RGB_binding')
            if 'triangle_ids' in arrays:
                triangles = arrays['triangle_ids']
                if triangles.dtype != np.int32 or triangles.shape != (512, 512) or np.any((triangles < -1)|(triangles >= 3337)):
                    raise ValueError('current_triangle_ID_buffer')
                labels = np.full((512, 512), -1, dtype=np.int32)
                occupied = triangles >= 0
                labels[occupied] = triangle_map[triangles[occupied]]
                expected_rgb = np.tile(np.array([18, 22, 30], dtype=np.uint8), (512, 512, 1))
                expected_rgb[occupied] = self.triangle_rgb[triangles[occupied]]
            else:
                patch = arrays['patch_owners']
                aliases = arrays['patch_roi_ids'].tolist()
                if patch.dtype != np.int32 or patch.shape != (512, 512) or len(aliases) != len(set(aliases)):
                    raise ValueError('current_patch_owner_buffer')
                if set(aliases) != set(self.aliases) or np.any((patch < -1)|(patch >= len(aliases))):
                    raise ValueError('current_patch_owner_identity')
                lookup = np.array([list(self.targets).index(self.aliases[alias]) for alias in aliases], dtype=np.int32)
                expected_face_patch = np.full(3337, -1, dtype=np.int32)
                for patch_id, alias in enumerate(aliases):
                    expected_face_patch[self.targets[self.aliases[alias]]['source_triangle_indices']] = patch_id
                if ('face_patch_ids' not in arrays or 'face_patch_offsets' not in arrays
                        or not np.array_equal(arrays['face_patch_ids'], expected_face_patch)
                        or not np.array_equal(arrays['face_patch_offsets'], [0, 3337])):
                    raise ValueError('current_patch_source_face_mapping')
                labels = np.full((512, 512), -1, dtype=np.int32)
                occupied = patch >= 0
                labels[occupied] = lookup[patch[occupied]]
                labels[(owners >= 0)&~occupied] = -2
                expected_rgb = np.tile(np.array([18, 22, 30], dtype=np.uint8), (512, 512, 1))
                expected_rgb[occupied] = self.region_rgb[labels[occupied]]
                expected_rgb[labels == -2] = self.triangle_rgb[48]
            occupied = owners >= 0
            if np.any(occupied & (owners != 0)) or np.any(occupied != np.isfinite(depth)):
                raise ValueError('current_depth_object_owner_binding')
            if np.any(color != expected_rgb):
                raise ValueError('common_source_geometry_shaded_RGB_changed')
            boundary = boundaries(color, labels)
            measured = {}
            for number, target in enumerate(self.truth['targets']):
                mask = labels == number
                count, edge = int(np.count_nonzero(mask)), int(np.count_nonzero(mask & boundary))
                expected = target['by_view'][view]
                measured[target['key']] = {'surface': count, 'boundary': edge,
                    'valid': bool(expected['geometry_complete'] and count >= 16 and edge >= 4)}
            evidence[ref] = {'view': view, 'targets': measured, 'labels': labels,
                             'image_delivered': frame['PNG_sha256'] in delivered,
                             'PNG_sha256': frame['PNG_sha256'], 'NPZ_sha256': frame['NPZ_sha256']}
        return evidence, len(attempts)

    def reason_valid(self, row, target):
        facts = list(target['by_view'].values())
        front_facts = [item for item in facts if item['front_facing']]
        code = row.get('reason_code')
        return (code == 'finite_pool_no_complete_readable_view'
                or code == 'back_facing_all_views' and all(not item['front_facing'] for item in facts)
                or code == 'outside_viewport_all_views' and all(not item['inside_viewport'] for item in facts)
                or code == 'positive_area_occlusion_all_front_views' and bool(front_facts) and all(
                    item['positive_area_blockers'] for item in front_facts))

    def panels(self, rows, evidence):
        names = [self.identity(row.get('identity')) for row in rows]
        counts = Counter(name for name in names if name is not None)
        result = {'missing': sorted(set(self.targets)-set(counts)),
                  'extra_rows': [number for number, name in enumerate(names) if name is None],
                  'duplicates': sorted(key for key, count in counts.items() if count > 1),
                  'valid_covered': [], 'invalid_covered': [], 'unfinished_reachable': [],
                  'invalid_unknown': [], 'unsupported_claims': []}
        for row, key in zip(rows, names):
            if key is None:
                continue
            target = self.targets[key]
            if not self.support(row.get('support')):
                result['unsupported_claims'].append(key)
            if row.get('status') == 'covered':
                refs = row.get('views', [])
                valid = bool(refs) and target['reachable']
                for claim in refs:
                    frame = evidence.get(claim.get('ref'))
                    valid = bool(valid and frame and claim.get('view', frame['view']) == frame['view']
                                 and frame['targets'][key]['valid'])
                result['valid_covered' if valid else 'invalid_covered'].append(key)
            elif target['reachable']:
                result['unfinished_reachable'].append(key)
            elif row.get('status') not in ('unknown', 'uncovered') or not self.reason_valid(row, target):
                result['invalid_unknown'].append(key)
        result['passed'] = not any(value for key, value in result.items() if key != 'valid_covered')
        return result

    def unsupported(self, rows):
        if len(rows) != 1:
            return False
        row = rows[0]
        return (row.get('status') in ('unknown', 'unsupported') and row.get('component_count', 1) == 1
                and row.get('shape') == 'nonrectangular' and row.get('domain') == 'outside_supported_rectangle_domain'
                and row.get('source_triangle_indices', [48]) == [48] and self.support(row.get('support')))

    def questions(self, rows, evidence):
        truth = self.truth['questions']
        output = {}
        for name in ('click', 'origin', 'bottom'):
            row = rows.get(name, {})
            output[name] = {'passed': False}
            if self.identity(row.get('identity')) != truth[name]['target'] or not self.support(row.get('support')):
                continue
            key = truth[name]['target']
            target = self.targets[key]
            if name == 'click':
                frame = evidence.get(row.get('ref'))
                point = truth[name]['pixel_xy']
                position = list(self.targets).index(key)
                correct = bool(frame and frame['view'] == 'SCENE' and frame['labels'][point[1], point[0]] == position
                    and vec(row.get('center_world_m', [])) == vec(target['center_world_m'])
                    and self.identity({'center_world_m': row.get('center_world_m', []),
                                       'front_direction_world': row.get('front_direction_world', [])}) == key)
                if 'quad_world_m' in row:
                    extent = set(map(vec, row['quad_world_m'])) == set(map(vec, target['quad_world_m']))
                elif 'bounds_world_m' in row:
                    quad = tuple(map(vec, target['quad_world_m']))
                    expected_bounds = (tuple(min(point[i] for point in quad) for i in range(3)),
                                       tuple(max(point[i] for point in quad) for i in range(3)))
                    extent = tuple(map(vec, row['bounds_world_m'])) == expected_bounds
                elif 'half_edge_u_world_m' in row and 'half_edge_v_world_m' in row:
                    center = vec(row['center_world_m'])
                    u, v = vec(row['half_edge_u_world_m']), vec(row['half_edge_v_world_m'])
                    corners = {tuple(center[i]+a*u[i]+b*v[i] for i in range(3))
                               for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))}
                    extent = corners == set(map(vec, target['quad_world_m']))
                else:
                    extent = False
                output[name] = {'passed': bool(correct and extent),
                                'image_delivered': bool(frame and frame['image_delivered'])}
            elif name == 'origin':
                scene = [frame for frame in evidence.values() if frame['view'] == 'SCENE']
                valid = bool(scene and all(frame['targets'][key]['surface'] == 0 for frame in scene)
                    and row.get('SCENE_visible_pixels') == 0 and row.get('SCENE_front_facing') is True
                    and row.get('SCENE_occluded') is True)
                witness = row.get('witness', {})
                frame = evidence.get(witness.get('ref'))
                point = witness.get('pixel_xy', [])
                pixel_ok = (type(point) is list and len(point) == 2 and all(type(x) is int and 0 <= x < 512 for x in point))
                if frame and pixel_ok:
                    valid = bool(valid and witness.get('view', frame['view']) == frame['view']
                        and frame['targets'][key]['valid']
                        and frame['labels'][point[1], point[0]] == list(self.targets).index(key))
                else:
                    actual_readable = any(frame['targets'][key]['valid'] for frame in evidence.values())
                    valid = bool(valid and not actual_readable and row.get('missing_readable_evidence') is True)
                output[name] = {'passed': valid}
            else:
                output[name] = {'passed': bool(row.get('finite_pool_no_front_readable') is True
                    and row.get('finite_pool_only') is True and row.get('global_invisibility_claim') is False
                    and all(not value['front_facing'] for value in target['by_view'].values()))}
        return output


def quality(args):
    truth = read(HERE/'TRUTH.json')
    rules = read(HERE/'FROZEN_SCORING.json')
    if rules['schema'] != RULES['schema']:
        raise ValueError('frozen_rule_schema')
    for path, wanted in rules['files_sha256'].items():
        if hashlib.sha256(raw(path)).hexdigest() != wanted:
            raise ValueError('frozen_scoring_dependency_changed:'+path)
    grader = Grader(truth)
    normalized = read(args.normalized)
    if normalized['schema'] != 'region-localization-normalized-v1':
        raise ValueError('normalized_schema')
    rows = normalized['slots']
    if len(rows) != 6 or {row['slot_id'] for row in rows} != set(SLOTS):
        raise ValueError('exact_six_unique_normalized_slots')
    runtime = read(args.runtime_root/'RUN_RESULT.json')
    records = runtime['records']
    if len(records) != 6 or {row['slot'] for row in records} != set(SLOTS):
        raise ValueError('exact_six_runtime_slots')
    by_slot = {row['slot_id']: row for row in rows}
    records = {row['slot']: row for row in records}
    scores = []
    for slot in SLOTS:
        outer, row = records[slot], by_slot[slot]
        score = {'slot_id': slot, 'execution_state': outer['execution_state'],
                 'fully_qualified': False, 'evidence_errors': []}
        if outer['execution_state'] == 'not_run':
            score['reason'] = 'not_run'
            scores.append(score)
            continue
        try:
            owner, consumer = args.runtime_root/slot/'o', args.runtime_root/slot/'c'
            answer = raw(consumer/'PUBLIC_FINAL.txt')
            if hashlib.sha256(answer).hexdigest() != row['raw_answer_sha256']:
                raise ValueError('normalized_final_SHA')
            if Path(row['raw_answer_path']).resolve() != (consumer/'PUBLIC_FINAL.txt').resolve():
                raise ValueError('normalized_final_original_path')
            text = answer.decode('utf8')
            record, tools, delivered, tool_count = grader.tool_binding(owner, consumer)
            grader.bind_sources(row, owner, consumer, text, tools)
            evidence, render_count = grader.frames(owner, outer, delivered)
            lifecycle = bool(outer['execution_state'] == 'completed' and outer['outer_valid_completion']
                and outer['consumer_safe_to_continue'] and not outer['common_image_faults']
                and outer['runtime_binding']['confirmed'] and outer['runtime_exit']['confirmed']
                and outer['owner_process_cleanup']['confirmed'] and outer['consumer_process_cleanup']['confirmed']
                and record['safe_to_continue'] and tool_count <= 12 and render_count <= 6)
            panels = grader.panels(row.get('panels', []), evidence)
            questions = grader.questions(row.get('questions', {}), evidence)
            remainder = grader.unsupported(row.get('unsupported', []))
            scope = row.get('finite_pool_scope_correct') is True and row.get('global_invisibility_overclaim') is False
            score.update(execution_evidence_valid=lifecycle, coverage=panels, questions=questions,
                         unsupported_remainder_passed=remainder,
                         finite_pool_scope_passed=scope,
                         raw_answer_sha256=row['raw_answer_sha256'],
                         frame_count=len(evidence), render_attempts=render_count, tool_attempts=tool_count,
                         image_refs_delivered=sum(frame['image_delivered'] for frame in evidence.values()))
            score['fully_qualified'] = bool(lifecycle and panels['passed'] and remainder and scope
                                            and all(value['passed'] for value in questions.values()))
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            score['evidence_errors'].append({'type': type(error).__name__, 'message': str(error)})
        scores.append(score)
    output = {'schema': 'region-localization-quality-v1', 'slots': scores,
        'all_six_quality_complete': all(row['fully_qualified'] for row in scores),
        'denominator': 6, 'cost_analysis_performed': False, 'minimum_view_count_graded': False,
        'normalization_entailment_review_required': True,
        'inputs_sha256': dict(sorted(INPUTS.items()))}
    save(args.output, output)
    print(json.dumps({'quality_file': str(args.output), 'qualified': sum(row['fully_qualified'] for row in scores),
                      'denominator': 6, 'cost_analysis_performed': False}))


def make_packets(args):
    if args.packet_dir.exists():
        raise FileExistsError('quality_packets_already_published')
    runtime = read(args.runtime_root/'RUN_RESULT.json')
    records = runtime['records']
    if len(records) != 6 or {row['slot'] for row in records} != set(SLOTS):
        raise ValueError('all_six_records_required_before_packets')
    args.packet_dir.mkdir(parents=True, exist_ok=False)
    key = []
    # This fixed non-route order avoids showing the paired route/order labels.
    for number, slot in enumerate(('N2', 'P3', 'N1', 'P2', 'P1', 'N3'), 1):
        consumer, owner = args.runtime_root/slot/'c', args.runtime_root/slot/'o'
        name = 'Q'+str(number).zfill(2)
        folder = args.packet_dir/name
        folder.mkdir()
        answer_path = consumer/'PUBLIC_FINAL.txt'
        answer_bytes = raw(answer_path) if answer_path.exists() else b''
        final = answer_bytes.decode('utf8')
        (folder/'FINAL.txt').write_text(quality_text(final, args.runtime_root), encoding='utf8', newline='\n')
        tools = read(owner/'TOOLS.json')['tools'] if (owner/'TOOLS.json').exists() else []
        texts = []
        for tool in tools:
            path = owner/('tool_'+str(tool['attempt']).zfill(2))/'RESPONSE.json'
            if not path.exists():
                path = path.with_name('ERROR_RESPONSE.json')
            response = read(path)
            for block in response.get('result', {}).get('content', []):
                if block.get('type') == 'text':
                    texts.append({'source_id': 'tool_'+str(tool['attempt']).zfill(2),
                                  'text': quality_text(block['text'], args.runtime_root),
                                  'original_sha256': INPUTS[str(path.resolve())]})
        save(folder/'TOOL_TEXT.json', {'schema': 'region-localization-anonymous-quality-text-v1',
            'packet': name, 'tool_text': texts,
            'limitations': 'Tool wording can disclose capability. Timing, usage and cost rankings are excluded. Full evidence is independently source-checked.'})
        observation_path = owner/'OBSERVATIONS.json'
        if observation_path.exists():
            observations = read(observation_path)
            images = []
            for index, frame in enumerate(observations['frames'], 1):
                png = raw(frame['PNG'])
                if hashlib.sha256(png).hexdigest() != frame['PNG_sha256']:
                    raise ValueError('packet_current_PNG_SHA')
                filename = str(index).zfill(2)+'_'+frame['view_name']+'.png'
                (folder/filename).write_bytes(png)
                images.append({'file': filename, 'view': frame['view_name'], 'ref': frame['ref'], 'sha256': frame['PNG_sha256']})
            save(folder/'IMAGES.json', {'current_images': images})
        key.append({'packet': name, 'slot_id': slot, 'raw_answer_path': str(answer_path),
                    'raw_answer_sha256': hashlib.sha256(answer_bytes).hexdigest()})
    save(HERE/'QUALITY_PACKET_KEY.json', {'administrator_only': True, 'packets': key})
    save(args.packet_dir/'MANIFEST.json', {'schema': 'region-localization-anonymous-quality-packets-v1',
        'packet_count': 6, 'cost_analysis_performed': False,
        'source_inputs_sha256': dict(sorted(INPUTS.items()))})
    print(json.dumps({'packets': 6, 'cost_analysis_performed': False}))


def quality_text(text, runtime_root):
    def strip(value):
        if type(value) is dict:
            return {key: strip(item) for key, item in value.items()
                    if not re.search(r'(^|_)(ns|ms|seconds|elapsed|duration|usage|tokens|cost|timing|metrics|stages|perf)(_|$)', key)}
        if type(value) is list:
            return [strip(item) for item in value]
        return value
    try:
        result = json.dumps(strip(json.loads(text)), ensure_ascii=False, allow_nan=False, indent=2)
    except (ValueError, TypeError):
        result = text
    for slot in SLOTS:
        result = result.replace(str(runtime_root/slot), '<current_session>')
        result = result.replace(str(runtime_root/slot).replace('\\', '/'), '<current_session>')
    return result


def freeze_scoring():
    truth_path = HERE/'TRUTH.json'
    truth = read(truth_path)
    truth['questions'] = location_truth(truth['targets'])
    save(truth_path, truth)
    raw(truth_path)
    schema = {
        'schema': 'region-localization-normalized-v1',
        'slots': [{'slot_id': '<one of N1 P1 P2 N2 N3 P3>',
            'raw_answer_path': '<absolute runtime/slot/c/PUBLIC_FINAL.txt>', 'raw_answer_sha256': '<sha256>',
            'coverage_use_excerpt': '<exact final text correctly using coverage facts>',
            'finite_pool_scope_correct': True, 'global_invisibility_overclaim': False,
            'sources': [{'id': '<unique>', 'kind': 'tool_result or cited_artifact', 'path': '<current original>',
                         'sha256': '<sha256>', 'final_citation_excerpt': '<required for cited_artifact>'}],
            'panels': [{'identity': {'source_triangle_indices': ['<all component integer face IDs>']},
                        'status': 'covered or unknown or uncovered',
                        'views': [{'view': '<registered>', 'ref': '<current>'}],
                        'reason_code': 'finite_pool_no_complete_readable_view or exact bounded reason',
                        'support': [{'source_id': 'final or source id', 'excerpt': '<exact source text>'}]}],
            'unsupported': [{'component_count': 1, 'status': 'unsupported or unknown',
                             'shape': 'nonrectangular', 'domain': 'outside_supported_rectangle_domain',
                             'support': {'source_id': '<id>', 'excerpt': '<exact>'}}],
            'questions': {'click': {'identity': '<same supported forms>', 'center_world_m': ['<exact>'],
                'front_direction_world': ['<exact>'], 'quad_world_m': ['<corners, or half-edge vectors, or bounds_world_m>'],
                'view': 'SCENE', 'ref': '<current>', 'support': '<source/excerpt>'},
                'origin': {'identity': '<same>', 'SCENE_visible_pixels': 0, 'SCENE_front_facing': True,
                    'SCENE_occluded': True, 'witness': {'view': '<actual readable>', 'ref': '<current>', 'pixel_xy': ['<int x>', '<int y>']},
                    'support': '<source/excerpt>'},
                'bottom': {'identity': '<same>', 'finite_pool_no_front_readable': True, 'finite_pool_only': True,
                    'global_invisibility_claim': False, 'support': '<source/excerpt>'}}}],
        'review_requirements': ['Exactly six distinct slots, including failures/not-run with missing claims.',
            'Administrator-only face keys are never accepted as a consumer invented identity.',
            'Normalize only facts actually entailed by quoted original text, including bounded scope and numeric claims.',
            'Equivalent native answers and algorithms qualify without ROI hashes or a fixed view count.',
            'Source tool facts need a final use excerpt. Scratch artifact facts need an explicit final citation.',
            'Tool errors remain errors and can recover under the original budget. No favorable resampling.'],
    }
    save(HERE/'NORMALIZATION_SCHEMA.json', schema)
    frozen = dict(RULES, files_sha256={
        str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (truth_path, Path(__file__), HERE/'NORMALIZATION_SCHEMA.json',
                     LEGACY_GRADER, RESULT_CONTRACT, BATCH/'inputs/SOURCES.json', BATCH/'inputs/PROMPT.txt')})
    save(HERE/'FROZEN_SCORING.json', frozen)
    prose_path = HERE/'FROZEN_SCORING.md'
    prose = prose_path.read_text(encoding='utf8').split('\n数值按有限有理数')[0]
    prose += '\n数值按有限有理数精确比较，支持等价十进制、分数及正比例法向。定位范围可用四角、中心与半边向量或世界边界。\n'
    prose += '\n归一化只摘录原始最终答、实际工具正文和明确引用的当前文件。程序验证字节绑定与几何像素事实，原文是否蕴含每项声明由独立审查核验。\n'
    prose += '\n质量包移除结构化时间、用量与成本字段。工具能力与答文可能透露路线，无法承诺完全内容盲法。六槽评分先封存，随后才解锁成本排名。\n'
    prose_path.write_text(prose, encoding='utf8', newline='\n')
    print(json.dumps({'scoring_frozen': True, 'script_sha256': frozen['files_sha256'][str(Path(__file__).resolve())],
                      'truth_sha256': frozen['files_sha256'][str(truth_path.resolve())]}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-truth', action='store_true')
    parser.add_argument('--make-packets', action='store_true')
    parser.add_argument('--freeze-scoring', action='store_true')
    parser.add_argument('--normalized', type=Path)
    parser.add_argument('--runtime-root', type=Path, default=Path('D:/he_loc_001/formal'))
    parser.add_argument('--packet-dir', type=Path, default=HERE/'quality_packets')
    parser.add_argument('--output', type=Path, default=HERE/'QUALITY.json')
    args = parser.parse_args()
    if args.prepare_truth:
        prepare_truth()
    elif args.freeze_scoring:
        freeze_scoring()
    elif args.make_packets:
        make_packets(args)
    elif args.normalized is not None:
        quality(args)
    else:
        parser.error('select truth preparation, packet preparation or normalized quality scoring')


if __name__ == '__main__':
    HERE.mkdir(parents=True, exist_ok=True)
    main()
