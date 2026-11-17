"""Human independent rubric decisions, validated against public sealed evidence.

This first phase deliberately has no author-score input. No raw consumer events,
hidden reasoning, image decoding, product execution, or model calls are used.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
NS = AUTHOR / 'verification/m4_source_region_consumption_001'
RUN = Path('D:/he_m4_source_region_consume_001/slots')
PINS = {}


def raw(path):
    data = Path(path).read_bytes()
    PINS[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def read(path):
    return json.loads(raw(path))


def gate(verdict, quote, reason, sources, failure_class=None):
    return dict(verdict=verdict, quote=quote, reason=reason, expected_sources=sources,
                failure_class=failure_class)


SHARED = {
    'G1': ['/task_result/facts/surface_proximity/value/distance_m', '/task_result/reference'],
    'G2': ['/region_ref', '/task_result/facts/surface_proximity/value/nearest_witness',
           '/task_result/source_mapping/nearest_witness', '/task_result/reference'],
    'G3': ['/measurement_scope', '/task_result/measurement_scope'],
    'G4': ['/status', '/observation_status', '/binding/image_scope', '/visibility/reason',
           '/task_result/status'],
    'G5': ['/visibility/selected_surface_pixels', '/visibility/image_ref'],
    'G6': ['/visibility/visible_source_triangle_indices', '/visibility/unseen_source_triangle_indices'],
    'G7': ['/visibility/unknown', '/visibility/complete_witness', '/unknowns'],
    'G8': ['/task_result/measurement_scope', '/task_result/facts/surface_proximity'],
    'G9': ['/region_ref', '/visibility/image_ref', '/binding/capture_state'],
}


def decisions():
    s1 = {gid: gate('unrun', '接口两次均返回 `empty_parameter_read_observation_required`',
        '协议未交付原观测，缺少内容评分前提。保留本例及九门分母，几何错误计数为零。',
        sources, 'execution_or_image_delivery_failure') for gid, sources in SHARED.items()}
    s2 = {
        'G1': gate('fail', '目前不能可靠报告最近距离数值、单位或最近点／三角形见证。',
            '遗漏本例已测0.37011719389236364米及370.11719389236364毫米。', SHARED['G1'], 'distance_or_unit_error'),
        'G2': gate('fail', '距离数值及见证不可读取',
            '区域R解析正确，原最近见证及A/B参考归属未采用。', SHARED['G2'], 'measurement_source_or_witness_error'),
        'G3': gate('pass', '完整选中源三角形并集到参考三角形表面',
            '明确完整748面量测并集、图像可见部分的作用范围，引用当前R与measurement_scope。', SHARED['G3']),
        'G4': gate('fail', 'selected_object_participates: true',
            '正确采用目标参与、零样本和图像证据不足，遗漏冻结S2要求的Cube也参与显示事实，并将既有量测数值悬置。',
            SHARED['G4'], 'display_scope_or_status_error'),
        'G5': gate('pass', '选区可见像素数为 0',
            '像素数准确且引用本例图像I。', SHARED['G5']),
        'G6': gate('pass', '全部 748 个选中三角形均未获得当前帧的可见像素证据',
            '准确标识全部未见选集和实际帧样本范围。', SHARED['G6']),
        'G7': gate('pass', '因此无法观察选区形状、表面间隙、接触位置或最近距离见证所在位置',
            '零样本与全748面未观察的表述保持完整可见性未知，指出图像证据不足，实体分类所缺封闭网格/内外分类来源明确。接受同义表达。', SHARED['G7']),
        'G8': gate('fail', '当前不能判定表面分离、接触或相交',
            '实体内外推断保持正确边界，但未据已测正距离给出本选区与参考表面分离的实际结论。条件解释不能替代本例所需结论。',
            SHARED['G8'], 'surface_or_solid_inference_error'),
        'G9': gate('pass', '本报告仅依据这份封存观测',
            'R和I均唯一解析到本例，主要空间/图像结论的引用对应，未虚构outside、inside或确定遮挡原因。截断为消费者自述，实际模型视域未测，该自述单列。', SHARED['G9']),
    }
    s3 = {
        'G1': gate('fail', '距离数值、单位及最近点见证无法可靠报告',
            '遗漏本例已测0.37011719389236364米及毫米换算。', SHARED['G1'], 'distance_or_unit_error'),
        'G2': gate('fail', '相关字段未出现在可读取内容中',
            '当前R绑定正确，原最近见证及A/B参考归属未采用。', SHARED['G2'], 'measurement_source_or_witness_error'),
        'G3': gate('pass', '完整选中源三角形并集到参考三角形表面',
            '完整选集量测范围准确，引用当前R及measurement_scope。', SHARED['G3']),
        'G4': gate('pass', '整体状态为 `partial / evidence_insufficient`',
            '采用目标未显示原因、当前partial状态，并保留当前几何测量完成及范围。数值遗漏另计G1/G2/G8。', SHARED['G4']),
        'G5': gate('pass', '选区可见像素为 0',
            '数值准确并引用当前R显示记录与图像I。', SHARED['G5']),
        'G6': gate('pass', '未观察到的是全部 748 个选中源三角形的表面外观',
            '正确标识完整未见选集，并给出目标不参与显示原因。', SHARED['G6']),
        'G7': gate('pass', '不能从这张图确认选区形状、朝向、接触位置或最近点位置',
            '图像排除选区、全部748面无样本，完整可见性保持未知。明确相应图像证据和实体分类来源的缺口。', SHARED['G7']),
        'G8': gate('fail', '本次可读取内容不足以给出确定的接触、分离或实体内外结论',
            '内外判断正确保持来源要求，实际所需正距离支持表面分离结论未采用，仅以条件规则表达。', SHARED['G8'], 'surface_or_solid_inference_error'),
        'G9': gate('pass', '仅分析这份观测',
            'R/I及revision4解析到本例。当前图片无参与对象与Cube排除均有本例来源，无额外确定几何/修复主张。截断自述单列。', SHARED['G9']),
    }
    # S3 expresses the sealed-capture restriction in its source binding and scope,
    # while the exact quoted text below supplies a direct validated anchor.
    s3['G9']['quote'] = '采集代次 `epoch=1 / revision=4`'
    return {'S1': s1, 'S2': s2, 'S3': s3}


def projected_calls(case, filename, brief):
    rows = []
    for line in raw(NS / 'runtime_archive' / filename).decode('utf8').splitlines():
        event = json.loads(line)['event']
        item = event.get('item', {})
        # The repository has already removed private reasoning bodies. This
        # reader only extracts publicly completed MCP tool calls.
        if event.get('type') != 'item.completed' or item.get('type') != 'mcp_tool_call':
            continue
        result = item.get('result')
        text = [c['text'] for c in (result or {}).get('content', []) if c.get('type') == 'text']
        observations = []
        for t in text:
            try:
                value = json.loads(t)
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict) and value.get('result_kind') == 'source_region':
                assert value == brief
                observations.append(dict(exact_public_brief=True,
                    text_bytes=len(t.encode('utf8')),
                    distance_m=value['task_result']['facts']['surface_proximity']['value']['distance_m'],
                    literal_truncation_marker_in_public_tool_result=any(
                        marker in t.lower() for marker in ('truncated', 'truncation', '截断'))))
        rows.append(dict(tool=item['tool'], public_tool_observations=observations,
                         returned_error_text=[t for t in text if len(t) < 400]))
    return rows


def main():
    raw(NS / 'inputs/M4_SOURCE_REGION_CONSUMPTION_001_PLAN.md')
    raw(NS / 'inputs/PROMPT.txt')
    raw(NS / 'scoring/SCORE_METHOD.md')
    rubric = read(NS / 'scoring/RUBRIC.json')
    sealed = read(NS / 'ANSWERS_SEALED.json')
    all_decisions = decisions()
    cases = []
    public_event_files = {'S1':'f000158_events.jsonl', 'S2':'f000198_events.jsonl', 'S3':'f000235_events.jsonl'}
    for case in ('S1','S2','S3'):
        answer_bytes = raw(NS / 'answers' / (case + '.txt'))
        answer = answer_bytes.decode('utf8')
        seal = next(r for r in sealed['answers'] if r['case_id'] == case)
        assert PINS[str(NS / 'answers' / (case+'.txt'))]['sha256'] == seal['sha256']
        assert answer_bytes == raw(RUN / case / 'consumer/PUBLIC_FINAL.txt')
        brief = read(NS / 'inputs' / case / 'ORIGINAL_BRIEF.json')
        response = read(NS / 'inputs' / case / 'ORIGINAL_RESPONSE.json')
        assert json.loads(response['result']['content'][0]['text']) == brief
        value = brief['task_result']['facts']['surface_proximity']['value']
        assert value['distance_m'] == 0.37011719389236364
        assert len(brief['region_ref']['source_triangle_indices']) == 748
        for gid, record in all_decisions[case].items():
            assert record['quote'] in answer, (case,gid,record['quote'])
            start = answer.index(record['quote'])
            record['answer_line'] = answer[:start].count('\n')+1
        refs = {'region_id': brief['region_ref']['region_id'], 'image_ref':brief['visibility']['image_ref']}
        if case != 'S1':
            assert all(ref in answer for ref in refs.values())
        counts = dict(Counter(v['verdict'] for v in all_decisions[case].values()))
        cases.append(dict(case_id=case,accepted=counts.get('pass',0)==9,
            content_status='unrun_protocol_delivery_failure' if case=='S1' else 'failed_content_adoption',
            original_case_denominator_retained=True, counts=counts, citations=refs,
            actual_public_brief_source=dict(distance_m=value['distance_m'],
                reference=brief['task_result']['reference'], nearest_witness=value['nearest_witness'],
                participation_mask=brief['binding']['image_scope']['participation_mask'],
                selected_surface_pixels=brief['visibility']['selected_surface_pixels'],
                visible_triangles=len(brief['visibility']['visible_source_triangle_indices']),
                unseen_triangles=len(brief['visibility']['unseen_source_triangle_indices']),
                complete_visibility_unknown=brief['visibility']['unknown']),
            actual_public_tool_calls=projected_calls(case,public_event_files[case],brief),
            gates=all_decisions[case]))
    totals = Counter()
    for case in cases:
        totals.update(case['counts'])
    result = dict(schema='independent-source-region-consumption-quality-v1',
        phase='blind_before_author_scores',author_scores_read=False,
        author_commit='28cc6fc728c9fb62d46120f3be14b46d673f675a',
        frozen_rubric_timestamp=rubric['frozen_at_utc'],
        manual_semantic_decisions_validated_against_exact_quotes=True,
        original_cases=3,accepted_cases=0,protocol_failed_cases=1,delivered_content_cases=2,
        delivered_content_accepted=0,gates_total=27,counts=dict(totals),cases=cases,
        actual_adoption=dict(distance_and_units='0/2 delivered',original_nearest_witness='0/2 delivered',
            complete_selection_scope='2/2 delivered',zero_selected_pixel_count='2/2 delivered',
            all_748_unseen='2/2 delivered',correct_current_region_and_image_refs='2/2 delivered',
            unsupported_outside_or_inside_inference='0/2 delivered',
            S1_geometry_errors=0),
        unresolved_observability='S2/S3 self-report truncated visibility. Saved public tool results retain full original brief and distance/witness; actual provider/model-visible postprocessing is unmeasured.',
        one_minimal_improvement='Place an explicit compact facts-and-source summary before large source index/mapping arrays, preserving distance+unit+witness pointers+measurement scope+current pixel/display/unknown facts and stable detail references.',
        input_pins=PINS,new_calls=dict(Blender=0,MCP=0,raster=0,encoding=0,model=0,paid=0))
    path = OUT / 'BLIND_SCORES.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(counts=result['counts'],cases=[dict(case_id=c['case_id'],counts=c['counts']) for c in cases],
                         output_sha256=hashlib.sha256(path.read_bytes()).hexdigest()),ensure_ascii=False))


if __name__=='__main__':
    main()
