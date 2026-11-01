"""A1c: frozen native reference plus untimed HE functional eligibility only."""
import argparse,base64,hashlib,json,math,queue,statistics,subprocess,sys,threading,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT))


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def run(args):
    from verification.engineering_task_contract import bootstrap,digest
    identity,_=bootstrap(args.entry,baseline='region_v3')
    from verification.engineering_qualification import registration,BUILD,ASSETS,HELPERS,normalize,select,quality,eligibility
    from verification.engineering_evidence import ArchiveCursor,check_images
    from verification.engineering_baseline_cases import cases
    from human_eye_plugin.structure_task_control import begin,close
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    registered=registration();save(output/'REGISTRATION.json',registered);reg_path=output/'REGISTRATION.json'
    reg_sha=hashlib.sha256(reg_path.read_bytes()).hexdigest()
    selected=cases();assert {c['id']:c['asset_task_sha256'] for c in selected}==ASSETS
    helpers={str(ROOT/'verification'/n):hashlib.sha256((ROOT/'verification'/n).read_bytes()).hexdigest() for n in HELPERS}
    save(output/'REGISTERED_INPUT.json',dict(registration_sha256=reg_sha,engine_build=BUILD,helpers=helpers,
        public_assets=[{k:c[k] for k in ('id','objects','task','asset_task_sha256')} for c in selected]))
    save(output/'PRIVATE_ORACLES.json',selected)
    frozen=output/'FROZEN_HELPERS';frozen.mkdir()
    for path,expected in helpers.items():
        raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==expected;(frozen/Path(path).name).write_bytes(raw)
    native_rows=[];he_rows=[];processes=[];failures=[]
    for purpose,phase in registered['phases'].items():
        arm=phase['arm'];measured=arm=='native'
        for case in selected:
            for repeat in range(phase['rounds']):
                folder=output/(arm+'_'+case['id']+'_'+str(repeat));folder.mkdir()
                save(folder/'ASSET.json',{k:case[k] for k in ('id','objects','task','asset_task_sha256')})
                base=dict(qualification_registration=str(reg_path),qualification_sha256=reg_sha,purpose=purpose,arm=arm,
                    case_id=case['id'],asset_task_sha256=case['asset_task_sha256'],helpers=helpers)
                save(folder/'SERVER_SPEC.json',dict(base,site=str(args.entry.parents[1]/'site-packages')))
                out=(folder/'BLENDER.stdout').open('xb');err=(folder/'BLENDER.stderr').open('xb');stream=None;host=None;mcp=None
                responses=[];cursor=ArchiveCursor(folder);task_start=time.perf_counter_ns() if measured else None
                try:
                    host=subprocess.Popen([str(args.blender),'--factory-startup','--background','--disable-autoexec','--python-exit-code','3',
                        '--python',str(ROOT/'verification/engineering_owned_server.py'),'--',str(folder)],stdout=out,stderr=err,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    end=time.monotonic()+30
                    while not (folder/'READY.json').exists():
                        if host.poll() is not None or time.monotonic()>=end:raise ValueError('owned_host_not_ready')
                        time.sleep(.01)
                    ready=json.loads((folder/'READY.json').read_text());assert ready['port']!=9876
                    startup=(time.perf_counter_ns()-task_start)/1e6 if measured else None
                    config=folder/'CONFIG.json';pin={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind','protocol_version','mode')}
                    save(config,dict(schema_version='1.0',enabled=True,project_root=str(args.entry.parents[1]/'site-packages'),
                        state_file='STATE.json',audit_file='AUDIT.jsonl',structure_task_file='TASK.json',structure_task_control_file='CONTROL.json',
                        expected_identity=pin,structure_region_mode='summary_v1',structure_patch_mode='nonplanar_dense_v1',quad_size=64,max_sessions=4,
                        blender=dict(host='127.0.0.1',port=ready['port'],timeout_s=30)))
                    spec=folder/'SPEC.json';save(spec,dict(base,entry=str(args.entry),config=str(config),config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
                        host='127.0.0.1',port=ready['port'],peer_nonce=ready['peer_nonce'],source_sha256=ready['source_sha256']))
                    stream=(folder/'MCP.stderr').open('xb')
                    mcp=subprocess.Popen([sys.executable,'-I','-B',str(ROOT/'verification/engineering_stdio.py'),str(spec)],stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,stderr=stream,text=True,encoding='utf8',cwd=folder,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    replies=queue.Queue()
                    def reader():
                        try:
                            for line in mcp.stdout:replies.put(line)
                        finally:replies.put(None)
                    threading.Thread(target=reader,daemon=True).start()
                    def rpc(method,params=None):
                        request=dict(jsonrpc='2.0',id=len(responses)+1,method=method)
                        if params is not None:request['params']=params
                        wire=json.dumps(request)+'\n';started=time.perf_counter_ns() if measured else None
                        mcp.stdin.write(wire);mcp.stdin.flush();line=replies.get(timeout=35)
                        if line is None:raise ValueError('MCP_exit_before_response')
                        response=json.loads(line);archives=cursor.collect()
                        record=dict(request=request,response=response,request_bytes=len(wire.encode()),response_bytes=len(line.encode()),host_replies=len(archives))
                        if measured:record['ms']=(time.perf_counter_ns()-started)/1e6
                        responses.append(record)
                        if 'error' in response:raise ValueError('MCP_error:'+str(response['error']))
                        return response['result'],archives
                    initialized,_=rpc('initialize');assert initialized['_meta']['human_eye']['source_sha256']==BUILD
                    tools,_=rpc('tools/list');assert len(tools['tools'])==4
                    for task_id in range(phase['tasks']):
                        if task_id:
                            task_start=time.perf_counter_ns() if measured else None
                        mark=time.perf_counter_ns() if measured else None
                        handoff=begin(config,'qualification-'+str(task_id),ready['object_id'],categories=case['task']['categories'])
                        begin_ms=(time.perf_counter_ns()-mark)/1e6 if measured else None
                        start_response=0 if task_id==0 else len(responses);start_archive=cursor.next;start_archive_bytes=cursor.bytes
                        def observe(request_id,ref=None,images=False):
                            query=dict(mode='mesh_structure',operation='patch' if ref else 'diagnose',request_id=request_id,task_ref=handoff['task_ref'])
                            if ref:query['patch_ref']=ref
                            reply,archives=rpc('tools/call',dict(name='human_eye_scene_observe',arguments=dict(query=query,include_image=images)))
                            value=json.loads(reply['content'][0]['text'])
                            if reply.get('isError'):raise ValueError('observe_error:'+str(value))
                            return value,reply,archives
                        diagnostic,_,_=observe('diagnose');norm=normalize(diagnostic,arm)
                        selection=select(norm,case['task']['anchor_world_bu']);evidence=dict(images=0,png_bytes=0,pixels=None)
                        image_status='not_requested';ref=None
                        if selection['status']=='selected':
                            ref=selection['region']['patch_ref'];visual,reply,archives=observe('patch',ref,True)
                            # Each fresh reply must preserve task fact totals and
                            # all published members; receipts carry no fresh facts.
                            fresh=normalize(visual,arm);assert fresh==norm
                            evidence=check_images(case,arm,reply,archives,folder/('task_'+str(task_id)+'_images'))
                            image_status=visual['image_status']
                            before=cursor.next;receipt,_,_=observe('patch',ref,True)
                            assert receipt['status']=='receipt' and not receipt['current_evidence'] and cursor.next==before
                            exhausted,reply,_=observe('exhausted',ref,True)
                            assert exhausted['image_status']=='budget_exhausted' and not any(b['type']=='image' for b in reply['content'])
                            assert normalize(exhausted,arm)==norm
                        elif selection['status']!='empty':raise ValueError('public_selection_unknown')
                        assessment=quality(case,norm,selection,evidence['pixels'],evidence['images'])
                        mark=time.perf_counter_ns() if measured else None;closed=close(config,handoff['task_ref'])
                        close_ms=(time.perf_counter_ns()-mark)/1e6 if measured else None
                        elapsed=(time.perf_counter_ns()-task_start)/1e6 if measured else None
                        assert closed['task_budget']['spent']['queries']==(3 if ref else 1)
                        assert closed['task_budget']['spent']['images']<=2
                        task_replies=responses[start_response:]
                        public_text=sum(len(b['text'].encode()) for r in task_replies for b in r['response'].get('result',{}).get('content',[]) if b['type']=='text')
                        row=dict(case=case['id'],round=repeat,task=task_id,first=task_id==0,selection=selection['status'],quality=assessment,
                            images=evidence['images'],pixels=evidence['pixels'],image_status=image_status,received_png_bytes=evidence['png_bytes'],
                            public_text_utf8_bytes=public_text,stdio_request_bytes=sum(r['request_bytes'] for r in task_replies),
                            stdio_response_bytes=sum(r['response_bytes'] for r in task_replies),host_replies=cursor.next-start_archive,
                            consumed_archive_bytes=cursor.bytes-start_archive_bytes,task_budget=closed['task_budget'],lifecycle_passed=True,
                            published_members=norm['published_members'])
                        if measured:
                            row.update(complete_task_ms=elapsed,timing=dict(host_startup_ms=startup if task_id==0 else 0,begin_ms=begin_ms,close_ms=close_ms,
                                rpc_and_archive_consume_ms=sum(r['ms'] for r in task_replies)))
                            native_rows.append(row)
                        else:he_rows.append(row)
                    denied,_=rpc('tools/call',dict(name='human_eye_scene_observe',arguments=dict(include_image=False,
                        query=dict(mode='mesh_structure',operation='diagnose',request_id='afterclose',task_ref=handoff['task_ref']))))
                    assert denied['isError'];mcp.stdin.close();assert mcp.wait(timeout=10)==0
                except Exception as exc:
                    failure=dict(arm=arm,case=case['id'],round=repeat,error=repr(exc),denominator_preserved=True)
                    failures.append(failure);save(folder/'FAILURE.json',failure)
                finally:
                    save(folder/'RESPONSES.json',responses)
                    if mcp is not None and mcp.poll() is None:mcp.kill();mcp.wait(timeout=5)
                    if stream:stream.close()
                    (folder/'STOP').write_text('qualification complete')
                    if host is not None:
                        try:host.wait(timeout=10)
                        except subprocess.TimeoutExpired:host.kill();host.wait(timeout=5)
                    out.close();err.close()
                    state=json.loads((folder/'SERVER_RESULT.json').read_text()) if (folder/'SERVER_RESULT.json').exists() else {}
                    process=dict(arm=arm,case=case['id'],round=repeat,host_pid=None if host is None else host.pid,
                        host_exit=None if host is None else host.returncode,mcp_pid=None if mcp is None else mcp.pid,mcp_exit=None if mcp is None else mcp.returncode,
                        source_unchanged=state.get('source_unchanged',False),display_restored=state.get('display_restored',False))
                    processes.append(process);save(folder/'PROCESS.json',process)
    stats=[]
    for case in ASSETS:
        for first in (True,False):
            values=sorted(r['complete_task_ms'] for r in native_rows if r['case']==case and r['first']==first)
            if values:stats.append(dict(case=case,first=first,n=len(values),median_ms=statistics.median(values),p95_ms=values[math.ceil(.95*len(values))-1]))
    gate=eligibility(native_rows,he_rows,processes)
    result=dict(stage='M2-A1c',registration_sha256=reg_sha,engine_build=BUILD,native_rows=native_rows,he_functional_rows=he_rows,
        processes=processes,failures=failures,stats=stats,eligibility=gate,HE_paired_cost_trials=0,formal_model_trials=0,
        cost_scope='registered validation workload, host launch or begin through close; includes original replies, native PNG consumption, receipt/exhaustion; not model minimal task latency')
    save(output/'RESULT.json',result);save(output/'A2_ELIGIBILITY.json',gate)
    print(json.dumps(dict(native_tasks=len(native_rows),HE_qualification_tasks=len(he_rows),failures=failures,eligibility=gate,stats=stats)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--blender',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
