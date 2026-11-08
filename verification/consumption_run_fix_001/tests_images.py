"""Known image-block accounting only; no PNG decode/render/network/process."""
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bridge


class ImageAccountingChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-image-', dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cell = dict(ledger_path=str(self.root/'budget.json'), audit_root=str(self.root/'audit'),
            deadline_perf_ns=time.perf_counter_ns()+60_000_000_000, max_public_text_bytes=1048576,
            native_helper=str(self.root/'NOT_PRESENT.py'), native_helper_sha256='0'*64,
            native_workspace=str(self.root), max_constructed_images=1)
        bridge.Budget.create(self.cell)
        self.budget = bridge.Budget(self.cell)
        # Deliberately not a PNG. Late/halted admission must stop before decode.
        self.blocks = [dict(type='image', mimeType='image/png', data='AAAA')]

    def state(self):
        return json.loads((self.root/'budget.json').read_bytes())

    def attempts(self):
        return [json.loads(path.read_bytes()) for path in (self.root/'audit/image_attempts').glob('*.json')]

    def expire(self):
        value = self.state()
        self.cell['deadline_perf_ns'] = time.perf_counter_ns()-1
        value['deadline_perf_ns'] = self.cell['deadline_perf_ns']
        (self.root/'budget.json').write_bytes(bridge.encoded(value))

    def assert_incurred_not_delivered(self, count=1):
        state = self.state()
        self.assertEqual(state['generated_image_blocks'], count)
        self.assertTrue(state['halted'])
        attempts = self.attempts()
        self.assertEqual(sum(row['generated_blocks'] for row in attempts), count)
        self.assertTrue(all(row['reservation'] is None and row['rows']==[] and row.get('error') for row in attempts))
        self.assertEqual(state['public_text_bytes'], 0)

    def test_late_known_block_is_recorded_before_deadline_refusal(self):
        self.expire()
        with self.assertRaisesRegex(bridge.BudgetError, 'answer_deadline'):
            bridge.register_images(self.cell, self.budget, self.blocks, 'late-synthetic')
        self.assert_incurred_not_delivered()
        self.assertEqual(self.attempts()[0]['error']['message'], 'answer_deadline')

    def test_halted_known_blocks_still_accumulate_without_refund(self):
        self.budget.halt('earlier_failure')
        for label in ('first-known-after-halt','second-known-after-halt'):
            with self.assertRaisesRegex(bridge.BudgetError, 'halted:'):
                bridge.register_images(self.cell, self.budget, self.blocks, label)
        self.assert_incurred_not_delivered(2)
        events = [event for event in self.state()['events'] if event['kind']=='generated_images']
        self.assertEqual([event['count'] for event in events], [1,1])

    def test_ordinary_postprocessing_failure_keeps_construction_credit(self):
        with self.assertRaises(FileNotFoundError):
            bridge.register_images(self.cell, self.budget, self.blocks, 'qualification-fails')
        self.assert_incurred_not_delivered()
        self.assertEqual(self.attempts()[0]['error']['type'], 'FileNotFoundError')

    def test_late_HE_block_is_counted_but_never_published(self):
        now = [time.perf_counter_ns()]
        self.cell['deadline_perf_ns'] = now[0]+60_000_000_000
        value = self.state(); value['deadline_perf_ns'] = self.cell['deadline_perf_ns']
        (self.root/'budget.json').write_bytes(bridge.encoded(value))
        cell_path = self.root/'cell.json'; cell_path.write_bytes(bridge.encoded(self.cell))
        reply = bridge.encoded(dict(jsonrpc='2.0', id=1, result=dict(content=self.blocks, isError=False)))
        class SyntheticHE:
            def __init__(backend, cell, budget, audit): pass
            def handle_raw(backend, raw, request):
                now[0] = self.cell['deadline_perf_ns']+1
                return reply
            def close(backend): pass
        request = dict(jsonrpc='2.0', id=1, method='tools/call',
            params=dict(name='human_eye_scene_observe', arguments={}))
        incoming = types.SimpleNamespace(buffer=io.BytesIO(bridge.encoded(request)))
        outgoing = types.SimpleNamespace(buffer=io.BytesIO())
        with patch.object(bridge, 'HE', SyntheticHE), patch.object(bridge.sys,'stdin',incoming), \
             patch.object(bridge.sys,'stdout',outgoing), patch.object(bridge.time,'perf_counter_ns',side_effect=lambda:now[0]):
            with self.assertRaisesRegex(bridge.BudgetError, 'answer_deadline'):
                bridge.main(['--kind','he','--cell',str(cell_path)])
        self.assertEqual(outgoing.buffer.getvalue(), b'')
        self.assert_incurred_not_delivered()
        folder = self.root/'audit/bridge_he/001'
        self.assertEqual((folder/'GENERATED_RESPONSE.bin').read_bytes(), reply)
        self.assertFalse((folder/'RX.bin').exists())
        meter = json.loads((folder/'METER.json').read_bytes())
        self.assertEqual(meter['generated_rx_bytes'], len(reply))
        self.assertEqual(meter['published_rx_bytes'], 0)

    def test_native_bridge_records_normal_EOF_without_claiming_child_tree(self):
        cell_path=self.root/'cell.json';cell_path.write_bytes(bridge.encoded(self.cell))
        incoming=types.SimpleNamespace(buffer=io.BytesIO())
        outgoing=types.SimpleNamespace(buffer=io.BytesIO())
        with patch.object(bridge.sys,'stdin',incoming),patch.object(bridge.sys,'stdout',outgoing):
            bridge.main(['--kind','native','--cell',str(cell_path)])
        folder=self.root/'audit/bridge_native'
        started=json.loads((folder/'STARTED.json').read_bytes())
        exited=json.loads((folder/'EXIT.json').read_bytes())
        self.assertEqual(started['pid'],exited['pid']);self.assertEqual(started['kind'],'native')
        self.assertEqual(started['ledger_path'],self.cell['ledger_path'])
        self.assertTrue(exited['normal_exit']);self.assertIsNone(exited['he_child_pid'])
        self.assertIsNone(exited['he_child_reaped']);self.assertGreaterEqual(exited['ended_ns'],started['started_ns'])

    def test_HE_close_exception_still_records_unknown_child_cleanup(self):
        cell_path=self.root/'cell.json';cell_path.write_bytes(bridge.encoded(self.cell))
        class SyntheticHE:
            def __init__(backend, cell, budget, audit):
                backend.process=types.SimpleNamespace(pid=314159)
            def close(backend):raise OSError('synthetic owned close failure')
        incoming=types.SimpleNamespace(buffer=io.BytesIO())
        outgoing=types.SimpleNamespace(buffer=io.BytesIO())
        with patch.object(bridge,'HE',SyntheticHE),patch.object(bridge.sys,'stdin',incoming),patch.object(bridge.sys,'stdout',outgoing):
            with self.assertRaisesRegex(OSError,'synthetic owned close failure'):
                bridge.main(['--kind','he','--cell',str(cell_path)])
        exited=json.loads((self.root/'audit/bridge_he/EXIT.json').read_bytes())
        self.assertFalse(exited['normal_exit']);self.assertEqual(exited['he_child_pid'],314159)
        self.assertIsNone(exited['he_child_reaped']);self.assertEqual(exited['close_error']['type'],'OSError')


if __name__=='__main__': unittest.main(verbosity=2)
