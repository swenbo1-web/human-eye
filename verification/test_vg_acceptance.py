"""Regression checks for the public-image hole in the author VG scorer."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from verification import test_raycast_saccade_gpu as author_audit
from verification.vg_acceptance import audit_run, read_images, verify_public_pixels


RUN = Path(__file__).resolve().parents[1] / "artifacts/vg/author_002"


@unittest.skipUnless((RUN / "run.json").exists(), "Requires frozen author_002 evidence")
class PublicVGAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((RUN / "process_00/raw.json").read_text(encoding="utf-8"))["cases"]

    def test_public_geometry_all_three_processes(self):
        result = audit_run(RUN)
        self.assertTrue(result["complete"])
        self.assertTrue(result["public_quality_gate_passed"])
        for process in result["processes"]:
            self.assertEqual(len(process["public_pass_sets"]["fixed"]), 10)
            self.assertEqual(len(process["public_pass_sets"]["active"]), 24)

    def test_erased_public_geometry_is_rejected_despite_valid_bottom(self):
        case = self.cases[0]
        hud, bottom, _ = read_images(case, "active")
        erased = hud.copy()
        erased[247:265, 750:785] = (0, 0, 0, 255)
        points = case["quality"]["active"]["witness_pixels"]
        self.assertTrue(author_audit._hud_binding(erased, bottom, points["global"], points["local"]))
        result = verify_public_pixels(case, "active", erased, bottom)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["public_target_surface_pixels"])
        self.assertFalse(result["checks"]["public_consecutive_gap_pixels"])

    def test_author_success_flags_cannot_turn_occlusion_into_a_pass(self):
        case = deepcopy(self.cases[4])
        evidence = case["quality"]["fixed"]
        evidence["passed"] = True
        for records in evidence["witness_neighborhood_rays"].values():
            for record in records:
                record["matched"] = True
        for record in evidence["interior_gap_rays"]:
            record["is_gap"] = True
        hud, bottom, _ = read_images(case, "fixed")
        result = verify_public_pixels(case, "fixed", hud, bottom)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["public_consecutive_gap_pixels"])

    def test_missing_native_samples_are_rejected(self):
        case = deepcopy(self.cases[0])
        case["quality"]["active"]["interior_gap_rays"].pop()
        hud, bottom, _ = read_images(case, "active")
        result = verify_public_pixels(case, "active", hud, bottom)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["raw_ray_coverage"])


if __name__ == "__main__":
    unittest.main()
