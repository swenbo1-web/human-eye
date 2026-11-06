"""Hand-written, single-scene integration reference over the accepted kernels.

This verification path owns no renderer or model. Its caller supplies both,
uses a fixed evaluated topology per control, and scores PNGs independently.
"""

from dataclasses import dataclass, replace

import numpy as np

from human_eye_fast.cerebellar_flash import FiniteAction, action_features, geometry_delta, view_features
from human_eye_fast.control import Action, BlenderControl, ClearanceReadback, Outcome, SetShapeKey, Translate
from human_eye_fast.fast_affordance_out import (
    AffordancePackage, ClearanceFact, DeformationFact, ImageFact, ObjectFact, ObservationFact, encode,
)
from human_eye_fast.tensor_deform import compute_cross_frame_deformation_tensor


class SharedCaptureControl(BlenderControl):
    """Extend the control-owned capture to context meshes on the same graph.

    All meshes use the accepted controller's capture flags. Start a new
    control for changed topology or appearance.
    """

    def __init__(self, scene, objects, goal):
        super().__init__(scene, objects, goal)
        self.mesh_ids = tuple(objects)
        self.context_objects = tuple((key, obj) for key, obj in objects.items()
                                     if key not in self._target_ids)

    def _capture(self, observation_id, graph, scale, changes):
        readback = super()._capture(observation_id, graph, scale, changes)
        for key, obj in self.context_objects:
            self.bridge.capture(key, obj, graph, scale, changes)
        return readback

    def scene_context(self):
        return self._context.temp_override(scene=self._scene, view_layer=self._view_layer)

    def close(self):
        self.bridge.clear()
        self._indexes = self._latest = None


@dataclass(frozen=True, slots=True)
class WorldReference:
    frame_id: int
    topology_generation: int
    world_m: np.ndarray


def reference_from_capture(control, readback, topology_generation=1):
    """Own the fixed world-meter reference before any later native mutation."""
    if control._latest is not readback:
        raise ValueError("Reference requires the current capture")
    moving = control.bridge.get(readback.target_ids[0])
    world_m = moving.world_m.copy()
    world_m.flags.writeable = False
    return WorldReference(readback.frame_id, topology_generation, world_m)


@dataclass(frozen=True, slots=True)
class RelativeShapeBasis:
    key_name: str
    local_delta_bu: np.ndarray


def _key_coordinates(block):
    coordinates = np.empty((len(block.data), 3), dtype=np.float32)
    block.data.foreach_get("co", coordinates.ravel())
    return coordinates.astype(np.float64)


def relative_basis_from_rna(moving, key_name):
    """Read the authored key and its actual relative key, both in local BU."""
    key = moving.data.shape_keys.key_blocks[key_name]
    delta = _key_coordinates(key) - _key_coordinates(key.relative_key)
    delta.flags.writeable = False
    return RelativeShapeBasis(key_name, delta)


def finite_action(control, command, *, basis=None):
    """Form a descriptor for fixed evaluated vertex order and unmasked relative keys."""
    moving = control._objects[0]
    world = control.bridge.get(control._target_ids[0]).world_from_local
    if isinstance(command, Translate):
        return FiniteAction.translation(command.delta_world_m, world[:3, 3])

    if not isinstance(command, SetShapeKey):
        raise TypeError(f"Unsupported command type: {type(command).__name__}")
    basis = relative_basis_from_rna(moving, command.key_name) if basis is None else basis
    if basis.key_name != command.key_name:
        raise ValueError("Relative basis belongs to a different key")
    with control.scene_context():
        graph = control._context.evaluated_depsgraph_get()
        keys = moving.data.shape_keys.evaluated_get(graph)
        q = keys.key_blocks[command.key_name].value
    scale = control._scene.unit_settings.scale_length
    world_delta_m = (basis.local_delta_bu * scale) @ world[:3, :3].T
    return FiniteAction.shape_key(q, command.value, world_delta_m)


@dataclass(frozen=True, slots=True)
class ViewReceipt:
    observation_id: str
    arm: str
    index: int
    rays: int
    native_stop: bool
    features: np.ndarray


@dataclass(frozen=True, slots=True)
class ObservedFrame:
    """Borrowed fact positions and durable PNG attachments."""

    fact: ObservationFact
    readback: ClearanceReadback
    attachments: dict[str, bytes]
    view: ViewReceipt | None


@dataclass(frozen=True, slots=True)
class PublishedObservation(ObservedFrame):
    ao_bytes: bytes


@dataclass(frozen=True, slots=True)
class Prediction:
    action: Action
    features: np.ndarray | None
    meters: float | None


@dataclass(frozen=True, slots=True)
class ActionPublication:
    outcome: Outcome
    after: ObservedFrame
    ao_bytes: bytes
    attachments: dict[str, bytes]


def _render(control, renderer, meshes, readback, mode, view_arm, model, audit):
    surface = readback.surface
    if surface.triangle_a is None or (mode == "SECTION" and surface.distance_m == 0):
        return None, None
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
        return rendered, None
    key, canonical = state[0]
    selected = rendered.metadata["selection"]
    direction = tuple(selected["direction"])
    probe = next(row for row in selected["probes"] if tuple(row["direction"]) == direction)
    receipt = ViewReceipt(readback.observation_id, view_arm, canonical.index(direction),
                          probe["ray_count"], probe["target_support"] == 2, key)
    return rendered, receipt


def _frame(control, renderer, reference, readback, *, mode, view_arm, model, audit, top_k,
           selected_face_ids):
    if view_arm not in ("F", "R", "L"):
        raise ValueError(f"Unknown view arm {view_arm!r}")
    if view_arm != "F" and model is None:
        raise ValueError(f"View arm {view_arm} requires a supplied model")
    meshes = {key: control.bridge.get(key) for key in control.mesh_ids}
    rendered, receipt = _render(control, renderer, meshes, readback, mode, view_arm, model, audit)
    object_facts = tuple(
        ObjectFact(key, reference.topology_generation,
                   tuple(mesh.world_m.mean(axis=0)) if len(mesh.world_m) else None)
        for key, mesh in meshes.items()
    )
    moving_id = readback.target_ids[0]
    moving = meshes[moving_id]
    metrics = compute_cross_frame_deformation_tensor(
        (moving.world_m,), moving.triangles, reference_vertices=reference.world_m, top_k=top_k,
    )
    deformation = DeformationFact(moving_id, reference.frame_id, (readback.frame_id,), metrics,
                                  moving.triangles, readback.frame_id, moving.world_m,
                                  tuple(selected_face_ids))
    path = f"{readback.observation_id}.png"
    fact = ObservationFact(
        readback.observation_id, readback.frame_id, object_facts,
        ClearanceFact(readback.target_ids, readback.surface), deformation,
        ImageFact(path, rendered) if rendered is not None else None,
    )
    return ObservedFrame(fact, readback, {path: rendered.png} if rendered is not None else {}, receipt)


def observe(control, renderer, reference, observation_id, *, mode, view_arm, model=None,
            audit=False, top_k=12, selected_face_ids=()):
    """Capture once and publish one immutable byte package and real attachments."""
    readback = control.observe(observation_id)
    frame = _frame(control, renderer, reference, readback, mode=mode, view_arm=view_arm,
                   model=model, audit=audit, top_k=top_k, selected_face_ids=selected_face_ids)
    return PublishedObservation(frame.fact, frame.readback, frame.attachments, frame.view,
                                encode(AffordancePackage((frame.fact,))))


def predict(control, before, command, action_id, *, action_arm, model=None, basis=None):
    """Bind a caller-selected command and an optional prediction to before."""
    if control._latest is not before.readback:
        raise ValueError("Prediction requires the current observation")
    surface = before.readback.surface
    if surface.triangle_a is None or control._reached(surface.distance_m):
        return None
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
    elif action_arm != "none":
        raise ValueError(f"Unknown action arm {action_arm!r}")
    action = Action(action_id, before.readback.observation_id, command, predicted)
    return Prediction(action, features, meters)


def execute(control, renderer, reference, before, prediction, after_observation_id, *, mode,
            view_arm, model=None, audit=False, top_k=12, selected_face_ids=()):
    """Publish from the actual control readback, with no second after capture."""
    if prediction is None:
        return None
    if (control._latest is not before.readback
            or prediction.action.before_observation_id != before.readback.observation_id):
        raise ValueError("Execution requires the bound current observation")
    old_deformation = before.fact.deformation
    retained = replace(old_deformation, position_vertices_m=old_deformation.position_vertices_m.copy())
    before_fact = replace(before.fact, deformation=retained)
    outcome = control.execute(prediction.action, after_observation_id)
    if outcome is None:
        return None
    after = _frame(control, renderer, reference, outcome.after, mode=mode, view_arm=view_arm,
                   model=model, audit=audit, top_k=top_k, selected_face_ids=selected_face_ids)
    payload = encode(AffordancePackage((before_fact, after.fact), outcome))
    return ActionPublication(outcome, after, payload, {**before.attachments, **after.attachments})


def view_feedback(model, receipt, pixel_pass):
    """Learn only the actually rendered direction after an external verdict."""
    if receipt is not None:
        model.learn_view(receipt.features, receipt.index, receipt.native_stop and pixel_pass,
                         receipt.rays, update_model=receipt.arm == "L")


def action_feedback(model, prediction, outcome):
    """Learn a real measured delta only for its bound learned prediction."""
    if prediction.action != outcome.action:
        raise ValueError("Outcome belongs to a different prediction")
    if prediction.features is not None and outcome.measured_delta_m is not None:
        model.learn_action(prediction.features, prediction.meters, outcome.measured_delta_m)
