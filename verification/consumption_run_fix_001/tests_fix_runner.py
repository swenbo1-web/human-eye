"""Directed stdlib mocks for the fixed runner; never starts an actual backend.

The parent compiles this exact file and the candidate source bytes in its
controlled test runner. No consumer, product, Blender or actual RPC is used.
"""
import hashlib
from contextlib import ExitStack
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock,patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import runner


def child_fixture(exit_on_kill=True):
    state={'exit':None}
    child=Mock(pid=424242)
    child.poll.side_effect=lambda:state['exit']
    def kill():
        if exit_on_kill:state['exit']=-9
    child.kill.side_effect=kill
    def wait(timeout=None):
        if state['exit'] is None:raise runner.subprocess.TimeoutExpired('synthetic',timeout)
        return state['exit']
    child.wait.side_effect=wait
    return child,state


def rows_from(result,output):
    if isinstance(result,list):return result
    if isinstance(result,dict) and 'cells' in result:return result['cells']
    return json.loads((output/'RESULTS.json').read_bytes())['cells']


def status_of(row):return row.get('status',row.get('state'))


class RunnerFixChecks(unittest.TestCase):
    def test_registered_cleanup_waits_before_loading_exit_receipt(self):
        with tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-receipt-') as name:
            root=Path(name);folder=root/'bridge_native';folder.mkdir()
            cell=dict(arm='N',audit_root=name,ledger_path=str(root/'budget.json'))
            (folder/'STARTED.json').write_text(json.dumps(dict(pid=424242,ledger_path=cell['ledger_path'])),encoding='utf8')
            def exited(pid):
                self.assertEqual(pid,424242)
                (folder/'EXIT.json').write_text(json.dumps(dict(pid=pid,ledger_path=cell['ledger_path'])),encoding='utf8')
                return True
            with patch.object(runner,'process_exited',side_effect=exited) as wait:
                result=runner.registered_tree_cleanup(cell)
            wait.assert_called_once_with(424242);self.assertTrue(result['confirmed'])

    def slot_fixture(self,root):
        pairs=[('T01','N'),('T01','P'),('T02','P'),('T02','N'),
            ('T03','N'),('T03','P'),('T04','P'),('T04','N')]
        cells=[dict(ordinal=i,task_id=task,arm=arm) for i,(task,arm) in enumerate(pairs,1)]
        plan=dict(cells=cells,limits=dict(answer_seconds=180,chain_seconds=600,cleanup_reserve_seconds=60),
            neutral_run_root=str(root/'private'))
        material=dict(tasks=[dict(task_id=task) for task in ('T01','T02','T03','T04')])
        output=root/'output';output.mkdir()
        return plan,material,types.SimpleNamespace(),output

    def assert_eight_order(self,result,output):
        rows=rows_from(result,output)
        self.assertEqual(len(rows),8)
        self.assertEqual([(r['task_id'],r['arm']) for r in rows],
            [('T01','N'),('T01','P'),('T02','P'),('T02','N'),('T03','N'),('T03','P'),('T04','P'),('T04','N')])
        return rows

    def test_taskkill_oserror_and_timeout_fall_back_to_owned_parent(self):
        for error in (OSError('synthetic taskkill missing'),runner.subprocess.TimeoutExpired('synthetic',3)):
            with self.subTest(error=type(error).__name__):
                child,state=child_fixture()
                with patch.object(runner.subprocess,'run',side_effect=error) as command:
                    receipt=runner.kill_tree(child)
                self.assertTrue(child.kill.called);self.assertTrue(child.wait.called)
                self.assertEqual(command.call_args.kwargs['timeout'],3)
                self.assertTrue(receipt['parent_reaped'])
                self.assertFalse(receipt['tree_reaped'])
                self.assertTrue(any(type(error).__name__ in str(row) for row in receipt['errors']))

    def test_unreaped_parent_is_reported_without_successful_tree_claim(self):
        child,state=child_fixture(exit_on_kill=False)
        child.kill.side_effect=OSError('synthetic owned kill failed')
        with patch.object(runner.subprocess,'run',side_effect=OSError('synthetic taskkill failed')):
            receipt=runner.kill_tree(child)
        self.assertTrue(child.kill.called);self.assertTrue(child.wait.called)
        self.assertFalse(receipt['parent_reaped']);self.assertFalse(receipt['tree_reaped'])
        self.assertTrue(receipt['errors'])

    def test_final_and_turn_receive_times_precede_cleanup(self):
        from bridge import Budget
        with tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-time-') as folder:
            root=Path(folder)
            cell=dict(audit_root=folder,ledger_path=str(root/'BUDGET.json'),
                deadline_perf_ns=time.perf_counter_ns()+10_000_000_000,
                max_native_rpc=128,max_public_text_bytes=1048576)
            Budget.create(cell)
            events=[
                dict(type='item.started',item=dict(type='mcp_tool_call',id='synthetic-tool',server='native',tool='execute_blender_code',arguments={'code':'synthetic'})),
                dict(type='item.completed',item=dict(type='agent_message',text='synthetic final')),
                dict(type='turn.completed',usage=dict(input_tokens=2,output_tokens=1)),
            ]
            child=types.SimpleNamespace(pid=424242,stdin=io.BytesIO(),
                stdout=io.BytesIO(b''.join((json.dumps(x)+'\n').encode() for x in events)),stderr=io.BytesIO(),returncode=None)
            child.poll=lambda:child.returncode
            def wait(timeout=None):child.returncode=0;return 0
            child.wait=wait
            def reap(process):
                # A small real stdlib delay makes cleanup distinct from the
                # earlier synthetic answer reception, without a child process.
                time.sleep(.003)
                process.returncode=0
                return dict(parent_reaped=True,tree_reaped=True,errors=[])
            with patch.object(runner,'argv_for',return_value=['synthetic-not-launched']), \
                    patch.object(runner.subprocess,'Popen',return_value=child), \
                    patch.object(runner,'kill_tree',side_effect=reap):
                record=runner.consume({},cell,root,b'synthetic only')
            clocks=record.get('timestamps',record)
            for key in ('consumer_popen_ns','first_public_tool_ns','final_received_ns','turn_completed_ns','process_exit_ns','cleanup_end_ns'):
                self.assertIsInstance(clocks.get(key),int,key)
            self.assertLessEqual(clocks['consumer_popen_ns'],clocks['first_public_tool_ns'])
            self.assertLessEqual(clocks['first_public_tool_ns'],clocks['final_received_ns'])
            self.assertLessEqual(clocks['final_received_ns'],clocks['turn_completed_ns'])
            self.assertLessEqual(clocks['turn_completed_ns'],clocks['process_exit_ns'])
            self.assertLess(clocks['final_received_ns'],clocks['cleanup_end_ns'])
            self.assertLessEqual(clocks['process_exit_ns'],clocks['cleanup_end_ns'])
            self.assertEqual((root/'final.txt').read_text('utf8'),'synthetic final')

    def test_all_slots_registered_before_cell_and_unreaped_stops_future(self):
        with tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-stop-') as folder:
            root=Path(folder);plan,material,native,output=self.slot_fixture(root)
            def unreaped(*args,**kwargs):
                snapshots=[json.loads(p.read_bytes()) for p in output.glob('*.json')]
                self.assertTrue(any(isinstance(s,dict) and len(s.get('cells',[]))==8 for s in snapshots),
                    'the full denominator must be persisted before first cell preparation')
                return dict(status='error',reason='synthetic unconfirmed process tree',safe_to_continue=False)
            with patch.object(runner,'run_cell',side_effect=unreaped) as cell:
                result=runner.execute_slots(plan,{},material,native,output,
                    window_deadline_ns=time.perf_counter_ns()+3600_000_000_000)
            rows=self.assert_eight_order(result,output)
            self.assertEqual(cell.call_count,1)
            self.assertEqual(status_of(rows[0]),'error')
            self.assertTrue(all(status_of(row)=='not_run' for row in rows[1:]))
            self.assertTrue(all(row.get('reason') for row in rows[1:]))

    def test_preparation_exceptions_keep_denominator_and_safe_errors_can_continue(self):
        # Exercise the actual per-cell preparation handler too. All files are
        # non-geometric synthetic bytes; the native launcher is always mocked.
        for stage in ('directory','prompt','asset_copy','host_start'):
            with self.subTest(direct_stage=stage),tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-cell-prep-') as folder:
                root=Path(folder);plan,material,native,output=self.slot_fixture(root)
                base=root/'base';materials=base/'materials';materials.mkdir(parents=True)
                prompt=materials/'synthetic.txt';prompt.write_bytes(b'synthetic question')
                asset=root/'synthetic.asset';asset.write_bytes(b'synthetic asset bytes')
                (materials/'MATERIAL_MANIFEST.json').write_text(json.dumps(dict(neutral_helper=
                    dict(local_path='admin/never-imported.py',sha256='0'*64))),encoding='utf8')
                task=dict(task_id='T01',prompt_path='synthetic.txt',prompt_utf8_sha256=hashlib.sha256(prompt.read_bytes()).hexdigest(),
                    source_asset_path=str(asset),asset_sha256=hashlib.sha256(asset.read_bytes()).hexdigest())
                plan.update(blender='synthetic-never-launched',product_manifest=[])
                start=Mock(side_effect=RuntimeError('synthetic_host_start'))
                native=types.SimpleNamespace(NativeSession=types.SimpleNamespace(start=start))
                target=output/'01';original_mkdir=Path.mkdir;original_read=Path.read_bytes
                def mkdir(path,*args,**kwargs):
                    if path==target:raise OSError('synthetic_directory')
                    return original_mkdir(path,*args,**kwargs)
                def read_bytes(path):
                    if path==prompt:raise OSError('synthetic_prompt')
                    return original_read(path)
                with ExitStack() as stack:
                    stack.enter_context(patch.object(runner,'BASE',base))
                    if stage=='directory':stack.enter_context(patch.object(Path,'mkdir',mkdir))
                    elif stage=='prompt':stack.enter_context(patch.object(Path,'read_bytes',read_bytes))
                    elif stage=='asset_copy':stack.enter_context(patch.object(runner.shutil,'copyfile',side_effect=OSError('synthetic_asset_copy')))
                    record=runner.run_cell(plan,plan['cells'][0],task,native,target,
                        window_deadline_ns=time.perf_counter_ns()+3600_000_000_000)
                self.assertEqual(status_of(record),'error')
                self.assertIn(stage,json.dumps(record))
                if stage=='host_start':
                    start.assert_called_once();self.assertFalse(record['safe_to_continue'])
                else:
                    start.assert_not_called();self.assertTrue(record['safe_to_continue'])
        for stage in ('directory','prompt','asset_copy','host_start'):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-prep-') as folder:
                root=Path(folder);plan,material,native,output=self.slot_fixture(root)
                with patch.object(runner,'run_cell',side_effect=OSError('synthetic_'+stage)) as cell:
                    result=runner.execute_slots(plan,{},material,native,output,
                        window_deadline_ns=time.perf_counter_ns()+3600_000_000_000)
                rows=self.assert_eight_order(result,output)
                self.assertEqual(cell.call_count,1)
                self.assertEqual(status_of(rows[0]),'error')
                self.assertIn(stage,json.dumps(rows[0]))
                self.assertTrue(all(status_of(row)=='not_run' for row in rows[1:]))
        with tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-safe-') as folder:
            root=Path(folder);plan,material,native,output=self.slot_fixture(root)
            outcomes=([dict(status='error',reason='synthetic known pre-start error',safe_to_continue=True)]+
                [dict(status='completed',safe_to_continue=True) for _ in range(7)])
            with patch.object(runner,'run_cell',side_effect=outcomes) as cell:
                result=runner.execute_slots(plan,{},material,native,output,
                    window_deadline_ns=time.perf_counter_ns()+3600_000_000_000)
            rows=self.assert_eight_order(result,output)
            self.assertEqual(cell.call_count,8)
            self.assertEqual(status_of(rows[0]),'error')
            self.assertTrue(all(status_of(row)=='completed' for row in rows[1:]))

    def test_insufficient_or_expired_window_starts_no_cell(self):
        for remaining_ns in (-1,239_000_000_000):
            with self.subTest(remaining_ns=remaining_ns),tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-window-') as folder:
                root=Path(folder);plan,material,native,output=self.slot_fixture(root)
                with patch.object(runner,'run_cell',side_effect=AssertionError('must not start')) as cell:
                    result=runner.execute_slots(plan,{},material,native,output,
                        window_deadline_ns=time.perf_counter_ns()+remaining_ns)
                rows=self.assert_eight_order(result,output)
                cell.assert_not_called()
                self.assertTrue(all(status_of(row)=='not_run' for row in rows))
                self.assertTrue(all(row.get('reason') for row in rows))
        with tempfile.TemporaryDirectory(dir=HERE,prefix='synthetic-cross-window-') as folder:
            root=Path(folder);plan,material,native,output=self.slot_fixture(root)
            clock=[10_000_000_000]
            deadline=clock[0]+300_000_000_000
            def one_cell(*args,**kwargs):
                clock[0]+=70_000_000_000
                return dict(status='completed',safe_to_continue=True)
            with patch.object(runner.time,'perf_counter_ns',side_effect=lambda:clock[0]), \
                    patch.object(runner,'run_cell',side_effect=one_cell) as cell:
                result=runner.execute_slots(plan,{},material,native,output,window_deadline_ns=deadline)
            rows=self.assert_eight_order(result,output)
            self.assertEqual(cell.call_count,1)
            self.assertEqual(status_of(rows[0]),'completed')
            self.assertTrue(all(status_of(row)=='not_run' for row in rows[1:]),
                'later cells must re-check the original window instead of receiving a new window')


if __name__=='__main__':unittest.main(verbosity=2)
