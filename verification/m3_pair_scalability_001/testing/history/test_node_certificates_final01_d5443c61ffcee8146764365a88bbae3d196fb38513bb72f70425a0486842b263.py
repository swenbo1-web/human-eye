"""Independent source-ID and exact triangle coverage checks for node pruning."""

from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from human_eye_plugin import surface_geometry as closed, surface_proximity as exact
from verification.test_surface_geometry import oracle as independent_intersection


HERE = Path(__file__).resolve().parent
CASES = json.loads((HERE/'NODE_CASES.json').read_bytes())
EVIDENCE = {}


def cross(a,b):
    return a[0]*b[1]-a[1]*b[0]


def sub(a,b):
    return tuple(x-y for x,y in zip(a,b))


def descendants(node):
    return list(node[3]) if node[3] is not None else descendants(node[4])+descendants(node[5])


def structure(case,budget):
    vertices = {i:tuple(int(F(value)*4) for value in point) for i,point in enumerate(case['vertices'])}
    faces = case['left']+case['right']
    bounds = [(tuple(min(vertices[i][k] for i in face) for k in range(3)),
               tuple(max(vertices[i][k] for i in face) for k in range(3))) for face in faces]
    left = closed._bvh(bounds,budget,list(range(len(case['left']))),leaf_size=1)
    right = closed._bvh(bounds,budget,list(range(len(case['left']),len(faces))),leaf_size=1)
    root = (tuple(min(left[0][k],right[0][k]) for k in range(3)),
        tuple(max(left[1][k],right[1][k]) for k in range(3)),len(faces),None,left,right)
    # Child nodes are real product BVHs over the exact source IDs. The joined
    # root is a valid coverage partition, independent of split heuristics.
    shell = {'candidate_vertices':vertices,'candidate_root':root,'faces':faces}
    return shell,left,right


def legal_intersection(points,first,second,vertices):
    shared = set(first)&set(second)
    if not points:
        return True
    if len(shared)==1:
        return all(point==vertices[next(iter(shared))] for point in points)
    if len(shared)!=2:
        return False
    a,b = (vertices[i] for i in sorted(shared))
    d = sub(b,a)
    norm = sum(x*x for x in d)
    if not norm:
        return all(point==a for point in points)
    for point in points:
        q = sub(point,a)
        product = (q[1]*d[2]-q[2]*d[1],q[2]*d[0]-q[0]*d[2],q[0]*d[1]-q[1]*d[0])
        if any(product) or not 0<=sum(x*y for x,y in zip(q,d))<=norm:
            return False
    return True


class NodeCertificateTests(unittest.TestCase):
    def assert_metadata(self,shell,metadata):
        nodes = {}
        def visit(node):
            nodes[id(node)] = node
            if node[3] is None:
                visit(node[4]);visit(node[5])
        visit(shell['candidate_root'])
        vertices = shell['candidate_vertices']
        facts = []
        for identity,anchors in metadata.items():
            faces = [shell['faces'][i] for i in descendants(nodes[identity])]
            for anchor,cone in anchors.items():
                self.assertTrue(all(anchor in face for face in faces))
                source_ids = set(i for face in faces for i in face)-{anchor}
                origin = vertices[anchor]
                rays = {i:sub(vertices[i][:2],origin[:2]) for i in source_ids}
                for face in faces:
                    a,b,c = [vertices[i][:2] for i in face]
                    self.assertNotEqual(cross(sub(b,a),sub(c,a)),0)
                self.assertGreater(cross(cone['lo'],cone['hi']),0)
                for ray in rays.values():
                    self.assertGreaterEqual(cross(cone['lo'],ray),0)
                    self.assertGreaterEqual(cross(ray,cone['hi']),0)
                for label,key in (('lo','lo_ids'),('hi','hi_ids')):
                    boundary = {i for i,ray in rays.items() if cross(cone[label],ray)==0
                        and sum(x*y for x,y in zip(cone[label],ray))>0}
                    self.assertEqual(set(cone[key]),boundary)
                facts.append({'descendant_faces':len(faces),'anchor':anchor,'lo_ids':sorted(cone['lo_ids']),
                    'hi_ids':sorted(cone['hi_ids'])})
        return facts

    def test_node_certificate_all_descendants_and_complete_source_ray_ids(self):
        for case in CASES['cases']:
            with self.subTest(case=case['id']):
                budget = closed._ClosedWork(lambda stage:None,{},exact)
                shell,left,right = structure(case,budget)
                metadata = closed._closed_cone_metadata(shell,budget)
                metadata_proof = self.assert_metadata(shell,metadata)
                certificate = closed._closed_node_simplex(left,right,metadata,shell['candidate_vertices'],budget)
                self.assertIs(certificate,case['certificate'])
                vertices = shell['candidate_vertices']
                illegal = []
                for i in descendants(left):
                    for j in descendants(right):
                        first,second = shell['faces'][i],shell['faces'][j]
                        points = independent_intersection(tuple(vertices[k] for k in first),tuple(vertices[k] for k in second))
                        if not legal_intersection(points,first,second,vertices):
                            illegal.append([i,j])
                self.assertIs(bool(illegal),case['illegal_pairs'])
                if certificate:
                    self.assertFalse(illegal)
                EVIDENCE[case['id']] = {'certificate':certificate,'independent_illegal_pairs':illegal,
                    'metadata_proof':metadata_proof,'work':dict(budget.counts)}

    def test_node_metadata_bit_fallback_and_original_interruptions(self):
        case = CASES['cases'][0]
        budget = closed._ClosedWork(lambda stage:None,{},exact)
        shell,left,right = structure(case,budget)
        with patch.object(closed,'_closed_cone_cross',side_effect=exact._DomainError('surface_exact_bit_budget')):
            metadata = closed._closed_cone_metadata(shell,budget)
        self.assertFalse(metadata)
        self.assertGreater(budget.counts['cone_bit_fallbacks'],0)
        self.assertFalse(closed._closed_node_simplex(left,right,metadata,shell['candidate_vertices'],budget))
        for exception in (RuntimeError('original cancellation'),TimeoutError('original deadline'),
                          closed._ClosedDomain('closed_solid_work_budget')):
            with self.subTest(error=type(exception).__name__):
                budget = closed._ClosedWork(lambda stage:None,{},exact)
                shell,left,right = structure(case,budget)
                with patch.object(closed,'_closed_cone_cross',side_effect=exception):
                    with self.assertRaises(type(exception)) as raised:
                        closed._closed_cone_metadata(shell,budget)
                self.assertIs(raised.exception,exception)
        budget = closed._ClosedWork(lambda stage:None,{},exact)
        shell,left,right = structure(case,budget)
        budget.counts['work_units'] = 262144
        with self.assertRaisesRegex(closed._ClosedDomain,'^closed_solid_work_budget$'):
            closed._closed_cone_metadata(shell,budget)
        EVIDENCE['node_guards'] = {'exact_bit_guard_falls_back':True,'original_exceptions_propagate':True,
            'total_work_budget_unchanged':262144}

    def test_independent_public_witness_certificate_membership_and_distance(self):
        path = HERE/'witness_oracle.py'
        spec = importlib.util.spec_from_file_location('_m3_public_witness_certificate',path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        raw = {'vertices_world':[[0.,0.,0.],[2.,0.,0.],[0.,2.,0.]],'triangles':[[0,1,2]]}
        for point,passed in (([.5,.5,0.],True),([1.,1.,0.],True),([.5,.5,.5e-9],True),
                             ([.5,.5,2e-9],False),([2.,2.,0.],False)):
            self.assertIs(module.certify_point(point,raw,tolerance_m=1e-9)['passed'],passed)
        second = {'vertices_world':[[x,y,z+1] for x,y,z in raw['vertices_world']],'triangles':raw['triangles']}
        valid = module.certify_pair([.5,.5,0.],[.5,.5,1.],1.,raw,second)
        invalid = module.certify_pair([.5,.5,0.],[.5,.5,1.],1.01,raw,second)
        self.assertTrue(valid['passed'])
        self.assertFalse(invalid['passed'])
        EVIDENCE['public_witness_oracle'] = {'valid':valid,'wrong_distance':invalid,
            'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
