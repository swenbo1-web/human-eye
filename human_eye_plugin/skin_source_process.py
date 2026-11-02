"""Fixed finite LBS source reader, reusing FK lifecycle and cleanup."""
import argparse,hashlib,json,os,queue,subprocess,sys,threading,time
from pathlib import Path
from . import skin_source as core
from . import surface_deformation
from .rig_pose_process import RigPoseProcess
from .surface_owned import pinned_file
from .runtime_identity import runtime_identity,check_source_drift
r=core.r


class SkinSourceProcess(RigPoseProcess):
    def __init__(self,profile_path):
        self.received_ns=time.perf_counter_ns();self.deadline_ns=self.received_ns+30_000_000_000
        self.path=Path(profile_path);r.require(self.path.is_absolute() and self.path.resolve()==self.path,'skin_profile_path')
        with self.path.open('rb') as f:self.profile_bytes=f.read(65537)
        r.require(len(self.profile_bytes)<=65536,'skin_profile_budget');p=self.profile=r.decode(self.profile_bytes)
        r.require(type(p) is dict and set(p)=={'schema','blender_executable','blender_sha256','scene_file','scene_sha256','mesh_name','rig_name','expected_frame','runtime_source_sha256'} and p['schema']=='skin-source-operator-profile-v1','skin_profile_fields')
        r.require(all(r.text(p[k]) for k in ('mesh_name','rig_name')) and p['mesh_name']!=p['rig_name']
            and type(p['expected_frame']) is dict and set(p['expected_frame'])=={'number','subframe'} and type(p['expected_frame']['number']) is int
            and r.finite(p['expected_frame']['subframe']) and 0<=p['expected_frame']['subframe']<1,'skin_profile_roles_frame')
        r.require(check_source_drift()['compatible'] and runtime_identity()['source_sha256']==p['runtime_source_sha256'],'skin_runtime_pin')
        pinned_file(p['blender_executable'],p['blender_sha256'],128*1024*1024);pinned_file(p['scene_file'],p['scene_sha256'],64*1024*1024)
        root=Path(__file__).resolve().parents[1];worker=root/'human_eye_plugin/skin_source_worker.py'
        self.module_sha=hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest();self.math_sha=hashlib.sha256(Path(r.__file__).read_bytes()).hexdigest()
        self.worker_sha=hashlib.sha256(worker.read_bytes()).hexdigest();self.queue=queue.Queue(maxsize=16);self.closed=False
        self.sequence=0;self.diagnostics=[];self.source=None;self._gate=threading.Lock();r.check_time(self.deadline_ns)
        self.process=subprocess.Popen([p['blender_executable'],'--factory-startup','--disable-autoexec','--background',p['scene_file'],
            '--python',str(worker),'--','--root',str(root),'--profile',str(self.path),'--profile-sha256',hashlib.sha256(self.profile_bytes).hexdigest(),
            '--module-sha256',self.module_sha,'--math-sha256',self.math_sha,'--deadline-ns',str(self.deadline_ns)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False)
        def read():
            try:
                while True:
                    blob=self.process.stdout.readline(r.MAX_BYTES+1)
                    if not blob:break
                    r.require(len(blob)<=r.MAX_BYTES,'skin_response_budget')
                    if blob.startswith(b'HUMAN_EYE_SKIN:'):self.queue.put_nowait(r.decode(blob[len(b'HUMAN_EYE_SKIN:'):]))
                    elif len(self.diagnostics)<16:self.diagnostics.append(blob[:512].decode('utf8','replace'))
            except Exception:pass
            finally:
                try:self.queue.put_nowait(None)
                except queue.Full:pass
        def stderr():
            while True:
                blob=self.process.stderr.readline(513)
                if not blob:break
                if len(self.diagnostics)<16:self.diagnostics.append(blob.decode('utf8','replace'))
        try:
            # Reader startup also belongs to the already-spawned process cleanup.
            threading.Thread(target=read,daemon=True).start();threading.Thread(target=stderr,daemon=True).start()
            ready=self._next();r.require(ready.get('kind')=='ready' and ready.get('protocol')==core.PROTOCOL and ready.get('process_id')==self.process.pid
                and ready.get('scene_sha256')==p['scene_sha256'] and ready.get('profile_sha256')==hashlib.sha256(self.profile_bytes).hexdigest()
                and ready.get('module_sha256')==self.module_sha and ready.get('math_sha256')==self.math_sha and ready.get('worker_sha256')==self.worker_sha
                and type(ready.get('deadline_ns')) is int and ready['deadline_ns']==self.deadline_ns and ready.get('read_only') is True
                and type(ready.get('geometry_setters')) is int and ready['geometry_setters']==0 and ready.get('saves_file') is False
                and ready.get('generic_exec') is False,'skin_worker_binding');self.capabilities=ready
        except BaseException:self.close();raise

    def _inspect(self):
        r.require(not self.closed,'skin_closed_transport');r.check_time(self.deadline_ns)
        with self.path.open('rb') as f:blob=f.read(65537)
        r.require(blob==self.profile_bytes and check_source_drift()['compatible'] and self.sequence<16,'skin_source_profile_or_lifetime')
        p=self.profile;pinned_file(p['scene_file'],p['scene_sha256'],64*1024*1024);r.check_time(self.deadline_ns)
        self.sequence+=1;self.process.stdin.write(r.encoded(dict(id=self.sequence,command='inspect',deadline_ns=self.deadline_ns))+b'\n');self.process.stdin.flush()
        value=self._next();r.require(value.get('kind')=='snapshot' and type(value.get('id')) is int and value.get('id')==self.sequence,'skin_reply:'+str(value.get('reason')))
        packet=value['snapshot'];proof=core.validate(packet,deadline_ns=self.deadline_ns,expected=self.source);payload=proof['payload']
        r.require(payload['object_name']==p['rig_name'] and payload['frame']==p['expected_frame'] and packet['scene_sha256']==p['scene_sha256']
            and packet['mesh']['identity']['name']==p['mesh_name'],'skin_fixed_roles_or_frame')
        self.source=packet;return packet


def run_reader(args,actor_type,*,analyzer=None,selection_binder=None,region_binder=None,anchor_binder=None,catalog_analyzer=None,
        context_binder=None,context_policy_installer=None,close_before_publish=False):
    """Shared owned source CLI persistence; every analyzer owns source admission."""
    if analyzer is None:analyzer=lambda packet,actor,**kw:surface_deformation.analyze(packet,**kw)
    if selection_binder is None:selection_binder=lambda packet,selection,actor,**kw:surface_deformation.bind_selection(packet,selection,**kw)
    output=args.output;r.require(output.is_absolute() and output.resolve()==output,'skin_output_path');output.mkdir(exist_ok=False);actor=None;published=False
    def save(name,value):
        with (output/name).open('xb') as f:f.write(r.encoded(value));f.flush();os.fsync(f.fileno())
    def verify_inputs():
        verifier=getattr(actor,'verify_inputs',None)
        if verifier is not None:verifier()
    try:
        selection=None;query=None;region_path=getattr(args,'region_query',None);anchor_path=getattr(args,'anchor_query',None)
        context_path=getattr(args,'context_query',None);policy_path=getattr(args,'context_policy',None);policy_digest=getattr(args,'context_policy_sha256',None)
        anchors_only=getattr(args,'anchors_only',False)
        r.require(type(anchors_only) is bool and sum((args.triangle_query is not None,region_path is not None,anchor_path is not None,context_path is not None,anchors_only))<=1,'deformation_query_modes')
        r.require(region_path is None or region_binder is not None,'deformation_region_entry_unavailable')
        r.require(anchor_path is None or anchor_binder is not None,'deformation_anchor_entry_unavailable')
        r.require(not anchors_only or catalog_analyzer is not None,'deformation_anchor_entry_unavailable')
        r.require((context_path is not None and policy_path is not None and policy_digest is not None)
            or (context_path is None and policy_path is None and policy_digest is None),'deformation_context_operator_fields')
        r.require(context_path is None or context_binder is not None and context_policy_installer is not None,'deformation_context_entry_unavailable')
        actor=actor_type(args.operator_profile);save('INPUTS.json',actor.profile);r.check_time(actor.deadline_ns)
        if context_path is not None:
            context_policy_installer(args,actor);save('CONTEXT_POLICY.json',r.decode(actor.context_policy_bytes));r.check_time(actor.deadline_ns)
        selection_path=args.triangle_query if region_path is None else region_path
        if anchor_path is not None:selection_path=anchor_path
        if context_path is not None:selection_path=context_path
        if selection_path is not None:
            path=selection_path;r.require(path.is_absolute() and path.resolve()==path,'deformation_selection_path')
            with path.open('rb') as f:blob=f.read(4097)
            r.require(len(blob)<=4096,'deformation_selection_byte_budget');selection=r.decode(blob)
            save('CONTEXT_SELECTION.json' if context_path is not None else 'ANCHOR_SELECTION.json' if anchor_path is not None else 'SELECTION.json' if region_path is None else 'REGION_SELECTION.json',selection);r.check_time(actor.deadline_ns)
        first=actor.inspect()
        if args.triangle_query is not None:query=selection_binder(first,selection,actor,deadline_ns=actor.deadline_ns)
        if region_path is not None:query=region_binder(first,selection,actor,deadline_ns=actor.deadline_ns)
        if anchor_path is not None:query=anchor_binder(first,selection,actor,deadline_ns=actor.deadline_ns)
        if context_path is not None:query=context_binder(first,selection,actor,deadline_ns=actor.deadline_ns)
        second=actor.inspect()
        save('SNAPSHOTS.json',dict(first=first,second=second,capabilities=actor.capabilities))
        r.check_time(actor.deadline_ns)
        if anchors_only:report=catalog_analyzer(second,actor,deadline_ns=actor.deadline_ns)
        else:report=analyzer(second,actor,deadline_ns=actor.deadline_ns,
            **({} if query is None else {('context_query' if context_path is not None else 'anchor_query' if anchor_path is not None else 'query' if region_path is None else 'region_query'):query}))
        r.check_time(actor.deadline_ns);verify_inputs()
        if context_path is not None:
            r.require(type(getattr(actor,'context_audit_bytes',None)) is bytes,'deformation_context_audit_required')
            save('CONTEXT_AUDIT.json',r.decode(actor.context_audit_bytes));r.check_time(actor.deadline_ns);verify_inputs()
        if close_before_publish:
            actor.close();r.check_time(actor.deadline_ns)
            r.require(actor.process.poll()==0,'source_worker_exit')
            verify_inputs()
        save('REPORT_PENDING.json',report);r.check_time(actor.deadline_ns);verify_inputs()
        os.replace(output/'REPORT_PENDING.json',output/'REPORT.json');published=True;r.check_time(actor.deadline_ns);verify_inputs()
        if context_path is not None:
            from .deformation_context import publication_bytes
            payload=publication_bytes(report)
            r.require(len(payload)<=r.MAX_BYTES,'deformation_context_report_byte_budget')
            save('PUBLICATION.json',dict(payload_bytes=len(payload),payload_sha256=hashlib.sha256(payload).hexdigest(),
                elapsed_ns=time.perf_counter_ns()-actor.received_ns,report_file=str(output/'REPORT.json'),snapshot_file=str(output/'SNAPSHOTS.json')))
            r.check_time(actor.deadline_ns);verify_inputs()
            binary=getattr(sys.stdout,'buffer',None)
            if binary is None:print(payload[:-1].decode('ascii'))
            else:binary.write(payload);binary.flush()
            return 0
        encoded=json.dumps(dict(report,evidence=dict(report_file=str(output/'REPORT.json'),snapshot_file=str(output/'SNAPSHOTS.json')),
            elapsed_ns=time.perf_counter_ns()-actor.received_ns),allow_nan=False)
        if anchor_path is not None or anchors_only:r.require(len(encoded.encode('utf8'))<=r.MAX_BYTES,'deformation_anchor_report_byte_budget')
        elif region_path is not None:r.require(len(encoded.encode('utf8'))<=r.MAX_BYTES,'deformation_region_report_byte_budget')
        r.check_time(actor.deadline_ns);verify_inputs();print(encoded);return 0
    except Exception as exc:
        if published:os.replace(output/'REPORT.json',output/'REVOKED_REPORT.json')
        reason=str(exc)[:400];failure=dict(status=getattr(exc,'status','unsupported' if 'unsupported_' in reason else 'unavailable'),reason=reason,
            execution_authority=False,geometry_setters=0,original_file_saved=False)
        save('FAILURE.json',failure);print(json.dumps(failure));return 1
    finally:
        if actor is not None:actor.close()


def main(argv=None):
    p=argparse.ArgumentParser(description='Read fixed original/evaluated LBS mesh sources; no edit, frame or save command')
    p.add_argument('--operator-profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--triangle-query',type=Path,help='Optional immutable file/role/frame selection of at most four original triangle IDs')
    return run_reader(p.parse_args(argv),SkinSourceProcess)


if __name__=='__main__':raise SystemExit(main())
