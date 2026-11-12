"""Service wiring and bounded measurement diagnostics for OPT1."""
import unittest
from unittest.mock import patch

from human_eye_plugin import surface_scan
from verification.m4_surface_scan_001.tests import test_entry as baseline
from verification.m4_surface_scan_001.tests.test_surface_scan import packet_for, triangle


QUERY = baseline.QUERY


class DependencyEntryTests(unittest.TestCase):
    service = baseline.EntryTests.service
    def test_service_uses_private_host_receipt_after_packet_validation(self):
        service, host, events = self.service(packet_for([triangle('a', 0), triangle('b', 1)]))
        receipt = object()
        captured = []
        host.surface_scan_dependencies = lambda packet: captured.append(packet) or receipt
        original = surface_scan.surface_scan_result
        observed = []
        def reduce(packet, *args, **kwargs):
            observed.append(kwargs.pop('_dependencies'))
            return original(packet, *args, **kwargs)
        with patch.object(surface_scan, 'surface_scan_result', side_effect=reduce):
            result = service.observe('s', query=QUERY, include_image=False)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(captured), 1)
        self.assertIs(observed[0], receipt)
        work = next(fields['task_work'] for event, fields in events if event == 'observe')
        for name in ('measurement_cache_before', 'measurement_cache_after'):
            self.assertEqual(work[name]['max_bytes'], 2*1024*1024)
            self.assertLessEqual(work[name]['accounted_bytes'], work[name]['max_bytes'])
        self.assertEqual(service._read_context.scene_cache.max_measurements, 256)

    def test_packet_fields_cannot_enable_private_dependency_receipt(self):
        packet = packet_for([triangle('a', 0), triangle('b', 1)])
        packet['_surface_dependencies'] = dict(trusted=True)
        service, _, _ = self.service(packet)
        original = surface_scan.surface_scan_result
        observed = []
        def reduce(packet, *args, **kwargs):
            observed.append(kwargs.get('_dependencies'))
            return original(packet, *args, **kwargs)
        with patch.object(surface_scan, 'surface_scan_result', side_effect=reduce):
            self.assertEqual(service.observe('s', query=QUERY, include_image=False)['status'], 'complete')
        self.assertEqual(observed, [None])

    def test_invalid_packet_rejected_before_private_receipt_lookup(self):
        packet = packet_for([])
        packet['binding']['directory_sha256'] = 'invalid'
        service, host, _ = self.service(packet)
        calls = []
        host.surface_scan_dependencies = lambda packet: calls.append(packet)
        with self.assertRaisesRegex(ValueError, 'directory digest mismatch'):
            service.observe('s', query=QUERY, include_image=False)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
