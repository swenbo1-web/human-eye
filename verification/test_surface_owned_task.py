"""Operator task authority, real kernel doubles and finite MCP regressions."""
import copy,io,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from human_eye_plugin import mesh_structure as raw,surface_owned as s
from human_eye_plugin.surface_restore import RestoreController,RestoreJournal
from human_eye_plugin.surface_owned_task import OperatorReferenceTask
from human_eye_plugin.surface_owned_mcp import SurfaceOwnedMCP,GOAL
from verification.test_surface_reference import fixture


class KernelActor:
    def __init__(self,config,registry,ref,target):
        self.config,self.config_sha=s.load_config(config);self.registry=registry;self.ref=ref
        self.state=copy.deepcopy(target);self.physical=0;self.poisoned=False;self.closed=False;self.tamper=None
        self.journal=RestoreJournal(self.config['journal_root'])
        self.controller=RestoreController(registry,journal=self.journal,capture=self.capture,set_vertex=self.setter,approve=lambda _:None)
    def capture(self):
        return raw.prepare_raw(self.state['raw'],{k:self.state['source'][k] for k in ('object_id','object_instance','document_epoch','capture_id')})
    def setter(self,index,point):self.physical+=1;self.state['raw']['vertices'][index]=point[:]
    def inspect(self):return dict(raw_snapshot=self.capture()['raw'],source=self.capture()['source'],quarantined=False,
        journal=RestoreJournal.inspect(self.config['journal_root']),physical_RNA_attempts=self.physical)
    def goal(self,selected,*,event_id,received_ns,approve,cancelled):
        def decision(scope):
            if self.tamper:self.tamper(scope)
            return dict(approved=approve(scope),scope_sha256=s.digest(scope))
        self.controller.approve=decision
        result=self.controller.restore(self.ref,selected,event_id=event_id,received_ns=received_ns,duration_ns=s.LIMITS['duration_ns'])
        return dict(status=result['status'],kernel_result=result,physical_RNA_attempts=result['setter_attempts'],
            worker_physical_RNA_attempts=self.physical,original_file_saved=False)
    def close(self):self.closed=True;self.journal.close()


class OperatorTaskTests(unittest.TestCase):
    def setup_task(self,*,clock=time.perf_counter_ns,attach=True):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name).resolve()
        registry,ref,reference,target,triangles=fixture()
        reference_file=root/'REFERENCE.json';reference_file.write_bytes(s.encoded(dict(raw=reference['raw'],source=reference['source'])))
        scene=root/'test.blend';scene.write_bytes(b'owned-test-only');binary=root/'blender.exe';binary.write_bytes(b'double')
        journal=root/'journal';journal.mkdir()
        config=root/'CONFIG.json';value=dict(schema='owned-surface-operator-config-v1',
            blender_executable=str(binary),blender_sha256='a'*64,scene_file=str(scene),scene_sha256='b'*64,
            reference_file=str(reference_file),reference_sha256=__import__('hashlib').sha256(reference_file.read_bytes()).hexdigest(),
            object_id=target['source']['object_id'],journal_root=str(journal),runtime_source_sha256='c'*64,
            reference_intent=dict(provenance='test',semantic_target='restore approved center',correspondence='same_index_from_owned_copy'))
        config.write_bytes(s.encoded(value));task=OperatorReferenceTask(config,[4],root/'task',clock=clock)
        actor=KernelActor(config,registry,ref,target);self.addCleanup(actor.close)
        if attach:task.attach(actor)
        return task,actor,config,root

    def execute(self,task,actor,selected=None,cancelled=lambda:False):
        return task.execute(actor,[4] if selected is None else selected,event_id='event',client_received_ns=time.perf_counter_ns(),cancelled=cancelled)

    def server(self,task,actor):
        server=SurfaceOwnedMCP(actor,io.StringIO(),io.StringIO(),operator_task=task)
        server.handle(dict(jsonrpc='2.0',id=0,method='initialize',params=dict(protocolVersion='2025-06-18',capabilities={})),time.perf_counter_ns())
        server.emit=lambda _:self.fail('operator task must not elicit a form')
        return server

    def call(self,server,key=1,indices=None):
        response=server.handle(dict(jsonrpc='2.0',id=key,method='tools/call',params=dict(name=GOAL,arguments=dict(indices=[4] if indices is None else indices))),time.perf_counter_ns())
        return json.loads(response['result']['content'][0]['text'])

    def test_single_task_real_kernel_and_readback(self):
        task,actor,_,root=self.setup_task();result=self.execute(task,actor)
        self.assertEqual(result['physical_RNA_attempts'],1);self.assertFalse(result['human_form_verified'])
        self.assertEqual(actor.state['raw']['vertices'][4],[0,0,0]);self.assertTrue((root/'task/RESULT.json').is_file())
        record=json.loads((root/'task/SCOPE.json').read_bytes())
        self.assertEqual(record['scope']['received_ns'],task.received_ns)
        self.assertEqual(record['scope']['deadline_ns'],task.deadline_ns)
        with self.assertRaises(ValueError):self.execute(task,actor)
        self.assertEqual(actor.physical,1)

    def test_mcp_without_form_and_duplicate_receipt_new_id_refused(self):
        task,actor,_,_=self.setup_task();server=self.server(task,actor)
        result=self.call(server);self.assertEqual(result['physical_RNA_attempts'],1)
        self.assertEqual(self.call(server)['status'],'receipt')
        self.assertEqual(self.call(server,key=2)['physical_count'],0);self.assertEqual(actor.physical,1)

    def test_task_does_not_remove_destructive_annotation(self):
        task,actor,_,_=self.setup_task();server=self.server(task,actor)
        response=server.handle(dict(jsonrpc='2.0',id=5,method='tools/list',params={}),time.perf_counter_ns())
        self.assertIs(response['result']['tools'][1]['annotations']['destructiveHint'],True)

    def test_wrong_indices_consume_task_without_dispatch(self):
        task,actor,_,_=self.setup_task()
        with self.assertRaises(ValueError):self.execute(task,actor,selected=[3])
        with self.assertRaises(ValueError):self.execute(task,actor)
        self.assertEqual(actor.physical,0)

    def test_restart_never_restores_authority_completed_or_incomplete(self):
        for completed in (False,True):
            task,actor,config,root=self.setup_task()
            if completed:self.execute(task,actor)
            with self.assertRaises(FileExistsError):OperatorReferenceTask(config,[4],root/'task')

    def test_directory_claim_survives_intake_publication_failure(self):
        task,_,config,root=self.setup_task()
        with patch('human_eye_plugin.surface_owned_task.os.fsync',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):OperatorReferenceTask(config,[4],root/'failed')
        with self.assertRaises(FileExistsError):OperatorReferenceTask(config,[4],root/'failed')

    def test_original_window_includes_initialization(self):
        now=[time.perf_counter_ns()];task,actor,_,_=self.setup_task(clock=lambda:now[0],attach=False)
        now[0]+=s.LIMITS['duration_ns']
        with self.assertRaises(ValueError):task.attach(actor)
        self.assertEqual(actor.physical,0)

    def test_reading_or_waiting_does_not_renew_window(self):
        now=[time.perf_counter_ns()];task,actor,_,_=self.setup_task(clock=lambda:now[0])
        actor.inspect();now[0]+=s.LIMITS['duration_ns']
        with self.assertRaises(ValueError):self.execute(task,actor)
        self.assertEqual(actor.physical,0)

    def test_cancellation_is_terminal_without_dispatch(self):
        task,actor,_,_=self.setup_task()
        with self.assertRaises(ValueError):self.execute(task,actor,cancelled=lambda:True)
        with self.assertRaises(ValueError):self.execute(task,actor)
        self.assertEqual(actor.physical,0)

    def test_config_and_reference_change_refuse(self):
        for name in ('config','reference'):
            task,actor,config,root=self.setup_task()
            if name=='config':config.write_bytes(config.read_bytes()+b' ')
            else:(root/'REFERENCE.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):self.execute(task,actor)
            self.assertEqual(actor.physical,0)

    def test_every_authorization_dimension_bound_before_dispatch(self):
        mutations=[lambda v:v['source'].__setitem__('document_epoch','new'),
            lambda v:v['source'].__setitem__('object_instance','new'),
            lambda v:v['source'].__setitem__('raw_sha256','0'*64),
            lambda v:v['reference_source'].__setitem__('raw_sha256','0'*64),
            lambda v:v['vertex_changes'][0]['target_local'].__setitem__(2,.0001),
            lambda v:v.__setitem__('received_ns',v['received_ns']+1),
            lambda v:v.__setitem__('deadline_ns',v['deadline_ns']+1),
            lambda v:v.__setitem__('maximum_setter_attempts',3),
            lambda v:v.__setitem__('max_displacement_m',.002),
            lambda v:v.__setitem__('event_id','other'),
            lambda v:v.__setitem__('approved',True)]
        for mutation in mutations:
            task,actor,_,_=self.setup_task();actor.tamper=mutation
            with self.assertRaises(ValueError):self.execute(task,actor)
            self.assertEqual(actor.physical,0)

    def test_changed_current_geometry_is_not_reauthorized(self):
        task,actor,_,_=self.setup_task();actor.state['raw']['vertices'][4][2]=-.0006
        with self.assertRaises(ValueError):self.execute(task,actor)
        self.assertEqual(actor.physical,0)

    def test_scope_publication_failure_no_setter(self):
        task,actor,_,_=self.setup_task();publish=task._publish
        def fail(name,value):
            if name=='SCOPE.json':raise OSError('cannot record authorization')
            return publish(name,value)
        task._publish=fail
        with self.assertRaises(OSError):self.execute(task,actor)
        self.assertEqual(actor.physical,0)

    def test_lost_result_after_actual_write_is_unknown_not_zero(self):
        task,actor,_,_=self.setup_task();publish=task._publish
        def fail(name,value):
            if name=='RESULT.json':raise OSError('cannot publish receipt after write')
            return publish(name,value)
        task._publish=fail;server=self.server(task,actor);reply=self.call(server)
        self.assertEqual(actor.physical,1);self.assertEqual(reply['status'],'unknown')
        self.assertIsNone(reply['physical_count']);self.assertTrue(actor.closed)
        self.assertEqual(self.call(server)['status'],'receipt');self.assertEqual(actor.physical,1)

    def test_closed_task_and_attach_twice_refuse(self):
        task,actor,_,_=self.setup_task()
        with self.assertRaises(ValueError):task.attach(actor)
        task.close()
        with self.assertRaises(ValueError):self.execute(task,actor)
        self.assertEqual(actor.physical,0)

    def test_model_cannot_turn_extra_fields_into_operator_authority(self):
        task,actor,_,_=self.setup_task();server=self.server(task,actor)
        for key,field in enumerate(('approved','operator_task','authorize_indices','task_root'),start=1):
            reply=server.handle(dict(jsonrpc='2.0',id=key,method='tools/call',params=dict(name=GOAL,
                arguments=dict(indices=[4],**{field:True}))),time.perf_counter_ns())
            self.assertEqual(json.loads(reply['result']['content'][0]['text'])['physical_count'],0)
        self.assertFalse(task.claimed);self.assertEqual(self.call(server,key=5)['physical_RNA_attempts'],1)

    def test_independent_final_readback_failure_does_not_report_success_or_zero(self):
        task,actor,_,_=self.setup_task();original=actor.inspect
        def changed():
            if actor.physical:actor.state['raw']['vertices'][0][0]+=.01
            return original()
        actor.inspect=changed;reply=self.call(self.server(task,actor))
        self.assertEqual(actor.physical,1);self.assertEqual(reply['status'],'unknown')
        self.assertIsNone(reply['physical_count']);self.assertTrue(actor.closed)


if __name__=='__main__':unittest.main()
