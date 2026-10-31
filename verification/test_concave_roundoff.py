"""Self-contained regressions from independent large-coordinate counterexamples."""
import copy
import math
import unittest
import numpy as np
from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin.geometry_safety import measure_pair_geometry
from verification.test_complex_scene_quality import l_prism, box

FALSE_CLEAR_INPUT = {'probe': {'object_id': 'roundoff-probe', 'mark_label': '#roundoff-probe', 'name': 'roundoff-probe', 'is_focal_target': False, 'color_rgb': [100, 130, 180], 'vertices': [[100000000.06394473, 100000000.05576563, 99999999.99], [100000000.072725, 100000000.0639453, 99999999.99], [100000000.06454533, 100000000.07272556, 99999999.99], [100000000.05576506, 100000000.0645459, 99999999.99], [100000000.06394473, 100000000.05576563, 100000000.01], [100000000.072725, 100000000.0639453, 100000000.01], [100000000.06454533, 100000000.07272556, 100000000.01], [100000000.05576506, 100000000.0645459, 100000000.01]], 'faces': [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]], 'edges': [[0, 1], [0, 2], [0, 3], [0, 4], [0, 5], [1, 2], [1, 5], [1, 6], [2, 3], [2, 6], [2, 7], [3, 4], [3, 7], [4, 5], [4, 6], [4, 7], [5, 6], [6, 7]], 'local_axes': [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], 'pivot_world': [100000000.06424503, 100000000.0642456, 100000000.0], 'axes_source': 'host', 'axes_confidence': 'explicit', 'axes_reason': 'independent_analytic_fixture'}, 'reference': {'object_id': 'independent-ring', 'mark_label': '#independent-ring', 'name': 'independent-ring', 'is_focal_target': False, 'color_rgb': [100, 130, 180], 'vertices': [[99999999.94, 99999999.94, 99999999.985], [100000000.06, 99999999.94, 99999999.985], [100000000.06, 100000000.06, 99999999.985], [99999999.94, 100000000.06, 99999999.985], [99999999.975, 99999999.975, 99999999.985], [100000000.025, 99999999.975, 99999999.985], [100000000.025, 100000000.025, 99999999.985], [99999999.975, 100000000.025, 99999999.985], [99999999.94, 99999999.94, 100000000.015], [100000000.06, 99999999.94, 100000000.015], [100000000.06, 100000000.06, 100000000.015], [99999999.94, 100000000.06, 100000000.015], [99999999.975, 99999999.975, 100000000.015], [100000000.025, 99999999.975, 100000000.015], [100000000.025, 100000000.025, 100000000.015], [99999999.975, 100000000.025, 100000000.015]], 'faces': [[8, 9, 13], [8, 13, 12], [0, 4, 5], [0, 5, 1], [0, 1, 9], [0, 9, 8], [5, 4, 12], [5, 12, 13], [9, 10, 14], [9, 14, 13], [1, 5, 6], [1, 6, 2], [1, 2, 10], [1, 10, 9], [6, 5, 13], [6, 13, 14], [10, 11, 15], [10, 15, 14], [2, 6, 7], [2, 7, 3], [2, 3, 11], [2, 11, 10], [7, 6, 14], [7, 14, 15], [11, 8, 12], [11, 12, 15], [3, 7, 4], [3, 4, 0], [3, 0, 8], [3, 8, 11], [4, 7, 15], [4, 15, 12]], 'edges': [[0, 1], [0, 3], [0, 4], [0, 5], [0, 8], [0, 9], [1, 2], [1, 5], [1, 6], [1, 9], [1, 10], [2, 3], [2, 6], [2, 7], [2, 10], [2, 11], [3, 4], [3, 7], [3, 8], [3, 11], [4, 5], [4, 7], [4, 12], [4, 15], [5, 6], [5, 12], [5, 13], [6, 7], [6, 13], [6, 14], [7, 14], [7, 15], [8, 9], [8, 11], [8, 12], [8, 13], [9, 10], [9, 13], [9, 14], [10, 11], [10, 14], [10, 15], [11, 12], [11, 15], [12, 13], [12, 15], [13, 14], [14, 15]], 'local_axes': [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], 'pivot_world': [100000000.0, 100000000.0, 100000000.0], 'axes_source': 'host', 'axes_confidence': 'explicit', 'axes_reason': 'independent_analytic_fixture'}}
DISTANCE_INPUT = {'probe': {'object_id': 'probe', 'mark_label': '#probe', 'name': 'probe', 'is_focal_target': False, 'color_rgb': [100, 140, 180], 'vertices': [[100000000.0746997, 100000000.06652004, 99999999.99], [100000000.08347997, 100000000.0746997, 99999999.99], [100000000.0753003, 100000000.08347997, 99999999.99], [100000000.06652004, 100000000.0753003, 99999999.99], [100000000.0746997, 100000000.06652004, 100000000.01], [100000000.08347997, 100000000.0746997, 100000000.01], [100000000.0753003, 100000000.08347997, 100000000.01], [100000000.06652004, 100000000.0753003, 100000000.01]], 'faces': [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]], 'edges': [[0, 1], [0, 2], [0, 3], [0, 4], [0, 5], [1, 2], [1, 5], [1, 6], [2, 3], [2, 6], [2, 7], [3, 4], [3, 7], [4, 5], [4, 6], [4, 7], [5, 6], [6, 7]], 'local_axes': [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], 'pivot_world': [0.0, 0.0, 0.0], 'axes_source': 'host', 'axes_confidence': 'explicit', 'axes_reason': 'independent_analytic_fixture'}, 'reference': {'object_id': 'ring', 'mark_label': '#ring', 'name': 'ring', 'is_focal_target': False, 'color_rgb': [100, 140, 180], 'vertices': [[99999999.94, 99999999.94, 99999999.985], [100000000.06, 99999999.94, 99999999.985], [100000000.06, 100000000.06, 99999999.985], [99999999.94, 100000000.06, 99999999.985], [99999999.975, 99999999.975, 99999999.985], [100000000.025, 99999999.975, 99999999.985], [100000000.025, 100000000.025, 99999999.985], [99999999.975, 100000000.025, 99999999.985], [99999999.94, 99999999.94, 100000000.015], [100000000.06, 99999999.94, 100000000.015], [100000000.06, 100000000.06, 100000000.015], [99999999.94, 100000000.06, 100000000.015], [99999999.975, 99999999.975, 100000000.015], [100000000.025, 99999999.975, 100000000.015], [100000000.025, 100000000.025, 100000000.015], [99999999.975, 100000000.025, 100000000.015]], 'faces': [[8, 9, 13], [8, 13, 12], [0, 4, 5], [0, 5, 1], [0, 1, 9], [0, 9, 8], [5, 4, 12], [5, 12, 13], [9, 10, 14], [9, 14, 13], [1, 5, 6], [1, 6, 2], [1, 2, 10], [1, 10, 9], [6, 5, 13], [6, 13, 14], [10, 11, 15], [10, 15, 14], [2, 6, 7], [2, 7, 3], [2, 3, 11], [2, 11, 10], [7, 6, 14], [7, 14, 15], [11, 8, 12], [11, 12, 15], [3, 7, 4], [3, 4, 0], [3, 0, 8], [3, 8, 11], [4, 7, 15], [4, 15, 12]], 'edges': [[0, 1], [0, 3], [0, 4], [0, 5], [0, 8], [0, 9], [1, 2], [1, 5], [1, 6], [1, 9], [1, 10], [2, 3], [2, 6], [2, 7], [2, 10], [2, 11], [3, 4], [3, 7], [3, 8], [3, 11], [4, 5], [4, 7], [4, 12], [4, 15], [5, 6], [5, 12], [5, 13], [6, 7], [6, 13], [6, 14], [7, 14], [7, 15], [8, 9], [8, 11], [8, 12], [8, 13], [9, 10], [9, 13], [9, 14], [10, 11], [10, 14], [10, 15], [11, 12], [11, 15], [12, 13], [12, 15], [13, 14], [14, 15]], 'local_axes': [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], 'pivot_world': [0.0, 0.0, 0.0], 'axes_source': 'host', 'axes_confidence': 'explicit', 'axes_reason': 'independent_analytic_fixture'}}

def pair(values):
    return tuple(MeshEntity3D.from_dict(values[key]) for key in ("probe","reference"))

class ConcaveRoundoffRegressionTests(unittest.TestCase):
    def test_world_projection_must_not_lose_actual_penetration(self):
        # Independent exact Fraction polygon/wall oracle classifies this raw
        # binary64 shape as penetrating. Early unreleased candidate lost it.
        focal,reference=pair(FALSE_CLEAR_INPUT)
        result=measure_pair_geometry(focal,reference)
        self.assertIs(result["measurement_valid"],True,result)
        self.assertIs(result["is_penetrating"],True,result)

    def test_unrepresentable_global_witness_is_explicit_unknown(self):
        focal,reference=pair(DISTANCE_INPUT)
        result=measure_pair_geometry(focal,reference,need_clearance=True)
        self.assertIs(result["measurement_valid"],False,result)
        self.assertIsNone(result["signed_clearance_m"])
        self.assertEqual(result["reason"],"original_surface_witness_precision_exceeded")
        collision=measure_pair_geometry(focal,reference,need_clearance=False)
        self.assertIs(collision["measurement_valid"],True,collision)
        self.assertIs(collision["is_penetrating"],False)

    def test_rebased_strict_scalar_matches_independent_decimal_distance(self):
        values=copy.deepcopy(DISTANCE_INPUT)
        origin=np.asarray(values["reference"]["vertices"][0],dtype=float)
        for raw in values.values():
            raw["vertices"]=(np.asarray(raw["vertices"],dtype=float)-origin).tolist()
            if raw.get("pivot_world") is not None:
                raw["pivot_world"]=(np.asarray(raw["pivot_world"])-origin).tolist()
        focal,reference=pair(values)
        result=measure_pair_geometry(focal,reference,need_clearance=True)
        self.assertIs(result["measurement_valid"],True,result)
        self.assertAlmostEqual(result["signed_clearance_m"],0.015199913633264292,places=14)

    def test_escape_certificate_checks_original_world_endpoint(self):
        reference=MeshEntity3D.from_dict(l_prism())
        focal=MeshEntity3D.from_dict(box("inside-crossing",(0,-.025,0),(.01,.04,.02)))
        result=measure_pair_geometry(focal,reference,need_clearance=True)
        self.assertIs(result["measurement_valid"],True,result)
        self.assertIs(result["is_penetrating"],True)
        vector=np.asarray(result["escape_vector_world_m"])
        moved=focal.vertices+vector
        # The certificate uses a sufficient world-axis AABB separation;
        # checking the exact reported world addition requires no tolerance.
        outside=any(moved[:,axis].min()>=reference.vertices[:,axis].max()
            or moved[:,axis].max()<=reference.vertices[:,axis].min() for axis in range(3))
        self.assertTrue(outside,result)
        self.assertEqual(result["classification_tolerance_m"],0.0)

if __name__=="__main__":unittest.main()
