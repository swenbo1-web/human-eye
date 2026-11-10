"""Independent final-worldmesh certificates for SCALE-DIAG-001.

No product or measured native implementation is imported.  A positive rational
support-plane separation is a lower bound on every triangle-pair distance.
Rational barycentric points on actual input faces supply an upper bound.  The
local two-layer prism check is independent of the generator's declared gap.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal, localcontext, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def fraction(value): return F.from_float(float(value))
def fpoint(value): return tuple(fraction(v) for v in value)
def encoded_fraction(v): return [v.numerator, v.denominator]


def sqrt_bounds(value):
    assert value >= 0
    if not value: return 0., 0.
    # Decimal.sqrt rounds to nearest.  One Decimal ulp around a directed input
    # quotient, followed by outward binary64 conversion, encloses the root.
    with localcontext() as ctx:
        ctx.prec = 100
        ctx.rounding = ROUND_FLOOR
        lo = (Decimal(value.numerator)/Decimal(value.denominator)).sqrt().next_minus()
        ctx.rounding = ROUND_CEILING
        hi = (Decimal(value.numerator)/Decimal(value.denominator)).sqrt().next_plus()
        return math.nextafter(float(lo), -math.inf), math.nextafter(float(hi), math.inf)


def connected(nodes, adjacency):
    if not nodes: return False
    seen = {next(iter(nodes))}; todo = list(seen)
    while todo:
        for node in adjacency.get(todo.pop(), ()):
            if node not in seen: seen.add(node); todo.append(node)
    return seen == set(nodes)


def edge_map(faces):
    edges = defaultdict(list)
    for fi, tri in enumerate(faces):
        for a, b in zip(tri, tri[1:]+tri[:1]):
            edges[tuple(sorted((a, b)))].append((fi, a, b))
    return edges


def boundary_cycle(cap_faces):
    edges = edge_map(cap_faces)
    boundary = [(rows[0][1], rows[0][2]) for rows in edges.values() if len(rows) == 1]
    if any(len(rows) not in (1, 2) for rows in edges.values()): raise ValueError('cap_edge_multiplicity')
    nxt = dict(boundary)
    if len(nxt) != len(boundary) or len(set(nxt.values())) != len(nxt): raise ValueError('cap_boundary_branches')
    start = next(iter(nxt)); cycle = [start]; current = nxt[start]
    while current != start:
        if current in cycle or current not in nxt: raise ValueError('cap_boundary_not_one_cycle')
        cycle.append(current); current = nxt[current]
    if len(cycle) != len(boundary): raise ValueError('cap_multiple_boundaries')
    return cycle, edges


def rectangle_simple_cycle(points):
    # Exact comparisons of finite binary64 local XY values; no arithmetic
    # tolerance can turn a crossing into a legal polygon.
    segments = list(zip(points, points[1:]+points[:1])); n = len(segments)
    for a, b in segments:
        if (a[0] == b[0]) == (a[1] == b[1]): raise ValueError('not_rectilinear_nonzero_boundary')
    for i, (a, b) in enumerate(segments):
        for j in range(i+1, n):
            if j == i+1 or i == 0 and j == n-1: continue
            c, d = segments[j]
            if (max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0]))
                    and max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1]))):
                raise ValueError('boundary_self_intersection_or_touch')


def inverse3(columns):
    a,b,c=columns;det=dot(a,cross(b,c))
    if not det:raise ValueError('singular_tetrahedron_or_frame')
    return tuple(tuple(v/det for v in row) for row in (cross(b,c),cross(c,a),cross(a,b)))


def mul_rows(rows, vector):
    return tuple(dot(row,vector) for row in rows)


def actual_world_embedding(local, faces, world, matrix, caps, cycles, levels):
    """Certify rounded final faces through an injective PL extension.

    Fill only the rectilinear complement with grid cells, making a convex box.
    Cone each triangular column's boundary triangles to its centre.  Its
    exact piecewise affine displacement in the inverse world frame has a
    global gradient norm <1.  Integrating across the convex box proves this
    extension injective, hence its original boundary restriction embedded.
    This also checks conformity; a T junction cannot qualify accidentally.
    """
    loc=[fpoint(p) for p in local];wor=[fpoint(p) for p in world]
    if len(set(loc))!=len(loc):raise ValueError('duplicate_local_vertex_in_embedding_domain')
    cols=[tuple(fraction(matrix[i][j]) for i in range(3)) for j in range(3)]
    inv=inverse3(cols);translation=tuple(fraction(matrix[i][3]) for i in range(3))
    displacement={}
    for p,w in zip(loc,wor):
        ideal=tuple(translation[k]+sum(cols[j][k]*p[j] for j in range(3)) for k in range(3))
        displacement[p]=mul_rows(inv,sub(w,ideal))
    first=[tuple(tuple(loc[i][:2]) for i in tri) for tri in caps[0]]
    other={tuple(sorted(tuple(loc[i][:2]) for i in tri)) for tri in caps[1]}
    if {tuple(sorted(t)) for t in first}!=other:raise ValueError('cap_triangulations_not_corresponding')
    polygon=[tuple(loc[i][:2]) for i in cycles[0]]
    xs=sorted({p[0] for p in polygon});ys=sorted({p[1] for p in polygon})
    def inside(p):
        return sum(a[0]>p[0] and min(a[1],b[1])<p[1]<max(a[1],b[1])
                   for a,b in zip(polygon,polygon[1:]+polygon[:1]) if a[0]==b[0])%2==1
    filled=list(first)
    for x0,x1 in zip(xs,xs[1:]):
        for y0,y1 in zip(ys,ys[1:]):
            if inside(((x0+x1)/2,(y0+y1)/2)):continue
            a,b,c,d=(x0,y0),(x1,y0),(x1,y1),(x0,y1)
            filled.extend(((a,b,c),(a,c,d)))
    edge_counts=Counter(tuple(sorted((a,b))) for tri in filled for a,b in zip(tri,tri[1:]+tri[:1]))
    for (a,b),n in edge_counts.items():
        outer=(a[0]==b[0] and a[0] in (xs[0],xs[-1])) or (a[1]==b[1] and a[1] in (ys[0],ys[-1]))
        if n!=(1 if outer else 2):raise ValueError('convex_extension_nonconforming_edge')
    if sum(abs(cross(sub(b,a)+(F(0),),sub(c,a)+(F(0),))[2]) for a,b,c in filled)!=2*(xs[-1]-xs[0])*(ys[-1]-ys[0]):
        raise ValueError('convex_extension_area_coverage')
    side=defaultdict(list)
    for tri in faces:
        if len({loc[i][2] for i in tri})==2:
            side[tuple(sorted({loc[i][:2] for i in tri}))].append(tuple(loc[i] for i in tri))
    zl,zh=map(fraction,levels);zero=(F(0),F(0),F(0));max_squared=F(0);tetrahedra=0
    for xy in filled:
        lower=[p+(zl,) for p in xy];upper=[p+(zh,) for p in xy]
        boundary=[tuple(lower),tuple(upper)]
        for i,j in ((0,1),(1,2),(2,0)):
            key=tuple(sorted((xy[i],xy[j])))
            if key in side:boundary.extend(side[key])
            else:
                a,b=key;al,bl,ah,bh=a+(zl,),b+(zl,),a+(zh,),b+(zh,)
                boundary.extend(((al,bl,bh),(al,bh,ah)))
        center=tuple(sum(p[k] for p in lower+upper)/6 for k in range(3))
        for tri in boundary:
            rows=inverse3([sub(v,center) for v in tri])
            errors=[displacement.get(v,zero) for v in tri]
            grad=tuple(tuple(sum(errors[j][k]*rows[j][l] for j in range(3)) for l in range(3)) for k in range(3))
            squared=sum(v*v for row in grad for v in row);max_squared=max(max_squared,squared);tetrahedra+=1
    if max_squared>=1:raise ValueError('actual_world_injective_extension_not_proved')
    return {'method':'exact_rational_convex_box_piecewise_affine_displacement_extension',
            'tetrahedra':tetrahedra,'squared_frobenius_gradient_upper':encoded_fraction(max_squared),
            'gradient_norm_upper':sqrt_bounds(max_squared)[1],
            'proof':'continuous extension on convex box; ||D(displacement)||<1 implies injectivity; original actual face triangles are its restriction to the original prism boundary'}


def prism_qualification(local, faces, world, matrix):
    result = {'qualified': False, 'method': 'independent_closed_rectilinear_prism_structure_v1'}
    try:
        levels = sorted({p[2] for p in local})
        if len(levels) != 2: raise ValueError('not_two_extrusion_levels')
        edges = edge_map(faces); adjacency = defaultdict(set)
        for rows in edges.values():
            if len(rows) != 2 or rows[0][1:] != rows[1][1:][::-1]: raise ValueError('not_closed_oriented_two_manifold')
            a, b = rows[0][0], rows[1][0]; adjacency[a].add(b); adjacency[b].add(a)
        if not connected(set(range(len(faces))), adjacency): raise ValueError('disconnected_shell')
        if len(local)-len(edges)+len(faces) != 2: raise ValueError('unexpected_shell_euler')
        caps = [[t for t in faces if all(local[i][2] == z for i in t)] for z in levels]
        cycles = []; cap_area = []
        for cap in caps:
            if not cap: raise ValueError('missing_cap')
            cycle, ce = boundary_cycle(cap); cycles.append(cycle)
            points = [tuple(local[i][:2]) for i in cycle]; rectangle_simple_cycle(points)
            used = set(i for t in cap for i in t)
            if len(used)-len(ce)+len(cap) != 1: raise ValueError('cap_not_disk_euler')
            ca = defaultdict(set)
            for rows in ce.values():
                if len(rows) == 2:
                    a, b = rows[0][0], rows[1][0]; ca[a].add(b); ca[b].add(a)
            if not connected(set(range(len(cap))), ca): raise ValueError('cap_not_connected')
            areas = []
            for t in cap:
                a, b, c = [fpoint(local[i]) for i in t]
                areas.append(cross(sub(b, a), sub(c, a))[2])
            if any(not a for a in areas) or min(areas)*max(areas) <= 0: raise ValueError('cap_degenerate_or_orientation_flip')
            poly = [fpoint(local[i]) for i in cycle]
            area = sum(a[0]*b[1]-a[1]*b[0] for a, b in zip(poly, poly[1:]+poly[:1]))
            if sum(areas) != area: raise ValueError('cap_area_boundary_mismatch')
            cap_area.append(area)
        xy_cycles = [[tuple(local[i][:2]) for i in c] for c in cycles]
        e0 = {tuple(sorted((a, b))) for a, b in zip(xy_cycles[0], xy_cycles[0][1:]+xy_cycles[0][:1])}
        e1 = {tuple(sorted((a, b))) for a, b in zip(xy_cycles[1], xy_cycles[1][1:]+xy_cycles[1][:1])}
        if e0 != e1 or cap_area[0]*cap_area[1] >= 0: raise ValueError('caps_do_not_correspond')
        side = [t for t in faces if len({local[i][2] for i in t}) == 2]; groups = Counter()
        for tri in side:
            xy = {tuple(local[i][:2]) for i in tri}
            if len(xy) != 2: raise ValueError('side_not_boundary_rectangle')
            key = tuple(sorted(xy))
            if key not in e0: raise ValueError('side_not_cap_boundary')
            groups[key] += 1
        if set(groups) != e0 or any(n != 2 for n in groups.values()): raise ValueError('side_rectangle_coverage')
        # The final world array, not a generated ideal mesh, is the distance
        # input.  This check separately binds its declared native affine map.
        error = max(abs(math.fsum(float(matrix[k][j])*float(p[j]) for j in range(3))
                        + float(matrix[k][3])-float(w[k])) for p, w in zip(local, world) for k in range(3))
        scale = max(1., *(abs(v) for p in world for v in p))
        if error > 1e-12*scale: raise ValueError('world_not_binary64_affine_forward_map')
        cols = [tuple(fraction(matrix[i][j]) for i in range(3)) for j in range(3)]
        determinant = dot(cols[0], cross(cols[1], cols[2]))
        if not determinant: raise ValueError('singular_world_frame')
        embedding=actual_world_embedding(local,faces,world,matrix,caps,cycles,levels)
        result.update(qualified=True, vertex_count=len(local), triangle_count=len(faces),
                      boundary_vertices=len(cycles[0]), side_triangles=len(side),
                      cap_triangles=[len(c) for c in caps], closed_edges=len(edges),
                      affine_forward_max_error_m=error,
                      determinant=encoded_fraction(determinant),
                      actual_world_embedding=embedding,
                      scope='closed simple local prism and bound affine world forward mapping; not arbitrary mesh qualification')
    except (ValueError, KeyError, StopIteration, IndexError, TypeError) as exc:
        result['reason'] = str(exc)
    return result


def closest_barycentric(point, triangle):
    # Floating guide only.  No numeric guide is a lower bound or an answer;
    # its barycentric proposal is reified to exact nonnegative rational weights.
    a, b, c = triangle; ab=sub(b, a); ac=sub(c, a); ap=sub(point, a)
    aa=dot(ab, ab); bb=dot(ab, ac); cc=dot(ac, ac); den=aa*cc-bb*bb
    if den > 0:
        v=(dot(ap, ab)*cc-dot(ap, ac)*bb)/den
        w=(dot(ap, ac)*aa-dot(ap, ab)*bb)/den
        if v >= 0 and w >= 0 and v+w <= 1: return (1-v-w, v, w)
    best=None
    for i, j in ((0, 1), (1, 2), (2, 0)):
        edge=sub(triangle[j], triangle[i]); squared=dot(edge, edge)
        t=max(0., min(1., dot(sub(point, triangle[i]), edge)/squared)) if squared else 0.
        p=tuple(triangle[i][k]+t*edge[k] for k in range(3)); d=dot(sub(point, p), sub(point, p))
        bary=[0., 0., 0.]; bary[i]=1-t; bary[j]=t
        if best is None or d < best[0]: best=(d, tuple(bary))
    return best[1]


def rational_bary(weights):
    values=[F(max(0., min(1., float(w)))).limit_denominator(10**9) for w in weights]
    total=sum(values)
    if total <= 0: raise ValueError('no_barycentric_weight')
    return tuple(v/total for v in values)


def bary_point(vertices, triangle, weights):
    return tuple(sum(weights[j]*fraction(vertices[triangle[j]][k]) for j in range(3)) for k in range(3))


def mesh(raw):
    world=raw.get('vertices_world', raw.get('world_vertices'))
    local=raw.get('vertices_local', raw.get('local_vertices'))
    faces=raw.get('triangles', raw.get('faces'))
    matrix=raw['matrix_world']
    if not world or not local or len(world) != len(local): raise ValueError('complete_vertex_arrays_required')
    if any(len(p) != 3 or not all(type(x) in (int, float) and math.isfinite(x) for x in p) for p in world+local):
        raise ValueError('finite_three_coordinates_required')
    if not faces or any(len(t) != 3 or len(set(t)) != 3 or any(type(i) is not int or not 0 <= i < len(world) for i in t) for t in faces):
        raise ValueError('actual_triangles_required')
    return {'id':str(raw.get('logical_id', raw.get('id', raw['name']))), 'name':raw['name'],
            'world':world, 'local':local, 'faces':[list(t) for t in faces], 'matrix':matrix,
            'geometry_sha256':digest({'world':world, 'local':local, 'triangles':faces, 'matrix':matrix})}


def pair_certificate(left, right, tolerance=1e-6):
    a, b=left['world'], right['world']; matrix=left['matrix']
    x=tuple(fraction(matrix[i][0]) for i in range(3)); z=tuple(fraction(matrix[i][2]) for i in range(3))
    normal=cross(z, x); norm2=dot(normal, normal)
    if norm2 <= 0: raise ValueError('no_guiding_world_normal')
    pa=[dot(normal, fpoint(p)) for p in a]; pb=[dot(normal, fpoint(p)) for p in b]
    if min(pb)-max(pa) <= 0 and min(pa)-max(pb) > 0:
        normal=tuple(-v for v in normal);pa=[-v for v in pa];pb=[-v for v in pb]
    support_a=max(pa);support_b=min(pb);gap=support_b-support_a
    result={'target':left['id'], 'candidate':right['id'], 'surface_distance_qualified':False,
            'relation_qualified':False, 'method':'exact_vertex_support_lower_and_face_barycentric_upper_v1',
            'left_geometry_sha256':left['geometry_sha256'], 'right_geometry_sha256':right['geometry_sha256']}
    if gap <= 0:
        result['reason']='no_positive_support_plane_separation';return result
    lower_sq=gap*gap/norm2;lower,_=sqrt_bounds(lower_sq)
    # Only guide which actual surface faces to propose.  All vertices, not
    # only guide faces, already participated in the global support lower bound.
    normal_float=tuple(float(v) for v in normal); nscale=math.sqrt(float(norm2))
    guide_eps=max(1e-12, 1e-8*nscale)
    af=[i for i,t in enumerate(left['faces']) if max(float(support_a-pa[j]) for j in t)<=guide_eps]
    bf=[i for i,t in enumerate(right['faces']) if max(float(pb[j]-support_b) for j in t)<=guide_eps]
    if not af or not bf:
        result.update(reason='no_near_support_face_witness',distance_lower_m=lower);return result
    best=None
    samples=((1/3,1/3,1/3),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.),(.5,.5,0.),(0.,.5,.5),(.5,0.,.5))
    for sample in samples:
        for ai in af:
            at=left['faces'][ai];p=tuple(sum(sample[j]*a[at[j]][k] for j in range(3)) for k in range(3))
            guide=tuple(p[k]+float(gap/norm2)*normal_float[k] for k in range(3))
            for bi in bf:
                bt=right['faces'][bi];tri=[b[j] for j in bt];weights=closest_barycentric(guide, tri)
                q=tuple(sum(weights[j]*tri[j][k] for j in range(3)) for k in range(3));delta=sub(q,p);squared=dot(delta,delta)
                if best is None or squared<best[0]:best=(squared,ai,bi,sample,weights)
                if math.sqrt(max(0.,squared))-lower < tolerance*.1:break
            if best is not None and math.sqrt(max(0.,best[0]))-lower < tolerance*.1:break
        if best is not None and math.sqrt(max(0.,best[0]))-lower < tolerance*.1:break
    _, ai, bi, wa, wb=best;wa=rational_bary(wa);wb=rational_bary(wb)
    p=bary_point(a,left['faces'][ai],wa);q=bary_point(b,right['faces'][bi],wb)
    upper_sq=dot(sub(q,p),sub(q,p));_,upper=sqrt_bounds(upper_sq)
    assert upper_sq >= lower_sq, 'invalid_support_or_witness_arithmetic'
    result.update(surface_distance_qualified=upper-lower<=tolerance,
        distance_lower_m=lower,distance_upper_m=upper,distance_midpoint_m=(lower+upper)*.5,
        absolute_error_bound_m=(upper-lower)*.5,
        support_normal=[encoded_fraction(v) for v in normal],support_gap=encoded_fraction(gap),
        normal_squared=encoded_fraction(norm2),support_vertex_a=pa.index(support_a),support_vertex_b=pb.index(support_b),
        witness={'triangle_a':ai,'triangle_b':bi,'barycentric_a':[encoded_fraction(v) for v in wa],
                 'barycentric_b':[encoded_fraction(v) for v in wb],
                 'point_a_world_m':[float(v) for v in p],'point_b_world_m':[float(v) for v in q],
                 'squared_distance':encoded_fraction(upper_sq)},
        support_scope='all final world vertices, hence all represented triangle convex hulls')
    if not result['surface_distance_qualified']:result['reason']='support_witness_interval_too_wide'
    if 'solid_qualification' not in left:left['solid_qualification']=prism_qualification(left['local'],left['faces'],a,left['matrix'])
    if 'solid_qualification' not in right:right['solid_qualification']=prism_qualification(right['local'],right['faces'],b,right['matrix'])
    left_q=left['solid_qualification'];right_q=right['solid_qualification']
    result['solid_qualification']={'target':left_q,'candidate':right_q}
    if left_q['qualified'] and right_q['qualified']:
        result.update(relation_qualified=True,solid_relation='separated',
                      relation_evidence='closed simple prism structures and strictly disjoint final-world convex-hull supports')
    return result


def object_selector(row, key, default):
    value=row.get(key,default)
    if isinstance(value,dict):return str(value.get('logical_id',value.get('id',value.get('name'))))
    return str(value)


def snapshot_certificate(raw, tolerance):
    started=time.perf_counter_ns();objects=[mesh(o) for o in raw['objects']]
    if len({o['id'] for o in objects})!=len(objects):raise ValueError('duplicate_logical_id_in_directory')
    target_id=object_selector(raw,'target_id',raw.get('target','Target'))
    targets=[o for o in objects if o['id']==target_id or o['name']==target_id]
    if len(targets)!=1:raise ValueError('target_not_unique_in_complete_directory')
    target=targets[0];pairs=[]
    for obj in objects:
        if obj is target:continue
        pairs.append(pair_certificate(target,obj,tolerance))
    known=[p for p in pairs if p['surface_distance_qualified']]
    best=min(known,key=lambda p:p['distance_upper_m']) if known else None
    possible=[];complete=False
    if best is not None:
        possible=[p['candidate'] for p in pairs if not p['surface_distance_qualified']
                  or p['distance_lower_m']<=best['distance_upper_m']]
        complete=(len(known)==len(pairs) and possible==[best['candidate']])
    return {'id':raw.get('id',raw.get('name','snapshot')),'qualified_surface_pairs':len(known),
        'candidate_count':len(pairs),'directory_count':len(objects),
        'pairs':pairs,'global_nearest_unsigned':{
            'complete':complete,'nearest_ids':[best['candidate']] if complete else None,
            'possible_nearest_ids':possible,'distance_lower_m':min((p.get('distance_lower_m',0.) for p in pairs),default=None),
            'distance_upper_m':best['distance_upper_m'] if best else None,
            'semantics':'global unsigned triangle-surface distance, not nearest separated or all penetrations',
            'tie_policy':'unique winner only if its certified upper is below every other lower; unresolved ties stay incomplete'},
        'elapsed_prepare_ns':time.perf_counter_ns()-started,'snapshot_geometry_sha256':digest(raw)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,default=HERE/'FIXTURES.json')
    parser.add_argument('--output',type=Path,default=HERE/'ORACLE.json');parser.add_argument('--tolerance-m',type=float,default=1e-6)
    args=parser.parse_args()
    if args.input.is_dir():
        files=sorted(p for p in args.input.glob('*.json') if p.name!='BUILD_COMPLETE.json')
        source={'snapshots':[json.loads(p.read_bytes()) for p in files]}
        inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files};blob=canonical(inputs)
    else:
        blob=args.input.read_bytes();source=json.loads(blob);inputs={str(args.input):hashlib.sha256(blob).hexdigest()}
        if isinstance(source,dict) and 'objects' in source:source={'snapshots':[source]}
    rows=source.get('snapshots',source.get('fixtures',source)) if isinstance(source,dict) else source
    if isinstance(rows,dict):rows=[dict(value,id=key) for key,value in rows.items()]
    if not isinstance(rows,list):raise ValueError('snapshot_list_required')
    started=time.perf_counter_ns();certificates=[]
    for row in rows:
        try:certificates.append(snapshot_certificate(row,args.tolerance_m))
        except (ValueError,AssertionError,KeyError,TypeError,IndexError) as exc:
            certificates.append({'id':row.get('id','unknown'),'qualified':False,'error':type(exc).__name__+': '+str(exc)})
    result={'schema':'scale-diag-independent-worldmesh-oracle-v1','input_sha256':hashlib.sha256(blob).hexdigest(),
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'input_files_sha256':inputs,
        'tolerance_m':args.tolerance_m,'snapshots':certificates,'prepare_elapsed_ns':time.perf_counter_ns()-started,
        'new_product_calls':0,'new_native_benchmark_calls':0,'new_Blender_runs':0,'model_calls':0,
        'limits':['distance certificate covers separated represented triangle surfaces only',
            'solid qualification is restricted to validated closed simple rectilinear prisms',
            'unknown/unqualified fields remain unverified, never successful task answers',
            'input world arrays, all candidates and actual face witnesses are required; generator nominal gaps are unused']}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
    print(json.dumps({'snapshots':len(certificates),'output':str(args.output),'new_test_calls':0}))


if __name__=='__main__':main()
