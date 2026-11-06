"""Hand-written, single-scene integration reference over the accepted kernels.

The caller supplies the renderer and model and scores PNGs independently.
No production session or replacement numerical kernels are used.
"""

from dataclasses import dataclass, replace
from math import isfinite

import numpy as np

from human_eye_fast.cerebellar_flash import FiniteAction, action_features, geometry_delta, view_features
from human_eye_fast.blender_resident_bridge import MeshChange
from human_eye_fast.control import Action, BlenderControl, ClearanceReadback, Outcome, SetShapeKey, Translate
from human_eye_fast.fast_affordance_out import (
    AffordancePackage, ClearanceFact, DeformationFact, ImageFact, ObjectFact, ObservationFact, encode,
)
from human_eye_fast.fast_bvh_clearance import SurfaceIndex, surface_distance
from human_eye_fast.tensor_deform import compute_cross_frame_deformation_tensor


_GEOMETRY = MeshChange.VERTICES | MeshChange.TRANSFORM
_OBSERVATION = _GEOMETRY | MeshChange.UNITS


@dataclass(frozen=True, slots=True)
class CaptureChange:
    mask: MeshChange
    generation: int | None = None


class ActionStageError(RuntimeError):
    """State observed at the failure boundary of a command."""

    def __init__(self, stage, write_status, outcome=None):
        super().__init__(f"Action failed at {stage} ({write_status})")
        self.stage = stage
        self.write_status = write_status
        self.outcome = outcome
        self.action_ticket = None


class SharedCaptureControl(BlenderControl):
    """Manual simulation of the proposed capture seam over the existing components."""

    def __init__(self, scene, objects, goal, *, generations=None, view_layer=None,
                 renderer=None, model=None):
        super().__init__(scene, objects, goal)
        if view_layer is not None:
            self._view_layer = view_layer
        self.mesh_ids = tuple(objects)
        self.context_objects = tuple((key, obj) for key, obj in objects.items()
                                     if key not in self._target_ids)
        self.generations = dict.fromkeys(self.mesh_ids, 1) if generations is None else dict(generations)
        if self.generations.keys() != set(self.mesh_ids):
            raise ValueError("A starting generation is required for each mesh")
        self.reference = None
        self._owner = object()
        self._closed = False
        self._model = model
        self._owns_model = model is not None
        self._renderer = renderer

    def require_open(self):
        if self._closed:
            raise ValueError("The reference control is closed")

    def bind_model(self, model):
        if model is not None and self._model is not None and model is not self._model:
            raise ValueError("Model does not belong to this control")
        if model is not None:
            self._model = model
        return self._model

    def capture_changes(self, changes, *, after=False):
        defaults = _GEOMETRY if after else _OBSERVATION
        if changes is None:
            return dict.fromkeys(self.mesh_ids, CaptureChange(defaults))
        if changes.keys() != set(self.mesh_ids):
            raise ValueError("Declare a capture mask for each mesh")
        for key, change in changes.items():
            mask, generation = change.mask, change.generation
            if key in self._target_ids:
                if mask & (MeshChange.TOPOLOGY | MeshChange.APPEARANCE) or generation is not None:
                    raise ValueError("Target topology, appearance and generation are fixed")
                if after and mask & _GEOMETRY != _GEOMETRY:
                    raise ValueError("An action refreshes both targets' geometry and transform")
            elif mask & MeshChange.TOPOLOGY:
                if generation is None or generation == self.generations[key]:
                    raise ValueError("Context topology replacement requires a new generation")
            elif generation is not None:
                raise ValueError("Context generation can change only with TOPOLOGY")
        return changes

    def _capture_targets(self, observation_id, graph, scale, changes):
        meshes = tuple(self.bridge.capture(key, obj, graph, scale, changes[key].mask)
                       for key, obj in zip(self._target_ids, self._objects, strict=True))
        if self._indexes is None:
            self._indexes = tuple(SurfaceIndex(mesh.world_m, mesh.triangles) for mesh in meshes)
        else:
            for key, index, mesh in zip(self._target_ids, self._indexes, meshes, strict=True):
                if changes[key].mask & (_GEOMETRY | MeshChange.UNITS):
                    index.update(mesh.world_m)
        surface = surface_distance(*self._indexes)
        return ClearanceReadback(observation_id, self._scene.frame_current, self._target_ids, surface)

    def _capture_context(self, graph, scale, changes):
        for key, obj in self.context_objects:
            change = changes[key]
            self.bridge.capture(key, obj, graph, scale, change.mask)
            if change.generation is not None:
                self.generations[key] = change.generation

    def scene_context(self):
        return self._context.temp_override(scene=self._scene, view_layer=self._view_layer)

    def replace_reference(self, reference):
        self.require_open()
        if reference.topology_generation != self.generations[self._target_ids[0]]:
            raise ValueError("Reference belongs to a different moving topology generation")
        self.reference = reference
        self._latest = None
        return reference

    def observe(self, observation_id, *, changes=None):
        self.require_open()
        self._latest = None
        changes = self.capture_changes(changes)
        with self.scene_context():
            graph = self._context.evaluated_depsgraph_get()
            scale = self._scene.unit_settings.scale_length
            readback = self._capture_targets(observation_id, graph, scale, changes)
            self._capture_context(graph, scale, changes)
        self._latest = readback
        return readback

    def execute(self, action, after_observation_id, *, changes=None):
        self.require_open()
        before = self._latest
        if before is None or action.before_observation_id != before.observation_id:
            raise ValueError("Action must refer to the current observation")
        self._latest = None
        if before.surface.triangle_a is None or self._reached(before.surface.distance_m):
            return None
        try:
            changes = self.capture_changes(changes, after=True)
        except Exception as error:
            raise ActionStageError("prepare", "not_written") from error

        command = action.command
        moving = self._objects[0]
        scale = self._scene.unit_settings.scale_length
        translate = isinstance(command, Translate)
        with self.scene_context():
            try:
                graph = self._context.evaluated_depsgraph_get()
                if translate:
                    world = moving.evaluated_get(graph).matrix_world.copy()
                    control_before = tuple(component * scale for component in world.translation)
                    world.translation = tuple(
                        position + delta / scale
                        for position, delta in zip(world.translation, command.delta_world_m, strict=True)
                    )
                else:
                    keys = moving.data.shape_keys
                    control_before = float(keys.evaluated_get(graph).key_blocks[command.key_name].value)
                    key = keys.key_blocks[command.key_name]
            except Exception as error:
                raise ActionStageError("prepare", "not_written") from error

            try:
                if translate:
                    moving.matrix_world = world
                else:
                    key.value = command.value
            except Exception as error:
                raise ActionStageError("write", "unknown") from error

            try:
                graph = self._context.evaluated_depsgraph_get()
                after = self._capture_targets(after_observation_id, graph, scale, changes)
                if translate:
                    position = self.bridge.get(self._target_ids[0]).world_from_local[:3, 3]
                    control_after = tuple(map(float, position))
                else:
                    control_after = float(keys.evaluated_get(graph).key_blocks[command.key_name].value)
            except Exception as error:
                raise ActionStageError("target_readback", "written") from error

            initial, final = before.surface.distance_m, after.surface.distance_m
            measured = final - initial if isfinite(initial) and isfinite(final) else None
            outcome = Outcome(self._goal, action, before, after, control_before, control_after,
                              measured, self._reached(final))
            try:
                self._capture_context(graph, scale, changes)
            except Exception as error:
                raise ActionStageError("context", "written", outcome) from error
        self._latest = after
        return outcome

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.bridge.clear()
        self._indexes = self._latest = None
        self.reference = None
        renderer, model = self._renderer, self._model if self._owns_model else None
        self._renderer = self._model = None
        try:
            if renderer is not None:
                with self.scene_context():
                    renderer.close()
        finally:
            try:
                if model is not None:
                    model.close()
            finally:
                self._objects = self.context_objects = ()
                self._context = self._scene = self._view_layer = None


@dataclass(frozen=True, slots=True)
class WorldReference:
    frame_id: int
    topology_generation: int
    world_m: np.ndarray

    def __post_init__(self):
        vertices = np.array(self.world_m, dtype=np.float64, copy=True, order="C")
        vertices.flags.writeable = False
        object.__setattr__(self, "world_m", vertices)


def reference_from_capture(control, readback, topology_generation=None):
    """Own the fixed world-meter reference before any later native mutation."""
    if control._latest is not readback:
        raise ValueError("Reference requires the current capture")
    moving_id = readback.target_ids[0]
    moving = control.bridge.get(moving_id)
    generation = control.generations[moving_id] if topology_generation is None else topology_generation
    return WorldReference(readback.frame_id, generation, moving.world_m)


@dataclass(frozen=True, slots=True)
class RelativeShapeBasis:
    key_name: str
    local_delta_bu: np.ndarray
    object_pointer: int
    key_pointer: int
    relative_key_pointer: int


def _key_coordinates(block):
    coordinates = np.empty((len(block.data), 3), dtype=np.float32)
    block.data.foreach_get("co", coordinates.ravel())
    return coordinates.astype(np.float64)


def relative_basis_from_rna(moving, key_name):
    """Read the authored key and its actual relative key, both in local BU."""
    key = moving.data.shape_keys.key_blocks[key_name]
    delta = _key_coordinates(key) - _key_coordinates(key.relative_key)
    delta.flags.writeable = False
    return RelativeShapeBasis(key_name, delta, moving.as_pointer(), key.as_pointer(),
                              key.relative_key.as_pointer())


def finite_action(control, command, *, basis=None):
    """Form a descriptor for fixed evaluated vertex order and unmasked relative keys."""
    moving = control._objects[0]
    world = control.bridge.get(control._target_ids[0]).world_from_local
    if isinstance(command, Translate):
        return FiniteAction.translation(command.delta_world_m, world[:3, 3])

    if not isinstance(command, SetShapeKey):
        raise TypeError(f"Unsupported command type: {type(command).__name__}")
    if basis is None:
        basis = relative_basis_from_rna(moving, command.key_name)
    else:
        key = moving.data.shape_keys.key_blocks[command.key_name]
        if (basis.key_name, basis.object_pointer, basis.key_pointer, basis.relative_key_pointer) != (
            command.key_name, moving.as_pointer(), key.as_pointer(), key.relative_key.as_pointer()
        ):
            raise ValueError("Relative basis belongs to a different object, key or relative key")
    with control.scene_context():
        graph = control._context.evaluated_depsgraph_get()
        keys = moving.data.shape_keys.evaluated_get(graph)
        q = keys.key_blocks[command.key_name].value
    scale = control._scene.unit_settings.scale_length
    world_delta_m = (basis.local_delta_bu * scale) @ world[:3, :3].T
    return FiniteAction.shape_key(q, command.value, world_delta_m)


@dataclass(eq=False, slots=True)
class ViewReceipt:
    observation_id: str
    arm: str
    index: int
    rays: int
    native_stop: bool
    features: np.ndarray | None
    attachment_key: str
    owner: object
    consumed: bool = False


@dataclass(frozen=True, slots=True)
class ViewFeedback:
    observation_id: str
    attachment_key: str
    index: int
    pixel_pass: bool


@dataclass(frozen=True, slots=True)
class ObservedFrame:
    """Borrowed fact positions and durable PNG attachments."""

    fact: ObservationFact
    readback: ClearanceReadback
    attachments: dict[str, bytes]
    view: ViewReceipt | None
    image_status: str


@dataclass(frozen=True, slots=True)
class PublishedObservation(ObservedFrame):
    ao_bytes: bytes


@dataclass(eq=False, slots=True)
class Prediction:
    action: Action
    features: np.ndarray | None
    meters: float | None
    before: ClearanceReadback
    owner: object
    consumed: bool = False


@dataclass(frozen=True, slots=True)
class NoAction:
    reason: str


@dataclass(eq=False, slots=True)
class ActionReceipt:
    outcome: Outcome
    features: np.ndarray | None
    meters: float
    owner: object
    consumed: bool = False


@dataclass(frozen=True, slots=True)
class ActionPublication:
    outcome: Outcome
    after: ObservedFrame
    ao_bytes: bytes
    attachments: dict[str, bytes]
    action_ticket: ActionReceipt | None


def _require_view(mode, view_arm, model):
    if mode not in (None, "NATURAL", "SECTION"):
        raise ValueError(f"Unknown image mode {mode!r}")
    if view_arm not in ("F", "R", "L"):
        raise ValueError(f"Unknown view arm {view_arm!r}")
    if mode is not None and view_arm != "F" and model is None:
        raise ValueError(f"View arm {view_arm} requires a supplied model")


def _reference(control, reference):
    if control.reference is None and reference is not None:
        return control.replace_reference(reference)
    if control.reference is None or (reference is not None and control.reference is not reference):
        raise ValueError("Use the current reference or explicitly replace it")
    return control.reference


def _render(control, renderer, meshes, readback, mode, view_arm, model, audit):
    if mode is None:
        return None, None, "disabled"
    surface = readback.surface
    if surface.triangle_a is None:
        return None, None, "empty_surface"
    if mode == "SECTION" and surface.distance_m == 0:
        return None, None, "section_requires_positive_gap"
    state = []
    rank = None
    if view_arm in ("R", "L") and surface.distance_m > 0:
        occluders = tuple((mesh.world_m, mesh.triangles) for key, mesh in meshes.items()
                          if key not in readback.target_ids)

        def rank(directions):
            key = view_features(surface.point_a, surface.point_b, directions, occluders,
                                section=mode == "SECTION")
            key.flags.writeable = False
            state.append((key, tuple(tuple(direction) for direction in directions)))
            return model.rank_view(key, view_arm)

    with control.scene_context():
        rendered = renderer.observe(
            renderer.prepare(meshes), surface, target_ids=readback.target_ids,
            frame_id=readback.frame_id, scale_length=control._scene.unit_settings.scale_length,
            mode=mode, rank_directions=rank, audit=audit,
        )
    if not state:
        return rendered, None, "rendered"
    key, canonical = state[0]
    selected = rendered.metadata["selection"]
    direction = tuple(selected["direction"])
    probe = next(row for row in selected["probes"] if tuple(row["direction"]) == direction)
    receipt = ViewReceipt(readback.observation_id, view_arm, canonical.index(direction),
                          probe["ray_count"], probe["target_support"] == 2, key,
                          f"{readback.observation_id}.png", control._owner)
    return rendered, receipt, "rendered"


def _frame(control, renderer, reference, readback, *, mode, view_arm, model, audit, top_k,
           selected_face_ids, outcome=None):
    meshes = {key: control.bridge.get(key) for key in control.mesh_ids}
    try:
        rendered, receipt, image_status = _render(control, renderer, meshes, readback, mode,
                                                  view_arm, model, audit)
    except Exception as error:
        if outcome is None:
            raise
        raise ActionStageError("render", "written", outcome) from error
    object_facts = tuple(
        ObjectFact(key, control.generations[key],
                   tuple(mesh.world_m.mean(axis=0)) if len(mesh.world_m) else None)
        for key, mesh in meshes.items()
    )
    moving_id = readback.target_ids[0]
    moving = meshes[moving_id]
    try:
        metrics = compute_cross_frame_deformation_tensor(
            (moving.world_m,), moving.triangles, reference_vertices=reference.world_m, top_k=top_k,
        )
    except Exception as error:
        if outcome is None:
            raise
        raise ActionStageError("td", "written", outcome) from error
    deformation = DeformationFact(moving_id, reference.frame_id, (readback.frame_id,), metrics,
                                  moving.triangles, readback.frame_id, moving.world_m,
                                  tuple(selected_face_ids))
    path = f"{readback.observation_id}.png"
    fact = ObservationFact(
        readback.observation_id, readback.frame_id, object_facts,
        ClearanceFact(readback.target_ids, readback.surface), deformation,
        ImageFact(path, rendered) if rendered is not None else None,
    )
    return ObservedFrame(fact, readback, {path: rendered.png} if rendered is not None else {},
                         receipt, image_status)


def observe(control, renderer, reference, observation_id, *, mode, view_arm, model=None,
            audit=False, top_k=12, selected_face_ids=(), changes=None):
    """Capture once and publish one immutable byte package and real attachments."""
    control.require_open()
    control._latest = None
    model = control.bind_model(model)
    _require_view(mode, view_arm, model)
    reference = _reference(control, reference)
    readback = control.observe(observation_id, changes=changes)
    try:
        frame = _frame(control, renderer, reference, readback, mode=mode, view_arm=view_arm,
                       model=model, audit=audit, top_k=top_k, selected_face_ids=selected_face_ids)
        payload = encode(AffordancePackage((frame.fact,)))
    except Exception:
        control._latest = None
        raise
    return PublishedObservation(frame.fact, frame.readback, frame.attachments, frame.view,
                                frame.image_status, payload)


def predict(control, before, command, action_id, *, action_arm="NONE", model=None, basis=None):
    """Bind a caller-selected command and an optional prediction to before."""
    control.require_open()
    if control._latest is not before.readback:
        raise ValueError("Prediction requires the current observation")
    if not isinstance(command, (Translate, SetShapeKey)):
        raise TypeError(f"Unsupported command type: {type(command).__name__}")
    if action_arm not in ("NONE", "G", "L"):
        raise ValueError(f"Unknown action arm {action_arm!r}")
    surface = before.readback.surface
    if surface.triangle_a is None:
        return NoAction("NO_SURFACE")
    if control._reached(surface.distance_m):
        return NoAction("GOAL_REACHED")
    model = control.bind_model(model)
    features = meters = predicted = None
    if action_arm in ("G", "L"):
        pairs = tuple((mesh.world_m, mesh.triangles)
                      for mesh in map(control.bridge.get, before.readback.target_ids))
        known = finite_action(control, command, basis=basis)
        if action_arm == "G":
            predicted = geometry_delta(*pairs, surface, known)
        else:
            if model is None:
                raise ValueError("Action arm L requires a supplied model")
            features, meters = action_features(*pairs, surface, known)
            features.flags.writeable = False
            predicted = model.predict_delta(features, meters)
    action = Action(action_id, before.readback.observation_id, command, predicted)
    return Prediction(action, features, meters, before.readback, control._owner)


def _action_ticket(control, features, meters, outcome):
    if outcome is None or features is None or outcome.measured_delta_m is None:
        return None
    return ActionReceipt(outcome, features, meters, control._owner)


def execute(control, renderer, reference, before, prediction, after_observation_id, *, mode,
            view_arm, model=None, audit=False, top_k=12, selected_face_ids=(), changes=None):
    """Publish from the actual control readback, with no second after capture."""
    control.require_open()
    if isinstance(prediction, NoAction):
        return None
    if (prediction.owner is not control._owner or prediction.consumed
            or control._latest is not before.readback or prediction.before is not before.readback
            or prediction.action.before_observation_id != before.readback.observation_id):
        raise ValueError("Execution requires a live plan bound to the current observation")
    prediction.consumed = True
    try:
        if after_observation_id == before.readback.observation_id:
            raise ValueError("The after observation requires a new ID")
        model = control.bind_model(model)
        _require_view(mode, view_arm, model)
        reference = _reference(control, reference)
        old_deformation = before.fact.deformation
        retained = replace(old_deformation, position_vertices_m=old_deformation.position_vertices_m.copy())
        before_fact = replace(before.fact, deformation=retained)
    except Exception as error:
        control._latest = None
        prediction.features = None
        raise ActionStageError("prepare", "not_written") from error
    features, prediction.features = prediction.features, None
    try:
        outcome = control.execute(prediction.action, after_observation_id, changes=changes)
    except ActionStageError as error:
        error.action_ticket = _action_ticket(control, features, prediction.meters, error.outcome)
        raise
    if outcome is None:
        return None
    ticket = _action_ticket(control, features, prediction.meters, outcome)
    try:
        after = _frame(control, renderer, reference, outcome.after, mode=mode, view_arm=view_arm,
                       model=model, audit=audit, top_k=top_k, selected_face_ids=selected_face_ids,
                       outcome=outcome)
        payload = encode(AffordancePackage((before_fact, after.fact), outcome))
        attachments = {**before.attachments, **after.attachments}
    except ActionStageError as error:
        control._latest = None
        error.action_ticket = ticket
        raise
    except Exception as error:
        control._latest = None
        publication_error = ActionStageError("ao", "written", outcome)
        publication_error.action_ticket = ticket
        raise publication_error from error
    return ActionPublication(outcome, after, payload, attachments, ticket)


def view_feedback(control, model, receipt, feedback):
    """Learn only the actually rendered direction after an external verdict."""
    control.require_open()
    if (receipt.owner is not control._owner or receipt.consumed
            or (receipt.observation_id, receipt.attachment_key, receipt.index)
            != (feedback.observation_id, feedback.attachment_key, feedback.index)):
        raise ValueError("Feedback requires a live receipt for the actual PNG and direction")
    model = control.bind_model(model)
    receipt.consumed = True
    features, receipt.features = receipt.features, None
    model.learn_view(features, receipt.index, receipt.native_stop and feedback.pixel_pass,
                     receipt.rays, update_model=receipt.arm == "L")


def action_feedback(control, model, receipt):
    """Learn only the actual measured delta embedded in the result receipt."""
    control.require_open()
    if receipt.owner is not control._owner or receipt.consumed:
        raise ValueError("Feedback requires a live measured receipt for this control")
    model = control.bind_model(model)
    receipt.consumed = True
    features, receipt.features = receipt.features, None
    model.learn_action(features, receipt.meters, receipt.outcome.measured_delta_m)
