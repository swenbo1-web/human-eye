"""Small changed-context oracle controls, without a live runtime or product."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    spec = importlib.util.spec_from_file_location('_recovery_independent_archive', HERE/'archive_oracle.py')
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    archive = HERE/'admin/archive_oracle_fixtures/product_full'
    entries = []
    for index in (1, 2, 3):
        directory = archive/('call_'+str(index).zfill(3))
        directory.mkdir(parents=True)
        path = directory/'SERVICE_RESULT.json'
        path.write_bytes(b'{"fixture":true,"status":"observed"}\n')
        entries.append({'index': index, 'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'started_ns': 100+index*20, 'producer_returned_ns': 110+index*20})
    encode = lambda rows: b''.join(json.dumps(row, sort_keys=True).encode()+b'\n' for row in rows)
    one, two, three = entries
    cases = []

    def check(name, before, after, error=False, expected_reason=None):
        try:
            result = oracle.transition(before, after, 100, 200, error, archive)
            reason = None
        except ValueError as exception:
            result, reason = None, str(exception)
        cases.append({'case': name, 'passed': reason == expected_reason, 'expected_reason': expected_reason,
                      'actual_reason': reason, 'result': result})
        assert reason == expected_reason, name

    check('first_completed_service_record', b'', encode([one]))
    check('pre_service_rejection_no_archive', b'', b'', True)
    check('first_rejection_after_prior_service', encode([one]), encode([one]), True)
    check('consecutive_rejection_keeps_same_bytes', encode([one]), encode([one]), True)
    check('next_valid_reply_after_rejections', encode([one]), encode([one, two]))
    check('service_serial_gap_independent_from_public_serial', encode([one]), encode([one, three]))
    check('service_error_with_completed_archive_record', encode([one]), encode([one, two]), True)
    check('successful_reply_missing_record', encode([one]), encode([one]), False, 'successful_public_reply_missing_service_record')
    changed = copy.deepcopy(one)
    changed['sha256'] = '0'*64
    check('previous_prefix_changed', encode([one]), encode([changed, two]), False, 'previous_archive_prefix_changed')
    check('extra_records_in_one_call', encode([one]), encode([one, two, three]), False, 'multiple_service_records_in_one_public_call')
    changed = copy.deepcopy(two)
    changed['producer_returned_ns'] = 201
    check('cross_call_window', encode([one]), encode([one, changed]), False, 'service_record_outside_original_public_window')
    changed = copy.deepcopy(two)
    changed['path'] = str(HERE/'admin/foreign_slot/product_full/call_002/SERVICE_RESULT.json')
    check('cross_slot_path', encode([one]), encode([one, changed]), False, 'archive_entry_cross_slot_or_noncanonical_path')
    changed = copy.deepcopy(two)
    changed['sha256'] = '0'*64
    check('payload_content_changed', encode([one]), encode([one, changed]), False, 'archive_payload_content_SHA_changed')
    check('incomplete_INDEX_line', encode([one]), encode([one, two])[:-1], False, 'index_complete_line_boundary')
    changed = copy.deepcopy(two)
    changed['index'] = 1
    check('duplicate_service_serial', encode([one]), encode([one, changed]), False, 'service_serial_not_strictly_increasing')
    changed = copy.deepcopy(two)
    changed['index'] = True
    check('boolean_service_serial', encode([one]), encode([one, changed]), False, 'service_serial_positive_integer')
    report = {'schema': 'm5-recovery-independent-archive-interface-v1', 'passed_checked_scope': all(row['passed'] for row in cases),
              'case_count': len(cases), 'cases': cases, 'production_correlator_executed': False,
              'scope': 'Independent synthetic inputs for the new-context byte/serial/path/time/hash oracle. Historical full pure matrices are referenced separately.',
              'source_pins': [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in
                              (Path(__file__), HERE/'archive_oracle.py', HERE/'EXPECTATIONS.json')],
              'new_actual_calls': 0, 'new_models': 0, 'new_rasters': 0}
    path = HERE/'admin/INTERFACE_ARCHIVE_ORACLE.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': report['passed_checked_scope'], 'cases': len(cases),
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
