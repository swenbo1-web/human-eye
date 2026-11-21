"""Feed original prompt bytes to the actual consumer using a terminating local CLI."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import costs
import driver


HISTORY = Path('D:/he_perf050_readonly_product_transfer_001')
REFERENCE = costs.TRANSFER / 'consumer'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'isolated_interpreter_required')
    turn, proof, metadata = driver.consumer_adapter()
    issue_files = {Path(__file__), HERE / 'driver.py', HERE / 'thin_stdio.py', HERE / 'costs.py', driver.PROMPT}
    pins = {}

    def pin(path, digest=None, size=None):
        path = Path(path).resolve()
        row = pins.get(path) or costs.file_receipt(path)
        require((digest is None or row['sha256'] == digest) and (size is None or row['bytes'] == size),
                'consumer_entry_source_changed/' + str(path))
        pins[path] = row
        return row

    for path in issue_files:
        pin(path)
    for row in proof['execution_sources']:
        pin(row['path'], row['sha256'], row['bytes'])
    pin(proof['CLI_path'], proof['CLI_sha256'])
    pin(proof['Python_path'], proof['Python_sha256'])
    old_config_path = HISTORY / 'slots/P1/consumer/ACTUAL_CONFIGURATION.json'
    old_index = costs.TRANSFER / 'RUNTIME_INDEX.json'
    original = costs.read(old_index)
    config_row, = [row for row in original['files'] if row['path'] == 'slots/P1/consumer/ACTUAL_CONFIGURATION.json']
    pin(old_index)
    pin(old_config_path, config_row['sha256'], config_row['bytes'])
    pin(driver.PILOT / 'consumer/preflight.py')
    with patch.object(driver, 'DENSE', driver.NS.parent / 'm4_dense_panel_sweep_formal_001', create=True):
        normalize = run_path(str(driver.PILOT / 'consumer/preflight.py'))['normalize']
    require(subprocess.check_output([proof['CLI_path'], '--version'], timeout=15).decode().strip() == 'codex-cli 0.152.1',
            'registered_cli_version_changed')
    login = subprocess.run([proof['CLI_path'], 'login', 'status'], capture_output=True, timeout=15, check=True)
    require((login.stdout + login.stderr).decode().strip() == 'Logged in using ChatGPT', 'existing_chatgpt_login_required')
    prompt = driver.PROMPT.read_bytes()
    with TemporaryDirectory(prefix='perf050_p2_offline_consumer_') as temp:
        folder = Path(temp).resolve()
        endpoint = folder / 'ENDPOINT.json'
        deadline = time.perf_counter_ns() + 45_000_000_000
        endpoint.write_text(json.dumps({'chain_deadline_ns': deadline, 'host': '127.0.0.1'}), encoding='utf8')
        owner = folder / 'owner'
        owner.mkdir()
        (owner / 'TOOLS.json').write_text('{"tools":[]}', encoding='utf8')
        probe = folder / 'stdin_probe.py'
        written = folder / 'STDIN.bin'
        probe.write_text('from pathlib import Path\nimport sys\nPath(' + repr(str(written))
                         + ').write_bytes(sys.stdin.buffer.read())\n'
                         'raise SystemExit(7)\n', encoding='utf8', newline='\n')
        offline = {'command': [proof['Python_path'], '-I', '-B', str(probe)],
                   'script_sha256': costs.digest(probe)}

        def local_turn(**entry):
            require(entry['episode_id'] == 'PERF050-TARGET-OBSERVATION-FIRST-IMAGE-P2'
                    and entry['expected_thread_id'] is None and entry['turn_index'] == 1
                    and entry['plan'] == {'model_consumer_enabled': True}
                    and entry['prompt'] == prompt and not entry['folder'].exists() and not entry['work'].exists(),
                    'formal_driver_not_a_fresh_turn_with_the_frozen_prompt')
            return turn(**entry, local_cli=offline)

        with patch.object(driver, 'consumer_adapter', return_value=(local_turn, proof, metadata)):
            envelope = driver.consume_slot('P2', folder, endpoint, owner, deadline, deadline + 150_000_000_000)
        record = costs.read(Path(envelope['consumer_record']))
        old_command = costs.read(old_config_path)['requested_cli_overrides_and_argv']
        current = normalize(record['frozen_cli_argv'], folder, driver.THIN)
        old = normalize(old_command, old_config_path.parents[1], REFERENCE / 'thin_stdio.py')
        require(current == old, 'P2_argv_differs_from_actual_P1')
        require(record['execution_kind'] == 'synthetic_local_process' and record['status'] == 'failed'
                and record['process_reaped'] and record['readers_stopped'] and record['exit_code'] == 7
                and not record['valid_completion'] and record['thread_id'] is None
                and record['initial_image']['count'] == 0 and not record['tool_calls']
                and not record['archive']['business_binding_errors']
                and written.read_bytes() == prompt and len(prompt) == 350
                and sha256(prompt).hexdigest() == driver.PROMPT_SHA, 'actual_P2_prompt_or_early_closure_changed')
    result = {'passed': True, 'actual_argv_matches_P1': True,
              'argv_normalized_sha256': sha256(json.dumps(current).encode()).hexdigest(),
              'stdin_bytes': len(prompt), 'stdin_sha256': driver.PROMPT_SHA,
              'actual_local_exit_code': record['exit_code'], 'actual_local_reaped': True,
              'CLI': proof['CLI_version'], 'observed_existing_login': 'ChatGPT',
              'provider_launches': 0, 'Blender_launches': 0, 'source_pins': list(pins.values())}
    with (HERE / 'PREFLIGHT.json').open('x', encoding='utf8', newline='\n') as sink:
        json.dump(result, sink, ensure_ascii=False, indent=2, allow_nan=False)
        sink.write('\n')


if __name__ == '__main__':
    main()
