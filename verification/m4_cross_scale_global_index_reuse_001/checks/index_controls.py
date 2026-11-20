"""Exercise installed coverage reuse against saved captures and fail-closed inputs."""

import argparse
import base64
import copy
from contextlib import ExitStack
from dataclasses import is_dataclass
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
import weakref


NS = Path(__file__).resolve().parents[1]
PREVIOUS = NS.parent / 'm4_cross_scale_local_first_view_001/checks/view_controls.py'
TRUTH = NS.parent / 'm4_cross_scale_live_task_formal_001/fixture/CURRENT_TRUTH.json'
TRUTH_SHA = '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922'
RESOURCE = 'region_task_global_index'


def load_previous():
    spec = importlib.util.spec_from_file_location('_m4_previous_view_controls', PREVIOUS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


previous = load_previous()


class Replay:
    """Replace only the host capture and raster layer with sealed original receipts."""

    def __init__(self, capture, producer, folder):
        from human_eye_plugin.live_service import LiveSpatialService
        from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer

        self.host = previous.SavedHost(copy.deepcopy(capture))
        self.target_capture = None
        self.host.capture_active_observation = self.capture_target
        self.target_reads = 0
        self.originals = {(f['candidate_identity'], f['view_name']): f for f in producer['constructed_frames']}
        config = folder / 'live.json'
        folder.mkdir()
        config.write_text(json.dumps({'schema_version': '1.0', 'enabled': True,
                                      'project_root': str(folder), 'state_file': 'state.json',
                                      'audit_file': 'audit.jsonl', 'request_budget_s': 30}), encoding='utf8')
        self.service = LiveSpatialService(config, host=self.host)
        self.server = LiveSpatialMCPServer(self.service)
        self.context = self.service._read_context
        self.original_observe = self.service.observe
        self.active = None
        self.ordinal = 0
        self.fail_global = None
        self.advance_clock = None
        self.stack = ExitStack()

    def capture_target(self, selector, deadline, _document_limit):
        assert self.target_capture is not None and deadline > time.perf_counter_ns()
        self.target_reads += 1
        assert selector == self.target_capture['observation_target']['selector']
        return copy.deepcopy(self.target_capture)

    def __enter__(self):
        from human_eye_plugin import active_observation as planner
        from human_eye_plugin import active_observation_region_task as region
        from human_eye_plugin.active_observation_images import ActiveObservationImages

        build_index = planner.build_index_from_parsed
        render_scope = region._render_scope
        prepared = self.context.prepared

        def build(*args, **kwargs):
            region_count = len(args[3])
            full = bool(kwargs.get('patch_scope'))
            mark, cpu = time.perf_counter_ns(), time.thread_time_ns()
            item = {'regions': region_count, 'global_scope': full}
            self.active['index_builds'].append(item)
            try:
                if full and self.fail_global is not None:
                    raise ValueError(self.fail_global)
                index = build_index(*args, **kwargs)
                if full and self.advance_clock is not None:
                    self.advance_clock()
                return index
            finally:
                item.update(cpu_ns=time.thread_time_ns() - cpu, wall_ns=time.perf_counter_ns() - mark)

        def cache(key, factory):
            mark, cpu = time.perf_counter_ns(), time.thread_time_ns()
            result, hit = prepared(key, factory)
            self.active['prepared'].append({'key': key, 'hit': hit,
                'cpu_ns': time.thread_time_ns() - cpu, 'wall_ns': time.perf_counter_ns() - mark})
            return result, hit

        def scope(session, *args, **kwargs):
            assert not session.state.observed_views
            assert not session.state.covered_mask and session.state.updates == 0
            self.active['states'].append(weakref.ref(session.state))
            return render_scope(session, *args, **kwargs)

        def replay(images, name):
            frame = self.originals[images.session.candidate_identity, name]
            assert frame['scene_identity'] == images.session.scene_identity
            self.active['replayed_frames'].append([frame['scope_id'], name])
            return copy.deepcopy(frame)

        def observe(*args, **kwargs):
            result = self.original_observe(*args, **kwargs)
            self.active['value'] = result
            return result

        self.stack.enter_context(patch.object(planner, 'build_index_from_parsed', build))
        self.stack.enter_context(patch.object(region, 'build_index_from_parsed', build))
        self.stack.enter_context(patch.object(self.context, 'prepared', cache))
        self.stack.enter_context(patch.object(region, '_render_scope', scope))
        self.stack.enter_context(patch.object(ActiveObservationImages, 'render_view', replay))
        self.stack.enter_context(patch.object(self.service, 'observe', observe))
        self.stack.enter_context(patch('human_eye_plugin.active_observation_images.rasterize_attention',
            side_effect=AssertionError('offline replay must not run a real raster')))
        return self

    def __exit__(self, *exception):
        return self.stack.__exit__(*exception)

    def resources(self):
        selections = self.context._selections
        return selections[self.context._capture]['prepared'] if selections else {}

    def call(self, arguments, *, error=None):
        self.ordinal += 1
        observed = {'index_builds': [], 'prepared': [], 'states': [], 'replayed_frames': []}
        self.active = observed
        mark, cpu = time.perf_counter_ns(), time.thread_time_ns()
        response = self.server.handle_jsonrpc_message({'jsonrpc': '2.0', 'id': self.ordinal, 'method': 'tools/call',
            'params': {'name': 'human_eye_scene_observe',
                       'arguments': {**arguments, 'session_id': 'm4-index-replay'}}})
        observed.update(caller_wall_ns=time.perf_counter_ns() - mark, caller_cpu_ns=time.thread_time_ns() - cpu)
        assert all(ref() is None for ref in observed.pop('states')), 'individual request state is unexpectedly retained'
        self.active = None
        assert response['id'] == self.ordinal and response['result']['content'][0]['type'] == 'text'
        result = response['result']
        raw = result['content'][0]['text']
        body = json.loads(raw)
        observed['public_body_utf8_bytes'] = len(raw.encode())
        observed['public_png_sha256'] = [previous.sha(base64.b64decode(image['data'], validate=True))
                                         for image in result['content'][1:]]
        if error is not None:
            assert result['isError'] is True and error in body['error'], body
            assert not observed['public_png_sha256'] and not observed['replayed_frames']
            observed['error'] = body['error']
            if body.get('budget_stage') is not None:
                observed['budget_stage'] = body['budget_stage']
        else:
            assert result['isError'] is False, body
        return observed, body


def result_rows(value):
    return {row['object_name']: row for row in value['facts']['region_task']['rows']}


def operation(call, kind, *, baseline, built, cache_hit=False, full=True):
    observed, reply = call
    value = observed.pop('value')
    work, stages = value['work'], value['stages']
    actual_global_builds = sum(item['global_scope'] for item in observed['index_builds'])
    assert actual_global_builds == built, (kind, observed)
    assert ('index_global' in stages) is bool(built)
    assert work['result_cache_hit'] is cache_hit
    if not cache_hit:
        assert work['camera_calls'] == work['geometry_parse_calls'] == work['mesh_conversions'] == 1
        assert work['partition_calls'] == work['prepare_calls'] == built
        if not baseline:
            assert work['global_index_cache_hit'] is (not built), work
    if cache_hit or baseline:
        assert not observed['prepared']
    elif observed['prepared']:
        item, = observed['prepared']
        assert item['key'] == RESOURCE and item['hit'] is (not built)
    else:
        assert built == 1 and value['binding']['capture_state'] is None
    if kind == 'prediction':
        assert value['status'] == 'predicted' and value['observation_status'] == reply['observation_status'] == 'prediction_only'
        assert value['frames'] == value['constructed_frames'] == value['steps'] == []
        assert not observed['replayed_frames'] and not observed['public_png_sha256']
        assert work['raster_attempts'] == work['raster_completed'] == work['frame_reuses'] == 0
        scope, = value['scopes']
        assert scope['facts']['observations'] == [] and scope['facts']['coverage']['state_updates'] == 0
        assert scope['facts']['coverage']['observed_views'] == scope['facts']['coverage']['covered_roi_ids'] == []
        assert all(row['complete_witness'] is None and row['status'] == 'unknown' for row in result_rows(value).values())
        if full:
            assert reply['facts']['region_task'] == value['facts']['region_task']
            assert reply['constructed_frames'] == reply['frames'] == []
    elif kind == 'observation':
        assert len(value['frames']) == len(value['constructed_frames']) == 3
        assert work['raster_attempts'] == work['raster_completed'] == (0 if cache_hit else 3)
        assert work['frame_reuses'] == (3 if cache_hit else 0)
        rows = result_rows(value)
        assert rows['M06']['reason'] == 'positive_area_occlusion_all_front_views'
        assert rows['M06']['complete_witness'] is None
        for name, view, pixels in (('M02', 'SCENE', [50557, 926]), ('M09', 'LEFT', [146797, 1530])):
            assert rows[name]['complete_witness']['view_name'] == view
            brief_row = next(row for row in reply['region_task']['rows'] if row['object_name'] == name)
            assert brief_row['complete_witness']['frame_identity'] == rows[name]['complete_witness']['frame_identity']
            witness = next(row for row in reply['witness_pixels']['rows'] if row[2] == rows[name]['roi_id'])
            assert witness[3:5] == pixels
    observed.update(kind=kind, global_builds=actual_global_builds, work=work,
                    stages_ns={key: row['elapsed_ns'] for key, row in stages.items()},
                    witnesses={name: row['complete_witness'] for name, row in result_rows(value).items()},
                    region_reasons={name: row['reason'] for name, row in result_rows(value).items()},
                    binding=value['binding']['binding_sha256'])
    return observed, value


def retained_graph(context, resources):
    from human_eye_plugin.active_observation import ActiveObservationSession, CoverageIndex, CoverageState

    index = resources[RESOURCE]
    assert tuple(resources) == (RESOURCE,) and type(index) is CoverageIndex and len(index.regions) == 84
    assert 'patch_scope' in vars(index)

    def visit(value, seen, *, forbid_resources=False):
        identity = id(value)
        if identity in seen:
            return 0
        seen.add(identity)
        if forbid_resources:
            assert not isinstance(value, (ActiveObservationSession, CoverageState, Path, bytes, bytearray))
            assert type(value).__module__ != 'numpy'
        children = ()
        if isinstance(value, dict):
            children = tuple(x for item in value.items() for x in item)
        elif isinstance(value, (tuple, list, set, frozenset)):
            children = value
        elif isinstance(value, Fraction):
            children = (value.numerator, value.denominator)
        elif is_dataclass(value):
            children = (vars(value),)
        return sys.getsizeof(value) + sum(visit(child, seen, forbid_resources=forbid_resources) for child in children)

    all_nodes = set()
    retained_bytes = visit(index, all_nodes, forbid_resources=True)
    other_nodes = {id(resources)}
    visit(context._selections, other_nodes)
    exclusive_bytes = visit(index, set(other_nodes), forbid_resources=True)
    return {'resource_key': RESOURCE, 'index_type': type(index).__name__, 'index_graph_bytes': retained_bytes,
            'unique_index_graph_bytes_excluding_objects_reachable_in_other_cached_results': exclusive_bytes,
            'retained_python_nodes': len(all_nodes), 'dictionary_overhead_delta_bytes': sys.getsizeof(resources) - sys.getsizeof({}),
            'measure': 'Recursive sys.getsizeof, counted once per object identity, includes built-in objects reachable by index. '
                       'Exclusive estimate omits objects also reachable in the service read context result entries. '
                       'Python heap estimate excludes allocator overhead, process RSS, image and NPZ file bytes.'}


def sequences(capture, producer, arguments, root, baseline):
    prediction = {**arguments, 'include_image': False, 'response_detail': 'full'}
    separate = copy.deepcopy(prediction)
    separate['query']['region_task']['area_max_m2'] = 0.014
    expected_png = [frame['image_sha256'] for frame in producer['frames']]
    reported = {}
    for reverse in (False, True):
        with Replay(capture, producer, root / ('reverse' if reverse else 'forward')) as replay:
            requests = [(prediction, 'prediction'), (arguments, 'observation')] if reverse else [
                (arguments, 'observation'), (prediction, 'prediction')]
            steps = {}
            for i, (request, kind) in enumerate(requests):
                step, value = operation(replay.call(request), kind, baseline=baseline, built=int(i == 0 or baseline))
                assert set(result_rows(value)) == {'M02', 'M06', 'M09'}
                steps[kind] = step
                if i == 0:
                    first_resources = dict(replay.resources())
            assert steps['observation']['public_png_sha256'] == expected_png
            if not baseline:
                assert first_resources[RESOURCE] is replay.resources()[RESOURCE]
            changed, value = operation(replay.call(separate), 'prediction', baseline=baseline, built=int(baseline))
            assert set(result_rows(value)) == {'M09'}
            assert value['facts']['region_task']['summary']['supported_region_count'] == 84
            hot, _ = operation(replay.call(arguments), 'observation', baseline=baseline, built=0, cache_hit=True)
            assert hot['public_png_sha256'] == expected_png
            assert hot['witnesses'] == steps['observation']['witnesses']
            assert replay.host.captures == 4
            steps.update(changed_conditions=changed, hot=hot, actual_captures=replay.host.captures)
            if not baseline:
                assert first_resources[RESOURCE] is replay.resources()[RESOURCE]
                steps['memory'] = retained_graph(replay.context, replay.resources())
            else:
                assert not replay.resources()
                steps['memory'] = {'index_graph_bytes': 0, 'retained_python_nodes': 0}
            reported['prediction_then_observation' if reverse else 'observation_then_prediction'] = steps
    return reported


def targeted_capture(capture):
    from human_eye_plugin.blender_host import _observation_target_cameras

    selected = copy.deepcopy(capture)
    meshes = selected['meshes']
    target = next(mesh for mesh in meshes if mesh['name'] == 'M02')
    bounds = [[list(map(reduce_axis, zip(*mesh['vertices']))) for reduce_axis in (min, max)] for mesh in meshes]
    full = copy.deepcopy(selected['host_identity'])
    instances = full['object_instances']
    directory = [{'object_id': mesh['object_id'], 'name': mesh['name'], 'instance_id': instances[mesh['object_id']]}
                 for mesh in meshes]
    directory_sha = previous.sha(json.dumps(directory, sort_keys=True, separators=(',', ':'),
                                           ensure_ascii=False, allow_nan=False).encode())
    selected['observation_target'] = dict(schema='active-observation-target-v1',
        selector={'name': target['name']}, target_object_id=target['object_id'],
        target_instance_id=instances[target['object_id']], target_object_index=meshes.index(target),
        camera_plan=_observation_target_cameras(target['vertices'], bounds),
        scene_directory=directory, full_scene_identity=full, retained_object_ids=list(instances),
        excluded_object_ids=[], directory_sha256=directory_sha,
        source_frame={'frame': 1, 'subframe': 0, 'scale_length': 1}, work={})
    selected['observation_target']['retained_object_ids'] = [mesh['object_id'] for mesh in meshes]
    selected['capture_scope'] = selected['host_identity']['capture_scope'] = 'target_observation_meshes'
    selected['capture_state']['selection_key'] += '-target'
    return selected


def invalidation(capture, producer, arguments, root):
    from human_eye_plugin import active_observation_host as host

    prediction = {**arguments, 'include_image': False, 'response_detail': 'full'}
    initial_mesh = next(mesh for mesh in capture['meshes'] if mesh['name'] == 'M02')
    variants = {}

    def variant(name):
        variants[name] = copy.deepcopy(capture)
        return variants[name]

    variant('generation_revision')['capture_state']['revision'] += 1
    variant('generation_epoch')['capture_state']['epoch'] += 1
    variant('generation_instance')['capture_state']['instance_id'] += '/replacement'
    variant('document_epoch')['host_identity']['document_epoch'] = '0' * 64
    variant('selection_key')['capture_state']['selection_key'] += '/another-selection'
    variant('same_name_new_instance')['host_identity']['object_instances'][initial_mesh['object_id']] += '/replacement'
    variant('mesh_order')['meshes'].reverse()
    variant('same_instance_rename')['meshes'][capture['meshes'].index(initial_mesh)]['name'] += '/renamed'
    for name in ('changed_mesh_world_vertices', 'changed_evaluated_pose'):
        changed = variant(name)
        mesh = changed['meshes'][capture['meshes'].index(initial_mesh)]
        points = mesh['vertices'][:1] if name == 'changed_mesh_world_vertices' else mesh['vertices']
        for point in points:
            point[2] += 0.125
        changed['revision'] += '/' + name
    variant('unversioned')['capture_state'] = None

    results = {}
    with Replay(capture, producer, root / 'isolated-bindings') as replay:
        for name, changed in variants.items():
            replay.host.capture = capture
            replay.context.reset()
            operation(replay.call(prediction), 'prediction', baseline=False, built=1)
            original = replay.resources()[RESOURCE]
            replay.host.capture = changed
            step, value = operation(replay.call(prediction), 'prediction', baseline=False, built=1)
            if name == 'unversioned':
                assert not replay.resources() and not step['prepared']
                repeat, _ = operation(replay.call(prediction), 'prediction', baseline=False, built=1)
                assert not replay.resources() and not repeat['prepared']
            else:
                assert replay.resources()[RESOURCE] is not original
                assert value['binding']['objects'] == host.source_binding(changed)['objects']
                assert value['binding']['scene_revision'] == changed['revision']
            results[name] = {'global_builds': 1, 'source_binding': value['binding']['source_binding_sha256']}

    with Replay(capture, producer, root / 'target-and-policy') as replay:
        first, _ = operation(replay.call(prediction), 'prediction', baseline=False, built=1)
        original = replay.resources()[RESOURCE]
        invalid = copy.deepcopy(prediction)
        invalid['query']['objects'] = [{'name': 'M02'}]
        rejected, _ = replay.call(invalid, error='region_task requires whole-scene discovery without objects')
        assert not rejected['index_builds'] and replay.resources()[RESOURCE] is original
        replay.target_capture = targeted_capture(capture)
        target_args = {**prediction, 'query': {'mode': 'active_observation', 'objects': [{'name': 'M02'}]}}
        target, body = replay.call(target_args)
        assert target['value']['binding']['capture_scope'] == 'target_observation_meshes'
        assert body['observation_status'] == 'prediction_only'
        assert not target['prepared'] and RESOURCE not in replay.resources() and replay.target_reads == 1
        operation(replay.call(prediction), 'prediction', baseline=False, built=0, cache_hit=True)
        assert replay.resources()[RESOURCE] is original
        with patch.object(host, 'MARGIN_PER_SIDE', 0.07):
            policy, value = operation(replay.call(prediction), 'prediction', baseline=False, built=1)
        assert replay.resources()[RESOURCE] is not original and policy['binding'] != first['binding']
        results['target_scope'] = {'mock_host_target_reads': replay.target_reads, 'prepared_calls': 0}
        results['camera_policy'] = {'global_builds': 1, 'camera_identity': value['binding']['camera_identity']}

    with Replay(capture, producer, root / 'bad-document') as replay:
        operation(replay.call(prediction), 'prediction', baseline=False, built=1)
        original = replay.resources()[RESOURCE]
        changed = copy.deepcopy(capture)
        changed['host_identity'].pop('document_epoch')
        replay.host.capture = changed
        failed, _ = replay.call(prediction, error='active_observation_complete_host_identity_required')
        assert not failed['index_builds'] and not failed['prepared'] and replay.resources()[RESOURCE] is original
        results['invalid_document_identity'] = {'error': failed['error']}
    return results


def failure_controls(capture, producer, arguments, root):
    prediction = {**arguments, 'include_image': False, 'response_detail': 'full'}
    results = {}
    for mode in ('factory_exception', 'deadline_during_index'):
        with Replay(capture, producer, root / mode) as replay:
            clock = [1000.0]
            if mode == 'factory_exception':
                replay.fail_global = 'injected_global_factory_exception'
                error = replay.fail_global
            else:
                replay.advance_clock = lambda: clock.__setitem__(0, 1031.0)
                error = 'live_request_expired'
            with patch('human_eye_plugin.live_service.time.monotonic', side_effect=lambda: clock[0]):
                attempt, body = replay.call(prediction, error=error)
            assert len(attempt['index_builds']) == 1 and not attempt['prepared'] and not replay.resources()
            assert not replay.context._results
            if mode == 'deadline_during_index':
                assert body['budget_stage'] == 'active_observation_after_global_index'
            replay.fail_global = replay.advance_clock = None
            retry, _ = operation(replay.call(prediction), 'prediction', baseline=False, built=1)
            assert retry['work']['result_cache_hit'] is False and RESOURCE in replay.resources()
            results[mode] = {'error': attempt['error'], 'budget_stage': attempt.get('budget_stage'),
                             'persisted_index_or_result': False, 'retry_global_builds': retry['global_builds']}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    assert sys.flags.isolated and sys.dont_write_bytecode
    product = args.product_root.resolve()
    sys.path[:0] = [str(product), str(previous.DEPENDENCIES)]
    history = previous.History()
    for path in (Path(__file__), PREVIOUS):
        history.pin(path)
    assert previous.sha(history.pin(TRUTH)) == TRUTH_SHA
    for name in ('active_observation', 'active_observation_host', 'active_observation_images',
                 'active_observation_region_task', 'blender_host', 'live_service', 'live_spatial_mcp', 'read_context'):
        module = __import__('human_eye_plugin.' + name, fromlist=[name])
        source = Path(module.__file__).resolve()
        assert source.parent == product / 'human_eye_plugin', source
        history.pin(source)
    producer, terminal, arguments = history.inputs()
    capture = previous.reconstruct_capture(producer, terminal)
    with tempfile.TemporaryDirectory(prefix='m4-index-controls-') as temporary:
        folder = Path(temporary)
        sequence = sequences(capture, producer, arguments, folder, args.baseline)
        invalidated = {} if args.baseline else invalidation(capture, producer, arguments, folder)
        failed = {} if args.baseline else failure_controls(capture, producer, arguments, folder)
    receipt = {'schema': 'm4-cross-scale-global-index-reuse-offline-controls-v1', 'passed': True,
               'baseline': args.baseline, 'owned_Blender': 0, 'models': 0, 'actual_new_rasters': 0,
               'product_root': str(product), 'sequences': sequence, 'binding_invalidation': invalidated,
               'failure_controls': failed, 'source_pins': list(history.pins.values())}
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print('Offline index controls passed', args.output)


if __name__ == '__main__':
    main()
