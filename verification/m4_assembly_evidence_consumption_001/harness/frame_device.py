"""Shared current Blender mesh read and same-slot terminal source evidence."""

import copy
import hashlib
import json
import os
from pathlib import Path
import time

from common import ALL_NAMES, LIVE, TASK_NAMES

CAPTURE_CODE = LIVE / 'harness/device_capture.py'
CAPTURE_MARKER = 'M4_LIVE_ASSEMBLY_CAPTURE:'


def _counts(arrays):
    return {'vertices': sum(len(row['vertices']) for row in arrays),
            'triangles': sum(len(row['triangles']) for row in arrays),
            'polygons': sum(row['polygon_count'] for row in arrays)}


class FrameDevice:
    def __init__(self, runroot, asset_sha256, copy_path, pid, group, label, native_call, terminal_call, check):
        self.runroot = Path(runroot).resolve()
        self.asset_sha256, self.copy_path, self.pid = asset_sha256, Path(copy_path).resolve(), pid
        self.group, self.label, self.check = group, label, check
        self.native_call, self.terminal_call = native_call, terminal_call
        self.source_reads, self.events = [], []
        self._scene = self._terminal_receipt = None

    def _record(self, event, **details):
        self.events.append({'event': event, 'at_ns': time.perf_counter_ns(), **details})

    def _capture(self, *, terminal):
        self.check(terminal=terminal)
        ref = f'live-source-{len(self.source_reads) + 1:03d}'
        path = self.runroot / ('terminal_sources' if terminal else 'raw_sources') / (ref + '.json')
        path.parent.mkdir(exist_ok=True)
        started = time.perf_counter_ns()
        source_code = CAPTURE_CODE.read_text(encoding='utf8') + (
            f'\ncapture_device(bpy, {str(path)!r}, {self.asset_sha256!r}, terminal={terminal!r})')
        code = f'exec(compile({source_code!r}, "<m4-live-assembly-capture>", "exec"), {{"bpy": bpy}})'
        callback = self.terminal_call if terminal else self.native_call
        record = {'source_ref': ref, 'path': str(path), 'terminal': terminal, 'status': 'failed'}
        self.source_reads.append(record)
        try:
            result = callback(code, trusted=True, timeout_s=30)
            if result['error'] is not None:
                raise RuntimeError('owned_Blender_assembly_read_failed:' + str(result['error']))
            lines = [line[len(CAPTURE_MARKER):] for line in result['stdout'].splitlines() if line.startswith(CAPTURE_MARKER)]
            if len(lines) != 1:
                raise ValueError('one_owned_assembly_capture_receipt_required')
            worker = json.loads(lines[0])
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if (len(raw), digest) != (worker['bytes'], worker['sha256']):
                raise ValueError('owned_assembly_capture_readback_mismatch')
            scene = json.loads(raw)
            source = scene['source']
            expected_schema = 'm4-live-assembly-' + ('terminal-source-v1' if terminal else 'native-scene-v1')
            if (scene['schema'] != expected_schema or source['pid'] != self.pid or worker['pid'] != self.pid
                    or source['asset_sha256'] != self.asset_sha256 or Path(source['asset_copy']).resolve() != self.copy_path):
                raise ValueError('owned_assembly_capture_source_identity_mismatch')
            objects = scene['objects']
            arrays = [item['evaluated'] if terminal else item for item in objects]
            counts = _counts(arrays)
            if (tuple(item['name'] for item in objects) != ALL_NAMES or counts['vertices'] != 416
                    or counts['triangles'] != 744 or len({item['object_id'] for item in objects}) != len(ALL_NAMES)
                    or len({item['instance_id'] for item in objects}) != len(ALL_NAMES)):
                raise ValueError('fixed_assembly_capture_mesh_inventory_required')
            digests = {item['name']: item['mesh_sha256'] for item in objects}
            record.update(sha256=digest, bytes=len(raw), worker=worker, evaluated_counts=counts, mesh_sha256=digests)
            if terminal:
                record['native_counts'] = _counts([item['native'] for item in objects])
                if self._scene is not None:
                    if (self._scene['source'] != source
                            or {item['name']: item['mesh_sha256'] for item in self._scene['objects']} != digests):
                        raise ValueError('ordinary_scene_and_terminal_evaluated_geometry_changed')
                    record['ordinary_source_ref'] = self._scene['source_ref']
                final = self.runroot / 'TERMINAL_SOURCE.json'
                os.link(path, final)
                record.update(path=str(final), worker_path=str(path))
            scene['source_ref'] = ref
            record['status'] = 'complete'
            return scene
        except Exception as error:
            record['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            closed = time.perf_counter_ns()
            record['parent_read'] = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
            self.save_evidence()

    def scene_data(self, selectors=None):
        self.check()
        if selectors is not None and (type(selectors) is not list
                                      or any(type(name) is not str or name not in ALL_NAMES for name in selectors)):
            raise ValueError('assembly_object_names_or_null_required')
        if self._scene is None:
            self._scene = self._capture(terminal=False)
            self._record('geometry_captured', requested_by='scene_data', source_ref=self._scene['source_ref'])
        else:
            self._record('geometry_cache_hit', requested_by='scene_data', source_ref=self._scene['source_ref'])
        names = TASK_NAMES if selectors is None else selectors
        result = {field: copy.deepcopy(value) for field, value in self._scene.items()
                  if field not in ('objects', 'source_face_offsets', 'display_object_mask')}
        result['objects'] = [copy.deepcopy(row) for row in self._scene['objects'] if row['name'] in names]
        result['display_object_mask'] = [row['visible_get'] for row in result['objects']]
        self.save_evidence()
        self.check()
        return result

    def save_evidence(self):
        packet = {'schema': 'm4-live-assembly-device-evidence-v1', 'label': self.label, 'group': self.group,
                  'asset_sha256': self.asset_sha256, 'frames': [], 'sources': self.source_reads,
                  'events': self.events, 'terminal_source': self._terminal_receipt}
        path = self.runroot / 'DEVICE_EVIDENCE.json'
        temporary = path.with_suffix('.next')
        with temporary.open('x', encoding='utf8', newline='\n') as stream:
            json.dump(packet, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)

    def export_terminal(self):
        """Capture fresh native and evaluated arrays inside the owned window."""
        if self._terminal_receipt is None:
            self._capture(terminal=True)
            self._terminal_receipt = copy.deepcopy(self.source_reads[-1])
            self.save_evidence()
        return copy.deepcopy(self._terminal_receipt)
