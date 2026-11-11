"""Independent finite replay: fixed-source schema scope only, no product service.

Reads the already-created author snapshot in place; creates no runtime copy.
Schema checks use the earlier reviewed bounded evaluator, not a complete JSON
Schema implementation. Actual product validators execute the same verified bytes.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import types
from contextlib import ExitStack
from types import MappingProxyType
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
WT = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = WT / 'verification/m4_geometry_schema_scope_fix_001'
ENGINE = BATCH / 'r1/e'
BASE = 'be2de48bd9656787c4cdfbc5767c2551defcaada'
HEAD = '00b13060a3cbe709b38f6e98ce04a6e5c3dabfb4'
CANONICAL = '4ebc3910652ee461d9fa7476c8df0ecf6312580d6a02e1066c0eac88bef5c76c'
OLD_MCP = 'b52f6468e6b71eb10b065a89b3417c1ee025e464b9be84d32b0b5625cd1b6275'
NEW_MCP = '0bb0733babb117a6ef6b0afc20bd451a700c347f047f867c4b10434d9222f326'
REFERENCE = Path('D:/hefe/verification/fixes/20261111_m4_relation_selected_review/code/check_geometry_schema_scope.py')
RELATIVE = 'human_eye_plugin/live_spatial_mcp.py'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*arguments):
    return subprocess.run(['git', '-C', str(WT), *arguments], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout


def assignment(tree, name):
    return next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))


def save(name, data):
    with (HERE / name).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def accepted(function, value):
    try:
        result = function(copy.deepcopy(value))
        return {'accepted': True, 'error': None, 'normalized': result}
    except ValueError as error:
        return {'accepted': False, 'error': str(error), 'normalized': None}


def cases():
    # Restated by reviewer after reading implementation, before execution.
    g = {'objects': [{'id': 'a'}]}
    q = {'mode': 'task', 'target': {'id': 'a'}, 'candidates': [{'id': 'b'}],
         'requested_facts': ['closed_solid_relation', 'surface_proximity']}
    full = dict(q, geometry=g)
    result = [
        ('overview_geometry', {'mode': 'overview', 'geometry': g}, True, False),
        ('legacy_AABB_geometry', {'mode': 'task', 'objects': [{'id': 'a'}],
                                  'requested_facts': ['aabb'], 'geometry': g}, True, False),
        ('valid_vertices', full, True, True),
        ('valid_full_AABB', dict(q, requested_facts=q['requested_facts'] + ['aabb'],
                                geometry=dict(g, include_triangles=True)), True, True),
        ('valid_task_no_geometry', q, True, True),
        ('legacy_overview', {'mode': 'overview'}, True, True),
        ('default_query', {}, True, True),
        ('legacy_AABB', {'mode': 'task', 'objects': [{'id': 'a'}],
                          'requested_facts': ['aabb']}, True, True),
        ('nearest_geometry', {'mode': 'surface_nearest', 'objects': [{'id': 'a'}], 'geometry': g}, False, False),
        ('nearest', {'mode': 'surface_nearest', 'objects': [{'id': 'a'}]}, True, True),
        ('geometry_only', {'geometry': g}, True, False),
    ]
    result += [('missing_' + field, {k: v for k, v in full.items() if k != field}, False, False)
               for field in ('mode', 'target', 'candidates', 'requested_facts')]
    result += [
        ('missing_required_fact', dict(full, requested_facts=['aabb']), False, False),
        ('mixed_objects', dict(full, objects=[{'id': 'a'}]), False, False),
        ('unsupported_fact', dict(full, requested_facts=q['requested_facts'] + ['center_delta']), False, False),
        ('empty_geometry', dict(q, geometry={'objects': []}), False, False),
        ('nonboolean_triangles', dict(q, geometry=dict(g, include_triangles=0)), False, False),
    ]
    assert len(result) == 20
    return result


def main():
    assert git('rev-parse', 'HEAD').decode().strip() == HEAD
    status_before = git('status', '--porcelain', '--untracked-files=no').decode()
    assert not status_before
    diff_raw = (BATCH / 'SOURCE_DIFF.json').read_bytes()
    manifest = json.loads(diff_raw)['manifest']
    blobs = {row['path']: (ENGINE / row['path']).read_bytes() for row in manifest}
    assert len(blobs) == 137
    calculated = [{'path': name, 'sha256': sha(raw)} for name, raw in sorted(blobs.items())]
    assert calculated == manifest
    assert all((WT / path).read_bytes() == raw for path, raw in blobs.items())
    runtime_tree = ast.parse(blobs['human_eye_plugin/runtime_identity.py'])
    constants = {name: ast.literal_eval(assignment(runtime_tree, name).value)
                 for name in ('BASE_VERSION', 'IMPLEMENTATION_REVISION')}
    canonical = sha(json.dumps({'base_version': constants['BASE_VERSION'],
                               'implementation_revision': constants['IMPLEMENTATION_REVISION'],
                               'files': manifest}, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())
    assert canonical == CANONICAL
    changed = git('diff', '--name-only', BASE, HEAD, '--', *blobs.keys()).decode().splitlines()
    assert changed == [RELATIVE]
    assert not git('diff', HEAD, '--', *blobs.keys())
    original = git('show', BASE + ':' + RELATIVE)
    candidate = blobs[RELATIVE]
    assert sha(original) == OLD_MCP and sha(candidate) == NEW_MCP
    assert original == (BATCH / 'r1/BASELINE_MCP.py').read_bytes()
    old_tree, new_tree = ast.parse(original), ast.parse(candidate)
    new_query = assignment(new_tree, '_QUERY_SCHEMA').value
    conditions = next(v for k, v in zip(new_query.keys, new_query.values)
                      if isinstance(k, ast.Constant) and k.value == 'allOf')
    condition = ast.literal_eval(conditions.elts.pop())
    assert condition == {'if': {'required': ['geometry']},
                         'then': {'required': ['mode', 'target', 'candidates'],
                                  'properties': {'mode': {'const': 'task'}}}}
    assert ast.dump(old_tree, include_attributes=False) == ast.dump(new_tree, include_attributes=False)

    evaluator_raw = REFERENCE.read_bytes()
    function = next(n for n in ast.parse(evaluator_raw).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'accepts')
    evaluator_namespace = {'json': json, 'VISITED': set()}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(REFERENCE) + ':function-only', 'exec'), evaluator_namespace)
    accepts = evaluator_namespace['accepts']

    sys.dont_write_bytecode = True
    loader = 'human_eye_plugin/verified_source_loader.py'
    helper = types.ModuleType('_human_eye_verified_source_bootstrap')
    helper.__file__ = str(ENGINE / loader)
    sys.modules[helper.__name__] = helper
    exec(compile(blobs[loader], helper.__file__, 'exec', dont_inherit=True), helper.__dict__)
    guard = helper.install(ENGINE.resolve(), manifest, sources=MappingProxyType(blobs), bootstrap_module=helper)
    namespace = types.ModuleType('human_eye_plugin')
    namespace.__path__ = [str(ENGINE / 'human_eye_plugin')]
    guard.allow_namespace(namespace)
    sys.modules[namespace.__name__] = namespace

    attempts = []
    def forbidden(*args, **kwargs):
        attempts.append('process/network/signal attempt')
        raise AssertionError(attempts[-1])

    records, compact_records = [], []
    with ExitStack() as stack:
        for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
            stack.enter_context(patch.object(subprocess, name, side_effect=forbidden))
        for name in ('system', 'kill'):
            stack.enter_context(patch.object(os, name, side_effect=forbidden))
        for name in ('socket', 'create_connection'):
            stack.enter_context(patch.object(socket, name, side_effect=forbidden))
        from human_eye_plugin import live_spatial_mcp as mcp
        from human_eye_plugin.query_policy import validate_query
        from human_eye_plugin.runtime_identity import runtime_identity
        identity = runtime_identity()
        assert identity['source_sha256'] == CANONICAL
        baseline_environment = {'copy': copy, 'SELECTOR_SCHEMA': mcp.SELECTOR_SCHEMA,
            'TASK_FACTS': mcp.TASK_FACTS, 'MAX_VISUAL_LABEL_IDS': mcp.MAX_VISUAL_LABEL_IDS,
            'NATIVE_VISUAL_SCHEMA': mcp.NATIVE_VISUAL_SCHEMA,
            'SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA': mcp.SUPPORT_PLANE_DISCOVERY_REQUEST_SCHEMA}
        for name in ('_ID_SCHEMA', '_VECTOR_SCHEMA', '_TASK_GEOMETRY_SCHEMA', '_QUERY_SCHEMA', 'SPATIAL_TASK_TOOLS_SCHEMA'):
            baseline_environment[name] = eval(compile(ast.Expression(assignment(old_tree, name).value),
                'fixed-old-schema-expression', 'eval'), baseline_environment)
        old_schema = baseline_environment['_QUERY_SCHEMA']
        new_schema = mcp._QUERY_SCHEMA
        assert old_schema == {**new_schema, 'allOf': new_schema['allOf'][:-1]}
        assert baseline_environment['SPATIAL_TASK_TOOLS_SCHEMA'] == mcp.SPATIAL_TASK_TOOLS_SCHEMA
        assert json.loads((BATCH / 'r1/BASELINE_QUERY_SCHEMA.json').read_bytes()) == old_schema
        assert json.loads((BATCH / 'r1/CANDIDATE_QUERY_SCHEMA.json').read_bytes()) == new_schema
        for name, query, old_expected, current_expected in cases():
            frozen = copy.deepcopy(query)
            old_result = accepts(old_schema, query)
            new_result = accepts(new_schema, query)
            runtime = accepted(validate_query, query)
            arguments = {'query': query, 'include_image': False, 'session_id': 'independent-schema-review'}
            generic = accepted(lambda arg: mcp._validate_arguments('human_eye_scene_observe', arg), arguments)
            assert (old_result, new_result, runtime['accepted'], generic['accepted']) == (
                old_expected, current_expected, current_expected, current_expected), name
            assert query == frozen
            records.append({'name': name, 'query': query, 'old_schema': old_result,
                'new_schema': new_result, 'validate_query': runtime, 'generic_validate': generic,
                'expected_old': old_expected, 'expected_current': current_expected})
        tool = 'human_eye_spatial_relations'
        compact_schema = next(t['inputSchema'] for t in mcp.SPATIAL_TASK_TOOLS_SCHEMA if t['name'] == tool)
        base = {'target': {'id': 'a'}, 'candidates': [{'id': 'b'}]}
        geometry = {'objects': [{'id': 'a'}]}
        for mode, extra in [('OFF', {}), ('vertices', {'geometry': geometry}),
                            ('full', {'geometry': dict(geometry, include_triangles=True)})]:
            arguments = copy.deepcopy(dict(base, **extra))
            assert accepts(compact_schema, arguments)
            assert mcp._validate_arguments(tool, arguments) is None
            normalized = validate_query(mcp._spatial_task_query(arguments))
            assert normalized['requested_facts'] == ['closed_solid_relation', 'surface_proximity']
            assert ('geometry' in normalized) == (mode != 'OFF')
            assert arguments == dict(base, **extra)
            compact_records.append({'mode': mode, 'arguments': arguments, 'normalized': normalized,
                                    'schema_accepts': True, 'validator_accepts': True})
        try:
            accepts({'unevaluatedProperties': False}, {})
        except AssertionError:
            unknown_keyword_rejected = True
        else:
            raise AssertionError('bounded evaluator silently accepted unknown keyword')
        guard.verify_loaded()

    assert not attempts
    assert all((ENGINE / path).read_bytes() == raw for path, raw in blobs.items())
    assert all((WT / path).read_bytes() == raw for path, raw in blobs.items())
    assert git('rev-parse', 'HEAD').decode().strip() == HEAD
    assert git('status', '--porcelain', '--untracked-files=no').decode() == status_before
    assert REFERENCE.read_bytes() == evaluator_raw
    evidence_paths = ['REPORT.md', 'REVIEW.md', 'SOURCE_DIFF.json', 'run_checks.py', 'tests/test_schema_scope.py',
                      'r1/RESULTS.json', 'r1/EVIDENCE.json', 'r1/EXECUTION_IDENTITY.json']
    pins = {'head': HEAD, 'baseline': BASE, 'runtime_source_sha256': CANONICAL,
            'source_count': len(manifest), 'manifest': manifest, 'only_changed_runtime_file': changed,
            'before_mcp_sha256': OLD_MCP, 'after_mcp_sha256': NEW_MCP,
            'only_added_condition': condition, 'bytes_added': len(candidate) - len(original),
            'whole_module_AST_equal_after_condition_removal': True,
            'snapshot_location_read_only': str(ENGINE),
            'script_sha256': sha(Path(__file__).read_bytes()),
            'bounded_evaluator_source': str(REFERENCE), 'bounded_evaluator_file_sha256': sha(evaluator_raw),
            'bounded_evaluator_function_AST_sha256': sha(ast.dump(function, include_attributes=False).encode()),
            'author_evidence_pins': {name: sha((BATCH / name).read_bytes()) for name in evidence_paths},
            'snapshot_and_worktree_137_unchanged_after_run': True}
    results = {'passed': True, 'generic_query_cases': records, 'compact_controls': compact_records,
               'generic_count': len(records), 'compact_count': len(compact_records),
               'whole_module_scope_pass': True, 'source_identity_pass': True, 'compact_schema_unchanged': True,
               'baseline_runtime_reexecuted': False, 'validator_same_AST_as_baseline': True,
               'schema_validation_kind': 'Explicit bounded static evaluator, not full JSON Schema implementation',
               'unknown_schema_keyword_rejected': unknown_keyword_rejected,
               'visited_schema_keywords': sorted(evaluator_namespace['VISITED']),
               'guard_verify_loaded_pass': True, 'external_operation_attempts': attempts,
               'Blender_sessions': 0, 'service_dispatches': 0, 'model_consumers': 0,
               'installs': 0, 'performance_measurements': 0, 'new_runtime_source_copies': 0}
    save('SOURCE_PINS.json', pins)
    save('RESULTS.json', results)
    print(json.dumps({'passed': True, 'generic_count': 20, 'compact_count': 3,
                      'runtime_source_sha256': CANONICAL, 'external_operation_attempts': attempts}))


if __name__ == '__main__':
    main()
