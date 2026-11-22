"""Exercise the exact formal launch selection and P entry without a live start."""

from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
PREVIOUS = NS.parent / 'm4_dense_sweep_integrated_native_pilot_001'
OLD = Path('D:/he_m4_dense_sweep_integrated_native_pilot_001')
COMMIT = '8a7ff397efd99fb5474c3018a36444db36f13395'
FAILED_NS = NS.parent / 'm4_dense_sweep_integrated_native_pilot_recovery_001'
FAILED_ROOT = Path('D:/he_m4_dense_sweep_integrated_native_pilot_recovery_001')
FAILED_COMMIT = '62a631344922ddcea57d78b051a37d33629ad3a2'
sys.path[:0] = [str(HERE), str(NS)]
from common import EXTERNAL, ORDER, PRODUCT_BINDING, ROOT, SEAL, read, save, sha


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def committed(path, commit=COMMIT):
    content = subprocess.check_output(['git', 'show', commit + ':' + path.relative_to(ROOT).as_posix()], cwd=ROOT)
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
            'QN/TERMINAL_SOURCE.json', 'QP/product_calls/call_001/REQUEST.json',
            'QP/product_calls/call_001/RESPONSE.json',
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


def reproduce_original_failure(pins):
    archived_script = FAILED_NS/'evidence/RUNTIME_IMPORT_ISOLATION.py'
    script = FAILED_ROOT/'postanalysis/RUNTIME_IMPORT_ISOLATION.py'
    pins.extend((committed(archived_script, FAILED_COMMIT),pin(script)))
    require(script.read_bytes() == archived_script.read_bytes(),'retained_failure_replay_script_changed')
    saved = FAILED_ROOT/'slots/N1/SLOT_RESULT.json'
    result = read(saved)
    pins.extend(pin(FAILED_ROOT/path) for path in ('slots/N1/SLOT_RESULT.json','slots/N1/SLOT_PUBLICATION.json',
                                                   'preflight/SEQUENCE.jsonl','preflight/DERIVED_ADMISSION.json'))
    pins.append(committed(FAILED_NS/'FROZEN.json', FAILED_COMMIT))
    call = subprocess.run([sys.executable,'-IB','-X','utf8',str(script),'--mode','original'],
                          cwd=ROOT,capture_output=True,timeout=45,check=True)
    observed = json.loads(call.stdout.splitlines()[-1])
    require(observed['same_frozen_admission_reached']
            and observed['failure']=={key:result['errors'][0][key] for key in ('stage','type','message')}
            and observed['failure']['type']=='ImportError'
            and observed['Blender_starts']==observed['model_starts']==0
            and not (FAILED_ROOT/'slots/P1').exists(),
            'fixed_original_runtime_failure_not_reproduced')
    return {'passed':True, 'observed':observed,'stdout_sha256':sha256(call.stdout).hexdigest(),
            'stdout_bytes':len(call.stdout),'stderr_sha256':sha256(call.stderr).hexdigest(),
            'stderr_bytes':len(call.stderr),'original_N1_sha256':sha(saved)}


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


def owner_replay(root, label, wire):
    """Use the current Owner and thin I/O with sealed device data and replies."""
    from bridge import Owner, TOOL_NAMES
    from runtime import transport

    root.mkdir()
    group = label[0]
    deadline = time.perf_counter_ns() + 30_000_000_000
    terminal = wire['QN/TERMINAL_SOURCE.json']
    product_request = wire['QP/product_calls/call_001/REQUEST.json']
    product_response = wire['QP/product_calls/call_001/RESPONSE.json']
    forwarded = []

    def replay_product(arguments):
        require(group == 'P' and arguments == product_request['params']['arguments'] and not forwarded,
                'actual_archived_product_arguments_changed')
        forwarded.append(arguments)
        runtime.public_requests.append({'request': product_request, 'response': product_response})
        return product_response

    runtime = SimpleNamespace(
        folder=root, cameras={'views': []}, buffers={}, public_requests=[],
        scene_data=lambda selectors=None: terminal, public_request=replay_product,
        product_tools=wire['QP/mcp/rpc_03/RX.bin']['result']['tools'] if group == 'P' else [],
    )
    owner = Owner(runtime, {'label': label, 'group': group, 'phase': 'formal',
                            'worker_deadline_ns': deadline, 'output': str(root / 'owner')})
    endpoint = owner.start(root / 'ENDPOINT.json')
    front = None
    try:
        front = transport.StdioClient([sys.executable, '-IB', '-X', 'utf8', str(NS / 'consumer/thin_stdio.py'),
            '--endpoint', endpoint, '--audit', str(root / 'attachments')], root, root / 'stdio', deadline)
        front.call({'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize',
                    'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                               'clientInfo': {'name': 'offline-startup-contract', 'version': '1'}}})
        front.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        tools = front.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})['result']['tools']
        expected = wire[f'Q{group}/client/TOOLS.json']['result']['tools']
        require(tools == expected and {row['name'] for row in tools} == TOOL_NAMES[group],
                'actual_formal_owner_schema_changed/' + label)

        def tool(i, name, args):
            return front.call({'jsonrpc': '2.0', 'id': i, 'method': 'tools/call',
                               'params': {'name': name, 'arguments': args}})['result']

        require(tool(1, 'render_local', {'direction': 'INVALID'})['isError'],
                'owner_early_request_error_missing/' + label)
        first = tool(2, 'execute_python', {'code': "rows=scene_data()['objects']\nprint(len(rows))"})
        second = tool(3, 'execute_python', {'code': "print(int(np.sum([len(row['evaluated']['triangles']) for row in rows])), shapely.Polygon([(0,0),(1,0),(0,1)]).area)"})
        stdout = [json.loads(item['content'][0]['text'])['stdout'].strip() for item in (first, second)]
        require(stdout == ['20', '6160 0.5'] and not first['isError'] and not second['isError'],
                'formal_owner_actual_persistent_ordinary_compute_failed/' + label)
        if group == 'P':
            original = tool(4, 'human_eye_scene_observe', product_request['params']['arguments'])
            require(original == product_response['result'] and len(forwarded) == 1,
                    'actual_owner_replayed_P_product_response_changed')
    finally:
        try:
            if front is not None:
                close = front.finish()
                require(close['confirmed'] and close['exit_code'] == 0, 'actual_thin_stdio_close_failed/' + label)
        finally:
            finish = owner.close()
            require(finish['confirmed'] and not finish['errors'] and not finish['transport_errors'],
                    'actual_owner_close_failed/' + label)
    return {'passed': True, 'tools': [row['name'] for row in tools],
            'retained_inputs': 'old closed device source and P product wire',
            'current_thin_stdio_closed': True, 'current_owner_listener_closed': True,
            'persisted_ordinary_facts': stdout, 'ordinary_calls': 3, 'product_replays': len(forwarded),
            'replayed_product_reply_digest': sha256(json.dumps(product_response['result'], sort_keys=True,
                                                                ensure_ascii=False).encode()).hexdigest()
                                               if forwarded else None}


def consumer_preflight(turn, proof, metadata, pins):
    """Use the formal consumer API and a local prompt-receipt executable."""
    from consumer import driver

    previous = NS.parent / 'perf050_readonly_product_pilot_001/consumer/preflight.py'
    original_path = sys.path[:]
    try:
        replay = run_path(str(previous))
    finally:
        sys.path[:] = original_path
    replay_test = replay['test_consumer']
    with patch.dict(replay_test.__globals__, {'driver': driver}), \
            patch.object(driver, 'DENSE', NS.parent / 'm4_dense_panel_sweep_formal_001', create=True):
        with TemporaryDirectory(prefix='m4-startup-consumer-') as work:
            results = {label: replay_test(label, Path(work).resolve(), turn, proof, metadata,
                                          lambda path: pins.append(pin(path))) for label in ORDER}
    require(all(row['argv_matches_original'] and row['stdin_bytes'] == 1072 and row['early_exit_archive_verified']
                for row in results.values()), 'formal_CLI_launch_argv_prompt_or_held_close_changed')
    pins.append(pin(previous))
    return results


def run():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'pinned_interpreter_I_B_required')
    binding = read(PRODUCT_BINDING)
    sys.path[:0] = [binding['dependency_root'], read(SEAL / 'SHARED_DEPENDENCY.json')['dependency_root']]
    from budget import LIMITS
    from consumer.driver import consumer_adapter

    require(LIMITS == {'Blender_start_attempts':2,'all_rasters':24,'consumer_tasks':2,
                       'tools_per_slot':12,'rasters_by_slot':{'N1':12,'P1':12}}, 'recovery_limits_changed')
    wire, pins = actual_wire()
    entry = product_entry(wire, binding)
    with TemporaryDirectory(prefix='m4-startup-owner-') as temporary:
        owner = {label: owner_replay(Path(temporary) / label, label, wire) for label in ORDER}
    turn, proof, metadata = consumer_adapter()
    cli, python = (Path(proof[key]) for key in ('CLI_path','Python_path'))
    require(sha(cli) == proof['CLI_sha256'] and sha(python) == proof['Python_sha256'], 'original_cli_pin_changed')
    version = subprocess.check_output([str(cli), '--version'], timeout=20).decode().strip()
    auth = subprocess.run([str(cli), 'login', 'status'], capture_output=True, timeout=20, check=True)
    authenticated = (auth.stdout + auth.stderr).decode().strip() == 'Logged in using ChatGPT'
    require(version == 'codex-cli 0.152.1' and authenticated, 'registered_cli_or_original_login_changed')
    consumer = {'passed': True, 'actual_version': version, 'ambient_ChatGPT_login_confirmed': authenticated,
                'actual_model_requests': 0, 'requested': [proof[k] for k in ('model','reasoning_effort','service_tier')],
                'actual_formal_argv_and_local_exit': consumer_preflight(turn, proof, metadata, pins)}
    for folder in ('harness', 'consumer', 'inputs'):
        for path in (PREVIOUS / folder).glob('*'):
            if path.is_file():
                pins.append(committed(path))
    pins.extend(proof['execution_sources'])
    pins.extend(pin(path) for path in (cli, python, NS / 'inputs/PROMPT.txt'))
    original_failure = reproduce_original_failure(pins)
    source_pins = {item['path']: item for item in pins}
    require(not (EXTERNAL / 'slots').exists(), 'offline_preflight_created_live_slots')
    save(HERE / 'RUNTIME_PREFLIGHT.json', {
        'passed': True, 'old_fixed_failure_replayed_once': original_failure,
        'installed_entry_replay': entry, 'real_Owner_and_thin_replay': owner, 'consumer': consumer,
        'formal_limits': LIMITS, 'actual_Blender_starts': 0, 'actual_model_starts': 0, 'actual_rasters': 0,
        'actual_qualification_slots': 0, 'source_pins': [source_pins[k] for k in sorted(source_pins)],
    })
    print('Retained P stdio startup, actual Owner and thin replay, formal consumer argv and historical failed entry passed.')


if __name__ == '__main__':
    run()
