import copy,unittest
from human_eye_plugin.episode_candidates import CandidateIndex


def candidate(key='c1',**kw):
    row=dict(candidate_id=key,source_event='event'+key,asset_family='family'+key,task_family='gap',operator_revision='op1',schema='s1',
        source_kind='independent_verified',verified_independent=True,training_positive=True,features=[1.,2.],constraints={'static':True},
        proposal={'operator':'gap','initial_guess':[.1]},provenance='explicit independent acceptance')
    row.update(kw);return row


class CandidateTests(unittest.TestCase):
    def query(self,index,**kw):
        args=dict(task_family='gap',operator_revision='op1',schema='s1',constraints={'static':True},features=[1.,2.]);args.update(kw)
        return index.shadow(**args)

    def test_factory_scripted_numeric_true_or_no_evidence_refused(self):
        for kw in (dict(source_kind='factory'),dict(verified_independent=1),dict(training_positive=False),dict(provenance='')):
            with self.assertRaises(ValueError):CandidateIndex().add(candidate(**kw))

    def test_hard_filters_before_even_identical_similarity(self):
        index=CandidateIndex();index.add(candidate())
        for kw in (dict(task_family='repair'),dict(operator_revision='op2'),dict(schema='s2'),dict(constraints={'static':False}),dict(excluded_asset_families=['familyc1'])):
            self.assertEqual(self.query(index,**kw)['status'],'no_qualified_match')

    def test_shadow_has_no_grant_and_revocation(self):
        index=CandidateIndex();index.add(candidate());r=self.query(index)
        self.assertFalse(r['execution_authority']);self.assertFalse(r['learning_enabled']);self.assertTrue(r['requires_new_admission'])
        index.revoke('c1');self.assertEqual(self.query(index)['candidates'],[])

    def test_event_dedup_detached_data_and_old_authority_rejected(self):
        index=CandidateIndex();a=candidate();index.add(a);a['proposal']['initial_guess'][0]=999
        self.assertEqual(self.query(index)['candidates'][0]['proposal']['initial_guess'],[.1])
        with self.assertRaises(ValueError):index.add(candidate('c2',source_event='eventc1'))
        with self.assertRaises(ValueError):index.add(candidate('c3',proposal={'approved':True,'grant':'old'}))


if __name__=='__main__':unittest.main()
