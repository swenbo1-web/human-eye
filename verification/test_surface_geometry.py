"""Exact analytic and independent edge-plane oracles, no private assets."""
import copy,itertools,random,unittest
from fractions import Fraction as Q
from human_eye_plugin import mesh_structure as raw,surface_geometry as g

IDENTITY=dict(object_id='target',object_instance='instance',document_epoch='document',capture_id='capture')
MATRIX=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]


def prepared(vertices,triangles,matrix=None,scale=1):
    edges=sorted({tuple(sorted(e)) for t in triangles for e in zip(t,t[1:]+t[:1])})
    value=dict(vertices=[list(p) for p in vertices],edges=[list(e) for e in edges],polygons=[list(t) for t in triangles],
        matrix_world=copy.deepcopy(matrix or MATRIX),unit_scale=scale)
    return raw.prepare_raw(value,IDENTITY)


def analyze(vertices,triangles,**kwargs):
    return g.analyze(prepared(vertices,triangles),triangles,list(range(len(triangles))),budget=raw.WorkBudget(),**kwargs)


def oracle(a,b):
    """Independent 6 segment/plane tests; coplanar segment half-plane clipping.

    Never invokes the production polygon clip or plane slice implementation.
    """
    def minus(a,b):return tuple(a[k]-b[k] for k in range(3))
    def dot(a,b):return sum(a[k]*b[k] for k in range(3))
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    def inside(p,t,n):return all(dot(cross(minus(t[(i+1)%3],t[i]),minus(p,t[i])),n)>=0 for i in range(3))
    witnesses=[]
    for t,u in ((a,b),(b,a)):
        n=cross(minus(u[1],u[0]),minus(u[2],u[0]))
        for i,p in enumerate(t):
            q=t[(i+1)%3];dp,dq=dot(n,minus(p,u[0])),dot(n,minus(q,u[0]))
            if dp==dq==0:
                low,high=Q(0),Q(1);direction=minus(q,p)
                for j in range(3):
                    e=minus(u[(j+1)%3],u[j]);c=dot(cross(e,minus(p,u[j])),n);d=dot(cross(e,direction),n)
                    if d==0:
                        if c<0:low,high=Q(1),Q(0);break
                    elif d>0:low=max(low,-Q(c,d))
                    else:high=min(high,-Q(c,d))
                if low<=high:
                    for s in (low,high):witnesses.append(tuple(p[k]+s*direction[k] for k in range(3)))
            elif dp*dq<=0 and dp!=dq:
                s=Q(dp,dp-dq);x=tuple(p[k]+s*(q[k]-p[k]) for k in range(3))
                if inside(x,u,n):witnesses.append(x)
    return set(witnesses)


class GeometryTests(unittest.TestCase):
    def test_crossing_closed_shells_not_topology_health(self):
        vertices=[[-1,0,0],[1,0,0],[0,1,0],[0,-1,-1],[0,-1,1],[0,1,0]]
        result=analyze(vertices,[[0,1,2],[3,4,5]],near_m=0)
        self.assertTrue(result['scan_complete']);self.assertEqual(result['total'],1)
        self.assertEqual(result['regions'][0]['kind'],'contact_line')
        self.assertEqual(result['regions'][0]['relation'],'transverse_crossing')

    def test_common_edge_legal_and_fold_overlap_not_ignored(self):
        vertices=[[0,0,0],[1,0,0],[0,1,0],[0,-1,0]]
        self.assertEqual(analyze(vertices,[[0,1,2],[1,0,3]])['total'],0)
        vertices[3]=[0,.5,0]
        self.assertEqual(analyze(vertices,[[0,1,2],[1,0,3]])['regions'][0]['kind'],'contact_area')

    def test_shared_vertex_does_not_hide_overlap_elsewhere(self):
        vertices=[[0,0,0],[2,0,0],[0,2,0],[1,0,0],[0,1,0]]
        self.assertEqual(analyze(vertices,[[0,1,2],[0,3,4]])['total'],1)

    def test_shared_vertex_only_is_legal(self):
        self.assertEqual(analyze([[0,0,0],[1,0,0],[0,1,0],[-1,0,0],[0,-1,0]],[[0,1,2],[0,3,4]])['total'],0)

    def test_duplicate_face_reported(self):
        self.assertEqual(analyze([[0,0,0],[1,0,0],[0,1,0]],[[0,1,2],[2,1,0]])['regions'][0]['kind'],'contact_area')

    def test_nonadjacent_point_is_contact_not_damage(self):
        r=analyze([[0,0,0],[1,0,0],[0,1,0],[0,0,0],[-1,0,0],[0,-1,0]],[[0,1,2],[3,4,5]])
        self.assertEqual(r['regions'][0]['kind'],'contact_point');self.assertEqual(r['damage_classification'],'not_inferred')
        self.assertEqual(r['counts_by_relation']['transverse_crossing'],0)

    def test_boundary_contact_overflow_does_not_hide_crossing(self):
        vertices=[];triangles=[]
        for i in range(130):
            x=i*4;offset=len(vertices)
            vertices += [[x,0,0],[x+1,0,0],[x,1,0],[x,0,0],[x-1,0,0],[x,-1,0]]
            triangles += [[offset,offset+1,offset+2],[offset+3,offset+4,offset+5]]
        offset=len(vertices);vertices += [[600-1,0,0],[600+1,0,0],[600,1,0],[600,-1,-1],[600,-1,1],[600,1,0]]
        triangles += [[offset,offset+1,offset+2],[offset+3,offset+4,offset+5]]
        r=analyze(vertices,triangles,near_m=0)
        self.assertTrue(r['scan_complete']);self.assertEqual(r['counts_by_relation']['boundary_contact'],130)
        self.assertEqual(r['counts_by_relation']['transverse_crossing'],1)
        self.assertEqual(r['regions'][0]['relation'],'transverse_crossing');self.assertEqual(r['omitted'],3)

    def test_parallel_gap_and_exact_threshold(self):
        vertices=[[0,0,0],[1,0,0],[0,1,0],[0,0,2**-20],[1,0,2**-20],[0,1,2**-20]]
        triangles=[[0,1,2],[3,4,5]]
        self.assertEqual(analyze(vertices,triangles,near_m=2**-20)['regions'][0]['kind'],'near_parallel_overlap')
        self.assertEqual(analyze(vertices,triangles,near_m=2**-21)['total'],0)

    def test_nonparallel_nearness_explicitly_unchecked(self):
        r=analyze([[0,0,0],[1,0,0],[0,1,0]],[[0,1,2]])
        self.assertIn('nonparallel_near_distance',r['not_checked'])

    def test_degenerate_not_clean(self):
        r=analyze([[0,0,0],[1,0,0],[2,0,0]],[[0,1,2]])
        self.assertEqual(r['status'],'partial');self.assertIsNone(r['total'])

    def test_wrong_tessellation_refused(self):
        p=prepared([[0,0,0],[1,0,0],[0,1,0]],[[0,1,2]])
        for triangles,indices in (([],[]),([[0,1,2]],[1]),([[0,0,1]],[0])):
            with self.assertRaises(ValueError):g.analyze(p,triangles,indices,budget=raw.WorkBudget())

    def test_source_limits_and_singular(self):
        p=prepared([[0,0,0],[1,0,0],[0,1,0]],[[0,1,2]]);p['raw']['matrix_world'][0][0]=0
        with self.assertRaisesRegex(ValueError,'singular'):g.analyze(p,[[0,1,2]],[0],budget=raw.WorkBudget())
        with self.assertRaisesRegex(ValueError,'geometry_budget'):g.validate_tessellation({'vertices':[],'polygons':[]},[[]]*4097,[],raw.WorkBudget())

    def test_work_stop_and_display_truncation_distinct(self):
        p=prepared([[0,0,0],[1,0,0],[0,1,0]]*20,[[3*i,3*i+1,3*i+2] for i in range(20)])
        t=p['raw']['polygons'];r=g.analyze(p,t,list(range(20)),budget=raw.WorkBudget())
        self.assertEqual(r['total'],190);self.assertEqual(r['delivered'],128);self.assertEqual(r['omitted'],62)
        r=g.analyze(p,t,list(range(20)),budget=raw.WorkBudget(max_work=500))
        self.assertFalse(r['scan_complete']);self.assertIsNone(r['total'])

    def test_exact_dyadic_transform_preserves_contacts(self):
        p=prepared([[0,0,0],[1,0,0],[0,1,0]]*2,[[0,1,2],[3,4,5]])
        p['raw']['matrix_world'][0][3]=2**40;p['raw']['unit_scale']=2**-12
        self.assertEqual(g.analyze(p,p['raw']['polygons'],[0,1],budget=raw.WorkBudget())['total'],1)

    def test_independent_random_oracle_including_coplanar(self):
        rng=random.Random(392471);examined=0
        for flat in (False,True):
            for _ in range(400):
                a=tuple(tuple(Q(rng.randrange(-4,5)) if k!=2 or not flat else Q(0) for k in range(3)) for _ in range(3))
                b=tuple(tuple(Q(rng.randrange(-4,5)) if k!=2 or not flat else Q(0) for k in range(3)) for _ in range(3))
                if not any(g.normal(a)) or not any(g.normal(b)):continue
                expected=oracle(a,b);actual=g.intersection(a,b,raw.WorkBudget())
                self.assertEqual(bool(expected),bool(actual),(a,b,expected,actual))
                if expected:self.assertEqual(g.dimension(list(expected)),g.dimension(actual),(a,b))
                examined+=1
        self.assertGreater(examined,600)

    def test_bvh_candidate_coverage_against_independent_all_pairs(self):
        rng=random.Random(70123)
        for count in (0,1,4,5,17,40):
            for pad in (0,1,4):
                bounds=[]
                for _ in range(count):
                    lo=tuple(rng.randrange(-10,10) for _ in range(3));hi=tuple(x+rng.randrange(0,6) for x in lo);bounds.append((lo,hi))
                stats=dict(node_pair_visits=0,leaf_pair_visits=0,aabb_pruned_pairs=0)
                actual=list(g.candidate_pairs(bounds,pad,raw.WorkBudget(),stats))
                expected={(i,j) for i in range(count) for j in range(i+1,count)
                    if all(bounds[i][0][k]<=bounds[j][1][k]+pad and bounds[j][0][k]<=bounds[i][1][k]+pad for k in range(3))}
                self.assertEqual(set(actual),expected);self.assertEqual(len(actual),len(set(actual)))
                self.assertEqual(stats['aabb_pruned_pairs']+len(actual),count*(count-1)//2)


if __name__=='__main__':unittest.main()
