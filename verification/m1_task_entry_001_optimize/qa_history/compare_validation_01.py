"""Fixed before/after checks for one MCP query-validation deduplication.

The root agent alone runs this script. Child interpreters isolate the two
original source guards; neither Blender nor a network/model service is used.
"""
import argparse
import ast
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import types
from types import MappingProxyType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = 'b296bae6f6e9f5fddda19f0fd6dc9eadcabee1f3'
MCP = 'human_eye_plugin/live_spatial_mcp.py'
CANDIDATE = 'babbb88e4ee044e753798c81f78866aaa193642d7408ac4cd7c6ea7216e65928'
SOURCE = '0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a'
SCENE = 'human_eye_scene_observe'
RELATIONS = 'human_eye_spatial_relations'
NEAREST = 'human_eye_surface_nearest'
TASK = {'mode': 'task', 'target': {'id': 'a'}, 'candidates': [{'id': 'b'}],
        'requested_facts': ['closed_solid_relation', 'surface_proximity']}
SURFACE = {'mode': 'surface_nearest', 'objects': [{'name': 'O0'}]}
BAD_QUERY = 'query contains unsupported observation fields'
BAD_IMAGE = 'include_image must be boolean'
REQUIRED = 'surface_nearest requires session_id, one target, include_image=false and no reference, goal or scene_delta'
CONFLICT = 'surface_nearest accepts query.objects or focal_id, not both'
TASK_CONFLICT = 'task queries require include_image=false and selectors only in query.objects or query.target/query.candidates'
sha = lambda raw: hashlib.sha256(raw).hexdigest()

# Expectations come from the frozen b296 contract and the approved one-call
# design, not from either runtime's output. Tuple: id, tool, exact arguments,
# baseline count, candidate count, expected ValueError message (None = accept).
CASES = [
 ('overview_explicit', SCENE, {'query': {'mode': 'overview'}}, 4, 1, None),
 ('overview_omitted', SCENE, {}, 3, 1, None),
 ('overview_null', SCENE, {'query': None}, 4, 1, None),
 ('ordinary_nearest', SCENE, {'query': {'mode': 'nearest', 'object_ids': ['b']}}, 4, 1, None),
 ('ordinary_task', SCENE, {'query': TASK, 'include_image': False}, 4, 1, None),
 ('surface_selector', SCENE, {'session_id': 'fixed', 'query': SURFACE, 'include_image': False}, 5, 1, None),
 ('surface_focal', SCENE, {'session_id': 'fixed', 'focal_id': 'f', 'query': {'mode': 'surface_nearest'}, 'include_image': False}, 5, 1, None),
 ('bad_query_before_bad_image', SCENE, {'query': [], 'include_image': 0}, 1, 1, BAD_QUERY),
 ('omitted_query_after_bad_image', SCENE, {'include_image': 0}, 0, 0, BAD_IMAGE),
 ('null_query_before_bad_image', SCENE, {'query': None, 'include_image': 0}, 1, 1, BAD_IMAGE),
 ('valid_query_before_bad_image', SCENE, {'query': {'mode': 'overview'}, 'include_image': 0}, 1, 1, BAD_IMAGE),
 ('false_query_is_not_default', SCENE, {'query': False}, 1, 1, BAD_QUERY),
 ('surface_missing_session', SCENE, {'query': SURFACE, 'include_image': False}, 3, 1, REQUIRED),
 ('surface_conflict_before_missing_session', SCENE, {'query': SURFACE, 'focal_id': 'f'}, 3, 1, CONFLICT),
 ('surface_forbidden_reference', SCENE, {'session_id': 'fixed', 'query': SURFACE, 'include_image': False, 'reference_id': 'r'}, 3, 1, REQUIRED),
 ('task_focal_conflict', SCENE, {'query': TASK, 'include_image': False, 'focal_id': 'f'}, 4, 1, TASK_CONFLICT),
 ('alignment_before_bad_context', SCENE, {'query': {'alignment_evidence': False}, 'task_context': None}, 3, 1, 'alignment_evidence=false requires include_image=false'),
 ('extra_before_bad_query', SCENE, {'query': [], 'extra': True}, 0, 0, 'Unexpected tool arguments'),
 ('unknown_tool', 'human_eye_not_a_tool', {'query': []}, 0, 0, 'Unknown tool: human_eye_not_a_tool'),
 ('session_before_bad_query', SCENE, {'session_id': None, 'query': []}, 0, 0, 'session_id must be a nonempty string'),
 ('compact_relations', RELATIONS, {'target': {'id': 'a'}, 'candidates': [{'id': 'b'}]}, 1, 1, None),
 ('compact_nearest', NEAREST, {'target': {'name': 'O0'}}, 1, 1, None),
 ('nonobserve_status_short_circuit', 'human_eye_connection_status', {}, 0, 0, None),
 ('nonobserve_transform_short_circuit', 'human_eye_transform', {'action': {'focal_id': 'a', 'reference_id': 'b', 'translation': [0, 0, 1]}}, 0, 0, None),
]


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True)+'\n', encoding='utf8')


def manifest(blobs):
    return [dict(path=path, sha256=sha(raw)) for path, raw in sorted(blobs.items())]


def canonical(blobs):
    tree = ast.parse(blobs['human_eye_plugin/runtime_identity.py'])
    values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in ('BASE_VERSION', 'IMPLEMENTATION_REVISION')}
    return sha(json.dumps(dict(base_version=values['BASE_VERSION'],
        implementation_revision=values['IMPLEMENTATION_REVISION'], files=manifest(blobs)),
        sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())


def child(folder, phase):
    engine = folder/phase/'engine'
    rows = json.loads((folder/phase/'MANIFEST.json').read_bytes())
    blobs = {row['path']: (engine/row['path']).read_bytes() for row in rows}
    assert all(sha(blobs[row['path']]) == row['sha256'] for row in rows)
    helper = types.ModuleType('_human_eye_verified_source_bootstrap')
    helper.__file__ = str(engine/'human_eye_plugin/verified_source_loader.py')
    sys.modules[helper.__name__] = helper
    exec(compile(blobs['human_eye_plugin/verified_source_loader.py'], helper.__file__, 'exec', dont_inherit=True), helper.__dict__)
    guard = helper.install(engine.resolve(), rows, sources=MappingProxyType(blobs), bootstrap_module=helper)
    package = types.ModuleType('human_eye_plugin')
    package.__path__ = [str(engine/'human_eye_plugin')]
    guard.allow_namespace(package)
    sys.modules[package.__name__] = package
    sys.path.insert(0, str(ROOT))
    from human_eye_plugin import runtime_identity, blender_host, live_service as service_module, live_spatial_mcp as mcp
    identity = runtime_identity.runtime_identity()
    assert identity['source_sha256'] == canonical(blobs)
    blender_host._READONLY_LOADED_HOST_SHA256 = sha(blobs['human_eye_plugin/blender_host.py'])
    blender_host._FIRST_FACE_FIXED_GIT = True
    blocked = []
    def forbidden(*args, **kwargs):
        blocked.append('external process/network/signal')
        raise AssertionError(blocked[-1])
    result = dict(phase=phase, runtime_source_sha256=identity['source_sha256'],
        source_kind=identity['source_kind'], validation=[], integration=[])
    with ExitStack() as stack:
        for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
            stack.enter_context(patch.object(subprocess, name, side_effect=forbidden))
        for name in ('kill', 'system'):
            stack.enter_context(patch.object(os, name, side_effect=forbidden))
        stack.enter_context(patch.object(socket, 'socket', side_effect=forbidden))
        stack.enter_context(patch.object(socket, 'create_connection', side_effect=forbidden))
        for case_id, name, original, before, after, message in CASES:
            arguments = copy.deepcopy(original)
            exception = None
            with patch.object(mcp, 'validate_query', wraps=mcp.validate_query) as count:
                try:
                    value = mcp._validate_arguments(name, arguments)
                    assert value is None
                except ValueError as exc:
                    exception = dict(type=type(exc).__name__, message=str(exc))
            expected = None if message is None else dict(type='ValueError', message=message)
            row = dict(id=case_id, exception=exception, expected_exception=expected,
                mcp_validate_query=count.call_count, expected_count=before if phase == 'baseline' else after,
                input_unchanged=arguments == original, service_observe=0, captures=0)
            row['passed'] = exception == expected and row['mcp_validate_query'] == row['expected_count'] and row['input_unchanged']
            result['validation'].append(row)

        # Reuse actual bounded service/capture fixtures, without their tests.
        from verification import test_blender_host_contracts as fixtures
        fixtures._module = blender_host
        fixtures.BlenderSceneHost = blender_host.BlenderSceneHost
        fixtures.BlenderHostError = blender_host.BlenderHostError
        from verification.surface_nearest_entry_001.tests.test_surface_nearest_entry import ActualCandidateHost
        from verification.arch_read_context_001.test_resident_task import TokenSelectedHost
        for case_id, name, original, compact, enabled, expected_local, expected_capture in (
            ('overview_disabled', SCENE, {'query': {'mode': 'overview'}, 'include_image': False}, False, False, (4, 1), 0),
            ('ordinary_task_actual', SCENE, {'query': TASK, 'include_image': False}, False, True, (4, 1), 1),
            ('ordinary_nearest_actual', SCENE, {'session_id': 'fixed', 'query': SURFACE, 'include_image': False}, False, True, (5, 1), 1),
            ('compact_relations_actual', RELATIONS, {'target': {'id': 'a'}, 'candidates': [{'id': 'b'}]}, True, True, (1, 1), 1),
            ('compact_nearest_actual', NEAREST, {'target': {'name': 'O0'}}, True, True, (1, 1), 1),
        ):
            target = folder/phase/case_id
            target.mkdir()
            config = target/'config.json'
            config.write_text(json.dumps(dict(schema_version='1.0', project_root=str(ROOT),
                enabled=enabled, state_file='actions.json', audit_file='audit.jsonl', quad_size=64)), encoding='utf8')
            nearest = 'nearest' in case_id
            host = ActualCandidateHost() if nearest else TokenSelectedHost()
            service = service_module.LiveSpatialService(config, host=host)
            server = mcp.LiveSpatialMCPServer(service, default_session_id='fixed', spatial_task_only=compact)
            arguments = copy.deepcopy(original)
            with patch.object(mcp, 'validate_query', wraps=mcp.validate_query) as local, \
                 patch.object(service_module, 'validate_query', wraps=service_module.validate_query) as independent, \
                 patch.object(service, 'observe', wraps=service.observe) as observe:
                output = server._dispatch_tool(name, arguments)
            body = json.loads(output['content'][0]['text'])
            trace = body.get('trace_id')
            def normalize(value):
                if isinstance(value, dict): return {key: normalize(item) for key, item in value.items()}
                if isinstance(value, list): return [normalize(item) for item in value]
                if isinstance(value, str):
                    value = value.replace(identity['build_id'], '<BUILD>').replace(identity['source_sha256'], '<SOURCE>')
                    if trace: value = value.replace(trace, '<TRACE>')
                return value
            captures = len(host.candidate_calls) if nearest else len(host.selected_calls)
            expected_status = 'disabled' if not enabled else 'complete' if nearest else 'observed'
            # Independent geometry expectations: two x-separated parallel
            # triangles are 2 m apart; disjoint 2 m boxes centred 4 m apart
            # have a 2 m gap. The fixture does not provide a final answer.
            geometric = (body.get('distance_m') == 2. if nearest else
                body['sets']['nearest_separated']['distance_m'] == 2. if compact else
                body['summary']['distance_m'] == 2. if enabled else body.get('routing') is None)
            row = dict(id=case_id, output=normalize({**output, 'content': [{'type': 'text', 'json': body}]}),
                mcp_validate_query=local.call_count, expected_count=expected_local[0 if phase == 'baseline' else 1],
                service_validate_query=independent.call_count, service_observe=observe.call_count,
                captures=captures, expected_captures=expected_capture, input_unchanged=arguments == original)
            row['passed'] = (row['mcp_validate_query'] == row['expected_count'] and independent.call_count == 1
                and observe.call_count == 1 and captures == expected_capture and arguments == original
                and body['status'] == expected_status and output['isError'] == (not enabled) and geometric and host.calls == 0)
            result['integration'].append(row)
        # The service retains its own validator even without the MCP adapter.
        bad = {'mode': 'overview', 'unsupported': True}
        original = copy.deepcopy(bad)
        capture_before = len(host.candidate_calls)
        with patch.object(service_module, 'validate_query', wraps=service_module.validate_query) as independent:
            try:
                service.observe('direct', query=bad, include_image=False)
                direct = None
            except ValueError as exc:
                direct = dict(type=type(exc).__name__, message=str(exc))
        result['direct_service'] = dict(exception=direct, service_validate_query=independent.call_count,
            input_unchanged=bad == original, capture_delta=len(host.candidate_calls)-capture_before,
            passed=direct == dict(type='ValueError', message=BAD_QUERY)
            and independent.call_count == 1 and bad == original and len(host.candidate_calls) == capture_before)
        result['guard_verify_loaded'] = guard.verify_loaded()
    result['external_operation_attempts'] = blocked
    result['snapshot_unchanged'] = all((engine/path).read_bytes() == raw for path, raw in blobs.items())
    result['passed'] = all(row['passed'] for group in ('validation', 'integration') for row in result[group]) and result['direct_service']['passed'] and result['guard_verify_loaded'] and result['snapshot_unchanged'] and not blocked
    save(folder/phase/'RESULTS.json', result)
    return 0 if result['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', help='new immediate child directory of this script directory')
    parser.add_argument('--child', choices=('baseline', 'candidate'))
    args = parser.parse_args()
    folder = HERE/args.output
    if folder.parent.resolve() != HERE.resolve(): raise ValueError('output must be a new immediate child')
    if args.child: return child(folder.resolve(), args.child)
    folder.mkdir(exist_ok=False)
    listed = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE], cwd=ROOT).decode().splitlines()
    tree = ast.parse((ROOT/'human_eye_plugin/runtime_identity.py').read_bytes())
    roots = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name) and node.targets[0].id == '_ROOT_MODULES')
    names = sorted(set(roots) | {name for name in listed if name.endswith('.py')
        and len(Path(name).parts) == 2 and Path(name).parts[0] in ('human_eye_plugin', 'human_eye_module1_operators')})
    baseline = {name: subprocess.check_output(['git', 'show', BASE+':'+name], cwd=ROOT) for name in names}
    candidate = {name: (ROOT/name).read_bytes() for name in names}
    assert len(candidate) == len(baseline) == 137
    assert sha(candidate[MCP]) == CANDIDATE and canonical(candidate) == SOURCE
    assert [name for name in names if baseline[name] != candidate[name]] == [MCP]
    def other_nodes(raw):
        return [ast.dump(node, include_attributes=False) for node in ast.parse(raw).body
                if not isinstance(node, ast.FunctionDef) or node.name != '_validate_arguments']
    assert other_nodes(baseline[MCP]) == other_nodes(candidate[MCP])
    save(folder/'EXPECTED_CASES.json', [dict(id=i, tool=n, arguments=a, baseline_count=b,
        candidate_count=c, expected_exception=None if e is None else dict(type='ValueError', message=e))
        for i, n, a, b, c, e in CASES])
    for phase, blobs in (('baseline', baseline), ('candidate', candidate)):
        target = folder/phase
        target.mkdir()
        for name, raw in blobs.items():
            path = target/'engine'/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        save(target/'MANIFEST.json', manifest(blobs))
        process = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()), args.output, '--child', phase], cwd=ROOT, capture_output=True)
        (target/'STDOUT.txt').write_bytes(process.stdout)
        (target/'STDERR.txt').write_bytes(process.stderr)
        save(target/'EXIT.json', dict(returncode=process.returncode))
    before = json.loads((folder/'baseline/RESULTS.json').read_bytes())
    after = json.loads((folder/'candidate/RESULTS.json').read_bytes())
    compare = []
    for group in ('validation', 'integration'):
        for left, right in zip(before[group], after[group], strict=True):
            keys = ('exception', 'input_unchanged', 'service_observe', 'captures') if group == 'validation' else ('output', 'input_unchanged', 'service_validate_query', 'service_observe', 'captures')
            compare.append(dict(id=left['id'], equal=left['id'] == right['id'] and all(left[key] == right[key] for key in keys)))
    summary = dict(baseline_commit=BASE, candidate_file_sha256=CANDIDATE,
        baseline_source_sha256=canonical(baseline), candidate_source_sha256=canonical(candidate),
        source_count=137, validation_cases=len(CASES), integration_cases=5,
        direct_service_checks=1, comparisons=compare,
        actual_source_unchanged=all((ROOT/name).read_bytes() == raw for name, raw in candidate.items()),
        runner_sha256=sha(Path(__file__).read_bytes()),
        normalization='Only exact runtime source/build digest and response trace ID are substituted; parsed JSON facts and error contents remain.',
        limits='Offline bounded representative checks. Overview uses disabled real service (no geometry). No performance/model/Blender/installation claim.')
    summary['passed'] = before['passed'] and after['passed'] and all(row['equal'] for row in compare) and before['direct_service'] == after['direct_service'] and summary['actual_source_unchanged']
    save(folder/'RESULTS.json', summary)
    print(json.dumps(summary))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
