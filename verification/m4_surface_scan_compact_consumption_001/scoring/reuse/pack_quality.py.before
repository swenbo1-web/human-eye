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
CYCLE = 'M4-SURFACE-SCAN-CONSUMPTION-001'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
KEYS = ('cell', 'task', 'round', 'group')
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
    """Copy a payload unchanged; field names and text never imply an envelope.

    The prior signature remains available for replaying archived counterexamples.
    Administrative removal requires an explicit known envelope at its caller.
    JSON-looking strings, native stdout and path-like text are not interpreted.
    """
    return copy.deepcopy(value)


def without_admin_fields(value, raw, removals, *, pointer, fields):
    """Remove only named direct fields of a caller-identified producer envelope."""
    result = copy.deepcopy(value)
    if not isinstance(result, dict):
        return result
    for key in fields:
        if key in result:
            original = result.pop(key)
            removals.append({'source_sha256':sha(raw),
                'pointer':pointer+'/'+key.replace('~','~0').replace('/','~1'),
                'rule':'known_administrative_envelope_field',
                'original_value_sha256':sha(encoded(original))})
    return result


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
    names = ('ACTOR_CONFIG.json', 'owner/IDENTITY.json', 'owner/CLOSE.json', 'CONSUMER.json')
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
    config, identity, close = (records[name] for name in names[:3])
    consumer = records['CONSUMER.json']
    image = consumer.get('initial_image') if isinstance(consumer,dict) else None
    delivery = consumer.get('image_delivery') if isinstance(consumer,dict) else None
    # Read nested values from the original object, not the projected copy.
    original_native = close.get('native_close') if isinstance(close,dict) else None
    worker = without_admin_fields(
        field('owner/CLOSE.json', close, 'worker_closed', '$/worker_closed'),
        sources.get('owner/CLOSE.json', b''), removals, pointer='$/worker_closed',
        fields=('pid','closed_ns','original_deadline_ns'))
    original_worker = close.get('worker_closed') if isinstance(close,dict) else None
    evidence = {
        'ACTOR_CONFIG':{'asset_sha256':field('ACTOR_CONFIG.json',config,'asset_sha256','$/asset_sha256')},
        'owner_IDENTITY':{'asset_sha256':field('owner/IDENTITY.json',identity,'asset_sha256','$/asset_sha256')},
        'CONSUMER_INPUT':{
            'input_image_count':field('CONSUMER.json',consumer,'input_image_count','$/input_image_count'),
            'input_image_bytes':field('CONSUMER.json',consumer,'input_image_bytes','$/input_image_bytes'),
            'initial_image_sha256':field('CONSUMER.json',image,'sha256','$/initial_image/sha256'),
            'initial_image_unchanged':field('CONSUMER.json',consumer,'initial_image_unchanged','$/initial_image_unchanged'),
            'image_delivery':{key:field('CONSUMER.json',delivery,key,'$/image_delivery/'+key)
                for key in ('prepared_file_verified','initial_attachment_in_argv',
                    'CLI_process_launched','CLI_thread_started','status',
                    'provider_delivery_confirmed','model_view_confirmed')}},
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
        assert all(consumer.get(key)==slot[key] for key in ('cell','task','round')), 'consumer slot binding mismatch'
        expected_group={'N':'N','P':'P'}[slot['group']]
        assert consumer.get('group')==expected_group and consumer.get('external_group')==slot['group'], 'consumer external/internal group binding mismatch'
    entered = record is not None
    if not entered:
        assert not sources, 'unrecorded material cannot be silently labelled not_run'
    state = 'not_run' if not entered else 'failed_before_consumer' if consumer is None else consumer.get('status', 'unknown')
    cell_errors = [] if record is None else copy.deepcopy(record.get('errors',[]))
    # These are known controller error envelopes. Their actual messages remain
    # available, including unknown/failure semantics and incidental path text.
    for index,error in enumerate(cell_errors):
        if isinstance(error,dict):
            cell_errors[index] = without_admin_fields(error,encoded(record),removals,
                pointer='$/record/errors/'+str(index),fields=('traceback',))
    finish = record.get('finish') if isinstance(record,dict) else None
    finish_confirmed = finish.get('confirmed') if isinstance(finish,dict) else None
    valid_completion = consumer.get('valid_completion') if isinstance(consumer,dict) else None
    continuation_safe = consumer.get('safe_to_continue') if isinstance(consumer,dict) else None
    consumer_errors = copy.deepcopy(consumer.get('errors',[])) if isinstance(consumer,dict) else []
    for index,error in enumerate(consumer_errors):
        if isinstance(error,dict):
            consumer_errors[index] = without_admin_fields(error,sources['CONSUMER.json'],removals,
                pointer='$/errors/'+str(index),fields=('traceback',))
    if not entered:
        cell_state = 'not_run'
    elif cell_errors or (isinstance(consumer,dict) and consumer.get('errors')) or state in ('failed','timeout','execution_failure') or valid_completion is False:
        cell_state = 'failed'
    elif state == 'completed' and valid_completion is True and finish_confirmed is True and continuation_safe is not False:
        cell_state = 'completed'
    else:
        cell_state = 'unknown'
    public = {'anonymous_id':mapping['anonymous_id'], 'task_id':slot['task'],
        'execution_record_state':state, 'answer_state':'not_run' if not entered else 'missing',
        'cell_execution_state':cell_state,'cell_errors':cell_errors,
        'consumer_execution_errors':consumer_errors,
        'consumer_valid_completion':valid_completion,'owner_finish_confirmed':finish_confirmed,
        'safe_to_continue':continuation_safe,
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
                    'event':projected,
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
                call['owner_exception'] = without_admin_fields(data.get('exception'), raw, removals,
                    pointer='$/exception', fields=('traceback',))
            else:
                call['responses'].append({'kind':filename,
                    'value':copy.deepcopy(without_rpc_envelope(data, raw, removals))})
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
source-binding fields remain. Only known RPC/event or producer-envelope
positions omit their explicit administrative fields. Entire tool result/error
payloads, native stdout, nested facts and JSON strings are preserved, including
their original whitespace and path-like text. No field-name whitelist or
recursive text parsing is used to decide what counts as a fact.
Private originals and pointer/rule/value hashes
make every projection auditable. Tool results are decoded/re-encoded JSON
projections, not claimed to be original network-frame bytes.

source_consistency.json projects existing configuration/identity asset hashes,
original initial/final file hashes and recorded closure/source/geometry fields.
Missing fields remain null with reasons. These are producer records, not new
passing checks or proof that no transient modification ever occurred.
The common task text has zero initial images and zero new images. Recorded
image counts and text-only CLI submission fields are producer records.
The scoring directory carries the frozen actual-geometry input, independent
oracle and quality contract. Reviewers check the complete threshold pair set,
stated distances and explicit completeness against the frozen full-scene truth
and actual geometry. A clear reference to a complete visible business list
remains eligible. Equivalent free-form answers receive the same fact checks.

Blinding is imperfect: original answer wording, tool names, schemas, code,
method-specific facts or incidental diagnostics may reveal the route. Model
content is not keyword-scrubbed to manufacture blindness. The task requires the
correct all-scene threshold set and distances. No
particular algorithm, manual proof replay or additional computation is a
quality requirement. This pack does not score, rank arms, infer adoption or
present timing/token/cost tables. Share only this public directory for the
first quality pass; the sibling private directory contains the original map,
complete source archives and audit details.
"""


def validate_zero_launch_failure(run, control):
    """Accept this cycle's started, terminal zero-consumer failure prefix."""
    go, started = (decode(control[name]) for name in ('GO.json','STARTED.json'))
    plan_sha256 = sha(control['PLAN.json'])
    assert (go.get('task')==CYCLE and go.get('authorized') is True
        and go.get('max_consumers')==6 and go.get('plan_sha256')==plan_sha256), 'zero-launch GO binding mismatch'
    assert (started.get('max_consumers')==6 and started.get('plan_sha256')==plan_sha256
        and type(started.get('started_ns')) is int and started['started_ns']>0), 'zero-launch STARTED binding mismatch'
    assert (len(run['records']) in (0,1) and type(run.get('started_cells')) is int
        and run['started_cells']==len(run['records']) and run.get('maximum_consumers')==6
        and run.get('all_planned_dispatched') is False
        and run.get('no_replacements') is True), 'zero-launch terminal counts mismatch'
    assert isinstance(run.get('stop'),str) and run['stop'].strip(), 'zero-launch failed prefix required'
    assert all(type(run.get(key)) is int and run[key]>0
        for key in ('batch_started_ns','batch_ended_ns')), 'zero-launch timing mismatch'
    assert (run['batch_started_ns']<=started['started_ns']<=run['batch_ended_ns']
        and type(run.get('batch_wall_ns')) is int
        and run['batch_wall_ns']==run['batch_ended_ns']-run['batch_started_ns']), 'zero-launch timing mismatch'
    if not run['records']:
        return
    row = run['records'][0]
    assert all(type(row.get(key)) is int and row[key]>0
        for key in ('cell_started_ns','cell_ended_ns')), 'zero-launch timing mismatch'
    assert (run['batch_started_ns']<=started['started_ns']<=row['cell_started_ns']
        <=row['cell_ended_ns']<=run['batch_ended_ns']), 'zero-launch timing mismatch'
    assert (type(run.get('batch_wall_ns')) is int
        and run['batch_wall_ns']==run['batch_ended_ns']-run['batch_started_ns']
        and type(row.get('full_cell_wall_ns')) is int
        and row['full_cell_wall_ns']==row['cell_ended_ns']-row['cell_started_ns']
        and row.get('within_570s') is (row['full_cell_wall_ns']<570*10**9)), 'zero-launch timing mismatch'
    consumer = row.get('consumer')
    if consumer is None:
        errors = row.get('errors')
    else:
        assert (isinstance(consumer,dict) and consumer.get('consumer_pid') is None
            and consumer.get('status')=='failed' and consumer.get('valid_completion') is False
            and consumer.get('thread_id') is None and consumer.get('final') is None), 'zero-launch failed prefix required'
        errors = consumer.get('errors')
    assert (isinstance(errors,list) and errors and any(isinstance(error,dict)
        and isinstance(error.get('type'),str) and isinstance(error.get('message'),str)
        for error in errors)), 'zero-launch failed prefix required'


def validate_pre_started_failure(run, control):
    """Retain six unstarted slots after a genuine pre-STARTED controller error."""
    go = decode(control['GO.json'])
    terminal = decode(control['FORMAL_PROCESS.json'])
    assert (go.get('task') == CYCLE and go.get('authorized') is True
        and go.get('max_consumers') == 6 and go.get('plan_sha256') == sha(control['PLAN.json'])), 'pre-start GO binding mismatch'
    assert (run['records'] == [] and run.get('started_cells') == 0
        and run.get('maximum_consumers') == 6 and run.get('all_planned_dispatched') is False
        and run.get('no_replacements') is True and isinstance(run.get('stop'),str)
        and run['stop'].strip()), 'pre-start terminal denominator mismatch'
    error = terminal.get('controller_error')
    assert (terminal.get('status') == 'terminal' and terminal.get('started_cells') == 0
        and terminal.get('stop') == run['stop'] and isinstance(error,dict)
        and isinstance(error.get('type'),str) and isinstance(error.get('message'),str)), 'pre-start controller failure required'
    times = [terminal.get('started_ns'),run.get('batch_started_ns'),
        run.get('batch_ended_ns'),terminal.get('ended_ns')]
    assert all(type(value) is int and value > 0 for value in times)
    assert times == sorted(times) and run.get('batch_wall_ns') == times[2]-times[1], 'pre-start timing mismatch'


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
    assert plan['cycle_id']==CYCLE and plan['batch']==CYCLE, 'wrong observation cycle'
    assert plan['logical_denominator']==6 and plan['per_arm']==3 and set(plan['arms'])=={'N','P'}, 'wrong fixed six-slot sample metadata'
    assert plan['image_count']==0 and plan['new_images']==0, 'wrong zero-image contract'
    sequence, rows, records=plan['sequence'],mapping['rows'],run['records']
    assert len(sequence)==len(rows)==6 and len({row['cell'] for row in sequence})==6
    assert len({row['anonymous_id'] for row in rows})==6
    assert all(re.fullmatch(r'answer_[0-9a-f]{16}',row['anonymous_id']) for row in rows)
    assert len(records)<=6 and len({row['cell'] for row in records})==len(records)
    assert type(run.get('batch_ended_ns')) is int and run['batch_ended_ns']>0, 'terminal batch record required'
    assert len(records)==6 or run.get('stop'), 'partial run needs its preserved stop reason'
    launched = any(isinstance(record.get('consumer'),dict)
        and type(record['consumer'].get('consumer_pid')) is int and record['consumer']['consumer_pid']>0
        for record in records)
    for name in ('FORMAL_PROCESS.json','FORMAL_PUBLICATION.json','FORMAL_ERROR.json'):
        if (EVAL/name).exists():
            control[name] = (EVAL/name).read_bytes()
    if not launched:
        control['GO.json'] = (EVAL/'GO.json').read_bytes()
        if (EVAL/'STARTED.json').exists():
            control['STARTED.json'] = (EVAL/'STARTED.json').read_bytes()
            validate_zero_launch_failure(run,control)
        else:
            validate_pre_started_failure(run,control)
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
    assert set(plan['tasks'])=={'T1'}, 'one fixed observation task required'
    for task_id,task in sorted(plan['tasks'].items()):
        raw=(EVAL/plan['inputs']['prompt']).read_bytes()
        assert sha(raw)==plan['inputs']['prompt_sha256']
        put(public/'tasks'/(task_id+'.txt'),raw)
        tasks.append({'task_id':task_id,'prompt':'tasks/'+task_id+'.txt','input_sha256':sha(raw),
            'initial_image_count':0,'new_images':0})
    scoring=[]
    for material in plan['quality_materials']:
        relative=Path(material['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        name=material['public_name']
        assert Path(name).name==name and name not in ('.','..')
        original=(EVAL/relative).resolve()
        assert original.is_relative_to(EVAL.resolve())
        raw=original.read_bytes()
        assert sha(raw)==material['sha256'], 'frozen quality material changed'
        put(public/'scoring'/name,raw)
        scoring.append({'file':'scoring/'+name,'sha256':sha(raw),'source_path':material['path']})
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
    controller = decode(control['FORMAL_PROCESS.json']) if 'FORMAL_PROCESS.json' in control else None
    controller_removals = []
    controller_public = without_admin_fields(controller,control.get('FORMAL_PROCESS.json',b''),controller_removals,
        pointer='$',fields=('started_ns','ended_ns','started_utc','ended_utc','timing_scope','scope'))
    if isinstance(controller_public,dict) and isinstance(controller_public.get('controller_error'),dict):
        controller_public['controller_error'] = without_admin_fields(controller_public['controller_error'],
            control['FORMAL_PROCESS.json'],controller_removals,pointer='$/controller_error',fields=('traceback',))
    put(public/'INDEX.json',encoded({'tasks':tasks,'scoring_materials':scoring,'answers':answers,
        'controller_execution':controller_public,'fixed_slots':6,'scoring_performed':False}))
    # Refuse a moving source rather than silently packaging a mixed-time run.
    for folder,expected in snapshots:
        current={path.relative_to(folder).as_posix():sha(path.read_bytes()) for path in folder.rglob('*') if path.is_file()} if folder.exists() else {}
        assert current==expected, 'cell source changed during postprocessing'
    assert all((EVAL/name).read_bytes()==raw for name,raw in control.items()), 'control record changed during packaging'
    receipt={'script_sha256':sha(Path(__file__).read_bytes()),'fixed_anonymous_map':mapping,
        'control_sha256':{name:sha(raw) for name,raw in control.items()},'answers':audit,
        'controller_administrative_projections':controller_removals,
        'public_files_sha256':{path.relative_to(public).as_posix():sha(path.read_bytes()) for path in public.rglob('*') if path.is_file()},
        'model_calls':0,'product_calls':0,'Blender_calls':0,'scoring_calls':0}
    put(private/'PROVENANCE.json',encoded(receipt))
    print(json.dumps({'packaged_slots':6,'public_directory':str(public),'private_directory':str(private),'scoring_performed':False}))


if __name__=='__main__': main()
