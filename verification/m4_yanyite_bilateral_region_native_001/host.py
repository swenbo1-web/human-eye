"""Bind the retained owned Blender, production MCP, and fresh CLI to this pair."""

import ast
import inspect
import json
from pathlib import Path
import subprocess
import sys
import time
import tomllib
from types import ModuleType, SimpleNamespace


HERE = Path(__file__).resolve().parent
V = HERE.parent
OLD = V/'m4_yanyite_dual_curved_region_native_001'
LIVE_M2 = V/'m2_source_region_shared_normalization_live_001'
WORKER = V/'m1_region_task_first_packet_consumption_holdout_recovery_001/harness/mcp_entry.py'
RUN = Path('D:/he_m4_yanyite_bilateral_region_native_001').resolve()
ASSET = Path('D:/codex data/2026-10-02/fps-blender-models/Yanyite/outputs/Yanyite_Appearance.blend')
ASSET_SHA256 = '614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d'
BLENDER = Path('D:/Tools/blender5.2/blender.exe')
PRODUCT_BINDING = V/'m2_resident_capture_direct_delta_001/install/PRODUCT_RUN_BINDING.json'
PRODUCT = {'commit': '4104add44251b03a1eafc5af69502aa2575b632c',
           'source_sha256': '5445ad313f43c2ed3e75c3efafa7e9982e03e8ef08d78374b65ddeae05a32fc9',
           'wheel_sha256': '40a3aab846f9213eeb536f8828bc20ef42f5ba09f2430a2438baad2275882807'}
SLOTS = {'N1': ('N', 'formal'), 'P1': ('P', 'formal')}
PROMPT = HERE/'inputs/PROMPT.txt'
CLI = Path('C:/Users/Administrator/.codex/packages/standalone/releases/0.152.1-x86_64-pc-windows-msvc/bin/codex.exe')
CLI_SHA = '01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6'
PYTHON_SHA = '50f885251e42eb8cd1fbf5d4fbcc01efdbe8b9f4d4379e16664d4d0f3d4a9869'
PLAN = 'f6f80b34c3034f4b22368b4318e98e4f49f1eea5:docs/M4_YANYITE_BILATERAL_REGION_NATIVE_001_PLAN.md'
CONSUMER_DRIVER = V/'perf050_readonly_product_pilot_001/consumer/driver.py'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    from hashlib import file_digest

    with Path(path).open('rb') as source:
        return file_digest(source, 'sha256').hexdigest()


def load(name, path, source=None):
    # These retained harness modules are scripts. Import under a private name or
    # the exact alias required by the original entry, with bytecode disabled.
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_bytes() if source is None else source, str(path), 'exec'), vars(module))
    return module


def owned_root(root, preflight):
    root = Path(root).resolve(strict=True)
    require(root.is_relative_to(RUN/'preflight') if preflight else root == RUN,
            'current_pair_run_root_required')
    return root


def fixed_binding(path=PRODUCT_BINDING):
    require(Path(path).resolve(strict=True) == PRODUCT_BINDING.resolve(strict=True),
            'only_the_fixed_isolated_product_binding_is_admitted')
    bind = read(path)
    require({'commit': bind['preparation_git'], 'source_sha256': bind['source_sha256'],
             'wheel_sha256': bind['wheel_sha256']} == PRODUCT and len(bind['source_manifest']) == 143
            and sha(bind['wheel_path']) == PRODUCT['wheel_sha256'], 'fixed_candidate_or_wheel_changed')
    return bind


def assemble(root, label, binding_path=PRODUCT_BINDING):
    """Set up the exact aliases used by the retained parent or hosted worker."""
    root = Path(root).resolve()
    require(label in SLOTS and (root == RUN or root.is_relative_to(RUN/'preflight')),
            'current_pair_slot_required')
    bind = fixed_binding(binding_path)
    common = load('common', OLD/'runtime/common.py')
    common.HERE = common.NS = HERE
    common.NATIVE = OLD/'native'
    common.EXTERNAL, common.PLAN = root, PLAN
    common.SLOTS, common.ORDER = SLOTS, tuple(SLOTS)
    common.SLOT_REQUESTS = dict.fromkeys(SLOTS, ())
    common.QUALIFICATION = ()
    common.PRODUCT_BINDING, common.PRODUCT_GIT = PRODUCT_BINDING, PRODUCT['commit']
    common.SOURCE_SHA, common.WHEEL_SHA = PRODUCT['source_sha256'], PRODUCT['wheel_sha256']
    common.PRODUCT = PRODUCT
    common.add_paths()
    ledger = common.load_retained('budget', OLD/'runtime/budget.py')
    limits = {'Blender_start_attempts': 2, 'all_rasters': 24, 'consumer_tasks': 2, 'tools_per_slot': 12,
              'rasters_by_slot': dict.fromkeys(SLOTS, 12)}
    ledger.LIMITS = ledger.previous.LIMITS = ledger.previous._ledger.LIMITS = limits
    return common, ledger, bind


def consumer_module():
    source = CONSUMER_DRIVER.read_text(encoding='utf8')
    for before, after in (
        ("HARNESS = NS / 'harness'", f'HARNESS = Path({str(OLD/"native")!r})'),
        ("THIN = HERE / 'thin_stdio.py'", f'THIN = Path({str(HERE/"thin_stdio.py")!r})'),
        ("PROMPT = NS / 'inputs/PROMPT.txt'", f'PROMPT = Path({str(PROMPT)!r})'),
        ("'PERF050-READONLY-PRODUCT-PILOT-001-'", "'M4-YANYITE-BILATERAL-REGION-NATIVE-001-'"),
    ):
        require(source.count(before) == 1, 'retained_consumer_anchor_changed')
        source = source.replace(before, after)
    original_path = sys.path[:]
    try:
        return load('consumer', CONSUMER_DRIVER, source)
    finally:
        sys.path[:] = original_path


def runtime_graph(root, label):
    common, _, bind = assemble(root, label)
    runtime = common.load_retained('runtime', OLD/'runtime/runtime.py')
    common.load_retained('frame_device', OLD/'native/frame_device.py')
    bridge = common.load_retained('bridge', OLD/'native/bridge.py')
    common.load_retained('closure', OLD/'runtime/closure.py')
    return common, runtime, bridge, consumer_module(), bind


def prepared_runner(common, validate_admission):
    """Reuse the actual slot, with this batch's admission and catalogue files."""
    admission = ModuleType('admission')
    admission.validate_admission = validate_admission
    sys.modules['admission'] = admission
    source = common.FORMAL/'harness/run_slot.py'
    text = source.read_text(encoding='utf8')
    before = "read(PRODUCT_BINDING.parent / 'TOOLS_SCHEMA.json')"
    require(text.count(before) == 1, 'retained_slot_catalogue_anchor_changed')
    text = text.replace(before, 'read(catalogue_for(label))')
    runner = common.load_retained('_bilateral_owned_formal_runner', source)
    require(runner.validate_admission is validate_admission, 'actual_slot_has_wrong_admission')
    parsed = ast.parse(text, filename=str(source))
    run, = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == 'run']
    env = dict(vars(runner), catalogue_for=common.catalogue_for)
    exec(compile(ast.Module(body=[run], type_ignores=[]), str(source), 'exec'), env)
    return env['run']


def run_slot(label, validate_admission):
    require(sys.flags.isolated and sys.dont_write_bytecode and sha(sys.executable) == PYTHON_SHA,
            'fixed_isolated_runtime_required')
    common, _, _, _, _ = runtime_graph(RUN, label)
    return prepared_runner(common, validate_admission)(label)


class PreflightBoundary(BaseException):
    """Stop immediately before the real Blender startup budget reservation."""


class Gate:
    def __init__(self, budget, label):
        self.delegate, self.label, self.root = budget, label, budget.root
        self.reached = False

    def reserve(self, kind, label, phase='formal', upper=1):
        if kind == 'Blender_start':
            counts = self.delegate.snapshot()['counts']
            require(label == self.label and phase == 'formal' and upper == 1 and not self.reached and
                    not any(counts[key] for key in ('Blender_start_attempts', 'consumer_admissions', 'all_raster_upper')),
                    'wrong_Blender_preflight_boundary')
            self.reached = True
            raise PreflightBoundary()
        require(kind == 'business_tool', 'preflight_cannot_admit_consumers_or_rasters')
        return self.delegate.reserve(kind, label, phase, upper)

    def snapshot(self):
        return self.delegate.snapshot()


def _preflight_arm(output, label):
    """Drive one fresh process through actual host ingress and closure."""
    output = Path(output).resolve()
    root = RUN/'preflight/entry_v2'/label
    require(label in SLOTS and output == root/'ARM.json' and not (RUN/'slots').exists() and not output.exists() and
            sha(CLI) == CLI_SHA and sha(sys.executable) == PYTHON_SHA,
            'real_no_Blender_startup_preflight_required')
    root.mkdir(parents=True, exist_ok=False)
    arms = {}
    paths = set(retained_sources())
    group, phase = SLOTS[label]
    common, module, bridge, consumer, bind = runtime_graph(root, label)
    folder = root/'slots'/label
    folder.mkdir(parents=True, exist_ok=False)
    # Prepare the same cold formal entry used for the live pair. This
    # callback can never validate a real admission from the private root.
    def reject_live(*_):
        raise ValueError('dry_startup_cannot_admit_formal_Blender')

    runner = prepared_runner(common, reject_live)
    require(runner.__globals__['EXTERNAL'] == root and runner.__globals__['SLOTS'] is SLOTS,
            'cold_formal_runner_namespace_or_slot_table_changed')
    deadline = time.perf_counter_ns()+120_000_000_000
    worker = module.Runtime(folder, label, deadline, deadline+30_000_000_000)
    worker.budget = Gate(worker.budget, label)
    owner = wire = None
    try:
        try:
            worker.start()
        except PreflightBoundary:
            require(worker.budget.reached and not worker.native_start_entered and worker.native is None
                    and worker.claim is None and not (folder/'native').exists(),
                    'preflight_crossed_the_owned_Blender_launch_boundary')
        else:
            raise ValueError('actual_runtime_start_did_not_reach_Blender_reserve')
        if group == 'P':
            worker.native = SimpleNamespace(host='127.0.0.1', port=1)
            try:
                worker._start_public_mcp(PRODUCT_BINDING, bind)
            finally:
                worker.native = None
        worker.prepare_device(ASSET_SHA256)
        owner = bridge.Owner(worker, {'label': label, 'group': group, 'phase': phase,
                             'worker_deadline_ns': deadline, 'output': str(folder/'owner')}, budget=worker.budget)
        endpoint = owner.start(folder/'ENDPOINT.json')
        wire = module.transport.StdioClient([sys.executable, '-IB', '-X', 'utf8', str(HERE/'thin_stdio.py'),
                '--endpoint', str(endpoint), '--audit', str(folder/'attachments')],
                folder, folder/'ingress_wire', deadline)
        wire.call({'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'yanyite-bilateral-ingress', 'version': '001'}}})
        wire.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        tools = wire.call({'jsonrpc': '2.0', 'id': 'list', 'method': 'tools/list'})['result']['tools']
        require(tools == owner.tools and [t for t in tools if t['name'] != bridge.PRODUCT_TOOL] == bridge.TOOLS
                and len(tools) == len(bridge.TOOLS)+(group == 'P'), 'actual_ordinary_and_product_catalogue_changed')

        def call(ident, tool, arguments):
            return wire.call({'jsonrpc': '2.0', 'id': ident, 'method': 'tools/call',
                              'params': {'name': tool, 'arguments': arguments}})

        first = call('session-set', 'execute_python', {'code': 'import numpy as np\nimport shapely\ns=np.arange(9)\nprint(int(s.sum()))'})
        require(json.loads(first['result']['content'][0]['text'])['stdout'].strip() == '36', 'ordinary_shared_calculation_failed')
        denied = call('invalid-observe', bridge.PRODUCT_TOOL, {'include_image': 'bad-contract'})
        require(denied['result']['isError'] is True and len(worker.public_requests) == (group == 'P'),
                'ordinary_rejection_or_product_validation_misrouted')
        after = call('session-get', 'execute_python', {'code': 'print(int(s[2]+s[-1]))'})
        require(json.loads(after['result']['content'][0]['text'])['stdout'].strip() == '10', 'persistent_session_did_not_recover')
        turn, cli, _ = consumer.consumer_adapter()
        require(consumer.PROMPT == PROMPT and consumer.THIN == HERE/'thin_stdio.py'
                and (cli['CLI_version'], cli['model'], cli['reasoning_effort'], cli['service_tier'],
                     cli['completed_CLI_tool_limit']) == ('0.152.1', 'gpt-6.1-sol', 'medium', 'default', 12),
                'retained_real_CLI_entry_configuration_changed')
        cell = folder/'DRY_CLI_CELL.json'
        common.save(cell, {'endpoint': str(endpoint), 'group': group, 'audit_dir': str(folder/'owner')})
        work = folder/'workspace'
        work.mkdir()
        argv = turn.__globals__['initial_argv'](sys.executable, cell, work, folder/'dry_final.txt', group)
        config, = [arg for arg in argv if arg.startswith('mcp_servers.arm_engine=')]
        mcp = tomllib.loads(config)['mcp_servers']['arm_engine']
        require(Path(argv[0]) == CLI and '--ephemeral' in argv and 'gpt-6.1-sol' in argv
                and Path(mcp['cwd']) == work and mcp['args'][:4] == ['-I', '-B', '-X', 'utf8']
                and Path(mcp['args'][4]) == HERE/'thin_stdio.py'
                and set(mcp['tools']) == bridge.TOOL_NAMES[group],
                'actual_CLI_argv_not_bound_to_the_current_thin_entry')
        arms[label] = {'tools': tools, 'actual_product_handshake': group == 'P', 'closed': False,
                       'reached_before_Blender_reserve': True,
                       'launch_callable': inspect.getsourcefile(type(worker).launch_native),
                       'public_product_attempts': len(worker.public_requests),
                       'consumer_configuration': cli, 'render_attempts': 0}
        paths.update(Path(row['path']) for row in cli['execution_sources'])
    finally:
        try:
            if wire is not None:
                closed = wire.finish()
                require(closed['confirmed'] and closed['exit_code'] == 0, 'actual_thin_stdio_did_not_close')
        finally:
            try:
                if owner is not None:
                    require(owner.close()['confirmed'], 'actual_Owner_did_not_close')
            finally:
                actual = worker.close('preflight')
        if sys.exception() is None:
            require(not actual['errors'] and (group == 'N' or (
                    actual['public_MCP_close']['production_eof_and_exit_verified'] and
                    actual['public_MCP_exit']['confirmed'])), 'actual_mcp_did_not_close')
            counts = worker.budget.snapshot()['counts']
            require(not any(counts[key] for key in ('Blender_start_attempts', 'consumer_admissions', 'all_raster_upper')),
                    'preflight_started_Blender_model_or_raster')
    arms[label]['closed'] = True
    paths.update(Path(mod.__file__).resolve() for mod in tuple(sys.modules.values())
                 if getattr(mod, '__file__', None) and Path(mod.__file__).resolve().is_relative_to(V))
    receipt = {'passed': True, 'arms': arms, 'Blender': 0, 'models': 0, 'rasters': 0,
               'source_pins': [{'path': str(p.resolve()), 'bytes': p.stat().st_size, 'sha256': sha(p)}
                               for p in sorted(paths) if p.is_file()]}
    common.save(output, receipt)
    return receipt


def preflight(output):
    """Qualify both actual ingress paths in distinct cold interpreters."""
    output = Path(output).resolve()
    require(output == RUN/'preflight/RUNTIME_PREFLIGHT.json' and not output.exists() and
            not (RUN/'slots').exists(), 'current_dry_preflight_output_required')
    reports, pins = {}, {}
    for label in SLOTS:
        arm_path = RUN/'preflight/entry_v2'/label/'ARM.json'
        subprocess.run([sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()),
                        '--preflight-arm', label, str(arm_path)], cwd=V.parent, check=True, timeout=150)
        report = read(arm_path)
        arm = report['arms'][label]
        require(report['passed'] and set(report['arms']) == {label} and arm['closed'] and
                arm['reached_before_Blender_reserve'] and
                all(report[key] == 0 for key in ('Blender', 'models', 'rasters')),
                'actual_fresh_dry_arm_failed')
        reports[label] = arm
        for row in [*report['source_pins'], {'path': str(arm_path), 'bytes': arm_path.stat().st_size,
                                              'sha256': sha(arm_path)}]:
            existing = pins.setdefault(row['path'], row)
            require(existing == row, 'dry_fresh_sources_differ_between_arms')
    require([tool for tool in reports['P1']['tools'] if tool['name'] != 'human_eye_scene_observe'] ==
            reports['N1']['tools'], 'ordinary_catalogue_not_equivalent_across_fresh_processes')
    receipt = {'passed': True, 'arms': reports, 'Blender': 0, 'models': 0, 'rasters': 0,
               'source_pins': [pins[key] for key in sorted(pins)]}
    with output.open('x', encoding='utf8', newline='\n') as dst:
        json.dump(receipt, dst, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        dst.write('\n')
    return receipt


def retained_sources():
    formal = V/'m4_dense_panel_sweep_formal_001'
    prior = V/'m4_live_source_region_task_003'
    return (Path(__file__).resolve(), HERE/'mcp_entry.py', HERE/'thin_stdio.py', PRODUCT_BINDING, PROMPT,
            ASSET, BLENDER, CLI, Path(sys.executable), CONSUMER_DRIVER,
            *[OLD/'runtime'/name for name in ('common.py', 'budget.py', 'runtime.py', 'closure.py')],
            OLD/'native/bridge.py', OLD/'native/frame_device.py', WORKER, WORKER.with_name('runtime.py'),
            LIVE_M2/'mcp_entry.py', LIVE_M2/'meter.py', formal/'harness/run_slot.py', formal/'harness/runtime.py',
            formal/'harness/budget.py', formal/'harness/closure.py', formal/'frame_device.py',
            prior/'harness/device_capture.py',
            prior/'harness/owned_runtime.py', prior/'thin_stdio.py', prior/'harness/reused/verified_bootstrap.py',
            V/'m5_harness_recovery_001/SHARED_DEPENDENCY.json',
            V/'m4_global_local_qualification_001/harness/reused/owned_native.py',
            V/'m4_global_local_qualification_001/harness/reused/wire_meter.py',
            V/'m4_dense_sweep_integrated_native_startup_001/inputs/PRODUCT_SCHEMA.json',
            V/'m4_dense_sweep_integrated_native_startup_001/inputs/EVIDENCE_TOOLS_SCHEMA.json')


if __name__ == '__main__':
    require(sys.flags.isolated and sys.dont_write_bytecode and len(sys.argv) == 4 and
            sys.argv[1] == '--preflight-arm', 'only_fresh_isolated_arm_preflight_entry')
    sys.path.insert(0, str(HERE))
    _preflight_arm(Path(sys.argv[3]), sys.argv[2])
