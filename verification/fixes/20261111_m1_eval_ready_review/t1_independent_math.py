"""Root review: stdlib-only checks of frozen T1 arrays; no producer imports."""
from fractions import Fraction as F
from collections import Counter, defaultdict
from pathlib import Path
import hashlib, json, math, sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m1_task_entry_001_eval')
T = BASE/'tasks/T1'
OUT = Path(__file__).parent
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
spec = read(T/'SPEC.FROZEN.json')
snap = read(T/'run_01/SNAPSHOT.json')
oracle = read(T/'run_01/ORACLE.json')
truth = read(T/'run_01/TRUTH.json')
roundoff = read(T/'run_01/WORLD_ROUNDOFF.json')
files_checked = {}
for freeze in ['SOURCE_FREEZE.json', 'CERTIFICATION_SOURCE_FREEZE.json']:
    for entry in read(T/freeze)['files']:
        assert sha(T/entry['path']) == entry['sha256'], entry['path']
        files_checked[entry['path']] = entry['sha256']
for entry in read(T/'run_01/PREPARATION_RESULT.json')['artifacts']:
    assert sha(T/'run_01'/entry['path']) == entry['sha256'], entry['path']
    files_checked['run_01/'+entry['path']] = entry['sha256']
assert 'T1_oracle_exact_rigid_rotation' in (T/'run_01/03_ORACLE.stderr.txt').read_text()
assert spec['answer_tolerance_m'] == truth['answer_tolerance_m'] == 1e-6
assert read(BASE/'SCORING_CONTRACT.json')['independent_answers']['T1']['answer_tolerance_m'] == 1e-6

def dot(a,b): return sum(x*y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def mv(a,b): return tuple(dot(r,b) for r in a)
def solve(a,b):
    rows = [list(r)+[v] for r,v in zip(a,b)]
    for c in range(3):
        pivot = next(i for i in range(c,3) if rows[i][c])
        rows[c],rows[pivot] = rows[pivot],rows[c]
        d=rows[c][c]; rows[c]=[v/d for v in rows[c]]
        for i in range(3):
            if i != c:
                d=rows[i][c]; rows[i]=[x-d*y for x,y in zip(rows[i],rows[c])]
    return tuple(r[3] for r in rows)
def inside(p,b): return all(F(l)<x<F(u) for x,l,u in zip(p,b['lower'],b['upper']))
def box_d2(a,b): return sum(max(F(0),F(l)-v,F(u)-h)**2 for l,h,u,v in zip(a['lower'],a['upper'],b['lower'],b['upper']))
def endpoint(x,upper):
    v=float(x)
    if (F(v)<x if upper else F(v)>x): v=math.nextafter(v, math.inf if upper else -math.inf)
    return v

S=F(*spec['coordinate_scale_m'])
R=[tuple(map(F,r)) for r in spec['common_rigid_rotation_rows']]
O={r:next(x for x in snap['objects'] if x['name']==name) for r,name in spec['names'].items()}
A=[tuple(map(F,r[:3])) for r in O['target']['matrix_world'][:3]]
assert A != R
assert all(dot(R[i],R[j])==int(i==j) for i in range(3) for j in range(3))
assert dot(A[0],cross(A[1],A[2]))>0
t=tuple(F(r[3]) for r in O['target']['matrix_world'][:3])
results={}; radii={}; rounds={}; shifts={}; matrices={}; origins={}
for role,row in O.items():
    M=[tuple(map(F,r)) for r in row['matrix_world']]
    matrices[role]=M
    assert [r[:3] for r in M[:3]]==A and M[3]==(0,0,0,1)
    assert row['parent'] is None and not row['constraints'] and not row['modifiers'] and not row['animation_data']
    origin=(F(0),)*3 if role=='target' else tuple((F(a)+F(b))/2 for a,b in zip(spec['candidate_boxes'][role]['lower'],spec['candidate_boxes'][role]['upper']))
    origins[role]=origin
    assert tuple(r[3] for r in M[:3])==tuple(x+S*y for x,y in zip(t,mv(R,origin)))
    q=[tuple(F(x)/S+y for x,y in zip(v,origin)) for v in row['vertices_local']]
    assert len(set(q))==len(q)
    edges=Counter(); directed=Counter(); area=defaultdict(F); vol6=F(0); adj=defaultdict(set)
    for face in row['faces']:
        assert len(face)==len(set(face))==3
        a,b,c=[q[i] for i in face]; n=cross(sub(b,a),sub(c,a))
        axis=next(i for i,x in enumerate(n) if x)
        assert sum(bool(x) for x in n)==1
        area[(axis,a[axis],1 if n[axis]>0 else -1)]+=abs(n[axis])/2
        vol6+=dot(a,cross(b,c))
        for x,y in zip(face,face[1:]+face[:1]):
            edges[tuple(sorted((x,y)))]+=1; directed[x,y]+=1; adj[x].add(y); adj[y].add(x)
    assert all(v==2 for v in edges.values())
    assert all(directed[a,b]==directed[b,a]==1 for a,b in edges)
    visited=set(); todo=[0]
    while todo:
        i=todo.pop()
        if i not in visited: visited.add(i); todo.extend(adj[i]-visited)
    assert len(visited)==len(q) and len(q)-len(edges)+len(row['faces'])==2
    boxes=spec['target_solid_rectangular_partition'] if role=='target' else [spec['candidate_boxes'][role]]
    expected_volume=sum(math.prod(F(u)-F(l) for l,u in zip(b['lower'],b['upper'])) for b in boxes)
    assert vol6==6*expected_volume
    # Independent signed planar area accounting: cancel shared box interfaces.
    boxfaces=[]
    for b in boxes:
        for ax in range(3):
            others=[i for i in range(3) if i!=ax]
            for key,sgn in [('lower',-1),('upper',1)]:
                boxfaces.append((ax,F(b[key][ax]),sgn,[(F(b['lower'][i]),F(b['upper'][i])) for i in others]))
    expected_area=defaultdict(F)
    for ax,plane,sgn,bounds in boxfaces:
        value=math.prod(u-l for l,u in bounds)
        for aa,pp,ss,bb in boxfaces:
            if (aa,pp,ss)==(ax,plane,-sgn):
                value-=math.prod(max(F(0), min(u,v)-max(l,k)) for (l,u),(k,v) in zip(bounds,bb))
        expected_area[ax,plane,sgn]+=value
    assert dict(area)=={k:v for k,v in expected_area.items() if v}
    displacement=[]; errors=[]
    for raw in row['vertices_local']:
        v=tuple(map(F,raw)); actual=tuple(dot(M[i][:3],v)+M[i][3] for i in range(3))
        ideal=tuple(dot(R[i],v)+M[i][3] for i in range(3))
        displacement.append(sum(abs(x-y) for x,y in zip(actual,ideal)))
        rounded=tuple(sum(row['matrix_world'][i][j]*raw[j] for j in range(3))+row['matrix_world'][i][3] for i in range(3))
        errors.append(sum(abs(F(x)-y) for x,y in zip(rounded,actual)))
    radii[role]=max(displacement); rounds[role]=max(errors)
    assert radii[role]==F(oracle['mesh_certificates'][role]['surface_Hausdorff_bound_m'])
    assert rounds[role]==F(next(x for x in roundoff['objects'] if x['name']==row['name'])['max_L1_world_roundoff_m'])
    shift=tuple(x/S-y for x,y in zip(solve(A,sub(tuple(r[3] for r in M[:3]),t)),origin))
    shifts[role]=shift
    assert shift==tuple(map(F,oracle['mesh_certificates'][role]['common_target_frame_translation_shift']))
    results[role]={'name':row['name'],'vertices':len(q),'triangles':len(row['faces']),'edges':len(edges),'volume_assembly_units3':str(vol6/6),'oriented_area_assembly_units2':str(sum(area.values())),'radius_m':str(radii[role]),'world_roundoff_m':str(rounds[role]),'shift_assembly':list(map(str,shift))}

intervals={}
for role in ['inner','outer']:
    b=spec['candidate_boxes'][role]
    shifted={k:[F(x)+y for x,y in zip(b[k],shifts[role])] for k in ['lower','upper']}
    assert min(box_d2(a,shifted) for a in spec['target_solid_rectangular_partition'])>0
    expected=spec['expected_facts_in_assembly_units'][role]
    nominal=F(*expected['gap'])*S
    assert min(box_d2(a,b) for a in spec['target_solid_rectangular_partition'])*S*S==nominal*nominal
    v=sub(tuple(map(F,expected['distance_witness_target'])),tuple(map(F,expected['distance_witness_candidate'])))
    assert dot(v,v)*S*S==nominal*nominal
    rad=radii['target']+radii[role]
    actual=(nominal-rad,nominal+rad)
    fact=next(f for f in truth['facts'] if f['name']==spec['names'][role])
    assert actual==tuple(map(F,fact['distance_interval_fraction_m']))
    extra=rounds['target']+rounds[role]
    expanded=[endpoint(actual[0]-extra,False),endpoint(actual[1]+extra,True)]
    wr=next(x for x in roundoff['separated_distance_intervals_with_binary64_world_roundoff'] if x['name']==fact['name'])
    assert expanded==wr['captured_world_distance_interval_m']
    intervals[role]=expanded
assert intervals['outer'][1]<intervals['inner'][0]

penetrating=next(f for f in truth['facts'] if f['relation']=='penetrating')
world=tuple(map(F,penetrating['strict_common_interior_witness_world_m']))
inv_coordinates={}
for role in ['target','penetrating']:
    q=tuple(x/S+y for x,y in zip(solve(A,sub(world,tuple(r[3] for r in matrices[role][:3]))),origins[role]))
    inv_coordinates[role]=q
    assert q==tuple(map(F,penetrating['same_world_point_actual_inverse_assembly_coordinates'][role]))
assert any(inside(inv_coordinates['target'],b) for b in spec['target_solid_rectangular_partition'])
assert inside(inv_coordinates['penetrating'],spec['candidate_boxes']['penetrating'])
assert F(penetrating['strict_interior_world_radius_lower_bound_m'])>0
guard=read(BASE/'ARITHMETIC_GUARD.json')
assert sha(T/'run_01/WORLD_ROUNDOFF.json')==guard['world_roundoff_sha256']
guard_checks=[]
preflight_binding={}
def norm(v):
    return {'unit_scale_m':v['unit_scale_m'],'objects':sorted([{'name':r['name'],'vertices_local':r['vertices_local'],'matrix_world':r['matrix_world'],'faces':r.get('faces',r.get('triangles'))} for r in v['objects']],key=lambda r:r['name'])}
wire_gaps={}
for group in ['N','C','S']:
    folder=BASE/'preflight_02'/('T1_'+group)
    initial=read(folder/'owner/INITIAL.json'); final=read(folder/'owner/FINAL.json')
    assert norm(initial)==norm(final)==norm(snap) and initial==final
    preflight_binding[group]={'initial_sha256':sha(folder/'owner/INITIAL.json'),'final_sha256':sha(folder/'owner/FINAL.json'),'complete_geometry_matches':True,'initial_final_equal':True}
    if group!='N':
        responses=[json.loads(line) for line in (folder/'thin_probe/RX.bin').read_bytes().splitlines()]
        wire=next(r['result'] for r in responses if r.get('id')==5)
        assert not wire['isError']
        value=json.loads(next(c['text'] for c in wire['content'] if c['type']=='text'))
        if group=='S':
            rows=value['candidates']
        else:
            rows=[{'name':value['binding']['objects'][i+1]['name'],**pair['facts'],'separation_gap':pair['separation_gap']} for i,pair in enumerate(value['pairs'])]
        assert [(r['name'],r['closed_solid_relation']['value']) for r in rows]==[('Part_17','penetrating'),('Part_26','separated'),('Part_38','separated')]
        wire_gaps[group]={r['name']:r['separation_gap']['value'] for r in rows}
        assert wire_gaps[group]['Part_17'] is None
        preflight_binding[group]['RX_sha256']=sha(folder/'thin_probe/RX.bin')
for r in guard['checks_of_existing_preflight_responses_no_new_product_calls']:
    assert wire_gaps[r['group']][r['name']]==r['value_m']
    role=next(k for k,v in spec['names'].items() if v==r['name'])
    err=max(abs(r['value_m']-v) for v in intervals[role])
    assert err==r['max_error_against_roundoff_expanded_interval_m'] and err<=r['tolerance_m']==1e-6
    guard_checks.append({'group':r['group'],'name':r['name'],'max_error_m':err})
result={'passed':True,'scope':'Independent stdlib arithmetic/topology/area checks plus source proof review; not a second complete surface solver or producer-oracle replay','python':sys.version,'source_sha256':sha(Path(__file__)),'frozen_file_checks':files_checked,'objects':results,'intervals_m':intervals,'shared_world_witness':list(map(str,world)),'shared_inverse_points':{k:list(map(str,v)) for k,v in inv_coordinates.items()},'arithmetic_guard_recomputed':guard_checks,'preflight_geometry_and_raw_wire_binding':preflight_binding,'old_exact_R_failure_preserved':True,'no_product_Blender_or_model_executed':True,'limitation':'Boundary per-patch overlap proof and interior radius derivation checked in source; aggregate area/topology alone is not claimed as a fresh complete boundary equivalence proof.'}
(OUT/'T1_MATH_RECOMPUTE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({'passed':True,'intervals':intervals,'output_sha256':sha(OUT/'T1_MATH_RECOMPUTE.json')}))
