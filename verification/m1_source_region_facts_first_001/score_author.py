"""Record the author's source-grounded scoring after unified answer sealing."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time


HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.perf_counter_ns()
    sealed = json.loads((HERE / 'ANSWERS_SEALED.json').read_bytes())
    assert len(sealed['answers']) == 3
    rubric = json.loads((HERE / 'scoring/RUBRIC.json').read_bytes())
    cases = []
    # Gate evidence uses one-based physical text lines, including blank lines.
    evidence = {
        'S1': [(3, 4), (10, 15), (3, 4), (22, 24), (22, 22), (22, 26),
               (23, 26), (30, 36), (19, 36)],
        'S2': [(3, 4), (10, 14), (3, 4), (33, 37), (27, 27), (26, 34),
               (29, 37), (41, 44), (19, 46)],
        'S3': [(3, 3), (5, 11), (11, 11), (25, 27), (19, 19), (20, 25),
               (23, 27), (31, 36), (5, 36)],
    }
    reasons = {
        'G1': '原答准确报告米值，并正确换算为37.0117厘米。冻结规则要求同时给出毫米等价量，原答未报告毫米，因此该门失败。这里未观察到距离数值或厘米换算错误。',
        'G2': '选区A与Cube参考B的端点、源三角形、源顶点及最近见证字段对应本例原始来源，区域短引用可唯一解析。',
        'G3': '明确采用完整所选三角并集到参考三角表面的世界米制距离，并保留局部选区范围。',
        'G4': '本例显示参与与图像证据状态被正确采用，几何量测在缺少相应图片证据时仍保留。',
        'G5': '本例选区可见表面像素计数与原记录一致。',
        'G6': '可见采样与无采样选中三角数量均正确，并以本例图像和visibility字段绑定。',
        'G7': '原答保留完整可见性的不确定性，说明当前无采样或不完整图像证据，并交代进一步实体判定缺少的证据。',
        'G8': '正的完整选区表面距离被用于所测两个表面的分离、无接触和无交点，实体内外保持信息不足。',
        'G9': '主要量测、区域、图像、显示和unknown结论都有当前例的可解析来源。额外方向与拓扑说明符合公开事实，未找到无依据的确定内外或修复断言。',
    }
    special = {
        ('S1', 'G4'): '图像提供局部样本，Cube未参加显示，Cube继续充当明确的几何量测参考。',
        ('S2', 'G4'): '选区与Cube均参与视口显示，选区没有可见像素，采用displayed_without_pixels及partial/evidence_insufficient。',
        ('S3', 'G4'): '选区宿主与Cube均未参加显示，所选区域几何量测完成而视觉证据不足。',
        ('S1', 'G7'): '明确写出complete_surface_visibility未知及complete_witness为空，363个面和已采样面上的未显露部分仍缺图像证据。',
        ('S2', 'G7'): 'visibility为unknown、完整见证为空，全部748个面没有图像样本且原因未确定。末段保留视觉证据不足和来源时点，实体分类缺有效实体及包含性证据。',
        ('S3', 'G7'): '明确写出完整表面可见性unknown，并指出视觉核验还缺实际显示选区和两对象的有效图像。',
    }
    for answer in sealed['answers']:
        case = answer['case_id']
        path = Path(answer['copy_path'])
        assert sha(path) == sha(Path(answer['original_path'])) == answer['sha256']
        lines = path.read_text(encoding='utf8').splitlines()
        brief = json.loads((HERE / 'inputs' / case / 'ORIGINAL_BRIEF.json').read_bytes())
        gates = []
        for index, gate in enumerate(rubric['gates']):
            first, last = evidence[case][index]
            verdict = 'fail' if gate['id'] == 'G1' else 'pass'
            gates.append({'gate_id': gate['id'], 'gate_name': gate['name'], 'verdict': verdict,
                'evidence': [{'answer_line_start': first, 'answer_line_end': last,
                              'quote': '\n'.join(lines[first - 1:last])}],
                'expected_original_brief_json_pointers': gate['sources'],
                'reference_resolution': {'region_id': brief['region_ref']['region_id'],
                    'image_ref': brief['images'][0]['image_ref'],
                    'field_reference_scope': 'The single current-case bound observation. v2 paths resolve through task_result.facts, source_mapping, visibility and image_scope.'},
                'reason': special.get((case, gate['id']), reasons[gate['id']]),
                'failure_classes': ['distance_or_unit_error'] if verdict == 'fail' else [],
                'failure_detail': 'required_millimetre_equivalent_omitted' if verdict == 'fail' else None})
        cases.append({'case_id': case, 'answer': {'path': str(path), 'sha256': sha(path), 'line_count': len(lines)},
            'execution_and_delivery': {'slot_status': answer['slot_status'], 'content_scoring_separate': True},
            'numeric_adoption': {'reported_m': '0.37011719389236364', 'reported_cm': '37.0117',
                'reported_mm': None, 'metre_value_absolute_error_m': 0,
                'centimetre_value_absolute_error_m': abs(0.37011719389236364 - 37.0117 / 100),
                'reason': 'Accurate physical quantity in metres and centimetres. The frozen millimetre reporting gate is unmet.'},
            'gates': gates, 'passed_gates': 8, 'failed_gates': ['G1'], 'unrun_gates': [], 'accepted': False})
    value = {'schema': 'm1-source-region-facts-first-author-scores-v1',
        'task': 'M1-SOURCE-REGION-FACTS-FIRST-001', 'scored_at_UTC': datetime.now(timezone.utc).isoformat(),
        'started_ns': started, 'closed_ns': time.perf_counter_ns(),
        'method': 'Author manual review against the unchanged nine frozen gates after all three originals were sealed. No additional consumers or answer edits.',
        'frozen_inputs': {name: sha(HERE / 'scoring' / name) for name in ('RUBRIC.json', 'CASE_ANSWERS.json', 'SCORE_METHOD.md')},
        'answers_sealed_sha256': sha(HERE / 'ANSWERS_SEALED.json'),
        'rules_changed': False, 'cases': cases,
        'summary': {'accepted_cases': 0, 'case_denominator': 3, 'passed_gates': 24, 'gate_denominator': 27,
                    'failed_gates': 3, 'unrun_gates': 0, 'all_failed_gate_ids': ['G1'],
                    'failure_scope': 'All three accurately adopt distance and a centimetre conversion but omit the frozen required millimetre conversion.'},
        'review_observation': 'The common prompt requests distance and units generally. The private frozen G1 specifically requires metres and millimetres. This alignment limitation is disclosed without changing the original scoring result.'}
    with (HERE / 'scoring/AUTHOR_SCORES.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(value['summary']))


if __name__ == '__main__':
    main()
