"""Independent solid-intersection, topology and bounded-probe regressions."""
from __future__ import annotations

from collections import OrderedDict
import dataclasses
from types import SimpleNamespace
import unittest

import numpy as np

from human_eye_foveated_renderer import MeshEntity3D
from human_eye_module1_operators.submodule_1_4_spatial_sniffer import (
    SpatialAnomalySniffer, _ray_triangle_hit_count, _RAY_DIR_PARITY,
    measure_raycast_penetration_depth_m,
)

SIGNS=np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],float)
FACES=np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]],np.int32)
EDGES=np.array([[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],
                [0,4],[1,5],[2,6],[3,7]],np.int32)


def box(mark,center,size,faces=None):
    return MeshEntity3D(mark,mark,mark,SIGNS*np.asarray(size)/2+np.asarray(center),
                        FACES.copy() if faces is None else faces,EDGES.copy(),(70,130,190),
                        mark=='#B',local_axes=np.eye(3))


def union_parts(parts):
    return MeshEntity3D('#A','#A','convex component union',np.vstack([p.vertices for p in parts]),
                        np.vstack([p.faces+8*i for i,p in enumerate(parts)]),
                        np.vstack([p.edges+8*i for i,p in enumerate(parts)]),
                        (70,130,190),local_axes=np.eye(3))


def assert_disjoint(test, a, b, tol=1e-4):
    extents=np.minimum(a.vertices.max(axis=0),b.vertices.max(axis=0))-np.maximum(
        a.vertices.min(axis=0),b.vertices.min(axis=0))
    test.assertTrue(np.any(extents<=tol+1e-10),extents)


class MeshIntersectionCertificationTests(unittest.TestCase):
    def test_crossing_without_interior_vertices_has_real_convex_depth(self):
        for thickness in (.2,.002):
            with self.subTest(thickness=thickness):
                ref=box('#A',(0,0,0),(2,thickness,thickness))
                focal=box('#B',(0,1-thickness/2,0),(thickness,2,thickness))
                inside=np.all((focal.vertices>ref.vertices.min(axis=0)+1e-10)
                              &(focal.vertices<ref.vertices.max(axis=0)-1e-10),axis=1)
                self.assertFalse(inside.any())
                probe=SpatialAnomalySniffer.probe_closest_clearance(focal,ref)
                self.assertTrue(probe.measurement_valid)
                self.assertTrue(probe.is_penetrating)
                self.assertFalse(probe.is_aligned_flush)
                self.assertAlmostEqual(probe.signed_clearance_m,-thickness,places=8)
                assert_disjoint(self,focal.translated(probe.axis_delta_m),ref)

    def test_center_crossing_uses_200mm_not_900mm_vertex_distance(self):
        ref=box('#A',(0,0,0),(2,.2,.2))
        focal=box('#B',(0,0,0),(.2,2,.2))
        probe=SpatialAnomalySniffer.probe_closest_clearance(focal,ref)
        self.assertTrue(probe.measurement_valid)
        self.assertAlmostEqual(probe.signed_clearance_m,-.2)
        self.assertAlmostEqual(np.linalg.norm(probe.axis_delta_m),.2)

    def test_true_u_slot_contact_remains_valid_but_both_walls_crossing_does_not(self):
        parts=[box('#A',(0,0,.1),(.9,.7,.2)),box('#A',(-.375,0,.425),(.15,.7,.45)),
               box('#A',(.375,0,.425),(.15,.7,.45))]
        ref=union_parts(parts)
        for width,expected in ((.58,False),(.6,False),(.601,True),(.7,True),(.89,True),(.9,True),(.9002,True)):
            with self.subTest(width=width):
                focal=box('#B',(0,0,.3),(width,.2,.2))
                probe=SpatialAnomalySniffer.probe_closest_clearance(focal,ref)
                self.assertTrue(probe.measurement_valid)
                self.assertEqual(probe.is_penetrating,expected)
                self.assertEqual(probe.is_aligned_flush,not expected)
                if expected:
                    moved=focal.translated(probe.axis_delta_m)
                    for part in parts:
                        assert_disjoint(self,moved,part)

    def test_true_l_bracket_contact_preserves_floor_and_side(self):
        ref=union_parts([box('#A',(0,0,.1),(.8,.7,.2)),box('#A',(-.3,0,.45),(.2,.7,.5))])
        focal=box('#B',(-.03,0,.32),(.34,.38,.24))
        probe=SpatialAnomalySniffer.probe_closest_clearance(focal,ref)
        self.assertTrue(probe.measurement_valid)
        self.assertFalse(probe.is_penetrating)
        self.assertTrue(probe.is_aligned_flush)

    def test_open_intersection_stays_unknown_and_never_flush(self):
        ref=box('#A',(0,0,0),(2,.2,.2))
        focal=box('#B',(0,.9,0),(.2,2,.2),faces=FACES[:-2].copy())
        probe=SpatialAnomalySniffer.probe_closest_clearance(focal,ref)
        self.assertFalse(probe.measurement_valid)
        self.assertTrue(probe.is_penetrating)
        self.assertFalse(probe.is_aligned_flush)
        self.assertEqual(probe.axis_delta_m,(0.,0.,0.))

    def test_connected_concave_shell_is_explicitly_unknown(self):
        polygon=np.array([[0,0],[2,0],[2,1],[1,1],[1,2],[0,2]],float)
        verts=np.vstack([np.c_[polygon,np.zeros(6)],np.c_[polygon,np.ones(6)]])
        top=np.array([[0,1,3],[1,2,3],[0,3,5],[3,4,5]],np.int32)
        faces=[*top[:,::-1],*(top+6)]
        for i in range(6):
            j=(i+1)%6;faces.extend([[i,j,j+6],[i,j+6,i+6]])
        faces=np.array(faces,np.int32)
        edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
        ref=MeshEntity3D('L','#A','connected concave L',verts,faces,edges,(70,130,190),local_axes=np.eye(3))
        focal=box('#B',(.5,.5,1.1),(.2,.2,.2))
        self.assertTrue(ref.is_closed_hull)
        probe=SpatialAnomalySniffer.probe_closest_clearance(focal,ref)
        self.assertFalse(probe.measurement_valid)
        self.assertFalse(probe.is_aligned_flush)

    def test_unique_ray_hits_are_invariant_to_shared_edge_and_face_diagonal(self):
        for faces in (FACES.copy(),np.array([*FACES[:6],[2,3,6],[3,7,6],*FACES[8:]],np.int32)):
            ref=box('#A',(0,0,0),(2,2,2),faces=faces)
            for point,expected_depth in (([0,0,0],1),([0,0,-.1],.9),([.01,0,-.1],.9)):
                with self.subTest(point=point,faces=faces[6].tolist()):
                    count=_ray_triangle_hit_count(np.array(point,float),_RAY_DIR_PARITY,*ref.tri_vertices)
                    self.assertEqual(count,1)
                    depth,n=measure_raycast_penetration_depth_m(SimpleNamespace(vertices=np.array([point],float)),ref)
                    self.assertEqual(n,1)
                    self.assertAlmostEqual(depth,expected_depth)
        # A ray touching just a cube vertex does not enter its solid interior.
        ref=box('#A',(0,0,0),(2,2,2))
        self.assertEqual(_ray_triangle_hit_count(np.array([-2.,0,0]),_RAY_DIR_PARITY,*ref.tri_vertices),0)

    def test_full_1200_face_topology_is_retained_for_parity(self):
        lookup={};verts=[];faces=[];n=10
        def vid(p):
            key=tuple(np.round(p,12))
            if key not in lookup:
                lookup[key]=len(verts);verts.append(p)
            return lookup[key]
        for face in FACES:
            a,b,c=SIGNS[face]
            def grid(i,j):return vid(a+(b-a)*i/n+(c-a)*j/n)
            for i in range(n):
                for j in range(n-i):
                    faces.append([grid(i,j),grid(i+1,j),grid(i,j+1)])
                    if i+j<n-1:faces.append([grid(i+1,j),grid(i+1,j+1),grid(i,j+1)])
        faces=np.asarray(faces,np.int32)
        edges=np.unique(np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
        ref=MeshEntity3D('dense','#A','dense cube',np.asarray(verts),faces,edges,(70,130,190),local_axes=np.eye(3))
        point=np.array([-.5244016935856292,-.5910683602522959,.9422649730810374])
        self.assertEqual(len(ref.faces),1200)
        self.assertTrue(ref.is_closed_hull)
        depth,inside=measure_raycast_penetration_depth_m(SimpleNamespace(vertices=point[None,:]),ref,max_faces=1024)
        self.assertEqual(inside,1)
        self.assertAlmostEqual(depth,1-point[2])

    def test_probe_lru_bounds_600_dynamic_references_and_promotes_hits(self):
        focal=box('#B',(0,0,.9),(.3,.2,.2))
        refs=[box('#A',(i*.002,0,.2),(1.4,1.2,.4)) for i in range(600)]
        for ref in refs:
            SpatialAnomalySniffer.probe_closest_clearance(focal,ref)
            self.assertLessEqual(len(focal._probe_cache),SpatialAnomalySniffer.PROBE_CACHE_CAPACITY)
        self.assertIsInstance(focal._probe_cache,OrderedDict)
        original=SpatialAnomalySniffer.probe_closest_clearance(focal,refs[-2])
        self.assertEqual(next(reversed(focal._probe_cache.values()))[0].object_id,refs[-2].object_id)
        self.assertIs(SpatialAnomalySniffer.probe_closest_clearance(focal,refs[-2]),original)
        self.assertIs(next(reversed(focal._probe_cache.values()))[0],refs[-2])
        self.assertFalse(any(entry[0] is refs[0] for entry in focal._probe_cache.values()))

    def test_mutating_published_probe_cannot_forge_a_safe_cache_hit(self):
        for mutation in ("safe_flags", "measurement_valid", "axes_valid", "axis_delta_m",
                         "rotation_matrix_3x3", "normal_a_world", "point_a_world",
                         "roi_vertices_world", "intersection_seam_segments"):
            with self.subTest(mutation=mutation):
                ref=box('#A',(0,0,0),(2,.2,.2))
                focal=box('#B',(0,0,0),(.2,2,.2))
                published=SpatialAnomalySniffer.probe_closest_clearance(focal,ref)
                self.assertTrue(published.is_penetrating)
                self.assertAlmostEqual(published.signed_clearance_m,-.2)
                self.assertIs(SpatialAnomalySniffer.probe_closest_clearance(focal,ref),published)
                expected=dataclasses.asdict(published)
                normals_before=focal.face_normals.copy()
                if mutation=="safe_flags":
                    published.is_penetrating=False
                    published.is_aligned_flush=True
                    published.signed_clearance_m=0.
                    published.axis_delta_m=(0.,0.,0.)
                elif mutation in ("measurement_valid","axes_valid"):
                    setattr(published,mutation,False)
                elif mutation=="axis_delta_m":
                    published.axis_delta_m=(9.,9.,9.)
                else:
                    array=getattr(published,mutation)
                    self.assertGreater(array.size,0)
                    array.flat[0]+=2.
                np.testing.assert_array_equal(focal.face_normals,normals_before)
                corrected=SpatialAnomalySniffer.probe_closest_clearance(focal,ref)
                self.assertIsNot(corrected,published)
                for field,value in expected.items():
                    if field=="compute_time_ms":
                        continue
                    if isinstance(value,np.ndarray):
                        np.testing.assert_array_equal(getattr(corrected,field),value)
                    else:
                        self.assertEqual(getattr(corrected,field),value,field)
                self.assertIs(SpatialAnomalySniffer.probe_closest_clearance(focal,ref),corrected)


if __name__=='__main__':unittest.main()
