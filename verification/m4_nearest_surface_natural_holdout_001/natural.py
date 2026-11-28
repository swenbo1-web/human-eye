"""Own two frozen natural consumers using the installed nearest-surface observer."""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'm4_reference_only_intent_holdout_001'
spec = importlib.util.spec_from_file_location('prior_natural', PREVIOUS / 'natural.py')
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
sys.path.insert(0, str(HERE))
from natural_evidence import RecordingBridge
from natural_bridge import DEADLINE_MS, MAX_CALLS, MAX_RASTERS, PRODUCT, TOOLS, encode, pin, require, write

BATCH = 'M4-NEAREST-SURFACE-NATURAL-HOLDOUT-001'
ADMIN = 'a70496e203f61782f2108bf4d5af4b0ad6eab824dd6a8758d99a2ccac1956a98'
CANDIDATE = '4225256485a82a9ddbdeeca61e1bbd3275574a6e'
SOURCE = '60eabe4f875aabbd6c7b1c24c7498ed06b53d10b40a0e70a0ab920b4a64631e0'
WHEEL = '5b1f10708bc61cf21453ca0c72fb54cc8b7af19fc3925747bcef96499fd8e4fb'
INSTALL_SHA = '60014204a745d00ea804dc06df0fff51dddecdbd16b5b6bcc22af01656ab117d'
SLOTS = ('NATURAL_K', 'NATURAL_T')
PLAN = 'preflight/NATURAL_PLAN.json'
COLD = 'preflight/NATURAL_COLD.json'
FREEZE = 'preflight/FROZEN_EXECUTION.json'
LIMITS = {'business': MAX_CALLS, 'rasters': MAX_RASTERS,
          'task_seconds': DEADLINE_MS / 1000, 'lifecycle_seconds': prior.CLOSURE_SECONDS}
CLI, REQUESTED, NO_WINDOW = prior.CLI, prior.REQUESTED, prior.NO_WINDOW
read, confirmed, hash_file = prior.read, prior.confirmed, prior.sha


def fixed_libraries():
    # Read verified prior bytecode-free source. Preserve the benchmark's
    # ordinary tools, event parser, and native pipe recorder unchanged.
    files = [
        PREVIOUS/'natural.py',
        PREVIOUS/'natural_bridge.py',
        PREVIOUS/'diagnostic.py',
        PREVIOUS.parent/'m4_task_region_focus_feedback_001/runner.py',
        PREVIOUS.parent/'m4_task_region_focus_feedback_001/worker_wire.py',
        PREVIOUS.parent/'m4_directed_focus_assembly_holdout_001/harness.py',
    ]
    required = ('5cb257ae6eb8d97ca7aa7c9154421e16d4dfc942b41a071dae2553368e25b065',
                '6215f81b0d2b286849647222159e9de27b7a837326aa6761b5c7246ed9b67bab')
    require(tuple(hash_file(p) for p in files[:2]) == required, 'prior_natural_code_changed')
    return files


def prepare(root):
    require(root.name == BATCH and hash_file(root/'preflight/ADMIN_PLAN.md') == ADMIN
            and sys.flags.isolated and sys.dont_write_bytecode, 'wrong_batch_or_interpreter')
    custody = root.parent / 'M4-NEAREST-SURFACE-FIRST-FOCUS-001/preflight/INSTALL_CUSTODY.json'
    require(hash_file(custody) == INSTALL_SHA, 'fixed_isolated_install_receipt_changed')
    value = read(custody)
    require(value['passed'] is True and value['candidate_commit'] == CANDIDATE
            and value['source_sha256'] == SOURCE and value['wheel']['sha256'] == WHEEL
            and value['runtime_sources'] == len(value['source_manifest']) == 146
            and Path(sys.executable).resolve() == confirmed(value['python']), 'wrong_fixed_installed_product')
    fixed = [pin(p) for p in [custody, CLI, prior.CLI_RECORD, HERE/'natural.py',
                             HERE/'natural_evidence.py', HERE/'transport.py', *fixed_libraries()]]
    transport_gate = root / 'preflight/TRANSPORT_RESULT.json'
    checked = read(transport_gate)
    require(checked['passed'] is True and checked['Blender'] == checked['models'] == 0
            and confirmed(checked['formal_transport']) == (HERE/'transport.py').resolve()
            and set(checked['cases']) == {'normal', 'missing_last', 'reset'}, 'wrong_no_turn_transport_gate')
    fixed.extend([pin(transport_gate), checked['plan'], *checked['cases'].values()])
    fixed.extend(pin(confirmed(value[key])) for key in ('blender', 'wheel', 'build'))
    site = Path(value['installation']['path']).resolve(strict=True)
    for row in value['source_manifest']:
        local = pin(site / row['path'])
        require(local['sha256'] == row['sha256'], 'installed_runtime_file_changed/' + row['path'])
        fixed.append(local)
    for dep in value['dependencies'].values():
        fixed.append(pin(confirmed(dep['module'])))
    cli_config = prior.consumer_config()
    login = subprocess.run([str(CLI), 'login', 'status'], capture_output=True, timeout=15, check=True, creationflags=NO_WINDOW)
    require(b'Logged in using ChatGPT' in login.stdout + login.stderr, 'existing_ChatGPT_login_not_available')
    version = subprocess.run([str(CLI), '--version'], capture_output=True, timeout=15, check=True, creationflags=NO_WINDOW)
    require(version.stdout.strip().endswith(REQUESTED['version'].encode()), 'unexpected_cli_version')
    fixture = root / 'preflight/fixture'
    prompts = {key: pin(fixture / f'PROMPT_{key}.txt') for key in 'KT'}
    # Geometry truth remains in the administrator freeze. The runner needs
    # only the asset bytes and the two immutable user prompts.
    return {'batch': BATCH, 'slots': list(SLOTS), 'limits': LIMITS,
            'asset': pin(fixture / 'main.blend'), 'prompts': prompts, 'product': CANDIDATE,
            'product_source_sha256': SOURCE, 'product_source_files': len(value['source_manifest']),
            'site': str(site), 'python': value['python'], 'blender': value['blender'], 'wheel': value['wheel'],
            'cli': pin(CLI), 'cli_request': REQUESTED, 'cli_config': cli_config,
            'chatgpt_login_status': 'existing_login_confirmed',
            'inputs': fixed}


def plan_settings(root):
    plan = read(root / PLAN)
    require(plan['batch'] == BATCH and plan['slots'] == list(SLOTS) and plan['limits'] == LIMITS
            and plan['product'] == CANDIDATE and plan['product_source_sha256'] == SOURCE
            and Path(sys.executable).resolve() == confirmed(plan['python'])
            and confirmed(plan['cli']) == CLI.resolve() and plan['cli_request'] == REQUESTED,
            'natural_frozen_plan_changed')
    for row in plan['inputs']:
        confirmed(row)
    confirmed(plan['asset'])
    for prompt in plan['prompts'].values():
        confirmed(prompt)
    return plan


def cli_argv(workspace, folder, endpoint, settings, names):
    def literal(value):
        return json.dumps(str(value), ensure_ascii=True)

    toolconfig = ','.join(literal(name) + '={approval_mode="approve"}' for name in sorted(names))
    thin = ','.join(map(literal, ('-IB', '-X', 'utf8', HERE/'transport.py', 'thin', endpoint)))
    definition = ('mcp_servers.arm_engine={command=' + literal(settings['python']['path'])
                  + ',args=[' + thin + '],cwd=' + literal(workspace)
                  + ',required=true,startup_timeout_sec=60,tool_timeout_sec=450,tools={' + toolconfig + '}}')
    command = [str(CLI), 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--strict-config',
               '--json', '--skip-git-repo-check', '-C', str(workspace), '--color', 'never']
    for option in [*settings['cli_config'], definition]:
        command.extend(('-c', option))
    return [*command, '-m', REQUESTED['model'], '-o', str(folder / 'final.txt'), '-']


def bridge_for(settings, folder, host, deadline):
    service, server = prior.product(settings, folder, host)
    return RecordingBridge(folder, host, service, server, deadline)


def cold_source(root):
    old = root.parent / 'M4-REFERENCE-ONLY-INTENT-HOLDOUT-001'
    archive = old / 'sealed/ORIGINAL_RUNTIME.zip'
    index = old / 'sealed/RAW_INDEX.json'
    member = 'slots/DIAGNOSTIC/post_capture.json'
    source = old / member
    require(hash_file(archive) == '956d479d4d7d7a4516e3a9bea0f9f480f1cbce22bb4ab4cf3fea430fd08500a4'
            and hash_file(index) == '174f15c8378e811157158fbaa8e335807a0d88abef5598fa57c54bad78ba24c4',
            'cold_capture_archive_changed')
    info = read(index)['members'][member]
    with ZipFile(archive) as bundle:
        archived = bundle.read(member)
    require(archived == source.read_bytes() and len(archived) == info['bytes']
            and sha256(archived).hexdigest() == info['sha256'], 'cold_capture_source_not_sealed')
    return source


def cold(root):
    from transport import start_transport

    settings = plan_settings(root)
    folder = root / 'preflight/natural_cold'
    folder.mkdir(exist_ok=False)
    workspace = folder / 'workspace'
    workspace.mkdir()
    source = cold_source(root)
    deadline = time.perf_counter_ns() + 65_000_000_000
    bridge = bridge_for(settings, folder, prior.ReplayHost(read(source)), deadline)
    requests = []

    def add(method, params):
        requests.append({'jsonrpc': '2.0', 'id': len(requests) + 1, 'method': method, 'params': params})

    def call(tool, args):
        add('tools/call', {'name': tool, 'arguments': args})

    add('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'owned-natural-cold', 'version': '1'}})
    add('tools/list', {})
    call('execute_python', {'code': 'import numpy as np\ns = np.arange(3)'})
    call('execute_python', {'code': 'print(int(s.sum()))'})
    call('execute_python', {'code': 'import os'})
    call('read_scene', {'objects': ['Part M', 'Fixture T']})
    call('render_view', {'object': 'Part M', 'view': 'TOP', 'source_triangle_indices': [2, 3]})
    call(PRODUCT, {'query': {'mode': 'active_observation', 'objects': [{'name': 'Part M'}],
                   'focus': {'task_region': {'reference': {'name': 'Fixture T'}, 'relation': 'nearest_surface'}}},
                   'include_image': True, 'response_detail': 'full'})
    call('read_images', {'refs': ['unknown-reference']})
    data = b''.join(encode(row) + b'\n' for row in requests)
    (folder / 'THIN_STDIN.bin').write_bytes(data)
    owner = start_transport(folder, bridge, deadline)
    cmd = [settings['python']['path'], '-IB', '-X', 'utf8', str(HERE / 'transport.py'), 'thin', str(owner.endpoint)]
    status, output, errors, failed = None, b'', b'', None
    thin = None
    try:
        thin = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=workspace, creationflags=NO_WINDOW)
        owner.bind_cli(thin.pid)
        output, errors = thin.communicate(input=data, timeout=54)
        status = thin.returncode
    except subprocess.TimeoutExpired:
        thin.kill()
        output, errors = thin.communicate(timeout=8)
        status, failed = thin.returncode, 'thin_cold_timeout'
    finally:
        closed = owner.finish()
    (folder / 'THIN_STDOUT.bin').write_bytes(output)
    (folder / 'THIN_STDERR.bin').write_bytes(errors)
    try:
        replies = [json.loads(line) for line in output.splitlines()]
        require(failed is None and status == 0 and closed['closed'] and closed['transport_eof']
                and closed['error'] is None and [r['id'] for r in replies] == list(range(1, len(requests)+1))
                and closed['paired_exchanges'] == len(requests), 'shared_thin_dispatch_or_close_failed')
        tools = replies[1]['result']['tools']
        names = [tool['name'] for tool in tools]
        require(replies[0]['result']['_meta']['human_eye']['source_sha256'] == SOURCE
                and tools[:-1] == TOOLS and names == [x['name'] for x in TOOLS] + [PRODUCT]
                and 'nearest_surface' in json.dumps(tools[-1]['inputSchema']['properties']['query']['properties']['focus']),
                'actual_natural_catalogue_drift')
        statuses = [r['result']['isError'] for r in replies[2:]]
        require(statuses == [False, False, True, False, False, False, True]
                and json.loads(replies[3]['result']['content'][0]['text'])['stdout'].strip() == '3'
                and all(any(block['type'] == 'image' for block in reply['result']['content']) for reply in replies[6:8]),
                'ordinary_or_product_probe_failed')
        frames = [json.loads(row) for row in (folder/'physical_frames.jsonl').read_bytes().splitlines()]
        require(len(frames) >= 2 and len(frames) <= MAX_RASTERS and all(r['frame_status'] == 'bound' for r in frames),
                'new_cold_frame_custody_unproven')
        argv = cli_argv(workspace, folder, owner.endpoint, settings, names)
        require(argv[-1] == '-' and '--ephemeral' in argv and 'resume' not in argv,
                'formal_cli_not_fresh')
        reply = {'passed': True, 'actual_tools': tools, 'actual_tools_sha256': sha256(encode(tools)).hexdigest(),
                 'statuses': statuses, 'cold_cli_argv': argv, 'physical_frames': pin(folder/'physical_frames.jsonl')}
    except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
        reply = {'passed': False, 'failure': str(error)}
    write(root / COLD, {'batch': BATCH, 'no_Blender_or_model': True, 'plan': pin(root / PLAN),
          'source': pin(source), 'actual_thin_exit': status, 'actual_wire': pin(folder / 'wire/INDEX.jsonl'),
          'thin_output': pin(folder / 'THIN_STDOUT.bin'), 'closure': closed, **reply})
    return int(not reply['passed'])


def admitted(root, label):
    plan = plan_settings(root)
    freeze = read(root / FREEZE)
    require(freeze['batch'] == BATCH and confirmed(freeze['natural_plan']) == (root/PLAN).resolve()
            and confirmed(freeze['natural_cold']) == (root/COLD).resolve()
            and confirmed(freeze['transport_preflight']) == (root/'preflight/TRANSPORT_RESULT.json').resolve(),
            'missing_final_natural_freeze')
    for row in freeze['inputs']:
        confirmed(row)
    fixture = freeze['fixture']
    require(fixture['blend'] == plan['asset'] and fixture['prompts'] == plan['prompts'],
            'unified_natural_asset_or_prompt_mismatch')
    actual = read(root / COLD)
    require(actual['passed'] is True and actual['plan'] == pin(root/PLAN) and label in plan['slots'],
            'actual_natural_cold_not_accepted')
    if label == SLOTS[1]:
        prev = root / 'slots' / SLOTS[0] / 'closed.json'
        require(read(prev)['safe_to_continue'] is True, 'previous_natural_slot_did_not_prove_safe_close')
    return plan, actual


def native_wire_custody(folder):
    wire = folder / 'worker_wire'
    idx = read(wire / 'INDEX.json')
    t = [r for r in idx['lines']['TX'] if r['kind'] == 'request']
    r = [r for r in idx['lines']['RX'] if r['kind'] == 'response']
    require(len(t) == len(r) >= 3 and all(v['terminated'] for v in [*t, *r])
            and [v['id'] for v in t] == [v['id'] for v in r] == list(range(1, len(t) + 1))
            and t[0]['command'] == 'capabilities' and t[-1]['command'] == 'shutdown'
            and r[-1]['state'] == 'result', 'native_worker_not_paired_and_closed')
    for key in ('TX', 'RX'):
        file = wire / (key + '.bin')
        full = file.read_bytes()
        offset = 0
        for line in idx['lines'][key]:
            require(line['offset'] == offset and
                    sha256(full[offset:offset + line['bytes']]).hexdigest() == line['sha256'],
                    'native_wire_span_bytes_not_original')
            offset += line['bytes']
        require(offset == len(full), 'native_wire_unindexed_bytes')
        if key == 'RX':
            last = r[-1]
            packet = full[last['offset']:last['offset'] + last['bytes']]
            require(packet.startswith(b'HUMAN_EYE_RPC:')
                    and json.loads(packet.removeprefix(b'HUMAN_EYE_RPC:')) ==
                        {'id': last['id'], 'result': {'closed': True}}, 'native_worker_shutdown_not_acknowledged')
    return {'passed': True, 'index': pin(wire / 'INDEX.json'), 'tx': pin(wire / 'TX.bin'),
            'rx': pin(wire / 'RX.bin'), 'pairs': len(t), 'worker_commands': [v['command'] for v in t]}


def run(root, label):
    from transport import start_transport, verify_cli_consumption

    settings, preflight = admitted(root, label)
    folder = root / 'slots' / label
    folder.mkdir(parents=True, exist_ok=False)
    fixture = folder / 'input.blend'
    shutil.copyfile(confirmed(settings['asset']), fixture)
    fixture.chmod(0o444)
    prompt = confirmed(settings['prompts'][label[-1]]).read_bytes()
    require(hash_file(fixture) == settings['asset']['sha256'] and len(prompt) > 0,
            'fresh_private_fixture_or_prompt_drift')
    workspace, consumer = folder / 'workspace', folder / 'consumer'
    workspace.mkdir()
    consumer.mkdir()
    started = time.perf_counter_ns()
    deadline = started + DEADLINE_MS * 1_000_000
    owned = started + prior.CLOSURE_SECONDS * 1_000_000_000
    write(folder/'NATURAL_START.json', {'batch': BATCH, 'slot': label, 'freeze': pin(root/FREEZE),
          'started_ns': started, 'deadline_ns': deadline, 'owned_deadline_ns': owned,
          'fixture': pin(fixture), 'prompt': settings['prompts'][label[-1]]})
    sys.path.insert(0, settings['site'])
    from human_eye_plugin import blender_process
    sys.path.insert(0, str(PREVIOUS))
    import diagnostic as prior_diagnostic

    launch = prior_diagnostic.pipeline.Launch(folder, 'formal',
             {'blender': settings['blender'], 'candidate_site': settings['site']}, fixture)
    manager = blender_process.subprocess
    blender_process.subprocess = launch
    host = cli = owner = transport = initial = terminal = original_capture = None
    error = cli_started = cli_closed = None
    capture_time = []
    try:
        host = blender_process.BlenderProcessHost(str(confirmed(settings['blender'])), fixture,
                                                   timeout=25, startup_timeout=45)
        require(launch.process is host._process, 'natural_did_not_own_Blender_spawn')
        write(folder / 'BLENDER_READY.json', {'pid': host._process.pid, 'started_ns': started,
              'ready_ns': time.perf_counter_ns(), 'runtime_source_sha256': settings['product_source_sha256']})
        original_capture = host.capture_scene

        def observed_capture(*args, **kwargs):
            nonlocal initial
            begin = time.perf_counter_ns()
            try:
                current = original_capture(*args, **kwargs)
                if initial is None:
                    initial = current
                    write(folder / 'initial_capture.json', current)
                return current
            finally:
                capture_time.append({'ordinal': bridge.ordinal, 'started_ns': begin,
                                     'closed_ns': time.perf_counter_ns()})

        host.capture_scene = observed_capture
        bridge = bridge_for(settings, folder, host, deadline)
        owner = start_transport(folder, bridge, deadline)
        argv = cli_argv(workspace, consumer, owner.endpoint, settings, [r['name'] for r in preflight['actual_tools']])
        write(consumer/'ACTUAL_CONFIGURATION.json', {'requested_cli_overrides_and_argv': argv,
              'cli_identity': settings['cli'], 'cli_request': REQUESTED, 'catalogue_sha256': preflight['actual_tools_sha256']})
        with (consumer/'stdout.raw.bin').open('xb') as stdout, (consumer/'stderr.raw.bin').open('xb') as stderr:
            cli_started = time.perf_counter_ns()
            cli = subprocess.Popen(argv, cwd=workspace, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   creationflags=NO_WINDOW)
            owner.bind_cli(cli.pid)
            cli.communicate(input=prompt, timeout=max(1, (deadline - time.perf_counter_ns()) / 1e9))
            cli_closed = time.perf_counter_ns()
    except BaseException as failure:
        error = {'type': type(failure).__name__, 'message': str(failure)}
    finally:
        blender_process.subprocess = manager
        if cli is not None and cli.poll() is None:
            cli.terminate()
            try:
                cli.wait(4)
            except subprocess.TimeoutExpired:
                cli.kill()
                cli.wait(4)
            cli_closed = time.perf_counter_ns()
        consumer_code = cli.poll() if cli else None
        if owner is not None:
            try:
                transport = owner.finish()
            except Exception as failure:
                error = error or {'type': type(failure).__name__, 'message': str(failure)}
        before_close = time.perf_counter_ns()
        terminal_start = terminal_end = None
        try:
            if host is not None and original_capture is not None and transport and transport['closed']:
                terminal_start = time.perf_counter_ns()
                terminal = original_capture()
                terminal_end = time.perf_counter_ns()
                write(folder/'post_capture.json', terminal)
        except Exception as failure:
            error = error or {'type': type(failure).__name__, 'message': str(failure)}
        finally:
            proc = launch.process
            try:
                if host is not None:
                    host.close()
                elif proc is not None and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(4)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(4)
                    for stream in (proc.stdin, proc.stdout, proc.stderr):
                        if stream is not None:
                            stream.close()
                if launch.wire is not None:
                    launch.wire.publish()
            except Exception as failure:
                error = error or {'type': type(failure).__name__, 'message': str(failure)}
        native_exit = proc.poll() if proc else None
        native = None
        if proc is not None and native_exit == 0:
            try:
                native = native_wire_custody(folder)
            except Exception as failure:
                native = {'passed': False, 'error': str(failure)}
            write(folder/'WORKER_CUSTODY.json', native)
        tail = time.perf_counter_ns()
        unchanged = initial is not None and terminal is not None and initial == terminal
        safe = bool(proc is not None and native_exit == 0 and native and native['passed']
                    and cli is not None and consumer_code is not None and transport and transport['closed']
                    and transport['transport_eof'] and transport['zero_in_flight']
                    and not transport['error'] and tail <= owned)
        write(folder/'closed.json', {'blender_pid': proc.pid if proc else None, 'blender_exit': native_exit,
             'cli_pid': cli.pid if cli else None, 'cli_exit': consumer_code, 'same_before_after_capture': unchanged,
             'safe_to_continue': safe, 'fixture_sha256_before': settings['asset']['sha256'],
             'fixture_sha256_after': hash_file(fixture), 'zero_geometry_preread': True,
             'initial_capture': pin(folder/'initial_capture.json') if initial is not None else None,
             'post_capture': pin(folder/'post_capture.json') if terminal is not None else None,
             'terminal_started_ns': terminal_start, 'terminal_closed_ns': terminal_end,
             'captures': capture_time, 'close_started_ns': before_close, 'closed_ns': tail,
             'owned_deadline_ns': owned, 'transport': transport, 'worker_custody': native, 'error': error})

    final, cli_info, delivery = None, {}, None
    raw = consumer / 'stdout.raw.bin'
    if raw.is_file():
        try:
            final, cli_info = prior.public_cli(raw, consumer)
            delivery = verify_cli_consumption(folder, consumer/'public_events.jsonl')
        except Exception as failure:
            delivery = {'passed': False, 'error': str(failure)}
        write(consumer/'DELIVERY.json', delivery)
    final_path = consumer / 'final.txt'
    same_answer = bool(final and final_path.is_file() and final_path.read_text(encoding='utf8').strip() == final.strip())
    correct_close = bool(safe and unchanged and delivery and delivery['passed'] and not error
                         and consumer_code == 0 and same_answer and cli_info.get('turn_status') == 'turn.completed')
    write(consumer / 'RESULT.json', {'batch': BATCH, 'slot': label, 'consumer_process_started': cli is not None,
          'status': 'complete' if correct_close else 'incomplete', 'passed_transport': correct_close,
          'safe_to_continue': safe, 'cli_requested': REQUESTED, 'cli_started_ns': cli_started,
          'cli_closed_ns': cli_closed, 'started_ns': started, 'closed_ns': tail, 'consumer_exit': consumer_code,
          'completion': cli_info, 'raw_public_final_match': same_answer, 'delivery': delivery,
          'native_closure': pin(folder/'closed.json'), 'stdin_prompt': settings['prompts'][label[-1]], 'error': error})
    return int(not correct_close)


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode, 'required_isolated_python')
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root', type=lambda path: Path(path).resolve(strict=True))
    cli.add_argument('phase', choices=('plan', 'cold', 'run'))
    cli.add_argument('slot', nargs='?', choices=SLOTS)
    args = cli.parse_args()
    if args.phase == 'plan':
        write(args.root / PLAN, prepare(args.root))
    elif args.phase == 'cold':
        raise SystemExit(cold(args.root))
    else:
        require(args.slot is not None, 'formal_natural_requires_slot')
        raise SystemExit(run(args.root, args.slot))
