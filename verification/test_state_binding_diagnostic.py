"""Binding diagnostics preserve hard refusal, bytes and unfinished journals."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.live_service import LiveSpatialService, StateBindingError


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class NoHost:
    def __init__(self):
        self.captures = self.mutations = 0

    def capture_scene(self):
        self.captures += 1
        raise AssertionError('Binding refusal must precede host capture')

    def apply_transform(self, *args, **kwargs):
        self.mutations += 1
        raise AssertionError('Binding refusal must precede host mutation')


class StateBindingDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.base = self.project/'.human-eye'
        self.base.mkdir()
        self.config_path = self.base/'connector.json'
        self.state_path = self.base/'state.json'
        self.config = {'schema_version': '1.0', 'project_root': str(Path(__file__).resolve().parents[1]),
            'state_file': 'state.json', 'audit_file': 'events.jsonl', 'enabled': True,
            'quad_size': 64, 'max_sessions': 4}
        self.write_config(self.config)
        self.host = NoHost()
        self.service = LiveSpatialService(self.config_path, host=self.host)
        self.runtime = self.service._runtime().export_state()
        self.action = {'focal_id': 'part', 'reference_id': 'base', 'translation': [0, 0, .001]}

    def write_config(self, config):
        self.config_path.write_text(json.dumps(config), encoding='utf-8')

    def write_state(self, binding='f'*64, *, inflight=None):
        self.state = {'schema_version': '1.0', 'config_fingerprint': binding,
            'runtime': copy.deepcopy(self.runtime), 'inflight': copy.deepcopy(inflight),
            'operator_payload': {'keep_exactly': '保留全部日志和既有观测', 'values': [None, False, 0, -0.0]}}
        self.state_raw = (' \n' + json.dumps(self.state, ensure_ascii=False, indent=3) + '\n\t').encode('utf-8')
        self.state_path.write_bytes(self.state_raw)
        return self.state_raw

    def manifest(self, *, folder='a'*32, root=None, **changes):
        root = self.base if root is None else root
        directory = root/'setup-backups'/folder
        directory.mkdir(parents=True)
        old_raw = copy.deepcopy(self.state)
        old_raw['config_fingerprint'] = fingerprint(self.config)
        old_hash = hashlib.sha256(json.dumps(old_raw).encode()).hexdigest()
        new_hash = '1'*64
        value = {'schema_version': '1.0', 'agent': 'codex', 'status': 'in_progress',
            'phase': 'fenced', 'recovery_required': True,
            'state_commit_order': 'fence_first_final_binding_last',
            'transaction_fence_fingerprint': self.state['config_fingerprint'],
            'fenced_state_sha256': hashlib.sha256(self.state_raw).hexdigest(),
            'old_state_sha256': old_hash, 'new_state_sha256': new_hash,
            'files': [{'path': '.human-eye/connector.json', 'existed': True,
                       'before_sha256': '2'*64, 'after_sha256': '3'*64},
                      {'path': '.human-eye/state.json', 'existed': True,
                       'before_sha256': old_hash, 'after_sha256': new_hash}]}
        value.update(changes)
        path = directory/'manifest.json'
        path.write_text(json.dumps(value), encoding='utf-8')
        return path, value

    def refusal(self, *, service=None, operation='status', classification='state_binding_cause_unconfirmed'):
        service = service or self.service
        before = self.state_path.read_bytes()
        with self.assertRaises(StateBindingError) as caught:
            if operation == 'status':
                service.status()
            elif operation == 'observe':
                service.observe('s')
            else:
                getattr(service, operation)('s', self.action)
        error = caught.exception
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.code, 'state_configuration_binding_mismatch')
        self.assertEqual(error.reason_codes, [error.code, classification])
        self.assertEqual(error.recovery['classification'], classification)
        self.assertIs(error.recovery['preserve_state_and_journal'], True)
        self.assertIs(error.recovery['preserve_activation_backups'], True)
        self.assertIs(error.recovery['restart_alone_is_sufficient'], False)
        self.assertIs(error.recovery['execution_authority'], False)
        self.assertNotIn('reset connector state', str(error))
        self.assertNotIn('reinitialize', str(error))
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertEqual(self.host.captures, 0)
        self.assertEqual(self.host.mutations, 0)
        return error

    def test_unknown_binding_is_not_called_a_fence_or_restart_fix(self):
        self.write_state()
        error = self.refusal()
        self.assertEqual(error.recovery['action'], 'review_configuration_state_and_activation_records')
        self.assertEqual(error.recovery['disk_configuration'], 'matches_loaded_configuration')
        self.assertNotIn('matching_activation_record', error.recovery)

    def test_all_four_entry_operations_refuse_before_runtime_import_or_host(self):
        self.write_state(inflight={'operation_id': 'uncertain-op', 'session_id': 's', 'started': 1.0})
        with patch.object(self.service, '_runtime', side_effect=AssertionError('Runtime import must not occur')):
            for operation in ('status', 'observe', 'preview_action', 'transform'):
                with self.subTest(operation=operation):
                    self.refusal(operation=operation)
        self.assertEqual(json.loads(self.state_path.read_bytes())['inflight']['operation_id'], 'uncertain-op')

    def test_old_cached_process_is_identified_only_when_disk_matches_persisted_binding(self):
        current = {**self.config, 'quad_size': 128}
        self.write_config(current)
        self.write_state(fingerprint(current))
        error = self.refusal(classification='stale_configuration_snapshot')
        self.assertEqual(error.recovery['action'], 'restart_and_revalidate_current_configuration')
        self.assertEqual(error.recovery['disk_configuration'], 'matches_persisted_state')
        fresh = LiveSpatialService(self.config_path, host=self.host)
        self.assertFalse(fresh.status()['quarantined'])
        self.assertEqual(self.state_path.read_bytes(), self.state_raw)
        self.assertEqual(self.host.captures, 0)

    def test_stale_guidance_does_not_clear_pending_uncertainty_after_restart(self):
        current = {**self.config, 'quad_size': 128}
        self.write_config(current)
        self.write_state(fingerprint(current), inflight={
            'operation_id': 'uncertain-op', 'session_id': 's', 'started': 1.0})
        self.refusal(classification='stale_configuration_snapshot')
        fresh = LiveSpatialService(self.config_path, host=self.host)
        self.assertTrue(fresh.status()['inflight_operation'])
        self.assertEqual(self.state_path.read_bytes(), self.state_raw)
        self.assertEqual(self.host.captures, 0)

    def test_fresh_process_with_changed_config_and_old_state_is_not_diagnosed_stale(self):
        self.write_state(fingerprint(self.config))
        current = {**self.config, 'quad_size': 128}
        self.write_config(current)
        self.refusal(service=LiveSpatialService(self.config_path, host=self.host))

    def test_known_uncommitted_fence_matches_paths_bytes_and_explicit_record(self):
        self.write_state(inflight={'operation_id': 'keep-op', 'session_id': 's', 'started': 1.0})
        path, _ = self.manifest()
        manifest_raw = path.read_bytes()
        error = self.refusal(classification='known_uncommitted_activation_fence')
        self.assertEqual(error.recovery['action'], 'operator_recovery_from_activation_records')
        self.assertEqual(error.recovery['matching_activation_record']['manifest_path'], str(path.resolve()))
        self.assertEqual(path.read_bytes(), manifest_raw)

    def test_prepared_record_already_fenced_is_not_misclassified_as_restart_only(self):
        self.write_state()
        self.manifest(status='prepared', phase='backups_prepared')
        self.refusal(classification='known_uncommitted_activation_fence')

    def test_incomplete_rollback_record_requires_manual_recovery(self):
        self.write_state()
        self.manifest(status='rollback_incomplete', phase='recovery_required')
        self.refusal(classification='known_uncommitted_activation_fence')

    def test_committed_or_rolled_back_record_does_not_prove_an_active_fence(self):
        self.write_state()
        path, original = self.manifest()
        for status, phase in (('applied', 'committed'), ('rolled_back', 'rolled_back')):
            with self.subTest(status=status):
                path.write_text(json.dumps({**original, 'status': status, 'phase': phase,
                                            'recovery_required': False}), encoding='utf-8')
                self.refusal()

    def test_matching_fingerprint_without_matching_full_state_bytes_is_unknown(self):
        self.write_state()
        self.manifest(fenced_state_sha256='0'*64)
        self.refusal()

    def test_manifest_for_another_state_or_config_is_unknown(self):
        self.write_state()
        path, original = self.manifest()
        for index in (0, 1):
            with self.subTest(index=index):
                changed = copy.deepcopy(original)
                changed['files'][index]['path'] = '.human-eye/other.json'
                path.write_text(json.dumps(changed), encoding='utf-8')
                self.refusal()

    def test_manifest_path_escape_duplicate_and_invalid_hashes_are_unknown(self):
        self.write_state()
        path, original = self.manifest()
        variants = []
        escaped = copy.deepcopy(original); escaped['files'][0]['path'] = '../escape.json'; variants.append(escaped)
        duplicate = copy.deepcopy(original); duplicate['files'].append(duplicate['files'][1]); variants.append(duplicate)
        bad_hash = copy.deepcopy(original); bad_hash['old_state_sha256'] = 'not-a-sha'; variants.append(bad_hash)
        bad_binding = copy.deepcopy(original); bad_binding['files'][1]['after_sha256'] = '0'*64; variants.append(bad_binding)
        for value in variants:
            with self.subTest(value=value):
                path.write_text(json.dumps(value), encoding='utf-8')
                self.refusal()

    def test_unknown_hex_is_not_inferred_from_fingerprint_shape(self):
        for binding in ('0'*64, 'a'*64, 'not-a-hash', None, ['a'*64]):
            with self.subTest(binding=binding):
                self.write_state(binding)
                self.refusal()

    def test_manifest_discovery_is_only_next_to_actual_connector_not_project_root(self):
        self.write_state()
        elsewhere = self.project/'other-project'
        self.manifest(root=elsewhere)
        self.service.root = elsewhere
        self.refusal()

    def test_oversized_manifest_and_ambiguous_json_remain_unknown(self):
        self.write_state()
        path, original = self.manifest()
        base = json.dumps(original)
        variants = [base[:-1] + ',"padding":"' + 'x'*(256*1024) + '"}',
                    base[:-1] + ',"status":"in_progress"}',
                    base[:-1] + ',"unknown":NaN}', base[:-1] + ',"unknown":1e999}', 'broken']
        for text in variants:
            with self.subTest(length=len(text)):
                path.write_text(text, encoding='utf-8')
                self.refusal()

    def test_manifest_directory_count_has_a_fixed_bound(self):
        self.write_state()
        self.manifest(folder='valid')
        backups = self.base/'setup-backups'
        for i in range(63):
            (backups/('empty-' + str(i))).mkdir()
        self.refusal(classification='known_uncommitted_activation_fence')
        (backups/'one-too-many').mkdir()
        self.refusal()

    def test_unreadable_or_invalid_current_disk_config_cannot_fake_stale_cause(self):
        invalid = {**self.config, 'schema_version': 'unsupported'}
        self.write_state(fingerprint(invalid))
        self.write_config(invalid)
        error = self.refusal()
        self.assertEqual(error.recovery['disk_configuration'], 'unavailable')
        self.config_path.unlink()
        self.refusal()

    def test_current_config_for_another_state_path_does_not_suggest_restart_resolution(self):
        different = {**self.config, 'state_file': 'another-state.json'}
        self.write_config(different)
        self.write_state(fingerprint(different))
        self.refusal()

    def test_diagnostic_lookup_failure_cannot_replace_binding_ValueError(self):
        self.write_state()
        with patch.object(self.service, '_matching_activation_fence', side_effect=RuntimeError('lookup failed')):
            self.refusal()

    def test_structured_fields_are_detached_and_keep_ValueError_compatibility(self):
        self.write_state()
        error = self.refusal()
        fields = error.to_error_fields()
        fields['reason_codes'].append('changed-output')
        fields['recovery']['action'] = 'changed-output'
        self.assertNotIn('changed-output', error.to_error_fields()['reason_codes'])
        self.assertNotEqual(error.to_error_fields()['recovery']['action'], 'changed-output')
        self.assertIsInstance(error, ValueError)
        self.assertTrue(str(error).startswith('[' + error.code + ']'))

    def test_matching_binding_still_preserves_existing_corrupt_runtime_refusal(self):
        self.write_state(fingerprint(self.config))
        self.state['runtime'] = None
        raw = json.dumps(self.state).encode()
        self.state_path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'Corrupt persisted live runtime'):
            self.service.status()
        self.assertEqual(self.state_path.read_bytes(), raw)
        self.assertEqual(self.host.captures, 0)


if __name__ == '__main__':
    unittest.main()
