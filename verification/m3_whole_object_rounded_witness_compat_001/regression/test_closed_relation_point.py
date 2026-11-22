"""Guard the three-coordinate localization returned through ordered task facts."""

import math
import unittest

from verification.m3_whole_object_rounded_witness_compat_001.relations.fixtures import (
    FACES,
    OFFSET,
    VERTICES,
)
from verification.test_concave_geometry import entity
from verification import test_task_complete_001 as support


class ClosedRelationPointTests(unittest.TestCase):
    setUp = support.CurrentTaskEvidenceTests.setUp
    set_pair = support.CurrentTaskEvidenceTests.set_pair
    observe = support.CurrentTaskEvidenceTests.observe

    def position_pair(self, offset):
        right = [tuple(value + delta for value, delta in zip(vertex, offset))
                 for vertex in VERTICES]
        self.set_pair(entity('a', VERTICES, FACES), entity('b', right, FACES))
        return VERTICES, right

    def test_penetrating_task_facts_publish_one_world_coordinate(self):
        vertices = self.position_pair(OFFSET)
        for requested in (
            ('closed_solid_relation',),
            ('closed_solid_relation', 'surface_proximity'),
            ('spatial_relation',),
            ('spatial_relation', 'closed_solid_relation', 'surface_proximity'),
        ):
            with self.subTest(requested=requested):
                facts = self.observe(requested)['facts']
                self.assertEqual(facts.keys(), set(requested))
                for name in requested:
                    with self.subTest(fact=name):
                        if name == 'surface_proximity':
                            self.assertEqual(facts[name]['value']['distance_m'], 0.0)
                            continue
                        self.assert_transverse_point(facts[name], vertices)

    def assert_transverse_point(self, fact, vertices):
        self.assertEqual(fact['status'], 'measured')
        self.assertEqual(fact['value'], 'penetrating')
        self.assertEqual(fact['certificate'], 'transverse_boundary_interiors')
        evidence = fact['local_evidence']
        self.assertEqual(evidence['type'], 'transverse_triangle_crossing')
        self.assertEqual(evidence['triangle_indices'], [6, 4])
        self.assertEqual(evidence['triangle_vertices_world_m'], [
            [list(points[vertex]) for vertex in FACES[index]]
            for points, index in zip(vertices, (6, 4))
        ])
        self.assertEqual(evidence['point_status'], 'approximate')
        point = evidence['point_world_m']
        self.assertIs(type(point), list)
        self.assertEqual(len(point), 3, point)
        self.assertTrue(all(type(value) in (int, float) and math.isfinite(value)
                            for value in point), point)
        self.assertEqual(point, [1.0, 0.4375, 0.25])

    def test_separated_task_facts_do_not_publish_transverse_point(self):
        self.position_pair((1.75, OFFSET[1], OFFSET[2]))
        facts = self.observe(('spatial_relation', 'closed_solid_relation', 'surface_proximity'))['facts']
        for name in ('spatial_relation', 'closed_solid_relation'):
            with self.subTest(fact=name):
                fact = facts[name]
                self.assertEqual(fact['status'], 'measured')
                self.assertEqual(fact['value'], 'separated')
                self.assertNotIn('local_evidence', fact)
        self.assertEqual(facts['surface_proximity']['value']['distance_m'], 0.75)
