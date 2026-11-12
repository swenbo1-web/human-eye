"""Root quality checks on public saved records; no product or consumer execution."""
import ast
from decimal import Decimal, localcontext
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import re

PUBLIC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/runtime/handoff_01/public')
OUT = Path(__file__).resolve().parent
NAMES = ('Peer_000', 'Competing_001', 'Near_003')

def read(name):
    return json.loads((PUBLIC / name).read_bytes())

def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))

def dot(a, b):
    return sum(x*y for x, y in zip(a, b))

def addscaled(a, b, t):
    return tuple(x+t*y for x, y in zip(a, b))

def segment(p, a, b):
    e = sub(b, a)
    t = min(1., max(0., dot(sub(p,a),e)/dot(e,e))) if dot(e,e) else 0.
    return addscaled(a,e,t)

def surface_membership(p, obj):
    best = None
    for ti, ids in enumerate(obj['triangles']):
        a,b,c = [obj['vertices_world'][i] for i in ids]
        u,v,w = sub(b,a),sub(c,a),sub(p,a)
        uu,uv,vv,wu,wv = dot(u,u),dot(u,v),dot(v,v),dot(w,u),dot(w,v)
        det = uu*vv-uv*uv
        trials = [(segment(p,a,b), 'edge_ab'),(segment(p,b,c), 'edge_bc'),(segment(p,c,a), 'edge_ca')]
        if det > 0:
            s,t = (wu*vv-wv*uv)/det,(wv*uu-wu*uv)/det
            if s>=0 and t>=0 and s+t<=1:
                trials.append((addscaled(addscaled(a,u,s),v,t),'interior'))
        for q,feature in trials:
            d2 = dot(sub(p,q),sub(p,q))
            if best is None or d2<best['distance2_m']:
                best={'distance2_m':d2,'triangle':ti,'feature':feature,'closest':q}
    return best

def decode_results(attempt):
    for response in attempt['responses']:
        for item in response['value'].get('result',{}).get('content',[]):
            if 'text' in item:
                yield json.loads(item['text'])

def extract_witnesses(evidence):
    found = {}
    for attempt in evidence['owner_attempts']:
        for result in decode_results(attempt):
            if result.get('result_kind')=='task_query':
                idnames={v['object_id']:v['name'] for v in result['binding']['objects']}
                for pair in result['pairs']:
                    fact=pair['facts']['surface_proximity']['value']
                    found[idnames[pair['object_id']]]=(fact['nearest_witness']['a'],fact['nearest_witness']['b'])
            stdout=result.get('result',{}).get('result','')
            if not isinstance(stdout,str):continue
            for line in stdout.splitlines():
                for name in NAMES:
                    if not line.startswith(name+' '):continue
                    if "'target_point_m'" in line:
                        value=ast.literal_eval(line[len(name)+1:])
                        found[name]=(value['target_point_m'],value['candidate_point_m'])
                    elif 'Target_xyz' in line:
                        a,b=re.search(r'Target_xyz (\[.*?\]) other_xyz (\[.*?\])',line).groups()
                        found[name]=(ast.literal_eval(a),ast.literal_eval(b))
                    elif 'Target_world_m' in line:
                        a,b=re.search(r'Target_world_m (\[.*?\]) other_world_m (\[.*?\])',line).groups()
                        found[name]=(list(map(float,ast.literal_eval(a))),list(map(float,ast.literal_eval(b))))
    assert set(found)==set(NAMES)
    return found

snapshot=read('scoring/ACTUAL_SNAPSHOT.json')
objects={o['name']:o for o in snapshot['objects']}
truth=read('scoring/TRUTH.json')
checks=[]
def check(label, okay):
    checks.append({'label':label,'passed':bool(okay)})
    if not okay:raise AssertionError(label)

lower={}
for pair in truth['pairs']:
    name=pair['candidate_name']
    n=tuple(F(*x) for x in pair['support_normal'])
    projections=[]
    for object_name in ('Target',name):
        obj=objects[object_name]
        ids=sorted({i for tri in obj['triangles'] for i in tri})
        projections.append([dot(n,tuple(F(x) for x in obj['vertices_world'][i])) for i in ids])
    gap=min(projections[1])-max(projections[0])
    check(name+': strict referenced-vertex separation',gap>0)
    check(name+': oracle support independently reproduced',gap==F(*pair['support_gap']))
    norm2=dot(n,n)
    with localcontext() as ctx:
        ctx.prec=80
        decimal_gap=Decimal(gap.numerator)/Decimal(gap.denominator)
        decimal_norm2=Decimal(norm2.numerator)/Decimal(norm2.denominator)
        lower[name]=float(decimal_gap/decimal_norm2.sqrt())
    check(name+': independent support distance agrees',abs(lower[name]-pair['distance_midpoint_m'])<1e-12)

scores=[]
for row in read('INDEX.json')['answers']:
    ident=row['anonymous_id']
    final=(PUBLIC/ident/'answer.txt').read_text(encoding='utf8')
    check(ident+': final raw hash',hashlib.sha256((PUBLIC/ident/'answer.txt').read_bytes()).hexdigest()==row['answer_original_sha256'])
    check(ident+': confirmed final',row['answer_state']=='present' and not row['unconfirmed_public_messages'])
    ev=read(ident+'/tool_evidence.json')
    source=read(ident+'/source_consistency.json')
    check(ident+': recorded original state equality',source['FINAL_original_file_sha256']==source['INITIAL_original_file_sha256'])
    check(ident+': same asset declared',source['ACTOR_CONFIG']['asset_sha256']=='27f197a8cc312832382ae06cb633cbf846f20a1a22797909a15dfda8513ade46')
    pts=extract_witnesses(ev)
    parsed=[]
    for name in NAMES:
        lines=[x for x in final.splitlines() if x.startswith('|') and name in x]
        gaps=[]
        coords=[]
        for line in lines:
            for field in line.split('|'):
                if re.fullmatch(r'\s*[0-9]+\.[0-9]+\s*',field):gaps.append(float(field)/1000)
            coords.extend([tuple(float(y.strip()) for y in x.replace('−','-').split(',')) for x in re.findall(r'\(([-+−0-9.eE ,]+)\)',line)])
        check(ident+name+': one numeric gap',len(gaps)==1)
        check(ident+name+': distance contract',abs(gaps[0]-lower[name])<=1e-6)
        check(ident+name+': two point triplets',len(coords)==2 and all(len(p)==3 for p in coords))
        memberships=[surface_membership(p,objects[o]) for p,o in zip(pts[name],('Target',name))]
        check(ident+name+': actual triangle membership',all(m['distance2_m']<1e-18 for m in memberships))
        norm=math.dist(*pts[name])
        check(ident+name+': attained globally bounded distance',abs(norm-lower[name])<1e-9)
        rounding=max(abs(x-y) for p,q in zip(coords,pts[name]) for x,y in zip(p,q))
        check(ident+name+': final coordinate rounding',rounding<=1e-6)
        threshold_lines=[x for x in lines if ('否' in x or '是' in x)]
        check(ident+name+': threshold decision',len(threshold_lines)==1 and ('否' in threshold_lines[0] if name=='Peer_000' else '是' in threshold_lines[0]))
        parsed.append({'candidate':name,'gap_m':gaps[0],'independent_support_distance_m':lower[name],'full_precision_or_12dp_witness':pts[name],'final_witness':coords,'surface_membership':memberships,'witness_distance_m':norm,'rounding_max_component_m':rounding,'relation':'separated','minimum_4mm':name!='Peer_000'})
    check(ident+': nearest explicit and scoped','Peer_000' in final and '唯一最近' in final and '三个候选' in final)
    scores.append({'anonymous_id':ident,'status':'complete_correct','relation_count':3,'distance_count':3,'threshold_count':3,'witness_pair_count':3,'nearest_count':1,'requested_unknown':0,'unsupported_extensions':[], 'pairs':parsed,'semantic_review':'Root manually read the final and business computation. Separation and scoped nearest are explicit, requested facts complete. Shell-classification unknown where present is not promoted to completed shell validation.'})

result={'schema':'root-anonymous-quality-v1','evidence_commit':'5cdf62f311f94890ca569d06c1a858f1578225e4','read_scope':'public packet only, fixed root plan; no private map, usage or cost','scores':scores,'complete_correct':len(scores),'slots':6,'checks':checks,'numerical_scope':'Fraction all-referenced-vertex strict separating support, Decimal80 support distance, independent float point-to-triangle membership and attained-distance checks; below-display-error numeric verification, not a new exact arithmetic geometry solver. Printed 12-decimal witnesses preserved as printed. Final semantic quality reviewed manually.','not_run':['Blender','consumer code','product solver','model/API','private originals mapping and cost audit'],'public_files':[{'path':str(p.relative_to(PUBLIC)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(PUBLIC.rglob('*')) if p.is_file()]}
(OUT/'SCORES.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'complete_correct':len(scores),'slots':6,'checks':len(checks),'all_passed':all(v['passed'] for v in checks)},ensure_ascii=False))
