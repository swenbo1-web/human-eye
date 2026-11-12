"""Root review: frozen bytes, independent saved geometry, directed pure kernels.

No author test/verifier/oracle code, installed product, Blender or API is run.
Only two fixed product modules are compiled into a private in-memory package.
"""
from pathlib import Path
from fractions import Fraction as F
from types import SimpleNamespace, ModuleType
import copy, hashlib, json, math, random, subprocess, sys, time, traceback

ROOT=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
OUT=Path(__file__).resolve().parent
COMMIT='743a484f16f1dadff8dedcf1abad8d0a14398d17'
PRODUCT='3beb3f809674658b086e50af194adaa16e226111'
B='verification/m3_pair_scalability_001/'
CHECKS=[]; INPUTS={}; BLOBS={}; RESULTS={}

def ck(label,ok,detail=None):
    CHECKS.append(dict(check=label,passed=bool(ok),detail=detail))
    if not ok: raise AssertionError(label)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def blob(path):
    if path not in BLOBS:
        b=subprocess.check_output(['git','show',COMMIT+':'+path],cwd=ROOT)
        ck('Git_disk:'+path,b==(ROOT/path).read_bytes())
        INPUTS[path]=dict(sha256=sha(b),bytes=len(b));BLOBS[path]=b
    return BLOBS[path]
def read(p):return json.loads(blob(p))
def eq(label,a,b):ck(label,enc(a)==enc(b))
def v(p):return tuple(F(x) for x in p)
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def mul(a,t):return tuple(x*t for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def sq(a,b):return dot(sub(a,b),sub(a,b))
def rational(a):return F(a[0],a[1])
def fracout(a):return [a.numerator,a.denominator]
def clamp(t):return max(F(0),min(F(1),t))

def segment_point(p,a,b):
    d=sub(b,a);q=dot(d,d);return add(a,mul(d,clamp(dot(sub(p,a),d)/q))) if q else a
def bary(p,t):
    a,b,c=t;e,f,w=sub(b,a),sub(c,a),sub(p,a)
    ee,ef,ff=dot(e,e),dot(e,f),dot(f,f);det=ee*ff-ef*ef
    if not det:return None
    u=(dot(w,e)*ff-dot(w,f)*ef)/det;z=(dot(w,f)*ee-dot(w,e)*ef)/det
    return 1-u-z,u,z
def point_triangle(p,t):
    candidates=[segment_point(p,t[i],t[(i+1)%3]) for i in range(3)]
    weights=bary(p,t)
    if weights is not None and min(weights)>=0:
        candidates.append(tuple(sum(weights[k]*t[k][j] for k in range(3)) for j in range(3)))
    return min(((sq(p,q),q) for q in candidates),key=lambda item:item[0])
def edge_edge(a,b,c,d):
    u,w,z=sub(b,a),sub(d,c),sub(a,c)
    uu,uw,ww=dot(u,u),dot(u,w),dot(w,w);det=uu*ww-uw*uw
    candidates=[(a,segment_point(a,c,d)),(b,segment_point(b,c,d)),(segment_point(c,a,b),c),(segment_point(d,a,b),d)]
    if det:
        s=(uw*dot(w,z)-ww*dot(u,z))/det;t=(uu*dot(w,z)-uw*dot(u,z))/det
        if 0<=s<=1 and 0<=t<=1:candidates.append((add(a,mul(u,s)),add(c,mul(w,t))))
    return min(((sq(p,q),p,q) for p,q in candidates),key=lambda item:item[0])
def piercing(a,b,t):
    n=cross(sub(t[1],t[0]),sub(t[2],t[0]));da=dot(n,sub(a,t[0]));db=dot(n,sub(b,t[0]))
    if da==db:return None
    u=da/(da-db)
    if not 0<=u<=1:return None
    p=add(a,mul(sub(b,a),u));weights=bary(p,t)
    return p if weights is not None and min(weights)>=0 else None
def tri_distance(a,b):
    choices=[]
    for p in a:
        d,q=point_triangle(p,b);choices.append((d,p,q))
    for p in b:
        d,q=point_triangle(p,a);choices.append((d,q,p))
    for i in range(3):
        for j in range(3):choices.append(edge_edge(a[i],a[(i+1)%3],b[j],b[(j+1)%3]))
        for p in (piercing(a[i],a[(i+1)%3],b),piercing(b[i],b[(i+1)%3],a)):
            if p is not None:choices.append((F(0),p,p))
    return min(choices,key=lambda item:item[0])
def triangles(mesh):return [tuple(v(mesh.vertices[i]) for i in face) for face in mesh.faces]
def minimum(left,right):
    best=None;pair=None
    for i,a in enumerate(triangles(left)):
        for j,b in enumerate(triangles(right)):
            answer=tri_distance(a,b)
            if best is None or answer[0]<best[0]:best,pair=answer,(i,j)
    return best,pair
def key_fraction(key):
    n,d,e=key;q=F(n,d);return q*(2**e) if e>=0 else q/F(2**(-e))
def member(point,raw):
    p=v(point);points=list(map(v,raw['vertices_world']));best=None
    for i,face in enumerate(raw['triangles']):
        d,q=point_triangle(p,[points[j] for j in face])
        if best is None or d<best[0]:best=(d,i,q)
    ck('public_membership:'+raw['name'],best[0]<=F(1,10**9)**2)
    return dict(triangle=best[1],squared_position_error=fracout(best[0]),surface_point=[fracout(x) for x in best[2]])

def saved_evidence():
    snap=read(B+'entry/run_01/ACTUAL_SNAPSHOT.json')
    old=read('verification/spatial_task_qualification_001/entry/run_01/ACTUAL_SNAPSHOT.json')
    eq('actual_full14_equal_prior_qualified_snapshot',snap,old)
    wire=read(B+'entry/run_01/native/WIRE/001/RESPONSE.bin')
    eq('actual_snapshot_from_raw_QA_wire',snap,json.loads(wire['result']['result']))
    rows={r['name']:r for r in snap['objects']}
    oracle=read('verification/spatial_task_qualification_001/oracle/formal_replay_01/ORACLE.json')
    certs={p['candidate_name']:p for p in oracle['pairs']}
    for number,names in [('003',{'Target','Peer_000','Competing_001','Near_003'}),('004',{'Control_A','Control_B'})]:
        wire=read(B+'entry/run_01/native/WIRE/'+number+'/RESPONSE.bin')
        packet=json.loads(wire['result']['result'].split('HUMAN_EYE_BLENDER_MCP:',1)[1])['result']
        resources={(r['id'],r['revision']):r for r in packet['resources']};cap=packet['capture']
        eq('captured_names:'+number,sorted(m['name'] for m in cap['meshes']),sorted(names))
        ck('captured_units:'+number,cap['unit']=='m' and cap['coordinate_frame']=='world')
        for m in cap['meshes']:
            raw=rows[m['name']];ref=m['_scene_resource'];r=resources[(ref['id'],ref['revision'])]
            eq('actual_local:'+m['name'],r['vertices_local'],raw['vertices_local'])
            eq('actual_faces:'+m['name'],r['faces'],raw['triangles'])
            eq('actual_matrix:'+m['name'],ref['matrix'],raw['matrix_world'])
            eq('actual_scale:'+m['name'],ref['scale'],snap['scale_length'])
    response=read(B+'entry/run_01/product/006/RX.bin');body=json.loads(response['result']['content'][0]['text'])
    eq('raw_public_parsed_body',body,read(B+'entry/run_01/assembly_task_RESULT.json')['body'])
    ck('public_result_is_partial',body['status']=='partial')
    ck('no_false_complete_nearest',body['summary']['nearest_separated_complete'] is False and body['summary']['nearest_separated_ids'] is None)
    by_id={r['object_id']:r for r in rows.values()};output=[]
    for pair in body['pairs']:
        target=rows['Target'];other=by_id[pair['object_id']];name=other['name'];c=certs[name]
        fact=pair['facts']['surface_proximity'];answer=fact['value'];points=answer['nearest_witness']
        ck('public_surface_measured:'+name,fact['status']=='measured' and fact['witness_status']=='measured')
        ck('public_closed_unknown:'+name,pair['facts']['closed_solid_relation']['reason']=='closed_solid_work_budget')
        ck('public_gap_unknown:'+name,pair['separation_gap']['status']=='unknown')
        n=tuple(rational(x) for x in c['support_normal']);n2=dot(n,n)
        gap=min(dot(n,v(p)) for p in other['vertices_world'])-max(dot(n,v(p)) for p in target['vertices_world'])
        ck('support_positive:'+name,gap>0 and gap==rational(c['support_gap']))
        lower2=gap*gap/n2;w=c['witness'];q=[]
        for raw,side in [(target,'a'),(other,'b')]:
            tri=[v(raw['vertices_world'][i]) for i in raw['triangles'][w['triangle_'+side]]]
            weights=[rational(x) for x in w['barycentric_'+side]]
            ck('oracle_bary:'+name+side,min(weights)>=0 and sum(weights)==1)
            q.append(tuple(sum(weights[k]*tri[k][j] for k in range(3)) for j in range(3)))
        upper2=sq(*q);ck('oracle_sandwich:'+name,lower2<=upper2)
        distance=F(answer['distance_m']);tol=F(1,10**6)
        ck('public_global_distance_interval:'+name,max(F(0),distance-tol)**2<=lower2 and upper2<=(distance+tol)**2)
        a,b=points['a'],points['b'];ma=member(a,target);mb=member(b,other)
        exact_pair=sq(v(a),v(b));pubtol=F(1,10**9)
        ck('public_point_distance_consistency:'+name,max(F(0),distance-pubtol)**2<=exact_pair<=(distance+pubtol)**2)
        vecdir=sub(v(b),v(a));direction=points['direction_a_to_b']
        ck('public_direction_finite:'+name,all(math.isfinite(x) for x in direction))
        ck('public_direction_matches:'+name,math.dist(direction,[float(x/distance) for x in vecdir])<1e-10)
        output.append(dict(name=name,distance_m=float(distance),point_a=ma,point_b=mb,
                           global_lower_squared=fracout(lower2),global_upper_squared=fracout(upper2),
                           closed='unknown',separation_gap='unknown'))
    control=json.loads(read(B+'entry/run_01/product/007/RX.bin')['result']['content'][0]['text'])
    proximity=control['pairs'][0]['facts']['surface_proximity']['value'];w=proximity['nearest_witness']
    ck('control_exact_distance',proximity['distance_m']==1 and sq(v(w['a']),v(w['b']))==1)
    controls=[member(w[s],rows[n]) for s,n in [('a','Control_A'),('b','Control_B')]]
    RESULTS['public_evidence']=dict(assembly=output,control=controls,actual_objects=len(rows))

def load_modules():
    pkg=ModuleType('_root_m3_review');pkg.__path__=[];sys.modules[pkg.__name__]=pkg
    for name in ['surface_proximity','surface_geometry']:
        path='human_eye_plugin/'+name+'.py';source=blob(path)
        product_source=subprocess.check_output(['git','show',PRODUCT+':'+path],cwd=ROOT)
        ck('product_commit_byte_match:'+name,source==product_source)
        mod=ModuleType(pkg.__name__+'.'+name);mod.__file__=COMMIT+':'+path;mod.__package__=pkg.__name__
        sys.modules[mod.__name__]=mod;setattr(pkg,name,mod)
        exec(compile(source,mod.__file__,'exec',dont_inherit=True),mod.__dict__)
    return pkg.surface_proximity,pkg.surface_geometry

def mesh_from_triangles(ts):
    return SimpleNamespace(vertices=[tuple(map(float,p)) for t in ts for p in t],faces=[(3*i,3*i+1,3*i+2) for i in range(len(ts))])
def rows(z=0,reverse=False):
    ts=[[(3*i,0,z),(3*i+2,0,z),(3*i,2,z)] for i in range(17)]
    return list(reversed(ts)) if reverse else ts
def change(ts,fn):return [[fn(*p) for p in tri] for tri in ts]
def cases():
    a=rows();b=change(rows(1),lambda x,y,z:(x+.25,y+.25,z))
    yield 'parallel_face_interior_17x17',a,b
    rb=change(rows(1,True),lambda x,y,z:(x+.25,y+.25,z))
    rb[0]=[(x,y,math.nextafter(z,math.inf)) for x,y,z in rb[0]]
    yield 'reversed_equal_and_nextafter',a,rb
    tx=lambda x,y,z:(2**40+x+y, -2**40-x+y, 2**39+2*z)
    yield 'large_common_translation_rotated_nonuniform',change(a,tx),change(b,tx)
    yield 'dyadic_tiny_gap',a,change(b,lambda x,y,z:(x,y,2**-40))
    yield 'degenerate_points_to_segments',[[(3*i,0,0)]*3 for i in range(17)], [[(3*i,-1,2),(3*i,1,2),(3*i,0,2)] for i in range(17)]
    cross_a=rows();cross_b=rows(10)
    cross_b[11]=[(.5,.5,-1),(.5,.5,1),(1,.5,1)]
    yield 'transverse_intersection_not_vertex',cross_a,cross_b
    # Three predetermined integer random clouds, fixed seed and size before execution.
    r=random.Random(53117)
    for index in range(3):
        cloud_a=[[(r.randrange(-4,5),r.randrange(-4,5),r.randrange(-4,5)) for _ in range(3)] for _ in range(17)]
        cloud_b=[[(r.randrange(-4,5)+10,r.randrange(-4,5)+index,r.randrange(-4,5)) for _ in range(3)] for _ in range(17)]
        yield 'fixed_integer_cloud_'+str(index),cloud_a,cloud_b

def directed_kernels(exact,closed):
    outputs=[]
    for name,a,b in cases():
        left,right=mesh_from_triangles(a),mesh_from_triangles(b)
        # Independent full feature enumeration, not old leaf code or candidate _nearest_linear.
        truth,pair=minimum(left,right)
        result=exact.measure_surface_proximity(left,right,lambda s:None,retain_exact_rank=True)
        ck(name+':measurement',result['measurement_valid'],result.get('reason'))
        ck(name+':tree_used',result['work']['tree_builds']==2 and result['work']['node_pair_visits']>0)
        ck(name+':exact_distance_matches_independent_enumeration',key_fraction(result['_exact_distance_sq'])==truth[0])
        # Same exact triangle pair tie order as lexicographic enumeration, where exposed by original world witness.
        if result['witness_status']=='measured':
            for side,m in [('a',left),('b',right)]:
                member(result['point_'+side+'_world'],dict(name=name+':'+side,vertices_world=m.vertices,triangles=m.faces))
        outputs.append(dict(name=name,triangles=[17,17],truth_squared=fracout(truth[0]),first_minimizing_pair=list(pair),result=result))
    RESULTS['directed_kernel_cases']=outputs
    # Exact comparator boundary: strict greater only, including maximum allowed factor widths.
    comparisons=[]
    for bits in [1,31,1023,4095]:
        normal=1<<bits;best=(1<<bits,1);edge=1<<bits
        for delta in [-1,0,1]:
            gap=edge+delta
            if gap<=0:continue
            for sign in [-1,1]:
                ds=(sign*gap,)*3
                expected=F(gap*gap,normal)>F(*best)
                got=exact._plane_exceeds_best(ds,normal,best)
                ck('plane_strict:'+str((bits,delta,sign)),got==expected)
                comparisons.append(dict(bits=bits,delta=delta,sign=sign,expected=expected,actual=got))
    ck('cross_plane_not_pruned',not exact._plane_exceeds_best((-1,1,2),1,(0,1)))
    ck('zero_plane_not_pruned',not exact._plane_exceeds_best((1,1,1),0,(0,1)))
    RESULTS['plane_bound_comparisons']=comparisons
    # Identical displayed binary64 distance can still have unequal exact rank.
    ranking=exact._rank_surface_results({'equal_a':dict(measurement_valid=True,_exact_distance_sq=[1,1,0]),
        'equal_b':dict(measurement_valid=True,_exact_distance_sq=[3,3,0]),
        'strictly_further':dict(measurement_valid=True,_exact_distance_sq=[(1<<106)+1,1,-106])},lambda s:None)
    eq('exact_rank_ties_not_display_ties',ranking['ordered_object_id_groups'],[['equal_a','equal_b'],['strictly_further']])
    RESULTS['rank']=ranking

def prepared_binding(exact,closed):
    # Prepare through the actual closed path, which may reject open-shell topology;
    # its query-local world tree is still usable for valid surface-only distance.
    left=mesh_from_triangles(rows());right=mesh_from_triangles(rows(1))
    holder={};relation=closed.classify_closed_solids(left,right,lambda s:None,prepared_holder=holder)
    shared=exact.measure_surface_proximity(left,right,lambda s:None,_prepared_pair=holder['pair'],_prepared_trees=holder['trees'])
    ck('same_pair_shared_tree_measured',shared['measurement_valid'] and shared['distance_m']==1 and shared['work']['shared_trees'])
    other=mesh_from_triangles(rows(2));foreign=exact.measure_surface_proximity(left,other,lambda s:None,_prepared_pair=holder['pair'],_prepared_trees=holder['trees'])
    ck('different_pair_rebuilt',foreign['measurement_valid'] and foreign['distance_m']==2 and not foreign['work']['shared_trees'])
    reversed_pair=exact.measure_surface_proximity(right,left,lambda s:None,_prepared_pair=holder['pair'],_prepared_trees=holder['trees'])
    ck('reverse_pair_rebuilt',reversed_pair['measurement_valid'] and reversed_pair['distance_m']==1 and not reversed_pair['work']['shared_trees'])
    # Matching new pair plus foreign tree is rejected by pair/triangle identity.
    own={};closed.classify_closed_solids(left,other,lambda s:None,prepared_holder=own)
    wrong_tree=exact.measure_surface_proximity(left,other,lambda s:None,_prepared_pair=own['pair'],_prepared_trees=holder['trees'])
    ck('foreign_tree_ignored',wrong_tree['measurement_valid'] and wrong_tree['distance_m']==2 and not wrong_tree['work']['shared_trees'])
    RESULTS['prepare_binding']=dict(closed_reason=relation.get('reason'),shared=shared,foreign=foreign,reversed=reversed_pair,wrong_tree=wrong_tree)
    # Cancellation and total budget must remain distinguishable from complete results.
    for stop in ['surface_proximity_surface_bvh_build','surface_proximity_node_pair_visits','surface_proximity_narrow_phase_pairs']:
        marker=RuntimeError('root_review_cancel:'+stop)
        def cp(stage):
            if stage==stop:raise marker
        try:exact.measure_surface_proximity(left,right,cp)
        except RuntimeError as error:ck('cancel_propagation:'+stop,error is marker)
        else:ck('cancel_not_seen:'+stop,False)
    b=exact._Work(lambda s:None);b.counts['work_units']=exact.MAX_WORK_UNITS
    try:b.tick('node_pair_visits')
    except exact._DomainError as e:ck('total_budget_boundary',str(e)=='surface_work_budget')
    else:ck('total_budget_boundary',False)
    b=exact._Work(lambda s:None);b.counts['narrow_phase_pairs']=exact.MAX_NARROW_PHASE_PAIRS
    try:b.narrow_pair()
    except exact._DomainError as e:ck('narrow_budget_boundary',str(e)=='surface_pair_budget')
    else:ck('narrow_budget_boundary',False)

if __name__=='__main__':
    started=time.perf_counter_ns()
    try:
        saved_evidence();exact,closed=load_modules();directed_kernels(exact,closed);prepared_binding(exact,closed)
        RESULTS.update(passed=True,fixed_commit=COMMIT,product_commit=PRODUCT)
    except BaseException as e:
        RESULTS.update(passed=False,error=type(e).__name__+': '+str(e),traceback=traceback.format_exc())
    RESULTS.update(checks=len(CHECKS),failures=sum(not c['passed'] for c in CHECKS),elapsed_ns=time.perf_counter_ns()-started,
      new_Blender_calls=0,new_model_calls=0,product_modules_loaded_in_memory=2,
      exclusions=['no author verifier/oracle/test execution','no G508 kernel performance rerun','no closed node certificate audit'])
    for name,value in [('RESULTS.json',RESULTS),('CHECKS.json',CHECKS),('INPUTS.json',INPUTS)]:
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:RESULTS[k] for k in ('passed','checks','failures','elapsed_ns')}))
    if not RESULTS['passed']:print(RESULTS['traceback']);sys.exit(1)
