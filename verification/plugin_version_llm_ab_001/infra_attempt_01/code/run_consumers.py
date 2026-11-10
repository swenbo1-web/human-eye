"""Twelve fixed fresh Pro-login consumers; no model starts on import.

This controller forwards prompts, records public CLI lifecycle/tool output,
and checks owned cleanup. It neither solves geometry nor grades an answer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
EXE=Path('C:/Users/Administrator/AppData/Local/Programs/OpenAI/Codex/bin/codex.exe')
EXE_SHA='01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
USAGE=('input_tokens','cached_input_tokens','output_tokens','total_tokens',
       'reasoning_tokens','reasoning_output_tokens')
EXPECTED_TOOLS={'describe_task','run_arm_goal'}
KNOWN_TOOL_TYPES={'command_execution','mcp_tool_call','custom_tool_call','function_call',
                  'web_search','image_view','file_change','todo_list','collab_tool_call'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def save(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.next')
    tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf8',newline='\n')
    os.replace(tmp,path)
def toml(value):
    if isinstance(value,dict):return '{'+','.join(json.dumps(k)+'='+toml(v) for k,v in value.items())+'}'
    if isinstance(value,list):return '['+','.join(toml(v) for v in value)+']'
    return json.dumps(value,ensure_ascii=True)


def safe_environment(source):
    excluded={'CODEX_THREAD_ID','CODEX_SESSION_ID','CODEX_TOOL_CALL_ID','APP_TOOLS_PIPE_PATH',
        'CODEX_APP_TOOLS_PIPE_PATH','CODEX_TASK_WORKSPACE_VERIFYING_IDENTITY','CODEX_PERMISSION_PROFILE',
        'OPENAI_API_KEY','CODEX_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY','PYTHONPATH'}
    return {key:source[key] for key in source if key.upper() not in excluded
            and not key.upper().endswith(('_API_KEY','_ACCESS_TOKEN'))}


def settings():
    value={'model':'gpt-6.1-sol','model_reasoning_effort':'medium','model_provider':'openai_http',
        'service_tier':'default','model_providers.openai_http':{'name':'OpenAI','wire_api':'responses',
            'requires_openai_auth':True,'supports_websockets':False,'supports_standalone_web_search':True,
            'base_url':'https://chatgpt.com/backend-api/codex'},'forced_login_method':'chatgpt',
        'hide_agent_reasoning':True,'show_raw_agent_reasoning':False,'web_search':'disabled',
        'features.hooks':False,'features.apps':False,'features.memories':False,'memories.use_memories':False,
        'features.multi_agent':False,'features.multi_agent_v2':False,'features.goals':False,
        'features.remote_plugin':False,'features.plugins':False,'features.skip_host_skill_discovery':True,
        'skills.bundled.enabled':False,'skills.include_instructions':False,'project_doc_max_bytes':0,
        'features.shell_tool':False,'features.view_image':False,'sandbox_mode':'read-only','approval_policy':'never'}
    for name in ('codex-app-tools@openai-bundled','visualize@openai-bundled',
        'documents@openai-primary-runtime','pdf@openai-primary-runtime','spreadsheets@openai-primary-runtime',
        'presentations@openai-primary-runtime','template-creator@openai-primary-runtime',
        'agent-learning@agent-learning-local'):
        value['plugins.'+json.dumps(name)+'.enabled']=False
    return value


def argv_for(python,cell,work,final):
    config=settings()
    config['mcp_servers.arm_engine']={'command':str(python),'args':['-I','-B',str(HERE/'bridge.py'),
        '--cell',str(cell)],'cwd':str(work),'required':True,'startup_timeout_sec':90,'tool_timeout_sec':90,
        'enabled_tools':sorted(EXPECTED_TOOLS),
        'tools':{name:{'approval_mode':'approve'} for name in sorted(EXPECTED_TOOLS)}}
    argv=[str(EXE),'exec','--ignore-user-config','--ignore-rules','--ephemeral','--strict-config',
        '--json','--skip-git-repo-check','-C',str(work),'--color','never']
    for key,value in config.items():argv+=['-c',key+'='+toml(value)]
    return argv+['-m','gpt-6.1-sol','-o',str(final),'-']


def kill_owned_tree(process):
    receipt={'pid':None if process is None else process.pid,'tree_kill_requested':False,
             'taskkill_returncode':None,'parent_reaped':process is None,'parent_exit':None}
    if process is None:return receipt
    if process.poll() is None:
        receipt['tree_kill_requested']=True
        try:
            stop=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=5,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            receipt['taskkill_returncode']=stop.returncode
        except (OSError,subprocess.TimeoutExpired) as error:receipt['tree_kill_error']=repr(error)
        if process.poll() is None:process.kill()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    receipt['parent_reaped']=process.poll() is not None;receipt['parent_exit']=process.poll()
    return receipt


def wait_bridge_closed(cell,seconds=15):
    path=Path(cell['audit_dir'])/'BRIDGE_RESULT.json';deadline=time.perf_counter()+seconds
    while time.perf_counter()<deadline:
        if path.exists():
            try:value=read(path)
            except (OSError,ValueError):value={}
            if value.get('closed'):
                process=value.get('process_exit',{})
                return {'confirmed':bool(process.get('closed') and process.get('returncode')==0),
                    'closed':value['closed'],'process_exit':process,'source_unchanged':value.get('source_unchanged'),
                    'blend_unchanged':value.get('blend_sha256_before')==value.get('blend_sha256_after')}
        time.sleep(.05)
    return {'confirmed':False,'reason':'bridge_close_receipt_missing_or_late'}


def consume(slot,install,plan,prompt):
    folder=HERE/'cells'/slot['cell'];cell_path=folder/'cell.json';cell=read(cell_path)
    work=ROOT/'.plugin_ab_runtime/consumer_workspaces'/slot['cell'];work.mkdir(parents=True,exist_ok=True)
    assert not list(work.iterdir()),'fresh_empty_consumer_workspace_required'
    final=folder/'final.txt';argv=argv_for(install['python'],cell_path,work,final)
    began=time.perf_counter_ns();deadline=began+int(plan['max_session_seconds']*1e9)
    record={**slot,'status':'running','started_ns':began,'deadline_ns':deadline,
        'argv':argv,'consumer_pid':None,'popen_ns':None,'prompt_submitted_ns':None,'prompt_write_started_ns':None,
        'final_received_ns':None,'turn_completed_ns':None,'process_exit_ns':None,'cleanup_end_ns':None,
        'usage':None,'usage_rows':[],'thread_id':None,'tool_calls':[],'public_events':[],
        'all_public_messages':[],'final':None,'errors':[],'unexpected_tool_deviations':[],
        'provider_retry_observations':[],'provider_requests':None,'fees':None,'model':'gpt-6.1-sol',
        'requested_effort':'medium','resolved_effort':None,'process_reaped':False,
        'input_text_bytes':len(prompt),'input_sha256':hashlib.sha256(prompt).hexdigest(),
        'public_image_bytes':0,'public_image_count':0,'valid_completion':False,'safe_to_continue':False}
    save(folder/'CONSUMER.json',record)
    process=None;readers=[];timer=None;fired=threading.Event();events=queue.Queue();closed=0
    def expire():
        fired.set()
        if process is not None and process.poll() is None:kill_owned_tree(process)
    def reader(stream,label):
        try:
            for raw in iter(stream.readline,b''):events.put((label,raw,time.perf_counter_ns()))
        except BaseException as error:events.put(('reader_error',repr(error).encode(),time.perf_counter_ns()))
        finally:events.put((label,None,time.perf_counter_ns()))
    try:
        timer=threading.Timer(max(0.,(deadline-time.perf_counter_ns())/1e9),expire);timer.daemon=True;timer.start()
        record['popen_ns']=time.perf_counter_ns()
        process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            cwd=work,env=safe_environment(os.environ),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        record['consumer_pid']=process.pid
        for label,stream in (('stdout',process.stdout),('stderr',process.stderr)):
            thread=threading.Thread(target=reader,args=(stream,label),daemon=True);thread.start();readers.append(thread)
        record['prompt_write_started_ns']=time.perf_counter_ns();process.stdin.write(prompt);process.stdin.close()
        record['prompt_submitted_ns']=time.perf_counter_ns()
        with (folder/'events.jsonl').open('w',encoding='utf8',newline='\n') as public_log, \
                (folder/'stderr.raw.bin').open('wb') as stderr_raw, \
                (folder/'stderr_lines.jsonl').open('w',encoding='utf8',newline='\n') as stderr_log:
            while closed<2:
                left=(deadline-time.perf_counter_ns())/1e9
                if left<=0 or fired.is_set():raise TimeoutError('original_360s_absolute_session_deadline')
                try:label,raw,received=events.get(timeout=min(.1,left))
                except queue.Empty:continue
                if raw is None:closed+=1;continue
                if label=='stderr':
                    stderr_raw.write(raw);stderr_raw.flush()
                    text=raw.decode('utf8',errors='replace')
                    stderr_log.write(json.dumps({'perf_ns':received,'text':text},ensure_ascii=False)+'\n');stderr_log.flush()
                    if any(word in text.lower() for word in ('retry','reconnect','429','503','rate limit','quota','usage limit')):
                        record['provider_retry_observations'].append({'perf_ns':received,'source':'stderr','text':text})
                    continue
                if label=='reader_error':raise RuntimeError(raw.decode())
                record['stdout_bytes']=record.get('stdout_bytes',0)+len(raw)
                try:event=json.loads(raw)
                except (ValueError,UnicodeError) as error:
                    with (folder/'stdout_unparsed.bin').open('ab') as malformed:malformed.write(raw)
                    record.setdefault('stdout_unparsed_lines',[]).append({'perf_ns':received,
                        'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
                    raise ValueError('non_JSON_CLI_stdout_line_retained') from error
                kind=event.get('type');item=event.get('item',{})
                # Hide agent reasoning is set. Retain only a hash/count if the
                # CLI nevertheless emits a reasoning body; never export it.
                if item.get('type') in ('reasoning','analysis'):
                    logged={'type':kind,'item':{'type':item['type'],'redacted':True},
                        'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)}
                else:logged=event
                public_log.write(json.dumps({'perf_ns':received,'event':logged},ensure_ascii=False)+'\n');public_log.flush()
                if kind=='thread.started':record['thread_id']=event.get('thread_id')
                if kind in ('error','turn.failed'):
                    record['errors'].append({'perf_ns':received,'event':event})
                if kind=='turn.completed':
                    usage=event.get('usage');record['turn_completed_ns']=received
                    if type(usage) is dict:
                        numeric={k:usage[k] for k in USAGE if k in usage}
                        if any(type(v) is not int or v<0 for v in numeric.values()):raise ValueError('invalid_actual_usage')
                        record['usage']=numeric;record['usage_rows'].append(numeric)
                if kind in ('item.started','item.completed'):
                    if item.get('type') in KNOWN_TOOL_TYPES:
                        projected={'perf_ns':received,'type':kind,'item':item};record['public_events'].append(projected)
                        if item.get('type')!='mcp_tool_call' or item.get('server')!='arm_engine' or item.get('tool') not in EXPECTED_TOOLS:
                            record['unexpected_tool_deviations'].append(projected)
                        if kind=='item.completed' and item.get('type')=='mcp_tool_call':record['tool_calls'].append(projected)
                    if item.get('type')=='agent_message' and kind=='item.completed':
                        text=item.get('text','');record['all_public_messages'].append({'perf_ns':received,'id':item.get('id'),'text':text})
                        record['final']=text;record['final_received_ns']=received
            process.wait(timeout=max(.01,(deadline-time.perf_counter_ns())/1e9))
            record['process_exit_ns']=time.perf_counter_ns()
        if record['final'] is not None:
            # Preserve the public item bytes as the answer even if -o is absent.
            record['cli_output_file_present']=final.exists()
            record['cli_output_matches_public_final']=None if not final.exists() else final.read_text(encoding='utf8')==record['final']
            (folder/'PUBLIC_FINAL.txt').write_bytes(record['final'].encode('utf8'))
        record['valid_completion']=bool(process.returncode==0 and record['thread_id']
            and record['turn_completed_ns'] and record['final_received_ns'] and not fired.is_set()
            and record['turn_completed_ns']<deadline and not record['errors'] and not record['unexpected_tool_deviations'])
    except BaseException as error:record['errors'].append({'type':type(error).__name__,'message':str(error)})
    finally:
        if timer is not None:timer.cancel();timer.join(timeout=15)
        record['process_cleanup']=kill_owned_tree(process)
        record['process_reaped']=process is not None and process.poll() is not None
        record['exit_code']=None if process is None else process.poll()
        if record['process_exit_ns'] is None and record['process_reaped']:record['process_exit_ns']=time.perf_counter_ns()
        for thread in readers:thread.join(timeout=1)
        record['readers_stopped']=all(not thread.is_alive() for thread in readers)
        record['deadline_timer_fired']=fired.is_set()
        record['bridge_cleanup']=wait_bridge_closed(cell)
        bridge_path=Path(cell['audit_dir'])/'BRIDGE_RESULT.json'
        bridge=read(bridge_path) if bridge_path.exists() else {}
        unknown=any(call.get('result',{}).get('status')=='execution_uncertain' for call in bridge.get('calls',[]))
        record['mutation_unknown']=unknown
        record['bridge_protocol_errors']=bridge.get('protocol_errors',[])
        record['safe_to_continue']=bool(record['process_reaped'] and record['readers_stopped']
            and record['bridge_cleanup'].get('confirmed') and not unknown and not record['bridge_protocol_errors'])
        record['cleanup_end_ns']=time.perf_counter_ns();record['wall_ns']=record['cleanup_end_ns']-began
        record['prompt_to_final_ns']=None if record['final_received_ns'] is None or record['prompt_submitted_ns'] is None else record['final_received_ns']-record['prompt_submitted_ns']
        record['public_text_bytes']=sum(len(row['text'].encode('utf8')) for row in record['all_public_messages'])
        record['output_text_bytes']=None if record['final'] is None else len(record['final'].encode('utf8'))
        record['status']='completed' if record['valid_completion'] else 'failed'
        record['bridge_public_text_bytes']=bridge.get('public_text_bytes')
        save(folder/'CONSUMER.json',record)
    return record


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true',required=True)
    args=parser.parse_args();plan=read(HERE/'PLAN.json');installs=read(HERE/'INSTALL_RESULT.json')
    assert args.execute and plan['cycle_id']=='PLUGIN-VERSION-LLM-AB-001'
    assert plan['model']=='gpt-6.1-sol' and plan['requested_effort']=='medium'
    assert len(plan['sequence'])==plan['max_new_consumers']==12 and installs['passed']
    assert sha(EXE)==EXE_SHA,'fixed_current_CLI_changed'
    prompt=(HERE/'PROMPT.txt').read_bytes();assert hashlib.sha256(prompt).hexdigest()==plan['prompt_sha256']
    for name,digest in read(HERE/'PLAN_FREEZE.json').items():assert sha(HERE/name)==digest,name
    cell_freeze=read(HERE/'CELLS_FREEZE.json')
    assert len(cell_freeze['rows'])==12
    for slot,binding in zip(plan['sequence'],cell_freeze['rows']):
        assert all(binding[k]==slot[k] for k in ('cell','task','pair','version'))
        folder=HERE/'cells'/slot['cell'];cell=read(folder/'cell.json')
        assert sha(folder/'cell.json')==binding['cell_sha256']
        assert sha(Path(cell['fixture_input']))==binding['fixture_sha256']
        install=installs['versions'][slot['version']]
        assert Path(cell['expected_install_root']).resolve()==Path(install['installed_root']).resolve()
        assert Path(binding['workspace']).resolve()==(ROOT/'.plugin_ab_runtime/consumer_workspaces'/slot['cell']).resolve()
    freeze=read(HERE/'RUNNER_FREEZE.json')
    assert freeze['runner_sha256']==sha(Path(__file__)) and freeze['bridge_sha256']==sha(HERE/'bridge.py')
    assert freeze['initializer_sha256']==sha(HERE/'initializer.py') and freeze['plan_sha256']==sha(HERE/'PLAN.json')
    claim=HERE/'CONSUMERS_STARTED.json'
    with claim.open('x',encoding='utf8') as stream:json.dump({'started_ns':time.perf_counter_ns(),'max_consumers':12,'no_resampling':True},stream)
    result={'schema':'plugin-version-llm-ab-consumers-v1','cycle_id':plan['cycle_id'],'denominator':12,
        'started_ns':time.perf_counter_ns(),'consumers_started':0,'consumers_attempted':0,'cells':[],
        'fees':None,'provider_requests':None,'model_replacement':False,'new_user_config_writes':0}
    stop=None
    for slot in plan['sequence']:
        if stop:record={**slot,'status':'not_run','reason':stop,'valid_completion':False}
        else:
            result['consumers_attempted']+=1
            try:record=consume(slot,installs['versions'][slot['version']],plan,prompt)
            except BaseException as error:
                record={**slot,'status':'failed','valid_completion':False,'safe_to_continue':False,
                    'errors':[{'type':type(error).__name__,'message':str(error)}]}
            if record.get('consumer_pid') is not None:result['consumers_started']+=1
            if not record.get('safe_to_continue'):stop='owned_cleanup_bridge_or_unknown_execution_blocked'
            elif record.get('exit_code')!=0:stop='consumer_nonzero_requires_review_no_automatic_retry'
            elif record.get('errors'):stop='consumer_error_requires_review_no_automatic_retry'
        result['cells'].append(record);save(HERE/'RUN_RESULT.json',result)
        print(json.dumps({k:record.get(k) for k in ('cell','task','version','status','prompt_to_final_ns','usage')},ensure_ascii=False),flush=True)
    result['ended_ns']=time.perf_counter_ns();result['stop_reason']=stop
    save(HERE/'RUN_RESULT.json',result)


if __name__=='__main__':main()
