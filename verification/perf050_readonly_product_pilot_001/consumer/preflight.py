"""Exercise the retained fresh consumer and archived CLI/wire binding offline."""

from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import costs
import driver


OLD = Path('D:/he_m4_dense_panel_sweep_formal_001/slots')
OLD_INDEX = driver.DENSE / 'RUNTIME_INDEX.json'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def normalize(argv, root, thin):
    for path, token in ((root, '<slot>'), (thin, '<thin>')):
        actual = str(path.resolve())
        argv = [item.replace(actual.replace('\\', '\\\\'), token).replace(actual, token) for item in argv]
    return argv


def replay_archive(slot, workspace, turn, pin):
    folder = slot / 'consumer'
    replay = workspace / 'historical'
    replay.mkdir()
    for directory in ('attachments',):
        shutil.copytree(folder / directory, replay / directory)
    for name in ('events.jsonl', 'stdout.raw.bin'):
        shutil.copyfile(folder / name, replay / name)
    record = costs.read(folder / 'CONSUMER.json')
    saved = costs.read(folder / 'BUSINESS_SOURCE_BINDING.json')
    rebuilt = turn.__globals__['archive_turn'](replay, {'audit_dir': str(slot / 'owner'), 'group': slot.name[0]},
                                              1, record['tool_calls'])
    require(not rebuilt['business_binding_errors'], 'original_CLI_tool_archive_replay_failed/' + slot.name)
    fields = ('attempt', 'tool', 'TX_sha256', 'RX_sha256', 'CLI_received_ns', 'CLI_text_UTF8_bytes', 'CLI_images')
    compare = lambda rows: [[row.get(key) for key in fields] for row in rows]
    require(compare(rebuilt['result_contracts']) == compare(saved['result_contracts']) and
            rebuilt['first_CLI_nonempty_successful_evidence_ns'] == saved['first_CLI_nonempty_successful_evidence_ns'],
            'original_CLI_result_contract_or_evidence_timestamp_changed/' + slot.name)
    for item in rebuilt['sources']:
        pin(item['original'], item['sha256'], item['bytes'])
    for path in (folder / 'CONSUMER.json', folder / 'BUSINESS_SOURCE_BINDING.json', folder / 'events.jsonl',
                 folder / 'stdout.raw.bin', folder / 'PUBLIC_FINAL.txt', slot / 'owner/TOOLS.json',
                 slot / 'SLOT_RESULT.json', slot / 'SLOT_PUBLICATION.json'):
        pin(path)
    for path in (folder / 'attachments').rglob('*'):
        if path.is_file():
            pin(path)
    row = costs.summarize(slot)
    require(row['cost_evidence_verified'] and row['status'] == 'completed' and row['input_plus_output_tokens'] > 0
            and len(row['actual_requests']) == len(rebuilt['result_contracts']) > 0
            and row['clock_ms']['prompt_to_first_call'] > 0 and row['clock_ms']['last_tool_to_final'] > 0,
            'original_runtime_cost_replay_failed/' + slot.name)
    require(any(result['CLI_images'] > 0 for result in rebuilt['result_contracts']),
            'original_PNG_delivery_evidence_missing/' + slot.name)
    return {'raw_tool_attempts': len(row['actual_requests']), 'CLI_tokens': row['input_plus_output_tokens'],
            'matching_original_tool_results': len(rebuilt['result_contracts']), 'clock_ms': row['clock_ms']}


def test_consumer(label, root, turn, proof, metadata, pin):
    group = label[0]
    folder = root / label
    folder.mkdir()
    endpoint = folder / 'ENDPOINT.json'
    deadline = time.perf_counter_ns() + 45_000_000_000
    endpoint.write_text(json.dumps({'chain_deadline_ns': deadline, 'host': '127.0.0.1'}), encoding='utf8')
    owner = folder / 'owner'
    owner.mkdir()
    (owner / 'TOOLS.json').write_text('{"tools":[]}', encoding='utf8')
    marker = folder / 'STDIN.bin'
    probe = folder / 'stdin_probe.py'
    probe.write_text('from pathlib import Path\nimport sys\nPath(' + repr(str(marker)) +
                     ').write_bytes(sys.stdin.buffer.read())\n' +
                     'print("perf050 offline preflight early exit", file=sys.stderr)\nraise SystemExit(7)\n',
                     encoding='utf8', newline='\n')
    python = proof['Python_path']
    offline_cli = {'command': [python, '-I', '-B', str(probe)], 'script_sha256': costs.digest(probe)}

    def offline_turn(**entry):
        require(entry['expected_thread_id'] is None and entry['turn_index'] == 1
                and entry['plan'] == {'model_consumer_enabled': True}
                and not entry['work'].exists() and not entry['folder'].exists(),
                'pilot_did_not_request_fresh_isolated_turn/' + label)
        require(entry['prompt'] == driver.PROMPT.read_bytes(), 'actual_prompt_argument_changed/' + label)
        return turn(**entry, local_cli=offline_cli)

    with patch.object(driver, 'consumer_adapter', return_value=(offline_turn, proof, metadata)):
        envelope = driver.consume_slot(label, folder, endpoint, owner, deadline, deadline + 150_000_000_000)
    current = costs.read(Path(envelope['consumer_record']))
    original_config = OLD / label / 'consumer/ACTUAL_CONFIGURATION.json'
    pin(original_config)
    prior = costs.read(original_config)
    current_argv = normalize(current['frozen_cli_argv'], folder, driver.THIN)
    old_argv = normalize(prior['requested_cli_overrides_and_argv'], OLD / label, driver.DENSE / 'thin_stdio.py')
    require(current_argv == old_argv, 'current_provider_settings_not_identical_to_true_historical_CLI/' + label)
    require(current['execution_kind'] == 'synthetic_local_process' and current['status'] == 'failed'
            and current['process_reaped'] and current['readers_stopped'] and current['exit_code'] == 7
            and not current['valid_completion'] and current['thread_id'] is None
            and current['initial_image']['count'] == 0 and current['tool_calls'] == []
            and not current['archive']['business_binding_errors']
            and marker.read_bytes() == driver.PROMPT.read_bytes(),
            'real_driver_did_not_preserve_prompt_bytes_or_early_exit/' + label)
    return {'argv_matches_original': True, 'argv_sha256': sha256(json.dumps(current_argv).encode()).hexdigest(),
            'stdin_bytes': marker.stat().st_size, 'stdin_sha256': costs.digest(marker),
            'expected_thread_id': current['expected_thread_id'], 'actual_local_process_exit': current['exit_code'],
            'early_exit_archive_verified': True}


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'require_registered_isolated_interpreter')
    turn, proof, metadata = driver.consumer_adapter()
    spec = turn.__globals__
    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = costs.file_receipt(path)
        value = pins[path]
        require((digest is None or value['sha256'] == digest) and (size is None or value['bytes'] == size),
                'original_source_record_changed/' + str(path))

    for path in (Path(__file__), driver.PROMPT, HERE / 'costs.py', OLD_INDEX):
        pin(path)
    for row in proof['execution_sources']:
        pin(row['path'], row['sha256'], row['bytes'])
    pin(proof['CLI_path'], proof['CLI_sha256'])
    pin(proof['Python_path'], proof['Python_sha256'])
    historical = costs.read(OLD_INDEX)
    archive = historical['archive']
    pin(archive['path'], archive['sha256'], archive['bytes'])
    runtime_files = {row['path']: row for row in historical['files']}

    env = spec['safe_environment']({'OPENAI_API_KEY': 'test', 'GOOGLE_API_KEY': 'test', 'A_ACCESS_TOKEN': 'test',
                                     'CODEX_THREAD_ID': 'inherited', 'Keep': 'sample'})
    require(env == {'Keep': 'sample'}, 'alternative_API_credentials_or_thread_context_not_filtered')
    cli = proof['CLI_path']
    version = subprocess.check_output([cli, '--version'], timeout=15).decode().strip()
    login = subprocess.run([cli, 'login', 'status'], capture_output=True, timeout=15, check=True)
    login_text = (login.stdout + login.stderr).decode('utf8').strip()
    require(version == 'codex-cli ' + proof['CLI_version'] and login_text == 'Logged in using ChatGPT',
            'fixed_CLI_version_or_readonly_ChatGPT_login_status_changed')
    tries, originals = {}, {}
    with TemporaryDirectory(prefix='perf050_consumer_preflight_') as temporary:
        work = Path(temporary).resolve()
        for label in driver.LABELS:
            tries[label] = test_consumer(label, work, turn, proof, metadata, pin)
            originals[label] = replay_archive(OLD / label, work / label, turn, pin)
    require(tries['N1']['stdin_sha256'] == tries['P1']['stdin_sha256']
            and set(proof['actual_tools_by_group']['P']) - set(proof['actual_tools_by_group']['N'])
                == {'human_eye_scene_observe'}, 'paired_prompt_or_common_tools_changed')
    with ZipFile(archive['path']) as sealed:
        for path, row in pins.items():
            if path.is_relative_to(OLD):
                name = path.relative_to(OLD.parent).as_posix()
                member = runtime_files[name]
                require(row['bytes'] == member['bytes'] and row['sha256'] == member['sha256']
                        and sha256(sealed.read(name)).hexdigest() == row['sha256'],
                        'true_archived_consumer_raw_bytes_not_sealed/' + name)

    output = HERE / 'PREFLIGHT.json'
    result = {'passed': True, 'fresh_local_early_exit_tests': tries, 'original_CLI_cost_and_result_replays': originals,
              'CLI': version, 'login_status': login_text, 'provider_model_launches': 0, 'Blender_launches': 0,
              'fixed_requested_model': proof['model'], 'fixed_reasoning_effort': proof['reasoning_effort'],
              'fixed_service_tier': proof['service_tier'], 'common_tools': proof['actual_tools_by_group']['N'],
              'P_only': ['human_eye_scene_observe'], 'source_pins': list(pins.values())}
    with output.open('x', encoding='utf8', newline='\n') as target:
        json.dump(result, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')
    print('Consumer preflight passed', costs.digest(output), len(pins), flush=True)


if __name__ == '__main__':
    main()
