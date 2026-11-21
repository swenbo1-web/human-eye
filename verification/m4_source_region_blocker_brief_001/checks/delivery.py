"""Replay the archived producer through both fixed installs and the CLI budget."""

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
from time import perf_counter_ns
from types import SimpleNamespace
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
RUN = Path('D:/he_perf050_dual_region_occlusion_transfer_001')
SLOT = RUN / 'slots/P1'
SOURCE = SLOT / 'product_full/call_004/SERVICE_RESULT.json'
TX = SLOT / 'mcp/rpc_07/TX.bin'
RX = TX.with_name('RX.bin')
ARCHIVE_SHA = 'a750e623fee4737c14eeef3552deb59ddfc2bc5cc70ebd4009606a58d2ebcf36'
BASE = V / 'm1_source_region_default_measurement_entry_001/install/PRODUCT_RUN_BINDING.json'
CANDIDATE = NS / 'install/PRODUCT_RUN_BINDING.json'
ROWS = [[view, 8, face] for view, face in zip(
    ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK'), (1, 0, 0, 1, 1, 0), strict=True)]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_bytes())


def digest(raw):
    return sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest(raw)}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def worker(binding_path, notes):
    binding = read(binding_path)
    sys.path[:0] = [binding['install_root'], binding['dependency_root']]
    from human_eye_plugin import live_spatial_mcp as mcp, source_region
    from human_eye_plugin.runtime_identity import runtime_identity

    require(runtime_identity()['source_sha256'] == binding['source_sha256']
            and Path(mcp.__file__).is_relative_to(binding['install_root']), 'installed_product_changed')
    original = read(SOURCE)
    args = read(TX)['params']['arguments']

    class RetainedProducerReplay:
        def __init__(self):
            self.audits = []
            self.budget = []
            self.calls = []
            self.closed = False
            observation = {key: deepcopy(value) for key, value in original.items()
                           if key not in ('task_result', 'session_id', 'request_trace')}
            for key in ('runtime_source_sha256', 'source_status', 'disk_status', 'source_check_scope'):
                observation['binding'].pop(key, None)
            self.prepared = SimpleNamespace(observation=observation)

        def observe(self, _session, *, query, include_image, **_kwargs):
            require(query == args['query'] and include_image is True, 'original_query_changed')
            if not self.calls:
                self.calls.append('archived_cold')
                return deepcopy(original)
            self.calls.append('installed_retained_hit')
            value = source_region.observe_region(self.prepared, None, include_image=True)
            require(value['work']['frame_reuses'] == 1 and value['work']['raster_attempts'] == 0
                    and value['frames'] == original['frames']
                    and value['facts'] == original['facts']
                    and value['view_attempts'] == original['view_attempts']
                    and value['constructed_frames'] == original['constructed_frames'], 'warm_work_or_evidence_changed')
            return {**value, **{key: deepcopy(original[key]) for key in ('binding', 'task_result', 'session_id')}}

        def _check_request_budget(self, phase, *, publication=False):
            self.budget.append([phase, publication])

        def record_event(self, event, **data):
            if event == 'source_region_mcp_content':
                self.audits.append(data['image_delivery'])

        def close(self):
            self.closed = True

    service = RetainedProducerReplay()
    mcp._configure_utf8_stdio()
    mcp.run_stdio_mcp_server(service)
    save(notes, {'source': binding['source_sha256'], 'closed': service.closed,
                 'calls': service.calls, 'budget': service.budget, 'audits': service.audits})
    require(service.closed and len(service.calls) >= 2 and len(service.audits) == len(service.calls)
            and service.budget == [['before_task_publication', False], ['before_stdio_write', True]] * len(service.calls),
            'stdio_EOF_notification_or_budget_changed')


def profile(reply, image_sha):
    helpers, policy = run_path(str(V / 'm4_cross_scale_live_qualification_001/checks/delivery.py'))['budget_helpers']()
    require((policy['MCP_bytes'], policy['history_approximate_tokens']) == (12000, 3000), 'CLI_budget_changed')
    full = reply['result']['content'][0]['text']
    records = []
    for secs, expected_head in zip(('0.0000', '10.0000', '100.0000'), (33, 34, 35), strict=True):
        items = helpers['model_items'](reply['result'], secs)
        head = len(items[0]['text'].encode())
        require(head == expected_head, 'CLI_head_size_changed')
        tool = helpers['truncate_items'](items, 12000)
        history = helpers['truncate_items'](tool, 3000, token_mode=True)
        for stage, retained in (('tool', tool), ('history', history)):
            texts = [item['text'] for item in retained if item['type'] == 'input_text']
            images = [digest(base64.b64decode(item['image_url'].split(',', 1)[1], validate=True))
                      for item in retained if item['type'] == 'input_image']
            require(texts == [items[0]['text'], full] and images == [image_sha], 'CLI_body_or_PNG_changed')
            records.append({'head_bytes': head, 'stage': stage, 'text_bytes': len(full.encode()),
                            'text_sha256': digest(full.encode()), 'image_sha256': image_sha})
    return records


def replay(output, label, binding, requests):
    notes = output / f'{label}_AUDIT.json'
    argv = [sys.executable, '-IB', str(Path(__file__).resolve()), '--worker', str(binding), '--notes', str(notes)]
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    received, wall = [], []
    try:
        for request in requests:
            start = perf_counter_ns()
            process.stdin.write(request)
            process.stdin.flush()
            line = process.stdout.readline()
            wall.append(perf_counter_ns() - start)
            require(line and json.loads(line)['id'] == json.loads(request)['id'], 'RPC_correlation_changed')
            received.append(line)
        process.stdin.close()
        returncode = process.wait(timeout=45)
        stderr, unexpected = process.stderr.read(), process.stdout.read()
        (output / f'{label}_TX.bin').write_bytes(b''.join(requests))
        (output / f'{label}_RX.bin').write_bytes(b''.join(received))
        (output / f'{label}_STDERR.bin').write_bytes(stderr)
        require(returncode == 0 and not stderr and not unexpected,
                f'installed_stdio_process_or_EOF_failed/{returncode}/{stderr.decode(errors="replace")}')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
    audit = read(notes)
    for row, raw in zip(audit['audits'], received[1:], strict=True):
        public = json.loads(raw)['result']
        require(public['isError'] is False and row['native_blocks_constructed'] == 1
                and row['PNG_bytes'] == 2458 and row['projection_status'] == 'brief', 'native_audit_changed')
    return received, wall[1:], audit['audits']


def summary(values):
    ordered = sorted(values)
    p95 = ordered[(len(ordered) * 95 + 99) // 100 - 1]
    return {'samples': len(ordered), 'median_ns': median(ordered), 'p95_ns': p95}


def run(output):
    frame, = read(SOURCE)['frames']
    png, npz = (Path(frame[key]) for key in ('image_path', 'arrays_path'))
    archive = RUN / 'ORIGINAL_RUNTIME.zip'
    owner = SLOT / 'owner/tool_04/RESPONSE.json'
    old_full = SLOT / 'mcp/rpc_04/RX.bin'
    files = (TX, RX, SOURCE, png, npz, owner, old_full, SLOT/'SLOT_RESULT.json')
    require(pin(archive)['sha256'] == ARCHIVE_SHA, 'historical_archive_changed')
    with ZipFile(archive) as original:
        require(all(path.read_bytes() == original.read(path.relative_to(RUN).as_posix()) for path in files),
                'historical_archive_member_changed')
    historical = read(RX)['result']
    raw_png = png.read_bytes()
    require(read(owner)['result'] == historical and read(SLOT/'SLOT_RESULT.json')['closure_verification']['passed']
            and base64.b64decode(historical['content'][1]['data'], validate=True) == raw_png
            and frame['image_sha256'] == digest(raw_png) and len(raw_png) == 2458
            and len(historical['content'][0]['text'].encode()) == 7360
            and len(read(old_full)['result']['content'][0]['text'].encode()) == 62318, 'historical_packet_changed')
    output.mkdir(parents=True, exist_ok=False)
    request = read(TX)
    requests = [json.dumps({'jsonrpc': '2.0', 'id': 'tools', 'method': 'tools/list'}).encode() + b'\n',
                TX.read_bytes().rstrip(b'\r\n') + b'\n']
    requests.extend(json.dumps({**request, 'id': f'warm-{index:02d}'}).encode() + b'\n' for index in range(12))
    (output / 'HISTORIC_TX.bin').write_bytes(TX.read_bytes())
    (output / 'HISTORIC_RX.bin').write_bytes(RX.read_bytes())
    (output / 'HISTORIC_SCENE.png').write_bytes(raw_png)
    arms = {'A': BASE, 'B': CANDIDATE}
    blocks = {}
    for index, arm in enumerate(('A', 'B', 'B', 'A', 'A', 'B'), 1):
        blocks.setdefault(arm, []).append(replay(output, f'{index}_{arm}', arms[arm], requests))
    catalogues = [read(NS/'install/TOOLS_SCHEMA.json'), read(BASE.with_name('TOOLS_SCHEMA.json'))]
    require(catalogues[0] == catalogues[1], 'installed_tool_directory_changed')
    baseline_directory = json.loads(blocks['A'][0][0][0])['result']['tools']
    require(all(json.loads(raw[0])['result']['tools'] == baseline_directory
                for arm in blocks.values() for raw, _, _ in arm)
            and all(tool in baseline_directory for tool in catalogues[0]), 'actual_replay_tool_directory_changed')
    records = {}
    for call, label in enumerate(('cold', 'hot'), 1):
        a, b = (json.loads(blocks[arm][0][0][call]) for arm in ('A', 'B'))
        ar, br = (item['result'] for item in (a, b))
        base_text = ar['content'][0]['text']
        body = json.loads(br['content'][0]['text'])
        table = body.pop('blocker_evidence')
        require(table['columns'] == ['view_name', 'blocker_object_index', 'source_triangle_index']
                and table['rows'] == ROWS and body['image_scope']['objects'][8]['object_name'] == 'Obj_03'
                and json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(',', ':')) == base_text
                and ar['content'][1:] == br['content'][1:] == historical['content'][1:]
                and body['visibility']['geometry_status'] == 'positive_area_occlusion'
                and body['visibility']['selected_surface_pixels'] == 0
                and body['visibility']['complete_witness'] is None
                and body['image_delivery']['frame_reuses'] == (label == 'hot')
                and body['image_delivery']['new_raster_attempts'] == (label == 'cold'),
                'candidate_changed_other_evidence_or_measured_work')
        if label == 'cold':
            require(body == json.loads(historical['content'][0]['text']), 'baseline_historical_body_changed')
        records[label] = {'A_text_bytes': len(base_text.encode()),
                          'B_text_bytes': len(br['content'][0]['text'].encode()),
                          'A_wire_bytes_including_EOL': len(blocks['A'][0][0][call]),
                          'B_wire_bytes_including_EOL': len(blocks['B'][0][0][call]),
                          'B_fixed_CLI_stages': profile(b, digest(raw_png))}
    for arm in blocks.values():
        first_raw = arm[0][0]
        require(all(raw == first_raw for raw, _, _ in arm), 'repeated_replay_packets_changed')
    costs = {arm: {
        'cold_content_encoder': summary([rows[0]['elapsed_ns'] for _, _, rows in blocks[arm]]),
        'warm_content_encoder': summary([row['elapsed_ns'] for _, _, rows in blocks[arm] for row in rows[1:]]),
        'cold_parent_stdio_RTT': summary([wall[0] for _, wall, _ in blocks[arm]]),
        'warm_parent_stdio_RTT': summary([elapsed for _, wall, _ in blocks[arm] for elapsed in wall[1:]]),
    } for arm in arms}
    result = {'passed': True, 'legacy_replies_retained': [pin(path) for path in (*files, archive)],
              'candidate_tool_list_unchanged': True, 'arms': {arm: read(binding)['preparation_git'] for arm, binding in arms.items()},
              'original_PNG_SHA': digest(raw_png), 'rows': ROWS, 'records': records,
              'replay_order': ['A', 'B', 'B', 'A', 'A', 'B'], 'costs': costs,
              'new_Blender': 0, 'new_models': 0, 'new_rasters': 0}
    save(output/'DELIVERY.json', result)
    print(json.dumps({'quality': '2/2', 'CLI': '12/12', 'records': records, 'costs': costs}))


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
