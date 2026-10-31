import copy,json,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import structure_task as t,structure_task_control as c
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
from verification.test_mesh_structure_service import TypedRawHost


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.config=self.root/'config.json';self.config.write_text(json.dumps(dict(schema_version='1.0',enabled=True,
            project_root=str(Path(__file__).resolve().parents[1]),state_file='state.json',audit_file='audit.jsonl',
            structure_task_file='legacy.json',structure_task_control_file='control.json',quad_size=64,max_sessions=4)))
        self.host=TypedRawHost();self.service=LiveSpatialService(self.config,host=self.host);self.server=LiveSpatialMCPServer(self.service)
        p=patch('human_eye_plugin.structure_task_service.counter_descriptor',return_value={'test_clock':True})
        p.start();self.addCleanup(p.stop)

    def begin(self,key='one',**kw):return c.begin(self.config,key,'target',**kw)
    def state(self,ref):return c.Control(self.config).store(ref)._read()
    def call(self,ref=None,request='first',server=None):
        q=dict(mode='mesh_structure',operation='diagnose',request_id=request)
        if ref is not None:q['task_ref']=ref
        r=(server or self.server).handle_jsonrpc_message(dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(
            name='human_eye_scene_observe',arguments=dict(query=q,include_image=False))))['result']
        return json.loads(r['content'][0]['text']),r

    def test_same_service_two_tasks_require_matching_generation(self):
        first=self.begin();a=first['task_ref'];value,r=self.call(a);self.assertFalse(r['isError'])
        self.assertEqual(value['task_budget']['task_id'],a)
        closed=c.close(self.config,a);self.assertTrue(closed['stopped']);self.assertEqual(closed['task_budget']['spent']['queries'],1)
        b=self.begin('two')['task_ref'];self.assertNotEqual(a,b)
        for ref in (None,a,'0'*32):
            value,r=self.call(ref);self.assertTrue(r['isError'])
        self.assertEqual(self.state(b)['spent']['queries'],0);self.assertEqual(self.host.raw_calls,1)
        value,r=self.call(b);self.assertFalse(r['isError']);self.assertEqual(value['task_budget']['task_id'],b)
        self.assertEqual(self.state(a)['spent']['queries'],1);self.assertEqual(self.state(b)['spent']['queries'],1)

    def test_begin_idempotent_and_conflict_never_renews(self):
        a=self.begin();self.call(a['task_ref']);again=self.begin()
        self.assertEqual(a['task_ref'],again['task_ref']);self.assertEqual(a['task_budget']['deadline_ns'],again['task_budget']['deadline_ns'])
        self.assertEqual(again['task_budget']['spent']['queries'],1)
        with self.assertRaisesRegex(ValueError,'registration_id_conflict'):c.begin(self.config,'one','different')
        with self.assertRaisesRegex(ValueError,'requires_close'):self.begin('two')
        c.close(self.config,a['task_ref']);old=self.begin();self.assertEqual(old['phase'],'closed')
        self.assertTrue(old['stopped']);self.assertIsNone(c.Control(self.config).read()['active'])

    def test_status_does_not_claim_owner_or_read_host(self):
        a=self.begin();status=c.status(self.config);self.assertFalse(status['service_claimed'])
        self.assertEqual(status['task_ref'],a['task_ref']);self.assertIsNone(self.state(a['task_ref'])['owner'])
        self.assertEqual(self.host.raw_calls,0);self.assertFalse((self.root/'legacy.json').exists())
        c.close(self.config,a['task_ref']);self.assertEqual(c.status(self.config)['phase'],'idle')

    def test_close_old_generation_cannot_close_new_active(self):
        a=self.begin()['task_ref'];c.close(self.config,a);b=self.begin('two')['task_ref']
        self.assertEqual(c.close(self.config,a)['phase'],'closed');self.assertEqual(c.status(self.config)['task_ref'],b)
        with self.assertRaisesRegex(ValueError,'unknown_task_ref'):c.close(self.config,'0'*32)
        with self.assertRaisesRegex(ValueError,'unknown_task_ref'):c.status(self.config,'0'*32)

    def test_registration_capacity_sixteen_without_dedup_eviction(self):
        ids=[]
        for i in range(16):
            ref=self.begin(str(i))['task_ref'];ids.append(ref);c.close(self.config,ref)
        with self.assertRaisesRegex(ValueError,'capacity_exhausted'):self.begin('seventeen')
        self.assertEqual(self.begin('0')['task_ref'],ids[0]);self.assertEqual(len(c.Control(self.config).read()['registrations']),16)

    def test_restart_cannot_claim_consumed_task_but_can_claim_new_one(self):
        a=self.begin()['task_ref'];self.call(a)
        restarted=LiveSpatialMCPServer(LiveSpatialService(self.config,host=self.host))
        value,r=self.call(a,request='later',server=restarted);self.assertTrue(r['isError']);self.assertIn('service_restart',value['error'])
        c.close(self.config,a);b=self.begin('two')['task_ref']
        value,r=self.call(b,server=restarted);self.assertFalse(r['isError'])

    def test_unknown_inflight_charge_survives_close(self):
        a=self.begin()['task_ref'];store=c.Control(self.config).store(a)
        with store.locked() as value:store.reserve(value,'crash','f'*64,want_images=True)
        c.close(self.config,a);value=self.state(a)
        self.assertEqual(value['inflight'],'crash');self.assertEqual(value['spent']['images'],2);self.assertTrue(value['stopped'])
        b=self.begin('two')['task_ref'];self.assertNotEqual(a,b)
        self.assertEqual(c.status(self.config,a)['outcome_unconfirmed'],True)

    def test_failure_at_each_begin_publication_point_never_auto_retries(self):
        for stage in (1,2,3):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as folder:
                config=Path(folder)/'config.json';config.write_bytes(self.config.read_bytes())
                real=c._atomic_write;writes=[]
                def control_write(*args,**kw):
                    writes.append('control')
                    if (stage==1 and len(writes)==1) or (stage==3 and len(writes)==2):raise OSError('publish failure')
                    return real(*args,**kw)
                with patch.object(c,'_atomic_write',side_effect=control_write),patch.object(t,'_atomic_write',
                        side_effect=OSError('ledger failure') if stage==2 else t._atomic_write):
                    with self.assertRaises(OSError):c.begin(config,'one','target')
                if stage==1:
                    self.assertFalse(c.Control(config).path.exists());continue
                pending=c.begin(config,'one','target');self.assertEqual(pending['phase'],'pending')
                with self.assertRaisesRegex(ValueError,'pending_operator_review'):c.begin(config,'two','target')
                self.assertIsNone(c.Control(config).read()['active'])

    def test_close_publication_failure_leaves_consumption_blocked(self):
        a=self.begin()['task_ref']
        with patch.object(c,'_atomic_write',side_effect=OSError('close publish')):
            with self.assertRaises(OSError):c.close(self.config,a)
        self.assertTrue(self.state(a)['stopped']);value,r=self.call(a)
        self.assertTrue(r['isError']);self.assertEqual(self.host.raw_calls,0)
        c.close(self.config,a);self.assertEqual(c.status(self.config)['phase'],'idle')

    def test_close_ledger_failure_preserves_active_unspent_task(self):
        a=self.begin()['task_ref']
        with patch.object(t,'_atomic_write',side_effect=OSError('stop ledger')):
            with self.assertRaises(OSError):c.close(self.config,a)
        self.assertFalse(self.state(a)['stopped']);self.assertEqual(c.status(self.config)['task_ref'],a)
        value,r=self.call(a);self.assertFalse(r['isError'])

    def test_control_lock_fences_cross_process_close(self):
        a=self.begin()['task_ref'];root=str(Path(__file__).resolve().parents[1])
        code="""import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from human_eye_plugin.structure_task_control import close
config=Path(sys.argv[2]);(config.parent/'close.ready').touch()
close(config,sys.argv[3])
"""
        child=None
        try:
            with c.consumption(self.service,{'task_ref':a},10):
                child=subprocess.Popen([sys.executable,'-I','-B','-c',code,root,str(self.config),a],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                deadline=time.monotonic()+15
                while not (self.root/'close.ready').exists():
                    self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                time.sleep(.15);self.assertIsNone(child.poll());self.assertFalse(self.state(a)['stopped'])
            out,err=child.communicate(timeout=15);self.assertEqual(child.returncode,0,err);self.assertTrue(self.state(a)['stopped'])
        finally:
            if child is not None and child.poll() is None:child.kill();child.communicate(timeout=10)

    def test_corrupt_control_and_generation_fail_before_host(self):
        a=self.begin()['task_ref'];control=c.Control(self.config);original=control.path.read_bytes()
        control.path.write_bytes(original.replace(b'"schema":',b'"schema": "bad", "schema":',1))
        value,r=self.call(a);self.assertTrue(r['isError']);self.assertIn('duplicate',value['error'])
        control.path.write_bytes(original);store=control.store(a);value=store._read();value['task_id']='0'*32;store._write(value)
        value,r=self.call(a);self.assertTrue(r['isError']);self.assertIn('generation_mismatch',value['error'])
        self.assertEqual(self.host.raw_calls,0)

    def test_no_direct_legacy_registration_in_control_mode(self):
        with self.assertRaisesRegex(ValueError,'use_lifecycle_begin'):t.register(self.config,'target')
        with self.assertRaises(ValueError):self.begin('bad id')
        for field in ('task_id','registration_id','limits'):
            with self.assertRaises(ValueError):t.query(dict(mode='mesh_structure',operation='diagnose',request_id='a',**{field:'new'}))

    def test_cli_begin_status_close_and_rejected_exit_code(self):
        root=str(Path(__file__).resolve().parents[1]);bootstrap="import sys;sys.path.insert(0,sys.argv.pop(1));from human_eye_plugin.structure_task_control import main;sys.exit(main())"
        def cli(*args):return subprocess.run([sys.executable,'-I','-B','-c',bootstrap,root,'--config',str(self.config),*args],capture_output=True,text=True)
        one=cli('begin','--registration-id','cli','--object-id','target');self.assertEqual(one.returncode,0,one.stderr)
        ref=json.loads(one.stdout)['task_ref'];self.assertEqual(cli('status').returncode,0)
        self.assertEqual(cli('close','--task-ref',ref).returncode,0)
        bad=cli('close','--task-ref','0'*32);self.assertEqual(bad.returncode,2);self.assertIn('unknown_task_ref',bad.stderr)

    def test_real_processes_cannot_publish_two_active_tasks(self):
        root=str(Path(__file__).resolve().parents[1]);code="""import sys,json,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from human_eye_plugin.structure_task_control import begin
config=Path(sys.argv[2]);name=sys.argv[3];(config.parent/(name+'.ready')).touch()
deadline=time.monotonic()+15
while not (config.parent/'go').exists():
 if time.monotonic()>deadline:raise RuntimeError('barrier timeout')
 time.sleep(.01)
try:result=begin(config,name,'target')
except ValueError as exc:result={'refused':str(exc)}
(config.parent/(name+'.json')).write_text(json.dumps(result))
"""
        children=[subprocess.Popen([sys.executable,'-I','-B','-c',code,root,str(self.config),name],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) for name in ('one','two')]
        try:
            deadline=time.monotonic()+15
            while not all((self.root/(name+'.ready')).exists() for name in ('one','two')):
                self.assertLess(time.monotonic(),deadline);time.sleep(.01)
            (self.root/'go').touch()
            for child in children:
                out,err=child.communicate(timeout=15);self.assertEqual(child.returncode,0,err)
            results=[json.loads((self.root/(name+'.json')).read_text()) for name in ('one','two')]
            self.assertEqual(sum(v.get('phase')=='active' for v in results),1)
            self.assertIn('requires_close',next(v['refused'] for v in results if 'refused' in v))
        finally:
            for child in children:
                if child.poll() is None:child.kill();child.communicate(timeout=10)


if __name__=='__main__':unittest.main()
