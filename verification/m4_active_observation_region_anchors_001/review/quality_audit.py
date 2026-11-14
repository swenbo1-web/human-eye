"""Independent saved-artifact location audit. Imports no product or oracle code."""
import base64
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import traceback

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
NS = HERE.parent
RUN = Path('D:/he_anchor_001/run/acceptance_01')
WORLD = ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m', 'front_direction_world')
PIXEL = ('front_facing', 'visible_surface_pixels', 'contrasting_boundary_pixels', 'readable',
         'visible_pixel_bounds', 'visible_pixel_anchor')
CHECKS = Counter()
INPUTS = {}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    path = Path(path)
    INPUTS[str(path.resolve())] = digest(path)
    return json.loads(path.read_bytes())


def check(value, label, group='quality'):
    CHECKS[group] += 1
    if not value:
        raise AssertionError(label)


def vec(value):
    return tuple(Fraction(x) for x in value)


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def rows(table):
    return [dict(zip(table['columns'], row)) for row in table['rows']]


def inside(point, quad):
    u, v = sub(quad[1], quad[0]), sub(quad[3], quad[0])
    offset = sub(point, quad[0])
    return (dot(offset, cross(u, v)) == 0 and 0 <= dot(offset, u) <= dot(u, u)
            and 0 <= dot(offset, v) <= dot(v, v))


def response(index):
    folder = RUN / 'stdio' / f'rpc_{index:02}'
    request = json.loads((folder / 'TX.bin').read_bytes())
    received = load(folder / 'RX.bin')
    check(received == load(folder / 'RESPONSE.json'), f'actual received response {index}', 'delivery')
    check(received['id'] == request['id'], f'RPC identity {index}', 'delivery')
    INPUTS[str((folder / 'TX.bin').resolve())] = digest(folder / 'TX.bin')
    return request, received['result']


def main():
    reference = load(NS / 'REFERENCE.json')
    expected = load(NS / 'inputs/EXPECTED_PATCHES.json')
    questions = load(NS / 'QUESTIONS.json')['questions']
    frozen = load(NS / 'FROZEN.json')
    accepted = load(RUN / 'RESULTS.json')
    captures = [load(RUN / 'server' / f'CAPTURE_{i:02}.json') for i in range(1, 4)]
    services = [load(RUN / 'server' / f'RESULT_{i:02}.json') for i in range(1, 4)]
    index_record = load(RUN / 'server/INDEX_01.json')
    check(accepted['passed'] and accepted['cleanup_errors'] == [], 'recorded original run completed', 'binding')
    check(len(frozen['runtime_manifest']) == 141, '141 frozen runtime sources', 'binding')
    for name in ('REFERENCE.json', 'QUESTIONS.json', 'inputs/EXPECTED_PATCHES.json', 'inputs/JOINED.json'):
        path = NS / name
        check(frozen['files_sha256'][str(path.resolve())] == digest(path), 'pre-execution input frozen ' + name, 'binding')
    check(accepted['reference_sha256'] == digest(NS / 'REFERENCE.json'), 'actual reference binding', 'binding')
    check(accepted['questions_sha256'] == digest(NS / 'QUESTIONS.json'), 'actual questions binding', 'binding')
    for capture in captures:
        check(capture['meshes'] == captures[0]['meshes'], 'three captures preserve complete geometry', 'binding')
    source = load(NS / 'inputs/JOINED.json')['objects'][0]
    mesh = captures[0]['meshes'][0]
    vertices = tuple(map(vec, mesh['vertices']))
    check(vertices == tuple(map(vec, source['vertices'])), 'actual world vertices equal frozen source', 'world')
    check(mesh['faces'] == source['triangles'], 'actual source face ordering preserved', 'world')
    check(len(mesh['faces']) == 3337, 'complete source contains 3337 faces', 'world')
    expected_by_id = {row['roi_id']: row for row in expected['regions']}
    check(len(expected_by_id) == 138, '138 independent source quads', 'world')
    world_rows = services[0]['facts']['regions']
    check(set(expected_by_id) == {row['roi_id'] for row in world_rows}, 'all world rows retained', 'world')
    mapping = {row['roi_id']: row['triangle_indices'] for row in
               services[0]['facts']['scope']['patch_support']['regions']}
    all_faces = set()
    for row in world_rows:
        identity = row['roi_id']
        quad = tuple(map(vec, expected_by_id[identity]['quad']))
        c, u, v, front = (vec(row[key]) for key in WORLD)
        reconstructed = tuple(tuple(c[k] + su * u[k] + sv * v[k] for k in range(3))
                              for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)))
        check(reconstructed == quad, identity + ' exact world reconstruction', 'world')
        normal = cross(sub(quad[1], quad[0]), sub(quad[3], quad[0]))
        check(front == tuple(x / max(map(abs, normal)) for x in normal), identity + ' oriented front', 'world')
        check(row['object_index'] == 0, identity + ' source object', 'world')
        check(mapping[identity] == expected_by_id[identity]['joined_triangle_indices'], identity + ' full source mapping', 'world')
        check(not all_faces.intersection(mapping[identity]), identity + ' disjoint source ownership', 'world')
        all_faces.update(mapping[identity])
        referenced = set()
        total_area_vector = [Fraction(0)] * 3
        for face_index in mapping[identity]:
            triangle = tuple(vertices[index] for index in mesh['faces'][face_index])
            referenced.update(triangle)
            check(all(inside(point, quad) for point in triangle), identity + ' actual source face in quad', 'world')
            area_vector = cross(sub(triangle[1], triangle[0]), sub(triangle[2], triangle[0]))
            check(dot(area_vector, normal) > 0, identity + ' actual face orientation', 'world')
            total_area_vector = [x + y for x, y in zip(total_area_vector, area_vector)]
        check(set(quad).issubset(referenced), identity + ' corners exist in captured faces', 'world')
        check(tuple(total_area_vector) == tuple(2 * x for x in normal), identity + ' exact area sum', 'world')
    check(set(range(3337)) - all_faces == {48}, 'only source face48 unsupported', 'world')

    all_responses = [response(index) for index in range(1, 6)]
    check([req['method'] for req, _ in all_responses] == ['initialize', 'tools/list', 'tools/call', 'tools/call', 'tools/call'],
          'five actual RPC methods', 'delivery')
    payloads = [result for _, result in all_responses[2:]]
    delivered = [json.loads(value['content'][0]['text']) for value in payloads]
    brief, hot, full = delivered
    text_bytes = [len(payload['content'][0]['text'].encode('utf8')) for payload in payloads]
    check(text_bytes[0] <= 48162 and text_bytes[1] <= 48162, 'actual received brief byte gate', 'delivery')
    check(brief['schema'] == hot['schema'] == 'active-observation-brief-v3', 'actual received v3 default/brief', 'delivery')
    check(full['facts'] == services[2]['facts'], 'actual full facts match service producer', 'delivery')
    for key in ('regions', 'pixels', 'images', 'coverage', 'location_conventions'):
        check(brief[key] == hot[key], 'cold and hot ' + key, 'delivery')
    actual_regions = rows(brief['regions'])
    region_ids = [row['roi_id'] for row in actual_regions]
    check(region_ids == [row['roi_id'] for row in world_rows], 'brief world ordering', 'delivery')
    for got, original in zip(actual_regions, world_rows):
        check(all(got[key] == original[key] for key in WORLD + ('roi_id', 'object_index', 'status', 'reason')),
              got['roi_id'] + ' actual received world semantics', 'delivery')
    conventions = brief['location_conventions']
    check(conventions == full['facts']['location_conventions'], 'brief/full shared convention', 'delivery')
    reference_conventions = reference['location_conventions']
    check(conventions['image_size_px'] == reference_conventions['image_size_px']
          and conventions['pixel_axis_order'] == reference_conventions['pixel_axes']
          and conventions['unit'] == reference_conventions['world_unit']
          and conventions['pixel_index_base'] == reference_conventions['pixel_index_base']
          and conventions['pixel_origin'] == reference_conventions['pixel_origin'].replace('_', '-'),
          'independent convention semantic correspondence', 'delivery')
    check(conventions['coordinate_frame'] == 'world'
          and conventions['corner_order'] == ['center-u-v', 'center+u-v', 'center+u+v', 'center-u+v']
          and conventions['front_direction_normalization'] == 'maximum absolute component is 1'
          and conventions['visible_pixel_bounds'] == 'inclusive bounds of actual ROI-owned pixels'
          and conventions['visible_pixel_anchor'] == 'ROI-owned pixel nearest bounds center; row-major ties',
          'declared geometric and pixel meanings', 'delivery')
    check(brief['location_conventions']['image_size_px'] == [512, 512], 'shared actual512 size', 'delivery')
    expected_binding = {k: v for k, v in full['binding'].items() if k not in ('schema', 'objects', 'camera_policy')}
    expected_binding['capture_state'] = {k: v for k, v in expected_binding['capture_state'].items() if k != 'selection_key'}
    check(brief['binding'] == expected_binding, 'source/context binding preserved', 'binding')
    check(brief['objects']['rows'] == [[o[k] for k in brief['objects']['columns']] for o in full['binding']['objects']],
          'actual object identity table', 'binding')
    check(brief['binding']['scene_revision'] == captures[0]['revision'], 'binding to actual capture', 'binding')
    check(index_record['actual_capture_sha256'] == digest(RUN / 'server/CAPTURE_01.json')
          and index_record['scene_identity'] == brief['binding']['geometry_identity']
          and index_record['candidate_identity'] == brief['binding']['camera_identity'], 'actual saved camera/index binding', 'binding')
    image_rows = rows(brief['images'])
    check([row['view_name'] for row in image_rows] == ['SCENE', 'BACK', 'LEFT'], 'three actual views', 'pixels')
    pixel_rows = rows(brief['pixels'])
    check(len(pixel_rows) == 414, '414 delivered pixel rows', 'pixels')
    original_by_view = {row['view_name']: row for row in services[0]['facts']['observations']}
    old_result = load(NS / reference['historical']['service_result_path'])
    old_regions = {row['roi_id']: row for row in old_result['facts']['regions']}
    old_pixels = {(obs['view_name'], row['roi_id']): row for obs in old_result['facts']['observations'] for row in obs['pixel_rows']}
    zero, nonempty = 0, 0
    for image_index, frame in enumerate(services[0]['frames']):
        view = frame['view_name']
        ref_frame = next(row for row in reference['pixel_frames'] if row['view_name'] == view)
        image_path, array_path = Path(frame['image_path']), Path(frame['arrays_path'])
        INPUTS[str(image_path)] = digest(image_path)
        INPUTS[str(array_path)] = digest(array_path)
        check(digest(image_path) == frame['image_sha256'] == ref_frame['image_sha256'], view + ' exact historical native PNG', 'pixels')
        check(image_path.read_bytes() == (NS / ref_frame['image_path']).read_bytes(), view + ' PNG byte equality', 'pixels')
        check(digest(array_path) == frame['arrays_sha256'] == ref_frame['arrays_sha256'], view + ' exact historical NPZ', 'pixels')
        check(array_path.read_bytes() == (NS / ref_frame['arrays_path']).read_bytes(), view + ' NPZ byte equality', 'pixels')
        with np.load(array_path, allow_pickle=False) as arrays:
            owners, color = arrays['patch_owners'], arrays['color']
            ids = arrays['patch_roi_ids'].tolist()
            check(ids == region_ids == frame['patch_roi_ids'], view + ' owner ID mapping', 'pixels')
            check(owners.shape == (512, 512) and owners.dtype == np.int32, view + ' saved actual owner shape', 'pixels')
            with Image.open(image_path) as image:
                check(image.mode == 'RGB' and image.size == (512, 512), view + ' actual native image dimensions', 'pixels')
                check(np.array_equal(np.asarray(image), color), view + ' actual PNG pixels bind array', 'pixels')
            for payload in payloads:
                block = payload['content'][image_index + 1]
                check(block['type'] == 'image' and base64.b64decode(block['data'], validate=True) == image_path.read_bytes(),
                      view + ' received native image block', 'delivery')
            for region_index, identity in enumerate(ids):
                actual = next(row for row in pixel_rows if row['image_index'] == image_index and row['region_index'] == region_index)
                producer = original_by_view[view]['pixel_rows'][region_index]
                check(producer['roi_id'] == identity, view + identity + ' row order', 'pixels')
                ys, xs = np.nonzero(owners == region_index)
                points = list(zip(map(int, xs), map(int, ys)))
                check(actual['visible_surface_pixels'] == len(points), view + identity + ' actual count', 'pixels')
                if points:
                    nonempty += 1
                    bounds = [min(xs).item(), min(ys).item(), max(xs).item(), max(ys).item()]
                    anchor = min(points, key=lambda p: ((2*p[0]-bounds[0]-bounds[2])**2 + (2*p[1]-bounds[1]-bounds[3])**2, p[1], p[0]))
                    check(actual['visible_pixel_bounds'] == bounds, view + identity + ' actual bounds', 'pixels')
                    check(actual['visible_pixel_anchor'] == list(anchor), view + identity + ' nearest row-major actual anchor', 'pixels')
                    check(owners[anchor[1], anchor[0]] == region_index, view + identity + ' owner lookup', 'pixels')
                else:
                    zero += 1
                    check(actual['visible_pixel_bounds'] is None and actual['visible_pixel_anchor'] is None,
                          view + identity + ' zero pixels two nulls', 'pixels')
                boundary_count = 0
                for x, y in points:
                    for xx, yy in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                        if not (0 <= xx < 512 and 0 <= yy < 512) or owners[yy, xx] == region_index:
                            continue
                        if sum((int(color[y, x, k])-int(color[yy, xx, k]))**2 for k in range(3)) >= 576:
                            boundary_count += 1
                            break
                front = dot(vec(actual_regions[region_index]['front_direction_world']), vec(frame['pose']['direction_rational'])) > 0
                readable = front and len(points) >= 16 and boundary_count >= 4
                check(actual['front_facing'] == front, view + identity + ' actual facing', 'pixels')
                check(actual['contrasting_boundary_pixels'] == boundary_count, view + identity + ' independent RGB boundary', 'pixels')
                check(actual['readable'] == readable, view + identity + ' original readable gate', 'pixels')
                check(all(actual[key] == producer[key] for key in PIXEL), view + identity + ' producer to receiver', 'delivery')
                check(all(actual[key] == old_pixels[view, identity][key] for key in PIXEL[:4]), view + identity + ' old semantic retention', 'retention')
    check((zero, nonempty) == (253, 161), 'all zero/nonempty actual anchors', 'pixels')
    counts = Counter(row['status'] for row in actual_regions)
    check(counts == {'covered': 115, 'unknown': 23}, 'original covered and unknown totals', 'retention')
    for row in actual_regions:
        check((row['status'], row['reason']) == (old_regions[row['roi_id']]['status'], old_regions[row['roi_id']]['reason']),
              row['roi_id'] + ' original region status/reason', 'retention')
    support = brief['scope']['patch_support']
    unsupported = rows(support['unsupported_components'])
    check(len(unsupported) == 1 and unsupported[0]['status'] == 'unknown'
          and unsupported[0]['triangle_index_ranges'] == [[48, 48]], 'unsupported remainder48 retained', 'retention')

    answers = []
    for question in questions:
        given = question['given']
        if 'center_world_m' in given:
            located = [row for row in actual_regions if vec(row['center_world_m']) == vec(given['center_world_m'])
                       and vec(row['front_direction_world']) == vec(given['front_direction_world'])]
            check(len(located) == 1, question['id'] + ' unique numeric location', 'questions')
            row = located[0]
            check(row['roi_id'] == question['expected']['world']['roi_id'], question['id'] + ' reference face', 'questions')
            ri = region_ids.index(row['roi_id'])
            pixels = [pixel for pixel in pixel_rows if pixel['region_index'] == ri]
            if 'view' in given:
                image_index = next(i for i, image in enumerate(image_rows) if image['view_name'] == given['view'])
                pixel = next(p for p in pixels if p['image_index'] == image_index)
                check(all(pixel[key] == question['expected']['pixel'][key] for key in PIXEL), question['id'] + ' received location answer', 'questions')
                answers.append({'id': question['id'], 'roi_id': row['roi_id'], 'view': given['view'],
                                **{key: pixel[key] for key in PIXEL}})
            else:
                check(row['status'] == 'unknown' and all(not pixel['front_facing'] and not pixel['readable'] for pixel in pixels),
                      question['id'] + ' back-face unknown', 'questions')
                check(all(pixel['visible_pixel_anchor'] is None for pixel in pixels), question['id'] + ' absent anchors', 'questions')
                check(len(index_record['cameras']['views']) == 6 and all(
                    dot(vec(row['front_direction_world']), vec(camera['direction_rational'])) < 0
                    for camera in index_record['cameras']['views']), question['id'] + ' six registered backward directions', 'questions')
                answers.append({'id': question['id'], 'roi_id': row['roi_id'], 'status': row['status'], 'anchors': [p['visible_pixel_anchor'] for p in pixels]})
        else:
            triangle = tuple(vertices[index] for index in mesh['faces'][48])
            check(set(triangle) == set(map(vec, given['triangle_vertices_world_m'])), 'remainder actual source triangle', 'questions')
            center = tuple(sum(point[k] for point in triangle)/3 for k in range(3))
            check(center == vec(given['triangle_center_world_m']), 'remainder exact center', 'questions')
            check(not any(inside(center, tuple(map(vec, row['quad']))) for row in expected['regions']), 'remainder center is outside supported source quads', 'questions')
            answers.append({'id': question['id'], 'triangle_index': 48, 'status': unsupported[0]['status']})
    check(len(answers) == 4, 'four actual location questions', 'questions')
    front, rear, bottom = questions[0]['expected']['world'], questions[1]['expected']['world'], questions[2]['expected']['world']
    front_quad, rear_quad = tuple(map(vec, front['source_quad'])), tuple(map(vec, rear['source_quad']))
    bottom_z = vec(bottom['center_world_m'])[2]
    check(bottom_z > rear_quad[0][2], 'positive rear/occluder depth gap', 'questions')
    shift = (4*bottom_z/3, -4*bottom_z/3)
    check(all(min(p[k] for p in front_quad) < point[k]+shift[k] < max(p[k] for p in front_quad)
              for point in rear_quad for k in (0, 1)), 'all forward rear rays cross the occluder XY interior', 'questions')
    for index, service in enumerate(services):
        check(service['work']['capture_calls'] == 1, 'one source capture per request', 'work')
        check(service['work']['prepare_calls'] == (1 if index == 0 else 0), 'single cold prepare', 'work')
        check(service['work']['raster_attempts'] == (3 if index == 0 else 0), '3 cold and zero hot/full rasters', 'work')
    check(accepted['actual_protocol_requests'] == 5 and accepted['new_raster_attempts'] == 3
          and accepted['total_native_image_blocks'] == 9 and accepted['prior_charged_raster_attempts'] == 0,
          'actual 5 RPC 3 tools 9 blocks 3 raster record', 'work')
    unit = load(NS / 'units_01/UNIT_RESULT.json')
    modules = {row['module']: row for row in unit['selected_modules']}
    check(unit['passed'] and unit['failures'] == unit['errors'] == [], 'frozen recorded units passed', 'legacy_records')
    for module in ('verification.test_active_observation_brief', 'verification.test_active_observation_patch_delivery'):
        check(module in modules, 'recorded historical v1/v2 regression ' + module, 'legacy_records')
        check(digest(Path(modules[module]['source'])) == modules[module]['source_sha256'], 'historical regression source binding', 'legacy_records')
    return {'schema': 'region-anchors-independent-saved-quality-v1', 'passed': True,
            'checks': sum(CHECKS.values()), 'checks_by_group': dict(CHECKS),
            'world_regions': 138, 'pixel_rows': 414, 'zero_locations': zero, 'nonempty_owned_anchors': nonempty,
            'covered_regions': counts['covered'], 'unknown_regions': counts['unknown'], 'unsupported_triangle_indices': [48],
            'actual_location_answers': answers, 'native_image_blocks_checked': 9,
            'received_text_bytes': dict(zip(('cold_brief', 'hot_brief', 'cached_full'), text_bytes)),
            'new_product_calls': 0, 'new_Blender_runs': 0, 'new_rasters': 0, 'new_model_calls': 0,
            'input_sha256': INPUTS, 'script_sha256': digest(Path(__file__)),
            'limitations': ['Saved-artifact audit, with no new runtime or benchmark execution.',
                'Source quad and face correspondence uses the pre-frozen independent reference and current captured faces.',
                'Legacy v1/v2 coverage is taken from source-bound recorded unit outcomes and was not rerun.',
                'Model consumption improvement and complete-task benefit remain unmeasured.']}


if __name__ == '__main__':
    try:
        result = main()
    except BaseException as error:
        result = {'schema': 'region-anchors-independent-saved-quality-v1', 'passed': False,
                  'checks': sum(CHECKS.values()), 'checks_by_group': dict(CHECKS),
                  'error': repr(error), 'traceback': traceback.format_exc(), 'input_sha256': INPUTS,
                  'new_product_calls': 0, 'new_Blender_runs': 0, 'new_rasters': 0, 'new_model_calls': 0}
    output = HERE / 'QUALITY.json'
    if output.exists():
        previous = json.loads(output.read_bytes())
        result['attempt_history'] = previous.get('attempt_history', []) + [{k: v for k, v in previous.items() if k != 'attempt_history'}]
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf8', newline='\n')
    lines = ['# 独立保存原件质量审核', '',
             f"审核通过状态为 {result['passed']}，完成 {result['checks']} 项检查。", '']
    if result['passed']:
        lines += ['138 个世界描述与实际捕获面逐项对应，四角和方向由 Fraction 独立重建。', '',
                  '414 个像素行从实际保存的 owner 数组重算。161 个非空锚点属于对应 ROI，且符合整数距离最小和 row-major 同距规则。253 个零像素行保留两个 null。', '',
                  '实际收到的冷／热 brief-v3 与 full 保留世界位置、像素定位、115 covered／23 unknown、来源和图片关联。源三角形48继续标为 unknown。', '',
                  '三份新 PNG 和 NPZ 与冻结历史参考逐字节一致，9 个实际 MCP 图像块均指向相同原生 PNG。四个定位问题均由实际接收的数值表回答。', '',
                  '旧 v1/v2 依据已冻结单测记录核对。本审核使用保存原件，模型消费改善仍待后续实测。', '',
                  '审核脚本的三项初始记录格式假设已纠正，涉及 patch_support 键名、参考说明字段异名及空错误列表。历史保存在 QUALITY.json，实际产品原件保持原字节。']
    else:
        lines += [result['error'], '', '完整失败及原始输入绑定保存在 QUALITY.json。']
    (HERE / 'QUALITY.md').write_text('\n'.join(lines) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'passed': result['passed'], 'checks': result['checks']}))
