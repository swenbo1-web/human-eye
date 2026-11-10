"""Anonymous tool evidence for the existing answer IDs; pure postprocessing.

Original model arguments/code are never redacted. Administrative metadata is
removed from returns, measured elapsed/seconds numbers are masked in stdout,
and only explicit diagnostic File lines/config warnings have neutral paths.
Every removal and raw-file hash is retained in a separate private provenance.
"""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import tempfile

HERE=Path(__file__).resolve().parent
NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
TIMING=re.compile(r'\b(?P<label>elapsed(?:_seconds|_s)?|seconds|duration(?:_seconds|_s)?)\b(?P<sep>\s*[:=]\s*|\s+)(?P<number>'+NUMBER+r')',re.I)
STACK_FILE=re.compile(r'(?m)^(?P<before>\s*File ")(?P<file>[^"\r\n]+)(?P<after>", line \d+[^\r\n]*)$')
TIME_KEYS={'elapsed','elapsed_s','elapsed_seconds','seconds','duration','duration_s','duration_seconds',
    'time_seconds','time_s','timing','timings','usage','usage_rows','token_usage','input_tokens','output_tokens',
    'cached_input_tokens','total_tokens','fees','cost','costs'}
PIN_KEYS={'runtime_source_sha256','host_source_sha256','source_sha256','build_id','source_files',
    'launcher_sha256','admin_sha256','binding_sha256','trace_id','request_trace','execution_trace'}
ADMIN_KEYS={'base_version','implementation_revision','distribution_version','version','schema_version',
    'protocol_version','entry','path','python','dependency_python','module_root','installed_root','target_release',
    'invocation_prefix','module_origins','source_file_count','source_count','scene_revision','scene_fingerprint',
    'document_epoch','generation_id','instance_id'}
ADMIN_CONTEXT={'binding','identity','runtime_identity','source','context','provenance','runtime','serverInfo'}


def decode(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('duplicate_json_key:'+key)
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite_json:'+x)))


def load(path):return decode(Path(path).read_bytes())
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def file_sha(path):return sha(Path(path).read_bytes())
def output_bytes(value):return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf8')


class Redactor:
    def __init__(self,source,removals):self.source=source;self.removals=removals
    def note(self,pointer,rule,value,**extra):
        self.removals.append({'source_file':str(self.source),'source_sha256':file_sha(self.source) if self.source else None,
            'pointer':pointer,'rule':rule,'original_value_sha256':sha(canonical(value)),**extra})
    def structured(self,value,pointer='$',admin=False):
        if isinstance(value,dict):
            result={}
            for key,item in value.items():
                path=pointer+'.'+key
                # Real query/arguments/code remain visible, even when they
                # contain suspicious paths or administrative-looking fields.
                if key in ('arguments','query','code'):
                    result[key]=item;continue
                rule=None
                if key=='_meta':rule='MCP_envelope_meta'
                elif key in PIN_KEYS:rule='administrative_source_pin_or_trace'
                elif key=='host_identity':rule='administrative_host_identity'
                elif key in TIME_KEYS or key.endswith(('_ns','_ms')):rule='administrative_timing_or_usage'
                elif admin and key in ADMIN_KEYS:rule='administrative_identity_version_path'
                if rule:self.note(path,rule,item)
                else:result[key]=self.structured(item,path,admin or key in ADMIN_CONTEXT)
            return result
        if isinstance(value,list):return [self.structured(item,pointer+'['+str(i)+']',admin) for i,item in enumerate(value)]
        if isinstance(value,str):return self.text(value,pointer)
        return value
    def text(self,text,pointer='$'):
        stripped=text.strip()
        if stripped.startswith(('{','[')):
            try:parsed=decode(stripped)
            except (ValueError,TypeError):pass
            else:
                value=self.structured(parsed,pointer+'::<JSON>')
                if value==parsed:return text
                return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+text[len(text.rstrip()):]
        lines=text.splitlines(keepends=True);result=[];protect_source_line=False
        for line_number,line in enumerate(lines):
            point=pointer+'::<line:'+str(line_number+1)+'>'
            match=STACK_FILE.match(line.rstrip('\r\n'))
            if match:
                original=match['file'];self.note(point,'diagnostic_stack_filepath_only',original)
                result.append(line[:match.start('file')]+'<diagnostic-file>'+line[match.end('file'):]);protect_source_line=True;continue
            if protect_source_line:
                # The code line under a traceback File entry must remain
                # verbatim, including real file-read paths and constants.
                result.append(line);protect_source_line=False;continue
            # JSON lines are handled structurally; no coordinate number is
            # selected merely because it happens to look like a duration.
            trim=line.strip()
            if trim.startswith(('{','[')):
                try:parsed=decode(trim)
                except (ValueError,TypeError):pass
                else:
                    value=self.structured(parsed,point+'::<JSON>')
                    result.append(line if value==parsed else json.dumps(value,ensure_ascii=False,separators=(',',':'))+line[len(line.rstrip('\r\n')):]);continue
            def mask(match):
                self.note(point,'explicit_elapsed_seconds_measured_number',match['number'],span=[match.start('number'),match.end('number')],label=match['label'])
                return match['label']+match['sep']+'<timing-redacted>'
            result.append(TIMING.sub(mask,line))
        return ''.join(result)
    def diagnostic(self,text,pointer):
        value=self.text(text,pointer)
        # This is a CLI diagnostic configuration warning, never model code or
        # a query. Other ordinary/file-read paths are deliberately untouched.
        pattern=re.compile(r'(?i)[A-Z]:\\[^\r\n]*?\\\.codex\\config\.toml')
        def mask(match):self.note(pointer,'diagnostic_CLI_configuration_path',match.group());return '<diagnostic-config>'
        return pattern.sub(mask,value)


def code_audit(code):
    flags=[]
    try:tree=ast.parse(code)
    except SyntaxError as exc:return [{'kind':'unparsed_model_code','line':exc.lineno}]
    sensitive=re.compile(r'(?i)(TRUTH|verification[/\\]|\.codex|\.human-eye|__file__|human_eye_plugin|[A-Z]:[/\\]|/tmp|/home)')
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            name=ast.unparse(node.func);leaf=name.rsplit('.',1)[-1]
            if leaf in {'open','read_text','read_bytes','write_text','write_bytes','exec','eval','compile','system','popen','Popen','load','listdir','glob','rglob'}:
                flags.append({'kind':'file_or_dynamic_code_access_for_review','line':node.lineno,'code':ast.get_source_segment(code,node)})
            if name.startswith('bpy.ops.') or leaf in {'save_mainfile','save_as_mainfile','frame_set'}:
                flags.append({'kind':'possible_scene_write_for_review','line':node.lineno,'code':ast.get_source_segment(code,node)})
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and sensitive.search(node.value):
            flags.append({'kind':'management_or_file_path_literal_for_review','line':node.lineno,'literal':node.value})
        if isinstance(node,(ast.Import,ast.ImportFrom)) and re.search(r'\b(os|pathlib|subprocess|inspect|human_eye_plugin)\b',ast.unparse(node)):
            flags.append({'kind':'filesystem_or_runtime_import_for_review','line':node.lineno,'code':ast.get_source_segment(code,node)})
    return flags


def projected_request(request,redactor):
    if request.get('method')!='tools/call':raise ValueError('only_actual_tools_call_request_expected')
    params=request['params']
    if set(params)-{'_meta','name','arguments'}:raise ValueError('unrecognized_MCP_params_do_not_silently_drop')
    for key in ('jsonrpc','id'):
        if key in request:redactor.note('$.'+key,'MCP_transport_envelope',request[key])
    if '_meta' in params:redactor.note('$.params._meta','MCP_envelope_meta',params['_meta'])
    return {'method':params['name'],'arguments':params.get('arguments',{})}


def sources_record(path,provenance):
    path=Path(path);provenance[str(path)]=file_sha(path);return load(path)


def expected_mesh(spec):
    raw=load(spec['initial']);raw=raw.get('initial',raw)
    return {'unit_scale_m':raw['unit_scale_m'],'objects':[{'name':obj['name'],'vertices_local':obj['vertices_local'],
        'matrix_world':obj['matrix_world'],'faces':obj.get('faces',obj.get('triangles'))} for obj in raw['objects']]}


def snapshot_receipt(path):
    receipt=load(path);response=receipt['response']
    if response['status']!='success' or response['result']['executed'] is not True:raise ValueError('snapshot_receipt_not_success')
    return decode(response['result']['result'])


def state_checks(folder,spec,protocol_state,consumer,provenance):
    owner=folder/'owner';initial=sources_record(owner/'INITIAL.json',provenance);final=sources_record(owner/'FINAL.json',provenance)
    for name in ('INITIAL.json.receipt.json','FINAL.json.receipt.json'):sources_record(owner/name,provenance)
    close=sources_record(owner/'CLOSE.json',provenance);finish=sources_record(folder/'OWNER_FINISH.json',provenance)
    native=close.get('native_close') or {};plugin=close.get('plugin_close');worker=close.get('worker_closed') or {}
    expected=expected_mesh(spec);provenance[spec['initial']]=file_sha(spec['initial']);provenance[spec['asset']]=file_sha(spec['asset'])
    initial_frozen=initial==expected
    receipt_bound=(snapshot_receipt(owner/'INITIAL.json.receipt.json')==initial and snapshot_receipt(owner/'FINAL.json.receipt.json')==final)
    actual_source_file_unchanged=file_sha(spec['asset'])==spec['asset_sha256']
    close_bound=finish.get('close')==close and consumer.get('owner_finish')==finish
    checks={'initial_matches_registered_frozen_mesh_exactly':initial_frozen,'initial_final_mesh_exactly_equal':initial==final,
        'actual_snapshot_receipts_match':receipt_bound,'registered_source_asset_bytes_unchanged':actual_source_file_unchanged,
        'owner_close_receipt_bound':close_bound,'owner_close_confirmed':close.get('confirmed') is True and finish.get('confirmed') is True,
        'all_attached_backends_closed_and_reaped':bool(native.get('process_reaped') and native.get('exit_code')==0 and worker
            and (plugin is None or plugin.get('confirmed'))),
        'worker_initial_final_geometry_fingerprint_equal':worker.get('initial_geometry_fingerprint')==worker.get('final_geometry_fingerprint'),
        'consumer_process_reaped':consumer.get('process_reaped') is True,'consumer_readers_stopped':consumer.get('readers_stopped') is True,
        'attached_client_cleanup_confirmed':consumer.get('bridge_cleanup',{}).get('confirmed') is True,
        'no_reported_mutation_unknown':consumer.get('mutation_unknown') is False,
        'no_bridge_protocol_errors':consumer.get('bridge_protocol_errors')==[],
        'root_protocol_prefinal_checks_agree':bool(protocol_state.get('initial_final_exact')==(initial==final)
            and protocol_state.get('source_file_unchanged')==actual_source_file_unchanged
            and protocol_state.get('owner_normal_close')==(close.get('confirmed') is True)),
        'mesh_check_scope':'full ordered local vertices, world matrices, oriented triangle faces and units; no full-array duplication in this packet',
        'readonly_limit':'unchanged final mesh and source asset do not by themselves prove absence of every transient in-memory operation'}
    return checks,close


def answer_evidence(root,answer,mapping,plan,protocol_state,provenance,removals):
    folder=root/'cells'/mapping['cell'];owner=folder/'owner';consumer=sources_record(folder/'CONSUMER.json',provenance)
    if file_sha(folder/'CONSUMER.json')!=mapping['consumer_sha256']:raise ValueError('consumer_drift_after_final_anonymization')
    if consumer['final']!=answer['text'] or consumer['valid_completion']!=answer['delivered']:raise ValueError('anonymous_final_binding_changed')
    public=folder/'PUBLIC_FINAL.txt';provenance[str(public)]=file_sha(public)
    if public.read_bytes()!=answer['text'].encode('utf8') or file_sha(public)!=mapping['public_final_sha256']:raise ValueError('PUBLIC_FINAL_binding_changed')
    event_path=folder/'events.jsonl';provenance[str(event_path)]=file_sha(event_path)
    events=[decode(line) for line in event_path.read_bytes().splitlines() if line]
    projected=[{'perf_ns':e['perf_ns'],'type':e['event']['type'],'item':e['event']['item']} for e in events
        if e['event'].get('type') in ('item.started','item.completed') and e['event'].get('item',{}).get('type')=='mcp_tool_call']
    if projected!=consumer['public_events']:raise ValueError('raw_events_public_tool_projection_mismatch')
    completed=[e for e in projected if e['type']=='item.completed'];started=[e for e in projected if e['type']=='item.started']
    if completed!=consumer['tool_calls'] or len(started)!=len(completed):raise ValueError('incomplete_or_mismatching_tool_lifecycle')
    tools=sources_record(owner/'TOOLS.json',provenance);folders=sorted(owner.glob('tool_*'))
    if len(folders)!=len(completed) or len(tools['tools'])!=len(completed) or tools['attempts']!=len(completed):raise ValueError('tool_denominator_mismatch')
    checks,close=state_checks(folder,plan['tasks'][answer['task_id']],protocol_state,consumer,provenance)
    if close['tools']!=tools['tools'] or close['tool_attempts']!=len(completed):raise ValueError('tool_close_log_mismatch')
    calls=[];flags=[];previous=None
    for i,(directory,event,start) in enumerate(zip(folders,completed,started)):
        request_path=directory/'REQUEST.json';request=sources_record(request_path,provenance)
        request_redactor=Redactor(request_path,removals);projected_request_value=projected_request(request,request_redactor)
        item=event['item'];before=start['item'];args=projected_request_value['arguments'];method=projected_request_value['method']
        if item['tool']!=method or item['arguments']!=args or before['tool']!=method or before['arguments']!=args or item['id']!=before['id']:
            raise ValueError('model_public_request_actual_owner_binding_mismatch')
        candidates=[p for p in (directory/'RESPONSE.json',directory/'ERROR_RESPONSE.json') if p.is_file()]
        if len(candidates)!=1:raise ValueError('one_actual_tool_response_required')
        response_path=candidates[0];response=sources_record(response_path,provenance);result=response.get('result')
        if item.get('result',{}).get('content')!=result.get('content'):raise ValueError('actual_return_public_model_content_mismatch')
        if item.get('result',{}).get('structured_content') is not None:raise ValueError('unrecognized_extra_public_structured_content')
        attempt=sources_record(directory/'ATTEMPT.json',provenance)
        if attempt!=tools['tools'][i] or attempt['attempt']!=i+1 or attempt['name']!=method:raise ValueError('attempt_order_or_result_log_mismatch')
        redactor=Redactor(response_path,removals)
        for key in ('id','jsonrpc'):
            if key in response:redactor.note('$.'+key,'MCP_transport_envelope',response[key])
        native_receipt=directory/'NATIVE_RECEIPT.json'
        if native_receipt.is_file():
            native=sources_record(native_receipt,provenance)
            if len(result['content'])!=1 or decode(result['content'][0]['text'])!=native['response']:raise ValueError('Native_receipt_response_mismatch')
        call={'sequence':i+1,**projected_request_value,'response':redactor.structured(result),
            'model_call_status':item.get('status'),'model_call_error':redactor.structured(item.get('error'),'$.public_call_error'),
            'actual_is_error':attempt['is_error'],'owner_exception':redactor.structured(attempt['exception'],'$.owner_exception')}
        if previous and previous['method']!=method:
            call['method_transition']={'from':previous['method'],'previous_call_failed':previous['actual_is_error'],
                'native_after_failed_other_method':method=='execute_blender_code' and previous['method']!='execute_blender_code' and previous['actual_is_error']}
        if isinstance(args.get('code'),str):
            found=code_audit(args['code'])
            if found:flags.append({'sequence':i+1,'findings':found})
        calls.append(call);previous=call
    diagnostics=[];diagnostic_redactor=Redactor(event_path,removals)
    for event in events:
        item=event['event'].get('item',{})
        if item.get('type')=='error':diagnostics.append({'type':'consumer_diagnostic','message':diagnostic_redactor.diagnostic(item.get('message',''),'$.event.error.message')})
    checks['model_requests_and_actual_returns_bound_to_public_events']=True
    checks['all_tool_attempts_including_errors_retained']=True
    evidence={'task_id':answer['task_id'],'answer_id':answer['answer_id'],'calls':calls,'consumer_diagnostics':diagnostics,
        'consumer_errors':Redactor(folder/'CONSUMER.json',removals).structured(consumer.get('errors',[]),'$.errors'),
        'code_access_and_write_review_flags':flags,'checks':checks}
    return evidence,{'code_review_flags':flags,'tool_calls':len(calls),'checks':checks,'consumer_source':str(folder/'CONSUMER.json')}


def build(root):
    root=Path(root).resolve();blind=root/'blind';target=blind/'tools';private_path=root/'private/TOOL_EVIDENCE_PROVENANCE.json';index_path=blind/'TOOL_EVIDENCE_INDEX.json'
    if target.exists() or private_path.exists() or index_path.exists():raise FileExistsError('anonymous_tool_outputs_are_exclusive_never_overwritten')
    answers_path=blind/'ANSWERS.json';answers_blob=answers_path.read_bytes();answers=decode(answers_blob)['answers']
    mapping_path=root/'private/BLIND_MAP.json';mapping=load(mapping_path);plan=load(root/'PLAN.json');run=load(root/'RUN_RESULT.json')
    if len(answers)!=18 or len(mapping['answers'])!=18 or len(run['cells'])!=18 or not run.get('ended_ns'):raise ValueError('same_complete_18_answer_denominator_required')
    if mapping['plan_sha256']!=file_sha(root/'PLAN.json') or mapping['run_result_sha256']!=file_sha(root/'RUN_RESULT.json'):raise ValueError('final_blind_input_binding_changed')
    if len({a['answer_id'] for a in answers})!=18 or {a['answer_id'] for a in answers}!=set(mapping['answers']):raise ValueError('same_unique_random_answer_ids_required')
    protocol_path=root/'private/PROTOCOL_PREFINAL.json';protocol=load(protocol_path);states={row['cell']:row for row in protocol['states']}
    provenance={str(answers_path):sha(answers_blob),str(mapping_path):file_sha(mapping_path),str(root/'PLAN.json'):file_sha(root/'PLAN.json'),
        str(root/'RUN_RESULT.json'):file_sha(root/'RUN_RESULT.json'),str(protocol_path):file_sha(protocol_path)}
    removals=[];packets=[];index=[];audit={}
    for answer in answers:
        key=answer['answer_id'];hidden=mapping['answers'][key]
        if answer['task_id']!=hidden['task_id']:raise ValueError('task_answer_mapping_changed')
        packet,summary=answer_evidence(root,answer,hidden,plan,states[hidden['cell']],provenance,removals)
        packets.append((key,packet));index.append({'task_id':answer['task_id'],'answer_id':key,'evidence':'tools/'+key+'.json','tool_calls':len(packet['calls'])})
        audit[key]={**hidden,**summary}
    # Pin/version/path leakage scan excludes original model args, which must
    # remain visible even if they themselves reveal misconduct or a route.
    def returned_only(packet):return {'calls':[{k:v for k,v in call.items() if k!='arguments'} for call in packet['calls']],
        'consumer_diagnostics':packet['consumer_diagnostics'],'checks':packet['checks']}
    canonical_pins=['a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b',
        '3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd']
    for key,packet in packets:
        text=json.dumps(returned_only(packet),ensure_ascii=False)
        if any(pin in text for pin in canonical_pins) or 'scale.baseline.lab' in text or 'scale.opt.r1' in text:raise ValueError('unresolved_administrative_return_leak:'+key)
    target.mkdir(exist_ok=False)
    for key,packet in packets:
        with (target/(key+'.json')).open('xb') as stream:stream.write(output_bytes(packet))
    with index_path.open('xb') as stream:stream.write(output_bytes({'answers':index}))
    private={'schema':'complex004-private-tool-evidence-provenance-v1','script_sha256':file_sha(__file__),
        'anonymous_final_sha256_before':sha(answers_blob),'anonymous_final_sha256_after':file_sha(answers_path),
        'raw_files_sha256':provenance,'answers':audit,'removals':removals,
        'rules':['Original model arguments/code copied as parsed JSON values without field or text redaction',
            'Only MCP envelope jsonrpc/id/params._meta omitted from requests; request method and all arguments retained',
            'All actual return content/error flags and chronological calls retained, with explicit administrative metadata removal',
            'Structured timing/usage and source pin/version/path fields removed; real query/arguments/code subtrees untouched',
            'Native text: only explicit elapsed/seconds/duration-labelled measured numbers masked; geometry numbers remain',
            'Traceback File diagnostic filenames neutralized; following model source line and actual file-read paths retained',
            'CLI configuration-warning path neutralized; all suspicious model access/write code is retained and flagged',
            'Lifecycle mesh evidence recomputed from full raw snapshots/receipts and compared with frozen inputs; hashes remain private',
            'No rubric, semantic scoring, cost, group, experimental order or source hashes are published in the evidence index'],
        'published_files_sha256':{str(p):file_sha(p) for p in [index_path,*sorted(target.glob('*.json'))]},
        'tool_calls':sum(row['tool_calls'] for row in index),'suspicious_answers':[key for key,summary in audit.items() if summary['code_review_flags']],
        'model_calls':0,'product_calls':0,'Blender_calls':0,'scoring_calls':0}
    if private['anonymous_final_sha256_after']!=private['anonymous_final_sha256_before']:raise ValueError('original_anonymous_finals_changed')
    with private_path.open('xb') as stream:stream.write(output_bytes(private))
    return {'answers':18,'tool_calls':private['tool_calls'],'index_sha256':file_sha(index_path),'private_provenance_sha256':file_sha(private_path),
        'suspicious_answers':private['suspicious_answers'],'final_answers_unchanged':True,'removal_records':len(removals),
        'model_calls':0,'product_calls':0,'Blender_calls':0,'scoring_calls':0}


def self_test():
    with tempfile.TemporaryDirectory(prefix='complex004-evidence-fake-') as temp:
        source=Path(temp)/'fake.json';source.write_text('{}',encoding='utf8');records=[];r=Redactor(source,records)
        code='print(open("D:/private/TRUTH.json").read())\nprint("elapsed", 0.2)\n'
        request={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'_meta':{'group':'C','usage':100},'name':'execute_blender_code','arguments':{'code':code,'query':{'path':'keep','source_sha256':'keep'}}}}
        projected=projected_request(request,r);assert projected['arguments']==request['params']['arguments'] and projected['arguments']['code']==code
        assert code_audit(code) and '_meta' not in projected
        value={'binding':{'runtime_source_sha256':'remove','version':'remove','path':'remove','currentness':'capture_snapshot'},'distance_m':.003,'elapsed_ns':5,'usage':{'output_tokens':2},'query':{'source_sha256':'keep'}}
        clean=r.structured(value);assert clean=={'binding':{'currentness':'capture_snapshot'},'distance_m':.003,'query':{'source_sha256':'keep'}}
        text='geometry_count 48 elapsed 0.25\ngap 0.003 normal [0.2, 0.4, 0.8]\nseconds 0.75 candidate count 47\n'
        clean=r.text(text);assert 'elapsed <timing-redacted>' in clean and 'seconds <timing-redacted>' in clean and 'gap 0.003 normal [0.2, 0.4, 0.8]' in clean
        clean=r.text('{"elapsed_s":0.2,"distance_m":0.003}\n');assert decode(clean)=={'distance_m':.003}
        stack='Traceback (most recent call last):\n  File "D:/host/runtime.py", line 7, in go\n    print(open("D:/private/TRUTH.json").read())\nValueError: bad\n'
        clean=r.text(stack);assert '<diagnostic-file>' in clean and 'D:/host/runtime.py' not in clean and 'D:/private/TRUTH.json' in clean
        assert all(row['source_sha256']==file_sha(source) for row in records)
        assert set({'task_id':'task','answer_id':'random','evidence':'tools/random.json','tool_calls':1})=={'task_id','answer_id','evidence','tool_calls'}
        return {'passed':True,'fake_only':True,'checks':['model_code_and_query_verbatim','truth_read_preserved_and_flagged',
            'MCP_meta_not_real_args_removed','structured_admin_only_removed','stdout_only_timing_numbers_masked',
            'JSON_timing_fields_removed_geometry_kept','diagnostic_path_only_not_code_line','private_removal_provenance_bound'],
            'actual_output_created':False,'model_calls':0,'product_calls':0,'Blender_calls':0,'scoring_calls':0}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=HERE);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    print(json.dumps(self_test() if args.self_test else build(args.root),ensure_ascii=False))


if __name__=='__main__':main()
