"""Focused fake accounting checks, no product/Blender process imports."""
import importlib.util
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace as NS
import unittest

spec=importlib.util.spec_from_file_location('qa_accounting',Path(__file__).with_name('owned_driver.py'))
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)


class Preflight(unittest.TestCase):
    def test_failed_send_is_attempted_not_delivered(self):
        class Bad:
            def sendall(self,data): raise OSError('injected partial/unknown send')
        metric=q.counts();sock=q.MeterSocket(Bad(),metric)
        with self.assertRaises(OSError):sock.sendall(b'12345')
        self.assertEqual(metric['send_attempted_bytes'],5)
        self.assertEqual(metric['sendall_completed_bytes'],0)

    def test_failed_arm_preserves_time_and_exception(self):
        class Host:
            def close(self): pass
        host=Host()
        def fail(h): h.meter['rpc_attempts']+=1;raise RuntimeError('primary arm failure')
        with tempfile.TemporaryDirectory() as temp:
            result,_,_=q.record_arm(lambda:host,fail,lambda _:None,Path(temp),'test')
            self.assertEqual(result['status'],'failed')
            self.assertIn('primary arm failure',result['error']['message'])
            self.assertEqual(result['transport']['rpc_attempts'],1)
            self.assertGreater(result['whole_arm_before_receipt_ns'],0)

    def test_cleanup_failure_is_separate_and_restores_socket(self):
        class Owner:
            process=NS(poll=lambda:7)
            def close(self): raise ValueError('cleanup failed')
        original=lambda *a,**k:None
        native=NS(socket=NS(create_connection=original))
        main_error={'message':'primary'}
        result=q.finish_owner(Owner(),native)
        self.assertEqual(main_error['message'],'primary')
        self.assertIn('cleanup failed',result['error']['message'])
        self.assertIs(native.socket.create_connection,original)

    def test_unknown_compares_exact_ID_and_reason(self):
        full={'near':{'status':'known','reason':None,'distance_m':2.},'far':{'status':'unknown','reason':'surface_degenerate_triangle'}}
        result=q.compare_facts(full,{'near':full['near']},{'far'})
        self.assertFalse(result['unknown_ID_reason_maps_equal'])
        self.assertEqual(result['missing_unknown_IDs'],{'far':'surface_degenerate_triangle'})
        self.assertEqual(result['candidate_all_IDs']['far']['status'],'not_evaluated_pruned')
        self.assertTrue(result['known_minimum_and_ties_equal'])
        self.assertFalse(result['full_scene_complete'])

    def test_owned_READY_needs_real_owner_PID(self):
        owner=NS(ready={'host':'127.0.0.1','port':48000,'pid':12,'deadline_ns':7,'helper_sha256':'sha'},
                 process=NS(pid=12,poll=lambda:None),config={'deadline_ns':7})
        self.assertEqual(q.owned_address(owner,'sha'),('127.0.0.1',48000))
        owner.ready['pid']=13
        with self.assertRaisesRegex(ValueError,'owned_READY'):q.owned_address(owner,'sha')


if __name__=='__main__':unittest.main()
