"""Synthetic quality counterexamples and lossless old/compact evidence packaging."""

from contextlib import redirect_stdout
import copy
from decimal import Decimal
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


score = load('_compact_quality_score_regression', HERE/'score_answer.py')
pack = load('_compact_quality_archive_regression', HERE.parent/'runtime/pack_quality.py')
fixtures = load('_compact_quality_archive_fixture', HERE/'check_packager.py')
truth = json.loads((HERE/'TRUTH.json').read_bytes())
snapshot = json.loads((HERE/'ACTUAL_SNAPSHOT.json').read_bytes())
ENGINEERING = ROOT/'verification/m4_surface_scan_compact_facts_001/engineering/run_01'
COMPACT = json.loads((ENGINEERING/'base_default_RESPONSE_RECEIPT.json').read_bytes())['body']
DETAILED = json.loads((ENGINEERING/'base_full_RESPONSE_RECEIPT.json').read_bytes())['body']


def text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class CompactScoringContractTests(unittest.TestCase):
    def test_actual_compact_layout_is_readable_without_product_projection(self):
        result = score.score_answer(text(COMPACT), truth, snapshot)
        self.assertEqual(result['status'], 'complete_correct')
        self.assertEqual(result['distance_correct_rows'], 71)

    def test_actual_detailed_metres_keep_presentation_incomplete(self):
        result = score.score_answer(text(DETAILED), truth, snapshot)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['distance_correct_rows'], 71)

    def test_compact_nonzero_coarse_mm_remains_presentation_incomplete(self):
        value = copy.deepcopy(COMPACT)
        column = value['match_columns'].index('distance_mm')
        row = next(row for row in value['matches'] if abs(float(row[column])-.5) < .0001)
        row[column] = 0.5
        result = score.score_answer(text(value),truth,snapshot)
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['distance_correct_rows'],71)
        self.assertTrue(result['presentation_issues'])

    def test_correct_display_mm_does_not_hide_a_wrong_raw_metre_fact(self):
        value = copy.deepcopy(COMPACT)
        column = value['match_columns'].index('distance_m')
        value['matches'][0][column] = 1.0
        result = score.score_answer(text(value),truth,snapshot)
        self.assertEqual(result['status'],'incorrect')
        self.assertEqual(result['distance_correct_rows'],71)
        self.assertIn('wrong_raw_shortest_surface_distance',[item['reason'] for item in result['errors']])

    def test_backend_count_or_trace_reference_cannot_supply_missing_visible_rows(self):
        value = copy.deepcopy(COMPACT)
        value['matches'] = []
        self.assertEqual(value['delivery']['matches_total'],71)
        result = score.score_answer(text(value),truth,snapshot)
        self.assertIsNone(result['status'])
        self.assertTrue(result['review_required'])
        trace_only = '检查完整。完整对象对列表请参见 trace_id=opaque_trace_reference。'
        result = score.score_answer(trace_only,truth,snapshot)
        self.assertIsNone(result['status'])
        self.assertTrue(result['review_required'])

    def test_detailed_layout_with_requested_mm_meets_same_fact_rule(self):
        value = copy.deepcopy(DETAILED)
        for row in value['matches']:
            row['distance_mm'] = str((Decimal(str(row['distance_m']))*1000).quantize(Decimal('.001')))
        self.assertEqual(score.score_answer(text(value),truth,snapshot)['status'], 'complete_correct')

    def test_missing_duplicate_wrong_distance_and_false_complete_are_rejected(self):
        missing = copy.deepcopy(COMPACT)
        missing['matches'].pop()
        self.assertEqual(score.score_answer(text(missing),truth,snapshot)['status'],'incorrect')
        missing['status'] = 'unknown'
        self.assertEqual(score.score_answer(text(missing),truth,snapshot)['status'],'incomplete')
        duplicate = copy.deepcopy(COMPACT)
        duplicate['matches'].append(copy.deepcopy(duplicate['matches'][0]))
        self.assertEqual(score.score_answer(text(duplicate),truth,snapshot)['status'],'incorrect')
        wrong = copy.deepcopy(COMPACT)
        column = wrong['match_columns'].index('distance_mm')
        wrong['matches'][0][column] = '1000.000'
        wrong['status'] = 'partial'
        self.assertEqual(score.score_answer(text(wrong),truth,snapshot)['status'],'incorrect')

    def test_invalid_references_and_encoding_require_independent_review(self):
        for mutate in (
            lambda value: value.update(display_encoding='unsupported-future'),
            lambda value: value['matches'][0].__setitem__(2, len(value['objects'])),
            lambda value: value['matches'][0].__setitem__(2, True),
            lambda value: value['matches'][0].__setitem__(0, 'wrong-readable-name'),
        ):
            with self.subTest(mutate=repr(mutate)):
                value = copy.deepcopy(COMPACT)
                mutate(value)
                result = score.score_answer(text(value),truth,snapshot)
                self.assertIsNone(result['status'])
                self.assertTrue(result['review_required'])

    def test_nine_slots_keep_no_final_execution_failure_and_not_run(self):
        sequence = fixtures.sequence()
        records = [dict(sequence[0],final=text(COMPACT)),
                   dict(sequence[1],final=None),
                   dict(sequence[2],final=text(COMPACT),execution_status='failed')]
        result = score.score_slots(sequence,records,truth,snapshot)
        self.assertEqual(len(result),9)
        self.assertEqual([row['status'] for row in result],
                         ['complete_correct','execution_failure','execution_failure']+['not_run']*6)


class EncodingPackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root/'runtime'
        self.runtime.mkdir()

    def run_pack(self):
        with patch.object(pack,'EVAL',self.root),patch.object(pack,'HERE',self.runtime),\
             patch.object(sys,'argv',['test-pack','handoff']),redirect_stdout(io.StringIO()):
            pack.main()
        return self.runtime/'handoff'

    def test_nine_archives_retain_both_encodings_and_business_fields(self):
        fixture = fixtures.fixture(self.root,all_nine=True)
        for slot in fixture['slots']:
            folder = self.root/'cells'/slot['cell']
            value = copy.deepcopy(COMPACT if slot['group']=='C' else DETAILED)
            value['synthetic_business_extension'] = {'group':'meaningful-domain-value',
                'usage':{'display_only':False},'path':'C:/semantic/object','unknown':[False,0,None]}
            raw_text = text(value)
            response = {'jsonrpc':'2.0','id':'synthetic-admin','result':{'isError':False,
                'content':[{'type':'text','text':raw_text}]}}
            path = folder/'owner/tool_01/RESPONSE.json'
            path.write_bytes(fixtures.encoded(response))
            event = {'perf_ns':100,'event':{'type':'item.completed','item':{'type':'mcp_tool_call',
                'server':'arm_engine','tool':'human_eye_scene_observe','arguments':{'query':{'mode':'surface_scan','threshold_m':.002}},
                'result':{'content':response['result']['content'],'structured_content':None},'status':'completed'}}}
            (folder/'events.jsonl').write_bytes(fixtures.encoded(event).replace(b'\n',b'')+b'\n')
        output = self.run_pack()
        index = json.loads((output/'public/INDEX.json').read_bytes())
        self.assertEqual(index['fixed_slots'],9)
        self.assertFalse(index['scoring_performed'])
        by_id = {row['anonymous_id']:row for row in index['answers']}
        for slot, mapping in zip(fixture['slots'],fixture['mapping']['rows'],strict=True):
            answer = by_id[mapping['anonymous_id']]
            folder = output/'public'/mapping['anonymous_id']
            evidence = json.loads((folder/'tool_evidence.json').read_bytes())
            original = json.loads((self.root/'cells'/slot['cell']/'owner/tool_01/RESPONSE.json').read_bytes())
            self.assertEqual(evidence['owner_attempts'][0]['responses'][0]['value'],{'result':original['result']})
            self.assertEqual(evidence['public_tool_events'][0]['event']['result']['content'],original['result']['content'])
            self.assertEqual((folder/'answer.txt').read_bytes(),fixture['final'].encode())
            self.assertEqual(answer['answer_state'],'present')
            with zipfile.ZipFile(output/'private/raw'/(mapping['anonymous_id']+'.zip')) as archive:
                self.assertEqual(archive.read('owner/tool_01/RESPONSE.json'),fixtures.encoded(original))

    def test_internal_profile_does_not_replace_external_group_binding(self):
        fixture = fixtures.fixture(self.root,all_nine=True)
        path = self.root/'cells/C1/CONSUMER.json'
        consumer = json.loads(path.read_bytes())
        self.assertEqual(consumer['group'],'P')
        consumer['external_group'] = 'O'
        path.write_bytes(fixtures.encoded(consumer))
        with self.assertRaisesRegex(AssertionError,'external/internal'):
            self.run_pack()

    def test_missing_final_stays_missing_and_partial_text_is_unconfirmed(self):
        fixture = fixtures.fixture(self.root,all_nine=True)
        path = self.root/'cells/C1/PUBLIC_FINAL.txt'
        path.unlink()
        output = self.run_pack()
        index = json.loads((output/'public/INDEX.json').read_bytes())
        mapping = next(row for row in fixture['mapping']['rows'] if row['cell']=='C1')
        answer = next(row for row in index['answers'] if row['anonymous_id']==mapping['anonymous_id'])
        self.assertEqual(answer['answer_state'],'missing')
        self.assertIsNone(answer['answer_file'])
        self.assertIn('record_only_text',answer)


if __name__ == '__main__':
    unittest.main(verbosity=2)
