"""Inspect frozen source differences and already closed public control records."""

import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = '03eb4e2971891dfe0160972cbcf974e3dcf1a21c'
CANDIDATE = '691f7b78ed89ccf30df47847fc1e99ad51a1dc64'
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


def git(*arguments):
    return subprocess.run(['git', *arguments], cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout


def masked_tree(raw, method):
    tree = ast.parse(raw.decode('utf8'))
    matches = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method:
            node.body = [ast.Pass()]
            matches += 1
    if matches != 1:
        raise AssertionError('expected one changed function ' + method)
    return ast.dump(tree, include_attributes=False)


def main():
    failure = None
    slots = []
    source_diff = []
    try:
        freeze = load(HERE / 'SOURCE_FREEZE.json')
        run_binding = load(HERE / 'build/RUN_BINDING.json')
        installed = load(HERE / 'INSTALLED_PURE_R1.json')
        first_installed = load(HERE / 'INSTALLED_PURE.json')
        load(HERE / 'INPUTS.json')
        load(HERE / 'INPUT_FREEZE.json')
        numeric = load(HERE / 'CANDIDATE_NUMERIC_INSTALLED_01.json')
        check('installed_R1_is_complete_and_141_files_match', installed['passed_checked_scope'] is True
              and installed['source_installation_parity_count'] == 141
              and [row['count'] for row in installed['checks']] == [16, 29, 16, 17]
              and all(row['passed'] for row in installed['checks']))
        check('first_installed_provenance_failure_preserved', first_installed['passed_checked_scope'] is False
              and first_installed['failure']['type'] == 'AssertionError'
              and 'human_eye_hook' in first_installed['failure']['message'])
        check('installed_independent_numeric_record_passed', numeric['passed'] is True and numeric['case_count'] == 6)
        changed = git('diff', '--name-only', BASELINE, CANDIDATE, '--', '*.py').decode('utf8').splitlines()
        production = [path for path in changed if not path.startswith('verification/')]
        check('only_two_product_files_changed', production == ['human_eye_plugin/blender_host.py',
                                                               'human_eye_plugin/live_spatial_mcp.py'])
        for path, method in [('human_eye_plugin/blender_host.py', '_observation_target_cameras'),
                             ('human_eye_plugin/live_spatial_mcp.py', '_error_result')]:
            old = git('show', BASELINE + ':' + path)
            committed = git('show', CANDIDATE + ':' + path)
            current, packaged = read(ROOT / path), read(Path(run_binding['install_root']) / path)
            check('committed_current_installed_equal_' + method, committed == current == packaged)
            check('all_other_AST_unchanged_' + method, masked_tree(old, method) == masked_tree(committed, method))
            source_diff.append({'path': path, 'method': method, 'baseline_sha256': hashlib.sha256(old).hexdigest(),
                                'candidate_sha256': hashlib.sha256(committed).hexdigest(),
                                'all_other_AST_unchanged': True})
        check('frozen_source_binding_matches_installed_run',
              run_binding['preparation_git'] == CANDIDATE
              and run_binding['source_freeze_sha256'] == hashlib.sha256(read(HERE / 'SOURCE_FREEZE.json')).hexdigest())

        for name in ('OLD_extreme', 'NEW_extreme', 'OLD_origin', 'NEW_origin', 'OLD_peripheral', 'NEW_peripheral'):
            directory = Path('D:/he_m4_camera_001/controls') / name
            result = load(directory / 'RESULT.json')
            public = load(directory / 'PUBLIC_01.json')
            response = load(directory / 'RESPONSE_01.json')
            request = load(directory / 'REQUEST_01.json')
            audit = [json.loads(line) for line in read(directory / 'audit.jsonl').splitlines()]
            check(name + '_closed_without_harness_errors', result['passed'] is True and result['errors'] == []
                  and result['MCP_runtime_exit']['confirmed'] is True
                  and result['MCP_runtime_exit']['exit_code'] == 0 and result['native_close']['process_reaped'] is True)
            check(name + '_fixed_public_request', request['params']['arguments']['include_image'] is True
                  and request['params']['arguments']['response_detail'] == 'full')
            check(name + '_saved_public_is_actual_text', json.loads(response['result']['content'][0]['text']) == public)
            for number in (2, 4):
                check(name + '_ping_' + str(number), load(directory / f'RESPONSE_{number:02d}.json')['result'] == {})
            readback = load(directory / 'PUBLIC_03.json')
            check(name + '_readback_succeeds', readback['status'] == 'observed'
                  and load(directory / 'RESPONSE_03.json')['result']['isError'] is False)
            readback_capture_path = next(directory.glob('READBACK_CAPTURE_*.json'))
            readback_capture = load(readback_capture_path)
            check(name + '_readback_is_real_single_object_source', len(readback_capture['meshes']) == 1
                  and readback_capture['capture_scope'] == 'selected_objects')
            saved = load(directory / 'SAVED_CAPTURES.json')
            check(name + '_readback_pinned_to_captured_command', any(
                entry['capture'] == str(readback_capture_path)
                and entry['capture_sha256'] == hashlib.sha256(read(readback_capture_path)).hexdigest()
                and entry['command']['command'] == 'capture_task' for entry in saved['captures']))
            render_attempts = [row for row in audit if row.get('event') == 'active_observation_render_attempt']
            target_events = [row for row in audit if row.get('target_view_classifications') is not None]
            slot = {'name': name, 'status': public['status'], 'isError': response['result']['isError'],
                    'reason': public.get('reason'), 'render_attempts': len(render_attempts),
                    'readback_geometry': readback_capture['meshes'][0]['vertices'],
                    'readback_faces': readback_capture['meshes'][0]['faces']}
            if name == 'NEW_extreme':
                check('NEW_extreme_strict_numeric_unknown', public['status'] == 'unknown'
                      and public['reason'] == 'active_observation_target_camera_numeric_insufficient'
                      and public['observation_status'] == 'numeric_insufficient'
                      and public['observation_mode'] == 'active_observation'
                      and response['result']['isError'] is True and public['automatic_retry'] is False)
                check('NEW_extreme_has_no_fabricated_primary_capture_or_image',
                      not {'binding', 'facts', 'frames', 'result_kind'} & set(public)
                      and len(response['result']['content']) == 1 and not render_attempts
                      and not list(directory.glob('MAIN_CAPTURE_*.json'))
                      and all(entry['command']['command'] == 'capture_task' for entry in saved['captures']))
            else:
                check(name + '_actual_classifications_retained', len(target_events) == 1
                      and public['target_view_classifications'] == target_events[0]['target_view_classifications'])
                capture = load(directory / 'MAIN_CAPTURE_01.json')
                target_id = capture['observation_target']['target_object_id']
                target = next(mesh for mesh in capture['meshes'] if mesh['object_id'] == target_id)
                check(name + '_readback_world_geometry_matches_target',
                      target['vertices'] == readback_capture['meshes'][0]['vertices']
                      and target['faces'] == readback_capture['meshes'][0]['faces'])
                slot['camera_plan'] = capture['observation_target']['camera_plan']
                slot['classifications'] = public['target_view_classifications']
                slot['counts'] = public['facts']['inspection']['counts']
                roi = public['facts']['regions'][0]['roi_id']
                left = slot['classifications']['LEFT'][roi]
                if name.endswith('origin'):
                    check(name + '_ordinary_control_keeps_complete_readable_witness',
                          public['facts']['regions'][0]['status'] == 'covered'
                          and public['facts']['inspection']['counts']['covered'] == 1
                          and public['facts']['region_evidence'][0]['complete_witness'] is not None
                          and left['complete'] is True)
                elif name.endswith('peripheral'):
                    check(name + '_old_geometric_unknown_keeps_exact_blocker',
                          public['facts']['regions'][0]['status'] == 'unknown'
                          and public['facts']['inspection']['counts']['covered'] == 0
                          and public['facts']['region_evidence'][0]['complete_witness'] is None
                          and left['status'] == 'positive_area_occlusion'
                          and left['first_blocker']['overlap_area_screen_exact'] == '73786983304225/9223372036854775808')
                else:
                    check('OLD_extreme_reproduces_false_outside_frustum', left['status'] == 'outside_frustum'
                          and public['facts']['inspection']['counts']['covered'] == 0)
                frames = public['frames']
                image_blocks = [block for block in response['result']['content'] if block['type'] == 'image']
                check(name + '_frame_and_attempt_counts_agree', len(frames) == len(image_blocks) == len(render_attempts))
                for index, (frame, block) in enumerate(zip(frames, image_blocks)):
                    png = read(frame['image_path'])
                    check(name + '_producer_PNG_receipt_' + str(index),
                          png == base64.b64decode(block['data'], validate=True)
                          and hashlib.sha256(png).hexdigest() == frame['image_sha256'])
                    check(name + '_producer_NPZ_receipt_' + str(index),
                          hashlib.sha256(read(frame['arrays_path'])).hexdigest() == frame['arrays_sha256'])
            slots.append(slot)
        by_name = {slot['name']: slot for slot in slots}
        for case in ('origin', 'peripheral'):
            check(case + '_published_camera_plan_unchanged_old_new',
                  by_name['OLD_' + case]['camera_plan'] == by_name['NEW_' + case]['camera_plan'])
        check('extreme_readback_geometry_same_old_new',
              by_name['OLD_extreme']['readback_geometry'] == by_name['NEW_extreme']['readback_geometry']
              and by_name['OLD_extreme']['readback_faces'] == by_name['NEW_extreme']['readback_faces'])
    except Exception as error:
        failure = {'type': type(error).__name__, 'message': str(error)}
    result = {
        'schema': 'm4-target-camera-final-product-review-v1', 'passed_checked_scope': failure is None,
        'reviewer_association': 'Author of the exact MCP error mapping and earlier target wiring. Camera guard authored by root. Independent numerical oracle has a separate author.',
        'candidate_commit': CANDIDATE, 'baseline_commit': BASELINE,
        'source_diff': source_diff, 'checks': CHECKS, 'failure': failure,
        'actual_closed_slots': slots, 'installed_pure_final': 'INSTALLED_PURE_R1.json',
        'installed_pure_first_attempt': 'INSTALLED_PURE.json',
        'installed_runner_correction': 'Initial fixtures caused a late absolute human_eye_hook import from the same-byte checkout. That provenance gate failed. R1 preloads installed live_service and hook before fixtures, and all loaded human_eye product modules remain installed.',
        'guard_review': {
            'fit': 'The 1.1 XY span and published ordinary matrices remain the original values. No epsilon added to geometric coverage.',
            'rounding': 'The local relative fit, computed center/translation residual and global affine raster evaluation are enclosed with positive operand magnitudes, gamma32 and an absolute gradual-underflow allowance. Each interval edge and final multiplication by the published inverse half span round outward.',
            'conservative_exit': 'Any nonfinite or out-of-viewport enclosure yields the exact numeric-insufficient token, retaining an explicit unknown outcome without enlarging the viewport.',
            'legacy': 'AST comparison excludes only the two edited functions. Other module semantics, full-scene camera logic, depth bound logic, capture and coverage code are unchanged.',
            'accepted_domain': 'Standard finite binary64 arithmetic and fixed published coefficients, reviewed against the frozen six-case independent installed numerical record. No claim of all possible unsupported geometry or numerical environments.'},
        'limitations': ['The extreme case is explicit numeric insufficiency, not restored complete-image capability.',
                        'Synthetic mapping/cache assertions are not extra camera scenes.',
                        'Saved producer PNG/NPZ receipts were byte-checked. This review did not reraster arrays or independently remeasure every pixel.',
                        'No microbenchmark rerun and no new performance claim.',
                        'Historical A01 runtime exit unknown and cache deletion refusal remain their original states.'],
        'source_pins': sorted(PINS.values(), key=lambda pin: pin['path']),
        'new_product_observations': 0, 'new_Blender_starts': 0, 'new_rasters': 0, 'new_model_calls': 0,
        'microbenchmarks_run': 0, 'production_edits_during_review': 0,
    }
    with (HERE / 'FINAL_PRODUCT_REVIEW.json').open('x', encoding='utf8', newline='\n') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    text = f"""# 冻结候选产品复核

本复核 passed_checked_scope={failure is None}，绑定候选691f7b78、SOURCE_FREEZE和隔离安装。生产差异只有目标相机函数和MCP错误映射，AST核对其他代码保持相同。

相机保留原1.1倍拟合span，复用目标相对坐标计算，并对最终发布view/projection系数给出向外舍入的XY误差包络。guard覆盖局部拟合、中心/平移残差和全局binary64求值的差异。包络不足时明确numeric_insufficient，覆盖阈值和viewport没有扩张。

远端映射要求精确错误dict键、宿主类型、message及布尔false。本地只接受精确BlenderHostError类及相同token。MCP保留isError=true、原error和禁止自动重试，结果没有伪造来源binding或几何facts。

隔离检查最终采用INSTALLED_PURE_R1.json。mapping16、target公共合同29、缓存/来源/预测16和旧pure17分别通过，141份当前/安装源码一致，实际被测函数来源均在安装目录。首轮INSTALLED_PURE.json保留为来源检查失败。其pure断言虽通过，但live_service加载较晚，测试fixture插入源码路径后使绝对human_eye_hook导入同字节源码副本。R1只调整runner预加载顺序，生产源码保持冻结。

六个已关闭实机槽经原件核读。OLD_extreme保留outside_frustum，NEW_extreme明确数值不足unknown，零主capture、零图片。两者后续ping与单对象source readback均成功，读回真实世界几何相同。旧新origin都取得完整见证，旧新peripheral都保留Near正面积遮挡unknown，ordinary两对相机plan完全相同。保存PNG/NPZ与生产者摘要、实际图片块一致。

本复核新增Blender、观察、raster、模型和microbenchmark均为0。极值没有恢复完整图片能力。纯合同断言、六相机输入与六实际槽分别记录。复核人是错误映射及此前target接线作者，独立数值审核另有作者。原A01退出unknown与删除拒绝不因本轮新进程而改变。
"""
    if failure:
        text += '\n审核异常为' + json.dumps(failure, ensure_ascii=False) + '，以上陈述须按JSON中已完成检查的范围读取。\n'
    with (HERE / 'FINAL_PRODUCT_REVIEW.md').open('x', encoding='utf8', newline='\n') as handle:
        handle.write(text)
    print(json.dumps({'passed_checked_scope': failure is None, 'checks': len(CHECKS),
                      'closed_slots': len(slots), 'failure': failure, 'source_pins': len(PINS)}))
    if failure:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
