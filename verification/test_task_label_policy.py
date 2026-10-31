"""Observation-only task label selection and alias namespace contracts."""
import copy
import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from human_eye_plugin import task_labels as labels


def meshes(*names):
    return [SimpleNamespace(object_id=name, name=name, mark_label='#'+name,
                            vertices=[[1, 2, 3]]) for name in names]


def exact(identity, value):
    return {'object_id': identity, 'measurement_valid': True, 'measurement_kind': 'exact',
            'clearance_exact': True, 'signed_clearance_m': value, 'is_penetrating': False}


def penetration(identity, value=-.001):
    return {'object_id': identity, 'measurement_valid': True,
            'measurement_kind': 'certified_penetration', 'clearance_exact': False,
            'signed_clearance_m': value, 'is_penetrating': True}


def lower_bound(identity, value):
    return {'object_id': identity, 'measurement_valid': False, 'measurement_kind': 'lower_bound',
            'numeric_bound_valid': True, 'clearance_lower_bound_m': value,
            'clearance_exact': False, 'signed_clearance_m': None, 'is_penetrating': None}


def build(items=None, **kwargs):
    return labels.build_task_label_plan(items if items is not None else meshes('focus','reference','c','d'),
        focal_id='focus', reference_id='reference', **kwargs)


class TaskLabelPolicyTests(unittest.TestCase):
    def test_core_aliases_and_complete_identity_rules_are_display_only(self):
        plan=build(scene_revision='r1',scene_fingerprint='fingerprint')
        self.assertEqual(labels.task_display_label('focus',plan),'A')
        self.assertEqual(labels.task_display_label('reference',plan),'B')
        self.assertEqual(labels.task_display_label('c',plan),'R'+hashlib.sha256(b'c').hexdigest()[:4].upper())
        self.assertEqual(plan['related_object_ids'],[])
        self.assertFalse(plan['execution_authority'])
        self.assertEqual(plan['core_object_ids'],['focus','reference'])
        self.assertEqual(plan['scene_revision'],'r1')
        json.dumps(plan,allow_nan=False)

    def test_identity_aliases_do_not_follow_enumeration_geometry_or_host_labels(self):
        items=meshes('focus','reference','c','d')
        a=build(items,contacts=[exact('reference',.1),exact('c',.03),exact('d',.02)])
        changed=copy.deepcopy(items[::-1])
        for i,item in enumerate(changed):
            item.vertices=[[i*1000, i*.03, 0]];item.mark_label='#new'+str(i)
        b=build(changed,contacts=[exact('d',.02),exact('c',.03),exact('reference',.1)])
        self.assertEqual(a,b)
        self.assertEqual(a['related_object_ids'],['c','d'])

    def test_priority_is_penetration_then_explicit_then_exact_then_potential(self):
        items=meshes('focus','reference','a-near','b-bound','z-query','zz-penetration')
        plan=build(items,contacts=[exact('reference',.01),exact('a-near',.001),
            lower_bound('b-bound',0),penetration('zz-penetration')],requested_ids=['z-query'])
        self.assertEqual(plan['related_object_ids'],['zz-penetration','z-query'])
        self.assertEqual(plan['related_candidate_count'],4)
        self.assertEqual(plan['related_reasons'],{'zz-penetration':'known_penetration','z-query':'explicit_query'})

    def test_near_exact_precedes_lower_bound_without_claiming_it_exact(self):
        plan=build(contacts=[exact('reference',.01),lower_bound('c',0),exact('d',.01)])
        self.assertEqual(plan['related_object_ids'],['d','c'])
        self.assertEqual(plan['related_reasons']['c'],'potential_neighbor_lower_bound')
        self.assertEqual(plan['related_reasons']['d'],'near_exact_clearance')

    def test_unknown_and_far_records_are_not_promoted(self):
        plan=build(contacts=[exact('reference',.01),exact('c',.02),
            {'object_id':'d','measurement_valid':False,'signed_clearance_m':0}])
        self.assertEqual(plan['related_object_ids'],[])

    def test_invalid_reference_cannot_define_near_threshold(self):
        for value in [None,True,False,float('nan'),float('inf'),-float('inf'),'0',10**1000]:
            with self.subTest(value_type=type(value).__name__):
                plan=build(contacts=[exact('reference',value),exact('c',0),lower_bound('d',0)])
                self.assertEqual(plan['related_object_ids'],[])

    def test_invalid_candidate_metrics_are_not_promoted(self):
        for value in [None,True,False,float('nan'),float('inf'),-float('inf'),'0',10**1000]:
            with self.subTest(value_type=type(value).__name__):
                plan=build(contacts=[exact('reference',.01),exact('c',value),lower_bound('d',value)])
                self.assertEqual(plan['related_object_ids'],[])

    def test_valid_zero_and_penetrating_reference_use_zero_near_threshold(self):
        for reference in [exact('reference',0),penetration('reference')]:
            with self.subTest(reference=reference):
                plan=build(contacts=[reference,exact('c',0),lower_bound('d',0)])
                self.assertEqual(plan['related_object_ids'],['c','d'])
                far=build(contacts=[reference,exact('c',.000001),lower_bound('d',.000001)])
                self.assertEqual(far['related_object_ids'],[])

    def test_negative_number_alone_is_not_penetration_evidence(self):
        invalid=[exact('c',-.1),dict(penetration('c'),measurement_valid=False),
                 dict(penetration('c'),is_penetrating=None),dict(penetration('c'),signed_clearance_m=True),
                 dict(penetration('c'),clearance_exact=True),dict(penetration('c'),measurement_kind='unknown')]
        for contact in invalid:
            with self.subTest(contact=contact):
                self.assertEqual(build(contacts=[contact])['related_object_ids'],[])

    def test_exact_far_measurement_is_not_promoted_by_a_loose_lower_bound(self):
        far=exact('c',.2)
        far.update(numeric_bound_valid=True,clearance_lower_bound_m=0)
        self.assertEqual(build(contacts=[exact('reference',.01),far])['related_object_ids'],[])
        for mutation in [{'measurement_kind':'unknown'},{'measurement_valid':True},
                         {'clearance_exact':True},{'numeric_bound_valid':1}]:
            with self.subTest(mutation=mutation):
                bound=lower_bound('d',0);bound.update(mutation)
                self.assertEqual(build(contacts=[exact('reference',.01),bound])['related_object_ids'],[])

    def test_exact_label_requires_exact_contract(self):
        for changed in [{'clearance_exact':False},{'measurement_kind':'lower_bound'},
                        {'is_penetrating':None},{'measurement_valid':1}]:
            with self.subTest(changed=changed):
                contact=exact('c',0);contact.update(changed)
                self.assertEqual(build(contacts=[exact('reference',.01),contact])['related_object_ids'],[])

    def test_conflicting_strict_facts_cannot_promote(self):
        contact=penetration('c');contact['strict_geometry']={'measurement_valid':False}
        ref=exact('reference',.01);ref['strict_geometry']={'signed_clearance_m':.02}
        self.assertEqual(build(contacts=[contact,ref,exact('d',0)])['related_object_ids'],[])

    def test_duplicate_records_and_malformed_rows_fail_closed(self):
        plan=build(contacts=[exact('reference',.1),exact('c',0),exact('c',.2),None,False,
            {'object_id':[],'measurement_valid':True},exact('unknown',0)])
        self.assertEqual(plan['related_object_ids'],[])
        self.assertEqual(build(contacts='not records')['related_object_ids'],[])
        self.assertEqual(build(contacts=None,requested_ids=['c'])['related_object_ids'],['c'])

    def test_explicit_unknown_measurement_still_gets_explicit_reason(self):
        plan=build(contacts=[{'object_id':'c','measurement_valid':False}],requested_ids=['c'])
        self.assertEqual(plan['related_reasons'],{'c':'explicit_query'})
        self.assertEqual(plan['related_candidate_count'],1)

    def test_reference_switch_changes_roles_without_renaming_old_reference_to_B(self):
        items=meshes('focus','reference','c','d');old=build(items)
        new=labels.build_task_label_plan(items,focal_id='focus',reference_id='c')
        self.assertEqual(labels.task_display_label('reference',old),'B')
        self.assertTrue(labels.task_display_label('reference',new).startswith('R'))
        self.assertEqual(labels.task_display_label('c',new),'B')
        with self.assertRaises(ValueError):
            labels.validate_task_label_plan(old,items,focal_id='focus',reference_id='c')

    def test_prefix_collision_extends_globally_including_unselected_objects(self):
        with patch.object(labels,'_alias_digest',side_effect=lambda identity:
                          {'c':'AAAA0'+'0'*59,'d':'AAAA1'+'1'*59}[identity]):
            plan=build(requested_ids=['c'])
            self.assertEqual(plan['related_alias_hex_chars'],5)
            self.assertEqual(labels.task_display_label('c',plan),'RAAAA0')
            self.assertEqual(labels.task_display_label('d',plan),'RAAAA1')
            labels.validate_task_label_plan(plan,meshes('d','c','reference','focus'),
                focal_id='focus',reference_id='reference')

    def test_eight_character_collision_rejects_optional_plan(self):
        with patch.object(labels,'_alias_digest',side_effect=lambda identity:'A'*8+identity+'0'*55):
            with self.assertRaisesRegex(ValueError,'eight-character'):
                build()

    def test_validation_is_detached_and_rejects_alias_spoofing_or_bad_fields(self):
        items=meshes('focus','reference','c','d');plan=build(items,requested_ids=['c'])
        valid=labels.validate_task_label_plan(plan,items,focal_id='focus',reference_id='reference')
        valid['related_object_ids'].clear();valid['related_reasons'].clear()
        self.assertEqual(plan['related_object_ids'],['c'])
        mutations=[{'execution_authority':True},{'related_alias_hex_chars':8},{'max_related_labels':True},
            {'related_object_ids':['focus'],'related_reasons':{'focus':'explicit_query'}},
            {'related_object_ids':['unknown'],'related_reasons':{'unknown':'explicit_query'}},
            {'related_reasons':{'c':'guaranteed_visible'}},{'related_candidate_count':True},
            {'related_candidate_count':0},{'core_object_ids':['reference','focus']},
            {'display_label':'A'},{'scene_revision':False},{'scene_fingerprint':[]},
            {'related_object_ids':['c','c']},{'related_object_ids':('c',)},
            {'schema_revision':'old'},{'scope':'execution'}]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                altered=copy.deepcopy(plan);altered.update(mutation)
                with self.assertRaises(ValueError):
                    labels.validate_task_label_plan(altered,items,focal_id='focus',reference_id='reference')

    def test_removed_object_and_noncanonical_related_order_rejected(self):
        plan=build(requested_ids=['c','d'])
        with self.assertRaises(ValueError):
            labels.validate_task_label_plan(plan,meshes('focus','reference','c'),focal_id='focus',reference_id='reference')
        plan['related_object_ids'].reverse()
        with self.assertRaises(ValueError):
            labels.validate_task_label_plan(plan,meshes('focus','reference','c','d'),focal_id='focus',reference_id='reference')

    def test_object_query_and_binding_boundaries(self):
        bad_meshes=[[],meshes('focus','focus'),meshes('focus','reference',''),
            meshes('focus','reference',*[str(i) for i in range(255)])]
        for items in bad_meshes:
            with self.subTest(size=len(items)),self.assertRaises(ValueError):build(items)
        for requested in ['c',['unknown'],['c','c'],[True],None]:
            with self.subTest(requested=requested),self.assertRaises(ValueError):build(requested_ids=requested)
        for binding in [False,0,'',[],{}]:
            with self.subTest(binding=binding),self.assertRaises(ValueError):build(scene_revision=binding)
        with self.assertRaises(ValueError):build(contacts=[None]*257)
        with self.assertRaises(ValueError):labels.build_task_label_plan(meshes('focus','reference'),focal_id='focus',reference_id='focus')

    def test_inputs_not_mutated_and_no_geometry_access_required(self):
        items=[{'object_id':name} for name in ('focus','reference','c','d')]
        contacts=[exact('reference',.01),exact('c',.001)];requested=['d']
        before=copy.deepcopy((items,contacts,requested))
        plan=build(items,contacts=contacts,requested_ids=requested)
        labels.validate_task_label_plan(plan,items,focal_id='focus',reference_id='reference')
        self.assertEqual((items,contacts,requested),before)


if __name__=='__main__':unittest.main()
