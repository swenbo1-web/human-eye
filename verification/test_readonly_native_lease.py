"""Independent read leases over real host code and injectable bpy doubles.

These validate admission, restoration and writer separation. They do not replace
actual Blender rendering, transport identity or public PNG-consumer acceptance.
"""
from __future__ import annotations
import base64,copy,hashlib,os,time,unittest
from unittest.mock import patch
from verification.test_blender_native_evidence import fixture
from verification import test_blender_host_contracts as hosts
from verification import test_readonly_render_gateway as rendering
from human_eye_plugin import forward_deadline
from human_eye_plugin.auto_router import _validated_scene


READ_STORE='_human_eye_native_readonly_observation_v1'
WRITER_KEYS=('_human_eye_owned_episode_gateway_v1','_human_eye_motion_ledger_v1',
             '_human_eye_forward_deadline_requirements_v1')


class ReadonlyNativeLeaseTests(unittest.TestCase):
    def ready(self,*,locked=False):
        self.host,self.part,self.base,_=fixture()
        if locked:self.part.lock_location=(True,True,True)
        self.initial=self.host.capture_readonly_evidence()
        self.focal=self.host.object_id(self.part);self.reference=self.host.object_id(self.base)
        self.module=self.host._readonly_native_module();self.rendered=[]
        return self.host

    def writers(self):
        namespace=self.host.bpy.app.driver_namespace
        return {key:copy.deepcopy(namespace[key]) for key in WRITER_KEYS if key in namespace}

    def read(self,rid='read-one',**changes):
        args={'request_id':rid,'focal_id':self.focal,'reference_id':self.reference,
            'expected_capture_revision':self.host.capture_scene()['revision'],
            'deadline_ns':time.perf_counter_ns()+10_000_000_000,'view':'SCENE'}
        args.update(changes)
        return self.host.observe_readonly_native(**args)

    def fake_render(self,bpy,scene,layer,native,view,**options):
        options['_frustum_sink'].append({'scope':'test-only frustum double'})
        raw=b'fake image '+str(len(self.rendered)).encode();self.rendered.append(raw)
        return {'mime_type':'image/png','image_base64':base64.b64encode(raw).decode('ascii'),
            'width':384,'height':384,'view':view,'source':'hostdouble_only'}

    def patches(self,*,two=False,renderer=None):
        native=self.initial['native_scene']
        plan,frame,_=self.module.plan_native_multiscale(native,self.focal,'SCENE',self.host._scale())
        if two:
            plan.update(image_count=2,detail_included=True,
                detail=self.module._public_view_frame(frame,self.host._scale(),'intentional_local_window'))
        return (patch.object(self.module,'plan_native_multiscale',return_value=(plan,frame,frame if two else None)),
            patch.object(self.module,'native_render_state',side_effect=lambda *args:copy.deepcopy(rendering.state_sample())),
            patch.object(self.module,'native_look',side_effect=renderer or self.fake_render))

    def test_capability_creates_no_capture_namespace_or_action_state(self):
        self.ready();namespace=copy.deepcopy(self.host.bpy.app.driver_namespace)
        with patch.object(self.host,'_capture',side_effect=AssertionError('capability must not capture')):
            caps=self.host.native_observation_capabilities()
        self.assertEqual(self.host.bpy.app.driver_namespace,namespace)
        self.assertEqual(caps['protocol'],'typed-native-readonly-observation-v1-20261031')
        self.assertEqual(caps['max_duration_ns'],30_000_000_000)
        self.assertTrue(caps['read_only']);self.assertFalse(caps['execution_authority'])
        self.assertEqual(len(caps['host_source_sha256']),64)

    def test_success_without_action_episode_is_atomic_detached_and_not_authority(self):
        self.ready();before=self.writers();a,b,c=self.patches(two=True)
        with a,b,c:value=self.read()
        self.assertEqual(set(value),{'evidence','overview','detail','plan','observation'})
        self.assertEqual(value['evidence'],self.initial)
        self.assertTrue(value['evidence']['coherence']['read_only_evidence'])
        obs=value['observation'];self.assertEqual(obs['status'],'completed')
        self.assertTrue(obs['geometry_restored']);self.assertTrue(obs['state_restored'])
        self.assertFalse(obs['execution_authority']);self.assertFalse(obs['quarantined'])
        self.assertLess(obs['finished_ns'],obs['deadline_ns'])
        self.assertEqual(value['plan']['budget_scope'],'per_call_readonly_observation_lease_deadline')
        for index,frame in enumerate(obs['bundle']['frames']):
            self.assertEqual(frame['render_audit']['sequence'],index+1)
            self.assertEqual(frame['png_sha256'],hashlib.sha256(self.rendered[index]).hexdigest())
        self.assertEqual(self.writers(),before)
        self.assertEqual(self.part.assignments+self.base.assignments,0)
        with self.assertRaisesRegex(hosts._module.EpisodePrewriteRefused,'episode_not_bound'):
            self.host.native_transform(self.focal,[0.,0.,.0001],self.initial['native_scene']['revision'])
        value['observation']['bundle']['frames'].clear()
        self.assertEqual(len(self.host.last_readonly_native_audit('read-one')['bundle']['frames']),2)

    def test_fresh_host_instance_and_new_pair_observe_without_rebinding_writer(self):
        self.ready();self.host.begin_owned_episode('original-action',self.focal,self.reference,
            deadline_ns=time.perf_counter_ns()+20_000_000_000)
        before=self.writers();a,b,c=self.patches()
        with a,b,c:self.read('first')
        old=self.host
        self.host=type(old)(bpy_module=old.bpy,scene=old.scene,view_layer=old.view_layer,
            execution_metadata=True,identity_metadata=True)
        self.assertEqual(self.host.last_readonly_native_audit('first')['status'],'completed')
        module=self.host._readonly_native_module();self.module=module
        a,b,c=self.patches()
        with a,b,c:value=self.read('reverse',focal_id=self.reference,reference_id=self.focal)
        self.assertEqual(value['observation']['binding']['focal_id'],self.reference)
        self.assertEqual(self.writers(),before)
        self.assertNotIn('_last_native_multiscale_audit',self.host.__dict__)
        self.assertNotIn('_native_render_sequence',self.host.__dict__)

    def test_failed_or_unknown_writer_is_never_reset_by_observation(self):
        for unknown in (False,True):
            with self.subTest(unknown=unknown):
                self.ready();self.host.begin_owned_episode('original-action',self.focal,self.reference,
                    deadline_ns=time.perf_counter_ns()+20_000_000_000)
                module,state=self.host._episode_store()
                if unknown:
                    native=state['record']['initial_native']
                    obj=next(item for item in native['objects'] if item['object_id']==self.focal)
                    target=[obj['matrix'][axis][3]+(.0001 if axis==2 else 0.) for axis in range(3)]
                    index=module.reserve_setter(state,helper='native_transform',object_id=self.focal,
                        requested_world=target,before_native=native,binding=state['record']['binding'],
                        now_ns=time.perf_counter_ns())
                    module.mark_unknown(state,index)
                    self.assertEqual(state['record']['events'][0]['state'],'unknown')
                else:module.freeze_episode(state,'existing-action-frozen')
                before=self.writers();a,b,c=self.patches()
                with a,b,c:self.read()
                self.assertEqual(self.writers(),before)
                with self.assertRaises(hosts._module.EpisodeUncertain):
                    self.host.native_transform(self.focal,[0.,0.,.0001],self.initial['native_scene']['revision'])
                self.assertEqual(self.part.assignments,0)

    def test_existing_three_writer_ledgers_and_confirmed_setter_are_unchanged(self):
        self.ready();self.host.begin_owned_episode('original-action',self.focal,self.reference,
            deadline_ns=time.perf_counter_ns()+20_000_000_000)
        self.host.begin_motion_goal('original-goal',self.focal,self.reference)
        self.host.require_forward_deadline('original-goal')
        scene=self.host.capture_scene();_,_,fingerprint=_validated_scene(scene)
        action={'focal_id':self.focal,'reference_id':self.reference,'translation':[0.,0.,.0005]}
        nonce='1'*32;now=time.perf_counter()
        lease=forward_deadline.make_deadline(now+15.,now+10.,goal_id='original-goal',
            binding=self.host.motion_goal_status('original-goal')['binding'],process_id=os.getpid())
        wire=forward_deadline.bind_deadline(lease,action=action,expected_revision=scene['revision'],
            expected_fingerprint=fingerprint,request_nonce=nonce)
        self.host.apply_transform(action,expected_revision=scene['revision'],expected_fingerprint=fingerprint,
            request_nonce=nonce,forward_deadline=wire)
        self.assertEqual(self.part.assignments,1)
        self.initial=self.host.capture_readonly_evidence()
        before=self.writers();self.assertEqual(set(before),set(WRITER_KEYS))
        a,b,c=self.patches()
        with a,b,c:value=self.read('after-action')
        self.assertEqual(value['evidence'],self.initial)
        self.assertEqual(self.writers(),before);self.assertEqual(self.part.assignments,1)

    def test_expired_action_does_not_expire_read_or_gain_a_renewed_deadline(self):
        self.ready();action_deadline=time.perf_counter_ns()+1_000_000_000
        self.host.begin_owned_episode('original-action',self.focal,self.reference,
            deadline_ns=action_deadline)
        before=self.writers();now=action_deadline+1
        a,b,c=self.patches()
        with patch.object(time,'perf_counter_ns',return_value=now),a,b,c:
            value=self.read('after-action-expiry',deadline_ns=now+5_000_000_000)
            self.assertEqual(value['observation']['status'],'completed')
            self.assertEqual(self.writers(),before)
            with self.assertRaisesRegex(hosts._module.EpisodePrewriteRefused,'deadline_expired'):
                self.host.native_transform(self.focal,[0.,0.,.0001],self.initial['native_scene']['revision'])
        self.assertEqual(self.part.assignments,0)

    def test_same_live_request_is_not_replayed_as_fresh_or_rendered_twice(self):
        self.ready();a,b,c=self.patches()
        with a,b,c:
            self.read('same')
            count=len(self.rendered)
            with self.assertRaisesRegex(hosts._module.EpisodePrewriteRefused,'request_reused'):
                self.read('same')
        self.assertEqual(len(self.rendered),count)
        self.assertEqual(self.host.last_readonly_native_audit('same')['status'],'completed')
        self.assertEqual(self.host.last_readonly_native_audit('other')['status'],'unavailable')

    def test_capacity_never_evicts_live_request_and_only_expired_ids_are_pruned(self):
        self.ready();store=self.host._readonly_observation_store(create=True)
        limit=time.perf_counter_ns()+15_000_000_000
        store['seen']={str(i):limit for i in range(128)}
        before=copy.deepcopy(store['seen'])
        with self.assertRaisesRegex(hosts._module.EpisodePrewriteRefused,'capacity'):self.read('new')
        self.assertEqual(store['seen'],before)
        store['seen']['0']=1
        a,b,c=self.patches()
        with a,b,c:self.read('new')
        self.assertNotIn('0',store['seen']);self.assertEqual(len(store['seen']),128)
        self.assertTrue(all(store['seen'][str(i)]==limit for i in range(1,128)))

    def test_invalid_or_expired_window_cannot_create_store_or_render(self):
        self.ready()
        for value in (True,None,0,1,time.perf_counter_ns()+31_000_000_000):
            with self.subTest(deadline=value),self.assertRaises(hosts._module.EpisodePrewriteRefused):
                self.read(deadline_ns=value)
        self.assertNotIn(READ_STORE,self.host.bpy.app.driver_namespace)
        self.assertEqual(self.part.assignments,0)

    def test_stale_capture_fails_before_render_and_fresh_request_is_still_allowed(self):
        self.ready();a,b,c=self.patches()
        with a,b,c:
            with self.assertRaisesRegex(hosts._module.EpisodePrewriteRefused,'stale_capture'):
                self.read('stale',expected_capture_revision='old')
            self.assertEqual(len(self.rendered),0)
            self.assertFalse(self.host.last_readonly_native_audit('stale')['quarantined'])
            self.read('fresh')
        self.assertEqual(len(self.rendered),1)

    def test_plan_expiry_starts_no_render_and_does_not_extend_deadline(self):
        self.ready();now=[time.perf_counter_ns()];limit=now[0]+5_000_000_000
        original=self.module.plan_native_multiscale
        def expire(*args,**kwargs):
            value=original(*args,**kwargs);now[0]=limit;return value
        with patch.object(time,'perf_counter_ns',side_effect=lambda:now[0]),\
             patch.object(self.module,'plan_native_multiscale',side_effect=expire),\
             patch.object(self.module,'native_look',side_effect=AssertionError('late render started')):
            with self.assertRaisesRegex(hosts._module.EpisodePrewriteRefused,'deadline_expired'):
                self.read('late',deadline_ns=limit)
        obs=self.host.last_readonly_native_audit('late')
        self.assertEqual(obs['deadline_ns'],limit);self.assertEqual(obs['bundle']['frames'],[])
        self.assertFalse(obs['quarantined'])

    def test_locked_read_stays_nonexecuting_and_other_unsupported_geometry_rejected(self):
        self.ready(locked=True);a,b,c=self.patches()
        with a,b,c:value=self.read()
        self.assertFalse(value['evidence']['capture']['host_execution']['supported'])
        self.assertEqual(self.writers(),{})
        self.part.constraints=[object()]
        with self.assertRaises(hosts._module.BlenderHostError):self.read('unsupported')
        self.assertEqual(self.part.assignments+self.base.assignments,0)

    def test_second_exception_with_full_restore_fails_lease_without_partial_or_permanent_quarantine(self):
        self.ready();before=self.writers();attempt=[]
        def fail_second(*args,**kwargs):
            attempt.append(True)
            if len(attempt)==2:raise RuntimeError('owner injected second error')
            return self.fake_render(*args,**kwargs)
        a,b,c=self.patches(two=True,renderer=fail_second)
        with a,b,c,self.assertRaises(RuntimeError):self.read('partial')
        obs=self.host.last_readonly_native_audit('partial')
        self.assertEqual(obs['status'],'failed');self.assertEqual(len(obs['bundle']['frames']),2)
        self.assertIsNone(obs['bundle']['frames'][1]['png_sha256'])
        self.assertTrue(obs['state_restored']);self.assertTrue(obs['geometry_restored'])
        self.assertFalse(obs['quarantined']);self.assertEqual(self.writers(),before)
        a,b,c=self.patches()
        with a,b,c:self.read('new-fresh')

    def test_unrestored_read_quarantines_only_observation_not_writer_registry(self):
        self.ready();before=self.writers();a,b,c=self.patches()
        values=[rendering.state_sample(),rendering.state_sample()]
        values[1]['render']['resolution_x']+=1
        with a,c,patch.object(self.module,'native_render_state',side_effect=values),\
             self.assertRaisesRegex(hosts._module.EpisodeUncertain,'restoration_unconfirmed'):
            self.read('unrestored')
        self.assertTrue(self.host.last_readonly_native_audit('unrestored')['quarantined'])
        self.assertEqual(self.writers(),before)
        with self.assertRaisesRegex(hosts._module.EpisodeUncertain,'quarantined'):self.read('blocked')
        self.assertEqual(self.part.assignments+self.base.assignments,0)

    def test_geometry_drift_cannot_become_new_action_baseline_or_fresh_image(self):
        self.ready();self.host.begin_owned_episode('original-action',self.focal,self.reference,
            deadline_ns=time.perf_counter_ns()+20_000_000_000)
        before=self.writers()
        def drift(*args,**kwargs):
            image=self.fake_render(*args,**kwargs);self.part._matrix_world[2][3]+=.001;return image
        a,b,c=self.patches(renderer=drift)
        with a,b,c,self.assertRaises(hosts._module.EpisodeUncertain):self.read('drift')
        self.assertTrue(self.host.last_readonly_native_audit('drift')['quarantined'])
        self.assertEqual(self.writers(),before)
        self.assertEqual(self.part.assignments+self.base.assignments,0)

    def test_nested_observation_is_refused_before_another_native_render(self):
        self.ready();nested=[]
        def render(*args,**kwargs):
            with self.assertRaisesRegex(hosts._module.EpisodePrewriteRefused,'busy'):
                self.read('nested')
            nested.append(True);return self.fake_render(*args,**kwargs)
        a,b,c=self.patches(renderer=render)
        with a,b,c:self.read('outer')
        self.assertEqual(nested,[True]);self.assertEqual(len(self.rendered),1)


if __name__=='__main__':unittest.main()
