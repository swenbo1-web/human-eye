"""Synthetic normal-entry M5 checks with no live host, raster or image call."""

from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import sys
import traceback
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(1, 'D:/he_anchor_001/venv/Lib/site-packages')

from human_eye_plugin.active_observation_host import source_binding
from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.blender_host import _observation_target_cameras
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import _tool_result, _validate_arguments
from human_eye_plugin.query_policy import validate_query
from human_eye_plugin.read_context import ReadContext
from human_eye_plugin.task_query import bind_objects
import human_eye_plugin.task_query as task_module


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def mesh(oid, name, vertices, faces):
    return {'object_id': oid, 'name': name, 'mark_label': oid,
        'vertices': vertices, 'faces': faces, 'edges': [],
        'local_axes': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
        'pivot_world': [0., 0., 0.], 'axes_source': 'host',
        'axes_confidence': 'explicit', 'axes_reason': 'synthetic_world_fixture',
        'color_rgb': [180, 190, 205]}


class SyntheticHost:
    def __init__(self):
        self.items = [
            mesh('real-far', 'Far', [[1., 0., 0.], [1., 0., 1.], [1., 1., 1.], [1., 1., 0.]], [[0, 1, 2], [0, 2, 3]]),
            mesh('real-near', 'Near', [[.25, .2, .2], [.25, .3, .2], [.25, .2, .3]], [[0, 1, 2]]),
            mesh('real-extra', 'Extra', [[51., 50., 50.], [51., 50., 51.], [51., 51., 51.]], [[0, 1, 2]]),
        ]
        self.instances = {item['object_id']: 'instance-' + item['object_id'] for item in self.items}
        self.calls = []
        self.mutate_supplement = None

    def identity(self, items, scope):
        return {'schema_version': '1.0', 'document_epoch': 'd' * 64,
            'capture_scope': scope, 'object_instances': {item['object_id']: self.instances[item['object_id']] for item in items}}

    def packet(self, items, scope, selection_key):
        return {'unit': 'm', 'coordinate_frame': 'world', 'source': 'blender', 'revision': 'blender:synthetic',
            'capture_scope': scope, 'meshes': copy.deepcopy(items), 'host_identity': self.identity(items, scope),
            'capture_state': {'instance_id': 'synthetic-host', 'epoch': 1, 'revision': 1, 'selection_key': selection_key}}

    def target_packet(self, selector):
        selected = self.items[:2]
        packet = self.packet(selected, 'target_observation_meshes', 'visual-selection')
        rows = []
        bounds = []
        for item in self.items:
            low = [min(point[axis] for point in item['vertices']) for axis in range(3)]
            high = [max(point[axis] for point in item['vertices']) for axis in range(3)]
            bounds.append([low, high])
            rows.append({'object_id': item['object_id'], 'name': item['name'],
                'instance_id': self.instances[item['object_id']], 'bounds_world_m': [low, high]})
        packet['observation_target'] = {'schema': 'active-observation-target-v1', 'selector': copy.deepcopy(selector),
            'target_object_id': self.items[0]['object_id'], 'target_instance_id': self.instances[self.items[0]['object_id']],
            'target_object_index': 0, 'camera_plan': _observation_target_cameras(self.items[0]['vertices'], bounds),
            'scene_directory': rows, 'full_scene_identity': self.identity(self.items, 'complete_scene_meshes'),
            'retained_object_ids': [item['object_id'] for item in selected],
            'excluded_object_ids': [self.items[2]['object_id']], 'directory_sha256': digest(rows),
            'source_frame': {'frame': 1, 'subframe': 0., 'scale_length': 1.}, 'work': {}}
        return packet

    def capture_active_observation(self, selector, deadline, maximum):
        self.calls.append({'operation': 'active', 'selectors': [copy.deepcopy(selector)]})
        return self.target_packet(selector)

    def capture_scene(self):
        self.calls.append({'operation': 'full'})
        return self.packet(self.items, 'complete_scene_meshes', 'full-selection')

    def capture_task_scene(self, selectors):
        self.calls.append({'operation': 'task', 'selectors': copy.deepcopy(selectors)})
        bound, bindings, reason = bind_objects({'meshes': self.items}, selectors)
        ids = {item['object_id'] for item in bound if item is not None}
        packet = self.packet([item for item in self.items if item['object_id'] in ids], 'selected_objects', 'different-task-selection')
        packet['task_selection'] = {'selectors': copy.deepcopy(selectors), 'bindings': bindings,
            'pair_reason': reason, 'candidate_count': len(self.items)}
        if self.mutate_supplement is not None:
            self.mutate_supplement(packet)
        return packet


class SyntheticService(LiveSpatialService):
    def __init__(self, host, output):
        self.host = host
        self.config = {'enabled': True}
        self.state_path = output / 'state.json'
        self._read_context = ReadContext()
        self._identity = {'source_sha256': 'a' * 64}
        self.request_budget_s = 30.
        self.events = []

    def _read_source_identity(self):
        return None, {'status': 'loaded_generation', 'source_check_scope': 'synthetic_loaded_source'}

    @contextmanager
    def request_trace(self, *args, **kwargs):
        yield None

    def _remember_execution_result(self, result):
        pass

    def record_event(self, event, **fields):
        self.events.append({'event': event, **copy.deepcopy(fields)})


PAIR = {'mode': 'task', 'objects': [{'name': 'Far'}, {'name': 'Near'}], 'requested_facts': ['surface_proximity']}


def main():
    output = HERE / 'product_v1_pure_01'
    output.mkdir(exist_ok=False)
    checks = []

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    def fresh():
        host = SyntheticHost()
        return host, SyntheticService(host, output)

    def query(task=PAIR):
        return {'mode': 'active_observation', 'objects': [{'name': 'Far'}], 'task_query': copy.deepcopy(task)}

    def expect_rejection(name, operation, expected):
        try:
            operation()
        except ValueError as error:
            check(name, str(error) == expected, str(error))
        else:
            check(name, False)

    host, service = fresh()
    original = host.target_packet({'name': 'Far'})
    with patch('human_eye_plugin.task_query.measure_surface_proximity', wraps=task_module.measure_surface_proximity) as solver, \
         patch('human_eye_plugin.active_observation_images.rasterize_attention', side_effect=AssertionError('raster forbidden')):
        value = service.observe('synthetic', query=query(), include_image=False)
    save(output / 'MAIN_SERVICE_RESULT.json', value)
    check('main_uses_one_parent_capture_and_no_supplement', host.calls == [{'operation': 'active', 'selectors': [{'name': 'Far'}]}])
    check('main_M3_solver_exactly_once', solver.call_count == 1 and value['work']['task_query']['surface_pair_count'] == 1)
    fact = value['task_result']['facts']['surface_proximity']
    check('main_analytic_distance', fact['status'] == 'measured' and fact['value']['distance_m'] == .75, fact)
    check('no_quantitative_raster', value['work']['task_query']['additional_raster_attempts'] == 0 and not value['frames'])
    source = value['task_result']['binding']['observation_source']
    check('whole_object_scope_and_honest_parent', source['measurement_scope'] == 'whole_objects'
        and source['parent_capture_scope'] == value['binding']['capture_scope'] == 'target_observation_meshes'
        and value['task_result']['binding']['capture_scope'] == 'observation_task_objects')
    check('same_generation_different_selection_allowed', all(source['capture_state'][key] == value['binding']['capture_state'][key]
        for key in ('instance_id', 'epoch', 'revision')) and source['capture_state']['selection_key'] != value['binding']['capture_state']['selection_key'])
    check('full_source_face_ranges', [item['source_triangle_index_ranges'] for item in source['objects']] == [[[0, 1]], [[0, 0]]])
    check('parent_original_unchanged', original == host.target_packet({'name': 'Far'}))
    brief = json.loads(_tool_result(value, is_error=False)['content'][0]['text'])
    full = json.loads(_tool_result(value, is_error=False, response_detail='full')['content'][0]['text'])
    check('brief_and_full_deliver_same_complete_task_result', brief.get('schema') == 'active-observation-brief-v5'
        and brief['task_result'] == full['task_result'] == value['task_result'])
    save(output / 'MAIN_BRIEF.json', brief)
    save(output / 'MAIN_FULL.json', full)
    host, service = fresh()
    default = service.observe('synthetic', query={'mode': 'active_observation', 'objects': [{'name': 'Far'}]}, include_image=False)
    check('original_observation_has_no_added_task_result', 'task_result' not in default and 'task_query' not in default['work'])
    host, service = fresh()
    ordinary = service.observe('synthetic', query=PAIR, include_image=False)
    check('task_only_retains_original_selected_path', [row['operation'] for row in host.calls] == ['task']
        and ordinary['binding']['capture_scope'] == 'selected_objects' and 'observation_source' not in ordinary['binding'])
    host, service = fresh()
    missing_query = copy.deepcopy(PAIR)
    missing_query['objects'][1] = {'name': 'Extra'}
    missing = service.observe('synthetic', query=query(missing_query), include_image=False)
    check('supplement_only_missing_real_id', host.calls[1] == {'operation': 'task', 'selectors': [{'id': 'real-extra'}]}
        and len(host.calls) == 2)
    source_missing = missing['task_result']['binding']['observation_source']['objects'][1]
    check('supplement_not_claimed_in_original_image', source_missing['observation_object_index'] is None and source_missing['geometry_id'] is None)
    for name, mutation, reason in (
        ('changed_revision', lambda packet: packet['capture_state'].update(revision=2), 'active_observation_task_generation_changed'),
        ('changed_epoch', lambda packet: packet['capture_state'].update(epoch=2), 'active_observation_task_generation_changed'),
        ('changed_host_instance', lambda packet: packet['capture_state'].update(instance_id='replaced-host'), 'active_observation_task_generation_changed'),
        ('missing_generation', lambda packet: packet.pop('capture_state'), 'active_observation_task_generation_unavailable'),
        ('changed_document', lambda packet: packet['host_identity'].update(document_epoch='e' * 64), 'active_observation_task_document_epoch_changed'),
        ('same_name_replacement', lambda packet: packet['host_identity']['object_instances'].update({'real-extra': 'new-instance'}), 'active_observation_task_instance_changed'),
    ):
        host, service = fresh()
        host.mutate_supplement = mutation
        expect_rejection(name, lambda: service.observe('synthetic', query=query(missing_query), include_image=False), reason)
        check(name + '_before_render', not any(row['event'] == 'active_observation_render_attempt' for row in service.events))
    host, service = fresh()
    host.items[2]['name'] = 'Near'
    ambiguous = service.observe('synthetic', query=query(), include_image=False)
    check('global_directory_name_ambiguity_preserved', ambiguous['task_result']['binding']['objects'][1]['reason'] == 'object_name_ambiguous'
        and [row['operation'] for row in host.calls] == ['active'])
    host, service = fresh()
    same = copy.deepcopy(PAIR)
    same['objects'][1] = {'id': 'real-far'}
    same_result = service.observe('synthetic', query=query(same), include_image=False)
    check('same_object_pair_reason_preserved', same_result['task_result']['facts']['surface_proximity']['reason'] == 'pair_selectors_resolve_to_same_object')
    host, service = fresh()
    captured = host.target_packet({'name': 'Far'})
    parent = source_binding(captured)
    view, _, _ = service._observation_task_view(captured, parent, PAIR)
    expect_rejection('old_task_entry_rejects_derived_scope', lambda: _validated_scene(view, _task_capture=True),
        'Scene capture_scope does not match this observation entry')
    host.items[1]['vertices'] = copy.deepcopy(host.items[0]['vertices'])
    host.items[1]['faces'] = copy.deepcopy(host.items[0]['faces'])
    captured = host.target_packet({'name': 'Far'})
    view, aliases, _ = service._observation_task_view(captured, source_binding(captured), PAIR)
    check('identical_geometry_alias_does_not_collapse_real_objects', len(aliases) == 2
        and aliases[0]['geometry_id'] == aliases[1]['geometry_id']
        and aliases[0]['object_id'] != aliases[1]['object_id']
        and [item['observation_object_index'] for item in aliases] == [0, 1])
    host, service = fresh()
    host.items[0]['vertices'] = [[1., 0., 0.], [1., 1., 0.], [1., 0., 1.], [2., 0., 0.]]
    host.items[0]['faces'] = [[0, 1, 2], [0, 2, 3]]
    captured = host.target_packet({'name': 'Far'})
    first_view, first_sources, _ = service._observation_task_view(captured, source_binding(captured), PAIR)
    host.items[0]['faces'].reverse()
    changed = host.target_packet({'name': 'Far'})
    second_view, second_sources, _ = service._observation_task_view(changed, source_binding(changed), PAIR)
    check('folded_source_faces_and_current_coordinates_kept', first_view['meshes'][0]['vertices'] == captured['meshes'][0]['vertices']
        and first_view['meshes'][0]['faces'] == [[0, 1, 2], [0, 2, 3]] and first_sources[0]['source_triangle_count'] == 2)
    check('ordered_face_change_invalidates_reference_even_same_geometry', first_sources[0]['geometry_id'] == second_sources[0]['geometry_id']
        and first_sources[0]['ordered_geometry_sha256'] != second_sources[0]['ordered_geometry_sha256']
        and first_view['revision'] != second_view['revision'])
    for nested in ([PAIR], {**PAIR, 'geometry': {}}, {'mode': 'task', 'target': {'name': 'Far'}, 'candidates': [{'name': 'Near'}], 'requested_facts': ['surface_proximity']}):
        expect_rejection('reject_nonlegacy_optional_shape_' + str(len(checks)),
            lambda: validate_query({'mode': 'active_observation', 'task_query': nested}),
            'active_observation task_query requires legacy task mode, objects and requested_facts')
    _validate_arguments('human_eye_scene_observe', {'session_id': 'synthetic', 'query': query(), 'include_image': False})
    check('normal_MCP_argument_validation_accepts_optional_query', True)
    result = {'schema': 'm5-product-v1-synthetic-checks-v1', 'passed_checked_scope': all(row['passed'] for row in checks),
        'checks': checks, 'check_count': len(checks), 'passed_count': sum(row['passed'] for row in checks),
        'source_pins': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            'human_eye_plugin/query_policy.py', 'human_eye_plugin/live_service.py', 'human_eye_plugin/auto_router.py',
            'human_eye_plugin/task_query.py', 'human_eye_plugin/live_spatial_mcp.py')},
        'new_actual_operations': {'Blender_starts': 0, 'MCP_processes': 0, 'rasters': 0, 'images': 0, 'models': 0},
        'scope': 'Synthetic host packets through the normal service query and MCP formatter. Image-free observation and actual M3 computation. Live captures and PNG delivery await root qualification.'}
    save(HERE / 'PRODUCT_V1_PURE.json', result)
    print(json.dumps({'passed': result['passed_checked_scope'], 'checks': len(checks), 'failed': [row for row in checks if not row['passed']]}))
    if not result['passed_checked_scope']:
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print(traceback.format_exc(), file=sys.stderr)
        raise
