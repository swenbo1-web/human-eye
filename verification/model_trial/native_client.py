"""Owner of one finite, isolated Blender fixture; no generic code API.

Importing or constructing this class starts neither Blender nor a model.
Use the pinned dependency interpreter when constructing a LiveSpatialService.
Private files in ``folder`` (including the token) must never enter model input.
"""
from __future__ import annotations

import importlib
import json
import math
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time

from .deadline import EpisodeDeadline, DeadlineExceeded


ROOT = Path(__file__).resolve().parents[2]
SITE_ROOT = ROOT / '.human-eye/releases/9.7.2+20261030.segment.brief.r1/site-packages'
DEPENDENCY_PYTHON = ROOT / '.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Scripts/python.exe'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
BUILD_ID = 'sha256:71c5bb2ecab267d6d055b20ee3105493296e58d1d82fa109df90f789dded5225'
LIFETIME_S = 360
CASES = frozenset({'floor', 'tilted', 'dense', 'occluded', 'readonly',
                   'readonly_occluded', 'open_focal', 'open_reference'})
PUBLIC_COMMANDS = frozenset({'native_scene_query', 'native_transform', 'native_look'})


class NativeCommandError(RuntimeError):
    def __init__(self, code, message, *, quarantined=False):
        self.code = code
        self.quarantined = bool(quarantined)
        super().__init__(message)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_config(case, angle_deg, gap_m, origin, readonly):
    if case not in CASES:
        raise ValueError('Unknown fixture case')
    if not _finite(angle_deg) or not -30 <= angle_deg <= 30:
        raise ValueError('angle_deg must be finite in [-30,30]')
    if not _finite(gap_m) or not 0 <= gap_m <= .1:
        raise ValueError('gap_m must be finite in [0,.1] metres')
    if not isinstance(origin, (list, tuple)) or len(origin) != 3 or any(
            not _finite(x) or abs(x) > .1 for x in origin):
        raise ValueError('origin must contain three finite metre coordinates in [-.1,.1]')
    if type(readonly) is not bool:
        raise ValueError('readonly must be boolean')


def _environment():
    value = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8', PYTHONNOUSERSITE='1')
    for name in ('PYTHONPATH', 'PYTHONHOME', 'HUMAN_EYE_CONFIG', 'PYTHONOPTIMIZE'):
        value.pop(name, None)
    return value


def _save_new(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def _loads(raw):
    def constant(_):
        raise ValueError('Nonfinite JSON')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    value = json.loads(raw, parse_constant=constant, object_pairs_hook=pairs)
    json.dumps(value, allow_nan=False)
    return value


class OwnedFixture:
    def __init__(self, folder, case='tilted', angle_deg=10, gap_m=.004, origin=None, readonly=False):
        origin = [0., 0., 0.] if origin is None else origin
        validate_config(case, angle_deg, gap_m, origin, readonly)
        self.folder = Path(folder).resolve()
        self.case = case
        self.angle_deg = 0. if case == 'floor' else float(angle_deg)
        self.gap_m = float(gap_m)
        self.origin = list(map(float, origin))
        self.readonly = readonly or case in {'readonly', 'readonly_occluded'}
        self.site_root = SITE_ROOT.resolve()
        self.dependency_python = DEPENDENCY_PYTHON.resolve()
        self.port = None
        self.process = None
        self.__token = secrets.token_hex(32)
        self._logs = []
        self._started = False
        self._closed = False
        self._poisoned = False
        self._watchdog = None
        self._deadline = None
        self._deadline_unregister = None
        self._prepare_process = None
        self._active_sockets = set()
        self._ownership_lock = threading.RLock()
        self._episode_bound = False
        self._episode_ack = None
        self.cleanup_info = None
        self.startup = None

    @property
    def bound_deadline(self):
        return self._deadline

    @property
    def deadline_budget(self):
        return self._deadline

    @property
    def deadline_enforced(self):
        return (self._deadline is not None and self._deadline.watchdog_active
                and not self._closed and not self._poisoned)

    @property
    def uncertain_outcome(self):
        return self._poisoned

    def bind_deadline(self, budget):
        """Bind once without starting Blender or issuing a host request."""
        if not isinstance(budget, EpisodeDeadline):
            raise TypeError('Expected one shared EpisodeDeadline')
        if self._deadline is not None:
            if self._deadline is not budget:
                raise ValueError('Owned fixture deadline cannot be replaced or extended')
            budget.check()
            return self
        if self._closed or self._poisoned:
            raise RuntimeError('Closed/uncertain fixture cannot acquire a deadline')
        budget.check()
        self._deadline = budget
        self._deadline_unregister = budget.add_expiry_callback(self._expire_owned)
        budget.check()
        return self

    def _remaining(self, cap):
        return self._deadline.remaining(cap) if self._deadline is not None else cap

    def _check_deadline(self):
        if self._closed:
            raise RuntimeError('OwnedFixture is closed; no restart or retry')
        if self._deadline is not None:
            self._deadline.check()

    def _expire_owned(self):
        """Nonblocking revocation; a later close separately records cleanup."""
        self._poisoned = True
        with self._ownership_lock:
            sockets = tuple(self._active_sockets)
            children = (self._prepare_process, self.process)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except OSError:
                pass
        for child in children:
            if child is not None and child.poll() is None:
                try:
                    child.kill()
                except OSError:
                    pass

    def _ensure_episode_bound(self):
        if self._deadline is not None and not self._episode_bound:
            try:
                self._check_deadline()
                ack = self._exchange('owner_begin_episode', {
                    'started_monotonic': self._deadline.started,
                    'deadline_monotonic': self._deadline.expires_at}, _synchronize=False)
                self._check_deadline()
                if (not isinstance(ack,dict) or ack.get('episode_started') is not True
                        or not _finite(ack.get('started_monotonic'))
                        or not _finite(ack.get('deadline_monotonic'))
                        or ack['started_monotonic'] > self._deadline.started
                        or not ack['started_monotonic'] < ack['deadline_monotonic']
                        or ack['deadline_monotonic'] > self._deadline.expires_at
                        or ack['deadline_monotonic'] <= self._deadline.clock()):
                    raise RuntimeError('Owned fixture did not enforce the bound deadline')
                self._episode_ack = ack
                self._episode_bound = True
            except BaseException:
                self._poisoned = True
                self.close()
                raise

    def _prepare(self):
        # A fresh pinned interpreter prevents another checkout's already imported
        # human_eye_plugin package from supplying identity or fixed template bytes.
        code = '''import hashlib,json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from human_eye_plugin.runtime_identity import runtime_identity
from human_eye_plugin.blender_mcp_host import BlenderMCPHost
root=pathlib.Path(sys.argv[1]).resolve()
identity=runtime_identity()
if identity['build_id']!=sys.argv[2]: raise RuntimeError('Installed v21 identity changed')
if identity['source_kind']!='installed_distribution': raise RuntimeError('Expected installed v21 distribution')
for entry in identity['source_files']:
 if hashlib.sha256((root/entry['path']).read_bytes()).hexdigest()!=entry['sha256']: raise RuntimeError('Runtime bytes changed')
host=BlenderMCPHost(root,port=1)
template=host._code('capture',{},'OWNED_FIXED_NONCE')
host.close()
source=root/'human_eye_plugin/blender_host.py'
print(json.dumps({'identity':identity,'template':template,'source_path':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}))
'''
        self._check_deadline()
        prepare = subprocess.Popen([str(self.dependency_python), '-I', '-B', '-c', code,
                                    str(self.site_root), BUILD_ID], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, encoding='utf-8', env=_environment(),
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with self._ownership_lock:
            self._prepare_process = prepare
        try:
            self._check_deadline()
            stdout, stderr = prepare.communicate(timeout=self._remaining(30))
            self._check_deadline()
            if prepare.returncode != 0:
                raise subprocess.CalledProcessError(prepare.returncode, prepare.args, stdout, stderr)
        except BaseException:
            if prepare.poll() is None:
                prepare.kill()
            prepare.communicate(timeout=2)
            raise
        finally:
            with self._ownership_lock:
                self._prepare_process = None
        value = _loads(stdout)
        template_path = self.folder / 'runtime_fixed_template.txt'
        with template_path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(value['template'])
        import hashlib
        _save_new(self.folder / 'SOURCE_IDENTITY.json', value['identity'])
        _save_new(self.folder / 'config.json', {
            'case': self.case, 'angle_deg': self.angle_deg, 'gap_m': self.gap_m,
            'origin': self.origin, 'readonly': self.readonly, 'token': self.__token,
            'source_path': value['source_path'], 'source_sha256': value['source_sha256'],
            'template_path': str(template_path),
            'template_sha256': hashlib.sha256(template_path.read_bytes()).hexdigest(),
            'runtime_build_id': BUILD_ID, 'lifetime_s': LIFETIME_S, 'episode_s': 180})

    def start(self):
        self._start_process()
        self._ensure_episode_bound()
        return self

    def _start_process(self):
        self._check_deadline()
        if self._closed:
            raise RuntimeError('OwnedFixture is closed; no restart or retry')
        if self._started:
            if self.process.poll() is not None:
                raise RuntimeError('Owned Blender exited; no restart or retry')
            return self
        self._started = True
        try:
            self.folder.mkdir(parents=True, exist_ok=False)
            self._prepare()
            self._check_deadline()
            self._logs = [(self.folder / ('blender.' + name + '.log')).open('x', encoding='utf-8')
                          for name in ('stdout', 'stderr')]
            argv = [str(BLENDER), '--factory-startup', '--disable-autoexec', '--background',
                    '--python', str(Path(__file__).with_name('native_fixture.py')), '--', str(self.folder)]
            self.process = subprocess.Popen(argv, stdout=self._logs[0], stderr=self._logs[1],
                                            env=_environment(), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self._check_deadline()
            # This timer bounds native rendering or a blocked fixed helper too.
            # It can address only the newly created process owned by this object.
            owned_process = self.process
            def expire_owned_process():
                if owned_process.poll() is None:
                    (self.folder / 'lifetime_expired.flag').touch(exist_ok=True)
                    (self.folder / 'stop.flag').touch(exist_ok=True)
                    owned_process.terminate()
            self._watchdog = threading.Timer(LIFETIME_S, expire_owned_process)
            self._watchdog.daemon = True
            self._watchdog.start()
            _save_new(self.folder / 'PROCESS.json', {'pid': self.process.pid, 'argv': argv})
            deadline = time.monotonic() + 60
            while not (self.folder / 'startup.json').is_file():
                self._check_deadline()
                if self.process.poll() is not None:
                    raise RuntimeError('Owned Blender exited during startup')
                if time.monotonic() >= deadline:
                    raise RuntimeError('Owned Blender startup timeout; no retry')
                time.sleep(self._remaining(.05))
            self.startup = _loads((self.folder / 'startup.json').read_bytes())
            if (self.startup['pid'] != self.process.pid or self.startup['runtime_build_id'] != BUILD_ID
                    or not 1 <= self.startup['port'] <= 65535):
                raise RuntimeError('Owned Blender startup identity mismatch')
            self.port = self.startup['port']
            self._check_deadline()
            return self
        except BaseException:
            # A local preparation/startup timeout may precede the timer
            # callback. Revoke this adapter independently of timer ordering;
            # this is no claim that a physical write was attempted.
            self._poisoned = True
            self.close()
            raise

    def _exchange(self, kind, params, *, _synchronize=True):
        self._start_process()
        if _synchronize and kind != 'owner_begin_episode':
            self._ensure_episode_bound()
        if self._poisoned:
            raise RuntimeError('Owned fixture transport invalidated; no retry')
        payload = json.dumps({'type': kind, 'params': params, 'token': self.__token},
                             allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(payload) > 32768:
            raise ValueError('Native request exceeds 32KiB')
        connection = None
        try:
            self._check_deadline()
            connection = socket.create_connection(('127.0.0.1', self.port), timeout=self._remaining(10))
            with self._ownership_lock:
                self._active_sockets.add(connection)
            self._check_deadline()
            connection.settimeout(self._remaining(10))
            connection.sendall(payload)
            self._check_deadline()
            connection.shutdown(socket.SHUT_WR)
            raw = bytearray()
            response_deadline = time.monotonic() + 15
            while True:
                remaining = response_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Native response deadline')
                connection.settimeout(self._remaining(remaining))
                block = connection.recv(65536)
                self._check_deadline()
                if not block:
                    break
                raw.extend(block)
                if len(raw) > 16 * 1024 * 1024:
                    raise ValueError('Native response exceeds 16MiB')
            result = _loads(raw)
            self._check_deadline()
            if not isinstance(result, dict) or result.get('status') not in {'success', 'error'}:
                raise ValueError('Invalid native response')
        except BaseException:
            self._poisoned = True
            self.close()
            raise
        finally:
            if connection is not None:
                with self._ownership_lock:
                    self._active_sockets.discard(connection)
                connection.close()
        if result['status'] == 'error':
            error = result['error']
            if error.get('quarantined'):
                self._poisoned = True
            raise NativeCommandError(error['code'], error['message'], quarantined=error.get('quarantined', False))
        return result['result']

    def call(self, name, params=None):
        if name not in PUBLIC_COMMANDS:
            raise ValueError('Unsupported public native command')
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError('Native params must be an object')
        return self._exchange(name, params)

    def owner_truth(self):
        return self._exchange('owner_truth', {})

    def owner_visibility(self, view='SCENE'):
        if view not in {'XY','XZ','SCENE'}:
            raise ValueError('view must be XY, XZ or SCENE')
        return self._exchange('owner_visibility', {'view':view})

    def begin_episode(self):
        if self._deadline is not None:
            self.start()
            return dict(self._episode_ack)
        self._episode_ack = self._exchange('owner_begin_episode', {})
        return dict(self._episode_ack)

    def engine_host(self):
        self.start()
        sys.path.insert(0, str(self.site_root))
        module = importlib.import_module('human_eye_plugin.blender_mcp_host')
        if Path(module.__file__).resolve() != self.site_root / 'human_eye_plugin/blender_mcp_host.py':
            raise RuntimeError('Another runtime package was already imported')
        identity = importlib.import_module('human_eye_plugin.runtime_identity').runtime_identity()
        if identity['build_id'] != BUILD_ID:
            raise RuntimeError('Installed runtime identity mismatch')
        return module.BlenderMCPHost(self.site_root, port=self.port, timeout_s=15)

    def close(self):
        with self._ownership_lock:
            if self._closed:
                return
            self._closed = True
        if self._watchdog is not None:
            self._watchdog.cancel()
        # A socket timeout can race the timer callback. Revoke the owned
        # process immediately for an unknown outcome instead of unregistering
        # the callback and granting a fresh graceful-shutdown interval.
        if self._deadline is not None and self._poisoned:
            self._expire_owned()
        if self._deadline_unregister is not None:
            self._deadline_unregister()
        cleanup_started = time.monotonic()
        forced = False
        with self._ownership_lock:
            connections = tuple(self._active_sockets)
            prepare = self._prepare_process
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        try:
            if prepare is not None and prepare.poll() is None:
                forced = True
                prepare.kill()
                prepare.wait(timeout=2)
            if self.process is not None and self.process.poll() is None:
                (self.folder / 'stop.flag').touch(exist_ok=True)
                try:
                    self.process.wait(timeout=1 if self._deadline is not None else 15)
                except subprocess.TimeoutExpired:
                    forced = True
                    self.process.kill()
                    self.process.wait(timeout=2)
        finally:
            for stream in self._logs:
                stream.close()
            self._logs.clear()
            self.cleanup_info = {'cleanup_wall_s':time.monotonic()-cleanup_started,
                'forced_kill':forced, 'deadline_bound':self._deadline is not None,
                'prepare_exit_code':prepare.returncode if prepare is not None else None,
                'exit_code':self.process.returncode if self.process is not None else None,
                'uncertain_outcome':self._poisoned}
            if self.folder.is_dir():
                _save_new(self.folder/'CLEANUP.json',self.cleanup_info)

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()
