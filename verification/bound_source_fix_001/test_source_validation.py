"""Directed acquisition source contracts; doubles are not Blender evidence.

Only enrich missing RNA fields in old doubles. The directed cases below call
the real product validator and public acquisition entry without that adapter.
"""
from collections import Counter
import math
import time
import unittest
from unittest.mock import patch

from verification.test_m4_capture_001 import fixture, capture, row, m, NS


def enrich_data(data):
    """Adapt legacy doubles only; never replace an existing RNA/error value.

    Parent regression runners may call this immediately before the real helper.
    In particular [] loops, explicit loop offsets/totals and explicit invalid
    vertex_index values remain unchanged. No product validator is bypassed.
    """
    offset = 0
    for face in data.polygons:
        indices = tuple(face.vertices)
        if not hasattr(face, 'loop_start'):
            face.loop_start = offset
        if not hasattr(face, 'loop_total'):
            face.loop_total = len(indices)
        for corner, index in enumerate(indices):
            slot = offset + corner
            if slot < len(data.loops) and data.loops[slot] is None:
                data.loops[slot] = NS(vertex_index=index)
        offset += len(indices)
    return data


def source_fixture(xs=(0., 2., 100.)):
    host, objects = fixture(xs)
    for obj in objects:
        enrich_data(obj.data)
    return host, objects


def second_face(obj, indices=(3, 4, 5)):
    obj.data.vertices.extend(NS(co=point) for point in ((0., 2., 0.), (0., 3., 0.), (0., 4., 0.)))
    obj.data.polygons.append(NS(vertices=tuple(indices), loop_start=3, loop_total=3))
    obj.data.loops.extend(NS(vertex_index=index) for index in indices)
    obj.data.loop_triangles.append(NS(vertices=tuple(indices)))
    obj.bound_box = [(x, y, z) for x in (0., 0.) for y in (0., 4.) for z in (0., 1.)]


def sentinel_native(obj):
    calls = Counter()
    def to_mesh():
        calls['to_mesh'] += 1
        raise AssertionError('bad source entered to_mesh')
    def triangulate():
        calls['calc_loop_triangles'] += 1
        raise AssertionError('bad source entered calc_loop_triangles')
    obj.to_mesh = to_mesh
    obj.data.calc_loop_triangles = triangulate
    return calls


class Coordinates:
    def __init__(self, values, index, observed):
        self.values, self.index, self.observed = values, index, observed
    def __getitem__(self, axis):
        self.observed['axis', self.index, axis] += 1
        return self.values[axis]


class ObservedVertex:
    def __init__(self, values, index, observed):
        self.values, self.index, self.observed = values, index, observed
    @property
    def co(self):
        self.observed['co', self.index] += 1
        return Coordinates(self.values, self.index, self.observed)


def helper_data(faces, points=None, observed=None):
    if points is None:
        points = [(0., 0., 0.), (0., 1., 0.), (0., 0., 1.)]
    observed = Counter() if observed is None else observed
    data = NS(vertices=[ObservedVertex(point, i, observed) for i, point in enumerate(points)],
              polygons=[], loops=[])
    for indices in faces:
        data.polygons.append(NS(vertices=tuple(indices), loop_start=len(data.loops), loop_total=len(indices)))
        data.loops.extend(NS(vertex_index=index) for index in indices)
    return data, observed


def validate(data, *, coordinates=True, checkpoint=lambda: None):
    return m._acquisition_validate_triangles(data, check_coordinates=coordinates,
                                             checkpoint=checkpoint, object_id='source-under-test')


class AcquisitionSourceValidation(unittest.TestCase):
    def test_each_disposition_validated_once_without_expanding_excluded_object(self):
        host, objects = source_fixture()
        second_face(objects[2])
        calls = []
        real = m._acquisition_validate_triangles
        def observe(data, **kwargs):
            calls.append((id(data), kwargs['check_coordinates']))
            return real(data, **kwargs)
        with patch.object(m, '_acquisition_validate_triangles', side_effect=observe):
            packet = capture(host)
        self.assertEqual(Counter(key for key, _ in calls), Counter({id(obj.data): 1 for obj in objects}))
        self.assertEqual(dict(calls), {id(obj.data): obj is objects[2] for obj in objects})
        self.assertEqual([obj.mesh_calls for obj in objects], [1, 1, 0])
        self.assertEqual(row(packet, host, objects[2])['disposition'], 'excluded_strict_bound')
        self.assertEqual(packet['result_kind'], 'acquisition_only_not_nearest_result')
        self.assertFalse(packet['execution_authority'])

    def test_later_invalid_index_in_all_four_roles_never_enters_native_expansion(self):
        for role in ('excluded', 'ordinary_retained', 'focal', 'seed'):
            with self.subTest(role=role):
                host, objects = source_fixture()
                bad = objects[{'focal': 0, 'seed': 1}.get(role, 2)]
                second_face(bad, (13, 4, 5))
                if role == 'ordinary_retained':
                    bad.bound_box = None
                native = sentinel_native(bad)
                with self.assertRaisesRegex(m.BlenderHostError, 'acquisition_invalid_triangle_indices:' + host.object_id(bad)):
                    capture(host)
                self.assertEqual(native, Counter(), 'source must fail before either native entry')
                self.assertEqual(bad.assignments, 0)

    def test_excluded_referenced_nan_is_rejected_in_real_acquisition_entry(self):
        host, objects = source_fixture()
        second_face(objects[2])
        objects[2].data.vertices[3].co = (math.nan, 2., 0.)
        native = sentinel_native(objects[2])
        with self.assertRaisesRegex(m.BlenderHostError, 'acquisition_nonfinite_referenced_vertex:' + host.object_id(objects[2])):
            capture(host)
        self.assertEqual(native, Counter())

    def test_mixed_face_lengths_with_same_total_loop_count_are_not_admitted(self):
        host, objects = source_fixture()
        second_face(objects[2])
        objects[2].data.polygons[0].loop_total = 2
        objects[2].data.polygons[1].loop_total = 4
        self.assertEqual(len(objects[2].data.loops), 3 * len(objects[2].data.polygons))
        native = sentinel_native(objects[2])
        with self.assertRaisesRegex(m.BlenderHostError, 'acquisition_invalid_triangle_structure:' + host.object_id(objects[2])):
            capture(host)
        self.assertEqual(native, Counter())

    def test_out_of_range_loop_starts_reject_before_native_expansion(self):
        for loop_start in (-1, 4, 6):
            with self.subTest(loop_start=loop_start):
                host, objects = source_fixture()
                second_face(objects[2])
                objects[2].data.polygons[1].loop_start = loop_start
                native = sentinel_native(objects[2])
                with self.assertRaisesRegex(m.BlenderHostError, 'acquisition_invalid_triangle_structure'):
                    capture(host)
                self.assertEqual(native, Counter())

    def test_all_indices_are_checked_before_any_helper_coordinate_dereference(self):
        data, observed = helper_data([(0, 1, 2), (0, 1, 13)])
        with self.assertRaisesRegex(m.BlenderHostError, 'acquisition_invalid_triangle_indices'):
            validate(data)
        self.assertEqual(observed, Counter())

    def test_shared_coordinates_are_checked_once_and_unreferenced_nan_is_unread(self):
        data, observed = helper_data([(0, 1, 2), (2, 0, 1)] * 200,
                                     points=[(0., 0., 0.), (0., 1., 0.), (0., 0., 1.), (math.nan, 0., 0.)])
        validate(data)
        expected_axes = Counter({('axis', i, axis): 1 for i in range(3) for axis in range(3)})
        self.assertEqual(Counter({key: value for key, value in observed.items() if key[0] == 'axis'}), expected_axes)
        self.assertEqual(observed['co', 3], 0)

    def test_retained_helper_does_not_read_coordinates(self):
        data, observed = helper_data([(0, 1, 2)], points=[(math.nan, 0., 0.), (0., 1., 0.), (0., 0., 1.)])
        validate(data, coordinates=False)
        self.assertEqual(observed, Counter())

    def test_retained_nan_reuses_original_capture_finite_check(self):
        host, objects = source_fixture()
        second_face(objects[0])
        objects[0].data.vertices[3].co = (math.nan, 2., 0.)
        with self.assertRaisesRegex(m.BlenderHostError, 'Nonfinite evaluated geometry'):
            capture(host)
        self.assertEqual(objects[0].mesh_calls, 1)
        self.assertEqual(objects[0].clears, 1)

    def test_finite_later_collinear_or_repeated_face_still_can_be_excluded(self):
        for indices in ((3, 4, 5), (3, 3, 3)):
            with self.subTest(indices=indices):
                host, objects = source_fixture()
                second_face(objects[2], indices)
                packet = capture(host)
                self.assertEqual(row(packet, host, objects[2])['disposition'], 'excluded_strict_bound')
                self.assertEqual(objects[2].mesh_calls, 0)

    def test_helper_entry_deadline_prevents_data_access(self):
        class NoData:
            def __getattribute__(self, key):
                raise AssertionError('data read after original deadline')
        def expired():
            raise m.BlenderHostError('acquisition_deadline_exceeded')
        with self.assertRaisesRegex(m.BlenderHostError, '^acquisition_deadline_exceeded$'):
            validate(NoData(), checkpoint=expired)

    def test_helper_face_scan_keeps_original_deadline_in_bounded_steps(self):
        data, _ = helper_data([(0, 1, 2)] * 1000)
        visited = [0]
        class Faces(list):
            def __iter__(self):
                for face in super().__iter__():
                    visited[0] += 1
                    yield face
        data.polygons = Faces(data.polygons)
        def expired():
            if visited[0] >= 256:
                raise m.BlenderHostError('acquisition_deadline_exceeded')
        with self.assertRaisesRegex(m.BlenderHostError, '^acquisition_deadline_exceeded$'):
            validate(data, checkpoint=expired)
        self.assertLessEqual(visited[0], 512)

    def test_helper_exit_deadline_is_not_turned_into_success(self):
        data, _ = helper_data([(0, 1, 2)])
        completed = [False]
        class LastLoop:
            @property
            def vertex_index(self):
                completed[0] = True
                return 2
        data.loops[-1] = LastLoop()
        def expired():
            if completed[0]:
                raise m.BlenderHostError('acquisition_deadline_exceeded')
        with self.assertRaisesRegex(m.BlenderHostError, '^acquisition_deadline_exceeded$'):
            validate(data, coordinates=False, checkpoint=expired)

    def test_existing_scene_quantity_limit_precedes_validator_and_native_capture(self):
        host, objects = source_fixture((0., 2.))
        class SizedVertices:
            def __init__(self, points): self.points = points
            def __len__(self): return 250_001
            def __getitem__(self, index): return self.points[index]
        for obj in objects:
            obj.data.vertices = SizedVertices(obj.data.vertices)
        with patch.object(m, '_acquisition_validate_triangles', side_effect=AssertionError('validator after over-budget source')) as validate_mock:
            with self.assertRaisesRegex(m.BlenderHostError, 'acquisition_scene_geometry_budget'):
                capture(host)
        validate_mock.assert_not_called()
        self.assertEqual(sum(obj.mesh_calls for obj in objects), 0)

    def test_existing_request_deadline_precedes_dependency_graph_and_native_capture(self):
        host, objects = source_fixture()
        with patch.object(host, '_depsgraph', side_effect=AssertionError('graph read after deadline')):
            with self.assertRaisesRegex(m.BlenderHostError, '^acquisition_deadline_exceeded$'):
                capture(host, deadline_ns=1)
        self.assertEqual(sum(obj.mesh_calls for obj in objects), 0)

    def test_legacy_enrichment_preserves_explicit_bad_metadata(self):
        data = NS(vertices=[], polygons=[NS(vertices=(0, 1, 2), loop_start=-1, loop_total=4)],
                  loops=[NS(vertex_index=13), None, None])
        enrich_data(data)
        self.assertEqual(data.polygons[0].loop_start, -1)
        self.assertEqual(data.polygons[0].loop_total, 4)
        self.assertEqual([loop.vertex_index for loop in data.loops], [13, 1, 2])


if __name__ == '__main__':
    unittest.main()
