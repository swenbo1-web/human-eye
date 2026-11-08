"""Finite exact predicates on frozen raw vertices and host tessellation.

Standalone Blender helper. Contacts are geometry facts, never damage labels.
All predicates use the exact dyadic input affine map, not renderer coordinates.
"""
from fractions import Fraction as Q
import hashlib,heapq,json,math,time

PROTOCOL='surface-geometry-v1'
LIMITS=dict(vertices=4096,triangles=4096,pair_tests=16384,results=128,bits=4096)


def require(value,reason):
    if not value:raise ValueError('surface_'+reason)


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def mul(a,t):return tuple(x*t for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def normal(t):return cross(sub(t[1],t[0]),sub(t[2],t[0]))
def orient(a,b,c,axes):
    x,y=axes;return (b[x]-a[x])*(c[y]-a[y])-(b[y]-a[y])*(c[x]-a[x])


def clip_coplanar(a,b,n,budget):
    """Closed convex intersection; retains points/segments as well as area."""
    drop=max(range(3),key=lambda k:abs(n[k]));axes=tuple(k for k in range(3) if k!=drop)
    sign=1 if orient(*b,axes)>0 else -1;poly=list(a)
    for i in range(3):
        budget.consume(1+len(poly),'surface_clip')
        if not poly:break
        c,d=b[i],b[(i+1)%3];out=[]
        for j,p in enumerate(poly):
            r=poly[j-1];fp=sign*orient(c,d,p,axes);fr=sign*orient(c,d,r,axes)
            if (fp>=0)!=(fr>=0):out.append(add(r,mul(sub(p,r),Q(fr,fr-fp))))
            if fp>=0:out.append(p)
        poly=list(dict.fromkeys(out))
    return poly


def plane_slice(t,dist):
    points=[p for p,d in zip(t,dist) if d==0]
    for i in range(3):
        j=(i+1)%3
        if dist[i]*dist[j]<0:points.append(add(t[i],mul(sub(t[j],t[i]),Q(dist[i],dist[i]-dist[j]))))
    return list(dict.fromkeys(points))


def intersection(a,b,budget):
    na,nb=normal(a),normal(b);require(any(na) and any(nb),'degenerate_triangle')
    da=[dot(na,sub(p,a[0])) for p in b];db=[dot(nb,sub(p,b[0])) for p in a]
    if all(v>0 for v in da) or all(v<0 for v in da) or all(v>0 for v in db) or all(v<0 for v in db):return []
    axis=cross(na,nb)
    if not any(axis):return clip_coplanar(a,b,na,budget) if all(d==0 for d in da) else []
    pa,pb=plane_slice(a,db),plane_slice(b,da)
    if not pa or not pb:return []
    k=max(range(3),key=lambda k:abs(axis[k]));pa.sort(key=lambda p:p[k]);pb.sort(key=lambda p:p[k])
    left=max(pa[0],pb[0],key=lambda p:p[k]);right=min(pa[-1],pb[-1],key=lambda p:p[k])
    return [] if left[k]>right[k] else list(dict.fromkeys((left,right)))


def dimension(points):
    if len(points)<=1:return 'point'
    direction=sub(points[1],points[0])
    return 'area' if any(any(cross(direction,sub(p,points[0]))) for p in points[2:]) else 'line'


def relation(points,a,b):
    kind=dimension(points)
    if kind=='area':return 'coplanar_overlap'
    if kind=='line' and any(cross(normal(a),normal(b))):
        center=tuple(Q(sum(p[k] for p in points),len(points)) for k in range(3))
        def strict_inside(t):
            n=normal(t)
            return all(dot(cross(sub(t[(i+1)%3],t[i]),sub(center,t[i])),n)>0 for i in range(3))
        if strict_inside(a) and strict_inside(b):return 'transverse_crossing'
    return 'boundary_contact'


def legal_simplex(points,shared,vertices):
    if not shared or len(shared)==3:return False
    if len(shared)==1:return all(p==vertices[shared[0]] for p in points)
    a,b=(vertices[i] for i in shared);d=sub(b,a);n=dot(d,d)
    return bool(n) and all(not any(cross(sub(p,a),d)) and 0<=dot(sub(p,a),d)<=n for p in points)


def world_integers(raw,budget):
    """One exact dyadic frame; integer AABBs cannot round away contacts."""
    matrix=[[Q(x) for x in row] for row in raw['matrix_world']];scale=Q(raw['unit_scale'])
    require(dot(matrix[0][:3],cross(matrix[1][:3],matrix[2][:3]))!=0,'singular_metric_frame')
    points=[];exponent=0
    for p in raw['vertices']:
        budget.consume(4,'surface_exact_frame')
        v=tuple((sum(matrix[r][c]*Q(p[c]) for c in range(3))+matrix[r][3])*scale for r in range(3))
        for x in v:
            require(x.denominator&(x.denominator-1)==0,'non_dyadic_frame')
            require(x.numerator.bit_length()<=LIMITS['bits'] and x.denominator.bit_length()<=LIMITS['bits'],'coordinate_bit_budget')
            exponent=max(exponent,x.denominator.bit_length()-1)
        points.append(v)
    factor=1<<exponent
    result=[tuple(int(x*factor) for x in p) for p in points]
    require(all(abs(x).bit_length()<=LIMITS['bits'] for p in result for x in p),'coordinate_bit_budget')
    return result,factor


def validate_tessellation(raw,triangles,polygons,budget):
    require(type(triangles) is list and type(polygons) is list and len(triangles)==len(polygons)
        and len(triangles)<=LIMITS['triangles'] and len(raw['vertices'])<=LIMITS['vertices'],'geometry_budget')
    counts=[0]*len(raw['polygons'])
    for t,p in zip(triangles,polygons):
        budget.consume(4,'surface_tessellation')
        require(type(p) is int and 0<=p<len(counts) and type(t) is list and len(t)==3
            and all(type(i) is int and i in raw['polygons'][p] for i in t) and len(set(t))==3,'tessellation_mapping')
        counts[p]+=1
    require(counts==[len(p)-2 for p in raw['polygons']],'tessellation_coverage')


def candidate_pairs(bounds,pad,budget,stats):
    """Exact outward BVH; disjoint node pairs certify all descendant pairs.

    Nodes partition source triangle ids. Self traversal visits LL, LR, RR;
    cross traversal splits one side, so no unordered pair is duplicated.
    """
    def build(ids):
        budget.consume(1+len(ids),'surface_bvh_build')
        lo=tuple(min(bounds[i][0][k] for i in ids) for k in range(3))
        hi=tuple(max(bounds[i][1][k] for i in ids) for k in range(3))
        if len(ids)<=4:return (lo,hi,len(ids),ids,None,None)
        axis=max(range(3),key=lambda k:hi[k]-lo[k]);ids.sort(key=lambda i:(bounds[i][0][axis]+bounds[i][1][axis],i));mid=len(ids)//2
        return (lo,hi,len(ids),None,build(ids[:mid]),build(ids[mid:]))
    if not bounds:return
    root=build(list(range(len(bounds))));pending=[(root,root)]
    while pending:
        budget.consume(1,'surface_bvh_node_pair');a,b=pending.pop();stats['node_pair_visits']+=1
        if any(a[1][k]+pad<b[0][k] or b[1][k]+pad<a[0][k] for k in range(3)):
            stats['aabb_pruned_pairs']+=a[2]*(a[2]-1)//2 if a is b else a[2]*b[2];continue
        if a[3] is not None and b[3] is not None:
            for i in a[3]:
                for j in b[3]:
                    if a is b and i>=j:continue
                    budget.consume(1,'surface_bvh_leaf_pair');stats['leaf_pair_visits']+=1
                    if any(bounds[i][1][k]+pad<bounds[j][0][k] or bounds[j][1][k]+pad<bounds[i][0][k] for k in range(3)):
                        stats['aabb_pruned_pairs']+=1;continue
                    yield tuple(sorted((i,j)))
        elif a is b:pending.extend(((a[4],a[4]),(a[4],a[5]),(a[5],a[5])))
        elif b[3] is not None or a[3] is None and a[2]>=b[2]:pending.extend(((a[4],b),(a[5],b)))
        else:pending.extend(((a,b[4]),(a,b[5])))


def analyze(prepared,triangles,triangle_polygons,*,budget,near_m=0.00001):
    require(type(near_m) in (int,float) and math.isfinite(near_m) and 0<=near_m<=.001,'near_threshold')
    raw=prepared['raw'];validate_tessellation(raw,triangles,triangle_polygons,budget)
    vertices,factor=world_integers(raw,budget);tolerance=Q(near_m)*factor
    pad=(tolerance.numerator+tolerance.denominator-1)//tolerance.denominator
    bounds=[];bad=[];points=[]
    for i,tri in enumerate(triangles):
        budget.consume(1,'surface_bounds');t=tuple(vertices[j] for j in tri);points.append(t)
        if not any(normal(t)):bad.append(i)
        bounds.append((tuple(min(p[k] for p in t) for k in range(3)),tuple(max(p[k] for p in t) for k in range(3))))
    retained=[];total=0;tested=0;completed=True;reason=None
    stats=dict(node_pair_visits=0,leaf_pair_visits=0,aabb_pruned_pairs=0)
    priorities={'transverse_crossing':0,'coplanar_overlap':1,'near_parallel':2,'boundary_contact':3}
    counts={k:0 for k in priorities}
    degenerate=set(bad);unknown_degenerate_pairs=0
    try:
        for j,i in candidate_pairs(bounds,pad,budget,stats):
                if tested>=LIMITS['pair_tests']:raise ValueError('surface_pair_test_budget')
                tested+=1;budget.consume(8,'surface_pair')
                if i in degenerate or j in degenerate:unknown_degenerate_pairs+=1;continue
                a,b=points[j],points[i];shared=sorted(set(triangles[j])&set(triangles[i]))
                witness=intersection(a,b,budget);kind=None;gap=None
                if witness and not legal_simplex(witness,shared,vertices):kind='contact_'+dimension(witness)
                if not witness and tolerance>0:
                    na,nb=normal(a),normal(b);delta=dot(na,sub(b[0],a[0]));nn=dot(na,na)
                    if not any(cross(na,nb)) and 0<delta*delta<=tolerance*tolerance*nn:
                        projected=[sub(p,mul(na,Q(delta,nn))) for p in b]
                        overlap=clip_coplanar(a,projected,na,budget)
                        if len(overlap)>=3 and dimension(overlap)=='area':
                            witness=overlap;kind='near_parallel_overlap';gap=math.sqrt(float(Q(delta*delta,nn*factor*factor)))
                if kind:
                    budget.consume(1,'surface_result_priority')
                    category='near_parallel' if kind=='near_parallel_overlap' else relation(witness,a,b)
                    total+=1;counts[category]+=1;left,right=sorted((j,i));key=(-priorities[category],-left,-right)
                    if len(retained)<LIMITS['results'] or key>retained[0][:3]:
                        center=[float(Q(sum(p[k] for p in witness),len(witness)*factor)) for k in range(3)]
                        require(all(math.isfinite(x) for x in center),'display_coordinate_overflow')
                        row=dict(triangles=[left,right],polygons=[triangle_polygons[left],triangle_polygons[right]],kind=kind,
                            relation=category,center_m=center,plane_gap_m=gap,shared_source_vertices=shared)
                        item=(*key,row)
                        if len(retained)<LIMITS['results']:heapq.heappush(retained,item)
                        else:heapq.heapreplace(retained,item)
    except Exception as exc:
        # Budget errors are explicit partial coverage. Programming faults must
        # not be disguised as ordinary geometry refusals.
        if type(exc).__name__!='StructureStopped' and str(exc)!='surface_pair_test_budget':raise
        completed=False;reason=str(exc)
    budget.check('surface_report')
    require(not completed or stats['aabb_pruned_pairs']+tested==len(points)*(len(points)-1)//2,'pair_accounting_invariant')
    found=[item[3] for item in sorted(retained,key=lambda item:(-item[0],-item[1],-item[2]))]
    return dict(schema=PROTOCOL,status='observed' if completed and not bad else 'partial',source=prepared['source'],
        tessellation_sha256=digest(dict(triangles=triangles,polygon_indices=triangle_polygons)),
        metric='exact_dyadic_input_affine_metres_not_renderer_precision',near_threshold_m=near_m,
        scan_complete=completed,triangle_count=len(points),pair_count=len(points)*(len(points)-1)//2,
        spatial_index='exact_integer_bvh_v1',spatial_work=stats,exact_pair_tests=tested,
        pair_accounting_complete=completed and stats['aabb_pruned_pairs']+tested==len(points)*(len(points)-1)//2,
        degenerate_triangles=bad[:128],
        degenerate_triangles_total=len(bad),unknown_degenerate_pairs=unknown_degenerate_pairs,
        found=total,total=total if completed and not bad else None,counts_by_relation=counts,
        delivery_priority=list(priorities),delivered=len(found),omitted=total-len(found),regions=found,
        reason=reason,execution_authority=False,damage_classification='not_inferred',
        not_checked=['nonparallel_near_distance','volume_containment','wire_intersections','intent','evaluated_modifier_geometry'],
        work_used=budget.used)
