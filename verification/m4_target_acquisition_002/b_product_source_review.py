"""Read-only source and installed-qualification review before formal timing."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PINS = {}


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    PINS[str(path)] = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return raw


def load(path):
    return json.loads(read(path))


def unchanged_ast(raw):
    tree = ast.parse(raw.decode('utf8'))
    tree.body = [node for node in tree.body if not isinstance(node, ast.FunctionDef)
                 or node.name != '_observation_outside_xy_viewports']
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'capture_active_observation':
            node.body = [ast.Pass()]
            count += 1
    if count != 1:
        raise AssertionError('expected one acquisition function')
    return ast.dump(tree, include_attributes=False)


def main():
    binding = load(HERE / 'build_B/RUN_BINDING.json')
    freeze = load(HERE / 'SOURCE_FREEZE_B.json')
    installed = load(HERE / 'B_INSTALLED_PURE.json')
    pure = load(HERE / 'PRODUCT_PURE_01.json')
    numeric = load(HERE / 'B_NUMERIC_SOURCE_01.json')
    qualified = load(HERE / 'B_QUALIFICATION.json')
    load(HERE / 'A_QUALIFICATION.json')
    load(HERE / 'PREREGISTRATION.json')
    old = subprocess.run(['git', 'show', '4f8c41f89c9b40b3f310cf3f8e8b711bf09864a6:human_eye_plugin/blender_host.py'],
                         cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout
    source_path = ROOT / 'human_eye_plugin/blender_host.py'
    source, packaged = read(source_path), read(Path(binding['install_root']) / 'human_eye_plugin/blender_host.py')
    checks = {
        'source_and_installation_are_frozen_equal': source == packaged and hashlib.sha256(source).hexdigest() == numeric['source_sha256'],
        'frozen_B_identity': binding['preparation_git'] == 'c309d7e4302518cd5f7d1c3966e7c7fa338ea128'
            and binding['source_sha256'] == '776b0f0914e116fece16d2b3875ee16ffebf4896a7e394861287ffaa6fe025be',
        'all_other_host_AST_unchanged': unchanged_ast(old) == unchanged_ast(source),
        'installation_all_141_sources_equal': installed['passed_checked_scope'] is True and installed['source_install_parity_count'] == 141,
        'installed_four_pure_groups_pass': all(row['passed'] for row in installed['checks'])
            and [row['checks'] for row in installed['checks']] == [26, 29, 16, 17],
        'source_fake_acquisition_pass': pure['passed'] is True,
        'independent_numeric_pass': numeric['passed_checked_scope'] is True and numeric['case_count'] == 14,
        'actual_two_qualifications_quality_pass': qualified['passed_checked_scope'] is True and qualified['qualification'] == 'PASS'
            and len(qualified['records']) == 2 and all(row['passed_checked_scope'] for row in qualified['records']),
        'actual_cameras_facts_and_classifications_equal': all(row['actual_cameras_equal']
            and row['all_target_semantic_facts_equal'] and row['six_view_classifications_equal'] for row in qualified['records']),
        'quality_record_does_not_score_performance': qualified['performance_gate'] == 'not_evaluated_by_quality_checker',
    }
    report = {
        'schema': 'm4-target-acquisition-002-B-product-source-review-v1',
        'passed_checked_scope': all(checks.values()), 'checks': checks,
        'reviewer_association': 'B implementation author. Independent mathematical and saved-image quality results are attributed to the separate quality agent.',
        'candidate_git': binding['preparation_git'], 'source141_sha256': binding['source_sha256'],
        'host_source_sha256': hashlib.sha256(source).hexdigest(),
        'production_scope': ['human_eye_plugin/blender_host.py'],
        'source_review': {
            'selection': 'Only six strict XY viewport separations exclude an object. Unknown/edge/unsupported projection structure retains it.',
            'numeric_path': 'Existing view affine enclosure followed by outward multiplication using published positive XY projection coefficients covers exact and two-stage raster comparisons.',
            'raster_link': 'The fixed raster directly rejects a triangle whose three NDC vertices share a strict clip-plane bit, before polygon clipping and pixel mapping.',
            'budgets': 'Original global metadata limits, require_complete fallback, first target/unknown read, source revalidation and deadline remain in place.',
            'ordering': 'Retained and excluded are original-order subsequences; remaining detailed acquisition excludes already-read initial_ids.',
            'bindings': 'Existing full directory, subset host identity, retained/excluded, actual geometry revision and target/camera hashes distinguish scopes without a new cache system.',
            'counters': 'bound_tests counts entered object-view checks; residency counters measure actual host operations, expanded counts describe returned geometry.',
        },
        'qualification_reference': 'B_QUALIFICATION.json contains the independent actual A/B source, classification, camera and buffer checks for main and target_only.',
        'formal_results_reviewed': False,
        'performance_conclusion': None,
        'limitations': ['This product-author review is not the independent quality oracle.',
                        'The fake-host counts are not Blender-native timings.',
                        'No formal timing/cost data read or ranked by this review.',
                        'Dynamic actual-cache controls remain separately owned by root/harness.'],
        'source_pins': sorted(PINS.values(), key=lambda pin: pin['path']),
        'new_Blender_starts': 0, 'new_rasters': 0, 'new_product_observations': 0, 'new_model_calls': 0,
        'microbenchmarks_run': 0, 'prior_384_replays': 0, 'production_edits': 0,
    }
    with (HERE / 'B_PRODUCT_SOURCE_REVIEW.json').open('x', encoding='utf8', newline='\n') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    text = f"""# B 冻结源码及隔离检查复核

本次passed_checked_scope={report['passed_checked_scope']}，绑定c309d7e4与141源776b0f版本。host源码与隔离安装相同。除新增2D helper及capture_active_observation之外，宿主其他AST保持A原样，相机数值修复也保持。

选择判据使用实际view区间及已发布projection的向外舍入端点。六窗都严格在外才剔除。触边、未知及不支持结构继续读取；target、已初读unknown、require_complete沿原流程保留。原全局预算和来源重校验仍执行。原对象/面顺序和现有目录、subset身份、缓存绑定与brief语义继续使用。

B_INSTALLED_PURE首轮通过。提前ordinary preload安装版hook/live_service，实际capture/helper/camera/core/binding/MCP/read-context函数路径均来自B安装。141份源码一致，26采集、29公共合同、16缓存/预测与17旧pure分别通过。fake测试副本只复制既有bpy doubles、绑定安装版类，并显式使用binary32 local点保持同world，没有生产改动。

独立14项数字oracle与实际两项A/B资格均通过。资格记录保存同相机、六向分类、完整目标事实及缓冲比较。当前复核没有读取或排名正式计时数据，没有净收益结论。

复核人为B产品作者，独立质量作者另列。fake计数和原生耗时分开，实际动态缓存控制由根/harness另行核验。新增Blender、观察、raster、模型、micro与384重放均为0。\n"""
    with (HERE / 'B_PRODUCT_SOURCE_REVIEW.md').open('x', encoding='utf8', newline='\n') as handle:
        handle.write(text)
    print(json.dumps({'passed_checked_scope': report['passed_checked_scope'], 'checks': len(checks),
                      'source_pins': len(PINS)}))
    if not report['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
