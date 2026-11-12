"""Bind actual evaluated source, then replay three independent certificates.

bind_actual only reads fixed files and compares data. It neither imports the
production engine nor computes a product answer. The CLI separately replays
the original exact-support and actual-face witness oracle.
"""

import argparse
from collections import defaultdict
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ASSETS = HERE.parent / 'assets'
OLD = ROOT / 'verification/scale_diag_001'
TOLERANCE_M = 1e-6
EXPECTED = {
    OLD/'fixtures/G508.blend': '04ec6907cb2384c7f8f248c7f7ad56373ca5203692deba20c1f6eae4ec0e1c6f',
    OLD/'fixtures/G508.json': 'd1af83c191a9672e49fb5ff2e1f9b46fab0a87e39aa0ad6556ccc5bf6e4b834d',
    OLD/'oracle.py': 'c2224f9e218589a7ab945510cc390f9ca5162220765e34036b4e6dd9461bc028',
    OLD/'ORACLE.json': '4c6d45ddc087e2c9c38864890a4f99333e3c6cda40c6f36397b1768791509720',
    ASSETS/'DERIVED_MANIFEST.json': '730f56bbbfabeff73d7369807ac4e63b87f3e13bf8ddf38306816c17a3487d61',
    ASSETS/'BUILD_SNAPSHOT.json': '2ed08d5a25c5b3d09cf7b5bd3a6aaeb2e05db64365d42aee9ce1035a17d607ad',
    ASSETS/'G508_control.blend': '27f197a8cc312832382ae06cb633cbf846f20a1a22797909a15dfda8513ade46',
}
PAIR_NAMES = ('Peer_000', 'Competing_001', 'Near_003')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def checked(condition, reason):
    if not condition:
        raise ValueError(reason)


def read_inputs():
    for path, expected in EXPECTED.items():
        checked(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'fixed_input_changed:' + str(path))
    return (json.loads((OLD/'fixtures/G508.json').read_bytes()),
        json.loads((ASSETS/'BUILD_SNAPSHOT.json').read_bytes()),
        json.loads((ASSETS/'DERIVED_MANIFEST.json').read_bytes()))


def oriented_triangle(triangle):
    a, b, c = triangle
    return min((a,b,c), (b,c,a), (c,a,b))


def surface_mapping(actual, frozen):
    for key in ('name','logical_id','matrix_world'):
        checked(canonical(actual[key]) == canonical(frozen[key]), 'source_field_mismatch:' + actual['name'] + ':' + key)
    checked(len(actual['vertices_local']) == len(frozen['vertices_local']), 'vertex_count_mismatch:' + actual['name'])
    checked(len(actual['vertices_world']) == len(frozen['vertices_world']), 'world_vertex_count_mismatch:' + actual['name'])
    checked(len(actual['triangles']) == len(frozen['triangles']), 'triangle_count_mismatch:' + actual['name'])
    # Exact numeric serialization preserves binary64 roundtrip values and signed
    # zero. Reindexing never changes either local or world coordinates.
    keys = [canonical([local, world]) for local,world in zip(frozen['vertices_local'], frozen['vertices_world'])]
    checked(len(set(keys)) == len(keys), 'frozen_vertex_correspondence_not_unique:' + actual['name'])
    lookup = {key:index for index,key in enumerate(keys)}
    vertex_map = []
    for local,world in zip(actual['vertices_local'], actual['vertices_world']):
        key = canonical([local,world])
        checked(key in lookup, 'actual_vertex_not_in_frozen_source:' + actual['name'])
        vertex_map.append(lookup[key])
    checked(len(set(vertex_map)) == len(keys), 'actual_vertex_correspondence_not_bijective:' + actual['name'])
    triangles = defaultdict(list)
    for index,triangle in enumerate(frozen['triangles']):
        triangles[oriented_triangle(triangle)].append(index)
    triangle_map = []
    for triangle in actual['triangles']:
        checked(len(triangle) == 3 and len(set(triangle)) == 3 and all(type(i) is int and 0 <= i < len(vertex_map) for i in triangle),
            'invalid_actual_triangle:' + actual['name'])
        key = oriented_triangle([vertex_map[i] for i in triangle])
        checked(bool(triangles.get(key)), 'oriented_triangle_surface_changed:' + actual['name'])
        triangle_map.append(triangles[key].pop())
    checked(not any(triangles.values()), 'frozen_triangles_not_fully_covered:' + actual['name'])
    direct = all(canonical(actual[key]) == canonical(frozen[key]) for key in
        ('vertices_local','vertices_world','matrix_world','triangles'))
    return {'name':actual['name'], 'mode':'exact_arrays' if direct else 'exact_oriented_surface_reindex',
        'current_to_frozen_vertex_indices':vertex_map, 'current_to_frozen_triangle_indices':triangle_map,
        'geometry_sha256':digest({key:actual[key] for key in ('vertices_local','vertices_world','matrix_world','triangles')})}


def bind_actual(snapshot):
    """Pure bounded binding check, suitable before the three business requests."""
    old, build, manifest = read_inputs()
    checked(type(snapshot) is dict, 'actual_snapshot_must_be_object')
    for key in ('unit','coordinate_frame','frame','subframe','scale_length'):
        checked(canonical(snapshot.get(key)) == canonical(build[key]), 'snapshot_context_mismatch:' + key)
    checked(snapshot['unit'] == 'm' and snapshot['coordinate_frame'] == 'world' and snapshot['scale_length'] == 1.,
        'snapshot_coordinate_contract')
    expected = {row['name']:row for row in build['objects']}
    originals = {row['name']:row for row in old['objects']}
    for name,row in originals.items():
        checked(all(canonical(expected[name][key]) == canonical(row[key]) for key in
            ('logical_id','vertices_local','vertices_world','matrix_world','triangles')), 'derived_original_source_changed:' + name)
    actual = snapshot.get('objects')
    checked(type(actual) is list and len(actual) == len(expected) == 14, 'actual_directory_count')
    names = [row.get('name') for row in actual]
    checked(len(set(names)) == 14 and set(names) == set(expected), 'actual_directory_name_coverage')
    mappings = []
    for row in actual:
        frozen = expected[row['name']]
        for key in ('name_full','library_path','object_id','source_polygon_count'):
            checked(canonical(row.get(key)) == canonical(frozen[key]), 'source_identity_mismatch:' + row['name'] + ':' + key)
        mappings.append(surface_mapping(row,frozen))
        matrix = row['matrix_world']
        recomputed = [[(sum(matrix[r][c]*point[c] for c in range(3)) + matrix[r][3])*snapshot['scale_length']
            for r in range(3)] for point in row['vertices_local']]
        checked(canonical(recomputed) == canonical(row['vertices_world']), 'actual_world_arithmetic_mismatch:' + row['name'])
    counts = {'mesh_objects':len(actual), 'vertices':sum(len(row['vertices_local']) for row in actual),
        'triangles':sum(len(row['triangles']) for row in actual)}
    checked(counts == manifest['counts'] == {'mesh_objects':14,'vertices':848,'triangles':1640}, 'actual_geometry_counts')
    return {'passed':True,'counts':counts,'original_12_source_bound':True,'control_source_bound':True,
        'context':{key:snapshot[key] for key in ('unit','coordinate_frame','frame','subframe','scale_length')},
        'snapshot_sha256':digest(snapshot),'source_surface_mappings':mappings,
        'binding_method':'exact local/world coordinate bijection, unchanged matrix and oriented triangle multiset; no geometric tolerance',
        'input_sha256':{str(path):value for path,value in EXPECTED.items()}}


def load_original_oracle():
    path = OLD/'oracle.py'
    checked(hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED[path], 'original_oracle_source_changed')
    spec = importlib.util.spec_from_file_location('_qualification_frozen_independent_oracle',path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(path.read_bytes(),str(path),'exec',dont_inherit=True),module.__dict__)
    return module


def exact_point_witness(oracle, point, mesh):
    p = tuple(F(value) for value in point)
    for index,triangle in enumerate(mesh['faces']):
        a,b,c = [oracle.fpoint(mesh['world'][i]) for i in triangle]
        ab,ac,ap = oracle.sub(b,a),oracle.sub(c,a),oracle.sub(p,a)
        normal = oracle.cross(ab,ac)
        if oracle.dot(ap,normal) != 0:
            continue
        aa,bb,cc = oracle.dot(ab,ab),oracle.dot(ab,ac),oracle.dot(ac,ac)
        denominator = aa*cc-bb*bb
        if denominator <= 0:
            continue
        v = (oracle.dot(ap,ab)*cc-oracle.dot(ap,ac)*bb)/denominator
        w = (oracle.dot(ap,ac)*aa-oracle.dot(ap,ab)*bb)/denominator
        if min(1-v-w,v,w) >= 0:
            return {'triangle':index,'barycentric':[oracle.encoded_fraction(value) for value in (1-v-w,v,w)],
                'point_world_m':list(point)}
    raise ValueError('analytic_control_point_not_on_actual_surface:' + mesh['name'])


def control_certificate(oracle, objects):
    left,right = [oracle.mesh(objects[name]) for name in ('Control_A','Control_B')]
    qualification = [oracle.prism_qualification(row['local'],row['faces'],row['world'],row['matrix']) for row in (left,right)]
    checked(all(row['qualified'] for row in qualification), 'control_closed_shell_unqualified')
    ax = max(F(point[0]) for point in left['world'])
    bx = min(F(point[0]) for point in right['world'])
    checked(bx-ax == 1, 'control_support_gap_not_one_metre')
    witnesses = [exact_point_witness(oracle,point,row) for point,row in (((11,0,0),left),((12,0,0),right))]
    return {'surface_distance_qualified':True,'relation_qualified':True,'solid_relation':'separated',
        'distance_lower_m':1.,'distance_upper_m':1.,'distance_m':1.,
        'method':'exact_axis_support_lower_and_actual_triangle_barycentric_witness_upper',
        'support_normal':[[1,1],[0,1],[0,1]],'support_gap':[1,1],
        'witnesses':witnesses,'closed_shell_qualification':qualification,
        'pair':['Control_A','Control_B']}


def replay(snapshot):
    binding = bind_actual(snapshot)
    oracle = load_original_oracle()
    objects = {row['name']:row for row in snapshot['objects']}
    old_oracle = json.loads((OLD/'ORACLE.json').read_bytes())
    original = next(row for row in old_oracle['snapshots'] if row['id'] == 'G508')
    frozen_pairs = {row['candidate']:row for row in original['pairs']}
    target = oracle.mesh(objects['Target'])
    pairs = []
    for name in PAIR_NAMES:
        row = oracle.pair_certificate(target,oracle.mesh(objects[name]),TOLERANCE_M)
        checked(row['surface_distance_qualified'] is True, 'surface_distance_unqualified:' + name)
        checked(row['relation_qualified'] is True and row['solid_relation'] == 'separated', 'solid_relation_unqualified:' + name)
        prior = frozen_pairs[row['candidate']]
        # Both independent intervals certify the same unchanged surface. Their
        # overlap is required in addition to the unchanged 1e-6 m qualification.
        checked(max(row['distance_lower_m'],prior['distance_lower_m']) <=
            min(row['distance_upper_m'],prior['distance_upper_m']), 'frozen_distance_intervals_disjoint:' + name)
        row['candidate_name'] = name
        row['minimum_4mm'] = ('satisfied' if row['distance_lower_m'] >= .004 else
            'not_satisfied' if row['distance_upper_m'] < .004 else 'unknown')
        row['original_interval_m'] = [prior['distance_lower_m'],prior['distance_upper_m']]
        pairs.append(row)
    winner = min(pairs,key=lambda row:row['distance_upper_m'])
    checked(all(winner is other or winner['distance_upper_m'] < other['distance_lower_m'] for other in pairs),
        'three_candidate_unique_nearest_not_proved')
    return {'binding':binding,'pairs':pairs,'control':control_certificate(oracle,objects),
        'tolerance_m':TOLERANCE_M,'three_candidate_nearest':{'complete':True,'name':winner['candidate_name'],
            'scope':'only Peer_000, Competing_001 and Near_003; no global-nearest claim'},
        'independent_oracle_source_sha256':EXPECTED[OLD/'oracle.py']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    checked(output.parent == HERE.resolve(), 'output_must_be_new_immediate_oracle_child')
    output.mkdir(exist_ok=False)
    started = time.perf_counter_ns()
    result = None
    error = None
    try:
        result = replay(json.loads(args.snapshot.read_bytes()))
    except BaseException as exception:
        error = {'type':type(exception).__name__,'message':str(exception),'traceback':traceback.format_exc()}
    ended = time.perf_counter_ns()
    for name,value in (('ORACLE.json',result),('RESULTS.json',{'passed':error is None,'error':error,
        'started_ns':started,'ended_ns':ended,'elapsed_ns':ended-started,
        'snapshot':str(args.snapshot.resolve()),'snapshot_file_sha256':hashlib.sha256(args.snapshot.read_bytes()).hexdigest(),
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'fixed_inputs_unchanged':all(hashlib.sha256(path.read_bytes()).hexdigest()==expected for path,expected in EXPECTED.items()),
        'product_solver_imports':0,'product_calls':0,'model_consumers':0})):
        with (output/name).open('x',encoding='utf8',newline='\n') as stream:
            json.dump(value,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')
    return 0 if error is None else 1


if __name__ == '__main__':
    raise SystemExit(main())
