"""Root final-answer numerical check. Reads the anonymous public pack only."""
from fractions import Fraction as Q
from pathlib import Path
import hashlib
import json
import re

PUB=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_grooved_rail_consumption_001/runtime/handoff_01/public')
OUT=Path(__file__).resolve().parent
def decode(v):
    if isinstance(v,dict):
        if set(v)=={'numerator','denominator'}: return Q(int(v['numerator']),int(v['denominator']))
        return {k:decode(x) for k,x in v.items()}
    if isinstance(v,list): return [decode(x) for x in v]
    return v

# Only geometric fields are selected; no consumer map, timing or usage is read.
raw=json.loads((PUB/'scoring/TRUTH.json').read_bytes())
truth=decode(raw['pair_results'])
point=re.compile(r'\(?\s*([-+]?\d+\.\d+)\s*,\s*([-+]?\d+\.\d+)\s*,\s*([-+]?\d+\.\d+)\s*\)?')
cases=[]
for folder in sorted(PUB.glob('answer_*')):
    data=(folder/'answer.txt').read_bytes(); final=data.decode('utf-8-sig')
    relation=bool(re.search(r'三对均(?:已)?分离', final))
    nearest='Part_B' in final and '唯一最近' in final
    rows={}
    for name in ('Part_A','Part_B','Part_C'):
        claimed_distance=None; threshold=None; coordinates=None
        for line in final.splitlines():
            if name not in line or '|' not in line: continue
            cells=[x.strip().strip('*').strip('`') for x in line.split('|') if x.strip()]
            numerical=[x for x in cells if re.fullmatch(r'\d+\.\d+',x)]
            if numerical:
                claimed_distance=Q(numerical[0])/1000
                threshold=cells[-1]
            triples=point.findall(line)
            if len(triples)==2: coordinates=[[Q(x) for x in p] for p in triples]
        assert claimed_distance is not None and coordinates is not None and threshold in ('是','否'), folder.name
        t=truth[name]; interval=t['sqrt_interval']
        lo=Q(interval['lower_decimal_m']); hi=Q(interval['upper_decimal_m'])
        distance_error=max(abs(claimed_distance-lo),abs(claimed_distance-hi))
        witness=t['selected_feature_witness']
        true_points=[witness['point_target'],witness['point_candidate']]
        errors=[abs(p[j]-q[j]) for p,q in zip(coordinates,true_points) for j in range(3)]
        # Existence of this independently certified globally nearest pair within
        # both coordinate error boxes suffices; alternatives would be accepted.
        expected_threshold=t['exact_squared_distance_m2']>=Q(1,250)**2
        rows[name]={'relation_correct':relation and t['solid_relation']=='separated',
                    'distance_correct':distance_error<=Q(1,10**6),
                    'threshold_correct':(threshold=='是')==expected_threshold,
                    'witness_rounding_correct':max(errors)<=Q(1,10**6),
                    'max_distance_error_m':float(distance_error),
                    'max_coordinate_component_error_m':float(max(errors)),
                    'certified_witness_source':'scoring/TRUTH.json pair_results selected_feature_witness',
                    'evidence_scope':'Final-coordinate box contains a previously independently certified actual global minimizer; business evidence audited separately.'}
    facts=sum(sum(r[k] for k in ('relation_correct','distance_correct','threshold_correct','witness_rounding_correct')) for r in rows.values())+nearest
    cases.append({'answer_id':folder.name,'answer_sha256':hashlib.sha256(data).hexdigest(),'facts_numerically_correct':facts,'facts_required':13,'nearest_correct':nearest,'pairs':rows})
assert len(cases)==6
result={'public_truth_sha256':hashlib.sha256((PUB/'scoring/TRUTH.json').read_bytes()).hexdigest(),'cases':cases,
        'facts_numerically_correct':sum(c['facts_numerically_correct'] for c in cases),'facts_required':78,
        'scope':'Final text numerics and compatibility with qualified exact witnesses only; independent business-evidence and source audits decide full quality.',
        'new_product_Blender_consumer_API_runs':0}
(OUT/'ROOT_FACT_CHECK.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'cases':len(cases),'facts_correct':result['facts_numerically_correct'],'facts_required':78}))
