"""Frozen spatial-fact query, summary, memo and public-schema controls."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from human_eye_module1_operators import MeshEntity3D
from human_eye_plugin import live_spatial_mcp as mcp, surface_geometry as closed
from human_eye_plugin import surface_proximity as exact, task_query as task
from human_eye_plugin.auto_router import _validated_scene
from human_eye_plugin.query_policy import validate_query
from human_eye_plugin.scene_cache import SpatialSceneCache


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DESIGNED_PATH = HERE.parent / 'testing/DESIGNED_CASES.json'
DESIGNED = json.loads(DESIGNED_PATH.read_bytes())
PAIRS = {row['id']: row for row in DESIGNED['analytic_pairs']}
REQUESTS = DESIGNED['requests']
EVIDENCE = {'designed_cases_sha256': hashlib.sha256(DESIGNED_PATH.read_bytes()).hexdigest()}


def scene_from(objects, *, source='frozen-spatial-wiring-source'):
    rows = []
    for item in objects:
        name = item['name']
        rows.append(MeshEntity3D(name, '#'+name, name,
            np.asarray(item['vertices_world'], dtype=float), np.asarray(item['triangles'], dtype=int),
            None, (70, 140, 210), False, local_axes=np.eye(3), pivot_world=np.zeros(3)).to_dict())
    return _validated_scene({'revision': 'frozen-spatial-wiring-revision', 'unit': 'm',
        'coordinate_frame': 'world', 'source': source, 'meshes': rows})


def set_query(target, candidates, requested):
    return {'mode': 'task', 'target': {'name': target['name']},
        'candidates': [{'name': item['name']} for item in candidates],
        'requested_facts': list(requested)}


def evaluate(objects, requested, *, cache=None, source='frozen-spatial-wiring-source'):
    scene, meshes, fingerprint = scene_from(objects, source=source)
    query = validate_query(set_query(objects[0], objects[1:], requested))
    work = {}
    value = task.task_result(scene, meshes, fingerprint, query,
        SpatialSceneCache() if cache is None else cache, lambda stage: None, diagnostics=work)
    return value, work


def ast_definition(tree, name):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node, include_attributes=False)
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.dump(node, include_attributes=False)
    raise AssertionError('Missing source definition '+name)


def bounded_evaluator():
    path = ROOT / 'verification/m4_geometry_schema_scope_fix_001/r1/BOUNDED_EVALUATOR.py'
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == '7b9825a50197e4c60c9aaca30ef1d8a4ff69f3452105f55c1f1bd23b586c262c'
    spec = importlib.util.spec_from_file_location('_spatial_wiring_bounded_schema', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.json = json
    module.VISITED = set()
    EVIDENCE['schema_evaluator'] = {'path': str(path), 'sha256': digest,
        'scope': 'reused finite-keyword QA evaluator, no full JSON Schema implementation claim'}
    return module.accepts


class SpatialWiringTests(unittest.TestCase):
    def test_set_versions_share_frozen_distances_and_keep_explicit_closed(self):
        fixtures = DESIGNED['sets']
        objects = [fixtures['target'], fixtures['known']]
        new, new_work = evaluate(objects, REQUESTS['new_set'])
        old, old_work = evaluate(objects, REQUESTS['old_set'])
        self.assertEqual(new['schema_version'], REQUESTS['versions']['new_set'])
        self.assertEqual(old['schema_version'], REQUESTS['versions']['old_set'])
        self.assertEqual(new['relation_fact'], 'spatial_relation')
        self.assertNotIn('relation_fact', old)
        self.assertEqual(new['pairs'][0]['facts']['spatial_relation']['value'], 'separated')
        self.assertEqual(old['pairs'][0]['facts']['closed_solid_relation']['value'], 'separated')
        self.assertNotIn('closed_solid_relation', new['pairs'][0]['facts'])
        self.assertNotIn('spatial_relation', old['pairs'][0]['facts'])
        for value in (new, old):
            self.assertEqual(value['status'], 'observed')
            self.assertTrue(value['summary']['nearest_separated_complete'])
            self.assertEqual(value['summary']['distance_m'], fixtures['ties']['distance_m'])
            self.assertFalse(value['execution_authority'])
            public = mcp._tool_result(value, is_error=False)
            self.assertEqual(json.loads(public['content'][0]['text']), value)
        self.assertEqual(new_work['closed_solid_pair_count'], 0)
        self.assertEqual(old_work['closed_solid_pair_count'], 1)
        EVIDENCE['versions'] = {'new': new, 'old': old, 'new_work': new_work, 'old_work': old_work}

    def test_mixed_open_support_keeps_closed_unknown_and_nearest_complete(self):
        case = PAIRS['open_separated']
        value, work = evaluate([case['left'], case['right']], REQUESTS['mixed'])
        facts = value['pairs'][0]['facts']
        self.assertEqual(facts['spatial_relation']['value'], case['independent_truth']['relation'])
        self.assertEqual(facts['spatial_relation']['certificate'], 'strict_all_referenced_vertex_support')
        self.assertEqual(facts['closed_solid_relation']['status'], case['independent_truth']['explicit_closed'])
        self.assertEqual(facts['closed_solid_relation']['reason'], 'closed_solid_too_few_faces')
        self.assertEqual(value['status'], 'partial')
        self.assertTrue(value['summary']['nearest_separated_complete'])
        self.assertEqual(value['summary']['distance_m'], case['independent_truth']['distance_m'])
        self.assertEqual(work['closed_solid_pair_count'], 1)
        EVIDENCE['mixed_open'] = {'value': value, 'work': work}

    def test_mixed_legal_fallback_reuses_its_single_closed_result(self):
        case = PAIRS['fallback_full_containment']
        with patch.object(closed, 'classify_closed_solids', wraps=closed.classify_closed_solids) as calls, \
                patch.object(task, 'classify_closed_solids', side_effect=AssertionError('duplicate mixed closed')):
            value, work = evaluate([case['left'], case['right']], REQUESTS['mixed'])
        facts = value['pairs'][0]['facts']
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(work['closed_solid_pair_count'], 1)
        self.assertEqual(facts['spatial_relation']['value'], 'penetrating')
        self.assertEqual(facts['closed_solid_relation']['value'], 'penetrating')
        self.assertEqual(facts['spatial_relation']['certificate'], facts['closed_solid_relation']['certificate'])
        self.assertEqual(value['status'], 'observed')
        self.assertEqual(value['pairs'][0]['separation_gap']['status'], 'not_applicable')
        EVIDENCE['mixed_fallback'] = {'value': value, 'work': work, 'closed_calls': calls.call_count}

    def test_mixed_stopped_budget_never_starts_a_second_budget(self):
        fixtures = DESIGNED['sets']
        original_init = exact._Work.__init__

        def exhausted(work, checkpoint, diagnostics):
            original_init(work, checkpoint, diagnostics)
            work.counts['work_units'] = exact.MAX_WORK_UNITS

        with patch.object(exact._Work, '__init__', exhausted), \
                patch.object(task, 'classify_closed_solids', side_effect=AssertionError('mixed after stop')), \
                patch.object(closed, 'classify_closed_solids', side_effect=AssertionError('fallback after stop')):
            value, work = evaluate([fixtures['target'], fixtures['known']], REQUESTS['mixed'])
        facts = value['pairs'][0]['facts']
        for name in ('spatial_relation', 'closed_solid_relation'):
            self.assertEqual(facts[name]['status'], 'unknown')
            self.assertIsNone(facts[name]['value'])
            self.assertEqual(facts[name]['reason'], 'surface_work_budget')
        self.assertEqual(work['closed_solid_pair_count'], 0)
        self.assertEqual(work['pairs'][0]['surface_work']['work_units'], exact.MAX_WORK_UNITS)
        self.assertFalse(value['summary']['nearest_separated_complete'])
        self.assertEqual(value['status'], 'unknown')
        EVIDENCE['mixed_budget_boundary'] = {'value': value, 'work': work,
            'scope': 'actual original Work seeded at its last admissible unit before the next operation'}

    def test_single_pair_new_fact_uses_existing_v3_envelope(self):
        case = PAIRS['open_separated']
        scene, meshes, fingerprint = scene_from([case['left'], case['right']])
        query = validate_query({'mode': 'task',
            'objects': [{'name': case['left']['name']}, {'name': case['right']['name']}],
            'requested_facts': REQUESTS['single_pair']})
        work = {}
        value = task.task_result(scene, meshes, fingerprint, query, SpatialSceneCache(),
            lambda stage: None, diagnostics=work)
        self.assertEqual(value['schema_version'], REQUESTS['versions']['single_pair'])
        self.assertEqual(set(value['facts']), {'spatial_relation'})
        self.assertEqual(value['facts']['spatial_relation']['value'], 'separated')
        self.assertEqual(work['closed_solid_pair_count'], 0)
        self.assertEqual(value['status'], 'observed')
        EVIDENCE['single_pair'] = {'value': value, 'work': work}

    def test_ties_and_unknown_candidate_preserve_collection_completeness(self):
        fixtures = DESIGNED['sets']
        records = []
        for key in ('ties', 'unknown_candidate'):
            expected = fixtures[key]
            objects = [fixtures['target'], *[fixtures[name] for name in expected['candidates']]]
            value, work = evaluate(objects, REQUESTS['new_set'])
            summary = value['summary']
            self.assertEqual(summary['nearest_separated_complete'], expected['complete'])
            self.assertEqual(set(summary['best_known_separated_ids']), set(fixtures['ties']['nearest']))
            self.assertEqual(summary['best_known_distance_m'], fixtures['ties']['distance_m'])
            if expected['complete']:
                self.assertEqual(set(summary['nearest_separated_ids']), set(expected['nearest']))
                self.assertEqual(value['status'], 'observed')
            else:
                self.assertIsNone(summary['nearest_separated_ids'])
                self.assertIsNone(summary['distance_m'])
                self.assertEqual(value['coverage']['unresolved_candidates'], 1)
                self.assertEqual(summary['unresolved_relations'][0]['candidate_index'], 2)
                self.assertEqual(value['status'], 'partial')
            records.append({'id': key, 'value': value, 'work': work})
        EVIDENCE['sets'] = records

    def test_new_memo_isolation_warmth_source_binding_and_unknown_retries(self):
        fixtures = DESIGNED['sets']
        objects = [fixtures['target'], fixtures['known']]
        cache = SpatialSceneCache()
        with patch.object(cache, 'pair_measurement', wraps=cache.pair_measurement) as memo:
            cold, cold_work = evaluate(objects, REQUESTS['new_set'], cache=cache)
            warm, warm_work = evaluate(objects, REQUESTS['new_set'], cache=cache)
            old, old_work = evaluate(objects, REQUESTS['old_set'], cache=cache)
            changed, changed_work = evaluate(objects, REQUESTS['new_set'], cache=cache,
                source='frozen-spatial-wiring-source-changed')
        versions = [call.kwargs['algorithm_version'] for call in memo.call_args_list]
        self.assertIn('task-spatial-relation-strict-support-v1', versions)
        self.assertIn('task-closed-solid-exact-local-evidence-v3', versions)
        self.assertIn('task-surface-proximity-exact-world-rank-v3', versions)
        self.assertEqual(cold_work['spatial_pair_count'], 1)
        self.assertEqual(warm_work['spatial_pair_count'], 0)
        self.assertTrue(warm_work['spatial_pair_cache_hit'])
        self.assertEqual(warm_work['surface_pair_count'], 0)
        self.assertEqual(warm_work['closed_solid_pair_count'], 0)
        self.assertEqual(cold, warm)
        self.assertEqual(old_work['closed_solid_pair_count'], 1)
        self.assertEqual(old_work['surface_pair_count'], 1)
        self.assertEqual(changed_work['spatial_pair_count'], 1)
        self.assertFalse(changed_work['spatial_pair_cache_hit'])
        self.assertNotEqual(cold['binding']['source'], changed['binding']['source'])
        unknown_objects = [fixtures['target'], fixtures['unknown']]
        first, first_work = evaluate(unknown_objects, REQUESTS['new_set'], cache=cache)
        second, second_work = evaluate(unknown_objects, REQUESTS['new_set'], cache=cache)
        self.assertEqual(first['pairs'][0]['facts']['spatial_relation']['status'], 'unknown')
        self.assertEqual(first_work['spatial_pair_count'], 1)
        self.assertEqual(second_work['spatial_pair_count'], 1)
        self.assertFalse(second_work['spatial_pair_cache_hit'])
        self.assertEqual(first, second)
        EVIDENCE['memo'] = {'cold': cold, 'warm_work': warm_work, 'old': old, 'old_work': old_work,
            'source_changed': changed, 'changed_work': changed_work,
            'unknown_work': [first_work, second_work], 'versions': versions}

    def test_scene_observe_schema_and_runtime_accept_the_same_explicit_fact_requests(self):
        fixtures = DESIGNED['sets']
        accepts = bounded_evaluator()
        records = []
        for key in ('old_set', 'new_set', 'mixed'):
            query = set_query(fixtures['target'], [fixtures['known']], REQUESTS[key])
            self.assertTrue(accepts(mcp._QUERY_SCHEMA, query))
            normalized = validate_query(query)
            self.assertEqual(normalized['requested_facts'], REQUESTS[key])
            self.assertIsNone(mcp._validate_arguments('human_eye_scene_observe',
                {'query': query, 'include_image': False}))
            records.append({'id': key, 'query': query, 'accepted': True})
        invalid = [set_query(fixtures['target'], [fixtures['known']], ['spatial_relation']),
            set_query(fixtures['target'], [fixtures['known']], ['surface_proximity']),
            set_query(fixtures['target'], [fixtures['known']], REQUESTS['new_set']+['center_delta']),
            set_query(fixtures['target'], [fixtures['known']], REQUESTS['new_set']+['spatial_relation'])]
        for query in invalid:
            self.assertFalse(accepts(mcp._QUERY_SCHEMA, query))
            with self.assertRaises(ValueError):
                validate_query(query)
            with self.assertRaises(ValueError):
                mcp._validate_arguments('human_eye_scene_observe', {'query': query, 'include_image': False})
            records.append({'query': query, 'accepted': False})
        EVIDENCE['schema'] = records

    def test_compact_schema_mapper_formatter_and_default_stay_byte_bound(self):
        receipt = json.loads((HERE/'INITIAL_SOURCE.json').read_bytes())
        old_raw = (HERE/'live_spatial_mcp.py.before').read_bytes()
        self.assertEqual(hashlib.sha256(old_raw).hexdigest(),
            receipt['sources']['human_eye_plugin\\live_spatial_mcp.py']['before_sha256'])
        old_tree = ast.parse(old_raw)
        new_tree = ast.parse(Path(mcp.__file__).read_bytes())
        names = ('SPATIAL_TASK_TOOLS_SCHEMA', '_TASK_GEOMETRY_SCHEMA', '_spatial_task_query',
                 '_project_spatial_relations', '_validate_arguments', '_tool_result')
        for name in names:
            self.assertEqual(ast_definition(old_tree, name), ast_definition(new_tree, name))
        fixtures = DESIGNED['sets']
        arguments = {'target': {'name': fixtures['target']['name']},
            'candidates': [{'name': fixtures['known']['name']}]}
        mapped = mcp._spatial_task_query(copy.deepcopy(arguments))
        self.assertEqual(mapped['requested_facts'], ['closed_solid_relation', 'surface_proximity'])
        self.assertIsNone(mcp._validate_arguments('human_eye_spatial_relations', arguments))
        old, work = evaluate([fixtures['target'], fixtures['known']], mapped['requested_facts'])
        compact = mcp._project_spatial_relations(old)
        self.assertEqual(compact['schema_version'], 'spatial-relations-v1')
        self.assertEqual(compact['candidates'][0]['closed_solid_relation']['value'], 'separated')
        self.assertNotIn('spatial_relation', compact['candidates'][0])
        public = mcp._tool_result(compact, is_error=False)
        self.assertEqual(json.loads(public['content'][0]['text']), compact)
        with self.assertRaises(ValueError):
            mcp._validate_arguments('human_eye_spatial_relations', dict(arguments, relation_fact='spatial_relation'))
        EVIDENCE['compact'] = {'unchanged_ast': list(names), 'mapped': mapped,
            'value': compact, 'work': work}
