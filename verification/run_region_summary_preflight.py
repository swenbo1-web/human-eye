"""Functional installed v3 acceptance; no HE/native cost or model comparison."""
import argparse,base64,hashlib,importlib.util,io,json,queue,subprocess,sys,threading,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def bind(entry,expected):
    spec=importlib.util.spec_from_file_location('_region_fixed_entry',entry)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    proof=module.validate_binding(expected_python=sys.executable);sys.path.insert(0,proof['module_root'])
    identity,_=module.verify_imported_runtime(proof)
    if identity['source_sha256']!=expected or identity['implementation_revision']!='v21-region-summary-candidate-20261101':
        raise ValueError('explicit_candidate_binding')
    return identity


def pixels(case,reply,folder):
    """Actual host camera and original PNG, never the planned view alone."""
    from PIL import Image
    from verification.run_native_engineering_preflight import pixel_check
    from human_eye_plugin.blender_mcp_host import RPC_PREFIX
    raw=None
    for path in sorted(folder.glob('WIRE_*.json'),key=lambda p:int(p.stem.split('_')[1])):
        wire=json.loads(path.read_text())
        if wire.get('status')!='success':continue
        text=wire['result']['result'];value=json.loads(text[len(RPC_PREFIX):]).get('result')
        if type(value) is dict and 'frames' in value:raw=value
    if raw is None:raise ValueError('missing_actual_frames')
    images=[b for b in reply['content'] if b['type']=='image'];frames=[]
    if len(images)!=len(raw['frames']):raise ValueError('native_frame_count')
    for i,(block,source) in enumerate(zip(images,raw['frames'])):
        png=base64.b64decode(block['data'],validate=True);original=base64.b64decode(source['picture']['image_base64'],validate=True)
        with Image.open(io.BytesIO(png)) as a,Image.open(io.BytesIO(original)) as b:
            if a.size!=(384,384) or a.convert('RGBA').tobytes()!=b.convert('RGBA').tobytes():raise ValueError('native_pixels_changed')
        path=folder/('PUBLIC_'+str(i)+'.png');path.write_bytes(png)
        f=source['frustum'];matrix=f['camera_matrix_host_units'];span=f['ortho_scale_bu']
        frames.append(dict(path=str(path),sha256=hashlib.sha256(png).hexdigest(),camera_matrix=matrix,actual_ortho_scale=span,
            right=[matrix[k][0] for k in range(3)],up=[matrix[k][1] for k in range(3)],direction=[matrix[k][2] for k in range(3)],
            span=span,location=[matrix[k][3] for k in range(3)]))
    return pixel_check(case,dict(images=frames))


def run(args):
    identity=bind(args.entry,args.expected_build);sys.path.append(str(ROOT))
    from verification.engineering_baseline_cases import cases
    from verification.engineering_task_contract import choose_region,he_regions
    from human_eye_plugin.structure_task_control import begin,close
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    helpers={str(ROOT/'verification'/n):hashlib.sha256((ROOT/'verification'/n).read_bytes()).hexdigest() for n in
        ('engineering_owned_server.py','native_engineering_baseline.py','engineering_task_contract.py','run_region_summary_preflight.py')}
    selected=cases();rows=[];processes=[]
    save(output/'REGISTERED_INPUT.json',dict(candidate=identity['source_sha256'],helpers=helpers,rounds=args.rounds,
        cases=[{k:c[k] for k in ('id','objects','task','asset_task_sha256')} for c in selected],
        mode='functional_only',formal_model_trials=0,new_paired_cost_trials=0,selection='public_anchor_only'))
    for case in selected:
        for repeat in range(args.rounds):
            folder=output/(case['id']+'_'+str(repeat));folder.mkdir()
            save(folder/'ASSET.json',{k:case[k] for k in ('id','objects','task','asset_task_sha256')})
            save(folder/'SERVER_SPEC.json',dict(site=str(args.entry.parents[1]/'site-packages'),helpers=helpers))
            out=(folder/'BLENDER.stdout').open('xb');err=(folder/'BLENDER.stderr').open('xb');stream=None;host=None;mcp=None
            responses=[];row=None
            try:
                host=subprocess.Popen([str(args.blender),'--factory-startup','--background','--disable-autoexec','--python-exit-code','3',
                    '--python',str(ROOT/'verification/engineering_owned_server.py'),'--',str(folder)],stdout=out,stderr=err,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                end=time.monotonic()+30
                while not (folder/'READY.json').exists():
                    if host.poll() is not None or time.monotonic()>=end:raise ValueError('owned_host_not_ready')
                    time.sleep(.01)
                ready=json.loads((folder/'READY.json').read_text());config=folder/'CONFIG.json'
                if ready['port']==9876:raise ValueError('shared_port')
                pin={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id','source_kind','protocol_version','mode')}
                save(config,dict(schema_version='1.0',enabled=True,project_root=str(args.entry.parents[1]/'site-packages'),
                    expected_identity=pin,state_file='STATE.json',audit_file='AUDIT.jsonl',structure_task_file='TASK.json',
                    structure_task_control_file='CONTROL.json',structure_region_mode='summary_v1',structure_patch_mode='nonplanar_dense_v1',
                    quad_size=64,max_sessions=4,blender=dict(host='127.0.0.1',port=ready['port'],timeout_s=30)))
                handoff=begin(config,'functional',ready['object_id'],categories=case['task']['categories'])
                stream=(folder/'MCP.stderr').open('xb')
                mcp=subprocess.Popen([sys.executable,'-I','-B',str(args.entry),'serve','--config',str(config)],stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,stderr=stream,text=True,encoding='utf8',cwd=folder,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                replies=queue.Queue()
                def reader():
                    try:
                        for line in mcp.stdout:replies.put(json.loads(line))
                    finally:replies.put(None)
                threading.Thread(target=reader,daemon=True).start()
                def rpc(method,params=None):
                    request=dict(jsonrpc='2.0',id=len(responses)+1,method=method)
                    if params is not None:request['params']=params
                    mcp.stdin.write(json.dumps(request)+'\n');mcp.stdin.flush();reply=replies.get(timeout=35)
                    responses.append(dict(request=request,reply=reply))
                    if reply is None or 'error' in reply:raise ValueError('rpc_failure')
                    return reply['result']
                def observe(request,ref=None,image=False):
                    query=dict(mode='mesh_structure',operation='patch' if ref else 'diagnose',request_id=request,task_ref=handoff['task_ref'])
                    if ref:query['patch_ref']=ref
                    reply=rpc('tools/call',dict(name='human_eye_scene_observe',arguments=dict(query=query,include_image=image)))
                    return json.loads(reply['content'][0]['text']),reply
                initialized=rpc('initialize');assert initialized['_meta']['human_eye']['source_sha256']==args.expected_build
                assert len(rpc('tools/list')['tools'])==4
                value,reply=observe('diagnose');assert not reply['isError'];assert value['diagnostic']['protocol']=='raw-mesh-structure-v3'
                regions,coverage=he_regions(value)
                selection=choose_region(regions,case['task']['anchor_world_bu'],**coverage)
                row=dict(case=case['id'],round=repeat,selection=selection,status=value['status'],images=0,pixels=None,
                    coverage=value['diagnostic']['region_summary']['coverage'],member_omissions={k:v['omitted'] for k,v in value['diagnostic']['report']['checks'].items()})
                if selection['status']=='selected':
                    region=selection['region'];assert not region['selection_only'] and region['patch_ref']
                    visual,image_reply=observe('image',region['patch_ref'],True);assert not image_reply['isError']
                    row['images']=sum(b['type']=='image' for b in image_reply['content']);row['image_status']=visual['image_status']
                    if row['images']:row['pixels']=pixels(case,image_reply,folder)
                    receipt,_=observe('image',region['patch_ref'],True);assert receipt['status']=='receipt' and not receipt['current_evidence']
                    exhausted,_=observe('exhausted',region['patch_ref'],True);assert exhausted['image_status']=='budget_exhausted'
                elif selection['status']!='empty':raise ValueError('public_selection_unknown')
                if case['id']=='dense1808':
                    assert row['coverage']['boundary_edges']['positions_complete'] and not row['coverage']['boundary_edges']['member_lists_complete']
                    regions,coverage=he_regions(value);remote=next(r for r in regions if r['selection_only'])
                    anchor=[sum(x)/2 for x in zip(*remote['bounds'])];chosen=choose_region(regions,anchor,**coverage)
                    assert chosen['region']['patch_ref'] is None
                    archives=len(list(folder.glob('WIRE_*.json')))
                    denied,rejected=observe('summary-cannot-render',remote['ref'][:32],True)
                    assert rejected['isError'] and denied.get('reason')=='structure_task_patch_ref_not_current'
                    assert not any(b['type']=='image' for b in rejected['content'])
                    assert len(list(folder.glob('WIRE_*.json')))==archives
                    row['summary_ref_render_refused']=True
                closed=close(config,handoff['task_ref']);row['budget']=closed['task_budget']
                denied=rpc('tools/call',dict(name='human_eye_scene_observe',arguments=dict(include_image=False,
                    query=dict(mode='mesh_structure',operation='diagnose',request_id='afterclose',task_ref=handoff['task_ref']))))
                assert denied['isError'];mcp.stdin.close();assert mcp.wait(timeout=10)==0
            except Exception as exc:
                save(folder/'FAILURE.json',dict(error=repr(exc),passed=False));raise
            finally:
                save(folder/'RESPONSES.json',responses)
                if mcp is not None and mcp.poll() is None:mcp.kill();mcp.wait(timeout=5)
                if stream:stream.close()
                (folder/'STOP').write_text('owned test complete')
                if host is not None:
                    try:host.wait(timeout=10)
                    except subprocess.TimeoutExpired:host.kill();host.wait(timeout=5)
                out.close();err.close()
                process=dict(case=case['id'],round=repeat,host_exit=None if host is None else host.returncode,mcp_exit=None if mcp is None else mcp.returncode)
                processes.append(process);save(folder/'PROCESS.json',process)
            state=json.loads((folder/'SERVER_RESULT.json').read_text());assert state['source_unchanged'] and state['display_restored']
            assert process['host_exit']==process['mcp_exit']==0
            if case['id'] in ('nonplanar_clear','dense1808'):assert row['pixels']['readable_pairs']==12 and row['pixels']['false_visible']==0
            if row['pixels'] and row['pixels']['status']=='scored':assert row['pixels']['false_visible']==0
            rows.append(row);save(folder/'CHECKED.json',row)
    result=dict(stage='M2-A1b functional installed public protocol',rows=rows,processes=processes,passed=True,
        formal_release_activated=False,formal_model_trials=0,new_paired_cost_trials=0,full_member_quality_passed=False)
    save(output/'RESULT.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--expected-build',required=True)
    p.add_argument('--blender',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rounds',type=int,default=3)
    a=p.parse_args();value=run(a);print(json.dumps(dict(passed=value['passed'],tasks=len(value['rows']))))
