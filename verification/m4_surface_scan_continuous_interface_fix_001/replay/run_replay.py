"""Source-bound offline replay through the old and new archive_turn entries."""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import traceback
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = HERE.parents[2]
OLD_BATCH = ROOT / 'verification/m4_surface_scan_continuous_consumption_001'
OLD_TRANSPORT = ROOT / 'verification/m4_surface_scan_continuity_001_fix1/runtime/consumer_transport.py'
NEW_TRANSPORT = BATCH / 'runtime/consumer_transport.py'
COMPATIBILITY = BATCH / 'compatibility.py'
REVIEW = Path('D:/hefe/verification/fixes/20261113_m4_surface_scan_continuous_quality_review/interface')
PLAN = Path('D:/hefe/docs/M4_SURFACE_SCAN_CONTINUOUS_INTERFACE_FIX_001_PLAN.md')
PLAN_SHA = 'ece9040ed2553687d54ba57b3d4d6acaeaf30610ec526a9353adf95d66a51ae5'
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf8')


def exact(left, right):
    return encoded(left) == encoded(right)


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def save(path, value):
    put(path, encoded(value))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Replay:
    def __init__(self, output):
        self.output = Path(output).resolve()
        if not self.output.is_relative_to(HERE.resolve()):
            raise ValueError('replay_output_must_stay_in_new_batch_replay')
        self.output.mkdir(parents=True, exist_ok=False)
        self.inputs = {}
        self.checks = []

    def read(self, path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = sha(raw)
        if expected is not None and digest != expected:
            raise ValueError('frozen_input_digest_mismatch:' + str(path))
        previous = self.inputs.get(str(path))
        if previous is not None and previous['sha256'] != digest:
            raise ValueError('input_changed_during_replay:' + str(path))
        self.inputs[str(path)] = {'sha256': digest, 'bytes': len(raw)}
        return raw

    def read_json(self, path, expected=None):
        return json.loads(self.read(path, expected))

    def check(self, name, passed):
        self.checks.append({'name': name, 'passed': bool(passed)})

    def successful_sources(self, review):
        binding_path = OLD_BATCH / 'quality/private/BINDING.json'
        delivery = self.read_json(OLD_BATCH / 'DELIVERY_MANIFEST.json')
        delivered = {row['path']: row for row in delivery['files']}
        binding = self.read_json(binding_path, delivered['quality/private/BINDING.json']['sha256'])
        by_anon = {row['anonymous_episode_id']: row for row in binding['episodes']}
        cases = []
        for ordinal, expected in enumerate(review['actual_success_attempts'], 1):
            anon = expected['anonymous_episode']
            origin = by_anon[anon]['original_sources']
            folder = Path(origin['folder'])
            archive_path = folder / 'ORIGINALS.zip'
            manifest_path = folder / 'RUNTIME_MANIFEST.json'
            manifest = self.read_json(manifest_path, origin['manifest_sha256'])
            archive_raw = self.read(archive_path, origin['archive_sha256'])
            relative_archive = archive_path.relative_to(OLD_BATCH).as_posix()
            relative_manifest = manifest_path.relative_to(OLD_BATCH).as_posix()
            self.check(anon + ':archive_delivery_binding', delivered[relative_archive]['sha256'] == sha(archive_raw))
            self.check(anon + ':manifest_delivery_binding', delivered[relative_manifest]['sha256'] == origin['manifest_sha256'])
            self.check(anon + ':manifest_inventory_binding', manifest['members'] == origin['members'])
            public_path = OLD_BATCH / 'quality/public' / anon / expected['turn'] / 'tool_evidence.json'
            projection = self.read_json(public_path, delivered[public_path.relative_to(OLD_BATCH).as_posix()]['sha256'])
            with zipfile.ZipFile(archive_path) as bundle:
                names = bundle.namelist()
                if len(names) != len(set(names)):
                    raise ValueError('duplicate_original_archive_member')

                def member(name):
                    raw = bundle.read(name)
                    meta = manifest['members'][name]
                    if meta != {'bytes': len(raw), 'sha256': sha(raw)}:
                        raise ValueError('original_member_digest:' + name)
                    return raw

                tools_raw = member('owner/TOOLS.json')
                tools = json.loads(tools_raw)['tools']
                selected = tools[expected['attempt'] - 1]
                attempt = selected['attempt']
                owner_prefix = 'owner/tool_' + str(attempt).zfill(2) + '/'
                request_raw = member(owner_prefix + 'REQUEST.json')
                response_raw = member(owner_prefix + 'RESPONSE.json')
                events_name = 'c/turns/BASE/events.jsonl'
                events_raw = member(events_name)
                completed = [(line, json.loads(line)['event']) for line in events_raw.splitlines()
                    if json.loads(line)['event'].get('type') == 'item.completed'
                    and json.loads(line)['event'].get('item', {}).get('type') == 'mcp_tool_call']
                self.check(anon + ':owner_CLI_attempt_count', len(completed) == len(tools))
                line, event = completed[expected['attempt'] - 1]
                item = event['item']
                request, response = json.loads(request_raw), json.loads(response_raw)
                projected_attempt = projection['owner_attempts'][expected['attempt'] - 1]
                projected_item = [row for row in projection['public_tool_events'] if row['phase'] == 'item.completed'][expected['attempt'] - 1]
                file_hashes = {row['kind']: row['original_sha256'] for row in projected_attempt['source_files']}
                self.check(anon + ':request_projection_source_' + str(attempt), file_hashes['REQUEST.json'] == sha(request_raw))
                self.check(anon + ':response_projection_source_' + str(attempt), file_hashes['RESPONSE.json'] == sha(response_raw))
                self.check(anon + ':event_projection_source_' + str(attempt), projected_item['source_sha256'] == sha(events_raw)
                           and projected_item['source_line_sha256'] == sha(line))
                projected_keys = ('type', 'tool', 'server', 'arguments', 'result', 'error', 'status', 'command')
                self.check(anon + ':public_item_matches_original_' + str(attempt),
                    exact(projected_item['event'], {key: item[key] for key in projected_keys if key in item}))
                content_hash = sha(json.dumps(response['result']['content'], ensure_ascii=False, sort_keys=True).encode())
                self.check(anon + ':root_review_content_binding_' + str(attempt), content_hash == expected['content_sha256'])
                self.check(anon + ':original_request_binding_' + str(attempt),
                    request['params']['name'] == item['tool'] and exact(request['params']['arguments'], item['arguments']))
                owner_files = {name.removeprefix(owner_prefix): member(name) for name in names if name.startswith(owner_prefix)}
                source = {'case': 'actual_success_' + str(ordinal).zfill(2), 'kind': 'actual_success',
                    'anonymous_episode': anon, 'attempt': attempt, 'archive': str(archive_path),
                    'archive_sha256': sha(archive_raw), 'manifest_sha256': origin['manifest_sha256'],
                    'request_member': owner_prefix + 'REQUEST.json', 'request_sha256': sha(request_raw),
                    'response_member': owner_prefix + 'RESPONSE.json', 'response_sha256': sha(response_raw),
                    'events_member': events_name, 'events_sha256': sha(events_raw), 'event_line_sha256': sha(line),
                    'owner_tools_sha256': sha(tools_raw), 'public_projection_sha256': sha(public_path.read_bytes()),
                    'content_sha256': content_hash}
                cases.append({'source': source, 'request': request, 'response': response, 'item': item,
                              'owner_files': owner_files, 'event_line': line})
        self.check('actual_success_sources_exactly_fourteen', len(cases) == 14)
        return cases

    def historical_errors(self, review):
        historical = ROOT / 'verification/m4_surface_scan_consumption_001'
        fixed = review['fixed_CLI_binding']
        old_plan = self.read_json(ROOT / fixed['frozen_plan'], fixed['frozen_plan_sha256'])
        old_driver = self.read(ROOT / fixed['driver_path'], fixed['driver_sha256'])
        self.check('historical_fixed_CLI_matches_current', old_plan['CLI_sha256'] == fixed['CLI_sha256'] == CLI_SHA)
        self.check('historical_driver_binds_CLI_before_launch', b"assert sha(transport.EXE) == plan['CLI_sha256']" in old_driver)
        cases = []
        for ordinal, expected in enumerate(review['historical_real_error_examples'], 1):
            request_path = ROOT / expected['owner_request_path']
            response_path = ROOT / expected['owner_response_path']
            request_raw = self.read(request_path, expected['request_sha256'])
            response_raw = self.read(response_path, expected['owner_response_sha256'])
            event_path = ROOT / expected['CLI_event_file_path']
            events_raw = self.read(event_path, expected['event_file_sha256'])
            lines = [line for line in events_raw.splitlines() if sha(line) == expected['event_line_sha256']]
            self.check('historical_error_unique_raw_line_' + str(ordinal), len(lines) == 1)
            line = lines[0]
            item = json.loads(line)['event']['item']
            request, response = json.loads(request_raw), json.loads(response_raw)
            attempt = int(request_path.parent.name.removeprefix('tool_'))
            self.check('historical_error_request_binding_' + str(ordinal), request['params']['name'] == item['tool']
                       and exact(request['params']['arguments'], item['arguments']))
            self.check('historical_error_flags_and_body_' + str(ordinal), response['result']['isError'] is True
                and item['status'] == 'failed' and item['error'] is None
                and exact(response['result']['content'], item['result']['content']))
            owner_files = {path.relative_to(request_path.parent).as_posix(): self.read(path)
                           for path in sorted(request_path.parent.rglob('*')) if path.is_file()}
            source = {'case': 'actual_error_' + str(ordinal).zfill(2), 'kind': 'actual_historical_tool_error',
                'attempt': attempt, 'request': str(request_path), 'request_sha256': sha(request_raw),
                'response': str(response_path), 'response_sha256': sha(response_raw),
                'events': str(event_path), 'events_sha256': sha(events_raw), 'event_line_sha256': sha(line),
                'fixed_CLI_plan_sha256': fixed['frozen_plan_sha256'], 'fixed_CLI_driver_sha256': fixed['driver_sha256'],
                'fixed_CLI_sha256': CLI_SHA}
            cases.append({'source': source, 'request': request, 'response': response, 'item': item,
                          'owner_files': owner_files, 'event_line': line})
        self.check('actual_historical_error_sources_exactly_three', len(cases) == 3)
        return cases

    def archive_case(self, case, modules, expected_binding, *, expected_predicate=None, run_old=True):
        source = case['source']
        name = source['case']
        directory = self.output / 'cases' / name
        owner = directory / 'owner'
        attempt = source['attempt']
        original = owner / ('tool_' + str(attempt).zfill(2))
        for relative, raw in case['owner_files'].items():
            put(original / relative, raw)
        # Modified variants replace only their explicitly registered inputs.
        (original / 'REQUEST.json').write_bytes(encoded(case['request']) if source['kind'] == 'synthetic_variant'
                                              else case['owner_files']['REQUEST.json'])
        (original / 'RESPONSE.json').write_bytes(encoded(case['response']) if source['kind'] == 'synthetic_variant'
                                               else case['owner_files']['RESPONSE.json'])
        for relative in case.get('missing_owner_files', []):
            target = (original / relative).resolve()
            if not target.is_relative_to(original.resolve()):
                raise ValueError('missing_file_variant_outside_case')
            target.unlink()
        save(owner / 'TOOLS.json', {'tools': [{'attempt': attempt}]})
        predicate = self.success_match(case['response'], case['item'])
        expected_predicate = expected_binding if expected_predicate is None else expected_predicate
        self.check(name + ':success_predicate_expected', predicate is expected_predicate)
        outcomes = {}
        for label, module in modules:
            if label == 'old' and not run_old:
                continue
            turn = directory / label / 'turn'
            put(turn / 'events.jsonl', case['event_line'] + b'\n')
            public = {'type': 'item.completed', 'item': copy.deepcopy(case['item'])}
            result = module.archive_turn(turn, {'audit_dir': str(owner)}, attempt, [public])
            errors = result['business_binding_errors']
            match = not errors
            outcomes[label] = {'matched': match, 'business_binding_errors': errors,
                'archive': str(Path(result['archive']).relative_to(self.output)),
                'archive_sha256': result['archive_sha256'], 'source_files_sha256': result['source_files_sha256']}
            with zipfile.ZipFile(result['archive']) as bundle:
                for relative in ('REQUEST.json', 'RESPONSE.json'):
                    if not (original / relative).exists():
                        continue
                    archive_member = 'owner_turn/' + original.name + '/' + relative
                    self.check(name + ':' + label + ':original_copy:' + relative,
                               bundle.read(archive_member) == (original / relative).read_bytes())
            if label == 'old' and source['kind'] == 'actual_success':
                self.check(name + ':old_reproduces_result_failure', not match
                    and any(error['reason'] == 'CLI_result_differs_from_owner' for error in errors))
            elif label == 'old':
                self.check(name + ':old_expected_binding', match is expected_binding)
            elif label == 'new':
                self.check(name + ':new_expected_binding', match is expected_binding)
        save(directory / 'SOURCE.json', source)
        save(directory / 'REPLAY_RESULT.json', {'source': source, 'expected_new_binding_match': expected_binding,
            'success_predicate': predicate, 'expected_success_predicate': expected_predicate,
            'outcomes': outcomes, 'scope': 'Offline actual archive_turn replay. Original formal execution classification is unchanged.'})
        return {'case': name, 'source_kind': source['kind'], 'expected_new_binding_match': expected_binding,
                'success_predicate': predicate, 'expected_success_predicate': expected_predicate, 'outcomes': outcomes}

    def variants(self, actual, modules):
        results = []

        def variant(name, change, binding=False, predicate=None, run_old=False):
            case = copy.deepcopy(actual)
            case['source'] = {'case': 'variant_' + name, 'kind': 'synthetic_variant', 'attempt': 1,
                'based_on': actual['source'], 'mutation': name,
                'scope': 'Directed offline mutation. This is not an observed CLI mapping.'}
            change(case)
            event = json.loads(case['event_line'])
            event['event']['item'] = case['item']
            case['event_line'] = json.dumps(event, ensure_ascii=False, allow_nan=False).encode('utf8')
            results.append(self.archive_case(case, modules, binding, expected_predicate=predicate, run_old=run_old))

        variant('request_argument_changed', lambda case: case['item'].__setitem__('arguments', {'changed': True}), predicate=True)
        variant('request_tool_changed', lambda case: case['item'].__setitem__('tool', 'changed_tool'), predicate=True)
        variant('request_original_missing', lambda case: case.__setitem__('missing_owner_files', ['REQUEST.json']), predicate=True)
        variant('content_text_changed', lambda case: case['item']['result']['content'][0].__setitem__('text', 'changed business text'))
        variant('content_block_removed', lambda case: case['item']['result']['content'].pop())
        variant('content_field_missing', lambda case: case['response']['result'].pop('content'))
        variant('owner_isError_true', lambda case: case['response']['result'].__setitem__('isError', True))
        variant('owner_isError_zero', lambda case: case['response']['result'].__setitem__('isError', 0))
        variant('owner_isError_empty_string', lambda case: case['response']['result'].__setitem__('isError', ''))
        variant('owner_isError_missing', lambda case: case['response']['result'].pop('isError'))
        variant('CLI_failed', lambda case: case['item'].__setitem__('status', 'failed'))
        variant('CLI_error_nonnull', lambda case: case['item'].__setitem__('error', {'message': 'directed transport error'}))
        variant('CLI_error_zero', lambda case: case['item'].__setitem__('error', 0))
        variant('CLI_error_missing', lambda case: case['item'].pop('error'))
        variant('RPC_error_with_result', lambda case: case['response'].__setitem__('error', {'code': -32000, 'message': 'directed RPC error'}))
        variant('RPC_error_null_present', lambda case: case['response'].__setitem__('error', None))
        variant('CLI_nonempty_structured', lambda case: case['item']['result'].__setitem__('structured_content', {'facts': [1]}))
        variant('owner_nonempty_structured', lambda case: case['response']['result'].__setitem__('structuredContent', {'facts': [1]}))
        variant('unknown_null_field', lambda case: case['item']['result'].__setitem__('unknown_field', None))
        variant('content_type_dict', lambda case: case['item']['result'].__setitem__('content', {'text': 'wrong type'}))

        def same_representation(case):
            case['item']['result'] = copy.deepcopy(case['response']['result'])

        variant('same_representation_success_control', same_representation, binding=True, run_old=True)

        def same_representation_error(case):
            case['response']['result']['isError'] = True
            case['item']['result'] = copy.deepcopy(case['response']['result'])
            case['item']['status'] = 'failed'
            case['item']['error'] = None

        variant('same_representation_error_loyal_delivery_control', same_representation_error,
                binding=True, predicate=False, run_old=True)

        def nested_business(case):
            block = {'type': 'text', 'text': '{"isError":true,"structured_content":{"usage":9}}',
                     'annotations': {'isError': True, 'structured_content': {'facts': [1, False, '0']}}}
            case['response']['result']['content'] = [copy.deepcopy(block)]
            case['item']['result']['content'] = [copy.deepcopy(block)]

        variant('nested_same_names_preserved', nested_business, binding=True)

        def nested_tamper(case):
            nested_business(case)
            case['item']['result']['content'][0]['annotations']['structured_content']['facts'][1] = 0

        variant('nested_bool_numeric_tamper', nested_tamper)

        def matching_nonempty_structure(case):
            case['response']['result']['structuredContent'] = {'facts': [1]}
            case['item']['result']['structured_content'] = {'facts': [1]}

        variant('matching_nonempty_structured_outside_domain', matching_nonempty_structure)
        return results

    def run(self):
        self.read(PLAN, PLAN_SHA)
        self.read(REVIEW / 'REPORT.md')
        review = self.read_json(REVIEW / 'RESULTS.json')
        self.check('independent_review_passed', review['passed'] is True)
        old_guard = self.read_json(OLD_BATCH / 'RUN_RESULT.json')
        self.check('old_formal_still_six_failed_twelve_not_run', old_guard['execution_counts']['failed'] == 6
                   and old_guard['execution_counts']['not_run'] == 12 and old_guard['execution_counts']['completed'] == 0)
        interface = self.read_json(ROOT / 'verification/m4_surface_scan_continuity_001/cli/CLI_INTERFACE.json')
        self.check('fixed_CLI_interface_same_bytes', interface['executable_sha256'] == CLI_SHA)
        for path in (OLD_TRANSPORT, NEW_TRANSPORT, COMPATIBILITY, Path(__file__)):
            self.read(path)
        old = load('_interface_replay_old_archive', OLD_TRANSPORT)
        new = load('_interface_replay_new_archive', NEW_TRANSPORT)
        self.success_match = load('_interface_replay_success_predicate', COMPATIBILITY).successful_result_matches
        modules = [('old', old), ('new', new)]
        successes = self.successful_sources(review)
        errors = self.historical_errors(review)
        rows = [self.archive_case(case, modules, True) for case in successes]
        rows.extend(self.archive_case(case, modules, False) for case in errors)
        directed = self.variants(successes[0], modules)
        unchanged = {path: {'before': meta['sha256'], 'after': sha(Path(path).read_bytes())}
                     for path, meta in self.inputs.items()}
        self.check('all_frozen_sources_unchanged_after_replay', all(value['before'] == value['after'] for value in unchanged.values()))
        result = {'schema': 'continuous_interface_archive_replay_v1',
            'cycle': 'M4-SURFACE-SCAN-CONTINUOUS-INTERFACE-FIX-001',
            'passed': all(row['passed'] for row in self.checks), 'check_count': len(self.checks),
            'failed_checks': [row for row in self.checks if not row['passed']],
            'actual_success_cases': 14, 'actual_historical_error_cases': 3,
            'old_success_reproduced_failures': sum(not row['outcomes']['old']['matched'] for row in rows[:14]),
            'new_success_matches': sum(row['outcomes']['new']['matched'] for row in rows[:14]),
            'new_historical_errors_refused': sum(not row['outcomes']['new']['matched'] for row in rows[14:]),
            'directed_variant_cases': len(directed), 'actual_cases': rows, 'directed_variants': directed,
            'fixed_CLI_sha256': CLI_SHA, 'old_formal_execution_changed': False,
            'model_calls': 0, 'Blender_calls': 0, 'product_calls': 0, 'API_calls': 0,
            'limits': ['Offline source/receipt replay does not prove actual provider resume.',
                       'Missing old thin EXIT remains unknown.',
                       'Directed variants are synthetic and do not prove unobserved CLI mappings.',
                       'Git commit provenance is named by the frozen plan and delivery manifest. This script executes no Git command.']}
        save(self.output / 'SOURCE_INDEX.json', {'actual_success_sources': [case['source'] for case in successes],
                                               'historical_error_sources': [case['source'] for case in errors]})
        save(self.output / 'INPUT_HASHES.json', self.inputs)
        save(self.output / 'UNCHANGED.json', unchanged)
        save(self.output / 'CHECKS.json', self.checks)
        save(self.output / 'RESULTS.json', result)
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    replay = Replay(args.output)
    try:
        result = replay.run()
    except BaseException as error:
        failure = {'passed': False, 'type': type(error).__name__, 'message': str(error),
                   'traceback': traceback.format_exc(), 'checks_before_failure': replay.checks,
                   'input_hashes': replay.inputs, 'model_calls': 0, 'Blender_calls': 0, 'product_calls': 0, 'API_calls': 0}
        save(replay.output / 'PREPARATION_FAILURE.json', failure)
        raise
    print(json.dumps({key: result[key] for key in (
        'passed', 'check_count', 'actual_success_cases', 'old_success_reproduced_failures',
        'new_success_matches', 'actual_historical_error_cases', 'new_historical_errors_refused',
        'directed_variant_cases', 'failed_checks', 'model_calls', 'Blender_calls', 'product_calls', 'API_calls')}))
    raise SystemExit(0 if result['passed'] else 1)
