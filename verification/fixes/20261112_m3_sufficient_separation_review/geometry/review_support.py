"""Independent support-proof review; frozen bytes and two pure in-memory kernels.
No author verifier/test/oracle, Blender, installed product, model or API executes.
"""
from pathlib import Path
from fractions import Fraction as F
from types import ModuleType, SimpleNamespace
import hashlib, json, math, struct, subprocess, sys, time, traceback

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path(__file__).resolve().parent
COMMIT='189ecdb84185d96c3ed0d75ca268bc16d6d4999b'
PRODUCT='e836e03f4b3821f869c72ac3e50df5204f28b50f'
B='verification/m3_sufficient_separation_001/'
CHECKS=[];INPUTS={};CACHE={};RESULTS={}
def ck(name,condition):
    CHECKS.append(dict(check=name,passed=bool(condition)))
    if not condition:raise AssertionError(name)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def blob(path):
    if path not in CACHE:
        b=subprocess.check_output(['git','show',COMMIT+':'+path],cwd=ROOT)
        ck('Git_disk:'+path,b==(ROOT/path).read_bytes());CACHE[path]=b
        INPUTS[path]=dict(sha256=sha(b),bytes=len(b))
    return CACHE[path]
def read(path):return json.loads(blob(path))
def eq(label,a,b):ck(label,enc(a)==enc(b))
def vec(p):return tuple(F(x) for x in p)
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def square(a,b):return dot(sub(a,b),sub(a,b))
def rat(x):return F(x[0],x[1])
def asrat(x):return [x.numerator,x.denominator]
def refs(mesh):return sorted({i for face in mesh.faces for i in face})
def point_triangle(p,t):
    a,b,c=t;e,f,w=sub(b,a),sub(c,a),sub(p,a)
    ee,ef,ff=dot(e,e),dot(e,f),dot(f,f);det=ee*ff-ef*ef;choices=[]
    if det:
        u=(dot(w,e)*ff-dot(w,f)*ef)/det;v=(dot(w,f)*ee-dot(w,e)*ef)/det
        if min(1-u-v,u,v)>=0:
            choices.append(tuple(a[j]+u*e[j]+v*f[j] for j in range(3)))
    for i,j in [(0,1),(1,2),(2,0)]:
        d=sub(t[j],t[i]);length=dot(d,d)
        s=max(F(0),min(F(1),dot(sub(p,t[i]),d)/length)) if length else F(0)
        choices.append(tuple(t[i][k]+s*d[k] for k in range(3)))
    return min(((square(p,q),q) for q in choices),key=lambda item:item[0])
def member(name,p,mesh):
    p=vec(p);vertices=list(map(vec,mesh.vertices));best=None
    for i,face in enumerate(mesh.faces):
        d,q=point_triangle(p,[vertices[j] for j in face])
        if best is None or d<best[0]:best=(d,i,q)
    ck(name+':point_on_actual_surface',best[0]<=F(1,10**9)**2)
    return dict(triangle=best[1],squared_error=asrat(best[0]))
def mesh(raw):return SimpleNamespace(vertices=[tuple(p) for p in raw['vertices_world']],faces=[tuple(t) for t in raw['triangles']])
def primitive(points):
    d=[F(b)-F(a) for a,b in zip(*points)];den=math.lcm(*(x.denominator for x in d))
    integers=[x.numerator*(den//x.denominator) for x in d];g=math.gcd(*integers)
    return [x//g for x in integers] if g else None
def verify_proof(name,evidence,left,right,points):
    direction=primitive(points);eq(name+':public_direction_exact',evidence['primitive_direction'],direction)
    ck(name+':nonzero_direction',direction is not None)
    origin=list(map(rat,evidence['origin']));factor=evidence['factor']
    ck(name+':positive_dyadic_frame',type(factor) is int and factor>0 and factor&(factor-1)==0)
    # Independent frame: exactly match the fixed coordinate conversion, not the certificate's extrema.
    first=left.vertices[refs(left)[0]];eq(name+':frame_origin',[asrat(F(float(x))) for x in first],evidence['origin'])
    expected_factor=max((F(float(x))-o).denominator for m in (left,right) for i in refs(m) for x,o in zip(m.vertices[i],origin))
    ck(name+':frame_factor',factor==expected_factor)
    projections=[];world_projections=[]
    for m in (left,right):
        values={};world={}
        for i in refs(m):
            p=tuple(F(float(x)) for x in m.vertices[i]);q=tuple((x-o)*factor for x,o in zip(p,origin))
            ck(name+':exact_integer_coordinate:'+str(len(projections))+':'+str(i),all(x.denominator==1 for x in q))
            values[i]=dot(direction,q);world[i]=dot(direction,p)
        projections.append(values);world_projections.append(world)
    a,b=max(projections[0].values()),min(projections[1].values())
    ck(name+':strict_integer_support',b>a)
    ck(name+':strict_source_support',min(world_projections[1].values())>max(world_projections[0].values()))
    ck(name+':extrema_and_indices',a==evidence['left_max'] and b==evidence['right_min'] and
       projections[0][evidence['left_vertex_index']]==a and projections[1][evidence['right_vertex_index']]==b)
    eq(name+':full_reference_counts',evidence['referenced_counts'],[len(refs(left)),len(refs(right))])
    return dict(referenced_counts=evidence['referenced_counts'],strict_support_gap_integer=int(b-a),
                source_projection_gap=asrat(min(world_projections[1].values())-max(world_projections[0].values())))

def saved():
    snap=read(B+'entry/run_01/ACTUAL_SNAPSHOT.json')
    eq('actual_snapshot_matches_prior_qualified',snap,read('verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json'))
    eq('actual_from_native_raw',snap,json.loads(read(B+'entry/run_01/native/WIRE/001/RESPONSE.bin')['result']['result']))
    byname={r['name']:r for r in snap['objects']};byid={r['object_id']:r for r in snap['objects']}
    packet=json.loads(read(B+'entry/run_01/native/WIRE/003/RESPONSE.bin')['result']['result'].split('HUMAN_EYE_BLENDER_MCP:',1)[1])['result']
    resources={(r['id'],r['revision']):r for r in packet['resources']}
    for m in packet['capture']['meshes']:
        ref=m['_scene_resource'];r=resources[(ref['id'],ref['revision'])];actual=byname[m['name']]
        eq('raw_capture_vertices:'+m['name'],r['vertices_local'],actual['vertices_local'])
        eq('raw_capture_triangles:'+m['name'],r['faces'],actual['triangles'])
        eq('raw_capture_matrix:'+m['name'],ref['matrix'],actual['matrix_world'])
        eq('raw_capture_scale:'+m['name'],ref['scale'],snap['scale_length'])
    response=read(B+'entry/run_01/product/006/RX.bin');body=json.loads(response['result']['content'][0]['text'])
    eq('parsed_response',body,read(B+'entry/run_01/spatial_assembly_task_RESULT.json')['body'])
    ck('explicit_v2_observed',body['schema_version']=='task-query-set-v2' and body['status']=='observed' and body['relation_fact']=='spatial_relation')
    oracle=read('verification/spatial_task_qualification_001/oracle/formal_replay_01/ORACLE.json')
    certificates={r['candidate_name']:r for r in oracle['pairs']};results=[]
    for pair in body['pairs']:
        raw=byid[pair['object_id']];name=raw['name'];left=mesh(byname['Target']);right=mesh(raw)
        relation=pair['facts']['spatial_relation'];surface=pair['facts']['surface_proximity'];answer=surface['value'];w=answer['nearest_witness'];points=(w['a'],w['b'])
        ck(name+':separated_by_strict_support',relation['value']=='separated' and relation['certificate']=='strict_all_referenced_vertex_support' and
           relation['geometry_scope']=='referenced_triangle_unions_and_their_vertex_convex_hulls')
        proof=verify_proof(name,relation['support_evidence'],left,right,points)
        ma=member(name+':a',points[0],left);mb=member(name+':b',points[1],right)
        d=F(answer['distance_m']);sqdist=square(vec(points[0]),vec(points[1]));eps=F(1,10**9)
        ck(name+':public_point_distance',max(F(0),d-eps)**2<=sqdist<=(d+eps)**2)
        c=certificates[name];n=list(map(rat,c['support_normal']))
        gap=min(dot(n,vec(p)) for p in right.vertices)-max(dot(n,vec(p)) for p in left.vertices);lower=gap*gap/dot(n,n)
        oldw=c['witness'];p=[]
        for m,side in [(left,'a'),(right,'b')]:
            tri=[vec(m.vertices[i]) for i in m.faces[oldw['triangle_'+side]]];weights=list(map(rat,oldw['barycentric_'+side]))
            ck(name+':oracle_bary:'+side,min(weights)>=0 and sum(weights)==1)
            p.append(tuple(sum(weights[i]*tri[i][j] for i in range(3)) for j in range(3)))
        upper=square(*p);ck(name+':global_minimum_sandwich',lower<=upper and max(F(0),d-F(1,10**6))**2<=lower and upper<=(d+F(1,10**6))**2)
        decision='satisfies' if lower>=F(1,250)**2 else 'violates' if upper<F(1,250)**2 else 'unknown'
        ck(name+':4mm_answer',decision==('violates' if name=='Peer_000' else 'satisfies'))
        ck(name+':gap_not_projection',pair['separation_gap']['value']==answer['distance_m'])
        results.append(dict(name=name,distance=float(d),proof=proof,point_a=ma,point_b=mb,minimum4mm=decision))
    ck('complete_nearest_Peer',body['summary']['nearest_separated_complete'] and body['summary']['nearest_separated_ids']==[byname['Peer_000']['object_id']])
    legacy=json.loads(read(B+'entry/run_01/product/007/RX.bin')['result']['content'][0]['text'])
    ck('legacy_v1_still_partial',legacy['schema_version']=='task-query-set-v1' and legacy['status']=='partial' and not legacy['summary']['nearest_separated_complete'])
    ck('legacy_closed_still_unknown',all(p['facts']['closed_solid_relation']['reason']=='closed_solid_work_budget' and p['separation_gap']['status']=='unknown' for p in legacy['pairs']))
    RESULTS['actual_MCP']=results

def load():
    pkg=ModuleType('_root_support_review');pkg.__path__=[];sys.modules[pkg.__name__]=pkg
    for name in ['surface_proximity','surface_geometry']:
        path='human_eye_plugin/'+name+'.py';source=blob(path)
        ck('product_commit_match:'+name,source==subprocess.check_output(['git','show',PRODUCT+':'+path],cwd=ROOT))
        m=ModuleType(pkg.__name__+'.'+name);m.__file__=COMMIT+':'+path;m.__package__=pkg.__name__
        sys.modules[m.__name__]=m;setattr(pkg,name,m);exec(compile(source,m.__file__,'exec',dont_inherit=True),m.__dict__)
    return pkg.surface_proximity,pkg.surface_geometry
def tri(z=0):return SimpleNamespace(vertices=[(0.,0.,float(z)),(2.,0.,float(z)),(0.,2.,float(z))],faces=[(0,1,2)])
def box(center,size=1):
    x,y,z=center;s=size
    verts=[(x+a*s,y+b*s,z+c*s) for a,b,c in [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),(1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)]]
    return SimpleNamespace(vertices=verts,faces=[(0,2,3),(0,3,1),(4,5,7),(4,7,6),(0,1,5),(0,5,4),(2,6,7),(2,7,3),(0,4,6),(0,6,2),(1,3,7),(1,7,5)])
def invoke(exact,name,left,right,support=None,relation=None):
    metrics={};holder={};value=exact.measure_spatial_relation(left,right,lambda s:None,diagnostics=metrics,prepared_holder=holder,retain_exact_rank=True)
    if support is not None:ck(name+':support_path',(metrics['closed_solid_pair_count']==0 and value['spatial'].get('certificate')=='strict_all_referenced_vertex_support')==support)
    if relation is not None:ck(name+':relation',value['spatial'].get('relation')==relation)
    if support:
        s=value['surface'];proof=verify_proof(name,value['spatial']['support_evidence'],left,right,(s['point_a_world'],s['point_b_world']))
        count=len(refs(left))+len(refs(right));work=metrics['support_work']
        ck(name+':actual_complete_count',work['support_source_vertices']==work['support_vertex_dots']==count and work['work_units_after']-work['work_units_before']==2*count+3)
    else:proof=None
    RESULTS.setdefault('small_cases',[]).append(dict(name=name,bundle=value,metrics=metrics,independent_proof=proof))
    return value,metrics,holder
def directed(exact,closed):
    invoke(exact,'binary64_positive_2^-25',tri(1),tri(1+2**-25),True,'separated')
    fp32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
    invoke(exact,'binary32_same_values_collapse_to_contact',tri(fp32(1)),tri(fp32(1+2**-25)),False,None)
    invoke(exact,'binary32_own_positive_spacing',tri(fp32(1)),tri(fp32(1+2**-22)),True,'separated')
    invoke(exact,'large_represented_spacing',tri(2**50),tri(2**50+.25),True,'separated')
    invoke(exact,'large_unrepresented_spacing_collapses',tri(2**50),tri(2**50+1e-9),False,None)
    invoke(exact,'dyadic_positive_2^-200',tri(0),tri(2**-200),True,'separated')
    collapsed=SimpleNamespace(vertices=[(0.,0.,0.),(2.,0.,0.),(1.,0.,0.)],faces=[(0,1,2)])
    shifted=SimpleNamespace(vertices=[(x,y,z+1) for x,y,z in collapsed.vertices],faces=collapsed.faces)
    value,metrics,holder=invoke(exact,'collapsed_middle_source_index',collapsed,shifted,True,'separated')
    ck('collapsed_index_retained',all(len(x)==3 and 2 in x for x in holder['coordinates']))
    remote=tri();remote.vertices.extend([(100.,0.,2.),(101.,0.,2.),(100.,1.,2.)]);remote.faces.append((3,4,5))
    value,metrics,_=invoke(exact,'remote_referenced_refutes_positive_local_gap',remote,tri(1),False,None)
    ck('remote_all9_checked',metrics['support_work']['support_source_vertices']==9 and metrics['closed_solid_pair_count']==1 and not value['spatial']['measurement_valid'])
    orphan=tri();orphan.vertices.append((100.,0.,2.))
    invoke(exact,'unreferenced_orphan_outside_explicit_scope',orphan,tri(1),True,'separated')
    invoke(exact,'reversed_signed_direction',tri(1),tri(),True,'separated')
    invoke(exact,'containment_positive_distance_requires_closed',box((0,0,0),2),box((0,0,0),.5),False,'penetrating')
    invoke(exact,'touching_requires_closed',box((0,0,0)),box((2,0,0)),False,'touching')
    # Seed remaining budget through the actual checkpoint/holder. Limits stay unchanged.
    holder={};metrics={};seeded=False
    def exhaust(stage):
        nonlocal seeded
        if stage=='surface_proximity_support_source_vertices' and not seeded:
            holder['work'].counts['work_units']=exact.MAX_WORK_UNITS;seeded=True
    value=exact.measure_spatial_relation(tri(),tri(1),exhaust,diagnostics=metrics,prepared_holder=holder)
    ck('support_budget_does_not_fallback',seeded and value['budget_stopped'] and not value['spatial']['measurement_valid'] and metrics['closed_solid_pair_count']==0 and value['surface']['measurement_valid'])
    RESULTS['budget_injection']=dict(bundle=value,metrics=metrics,injected='seed existing work counter to original cap at first support-source checkpoint')
    for stage in ['surface_proximity_support_direction_components','surface_proximity_support_vertex_dots','closed_solid_admission']:
        marker=TimeoutError('original deadline at '+stage);metrics={}
        def cp(value):
            if value==stage:raise marker
        try:exact.measure_spatial_relation(box((0,0,0),2) if stage.startswith('closed') else tri(),box((0,0,0),.5) if stage.startswith('closed') else tri(1),cp,diagnostics=metrics)
        except TimeoutError as e:ck('deadline_propagates:'+stage,e is marker)
        else:ck('deadline_missing:'+stage,False)
    # Optional numeric guard fault, explicitly not a naturally occurring geometry sample.
    fn=exact._referenced_support_evidence
    def numeric_failure(*args):raise exact._DomainError('surface_exact_bit_budget')
    exact._referenced_support_evidence=numeric_failure
    try:value,metrics,_=invoke(exact,'injected_optional_bit_guard',box((0,0,0)),box((3,0,0)),False,'separated')
    finally:exact._referenced_support_evidence=fn
    ck('numeric_guard_single_fallback',metrics['closed_solid_pair_count']==1 and metrics['closed_solid_work']['prepared_pair_reused'])
    # Invalid or rounded-identical public proposals must not fabricate nonzero directions.
    work=exact._Work(lambda s:None,None)
    for name,proposal in [('identical',{'measurement_valid':True,'witness_status':'measured','point_a_world':[2**50,0,0],'point_b_world':[2**50+1e-9,0,0]}),
                          ('nonfinite',{'measurement_valid':True,'witness_status':'measured','point_a_world':[0,0,0],'point_b_world':[math.inf,0,0]})]:
        direction,reason=exact._public_support_direction(proposal,work);ck('public_proposal_rejected:'+name,direction is None)
    # Direction derived from rounded public witnesses, but arbitrary-direction proof remains sound.
    proposal={'measurement_valid':True,'witness_status':'measured','point_a_world':[0.1,0.2,0.3],'point_b_world':[0.10000000000000002,0.25,0.4]}
    direction,_=exact._public_support_direction(proposal,work)
    eq('exact_difference_before_integer_reduction',list(direction),primitive((proposal['point_a_world'],proposal['point_b_world'])))

if __name__=='__main__':
    start=time.perf_counter_ns()
    try:saved();exact,closed=load();directed(exact,closed);RESULTS.update(passed=True)
    except BaseException as e:RESULTS.update(passed=False,error=type(e).__name__+': '+str(e),traceback=traceback.format_exc())
    RESULTS.update(fixed_commit=COMMIT,product_commit=PRODUCT,checks=len(CHECKS),failures=sum(not c['passed'] for c in CHECKS),elapsed_ns=time.perf_counter_ns()-start,
                   new_Blender_calls=0,new_model_calls=0,new_performance_samples=0)
    for name,obj in [('RESULTS.json',RESULTS),('CHECKS.json',CHECKS),('INPUTS.json',INPUTS)]:
        (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:RESULTS[k] for k in ('passed','checks','failures','elapsed_ns')}))
    if not RESULTS['passed']:print(RESULTS['traceback']);sys.exit(1)
