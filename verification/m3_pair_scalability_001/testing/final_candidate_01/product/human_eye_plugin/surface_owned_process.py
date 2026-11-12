"""One fixed Blender process for local restore goals; no generic command API."""
from .verified_source_loader import worker_arguments
import hashlib,os,queue,subprocess,threading,time,uuid
from collections import deque
from pathlib import Path
from . import surface_owned as s
from .runtime_identity import runtime_identity,check_source_drift


class OwnedSurfaceProcess:
    def __init__(self,config_path):
        self.config,self.config_sha=s.load_config(config_path)
        s.require(check_source_drift()['compatible'],'source_drift');identity=runtime_identity();s.require(identity['source_sha256']==self.config['runtime_source_sha256'],'runtime_identity')
        self.root=Path(__file__).resolve().parents[1];self.closed=False;self.poisoned=False;self.physical=0
        self._gate=threading.Lock();self._output=queue.Queue(maxsize=16);self.diagnostics=deque(maxlen=32)
        modules=(*s.MODULES,'blender_host','forward_deadline','surface_owned_worker')
        self.manifest={name:hashlib.sha256((self.root/'human_eye_plugin'/(name+'.py')).read_bytes()).hexdigest() for name in modules}
        s.pinned_file(self.config['blender_executable'],self.config['blender_sha256'],128*1024*1024)
        s.pinned_file(self.config['scene_file'],self.config['scene_sha256'],64*1024*1024)
        s.pinned_file(self.config['reference_file'],self.config['reference_sha256'],65536)
        worker=Path(__file__).with_name('surface_owned_worker.py')
        command=[self.config['blender_executable'],'--factory-startup','--disable-autoexec','--background',self.config['scene_file'],
            *worker_arguments(self.root,worker),'--','--root',str(self.root),'--manifest',s.encoded(self.manifest).decode(),
            '--config',str(config_path),'--config-sha256',self.config_sha]
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False)
        try:
            # Reader startup also belongs to the already-spawned process cleanup.
            threading.Thread(target=self._reader,daemon=True).start();threading.Thread(target=self._stderr,daemon=True).start()
            ready=self._next(time.perf_counter_ns()+60_000_000_000)
            from .forward_deadline import counter_descriptor
            s.require(ready.get('kind')=='ready' and ready.get('protocol')==s.PROTOCOL and ready.get('config_sha256')==self.config_sha
                and ready.get('worker_source_sha256')==self.manifest['surface_owned_worker']
                and ready.get('source_manifest')==self.manifest and ready.get('runtime_source_sha256')==identity['source_sha256']
                and ready.get('process_id')==self.process.pid and ready.get('clock')==counter_descriptor()
                and ready.get('limits')==s.LIMITS and ready.get('generic_exec') is False and ready.get('ui_attached') is False
                and ready.get('original_file_saved') is False and ready.get('external_process_proof') is False,'ready_binding')
            self.capabilities=ready
        except BaseException as exc:
            self.close();raise ValueError(str(exc)+';'+''.join(list(self.diagnostics)[-4:])) from exc

    def _reader(self):
        try:
            while True:
                blob=self.process.stdout.readline(s.MAX_MESSAGE+1)
                if not blob:break
                s.require(len(blob)<=s.MAX_MESSAGE,'stdout_line_budget')
                if blob.startswith(s.PREFIX.encode()):self._output.put_nowait(s.decode(blob[len(s.PREFIX):]))
                else:self.diagnostics.append(blob[:512].decode('utf8','replace'))
        except Exception:self.poisoned=True
        finally:
            try:self._output.put_nowait(None)
            except queue.Full:self.poisoned=True

    def _stderr(self):
        while True:
            blob=self.process.stderr.readline(4097)
            if not blob:break
            self.diagnostics.append(blob[:512].decode('utf8','replace'))

    def _send(self,value):
        s.require(not self.closed and not self.poisoned,'process_unavailable');blob=s.encoded(value)+b'\n'
        s.require(len(blob)<=s.MAX_MESSAGE,'stdin_budget');self.process.stdin.write(blob);self.process.stdin.flush()

    def _next(self,deadline,cancelled=None):
        while True:
            s.require(not self.closed and not self.poisoned,'process_unavailable')
            s.require(cancelled is None or not cancelled(),'cancelled_result_unknown')
            remaining=min(.05,(deadline-time.perf_counter_ns())/1e9);s.require(remaining>0,'original_deadline_unknown')
            try:
                value=self._output.get(timeout=remaining);s.require(type(value) is dict,'process_closed_unknown')
                s.require(time.perf_counter_ns()<deadline and (cancelled is None or not cancelled()),'late_or_cancelled_result_unknown')
                return value
            except queue.Empty:continue

    def _call(self,command,*,deadline,approve=None,cancelled=None):
        s.require(self._gate.acquire(blocking=False),'single_flight');called=False;approval_seen=False
        try:
            s.require(cancelled is None or not cancelled(),'cancelled_before_dispatch')
            request_id=uuid.uuid4().hex;command=dict(command,id=request_id);self._send(command);called=True
            while True:
                # The worker cannot write before an affirmative approval. If
                # cancelled during preparation, deny when its scope arrives.
                # Once approved, cancellation cannot erase an in-flight write:
                # drain its actual receipt within the same original deadline.
                response=self._next(deadline);s.require(response.get('id')==request_id,'reply_id')
                kind=response.get('kind')
                if kind=='approval':
                    s.require(approve is not None and not approval_seen and set(response)=={'kind','id','scope','scope_sha256'},'unexpected_approval')
                    scope=response['scope'];s.require(s.digest(scope)==response['scope_sha256'] and scope['deadline_ns']==deadline
                        and scope['event_id']==command['event_id'] and scope['received_ns']==command['received_ns']
                        and scope['indices']==command['indices'] and scope['maximum_setter_attempts']==2*len(command['indices'])
                        and scope['max_displacement_m']==s.LIMITS['displacement_m'] and len(scope['vertex_changes'])==len(command['indices']),'scope_binding')
                    approval_seen=True
                    answer=False
                    if cancelled is None or not cancelled():
                        try:answer=approve(scope)
                        except Exception:
                            if cancelled is None or not cancelled():raise
                    s.require(time.perf_counter_ns()<deadline,'approval_expired')
                    s.require(type(answer) is bool,'strict_approval')
                    message=dict(command='approval',id=request_id,approved=answer,scope_sha256=response['scope_sha256'])
                    if answer:
                        # The MCP cancellation token shares its input-state
                        # lock with this handoff. Whichever takes that lock
                        # first wins: cancellation, or the approval pipe write.
                        submit=getattr(cancelled,'submit_if_live',None)
                        if submit is not None:
                            sent=submit(lambda:self._send(message))
                        elif cancelled is None or not cancelled():
                            # Trusted local callers without a shared token use
                            # this final check as their logical commit boundary.
                            self._send(message);sent=True
                        else:sent=False
                        s.require(type(sent) is bool,'strict_submission_result')
                        if not sent:
                            message['approved']=False;self._send(message)
                    else:self._send(message)
                elif kind=='result':
                    s.require(set(response)=={'kind','id','result'},'result_fields');return response['result']
                elif kind=='error':raise ValueError(response.get('error','worker_error'))
                else:raise ValueError('owned_surface_unknown_reply')
        except BaseException:
            if called:self.poisoned=True;self.close()
            raise
        finally:self._gate.release()

    def inspect(self):return self._call(dict(command='inspect'),deadline=time.perf_counter_ns()+30_000_000_000)

    def goal(self,selected,*,event_id,received_ns,approve,cancelled=None):
        selected=s.indices(selected);deadline=received_ns+s.LIMITS['duration_ns']
        s.require(type(received_ns) is int and 0<=received_ns<=time.perf_counter_ns()<deadline,'intake_window')
        result=self._call(dict(command='goal',indices=selected,event_id=event_id,received_ns=received_ns),
            deadline=deadline,approve=approve,cancelled=cancelled)
        try:
            s.require(type(result) is dict and type(result.get('physical_RNA_attempts')) is int
                and 0<=result['physical_RNA_attempts']<=2*len(selected)
                and result.get('worker_physical_RNA_attempts')==self.physical+result['physical_RNA_attempts']
                and result.get('execution_authority') is False and result.get('reusable_grant') is False
                and result.get('original_file_saved') is False,'physical_counter')
        except BaseException:self.poisoned=True;self.close();raise
        self.physical=result['worker_physical_RNA_attempts'];return result

    def close(self):
        if self.closed:return
        self.closed=True
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
            try:stream.close()
            except (OSError,ValueError):pass
