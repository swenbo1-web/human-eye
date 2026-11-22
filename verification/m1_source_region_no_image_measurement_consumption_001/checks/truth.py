"""Reconstruct the two exact distances from the sealed Blender mesh source."""

from fractions import Fraction as F
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from runpy import run_path


NS = Path(__file__).resolve().parents[1]
V = NS.parent
ASSET = Path('D:/he_m4_cross_scale_live_task_001/fixture/main.blend')
REOPENED = ASSET.with_name('READBACK_AFTER_RELOAD.json')
PRIOR_RUN = Path('D:/he_m4_cross_scale_live_task_formal_001/slots/P1')
PRIOR_TERMINAL = PRIOR_RUN/'TERMINAL_SOURCE.json'
ASSET_SHA = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
REOPENED_SHA = '836219a6cd00f81dc658b0277c4dfa82cfafba8d094570ec797dbc5eb8e12dee'
PRIOR_TERMINAL_SHA = 'aae8ad86e3c79032346853360d212c4614c71d20cc50b7b1375786860166e927'
MEMBERSHIP = V/'m5_observe_measure_001/oracle.py'
DOMAIN = 'zero_based_object_local_current_evaluated_capture_triangle_rows'
TARGET, REFERENCE = 'M15', 'M14'
SELECTIONS = {'selected':(6,7), 'whole':tuple(range(12))}
THRESHOLD = F(2)
REPORT_METRES = F(1,20000)
REPORT_DIRECTION = 5e-5
POINT = run_path(str(MEMBERSHIP))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path, expected=None):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    actual = sha256(raw).hexdigest()
    require(expected is None or actual==expected,'frozen_bytes_changed/'+path.name)
    return {'path':path.as_posix(),'bytes':len(raw),'sha256':actual}


def fingerprint(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def vector(values):
    require(type(values) in (tuple,list) and len(values)==3
            and all(type(v) in (str,int,float,F) for v in values),'three_world_coordinates_required')
    return tuple(F(v) for v in values)


def meshes(packet):
    rows = packet['objects']
    result = {row['name']:row for row in rows}
    require(len(rows)==len(result)==21 and TARGET in result and REFERENCE in result,
            'full_owned_current_object_roster_required')
    return result


def verify_source(source, first=None):
    """Validate actual order, geometry and display against the frozen asset readback."""
    asset = source['source']
    require(asset['asset_sha256']==ASSET_SHA and asset['source_index_domain']==DOMAIN
            and asset['scale_length']==1 and asset['unit_settings']['system']=='METRIC'
            and asset['frame']==1 and asset['subframe']==0,'current_asset_frame_or_world_units_changed')
    pin(REOPENED,REOPENED_SHA)
    reopened = read(REOPENED)
    formal = run_path(str(V/'m4_cross_scale_live_task_formal_001/scoring/formal.py'))
    require(formal['verified_arrays'](source if first is None else first,source,reopened)==21,
            'unchanged_native_evaluated_current_geometry_required')
    rows = meshes(source)
    counts = {'objects':len(rows),
              'vertices':sum(len(row['evaluated']['vertices_world_m']) for row in rows.values()),
              'triangles':sum(len(row['evaluated']['triangles']) for row in rows.values())}
    require(counts=={'objects':21,'vertices':148,'triangles':184}
            and len({row['object_id'] for row in rows.values()})==21
            and all(row['visible_get'] is True for row in rows.values()),'world_geometry_counts_or_current_display_changed')
    return {'counts':counts,'asset_sha256':asset['asset_sha256'],'same_saved_frame':True,
            'ordered_geometry_sha256':fingerprint({name:row['evaluated'] for name,row in rows.items()})}


def source_faces(source, name, indices=None):
    raw = meshes(source)[name]['evaluated']
    points = tuple(vector(value) for value in raw['vertices_world_m'])
    faces = tuple(tuple(row) for row in raw['triangles'])
    ids = tuple(range(len(faces))) if indices is None else tuple(indices)
    require(ids and len(ids)==len(set(ids)) and all(type(i) is int and 0<=i<len(faces) for i in ids),
            'invalid_current_object_local_source_index/'+name)
    return points,faces,ids


def member(point, surface, tolerance=F(0)):
    vertices,faces,indices = surface
    nearest = [(i,POINT['triangle_distance_squared'](point,tuple(vertices[j] for j in faces[i]))) for i in indices]
    exact = [i for i,distance in nearest if distance==0]
    close = [i for i,distance in nearest if distance<=tolerance*tolerance]
    vertex_ids = sorted({j for i in exact for j in faces[i] if vertices[j]==point})
    return {'exact_source_triangle_indices':exact,'source_triangle_indices_within_tolerance':close,
            'exact_source_vertex_indices':vertex_ids,'minimum_squared_surface_distance_m2':str(min(d for _,d in nearest))}


def triangle_points(surface):
    points, faces, ids = surface
    return [points[j] for i in ids for j in faces[i]]


def establish(source, scope):
    domain = SELECTIONS[scope]
    sa,sb = source_faces(source,TARGET,domain),source_faces(source,REFERENCE)
    xa,xb = triangle_points(sa),triangle_points(sb)
    a_x,a_z = min(p[0] for p in xa),min(p[2] for p in xa)
    b_x,b_z = max(p[0] for p in xb),max(p[2] for p in xb)
    require(a_x>b_x and a_z>b_z,'axis_separators_not_disjoint')
    dx,dz = a_x-b_x,a_z-b_z
    exact_squared = dx*dx+dz*dz
    require(exact_squared=={'selected':F(153,16),'whole':F(13,16)}[scope],'frozen_distance_lower_bound_changed')
    min_y,max_y = F(1),F(11,4)
    # Coverage along the extremal lines follows from the continuous mesh edges.
    # Each line segment is one edge of a verified triangle, so each y between
    # the endpoints of the shared interval realizes both x and z extrema.
    for surface,x,z in ((sa,a_x,a_z),(sb,b_x,b_z)):
        pts,faces,indices = surface
        require(any(all(pts[j][0]==x and pts[j][2]==z for j in (u,v))
                    and min(pts[u][1],pts[v][1])<=min_y and max(pts[u][1],pts[v][1])>=max_y
                    for i in indices for u,v in zip(faces[i],faces[i][1:]+faces[i][:1])),
                'extremal_lines_do_not_share_continuous_exact_y_interval')
    examples = []
    for y in (F(2),F(3,2)):
        a,b = (a_x,y,a_z),(b_x,y,b_z)
        ma,mb = member(a,sa),member(b,sb)
        require(ma['exact_source_triangle_indices'] and mb['exact_source_triangle_indices'],
                'both_exact_attaining_pairs_require_current_source_triangle_members')
        examples.append({'a':list(map(str,a)),'b':list(map(str,b)),
                         'source_memberships':{'a':ma,'b':mb}})
    distance = sqrt(exact_squared)
    return {'scope':scope,'target':TARGET,'reference':REFERENCE,
            'target_source_triangles':list(domain),'reference_source_triangles':list(sb[2]),
            'separation_xyz_abs_m':[str(dx),'0',str(dz)],'shared_attaining_y_interval_m':[str(min_y),str(max_y)],
            'distance_squared_m2':str(exact_squared),'distance_m':distance,
            'unit_direction_A_to_B':[-float(dx)/distance,0.,-float(dz)/distance],
            'meets_2m':exact_squared>=THRESHOLD*THRESHOLD,'equivalent_attaining_pairs':examples}


def check_measurement(source, scope, item, *, exact=False):
    """Accept equal-distance pairs on either extremal segment, with the correct source faces."""
    expected = establish(source,scope)
    a,b = (vector(item[key]) for key in ('a','b'))
    direction = vector(item['direction_a_to_b'])
    delta = tuple(y-x for x,y in zip(a,b,strict=True))
    measured, squared = float(F(item['distance_m'])),sum(x*x for x in delta)
    metres = F(0) if exact else REPORT_METRES
    numeric_eps = 1e-12 if exact else float(REPORT_METRES)
    pair_error = abs(sqrt(squared)-expected['distance_m'])
    pair_cutoff = 1e-12 if exact else float(REPORT_METRES)*2
    component_eps = 1e-12 if exact else REPORT_DIRECTION
    distance_ok = abs(measured-expected['distance_m'])<=numeric_eps
    direction_ok = all(abs(float(got)-want)<=component_eps
                       for got,want in zip(direction,expected['unit_direction_A_to_B'],strict=True))
    domains = (('a',a,source_faces(source,TARGET,SELECTIONS[scope])),('b',b,source_faces(source,REFERENCE)))
    proof = {label:member(point,surface,metres) for label,point,surface in domains}
    pair_ok = (all(p['source_triangle_indices_within_tolerance'] for p in proof.values())
               and pair_error<=pair_cutoff
               and (not exact or squared==F(expected['distance_squared_m2'])))
    stated = item.get('source_triangle_indices',{})
    faces_ok = all(type(stated.get(side)) is list and stated[side]
                   and all(type(index) is int for index in stated[side])
                   and len(stated[side])==len(set(stated[side]))
                   and set(stated[side])<=set(details['source_triangle_indices_within_tolerance'])
                   for side,details in proof.items())
    return {'scope':scope,'distance_correct':distance_ok,'world_direction_correct':direction_ok,
            'actual_attaining_pair':pair_ok,'stated_source_triangle_membership_correct':faces_ok,
            'pair_distance_m':sqrt(squared),'expected':expected,'reported_memberships':proof}


def frozen_truth():
    source = read(PRIOR_TERMINAL)
    assets = {'blend':pin(ASSET,ASSET_SHA),'reopened':pin(REOPENED,REOPENED_SHA),
              'terminal':pin(PRIOR_TERMINAL,PRIOR_TERMINAL_SHA),'independent_point_membership':pin(MEMBERSHIP)}
    verification = verify_source(source)
    return {'schema':'independent-source-region-clearance-v1','assets':assets,
            'whole_scene':verification,'ordered_pair':[TARGET,REFERENCE],'threshold_m':2,
            'measurements':{scope:establish(source,scope) for scope in SELECTIONS},
            'grade_tolerances':{'scalar_m':str(REPORT_METRES),'direction_component':REPORT_DIRECTION},
            'new_Blender':0,'new_Model':0}


if __name__=='__main__':
    print(json.dumps(frozen_truth(),ensure_ascii=False,allow_nan=False,indent=2))
