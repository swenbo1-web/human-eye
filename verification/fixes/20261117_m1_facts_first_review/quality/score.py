"""Independent original-gate and actual-prompt alignment review.

Decisions are human semantic assessments. The program verifies source facts,
exact quotations, copied answers and Decimal conversions before sealing them.
Author and author-independent scores are excluded from this phase.
"""
from collections import Counter
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
NS = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m1_source_region_facts_first_001')
PINS = {}


def raw(path):
    data = Path(path).read_bytes()
    PINS[str(path)] = dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    return data


def read(path):
    return json.loads(raw(path))


QUOTES = {
    'S1': {
        'G1': '0.37011719389236364 m',
        'G2': 'task_result.source_mapping.nearest_witness',
        'G3': '测量范围覆盖全部选中源三角形',
        'G4': '`Cube` 的 `participates: false`、`visible_get: false`',
        'G5': '35,452',
        'G6': '363 个选中三角形没有当前帧可见采样',
        'G7': 'complete_surface_visibility',
        'G8': '选区表面与参考表面分离、不接触、不相交',
        'G9': 'source-region:5465d50b1c1b3c8057f9c2356903e1a0df7996e81c9ee7210ddda2788e806722',
    },
    'S2': {
        'G1': '0.37011719389236364 m',
        'G2': 'task_result.source_mapping.nearest_witness',
        'G3': '完整选区的三角形并集',
        'G4': '选区所属对象与 `Cube` 都被记录为参与当前视口显示',
        'G5': '选区表面可见像素数',
        'G6': '全部 748 个选区三角形都没有获得本帧的可见表面像素证据',
        'G7': '完整可见性见证',
        'G8': '完整选区与 `Cube` 的当前求值三角形表面严格分离',
        'G9': 'source-region:67406db56fa00e9b715175753e4906dd87c159ab0d5238ca95c46f1ede9de873',
    },
    'S3': {
        'G1': '0.37011719389236364 m',
        'G2': 'task_result.source_mapping',
        'G3': 'complete_selected_source_triangle_union_to_reference_triangle_surface',
        'G4': '选区宿主和 `Cube` 均未参与当前视图显示',
        'G5': '选区可见表面像素',
        'G6': '未见选区三角形',
        'G7': '完整表面可见性仍为 `unknown`',
        'G8': '所测完整选区与参考三角形表面分离，不相交、不接触',
        'G9': 'source-region:9dac0581531ea07b6555cf45b7a2d57b9fd426bed863947cf7d0cc17bea5a6bb',
    },
}

REASONS = {
    'G1': '米原值完整正确，约37.0117cm为忠实换算。原私有G1同时要求毫米，回答缺少mm，故严格fail。',
    'G2': '本例region及原最近见证正确，A源面48160/48161、源顶点24331，B属Cube面0，坐标及+Z方向匹配公开输入。',
    'G3': '明确当前求值世界几何的完整选区到Cube参考三角形表面，不限可见子集且不外推整体对象。',
    'G4': '采用本例显示参与和图像状态，保留独立已测几何事实。S1目标有样本且Cube排除，S2双方参与且零样本，S3双方排除且视觉证据不足。',
    'G5': '选区像素准确。S1为35452，S2/S3均为0，引用本例图像及visibility。',
    'G6': 'S1准确识别385有样本和363无样本，并限制为实际像素采样。S2/S3明确全部748无样本，来源和原因保持本例范围。',
    'G7': '完整曲面可见性保持unknown，说明未观察部分、视觉证据和实体内外分类所缺来源。',
    'G8': '实际采用正距离支持完整选区与参考表面分离/无接触，保持无符号距离的实体内外限制，无+Z外法线或整对象外推。',
    'G9': '区域/图像/见证均解析当前封存case。未观察原因保持未测或条件表述，额外拓扑与显示结论有公开字段支持。',
}


def main():
    prompt = raw(NS/'inputs/PROMPT.txt').decode('utf8').strip()
    raw(NS/'inputs/M1_SOURCE_REGION_FACTS_FIRST_001_PLAN.md')
    raw(NS/'scoring/SCORE_METHOD.md')
    rubric = read(NS/'scoring/RUBRIC.json')
    schema = read(NS/'inputs/TOOL_SCHEMA.json')
    assert prompt == rubric['common_prompt_verbatim']
    assert '单位' in prompt and '毫米' not in prompt and 'mm' not in prompt
    assert '毫米' not in schema['description'] and 'mm' not in schema['description']
    seals = read(NS/'ANSWERS_SEALED.json')
    original_rubric = Path('D:/hefe/verification/fixes/20261117_source_region_consumption_review/quality/BLIND_SCORES.json')
    prior = read(original_rubric)
    prior_rubric_pin = next(v for k,v in prior['input_pins'].items() if k.endswith('scoring\\RUBRIC.json') or k.endswith('scoring/RUBRIC.json'))
    assert PINS[str(NS/'scoring/RUBRIC.json')]['sha256'] == prior_rubric_pin['sha256']
    gate_definitions = {g['id']:g for g in rubric['gates']}
    expected_m = D('0.37011719389236364')
    reported_cm = D('37.0117')
    cases = []
    for case in ('S1','S2','S3'):
        answer_path = NS/'answers'/(case+'.txt')
        answer_bytes = raw(answer_path)
        answer = answer_bytes.decode('utf8')
        seal = next(v for v in seals['answers'] if v['case_id'] == case)
        assert hashlib.sha256(answer_bytes).hexdigest() == seal['sha256']
        assert answer_bytes == raw(seal['original_path'])
        brief = read(NS/'inputs'/case/'ORIGINAL_BRIEF.json')
        tool = read(NS/'inputs'/case/'TOOL_RESULT.json')
        assert json.loads(tool['content'][0]['text']) == brief
        assert brief['schema'] == 'source-region-brief-v2'
        measurement = brief['task_result']
        fact = measurement['facts']['surface_proximity']
        assert D(str(fact['value']['distance_m'])) == expected_m
        assert measurement['unit'] == 'm' and measurement['coordinate_frame'] == 'world'
        assert measurement['reference']['name'] == 'Cube'
        assert measurement['measurement_scope'] == 'complete_selected_source_triangle_union_to_reference_triangle_surface'
        witness = fact['value']['nearest_witness']
        mapping = measurement['source_mapping']['nearest_witness']
        assert witness['a'] == [-0.016845703125,0.1462402619080522,0.6298828061076364]
        assert witness['b'] == [-0.016845703125,0.1462402619080522,1.0]
        assert witness['direction_a_to_b'] == [0.,0.,1.]
        assert mapping['a']['source_triangle_indices'] == [48160,48161]
        assert mapping['a']['source_vertex_indices'] == [24331]
        assert mapping['b']['source_triangle_indices'] == [0]
        assert all(str(coord) in answer for point in ('a','b') for coord in witness[point])
        assert all(str(index) in answer for index in (48160,48161,24331))
        assert '37.0117 cm' in answer and '0.37011719389236364 m' in answer
        assert '毫米' not in answer and ' mm' not in answer
        assert expected_m*100 == D('37.011719389236364')
        assert (expected_m*100).quantize(D('0.0001')) == reported_cm
        refs = dict(region_id=brief['region_ref']['region_id'],image_ref=brief['visibility']['image_ref'])
        assert all(value in answer for value in refs.values())
        visibility = brief['visibility']
        counts = (visibility['selected_surface_pixels'],visibility['visible_source_triangle_count'],visibility['unseen_source_triangle_count'])
        assert counts == ((35452,385,363) if case == 'S1' else (0,0,748))
        assert visibility['complete_witness'] is None and visibility['unknown'] == ['complete_surface_visibility']
        assert brief['image_scope']['participation_mask'] == {'S1':[True,False],'S2':[True,True],'S3':[False,False]}[case]
        assert brief['status'] == ('complete' if case == 'S1' else 'partial')
        assert brief['observation_status'] == ('locally_observed' if case == 'S1' else 'evidence_insufficient')
        gates = {}
        for gid in gate_definitions:
            quote = QUOTES[case][gid]
            assert quote in answer, (case,gid,quote)
            gates[gid] = dict(verdict='fail' if gid == 'G1' else 'pass',
                answer_quote=quote,answer_line=answer[:answer.index(quote)].count('\n')+1,
                expected_sources=gate_definitions[gid]['sources'],reason=REASONS[gid])
        obligations = [
            dict(id='O1',obligation='最近距离与正确单位',verdict='pass',reason='完整m原值满足题面，附加cm换算正确。题面没有指定mm或双单位。'),
            dict(id='O2',obligation='原见证与来源',verdict='pass',reason=REASONS['G2']),
            dict(id='O3',obligation='本图选区证据与可见像素',verdict='pass',reason=REASONS['G4']+' '+REASONS['G5']),
            dict(id='O4',obligation='未观察部分与缺失信息',verdict='pass',reason=REASONS['G6']+' '+REASONS['G7']),
            dict(id='O5',obligation='表面关系及实体内外的有据判断',verdict='pass',reason=REASONS['G8']),
            dict(id='O6',obligation='当前区域/图像引用与封存范围',verdict='pass',reason=REASONS['G9']),
        ]
        cases.append(dict(case_id=case,strict_original_accepted=False,
            strict_gate_counts=dict(Counter(g['verdict'] for g in gates.values())),strict_gates=gates,
            actual_prompt_obligations=obligations,actual_prompt_satisfied=True,remaining_actual_task_omissions=[],
            current_refs=refs,published_measurement_witness=witness,
            exact_distance_m=str(expected_m),exact_distance_cm=str(expected_m*100),
            reported_cm=str(reported_cm),reported_cm_converted_m=str(reported_cm/100),
            cm_rounding_absolute_error_m=str(abs(reported_cm/100-expected_m)),
            visibility=dict(pixels=counts[0],sampled_triangles=counts[1],unseen_triangles=counts[2],
                complete_visibility_unknown=True,status=brief['status'],observation_status=brief['observation_status'])))
    result = dict(schema='independent-facts-first-quality-and-prompt-alignment-v1',
        phase='independent_before_author_comparison',author_scores_read=False,
        author_commit='544cf4f123c35fbca24b8f425acc30fd3308b178',
        actual_prompt=prompt,original_frozen_rubric_unchanged=True,
        strict_preregistered_result=dict(cases=3,accepted=0,gate_pass=24,gate_fail=3,gate_unrun=0,
            failure_reason='All original G1 failures are the missing millimetre expression required by the private rubric.'),
        actual_prompt_alignment=dict(cases=3,satisfied=3,explicit_unit_requirement='report the distance and unit',
            millimetre_requirement_present_in_actual_prompt=False,
            millimetre_requirement_present_in_tool_description=False,
            correct_metres_alone_satisfies_prompt=True,metres_plus_faithful_centimetres_satisfies_prompt=True,
            extra_private_requirement='Report metres and the millimetre equivalent.',
            remaining_actual_task_omissions=[],
            interpretation='Descriptive alignment audit of sealed answers against the original public task. Preserve the original strict 0/3 record.'),
        cases=cases,input_pins=PINS,
        new_calls=dict(live=0,MCP=0,raster=0,PNG_encoding=0,model=0,paid=0),
        private_reasoning_bodies_read=0)
    path=OUT/'BLIND_SCORES.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(strict=result['strict_preregistered_result'],actual=result['actual_prompt_alignment'],
        blind_sha256=hashlib.sha256(path.read_bytes()).hexdigest()),ensure_ascii=False))


if __name__ == '__main__':
    main()
