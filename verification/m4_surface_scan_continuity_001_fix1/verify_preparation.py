"""Read-only root reconciliation of the real owner regression and fake CLI chain."""

import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_surface_scan_continuity_001'


def read(path):
    return json.loads(path.read_bytes())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    checks = []

    def check(value, label):
        checks.append(label)
        assert value, label

    check((HERE / 'runtime/actor.py').read_bytes() == (OLD / 'runtime/actor.py').read_bytes(), 'unchanged_actor')
    definitions = ast.parse((HERE / 'qualification/verify_continuity.py').read_text(encoding='utf8')).body
    for name in ('verify_c_turn', 'bind_source_snapshot'):
        check(sum(isinstance(node, ast.FunctionDef) and node.name == name for node in definitions) == 1, 'single_active_' + name)
    original = read(OLD / 'DELIVERY_MANIFEST.json')
    for row in original['files']:
        raw = (OLD / row['path']).read_bytes()
        check(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'old_original_' + row['path'])
    check(read(OLD / 'episodes/N/FINAL_TIMING.json')['accepted_success'] is True, 'old_N_reused')
    check(read(OLD / 'episodes/C/RESULTS.json')['execution_counts'] == {'planned': 3, 'attempted': 1, 'completed': 0, 'failed': 1, 'not_run': 2}, 'old_C_failure_retained')
    runner = load('_fix1_root_runner', HERE / 'engineering/run_candidate.py')
    qualification = load('_fix1_root_qualification', HERE / 'qualification/verify_continuity.py')
    folder = OLD / 'episodes/C'
    row = copy.deepcopy(read(folder / 'TURN_BASE.json'))
    facts = runner.verify_business(row, folder, read(folder / 'owner/INITIAL.json'), qualification)
    check(facts['matches'] == 71 and facts['new_kernel_calls'] == 112 and facts['actual_host_capture_count'] == 1, 'actual_runner_owner_regression')
    check(facts['source_report']['rich_source_metadata_verified'] is False, 'missing_rich_remains_unverified')

    normal = []
    for path in sorted((HERE / 'consumer/offline/attempt_03').rglob('EPISODE_RESULT.json')):
        value = read(path)
        if not value['qualified_execution']:
            continue
        normal.append(path.parent)
        check(value['counts'] == {'completed': 3, 'failed': 0, 'not_run': 0}, str(path) + ' three_completed')
        check(value['mode'] == 'local_synthetic_processes' and value['new_provider_calls'] == 0, str(path) + ' synthetic')
        check(value['owner_finish']['confirmed'] is True, str(path) + ' finish')
        threads = [turn['consumer']['thread_id'] for turn in value['turns']]
        work = [turn['consumer']['shared_work'] for turn in value['turns']]
        endpoints = [turn['consumer']['endpoint'] for turn in value['turns']]
        check(len(set(threads)) == len(set(work)) == len(set(endpoints)) == 1, str(path) + ' shared_context')
        for index, turn in enumerate(value['turns']):
            record = turn['consumer']
            check(record['execution_kind'] == 'synthetic_local_process' and record['valid_completion'], str(path) + ' actual_loop_' + str(index))
            check(record['process_reaped'] and record['readers_stopped'], str(path) + ' reaped_' + str(index))
            check(record['bridge_cleanup']['confirmed'] is True, str(path) + ' thin_exit_' + str(index))
            check(record['usage_aggregation'] is None, str(path) + ' raw_usage_' + str(index))
            check('--ephemeral' not in record['frozen_cli_argv'], str(path) + ' persisted_' + str(index))
            if index:
                check('resume' in record['frozen_cli_argv'] and threads[0] in record['frozen_cli_argv'], str(path) + ' explicit_resume_' + str(index))
            check(record['deadline_ns'] <= record['episode_deadline_ns'] == value['episode_deadline_ns'], str(path) + ' absolute_deadline_' + str(index))
        binding = read(path.parent / 'quality/PRIVATE_BINDING.json')
        for filename, field in (('CONSUMER_ORIGINALS.zip', 'consumer_originals'), ('OWNER_ORIGINALS.zip', 'owner_originals')):
            with zipfile.ZipFile(path.parent / 'quality' / filename) as archive:
                check(set(archive.namelist()) == set(binding[field]), str(path) + ' zip_members_' + filename)
                for member, expected in binding[field].items():
                    check(hashlib.sha256(archive.read(member)).hexdigest() == expected, str(path) + ' zip_bytes_' + member)
        check(len(binding['turn_bindings']) == 3, str(path) + ' three_turn_binding')
    check(len(normal) == 2, 'N_and_C_complete_fake_loops')
    for path in (HERE / 'consumer/offline/attempt_04').rglob('EPISODE_RESULT.json'):
        value = read(path)
        check(value['qualified_execution'] is False and value['archive_status'] == 'failed', str(path) + ' archive_failure_terminal')
        check(value['owner_finish']['confirmed'] is True and len(value['turns']) == 3, str(path) + ' archive_failure_keeps_turns_and_cleanup')
        check(read(path.parent / 'FINAL_TIMING.json')['qualified_execution'] is False, str(path) + ' final_timing_failed')
    result = {'checks': len(checks), 'labels': checks, 'passed': True, 'new_Blender_model_API_calls': 0,
              'scope': 'Actual saved owner replay through engineering interface and read-only full fake-loop archives',
              'actual_C1': facts, 'normal_fake_episodes': [str(path) for path in normal]}
    (HERE / 'ROOT_PREPARATION_CHECK.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'checks': len(checks), 'passed': True, 'normal_fake_episodes': len(normal), 'new_Blender_model_API_calls': 0}))


if __name__ == '__main__':
    main()
