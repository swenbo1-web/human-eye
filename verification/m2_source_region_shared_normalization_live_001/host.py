"""One owned Blender and one installed production stdio process per live arm."""

import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
V = HERE.parent
RUN = Path('D:/he_m2_source_region_shared_normalization_live_001')
HISTORICAL = V / 'm4_yanyite_dual_curved_region_native_001'
SEAL = V / 'm5_harness_recovery_001'
SHARED = SEAL / 'SHARED_DEPENDENCY.json'
PRIOR = V / 'm4_live_source_region_task_003'
DISPLAY = V / 'm4_source_region_display_001'
FORMAL = V / 'm4_dense_panel_sweep_formal_001'
RECOVERY = V / 'm5_joint_brief_source_projection_recovery_001'
DENSE = V / 'perf050_dense_micro_surface_holdout_recovery_001'
WORKER = V / 'm1_region_task_first_packet_consumption_holdout_recovery_001/harness/mcp_entry.py'
METADATA = V / 'm4_dense_sweep_integrated_native_pilot_001/harness/common.py'
GENERIC = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
CATALOGUE = V / 'm4_dense_sweep_integrated_native_startup_001/inputs/EVIDENCE_TOOLS_SCHEMA.json'
PRODUCT_SCHEMA = CATALOGUE.with_name('PRODUCT_SCHEMA.json')
ASSET = Path('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend')
ASSET_SHA256 = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
SLOTS = dict.fromkeys(('A', 'B'), ('P', 'formal'))
BINDINGS = {
    'A': V / 'm2_source_region_normalization_triangle_list_001/install/PRODUCT_RUN_BINDING.json',
    'B': V / 'm2_source_region_shared_normalization_001/install/PRODUCT_RUN_BINDING.json',
}
PRODUCTS = {
    'A': ('31e9b46a68e5f791df9a75a1bad11caa8a6e8410',
          '6aaa60003ebbb8d689b8d9858a74a247c6d4f0de13bacac0d5dcead019555d70',
          '4724ff9f97cd8eb108b38396fa5ea3a12c3daf0fa960dc62eedcfe10e8f34e14'),
    'B': ('ee385e9842b9ea413f9d63dea6b74e88c8a051da',
          'df09c607da2e1e1c17855474943ef536a0a8ecc145d92f409f7d8c72f1cd9eaa',
          'a3b46a29c4361318ab9adf7359951307717a8d0844fe53ed29e1ab39fc7eee63'),
}
LIMITS = {'Blender_start_attempts': 2, 'all_rasters': 2, 'consumer_tasks': 0,
          'tools_per_slot': 5, 'rasters_by_slot': dict.fromkeys(SLOTS, 1)}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def require(statement, reason):
    if not statement:
        raise ValueError(reason)


def asset_identity():
    asset = ASSET.resolve(strict=True)
    require(asset.stat().st_size == 3_415_766 and sha(asset) == ASSET_SHA256,
            'fixed_yanyite_original_changed')
    return asset, ASSET_SHA256


def binding_identity(label, path):
    require(label in SLOTS and path.resolve(strict=True) == BINDINGS[label].resolve(strict=True),
            'fixed_live_arm_binding_path_required')
    binding = read(path)
    keys = ('preparation_git', 'source_sha256', 'wheel_sha256')
    require(tuple(binding[k] for k in keys) == PRODUCTS[label] and len(binding['source_manifest']) == 143,
            'fixed_live_arm_product_identity_required')
    require(sha(binding['wheel_path']) == binding['wheel_sha256'], 'fixed_live_arm_wheel_changed')
    return binding


def retained_sources():
    """File dependencies that the caller pins with the live freeze."""
    return (Path(__file__), HERE/'mcp_entry.py', HERE/'meter.py', *BINDINGS.values(),
            METADATA, CATALOGUE, PRODUCT_SCHEMA, SHARED, GENERIC,
            GENERIC.with_name('wire_meter.py'), HISTORICAL/'runtime/runtime.py',
            HISTORICAL/'runtime/common.py', HISTORICAL/'runtime/closure.py',
            HISTORICAL/'native/frame_device.py', HISTORICAL/'native/bridge.py',
            FORMAL/'harness/common.py', FORMAL/'harness/runtime.py', FORMAL/'harness/closure.py',
            FORMAL/'harness/run_slot.py',
            FORMAL/'bridge.py', FORMAL/'frame_device.py', RECOVERY/'harness/runtime.py',
            DENSE/'harness/runtime.py', DENSE/'harness/bridge.py', SEAL/'harness/owned_runtime.py',
            WORKER, WORKER.with_name('runtime.py'), PRIOR/'harness/owned_runtime.py',
            PRIOR/'harness/mcp_entry.py', PRIOR/'harness/budget.py', PRIOR/'harness/frame_device.py',
            PRIOR/'harness/device_capture.py',
            PRIOR/'harness/reused/verified_bootstrap.py', PRIOR/'bridge.py', PRIOR/'thin_stdio.py',
            DISPLAY/'harness/reused/process_proof.py', DISPLAY/'harness/reused/stdio_checks.py',
            V/'m4_target_task_consumption_001/native_consumer_audit.py')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def owned_root(root, preflight):
    root = Path(root).resolve()
    expected = RUN.resolve()
    if preflight:
        require(root.is_relative_to(expected/'preflight'), 'registered_preflight_root_required')
    else:
        require(root == expected, 'registered_formal_root_required')
    return root


def assemble(root, label, binding_path):
    """Bind the retained Yanyite runtime module graph to this arm and no other."""
    binding = binding_identity(label, binding_path)
    sys.path[:0] = [str(HERE), binding['dependency_root'], read(SHARED)['dependency_root']]
    common = load('common', METADATA)
    common.HERE = common.NS = HERE
    common.EXTERNAL, common.ASSET, common.ASSET_SHA256 = root, ASSET, ASSET_SHA256
    common.SLOTS, common.ORDER, common.asset_identity = SLOTS, tuple(SLOTS), asset_identity
    common.SOURCE_SHA, common.PRODUCT_BINDING = binding['source_sha256'], binding_path
    common.CATALOGUE, common.PRODUCT_SCHEMA = CATALOGUE, PRODUCT_SCHEMA
    common.PRODUCT_GIT, common.WHEEL_SHA = binding['preparation_git'], binding['wheel_sha256']
    common.PRODUCT = {'commit': common.PRODUCT_GIT, 'source_sha256': common.SOURCE_SHA,
                      'wheel_sha256': common.WHEEL_SHA}
    common.SLOT_REQUESTS = dict.fromkeys(SLOTS, ())
    ledger = load('budget', PRIOR/'harness/budget.py')
    ledger.LIMITS = LIMITS
    return common, ledger, binding


class PreflightBoundary(Exception):
    """Admission was checked without reserving or starting real Blender."""


class PreflightBudget:
    def __init__(self, ledger):
        self.ledger = ledger
        self.root = ledger.root

    def reserve(self, kind, label, phase='formal', upper=1):
        require(kind == 'Blender_start' and SLOTS[label][1] == phase and upper == 1,
                'actual_live_start_admission_changed')
        counts = self.ledger.snapshot()['counts']
        require(not any(counts.values()), 'preflight_ledger_must_start_empty')
        raise PreflightBoundary()

    def snapshot(self):
        return self.ledger.snapshot()


class Slot:
    def __init__(self, root, label, binding_path, *, preflight=False, start_ns=None):
        self.root = owned_root(root, preflight)
        self.label, self.binding_path, self.preflight = label, Path(binding_path).resolve(), preflight
        self.folder = self.root/'slots'/label
        self.start_ns = time.perf_counter_ns() if start_ns is None else start_ns
        self.task_deadline = self.start_ns + 450_000_000_000
        self.owned_deadline = self.start_ns + 600_000_000_000
        self.runtime = self.initial = self.receipt = self.owner = self.image_client = None
        self._outcome = 'failed'
        self._errors = []

    def __enter__(self):
        self.common, ledger, self.binding = assemble(self.root, self.label, self.binding_path)
        self.folder.mkdir(parents=True, exist_ok=False)
        try:
            runtime = self.common.load_retained('_m2_live_runtime', HISTORICAL/'runtime/runtime.py')
            self.common.load_retained('bridge', HISTORICAL/'native/bridge.py')
            self.common.load_retained('frame_device', HISTORICAL/'native/frame_device.py')
            self.runtime = runtime.Runtime(self.folder, self.label, self.task_deadline, self.owned_deadline)
            require(type(self.runtime.budget) is ledger.Budget, 'actual_runtime_ledger_binding_changed')
            if self.preflight:
                self.runtime.budget = PreflightBudget(self.runtime.budget)
            try:
                self.runtime.start()
            except PreflightBoundary:
                require(self.preflight and not self.runtime.native_start_entered and self.runtime.native is None
                        and self.runtime.claim is None and not (self.folder/'native').exists(),
                        'preflight_crossed_Blender_start_boundary')
                self.runtime.native = SimpleNamespace(host='127.0.0.1', port=1)
                try:
                    self.runtime._start_public_mcp(self.binding_path, self.binding)
                    self.runtime.prepare_device(ASSET_SHA256)
                finally:
                    self.runtime.native = None
                self.common.save(self.folder/'PREFLIGHT_BOUNDARY.json', {
                    'preflight': True, 'actual_runtime_start_until_Budget_reserve': True,
                    'launch_callable': inspect.getsourcefile(type(self.runtime).launch_native),
                    'native_starts': 0, 'actual_production_stdio': True,
                    'budgets': self.runtime.budget.snapshot()['counts']})
            require((self.runtime.native is None) is self.preflight, 'owned_Blender_required_in_live_slot')
            self.product_tools = self.runtime.product_tools
            self.client = self.runtime.client
            self.device = self.runtime.device
        except BaseException as error:
            self._note('start', error)
            try:
                self.finish()
            except BaseException as cleanup:
                error.add_note(f'closure receipt issue: {cleanup!r}')
            raise
        return self

    def _note(self, stage, error):
        self._errors.append({'stage': stage, 'type': type(error).__name__, 'message': str(error)})

    def _capture(self, stage, action):
        try:
            return action()
        except BaseException as error:
            self._note(stage, error)
            return None

    def source(self, terminal=False):
        require(not self.preflight and self.runtime is not None and self.runtime.device is not None,
                'owned_live_source_required')
        if terminal:
            return self.runtime.device.export_terminal()
        self.initial = self.runtime.capture_initial()
        return Path(self.initial['path'])

    def observe(self, arguments):
        require(not self.preflight and arguments.get('query', {}).get('mode') == 'source_region',
                'only_live_source_region_business_dispatch')
        self.runtime.budget.admit_business(self.label, 'formal')
        response = self.runtime.public_request(arguments)
        return response, self.runtime.public_requests[-1]

    def read_images(self, ref):
        """Use the existing ordinary held MCP path only if direct delivery lacks a path."""
        require(not self.preflight and self.owner is None, 'at_most_one_optional_read_images')
        from bridge import Owner

        self.owner = Owner(self.runtime, {'label': self.label, 'group': 'P', 'phase': 'formal',
                           'worker_deadline_ns': self.task_deadline, 'output': str(self.folder/'owner')},
                           budget=self.runtime.budget)
        endpoint = self.owner.start(self.folder/'ENDPOINT.json')
        if isinstance(endpoint, dict):
            endpoint = self.folder/'ENDPOINT.json'
        exe = [sys.executable, '-IB', '-X', 'utf8', str(PRIOR/'thin_stdio.py'),
               '--endpoint', str(endpoint), '--audit', str(self.folder/'attachment_audit')]
        transport = self.common.load_retained('_m2_live_attachment_transport',
                                              DISPLAY/'harness/reused/stdio_checks.py')
        self.image_client = transport.StdioClient(
            exe, self.folder, self.folder/'attachment_stdio', self.task_deadline)
        request = {'jsonrpc': '2.0', 'id': 'image-read', 'method': 'tools/call',
                   'params': {'name': 'read_images', 'arguments': {'refs': [ref]}}}
        response = self.image_client.call(request)
        return response, self.image_client.records[-1]

    def finish(self):
        if self.receipt is not None:
            return self.receipt
        initial, terminal, closure, verification, independent, budget = self.initial, None, None, None, None, None
        attachment_close = self._capture('attachment_stdio_close', self.image_client.finish) if self.image_client else None
        owner_close = self._capture('attachment_owner_close', self.owner.close) if self.owner else None
        if attachment_close is not None and (not attachment_close.get('confirmed') or attachment_close.get('exit_code') != 0):
            self._note('attachment_stdio_close', ValueError('actual_attachment_stdio_close_failed'))
        if owner_close is not None and (not owner_close.get('confirmed') or owner_close.get('errors')
                                        or owner_close.get('transport_errors')):
            self._note('attachment_owner_close', ValueError('actual_attachment_owner_close_failed'))
        if self.runtime is not None:
            if not self.preflight and self.runtime.device is not None:
                terminal = self._capture('terminal', lambda: self.source(terminal=True))
            closure = self._capture('runtime_close', lambda: self.runtime.close(
                'failed' if self._errors else self._outcome))
            budget = self._capture('budget', self.runtime.budget.snapshot)
            if closure is not None:
                mcp = closure.get('public_MCP_close') or {}
                if mcp.get('confirmed') is not True or mcp.get('production_eof_and_exit_verified') is not True:
                    self._note('mcp_close', ValueError('actual_production_stdio_EOF_not_confirmed'))
                if self.runtime.native is not None:
                    checker = self.common.load_retained('_m2_live_closure', HISTORICAL/'runtime/closure.py')
                    verification = self._capture('closure_verification', lambda: checker.ready_closure(
                        closure, 'P', read(self.folder/'NATIVE_RUNTIME_PROOF.json')))
                    if verification and initial and terminal:
                        pair = retained_independent_pair()
                        independent = self._capture('initial_terminal_pair', lambda: pair(
                            self.folder, initial, terminal, ASSET_SHA256, verification['pid']))
                for row in closure['errors']:
                    if row not in self._errors:
                        self._errors.append(row)
        closed = time.perf_counter_ns()
        if closed >= self.owned_deadline:
            self._note('closure_deadline', TimeoutError('owned_absolute_deadline'))
        if not self.preflight and self._outcome == 'completed' and (not verification or not independent):
            self._note('required_readonly_receipts', ValueError('initial_or_final_readonly_proof_missing'))
        self.receipt = {'status': 'completed' if not self._errors and self._outcome == 'completed' else 'failed',
                        'label': self.label, 'preflight': self.preflight, 'started_ns': self.start_ns,
                        'closed_ns': closed, 'complete_slot_ns': closed-self.start_ns, 'errors': self._errors,
                        'initial_source': initial, 'terminal_source': terminal, 'runtime_close': closure,
                        'closure_verification': verification, 'independent_before_after': independent,
                        'budget': budget, 'attachment_stdio_close': attachment_close, 'owner_close': owner_close}
        self.common.save(self.folder/'HOST_RECEIPT.json', self.receipt)
        return self.receipt

    def __exit__(self, kind, error, traceback):
        if error is not None:
            self._note('caller', error)
        else:
            self._outcome = 'completed'
        try:
            self.finish()
        except BaseException as cleanup:
            if error is None:
                raise
            error.add_note(f'closure receipt issue: {cleanup!r}')


def retained_independent_pair():
    """Use the original independent before/after scorer without slot dispatch imports."""
    import ast

    source = FORMAL/'harness/run_slot.py'
    tree = ast.parse(source.read_bytes(), filename=str(source))
    pair = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'independent_pair')
    env = {'Path': Path, 'read': read, 'sha': sha}
    exec(compile(ast.Module(body=[pair], type_ignores=[]), str(source), 'exec'), env)
    return env['independent_pair']
