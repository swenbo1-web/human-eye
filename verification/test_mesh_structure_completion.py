"""Independent M1-02 completion oracles and metamorphic/budget checks."""
import copy,math,unittest
from human_eye_plugin import mesh_structure as m
from human_eye_plugin.mesh_structure_service import validate_result
from verification.mesh_structure_contract import score
from verification.mesh_structure_completion_fixtures import fixtures
from verification.test_mesh_structure_runtime import raw_case,identity
from verification.test_mesh_structure_topology import run


NEW=('duplicate_positions','duplicate_polygons','winding_conflicts')
def case(name):return next(c for c in fixtures() if c['id']==name)
def canon(groups,edge=False):
    return sorted(tuple(sorted(tuple(sorted(e)) for e in region)) if edge else tuple(sorted(region)) for region in groups)


class StructureCompletionTests(unittest.TestCase):
    def test_preregistered_known_groups_and_unknown_edge_witnesses(self):
        for fixture in fixtures():
            with self.subTest(case=fixture['id']):
                raw=raw_case(fixture);categories=list(dict.fromkeys([*fixture['expected'],*fixture['unknown']]))
                result=run(raw,categories);checks=result['report']['checks']
                metric=score(fixture['expected'],checks)
                self.assertEqual((metric['fp'],metric['fn']),(0,0))
                self.assertEqual(set(result['coverage']['unclassified']),set(fixture['unknown']))
                for cat,witnesses in fixture['unknown'].items():
                    unknown=result['coverage']['unclassified'][cat]
                    actual=[raw['edges'][i] for i in unknown['source_indices']]
                    self.assertEqual(canon([actual],True),canon([witnesses],True))
                    self.assertEqual(unknown['count'],len(witnesses))
                    self.assertEqual(checks[cat]['state'],'partial');self.assertIsNone(checks[cat]['total'])
                for cat in fixture['expected'].keys()-fixture['unknown'].keys():
                    self.assertEqual(checks[cat]['state'],'complete')

    def test_permuted_source_mapping_and_global_winding_reversal(self):
        for fixture in fixtures():
            original=raw_case(fixture);raw=copy.deepcopy(original)
            n=len(raw['vertices']);p=len(raw['polygons']);vmap=lambda i:n-1-i
            raw['vertices'].reverse()
            raw['edges']=[[vmap(i) for i in e[::-1]] for e in original['edges'][::-1]]
            raw['polygons']=[[vmap(i) for i in poly[::-1]] for poly in original['polygons'][::-1]]
            categories=list(dict.fromkeys([*fixture['expected'],*fixture['unknown']]))
            result=run(raw,categories)
            for cat,wanted in fixture['expected'].items():
                mapped=[]
                for region in result['report']['checks'][cat]['regions']:
                    if cat=='winding_conflicts':mapped.append([[vmap(v) for v in edge] for edge in region])
                    elif cat=='duplicate_positions':mapped.append([vmap(i) for i in region])
                    else:mapped.append([p-1-i for i in region])
                self.assertEqual(canon(mapped,cat=='winding_conflicts'),canon(wanted,cat=='winding_conflicts'),fixture['id'])
            for cat,wanted in fixture['unknown'].items():
                actual=[[vmap(v) for v in raw['edges'][i]] for i in result['coverage']['unclassified'][cat]['source_indices']]
                self.assertEqual(canon([actual],True),canon([wanted],True),fixture['id'])

    def test_exact_numeric_equality_does_not_float_coerce_large_ints(self):
        raw=raw_case(dict(vertices=[[2**53,0,0],[2**53+1,0,0],[float(2**53),0,0]],edges=[],polygons=[]))
        self.assertEqual(run(raw,['duplicate_positions'])['report']['checks']['duplicate_positions']['regions'],[[0,2]])

    def test_adjacent_floats_and_unit_underflow_do_not_merge_raw_positions(self):
        for x,y,scale in [(1.,math.nextafter(1.,math.inf),.001),(0.,math.nextafter(0.,1.),.5)]:
            raw=raw_case(dict(vertices=[[x,0,0],[y,0,0]],edges=[],polygons=[]));raw['unit_scale']=scale
            self.assertEqual(run(raw,['duplicate_positions'])['report']['checks']['duplicate_positions']['found'],0)

    def test_singular_world_transform_does_not_create_raw_duplicate_positions(self):
        raw=raw_case(case('near_positions_stay_distinct'));raw['matrix_world'][0]=[0,0,0,9]
        self.assertEqual(run(raw,['duplicate_positions'])['report']['checks']['duplicate_positions']['found'],0)

    def test_equivalent_faces_not_merged_with_a_different_equivalence_class(self):
        raw=raw_case(case('distinct_duplicate_classes_share_edge'))
        result=run(raw,NEW)
        self.assertEqual(result['report']['checks']['duplicate_polygons']['regions'],[[0,1],[2,3]])
        self.assertEqual(result['report']['checks']['winding_conflicts']['found'],1)
        self.assertEqual(result['report']['checks']['winding_conflicts']['state'],'partial')

    def test_duplicate_face_winding_facts_survive_unknown_vertex_links(self):
        raw=raw_case(case('rotated_same_direction_duplicate'));result=run(raw)
        self.assertEqual(result['report']['checks']['duplicate_polygons']['regions'],[[0,1]])
        self.assertEqual(result['report']['checks']['winding_conflicts']['found'],1)
        self.assertEqual(result['report']['checks']['nonmanifold_vertices']['state'],'partial')

    def test_index_winding_not_geometric_normal_or_world_handedness(self):
        fixture=case('rotated_same_direction_duplicate')
        fixture['vertices']=[[i,0,0] for i in range(4)];raw=raw_case(fixture)
        raw['matrix_world'][0][0]=-1
        result=run(raw,['winding_conflicts'])
        self.assertEqual(score(fixture['expected'],run(raw,NEW)['report']['checks'])['fn'],0)
        self.assertEqual(result['report']['checks']['winding_conflicts']['found'],1)

    def test_oversized_duplicate_equivalence_classes_are_omitted_whole(self):
        for count in (64,65):
            for cat in ('duplicate_positions','duplicate_polygons'):
                fixture=(dict(vertices=[[0,0,0]]*count,edges=[],polygons=[]) if cat=='duplicate_positions' else
                         dict(vertices=[[0,0,0],[1,0,0],[0,1,0]],edges=[],polygons=[[0,1,2]]*count))
                result=run(raw_case(fixture),[cat]);record=result['report']['checks'][cat]
                self.assertEqual((record['found'],record['total'],record['omitted']),(1,1,int(count==65)))
                self.assertEqual(len(result['patches']),int(count==64))

    def test_many_duplicate_groups_keep_byte_and_omission_accounting(self):
        raw=raw_case(dict(vertices=[[n,0,0] for n in range(200) for _ in range(2)],edges=[],polygons=[]))
        result=run(raw,['duplicate_positions']);record=result['report']['checks']['duplicate_positions']
        self.assertEqual(record['found'],200);self.assertGreater(record['omitted'],0)
        self.assertEqual(record['found'],len(record['regions'])+record['omitted'])
        self.assertLessEqual(len(m._bytes(result)),m.LIMITS['report_bytes'])

    def test_winding_unknown_prefix_is_source_edges_not_vertices(self):
        vertices=[];polygons=[];base=case('nonmanifold_orientation_unknown')
        for n in range(70):
            vertices.extend([[x+3*n,y,z] for x,y,z in base['vertices']])
            polygons.extend([[i+5*n for i in face] for face in base['polygons']])
        raw=raw_case(dict(vertices=vertices,edges=[],polygons=polygons))
        result=run(raw,['winding_conflicts']);row=result['coverage']['unclassified']['winding_conflicts']
        self.assertEqual((row['count'],len(row['source_indices'])),(70,64))
        self.assertEqual(canon([[raw['edges'][i] for i in row['source_indices']]],True),
                         canon([[[5*n,5*n+1] for n in range(64)]],True))

    def test_known_winding_edges_do_not_bridge_through_unknown_edge(self):
        raw=raw_case(dict(vertices=[[i,i*i,0] for i in range(11)],edges=[],polygons=[
            [0,2,3],[0,2,5],[1,4,6],[1,4,7],[0,1,8],[1,0,9],[0,1,10]]))
        result=run(raw,['winding_conflicts'])
        self.assertEqual(canon(result['report']['checks']['winding_conflicts']['regions'],True),
                         canon([[[0,2]],[[1,4]]],True))
        unknown=result['coverage']['unclassified']['winding_conflicts']['source_indices']
        self.assertEqual([sorted(raw['edges'][i]) for i in unknown],[[0,1]])

    def test_patch_positions_bind_original_vertices_faces_and_edges(self):
        for name,cat,kind,ids in [('signed_zero_and_equal_numeric_groups','duplicate_positions','vertex',[0,1]),
                                 ('rotated_same_direction_duplicate','duplicate_polygons','polygon',[0,1]),
                                 ('two_disconnected_winding_clusters','winding_conflicts','edge',None)]:
            raw=raw_case(case(name));result=run(raw,[cat]);patch=result['patches'][0]
            self.assertEqual(patch['element_kind'],kind)
            if ids is not None:self.assertEqual(patch['source_indices'],ids)
            p=patch['position'];self.assertEqual(p['status'],'known')
            if kind=='vertex':self.assertEqual(p['local_bounds_m'],[[0.,0.,0.],[0.,0.,0.]])
            else:self.assertEqual(p['local_bounds_m'],[[0.,0.,0.],[1.,1.,0.]])

    def test_category_budget_stop_never_claims_full_total(self):
        prepared=m.prepare_raw(raw_case(case('rotated_same_direction_duplicate')),identity())
        for cat in NEW:
            result=m.analyze_prepared(prepared,task_id='topology-test',categories=[cat],budget=m.WorkBudget(max_work=1))
            self.assertIsNone(result['report']['checks'][cat]['total']);self.assertEqual(result['status'],'partial')
            validate_result(result,object_id='target',request_id='topology-test',categories=[cat],deadline_ns=result['accounting']['deadline_ns'])

    def test_unknown_edge_and_duplicate_kind_tampering_refused(self):
        raw=raw_case(case('distinct_duplicate_classes_share_edge'));result=run(raw,NEW)
        def overlap(r):
            edge=next(p for p in r['patches'] if p['category']=='winding_conflicts')['source_indices'][0]
            r['coverage']['unclassified']['winding_conflicts']['source_indices']=[edge]
        edits=[overlap,lambda r:r['coverage']['unclassified']['winding_conflicts'].update(reasons=['duplicate_face_link_ambiguous']),
               lambda r:r['patches'][0].update(element_kind='vertex'),
               lambda r:r['report']['checks']['winding_conflicts'].update(total=1),
               lambda r:r.update(status='observed')]
        for edit in edits:
            value=copy.deepcopy(result);edit(value)
            with self.assertRaises(ValueError):
                validate_result(value,object_id='target',request_id='topology-test',categories=NEW,deadline_ns=value['accounting']['deadline_ns'])


if __name__=='__main__':unittest.main()
