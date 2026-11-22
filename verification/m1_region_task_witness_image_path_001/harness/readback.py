"""Original Owner/thin/read_images over restored closed-slot frame resources."""

import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from replay import ORIGINAL, V, pin, read, require, save, transport


def public_read_images(root, record, catalogue, refs):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    shared = read(V / 'm5_harness_recovery_001/SHARED_DEPENDENCY.json')
    sys.path[:0] = [str(ORIGINAL / 'harness'), str(ORIGINAL), shared['dependency_root'],
                   'D:/he_anchor_001/venv/Lib/site-packages']
    from bridge import Owner
    from frame_device import FrameDevice

    reads = []
    tracking = {'enabled': True}
    old_folder = record['folder'].resolve()

    def audit(event, args):
        if not tracking['enabled'] or event != 'open':
            return
        path, mode, flags = args
        if not isinstance(path, (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(path)).resolve()
        if not path.is_relative_to(old_folder):
            return
        writing = (isinstance(mode, str) and any(char in mode for char in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        require(not writing, 'original_closed_slot_write_forbidden')
        if path.suffix.lower() == '.png':
            reads.append(str(path))

    sys.addaudithook(audit)
    deadline = time.perf_counter_ns() + 60_000_000_000

    class RetainedFrames:
        def __init__(self):
            # The original Owner enforces this boundary on its public PNG path.
            # All mutable event evidence goes to the new device output instead.
            self.folder = old_folder
            self.product_tools = catalogue
            self.public_requests = []
            self.device = FrameDevice(runroot=root, asset_sha256=record['device']['asset_sha256'],
                group='P', label=record['slot'], native_call=self.no_host,
                phase='qualification' if record['slot'].startswith('Q') else 'formal')
            self.buffers, self.cameras = self.device.buffers, self.device.cameras
            self.image_specification = self.device.image_specification
            by_ref = {frame['ref']: frame for frame in record['device']['frames']}
            for frame in record['producer']['frames']:
                old = by_ref[frame['image_ref']]
                require(Path(old['PNG']).resolve() == Path(frame['image_path']).resolve()
                        and (old['PNG_sha256'], old['frame_identity']) == (
                            frame['image_sha256'], frame['frame_identity']),
                    'closed_retained_frame_does_not_match_producer')
                self.device.by_ref[frame['image_ref']] = old

        def no_host(self, *args, **kwargs):
            raise AssertionError('public_image_read_must_not_capture_or_render')

    runtime = RetainedFrames()
    phase = 'qualification' if record['slot'].startswith('Q') else 'formal'
    owner = Owner(runtime, {'label': record['slot'], 'group': 'P', 'phase': phase,
                           'worker_deadline_ns': deadline, 'output': str(root / 'owner')})
    endpoint = owner.start(root / 'ENDPOINT.json')
    client = None
    try:
        client = transport().StdioClient(
            [sys.executable, '-I', '-B', '-X', 'utf8',
             str(ORIGINAL / 'consumer/thin_stdio.py'), '--endpoint', endpoint,
             '--audit', str(root / 'attachments')], root, root / 'thin_wire', deadline)
        client.call({'jsonrpc': '2.0', 'id': 'initialize', 'method': 'initialize',
                     'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                'clientInfo': {'name': 'witness-path-public-readback', 'version': '1'}}})
        client.call({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        request = {'jsonrpc': '2.0', 'id': 'read-originals', 'method': 'tools/call',
                   'params': {'name': 'read_images', 'arguments': {'refs': refs}}}
        save(root / 'REQUEST.json', request)
        response = client.call(request)
        save(root / 'RESPONSE.json', response)
        require(response['result']['isError'] is False, 'actual_public_read_images_failed')
        blocks = response['result']['content']
        images, paths = [], []
        for block in blocks:
            if block['type'] == 'image':
                raw = base64.b64decode(block['data'], validate=True)
                images.append({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
            elif block['type'] == 'text':
                _, text = block['text'].split('\n', 1)
                paths.append(json.loads(text))
        require(len(images) == len(paths) == len(refs), 'public_image_reference_count_mismatch')
        output = {'requested_refs': refs, 'images': images, 'public_paths': paths,
                  'response_path': str(root / 'RESPONSE.json'), 'PNG_read_opens': reads,
                  'original_read_images_folder': str(record['read_images_folder']),
                  'original_result_equal': response['result'] == record['read_images_response']['result'],
                  'original_request_arguments_equal': request['params']['arguments'] ==
                      record['read_images_request']['params']['arguments'],
                  'original_ref_bindings': [{key: runtime.device.by_ref[ref][key]
                      for key in ('ref', 'scope_id', 'frame_identity', 'view_name', 'PNG', 'PNG_sha256')}
                      for ref in refs],
                  'normal_read_scope': 'original FrameDevice image_specification plus original image_content encoder',
                  'new_PNG_files': 0, 'new_rasters': 0, 'new_captures': 0}
    finally:
        try:
            if client is not None:
                close = client.finish()
                save(root / 'THIN_CLOSE.json', close)
                require(close['confirmed'] and close['exit_code'] == 0, 'original_thin_close_unconfirmed')
        finally:
            closed = owner.close()
            tracking['enabled'] = False
            save(root / 'OWNER_CLOSE.json', closed)
            require(closed['confirmed'] and not closed['errors'] and not closed['transport_errors'],
                    'original_image_owner_close_unconfirmed')
    save(root / 'RESULT.json', output)
    return output
