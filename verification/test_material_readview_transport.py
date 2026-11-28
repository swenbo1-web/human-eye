"""Material reads require the default typed worker, beyond claimed capabilities."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,Mock,patch

from human_eye_plugin.blender_process import BlenderProcessHost
from human_eye_plugin.forward_deadline import counter_descriptor


class MaterialReadviewTransportTests(unittest.TestCase):
    def host(self,default_worker=True):
        host=BlenderProcessHost.__new__(BlenderProcessHost)
        host._default_worker=default_worker
        host._process=SimpleNamespace(pid=123)
        host.timeout=30.
        host._capabilities={'material_readview_protocol':'static-material-readview-v1',
                            'material_readview_only':True,'process_id':123,
                            'forward_deadline_clock':counter_descriptor()}
        host._request=Mock(return_value={'status':'observed'})
        return host

    def test_custom_or_unidentified_worker_cannot_dispatch_with_valid_claims(self):
        for flag in (False,None):
            with self.subTest(default_worker=flag):
                host=self.host(False)
                if flag is None:del host._default_worker
                calls=(lambda:host.material_readview_header({'object_id':'original'}),
                       lambda:host.observe_material_readview('r1',{},'a'*64,3_000_000_000),
                       host.last_material_readview_audit)
                for call in calls:
                    with self.assertRaisesRegex(ValueError,'fixed owned readonly material-view worker'):
                        call()
                host._request.assert_not_called()

    def test_default_worker_dispatches_all_three_typed_material_reads(self):
        host=self.host();binding={'object_id':'original'}
        self.assertEqual(host.material_readview_header(binding),{'status':'observed'})
        host._request.assert_called_with('material_readview_header',{'binding':binding})
        with patch('human_eye_plugin.blender_process.time.perf_counter_ns',return_value=1_000_000_000):
            host.observe_material_readview('r1',binding,'a'*64,3_000_000_000)
        host._request.assert_called_with('observe_material_readview',{
            'request_id':'r1','binding':binding,'expected_fingerprint':'a'*64,
            'deadline_ns':3_000_000_000},timeout=2.)
        host.last_material_readview_audit()
        host._request.assert_called_with('last_material_readview_audit',{})

    def test_explicit_exact_default_source_path_still_has_no_fixed_worker_privilege(self):
        from human_eye_plugin import blender_process
        worker=Path(blender_process.__file__).resolve().with_name('blender_worker.py')
        capabilities={**self.host()._capabilities,'protocol_version':'1.0'}
        child=MagicMock();child.pid=123;child.poll.return_value=0
        with tempfile.TemporaryDirectory(prefix='material-transport-') as directory:
            blend=Path(directory)/'fixture.blend';blend.write_bytes(b'private transport fixture')
            with patch.object(blender_process.subprocess,'Popen',return_value=child), \
                    patch.object(blender_process.threading,'Thread'), \
                    patch.object(BlenderProcessHost,'_request',return_value=capabilities):
                host=BlenderProcessHost(sys.executable,blend,worker_path=worker)
            try:
                self.assertEqual(host._worker_source,worker)
                self.assertIs(host._default_worker,False)
                host._request=Mock()
                with self.assertRaisesRegex(ValueError,'fixed owned readonly material-view worker'):
                    host.material_readview_header({'object_id':'original'})
                host._request.assert_not_called()
            finally:host.close()


if __name__=='__main__':unittest.main()
