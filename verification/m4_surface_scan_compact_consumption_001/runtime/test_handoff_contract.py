"""Offline projection and fixed-denominator checks for the post-run verifier."""
import ast
import importlib.util
from pathlib import Path
import unittest


BATCH = Path(__file__).resolve().parent.parent
PATH = BATCH / 'verify_handoff.py'
spec = importlib.util.spec_from_file_location('_tri_handoff_verifier_contract', PATH)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class HandoffContractTests(unittest.TestCase):
    def test_request_projection_removes_only_transport_envelopes(self):
        original = {'jsonrpc': '2.0', 'id': 7, '_meta': {'cost': 12},
            'method': 'tools/call', 'params': {'name': 'human_eye_scene_observe',
                '_meta': {'group': 'C'}, 'arguments': {'query': {'mode': 'surface_scan'},
                    'response_detail': 'full', 'group': 'business-value', 'cost': 'business-value'}}}
        projected = verifier.request_projection(original)
        self.assertNotIn('id', projected)
        self.assertNotIn('_meta', projected['params'])
        self.assertEqual(projected['params']['arguments'], original['params']['arguments'])
        self.assertIn('_meta', original['params'])

    def test_response_projection_preserves_old_and_compact_business_values(self):
        for matches in ([{'objects': [{'id': 'a', 'name': 'x'}, {'id': 'b', 'name': 'x'}],
                          'distance_m': 0.001}], [['x', 'x', 0, 1, 0.001, 1.0]]):
            payload = {'status': 'unknown', 'matches': matches, 'unknown': ['source'],
                'delivery': {'complete': False}, 'group': 'business-value',
                'usage': 'business-value', 'error': 'business-value'}
            response = {'jsonrpc': '2.0', 'id': 7, 'result': payload}
            projected = verifier.response_projection(response)
            self.assertEqual(projected, {'result': payload})
            self.assertEqual(projected['result']['matches'], matches)

    def test_main_is_nine_slot_two_profile_and_never_scores(self):
        tree = ast.parse(PATH.read_bytes())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        source = ast.get_source_segment(PATH.read_text(encoding='utf8'), main)
        self.assertIn("['N1','O1','C1','O2','C2','N2','C3','N3','O3']", source)
        self.assertIn("plan['logical_denominator'] == 9", source)
        self.assertIn("index['fixed_slots'] == 9", source)
        self.assertIn("set(profiles) == {'O', 'C'}", source)
        self.assertIn('quality_scoring_performed=False', source)
        called = {node.func.id for node in ast.walk(main)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertFalse(called.intersection({'score', 'score_answer', 'grade', 'run_models', 'consume'}))


if __name__ == '__main__':
    unittest.main()
