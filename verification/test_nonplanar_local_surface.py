import copy
import math
import time
import unittest
from unittest.mock import patch

from verification import nonplanar_patch_candidate as planner
from verification.nonplanar_local_surface import LocalSurfaceIndex,local_hit
from verification.nonplanar_local_validation import ExactLocalIndex
from verification.nonplanar_local_fixtures import local_source,sampling_case
from verification.nonplanar_patch_fixtures import cases,source,refine_boundary
from verification.test_nonplanar_patch_candidate import replay


def target(points=None,faces=None):
    return {'object_id':'target','world_vertices':points or [[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[1.,1.,0.]],
        'faces':faces or [[0,1,2],[2,1,3]]}


class NonplanarLocalSurfaceTests(unittest.TestCase):
    def proof(self,value=None):
        value=target() if value is None else value
        index=LocalSurfaceIndex(value,time.perf_counter_ns()+10**10)
        proof=index.proof([0,1],.1)
        other=ExactLocalIndex(value,32768)
        self.assertEqual(proof,other.reconstruct([0,1],.1))
        self.assertEqual(index.work,other.work)
        return index,proof

    def test_connected_coplanar_surface_is_allowed(self):
        index,proof=self.proof()
        self.assertEqual(proof['face_ids'],[0,1])

    def test_disconnected_same_plane_and_parallel_layer_are_not_local(self):
        for z in (0.,1e-7,.01):
            value=target();value['world_vertices'] += [[.2,.01,z],[.8,.01,z],[.2,.02,z]]
            value['faces'].append([4,5,6])
            with self.subTest(z=z):
                index,proof=self.proof(value)
                self.assertNotIn(2,proof['face_ids'])
                self.assertFalse(local_hit(index,proof,[.3,.015,z],[0.,0.,1.],[('target',2,0.)],'target'))

    def test_opposite_winding_and_folded_face_are_not_local(self):
        for face,vertex in (([1,2,3],[1.,1.,0.]),([2,1,3],[1.,1.,.1])):
            value=target();value['faces'][1]=face;value['world_vertices'][3]=vertex
            index,proof=self.proof(value)
            self.assertEqual(proof['face_ids'],[0])

    def test_nonmanifold_shared_edge_is_not_a_path(self):
        value=target();value['world_vertices'].append([.5,1.,0.]);value['faces'].append([1,2,4])
        index,proof=self.proof(value)
        self.assertEqual(proof['face_ids'],[0])

    def test_far_bridge_and_returning_fold_cannot_reach_nearby_surface(self):
        points=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[1.,1.,0.],[0.,2.,0.],[1.,2.,0.],[0.,.02,0.],[1.,.02,0.]]
        faces=[[0,1,2],[2,1,3],[2,3,4],[4,3,5],[4,5,6],[6,5,7]]
        index,proof=self.proof(target(points,faces))
        self.assertEqual(proof['face_ids'],[0,1])
        self.assertNotIn(5,proof['face_ids'])

    def test_actual_hit_outside_capsule_is_not_local_even_on_allowed_face(self):
        index,proof=self.proof()
        self.assertFalse(local_hit(index,proof,[.5,.8,0.],[0.,0.,1.],[('target',1,0.)],'target'))

    def test_visit_and_work_limits_stop_before_unbounded_proof(self):
        value=target()
        with self.assertRaisesRegex(ValueError,'work_budget'):LocalSurfaceIndex(value,time.perf_counter_ns()+10**9,0)
        vertices=[[0.,0.,0.]]+[[math.cos(i/100),math.sin(i/100),0.] for i in range(131)]
        faces=[[0,i,i+1] for i in range(1,131)]
        index=LocalSurfaceIndex(target(vertices,faces),time.perf_counter_ns()+10**9)
        with self.assertRaisesRegex(ValueError,'face_visit_budget'):index.proof([0,1],.1)

    def test_sliver_changes_no_source_and_binds_native_snapshot(self):
        native,edges=source(cases()[1]);refine_boundary(native,edges,sliver=True)
        original=copy.deepcopy(native)
        result=planner.choose(native,'target',edges,time.perf_counter_ns()+10**10)
        self.assertEqual(native,original)
        self.assertEqual(result['selected']['visible_count'],12)
        replay(result,native,'target',edges)
        for mutate in ('point','seed','face','budget'):
            changed=copy.deepcopy(native);claim=copy.deepcopy(result)
            if mutate=='point':changed['objects'][0]['world_vertices'][0][0]+=.001
            elif mutate=='seed':claim['selected']['local_surfaces'][0]['seed_face']+=1
            elif mutate=='face':claim['selected']['local_surfaces'][0]['face_ids'].append(10000)
            else:claim['locality_work_reserved']-=1
            with self.subTest(mutate=mutate),self.assertRaises(AssertionError):replay(claim,changed,'target',edges)

    def test_exact_verifier_never_uses_producer_provenance(self):
        native,edges=source(cases()[1]);refine_boundary(native,edges,sliver=True)
        result=planner.choose(native,'target',edges,time.perf_counter_ns()+10**10)
        with patch.object(LocalSurfaceIndex,'proof',side_effect=AssertionError('producer forbidden')):
            replay(result,native,'target',edges)

    def test_boundary_split_does_not_change_feature_decision(self):
        case=sampling_case();before,edges=local_source(case)
        after,split=local_source(dict(case,split_edges=True))
        original=planner.choose(before,'target',edges,time.perf_counter_ns()+10**10)
        refined=planner.choose(after,'target',split,time.perf_counter_ns()+10**10)
        self.assertIsNone(original['selected'])
        self.assertIsNone(refined['selected'])
        self.assertEqual(len(refined['sampling_features']),4)
        replay(refined,after,'target',split)

    def test_visible_and_partially_blocked_cases_keep_the_same_feature_samples(self):
        for case in cases()[:3]:
            native,edges=local_source(dict(case,split_edges=True))
            result=planner.choose(native,'target',edges,time.perf_counter_ns()+10**10)
            with self.subTest(case=case['id']):
                self.assertEqual(len(edges),6)
                self.assertEqual(len(result['sampling_features']),4)
                self.assertEqual(len(result['selected']['samples']),12)
                self.assertEqual(result['selected']['visible_count'],case['pairs'])
                replay(result,native,'target',edges)

    def test_disconnected_same_object_shells_cannot_replace_hidden_original(self):
        native,edges=local_source(dict(cases()[1],occluding_shells=True))
        result=planner.choose(native,'target',edges,time.perf_counter_ns()+10**10)
        self.assertIsNone(result['selected'])
        self.assertTrue(all(row['visible_count']==0 for row in result['candidates']))
        replay(result,native,'target',edges)

    def test_feature_partition_tampering_is_rejected(self):
        import json
        native,edges=local_source(dict(cases()[1],split_edges=True))
        result=planner.choose(native,'target',edges,time.perf_counter_ns()+10**10)
        wire=json.loads(json.dumps(result))
        wire['selected']['local_surfaces'][0]['face_ids'].append(9999)
        with self.assertRaises(AssertionError):replay(wire,native,'target',edges)
        result['sampling_features'][0]['source_edges']*=2
        with self.assertRaises(AssertionError):replay(result,native,'target',edges)

    def test_index_reorder_and_reversed_boundary_keep_finite_decision(self):
        import random
        native,edges=local_source(dict(cases()[1],split_edges=True));obj=native['objects'][0]
        order=list(range(len(obj['world_vertices'])));random.Random(717).shuffle(order)
        inverse={old:new for new,old in enumerate(order)}
        obj['world_vertices']=[obj['world_vertices'][i] for i in order]
        obj['faces']=[[inverse[v] for v in face] for face in reversed(obj['faces'])]
        edges=[[inverse[b],inverse[a]] for a,b in reversed(edges)]
        result=planner.choose(native,'target',edges,time.perf_counter_ns()+10**10)
        self.assertEqual(result['selected']['visible_count'],12)
        self.assertEqual(len(result['sampling_features']),4)
        replay(result,native,'target',edges)

    def test_visual_mode_has_explicit_plane_and_normal_limits(self):
        for point,want in (([1.,1.,.0001],True),([1000.,1000.,.002],False),([.51,.51,.0001],False)):
            value=target();value['world_vertices'][3]=point
            with self.subTest(point=point):
                index=LocalSurfaceIndex(value,time.perf_counter_ns()+10**9,policy='visual_nearplanar')
                proof=index.proof([0,1],.1)
                self.assertEqual(1 in proof['face_ids'],want)
                independent=ExactLocalIndex(value,32768,'visual_nearplanar')
                self.assertEqual(proof,independent.reconstruct([0,1],.1))
        # The original strict mode remains distinct; no dimensions tolerance changes.
        value=target();value['world_vertices'][3][2]=.0001
        self.assertEqual(self.proof(value)[1]['face_ids'],[0])

    def test_source_bytes_and_locality_budget_are_enforced(self):
        native,edges=source(cases()[1]);native['oversized_metadata']='x'*(1024*1024)
        with self.assertRaisesRegex(ValueError,'source_bytes_budget'):
            planner.choose(native,'target',edges,time.perf_counter_ns()+10**9)
        native,edges=source(cases()[1])
        with self.assertRaisesRegex(ValueError,'work_budget'):
            planner.choose(native,'target',edges,time.perf_counter_ns()+10**9,max_locality_work=0)

    def test_real_new_corner_is_not_collapsed_as_sampling_refinement(self):
        native,edges=local_source(dict(cases()[1],split_edges=True))
        native['objects'][0]['world_vertices'][8][0]+=.00001
        result=planner.choose(native,'target',edges,time.perf_counter_ns()+10**10)
        self.assertGreater(len(result['sampling_features']),4)
        replay(result,native,'target',edges)


if __name__=='__main__':unittest.main()
