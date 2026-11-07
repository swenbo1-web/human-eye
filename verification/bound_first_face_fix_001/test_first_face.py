"""Sentinels and value checks; executed only by the fixed-Git runner."""
from collections import Counter
import itertools
import math
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS

from verification.test_m4_capture_001 import fixture, capture, m
from verification.bound_source_fix_001.test_source_validation import enrich_data, sentinel_native

OLD=sys.modules['_first_face_prior']
assert getattr(m,'_FIRST_FACE_FIXED_GIT',False), 'use the fixed-Git runner'
I=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]


class Face:
    def __init__(self,start,total,observed):
        self.loop_start,self.loop_total,self.observed=start,total,observed
    @property
    def vertices(self):
        self.observed['forbidden_polygon_vertices']+=1
        raise AssertionError('forbidden polygon.vertices getter')


class Loops(list):
    def __init__(self,indices,observed):
        super().__init__(NS(vertex_index=x) for x in indices);self.observed=observed
    def __getitem__(self,index):
        self.observed['loop_reads']+=1
        return super().__getitem__(index)


class Vertices(list):
    def __init__(self,points,observed):
        super().__init__(NS(co=p) for p in points);self.observed=observed
    def __getitem__(self,index):
        self.observed['vertex_dereferences']+=1
        return super().__getitem__(index)


def data(start=0,total=3,indices=(0,1,2),points=None):
    observed=Counter()
    points=points or [(0.,0.,0.),(0.,1.,0.),(0.,0.,1.)]
    result=NS(polygons=[Face(start,total,observed)],loops=Loops(indices,observed),
              vertices=Vertices(points,observed))
    return result,observed


class FirstFaceContracts(unittest.TestCase):
    def test_prior_fixed_bytes_reach_forbidden_getter(self):
        malformed,reads=data(total=8,indices=(0,1,2,0,1,2))
        with self.assertRaisesRegex(AssertionError,'forbidden polygon.vertices'):
            OLD._acquisition_witness(malformed,I,1.)
        self.assertEqual(reads['forbidden_polygon_vertices'],1)
        self.assertEqual(reads['loop_reads'],0)
        self.assertEqual(reads['vertex_dereferences'],0)

    def test_bad_layout_never_reads_corner_or_coordinate(self):
        cases=[(-1,3),(1,3),(8,3),(0,0),(0,2),(0,4),(True,3),(0,True),(0,3.0),('0',3)]
        for start,total in cases:
            with self.subTest(start=start,total=total):
                malformed,reads=data(start,total)
                self.assertIsNone(m._acquisition_witness(malformed,I,1.))
                self.assertEqual(reads,Counter())

    def test_compensating_first_long_face_preserves_global_counts_but_no_reads(self):
        malformed,reads=data(total=8,indices=(0,1,2,0,1,2))
        malformed.polygons.append(Face(8,-2,reads))
        self.assertEqual(len(malformed.loops),3*len(malformed.polygons))
        self.assertIsNone(m._acquisition_witness(malformed,I,1.))
        self.assertEqual(reads,Counter())

    def test_bad_first_index_does_not_dereference_any_vertex(self):
        for bad in (-1,13,True,0.0,'0'):
            with self.subTest(index=bad):
                malformed,reads=data(indices=(bad,1,2))
                self.assertIsNone(m._acquisition_witness(malformed,I,1.))
                self.assertEqual(reads['loop_reads'],3)
                self.assertEqual(reads['vertex_dereferences'],0)
                self.assertEqual(reads['forbidden_polygon_vertices'],0)

    def test_valid_order_transform_units_and_nonzero_start_equal_prior(self):
        matrices=[I,[[0.,-2.,0.,4.],[3.,0.,0.,-2.],[0.,0.,.5,7.],[0.,0.,0.,1.]]]
        for rotation,world,scale,start in itertools.product(range(3),matrices,(1.,.001,3.),(0,3)):
            indices=[0,1,2];indices=indices[rotation:]+indices[:rotation]
            current,reads=data(start=start,indices=([99]*start)+indices)
            prior=NS(vertices=current.vertices,polygons=[NS(vertices=tuple(indices))])
            expected=OLD._acquisition_witness(prior,world,scale)
            reads.clear()
            actual=m._acquisition_witness(current,world,scale)
            self.assertEqual(actual,expected)
            self.assertEqual(actual['triangle_vertex_indices'],indices)
            self.assertEqual(reads['loop_reads'],3)
            self.assertEqual(reads['forbidden_polygon_vertices'],0)

    def test_nonfinite_and_finite_degenerate_behaviour_equal_prior(self):
        for points in ([(0.,0.,0.),(0.,1.,0.),(0.,2.,0.)],
                       [(0.,0.,0.),(0.,1.,0.),(math.nan,0.,1.)],
                       [(0.,0.,0.),(0.,1.,0.),(math.inf,0.,1.)]):
            current,reads=data(points=points)
            prior=NS(vertices=current.vertices,polygons=[NS(vertices=(0,1,2))])
            self.assertIsNone(OLD._acquisition_witness(prior,I,1.))
            self.assertIsNone(m._acquisition_witness(current,I,1.))
            self.assertEqual(reads['forbidden_polygon_vertices'],0)

    def test_capture_rejects_bad_first_layout_before_native(self):
        for start,total in ((-1,3),(8,3),(0,8)):
            with self.subTest(start=start,total=total):
                host,objects=fixture()
                for obj in objects:enrich_data(obj.data)
                target=objects[0];reads=Counter()
                target.data.vertices.extend(NS(co=(0.,2.,float(i))) for i in range(3))
                target.data.loops=Loops([0,1,2,3,4,5],reads)
                target.data.polygons=[Face(start,total,reads),Face(3,3,reads)]
                native=sentinel_native(target)
                with self.assertRaisesRegex(m.BlenderHostError,'acquisition_invalid_triangle_structure:'+host.object_id(target)):
                    capture(host)
                self.assertEqual(native,Counter())
                self.assertEqual(reads['forbidden_polygon_vertices'],0)
                self.assertTrue(all(obj.mesh_calls==0 for obj in objects))

    def test_capture_rejects_bad_first_corner_before_native(self):
        host,objects=fixture()
        for obj in objects:enrich_data(obj.data)
        target=objects[0];reads=Counter()
        target.data.polygons=[Face(0,3,reads)]
        target.data.loops=Loops([13,1,2],reads)
        target.data.vertices=Vertices([(0.,0.,0.),(0.,1.,0.),(0.,0.,1.)],reads)
        native=sentinel_native(target)
        with self.assertRaisesRegex(m.BlenderHostError,'acquisition_invalid_triangle_indices:'+host.object_id(target)):
            capture(host)
        self.assertEqual(reads['vertex_dereferences'],0)
        self.assertEqual(reads['forbidden_polygon_vertices'],0)
        self.assertEqual(native,Counter())
        self.assertTrue(all(obj.mesh_calls==0 for obj in objects))

    def test_valid_capture_never_calls_polygon_vertices_getter(self):
        host,objects=fixture();reads=Counter()
        for obj in objects:
            enrich_data(obj.data)
            obj.data.polygons=[Face(0,3,reads)]
        packet=capture(host)
        self.assertEqual(packet['work']['expanded_objects'],2)
        self.assertEqual(reads['forbidden_polygon_vertices'],0)
