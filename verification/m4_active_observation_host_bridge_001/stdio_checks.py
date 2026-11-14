"""Finite local MCP consumer and same-capture, host-instance comparison.

No model client or Blender startup is embedded here. The root controller owns
the sequence and launches this local transport through the methods below.
"""

import base64
import hashlib
import io
import json
from pathlib import Path
import queue
import subprocess
import threading
import time


MAX_FRAME = 32 * 1024 * 1024


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(',', ':')) + '\n').encode('ascii')


def save(path, value):
    Path(path).write_bytes(encoded(value))


def inspect_images(response, output_directory):
    """Decode actual received ImageContent, independently of server metadata."""
    from PIL import Image

    started = time.perf_counter_ns()
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=False)
    content = response.get('result', {}).get('content', [])
    texts = [json.loads(block['text']) for block in content if block.get('type') == 'text']
    assert len(texts) == 1
    rows = []
    for block in content:
        if block.get('type') != 'image':
            continue
        assert block['mimeType'] == 'image/png'
        raw = base64.b64decode(block['data'], validate=True)
        assert raw.startswith(b'\x89PNG\r\n\x1a\n')
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            assert image.format == 'PNG' and image.size == (512, 512)
            dimensions = list(image.size)
            pixels = image.convert('RGB').tobytes()
        path = output / ('image_' + str(len(rows) + 1).zfill(2) + '.png')
        path.write_bytes(raw)
        rows.append({'index': len(rows) + 1, 'path': str(path.resolve()),
                     'PNG_sha256': hashlib.sha256(raw).hexdigest(), 'PNG_bytes': len(raw),
                     'base64_characters': len(block['data']), 'size_px': dimensions,
                     'RGB_sha256': hashlib.sha256(pixels).hexdigest(), 'RGB_bytes': len(pixels),
                     'consumer_read_confirmed': True})
    closed = time.perf_counter_ns()
    value = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started,
             'text': texts[0], 'images': rows, 'image_blocks_read': len(rows),
             'PNG_bytes': sum(row['PNG_bytes'] for row in rows),
             'base64_characters': sum(row['base64_characters'] for row in rows),
             'model_image_consumption': 'not_tested', 'model_calls': 0}
    save(output / 'READBACK.json', value)
    return value


class StdioClient:
    """A held-process local reader with exact original stdout and wire files."""

    def __init__(self, command, cwd, output, deadline_ns):
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.deadline = deadline_ns
        self.events = queue.Queue()
        self.records = []
        self.close_record = None
        self.stderr = (self.output / 'stderr.raw.bin').open('wb')
        self.process = None
        self.reader = None
        started = time.perf_counter_ns()
        try:
            self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.stderr, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            def read():
                try:
                    with (self.output / 'stdout.raw.bin').open('xb') as raw_stream:
                        while True:
                            raw = self.process.stdout.readline(MAX_FRAME + 1)
                            if not raw:
                                break
                            raw_stream.write(raw)
                            raw_stream.flush()
                            if len(raw) > MAX_FRAME:
                                raise ValueError('stdio_frame_bytes_exceeded')
                            self.events.put(('reply', raw, time.perf_counter_ns()))
                except BaseException as exc:
                    self.events.put(('error', {'type': type(exc).__name__, 'message': str(exc)}, time.perf_counter_ns()))
                finally:
                    self.events.put(('eof', None, time.perf_counter_ns()))
            self.reader = threading.Thread(target=read, daemon=True)
            self.reader.start()
            save(self.output / 'START.json', {'pid': self.process.pid, 'command': command,
                                             'cwd': str(cwd), 'started_ns': started, 'ready_ns': time.perf_counter_ns(),
                                             'deadline_ns': deadline_ns, 'model_calls': 0})
        except BaseException:
            self.finish()
            raise

    def call(self, request):
        started = time.perf_counter_ns()
        if started >= self.deadline:
            raise TimeoutError('original_stdio_deadline_exceeded')
        folder = self.output / ('rpc_' + str(len(self.records) + 1).zfill(2))
        folder.mkdir()
        tx = encoded(request)
        (folder / 'TX.bin').write_bytes(tx)
        row = {'index': len(self.records) + 1, 'id': request.get('id'), 'method': request['method'],
               'started_ns': started, 'TX_bytes': len(tx), 'error': None}
        try:
            self.process.stdin.write(tx)
            self.process.stdin.flush()
            row['stdin_flushed_ns'] = time.perf_counter_ns()
            if 'id' not in request:
                return None
            kind, raw, received = self.events.get(timeout=max(.001, (self.deadline - time.perf_counter_ns()) / 1e9))
            if kind != 'reply':
                raise RuntimeError('stdio_' + kind + ':' + str(raw))
            (folder / 'RX.bin').write_bytes(raw)
            response = json.loads(raw)
            assert response.get('id') == request['id']
            row.update(RX_bytes=len(raw), received_complete_ns=received,
                       consumer_json_decoded_ns=time.perf_counter_ns(),
                       RX_sha256=hashlib.sha256(raw).hexdigest())
            save(folder / 'RESPONSE.json', response)
            return response
        except BaseException as exc:
            row['error'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
        finally:
            row['closed_ns'] = time.perf_counter_ns()
            row['elapsed_ns'] = row['closed_ns'] - started
            self.records.append(row)
            save(folder / 'RECEIPT.json', row)

    def finish(self):
        if self.close_record is not None:
            return self.close_record
        started = time.perf_counter_ns()
        errors = []
        forced = False
        exit_code = None
        handle_closed = False
        pipes_closed = {}
        if self.process is not None:
            try:
                if self.process.stdin is not None and not self.process.stdin.closed:
                    self.process.stdin.close()
            except BaseException as exc:
                errors.append({'stage': 'stdin_close', 'type': type(exc).__name__, 'message': str(exc)})
            try:
                exit_code = self.process.wait(timeout=max(.001, min(8, (self.deadline - time.perf_counter_ns()) / 1e9)))
            except subprocess.TimeoutExpired:
                forced = True
            except BaseException as exc:
                errors.append({'stage': 'initial_wait', 'type': type(exc).__name__, 'message': str(exc)})
            if exit_code is None:
                forced = True
                try:
                    self.process.kill()
                except BaseException as exc:
                    errors.append({'stage': 'held_process_kill', 'type': type(exc).__name__, 'message': str(exc)})
                try:
                    exit_code = self.process.wait(timeout=5)
                except BaseException as exc:
                    errors.append({'stage': 'post_kill_wait', 'type': type(exc).__name__, 'message': str(exc)})
        if self.reader is not None and self.reader.ident is not None:
            try:
                self.reader.join(timeout=2)
            except BaseException as exc:
                errors.append({'stage': 'reader_join', 'type': type(exc).__name__, 'message': str(exc)})
        if self.process is not None:
            for name in ('stdin', 'stdout', 'stderr'):
                stream = getattr(self.process, name, None)
                if name == 'stdout' and self.reader is not None and self.reader.is_alive():
                    pipes_closed[name] = False
                    errors.append({'stage': 'stdout_close_deferred',
                                   'type': 'ReaderStillRunning',
                                   'message': 'Retain the pipe while the reader may hold its buffer lock.'})
                    continue
                try:
                    if stream is not None:
                        stream.close()
                    pipes_closed[name] = stream is None or stream.closed
                except BaseException as exc:
                    pipes_closed[name] = False
                    errors.append({'stage': name + '_close', 'type': type(exc).__name__, 'message': str(exc)})
            try:
                handle = getattr(self.process, '_handle', None)
                if handle is not None and exit_code is not None:
                    handle.Close()
                    handle_closed = bool(handle.closed)
                elif handle is None:
                    handle_closed = True
            except BaseException as exc:
                errors.append({'stage': 'process_handle_close', 'type': type(exc).__name__, 'message': str(exc)})
        try:
            self.stderr.close()
        except BaseException as exc:
            errors.append({'stage': 'stderr_file_close', 'type': type(exc).__name__, 'message': str(exc)})
        self.close_record = {'pid': None if self.process is None else self.process.pid,
                             'started_ns': started, 'closed_ns': time.perf_counter_ns(),
                             'exit_code': exit_code, 'forced_kill': forced, 'process_handle_closed': handle_closed,
                             'pipes_closed': pipes_closed,
                             'reader_stopped': self.reader is None or not self.reader.is_alive(), 'errors': errors}
        self.close_record['elapsed_ns'] = self.close_record['closed_ns'] - started
        self.close_record['confirmed'] = (exit_code == 0 and not forced and handle_closed
                                          and self.close_record['reader_stopped'] and all(pipes_closed.values()) and not errors)
        save(self.output / 'CLOSE.json', self.close_record)
        return self.close_record


def compare_same_capture(core, capture, cameras, bridge_result, bridge_index):
    """An extra QA-only parse/index comparison, with no rendering or capture.

    The exact same installed-input capture saved by stdio_entry is supplied by
    the controller. Old fixture object ordering or ROI hashes are never used.
    """
    started = time.perf_counter_ns()
    meshes = capture['meshes']
    scene = {'unit': 'm', 'coordinate_frame': 'world', 'objects': [
        {'name': mesh['name'], 'vertices': mesh['vertices'], 'triangles': mesh['faces']} for mesh in meshes
    ]}
    session = core.prepare_scene(scene, cameras)
    actual_regions = bridge_result['facts']['regions']
    mapping = {index: {'host_object_id': mesh['object_id'], 'name': mesh['name'],
                       'instance': capture['host_identity']['object_instances'][mesh['object_id']]}
               for index, mesh in enumerate(meshes)}
    direct = {region.roi_id: {'host': mapping[region.object_index], 'vertices': [[str(value) for value in point] for point in region.vertices],
                             'normal': [str(value) for value in region.normal], 'triangle_indices': list(region.triangle_indices)}
              for region in session.regions}
    expected_regions = [{'roi_id': region.roi_id, 'object_index': region.object_index,
                         'object_name': region.object_name, 'triangle_indices': list(region.triangle_indices),
                         'vertices': [[str(value) for value in point] for point in region.vertices],
                         'normal': [str(value) for value in region.normal]} for region in session.regions]
    capture_sha = hashlib.sha256(encoded(capture)).hexdigest()
    for observation in bridge_result['facts']['observations']:
        session.observe({'scene_identity': session.scene_identity, 'candidate_identity': session.candidate_identity,
                         'view_name': observation['view_name'], 'actual_image_delivered': True,
                         'image_path': observation['image_path'], 'image_sha256': observation['image_sha256'],
                         'image_ref': observation.get('image_ref'), 'pixel_evidence_scope': 'actual_common_depth_owner',
                         'readable_roi_ids': observation['readable_roi_ids']})
    result = {'same_capture_sha256': capture_sha,
              'capture_revision': capture['revision'], 'host_mapping': mapping,
              'direct_regions': direct, 'direct_region_ids': list(session.index.region_ids),
              'direct_view_masks': session.index.view_masks,
              'direct_classifications': session.index.classifications,
              'public_region_ids_match': set(direct) == {row['roi_id'] for row in actual_regions},
              'bridge_projection_bound_to_same_capture': bridge_index['actual_capture_sha256'] == capture_sha,
              'bridge_regions_equal': expected_regions == bridge_index['regions'],
              'bridge_full_classifications_equal': session.index.classifications == bridge_index['classifications'],
              'bridge_view_masks_equal': session.index.view_masks == bridge_index['view_masks'],
              'bridge_scene_camera_identities_equal': ((session.scene_identity, session.candidate_identity)
                  == (bridge_index['scene_identity'], bridge_index['candidate_identity'])),
              'bridge_actual_receipt_state_equal': session.summary() == bridge_result['facts']['coverage'],
              'extra_QA_geometry_parses': 1, 'extra_QA_indexes': 1, 'new_rasters': 0,
              'started_ns': started, 'closed_ns': time.perf_counter_ns()}
    result['elapsed_ns'] = result['closed_ns'] - started
    return result
