"""Explicit Blender actions with evaluated RB and BC readback."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

from .blender_resident_bridge import BlenderResidentBridge, MeshChange
from .fast_bvh_clearance import SurfaceDistance, SurfaceIndex, surface_distance

if TYPE_CHECKING:
    from bpy.types import Object, Scene


Point = tuple[float, float, float]
_GEOMETRY_CHANGE = MeshChange.VERTICES | MeshChange.TRANSFORM


@dataclass(frozen=True, slots=True)
class Goal:
    moving_id: str
    reference_id: str
    distance_m: float
    tolerance_m: float


@dataclass(frozen=True, slots=True)
class Translate:
    delta_world_m: Point


@dataclass(frozen=True, slots=True)
class SetShapeKey:
    key_name: str
    value: float


@dataclass(frozen=True, slots=True)
class Action:
    action_id: str
    before_observation_id: str
    command: Translate | SetShapeKey
    predicted_delta_m: float | None = None


@dataclass(frozen=True, slots=True)
class ClearanceReadback:
    observation_id: str
    frame_id: int
    target_ids: tuple[str, str]
    surface: SurfaceDistance


@dataclass(frozen=True, slots=True)
class Outcome:
    goal: Goal
    action: Action
    before: ClearanceReadback
    after: ClearanceReadback
    control_before: Point | float
    control_after: Point | float
    measured_delta_m: float | None
    goal_reached: bool


class BlenderControl:
    """Control a fixed-topology pair in a serialized Blender scene.

    Observe before choosing an action. Keep scene state stable between the
    observed state and its action, and start a new session for new topology.
    The bridge exposes borrowed geometry from the latest evaluated capture.
    """

    def __init__(self, scene: "Scene", objects: Mapping[str, "Object"], goal: Goal):
        import bpy

        self._context = bpy.context
        self._scene = scene
        self._view_layer = scene.view_layers[0]
        self._goal = goal
        self._target_ids = (goal.moving_id, goal.reference_id)
        self._objects = (objects[goal.moving_id], objects[goal.reference_id])
        self.bridge = BlenderResidentBridge()
        self._indexes = None
        self._latest = None

    def _capture(self, observation_id, graph, scale, changes):
        meshes = tuple(
            self.bridge.capture(object_id, obj, graph, scale, changes)
            for object_id, obj in zip(self._target_ids, self._objects)
        )
        if self._indexes is None:
            self._indexes = tuple(SurfaceIndex(mesh.world_m, mesh.triangles) for mesh in meshes)
        else:
            for index, mesh in zip(self._indexes, meshes):
                index.update(mesh.world_m)
        surface = surface_distance(*self._indexes)
        return ClearanceReadback(observation_id, self._scene.frame_current, self._target_ids, surface)

    def observe(self, observation_id: str) -> ClearanceReadback:
        """Capture current evaluated geometry and query its minimum distance."""
        self._latest = None
        with self._context.temp_override(scene=self._scene, view_layer=self._view_layer):
            graph = self._context.evaluated_depsgraph_get()
            self._latest = self._capture(
                observation_id, graph, self._scene.unit_settings.scale_length,
                _GEOMETRY_CHANGE | MeshChange.UNITS,
            )
        return self._latest

    def _reached(self, distance_m):
        return abs(distance_m - self._goal.distance_m) <= self._goal.tolerance_m

    def execute(self, action: Action, after_observation_id: str) -> Outcome | None:
        """Apply one command and return its measured outcome, or stop at goal."""
        before = self._latest
        if before is None or action.before_observation_id != before.observation_id:
            raise ValueError("Action must refer to the current observation")
        if self._reached(before.surface.distance_m):
            return None

        command = action.command
        moving = self._objects[0]
        scale = self._scene.unit_settings.scale_length
        translate = isinstance(command, Translate)
        with self._context.temp_override(scene=self._scene, view_layer=self._view_layer):
            graph = self._context.evaluated_depsgraph_get()
            # A failed write or readback cannot leave a usable pre-action observation.
            self._latest = None
            if translate:
                world = moving.evaluated_get(graph).matrix_world.copy()
                control_before = tuple(component * scale for component in world.translation)
                world.translation = tuple(
                    position + delta / scale
                    for position, delta in zip(world.translation, command.delta_world_m)
                )
                moving.matrix_world = world
            else:
                keys = moving.data.shape_keys
                control_before = float(keys.evaluated_get(graph).key_blocks[command.key_name].value)
                keys.key_blocks[command.key_name].value = command.value

            graph = self._context.evaluated_depsgraph_get()
            # Both evaluated objects can depend on the write, e.g. through parenting.
            after = self._capture(after_observation_id, graph, scale, _GEOMETRY_CHANGE)
            if translate:
                position_m = self.bridge.get(self._goal.moving_id).world_from_local[:3, 3]
                control_after = tuple(map(float, position_m))
            else:
                control_after = float(keys.evaluated_get(graph).key_blocks[command.key_name].value)

        self._latest = after
        initial = before.surface.distance_m
        final = after.surface.distance_m
        measured = final - initial if isfinite(initial) and isfinite(final) else None
        return Outcome(self._goal, action, before, after, control_before, control_after, measured,
                       self._reached(final))
