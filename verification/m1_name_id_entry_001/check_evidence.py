"""Existing validators/tests and source evidence; no new test cases or live I/O."""
import ast
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BASE = 'c77111f7076b4a1720a98e8c0f8f8af43feb1c34'
REL = 'human_eye_plugin/live_spatial_mcp.py'
sha = lambda data: hashlib.sha256(data).hexdigest()
assert not (OUT / 'RESULTS.json').exists(), 'preserve previous check evidence'
sys.path.insert(0, str(ROOT))
old = subprocess.check_output(['git', 'cat-file', 'blob', BASE + ':' + REL], cwd=ROOT)
new = (ROOT / REL).read_bytes()


def description(raw):
    tree = ast.parse(raw)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            values = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
            name = values.get('name')
            if isinstance(name, ast.Constant) and name.value == 'human_eye_scene_observe':
                return tree, values['description']
    raise ValueError('observe descriptor not found')


before, old_desc = description(old)
after, new_desc = description(new)
old_description = old_desc.value
new_description = new_desc.value
old_bytes, new_bytes = len(old_description.encode()), len(new_description.encode())
assert old_bytes == 1471 and new_bytes <= old_bytes
old_lines, new_lines = old.splitlines(keepends=True), new.splitlines(keepends=True)
assert old_lines[:old_desc.lineno-1] == new_lines[:new_desc.lineno-1]
assert old_lines[old_desc.end_lineno:] == new_lines[new_desc.end_lineno:]
old_desc.value = new_desc.value
assert ast.dump(before) == ast.dump(after)

protected_paths = [
    'verification/consumption_run_final_001/actual_01/RESULTS.json',
    'verification/consumption_run_002/actual_01/RESULTS.json',
    'verification/consumption_run_002/EVIDENCE_INDEX.json',
    'verification/consumption_run_003/actual_01/RESULTS.json',
    'verification/consumption_run_003/EVIDENCE_INDEX.json',
]
protected = {rel: sha((ROOT / rel).read_bytes()) for rel in protected_paths}
bindings = []
for slot, frame in (('02', '006'), ('03', '006'), ('06', '005')):
    folder = ROOT / 'verification/consumption_run_003/actual_01' / slot / 'bridge_he' / frame
    tx, rx = (folder / 'TX.bin').read_bytes(), (folder / 'RX.bin').read_bytes()
    args = json.loads(tx)['params']['arguments']
    result = json.loads(rx)['result']
    packet = json.loads(result['content'][0]['text'])
    assert result['isError'] is False and args['query']['requested_facts'] == ['aabb']
    object_id = packet['binding']['objects'][0]['object_id']
    assert type(object_id) is str and object_id
    bindings.append(dict(slot=slot, frame=frame, tx_path=str((folder/'TX.bin').relative_to(ROOT)),
                         rx_path=str((folder/'RX.bin').relative_to(ROOT)), tx_sha256=sha(tx), rx_sha256=sha(rx),
                         path='binding.objects[0].object_id', nonempty_string=True,
                         object_name_id_and_geometry_values_omitted=True))

forbidden_calls = []


def forbidden(*args, **kwargs):
    forbidden_calls.append('blocked process/network/signal operation')
    raise AssertionError(forbidden_calls[-1])


started = datetime.now(timezone.utc).isoformat()
started_ns = time.perf_counter_ns()
stream, stdout = io.StringIO(), io.StringIO()
with ExitStack() as guards, redirect_stdout(stdout), redirect_stderr(stream):
    for name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
        guards.enter_context(patch.object(subprocess, name, side_effect=forbidden))
    for name in ('kill', 'system'):
        guards.enter_context(patch.object(os, name, side_effect=forbidden))
    guards.enter_context(patch.object(socket, 'socket', side_effect=forbidden))
    guards.enter_context(patch.object(socket, 'create_connection', side_effect=forbidden))
    from human_eye_plugin import live_spatial_mcp as current, runtime_identity, blender_host
    baseline = types.ModuleType('_m1_baseline_descriptor')
    baseline.__file__ = str(ROOT / REL)
    baseline.__package__ = 'human_eye_plugin'
    exec(compile(old, 'baseline:' + sha(old) + ':' + REL, 'exec', dont_inherit=True), baseline.__dict__)
    old_tools = json.loads(json.dumps(baseline.LIVE_MCP_TOOLS_SCHEMA))
    new_tools = json.loads(json.dumps(current.LIVE_MCP_TOOLS_SCHEMA))
    for tools in (old_tools, new_tools):
        next(t for t in tools if t['name'] == 'human_eye_scene_observe').pop('description')
    assert old_tools == new_tools
    decoder, examples, position = json.JSONDecoder(), [], 0
    while True:
        position = new_description.find('{', position)
        if position < 0:
            break
        value, length = decoder.raw_decode(new_description[position:])
        current._validate_arguments('human_eye_scene_observe', value)
        examples.append(value)
        position += length
    assert len(examples) == 2
    assert examples[0]['query']['mode'] == 'task' and examples[1]['query'] == {'mode': 'surface_nearest'}
    assert 'identity' not in current.TASK_FACTS and 'object_identity' not in current.TASK_FACTS
    import verification.test_blender_host_contracts as fixtures
    fixtures._module = blender_host
    fixtures.BlenderSceneHost = blender_host.BlenderSceneHost
    fixtures.BlenderHostError = blender_host.BlenderHostError
    import verification.test_task_query as task_tests
    import verification.test_production_entry as identity_tests
    entry_path = ROOT / 'verification/surface_nearest_entry_001/tests/test_surface_nearest_entry.py'
    entry_raw = entry_path.read_bytes()
    entry = types.ModuleType('_m1_existing_entry_checks')
    entry.__file__ = str(entry_path)
    exec(compile(entry_raw, 'existing-test:' + sha(entry_raw), 'exec', dont_inherit=True), entry.__dict__)
    temporary = OUT / 'tmp'
    temporary.mkdir(exist_ok=True)
    guards.enter_context(patch.object(tempfile, 'tempdir', str(temporary)))
    guards.enter_context(patch.object(entry, 'TESTS', temporary))
    suite = unittest.TestSuite([
        entry.SurfaceNearestEntryTests('test_01_explicit_mode_schema_and_mode_only_query'),
        entry.SurfaceNearestEntryTests('test_02_invalid_envelopes_fail_before_any_host_read'),
        task_tests.TaskQueryTests('test_name_and_id_have_identical_facts_from_current_capture'),
        task_tests.TaskQueryTests('test_query_prevalidation_rejects_ambiguous_shapes_and_unknown_facts'),
        task_tests.TaskQueryTests('test_v3_keeps_trace_link_and_audited_work_without_wrapper_construction'),
        identity_tests.RuntimeIdentityTests('test_source_manifest_hash_is_reproducible_and_includes_identity'),
    ])
    methods = [test.id() for test in suite]
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    identity = runtime_identity.runtime_identity()
    assert runtime_identity.check_source_drift()['compatible'] is True
elapsed_ns = time.perf_counter_ns() - started_ns
assert not forbidden_calls
assert all(sha((ROOT / rel).read_bytes()) == digest for rel, digest in protected.items())
assert (ROOT / REL).read_bytes() == new
old_manifest = json.loads((ROOT / 'verification/consumption_run_003/PLAN.json').read_bytes())['product_manifest']
old_sources = {row['path']: row['sha256'] for row in old_manifest}
new_sources = {row['path']: row['sha256'] for row in identity['source_files']}
assert old_sources.keys() == new_sources.keys() and len(new_sources) == 131
changed_sources = [path for path in old_sources if old_sources[path] != new_sources[path]]
assert changed_sources == [REL]
(OUT / 'SOURCE_IDENTITY.json').write_text(json.dumps(identity, indent=2)+'\n', encoding='utf8', newline='\n')
(OUT / 'EXAMPLES.json').write_text(json.dumps(examples, indent=2)+'\n', encoding='utf8', newline='\n')
(OUT / 'CHECK_STDOUT.txt').write_text(stdout.getvalue(), encoding='utf8', newline='\n')
(OUT / 'CHECK_STDERR.txt').write_text(stream.getvalue(), encoding='utf8', newline='\n')
record = dict(baseline_HEAD=BASE, started_utc=started, elapsed_ns=elapsed_ns,
              old_description_utf8_bytes=old_bytes, new_description_utf8_bytes=new_bytes,
              delta_utf8_bytes=new_bytes-old_bytes, old_file_sha256=sha(old), new_file_sha256=sha(new),
              only_description_AST_changed=True, bytes_outside_description_unchanged=True,
              all_descriptors_except_observe_description_identical=True, example_validator_acceptances=2,
              existing_methods=methods, methods_run=result.testsRun, failures=len(result.failures),
              errors=len(result.errors), skipped=len(result.skipped), successful=result.wasSuccessful(),
              runtime_source_sha256=identity['source_sha256'], source_count=131, changed_source_files=changed_sources,
              source_identity_method='existing runtime_identity fresh ordinary imports; no verified-loader execution claim',
              existing_aabb_binding_evidence=bindings, protected_original_hashes=protected, protected_originals_unchanged=True,
              new_test_cases=0, actual_consumers=0, actual_Codex_CLI=0, actual_Blender=0,
              actual_MCP_services=0, actual_RPC=0, actual_API=0, actual_paid_API=0, forbidden_calls=0)
(OUT / 'RESULTS.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf8', newline='\n')
print(json.dumps({k: record[k] for k in ('old_description_utf8_bytes','new_description_utf8_bytes','methods_run','failures','errors','successful','runtime_source_sha256')}))
raise SystemExit(0 if result.wasSuccessful() else 1)
