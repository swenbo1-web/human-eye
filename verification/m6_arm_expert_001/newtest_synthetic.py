"""Analytic checks of the fixed synthetic construction, not model training."""
from collections import Counter, defaultdict
import math
import unittest

from verification.m6_arm_expert_001.synthetic import generate_dataset


def area(points):
    center=[math.fsum(p[k] for p in points)/len(points) for k in range(3)]
    relative=[[p[k]-center[k] for k in range(3)] for p in points]
    normal=[math.fsum(a[(k+1)%3]*b[(k+2)%3]-a[(k+2)%3]*b[(k+1)%3]
              for a,b in zip(relative,relative[1:]+relative[:1])) for k in range(3)]
    return math.sqrt(math.fsum(v*v for v in normal))/2


def rigid_skin_point(rest,pose,vertex):
    # Independent rigid inverse (transpose), not the producer's cofactor inverse.
    local=[math.fsum(rest[k][i]*(vertex[k]-rest[k][3]) for k in range(3)) for i in range(3)]
    return [math.fsum(pose[i][k]*local[k] for k in range(3))+pose[i][3] for i in range(3)]


class SyntheticConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.cases=generate_dataset()

    def test_exact_packet_domain_finite_closed_topology_and_over256_patch(self):
        fields={'schema','unit','rest_vertices','current_vertices','triangles','weights',
                'bone_chain','sections','vertex_ids'}
        for case in self.cases:
            packet=case['packet'];self.assertEqual(set(packet),fields)
            self.assertEqual(packet['schema'],'arm-twist-patch-v1');self.assertEqual(packet['unit'],'m')
            self.assertEqual(len(packet['rest_vertices']),402)
            self.assertEqual(len(packet['current_vertices']),402)
            self.assertEqual(len(set(packet['vertex_ids'])),402)
            self.assertTrue(all(type(v) is int and v>=0 for v in packet['vertex_ids']))
            self.assertEqual(len(packet['sections']),25)
            self.assertTrue(all(len(section)==16 and len(set(section))==16 for section in packet['sections']))
            self.assertTrue(all(math.isfinite(v) for name in ('rest_vertices','current_vertices') for p in packet[name] for v in p))
            self.assertTrue(all(len(w)==len(packet['bone_chain']) and min(w)>=0 and abs(sum(w)-1)<1e-12 for w in packet['weights']))
            edges=Counter();directed=Counter()
            for face in packet['triangles']:
                self.assertEqual(len(face),3);self.assertTrue(all(0<=i<402 for i in face))
                for a,b in zip(face,face[1:]+face[:1]):edges[tuple(sorted((a,b)))]+=1;directed[a,b]+=1
            self.assertTrue(all(n==2 for n in edges.values()))
            self.assertTrue(all(directed[a,b]==directed[b,a] for a,b in edges))

    def test_asset_poses_and_all_three_family_marginals_are_split_disjoint(self):
        groups=defaultdict(list)
        for case in self.cases:groups[case['metadata']['asset_id']].append(case)
        self.assertEqual(len(groups),11)
        self.assertEqual(Counter(c['metadata']['split'] for c in self.cases),{'train':56,'validation':7,'test':14})
        for rows in groups.values():
            self.assertEqual(len(rows),7)
            self.assertEqual(len({c['metadata']['split'] for c in rows}),1)
            self.assertTrue(all(c['packet']['rest_vertices']==rows[0]['packet']['rest_vertices'] for c in rows))
        for field in ('shape_family','skeleton_family','weight_family'):
            families={split:{c['metadata'][field] for c in self.cases if c['metadata']['split']==split}
                      for split in ('train','validation','test')}
            for a,b in (('train','validation'),('train','test'),('validation','test')):
                self.assertFalse(families[a]&families[b])

    def test_same_angle_controls_have_identical_bones_weights_and_opposite_labels(self):
        pairs=defaultdict(dict)
        for case in self.cases:
            family=case['metadata']['pose_family']
            if family in ('anomalous_twist','same_angle_preserved'):pairs[case['metadata']['pair_id']][family]=case
        self.assertEqual(len(pairs),22)
        for pair in pairs.values():
            self.assertEqual(set(pair),{'anomalous_twist','same_angle_preserved'})
            bad,normal=pair['anomalous_twist'],pair['same_angle_preserved']
            for field in ('rest_vertices','bone_chain','weights','sections','triangles','vertex_ids'):
                self.assertEqual(bad['packet'][field],normal['packet'][field])
            self.assertGreater(max(bad['label_severity']),.4)
            self.assertEqual(normal['label_severity'],[0.]*25)
            self.assertNotEqual(bad['packet']['current_vertices'],normal['packet']['current_vertices'])
            self.assertEqual(bad['reference_vertices'],normal['packet']['current_vertices'])

    def test_every_lbs_vertex_matches_independent_rigid_inverse_recalculation(self):
        for case in self.cases:
            if case['metadata']['pose_family']=='same_angle_preserved':continue
            packet=case['packet']
            for rest,actual,weights in zip(packet['rest_vertices'],packet['current_vertices'],packet['weights']):
                expected=[0.,0.,0.]
                for bone,w in zip(packet['bone_chain'],weights):
                    posed=rigid_skin_point(bone['rest_matrix'],bone['pose_matrix'],rest)
                    for k in range(3):expected[k]+=w*posed[k]
                self.assertLess(max(abs(a-b) for a,b in zip(actual,expected)),2e-12)

    def test_axial_reference_preserves_independent_polygon_area(self):
        for case in self.cases:
            if case['metadata']['pose_family']=='normal_bend':continue
            packet=case['packet']
            for section in packet['sections']:
                rest=area([packet['rest_vertices'][i] for i in section])
                reference=area([case['reference_vertices'][i] for i in section])
                self.assertGreater(rest,1e-6)
                self.assertAlmostEqual(reference/rest,1.,delta=2e-12)

    def test_severe_labels_match_independent_constructed_section_loss(self):
        for case in self.cases:
            if case['metadata']['pose_family']!='anomalous_twist':continue
            packet=case['packet']
            for section,label in zip(packet['sections'],case['label_severity']):
                reference=area([case['reference_vertices'][i] for i in section])
                current=area([packet['current_vertices'][i] for i in section])
                self.assertAlmostEqual(max(0.,1-current/reference),label,delta=2e-12)
            peak=max(range(25),key=case['label_severity'].__getitem__)
            center=[sum(packet['rest_vertices'][i][k] for i in packet['sections'][peak])/16 for k in range(3)]
            joint=packet['bone_chain'][case['metadata']['joint_index']]['rest_matrix']
            first=[sum(packet['rest_vertices'][i][k] for i in packet['sections'][0])/16 for k in range(3)]
            last=[sum(packet['rest_vertices'][i][k] for i in packet['sections'][-1])/16 for k in range(3)]
            length=math.dist(first,last)
            self.assertLessEqual(math.dist(center,[joint[k][3] for k in range(3)]),length/48+1e-12)

    def test_nominal_zero_labels_do_not_deny_real_bend_or_small_twist_area_change(self):
        for family in ('normal_bend','legal_twist'):
            rows=[c for c in self.cases if c['metadata']['pose_family']==family]
            self.assertTrue(all(c['label_severity']==[0.]*25 for c in rows))
            losses=[]
            for case in rows:
                p=case['packet']
                losses.extend(1-area([p['current_vertices'][i] for i in s])/area([p['rest_vertices'][i] for i in s]) for s in p['sections'])
            self.assertGreater(max(losses),.01)


if __name__=='__main__':unittest.main(verbosity=2)
