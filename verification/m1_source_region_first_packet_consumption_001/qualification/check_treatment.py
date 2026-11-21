"""Offline selector qualification: installed validation, zero host/business calls."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
PATH = HERE.parent / 'harness/treatment.py'
SPEC = importlib.util.spec_from_file_location('first_packet_treatment_under_test', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
Treatment = MODULE.Treatment


def arguments(*, target=None, reference=None, rows=None):
    return {'query': {
        'mode': 'source_region',
        'region': {'object': target or {'name': 'Obj_09'},
                   'source_triangle_indices': [0, 1] if rows is None else rows},
        'reference': reference or {'name': 'Obj_04'},
        'requested_facts': ['surface_proximity'],
    }, 'include_image': True}


def region_ref():
    return {
        'schema': 'human-eye-source-region-ref-v1',
        'region_id': 'source-region:' + 'a' * 64,
        'document_epoch': 'b' * 64,
        'host_id': 'actual-target-id', 'instance_id': 'target-instance',
        'capture_generation': {'instance_id': 'owned-host', 'epoch': 3, 'revision': 4},
        'ordered_geometry_sha256': 'c' * 64, 'source_triangle_indices': [0, 1],
    }


def reference_arguments(ref):
    value = arguments()
    del value['query']['region']
    value['query']['region_ref'] = ref
    return value


def response(ref=None):
    value = {
        'result_kind': 'source_region', 'status': 'complete', 'observation_status': 'locally_observed',
        'read_only': True, 'execution_authority': False,
        'region_ref': region_ref() if ref is None else ref,
        'task_result': {'reference': {'object_id': 'actual-reference-id'}},
    }
    return {'jsonrpc': '2.0', 'id': 'offline-only', 'result': {
        'isError': False, 'content': [{'type': 'text', 'text': json.dumps(value)}]}}


class SelectorTests(unittest.TestCase):
    def treatment(self, detail='brief'):
        return Treatment(detail, 'actual-target-id', 'actual-reference-id')

    def assert_untouched(self, original, refs=()):
        before = deepcopy(original)
        selector = self.treatment()
        forwarded, decision = selector.arguments(original, refs)
        self.assertEqual(original, before)
        self.assertEqual(forwarded, before)
        self.assertFalse(decision['applied'])
        self.assertFalse(selector.used)
        return decision

    def test_names_and_actual_ids_both_match_each_detail(self):
        for detail in ('brief', 'full'):
            for by_id in (False, True):
                with self.subTest(detail=detail, by_id=by_id):
                    original = arguments(target={'id': 'actual-target-id'} if by_id else None,
                                         reference={'id': 'actual-reference-id'} if by_id else None)
                    before = deepcopy(original)
                    forwarded, decision = self.treatment(detail).arguments(original)
                    self.assertTrue(decision['applied'])
                    self.assertEqual(original, before)
                    self.assertEqual(forwarded, {**before, 'response_detail': detail})

    def test_product_canonical_sort_does_not_rewrite_source_request(self):
        original = arguments(rows=[1, 0])
        forwarded, decision = self.treatment().arguments(original)
        self.assertTrue(decision['applied'])
        self.assertEqual(forwarded['query']['region']['source_triangle_indices'], [1, 0])

    def test_image_default_true_matches(self):
        original = arguments()
        del original['include_image']
        self.assertTrue(self.treatment().arguments(original)[1]['applied'])

    def test_missing_nonmatch_and_image_false_are_untouched(self):
        rows = [None, {}, [], {'query': {'mode': 'directory'}}, arguments(rows=[0]),
                arguments(rows=[0, 2]), arguments(target={'name': 'Obj_08'}),
                arguments(reference={'id': 'Obj_04'}), arguments(reference={'name': 'Obj_05'})]
        no_image = arguments()
        no_image['include_image'] = False
        rows.append(no_image)
        for original in rows:
            with self.subTest(original=original):
                self.assert_untouched(original)

    def test_actual_product_argument_rejections_stay_untouched(self):
        rows = []
        for indices in ([False, 1], [0.0, 1], [0, 0], [-1, 1], [], '0,1'):
            rows.append(arguments(rows=indices))
        for field, value in (('include_image', 1), ('response_detail', 'diagnostic'),
                             ('unexpected', True), ('goal', {}), ('task_instruction', 'move')):
            item = arguments()
            item[field] = value
            rows.append(item)
        for field in ('reference', 'requested_facts'):
            item = arguments()
            del item['query'][field]
            rows.append(item)
        item = arguments()
        item['query']['requested_facts'].append('aabb')
        rows.append(item)
        item = arguments()
        item['query']['region']['object']['id'] = 'actual-target-id'
        rows.append(item)
        for original in rows:
            with self.subTest(original=original):
                decision = self.assert_untouched(original)
                self.assertEqual(decision['reason'], 'invalid_arguments')

    def test_known_current_full_reference_matches(self):
        ref = region_ref()
        self.assertTrue(self.treatment().arguments(reference_arguments(ref), [deepcopy(ref)])[1]['applied'])

    def test_unproven_reference_and_any_binding_difference_do_not_match(self):
        ref = region_ref()
        self.assert_untouched(reference_arguments(ref), [])
        self.assert_untouched(reference_arguments(ref), [ref['region_id']])
        for field, value in (('document_epoch', 'd' * 64), ('ordered_geometry_sha256', 'e' * 64),
                             ('instance_id', 'different-instance'), ('host_id', 'different-host'),
                             ('source_triangle_indices', [0, 2]),
                             ('capture_generation', {'instance_id': 'owned-host', 'epoch': 3, 'revision': 5})):
            changed = deepcopy(ref)
            changed[field] = value
            with self.subTest(field=field):
                self.assert_untouched(reference_arguments(changed), [ref])

    def test_noncanonical_ref_and_bool_generation_are_rejected(self):
        for mutation in ('indices', 'generation'):
            ref = region_ref()
            if mutation == 'indices':
                ref['source_triangle_indices'] = [1, 0]
            else:
                ref['capture_generation']['epoch'] = True
            self.assertEqual(self.assert_untouched(reference_arguments(ref), [ref])['reason'], 'invalid_arguments')

    def test_invalid_request_then_valid_request_can_recover_before_dispatch(self):
        selector = self.treatment()
        invalid = arguments()
        invalid['include_image'] = 1
        self.assertFalse(selector.arguments(invalid)[1]['applied'])
        self.assertTrue(selector.arguments(arguments())[1]['applied'])

    def test_first_dispatched_match_is_used_even_when_product_fails(self):
        for failure in (None, {'error': {'code': -32602}}, {'result': {'isError': True, 'content': []}}):
            with self.subTest(failure=failure):
                selector = self.treatment()
                _, verdict = selector.arguments(arguments())
                outcome = selector.accept(verdict, failure)
                self.assertTrue(outcome['consumed'])
                self.assertFalse(outcome['response_valid'])
                next_args = arguments()
                next_args['response_detail'] = 'full'
                forwarded, next_verdict = selector.arguments(next_args)
                self.assertEqual(forwarded, next_args)
                self.assertFalse(next_verdict['applied'])

    def test_success_outcome_is_scope_bound_and_accept_once(self):
        selector = self.treatment()
        _, verdict = selector.arguments(arguments())
        outcome = selector.accept(verdict, response())
        self.assertTrue(outcome['response_valid'])
        self.assertFalse(selector.accept(verdict, response())['consumed'])

    def test_malformed_or_different_scope_response_is_not_valid_and_never_retried(self):
        for invalid in ({'result': {'isError': False, 'content': [{'type': 'text', 'text': '{bad'}]}},
                        response({**region_ref(), 'host_id': 'different-host'})):
            selector = self.treatment()
            _, verdict = selector.arguments(arguments())
            self.assertFalse(selector.accept(verdict, invalid)['response_valid'])
            self.assertTrue(selector.used)


if __name__ == '__main__':
    unittest.main(verbosity=2)
