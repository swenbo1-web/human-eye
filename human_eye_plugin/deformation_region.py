"""Bounded exact current-world region membership for already-validated sources.

Membership is exact for rational affine expressions of the supplied binary
numbers. It is not a physical uncertainty bound, visibility or damage judgment.
Only a complete source consumer may supply the internal geometry proof.
"""
import copy,math
from fractions import Fraction as Q
from . import rig_pose as r

MAX_BITS=16384
MAX_VERTICES=256
MAX_TRIANGLES=256
MAX_DETAILS=4
COORDINATE_MODEL='exact_rational_affine_from_binary_inputs'
SELECTION_RULE='closed_current_triangle_hull_intersects_box'
DETAIL_POLICY='extrema_witnesses_then_smallest_unknown_then_remaining_ids'
MEMBERSHIP_FIELDS={'schema','source_sha256','region','matched_triangle_indices','triangles_scanned',
    'vertices_transformed','membership_complete','coordinate_model','selection_rule'}


def need(value,reason):r.require(value,'deformation_region_'+reason)


def finite(value,maximum):
    # Bound integers before any conversion to float, including hostile huge ints.
    return type(value) is int and abs(value)<=maximum or type(value) is float and math.isfinite(value) and abs(value)<=maximum


def region_value(value):
    need(type(value) is dict and set(value)=={'kind','coordinate_space','bounds'},'region_fields')
    need(value['kind']=='closed_aabb' and value['coordinate_space']=='current_world_m','region_kind')
    bounds=value['bounds']
    need(type(bounds) is list and len(bounds)==2 and all(type(v) is list and len(v)==3 and all(finite(x,1e9) for x in v) for v in bounds),'region_bounds')
    need(all(bounds[0][k]<bounds[1][k] for k in range(3)),'region_extent');return value


def bind_selection(proof,selection,*,deadline_ns):
    r.check_time(deadline_ns)
    need(type(selection) is dict and set(selection)=={'schema','source_ref','region'}
        and selection['schema']=='surface-deformation-region-selection-v1','selection_fields')
    ref=selection['source_ref']
    need(type(ref) is dict and set(ref)=={'scene_sha256','rig_object_id','mesh_object_id','frame'}
        and r.hex_text(ref['scene_sha256'],64) and r.text(ref['rig_object_id']) and r.text(ref['mesh_object_id']),'source_fields')
    frame=ref['frame'];need(type(frame) is dict and set(frame)=={'number','subframe'} and type(frame['number']) is int
        and finite(frame['subframe'],1) and 0<=frame['subframe']<1,'frame')
    source=proof['source'];expected=dict(scene_sha256=source['scene_sha256'],rig_object_id=source['object_id'],
        mesh_object_id=source['mesh_identity']['object_id'],frame=source['frame'])
    need(ref==expected,'stale_selection');region_value(selection['region'])
    need(r.hex_text(proof['source_sha256'],64),'proof_shape')
    result=dict(schema='surface-deformation-region-query-v1',expected_source_sha256=proof['source_sha256'],region=copy.deepcopy(selection['region']))
    r.check_time(deadline_ns);return result


def limited(value):
    value=Q(value)
    need(value.numerator.bit_length()<=MAX_BITS and value.denominator.bit_length()<=MAX_BITS,'arithmetic_budget');return value


def clipped(points,low,high,*,deadline_ns):
    """Clip the closed convex hull, retaining even point/segment intersections."""
    polygon=list(points)
    for axis in range(3):
        for bound,sign in ((low[axis],1),(high[axis],-1)):
            r.check_time(deadline_ns)
            if not polygon:return False
            output=[];previous=polygon[-1];before=limited(sign*limited(previous[axis]-bound))
            for current in polygon:
                r.check_time(deadline_ns);after=limited(sign*limited(current[axis]-bound))
                if (before>=0)!=(after>=0):
                    fraction=limited(before/limited(before-after))
                    point=tuple(limited(previous[k]+limited(fraction*limited(current[k]-previous[k]))) for k in range(3))
                    if not output or output[-1]!=point:output.append(point)
                if after>=0 and (not output or output[-1]!=current):output.append(current)
                previous,before=current,after
            if len(output)>1 and output[0]==output[-1]:output.pop()
            # At most 192 entries even without deduplication: 3 * 2**6.
            # This loose bound includes degenerate closed walks without relying
            # on a nonzero polygon area or on its winding orientation.
            need(len(output)<=192,'arithmetic_budget');polygon=output
    r.check_time(deadline_ns);return bool(polygon)


def select(proof,query,*,deadline_ns):
    r.check_time(deadline_ns)
    need(type(query) is dict and set(query)=={'schema','expected_source_sha256','region'}
        and query['schema']=='surface-deformation-region-query-v1' and r.hex_text(query['expected_source_sha256'],64),'query_fields')
    need(type(proof) is dict and r.hex_text(proof.get('source_sha256'),64),'proof_shape')
    need(query['expected_source_sha256']==proof['source_sha256'],'stale_source');region_value(query['region'])
    current=proof.get('current');triangles=proof.get('triangles');world=proof.get('world');unit=proof.get('unit')
    need(type(current) is list and 1<=len(current)<=MAX_VERTICES and type(triangles) is list and 1<=len(triangles)<=MAX_TRIANGLES,'mesh_budget')
    need(type(world) is list and len(world)==4 and all(type(row) is list and len(row)==4 and all(finite(x,1e12) for x in row) for row in world)
        and world[3]==[0,0,0,1] and finite(unit,1e6) and unit>0,'proof_shape')
    matrix=[[limited(x) for x in row] for row in world];unit=limited(unit)
    low,high=[[limited(x) for x in row] for row in query['region']['bounds']];points=[]
    for point in current:
        r.check_time(deadline_ns)
        need(type(point) is list and len(point)==3 and all(finite(x,10) for x in point),'proof_shape')
        p=[limited(x) for x in point];transformed=[]
        for axis in range(3):
            value=matrix[axis][3]
            for k in range(3):
                r.check_time(deadline_ns);value=limited(value+limited(matrix[axis][k]*p[k]))
            transformed.append(limited(value*unit))
        points.append(tuple(transformed))
    members=[]
    for index,tri in enumerate(triangles):
        r.check_time(deadline_ns)
        need(type(tri) is list and len(tri)==3 and all(type(i) is int and 0<=i<len(points) for i in tri) and len(set(tri))==3,'proof_shape')
        if clipped([points[i] for i in tri],low,high,deadline_ns=deadline_ns):members.append(index)
    result=dict(schema='surface-deformation-region-membership-v1',source_sha256=proof['source_sha256'],region=copy.deepcopy(query['region']),
        matched_triangle_indices=members,triangles_scanned=len(triangles),vertices_transformed=len(points),membership_complete=True,
        coordinate_model=COORDINATE_MODEL,selection_rule=SELECTION_RULE)
    r.check_time(deadline_ns);return result


def summarize(membership,rows,*,deadline_ns):
    r.check_time(deadline_ns)
    need(type(membership) is dict and set(membership)==MEMBERSHIP_FIELDS and membership['schema']=='surface-deformation-region-membership-v1'
        and r.hex_text(membership['source_sha256'],64) and membership['membership_complete'] is True
        and membership['coordinate_model']==COORDINATE_MODEL and membership['selection_rule']==SELECTION_RULE,'membership')
    region_value(membership['region']);scanned=membership['triangles_scanned'];members=membership['matched_triangle_indices']
    need(type(scanned) is int and 1<=scanned<=MAX_TRIANGLES and type(membership['vertices_transformed']) is int
        and 1<=membership['vertices_transformed']<=MAX_VERTICES and type(members) is list and all(type(i) is int and 0<=i<scanned for i in members)
        and members==sorted(set(members)),'membership')
    need(type(rows) is list and len(rows)==scanned,'rows')
    for index,row in enumerate(rows):
        r.check_time(deadline_ns)
        need(type(row) is dict and type(row.get('triangle')) is int and row['triangle']==index
            and row.get('state') in ('measured','collapsed','unknown'),'rows')
    selected=[rows[i] for i in members];measurable=[];unknown=[];counts=dict(measured=0,collapsed=0,unknown=0);reasons={}
    for row in selected:
        r.check_time(deadline_ns);state=row['state'];counts[state]+=1
        if state=='unknown':
            need(r.text(row.get('reason')) and row.get('principal_stretches') is None and row.get('area_ratio') is None,'rows')
            unknown.append(row);reasons[row['reason']]=reasons.get(row['reason'],0)+1
        else:
            stretches=row.get('principal_stretches');area=row.get('area_ratio')
            need(type(stretches) is list and len(stretches)==2 and all(finite(x,1e308) for x in stretches)
                and stretches[0]>=stretches[1]>=0 and finite(area,1e308) and area>=0,'rows');measurable.append(row)
    extrema={};details=[]
    for name,key,maximum in (('max_principal_stretch',lambda v:v['principal_stretches'][0],True),
            ('min_principal_stretch',lambda v:v['principal_stretches'][1],False),('min_area_ratio',lambda v:v['area_ratio'],False),
            ('max_area_ratio',lambda v:v['area_ratio'],True)):
        r.check_time(deadline_ns)
        witness=min(measurable,key=lambda row:((-key(row) if maximum else key(row)),row['triangle'])) if measurable else None
        extrema[name]=None if witness is None else dict(triangle=witness['triangle'],value=key(witness))
        if witness is not None and witness['triangle'] not in details:details.append(witness['triangle'])
    for index in ([unknown[0]['triangle']] if unknown else [])+members:
        r.check_time(deadline_ns)
        if len(details)>=MAX_DETAILS:break
        if index not in details:details.append(index)
    result=dict(schema='surface-deformation-region-result-v1',source_sha256=membership['source_sha256'],region=copy.deepcopy(membership['region']),
        status='empty' if not members else 'partial' if unknown else 'observed',membership_complete=True,
        matched_triangle_indices=members[:],triangles_scanned=scanned,vertices_transformed=membership['vertices_transformed'],triangles_total=len(members),
        triangles_measured=counts['measured'],triangles_unknown=counts['unknown'],triangles_collapsed=counts['collapsed'],unknown_reasons=dict(sorted(reasons.items())),
        metric_extrema=extrema,extrema_scope='measured_and_collapsed_members_only',all_members_measurable=bool(members) and not unknown,
        triangles=[copy.deepcopy(rows[i]) for i in details],details_omitted=len(members)-len(details),detail_policy=DETAIL_POLICY,
        metric_scope='whole_original_triangles_not_clipped_integrals',coordinate_model=COORDINATE_MODEL,selection_rule=SELECTION_RULE)
    r.check_time(deadline_ns);return result
