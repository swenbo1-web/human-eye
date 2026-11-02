"""Bounded product-entry doubles verify launch trust, source and close gates.

These tests never grant support to a real asset. Production packet replay is
checked independently from the fake stdio launch; native captures are separate.
"""
import contextlib,copy,hashlib,io,json,os,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from human_eye_plugin import small_skin_source_process as process
from verification.test_small_skin_source import packet as fixture,rehash,binding
from verification.test_reader_startup_cleanup import Process,LaunchFailure

SOURCE='a'*64


def stable_selection(p,ids=(0,)):
    return dict(schema='surface-deformation-selection-v1',source_ref=dict(scene_sha256=p['identity']['scene_sha256'],
        rig_object_id='blender:'+process.r.digest(['',p['inputs']['rig']['name']]),mesh_object_id='blender:'+process.r.digest(['',p['inputs']['mesh']['name']]),
        frame=copy.deepcopy(p['inputs']['frame'])),triangle_indices=list(ids))


class SmallSourceTransportTests(unittest.TestCase):
    @contextlib.contextmanager
    def setup_actor(self,*,ready_change=None,start_failure=None):
        with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
            root=Path(folder).resolve();binary=root/'fake-blender.exe';scene=root/'scene.blend';binary.write_bytes(b'binary');scene.write_bytes(b'scene')
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            profile=dict(schema='small-skin-source-operator-profile-v1',blender_executable=str(binary),blender_sha256=sha(binary),
                scene_file=str(scene),scene_sha256=sha(scene),mesh_name='Mesh',rig_name='Rig',expected_frame=dict(number=1,subframe=0.),
                unit_scale_m=1.,runtime_source_sha256=SOURCE)
            path=root/'PROFILE.json';path.write_text(json.dumps(profile));child=Process();child.pid=1234;threads=[]
            stack.enter_context(patch.object(process,'check_source_drift',return_value=dict(compatible=True)))
            stack.enter_context(patch.object(process,'runtime_identity',return_value=dict(source_sha256=SOURCE)))
            stack.enter_context(patch.object(process.subprocess,'Popen',return_value=child))
            def thread(**kw):
                index=len(threads)+1;threads.append(index)
                def start():
                    if start_failure==index:raise LaunchFailure('reader start failed')
                return SimpleNamespace(start=start)
            stack.enter_context(patch.object(process.threading,'Thread',side_effect=thread))
            def ready(actor):
                sample=fixture();roles={o['name']:o for o in sample['inputs']['closure']}
                value=dict(kind='ready',protocol=process.core.PROTOCOL,process_id=child.pid,scene_sha256=profile['scene_sha256'],
                    profile_sha256=hashlib.sha256(actor.profile_bytes).hexdigest(),module_sha256=actor.module_sha,math_sha256=actor.math_sha,
                    worker_sha256=actor.worker_sha,binary_sha256=profile['blender_sha256'],runtime_source_sha256=SOURCE,
                    document_epoch='a'*32,frame=copy.deepcopy(profile['expected_frame']),unit_scale_m=1.,deadline_ns=actor.deadline_ns,
                    mesh_identity=copy.deepcopy(roles['Mesh']['identity']),mesh_data_identity=copy.deepcopy(roles['Mesh']['data_identity']),
                    rig_identity=copy.deepcopy(roles['Rig']['identity']),rig_data_identity=copy.deepcopy(roles['Rig']['data_identity']),
                    read_only=True,geometry_setters=0,saves_file=False,sets_frame=False,generic_exec=False,max_requests=16,byte_limit=process.r.MAX_BYTES)
                if ready_change:ready_change(value)
                return value
            handshake=stack.enter_context(patch.object(process.SmallSkinSourceProcess,'_next',autospec=True,side_effect=ready))
            yield SimpleNamespace(path=path,root=root,profile=profile,child=child,threads=threads,handshake=handshake,
                create=lambda:process.SmallSkinSourceProcess(path))

    def captured(self,actor):
        p=fixture();p['identity']={key:getattr(actor.bindings,key) for key in process.core.PIN_FIELDS}
        p['identity'].update(document_epoch=actor.bindings.document_epoch,process_id=actor.bindings.process_id)
        return rehash(p)

    def observe(self,actor,p=None):
        p=self.captured(actor) if p is None else p
        with patch.object(actor,'_next',side_effect=lambda:dict(kind='snapshot',id=actor.sequence,packet=copy.deepcopy(p))):return actor.inspect()

    def test_ready_external_pin_fields_and_typed_process_id_must_match_launch(self):
        for key in (*process.core.PIN_FIELDS,'protocol','process_id'):
            def change(value,key=key):value[key]=True if key=='process_id' else 'wrong' if key=='protocol' else 'f'*64
            with self.subTest(key=key),self.setup_actor(ready_change=change) as h:
                with self.assertRaises(process.core.SmallSourceError) as caught:h.create()
                self.assertEqual(caught.exception.code,'small_skin_worker_binding');self.assertEqual(caught.exception.status,'unavailable')
                self.assertIsNotNone(h.child.poll());self.assertTrue(all(s.closed for s in (h.child.stdin,h.child.stdout,h.child.stderr)))

    def test_ready_frame_unit_epoch_and_role_identities_are_not_coerced(self):
        cases=[(lambda v:v['frame'].update(number=True),'worker_frame_unit_binding'),
            (lambda v:v.update(unit_scale_m=True),'worker_frame_unit_binding'),
            (lambda v:v.update(deadline_ns=True),'worker_frame_unit_binding'),
            (lambda v:v.update(document_epoch='x'*32),'external_unit_epoch'),
            (lambda v:v['mesh_identity'].update(name='Different'),'external_role_name'),
            (lambda v:v['mesh_identity'].update(session_uid=True),'identity_value')]
        for change,code in cases:
            with self.subTest(code=code),self.setup_actor(ready_change=change) as h:
                with self.assertRaises(process.core.SmallSourceError) as caught:h.create()
                self.assertEqual(caught.exception.code,'small_skin_'+code);self.assertIsNotNone(h.child.poll())

    def test_ready_capability_limits_are_strictly_typed(self):
        for key,value in (('byte_limit',float(process.r.MAX_BYTES)),('max_requests',16.),('geometry_setters',False),('sets_frame',True),('generic_exec',True)):
            with self.subTest(key=key),self.setup_actor(ready_change=lambda v:v.update({key:value})) as h:
                with self.assertRaises(process.core.SmallSourceError) as caught:h.create()
                self.assertEqual(caught.exception.code,'small_skin_worker_capabilities');self.assertIsNotNone(h.child.poll())

    def test_first_and_second_reader_start_failure_cleanup_precedes_handshake(self):
        for ordinal in (1,2):
            with self.subTest(ordinal=ordinal),self.setup_actor(start_failure=ordinal) as h:
                with self.assertRaises(LaunchFailure):h.create()
                h.handshake.assert_not_called();self.assertIsNotNone(h.child.poll())
                self.assertTrue(all(s.closed for s in (h.child.stdin,h.child.stdout,h.child.stderr)))

    def test_analysis_or_selection_without_actual_observation_is_refused(self):
        with self.setup_actor() as h:
            actor=h.create();p=self.captured(actor)
            try:
                with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                    for callback in (lambda:actor.analyze(p,deadline_ns=actor.deadline_ns),
                        lambda:actor.bind_selection(p,stable_selection(p),deadline_ns=actor.deadline_ns)):
                        with self.assertRaises(process.core.SmallSourceError) as caught:callback()
                        self.assertEqual(caught.exception.code,'small_skin_observation_required');self.assertEqual(caught.exception.status,'unavailable')
                    geometry.assert_not_called()
            finally:actor.close()

    def test_valid_observation_analysis_and_stable_query_are_source_bound(self):
        with self.setup_actor() as h:
            actor=h.create()
            try:
                p=self.observe(actor);query=actor.bind_selection(p,stable_selection(p),deadline_ns=actor.deadline_ns)
                report=actor.analyze(p,deadline_ns=actor.deadline_ns,query=query)
                self.assertEqual(report['task_query']['triangle_indices'],[0]);self.assertEqual(report['task_query']['source_sha256'],p['source_sha256'])
                self.assertEqual(report['task_query']['triangles'][0]['vertices'],[0,1,2]);self.assertEqual(report['source_validation']['schema'],process.core.SCHEMA)
                self.assertFalse(report['execution_authority']);self.assertEqual(report['geometry_setters'],0)
                bad=stable_selection(p);bad['source_ref']['scene_sha256']='0'*64
                with self.assertRaisesRegex(ValueError,'deformation_selection_stale_source'):actor.bind_selection(p,bad,deadline_ns=actor.deadline_ns)
            finally:actor.close()

    def test_changed_bound_scope_or_tail_is_rejected_before_shared_geometry(self):
        for mode,expected in (('pin','external_binding_mismatch'),('vertex','LBS_replay_disagreement'),('face','triangles')):
            with self.subTest(mode=mode),self.setup_actor() as h:
                actor=h.create();p=self.captured(actor)
                if mode=='pin':p['identity']['scene_sha256']='f'*64
                elif mode=='vertex':p['evaluated']['vertices'][-1][0]+=.1
                else:p['inputs']['mesh']['triangles'][0][0]=True;p['evaluated']['triangles'][0][0]=True
                rehash(p)
                try:
                    with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                        with self.assertRaises(process.core.SmallSourceError) as caught:self.observe(actor,p)
                        self.assertEqual(caught.exception.code,'small_skin_'+expected);self.assertIsNone(actor.source);geometry.assert_not_called()
                finally:actor.close()

    def test_first_capture_cannot_choose_its_own_epoch_roles_frame_or_unit(self):
        for mode,expected in (('epoch','external_binding_mismatch'),('instance','role_instance_changed'),
            ('frame','fixed_frame'),('unit','fixed_unit'),('role','fixed_roles')):
            with self.subTest(mode=mode),self.setup_actor() as h:
                actor=h.create();p=self.captured(actor)
                if mode=='epoch':p['identity']['document_epoch']='b'*32
                elif mode=='instance':
                    for collection in (p['inputs']['closure'],p['inputs']['scene']['objects']):
                        next(o for o in collection if o['name']=='Mesh')['identity']['session_uid']=99
                elif mode=='frame':p['inputs']['frame']['number']=2
                elif mode=='unit':p['inputs']['unit_scale_m']=.001
                else:p['inputs']['mesh']['name']='Other'
                rehash(p)
                try:
                    with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                        with self.assertRaises(process.core.SmallSourceError) as caught:self.observe(actor,p)
                        self.assertEqual(caught.exception.code,'small_skin_'+expected);self.assertEqual(caught.exception.status,'unavailable')
                        self.assertIsNone(actor.source);geometry.assert_not_called()
                finally:actor.close()

    def test_caller_cannot_rebind_first_observation_by_mutating_future_key(self):
        with self.setup_actor() as h:
            actor=h.create();p=fixture(True);p['identity']=copy.deepcopy(self.captured(actor)['identity']);rehash(p)
            try:
                observed=self.observe(actor,p);first_sha=observed['source_sha256']
                self.assertEqual(actor.source,first_sha);self.assertIs(type(actor.source),str)
                keys=observed['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0]['keys']
                keys.append(dict(keys[-1],co=[5.,.2]));rehash(observed)
                self.assertNotEqual(observed['source_sha256'],first_sha);self.assertEqual(actor.source,first_sha)
                with patch.object(process.surface_deformation,'_analyze_geometry') as geometry:
                    with self.assertRaises(process.core.SmallSourceError) as caught:actor.analyze(observed,deadline_ns=actor.deadline_ns)
                    self.assertEqual(caught.exception.code,'small_skin_stale_source');self.assertEqual(caught.exception.status,'unavailable')
                    geometry.assert_not_called()
                self.assertEqual(actor.source,first_sha)
            finally:actor.close()

    def test_sixteen_reads_use_original_deadline_then_refuse_without_sending(self):
        with self.setup_actor() as h:
            actor=h.create();p=self.captured(actor);deadline=actor.deadline_ns
            try:
                for _ in range(16):self.observe(actor,p)
                before=h.child.stdin.getvalue();requests=[process.r.decode(v) for v in before.splitlines()]
                self.assertEqual(len(requests),16);self.assertEqual({v['deadline_ns'] for v in requests},{deadline})
                with self.assertRaisesRegex(process.core.SmallSourceError,'request_lifetime'):actor.inspect()
                self.assertEqual(h.child.stdin.getvalue(),before);self.assertEqual(actor.deadline_ns,deadline)
            finally:actor.close()

    def test_analysis_selection_deadline_mismatch_and_expiry_do_not_renew(self):
        with self.setup_actor() as h:
            actor=h.create();p=self.observe(actor)
            try:
                with self.assertRaisesRegex(process.core.SmallSourceError,'analysis_window'):actor.analyze(p,deadline_ns=actor.deadline_ns+1)
                with self.assertRaisesRegex(process.core.SmallSourceError,'selection_window'):actor.bind_selection(p,stable_selection(p),deadline_ns=actor.deadline_ns+1)
                actor.deadline_ns=time.perf_counter_ns()-1;before=h.child.stdin.getvalue()
                with self.assertRaisesRegex(process.core.SmallSourceError,'original_deadline'):actor.inspect()
                self.assertEqual(h.child.stdin.getvalue(),before)
            finally:actor.close()

    def test_disk_profile_binary_scene_or_runtime_drift_stops_before_send(self):
        for mode in ('profile','binary','scene','runtime'):
            with self.subTest(mode=mode),self.setup_actor() as h:
                actor=h.create()
                if mode=='profile':h.path.write_bytes(h.path.read_bytes()+b' ')
                elif mode=='binary':Path(h.profile['blender_executable']).write_bytes(b'changed')
                elif mode=='scene':Path(h.profile['scene_file']).write_bytes(b'changed')
                try:
                    with patch.object(process,'check_source_drift',return_value=dict(compatible=mode!='runtime')):
                        with self.assertRaises(process.core.SmallSourceError):actor.inspect()
                    self.assertEqual(h.child.stdin.getvalue(),b'')
                finally:actor.close()

    def test_wrong_id_worker_error_cannot_impersonate_an_expected_refusal(self):
        with self.setup_actor() as h:
            actor=h.create()
            try:
                reply=dict(kind='error',id=99,reason='small_skin_bone_limit',geometry_setters=0)
                with patch.object(actor,'_next',return_value=reply):
                    with self.assertRaises(process.core.SmallSourceError) as caught:actor.inspect()
                self.assertEqual(caught.exception.code,'small_skin_error_reply_binding');self.assertEqual(caught.exception.status,'unavailable')
                self.assertIsNone(actor.source)
            finally:actor.close()

    def test_pins_are_rechecked_during_pending_publish_and_final_encoding(self):
        for phase in ('pending','published','encoded'):
            with self.subTest(phase=phase),self.setup_actor() as h:
                actor=h.create();p=self.captured(actor);actor.received_ns=100;actor.deadline_ns=1000
                output=h.root/'readback';scene=Path(h.profile['scene_file']);real_open=Path.open;real_fsync=os.fsync;real_replace=os.replace;real_dumps=json.dumps;names={}
                def change():scene.write_bytes(b'changed after observation')
                def opened(path,*a,**kw):
                    stream=real_open(path,*a,**kw);names[stream.fileno()]=path.name;return stream
                def fsync(fd):
                    real_fsync(fd)
                    if phase=='pending' and names[fd]=='REPORT_PENDING.json':change()
                def replace(source,destination):
                    real_replace(source,destination)
                    if phase=='published' and Path(destination).name=='REPORT.json':change()
                def dumps(value,*a,**kw):
                    result=real_dumps(value,*a,**kw)
                    if phase=='encoded' and type(value) is dict and 'evidence' in value:change()
                    return result
                stdout=io.StringIO()
                with patch.object(process,'SmallSkinSourceProcess',return_value=actor),patch.object(actor,'_next',side_effect=lambda:dict(kind='snapshot',id=actor.sequence,packet=copy.deepcopy(p))),\
                        patch.object(process.time,'perf_counter_ns',return_value=100),patch.object(Path,'open',opened),patch.object(os,'fsync',fsync),patch.object(os,'replace',replace),\
                        patch.object(process.run_reader.__globals__['json'],'dumps',dumps),contextlib.redirect_stdout(stdout):
                    code=process.main(['--operator-profile',str(h.path),'--output',str(output)])
                value=json.loads(stdout.getvalue());self.assertEqual(code,1);self.assertEqual(value['reason'],'small_skin_scene_pin')
                self.assertEqual(value['status'],'unavailable');self.assertFalse((output/'REPORT.json').exists());self.assertIsNotNone(h.child.poll())
                self.assertEqual((output/'REVOKED_REPORT.json').exists(),phase in ('published','encoded'))


class SmallSourceCLICloseTests(unittest.TestCase):
    def invoke(self,*,close_exit=0,expire_close=False,query_blob=None,late_encode=False):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name).resolve();out=root/'output';clock=[100];events=[];actors=[];p=fixture()
        class Actor:
            def __init__(self,_):
                self.received_ns=100;self.deadline_ns=1000;self.profile=dict(fake_profile=True);self.capabilities=dict(read_only=True)
                self.bindings=binding(p);self.source=None;self.closed=False;self.count=0;self.process=SimpleNamespace(returncode=None,poll=lambda:self.process.returncode);actors.append(self)
            def inspect(self):self.count+=1;self.source=copy.deepcopy(p);return copy.deepcopy(p)
            def analyze(self,*args,**kw):events.append(('analyze',None));return process.SmallSkinSourceProcess.analyze(self,*args,**kw)
            def bind_selection(self,*args,**kw):return process.SmallSkinSourceProcess.bind_selection(self,*args,**kw)
            def close(self):
                if self.closed:return
                events.append(('close',None));self.closed=True;self.process.returncode=close_exit
                if expire_close:clock[0]=1000
            def verify_inputs(self):process.core.check(self.deadline_ns)
        # Preserve methods before replacing the constructor module symbol.
        analyze=process.SmallSkinSourceProcess.analyze;bind=process.SmallSkinSourceProcess.bind_selection
        Actor.analyze=lambda self,*a,**kw:(events.append(('analyze',None)),analyze(self,*a,**kw))[1]
        Actor.bind_selection=lambda self,*a,**kw:bind(self,*a,**kw)
        path=root/'selection.json';argv=['--operator-profile',str(root/'unused.json'),'--output',str(out)]
        if query_blob is not None:path.write_bytes(query_blob);argv.extend(['--triangle-query',str(path)])
        original_open=Path.open;original_dumps=json.dumps
        def opened(path,*a,**kw):
            if a and a[0]=='xb':events.append(('save',path.name))
            return original_open(path,*a,**kw)
        def dumps(value,*a,**kw):
            result=original_dumps(value,*a,**kw)
            if late_encode and type(value) is dict and 'evidence' in value:clock[0]=1000
            return result
        stdout=io.StringIO()
        with patch.object(process,'SmallSkinSourceProcess',Actor),patch.object(process.time,'perf_counter_ns',side_effect=lambda:clock[0]),\
                patch.object(Path,'open',opened),patch.object(process.run_reader.__globals__['json'],'dumps',dumps),contextlib.redirect_stdout(stdout):
            code=process.main(argv)
        self.assertEqual(len(actors),1);self.assertTrue(actors[0].closed);lines=stdout.getvalue().splitlines();self.assertEqual(len(lines),1)
        return code,json.loads(lines[0]),out,events,actors[0]

    def test_close_and_zero_exit_precede_report_persistence(self):
        code,value,out,events,actor=self.invoke();self.assertEqual(code,0);self.assertEqual(actor.count,2)
        self.assertLess(events.index(('analyze',None)),events.index(('close',None)))
        self.assertLess(events.index(('close',None)),events.index(('save','REPORT_PENDING.json')))
        self.assertTrue((out/'REPORT.json').exists());self.assertEqual(value['geometry_setters'],0)

    def test_nonzero_worker_exit_never_publishes_success(self):
        code,value,out,_,_=self.invoke(close_exit=73);self.assertEqual(code,1);self.assertEqual(value['reason'],'rig_pose_source_worker_exit')
        self.assertFalse((out/'REPORT.json').exists());self.assertFalse((out/'REPORT_PENDING.json').exists())

    def test_expiry_during_close_never_publishes_success(self):
        code,value,out,_,_=self.invoke(expire_close=True);self.assertEqual(code,1);self.assertEqual(value['reason'],'rig_pose_original_deadline')
        self.assertFalse((out/'REPORT.json').exists());self.assertFalse((out/'REPORT_PENDING.json').exists())

    def test_late_success_encoding_revokes_the_report_even_after_clean_close(self):
        code,value,out,_,_=self.invoke(late_encode=True);self.assertEqual(code,1);self.assertEqual(value['reason'],'rig_pose_original_deadline')
        self.assertFalse((out/'REPORT.json').exists());self.assertTrue((out/'REVOKED_REPORT.json').exists())

    def test_explicit_invalid_query_never_degrades_into_overview_success(self):
        for blob,reason in ((b'null','deformation_selection_fields'),(b' '*4097,'deformation_selection_byte_budget'),
            (b'{"schema":0,"schema":1}','duplicate_JSON_key')):
            with self.subTest(reason=reason):
                code,value,out,_,_=self.invoke(query_blob=blob);self.assertEqual(code,1);self.assertIn(reason,value['reason']);self.assertFalse((out/'REPORT.json').exists())


if __name__=='__main__':unittest.main()
