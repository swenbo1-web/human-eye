"""Preflight the actual P2 consumer path and sealed historical CLI events."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
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


OLD_RUN = Path('D:/he_perf050_readonly_product_pilot_001')
OLD_CONSUMER = driver.PILOT / 'consumer'
OLD_INDEX = driver.PILOT / 'RUNTIME_INDEX.json'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def check_actual_consumer(folder, turn, proof, metadata, normalize, prior_configuration):
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
                     'print("P2 offline early exit", file=sys.stderr)\nraise SystemExit(7)\n',
                     encoding='utf8', newline='\n')
    offline = {'command': [proof['Python_path'], '-I', '-B', str(probe)], 'script_sha256': costs.digest(probe)}

    def local_turn(**entry):
        require(entry['expected_thread_id'] is None and entry['turn_index'] == 1
                and entry['plan'] == {'model_consumer_enabled': True}
                and not entry['work'].exists() and not entry['folder'].exists()
                and entry['prompt'] == driver.PROMPT.read_bytes(), 'P2_turn_not_fresh_or_original_prompt_changed')
        return turn(**entry, local_cli=offline)

    with patch.object(driver, 'consumer_adapter', return_value=(local_turn, proof, metadata)):
        result = driver.consume_slot('P2', folder, endpoint, owner, deadline, deadline + 150_000_000_000)
    record = costs.read(Path(result['consumer_record']))
    command = normalize(record['frozen_cli_argv'], folder, driver.THIN)
    old_command = normalize(prior_configuration['requested_cli_overrides_and_argv'], OLD_RUN / 'slots/P1',
                            OLD_CONSUMER / 'thin_stdio.py')
    require(command == old_command, 'P2_requested_cli_argv_differs_from_the_actual_P1_consumer')
    require(record['execution_kind'] == 'synthetic_local_process' and record['status'] == 'failed'
            and record['process_reaped'] and record['readers_stopped'] and record['exit_code'] == 7
            and not record['valid_completion'] and record['thread_id'] is None
            and record['initial_image']['count'] == 0 and not record['tool_calls']
            and not record['archive']['business_binding_errors']
            and marker.read_bytes() == driver.PROMPT.read_bytes(),
            'actual_P2_driver_did_not_preserve_prompt_or_early_exit')
    return {'normalized_argv_exactly_matches_P1': True,
            'normalized_argv_sha256': sha256(json.dumps(command).encode()).hexdigest(),
            'stdin_bytes': marker.stat().st_size, 'stdin_sha256': costs.digest(marker),
            'expected_thread_id': record['expected_thread_id'], 'actual_local_exit_code': record['exit_code'],
            'original_failure_and_closure_recorded': True}


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'registered_isolated_interpreter_required')
    paths = sys.path[:]
    try:
        dense = driver.NS.parent / 'm4_dense_panel_sweep_formal_001'
        with patch.object(driver, 'DENSE', dense, create=True):
            retained = run_path(str(OLD_CONSUMER / 'preflight.py'))
    finally:
        sys.path[:] = paths
    turn, proof, metadata = driver.consumer_adapter()
    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        if path not in pins:
            pins[path] = costs.file_receipt(path)
        row = pins[path]
        require((digest is None or row['sha256'] == digest) and (size is None or row['bytes'] == size),
                'original_consumer_identity_changed/' + str(path))
        return row

    for path in (Path(__file__), HERE / 'costs.py', OLD_CONSUMER / 'preflight.py', OLD_CONSUMER / 'costs.py',
                 OLD_CONSUMER / 'COSTS.json', OLD_INDEX):
        pin(path)
    prompt = pin(driver.PROMPT, driver.PROMPT_SHA, 387)
    for row in proof['execution_sources']:
        pin(row['path'], row['sha256'], row['bytes'])
    pin(proof['CLI_path'], proof['CLI_sha256'])
    pin(proof['Python_path'], proof['Python_sha256'])
    source = costs.read(OLD_INDEX)
    old_archive = source['archive']
    archive_path = Path(pin(old_archive['path'], old_archive['sha256'], old_archive['bytes'])['path'])
    archive_members = {row['path']: row for row in source['files']}
    cli = proof['CLI_path']
    version = subprocess.check_output([cli, '--version'], timeout=15).decode().strip()
    login = subprocess.run([cli, 'login', 'status'], capture_output=True, timeout=15, check=True)
    login_text = (login.stdout + login.stderr).decode('utf8').strip()
    require(version == 'codex-cli 0.152.1' and login_text == 'Logged in using ChatGPT',
            'original_CLI_version_or_readonly_ChatGPT_login_changed')
    env = turn.__globals__['safe_environment']({'OPENAI_API_KEY': 'test', 'GOOGLE_API_KEY': 'test',
                                               'A_ACCESS_TOKEN': 'test', 'CODEX_THREAD_ID': 'inherited',
                                               'Keep': 'sample'})
    require(env == {'Keep': 'sample'}, 'alternative_API_credentials_or_thread_context_not_filtered')
    previous_configuration = OLD_RUN / 'slots/P1/consumer/ACTUAL_CONFIGURATION.json'
    pin(previous_configuration)
    historical = {}
    with TemporaryDirectory(prefix='perf050_p2_consumer_preflight_') as temporary:
        work = Path(temporary).resolve()
        actual = check_actual_consumer(work / 'P2', turn, proof, metadata, retained['normalize'],
                                       costs.read(previous_configuration))
        for label in ('N1', 'P1'):
            folder = work / label
            folder.mkdir()
            historical[label] = retained['replay_archive'](OLD_RUN / 'slots' / label, folder, turn, pin)
    require(actual['stdin_sha256'] == prompt['sha256'] and actual['stdin_bytes'] == prompt['bytes']
            and set(proof['actual_tools_by_group']['P']) - set(proof['actual_tools_by_group']['N'])
                == {'human_eye_scene_observe'},
            'original_prompt_or_existing_tool_directory_changed')
    with ZipFile(old_archive['path']) as sealed:
        for path, row in pins.items():
            if path != archive_path and path.is_relative_to(OLD_RUN):
                member = path.relative_to(OLD_RUN).as_posix()
                original = archive_members[member]
                require(row['bytes'] == original['bytes'] and row['sha256'] == original['sha256']
                        and sha256(sealed.read(member)).hexdigest() == row['sha256'],
                        'historical_raw_tool_or_PNG_not_bound_to_sealed_member/' + member)

    output = HERE / 'PREFLIGHT.json'
    result = {'passed': True, 'provider_model_launches': 0, 'Blender_launches': 0,
              'CLI': version, 'login_status': login_text, 'original_prompt': prompt,
              'fixed_requested_model': proof['model'], 'fixed_reasoning_effort': proof['reasoning_effort'],
              'fixed_service_tier': proof['service_tier'], 'actual_consumer_early_exit_test': actual,
              'original_CLI_cost_and_result_replays': historical, 'tool_names': proof['actual_tools_by_group'],
              'source_pins': list(pins.values())}
    with output.open('x', encoding='utf8', newline='\n') as target:
        json.dump(result, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write('\n')
    print('P2 consumer preflight passed', costs.digest(output), len(pins), flush=True)


if __name__ == '__main__':
    main()
