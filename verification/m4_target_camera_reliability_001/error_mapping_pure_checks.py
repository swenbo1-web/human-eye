"""Exercise only the public error serializer with fixed synthetic exceptions."""

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from human_eye_plugin.blender_host import BlenderHostError
from human_eye_plugin.blender_process import HostRemoteError
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer


class LocalSubclass(BlenderHostError):
    pass


class RemoteDictSubclass(dict):
    pass


class ErrorFieldsService:
    def request_error_fields(self, error=None):
        return {'allow_action': False, 'execution_authority': False, 'executed': False,
                'verified': False, 'execution_verified': False, 'execution_status': 'not_executed'}


def exception_for(case, reason):
    message = 'active_observation_target_camera_depth_unknown' if case['variation'] == 'other_message' else reason
    if case['kind'] == 'local':
        return BlenderHostError(message)
    if case['kind'] == 'local_subclass':
        return LocalSubclass(message)
    if case['kind'] == 'value_error':
        return ValueError(message)
    if case['kind'] == 'runtime_error':
        return RuntimeError(message)
    remote = {'type': 'BlenderHostError', 'message': message, 'mutation_uncertain': False}
    variation = case['variation']
    if variation == 'wrong_type':
        remote['type'] = 'ValueError'
    elif variation == 'prefix':
        remote['message'] = 'prefix:' + reason
    elif variation == 'suffix':
        remote['message'] = reason + ':suffix'
    elif variation == 'mutation_true':
        remote['mutation_uncertain'] = True
    elif variation == 'mutation_zero':
        remote['mutation_uncertain'] = 0
    elif variation == 'missing_field':
        del remote['mutation_uncertain']
    elif variation == 'extra_field':
        remote['extra'] = 'unrecognized'
    elif variation == 'message_integer':
        remote['message'] = 7
    elif variation == 'dict_subclass':
        remote = RemoteDictSubclass(remote)
    return HostRemoteError(remote)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--out', required=True)
    arguments = parser.parse_args()
    directory = Path(__file__).resolve().parent
    plan_path = directory / 'ERROR_MAPPING_TEST_PLAN.json'
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    source = ROOT / 'human_eye_plugin/live_spatial_mcp.py'
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    server = LiveSpatialMCPServer(ErrorFieldsService())
    rows = []
    for case in plan['cases']:
        error = exception_for(case, plan['reason'])
        actual = server._error_result(error)
        metadata = json.loads(actual['content'][0]['text'])
        matched = case['mapped'] and not arguments.baseline
        checks = {
            'status': metadata['status'] == ('unknown' if matched else 'error'),
            'error_text_preserved': metadata['error'] == str(error),
            'MCP_error_contract': actual['isError'] is True,
            'single_text_block': [block['type'] for block in actual['content']] == ['text'],
            'tool_outcome_preserved': metadata['tool_outcome'] == 'unknown',
            'automatic_retry_preserved': metadata['automatic_retry'] is False,
            'request_fields_preserved': all(metadata[key] == value for key, value in ErrorFieldsService().request_error_fields().items()),
            'no_fabricated_capture': not set(plan['forbidden_fabricated_fields']) & set(metadata),
            'numerical_reason_scope': all(metadata.get(key) == value for key, value in plan['expected_matching_metadata'].items())
                if matched else not {'reason', 'observation_mode', 'observation_status'} & set(metadata),
        }
        rows.append({'id': case['id'], 'expected_mapped_after_fix': case['mapped'],
                     'expected_mapped_in_this_run': matched, 'actual': metadata,
                     'checks': checks, 'passed': all(checks.values())})
    unchanged = source_sha == hashlib.sha256(source.read_bytes()).hexdigest()
    result = {
        'schema': 'm4-target-camera-error-mapping-pure-checks-v1',
        'phase': 'baseline_before_mapping_edit' if arguments.baseline else 'candidate_mapping',
        'source': {'path': str(source), 'sha256': source_sha, 'unchanged_during_run': unchanged},
        'test_plan': {'path': str(plan_path), 'sha256': hashlib.sha256(plan_bytes).hexdigest()},
        'case_count': len(rows), 'assertion_count': sum(len(row['checks']) for row in rows),
        'cases': rows, 'passed': unchanged and all(row['passed'] for row in rows),
        'new_product_observations': 0, 'new_Blender_starts': 0, 'new_rasters': 0, 'new_model_calls': 0,
        'scope': 'fixed synthetic error-contract cases, not camera scenes or actual host qualification',
    }
    output = directory / arguments.out
    with output.open('x', encoding='utf8', newline='\n') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'passed': result['passed'], 'case_count': result['case_count'],
                      'assertion_count': result['assertion_count'], 'output': str(output)}))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
