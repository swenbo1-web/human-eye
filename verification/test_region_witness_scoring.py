import copy
import unittest
from verification.region_witness_scoring import grade


class WitnessGrading(unittest.TestCase):
    def setUp(self):
        facts={0:dict(state='measured',reason=None,principal_stretches=[1.2,.8],area_ratio=.96),
               1:dict(state='measured',reason=None,principal_stretches=[1.3,.98],area_ratio=1.274),
               2:dict(state='measured',reason=None,principal_stretches=[1.02,.7],area_ratio=.714),
               3:dict(state='measured',reason=None,principal_stretches=[1.2,.8],area_ratio=.96)}
        self.truth=dict(frames=[dict(label=label,source_ref=dict(scene_sha256=label),anchor=dict(anchor_id=label),
                                  acceptable_witnesses=[0],members=[0,1,2],facts=copy.deepcopy(facts)) for label in ('one','two')])
        self.evidence=dict(targeted_triangle_indices=[0,1,2,3],same_original_topology_verified=True,anchor_ids=dict(one='one',two='two'))
        self.answer=dict(task_sha256='bound',selected_triangle=0,frames=[dict(label=label,file_sha256=label,principal_stretches=[1.2,.8],area_ratio=.96,state='measured',reason=None,in_core=True,has_confirmed_mixed_witness=True) for label in ('one','two')],interpretation='local numeric evidence only')

    def result(self,answer=None,evidence=None):
        return grade(answer or self.answer,'bound',self.truth,evidence or self.evidence)

    def test_any_acceptable_face_is_accepted(self):
        self.assertTrue(self.result()['mechanical_complete'])
        for frame in self.truth['frames']:
            frame['acceptable_witnesses'].append(3);frame['members'].append(3)
        self.answer['selected_triangle']=3
        self.assertTrue(self.result()['mechanical_complete'])

    def test_different_faces_cannot_join_two_thresholds(self):
        self.answer['selected_triangle']=1
        self.assertFalse(self.result()['checks']['original_triangle'])

    def test_correct_numbers_outside_core_fail(self):
        self.answer['selected_triangle']=3
        self.assertFalse(self.result()['checks']['original_triangle'])
        self.assertFalse(self.result()['checks']['core_membership'])

    def test_wrong_source_or_task_fail(self):
        self.answer['frames'][0]['file_sha256']='wrong'
        self.answer['task_sha256']='wrong'
        result=self.result()['checks'];self.assertFalse(result['source_and_frame']);self.assertFalse(result['task_binding'])

    def test_same_id_without_same_topology_fails(self):
        self.evidence['same_original_topology_verified']=False
        self.assertFalse(self.result()['checks']['same_face_evidence'])

    def test_unknown_does_not_prove_absence(self):
        f=self.truth['frames'][0];f['acceptable_witnesses']=[]
        f['facts'][1]=dict(state='unknown',reason='metric_resolution_insufficient',principal_stretches=None,area_ratio=None)
        self.answer['frames'][0]['has_confirmed_mixed_witness']=False
        self.assertFalse(self.result()['checks']['confirmation_scope'])
        self.answer['frames'][0]['has_confirmed_mixed_witness']=None
        self.assertTrue(self.result()['checks']['confirmation_scope'])

    def test_duplicates_extra_rows_boolean_numbers_fail(self):
        self.answer['frames'].append(copy.deepcopy(self.answer['frames'][0]))
        self.assertFalse(self.result()['mechanical_complete'])
        self.answer['frames'].pop();self.answer['frames'][0]['principal_stretches'][0]=True
        self.assertFalse(self.result()['checks']['numbers'])


if __name__=='__main__':
    unittest.main()
