"""Independently audit finished T04 wire geometry; stdlib only, no product run."""
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parent
QA = ROOT / 'qa_01'
EXPECTED_COMMIT = '0ad59befeee43c2fad752e3bad2ee69f87af3136'
EXPECTED_SOURCE = '82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
load = lambda path: json.loads(path.read_bytes())


def inventory(folder):
    return [dict(path=path.relative_to(folder).as_posix(), bytes=path.stat().st_size,
                 sha256=sha(path.read_bytes()))
            for path in sorted(folder.rglob('*')) if path.is_file()]


def exact(value):
    assert type(value) in (int, float) and math.isfinite(value)
    return Fraction.from_float(float(value))


def point(values):
    assert len(values) == 3
    return tuple(exact(value) for value in values)


def fraction(value):
    return dict(numerator=value.numerator, denominator=value.denominator)


def socket_capture(ordinal):
    wire = QA / f'stdio/socket_{ordinal}/RX.bin'
    outer = load(wire)
    assert outer['status'] == 'success'
    assert outer['result']['executed'] is True
    prefix, body = outer['result']['result'].split('HUMAN_EYE_BLENDER_MCP:', 1)
    assert not prefix.strip()
    envelope = json.loads(body)
    assert envelope['protocol_version'] == '1.0'
    packet = envelope['result']
    assert packet['protocol'] == 'single-read-surface-candidates-v1'
    assert packet['result_kind'] == 'acquisition_only_not_nearest_result'
    assert packet['M3_qualification_performed'] is False
    assert packet['execution_authority'] is False
    assert load(QA / f'stdio/socket_{ordinal}/TX.bin')['type'] == 'execute_code'
    return packet


def public(ordinal):
    folder = QA / f'mcp_frames/{ordinal + 3:02}'
    request = load(folder / 'TX.bin')
    response = load(folder / 'RX.bin')
    assert request['method'] == 'tools/call'
    assert request['params']['name'] == 'human_eye_scene_observe'
    assert request['id'] == response['id']
    assert response['result']['isError'] is False
    content = response['result']['content']
    assert len(content) == 1 and content[0]['type'] == 'text'
    return request['params']['arguments'], json.loads(content[0]['text'])


def independently_measure(packet):
    capture = packet['capture']
    assert capture['unit'] == 'm' and capture['coordinate_frame'] == 'world'
    assert capture['source'] == 'blender'
    assert capture['capture_scope'] == 'surface_nearest_candidates'
    assert capture['execution_authority'] is False
    meshes = capture['meshes']
    assert len(meshes) == 5
    by_id = {mesh['object_id']: mesh for mesh in meshes}
    assert len(by_id) == 5
    assert set(by_id) == {row['object_id'] for row in packet['coverage']}
    assert all(row['disposition'] == 'retained' for row in packet['coverage'])
    focal = by_id[packet['focal_id']]
    assert focal['name'] == 'M4_Focal' and focal['is_focal_target'] is True
    assert focal['faces'] == [[0, 1, 2]]
    focal_points = [point(row) for row in focal['vertices']]
    assert focal_points == [(0, 0, 0), (0, 1, 0), (0, 0, 0)]
    # This is an analytic proof over the parsed coordinates, not any product
    # primitive: p=(0,t,0), 0<=t<=1. Each q=(x,s,u) has s,u>=0,s+u<=1.
    # ||p-q||²=x²+(t-s)²+u² >= x², attained at t=s=u=0.
    targets = []
    for identity, mesh in sorted(by_id.items()):
        if identity == packet['focal_id']:
            continue
        assert mesh['faces'] == [[0, 1, 2]]
        coordinates = [point(row) for row in mesh['vertices']]
        x = coordinates[0][0]
        assert x > 0
        assert coordinates == [(x, 0, 0), (x, 1, 0), (x, 0, 1)]
        targets.append(dict(object_id=identity, name=mesh['name'],
            vertices_binary64=mesh['vertices'], faces=mesh['faces'],
            distance_exact=fraction(x), distance_squared_exact=fraction(x*x),
            distance_binary64=float(x), coordinate_hex=float(x).hex(),
            independently_proved_rank=2,
            lower_bound='x_squared_from_constant_x_support_planes',
            attaining_points=[[0., 0., 0.], [float(x), 0., 0.]]))
    actual_names = {row['name'] for row in targets}
    assert actual_names == {'M4_Near', 'M4_Far_00', 'M4_Far_01', 'M4_Far_02'}
    exact_distances = {row['object_id']: Fraction(**row['distance_exact']) for row in targets}
    minimum = min(exact_distances.values())
    nearest = sorted(identity for identity, value in exact_distances.items() if value == minimum)
    expected_by_name = {'M4_Near': Fraction(8589935, 2147483648),
                        'M4_Far_00': Fraction(1), 'M4_Far_01': Fraction(2), 'M4_Far_02': Fraction(3)}
    assert {row['name']: exact_distances[row['object_id']] for row in targets} == expected_by_name
    assert minimum == Fraction(8589935, 2147483648)
    assert len(nearest) == 1 and by_id[nearest[0]]['name'] == 'M4_Near'
    focal_row = next(row for row in packet['coverage'] if row['object_id'] == packet['focal_id'])
    assert focal_row['witness'] is None
    assert packet['witness_upper_bound_m'] is None and packet['upper_seed_id'] is None
    return dict(focal=dict(object_id=packet['focal_id'], name=focal['name'],
                    vertices_binary64=focal['vertices'], faces=focal['faces'], independently_proved_rank=1,
                    closed_hull='segment (0,0,0) to (0,1,0)'),
        targets=targets, minimum_distance_exact=fraction(minimum),
        minimum_squared_exact=fraction(minimum*minimum), minimum_distance_binary64=float(minimum),
        all_nearest_objects=[dict(id=identity, name=by_id[identity]['name']) for identity in nearest],
        targets_excluding_focal=len(targets), all_geometry_finite_and_supported_by_analytic_proof=True,
        acquisition=dict(all_five_retained=True, focal_triangle_witness_absent=True,
            witness_upper_bound_absent=True, strictly_excluded=0,
            explanation='Degenerate focal supplies no original nondegenerate triangle upper witness; all four target distances are independently checked.'))


def main():
    started = time.perf_counter_ns()
    json_path, md_path = ROOT / 'GEOMETRY_AUDIT.json', ROOT / 'GEOMETRY_AUDIT.md'
    assert not json_path.exists() and not md_path.exists(), 'preserve earlier audit attempts'
    before = inventory(QA)
    original_qa = load(QA / 'RESULTS.json')
    assert original_qa['candidate_commit'] == EXPECTED_COMMIT
    assert original_qa['source_sha256'] == EXPECTED_SOURCE
    assert original_qa['total_RPC_attempts'] == 3
    assert sorted(path.name for path in (QA / 'stdio').glob('socket_*')) == ['socket_1', 'socket_2']
    captures, public_results, rows, requests = [], [], [], []
    for ordinal in (1, 2):
        packet = socket_capture(ordinal)
        independent = independently_measure(packet)
        arguments, result = public(ordinal)
        assert result['result_kind'] == 'surface_nearest'
        assert result['status'] == 'complete' and result['scope'] == 'surface_nearest_candidates'
        assert result['unit'] == 'm' and result['execution_authority'] is False
        assert result['focal'] == dict(id=independent['focal']['object_id'], name='M4_Focal')
        assert result['nearest_objects'] == independent['all_nearest_objects']
        assert result['best_known_objects'] == independent['all_nearest_objects']
        assert result['distance_m'] == result['best_known_distance_m'] == independent['minimum_distance_binary64']
        assert result['coverage'] == dict(targets_excluding_focal=4, distance_valid=4,
                                           strictly_excluded=0, unresolved=0)
        assert result['unresolved'] == [] and result['measurement_notes'] == {}
        assert result['binding']['runtime_source_sha256'] == EXPECTED_SOURCE
        assert result['binding']['scene_revision'] == packet['capture']['revision']
        assert result['binding']['document_epoch'] == packet['binding']['host_identity']['document_epoch']
        assert result['binding']['directory_sha256'] == packet['binding']['directory_sha256']
        assert arguments['include_image'] is False
        rows.append(dict(ordinal=ordinal, request=arguments, public_result=result,
            independent_geometry=independent, public_matches_independent_oracle=True))
        captures.append(packet)
        public_results.append(result)
        requests.append(arguments)
    assert requests[0]['query'] == dict(mode='surface_nearest', objects=[dict(name='M4_Focal')])
    assert 'focal_id' not in requests[0]
    assert requests[1]['query'] == dict(mode='surface_nearest')
    assert requests[1]['focal_id'] == public_results[0]['focal']['id']
    semantic = lambda value: {key: item for key, item in value.items() if key != 'trace_id'}
    assert semantic(public_results[0]) == semantic(public_results[1])
    assert captures[0]['capture'] == captures[1]['capture']
    assert rows[0]['independent_geometry'] == rows[1]['independent_geometry']
    offline = load(ROOT / 'offline_01/RESULTS.json')
    assert offline['runtime_source_sha256'] == EXPECTED_SOURCE
    assert offline['groups']['DIRECTED_MATH'] == dict(tests=12, failures=0, errors=0,
        skipped=0, successful=True, omitted_methods=[], selected_methods=[])
    groups = [dict(number=i, scope=text) for i, text in enumerate([
        'point/point repetition and zero direction',
        'point/segment hull endpoints, permutations, repeated zero edges',
        'point/triangle interior, edge, vertex and contact',
        'segment/segment skew, parallel, crossing, collinear overlap/touch/gap',
        'noncoplanar segment through face interior with both endpoints outside',
        'coplanar segment/face crossing and parallel offset projection',
        'ordinary triangle work, face union not global hull, late degenerate face',
        'actual binary64 large translations and rotations',
        'nonzero nearly collinear triangle and tiny positive gaps',
        'invalid indices/nonfinite data, original work/bit/deadline limits',
        'fake-RNA actual read-only chain, original T04, duplicate-near ties, ordinary strict exclusion, hot rank cache',
        'old/new and normal/rank cache isolation, valid distance with unpublished witness'], 1)]
    after = inventory(QA)
    assert before == after, 'finished raw QA evidence changed during audit'
    inputs = [QA / f'stdio/socket_{i}/{name}.bin' for i in (1, 2) for name in ('TX', 'RX')]
    inputs += [QA / f'mcp_frames/{i:02}/{name}.bin' for i in (4, 5) for name in ('TX', 'RX')]
    inputs += [QA / 'RESULTS.json', ROOT / 'offline_01/RESULTS.json',
               ROOT / 'offline_01/DIRECTED_MATH.txt', ROOT / 'tests/test_degenerate_surface.py',
               ROOT / 'tests/TEST_PLAN.md', ROOT / 'T04_ORACLE.json']
    report = dict(cycle_id='DEGENERATE-SURFACE-001', checked_utc=datetime.now(timezone.utc).isoformat(),
        scope='Finished raw public stdio/socket geometry only; no product import or experiment replay',
        passed=True, fixed_candidate_commit=EXPECTED_COMMIT, fixed_runtime_source_sha256=EXPECTED_SOURCE,
        inputs=[dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size,
                     sha256=sha(path.read_bytes())) for path in inputs],
        independent_argument='For parsed focal p=(0,t,0), 0<=t<=1, and target q=(x,s,u), s,u>=0,s+u<=1, squared distance x^2+(t-s)^2+u^2 is at least x^2 and attained at p=(0,0,0),q=(x,0,0). Every actual face and vertex was checked against these constraints using exact Fractions of parsed binary64 numbers.',
        captures=rows, name_legacy_semantics_equal_except_trace_id=True,
        all_captured_geometry_identical_between_requests=True,
        original_QA_RPC_count=original_qa['total_RPC_attempts'],
        raw_QA_preserved=dict(files=len(before), before=before, after_matches_before=True),
        directed_test_record=dict(source='offline_01/RESULTS.json and DIRECTED_MATH.txt',
            tests=12, failures=0, errors=0, skipped=0, executed_by='parent original verified-loader run, not this audit',
            cases=groups, total_related_regressions_recorded=offline['tests_run']),
        limits=[
            'Actual T04 has one unique nearest object. Multi-object exact ties are supported here by the offline duplicate-near cases, not by this real asset.',
            'Actual T04 has no strict-bound exclusions; ordinary-focal strict pruning is covered offline, not invented for this sample.',
            'This audit independently proves geometry from raw captures; source execution/owner cleanup/asset preservation require their separate receipts and audits.',
            'No new model answer or consumer was run. Geometry completion does not establish model tool adoption, whole-task savings or fees.',
            'No backend/provider accounting or unavailable final process events are inferred.'],
        actual_new_product_imports=0, actual_new_models=0, actual_new_Blender=0,
        actual_new_RPC=0, actual_new_external_API=0, tests_rerun=0,
        elapsed_ns=time.perf_counter_ns()-started)
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf8', newline='\n')
    minimum = rows[0]['independent_geometry']['minimum_distance_exact']
    target_table = '\n'.join(f"| {row['name']} | {row['distance_exact']['numerator']}/{row['distance_exact']['denominator']} | {row['distance_binary64']} |"
        for row in sorted(rows[0]['independent_geometry']['targets'], key=lambda item:item['distance_binary64']))
    md = f"""# Independent T04 geometry audit

Both finished raw socket captures and public stdio returns pass independent geometry checks. No product module or test module was imported; no model, Blender, RPC or test was rerun.

The actual focal vertices are `(0,0,0), (0,1,0), (0,0,0)`, so its closed face hull is a segment. Every actual target face is `(x,0,0), (x,1,0), (x,0,1)`. With focal p=(0,t,0) and target q=(x,s,u), squared distance is x²+(t−s)²+u² ≥ x². The lower bound is attained at paired y=z=0 vertices. This proof uses exact Fractions of the parsed binary64 coordinates, independently of the product distance kernel.

| Actual target | Exact distance metres | Binary64 distance metres |
|---|---:|---:|
{target_table}

The exact nearest distance is {minimum['numerator']}/{minimum['denominator']} m = `0.004000000189989805` m. The sole nearest object is `M4_Near`; all four actual candidate distances are finite and independently proved. Both public packets report complete, coverage 4 valid / 0 strictly excluded / 0 unresolved, metres, unchanged focal identity and no execution authority. The second request's legacy focal_id is exactly the first return's focal.id; all public semantic fields, including bindings, are identical except trace_id. Captured geometry is identical.

The actual asset has no multiple nearest-object tie and no strict AABB exclusion. Its degenerate focal has no original nondegenerate triangle acquisition witness or finite upper seed, so all four targets remain retained. Multiple exact ties and strict exclusion are demonstrated by the distinct fixed offline variants, not claimed from this real sample.

The original offline record reports 12/12 directed groups passed, 0 failures/errors/skips; 83 related methods overall. The twelve groups cover point/line/face combinations, all collinear vertex orders and zero edges, interior segment/face crossing, coplanar cases, face-union semantics, actual binary64 transforms, near-nonzero geometry, bit/work/deadline limits, real read-only fake-RNA chain and ties/pruning, normal/rank cache identities, and distance/witness separation. That is offline verified-source evidence. These two actual Blender captures establish only this real T04's supported segment-to-triangle geometry and name/legacy equivalence.

Candidate `{EXPECTED_COMMIT}`, raw reported runtime source `{EXPECTED_SOURCE}`. Source execution proof and owner/asset closure are separate audits; this geometry audit does not substitute for missing receipts. All {len(before)} QA files were hash-inventoried before and after and remained byte-identical. Inputs and exact fractions are retained in GEOMETRY_AUDIT.json. This audit does not claim model adoption, task savings, provider requests or fees.
"""
    md_path.write_text(md, encoding='utf8', newline='\n')
    print(json.dumps(dict(passed=True, json_sha256=sha(json_path.read_bytes()),
        markdown_sha256=sha(md_path.read_bytes()), raw_QA_files=len(before),
        minimum_distance_exact=minimum, nearest_names=['M4_Near'],
        name_legacy_semantics_equal_except_trace_id=True)))


if __name__ == '__main__':
    main()
