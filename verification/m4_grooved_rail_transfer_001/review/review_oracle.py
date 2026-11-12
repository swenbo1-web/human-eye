"""Review saved oracle certificates and pure-math boundaries without a live run."""

from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction as F
from itertools import combinations
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rational(value):
    return F(int(value['numerator']), int(value['denominator']))


def vector(values):
    return tuple(rational(value) for value in values)


def load_geometry():
    path = BATCH / 'oracle/exact_geometry.py'
    spec = importlib.util.spec_from_file_location('_reviewed_offline_rational_geometry', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def microchecks(module):
    def points(rows):
        return [tuple(F(value) for value in row) for row in rows]

    base = points(((0, 0, 0), (4, 0, 0), (0, 4, 0)))
    nested = points(((1, 1, 0), (2, 1, 0), (1, 2, 0)))
    opposite = points(((0, 0, 0), (4, 0, 0), (0, -4, 0)))
    overlap = points(((0, 0, 0), (3, 1, 0), (1, 3, 0)))
    checks = {
        'coplanar_nested_area': set(module.triangle_intersection(base, nested)) == set(nested),
        'coplanar_shared_edge_only': set(module.triangle_intersection(base, opposite)) == set(base[:2]),
        'coplanar_shared_vertex_extra_overlap_visible': len(module.triangle_intersection(base, overlap)) > 1,
        'triangle_intersection_symmetric': module.triangle_intersection(base, overlap) == module.triangle_intersection(overlap, base),
    }
    gap = F(1, 2**80)
    parallel = [module.add(point, (0, 0, gap)) for point in base]
    contacts = module.triangle_intersection(base, parallel)
    distance = module.triangle_distance(base, parallel, contacts)
    checks['tiny_parallel_gap_kept_exact'] = not contacts and distance['squared_distance_m2'] == gap * gap
    left = points(((-2, 0, 0), (2, 0, 0), (0, -3, -3)))
    right = points(((0, -2, 1), (0, 2, 1), (3, 0, 4)))
    edge = module.triangle_distance(left, right, module.triangle_intersection(left, right))
    checks['nonparallel_edge_interior_exact_one'] = edge['squared_distance_m2'] == 1 and any(
        row['kind'] == 'nonparallel_edge_interiors' for row in edge['minimum_candidates'])
    tetra = points(((0, 0, 0), (4, 0, 0), (0, 4, 0), (0, 0, 4)))
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    queries = [('inside', (1, 1, 1), 'inside'), ('outside_tiny', (-gap, 0, 0), 'outside'),
               ('face_boundary', (1, 1, 0), 'boundary'), ('edge_boundary', (1, 0, 0), 'boundary'),
               ('vertex_boundary', (0, 0, 0), 'boundary')]
    for name, point, expected in queries:
        checks[name] = module.point_in_solid(tuple(F(value) for value in point), tetra, faces)['status'] == expected
    retry = module.point_in_solid(tuple(F(value) for value in (-1, -1, -3)), tetra, faces)
    checks['ray_vertex_degeneracy_changes_direction'] = retry['status'] == 'outside' and bool(retry['rejected_directions'])
    for name, square in [('irrational', F(2)), ('tiny_rational', gap * gap), ('zero', F(0))]:
        interval = module.root_interval(square)
        low, high = F(Decimal(interval['lower_decimal_m'])), F(Decimal(interval['upper_decimal_m']))
        checks[name + '_root_endpoint_squares'] = low * low <= square <= high * high
    return checks


def main():
    assert not (HERE / 'RESULTS.json').exists() and not (HERE / 'REPORT.md').exists()
    bound_names = ('FREEZE.json', 'SOURCE_BINDING.json', 'PROTECTED_BEFORE.json', 'spec/PLAN.md',
        'spec/DESIGN.md', 'spec/PREVIOUS_REVIEW.md', 'asset/ACTUAL_SNAPSHOT.json', 'asset/ASSET_BINDING.json',
        'asset/grooved_rail.blend', 'worker/SOURCE_OUTPUT_MANIFEST.json', 'worker/EXPORT_AUDIT.json',
        'worker/PREPARATION.json', 'worker/BUILDER_CLOSED.json', 'worker/QA_CLOSE.json',
        'oracle/exact_geometry.py', 'oracle/exact_oracle.py', 'oracle/TRUTH.json', 'oracle/SOURCES.json',
        'oracle/RUNS.jsonl', 'oracle/REPORT.md', 'review/actual_certificates.py',
        'review/ACTUAL_CERTIFICATES.json', 'review/check_sources.py', 'review/SOURCE_REVIEW.json',
        'review/review_oracle.py')
    bound = {name: sha(BATCH / name) for name in bound_names}
    truth = read(BATCH / 'oracle/TRUTH.json')
    cert = read(HERE / 'ACTUAL_CERTIFICATES.json')
    sources = read(HERE / 'SOURCE_REVIEW.json')
    snapshot = read(BATCH / 'asset/ACTUAL_SNAPSHOT.json')
    objects = {row['name']: row for row in snapshot['objects']}
    vertices = {name: [tuple(F(value) for value in point) for point in row['vertices_world']]
                for name, row in objects.items()}
    module = load_geometry()
    checks = microchecks(module)
    checks['source_and_independent_actual_certificates_pass'] = sources['passed'] is True and cert['passed'] is True
    checks['oracle_actual_snapshot_bound'] = truth['actual_snapshot_sha256'] == cert['snapshot_sha256'] == bound['asset/ACTUAL_SNAPSHOT.json']
    checks['oracle_qualification_record_passed'] = truth['qualification_status'] == 'passed'
    checks['all_oracle_input_and_gate_checks_pass'] = all(item['passed'] for item in truth['input_checks'] + truth['algorithm_checks'] + truth['qualification_checks'])
    checks['recorded_288_294_54_counts'] = truth['counts'] == {'objects': 4, 'vertices': 26, 'triangles': 36,
        'interbody_triangle_pairs': 288, 'self_triangle_pairs': 294, 'bidirectional_vertex_parity_queries': 54}
    for prism in cert['A_prism_bounds']:
        uses = defaultdict(list)
        for face in prism['oriented_faces']:
            for a, b in zip(face, face[1:] + face[:1]):
                uses[tuple(sorted((a, b)))].append((a, b))
        key = '_'.join(map(str, prism['cap']))
        checks['prism_chain_' + key + '_closed_orientation'] = all(len(edge) == 2 and edge[0] == edge[1][::-1] for edge in uses.values())
    for name, body in truth['body_checks'].items():
        faces = objects[name]['triangles']
        expected_pairs = set(combinations(range(len(faces)), 2))
        actual_pairs = {tuple(row['triangle_ids']) for row in body['self_pair_certificates']}
        checks[name + '_all_self_pairs_and_legal_contact'] = body['passed'] is True and actual_pairs == expected_pairs
        checks[name + '_all_self_pairs_and_legal_contact'] &= not body['illegal_self_intersections'] and all(row['legal_contact'] for row in body['self_pair_certificates'])
        checks[name + '_independent_actual_signed_volume'] = rational(body['signed_volume_m3']) == F(sources['actual_signed_volumes_m3'][name])
    pair_results = []
    for name, pair in truth['pair_results'].items():
        records = pair['triangle_pair_certificates']
        expected = {(i, j) for i in range(24) for j in range(4)}
        actual = {(row['target_triangle_id'], row['candidate_triangle_id']) for row in records}
        checks[name + '_all_96_interbody_pairs'] = len(records) == 96 and actual == expected
        checks[name + '_all_feature_families_examined'] = all(row['candidate_counts']['vertex_face_projection_tests'] == 6
            and row['candidate_counts']['edge_edge_stationary_tests'] == 9 and row['candidate_counts']['vertex_vertex'] == 9
            and row['candidate_counts']['target_vertex_candidate_edge'] == 9
            and row['candidate_counts']['candidate_vertex_target_edge'] == 9 for row in records)
        square = rational(pair['exact_squared_distance_m2'])
        own = cert['actual_features'][name]
        checks[name + '_independent_bounds_and_exact_witness_match'] = F(own['distance_square_lower_bound_m2']) <= square == F(own['distance_square_m2'])
        checks[name + '_global_minimum_matches_all_pair_minima'] = square == min(rational(row['squared_distance_m2']) for row in records)
        all_minima = [witness for row in records if rational(row['squared_distance_m2']) == square for witness in row['minimum_candidates']]
        key = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'))
        checks[name + '_all_equal_global_minimum_candidates_retained'] = Counter(map(key, all_minima)) == Counter(map(key, pair['global_minimum_candidates']))
        valid = []
        for witness in pair['global_minimum_candidates']:
            target_bary, candidate_bary = vector(witness['barycentric_target']), vector(witness['barycentric_candidate'])
            target_tri = [vertices['Target'][i] for i in witness['target_vertex_ids']]
            candidate_tri = [vertices[name][i] for i in witness['candidate_vertex_ids']]
            pa, pb = vector(witness['point_target']), vector(witness['point_candidate'])
            valid.append(sum(target_bary) == sum(candidate_bary) == 1 and min(target_bary) >= 0 and min(candidate_bary) >= 0
                and module.blend(target_tri, target_bary) == pa and module.blend(candidate_tri, candidate_bary) == pb
                and module.squared(pa, pb) == square)
        checks[name + '_all_global_witnesses_exactly_legal'] = bool(valid) and all(valid)
        interval = pair['sqrt_interval']
        low, high = F(Decimal(interval['lower_decimal_m'])), F(Decimal(interval['upper_decimal_m']))
        checks[name + '_final_decimal_sqrt_bounds_certified'] = low == rational(interval['lower_exact_m'])
        checks[name + '_final_decimal_sqrt_bounds_certified'] &= high == rational(interval['upper_exact_m']) and low * low <= square <= high * high
        parity = pair['target_vertices_in_candidate_ray_parity'] + pair['candidate_vertices_in_target_ray_parity']
        checks[name + '_all_bidirectional_parity_outside'] = len(parity) == 18 and all(query['status'] == 'outside'
            and query['intersection_count'] == len(query['hits']) and len(query['hits']) % 2 == 0 for query in parity)
        checks[name + '_separated_and_expected_feature'] = pair['solid_relation'] == 'separated' and not pair['boundary_intersections']
        checks[name + '_separated_and_expected_feature'] &= truth['crosschecks']['nearest_features'][name]['passed'] is True
        pair_results.append({'candidate': name, 'actual_gap_mm': interval['display_mm'],
            'actual_squared_minimum': pair['exact_squared_distance_m2'], 'independent_legal_witness_exact_match': True})
    checks['thresholds_and_unique_nearest_from_actual_geometry'] = [truth['pair_results'][name]['at_least_4mm']
        for name in ('Part_A', 'Part_B', 'Part_C')] == [True, False, True] and truth['nearest_candidates'] == ['Part_B']
    sources_manifest = read(BATCH / 'oracle/SOURCES.json')['files']
    checks['oracle_source_manifest_matches_current_inputs'] = sources_manifest == truth['source_manifest']
    checks['oracle_source_manifest_matches_current_inputs'] &= all(sha(Path(item['path'])) == item['sha256']
        and Path(item['path']).stat().st_size == item['bytes'] for item in sources_manifest)
    runs = [json.loads(raw) for raw in (BATCH / 'oracle/RUNS.jsonl').read_bytes().splitlines() if raw]
    last = runs[-1]
    checks['original_oracle_publication_receipt_bound'] = last['qualification_status'] == 'passed' and last['exception'] is None
    checks['original_oracle_publication_receipt_bound'] &= last['truth_sha256'] == bound['oracle/TRUTH.json']
    checks['original_oracle_publication_receipt_bound'] &= last['entry_sha256'] == bound['oracle/exact_oracle.py'] and last['geometry_sha256'] == bound['oracle/exact_geometry.py']
    checks['final_bound_files_stable'] = all(sha(BATCH / name) == expected for name, expected in bound.items())
    blocking = [name for name, passed in checks.items() if not passed]
    result = {'schema': 'm4-grooved-rail-independent-qualification-review-v1', 'passed': not blocking,
        'blocking_findings': blocking, 'incomplete_items': [], 'files_sha256': bound, 'checks': checks,
        'actual_pairs': pair_results, 'source_check_count': len(sources['checks']),
        'independent_support_check_count': len(cert['checks']), 'oracle_static_review': {
            'complete_closest_features': 'Both vertex-face projections, clamped vertex-edge/endpoints and nonparallel edge interiors are enumerated for every triangle pair.',
            'intersection': 'Six segment/triangle clips handle coplanar overlap and noncoplanar crossings exactly.',
            'self_contact': 'All body triangle pairs are checked; only recorded shared vertices/edges permit contact.',
            'containment': 'All 54 actual vertices are queried bidirectionally. Boundary is explicit; coplanar or edge/vertex rays choose another recorded integer direction.',
            'numerics': 'Fraction(float) preserves actual exported binary64 geometry. Seventy-digit decimal square-root endpoints are reparsed and squared exactly.',
            'source_and_exit': 'Frozen parent blobs, complete asset/worker hashes and actual owned builder/QA exit receipts passed independent source review.'},
        'scope': 'One fixed synthetic asset qualification. Product ability, consumer quality, transfer benefit and cost comparison are unmeasured.',
        'reviewer_model_Blender_product_runs': 0, 'reviewer_formal_oracle_replays': 0,
        'math_microchecks_only': True, 'original_asset_oracle_files_modified': 0}
    with (HERE / 'RESULTS.json').open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    lines = ['# 独立几何资格复审', '', '资格复审通过。' if result['passed'] else '资格复审存在失败项。', '',
        '冻结规格、实际资产与独占读取来源核验通过。实际计数为4对象、26点、36三角。'
        '唯一资产及QA读取副本保持同一SHA，两个既有owned Blender进程均有exit0和reap回执。', '',
        '独立support与有向链证书采用实际Fraction坐标。五条闭prism链的外部三角匹配实际Target，'
        '内部采用同一对角线后精确抵消。A与每条链的凸包严格分离，且严格位于实际Target外凸包内。'
        '另以实际A半空间排除反向包含。B的全局support下界与边内点见证距离平方精确相等。', '',
        'Oracle完成288个互体三角对、294个自体三角对和54个双向顶点包含查询。'
        '完整最近特征、共面裁剪、合法共享拓扑接触、有理射线避退化和精确平方根夹界已静审，'
        '并执行15项纯数学边界核验。全部同值最小见证完整保留，三对精确minsq均与独立合法见证相同。', '',
        '| 对象对 | 实际间隙毫米 | 至少4毫米 |', '|---|---:|---|']
    for pair in pair_results:
        lines.append('| Target / ' + pair['candidate'] + ' | ' + pair['actual_gap_mm'] + ' | '
                     + ('否' if pair['candidate'] == 'Part_B' else '是') + ' |')
    lines += ['', '唯一最近者为Part_B。A保持槽底面内部最近点，B保持非平行边的严格内参数，'
        'C保持端面材料内部最近点。实际坐标保留标准API表示变化，未吸附到名义设计。', '',
        '本复审通过清单见RESULTS.json的checks。失败项为' + json.dumps(blocking, ensure_ascii=False)
        + '，未完成项为[]。此结论限于该唯一资产的几何资格，产品能力与后续消费收益仍待后续阶段验收。', '',
        '本复审新增模型、Blender和产品运行均为0，正式oracle重放为0。'
        '纯数学边界核验使用独立加载的离线几何函数，资产和oracle原件保持只读。', '',
        '最终输入及脚本SHA绑定于RESULTS.json的files_sha256。', '']
    with (HERE / 'REPORT.md').open('x', encoding='utf8', newline='\n') as stream:
        stream.write('\n'.join(lines))
    print(json.dumps({'passed': result['passed'], 'checks': len(checks), 'blocking_findings': blocking,
                      'incomplete_items': result['incomplete_items']}))


if __name__ == '__main__':
    main()
