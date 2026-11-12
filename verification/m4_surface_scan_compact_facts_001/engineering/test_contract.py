"""Offline controller contract checks with all process/network startup blocked."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


HERE = Path(__file__).resolve().parent
with patch.object(subprocess, 'Popen', side_effect=AssertionError('offline import attempted process startup')):
    spec = importlib.util.spec_from_file_location('_compact_engineering_contract_target', HERE / 'run_candidate.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)


def values():
    objects = [{'id': 'a', 'name': '同名'}, {'id': 'b', 'name': '同名'}]
    shared = {'result_kind': 'surface_scan', 'status': 'complete', 'binding': {'source': 'fixed'},
              'coverage': {'objects': 3, 'measured_match': 1},
              'delivery': {'complete': True, 'scope': 'reducer_result_before_service_binding_and_trace'}}
    metadata = {'witness_status': 'measured', 'method': 'exact'}
    full = {**deepcopy(shared), 'trace_id': 'full', 'matches': [
        {'objects': deepcopy(objects), 'distance_m': .001, **metadata,
         'point_a_world': [0., 0., 0.], 'point_b_world': [0., 0., .001]}]}
    compact = {**deepcopy(shared), 'trace_id': 'brief',
               'display_encoding': 'surface-scan-task-table-v1',
               'object_table_scope': 'matched_endpoints_only', 'objects': deepcopy(objects),
               'match_columns': ['object_a', 'object_b', 'object_a_ref', 'object_b_ref', 'distance_m', 'distance_mm'],
               'match_metadata': metadata, 'match_exceptions': [],
               'matches': [['同名', '同名', 0, 1, .001, 1.]]}
    return full, compact


class ContractTests(unittest.TestCase):
    def test_exact_five_slots(self):
        self.assertEqual(runner.SLOTS, (
            ('base_default', 'BASE', None, 71, 112),
            ('base_brief', 'BASE', 'brief', 71, 0),
            ('base_full', 'BASE', 'full', 71, 0),
            ('edit_default', 'EDIT', None, 72, 10),
            ('edit_full', 'EDIT', 'full', 72, 0)))

    def test_ordinary_default_and_full_arguments(self):
        request = runner.request('default', None)
        self.assertEqual(request['method'], 'tools/call')
        self.assertEqual(request['params']['name'], 'human_eye_scene_observe')
        args = request['params']['arguments']
        self.assertNotIn('response_detail', args)
        self.assertEqual(args['query'], {'mode': 'surface_scan', 'threshold_m': .002})
        self.assertEqual(runner.request('full', 'full')['params']['arguments']['response_detail'], 'full')

    def test_duplicate_unicode_names_recover_by_index(self):
        full, compact = values()
        recovered = runner.recover(compact)
        self.assertEqual(recovered[0]['objects'], full['matches'][0]['objects'])
        self.assertEqual(recovered[0]['method'], 'exact')
        self.assertTrue(runner.compare_state([
            {'state': 'default', 'body': compact, 'response_detail': None},
            {'state': 'full', 'body': full, 'response_detail': 'full'}])['passed'])

    def test_invalid_reference_name_and_unit_rejected(self):
        _, value = values()
        for column, invalid in ((2, 9), (0, 'wrong-name'), (5, .001)):
            changed = deepcopy(value)
            changed['matches'][0][column] = invalid
            with self.assertRaises(AssertionError):
                runner.recover(changed)

    def test_signed_zero_and_incorrect_zero_conversion(self):
        _, value = values()
        value['matches'][0][4:6] = [-0., -0.]
        self.assertEqual(runner.bits(runner.recover(value)[0]['distance_m']), runner.bits(-0.))
        value['matches'][0][5] = 0.
        with self.assertRaises(AssertionError):
            runner.recover(value)

    def test_wrong_complete_or_binding_is_rejected(self):
        full, value = values()
        for key, invalid in (('status', 'partial'), ('binding', {'source': 'changed'})):
            changed = deepcopy(value)
            changed[key] = invalid
            with self.assertRaises(AssertionError):
                runner.compare_state([
                    {'state': 'default', 'body': changed, 'response_detail': None},
                    {'state': 'full', 'body': full, 'response_detail': 'full'}])

    def test_metadata_delta_and_lost_metadata(self):
        full, value = values()
        value['match_metadata'] = {'method': 'exact'}
        value['match_exceptions'] = [{'match_index': 0, 'metadata': {'witness_status': 'measured'}}]
        self.assertEqual(runner.recover(value)[0]['witness_status'], 'measured')
        value['match_exceptions'] = []
        with self.assertRaises(KeyError):
            runner.compare_state([
                {'state': 'default', 'body': value, 'response_detail': None},
                {'state': 'full', 'body': full, 'response_detail': 'full'}])

    def test_dropped_or_duplicate_rows_are_rejected(self):
        full, value = values()
        for matches in ([], value['matches'] * 2):
            changed = deepcopy(value)
            changed['matches'] = matches
            with self.assertRaises(AssertionError):
                runner.compare_state([
                    {'state': 'default', 'body': changed, 'response_detail': None},
                    {'state': 'full', 'body': full, 'response_detail': 'full'}])

    def test_build_preparation_is_unchanged_copy(self):
        current = HERE.parent / 'installation/prepare_install.py'
        original = runner.ROOT / 'verification/m4_surface_scan_001_opt1/installation/prepare_install.py'
        self.assertEqual(current.read_bytes(), original.read_bytes())

    def test_original_deadline_boundary(self):
        with patch.object(runner.time, 'perf_counter_ns', return_value=49):
            runner.check_deadline(50, 'synthetic')
        for observed in (50, 51):
            with patch.object(runner.time, 'perf_counter_ns', return_value=observed):
                with self.assertRaisesRegex(TimeoutError, 'original_590s_deadline_synthetic'):
                    runner.check_deadline(50, 'synthetic')

    def test_expired_business_never_dispatches(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='contract-deadline-') as folder:
            output = Path(folder).resolve()
            self.assertTrue(output.is_relative_to(HERE))
            peer = Mock()
            with patch.object(runner.time, 'perf_counter_ns', return_value=51), patch.object(runner, 'memory') as memory:
                row = runner.business(peer, runner.SLOTS[0], output, output / 'audit.jsonl',
                                      None, 'source', 1, 2, 50)
            peer.call.assert_not_called()
            memory.assert_not_called()
            self.assertEqual(row['errors'][0]['type'], 'TimeoutError')

    def test_preparation_failure_retains_five_not_run_without_reuse(self):
        with tempfile.TemporaryDirectory(dir=HERE, prefix='contract-preparation-') as folder:
            temporary = Path(folder).resolve()
            self.assertTrue(temporary.is_relative_to(HERE))
            output = temporary / 'run'
            argv = ['run_candidate.py', '--ready', str(temporary / 'absent-ready.json'),
                    '--commit', 'candidate', '--source-sha256', 'source', '--output', str(output), '--run']
            with patch.object(sys, 'argv', argv), patch.object(runner, 'qualification_binding', side_effect=ValueError('synthetic qualification failure')), patch.object(runner, 'run_candidate') as live:
                self.assertEqual(runner.main(), 1)
            live.assert_not_called()
            planned = json.loads((output / 'PLANNED_ROWS.json').read_bytes())
            self.assertEqual(len(planned), 5)
            self.assertTrue(all(row['status'] == 'not_attempted' for row in planned))
            result = json.loads((output / 'PREPARATION_RESULT.json').read_bytes())
            self.assertEqual(result['execution_counts'], {'attempted': 0, 'completed': 0, 'failed': 0, 'not_attempted': 5})
            original = (output / 'PREPARATION_FAILURE.json').read_bytes()
            with patch.object(sys, 'argv', argv):
                with self.assertRaises(FileExistsError):
                    runner.main()
            self.assertEqual((output / 'PREPARATION_FAILURE.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
