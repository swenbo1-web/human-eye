"""Raw topology extension: frozen oracles, precision, locations and refusals."""
import copy,math,unittest
from human_eye_plugin import mesh_structure as m
from human_eye_plugin.mesh_structure_service import validate_result
from verification.mesh_structure_contract import validate_report,score
from verification.mesh_structure_topology_fixtures import fixtures
from verification.test_mesh_structure_runtime import raw_case,identity


def run(raw,categories=m.SUPPORTED,budget=None):
    result=m.analyze_raw(raw,identity(),task_id='topology-test',categories=categories,budget=budget)
    validate_report(result['report'])
    validate_result(result,object_id='target',request_id='topology-test',categories=categories,
                    deadline_ns=result['accounting']['deadline_ns'])
    return result


def case(name):return next(c for c in fixtures() if c['id']==name)


class TopologyExtensionTests(unittest.TestCase):
    def test_frozen_new_oracles_known_and_unknown_scored_separately(self):
        for fixture in fixtures():
            with self.subTest(case=fixture['id']):
                categories=list(dict.fromkeys([*fixture['expected'],*fixture['unknown']]))
                result=run(raw_case(fixture),categories)
                metrics=score(fixture['expected'],result['report']['checks'])
                self.assertEqual((metrics['fp'],metrics['fn']),(0,0))
                self.assertEqual(result['status'],'partial' if fixture['unknown'] else 'observed')
                self.assertEqual(set(result['coverage']['unclassified']),set(fixture['unknown']))
                for cat,ids in fixture['unknown'].items():
                    row=result['coverage']['unclassified'][cat]
                    self.assertEqual((row['count'],row['source_indices']),(len(ids),ids))
                    self.assertEqual(result['report']['checks'][cat]['state'],'partial')
                    self.assertIsNone(result['report']['checks'][cat]['total'])
                for cat in fixture['expected'].keys()-fixture['unknown'].keys():
                    self.assertEqual(result['report']['checks'][cat]['state'],'complete')

    def test_closed_edge_incidence_does_not_hide_pinched_vertex(self):
        result=run(raw_case(case('pinched_closed_shells')))
        checks=result['report']['checks']
        self.assertEqual(checks['boundary_edges']['found'],0)
        self.assertEqual(checks['nonmanifold_edges']['found'],0)
        self.assertEqual(checks['nonmanifold_vertices']['regions'],[[0]])

    def test_cyclic_and_reversed_duplicate_faces_leave_link_unknown(self):
        for polygon in ([0,1,2],[1,2,0],[2,1,0]):
            fixture=case('duplicate_face_link_unknown');fixture['polygons'][1]=polygon
            result=run(raw_case(fixture),['nonmanifold_vertices'])
            self.assertEqual(result['coverage']['unclassified']['nonmanifold_vertices']['source_indices'],[0,1,2])

    def test_wire_only_branch_is_not_a_surface_nonmanifold_claim(self):
        raw=raw_case(dict(vertices=[[0,0,0],[1,0,0],[0,1,0],[-1,0,0]],edges=[[0,1],[0,2],[0,3]],polygons=[]))
        result=run(raw)
        self.assertEqual(result['report']['checks']['nonmanifold_vertices']['found'],0)
        self.assertEqual(result['report']['checks']['loose_edges']['found'],1)

    def test_threshold_adjacent_floats_and_exact_zero_have_distinct_meaning(self):
        for height,expected in [(0.,'exact_zero'),(2.**-40,'relative_near'),
                                (math.nextafter(2.**-40,math.inf),None)]:
            fixture=case('near_triangle');fixture['vertices'][2][1]=height
            result=run(raw_case(fixture),['degenerate_polygons'])
            classes=[label for p in result['patches'] for label in p['classification']]
            self.assertEqual(classes,[] if expected is None else [expected])

    def test_exact_predicate_handles_extreme_binary_coordinates_and_units(self):
        for factor in (2.**-900,1.,2.**900):
            for scale in (2.**-30,1.,2.**30):
                fixture=case('near_triangle')
                fixture['vertices']=[[x*factor for x in p] for p in fixture['vertices']]
                raw=raw_case(fixture);raw['unit_scale']=scale
                result=run(raw,['degenerate_polygons'])
                self.assertEqual(result['patches'][0]['classification'],['relative_near'])

    def test_non_simple_adjacent_backtracking_is_unknown(self):
        raw=raw_case(dict(vertices=[[0,0,0],[2,0,0],[1,0,0],[1,1,0],[0,1,0]],
                          edges=[],polygons=[[0,1,2,3,4]]))
        result=run(raw,['degenerate_polygons'])
        self.assertEqual(result['coverage']['unclassified']['degenerate_polygons']['reasons'],['non_simple_ngon'])

    def test_large_noncollinear_ngon_unknown_but_collinear_has_exact_zero(self):
        for collinear in (False,True):
            vertices=[[i,0 if collinear else i*i,0] for i in range(65)]
            result=run(raw_case(dict(vertices=vertices,edges=[],polygons=[list(range(65))])),['degenerate_polygons'])
            if collinear:self.assertEqual(result['patches'][0]['classification'],['exact_zero'])
            else:self.assertEqual(result['coverage']['unclassified']['degenerate_polygons']['reasons'],['ngon_predicate_arity_budget'])

    def test_unknown_prefix_is_bounded_and_not_relabelled_complete(self):
        fixture=case('duplicate_face_link_unknown');vertices=[];polygons=[]
        for n in range(30):
            vertices.extend([[x+3*n,y,z] for x,y,z in fixture['vertices']])
            polygons.extend([[i+3*n for i in p] for p in fixture['polygons']])
        result=run(raw_case(dict(vertices=vertices,edges=[],polygons=polygons)),['nonmanifold_vertices'])
        row=result['coverage']['unclassified']['nonmanifold_vertices']
        self.assertEqual((row['count'],len(row['source_indices'])),(90,64))
        self.assertIsNone(result['report']['checks']['nonmanifold_vertices']['total'])

    def test_source_permutation_preserves_mapped_vertex_and_polygon_groups(self):
        for name,cat in [('pinched_closed_shells','nonmanifold_vertices'),
                         ('two_degenerate_faces_connected','degenerate_polygons')]:
            fixture=case(name);old=raw_case(fixture);n=len(old['vertices']);p=len(old['polygons'])
            remap=lambda v:n-1-v
            raw=copy.deepcopy(old);raw['vertices'].reverse()
            raw['edges']=[[remap(v) for v in edge[::-1]] for edge in old['edges'][::-1]]
            raw['polygons']=[[remap(v) for v in face[::-1]] for face in old['polygons'][::-1]]
            result=run(raw,[cat]);mapped=[]
            for region in result['report']['checks'][cat]['regions']:
                mapped.append(sorted(remap(i) if cat=='nonmanifold_vertices' else p-1-i for i in region))
            self.assertEqual(sorted(mapped),sorted(fixture['expected'][cat]))

    def test_positions_use_all_patch_vertices_and_affine_then_scale(self):
        fixture=case('two_degenerate_faces_connected');raw=raw_case(fixture)
        raw['unit_scale']=.01;raw['matrix_world']=[[0,-2,0,10],[3,0,0,-20],[0,0,4,30],[0,0,0,1]]
        result=run(raw,['degenerate_polygons']);p=result['patches'][0]['position']
        self.assertEqual(p['local_bounds_m'],[[0.,0.,0.],[.03,0.,0.]])
        self.assertEqual(p['world_bounds_m'],[[.1,-.2,.3],[.1,-.11,.3]])
        self.assertEqual(p['witness_vertex_index'],0)
        self.assertEqual(p['witness_world_m'],[.1,-.2,.3])

    def test_position_overflow_retains_topology_without_fabricated_location(self):
        raw=raw_case(dict(vertices=[[1e308,0,0]],edges=[],polygons=[]));raw['matrix_world'][0][0]=2.
        result=run(raw,['isolated_vertices'])
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['report']['checks']['isolated_vertices']['state'],'complete')
        self.assertEqual(result['patches'][0]['position'],{'status':'unknown','reason':'position_nonfinite'})

    def test_position_budget_exhaustion_retains_completed_fact(self):
        prepared=m.prepare_raw(raw_case(dict(vertices=[[0,0,0]],edges=[],polygons=[])),identity())
        result=m.analyze_prepared(prepared,task_id='topology-test',categories=['isolated_vertices'],budget=m.WorkBudget(max_work=1))
        self.assertEqual(result['patches'][0]['position']['reason'],'work_budget_exhausted')
        self.assertEqual(result['report']['checks']['isolated_vertices']['total'],1)
        validate_result(result,object_id='target',request_id='topology-test',categories=['isolated_vertices'],deadline_ns=result['accounting']['deadline_ns'])

    def test_stop_during_new_predicate_never_fabricates_total(self):
        prepared=m.prepare_raw(raw_case(case('pinched_closed_shells')),identity())
        for cat in ('nonmanifold_vertices','degenerate_polygons'):
            result=m.analyze_prepared(prepared,task_id='topology-test',categories=[cat],budget=m.WorkBudget(max_work=3))
            self.assertEqual(result['status'],'partial');self.assertIsNone(result['report']['checks'][cat]['total'])
            validate_result(result,object_id='target',request_id='topology-test',categories=[cat],deadline_ns=result['accounting']['deadline_ns'])

    def test_algorithm_unknown_and_position_tampering_rejected(self):
        result=run(raw_case(case('unknown_and_known_bad_vertex')),['nonmanifold_vertices'])
        edits=[lambda r:r['algorithm'].update(near_ngon_quality='checked'),
               lambda r:r['coverage']['unclassified'].clear(),
               lambda r:r['coverage']['unclassified']['nonmanifold_vertices'].update(source_indices=[0,1,3]),
               lambda r:r['patches'][0]['position'].update(witness_vertex_index=0),
               lambda r:r['patches'][0]['position'].update(world_bounds_m=[[0,0,0],[-1,0,0]]),
               lambda r:r['patches'][0]['position'].update(witness_world_m=[True,0,0]),
               lambda r:r['patches'][0].update(classification=['exact_zero']),
               lambda r:r.update(status='observed')]
        for edit in edits:
            value=copy.deepcopy(result);edit(value)
            with self.subTest(edit=edit),self.assertRaises(ValueError):
                validate_result(value,object_id='target',request_id='topology-test',categories=['nonmanifold_vertices'],deadline_ns=value['accounting']['deadline_ns'])


if __name__=='__main__':unittest.main()
