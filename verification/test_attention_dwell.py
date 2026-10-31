"""A retained focus must be reconsidered when its dwell interval expires.

This exercises the real policy and router observation cache. Visibility and
render cost are deterministic test inputs; actual pixels are covered by the
separate attention rendering and raster tests.
"""
import copy
import json
import unittest
from unittest.mock import patch

from human_eye_plugin.attention_policy import AttentionPolicy, confirm_attention
from human_eye_plugin.auto_router import HumanEyeAutoRouter
from verification.test_auto_router import box, observation


def assembly(gap, *, side=False, revision="r1"):
    meshes = [box("part", [0, 0, .25 + gap], [.3, .2, .1], True),
              box("base", [0, 0, .1], [1.4, 1.2, .2])]
    if side:
        meshes.append(box("side", [.2001, -.1, .25], [.1, .1, .1]))
    return {"revision": revision, "unit": "m", "coordinate_frame": "world",
            "source": "retained_dwell_contract_fixture", "meshes": meshes}


class RetainedAttentionDwellTests(unittest.TestCase):
    def test_retained_focus_rechecks_better_contact_at_dwell_deadline(self):
        clock = [100.]
        router = HumanEyeAutoRouter(quad_size=128, clock=lambda: clock[0])
        policy = AttentionPolicy()
        evaluations = []

        def confirmed_policy(canvas, metadata, meshes, **options):
            by_id = {mesh.object_id: mesh for mesh in meshes}
            gap = float(by_id["part"].bbox_min[2] - by_id["base"].bbox_max[2])
            contacts = [{"object_id": "base", "measurement_valid": True,
                         "signed_clearance_m": gap,
                         "point_a_world": [.15, .1, .2 + gap],
                         "point_b_world": [.15, .1, .2]}]
            if "side" in by_id:
                contacts.append({"object_id": "side", "measurement_valid": True,
                                 "signed_clearance_m": .0001,
                                 "point_a_world": [.15, -.1, .25],
                                 "point_b_world": [.1501, -.1, .25]})
            proposal = policy.propose(
                meshes, focal_id=options["focal_id"], reference_id=options["reference_id"],
                contacts=contacts, quad_size=metadata["quad_size"],
                scene_fingerprint=options["scene_fingerprint"],
                previous=options["previous"], now_s=options["now_s"],
                candidate_visible=lambda plan: True)
            self.assertIn(proposal["decision"], ("propose", "retain"))
            confirmed = confirm_attention(
                proposal, witness_visible=[True, True],
                actual_projected_gap_px=proposal["candidate_projected_gap_px"],
                additional_cost_ms=.1, scene_fingerprint=options["scene_fingerprint"],
                now_s=options["now_s"])
            visual = copy.deepcopy(metadata)
            visual["attention"] = {**confirmed, "proposal": proposal}
            evaluations.append(proposal)
            return canvas, visual, confirmed["state_to_commit"]

        with patch("human_eye_plugin.auto_router.apply_attention_to_canvas", confirmed_policy):
            first = router.handle_event(observation(scene=assembly(.002)))
            self.assertEqual(json.loads(first["context_text"])["attention"]["decision"], "applied")
            clock[0] = 100.01
            changed = observation(scene=assembly(.001, side=True, revision="r2"))
            during = router.handle_event(changed)
            early = json.loads(during["context_text"])["attention"]
            self.assertEqual(early["decision"], "retained")
            self.assertEqual(early["proposal"]["camera_plan"]["target_object_ids"], ["part", "base"])
            self.assertNotIn("attention_dwell_active", early["reason_codes"])
            self.assertAlmostEqual(router.export_state()["sessions"][0][1]["observation"]
                                   ["attention_recheck_after"], 101.)

            clock[0] = 100.5
            reused = router.handle_event(changed)
            self.assertTrue(reused["cache_hit"])
            self.assertEqual(len(evaluations), 2)

            clock[0] = 101.
            after = router.handle_event(changed)
            facts = json.loads(after["context_text"])
            self.assertFalse(after["cache_hit"])
            self.assertEqual(len(evaluations), 3)
            self.assertNotEqual(after["observation_id"], during["observation_id"])
            self.assertEqual(facts["attention"]["decision"], "applied")
            self.assertEqual(facts["attention"]["proposal"]["camera_plan"]["target_object_ids"],
                             ["part", "side"])
            self.assertEqual((facts["focal_id"], facts["reference_id"]), ("part", "base"))
            self.assertEqual(facts["measurement_cache"]["hits"], 2)


if __name__ == "__main__":
    unittest.main()
