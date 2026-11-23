"""Independently exercise closed-box boundaries and source binding in the installed service."""

import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys


RUN = Path('D:/he_m1_source_region_world_box_001').resolve()
BASE = '4104add44251b03a1eafc5af69502aa2575b632c'
BOX = {'min': [1., -1., -1.], 'max': [2., 1., 1.]}
SHAPE = 'source_region world_box_m requires min and max 3D arrays'
NUMBER = 'source_region world_box_m bounds must be finite binary64 numbers'
ORDER = 'source_region world_box_m requires min <= max on every axis'
REGION = 'source_region region requires object and exactly one of source_triangle_indices or world_box_m'
OBSERVE = 'human_eye_scene_observe'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def pin(path):
    path = Path(path).resolve(strict=True)
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')
    return hashlib.sha256(raw).hexdigest()


def sign_display(snapshot):
    snapshot.pop('sha256', None)
    snapshot['sha256'] = digest(snapshot)


def capture(vertices, faces):
    names = {'target': 'Target', 'reference': 'Reference'}
    snapshot = {'schema': 'blender-viewport-display-v1', 'scope': 'active_view_layer', 'status': 'captured',
        'view_layer': {'name': 'ViewLayer', 'instance_id': 'rna:owned-control'},
        'objects': [{'host_id': identity, 'instance_id': identity+'-instance', 'visible_get': identity == 'target',
            'hide_get': identity == 'reference', 'hide_viewport': False, 'hide_render': identity == 'reference'}
            for identity in names]}
    sign_display(snapshot)
    items = [
        {'object_id': 'target', 'mark_label': '#B0001', 'name': names['target'],
         'vertices': vertices, 'faces': faces, 'edges': [[0, 1]]},
        {'object_id': 'reference', 'mark_label': '#B0002', 'name': names['reference'],
         'vertices': [[5., -8., -8.], [5., 8., -8.], [5., 8., 8.], [5., -8., 8.]],
         'faces': [[0, 1, 2], [0, 2, 3]], 'edges': [[0, 1], [0, 2], [0, 3], [1, 2], [2, 3]]},
    ]
    return {'unit': 'm', 'coordinate_frame': 'world', 'source': 'blender', 'revision': 'test-geometry-0',
            'capture_state': {'instance_id': 'fixture-worker', 'epoch': 1, 'revision': 1, 'selection_key': 'all'},
            'host_identity': {'schema_version': '1.0', 'capture_scope': 'complete_scene_meshes',
                              'document_epoch': 'a' * 64,
                              'object_instances': {key: key+'-instance' for key in names}},
            'display_snapshot': snapshot, 'meshes': items}


def fixture():
    above, below = math.nextafter(2., math.inf), math.nextafter(1., -math.inf)
    triangles = [
        [(1., -1., -1.), (1., 1., -1.), (2., 0., 1.)],       # all on or inside the planes
        [(1., -1., -1.), (1., 1., -1.), (above, 0., 1.)],      # one vertex one ULP above
        [(0., 0., 0.), (3., -.25, 0.), (3., .25, 0.)],        # intersects with no enclosed vertex
        [(1., .5, 0.), (below, .5, 0.), (.5, .5, 0.)],        # exterior degenerate touches the wall
        [(2., -.5, 0.), (2., 0., 0.), (2., .5, 0.)],          # enclosed degenerate on the wall
        [(below, -.75, 0.), (2., 0., 0.), (2., .75, 0.)],      # one vertex one ULP below
        [(2., .75, .5), (2., -.75, .5), (2., 0., -.5)],
    ]
    vertices = [list(v) for tri in triangles for v in tri]
    return capture(vertices, [list(range(i, i+3)) for i in range(0, len(vertices), 3)])


def rows(mesh, box):
    """Compare exact rationals independently of NumPy and the production indexing."""
    lo = tuple(map(Fraction, box['min']))
    hi = tuple(map(Fraction, box['max']))
    return [i for i, face in enumerate(mesh['faces']) if
            all(lo[axis] <= Fraction(mesh['vertices'][j][axis]) <= hi[axis] for j in face for axis in range(3))]


def query(key, value, obj=None):
    return {'mode': 'source_region', 'region': {'object': obj or {'name': 'Target'}, key: value},
            'reference': {'name': 'Reference'}, 'requested_facts': ['surface_proximity']}


def ref_query(ref):
    return {'mode': 'source_region', 'region_ref': ref, 'reference': {'name': 'Reference'},
            'requested_facts': ['surface_proximity']}


def evidence(result):
    return {key: result[key] for key in ('region_ref', 'source_mapping', 'facts', 'observation_status')} | {
        'task_facts': result['task_result']['facts'], 'reference': result['task_result']['reference']}


class Host:
    def __init__(self, scene):
        self.scene, self.calls, self.lock = scene, 0, None

    def capture_scene(self):
        require(self.lock._is_owned(), 'capture_outside_current_read_lock')
        self.calls += 1
        return self.scene


class Suite:
    def __init__(self, output, binding, live, mcp):
        self.output, self.binding, self.live, self.mcp = output, binding, live, mcp
        self.cases = {}

    def service(self, label, scene):
        folder = self.output/label
        folder.mkdir(exist_ok=False)
        config = folder/'CONFIG.json'
        write(config, {'schema_version': '1.0', 'enabled': True, 'observe_on_prompt': False,
                       'project_root': self.binding['install_root'], 'state_file': str(folder/'state.json'),
                       'audit_file': str(folder/'audit.jsonl'), 'request_budget_s': 30,
                       'expected_identity': {'source_sha256': self.binding['source_sha256']}})
        host = Host(scene)
        service = self.live.LiveSpatialService(config, host=host, production_mode=True)
        host.lock = service._read_context.lock
        return service, host, self.mcp.LiveSpatialMCPServer(service, default_session_id='world-box-controls')

    def observe(self, label, service, host, value, expected, *, hit, image=False):
        before = host.calls
        result = service.observe(label, include_image=image, query=value)
        work = result['work']
        require(host.calls == before + 1 and work['capture_calls'] == 1, 'capture_not_exactly_once/'+label)
        ref = result['region_ref']
        mapping = result['source_mapping'].get('region', result['source_mapping'])
        require(ref['source_triangle_indices'] == expected and mapping['submesh_to_source_triangle_indices'] == expected,
                'ordered_source_rows_not_oracle/'+label)
        require(work['prepare_cache_hit'] is hit, 'canonical_prepare_reuse_changed/'+label)
        if 'world_box_m' in value.get('region', {}):
            stage = result['stages']['world_box_selection']
            require(work['world_box_selection_calls'] == 1 and stage['elapsed_ns'] > 0 and
                    stage['closed_ns']-stage['started_ns'] == stage['elapsed_ns'], 'box_selection_stage/'+label)
        else:
            require(not work.get('world_box_selection_calls') and 'world_box_selection' not in result['stages'],
                    'old_entry_entered_box_selection/'+label)
        self.cases[label] = {'row_count': len(expected), 'facts_sha256': digest(evidence(result)),
                             'ref': ref['region_id'], 'work': work}
        return result

    def reject_service(self, label, service, host, value, expected):
        before = host.calls
        try:
            service.observe(label, include_image=False, query=value)
        except ValueError as exc:
            require(str(exc) == expected, f'wrong_rejection/{label}/{exc}')
        else:
            raise ValueError('invalid_request_accepted/'+label)
        require(host.calls-before == 1, 'wrong_failed_capture_count/'+label)
        self.cases[label] = {'error': expected, 'capture_calls': 1}

    def rpc(self, server, method, parameters, label):
        result = server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': label, 'method': method, 'params': parameters})
        require(result['id'] == label and 'error' not in result, 'invalid_RPC_envelope/'+label)
        return result['result']

    def call(self, server, value, label, *, full=False):
        args = {'query': value, 'include_image': False}
        if full:
            args['response_detail'] = 'full'
        result = self.rpc(server, 'tools/call', {'name': OBSERVE, 'arguments': args}, label)
        require(len(result['content']) == 1 and result['content'][0]['type'] == 'text', 'wrong_plain_content/'+label)
        return result['isError'], json.loads(result['content'][0]['text'])

    def reject_mcp(self, label, server, host, value, expected):
        before = host.calls
        is_error, packet = self.call(server, value, label)
        require(is_error and packet['error'] == expected and host.calls == before,
                'wrong_MCP_schema_rejection/'+label+'/'+str(packet.get('error')))
        self.cases[label] = {'error': packet['error'], 'capture_calls': 0}


def transformed(decoder, protocol):
    """Take both fixture objects through the installed meter-world delta forward map."""
    local = [[0., 0., 0.], [0., .5, 0.], [.5, 0., .25], [2., 0., 0.], [2., .5, 0.], [2.5, 0., .25]]
    scene = capture(local, [[0, 1, 2], [3, 4, 5]])
    resources = []
    pose = [[2., 0., 0., 2.], [0., 3., 0., -1.], [0., 0., 4., 1.], [0., 0., 0., 1.]]
    identity = [[float(j == i) for j in range(4)] for i in range(4)]
    for mesh in scene['meshes']:
        key = 'resource-'+mesh['object_id']
        resources.append({'id': key, 'revision': 1, 'vertices_local': mesh.pop('vertices'),
                          'faces': mesh.pop('faces'), 'edges': mesh.pop('edges')})
        target = mesh['object_id'] == 'target'
        mesh['_scene_resource'] = {'id': key, 'revision': 1, 'matrix': pose if target else identity,
                                  'scale': .5 if target else 1.}
    fixed = decoder().apply({'schema': protocol, 'capture': scene, 'resources': resources,
                            'live_resources': [row['id'] for row in resources]})
    low, high = [1., -.5, .5], [1.5, .25, 1.]
    require(fixed['meshes'][0]['vertices'][:3] == [low, [1., .25, .5], [1.5, -.5, 1.]], 'nonunit_fixture_wrong')
    return fixed, {'min': low, 'max': high}


def legacy(suite):
    scene = fixture()
    expected = rows(scene['meshes'][0], BOX)
    require(expected == [0, 4, 6], 'independent_closed_box_fixture_changed')
    service, host, server = suite.service('legacy', scene)
    original = suite.observe('legacy_reverse_index_order', service, host, query('source_triangle_indices', expected[::-1]),
                             expected, hit=False)
    ref = suite.observe('legacy_ref', service, host, ref_query(original['region_ref']), expected, hit=True)
    require(evidence(original) == evidence(ref), 'legacy_current_ref_result_changed')
    require(original['task_result']['facts']['surface_proximity']['status'] == 'measured'
            and original['binding']['image_scope']['participation_mask'] == [True, False], 'hidden_reference_not_measured')
    brief_error, brief = suite.call(server, query('source_triangle_indices', expected), 'legacy-brief')
    full_error, full = suite.call(server, query('source_triangle_indices', expected), 'legacy-full', full=True)
    require(not (brief_error or full_error) and brief['region_ref'] == full['region_ref'] == original['region_ref'],
            'legacy_brief_full_measurement_changed')
    whole = {'mode': 'task', 'objects': [{'name': 'Target'}, {'name': 'Reference'}],
             'requested_facts': ['surface_proximity']}
    error, packet = suite.call(server, whole, 'ordinary-task')
    require(not error and packet['facts']['surface_proximity']['status'] == 'measured', 'legacy_ordinary_pair_task_failed')
    suite.cases['legacy_public_brief_full_and_ordinary_task'] = {'surface_proximity': packet['facts']['surface_proximity'],
          'brief_sha256': digest(brief['task_result']['facts']), 'full_sha256': digest(full['task_result']['facts'])}
    return original


def syntax(suite):
    _, host, server = suite.service('schema', fixture())
    good = query('world_box_m', BOX)
    both = {**good, 'region': {**good['region'], 'source_triangle_indices': [0]}}
    values = [
        ('both_selection_keys', both, REGION),
        ('region_missing_selection', {**good, 'region': {'object': {'id': 'target'}}}, REGION),
        ('box_missing_axis', query('world_box_m', {'min': [1, -1], 'max': [2, 1, 1]}), SHAPE),
        ('box_excess_axis', query('world_box_m', {'min': [1, -1, -1, 0], 'max': [2, 1, 1]}), SHAPE),
        ('box_extra_members', query('world_box_m', {**BOX, 'unit': 'm'}), SHAPE),
        ('box_missing_max', query('world_box_m', {'min': [1, -1, -1]}), SHAPE),
        ('box_bad_container', query('world_box_m', [BOX['min'], BOX['max']]), SHAPE),
        ('box_inverted_z', query('world_box_m', {'min': [1, -1, 2], 'max': [2, 1, 1]}), ORDER),
        ('ref_cannot_embed_box', ref_query({'world_box_m': BOX}), 'source_region region_ref structure is invalid'),
        ('region_ref_and_box_conflict', {**good, 'region_ref': {}}, 'source_region requires exactly one of region or region_ref'),
    ]
    for label, number in (('bool', True), ('string', '1'), ('overflow', 10**400), ('unrepresentable_integer', 2**53+1),
                          ('nan', float('nan')), ('positive_infinity', float('inf')), ('negative_infinity', -float('inf'))):
        values.append(('box_bad_'+label, query('world_box_m', {'min': [number, -1, -1], 'max': [2, 1, 1]}), NUMBER))
    for label, value, expected in values:
        suite.reject_mcp(label, server, host, value, expected)
    reply = suite.rpc(server, 'tools/list', {}, 'actual-directory')
    tool, = [row for row in reply['tools'] if row['name'] == OBSERVE]
    region = tool['inputSchema']['properties']['query']['properties']['region']
    require(region['additionalProperties'] is False and region['required'] == ['object'] and
            {tuple(choice['required']) for choice in region['oneOf']} == {('source_triangle_indices',), ('world_box_m',)},
            'advertised_region_requires_exact_selection_variant')
    offered = region['properties']['world_box_m']
    require(offered['additionalProperties'] is False and set(offered['required']) == {'min', 'max'} and
            all(axis['type'] == 'array' and axis['minItems'] == axis['maxItems'] == 3 and axis['items']['type'] == 'number'
                for axis in offered['properties'].values()), 'advertised_box_shape_not_closed_triplets')
    error, packet = suite.call(server, good, 'MCP-recovery')
    require(not error and packet['region_ref']['source_triangle_indices'] == [0, 4, 6] and host.calls == 1,
            'rejected_schema_prevented_valid_MCP_recovery')
    suite.cases['actual_catalogue_and_MCP_recovery'] = {'tool_count': len(reply['tools']), 'capture_calls': 1}


def candidate(suite, historical, residency):
    syntax(suite)
    initial = fixture()
    expected = rows(initial['meshes'][0], BOX)
    box = query('world_box_m', BOX)
    explicit = query('source_triangle_indices', expected)
    srv, host, _ = suite.service('box-first', initial)
    cold = suite.observe('fresh_world_box', srv, host, box, expected, hit=False)
    warm = suite.observe('same_world_box_repeat', srv, host, box, expected, hit=True)
    by_id = query('source_triangle_indices', expected, {'id': 'target'})
    old_by_id = suite.observe('box_then_index_by_ID', srv, host, by_id, expected, hit=True)
    equivalent = query('world_box_m', {'min': [1., -1.5, -1.5], 'max': [2., 1.5, 1.5]}, {'id': 'target'})
    same = suite.observe('different_boxes_same_closed_rows', srv, host, equivalent, expected, hit=True)
    require(all(evidence(v) == evidence(historical) for v in (cold, warm, old_by_id, same)), 'canonical_box_evidence_changed')
    srv, host, _ = suite.service('index-first', initial)
    old = suite.observe('index_seed', srv, host, explicit, expected, hit=False)
    after = suite.observe('index_then_box_by_ID', srv, host, query('world_box_m', BOX, {'id': 'target'}), expected, hit=True)
    require(evidence(old) == evidence(after), 'index_first_ref_or_measure_changed')
    wall = {'min': [2., -.5, 0.], 'max': [2., .5, 0.]}
    require(rows(initial['meshes'][0], wall) == [4], 'independent_planar_degenerate_selection')
    single = suite.observe('zero_width_closed_axis_selects_degenerate', srv, host, query('world_box_m', wall), [4], hit=False)
    require(single['work']['geometry_normalization_calls'] == 0 and single['work']['geometry_normalization_shared_hit'],
            'independent_second_region_rebuilt_whole_scene')
    empty = {'min': [100, 0, 0], 'max': [100, 1, 1]}
    suite.reject_service('empty_box', srv, host, query('world_box_m', empty), 'source_region_world_box_empty')
    suite.reject_service('unknown_target', srv, host, query('world_box_m', BOX, {'id': 'absent'}), 'object_not_found')
    altered = deepcopy(initial)
    altered['meshes'][0]['edges'][0][1] = 10000
    host.scene = altered
    suite.reject_service('same_digest_bad_edge_after_prepared_alias', srv, host, box, 'invalid topology indices')
    altered['meshes'][0]['edges'] = [[0, 1]]
    altered['meshes'][0]['pivot_world'] = [0, 0]
    suite.reject_service('same_digest_bad_pivot_after_prepared_alias', srv, host, box, 'invalid pivot_world')
    host.scene = initial
    suite.observe('same_digest_bad_geometry_recovery', srv, host, box, expected, hit=True)

    changed = deepcopy(initial)
    changed['meshes'][0]['faces'].reverse()
    host.scene = changed
    suite.reject_service('same_generation_changed_order_stales_ref', srv, host, ref_query(old['region_ref']),
                         'source_region_ref_ordered_geometry_changed')
    expected = rows(changed['meshes'][0], BOX)
    new = suite.observe('current_reversed_face_order', srv, host, box, expected, hit=False)
    require(new['region_ref'] != old['region_ref'] and new['work']['geometry_normalization_calls'] == 1,
            'reordered_faces_used_old_scope')
    changed['capture_state']['revision'] += 1
    suite.reject_service('new_generation_stales_ref', srv, host, ref_query(new['region_ref']),
                         'source_region_ref_capture_generation_changed')
    suite.observe('new_generation_box_recovery', srv, host, box, expected, hit=False)
    hidden = deepcopy(changed)
    hidden['display_snapshot']['objects'][0].update(visible_get=False, hide_get=True)
    sign_display(hidden['display_snapshot'])
    host.scene = hidden
    out = suite.observe('hidden_selected_geometry_measured', srv, host, box, expected, hit=False, image=True)
    require(out['task_result']['facts']['surface_proximity']['status'] == 'measured' and
            out['binding']['image_scope']['participation_mask'] == [False, False] and
            out['observation_status'] == 'evidence_insufficient' and
            out['facts']['visibility']['reason'] == 'selected_region_not_displayed' and
            out['facts']['visibility']['selected_surface_pixels'] == 0 and
            out['work']['raster_completed'] == 1 and len(out['frames']) == 1, 'hidden_target_wrong_geometry_or_pixels')

    moved, bounds = transformed(residency.SceneDeltaDecoder, residency.PROTOCOL)
    srv, host, _ = suite.service('nonunit', moved)
    require(rows(moved['meshes'][0], bounds) == [0], 'nonunit_world_oracle_disagreed')
    suite.observe('actual_nonunit_delta_world_transform', srv, host, query('world_box_m', bounds), [0], hit=False)
    original_check = srv._check_request_budget
    expired = []

    def expire(stage, *, publication=False):
        if 'world_box' in stage:
            expired.append(stage)
            raise suite.live.RequestBudgetError('expired', stage)
        return original_check(stage, publication=publication)

    before = host.calls
    srv._check_request_budget = expire
    try:
        srv.observe('deadline', include_image=False, query=query('world_box_m', bounds))
    except suite.live.RequestBudgetError as exc:
        require(exc.code == 'live_request_expired' and len(expired) == 1 and host.calls == before+1, 'deadline_cause_wrong')
    else:
        raise ValueError('world_box_deadline_not_checked')
    finally:
        srv._check_request_budget = original_check
    suite.cases['box_deadline_refused_then_recovers'] = {'stage': expired[0], 'capture_calls': 1}
    suite.observe('selection_deadline_recovery', srv, host, query('world_box_m', bounds), [0], hit=True)


def limits(suite):
    vertices = [[1., 0., 0.], [1., .125, 0.], [1.125, 0., .125]]
    scene = capture(vertices, [[0, 1, 2] for _ in range(4096)])
    service, host, _ = suite.service('limits', scene)
    expected = rows(scene['meshes'][0], BOX)
    require(expected == list(range(4096)), '4096_oracle_changed')
    result = suite.observe('exact_4096_included', service, host, query('world_box_m', BOX), expected, hit=False)
    overflow = deepcopy(scene)
    overflow['meshes'][0]['faces'].append([0, 1, 2])
    overflow['capture_state']['revision'] += 1
    host.scene = overflow
    suite.reject_service('exact_4097_rejected', service, host, query('world_box_m', BOX), 'source_region_world_box_triangle_limit')
    host.scene = scene
    suite.observe('4097_recovery_back_to_4096', service, host, ref_query(result['region_ref']), expected, hit=False)


def worker(arm, binding_path, folder):
    binding = read(binding_path)
    candidate_arm = arm == 'B'
    require((binding['preparation_git'] != BASE) is candidate_arm and len(binding['source_manifest']) == 143,
            'isolated_arm_binding_identity')
    install = Path(binding['install_root']).resolve(strict=True)
    sys.path[:0] = [str(install), binding['dependency_root']]
    from human_eye_plugin import live_service, live_spatial_mcp, query_policy, scene_residency, source_region

    manifest = {item['path']: item['sha256'] for item in binding['source_manifest']}
    modules = (live_service, live_spatial_mcp, query_policy, scene_residency, source_region)
    pins = [pin(Path(module.__file__)) for module in modules]
    require(all(row['sha256'] == manifest[Path(row['path']).relative_to(install).as_posix()] for row in pins),
            'imported_runtime_not_verified_installed_arm')
    folder.mkdir(exist_ok=False)
    suite = Suite(folder, binding, live_service, live_spatial_mcp)
    previous = legacy(suite)
    if candidate_arm:
        candidate(suite, previous, scene_residency)
        limits(suite)
    else:
        _, host, server = suite.service('baseline-support', fixture())
        suite.reject_mcp('baseline_reports_no_box_support', server, host, query('world_box_m', BOX),
                         'source_region region requires object and source_triangle_indices')
    write(folder/'ARM.json', {'passed': True, 'commit': binding['preparation_git'], 'arm': arm,
          'source_sha256': binding['source_sha256'], 'cases': suite.cases, 'source_pins': [pin(binding_path), *pins]})


def run(options):
    out = options.output.resolve()
    require(out.is_relative_to(RUN) and out != RUN, 'only_new_bounded_experiment_directory')
    if options.arm:
        worker(options.arm, options.binding, out)
        return
    out.mkdir(parents=True, exist_ok=False)
    reports = {}
    for label, binding in (('A', options.baseline), ('B', options.candidate)):
        slot = out/label
        subprocess.run([sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), '--arm', label,
                        '--binding', str(binding.resolve(strict=True)), '--output', str(slot)], check=True, timeout=180)
        reports[label] = read(slot/'ARM.json')
    a, b = (v['cases'] for v in reports.values())
    common = ('legacy_reverse_index_order', 'legacy_ref', 'legacy_public_brief_full_and_ordinary_task')

    def without_clocks(result):
        value = deepcopy(result)
        value.get('work', {}).get('task_query', {}).pop('stages', None)
        return value

    require(all(without_clocks(a[key]) == without_clocks(b[key]) for key in common),
            'old_row_ref_or_whole_object_facts_changed')
    cases = {arm: report['cases'] for arm, report in reports.items()}
    write(out/'RESULT.json', {'passed': True, 'actual_new_Blender': 0, 'actual_new_models': 0,
          'reported_rasters': sum(r.get('work', {}).get('raster_completed', 0) for group in cases.values() for r in group.values()),
          'cases': cases, 'baseline': reports['A']['commit'], 'candidate': reports['B']['commit'],
          'source_pins': [pin(Path(__file__)), pin(sys.executable), *[item for arm, proof in reports.items()
              for item in [pin(out/arm/'ARM.json'), *proof['source_pins']]]]})
    print(json.dumps({'passed': True, 'counts': {k: len(v) for k,v in cases.items()}}), flush=True)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_Python_flags')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--baseline', type=Path)
    cli.add_argument('--candidate', type=Path)
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--arm', choices=('A', 'B'))
    cli.add_argument('--binding', type=Path)
    options = cli.parse_args()
    require(bool(options.arm and options.binding) if options.arm else bool(options.baseline and options.candidate),
            'both_isolated_bindings_required')
    run(options)
