"""Stdlib synthetic checks only; no socket/process/product/model/geometry run."""
import importlib.util
import io
import json
from pathlib import Path
import queue
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_consumption_bridge_synthetic', HERE/'bridge.py')
bridge = importlib.util.module_from_spec(spec)
exec(compile((HERE/'bridge.py').read_bytes(), str(HERE/'bridge.py'), 'exec', dont_inherit=True), bridge.__dict__)


class BridgeChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-bridge-', dir=HERE)
        self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.cell = dict(ledger_path=str(self.root/'budget.json'), audit_root=str(self.root/'audit'),
            deadline_perf_ns=time.perf_counter_ns()+60_000_000_000, max_actions=8,
            max_native_rpc=8, max_public_text_bytes=1024*1024, endpoint=dict(host='127.0.0.1',port=1))
        bridge.Budget.create(self.cell); self.budget = bridge.Budget(self.cell)

    def state(self): return json.loads((self.root/'budget.json').read_bytes())

    def test_shared_action_observation_counts_over_threshold_without_failure(self):
        self.cell['action_observation_threshold'] = 2
        self.budget.reserve_action('native:bad_arguments')
        bridge.Budget(self.cell).reserve_action('he:observe')
        self.budget.reserve_action('native:fallback')
        state = self.state(); self.assertEqual(state['actions'], 3); self.assertFalse(state['halted'])
        self.assertTrue(state['events'][-1]['above_observation_threshold'])

    def test_physical_outcome_unknown_halts_without_replay(self):
        token = self.budget.reserve_rpc('synthetic-native')
        self.assertEqual(self.state()['inflight_rpc'], [token])
        self.budget.complete_rpc(token, unknown=True)
        with self.assertRaises(bridge.BudgetError): self.budget.reserve_rpc('replay-forbidden')
        self.assertEqual(self.state()['physical_rpc'], 1)
        self.assertEqual(self.state()['inflight_rpc'], [])
        self.assertIn('unknown_no_replay', self.state()['reason'])

    def test_absolute_deadline_prevents_reservation(self):
        self.cell['deadline_perf_ns'] = time.perf_counter_ns()-1
        with self.assertRaises(bridge.BudgetError): self.budget.reserve_action('late')
        self.assertEqual(self.state()['actions'], 0)

    def test_schema_and_text_charge_one_shared_limit(self):
        self.cell['max_public_text_bytes'] = 20
        self.budget.charge_public(12, 'schema')
        bridge.Budget(self.cell).charge_text(8, 'public-text')
        with self.assertRaises(bridge.BudgetError): self.budget.charge_public(1, 'not-published')
        self.assertEqual(self.state()['public_text_bytes'], 20)
        self.assertEqual(self.state()['events'][-1]['kind'], 'undelivered_public_text')

    def test_exposure_counter_distinguishes_literal_text_and_images(self):
        response = dict(result=dict(content=[dict(type='text',text='汉字'),dict(type='image',data='AAAA',mimeType='image/png')]))
        self.assertEqual(bridge.public_text_bytes(response), 6)
        listing = dict(result=dict(tools=[bridge.NATIVE_TOOL]))
        self.assertEqual(bridge.public_text_bytes(listing), len(bridge.encoded([bridge.NATIVE_TOOL]))-1)

    def test_common_image_cap_retains_failed_allocation_without_decode(self):
        blocks=[dict(type='image',mimeType='image/png',data='AAAA') for _ in range(2)]
        with self.assertRaises(bridge.BudgetError):
            bridge.register_images(self.cell,self.budget,blocks,'synthetic-HE-output')
        self.assertEqual(self.state()['generated_image_blocks'],2)
        self.assertTrue(self.state()['halted'])
        attempts=list((self.root/'audit/image_attempts').glob('*.json'))
        self.assertEqual(len(attempts),1)
        record=json.loads(attempts[0].read_bytes())
        self.assertEqual(record['generated_blocks'],2)
        self.assertEqual(record['rows'],[])
        self.assertIsNone(record['reservation'])
        self.assertIn('image_output_limit',record['error']['message'])

    def test_native_forwards_code_and_preserves_original_response_semantics(self):
        audit = self.root/'native'; audit.mkdir(); native = bridge.Native(self.cell,self.budget,audit)
        response = dict(status='success',result=dict(executed=True,result='synthetic\n'))
        request = dict(jsonrpc='2.0',id=3,method='tools/call',params=dict(name='execute_blender_code',arguments=dict(code="print('synthetic')")))
        with patch.object(native,'execute',return_value=response) as execute:
            public = native.handle(request)
        execute.assert_called_once_with("print('synthetic')")
        self.assertEqual(json.loads(public['result']['content'][0]['text']), response)
        self.assertFalse(public['result']['isError'])
        with self.assertRaises(ValueError): native.handle({**request,'params':dict(name='execute_blender_code',arguments=dict(code='é'*(bridge.MAX_CODE//2+1)))})

    def test_he_proxy_forwards_exact_public_bytes_without_child_start(self):
        relay = bridge.HE.__new__(bridge.HE)
        relay.budget=self.budget; relay.incoming=queue.Queue()
        reply=b'{"jsonrpc":"2.0", "id":7, "result":{"tools":[{"name":"original","description":"unchanged","inputSchema":{}}]}}\n'
        relay.incoming.put(reply)
        relay.process=types.SimpleNamespace(stdin=io.BytesIO())
        request=dict(jsonrpc='2.0',id=7,method='tools/list')
        raw=bridge.encoded(request)
        self.assertEqual(relay.handle_raw(raw,request),reply)
        self.assertEqual(relay.process.stdin.getvalue(),raw)

    def test_main_publishes_calls_above_observation_threshold(self):
        self.cell['action_observation_threshold']=1
        path=self.root/'cell.json'; path.write_bytes(bridge.encoded(self.cell))
        messages=[dict(jsonrpc='2.0',id=1,method='initialize',params=dict(protocolVersion='2024-11-05')),
            dict(jsonrpc='2.0',id=2,method='tools/list'),
            dict(jsonrpc='2.0',id=3,method='tools/call',params=dict(name='execute_blender_code',arguments=dict(code='synthetic-only'))),
            dict(jsonrpc='2.0',id=4,method='tools/call',params=dict(name='execute_blender_code',arguments=dict(code='not-executed')))]
        incoming=types.SimpleNamespace(buffer=io.BytesIO(b''.join(bridge.encoded(m) for m in messages)))
        outgoing=types.SimpleNamespace(buffer=io.BytesIO())
        with patch.object(bridge.sys,'stdin',incoming), patch.object(bridge.sys,'stdout',outgoing), \
             patch.object(bridge.Native,'execute',return_value=dict(status='success',result=dict(executed=True,result='synthetic-only'))) as execute:
            bridge.main(['--kind','native','--cell',str(path)])
        values=[json.loads(line) for line in outgoing.buffer.getvalue().splitlines()]
        self.assertEqual([r['id'] for r in values],[1,2,3,4]); self.assertEqual(execute.call_count,2)
        self.assertTrue((self.root/'audit/bridge_native/004/RX.bin').exists())
        self.assertGreater(json.loads((self.root/'audit/bridge_native/004/METER.json').read_bytes())['published_rx_bytes'],0)
        self.assertEqual(self.state()['actions'],2)


if __name__=='__main__': unittest.main(verbosity=2)
