"""Independent dependency counterexamples over authored, source-valid doubles.

These tests certify the qualification checker only. They are not native actor,
production admission, malicious-producer authentication or model-value evidence.
"""
import copy,time,unittest
from unittest.mock import patch
from verification import rigged_source_qualification as q
from verification.test_rigged_source_qualification import fixture,rehash


def rig_object(packet):return next(o for o in packet['inputs']['closure'] if o['name']==packet['inputs']['rig']['name'])
def first_curve(packet):return packet['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]['fcurves'][0]


def add_muted_track(packet):
    action=packet['inputs']['actions'][0];slot=action['slots'][0]
    strip=dict(action=action['name'],action_id=copy.deepcopy(action['identity']),
        action_slot={k:copy.deepcopy(slot[k]) for k in ('handle','identifier','target_id_type')},
        settings=dict(type='CLIP',mute=False,influence=0.,frame_start=0.,frame_end=6.,blend_in=0.,blend_out=0.),
        modifiers=[],fcurves=[],strips=[])
    rig_object(packet)['animation']['object']['nla_tracks']=[dict(name='Stashed',mute=True,is_solo=False,strips=[strip])]
    return rehash(packet)


class DependencyContractTests(unittest.TestCase):
    def qualify(self,packet,**kwargs):return q.qualify(packet,deadline_ns=time.perf_counter_ns()+5_000_000_000,**kwargs)
    def refused(self,packet,reason,status='rejected'):
        out=self.qualify(rehash(packet));self.assertEqual(out['reasons'],[reason],out)
        self.assertEqual(out['status'],status,out);self.assertEqual(out['dependency_admission'],status)
        self.assertFalse(out['product_support_certified']);self.assertFalse(out['execution_authority']);return out

    def changed_source_same_geometry(self,before,after):
        rehash(after);self.assertEqual(before['evaluated'],after['evaluated'])
        self.assertNotEqual(before['source_sha256'],after['source_sha256'])
        out=self.qualify(after);self.assertEqual(out['status'],'qualified',out)
        stale=self.qualify(after,expected_source_sha256=before['source_sha256'])
        self.assertEqual(stale['reasons'],['b3_stale_source']);self.assertEqual(stale['status'],'rejected')

    def test_parent_inverse_and_basis_compensation_preserves_world_but_invalidates_source(self):
        before=fixture();after=copy.deepcopy(before);obj=rig_object(after)
        obj['matrix_parent_inverse'][0][3]=.125;obj['matrix_basis'][0][3]=-.125;obj['location'][0]=-.125
        self.assertEqual(obj['matrix_world'],rig_object(before)['matrix_world'])
        self.changed_source_same_geometry(before,after)

    def test_future_key_change_outside_current_interval_preserves_pose_but_invalidates_source(self):
        before=fixture(True);curve=first_curve(before)
        curve['keys'].extend([dict(co=[4.,0.],interpolation='LINEAR'),dict(co=[6.,0.],interpolation='LINEAR')]);rehash(before)
        after=copy.deepcopy(before);first_curve(after)['keys'][-1]['co'][1]=.5
        self.assertEqual(q.curve_value(first_curve(before),1.),q.curve_value(first_curve(after),1.))
        self.changed_source_same_geometry(before,after)

    def test_muted_nla_metadata_still_participates_in_source_identity(self):
        before=add_muted_track(fixture(True));after=copy.deepcopy(before)
        rig_object(after)['animation']['object']['nla_tracks'][0]['strips'][0]['settings']['blend_in']=.125
        self.changed_source_same_geometry(before,after)

    def test_unmuted_or_solo_nla_is_refused_for_the_expected_domain_reason(self):
        for key,value in (('mute',False),('is_solo',True)):
            packet=add_muted_track(fixture(True));rig_object(packet)['animation']['object']['nla_tracks'][0][key]=value
            with self.subTest(key=key):self.refused(packet,'b3_active_nla')

    def test_tweak_mode_is_refused_even_if_current_vertices_match(self):
        packet=fixture(True);rig_object(packet)['animation']['object']['use_tweak_mode']=True
        out=self.refused(packet,'b3_tweak_mode');self.assertEqual(out['numerical_replay']['LBS_maximum_error'],0.)

    def test_slot_handle_identifier_channelbag_and_foreign_users_are_checked(self):
        changes=[lambda p:rig_object(p)['animation']['object'].update(action_slot_handle=8),
            lambda p:rig_object(p)['animation']['object']['action_slot'].update(identifier='OBOther'),
            lambda p:p['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0].update(slot_handle=8),
            lambda p:p['inputs']['actions'][0]['slots'][0]['users'].append(dict(name='Outside',id_type='OBJECT',linked=False,session_uid=99))]
        for index,change in enumerate(changes):
            packet=fixture(True);change(packet)
            with self.subTest(index=index):self.refused(packet,'b3_action_slot')

    def test_unknown_layer_strip_or_bag_semantics_are_not_silently_ignored(self):
        changes=[lambda p:p['inputs']['actions'][0]['layers'][0].update(influence=.5),
            lambda p:p['inputs']['actions'][0]['layers'][0].update(mix_mode='ADD'),
            lambda p:p['inputs']['actions'][0]['layers'][0]['strips'][0].update(influence=.5),
            lambda p:p['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0].update(extra=True)]
        for index,change in enumerate(changes):
            packet=fixture(True);change(packet)
            with self.subTest(index=index):self.refused(packet,'b3_action_shape')

    def test_offline_animation_limits_match_the_capture_envelope(self):
        packet=fixture(True);packet['inputs']['actions']*=17
        self.refused(packet,'b3_action_limit')
        packet=fixture(True);bag=packet['inputs']['actions'][0]['layers'][0]['strips'][0]['channelbags'][0]
        bag['fcurves']*=65;self.refused(packet,'b3_curve_limit')
        packet=fixture(True);curve=first_curve(packet)
        curve['keys']=[dict(co=[float(i),0.],interpolation='LINEAR') for i in range(257)]
        self.refused(packet,'b3_curve_key_limit')
        curve['keys'].pop();out=self.qualify(rehash(packet));self.assertEqual(out['status'],'qualified',out)

    def test_driver_and_curve_modifier_do_not_pass_because_geometry_matches(self):
        packet=fixture(True);rig_object(packet)['animation']['object']['drivers'].append(dict(expression='0'))
        self.refused(packet,'b3_driver')
        packet=fixture(True);first_curve(packet)['modifiers'].append(dict(type='NOISE'))
        self.refused(packet,'b3_curve_modifier')

    def test_arbitrary_missing_bone_custom_property_and_bad_array_paths_are_refused(self):
        for path,index in (('pose.bones["Outside"].location',0),('pose.bones["Bone"]["custom"]',0),('location',0),('pose.bones["Bone"].location',True),('pose.bones["Bone"].location',3)):
            packet=fixture(True);first_curve(packet).update(data_path=path,array_index=index)
            with self.subTest(path=path,index=index):self.refused(packet,'b3_animation_path')

    def test_linked_source_is_not_local_even_if_all_matrices_are_identical(self):
        packet=fixture();root=packet['inputs']['closure'][0];root['object_linked']=True;root['identity']['linked']=True
        packet['inputs']['scene']['objects'][0]['identity']['linked']=True;rig_object(packet)['parent_identity']['linked']=True
        self.refused(packet,'b3_linked_source')

    def test_parent_type_missing_and_identity_are_distinct_refusals(self):
        packet=fixture();rig_object(packet)['parent_type']='BONE';rig_object(packet)['parent_bone']='Bone'
        self.refused(packet,'b3_parent_type')
        packet=fixture();rig_object(packet)['parent']='Missing';self.refused(packet,'b3_parent_missing')
        packet=fixture();rig_object(packet)['parent_identity']['session_uid']=999;self.refused(packet,'b3_parent_identity_binding')

    def test_scene_identity_cannot_disagree_with_same_named_closure(self):
        packet=fixture();packet['inputs']['scene']['objects'][1]['identity']['session_uid']=999
        self.refused(packet,'b3_object_identity_binding')

    def test_missing_role_closure_is_not_accepted_using_untrusted_world_numbers(self):
        packet=fixture();packet['inputs']['closure']=[o for o in packet['inputs']['closure'] if o['name']!='Rig']
        self.refused(packet,'b3_closure_missing')

    def test_equal_translation_of_evaluated_mesh_and_rig_does_not_hide_wrong_world_source(self):
        packet=fixture();packet['evaluated']['rig_matrix_world'][0][3]=1.;packet['evaluated']['mesh_matrix_world'][0][3]=1.
        # B=inv(Mrig)@Mmesh is still identity, so an LBS-only check passes.
        self.refused(packet,'b3_evaluated_world_binding')

    def test_original_pose_and_evaluated_pose_are_bound(self):
        packet=fixture();packet['inputs']['rig']['bones'][0]['pose_matrix'][0][3]=1.
        self.refused(packet,'b3_evaluated_pose_binding')
        packet=fixture();packet['inputs']['rig']['bones'][0]['pose_head'][0]=1.
        self.refused(packet,'b3_evaluated_pose_binding')

    def test_endpoints_are_checked_even_if_original_and_evaluated_heads_agree(self):
        packet=fixture();packet['inputs']['rig']['bones'][0]['pose_head'][0]=1.;packet['evaluated']['bones'][0]['pose_head'][0]=1.
        self.refused(packet,'b3_endpoint_matrix')
        packet=fixture();packet['inputs']['rig']['bones'][0]['rest_tail'][1]=2.
        self.refused(packet,'b3_endpoint_matrix')

    def test_bad_matrix_condition_is_unknown_instead_of_a_healthy_geometry_answer(self):
        packet=fixture();root=packet['inputs']['closure'][0];root['scale'][0]=1e-5
        for key in ('matrix_basis','matrix_local','matrix_world'):root[key][0][0]=1e-5
        for obj in packet['inputs']['closure'][1:]:obj['matrix_world'][0][0]=1e-5
        packet['evaluated']['rig_matrix_world'][0][0]=packet['evaluated']['mesh_matrix_world'][0][0]=1e-5
        self.refused(packet,'b3_matrix_condition','unknown')

    def test_near_key_is_interpolated_not_snapped_to_a_keyframe(self):
        curve=first_curve(fixture(True));curve['keys']=[dict(co=[.9999988675,0.],interpolation='LINEAR'),dict(co=[1.99999928,1.],interpolation='LINEAR')]
        value=q.curve_value(curve,1.);self.assertGreater(value,0.)
        self.assertAlmostEqual(value,(1.-.9999988675)/(1.99999928-.9999988675),places=15)

    def test_original_deadline_applies_at_entry_and_after_animation_work(self):
        packet=fixture(True);out=q.qualify(packet,deadline_ns=time.perf_counter_ns()-1)
        self.assertEqual(out['status'],'unknown');self.assertEqual(out['reasons'],['b3_original_deadline'])
        clock=[0];original=q.animation_metrics
        def late(*args):
            result=original(*args);clock[0]=100;return result
        with patch.object(q.time,'perf_counter_ns',side_effect=lambda:clock[0]),patch.object(q,'animation_metrics',late):
            out=q.qualify(packet,deadline_ns=100)
        self.assertEqual(out['status'],'unknown');self.assertEqual(out['reasons'],['b3_original_deadline'])


if __name__=='__main__':unittest.main()
