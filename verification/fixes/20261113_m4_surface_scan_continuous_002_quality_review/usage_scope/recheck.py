"""Scope-only audit of six explicitly authorized test UUIDs.

No group totals, episode token totals, cost values, messages, or winners are
published. Raw numeric values exist only transiently for equality checks.
"""
import hashlib
import json
from pathlib import Path
import re

TREE = Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe')
BATCH = TREE / 'verification/m4_surface_scan_continuous_consumption_002'
PROOF_PATH = BATCH / 'review/actual_usage/ALL_NUMERIC_PROOF.json'
OUT = Path(__file__).resolve().parent
EXPECTED = 'ec7e56a39f6d4632aee174a4c4ff19b8f4d9109d3d3da43ee9320de57590f2f1'
FIELDS = ('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens','total_tokens')
CHECKS, INPUTS = [], []

def sha(b):
    return hashlib.sha256(b).hexdigest()

def read_bytes(path, kind, expected=None):
    p = Path(path)
    data = p.read_bytes()
    h = sha(data)
    INPUTS.append({'kind': kind, 'source_path_sha256': sha(str(p.resolve()).encode()), 'sha256': h})
    if expected is not None:
        check(kind + ':source_SHA', h == expected)
    return data

def check(name, passed):
    CHECKS.append({'name': name, 'passed': bool(passed)})

def numeric(value, label):
    check(label + ':fields', type(value) is dict and set(value) == set(FIELDS))
    check(label + ':nonnegative_ints', all(type(value.get(k)) is int and value[k] >= 0 for k in FIELDS))
    check(label + ':input_output_total', value['total_tokens'] == value['input_tokens'] + value['output_tokens'])
    check(label + ':cached_subset', value['cached_input_tokens'] <= value['input_tokens'])
    check(label + ':cache_write_subset', value['cache_write_input_tokens'] <= value['input_tokens'])
    check(label + ':reasoning_subset', value['reasoning_output_tokens'] <= value['output_tokens'])
    return value

def session_projection(data, uuid):
    """Skip all message/response payloads; parse only metadata/task/token types."""
    selected = []
    active = None
    for n, line in enumerate(data.splitlines(keepends=True), 1):
        head, separator, tail = line.partition(b'"payload"')
        if not separator:
            continue
        m = re.search(rb'"type"\s*:\s*"([^"]+)"', head)
        if not m:
            continue
        kind = m.group(1).decode()
        if kind == 'event_msg':
            subtype = re.search(rb'^\s*:\s*\{\s*"type"\s*:\s*"([^"]+)"', tail)
            if subtype is None or subtype.group(1) not in (b'task_started', b'task_complete', b'token_count'):
                continue
            kind = subtype.group(1).decode()
        elif kind != 'session_meta':
            continue
        event = json.loads(line)
        payload = event['payload']
        common = {'source_line': n, 'source_line_sha256': sha(line), 'timestamp': event['timestamp']}
        if kind == 'session_meta':
            check('session_meta:UUID', payload['id'] == uuid and payload.get('session_id', uuid) == uuid)
            selected.append({'type':kind, 'thread_id':payload['id'], 'cli_version':payload['cli_version'], **common})
        elif kind == 'task_started':
            check('task_boundary:no_overlap', active is None)
            active = payload['turn_id']
            selected.append({'type':kind, 'turn_id':active, **common})
        elif kind == 'task_complete':
            check('task_boundary:matching_complete', active is not None and payload['turn_id'] == active)
            selected.append({'type':kind, 'turn_id':payload['turn_id'], **common})
            active = None
        else:
            check('token_scope:inside_task', active is not None)
            info = payload['info']
            selected.append({'type':kind,'info_present':info is not None,'turn_id':active,
                             'total_token_usage':None if info is None else info['total_token_usage'],
                             'last_token_usage':None if info is None else info['last_token_usage'], **common})
    check('session_tasks_closed', active is None)
    return selected

proof = json.loads(read_bytes(PROOF_PATH, 'numeric_proof', EXPECTED))
whitelist_path = Path(proof['whitelist_path'])
check('whitelist_under_fixed_batch', whitelist_path.resolve().is_relative_to(BATCH.resolve()))
whitelist = json.loads(read_bytes(whitelist_path, 'explicit_test_UUID_whitelist', proof['whitelist_sha256']))
threads = proof['threads']
uuids = [t['thread_id'] for t in threads]
check('six_unique_exact_UUIDs', len(uuids) == len(set(uuids)) == 6)
check('whitelist_18_bindings', len(whitelist['records']) == 18)
check('whitelist_same_exact_UUIDs', {r['thread_id'] for r in whitelist['records']} == set(uuids))
check('no_cost_unseal_claim', proof['cost_unsealed'] is False and proof['usage_aggregation'] is None and proof['group_totals_computed'] is False and proof['episode_usage_aggregates_computed'] is False)

# Bind the authorized UUID list to the same fixed batch's closed outer records.
outer_bindings = set()
for row in proof['closed_outer_sources']:
    p = Path(row['path'])
    check('outer_source_under_fixed_batch', p.resolve().is_relative_to(BATCH.resolve()))
    outer = json.loads(read_bytes(p, 'same_batch_closed_outer', row['sha256']))
    for turn in outer['coordinator']['turns']:
        c = turn['consumer']
        outer_bindings.add((c['thread_id'], c['turn_index'], c['expected_thread_id']))
check('outer_eighteen_UUID_slots', len(outer_bindings) == 18)
check('whitelist_matches_closed_outer_slots', outer_bindings == {(r['thread_id'],r['turn_index'],r['expected_thread_id']) for r in whitelist['records']})

session_paths = set()
turn_ids = set()
confirmed = []
resumes = 0
duplicates_observed = False
for thread_no, thread in enumerate(threads, 1):
    label = 'scope_thread_' + str(thread_no)
    uuid = thread['thread_id']
    session_path = Path(thread['session_path'])
    check(label + ':UUID_in_exact_session_basename', uuid in session_path.name)
    check(label + ':session_path_not_reused', str(session_path.resolve()) not in session_paths)
    session_paths.add(str(session_path.resolve()))
    selected = session_projection(read_bytes(session_path, 'authorized_session_' + str(thread_no), thread['session_sha256']), uuid)
    check(label + ':entire_allowed_projection_matches_proof', selected == thread['selected_numeric_events'])
    check(label + ':single_session_meta', sum(x['type']=='session_meta' for x in selected) == 1)
    check(label + ':fixed_CLI_version', next(x for x in selected if x['type']=='session_meta')['cli_version'] == '0.152.1')
    starts = [x for x in selected if x['type']=='task_started']
    ends = [x for x in selected if x['type']=='task_complete']
    check(label + ':three_tasks', len(starts) == len(ends) == 3)
    check(label + ':same_order_closed_tasks', [x['turn_id'] for x in starts] == [x['turn_id'] for x in ends])
    check(label + ':three_consumer_bindings', [x['turn_index'] for x in thread['consumer_bindings']] == [1,2,3])
    prior_terminal = None
    for index, (start, end, binding, author) in enumerate(zip(starts,ends,thread['consumer_bindings'],thread['per_turn_proof']),1):
        turn_label = label + ':turn_' + str(index)
        check(turn_label + ':unique_task_id', start['turn_id'] not in turn_ids)
        turn_ids.add(start['turn_id'])
        check(turn_label + ':ordered_task_window', start['source_line'] < end['source_line'])
        tokens = [x for x in selected if x['type']=='token_count' and x['turn_id']==start['turn_id']]
        check(turn_label + ':token_events_present', bool(tokens))
        check(turn_label + ':token_windows', all(start['source_line'] < x['source_line'] < end['source_line'] for x in tokens))
        states=[]
        for count,event in enumerate(tokens,1):
            check(turn_label + ':info_present', event['info_present'] is True)
            total=numeric(event['total_token_usage'],turn_label+':event_'+str(count)+':total')
            last=numeric(event['last_token_usage'],turn_label+':event_'+str(count)+':last')
            state=(total,last)
            if states and state==states[-1]:
                duplicates_observed=True
                continue
            states.append(state)
        check(turn_label + ':starts_from_zero', states[0][0] == states[0][1])
        if prior_terminal is not None:
            check(turn_label + ':not_previous_thread_cumulative_terminal', states[0][0] != prior_terminal)
        for j in range(1,len(states)):
            check(turn_label + ':new_numeric_state_has_increment_'+str(j), any(states[j][0][f] != states[j-1][0][f] for f in FIELDS))
            check(turn_label + ':delta_equals_last_'+str(j), all(states[j][0][f] == states[j-1][0][f] + states[j][1][f] for f in FIELDS))
        terminal=states[-1][0]
        check(turn_label + ':terminal_equals_distinct_last_sum', all(terminal[f]==sum(s[1][f] for s in states) for f in FIELDS))

        cb=Path(binding['consumer_path']); eb=Path(binding['CLI_events_path'])
        expected=None if index==1 else uuid
        check(turn_label+':binding_expected_UUID',binding['expected_thread_id']==expected)
        wl=[r for r in whitelist['records'] if r['thread_id']==uuid and r['turn_index']==index]
        check(turn_label+':whitelist_exact_consumer_binding',len(wl)==1 and Path(wl[0]['consumer_record']).resolve()==cb.resolve() and wl[0]['consumer_sha256']==binding['consumer_sha256'])
        consumer=json.loads(read_bytes(cb,turn_label+':consumer',binding['consumer_sha256']))
        check(turn_label+':consumer_identity',consumer['thread_id']==uuid and consumer['turn_index']==index and consumer['expected_thread_id']==expected)
        argv=consumer['frozen_cli_argv']
        check(turn_label+':real_resume_argument', ('resume' in argv and uuid in argv) if index>1 else ('resume' not in argv))
        if index>1:resumes+=1
        complete=[]; cli_threads=[]
        for line in read_bytes(eb,turn_label+':CLI_events',binding['CLI_events_sha256']).splitlines():
            # Ignore tool messages, final answers, time and non-usage events.
            obj=json.loads(line);event=obj.get('event',{})
            if event.get('type')=='thread.started':cli_threads.append(event.get('thread_id'))
            if event.get('type')=='turn.completed':complete.append(event.get('usage'))
        check(turn_label+':one_CLI_UUID',cli_threads==[uuid])
        check(turn_label+':single_CLI_terminal_usage',len(complete)==1)
        usage=complete[0]
        check(turn_label+':CLI_consumer_same_unique_terminal',consumer['raw_usage_events']==[usage] and consumer['usage_rows']==[usage] and consumer['usage']==usage)
        check(turn_label+':reported_fields_known',set(usage).issubset(FIELDS) and {'input_tokens','output_tokens','cached_input_tokens','reasoning_output_tokens'}.issubset(usage))
        check(turn_label+':CLI_terminal_equals_session_terminal',all(type(v)is int and v>=0 and terminal[k]==v for k,v in usage.items()))
        check(turn_label+':cached_not_extra',usage['cached_input_tokens']<=usage['input_tokens'])
        check(turn_label+':reasoning_not_extra',usage['reasoning_output_tokens']<=usage['output_tokens'])
        check(turn_label+':author_raw_usage_same',author['raw_CLI_usage']==usage)
        check(turn_label+':author_task_ID_same',author['session_turn_id']==start['turn_id'] and author['turn_index']==index)
        check(turn_label+':author_counts_recomputed',author['raw_token_count_events']==len(tokens) and author['distinct_numeric_states']==len(states))
        prior_terminal=terminal
    confirmed.append({'scope_label':label,'authorized_thread_id_sha256':sha(uuid.encode()),'three_disjoint_task_windows':True,'per_turn_CLI_terminal_scope_observed':True})

check('eighteen_unique_task_IDs',len(turn_ids)==18)
check('twelve_actual_resume_bindings',resumes==12)
check('author_scope_summary_count_matches',proof['summary']['actual_threads_checked']==6 and proof['summary']['actual_turns_checked']==18 and proof['summary']['actual_resume_turns']==12)
result={'scope_conclusion':'per_turn_CLI_invocation_observed' if all(x['passed'] for x in CHECKS) else 'not_confirmed',
        'checks':len(CHECKS),'passed':all(x['passed'] for x in CHECKS),'failed_checks':[x for x in CHECKS if not x['passed']],
        'authorized_test_threads':6,'CLI_invocations':18,'resume_invocations':12,
        'duplicate_numeric_snapshots_observed':duplicates_observed,
        'scope_proofs':confirmed,'numeric_proof_sha256':EXPECTED,
        'numeric_aggregates_published':False,'group_mapping_published':False,'cost_unsealed':False,
        'aggregation_rule':'After quality seal, sum exactly one final reported usage per confirmed CLI invocation. Do not sum cumulative token_count snapshots. Cached and reasoning remain subsets. Replayed history tokens are real per-invocation input, not a duplicate event to subtract.',
        'unconfirmed':['Provider-side abandoned/retried request billing coverage beyond recorded terminal events.','Actual fees or subscription debit.','Resolved provider model/effort or tokenized input visibility.'],
        'reading_boundary':'Only exact six authorized session paths; metadata/task/token_count fields projected, all messages/base instructions/rate limits ignored. Same-batch consumer terminal usage and UUID bindings only; no unrelated sessions or credentials.'}
for name,value in [('RESULTS.json',result),('CHECKS.json',CHECKS),('INPUT_HASHES.json',INPUTS)]:
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:result[k] for k in ('scope_conclusion','checks','passed','authorized_test_threads','CLI_invocations','resume_invocations','failed_checks')},ensure_ascii=False))
