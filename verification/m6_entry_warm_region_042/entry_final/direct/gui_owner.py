"""036 owned hidden GUI, reusing the verified 035 normal add-on launcher.

Import/prepare do not start Blender. Only Owned(...) starts a child, after the
coordinator supplies its explicit available exclusive-window record.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback

HERE = Path(__file__).resolve().parent
PRIVATE = Path('D:\\HumanEye\\runs\\M6-042-ENTRY-WARM-REGION\\E_FINAL_001\\direct')
CYCLE = 'M6-042-E-FINAL-DIRECT'
ADDON = Path('C:/Users/Administrator/AppData/Roaming/Blender Foundation/Blender/5.2/scripts/addons/blender_mcp.py')
ADDON_SHA = 'c836e1e7f9a7177e0101abeb9b34d80103e194dcdec8d086deb0bd9251451767'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
BLENDER_SHA = '284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb'
ASSET_SHAS = {
    '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d': 'Yanyite',
    '8729d98bcbcc774b36b69e7df73ac48c5ec09553df27e55bb24b6fbce28bc431': 'D48',
    '9bba515e72bcbd307d3b41b42d426e253d9da56b1723c0da21663b3653bb7cd8': 'G60_D12',
}
MAX_WIRE = 64*1024*1024


def need(value, reason):
    if not value:
        raise ValueError('gui035_'+reason)


def artifact(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}


def save(path, value):
    path = Path(path).resolve()
    need(path.is_relative_to(PRIVATE.resolve()), 'output_scope')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')
    return artifact(path)


def _copy_exact(source, destination, expected=None):
    raw = Path(source).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    need(expected is None or digest == expected, 'source_pin')
    destination = Path(destination).resolve()
    need(destination.is_relative_to(PRIVATE.resolve()), 'copy_scope')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        need(destination.read_bytes() == raw, 'retained_support_changed')
    else:
        with destination.open('xb') as stream:
            stream.write(raw)
    return artifact(destination)


def prepare():
    """Pin/copy sources only. No GUI, socket, Blender or shared configuration write."""
    original = artifact(ADDON)
    need(original['sha256'] == ADDON_SHA, 'installed_addon_pin')
    copied = _copy_exact(ADDON, PRIVATE/'gui_support/blender_mcp.py', ADDON_SHA)
    identity = _copy_exact(HERE.parent/'m6_bounded_surface_scan_live_028/live_host.py',
                           PRIVATE/'gui_support/identity_tools.py')
    binary = artifact(BLENDER)
    need(binary['sha256'] == BLENDER_SHA, 'Blender_binary_pin')
    return {'addon_original': original, 'addon': copied, 'identity_tools': identity,
            'blender': binary, 'worker': artifact(HERE/'gui_worker.py'), 'launcher': artifact(__file__)}


def _load_identity(path):
    spec = importlib.util.spec_from_file_location('_gui035_pinned_identity_tools', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hide_owned_windows(pid):
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    rows = []
    @callback_type
    def inspect(hwnd, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            before = bool(user.IsWindowVisible(hwnd))
            user.ShowWindow(hwnd, 0)
            rows.append({'hwnd': int(hwnd), 'visible_before': before,
                         'visible_after': bool(user.IsWindowVisible(hwnd))})
        return True
    user.EnumWindows(inspect, 0)
    return rows


class Owned:
    """Existing controller-compatible GUI handle, with no private business server."""
    def __init__(self, folder, asset, support, window, *, deadline_ns=None):
        need(os.name == 'nt', 'Windows_required')
        need(window['status'] == 'available' and window['cycle_id'] == CYCLE
             and bool(window.get('token')), 'explicit_exclusive_window_required')
        now = time.perf_counter_ns()
        self.deadline_ns = now+590*10**9 if deadline_ns is None else deadline_ns
        need(type(self.deadline_ns) is int and 0 < self.deadline_ns-now <= 600*10**9, 'original_owned_deadline')
        self.workspace = Path(folder).resolve()
        need(self.workspace.is_relative_to(PRIVATE.resolve()) and not self.workspace.exists(), 'fresh_owned_workspace')
        self.workspace.mkdir(parents=True)
        self.support, self.asset = support, asset
        self.process = None
        self.ready = None
        self.closed = False
        self.native = self
        self.host = '127.0.0.1'
        self.sequence = 0
        self.request_lock = threading.Lock()
        self.identity_tools = _load_identity(support['identity_tools']['path'])
        self.started_ns = now
        self.config = None
        try:
            source = artifact(asset['path'])
            need(source == {key: asset[key] for key in ('path','bytes','sha256')}
                 and source['sha256'] in ASSET_SHAS, 'fixed_asset_pin')
            for name in ('addon','addon_original','identity_tools','blender','worker','launcher'):
                need(artifact(support[name]['path']) == support[name], 'frozen_support_'+name)
            need(support['addon']['sha256'] == support['addon_original']['sha256'] == ADDON_SHA
                 and support['blender']['sha256'] == BLENDER_SHA, 'fixed_runtime_pins')
            copied = self.workspace/'input.blend'
            shutil.copyfile(asset['path'], copied)
            need(artifact(copied)['sha256'] == source['sha256'], 'asset_copy')
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
                reservation.bind((self.host, 48142))
                self.port = reservation.getsockname()[1]
            directories = {name: self.workspace/name for name in (
                'config','scripts','datafiles','extensions','appdata','localappdata','temp')}
            for directory in directories.values():
                directory.mkdir()
            self.config = {'schema': '036-gui-startup-v1', 'workspace': str(self.workspace),
                'asset': str(Path(asset['path']).resolve()), 'asset_copy': str(copied),
                'asset_sha256': source['sha256'], 'asset_label': ASSET_SHAS[source['sha256']], 'addon': support['addon'],
                'addon_original': support['addon_original'], 'deadline_ns': self.deadline_ns,
                'port': self.port, 'window': window, 'fresh_directories': {k:str(v) for k,v in directories.items()}}
            config_ref = save(self.workspace/'CONFIG.json', self.config)
            env = {key:value for key,value in os.environ.items()
                   if not key.upper().startswith(('BLENDER_','BLENDERMCP_','PYTHON'))}
            env.update(BLENDER_USER_CONFIG=str(directories['config']), BLENDER_USER_SCRIPTS=str(directories['scripts']),
                BLENDER_USER_DATAFILES=str(directories['datafiles']), BLENDER_USER_EXTENSIONS=str(directories['extensions']),
                APPDATA=str(directories['appdata']), LOCALAPPDATA=str(directories['localappdata']),
                TEMP=str(directories['temp']), TMP=str(directories['temp']))
            command = [support['blender']['path'], '--factory-startup', '--disable-autoexec',
                '--window-geometry', '0', '0', '320', '240', str(copied), '--python-exit-code', '1',
                '--python', support['worker']['path'], '--', config_ref['path']]
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            with (self.workspace/'GUI.stdout.txt').open('xb') as out, (self.workspace/'GUI.stderr.txt').open('xb') as err:
                self.process = subprocess.Popen(command, cwd=self.workspace, env=env, stdin=subprocess.DEVNULL,
                    stdout=out, stderr=err, startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
            self.pid = self.process.pid
            save(self.workspace/'SPAWN.json', {'pid': self.pid, 'command': command, 'cwd': str(self.workspace),
                'GUI_mode_no_background_flag': True, 'startupinfo_SW_HIDE': True,
                'private_config_environment': {key:env[key] for key in (
                    'BLENDER_USER_CONFIG','BLENDER_USER_SCRIPTS','BLENDER_USER_DATAFILES','BLENDER_USER_EXTENSIONS',
                    'APPDATA','LOCALAPPDATA','TEMP','TMP')}, 'started_ns': now, 'deadline_ns': self.deadline_ns,
                'source_refs': support, 'input': asset})
            startup_deadline = min(self.deadline_ns, now+45*10**9)
            while time.perf_counter_ns() < startup_deadline:
                failure = self.workspace/'START_FAILURE.json'
                if failure.exists():
                    raise RuntimeError('GUI worker startup failed: '+failure.read_text(encoding='utf8'))
                need(self.process.poll() is None, 'GUI_exited_before_ready')
                ready_path = self.workspace/'READY.json'
                if ready_path.exists():
                    try:
                        ready = json.loads(ready_path.read_bytes())
                    except json.JSONDecodeError:
                        pass
                    else:
                        self.ready = ready
                        break
                _hide_owned_windows(self.pid)
                time.sleep(.05)
            need(self.ready is not None, 'GUI_startup_timeout')
            need(self.ready['pid'] == self.pid and self.ready['host'] == self.host and self.ready['port'] == self.port
                 and self.ready['background'] is False and self.ready['ordinary_queue_roundtrip_required'] is True
                 and self.ready['compiled_exact_source_sha256'] == ADDON_SHA, 'GUI_ready_binding')
            process = self.identity_tools.process_identity(self.pid)
            port = self.identity_tools.port_identity(self.host, self.port, self.pid)
            need(port['owned_listener'], 'GUI_owned_listener')
            need(Path(process['image_path']).resolve() == Path(support['blender']['path']).resolve(), 'GUI_binary_identity')
            ping = self.ping(timeout_s=10)
            need(ping['response'] == {'status':'success','result':{'pong':True}}, 'normal_queue_ping')
            hidden = _hide_owned_windows(self.pid)
            need(not any(row['visible_after'] for row in hidden), 'GUI_hidden_windows')
            self.start_proof = {'window': window, 'process': process, 'port_ownership': port,
                'ready': self.ready, 'startup_ping': ping, 'hidden_windows': hidden,
                'source_refs': support, 'scene': asset, 'startup_ns': time.perf_counter_ns()-now,
                'normal_addon_unmodified': True, 'normal_queue_roundtrip_verified': True,
                'business_relay': False, 'business_monkeypatch': False}
            save(self.workspace/'OWNERSHIP.json', self.start_proof)
        except BaseException as error:
            save(self.workspace/'LAUNCH_FAILURE.json', {'type':type(error).__name__,'error':str(error),
                'traceback':traceback.format_exc(),'at_ns':time.perf_counter_ns()})
            if self.process is not None:
                try:
                    self._terminate_owned('startup_failure')
                except BaseException as close_error:
                    save(self.workspace/'STARTUP_CLOSE_FAILURE.json', {'error':repr(close_error)})
            raise

    def _check(self):
        need(not self.closed and self.process is not None and self.process.poll() is None, 'owned_process_not_running')
        need(time.perf_counter_ns() < self.deadline_ns, 'original_owned_deadline_expired')

    def request(self, payload, *, timeout_s=30, max_response_bytes=MAX_WIRE):
        """Trusted QA/control only; product business connects directly to this listener."""
        self._check()
        need(type(timeout_s) in (int,float) and 0 < timeout_s <= 60, 'request_timeout')
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',',':')).encode('utf8')
        need(len(raw) <= 256*1024 and 1 <= max_response_bytes <= MAX_WIRE, 'request_bounds')
        with self.request_lock:
            self.sequence += 1
            directory = self.workspace/'qa_wire'
            directory.mkdir(exist_ok=True)
            stem = directory/f'{self.sequence:03d}'
            with stem.with_suffix('.TX.bin').open('xb') as stream:
                stream.write(raw)
            started = time.perf_counter_ns()
            deadline = min(self.deadline_ns, started+int(timeout_s*1e9))
            response = bytearray()
            parsed = None
            error = None
            try:
                with socket.create_connection((self.host,self.port),timeout=max(.001,(deadline-time.perf_counter_ns())/1e9)) as conn:
                    conn.sendall(raw)
                    while True:
                        remaining = (deadline-time.perf_counter_ns())/1e9
                        need(remaining > 0, 'QA_response_timeout')
                        conn.settimeout(remaining)
                        chunk = conn.recv(65536)
                        if not chunk:
                            raise EOFError('ordinary add-on closed before a complete JSON response')
                        response.extend(chunk)
                        need(len(response) <= max_response_bytes, 'QA_response_bytes')
                        try:
                            text = response.decode('utf8')
                            value,end = json.JSONDecoder().raw_decode(text)
                        except (UnicodeDecodeError,json.JSONDecodeError):
                            continue
                        need(not text[end:].strip(), 'QA_extra_response')
                        parsed = value
                        break
                self._check()
            except BaseException as failure:
                error = {'type':type(failure).__name__,'error':str(failure)}
                raise
            finally:
                with stem.with_suffix('.RX.bin').open('xb') as stream:
                    stream.write(response)
                receipt = {'request':payload,'response':parsed,'error':error,'elapsed_ns':time.perf_counter_ns()-started,
                    'original_deadline_ns':self.deadline_ns,'endpoint':{'host':self.host,'port':self.port,'pid':self.pid},
                    'tx':artifact(stem.with_suffix('.TX.bin')),'rx':artifact(stem.with_suffix('.RX.bin')),
                    'origin':'actual_unmodified_addon_TCP_queue'}
                save(stem.with_suffix('.json'),receipt)
            return receipt

    def run(self, code, *, timeout_s=30):
        need(type(code) is str, 'QA_code_string')
        return self.request({'type':'execute_code','params':{'code':code}},timeout_s=timeout_s)

    def execute(self, code, timeout=30):
        return self.run(code,timeout_s=timeout)

    def ping(self, *, timeout_s=10):
        return self.request({'type':'ping'},timeout_s=timeout_s)

    def _terminate_owned(self, reason):
        need(self.process is not None and self.process.pid == self.pid, 'owned_Popen_required')
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        result = {'pid':self.pid,'reason':reason,'returncode':self.process.returncode,
                  'forced':True,'only_owned_Popen':True,'at_ns':time.perf_counter_ns()}
        save(self.workspace/'FORCED_CLOSE.json',result)
        return result

    def close(self):
        need(not self.closed and self.process is not None and self.process.pid == self.pid, 'close_owned_once')
        started = time.perf_counter_ns()
        receipt = None
        failure = None
        forced = None
        callback = self.workspace/'GUI_CLOSED.json'
        # Ordinary add-on execute_code schedules shutdown *after* its original
        # queue sends the acknowledgement. No serving method or timer is wrapped.
        code = ("import bpy,json,sys,os,time\n"
            "def _close_035_owned_gui():\n"
            "    module=sys.modules['blender_mcp']\n"
            "    server=getattr(bpy.types,'blendermcp_server',None)\n"
            "    module.unregister()\n"
            f"    with open({str(callback)!r},'x',encoding='utf8') as out:\n"
            "        json.dump({'pid':os.getpid(),'stopped':server is not None and not server.running,'at_ns':time.perf_counter_ns()},out)\n"
            "    bpy.ops.wm.quit_blender()\n"
            "    return None\n"
            "bpy.app.timers.register(_close_035_owned_gui,first_interval=.2)\n"
            "print(json.dumps({'scheduled':True,'pid':os.getpid()}))\n")
        try:
            if self.process.poll() is None:
                receipt = self.run(code,timeout_s=10)
                need(receipt['response'].get('status') == 'success', 'ordinary_close_schedule')
            self.process.wait(timeout=15)
        except BaseException as error:
            failure = {'type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc()}
            if self.process.poll() is None:
                forced = self._terminate_owned('ordinary_GUI_close_failed')
        finally:
            self.closed = True
        after = self.identity_tools.port_identity(self.host,self.port,self.pid)
        original = artifact(self.asset['path'])['sha256'] == self.asset['sha256']
        copy = artifact(self.config['asset_copy'])['sha256'] == self.asset['sha256']
        addon = all(artifact(self.support[k]['path'])['sha256'] == ADDON_SHA for k in ('addon','addon_original'))
        callback_value = json.loads(callback.read_bytes()) if callback.exists() else None
        good = (failure is None and forced is None and self.process.returncode == 0 and not after['owned_listener']
                and original and copy and addon and callback_value is not None and callback_value['pid']==self.pid
                and callback_value['stopped'] is True)
        result = {'status':'pass' if good else 'fail','pid':self.pid,'method':'original_addon_execute_code_then_original_stop_unregister_and_GUI_quit',
            'schedule_receipt':receipt,'GUI_close_callback':callback_value,'error':failure,'forced':forced,
            'exit_code':self.process.returncode,'process_reaped':self.process.poll() is not None,'released_port':after,
            'source_unchanged':original,'owned_copy_unchanged':copy,'original_addon_unchanged':addon,
            'elapsed_ns':time.perf_counter_ns()-started}
        save(self.workspace/'TERMINAL_OWNERSHIP.json',result)
        need(good,'GUI_close_or_source_custody_failed')
        return result


if __name__ == '__main__':
    # Explicitly preparation only. Actual GUI launch belongs to the coordinator.
    print(json.dumps(prepare(),indent=2))
