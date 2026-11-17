"""Independent saved-geometry, skipped-view and pure numeric review.

No product or author-oracle imports. Selected pure production functions are
extracted for directed controls. Current geometry comes from original WIRE.
"""
import ast
import base64
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import random
from types import SimpleNamespace
import traceback
import zlib

OUT = Path(__file__).resolve().parent
AUTHOR = Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe')
RUN = Path('D:/he_m4_cross_scale_001/sessions')
PRIOR = Path('D:/hefe/verification/fixes/20261116_m4_global_local_qualification_review/geometry/independent_geometry.py')
checks = []
pins = {}


def check(value, label):
    if not value:
        raise AssertionError(label)
    checks.append(label)


def raw(path):
    path = Path(path)
    value = path.read_bytes()
    pins[str(path)] = dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
    return value


def read(path):
    return json.loads(raw(path))


def extract(path, names, env):
    tree = ast.parse(raw(path).decode('utf8'))
    selected = [item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.ClassDef)) and item.name in names]
    check({item.name for item in selected} == set(names), 'all_requested_pure_definitions_found/' + str(path))
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), env)
    return env


G = extract(PRIOR, ['vec', 'sub', 'dot', 'cross', 'canonical_plane', 'components',
    'clip_polygon', 'unobstructed_rectangle'], dict(F=F, math=math, Counter=Counter,
    defaultdict=defaultdict, check=check))
vec, sub, dot, cross = [G[name] for name in ('vec', 'sub', 'dot', 'cross')]


def captures(session):
    resources, output = {}, []
    for folder in sorted((session / 'native/WIRE').glob('[0-9]*')):
        request, response = read(folder / 'REQUEST.bin'), read(folder / 'RESPONSE.bin')
        if request.get('type') != 'execute_code':
            continue
        code = request['params']['code']
        if '_request = _json.loads(' not in code:
            continue
        lines = [line for line in response.get('result', {}).get('result', '').splitlines()
                 if line.startswith('HUMAN_EYE_BLENDER_MCP:')]
        check(response['status'] == 'success' and len(lines) == 1, 'successful_unique_native_packet')
        packet = json.loads(lines[0].split(':', 1)[1])
        check(packet.get('error') is None, 'native_packet_no_error')
        value = packet.get('result')
        if not isinstance(value, dict):
            continue
        for resource in value.get('resources', []):
            identity = resource['id'], resource['revision']
            check(identity not in resources or resources[identity] == resource, 'resource_identity_consistent')
            resources[identity] = resource
        capture = json.loads(json.dumps(value.get('capture', value)))
        if not capture.get('meshes'):
            continue
        for mesh in capture['meshes']:
            reference = mesh.pop('_scene_resource', None)
            if reference is None:
                continue
            source = resources[reference['id'], reference['revision']]
            matrix, scale = reference['matrix'], reference['scale']
            mesh['vertices'] = [[(((matrix[axis][0] * p[0] + matrix[axis][1] * p[1])
                + matrix[axis][2] * p[2]) + matrix[axis][3]) * scale for axis in range(3)]
                for p in source['vertices_local']]
            mesh['faces'] = source['faces']
        output.append(capture)
    return output


class Interval:
    def __init__(self, lo, hi=None):
        self.lo = F(lo)
        self.hi = F(lo if hi is None else hi)

    @staticmethod
    def rounded(lo, hi):
        a, b = float(lo), float(hi)
        if F(a) > lo:
            a = math.nextafter(a, -math.inf)
        if F(b) < hi:
            b = math.nextafter(b, math.inf)
        return Interval(a, b)

    def __neg__(self):
        return Interval(-self.hi, -self.lo)

    def __add__(self, other):
        other = other if isinstance(other, Interval) else Interval(other)
        return self.rounded(self.lo + other.lo, self.hi + other.hi)

    __radd__ = __add__

    def __sub__(self, other):
        return self + -(other if isinstance(other, Interval) else Interval(other))

    def __rsub__(self, other):
        return Interval(other) + -self

    def __mul__(self, other):
        other = other if isinstance(other, Interval) else Interval(other)
        values = [a * b for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        return self.rounded(min(values), max(values))

    __rmul__ = __mul__

    def __truediv__(self, other):
        other = other if isinstance(other, Interval) else Interval(other)
        if other.lo <= 0 <= other.hi:
            raise ValueError('unresolved_denominator_interval')
        values = [a / b for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        return self.rounded(min(values), max(values))


def project_intervals(pose, point):
    # Two independent four-term error expansions precede the actual scalar
    # screen/barycentric operation graph. No product enclosure is reused.
    p = tuple(point) + (F(1),)
    gamma, tiny = F(16, 2**53 - 16), F(16, 2**1074)
    camera = [sum(F(a) * b for a, b in zip(row, p)) for row in pose['view_matrix']]
    errors = [gamma * sum(abs(F(a) * b) for a, b in zip(row, p)) + tiny
              for row in pose['view_matrix']]
    clip = []
    for row in pose['projection_matrix']:
        center = sum(F(a) * b for a, b in zip(row, camera))
        propagation = sum(abs(F(a)) * b for a, b in zip(row, errors))
        roundoff = gamma * sum(abs(F(a)) * (abs(b) + c)
                               for a, b, c in zip(row, camera, errors)) + tiny
        clip.append(Interval(center - propagation - roundoff, center + propagation + roundoff))
    check(all(v.lo > -1 and v.hi < 1 for v in clip[:3]), 'skipped_source_strictly_inside_clip')
    return (clip[0] + 1) * 511 / 2, (1 - clip[1]) * 511 / 2


def verify_bound(mesh, face_rows, pose, bound):
    ranges = bound['pixel_index_ranges']
    check(bound['status'] == 'bounded' and bound['actual_observation'] is False,
          'skip_bound_is_prediction')
    check(bound['upper_bound'] == math.prod(max(0, b - a + 1) for a, b in ranges)
          and bound['upper_bound'] < 16, 'pixel_integer_count_below_unchanged_16')
    check([row['source_triangle_index'] for row in bound['source_triangles']] == face_rows,
          'every_task_source_triangle_has_bound')
    screens = {i: project_intervals(pose, vec(mesh['vertices'][i]))
               for row in face_rows for i in mesh['faces'][row]}
    exclusions = 0
    for row in face_rows:
        a, b, c = [screens[i] for i in mesh['faces'][row]]
        area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        check(area.lo > 0 or area.hi < 0, 'independent_nonzero_area')
        low = [max(0, math.floor(min(p[k].lo for p in (a, b, c)))) for k in (0, 1)]
        high = [min(511, math.ceil(max(p[k].hi for p in (a, b, c)))) for k in (0, 1)]
        for y_index in range(low[1], high[1] + 1):
            for x_index in range(low[0], high[0] + 1):
                if ranges[0][0] <= x_index <= ranges[0][1] and ranges[1][0] <= y_index <= ranges[1][1]:
                    continue
                x, y = F(2 * x_index + 1, 2), F(2 * y_index + 1, 2)
                w0 = ((b[0] - x) * (c[1] - y) - (b[1] - y) * (c[0] - x)) / area
                w1 = ((c[0] - x) * (a[1] - y) - (c[1] - y) * (a[0] - x)) / area
                w2 = 1 - w0 - w1
                check(any(w.hi < F(-1e-10) for w in (w0, w1, w2)),
                      'outside_claimed_bound_cannot_pass_actual_barycentric_graph')
                exclusions += 1
    return exclusions


def exact_eligible(component, conditions):
    if not component['rectangle']:
        return False
    low, high, threshold = [F(str(conditions[k])) for k in ('area_min_m2', 'area_max_m2', 'normal_z_min')]
    n = component['normal']
    if not low**2 <= component['area_squared'] <= high**2:
        return False
    with localcontext() as ctx:
        ctx.prec = 100
        z = Decimal(n[2]) / Decimal(dot(n, n)).sqrt()
        t = Decimal(threshold.numerator) / Decimal(threshold.denominator)
        return z >= t


def verify_saved():
    records, skip_records, outside, local_proofs = [], 0, 0, 0
    for session in sorted(RUN.iterdir()):
        all_captures = captures(session)
        for path in sorted((session / 'product_full').glob('call_*/SERVICE_RESULT.json')):
            full = read(path)
            task = full.get('facts', {}).get('region_task')
            if task is None:
                continue
            binding = full['binding']
            matches = [c for c in all_captures if c.get('revision') == binding['scene_revision']
                       and c.get('capture_state') == binding['capture_state']]
            check(bool(matches), 'actual_current_capture_found/' + session.name + '/' + path.parent.name)
            check(all(c == matches[0] for c in matches), 'current_capture_unambiguous')
            capture = matches[0]
            objects = [dict(name=m['name'], vertices=list(map(vec, m['vertices'])), triangles=m['faces'])
                       for m in capture['meshes']]
            components = [row for obj in objects for row in G['components'](obj)]
            eligible = [row for row in components if exact_eligible(row, task['conditions'])]
            check(len(objects) == 9 and len(components) == 24, 'independent_full_scene_components')
            check(sum(row['rectangle'] for row in components) == 22, 'independent_rectangle_count')
            check(sum(len(row['faces']) for row in components if not row['rectangle']) == 12,
                  'unsupported_triangles_retained')
            expected = {(row['object'], tuple(row['faces'])) for row in eligible}
            actual = {(row['object_name'], tuple(row['source_triangle_indices'])) for row in task['rows']}
            check(expected == actual, 'exact_task_eligible_set')
            by_name = {o['name']: o for o in objects}
            comp_by_key = {(row['object'], tuple(row['faces'])): row for row in components}
            scopes = {row['scope_id']: row for row in full['scopes']}
            frames = {row['frame_identity']: row for row in full['constructed_frames']}
            for row in task['rows']:
                comp = comp_by_key[row['object_name'], tuple(row['source_triangle_indices'])]
                source = row['source']
                check(source['source_triangle_indices'] == comp['faces'], 'source_rows_match_exact_component')
                check(binding['objects'][source['object_index']]['object_name'] == row['object_name'],
                      'source_object_index_current')
                if row['object_name'] == 'Obj_06':
                    check(row['status'] == 'unknown' and row['complete_witness'] is None
                          and row['reason'] == 'positive_area_occlusion_all_front_views', 'covered_target_unknown')
                    top = next(o for o in objects if o['name'] == 'Obj_04')
                    # Determine cover from geometry rather than trusting the neutral label.
                    boxes = [o for o in objects if len(o['vertices']) == 8 and
                             min(p[2] for p in o['vertices']) == F(9, 8)]
                    check(len(boxes) == 1, 'unique_actual_cover')
                    cover = boxes[0]
                    target = by_name[row['object_name']]
                    global_scope = scopes['global']
                    for pose in global_scope['binding']['camera_specification']['views']:
                        direction = vec(pose['direction_rational'])
                        for p in target['vertices']:
                            ray_t = (F(9, 8) - p[2]) / direction[2]
                            q = tuple(x + ray_t * d for x, d in zip(p, direction))
                            check(ray_t > 0 and all(F(3, 2) < q[k] < F(5, 2) for k in (0, 1)),
                                  'cover_strictly_occludes_entire_task_face')
                    continue
                witness = row['complete_witness']
                check(row['status'] == 'covered' and witness is not None, 'open_task_has_real_witness')
                frame = frames[witness['frame_identity']]
                scope = scopes[witness['scope_id']]
                direction = vec(frame['pose']['direction_rational'])
                target = by_name[row['object_name']]
                tested = G['unobstructed_rectangle'](objects, target, direction, comp['loops'][0])
                check(tested > 0, 'local_witness_full_scene_unobstructed')
                local_proofs += 1
                check(scope['binding']['geometry_identity'] == binding['geometry_identity'],
                      'local_and_global_same_geometry_identity')
            global_scope = scopes['global']
            skipped = global_scope.get('skipped_views', [])
            if skipped and not full['work']['result_cache_hit']:
                check(len(skipped) == 5, 'five_unrendered_global_directions')
                observed = {row['view_name'] for row in global_scope['facts']['observations']}
                check(observed == {'SCENE'}, 'only_SCENE_actual_global_observation')
                task_by_roi = {r['roi_id']: r for r in task['rows']}
                cameras = {p['name']: p for p in global_scope['binding']['camera_specification']['views']}
                for skip in skipped:
                    check(skip['actual_observation'] is False and skip['view_name'] not in observed,
                          'prediction_never_added_as_actual_observation')
                    bounded = {r['roi_id'] for r in skip['regions']}
                    non = {r['roi_id'] for r in skip['geometric_non_candidates']}
                    check(not bounded & non and bounded | non == set(task_by_roi),
                          'all_task_regions_have_skip_or_geometric_non_candidate')
                    for bound in skip['regions']:
                        row = task_by_roi[bound['roi_id']]
                        mesh = capture['meshes'][row['object_index']]
                        outside += verify_bound(mesh, row['source_triangle_indices'], cameras[skip['view_name']], bound)
                    check(all(task_by_roi[r['roi_id']]['object_name'] == 'Obj_06'
                              and r['classification'] == 'positive_area_occlusion'
                              for r in skip['geometric_non_candidates']), 'strict_cover_only_geometric_non_candidate')
                    skip_records += 1
            records.append(dict(session=session.name, call=path.parent.name,
                                eligible=sorted(name for name, faces in expected),
                                cached=full['work']['result_cache_hit'], skipped=len(skipped)))
    check(skip_records == 35, '35_unique_actual_skip_decisions')
    check(outside == 1708, '1708_independent_outside_triangle_sample_exclusions')
    check(len(records) == 13, '13_region_task_requests')
    return dict(requests=records, skipped_views=skip_records, outside_samples=outside,
                complete_local_rectangle_proofs=local_proofs)


def pure_controls():
    env = dict(Fraction=F, math=math, cross=cross, subtract=sub, dot=dot)
    extract(AUTHOR / 'human_eye_plugin/blender_host.py', ['_observation_affine_interval'], env)
    extract(AUTHOR / 'human_eye_plugin/query_policy.py', ['validate_region_task'], env)
    extract(AUTHOR / 'human_eye_plugin/active_observation_region_task.py',
            ['region_matches', '_outward', '_subtract_interval', '_multiply_interval', '_float_upper',
             '_screen_intervals', 'pixel_center_upper_bound'], env)
    matcher, validate, bounder = [env[k] for k in ('region_matches', 'validate_region_task', 'pixel_center_upper_bound')]
    normal_checks = 0
    for q, r in ((1, 0), (-1, 0), (0, 1), (3, 4), (-3, 4), (4, 3), (-4, 3), (2, 3)):
        vertices = ((F(0), F(0), F(0)), (F(1), F(0), F(0)),
                    (F(1), F(q), F(r)), (F(0), F(q), F(r)))
        region = SimpleNamespace(vertices=vertices)
        normal = cross(sub(vertices[1], vertices[0]), sub(vertices[3], vertices[0]))
        squared = dot(normal, normal)
        for threshold in (-1, -.8000000000000002, -.8, -.7999999999999999, -.6, 0, .6,
                          .7999999999999999, .8, .8000000000000002, 1):
            c = validate(dict(area_min_m2=0, area_max_m2=10, normal_z_min=threshold))
            with localcontext() as ctx:
                ctx.prec = 100
                expected = Decimal(normal[2]) / Decimal(squared).sqrt() >= Decimal(str(threshold))
            check(matcher(region, c) == expected, 'pure_signed_unit_normal_threshold')
            normal_checks += 1
    for bad in (True, False, float('nan'), float('inf'), '0.1', None):
        try:
            validate(dict(area_min_m2=bad, area_max_m2=1, normal_z_min=0))
        except ValueError:
            pass
        else:
            raise AssertionError('invalid_numeric_threshold_accepted')
        check(True, 'bad_threshold_rejected')
    check(validate(dict(area_min_m2=0., area_max_m2=1., normal_z_min=-0.)) ==
          dict(area_min_m2=0, area_max_m2=1, normal_z_min=0), 'integer_float_query_normalization')
    region = SimpleNamespace(vertices=((F(0), F(0), F(0)), (F(1, 10), F(0), F(0)),
        (F(1, 10), F(1), F(0)), (F(0), F(1), F(0))))
    check(matcher(region, validate(dict(area_min_m2=.1, area_max_m2=.1, normal_z_min=1))),
          'shortest_decimal_threshold_contract_point_one')
    pose = dict(projection='orthographic', size_px=[512, 512],
        view_matrix=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,-2.],[0.,0.,0.,1.]],
        projection_matrix=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,.25,0.],[0.,0.,0.,1.]])
    rng = random.Random(2026111701)
    bounded, unknown, accepted_samples = 0, 0, 0
    for index in range(300):
        cx = rng.randrange(20, 490) + rng.choice((0., .5, .5 - 2**-40, .5 + 2**-40))
        cy = rng.randrange(20, 490) + rng.choice((0., .5, .5 - 2**-40, .5 + 2**-40))
        half_x = rng.choice((.49, .5, .5000000000001, 1.49, 1.5, 1.51, 2.01, .0000001))
        half_y = rng.choice((.49, .5, .5000000000001, 1.49, 1.5, 1.51, 2.01, .0000001))
        angle = rng.choice((0., .2, .7853981633974483, 1.4))
        u = half_x * math.cos(angle), half_x * math.sin(angle)
        v = -half_y * math.sin(angle), half_y * math.cos(angle)
        xy = [(cx + a*u[0] + b*v[0], cy + a*u[1] + b*v[1]) for a,b in ((-1,-1),(1,-1),(1,1),(-1,1))]
        verts = tuple((F(2*x/511-1), F(1-2*y/511), F(0)) for x,y in xy)
        faces = ((0,1,2),(0,2,3))
        region = SimpleNamespace(roi_id='fuzz', object_index=0, triangle_indices=(0,1), vertices=verts)
        answer = bounder(region, ((verts, faces, None, ''),), pose)
        if answer['status'] == 'unknown':
            unknown += 1
            continue
        bounded += 1
        actual_xy = [((float(p[0])+1)*511/2, (1-float(p[1]))*511/2) for p in verts]
        inside_set = set()
        for face in faces:
            a,b,c = [actual_xy[i] for i in face]
            area = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(area) <= 2**-52 * 512**2 * 8:
                continue
            lo = [max(0, math.floor(min(p[k] for p in (a,b,c)))) for k in (0,1)]
            hi = [min(511, math.ceil(max(p[k] for p in (a,b,c)))) for k in (0,1)]
            for iy in range(lo[1], hi[1]+1):
                for ix in range(lo[0], hi[0]+1):
                    x,y = ix+.5, iy+.5
                    w0 = ((b[0]-x)*(c[1]-y)-(b[1]-y)*(c[0]-x))/area
                    w1 = ((c[0]-x)*(a[1]-y)-(c[1]-y)*(a[0]-x))/area
                    if min(w0,w1,1-w0-w1) >= -1e-10:
                        check(all(lo <= value <= hi for value, (lo,hi) in zip((ix,iy), answer['pixel_index_ranges'])),
                              'direct_scalar_accepted_sample_inside_product_bound')
                        inside_set.add((ix,iy))
        check(len(inside_set) <= answer['upper_bound'], 'direct_scalar_count_within_upper_bound')
        accepted_samples += len(inside_set)
    # Directed fallback controls call only the extracted bound function.
    verts = tuple((F(x), F(y), F(0)) for x,y in ((-1,-.1),(.1,-.1),(.1,.1),(-1,.1)))
    region = SimpleNamespace(roi_id='clip', object_index=0, triangle_indices=(0,1), vertices=verts)
    check(bounder(region, ((verts,faces,None,''),), pose)['status'] == 'unknown', 'clipped_target_falls_back')
    changed = json.loads(json.dumps(pose))
    changed['projection_matrix'][3][0] = .1
    check(bounder(region, ((verts,faces,None,''),), changed)['status'] == 'unknown', 'nonstandard_projection_falls_back')
    tiny = tuple((F(x,2**44),F(y,2**44),F(0)) for x,y in ((0,0),(1,0),(1,1),(0,1)))
    region = SimpleNamespace(roi_id='tiny', object_index=0, triangle_indices=(0,1), vertices=tiny)
    check(bounder(region, ((tiny,faces,None,''),), pose)['status'] == 'unknown', 'degenerate_screen_area_falls_back')
    return dict(signed_normal_controls=normal_checks, numerical_layouts=300, bounded_layouts=bounded,
                fallback_layouts=unknown, direct_accepted_scalar_samples=accepted_samples,
                new_production_raster_calls=0)


def main():
    saved = verify_saved()
    pure = pure_controls()
    result = dict(status='passed_checked_scope', checks=len(checks), saved=saved, pure=pure,
                  input_pins=pins, new_live_operations=dict(Blender=0,MCP=0,raster=0,model=0,paid_API=0))
    (OUT / 'RESULT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status=result['status'],checks=len(checks),saved=saved,pure=pure)))


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        (OUT / 'FAILURE.txt').write_text(traceback.format_exc(), encoding='utf8')
        raise
