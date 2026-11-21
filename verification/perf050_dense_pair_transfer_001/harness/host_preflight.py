"""Offline qualification of the fixed dense fixture and the actual shared host stack."""

import argparse
import base64
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import FunctionType, SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile


ASSET = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
IMAGES = {'TOP': '999cef092eb9e6f49735804bc65739784396776d7d1cd304e78b4c84bc89cf7d',
          'SCENE': '21ed0afc6e7a78b49364f5b888f1f0e03800616b4567f839411efaf5c820fa47'}
PRODUCT = '0e85052a0a4dec4ee42f8f9f62729a416b57445783224b303723b515ada0a147'
ARCHIVE = '31c389c0815507a2a71c01073e99f9f445758e0d4f3afb2409bd3672fecd0dbf'
P2_ARCHIVE = 'f675d00775e16397d1802339f9b994a44d39a5e34048dd678e3a952872e439ce'
TARGET, OTHER = 'M4_Far_00', 'M4_Focal'


def require(value, problem):
    if not value:
        raise ValueError(problem)


def sha(data):
    return sha256(data).hexdigest()


def file_pin(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': sha(data)}


def read(path):
    return json.loads(Path(path).read_bytes())


class Archive:
    def __init__(self, index, digest):
        self.index = Path(index)
        value = read(self.index)
        self.path = Path(value['archive']['path'])
        self.root = self.path.parent
        self.pins = [file_pin(self.index), file_pin(self.path)]
        require(self.pins[1]['sha256'] == value['archive']['sha256'] == digest, 'old_archive_not_same_bytes')
        self.zip = ZipFile(self.path)
        self.entries = {row['path']: row for row in value['files']}
        require(len(self.entries) == value['count'] == len(self.zip.namelist())
                and set(self.entries) == set(self.zip.namelist()), 'old_archive_member_roster_changed')

    def get(self, member):
        if isinstance(member, Path):
            member = member.relative_to(self.root).as_posix()
        data = self.zip.read(member)
        item = self.entries[member]
        path = self.root / member
        require(item['sha256'] == sha(data) and item['bytes'] == len(data) and path.read_bytes() == data,
                'old_raw_archive_and_disk_differ/' + member)
        self.pins.append(file_pin(path))
        return data

    def json(self, member):
        return json.loads(self.get(member))


def request(index, method, params=None):
    row = {'jsonrpc': '2.0', 'id': index, 'method': method}
    if params is not None:
        row['params'] = params
    return row


def call(index, name, arguments):
    return request(index, 'tools/call', {'name': name, 'arguments': arguments})


def read_origin(original):
    native = original.json('slots/N2/DEVICE_EVIDENCE.json')
    terminal = original.json('slots/N2/TERMINAL_SOURCE.json')
    initial = original.json('slots/N2/initial_capture/TERMINAL_SOURCE.json')
    result = original.json('slots/N2/SLOT_RESULT.json')
    require(result['closure_verification']['passed'] and result['independent_before_after']['passed']
            and terminal['objects'] == initial['objects'] and terminal['display_object_mask'] == initial['display_object_mask']
            and terminal['source']['asset_sha256'] == ASSET, 'old_dense_terminal_not_same_asset_and_display')
    selected, = (row for row in native['frames'] if row['view'] == 'TOP' and row['origin'] == 'common_native')
    row, = (src for src in native['sources'] if src['source_ref'] == selected['source_ref'])
    raw = original.json(Path(row['path']))
    source_by_id = {item['object_id']: item for item in terminal['objects']}
    for item in raw['objects']:
        final = source_by_id[item['object_id']]
        require(item['instance_id'] == final['instance_id'] and item['name'] == final['name']
                and item['visible_get'] is final['visible_get'] and item['triangles'] == final['evaluated']['triangles']
                and item['vertices'] == final['evaluated']['vertices_world_m'],
                'old_dense_native_read_not_same_ordered_evaluated_source')
    raw['source_ref'] = row['source_ref']
    require(len(raw['objects']) == 14 and sum(len(item['vertices']) for item in raw['objects']) == 3478
            and raw['source_face_offsets'][-1] == 6148, 'archived_dense_geometry_counts_changed')
    return raw, selected


def historical_delivery(original, label, attempt, png):
    slot = f'slots/{label}'
    archive = original.json(f'{slot}/consumer/BUSINESS_SOURCE_BINDING.json')
    contract, = (row for row in archive['result_contracts'] if row['attempt'] == attempt)
    receipt, = [member for member in original.entries if member.startswith(f'{slot}/consumer/attachments/bridge_')
                and member.endswith('/RECEIPT.json') and original.json(member).get('attempt') == attempt]
    rx_path = receipt.replace('/RECEIPT.json', '/RX.bin')
    tx_path = receipt.replace('/RECEIPT.json', '/TX.bin')
    tx, rx = original.get(tx_path), original.get(rx_path)
    request, reply = json.loads(tx), json.loads(rx)
    owner = f'{slot}/owner/tool_{attempt:02d}'
    require(contract['matched'] and contract['reason'] == 'content_and_envelope_match'
            and contract['RX_sha256'] == sha(rx) and contract['TX_sha256'] == sha(tx)
            and request == original.json(f'{owner}/REQUEST.json') and reply == original.json(f'{owner}/RESPONSE.json'),
            'historical_original_outer_delivery_unbound')
    item_id = contract['caller_identity']['CLI_event_item_id']
    item, = [row['item'] for line in original.get(f'{slot}/consumer/stdout.raw.bin').splitlines() if line
             for row in [json.loads(line)] if row.get('type') == 'item.completed'
             and row.get('item', {}).get('id') == item_id]
    blocks = reply['result']['content']
    index, = [index for index, image in enumerate(blocks) if image['type'] == 'image'
              and base64.b64decode(image['data'], validate=True) == png]
    require(not reply['result']['isError'] and item['result']['content'] == blocks
            and item['tool'] == request['params']['name'] and item['arguments'] == request['params']['arguments']
            and sum(row['type'] == 'image' for row in blocks) == contract['CLI_images'],
            'historical_PNG_did_not_reach_actual_CLI')
    return {'historical_label': label, 'attempt': attempt, 'tool': item['tool'], 'CLI_item_id': item_id,
            'actual_PNG_content_block': index, 'PNG_bytes': len(png), 'PNG_sha256': sha(png),
            'outer_RX_sha256': sha(rx)}


def pixels(frame, png, npz):
    import numpy as np
    from PIL import Image

    idx = frame['object_names'].index(TARGET)
    offset = frame['source_face_offsets'][idx]
    with np.load(BytesIO(npz), allow_pickle=False) as arrays, Image.open(BytesIO(png)) as image:
        selected = (arrays['owners'] == idx) & np.isin(arrays['triangle_ids'], [offset + 512, offset + 513])
        native_rgb = arrays['color'][:, :, :3]
        require(image.size == (512, 512) and np.array_equal(native_rgb, np.asarray(image.convert('RGB'))),
                'archived_png_and_raster_source_differ')
        rgb = native_rgb.astype(np.int32)
        boundary = np.zeros(selected.shape, dtype=bool)
        for a, b in ((np.s_[:-1, :], np.s_[1:, :]), (np.s_[1:, :], np.s_[:-1, :]),
                     (np.s_[:, :-1], np.s_[:, 1:]), (np.s_[:, 1:], np.s_[:, :-1])):
            delta = rgb[a] - rgb[b]
            boundary[a] |= selected[a] & ~selected[b] & (np.sum(delta * delta, axis=2) >= 24 ** 2)
        require(set(arrays['triangle_ids'][selected] - offset) == {512, 513}, 'not_both_selected_source_triangles_visible')
        return int(selected.sum()), int(boundary.sum())


def check_image(result, png, slot, prefix=None):
    blocks = result['content']
    caption, picture = blocks[-2:]
    require(not result['isError'] and caption['type'] == 'text' and picture['type'] == 'image'
            and picture['mimeType'] == 'image/png' and base64.b64decode(picture['data'], validate=True) == png,
            'actual_ordinary_outbound_png_changed')
    title, tail = caption['text'].splitlines()
    binding = json.loads(tail)
    path = Path(binding['local_image_path'])
    require((prefix is None or title.startswith(prefix + ' ')) and path.is_absolute()
            and path.resolve(strict=True).as_posix() == path.as_posix() and path.is_relative_to(slot)
            and path.read_bytes() == png and binding['image_sha256'] == sha(png), 'same_slot_caption_cannot_reopen_png')
    return binding


def prepare_frame(device, frame, png, npz, path):
    import numpy as np

    path.mkdir(parents=True, exist_ok=False)
    out_png, out_npz = path / 'TOP.png', path / 'TOP.npz'
    out_png.write_bytes(png)
    out_npz.write_bytes(npz)
    ready = deepcopy(frame)
    ready.update(PNG=str(out_png), NPZ=str(out_npz))
    with np.load(BytesIO(npz), allow_pickle=False) as packed:
        arrays = {name: packed[name] for name in ('color', 'depth', 'owners', 'triangle_ids')}
    device._register(ready, arrays)
    device._pose_refs[('TOP', None, None)] = ready['ref']
    return ready


def run_bridge(common, bridge, held, slot, image, product_response=None):
    deadline = held.task_deadline
    owner = bridge.Owner(held, {'label': held.label, 'group': held.group, 'phase': 'formal',
                               'worker_deadline_ns': deadline, 'output': str(slot / 'owner')}, budget=held.budget)
    endpoint = owner.start(slot / 'ENDPOINT.json')
    audit = slot / 'offline_consumer'
    math_code = (
        'objs={row["name"]:row for row in scene_data(["M4_Far_00","M4_Focal"])["objects"]}\n'
        'a=np.asarray(objs["M4_Far_00"]["vertices"])\n'
        'b=np.asarray(objs["M4_Focal"]["vertices"])\n'
        'f=np.asarray(objs["M4_Far_00"]["triangles"])\n'
        'top=a[f[[512,513]]]\n'
        'checks=[a[:,0].min()==1,np.all(b[:,0]==0),np.any(np.all(a==[1,0,0],axis=1)),'
        'np.any(np.all(b==[0,0,0],axis=1)),np.all(top[:,:,2]==2),b[:,2].max()==1]\n'
        'print(len(objs),all(checks),np.sqrt(2)>1)'
    )
    known = held.device._pose_refs[('TOP', None, None)]
    calls = [
        request(1, 'initialize'),
        request(2, 'tools/list'),
        call(3, 'execute_python', {'code': math_code}),
        call(4, 'execute_python', {'code': 'print(len(objs),len(f),type(shapely.Point(0,0)).__name__)'}),
        call(5, 'render_views', {'names': ['TOP'], 'include_images': True}),
        call(6, 'read_images', {'refs': [known]}),
        call(7, 'render_local', {'direction': 'TOP', 'target_world_m': [0, 0, 0]}),
        call(8, 'read_images', {'refs': ['native-image:foreign-unknown-ref']}),
    ]
    if product_response is not None:
        query, expected_wire, product_frame, product_bytes = product_response
        calls.append(call(9, 'human_eye_scene_observe', query))
        calls.append(call(10, 'read_images', {'refs': [product_frame]}))
    argv = [sys.executable, '-IB', '-X', 'utf8', str(common.NS / 'consumer/thin_stdio.py'),
            '--endpoint', str(endpoint), '--audit', str(audit)]
    try:
        command = subprocess.run(argv, input=b''.join(bridge.encoded(req) + b'\n' for req in calls),
                                 capture_output=True, timeout=40)
        require(command.returncode == 0, 'ordinary_thin_stdio_failed/' + command.stderr.decode(errors='replace')[-1000:])
        envelopes = [json.loads(line) for line in command.stdout.splitlines()]
        require([row['id'] for row in envelopes] == [row['id'] for row in calls], 'ordinary_outer_reply_ids_changed')
        responses = [row['result'] for row in envelopes]
    finally:
        close = owner.close()
    require(close['confirmed'] and not close['errors'] and not close['transport_errors'], 'ordinary_owner_close_unconfirmed')
    expected = bridge.TOOLS + ([read(common.PRODUCT_SCHEMA)] if held.group == 'P' else [])
    require(responses[1]['tools'] == expected
            and json.loads(responses[2]['content'][0]['text'])['stdout'].strip() == '2 True True'
            and json.loads(responses[3]['content'][0]['text'])['stdout'].strip().startswith('2 ')
            and json.loads(responses[3]['content'][0]['text'])['stdout'].strip().endswith(' Point'),
            'common_tools_or_persistent_same_source_geometry_not_accessible')
    first = check_image(responses[4], image, slot, known)
    second = check_image(responses[5], image, slot, known)
    require(first == second and responses[6]['isError'] and responses[7]['isError'],
            'ordinary_reopen_or_negative_controls_changed')
    foreign = slot.parent / 'FOREIGN.png'
    if not foreign.exists():
        foreign.write_bytes(image)
    registered = held.device.by_ref[known]
    for field, bad, reason in (('PNG', str(foreign), 'current_slot_original_png_path_required'),
                               ('PNG_sha256', '0' * 64, 'current_image_bytes_changed')):
        with patch.dict(registered, {field: bad}):
            try:
                owner.images([known], {'image_attachments': []})
            except ValueError as error:
                require(str(error) == reason, 'ordinary_negative_wrong_reason/' + field)
            else:
                raise ValueError('ordinary_cross_slot_or_bad_digest_was_accepted/' + field)
    journal, = audit.iterdir()
    attempts = len(calls) - 2
    for index, envelope in enumerate(envelopes, 1):
        folder = journal / f'{index:03d}'
        receipt = read(folder / 'RECEIPT.json')
        require(read(folder / 'TX.bin') == calls[index - 1]
                and read(folder / 'RX.bin') == envelope
                and receipt['origin'] == 'owner' and receipt['attempt'] == (index - 2 if index > 2 else None),
                'ordinary_raw_outer_content_or_attempt_unbound')
    exit_record = read(journal / 'EXIT.json')
    count = held.budget.snapshot()['slots'][held.label]
    require(exit_record['normal_exit'] and count['business_admissions'] == attempts and count['raster_actual'] == 0,
            'ordinary_credit_or_exit_contract_changed')
    product_matches = product_response is not None and responses[-2] == expected_wire
    require(product_response is None or product_matches, 'candidate_outer_bridge_changed_real_formatter_result')
    product_image = None if product_response is None else check_image(responses[-1], product_bytes, slot, product_frame)
    return {'public_tool_count': len(expected), 'ordinary_distance_route': 'persistent_python_supported',
            'TOP_PNG_sha256': first['image_sha256'], 'TOP_original_reclosed': True,
            'actual_sandboxed_code_calls': 2, 'invalid_parameters_rejected': True,
            'foreign_ref_and_same_bytes_foreign_file_rejected': True, 'bad_digest_rejected': True,
            'actual_rasters': count['raster_actual'], 'business_attempts': attempts,
            'candidate_original_formatter_matches_outer': product_matches,
            'candidate_SCENE_original_reclosed': None if product_image is None else product_image['image_sha256'],
            'normal_owner_stdio_close': True}


def startup(common, held, window, binding, reject):
    method = held._start_public_mcp
    transport = common.load_retained('_dense_pair_stdio_offline_probe', common.DISPLAY / 'harness/reused/stdio_checks.py')
    real = None
    reads = []

    def new_client(command, folder, destination, deadline):
        here = common.HERE
        require(Path(command[5]) == here / 'mcp_entry.py', 'actual_registered_MCP_entry_changed')
        launcher = ('from pathlib import Path; import runpy, sys; '
                    f'sys.path.insert(0, {str(here)!r}); import common; '
                    'common.EXTERNAL=Path(sys.argv[1]); sys.argv=sys.argv[2:]; '
                    'runpy.run_path(sys.argv[0], run_name="__main__")')
        nonlocal real
        real = transport.StdioClient(command[:5] + ['-c', launcher, str(window)] + command[5:], folder, destination, deadline)
        return real

    def load_module(name, path):
        require(name == '_live_stdio_client' and path == common.DISPLAY / 'harness/reused/stdio_checks.py',
                'actual_candidate_startup_loader_changed')
        return SimpleNamespace(StdioClient=new_client)

    def watched(path):
        reads.append(Path(path).resolve())
        return read(path)

    try:
        with patch.object(held, 'native', SimpleNamespace(host='127.0.0.1', port=1)), patch.object(
                held, '_retain', return_value=object()) as retained:
            hook = FunctionType(method.__func__.__code__, dict(method.__func__.__globals__, load=load_module, read=watched))
            hook(held, common.PRODUCT_BINDING, binding)
        retained.assert_called_once_with(real.process, 'MCP_RUNTIME_PROOF.json')
        sent, expected = reject
        reply = real.call(sent)
        require(reply == expected
                and reads == [common.PRODUCT_SCHEMA.resolve(), common.CATALOGUE.resolve()]
                and read(held.folder / 'MCP_IDENTITY.json')['source_sha256'] == PRODUCT,
                'actual_candidate_boot_catalogue_or_archive_rejection_changed')
        meter = [json.loads(row) for row in (held.folder / 'mcp_io/MCP_IO.jsonl').read_bytes().splitlines()]
        blocked, = (row for row in meter if row['method'] == 'tools/call')
        require(blocked['raster_actual'] == 0, 'rejection_entered_raster_before_validation')
    finally:
        closed = real.finish() if real is not None else {}
    require(closed['confirmed'] and closed['exit_code'] == 0, 'actual_candidate_subprocess_cleanup_not_confirmed')
    return {'source_sha256': PRODUCT, 'real_installed_startup': True, 'real_catalogue_count': len(held.product_tools),
            'registered_schema_reached': True, 'same_original_malformed_reply': True,
            'actual_MCP_normal_close': True, 'raster_attempts': 0}


def product_png(original, held, binding):
    from human_eye_plugin import live_spatial_mcp as mcp

    request = original.json('slots/P1/product_calls/call_001/REQUEST.json')
    result = original.json('slots/P1/product_calls/call_001/RESPONSE.json')
    entry = original.json('slots/P1/owner/tool_01/PRODUCT_RECEIPT.json')
    expected = original.json(f"slots/P1/mcp/rpc_{entry['receipt']['index']:02d}/RX.bin")
    require(result == expected, 'actual_old_product_wire_disconnected_from_public_record')
    packet = original.json('slots/P1/product_full/call_001/SERVICE_RESULT.json')
    metadata = original.json('slots/P1/DEVICE_EVIDENCE.json')
    files = {}
    digest_to_png = {}
    old_slot = original.root / 'slots/P1'
    for frame in packet['frames'] + packet['constructed_frames']:
        for field in ('image_path', 'arrays_path'):
            source = Path(frame[field])
            new = held.folder / source.relative_to(old_slot)
            raw = original.get(source)
            expected_digest = frame['image_sha256'] if field == 'image_path' else frame['arrays_sha256']
            require(sha(raw) == expected_digest, 'archived_dense_product_image_original_changed')
            if source not in files:
                new.parent.mkdir(parents=True, exist_ok=True)
                new.write_bytes(raw)
                files[str(source)] = str(new)
            if field == 'image_path':
                digest_to_png[expected_digest] = raw
    scene_frame, = (row for row in metadata['frames'] if row['view'] == 'SCENE' and row['origin'] == 'product')
    png = digest_to_png[IMAGES['SCENE']]
    pixel = pixels(scene_frame, png, original.get(Path(scene_frame['NPZ'])))
    require(pixel == (1197, 138), 'actual_dense_product_visibility_pixel_receipt_changed')
    # Preserve the archived producer and its historical source attestation.
    # The replay substitutes only fixture file locations under the offline owned slot.
    def rebase(value):
        if isinstance(value, str):
            return files.get(value, value)
        if isinstance(value, dict):
            return {key: rebase(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rebase(item) for item in value]
        return value

    rebased = rebase(packet)

    class Saved:
        state_path = held.folder / 'product_state.json'
        calls = 0

        def observe(self, session, **arguments):
            require(self.calls == 0 and session == rebased['session_id']
                    and arguments['query'] == request['params']['arguments']['query']
                    and arguments['include_image'] is True, 'actual_registered_qualification_input_changed')
            self.calls += 1
            return deepcopy(rebased)

        def _check_request_budget(self, phase):
            require(phase == 'before_task_publication', 'public_formatter_bypassed_final_budget')

    stub = Saved()
    server = mcp.LiveSpatialMCPServer(stub, default_session_id=rebased['session_id'])
    returned = server.handle_jsonrpc_message(deepcopy(request))
    result_blocks = returned['result']['content']
    historical_blocks = expected['result']['content']
    require(stub.calls == 1 and returned['result']['isError'] is False and result_blocks[1:] == historical_blocks[1:]
            and json.loads(result_blocks[0]['text']) == json.loads(historical_blocks[0]['text'])
            and png in [base64.b64decode(row['data'], validate=True) for row in result_blocks[1:]],
            'current_product_formatter_did_not_preserve_actual_dense_visibility_evidence')
    held.device.adopt_product_result(rebased)
    return request['params']['arguments'], returned['result'], scene_frame['ref'], png, {
        'actual_candidate_formatter': True, 'source_sha256': binding['source_sha256'],
        'original_ordered_PNG_sha256': [sha(base64.b64decode(row['data'], validate=True)) for row in result_blocks[1:]],
        'original_SCENE_pixels': list(pixel), 'original_body_and_native_images_semantically_exact': True,
        'archive_producer_geometry_scope_preserved': True,
        'historical_delivery': historical_delivery(original, 'P1', 1, png),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'use_pinned_interpreter_minus_I_minus_B')
    repo = args.repo.resolve()
    ns = repo / 'verification/perf050_dense_pair_transfer_001'
    sys.path.insert(0, str(ns / 'harness'))
    import common
    from budget import LIMITS
    import admission
    from closure import startup_closure

    binding = read(common.PRODUCT_BINDING)
    shared = common.SEAL / 'SHARED_DEPENDENCY.json'
    sys.path[:0] = [str(ns), binding['install_root'], binding['dependency_root'], read(shared)['dependency_root']]
    import bridge
    import runtime
    from human_eye_plugin.runtime_identity import runtime_identity

    require(not common.EXTERNAL.exists() and runtime_identity()['source_sha256'] == PRODUCT
            and admission.registered_product()['source_sha256'] == PRODUCT, 'not_new_isolated_dense_product_batch')
    common.asset_identity()
    dispatch = {}
    for label in common.ORDER:
        cmd = [sys.executable, '-IB', str(common.HERE / 'run_slot.py'), label, '--dispatch-smoke']
        dispatch[label] = json.loads(subprocess.check_output(cmd, timeout=30))
    cmd = [sys.executable, '-IB', str(common.HERE / 'mcp_entry.py'), '--dispatch-smoke']
    dispatch['MCP'] = json.loads(subprocess.check_output(cmd, timeout=30))
    require(all(row['group'] == label[0] and Path(row['actual_product_schema']) == common.PRODUCT_SCHEMA
                for label, row in dispatch.items() if label in common.ORDER)
            and Path(dispatch['MCP']['absolute_state_file']) == common.EXTERNAL/'slots/P1/product_state.json',
            'actual_registered_dense_dispatch_mismatch')
    original = Archive(common.FORMAL / 'RUNTIME_INDEX.json', ARCHIVE)
    old_p2 = Archive(repo / 'verification/perf050_target_observation_first_image_p2/RUNTIME_INDEX.json', P2_ARCHIVE)
    reject = (old_p2.json('slots/P2/mcp/rpc_05/TX.bin'), old_p2.json('slots/P2/mcp/rpc_05/RX.bin'))
    raw, native = read_origin(original)
    png, npz = (original.get(Path(native[key])) for key in ('PNG', 'NPZ'))
    require(sha(png) == IMAGES['TOP'] and pixels(native, png, npz) == (1521, 152),
            'archived_TOP_visibility_bytes_or_pixels_changed')
    native_delivery = historical_delivery(original, 'N2', 8, png)
    reports = {}
    began = time.perf_counter_ns()
    with tempfile.TemporaryDirectory(prefix='probe_', dir=args.output.parent) as folder:
        window = Path(folder).resolve()
        for label in common.ORDER:
            slot = window / 'slots' / label
            slot.mkdir(parents=True)
            inherited = runtime.Runtime.__mro__[2]
            with patch.dict(inherited.__init__.__globals__, EXTERNAL=window):
                held = runtime.Runtime(slot, label, began + 100_000_000_000, began + 120_000_000_000)
            held.prepare_device(ASSET)
            held.device._scene = deepcopy(raw)
            prepare_frame(held.device, native, png, npz, slot / 'archived_native_TOP')
            product_response = None
            if label == 'P1':
                product_start = startup(common, held, window, binding, reject)
                arguments, result, product_ref, product_scene, product_report = product_png(original, held, binding)

                def serve(query):
                    require(query == arguments, 'shared_owner_changed_candidate_request')
                    return {'jsonrpc': '2.0', 'id': 'observe-1', 'result': deepcopy(result)}

                held.public_request = serve
                product_response = (arguments, result, product_ref, product_scene)
            reports[label] = run_bridge(common, bridge, held, slot, png, product_response)
        early = {'spawn': None, 'failure': None, 'launch_cleanup': None, 'settlement': None,
                 'asset_matches': True, 'copy_matches': None}
        not_worker = {'status': 'failed', 'model_consumers': 0, 'paid_API_calls': 0}
        receipt = {'status': 'failed', 'owned_budget_passed': True}
        require(admission.can_continue({**not_worker, 'closure_verification': startup_closure(
                    **early, startup_entered=False)}, receipt)
                and not admission.can_continue({**not_worker, 'closure_verification': startup_closure(**early)}, receipt),
                'premature_close_admitted_without_real_cleanup')
    require(not common.EXTERNAL.exists() and reports['N1']['TOP_PNG_sha256'] == reports['P1']['TOP_PNG_sha256'],
            'offline_qualification_touched_formal_root_or_diverged_ordinary_images')
    refs = {p['path']: p for p in original.pins + old_p2.pins}
    for path in [Path(__file__), common.ASSET, common.PRODUCT_BINDING, Path(binding['wheel_path']),
                 common.PRODUCT_SCHEMA, common.CATALOGUE, shared, common.NS / 'consumer/thin_stdio.py',
                 common.DISPLAY / 'harness/reused/stdio_checks.py', common.FORMAL / 'bridge.py',
                 common.FORMAL / 'frame_device.py', *common.HERE.glob('*.py')]:
        item = file_pin(path)
        refs[item['path']] = item
    result = {'passed': True, 'schema': 'perf050-dense-pair-transfer-offline-host-v1',
              'Blender_launches': 0, 'model_calls': 0, 'actual_owned_slots': 0, 'new_raster_attempts': 0,
              'ledger_limits': LIMITS, 'entrypoints': dispatch, 'ordinary': reports, 'plugin': product_start,
              'product_formatter_replay': product_report, 'historical_native_TOP_delivery': {**native_delivery,
                'selected_surface_pixels': 1521, 'contrasting_boundary_pixels': 152},
              'asset_sha256': ASSET, 'early_cleanup_checked': True,
              'source_pins': list(refs.values())}
    original.zip.close()
    old_p2.zip.close()
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(file_pin(args.output))


if __name__ == '__main__':
    main()
