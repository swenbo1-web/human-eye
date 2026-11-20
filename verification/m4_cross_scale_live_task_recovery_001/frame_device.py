"""Give both arms the same raw capture and model-directed orthographic viewport."""

import copy
from pathlib import Path
import time

import numpy as np

from bridge import SOURCE_REGION, load


_base = load('_cross_scale_prior_frame_device', SOURCE_REGION / 'harness/frame_device.py')
PIXEL_CONVENTION = _base.PIXEL_CONVENTION
DIRECTIONS = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1), 'RIGHT': (1, 0, 1),
              'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}
SIZE = 512
PUBLIC_FRAME = ('ref', 'frame_identity', 'view', 'view_name', 'scope_id', 'direction_rational', 'pose', 'size_px',
                'camera_sha256', 'PNG_sha256', 'NPZ_sha256', 'source_ref', 'origin', 'object_names', 'object_ids',
                'object_instance_ids', 'source_face_offsets', 'display_object_mask', 'triangle_id_scope',
                'buffer_handle', 'status')


class FrameDevice(_base.FrameDevice):
    def __init__(self, runroot, asset_sha256, group, label, native_call, terminal_call=None,
                 budget=None, phase='formal', check=lambda: None):
        self.runroot = Path(runroot).resolve()
        self.asset_sha256, self.group, self.label, self.phase = asset_sha256, group, label, phase
        self.native_call, self.terminal_call = native_call, terminal_call or native_call
        self.budget, self.check = budget, check
        self.cameras = {'views': [{'name': name, 'direction': list(direction), 'direction_rational': list(direction)}
                                  for name, direction in DIRECTIONS.items()], 'pixel_convention': PIXEL_CONVENTION}
        self.camera = self.cameras
        self.pose = None
        self.buffers, self.by_ref, self.by_view, self._pose_refs = {}, {}, {}, {}
        self.events, self.source_reads = [], []
        self._native_counter = self._source_counter = 0
        self._scene = self._renderer = self._terminal_receipt = self._preferred_product_ref = None

    def _register(self, row, arrays):
        # Keep original low-level RGB/depth/owner consistency checks. The
        # multiple view scopes are identified by immutable refs, never aliases.
        view = row['view']
        old_view, old_buffer = self.by_view.get(view), self.buffers.get(view)
        super()._register(row, arrays)
        if old_view is None:
            self.by_view.pop(view, None)
            self.buffers.pop(view, None)
        else:
            self.by_view[view], self.buffers[view] = old_view, old_buffer

    def _fit(self, direction, target, span, scope_id):
        from human_eye_plugin.attention_rendering import _attention_camera

        started = time.perf_counter_ns()
        _, meshes, _ = self._prepare_raster()
        points = np.concatenate([mesh.vertices for mesh in meshes])
        rational = DIRECTIONS[direction]
        eye_direction = np.asarray(rational, dtype=np.float64)
        eye_direction /= np.linalg.norm(eye_direction)
        up_seed = np.array([0., 1., 0.]) if direction == 'TOP' else np.array([0., 0., 1.])
        if target is None:
            target = (points.min(axis=0) * .5 + points.max(axis=0) * .5).tolist()
            right = np.cross(-eye_direction, up_seed)
            right /= np.linalg.norm(right)
            up = np.cross(right, -eye_direction)
            span = 2.2 * float(np.abs((points - target) @ np.stack((right, up)).T).max())
        view, projection, eye, far = _attention_camera(meshes, {'target_world_m': target,
                    'view_span_m': span, 'direction': eye_direction, 'up': up_seed})
        if not (np.isfinite(view).all() and np.isfinite(projection).all() and np.isfinite(far)):
            raise ValueError('finite_orthographic_camera_required')
        pose = {'name': direction, 'size_px': [SIZE, SIZE], 'direction_rational': list(rational),
                'projection': 'orthographic', 'target_world_m': target, 'camera_eye_world_m': eye.tolist(),
                'view_span_m': span, 'near_m': .08, 'far_m': far, 'view_matrix': view.tolist(),
                'projection_matrix': projection.tolist(), 'scope_id': scope_id}
        self._record('native_camera_fit', view=direction, scope_id=scope_id, **_base._span(started))
        return pose

    def _frame(self, direction, target, span, fresh):
        key = (direction, None if target is None else tuple(target), span)
        scope_id = 'global' if target is None else 'local:' + _base._sha(_base._encode(key))
        ref = None if fresh else self._pose_refs.get(key)
        if ref is None:
            pose = self._fit(direction, target, span, scope_id)
            old_pose, old_camera = self.pose, self.camera
            self.pose = pose
            self.camera = {**self.cameras, 'camera_sha256': _base._sha(_base._encode(_base._view_key(pose)))}
            try:
                row = self._native_frame()
            finally:
                self.pose, self.camera = old_pose, old_camera
            ref = row['ref']
            row.update(view=direction, view_name=direction, scope_id=scope_id,
                       direction_rational=pose['direction_rational'])
            row.pop('fixed_camera_matches', None)
            self._pose_refs[key] = ref
            cached = False
        else:
            row = self.by_ref[ref]
            self._record('frame_cache_hit', ref=ref, origin='common_native', requested_by='native_camera')
            cached = True
        return {**{k: copy.deepcopy(row[k]) for k in PUBLIC_FRAME}, 'cached': cached,
                'new_raster_attempts': int(not cached)}

    def render_views(self, names, fresh=False):
        self.check()
        if (type(names) not in (list, tuple) or not 1 <= len(names) <= 6
                or any(type(name) is not str or name not in DIRECTIONS for name in names)
                or type(fresh) is not bool):
            raise ValueError('one_to_six_registered_view_names_and_fresh_boolean_required')
        try:
            frames = [self._frame(direction, None, None, fresh) for direction in names]
            self.check()
            return frames
        finally:
            self.save_evidence()

    def render_local(self, direction, target_world_m, view_span_m, fresh=False):
        self.check()
        if (type(direction) is not str or direction not in DIRECTIONS or type(fresh) is not bool
                or type(target_world_m) not in (list, tuple) or len(target_world_m) != 3
                or any(type(value) not in (int, float) for value in target_world_m)
                or type(view_span_m) not in (int, float)):
            raise ValueError('registered_direction_finite_three_component_target_and_positive_span_required')
        target, span = list(map(float, target_world_m)), float(view_span_m)
        if not np.isfinite(target).all() or not np.isfinite(span) or span <= 0:
            raise ValueError('finite_local_target_and_positive_span_required')
        try:
            frame = self._frame(direction, target, span, fresh)
            self.check()
            return frame
        finally:
            self.save_evidence()

    def adopt_product_result(self, full, entry=None):
        """Reuse same-slot producer image refs and arrays, retaining each scope."""
        self.check()
        if self.group != 'P':
            raise ValueError('product_frame_requires_product_slot')
        if full.get('result_kind') not in ('active_observation', 'source_region') or not full.get('frames'):
            return []
        scopes = {scope['scope_id']: scope['binding'] for scope in full.get('scopes', [])}
        retained = []
        try:
            for frame in full['frames']:
                ref = frame['image_ref']
                scope_id = frame.get('scope_id', 'global')
                existing = self.by_ref.get(ref)
                if existing is not None:
                    if (frame['frame_identity'], frame['image_sha256'], frame['arrays_sha256']) != (
                        existing['frame_identity'], existing['PNG_sha256'], existing['NPZ_sha256']):
                        raise ValueError('producer_frame_reuse_identity_mismatch')
                    self._record('frame_cache_hit', ref=ref, origin='product', requested_by='product_read')
                    retained.append(ref)
                    continue
                started = time.perf_counter_ns()
                binding = scopes.get(scope_id, full['binding'])
                if frame.get('host_binding_sha256') != binding['binding_sha256']:
                    raise ValueError('original_producer_frame_scope_binding_mismatch')
                png, npz = (Path(frame[key]).resolve() for key in ('image_path', 'arrays_path'))
                if not (png.is_relative_to(self.runroot) and npz.is_relative_to(self.runroot)):
                    raise ValueError('producer_frame_outside_current_slot')
                png_sha, npz_sha = _base._sha(png.read_bytes()), _base._sha(npz.read_bytes())
                if (png_sha, npz_sha) != (frame['image_sha256'], frame['arrays_sha256']):
                    raise ValueError('original_producer_frame_hash_mismatch')
                objects = sorted(binding['objects'], key=lambda row: row['object_index'])
                if [obj['object_index'] for obj in objects] != list(range(len(objects))):
                    raise ValueError('complete_producer_frame_mesh_order_required')
                with np.load(npz, allow_pickle=False) as archive:
                    arrays = {name: archive[name] for name in _base.BUFFER_NAMES}
                    offsets = archive['face_patch_offsets'].tolist()
                    mask = binding.get('image_scope', {}).get('participation_mask', [True] * len(objects))
                    if 'display_object_mask' in archive and archive['display_object_mask'].tolist() != mask:
                        raise ValueError('producer_archive_and_display_binding_mismatch')
                pose = frame['pose']
                if frame['view_name'] != pose['name']:
                    raise ValueError('producer_frame_camera_name_mismatch')
                row = {'ref': ref, 'frame_identity': frame['frame_identity'], 'origin': 'product',
                       'view': frame['view_name'], 'view_name': frame['view_name'], 'scope_id': scope_id,
                       'pose': copy.deepcopy(pose), 'size_px': pose['size_px'],
                       'direction_rational': pose.get('direction_rational'),
                       'camera_sha256': frame.get('camera_identity') or _base._sha(_base._encode(_base._view_key(pose))),
                       'PNG': str(png), 'NPZ': str(npz), 'PNG_sha256': png_sha, 'NPZ_sha256': npz_sha,
                       'PNG_bytes': png.stat().st_size, 'NPZ_bytes': npz.stat().st_size,
                       'source_ref': 'product-binding:' + frame['host_binding_sha256'],
                       'object_names': [obj['object_name'] for obj in objects],
                       'object_ids': [obj['host_id'] for obj in objects],
                       'object_instance_ids': [obj['instance_id'] for obj in objects],
                       'source_face_offsets': offsets, 'display_object_mask': mask,
                       'producer': copy.deepcopy(frame), 'full_result': copy.deepcopy(entry),
                       'stages': copy.deepcopy(frame.get('stages', {}))}
                self._register(row, arrays)
                self._record('original_product_frame_adopted', ref=ref, scope_id=scope_id,
                             PNG_bytes=row['PNG_bytes'], NPZ_bytes=row['NPZ_bytes'], **_base._span(started))
                retained.append(ref)
            self.check()
            return retained
        finally:
            self.save_evidence()
