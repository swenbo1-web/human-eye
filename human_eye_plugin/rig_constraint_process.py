"""Fixed static-constraint transport, reusing FK single-flight/expiry/cleanup."""
import argparse,hashlib,json,os,queue,subprocess,sys,threading,time
from pathlib import Path
from . import rig_constraint as core
from .rig_pose_process import RigPoseProcess
from .surface_owned import pinned_file
from .runtime_identity import runtime_identity,check_source_drift
r=core.r


class RigConstraintProcess(RigPoseProcess):
    def __init__(self,profile_path):
        self.received_ns=time.perf_counter_ns();self.deadline_ns=self.received_ns+30_000_000_000
        self.path=Path(profile_path);r.require(self.path.is_absolute() and self.path.resolve()==self.path,'constraint_profile_path')
        with self.path.open('rb') as f:self.profile_bytes=f.read(65537)
        r.require(len(self.profile_bytes)<=65536,'constraint_profile_budget');p=self.profile=r.decode(self.profile_bytes)
        r.require(type(p) is dict and set(p)=={'schema','blender_executable','blender_sha256','scene_file','scene_sha256','object_name',
            'target_name','constraint_bone','expected_frame','runtime_source_sha256'} and p['schema']=='rig-constraint-operator-profile-v1','constraint_profile_fields')
        r.require(all(r.text(p[k]) for k in ('object_name','target_name','constraint_bone')) and p['object_name']!=p['target_name']
            and type(p['expected_frame']) is dict and set(p['expected_frame'])=={'number','subframe'} and type(p['expected_frame']['number']) is int
            and r.finite(p['expected_frame']['subframe']) and 0<=p['expected_frame']['subframe']<1,'constraint_profile_roles_frame')
        r.require(check_source_drift()['compatible'] and runtime_identity()['source_sha256']==p['runtime_source_sha256'],'constraint_runtime_pin')
        pinned_file(p['blender_executable'],p['blender_sha256'],128*1024*1024);pinned_file(p['scene_file'],p['scene_sha256'],64*1024*1024)
        root=Path(__file__).resolve().parents[1];worker=root/'human_eye_plugin/rig_constraint_worker.py'
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
                    r.require(len(blob)<=r.MAX_BYTES,'constraint_response_budget')
                    if blob.startswith(b'HUMAN_EYE_CONSTRAINT:'):self.queue.put_nowait(r.decode(blob[21:]))
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
                and ready.get('generic_exec') is False,'constraint_worker_binding');self.capabilities=ready
        except BaseException:self.close();raise

    def _inspect(self):
        r.require(not self.closed,'constraint_closed_transport');r.check_time(self.deadline_ns)
        with self.path.open('rb') as f:blob=f.read(65537)
        r.require(blob==self.profile_bytes and check_source_drift()['compatible'] and self.sequence<16,'constraint_source_profile_or_lifetime')
        p=self.profile;pinned_file(p['scene_file'],p['scene_sha256'],64*1024*1024);r.check_time(self.deadline_ns)
        self.sequence+=1;self.process.stdin.write(r.encoded(dict(id=self.sequence,command='inspect',deadline_ns=self.deadline_ns))+b'\n');self.process.stdin.flush()
        value=self._next();r.require(value.get('kind')=='snapshot' and value.get('id')==self.sequence,'constraint_reply:'+str(value.get('reason')))
        packet=value['snapshot'];payload=core.validate(packet,deadline_ns=self.deadline_ns,expected=self.source)
        r.require(payload['object_name']==p['object_name'] and payload['frame']==p['expected_frame'] and packet['scene_sha256']==p['scene_sha256']
            and packet['target']['name']==p['target_name'] and packet['constraint']['bone']==p['constraint_bone'],'constraint_fixed_roles_or_frame')
        self.source=packet;return packet


def main(argv=None):
    p=argparse.ArgumentParser(description='Read one fixed static Copy Rotation rig; no edit, frame or save command')
    p.add_argument('--operator-profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args(argv)
    output=args.output;r.require(output.is_absolute() and output.resolve()==output,'constraint_output_path');output.mkdir(exist_ok=False);actor=None
    def save(name,value):
        with (output/name).open('xb') as f:f.write(r.encoded(value));f.flush();os.fsync(f.fileno())
    try:
        actor=RigConstraintProcess(args.operator_profile);save('INPUTS.json',actor.profile);first=actor.inspect();second=actor.inspect()
        save('SNAPSHOTS.json',dict(first=first,second=second,capabilities=actor.capabilities))
        report=core.analyze(second,deadline_ns=actor.deadline_ns);save('REPORT.json',report)
        print(json.dumps(dict(report,evidence=dict(report_file=str(output/'REPORT.json'),snapshot_file=str(output/'SNAPSHOTS.json')),
            elapsed_ns=time.perf_counter_ns()-actor.received_ns),allow_nan=False));return 0
    except Exception as exc:
        reason=str(exc)[:400];failure=dict(status='unsupported' if 'unsupported_' in reason else 'unavailable',reason=reason,
            execution_authority=False,geometry_setters=0,original_file_saved=False)
        save('FAILURE.json',failure);print(json.dumps(failure));return 1
    finally:
        if actor is not None:actor.close()


if __name__=='__main__':raise SystemExit(main())
