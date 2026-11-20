"""Retain the reviewed owned Blender and installed MCP implementation."""

import ast
from pathlib import Path
import sys
from textwrap import dedent
import time

from budget import Budget
from common import ARMS, BLENDER, DISPLAY, GENERIC_WORKER, PRIOR, ROOT, SLOTS, asset_identity, load, product_for, save, sha


PREVIOUS = PRIOR / 'harness/owned_runtime.py'
_previous = load('_cross_task_original_runtime', PREVIOUS)
transport = load('_cross_task_stdio', DISPLAY / 'harness/reused/stdio_checks.py')


def start_generic_native(start_callable, *, blender, asset, workspace, deadline_ns, condition, expected_asset_sha256):
    return start_callable(blender=blender, asset=asset, workspace=workspace, deadline_ns=deadline_ns,
                          condition=condition, expected_asset_sha256=expected_asset_sha256, max_calls=48)


def reuse_method(name, before, after, *, local_product=False):
    source = PREVIOUS.read_text(encoding='utf8')
    tree = ast.parse(source, filename=str(PREVIOUS))
    klass = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Runtime')
    original = next(node for node in klass.body if isinstance(node, ast.FunctionDef) and node.name == name)
    method = dedent('\n'.join(source.splitlines()[original.lineno - 1:original.end_lineno]))
    if method.count(before) != 1 or (local_product and method.count('SOURCE_SHA') != 2):
        raise ValueError('original_runtime_anchor_changed/' + name)
    method = method.replace(before, after)
    if local_product:
        method = method.replace('SOURCE_SHA', 'self.source_sha')
    scope = dict(vars(_previous))
    exec(compile(method, str(PREVIOUS), 'exec'), scope)
    return scope[name]


class Runtime(_previous.Runtime):
    _start_public_mcp = reuse_method('_start_public_mcp', "'--phase', 'formal'", "'--phase', self.phase", local_product=True)
    public_request = reuse_method('public_request',
        "if self.client is None or arguments.get('query', {}).get('mode') != 'source_region':\n"
        "        raise ValueError('registered_source_region_public_query_required')",
        "if self.client is None or type(arguments) is not dict:\n"
        "        raise ValueError('installed_read_only_observe_entry_required')")
    close = reuse_method('close', "spawn_status='spawned' if spawned is not None else 'unknown',",
        "spawn_status='spawned' if spawned is not None else (\n"
        "                'not_spawned' if (self.startup_cleanup or {}).get('no_process_created') is True else 'unknown'),")

    def __init__(self, folder, label, task_deadline, owned_deadline):
        group, self.phase = SLOTS[label]
        super().__init__(folder, label, group, task_deadline, owned_deadline)
        self.arm = ARMS[label]
        self.binding_path, self.binding = product_for(label)
        self.source_sha = self.binding['source_sha256']
        self.runroot = self.folder
        self.product_tools = []
        self.native_start_entered = False
        self.startup_cleanup = None

    def start(self):
        self.check()
        self.started = time.perf_counter_ns()
        asset, digest = asset_identity()
        binding = self.binding
        sys.path.insert(0, binding['dependency_root'])
        self.product_root = binding['install_root']
        self.native_audit = load('_cross_task_native_readonly_audit', ROOT /
                                 'verification/m4_target_task_consumption_001/native_consumer_audit.py')
        self.native_audit_installed = False
        bootstrap = load('_cross_task_device_bootstrap', PRIOR / 'harness/reused/verified_bootstrap.py')
        self.guard = bootstrap.bootstrap(binding)
        native_module = load('_cross_recovery_generic_blender', GENERIC_WORKER)
        self.claim = self.budget.reserve('Blender_start', self.label, self.phase)
        self.native = self.launch_native(native_module, asset, digest)
        self.native_handle = self._retain(self.native.process, 'NATIVE_RUNTIME_PROOF.json')
        if self.group == 'P':
            self._start_public_mcp(self.binding_path, binding)
            save(self.folder / 'INSTALLED_TOOLS.json', self.product_tools)
        self.prepare_device(digest)
        self.check()
        save(self.folder / 'RUNTIME_READY.json', {'started_ns': self.started, 'ready_ns': time.perf_counter_ns(),
             'group': self.group, 'arm': self.arm, 'phase': self.phase, 'native_pid': self.native.process.pid,
             'product_PID': None if self.client is None else self.client.process.pid,
             'asset_copy_sha256': sha(self.native.workspace / 'input.blend'),
             'product_source_sha256': self.source_sha, 'prior_task_captures': 0,
             'worker': str(GENERIC_WORKER), 'worker_sha256': sha(GENERIC_WORKER),
             'startup_scope': 'Owned file load, read-only device preparation and optional MCP handshake.'})

    def launch_native(self, native_module, asset, digest):
        # NativeSession.start owns the original launcher until it returns. Observe
        # its existing kill/wait path to retain evidence even if startup raises.
        startup_pending = True

        class ObservedNativeSession(native_module.NativeSession):
            def _kill(session):
                try:
                    return super()._kill()
                finally:
                    if startup_pending:
                        process = session.process
                        exit_code = process.poll() if process is not None else None
                        self.startup_cleanup = {'no_process_created': process is None,
                            'pid': None if process is None else process.pid, 'exit_code': exit_code,
                            'process_reaped': None if process is None else exit_code is not None,
                            'observed_ns': time.perf_counter_ns(), 'basis': 'generic launcher-owned Popen'}

        self.native_start_entered = True
        try:
            return start_generic_native(ObservedNativeSession.start, blender=BLENDER, asset=asset,
            workspace=self.folder / 'native', deadline_ns=self.owned_deadline, condition=self.group,
            expected_asset_sha256=digest)
        finally:
            startup_pending = False

    def _device(self, folder, digest):
        from frame_device import FrameDevice

        return FrameDevice(runroot=folder, asset_sha256=digest, group=self.group, label=self.label,
            native_call=self._native_call, terminal_call=self._terminal_call,
            budget=self.budget, phase=self.phase, check=self.check)

    def prepare_device(self, digest):
        self.device = self._device(self.folder, digest)
        self.buffers = self.device.buffers
        self.cameras = self.device.cameras

    def capture_initial(self):
        self.check()
        directory = self.folder / 'initial_capture'
        directory.mkdir(exist_ok=False)
        receipt = self._device(directory, self.device.asset_sha256).export_terminal()
        self.check()
        return receipt

    def render_local(self, direction, target_world_m, view_span_m, fresh=False):
        return self.device.render_local(direction, target_world_m, view_span_m, fresh=fresh)
