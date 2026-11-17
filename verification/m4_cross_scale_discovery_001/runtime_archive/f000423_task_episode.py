"""Bounded task evidence records. No replay, authorization or training policy.

The trusted embedding records observations; JSON hashes detect corruption, not
authenticity. A negotiated client response never proves a human used a UI.
Records are returned in the tool result, not a durable or acknowledged outbox.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from .task_authority import _spec_from_dict, _scope

SCHEMA = 'owned-task-episode-v1'
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 256 * 1024


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _bytes(value, limit=MAX_DOCUMENT_BYTES):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=True, allow_nan=False).encode('utf8')
    _need(len(raw) <= limit, 'episode_document_budget')
    return raw


def _clone(value):
    return json.loads(_bytes(value))


def _hash(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def task_event_id(connection_id, request_id):
    _need(type(connection_id) is str and 0 < len(connection_id) <= 128,
          'episode_connection_id_required')
    _need((type(request_id) is str and 0 < len(request_id) <= 128) or
          (type(request_id) is int and 0 <= request_id < 2**53),
          'episode_request_id_required')
    return 'call:' + connection_id + ':' + hashlib.sha256(
        json.dumps(request_id).encode('utf8')).hexdigest()[:32]


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def approval_decision(value, expected_id):
    if type(value) is not dict or type(value.get('id')) is not str or value['id'] != expected_id:
        return 'wrong_id'
    if 'error' in value:
        return 'rpc_error'
    result = value.get('result')
    if type(result) is not dict or set(result)-{'action', 'content', '_meta'}:
        return 'invalid_or_false'
    action = result.get('action')
    if action in ('decline', 'cancel'):
        return action
    content = result.get('content')
    return ('accept_true' if action == 'accept' and type(content) is dict and
            set(content) == {'approve'} and content['approve'] is True else 'invalid_or_false')


def _complete_source(binding):
    try:
        # Reuse the original read-only shape validation. This does not issue,
        # claim or reconstruct a TaskGrant or any dispatch capability.
        spec = _spec_from_dict(binding.get('task'))
        _scope(binding.get('scope'), spec)
        return True
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


def _derived(raw):
    result = raw['result']
    admission = raw['admission'] or {}
    binding = raw['binding'] or {}
    proposal = raw['proposal'] or {}
    approved = raw['approval']
    count = result.get('new_setter_count')
    count_known = type(count) is int and count >= 0
    if not raw['execution_started']:
        # Known zero is about this entry's dispatch path, not an independent
        # physical meter covering all scene writers.
        count = 0
        count_known = True
    timing_valid = (_number(raw['received_monotonic']) and
                    _number(raw['finished_monotonic']) and
                    raw['finished_monotonic'] >= raw['received_monotonic'])
    resolved = binding.get('task', {})
    same_proposal = (bool(proposal) and set(proposal) == set(resolved) and
                     all(v == resolved[k] for k, v in proposal.items()
                         if k != 'reference_triangle_index') and
                     (proposal.get('reference_triangle_index') is None or
                      proposal['reference_triangle_index'] == resolved.get('reference_triangle_index')))
    binding_complete = (same_proposal and _complete_source(binding) and
                        admission.get('scope') == binding.get('scope') and
                        admission.get('event_id') == raw['event_id'] and
                        admission.get('authorization_id') == approved.get('request_id') and
                        admission.get('original_started_monotonic') == raw['received_monotonic'] and
                        admission.get('persistence') == 'committed' and
                        admission.get('current_scene_revalidated') is True and
                        admission.get('live_registration_available') is True and
                        admission.get('goal_id') == result.get('goal_id') and
                        admission.get('limits') == resolved.get('limits') and
                        _number(admission.get('original_deadline_monotonic')) and
                        admission['original_deadline_monotonic'] ==
                        raw['received_monotonic'] + resolved.get('limits', {}).get('max_duration_s', -1))
    budget = result.get('budget') if type(result.get('budget')) is dict else {}
    historical = result.get('historical_receipt') is True or result.get('replayed') is True
    confirmed = (raw['execution_started'] and not historical and binding_complete and timing_valid and
                 approved.get('decision') == 'accept_true' and
                 approval_decision(approved.get('response'), approved.get('request_id')) == 'accept_true' and
                 result.get('status') == 'completed' and
                 result.get('task_succeeded') is True and
                 result.get('physical_task_succeeded') is True and
                 result.get('host_closed') is True and
                 result.get('execution_phase') == 'physical_completion_verified' and
                 result.get('completion_persistence') == 'committed' and
                 count_known and result.get('engine_confirmed_steps') == count and
                 type(result.get('engine_confirmed_steps')) is int and
                 budget.get('confirmed_steps') == count and
                 type(budget.get('confirmed_steps')) is int and
                 budget.get('started_monotonic') == raw['received_monotonic'] and
                 budget.get('deadline_monotonic') == admission.get('original_deadline_monotonic'))
    if historical:
        outcome = 'historical_receipt'
    elif not raw['execution_started']:
        outcome = ('client_declined' if approved.get('decision') == 'decline' else
                   'client_cancelled' if approved.get('decision') == 'cancel' else 'not_admitted')
    elif confirmed:
        outcome = 'succeeded'
    elif (not count_known or result.get('physical_task_succeeded') is True or
          result.get('task_succeeded') is True or not timing_valid):
        outcome = 'unknown'
    else:
        outcome = 'stopped_or_failed'
    return dict(outcome=outcome, new_setter_count=count if count_known else None,
                count_basis='engine_receipt' if raw['execution_started'] else 'entry_not_dispatched',
                physical_task_succeeded=result.get('physical_task_succeeded'),
                completion_persistence=result.get('completion_persistence',
                    'unknown' if raw['execution_started'] else 'not_attempted'),
                binding_complete=bool(binding_complete), timing_valid=timing_valid,
                success_candidate=bool(confirmed),
                human_UI_verified=False, training_positive=False,
                execution_authority=False, retry_authorized=False,
                delivery='result_constructed_not_client_consumption_proof',
                durability='in_memory_until_consumer_persists')


class TaskEpisode:
    """One receipt-time identity; each later layer is frozen at most once."""
    def __init__(self, connection_id, request_id, arguments, received_monotonic):
        event_id = task_event_id(connection_id, request_id)
        request_bytes = _bytes(arguments, MAX_REQUEST_BYTES)
        self._raw = dict(event_id=event_id, connection_id=connection_id, request_id=request_id,
                         request_sha256=hashlib.sha256(request_bytes).hexdigest(),
                         received_monotonic=received_monotonic,
                         origin='stdio_client_response_human_unverified',
                         proposal=None, binding=None, admission=None,
                         approval=dict(decision='not_requested', request_id=None, response=None),
                         execution_started=False, result=None, finished_monotonic=None)
        self._final = None

    def intake(self):
        self._open()
        fields=('event_id','connection_id','request_id','request_sha256','received_monotonic','origin')
        value={k:self._raw[k] for k in fields}
        if not _number(value['received_monotonic']):value['received_monotonic']=None
        return _clone(value)

    def _open(self):
        _need(self._final is None, 'episode_already_sealed')

    def proposed(self, task):
        self._open()
        _need(self._raw['proposal'] is None, 'episode_proposal_already_frozen')
        self._raw['proposal'] = _clone(task)

    def bind(self, task, scope, approval_request_id):
        self._open()
        _need(self._raw['binding'] is None, 'episode_binding_already_frozen')
        self._raw['binding'] = _clone(dict(task=task, scope=scope))
        self._raw['approval']['request_id'] = approval_request_id
        self._raw['approval']['decision'] = 'requested_no_valid_response'

    def response(self, value, decision):
        self._open()
        _need(self._raw['approval']['response'] is None, 'episode_response_already_frozen')
        _need(decision in ('accept_true', 'decline', 'cancel', 'invalid_or_false', 'rpc_error', 'wrong_id'),
              'episode_unknown_response_decision')
        _need(decision == approval_decision(value, self._raw['approval']['request_id']),
              'episode_response_decision_mismatch')
        self._raw['approval'].update(decision=decision, response=_clone(value))

    def admitted(self, admission):
        self._open()
        _need(self._raw['admission'] is None, 'episode_admission_already_frozen')
        self._raw['admission'] = _clone(admission)

    def execution_started(self):
        self._open()
        self._raw['execution_started'] = True

    def finish(self, result, finished_monotonic):
        self._open()
        self._raw['result'] = _clone(result)
        self._raw['finished_monotonic'] = finished_monotonic
        # Invalid direct-embedding times are represented as missing evidence.
        # Transport times are finite; a rejected NaN proposal must not poison
        # serialization of the already known non-dispatched tool response.
        for key in ('received_monotonic', 'finished_monotonic'):
            if not _number(self._raw[key]):
                self._raw[key] = None
        body = dict(schema=SCHEMA, raw_evidence=_clone(self._raw), derived=_derived(self._raw),
                    conclusions=dict(learned_skill=False, independent_support_count=None))
        body['sha256'] = _hash(body)
        _bytes(body)
        self._final = body
        return copy.deepcopy(body)


def validate_episode(value):
    """Check bounded structure, digest and derivation; never authenticate it."""
    value = _clone(value)
    _need(type(value) is dict and set(value) == {'schema', 'raw_evidence', 'derived', 'conclusions', 'sha256'}
          and value['schema'] == SCHEMA, 'episode_schema_mismatch')
    digest = value.pop('sha256')
    _need(type(digest) is str and digest == _hash(value), 'episode_digest_mismatch')
    try:
        raw = value['raw_evidence']
        _need(raw['event_id'] == task_event_id(raw['connection_id'], raw['request_id']),
              'episode_event_mismatch')
        _need(raw['origin'] == 'stdio_client_response_human_unverified' and
              type(raw['execution_started']) is bool, 'episode_origin_or_phase_invalid')
        approved = raw['approval']
        if approved['response'] is not None:
            _need(approved['decision'] == approval_decision(approved['response'], approved['request_id']),
                  'episode_response_decision_mismatch')
        _need(value['derived'] == _derived(raw) and
              value['conclusions'] == dict(learned_skill=False, independent_support_count=None),
              'episode_derivation_mismatch')
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError('episode_invalid_structure') from exc
    value['sha256'] = digest
    return value


def summarize_episodes(values):
    """Deduplicate recorded event identities; copies are not new evidence.

    Distinct events are not statistically independent trials or assets. That
    qualification needs the external native traces and experiment design.
    """
    _need(type(values) in (list, tuple) and len(values) <= 1024, 'episode_collection_budget')
    unique = {}
    outcomes = {}
    for value in values:
        episode = validate_episode(value)
        key = episode['raw_evidence']['event_id']
        _need(key not in unique or unique[key]['sha256'] == episode['sha256'],
              'episode_same_event_conflicting_records')
        unique[key] = episode
    for value in unique.values():
        outcome = value['derived']['outcome']
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return dict(input_records=len(values), distinct_recorded_events=len(unique),
                duplicate_records=len(values)-len(unique), outcomes=outcomes,
                success_candidates=sum(v['derived']['success_candidate'] for v in unique.values()),
                human_UI_verified=0, training_positives=0, independent_support_count=None,
                execution_authority=False, retry_authorized=False)


def read_episode(path):
    """Read one selected archive; absence/corruption never means success."""
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES+1)
    _need(len(raw) <= MAX_DOCUMENT_BYTES, 'episode_document_budget')
    return validate_episode(json.loads(raw))


def archive_episode(value, directory):
    """Opt-in consumer storage, never called from the execution loop.

    A complete file is flushed before an exclusive hard-link publication. A
    pre-existing file is validated and never overwritten. This is not a claim
    of directory-metadata durability after power loss or exactly-once delivery.
    The caller chooses an existing local directory; a resource URI is not a path.
    """
    value = validate_episode(value)
    folder = Path(directory).resolve(strict=True)
    _need(folder.is_dir(), 'episode_archive_directory_required')
    target = folder / (value['sha256']+'.json')
    temporary = None
    deduplicated = False
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=folder, prefix='.episode-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            _need(not target.is_symlink(), 'episode_archive_symlink_refused')
            _need(read_episode(target) == value, 'episode_archive_existing_conflict')
            deduplicated = True
    finally:
        if temporary is not None:
            temporary.unlink()
    return dict(path=str(target), sha256=value['sha256'], deduplicated=deduplicated,
                file_flushed=True, directory_metadata_flushed=False,
                execution_authority=False, retry_authorized=False)
