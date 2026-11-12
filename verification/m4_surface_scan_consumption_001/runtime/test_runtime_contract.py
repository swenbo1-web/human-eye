"""Offline six-slot and final-accounting checks, with every process launch blocked."""
from contextlib import ExitStack, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


driver = load('_scan_contract_driver', HERE/'driver.py')
formal = load('_scan_contract_formal', HERE/'run_formal.py')
transport = load('_scan_contract_transport', HERE/'consumer_transport.py')
SOURCE = 'c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943'
COMMIT = 'c1cb2da32034e056a270384e691a2cde8dddbc0d'


class RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.no_process = patch('subprocess.Popen', side_effect=AssertionError('offline test forbids processes'))
        self.no_process.start()
        self.addCleanup(self.no_process.stop)

    def plan(self):
        sequence = [dict(cell=name,task='T1',round=int(name[1]),group=name[0])
                    for name in ('N1','P1','P2','N2','N3','P3')]
        ready = dict(commit=COMMIT,source_sha256=SOURCE,source_count=138,dependency_python='synthetic')
        return dict(cycle_id=driver.CYCLE,batch=driver.CYCLE,sequence=sequence,
            image_count=0,new_images=0,arms={
                'N':dict(actor_group='N',installation_profile='P',source_sha256=None),
                'P':dict(actor_group='P',installation_profile='P',source_sha256=SOURCE)},
            installations={'P':ready},installation_ready=ready)

    def test_exact_six_slot_order_source_and_denominator(self):
        plan = self.plan()
        go = dict(task=driver.CYCLE,authorized=True,plan_sha256='fixed',max_consumers=6)
        driver.go_contract(go,plan,'fixed')
        for key,value in [('max_consumers',7),('authorized',False),('plan_sha256','changed')]:
            with self.subTest(key=key),self.assertRaises(AssertionError):
                driver.go_contract(dict(go,**{key:value}),plan,'fixed')
        plan['sequence'].pop()
        with self.assertRaises(AssertionError):
            driver.go_contract(go,plan,'fixed')

    def test_final_business_write_and_close_precedes_observed_end(self):
        folder = self.root/'cells/N1'
        folder.mkdir(parents=True)
        row = dict(cell='N1',cell_started_ns=1,finish={'confirmed':True})
        clock = [10]
        events = []
        original = driver.save
        def now():
            clock[0] += 1
            return clock[0]
        def save(path,value):
            clock[0] += 100
            original(path,value)
            events.append((Path(path).name,clock[0]))
        with patch.object(driver,'HERE',self.root),patch.object(driver,'save',side_effect=save), \
                patch.object(driver.time,'perf_counter_ns',side_effect=now):
            result = driver.close_cell_accounting(folder,row,[row],None)
        names = [name for name,tick in events]
        self.assertEqual(names,['RUN_RESULT.json','CELL_FINAL_TIMING.json','CELL_TIMING_PUBLICATION.json'])
        self.assertGreater(result['business_receipts_closed_ns'],events[0][1])
        publication = driver.read(folder/'CELL_TIMING_PUBLICATION.json')
        self.assertGreaterEqual(publication['timing_receipt_publication_closed_ns'],events[1][1])
        self.assertGreater(publication['controller_tail_ns'],0)
        self.assertTrue(result['within_570s'])

    def test_failed_business_publication_does_not_claim_closed_accounting(self):
        folder = self.root/'cells/N1'
        row = dict(cell='N1',cell_started_ns=1,finish={'confirmed':True})
        with patch.object(driver,'HERE',self.root),patch.object(driver,'save',side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError):
                driver.close_cell_accounting(folder,row,[row],None)
        self.assertFalse((folder/'CELL_FINAL_TIMING.json').exists())

    def test_expired_final_accounting_is_explicit(self):
        folder = self.root/'cells/N1'
        row = dict(cell='N1',cell_started_ns=0,finish={'confirmed':True})
        with patch.object(driver,'HERE',self.root),patch.object(driver.time,'perf_counter_ns',return_value=571*10**9):
            result = driver.close_cell_accounting(folder,row,[row],None)
        self.assertFalse(result['within_570s'])

    def test_formal_failure_before_start_still_preserves_six_denominator(self):
        runtime = self.root/'runtime'
        runtime.mkdir()
        def execute(module):
            def run_models():
                raise OSError('synthetic pre-dispatch failure')
            module.run_models = run_models
        spec = types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=execute))
        with patch.object(formal,'HERE',runtime),patch.object(formal,'BATCH',self.root), \
                patch.object(formal.importlib.util,'spec_from_file_location',return_value=spec), \
                patch.object(formal.importlib.util,'module_from_spec',return_value=types.SimpleNamespace()), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(formal.main(),1)
        result = driver.read(self.root/'RUN_RESULT.json')
        self.assertEqual(result['records'],[])
        self.assertEqual(result['started_cells'],0)
        self.assertEqual(result['maximum_consumers'],6)
        self.assertFalse(result['all_planned_dispatched'])
        self.assertEqual(driver.read(self.root/'FORMAL_PROCESS.json')['status'],'terminal')
        self.assertTrue((self.root/'FORMAL_PUBLICATION.json').exists())

    def test_zero_consumer_start_is_failed_record_and_no_final_answer(self):
        cell = 'synthetic_zero_start'
        folder = self.root/'cells'/cell
        folder.mkdir(parents=True)
        driver.save(folder/'cell.json',dict(group='N',endpoint=str(folder/'endpoint.json'),audit_dir=str(folder/'owner')))
        with patch.object(transport,'HERE',self.root),patch.object(transport,'ROOT',self.root), \
                patch.object(transport.subprocess,'Popen',side_effect=OSError('synthetic launch failure')):
            record = transport.consume(dict(cell=cell,group='N',task='T1',round=1),
                {'python':'synthetic'},dict(max_session_seconds=450,image_count=0,new_images=0,inputs={}),b'common prompt')
        self.assertEqual(record['status'],'failed')
        self.assertIsNone(record['thread_id'])
        self.assertIsNone(record['consumer_pid'])
        self.assertIsNone(record['final'])
        self.assertFalse(record['safe_to_continue'])
        self.assertTrue((folder/'CONSUMER.json').exists())

    def test_native_only_arm_has_no_plugin_entry_or_source(self):
        slot,ready,profile = driver.arm_runtime(self.plan(),dict(cell='N1',group='N',task='T1',round=1))
        self.assertEqual(slot['group'],'N')
        self.assertIsNone(self.plan()['arms']['N']['source_sha256'])
        self.assertEqual(ready['source_count'],138)

    def synthetic_driver(self, *, close_confirmed):
        plan = self.plan()
        prompt = self.root/'prompt.txt'
        prompt.write_bytes(b'common prompt')
        snapshot = self.root/'snapshot.json'
        driver.save(snapshot,dict(unit_scale_m=1,objects=[]))
        cli = self.root/'synthetic-cli'
        cli.write_bytes(b'not executable; synthetic hash only')
        plan.update(inputs=dict(prompt='prompt.txt',prompt_sha256=driver.sha(prompt)),
            tasks={'T1':dict(snapshot='snapshot.json',snapshot_sha256=driver.sha(snapshot))},
            consumer_transport_sha256=driver.sha(HERE/'consumer_transport.py'),
            actor_sha256=driver.sha(HERE/'actor.py'),preflight_driver_sha256=driver.sha(HERE/'driver.py'),
            CLI_sha256=driver.sha(cli),dispatch_input_sha256={},external_input_sha256={})
        # The real file integrity checks continue to run against copied bytes.
        (self.root/'runtime').mkdir()
        for name in ('consumer_transport.py','actor.py','driver.py'):
            (self.root/'runtime'/name).write_bytes((HERE/name).read_bytes())
        driver.save(self.root/'PLAN.json',plan)
        driver.save(self.root/'GO.json',dict(task=driver.CYCLE,authorized=True,
            plan_sha256=driver.sha(self.root/'PLAN.json'),max_consumers=6))
        calls = []
        def prepare(slot,output,cell_started_ns):
            output.mkdir(parents=True)
            (output/'owner').mkdir()
            driver.save(output/'owner/INITIAL.json',dict(unit_scale_m=1,objects=[]))
            return output,object(),cell_started_ns
        def consume(slot,install,plan,prompt):
            calls.append(slot['cell'])
            return dict(started_ns=driver.time.perf_counter_ns(),thread_id='synthetic-'+slot['cell'],
                safe_to_continue=True,errors=[],exit_code=0,unexpected_tool_deviations=[],status='completed')
        def finish(folder,process):
            value = dict(confirmed=close_confirmed)
            driver.save(folder/'OWNER_FINISH.json',value)
            return value
        fake = types.SimpleNamespace(EXE=cli,initial_image_metadata=lambda plan: {},consume=consume)
        original_file = driver.__file__
        with patch.object(driver,'HERE',self.root),patch.object(driver,'__file__',str(self.root/'runtime/driver.py')), \
                patch.object(driver,'load',return_value=fake),patch.object(driver,'prepare',side_effect=prepare), \
                patch.object(driver,'finish',side_effect=finish):
            result = driver.run_models()
        self.assertEqual(driver.__file__,original_file)
        return result,calls

    def test_mock_complete_six_cells_have_final_receipts_after_consumer_close(self):
        result,calls = self.synthetic_driver(close_confirmed=True)
        self.assertEqual(calls,['N1','P1','P2','N2','N3','P3'])
        self.assertEqual(len(result['records']),6)
        self.assertIsNone(result['stop'])
        for row in result['records']:
            folder = self.root/'cells'/row['cell']
            self.assertTrue((folder/'CONSUMER.json').exists())
            timing = driver.read(folder/'CELL_FINAL_TIMING.json')
            self.assertGreaterEqual(timing['business_receipts_closed_ns'],row['cell_ended_ns'])
            self.assertTrue(timing['owner_cleanup_confirmed'])
            self.assertTrue(timing['within_570s'])

    def test_mock_unconfirmed_owner_stops_without_replacing_or_dispatching_tail(self):
        result,calls = self.synthetic_driver(close_confirmed=False)
        self.assertEqual(calls,['N1'])
        self.assertEqual(result['started_cells'],1)
        self.assertEqual(result['maximum_consumers'],6)
        self.assertFalse(result['all_planned_dispatched'])
        self.assertEqual(result['stop'],'owner_backend_close_unconfirmed')
        self.assertFalse(driver.read(self.root/'cells/N1/CELL_FINAL_TIMING.json')['owner_cleanup_confirmed'])

    def test_provider_restrictions_distinguish_unavailability_from_numbers(self):
        for message in ('quota exhausted','rate limit','HTTP 503','status: 429'):
            self.assertTrue(driver.provider_unavailable(message))
        self.assertFalse(driver.provider_unavailable('triangle index 503'))


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeContractTests))
    raise SystemExit(not result.wasSuccessful())
