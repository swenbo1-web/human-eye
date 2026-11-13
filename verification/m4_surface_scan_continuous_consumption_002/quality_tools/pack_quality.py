"""Offline eighteen-slot quality handoff. No execution or content scoring."""

import argparse
import copy
import importlib.util
from pathlib import Path
import re
import zipfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CYCLE = 'M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-002'
CELLS = ('N1', 'C1', 'C2', 'N2', 'N3', 'C3')
LABELS = ('BASE', 'REPEAT', 'EDIT')
OLD_PACK = ROOT / 'verification/m4_surface_scan_compact_consumption_001/runtime/pack_quality.py'
OLD_EPISODE = ROOT / 'verification/m4_surface_scan_continuity_001_fix1/consumer/episode.py'
OLD_SCORING = ROOT / 'verification/m4_surface_scan_compact_consumption_001/scoring'
QUALIFICATION = ROOT / 'verification/m4_surface_scan_001/qualification'
MATERIALS = {
    'BASE_TRUTH.json': 'a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7',
    'EDIT_TRUTH.json': 'ccbc66e4071dd3fc8f7fc4c7195e29a6a5a58db39fa1e0a86457b2a8929b1e91',
    'BASE_SNAPSHOT.json': 'f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b',
    'EDIT_SNAPSHOT.json': 'beb4e441b1898c6aedbe633828b1a93948f1d5be172ded9e1a884c8bdebffd80',
}
PROMPTS = (
    ('PROMPT_T1.txt', '6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc'),
    ('PROMPT_T2_T3.txt', '1556e86013d52b1ca222237f6e5df33d389d33e95c8e3df3bd218edb4e5549d6'),
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load('_continuous_quality_pack_reuse', OLD_PACK)
episode = load('_continuous_quality_episode_reuse', OLD_EPISODE)
decode, encoded, sha, put = pack.decode, pack.encoded, pack.sha, pack.put


def read_json(path):
    return decode(Path(path).read_bytes())


def validate_mapping(value):
    if value.get('schema') != 'continuous_anonymous_map_v1':
        raise ValueError('anonymous_map_schema')
    rows = value['rows']
    if [row['cell'] for row in rows] != list(CELLS):
        raise ValueError('fixed_six_dispatch_slots')
    identifiers = []
    for row in rows:
        if row['group'] != row['cell'][0] or row['pair'] != int(row['cell'][1]):
            raise ValueError('anonymous_map_cell_binding')
        if not re.fullmatch(r'episode_[0-9a-f]{16}', row['anonymous_episode_id']):
            raise ValueError('anonymous_episode_format')
        if len(row['anonymous_turn_ids']) != 3:
            raise ValueError('three_anonymous_turns')
        if any(not re.fullmatch(r'answer_[0-9a-f]{16}', item) for item in row['anonymous_turn_ids']):
            raise ValueError('anonymous_turn_format')
        identifiers.extend([row['anonymous_episode_id'], *row['anonymous_turn_ids']])
    if len(set(identifiers)) != 24:
        raise ValueError('anonymous_identifiers_unique')
    return rows


class OriginalSources:
    """Verify complete driver originals and read only archive-bound members."""

    def __init__(self, row):
        self.row = row
        self.runtime = Path(row['runtime_folder']).resolve()
        self.folder = Path(row['folder']).resolve()
        self.notes = []
        self.members = {}
        self.used = {}
        self.archive = None
        self.binding = {'runtime_folder': str(self.runtime), 'folder': str(self.folder)}
        archive_path = self.folder / 'ORIGINALS.zip'
        manifest_path = self.folder / 'RUNTIME_MANIFEST.json'
        if not archive_path.exists() or not manifest_path.exists():
            self.notes.append('outer_originals_or_manifest_missing')
            for path in sorted(self.runtime.rglob('*')):
                if path.is_file():
                    if path.is_symlink():
                        raise ValueError('unsealed_original_symlink')
                    raw = path.read_bytes()
                    self.members[self.member(path)] = {'bytes': len(raw), 'sha256': sha(raw)}
            self.binding.update(archive_status='missing_or_incomplete', members=self.members)
            return
        archive_raw = archive_path.read_bytes()
        manifest_raw = manifest_path.read_bytes()
        manifest = decode(manifest_raw)
        self.binding.update(archive_sha256=sha(archive_raw), manifest_sha256=sha(manifest_raw))
        if manifest.get('archive_sha256') != sha(archive_raw):
            self.notes.append('outer_archive_digest_mismatch')
        if Path(manifest['runtime_folder']).resolve() != self.runtime:
            self.notes.append('outer_manifest_runtime_binding')
        if Path(manifest['archive']).resolve() != archive_path:
            self.notes.append('outer_manifest_archive_binding')
        self.archive = zipfile.ZipFile(archive_path)
        names = self.archive.namelist()
        if len(names) != len(set(names)) or any(
            name.startswith('/') or '\\' in name or '..' in Path(name).parts for name in names
        ):
            raise ValueError('unsafe_or_duplicate_original_archive_members')
        for name in names:
            raw = self.archive.read(name)
            self.members[name] = {'bytes': len(raw), 'sha256': sha(raw)}
        if manifest.get('members') != self.members:
            self.notes.append('outer_manifest_member_inventory_mismatch')
        self.binding['members'] = self.members
        self.binding['archive_status'] = 'present'
        actual_members = {path.relative_to(self.runtime).as_posix() for path in self.runtime.rglob('*') if path.is_file()}
        if actual_members != set(self.members):
            self.notes.append('runtime_and_archive_inventory_mismatch')
        for name in sorted(actual_members & set(self.members)):
            self.get(self.runtime / name)

    def member(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.runtime):
            raise ValueError('source_outside_owned_runtime')
        return path.relative_to(self.runtime).as_posix()

    def get(self, path):
        name = self.member(path)
        if name not in self.members:
            return None
        if self.archive is None:
            raw = (self.runtime / name).read_bytes()
            if {'bytes': len(raw), 'sha256': sha(raw)} != self.members[name]:
                self.notes.append('unsealed_source_changed:' + name)
        else:
            raw = self.archive.read(name)
        self.used[name] = self.members[name]
        actual = self.runtime / name
        if actual.exists() and (actual.is_symlink() or actual.read_bytes() != raw):
            self.notes.append('runtime_differs_from_archive:' + name)
        return raw

    def json(self, path):
        raw = self.get(path)
        return None if raw is None else decode(raw)

    def close(self):
        if self.archive is not None:
            self.archive.close()


def anonymous_error(value, contexts, raw, removals, pointer='$'):
    """Known error envelopes only. Business error data remains intact."""
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    if 'event' in value and 'perf_ns' in value:
        result = pack.without_admin_fields(value, raw, removals, pointer=pointer, fields=('perf_ns',))
        result['event'] = anonymous_error(result['event'], contexts, raw, removals, pointer + '/event')
        return result
    result = pack.without_admin_fields(value, raw, removals, pointer=pointer, fields=('traceback',))
    if result.get('type') in ('error', 'turn.failed'):
        # These are CLI events. Nested error/message/data belong to the provider.
        result = pack.without_admin_fields(result, raw, removals, pointer=pointer,
            fields=('usage', 'timestamp', 'perf_ns', 'argv', 'episode_id'))
        for key in ('thread_id', 'expected_thread_id', 'observed_thread_id'):
            if key in result:
                result[key] = contexts.alias(result[key])
    if result.get('type') == 'resume_thread_mismatch':
        for key in ('expected', 'observed'):
            result[key] = contexts.alias(result.get(key))
    return result


class Contexts:
    def __init__(self):
        self.identities = []

    def alias(self, value):
        if value is None:
            return None
        if value not in self.identities:
            self.identities.append(value)
        return 'context_' + str(self.identities.index(value) + 1)

    def private(self):
        return [{'anonymous_context': self.alias(value), 'original_value_sha256': sha(encoded(value))}
                for value in self.identities]


def project_errors(errors, contexts, raw, removals):
    return [anonymous_error(value, contexts, raw, removals, '$/errors/' + str(index))
            for index, value in enumerate(errors or [])]


def archived_events(sources, folder):
    raw = sources.get(folder / 'events.jsonl') or b''
    return raw, [decode(line)['event'] for line in raw.splitlines()]


def partial_business_projection(sources, turn, owner, destination):
    """Same explicit old projections for an entered turn without CONSUMER."""
    destination.mkdir()
    folder = Path(turn['folder'])
    raw_events, events = archived_events(sources, folder)
    public_events = []
    for line, event in zip(raw_events.splitlines(), events):
        item = event.get('item', {})
        if event.get('type') in ('item.started', 'item.completed') and item.get('type') in pack.TOOL_TYPES:
            public_events.append({'order': len(public_events) + 1, 'phase': event['type'],
                'event': {key: copy.deepcopy(item[key]) for key in (
                    'type', 'tool', 'server', 'arguments', 'result', 'error', 'status', 'command') if key in item},
                'source_sha256': sha(raw_events), 'source_line_sha256': sha(line)})
    boundary = turn.get('status_before', {}).get('business_attempts')
    before = 0 if boundary is None else boundary
    numbers = [int(Path(name).parts[1].removeprefix('tool_')) for name in sources.members
               if len(Path(name).parts) >= 3 and Path(name).parts[0] == owner.name
               and re.fullmatch(r'tool_\d+', Path(name).parts[1])]
    after = turn.get('status_after', {}).get('business_attempts', max([before, *numbers]))
    removals, attempts = [], []
    for number in range(before + 1, after + 1):
        call = {'order': number - before, 'request': None, 'responses': [], 'is_error': None,
                'owner_exception': None, 'source_files': []}
        for name in ('REQUEST.json', 'RESPONSE.json', 'ERROR_RESPONSE.json', 'ATTEMPT.json'):
            raw = sources.get(owner / ('tool_' + str(number).zfill(2)) / name)
            if raw is None:
                continue
            value = decode(raw)
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
    evidence = {'owner_attempts': attempts, 'public_tool_events': public_events,
        'owner_attempt_attribution': 'unknown_start_boundary; all available owner attempts retained' if boundary is None else 'recorded_turn_boundary',
        'scope': 'Actual owner records and consumer-visible events are independently bound; no missing delivery is inferred.'}
    put(destination / 'tool_evidence.json', encoded(evidence))
    final_raw = sources.get(folder / 'PUBLIC_FINAL.txt')
    if final_raw is not None:
        put(destination / 'answer.txt', final_raw)
    return {'administrative_projections': removals, 'partial_turn': True,
            'published_tool_evidence_sha256': sha(encoded(evidence))}


def turn_projection(sources, turn, anon, index, destination, owner, contexts):
    record = turn.get('consumer')
    folder = Path(turn['folder'])
    disk_raw = sources.get(folder / 'CONSUMER.json')
    disk = None if disk_raw is None else decode(disk_raw)
    removals, issues = [], []
    if record is None:
        record = disk
    if record is None:
        record = {}
    if disk is None:
        issues.append('consumer_record_missing_for_entered_turn')
    elif any(record.get(key) != disk.get(key) for key in ('final', 'errors', 'thread_id', 'expected_thread_id')):
        issues.append('coordinator_consumer_binding_mismatch')
    # Reuse the actual FIX1 projection after checking every byte it will read.
    required = [path for path in folder.rglob('*') if path.is_file()] if folder.exists() else []
    for path in required:
        if sources.get(path) is None:
            issues.append('live_turn_source_unarchived:' + path.relative_to(folder).as_posix())
    for name in sources.members:
        if name.startswith(owner.name + '/tool_'):
            sources.get(sources.runtime / name)
    if disk is not None and folder.is_dir() and not sources.notes and not issues:
        projection = episode.project_turn(turn, record, owner, destination)
    else:
        projection = partial_business_projection(sources, turn, owner, destination)
    final_raw = sources.get(folder / 'PUBLIC_FINAL.txt')
    _, events = archived_events(sources, folder)
    messages = [event['item'].get('text') for event in events
                if event.get('type') == 'item.completed' and event.get('item', {}).get('type') == 'agent_message']
    if final_raw is not None and (not messages or not isinstance(messages[-1], str)
                                  or messages[-1].encode('utf8') != final_raw):
        issues.append('public_final_event_binding')
    if final_raw is not None and record.get('final') != final_raw.decode('utf8'):
        issues.append('consumer_public_final_binding')
    if final_raw is None:
        for number, text in enumerate(messages, 1):
            if isinstance(text, str):
                put(destination / ('unconfirmed_public_message_' + str(number) + '.txt'), text.encode('utf8'))
        if isinstance(record.get('final'), str):
            put(destination / 'consumer_final_unconfirmed.txt', record['final'].encode('utf8'))
    cli_output = sources.get(folder / 'final.txt')
    if cli_output is not None:
        put(destination / 'cli_output_unconfirmed.txt', cli_output)
    observed = record.get('thread_id')
    expected = record.get('expected_thread_id', turn.get('expected_thread_id'))
    thread_events = [event.get('thread_id') for event in events if event.get('type') == 'thread.started']
    thread_bound = len(thread_events) == 1 and thread_events[0] == observed and observed is not None
    resume_uuid_bound = None if expected is None else expected in record.get('frozen_cli_argv', [])
    if index > 1 and (expected is None or expected != observed or resume_uuid_bound is not True):
        issues.append('explicit_resume_identity_binding')
    timing = sources.json(folder / 'FINAL_TIMING.json')
    valid = (record.get('valid_completion') is True and disk is not None and final_raw is not None
             and timing is not None and timing.get('accepted_success') is True
             and thread_bound and not record.get('errors') and not record.get('unexpected_tool_deviations')
             and not issues)
    summary = record.get('summary') or {}
    error_source = disk_raw or encoded(record)
    value = {'anonymous_turn_id': anon, 'turn_index': index, 'turn_label': LABELS[index - 1],
        'execution_state': 'completed' if valid else 'failed', 'valid_completion': valid,
        'recorded_valid_completion': record.get('valid_completion'),
        'recorded_summary_execution_state': summary.get('execution_state'),
        'final_present': final_raw is not None, 'content_quality': 'unscored',
        'errors': project_errors(record.get('errors'), contexts, error_source, removals),
        'summary_errors': project_errors(summary.get('errors'), contexts, error_source, removals),
        'bridge_protocol_errors': project_errors(record.get('bridge_protocol_errors'), contexts, error_source, removals),
        'public_error_events': project_errors([event for event in events if event.get('type') in ('error', 'turn.failed')],
                                              contexts, error_source, removals),
        'continuity': {'observed_context': contexts.alias(observed), 'expected_context': contexts.alias(expected),
            'expected_matches_observed': None if expected is None or observed is None else expected == observed,
            'observed_context_matches_events': thread_bound,
            'resume_requested': None if not record else 'resume' in record.get('frozen_cli_argv', []),
            'recorded_resume_uuid_matches_expected': resume_uuid_bound},
        'execution_checks': {key: copy.deepcopy(record.get(key)) for key in (
            'process_reaped', 'readers_stopped', 'safe_to_continue', 'mutation_unknown')},
        'consumer_publication_accepted': None if timing is None else timing.get('accepted_success'),
        'source_consistency_issues': issues,
        'current_state_evidence': 'unscored; use this turn business evidence, independently of administrative QA'}
    put(destination / 'TURN.json', encoded(value))
    return value, {'business_projection': projection, 'administrative_projections': removals,
        'turn_folder': str(folder), 'record_member': sources.member(folder / 'CONSUMER.json'),
        'final_member': sources.member(folder / 'PUBLIC_FINAL.txt'),
        'consumer_record_sha256': None if disk_raw is None else sha(disk_raw),
        'answer_sha256': None if final_raw is None else sha(final_raw)}


def not_run_turn(anon, index, destination):
    destination.mkdir()
    value = {'anonymous_turn_id': anon, 'turn_index': index, 'turn_label': LABELS[index - 1],
        'execution_state': 'not_run', 'valid_completion': False, 'final_present': False,
        'content_quality': 'unscored', 'errors': [], 'summary_errors': [], 'public_error_events': [],
        'continuity': {'observed_context': None, 'expected_context': None,
                       'expected_matches_observed': None, 'observed_context_matches_events': None,
                       'resume_requested': None, 'recorded_resume_uuid_matches_expected': None},
        'source_consistency_issues': [], 'current_state_evidence': 'unscored; planned slot did not run'}
    put(destination / 'TURN.json', encoded(value))
    put(destination / 'tool_evidence.json', encoded({'owner_attempts': [], 'public_tool_events': [],
                                                  'scope': 'Planned slot did not run.'}))
    return value


def project_episode(mapping, outer, public):
    anon = mapping['anonymous_episode_id']
    destination = public / anon
    destination.mkdir()
    contexts, removals = Contexts(), []
    sources = None if outer is None else OriginalSources(outer)
    private = {'cell': mapping['cell'], 'anonymous_episode_id': anon, 'turns': []}
    coordinator = {} if outer is None else outer.get('coordinator') or {}
    outer_timing = None
    if sources is not None:
        timing_path = sources.folder / 'FINAL_TIMING.json'
        if timing_path.exists():
            timing_raw = timing_path.read_bytes()
            outer_timing = decode(timing_raw)
            private['outer_timing_sha256'] = sha(timing_raw)
            if outer.get('timing') != outer_timing:
                sources.notes.append('outer_timing_run_result_binding')
            if outer.get('outer_valid_completion') != outer_timing.get('outer_valid_completion'):
                sources.notes.append('outer_completion_timing_binding')
        else:
            sources.notes.append('outer_authoritative_timing_missing')
        private['outer_receipts'] = {path.name: {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
            for path in sorted(sources.folder.glob('*.json')) if path.is_file()}
        coordinator_path = Path(outer['consumer_output']) / 'EPISODE_RESULT.json'
        archived = sources.json(coordinator_path)
        if archived is not None:
            if coordinator and coordinator != archived:
                # Returned coordinator includes final timing added after EPISODE_RESULT publication.
                stable = ('turns', 'errors', 'within_episode_deadline', 'qualified_execution', 'owner_finish')
                if any(coordinator.get(key) != archived.get(key) for key in stable):
                    sources.notes.append('outer_coordinator_record_mismatch')
            coordinator = archived
    turns = coordinator.get('turns', [])
    if len(turns) > 3 or any(turn.get('turn_index', index) != index for index, turn in enumerate(turns, 1)):
        raise ValueError('recorded_turns_must_be_fixed_prefix')
    projected = []
    try:
        for index, turn_anon in enumerate(mapping['anonymous_turn_ids'], 1):
            turn_destination = destination / ('turn_' + str(index))
            if index <= len(turns):
                turn = turns[index - 1]
                if turn['turn_label'] != LABELS[index - 1]:
                    raise ValueError('turn_label_binding')
                if 'turn_index' not in turn:
                    sources.notes.append('recovered_turn_index_from_fixed_label:' + str(index))
                    turn = dict(turn, turn_index=index)
                owner = Path(outer.get('owner_output', str(sources.runtime / 'owner')))
                value, binding = turn_projection(sources, turn, turn_anon, index, turn_destination, owner, contexts)
                private['turns'].append(binding)
            else:
                value = not_run_turn(turn_anon, index, turn_destination)
                private['turns'].append({'not_run': True})
            projected.append(value)
        raw = encoded(coordinator)
        outer_errors = [] if outer is None else outer.get('errors', [])
        outer_valid = None if outer_timing is None else outer_timing.get('outer_valid_completion')
        episode_valid = (outer_valid is True and not outer_errors and not coordinator.get('errors')
            and all(turn['valid_completion'] for turn in projected) and not sources.notes)
        value = {'anonymous_episode_id': anon, 'planned_turns': 3, 'turns': projected,
            'entered': outer is not None,
            'execution_state': 'not_run' if outer is None else 'completed' if episode_valid else 'execution_failure',
            'valid_completion': episode_valid,
            'counts': {state: sum(turn['execution_state'] == state for turn in projected)
                       for state in ('completed', 'failed', 'not_run')},
            'coordinator_errors': project_errors(coordinator.get('errors'), contexts, raw, removals),
            'outer_errors': project_errors(outer_errors, contexts, encoded(outer), removals),
            'coordinator_qualified_execution': coordinator.get('qualified_execution'),
            'outer_valid_completion': outer_valid,
            'outer_execution_counts': None if outer is None else outer.get('execution_counts'),
            'coordinator_within_original_deadline': coordinator.get('within_episode_deadline'),
            'owner_close_confirmed': coordinator.get('owner_finish', {}).get('confirmed'),
            'all_three_observed_same_context': (len(contexts.identities) == 1
                and all(turn['continuity']['observed_context_matches_events'] is True for turn in projected)),
            'content_quality': 'unscored',
            'source_consistency_issues': [] if sources is None else list(dict.fromkeys(sources.notes)),
            'scope': 'Administrative execution evidence only. State basis requires actual consumer business evidence.'}
        put(destination / 'EPISODE.json', encoded(value))
        private.update(contexts=contexts.private(), administrative_projections=removals,
            original_sources=None if sources is None else sources.binding,
            used_sources={} if sources is None else sources.used,
            source_issues=[] if sources is None else list(dict.fromkeys(sources.notes)),
            outer_record_sha256=None if outer is None else sha(encoded(outer)))
        return value, private
    finally:
        if sources is not None:
            sources.close()


def scoring_materials(batch, public):
    hashes = {}
    for name, digest in MATERIALS.items():
        raw = (QUALIFICATION / name).read_bytes()
        if sha(raw) != digest:
            raise ValueError('frozen_quality_material_digest:' + name)
        put(public / 'scoring' / name, raw)
        hashes['scoring/' + name] = digest
    for name, digest in PROMPTS:
        raw = (batch / 'inputs' / name).read_bytes()
        if sha(raw) != digest:
            raise ValueError('frozen_prompt_digest:' + name)
        put(public / 'tasks' / name, raw)
        hashes['tasks/' + name] = digest
    for source, name in ((OLD_SCORING / 'SCORING_CONTRACT.json', 'BASE_SCORING_CONTRACT.json'),
                         (OLD_SCORING / 'score_answer.py', 'score_answer.py'),
                         (HERE / 'SCORING_CONTRACT.json', 'SCORING_CONTRACT.json')):
        raw = source.read_bytes()
        put(public / 'scoring' / name, raw)
        hashes['scoring/' + name] = sha(raw)
    return hashes


def pack_batch(*, batch, run_result, mapping_path, output):
    batch, mapping_path, output = Path(batch).resolve(), Path(mapping_path).resolve(), Path(output).resolve()
    result_path = Path(run_result).resolve()
    result_raw, mapping_raw = result_path.read_bytes(), mapping_path.read_bytes()
    result, mapping = decode(result_raw), decode(mapping_raw)
    rows = validate_mapping(mapping)
    plan_raw = (batch / 'PLAN.json').read_bytes()
    plan = decode(plan_raw)
    if plan.get('anonymous_map_sha256') != sha(mapping_raw):
        raise ValueError('frozen_mapping_digest')
    if plan.get('cycle') != CYCLE:
        raise ValueError('batch_cycle')
    for frozen, row in zip(plan['sequence'], rows):
        if any(frozen.get(key) != row.get(key) for key in (
                'cell', 'group', 'pair', 'anonymous_episode_id', 'anonymous_turn_ids')):
            raise ValueError('frozen_plan_map_binding')
    records = result.get('records', [])
    if [row['cell'] for row in records] != list(CELLS[:len(records)]) or len(records) > 6:
        raise ValueError('entered_episodes_must_be_frozen_prefix')
    by_cell = {row['cell']: row for row in records}
    for row in rows:
        record = by_cell.get(row['cell'])
        if record is not None and (record['group'] != row['group'] or record['pair'] != row['pair']
                or record['anonymous_episode_id'] != row['anonymous_episode_id']):
            raise ValueError('outer_anonymous_mapping_binding')
    output.mkdir(parents=True, exist_ok=False)
    public, private_dir = output / 'public', output / 'private'
    public.mkdir()
    private_dir.mkdir()
    material_hashes = scoring_materials(batch, public)
    episodes, private = [], []
    for row in sorted(rows, key=lambda item: item['anonymous_episode_id']):
        value, binding = project_episode(row, by_cell.get(row['cell']), public)
        episodes.append(value)
        private.append(binding)
    batch_removals = []
    batch_errors = project_errors([*result.get('errors', []), *result.get('publication_errors', [])],
                                  Contexts(), result_raw, batch_removals)
    index = {'schema': 'continuous_quality_handoff_v1', 'cycle': CYCLE,
        'planned_episodes': 6, 'planned_turns': 18,
        'anonymous_episode_order': [item['anonymous_episode_id'] for item in episodes],
        'episodes': [{'anonymous_episode_id': item['anonymous_episode_id'], 'counts': item['counts'],
                      'entered': item['entered'], 'execution_state': item['execution_state'],
                      'valid_completion': item['valid_completion'],
                      'all_three_observed_same_context': item['all_three_observed_same_context']}
                     for item in episodes],
        'counts': {state: sum(item['counts'][state] for item in episodes) for state in ('completed', 'failed', 'not_run')},
        'episode_counts': {state: sum(item['execution_state'] == state for item in episodes)
                           for state in ('completed', 'execution_failure', 'not_run')},
        'fixed_quality_materials': material_hashes, 'content_quality': 'unscored',
        'batch_errors': batch_errors,
        'batch_stop_reason_codes': [item.get('reason') for item in result.get('stop_reasons', [])],
        'administrative_projection': 'Group mapping, raw thread identity, times, usage, argv and administrative paths are private.',
        'blinding_limit': 'Actual tool content and original error messages can reveal route. Business text is preserved.',
        'scope': 'Eighteen frozen slots. Primary current-list content, auxiliary contextual reconstruction, current-state basis and execution are independent.'}
    put(public / 'INDEX.json', encoded(index))
    put(public / 'README.md', (HERE / 'PUBLIC_README.md').read_bytes())
    inventory = {path.relative_to(public).as_posix(): {'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
                 for path in sorted(public.rglob('*')) if path.is_file()}
    reuse = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in (
        OLD_PACK, OLD_EPISODE, OLD_SCORING / 'SCORING_CONTRACT.json', OLD_SCORING / 'score_answer.py')}
    binding = {'schema': 'continuous_quality_private_binding_v1', 'cycle': CYCLE,
        'batch': str(batch), 'run_result_path': str(result_path), 'run_result_sha256': sha(result_raw),
        'mapping_path': str(mapping_path), 'mapping_sha256': sha(mapping_raw), 'mapping': mapping,
        'plan_sha256': sha(plan_raw), 'episodes': private, 'public_files': inventory,
        'batch_administrative_projections': batch_removals,
        'reused_sources': reuse, 'pack_source_sha256': sha(Path(__file__).read_bytes()),
        'quality': 'unscored', 'cost_unsealed': False}
    put(private_dir / 'BINDING.json', encoded(binding))
    archive = output / 'ANONYMOUS_QUALITY.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in inventory:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 0
            entry.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(entry, (public / name).read_bytes())
    receipt = {'schema': 'continuous_quality_package_receipt_v1', 'archive': str(archive),
        'archive_sha256': sha(archive.read_bytes()), 'private_binding_sha256': sha(encoded(binding)),
        'public_files': len(inventory), 'planned_episodes': 6, 'planned_turns': 18,
        'counts': index['counts'], 'quality': 'unscored', 'cost_unsealed': False,
        'source_consistency_issues': {item['anonymous_episode_id']: item['source_issues']
                                      for item in private if item['source_issues']}}
    put(output / 'PACKAGE_RECEIPT.json', encoded(receipt))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--run-result', type=Path, required=True)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = pack_batch(batch=args.batch, run_result=args.run_result, mapping_path=args.mapping, output=args.output)
    print(encoded(receipt).decode(), end='')
