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

import numpy as np
from PIL import Image

from human_eye_module1_operators import MeshEntity3D

from .active_observation import ActiveObservationSession, fingerprint
from .attention_raster import rasterize_attention
from .attention_rendering import _readability_evidence


SURFACE_COLOR_RGB = (180, 190, 205)


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


def _pixel_rows(meshes, pose, buffers, regions):
    view = np.asarray(pose['view_matrix'], dtype=np.float64)
    projection = np.asarray(pose['projection_matrix'], dtype=np.float64)
    direction = np.asarray(pose['target_to_eye_unit'], dtype=np.float64)
    size = _size(pose)
    rows = []
    for region in regions:
        mesh = meshes[region.object_index]
        corners = np.asarray(region.vertices, dtype=np.float64)
        camera = corners @ view[:3, :3].T + view[:3, 3]
        ndc = camera @ projection[:3, :3].T + projection[:3, 3]
        pixels = (ndc[:, :2] + 1) * (size - 1) / 2
        front = bool(np.asarray(region.normal, dtype=np.float64) @ direction > 0)
        evidence = _readability_evidence(
            buffers['color'], buffers['owners'], meshes, (mesh.object_id,), pixels,
        )
        rows.append({
            'roi_id': region.roi_id,
            'object_index': region.object_index,
            'view': pose['name'],
            'front_facing': front,
            'visible_surface_pixels': evidence['visible_surface_pixels'][0],
            'contrasting_boundary_pixels': evidence['contrasting_boundary_pixels'][0],
            'readable': front and evidence['passed'],
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

    def __init__(self, session, output_directory):
        if not isinstance(session, ActiveObservationSession):
            raise TypeError('active_observation_session_required')
        self.session = session
        self.output_directory = Path(output_directory).resolve()
        self._objects = None
        self._cameras = None
        self._binding = None
        self._frames = {}
        self._sequence = 0
        self._synchronize()

    def _synchronize(self):
        binding = (self.session.scene_identity, self.session.candidate_identity)
        if (binding == self._binding and self.session.objects is self._objects
                and self.session.cameras is self._cameras):
            return
        mesh_order_identity = fingerprint(tuple(item[2] for item in self.session.objects))
        reuse_frames = (binding == self._binding
                        and mesh_order_identity == getattr(self, '_mesh_order_identity', None)
                        and self.session.cameras == self._cameras)
        self.meshes = _meshes_from_objects(self.session.objects)
        self._poses = {pose['name']: pose for pose in self.session.cameras['views']}
        self._mesh_order_identity = mesh_order_identity
        self._objects = self.session.objects
        self._cameras = self.session.cameras
        self._binding = binding
        if not reuse_frames:
            self._frames.clear()

    def render_next(self):
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
        color, depth, owners = rasterize_attention(
            self.meshes,
            np.asarray(pose['view_matrix'], dtype=np.float64),
            np.asarray(pose['projection_matrix'], dtype=np.float64),
            size,
            return_owner=True,
        )
        buffers = {'color': color, 'depth': depth, 'owners': owners}
        for values in buffers.values():
            values.setflags(write=False)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        stem = str(self._sequence).zfill(3) + '-' + fingerprint((self._binding, view_name))[:24]
        png = self.output_directory / (stem + '.png')
        arrays = self.output_directory / (stem + '.npz')
        with png.open('xb') as stream:
            Image.fromarray(color, mode='RGB').save(stream, format='PNG')
        with arrays.open('xb') as stream:
            np.savez_compressed(stream, **buffers)
        image_sha = hashlib.sha256(png.read_bytes()).hexdigest()
        frame = {
            'scene_identity': self._binding[0],
            'candidate_identity': self._binding[1],
            'mesh_order_identity': self._mesh_order_identity,
            'view_name': view_name,
            'pose': copy.deepcopy(pose),
            'image_path': str(png),
            'image_sha256': image_sha,
            'image_ref': 'active-image:' + fingerprint((self._binding, view_name, image_sha)),
            'PNG_bytes': png.stat().st_size,
            'arrays_path': str(arrays),
            'arrays_sha256': hashlib.sha256(arrays.read_bytes()).hexdigest(),
            'compressed_array_file_bytes': arrays.stat().st_size,
            'arrays': {name: _array_metadata(values) for name, values in buffers.items()},
            'array_payload_bytes': sum(values.nbytes for values in buffers.values()),
            'buffers': buffers,
            'all_object_count': len(self.meshes),
            'all_triangle_count': sum(len(mesh.faces) for mesh in self.meshes),
        }
        self._frames[view_name] = frame
        return frame

    def observe_frame(self, frame):
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
            if buffers is not None:
                for key, values in stored.items():
                    supplied = np.asarray(buffers[key])
                    if supplied.dtype != values.dtype or not np.array_equal(supplied, values):
                        raise ValueError('frame_array_payload_mismatch')
            buffers = stored
        if buffers is None:
            raise ValueError('actual_frame_buffers_required')
        buffers = _validate_buffers(buffers, _size(pose), len(self.meshes))
        raw = Path(frame['image_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != frame['image_sha256']:
            raise ValueError('actual_PNG_bytes_required')
        with Image.open(BytesIO(raw)) as image:
            if (image.format != 'PNG' or image.mode != 'RGB'
                    or image.size != (_size(pose), _size(pose))
                    or not np.array_equal(np.asarray(image), buffers['color'])):
                raise ValueError('PNG_RGB_frame_array_binding_required')
        rows = _pixel_rows(self.meshes, pose, buffers, self.session.regions)
        receipt = {
            'scene_identity': self._binding[0],
            'candidate_identity': self._binding[1],
            'view_name': name,
            'actual_image_delivered': True,
            'image_path': str(Path(frame['image_path']).resolve()),
            'image_sha256': frame['image_sha256'],
            'image_ref': frame.get('image_ref') or 'active-image:' + fingerprint(
                (self._binding, name, frame['image_sha256']),
            ),
            'pixel_evidence_scope': 'actual_common_depth_owner',
            'readable_roi_ids': sorted(row['roi_id'] for row in rows if row['readable']),
            'pixel_rows': rows,
        }
        update = self.session.observe(receipt)
        return {'receipt': receipt, 'pixel_rows': rows, 'update': update, 'summary': self.session.summary()}


__all__ = ['ActiveObservationImages']
