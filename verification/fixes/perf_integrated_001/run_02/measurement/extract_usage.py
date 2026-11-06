"""PERF-000 read-only host metadata + public tool/answer extractor.

Public text comes ONLY from sanitized codex_app.read_thread snapshots. The exact
UUID rollout is streamed for whitelisted metadata, token counters and public
tool envelope timestamps/image block counts; reasoning/analysis is skipped.
Never imports a product module or starts Blender/models. Outputs are new named
revisions and never replace earlier extraction evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
PLAN_SHA256 = '1af39e2e6a8f980a2f575d1b2417c012931719a6071683b8343d05ce809860b9'
TOKEN_KEYS = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
              'output_tokens', 'reasoning_output_tokens', 'total_tokens')
UUID = re.compile(r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$')
ENVELOPE = re.compile(r'"type"\s*:\s*"(session_meta|turn_context|event_msg|response_item)"')
PRIVATE = re.compile(r'"(?:type|channel)"\s*:\s*"(?:reasoning|analysis)"')


def blob(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def evidence(path):
    raw = path.read_bytes()
    return dict(path=str(path).replace('\\', '/'), bytes=len(raw), sha256=sha(raw))


def load(path):
    return json.loads(path.read_bytes())


def new_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as out:
        out.write(blob(value))


def count_images(value):
    if isinstance(value, list):
        return sum(count_images(x) for x in value)
    if isinstance(value, dict):
        own = int(value.get('type') in ('input_image', 'image'))
        return own + sum(count_images(v) for k,v in value.items() if k not in ('data','image_url','base64'))
    return 0


def public_tool_text(value):
    """Exact delivered textual blocks, without inventing framing/newline bytes."""
    if isinstance(value,str):
        values=[('function_output_string',value)]
    elif isinstance(value,list):
        values=[(item.get('type'),item['text']) for item in value if isinstance(item,dict)
                and item.get('type') in ('input_text','text') and isinstance(item.get('text'),str)]
    elif isinstance(value,dict) and value.get('type') in ('input_text','text') and isinstance(value.get('text'),str):
        values=[(value['type'],value['text'])]
    else:
        values=[]
    return [dict(type=kind,text=text,utf8_bytes=len(text.encode('utf8')),sha256=sha(text.encode('utf8')))
            for kind,text in values]


def rollout_metadata(path, expected_thread):
    before = path.stat()
    current = None
    turns = {}
    meta = None
    previous = None
    selected = []
    skipped = 0
    with path.open('r', encoding='utf-8-sig') as source:
        for line_number, raw in enumerate(source, 1):
            if PRIVATE.search(raw):
                skipped += 1
                continue
            match = ENVELOPE.search(raw[:250])
            if not match:
                continue
            kind = match.group(1)
            row = json.loads(raw)
            p = row.get('payload', {})
            record = None
            if kind == 'session_meta':
                if p.get('id') != expected_thread:
                    raise ValueError('rollout exact thread UUID mismatch')
                meta = {k:p.get(k) for k in ('id','parent_thread_id','timestamp','agent_path','agent_nickname','originator','cli_version','model_provider','thread_source','git')}
                record = dict(line=line_number, timestamp=row.get('timestamp'), kind=kind, value=meta)
            elif kind == 'event_msg' and p.get('type') == 'task_started':
                current = p['turn_id']
                turns.setdefault(current, dict(turn_id=current, context=None, usage_events=[], tool_envelopes=[]))
                record = dict(line=line_number,timestamp=row.get('timestamp'),kind='task_started',
                              turn_id=current,started_at=p.get('started_at'))
                turns[current]['started'] = record
            elif kind == 'turn_context':
                turn_id = p.get('turn_id', current)
                current = turn_id
                turn = turns.setdefault(turn_id, dict(turn_id=turn_id,context=None,usage_events=[],tool_envelopes=[]))
                settings = p.get('collaboration_mode',{}).get('settings',{})
                value = dict(model_alias=p.get('model'),reasoning_effort=p.get('effort'),
                             collaboration_model=settings.get('model'),collaboration_reasoning_effort=settings.get('reasoning_effort'))
                record = dict(line=line_number,timestamp=row.get('timestamp'),kind='turn_context',turn_id=turn_id,value=value)
                turn['context'] = value
            elif kind == 'event_msg' and p.get('type') == 'token_count' and current:
                info = p.get('info') or {}
                total = info.get('total_token_usage')
                last = info.get('last_token_usage')
                if not isinstance(total,dict):
                    continue
                total = {k:total.get(k) for k in TOKEN_KEYS}
                last = None if not isinstance(last,dict) else {k:last.get(k) for k in TOKEN_KEYS}
                valid = all(type(total[k]) is int and total[k] >= 0 for k in TOKEN_KEYS)
                delta = None
                issues = []
                if valid:
                    base = previous or {k:0 for k in TOKEN_KEYS}
                    if all(type(base.get(k)) is int and total[k] >= base[k] for k in TOKEN_KEYS):
                        delta = {k:total[k]-base[k] for k in TOKEN_KEYS}
                    else:
                        issues.append('cumulative_counter_reset_or_missing_field; no inferred delta')
                    previous = total
                    if total['cached_input_tokens'] > total['input_tokens']:
                        issues.append('cached_input_exceeds_input')
                    if total['reasoning_output_tokens'] > total['output_tokens']:
                        issues.append('reasoning_exceeds_output')
                    if total['total_tokens'] != total['input_tokens']+total['output_tokens']:
                        issues.append('total_is_not_input_plus_output')
                else:
                    issues.append('incomplete_or_invalid_cumulative_usage')
                duplicate = delta is not None and all(v==0 for v in delta.values())
                record = dict(line=line_number,timestamp=row.get('timestamp'),kind='token_count',turn_id=current,
                    total_usage=total,last_usage=last,cumulative_delta=delta,
                    duplicate_cumulative_snapshot=duplicate,
                    delta_matches_last_usage=(None if delta is None or last is None or duplicate else delta==last),
                    last_usage_includes_reasoning=info.get('last_usage_includes_reasoning'),issues=issues)
                turns[current]['usage_events'].append(record)
            elif kind == 'event_msg' and p.get('type') == 'task_complete' and p.get('turn_id') in turns:
                turn_id = p['turn_id']
                record = dict(line=line_number,timestamp=row.get('timestamp'),kind='task_complete',turn_id=turn_id,
                    started_at=p.get('started_at'),completed_at=p.get('completed_at'),duration_ms=p.get('duration_ms'),
                    time_to_first_token_ms=p.get('time_to_first_token_ms'))
                turns[turn_id]['completed'] = record
            elif kind == 'response_item' and p.get('type') in ('custom_tool_call','function_call','custom_tool_call_output','function_call_output'):
                passthrough = p.get('internal_chat_message_metadata_passthrough') or {}
                turn_id = passthrough.get('turn_id', current)
                if turn_id not in turns:
                    continue
                output = p.get('type','').endswith('_output')
                text_blocks=public_tool_text(p.get('output')) if output else []
                tool_input=p.get('input',p.get('arguments')) if not output else None
                record = dict(line=line_number,timestamp=row.get('timestamp'),kind=p['type'],turn_id=turn_id,
                    call_id=p.get('call_id'),name=p.get('name'),
                    actual_create_time=passthrough.get('create_time'),
                    input_image_blocks=(count_images(p.get('output')) if output else 0),
                    public_tool_input=tool_input,public_tool_text_blocks=text_blocks,
                    actual_tool_output_text_utf8_bytes=sum(b['utf8_bytes'] for b in text_blocks),
                    tool_text_scope='Exact nonreasoning rollout input_text/text blocks or function output string; not command-stdout-only, wire framing, or all model input.')
                turns[turn_id]['tool_envelopes'].append(record)
            if record is not None:
                selected.append(record)
    after = path.stat()
    if not meta:
        raise ValueError('missing exact session_meta')
    if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
        raise ValueError('rollout changed while extracting metadata')
    for t in turns.values():
        events = t['usage_events']
        if events and all(e['cumulative_delta'] is not None for e in events):
            t['usage'] = {k:sum(e['cumulative_delta'][k] for e in events) for k in TOKEN_KEYS}
        else:
            t['usage'] = None
        t['input_image_blocks'] = sum(e['input_image_blocks'] for e in t['tool_envelopes'])
        t['actual_tool_call_count']=sum(not e['kind'].endswith('_output') for e in t['tool_envelopes'])
        t['actual_tool_output_count']=sum(e['kind'].endswith('_output') for e in t['tool_envelopes'])
        t['actual_tool_output_text_utf8_bytes']=sum(e['actual_tool_output_text_utf8_bytes'] for e in t['tool_envelopes'])
        t['actual_tool_output_text_blocks']=sum(len(e['public_tool_text_blocks']) for e in t['tool_envelopes'])
        calls = {e['call_id']:e for e in t['tool_envelopes'] if not e['kind'].endswith('_output')}
        for e in t['tool_envelopes']:
            start = calls.get(e['call_id'])
            if start and e['kind'].endswith('_output'):
                a,b = start.get('actual_create_time'),e.get('actual_create_time')
                e['inclusive_tool_envelope_seconds'] = b-a if isinstance(a,(int,float)) and isinstance(b,(int,float)) else None
    return dict(meta=meta,turns=turns,selected_metadata=selected,
        source=dict(path=str(path).replace('\\','/'),bytes=after.st_size,mtime_ns=after.st_mtime_ns,
                    selected_nonreasoning_metadata_sha256=sha(blob(selected)),full_rollout_sha256=None,
                    hash_scope='canonical whitelist metadata only; hidden reasoning not copied or hashed as semantic content'),
        skipped_reasoning_or_analysis_lines=skipped)


def timing_values(value, prefix=''):
    out = []
    if isinstance(value,dict):
        for k,v in value.items():
            q = f'{prefix}.{k}' if prefix else k
            if (k.endswith('_ns') or k.endswith('_s')) and type(v) in (int,float):
                out.append(dict(field=q,value=v))
            elif k in ('spans','telemetry','native','host_execution','observability','result','observation'):
                out.extend(timing_values(v,q))
    elif isinstance(value,list):
        for i,v in enumerate(value):
            out.extend(timing_values(v,f'{prefix}[{i}]'))
    return out


def actor_records(workspace):
    perf = []
    for p in workspace.glob('perf000_calls/*/AUDIT.json'):
        folder=p.parent
        audit=load(p);request=load(folder/'REQUEST.json');reply=load(folder/'REPLY.json')
        result=reply.get('result') or {}
        stdout=result.get('stdout') if isinstance(result,dict) else None
        perf.append(dict(request_id=request.get('request_id'),operation=request.get('operation'),request=request,
            audit=audit,audit_source=evidence(p),request_source=evidence(folder/'REQUEST.json'),reply_source=evidence(folder/'REPLY.json'),
            stdout=stdout,stdout_utf8_bytes=None if stdout is None else len(stdout.encode('utf8')),
            stdout_sha256=None if stdout is None else sha(stdout.encode('utf8')),
            result_image_refs=(result.get('image_refs') if isinstance(result,dict) else None),
            response_ok=reply.get('ok'),operation_succeeded=reply.get('operation_succeeded'),
            model_image_consumption_confirmed=reply.get('model_image_consumption_confirmed'),
            phase_measurements=timing_values(reply),broker=None))
    perf.sort(key=lambda x:x['audit'].get('started_ns',0))
    broker=[]
    for p in workspace.glob('broker_calls/*/FULL_RESULT.json'):
        request=load(p.parent/'REQUEST.json');reply=load(p)
        row=dict(request_id=request.get('request_id'),operation=request.get('operation'),request_source=evidence(p.parent/'REQUEST.json'),
            full_result_source=evidence(p),phase_measurements=timing_values(reply),
            operation_succeeded=reply.get('operation_succeeded'),ok=reply.get('ok'))
        broker.append(row)
        for call in perf:
            if call['request_id']==row['request_id']:
                call['broker']=row
    # Direct underlying worker stdout/scripts are evidence, not proof they were
    # returned to a model. Crosslink by exact stdout text when possible.
    workers=[]
    for p in sorted(workspace.glob('call_*/stdout.txt')):
        raw=p.read_bytes();text=raw.decode('utf-8-sig')
        item=dict(stdout_source=evidence(p),script_source=evidence(p.parent/'SCRIPT.py') if (p.parent/'SCRIPT.py').exists() else None,
                  stderr_source=evidence(p.parent/'stderr.txt') if (p.parent/'stderr.txt').exists() else None)
        workers.append(item)
        for call in perf:
            if call['stdout'] is not None and text.replace('\r\n','\n')==call['stdout'].replace('\r\n','\n'):
                call['underlying_worker_output']=item
    metadata={}
    for name in ('SESSION.json','BROKER_READY.json','BROKER_STATE.json','COORDINATOR_CLOSE.json','WORKER_CLOSED.json'):
        p=workspace/name
        if p.exists():metadata[name]=dict(source=evidence(p),value=load(p))
    return dict(perf_calls=perf,broker_calls=broker,worker_outputs=workers,owner_metadata=metadata,
                control_broker_calls_not_consumer_operations=[r for r in broker if r['request_id'] not in {x['request_id'] for x in perf}])


def normalize_stdout(s):
    return s.replace('\r\n','\n').rstrip('\n')


def public_turn(turn):
    commands=[];finals=[];comments=[];other=[]
    for item in turn.get('items',[]):
        kind=item.get('type')
        if kind=='reasoning' or (kind=='agentMessage' and item.get('phase')=='analysis'):
            raise ValueError('read_thread snapshot was not sanitized')
        if kind=='agentMessage':
            row=dict(item_id=item.get('id'),phase=item.get('phase'),text=item.get('text',''))
            (finals if item.get('phase')=='final_answer' else comments).append(row)
        elif kind=='commandExecution':
            value=item.get('output') or {}
            text=value.get('text','')
            commands.append(dict(item_id=item.get('id'),command=item.get('command'),cwd=item.get('cwd'),
                status=item.get('status'),exit_code=item.get('exitCode'),command_duration_ms=item.get('durationMs'),
                actual_public_output=text,public_output_utf8_bytes=len(text.encode('utf8')),
                public_output_sha256=sha(text.encode('utf8')),output_truncated=value.get('truncated'),
                bytes_scope='read_thread included output text; lower bound if output_truncated=true'))
        else:
            other.append(item)
    return dict(turn_id=turn['id'],status=turn.get('status'),error=turn.get('error'),
        started_at=turn.get('startedAt'),completed_at=turn.get('completedAt'),duration_ms=turn.get('durationMs'),
        commands=commands,final_answers=finals,commentary=comments,other_public_items=other,
        command_returned_text_utf8_bytes=sum(c['public_output_utf8_bytes'] for c in commands))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--agent-map',type=Path,default=BASE/'AGENT_MAP.json')
    ap.add_argument('--sessions-root',type=Path,default=Path('C:/Users/Administrator/.codex/sessions'))
    ap.add_argument('--snapshots',type=Path,default=HERE/'read_thread')
    ap.add_argument('--revision',required=True)
    args=ap.parse_args()
    if not re.fullmatch(r'[0-9A-Za-z_-]+',args.revision):raise ValueError('invalid revision')
    out=HERE/f'EXTRACTED_{args.revision}.json'
    manifest=HERE/f'MANIFEST_{args.revision}.json'
    if out.exists() or manifest.exists():raise FileExistsError('revision already exists; preserve prior evidence')
    mapping=load(args.agent_map)
    authority_plan=evidence(BASE/'FROZEN_AUDIT_PLAN.json')
    if authority_plan['sha256']!=PLAN_SHA256:raise ValueError('frozen audit plan changed')
    paths=subprocess.run(['rg','--files','-uu',str(args.sessions_root)],check=True,capture_output=True,text=True,encoding='utf8').stdout.splitlines()
    agents=[];gaps=[]
    for assigned in mapping['agents']:
        thread=assigned['thread_id']
        if not UUID.fullmatch(thread):raise ValueError('invalid exact thread UUID')
        matches=[Path(p) for p in paths if Path(p).name.endswith('-'+thread+'.jsonl')]
        if len(matches)!=1:raise ValueError('exact rollout UUID not unique: '+thread)
        candidates=sorted(args.snapshots.glob(thread+'_*.json'))
        if not candidates:
            gaps.append(dict(thread_id=thread,reason='missing codex_app.read_thread nonreasoning snapshot'))
            continue
        snap_path=candidates[-1];snapshot=load(snap_path)
        if snapshot.get('tool')!='codex_app.read_thread' or snapshot['result']['thread']['id']!=thread:
            raise ValueError('snapshot exact tool/thread mismatch')
        if snapshot['result'].get('page',{}).get('hasMore'):
            raise ValueError('snapshot incomplete pagination: '+thread)
        host=rollout_metadata(matches[0],thread)
        if assigned.get('agent_path') and host['meta']['agent_path']!=assigned['agent_path']:
            raise ValueError('agent path binding mismatch')
        workspace=Path(assigned['workspace']).resolve()
        if not workspace.is_relative_to(BASE/'runs'):raise ValueError('workspace outside authorized run tree')
        actor=actor_records(workspace)
        turns=[public_turn(t) for t in reversed(snapshot['result']['turns'])]
        stages=assigned['stages']
        if len(turns)!=len(stages):raise ValueError('stage/turn count mismatch: '+thread)
        matched_requests=set()
        for turn,stage in zip(turns,stages):
            turn['stage']=stage
            meta=host['turns'].get(turn['turn_id'])
            if not meta:raise ValueError('app turn missing in exact rollout')
            turn['host_metadata']=meta
            turn['model_provider_alias']=host['meta']['model_provider']
            turn['actual_backend_or_Pro_identity_verified']=False
            turn['provider_request_count']=None;turn['USD']=None
            for command in turn['commands']:
                text=command['actual_public_output']
                candidates=[c for c in actor['perf_calls'] if c['request_id'] not in matched_requests and c['stdout'] is not None and normalize_stdout(c['stdout'])==normalize_stdout(text)]
                if len(candidates)==1:
                    call=candidates[0];matched_requests.add(call['request_id'])
                    command['actor_call']=call
                    command['crosslink']='Exact public stdout after CRLF normalization; request/source artifacts retained separately.'
                else:
                    command['actor_call']=None
                    command['crosslink']='No unique raw stdout match; do not infer call binding or physical phase totals.'
            complete=meta.get('completed') or {}
            turn['app_and_event_duration_match']=turn['duration_ms']==complete.get('duration_ms')
            turn['image_count_scope']='Actual structured input_image blocks in nonreasoning rollout tool outputs; paths and constructed images do not count.'
        agents.append(dict(assignment=assigned,read_thread_snapshot=evidence(snap_path),
            rollout=host['source'],session_metadata=host['meta'],
            skipped_reasoning_or_analysis_lines=host['skipped_reasoning_or_analysis_lines'],
            turns=turns,actor=actor,
            unbound_actor_calls=[c['request_id'] for c in actor['perf_calls'] if c['request_id'] not in matched_requests]))
    result=dict(schema='perf000-actual-host-measurement-v1',revision=args.revision,
        generated_utc=datetime.now(timezone.utc).isoformat(),agent_map=evidence(args.agent_map),authority_plan=authority_plan,
        source_extractor=evidence(Path(__file__)),agents=agents,gaps=gaps,
        scopes=dict(public_answer_and_command_text_source='codex_app.read_thread sanitized nonreasoning snapshots only; unchanged originals',
            all_public_tool_output_text_source='Exact UUID rollout nonreasoning function/custom_tool output blocks, including pure functions.exec local math; separately measured from CLI stdout',
            metadata_source='Exact UUID rollout session_meta/turn_context/token_count/task start+complete and nonreasoning public tool inputs/outputs',
            usage='Sum verified cumulative deltas per turn; last_usage retained for comparison, never added again. Cached input/reasoning output remain subsets.',
            phase_costs='Tool/actor/native intervals nest inside task wall; do not sum nested spans or call uncovered wall inference-only time.',
            partial_text='read_thread truncation flags retained; source stdout alone does not prove whole output was actually received',
            model_identity='Reported host aliases/settings only; exact backend revision, Pro identity, provider requests and USD unverified/unexposed',
            scoring='none; no task quality judgments',new_model_calls=0,new_blender_calls=0))
    new_json(out,result)
    new_json(manifest,dict(schema='perf000-extraction-output-manifest-v1',revision=args.revision,
                          output=evidence(out),extractor=evidence(Path(__file__)),agent_map=evidence(args.agent_map)))
    print(json.dumps(dict(output=str(out),agents=len(agents),turns=sum(len(a['turns']) for a in agents),
        gaps=gaps,sha256=evidence(out)['sha256'],new_model_calls=0,new_blender_calls=0)))


if __name__=='__main__':main()
