"""Owned factory reference-restore product QA; scripted client, not human UI.

Builder runs in a new Blender factory process. Controller runs with dependency
Python and verifies a fixed installed target bootstrap before importing it.
"""
import argparse,copy,hashlib,importlib.util,json,os,queue,subprocess,sys,threading,time,types
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]


def save(path,value):
    with path.open('x',encoding='utf8') as f:json.dump(value,f,indent=2,allow_nan=False)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def builder(args):
    import bpy,bmesh
    assert bpy.app.background and args.output.resolve().is_relative_to(ROOT/'verification/fixes/20261102_m3_surface_entry')
    args.output.mkdir(exist_ok=False);sys.path.insert(0,str(ROOT))
    package=types.ModuleType('human_eye_plugin');package.__path__=[str(args.core_root/'human_eye_plugin')];sys.modules['human_eye_plugin']=package
    from human_eye_plugin import mesh_structure as m
    source=args.core_root/'human_eye_plugin/blender_host.py';spec=importlib.util.spec_from_file_location('_surface_owned_builder_host',source)
    hostmodule=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hostmodule;exec(compile(source.read_bytes(),str(source),'exec'),hostmodule.__dict__)
    from verification.m3_asset_cases import build
    rows=[]
    for name in ('flat','curved','rotated','millimetre_units','two_vertices','satisfied','too_far','original_quad','extra_object'):
        bpy.ops.wm.read_factory_settings(use_empty=True);obj=build(bpy,dict(kind='sheet',n=5,unit_scale=.001 if name=='millimetre_units' else 1.))[0]
        if name!='original_quad':
            bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free()
        if name=='curved':
            for v in obj.data.vertices:v.co.z=.3*(v.co.x*v.co.x+v.co.y*v.co.y)
        if name=='rotated':obj.rotation_euler=[.4,-.7,.9]
        obj.data.update();bpy.context.view_layer.update();host=hostmodule.BlenderSceneHost(execution_metadata=True,identity_metadata=True)
        oid=host.object_id(obj);reference=m.capture_raw(host,oid);obj.data.calc_loop_triangles()
        triangles=[[int(i) for i in t.vertices] for t in obj.data.loop_triangles];mapping=[int(t.polygon_index) for t in obj.data.loop_triangles]
        chosen=[6,12] if name=='two_vertices' else [12]
        if name!='satisfied':
            for i in chosen:obj.data.vertices[i].co.z-=.002 if name=='too_far' else .0005
        obj.data.update()
        if name=='extra_object':
            extra=bpy.data.objects.new('OwnedExtra',obj.data.copy());bpy.context.scene.collection.objects.link(extra)
        folder=args.output/name;folder.mkdir(exist_ok=False)
        save(folder/'REFERENCE.json',dict(raw=reference['raw'],source=reference['source'],triangles=triangles,triangle_polygons=mapping))
        current=m.capture_raw(host,oid);path=folder/'fixture.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=True)
        row=dict(name=name,scene=str(path),scene_sha256=sha(path),object_id=oid,indices=chosen,current_raw=current['raw'],reference_raw=reference['raw'],
            reference_file=str(folder/'REFERENCE.json'),reference_sha256=sha(folder/'REFERENCE.json'))
        save(folder/'CASE.json',row);rows.append(row)
    save(args.output/'CASES.json',dict(rows=rows,owned_factory_only=True))


class Client:
    def __init__(self,entry,config,root):
        self.root=root;self.root.mkdir(exist_ok=False);self.messages=queue.Queue();self.protocol=[]
        self.err=(root/'STDERR.txt').open('wb')
        self.process=subprocess.Popen([sys.executable,'-I','-B',str(entry),'--operator-config',str(config)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def reader():
            try:
                while True:
                    line=self.process.stdout.readline(256*1024+1)
                    if not line:break
                    assert len(line)<=256*1024
                    value=json.loads(line);self.protocol.append(dict(direction='received',counter_ns=time.perf_counter_ns(),value=value));self.messages.put(value)
            finally:self.messages.put(None)
        threading.Thread(target=reader,daemon=True).start()
    def send(self,value):
        self.protocol.append(dict(direction='sent',counter_ns=time.perf_counter_ns(),value=value));self.process.stdin.write((json.dumps(value)+'\n').encode());self.process.stdin.flush()
    def receive(self):
        value=self.messages.get(timeout=70);assert value is not None,('server closed',self.root);return value
    def rpc(self,key,method,params=None):
        self.send(dict(jsonrpc='2.0',id=key,method=method,params={} if params is None else params));return self.receive()
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
        self.err.close();save(self.root/'PROTOCOL.json',self.protocol)
        requests=[r for r in self.protocol if r['direction']=='sent' and 'method' in r['value'] and 'id' in r['value']]
        metrics=[]
        for request in requests:
            replies=[r for r in self.protocol if r['direction']=='received' and 'method' not in r['value']
                and type(r['value'].get('id')) is type(request['value']['id']) and r['value'].get('id')==request['value']['id']
                and r['counter_ns']>=request['counter_ns']]
            reply=replies[0] if replies else None
            metrics.append(dict(id=request['value']['id'],method=request['value']['method'],
                roundtrip_ns=reply['counter_ns']-request['counter_ns'] if reply else None,
                request_json_utf8_bytes=len(json.dumps(request['value'],separators=(',',':'),ensure_ascii=False).encode()),
                response_json_utf8_bytes=len(json.dumps(reply['value'],separators=(',',':'),ensure_ascii=False).encode()) if reply else None))
        save(self.root/'CLIENT_IO_METRICS.json',dict(rows=metrics,
            measurement='client serialize-send through reader parse and queue, includes explicit scripted form roundtrip for goal',
            initialization='includes new MCP and Blender startup before initialize reply',model_tokens=None,model_cost=None,
            comparative_performance_gate=False))


def metadata(reply):return json.loads(reply['result']['content'][0]['text'])


def controller(args):
    root=args.output/('run-'+args.run_id);root.mkdir(exist_ok=False)
    spec=importlib.util.spec_from_file_location('_surface_owned_target',args.entry);entry=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=entry;spec.loader.exec_module(entry);proof=entry.validate_binding(expected_python=sys.executable)
    sys.path.insert(0,proof['module_root']);identity,_=entry.verify_imported_runtime(proof)
    from human_eye_plugin.surface_owned_process import OwnedSurfaceProcess
    from human_eye_plugin.surface_restore import RestoreJournal
    from human_eye_plugin.surface_owned_mcp import GOAL,INSPECT
    # Install a separate pinned entry inside this experiment, beside a copy of
    # its target binding and admin. This never edits Codex config or activation.
    installed=root/'admin';installed.mkdir(exist_ok=False)
    for name in ('target_runtime_entry.py','RUNTIME_BINDING.json','installed_release.py'):
        (installed/name).write_bytes((args.entry.parent/name).read_bytes())
    # Binding pins the original launch path; the template points there directly.
    source=(ROOT/'examples/agents/surface_owned_entry.py').read_text()
    source=source.replace("EXPECTED_TARGET_ENTRY_SHA256=''",'EXPECTED_TARGET_ENTRY_SHA256='+repr(sha(args.entry)))
    source=source.replace("Path(__file__).resolve().with_name('target_runtime_entry.py')",'Path('+repr(str(args.entry))+')')
    launcher=installed/'surface_owned_entry.py';launcher.write_text(source,encoding='utf8')
    cases=json.loads((args.output/'CASES.json').read_text())['rows'];binary_sha=sha(args.blender);rows=[]
    matrix=[(name,'accept') for name in ('flat','curved','rotated','millimetre_units','two_vertices','satisfied','too_far')]
    matrix +=[('flat',p) for p in ('decline','numeric','wrong_id','no_form','model_approval','cancel','disconnect')]
    matrix += [('original_quad','startup_refuse'),('extra_object','startup_refuse'),('flat','expired_intake')]
    for ordinal,(name,policy) in enumerate(matrix):
        case=next(x for x in cases if x['name']==name);folder=root/('%02d_%s_%s'%(ordinal,name,policy));folder.mkdir(exist_ok=False)
        journal=folder/'journal';journal.mkdir();config=folder/'CONFIG.json'
        values=dict(schema='owned-surface-operator-config-v1',blender_executable=str(args.blender),blender_sha256=binary_sha,
            scene_file=case['scene'],scene_sha256=case['scene_sha256'],reference_file=case['reference_file'],reference_sha256=case['reference_sha256'],
            object_id=case['object_id'],journal_root=str(journal),runtime_source_sha256=identity['source_sha256'],
            reference_intent=dict(provenance='owned_factory_same_index_reference_before_explicit_dent',semantic_target='restore selected vertices to the authored intended surface',
                correspondence='same_index_from_owned_copy'))
        save(config,values);before_scene=sha(Path(case['scene']));result=None;inspection=None;form=None;error=None;client=None;actor=None
        try:
            if policy in ('startup_refuse','expired_intake'):
                try:actor=OwnedSurfaceProcess(config)
                except Exception as exc:error=str(exc)
                if policy=='startup_refuse':assert actor is None and error
                else:
                    try:actor.goal(case['indices'],event_id='expired',received_ns=time.perf_counter_ns()-31_000_000_000,
                        approve=lambda _:(_ for _ in ()).throw(AssertionError('must not ask')))
                    except ValueError as exc:error=str(exc)
                    else:raise AssertionError('expired accepted')
                    inspection=actor.inspect();assert inspection['physical_RNA_attempts']==0 and inspection['raw_snapshot']==case['current_raw']
            else:
                client=Client(launcher,config,folder/'client')
                init=client.rpc(1,'initialize',dict(protocolVersion='2025-06-18',capabilities={} if policy=='no_form' else {'elicitation':{}}))
                assert init['result']['_meta']['actual_Codex_UI_proven'] is False
                client.rpc(2,'tools/list');before=metadata(client.rpc(3,'tools/call',dict(name=INSPECT,arguments={})))
                assert before['raw_snapshot']==case['current_raw'] and before['physical_RNA_attempts']==0
                arguments=dict(indices=case['indices'])
                if policy=='model_approval':arguments['approved']=True
                client.send(dict(jsonrpc='2.0',id='goal',method='tools/call',params=dict(name=GOAL,arguments=arguments)))
                reply=client.receive()
                if reply.get('method')=='elicitation/create':
                    form=reply;message=json.loads(form['params']['message'].split('\n',1)[1]);scope=message['scope']
                    assert len(scope['vertex_changes'])==len(case['indices']) and scope['maximum_setter_attempts']==2*len(case['indices'])
                    assert scope['deadline_ns']-scope['received_ns']==30_000_000_000
                    for change in scope['vertex_changes']:
                        assert change['before_local']==case['current_raw']['vertices'][change['vertex']]
                        assert change['target_local']==case['reference_raw']['vertices'][change['vertex']]
                    if policy=='disconnect':client.close();client=None
                    elif policy=='cancel':
                        client.send(dict(jsonrpc='2.0',method='notifications/cancelled',params=dict(requestId='goal')));result=metadata(client.receive())
                    else:
                        answer=dict(jsonrpc='2.0',id='wrong' if policy=='wrong_id' else reply['id'],
                            result=dict(action='decline' if policy=='decline' else 'accept',content=dict(approve=1 if policy=='numeric' else True)))
                        client.send(answer);result=metadata(client.receive())
                else:result=metadata(reply)
                if client is not None and policy!='cancel':
                    duplicate=metadata(client.rpc('goal','tools/call',dict(name=GOAL,arguments=arguments)))
                    assert duplicate['status']=='receipt' and duplicate['retried'] is False
                    inspection=metadata(client.rpc('inspect_after','tools/call',dict(name=INSPECT,arguments={})))
                    expected=case['reference_raw'] if policy=='accept' and name!='too_far' else case['current_raw']
                    assert inspection['raw_snapshot']==expected,(name,policy,result,inspection)
                    count=0 if policy!='accept' or name in ('satisfied','too_far') else len(case['indices'])
                    assert inspection['physical_RNA_attempts']==count,(name,policy,result)
                    if count:
                        assert result['kernel_result']['status']=='completed' and result['physical_RNA_attempts']==count
                        assert result['kernel_result']['protected_vertices_unchanged'] is True
                    else:assert result.get('physical_RNA_attempts',result.get('physical_count'))==0
                    assert form is None if policy in ('no_form','model_approval') or name=='too_far' else form is not None
                if policy in ('disconnect','cancel'):
                    if client is not None:client.close();client=None
                    history=RestoreJournal.inspect(journal);assert history['unknown']
                    assert len(history['rows'])==1 and history['rows'][0]['setter_count'] is None
                    # Restart on the same fixed journal remains read-only and
                    # refuses a new goal before another form or native write.
                    actor=OwnedSurfaceProcess(config);inspection=actor.inspect()
                    assert inspection['physical_RNA_attempts']==0 and inspection['raw_snapshot']==case['current_raw']
                    retry=actor.goal(case['indices'],event_id='must_refuse_after_unknown',received_ns=time.perf_counter_ns(),
                        approve=lambda _:(_ for _ in ()).throw(AssertionError('must not ask')))
                    assert retry['quarantined'] and retry['physical_RNA_attempts']==0
        finally:
            if client is not None:client.close()
            if actor is not None:actor.close()
        assert sha(Path(case['scene']))==before_scene==case['scene_sha256']
        row=dict(case=name,policy=policy,result=result,inspection=inspection,form_present=form is not None,error=error,
            scene_unchanged=True,journal=RestoreJournal.inspect(journal),scripted_client=True,human_UI_proof=False)
        save(folder/'RESULT.json',row);rows.append(row);print(json.dumps(dict(case=name,policy=policy,passed=True)),flush=True)
    save(root/'RESULT.json',dict(runtime_source=identity['source_sha256'],rows=rows,formal_model_calls=0,shared_GUI_accessed=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True);group.add_argument('--builder',action='store_true');group.add_argument('--controller',action='store_true')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--core-root',type=Path);p.add_argument('--entry',type=Path)
    p.add_argument('--blender',type=Path);p.add_argument('--run-id',default='r1');argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    args=p.parse_args(argv);builder(args) if args.builder else controller(args)
