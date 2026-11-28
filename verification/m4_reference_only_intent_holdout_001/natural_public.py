"""Prepare and run fresh, bounded natural consumers against the installed observer."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from natural_bridge import Bridge, DEADLINE_MS, MAX_CALLS, MAX_LINE, MAX_RASTERS, PRODUCT, TOOLS, encode, pin, require, write


HERE = Path(__file__).resolve().parent
BATCH = 'M4-REFERENCE-ONLY-INTENT-HOLDOUT-001'
ROOT = Path(os.environ['HE_INTENT_RUNS']) / BATCH
PRIOR = ROOT.parent / 'M4-TASK-REGION-FOCUS-FEEDBACK-001'
CLI = Path(os.environ['HE_INTENT_CODEX_CLI'])
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
REQUESTED = {'version': '0.152.1', 'model': 'gpt-6.1-sol', 'reasoning_effort': 'medium', 'service_tier': 'default'}
CLI_RECORD = ROOT.parent / 'archive/he_m4_rail_source_region_product_native_001/slots/P1/consumer/ACTUAL_CONFIGURATION.json'
CLI_RECORD_SHA = 'fdb45c38e9c0df714468cea23c89e8b87315e9cacf5e6d6c188494e4e6b8b1d8'
PLAN = ROOT / 'preflight/NATURAL_PLAN.json'
COLD = ROOT / 'preflight/NATURAL_COLD.json'
FREEZE = ROOT / 'preflight/FROZEN_EXECUTION.json'
PRIOR_COMMIT = 'b7fe4bb0dc2ce277ff5dd7a6198365253b716c09'
LABELS = ('NATURAL_K', 'NATURAL_T')
CLOSURE_SECONDS = 600
PUBLIC_TYPES = frozenset(('thread.started', 'turn.started', 'turn.completed', 'turn.failed', 'error'))
PUBLIC_ITEMS = frozenset(('mcp_tool_call', 'agent_message'))
TYPE = re.compile(rb'^\s*\{\s*"type"\s*:\s*"([^"]+)"')
ITEM_TYPE = re.compile(rb'"item"\s*:\s*\{(?:\s*"id"\s*:\s*"[^"]+"\s*,)?\s*"type"\s*:\s*"([^"]+)"')
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def read(path):
    return json.loads(Path(path).read_bytes())


def confirmed(row):
    require(type(row) is dict and pin(row['path']) == row, 'frozen_file_changed')
    return Path(row['path'])


def sha(path):
    return pin(path)['sha256']


def consumer_config():
    require(sha(CLI_RECORD) == CLI_RECORD_SHA and sha(CLI) == CLI_SHA,
            'historical_CLI_configuration_or_binary_changed')
    raw = read(CLI_RECORD)['requested_cli_overrides_and_argv']
    args = [v for i, v in enumerate(raw) if i and raw[i - 1] == '-c' and not v.startswith('mcp_servers.')]
    fixed = {key: value for arg in args for key, value in tomllib.loads(arg).items()
             if key != 'features'}
    shell = next(tomllib.loads(arg)['features']['shell_tool'] for arg in args
                 if arg.startswith('features.shell_tool='))
    require(fixed['model'] == REQUESTED['model'] and fixed['service_tier'] == REQUESTED['service_tier']
            and fixed['model_reasoning_effort'] == REQUESTED['reasoning_effort']
            and fixed['model_provider'] == 'openai_http' and fixed['forced_login_method'] == 'chatgpt'
            and fixed['sandbox_mode'] == 'read-only' and fixed['web_search'] == 'disabled'
            and shell is False, 'unaccepted_consumer_protocol')
    return args


def cli_argv(workspace, folder, endpoint, settings, names):
    def literal(value):
        return json.dumps(str(value), ensure_ascii=True)

    toolconfig = ','.join(literal(name) + '={approval_mode="approve"}' for name in sorted(names))
    thin_args = ','.join(map(literal, ('-IB', '-X', 'utf8', HERE / 'natural.py', 'thin', endpoint)))
    mcp = ('mcp_servers.arm_engine={command=' + literal(settings['python']['path']) + ',args=[' + thin_args + '],'
           'cwd=' + literal(workspace) + ',required=true,startup_timeout_sec=60,tool_timeout_sec=450,'
           'tools={' + toolconfig + '}}')
    command = [str(CLI), 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--strict-config',
               '--json', '--skip-git-repo-check', '-C', str(workspace), '--color', 'never']
    for config in [*settings['cli_config'], mcp]:
        command.extend(('-c', config))
    return [*command, '-m', REQUESTED['model'], '-o', str(folder / 'final.txt'), '-']


def prepare():
    custody = PRIOR / 'preflight/CANDIDATE_INSTALL_CUSTODY.json'
    value = read(custody)
    require(value['passed'] and value['candidate_commit'] == PRIOR_COMMIT, 'fixed_product_candidate')
    for stage in ('python', 'blender', 'wheel', 'build'):
        confirmed(value[stage])
    require(Path(sys.executable).resolve() == Path(value['python']['path']), 'fixed_isolated_interpreter')
    login = subprocess.run([str(CLI), 'login', 'status'], capture_output=True, timeout=15, check=True,
                           creationflags=NO_WINDOW)
    require(b'Logged in using ChatGPT' in login.stdout + login.stderr, 'existing_chatgpt_login_unavailable')
    version = subprocess.run([str(CLI), '--version'], capture_output=True, timeout=15, check=True,
                             creationflags=NO_WINDOW)
    require(version.stdout.strip().endswith(REQUESTED['version'].encode()), 'historical_CLI_version_changed')
    site = Path(value['installation']['path']).resolve(strict=True)
    fixture = ROOT / 'preflight/fixture'
    fixed = [pin(p) for p in (custody, CLI, CLI_RECORD, HERE / 'natural.py', HERE / 'natural_bridge.py')]
    for row in value['source_manifest']:
        local = pin(site / row['path'])
        require(local['sha256'] == row['sha256'], 'fixed_install_source_changed')
        fixed.append(local)
    for dep in value['dependencies'].values():
        fixed.append(pin(confirmed(dep['module'])))
    plan = {'batch': BATCH, 'slots': list(LABELS), 'limits': {'business': MAX_CALLS, 'rasters': MAX_RASTERS,
             'task_seconds': DEADLINE_MS / 1000, 'lifecycle_seconds': CLOSURE_SECONDS},
            'asset': pin(fixture / 'main.blend'), 'prompts': {key: pin(fixture / f'PROMPT_{key}.txt') for key in 'KT'},
            'product': PRIOR_COMMIT, 'product_source_sha256': value['source_sha256'],
            'product_source_files': value['runtime_sources'], 'site': str(site),
            'python': value['python'], 'blender': value['blender'], 'cli': pin(CLI), 'cli_request': REQUESTED,
            'cli_config': consumer_config(), 'chatgpt_login_status': 'existing_login_confirmed',
            'inputs': fixed}
    write(PLAN, plan)
    return plan


def product(settings, folder, host):
    sys.path.insert(0, settings['site'])
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    from human_eye_plugin.runtime_identity import runtime_identity
    identity = runtime_identity()
    require(identity['source_kind'] == 'installed_distribution'
            and identity['source_sha256'] == settings['product_source_sha256']
            and len(identity['source_files']) == settings['product_source_files'], 'actual_installed_product_drift')
    config = folder / 'PRODUCT_CONFIG.json'
    write(config, {'schema_version': '1.0', 'enabled': True, 'project_root': str(folder),
                   'state_file': 'product_state.json', 'audit_file': 'product_audit.jsonl',
                   'request_budget_s': 30, 'expected_identity': {'source_sha256': identity['source_sha256']}})
    service = LiveSpatialService(config, host=host, production_mode=True)
    return service, LiveSpatialMCPServer(service, default_session_id=folder.name)


def thin_command(settings, endpoint):
    return [settings['python']['path'], '-IB', '-X', 'utf8', str(HERE / 'natural.py'), 'thin', str(endpoint)]


def thin(endpoint):
    describe = read(endpoint)
    require(describe['host'] == '127.0.0.1', 'owned_local_endpoint_required')
    with socket.create_connection((describe['host'], describe['port']), timeout=5) as connection:
        connection.settimeout(max(1, (describe['deadline_ns'] - time.perf_counter_ns()) / 1e9 + 3))
        connection.sendall(describe['token'].encode('ascii') + b'\n')
        source, sink = sys.stdin.buffer, sys.stdout.buffer
        with connection.makefile('rb', buffering=0) as replies:
            while raw := source.readline(MAX_LINE + 1):
                require(len(raw) <= MAX_LINE and raw.endswith(b'\n'), 'bounded_complete_MCP_request_line')
                message = json.loads(raw)
                connection.sendall(raw)
                if 'id' in message:
                    answer = replies.readline(MAX_LINE + 1)
                    require(0 < len(answer) <= MAX_LINE and answer.endswith(b'\n'), 'missing_complete_MCP_reply')
                    sink.write(answer)
                    sink.flush()
        connection.shutdown(socket.SHUT_WR)


def run_bridge(settings, folder, host, deadline):
    service, server = product(settings, folder, host)
    bridge = Bridge(folder, host, service, server, deadline)
    endpoint = folder / 'ENDPOINT.json'
    token = secrets.token_hex(24)
    port = bridge.start(token)
    write(endpoint, {'host': '127.0.0.1', 'port': port, 'token': token, 'deadline_ns': deadline})
    return bridge, endpoint


class ReplayHost:
    """Only retained complete captures in the offline bridge probe."""
    def __init__(self, source):
        self.source = source

    def capture_scene(self):
        return copy.deepcopy(self.source)


def cold_probe():
    settings = read(PLAN)
    folder = ROOT / 'preflight/natural_cold'
    folder.mkdir()
    source = PRIOR / 'slots/RAIL_TASK/post_capture.json'
    bridge, endpoint = run_bridge(settings, folder, ReplayHost(read(source)),
                                  time.perf_counter_ns() + 60_000_000_000)
    workspace = folder / 'workspace'
    workspace.mkdir()
    requests = []

    def add(method, params):
        requests.append({'jsonrpc': '2.0', 'id': len(requests) + 1, 'method': method, 'params': params})

    def call(name, args):
        add('tools/call', {'name': name, 'arguments': args})

    add('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'offline-natural', 'version': '1'}})
    add('tools/list', {})
    call('execute_python', {'code': 'import numpy as np\ns = np.arange(3)'})
    call('execute_python', {'code': 'print(int(s.sum()))'})
    call('execute_python', {'code': 'import os'})
    call('read_scene', {'objects': ['M21', 'M13']})
    call('render_view', {'object': 'M21', 'view': 'SCENE', 'source_triangle_indices': [2, 3]})
    call(PRODUCT, {'query': {'mode': 'active_observation', 'objects': [{'name': 'M21'}],
                             'focus': {'task_region': {'reference': {'name': 'M13'}}}}, 'include_image': True})
    call('read_images', {'refs': ['unknown-reference']})
    data = b''.join(encode(row) + b'\n' for row in requests)
    try:
        tested = subprocess.run(thin_command(settings, endpoint), input=data, capture_output=True, cwd=workspace,
                                timeout=55, creationflags=NO_WINDOW)
    finally:
        closed = bridge.finish()
    replies = [json.loads(line) for line in tested.stdout.splitlines()]
    require(tested.returncode == 0 and closed['closed'] and closed['transport_eof']
            and closed['error'] is None and [r['id'] for r in replies] == list(range(1, len(requests) + 1)),
            'offline_real_consumer_thin_dispatch_close_failed')
    tools = replies[1]['result']['tools']
    names = [tool['name'] for tool in tools]
    require(replies[0]['result']['_meta']['human_eye']['source_sha256'] == settings['product_source_sha256']
            and names == [x['name'] for x in TOOLS] + [PRODUCT]
            and 'task_region' in json.dumps(tools[-1]['inputSchema']['properties']['query']['properties']['focus']),
            'actual_catalogue_mismatch')
    statuses = [r['result']['isError'] for r in replies[2:]]
    require(statuses == [False, False, True, False, False, False, True],
            'offline_ordinary_or_product_dispatch_failed/' + str(statuses))
    require(json.loads(replies[3]['result']['content'][0]['text'])['stdout'].strip() == '3'
            and any(b['type'] == 'image' for b in replies[6]['result']['content'])
            and any(b['type'] == 'image' for b in replies[7]['result']['content']), 'offline_actual_images_missing')
    argv = cli_argv(workspace, folder, endpoint, settings, names)
    require('-' == argv[-1] and 'resume' not in argv and '--ephemeral' in argv,
            'not_original_fresh_CLI_command')
    write(COLD, {'batch': BATCH, 'passed': True, 'no_Blender_or_model': True,
                 'source': pin(source), 'plan': pin(PLAN), 'actual_tools': tools,
                 'actual_tools_sha256': hashlib.sha256(encode(tools)).hexdigest(),
                 'actual_wire': pin(folder / 'wire/INDEX.jsonl'), 'closure': closed, 'cold_cli_argv': argv,
                 'actual_thin_exit': tested.returncode, 'request_statuses': statuses})


def public_cli(raw, folder):
    final, turn, messages = None, None, []
    with raw.open('rb') as source, (folder / 'public_events.jsonl').open('xb') as out:
        for line in source:
            head = TYPE.search(line[:175])
            if head is None:
                continue
            event_type = head.group(1).decode('ascii')
            if event_type.startswith('item.'):
                item_type = ITEM_TYPE.search(line[:300])
                if item_type is None or item_type.group(1).decode('ascii') not in PUBLIC_ITEMS:
                    continue
            elif event_type not in PUBLIC_TYPES:
                continue
            row = json.loads(line)
            if row['type'] == 'item.completed' and row['item']['type'] == 'agent_message':
                final = row['item']['text']
                messages.append(final)
            if row['type'] in ('turn.completed', 'turn.failed'):
                turn = row
            out.write(line)
    usage = turn.get('usage') if turn is not None and turn['type'] == 'turn.completed' else None
    if isinstance(usage, dict) and all(type(usage.get(k)) is int for k in
                                        ('input_tokens', 'cached_input_tokens', 'output_tokens')):
        uncached = usage['input_tokens'] - usage['cached_input_tokens'] + usage['output_tokens']
    else:
        uncached = None
    return final, {'turn_status': None if turn is None else turn['type'], 'usage': usage,
                   'uncached_input_plus_output': uncached, 'public_agent_message_count': len(messages)}


def checked_settings(label):
    freeze = read(FREEZE)
    require(freeze['batch'] == BATCH and confirmed(freeze['natural_plan']) == PLAN.resolve()
            and confirmed(freeze['natural_cold']) == COLD.resolve(), 'missing_unified_natural_freeze')
    for row in freeze['inputs']:
        confirmed(row)
    plan, preflight = read(PLAN), read(COLD)
    require(preflight['passed'] and preflight['plan'] == pin(PLAN) and label in plan['slots']
            and plan['limits'] == {'business': MAX_CALLS, 'rasters': MAX_RASTERS,
                                   'task_seconds': DEADLINE_MS / 1000, 'lifecycle_seconds': CLOSURE_SECONDS},
            'natural_run_not_admitted')
    for row in plan['inputs']:
        confirmed(row)
    require(Path(sys.executable).resolve() == confirmed(plan['python'])
            and confirmed(plan['cli']) == CLI.resolve(), 'fixed_runtime_drift')
    diagnostic = ROOT / 'DIAGNOSTIC_EXECUTION.json'
    require(diagnostic.is_file(), 'diagnostic_execution_required_before_natural_slots')
    if label == LABELS[1]:
        require((ROOT / 'slots' / LABELS[0] / 'closed.json').is_file(), 'first_natural_slot_must_close')
    return plan, preflight


def run_slot(label):
    settings, preflight = checked_settings(label)
    folder = ROOT / 'slots' / label
    folder.mkdir()
    fixture = folder / 'input.blend'
    shutil.copyfile(confirmed(settings['asset']), fixture)
    prompt = confirmed(settings['prompts'][label[-1]]).read_bytes()
    require(sha(fixture) == settings['asset']['sha256'], 'independent_fixture_copy_changed')
    workspace, consumer = folder / 'workspace', folder / 'consumer'
    workspace.mkdir()
    consumer.mkdir()
    started = time.perf_counter_ns()
    deadline = started + DEADLINE_MS * 1_000_000
    owned_deadline = started + CLOSURE_SECONDS * 1_000_000_000
    write(folder / 'NATURAL_START.json', {'batch': BATCH, 'slot': label, 'freeze': pin(FREEZE),
          'started_ns': started, 'deadline_ns': deadline, 'owned_deadline_ns': owned_deadline,
          'prompt': settings['prompts'][label[-1]], 'fixture': pin(fixture)})
    sys.path.insert(0, settings['site'])
    from human_eye_plugin.blender_process import BlenderProcessHost
    cli, bridge, transport, host, capture, initial = None, None, None, None, None, None
    code, caught, info, cli_started, cli_closed = None, None, None, None, None
    try:
        host = BlenderProcessHost(str(confirmed(settings['blender'])), fixture, timeout=25, startup_timeout=45)
        write(folder / 'BLENDER_READY.json', {'pid': host._process.pid, 'started_ns': started,
                                              'ready_ns': time.perf_counter_ns()})
        original_capture = host.capture_scene

        def observed_capture():
            nonlocal initial
            current = original_capture()
            if initial is None:
                initial = current
                write(folder / 'initial_capture.json', current)
            return current

        host.capture_scene = observed_capture
        bridge, endpoint = run_bridge(settings, folder, host, deadline)
        argv = cli_argv(workspace, consumer, endpoint, settings, [r['name'] for r in preflight['actual_tools']])
        with (consumer / 'stdout.raw.bin').open('xb') as stdout, (consumer / 'stderr.raw.bin').open('xb') as stderr:
            cli_started = time.perf_counter_ns()
            cli = subprocess.Popen(argv, cwd=workspace, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   creationflags=NO_WINDOW)
            cli.communicate(input=prompt, timeout=max(1, (deadline - time.perf_counter_ns()) / 1e9))
        cli_closed = time.perf_counter_ns()
        code = cli.returncode
    except BaseException as error:
        caught = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if cli is not None and cli.poll() is None:
            cli.terminate()
            try:
                cli.wait(4)
            except subprocess.TimeoutExpired:
                cli.kill()
                cli.wait(4)
            cli_closed, code = time.perf_counter_ns(), cli.returncode
        if bridge is not None:
            transport = bridge.finish()
        before_close = time.perf_counter_ns()
        blender_exit = None
        try:
            if host is not None:
                capture = original_capture()
                write(folder / 'post_capture.json', capture)
        except Exception as error:
            caught = caught or {'type': type(error).__name__, 'message': str(error)}
        finally:
            if host is not None:
                host.close()
                blender_exit = host._process.returncode
        closed = time.perf_counter_ns()
        unchanged = initial is not None and capture is not None and initial == capture
        write(folder / 'closed.json', {'blender_pid': None if host is None else host._process.pid,
             'blender_exit': blender_exit, 'cli_exit': code, 'fixture_sha256_before': settings['asset']['sha256'],
             'fixture_sha256_after': sha(fixture), 'post_capture': pin(folder / 'post_capture.json') if capture else None,
             'same_before_after_capture': unchanged, 'zero_geometry_preread': True,
             'close_started_ns': before_close, 'closed_ns': closed,
             'owned_deadline_ns': owned_deadline, 'transport': transport, 'error': caught})
    final, info = None, {}
    raw = consumer / 'stdout.raw.bin'
    if raw.is_file():
        final, info = public_cli(raw, consumer)
    final_path = consumer / 'final.txt'
    actual_final = final_path.is_file() and final is not None and final_path.read_text(encoding='utf8').strip() == final.strip()
    passed = bool(code == blender_exit == 0 and final and actual_final and unchanged
                  and transport and transport['closed'] and transport['transport_eof']
                  and not transport['error'] and caught is None and closed <= owned_deadline
                  and info.get('turn_status') == 'turn.completed')
    write(consumer / 'RESULT.json', {'batch': BATCH, 'slot': label, 'consumer_process_started': cli is not None,
          'status': 'complete' if passed else 'incomplete', 'passed_transport': passed,
          'cli_requested': REQUESTED, 'cli_started_ns': cli_started, 'cli_closed_ns': cli_closed,
          'started_ns': started, 'closed_ns': closed, 'consumer_exit': code, 'completion': info,
          'raw_public_final_match': actual_final, 'native_closure': pin(folder / 'closed.json'),
          'stdin_prompt': settings['prompts'][label[-1]], 'error': caught})
    return 0 if passed else 1


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'required_isolated_python')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'cold', 'thin', 'slot'))
    parser.add_argument('value', nargs='?')
    args = parser.parse_args()
    if args.phase == 'prepare':
        prepare()
    elif args.phase == 'cold':
        cold_probe()
    elif args.phase == 'thin':
        thin(Path(args.value))
    else:
        return run_slot(args.value)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
