"""Exercise both installed MCP stdio paths over the retained P1 producer."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from statistics import median
import subprocess
import sys
from threading import Timer
from time import perf_counter_ns
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
RUN = Path('D:/he_perf050_dual_region_occlusion_transfer_001')
SLOT = RUN / 'slots/P1'
SOURCE = SLOT / 'product_full/call_004/SERVICE_RESULT.json'
TX = SLOT / 'mcp/rpc_07/TX.bin'
RX = TX.with_name('RX.bin')
ARCHIVE_SHA = 'a750e623fee4737c14eeef3552deb59ddfc2bc5cc70ebd4009606a58d2ebcf36'
BASE = V / 'm4_source_region_blocker_brief_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
REPLAY = V / 'm4_source_region_blocker_brief_001/checks/delivery.py'
ROWS = [['SCENE', 8, 1], ['TOP', 8, 0], ['LEFT', 8, 0], ['RIGHT', 8, 1],
        ['FRONT', 8, 1], ['BACK', 8, 0]]
ANNOTATIONS = ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope')
ORDER = ('A', 'B', 'B', 'A', 'A', 'B')
WARM = 18


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    data = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(data), 'sha256': sha256(data).hexdigest()}


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def worker(binding_path, notes):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root'], str(HERE)]
    from human_eye_plugin import active_observation_host, live_spatial_mcp, source_region
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.read_context import ReadContext
    from human_eye_plugin.runtime_identity import runtime_identity
    from prepared_replay import restore

    identity = runtime_identity()
    require(identity['source_kind'] == 'installed_distribution'
            and identity['source_sha256'] == binding['source_sha256']
            and all(Path(module.__file__).resolve().is_relative_to(Path(binding['install_root']).resolve())
                    for module in (live_spatial_mcp, source_region, active_observation_host)),
            'stdio_imported_the_wrong_installed_sources')
    original, request = read(SOURCE), read(TX)
    arguments = request['params']['arguments']

    def deny_raster(_view):
        raise ValueError('isolated_replay_must_not_rasterize')

    class RetainedService:
        _source_region_sample_directory = getattr(LiveSpatialService, '_source_region_sample_directory', None)
        _source_region_sample_path = getattr(LiveSpatialService, '_source_region_sample_path', None)
        _matching_source_region_producer = getattr(LiveSpatialService, '_matching_source_region_producer', None)
        _source_region_blocker_rows = getattr(LiveSpatialService, '_source_region_blocker_rows', None)

        def __init__(self):
            self.state_path = SLOT / 'product_state.json'
            self._read_context = ReadContext()
            self.calls, self.budget, self.audits = [], [], []
            self.closed = False
            started = perf_counter_ns()
            with self._read_context.lock:
                self.prepared = restore(source_region, active_observation_host, self._read_context, request, original)
            self.restore_ns = perf_counter_ns() - started

        def observe(self, _session, *, query, include_image, **_unused):
            require(query == arguments['query'] and include_image is True, 'retained_original_arguments_changed')
            with self._read_context.lock:
                if not self.calls:
                    self.calls.append('archived_cold_producer')
                    return deepcopy(original)
                self.calls.append('installed_same_generation_observation_hit')
                result = source_region.observe_region(self.prepared, None, include_image=True,
                                                      construction_callback=deny_raster)
                require(result['work']['raster_attempts'] == 0 and result['work']['frame_reuses'] == 1
                        and all(result[key] == original[key] for key in
                                ('frames', 'facts', 'view_attempts', 'constructed_frames', 'region_ref')),
                        'retained_observation_evidence_or_raster_work_changed')
            # These are outer service annotations, absent from its retained observation.
            result['binding'].update({key: original['binding'][key] for key in ANNOTATIONS if key in original['binding']})
            result['task_result'] = deepcopy(original['task_result'])
            result['session_id'] = original['session_id']
            return result

        def record_event(self, event, **data):
            if event == 'source_region_mcp_content':
                self.audits.append(data['image_delivery'])

        def _check_request_budget(self, stage, *, publication=False):
            self.budget.append([stage, publication])

        def close(self):
            self.closed = True

    service = RetainedService()
    encode = live_spatial_mcp.wire.encode_response
    publish = live_spatial_mcp.wire.write_encoded
    wire_encode_ns, wire_publish_ns = [], []

    def timed_encode(*args, **kwargs):
        started = perf_counter_ns()
        result = encode(*args, **kwargs)
        wire_encode_ns.append(perf_counter_ns() - started)
        return result

    def timed_publish(*args, **kwargs):
        started = perf_counter_ns()
        result = publish(*args, **kwargs)
        wire_publish_ns.append(perf_counter_ns() - started)
        return result

    live_spatial_mcp.wire.encode_response = timed_encode
    live_spatial_mcp.wire.write_encoded = timed_publish
    live_spatial_mcp._configure_utf8_stdio()
    live_spatial_mcp.run_stdio_mcp_server(service)
    count = len(service.calls)
    save(notes, {'source': identity['source_sha256'], 'closed': service.closed, 'fixture_restore_ns': service.restore_ns,
                 'calls': service.calls, 'budget': service.budget, 'audits': service.audits,
                 'wire_encode_ns_including_catalogue': wire_encode_ns,
                 'wire_publish_ns_including_catalogue': wire_publish_ns})
    require(service.closed and count >= 2 and len(service.audits) == count
            and len(wire_encode_ns) == len(wire_publish_ns) == count + 1
            and service.budget == [['before_task_publication', False], ['before_stdio_write', True]] * count,
            'actual_stdio_close_or_publication_checks_changed')


def packet(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode() + b'\n'


def requests(*, full=False):
    historical = read(TX)
    setup = packet({'jsonrpc': '2.0', 'id': 'catalogue', 'method': 'tools/list'})
    if full:
        historical['params']['arguments']['response_detail'] = 'full'
        return [setup, packet(historical), packet({**historical, 'id': 'full-hot'})]
    return [setup, TX.read_bytes().rstrip(b'\r\n') + b'\n',
            *(packet({**historical, 'id': f'warm-{index:02d}'}) for index in range(WARM))]


def replay(output, label, binding, payloads):
    notes = output / (label + '_AUDIT.json')
    argv = [sys.executable, '-IB', str(Path(__file__).resolve()), '--worker', str(binding), '--notes', str(notes)]
    sent, received, parent_ns = [], [], []
    with (output / (label + '_STDERR.bin')).open('xb') as errors:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)

        def close_overdue_worker():
            if process.poll() is None:
                process.kill()

        deadline = Timer(50, close_overdue_worker)
        deadline.start()
        try:
            for request in payloads:
                started = perf_counter_ns()
                process.stdin.write(request)
                process.stdin.flush()
                sent.append(request)
                line = process.stdout.readline()
                parent_ns.append(perf_counter_ns() - started)
                received.append(line)
                require(line and json.loads(line)['id'] == json.loads(request)['id'], 'stdio_correlation_failed/' + label)
            process.stdin.close()
            exit_code = process.wait(timeout=10)
            require(exit_code == 0 and not process.stdout.read(), 'installed_stdio_EOF_or_exit_failed/' + label)
        finally:
            deadline.cancel()
            close_overdue_worker()
            process.wait(timeout=10)
            process.stdin.close()
            process.stdout.close()
            (output / (label + '_TX.bin')).write_bytes(b''.join(sent))
            (output / (label + '_RX.bin')).write_bytes(b''.join(received))
            save(output / (label + '_PARENT_RTT.json'), parent_ns)
    require((output / (label + '_STDERR.bin')).stat().st_size == 0, 'unexpected_worker_stderr/' + label)
    audit = read(notes)
    for row, response in zip(audit['audits'], received[1:], strict=True):
        public = json.loads(response)['result']
        require(public['isError'] is False and row['native_blocks_constructed'] == 1 and row['PNG_bytes'] == 2458,
                'observed_MCP_delivery_audit_changed/' + label)
    return {'received': received, 'parent_ns': parent_ns[1:], 'audit': audit}


def proof(retained):
    frame, = read(SOURCE)['frames']
    png, npz = (Path(frame[key]) for key in ('image_path', 'arrays_path'))
    archive = RUN / 'ORIGINAL_RUNTIME.zip'
    owner = SLOT / 'owner/tool_04/RESPONSE.json'
    old_full = SLOT / 'mcp/rpc_04/RX.bin'
    paths = (TX, RX, SOURCE, png, npz, owner, old_full, SLOT / 'SLOT_RESULT.json')
    require(pin(archive)['sha256'] == ARCHIVE_SHA, 'historical_archive_changed')
    with ZipFile(archive) as sealed:
        require(all(path.read_bytes() == sealed.read(path.relative_to(RUN).as_posix()) for path in paths),
                'historical_archive_member_changed')
    historic = read(RX)['result']
    raw = png.read_bytes()
    require(historic == read(owner)['result'] and read(SLOT / 'SLOT_RESULT.json')['closure_verification']['passed']
            and base64.b64decode(historic['content'][1]['data'], validate=True) == raw
            and frame['image_sha256'] == sha256(raw).hexdigest()
            and len(historic['content'][0]['text'].encode()) == 7360, 'original_MCP_packet_changed')
    retained.extend(pin(path) for path in (*paths, archive))
    return historic, raw


def paired_costs(blocks, pair_order, summarizer):
    def samples(block, key):
        audit = block['audit']
        if key == 'content_encoder':
            return [row['elapsed_ns'] for row in audit['audits']]
        if key == 'parent_stdio_RTT':
            return block['parent_ns']
        return audit[key + '_including_catalogue'][1:]

    by_arm, deltas = {}, {}
    for key in ('content_encoder', 'wire_encode_ns', 'wire_publish_ns', 'parent_stdio_RTT'):
        by_arm[key] = {}
        for arm, runs in blocks.items():
            bucket = [samples(run, key) for run in runs]
            by_arm[key][arm] = {
                'cold': summarizer([row[0] for row in bucket]),
                'warm': summarizer([item for row in bucket for item in row[1:]]),
            }
        pairs = [(samples(a, key), samples(b, key)) for a, b in pair_order]
        cold = [b[0] - a[0] for a, b in pairs]
        warm = [median(b[1:]) - median(a[1:]) for a, b in pairs]
        deltas[key] = {'cold_B_minus_A_ns': cold, 'warm_block_median_B_minus_A_ns': warm,
                       'cold_paired_median_delta_ns': median(cold), 'warm_paired_median_delta_ns': median(warm)}
    return by_arm, deltas


def run(output):
    prior = run_path(str(REPLAY))
    pins = []
    historical, original_png = proof(pins)
    image_sha = sha256(original_png).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'HISTORIC_TX.bin').write_bytes(TX.read_bytes())
    (output / 'HISTORIC_RX.bin').write_bytes(RX.read_bytes())
    (output / 'HISTORIC_SCENE.png').write_bytes(original_png)
    arms = {'A': BASE, 'B': CANDIDATE}
    blocks = {arm: [] for arm in arms}
    pairing = []
    for index, arm in enumerate(ORDER, 1):
        result = replay(output, f'{index}_{arm}', arms[arm], requests())
        blocks[arm].append(result)
        if index % 2 == 0:
            pairing.append((blocks['A'][-1], blocks['B'][-1]))
    full = {arm: replay(output, arm + '_full', binding, requests(full=True)) for arm, binding in arms.items()}
    for block in [*blocks['A'], *blocks['B'], *full.values()]:
        actual = json.loads(block['received'][0])['result']['tools']
        require(all(tool in actual for tool in read(CANDIDATE.with_name('TOOLS_SCHEMA.json')))
                and actual == json.loads(blocks['A'][0]['received'][0])['result']['tools'],
                'actual_installed_catalogue_changed')
    require(read(BASE.with_name('TOOLS_SCHEMA.json')) == read(CANDIDATE.with_name('TOOLS_SCHEMA.json')),
            'install_scoped_catalogue_changed')
    for runs in blocks.values():
        require(all(r['received'] == runs[0]['received'] for r in runs), 'same_arm_replay_bytes_changed')

    records = {}
    for index, phase in enumerate(('cold', 'hot'), 1):
        wire_a, wire_b = (blocks[arm][0]['received'][index] for arm in arms)
        a, b = json.loads(wire_a), json.loads(wire_b)
        br = b['result']
        content = br['content']
        body = json.loads(content[0]['text'])
        table = body.pop('blocker_evidence')
        require(wire_a == wire_b and table['rows'] == ROWS
                and table['columns'] == ['view_name', 'blocker_object_index', 'source_triangle_index']
                and body['image_scope']['objects'][8]['object_name'] == 'Obj_03'
                and content[1:] == historical['content'][1:]
                and body['visibility']['geometry_status'] == 'positive_area_occlusion'
                and body['visibility']['complete_witness'] is None
                and body['visibility']['selected_surface_pixels'] == 0
                and body['image_delivery']['frame_reuses'] == (phase == 'hot')
                and body['image_delivery']['new_raster_attempts'] == (phase == 'cold'),
                'positive_blocker_producer_replay_changed/' + phase)
        if phase == 'cold':
            require(body == json.loads(historical['content'][0]['text']), 'original_source_region_facts_changed')
        full_a, full_b = (full[arm]['received'][index] for arm in arms)
        require(full_a == full_b, 'explicit_full_retained_wire_changed/' + phase)
        records[phase] = {'A_text_bytes': len(a['result']['content'][0]['text'].encode()),
                          'B_text_bytes': len(content[0]['text'].encode()),
                          'A_wire_bytes_including_EOL': len(wire_a), 'B_wire_bytes_including_EOL': len(wire_b),
                          'explicit_full_wire_bytes_including_EOL': len(full_b),
                          'B_fixed_CLI_stages': prior['profile'](b, image_sha)}
    for arm in arms:
        reference = json.loads(blocks[arm][0]['received'][2])['result']
        require(all(json.loads(raw)['result'] == reference for block in blocks[arm] for raw in block['received'][2:]),
                'warm_retained_evidence_or_counters_changed')
    costs, deltas = paired_costs(blocks, pairing, prior['summary'])
    result = {'passed': True, 'qualified_cold_hot': 2, 'fixed_CLI_combinations': 12,
              'legacy_replies_retained': pins, 'candidate_tool_list_unchanged': True,
              'product_installs': {arm: pin(binding) for arm, binding in arms.items()},
              'original_PNG_SHA': image_sha, 'rows': ROWS, 'records': records,
              'replay_order': list(ORDER), 'warm_per_block': WARM, 'costs': costs, 'paired_deltas': deltas,
              'method': 'Archived cold producer; hot uses installed retained observation. Fixture reconstruction and '
                        'initial catalogue are outside timing. Wire samples are instrumented symmetrically.',
              'new_Blender': 0, 'new_models': 0, 'new_rasters': 0}
    save(output / 'DELIVERY.json', result)
    print(json.dumps({'quality': '2/2', 'CLI': '12/12', 'costs': costs, 'paired_deltas': deltas}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--notes', type=Path)
    cli = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_interpreter_I_B')
    if cli.worker:
        worker(cli.worker, cli.notes)
    else:
        run(cli.output)
