"""Complete native_shared task baseline; new HE trials stay disabled."""
import argparse,base64,copy,hashlib,json,math,queue,statistics,subprocess,sys,threading,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT))
from verification.engineering_task_contract import bootstrap,choose_region,he_regions,digest


def save(path,value):
    with Path(path).open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def run(blender,output,entry,rounds=3,tasks=3,only=None):
    identity,_=bootstrap(entry)
    from human_eye_plugin.structure_task_control import begin,close
    from verification.engineering_baseline_cases import cases,validate_facts
    from verification.run_native_engineering_preflight import pixel_check
    from PIL import Image
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    selected=[case for case in cases() if only is None or case['id']==only]
    helpers={str(ROOT/'verification'/name):hashlib.sha256((ROOT/'verification'/name).read_bytes()).hexdigest() for name in
        ('engineering_task_contract.py','engineering_native_service.py','engineering_stdio.py','engineering_owned_server.py',
         'native_engineering_baseline.py','run_native_engineering_preflight.py','measure_engineering_transport.py','engineering_baseline_cases.py')}
    save(output/'REGISTERED_INPUT.json',dict(assets=[{k:c[k] for k in ('id','objects','task','asset_task_sha256')} for c in selected],
        helpers=helpers,engine_build=identity['source_sha256'],arm='native_shared',rounds=rounds,tasks=tasks))
    save(output/'PRIVATE_ORACLES.json',selected)
    rows=[];processes=[]
    for case in selected:
        for repeat in range(rounds):
            folder=output/(case['id']+'_'+str(repeat));folder.mkdir()
            asset={k:case[k] for k in ('id','objects','task','asset_task_sha256')};save(folder/'ASSET.json',asset)
            save(folder/'SERVER_SPEC.json',dict(site=str(Path(entry).parents[1]/'site-packages'),helpers=helpers))
            out=(folder/'BLENDER.stdout').open('xb');err=(folder/'BLENDER.stderr').open('xb')
            task_start=time.perf_counter_ns();host=None;mcp=None;stream=None;responses=[]
            try:
                host=subprocess.Popen([str(blender),'--factory-startup','--background','--disable-autoexec','--python-exit-code','3',
                    '--python',str(ROOT/'verification/engineering_owned_server.py'),'--',str(folder)],stdout=out,stderr=err,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                end=time.monotonic()+30
                while not (folder/'READY.json').is_file():
                    if host.poll() is not None or time.monotonic()>=end:raise RuntimeError('owned_host_not_ready')
                    time.sleep(.01)
                ready=json.loads((folder/'READY.json').read_text());config=folder/'CONFIG.json'
                host_startup_ms=(time.perf_counter_ns()-task_start)/1e6
                pin={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind','protocol_version','mode')}
                save(config,dict(schema_version='1.0',enabled=True,project_root=str(Path(entry).parents[1]/'site-packages'),
                    state_file='STATE.json',audit_file='AUDIT.jsonl',structure_task_file='TASK.json',structure_task_control_file='CONTROL.json',
                    quad_size=64,max_sessions=4,expected_identity=pin,structure_patch_mode='nonplanar_dense_v1',
                    blender=dict(host='127.0.0.1',port=ready['port'],timeout_s=30)))
                spec=folder/'SPEC.json';save(spec,dict(arm='native',entry=str(entry),config=str(config),helpers=helpers,
                    host='127.0.0.1',port=ready['port'],peer_nonce=ready['peer_nonce'],source_sha256=ready['source_sha256']))
                stream=(folder/'MCP.stderr').open('xb')
                mcp=subprocess.Popen([sys.executable,'-I','-B',str(ROOT/'verification/engineering_stdio.py'),str(spec)],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stream,text=True,encoding='utf8',cwd=folder,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                replies=queue.Queue()
                def reader():
                    for line in mcp.stdout:replies.put(line)
                    replies.put(None)
                threading.Thread(target=reader,daemon=True).start();counter=0
                def rpc(method,params=None):
                    nonlocal counter
                    counter+=1;request=dict(jsonrpc='2.0',id=counter,method=method)
                    if params is not None:request['params']=params
                    started=time.perf_counter_ns();mcp.stdin.write(json.dumps(request)+'\n');mcp.stdin.flush();line=replies.get(timeout=35)
                    if line is None:raise RuntimeError('MCP_exit_before_response')
                    response=json.loads(line);responses.append(dict(request=request,response=response,ms=(time.perf_counter_ns()-started)/1e6))
                    if 'error' in response:raise RuntimeError(str(response))
                    return response['result']
                initialized=rpc('initialize');mcp_initialize_ms=responses[-1]['ms'];assert initialized['_meta']['human_eye']['source_sha256']==identity['source_sha256']
                tools=rpc('tools/list');assert len(tools['tools'])==4
                for task_id in range(tasks):
                    if task_id:task_start=time.perf_counter_ns()
                    mark=time.perf_counter_ns();handoff=begin(config,'registration-'+str(task_id),ready['object_id'],categories=case['task']['categories'])
                    registration_ms=(time.perf_counter_ns()-mark)/1e6;response_start=len(responses);client_check_ms=0.
                    def observe(request_id,ref=None,images=False):
                        query=dict(mode='mesh_structure',operation='patch' if ref else 'diagnose',request_id=request_id,task_ref=handoff['task_ref'])
                        if ref:query['patch_ref']=ref
                        reply=rpc('tools/call',dict(name='human_eye_scene_observe',arguments=dict(query=query,include_image=images)))
                        value=json.loads(reply['content'][0]['text'])
                        if reply.get('isError'):raise RuntimeError(str(value))
                        return value,reply
                    diagnostic,_=observe('diagnose');validate_facts(case,diagnostic['native'])
                    selection=choose_region(diagnostic['regions'],case['task']['anchor_world_bu'],**diagnostic['region_coverage'])
                    image_status=None;pixels=None;blocks=[];image_meta=[];image_value=None
                    if selection['status']=='selected':
                        ref=selection['region']['ref'];image_value,reply=observe('patch',ref,True)
                        validate_facts(case,image_value['native']);image_status=image_value['image_status']
                        blocks=[block for block in reply['content'] if block['type']=='image'];image_meta=image_value['native']['image_metadata']
                        client=folder/('task_'+str(task_id));client.mkdir()
                        frames=[]
                        check_start=time.perf_counter_ns()
                        for index,(block,meta) in enumerate(zip(blocks,image_meta)):
                            raw=base64.b64decode(block['data'],validate=True);path=client/('image_'+str(index)+'.png');path.write_bytes(raw)
                            private=folder/('native_'+image_value['native']['capture_request_id'])/('overview.png' if index==0 else 'detail.png')
                            with Image.open(private) as a,Image.open(path) as b:assert a.convert('RGBA').tobytes()==b.convert('RGBA').tobytes()
                            frame=dict(meta,path=str(path),source_png_sha256=meta['sha256'],sha256=hashlib.sha256(raw).hexdigest());frames.append(frame)
                        assert len(blocks)==len(image_meta)
                        pixels=pixel_check(case,dict(images=frames))
                        client_check_ms=(time.perf_counter_ns()-check_start)/1e6
                        if case['id'] in ('nonplanar_clear','center_blocked','dense1808'):
                            assert pixels['readable_pairs']>=8 and pixels['false_visible']==0
                        if case['id']=='feature_blocked':assert not blocks
                        receipt,_=observe('patch',ref,True);assert receipt['status']=='receipt' and not receipt['current_evidence']
                        exhausted,exhausted_reply=observe('exhausted',ref,True)
                        assert exhausted['image_status']=='budget_exhausted' and not any(b['type']=='image' for b in exhausted_reply['content'])
                    else:
                        assert selection['status']=='empty';receipt,_=observe('diagnose');assert receipt['status']=='receipt'
                    mark=time.perf_counter_ns();closed=close(config,handoff['task_ref']);close_ms=(time.perf_counter_ns()-mark)/1e6
                    elapsed=(time.perf_counter_ns()-task_start)/1e6
                    assert closed['task_budget']['spent']['queries']==(3 if selection['status']=='selected' else 1)
                    rows.append(dict(case=case['id'],round=repeat,task=task_id,first=task_id==0,complete_task_ms=elapsed,
                        selection=selection['status'],images=len(blocks),pixels=pixels,image_status=image_status,
                        received_png_bytes=sum(len(base64.b64decode(b['data'])) for b in blocks),task_budget=closed['task_budget']))
                    rows[-1]['timing']=dict(host_startup_ms=host_startup_ms if task_id==0 else 0,
                        mcp_initialize_ms=mcp_initialize_ms if task_id==0 else 0,registration_ms=registration_ms,close_ms=close_ms,
                        tool_rpc_ms=sum(r['ms'] for r in responses[response_start:]),client_image_check_ms=client_check_ms)
                # Closed references cannot reobserve; outside the measured task.
                denied=rpc('tools/call',dict(name='human_eye_scene_observe',arguments=dict(include_image=False,
                    query=dict(mode='mesh_structure',operation='diagnose',request_id='afterclose',task_ref=handoff['task_ref']))))
                assert denied['isError'];save(folder/'RESPONSES.json',responses)
                mcp.stdin.close();assert mcp.wait(timeout=10)==0
            except Exception as exc:
                save(folder/'FAILURE.json',dict(case=case['id'],round=repeat,error=type(exc).__name__+': '+str(exc),
                    completed_tasks=len(rows),registered_denominator=len(selected)*rounds*tasks,trial_passed=False))
                raise
            finally:
                if mcp is not None and mcp.poll() is None:mcp.kill();mcp.wait(timeout=5)
                if stream:stream.close()
                (folder/'STOP').write_text('owned test complete')
                if host is not None:
                    try:host.wait(timeout=10)
                    except subprocess.TimeoutExpired:host.kill();host.wait(timeout=5)
                out.close();err.close()
                process=dict(case=case['id'],round=repeat,host_pid=None if host is None else host.pid,host_exit=None if host is None else host.returncode,
                    mcp_pid=None if mcp is None else mcp.pid,mcp_exit=None if mcp is None else mcp.returncode)
                processes.append(process);save(folder/'PROCESS.json',process)
            server=json.loads((folder/'SERVER_RESULT.json').read_text());assert server['source_unchanged'] and server['display_restored']
    full=len(selected)==8 and rounds==tasks==3
    stats=[]
    for case in selected:
        for first in (True,False):
            values=sorted(r['complete_task_ms'] for r in rows if r['case']==case['id'] and r['first']==first)
            if values:stats.append(dict(case=case['id'],first=first,n=len(values),median_ms=statistics.median(values),p95_ms=values[math.ceil(.95*len(values))-1]))
    result=dict(stage='M2-A1 native_shared full-task baseline',full_matrix=full,native_tasks=len(rows),rows=rows,stats=stats,
        processes=processes,HE_trials=0,model_trials=0,full_HE_guarantee_parity=False,
        cost_scope='host launch or warm begin through trusted close, including stdio/TCP, independent pixel checks, receipts and image budget verification; shutdown and afterclose check separate')
    save(output/'RESULT.json',result)
    if full:
        save(output/'REGISTERED_HE_GATES.json',dict(new_HE_trials_permitted=False,reason='global_ROI_public_coverage_gap_requires_fix',
            engine_build=identity['source_sha256'],native_input_sha256=digest(json.loads((output/'REGISTERED_INPUT.json').read_text())),
            common_quality='all original source members, valid actual camera/PNG/pixels, no false visibility; omissions/unknown in denominator',
            maximum_complete_first_ms=3390,maximum_complete_warm_ms=2000,strict_speed_gain='HE p95 below matched native p95 at equal quality',
            baseline_stats=stats,original_release_gates_unchanged=True))
    print(json.dumps(dict(tasks=len(rows),full=full,stats=stats,HE_trials=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--blender',required=True,type=Path);parser.add_argument('--entry',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--rounds',type=int,default=3)
    parser.add_argument('--tasks',type=int,default=3);parser.add_argument('--only');args=parser.parse_args()
    run(args.blender,args.output,args.entry,args.rounds,args.tasks,args.only)
