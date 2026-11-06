"""Analytical orthogonal-polyhedron cases; no engine result is an oracle."""
from __future__ import annotations

import copy
import math
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.geometry_safety import measure_pair_geometry, solid_support_status
from human_eye_plugin.orthogonal_solid import decompose_orthogonal_solid


SIGNS = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                  [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=float)
BOX_FACES = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],
                      [2,3,7],[2,7,6],[1,2,6],[1,6,5],[3,0,4],[3,4,7]])


def entity(identity, vertices, faces):
    return MeshEntity3D(identity, '#'+identity, identity, np.array(vertices, dtype=float),
        np.array(faces, dtype=np.int64), None, (100,140,180), False,
        local_axes=np.eye(3), pivot_world=np.zeros(3), axes_source='host',
        axes_confidence='explicit', axes_reason='independent_analytic_fixture')


def box(center=(0,0,0), size=(.012,.012,.02), identity='probe'):
    return entity(identity, SIGNS*np.asarray(size)/2 + np.asarray(center), BOX_FACES)


def ring():
    outer = [(-.06,-.06),(.06,-.06),(.06,.06),(-.06,.06)]
    inner = [(-.025,-.025),(.025,-.025),(.025,.025),(-.025,.025)]
    points = [(x,y,z) for z in (-.015,.015) for x,y in outer+inner]
    quads=[]
    for i in range(4):
        j=(i+1)%4
        quads.extend([(8+i,8+j,12+j,12+i),(i,4+i,4+j,j),
                      (i,j,8+j,8+i),(4+j,4+i,12+i,12+j)])
    return entity('ring', points, [triangle for a,b,c,d in quads for triangle in ((a,b,c),(a,c,d))])


def l_shape():
    polygon=[(-.06,-.06),(.06,-.06),(.06,-.025),(-.025,-.025),(-.025,.06),(-.06,.06)]
    points=[(x,y,z) for z in (-.02,.02) for x,y in polygon]
    top=[(0,1,2),(0,2,3),(0,3,5),(3,4,5)]
    faces=[(c,b,a) for a,b,c in top]+[(a+6,b+6,c+6) for a,b,c in top]
    for i in range(6):
        j=(i+1)%6
        faces.extend(((i,j,j+6),(i,j+6,i+6)))
    return entity('L', points, faces)


def changed(mesh, *, vertices=None, faces=None):
    return entity(mesh.object_id, mesh.vertices if vertices is None else vertices,
                  mesh.faces if faces is None else faces)


class ConcaveGeometryTests(unittest.TestCase):
    def test_hole_is_empty_and_exact_clearance_is_19mm(self):
        result=measure_pair_geometry(box(),ring(),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertFalse(result['is_penetrating'])
        self.assertAlmostEqual(result['signed_clearance_m'],.019,places=14)
        self.assertEqual(result['measurement_method'],'exact_orthogonal_cell_union_sat')

    def test_l_slot_is_not_filled_by_a_convex_hull(self):
        result=measure_pair_geometry(box((.02,.02,0),(.01,.01,.02)),l_shape(),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertFalse(result['is_penetrating'])
        self.assertAlmostEqual(result['signed_clearance_m'],.04,places=14)

    def test_exact_boundary_proof_preserves_ring_topology(self):
        proof=decompose_orthogonal_solid(ring())
        self.assertTrue(proof['supported'])
        self.assertEqual(proof['proof']['grid_cells'],9)
        self.assertEqual(proof['proof']['occupied_cells'],8)
        self.assertEqual(proof['convex_part_count'],4)
        self.assertFalse(proof['proof']['coordinate_snapping'])
        self.assertFalse(proof['proof']['ray_sampling'])
        self.assertFalse(proof['proof']['execution_authority'])

    def test_strict_original_surface_witness_not_internal_cells(self):
        result=measure_pair_geometry(box(),ring(),need_clearance=True)
        a,b=np.array(result['point_a_world']),np.array(result['point_b_world'])
        self.assertAlmostEqual(float(np.linalg.norm(a-b)),.019,places=14)
        self.assertLess(min(abs(abs(b[0])-.025),abs(abs(b[1])-.025)),1e-14)
        self.assertLessEqual(abs(b[2]),.015)
        self.assertLess(min(abs(abs(a[k])-value) for k,value in enumerate((.006,.006,.01))),1e-14)

    def test_convex_rotated_probe_inside_exact_axis_aligned_hole(self):
        angle=.37
        rotation=np.array([[math.cos(angle),-math.sin(angle),0],
                           [math.sin(angle),math.cos(angle),0],[0,0,1]])
        probe=changed(box(),vertices=box().vertices @ rotation.T)
        expected=.025-max(np.max(np.abs(probe.vertices[:,0])),np.max(np.abs(probe.vertices[:,1])))
        result=measure_pair_geometry(probe,ring(),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertAlmostEqual(result['signed_clearance_m'],expected,places=14)

    def test_crossing_wall_is_penetrating_and_escape_is_certified(self):
        probe=box((.025,0,0))
        reference=ring()
        result=measure_pair_geometry(probe,reference,need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertTrue(result['is_penetrating'])
        self.assertLess(result['signed_clearance_m'],0)
        self.assertEqual(result['penetration_metric_scope'],'certified_separating_translation_not_minimum_depth')
        moved=changed(probe,vertices=probe.vertices+np.array(result['escape_vector_world_m']))
        self.assertFalse(measure_pair_geometry(moved,reference)['is_penetrating'])

    def test_complete_containment_in_wall_is_not_surface_clearance(self):
        result=measure_pair_geometry(box((.04,0,0)),ring(),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertTrue(result['is_penetrating'])
        self.assertLess(result['signed_clearance_m'],0)

    def test_exact_inner_wall_touch_is_not_penetrating(self):
        probe=box((.019,0,0))
        result=measure_pair_geometry(probe,ring(),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertFalse(result['is_penetrating'])
        self.assertLess(result['signed_clearance_m'],1e-14)

    def test_25um_positive_gap_not_display_rounded(self):
        probe=box((.019-.000025,0,0))
        result=measure_pair_geometry(probe,ring(),need_clearance=True)
        self.assertFalse(result['is_penetrating'])
        self.assertAlmostEqual(result['signed_clearance_m'],.000025,places=14)

    def test_sub_nanometre_positive_gap_preserved(self):
        probe=box((.019-1e-12,0,0))
        result=measure_pair_geometry(probe,ring(),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertFalse(result['is_penetrating'])
        self.assertGreater(result['signed_clearance_m'],0)
        self.assertAlmostEqual(result['signed_clearance_m'],1e-12,places=16)

    def test_positive_overlap_below_requested_tolerance_is_conservatively_blocked(self):
        result=measure_pair_geometry(box((.019+1e-12,0,0)),ring(),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertTrue(result['is_penetrating'])
        self.assertEqual(result['classification_tolerance_m'],0)
        self.assertEqual(result['collision_tolerance_m'],1e-9)

    def test_internal_partition_seam_cannot_tolerate_away_a_thin_embedded_probe(self):
        probe=box((-.04,-.025,0),(1e-10,1.5e-9,1e-10))
        result=measure_pair_geometry(probe,ring(),need_clearance=True)
        # Legacy numeric rejection of this extremely thin convex probe must
        # remain unknown; in particular it can never become a clear endpoint.
        self.assertFalse(result['measurement_valid'])
        self.assertIsNone(result['is_penetrating'])

    def test_global_reverse_winding_is_supported(self):
        reference=ring()
        result=measure_pair_geometry(box(),changed(reference,faces=reference.faces[:,::-1]),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertAlmostEqual(result['signed_clearance_m'],.019,places=14)

    def test_axis_permutation_is_exactly_supported(self):
        reference,probe=ring(),box()
        result=measure_pair_geometry(changed(probe,vertices=probe.vertices[:,[2,0,1]]),
            changed(reference,vertices=reference.vertices[:,[2,0,1]]),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertAlmostEqual(result['signed_clearance_m'],.019,places=14)

    def test_negative_scale_reflection_is_exactly_supported(self):
        reference,probe=ring(),box()
        reflection=np.array([-1.,1.,1.])
        result=measure_pair_geometry(changed(probe,vertices=probe.vertices*reflection),
            changed(reference,vertices=reference.vertices*reflection),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertAlmostEqual(result['signed_clearance_m'],.019,places=14)

    def test_large_translation_uses_represented_float_geometry(self):
        reference,probe=ring(),box()
        shift=np.array([1e12,1e12,1e12])
        moved_probe=changed(probe,vertices=probe.vertices+shift)
        moved_reference=changed(reference,vertices=reference.vertices+shift)
        expected=(shift[0]+.025)-np.max(moved_probe.vertices[:,0])
        result=measure_pair_geometry(moved_probe,moved_reference,need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertFalse(result['is_penetrating'])
        self.assertEqual(result['signed_clearance_m'],expected)

    def test_large_world_witness_roundoff_becomes_unknown_but_collision_gate_remains_available(self):
        from decimal import Decimal,localcontext
        angle=.75;shift=1e8
        c,s=math.cos(angle),math.sin(angle)
        rotation=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
        probe=box();reference=ring()
        probe=changed(probe,vertices=probe.vertices@rotation.T+np.array([shift+.075,shift+.075,shift]))
        reference=changed(reference,vertices=reference.vertices+shift)
        # Independent high-precision minimum from the represented reference
        # corner to the four represented convex-probe polygon edges.
        corner=np.max(reference.vertices[:,:2],axis=0)
        self.assertTrue((np.min(probe.vertices[:,:2],axis=0)>corner).all())
        with localcontext() as context:
            context.prec=90
            point=[Decimal(float(value)) for value in corner]
            corners=[[Decimal(float(value)) for value in row] for row in probe.vertices[:4,:2]]
            values=[]
            for a,b in zip(corners,corners[1:]+corners[:1]):
                delta=[b[k]-a[k] for k in (0,1)]
                offset=[point[k]-a[k] for k in (0,1)]
                parameter=sum(offset[k]*delta[k] for k in (0,1))/sum(value*value for value in delta)
                parameter=max(Decimal(0),min(Decimal(1),parameter))
                values.append(sum((offset[k]-parameter*delta[k])**2 for k in (0,1)))
            expected=float(min(values).sqrt())
        observed=measure_pair_geometry(probe,reference,need_clearance=True)
        self.assertFalse(observed['measurement_valid'])
        self.assertEqual(observed['reason'],'original_surface_witness_precision_exceeded')
        self.assertIsNone(observed['signed_clearance_m'])
        gate=measure_pair_geometry(probe,reference,need_clearance=False)
        self.assertTrue(gate['measurement_valid'])
        self.assertFalse(gate['is_penetrating'])
        origin=probe.vertices[0]
        local=measure_pair_geometry(changed(probe,vertices=probe.vertices-origin),
                                    changed(reference,vertices=reference.vertices-origin),need_clearance=True)
        self.assertTrue(local['measurement_valid'])
        self.assertAlmostEqual(local['signed_clearance_m'],expected,places=14)

    def test_new_union_sat_uses_one_shared_projection_origin(self):
        for center in ((0,0,0),(.025,0,0),(.04,0,0),(.12,.12,0)):
            with self.subTest(center=center):
                probe,reference=box(center),ring()
                offset=np.array([1e8,1e8,1e8])
                world_probe=changed(probe,vertices=probe.vertices+offset)
                world_reference=changed(reference,vertices=reference.vertices+offset)
                world=measure_pair_geometry(world_probe,world_reference)
                origin=world_probe.vertices[0]
                local=measure_pair_geometry(changed(world_probe,vertices=world_probe.vertices-origin),
                    changed(world_reference,vertices=world_reference.vertices-origin))
                self.assertTrue(world['measurement_valid'])
                self.assertEqual(world['is_penetrating'],local['is_penetrating'])
                self.assertEqual(world['projection_coordinate_frame'],'shared_first_focal_vertex_origin')

    def test_general_rotation_is_unknown_without_snapping(self):
        reference=ring();angle=.17
        matrix=np.array([[math.cos(angle),-math.sin(angle),0],[math.sin(angle),math.cos(angle),0],[0,0,1]])
        self.assertFalse(solid_support_status(changed(reference,vertices=reference.vertices@matrix.T))['supported'])

    def test_nearly_axis_aligned_faces_are_not_snapped(self):
        reference=ring();vertices=reference.vertices.copy();vertices[0,0]+=1e-15
        self.assertFalse(solid_support_status(changed(reference,vertices=vertices))['supported'])

    def test_open_mesh_unknown(self):
        reference=ring()
        self.assertFalse(solid_support_status(changed(reference,faces=reference.faces[:-1]))['supported'])

    def test_repeated_face_unknown(self):
        reference=ring()
        self.assertFalse(solid_support_status(changed(reference,faces=np.vstack([reference.faces,reference.faces[0]])))['supported'])

    def test_single_reversed_face_unknown(self):
        reference=ring();faces=reference.faces.copy();faces[0]=faces[0,::-1]
        self.assertFalse(solid_support_status(changed(reference,faces=faces))['supported'])

    def test_closed_self_crossing_ring_unknown(self):
        reference=ring();vertices=reference.vertices.copy()
        # Only one inner wall crosses the outer wall. Expanding every inner
        # extent instead would describe another valid ring with reversed winding.
        vertices[[5,6,13,14],0]=.075
        self.assertFalse(solid_support_status(changed(reference,vertices=vertices))['supported'])

    def test_separate_inward_cavity_shell_unknown(self):
        outer=box(size=(.2,.2,.2));inner=box(size=(.1,.1,.1))
        cavity=entity('cavity',np.vstack([outer.vertices,inner.vertices]),
                      np.vstack([outer.faces,inner.faces[:,::-1]+8]))
        self.assertFalse(solid_support_status(cavity)['supported'])

    def test_disconnected_concave_shell_and_solid_unknown(self):
        reference=ring();extra=box((.2,0,0))
        compound=entity('compound',np.vstack([reference.vertices,extra.vertices]),
                        np.vstack([reference.faces,extra.faces+len(reference.vertices)]))
        self.assertFalse(solid_support_status(compound)['supported'])

    def test_existing_disconnected_convex_union_semantics_preserved(self):
        first,second=box((-.1,0,0)),box((.1,0,0))
        compound=entity('compound',np.vstack([first.vertices,second.vertices]),np.vstack([first.faces,second.faces+8]))
        self.assertTrue(solid_support_status(compound)['supported'])
        self.assertFalse(measure_pair_geometry(box(),compound)['is_penetrating'])

    def test_new_support_is_not_an_action_authority(self):
        support=solid_support_status(ring())
        self.assertTrue(support['supported'])
        self.assertFalse(support['independent_ground_truth'])
        self.assertFalse(support['orthogonal_boundary_proof']['execution_authority'])

    def test_nonfinite_vertices_unknown(self):
        value=ring().to_dict();value['vertices'][0][0]=float('nan')
        self.assertFalse(decompose_orthogonal_solid(value)['supported'])

    def test_boolean_faces_unknown(self):
        value=ring().to_dict();value['faces']=np.asarray(value['faces'],dtype=bool)
        self.assertFalse(decompose_orthogonal_solid(value)['supported'])

    def test_unused_vertices_unknown_in_new_subclass(self):
        reference=ring()
        self.assertFalse(solid_support_status(changed(reference,vertices=np.vstack([reference.vertices,[[.3,.3,.3]]])))['supported'])

    def test_direct_decomposition_rejects_excess_vertices_before_rational_conversion(self):
        value=ring().to_dict()
        value['vertices'] += [[.3,.3,.3]]*100
        with patch('human_eye_plugin.orthogonal_solid._fraction',side_effect=AssertionError('must not convert')):
            result=decompose_orthogonal_solid(value)
        self.assertFalse(result['supported'])
        self.assertEqual(result['reason'],'orthogonal_unreferenced_vertex_work_limit')

    def test_face_grid_part_and_exact_work_limits_unknown(self):
        for name,limit in [('MAX_FACES',31),('MAX_PLANES_PER_AXIS',3),('MAX_GRID_CELLS',8),
                           ('MAX_CELL_BOXES',3),('MAX_FACE_CLIPS',1),('MAX_OVERLAP_TESTS',1),
                           ('MAX_RATIONAL_BITS',32)]:
            with self.subTest(name=name),patch('human_eye_plugin.orthogonal_solid.'+name,limit):
                self.assertFalse(solid_support_status(ring())['supported'])

    def test_decomposed_pair_budget_unknown_before_collision(self):
        for name,limit in [('MAX_PART_PAIRS',3),('MAX_PAIR_PROJECTIONS',10)]:
            with self.subTest(name=name),patch('human_eye_plugin.orthogonal_solid.'+name,limit):
                result=measure_pair_geometry(box(),ring(),need_clearance=True)
                self.assertFalse(result['measurement_valid'])
                self.assertIsNone(result['is_penetrating'])
                self.assertIsNone(result['signed_clearance_m'])

    def test_binary_rational_bit_limit_rejects_extreme_subnormal_geometry(self):
        reference=ring();vertices=reference.vertices*1e-300
        self.assertFalse(decompose_orthogonal_solid(changed(reference,vertices=vertices))['supported'])

    def test_execution_measurement_revalidates_mutated_original_faces(self):
        reference=ring()
        self.assertTrue(measure_pair_geometry(box(),reference)['measurement_valid'])
        reference.faces[0]=reference.faces[0,::-1]
        self.assertFalse(measure_pair_geometry(box(),reference)['measurement_valid'])

    def test_original_convex_fast_path_method_is_preserved(self):
        result=measure_pair_geometry(box((0,0,.03)),box(),need_clearance=True)
        self.assertTrue(result['measurement_valid'])
        self.assertTrue(result['measurement_method'].startswith('convex'))
        self.assertNotIn('classification_tolerance_m',result)

    def test_legacy_thin_and_micro_convex_numeric_rejections_are_not_reopened(self):
        for size in ((.2,.2,1e-13),(2e-8,2e-8,2e-8)):
            with self.subTest(size=size):
                probe=box(size=size)
                self.assertFalse(solid_support_status(probe)['supported'])
                result=measure_pair_geometry(probe,ring(),need_clearance=True)
                self.assertFalse(result['measurement_valid'])
                self.assertIsNone(result['is_penetrating'])

    def test_supported_thin_probe_embedded_on_partition_seam_is_not_clear(self):
        probe=box((-.04,-.025,0),(.012,1e-6,.012))
        result=measure_pair_geometry(probe,ring(),need_clearance=True)
        # This probe passes the existing nondegenerate convex input checks;
        # effective zero tolerance prevents a per-cell seam from forgiving it.
        self.assertTrue(result['measurement_valid'])
        self.assertTrue(result['is_penetrating'])

    def test_original_surface_witness_is_optional_without_clearance(self):
        result=measure_pair_geometry(box(),ring(),need_clearance=False)
        self.assertTrue(result['measurement_valid'])
        self.assertIsNone(result['signed_clearance_m'])
        self.assertNotIn('point_a_world',result)


if __name__=='__main__':
    unittest.main()
