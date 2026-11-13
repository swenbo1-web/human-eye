"""Recompute 002 mechanism/byte facts from sealed originals, offline only."""

import argparse
import ast
import base64
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BATCH = ROOT / 'verification/m4_surface_scan_continuous_consumption_002'
REVIEW = Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_002_quality_review')
PLAN = Path('D:/hefe/docs/M4_SURFACE_SCAN_CONTINUOUS_CONSUMPTION_002_COST_PLAN.md')
PLAN_SHA = '718af692f891fb27150c8aa40fcfe2408ac80854399d1204a13a234c6ae2e6e3'
SEAL_SHA = 'ccea554353a6f0607263124d2170ef3b2094a07e222c86276f522184b7f5316c'
ORDER = ('N1', 'C1', 'C2', 'N2', 'N3', 'C3')
MARKER = 'HUMAN_EYE_BLENDER_MCP:'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf8')


def actor_wire(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8') + b'\n'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(encoded(value))


def content_metrics(content):
    texts = [block['text'] for block in content if block.get('type') == 'text']
    images = [block for block in content if block.get('type') == 'image']
    return {'text_utf8_bytes': sum(len(text.encode('utf8')) for text in texts),
            'text_blocks': len(texts), 'image_blocks': len(images),
            'image_decoded_bytes': sum(len(base64.b64decode(block['data'], validate=True)) for block in images)}


def wire_totals(rows):
    return {'requests': len(rows), 'request_bytes': sum(row['request_bytes'] for row in rows),
            'response_bytes': sum(row['response_bytes'] for row in rows),
            'stdout_utf8_bytes': sum(row.get('stdout_utf8_bytes', 0) for row in rows),
            'request_types': dict(Counter(row['request_type'] for row in rows)),
            'sequences': [row['sequence'] for row in rows]}


class Builder:
    def __init__(self):
        self.inputs = {}
        self.runtime_bindings = {}
        self.checks = []

    def read(self, path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = sha(raw)
        if expected is not None and digest != expected:
            raise ValueError('frozen_input_digest_mismatch:' + str(path))
        for runtime, members in self.runtime_bindings.items():
            if path.is_relative_to(runtime):
                relative = path.relative_to(runtime).as_posix()
                if members.get(relative) != {'bytes': len(raw), 'sha256': digest}:
                    raise ValueError('runtime_original_not_bound_to_sealed_manifest:' + relative)
        previous = self.inputs.get(str(path))
        if previous is not None and previous != digest:
            raise ValueError('input_changed_during_recomputation:' + str(path))
        self.inputs[str(path)] = digest
        return raw

    def json(self, path, expected=None):
        return json.loads(self.read(path, expected))

    def jsonl(self, path):
        return [json.loads(line) for line in self.read(path).splitlines() if line]

    def check(self, label, condition):
        self.checks.append({'check': label, 'passed': bool(condition)})
        if not condition:
            raise ValueError('mechanism_consistency_check:' + label)

    def native_path(self, code, functions, attempt, cell, turn_index):
        tree = ast.parse(code)
        definitions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        attributes = Counter(node.func.attr for node in ast.walk(tree)
                             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute))
        evaluated_names = {target.id for node in ast.walk(tree) if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == 'evaluated_get' for target in node.targets if isinstance(target, ast.Name)}
        evaluated_data_read = any(isinstance(node, ast.Attribute) and node.attr == 'data'
            and isinstance(node.value, ast.Name) and node.value.id in evaluated_names for node in ast.walk(tree))
        reused = sorted((calls & set(functions)) - definitions)
        result = {'cell': cell, 'turn_index': turn_index, 'attempt': attempt,
            'code_sha256': sha(code.encode('utf8')), 'functions_defined': sorted(definitions),
            'prior_functions_referenced_by_call_sites': {name: copy.deepcopy(functions[name]) for name in reused},
            'mesh_acquisition_call_sites': {name: attributes[name] for name in (
                'evaluated_depsgraph_get', 'evaluated_get', 'to_mesh', 'calc_loop_triangles', 'to_mesh_clear')},
            'current_to_mesh_in_code': attributes['to_mesh'] > 0,
            'current_evaluated_data_read_in_code': evaluated_data_read,
            'current_evaluated_mesh_acquisition_in_code': attributes['to_mesh'] > 0 or evaluated_data_read,
            'current_triangulation_in_code': attributes['calc_loop_triangles'] > 0,
            'has_pair_loop_syntax': any(isinstance(node, (ast.For, ast.ListComp)) for node in ast.walk(tree)),
            'runtime_kernel_invocations': None,
            'scope': 'Actual successfully executed script source. AST counts are syntactic sites, not dynamic loop/kernel counts.'}
        for name in definitions:
            functions[name] = {'attempt_defined': attempt, 'code_sha256': result['code_sha256']}
        return result

    def host_wires(self, owner, attempts):
        index = self.json(owner / 'native/WIRE/INDEX.json')
        events = self.jsonl(owner / 'native/WORKER_EVENTS.jsonl')
        by_sequence = {row['sequence']: row for row in events}
        result = []
        for entry in index:
            sequence = entry['sequence']
            folder = owner / 'native/WIRE' / str(sequence).zfill(3)
            request_raw, response_raw = self.read(folder / 'REQUEST.bin'), self.read(folder / 'RESPONSE.bin')
            request, response = json.loads(request_raw), json.loads(response_raw)
            event = by_sequence[sequence]
            self.check(str(owner.name) + ':wire_bytes:' + str(sequence),
                len(request_raw) == entry['request_bytes'] and len(response_raw) == entry['response_attempted_bytes'])
            self.check(str(owner.name) + ':wire_send_completed:' + str(sequence), entry['response_sendall_completed'] is True)
            matches = [row['attempt'] for row in attempts if row['started_ns'] <= event['started_ns']
                       < row['started_ns'] + row['elapsed_ns']]
            self.check(str(owner.name) + ':wire_unique_tool_interval:' + str(sequence), len(matches) <= 1)
            text = response.get('result', {}).get('result') if isinstance(response.get('result'), dict) else None
            value = {'sequence': sequence, 'request_type': request['type'],
                'request_bytes': len(request_raw), 'response_bytes': len(response_raw),
                'started_ns': event['started_ns'], 'business_attempt': matches[0] if matches else None,
                'stdout_utf8_bytes': len(text.encode('utf8')) if isinstance(text, str) else 0,
                'worker_status': event['status'], 'script_error': event.get('script_error'),
                'script_sha256': event.get('script_sha256'),
                'resident_resource_observation': copy.deepcopy(event.get('m2_work'))}
            if isinstance(text, str) and MARKER in text:
                lines = [line[len(MARKER):] for line in text.splitlines() if line.startswith(MARKER)]
                self.check('one_known_scene_delta_frame:' + str(sequence), len(lines) == 1)
                packet = json.loads(lines[0])['result']
                resources = packet['resources']
                value['scene_delta'] = {'schema': packet['schema'],
                    'frame_json_utf8_bytes': len(lines[0].encode('utf8')),
                    'resources_transmitted': len(resources), 'live_resource_ids': copy.deepcopy(packet['live_resources']),
                    'resource_vertices_transmitted': sum(len(item['vertices_local']) for item in resources),
                    'resource_faces_transmitted': sum(len(item['faces']) for item in resources),
                    'resource_edges_transmitted': sum(len(item['edges']) for item in resources),
                    'capture_work': copy.deepcopy(packet['capture']['work'])}
            result.append(value)
        self.check('all_worker_events_have_wire', len(result) == len(events))
        return result

    def plugin_mechanism(self, observation, audit, base_pairs, host_rows):
        work = audit['task_work']
        pairs = work.get('pairs', {})
        hits = sum(row['surface_pair_cache_hit'] is True for row in pairs.values())
        misses = sum(row['surface_pair_cache_hit'] is False for row in pairs.values())
        self.check('actual_pair_cache_counter_matches', hits == work['cache_hits'] and misses == work['kernel_calls'])
        base_common = set(base_pairs) & set(pairs)
        changed = [key for key in sorted(base_common)
                   if base_pairs[key]['surface_dependency_key'] != pairs[key]['surface_dependency_key']]
        new_pairs = sorted(set(pairs) - set(base_pairs))
        unchanged = [key for key in sorted(base_common)
                     if base_pairs[key]['surface_dependency_key'] == pairs[key]['surface_dependency_key']]
        names = {row['id']: row['name'] for row in observation.get('objects', [])}
        changed_names = [[names.get(value, value) for value in json.loads(key)] for key in changed]
        new_names = [[names.get(value, value) for value in json.loads(key)] for key in new_pairs]
        return {'trace_id': observation['trace_id'], 'scene_binding': copy.deepcopy(observation['binding']),
            'kernel_calls': work['kernel_calls'], 'pair_calls': work['pair_calls'], 'cache_hits': work['cache_hits'],
            'result_cache_hit': work['result_cache_hit'], 'normalizations': work['normalizations'],
            'candidate_pairs': work['candidate_pairs'], 'bound_pairs': work['bound_pairs'],
            'acquisition_work': copy.deepcopy(work['acquisition_work']),
            'measurement_cache_before': copy.deepcopy(work['measurement_cache_before']),
            'measurement_cache_after': copy.deepcopy(work['measurement_cache_after']),
            'recomputed_pair_rows': misses, 'cached_pair_rows': hits,
            'disposition_counts': dict(Counter(row['status'] for row in work.get('dispositions', []))),
            'base_dependency_comparison': {'same_dependency_existing_pair_count': len(unchanged),
                'changed_dependency_existing_pair_count': len(changed), 'new_candidate_pair_count': len(new_pairs),
                'changed_dependency_pairs': changed_names, 'new_candidate_pairs': new_names,
                'scope': 'Pair-row comparison exists only on non-result-cache-hit requests. BASE supplies the baseline.'},
            'scene_delta_transmissions': [row['scene_delta'] for row in host_rows if 'scene_delta' in row],
            'geometry_cache_actual_resident_memory_bytes': None,
            'cache_accounted_bytes_scope': 'Internal immutable-payload/entry allowance budget, excluding temporary work; not measured cache RAM.',
            'internal_algorithm_fallback_count': None,
            'internal_algorithm_fallback_scope': 'No exhaustive fallback counter is present in these originals.'}

    def episode(self, row, delivered):
        cell, group = row['cell'], row['group']
        runtime, owner = Path(row['runtime_folder']), Path(row['owner_output'])
        outer = Path(row['folder'])
        manifest_raw = self.read(outer / 'RUNTIME_MANIFEST.json', delivered[(outer / 'RUNTIME_MANIFEST.json').relative_to(BATCH).as_posix()])
        manifest = json.loads(manifest_raw)
        archive_raw = self.read(outer / 'ORIGINALS.zip', delivered[(outer / 'ORIGINALS.zip').relative_to(BATCH).as_posix()])
        self.check(cell + ':archive_manifest_binding', sha(archive_raw) == manifest['archive_sha256'])
        self.runtime_bindings[runtime.resolve()] = manifest['members']
        tools = self.json(owner / 'TOOLS.json')
        attempts = tools['tools']
        wires = self.host_wires(owner, attempts)
        coordinator = self.json(Path(row['consumer_output']) / 'EPISODE_RESULT.json')
        audits = self.jsonl(owner / 'audit.jsonl') if group == 'C' else []
        observations = {value['trace_id']: value for value in audits if value.get('event') == 'observe'}
        request_traces = {value['trace_id']: value['trace'] for value in audits if value.get('event') == 'request_trace'}
        native_functions, base_pairs = {}, {}
        turns, all_numbers = [], []
        for turn in coordinator['turns']:
            index = turn['turn_index']
            folder = Path(turn['folder'])
            first = turn['status_before']['business_attempts'] + 1
            last = turn['status_after']['business_attempts']
            selected = [item for item in attempts if first <= item['attempt'] <= last]
            numbers = [item['attempt'] for item in selected]
            all_numbers.extend(numbers)
            event_rows = self.jsonl(folder / 'events.jsonl')
            completed = [item['event']['item'] for item in event_rows
                         if item['event'].get('type') == 'item.completed'
                         and item['event'].get('item', {}).get('type') == 'mcp_tool_call']
            self.check(cell + ':owner_CLI_attempts:' + str(index), len(selected) == len(completed))
            details, native, plugins = [], [], []
            for attempt, item in zip(selected, completed):
                original = owner / ('tool_' + str(attempt['attempt']).zfill(2))
                request = self.json(original / 'REQUEST.json')
                response_path = original / ('RESPONSE.json' if (original / 'RESPONSE.json').exists() else 'ERROR_RESPONSE.json')
                response = self.json(response_path)
                receipt = self.json(original / 'ATTEMPT.json')
                self.check(cell + ':owner_receipt:' + str(attempt['attempt']), receipt == attempt)
                self.check(cell + ':encoded_response_bytes:' + str(attempt['attempt']),
                           len(actor_wire(response)) == attempt['response_bytes'])
                self.check(cell + ':request_business_binding:' + str(attempt['attempt']),
                    request['params']['name'] == item['tool'] and actor_wire(request['params']['arguments']) == actor_wire(item['arguments']))
                self.check(cell + ':content_business_binding:' + str(attempt['attempt']),
                           actor_wire(response['result']['content']) == actor_wire(item['result']['content']))
                host = [wire for wire in wires if wire['business_attempt'] == attempt['attempt']]
                metrics = content_metrics(item['result']['content'])
                detail = {'attempt': attempt['attempt'], 'tool': attempt['name'], 'owner_is_error': attempt['is_error'],
                    'owner_exception': copy.deepcopy(attempt['exception']), 'CLI_status': item['status'],
                    'CLI_error': copy.deepcopy(item['error']), 'owner_encoded_response_bytes': attempt['response_bytes'],
                    'owner_produced_response_bytes': attempt['produced_response_bytes'],
                    'response_original_file_bytes': response_path.stat().st_size,
                    'consumer_visible_content': metrics, 'host_business_wire': wire_totals(host),
                    'original_request': str(original / 'REQUEST.json'), 'original_response': str(response_path)}
                details.append(detail)
                if attempt['name'] == 'execute_blender_code':
                    native.append(self.native_path(request['params']['arguments']['code'], native_functions,
                                                   attempt['attempt'], cell, index))
                elif attempt['name'] == 'human_eye_scene_observe':
                    observation = json.loads(response['result']['content'][0]['text'])
                    audit = observations[observation['trace_id']]
                    trace = request_traces[observation['trace_id']]
                    self.check(cell + ':trace_delivery:' + str(index), trace['annotations']['delivery'] == 'stdio_write_completed')
                    mechanism = self.plugin_mechanism(observation, audit, base_pairs, host)
                    mechanism['trace_delivery'] = copy.deepcopy(trace['annotations'])
                    mechanism['process_lifetime_peak_rss'] = copy.deepcopy(trace.get('peak_rss'))
                    plugins.append(mechanism)
                    if index == 1:
                        base_pairs = copy.deepcopy(audit['task_work'].get('pairs', {}))
            final = self.read(folder / 'PUBLIC_FINAL.txt')
            consumer = turn['consumer']
            self.check(cell + ':final_binding:' + str(index), final == consumer['final'].encode('utf8'))
            tool_count = dict(Counter(item['tool'] for item in details))
            host = [wire for wire in wires if wire['business_attempt'] in numbers]
            value = {'cell': cell, 'group': group, 'turn_index': index, 'turn_label': turn['turn_label'],
                'owner_attempt_numbers': numbers, 'tool_counts': tool_count, 'tool_attempts': len(details),
                'owner_tool_errors': sum(item['owner_is_error'] is True for item in details),
                'CLI_tool_errors': sum(item['CLI_status'] != 'completed' or item['CLI_error'] is not None for item in details),
                'native_fallback_attempts': tool_count.get('execute_blender_code', 0) if group == 'C' else None,
                'owner_encoded_response_bytes': sum(item['owner_encoded_response_bytes'] for item in details),
                'consumer_visible_tool_text_utf8_bytes': sum(item['consumer_visible_content']['text_utf8_bytes'] for item in details),
                'tool_image_blocks': sum(item['consumer_visible_content']['image_blocks'] for item in details),
                'tool_image_decoded_bytes': sum(item['consumer_visible_content']['image_decoded_bytes'] for item in details),
                'input_image_count': consumer['input_image_count'], 'input_image_bytes': consumer['input_image_bytes'],
                'final_answer_utf8_bytes': len(final),
                'all_public_agent_text_utf8_bytes': sum(len(item['event']['item']['text'].encode('utf8')) for item in event_rows
                    if item['event'].get('type') == 'item.completed' and item['event'].get('item', {}).get('type') == 'agent_message'),
                'host_business_wire': wire_totals(host), 'attempts': details,
                'plugin_mechanism': plugins, 'native_execution_source': native,
                'native_current_mesh_acquisition_in_source': any(item['current_evaluated_mesh_acquisition_in_code'] for item in native) if group == 'N' else None,
                'native_current_triangulation_in_source': any(item['current_triangulation_in_code'] for item in native) if group == 'N' else None,
                'native_prior_function_calls_in_source': sorted({name for item in native for name in item['prior_functions_referenced_by_call_sites']}) if group == 'N' else [],
                'provider_serialized_tool_input_bytes': None,
                'provider_service_time_or_retries': None}
            turns.append(value)
        self.check(cell + ':all_attempts_assigned_once', all_numbers == [item['attempt'] for item in attempts])
        self.check(cell + ':wire_tool_bytes_recomputed', sum(item['response_bytes'] for item in attempts) == tools['wire_tool_bytes'])
        administrative = [wire for wire in wires if wire['business_attempt'] is None]
        plugin_rpc = self.json(owner / 'plugin/RPC.json') if group == 'C' else None
        return {'cell': cell, 'group': group, 'pair': row['pair'], 'turns': turns,
            'source_archive_sha256': sha(archive_raw), 'source_manifest_sha256': sha(manifest_raw),
            'host_wire_total': wire_totals(wires), 'host_wire_business': wire_totals([wire for wire in wires if wire['business_attempt'] is not None]),
            'host_wire_administrative': wire_totals(administrative), 'host_wire_rows': wires,
            'plugin_stdio_RPC': plugin_rpc,
            'geometry_cache_actual_resident_memory_bytes': None,
            'scope': 'Wire files measure recorded payload bytes. Administrative snapshots/EDIT/close are separate from business attempts.'}

    def run(self):
        self.read(PLAN, PLAN_SHA)
        seal = self.json(REVIEW / 'QUALITY_SEAL.json', SEAL_SHA)
        for name, digest in seal['independent_evidence_sha256'].items():
            self.read(REVIEW / name, digest)
        self.check('quality_seal_eligible', seal['quality']['primary_complete_correct'] == 18
                   and seal['quality']['current_state_basis_sufficient'] == 18 and seal['execution']['completed_episodes'] == 6)
        delivery = self.json(BATCH / 'DELIVERY_MANIFEST.json', seal['delivery_manifest_sha256'])
        delivered = {row['path']: row['sha256'] for row in delivery['files']}
        self.read(BATCH / 'quality/ANONYMOUS_QUALITY.zip', seal['anonymous_package_sha256'])
        self.read(BATCH / 'private/ANON_MAP.json', delivered['private/ANON_MAP.json'])
        result = self.json(BATCH / 'RUN_RESULT.json', delivered['RUN_RESULT.json'])
        self.check('fixed_episode_order', tuple(row['cell'] for row in result['records']) == ORDER)
        episodes = [self.episode(row, delivered) for row in result['records']]
        turns = [turn for episode in episodes for turn in episode['turns']]
        self.check('six_episodes_eighteen_turns', len(episodes) == 6 and len(turns) == 18)
        self.check('native_evaluated_mesh_acquisition_including_data_access', all(
            turn['native_current_mesh_acquisition_in_source'] is True for turn in turns if turn['group'] == 'N'))
        self.read(Path(__file__))
        self.read(ROOT / 'verification/native_plugin_complex_003/actor.py')
        self.read(ROOT / 'verification/m4_surface_scan_continuity_001_fix1/runtime/actor.py')
        self.check('all_inputs_unchanged', all(sha(Path(path).read_bytes()) == digest for path, digest in self.inputs.items()))
        summary = {}
        for group in ('N', 'C'):
            selected = [turn for turn in turns if turn['group'] == group]
            summary[group] = {key: sum(turn[key] for turn in selected) for key in (
                'tool_attempts', 'owner_tool_errors', 'CLI_tool_errors', 'owner_encoded_response_bytes',
                'consumer_visible_tool_text_utf8_bytes', 'tool_image_blocks', 'tool_image_decoded_bytes', 'final_answer_utf8_bytes')}
            summary[group]['host_business_requests'] = sum(turn['host_business_wire']['requests'] for turn in selected)
            summary[group]['host_business_request_bytes'] = sum(turn['host_business_wire']['request_bytes'] for turn in selected)
            summary[group]['host_business_response_bytes'] = sum(turn['host_business_wire']['response_bytes'] for turn in selected)
        return {'schema': 'continuous_002_cost_mechanism_v1', 'cycle': 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002-COST',
            'quality_seal_sha256': SEAL_SHA, 'cost_dispatch_plan_sha256': PLAN_SHA,
            'delivery_commit': seal['delivery_commit'], 'preparation_commit': seal['preparation_commit'],
            'episodes': episodes, 'turns': turns, 'group_summary': summary,
            'checks': self.checks, 'passed': True, 'inputs_sha256': self.inputs,
            'unknown': {'geometry_cache_actual_RAM_bytes': None, 'provider_serialized_input_bytes': None,
                'native_in_process_mesh_collection_bytes': None,
                'provider_service_time_retries_requests': None, 'native_dynamic_kernel_counts': None,
                'internal_algorithm_fallback_count_without_counter': None, 'transport_protocol_overhead_bytes': None},
            'measurement_scope': {'tool_text_bytes': 'UTF8 text fields from actual completed CLI tool events, independently matched to owner content.',
                'host_bytes': 'Exact REQUEST.bin/RESPONSE.bin payload bytes, partitioned by actual owner attempt intervals.',
                'capture_bytes': 'UTF8 stdout returned by actual host calls, including registered framing where present.',
                'kernel_cache': 'This 002 audit task_work and pair rows, corroborated with host scene-delta resources and worker observations.',
                'native_reuse': 'Actual successful scripts reference prior-defined functions and reacquire/triangulate current meshes; AST site counts are not dynamic counts.'},
            'new_model_calls': 0, 'new_Blender_calls': 0, 'new_product_calls': 0, 'new_API_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE.resolve()):
        raise ValueError('mechanism_output_outside_assigned_directory')
    builder = Builder()
    try:
        value = builder.run()
    except BaseException as error:
        save(output.with_name(output.stem + '_FAILURE.json'), {'type': type(error).__name__, 'message': str(error),
             'traceback': traceback.format_exc(), 'checks': builder.checks, 'inputs_sha256': builder.inputs,
             'new_model_Blender_product_API_calls': 0})
        raise
    save(output, value)
    print(json.dumps({'passed': value['passed'], 'episodes': len(value['episodes']), 'turns': len(value['turns']),
                      'checks': len(value['checks']), 'group_summary': value['group_summary']}))
