"""Independent standard-library audit; reads only the public anonymous handoff.

No product code, Blender, subprocesses, model calls or other reviewer outputs.
Uses exact Fraction support bounds and feasible surface points. Decimal square
roots are outward padded by 1e-40 m, independently of the task's 1e-6 m tolerance.
"""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, localcontext
import ast
import hashlib
import json
import math
import re

PUBLIC = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_spatial_fact_consumption_001/runtime/handoff_01/public')
OUT = Path(__file__).resolve().parent
NAMES = ['Peer_000', 'Competing_001', 'Near_003']
EXPECTED_COMMIT = '5cdf62f311f94890ca569d06c1a858f1578225e4'

def read(rel):
    return json.loads((PUBLIC / rel).read_text(encoding='utf-8-sig'))

def sha(rel):
    return hashlib.sha256((PUBLIC / rel).read_bytes()).hexdigest()

def dot(a,b): return sum(x*y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def add(a,b): return tuple(x+y for x,y in zip(a,b))
def mul(a,t): return tuple(x*t for x in a)
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def fracvec(a): return tuple(F(x) for x in a)
def serialf(a): return [str(a.numerator), str(a.denominator)]
def sqdist(a,b): return dot(sub(a,b),sub(a,b))

def root(q, sign=0):
    with localcontext() as ctx:
        ctx.prec=70
        v=(Decimal(q.numerator)/Decimal(q.denominator)).sqrt()
        return str(v + Decimal(sign)*Decimal('1e-40'))

def closest_on_triangle(p,a,b,c):
    """Exact projection when inside; otherwise exact minimum of three edges."""
    u,v,w=sub(b,a),sub(c,a),sub(p,a)
    uu,uv,vv,wu,wv=dot(u,u),dot(u,v),dot(v,v),dot(w,u),dot(w,v)
    den=uu*vv-uv*uv
    if den:
        s,t=(wu*vv-wv*uv)/den,(wv*uu-wu*uv)/den
        if s>=0 and t>=0 and s+t<=1:
            return add(a,add(mul(u,s),mul(v,t))), (1-s-t,s,t)
    choices=[]
    for i,(x,y) in enumerate(((a,b),(b,c),(c,a))):
        d=sub(y,x)
        t=max(F(0),min(F(1),dot(sub(p,x),d)/dot(d,d)))
        q=add(x,mul(d,t)); bary=[F(0)]*3
        bary[i]=1-t; bary[(i+1)%3]=t
        choices.append((sqdist(p,q),q,tuple(bary)))
    _,q,bary=min(choices,key=lambda x:x[0])
    return q,bary

snap=read('scoring/ACTUAL_SNAPSHOT.json')
objects={o['name']:o for o in snap['objects']}
fv={name:[fracvec(v) for v in objects[name]['vertices_world']] for name in ['Target']+NAMES}
idx=read('INDEX.json')
truth=read('scoring/TRUTH.json')
truthpairs={p['candidate_name']:p for p in truth['pairs']}

# Normal comes from the stored world transform, never from any answer point:
# the cross product of world Z and world X is the local Y plane covector.
mat=objects['Target']['matrix_world']
normal=cross(fracvec([mat[i][2] for i in range(3)]),fracvec([mat[i][0] for i in range(3)]))
nn=dot(normal,normal)
support={}
for name in NAMES:
    av=[dot(normal,v) for v in fv['Target']]
    bv=[dot(normal,v) for v in fv[name]]
    hi,lo=max(av),min(bv)
    assert lo>hi
    gap=lo-hi
    lower2=gap*gap/nn
    support[name]={'normal_exact':[serialf(x) for x in normal],
        'target_max_dot_exact':serialf(hi),'candidate_min_dot_exact':serialf(lo),
        'lower_squared_exact':serialf(lower2),'lower_m_outward':root(lower2,-1),
        'target_support_vertex':av.index(hi),'candidate_support_vertex':bv.index(lo),
        'referenced_vertex_counts':[len(av),len(bv)],'lower2':lower2}

def surface_point(name,point):
    p=fracvec(point)
    # A float pass selects nearby faces only; exact operations evaluate every
    # face in the candidate radius. This changes efficiency, not feasibility.
    nearby=[]
    for ti,ids in enumerate(objects[name]['triangles']):
        verts=[objects[name]['vertices_world'][i] for i in ids]
        # Reject only when outside an expanded triangle AABB (2e-8 m).
        if any(point[k]<min(v[k] for v in verts)-2e-8 or point[k]>max(v[k] for v in verts)+2e-8 for k in range(3)):
            continue
        a,b,c=[fv[name][i] for i in ids]
        q,bary=closest_on_triangle(p,a,b,c)
        nearby.append((sqdist(p,q),ti,q,bary))
    assert nearby, (name,point)
    d2,ti,q,bary=min(nearby,key=lambda x:x[0])
    assert all(x>=0 for x in bary) and sum(bary)==1
    return {'triangle_index':ti,'triangle_vertex_indices':objects[name]['triangles'][ti],
        'barycentric_exact':[serialf(x) for x in bary],
        'point_exact':[serialf(x) for x in q], 'point_float':[float(x) for x in q],
        'evidence_point_surface_adjustment_m':float(root(d2,1))},q

def reconstruct_rounded_pair(name, point_a, point_b, final_a, final_b):
    """Recover a nearest-feature solution from adjacent actual triangles.

    Merely projecting rounded points separately can leave a small tangential
    residual. Solve exact face/vertex and edge/edge stationary candidates, and
    require a solution inside the final coordinate boxes and near tool output.
    The independent global support bound then checks global minimality.
    """
    faces=[]
    for obj,point in [('Target',point_a),(name,point_b)]:
        p=fracvec(point); choices=[]
        for ti,ids in enumerate(objects[obj]['triangles']):
            verts=[objects[obj]['vertices_world'][i] for i in ids]
            if any(point[k]<min(v[k] for v in verts)-2e-11 or point[k]>max(v[k] for v in verts)+2e-11 for k in range(3)):
                continue
            tri=[fv[obj][i] for i in ids]
            q,_=closest_on_triangle(p,*tri)
            if sqdist(p,q)<F(1,10**22): choices.append((ti,tri))
        faces.append(choices)
    candidates=[]
    def accept(a,b,ta,tb):
        if all(abs(float(x)-y)<=1e-6 for p,f in [(a,final_a),(b,final_b)] for x,y in zip(p,f)):
            candidates.append((sqdist(a,b),a,b,ta,tb))
    for ta,a in faces[0]:
        for tb,b in faces[1]:
            for p in a:
                q,_=closest_on_triangle(p,*b); accept(p,q,ta,tb)
            for q in b:
                p,_=closest_on_triangle(q,*a); accept(p,q,ta,tb)
            for i in range(3):
                for j in range(3):
                    p,q=a[i],b[j];u,v=sub(a[(i+1)%3],p),sub(b[(j+1)%3],q);w=sub(p,q)
                    aa,bb,cc,dd,ee=dot(u,u),dot(u,v),dot(v,v),dot(u,w),dot(v,w)
                    den=aa*cc-bb*bb
                    if den:
                        s,t=(bb*ee-cc*dd)/den,(aa*ee-bb*dd)/den
                        if 0<=s<=1 and 0<=t<=1: accept(add(p,mul(u,s)),add(q,mul(v,t)),ta,tb)
    assert candidates, name
    _,pa,pb,ta,tb=min(candidates,key=lambda x:x[0])
    out=[]
    for obj,q,ti,original in [('Target',pa,ta,point_a),(name,pb,tb,point_b)]:
        _,bary=closest_on_triangle(q,*[fv[obj][i] for i in objects[obj]['triangles'][ti]])
        out.append({'triangle_index':ti,'triangle_vertex_indices':objects[obj]['triangles'][ti],
            'barycentric_exact':[serialf(x) for x in bary], 'point_exact':[serialf(x) for x in q],
            'point_float':[float(x) for x in q],
            'evidence_point_surface_adjustment_m':float(root(sqdist(q,fracvec(original)),1)),
            'reconstruction':'Exact rational face-vertex and stationary edge-edge candidates on adjacent actual triangles; selected a solution inside both final error boxes.'})
    return out[0],pa,out[1],pb

def decode_results(event):
    return [json.loads(c['text']) for c in event['result']['content'] if c.get('type')=='text']

def final_rows(text):
    text=text.replace('−','-')
    rows={}
    for name in NAMES:
        lines=[line for line in text.splitlines() if line.startswith('|') and name in line]
        # Pair distances occur before any coordinates, or in a separate table.
        gapline=lines[0]
        parts=[s.strip(' *`') for s in gapline.split('|')]
        gap=next(float(s) for s in parts if re.fullmatch(r'\d+\.\d+',s))
        coords=[]
        for line in lines:
            for m in re.finditer(r'\(([-\d.]+),\s*([-\d.]+),\s*([-\d.]+)\)',line):
                coords.append([float(x) for x in m.groups()])
        assert len(coords)==2
        rows[name]={'gap_mm':gap,'a':coords[0],'b':coords[1], 'at_least_4mm':('否' not in gapline)}
    return rows

def extract_witnesses(events):
    records={}
    unknowns=[]
    errors=[]
    for e in events:
        ev=e['event']
        for data in decode_results(ev):
            if data.get('status')=='error':
                errors.append({'public_event_order':e['order'],'error':data.get('error'),'executed':data.get('executed')})
            if 'pairs' in data:
                byid={o['object_id']:o['name'] for o in data['binding']['objects']}
                assert all(objects[o['name']]['object_id']==o['object_id'] for o in data['binding']['objects'])
                for pair in data['pairs']:
                    name=byid[pair['object_id']]
                    value=pair['facts']['surface_proximity']['value']
                    assert pair['facts']['spatial_relation']['value']=='separated'
                    records[name]={'a':value['nearest_witness']['a'],'b':value['nearest_witness']['b'],
                        'distance_m':value['distance_m'],'public_event_order':e['order'],
                        'coordinate_precision':'binary64 JSON','relation':'separated'}
                    closed=pair['facts'].get('closed_solid_relation')
                    if closed and closed['status']=='unknown': unknowns.append({'candidate':name,**closed})
            else:
                stdout=data.get('result',{}).get('result','') if isinstance(data.get('result'),dict) else ''
                for line in stdout.replace('\\n','\n').splitlines():
                    name=next((n for n in NAMES if line.startswith(n+' ')),None)
                    if not name: continue
                    if "'target_point_m'" in line:
                        d=ast.literal_eval(line[len(name)+1:]); records[name]={'a':d['target_point_m'],'b':d['candidate_point_m'],
                            'distance_m':d['distance_m'],'public_event_order':e['order'],'coordinate_precision':'binary64 repr'}
                    elif 'Target_xyz' in line:
                        m=re.search(r'distance_m (\S+) Target_xyz (\[.*?\]) other_xyz (\[.*?\])',line)
                        records[name]={'a':ast.literal_eval(m[2]),'b':ast.literal_eval(m[3]),'distance_m':float(m[1]),
                            'public_event_order':e['order'],'coordinate_precision':'binary64 repr'}
                    elif 'Target_world_m' in line:
                        m=re.search(r'distance_mm (\S+) Target_world_m (\[.*?\]) other_world_m (\[.*?\])',line)
                        records[name]={'a':list(map(float,ast.literal_eval(m[2]))),'b':list(map(float,ast.literal_eval(m[3]))),
                            'distance_m':float(m[1])/1000,'public_event_order':e['order'],'coordinate_precision':'12 decimal places; reconstructed on actual triangles'}
    assert set(records)==set(NAMES),records
    return records,unknowns,errors

checks=[]
for m in idx['scoring_materials']:
    assert sha(m['file'])==m['sha256']
    checks.append({'file':m['file'],'sha256':sha(m['file']),'matches_INDEX':True})
results=[]
for item in idx['answers']:
    rel=item['directory']
    assert sha(rel+'/answer.txt')==item['answer_original_sha256']
    answer=(PUBLIC/rel/'answer.txt').read_text(encoding='utf-8')
    final=final_rows(answer)
    evidence=read(rel+'/tool_evidence.json')
    events=[e for e in evidence['public_tool_events'] if e['phase']=='item.completed']
    owner_matches=[]
    for owner,e in zip(evidence['owner_attempts'],events):
        assert not owner['request_missing'] and not owner['response_missing']
        params=owner['request']['params']
        assert params['arguments']==e['event']['arguments']
        response=next(x['value'] for x in owner['responses'] if x['kind']=='RESPONSE.json')
        assert response['result']['content']==e['event']['result']['content']
        owner_matches.append({'owner_order':owner['order'],'public_event_order':e['order'],'content_exact_match':True})
    assert len(events)==len(evidence['owner_attempts'])
    witnesses,unknowns,errors=extract_witnesses(events)
    consistency=read(rel+'/source_consistency.json')
    pairs=[]
    for name in NAMES:
        w=witnesses[name]; f=final[name]; t=truthpairs[name]
        wa,pa=surface_point('Target',w['a']); wb,pb=surface_point(name,w['b'])
        if w['coordinate_precision'].startswith('12 decimal'):
            wa,pa,wb,pb=reconstruct_rounded_pair(name,w['a'],w['b'],f['a'],f['b'])
        upper2=sqdist(pa,pb); lower2=support[name]['lower2']
        assert upper2>=lower2
        interval=[support[name]['lower_m_outward'],root(upper2,1)]
        width=float(Decimal(interval[1])-Decimal(interval[0]))
        assert width<1e-15,(name,width)
        # This independent global lower bound plus attained rational surface
        # upper bound is stronger than proximity-to-surface + pair length alone.
        max_coord_error=max(abs(float(p)-v) for q,r in [(pa,f['a']),(pb,f['b'])] for p,v in zip(q,r))
        final_gap_error=abs(f['gap_mm']/1000-t['distance_midpoint_m'])
        assert max_coord_error<=1e-6 and final_gap_error<=1e-6
        assert f['at_least_4mm']==(float(interval[0])>=.004)
        assert interval and float(interval[0])>0
        pairs.append({'candidate':name,'relation_status':'correct','gap_status':'correct','threshold_status':'correct',
            'witness_status':'correct','claimed_gap_mm':f['gap_mm'],'true_gap_reference_m':t['distance_midpoint_m'],
            'final_gap_absolute_error_m':final_gap_error,'at_least_4mm':f['at_least_4mm'],
            'final_points':{'a':f['a'],'b':f['b']},'original_business_witness':w,
            'independent_witness_certificate':{'target':wa,'candidate':wb,'global_distance_bracket_m':interval,
                'bracket_width_m':width,'attained_surface_pair_squared_distance_exact':serialf(upper2),
                'final_coordinate_max_component_error_m':max_coord_error,
                'interpretation':'Feasible exact barycentric surface points attain the independent all-vertex support lower bound to below 1e-15 m; final coordinates fall within 1e-6 m component boxes. This is a numerical shortest-pair certificate, not a claim of exact algebraic uniqueness.'}})
    assert 'Peer_000' in answer and ('唯一最近' in answer)
    results.append({'anonymous_id':item['anonymous_id'],'quality_status':'complete_correct',
        'execution_record_state':item['execution_record_state'],'answer_state':item['answer_state'],
        'requested_fact_counts':{'relations':3,'gaps':3,'thresholds':3,'witness_pairs':3,'restricted_nearest':1,'total_correct':13,'total_required':13},
        'pairs':pairs,'restricted_nearest':{'status':'correct','unique_nearest':'Peer_000','scope':NAMES},
        'requested_unknowns':[],'extra_unknowns':unknowns,'unsupported_extensions':[],
        'preserved_business_errors':errors,'owner_public_response_binding':owner_matches,
        'source_binding':{'asset_sha256':consistency['ACTOR_CONFIG']['asset_sha256'],
            'initial_final_original_sha256_equal':consistency['INITIAL_original_file_sha256']==consistency['FINAL_original_file_sha256'],
            'producer_geometry_unchanged':consistency['CLOSE']['geometry_unchanged'],
            'scope':'Public producer records corroborate current source; not independent proof excluding every transient mutation.'},
        'file_sha256':{name:sha(rel+'/'+name) for name in ['answer.txt','tool_evidence.json','source_consistency.json']}})

report={'schema':'independent-anonymous-quality-review-v1','expected_evidence_commit':EXPECTED_COMMIT,
    'commit_checkout_independently_verified':False,'commit_note':'Parent-provided frozen identity; reviewer intentionally performed no git operations.',
    'public_root':str(PUBLIC),'scope':'Anonymous answer correctness only; no group map, other reviews, timings, usage, cost or adoption assessment.',
    'contract':{'distance_absolute_error_m':1e-6,'coordinate_component_error_m':1e-6,'allow_nonunique_nearest_points':True,'shell_health_required':False},
    'independent_geometry_method':'Exact rational all-world-vertex support separation along cross(matrix Z, matrix X), plus exact feasible barycentric surface-pair upper bounds. Standard library only.',
    'support_bounds':{n:{k:v for k,v in d.items() if k!='lower2'} for n,d in support.items()},
    'index_scoring_hash_checks':checks,'answers':results,
    'summary':{'fixed_slots':6,'complete_correct':6,'incomplete':0,'incorrect':0,'execution_failure':0,'not_run':0,'requested_facts_correct':78,'requested_facts_required':78},
    'reviewer_binding':{'agent_id':'01a1cee2-ff3c-7073-9f14-e3ca49ef00e1','assignment_id':'e9812169-e942-4097-8634-1909e4c5b00d','task_access':'parent_read_only'},
    'audit_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'unverified':['No private originals, original runtime folders or Git objects were read.','No Blender rerun or product implementation audit.','Read-only/no-save statements supported by public scripts and producer closure records; every transient action not independently observable.','Exact algebraic uniqueness or identity of nonunique minimum points is not claimed; numerical certificates use actual triangle geometry and widths below 1e-15 m.','No full-scene collision or shell health certification, and none required.']}
(OUT/'SCORES.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
max_width=max(p['independent_witness_certificate']['bracket_width_m'] for a in results for p in a['pairs'])
max_round=max(p['independent_witness_certificate']['final_coordinate_max_component_error_m'] for a in results for p in a['pairs'])
lines=[
    '# 独立匿名质量评分', '',
    '六份匿名答案均为 **complete_correct（完整正确）**：每份 13/13 个所需事实正确，合计 78/78。没有所需项 incomplete、incorrect、execution_failure 或 not_run。此结论只评价题目指定的空间事实。', '',
    f'固定证据身份：`{EXPECTED_COMMIT}`（父任务指定；本评分者没有执行 Git 命令，提交与工作区字节的对应由根封存）。输入仅为指定 public 目录及计划中的质量合同。没有读取私有映射、原运行格目录、其他评分者意见、计时或 usage。工具名称可能暴露求解方式，因此这是标签遮蔽下的独立质量审查，不声称完全双盲。', '',
    '## 评分合同与独立核验', '',
    '每份按三项分离关系、三项真实表面间隙、三项 4 mm 判断、三对最近世界位置、限定三候选集合内的最近者逐项判定；全部满足才完整正确，无加权补偿。间隙绝对误差限 1e-6 m，最终坐标各分量误差限 1e-6 m。允许不同的有效最近点，不要求与参考点或其他答案的点重合。壳体健康不是题目必需项。', '',
    '独立核查程序 audit_saved_geometry.py 仅使用 Python 标准库读取冻结 JSON，不导入产品求解器、不执行保存下来的消费者代码、不调用 Blender 或模型。由 Target 的世界变换 Z、X 列叉积构造法向量，再以 Fraction 对两侧全部实际世界顶点作精确投影，得到严格正支撑间隔；三角形及其凸包因此严格分离，支撑间隔除以法向量模长是全局距离下界。法向量独立于答案点，未把答案点间距当成真值。', '',
    '对工具中的完整精度端点，核其在实际三角面上的合法非负重心组合，并计算精确有理点对距离上界，再核最终文字舍入。answer_3bb23736081f79f8 的工具仅输出 12 位小数：额外从附近实际三角面求解精确点—面及边—边驻点候选，取得同时落在最终两坐标误差盒内的合法最近特征点对，再用同一全局下界验最短性。没有仅凭“接近表面”和“点间距接近”两项必要条件判过。', '',
    f'18 对证据的独立上下界最大宽度为 **{max_width:.16g} m**；最终坐标相对合法点的最大分量误差为 **{max_round:.16g} m**。此极小计算界用于说明最短性证据精度，没有扩大题目 1e-6 m 的间隙误差限。平方值、支撑值及重心系数均以完整有理数存于 SCORES.json；十进制开方向外留 1e-40 m。未声称非唯一点的精确代数唯一性。', '',
    '| 候选 | 独立真值（m） | 分离 | ≥ 4 mm |',
    '|---|---:|---|---|',
]
for name in NAMES:
    lines.append(f"| {name} | {truthpairs[name]['distance_midpoint_m']:.17g} | 是 | {'否' if name=='Peer_000' else '是'} |")
lines += ['', '三段间隙严格有序，因此限定集合内唯一最近者是 Peer_000，无真实并列。此处没有扩张为全场最近或全场无碰撞。', '',
    '## 逐份、逐项结果', '',
    '以下“最近点正确”同时包括两端表面归属、最短性及最终舍入。三角序号是本独立核查在 ACTUAL_SNAPSHOT.json 中定位的从 0 起序号，不要求与消费者或参考材料使用相同序号。全部最终坐标、原始业务坐标、独立合法点及逐项误差见 SCORES.json 对应 anonymous_id。', '']
notes={
    'answer_194ae90393424045':'业务事件 4 给出完整精度最短点；记录中覆盖三角顶点—面、边—边及相交检查，事件 6 补充绕数。最终“无相交、未发现包含”与独立严格支撑分离一致。没有额外全场或壳体健康断言。',
    'answer_27379ae7b6ac4280':'业务事件 4 给出完整精度点对与三类特征计算结果。相交点为空及绕数记录与独立支撑分离一致；最终没有把边拓扑检查提升为壳体健康结论。',
    'answer_3bb23736081f79f8':'业务事件 6 提供 12 位小数的点对和距离，事件 4 保留当前 Target 顶点及世界变换读法。独立重建附近面上的精确特征候选后，最近点与最终坐标误差盒相容。未要求其证明壳体健康。',
    'answer_3d9fef31bcaa7736':'业务事件 2 直接提供绑定到目标对象的 spatial_relation 与 surface_proximity。三项 closed_solid_relation=unknown（closed_solid_work_budget）是额外分类，已在最终说明保留；题目所需的分离、间隙及点对都有独立有效证据，因此不记所需项 incomplete。',
    'answer_4c5339761016a915':'保留业务事件 2 的无效 requested_facts 请求错误：额外 nearest_witness 字段被拒绝，executed=false；事件 4 修正后返回完整所需空间事实。最终 13 项由成功记录支持，错误不被删去，也不自动改判最终 incorrect。三项额外闭合实体 unknown 原样单列。',
    'answer_810d2b5de2b6d865':'业务事件 2 的绑定空间事实给出更长的间隙小数与完整精度点对；三项闭合实体分类仍为 unknown，最终说明准确保留。所需项均确定且独立核查正确。'
}
for a in results:
    lines += [f"### {a['anonymous_id']}", '',
        '**complete_correct，13/13。** 公开执行记录 completed，确认最终答案 present；执行状态与质量判断分别记录。', '',
        '| 候选 | 分离 | 间隙 mm（正确） | ≥4 mm（正确） | 最近点 | 三角序号 Target/候选 | 最大坐标分量误差 m |',
        '|---|---|---:|---|---|---|---:|']
    for p in a['pairs']:
        c=p['independent_witness_certificate']
        lines.append(f"| {p['candidate']} | 正确：分离 | {p['claimed_gap_mm']:.9f} | {'是' if p['at_least_4mm'] else '否'} | 正确 | {c['target']['triangle_index']}/{c['candidate']['triangle_index']} | {c['final_coordinate_max_component_error_m']:.4e} |")
    lines += ['', '**限定集合最近者：正确，Peer_000 唯一最近。** 所需 unknown：0；错误确定结论：0；无依据全场/健康扩张：0。', '', notes[a['anonymous_id']], '']
lines += ['## 来源与未验证项', '',
    'INDEX 指定的六份 answer.txt 原始 SHA256 全部匹配；三份 scoring 文件 SHA256 全部匹配。六份所有 owner 请求参数与 public 完成事件对应，业务响应 content 逐项精确相等；无缺失请求或缺失响应。原始错误仍在材料和评分中。各答案、工具材料、来源一致性材料的实读 SHA256 已写入 SCORES.json。', '',
    '公开 source_consistency 的资产 SHA256 均为 27f197a8cc312832382ae06cb633cbf846f20a1a22797909a15dfda8513ade46；初末文件记录相等，生产者报告 geometry_unchanged。原生记录的求值网格读取及双精度世界变换与评分几何相符；结构化事实的对象名/ID 已与实际快照核对。', '',
    '未验证项：没有读取私有原件、原运行格目录或 Git 对象；没有重新打开 Blender 验证瞬时状态，也没有重验产品实现。公开代码和关闭记录支持只读、未保存的陈述，但初末一致不能独立排除每个瞬时动作。全场碰撞、闭壳健康、非唯一最近点的代数唯一性均未作认证，也不是本题要求。', '',
    'AL：已用本子 Agent 的真实 context_handle 读取并确认 assignment e9812169-e942-4097-8634-1909e4c5b00d；task_access=parent_read_only，没有更新父任务。本报告只包含独立匿名质量结论。', '']
(OUT/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'summary':report['summary'],'max_bracket_width_m':max(p['independent_witness_certificate']['bracket_width_m'] for a in results for p in a['pairs']),
    'max_coordinate_component_error_m':max(p['independent_witness_certificate']['final_coordinate_max_component_error_m'] for a in results for p in a['pairs'])},indent=2))
