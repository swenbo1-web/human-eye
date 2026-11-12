"""Read-only asset binding and mocked owner-cleanup checks, without child processes."""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def asset_check():
    source = ROOT / 'verification/m3_sufficient_separation_001/entry/run_01'
    session = json.loads((source / 'native/SESSION.json').read_bytes())
    config = json.loads((source / 'native/CONFIG.json').read_bytes())
    bindings = json.loads((source / 'INPUT_BINDINGS.json').read_bytes())
    actual = source / 'ACTUAL_SNAPSHOT.json'
    expected_asset = '27f197a8cc312832382ae06cb633cbf846f20a1a22797909a15dfda8513ade46'
    expected_snapshot = '29dfdccd839170b70ec03339925323d433b5e4221d1caac6649b2060fefa453c'
    copied = source / 'native/input.blend'
    assert Path(session['asset_copy']).resolve() == copied.resolve()
    assert config['asset_copy'] == session['asset_copy']
    assert config['asset'] == session['asset'] == bindings['asset_manifest']['asset']
    assert session['asset_sha256'] == config['asset_sha256'] == bindings['asset_manifest']['asset_sha256'] == expected_asset
    assert digest(copied) == digest(Path(session['asset'])) == expected_asset
    assert digest(actual) == expected_snapshot
    snapshot = json.loads(actual.read_bytes())
    receipt = json.loads((source / 'QA_SNAPSHOT_RECEIPT.json').read_bytes())
    assert json.loads(receipt['response']['result']['result']) == snapshot
    assert len(snapshot['objects']) == 14
    assert sum(len(row['vertices_world']) for row in snapshot['objects']) == 848
    assert sum(len(row['triangles']) for row in snapshot['objects']) == 1640
    return {'asset_copy': str(copied), 'asset_sha256': expected_asset,
            'source_session': str(source / 'native/SESSION.json'),
            'snapshot': str(actual), 'snapshot_sha256': expected_snapshot,
            'recorded_capture_matches_snapshot': True, 'passed': True}


class FakeInput:
    def __init__(self, broken=False):
        self.broken = broken
        self.closed = False

    def write(self, unused):
        if self.broken:
            raise BrokenPipeError('synthetic_pipe_closed')

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, broken=False):
        self.pid = 799999
        self.stdin = FakeInput(broken)
        self.returncode = None
        self.wait_calls = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls += 1
        self.returncode = 0
        return 0

    def kill(self):
        self.returncode = -1


def load_driver(path, label):
    spec = importlib.util.spec_from_file_location('_cleanup_review_' + label, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cleanup_checks(path, output):
    module = load_driver(path, output.name)
    output.mkdir(parents=True, exist_ok=False)
    expected_ready = {'dependency_python': 'synthetic-no-process-python'}
    plan = {'tasks': {'T1': {'asset': 'asset.blend', 'asset_sha256': 'synthetic-asset'}},
            'inputs': {'scene': 'asset.blend', 'scene_sha256': 'synthetic-asset'}}
    slot = {'cell': 'synthetic', 'round': 1, 'group': 'N', 'task': 'T1'}
    records = []

    def forbidden(*args, **kwargs):
        raise AssertionError('unexpected subprocess execution')

    for case in ('launch_receipt_write_failure', 'finish_broken_pipe'):
        folder = output / case
        process = FakeProcess(broken=case == 'finish_broken_pipe')
        fake_subprocess = SimpleNamespace(Popen=lambda *args, **kwargs: process, PIPE=object(),
            CREATE_NO_WINDOW=0, TimeoutExpired=subprocess.TimeoutExpired, run=forbidden)
        error = None
        result = None

        def fake_read(candidate):
            return plan if Path(candidate).name == 'PLAN.json' else expected_ready

        def fake_save(candidate, value):
            if Path(candidate).name == 'ACTOR_LAUNCH.json' and case == 'launch_receipt_write_failure':
                raise OSError('synthetic_launch_receipt_write_failed')
            Path(candidate).parent.mkdir(parents=True, exist_ok=True)
            Path(candidate).write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')

        with patch.multiple(module, HERE=output, subprocess=fake_subprocess, read=fake_read,
                            save=fake_save, sha=lambda unused: 'synthetic-asset',
                            arm_runtime=lambda *args: (slot, expected_ready, 'P')):
            try:
                if case == 'launch_receipt_write_failure':
                    module.prepare(slot, output=folder, cell_started_ns=time.perf_counter_ns())
                else:
                    (folder / 'owner').mkdir(parents=True)
                    (folder / 'owner/CLOSE.json').write_text('{}', encoding='utf8')
                    result = module.finish(folder, process)
            except BaseException as exc:
                error = {'type': type(exc).__name__, 'message': str(exc)}
        records.append({'case': case, 'process_reaped': process.poll() is not None,
                        'wait_calls': process.wait_calls, 'stdin_closed': process.stdin.closed,
                        'error': error, 'result': result})
    return {'driver': str(path), 'driver_sha256': digest(path), 'cases': records,
            'all_owned_processes_reaped': all(row['process_reaped'] and row['wait_calls'] for row in records),
            'actual_subprocesses': 0, 'model_calls': 0, 'Blender_sessions': 0}


def contract_checks(path):
    module = load_driver(path, 'contracts')
    ready = {'source_sha256': '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390',
             'source_count': 137, 'commit': 'e836e03f4b3821f869c72ac3e50df5204f28b50f',
             'dependency_python': 'synthetic-common-python'}
    groups = ['N', 'P', 'P', 'N', 'N', 'P']
    plan = {'cycle_id': module.CYCLE, 'batch': module.CYCLE, 'image_count': 0, 'new_images': 0,
            'installations': {'P': ready}, 'installation_ready': ready,
            'arms': {'N': {'actor_group': 'N', 'installation_profile': 'P', 'source_sha256': None},
                     'P': {'actor_group': 'P', 'installation_profile': 'P', 'source_sha256': ready['source_sha256']}},
            'sequence': [{'cell': 'spc' + str(i + 1).zfill(2), 'round': i // 2 + 1,
                          'task': 'T1', 'group': group} for i, group in enumerate(groups)]}
    authorization = {'task': module.CYCLE, 'authorized': True, 'plan_sha256': 'synthetic-plan', 'max_consumers': 6}
    module.go_contract(authorization, plan, 'synthetic-plan')
    rejected = []
    for case in ('old_nine_count', 'old_image_count', 'unexpected_group', 'duplicate_slot', 'plan_binding_changed'):
        modified = copy.deepcopy(plan)
        go = dict(authorization)
        if case == 'old_nine_count':
            go['max_consumers'] = 9
        elif case == 'old_image_count':
            modified['image_count'] = 1
        elif case == 'unexpected_group':
            modified['sequence'][0]['group'] = 'G'
        elif case == 'duplicate_slot':
            modified['sequence'][-1]['cell'] = modified['sequence'][0]['cell']
        else:
            go['plan_sha256'] = 'another-plan'
        try:
            module.go_contract(go, modified, 'synthetic-plan')
        except AssertionError:
            rejected.append(case)
    assert len(rejected) == 5
    object_data = {'name': 'synthetic-object', 'vertices_local': [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                   'matrix_world': [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}
    actual = {'unit_scale_m': 1.0, 'objects': [dict(object_data, faces=[[0, 1, 2]])]}
    expected = {'scale_length': 1.0, 'objects': [dict(object_data, triangles=[[0, 1, 2]])]}
    module.snapshot_binding(actual, expected)
    changed = copy.deepcopy(expected)
    changed['scale_length'] = .001
    try:
        module.snapshot_binding(actual, changed)
    except AssertionError:
        pass
    else:
        raise AssertionError('changed unit accepted')
    provider_positive = ('HTTP 429 Too Many Requests', 'HTTP/2 503 unavailable',
                         'status code: 503', 'error=429', 'usage limit exceeded',
                         'rate limit reached', 'quota exhausted')
    provider_negative = ('port=50429 pid=1503', 'trace hash abc429def503123',
                         'source line 503 vertex 429', 'status 200 pid=429',
                         'HTTP 5030 is an invalid synthetic status')
    assert all(module.provider_unavailable(value) for value in provider_positive)
    assert not any(module.provider_unavailable(value) for value in provider_negative)
    return {'six_slot_zero_image_contract_passed': True, 'rejected_contract_cases': rejected,
            'snapshot_scale_length_and_triangle_alias_passed': True, 'changed_units_rejected': True,
            'provider_positive_cases': list(provider_positive), 'provider_negative_cases': list(provider_negative),
            'provider_contextual_classification_passed': True,
            'actual_subprocesses': 0}


def source_and_cli_check():
    batch = HERE.parent
    ready = json.loads((ROOT / 'verification/m3_sufficient_separation_001/installation/READY.json').read_bytes())
    release = Path(ready['release'])
    binding = json.loads((release / 'admin/RUNTIME_BINDING.json').read_bytes())
    manifest = binding['source_files']
    assert ready['commit'] == 'e836e03f4b3821f869c72ac3e50df5204f28b50f'
    assert ready['source_count'] == len(manifest) == 137
    expected_source = '2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390'
    assert ready['source_sha256'] == binding['identity']['source_sha256'] == expected_source
    canonical = json.dumps({'base_version': binding['identity']['base_version'],
        'implementation_revision': binding['identity']['implementation_revision'],
        'files': manifest}, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    assert hashlib.sha256(canonical).hexdigest() == expected_source
    for row in manifest:
        assert digest(Path(ready['install_root']) / row['path']) == row['sha256']
        assert digest(ROOT / row['path']) == row['sha256']
    module = load_driver(batch / 'runtime/consumer_transport.py', 'transport_controls')
    actor = load_driver(batch / 'runtime/actor.py', 'actor_controls')
    settings = module.settings()
    disabled = ('features.hooks', 'features.apps', 'features.memories', 'memories.use_memories',
                'features.multi_agent', 'features.multi_agent_v2', 'features.goals',
                'features.remote_plugin', 'features.plugins', 'skills.bundled.enabled',
                'skills.include_instructions', 'features.shell_tool', 'features.view_image')
    assert all(settings[key] is False for key in disabled)
    assert settings['project_doc_max_bytes'] == 0 and settings['web_search'] == 'disabled'
    assert settings['forced_login_method'] == 'chatgpt'
    assert settings['model'] == 'gpt-6.1-sol' and settings['model_reasoning_effort'] == 'medium'
    assert module.safe_environment({'CODEX_THREAD_ID': 'x', 'PYTHONPATH': 'x',
                                    'OPENAI_API_KEY': 'synthetic-secret', 'KEEP': 'ok'}) == {'KEEP': 'ok'}
    assert module.TOOLS_BY_GROUP == {'N': frozenset({'execute_blender_code'}),
        'P': frozenset({'execute_blender_code', 'human_eye_scene_observe'})}
    assert actor.TOOLS_BY_GROUP == {'N': frozenset(), 'P': frozenset({'human_eye_scene_observe'})}
    cli = Path(module.EXE)
    assert digest(cli) == '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
    return {'source_count': 137, 'source_sha256': expected_source,
            'installed_and_worktree_sources_match': True, 'CLI_sha256': digest(cli),
            'requested_model_effort_and_login': 'gpt-6.1-sol/medium, chatgpt',
            'resolved_backend_model_effort': None,
            'hooks_memories_rules_tool_settings_verified': True,
            'NP_tool_and_preapproval_names_aligned': True, 'actual_subprocesses': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'asset': asset_check(), 'new': cleanup_checks(args.driver.resolve(), output / 'new'),
              'contracts': contract_checks(args.driver.resolve()),
              'source_and_cli': source_and_cli_check(),
              'review_source_sha256': digest(Path(__file__))}
    old = ROOT / 'verification/m4_selected_geometry_consumption_001/runtime/driver.py'
    result['original'] = cleanup_checks(old, output / 'original')
    result['passed'] = result['new']['all_owned_processes_reaped'] and not result['original']['all_owned_processes_reaped']
    save(output / 'RESULTS.json', result)
    print(json.dumps({'passed': result['passed'], 'actual_subprocesses': 0, 'asset_source_bound': True}))
