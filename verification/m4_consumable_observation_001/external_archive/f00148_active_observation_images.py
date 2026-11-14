"""Actual full-scene image feedback for finite active observation.

Mesh arrays come from the session's already normalized world geometry. Every
object participates in the same RGB, depth and owner raster. Frame feedback
uses the current canonical rectangular regions and commits through the
session's coverage state.
"""

from __future__ import annotations

import copy
import hashlib
from io import BytesIO
from pathlib import Path
import time

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D

from .active_observation import ActiveObservationSession, fingerprint
from .attention_raster import rasterize_attention
from .attention_rendering import _contrasting_boundaries


SURFACE_COLOR_RGB = (180, 190, 205)
PATCH_MAPPING_VERSION = 'active-patch-owner-v1'
_PATCH_METADATA_KEYS = ('patch_mapping_version', 'patch_mapping_identity', 'patch_roi_ids',
                        'face_patch_ids', 'face_patch_offsets')


def _meshes_from_objects(objects):
    meshes = []
    for index, (vertices, faces, key, name) in enumerate(objects):
        mesh = MeshEntity3D(
            object_id='geometry:' + fingerprint(key),
            mark_label='geometry_' + str(index),
            name=name,
            vertices=np.asarray(vertices, dtype=np.float64),
            faces=np.asarray(faces, dtype=np.int32),
            edges=np.empty((0, 2), dtype=np.int32),
            color_rgb=SURFACE_COLOR_RGB,
            local_axes=np.eye(3, dtype=np.float64),
            axes_source='world_geometry',
            axes_confidence='explicit',
            axes_reason='world_coordinates_no_transform',
        )
        for values in (mesh.vertices, mesh.faces, mesh.edges):
            values.setflags(write=False)
        meshes.append(mesh)
    if len({mesh.object_id for mesh in meshes}) != len(meshes):
        raise ValueError('geometry_identity_collision_requires_explicit_instance_identity')
    return tuple(meshes)


def _size(pose):
    dimensions = pose['size_px']
    if (len(dimensions) != 2 or dimensions[0] != dimensions[1]
            or type(dimensions[0]) is not int or not 64 <= dimensions[0] <= 512):
        raise ValueError('square_attention_frame_size_required')
    return dimensions[0]


def _array_metadata(values):
    return {
        'dtype': str(values.dtype),
        'shape': list(values.shape),
        'nbytes': int(values.nbytes),
        'sha256': hashlib.sha256(values.tobytes(order='C')).hexdigest(),
    }


def _validate_buffers(buffers, size, object_count):
    color, depth, owners = (np.asarray(buffers[key]) for key in ('color', 'depth', 'owners'))
    if (color.shape != (size, size, 3) or color.dtype != np.uint8
            or depth.shape != (size, size) or depth.dtype != np.float64
            or owners.shape != (size, size) or owners.dtype != np.int32):
        raise ValueError('RGB_depth_owner_frame_arrays_required')
    background = owners == -1
    foreground = ~background
    if (np.any(owners < -1) or np.any(owners >= object_count)
            or not np.all(np.isposinf(depth[background]))
            or not np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0))):
        raise ValueError('common_depth_owner_consistency_required')
    return {'color': color, 'depth': depth, 'owners': owners}


def _patch_mapping(objects, regions):
    roi_ids = tuple(region.roi_id for region in regions)
    if roi_ids != tuple(sorted(set(roi_ids))):
        raise ValueError('stable_unique_patch_order_required')
    face_ids = [np.full(len(source[1]), -1, dtype=np.int32) for source in objects]
    for patch_index, region in enumerate(regions):
        values = face_ids[region.object_index]
        for face_index in region.triangle_indices:
            if not 0 <= face_index < len(values) or values[face_index] != -1:
                raise ValueError('patch_triangle_mapping_must_be_unique')
            values[face_index] = patch_index
    identity = fingerprint({'version': PATCH_MAPPING_VERSION, 'roi_ids': roi_ids,
                            'ordered_geometry': [(source[0], source[1]) for source in objects],
                            'face_patch_ids': [values.tolist() for values in face_ids]})
    offsets = np.zeros(len(objects) + 1, dtype=np.int64)
    np.cumsum([len(source[1]) for source in objects], out=offsets[1:])
    arrays = {'patch_mapping_version': np.asarray(PATCH_MAPPING_VERSION),
              'patch_mapping_identity': np.asarray(identity),
              'patch_roi_ids': np.asarray(roi_ids, dtype=str),
              'face_patch_ids': np.concatenate(face_ids) if face_ids else np.empty(0, dtype=np.int32),
              'face_patch_offsets': offsets}
    for values in (*face_ids, *arrays.values()):
        values.setflags(write=False)
    return {'identity': identity, 'roi_ids': roi_ids, 'face_ids': tuple(face_ids),
            'roi_object_indices': np.asarray([region.object_index for region in regions], dtype=np.int32),
            'arrays': arrays}


def _validated_patch_buffers(buffers, size, object_count, mapping):
    validated = _validate_buffers(buffers, size, object_count)
    owners = validated['owners']
    if 'patch_owners' in buffers:
        patches = np.asarray(buffers['patch_owners'])
    else:
        # Historical three-buffer evidence is sufficient only where an object
        # has one whole-object patch. Multiple/partial patches need true winners.
        object_patch = np.full(object_count, -1, dtype=np.int32)
        for object_index, face_ids in enumerate(mapping['face_ids']):
            ids = np.unique(face_ids)
            if len(ids) > 1:
                raise ValueError('patch_owner_frame_required_for_multiple_or_partial_patches')
            if len(ids):
                object_patch[object_index] = ids[0]
        patches = np.full(owners.shape, -1, dtype=np.int32)
        foreground = owners >= 0
        patches[foreground] = object_patch[owners[foreground]]
    if patches.shape != (size, size) or patches.dtype != np.int32:
        raise ValueError('int32_patch_owner_frame_required')
    assigned = patches >= 0
    if (np.any(patches < -1) or np.any(patches >= len(mapping['roi_ids']))
            or np.any(patches[owners == -1] != -1)
            or np.any(mapping['roi_object_indices'][patches[assigned]] != owners[assigned])):
        raise ValueError('common_depth_patch_owner_consistency_required')
    validated['patch_owners'] = patches
    return validated


def _aggregate_patch_pixels(color, patch_owners, region_count, *, include_locations=False,
                            _localization_stages=None):
    """Share patch counts, with optional bounds and actual owned-pixel anchors."""
    patches = np.asarray(patch_owners)
    if (type(include_locations) is not bool or type(region_count) is not int
            or region_count < 0 or patches.dtype != np.int32
            or patches.ndim != 2 or np.any(patches < -1) or np.any(patches >= region_count)):
        raise ValueError('bounded_patch_owner_ids_required')
    boundary = _contrasting_boundaries(color, patches)
    foreground = patches >= 0
    surface_ids = patches[foreground]
    boundary_ids = patches[boundary & foreground]
    result = {'visible_surface_pixels': np.bincount(surface_ids, minlength=region_count),
              'contrasting_boundary_pixels': np.bincount(boundary_ids, minlength=region_count)}
    if not include_locations:
        return result
    started = time.perf_counter_ns() if _localization_stages is not None else None
    height, width = patches.shape
    flat = np.flatnonzero(foreground)
    y, x = np.divmod(flat, width)
    xmin = np.full(region_count, width, dtype=np.int64)
    ymin = np.full(region_count, height, dtype=np.int64)
    xmax = np.full(region_count, -1, dtype=np.int64)
    ymax = np.full(region_count, -1, dtype=np.int64)
    np.minimum.at(xmin, surface_ids, x)
    np.minimum.at(ymin, surface_ids, y)
    np.maximum.at(xmax, surface_ids, x)
    np.maximum.at(ymax, surface_ids, y)
    dx = 2 * x - xmin[surface_ids] - xmax[surface_ids]
    dy = 2 * y - ymin[surface_ids] - ymax[surface_ids]
    distance = dx * dx + dy * dy
    best_distance = np.full(region_count, np.iinfo(np.int64).max, dtype=np.int64)
    np.minimum.at(best_distance, surface_ids, distance)
    nearest = distance == best_distance[surface_ids]
    nearest_ids = surface_ids[nearest]
    nearest_flat = flat[nearest]
    anchor_flat = np.full(region_count, height * width, dtype=np.int64)
    np.minimum.at(anchor_flat, nearest_ids, nearest_flat)
    bounds, anchors = [], []
    for index, count in enumerate(result['visible_surface_pixels']):
        if count:
            bounds.append([int(xmin[index]), int(ymin[index]), int(xmax[index]), int(ymax[index])])
            anchors.append([int(anchor_flat[index] % width), int(anchor_flat[index] // width)])
        else:
            bounds.append(None)
            anchors.append(None)
    result['visible_pixel_bounds'] = bounds
    result['visible_pixel_anchor'] = anchors
    if _localization_stages is not None:
        closed = time.perf_counter_ns()
        _localization_stages['pixel_localization'] = {
            'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started,
            'named_temporary_array_bytes': sum(values.nbytes for values in (
                flat, x, y, xmin, ymin, xmax, ymax, dx, dy, distance,
                best_distance, nearest, nearest_ids, nearest_flat, anchor_flat)),
            'temporary_array_scope': 'Named localization arrays only, excluding transient NumPy internals and shared count arrays. Process RSS is unmeasured.',
            'new_cached_array_bytes': 0,
        }
    return result


def _pixel_rows(meshes, pose, buffers, regions, *, _localization_stages=None):
    direction = np.asarray(pose['target_to_eye_unit'], dtype=np.float64)
    counts = _aggregate_patch_pixels(buffers['color'], buffers['patch_owners'], len(regions),
                                     include_locations=True, _localization_stages=_localization_stages)
    rows = []
    for index, region in enumerate(regions):
        mesh = meshes[region.object_index]
        front = bool(np.asarray(region.normal, dtype=np.float64) @ direction > 0)
        surface = int(counts['visible_surface_pixels'][index])
        boundary = int(counts['contrasting_boundary_pixels'][index])
        rows.append({
            'roi_id': region.roi_id,
            'object_index': region.object_index,
            'view': pose['name'],
            'front_facing': front,
            'visible_surface_pixels': surface,
            'contrasting_boundary_pixels': boundary,
            'visible_pixel_bounds': counts['visible_pixel_bounds'][index],
            'visible_pixel_anchor': counts['visible_pixel_anchor'][index],
            'readable': front and surface >= 16 and boundary >= 4,
            'triangle_indices': list(region.triangle_indices),
            'source_vertices': len(mesh.vertices),
            'source_triangles': len(mesh.faces),
            'minimum_surface_pixels': 16,
            'minimum_boundary_pixels': 4,
            'minimum_rgb_boundary_contrast': 24,
        })
    return rows


class ActiveObservationImages:
    """Own full meshes and current-source frames for one observation session.

    ``render_view`` and ``render_next`` return frame dictionaries containing
    PNG/NPZ paths, source identities, an image reference and in-process buffers.
    ``observe_frame`` also accepts saved frames with ``arrays_path`` and
    ``arrays_sha256`` in place of buffers. Owner indices follow the session's
    complete object order. Application serialization can omit ``buffers`` and
    retain the saved array reference.
    """

    def __init__(self, session, output_directory, *, _prepared_meshes=None, _measure_stages=False):
        if not isinstance(session, ActiveObservationSession):
            raise TypeError('active_observation_session_required')
        self.session = session
        self.output_directory = Path(output_directory).resolve()
        self._objects = None
        self._cameras = None
        self._binding = None
        self._frames = {}
        self._sequence = 0
        self._prepared_meshes = _prepared_meshes
        self._measure_stages = _measure_stages
        self._synchronize()

    def _synchronize(self):
        binding = (self.session.scene_identity, self.session.candidate_identity)
        if (binding == self._binding and self.session.objects is self._objects
                and self.session.cameras is self._cameras):
            return
        mesh_order_identity = fingerprint(tuple(item[2] for item in self.session.objects))
        mapping = _patch_mapping(self.session.objects, self.session.regions)
        reuse_frames = (binding == self._binding
                        and mesh_order_identity == getattr(self, '_mesh_order_identity', None)
                        and mapping['identity'] == getattr(self, '_patch_mapping_identity', None)
                        and self.session.cameras == self._cameras)
        if self._prepared_meshes is None:
            self.meshes = _meshes_from_objects(self.session.objects)
        else:
            objects, meshes = self._prepared_meshes
            if (objects is not self.session.objects or type(meshes) is not tuple
                    or len(meshes) != len(objects) or any(
                        len(mesh.vertices) != len(source[0]) or len(mesh.faces) != len(source[1])
                        for mesh, source in zip(meshes, objects))):
                raise ValueError('prepared_mesh_geometry_binding_required')
            self.meshes = meshes
            self._prepared_meshes = None
        self._poses = {pose['name']: pose for pose in self.session.cameras['views']}
        self._mesh_order_identity = mesh_order_identity
        self._patch_mapping = mapping
        self._patch_mapping_identity = mapping['identity']
        self._objects = self.session.objects
        self._cameras = self.session.cameras
        self._binding = binding
        self.session.state.bind_patch_mapping(self._patch_mapping_identity)
        if not reuse_frames:
            self._frames.clear()

    def render_next(self):
        self._synchronize()
        name = self.session.next_view()
        return None if name is None else self.render_view(name)

    def render_view(self, view_name):
        self._synchronize()
        if view_name not in self._poses:
            raise ValueError('unknown_observation_view')
        if view_name in self._frames:
            return self._frames[view_name]
        pose = self._poses[view_name]
        size = _size(pose)
        self._sequence += 1
        stages = {}
        if self._measure_stages:
            started = time.perf_counter_ns()
        raster = rasterize_attention(
            self.meshes,
            np.asarray(pose['view_matrix'], dtype=np.float64),
            np.asarray(pose['projection_matrix'], dtype=np.float64),
            size,
            return_owner=True,
            return_patch_owner=True,
            face_patch_ids=self._patch_mapping['face_ids'],
        )
        if self._measure_stages:
            closed = time.perf_counter_ns()
            stages['actual_raster'] = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
        if len(raster) not in (3, 4):
            raise ValueError('common_depth_owner_raster_result_required')
        buffers = dict(zip(('color', 'depth', 'owners', 'patch_owners'), raster))
        buffers = _validated_patch_buffers(buffers, size, len(self.meshes), self._patch_mapping)
        color = buffers['color']
        for values in buffers.values():
            values.setflags(write=False)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        stem = str(self._sequence).zfill(3) + '-' + fingerprint((self._binding, self._patch_mapping_identity, view_name))[:24]
        png = self.output_directory / (stem + '.png')
        arrays = self.output_directory / (stem + '.npz')
        if self._measure_stages:
            started = time.perf_counter_ns()
        with png.open('xb') as stream:
            Image.fromarray(color, mode='RGB').save(stream, format='PNG')
        with arrays.open('xb') as stream:
            np.savez_compressed(stream, **buffers, **self._patch_mapping['arrays'])
        if self._measure_stages:
            closed = time.perf_counter_ns()
            stages['PNG_NPZ_publication'] = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
            started = closed
        image_sha = hashlib.sha256(png.read_bytes()).hexdigest()
        frame = {
            'scene_identity': self._binding[0],
            'candidate_identity': self._binding[1],
            'mesh_order_identity': self._mesh_order_identity,
            'patch_mapping_version': PATCH_MAPPING_VERSION,
            'patch_mapping_identity': self._patch_mapping_identity,
            'patch_roi_ids': list(self._patch_mapping['roi_ids']),
            'view_name': view_name,
            'pose': copy.deepcopy(pose),
            'image_path': str(png),
            'image_sha256': image_sha,
            'image_ref': 'active-image:' + fingerprint((self._binding, self._patch_mapping_identity, view_name, image_sha)),
            'PNG_bytes': png.stat().st_size,
            'arrays_path': str(arrays),
            'arrays_sha256': hashlib.sha256(arrays.read_bytes()).hexdigest(),
            'compressed_array_file_bytes': arrays.stat().st_size,
            'arrays': {name: _array_metadata(values) for name, values in
                       {**buffers, **self._patch_mapping['arrays']}.items()},
            'array_payload_bytes': sum(values.nbytes for values in buffers.values())
                                   + sum(values.nbytes for values in self._patch_mapping['arrays'].values()),
            'patch_owner_array_bytes': buffers['patch_owners'].nbytes,
            'patch_mapping_array_bytes': sum(values.nbytes for values in self._patch_mapping['arrays'].values()),
            'buffers': buffers,
            'all_object_count': len(self.meshes),
            'all_triangle_count': sum(len(mesh.faces) for mesh in self.meshes),
        }
        if self._measure_stages:
            closed = time.perf_counter_ns()
            stages['frame_metadata'] = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
            frame['stages'] = stages
        self._frames[view_name] = frame
        return frame

    def observe_frame(self, frame):
        stages = {}
        if self._measure_stages:
            started = time.perf_counter_ns()
        self._synchronize()
        if (frame.get('scene_identity'), frame.get('candidate_identity')) != self._binding:
            raise ValueError('current_scene_camera_frame_required')
        name = frame['view_name']
        if name not in self._poses:
            raise ValueError('unknown_observation_view')
        pose = self._poses[name]
        if (frame.get('mesh_order_identity', self._mesh_order_identity) != self._mesh_order_identity
                or 'pose' in frame and frame['pose'] != pose):
            raise ValueError('current_frame_geometry_camera_binding_required')
        buffers = frame.get('buffers')
        if 'arrays_path' in frame:
            arrays_raw = Path(frame['arrays_path']).read_bytes()
            if hashlib.sha256(arrays_raw).hexdigest() != frame['arrays_sha256']:
                raise ValueError('actual_frame_array_bytes_required')
            with np.load(BytesIO(arrays_raw), allow_pickle=False) as arrays:
                stored = {key: arrays[key] for key in ('color', 'depth', 'owners')}
                if 'patch_owners' in arrays:
                    stored['patch_owners'] = arrays['patch_owners']
                    for key in _PATCH_METADATA_KEYS:
                        expected = self._patch_mapping['arrays'][key]
                        if key not in arrays or arrays[key].dtype != expected.dtype or not np.array_equal(arrays[key], expected):
                            raise ValueError('saved_patch_mapping_mismatch')
                elif any(key in arrays for key in _PATCH_METADATA_KEYS):
                    raise ValueError('saved_patch_owner_missing')
            if buffers is not None:
                for key, values in stored.items():
                    supplied = np.asarray(buffers[key])
                    if supplied.dtype != values.dtype or not np.array_equal(supplied, values):
                        raise ValueError('frame_array_payload_mismatch')
            buffers = stored
        if buffers is None:
            raise ValueError('actual_frame_buffers_required')
        if 'patch_owners' in buffers:
            if (frame.get('patch_mapping_version') != PATCH_MAPPING_VERSION
                    or frame.get('patch_mapping_identity') != self._patch_mapping_identity
                    or frame.get('patch_roi_ids') != list(self._patch_mapping['roi_ids'])):
                raise ValueError('current_patch_mapping_frame_required')
        elif any(key in frame for key in ('patch_mapping_version', 'patch_mapping_identity', 'patch_roi_ids')):
            raise ValueError('declared_patch_owner_frame_required')
        buffers = _validated_patch_buffers(buffers, _size(pose), len(self.meshes), self._patch_mapping)
        raw = Path(frame['image_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != frame['image_sha256']:
            raise ValueError('actual_PNG_bytes_required')
        with Image.open(BytesIO(raw)) as image:
            if (image.format != 'PNG' or image.mode != 'RGB'
                    or image.size != (_size(pose), _size(pose))
                    or not np.array_equal(np.asarray(image), buffers['color'])):
                raise ValueError('PNG_RGB_frame_array_binding_required')
        if self._measure_stages:
            closed = time.perf_counter_ns()
            stages['load_validate'] = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
            started = closed
        rows = _pixel_rows(self.meshes, pose, buffers, self.session.regions,
                           _localization_stages=stages if self._measure_stages else None)
        if self._measure_stages:
            closed = time.perf_counter_ns()
            stages['readability'] = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
            started = closed
        receipt = {
            'scene_identity': self._binding[0],
            'candidate_identity': self._binding[1],
            'view_name': name,
            'actual_image_delivered': True,
            'image_path': str(Path(frame['image_path']).resolve()),
            'image_sha256': frame['image_sha256'],
            'image_ref': frame.get('image_ref') or 'active-image:' + fingerprint(
                (self._binding, self._patch_mapping_identity, name, frame['image_sha256']),
            ),
            'patch_mapping_version': PATCH_MAPPING_VERSION,
            'patch_mapping_identity': self._patch_mapping_identity,
            'patch_roi_ids': list(self._patch_mapping['roi_ids']),
            'pixel_evidence_scope': 'actual_common_depth_owner',
            'readable_roi_ids': sorted(row['roi_id'] for row in rows if row['readable']),
            'pixel_rows': rows,
        }
        update = self.session.observe(receipt)
        result = {'receipt': receipt, 'pixel_rows': rows, 'update': update, 'summary': self.session.summary()}
        if self._measure_stages:
            closed = time.perf_counter_ns()
            stages['state_commit'] = {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}
            result['stages'] = stages
        return result


__all__ = ['ActiveObservationImages']
