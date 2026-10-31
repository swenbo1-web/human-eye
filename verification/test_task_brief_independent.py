"""Independent semantic and compatibility checks for opt-in task briefs.

No running Blender, model, installed configuration or persistent production state
is accessed. Expected safety distinctions come from existing real-service host
doubles, rather than deriving expectations from the new projector implementation.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, _tool_result
from human_eye_plugin.task_brief import project_task_brief
from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.scene_cache import SpatialSceneCache
from human_eye_plugin.scene_delta import apply_scene_delta
from verification.test_flow_result_contract import CapturedHost
from verification.test_host_runtime import mesh
from verification.test_live_spatial_mcp import FakeService
from verification.test_observation_queries import ranking_scene


def metadata(result):
    texts=[item['text'] for item in result['content'] if item['type']=='text']
    if len(texts)!=1:
        raise AssertionError('Exactly one metadata text block is required')
    return json.loads(texts[0])


class TaskBriefTransportIndependentTests(unittest.TestCase):
    def setUp(self):
        self.service=FakeService()
        self.server=LiveSpatialMCPServer(self.service,default_session_id='independent-brief')

    def call(self,arguments=None,name='human_eye_scene_observe'):
        return self.server.handle_jsonrpc_message({
            'jsonrpc':'2.0','id':8,'method':'tools/call',
            'params':{'name':name,'arguments':{} if arguments is None else arguments}})['result']

    def test_existing_caller_and_explicit_full_have_identical_payloads(self):
        implicit=self.call({'task_instruction':'Inspect current clearance.'})
        explicit=self.call({'task_instruction':'Inspect current clearance.','response_detail':'full'})
        self.assertEqual(implicit,explicit)
        self.assertEqual(self.service.calls[0],self.service.calls[1])
        self.assertNotIn('response_detail',self.service.calls[0][2])

    def test_invalid_detail_is_rejected_without_accessing_service(self):
        for detail in [None,False,True,0,1,'','short','FULL',[],{},['brief']]:
            with self.subTest(detail=detail):
                result=self.call({'response_detail':detail})
                self.assertTrue(result['isError'])
        self.assertEqual(self.service.calls,[])

    def test_detail_is_not_an_option_on_transform_or_status_tools(self):
        requests=[('human_eye_transform',{'action':{
            'focal_id':'part','reference_id':'base','translation':[0,0,.001]}}),
            ('human_eye_connection_status',{})]
        for name,args in requests:
            with self.subTest(name=name):
                self.assertTrue(self.call(dict(args,response_detail='brief'),name)['isError'])
        self.assertEqual(self.service.calls,[])

    def test_legacy_unstructured_context_retains_full_information(self):
        original=copy.deepcopy(self.service.observation)
        result=self.call({'response_detail':'brief'})
        self.assertFalse(result['isError'])
        self.assertEqual(metadata(result)['routing']['context_text'],'gap=0.100m')
        self.assertEqual(self.service.observation,original)
        self.assertIsNone(project_task_brief(original))

    def test_unknown_structure_is_not_fabricated_into_a_task_brief(self):
        candidates=[{}, {'status':'observed','routing':None},
            {'status':'observed','routing':{'context_text':'{"measurement": {}}'}},
            {'status':'observed','routing':{'context_text':'[]'}},
            {'status':'observed','routing':{'context_text':'null'}}]
        for value in candidates:
            with self.subTest(value=value):
                before=copy.deepcopy(value)
                self.assertIsNone(project_task_brief(value))
                self.assertEqual(value,before)

    def test_blocked_result_keeps_error_classification_and_diagnostic_reason(self):
        self.service.observation={'status':'host_quarantined','allow_action':False,
            'executed':None,'reason_codes':['prior_commit_unresolved'],
            'routing':None,'recovery':{'action':'inspect_without_repeating_motion'}}
        result=self.call({'response_detail':'brief'})
        value=metadata(result)
        self.assertTrue(result['isError'])
        self.assertEqual(value['status'],'host_quarantined')
        self.assertEqual(value['reason_codes'],['prior_commit_unresolved'])
        self.assertIsNone(value['executed'])
        self.assertEqual(value['recovery']['action'],'inspect_without_repeating_motion')

    def test_native_image_is_unchanged_in_fallback_and_not_duplicated_in_text(self):
        full=self.call({'response_detail':'full'})
        brief=self.call({'response_detail':'brief'})
        full_images=[item for item in full['content'] if item['type']=='image']
        brief_images=[item for item in brief['content'] if item['type']=='image']
        self.assertEqual(full_images,brief_images)
        self.assertEqual(len(brief_images),1)
        self.assertNotIn(brief_images[0]['data'],json.dumps(metadata(brief)))

    def test_brief_presentation_is_not_forwarded_to_service_or_mutating_request(self):
        args={'task_instruction':'Inspect a clearance.','focal_id':'part',
            'reference_id':'base','response_detail':'brief'}
        before=copy.deepcopy(args)
        self.call(args)
        self.assertEqual(args,before)
        forwarded=self.service.calls[0][2]
        self.assertNotIn('response_detail',forwarded)
        self.assertEqual(forwarded,{'task_instruction':'Inspect a clearance.',
            'focal_id':'part','reference_id':'base'})

    def test_projector_failure_cannot_replace_a_valid_full_result_with_error(self):
        value=copy.deepcopy(self.service.observation)
        full=_tool_result(value,is_error=False,response_detail='full')
        with patch('human_eye_plugin.live_spatial_mcp.project_task_brief',
                   side_effect=RuntimeError('independent presentation fault')):
            brief=_tool_result(value,is_error=False,response_detail='brief')
        self.assertEqual(brief,full)
        self.assertFalse(brief['isError'])

    def test_unencodable_brief_candidate_falls_back_to_exact_full_payload(self):
        value=copy.deepcopy(self.service.observation)
        full=_tool_result(value,is_error=False,response_detail='full')
        for candidate in [{'unsupported':{1,2}}, {'nonfinite':float('nan')},object()]:
            with self.subTest(candidate_type=type(candidate).__name__):
                with patch('human_eye_plugin.live_spatial_mcp.project_task_brief',return_value=candidate):
                    brief=_tool_result(value,is_error=False,response_detail='brief')
                self.assertEqual(brief,full)
                self.assertFalse(brief['isError'])

    def test_existing_tool_error_is_not_projected_or_reclassified(self):
        value={'status':'error','error':'actual service fault','executed':None,
            'reason_codes':['operation_result_unknown']}
        full=_tool_result(value,is_error=True,response_detail='full')
        with patch('human_eye_plugin.live_spatial_mcp.project_task_brief',
                   side_effect=AssertionError('error must not be projected')) as project:
            brief=_tool_result(value,is_error=True,response_detail='brief')
        project.assert_not_called()
        self.assertEqual(brief,full)
        self.assertTrue(brief['isError'])
        self.assertIsNone(metadata(brief)['executed'])

    def test_original_nonfinite_json_is_an_error_outside_presentation_fallback(self):
        value=copy.deepcopy(self.service.observation);value['bad_geometry_fact']=float('inf')
        with patch('human_eye_plugin.live_spatial_mcp.project_task_brief') as project:
            with self.assertRaises(ValueError):
                _tool_result(value,is_error=False,response_detail='brief')
        project.assert_not_called()

    def test_invalid_native_png_remains_an_error_outside_presentation_fallback(self):
        value=copy.deepcopy(self.service.observation)
        value['routing']['image']['data']='%%%invalid-base64%%%'
        with patch('human_eye_plugin.live_spatial_mcp.project_task_brief') as project:
            with self.assertRaises(ValueError):
                _tool_result(value,is_error=False,response_detail='brief')
        project.assert_not_called()

    def test_candidate_that_increases_payload_keeps_exact_full_result(self):
        value=copy.deepcopy(self.service.observation)
        full=_tool_result(value,is_error=False,response_detail='full')
        with patch('human_eye_plugin.live_spatial_mcp.project_task_brief',
                   return_value={'display_only_noise':'x'*100_000}):
            brief=_tool_result(value,is_error=False,response_detail='brief')
        self.assertEqual(brief,full)


class TaskBriefServiceIndependentTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name)
        path=self.folder/'config.json'
        path.write_text(json.dumps({'schema_version':'1.0',
            'project_root':str(Path(__file__).resolve().parents[1]),
            'quad_size':64,'state_file':'state.json','audit_file':'events.jsonl'}),encoding='utf-8')
        self.host=CapturedHost()
        self.service=LiveSpatialService(path,host=self.host,production_mode=True)

    def observe(self,**changes):
        options={'focal_id':'part','reference_id':'base','include_image':False}
        options.update(changes)
        return self.service.observe('brief-independent',**options)

    def full(self,value):
        return metadata(_tool_result(value,is_error=False,response_detail='full'))

    def projected(self,value):
        full=self.full(value)
        before=copy.deepcopy(full)
        brief=project_task_brief(full)
        self.assertIsInstance(brief,dict)
        self.assertEqual(full,before)
        return full,brief

    @staticmethod
    def facts(full):
        return json.loads(full['routing']['context_text'])

    def assert_scopes_unchanged(self,full,brief):
        for key in ['status','observation_status','pair_goal','task_succeeded_scope',
            'scene_assessment','action_eligibility','execution_status','reason_codes',
            'scene_capabilities','query_result','host_execution']:
            self.assertEqual(brief[key],full[key],key)
        for key in ['route','scene_revision','scene_fingerprint','observation_id',
            'allow_action','requires_reobserve','execution_scope']:
            self.assertEqual(brief['routing'][key],full['routing'][key],key)
        self.assertFalse(brief['task_brief']['execution_authority'])
        self.assertEqual(brief['task_brief']['full_diagnostics_returns'],
            'new_current_observation_not_historical_receipt')
        self.assertNotIn('context_text',brief['routing'])

    def test_exact_measurement_frames_contacts_and_snapshot_binding_are_lossless(self):
        full,brief=self.projected(self.observe())
        facts=self.facts(full)
        self.assert_scopes_unchanged(full,brief)
        for key in ['source','unit','coordinate_frame','scene_revision','focal_id','reference_id',
            'measurement','rigid_frame','scene_contacts','unknown_objects','query_result']:
            self.assertEqual(brief['observation'][key],facts[key],key)
        self.assertAlmostEqual(brief['observation']['measurement']['signed_clearance_m'],.1)
        self.assertEqual(self.host.calls,0)

    def test_partial_scene_goal_success_does_not_hide_unknown_or_blocked_execution(self):
        surface=mesh('open_surface',[20,0,.2],[.6,.4,.02])
        surface['faces']=surface['faces'][:2];surface['edges']=None
        self.host.scene['meshes'].append(surface)
        full,brief=self.projected(self.observe(goal={
            'target_clearance_m':.1,'clearance_tolerance_m':1e-7}))
        self.assert_scopes_unchanged(full,brief)
        self.assertEqual(brief['observation_status'],'partial')
        self.assertEqual(brief['pair_goal']['status'],'satisfied')
        self.assertTrue(brief['pair_goal']['satisfied'])
        self.assertEqual(brief['scene_assessment']['status'],'unknown')
        self.assertIn('open_surface',brief['scene_assessment']['unknown_object_ids'])
        self.assertEqual(brief['action_eligibility']['status'],'blocked')
        self.assertIsNone(brief['routing']['observation_id'])
        self.assertFalse(brief['routing']['allow_action'])
        self.assertTrue(brief['routing']['requires_reobserve'])
        self.assertEqual(brief['observation']['unknown_objects'],self.facts(full)['unknown_objects'])
        self.assertEqual(self.host.calls,0)

    def test_exact_zero_false_and_zero_tolerance_survive_projection(self):
        self.host.scene['meshes'][1]=mesh('part',[0,0,.25],[.2,.3,.1],True)
        full,brief=self.projected(self.observe(goal={
            'target_clearance_m':0.,'clearance_tolerance_m':0.}))
        measurement=brief['observation']['measurement']
        self.assertEqual(measurement['signed_clearance_m'],0.)
        self.assertTrue(measurement['clearance_exact'])
        self.assertFalse(measurement['is_penetrating'])
        self.assertEqual(brief['goal_verification'],full['goal_verification'])
        self.assertEqual(brief['goal_verification']['goal']['clearance_tolerance_m'],0.)
        self.assertEqual(self.host.calls,0)

    def test_unsatisfied_caller_goal_remains_false_and_does_not_become_execution(self):
        full,brief=self.projected(self.observe(goal={
            'target_clearance_m':.05,'clearance_tolerance_m':0.}))
        self.assert_scopes_unchanged(full,brief)
        self.assertEqual(brief['pair_goal']['status'],'not_satisfied')
        self.assertIs(brief['pair_goal']['satisfied'],False)
        self.assertIs(brief['task_succeeded'],False)
        self.assertEqual(brief['execution_status'],'not_requested')
        self.assertEqual(brief['goal_verification'],full['goal_verification'])
        self.assertEqual(self.host.calls,0)

    def test_host_specific_restriction_remains_visible_despite_readable_measurement(self):
        reason={'object_id':'part','object_name':'part','reason':'nonrigid_or_nonuniform_world_frame'}
        self.host.scene['host_execution'].update(supported=False,reasons=[reason])
        full,brief=self.projected(self.observe())
        self.assert_scopes_unchanged(full,brief)
        self.assertTrue(brief['observation']['measurement']['measurement_valid'])
        self.assertEqual(brief['action_eligibility']['status'],'blocked')
        self.assertIn(reason,brief['host_execution']['reasons'])
        self.assertIn(reason['reason'],brief['action_eligibility']['reason_codes'])
        self.assertEqual(self.host.calls,0)

    def test_budget_limited_nearest_does_not_invent_rank_or_hide_unresolved_objects(self):
        support=copy.deepcopy(self.host.scene['host_execution'])
        self.host.scene=ranking_scene();self.host.scene['host_execution']=support
        full,brief=self.projected(self.observe(query={'mode':'nearest','max_exact_pairs':1}))
        self.assert_scopes_unchanged(full,brief)
        query=brief['query_result']
        self.assertEqual(query['status'],'unknown')
        self.assertIsNone(query['ranked_object_ids'])
        self.assertEqual(set(query['unresolved_object_ids']),{'diagonal-A','axial-B'})
        self.assertIn('query_exact_pair_budget_exhausted',query['reason_codes'])
        self.assertEqual(brief['observation_status'],'partial')
        self.assertFalse(brief['routing']['allow_action'])
        self.assertEqual(brief['observation']['scene_contacts'],self.facts(full)['scene_contacts'])

    def test_overview_lower_bounds_do_not_turn_into_exact_distance_or_order(self):
        support=copy.deepcopy(self.host.scene['host_execution'])
        self.host.scene=ranking_scene();self.host.scene['host_execution']=support
        full,brief=self.projected(self.observe())
        contacts={record['object_id']:record for record in brief['observation']['scene_contacts']}
        for key in ['diagonal-A','axial-B']:
            self.assertEqual(contacts[key]['measurement_kind'],'lower_bound')
            self.assertFalse(contacts[key]['clearance_exact'])
            self.assertIsNone(contacts[key]['signed_clearance_m'])
        self.assertEqual(brief['query_result'],full['query_result'])

    def test_unpaired_scene_keeps_pair_required_and_unknown_nearest(self):
        self.host.scene['meshes']=self.host.scene['meshes'][:1]
        full,brief=self.projected(self.observe(focal_id=None,reference_id=None,query={'mode':'nearest'}))
        self.assert_scopes_unchanged(full,brief)
        self.assertEqual(brief['status'],'overview')
        self.assertTrue(brief['observation']['pair_required_for_clearance'])
        self.assertNotIn('measurement',brief['observation'])
        self.assertEqual(brief['query_result']['status'],'unknown')
        self.assertIn('query_pair_required',brief['query_result']['reason_codes'])
        self.assertIsNone(brief['pair_goal']['focal_id'])
        self.assertIsNone(brief['pair_goal']['reference_id'])

    def test_requested_full_snapshot_and_diagnostic_remain_reconstructable(self):
        full,brief=self.projected(self.observe(scene_delta={}))
        self.assertEqual(brief['scene_transport'],full['scene_transport'])
        self.assertEqual(brief.get('scene_transport_diagnostic'),full.get('scene_transport_diagnostic'))
        rebuilt=apply_scene_delta(None,brief['scene_transport'])
        self.assertEqual(rebuilt['meshes'],self.host.scene['meshes'])
        self.assertFalse(brief['scene_transport']['execution_authority'])
        self.assertEqual(self.host.calls,0)

    def test_invalid_historical_base_falls_back_to_full_with_its_diagnostic_intact(self):
        import hashlib
        self.host.scene['host_identity']={'schema_version':'1.0','document_epoch':'brief-doc',
            'object_instances':{'base':'base-instance','part':'part-instance'},
            'capture_scope':'complete_scene_meshes'}
        invalid=_validated_scene(self.host.scene)[0]
        invalid['host_identity']['object_instances']['not-captured']='invalid-instance'
        encoded=json.dumps(invalid,sort_keys=True,ensure_ascii=False,allow_nan=False,
            separators=(',',':')).encode('utf-8')
        cache=SpatialSceneCache();cache.record_scene(invalid)
        self.service._perception_cache=cache
        full,brief=self.projected(self.observe(scene_delta={
            'base_revision':invalid['revision'],'base_fingerprint':hashlib.sha256(encoded).hexdigest()}))
        self.assertEqual(brief['scene_transport']['status'],'full')
        self.assertEqual(brief['scene_transport_diagnostic'],full['scene_transport_diagnostic'])
        self.assertEqual(brief['scene_transport_diagnostic']['base_status'],'invalid_or_unusable_full_resync')
        self.assertEqual(apply_scene_delta(None,brief['scene_transport']),_validated_scene(self.host.scene)[0])
        self.assertEqual(self.host.calls,0)

    def test_analytical_contact_section_cannot_become_natural_visibility_or_path_evidence(self):
        full,brief=self.projected(self.observe(include_image=True,query={'visual_diagnostic':'contact_section'}))
        diagnostics=brief['observation']['visual_diagnostics']
        self.assertEqual(diagnostics,self.facts(full)['visual_diagnostics'])
        self.assertEqual(diagnostics['status'],'available')
        self.assertFalse(diagnostics['natural_visibility_certified'])
        self.assertFalse(diagnostics['free_path_certified'])
        self.assertFalse(diagnostics['execution_authority'])
        self.assertFalse(diagnostics['independent_ground_truth'])
        self.assertFalse(diagnostics['geometry_modified'])
        self.assertEqual(self.host.calls,0)

    def test_additive_future_safety_fields_are_preserved_without_interpretation(self):
        full=self.full(self.observe())
        full['additional_risk']={'status':'unknown','reason_codes':['new-domain-not-proven']}
        full['routing']['future_review_required']={'object_id':'other','reason':'needs-human-review'}
        facts=self.facts(full);facts['future_clearance_caveat']={'applicable':None,'units':'unknown'}
        full['routing']['context_text']=json.dumps(facts)
        brief=project_task_brief(full)
        self.assertIsInstance(brief,dict)
        self.assertEqual(brief['additional_risk'],full['additional_risk'])
        self.assertEqual(brief['routing']['future_review_required'],full['routing']['future_review_required'])
        self.assertEqual(brief['observation']['future_clearance_caveat'],facts['future_clearance_caveat'])

    def test_unrecognized_coordinate_contract_falls_back_without_mutating_input(self):
        full=self.full(self.observe())
        for key,value in [('source','unknown_future_source'),('unit','mm'),('coordinate_frame','image')]:
            candidate=copy.deepcopy(full);facts=self.facts(candidate);facts[key]=value
            candidate['routing']['context_text']=json.dumps(facts)
            original=copy.deepcopy(candidate)
            with self.subTest(key=key):
                self.assertIsNone(project_task_brief(candidate))
                self.assertEqual(candidate,original)

    def test_nonstring_sources_and_statuses_fall_back_without_membership_type_errors(self):
        full=self.full(self.observe())
        for field,value in [('source',[]),('source',{}),('source',False),('source',0),
            ('status',[]),('status',{}),('status',False)]:
            candidate=copy.deepcopy(full)
            if field=='source':
                facts=self.facts(candidate);facts['source']=value
                candidate['routing']['context_text']=json.dumps(facts)
            else:
                candidate['status']=value
            original=copy.deepcopy(candidate)
            with self.subTest(field=field,value=value):
                self.assertIsNone(project_task_brief(candidate))
                self.assertEqual(candidate,original)

    def test_malformed_scoped_contract_types_are_not_presented_as_understood_briefs(self):
        full=self.full(self.observe())
        replacements=[]
        for field in ['scene_assessment','action_eligibility','pair_goal','scene_capabilities']:
            replacements.extend((field,value) for value in [None,False,0,[], 'unknown'])
        replacements.extend((field,value) for field in ['observation_status','execution_status']
            for value in [None,False,0,[],{},'new_unknown_status'])
        for field,value in replacements:
            candidate=copy.deepcopy(full);candidate[field]=value
            original=copy.deepcopy(candidate)
            with self.subTest(field=field,value=value):
                self.assertIsNone(project_task_brief(candidate))
                self.assertEqual(candidate,original)

    def test_boolean_and_zero_in_conflicting_query_evidence_are_not_treated_as_equal(self):
        full=self.full(self.observe());facts=self.facts(full)
        full['query_result']['exact_pair_count']=0
        full['routing']['query_result']['exact_pair_count']=0
        facts['query_result']['exact_pair_count']=False
        full['routing']['context_text']=json.dumps(facts)
        original=copy.deepcopy(full)
        self.assertIsNone(project_task_brief(full))
        self.assertEqual(full,original)

    def test_returned_brief_nested_data_cannot_mutate_original_result(self):
        full=self.full(self.observe());original=copy.deepcopy(full)
        brief=project_task_brief(full);self.assertIsInstance(brief,dict)
        brief['observation']['measurement']['signed_clearance_m']=999.
        brief['scene_capabilities']['scene']['captured_object_count']=999
        brief['routing']['reason_codes'].append('mutated-by-test')
        self.assertEqual(full,original)

    def test_native_png_and_critical_facts_are_unchanged_in_actual_compact_transport(self):
        value=self.observe(include_image=True);original=copy.deepcopy(value)
        full=_tool_result(value,is_error=False,response_detail='full')
        brief=_tool_result(value,is_error=False,response_detail='brief')
        self.assertEqual(value,original)
        full_metadata=metadata(full);brief_metadata=metadata(brief)
        self.assertEqual(brief_metadata['response_detail'],'brief')
        self.assert_scopes_unchanged(full_metadata,brief_metadata)
        full_images=[item for item in full['content'] if item['type']=='image']
        brief_images=[item for item in brief['content'] if item['type']=='image']
        self.assertEqual(full_images,brief_images)
        self.assertEqual(len(brief_images),1)
        full_text=full['content'][0]['text'].encode('utf-8')
        brief_text=brief['content'][0]['text'].encode('utf-8')
        self.assertGreaterEqual(len(full_text)-len(brief_text),256)
        self.assertLessEqual(len(brief_text),len(full_text)*.9)
        self.assertNotIn(brief_images[0]['data'],brief['content'][0]['text'])


if __name__=='__main__':
    unittest.main()
