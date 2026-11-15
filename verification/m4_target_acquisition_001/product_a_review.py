"""Review the closed A qualification from saved bytes without product imports."""

import base64
import hashlib
import io
import json
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = Path('D:/he_m4_target_001/qualification/A_peripheral_02')
PINS = {}
CHECKS = []


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    PINS[str(path)] = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return raw


def load(path):
    return json.loads(read(path))


def check(name, condition):
    CHECKS.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


def table(value):
    return [dict(zip(value['columns'], row)) for row in value['rows']]


def main():
    error = None
    summary = {}
    try:
        capture = load(RUN / 'CAPTURE_01.json')
        public = load(RUN / 'PUBLIC_01.json')
        request = load(RUN / 'REQUEST_01.json')
        response = load(RUN / 'RESPONSE_01.json')
        runtime = load(RUN / 'RESULT.json')
        audit = [json.loads(line) for line in read(RUN / 'audit.jsonl').splitlines()]
        observe = next(row for row in audit if row['event'] == 'observe')
        peer = load(OUT / 'ACTUAL_A_PERIPHERAL_REVIEW.json')
        decision = load(OUT / 'DECISION.json')
        report = read(OUT / 'REPORT.md').decode('utf8')
        freeze = load(OUT / 'SOURCE_FREEZE_A.json')
        parity = load(OUT / 'A_GIT_SOURCE_PARITY.json')
        expected_source = {row['path']: row['sha256'] for row in freeze['runtime_manifest']}
        git_source = {row['path']: row['sha256'] for row in parity['files']}
        reviewed_sources = {}
        for name in ('active_observation.py', 'active_observation_host.py', 'live_service.py', 'live_spatial_mcp.py'):
            relative = 'human_eye_plugin/' + name
            current = read(ROOT / relative)
            installed = read(Path('D:/he_m4_target_001/A/product') / relative)
            digest = hashlib.sha256(current).hexdigest()
            check('frozen_installed_source_' + name,
                  current == installed and digest == expected_source[relative] == git_source[relative])
            reviewed_sources[relative] = digest
        check('A_source_identity_matches_actual_runtime',
              public['binding']['runtime_source_sha256'] == runtime['source_sha256']
              == parity['source_sha256'] == decision['A_source141_sha256'])
        check('request_is_original_single_target', request['params']['arguments']['query'] ==
              {'mode': 'active_observation', 'objects': [{'name': 'M4_Far_00'}]})
        check('public_result_matches_actual_MCP_text', json.loads(response['result']['content'][0]['text']) == public)
        meta = capture['observation_target']
        meshes = capture['meshes']
        target_index = meta['target_object_index']
        target = meshes[target_index]
        check('actual_target_identity_and_scope',
              target_index == 13 and target['name'] == 'M4_Far_00'
              and target['object_id'] == meta['target_object_id']
              and meta['target_instance_id'] == capture['host_identity']['object_instances'][target['object_id']]
              and capture['capture_scope'] == capture['host_identity']['capture_scope'] == 'target_observation_meshes')
        check('A_retains_all_original_objects_and_geometry', len(meshes) == 14
              and sum(len(mesh['vertices']) for mesh in meshes) == 3474
              and sum(len(mesh['faces']) for mesh in meshes) == 6146
              and meta['retained_object_ids'] == [mesh['object_id'] for mesh in meshes]
              and not meta['excluded_object_ids'])
        objects = table(public['objects'])
        check('public_objects_match_current_capture_instances', all(
            row['object_index'] == index and row['host_id'] == mesh['object_id']
            and row['object_name'] == mesh['name']
            and row['instance_id'] == capture['host_identity']['object_instances'][mesh['object_id']]
            for index, (row, mesh) in enumerate(zip(objects, meshes))) and len(objects) == len(meshes))
        regions = table(public['regions'])
        check('one_supported_target_with_all_512_source_faces', len(regions) == 1
              and regions[0]['object_index'] == target_index and regions[0]['triangle_count'] == 512
              and regions[0]['source_triangle_index_ranges'] == [[0, 511]] and len(target['faces']) == 512)
        support = table(public['scope']['patch_support']['object_support'])
        check('thirteen_occluders_do_not_enter_unknown_denominator', len(support) == 14
              and all(row['support_status'] == 'occluder_only'
                      and row['supported_triangle_count'] == row['unsupported_triangle_count'] == 0
                      for row in support if row['object_index'] != target_index)
              and support[target_index]['support_status'] == 'fully_supported'
              and public['scope']['observation_scope']['target_object_count'] == 1
              and public['scope']['observation_scope']['occluder_only_object_count'] == 13
              and not public['scope'].get('objects_without_supported_roi'))
        check('brief_remains_M1_v5_with_small_target_binding', public['schema'] == 'active-observation-brief-v5'
              and 'scene_directory' not in public['binding']['observation_target']
              and 'camera_plan' not in public['binding']['observation_target'])

        vertices = [tuple(Fraction(value) for value in point) for point in target['vertices']]
        check('target_exact_plane_and_rectangle_extent', {point[0] for point in vertices} == {Fraction(1)}
              and min(point[1] for point in vertices) == min(point[2] for point in vertices) == 0
              and max(point[1] for point in vertices) == max(point[2] for point in vertices) == 1)
        areas = []
        for face in target['faces']:
            a, b, c = (vertices[index] for index in face)
            normal_x = (b[1] - a[1]) * (c[2] - a[2]) - (b[2] - a[2]) * (c[1] - a[1])
            areas.append(-normal_x / 2)
        check('all_target_triangles_have_negative_X_winding_and_unit_area',
              all(area > 0 for area in areas) and sum(areas) == 1)
        directions = {pose['name']: pose['direction_rational'] for pose in meta['camera_plan']['views']}
        statuses = {name: ('back_facing' if direction[0] > 0 else 'edge_on' if direction[0] == 0
                           else 'positive_area_occlusion') for name, direction in directions.items()}
        actual = observe['target_view_classifications']
        roi = regions[0]['roi_id']
        check('six_actual_view_classifications_match_independent_normal',
              len(actual) == 6 and all(actual[name][roi]['status'] == status for name, status in statuses.items()))
        check('no_complete_geometric_view_is_reported', all(actual[name][roi]['complete'] is False for name in statuses))
        near = next(mesh for mesh in meshes if mesh['name'] == 'M4_Near')
        near_points = [tuple(Fraction(value) for value in point) for point in near['vertices']]
        d = near_points[0][0]
        check('Near_is_original_small_plane_triangle', len(near['faces']) == 1
              and set(near_points) == {(d, Fraction(0), Fraction(0)), (d, Fraction(1), Fraction(0)),
                                       (d, Fraction(0), Fraction(1))} and 0 < d < 1)
        area = d * d / 2
        blocker = actual['LEFT'][roi]['first_blocker']
        check('LEFT_exact_positive_area_agrees_with_runtime', Fraction(blocker['overlap_area_screen_exact']) == area and area > 0)
        ordered = tuple(near_points[index] for index in near['faces'][0])
        canonical = min(ordered[index:] + ordered[:index] for index in range(3))
        geometry_id = hashlib.sha256(json.dumps(canonical, default=str, sort_keys=True,
                                                separators=(',', ':')).encode('utf8')).hexdigest()
        check('actual_blocker_identifies_Near_triangle', blocker['triangle_geometry_id'] == geometry_id)
        left = next(pose for pose in meta['camera_plan']['views'] if pose['name'] == 'LEFT')
        matrix, projection = np.asarray(left['view_matrix']), np.asarray(left['projection_matrix'])
        points = np.asarray(target['vertices'], dtype=np.float64)
        camera = points @ matrix[:3, :3].T + matrix[:3, 3]
        ndc = camera @ projection[:3, :3].T + projection[:3, 3]
        check('actual_LEFT_frustum_contains_target', np.all((ndc >= -1) & (ndc <= 1)) and np.all(camera[:, 2] < 0))
        check('correct_unknown_and_empty_complete_witness', regions[0]['status'] == 'unknown'
              and regions[0]['complete_witness_pixel_index'] is None
              and regions[0]['unobserved_reason'] == 'positive_area_occlusion_all_front_views'
              and public['inspection']['counts']['covered'] == 0
              and public['inspection']['counts']['no_geometric_complete_candidate'] == 1
              and public['inspection']['state'] == 'finite_pool_exhausted')

        png_path = next(RUN.rglob('*.png'))
        npz_path = next(RUN.rglob('*.npz'))
        png, npz = read(png_path), read(npz_path)
        delivered = base64.b64decode(response['result']['content'][1]['data'], validate=True)
        check('one_SCENE_image_only_and_exact_PNG_delivery', len(response['result']['content']) == 2
              and public['coverage']['observed_views'] == ['SCENE']
              and png == delivered and len(png) == 3223
              and hashlib.sha256(png).hexdigest() == table(public['images'])[0]['image_sha256'])
        rgb = np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))
        with np.load(io.BytesIO(npz), allow_pickle=False) as arrays:
            check('saved_RGB_equals_PNG', np.array_equal(arrays['color'], rgb) and rgb.shape == (512, 512, 3))
            owners, raw_ids, patch_ids = arrays['owners'], arrays['triangle_ids'], arrays['patch_owners']
            offsets, face_patch = arrays['face_patch_offsets'], arrays['face_patch_ids']
            expected_offsets = np.cumsum([0] + [len(mesh['faces']) for mesh in meshes])
            check('owner_offsets_match_all_captured_source_faces', np.array_equal(offsets, expected_offsets))
            foreground = owners >= 0
            check('source_triangle_owners_are_in_current_object_ranges',
                  np.all(owners < len(meshes)) and np.all(owners >= -1)
                  and np.all(raw_ids[foreground] >= offsets[owners[foreground]])
                  and np.all(raw_ids[foreground] < offsets[owners[foreground] + 1]))
            check('patch_ids_follow_original_source_triangle_winners',
                  np.array_equal(patch_ids[foreground], face_patch[raw_ids[foreground]]))
            expected_patch = np.full(len(face_patch), -1, dtype=np.int32)
            expected_patch[offsets[target_index]:offsets[target_index + 1]] = 0
            check('only_target_source_triangles_have_patch_ids', np.array_equal(face_patch, expected_patch))
            ys, xs = np.nonzero(patch_ids == 0)
            pixel = table(public['pixels'])[0]
            check('visible_surface_count_matches_actual_patch_pixels', len(xs) == pixel['visible_surface_pixels'] == 91559)
            bounds = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
            nearest = np.argmin((2 * xs - bounds[0] - bounds[2]) ** 2 + (2 * ys - bounds[1] - bounds[3]) ** 2)
            anchor = [int(xs[nearest]), int(ys[nearest])]
            check('actual_pixel_bounds_and_anchor_match_public', bounds == pixel['visible_pixel_bounds']
                  and anchor == pixel['visible_pixel_anchor'])
            check('back_facing_SCENE_pixels_do_not_become_readable', pixel['front_facing'] is False
                  and pixel['readable'] is False and public['observations']['rows'] == [[0, []]])
        check('independent_peer_review_agrees_without_replacing_actual_values', peer['passed_checked_scope'] is True
              and peer['actual_classifications'] == actual
              and peer['analytic_blocker']['exact_positive_area'] == str(area)
              and peer['saved_buffers']['contrasting_boundary_pixels'] == pixel['contrasting_boundary_pixels'] == 1127)

        io_rows = [json.loads(line) for line in read(RUN / 'io_audit/MCP_IO.jsonl').splitlines()]
        io_target = next(row for row in io_rows if row.get('id') == 'target_observation')
        wire = read(RUN / 'stdio/rpc_05/RX.bin')
        check('wire_response_decodes_to_saved_actual_response', json.loads(wire) == response)
        check('LF_audit_vs_CRLF_wire_correction_is_exact', wire.endswith(b'\r\n')
              and len(wire) == 12139 and len(wire.replace(b'\r\n', b'\n')) == io_target['RX_bytes'] == 12138
              and hashlib.sha256(wire.replace(b'\r\n', b'\n')).hexdigest() == io_target['RX_sha256'])
        check('reported_public_text_byte_count_is_exact', len(response['result']['content'][0]['text'].encode('utf8')) == 7088)
        work = meta['work']['residency_delta']
        check('reported_A_work_counts_match_actual_host_counters', work['to_mesh'] == work['triangulations'] == 14
              and work['resource_vertices_read'] == work['world_vertices_transformed'] == 3474
              and work['resource_faces_read'] == 6146 and work['directory_builds'] == work['directory_vertices'] == 0)
        check('root_decision_preserves_not_realized_and_unrun_B', decision['disposition'] == 'not_realized'
              and decision['A_public_target_entry_success'] is True
              and decision['A_new_target_witness_goal_realized'] is False
              and decision['B_status'] == 'not_implemented_after_qualification_exit'
              and decision['formal_slots_run'] == 0 and decision['engineering_performance_benefit'] is None
              and decision['target_complete_witnesses'] == 0)
        check('root_report_matches_checked_scope_and_known_limits', all(text in report for text in (
            '完整见证数为0', 'B 未实现', '7088', '3223', '12139', '12138',
            '缺少生产者原始 NPZ 摘要', 'LEFT 图片未构造', '输入规划在冻结前遗漏')))
        summary = {'source_files_reviewed': reviewed_sources, 'objects': 14, 'target_index': target_index,
                   'target_source_faces': 512, 'occluder_only_objects': 13, 'actual_classifications': actual,
                   'Near_plane_exact': str(d), 'LEFT_positive_occlusion_area_exact': str(area),
                   'target_unknown_correct': True, 'complete_witnesses': 0,
                   'actual_SCENE_visible_pixels': len(xs), 'actual_SCENE_bounds': bounds,
                   'actual_SCENE_anchor': anchor, 'actual_PNG_bytes': len(png), 'current_NPZ_bytes': len(npz),
                   'public_text_UTF8_bytes': 7088, 'actual_MCP_wire_bytes': len(wire),
                   'MCP_LF_text_audit_bytes': io_target['RX_bytes'], 'root_report_semantic_issues_found': []}
    except Exception as failure:
        error = {'type': type(failure).__name__, 'message': str(failure)}
    result = {'schema': 'm4-target-product-A-actual-review-v1', 'passed_checked_scope': error is None,
              'reviewer_association': 'Author of active_observation.py, active_observation_host.py, live_service.py and live_spatial_mcp.py target wiring',
              'checked_scope': 'Closed A_peripheral_02 public target semantics, four frozen sources, current saved arrays/PNG, source-face and byte claims',
              'disposition': 'not_realized', 'new_capability_goal_realized': False,
              'checks': CHECKS, 'failure': error, 'summary': summary,
              'limitations': ['One fixed engineering input and one successful A observation.',
                              'B, formal matrix and additional controls were not executed.',
                              'No independent reraster. LEFT has geometric evidence but no constructed image.',
                              'Current NPZ was inspected. The original producer full-frame/NPZ-hash receipt was absent in brief.',
                              'Boundary contrast count cross-checked with the separately pinned independent review; this script did not recompute contrast.',
                              'This product-author review is not the independent quality author review.'],
              'planning_limitation': 'The fixed input gate did not establish a complete unobstructed view before freezing the target. This is not a B performance failure.',
              'source_pins': sorted(PINS.values(), key=lambda row: row['path']),
              'new_product_observations': 0, 'new_Blender_starts': 0, 'new_rasters': 0,
              'new_model_calls': 0, 'product_imports': 0, 'frozen_product_edits': 0}
    with (OUT / 'PRODUCT_A_REVIEW.json').open('x', encoding='utf8', newline='\n') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    text = f"""# A 实际产品复核

本次复核 `passed_checked_scope={error is None}`，读取已关闭的 A_peripheral_02 原件，新增产品观察、Blender、raster、模型调用和产品import均为0。四份目标接线源码与A冻结、Git来源表及隔离安装逐字节一致。复核人是这四份文件的产品作者，独立质量审核另有已绑定报告。

实际公共请求以单元素 objects 指定 M4_Far_00，返回 brief-v5。目标为索引13、512个完整原始三角形，源面闭区间为[0,511]。其余13个对象仅参与遮挡，支持/不支持目标计数均为0，未成为unknown目标。A保留全部14对象、3474顶点与6146三角形。

目标在x=1平面、法向−X。根据实际目标三角形和六方向独立核对，SCENE/RIGHT背向，TOP/FRONT/BACK边缘朝向，LEFT为唯一正面。Near原三角形在x=d，d=8589935/2147483648。LEFT射线映射给出目标遮挡区域y≥0、z≥0、y+z≤d，其正面积为73786983304225/9223372036854775808。该面积及Near源三角形摘要与实际audit一致。实际LEFT视锥包含目标，六个complete均为false。

实际仅构造SCENE。已保存PNG与MCP图片块逐字节一致，RGB与当前NPZ一致，对象/源三角赢家及target patch映射一致。91559个目标可见像素、bounds和anchor从当前数组复算一致。SCENE的front_facing/readable保持false。1127个对比边界像素由独立质量报告交叉核对，本脚本没有重新计算该指标。

观察API的complete与目标unknown同时保留，covered=0、完整见证为空、finite_pool_exhausted符合当前证据。固定主输入没有达到完整可读见证目标。按预登记出口维持not_realized。输入冻结前没有确认存在无挡完整视图的规划不足保留，B和正式性能矩阵未运行。

实际公开文本7088 UTF8字节，PNG3223字节，原MCP RX为12139字节。写入文本的LF审计为12138字节，原wire结尾CRLF解释该1字节差异。根REPORT和DECISION中相关产品、目标、字节及scope措辞与本次已检查范围一致，未发现需要修改的声明。

限制为单个固定输入和一次成功A观察。LEFT没有构造图片，本复核没有独立reraster。当前NPZ可核，brief未交付生成时完整frame和NPZ摘要回执。工程收益、B收益、模型消费及更多场景仍未测。具体输入SHA、逐项检查和异常见PRODUCT_A_REVIEW.json。
"""
    if error is not None:
        text += '\n本次审核异常为' + json.dumps(error, ensure_ascii=False) + '。上述预期结论须结合JSON中已完成检查读取。\n'
    with (OUT / 'PRODUCT_A_REVIEW.md').open('x', encoding='utf8', newline='\n') as handle:
        handle.write(text)
    print(json.dumps({'passed_checked_scope': error is None, 'checks': len(CHECKS), 'failure': error,
                      'source_pins': len(PINS)}, ensure_ascii=False))
    if error is not None:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
