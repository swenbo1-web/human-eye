"""Finite task queries keep full source validation and bounded honest facts.

These source-valid packets are mathematical doubles, not native asset evidence.
Target truths use the authored half-turn formula plus independent NumPy QR/SVD.
"""
import copy,time,unittest
from unittest.mock import patch
import numpy as np
from human_eye_plugin import surface_deformation as d
from verification.run_deformation_task_probe import fixture,independent_target
from verification.test_skin_source import rehash


def query(packet,ids=(128,)):
    return dict(schema='surface-deformation-query-v1',expected_source_sha256=packet['source_sha256'],triangle_indices=list(ids))


def selection(packet,ids=(128,)):
    return dict(schema='surface-deformation-selection-v1',source_ref=dict(scene_sha256=packet['scene_sha256'],
        rig_object_id=packet['rig']['identity']['object_id'],mesh_object_id=packet['mesh']['identity']['object_id'],
        frame=copy.deepcopy(packet['rig']['payload']['frame'])),triangle_indices=list(ids))


class DeformationTaskQueries(unittest.TestCase):
    def analyze(self,packet,**kwargs):return d.analyze(packet,deadline_ns=time.perf_counter_ns()+5_000_000_000,**kwargs)
    def bind(self,packet,value):return d.bind_selection(packet,value,deadline_ns=time.perf_counter_ns()+5_000_000_000)

    def assert_metric(self,actual,expected):
        for field in ('triangle','vertices','state','reason','unweighted_vertices'):self.assertEqual(actual[field],expected[field])
        if expected['state']=='unknown':
            self.assertIsNone(actual['principal_stretches']);self.assertIsNone(actual['engineering_strains']);self.assertIsNone(actual['area_ratio'])
        else:
            np.testing.assert_allclose(actual['principal_stretches'],expected['principal_stretches'],atol=1e-12)
            self.assertAlmostEqual(actual['area_ratio'],expected['area_ratio'],places=12)

    def test_requested_normal_and_stretch_survive_unknown_summary_crowding(self):
        for weights in ((0.,0.,0.),(0.,.1,.3)):
            with self.subTest(weights=weights):
                packet=fixture('unknown_crowding',weights=weights);baseline=self.analyze(packet)
                self.assertNotIn(128,[r['triangle'] for r in baseline['triangles']])
                self.assertEqual((baseline['triangles_unknown'],baseline['triangles_measured']),(255,1))
                out=self.analyze(packet,query=query(packet));task=out.pop('task_query')
                self.assertEqual(out,baseline);self.assertEqual(task['schema'],'surface-deformation-query-result-v1')
                self.assertEqual(task['source_sha256'],packet['source_sha256']);self.assertEqual(task['triangle_indices'],[128])
                self.assertEqual(task['status'],'observed');self.assertEqual(len(task['triangles']),1)
                self.assert_metric(task['triangles'][0],independent_target(packet,128))

    def test_requested_normal_survives_collapse_crowding_without_changing_overview(self):
        packet=fixture('collapse_crowding');overview=self.analyze(packet)
        self.assertGreater(overview['triangles_collapsed'],16);self.assertNotIn(128,[r['triangle'] for r in overview['triangles']])
        out=self.analyze(packet,query=query(packet));task=out.pop('task_query');self.assertEqual(out,overview)
        self.assertEqual(task['status'],'observed');self.assert_metric(task['triangles'][0],independent_target(packet,128))

    def test_unknown_target_stays_unknown_and_null(self):
        packet=fixture('all_unweighted');out=self.analyze(packet,query=query(packet));task=out['task_query']
        self.assertEqual(task['status'],'partial');self.assert_metric(task['triangles'][0],independent_target(packet,128))
        self.assertEqual(task['triangles'][0]['unweighted_vertices'],[64,80,81])
        self.assertFalse(out['execution_authority']);self.assertEqual(out['damage_classification'],'not_inferred')
        self.assertEqual(out['geometry_setters'],0);self.assertFalse(out['original_file_saved'])

    def test_four_requested_faces_retain_order_and_do_not_expand_default_sixteen(self):
        packet=fixture('all_isometric');ids=[255,128,0,64];baseline=self.analyze(packet)
        out=self.analyze(packet,query=query(packet,ids));task=out.pop('task_query')
        self.assertEqual(out,baseline);self.assertEqual(len(out['triangles']),16);self.assertEqual(out['triangles_omitted'],240)
        self.assertEqual(task['triangle_indices'],ids);self.assertEqual([r['triangle'] for r in task['triangles']],ids)
        for row,index in zip(task['triangles'],ids):self.assert_metric(row,independent_target(packet,index))

    def test_mixed_requested_states_have_partial_task_status(self):
        packet=fixture('unknown_crowding');out=self.analyze(packet,query=query(packet,[128,0]));task=out['task_query']
        self.assertEqual(task['status'],'partial');self.assertEqual([r['state'] for r in task['triangles']],['measured','unknown'])
        self.assertEqual(task['triangles'][1]['reason'],'unweighted_vertex_source')

    def test_query_envelope_types_schema_fields_and_source_hash_are_strict(self):
        packet=fixture('all_isometric');valid=query(packet)
        bad=[False,[],{'schema':valid['schema']},dict(valid,extra=True),dict(valid,schema='surface-deformation-query-v2'),
            dict(valid,expected_source_sha256=None),dict(valid,expected_source_sha256=True),dict(valid,expected_source_sha256='f'*63),
            dict(valid,expected_source_sha256='z'*64),dict(valid,expected_source_sha256='0'*64)]
        for value in bad:
            with self.subTest(value=value),patch.object(d,'triangle_facts') as metric:
                with self.assertRaises(ValueError):self.analyze(packet,query=value)
                metric.assert_not_called()

    def test_query_indices_are_a_bounded_unique_integer_list(self):
        packet=fixture('all_isometric')
        for ids in ([],[0,1,2,3,4],[128,128],[True],[False],[1.0],['1'],[None],[-1],[256],(128,),128,None):
            with self.subTest(indices=ids),patch.object(d,'triangle_facts') as metric:
                with self.assertRaises(ValueError):self.analyze(packet,query=dict(query(packet),triangle_indices=ids))
                metric.assert_not_called()

    def test_full_source_tail_corruption_rejected_before_any_selected_metric(self):
        for kind in ('vertex','triangle'):
            packet=fixture('all_isometric');mesh=packet['mesh']
            if kind=='vertex':mesh['evaluated_vertices'][127][0]+=.1
            else:mesh['triangles'][255][0]=True;mesh['evaluated_triangles'][255][0]=True
            rehash(packet)
            with self.subTest(kind=kind),patch.object(d,'triangle_facts') as metric:
                with self.assertRaises(ValueError):self.analyze(packet,query=query(packet,[0]))
                metric.assert_not_called()

    def test_stable_selection_rebinds_new_epoch_but_old_live_query_does_not(self):
        packet=fixture('all_isometric');stable=selection(packet);live=self.bind(packet,stable)
        self.assertEqual(live,query(packet))
        fresh=copy.deepcopy(packet);fresh['rig']['identity']['document_epoch']='e'*32;rehash(fresh)
        self.assertNotEqual(fresh['source_sha256'],packet['source_sha256'])
        rebound=self.bind(fresh,stable);self.assertEqual(rebound,query(fresh))
        with self.assertRaises(ValueError):self.analyze(fresh,query=live)
        out=self.analyze(fresh,query=rebound);self.assertEqual(out['task_query']['source_sha256'],fresh['source_sha256'])
        self.assertFalse(out['execution_authority'])

    def test_selection_rejects_changed_file_roles_or_frame_instead_of_rebinding(self):
        packet=fixture('all_isometric');valid=selection(packet)
        changes=[('scene_sha256','0'*64),('rig_object_id','blender:'+'0'*64),('mesh_object_id','blender:'+'0'*64),
            ('frame',dict(number=packet['rig']['payload']['frame']['number']+1,subframe=0.)),
            ('frame',dict(number=packet['rig']['payload']['frame']['number'],subframe=.5))]
        for field,value in changes:
            proposal=copy.deepcopy(valid);proposal['source_ref'][field]=value
            with self.subTest(field=field,value=value):
                with self.assertRaises(ValueError):self.bind(packet,proposal)

    def test_selection_exact_fields_and_frame_types_are_strict(self):
        packet=fixture('all_isometric');valid=selection(packet)
        bad=[None,False,[],dict(valid,extra=True),dict(valid,schema='surface-deformation-selection-v2'),
            dict(valid,source_ref={}),dict(valid,source_ref=dict(valid['source_ref'],extra=True)),dict(valid,triangle_indices=[128,128]),
            dict(valid,triangle_indices=[True]),dict(valid,triangle_indices=[]),dict(valid,triangle_indices=[0,1,2,3,4])]
        for field,value in (('scene_sha256',False),('rig_object_id',None),('mesh_object_id',12)):
            proposal=copy.deepcopy(valid);proposal['source_ref'][field]=value;bad.append(proposal)
        for frame in (None,dict(number=True,subframe=0.),dict(number=1.0,subframe=0.),dict(number=1,subframe=True),
            dict(number=1,subframe=float('nan')),dict(number=1,subframe=float('inf')),dict(number=1,subframe=-.1),
            dict(number=1,subframe=1.),dict(number=1,subframe=0.,extra=True)):
            proposal=copy.deepcopy(valid);proposal['source_ref']['frame']=frame;bad.append(proposal)
        for proposal in bad:
            with self.subTest(proposal=proposal):
                with self.assertRaises(ValueError):self.bind(packet,proposal)

    def test_inputs_are_not_mutated_or_aliased_into_bound_requests(self):
        packet=fixture('all_isometric');proposal=selection(packet,[128,0]);saved=copy.deepcopy((packet,proposal))
        live=self.bind(packet,proposal);self.assertEqual((packet,proposal),saved)
        proposal['triangle_indices'][0]=7;self.assertEqual(live['triangle_indices'],[128,0])
        before=copy.deepcopy((packet,live));out=self.analyze(packet,query=live);self.assertEqual((packet,live),before)
        out['task_query']['triangle_indices'][0]=11;self.assertEqual(live['triangle_indices'],[128,0])

    def test_original_deadline_applies_to_query_entry_and_final_output(self):
        packet=fixture('all_isometric');live=query(packet);proposal=selection(packet)
        for call in (lambda:d.analyze(packet,query=live,deadline_ns=time.perf_counter_ns()-1),
            lambda:d.bind_selection(packet,proposal,deadline_ns=time.perf_counter_ns()-1)):
            with self.assertRaisesRegex(ValueError,'original_deadline'):call()
        clock=[0];count=[0];original=d.triangle_facts
        def late(*args,**kwargs):
            result=original(*args,**kwargs);count[0]+=1
            if count[0]==256:clock[0]=100
            return result
        with patch.object(d,'triangle_facts',late),patch.object(d.r.time,'perf_counter_ns',side_effect=lambda:clock[0]):
            with self.assertRaisesRegex(ValueError,'original_deadline'):d.analyze(packet,query=live,deadline_ns=100)
        checks=[0]
        def expire_after_entry():checks[0]+=1;return 0 if checks[0]==1 else 100
        with patch.object(d.r.time,'perf_counter_ns',side_effect=expire_after_entry):
            with self.assertRaisesRegex(ValueError,'original_deadline'):d.bind_selection(packet,proposal,deadline_ns=100)


if __name__=='__main__':unittest.main()
