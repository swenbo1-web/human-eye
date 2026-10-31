"""Lazy private fixed-entry MCP adapter, never a model-provider client.

Each instance owns one private state/audit/session and subprocess.  Production
configuration and the running desktop MCP are never used.  Returned results
are private raw MCP wire data; TrialRouter applies the model-facing boundary.
"""
from pathlib import Path
import copy
import hashlib
import json
import math
import os
import queue
import subprocess
import threading
import time
import uuid

ROOT = Path('D:/hefe')
RELEASE = ROOT / '.human-eye/releases/9.7.2+20261030.segment.brief.r1'
PYTHON = ROOT / '.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
ENTRY = RELEASE / 'admin/target_runtime_entry.py'
BUILD = 'sha256:71c5bb2ecab267d6d055b20ee3105493296e58d1d82fa109df90f789dded5225'
ENTRY_SHA = 'ff50ea2a4a29b5c36f410142fe1d60e244e2a62563b9aa922b8f79c3c00a6a1e'
ALLOWED = frozenset(('human_eye_scene_observe','human_eye_transform','human_eye_clearance_segment'))

def save(path, value):
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)

class UnconfirmedRequestError(RuntimeError):
    uncertain = True

class PrivatePluginClient:
    def __init__(self, folder, fixture, clock=time.monotonic):
        self.folder = Path(folder)
        self.fixture = fixture
        self.clock = clock
        self.process = None
        self.closed = False
        self.failed = False
        self.rows = []
        self.session_id = 'trial-' + uuid.uuid4().hex
        self.segment_wall_s = 0.0
        self.stderr = None
        self.identity = None
        self.tools = None
        self.queue = queue.Queue()
        self._deadline = None
        self._deadline_unregister = None
        self._reader_thread = None
        self._send_thread = None
        self._rpc_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self.cleanup_failures = []

    @property
    def deadline_budget(self):
        return self._deadline

    @property
    def bound_deadline(self):
        return self._deadline

    @property
    def deadline_enforced(self):
        return (self._deadline is not None and self._deadline.watchdog_active
                and not self.closed and not self.failed)

    def bind_deadline(self, budget):
        """Bind once without starting a process or issuing a host request."""
        from .deadline import EpisodeDeadline
        if type(budget) is not EpisodeDeadline:
            raise TypeError('A shared EpisodeDeadline is required')
        if self._deadline is budget:
            return self
        if self._deadline is not None or self.closed or self.failed:
            raise RuntimeError('Plugin deadline cannot be replaced or revived')
        budget.check()
        self.fixture.bind_deadline(budget)
        if self.fixture.bound_deadline is not budget:
            raise RuntimeError('Plugin and native fixture must share one deadline')
        self._deadline = budget
        self.clock = budget.clock
        self._deadline_unregister = budget.add_expiry_callback(self._expire)
        budget.check()
        return self

    def _expire(self):
        # Timer callbacks must never wait for a pipe lock, flush, or process.
        self.failed = True
        self._kill_owned()

    def _kill_owned(self):
        process = self.process
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except (OSError, ProcessLookupError):
                pass

    def _check(self):
        if self._deadline is not None:
            self._deadline.check()
        if self.closed or self.failed:
            raise RuntimeError('Private plugin adapter is closed or uncertain; no restart/retry')

    def _remaining(self, local_deadline):
        remaining = local_deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError('Private MCP request time exhausted')
        if self._deadline is not None:
            return self._deadline.remaining(remaining)
        return remaining

    def _start_reader(self):
        process = self.process
        def reader():
            try:
                for line in process.stdout:
                    self.queue.put(line)
            except (OSError, ValueError):
                pass
            finally:
                self.queue.put(None)
        self._reader_thread = threading.Thread(target=reader,
            name='he-plugin-read-' + str(process.pid), daemon=True)
        self._reader_thread.start()

    def _join_io(self, until):
        for thread in (self._send_thread, self._reader_thread):
            if thread is not None and thread is not threading.current_thread():
                thread.join(max(0., until-time.monotonic()))
                if thread.is_alive():
                    message = 'owned I/O worker did not stop: ' + thread.name
                    if message not in self.cleanup_failures:
                        self.cleanup_failures.append(message)

    def _abort(self, reason):
        self.failed = True
        if self._deadline is not None:
            # Also revoke the native channel: a pending host mutation may have
            # outlived this private MCP process even when its reply is lost.
            self._deadline.expire(reason)
        self._kill_owned()
        until = time.monotonic() + 2.
        if self.process is not None:
            try:
                self.process.wait(timeout=max(.001, until-time.monotonic()))
            except subprocess.TimeoutExpired:
                self.cleanup_failures.append('owned MCP process did not exit after kill')
        self._join_io(until)

    @property
    def uncertain_outcome(self):
        return self.failed

    def start(self):
        self._check()
        # The fixture owns startup and synchronizes the same immutable deadline
        # into its per-setter gate. Do this even if MCP was prepared earlier.
        self.fixture.start()
        self._check()
        if self.process is not None:
            return self
        if hashlib.sha256(ENTRY.read_bytes()).hexdigest() != ENTRY_SHA:
            raise RuntimeError('Frozen fixed entry changed')
        if self.fixture.port == 9876:
            raise RuntimeError('Trial must not contact production/readonly port9876')
        self.folder.mkdir(parents=True,exist_ok=False)
        config = {'schema_version':'1.0','enabled':True,'observe_on_prompt':False,
            'project_root':str(RELEASE/'site-packages'),'state_file':str(self.folder/'PRIVATE_STATE.json'),
            'audit_file':str(self.folder/'PRIVATE_AUDIT.jsonl'),'quad_size':192,'max_sessions':2,
            'readback_atol_m':1e-6,'blender':{'host':'127.0.0.1','port':self.fixture.port,'timeout_s':10},
            'expected_identity':{'base_version':'9.7.2','implementation_revision':'v21-segment-endpoint-brief-20261030',
                'build_id':BUILD,'source_kind':'installed_distribution','protocol_version':'2025-03-26','mode':'live'}}
        save(self.folder/'PRIVATE_CONNECTOR.json',config)
        self._check()
        argv = [str(PYTHON),'-I','-B',str(ENTRY),'serve','--config',str(self.folder/'PRIVATE_CONNECTOR.json')]
        env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1')
        for name in ('PYTHONPATH','PYTHONHOME','HUMAN_EYE_CONFIG','PYTHONOPTIMIZE'):
            env.pop(name,None)
        self.stderr = (self.folder/'mcp.stderr.log').open('x',encoding='utf-8')
        try:
            self.process = subprocess.Popen(argv,cwd=self.folder,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=self.stderr,text=True,encoding='utf-8',bufsize=1,creationflags=subprocess.CREATE_NO_WINDOW)
            # A deadline can fire between Popen and assigning this reference.
            # Recheck after publication and kill the newly owned process if so.
            if self.failed:
                self._kill_owned()
            self._check()
            save(self.folder/'PROCESS.json',{'pid':self.process.pid,'argv':argv,'private_trial_state':True,'provider_calls':0})
            self._start_reader()
            init = self._rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'isolated-trial-gateway-preflight','version':'1'}})
            self.identity = init['_meta']['human_eye']
            if self.identity['build_id'] != BUILD or self.identity['source_file_count'] != 68 or self.identity['source_kind'] != 'installed_distribution':
                raise RuntimeError('Frozen installed v21 identity mismatch')
            self.tools = self._rpc('tools/list',{})['tools']
            save(self.folder/'IDENTITY.json',self.identity)
            self._check()
            return self
        except BaseException:
            self.failed = True
            self.close()
            raise

    def _rpc(self, method, params, timeout=35.0):
        self._check()
        if self.failed or self.process is None or self.process.poll() is not None:
            raise RuntimeError('MCP process unavailable or uncertain; no retry')
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('RPC timeout must be positive and finite')
        # No overlapping callers may put a second mutation behind an unknown
        # first one. Acquiring the serialization lock is itself bounded.
        local_deadline = self.clock() + timeout
        if not self._rpc_lock.acquire(timeout=self._remaining(local_deadline)):
            self._abort('private_mcp_serialization_timeout')
            raise UnconfirmedRequestError('Private MCP serialization time exhausted')
        try:
            self._check()
            request = {'jsonrpc':'2.0','id':len(self.rows)+1,'method':method,'params':params}
            started = self.clock()
            sent = queue.Queue(maxsize=1)
            try:
                wire = json.dumps(request,ensure_ascii=False,allow_nan=False)+'\n'
                self._remaining(local_deadline)
                self._check()
                process = self.process
                def writer():
                    try:
                        process.stdin.write(wire)
                        process.stdin.flush()
                        sent.put(None)
                    except BaseException as exc:
                        sent.put(exc)
                self._send_thread = threading.Thread(target=writer,
                    name='he-plugin-send-' + str(process.pid),daemon=True)
                self._send_thread.start()
                write_error = sent.get(timeout=self._remaining(local_deadline))
                self._send_thread.join(timeout=self._remaining(local_deadline))
                if write_error is not None:
                    raise write_error
                self._check()
                line = self.queue.get(timeout=self._remaining(local_deadline))
                self._remaining(local_deadline)
                self._check()
                if line is None:
                    raise RuntimeError('MCP ended before acknowledgement')
                response = json.loads(line)
                self._remaining(local_deadline)
                if response.get('id') != request['id'] or 'error' in response or 'result' not in response:
                    raise RuntimeError('Invalid MCP acknowledgement')
                row = {'request':request,'response':response,'wall_s':self.clock()-started}
                with (self.folder/'RPC.jsonl').open('a',encoding='utf-8') as f:
                    f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                self._remaining(local_deadline)
                self._check()
                self.rows.append(row)
                return response['result']
            except BaseException as exc:
                self._abort('private_mcp_request_unconfirmed')
                path=self.folder/'UNCONFIRMED_REQUEST.json'
                if not path.exists():
                    try:
                        save(path,{'request':request,'error':type(exc).__name__,
                            'unknown_outcome':True,'retry':False,
                            'cleanup_failures':list(self.cleanup_failures)})
                    except OSError:
                        pass
                raise UnconfirmedRequestError('MCP acknowledgement uncertain; no channel may continue motion') from exc
        finally:
            self._rpc_lock.release()

    def call(self, name, args):
        self._check()
        if name not in ALLOWED or type(args) is not dict:
            raise ValueError('Tool not exposed by private plugin adapter')
        if 'session_id' in args or 'task_context' in args:
            raise ValueError('Caller may not supply private session or context')
        self.start()
        values = copy.deepcopy(args)
        self._check()
        values['session_id'] = self.session_id
        if name in ('human_eye_scene_observe','human_eye_clearance_segment'):
            values['response_detail'] = 'brief'
        if name == 'human_eye_clearance_segment':
            remaining = 30.0 - self.segment_wall_s
            if remaining <= 0:
                raise RuntimeError('Aggregate plugin segment wall budget exhausted')
            request = values.get('request')
            if type(request) is not dict:
                raise ValueError('Segment request required')
            requested = request.get('max_duration_s',remaining)
            if type(requested) not in (int,float) or not 0 < requested <= 30:
                raise ValueError('Invalid segment duration')
            if self._deadline is not None:
                remaining = self._deadline.remaining(remaining)
            request['max_duration_s'] = min(requested,remaining)
        started = self.clock()
        try:
            return self._rpc('tools/call',{'name':name,'arguments':values},
                timeout=remaining if name == 'human_eye_clearance_segment' else 35.0)
        finally:
            if name == 'human_eye_clearance_segment':
                self.segment_wall_s += self.clock()-started

    def close(self):
        with self._close_lock:
            if self.closed:
                return
            self.closed = True
            started=time.monotonic()
            until=started+3.
            forced=False
            closer=None
            try:
                if self.process is not None:
                    if self.failed or (self._send_thread is not None and self._send_thread.is_alive()):
                        self._kill_owned();forced=True
                    # TextIO.close may flush or wait on a writer lock. Keep it
                    # off the caller and kill its owned pipe peer if it stalls.
                    def close_input():
                        try:
                            self.process.stdin.close()
                        except (OSError,ValueError):
                            pass
                    closer=threading.Thread(target=close_input,
                        name='he-plugin-close-' + str(self.process.pid),daemon=True)
                    closer.start()
                    try:
                        self.process.wait(timeout=min(.5,max(.001,until-time.monotonic())))
                    except subprocess.TimeoutExpired:
                        forced=True;self._kill_owned()
                        try:
                            self.process.wait(timeout=max(.001,until-time.monotonic()))
                        except subprocess.TimeoutExpired:
                            self.cleanup_failures.append('owned MCP process did not exit before cleanup deadline')
                    self._join_io(until)
                    closer.join(max(0.,until-time.monotonic()))
                    if closer.is_alive():
                        self.cleanup_failures.append('owned stdin close worker did not stop')
                    # A live reader can own TextIO's lock. Never synchronously
                    # close its stream after a failed join and lose our bound.
                    if self._reader_thread is None or not self._reader_thread.is_alive():
                        if self.process.stdout is not None:
                            self.process.stdout.close()
                    if self.process.stderr is not None:
                        self.process.stderr.close()
            finally:
                if self._deadline_unregister is not None:
                    self._deadline_unregister()
                    self._deadline_unregister=None
                if self.stderr is not None:
                    self.stderr.close()
                if self.process is not None:
                    save(self.folder/'CLOSED.json',{'pid':self.process.pid,'exit_code':self.process.returncode,
                        'forced_close':forced,'uncertain_request':self.failed,
                        'cleanup_wall_s':time.monotonic()-started,
                        'cleanup_failures':list(self.cleanup_failures),
                        'io_workers_stopped':not any(t is not None and t.is_alive()
                            for t in (self._send_thread,self._reader_thread,closer))})

    def __enter__(self):
        return self

    def __exit__(self,*_):
        self.close()
