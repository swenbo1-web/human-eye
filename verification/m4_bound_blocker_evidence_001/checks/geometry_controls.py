"""Check installed blocker sources against independent exact archived geometry."""

import argparse
from dataclasses import asdict
from fractions import Fraction
import gc
from hashlib import file_digest, sha256
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import tracemalloc
from types import ModuleType
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
FORMAT = 'human_eye_plugin/active_observation.py'
BASE = '278fd3003758299379f6d87b7e9174c577f5bb88'
BASE_SOURCE = '6e8663feb57b630048fe919141cfcabbae4ae2365df1f80da693382c360b65e8'
REASON = 'positive_area_occlusion_all_front_views'
BLOCK = 'positive_area_occlusion'
FIELDS = {'source_object_index', 'source_triangle_index'}
FIXTURES = (
    ('dense', 'm4_dense_region_brief_001', 'QP',
     'd22eae5a40a75a8b6dda86fca05b16c48c09a4f1a030bbbe6b0cc46715e2b645',
     '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164', (14, 3478, 6148), 2),
    ('assembly28', 'm4_cross_scale_pixel_evidence_001', 'P1',
     '0802bfd8968a14ceb9cb209b4378d27b3045acc61d9bede297d42dba29c5658e',
     '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85', (28, 416, 744), 6),
    ('cross21', 'm4_cross_scale_cold_frustum_001', 'B1',
     '7f94dc9f4a1d01d5b8b38064293887504b8025065a3e2e994370aea4a1f1a3b0',
     'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce', (21, 148, 184), 6),
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(value):
    return sha256(json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class PinLedger:
    def __init__(self):
        self.rows = {}

    def pin(self, path, expected=None, *, read=False):
        path = Path(path).resolve()
        if read:
            raw = path.read_bytes()
            checksum, size = sha256(raw).hexdigest(), len(raw)
        else:
            with path.open('rb') as stream:
                checksum = file_digest(stream, 'sha256').hexdigest()
            size = path.stat().st_size
        row = {'path': str(path), 'sha256': checksum, 'bytes': size}
        require(expected is None or checksum == expected, 'source_hash_changed/' + str(path))
        require(self.rows.setdefault(str(path), row) == row, 'pin_changed/' + str(path))
        return raw if read else row

    def json(self, path, expected=None):
        return json.loads(self.pin(path, expected, read=True))


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b, strict=True))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b, strict=True))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def region_corners(row):
    center, u, v = (tuple(map(Fraction, row[key])) for key in
                    ('center_world_m', 'half_edge_u_world_m', 'half_edge_v_world_m'))
    return tuple(tuple(c + i*x + j*y for c, x, y in zip(center, u, v, strict=True))
                 for i, j in ((-1,-1), (1,-1), (1,1), (-1,1)))


def clip(points, signed):
    if not points:
        return points
    kept = []
    previous = points[-1]
    before = signed(previous)
    for point in points:
        after = signed(point)
        if (after >= 0) != (before >= 0):
            ratio = before / (before-after)
            kept.append(tuple(x + ratio*(y-x) for x, y in zip(previous, point, strict=True)))
        if after >= 0:
            kept.append(point)
        previous, before = point, after
    return tuple(kept)


def triangle_signature(points):
    a, b, c = points
    return min((a,b,c), (b,c,a), (c,a,b))


class TargetProjection:
    """Use a target-plane chart and exact homogeneous camera constraints."""

    def __init__(self, corners, pose):
        self.origin, b, _, d = (tuple(map(Fraction, corner)) for corner in corners)
        u, v = sub(b, self.origin), sub(d, self.origin)
        n = cross(u, v)
        direction = tuple(map(Fraction, pose['direction_rational']))
        facing = dot(n, direction)
        self.chart_axes = (u, v)
        self.forward = tuple(x/facing for x in n) if facing > 0 else None
        self.inverse_plane = tuple(tuple(x/dot(axis, axis) for x in axis) for axis in (u, v))
        self.shift = tuple(dot(axis, direction) for axis in self.inverse_plane)
        view = tuple(tuple(map(Fraction, row)) for row in pose['view_matrix'])
        projection = tuple(tuple(map(Fraction, row)) for row in pose['projection_matrix'])
        columns = tuple(zip(*view, strict=True))
        camera = tuple(tuple(dot(row, column) for column in columns) for row in projection)
        self.frustum = tuple(tuple(w + sign*t for w,t in zip(camera[3], row, strict=True))
                             for row in camera[:3] for sign in (-1,1))
        self.region_inside = all(dot(plane, (*p, 1)) >= 0 for plane in self.frustum for p in corners)
        right = cross((0,0,1), direction)
        if not any(right):
            right = cross((0,1,0), direction)
        up = cross(direction, right)
        self.area_scale = abs(dot(right,u)*dot(up,v)-dot(up,u)*dot(right,v))

    def project(self, point):
        offset = sub(point, self.origin)
        depth = dot(self.forward, offset)
        x, y = (dot(axis, offset) - shift*depth for axis,shift in zip(self.inverse_plane, self.shift, strict=True))
        return x, y, depth

    def overlap(self, points):
        zero = Fraction(0), Fraction(0)
        if self.forward is None or not self.region_inside:
            return zero
        polygon = tuple(self.project(point) for point in points)
        x, y, z = zip(*polygon, strict=True)
        if max(z) <= 0 or min(x) >= 1 or max(x) <= 0 or min(y) >= 1 or max(y) <= 0:
            return zero
        # Keep each source point's world coordinates so NDC clipping stays
        # affine in the same chart and does not use the installed screen solver.
        polygon = tuple((*chart, *point) for chart, point in zip(polygon, points, strict=True))
        for plane in self.frustum:
            polygon = clip(polygon, lambda p: dot(plane, (*p[3:], 1)))
        if not polygon or max(p[2] for p in polygon) <= 0:
            return zero
        polygon = clip(polygon, lambda p: p[2])
        for axis in (0,1):
            polygon = clip(polygon, lambda p: p[axis])
            polygon = clip(polygon, lambda p: 1-p[axis])
        chart_area = abs(sum(a[0]*b[1]-a[1]*b[0]
                             for a,b in zip(polygon, polygon[1:]+polygon[:1], strict=True)))/2 if polygon else Fraction(0)
        return chart_area, chart_area*self.area_scale


def independent_overlap(points, corners, pose):
    """Return normalized target chart and original screen areas as Fractions."""
    points = tuple(tuple(map(Fraction, point)) for point in points)
    return TargetProjection(corners, pose).overlap(points)


def exact_triangles(scene):
    # Baseline order is cyclic canonical vertex order, stable on equal keys.
    # Keep the original enumerated identities out of the sort key.
    all_faces = []
    for object_index, obj in enumerate(scene['objects']):
        points = tuple(tuple(map(Fraction, p)) for p in obj['vertices'])
        for face_index, face in enumerate(obj['triangles']):
            triangle = tuple(points[i] for i in face)
            all_faces.append((triangle_signature(triangle), object_index, face_index, triangle))
    return sorted(all_faces, key=lambda source: source[0])


def expected_first(row, pose, ordered):
    proof = TargetProjection(region_corners(row), pose)
    require(proof.forward is not None and proof.region_inside, 'archived_blocked_region_not_a_valid_front_view')
    own = set(row['source_triangle_indices'])
    for signature, index, triangle, points in ordered:
        if index == row['object_index'] and triangle in own:
            continue
        chart, screen = proof.overlap(points)
        if chart > 0:
            return {
                'roi_id': row['roi_id'], 'region_object_index': row['object_index'], 'region_object_name': row['object_name'],
                'view_name': pose['name'], 'blocker_object_index': index, 'source_triangle_index': triangle,
                'triangle_geometry_id': digest(signature), 'overlap_area_screen_exact': str(screen),
                'overlap_target_chart_exact': str(chart),
            }
    raise ValueError('independent_first_blocker_missing/' + row['roi_id'] + '/' + pose['name'])


def load_capture(pins, fixture):
    key, batch, slot, index_hash, asset_hash, counts, expected_count = fixture
    location = Path('D:/he_' + batch)
    index = pins.json(V / batch / 'RUNTIME_INDEX.json', index_hash)
    archive = Path(index['archive']['path']).resolve()
    require(archive == (location / 'ORIGINAL_RUNTIME.zip').resolve(), 'original_bundle_path/' + key)
    pins.pin(archive, index['archive']['sha256'])
    records = {row['path']: row for row in index['files']}
    require(len(records) == len(index['files']), 'duplicate_bundle_path/' + key)
    with ZipFile(archive) as bundle:
        def original(leaf):
            prefix = f'slots/{slot}/{leaf}'
            row = records[prefix]
            raw = pins.pin(location / prefix, row['sha256'], read=True)
            require(len(raw) == row['bytes'] and raw == bundle.read(prefix), 'original_not_in_archive/' + prefix)
            return raw

        terminal_raw = original('TERMINAL_SOURCE.json')
        producer_raw = original('product_full/call_001/SERVICE_RESULT.json')
        result_raw = original('SLOT_RESULT.json')
        result = json.loads(result_raw)
        publication = json.loads(original('SLOT_PUBLICATION.json'))
        terminal = json.loads(terminal_raw)
        producer = json.loads(producer_raw)
        require(sha256(original('native/input.blend')).hexdigest() == asset_hash, 'actual_asset_changed/' + key)
    terminal_sha = sha256(terminal_raw).hexdigest()
    bound = producer['binding']
    cameras = bound['camera_specification']
    require(publication['result_sha256'] == sha256(result_raw).hexdigest()
            and publication['status'] == result['status']
            and result['terminal_source']['sha256'] == terminal_sha
            and terminal['source']['asset_sha256'] == asset_hash
            and terminal['source']['pid'] == result['terminal_source']['worker']['pid']
            and bound['capture_scope'] == 'complete_scene_meshes'
            and all(terminal['display_object_mask']), 'incorrect_archived_capture/' + key)
    meshes = terminal['objects']
    tracked = bound['objects']
    require(len(meshes) == len(tracked) and
            all((i, mesh['name'], mesh['object_id'], mesh['instance_id']) ==
                (row['object_index'], row['object_name'], row['host_id'], row['instance_id'])
                for i,(mesh,row) in enumerate(zip(meshes,tracked,strict=True))), 'producer_source_object_order/' + key)
    objects = [{'name': mesh['name'], 'vertices': mesh['evaluated']['vertices_world_m'],
                'triangles': mesh['evaluated']['triangles']} for mesh in meshes]
    require((len(meshes), sum(len(mesh['vertices']) for mesh in objects),
             sum(len(mesh['triangles']) for mesh in objects)) == counts, 'original_mesh_denominator/' + key)
    scene = {'objects': objects}
    ordered = exact_triangles(scene)
    views = {row['name']: row for row in cameras['views']}
    rows = producer['facts']['region_task']['rows']
    selection = {row['object_index'] for row in rows}
    blocked = []
    for row in rows:
        if row['reason'] != REASON:
            continue
        require(row['status'] == 'unknown' and not row['complete_witness'], 'archived_blocker_not_final_unknown')
        for name in row['view_reasons'][BLOCK]:
            witness = expected_first(row, views[name], ordered)
            source = objects[witness['blocker_object_index']]
            blocked.append(witness | {'blocker_object_name': source['name'],
                                      'blocker_object_in_target_set': witness['blocker_object_index'] in selection})
    require(len(blocked) == expected_count, 'changed_target_blocker_denominator/' + key)
    if key == 'dense':
        exact = {(row['region_object_name'], row['view_name']): (row['blocker_object_name'], row['source_triangle_index'],
                 row['overlap_target_chart_exact']) for row in blocked}
        require(exact == {('M4_Far_00','LEFT'): ('M4_Near',0,'73786983304225/9223372036854775808'),
                          ('M4_Far_02','LEFT'): ('M4_Far_00',512,'1/2')}, 'dense_bound_sources_not_independent_truth')
    elif key == 'assembly28':
        require({row['region_object_name'] for row in blocked} == {'N11'}
                and len({row['blocker_object_name'] for row in blocked}) > 1, 'assembly_blocker_roster')
    else:
        require({(row['region_object_name'], row['blocker_object_name']) for row in blocked} == {('M06','M03')},
                'cross21_blocker_roster')
    return scene, producer, {
        'asset_sha256': asset_hash, 'terminal_sha256': terminal_sha, 'producer_sha256': sha256(producer_raw).hexdigest(),
        'counts': dict(zip(('objects','vertices','triangles'),counts,strict=True)), 'rows': blocked,
    }


def import_kernel(pins, binding, label):
    manifest = {row['path']:row['sha256'] for row in binding['source_manifest']}
    require(len(manifest) == 143, 'wrong_installed_manifest_count/' + label)
    path = Path(binding['install_root']) / FORMAT
    raw = pins.pin(path, manifest[FORMAT], read=True)
    module = ModuleType('_bound_blocker_installed_' + label)
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), 'exec'), vars(module))
    return module


def without_sources(index):
    value = asdict(index)
    count = 0
    for rows in value['classifications'].values():
        for info in rows.values():
            blocker = info.get('first_blocker')
            if blocker and FIELDS & blocker.keys():
                require(FIELDS <= blocker.keys(), 'incomplete_index_blocker_source_fields')
                count += 1
                for key in FIELDS:
                    del blocker[key]
    return value, count


def compare_fixture(a, b, scene, producer, evidence):
    cameras = producer['binding']['camera_specification']
    parsed_a = a.geometry(scene)
    parsed_b = b.geometry(scene)
    require(parsed_a[2] == parsed_b[2] == producer['binding']['geometry_identity'], 'archive_geometry_identity')
    work_a,work_b = {},{}
    started = perf_counter_ns()
    original, _ = a.prepare_coverage_index(*parsed_a, cameras, prove_frustum_containment=True, frustum_work=work_a)
    elapsed_a = perf_counter_ns()-started
    started = perf_counter_ns()
    candidate, _ = b.prepare_coverage_index(*parsed_b, cameras, prove_frustum_containment=True, frustum_work=work_b,
                                           bind_blocker_sources=True)
    elapsed_b = perf_counter_ns()-started
    old, count_a = without_sources(original)
    new, count_b = without_sources(candidate)
    require(old == new and count_a == 0 and
            {k:v for k,v in work_a.items() if k != 'frustum_proof_ns'} ==
            {k:v for k,v in work_b.items() if k != 'frustum_proof_ns'}, 'earlier_index_or_work_changed')
    require(original.candidate_identity == producer['binding']['camera_identity'], 'archive_camera_identity')
    raw_faces = {(index, local): signature for signature,index,local,_ in exact_triangles(scene)}
    old_blocks = sum(bool(row.get('first_blocker')) for rows in old['classifications'].values() for row in rows.values())
    require(old_blocks == count_b, 'new_index_blocker_denominator')
    for rows in candidate.classifications.values():
        for info in rows.values():
            hit = info.get('first_blocker')
            if hit:
                index, local = hit['source_object_index'], hit['source_triangle_index']
                require(type(index) is type(local) is int and
                        hit['triangle_geometry_id'] == digest(raw_faces[(index,local)]) and
                        Fraction(hit['overlap_area_screen_exact']) > 0, 'bound_first_blocker_not_original_source')
    for row in evidence['rows']:
        hit = candidate.classifications[row['view_name']][row['roi_id']]['first_blocker']
        require(hit == {'source_object_index': row['blocker_object_index'], 'source_triangle_index': row['source_triangle_index'],
                        'triangle_geometry_id': row['triangle_geometry_id'],
                        'overlap_area_screen_exact': row['overlap_area_screen_exact']},
                'candidate_exact_first_source_differs/' + row['roi_id'] + '/' + row['view_name'])

    ordinary_b,_ = b.prepare_coverage_index(*parsed_b,cameras)
    ordinary_a,_ = a.prepare_coverage_index(*parsed_a,cameras)
    require(asdict(ordinary_a) == asdict(ordinary_b), 'ordinary_index_changed')
    local_count = 0
    for scope in producer['scopes']:
        if scope['scope_id'] == 'global':
            continue
        roi_id = scope['facts']['scope']['roi_id']
        local_camera = scope['binding']['camera_specification']
        locals_ = [{r.roi_id:r for r in value.regions}[roi_id] for value in (ordinary_a,ordinary_b)]
        local_a = a.build_index_from_parsed(*parsed_a,(locals_[0],),local_camera)
        local_b = b.build_index_from_parsed(*parsed_b,(locals_[1],),local_camera)
        require(asdict(local_a) == asdict(local_b), 'local_index_changed/' + roi_id)
        local_count += 1

    return evidence | {
        'index_sha256': digest(old), 'index_views': len(original.view_order), 'index_regions': len(original.regions),
        'original_first_blocker_count': old_blocks, 'bound_first_blocker_count': count_b,
        'unchanged_ordinary_index': True, 'unchanged_local_indexes': local_count,
        'offline_cold_index_baseline_ms': elapsed_a/1e6, 'offline_cold_index_candidate_ms': elapsed_b/1e6,
    }


def synthetic(api):
    one = tuple(tuple(int(i==j) for j in range(4)) for i in range(4))
    pose = {'name':'SCENE','direction_rational': (0,0,1),'view_matrix': one,
            'projection_matrix': one,'size_px': (64,64)}
    camera = {'views':[pose]}
    r = Fraction(1,4)
    e = Fraction(1,2**100)
    target = {'name': 'target', 'vertices': [(0,0,0),(1,0,0),(1,1,0),(0,1,0)],
              'triangles': [(0,1,2),(0,2,3)]}
    repeated = [(r,r,r),(2*r,r,r),(r,2*r,r)]
    shapes = (
        ('coincident_objects_preserve_first_source', [('Z-first',repeated),('A-twin',repeated)], (1,0)),
        ('reversed_coincident_objects_report_new_first_owner', [('A-twin',repeated),('Z-first',repeated)], (1,0)),
        ('first_source_is_not_nearest', [('lower',repeated),('nearest',[(x,y,2*r) for x,y,z in repeated])], (1,0)),
        ('positive_far_below_float_tolerance', [('tiny',[(r,r,r),(r+e,r,r),(r,r+e,r)])], (1,0)),
        ('edge_contact_zero_area', [('touch',[(r,1,r),(2*r,1,r),(r,2,r)])], None),
        ('zero_depth_does_not_occlude', [('coplanar',[(x,y,0) for x,y,z in repeated])], None),
        ('zero_area_after_exact_frustum_clipping', [('outside_camera',[(r,r,2),(2*r,r,2),(r,2*r,2)])], None),
        ('self_source_is_excluded', [], None),
    )
    results = {}
    for name, extras, expected in shapes:
        scene = {'objects':[target,*[{'name': label, 'vertices': vertices, 'triangles': [(0,1,2)]}
                                     for label, vertices in extras]]}
        parsed = api.geometry(scene)
        regions,_ = api.partition_regions(parsed[0], target_object_index=0)
        region, = regions
        visits = []
        real = api.triangle_shadow

        def traced(triangle,*args,**kwargs):
            visits.append((triangle.object_index,triangle.triangle_index))
            return real(triangle,*args,**kwargs)

        with patch.object(api, 'triangle_shadow', traced):
            index = api.build_index_from_parsed(*parsed,regions,camera,prove_frustum_containment=True,
                                                bind_blocker_sources=True)
        hit = index.classifications['SCENE'][region.roi_id].get('first_blocker')
        require(all(index!=0 for index,_ in visits), 'same_region_source_not_excluded')
        require((None if hit is None else (hit['source_object_index'],hit['source_triangle_index'])) == expected,
                'synthetic_first_blocker_failed/' + name)
        areas = [independent_overlap(points,region.vertices,pose) for points in (vertices for _,vertices in extras)]
        if expected is None:
            require(all(a == 0 and b == 0 for a,b in areas), 'synthetic_zero_overlap_fixture_not_zero')
        elif hit:
            require(Fraction(hit['overlap_area_screen_exact']) == areas[expected[0]-1][1] > 0,
                    'synthetic_first_blocker_overlap_differed')
        results[name] = {'actual_source': hit, 'actual_object_name': extras[expected[0]-1][0] if expected else None,
                         'independent_target_chart_areas': [str(a) for a,_ in areas], 'shadow_source_visits': visits}
    return results


def memory_comparison(a, b, dense_scene, cameras):
    """Measure one isolated build per arm; retain no earlier build in the trace."""
    results = {}
    for label, module in (('baseline', a), ('candidate', b)):
        parsed = module.geometry(dense_scene)
        gc.collect()
        kwargs = {} if label == 'baseline' else {'bind_blocker_sources': True}
        tracemalloc.start()
        started = perf_counter_ns()
        try:
            index, _ = module.prepare_coverage_index(*parsed,cameras,prove_frustum_containment=True,**kwargs)
            elapsed = perf_counter_ns()-started
            retained,peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        blockers = [row['first_blocker'] for views in index.classifications.values() for row in views.values()
                    if row.get('first_blocker')]
        results[label] = {'single_build_python_traced_retained_bytes': retained, 'single_build_python_traced_peak_bytes': peak,
                          'single_build_traced_ms': elapsed/1e6,
                          'first_blocker_dict_shallow_bytes_total': sum(map(sys.getsizeof,blockers)),
                          'first_blocker_rows': len(blockers)}
    require(results['baseline']['first_blocker_rows'] == results['candidate']['first_blocker_rows'],
            'memory_comparison_denominator_changed')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=NS/'install/PRODUCT_RUN_BINDING.json')
    parser.add_argument('--output', type=Path, default=HERE/'GEOMETRY_CONTROLS.json')
    parser.add_argument('--oracle-only', action='store_true', help='Only print the independently derived fixture rows')
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_python_I_B_required')
    pins = PinLedger()
    pins.pin(__file__)
    captures = {spec[0]:load_capture(pins,spec) for spec in FIXTURES}
    if args.oracle_only:
        print(json.dumps({key:value[2] for key,value in captures.items()},indent=2))
        return
    a = pins.json(V/'m4_dense_region_brief_001/install/PRODUCT_RUN_BINDING.json')
    b = pins.json(args.candidate)
    require(a['preparation_git'] == BASE and a['source_sha256'] == BASE_SOURCE
            and b['source_sha256'] != BASE_SOURCE and b['historical_preparation_git'] == BASE
            and a['dependency_root'] == b['dependency_root'], 'incorrect_installed_candidate_lineage')
    a_kernel,b_kernel = import_kernel(pins,a,'baseline'),import_kernel(pins,b,'candidate')
    result = {
        'schema': 'm4-bound-blocker-geometry-controls-v1', 'passed': True,
        'actual_Blender_processes': 0, 'actual_model_runs': 0, 'actual_raster_attempts': 0,
        'baseline_source_sha256': BASE_SOURCE, 'candidate_source_sha256': b['source_sha256'],
        'fixtures': {key:compare_fixture(a_kernel,b_kernel,*spec) for key,spec in captures.items()},
        'synthetic': synthetic(b_kernel),
        'dense_index_memory': memory_comparison(a_kernel,b_kernel,captures['dense'][0],
                                                captures['dense'][1]['binding']['camera_specification']),
        'source_pins': sorted(pins.rows.values(), key=lambda row: row['path']),
    }
    with args.output.open('x',encoding='utf8',newline='\n') as out:
        json.dump(result,out,sort_keys=True,indent=2,allow_nan=False)
        out.write('\n')
    print('Independent geometry passed:',sum(len(value['rows']) for value in result['fixtures'].values()),'fixture sources',
          len(result['synthetic']),'targeted geometry cases',result['dense_index_memory'])


if __name__ == '__main__':
    main()
