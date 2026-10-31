"""Bounded visual intent stays separate from geometric measurement requests."""
import copy
import hashlib
import unittest

from human_eye_plugin import task_labels
from human_eye_plugin.live_spatial_mcp import LIVE_MCP_TOOLS_SCHEMA, _validate_arguments
from human_eye_plugin.query_policy import MAX_VISUAL_LABEL_IDS, validate_query


def items(*related):
    return [{'object_id': identity} for identity in ['focus', 'reference', *related]]


def penetration(identity):
    return {'object_id': identity, 'measurement_valid': True,
            'measurement_kind': 'certified_penetration', 'clearance_exact': False,
            'signed_clearance_m': -.001, 'is_penetrating': True}


def plan(related=('a','b','c','d'), **kwargs):
    return task_labels.build_task_label_plan(items(*related), focal_id='focus',
        reference_id='reference', scene_revision='r1', scene_fingerprint='current', **kwargs)


def validate(value, related=('a','b','c','d')):
    return task_labels.validate_task_label_plan(value, items(*related),
        focal_id='focus', reference_id='reference')


class LabelVisualFocusQueryTests(unittest.TestCase):
    def test_default_query_does_not_acquire_visual_intent(self):
        self.assertEqual(validate_query(None), {'mode':'overview','max_exact_pairs':255})
        request={'mode':'exact_pairs','object_ids':['d','c','b','a']}
        self.assertNotIn('label_object_ids',validate_query(request))

    def test_visual_focus_is_independent_of_precision_mode_and_core_ids_are_valid(self):
        for mode in ['overview','exact_pairs','nearest']:
            request={'mode':mode,'label_object_ids':['reference','d','focus','b']}
            before=copy.deepcopy(request)
            result=validate_query(request, object_ids={'focus','reference','a','b','c','d'}, focal_id='focus')
            self.assertEqual(result['label_object_ids'],['b','d','focus','reference'])
            self.assertEqual(request,before)
            self.assertEqual(validate_query(result),result)

    def test_empty_duplicate_large_and_non_id_visual_requests_rejected(self):
        bad=[[],None,'a',('a',),['a','a'],[''],[' '],[True],[{}],list('abcdefg')]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate_query({'label_object_ids':value})

    def test_unknown_current_namespace_rejected_before_display_selection(self):
        query={'label_object_ids':['a','removed']}
        self.assertEqual(validate_query(query)['label_object_ids'],['a','removed'])
        with self.assertRaisesRegex(ValueError,'unknown scene object'):
            validate_query(query,object_ids={'focus','reference','a'})

    def test_schema_and_argument_validation_expose_only_bounded_observation_option(self):
        tool=next(t for t in LIVE_MCP_TOOLS_SCHEMA if t['name']=='human_eye_scene_observe')
        query=tool['inputSchema']['properties']['query']
        labels=query['properties']['label_object_ids']
        self.assertEqual((labels['minItems'],labels['maxItems'],labels['uniqueItems']),(1,MAX_VISUAL_LABEL_IDS,True))
        self.assertEqual(MAX_VISUAL_LABEL_IDS,task_labels.MAX_VISUAL_FOCUS_IDS)
        self.assertFalse(query['additionalProperties'])
        _validate_arguments('human_eye_scene_observe',{'query':{'label_object_ids':['a']}})
        for request in [{'query':{'label_object_ids':[]}}, {'label_object_ids':['a']}]:
            with self.subTest(request=request),self.assertRaises(ValueError):
                _validate_arguments('human_eye_scene_observe',request)
        with self.assertRaises(ValueError):
            _validate_arguments('human_eye_transform',{'query':{'label_object_ids':['a']}})


class LabelVisualFocusSelectionTests(unittest.TestCase):
    def test_measurement_query_keeps_default_two_and_original_alias_namespace(self):
        current=plan(contacts=[penetration(i) for i in 'abcd'],requested_ids=list('dcba'))
        self.assertEqual(current['related_object_ids'],['a','b'])
        self.assertEqual(current['max_related_labels'],2)
        self.assertEqual(current['visual_focus_object_ids'],[])
        self.assertEqual(current['candidate_reason_counts'],{'known_penetration':4})
        self.assertEqual(task_labels.task_display_label('focus',current),'A')
        self.assertEqual(task_labels.task_display_label('reference',current),'B')
        for identity in 'abcd':
            self.assertEqual(task_labels.task_display_label(identity,current),
                             'R'+hashlib.sha256(identity.encode()).hexdigest()[:4].upper())
        validate(current)

    def test_explicit_later_visual_id_cannot_be_starved_by_earlier_penetrations(self):
        contacts=[penetration(i) for i in 'abcd']
        current=plan(contacts=contacts,visual_focus_ids=['d'])
        self.assertEqual(current['related_object_ids'],['d','a'])
        self.assertEqual(current['max_related_labels'],2)
        self.assertEqual(current['related_reasons'],{'d':'known_penetration','a':'known_penetration'})
        self.assertEqual(current['candidate_reason_counts'],{'known_penetration':4})
        validate(current)

    def test_two_later_visual_ids_keep_small_budget_and_geometric_reasons(self):
        current=plan(contacts=[penetration(i) for i in 'abcd'],visual_focus_ids=['d','c'])
        self.assertEqual(current['related_object_ids'],['c','d'])
        self.assertEqual(current['max_related_labels'],2)
        self.assertEqual(current['visual_focus_object_ids'],['c','d'])
        self.assertTrue(all(reason=='known_penetration' for reason in current['related_reasons'].values()))
        validate(current)

    def test_four_visible_focus_candidates_expand_only_explicit_budget(self):
        current=plan(contacts=[penetration(i) for i in 'abcd'],visual_focus_ids=list('dcba'))
        self.assertEqual(current['related_object_ids'],list('abcd'))
        self.assertEqual(current['max_related_labels'],4)
        self.assertEqual(current['related_candidate_count'],4)
        self.assertFalse(current['execution_authority'])
        validate(current)

    def test_six_is_hard_limit_and_no_geometry_claim_is_created_for_focus_only(self):
        current=plan(related=tuple('abcdef'),visual_focus_ids=list('fedcba'))
        self.assertEqual(current['max_related_labels'],6)
        self.assertEqual(len(current['core_object_ids'])+len(current['related_object_ids']),8)
        self.assertEqual(current['candidate_reason_counts'],{'explicit_visual_focus':6})
        self.assertTrue(all(reason=='explicit_visual_focus' for reason in current['related_reasons'].values()))
        self.assertNotIn('is_penetrating',current)
        validate(current,tuple('abcdef'))
        with self.assertRaises(ValueError):
            plan(related=tuple('abcdefg'),visual_focus_ids=list('abcdefg'))

    def test_core_focus_requests_do_not_consume_related_slots(self):
        current=plan(visual_focus_ids=['focus','reference','a','b','c','d'])
        self.assertEqual(current['visual_focus_object_ids'],['a','b','c','d','focus','reference'])
        self.assertEqual(current['max_related_labels'],4)
        self.assertEqual(task_labels.task_display_label('focus',current),'A')
        self.assertEqual(task_labels.task_display_label('reference',current),'B')
        validate(current)

    def test_large_measurement_inventory_does_not_expand_default_display(self):
        identities=['object-'+str(i).zfill(3) for i in range(254)]
        current=plan(related=identities,requested_ids=identities)
        self.assertEqual(current['max_related_labels'],2)
        self.assertEqual(current['related_object_ids'],identities[:2])
        self.assertEqual(current['candidate_reason_counts'],{'explicit_query':254})
        self.assertNotIn('all_candidate_object_ids',current)
        validate(current,identities)

    def test_validation_is_detached_and_inputs_stay_unchanged(self):
        contacts=[penetration(i) for i in 'abcd'];focus=['d','c']
        before=copy.deepcopy((contacts,focus))
        current=plan(contacts=contacts,visual_focus_ids=focus)
        detached=validate(current)
        detached['candidate_reason_counts']['known_penetration']=999
        detached['visual_focus_object_ids'].clear()
        self.assertEqual((contacts,focus),before)
        self.assertEqual(current['candidate_reason_counts'],{'known_penetration':4})
        self.assertEqual(current['visual_focus_object_ids'],['c','d'])

    def test_reason_counts_cannot_understate_selected_reasons_or_invent_visual_candidates(self):
        current=plan(contacts=[penetration('a')],visual_focus_ids=['d'])
        for counts in [{'known_penetration':0,'explicit_visual_focus':2},
                       {'explicit_visual_focus':2},
                       {'known_penetration':True,'explicit_visual_focus':1},
                       {'known_penetration':1,'explicit_visual_focus':1,'unexpected':1},
                       {'known_penetration':1,'explicit_visual_focus':1,'explicit_query':0},
                       [],None]:
            altered=copy.deepcopy(current);altered['candidate_reason_counts']=counts
            with self.subTest(counts=counts),self.assertRaises(ValueError):validate(altered)

    def test_focus_budget_selection_and_reason_mutations_fail_closed(self):
        current=plan(contacts=[penetration(i) for i in 'abcd'],visual_focus_ids=['d'])
        mutations=[{'max_related_labels':6},{'max_related_labels':True},
                   {'visual_focus_object_ids':['focus']},{'visual_focus_object_ids':['missing']},
                   {'visual_focus_object_ids':['d','d']},{'visual_focus_object_ids':('d',)},
                   {'visual_focus_object_ids':['d','c']},
                   {'related_object_ids':['a','b'],'related_reasons':{'a':'known_penetration','b':'known_penetration'}},
                   {'related_reasons':{'d':'known_penetration','a':'explicit_visual_focus'}},
                   {'execution_authority':True},{'unexpected_field':False}]
        for change in mutations:
            altered=copy.deepcopy(current);altered.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):validate(altered)

    def test_bad_direct_visual_focus_inputs_are_rejected(self):
        for focus in [None,'a',['missing'],['a','a'],[True],[{}]]:
            with self.subTest(focus=focus),self.assertRaises(ValueError):plan(visual_focus_ids=focus)


if __name__=='__main__':
    unittest.main()
