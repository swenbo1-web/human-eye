import copy,unittest
from verification.patch_observation_fixtures import fixtures,ring,edge_samples,analytically_visible
from verification.test_mesh_structure_runtime import raw_case,identity
from human_eye_plugin import mesh_structure as m


class PatchReferenceTests(unittest.TestCase):
    def test_literal_visibility_counts_match_analytic_rectangle_oracle(self):
        for c in fixtures():
            samples=edge_samples(c)
            self.assertEqual(len(samples),12)
            self.assertEqual(sum(analytically_visible(c,s['point']) for s in samples),c['visible_samples'])

    def test_object_center_and_feature_visibility_are_different_truths(self):
        for c in fixtures():
            self.assertEqual(analytically_visible(c,[0.,0.,0.]),c['object_center_visible'])
            self.assertEqual(not analytically_visible(c,c['center']),c['patch_center_blocked'])
        cases={c['id']:c for c in fixtures()}
        self.assertFalse(cases['object_center_blocked_feature_visible']['object_center_visible'])
        self.assertEqual(cases['object_center_blocked_feature_visible']['visible_samples'],12)
        self.assertTrue(cases['object_visible_feature_blocked']['object_center_visible'])
        self.assertEqual(cases['object_visible_feature_blocked']['visible_samples'],0)

    def test_inner_boundary_matches_one_whole_original_component(self):
        for c in fixtures():
            raw=raw_case(ring(c));result=m.analyze_raw(raw,identity(),task_id='reference',categories=['boundary_edges'])
            expected={tuple(sorted(e)) for e in c['feature_edges']}
            matches=[p for p in result['patches'] if {tuple(sorted(raw['edges'][i])) for i in p['source_indices']}==expected]
            self.assertEqual(len(matches),1)
            self.assertEqual(result['report']['checks']['boundary_edges']['found'],2)
            self.assertEqual(matches[0]['position']['status'],'known')

    def test_patch_is_offset_from_object_center_and_frame_contains_whole_feature(self):
        for c in fixtures():
            source=ring(c);span=1.6*max(2*x for x in c['half'])
            self.assertNotEqual(c['center'],[0.,0.,0.])
            for i in (4,5,6,7):
                self.assertLess(max(abs(source['vertices'][i][k]-c['center'][k]) for k in (0,1)),span/2)
            self.assertGreaterEqual(384*min(2*x for x in c['half'])/span,16)

    def test_reference_opportunity_policy_has_both_positive_and_negative_cases(self):
        self.assertEqual(sum(c['want_detail'] for c in fixtures()),3)
        for c in fixtures():
            # Full-scene XY span follows analytic extremes, independent of the
            # producer planner: [-1,101] with a far box, or [-1,1] without it.
            overview_span=127.5 if c['far'] else 2.5
            detail_span=1.6*max(2*x for x in c['half'])
            expected=(c['visible_samples']>=8 and 384*min(2*x for x in c['half'])/overview_span<16
                      and 384*min(2*x for x in c['half'])/detail_span>=16 and overview_span/detail_span>=2)
            self.assertEqual(expected,c['want_detail'])

    def test_fixtures_return_detached_values(self):
        first=fixtures();original=copy.deepcopy(first);first[0]['feature_edges'][0][0]=999
        self.assertEqual(fixtures(),original)


if __name__=='__main__':unittest.main()
