"""Blender fixtures and shared timed CF observation/action path."""

from contextlib import contextmanager
from dataclasses import dataclass, replace
from time import perf_counter_ns

import bpy
import numpy as np

from human_eye_fast.blender_resident_bridge import BlenderResidentBridge, MeshChange
from human_eye_fast.cerebellar_flash import (
    FiniteAction, action_features, command_group, triangle_pair_distance, view_features,
)
from human_eye_fast.control import Action, BlenderControl, Goal, SetShapeKey, Translate
from human_eye_fast.fast_affordance_out import (
    AffordancePackage, ClearanceFact, DeformationFact, ImageFact, ObjectFact, ObservationFact, encode,
)
from human_eye_fast.fast_bvh_clearance import SurfaceIndex, surface_distance
from human_eye_fast.tensor_deform import compute_cross_frame_deformation_tensor
from verification.test_blender_control import _mesh_object, _scene
from verification.test_raycast_saccade_gpu import _native_meshes


_CHANGES = MeshChange.VERTICES | MeshChange.TRANSFORM | MeshChange.UNITS


def _coordinates(data):
    coordinates = np.empty((len(data), 3), dtype=np.float32)
    data.foreach_get("co", coordinates.ravel())
    return coordinates.astype(np.float64)


@dataclass
class NativeFixture:
    fixture: object
    scene: object
    objects: dict
    key: object
    scale_length: float
    rest: np.ndarray
    relative_basis_bu: np.ndarray | None

    @property
    def targets(self):
        return self.fixture.target_ids

    def context(self):
        return bpy.context.temp_override(scene=self.scene, view_layer=self.scene.view_layers[0])

    def snapshot(self):
        return _native_meshes(self)


@contextmanager
def materialize(fixture):
    with _scene(7, fixture.scale_length) as scene:
        scale = scene.unit_settings.scale_length
        objects = {}
        key = basis = None
        for mesh in fixture.meshes:
            obj = _mesh_object(scene, mesh.object_id, (mesh.vertices_m / scale).tolist(),
                               mesh.triangles.tolist(), mesh.color)
            objects[mesh.object_id] = obj
            if mesh.shape_basis_m is not None:
                obj.shape_key_add(name="Basis", from_mix=False)
                key = obj.shape_key_add(name=fixture.command.key_name, from_mix=False)
                keyed = ((mesh.vertices_m + mesh.shape_basis_m) / scale).astype(np.float32)
                key.data.foreach_set("co", keyed.ravel())
                key.value = fixture.command.control_before
                basis = _coordinates(key.data) - _coordinates(key.relative_key.data)
        moving = objects[fixture.target_ids[0]]
        rest = _coordinates(moving.data.vertices) * scale
        yield NativeFixture(fixture, scene, objects, key, scale, rest, basis)


def mesh_pair(meshes, targets):
    return tuple((meshes[key].world_m, meshes[key].triangles) for key in targets)


def observation(native, meshes, surface, observation_id, image, *, retain_positions=False):
    """Capture current facts while the RB arrays still describe this observation."""
    frame = native.scene.frame_current
    targets = native.targets
    objects = tuple(ObjectFact(key, 1, tuple(mesh.world_m.mean(axis=0)) if len(mesh.world_m) else None)
                    for key, mesh in meshes.items())
    moving = meshes[targets[0]]
    metrics = compute_cross_frame_deformation_tensor(
        (moving.world_m,), moving.triangles, reference_vertices=native.rest,
    )
    positions = moving.world_m.copy() if retain_positions else moving.world_m
    deformation = DeformationFact(targets[0], 0, (frame,), metrics, moving.triangles,
                                  frame, positions)
    return ObservationFact(observation_id, frame, objects, ClearanceFact(targets, surface),
                           deformation, ImageFact(f"{observation_id}.png", image) if image else None)


class ViewEpisode:
    def __init__(self, native):
        self.native = native
        self.bridge = BlenderResidentBridge()
        self.indexes = None

    def capture(self):
        graph = bpy.context.evaluated_depsgraph_get()
        meshes = {key: self.bridge.capture(key, obj, graph, self.native.scale_length, _CHANGES)
                  for key, obj in self.native.objects.items()}
        pairs = mesh_pair(meshes, self.native.targets)
        if self.indexes is None:
            self.indexes = tuple(SurfaceIndex(*pair) for pair in pairs)
        else:
            for index, (vertices, _) in zip(self.indexes, pairs):
                index.update(vertices)
        return meshes, surface_distance(*self.indexes)

    def ranker(self, meshes, surface, model, arm):
        features = []
        if arm == "F":
            return None, features

        targets = self.native.targets
        context = tuple((mesh.world_m, mesh.triangles) for key, mesh in meshes.items()
                        if key not in targets)
        section = self.native.fixture.mode == "SECTION"

        def rank(directions):
            current = view_features(surface.point_a, surface.point_b, directions, context,
                                    section=section)
            features.append(current)
            return model.rank_view(current, arm)

        return rank, features

    def run(self, renderer, model, arm, stages=None):
        """Native deployment path used inside the performance interval."""
        native = self.native
        with native.context():
            meshes, surface = self.capture()
            if stages is not None:
                stages["captured"] = perf_counter_ns()
            rank, features = self.ranker(meshes, surface, model, arm)
            image = renderer.observe(
                renderer.prepare(meshes), surface, target_ids=native.targets,
                frame_id=native.scene.frame_current, scale_length=native.scale_length,
                mode=native.fixture.mode, rank_directions=rank,
            )
            if stages is not None:
                stages["drawn"] = perf_counter_ns()
            payload = encode(AffordancePackage((observation(native, meshes, surface, "view", image),)))
            if stages is not None:
                stages["published"] = perf_counter_ns()
        return image, payload, features


@dataclass
class ActionResult:
    outcome: object
    prediction: float | None
    comparison: dict
    features: np.ndarray | None
    meters: float | None
    group: tuple | None
    before_png: object
    after_png: object
    before_payload: bytes
    after_payload: bytes
    native_before: dict | None
    native_after: dict | None
    stages_ns: dict


class ActionEpisode:
    def __init__(self, native):
        self.native = native
        self.moving, self.reference = native.targets
        command = native.fixture.command
        self.command = (Translate(command.delta_world_m) if command.kind == "translate" else
                        SetShapeKey(command.key_name, command.target_value))
        self.controller = BlenderControl(native.scene, native.objects,
                                         Goal(self.moving, self.reference, 0., 0.))

    def reset(self):
        native = self.native
        if native.key is not None:
            native.key.value = native.fixture.command.control_before
        else:
            native.objects[self.moving].location = tuple(
                v / native.scale_length for v in native.fixture.command.control_before)

    def _meshes(self):
        return {key: self.controller.bridge.get(key) for key in self.native.targets}

    def _control(self):
        native = self.native
        moving = native.objects[self.moving]
        if native.key is None:
            return FiniteAction.translation(self.command.delta_world_m,
                                            tuple(moving.location * native.scale_length))
        graph = bpy.context.evaluated_depsgraph_get()
        q = moving.data.shape_keys.evaluated_get(graph).key_blocks[native.key.name].value
        return FiniteAction("set_shape_key", float(q), self.command.value, None)

    def _finite_basis(self, moving, indices=slice(None)):
        native = self.native
        return ((native.relative_basis_bu[indices] * native.scale_length) @
                moving.world_from_local[:3, :3].T)

    def _group(self, current, surface, pairs):
        if current.kind == "set_shape_key":
            return command_group(current)
        a, b = (vertices[np.unique(triangles)] for vertices, triangles in pairs)
        scale = max(surface.distance_m, np.linalg.norm(np.ptp(a, axis=0)),
                    np.linalg.norm(np.ptp(b, axis=0))) or 1.
        normal = (np.asarray(surface.point_b) - surface.point_a) / surface.distance_m
        return command_group(current, normal=normal, scale=scale)

    def _geometry(self, current, surface, moving, pairs):
        a, b = pairs
        ids = a[1][surface.triangle_a]
        if current.kind == "set_shape_key":
            shift = (current.target - current.control_before) * self._finite_basis(moving, ids)
        else:
            shift = np.asarray(current.target)
        return triangle_pair_distance(a[0][ids] + shift, b[0][b[1][surface.triangle_b]]) - surface.distance_m

    def _predict(self, surface, meshes, arm, model, constant, shuffle, collect):
        current = self._control()
        pairs = mesh_pair(meshes, self.native.targets)
        moving = meshes[self.moving]
        features = meters = group = predicted = None
        comparison = {}
        if arm == "L" or collect:
            if current.kind == "set_shape_key":
                current = replace(current, basis_world_m=self._finite_basis(moving))
            features, meters = action_features(*pairs, surface, current)
            comparison["G"] = float(features[1] * meters)
            if model is not None:
                comparison["L"] = model.predict_delta(features, meters)
            if shuffle is not None:
                comparison["shuffle"] = shuffle.predict_delta(features, meters)
        if arm == "G" and not collect:
            comparison["G"] = self._geometry(current, surface, moving, pairs)
        if arm == "C" or collect:
            group = self._group(current, surface, pairs)
            if constant is not None:
                comparison["C"] = constant.predict(group)
                if collect:
                    comparison["ungrouped"] = constant.global_median_m
        if arm is not None:
            predicted = comparison[arm]
        return predicted, comparison, features, meters, group

    def run(self, renderer, arm, *, model=None, constant=None, shuffle=None, collect=False,
            snapshots=False, stages=False):
        native = self.native
        times = {}
        # Perf driver owns the enclosing and subinterval clocks. Detailed clocks
        # are collected separately so the timed deployment path stays uninstrumented.
        def mark(name):
            if stages:
                times[name] = perf_counter_ns()

        def draw(meshes, surface):
            if renderer is None:
                return None
            return renderer.observe(renderer.prepare(meshes), surface, target_ids=native.targets,
                                    frame_id=native.scene.frame_current,
                                    scale_length=native.scale_length, mode="NATURAL")

        with native.context():
            mark("start")
            before = self.controller.observe("before")
            meshes = self._meshes()
            mark("captured")
            predicted, comparison, features, meters, group = self._predict(
                before.surface, meshes, arm, model, constant, shuffle, collect)
            mark("predicted")
            before_png = draw(meshes, before.surface)
            before_fact = observation(native, meshes, before.surface, "before", before_png,
                                      retain_positions=True)
            before_payload = encode(AffordancePackage((before_fact,)))
            old = native.snapshot() if snapshots else None
            mark("before_ready")
            outcome = self.controller.execute(Action("apply", "before", self.command, predicted),
                                              "after")
            mark("executed")
            meshes = self._meshes()
            after_png = draw(meshes, outcome.after.surface)
            after_fact = observation(native, meshes, outcome.after.surface, "after", after_png)
            after_payload = encode(AffordancePackage((before_fact, after_fact), outcome))
            new = native.snapshot() if snapshots else None
            mark("finished")
        return ActionResult(outcome, predicted, comparison, features, meters, group, before_png,
                            after_png, before_payload, after_payload, old, new, times)
