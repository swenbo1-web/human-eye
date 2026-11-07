"""Twelve preregistered offline classes. Stubs are not Blender evidence."""
import contextlib
import hashlib
import io
import itertools
import json
import math
from fractions import Fraction as F
from pathlib import Path
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from verification.test_blender_host_contracts import FakeObject, host_fixture, matrix, _module as m
from verification.test_blender_mcp_host import _server, _reply
from human_eye_plugin.blender_mcp_host import BlenderMCPHost, RPC_PREFIX

ROOT = Path(__file__).resolve().parents[1]
m._READONLY_LOADED_HOST_SHA256 = hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()


class TriangleObject(FakeObject):
    def __init__(self, name, x=0., uid=101):
        super().__init__(name, (x, 0, 0))
        self.session_uid, self.is_evaluated = uid, True
        self.eval_calls = self.mesh_calls = 0
        self.data.vertices = [NS(co=p) for p in ((0., 0., 0.), (0., 1., 0.), (0., 0., 1.))]
        self.data.polygons = [NS(vertices=(0, 1, 2))]
        self.data.loops = [None] * 3
        self.data.loop_triangles = [NS(vertices=(0, 1, 2))]
        self.bound_box = list(itertools.product((0., 0.), (0., 1.), (0., 1.)))

    def evaluated_get(self, graph):
        self.eval_calls += 1
        return self

    def to_mesh(self):
        self.mesh_calls += 1
        return super().to_mesh()


def fixture(xs=(0., 2., 100.), scale=1.):
    host, _, _, graph = host_fixture(scale)
    objects = [TriangleObject('O%d' % i, x, 101+i) for i, x in enumerate(xs)]
    host.scene.objects = objects
    host.scene.session_uid = 77
    host.bpy.app = NS(driver_namespace={})
    host.view_layer.objects.active = objects[0]
    host.updates = 0
    def update():
        host.updates += 1
    host.view_layer.update = update
    host.identity_metadata = True
    return host, objects


def capture(host, **kwargs):
    return host.capture_nearest_candidates(host.object_id(host.scene.objects[0]),
        kwargs.get('deadline_ns', time.perf_counter_ns()+10_000_000_000), kwargs.get('max_response_bytes', 1_000_000))


def enclosed(test, bounds, point):
    test.assertIsNotNone(bounds)
    for k in range(3):
        test.assertLessEqual(F(bounds[0][k]), point[k])
        test.assertLessEqual(point[k], F(bounds[1][k]))


def row(packet, host, obj):
    return next(item for item in packet['coverage'] if item['object_id'] == host.object_id(obj))


class M4Capture001(unittest.TestCase):
    def test_01_far_pruning(self):
        host, objs = fixture()
        packet = capture(host)
        self.assertEqual(packet['work']['expanded_objects'], 2)
        self.assertEqual([o.mesh_calls for o in objs], [1, 1, 0])
        self.assertEqual(row(packet, host, objs[2])['disposition'], 'excluded_strict_bound')
        self.assertGreater(row(packet, host, objs[2])['lower_bound_m'], packet['witness_upper_bound_m'])
        self.assertFalse(packet['execution_authority'])
        self.assertEqual(packet['capture']['capture_scope'], 'surface_nearest_candidates')
        full = host.capture_scene()
        full_by_id = {x['object_id']: x for x in full['meshes']}
        for mesh in packet['capture']['meshes']:
            self.assertEqual(mesh['vertices'], full_by_id[mesh['object_id']]['vertices'])
            self.assertEqual(mesh['faces'], full_by_id[mesh['object_id']]['faces'])
        self.assertEqual([o.assignments for o in objs], [0, 0, 0])

    def test_02_all_overlap(self):
        host, objs = fixture((0., 0., 0., 0.))
        packet = capture(host)
        self.assertTrue(all(x['disposition'] == 'retained' for x in packet['coverage']))
        self.assertEqual(len(packet['capture']['meshes']), 4)
        self.assertEqual([o.mesh_calls for o in objs], [1]*4)

    def test_03_ties_and_strict_equality(self):
        host, objs = fixture((0., 2., 2.))
        packet = capture(host)
        self.assertEqual(len(packet['capture']['meshes']), 3)
        upper = packet['witness_upper_bound_m']
        # Independent decision-boundary injection, not a numeric enclosure test.
        with patch.object(m, '_acquisition_lower', return_value=upper):
            equal = capture(host)
        self.assertTrue(all(x['disposition'] == 'retained' for x in equal['coverage']))

    def test_04_zero(self):
        host, objs = fixture((0., 0., 0., 100.))
        packet = capture(host)
        self.assertEqual(packet['witness_upper_bound_m'], 0.)
        self.assertEqual([row(packet, host, obj)['disposition'] for obj in objs],
                         ['retained', 'retained', 'retained', 'excluded_strict_bound'])

    def test_05_rotated_nonuniform(self):
        host, objs = fixture()
        transform = [[0., -3., .125, 8.], [2., 0., .5, -4.], [.25, 0., .75, 16.], [0., 0., 0., 1.]]
        objs[0]._matrix_world = transform
        bounds = m._acquisition_bounds(objs[0].bound_box, transform, .01)
        for point in objs[0].bound_box + [v.co for v in objs[0].data.vertices]:
            exact = [(sum(F(transform[r][c])*F(point[c]) for c in range(3))+F(transform[r][3]))*F(.01) for r in range(3)]
            enclosed(self, bounds, exact)
        packet = capture(host)
        focal_mesh = next(x for x in packet['capture']['meshes'] if x['object_id'] == host.object_id(objs[0]))
        for point in focal_mesh['vertices']:
            enclosed(self, row(packet, host, objs[0])['bounds_world_m'], list(map(F, point)))

    def test_06_numeric_oracle(self):
        transforms = [
            (matrix((2.**50, -2.**50, 2.**50), (2.**-20, 3., -7.)), 2.**-80),
            ([[2.**200, -2.**200, .125, -2.**100], [1., -1., 1., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]], 2.**-100),
            (matrix((0., 0., 0.), (2.**-1000, 2.**-1000, 2.**-1000)), 2.**-50),
        ]
        corners = list(itertools.product((-.5, 1.), (-1., 2.), (-2., 3.)))
        for transform, scale in transforms:
            with self.subTest(scale=scale):
                bounds = m._acquisition_bounds(corners, transform, scale)
                for point in corners + [(0., 0., 0.)]:
                    exact = [(sum(F(transform[r][c])*F(point[c]) for c in range(3))+F(transform[r][3]))*F(scale) for r in range(3)]
                    enclosed(self, bounds, exact)
                    actual = [(sum(transform[r][c]*point[c] for c in range(3))+transform[r][3])*scale for r in range(3)]
                    enclosed(self, bounds, list(map(F, actual)))
        for a, b in [([0., 0., 0.], [2., 3., 4.]), ([2.**100]*3, [math.nextafter(2.**100, math.inf), 2.**100, 0.]),
                     ([0., 0., 0.], [2.**-1074, 0., 0.])]:
            distance2 = sum((F(x)-F(y))**2 for x, y in zip(a, b))
            self.assertGreaterEqual(F(m._acquisition_upper(a, b))**2, distance2)
            lower = m._acquisition_lower([a, a], [b, b])
            self.assertLessEqual(F(lower)**2, distance2)

    def test_07_invalid_bounds(self):
        for box in [[], None, [(-1., -1., -1.)]*8, [(math.inf, 0., 0.)]*8, [(0., 0., 0.)]*7,
                    [(0., 0., 0.)]*7+[(1., 1., 1.)]]:
            with self.subTest(box=box):
                host, objs = fixture()
                objs[2].bound_box = box
                packet = capture(host)
                self.assertEqual(row(packet, host, objs[2])['bounds_status'], 'unknown')
                self.assertEqual(objs[2].mesh_calls, 1)
        class UnavailableBox(TriangleObject):
            @property
            def bound_box(self): raise RuntimeError('unavailable evaluated box')
        host, objs = fixture()
        objs[2].__class__ = UnavailableBox
        packet = capture(host)
        self.assertEqual(row(packet, host, objs[2])['bounds_status'], 'unknown')
        self.assertEqual(objs[2].mesh_calls, 1)

    def test_08_real_triangle_witness(self):
        host, objs = fixture((0., 2., 100.))
        objs[2].data.vertices.insert(0, NS(co=(-100., 0., 0.)))
        objs[2].data.polygons = [NS(vertices=(1, 2, 3))]
        objs[2].data.loop_triangles = [NS(vertices=(1, 2, 3))]
        objs[2].bound_box = list(itertools.product((-100., 0.), (0., 1.), (0., 1.)))
        packet = capture(host)
        self.assertEqual(row(packet, host, objs[2])['witness']['triangle_vertex_indices'], [1, 2, 3])
        self.assertEqual(row(packet, host, objs[2])['witness']['point_world_m'][0], 100.)
        self.assertEqual(packet['upper_seed_id'], host.object_id(objs[1]))
        host, objs = fixture()
        objs[0].data.vertices[2].co = (0., 2., 0.)
        packet = capture(host)
        self.assertIsNone(packet['witness_upper_bound_m'])
        self.assertEqual(packet['work']['expanded_objects'], 3)
        host, objs = fixture()
        objs[2].data.vertices[2].co = (0., 2., 0.)
        packet = capture(host)
        self.assertEqual(row(packet, host, objs[2])['disposition'], 'retained')
        self.assertIn(host.object_id(objs[2]), packet['unresolved_witness_ids'])

    def test_09_reject_unsupported(self):
        variants = [('modifier', 'static_triangle_source'), ('parent', 'static_triangle_source'),
                    ('animation', 'static_triangle_source'), ('shape', 'static_triangle_source'),
                    ('evaluation', 'evaluation_unavailable'), ('loops', 'triangle_data_required')]
        for kind, reason in variants:
            with self.subTest(kind=kind):
                host, objs = fixture()
                if kind == 'modifier': objs[2].modifiers = [NS(type='BEVEL', name='B')]
                elif kind == 'parent': objs[2].parent = objs[0]
                elif kind == 'animation': objs[2].animation_data = NS()
                elif kind == 'shape': objs[2].data.shape_keys = NS()
                elif kind == 'evaluation': objs[2].is_evaluated = False
                else: objs[2].data.loops = []
                with self.assertRaisesRegex(m.BlenderHostError, reason): capture(host)
                self.assertEqual(sum(o.mesh_calls for o in objs), 0)

    def test_10_legacy_and_transport(self):
        host, objs = fixture()
        with patch.object(host, 'capture_nearest_candidates', side_effect=AssertionError('must bypass')):
            host.capture_scene()
            task = host.capture_task_scene([{'name': 'O0'}, {'name': 'O1'}])
        self.assertEqual(len(task['meshes']), 2)
        connector = BlenderMCPHost(ROOT)
        params = {'focal_id': host.object_id(objs[0]), 'deadline_ns': time.perf_counter_ns()+10_000_000_000,
                  'max_response_bytes': 1_000_000}
        code = connector._code('capture_nearest_candidates', params, 'fixed-request')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            exec(compile(code, '<typed-acquisition>', 'exec'), {'bpy': host.bpy})
        response = json.loads(output.getvalue()[len(RPC_PREFIX):])
        self.assertNotIn('error', response, response)
        self.assertEqual(response['result']['protocol'], 'single-read-surface-candidates-v1')
        with _server(lambda request: _reply(request, response['result'])) as (port, requests):
            transport = BlenderMCPHost(ROOT, port=port)
            with transport.observation_transaction():
                packet = transport.capture_nearest_candidates(**params)
            self.assertEqual(packet, response['result'])
        self.assertEqual(requests[0][1]['command'], 'capture_nearest_candidates')
        self.assertIn('_host.capture_nearest_candidates(**', requests[0][0]['params']['code'])

    def test_11_same_read_coverage(self):
        host, objs = fixture()
        objs[2].hide_viewport = objs[2].hide_render = True
        packet = capture(host)
        self.assertEqual(host.updates, 1)
        self.assertEqual([o.eval_calls for o in objs], [1, 1, 1])
        self.assertEqual([r['object_id'] for r in packet['coverage']], sorted(host.object_id(o) for o in objs))
        self.assertTrue(packet['binding']['same_main_thread_read'])
        host, objs = fixture()
        original = objs[0].to_mesh
        def mutate():
            objs[2].session_uid += 500
            return original()
        objs[0].to_mesh = mutate
        with self.assertRaisesRegex(m.BlenderHostError, 'source_changed'): capture(host)
        self.assertEqual(objs[0].clears, 1)

    def test_12_cumulative_budgets(self):
        connector = BlenderMCPHost(ROOT, timeout_s=.001)
        sent = []
        def request(command, params):
            sent.append(params.copy())
            return {'protocol': 'single-read-surface-candidates-v1', 'focal_id': 'focus',
                    'execution_authority': False,
                    'binding': {'host_source_sha256': connector._readonly_host_source_sha256}}
        with patch.object(m.time, 'perf_counter_ns', return_value=1000), patch.object(connector, '_request', side_effect=request):
            connector.capture_nearest_candidates('focus', 10_000_000_000, 1000)
            connector.capture_nearest_candidates('focus', 1001, 1000)
        self.assertEqual([p['deadline_ns'] for p in sent], [1_001_000, 1001])
        host, objs = fixture()
        with self.assertRaisesRegex(m.BlenderHostError, 'document_budget_exceeded'):
            capture(host, max_response_bytes=1)
        self.assertEqual([o.clears for o in objs], [1, 1, 0])
        host, objs = fixture()
        with self.assertRaisesRegex(m.BlenderHostError, 'deadline_exceeded'):
            capture(host, deadline_ns=1)
        self.assertEqual(sum(o.mesh_calls for o in objs), 0)
        class SizedVertices:
            def __init__(self, points): self.points = points
            def __len__(self): return 250_001
            def __getitem__(self, key): return self.points[key]
        host, objs = fixture((0., 2.))
        for o in objs: o.data.vertices = SizedVertices(o.data.vertices)
        with self.assertRaisesRegex(m.BlenderHostError, 'scene_geometry_budget'): capture(host)
        self.assertEqual(sum(o.mesh_calls for o in objs), 0)
        host, objs = fixture()
        def fail(): raise RuntimeError('triangulation failed')
        objs[0].data.calc_loop_triangles = fail
        with self.assertRaisesRegex(RuntimeError, 'triangulation failed'): capture(host)
        self.assertEqual(objs[0].clears, 1)
        host, objs = fixture()
        deadline = time.perf_counter_ns()+10_000_000_000
        now = [deadline-1]
        dumps = json.dumps
        def expire_at_publish(value, *args, **kwargs):
            result = dumps(value, *args, **kwargs)
            if isinstance(value, dict) and value.get('protocol') == 'single-read-surface-candidates-v1':
                now[0] = deadline
            return result
        with patch.object(m.time, 'perf_counter_ns', side_effect=lambda: now[0]), patch.object(m.json, 'dumps', side_effect=expire_at_publish):
            with self.assertRaisesRegex(m.BlenderHostError, 'deadline_exceeded'):
                capture(host, deadline_ns=deadline)


if __name__ == '__main__':
    unittest.main()
