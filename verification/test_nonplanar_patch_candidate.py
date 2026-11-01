import copy,math,time,unittest
from unittest.mock import patch
from verification import nonplanar_patch_candidate as p
from verification.nonplanar_patch_fixtures import cases,source


def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def subtract(a,b):return [x-y for x,y in zip(a,b)]
def ray(native,point,direction):
    """3D Moller line intersection; no producer projection or depth routine."""
    hits=[]
    for obj in native['objects']:
        for index,face in enumerate(obj['faces']):
            a,b,c=[obj['world_vertices'][i] for i in face];e1=subtract(b,a);e2=subtract(c,a)
            h=cross(direction,e2);det=dot(e1,h)
            if abs(det)<=1e-12*max(math.hypot(*e1)*math.hypot(*e2),1e-300):continue
            s=subtract(point,a);u=dot(s,h)/det;q=cross(s,e1);v=dot(direction,q)/det
            if min(u,v,1-u-v)<-1e-12:continue
            hits.append((dot(e2,q)/det,obj['object_id'],index))
    if not hits:return []
    depth=max(h[0] for h in hits);eps=1e-9*max(1.,abs(depth))
    return [(obj,index) for z,obj,index in hits if depth-z<=eps]


def replay(result,native,object_id,edges):
    """Rebuild each proposed view's offsets and independently replay all rays."""
    vertices=next(o['world_vertices'] for o in native['objects'] if o['object_id']==object_id)
    faces=next(o['faces'] for o in native['objects'] if o['object_id']==object_id);reserved=0
    for row in result['candidates']:
        if not row['tests_reserved']:continue
        rebuilt=[];visible=[]
        for a,b in edges:
            delta=subtract(vertices[b],vertices[a]);x=dot(delta,row['right']);y=dot(delta,row['up']);length=math.sqrt(x*x+y*y)
            assert length>row['span']/64
            off=[row['span']/128/length*(-y*row['right'][k]+x*row['up'][k]) for k in range(3)]
            incident={(object_id,i) for i,f in enumerate(faces) if a in f and b in f};assert len(incident)==1
            for num in (1,2,3):
                mid=[(vertices[a][k]*(4-num)+vertices[b][k]*num)/4 for k in range(3)]
                pair=[[mid[k]+sign*off[k] for k in range(3)] for sign in (-1,1)]
                h0,h1=[ray(native,q,row['direction']) for q in pair]
                value=(not h0 and set(h1)==incident) or (not h1 and set(h0)==incident)
                rebuilt.append(pair);visible.append(bool(value))
        assert len(rebuilt)==len(row['samples'])
        for sample,pair,v in zip(row['samples'],rebuilt,visible):
            assert sample['visible']==v
            assert all(abs(x-y)<=row['span']*1e-10 for a,b in zip(sample['pair'],pair) for x,y in zip(a,b))
        assert sum(visible)==row['visible_count']
        reserved+=row['tests_reserved']
    assert reserved==result['combined_triangle_tests_reserved']<=8192
    assert len(result['candidates'])<=4 and result['maximum_images']==2 and result['execution_authority'] is False
    return reserved


class NonplanarCandidateTests(unittest.TestCase):
    def test_seven_fixed_cases_independent_rays(self):
        for case in cases():
            native,edges=source(case);result=p.choose(native,'target',edges,time.perf_counter_ns()+30_000_000_000)
            with self.subTest(case=case['id']):
                self.assertEqual(result['selected'] is not None,case['want'])
                if result['selected']:self.assertEqual(result['selected']['visible_count'],case['pairs'])
                with patch.object(p,'projected_hit',side_effect=AssertionError('verifier cannot use producer rays')):
                    replay(result,native,'target',edges)

    def test_budget_reserved_before_scanning_and_search_is_partial(self):
        native,edges=source(cases()[1])
        with patch.object(p,'projected_hit',side_effect=AssertionError('no rays allowed')):
            value=p.choose(native,'target',edges,time.perf_counter_ns()+30_000_000_000,max_tests=0)
        self.assertFalse(value['search_complete']);self.assertIsNone(value['selected']);self.assertEqual(value['combined_triangle_tests_reserved'],0)

    def test_unrelated_target_surface_cannot_impersonate_local_edge(self):
        native,edges=source(cases()[1]);target=native['objects'][0]
        # A remote same-object sheet in front of the aperture is not an incident face.
        base=len(target['world_vertices']);target['world_vertices'] += [[2,-.2,-.2],[2,.2,-.2],[2,.2,.2],[2,-.2,.2]]
        target['faces'] += [[base,base+1,base+2],[base,base+2,base+3]]
        point=[0,0,0];r,u,d=p.axes([1,0,0]);hits=p.projected_hit(native,point,r,u,d)
        self.assertTrue(all(i>=8 for obj,i in hits if obj=='target'))
        self.assertEqual(set(hits),set(ray(native,point,d)))

    def test_deadline_geometry_and_edge_limits(self):
        native,edges=source(cases()[1])
        with self.assertRaisesRegex(ValueError,'deadline'):p.choose(native,'target',edges,time.perf_counter_ns()-1)
        with self.assertRaisesRegex(ValueError,'boundary_budget'):p.choose(native,'target',edges*17,time.perf_counter_ns()+10**9)
        native['objects'][0]['faces']*=257
        with self.assertRaisesRegex(ValueError,'geometry_budget'):p.choose(native,'target',edges,time.perf_counter_ns()+10**9)

    def test_normal_cancellation_and_nonfinite_refuse(self):
        native,edges=source(cases()[1]);target=native['objects'][0]
        # Use a planar symmetric ring; one horizontal plus one vertical incident face
        # balances the opposite equal-area pair when their winding is reversed.
        for point in target['world_vertices']:point[0]=0.
        adjacent=[i for i,f in enumerate(target['faces']) if any(a in f and b in f for a,b in edges)]
        for i in adjacent[:2]:target['faces'][i].reverse()
        normals=[cross(subtract(target['world_vertices'][f[1]],target['world_vertices'][f[0]]),
            subtract(target['world_vertices'][f[2]],target['world_vertices'][f[0]])) for i,f in enumerate(target['faces']) if i in adjacent]
        self.assertLess(math.hypot(*(sum(n[k] for n in normals) for k in range(3))),1e-12)
        with self.assertRaisesRegex(ValueError,'normal_cancellation'):p.choose(native,'target',edges,time.perf_counter_ns()+10**9)
        native,edges=source(cases()[1]);native['objects'][0]['world_vertices'][4][0]=float('nan')
        with self.assertRaises(ValueError):p.choose(native,'target',edges,time.perf_counter_ns()+10**9)

    def test_tamper_independent_replay_rejects(self):
        native,edges=source(cases()[1]);result=p.choose(native,'target',edges,time.perf_counter_ns()+10**9)
        row=next(r for r in result['candidates'] if r['samples']);row['samples'][0]['visible']=not row['samples'][0]['visible']
        with self.assertRaises(AssertionError):replay(result,native,'target',edges)

    def test_old_gate_rejects_planar_rim_because_body_is_curved(self):
        from human_eye_plugin import patch_focus as old
        native,edges=source(cases()[0]);vertices=native['objects'][0]['world_vertices']
        unrotated=[[-v[2],v[1],v[0]] for v in vertices]
        native['objects'][0]['world_vertices']=unrotated
        self.assertTrue(all(unrotated[i][2]==0 for i in (4,5,6,7)))
        prepared=dict(raw=dict(vertices=unrotated,edges=edges,unit_scale=1.,
            matrix_world=[[1.,0,0,0],[0,1.,0,0],[0,0,1.,0],[0,0,0,1.]]),source={'object_id':'target'})
        patch_value=dict(category='boundary_edges',element_kind='edge',source_indices=list(range(4)),position={'status':'known'})
        with self.assertRaisesRegex(ValueError,'planar_XY_target_required'):old.geometry(prepared,patch_value,native)


if __name__=='__main__':unittest.main()
