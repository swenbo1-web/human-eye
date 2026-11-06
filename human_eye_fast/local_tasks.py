"""Typed local tasks over the existing Blender control and clearance readback."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from threading import current_thread, main_thread

from .blender_resident_bridge import MeshChange
from .control import Action, ActionStageError, BlenderControl, ClearanceReadback, Goal, Outcome, Translate


@dataclass(frozen=True, slots=True)
class CloseGapTask:
    """Reduce the unsigned surface distance of two explicitly bound rigid meshes."""

    moving_id: str
    reference_id: str
    target_gap_m: float
    tolerance_m: float

    def __post_init__(self):
        if (not _identifier(self.moving_id) or not _identifier(self.reference_id)
                or self.moving_id == self.reference_id):
            raise ValueError("CloseGapTask requires two distinct object IDs")
        for name in ("target_gap_m", "tolerance_m"):
            value = getattr(self, name)
            try:
                number = float(value) if type(value) in (float, int) else -1.
            except OverflowError:
                number = -1.
            if not isfinite(number) or number < 0:
                raise ValueError(f"{name} must be a finite nonnegative number in meters")
            object.__setattr__(self, name, number)


@dataclass(frozen=True, slots=True)
class CloseGapResult:
    status: str
    reason: str | None
    write_status: str
    before: ClearanceReadback | None = None
    outcome: Outcome | None = None
    command: Translate | None = None
    planned_after_m: float | None = None
    stage: str | None = None


def _identifier(value):
    return isinstance(value, str) and bool(value)


def _require_main_thread():
    if current_thread() is not main_thread():
        raise RuntimeError("CloseGapSession runs on the Blender main thread")


class CloseGapSession:
    """One explicitly bound target on the Blender main thread.

    The host binds two independent rigid mesh surfaces. A write must only
    translate the moving surface uniformly in world space and leave the
    reference fixed. The host serializes access, holds scene geometry, frame
    and units stable through any evidence request, and closes the session
    before either target's topology changes.
    """

    def __init__(self, scene, view_layer, objects, task: CloseGapTask):
        _require_main_thread()
        if not isinstance(task, CloseGapTask):
            raise TypeError("Pass a CloseGapTask")
        if view_layer is None or scene.view_layers.get(view_layer.name) != view_layer:
            raise ValueError("Pass a view layer belonging to the bound scene")
        self._scene = scene
        self._view_layer = view_layer
        self._task = task
        ids = (task.moving_id, task.reference_id)
        pair = tuple(objects[key] for key in ids)
        if pair[0] == pair[1]:
            raise ValueError("The two object IDs must bind distinct Blender objects")
        self._pair = pair
        self._control = BlenderControl(scene, dict(zip(ids, pair)),
                                       Goal(*ids, task.target_gap_m, task.tolerance_m),
                                       view_layer=view_layer)
        self._closed = False
        self._evidence = None

    def evidence_meshes(self, readback: ClearanceReadback, *, context_objects=None):
        """Borrow target geometry and capture explicitly bound visual context.

        Only appearance is refreshed for the targets. The returned mapping
        lists the targets first, followed by the supplied context order.
        Consume it before the next run or close.
        """
        import bpy

        _require_main_thread()
        evidence = self._evidence
        if evidence is None or readback is not evidence[0]:
            raise ValueError("Use the current measurable close_gap readback")
        scene = self._scene
        _, scale, subframe = evidence
        if (scene.frame_current != readback.frame_id or scene.frame_subframe != subframe
                or scene.unit_settings.scale_length != scale):
            raise ValueError("The bound scene frame or units changed after the readback")
        if context_objects is not None and not isinstance(context_objects, Mapping):
            raise TypeError("Pass an ordered mapping of context IDs to mesh objects")
        context = tuple(context_objects.items()) if context_objects is not None else ()
        names = {obj.name for obj in self._pair}
        for key, obj in context:
            if (not _identifier(key) or key in readback.target_ids or obj.type != "MESH"
                    or obj.name in names or self._view_layer.objects.get(obj.name) != obj):
                raise ValueError("Context must name distinct mesh objects in the bound view layer")
            names.add(obj.name)
        with bpy.context.temp_override(scene=scene, view_layer=self._view_layer):
            graph = bpy.context.evaluated_depsgraph_get()
            bridge = self._control.bridge
            meshes = {
                key: bridge.capture(key, obj, graph, scale, MeshChange.APPEARANCE)
                for key, obj in zip(readback.target_ids, self._pair)
            }
            for key, obj in context:
                meshes[key] = bridge.capture(key, obj, graph, scale,
                                             MeshChange.TOPOLOGY | MeshChange.APPEARANCE)
        return meshes, scale

    def run(self, *, before_id: str, after_id: str) -> CloseGapResult:
        _require_main_thread()
        if self._closed:
            raise RuntimeError("CloseGapSession is closed")
        if not _identifier(before_id) or not _identifier(after_id) or before_id == after_id:
            raise ValueError("Supply distinct nonempty before and after observation IDs")
        self._evidence = None
        scale = self._scene.unit_settings.scale_length
        if not isfinite(scale) or scale <= 0:
            return CloseGapResult("rejected", "invalid_unit_scale", "not_written")
        subframe = self._scene.frame_subframe
        try:
            before = self._control.observe(before_id)
        except Exception:
            return CloseGapResult("error", "observation_failed", "not_written", stage="observe")
        surface = before.surface
        distance = surface.distance_m
        target = self._task.target_gap_m
        if surface.triangle_a is None or surface.triangle_b is None:
            return CloseGapResult("no_action", "empty_surface", "not_written", before)
        if not isfinite(distance) or distance < 0:
            return CloseGapResult("error", "invalid_gap", "not_written", before, stage="plan")
        if abs(distance - target) <= self._task.tolerance_m:
            self._evidence = before, scale, subframe
            return CloseGapResult("no_action", "already_reached", "not_written", before)
        if target > distance:
            self._evidence = before, scale, subframe
            return CloseGapResult("rejected", "would_increase_gap", "not_written", before)
        if surface.point_a is None or surface.point_b is None:
            return CloseGapResult("error", "invalid_witness", "not_written", before, stage="plan")

        step = distance - target
        # The distance lower bound is d - |t|. The original closest pair
        # gives the same upper bound for a translation toward that witness.
        fraction = step / distance
        delta = tuple(fraction * (b - a) for a, b in zip(surface.point_a, surface.point_b))
        if not all(map(isfinite, delta)):
            return CloseGapResult("error", "invalid_witness", "not_written", before, stage="plan")
        command = Translate(delta)
        action = Action(f"close_gap:{after_id}", before_id, command, -step)
        changes = dict.fromkeys(before.target_ids, MeshChange.VERTICES | MeshChange.TRANSFORM)
        try:
            outcome = self._control.execute(action, after_id, target_changes=changes)
        except ActionStageError as error:
            return CloseGapResult("error", "execution_failed", error.write_status, before,
                                  error.outcome, command, target, error.stage)
        except Exception:
            return CloseGapResult("error", "execution_failed", "unknown", before, command=command,
                                  planned_after_m=target, stage="execute")
        if outcome is None:
            return CloseGapResult("error", "missing_outcome", "unknown", before, command=command,
                                  planned_after_m=target, stage="execute")
        if outcome.measured_delta_m is None or not isfinite(outcome.after.surface.distance_m):
            return CloseGapResult("error", "unmeasured_after", "written", before, outcome, command, target)
        self._evidence = outcome.after, scale, subframe
        if not outcome.goal_reached:
            return CloseGapResult("not_reached", "outside_tolerance", "written", before, outcome, command, target)
        return CloseGapResult("reached", None, "written", before, outcome, command, target)

    def close(self):
        _require_main_thread()
        if not self._closed:
            self._control.close()
            self._pair = ()
            self._scene = self._view_layer = None
            self._evidence = None
            self._closed = True
