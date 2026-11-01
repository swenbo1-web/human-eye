"""Complete finite-decision checks and separate capability admission."""
import ast
import copy
import hashlib
import subprocess
import sys
import time
import tempfile
from types import ModuleType
import unittest
from pathlib import Path
from unittest.mock import patch

from human_eye_plugin import nonplanar_focus as producer, nonplanar_replay as consumer
from human_eye_plugin import nonplanar_observation as envelope
from human_eye_plugin.blender_host import BlenderSceneHost, _NONPLANAR_FOCUS_SHA256
from verification.nonplanar_dense_fixtures import dense_cases, dense_source, dense_case

ROOT = Path(__file__).resolve().parents[1]


def example(case=None):
    case = case or dense_cases()[1]
    native, edges = dense_source(case)
    deadline = time.perf_counter_ns()+30_000_000_000
    plan = producer.choose(native, 'target', edges, deadline,
        locality_policy='visual_nearplanar', acceleration='auto')
    return plan, native, edges, deadline


class NonplanarProtocolTests(unittest.TestCase):
    def test_all_reliable_decisions_independently_reconstructed(self):
        for case in dense_cases():
            with self.subTest(case=case['id']):
                plan, native, edges, deadline = example(case)
                work, overview, detail = consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', deadline)
                self.assertEqual(detail is not None, case['want'])
                self.assertLessEqual(work, 8192)

    def test_schema_extra_and_policy_tampering_refused(self):
        for key, value in [('schema', 'old'), ('search_complete', False), ('execution_authority', True),
            ('max_triangle_tests', 9000), ('locality_policy', 'strict_coplanar'), ('maximum_images', 3),
            ('max_locality_work', 99999), ('binding_scope', 'unbound'), ('extra', 1)]:
            plan, native, edges, deadline = example(); plan[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', deadline)

    def test_basis_projection_and_frame_tampering_refused(self):
        for key in ('direction','right','up','center','span','overview_span','projection','detail_frame'):
            plan, native, edges, deadline = example(); row = plan['selected']
            if key == 'projection':row[key]['overview_px'] += 1
            elif key == 'detail_frame':row[key]['camera_location_bu'][0] += 1
            elif type(row[key]) is list:row[key][0] += .01
            else:row[key] += .01
            with self.subTest(key=key), self.assertRaises(ValueError):
                consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', deadline)

    def test_omitted_candidates_and_suppressed_gain_refused(self):
        for mutation in ('omit','reason','selected','samples','visible'):
            plan, native, edges, deadline = example()
            if mutation == 'omit':plan['candidates'].pop()
            elif mutation == 'reason':plan['selected']['reason'] = 'no_projection_gain'
            elif mutation == 'selected':plan['selected'] = None
            elif mutation == 'samples':plan['selected']['samples'] = []
            else:plan['selected']['samples'][0]['visible'] = not plan['selected']['samples'][0]['visible']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', deadline)

    def test_all_work_counters_and_features_refused_when_changed(self):
        for key in ('combined_box_tests_reserved','combined_projection_ops_reserved','combined_triangle_tests_reserved',
                    'locality_work_reserved','sampling_features'):
            plan, native, edges, deadline = example()
            if key == 'sampling_features':plan[key].pop()
            else:plan[key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', deadline)

    def test_wrong_acceleration_mode_and_query_ledger_refused(self):
        for mutation in ('mode','query','index','reservation','prune'):
            plan, native, edges, deadline = example(dense_case(12))
            row = next(r for r in plan['candidates'] if 'acceleration' in r)
            mode = 'nonplanar_dense_v1'
            if mutation == 'mode':mode = 'nonplanar_boundary_v1'
            elif mutation == 'query':row['samples'][0]['index_queries'].reverse()
            elif mutation == 'index':next(iter(row['acceleration']['indices'].values()))['extra'] = True
            elif mutation == 'reservation':plan['index_build_reservations'].pop()
            else:
                index = next(iter(row['acceleration']['indices'].values())); index['nodes'][0][0] = 1e9
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, IndexError)):
                consumer.decision(plan, native, 'target', edges, mode, deadline)

    def test_consumer_does_not_call_producer_algorithms(self):
        plan, native, edges, deadline = example(dense_case(12))
        with patch.object(producer, 'choose', side_effect=AssertionError('producer called')), \
             patch.object(producer, 'projected_hit', side_effect=AssertionError('producer ray called')), \
             patch.object(producer, 'canonical_boundary', side_effect=AssertionError('producer features called')):
            consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', deadline)

    def test_deadline_partial_and_wire_complexity_fail_closed(self):
        plan, native, edges, deadline = example()
        with self.assertRaisesRegex(ValueError, 'deadline'):
            consumer.decision(plan, native, 'target', edges, 'nonplanar_dense_v1', 1)
        for value in ({'plan': {'x': float('nan')}}, {'plan': [0]*16385}, {'plan': 2**200}):
            with self.assertRaises(ValueError):envelope.bounded_wire(value)
        recursive = {}; recursive['self'] = recursive
        with self.assertRaisesRegex(ValueError, 'wire_complexity'):envelope.bounded_wire(recursive)

    def test_partial_search_with_early_good_view_is_not_production_complete(self):
        native,edges=dense_source(dense_case(7));target=native['objects'][0]
        target['local_vertices']=copy.deepcopy(target['world_vertices'])
        matrix=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        target['matrix']=matrix
        prepared=dict(source={'object_id':'target'},raw=dict(vertices=target['local_vertices'],polygons=target['faces'],
            matrix_world=matrix,unit_scale=1.,edges=edges))
        patch_value=dict(category='boundary_edges',element_kind='edge',position={'status':'known'},source_indices=list(range(len(edges))))
        deadline=time.perf_counter_ns()+30_000_000_000
        partial=producer.choose(native,'target',edges,deadline,locality_policy='visual_nearplanar',acceleration='off')
        self.assertIsNotNone(partial['selected']);self.assertFalse(partial['search_complete'])
        with self.assertRaisesRegex(ValueError,'incomplete_search_requires_review'):
            producer.production_plan(prepared,patch_value,native,None,deadline,'nonplanar_boundary_v1')

    def test_protocol_checks_survive_optimized_python(self):
        code = """import sys,time
sys.path.insert(0,sys.argv[1])
from verification.test_nonplanar_protocol import example
from human_eye_plugin.nonplanar_replay import decision
p,n,e,d=example();p['combined_triangle_tests_reserved']=0
try:decision(p,n,'target',e,'nonplanar_dense_v1',d)
except ValueError:pass
else:raise RuntimeError('optimized checks removed')
"""
        subprocess.run([sys.executable,'-I','-B','-O','-c',code,str(ROOT)],check=True,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=12)

    def test_runtime_sources_are_self_contained_and_have_no_assert_checks(self):
        for name in ('nonplanar_focus','nonplanar_exact','nonplanar_replay','nonplanar_observation'):
            text=(ROOT/'human_eye_plugin'/f'{name}.py').read_text(encoding='utf8')
            tree=ast.parse(text)
            self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(tree)),name)
            for n in ast.walk(tree):
                if isinstance(n,ast.ImportFrom):self.assertFalse((n.module or '').startswith('verification'))
                if isinstance(n,ast.Import):self.assertFalse(any(a.name.startswith('verification') for a in n.names))

    def test_helper_pin_and_checked_dependency_free_load(self):
        self.assertEqual(hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest(),_NONPLANAR_FOCUS_SHA256)
        host=BlenderSceneHost.__new__(BlenderSceneHost)
        loaded=host._nonplanar_focus_module()
        self.assertEqual(loaded.PROTOCOL,envelope.PROTOCOL)
        self.assertEqual(loaded.MODES,envelope.MODES)
        self.assertIs(loaded,host._nonplanar_focus_module())

    def test_helper_warm_cache_cannot_hide_changed_source(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            for name in ('blender_host.py','nonplanar_focus.py'):
                (directory/name).write_bytes((ROOT/'human_eye_plugin'/name).read_bytes())
            module=ModuleType('_nonplanar_loader_test');module.__file__=str(directory/'blender_host.py')
            exec(compile((directory/'blender_host.py').read_bytes(),module.__file__,'exec'),module.__dict__)
            host=module.BlenderSceneHost.__new__(module.BlenderSceneHost)
            host._nonplanar_focus_module()
            with (directory/'nonplanar_focus.py').open('ab') as stream:stream.write(b'\n# changed\n')
            with self.assertRaisesRegex(ValueError,'nonplanar_source_mismatch'):
                host._nonplanar_focus_module()

    def test_typed_capability_changes_refused(self):
        host=BlenderSceneHost.__new__(BlenderSceneHost)
        caps=host.nonplanar_observation_capabilities();envelope.validate_capabilities(caps)
        for key,value in [('modes',[]),('helper_sha256','0'*64),('execution_authority',True),('protocol','old')]:
            changed=copy.deepcopy(caps);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):envelope.validate_capabilities(changed)

    def test_json_object_order_does_not_define_index_reservation_order(self):
        import json
        plan,native,edges,deadline=example(dense_case(12))
        plan=json.loads(json.dumps(plan,sort_keys=True))
        consumer.decision(plan,native,'target',edges,'nonplanar_dense_v1',deadline)

    def test_triangular_raw_native_correspondence_refuses_changed_faces(self):
        plan,native,edges,deadline=example()
        target=native['objects'][0];target['local_vertices']=copy.deepcopy(target['world_vertices'])
        raw=dict(vertices=copy.deepcopy(target['local_vertices']),polygons=copy.deepcopy(target['faces']),edges=edges,
            matrix_world=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]],unit_scale=1.)
        target['matrix']=copy.deepcopy(raw['matrix_world'])
        prepared={'raw':raw,'source':{'object_id':'target'}}
        patch_value=dict(category='boundary_edges',element_kind='edge',position={'status':'known'},source_indices=list(range(len(edges))))
        self.assertEqual(envelope.source_geometry(prepared,patch_value,native),edges)
        raw['polygons'].reverse()
        with self.assertRaisesRegex(ValueError,'triangle_correspondence'):
            envelope.source_geometry(prepared,patch_value,native)

    def test_unit_conversion_and_matrix_binding(self):
        native=dict(objects=[dict(object_id='target',faces=[[0,1,2]],
            local_vertices=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],world_vertices=[[2.,0.,0.],[3.,0.,0.],[2.,1.,0.]],
            matrix=[[1.,0.,0.,2.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]])])
        raw=dict(vertices=[[0.,0.,0.],[1000.,0.,0.],[0.,1000.,0.]],polygons=[[0,1,2]],edges=[[0,1],[1,2],[2,0]],unit_scale=.001,
            matrix_world=[[1.,0.,0.,2000.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]])
        prepared=dict(raw=raw,source={'object_id':'target'})
        p=dict(category='boundary_edges',element_kind='edge',position={'status':'known'},source_indices=[0,1,2])
        self.assertEqual(envelope.source_geometry(prepared,p,native),raw['edges'])
        self.assertEqual(producer.source_geometry(prepared,p,native),raw['edges'])
        native['objects'][0]['matrix'][2][2]=2.
        with self.assertRaisesRegex(ValueError,'matrix_correspondence'):envelope.source_geometry(prepared,p,native)


if __name__ == '__main__':unittest.main()
