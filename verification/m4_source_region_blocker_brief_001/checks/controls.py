"""Replay archived and derived controls through both installed MCP serializers."""

import argparse
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from time import perf_counter_ns
from types import SimpleNamespace


V = Path(__file__).resolve().parents[2]
BASE = V / 'm1_source_region_default_measurement_entry_001/install/PRODUCT_RUN_BINDING.json'
BASE_SOURCE = '73e28f8e9b334a386c95b785aa3698e5171795fae9bffc9ea4e73403344f33b4'
PRIOR = V / 'm1_joint_full_task_tail_001/checks/controls.py'
SAMPLED = V / 'm1_source_region_sampled_image_path_001/checks/controls.py'
DUAL = 'perf050_dual_region_occlusion_transfer_001'
ORIGINAL_ROWS = [['SCENE', 8, 1], ['TOP', 8, 0], ['LEFT', 8, 0],
                 ['RIGHT', 8, 1], ['FRONT', 8, 1], ['BACK', 8, 0]]
TABLE_COLUMNS = ['view_name', 'blocker_object_index', 'source_triangle_index']
TINY_AREA = Fraction(1, 2**41)
EXPECTED_ERRORS = {
    'actual_archived_bad_request': (
        'task set requires surface_proximity with closed_solid_relation or spatial_relation and optional aabb'),
    'request_rejects_empty_selection': 'source_triangle_indices requires 1..4096 unique nonnegative integer rows',
    'wrong_region_ref': 'source_region_result_scope_mismatch',
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def get_proof(path):
    data = read(path)
    controls = data['derived_controls']
    positive = controls['TOP_tiny_positive_partial']
    require(Fraction(positive['area']) == TINY_AREA and Fraction(positive['selection_fraction']) == Fraction(1, 2**35)
            and (positive['same_object_index_if_appended'], positive['same_object_unselected_source_triangle_if_appended'])
            == (2, 2) and Fraction(controls['TOP_equal_depth_occlusion_area']) == 0
            and Fraction(controls['TOP_edge_touch_occlusion_area']) == 0, 'independent_geometry_controls_differ')
    return {'geometry_proof': pin(path), 'derived_control_facts': controls}


def derive_geometry(producer, source_region):
    """Exercise the installed classifier on exact synthetic TOP geometry without a raster."""
    binding = producer['binding']
    facts = producer['facts']['region']
    selected = tuple(tuple(Fraction(value) for value in point) for point in facts['vertices_world_m'])
    faces = tuple(tuple(row) for row in facts['triangles_source_vertices'])
    top, = [pose for pose in binding['camera_specification']['views'] if pose['name'] == 'TOP']
    center = Fraction(2)
    edge = Fraction(33, 16)
    small = Fraction(1, 2**20)
    front = Fraction(9, 8)
    raised = ((center, center, front), (center + small, center, front), (center, center + small, front))
    level = tuple((x, y, Fraction(1)) for x, y, _ in raised)
    touching = ((edge, center, front), (edge + small, center, front), (edge, center + small, front))
    checkpoint = lambda _phase: None

    def classify(triangle, *, own=False, hidden=False):
        objects = [((), (), row['host_id'], row['object_name']) for row in binding['objects']]
        vertices = selected + triangle if own else selected
        selected_faces = faces + ((4, 5, 6),) if own else faces
        objects[2] = (vertices, selected_faces, *objects[2][2:])
        if not own:
            objects[8] = (triangle, ((0, 1, 2),), *objects[8][2:])
        region, = source_region.partition_regions(objects, target_object_index=2)[0]
        require(region.triangle_indices == (0, 1), 'derived_fixture_changed_selected_region')
        mask = [True] * len(objects)
        mask[8] = not hidden
        prepared = SimpleNamespace(objects=objects, binding={'image_scope': {'participation_mask': mask}})
        blockers = source_region._displayed_front_triangles(prepared, region, checkpoint)
        return source_region._classify_view(region, blockers, top, checkpoint)

    derived = {'tiny': classify(raised), 'self': classify(raised, own=True), 'equal': classify(level),
               'edge': classify(touching), 'hidden': classify(raised, hidden=True)}
    expected = {'object_index': 8, 'source_triangle_index': 0, 'overlap_area_screen_exact': str(TINY_AREA)}
    require(derived == {
        'tiny': {'status': 'positive_area_occlusion', 'first_blocker': expected},
        'self': {'status': 'positive_area_occlusion',
                 'first_blocker': dict(expected, object_index=2, source_triangle_index=2)},
        'equal': {'status': 'equal_depth_ownership_unknown', 'first_tie': expected},
        'edge': {'status': 'complete'}, 'hidden': {'status': 'complete'},
    }, 'installed_TOP_geometry_changed_or_disagrees_with_independent_exact_truth')
    return derived


def build_cases(source_region):
    prior = run_path(str(PRIOR))
    sampled = run_path(str(SAMPLED))
    specs = {
        'blocked': (DUAL, 'P1', 4),
        'complete': ('m4_source_region_active_view_001', 'B', 1),
        'warm_complete': ('m4_source_region_active_view_001', 'B', 2),
        'no_image': ('perf050_source_scope_rank_transfer_recovery_001', 'P1', 3),
        'sampled': ('perf050_source_scope_rank_transfer_recovery_001', 'P1', 2),
        'target': prior['M09'],
        'region_task': prior['REGION_FOUR'],
        'error': prior['BAD_M09'],
    }
    fixtures = {name: prior['Fixture'](V, spec, invalid=name == 'error') for name, spec in specs.items()}
    cursor = sampled['CopiedArchiveFixture']
    fixtures.update(
        hidden=cursor(4),
        zero=cursor(2),
        ordinary=cursor(1, archive_directory=V / 'm4_m5_source_region_001',
                        run_directory=Path('D:/he_m4_m5_source_region_001')),
    )
    authored = fixtures['blocked'].producer
    geometry = derive_geometry(authored, source_region)
    require(authored['facts']['visibility']['complete_witness'] is None, 'blocker_fixture_has_complete_witness')
    require([[row['view_name'], row['first_blocker']['object_index'], row['first_blocker']['source_triangle_index']]
             for row in authored['view_attempts']] == ORIGINAL_ROWS, 'blocker_fixture_original_rows_changed')
    complete = fixtures['complete'].producer
    require([(row['view_name'], row['status']) for row in complete['view_attempts']]
            == [('SCENE', 'positive_area_occlusion'), ('TOP', 'complete'),
                ('LEFT', 'positive_area_occlusion'), ('RIGHT', 'complete')]
            and complete['facts']['visibility']['complete_witness']['view_name'] == 'RIGHT',
            'expected_historical_RIGHT_complete_after_two_blockers')
    cases = {}

    def case(name, fixture='blocked', *, mutate=None, expected=None, error=False, original=False,
             observations=None):
        source = fixtures[fixture]
        query, value = deepcopy(source.request), deepcopy(source.producer)
        if mutate is not None:
            mutate(query['params']['arguments'], value)
        cases[name] = {'fixture': source, 'request': query, 'producer': value, 'expected': expected,
                       'error': error, 'is_unmodified_archived_call': original,
                       'observations': int(not error) if observations is None else observations}

    case('actual_P1_4_blockers', expected=ORIGINAL_ROWS, original=True)
    case('historical_N15_RIGHT_full_witness_cold', 'complete', original=True)
    case('historical_N15_RIGHT_full_witness_warm', 'warm_complete', original=True)
    case('explicit_full', mutate=lambda args, value: args.update(response_detail='full'))
    case('omitted_brief_default', mutate=lambda args, value: args.pop('response_detail'), expected=ORIGINAL_ROWS)
    for name in ('no_image', 'sampled', 'target', 'region_task', 'hidden', 'zero', 'ordinary'):
        case('historical_' + name, name, original=True)
    case('actual_archived_bad_request', 'error', error=True, original=True)

    def no_classification(_args, value):
        value.pop('view_attempts')
        value['facts']['visibility']['geometry_status'] = 'unknown'

    case('unclassified_no_attempts', mutate=no_classification)
    case('unknown_measurement_preserved',
         mutate=lambda args, v: v['task_result'].update(status='unknown'), expected=ORIGINAL_ROWS)
    case('request_rejects_empty_selection',
         mutate=lambda args, v: args['query']['region'].update(source_triangle_indices=[]), error=True)
    case('wrong_region_ref',
         mutate=lambda args, v: v['task_result']['region_ref'].update(region_id='source-region:' + '0' * 64),
         error=True, observations=1)
    case('wrong_binding_identity',
         mutate=lambda args, v: v['task_result']['binding'].update(ordered_geometry_sha256='0' * 64))
    case('wrong_frame_identity',
         mutate=lambda args, v: v['view_attempts'][0].update(frame_identity='0' * 64))
    case('wrong_FRAME_display_identity',
         mutate=lambda args, v: v['frames'][0].update(display_identity='0' * 64))
    case('duplicate_angle',
         mutate=lambda args, v: v['view_attempts'][2].update(view_name='TOP'))
    case('wrong_angle_order',
         mutate=lambda args, v: v['view_attempts'].__setitem__(
             slice(1, 3), list(reversed(v['view_attempts'][1:3]))))
    def display_row(value, **updates):
        for container in (value['binding'], value['task_result']['binding'], value['facts']['visibility'],
                          value['frames'][0], value['constructed_frames'][0]):
            scope = container['image_scope']
            scope['objects'][8].update(updates)
            if updates.get('participates') is False:
                scope['participation_mask'][8] = False
                scope['participating_object_indices'].remove(8)
                scope['excluded_object_indices'].append(8)

    case('hidden_display_blocker_identity',
         mutate=lambda args, v: display_row(v, participates=False, visible_get=False, hide_get=True))
    case('wrong_object_instance', mutate=lambda args, v: display_row(v, instance_id='invalid'))
    case('wrong_object_index',
         mutate=lambda args, v: v['view_attempts'][1]['first_blocker'].update(object_index=99),
         expected=[row for row in ORIGINAL_ROWS if row[0] != 'TOP'])
    case('wrong_source_index',
         mutate=lambda args, v: v['view_attempts'][1]['first_blocker'].update(source_triangle_index=9000),
         expected=[row for row in ORIGINAL_ROWS if row[0] != 'TOP'])
    case('bool_is_not_source_index',
         mutate=lambda args, v: v['view_attempts'][1]['first_blocker'].update(source_triangle_index=True),
         expected=[row for row in ORIGINAL_ROWS if row[0] != 'TOP'])

    def blocker_row(value, *, area, owner=8, triangle=0, status='positive_area_occlusion'):
        row = value['view_attempts'][1]
        row['status'] = status
        row['first_blocker'].update(object_index=owner, source_triangle_index=triangle,
                                    overlap_area_screen_exact=area)

    original_without_TOP = [row for row in ORIGINAL_ROWS if row[0] != 'TOP']
    tiny = str(TINY_AREA)
    def classified_TOP(value, kind):
        row = value['view_attempts'][1]
        row.pop('first_blocker')
        row.update(deepcopy(geometry[kind]))

    case('tiny_positive_partial', mutate=lambda args, v: classified_TOP(v, 'tiny'), expected=ORIGINAL_ROWS)
    case('equal_depth_does_not_certify', mutate=lambda args, v: classified_TOP(v, 'equal'),
         expected=original_without_TOP)
    def tied_blocker(_args, value):
        value['view_attempts'][1]['first_tie'] = deepcopy(value['view_attempts'][1]['first_blocker'])

    case('contradictory_depth_tie_untrusted', mutate=tied_blocker, expected=original_without_TOP)
    case('zero_area_does_not_certify',
         mutate=lambda args, v: classified_TOP(v, 'edge'), expected=original_without_TOP)
    case('reported_zero_area_does_not_certify',
         mutate=lambda args, v: blocker_row(v, area='0'), expected=original_without_TOP)
    case('invalid_exact_area',
         mutate=lambda args, v: blocker_row(v, area='1/0'), expected=original_without_TOP)
    case('same_object_unselected_face',
         mutate=lambda args, v: classified_TOP(v, 'self'),
         expected=[ORIGINAL_ROWS[0], ['TOP', 2, 2], *ORIGINAL_ROWS[2:]])
    case('same_object_selected_face_does_not_certify',
         mutate=lambda args, v: blocker_row(v, area=tiny, owner=2, triangle=0),
         expected=original_without_TOP)
    evidence = {item['path']: item for fx in fixtures.values() for item in fx.pins}
    return cases, list(evidence.values()), geometry


def worker(binding_path, output):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp, source_region
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.runtime_identity import runtime_identity

    identity = runtime_identity()
    require(identity['source_kind'] == 'installed_distribution' and identity['source_sha256'] == binding['source_sha256']
            and Path(mcp.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve()),
            'wrong_isolated_runtime')
    output.mkdir(parents=True)
    cases, sources, geometry = build_cases(source_region)

    class ReplayService:
        request_budget_s = None
        _request_budget = LiveSpatialService._request_budget
        request_error_fields = staticmethod(LiveSpatialService.request_error_fields)

        def __init__(self, case):
            self.case = case
            self.state_path = case['fixture'].state
            self.observations = 0
            self.closed = False
            self.budgets, self.deliveries = [], []

        def observe(self, _session, **kwargs):
            args = self.case['request']['params']['arguments']
            require(kwargs['query'] == args['query']
                    and kwargs.get('include_image', True) == args.get('include_image', True),
                    'actual_observe_arguments_changed')
            self.observations += 1
            require(self.case['producer'] is not None, 'error_fixture_reached_observe')
            return deepcopy(self.case['producer'])

        def _check_request_budget(self, phase, *, publication=False):
            self.budgets.append((phase, publication))

        def record_event(self, event, **data):
            if event in ('source_region_mcp_content', 'active_observation_mcp_content'):
                self.deliveries.append(data['image_delivery'])

        def close(self):
            self.closed = True

    def invoke(case):
        service = ReplayService(case)
        request = case['request']
        incoming = json.dumps(request, ensure_ascii=False) + '\n'
        outgoing = StringIO(newline='\r\n')
        start = perf_counter_ns()
        mcp.run_stdio_mcp_server(service, input_stream=StringIO(incoming), output_stream=outgoing)
        elapsed = perf_counter_ns() - start
        wire = outgoing.getvalue().encode()
        reply = json.loads(wire)
        require(reply['id'] == request['id'] and reply['jsonrpc'] == '2.0' and service.closed,
                'MCP_alignment_or_EOF_changed')
        return service, reply, incoming.encode(), wire, elapsed

    replay = {}
    for name, case in cases.items():
        service, reply, tx, rx, elapsed = invoke(case)
        transmit, receive = output / (name + '_TX.bin'), output / (name + '_RX.bin')
        transmit.write_bytes(tx)
        receive.write_bytes(rx)
        failed = 'error' in reply or reply['result']['isError']
        text = reply['result']['content'][0]['text'] if 'result' in reply else ''
        require(failed == case['error'], 'unexpected_case_error/' + name)
        error_reason = json.loads(text).get('error') if failed and text else None
        if failed:
            require(error_reason == EXPECTED_ERRORS[name], 'unexpected_error_reason/' + name)
        require(service.observations == case['observations'], 'wrong_observation_count/' + name)
        replay[name] = {
            'expected_rows': case['expected'], 'unmodified_archived_call': case['is_unmodified_archived_call'],
            'MCP_TX': pin(transmit), 'MCP_RX': pin(receive), 'same_as_archived_wire': rx == case['fixture'].original_inner
            if hasattr(case['fixture'], 'original_inner') else None,
            'serialized_text_bytes': len(text.encode()), 'error': failed, 'error_reason': error_reason, 'EOF': service.closed,
            'observations': service.observations, 'budget_phases': service.budgets, 'stdio_elapsed_ns': elapsed,
            'image_delivery': service.deliveries,
        }
    return {'identity': identity, 'binding': pin(binding_path), 'cases': replay, 'sealed_sources': sources,
            'installed_TOP_geometry_controls': geometry}


def compare(before, after):
    require(before['identity']['source_sha256'] == BASE_SOURCE
            and after['identity']['source_sha256'] != BASE_SOURCE, 'baseline_or_candidate_source')
    require(before['cases'].keys() == after['cases'].keys() and before['sealed_sources'] == after['sealed_sources'],
            'case_roster_or_sealed_source_changed')
    require(before['installed_TOP_geometry_controls'] == after['installed_TOP_geometry_controls'],
            'installed_geometry_contract_changed')
    outcomes = {}
    for name, base in before['cases'].items():
        candidate = after['cases'][name]
        require(candidate['MCP_TX']['sha256'] == base['MCP_TX']['sha256']
                and candidate['error'] == base['error'] and candidate['observations'] == base['observations']
                and candidate['budget_phases'] == base['budget_phases'], 'scope_or_dispatch_changed/' + name)
        a, b = (Path(arm['MCP_RX']['path']).read_bytes() for arm in (base, candidate))
        expected = base['expected_rows']
        if expected is None:
            require(a == b, 'unchanged_wire_differs/' + name)
            outcomes[name] = {'result': 'byte_identical', 'text_delta_B': 0}
            continue
        before_rpc, after_rpc = json.loads(a), json.loads(b)
        base_text, new_text = [rpc['result']['content'][0] for rpc in (before_rpc, after_rpc)]
        original, projected = json.loads(base_text['text']), json.loads(new_text['text'])
        evidence = projected.pop('blocker_evidence', None)
        require(isinstance(evidence, dict) and evidence['columns'] == TABLE_COLUMNS
                and evidence['rows'] == expected and isinstance(evidence.get('meaning'), str),
                'invalid_blocker_table/' + name)
        require(json.dumps(projected, ensure_ascii=False) == json.dumps(original, ensure_ascii=False),
                'fields_other_than_evidence_changed/' + name)
        new_text['text'] = base_text['text']
        require(before_rpc == after_rpc, 'image_blocks_or_transport_changed/' + name)
        outcomes[name] = {'result': 'additive_only', 'rows': expected,
                          'text_delta_B': candidate['serialized_text_bytes'] - base['serialized_text_bytes']}
    return outcomes


def summarize(full_report, output):
    report = read(full_report)
    a, b = report['A_B']
    controls = {}
    for name, outcome in report['outcomes'].items():
        pairs = [arm['cases'][name] for arm in (a, b)]
        controls[name] = {**outcome, 'MCP_RX_sha256': [row['MCP_RX']['sha256'] for row in pairs],
                          'body_bytes': [row['serialized_text_bytes'] for row in pairs],
                          'wire_bytes': [row['MCP_RX']['bytes'] for row in pairs]}
        if pairs[0]['error']:
            controls[name]['actual_error_reason'] = pairs[0]['error_reason']
    summary = {
        'archive_record': pin(full_report),
        'source_sha256_A_B': [arm['identity']['source_sha256'] for arm in (a, b)],
        'passed': report['passed'], 'planned': report['planned'],
        'byte_identical': sum(row['result'] == 'byte_identical' for row in controls.values()),
        'additive_only': sum(row['result'] == 'additive_only' for row in controls.values()),
        'geometry': report['independent_derived_geometry'], 'derived_contract': report['derived_contract'],
        'installed_TOP_geometry_controls': a['installed_TOP_geometry_controls'],
        'controls': controls,
    }
    write(output, summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, help='run one separately installed arm')
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--geometry-proof', type=Path)
    parser.add_argument('--summary', type=Path, help='write a compact index in addition to full replay records')
    args = parser.parse_args()
    if args.worker:
        write(args.output / 'REPLAY.json', worker(args.worker, args.output))
        return
    require(args.candidate is not None, 'candidate_install_binding_required')
    require(args.geometry_proof is not None, 'independent_geometry_proof_required')
    proof = get_proof(args.geometry_proof)
    args.output.mkdir(parents=True)
    reports = []
    for arm, binding in (('A', BASE), ('B', args.candidate)):
        out = args.output / arm
        completed = subprocess.run([sys.executable, '-I', str(Path(__file__).resolve()), '--worker',
                                    str(binding.resolve()), '--output', str(out.resolve())],
                                   capture_output=True, check=False)
        (args.output / (arm + '_WORKER_STDERR.bin')).write_bytes(completed.stderr)
        require(completed.returncode == 0, '{} worker failed. {}'.format(arm, completed.stderr.decode(errors='replace')))
        reports.append(read(out / 'REPLAY.json'))
    outcomes = compare(*reports)
    passed = {'passed': len(outcomes), 'planned': len(outcomes), 'outcomes': outcomes, 'A_B': reports,
              'independent_derived_geometry': proof,
              'derived_contract': ('Both installations classified exact derived TOP plane controls without a raster. '
                                   'Only the TOP producer metadata is replaced for MCP replay. The original SCENE '
                                   'image remains historic and is unrelated to the derived TOP geometry.')}
    write(args.output / 'CONTROLS.json', passed)
    if args.summary:
        summarize(args.output / 'CONTROLS.json', args.summary)
    print(json.dumps({'passed': len(outcomes), 'report': pin(args.output / 'CONTROLS.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
