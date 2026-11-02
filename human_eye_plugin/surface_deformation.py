"""Read-only triangle surface stretches. Geometry facts never imply damage."""
import math
from fractions import Fraction as Q
from . import skin_source as source
r=source.r
QUALITY_FLOOR=2**-20
ROUND32=2**-24
SUBNORMAL32=2**-149
MAX_STRETCH_ERROR=.01
MAX_AREA_ERROR=.02


def sub(a,b):return [x-y for x,y in zip(a,b)]
def dot(a,b):return math.fsum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def norm(a):return math.hypot(*a)
def exact_zero(points,cache):
    values=[]
    for p in points:
        key=tuple(p)
        if key not in cache:cache[key]=[Q(x) for x in p]
        values.append(cache[key])
    a,b,c=values;return not any(cross(sub(b,a),sub(c,a)))
def coordinate_margin(points):return 8*(ROUND32*max(abs(x) for p in points for x in p)+SUBNORMAL32)


def triangle_facts(original,current,*,unweighted=(),deadline_ns,_rational_cache=None):
    r.check_time(deadline_ns)
    r.require(all(type(ps) is list and len(ps)==3 and all(type(p) is list and len(p)==3 and all(r.finite(v) for v in p) for p in ps)
        for ps in (original,current)),'deformation_triangle_shape')
    e1=sub(original[1],original[0]);e2=sub(original[2],original[0]);d1=sub(current[1],current[0]);d2=sub(current[2],current[0])
    a0=norm(cross(e1,e2));a1=norm(cross(d1,d2));longest=max(norm(e1),norm(e2),norm(sub(original[2],original[1])))
    cache={} if _rational_cache is None else _rational_cache
    reference_zero=exact_zero(original,cache);current_zero=exact_zero(current,cache)
    result=dict(state='unknown',reason=None,reference_geometry='zero_area' if reference_zero else 'nonzero_area',
        current_geometry='zero_area' if current_zero else 'nonzero_area',unweighted_vertices=list(unweighted),
        principal_stretches=None,engineering_strains=None,area_ratio=None,principal_directions=None,
        estimated_stretch_error=None,estimated_area_ratio_error=None,change_detectable=None)
    def finish():r.check_time(deadline_ns);return result
    if reference_zero:result['reason']='original_zero_area';return finish()
    if unweighted:result['reason']='unweighted_vertex_source';return finish()
    q0=coordinate_margin(original);q1=coordinate_margin(current)
    if longest<=16*q0:result['reason']='reference_below_coordinate_resolution';return finish()
    if a0<=QUALITY_FLOOR*longest*longest:result['reason']='reference_ill_conditioned';return finish()
    length=norm(e1);height=a0/length
    if height<=16*q0:result['reason']='reference_height_below_resolution';return finish()
    u0=[x/length for x in e1];projection=dot(e2,u0)
    u1=[(e2[k]-projection*u0[k])/height for k in range(3)]
    f0=[x/length for x in d1];f1=[(d2[k]-d1[k]*projection/length)/height for k in range(3)]
    c00=dot(f0,f0);c11=dot(f1,f1);c01=dot(f0,f1)
    largest=max(0.,(c00+c11+math.hypot(c00-c11,2*c01))/2)
    high=math.sqrt(largest);low=norm(cross(f0,f1))/high if high else 0.;area=a1/a0
    if current_zero:low=0.;area=0.
    error=32*(q1+max(1.,high)*q0)/height
    area_error=(high+low)*error+error*error
    result.update(estimated_stretch_error=error,estimated_area_ratio_error=area_error)
    if not all(math.isfinite(v) for v in (high,low,area,error,area_error)) or error>MAX_STRETCH_ERROR or area_error>MAX_AREA_ERROR:
        result['reason']='metric_resolution_insufficient';return finish()
    if not current_zero and (low<=4*error or norm(cross(d1,d2))<=QUALITY_FLOOR*max(norm(d1),norm(d2),norm(sub(current[2],current[1])))**2):
        result['reason']='current_near_degenerate';return finish()
    directions=None
    if high-low>4*error:
        angle=.5*math.atan2(2*c01,c00-c11);cs=math.cos(angle);sn=math.sin(angle)
        directions=[]
        for a,b,value in ((cs,sn,high),(-sn,cs,low)):
            directions.append(dict(original_local_axis=[a*u0[k]+b*u1[k] for k in range(3)],
                current_local_axis=[(a*f0[k]+b*f1[k])/value for k in range(3)] if value>4*error else None))
    result.update(state='collapsed' if current_zero else 'measured',reason='current_zero_area' if current_zero else None,
        principal_stretches=[high,low],engineering_strains=[high-1,low-1],area_ratio=area,principal_directions=directions,
        change_detectable=current_zero or max(abs(high-1),abs(low-1))>error or abs(area-1)>area_error)
    return finish()


def analyze(packet,*,deadline_ns):
    proof=source.validate(packet,deadline_ns=deadline_ns);mesh=packet['mesh'];original=mesh['vertices'];current=mesh['evaluated_vertices'];unit=proof['payload']['unit_scale_m']
    unweighted=set(proof['unweighted']);rows=[];rational_cache={}
    for index,tri in enumerate(mesh['triangles']):
        r.check_time(deadline_ns);facts=triangle_facts([original[i] for i in tri],[current[i] for i in tri],
            unweighted=[i for i in tri if i in unweighted],deadline_ns=deadline_ns,_rational_cache=rational_cache)
        points=[r.point(mesh['object_matrix_world'],current[i]) for i in tri]
        facts.update(triangle=index,vertices=tri[:],region_kind='original_triangle',
            centroid_world_m=[math.fsum(p[k] for p in points)*unit/3 for k in range(3)],
            bounds_world_m=[[min(p[k] for p in points)*unit for k in range(3)],[max(p[k] for p in points)*unit for k in range(3)]])
        rows.append(facts)
    def rank(v):
        change=max([abs(x-1) for x in v['principal_stretches']]+[abs(v['area_ratio']-1)]) if v['principal_stretches'] is not None else 0
        return (0 if v['state']=='collapsed' else 1 if v['state']=='unknown' else 2,-change,v['triangle'])
    ranked=sorted(rows,key=rank);unknown=[v for v in rows if v['state']=='unknown'];collapsed=[v for v in rows if v['state']=='collapsed']
    result=dict(schema='surface-deformation-diagnostic-v1',source_sha256=packet['source_sha256'],assessment='geometric_facts_not_damage',
        source=dict(packet['rig']['identity'],source_sha256=packet['source_sha256'],scene_sha256=packet['scene_sha256'],rig_sha256=packet['rig']['rig_sha256'],
            mesh_identity=mesh['identity'],frame=proof['payload']['frame']),
        source_summary=dict(vertices_total=len(original),triangles_total=len(rows),bones_total=len(packet['rig']['payload']['bones']),
            weighted_vertices_total=len(original)-len(unweighted),unweighted_vertices_total=len(unweighted)),
        coordinate_precision_model='binary32 coordinate quantization plus conservative binary64 arithmetic margins; not a certified physical bound',
        status='partial' if unknown else 'observed',triangles_total=len(rows),triangles_measured=sum(v['state']=='measured' for v in rows),
        triangles_collapsed=len(collapsed),triangles_unknown=len(unknown),original_zero_area_total=sum(v['reference_geometry']=='zero_area' for v in rows),
        triangles=ranked[:16],triangles_omitted=max(0,len(rows)-16),
        unknown_reasons={reason:sum(v['reason']==reason for v in unknown) for reason in sorted({v['reason'] for v in unknown})},
        damage_classification='not_inferred',execution_authority=False,geometry_setters=0,original_file_saved=False,
        not_checked=['volume_Jacobian','inversion_vs_3D_rotation','self_contact','intended_shape_quality','repair','visibility'])
    r.check_time(deadline_ns);return result
