"""Preflight the current consumer, Owner, and installed production handoff on sealed records."""

from functools import partial
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
BASE = V / 'm1_region_task_first_packet_projection_001'
OLD = V / 'perf050_dense_micro_surface_holdout_001'
sys.path[:0] = [str(NS/'harness'), str(HERE), str(BASE), str(NS/'consumer'), str(NS)]
from common import ASSET_SHA256, EXTERNAL, PRODUCT, PRODUCT_BINDING, SEAL, catalogue_for, read, save
import diagnostic
import launch


def offline_worker(root, label):
    launch.EXTERNAL = EXTERNAL
    return launch.worker(root, PRODUCT_BINDING, 'P3', label == 'QB', 30, ())


def cell(root, label):
    from bridge import Owner
    from frame_device import FrameDevice

    deadline = time.perf_counter_ns() + 90_000_000_000
    root.mkdir()
    process = launch.transport().StdioClient(
        [sys.executable, '-IB', '-X', 'utf8', str(Path(__file__).resolve()), '--worker', str(root/'worker'), label],
        root, root/'producer_stdio', deadline)
    owner = None
    try:
        init, catalogue = launch.hello(process)
        identity = init['result']['_meta']['human_eye']
        diagnostic.require(identity['source_sha256'] == PRODUCT['source_sha256'] and identity['production_mode'],
                           'preflight_actual_installed_production_identity')
        diagnostic.require(catalogue['result']['tools'] == read(catalogue_for(label)),
                           'preflight_actual_production_directory_changed')
        records = launch.fixtures('P3')

        class ArchiveRuntime:
            def __init__(self):
                self.folder = root.resolve()
                self.product_tools = catalogue['result']['tools']
                self.public_requests = []
                self.device = FrameDevice(runroot=root, asset_sha256=ASSET_SHA256, group='P', label=label,
                                          native_call=self.no_host, terminal_call=self.no_host, phase='qualification')
                self.buffers, self.cameras = self.device.buffers, self.device.cameras
                self.image_specification = self.device.image_specification
                originals = root / 'original_frames'
                originals.mkdir()
                for index, frame in enumerate(records['discovery']['producer']['frames']):
                    original = Path(frame['image_path'])
                    destination = (originals / f'{index+1:02}.png').resolve()
                    diagnostic.require(launch.pin(original)['sha256'] == frame['image_sha256'], 'sealed_preflight_PNG_changed')
                    destination.write_bytes(original.read_bytes())
                    self.device.by_ref[frame['image_ref']] = {
                        'ref': frame['image_ref'], 'scope_id': frame['scope_id'], 'view_name': frame['view_name'],
                        'frame_identity': frame['frame_identity'], 'PNG': str(destination), 'PNG_sha256': frame['image_sha256'],
                        'size_px': frame['pose']['size_px'], 'origin': 'product'}

            def no_host(self, *args, **kwargs):
                raise AssertionError('archived_preflight_would_have_touched_host')

            def public_request(self, arguments):
                ordinal = len(self.public_requests) + 1
                request = launch.rpc(f'preflight-product-{ordinal}', 'tools/call', name=diagnostic.TOOL, arguments=arguments)
                response = process.call(request)
                self.public_requests.append({'request': request, 'response': response, 'receipt': process.records[-1]})
                return response

        runtime = ArchiveRuntime()
        owner = Owner(runtime, {'label': label, 'group': 'P', 'phase': 'qualification',
                               'worker_deadline_ns': deadline, 'output': str(root/'owner')})
        endpoint = owner.start(root/'ENDPOINT.json')
        result = {'label': label, 'diagnostic_calls': []}
        cases = launch.requests('P3')
        plan = partial(diagnostic.run_calls, discover=cases['discover_full'], measure=cases['source_region_no_image'])
        diagnostic.run_diagnostic(root, endpoint, deadline, 'P', owner, result, plan=plan)
        discovery, short, measure = runtime.public_requests
        for record, index in zip((discovery, short, measure), (2, 4, 5), strict=True):
            folder = root/'client'/f'call_{index:02}'
            original = read(folder/'REQUEST.json')
            delivered = read(folder/'RESPONSE.json')
            diagnostic.require(record['request']['params'] == original['params']
                               and record['response']['result'] == delivered['result'],
                               'preflight_actual_producer_forwarding_changed')
        full = discovery['response']['result']
        brief = short['response']['result']
        diagnostic.require(full['content'][1:] == brief['content'][1:] and (full == brief) is (label == 'QB'),
                           'preflight_actual_selected_production_profile_wrong')
        captions = read(root/'client/call_03/RESPONSE.json')['result']['content']
        diagnostic.require(captions[1::2] == full['content'][1:] and len(captions) == 6,
                           'preflight_actual_same_name_original_PNGs_changed')
        save(root/'DIAGNOSTIC.json', result)
    finally:
        try:
            if owner is not None:
                closure = owner.close()
                save(root/'OWNER_CLOSE.json', closure)
                diagnostic.require(closure['confirmed'] and not closure['errors'] and not closure['transport_errors'],
                                   'preflight_owner_not_closed')
        finally:
            closed = process.finish()
            save(root/'PRODUCER_STOCK_CLOSE.json', closed)
            eof = read(root/'worker/EOF.json')
            diagnostic.require(closed['confirmed'] and closed['exit_code'] == 0 and closed['process_handle_closed']
                               and eof['closed'] and eof['host_attempts'] == eof['new_rasters'] == 0,
                               'preflight_production_process_not_closed')
    return {'product_calls': len(runtime.public_requests), 'consumer_calls': len(result['diagnostic_calls']),
            'actual_process_closed': True, 'original_image_refs': result['qualification_pending']['frames']}


def run(root):
    sys.path[:0] = [read(PRODUCT_BINDING)['dependency_root'], read(SEAL/'SHARED_DEPENDENCY.json')['dependency_root']]
    from consumer import driver

    root.mkdir(parents=True, exist_ok=False)
    cells = {label: cell(root/label, label) for label in ('QA', 'QB')}
    turn, adapter, metadata = driver.consumer_adapter()
    executable = adapter['CLI_path']
    version = subprocess.check_output([executable, '--version'], timeout=15).decode().strip()
    login = subprocess.run([executable, 'login', 'status'], capture_output=True, timeout=15, check=True)
    diagnostic.require(version == 'codex-cli 0.152.1' and (login.stdout + login.stderr).decode().strip() == 'Logged in using ChatGPT',
                       'registered_existing_CLI_login_changed')
    environment = turn.__globals__['safe_environment']({'OPENAI_API_KEY':'test', 'GOOGLE_API_KEY':'test',
                                                       'A_ACCESS_TOKEN':'test', 'CODEX_THREAD_ID':'test', 'Keep':'sample'})
    diagnostic.require(environment == {'Keep':'sample'}, 'alternative_API_credentials_or_thread_context_not_filtered')
    pins = {}

    def pin(path, digest=None, size=None):
        row = launch.pin(Path(path))
        diagnostic.require((digest is None or row['sha256'] == digest) and (size is None or row['bytes'] == size),
                           'preflight_dependency_changed/' + str(path))
        pins[row['path']] = row
        return row

    # Reuse the real public prompt/argv/exit check with a local stdin-only process.
    sys.modules['driver'] = driver
    retained = run_path(str(OLD/'consumer/preflight.py'))
    with patch.object(driver, 'DENSE', V/'m4_dense_panel_sweep_formal_001', create=True):
        pilot = run_path(str(V/'perf050_readonly_product_pilot_001/consumer/preflight.py'))
    local = {label: retained['local_exit'](label, root/f'{label}_exit_probe', turn, adapter, metadata, pilot['normalize'], pin)
             for label in ('A1', 'B1')}
    for row in adapter['execution_sources']:
        pin(row['path'], row['sha256'], row['bytes'])
    pin(executable, adapter['CLI_sha256'])
    pin(adapter['Python_path'], adapter['Python_sha256'])
    pin(driver.PROMPT, driver.PROMPT_SHA)
    for source in (BASE/'launch.py', OLD/'consumer/preflight.py', V/'perf050_readonly_product_pilot_001/consumer/preflight.py'):
        pin(source)
    for case in launch.fixtures('P3').values():
        for row in case['pins']:
            pin(row['path'], row['sha256'], row['bytes'])
    receipt = {'passed':True, 'scope':'new Owner and thin stdio with archived producer at actual installed production main',
               'original_shared_prompt_sha256':driver.PROMPT_SHA, 'CLI':version, 'local_exit':local, 'cells':cells,
               'provider_model_starts':0, 'Blender_starts':0, 'new_rasters':0, 'source_pins':list(pins.values())}
    save(NS/'qualification/PREFLIGHT.json', receipt)


if __name__ == '__main__':
    diagnostic.require(sys.flags.isolated and sys.dont_write_bytecode, 'fixed_isolated_interpreter_required')
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        raise SystemExit(offline_worker(Path(sys.argv[2]), sys.argv[3]))
    run(EXTERNAL/'offline_preflight')
