"""Collect Blender's evaluated mesh into resident, meter-space arrays."""

from dataclasses import dataclass
from enum import IntFlag, auto

import numpy as np

from .resident_bridge import ResidentMesh, _readonly_view


class MeshChange(IntFlag):
    """Trusted declarations for one evaluated object since its last capture."""

    NONE = 0
    VERTICES = auto()
    TOPOLOGY = auto()
    TRANSFORM = auto()
    UNITS = auto()
    APPEARANCE = auto()


@dataclass(frozen=True, slots=True)
class BlenderAppearance:
    """Object and slot colors, plus the polygon/triangle material mapping."""

    object_color: tuple[float, float, float, float]
    material_slots: tuple[tuple[str, tuple[float, float, float, float]] | None, ...]
    polygon_material_indices: np.ndarray
    triangle_polygon_indices: np.ndarray


def _read_triangles(mesh):
    faces = len(mesh.polygons)
    if len(mesh.loops) == 3 * faces:
        # In a valid mesh every face has at least three corners. For an
        # all-triangle mesh Blender emits the existing corner order per face.
        triangles = np.empty((faces, 3), dtype=np.int32)
        if faces:
            mesh.attributes[".corner_vert"].data.foreach_get("value", triangles.reshape(-1))
        return triangles, np.arange(faces, dtype=np.int32)

    loop_triangles = mesh.loop_triangles
    triangles = np.empty((len(loop_triangles), 3), dtype=np.int32)
    triangle_polygons = np.empty(len(loop_triangles), dtype=np.int32)
    loop_triangles.foreach_get("vertices", triangles.reshape(-1))
    mesh.loop_triangle_polygons.foreach_get("value", triangle_polygons)
    return triangles, triangle_polygons


class _Capture:
    def __init__(self, mesh):
        shape = (len(mesh.vertices), 3)
        self.positions = np.empty(shape, dtype=np.float32)
        self.local_m = np.empty(shape, dtype=np.float64)
        self.world_m = np.empty_like(self.local_m)
        self.transform = np.empty((4, 4), dtype=np.float64)
        self.linear = self.transform[:3, :3].T
        self.translation = self.transform[:3, 3]

        triangles, triangle_polygons = _read_triangles(mesh)
        self.triangle_polygons = _readonly_view(triangle_polygons)
        self.view = ResidentMesh(
            _readonly_view(self.local_m),
            _readonly_view(self.world_m),
            _readonly_view(triangles),
            _readonly_view(self.transform),
            None,
        )

    def read_appearance(self, evaluated, mesh):
        slots = tuple(
            (slot.name, tuple(material.diffuse_color)) if (material := slot.material) else None
            for slot in evaluated.material_slots
        )
        material_index = mesh.attributes.get("material_index")
        if material_index is None:
            indices = np.zeros(len(mesh.polygons), dtype=np.int32)
        else:
            indices = np.empty(len(mesh.polygons), dtype=np.int32)
            material_index.data.foreach_get("value", indices)
        appearance = BlenderAppearance(
            tuple(evaluated.color), slots, _readonly_view(indices), self.triangle_polygons
        )
        self.view = ResidentMesh(
            self.view.local_m,
            self.view.world_m,
            self.view.triangles,
            self.view.world_from_local,
            appearance,
        )


class BlenderResidentBridge:
    """Own arrays for Blender mesh objects keyed by caller-supplied IDs.

    Supply a current depsgraph and scene scale_length. The caller serializes
    access, declares all changes, and shares one graph across a capture batch.
    TOPOLOGY includes changes to the final loop-triangle connectivity. Keep
    copies for snapshots across updates of borrowed arrays.
    """

    def __init__(self):
        self._objects = {}

    def __len__(self):
        return len(self._objects)

    def capture(self, object_id, obj, depsgraph, scale_length, changes=MeshChange.NONE):
        """Register or refresh an object and return a borrowed ResidentMesh."""
        entry = self._objects.get(object_id)
        rebuild = entry is None or changes & MeshChange.TOPOLOGY
        if not rebuild and not changes:
            return entry.view

        vertices = rebuild or changes & MeshChange.VERTICES
        local = vertices or changes & MeshChange.UNITS
        transform = rebuild or changes & (MeshChange.TRANSFORM | MeshChange.UNITS)
        appearance = rebuild or changes & MeshChange.APPEARANCE
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.data if vertices or appearance else None
        if rebuild:
            entry = _Capture(mesh)
        if vertices and entry.positions.size:
            mesh.attributes["position"].data.foreach_get("vector", entry.positions.reshape(-1))
        if local:
            np.multiply(entry.positions, scale_length, out=entry.local_m, dtype=np.float64)
        if transform:
            entry.transform[:] = evaluated.matrix_world
            entry.translation[:] *= scale_length
        if local or transform:
            np.matmul(entry.local_m, entry.linear, out=entry.world_m)
            entry.world_m += entry.translation
        if appearance:
            entry.read_appearance(evaluated, mesh)
        if rebuild:
            self._objects[object_id] = entry
        return entry.view

    def get(self, object_id):
        """Borrow the last captured arrays without touching Blender."""
        return self._objects[object_id].view

    def remove(self, object_id):
        """Release the bridge's references to one capture."""
        del self._objects[object_id]

    def clear(self):
        """Release the bridge's references to all captures."""
        self._objects.clear()
