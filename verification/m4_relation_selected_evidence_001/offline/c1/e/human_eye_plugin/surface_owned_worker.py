"""Dedicated background Blender actor: no exec, rigid transform or save command.

All legal vertex dispatches in this fixed worker pass the restore kernel. This
does not protect against altered source or arbitrary same-account extensions.
"""
import argparse,hashlib,importlib.util,json,os,queue,sys,threading,time,types
from pathlib import Path
sys.dont_write_bytecode=True


def _execute(module,path,blob):
    guard=next((f for f in sys.meta_path if getattr(f,'protocol',None)=='human-eye-verified-source-v1' and f.root==path.parents[1]),None)
    if guard is not None:return guard.exec_path(module,path,expected_blob=blob)
    exec(compile(blob,str(path),'exec',dont_inherit=True),module.__dict__)


def run(args):
    import bpy
    root=args.root.resolve();package=types.ModuleType('human_eye_plugin');package.__path__=[str(root/'human_eye_plugin')]
    sys.modules['human_eye_plugin']=package
    guard=next((f for f in sys.meta_path if getattr(f,'protocol',None)=='human-eye-verified-source-v1' and f.root==root),None)
    if guard is not None:guard.allow_namespace(package)
    manifest=json.loads(args.manifest)
    for name in ('mesh_structure','surface_geometry','surface_reference','surface_restore','surface_owned','blender_host','forward_deadline'):
        path=root/'human_eye_plugin'/(name+'.py');blob=path.read_bytes()
        if len(blob)>512*1024 or hashlib.sha256(blob).hexdigest()!=manifest[name]:raise ValueError('surface_worker_source_pin')
        spec=importlib.util.spec_from_file_location('human_eye_plugin.'+name,path);module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module;_execute(module,path,blob)
    from human_eye_plugin import mesh_structure as raw,surface_geometry as g,surface_owned as s
    from human_eye_plugin.surface_reference import ReferenceRegistry,ReferenceIntent,diagnose
    from human_eye_plugin.surface_restore import RestoreController,RestoreJournal
    from human_eye_plugin.blender_host import BlenderSceneHost
    from human_eye_plugin.forward_deadline import counter_descriptor
    config,config_sha=s.load_config(args.config);s.require(config_sha==args.config_sha256,'config_binding')
    s.require(bpy.app.background and str(Path(bpy.data.filepath).resolve())==config['scene_file'],'owned_background_file')
    s.pinned_file(config['scene_file'],config['scene_sha256'],64*1024*1024)
    reference=s.decode(s.pinned_file(config['reference_file'],config['reference_sha256'],65536))
    host=BlenderSceneHost(execution_metadata=True,identity_metadata=True);commands=queue.Queue(maxsize=16)
    closed=threading.Event();physical=0;active=None;output_lock=threading.Lock()
    def emit(value):
        blob=s.encoded(value);s.require(len(blob)<=s.MAX_MESSAGE,'output_budget')
        with output_lock:sys.stdout.write(s.PREFIX+blob.decode('utf8')+'\n');sys.stdout.flush()
    def reader():
        try:
            while True:
                line=sys.stdin.buffer.readline(s.MAX_MESSAGE+1)
                if not line:break
                value=s.decode(line);s.require(type(value) is dict,'command_object');commands.put_nowait(value)
        except Exception:pass
        finally:closed.set()
    def next_command(deadline=None):
        while True:
            s.require(not closed.is_set(),'parent_closed')
            remaining=.05 if deadline is None else min(.05,(deadline-time.perf_counter_ns())/1e9)
            s.require(remaining>0,'original_deadline')
            try:return commands.get(timeout=remaining)
            except queue.Empty:continue
    def capture():
        objects=list(bpy.context.scene.objects)
        s.require(len(objects)==1 and objects[0].type=='MESH' and host.object_id(objects[0])==config['object_id'],'single_original_mesh')
        obj=objects[0];s.require(len(obj.data.vertices)<=128 and len(obj.data.polygons)<=256
            and all(len(p.vertices)==3 for p in obj.data.polygons),'original_triangle_domain')
        s.require(bpy.context.mode=='OBJECT','object_mode')
        return raw.capture_raw(host,config['object_id'],budget=raw.WorkBudget(deadline_ns=active['deadline_ns']) if active else None)
    current=capture();rr=raw.prepare_raw(reference['raw'],{k:reference['source'][k]
        for k in ('object_id','object_instance','document_epoch','capture_id')})
    s.require(rr['source']['raw_sha256']==reference['source']['raw_sha256'],'reference_source_digest')
    s.require(reference['triangles']==current['raw']['polygons'] and reference['triangle_polygons']==list(range(len(current['raw']['polygons']))),'reference_triangles')
    registry=ReferenceRegistry();ref=registry.bind(rr,current,reference['triangles'],reference['triangle_polygons'],intent=ReferenceIntent(**config['reference_intent']))
    journal=RestoreJournal(config['journal_root'])
    def approve(scope):
        token=s.digest(scope);emit(dict(kind='approval',id=active['id'],scope=scope,scope_sha256=token))
        answer=next_command(scope['deadline_ns'])
        s.require(set(answer)=={'command','id','approved','scope_sha256'} and answer['command']=='approval'
            and answer['id']==active['id'],'approval_message')
        return dict(approved=answer['approved'],scope_sha256=answer['scope_sha256'])
    def setter(index,point):
        nonlocal physical
        s.require(active is not None and index in active['indices'] and physical-active['physical_start']<2*len(active['indices']),'native_dispatch_budget')
        capture();s.require(time.perf_counter_ns()<active['deadline_ns'] and not closed.is_set(),'native_dispatch_deadline')
        obj=bpy.context.scene.objects[0];physical+=1
        obj.data.vertices[index].co=point;obj.data.update()
    controller=RestoreController(registry,journal=journal,capture=capture,set_vertex=setter,approve=approve)
    initial_source=current['source'];fixed=dict(protocol=s.PROTOCOL,config_sha256=config_sha,
        runtime_source_sha256=config['runtime_source_sha256'],process_id=os.getpid(),source_manifest=manifest,
        worker_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        clock=counter_descriptor(),limits=s.LIMITS,all_legal_setters='dedicated_typed_worker_vertex_setter',generic_exec=False,ui_attached=False,
        original_file_saved=False,external_process_proof=False)
    thread=threading.Thread(target=reader,daemon=True);thread.start();emit(dict(kind='ready',**fixed))
    try:
        while not closed.is_set():
            request=next_command();request_id=request.get('id');command=request.get('command');result=None
            try:
                if command=='shutdown' and set(request)=={'command','id'}:emit(dict(kind='result',id=request_id,result={'closed':True}));break
                if command=='inspect' and set(request)=={'command','id'}:
                    snapshot=capture();report=diagnose(registry.resolve(ref,snapshot),snapshot,budget=raw.WorkBudget())
                    result=dict(diagnostic=report,raw_snapshot=snapshot['raw'],source=snapshot['source'],original_source=initial_source,
                        physical_RNA_attempts=physical,journal=RestoreJournal.inspect(config['journal_root']),
                        quarantined=controller.quarantined,execution_authority=False,original_file_saved=False)
                elif command=='goal' and set(request)=={'command','id','event_id','indices','received_ns'}:
                    selected=s.indices(request['indices']);received=request['received_ns']
                    s.require(type(received) is int and 0<=received<=time.perf_counter_ns(),'intake_counter')
                    active=dict(id=request_id,indices=selected,physical_start=physical,deadline_ns=received+s.LIMITS['duration_ns'])
                    error=None
                    try:result=controller.restore(ref,selected,event_id=request['event_id'],received_ns=received,
                        duration_ns=s.LIMITS['duration_ns'],max_displacement_m=s.LIMITS['displacement_m'])
                    except Exception as exc:error=str(exc)[:300]
                    history=RestoreJournal.inspect(config['journal_root'])
                    row=next((r for r in history['rows'] if r['event_id']==request['event_id']),None)
                    result=dict(status=result['status'] if type(result) is dict else 'refused_before_dispatch',
                        kernel_result=result,error=error,journal_event=row,
                        physical_RNA_attempts=physical-active['physical_start'],worker_physical_RNA_attempts=physical,
                        historical_authority=False,original_file_saved=False,save_status='not_saved',
                        execution_authority=False,reusable_grant=False,quarantined=controller.quarantined or history['unknown'])
                else:raise ValueError('owned_surface_unknown_command_or_fields')
                emit(dict(kind='result',id=request_id,result=result))
            except Exception as exc:emit(dict(kind='error',id=request_id,error=str(exc)[:300]))
            finally:active=None
    finally:journal.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--manifest',required=True)
    p.add_argument('--config',type=Path,required=True);p.add_argument('--config-sha256',required=True)
    run(p.parse_args(sys.argv[sys.argv.index('--')+1:]))
