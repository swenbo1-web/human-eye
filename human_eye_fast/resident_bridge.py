"""Resident, trusted-input mesh arrays in meters."""

from collections.abc import Hashable
from copy import deepcopy
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class ResidentMesh:
    """Borrowed read-only array views and appearance metadata for one object."""

    local_m: np.ndarray
    world_m: np.ndarray
    triangles: np.ndarray
    world_from_local: np.ndarray
    appearance: object


def _readonly_view(array):
    return np.asarray(memoryview(array).toreadonly())


class _ResidentObject:
    def __init__(self, local_m, triangles, world_from_local, appearance):
        self.local_m = local_m.copy()
        self.world_m = np.empty_like(self.local_m)
        self.transform = world_from_local.copy()
        self.linear = self.transform[:3, :3].T
        self.translation = self.transform[:3, 3]
        self.refresh_world()
        self.view = ResidentMesh(
            _readonly_view(self.local_m),
            _readonly_view(self.world_m),
            _readonly_view(triangles.copy()),
            _readonly_view(self.transform),
            appearance,
        )

    def refresh_world(self):
        np.matmul(self.local_m, self.linear, out=self.world_m)
        self.world_m += self.translation


class ResidentBridge:
    """Own local geometry and cache world geometry for multiple object IDs.

    Supply contiguous float64 vertex arrays and affine float64 4x4 matrices.
    Local coordinates and the matrix translation are already in meters.
    Triangle indices and dirty declarations are trusted. Serialize access and
    treat borrowed arrays and appearance as read-only. Use copies to retain
    a snapshot across updates.
    """

    def __init__(self):
        self._objects: dict[Hashable, _ResidentObject] = {}

    def __len__(self):
        return len(self._objects)

    def add(self, object_id, local_m, triangles, world_from_local, appearance=None):
        """Register a new object ID, copying the input geometry and metadata."""
        entry = _ResidentObject(local_m, triangles, world_from_local, deepcopy(appearance))
        self._objects[object_id] = entry
        return entry.view

    def get(self, object_id):
        """Borrow the existing descriptor without inspecting the geometry."""
        return self._objects[object_id].view

    def update_full(self, object_id, local_m):
        """Copy all local vertices and refresh the existing world buffer."""
        entry = self._objects[object_id]
        np.copyto(entry.local_m, local_m)
        entry.refresh_world()
        return entry.view

    def update_dirty(self, object_id, indices, local_rows_m):
        """Refresh the declared vertices, with one input row per distinct index."""
        entry = self._objects[object_id]
        world_rows = local_rows_m @ entry.linear
        world_rows += entry.translation
        entry.local_m[indices] = local_rows_m
        entry.world_m[indices] = world_rows
        return entry.view

    def update_transform(self, object_id, world_from_local):
        """Replace the affine transform and refresh world vertices in place."""
        entry = self._objects[object_id]
        np.copyto(entry.transform, world_from_local)
        entry.refresh_world()
        return entry.view

    def update_appearance(self, object_id, appearance):
        """Copy appearance metadata while keeping every array view."""
        entry = self._objects[object_id]
        mesh = entry.view
        entry.view = ResidentMesh(
            mesh.local_m, mesh.world_m, mesh.triangles, mesh.world_from_local, deepcopy(appearance)
        )
        return entry.view

    def replace_topology(self, object_id, local_m, triangles):
        """Replace one object's geometry while retaining its transform and appearance."""
        previous = self._objects[object_id]
        entry = _ResidentObject(local_m, triangles, previous.transform, previous.view.appearance)
        self._objects[object_id] = entry
        return entry.view

    def remove(self, object_id):
        """Release the bridge's references to one object."""
        del self._objects[object_id]

    def clear(self):
        """Release the bridge's references to all objects."""
        self._objects.clear()
