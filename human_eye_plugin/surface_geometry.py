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


def _bvh(bounds,budget,ids=None):
    ids=list(range(len(bounds))) if ids is None else ids
    budget.consume(1+len(ids),'surface_bvh_build')
    lo=tuple(min(bounds[i][0][k] for i in ids) for k in range(3))
    hi=tuple(max(bounds[i][1][k] for i in ids) for k in range(3))
    if len(ids)<=4:return (lo,hi,len(ids),ids,None,None)
    axis=max(range(3),key=lambda k:hi[k]-lo[k]);ids.sort(key=lambda i:(bounds[i][0][axis]+bounds[i][1][axis],i));mid=len(ids)//2
    return (lo,hi,len(ids),None,_bvh(bounds,budget,ids[:mid]),_bvh(bounds,budget,ids[mid:]))


def candidate_pairs(bounds,pad,budget,stats,*,other_bounds=None,roots=None):
    """Exact outward BVH; disjoint node pairs certify all descendant pairs.

    Nodes partition source triangle ids. Self traversal visits LL, LR, RR;
    cross traversal splits one side, so no unordered pair is duplicated.
    """
    if not bounds:return
    other=bounds if other_bounds is None else other_bounds
    if not other:return
    if roots is None:
        root=_bvh(bounds,budget);roots=(root,root if other_bounds is None else _bvh(other,budget))
    pending=[roots]
    while pending:
        budget.consume(1,'surface_bvh_node_pair');a,b=pending.pop();stats['node_pair_visits']+=1
        if any(a[1][k]+pad<b[0][k] or b[1][k]+pad<a[0][k] for k in range(3)):
            stats['aabb_pruned_pairs']+=a[2]*(a[2]-1)//2 if a is b else a[2]*b[2];continue
        if a[3] is not None and b[3] is not None:
            for i in a[3]:
                for j in b[3]:
                    if a is b and i>=j:continue
                    budget.consume(1,'surface_bvh_leaf_pair');stats['leaf_pair_visits']+=1
                    if any(bounds[i][1][k]+pad<other[j][0][k] or other[j][1][k]+pad<bounds[i][0][k] for k in range(3)):
                        stats['aabb_pruned_pairs']+=1;continue
                    yield tuple(sorted((i,j))) if other_bounds is None else (i,j)
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


CLOSED_SOLID_MAX_WORK = 262144
CLOSED_SOLID_MAX_PAIR_TESTS = 16384
CLOSED_SOLID_MAX_RAY_TESTS = 16384
CLOSED_SOLID_METHOD = 'bounded_exact_closed_shell_v1'
CLOSED_SOLID_SCOPE = 'two_connected_embedded_closed_orientable_triangle_shells_binary64_world_zero_tolerance'


class _ClosedDomain(ValueError):
    pass


class _ClosedWork:
    def __init__(self, checkpoint, diagnostics, exact):
        self.checkpoint=checkpoint;self.exact=exact
        self.counts=diagnostics if diagnostics is not None else {}
        self.counts.update(work_units=0,pair_tests=0,self_pair_tests=0,cross_pair_tests=0,
            ray_tests=0,point_queries=0,ray_attempts=0,validated_faces=0,referenced_vertices=0,
            node_pair_visits=0,leaf_pair_visits=0,aabb_pruned_pairs=0,prepared_pair_reused=False)

    def consume(self, amount, stage):
        self.checkpoint('closed_solid_'+stage)
        if self.counts['work_units']+amount>CLOSED_SOLID_MAX_WORK:
            raise _ClosedDomain('closed_solid_work_budget')
        self.counts['work_units']+=amount

    def tick(self, kind, amount=1):
        self.consume(amount,kind);self.counts[kind]=self.counts.get(kind,0)+amount

    def pair(self, kind):
        self.consume(1,kind)
        if self.counts['pair_tests']>=CLOSED_SOLID_MAX_PAIR_TESTS:
            raise _ClosedDomain('closed_solid_pair_budget')
        self.counts['pair_tests']+=1;self.counts[kind]+=1


def _closed_require(value, reason):
    if not value:raise _ClosedDomain('closed_solid_'+reason)


def _closed_topology(mesh, faces, triangles, budget):
    from collections import defaultdict
    e=budget.exact
    edges=defaultdict(list);links=defaultdict(list);used=set();unique=set()
    vertices={}
    for ordinal,(face,triangle) in enumerate(zip(faces,triangles)):
        budget.consume(1,'topology_face')
        _closed_require(triangle[2] and len(triangle[0])==3,'degenerate_face')
        key=tuple(sorted(face));_closed_require(key not in unique,'duplicate_face');unique.add(key)
        for i,v in enumerate(face):
            used.add(v);vertices[v]=triangle[0][i]
            a,b=face[(i+1)%3],face[(i+2)%3]
            links[v].append((a,b))
            edges[tuple(sorted((v,a)))].append((ordinal,v<a))
    _closed_require(len(used)==len(mesh.vertices),'unreferenced_vertices')
    neighbours=[set() for _ in faces]
    for adjacent in edges.values():
        budget.consume(1,'topology_edge')
        _closed_require(len(adjacent)==2 and adjacent[0][1]!=adjacent[1][1],'open_nonmanifold_or_orientation')
        a,b=adjacent[0][0],adjacent[1][0];neighbours[a].add(b);neighbours[b].add(a)
    seen={0};pending=[0]
    while pending:
        budget.consume(1,'topology_connected')
        for other in neighbours[pending.pop()]-seen:seen.add(other);pending.append(other)
    _closed_require(len(seen)==len(faces),'multiple_shells')
    for rows in links.values():
        graph=defaultdict(set)
        for a,b in rows:graph[a].add(b);graph[b].add(a)
        _closed_require(all(len(row)==2 for row in graph.values()),'nonmanifold_vertex')
        first=next(iter(graph));seen={first};pending=[first]
        while pending:
            budget.consume(1,'topology_vertex_link')
            for other in graph[pending.pop()]-seen:seen.add(other);pending.append(other)
        _closed_require(len(seen)==len(graph),'nonmanifold_vertex')
    volume=0
    for tri in triangles:
        budget.consume(1,'oriented_volume')
        volume=e._bounded(volume+e._dot(tri[0][0],e._cross(tri[0][1],tri[0][2])))
    _closed_require(volume!=0,'zero_volume')
    bounds=[(tuple(row[0] for row in t[4]),tuple(row[1] for row in t[4])) for t in triangles]
    return dict(vertices=vertices,faces=faces,triangles=triangles,bounds=bounds,root=_bvh(bounds,budget))


def _closed_legal_contact(points, shared, vertices, budget):
    e=budget.exact
    if len(shared)==1:return all(p==vertices[shared[0]] for p in points)
    if len(shared)!=2:return False
    a,b=(vertices[i] for i in shared);d=e._sub(b,a);squared=e._dot(d,d)
    return bool(squared) and all(not any(e._cross(e._sub(p,a),d))
        and 0<=e._dot(e._sub(p,a),d)<=squared for p in points)


def _closed_validate_embedded(shell,budget):
    e=budget.exact
    for i,j in candidate_pairs(shell['bounds'],0,budget,budget.counts,roots=(shell['root'],shell['root'])):
        budget.pair('self_pair_tests')
        a,b=shell['triangles'][i],shell['triangles'][j]
        points=e._intersection(a[0],b[0],a[1],b[1],budget)
        if points:
            shared=sorted(set(shell['faces'][i])&set(shell['faces'][j]))
            _closed_require(_closed_legal_contact(points,shared,shell['vertices'],budget),'self_intersection')


def _closed_in_triangle(point, triangle, budget, strict=False):
    e=budget.exact;points,n,squared,_,_=triangle
    q=e._sub(point,points[0])
    if e._dot(n,q)!=0:return False
    u=e._dot(e._cross(e._sub(points[2],points[0]),n),q)
    v=e._dot(e._cross(n,e._sub(points[1],points[0])),q)
    total=e._bounded(u+v)
    return u>0 and v>0 and total<squared if strict else u>=0 and v>=0 and total<=squared


def _closed_transverse(points,a,b,budget):
    e=budget.exact
    if len(points)!=2 or points[0]==points[1] or not any(e._cross(a[1],b[1])):return False
    middle=e._mul(e._add(points[0],points[1]),e._fraction(1,2))
    return _closed_in_triangle(middle,a,budget,True) and _closed_in_triangle(middle,b,budget,True)


def _closed_point_candidates(point,shell,budget):
    pending=[shell['root']]
    while pending:
        budget.consume(1,'point_bvh')
        node=pending.pop()
        if any(point[k]<node[0][k] or point[k]>node[1][k] for k in range(3)):continue
        if node[3] is not None:
            for i in node[3]:
                low,high=shell['bounds'][i]
                if all(low[k]<=point[k]<=high[k] for k in range(3)):yield i
        else:pending.extend((node[4],node[5]))


def _closed_ray_box(point,direction,low,high,budget):
    e=budget.exact;near=0;far=None
    for k in range(3):
        left=e._fraction(e._bounded(low[k]-point[k]),direction[k])
        right=e._fraction(e._bounded(high[k]-point[k]),direction[k])
        near=max(near,left);far=right if far is None else min(far,right)
        if far<near:return False
    return far>0


def _closed_ray_candidates(point,direction,shell,budget):
    pending=[shell['root']]
    while pending:
        budget.consume(1,'ray_bvh')
        node=pending.pop()
        if not _closed_ray_box(point,direction,node[0],node[1],budget):continue
        if node[3] is not None:
            for i in node[3]:
                if _closed_ray_box(point,direction,*shell['bounds'][i],budget):yield i
        else:pending.extend((node[4],node[5]))


def _closed_location(point,shell,budget):
    e=budget.exact;budget.tick('point_queries')
    for i in _closed_point_candidates(point,shell,budget):
        if _closed_in_triangle(point,shell['triangles'][i],budget):return 'boundary'
    for k in range(1,9):
        budget.tick('ray_attempts');direction=(1,k,k*k+1);count=0;ambiguous=False
        for i in _closed_ray_candidates(point,direction,shell,budget):
            budget.tick('ray_tests')
            if budget.counts['ray_tests']>CLOSED_SOLID_MAX_RAY_TESTS:
                raise _ClosedDomain('closed_solid_ray_budget')
            triangle=shell['triangles'][i];n=triangle[1]
            numerator=e._dot(n,e._sub(triangle[0][0],point));denominator=e._dot(n,direction)
            if denominator==0:
                if numerator==0:ambiguous=True;break
                continue
            parameter=e._fraction(numerator,denominator)
            if parameter<=0:continue
            hit=e._add(point,e._mul(direction,parameter))
            if not _closed_in_triangle(hit,triangle,budget):continue
            if not _closed_in_triangle(hit,triangle,budget,True):ambiguous=True;break
            count+=1
        if not ambiguous:return 'inside' if count%2 else 'outside'
    raise _ClosedDomain('closed_solid_ray_degeneracy')


def _closed_separating_plane(triangle,left,right,budget):
    e=budget.exact;origin=triangle[0][0];n=triangle[1]
    def signs(shell):
        positive=False;negative=False
        for point in shell['vertices'].values():
            budget.consume(1,'supporting_plane')
            value=e._dot(n,e._sub(point,origin))
            positive|=value>0;negative|=value<0
            if positive and negative:return None
        return 1 if positive else -1 if negative else 0
    a=signs(left)
    if a is None:return False
    b=signs(right)
    return b is not None and a*b<0


def classify_closed_solids(left,right,checkpoint,*,diagnostics=None,prepared_pair=None,prepared_holder=None):
    """Zero-tolerance relation of represented embedded, connected closed shells.

    Interior overlap needs a strict containment or transverse-boundary witness.
    Contact needs a global separating plane certificate. Unresolved coincident
    or mesh-edge boundary arrangements remain unknown, never guessed touching.
    """
    from . import surface_proximity as exact
    budget=_ClosedWork(checkpoint,diagnostics,exact)
    result=dict(measurement_valid=False,relation=None,method=CLOSED_SOLID_METHOD,
        geometry_scope=CLOSED_SOLID_SCOPE,relation_tolerance_m=0.0,work=budget.counts)
    try:
        budget.consume(1,'admission')
        _closed_require(sum(len(mesh.vertices) for mesh in (left,right))<=LIMITS['vertices'],
                        'vertex_budget')
        if prepared_pair is None:
            records,topology=exact._admit((left,right),budget)
            origin,factor,prepared=exact._integer_frame(records,budget)
            prepared_pair=(records,topology,origin,factor,prepared)
        else:budget.counts['prepared_pair_reused']=True
        if prepared_holder is not None:prepared_holder['pair']=prepared_pair
        records,_,_,_,prepared=prepared_pair
        _closed_require(all(len(r[1])>=4 for r in records),'too_few_faces')
        shells=[_closed_topology(record[0],record[1],triangles,budget)
                for record,triangles in zip(records,prepared)]
        for shell in shells:_closed_validate_embedded(shell,budget)
        a,b=shells;contacts=[]
        for i,j in candidate_pairs(a['bounds'],0,budget,budget.counts,
                other_bounds=b['bounds'],roots=(a['root'],b['root'])):
            budget.pair('cross_pair_tests')
            ta,tb=a['triangles'][i],b['triangles'][j]
            points=exact._intersection(ta[0],tb[0],ta[1],tb[1],budget)
            if not points:continue
            if _closed_transverse(points,ta,tb,budget):
                result.update(measurement_valid=True,relation='penetrating',certificate='transverse_boundary_interiors')
                return result
            contacts.append((i,j))
        if contacts:
            seen=set()
            for i,j in contacts:
                for side,index in ((0,i),(1,j)):
                    if (side,index) in seen:continue
                    seen.add((side,index))
                    if _closed_separating_plane(shells[side]['triangles'][index],a,b,budget):
                        result.update(measurement_valid=True,relation='touching',certificate='global_supporting_plane_with_contact')
                        return result
            for source,target in ((a,b),(b,a)):
                groups=(source['vertices'].values(),
                    (exact._mul(exact._add(exact._add(t[0][0],t[0][1]),t[0][2]),exact._fraction(1,3)) for t in source['triangles']))
                for points in groups:
                    for point in points:
                        if _closed_location(point,target,budget)=='inside':
                            result.update(measurement_valid=True,relation='penetrating',certificate='strict_containment_point')
                            return result
            raise _ClosedDomain('closed_solid_ambiguous_boundary_arrangement')
        locations=[_closed_location(next(iter(a['vertices'].values())),b,budget),
                   _closed_location(next(iter(b['vertices'].values())),a,budget)]
        _closed_require('boundary' not in locations,'unresolved_boundary')
        result.update(measurement_valid=True,relation='penetrating' if 'inside' in locations else 'separated',
            certificate='disjoint_boundaries_with_exact_parity')
        return result
    except (_ClosedDomain,exact._DomainError) as error:
        reason=str(error)
        result['reason']=reason.replace('surface_','closed_solid_',1) if reason.startswith('surface_') else reason
        return result
