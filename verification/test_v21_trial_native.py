"""Public analytic fixtures for the finite independent trial baseline.

No Blender, published trial input, implementation answer or private truth is
read. All expected geometry here follows from the authored affine transforms.
"""
import copy,time,unittest
from unittest.mock import patch
from verification import v21_trial_native as native
from verification.test_b3e_native_evidence import fixture,directory,rehash


def catalog_with_bounds_state(packet):
    catalog=directory(packet)
    # The old authored oracle helper predates production bounds status fields.
    # These fixtures stay inside the coordinate domain; the new real-catalog
    # test below also exercises production's actual unstripped metadata.
    catalog['bounds'].update(state='available',reason=None)
    catalog['catalog_sha256']=native.digest({key:catalog[key] for key in native.STABLE_KEYS})
    return catalog


def triangles(scales,*,outside_unknown=False,source='1',frame=1):
    """Parallel unit right triangles, each with a known diagonal affine map."""
    packet,_,policy=fixture();mesh=packet['inputs']['mesh'];evaluated=packet['evaluated']
    weight=copy.deepcopy(mesh['weights'][0]);original=[];current=[];faces=[]
    for index,(high,low) in enumerate(scales):
        z=index*.25;base=len(original)
        original.extend([[0.,0.,z],[1.,0.,z],[0.,1.,z]])
        current.extend([[0.,0.,z],[high,0.,z],[0.,low,z]])
        faces.append([base,base+1,base+2])
    if outside_unknown:
        base=len(original);extra=[[6.,0.,0.],[7.,0.,0.],[6.,1.,0.]]
        original.extend(extra);current.extend(copy.deepcopy(extra));faces.append([base,base+1,base+2])
    mesh.update(vertices=original,triangles=faces,weights=[copy.deepcopy(weight) for _ in original])
    if outside_unknown:
        for index in faces[-1]:mesh['weights'][index]=[]
    evaluated.update(vertices=current,triangles=copy.deepcopy(faces))
    packet['identity']['scene_sha256']=source*64;packet['inputs']['frame']['number']=frame
    rehash(packet);catalog=catalog_with_bounds_state(packet)
    policy.update(source_ref=copy.deepcopy(catalog['source_ref']),catalog_sha256=catalog['catalog_sha256'],
        anchor_id=catalog['anchors'][0]['anchor_id'])
    return packet,catalog,policy


class Clock:
    def __init__(self):self.now=100
    def __call__(self):return self.now
    def advance(self,value=100):self.now+=value


class NativeTrialTests(unittest.TestCase):
    def frame(self,values,**kwargs):
        kwargs.setdefault('deadline_ns',time.perf_counter_ns()+5_000_000_000)
        return native.prepare_native_frame(*values,**kwargs)

    def pair(self,left,right,**kwargs):
        kwargs.setdefault('deadline_ns',time.perf_counter_ns()+5_000_000_000)
        return native.prepare_native_pair({'left':left,'right':right},**kwargs)

    def refused(self,reason,function,*args,**kwargs):
        with self.assertRaisesRegex(native.NativeTrialError,'^v21_trial_native_'+reason+'$'):
            function(*args,**kwargs)

    def test_known_affine_pair_has_actual_same_face_rows_and_area(self):
        left=self.frame(triangles([(1.3,.7)]));right=self.frame(triangles([(1.2,.8)],source='8',frame=25))
        result=self.pair(left,right)
        self.assertEqual(result['candidate_triangle_indices'],[0])
        rows=result['report']['candidate_witness_trajectories'][0]['frames']
        for row,wanted in zip(rows,([1.3,.7],[1.2,.8])):
            self.assertEqual(row['principal_stretches'],wanted)
            self.assertEqual(row['triangle'],0);self.assertTrue(row['in_core'])
            self.assertAlmostEqual(row['area_ratio'],wanted[0]*wanted[1])
        self.assertNotEqual(rows[0]['source_ref'],rows[1]['source_ref'])
        self.assertTrue(result['report']['same_original_topology_verified'])

    def test_separate_face_extrema_are_not_a_confirmed_mixed_witness(self):
        value=self.frame(triangles([(1.3,1.),(1.,.7)]))
        for scope in ('core_summary','global_summary'):
            self.assertIs(value['report'][scope]['has_confirmed_mixed_witness'],False)
            self.assertEqual(value['report'][scope]['confirmed_mixed_witness_count'],0)

    def test_full_global_unknown_does_not_overwrite_complete_core(self):
        value=self.frame(triangles([(1.,1.)],outside_unknown=True))
        core=value['report']['core_summary'];global_summary=value['report']['global_summary']
        self.assertEqual(value['members'],[0]);self.assertEqual(set(value['facts']),{0,1})
        self.assertEqual(core['states'],dict(measured=1,collapsed=0,unknown=0))
        self.assertIs(core['has_confirmed_mixed_witness'],False)
        self.assertIs(global_summary['has_confirmed_mixed_witness'],None)
        self.assertEqual(global_summary['unknown_reasons'],{'unweighted_vertex_source':1})
        self.assertIsNone(value['facts'][1]['principal_stretches'])
        self.assertIsNone(value['facts'][1]['area_ratio'])
        self.assertFalse(value['facts'][1]['in_core'])

    def test_known_positive_stays_positive_while_global_unknown_is_retained(self):
        value=self.frame(triangles([(1.3,.7)],outside_unknown=True))
        self.assertTrue(value['report']['global_summary']['has_confirmed_mixed_witness'])
        self.assertEqual(value['report']['global_summary']['states']['unknown'],1)
        self.assertEqual(value['report']['global_summary']['observation_state'],'partial')

    def test_collapsed_and_reference_zero_area_are_distinct(self):
        value=self.frame(triangles([(1.,0.)]))
        self.assertEqual(value['facts'][0]['state'],'collapsed')
        self.assertEqual(value['facts'][0]['principal_stretches'],[1.,0.])
        self.assertEqual(value['facts'][0]['area_ratio'],0.)
        self.assertFalse(value['report']['core_summary']['has_confirmed_mixed_witness'])
        packet,catalog,policy=triangles([(1.,1.)])
        packet['inputs']['mesh']['vertices'][2]=[2.,0.,0.]
        packet['evaluated']['vertices'][2]=[2.,0.,0.]
        rehash(packet);catalog=catalog_with_bounds_state(packet)
        policy['source_ref']=copy.deepcopy(catalog['source_ref']);policy['catalog_sha256']=catalog['catalog_sha256']
        unknown=self.frame((packet,catalog,policy))
        self.assertEqual(unknown['facts'][0]['reason'],'original_zero_area')
        self.assertIs(unknown['report']['core_summary']['has_confirmed_mixed_witness'],None)

    def test_one_slot_preserves_same_face_mixed_over_separate_larger_extrema(self):
        values=[(1.8,1.),(1.,.5),(1.3,.7)]
        left=self.frame(triangles(values));right=self.frame(triangles(values,source='8',frame=25))
        result=self.pair(left,right,max_candidates=1)
        self.assertEqual(result['candidate_triangle_indices'],[2])
        self.assertTrue(all(reason.startswith('confirmed_same_face_mixed_in_core:')
            for reason in result['report']['candidate_witness_trajectories'][0]['selection_reasons']))

    def test_budget_never_silently_drops_a_second_frame_mandatory_witness(self):
        left=self.frame(triangles([(1.3,.7),(1.,1.)]))
        right=self.frame(triangles([(1.,1.),(1.3,.7)],source='8',frame=25))
        self.refused('mandatory_witness_budget',self.pair,left,right,max_candidates=1)
        self.assertEqual(set(self.pair(left,right,max_candidates=2)['candidate_triangle_indices']),{0,1})

    def test_pair_rejects_topology_difference_even_outside_the_chosen_face(self):
        left=self.frame(triangles([(1.3,.7),(1.,1.)]))
        right=self.frame(triangles([(1.3,.7),(1.,1.)],source='8',frame=25))
        wrong=copy.deepcopy(right);wrong['facts'][1]['vertices']=[3,5,4]
        self.refused('original_topology',self.pair,left,wrong)
        wrong=copy.deepcopy(right);wrong['topology_sha256']='f'*64
        self.refused('original_topology',self.pair,left,wrong)

    def test_one_source_cannot_masquerade_as_two_different_frames(self):
        value=self.frame(triangles([(1.3,.7)]))
        self.refused('distinct_sources',self.pair,value,copy.deepcopy(value))

    def test_missing_all_face_tail_is_not_a_complete_pair(self):
        left=self.frame(triangles([(1.3,.7),(1.,1.)]));right=self.frame(triangles([(1.3,.7),(1.,1.)],source='8',frame=25))
        right['facts'].pop(1)
        self.refused('complete_original_faces',self.pair,left,right)

    def test_catalog_self_consistent_digest_cannot_replace_external_source_identity(self):
        packet,catalog,policy=triangles([(1.3,.7)])
        catalog['source_ref']['frame']['number']=999
        catalog['catalog_sha256']=native.digest({key:catalog[key] for key in native.STABLE_KEYS})
        policy.update(source_ref=copy.deepcopy(catalog['source_ref']),catalog_sha256=catalog['catalog_sha256'])
        self.refused('catalog_source_binding',self.frame,(packet,catalog,policy))

    def test_real_product_catalog_keeps_verified_bounds_state_and_reason(self):
        from human_eye_plugin import small_skin_source as source,deformation_anchors as anchors
        from verification.test_small_skin_source import packet as authored,binding
        packet=authored();deadline=time.perf_counter_ns()+5_000_000_000
        proof=source.validate(packet,expected_bindings=binding(packet),deadline_ns=deadline)
        pins={key:packet['identity'][key] for key in native.PIN_KEYS}
        catalog=anchors.catalog(proof,pins=pins,deadline_ns=deadline)
        _,_,policy=fixture()
        policy.update(source_ref=copy.deepcopy(catalog['source_ref']),catalog_sha256=catalog['catalog_sha256'],
            anchor_id=catalog['anchors'][0]['anchor_id'])
        value=self.frame((packet,catalog,policy))
        self.assertEqual(catalog['bounds']['state'],'available');self.assertIsNone(catalog['bounds']['reason'])
        self.assertEqual(value['facts'][0]['principal_stretches'],[1.,1.])
        wrong=copy.deepcopy(catalog);wrong['bounds']['state']='unavailable';wrong['bounds']['reason']='coordinate_underflow'
        wrong['catalog_sha256']=native.digest({key:wrong[key] for key in native.STABLE_KEYS})
        policy['catalog_sha256']=wrong['catalog_sha256']
        self.refused('catalog_bounds',self.frame,(packet,wrong,policy))

    def test_outside_coordinate_domain_bounds_status_is_verified_not_discarded(self):
        packet,_,policy=triangles([(1.,1.)])
        packet['evaluated']['mesh_matrix_world'][0][3]=1e10
        rehash(packet);catalog=directory(packet)
        self.assertIsNone(catalog['bounds']['bounds_world_m'])
        catalog['bounds'].update(state='unavailable',reason='outside_region_coordinate_domain')
        catalog['catalog_sha256']=native.digest({key:catalog[key] for key in native.STABLE_KEYS})
        policy.update(source_ref=copy.deepcopy(catalog['source_ref']),catalog_sha256=catalog['catalog_sha256'])
        value=self.frame((packet,catalog,policy))
        self.assertEqual(value['members'],[]);self.assertEqual(value['report']['core_summary']['observation_state'],'empty')
        self.assertEqual(value['report']['global_summary']['states']['measured'],1)
        wrong=copy.deepcopy(catalog);wrong['bounds']['reason']='coordinate_underflow'
        wrong['catalog_sha256']=native.digest({key:wrong[key] for key in native.STABLE_KEYS})
        policy['catalog_sha256']=wrong['catalog_sha256']
        self.refused('catalog_bounds',self.frame,(packet,wrong,policy))

    def test_calculation_does_not_mutate_the_common_capture_or_call_product_math(self):
        values=triangles([(1.3,.7)]);before=copy.deepcopy(values)
        with (patch('human_eye_plugin.surface_deformation._geometry_rows',side_effect=AssertionError('production B2')),
             patch('human_eye_plugin.deformation_region.select',side_effect=AssertionError('production selector'))):
            value=self.frame(values)
        self.assertEqual(values,before);self.assertEqual(value['facts'][0]['principal_stretches'],[1.3,.7])

    def test_expired_start_rejects_before_geometry(self):
        clock=Clock()
        with patch.object(native,'independent_metric',side_effect=AssertionError('late geometry')):
            self.refused('deadline',self.frame,triangles([(1.3,.7)]),clock_ns=clock,deadline_ns=clock())

    def test_expiry_during_metric_or_final_serialization_cannot_return_a_report(self):
        for stage in ('metric','serialization'):
            with self.subTest(stage=stage):
                clock=Clock();real=native.independent_metric if stage=='metric' else native.encode
                def late(*args,**kwargs):
                    value=real(*args,**kwargs);clock.advance();return value
                with patch.object(native,'independent_metric' if stage=='metric' else 'encode',side_effect=late):
                    self.refused('deadline',self.frame,triangles([(1.3,.7)]),clock_ns=clock,deadline_ns=150)

    def test_pair_final_serialization_preserves_absolute_deadline(self):
        left=self.frame(triangles([(1.3,.7)]));right=self.frame(triangles([(1.2,.8)],source='8',frame=25))
        clock=Clock();real=native.encode
        def late(*args,**kwargs):
            value=real(*args,**kwargs);clock.advance();return value
        with patch.object(native,'encode',side_effect=late):
            self.refused('deadline',self.pair,left,right,clock_ns=clock,deadline_ns=150)


if __name__=='__main__':unittest.main()
