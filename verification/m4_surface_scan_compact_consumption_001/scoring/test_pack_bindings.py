"""Extra synthetic binding and timing-seal checks for the reused packer."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


HERE = Path(__file__).resolve().parent


def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixture_module = load('_surface_synthetic_pack_fixture',HERE/'check_packager.py')
pack = load('_surface_pack_binding_tests',HERE.parent/'runtime/pack_quality.py')


class PackBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root/'runtime'
        self.runtime.mkdir()

    def run_pack(self):
        with patch.object(pack,'EVAL',self.root),patch.object(pack,'HERE',self.runtime),\
             patch.object(sys,'argv',['test-pack','handoff']),redirect_stdout(io.StringIO()):
            pack.main()
        return self.runtime/'handoff'

    def test_new_timing_receipts_are_sealed_only(self):
        data = fixture_module.fixture(self.root,all_nine=True)
        cell = data['slots'][0]['cell']
        payload = fixture_module.encoded(dict(private_timing_marker='sealed-only-407193',
            group='N',full_cell_wall_ns=123456,usage=dict(input_tokens=87654)))
        for name in ('CELL_FINAL_TIMING.json','CELL_TIMING_PUBLICATION.json'):
            fixture_module.put(self.root,'cells/'+cell+'/'+name,payload)
        output = self.run_pack()
        public = output/'public'
        self.assertFalse(any(b'sealed-only-407193' in p.read_bytes() for p in public.rglob('*') if p.is_file()))
        label = data['mapping']['rows'][0]['anonymous_id']
        with zipfile.ZipFile(output/'private/raw'/(label+'.zip')) as archive:
            for name in ('CELL_FINAL_TIMING.json','CELL_TIMING_PUBLICATION.json'):
                self.assertEqual(archive.read(name),payload)

    def test_inconsistent_final_is_preserved_without_repair(self):
        data = fixture_module.fixture(self.root,all_nine=True)
        cell = data['slots'][0]['cell']
        raw = b'Original mismatched final bytes\n'
        (self.root/'cells'/cell/'PUBLIC_FINAL.txt').write_bytes(raw)
        output = self.run_pack()
        index = json.loads((output/'public/INDEX.json').read_bytes())
        label = data['mapping']['rows'][0]['anonymous_id']
        row = next(row for row in index['answers'] if row['anonymous_id']==label)
        self.assertEqual(row['answer_state'],'inconsistent_final_binding')
        self.assertEqual((output/'public'/label/'answer.txt').read_bytes(),raw)
        self.assertTrue((output/'public'/label/'consumer_record_text_unconfirmed.txt').exists())

    def test_extra_tail_result_cannot_be_ignored(self):
        data = fixture_module.fixture(self.root,all_nine=True)
        data['run']['records'].append(data['run']['records'][-1])
        (self.root/'RUN_RESULT.json').write_bytes(fixture_module.encoded(data['run']))
        with self.assertRaises(AssertionError):
            self.run_pack()

    def test_wrong_last_task_binding_is_rejected(self):
        data = fixture_module.fixture(self.root,all_nine=True)
        data['run']['records'][-1]['task']='different_task'
        (self.root/'RUN_RESULT.json').write_bytes(fixture_module.encoded(data['run']))
        with self.assertRaisesRegex(AssertionError,'planned prefix'):
            self.run_pack()

    def test_wrong_consumer_binding_is_rejected(self):
        data = fixture_module.fixture(self.root,all_nine=True)
        path = self.root/'cells'/data['slots'][0]['cell']/'CONSUMER.json'
        consumer = json.loads(path.read_bytes())
        consumer['round'] += 1
        path.write_bytes(fixture_module.encoded(consumer))
        with self.assertRaisesRegex(AssertionError,'consumer slot binding'):
            self.run_pack()

    def test_orphan_material_cannot_be_labelled_not_run(self):
        data = fixture_module.fixture(self.root,zero_entered=True)
        fixture_module.put(self.root,'cells/'+data['slots'][0]['cell']+'/unrecorded.txt',b'preserved partial')
        with self.assertRaisesRegex(AssertionError,'unrecorded material'):
            self.run_pack()

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate JSON key'):
            pack.decode(b'{"records":[],"records":[{}]}')

    def test_post_completion_controller_error_remains_failed(self):
        data = fixture_module.fixture(self.root,all_nine=True)
        row = data['run']['records'][0]
        message = 'original_full_cell_deadline_exceeded at C:/actual/path after publication'
        row['errors'] = [dict(type='TimeoutError',stage='final_business_accounting',
            message=message,traceback='administrative traceback')]
        row['finish'] = dict(confirmed=True)
        (self.root/'RUN_RESULT.json').write_bytes(fixture_module.encoded(data['run']))
        output = self.run_pack()
        index = json.loads((output/'public/INDEX.json').read_bytes())
        label = data['mapping']['rows'][0]['anonymous_id']
        answer = next(answer for answer in index['answers'] if answer['anonymous_id']==label)
        self.assertEqual(answer['execution_record_state'],'completed')
        self.assertEqual(answer['cell_execution_state'],'failed')
        self.assertEqual(answer['cell_errors'],[dict(type='TimeoutError',
            stage='final_business_accounting',message=message)])

    def test_unconfirmed_cleanup_stays_unknown(self):
        data = fixture_module.fixture(self.root,all_nine=True)
        data['run']['records'][0]['finish'] = dict(confirmed=None)
        (self.root/'RUN_RESULT.json').write_bytes(fixture_module.encoded(data['run']))
        output = self.run_pack()
        index = json.loads((output/'public/INDEX.json').read_bytes())
        label = data['mapping']['rows'][0]['anonymous_id']
        answer = next(answer for answer in index['answers'] if answer['anonymous_id']==label)
        self.assertEqual(answer['cell_execution_state'],'unknown')

    def test_actual_consumer_failure_message_is_preserved(self):
        data = fixture_module.fixture(self.root,consumer_failure=True)
        output = self.run_pack()
        index = json.loads((output/'public/INDEX.json').read_bytes())
        label = data['mapping']['rows'][0]['anonymous_id']
        answer = next(answer for answer in index['answers'] if answer['anonymous_id']==label)
        self.assertEqual(answer['cell_execution_state'],'failed')
        self.assertEqual(answer['consumer_execution_errors'],[dict(type='SyntheticPopenError',message='synthetic launch failure')])

    def test_pre_started_controller_failure_preserves_nine_not_run(self):
        data = fixture_module.fixture(self.root,zero_entered=True)
        (self.root/'STARTED.json').unlink()
        fixture_module.put(self.root,'FORMAL_PROCESS.json',fixture_module.encoded(dict(
            started_ns=5,ended_ns=80,status='terminal',started_cells=0,
            stop=data['run']['stop'],controller_error=dict(type='ValueError',
                message='frozen input hash changed',traceback='administrative stack'))))
        output = self.run_pack()
        index = json.loads((output/'public/INDEX.json').read_bytes())
        self.assertEqual(len(index['answers']),9)
        self.assertTrue(all(row['cell_execution_state']=='not_run' for row in index['answers']))
        self.assertEqual(index['controller_execution']['controller_error'],
                         dict(type='ValueError',message='frozen input hash changed'))
        self.assertNotIn('started_ns',index['controller_execution'])
        self.assertFalse((output/'private/control/STARTED.json').exists())

    def test_pre_started_path_rejects_missing_terminal_or_wrong_GO(self):
        data = fixture_module.fixture(self.root,zero_entered=True)
        control = dict(data['controls'])
        control.pop('STARTED.json')
        with self.assertRaises(KeyError):
            pack.validate_pre_started_failure(data['run'],control)
        control['FORMAL_PROCESS.json'] = fixture_module.encoded(dict(started_ns=5,ended_ns=80,
            status='terminal',started_cells=0,stop=data['run']['stop'],
            controller_error=dict(type='ValueError',message='failure')))
        control['GO.json'] = fixture_module.encoded(dict(task='wrong',authorized=True,
            max_consumers=9,plan_sha256=fixture_module.sha(control['PLAN.json'])))
        with self.assertRaisesRegex(AssertionError,'GO binding'):
            pack.validate_pre_started_failure(data['run'],control)


if __name__ == '__main__':
    unittest.main(verbosity=2)
