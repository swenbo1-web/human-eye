"""Independent read-only raw protocol/termination/ledger audit.

No author scorer, validator, actor, model, renderer or runtime is imported.
Known matching rules are independently reconstructed from the frozen source.
"""
import copy
import hashlib
import json
from pathlib import Path

BASE=Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe/verification/m4_active_coverage_consumption_001')
OUT=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
checks=[]; inputs={}; runs={}; pairs=[]
def raw(path):
    path=Path(path);data=path.read_bytes();inputs[str(path)]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};return data
def read(path):return json.loads(raw(path))
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)
def check(name,ok,detail=None):checks.append({'name':name,'passed':bool(ok),'detail':detail})

def old_success(response,item):
    # Independent transcription of the small old success-only rule, not import.
    if type(response)is not dict or 'error'in response or type(item)is not dict:return False
    owner=response.get('result');actual=item.get('result')
    if type(owner)is not dict or type(actual)is not dict:return False
    if set(owner)!={'content','isError'} or owner['isError']is not False:return False
    if item.get('status')!='completed' or 'error'not in item or item['error']is not None:return False
    if type(owner['content'])is not list or type(actual.get('content'))is not list:return False
    if set(actual)=={'content','isError'}:
        if actual['isError']is not False:return False
    elif set(actual)=={'content','structured_content'}:
        if actual['structured_content']is not None:return False
    else:return False
    return canonical(owner['content'])==canonical(actual['content'])

def existing_result_gate(response,item):
    return canonical(response.get('result'))==canonical(item.get('result')) or old_success(response,item)

source={name:raw(BASE/name).decode('utf8') for name in ('consumer.py','driver.py','actor.py','image_content.py','runtime_handle.py','ledger_controls.py')}
old=raw(ROOT/'verification/m4_surface_scan_continuous_interface_fix_001/compatibility.py').decode('utf8')
check('success_rule_explicitly_excludes_error',"owner['isError'] is not False"in old and "item.get('status') != 'completed'"in old)
check('archive_exact_equality_bypasses_status',"packer.encoded(response.get('result')) != packer.encoded(item.get('result'))"in source['consumer.py'])
check('post_construct_cost_commits_before_late_checks',source['image_content.py'].index('receipt["constructed"] = True') < source['image_content.py'].index('on_constructed(receipt)') < source['image_content.py'].index('base64.b64decode(payload'))
check('actor_uses_actual_construction_callback','on_constructed=self.record_constructed'in source['actor.py'])
check('actor_preserves_constructed_failures','if error.receipt["constructed"]:'in source['actor.py'] and 'self.post_construction_failures.append(error.receipt)'in source['actor.py'])
check('outer_gate_now_requires_continue_and_image_faults',"row.get('consumer_safe_to_continue')"in source['driver.py'] and "and not row['common_image_faults']"in source['driver.py'])
check('runtime_binding_once_after_started','runtime_binding_attempted = True'in source['consumer.py'] and 'after_stdio_STARTED=True'in source['runtime_handle.py'] and "proof.pop('before_stdin', None)"in source['runtime_handle.py'])
check('exit_wait_retains_original_deadline','WaitForSingleObject(handle, milliseconds)'in source['runtime_handle.py'] and "row['closed_ns'] < deadline_ns"in source['runtime_handle.py'])

for slot in ('N1','P1','P2','N2','N3','P3'):
    folder=BASE/'r'/slot; row=read(folder/'RESULT.json'); c=read(folder/'c/CONSUMER.json')
    timing=read(folder/'FINAL_TIMING.json');tools=read(folder/'o/TOOLS.json')['tools']
    stdout=raw(folder/'c/stdout.raw.bin');events=[json.loads(line)for line in stdout.splitlines()]
    completed=[e['item']for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
    top_errors=[e for e in events if e.get('type')in ('error','turn.failed')]
    check(slot+'/actual_CLI_tool_count',len(completed)==len(c['tool_calls'])==len(tools))
    check(slot+'/original_stdout_bound',len(stdout)==c['stdout_raw_bytes'] and hashlib.sha256(stdout).hexdigest()==c['stdout_raw_sha256'])
    expected_failure=slot in ('N1','N3')
    check(slot+'/original_strict_status_preserved',row['outer_valid_completion']is(not expected_failure) and c['valid_completion']is(not expected_failure))
    check(slot+'/no_shared_image_fault',row['common_image_faults']==[] and row['stop_remaining_reasons']==[])
    check(slot+'/terminal_error_count',len(top_errors)==int(slot=='N3'))
    if slot=='N3':check(slot+'/actual_reconnect',top_errors[0]['type']=='error' and 'Reconnecting... 1/5' in top_errors[0]['message'] and 'error decoding response body' in top_errors[0]['message'])
    finals=[e['item']['text']for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
    check(slot+'/public_answer_bound',bool(finals) and finals[-1]==c['final']==raw(folder/'c/PUBLIC_FINAL.txt').decode('utf8'))
    check(slot+'/one_terminal_completed',len([e for e in events if e.get('type')=='turn.completed'])==1)
    bindings=[]
    for tool,observed,item in zip(tools,c['tool_calls'],completed):
        attempt=tool['attempt'];p=folder/'o'/('tool_'+str(attempt).zfill(2));request=read(p/'REQUEST.json');response=read(p/'RESPONSE.json')
        label=slot+'/tool'+str(attempt)
        check(label+'/raw_CLI_matches_record',item==observed['item'])
        check(label+'/request_identity',request['id']==response['id'] and request['params']['name']==item['tool'] and canonical(request['params']['arguments'])==canonical(item['arguments']))
        owner=response['result'];actual=item['result'];error=owner['isError']
        check(label+'/same_business_content',canonical(owner['content'])==canonical(actual['content']))
        check(label+'/observed_semantic_projection',type(error)is bool and item['status']==('failed'if error else'completed') and item['error']is None and set(actual)=={'content','structured_content'} and actual['structured_content']is None)
        accepted=existing_result_gate(response,item)
        check(label+'/old_gate_result_matches_diagnosis',accepted is(not error))
        if error:
            parsed=json.loads(owner['content'][0]['text']);expected_type='SyntaxError'if slot=='N1'else'ValueError'
            check(label+'/actual_business_error_type',parsed['error']['type']==expected_type)
            check(label+'/later_tool_and_final',attempt<len(tools) and c['final_received_ns']>observed['perf_ns'])
            bindings.append(dict(attempt=attempt,type=expected_type,text_bytes=len(owner['content'][0]['text'].encode('utf8')),
                                 content_equal=True,old_rule_accepted=accepted,CLI_status=item['status']))
        pairs.append(dict(slot=slot,attempt=attempt,owner_error=error,old_gate=accepted))
    expected_binding=[{'attempt':d['attempt'],'reason':'CLI_result_differs_from_owner'}for d in bindings]
    actual_binding=[e['errors']for e in c['errors']if e.get('stage')=='business_original_binding']
    check(slot+'/binding_errors_exact',actual_binding==([expected_binding]if bindings else []))
    if slot=='N1':check(slot+'/only_protocol_projection_error',len(c['errors'])==1)
    if slot=='N3':check(slot+'/network_error_independent_of_projection',len(c['errors'])==2)
    binding=read(folder/'c/RUNTIME_BINDING.json');exit_row=c['runtime_exit']
    starts=list((folder/'c/attachments').glob('bridge_*/STARTED.json'));check(slot+'/one_stdio_start',len(starts)==1)
    started=read(starts[0]);chain=binding['parent_chain']
    check(slot+'/binding_same_across_records',binding==c['runtime_binding']==row['runtime_binding'])
    check(slot+'/actual_lifetime_bound',binding['confirmed']is True and binding['runtime_pid']==started['pid']==chain[0]['pid'] and binding['launcher_pid']==c['process_cleanup']['pid']==chain[-1]['pid'])
    check(slot+'/ancestry_birth_order',binding['parent_edges']==len(chain)-1<=4 and all(a['created_filetime']>=b['created_filetime']for a,b in zip(chain,chain[1:])))
    check(slot+'/actual_base_image',Path(binding['actual_executable'])==Path(binding['expected_executable']) and binding['actual_executable_sha256']==binding['expected_executable_sha256'])
    check(slot+'/truthful_binding_time',binding['after_stdio_STARTED']is True and 'before_stdin'not in binding and started['started_ns']<=binding['observed_ns']<=binding['proved_ns']<=binding['actual_image_checked_ns']<c['final_received_ns'])
    check(slot+'/actual_thin_exit_handle',exit_row['confirmed']is True and exit_row['exited']is True and exit_row['handle_closed']is True and exit_row['error']is None and exit_row['closed_ns']<row['deadline_ns'] and row['runtime_exit']==exit_row)
    check(slot+'/stdio_EOF_retained_unknown',c['bridge_cleanup']['confirmed']is None and c['bridge_cleanup']['missing_exit_count']==1 and not(starts[0].parent/'EXIT.json').exists())
    for name,cleanup in [('CLI',c['process_cleanup']),('actor',row['owner_process_cleanup'])]:
        check(slot+'/'+name+'_original_handle_closed',cleanup['confirmed']is True and cleanup['reaped']is True and cleanup['process_handle_closed']is True and all(cleanup['pipes_closed'].values()) and not cleanup['errors'] and cleanup['exit_code']==0)
    check(slot+'/safe_to_continue_after_exit',c['safe_to_continue']is True and row['consumer_safe_to_continue']is True)
    runs[slot]=dict(original_outer_accepted=row['outer_valid_completion'],business_errors=bindings,top_level_errors=top_errors,
        CLI_exit=c['exit_code'],thin_exit=exit_row['exit_code'],thin_graceful_EOF='unknown',continued_safely=c['safe_to_continue'],
        final_present=True,final_received_ns=c['final_received_ns'],runtime_exit_observed_ns=exit_row['closed_ns'])

ledger=read(BASE/'local_ledger/a01/RESULTS.json')
for row in ledger['cases']:
    name=row['case'];metrics=row['metrics'];original=read(BASE/'local_ledger/a01'/name/'METRICS.json')
    check('ledger/'+name+'/actual_metrics_match',metrics==original)
    check('ledger/'+name+'/one_constructed_no_refund',metrics['constructed_image_blocks']==1 and metrics['constructed_PNG_bytes']==ledger['fixture_PNG_bytes'] and metrics['constructed_base64_chars']==4*((ledger['fixture_PNG_bytes']+2)//3))
    check('ledger/'+name+'/no_network_or_render',metrics['server_socket_sent_image_blocks']==0 and row['actual_render_attempts']==row['actual_network_sends']==0)
    check('ledger/'+name+'/post_construct_separate',metrics['post_construction_failures']==int(name in ('post_encode_deadline','post_construct_serialization')) and metrics['failed_image_constructions']==0)
    if name=='post_encode_deadline':check('ledger/final_deadline_point',row['deadline_checks']==3 and row['returned_image_blocks']==0)
    if name=='post_construct_serialization':check('ledger/unknown_JSON_preserved',metrics['constructed_image_JSON_bytes_unknown_count']==1)
    if name=='post_construct_send':check('ledger/send_failure_retained',metrics['failed_or_unknown_socket_sends']==1)

local=read(BASE/'local/a01/LOCAL_CHECK.json');check('local/recorded_controls_passed',all(c['passed']for c in local['checks']))
for name,expected_code,eof in [('normal_EOF',0,True),('forced_no_EXIT',1,None)]:
    c=read(BASE/'local/a01'/name/'c/CONSUMER.json')
    check('local/'+name+'/actual_exit',c['runtime_exit']['confirmed']is True and c['runtime_exit']['handle_closed']is True and c['runtime_exit']['exit_code']==expected_code)
    check('local/'+name+'/EOF_separate',c['bridge_cleanup']['confirmed']is eof)
    check('local/'+name+'/same_runtime_binding',c['runtime_binding']['confirmed']is True and c['runtime_binding']['after_stdio_STARTED']is True)

fixture_response=read(BASE/'local/a01/shared_fault_controls/ordinary_tool_error/tool_01/RESPONSE.json')
check('local_error_control_not_actual_CLI_projection',"'status': 'failed', 'result': result"in source['driver.py'] and "observed = common_image_faults(record, owner)"in source['driver.py'])
item={'status':'failed','error':None,'result':copy.deepcopy(fixture_response['result'])}
check('same_envelope_error_accepted_by_equality',existing_result_gate(fixture_response,item))
contradictory=copy.deepcopy(item);contradictory['status']='completed'
check('latent_status_contradiction_bypass',existing_result_gate(fixture_response,contradictory))

result=dict(author_commit='52d9a838fd52074f3df157aba97e29a5c0cde924',scope='Independent raw records plus pure reconstructed protocol branch checks; no author engine/scorer/validator execution.',
    new_process_model_renderer_Blender_calls=0,input_files=len(inputs),checks_count=len(checks),checks=checks,failed=[c for c in checks if not c['passed']],
    runs=runs,tool_pairs=pairs,known_error_projection_count=sum(p['owner_error']for p in pairs),
    next='One minimal business-result projection fix with status consistency and exact content, tested against all15 stored tool pairs plus negative controls. No new Pro benchmark or old-status rewrite.',
    retained_unknown=['stdio graceful EOF/cause (actual exit observed)','N3 pre-disconnect usage coverage/provider internal attempts','resolved provider model/effort'],
    limitations=['Local ledger and lifecycle controls are reviewed from original records and source, not rerun by this reviewer.','Pure contradictory-status example is an unobserved fixture, not a real false acceptance in these15 tools.'])
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'RESULTS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'INPUTS.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items()if k in ('input_files','checks_count','failed','known_error_projection_count')}))
