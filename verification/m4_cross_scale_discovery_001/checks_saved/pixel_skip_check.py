"""Prove each saved skipped direction's integer bound by outward arithmetic."""

from fractions import Fraction as F
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'oracle'))
import check_saved as shared


class Interval:
    def __init__(self,low,high=None):
        self.low,self.high = F(low),F(low if high is None else high)

    @staticmethod
    def rounded(low,high):
        a,b = float(low),float(high)
        if F(a)>low:
            a = math.nextafter(a,-math.inf)
        if F(b)<high:
            b = math.nextafter(b,math.inf)
        return Interval(a,b)

    def __add__(self,other):
        other = other if isinstance(other,Interval) else Interval(other)
        return self.rounded(self.low+other.low,self.high+other.high)

    __radd__ = __add__

    def __neg__(self):
        return Interval(-self.high,-self.low)

    def __sub__(self,other):
        return self + -(other if isinstance(other,Interval) else Interval(other))

    def __rsub__(self,other):
        return Interval(other)+-self

    def __mul__(self,other):
        other = other if isinstance(other,Interval) else Interval(other)
        values = [a*b for a in (self.low,self.high) for b in (other.low,other.high)]
        return self.rounded(min(values),max(values))

    __rmul__ = __mul__

    def __truediv__(self,other):
        other = other if isinstance(other,Interval) else Interval(other)
        if other.low<=0<=other.high:
            raise ValueError('unresolved_division_interval')
        values = [a/b for a in (self.low,self.high) for b in (other.low,other.high)]
        return self.rounded(min(values),max(values))


def projection(pose,point):
    gamma,tiny = F(16,2**53-16),F(16,2**1074)
    homogeneous = tuple(point)+(F(1),)
    camera = [sum(F(a)*b for a,b in zip(row,homogeneous)) for row in pose['view_matrix']]
    errors = [gamma*sum(abs(F(a)*b) for a,b in zip(row,homogeneous))+tiny for row in pose['view_matrix']]
    clip = []
    for row in pose['projection_matrix']:
        exact = sum(F(a)*b for a,b in zip(row,camera))
        propagated = sum(abs(F(a))*b for a,b in zip(row,errors))
        error = propagated+gamma*sum(abs(F(a))*(abs(b)+c) for a,b,c in zip(row,camera,errors))+tiny
        clip.append(Interval(exact-error,exact+error))
    if any(value.low<=-1 or value.high>=1 for value in clip[:3]):
        raise ValueError('skip_requires_strict_unclipped_source')
    return (clip[0]+1)*511/2,(1-clip[1])*511/2


def exclude_outside_samples(mesh,faces,pose,certificate,audit):
    ranges = certificate['pixel_index_ranges']
    count = math.prod(max(0,b-a+1) for a,b in ranges)
    audit.check(count==certificate['upper_bound']<16 and certificate['status']=='bounded'
                and certificate['actual_observation'] is False, 'predicted_bound_strictly_below_threshold')
    reported = certificate['source_triangles']
    audit.check([row['source_triangle_index'] for row in reported]==faces, 'all_region_source_triangle_certificates')
    screens = {index:projection(pose,tuple(F(value) for value in mesh['vertices'][index]))
               for face in faces for index in mesh['faces'][face]}
    exclusions = 0
    for face_index in faces:
        a,b,c = [screens[index] for index in mesh['faces'][face_index]]
        area = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        audit.check(area.low>0 or area.high<0, 'independently_nondegenerate_screen_triangle')
        low = [max(0,math.floor(min(point[axis].low for point in (a,b,c)))) for axis in (0,1)]
        high = [min(511,math.ceil(max(point[axis].high for point in (a,b,c)))) for axis in (0,1)]
        for iy in range(low[1],high[1]+1):
            for ix in range(low[0],high[0]+1):
                if ranges[0][0]<=ix<=ranges[0][1] and ranges[1][0]<=iy<=ranges[1][1]:
                    continue
                x,y = F(2*ix+1,2),F(2*iy+1,2)
                w0 = ((b[0]-x)*(c[1]-y)-(b[1]-y)*(c[0]-x))/area
                w1 = ((c[0]-x)*(a[1]-y)-(c[1]-y)*(a[0]-x))/area
                w2 = 1-w0-w1
                audit.check(any(weight.high<F(-1e-10) for weight in (w0,w1,w2)), 'outside_claimed_integer_bound_rejected_by_actual_barycentric_graph')
                exclusions += 1
    return dict(pixel_center_upper=count,outside_source_triangle_samples_excluded=exclusions,
                method='gamma16 two-stage affine error then directed binary64 interval screen/barycentric operation graph',
                original_raster_edge_threshold=-1e-10,actual_observation=False)


def evaluate(session,call_index=1):
    audit = shared.Audit()
    slot = audit.read(session/'SLOT_RESULT.json')
    install = audit.read(slot['run_binding_path'])
    records = [json.loads(line) for line in audit.file(session/'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    public = records[call_index-1]
    full = audit.read(public['producer_archive']['path'],public['producer_archive']['sha256'],session)
    captures,_ = shared.decode_captures(session,install,audit)
    capture = shared.current_capture(captures,full['binding'],audit)
    task = full['facts']['region_task']
    scopes = {scope['scope_id']:scope for scope in full['scopes']}
    global_scope = scopes['global']
    frames = [frame for frame in full['constructed_frames'] if frame['scope_id']=='global']
    audit.check([frame['view_name'] for frame in frames]==['SCENE'], 'only_global_SCENE_actually_constructed')
    skipped = global_scope['skipped_views']
    audit.check({row['view_name'] for row in skipped}==set(shared.PIXELS.ORDER)-{'SCENE'} and len(skipped)==5,
                'five_distinct_unconstructed_global_directions')
    roi_rows = {row['roi_id']:row for row in task['rows']}
    views = {pose['name']:pose for pose in global_scope['binding']['camera_specification']['views']}
    proofs = []
    for item in skipped:
        audit.check(item['actual_observation'] is False and item['reason']=='pixel_upper_bound_below_readability', 'skip_is_prediction')
        observed = {row['view_name'] for row in global_scope['facts']['observations']}
        audit.check(item['view_name'] not in observed, 'skipped_direction_has_no_fabricated_observation')
        bounded = {row['roi_id']:row for row in item['regions']}
        non_candidates = {row['roi_id']:row for row in item['geometric_non_candidates']}
        audit.check(set(bounded).isdisjoint(non_candidates) and set(bounded)|set(non_candidates)==set(roi_rows),
                    'every_unresolved_task_region_has_explicit_skip_disposition')
        row_proofs = []
        for roi,certificate in bounded.items():
            row = roi_rows[roi]
            audit.check(row['object_name'] in ('Obj_02','Obj_09'), 'only_open_geometry_candidates_bounded')
            mesh = capture['meshes'][row['object_index']]
            row_proofs.append(dict(roi_id=roi,object_name=row['object_name'],**exclude_outside_samples(
                mesh,row['source_triangle_indices'],views[item['view_name']],certificate,audit)))
        for roi,description in non_candidates.items():
            audit.check(roi_rows[roi]['object_name']=='Obj_06'
                        and description['classification']=='positive_area_occlusion', 'independent_known_strict_cover_non_candidate')
        proofs.append(dict(view_name=item['view_name'],regions=row_proofs))
    return dict(schema='cross-scale-skipped-view-independent-certificate-v1',passed_checked_scope=True,
                session=str(session),call_index=call_index,proofs=proofs,check_count=len(audit.checks),checks=audit.checks,
                input_pins=list(audit.pins.values())+[shared.expected.EXACT.pin(__file__)],
                new_operations=dict(Blender=0,MCP=0,raster=0,model=0))


if __name__=='__main__':
    session = Path(sys.argv[1])
    output = Path(sys.argv[2])
    call_index = int(sys.argv[3]) if len(sys.argv)>3 else 1
    result = evaluate(session,call_index)
    with output.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=True,checks=result['check_count'],skipped_views=len(result['proofs']))))
