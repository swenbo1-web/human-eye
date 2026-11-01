"""Index correctness comes from independent exact bounds and full rays."""
import copy
import json
import math
import random
import time
import unittest
from unittest.mock import patch

from verification import nonplanar_dense_candidate as p
from verification.nonplanar_dense_fixtures import dense_case,dense_source
from verification.nonplanar_local_fixtures import local_cases,local_source
from verification.nonplanar_triangle_index import IndexBudget,IndexBudgetError,build_index,traverse
from verification.nonplanar_triangle_validation import validate_index,validate_query
from verification.nonplanar_dense_validation import replay,ray
from fractions import Fraction as Q


def choose(native,edges,**kw):
    return p.choose(native,'target',edges,time.perf_counter_ns()+30_000_000_000,
        locality_policy='visual_nearplanar',**kw)


def overlap_source(count=1800,boundary=4):
    if boundary==4:
        case=dense_case(0);case.pop('grid_n')
        native,edges=dense_source(case);native['objects'][0]['faces']=native['objects'][0]['faces'][:8]
        native['objects'][0]['world_vertices']=native['objects'][0]['world_vertices'][:8]
    else:
        points=[]
        for radius in (1.,.1):
            for i in range(boundary):
                angle=2*math.pi*i/boundary;points.append([0.,radius*math.cos(angle),radius*math.sin(angle)])
        faces=[]
        for i in range(boundary):
            j=(i+1)%boundary
            faces.extend([[i,j,boundary+j],[i,boundary+j,boundary+i]])
        native={'objects':[{'object_id':'target','world_vertices':points,'faces':faces}]}
        edges=[[boundary+i,boundary+(i+1)%boundary] for i in range(boundary)]
    native['objects'].append({'object_id':'overlap','world_vertices':[[.2,-2.,-2.],[.2,2.,-2.],[.2,0.,2.]],
        'faces':[[0,1,2] for _ in range(count)]})
    return native,edges


class NonplanarTriangleIndexTests(unittest.TestCase):
    def test_existing_fourteen_scenarios_keep_their_decisions(self):
        for case in local_cases():
            native,edges=local_source(case);result=choose(native,edges)
            with self.subTest(case=case['id']):
                self.assertEqual(result['selected'] is not None,case['want'])
                replay(result,native,'target',edges)

    def test_single_object_density_recovers_under_original_ray_budget(self):
        for n in (10,12,16,24,30):
            native,edges=dense_source(dense_case(n));result=choose(native,edges)
            with self.subTest(n=n):
                self.assertEqual(result['selected']['visible_count'],12)
                self.assertTrue(result['search_complete'])
                self.assertLessEqual(result['combined_triangle_tests_reserved'],8192)
                replay(json.loads(json.dumps(result)),native,'target',edges)

    def test_true_dense_occluder_is_retained(self):
        for n in (12,30):
            native,edges=dense_source(dense_case(n,'blocker'));result=choose(native,edges)
            self.assertIsNone(result['selected']);self.assertTrue(result['search_complete'])
            replay(result,native,'target',edges)

    def test_pointwise_hits_equal_unfiltered_producer_and_independent_rays(self):
        native,edges=dense_source(dense_case(6));result=choose(native,edges,acceleration='force')
        for row in result['candidates']:
            accel=row.get('acceleration')
            if accel is None:continue
            for query in accel['queries']:
                full=p.projected_hit(native,query['point'],row['right'],row['up'],row['direction'],query['possible_objects'])
                reduced=p.projected_hit(native,query['point'],row['right'],row['up'],row['direction'],query['possible_objects'],allowed_faces=query['filters'])
                independent=ray(native,query['point'],row['direction'],query['possible_objects'])
                self.assertEqual(set(full),set(reduced))
                self.assertEqual(set(reduced),set(independent))

    def test_node_bounds_face_partition_and_active_pruning_tampering_rejected(self):
        native,edges=dense_source(dense_case(12));original=choose(native,edges)
        for mode in ('bounds','missing_face','duplicate_face','cycle','false_prune','source','basis','meter'):
            result=json.loads(json.dumps(original));row=next(r for r in result['candidates'] if r.get('acceleration'))
            accel=row['acceleration'];index=next(iter(accel['indices'].values()))
            leaf=next(n for n in index['nodes'] if n[4]==-1)
            if mode=='bounds':leaf[:4]=[0.,0.,0.,0.]
            elif mode=='missing_face':leaf[6].pop()
            elif mode=='duplicate_face':leaf[6].append(leaf[6][0])
            elif mode=='cycle':index['nodes'][0][4]=0
            elif mode=='source':index['source_binding']='0'*64
            elif mode=='basis':index['right']=[0.,0.,0.]
            elif mode=='meter':result['index_node_tests_reserved']-=2
            else:
                query=next(q for q in accel['queries'] if any(q['filters'].values()))
                name=next(iter(query['traces']));query['traces'][name][0][1]=False
            # This test is about the row certificate, including serialized
            # selected copies; keep its selected payload consistent first.
            if result['selected'] is not None and result['selected']['direction']==row['direction']:
                result['selected']=copy.deepcopy(row)
            with self.subTest(mode=mode),self.assertRaises((AssertionError,ValueError,IndexError)):
                replay(result,native,'target',edges)

    def test_source_mutations_invalidate_reuse_without_a_persistent_cache(self):
        native,edges=dense_source(dense_case(12));before=choose(native,edges)
        for mode in ('vertex','topology','identity','units','display'):
            changed=copy.deepcopy(native)
            if mode=='vertex':changed['objects'][0]['world_vertices'][-1][0]+=.001
            elif mode=='topology':changed['objects'][0]['faces'][-1].reverse()
            elif mode=='identity':changed['document_epoch']='recreated-same-names'
            elif mode=='units':changed['unit_scale']=.001
            else:changed['objects'][0]['color']=[.1,.2,.3,1.]
            with self.subTest(mode=mode),self.assertRaises(AssertionError):replay(before,changed,'target',edges)
            fresh=choose(changed,edges)
            self.assertNotEqual(before['native_binding_sha256'],fresh['native_binding_sha256'])
            replay(fresh,changed,'target',edges)

    def test_build_memory_and_packet_limits_never_restore_a_free_budget(self):
        native,edges=dense_source(dense_case(12))
        for options in ({'max_build':0},{'max_nodes':0},{'max_bytes':0}):
            if options.get('max_bytes')==0:
                # No certificate byte can be emitted under a zero-byte grant.
                # The explicit unknown exception is preferable to a free retry.
                with self.assertRaisesRegex(IndexBudgetError,'packet_budget'):choose(native,edges,index_limits=options)
                continue
            result=choose(native,edges,index_limits=options)
            self.assertIsNone(result['selected']);self.assertFalse(result['search_complete'])
            self.assertTrue(any('budget' in r['reason'] for r in result['candidates']))
            replay(result,native,'target',edges)

    def test_all_overlap_returns_unknown_or_blocked_within_original_limits(self):
        native,edges=overlap_source(1200);result=choose(native,edges)
        self.assertIsNone(result['selected']);self.assertFalse(result['search_complete'])
        self.assertLessEqual(result['combined_triangle_tests_reserved'],8192)
        replay(result,native,'target',edges)

    def test_partial_traversal_never_publishes_visibility(self):
        native,edges=overlap_source(1800,64);result=choose(native,edges)
        self.assertIsNone(result['selected']);self.assertFalse(result['search_complete'])
        self.assertTrue(any(r['reason']=='triangle_index_traversal_budget' for r in result['candidates']))
        self.assertTrue(all(not r['samples'] for r in result['candidates']))
        replay(result,native,'target',edges)

    def test_verifier_does_not_call_builder_traversal_or_producer_intersections(self):
        native,edges=dense_source(dense_case(12));result=choose(native,edges)
        with patch('verification.nonplanar_triangle_index.build_index',side_effect=AssertionError('builder forbidden')), \
             patch('verification.nonplanar_triangle_index.traverse',side_effect=AssertionError('traversal forbidden')), \
             patch.object(p,'projected_hit',side_effect=AssertionError('producer ray forbidden')):
            replay(result,native,'target',edges)

    def test_input_unchanged_and_small_fast_path_uses_no_index(self):
        case=local_cases()[1];native,edges=local_source(case);before=copy.deepcopy(native)
        result=choose(native,edges)
        self.assertEqual(native,before)
        self.assertNotIn('index_build_reservations',result)
        self.assertEqual(result.get('index_build_units_reserved',0),0)
        self.assertEqual(result.get('index_node_tests_reserved',0),0)

    def test_legacy_default_import_does_not_load_or_route_to_index(self):
        import subprocess,sys
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        code='import sys;sys.path.insert(0,'+repr(str(root))+');from verification import nonplanar_patch_candidate;assert "verification.nonplanar_triangle_index" not in sys.modules;assert "verification.nonplanar_dense_candidate" not in sys.modules'
        completed=subprocess.run([sys.executable,'-I','-B','-c',code],capture_output=True,timeout=10)
        self.assertEqual(completed.returncode,0,completed.stderr.decode(errors='replace'))

    def test_local_surface_visit_limit_is_not_bypassed_by_index(self):
        from verification.nonplanar_patch_fixtures import refine_boundary
        case=dense_case(0);case.pop('grid_n');native,edges=dense_source(case)
        obj=native['objects'][0]
        refine_boundary(native,edges,sliver=True)
        marked=[(face,any(a in face and b in face for a,b in edges)) for face in obj['faces']]
        for depth in range(5):
            updated=[]
            for face,refine in marked:
                if not refine:updated.append((face,False));continue
                a,b,c=face
                midpoint=len(obj['world_vertices'])
                obj['world_vertices'].append([sum(obj['world_vertices'][v][k] for v in (a,b,c))/3 for k in range(3)])
                updated.extend((child,True) for child in ([a,b,midpoint],[b,c,midpoint],[c,a,midpoint]))
            marked=updated
        obj['faces']=[face for face,_ in marked]
        self.assertEqual(len(obj['faces']),984)
        with self.assertRaisesRegex(ValueError,'face_visit_budget'):
            choose(native,edges)

    def test_budget_caps_and_nonfinite_projection_are_rejected(self):
        for options in ({'max_build':65537},{'max_nodes':4097},{'max_bytes':524289},{'max_build':True}):
            with self.assertRaises(ValueError):IndexBudget(time.perf_counter_ns()+10**9,**options)
        obj={'object_id':'mesh','world_vertices':[[1e308,1e308,0.],[1e308,-1e308,0.],[1.,1.,0.]],'faces':[[0,1,2]]}
        sink={};p.object_bounds([obj],[1e308,1e308,0.],[0.,0.,1.],sink)
        with self.assertRaisesRegex(IndexBudgetError,'nonfinite_bounds'):
            build_index(obj,sink['mesh'],[1e308,1e308,0.],[0.,0.,1.],'f'*64,IndexBudget(time.perf_counter_ns()+10**9))

    def test_representable_near_vertex_rays_match_full_scan(self):
        right=[math.cos(.17),math.sin(.17),0.];up=[-right[1],right[0],0.]
        points=[[float(x),float(y),0.] for x,y in ((0,0),(1,0),(0,1),(1,1),(.3,.7),(.8,.1))]
        obj={'object_id':'mesh','world_vertices':points,'faces':[[0,1,2],[1,3,2],[0,4,5]]}
        native={'objects':[obj]};sink={};p.object_bounds([obj],right,up,sink)
        budget=IndexBudget(time.perf_counter_ns()+10**10);index=build_index(obj,sink['mesh'],right,up,'f'*64,budget)
        for point in points:
            for axis in (0,1):
                for direction in (-math.inf,math.inf):
                    value=point[:];value[axis]=math.nextafter(value[axis],direction)
                    trace=[];selected=[]
                    traverse(index,[p.dot_interval(value,a) for a in (right,up)],budget,trace,selected)
                    complete=p.projected_hit(native,value,right,up,[0.,0.,1.])
                    filtered=p.projected_hit(native,value,right,up,[0.,0.,1.],allowed_faces={'mesh':selected})
                    self.assertEqual(set(complete),set(filtered))

    def test_exact_bounds_random_near_edges_and_numeric_extremes(self):
        rng=random.Random(119)
        for scale,origin in ((1.,0.),(1e-6,0.),(1.,1e12),(1e-290,0.)):
            points=[[origin+scale*rng.uniform(-1,1),scale*rng.uniform(-1,1),0.] for _ in range(30)]
            obj={'object_id':'mesh','world_vertices':points,'faces':[[i,i+1,i+2] for i in range(0,30,3)]}
            right=[1.,0.,0.];up=[0.,1.,0.];sink={};p.object_bounds([obj],right,up,sink)
            budget=IndexBudget(time.perf_counter_ns()+10**10)
            index=build_index(obj,sink['mesh'],right,up,'f'*64,budget)
            coords=[[sum((Q(v)*Q(a) for v,a in zip(point,axis)),Q(0)) for point in points] for axis in (right,up)]
            validate_index(index,obj,right,up,'f'*64,coords,budget.reservations)
            for point in points:
                query={'point':point,'possible_objects':['mesh'],'traces':{'mesh':[]},'filters':{'mesh':[]},'complete':True}
                trace=query['traces']['mesh'];selected=query['filters']['mesh']
                traverse(index,[p.dot_interval(point,a) for a in (right,up)],budget,trace,selected)
                validate_query(index,query,'mesh',right,up)


if __name__=='__main__':unittest.main()
