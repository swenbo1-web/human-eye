"""Exercise the exact formal launch selection and P entry without a live start."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
PREVIOUS = NS.parent / 'm4_dense_sweep_integrated_native_pilot_001'
OLD = Path('D:/he_m4_dense_sweep_integrated_native_pilot_001')
COMMIT = '8a7ff397efd99fb5474c3018a36444db36f13395'
sys.path[:0] = [str(HERE), str(NS)]
from common import ASSET, EXTERNAL, ORDER, PRODUCT_BINDING, ROOT, SEAL, read, save, sha


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def committed(path):
    content = subprocess.check_output(['git', 'show', COMMIT + ':' + path.relative_to(ROOT).as_posix()], cwd=ROOT)
    require(content == path.read_bytes(), 'retained_pilot_bytes_changed/' + path.name)
    return pin(path)


def actual_wire():
    index_path = PREVIOUS / 'RAW_INDEX.json'
    pins = [committed(index_path), committed(PREVIOUS / 'harness/RUNTIME_PREFLIGHT.json')]
    index = read(index_path)
    archive = PREVIOUS / index['archive']['name']
    pins.append(pin(archive))
    require(pins[-1]['sha256'] == index['archive']['sha256'] and pins[-1]['bytes'] == index['archive']['bytes'],
            'original_archive_changed')
    keys = ('QN/client/TOOLS.json', 'QP/client/TOOLS.json', 'QP/mcp/rpc_01/TX.bin', 'QP/mcp/rpc_01/RX.bin',
            'QP/mcp/rpc_03/TX.bin', 'QP/mcp/rpc_03/RX.bin', 'QP/mcp/HELD_CLOSE.json',
            'QP/mcp_io/EOF.json', 'QP/mcp_io/WORKER_EXIT.json')
    records = {}
    with ZipFile(archive) as bundle:
        for key in keys:
            name = 'runtime/slots/' + key
            original = OLD / 'slots' / key
            data = bundle.read(name)
            require(index['members'][name] == {'bytes': len(data), 'sha256': sha256(data).hexdigest()}
                    and data == original.read_bytes(), 'original_wire_bytes_changed/' + key)
            pins.append(pin(original))
            records[key] = json.loads(data)
    held, eof, exited = (records[key] for key in keys[-3:])
    require(held['confirmed'] and held['stdout_eof_seen'] and held['production_eof_and_exit_verified']
            and held['process_handle_closed'] and eof['closed'] and eof['input_eof_observed']
            and exited['production_return_code'] == 0 and exited['installed_source_verified'],
            'original_owned_stdio_close_unproven')
    sets = [{item['name']: item for item in records[key]['result']['tools']} for key in keys[:2]]
    plugin = sets[1].pop('human_eye_scene_observe')
    require(sets[0] == sets[1] and len(sets[0]) == 5 and plugin['name'] == 'human_eye_scene_observe',
            'original_common_tool_schemas_differ')
    return records, pins


def prepared_dispatch():
    entry = HERE / 'run_slot.py'
    slots = {}
    for label in ORDER:
        out = subprocess.check_output([sys.executable, '-IB', '-X', 'utf8', str(entry), label, '--dispatch-smoke'],
                                      cwd=ROOT, timeout=40)
        slots[label] = json.loads(out)
    require(tuple(slots) == ('N1', 'P1') and set(slots['P1']['tools']) - set(slots['N1']['tools'])
            == {'human_eye_scene_observe'} and len(slots['N1']['tools']) == 5
            and all(row['run_root'] == str(EXTERNAL.resolve()) and row['asset'] == str(ASSET.resolve())
                    and row['fresh_process_prepared_only'] for row in slots.values())
            and slots['N1']['actual_product_binding'] is None and slots['N1']['endpoint_flag'] is None
            and slots['P1']['actual_product_binding'] == str(PRODUCT_BINDING.resolve())
            and slots['P1']['endpoint_flag'] == '--region-task-evidence',
            'formal_slot_dispatch_does_not_match_retained_NP_contract')
    return slots


def product_entry(wire, binding):
    import mcp_entry
    from runtime import Runtime

    writes, call_methods, command = {}, [], []
    slot = EXTERNAL / 'slots/P1'
    runtime = SimpleNamespace(folder=slot, label='P1', phase='formal', task_deadline=1,
                              budget=SimpleNamespace(root=EXTERNAL / 'budget'),
                              native=SimpleNamespace(host='127.0.0.1', port=32123),
                              _retain=lambda process, name: name)

    def retain(path, data):
        writes[Path(path)] = data

    class StdioProbe:
        def __init__(self, argv, cwd, output, deadline, *, worker_evidence):
            require(cwd == slot and output == slot / 'mcp' and worker_evidence == slot / 'mcp_io',
                    'current_held_worker_paths_changed')
            self.process = object()
            command.extend(argv)

        def call(self, request):
            method = request['method']
            call_methods.append(method)
            if method == 'notifications/initialized':
                return None
            index = {'initialize': '01', 'tools/list': '03'}[method]
            require(request == wire[f'QP/mcp/rpc_{index}/TX.bin'], 'original_startup_request_changed')
            return wire[f'QP/mcp/rpc_{index}/RX.bin']

    startup = Runtime._start_public_mcp
    with patch.dict(startup.__globals__, {'ProductionStdioClient': StdioProbe, 'save': retain}):
        startup(runtime, PRODUCT_BINDING, binding)
    require(command[:5] == [sys.executable, '-I', '-B', '-X', 'utf8']
            and Path(command[5]).resolve() == (HERE / 'mcp_entry.py').resolve()
            and call_methods == ['initialize', 'notifications/initialized', 'tools/list']
            and runtime.mcp_handle == 'MCP_RUNTIME_PROOF.json',
            'actual_product_launch_path_or_original_handshake_changed')
    admitted = []

    def refuse_or_reach_worker(argv, state, expected):
        config = slot / 'PRODUCT_CONFIG.json'
        contents = {**writes[config], 'state_file': str(state)}
        with patch.object(sys, 'argv', argv), patch.object(mcp_entry, 'worker', lambda args: admitted.append(args) or 0), \
                patch.object(mcp_entry, 'read', lambda path: contents):
            try:
                code = mcp_entry.main()
            except ValueError as error:
                require(expected is not None and str(error) == expected, 'unexpected_actual_entry_rejection')
            else:
                require(expected is None and code == 0, 'invalid_entry_reached_worker')

    args = command[5:]
    state = slot / 'product_state.json'
    refuse_or_reach_worker(args, state, None)
    refuse_or_reach_worker(args[:-1], state, 'registered_production_arm_paths_and_flag_required')
    refuse_or_reach_worker([('qualification' if arg == 'formal' else arg) for arg in args], state,
                           'registered_production_arm_paths_and_flag_required')
    refuse_or_reach_worker(args, OLD / 'slots/QP/product_state.json', 'current_absolute_owned_state_required')
    require(len(admitted) == 1 and admitted[0].phase == 'formal' and admitted[0].label == 'P1',
            'one_actual_formal_entry_validation_required')
    return {'actual_entry_source': str(Path(mcp_entry.__file__).resolve()), 'argv': command, 'passed': True,
            'original_handshake_requests': call_methods, 'negative_controls': 3,
            'scope': 'Actual launcher and entry routing with original raw handshake and held EOF evidence. '
                     'The process constructor and product worker are intercepted before starting.'}


def run():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_interpreter_I_B_required')
    binding = read(PRODUCT_BINDING)
    sys.path[:0] = [binding['dependency_root'], read(SEAL / 'SHARED_DEPENDENCY.json')['dependency_root']]
    from budget import LIMITS
    from consumer.driver import consumer_adapter

    require(LIMITS == {'Blender_start_attempts':2,'all_rasters':24,'consumer_tasks':2,
                       'tools_per_slot':12,'rasters_by_slot':{'N1':12,'P1':12}}, 'recovery_limits_changed')
    wire, pins = actual_wire()
    dispatch = prepared_dispatch()
    entry = product_entry(wire, binding)
    _, proof, _ = consumer_adapter()
    cli, python = (Path(proof[key]) for key in ('CLI_path','Python_path'))
    require(sha(cli) == proof['CLI_sha256'] and sha(python) == proof['Python_sha256'], 'original_cli_pin_changed')
    version = subprocess.check_output([str(cli), '--version'], timeout=20).decode().strip()
    auth = subprocess.run([str(cli), 'login', 'status'], capture_output=True, timeout=20, check=True)
    authenticated = (auth.stdout + auth.stderr).decode().strip() == 'Logged in using ChatGPT'
    require(version == 'codex-cli 0.152.1' and authenticated, 'registered_cli_or_original_login_changed')
    consumer = {'passed': True, 'actual_version': version, 'ambient_ChatGPT_login_confirmed': authenticated,
                'actual_model_requests': 0, 'requested': [proof[k] for k in ('model','reasoning_effort','service_tier')]}
    for folder in ('harness', 'consumer', 'inputs'):
        for path in (PREVIOUS / folder).glob('*'):
            if path.is_file():
                pins.append(committed(path))
    pins.extend(proof['execution_sources'])
    pins.extend(pin(path) for path in (cli, python, NS / 'inputs/PROMPT.txt'))
    source_pins = {item['path']: item for item in pins}
    require(not (EXTERNAL / 'slots').exists(), 'offline_preflight_created_live_slots')
    save(HERE / 'RUNTIME_PREFLIGHT.json', {
        'passed': True, 'dispatch': dispatch, 'installed_entry_replay': entry, 'consumer': consumer,
        'formal_limits': LIMITS, 'actual_Blender_starts': 0, 'actual_model_starts': 0, 'actual_rasters': 0,
        'actual_qualification_slots': 0, 'source_pins': [source_pins[k] for k in sorted(source_pins)],
    })
    print('Formal-only dispatch, retained stdio, actual P entry checks and CLI configuration passed.')


if __name__ == '__main__':
    run()
