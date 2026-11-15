"""Bind actual public API calls, outer tool delivery and current measurements."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ENGINEERING = HERE.with_name('m5_observe_measure_001')
ENGINEERING_PINS = {
    'quality_saved_r2.py': '265096c20cdf0cb10409e0779cf74ddda549b727686ae2c6697d0380dd0a4c03',
    'oracle.py': '0133b8e69b34e9347cb48cf9220f9a880065f6dc95517e300295afd2c96a9acb',
    'source_contract_r2.py': '4dae91a7522ed285495e7bfa600fb252004bd580af551d0b10214d968521ba22'
}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers():
    for name, digest in ENGINEERING_PINS.items():
        require(sha(ENGINEERING / name) == digest, 'accepted_M5_source_quality_helper_changed')
    return (load(ENGINEERING / 'quality_saved_r2.py', '_m5_consume_producer_numeric'),
            load(ENGINEERING / 'oracle.py', '_m5_consume_member_oracle'),
            load(ENGINEERING / 'source_contract_r2.py', '_m5_consume_source_contract'))


def current_whole_sources(captures):
    sources, generations = {}, set()
    for row in captures:
        capture = row['capture']
        state = capture['capture_state']
        generations.add((state['instance_id'], state['epoch'], state['revision']))
        for mesh in capture['meshes']:
            if mesh['name'] not in ('M4_Far_00', 'M4_Near'):
                continue
            actual = {'object_id': mesh['object_id'], 'object_name': mesh['name'],
                      'instance_id': capture['host_identity']['object_instances'][mesh['object_id']],
                      'document_epoch': capture['host_identity']['document_epoch'],
                      'vertices': mesh['vertices'], 'faces': mesh['faces']}
            previous = sources.get(mesh['name'])
            require(previous is None or actual == previous, 'current_whole_measurement_sources_disagree')
            sources[mesh['name']] = actual
    require(set(sources) == {'M4_Far_00', 'M4_Near'}, 'both_whole_current_measurement_sources_required')
    require(len(generations) == 1, 'mixed_product_capture_generations')
    return sources, list(next(iter(generations)))


def validate_measurement(task, captures, parent=None):
    ql, oracle, source = helpers()
    if 'surface_proximity' not in task.get('facts', {}):
        return None
    require(task.get('schema_version') == 'task-query-v3' and task.get('unit') == 'm'
            and task.get('coordinate_frame') == 'world' and task.get('pair_order') == 'A_to_B'
            and task.get('execution_authority') is False, 'actual_public_measurement_contract')
    bindings = task['binding']['objects']
    by_id = {mesh['object_id']: mesh for row in captures for mesh in row['capture']['meshes']}
    names = [by_id[row['object_id']]['name'] for row in bindings]
    expected = ['M4_Far_00', 'M4_Near']
    if names not in (expected, list(reversed(expected))):
        return None
    canonical = copy.deepcopy(task['facts']['surface_proximity'])
    if names != expected:
        witness = canonical['value']['nearest_witness']
        witness['a'], witness['b'] = witness['b'], witness['a']
        witness['direction_a_to_b'] = [-value for value in witness['direction_a_to_b']]
        canonical['value']['topology'].reverse()
    meshes = {mesh['name']: mesh for row in captures for mesh in row['capture']['meshes']}
    numeric = ql.validate_numeric(canonical, meshes[expected[0]], meshes[expected[1]], oracle)
    source_review = None
    if parent is not None:
        source_review = source.validate_source(task['binding']['observation_source'], parent['binding'],
                                              parent['capture'], bindings)
    else:
        matches = [row['capture'] for row in captures
                   if row['capture'].get('capture_scope') == 'selected_objects'
                   and row['capture']['revision'] == task['binding']['scene_revision']]
        require(bool(matches), 'ordinary_measurement_actual_capture_binding')
        require(all(capture['meshes'] == matches[0]['meshes']
                    and capture['host_identity'] == matches[0]['host_identity']
                    and capture['capture_state'] == matches[0]['capture_state'] for capture in matches),
                'ordinary_measurement_same_revision_current_source')
        actual = matches[0]
        require(task['binding']['objects'] == actual['task_selection']['bindings']
                and task['binding']['capture_scope'] == actual['capture_scope']
                and task['binding']['source'] == actual['source'], 'ordinary_measurement_current_selector_source')
        source_review = {'schema': 'current-ordinary-task-source-v1', 'capture_state': actual['capture_state'],
                         'scene_revision': actual['revision'], 'document_epoch': actual['host_identity']['document_epoch'],
                         'object_instances': actual['host_identity']['object_instances']}
    return {'actual_pair_names': names, 'numeric_canonical_Far_to_Near': numeric,
            'source': source_review, 'whole_objects': True}


def audit_calls(runtime, tools, requests, responses, captures, all_full_entries, aliases, truth, validate_brief):
    path = runtime / 'PUBLIC_REQUESTS.jsonl'
    rows = [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]
    require([row['internal_public_call_index'] for row in rows] == list(range(1, len(rows)+1)), 'actual_public_API_full_sequence')
    entries = {row['index']: row for row in all_full_entries}
    require(len(entries) == len(all_full_entries), 'duplicate_same_producer_archive_index')
    claimed = [index for tool in tools for index in tool['internal_public_call_indices']]
    require(sorted(claimed) == list(range(1, len(rows)+1)) and len(set(claimed)) == len(claimed), 'outer_to_public_API_exact_bijection')
    public_refs, current_outer_paths, reviews = set(), set(), []
    for call in rows:
        index = call['internal_public_call_index']
        outer = next(tool for tool in tools if index in tool['internal_public_call_indices'])
        attempt = outer['attempt']
        require(1 <= attempt <= len(requests), 'actual_outer_attempt_range')
        internal_range = outer['internal_public_call_range']
        require(internal_range['index_base'] == 0
                and outer['internal_public_call_indices'] == list(range(internal_range['start_inclusive']+1, internal_range['end_exclusive']+1)),
                'outer_public_API_recorded_range')
        for name, digest_key in (('request_path', 'request_sha256'), ('response_path', 'response_sha256'),
                                 ('actual_TX_path', 'actual_TX_sha256'), ('actual_RX_path', 'actual_RX_sha256')):
            actual_path = Path(call[name]).resolve()
            require(actual_path.is_relative_to(runtime) and sha(actual_path) == call[digest_key], 'actual_public_API_file_pin')
        request, response = read(call['request_path']), read(call['response_path'])
        require(request == call['request'] and response == call['response'], 'actual_public_API_index_binding')
        require(json.loads(Path(call['actual_TX_path']).read_bytes()) == request
                and json.loads(Path(call['actual_RX_path']).read_bytes()) == response, 'actual_public_API_stdio_binding')
        require(type(request['id']) is type(response['id']) and request['id'] == response['id'], 'actual_public_API_response_id')
        require(request['params']['name'] == 'human_eye_scene_observe', 'actual_product_API_entry')
        outer_response = read(responses[attempt-1])
        require(outer_response['id'] == read(requests[attempt-1])['id'], 'actual_outer_tool_ID')
        current_outer_paths.add(responses[attempt-1])
        content = response.get('result', {}).get('content', [])
        bodies = [json.loads(block['text']) for block in content if block.get('type') == 'text']
        require(len(bodies) == 1, 'one_original_public_API_text')
        public = bodies[0]
        mode = request['params']['arguments'].get('query', {}).get('mode')
        joint = mode == 'active_observation' and type(request['params']['arguments']['query'].get('task_query')) is dict
        review = {'index': index, 'outer_attempt': attempt, 'request_path': call['request_path'],
                  'response_path': call['response_path'], 'request_sha256': call['request_sha256'],
                  'response_sha256': call['response_sha256'], 'mode': mode, 'joint': joint,
                  'is_error': response.get('result', {}).get('isError'), 'public': public,
                  'outer_result_path': responses[attempt-1], 'measurement': None}
        if review['is_error'] is True:
            reviews.append(review)
            continue
        entry = entries.get(call['producer_archive_index'])
        require(entry is not None and sha(entry['path']) == entry['sha256'], 'same_producer_API_archive_binding')
        full = read(entry['path'])
        if mode == 'active_observation':
            parents = [row for row in captures if row['binding'] is not None
                       and row['binding']['binding_sha256'] == full['binding']['binding_sha256']]
            require(bool(parents), 'actual_public_observation_parent_source')
            if public.get('schema') == 'active-observation-brief-v5':
                validate_brief(public, full, aliases, truth)
            else:
                require(public.get('facts') == full['facts'], 'actual_public_full_observation_facts')
            if joint:
                require(type(public.get('task_result')) is dict and public['task_result'] == full.get('task_result'),
                        'actual_public_joint_measurement_delivered')
                review['measurement'] = validate_measurement(public['task_result'], captures, parents[0])
            review['observation_binding_sha256'] = full['binding']['binding_sha256']
            review['observation_source_binding_sha256'] = full['binding']['source_binding_sha256']
        elif mode == 'task':
            require(public == full, 'actual_public_ordinary_task_unchanged')
            review['measurement'] = validate_measurement(public, captures)
        for value in (public.get('binding', {}), public.get('task_result', {}).get('binding', {})):
            for key in ('binding_sha256', 'source_binding_sha256', 'scene_revision', 'scene_fingerprint'):
                if type(value.get(key)) is str:
                    public_refs.add(value[key])
        reviews.append(review)
    whole, generation = current_whole_sources(captures)
    api_by_attempt = {tool['attempt']: [row for row in reviews if row['outer_attempt'] == tool['attempt']] for tool in tools}
    batches = [attempt for attempt, calls in api_by_attempt.items()
               if any(row['mode'] == 'active_observation' and not row['is_error'] for row in calls)
               and any(row['mode'] == 'task' and row['measurement'] is not None and not row['is_error'] for row in calls)]
    joints = [row['index'] for row in reviews if row['joint'] and row['measurement'] is not None and not row['is_error']]
    return {'public_calls': reviews, 'public_index_path': str(path), 'public_index_sha256': sha(path),
            'actual_product_outer_results': sorted(current_outer_paths), 'current_public_source_references': sorted(public_refs),
            'whole_object_sources': whole, 'one_current_generation': generation,
            'observation_measurement_current_source_consistent': True,
            'observation_binding_sha256s': sorted({row['observation_binding_sha256'] for row in reviews if 'observation_binding_sha256' in row}),
            'observation_source_binding_sha256s': sorted({row['observation_source_binding_sha256'] for row in reviews if 'observation_source_binding_sha256' in row}),
            'actual_batch_outer_attempts': batches, 'actual_joint_public_call_indices': joints,
            'initial_product_entry': bool(api_by_attempt.get(1)), 'new_actual_calls': 0, 'new_rasters': 0, 'new_models': 0}
