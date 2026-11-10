"""Compare saved, guarded offline evidence only; never import product or QA.

The fifteen case names, fact positions and permitted old/new constants below
are finite. No recursive field-name deletion or arbitrary JSON-text decoding
is used. Original evidence files remain the authority for every recorded diff.
"""
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SUITE = 'verification/m4_local_relation_evidence_001/tests/test_local_relation_evidence.py:LocalRelationEvidenceTests'
TEST = 'verification/m4_local_relation_evidence_001/tests/test_local_relation_evidence.py'
BASE = '7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1'
CANDIDATE = '53db41976085ce5f361d026196f4da5faf80d639af33dfced35ba58e328ef732'
OLD_VERSION = 'task-closed-solid-exact-v1'
NEW_VERSION = 'task-closed-solid-exact-local-evidence-v2'
OLD_SCOPE = 'Proof category only; surface witnesses are not shared-interior proofs.'
NEW_SCOPE = ('Certificate category with local evidence when available. '
    'Transverse evidence identifies current captured triangles and approximates their boundary crossing; '
    'the exact midpoint is on both boundaries, not in their shared volume interior. '
    'Neither a boundary location nor surface distance is penetration depth.')
DIRECT = {'frozen', 'frozen_swapped', 'frozen_rigid', 'contact_then_transverse',
    'large_point_unavailable', 'separated', 'touching', 'contained', 'open_unknown'}
SERVICE = {'service_cold', 'service_warm', 'service_same_geometry_new_generation', 'service_geometry_changed'}
CASES = DIRECT | SERVICE | {'public_ordinary', 'public_compact'}
TRANSVERSE = {'frozen', 'frozen_swapped', 'frozen_rigid', 'contact_then_transverse',
    'large_point_unavailable', 'service_cold', 'service_warm',
    'service_same_geometry_new_generation', 'public_ordinary', 'public_compact'}
PROOFS = {'frozen', 'frozen_swapped', 'frozen_rigid', 'contact_then_transverse',
    'large_point_unavailable', 'public_ordinary'}
COUNTERS = ('diagnostics', 'calls', 'loop_counts', 'loop_work_amounts', 'checkpoint_counts',
    'capture_calls', 'host_rpc_calls', 'host_write_calls')
MISSING = object()


def raw_hash(raw):
    return hashlib.sha256(raw).hexdigest()


def encoding(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


def read(path):
    return json.loads(path.read_bytes())


def brief(value):
    if value is MISSING:
        return {'present': False}
    raw = encoding(value)
    result = {'present': True, 'type': type(value).__name__, 'json_bytes': len(raw), 'sha256': raw_hash(raw)}
    if value is None or isinstance(value, (bool, int, float)) or isinstance(value, str) and len(value) <= 96:
        result['value'] = value
    return result


def pointer(parts):
    return '$' + ''.join('/' + str(x).replace('~', '~0').replace('/', '~1') for x in parts)


def differences(left, right, path=()):
    """Record original changes, not a normalization rule."""
    if isinstance(left, dict) and isinstance(right, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                result.append({'path': pointer((*path, key)), 'baseline': brief(left.get(key, MISSING)),
                    'candidate': brief(right.get(key, MISSING))})
            else:
                result.extend(differences(left[key], right[key], (*path, key)))
        return result
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [row for i, (a, b) in enumerate(zip(left, right)) for row in differences(a, b, (*path, i))]
    if type(left) is type(right) and left == right:
        return []
    return [{'path': pointer(path), 'baseline': brief(left), 'candidate': brief(right)}]


def parent_at(value, path):
    for key in path[:-1]:
        value = value[key]
    return value, path[-1]


def fact_path(case):
    if case in DIRECT:
        return ()
    if case in SERVICE:
        return ('facts', 'closed_solid_relation')
    if case == 'public_ordinary':
        return ('pairs', 0, 'facts', 'closed_solid_relation')
    return ('candidates', 0, 'closed_solid_relation')


def fact_at(value, case):
    for key in fact_path(case):
        value = value[key]
    return value


def own_core(result, case):
    """Independently check the QA's existing finite core representation."""
    value = copy.deepcopy(result)
    if case not in DIRECT:
        value.pop('trace_id', None)
    fact_at(value, case).pop('local_evidence', None)
    return value


def main():
    issues, checks, inputs, cases = [], [], {}, {}
    output = HERE / 'OFFLINE_COMPARISON.json'
    if output.exists():
        raise FileExistsError('preserve_existing_offline_comparison')

    def check(condition, label):
        checks.append(label)
        if not condition:
            issues.append(label)

    saved = {}
    identity = {}
    results = {}
    for role, folder, expected in (('baseline', 'baseline_02', BASE), ('candidate', 'candidate_02', CANDIDATE)):
        for filename in ('EVIDENCE.json', 'RESULTS.json', 'EXECUTION_IDENTITY.json'):
            path = HERE / folder / filename
            raw = path.read_bytes()
            inputs[path.relative_to(HERE).as_posix()] = raw_hash(raw)
        all_data = read(HERE / folder / 'EVIDENCE.json')
        saved[role] = all_data[SUITE]
        identity[role] = read(HERE / folder / 'EXECUTION_IDENTITY.json')
        results[role] = read(HERE / folder / 'RESULTS.json')
        summary, source = results[role], identity[role]
        check(set(saved[role]) == CASES, role + '.exact_fifteen_cases')
        check(summary['successful'] is True and summary['tests'] == 36 and not summary['failures']
            and not summary['errors'] and not summary['external_operation_attempts'], role + '.original_36_pass_no_external_ops')
        check(summary['runtime_source_sha256'] == source['runtime_source_sha256'] == expected
            and summary['source_count'] == source['source_count'] == 137, role + '.fixed_source_pin')
        check(source['guard_verify_loaded'] is True and source['checkout_files_unchanged'] is True
            and source['loaded_tests_unchanged'] is True and source['original_read_evidence_unchanged'] is True,
            role + '.existing_source_guard_and_preservation')
        check(summary['model_consumers'] == summary['Blender_sessions'] == summary['network_sessions'] == 0,
            role + '.original_run_scope')
    check(identity['baseline']['loaded_tests'] == identity['candidate']['loaded_tests'], 'source.identical_QA_bytes_and_filenames')
    check(identity['baseline']['fixture_sha256'] == identity['candidate']['fixture_sha256'], 'source.identical_imported_fixture_bytes')
    check(identity['baseline']['loaded_tests'][TEST]['sha256'] == raw_hash((ROOT / TEST).read_bytes()), 'source.current_QA_matches_both_executions')

    def normalized(value, case, role, core=False):
        """Only this case's explicit result positions are permitted to differ."""
        item = copy.deepcopy(value)
        fact = fact_at(item, case)
        if not core:
            if case in TRANSVERSE:
                if role == 'baseline':
                    check('local_evidence' not in fact, case + '.' + role + '.new_fact_absent')
                else:
                    check('local_evidence' in fact, case + '.' + role + '.new_fact_present')
                    if 'local_evidence' in fact:
                        check(fact.get('certificate') == 'transverse_boundary_interiors', case + '.new_fact_original_certificate')
                        check((fact.get('measurement_valid') is True and fact.get('relation') == 'penetrating')
                            if case in DIRECT else (fact.get('status') == 'measured' and fact.get('value') == 'penetrating'),
                            case + '.new_fact_only_measured_transverse')
                        fact.pop('local_evidence')
            else:
                check('local_evidence' not in fact, case + '.' + role + '.nontransverse_no_new_fact')
        else:
            check('local_evidence' not in fact, case + '.' + role + '.own_core_no_new_fact')
        if case not in DIRECT:
            if core:
                check('trace_id' not in item, case + '.' + role + '.core_root_trace_absent')
            else:
                trace = item.pop('trace_id', None)
                check(isinstance(trace, str) and len(trace) == 32 and all(c in '0123456789abcdef' for c in trace),
                    case + '.' + role + '.root_trace_shape')
            source_path = ('context' if case == 'public_compact' else 'binding', 'runtime_source_sha256')
            container, key = parent_at(item, source_path)
            check(container.get(key) == (BASE if role == 'baseline' else CANDIDATE),
                case + '.' + role + '.exact_result_source_pin')
            container[key] = '<exactly_verified_runtime_source>'
        if case == 'public_compact':
            check(item['context'].get('certificate_scope') == (OLD_SCOPE if role == 'baseline' else NEW_SCOPE),
                case + '.' + role + '.exact_certificate_scope_text')
            item['context']['certificate_scope'] = '<exactly_verified_scope_text_change>'
        return item

    total_calls = {'baseline': Counter(), 'candidate': Counter()}
    total_result_bytes = {'baseline': 0, 'candidate': 0}
    for case in sorted(CASES):
        a, b = saved['baseline'][case], saved['candidate'][case]
        row = {'raw_case_differences': differences(a, b), 'invariants': {}, 'serialized_result_bytes': {},
            'permitted_result_differences': differences(a['result'], b['result'])}
        common_keys = {'input', 'result', 'core', 'diagnostics', 'calls', 'loop_counts',
            'loop_work_amounts', 'cache_algorithm_versions', 'raw_json', 'serialized_bytes'}
        if case in DIRECT:
            common_keys.add('checkpoint_counts')
        else:
            common_keys.update(('capture_calls', 'host_rpc_calls', 'host_write_calls', 'raw_tool_result'))
        if case in PROOFS and case != 'public_ordinary':
            common_keys.add('independent_local_proof')
        if case == 'contact_then_transverse':
            common_keys.add('first_contact_triangle_indices')
        check(set(a) == common_keys, case + '.exact_baseline_case_schema')
        check(set(b) == common_keys | ({'independent_local_proof'} if case == 'public_ordinary' else set()),
            case + '.exact_candidate_case_schema')
        input_equal = not differences(a['input'], b['input'])
        check(input_equal, case + '.identical_complete_input')
        row['invariants']['input'] = input_equal
        for name in COUNTERS:
            equal = (name in a) == (name in b) and not differences(a.get(name), b.get(name))
            check(equal, case + '.strict.' + name)
            row['invariants'][name] = equal
        for role, data in (('baseline', a), ('candidate', b)):
            result_raw = encoding(data['result'])
            check(data['raw_json'].encode('utf8') == result_raw and data['serialized_bytes'] == len(result_raw),
                case + '.' + role + '.actual_result_encoding_and_byte_count')
            check(not differences(data['core'], own_core(data['result'], case)), case + '.' + role + '.own_core_derivation')
            row['serialized_result_bytes'][role] = len(result_raw)
            row.setdefault('original_result_sha256', {})[role] = raw_hash(result_raw)
            total_result_bytes[role] += len(result_raw)
            total_calls[role].update(data['calls'])
        left, right = normalized(a['result'], case, 'baseline'), normalized(b['result'], case, 'candidate')
        row['unexplained_result_differences'] = differences(left, right)
        check(not row['unexplained_result_differences'], case + '.strict_original_result_after_exact_allowed_positions')
        left, right = normalized(a['core'], case, 'baseline', True), normalized(b['core'], case, 'candidate', True)
        row['unexplained_core_differences'] = differences(left, right)
        check(not row['unexplained_core_differences'], case + '.strict_recorded_core_after_exact_allowed_positions')
        check(len(a['cache_algorithm_versions']) == len(b['cache_algorithm_versions']), case + '.cache_version_list_length')
        version_differences = []
        for i, (old, new) in enumerate(zip(a['cache_algorithm_versions'], b['cache_algorithm_versions'])):
            if old == OLD_VERSION:
                check(new == NEW_VERSION, case + '.exact_closed_cache_version.' + str(i))
                version_differences.append({'index': i, 'baseline': old, 'candidate': new})
            else:
                check(old == new, case + '.other_cache_version_unchanged.' + str(i))
        row['cache_version_differences'] = version_differences
        check(a.get('first_contact_triangle_indices') == b.get('first_contact_triangle_indices'), case + '.first_contact_input_marker_unchanged')
        if case in PROOFS:
            check(a.get('independent_local_proof') is None and isinstance(b.get('independent_local_proof'), dict),
                case + '.existing_candidate_independent_oracle_record')
            row['candidate_oracle_record_sha256'] = raw_hash(encoding(b.get('independent_local_proof')))
        else:
            check('independent_local_proof' not in a and 'independent_local_proof' not in b,
                case + '.no_unplanned_oracle_record')
        if case in ('public_ordinary', 'public_compact'):
            row['public_encoding'] = {}
            for role, data in (('baseline', a), ('candidate', b)):
                wire = data['raw_tool_result']
                check(set(wire) == {'content', 'isError'} and wire['isError'] is False
                    and len(wire['content']) == 1 and set(wire['content'][0]) == {'type', 'text'}
                    and wire['content'][0]['type'] == 'text', case + '.' + role + '.known_MCP_text_slot')
                text = wire['content'][0]['text']
                # Exactly this protocol text slot is structured result JSON.
                # Native stdout/arbitrary fact strings are never parsed here.
                check(not differences(json.loads(text), data['result']), case + '.' + role + '.MCP_text_is_recorded_result')
                row['public_encoding'][role] = {'content_text_utf8_bytes': len(text.encode('utf8')),
                    'serialized_tool_result_utf8_bytes': len(encoding(wire)), 'original_tool_result_sha256': raw_hash(encoding(wire))}
            row['public_encoding']['content_text_delta_bytes'] = row['public_encoding']['candidate']['content_text_utf8_bytes'] - row['public_encoding']['baseline']['content_text_utf8_bytes']
            row['public_encoding']['serialized_tool_result_delta_bytes'] = row['public_encoding']['candidate']['serialized_tool_result_utf8_bytes'] - row['public_encoding']['baseline']['serialized_tool_result_utf8_bytes']
        elif case in SERVICE:
            check(a['raw_tool_result'] is None and b['raw_tool_result'] is None, case + '.no_invented_public_wire')
        else:
            check('raw_tool_result' not in a and 'raw_tool_result' not in b, case + '.kernel_has_no_public_wire')
        row['serialized_result_bytes']['delta'] = row['serialized_result_bytes']['candidate'] - row['serialized_result_bytes']['baseline']
        cases[case] = row

    check(total_calls['baseline'] == total_calls['candidate'], 'all_fifteen.aggregate_direct_operation_counts_identical')
    for name, digest in inputs.items():
        check(raw_hash((HERE / name).read_bytes()) == digest, 'input_unchanged.' + name)
    report = {'cycle_id': 'M4-LOCAL-RELATION-EVIDENCE-001', 'status': 'PASS' if not issues else 'FAIL',
        'issues': issues, 'checks_total': len(checks), 'checks_passed': len(checks) - len(issues),
        'comparison_script_sha256': raw_hash(Path(__file__).read_bytes()), 'input_sha256': inputs,
        'fixed_source_sha256': {'baseline': BASE, 'candidate': CANDIDATE}, 'source_count_each': 137,
        'QA_source_sha256': identity['baseline']['loaded_tests'][TEST]['sha256'],
        'original_tests_passed_each': 36, 'new_cases_compared': len(CASES), 'cases': cases,
        'aggregate_operation_counts': {role: dict(values) for role, values in total_calls.items()},
        'aggregate_serialized_result_bytes': {**total_result_bytes,
            'delta': total_result_bytes['candidate'] - total_result_bytes['baseline']},
        'fixed_scope_text_change': {'baseline': OLD_SCOPE, 'candidate': NEW_SCOPE},
        'old_regression_scope': 'Thirty existing methods per version retain their original passed assertions. Their dynamic nearest_trace telemetry is not asserted byte-equal or normalized by this comparator.',
        'source_qualification_scope': 'Physical snapshots of 137 original source files under verified loader; actual source_kind values are recorded below. Not installed/default-runtime/Blender acceptance.',
        'recorded_source_kind': {role: value['source_kind'] for role, value in identity.items()},
        'new_local_evidence_oracle_scope': 'Independent Fraction QA checks already passed in both recorded guarded executions; comparator checks record/payload preservation, does not rerun a geometry solver.',
        'raw_differences': 'Every original case delta is retained by exact path with scalar value or complete value hash/byte length; original input EVIDENCE files remain unchanged.',
        'byte_scope': 'Saved result UTF8 encoding and actual known MCP text/tool-result UTF8 encoding; not socket/provider tokens or task benefit.',
        'product_or_QA_imports': 0, 'product_executions': 0, 'model_consumers': 0, 'Blender_sessions': 0,
        'tests_rerun': 0, 'geometry_solves': 0, 'timing_or_token_benefit_claimed': False}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'cases': len(cases), 'checks_total': len(checks),
        'issues': issues, 'output': str(output), 'aggregate_result_delta_bytes': report['aggregate_serialized_result_bytes']['delta']}))
    return 0 if not issues else 1


if __name__ == '__main__':
    raise SystemExit(main())
