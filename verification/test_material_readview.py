"""Candidate static appearance contracts, without Blender or asset edits.

The generated PNGs exercise transport verification only. They are not render,
visibility, material fidelity, or artwork acceptance evidence.
"""
import base64
import copy
from contextlib import nullcontext
import hashlib
import io
import json
from pathlib import Path
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.forward_deadline import counter_descriptor
from verification.test_blender_native_evidence import fixture
from verification.test_blender_host_contracts import _module as host_module


PROTOCOL = 'static-material-readview-v1'


def binding():
    return {'schema': PROTOCOL, 'source_path': 'readonly-fixture.blend',
            'source_sha256': 'a' * 64, 'target_id': 'fixture-mesh',
            'view': 'head_front', 'center_world_m': [0., 0., .8], 'span_m': .3}


def png_bytes(size=(384, 384)):
    output = io.BytesIO()
    Image.new('RGB', size, (24, 48, 72)).save(output, format='PNG')
    return output.getvalue()


def service_fixture(png=None):
    """Keep real service publication/PNG verification, fake only the host."""
    if png is None:
        png = png_bytes()
    source = binding()
    appearance = {'fingerprint': 'b' * 64}
    source_digest=hashlib.sha256(json.dumps(source,sort_keys=True,
        separators=(',', ':'),ensure_ascii=False,allow_nan=False).encode('utf8')).hexdigest()
    clock=counter_descriptor()
    header = {'protocol': PROTOCOL, 'binding': copy.deepcopy(source),
              'binding_digest': source_digest, 'clock': clock,
              'appearance': copy.deepcopy(appearance), 'read_only': True,
              'execution_authority': False}
    raw = {'protocol': PROTOCOL, 'request_id': 'view-1',
           'binding_digest': source_digest, 'expected_appearance_fingerprint': appearance['fingerprint'],
           'read_only': True, 'execution_authority': False,
           'binding': copy.deepcopy(source), 'appearance': copy.deepcopy(appearance),
           'audit': {'protocol': PROTOCOL, 'request_id': 'view-1', 'clock': clock,
                     'status': 'ready', 'restored': True, 'error': None,
                     'render_attempted': True, 'image_constructed': True,
                     'image_returned_to_transport': True, 'attempts_spent': 1,
                     'constructed_spent': 1, 'returned_to_transport': 1,
                     'read_only': True, 'execution_authority': False,
                     'png_bytes': len(png), 'png_sha256': hashlib.sha256(png).hexdigest()},
           'image': {'image_base64': base64.b64encode(png).decode('ascii'),
                     'source': 'blender_cycles_material_readview', 'view': 'head_front'}}
    service = LiveSpatialService.__new__(LiveSpatialService)
    service.config_path = Path('readview-test-config-do-not-create.json')
    service.config = {'material_readview': {'enabled': True, 'binding': source}}
    service._identity = {'fixture': 'isolated-unit-test'}
    service._identity_rejection = Mock(return_value=None)
    def respond(request_id, source, fingerprint, deadline_ns):
        if type(raw.get('audit')) is dict:
            raw['audit'].update(started_ns=deadline_ns-30_000_000_000+1,
                                finished_ns=deadline_ns-30_000_000_000+2,
                                deadline_ns=deadline_ns)
        return raw
    service.host = NS(transaction=Mock(side_effect=lambda: nullcontext()),
                      material_readview_header=Mock(return_value=header),
                      observe_material_readview=Mock(side_effect=respond))
    return service, raw


class MaterialReadviewServiceTests(unittest.TestCase):
    def observe(self, service, **kwargs):
        with patch('human_eye_plugin.live_service._read_object',
                   return_value=copy.deepcopy(service.config)):
            return service.observe_readview('unit-session', 'view-1', **kwargs)

    def test_conflicting_target_or_source_never_enters_host(self):
        for override, reason in (({'target_id': 'another-instance'}, 'target_conflict'),
                                 ({'expected_source_sha256': 'c' * 64}, 'source_conflict')):
            with self.subTest(override=override):
                service, _ = service_fixture()
                result = self.observe(service, **override)
                self.assertEqual(result['status'], 'unavailable')
                self.assertIn(reason, result['receipt']['error']['message'])
                self.assertEqual(result['receipt']['images_constructed'], 0)
                service.host.transaction.assert_not_called()
                service.host.material_readview_header.assert_not_called()
                service.host.observe_material_readview.assert_not_called()

    def test_real_png_is_publishable_without_claiming_consumer_delivery(self):
        service, raw = service_fixture()
        result = self.observe(service, target_id='fixture-mesh',
                              expected_source_sha256='a' * 64)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['image']['data'], raw['image']['image_base64'])
        self.assertEqual(result['image']['mimeType'], 'image/png')
        self.assertEqual(result['receipt']['images_constructed'], 1)
        self.assertEqual(result['receipt']['publishable_images'], 1)
        self.assertIs(result['receipt']['consumer_delivery_confirmed'], False)
        self.assertIs(result['execution_authority'], False)
        self.assertIsNotNone(result['receipt']['finished_ns'])
        service.host.observe_material_readview.assert_called_once()

    def test_png_postprocessing_failure_keeps_constructed_cost_but_cannot_publish(self):
        good = png_bytes()
        for name, png in (('wrong-size', png_bytes((32, 32))),
                          ('truncated', good[:len(good) // 2])):
            with self.subTest(case=name):
                service, raw = service_fixture(png)
                result = self.observe(service)
                receipt = result['receipt']
                self.assertEqual(result['status'], 'unavailable')
                self.assertIsNone(result['image'])
                self.assertEqual(receipt['publishable_images'], 0)
                self.assertEqual(receipt['images_constructed'], 1)
                self.assertEqual(receipt['host_audit'], raw['audit'])
                self.assertIsNot(receipt['host_audit'], raw['audit'])
                self.assertIsNotNone(receipt['error'])
                self.assertIs(receipt['consumer_delivery_confirmed'], False)

    def test_deadline_expired_after_host_image_cannot_publish_or_refund(self):
        service, _ = service_fixture()
        with patch('human_eye_plugin.live_service._read_object',
                   return_value=copy.deepcopy(service.config)), \
                patch('human_eye_plugin.live_service.time.perf_counter_ns',
                      side_effect=[100, 200, 30_000_000_101, 30_000_000_102]):
            result = service.observe_readview('unit-session', 'view-1')
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('deadline_expired_before_publish', result['receipt']['error']['message'])
        self.assertEqual(result['receipt']['images_constructed'], 1)
        self.assertEqual(result['receipt']['publishable_images'], 0)

    def test_missing_or_misbound_host_receipts_cannot_claim_known_construction(self):
        mutations = {
            'missing-audit': lambda raw: raw.pop('audit'),
            'empty-audit': lambda raw: raw.update(audit={}),
            'missing-restored': lambda raw: raw['audit'].pop('restored'),
            'missing-error': lambda raw: raw['audit'].pop('error'),
            'wrong-protocol-with-constructed': lambda raw: raw.update(protocol='other-protocol'),
            'wrong-request-with-constructed': lambda raw: raw.update(request_id='another-request'),
            'wrong-source': lambda raw: raw['binding'].update(source_sha256='e' * 64),
            'wrong-binding-digest': lambda raw: raw.update(binding_digest='f' * 64),
            'wrong-expected-appearance': lambda raw: raw.update(expected_appearance_fingerprint='e' * 64),
            'wrong-actual-appearance': lambda raw: raw.update(appearance={'fingerprint': 'e' * 64}),
            'wrong-audit-request': lambda raw: raw['audit'].update(request_id='another-request'),
            'wrong-audit-clock': lambda raw: raw['audit'].update(clock={'clock': 'unrelated'}),
            'wrong-audit-deadline': lambda raw: raw['audit'].update(deadline_ns=1),
            'integer-instead-of-bool': lambda raw: raw['audit'].update(image_constructed=1),
            'boolean-instead-of-count': lambda raw: raw['audit'].update(constructed_spent=True),
            'impossible-counts': lambda raw: raw['audit'].update(constructed_spent=2, attempts_spent=1),
            'future-finished-time': lambda raw: raw['audit'].update(finished_ns=(1 << 63)-1),
        }
        for name, mutate in mutations.items():
            with self.subTest(case=name):
                service, _ = service_fixture()
                reply = service.host.observe_material_readview.side_effect
                def malformed(*args, **kwargs):
                    raw = reply(*args, **kwargs)
                    mutate(raw)
                    return raw
                service.host.observe_material_readview.side_effect = malformed
                result = self.observe(service)
                self.assertEqual(result['status'], 'unavailable')
                self.assertIsNone(result['receipt']['images_constructed'])
                self.assertEqual(result['receipt']['construction_status'], 'unknown_invalid_host_receipt')
                self.assertEqual(result['receipt']['publishable_images'], 0)
                self.assertNotIn('host_audit', result['receipt'])
                service.host.observe_material_readview.assert_called_once()

    def test_transport_failure_keeps_construction_unknown_and_does_not_retry(self):
        service, _ = service_fixture()
        service.host.observe_material_readview.side_effect = TimeoutError('reply lost after possible render')
        result = self.observe(service)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['receipt']['images_constructed'])
        self.assertEqual(result['receipt']['construction_status'], 'unknown_until_host_receipt')
        self.assertEqual(result['receipt']['publishable_images'], 0)
        service.host.observe_material_readview.assert_called_once()

    def test_complete_failed_receipt_preserves_constructed_image(self):
        service, raw = service_fixture()
        raw.update(status='unavailable', image=None)
        raw['audit'].update(status='failed', restored=False,
            image_returned_to_transport=False, returned_to_transport=0,
            error={'type': 'EpisodeUncertain', 'message': 'restore failed after construction'})
        result = self.observe(service)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['receipt']['images_constructed'], 1)
        self.assertEqual(result['receipt']['construction_status'], 'validated_host_receipt')
        self.assertEqual(result['receipt']['host_audit']['constructed_spent'], 1)
        self.assertEqual(result['receipt']['publishable_images'], 0)
        service.host.observe_material_readview.assert_called_once()

    def test_complete_pre_render_failure_receipt_can_confirm_zero(self):
        service, raw = service_fixture()
        raw.update(status='unavailable', appearance=None, image=None)
        raw['audit'].update(status='failed', restored=None, render_attempted=False,
            image_constructed=False, image_returned_to_transport=False,
            attempts_spent=0, constructed_spent=0, returned_to_transport=0,
            error={'type': 'EpisodePrewriteRefused', 'message': 'material_readview_source_changed'})
        raw['audit'].pop('png_bytes')
        raw['audit'].pop('png_sha256')
        result = self.observe(service)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['receipt']['images_constructed'], 0)
        self.assertEqual(result['receipt']['construction_status'], 'validated_host_receipt')
        self.assertEqual(result['receipt']['publishable_images'], 0)


class MaterialReadviewHostTests(unittest.TestCase):
    def setUp(self):
        self.host, target, _, _ = fixture()
        self.host.scene.frame_current = 1
        self.source = binding()
        self.appearance = {'fingerprint': 'b' * 64}
        self.renderer = Mock()
        self.module = NS(EpisodePrewriteRefused=host_module.EpisodePrewriteRefused,
                         EpisodeUncertain=host_module.EpisodeUncertain,
                         material_readview_state=Mock(return_value=self.appearance),
                         native_material_readview=self.renderer)
        self.host._material_readview_preflight = Mock(return_value=(target, {'vertices': 4}))
        self.host._readonly_native_module = Mock(return_value=self.module)
        self.host._readonly_clock_module = Mock(return_value=NS(counter_descriptor=counter_descriptor))
        self.host.capture_readonly_evidence = Mock(return_value={
            'capture': {'revision': 'fixture-revision'}, 'native_scene': {'objects': []}})
        self.host._scale = Mock(return_value=1.)
        self.host.material_readview_header(self.source)

    def observe(self, request_id='host-view-1', fingerprint=None):
        return self.host.observe_material_readview(
            request_id, self.source, fingerprint or self.appearance['fingerprint'],
            time.perf_counter_ns() + 5_000_000_000)

    def assert_no_render(self):
        self.renderer.assert_not_called()
        self.assertEqual(self.host._material_readview_store()['attempts'], 0)

    def test_stale_appearance_is_refused_before_render(self):
        result = self.observe(fingerprint='c' * 64)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('stale_appearance', result['audit']['error']['message'])
        self.assertIs(result['audit']['render_attempted'], False)
        self.assertIs(result['audit']['restored'], True)
        self.assert_no_render()

    def test_expired_deadline_cannot_spend_request_or_render_budget(self):
        with self.assertRaisesRegex(host_module.EpisodePrewriteRefused,
                                    'material_readview_deadline_invalid'):
            self.host.observe_material_readview('host-view-1', self.source,
                                               self.appearance['fingerprint'], 0)
        self.assert_no_render()
        self.assertEqual(self.host._material_readview_store()['requests'], {})

    def test_exhausted_render_budget_cannot_start_a_third_render(self):
        store = self.host._material_readview_store()
        store['attempts'] = 2
        result = self.observe()
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('render_budget', result['audit']['error']['message'])
        self.assertIs(result['audit']['render_attempted'], False)
        self.renderer.assert_not_called()
        self.assertEqual(store['attempts'], 2)
        self.assertEqual(store['constructed'], 0)
        self.assertIs(store['active'], False)

    def test_failure_after_construction_is_a_spent_attempt_and_image(self):
        def constructed_then_failed(*args, **kwargs):
            kwargs['constructed_sink'].update(image_constructed=True,
                                              sha256='d' * 64, bytes=123)
            raise RuntimeError('unit_failure_after_png_construction')
        self.renderer.side_effect = constructed_then_failed
        result = self.observe()
        audit = result['audit']
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['image'])
        self.assertIs(audit['render_attempted'], True)
        self.assertIs(audit['image_constructed'], True)
        self.assertEqual(audit['attempts_spent'], 1)
        self.assertEqual(audit['constructed_spent'], 1)
        self.assertEqual(audit['returned_to_transport'], 0)
        self.assertIs(audit['restored'], True)
        self.assertIs(self.host._material_readview_store()['active'], False)

    def observe_through_service(self):
        service, _ = service_fixture()
        service.host = self.host
        with patch('human_eye_plugin.live_service._read_object',
                   return_value=copy.deepcopy(service.config)):
            return service.observe_readview('integrated-unit-session', 'integrated-view-1')

    def test_host_to_service_success_validates_actual_envelope_and_png(self):
        png = png_bytes()
        def render(*args, **kwargs):
            kwargs['constructed_sink'].update(image_constructed=True, bytes=len(png),
                sha256=hashlib.sha256(png).hexdigest())
            return {'image_base64': base64.b64encode(png).decode('ascii'),
                    'source': 'blender_cycles_material_readview', 'view': 'head_front'}
        self.renderer.side_effect = render
        result = self.observe_through_service()
        self.assertEqual(result['status'], 'observed', result['receipt']['error'])
        self.assertEqual(result['receipt']['images_constructed'], 1)
        self.assertEqual(result['receipt']['publishable_images'], 1)
        self.assertEqual(result['receipt']['host_audit'], self.host.last_material_readview_audit())
        self.renderer.assert_called_once()

    def test_host_to_service_construction_failure_keeps_actual_physical_cost(self):
        def fail_after_png(*args, **kwargs):
            kwargs['constructed_sink'].update(image_constructed=True, bytes=17, sha256=None)
            raise RuntimeError('physical output before transport preparation failed')
        self.renderer.side_effect = fail_after_png
        result = self.observe_through_service()
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['receipt']['construction_status'], 'validated_host_receipt')
        self.assertEqual(result['receipt']['images_constructed'], 1)
        self.assertEqual(result['receipt']['publishable_images'], 0)
        self.assertEqual(result['receipt']['host_audit']['attempts_spent'], 1)
        self.renderer.assert_called_once()

    def test_host_to_service_preflight_failure_with_no_appearance_confirms_zero(self):
        target_counts = self.host._material_readview_preflight.return_value
        self.host._material_readview_preflight.side_effect = [target_counts,
            host_module.EpisodePrewriteRefused('material_readview_source_changed')]
        result = self.observe_through_service()
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['receipt']['construction_status'], 'validated_host_receipt')
        self.assertEqual(result['receipt']['images_constructed'], 0)
        self.assertEqual(result['receipt']['host_audit']['attempts_spent'], 0)
        self.assertEqual(result['receipt']['host_audit']['restored'], None)
        self.renderer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
