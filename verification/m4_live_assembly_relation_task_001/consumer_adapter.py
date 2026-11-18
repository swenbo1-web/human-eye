"""Bind the accepted fresh CLI event loop to one live N or P slot."""

import hashlib
import json
from pathlib import Path
import ast
import sys
import time
import types


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bridge import TOOL_LIMIT, TOOL_NAMES, load, save
import consumer_contract


BASE = Path('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
BASE_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
THIN = HERE / 'thin_stdio.py'
LOOP = HERE.parent / 'm1_source_region_facts_first_001/harness/consumer_loop.py'
PROMPT = HERE / 'inputs/PROMPT.txt'
SLOTS = (('N1', 'N'), ('P1', 'P'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fresh_argv(argv, expected_thread_id=None):
    command = list(argv)
    if (expected_thread_id is not None or len(command) < 3 or command[1] != 'exec' or command[-1] != '-'
            or '--ephemeral' not in command or any(value in command for value in ('resume', 'fork', '--last', '--all'))):
        raise ValueError('original_fresh_ephemeral_CLI_argv_required')
    return command


def consumer_adapter():
    accepted = load('_m4_live_facts_first_loop', LOOP)

    def initial_argv(python, cell_path, work, final, group):
        if (group not in TOOL_NAMES or Path(python).resolve() != BASE.resolve()
                or sha(BASE) != BASE_SHA or sha(CLI) != CLI_SHA):
            raise ValueError('fixed_CLI_and_Python_bytes_required')
        cell = json.loads(Path(cell_path).read_bytes())
        config = accepted.previous.settings()
        config['mcp_servers.arm_engine'] = {
            'command': str(BASE), 'args': ['-I', '-B', '-X', 'utf8', str(THIN), '--endpoint', cell['endpoint'],
                '--audit', str(Path(cell_path).parent / 'attachments')], 'cwd': str(work), 'required': True,
            'startup_timeout_sec': 60, 'tool_timeout_sec': 450,
            'tools': {name: {'approval_mode': 'approve'} for name in sorted(TOOL_NAMES[group])},
        }
        command = [str(CLI), 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--strict-config',
                   '--json', '--skip-git-repo-check', '-C', str(work), '--color', 'never']
        for key, value in config.items():
            command.extend(['-c', key + '=' + accepted.previous.toml(value)])
        return command + ['-m', 'gpt-6.1-sol', '-o', str(final), '-']

    # Retain the reviewed M1 event/process loop with this batch's tool limit.
    before = ("if len(record['tool_calls']) > 4:\n"
              "                                raise ValueError('original_four_completed_tool_call_limit')")
    after = ("if len(record['tool_calls']) > TOOL_LIMIT:\n"
             "                                raise ValueError('original_tool_attempt_limit')")
    source = LOOP.read_text(encoding='utf8')
    if source.count(before) != 1:
        raise ValueError('accepted_event_loop_budget_anchor_changed')
    runtime_cli = types.SimpleNamespace(argv_for_turn=fresh_argv, summarize_turn=accepted.cli.summarize_turn,
                                        TURN_LABELS=accepted.cli.TURN_LABELS)
    scope = dict(accepted.consume_turn.__globals__)
    scope.update(initial_argv=initial_argv, cli=runtime_cli, TOOLS_BY_GROUP=TOOL_NAMES,
                 archive_turn=consumer_contract.archive_turn, bridge_contract=consumer_contract,
                 TOOL_LIMIT=TOOL_LIMIT)
    # Execute only the function definition to avoid a second import and keep the injected globals private.
    tree = ast.parse(source.replace(before, after), filename=str(LOOP))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'consume_turn')
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(LOOP), 'exec'), scope)
    sources = {LOOP, THIN, Path(__file__).resolve(), HERE / 'bridge.py', HERE / 'consumer_contract.py',
               HERE.parent / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json'}
    visited = set()

    def collect(module):
        if id(module) in visited:
            return
        visited.add(id(module))
        source_file = getattr(module, '__file__', None)
        if source_file and Path(source_file).resolve().is_relative_to(HERE.parent):
            sources.add(Path(source_file).resolve())
            for value in vars(module).values():
                if isinstance(value, types.ModuleType):
                    collect(value)

    collect(accepted)
    collect(consumer_contract)
    collect(sys.modules['bridge'])
    proof = {'schema': 'm4-live-assembly-relation-task-001-consumer-adapter-v1', 'fresh_ephemeral': True,
             'CLI_path': str(CLI), 'CLI_sha256': CLI_SHA, 'CLI_version': '0.152.1', 'Python_path': str(BASE),
             'Python_sha256': BASE_SHA, 'model': 'gpt-6.1-sol', 'reasoning_effort': 'medium', 'service_tier': 'default',
             'original_loop': str(LOOP), 'business_tool_attempt_limit': TOOL_LIMIT,
             'completed_CLI_tool_limit': TOOL_LIMIT,
             'loop_change': 'The guard counts all completed CLI tool events, including empty resource discovery. '
                            'Raw stdio independently records and limits all tools/call attempts, including failures.',
             'consumer_launches_during_adapter_construction': 0,
             'execution_sources': [{'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
                                   for path in sorted(sources)]}
    return scope['consume_turn'], proof


def metadata(folder, proof, record):
    rows = []
    actual = []
    for name in ('events.jsonl', 'stderr_lines.jsonl'):
        source = folder / name
        if not source.exists():
            continue
        for line in source.read_bytes().splitlines():
            row = json.loads(line)
            value = row.get('event', {})
            diagnostic = row.get('text') or value.get('item', {}).get('message', '')
            if 'fallback' in diagnostic.lower() and ('model' in diagnostic.lower() or 'metadata' in diagnostic.lower()):
                rows.append({'path': str(source), 'perf_ns': row['perf_ns'], 'warning': diagnostic})
            if '_meta' in value:
                actual.append({'path': str(source), 'perf_ns': row['perf_ns'], '_meta': value['_meta']})
    return {'requested_model': proof['model'], 'requested_effort': proof['reasoning_effort'],
            'requested_service_tier': proof['service_tier'], 'requested_cli_overrides_and_argv': record['frozen_cli_argv'],
            'actual_meta': actual or None, 'fallback_diagnostics': rows,
            'fallback_state': 'observed' if rows else 'unobserved',
            'metadata_scope': 'Original public CLI JSONL event metadata and original fallback diagnostics. Provider identity, image tokens, and financial charges are unmeasured.',
            'provider_requests': None, 'image_tokens': None, 'cash_fees': None}


def consume_slot(*, slot_id, group, slot_root, endpoint, owner_output, deadline_ns, owned_deadline_ns,
                 model_consumer_enabled=False):
    if (slot_id, group) not in SLOTS or model_consumer_enabled is not True:
        raise ValueError('root_explicit_registered_slot_gate')
    if (type(deadline_ns) is not int or type(owned_deadline_ns) is not int
            or not time.perf_counter_ns() < deadline_ns < owned_deadline_ns):
        raise ValueError('original_absolute_task_and_owned_deadlines')
    if json.loads(Path(endpoint).read_bytes())['chain_deadline_ns'] != deadline_ns:
        raise ValueError('owner_original_task_deadline_binding')
    turn, proof = consumer_adapter()
    slot_root = Path(slot_root).resolve()
    folder, workspace = slot_root / 'consumer', slot_root / 'workspace'
    cell = {'endpoint': str(Path(endpoint).resolve()), 'group': group, 'audit_dir': str(Path(owner_output).resolve())}
    record = turn(episode_id='M4-LIVE-ASSEMBLY-RELATION-TASK-001-' + slot_id, turn_index=1, folder=folder,
        work=workspace, cell=cell, install={'python': str(BASE)}, plan={'model_consumer_enabled': True},
        prompt=PROMPT.read_bytes(), episode_deadline_ns=deadline_ns, turn_deadline_ns=deadline_ns,
        expected_thread_id=None)
    configuration = metadata(folder, proof, record)
    save(folder / 'ACTUAL_CONFIGURATION.json', configuration)
    evidence_time = record.get('archive', {}).get('first_CLI_nonempty_successful_evidence_ns')
    answer_time = record.get('final_received_ns')
    return {'slot_id': slot_id, 'group': group, 'status': record['status'], 'consumer_path': str(folder),
            'consumer_record': str(folder / 'CONSUMER.json'), 'consumer': record, 'adapter_proof': proof,
            'model_configuration': configuration, 'prompt_sha256': sha(PROMPT),
            'first_CLI_nonempty_successful_evidence_to_final_ns': (answer_time - evidence_time
                if evidence_time is not None and answer_time is not None and answer_time >= evidence_time else None)}
