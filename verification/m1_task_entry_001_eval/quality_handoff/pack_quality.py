"""Post-run anonymous quality handoff only; never launches or scores a run.

Keep every frozen slot, original final byte, failed attempt and duplicate.
Only administrative evidence envelopes are projected; originals stay private.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
KEYS = ('cell', 'task', 'round', 'group')
PROTECTED = {'arguments', 'query', 'code', 'command'}
FACTS = {'binding', 'context', 'facts', 'coverage', 'unresolved', 'measurement_contracts',
    'limits', 'geometry_budget', 'budgets', 'candidate_acquisition', 'certificate'}
ADMIN = {'group', 'arm', 'profile', 'condition', 'cell', 'round', 'thread_id', 'pid',
    'actor_pid', 'actor_parent_pid', 'consumer_pid', 'launcher_pid', 'runtime_pid',
    'port', 'host', 'endpoint', 'argv', 'command_line', 'trace_id', 'request_id',
    'request_trace', 'execution_trace', 'runtime_identity', 'traceback', '_meta',
    'usage', 'usage_rows', 'token_usage', 'input_tokens', 'output_tokens',
    'cached_input_tokens', 'total_tokens', 'reasoning_tokens', 'fees', 'cost', 'costs',
    'started_ns', 'ended_ns', 'elapsed_ns', 'elapsed_s', 'elapsed_seconds',
    'wall_ns', 'duration_ns', 'duration_ms', 'duration_s', 'execution_time',
    'prompt_to_final_ns', 'total_task_wall_ns', 'full_cell_wall_ns', 'pre_consumer_setup_ns',
    'popen_ns', 'prompt_submitted_ns', 'final_received_ns', 'turn_completed_ns',
    'process_exit_ns', 'cleanup_end_ns', 'startup_ns', 'perf_ns', 'timings',
    'closed_ns', 'original_deadline_ns', 'deadline_ns',
    'wire_tool_bytes', 'response_bytes', 'produced_response_bytes',
    'closed_ns', 'deadline_ns', 'original_deadline_ns', 'chain_deadline_ns',
    'worker_deadline_ns', 'cell_started_ns', 'cell_ended_ns', 'batch_started_ns',
    'batch_ended_ns', 'batch_wall_ns'}
PATH = re.compile(r'(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/]|\\\\)[^\s"<>]+')
TOOL_TYPES = {'command_execution', 'mcp_tool_call', 'custom_tool_call', 'function_call',
    'web_search', 'image_view', 'file_change', 'todo_list', 'collab_tool_call'}


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: '+key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: '+value)))


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf8')


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def audit_projection(value, source, removals, pointer='$', semantic=False):
    """Exact key rules only. No numeric/text keyword scrub of model content."""
    def note(rule, original, at=pointer):
        removals.append({'source_sha256':sha(source), 'pointer':at, 'rule':rule,
            'original_value_sha256':sha(encoded(original))})
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            at = pointer+'/'+key.replace('~','~0').replace('/','~1')
            if key in PROTECTED:
                result[key] = item
            elif not semantic and key in ADMIN:
                note('administrative_envelope_field', item, at)
            else:
                result[key] = audit_projection(item, source, removals, at, semantic or key in FACTS)
        return result
    if isinstance(value, list):
        return [audit_projection(item, source, removals, pointer+'/'+str(i), semantic)
            for i, item in enumerate(value)]
    if isinstance(value, str):
        # Structured text results are decoded only to apply the same explicit
        # envelope rules. Facts, budgets, unknowns and source-binding keys stay.
        if value.strip().startswith(('{','[')):
            try:
                parsed = decode(value)
            except (ValueError, UnicodeError):
                pass
            else:
                projected = audit_projection(parsed, source, removals, pointer+'/decoded_json', semantic)
                if projected != parsed:
                    return json.dumps(projected, ensure_ascii=False, separators=(',',':'), allow_nan=False)
                return value
        def alias(match):
            original = match.group()
            note('absolute_diagnostic_or_source_path_stable_alias', original)
            return '<path_'+sha(original.encode('utf8'))[:16]+'>'
        return PATH.sub(alias, value)
    return value


def without_rpc_envelope(value, raw, removals):
    if not isinstance(value, dict):
        return value
    result = dict(value)
    for key in ('id', 'jsonrpc', '_meta'):
        if key in result:
            old = result.pop(key)
            removals.append({'source_sha256':sha(raw), 'pointer':'$/'+key,
                'rule':'RPC_transport_envelope', 'original_value_sha256':sha(encoded(old))})
    return result


def request_projection(value, raw, removals):
    result = without_rpc_envelope(value, raw, removals)
    if isinstance(result, dict) and isinstance(result.get('params'), dict) and '_meta' in result['params']:
        result['params'] = dict(result['params'])
        original = result['params'].pop('_meta')
        removals.append({'source_sha256':sha(raw), 'pointer':'$/params/_meta',
            'rule':'RPC_administrative_meta_envelope', 'original_value_sha256':sha(encoded(original))})
    return result


def capture_cell(folder, archive):
    """Complete originals, not just whichever records are convenient to score."""
    sources = {}
    if not folder.exists():
        return sources
    for path in sorted(folder.rglob('*')):
        if path.is_dir():
            continue
        assert not path.is_symlink() and path.resolve().is_relative_to(folder.resolve())
        sources[path.relative_to(folder).as_posix()] = path.read_bytes()
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, raw in sources.items():
            bundle.writestr(name, raw)
    return sources


def source_consistency(sources, removals):
    """Project existing producer evidence; never synthesize a passing check."""
    notes, records = [], {}
    names = ('ACTOR_CONFIG.json', 'owner/IDENTITY.json', 'owner/CLOSE.json')
    for name in names:
        raw = sources.get(name)
        if raw is None:
            records[name] = None
            notes.append({'record':name, 'pointer':'$', 'reason':'record_missing'})
            continue
        try:
            records[name] = decode(raw)
        except (ValueError, UnicodeError, TypeError) as exc:
            records[name] = None
            notes.append({'record':name, 'pointer':'$', 'reason':'record_unreadable_'+type(exc).__name__})
    def field(name, container, key, pointer):
        if not isinstance(container, dict) or key not in container:
            notes.append({'record':name, 'pointer':pointer, 'reason':'field_missing_or_parent_unavailable'})
            return None
        value = copy.deepcopy(container[key])
        if value is None:
            notes.append({'record':name, 'pointer':pointer, 'reason':'present_recorded_null'})
        return audit_projection(value, sources[name], removals, pointer)
    config, identity, close = (records[name] for name in names)
    # Read nested values from the original object, not the projected copy.
    original_native = close.get('native_close') if isinstance(close,dict) else None
    worker = field('owner/CLOSE.json', close, 'worker_closed', '$/worker_closed')
    original_worker = close.get('worker_closed') if isinstance(close,dict) else None
    evidence = {
        'ACTOR_CONFIG':{'asset_sha256':field('ACTOR_CONFIG.json',config,'asset_sha256','$/asset_sha256')},
        'owner_IDENTITY':{'asset_sha256':field('owner/IDENTITY.json',identity,'asset_sha256','$/asset_sha256')},
        'INITIAL_original_file_sha256':None,
        'FINAL_original_file_sha256':None,
        'CLOSE':{
            'geometry_unchanged':field('owner/CLOSE.json',close,'geometry_unchanged','$/geometry_unchanged'),
            'asset_unchanged':field('owner/CLOSE.json',close,'asset_unchanged','$/asset_unchanged'),
            'native_close':{
                key:field('owner/CLOSE.json',original_native,key,'$/native_close/'+key)
                for key in ('source_file_unchanged','protected_files_unchanged')},
            'worker_closed':worker,
            'worker_fingerprint_fields':{
                key:field('owner/CLOSE.json',original_worker,key,'$/worker_closed/'+key)
                for key in ('initial_geometry_fingerprint','final_geometry_fingerprint')},
            'errors':field('owner/CLOSE.json',close,'errors','$/errors')},
        'source_records_sha256':{name:sha(sources[name]) if name in sources else None
            for name in (*names,'owner/INITIAL.json','owner/FINAL.json')},
        'scope':'Existing producer fields and original file hashes only. No pass/fail, equality or independent readonly attestation is inferred. Final equality cannot exclude every transient operation.'}
    for label,name in (('INITIAL','owner/INITIAL.json'),('FINAL','owner/FINAL.json')):
        raw = sources.get(name)
        if raw is None:
            notes.append({'record':name,'pointer':'$','reason':'record_missing'})
        else:
            evidence[label+'_original_file_sha256'] = sha(raw)
    evidence['missing_or_null_notes'] = notes
    return evidence


def handoff_one(slot, mapping, record, sources, destination):
    removals, issues, files, attempts, events = [], [], {}, [], []
    def publish(name, raw):
        put(destination/name, raw)
        files[name] = sha(raw)
        return name
    consumer = None
    if 'CONSUMER.json' in sources:
        consumer = decode(sources['CONSUMER.json'])
        assert all(consumer.get(key)==slot[key] for key in KEYS), 'consumer slot binding mismatch'
    entered = record is not None
    if not entered:
        assert not sources, 'unrecorded material cannot be silently labelled not_run'
    state = 'not_run' if not entered else 'failed_before_consumer' if consumer is None else consumer.get('status', 'unknown')
    public = {'anonymous_id':mapping['anonymous_id'], 'task_id':slot['task'],
        'execution_record_state':state, 'answer_state':'not_run' if not entered else 'missing',
        'answer_file':None, 'unconfirmed_public_messages':[], 'cli_output_corroboration':None}
    final_raw = sources.get('PUBLIC_FINAL.txt')
    final_text = None if consumer is None else consumer.get('final')
    if final_raw is not None:
        name = publish('answer.txt', final_raw)
        public['answer_file'] = name
        public['answer_original_sha256'] = sha(final_raw)
        public['answer_state'] = 'present' if isinstance(final_text,str) and final_raw==final_text.encode('utf8') else 'inconsistent_final_binding'
        if public['answer_state'] != 'present':
            issues.append('PUBLIC_FINAL does not exactly equal consumer.final UTF8; no repair or replacement made')
    if 'final.txt' in sources:
        public['cli_output_corroboration'] = publish('cli_output_unconfirmed.txt', sources['final.txt'])
    raw_events = sources.get('events.jsonl')
    if raw_events is not None:
        for number, line in enumerate(raw_events.splitlines(), 1):
            if not line:
                continue
            entry = decode(line)
            event = entry.get('event', {})
            item = event.get('item', {})
            if final_raw is None and event.get('type')=='item.completed' and item.get('type')=='agent_message' and isinstance(item.get('text'),str):
                name = publish('unconfirmed_public_message_'+str(number)+'.txt', item['text'].encode('utf8'))
                public['unconfirmed_public_messages'].append({'file':name,
                    'scope':'decoded public event text encoded as UTF8; not a confirmed final file',
                    'source_sha256':sha(raw_events), 'source_line_sha256':sha(line)})
            if item.get('type') in TOOL_TYPES and event.get('type') in ('item.started','item.completed'):
                # Preserve every event independently; do not merge duplicate
                # requests or infer delivery from an owner-produced response.
                projected = {key:copy.deepcopy(item[key]) for key in ('type','tool','server','arguments','result','error','status','command') if key in item}
                events.append({'order':len(events)+1, 'phase':event['type'],
                    'event':audit_projection(projected, raw_events, removals),
                    'source_sha256':sha(raw_events), 'source_line_sha256':sha(line)})
    # Retain record-only text as explicitly unconfirmed, never fill a missing
    # final, never replace null with an invented answer such as "unknown".
    if isinstance(final_text,str) and (final_raw is None or final_raw!=final_text.encode('utf8')):
        public['record_only_text'] = publish('consumer_record_text_unconfirmed.txt', final_text.encode('utf8'))
    directories = sorted({Path(name).parts[1] for name in sources
        if len(Path(name).parts)>=3 and Path(name).parts[0]=='owner' and re.fullmatch(r'tool_\d+',Path(name).parts[1])},
        key=lambda name:int(name.split('_')[1]))
    for directory in directories:
        call = {'order':len(attempts)+1, 'request':None, 'responses':[], 'is_error':None,
            'owner_exception':None, 'source_files':[]}
        for filename in ('REQUEST.json','RESPONSE.json','ERROR_RESPONSE.json','ATTEMPT.json'):
            raw = sources.get('owner/'+directory+'/'+filename)
            if raw is None:
                continue
            data = decode(raw)
            call['source_files'].append({'kind':filename, 'original_sha256':sha(raw)})
            if filename=='REQUEST.json':
                # The request and params/arguments/query/code remain exact
                # decoded values; only top-level transport IDs are removed.
                call['request'] = request_projection(data, raw, removals)
            elif filename=='ATTEMPT.json':
                call['is_error'] = data.get('is_error')
                call['owner_exception'] = audit_projection(data.get('exception'), raw, removals)
            else:
                call['responses'].append({'kind':filename,
                    'value':audit_projection(without_rpc_envelope(data, raw, removals), raw, removals)})
        call['request_missing'] = call['request'] is None
        call['response_missing'] = not call['responses']
        attempts.append(call)
    publish('tool_evidence.json', encoded({'owner_attempts':attempts, 'public_tool_events':events,
        'binding_scope':'Owner-produced responses and consumer-public events are separate original records; unmatched/missing evidence does not prove delivery.'}))
    public['evidence_file'] = 'tool_evidence.json'
    publish('source_consistency.json', encoded(source_consistency(sources,removals)))
    public['source_consistency_file'] = 'source_consistency.json'
    public['source_provenance'] = {'consumer_record_sha256':None if consumer is None else sha(sources['CONSUMER.json']),
        'public_final_sha256':None if final_raw is None else sha(final_raw)}
    return public, {'files_sha256':files, 'source_files_sha256':{name:sha(raw) for name,raw in sources.items()},
        'administrative_projections':removals, 'issues':issues}


README = """# Anonymous quality review

Review each task-labelled answer and necessary tool evidence before viewing
the private directory or any cost/group analysis. Runtime completion does not
mean the answer is correct. Missing finals, unconfirmed public messages,
entered failures and unstarted slots are kept distinct. No slot, failed tool
attempt or duplicate request was replaced, merged or selected for quality.

answer.txt preserves PUBLIC_FINAL bytes exactly; its binding state states
whether consumer.final agrees. CLI output and decoded unconfirmed messages
are separate corroboration, never a substitute final. Tool requests retain
original decoded arguments/query/code. Facts, unknowns, geometry budgets and
source-binding fields remain; administrative envelopes omit route mapping,
process/request IDs and measured usage/timing. Absolute diagnostic/source
paths may use stable aliases. Private originals and pointer/rule/value hashes
make every projection auditable. Tool results are decoded/re-encoded JSON
projections, not claimed to be original network-frame bytes.

source_consistency.json projects existing configuration/identity asset hashes,
original initial/final file hashes and recorded closure/source/geometry fields.
Missing fields remain null with reasons. These are producer records, not new
passing checks or proof that no transient modification ever occurred.

Blinding is imperfect: original answer wording, tool names, schemas, code,
method-specific facts or incidental diagnostics may reveal the route. Model
content is not keyword-scrubbed to manufacture blindness. A short valid AABB
bound plus attained witness is valid evidence; extra computation is not a
quality requirement. This pack does not score, rank arms, infer adoption or
present timing/token/cost tables. Share only this public directory for the
first quality pass; the sibling private directory contains the original map,
complete source archives and audit details.
"""


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',help='new immediate child of quality_handoff, e.g. handoff_01')
    args=p.parse_args()
    assert Path(args.output).name==args.output and args.output not in ('.','..')
    out=(HERE/args.output).resolve()
    assert out.parent==HERE.resolve()
    control={name:(EVAL/name).read_bytes() for name in ('PLAN.json','FREEZE.json','private/ANON_MAP.json','RUN_RESULT.json')}
    plan,freeze,mapping,run=(decode(control[name]) for name in ('PLAN.json','FREEZE.json','private/ANON_MAP.json','RUN_RESULT.json'))
    assert sha(control['PLAN.json'])==freeze['plan_sha256'], 'execution PLAN not frozen'
    assert sha(control['private/ANON_MAP.json'])==plan['private_anonymous_map_sha256'], 'anonymous map drift'
    sequence, rows, records=plan['sequence'],mapping['rows'],run['records']
    assert len(sequence)==len(rows)==27 and len({row['cell'] for row in sequence})==27
    assert len({row['anonymous_id'] for row in rows})==27
    assert all(re.fullmatch(r'answer_[0-9a-f]{16}',row['anonymous_id']) for row in rows)
    assert len(records)<=27 and len({row['cell'] for row in records})==len(records)
    assert type(run.get('batch_ended_ns')) is int and run['batch_ended_ns']>0, 'terminal batch record required'
    assert len(records)==27 or run.get('stop'), 'partial run needs its preserved stop reason'
    for slot,row in zip(sequence,rows,strict=True):
        assert all(slot[key]==row[key] for key in KEYS), 'frozen map/plan mismatch'
    for slot,record in zip(sequence[:len(records)],records,strict=True):
        assert all(slot[key]==record[key] for key in KEYS), 'run is not a unique planned prefix'
    out.mkdir(exist_ok=False)
    public,private=out/'public',out/'private'
    public.mkdir();private.mkdir();(private/'raw').mkdir()
    for name,raw in control.items(): put(private/'control'/name,raw)
    put(public/'README.md',README.encode('utf8'))
    tasks=[]
    for task_id,task in sorted(plan['tasks'].items()):
        raw=(EVAL/'SESSION_RULES.txt').read_bytes()+b'\n'+(EVAL/task['prompt']).read_bytes()
        assert sha(raw)==task['model_input_sha256']
        put(public/'tasks'/(task_id+'.txt'),raw)
        tasks.append({'task_id':task_id,'prompt':'tasks/'+task_id+'.txt','input_sha256':sha(raw)})
    by_cell={row['cell']:row for row in records}
    answers,audit,snapshots=[],[],[]
    for row in sorted(rows,key=lambda row:row['anonymous_id']):
        cell=row['cell'];slot=next(slot for slot in sequence if slot['cell']==cell)
        folder=EVAL/'cells'/cell
        sources=capture_cell(folder,private/'raw'/(row['anonymous_id']+'.zip'))
        snapshots.append((folder,{name:sha(raw) for name,raw in sources.items()}))
        answer,details=handoff_one(slot,row,by_cell.get(cell),sources,public/row['anonymous_id'])
        answer['directory']=row['anonymous_id']
        answers.append(answer);audit.append({'mapping':row,**details})
    put(public/'INDEX.json',encoded({'tasks':tasks,'answers':answers,'fixed_slots':27,'scoring_performed':False}))
    # Refuse a moving source rather than silently packaging a mixed-time run.
    for folder,expected in snapshots:
        current={path.relative_to(folder).as_posix():sha(path.read_bytes()) for path in folder.rglob('*') if path.is_file()} if folder.exists() else {}
        assert current==expected, 'cell source changed during postprocessing'
    assert all((EVAL/name).read_bytes()==raw for name,raw in control.items()), 'control record changed during packaging'
    receipt={'script_sha256':sha(Path(__file__).read_bytes()),'fixed_anonymous_map':mapping,
        'control_sha256':{name:sha(raw) for name,raw in control.items()},'answers':audit,
        'public_files_sha256':{path.relative_to(public).as_posix():sha(path.read_bytes()) for path in public.rglob('*') if path.is_file()},
        'model_calls':0,'product_calls':0,'Blender_calls':0,'scoring_calls':0}
    put(private/'PROVENANCE.json',encoded(receipt))
    print(json.dumps({'packaged_slots':27,'public_directory':str(public),'private_directory':str(private),'scoring_performed':False}))


if __name__=='__main__': main()
