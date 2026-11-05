"""Independent analytic task facts and boundary counterexamples; no Blender."""
import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import random
import struct
import sys
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

    def work(self):
        events = [json.loads(line) for line in self.service.audit_path.read_text(encoding='utf8').splitlines()]
        return [event['task_work'] for event in events if event['event'] == 'observe'][-1]

    def test_single_object_has_no_pair_or_unused_agent_work(self):
        self.host.scene['meshes'] = [self.host.scene['meshes'][1]]
        with patch('human_eye_plugin.task_query.measure_pair_geometry', side_effect=AssertionError('unused solver')),\
             patch('human_eye_plugin.agent_adapters.build_agent_observation', side_effect=AssertionError('unused messages')):
            result = self.observe()
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(self.host.captures, 1)
        self.assertEqual(self.host.calls, 0)
        self.assertEqual(self.work()['exact_pair_count'], 0)
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
        self.assertEqual(self.work()['exact_pair_count'], 1)

    def test_only_one_pair_and_warm_cache_reuses_current_geometry(self):
        self.host.scene['meshes'].append(mesh('noise',[10,0,0],[1,1,1]))
        self.pair(['surface_clearance']); cold_work = self.work()
        self.pair(['surface_clearance']); warm_work = self.work()
        self.assertEqual(cold_work['exact_pair_count'], 1)
        self.assertEqual(warm_work['exact_pair_count'], 0)
        self.assertTrue(warm_work['pair_cache_hit'])
        self.assertEqual(self.host.captures, 2)

    def test_aabb_direction_never_runs_exact_pair(self):
        with patch('human_eye_plugin.task_query.measure_pair_geometry', side_effect=AssertionError('unused solver')):
            result = self.pair(['axis_gap','center_delta'])
        self.assertEqual(self.work()['exact_pair_count'], 0)

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
        self.assertEqual(self.work()['exact_pair_count'], 0)

    def test_selector_byte_limit_rejected_before_capture(self):
        for value in ('x'*257, '名'*86):
            with self.assertRaisesRegex(ValueError, '256 UTF-8 bytes'):
                self.observe(objects=[{'name':value}])
        self.assertEqual(self.host.captures, 0)

    def test_long_host_names_deliver_complete_facts_without_trimming(self):
        self.host.scene['meshes'][1]['name'] = 'x'*5000
        result = self.observe(objects=[{'id':'part'}])
        self.assertEqual(result['facts']['aabb'][0]['status'], 'measured')
        encoded = _tool_result(result, is_error=False)['content'][0]['text']
        self.assertEqual(json.loads(encoded), result)
        self.assertEqual(json.loads(encoded)['binding']['objects'][0]['name'], 'x'*5000)
        self.assertGreater(len(encoded.encode('utf8')), 2048)

    def test_v2_keeps_trace_link_and_audited_work_without_wrapper_construction(self):
        result = self.pair(['surface_clearance'])
        self.assertEqual(result['schema_version'], 'task-query-v2')
        self.assertNotIn('work', result)
        self.assertNotIn('request_trace', result)
        self.assertEqual(set(result['binding']['objects'][0]), {'object_id', 'name'})
        events = [json.loads(line) for line in self.service.audit_path.read_text(encoding='utf8').splitlines()]
        observe = next(event for event in events if event['event'] == 'observe')
        trace = next(event for event in events if event['event'] == 'request_trace')
        self.assertEqual(result['trace_id'], observe['trace_id'])
        self.assertEqual(result['trace_id'], trace['trace_id'])
        self.assertEqual(observe['task_work']['exact_pair_count'], 1)
        self.assertEqual(observe['request_id'], trace['request_id'])

    def test_preconstructed_v1_dictionary_keeps_its_original_schema_and_fields(self):
        value = {'result_kind': 'task_query', 'schema_version': 'task-query-v1',
            'facts': {'aabb': [{'status': 'unknown', 'value': None, 'reason': 'selector_unresolved'}]},
            'work': {'exact_pair_count': 0, 'pair_cache_hit': False},
            'request_trace': {'trace_id': 'old', 'model_usage': 'unknown'}}
        result = _tool_result(value, is_error=False)
        self.assertEqual(json.loads(result['content'][0]['text']), value)

    def test_task_correlation_remains_in_trace_without_response_echo(self):
        context = {'task_id': 'o1', 'task_run_id': 'one-run'}
        result = self.service.observe('s', query=self.query(), include_image=False, task_context=context)
        self.assertNotIn('request_trace', result)
        events = [json.loads(line) for line in self.service.audit_path.read_text(encoding='utf8').splitlines()]
        trace = next(event for event in events if event['event'] == 'request_trace')
        self.assertEqual(result['trace_id'], trace['trace_id'])
        for key, value in context.items():
            self.assertEqual(trace['trace']['correlation'][key], value)

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

    def test_four_object_ordinary_name_suffix_preserves_fixed_target_and_all_facts(self):
        self.host.scene['meshes'] = [mesh('Object_'+str(i)+'_a',
            [i*.1234567,-.3765432,.4891234],[.3923456,.433333,.678901]) for i in range(4)]
        for item in self.host.scene['meshes']:
            item['vertices'] = np.asarray(item['vertices'], dtype=np.float32).astype(float).tolist()
        args = {'include_image': False, 'query': self.query(objects=[{'name': item['name']}
            for item in self.host.scene['meshes']])}
        reply = self.server._call_tool('human_eye_scene_observe', args)
        body = reply['content'][0]['text']
        self.assertFalse(reply['isError'])
        self.assertLessEqual(len(body.encode('utf8')), 2048)
        decoded = json.loads(body)
        self.assertEqual([row['name'] for row in decoded['binding']['objects']],
            [item['name'] for item in self.host.scene['meshes']])
        for raw, fact in zip(self.host.scene['meshes'], decoded['facts']['aabb']):
            vertices = np.asarray(raw['vertices'])
            self.assertEqual(fact['status'], 'measured')
            self.assertEqual(fact['value']['min'], vertices.min(axis=0).tolist())
            self.assertEqual(fact['value']['max'], vertices.max(axis=0).tolist())
            self.assertEqual(fact['value']['dimensions'], (vertices.max(axis=0)-vertices.min(axis=0)).tolist())

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


def center_delta_oracle(endpoints):
    """Exact binary64 endpoints, with one final round-to-nearest conversion."""
    a0, a1, b0, b1 = map(Fraction.from_float, endpoints)
    exact = (b0 + b1 - a0 - a1) / 2
    try:
        rounded = float(exact)
    except OverflowError:
        return None, 'world_arithmetic_not_finite'
    if exact and rounded == 0:
        return None, 'world_arithmetic_below_float_resolution'
    return rounded, None


CENTER_ENDPOINT_CASES = (
    ('origin', (0., 2., 2., 4.)),
    ('large_translation', (1e16, 1e16 + 2., 1e16 + 2., 1e16 + 4.)),
    ('negative_translation', (-1e16 - 4., -1e16 - 2., -1e16 - 2., -1e16)),
    ('opposite_signs', (-4., -2., 2., 4.)),
    ('half_ulp_midpoints', (1., math.nextafter(1., math.inf),
        math.nextafter(1., math.inf), 1. + 2. * math.ulp(1.))),
    ('near_overflow_finite', (sys.float_info.max / 2., sys.float_info.max,
        sys.float_info.max / 2., sys.float_info.max)),
    ('intermediate_overflow', (-sys.float_info.max, sys.float_info.max,
        sys.float_info.max, sys.float_info.max)),
    ('true_overflow', (-sys.float_info.max, -sys.float_info.max,
        sys.float_info.max, sys.float_info.max)),
    ('subnormal_measured', (0., math.ulp(0.), math.ulp(0.), 2. * math.ulp(0.))),
    ('subnormal_unrepresentable', (0., 0., 0., math.ulp(0.))),
    ('subnormal_exact_zero', (-math.ulp(0.), math.ulp(0.), 0., 0.)),
    ('normal_boundary', (sys.float_info.min, math.nextafter(sys.float_info.min, math.inf),
        math.nextafter(sys.float_info.min, math.inf), sys.float_info.min + 2. * math.ulp(0.))),
)


def center_scene(endpoints, axis=0):
    """Assign represented endpoint bytes directly, avoiding a midpoint builder."""
    scene = {'revision': 'center-r1', 'unit': 'm', 'coordinate_frame': 'world',
             'source': 'test_host', 'meshes': []}
    for name, low, high in (('A', *endpoints[:2]), ('B', *endpoints[2:])):
        item = mesh(name, [0., 0., 0.], [2., 2., 2.])
        for vertex in item['vertices']:
            vertex[axis] = low if vertex[axis] < 0 else high
        scene['meshes'].append(item)
    return scene


class CenterDeltaNumericsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = Path(self.temp.name) / 'live.json'
        config.write_text(json.dumps({'schema_version': '1.0', 'enabled': True,
            'project_root': str(Path(__file__).resolve().parents[1]), 'quad_size': 64,
            'state_file': 'state.json', 'audit_file': 'audit.jsonl'}), encoding='utf8')
        self.host = SelfLockingHost()
        self.server = LiveSpatialMCPServer(LiveSpatialService(config, host=self.host), 'center-tests')

    def read_case(self, endpoints, axis=0, reverse=False):
        self.host.scene = center_scene(endpoints, axis)
        names = ('B', 'A') if reverse else ('A', 'B')
        with np.errstate(over='ignore', under='ignore', invalid='ignore'):
            reply = self.server._call_tool('human_eye_scene_observe', {'include_image': False,
                'query': {'mode': 'task', 'objects': [{'name': name} for name in names],
                          'requested_facts': ['aabb', 'center_delta', 'axis_gap']}})
        self.assertFalse(reply['isError'])
        return json.loads(reply['content'][0]['text'])

    def test_endpoint_oracle_at_mcp_boundary_all_axes_and_orders(self):
        captures = 0
        for label, endpoints in CENTER_ENDPOINT_CASES:
            for axis in range(3):
                for reverse in (False, True):
                    with self.subTest(case=label, axis=axis, reverse=reverse):
                        ordered = endpoints[2:] + endpoints[:2] if reverse else endpoints
                        expected, reason = center_delta_oracle(ordered)
                        body = self.read_case(endpoints, axis, reverse)
                        fact = body['facts']['center_delta']
                        if reason:
                            self.assertEqual(fact['status'], 'unknown')
                            self.assertIsNone(fact['value'])
                            self.assertEqual(fact['reason'], reason)
                            self.assertEqual(body['status'], 'partial')
                            self.assertTrue(any(row['status'] == 'measured' for row in body['facts']['aabb']))
                        else:
                            vector = [0., 0., 0.]
                            vector[axis] = expected
                            self.assertEqual(fact['status'], 'measured')
                            self.assertEqual(fact['value'], vector)
                        self.assertNotIn('work', body)
                        self.assertFalse(body['execution_authority'])
                    captures += 1
        self.assertEqual(self.host.captures, captures)
        self.assertEqual(self.host.calls, 0)
        events = [json.loads(line) for line in self.server.service.audit_path.read_text(encoding='utf8').splitlines()]
        work = [row['task_work'] for row in events if row['event'] == 'observe']
        self.assertEqual(len(work), captures)
        self.assertTrue(all(row['exact_pair_count'] == 0 for row in work))

    def test_unrepresentable_center_keeps_other_known_facts(self):
        endpoints = dict(CENTER_ENDPOINT_CASES)['subnormal_unrepresentable']
        body = self.read_case(endpoints)
        self.assertEqual(body['facts']['axis_gap']['status'], 'measured')
        self.assertEqual(body['facts']['axis_gap']['value'], [0., 0., 0.])
        self.assertTrue(all(row['status'] == 'measured' for row in body['facts']['aabb']))
        self.assertEqual(body['facts']['aabb'][1]['value']['max'][0], math.ulp(0.))

    def test_simultaneous_three_axis_translation(self):
        self.host.scene = center_scene((1e16, 1e16 + 2., 1e16 + 2., 1e16 + 4.))
        for item in self.host.scene['meshes']:
            for vertex in item['vertices']:
                vertex[1] = -vertex[0]
                vertex[2] = vertex[0]
        reply = self.server._call_tool('human_eye_scene_observe', {'include_image': False,
            'query': {'mode': 'task', 'objects': [{'name': 'A'}, {'name': 'B'}],
                      'requested_facts': ['center_delta']}})
        fact = json.loads(reply['content'][0]['text'])['facts']['center_delta']
        self.assertEqual(fact['status'], 'measured')
        self.assertEqual(fact['value'], [2., -2., 2.])

    def test_normal_and_large_coordinates_do_not_need_fraction_fallback(self):
        with patch('fractions.Fraction', side_effect=AssertionError('unnecessary exact fallback')):
            for label, endpoints in CENTER_ENDPOINT_CASES[:6]:
                with self.subTest(case=label):
                    self.assertEqual(self.read_case(endpoints)['facts']['center_delta']['status'], 'measured')

    def test_fixed_seed_finite_endpoints_against_exact_oracle(self):
        from human_eye_plugin.task_query import task_result
        from types import SimpleNamespace
        rng = random.Random(703)
        for index in range(2000):
            values = []
            while len(values) < 4:
                value = struct.unpack('>d', rng.getrandbits(64).to_bytes(8, 'big'))[0]
                if math.isfinite(value):
                    values.append(value)
            endpoints = (*sorted(values[:2]), *sorted(values[2:]))
            expected, reason = center_delta_oracle(endpoints)
            meshes = [SimpleNamespace(object_id=name, bbox_min=np.array([low, 0., 0.]),
                bbox_max=np.array([high, 0., 0.]))
                for name, low, high in (('A', *endpoints[:2]), ('B', *endpoints[2:]))]
            result = task_result({'revision': 'fuzz', 'source': 'test_host',
                'meshes': [{'object_id': name, 'name': name} for name in ('A', 'B')]},
                meshes, 'fuzz', {'objects': [{'name': 'A'}, {'name': 'B'}],
                'requested_facts': ['center_delta']}, None, lambda stage: None)
            fact = result['facts']['center_delta']
            with self.subTest(index=index, endpoints=endpoints):
                if reason:
                    self.assertEqual(fact['status'], 'unknown')
                    self.assertEqual(fact['reason'], reason)
                else:
                    self.assertEqual(fact['status'], 'measured')
                    self.assertEqual(fact['value'], [expected, 0., 0.])


if __name__ == '__main__': unittest.main()
