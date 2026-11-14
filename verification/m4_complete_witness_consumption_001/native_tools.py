"""Shared raw replay inputs/raster and the installed observation entry.

This task adapter imports no product implementation until a fresh owner starts.
It supplies source geometry and primitive buffers through the common tools.
"""

import contextlib
import copy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRODUCT_SOURCE_SHA256 = 'd8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02'
SURFACE_COLOR = (180, 190, 205)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, default=str, sort_keys=True,
                       allow_nan=False, separators=(',', ':')) + '\n').encode('utf8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    raw = encoded(value)
    with Path(path).open('wb') as stream:
        stream.write(raw)
    return raw


def check_deadline(deadline_ns):
    if time.perf_counter_ns() >= deadline_ns:
        raise TimeoutError('original_route_deadline')


class RenderLimitError(ValueError):
    pass


class Trace:
    def __init__(self, path, group):
        self.stream = Path(path).open('xb')
        self.group, self.sequence = group, 0

    def emit(self, event, durable=False, **fields):
        self.sequence += 1
        row = {'sequence': self.sequence, 'event': event, 'monotonic_ns': time.perf_counter_ns(),
               'process_id': os.getpid(), 'group': self.group, **fields}
        self.stream.write(encoded(row))
        self.stream.flush()
        if durable:
            os.fsync(self.stream.fileno())
        return row

    def close(self):
        self.stream.close()


class ReplayHost:
    def __init__(self, session, capture_bytes):
        self.session, self.capture_bytes = session, capture_bytes
        self.capture = json.loads(capture_bytes)

    def capture_scene(self):
        self.session.check()
        started = time.perf_counter_ns()
        value = copy.deepcopy(self.capture)
        index = len(self.session.replays) + 1
        path = self.session.output / ('PRIVATE_REPLAY_' + str(index).zfill(2) + '.json')
        path.write_bytes(self.capture_bytes)
        row = dict(index=index, replay_label='CAPTURE_REPLAY', path=str(path),
                   sha256=digest(self.capture_bytes), bytes=len(self.capture_bytes),
                   started_ns=started, closed_ns=time.perf_counter_ns(),
                   actual_Blender_capture_calls=0, deep_copy_returned=True)
        self.session.replays.append(row)
        self.session.trace.emit('capture_replayed', durable=True, **row)
        return value


class ObservationSession:
    def __init__(self, config):
        self.output = Path(config['output']).resolve()
        self.group = config['group']
        self.deadline_ns = config['worker_deadline_ns']
        self.max_render_attempts = config.get('max_render_attempts', 6)
        if self.group not in ('N', 'P') or self.max_render_attempts != 6:
            raise ValueError('fixed_group_and_six_render_cap')
        self.trace = Trace(self.output / 'TRACE.jsonl', self.group)
        self.started_ns = time.perf_counter_ns()
        self.attempts, self.runtime_faults, self.stages = [], [], []
        self.by_view, self.by_ref, self.buffers = {}, {}, {}
        self.cache_requests = []
        self._owner_generation = ('native-global-source-triangles-v1', None)
        self.product_calls, self.replays = [], []
        self.product_image_failures = []
        self._render_origin = None
        self._render_view = None
        self._consumer_running = False
        self._budget_io = False
        self.audit = dict(forbidden_old_evidence_reads=0, old_evidence_read_attempts=[],
                          forbidden_old_writes=0, old_write_attempts=[], forbidden_product_calls=[])
        self.check()
        started = time.perf_counter_ns()
        manifest_path = Path(config['input_manifest']).resolve()
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if manifest['schema'] not in ('region-localization-consumption-001-inputs-v1', 'view-reuse-001-inputs-v1') or manifest['replay_label'] != 'CAPTURE_REPLAY':
            raise ValueError('frozen_replay_input_manifest')
        self._private_paths = {manifest_path}
        data, source_inputs = {}, {}
        for name in ('scene', 'cameras', 'capture', 'product_binding'):
            specification = manifest[name]
            path = (Path(specification['path']) if 'path' in specification else manifest_path.parent / specification['file']).resolve()
            if name in ('capture', 'product_binding'):
                self._private_paths.add(path)
            source_inputs[name + '_path'] = str(path)
            source_inputs[name + '_sha256'] = specification['sha256']
            if name != 'capture' or self.group == 'P':
                raw = path.read_bytes()
                if digest(raw) != specification['sha256']:
                    raise ValueError('frozen_input_changed:' + name)
                data[name] = (raw, json.loads(raw))
        self.scene = data['scene'][1]
        self.cameras = data['cameras'][1]
        if (set(self.scene) != {'objects'} or any(set(obj) != {'name', 'vertices', 'triangles'} for obj in self.scene['objects'])
                or manifest['public_surface_color_rgb'] != list(SURFACE_COLOR)):
            raise ValueError('raw_public_geometry_and_shared_color')
        self.poses = {pose['name']: pose for pose in self.cameras['views']}
        if len(self.poses) != 6 or any(pose['size_px'] != [512, 512] for pose in self.poses.values()):
            raise ValueError('six_registered_512_cameras')
        self.source_inputs = dict(source_inputs, replay_label='CAPTURE_REPLAY',
            manifest_path=str(manifest_path), manifest_sha256=digest(manifest_bytes))
        self._frozen_source_ids = tuple(self.source_inputs[name + '_sha256']
                                        for name in ('scene', 'cameras', 'capture', 'product_binding'))
        self.binding = data['product_binding'][1]
        self.product_root = Path(self.binding['install_root']).resolve()
        if self.binding['source_sha256'] != PRODUCT_SOURCE_SHA256:
            raise ValueError('accepted_installed_product_generation')
        contract = manifest['budget_contract']
        self.phase = config['phase']
        self.budget_root = Path(config['budget_root']).resolve()
        self.phase_cap = contract['preparation_cap'] if self.phase == 'preparation' else contract['formal_cap']
        self.total_cap = contract['total_cap']
        if (self.phase not in ('preparation', 'formal') or self.budget_root != Path(contract['ledger_root']).resolve()
                or config['phase_render_cap'] != self.phase_cap or config['whole_render_cap'] != self.total_cap
                or type(self.total_cap) is not int or self.total_cap < 1
                or type(self.phase_cap) is not int or not 0 <= self.phase_cap <= self.total_cap
                or contract['per_slot_cap'] != 6):
            raise ValueError('frozen_phase_and_global_raster_caps')
        self.budget_root.mkdir(parents=True, exist_ok=True)
        from human_eye_plugin.verified_source_loader import current_guard
        self.guard = current_guard(self.product_root)
        if self.guard is None:
            raise ValueError('verified_installed_source_guard_required')
        self.guard.verify_loaded()
        import numpy as np
        import PIL
        from PIL import Image
        from human_eye_module1_operators import MeshEntity3D
        from human_eye_plugin import attention_raster
        self.np, self.Image = np, Image
        self.raster_module = attention_raster
        self.original_raster = attention_raster.rasterize_attention
        attention_raster.rasterize_attention = self._charged_raster
        for name in ('human_eye_plugin.attention_rendering', 'human_eye_plugin.active_observation_images'):
            module = sys.modules.get(name)
            if module is not None and getattr(module, 'rasterize_attention', None) is self.original_raster:
                module.rasterize_attention = self._charged_raster
        self.meshes, self.face_ids = [], []
        offset = 0
        for index, obj in enumerate(self.scene['objects']):
            vertices = np.asarray([[float(Fraction(value)) for value in point] for point in obj['vertices']], dtype=np.float64)
            faces = np.asarray(obj['triangles'], dtype=np.int32)
            mesh = MeshEntity3D(object_id='native-object-' + str(index), mark_label='object_' + str(index),
                name=obj['name'], vertices=vertices, faces=faces, edges=np.empty((0, 2), dtype=np.int32),
                color_rgb=SURFACE_COLOR, local_axes=np.eye(3), axes_source='world_geometry',
                axes_confidence='explicit', axes_reason='supplied_world_geometry')
            self.meshes.append(mesh)
            self.face_ids.append(np.arange(offset, offset + len(faces), dtype=np.int32))
            offset += len(faces)
            for array in (mesh.vertices, mesh.faces, mesh.edges, self.face_ids[-1]):
                array.setflags(write=False)
        self._frozen_mesh_order = self._mesh_order()
        self._frozen_face_order = tuple((id(values), tuple(values.shape)) for values in self.face_ids)
        save(self.output / 'DEPENDENCIES.json', dict(numpy_path=np.__file__, numpy_version=np.__version__,
            PIL_path=PIL.__file__, PIL_version=PIL.__version__, raster_path=attention_raster.__file__,
            raster_sha256=digest(Path(attention_raster.__file__).read_bytes()), product_source_sha256=PRODUCT_SOURCE_SHA256))
        self.service = None
        if self.group == 'P':
            from human_eye_plugin.live_service import LiveSpatialService
            from human_eye_plugin.live_spatial_mcp import _tool_result
            self.project_product = _tool_result
            service_config = dict(schema_version='1.0', project_root=str(self.product_root), enabled=True,
                observe_on_prompt=False, state_file=str(self.output / 'product_state.json'),
                audit_file=str(self.output / 'product_audit.jsonl'), request_budget_s=max(.001, (self.deadline_ns-time.perf_counter_ns())/1e9),
                expected_identity={key: self.binding[key] for key in
                    ('base_version', 'implementation_revision', 'build_id', 'source_sha256', 'protocol_version')})
            config_path = self.output / 'product_config.json'
            save(config_path, service_config)
            self.service = LiveSpatialService(config_path, host=ReplayHost(self, data['capture'][0]), production_mode=True)
            original_event = self.service.record_event

            def event(name, **fields):
                if name == 'active_observation_render_attempt':
                    self._render_view = fields['view_name']
                return original_event(name, **fields)

            self.service.record_event = event
        self.install_audit()
        self.stage('startup_shared_inputs_and_runtime', started)
        self.save()

    def check(self):
        check_deadline(self.deadline_ns)

    def stage(self, name, started, **fields):
        closed = time.perf_counter_ns()
        row = dict(name=name, started_ns=started, closed_ns=closed, elapsed_ns=closed-started, **fields)
        self.stages.append(row)
        return row

    def install_audit(self):
        helper = ROOT / 'verification/m4_active_coverage_consumption_001/image_content.py'
        common_product_sources = {'attention_raster.py', 'geometry_safety.py', 'verified_source_loader.py'}
        research_roots = tuple(path.resolve() for path in (
            ROOT, Path('D:/hefe'), Path('D:/he_loc_001'),
            Path('D:/he_explicit_001'), Path('D:/he_consume_001'),
            Path('D:/he_routed_001'),
            Path('D:/he_view_reuse_001'),
            Path('D:/he_complete_witness_001'),
            Path('C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe'),
            Path('D:/he_anchor_001/run'), Path('D:/he_patch_001/run')))

        def audit(event, arguments):
            if not self._consumer_running:
                return
            if event == 'exec':
                filename = Path(arguments[0].co_filename)
                if (filename.is_absolute() and filename.is_relative_to(self.product_root)
                        and filename.name not in common_product_sources):
                    self.audit['forbidden_product_calls'].append(dict(path=str(filename), operation='module_execution'))
                    raise PermissionError('consumer_uses_ordinary_Python_and_registered_tools')
                return
            if event != 'open' or not isinstance(arguments[0], (str, bytes, os.PathLike)):
                return
            path = Path(os.fsdecode(arguments[0])).resolve()
            mode, flags = arguments[1], arguments[2]
            writing = isinstance(mode, str) and any(value in mode for value in 'wax+')
            writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if self._budget_io and path.is_relative_to(self.budget_root):
                return
            private = path in self._private_paths or path.name.startswith('PRIVATE_REPLAY_')
            public_read = not writing and (path == helper or path in {
                Path(self.source_inputs['scene_path']), Path(self.source_inputs['cameras_path'])}
                or (path.is_relative_to(self.product_root) and path.name in common_product_sources))
            allowed = path.is_relative_to(self.output) or public_read
            unpublished_product = path.is_relative_to(self.product_root) and (
                writing or path.name not in common_product_sources)
            research_input = any(path.is_relative_to(root) for root in research_roots)
            blocked = private or unpublished_product or research_input and not allowed
            if blocked:
                key = 'forbidden_old_writes' if writing else 'forbidden_old_evidence_reads'
                rows = 'old_write_attempts' if writing else 'old_evidence_read_attempts'
                self.audit[key] += 1
                self.audit[rows].append(dict(path=str(path), mode=mode))
                raise PermissionError('consumer_private_or_administrator_input_forbidden')

        sys.addaudithook(audit)

    @contextlib.contextmanager
    def consumer_scope(self):
        self._consumer_running = True
        try:
            yield
        finally:
            self._consumer_running = False

    def reserve(self, view_name):
        self.check()
        if len(self.attempts) >= 6:
            raise RenderLimitError('six_actual_raster_attempt_limit')
        previous = []
        slots = sorted(self.budget_root.glob('attempt_*'))
        for slot in slots:
            try:
                previous.append(json.loads((slot / 'INTENT.json').read_bytes()))
            except (OSError, ValueError) as exc:
                raise RuntimeError('global_raster_ledger_unknown') from exc
        if [row['global_attempt'] for row in previous] != list(range(1, len(previous)+1)):
            raise RuntimeError('global_raster_ledger_unknown')
        if len(previous) >= self.total_cap or sum(row['phase'] == self.phase for row in previous) >= self.phase_cap:
            raise RuntimeError('shared_raster_budget_exhausted')
        ordinal = len(previous) + 1
        folder = self.budget_root / ('attempt_' + str(ordinal).zfill(2))
        folder.mkdir()
        row = dict(attempt_id=len(self.attempts)+1, global_attempt=ordinal, phase=self.phase,
            group=self.group, owner_output=str(self.output), process_id=os.getpid(),
            view_name=view_name, origin=self._render_origin, ref='image-' + str(len(self.attempts)+1).zfill(2),
            status='attempted', source_capture_sha256=self.source_inputs['capture_sha256'],
            source_scene_sha256=self.source_inputs['scene_sha256'], started_ns=time.perf_counter_ns())
        with (folder / 'INTENT.json').open('xb') as stream:
            stream.write(encoded(row))
            stream.flush()
            os.fsync(stream.fileno())
        self.attempts.append(row)
        self.trace.emit('render_attempt', durable=True, **row)
        self.save()
        return row

    def _charged_raster(self, *args, **kwargs):
        if self._render_origin not in ('native', 'product') or self._render_view not in self.poses:
            raise PermissionError('use_registered_frozen_scene_render_entry')
        self._budget_io = True
        try:
            row = self.reserve(self._render_view)
        finally:
            self._budget_io = False
        row['render_started_ns'] = time.perf_counter_ns()
        try:
            value = self.original_raster(*args, **kwargs)
            row.update(render_closed_ns=time.perf_counter_ns(), status='rendered',
                       raster_returned_array_payload_bytes=sum(array.nbytes for array in value))
            return value
        except BaseException as exc:
            row.update(status='failed', error=dict(type=type(exc).__name__, message=str(exc)))
            self.runtime_faults.append(dict(stage='raster', attempt_id=row['attempt_id'], **row['error']))
            raise
        finally:
            self.save()

    def _mesh_order(self):
        return tuple((mesh.object_id, mesh.name, id(mesh), id(mesh.vertices),
                      id(mesh.faces), tuple(mesh.vertices.shape), tuple(mesh.faces.shape))
                     for mesh in self.meshes)

    def _view_binding(self, name):
        """Use already-bound identities and a small camera specification only."""
        pose = self.poses[name]
        face_order = tuple((id(values), tuple(values.shape)) for values in self.face_ids)
        return (self.source_inputs['capture_sha256'], self.source_inputs['scene_sha256'],
                self.source_inputs['cameras_sha256'], PRODUCT_SOURCE_SHA256,
                self._mesh_order(), face_order, encoded(pose), self._owner_generation)

    def _register(self, row, png, npz, ref, arrays, *, frame_metadata=None):
        """Publish complete arrays and stable refs only after all file checks succeed."""
        details = dict(status='completed', completed_ns=time.perf_counter_ns(), ref=ref,
            PNG=str(png), PNG_bytes=png.stat().st_size, PNG_sha256=digest(png.read_bytes()),
            NPZ=str(npz), NPZ_bytes=npz.stat().st_size, NPZ_sha256=digest(npz.read_bytes()),
            array_payload_bytes=sum(value.nbytes for value in arrays.values()),
            arrays={key:dict(dtype=str(value.dtype), shape=list(value.shape), nbytes=int(value.nbytes),
                            sha256=digest(value.tobytes(order='C'))) for key,value in arrays.items()})
        if frame_metadata is not None:
            if (details['PNG_sha256'] != frame_metadata['image_sha256']
                    or details['NPZ_sha256'] != frame_metadata['arrays_sha256']):
                raise ValueError('product_frame_file_binding_changed')
        if ref in self.by_ref:
            raise ValueError('stable_frame_reference_already_registered')
        raw = arrays.get('triangle_ids')
        capable = (raw is not None and raw.dtype == self.np.dtype('int32')
                   and raw.shape == arrays['owners'].shape)
        for values in arrays.values():
            values.setflags(write=False)
        owner_schema = 'native-global-source-triangles-v1'
        owner_mapping_identity = None
        if frame_metadata is not None:
            owner_schema = frame_metadata.get('owner_schema', 'legacy-patch-owner')
            owner_mapping_identity = frame_metadata.get('owner_mapping_identity')
        details.update(buffer_key=ref, triangle_id_capability=capable,
                       owner_schema=owner_schema, owner_mapping_identity=owner_mapping_identity,
                       owner_capabilities={'triangle_ids': capable, 'patch_owners': 'patch_owners' in arrays},
                       triangle_id_scope=('zero-based-global-source-triangles-in-mesh-order' if capable else None))
        binding = self._view_binding(row['view_name'])
        row.update(details)
        row['_reuse_binding'] = binding
        self.by_ref[ref] = row
        self.by_view[row['view_name']] = row
        self.buffers[ref] = arrays
        self.buffers[row['view_name']] = arrays

    def public_frame(self, row, *, cached=False, reason='constructed', new_raster_attempts=1):
        return dict(ref=row['ref'], view=row['view_name'], size_px=[512,512], mimeType='image/png',
                    buffer_handle=row['ref'], buffer_key=row['ref'], latest_buffer_alias=row['view_name'],
                    status=row['status'], cached=cached, reuse_reason=reason,
                    new_raster_attempts=new_raster_attempts, triangle_id_capability=row['triangle_id_capability'],
                    owner_schema=row['owner_schema'], owner_mapping_identity=row['owner_mapping_identity'],
                    owner_capabilities=copy.deepcopy(row['owner_capabilities']), triangle_id_scope=row['triangle_id_scope'])

    def _record_cache_request(self, names, fresh, started, before, frames, *, status='completed', error=None):
        self.cache_requests.append(dict(names=list(names), fresh=fresh, started_ns=started,
            closed_ns=time.perf_counter_ns(), new_raster_attempts=len(self.attempts)-before,
            frames=copy.deepcopy(frames), status=status, error=error))
        self.save()

    def render_views(self, names, fresh=False):
        if not isinstance(names, (list,tuple)) or not names or any(name not in self.poses for name in names):
            raise ValueError('registered_camera_names_required')
        if type(fresh) is not bool:
            raise ValueError('fresh_boolean')
        frames = []
        requested = {}
        started = time.perf_counter_ns()
        before = len(self.attempts)
        current_sources = tuple(self.source_inputs[name + '_sha256']
                                for name in ('scene', 'cameras', 'capture', 'product_binding'))
        face_order = tuple((id(values), tuple(values.shape)) for values in self.face_ids)
        if (current_sources != self._frozen_source_ids or self._mesh_order() != self._frozen_mesh_order
                or face_order != self._frozen_face_order):
            self._record_cache_request(names, fresh, started, before, frames,
                status='rejected', error='source_or_object_order_changed_new_session_required')
            raise ValueError('source_or_object_order_changed_new_session_required')
        for name in names:
            if self.poses[name]['size_px'] != [512, 512]:
                self._record_cache_request(names, fresh, started, before, frames,
                    status='rejected', error='registered_512_camera_size_required')
                raise ValueError('registered_512_camera_size_required')
            if name in requested:
                frames.append(self.public_frame(requested[name], cached=True,
                                                reason='same_request_view', new_raster_attempts=0))
                continue
            existing = self.by_view.get(name)
            reason = 'explicit_fresh' if fresh else 'not_constructed'
            if not fresh and existing is not None:
                if existing.get('_reuse_binding') != self._view_binding(name):
                    reason = 'binding_changed'
                elif not existing.get('triangle_id_capability'):
                    reason = 'raw_triangle_capability_missing'
                else:
                    requested[name] = existing
                    frames.append(self.public_frame(existing, cached=True,
                                                    reason='current_bound_frame', new_raster_attempts=0))
                    continue
            self._render_origin, self._render_view = 'native', name
            try:
                pose = self.poses[name]
                color, depth, owners, triangles = self._charged_raster(self.meshes,
                    self.np.asarray(pose['view_matrix']), self.np.asarray(pose['projection_matrix']), 512,
                    return_owner=True, return_patch_owner=True, face_patch_ids=tuple(self.face_ids))
                row = self.attempts[-1]
                row['pose'] = copy.deepcopy(pose)
                arrays = dict(color=color, depth=depth, owners=owners, triangle_ids=triangles)
                folder = self.output / 'frames' / str(row['attempt_id']).zfill(2)
                folder.mkdir(parents=True)
                png, npz = folder / (name+'.png'), folder / (name+'.npz')
                with png.open('xb') as stream:
                    self.Image.fromarray(color, mode='RGB').save(stream,format='PNG')
                with npz.open('xb') as stream:
                    self.np.savez_compressed(stream,**arrays)
                self._register(row,png,npz,row['ref'],arrays)
                requested[name] = row
                frames.append(self.public_frame(row, reason=reason))
            except BaseException as error:
                if len(self.attempts) > before and self.attempts[-1].get('status') == 'rendered':
                    self.attempts[-1].update(status='postprocess_failed',
                        error=dict(type=type(error).__name__, message=str(error)))
                self._record_cache_request(names, fresh, started, before, frames, status='failed',
                    error=dict(type=type(error).__name__, message=str(error)))
                raise
            finally:
                self._render_origin = self._render_view = None
                self.save()
        self._record_cache_request(names, fresh, started, before, frames)
        return frames

    def image_specification(self, ref):
        row = self.by_ref.get(ref)
        if row is None or row['status'] != 'completed':
            raise ValueError('current_session_generated_image_reference_required')
        path = Path(row['PNG'])
        return dict(ref=ref,file=path.name,PNG_bytes=row['PNG_bytes'],sha256=row['PNG_sha256'],
                    width=512,height=512,mimeType='image/png'),path.parent

    def active_observation(self, include_images, on_constructed):
        if self.group != 'P':
            raise ValueError('product_observation_route_unavailable')
        self.check()
        call_index = len(self.product_calls)+1
        folder = self.output / ('product_call_'+str(call_index).zfill(2))
        folder.mkdir()
        row = dict(index=call_index,replay_label='CAPTURE_REPLAY',started_ns=time.perf_counter_ns(),
                   result_path=str(folder/'SERVICE_RESULT.json'))
        self.product_calls.append(row)
        before = len(self.attempts)
        self.service.request_budget_s=max(.001,(self.deadline_ns-time.perf_counter_ns())/1e9)
        self._render_origin = 'product'
        audit = {}
        raw = None
        result = None
        try:
            raw = self.service.observe('localization-current-slot',query={'mode':'active_observation'},include_image=include_images)
            row['producer_returned_ns']=time.perf_counter_ns()
            save(folder/'SERVICE_RESULT.json',raw)
            owner_bindings = {(frame.get('owner_schema', 'legacy-patch-owner'), frame.get('owner_mapping_identity'))
                              for frame in raw.get('frames', [])}
            if len(owner_bindings) > 1:
                raise ValueError('one_product_owner_generation_required')
            if owner_bindings:
                self._owner_generation = next(iter(owner_bindings))
            for frame in raw.get('frames',[]):
                matches=[entry for entry in self.attempts[before:] if entry['view_name']==frame['view_name']]
                if matches:
                    with self.np.load(frame['arrays_path'],allow_pickle=False) as archive:
                        arrays={key:archive[key] for key in archive.files}
                    self._register(matches[0],Path(frame['image_path']),Path(frame['arrays_path']),frame['image_ref'],arrays,
                                   frame_metadata=frame)
                    matches[0].update(pose=copy.deepcopy(frame['pose']),
                        patch_mapping_version=frame['patch_mapping_version'],
                        patch_mapping_identity=frame['patch_mapping_identity'],
                        patch_roi_ids=list(frame['patch_roi_ids']))
                else:
                    existing = self.by_ref.get(frame['image_ref'])
                    if existing is None:
                        raise ValueError('product_cache_reference_not_owned_by_this_slot')
                    if existing.get('_reuse_binding') != self._view_binding(frame['view_name']):
                        raise ValueError('product_cached_frame_binding_changed')
            result=self.project_product(raw,is_error=raw['status'] not in ('complete','predicted','unknown'),active_delivery_audit=audit)
            row.update(status='completed',closed_ns=time.perf_counter_ns(),work=raw.get('work'),
                       product_source_sha256=raw.get('binding',{}).get('runtime_source_sha256'))
            return result
        except BaseException as exc:
            row.update(status='failed',closed_ns=time.perf_counter_ns(),error=dict(type=type(exc).__name__,message=str(exc)),
                failed_product_work=getattr(exc,'active_observation_work',None),
                failed_product_stages=getattr(exc,'active_observation_stages',None))
            raise
        finally:
            self._render_origin = self._render_view = None
            row['delivery_audit']=audit
            if raw is not None:
                for index,item in enumerate(audit.get('frames',[])):
                    if item.get('status') != 'constructed':
                        continue
                    frame=raw['frames'][index]
                    block=None if result is None else result['content'][index+1]
                    receipt=dict(ref=frame['image_ref'],PNG_bytes_read=item['PNG_bytes_read'],
                        PNG_sha256=frame['image_sha256'],base64_chars=item['base64_chars'],
                        image_block_JSON_bytes=None if block is None else len(encoded(block))-1,
                        constructed=True,constructed_ns=audit['closed_ns'],delivery_ready=result is not None,
                        timestamp_scope='Product content bundle closure; individual construction instant unmeasured',
                        origin='product_mcp', stages=dict(read_ns=item.get('read_ns'),
                            validate_ns=item.get('validate_ns'), base64_ns=item.get('base64_ns')))
                    on_constructed(receipt)
            if audit.get('status') == 'failed':
                self.product_image_failures.append(dict(constructed=audit.get('native_blocks_constructed',0)>0,
                    product_call=call_index, audit=copy.deepcopy(audit)))
            save(folder/'CALL.json',row)
            self.save()

    def metrics(self):
        return dict(render_attempts=len(self.attempts),raster_completed=sum('render_closed_ns' in row for row in self.attempts),
            frames_completed=sum(row['status']=='completed' for row in self.attempts),
            PNG_bytes=sum(row.get('PNG_bytes',0) for row in self.attempts),NPZ_bytes=sum(row.get('NPZ_bytes',0) for row in self.attempts),
            array_payload_bytes=sum(row.get('array_payload_bytes',0) for row in self.attempts),
            max_render_attempts=6,capture_replay_calls=len(self.replays),actual_Blender_capture_calls=0,
            product_observation_calls=len(self.product_calls),Blender_processes=0,
            cache_requests=len(self.cache_requests),cache_hit_frames=sum(frame['cached'] for request in self.cache_requests for frame in request['frames']),
            array_payload_scope='Generated ndarray payload; RSS unmeasured')

    def save(self):
        attempts = [{key:value for key,value in row.items() if key != '_reuse_binding'} for row in self.attempts]
        return save(self.output/'OBSERVATIONS.json',dict(schema='view-reuse-observations-v1',
            process_id=os.getpid(),group=self.group,deadline_ns=self.deadline_ns,replay_label='CAPTURE_REPLAY',
            source_inputs=self.source_inputs,render_attempts=attempts,
            frames=[row for row in attempts if row['status']=='completed'],metrics=self.metrics(),cache_requests=self.cache_requests,
            stages=self.stages,active=self.product_calls,replays=self.replays,runtime_faults=self.runtime_faults,audit=self.audit))
