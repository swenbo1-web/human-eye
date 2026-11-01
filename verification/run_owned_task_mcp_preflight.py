"""Real owned stdio integration with a scripted client, never human UI proof."""
import argparse,hashlib,importlib.util,json,os,queue,subprocess,sys,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def worker(args):
    spec=importlib.util.spec_from_file_location('_owned_goal_installed',args.entry)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    proof=module.validate_binding(expected_python=sys.executable);sys.path.insert(0,proof['module_root'])
    identity,_=module.verify_imported_runtime(proof);assert identity['source_sha256']==args.expected_build
    from human_eye_plugin.owned_task_mcp import OwnedTaskMCP
    from human_eye_plugin.blender_process import BlenderProcessHost
    from human_eye_plugin.goal_scheduler import _json
    host=BlenderProcessHost(args.blender,args.scene);folder=args.config.parent;commands=[];real_request=host._request
    def request(command,params,**kwargs):commands.append(command);return real_request(command,params,**kwargs)
    host._request=request
    from human_eye_plugin.live_spatial_mcp import _configure_utf8_stdio
    archive=None
    if args.with_episode_archive:
        from human_eye_plugin.task_episode_archive import EpisodeArchive
        archive_root=folder/'task-evidence';archive_root.mkdir(exist_ok=False);archive=EpisodeArchive(archive_root)
    _configure_utf8_stdio();server=OwnedTaskMCP(args.config,host,sys.stdin,sys.stdout,episode_archive=archive)
    initial=server.entry._scheduler._capture();save(folder/'INITIAL.json',initial)
    original_emit=server.emit;original_apply=host.apply_transform;original_save=server.entry.service._save
    applied=[];faults=[];snapshots=[]
    def apply(*values,**kwargs):
        result=original_apply(*values,**kwargs);applied.append(True)
        if args.scenario in ('cancel_after_first','EOF_after_first') and len(applied)==1:
            (folder/'FIRST_APPLY.txt').write_text('real setter finished, response deliberately held',encoding='utf8')
            active=server.active
            assert active['cancelled'].wait(5),'actual client did not cancel/close'
        if args.scenario=='lost_apply_reply':raise OSError('injected loss after actual owned setter')
        return result
    def saving(value,runtime,**kwargs):
        original_save(value,runtime,**kwargs)
        if args.scenario=='completion_ack_loss' and not faults and any(r['status']=='completed' for r in value.get('goal_authorizations',{}).get('records',{}).values()):
            faults.append(True);raise OSError('injected completed save ACK loss')
    def emit(value):
        if value.get('method')=='elicitation/create' and args.scenario=='config_changed':
            args.config.write_bytes(args.config.read_bytes()+b' ')
        if value.get('id')==100 and 'result' in value:
            final=server.entry._scheduler._capture();save(folder/('FINAL_'+str(len(snapshots))+'.json'),final)
            objects={o['name']:o for o in final['native_scene']['objects']};old={o['name']:o for o in initial['native_scene']['objects']}
            assert objects['GreyBase']==old['GreyBase']
            assert {k:v for k,v in objects['BluePart'].items() if k not in ('world_vertices','matrix')}=={
                k:v for k,v in old['BluePart'].items() if k not in ('world_vertices','matrix')}
            assert all(objects['BluePart']['matrix'][r][c]==old['BluePart']['matrix'][r][c] for r in range(4) for c in range(4) if (r,c)!=(2,3))
            gap=min(v[2] for v in objects['BluePart']['world_vertices'])-max(v[2] for v in objects['GreyBase']['world_vertices'])
            goals=server.entry._live;reports={key:host.motion_goal_status(live['grant'].goal_id) for key,live in goals.items() if 'motion_begin' in commands}
            snapshot=dict(gap_m=gap,actual_setters=sum(r['physical_meter']['actual_setter_count'] for r in reports.values()),reports=reports,
                original_reference_and_local_geometry_unchanged=True,only_Z_changed=True,applied_calls=len(applied),commands=list(commands))
            snapshots.append(snapshot);save(folder/('PHYSICAL_'+str(len(snapshots)-1)+'.json'),snapshot)
        original_emit(value)
    try:
        with patch.object(host,'apply_transform',side_effect=apply),patch.object(server.entry.service,'_save',side_effect=saving),patch.object(server,'emit',side_effect=emit):server.run()
    finally:
        host.close()
        if archive is not None:save(folder/'RECOVERY.json',archive.recover())
        from human_eye_plugin.task_episode import archive_episode
        archive=folder/'episodes';archive.mkdir(exist_ok=False)
        archived=[archive_episode(value,archive) for value in server.episodes.values()]
        save(folder/'EPISODE_ARCHIVE.json',dict(records=archived,consumer='scripted_worker_not_Codex_UI',
            delivery_proven=False,execution_authority=False))
        save(folder/'PROCESS.json',dict(exit_code=host._process.poll(),pid=host._process.pid,commands=commands,applied_calls=len(applied)))
        assert host._process.poll()==0


class Client:
    def __init__(self,command,folder):
        self.err=(folder/'SERVER.stderr').open('xb')
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,
            text=True,encoding='utf8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.messages=queue.Queue();self.wire=[]
        def read():
            for line in self.process.stdout:
                try:self.messages.put(json.loads(line))
                except Exception:self.messages.put(dict(parse_error=line))
            self.messages.put(None)
        threading.Thread(target=read,daemon=True).start()
    def send(self,value):
        self.wire.append(dict(direction='client_to_server',value=value));self.process.stdin.write(json.dumps(value)+'\n');self.process.stdin.flush()
    def receive(self,timeout=20):
        value=self.messages.get(timeout=timeout);self.wire.append(dict(direction='server_to_client',value=value));return value
    def rpc(self,rid,method,params=None):self.send(dict(jsonrpc='2.0',id=rid,method=method,params=params or {}))
    def finish(self,folder):
        if self.process.stdin and not self.process.stdin.closed:self.process.stdin.close()
        try:self.process.wait(15)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait();raise
        self.err.close();save(folder/'WIRE.json',self.wire);assert self.process.returncode==0


def parent(args):
    sys.path.insert(0,str(ROOT))
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    scenarios=['accept','decline','cancel_form','numeric_approval','wrong_response_id','legacy_no_elicitation','model_approval_injection',
        'approval_expiry','config_changed','cancel_after_first','EOF_after_first','lost_apply_reply','completion_ack_loss']
    identity=json.loads((args.entry.parent/'RUNTIME_BINDING.json').read_text())['identity']
    site=args.entry.parent.parent/'site-packages';pin={k:identity[k] for k in ('base_version','implementation_revision','source_sha256','build_id')}
    pin.update(source_kind='installed_distribution',protocol_version='2025-03-26',mode='live')
    creator=ROOT/'verification/fixtures/create_task_entry_scene.py'
    save(output/'REGISTERED_INPUT.json',dict(source_sha256=args.expected_build,scenarios=scenarios,rounds=args.rounds,
        creator_sha256=hashlib.sha256(creator.read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        client='scripted_protocol_client_not_human_UI',formal_model_calls=0,shared_GUI=False))
    rows=[]
    for repeat in range(args.rounds):
        for scenario in scenarios:
            folder=Path(tempfile.mkdtemp(prefix='he-entry-',dir=output));blend=folder/'fixture.blend'
            create=subprocess.run([str(args.blender),'--factory-startup','--disable-autoexec','--background','--python',str(creator),'--',str(blend)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.DEVNULL,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            (folder/'CREATE.stdout').write_bytes(create.stdout);(folder/'CREATE.stderr').write_bytes(create.stderr)
            assert create.returncode==0 and blend.exists();blend_sha=hashlib.sha256(blend.read_bytes()).hexdigest()
            config=folder/'CONFIG.json';save(config,dict(schema_version='1.0',enabled=True,project_root=str(site),expected_identity=pin,
                state_file='STATE.json',audit_file='AUDIT.jsonl',quad_size=64,max_sessions=4))
            command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'--worker','--entry',str(args.entry),'--expected-build',args.expected_build,
                '--blender',str(args.blender),'--scene',str(blend),'--config',str(config),'--scenario',scenario]
            if args.with_episode_archive:command.append('--with-episode-archive')
            client=Client(command,folder);response=None
            try:
                protocol='2025-03-26' if scenario=='legacy_no_elicitation' else '2025-11-25'
                client.rpc(1,'initialize',dict(protocolVersion=protocol,capabilities={'elicitation':{'form':{}}},clientInfo={'name':'explicit-scripted-preflight','version':'1'}))
                init=client.receive();assert init['id']==1
                client.rpc(2,'tools/list');tools=client.receive();names={x['name'] for x in tools['result']['tools']}
                assert names=={'human_eye_scene_observe','human_eye_connection_status','human_eye_owned_clearance_goal'}
                client.rpc(3,'tools/call',dict(name='human_eye_scene_observe',arguments={'include_image':False}));observed=client.receive()
                metadata=json.loads(observed['result']['content'][0]['text'])
                context=json.loads(metadata['routing']['context_text'])
                assert context['source']=='human_eye_geometry_observation'
                focal,reference=context['focal_id'],context['reference_id']
                assert focal.startswith('blender:') and reference.startswith('blender:') and focal!=reference
                proposal=dict(focal_id=focal,reference_id=reference,target_clearance_m=.001)
                if scenario=='approval_expiry':proposal['limits']={'max_duration_s':1.5}
                if scenario=='model_approval_injection':proposal['approved']=True
                client.rpc(100,'tools/call',dict(name='human_eye_owned_clearance_goal',arguments=proposal))
                first=client.receive();elicited=first.get('method')=='elicitation/create'
                if elicited:
                    assert scenario not in ('legacy_no_elicitation','model_approval_injection')
                    if scenario=='approval_expiry':time.sleep(1.6)
                    result={'action':'decline'} if scenario=='decline' else {'action':'cancel'} if scenario=='cancel_form' else {'action':'accept','content':{'approve':True}}
                    if scenario=='numeric_approval':result['content']['approve']=1
                    client.send(dict(jsonrpc='2.0',id='foreign-response' if scenario=='wrong_response_id' else first['id'],result=result))
                    if scenario in ('cancel_after_first','EOF_after_first'):
                        until=time.perf_counter()+10
                        while not (folder/'FIRST_APPLY.txt').exists():
                            assert time.perf_counter()<until,'real apply marker missing';time.sleep(.02)
                        if scenario=='EOF_after_first':client.process.stdin.close()
                        else:client.send(dict(jsonrpc='2.0',method='notifications/cancelled',params={'requestId':100}))
                    response=client.receive()
                else:response=first
                assert response['id']==100,response;save(folder/'RESULT_WIRE.json',response)
                public=json.loads(response['result']['content'][0]['text'])
                if scenario=='accept':
                    assert public['status']=='completed' and public['task_succeeded'] and public['new_setter_count']==4,public
                    client.rpc(100,'tools/call',dict(name='human_eye_owned_clearance_goal',arguments=proposal));again=client.receive()
                    assert 'duplicate' in again['error']['message'];save(folder/'REPLAY.json',again)
                elif scenario in ('cancel_after_first','EOF_after_first'):
                    assert public['status']=='review_required' and public['new_setter_count']==1,public
                elif scenario=='lost_apply_reply':assert public['new_setter_count'] is None and public['status']=='review_required',public
                elif scenario=='completion_ack_loss':assert public['physical_task_succeeded'] is True and public['completion_persistence']=='unknown',public
                else:assert public.get('executed',False) is False and public['new_setter_count']==0,public
                from human_eye_plugin.task_episode import validate_episode
                ref=public['task_episode_ref'];assert len(json.dumps(ref).encode())<=650
                consumed=False
                if scenario not in ('EOF_after_first','approval_expiry'):
                    client.rpc(201,'resources/read',{'uri':ref['uri']});resource=client.receive()
                    episode=validate_episode(json.loads(resource['result']['contents'][0]['text']))
                    assert episode['sha256']==ref['sha256']
                    save(folder/'EPISODE_WIRE.json',resource);consumed=True
                    assert episode['derived']['new_setter_count']==public['new_setter_count']
                    assert episode['derived']['success_candidate']==(scenario=='accept')
                    assert episode['derived']['training_positive'] is False
                rows.append(dict(round=repeat,scenario=scenario,status=public['status'],new_setter_count=public['new_setter_count'],elicited=elicited,
                    episode_sha256=ref['sha256'],episode_outcome=ref['outcome'],episode_client_read=consumed))
                print(json.dumps(rows[-1]),flush=True)
            except Exception as exc:save(folder/'FAILURE.json',dict(error=repr(exc),response=response));raise
            finally:
                client.finish(folder);assert hashlib.sha256(blend.read_bytes()).hexdigest()==blend_sha
            physical=json.loads((folder/'PHYSICAL_0.json').read_text());process=json.loads((folder/'PROCESS.json').read_text())
            count=4 if scenario in ('accept','completion_ack_loss') else 1 if scenario in ('cancel_after_first','EOF_after_first','lost_apply_reply') else 0
            assert physical['actual_setters']==count and process['applied_calls']==count,physical
            from human_eye_plugin.task_episode import read_episode
            archived=json.loads((folder/'EPISODE_ARCHIVE.json').read_text())['records'];assert len(archived)==1
            episode=read_episode(archived[0]['path']);assert episode['sha256']==rows[-1]['episode_sha256']
            assert episode['derived']['success_candidate']==(scenario=='accept')
            assert episode['derived']['training_positive'] is False
            assert episode['derived']['new_setter_count']==(None if scenario=='lost_apply_reply' else count)
            if args.with_episode_archive:
                recovered=json.loads((folder/'RECOVERY.json').read_text())
                assert recovered['terminal_records']==1 and recovered['unknown_records']==0,recovered
                row=recovered['rows'][0]
                assert row['recorded_new_setter_count']==(None if scenario=='lost_apply_reply' else count)
                assert row['source_verified']==(scenario not in ('legacy_no_elicitation','model_approval_injection'))
                assert recovered['execution_authority'] is False and recovered['training_positives']==0
            if scenario in ('accept','completion_ack_loss'):assert abs(physical['gap_m']-.001)<=1e-6
    save(output/'RESULT.json',dict(passed=True,rows=rows,source_sha256=args.expected_build,owned_workers=len(rows),
        actual_Codex_UI_approval=False,scripted_client_only=True,formal_activation=False,model_calls=0,
        with_episode_archive=args.with_episode_archive))
    print(json.dumps(dict(passed=True,scenarios=len(rows),actual_Codex_UI_approval=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--expected-build',required=True);p.add_argument('--blender',type=Path,required=True)
    p.add_argument('--output',type=Path);p.add_argument('--rounds',type=int,choices=(1,2),default=2);p.add_argument('--worker',action='store_true')
    p.add_argument('--with-episode-archive',action='store_true')
    p.add_argument('--scene',type=Path);p.add_argument('--config',type=Path);p.add_argument('--scenario');args=p.parse_args();worker(args) if args.worker else parent(args)
