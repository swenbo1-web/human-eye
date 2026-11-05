"""Independent analytic task facts and boundary counterexamples; no Blender."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_plugin.live_service import LiveSpatialService
from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer, _tool_result
from human_eye_plugin.query_policy import validate_query
from verification.test_host_runtime import mesh
from verification.test_live_service import SelfLockingHost


class TaskQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / 'live.json'
        self.config.write_text(json.dumps({'schema_version':'1.0', 'enabled':True,
            'project_root':str(Path(__file__).resolve().parents[1]), 'quad_size':64,
            'state_file':'state.json', 'audit_file':'audit.jsonl'}), encoding='utf8')
        self.host = SelfLockingHost()
        self.service = LiveSpatialService(self.config, host=self.host)
        self.server = LiveSpatialMCPServer(self.service, 'task-tests')

    def query(self, facts=('aabb',), objects=None):
        return {'mode':'task', 'objects':objects or [{'name':'part'}], 'requested_facts':list(facts)}

    def observe(self, facts=('aabb',), objects=None):
        return self.service.observe('s', query=self.query(facts, objects), include_image=False)

    def pair(self, facts):
        return self.observe(facts, [{'name':'part'}, {'name':'base'}])

    def test_single_object_has_no_pair_or_unused_agent_work(self):
        self.host.scene['meshes'] = [self.host.scene['meshes'][1]]
        with patch('human_eye_plugin.task_query.measure_pair_geometry', side_effect=AssertionError('unused solver')),\
             patch('human_eye_plugin.agent_adapters.build_agent_observation', side_effect=AssertionError('unused messages')):
            result = self.observe()
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(self.host.captures, 1)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(result['work']['exact_pair_count'], 0)
        self.assertEqual(set(result['facts']), {'aabb'})
        np.testing.assert_allclose(result['facts']['aabb'][0]['value']['dimensions'], [.2,.3,.1], atol=1e-14)
        self.assertFalse(result['execution_authority'])

    def test_name_and_id_have_identical_facts_from_current_capture(self):
        a = self.observe(); b = self.observe(objects=[{'id':'part'}])
        self.assertEqual(a['facts'], b['facts'])
        self.assertEqual(a['binding']['scene_fingerprint'], b['binding']['scene_fingerprint'])

    def test_pair_analytic_axis_and_scalar_semantics(self):
        result = self.pair(['center_delta','axis_gap','surface_clearance','solid_relation','nearest_witness'])
        np.testing.assert_allclose(result['facts']['center_delta']['value'], [0,0,-.25], atol=1e-14)
        np.testing.assert_allclose(result['facts']['axis_gap']['value'], [0,0,.1], atol=1e-14)
        self.assertAlmostEqual(result['facts']['surface_clearance']['value'], .1, places=14)
        self.assertEqual(result['facts']['solid_relation']['value'], 'not_penetrating')
        self.assertEqual(result['facts']['nearest_witness']['status'], 'unknown')
        self.assertEqual(result['facts']['nearest_witness']['reason'], 'strict_nearest_witness_unavailable')
        self.assertEqual(result['work']['exact_pair_count'], 1)

    def test_only_one_pair_and_warm_cache_reuses_current_geometry(self):
        self.host.scene['meshes'].append(mesh('noise',[10,0,0],[1,1,1]))
        cold = self.pair(['surface_clearance']); warm = self.pair(['surface_clearance'])
        self.assertEqual(cold['work']['exact_pair_count'], 1)
        self.assertEqual(warm['work']['exact_pair_count'], 0)
        self.assertTrue(warm['work']['pair_cache_hit'])
        self.assertEqual(self.host.captures, 2)

    def test_aabb_direction_never_runs_exact_pair(self):
        with patch('human_eye_plugin.task_query.measure_pair_geometry', side_effect=AssertionError('unused solver')):
            result = self.pair(['axis_gap','center_delta'])
        self.assertEqual(result['work']['exact_pair_count'], 0)

    def test_missing_name_preserves_other_known_object(self):
        result = self.observe(objects=[{'name':'part'}, {'name':'missing'}])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['facts']['aabb'][0]['status'], 'measured')
        self.assertEqual(result['binding']['objects'][1]['reason'], 'object_not_found')
        self.assertEqual(result['facts']['aabb'][1]['status'], 'unknown')

    def test_duplicate_name_and_instance_ids_do_not_choose_active(self):
        other = mesh('instance',[4,0,0],[1,1,1]); other['name'] = 'part'
        self.host.scene['meshes'].append(other)
        result = self.observe()
        self.assertEqual(result['binding']['objects'][0]['reason'], 'object_name_ambiguous')
        self.assertEqual(self.observe(objects=[{'id':'instance'}])['status'], 'observed')

    def test_name_is_not_an_id_alias(self):
        self.host.scene['meshes'][1]['name'] = 'different'
        self.assertEqual(self.observe()['status'], 'partial')
        self.assertEqual(self.observe(objects=[{'id':'part'}])['status'], 'observed')

    def test_replaced_object_and_changed_revision_are_fresh(self):
        first = self.observe()
        item = self.host.scene['meshes'][1]
        item['object_id'] = 'replacement'; self.host.scene['revision'] = 'r2'
        second = self.observe()
        self.assertEqual(second['binding']['objects'][0]['object_id'], 'replacement')
        self.assertNotEqual(first['binding']['scene_fingerprint'], second['binding']['scene_fingerprint'])
        self.assertEqual(second['binding']['scene_revision'], 'r2')

    def test_unsupported_surface_retains_aabb_and_axis_but_not_solid_claim(self):
        self.host.scene['meshes'][1]['faces'] = [[0,2,1]]
        self.host.scene['meshes'][1]['edges'] = [[0,2],[2,1],[1,0]]
        result = self.pair(['aabb','axis_gap','surface_clearance','solid_relation'])
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['facts']['aabb'][0]['status'], 'measured')
        self.assertEqual(result['facts']['axis_gap']['status'], 'measured')
        self.assertEqual(result['facts']['surface_clearance']['status'], 'unknown')
        self.assertEqual(result['facts']['solid_relation']['status'], 'unknown')

    def test_zero_and_negative_do_not_claim_physical_contact_or_minimum_depth(self):
        for center, expected in ((.25,0.), (.2,-.05)):
            self.host.scene['meshes'][1] = mesh('part',[0,0,center],[.2,.3,.1],True)
            result = self.pair(['surface_clearance','solid_relation','nearest_witness'])
            clearance = result['facts']['surface_clearance']
            self.assertAlmostEqual(clearance['value'], expected, places=14)
            self.assertEqual(result['facts']['nearest_witness']['status'], 'unknown')
            if expected < 0:
                self.assertEqual(clearance['kind'], 'certified_penetration')
                self.assertIn('not_global_minimum', clearance['semantics'])
            else:
                self.assertEqual(result['facts']['solid_relation']['value'], 'not_penetrating')

    def test_strict_orthogonal_witness_keeps_independent_distance_and_direction(self):
        from verification.test_complex_scene_quality import fixture
        value = fixture('square_hole')
        self.host.scene = copy.deepcopy(value['scene'])
        result = self.observe(['surface_clearance','nearest_witness'],
            [{'id':value['focal']}, {'id':value['reference']}])
        self.assertAlmostEqual(result['facts']['surface_clearance']['value'], .019, places=14)
        witness = result['facts']['nearest_witness']
        self.assertEqual(witness['status'], 'measured')
        points = witness['value']
        self.assertAlmostEqual(float(np.linalg.norm(np.asarray(points['b'])-points['a'])), .019, places=14)
        self.assertAlmostEqual(float(np.linalg.norm(points['direction_a_to_b'])), 1., places=14)
        for item in self.host.scene['meshes']:
            if item['object_id'] == value['focal']:
                item['vertices'] = (np.asarray(item['vertices']) + [.019,0,0]).tolist()
        touching = self.observe(['surface_clearance','nearest_witness'],
            [{'id':value['focal']}, {'id':value['reference']}])
        self.assertAlmostEqual(touching['facts']['surface_clearance']['value'], 0., places=14)
        self.assertEqual(touching['facts']['nearest_witness']['direction_status'], 'unknown')
        self.assertIsNone(touching['facts']['nearest_witness']['value']['direction_a_to_b'])

    def test_world_rotated_aabb_uses_represented_vertices(self):
        rotation = np.array([[0,-1,0],[1,0,0],[0,0,1.]])
        self.host.scene['meshes'][1]['vertices'] = (np.array(self.host.scene['meshes'][1]['vertices']) @ rotation.T).tolist()
        result = self.observe()
        np.testing.assert_allclose(result['facts']['aabb'][0]['value']['dimensions'], [.3,.2,.1], atol=1e-14)

    def test_unit_and_nonfinite_source_rejected(self):
        self.host.scene['unit'] = 'mm'
        with self.assertRaises(ValueError): self.observe()
        self.host.scene['unit'] = 'm'; self.host.scene['meshes'][1]['vertices'][0][0] = float('nan')
        with self.assertRaises(ValueError): self.observe()

    def test_center_delta_matches_exposed_centers_at_large_origin_and_reverses(self):
        for offset in (0., 1e16):
            self.host.scene['meshes'] = [mesh('part',[offset,0,0],[4,2,2]),
                                         mesh('base',[offset,0,0],[4,2,2])]
            result = self.pair(['center_delta','aabb'])
            self.assertEqual(result['facts']['center_delta']['value'], [0.,0.,0.])
        self.host.scene['meshes'][0]['vertices'] = (np.array(self.host.scene['meshes'][0]['vertices']) + [8,0,0]).tolist()
        forward = self.pair(['center_delta'])['facts']['center_delta']['value']
        reverse = self.observe(['center_delta'], [{'name':'base'}, {'name':'part'}])['facts']['center_delta']['value']
        self.assertEqual(forward, [-8.,0.,0.])
        np.testing.assert_array_equal(np.array(reverse), -np.array(forward))

    def test_query_prevalidation_rejects_ambiguous_shapes_and_unknown_facts(self):
        cases = [self.query(objects=[{'name':'part','id':'part'}]),
                 self.query(facts=['invented']), self.query(facts=['aabb','aabb']),
                 self.query(facts=['surface_clearance']), {**self.query(), 'max_exact_pairs':2}]
        for query in cases:
            with self.subTest(query=query), self.assertRaises(ValueError): validate_query(query)

    def test_same_object_pair_is_field_unknown(self):
        result = self.observe(['surface_clearance'], [{'id':'part'},{'name':'part'}])
        self.assertEqual(result['facts']['surface_clearance']['reason'], 'pair_selectors_resolve_to_same_object')
        self.assertEqual(result['work']['exact_pair_count'], 0)

    def test_selector_byte_limit_rejected_before_capture(self):
        for value in ('x'*257, '名'*86):
            with self.assertRaisesRegex(ValueError, '256 UTF-8 bytes'):
                self.observe(objects=[{'name':value}])
        self.assertEqual(self.host.captures, 0)

    def test_long_host_names_fail_explicit_body_budget_without_trimming(self):
        self.host.scene['meshes'][1]['name'] = 'x'*5000
        result = self.observe(objects=[{'id':'part'}])
        self.assertEqual(result['facts']['aabb'][0]['status'], 'measured')
        with self.assertRaisesRegex(ValueError, 'task_result_body_budget_exceeded'):
            _tool_result(result, is_error=False)

    def test_mcp_encodes_only_selected_body_once_without_deepcopy(self):
        result = self.pair(['surface_clearance'])
        original = json.dumps; calls = []
        def count(value, **kwargs): calls.append(value); return original(value, **kwargs)
        with patch('human_eye_plugin.live_spatial_mcp.json.dumps', side_effect=count),\
             patch('human_eye_plugin.live_spatial_mcp.copy.deepcopy', side_effect=AssertionError('unused copy')):
            response = _tool_result(result, is_error=False, response_detail='brief')
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(response['content'][0]['text']), result)
        self.assertLess(len(response['content'][0]['text'].encode('utf8')), 4096)

    def test_four_object_overview_body_budget(self):
        for i in range(2): self.host.scene['meshes'].append(mesh('extra'+str(i),[2+i,0,0],[1,1,1]))
        result = self.observe(objects=[{'id':m['object_id']} for m in self.host.scene['meshes']])
        body = _tool_result(result, is_error=False)['content'][0]['text']
        self.assertLessEqual(len(body.encode('utf8')), 2048)

    def test_four_object_float32_like_blender_bounds_budget_without_rounding(self):
        self.host.scene['meshes'] = [mesh('Object_'+str(i),[i*.1234567,-.3765432,.4891234],[.3923456,.433333,.678901]) for i in range(4)]
        for item in self.host.scene['meshes']:
            item['vertices'] = np.asarray(item['vertices'], dtype=np.float32).astype(float).tolist()
        result = self.observe(objects=[{'name':m['name']} for m in self.host.scene['meshes']])
        body = _tool_result(result, is_error=False)['content'][0]['text']
        self.assertLessEqual(len(body.encode('utf8')), 2048)
        for raw, fact in zip(self.host.scene['meshes'], result['facts']['aabb']):
            np.testing.assert_array_equal(fact['value']['min'], np.asarray(raw['vertices']).min(axis=0))

    def test_service_prevalidation_no_capture_for_incompatible_options(self):
        for extra in ({'include_image':True}, {'focal_id':'part'}, {'reference_id':'base'}, {'goal':{}}):
            options = {'include_image':False, **extra}
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.service.observe('s', query=self.query(), **options)
        self.assertEqual(self.host.captures, 0)

    def test_does_not_reuse_prior_write_prepare_context(self):
        self.service.observe('s', focal_id='part', reference_id='base', include_image=False)
        self.assertTrue(json.loads((self.base/'state.json').read_text())['runtime']['sessions'])
        self.observe()
        self.assertFalse(json.loads((self.base/'state.json').read_text())['runtime']['sessions'])
        self.assertEqual(self.host.calls, 0)

    def test_mcp_task_response_and_expired_publication(self):
        args = {'include_image':False, 'query':self.query()}
        response = self.server._call_tool('human_eye_scene_observe', args)
        self.assertFalse(response['isError'])
        self.assertEqual(json.loads(response['content'][0]['text'])['result_kind'], 'task_query')
        original = self.service._check_request_budget
        def expire(stage):
            if stage == 'before_task_publication': raise ValueError('expired at publication')
            return original(stage)
        with patch.object(self.service, '_check_request_budget', side_effect=expire):
            with self.assertRaisesRegex(ValueError, 'expired at publication'):
                self.server._call_tool('human_eye_scene_observe', args)

    def test_original_budget_still_applies_during_mcp_encoding(self):
        import time
        from human_eye_plugin.live_service import _REQUEST_BUDGET, RequestBudgetError
        self.service.request_budget_s = 20.
        args = {'include_image':False, 'query':self.query()}
        original = _tool_result
        def expire(*values, **kwargs):
            self.assertIsNotNone(_REQUEST_BUDGET.get())
            _REQUEST_BUDGET.get()['deadline'] = time.monotonic() - 1
            return original(*values, **kwargs)
        with patch('human_eye_plugin.live_spatial_mcp._tool_result', side_effect=expire):
            with self.assertRaises(RequestBudgetError): self.server._call_tool('human_eye_scene_observe', args)


if __name__ == '__main__': unittest.main()
