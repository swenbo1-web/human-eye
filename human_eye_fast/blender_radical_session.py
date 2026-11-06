"""Unified Blender observations, explicit actions and actual-result feedback."""

from dataclasses import dataclass, field, replace
from math import isfinite
from types import MappingProxyType

import numpy as np

from ._cf_features import (
    FiniteAction, action_features, geometry_delta, triangle_pair_distance, view_features,
)
from .blender_resident_bridge import MeshChange
from .cf_deployment import CFDeployment
from .control import Action, ActionStageError, BlenderControl, ClearanceReadback, SetShapeKey, Translate
from .fast_affordance_out import (
    AffordancePackage, ClearanceFact, DeformationFact, ImageFact, ObjectFact, ObservationFact, encode,
)
from .tensor_deform import compute_cross_frame_deformation_tensor


_GEOMETRY = MeshChange.VERTICES | MeshChange.TRANSFORM
_ALL_CHANGES = _GEOMETRY | MeshChange.TOPOLOGY | MeshChange.UNITS | MeshChange.APPEARANCE


@dataclass(frozen=True, slots=True)
class CaptureChange:
    mask: MeshChange
    generation: int | None = None


@dataclass(frozen=True, slots=True)
class ReferenceFrame:
    frame_id: int
    topology_generation: int
    moving_world_m: np.ndarray

    def __post_init__(self):
        vertices = np.asarray(self.moving_world_m, dtype=np.float64)
        if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
            raise ValueError("A reference needs finite world-meter vertices with shape (N, 3)")
        owned = np.frombuffer(vertices.tobytes(), dtype=np.float64).reshape(vertices.shape)
        object.__setattr__(self, "moving_world_m", owned)


@dataclass(frozen=True, slots=True)
class ObservationRequest:
    observation_id: str
    image_mode: str | None
    view_arm: str


@dataclass(frozen=True, slots=True)
class NoAction:
    reason: str


@dataclass(eq=False, slots=True, frozen=True)
class PreparedAction:
    _owner: object = field(repr=False)
    _before: ClearanceReadback = field(repr=False)
    _action: Action = field(repr=False)
    _features: np.ndarray | None = field(repr=False)
    _meters: float | None = field(repr=False)
    _consumed: bool = field(default=False, init=False, repr=False)

    @property
    def observation_id(self):
        return self._action.before_observation_id

    @property
    def action_id(self):
        return self._action.action_id

    @property
    def predicted_delta_m(self):
        return self._action.predicted_delta_m


@dataclass(frozen=True, slots=True)
class ViewFeedback:
    observation_id: str
    attachment_key: str
    index: int
    pixel_pass: bool


@dataclass(frozen=True, slots=True)
class ProbeAudit:
    direction: tuple
    ray_count: int
    aperture_taps: int
    target_support: int


@dataclass(frozen=True, slots=True)
class ViewAudit:
    canonical_index: int | None
    direction: tuple
    total_rays: int
    probes: tuple[ProbeAudit, ...]
    native_stop: bool
    order: tuple[int, ...] | None


@dataclass(eq=False, frozen=True, slots=True)
class _ViewTicket:
    observation_id: str
    attachment_key: str
    index: int
    _owner: object = field(repr=False)
    _features: np.ndarray | None = field(repr=False)
    _rays: int
    _native_stop: bool
    _arm: str
    _consumed: bool = field(default=False, init=False, repr=False)


@dataclass(eq=False, frozen=True, slots=True)
class _ActionTicket:
    _owner: object = field(repr=False)
    _features: np.ndarray | None = field(repr=False)
    _meters: float
    _measured_delta_m: float
    _consumed: bool = field(default=False, init=False, repr=False)


@dataclass(frozen=True, slots=True)
class ObservationResult:
    observation_id: str
    frame_id: int
    ao_bytes: bytes
    attachments: MappingProxyType
    image_status: str
    view_ticket: _ViewTicket | None
    view_audit: ViewAudit | None


@dataclass(frozen=True, slots=True)
class ActionResult(ObservationResult):
    action_ticket: _ActionTicket | None


@dataclass(slots=True)
class _Current:
    readback: ClearanceReadback
    fact: ObservationFact
    attachments: MappingProxyType


@dataclass(slots=True)
class _RelativeBasis:
    pointers: tuple
    delta_bu: np.ndarray


def _coordinates(key):
    result = np.empty((len(key.data), 3), dtype=np.float32)
    key.data.foreach_get("co", result.ravel())
    return result.astype(np.float64)


def _path_segment(value):
    return (isinstance(value, str) and value not in ("", ".", "..")
            and not any(character in "/\\:" or ord(character) < 32 for character in value))


class BlenderRadicalSession:
    """Serialize access on the caller's Blender main thread and GPU context."""

    def __init__(self, scene, view_layer, objects, goal, generations, *, reference, deployment=None,
                 top_k=12, selected_face_ids=()):
        self._objects = dict(objects)
        self._targets = (goal.moving_id, goal.reference_id)
        if self._targets[0] == self._targets[1] or not all(key in objects for key in self._targets):
            raise ValueError("Goal must name two distinct session objects")
        if view_layer is None or scene.view_layers.get(view_layer.name) != view_layer:
            raise ValueError("View layer must belong to the explicit scene")
        if set(generations) != set(objects):
            raise ValueError("Provide exactly one generation per session object")
        self._generations = dict(generations)
        self._reference = self._checked_reference(reference)
        if deployment is not None and not isinstance(deployment, CFDeployment):
            raise TypeError("Pass a CFDeployment or load it with load_cf_deployment")
        self._controller = BlenderControl(scene, self._objects, goal, view_layer=view_layer,
                                          capture_context=self._capture_context)
        self._context_ids = tuple(key for key in objects if key not in self._targets)
        self._model = None if deployment is None else deployment.session()
        self._top_k = top_k
        self._selected_face_ids = tuple(selected_face_ids)
        self._renderer = None
        self._current = None
        self._changes = None
        self._bases = {}
        self._owner = object()
        self._closed = False

    def _require_open(self):
        if self._closed:
            raise ValueError("Session is closed")

    def _discard_current(self):
        self._current = None
        self._controller._latest = None

    def _scene_context(self):
        control = self._controller
        return control._context.temp_override(scene=control._scene, view_layer=control._view_layer)

    def _checked_reference(self, reference):
        if not isinstance(reference, ReferenceFrame):
            raise TypeError("Provide an explicit ReferenceFrame")
        if reference.topology_generation != self._generations[self._targets[0]]:
            raise ValueError("Reference must match the moving topology generation")
        return reference

    def replace_reference(self, reference):
        self._require_open()
        self._reference = self._checked_reference(reference)
        self._discard_current()

    def _request(self, request):
        if not _path_segment(request.observation_id):
            raise ValueError("Observation ID must be a nonempty relative path segment")
        if request.image_mode not in (None, "NATURAL", "SECTION"):
            raise ValueError(f"Unknown image mode {request.image_mode!r}")
        if request.view_arm not in ("F", "R", "L"):
            raise ValueError(f"Unknown view arm {request.view_arm!r}")
        if request.view_arm != "F" and self._model is None:
            raise ValueError(f"View arm {request.view_arm} requires an explicit deployment")

    def _capture_changes(self, changes, *, after=False):
        if changes.keys() != self._objects.keys():
            raise ValueError("Declare a capture change for every session object")
        masks = {}
        for key in self._objects:
            change = changes[key]
            if not isinstance(change, CaptureChange):
                raise TypeError("Use CaptureChange for each capture declaration")
            mask = MeshChange(change.mask)
            if int(mask) & ~int(_ALL_CHANGES):
                raise ValueError(f"Unknown mesh change for {key!r}")
            topology = bool(mask & MeshChange.TOPOLOGY)
            if key in self._targets:
                if mask & (MeshChange.TOPOLOGY | MeshChange.APPEARANCE):
                    raise ValueError("Target topology and appearance require a new session")
                masks[key] = mask | _GEOMETRY if after else mask
            if topology != (change.generation is not None):
                raise ValueError("A topology change requires an explicit new generation")
            if topology and change.generation == self._generations[key]:
                raise ValueError("Context topology requires a different generation")
        return masks

    def _capture_context(self, phase, bridge, graph, scale_length, measured_outcome):
        for key in self._context_ids:
            change = self._changes[key]
            bridge.capture(key, self._objects[key], graph, scale_length, change.mask)
            if change.generation is not None:
                self._generations[key] = change.generation

    def _render(self, meshes, readback, request):
        mode = request.image_mode
        surface = readback.surface
        if mode is None:
            return None, None, None, "disabled"
        if surface.triangle_a is None:
            return None, None, None, "empty_surface"
        if mode == "SECTION" and surface.distance_m <= 0:
            return None, None, None, "section_requires_positive_gap"
        ranking = None
        rank = None
        if request.view_arm != "F" and surface.distance_m > 0:
            occluders = tuple((meshes[key].world_m, meshes[key].triangles) for key in self._context_ids)

            def rank(directions):
                nonlocal ranking
                features = view_features(surface.point_a, surface.point_b, directions, occluders,
                                         section=mode == "SECTION")
                features.flags.writeable = False
                order = self._model.rank_view(features, request.view_arm)
                ranking = features, tuple(map(tuple, directions)), order
                return order

        with self._scene_context():
            if self._renderer is None:
                from .raycast_saccade_gpu import VGRenderer

                self._renderer = VGRenderer()
            rendered = self._renderer.observe(
                self._renderer.prepare(meshes), surface, target_ids=readback.target_ids,
                frame_id=readback.frame_id, scale_length=self._controller._scene.unit_settings.scale_length,
                mode=mode, rank_directions=rank,
            )
        selection = rendered.metadata["selection"]
        direction = tuple(selection["direction"])
        probes = tuple(ProbeAudit(tuple(probe["direction"]), probe["ray_count"], probe["aperture_taps"],
                                  probe["target_support"]) for probe in selection["probes"])
        selected = next((probe for probe in probes if probe.direction == direction), None)
        stopped = selected is not None and selected.target_support == 2
        ticket = index = order = None
        if ranking is not None:
            features, canonical, order = ranking
            index = canonical.index(direction)
            ticket = _ViewTicket(request.observation_id, f"{request.observation_id}.png", index,
                                 self._owner, features, selected.ray_count, stopped, request.view_arm)
        audit = ViewAudit(index, direction, selection["ray_count"], probes, stopped, order)
        return rendered, ticket, audit, "rendered"

    def _frame(self, readback, request, outcome=None):
        meshes = {key: self._controller.bridge.get(key) for key in self._objects}
        try:
            rendered, ticket, audit, status = self._render(meshes, readback, request)
        except Exception as error:
            if outcome is None:
                raise
            raise ActionStageError("render", "written", outcome) from error
        facts = tuple(ObjectFact(key, self._generations[key],
                                 tuple(mesh.world_m.mean(axis=0)) if len(mesh.world_m) else None)
                      for key, mesh in meshes.items())
        moving_id = self._targets[0]
        mesh = meshes[moving_id]
        try:
            metrics = compute_cross_frame_deformation_tensor(
                (mesh.world_m,), mesh.triangles, reference_vertices=self._reference.moving_world_m,
                top_k=self._top_k,
            )
        except Exception as error:
            if outcome is None:
                raise
            raise ActionStageError("td", "written", outcome) from error
        deformation = DeformationFact(moving_id, self._reference.frame_id, (readback.frame_id,),
                                      metrics, mesh.triangles, readback.frame_id, mesh.world_m,
                                      self._selected_face_ids)
        key = f"{request.observation_id}.png"
        image = ImageFact(key, rendered) if rendered is not None else None
        fact = ObservationFact(request.observation_id, readback.frame_id, facts,
                               ClearanceFact(self._targets, readback.surface), deformation, image)
        attachments = MappingProxyType({key: rendered.png} if rendered is not None else {})
        return _Current(readback, fact, attachments), status, ticket, audit

    def observe(self, request, *, changes):
        self._require_open()
        self._discard_current()
        self._request(request)
        masks = self._capture_changes(changes)
        self._changes = changes
        try:
            readback = self._controller.observe(request.observation_id, target_changes=masks)
            current, status, ticket, audit = self._frame(readback, request)
            ao_bytes = encode(AffordancePackage((current.fact,)))
        except Exception:
            self._discard_current()
            raise
        finally:
            self._changes = None
        self._current = current
        return ObservationResult(request.observation_id, readback.frame_id, ao_bytes,
                                 current.attachments, status, ticket, audit)

    def _relative_key(self, key_name):
        moving = self._objects[self._targets[0]]
        keys = moving.data.shape_keys
        if keys is None or not keys.use_relative:
            raise ValueError("Finite prediction requires relative shape keys")
        key = keys.key_blocks[key_name]
        relative = key.relative_key
        if relative is None or relative == key or key.vertex_group or key.mute:
            raise ValueError("Finite prediction requires an active, unmasked relative shape key")
        pointers = moving.as_pointer(), key.as_pointer(), relative.as_pointer()
        return key, relative, pointers

    def prepare_relative_basis(self, key_name):
        """Refresh authored coordinates for one explicit object/key/relative-key binding."""
        self._require_open()
        key, relative, pointers = self._relative_key(key_name)
        self._bases[key_name] = _RelativeBasis(pointers, _coordinates(key) - _coordinates(relative))

    def _shape_inputs(self, command, mesh):
        key, _, pointers = self._relative_key(command.key_name)
        basis = self._bases.get(command.key_name)
        if basis is None or basis.pointers != pointers:
            raise ValueError("Prepare the current relative basis before finite shape prediction")
        if len(basis.delta_bu) != len(mesh.world_m):
            raise ValueError("Authored basis and evaluated geometry must share vertex rows")
        control = self._controller
        with self._scene_context():
            graph = control._context.evaluated_depsgraph_get()
            keys = self._objects[self._targets[0]].data.shape_keys.evaluated_get(graph)
            q = float(keys.key_blocks[command.key_name].value)
        if not (key.slider_min <= q <= key.slider_max and key.slider_min <= command.value <= key.slider_max):
            raise ValueError("Finite shape prediction requires values in the key's slider range")
        return q, basis.delta_bu, control._scene.unit_settings.scale_length

    def _predict_finite(self, command, surface, predictor):
        moving, reference = map(self._controller.bridge.get, self._targets)
        pairs = (moving.world_m, moving.triangles), (reference.world_m, reference.triangles)
        world = moving.world_from_local
        if isinstance(command, Translate):
            known = FiniteAction.translation(command.delta_world_m, world[:3, 3])
        else:
            q, local, scale = self._shape_inputs(command, moving)
            if predictor == "G":
                rows = moving.triangles[surface.triangle_a]
                shift = (command.value - q) * ((local[rows] * scale) @ world[:3, :3].T)
                after = triangle_pair_distance(moving.world_m[rows] + shift,
                                               reference.world_m[reference.triangles[surface.triangle_b]])
                return after - surface.distance_m, None, None
            known = FiniteAction.shape_key(q, command.value, (local * scale) @ world[:3, :3].T)
        if predictor == "G":
            return geometry_delta(*pairs, surface, known), None, None
        features, meters = action_features(*pairs, surface, known)
        features.flags.writeable = False
        return self._model.predict_delta(features, meters), features, meters

    def predict_action(self, observation_id, action_id, command, *, predictor):
        self._require_open()
        if self._current is None or self._current.readback.observation_id != observation_id:
            raise ValueError("Prediction requires the current observation")
        if not isinstance(command, (Translate, SetShapeKey)):
            raise TypeError("Use Translate or SetShapeKey")
        if predictor not in ("NONE", "G", "L"):
            raise ValueError(f"Unknown predictor {predictor!r}")
        if predictor == "L" and self._model is None:
            raise ValueError("Predictor L requires an explicit deployment")
        before = self._current.readback
        surface = before.surface
        if surface.triangle_a is None:
            return NoAction("NO_SURFACE")
        if self._controller._reached(surface.distance_m):
            return NoAction("GOAL_REACHED")
        predicted = features = meters = None
        if predictor != "NONE":
            predicted, features, meters = self._predict_finite(command, surface, predictor)
        action = Action(action_id, observation_id, command, predicted)
        return PreparedAction(self._owner, before, action, features, meters)

    def _action_ticket(self, outcome, features, meters):
        if outcome is None or features is None or outcome.measured_delta_m is None:
            return None
        if not isfinite(outcome.measured_delta_m):
            return None
        return _ActionTicket(self._owner, features, meters, outcome.measured_delta_m)

    def execute(self, plan, after_request, *, changes):
        self._require_open()
        before = self._current
        if (not isinstance(plan, PreparedAction) or plan._owner is not self._owner or plan._consumed
                or before is None or plan._before is not before.readback):
            raise ValueError("Execution requires a live plan for the current observation")
        object.__setattr__(plan, "_consumed", True)
        features = plan._features
        object.__setattr__(plan, "_features", None)
        self._current = None
        try:
            self._request(after_request)
            if after_request.observation_id == plan.observation_id:
                raise ValueError("The after observation requires a new ID")
            masks = self._capture_changes(changes, after=True)
            before_fact = before.fact
            deformation = before_fact.deformation
            if deformation.selected_face_ids or deformation.metrics["witness_triangle_ids"].size:
                before_fact = replace(before_fact, deformation=replace(
                    deformation, position_vertices_m=deformation.position_vertices_m.copy()))
        except Exception as error:
            self._discard_current()
            raise ActionStageError("prepare", "not_written") from error
        self._changes = changes
        try:
            outcome = self._controller.execute(plan._action, after_request.observation_id, target_changes=masks)
        except ActionStageError as error:
            self._discard_current()
            error.action_ticket = self._action_ticket(error.outcome, features, plan._meters)
            raise
        finally:
            self._changes = None
        ticket = self._action_ticket(outcome, features, plan._meters)
        try:
            after, status, view_ticket, audit = self._frame(outcome.after, after_request, outcome)
            ao_bytes = encode(AffordancePackage((before_fact, after.fact), outcome))
            attachments = MappingProxyType({**before.attachments, **after.attachments})
        except ActionStageError as error:
            self._discard_current()
            error.action_ticket = ticket
            raise
        except Exception as error:
            self._discard_current()
            failure = ActionStageError("ao", "written", outcome)
            failure.action_ticket = ticket
            raise failure from error
        self._current = after
        return ActionResult(after_request.observation_id, outcome.after.frame_id, ao_bytes, attachments,
                            status, view_ticket, audit, ticket)

    def view_feedback(self, ticket, feedback):
        self._require_open()
        if (not isinstance(ticket, _ViewTicket) or ticket._owner is not self._owner or ticket._consumed
                or not isinstance(feedback, ViewFeedback) or type(feedback.pixel_pass) is not bool
                or (ticket.observation_id, ticket.attachment_key, ticket.index)
                != (feedback.observation_id, feedback.attachment_key, feedback.index)):
            raise ValueError("Feedback requires a live ticket for the actual PNG and direction")
        features = ticket._features
        object.__setattr__(ticket, "_consumed", True)
        object.__setattr__(ticket, "_features", None)
        self._model.learn_view(features, ticket.index, ticket._native_stop and feedback.pixel_pass,
                               ticket._rays, update_model=ticket._arm == "L")

    def action_feedback(self, ticket):
        self._require_open()
        if not isinstance(ticket, _ActionTicket) or ticket._owner is not self._owner or ticket._consumed:
            raise ValueError("Feedback requires a live measured ticket for this session")
        features = ticket._features
        object.__setattr__(ticket, "_consumed", True)
        object.__setattr__(ticket, "_features", None)
        self._model.learn_action(features, ticket._meters, ticket._measured_delta_m)

    def close(self):
        if self._closed:
            return
        self._closed = True
        renderer, self._renderer = self._renderer, None
        model, self._model = self._model, None
        try:
            if renderer is not None:
                with self._scene_context():
                    renderer.close()
        finally:
            try:
                if model is not None:
                    model.close()
            finally:
                self._controller.close()
                self._objects.clear()
                self._bases.clear()
                self._reference = self._current = None

    def __enter__(self):
        self._require_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
