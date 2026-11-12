"""Finalize this reviewer's manual semantic decisions with public evidence links."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib
import json
import re
import sys

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import review_answers as review


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


MANUAL = {
    'answer_11a4c8ec025d6a16': '逐份读完。明确包括隐藏网格，276=71+41+164，unknown/deferred为0；明确0仅指三角表面公共点，不判断实体关系。中间业务输出70行后在后续输出修正为71，不把中间少行结果替代final。',
    'answer_3990a6a4bf660eee': '逐份读完。28正距离与43零距离分表含义明确，A分别与每个B配对；24对象/978三角及276全对复核有业务记录；最小非匹配Obj_002–Obj_008≈2.250 mm与精确真值一致。执行failed保持。',
    'answer_4a4a77418ce1424c': '逐份读完。71逐行表格、六位毫米、全部场景含隐藏网格及71/41/164覆盖说明齐全；不将0细分为实体接触/穿入，也不宣称包含关系。',
    'answer_4c4c0fa03baa1ee8': '逐份读完。71逐行表格、六位毫米，含等于阈值、unknown/deferred为0，说明是当前三角网格浮点几何而非无限精度解析曲面；没有错误实体关系推断。执行failed保持。',
    'answer_89dab9e90194dcbf': '逐份读完。43零组表和28正表含义明确；978三角、112三角距离候选与164包围界排除有业务支持；顶点面/边边/相交与有限坐标说明与公开计算及检查对应。',
    'answer_9297e204cfb1d7f7': '逐份读完。无序端点顺序不同不构成重复；71/41/164与0未知覆盖完整；原始值分类、六位毫米展示分开，没有把surface距离当实体分类。',
    'answer_9ee63c86af8ff66d': '逐份读完。顶部明确完整覆盖，71/205及164/41一致；含隐藏网格和0未知项；六位毫米及当前场景绑定说明清楚，没有其他确定性错误。',
    'answer_bb2c246d257d7867': '逐份读完。每个A对应B:距离的合并表语义明确，三位毫米满足要求；全276复核、43零/28正、最小非匹配约2.250 mm有业务及真值支持；0交点声明由triangular-intersection输出与精确零距离支持。',
    'answer_dccb27e1bc47c94f': '逐份读完。71行无序对象对、六位毫米、阈值含等号，完整覆盖及无未知；明确距离零不代表特定实体关系，未发现额外确定性错误。',
}


def main():
    numeric = json.loads((OUT/'NUMERIC_RESULTS.json').read_bytes())
    source = json.loads((OUT/'BUSINESS_EVIDENCE_REVIEW.json').read_bytes())
    truth = review.obj(review.PUBLIC/'scoring/TRUTH.json')
    all_pairs = {tuple(sorted([p['object_a'], p['object_b']])): review.qvalue(p) for p in truth['pairs']}
    matches = {pair:q for pair,q in all_pairs.items() if q <= F(0.002)**2}
    finalized=[]
    for original in numeric['answers']:
        row = {k:v for k,v in original.items() if k != 'parsed_rows'}
        aid = row['anonymous_id']
        evidence = review.obj(review.PUBLIC/aid/'tool_evidence.json')
        event_results = [e['event'].get('result') for e in evidence['public_tool_events'] if e['event'].get('result') is not None]
        supports=[]
        for attempt, summary in zip(evidence['owner_attempts'],source[aid]):
            owner_results=[r['value'].get('result') for r in attempt.get('responses',[]) if isinstance(r.get('value'),dict)]
            delivery_matches=any(encoded(a.get('content'))==encoded(b.get('content'))
                                 for a in owner_results for b in event_results
                                 if isinstance(a,dict) and isinstance(b,dict) and a.get('content') is not None)
            for fact in summary['scan_business_facts']:
                pairs={tuple(sorted([a,b])): F(d)*1000 for a,b,d in fact['pairs']}
                valid=(set(pairs)==set(matches) and all(review.in_tolerance(d,matches[p]) for p,d in pairs.items()))
                supports.append({'order':attempt['order'],'type':'structured_surface_business_facts',
                                 'complete_matching_set_supported':valid,'public_event_same_content':delivery_matches,
                                 'coverage_and_delivery':{'coverage':fact['coverage'],'delivery':fact['delivery']}})
            for stdout in summary['native_business_stdout']:
                lines=re.findall(r'^(Obj_\d{3})\s+(Obj_\d{3})\s+('+review.NUM+r')(?:\s|$)',stdout,re.M)
                if not lines: continue
                parsed=[(tuple(sorted([a,b])),F(d)) for a,b,d in lines]
                qualifying=[(p,d) for p,d in parsed if d<=2]
                keys=[p for p,d in qualifying]
                valid=(set(keys)==set(matches) and len(keys)==len(set(keys))==71 and all(review.in_tolerance(d,matches[p]) for p,d in qualifying))
                supports.append({'order':attempt['order'],'type':'explicit_business_numeric_list',
                                 'complete_matching_set_supported':valid,'public_event_same_content':delivery_matches,
                                 'qualifying_rows_in_this_record':len(qualifying)})
        has_support=any(s['complete_matching_set_supported'] and s['public_event_same_content'] for s in supports)
        assert has_support, aid
        assert row['pair_distance_presentation_pass'], aid
        assert all(v is True for v in row['producer_source_records'].values()), aid
        row.update(manual_semantic_review_pending=False, manual_review=MANUAL[aid],
            completeness_claim='explicit_complete_and_supported',
            unit_and_precision='mm; all_nonzero_at_least_3_decimal_places',
            surface_solid_confusion=False, unsupported_extra_deterministic_errors=[],
            content_classification='complete_correct',
            final_classification='complete_correct' if row['execution_state']=='completed' and row['consumer_valid_completion'] else 'execution_failure',
            public_evidence_support=supports,
            provenance_limit='Business evidence supports facts and observed output, not unique causal attribution or provider-rendered input completeness; initial/final equality cannot exclude every transient operation.')
        finalized.append(row)
    result={'review_kind':'independent anonymous final semantic and numeric review',
            'public_materials_only':True,'cost_group_other_reviewer_materials_opened':False,
            'fixed_denominator':9,'final_content_counts':dict(Counter(r['content_classification'] for r in finalized)),
            'execution_retaining_counts':dict(Counter(r['final_classification'] for r in finalized)),
            'answers':finalized,'extra_claim_reference':numeric['extra_claim_reference']}
    (OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    hashes=json.loads((OUT/'INPUT_HASHES.json').read_bytes())
    for filename in ('review_answers.py','finalize_review.py'):
        p=OUT/filename; data=p.read_bytes(); hashes[str(p)]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    (OUT/'INPUT_HASHES.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('answers','extra_claim_reference')},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
