"""Fixed three-turn consumption coordinator with one externally owned backend."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import traceback


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
ROOT = BATCH.parents[1]
TURNS = ('BASE', 'REPEAT', 'EDIT')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transport = load('_fix1_consumer_loop', BATCH / 'runtime/consumer_transport.py')
cli = load('_fix1_continuity_cli', ROOT / 'verification/m4_surface_scan_continuity_001/cli/continuity_cli.py')
pack = load('_fix1_quality_projection', ROOT / 'verification/m4_surface_scan_compact_consumption_001/runtime/pack_quality.py')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_bytes(pack.encoded(value))


def identity(status):
    return {key: copy.deepcopy(status[key]) for key in (
        'episode_id', 'owner_pid', 'native_pid', 'native_host', 'native_port', 'native_workspace',
        'product_launcher_pid', 'product_runtime_proof', 'session_id', 'worker_deadline_ns')}


def project_turn(turn, consumer, owner, destination):
    """Bind actual event and owner bytes, using the existing business projection."""
    destination.mkdir()
    folder = Path(turn['folder'])
    removals = []
    events = []
    raw_events = (folder / 'events.jsonl').read_bytes() if (folder / 'events.jsonl').exists() else b''
    for line in raw_events.splitlines():
        event = pack.decode(line)['event']
        item = event.get('item', {})
        if event.get('type') in ('item.started', 'item.completed') and item.get('type') in pack.TOOL_TYPES:
            events.append({'order': len(events) + 1, 'phase': event['type'],
                           'event': {key: copy.deepcopy(item[key]) for key in (
                               'type', 'tool', 'server', 'arguments', 'result', 'error', 'status', 'command') if key in item},
                           'source_sha256': sha(raw_events), 'source_line_sha256': sha(line)})
    before = turn['status_before']['business_attempts']
    after = turn.get('status_after', {}).get('business_attempts')
    if after is None:
        after = max([before] + [int(path.name.removeprefix('tool_')) for path in owner.glob('tool_*') if path.is_dir()])
    attempts = []
    for number in range(before + 1, after + 1):
        call = {'order': number - before, 'request': None, 'responses': [], 'is_error': None,
                'owner_exception': None, 'source_files': []}
        for name in ('REQUEST.json', 'RESPONSE.json', 'ERROR_RESPONSE.json', 'ATTEMPT.json'):
            source = owner / ('tool_' + str(number).zfill(2)) / name
            if not source.exists():
                continue
            raw = source.read_bytes()
            value = pack.decode(raw)
            call['source_files'].append({'kind': name, 'original_sha256': sha(raw)})
            if name == 'REQUEST.json':
                call['request'] = pack.request_projection(value, raw, removals)
            elif name == 'ATTEMPT.json':
                call['is_error'] = value.get('is_error')
                call['owner_exception'] = pack.without_admin_fields(value.get('exception'), raw, removals,
                    pointer='$/exception', fields=('traceback',))
            else:
                call['responses'].append({'kind': name, 'value': pack.without_rpc_envelope(value, raw, removals)})
        call['request_missing'] = call['request'] is None
        call['response_missing'] = not call['responses']
        attempts.append(call)
    value = {'owner_attempts': attempts, 'public_tool_events': events,
             'scope': 'Actual owner records and consumer-visible events are independently bound; no missing delivery is inferred.'}
    save(destination / 'tool_evidence.json', value)
    final_path = folder / 'PUBLIC_FINAL.txt'
    if final_path.exists():
        (destination / 'answer.txt').write_bytes(final_path.read_bytes())
    sources = {}
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            raw = path.read_bytes()
            sources[path.relative_to(folder).as_posix()] = {'bytes': len(raw), 'sha256': sha(raw)}
    return {'turn_index': turn['turn_index'], 'source_files': sources,
            'owner_attempt_range': [before + 1, after], 'administrative_projections': removals,
            'consumer_record_sha256': sha((folder / 'CONSUMER.json').read_bytes()),
            'public_final_sha256': sha(final_path.read_bytes()) if final_path.exists() else None,
            'published_tool_evidence_sha256': sha((destination / 'tool_evidence.json').read_bytes()),
            'scope': 'Private binding for this fixed turn; quality remains unscored.'}


def run_episode(*, episode_id, output, work, cell, install, plan, prompts,
                episode_deadline_ns, turn_budget_ns, control, finish,
                anonymous_episode_id, local_cli=None):
    """Use the real consume loop, explicit resume and one final owner cleanup.

    control and finish are the existing outer-owner operations. The coordinator
    never creates a backend or replaces a failed context. Provider execution
    remains gated inside consume_turn; local_cli is the zero-provider fixture.
    """
    if len(prompts) != 3 or prompts[1] != prompts[2]:
        raise ValueError('fixed_three_common_prompts')
    if type(episode_deadline_ns) is not int or type(turn_budget_ns) is not int or turn_budget_ns <= 0:
        raise ValueError('original_absolute_deadline_required')
    output, work = Path(output), Path(work)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'turns').mkdir()
    started = time.perf_counter_ns()
    result = {'episode_id': episode_id, 'started_ns': started, 'episode_deadline_ns': episode_deadline_ns,
              'turns': [], 'errors': [], 'usage_aggregation': None,
              'usage_semantics': 'unconfirmed_turn_or_session_scope', 'model_continuity_attestation': 'pending_actual_consumer',
              'mode': 'local_synthetic_processes' if local_cli is not None else 'provider_gated',
              'new_provider_calls': 0 if local_cli is not None else None}
    expected_thread = None
    endpoint_path = Path(cell['endpoint'])
    endpoint_bytes = endpoint_path.read_bytes()
    initial_identity = None
    try:
        initial = control('status')
        initial_identity = identity(initial)
        for index, label in enumerate(TURNS, 1):
            if time.perf_counter_ns() >= episode_deadline_ns:
                raise TimeoutError('original_episode_deadline')
            if label == 'EDIT':
                result['registered_pose'] = control('qa_advance')
            before = control('status')
            if identity(before) != initial_identity or endpoint_path.read_bytes() != endpoint_bytes:
                raise ValueError('episode_backend_identity_changed')
            deadline = min(episode_deadline_ns, time.perf_counter_ns() + turn_budget_ns)
            control('begin_turn', turn_id=label, deadline_ns=deadline)
            folder = output / 'turns' / label
            row = {'turn_index': index, 'turn_label': label, 'folder': str(folder),
                   'deadline_ns': deadline, 'status_before': before, 'expected_thread_id': expected_thread}
            result['turns'].append(row)
            record = transport.consume_turn(episode_id=episode_id, turn_index=index, folder=folder,
                work=work, cell=cell, install=install, plan=plan, prompt=prompts[index - 1],
                episode_deadline_ns=episode_deadline_ns, turn_deadline_ns=deadline,
                expected_thread_id=expected_thread, local_cli=local_cli)
            row['consumer'] = record
            if record['safe_to_continue']:
                row['status_after'] = control('end_turn', turn_id=label)
                if identity(row['status_after']) != initial_identity or endpoint_path.read_bytes() != endpoint_bytes:
                    raise ValueError('episode_backend_identity_changed')
            save(output / ('TURN_' + label + '.json'), row)
            if not record['valid_completion'] or not record['safe_to_continue']:
                break
            expected_thread = record['thread_id']
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    finally:
        result['cleanup_started_ns'] = time.perf_counter_ns()
        try:
            result['owner_finish'] = finish()
        except BaseException as error:
            result['errors'].append({'stage': 'owner_finish', 'type': type(error).__name__, 'message': str(error)})
        result['cleanup_ended_ns'] = time.perf_counter_ns()
        result['within_episode_deadline'] = result['cleanup_ended_ns'] < episode_deadline_ns
        summaries = [row['consumer']['summary'] for row in result['turns'] if 'consumer' in row]
        envelope = cli.episode_manifest(episode_id, summaries, anonymous_episode_id)
        quality = output / 'quality'
        public = quality / 'public'
        result['counts'] = envelope['counts']
        result['quality_archive'] = str(quality)
        result['archive_status'] = 'failed'
        try:
            quality.mkdir()
            public.mkdir()
            save(public / 'EPISODE.json', envelope)
            private = []
            for row in result['turns']:
                if 'consumer' in row:
                    private.append(project_turn(row, row['consumer'], Path(cell['audit_dir']),
                                                public / ('turn_' + str(row['turn_index']))))
            consumer_sources = pack.capture_cell(output / 'turns', quality / 'CONSUMER_ORIGINALS.zip')
            owner_sources = pack.capture_cell(Path(cell['audit_dir']), quality / 'OWNER_ORIGINALS.zip')
            binding = {'episode_id': episode_id, 'anonymous_episode_id': anonymous_episode_id,
                       'turn_bindings': private, 'endpoint_sha256': sha(endpoint_bytes),
                       'consumer_originals': {key: sha(raw) for key, raw in consumer_sources.items()},
                       'owner_originals': {key: sha(raw) for key, raw in owner_sources.items()},
                       'consumer_archive_sha256': sha((quality / 'CONSUMER_ORIGINALS.zip').read_bytes()),
                       'owner_archive_sha256': sha((quality / 'OWNER_ORIGINALS.zip').read_bytes()),
                       'public_envelope_sha256': sha((public / 'EPISODE.json').read_bytes()),
                       'usage_aggregation': None, 'quality': 'unscored',
                       'synthetic_fixture': local_cli is not None}
            save(quality / 'PRIVATE_BINDING.json', binding)
            result['archive_status'] = 'completed'
        except BaseException as error:
            failure = {'stage': 'quality_archive', 'type': type(error).__name__,
                       'message': str(error), 'traceback': traceback.format_exc()}
            result['errors'].append(failure)
            try:
                save(quality / 'ARCHIVE_FAILURE.json', failure)
            except OSError as receipt_error:
                failure['failure_receipt_error'] = repr(receipt_error)
        result['qualified_execution'] = bool(not result['errors'] and result['counts']['completed'] == 3
            and result['within_episode_deadline'] and result.get('owner_finish', {}).get('confirmed') is True)
        save(output / 'EPISODE_RESULT.json', result)
        result['business_receipts_closed_ns'] = time.perf_counter_ns()
        result['full_episode_wall_ns'] = result['business_receipts_closed_ns'] - started
        result['qualified_execution'] = result['qualified_execution'] and result['business_receipts_closed_ns'] < episode_deadline_ns
        save(output / 'FINAL_TIMING.json', {'started_ns': started,
            'business_receipts_closed_ns': result['business_receipts_closed_ns'],
            'full_episode_wall_ns': result['full_episode_wall_ns'],
            'episode_deadline_ns': episode_deadline_ns, 'qualified_execution': result['qualified_execution'],
            'scope': 'coordinator, turns, owner cleanup, archives and EPISODE_RESULT write/close; timing publication excluded'})
    return result
