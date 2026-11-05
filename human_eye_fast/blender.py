"""In-process Blender capture; caller owns object, topology and update declarations.

Coordinates are mesh-local metres. Object world transforms are deliberately not
applied: bounds and surface metrics use the same mesh-local coordinate system.
Evaluated vertex indexing must match the reference. Topology changes require a
new BlenderSession. No topology/source checks run in this adapter.
"""
from __future__ import annotations

import numpy as np

from .engine import FastSession


def _vertices(mesh, scale):
    # Blender RNA coordinates expose float32; matching the buffer format keeps
    # foreach_get on its bulk copy path instead of Python sequence conversion.
    vertices = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", vertices)
    return vertices.reshape(-1, 3).astype(np.float64) * scale


class BlenderSession:
    def __init__(self, obj):
        import bpy

        self.bpy = bpy
        self.obj = bpy.data.objects[obj] if isinstance(obj, str) else obj
        self.scale = bpy.context.scene.unit_settings.scale_length
        mesh = self.obj.data
        mesh.calc_loop_triangles()
        triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", triangles)
        self.engine = FastSession(_vertices(mesh, self.scale), triangles.reshape(-1, 3))

    def read_frame(self, label, *, changed_vertices=None):
        graph = self.bpy.context.evaluated_depsgraph_get()
        evaluated = self.obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        # Releasing a Blender-owned temporary is ordinary object lifecycle.
        try:
            vertices = _vertices(mesh, self.scale)
        finally:
            evaluated.to_mesh_clear()
        return self.engine.set_frame(label, vertices, changed_vertices=changed_vertices)

    def query(self, labels, **kwargs):
        return self.engine.query(labels, **kwargs)
