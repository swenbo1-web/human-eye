"""Fixed owned read-only rig transport and compact explicit Codex entry."""
import argparse,hashlib,json,os,queue,subprocess,sys,threading,time
from pathlib import Path
from . import rig_pose as r
from .surface_owned import pinned_file
from .runtime_identity import runtime_identity,check_source_drift


class RigPoseProcess:
    def __init__(self,profile_path):
        self.received_ns=time.perf_counter_ns();self.deadline_ns=self.received_ns+30_000_000_000
        self.path=Path(profile_path);r.require(self.path.is_absolute() and self.path.resolve()==self.path,'profile_path')
        with self.path.open('rb') as f:self.profile_bytes=f.read(65537)
        r.require(len(self.profile_bytes)<=65536,'profile_budget');self.profile=r.decode(self.profile_bytes);p=self.profile
        r.require(type(p) is dict and set(p)=={'schema','blender_executable','blender_sha256','scene_file','scene_sha256','object_name',
            'expected_frame','runtime_source_sha256','policy_file','policy_sha256'} and p['schema']=='rig-pose-operator-profile-v1','profile_fields')
        r.require(r.text(p['object_name']) and type(p['expected_frame']) is dict and set(p['expected_frame'])=={'number','subframe'}
            and type(p['expected_frame']['number']) is int and r.finite(p['expected_frame']['subframe']) and 0<=p['expected_frame']['subframe']<1,'profile_target_frame')
        r.require(check_source_drift()['compatible'] and runtime_identity()['source_sha256']==p['runtime_source_sha256'],'runtime_pin')
        pinned_file(p['blender_executable'],p['blender_sha256'],128*1024*1024);pinned_file(p['scene_file'],p['scene_sha256'],64*1024*1024)
        if p['policy_file'] is None:r.require(p['policy_sha256'] is None,'policy_pin');self.policy=None
        else:self.policy=r.decode(pinned_file(p['policy_file'],p['policy_sha256'],65536))
        root=Path(__file__).resolve().parents[1];module=root/'human_eye_plugin/rig_pose.py';worker=module.with_name('rig_pose_worker.py')
        self.module_sha=hashlib.sha256(module.read_bytes()).hexdigest();self.worker_sha=hashlib.sha256(worker.read_bytes()).hexdigest()
        self.queue=queue.Queue(maxsize=16);self.closed=False;self.sequence=0;self.diagnostics=[];self.source=None;self._gate=threading.Lock()
        self.process=subprocess.Popen([p['blender_executable'],'--factory-startup','--disable-autoexec','--background',p['scene_file'],
            '--python',str(worker),'--','--root',str(root),'--profile',str(self.path),'--profile-sha256',hashlib.sha256(self.profile_bytes).hexdigest(),
            '--module-sha256',self.module_sha],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False)
        def read():
            try:
                while True:
                    blob=self.process.stdout.readline(r.MAX_BYTES+1)
                    if not blob:break
                    r.require(len(blob)<=r.MAX_BYTES,'response_budget')
                    if blob.startswith(b'HUMAN_EYE_RIG:'):self.queue.put_nowait(r.decode(blob[len(b'HUMAN_EYE_RIG:'):]))
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
            ready=self._next();r.require(ready.get('kind')=='ready' and ready.get('protocol')==r.PROTOCOL
                and ready.get('process_id')==self.process.pid and ready.get('scene_sha256')==p['scene_sha256']
                and ready.get('profile_sha256')==hashlib.sha256(self.profile_bytes).hexdigest()
                and ready.get('module_sha256')==self.module_sha and ready.get('worker_sha256')==self.worker_sha
                and ready.get('read_only') is True and type(ready.get('geometry_setters')) is int and ready['geometry_setters']==0 and ready.get('saves_file') is False
                and ready.get('generic_exec') is False,'worker_binding');self.capabilities=ready
        except BaseException:
            self.close();raise

    def _next(self):
        while True:
            r.check_time(self.deadline_ns)
            try:
                value=self.queue.get(timeout=min(.05,(self.deadline_ns-time.perf_counter_ns())/1e9))
                r.require(type(value) is dict,'worker_closed');return value
            except queue.Empty:continue

    def inspect(self):
        r.require(self._gate.acquire(blocking=False),'single_flight')
        try:return self._inspect()
        finally:self._gate.release()

    def _inspect(self):
        r.require(not self.closed,'closed_transport');r.check_time(self.deadline_ns)
        with self.path.open('rb') as f:blob=f.read(65537)
        r.require(blob==self.profile_bytes and check_source_drift()['compatible'] and self.sequence<16,'source_profile_or_lifetime_budget')
        if self.profile['policy_file'] is not None:pinned_file(self.profile['policy_file'],self.profile['policy_sha256'],65536)
        self.sequence+=1;self.process.stdin.write(r.encoded(dict(id=self.sequence,command='inspect',deadline_ns=self.deadline_ns))+b'\n');self.process.stdin.flush()
        value=self._next();r.require(value.get('kind')=='snapshot' and value.get('id')==self.sequence,'snapshot_reply:'+str(value.get('reason')))
        snapshot=value['snapshot'];p=r.validate(snapshot,deadline_ns=self.deadline_ns,expected_source=self.source)
        r.require(p['object_name']==self.profile['object_name'] and p['frame']==self.profile['expected_frame'],'target_or_frame_binding')
        self.source=snapshot['identity'];return snapshot

    def close(self):
        if self.closed:return
        self.closed=True
        if self.process.poll() is None:
            try:self.process.stdin.close();self.process.wait(timeout=3)
            except (OSError,ValueError,subprocess.TimeoutExpired):
                self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
            try:stream.close()
            except (OSError,ValueError):pass


def main(argv=None):
    p=argparse.ArgumentParser(description='Read a fixed owned rig at its current saved frame; never edit or save')
    p.add_argument('--operator-profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args(argv)
    actor=None;output=args.output;r.require(output.is_absolute() and output.resolve()==output,'output_path');output.mkdir(exist_ok=False)
    def save(name,value):
        with (output/name).open('xb') as f:f.write(r.encoded(value));f.flush();os.fsync(f.fileno())
    try:
        actor=RigPoseProcess(args.operator_profile);save('INPUTS.json',dict(profile=actor.profile,policy=actor.policy))
        first=actor.inspect();second=actor.inspect()
        r.require(first['source_sha256']==second['source_sha256'] and first['audit']==second['audit'],'snapshot_changed_between_reads')
        save('SNAPSHOTS.json',dict(first=first,second=second,capabilities=actor.capabilities))
        report=r.analyze(second,actor.policy,deadline_ns=actor.deadline_ns);save('REPORT.json',report)
        result=dict(report,evidence=dict(report_file=str(output/'REPORT.json'),snapshot_file=str(output/'SNAPSHOTS.json'),
            source_sha256=second['source_sha256']),elapsed_ns=time.perf_counter_ns()-actor.received_ns)
        print(json.dumps(result,ensure_ascii=True,allow_nan=False));return 0
    except Exception as exc:
        failure=dict(status='unavailable',reason=str(exc)[:400],execution_authority=False,geometry_setters=0,original_file_saved=False)
        save('FAILURE.json',failure);print(json.dumps(failure));return 1
    finally:
        if actor is not None:actor.close()


if __name__=='__main__':raise SystemExit(main())
