"""Frozen AO inputs, native observations and independent scoring evidence."""

from contextlib import contextmanager
from hashlib import sha256
from math import cos, isfinite, pi, sin
from time import perf_counter_ns

import bpy
import gpu
import numpy as np

from human_eye_fast.blender_resident_bridge import BlenderResidentBridge, MeshChange
from human_eye_fast.control import Action, BlenderControl, Goal, SetShapeKey, Translate
from human_eye_fast.fast_affordance_out import (
    AffordancePackage, ClearanceFact, DeformationFact, ImageFact, ObjectFact,
    ObservationFact, encode, public_schema,
)
from human_eye_fast.fast_bvh_clearance import SurfaceIndex, surface_distance
from human_eye_fast.raycast_saccade_gpu import VGRenderer
from human_eye_fast.resident_bridge import ResidentBridge
from human_eye_fast.tensor_deform import compute_cross_frame_deformation_tensor
from verification.test_fast_affordance_out import decode_public
from verification.vg_fixtures import (
    COLOR_A, COLOR_B, S, TETRA_FACES, TETRA_POINTS, VARIANTS,
    _box, _build, _centered_box, _material, _object, build_fixture,
)


_QUESTIONS = (
    "Report the clearance in meters, both world witness points, original triangle rows, and their object and frame bindings.",
    "Report the unrounded surface separation in meters. Do the two surfaces have a positive gap or zero surface distance?",
    "Report the surface separation and both world-meter witnesses after the parent transform. Bind each witness to its object, frame and face.",
    "What is the unsigned surface separation of the nested boxes?",
    "Report the zero surface distance and both witnesses. Use the BC relation as stated.",
    "Report the zero surface distance and both witnesses for the crossing triangles.",
    "Report the surface-distance status and whether distance and witnesses are defined.",
    "Report the original input triangle rows after object swap and row reorder. Which object owns each witness?",
    "Report both principal stretches and maximum area strain. Is this a substantial stretch despite the area change?",
    "Report the stretch, area strain, and world normal angle after the rigid rotation.",
    "Report the area strain, minimum stretch and whether the current-frame world normal angle is defined.",
    "Identify the undefined reference-based metrics and report the separately measured centroid displacement.",
    "Report the reduction size, the ordered top six original face rows, their six metrics and the frame-8 world centroids.",
    "Report the reference and sampled frames over which the metrics were reduced. Can a peak occurrence frame be recovered?",
    "Open the PNG and identify the two targets, frame, observation and actual panel cameras in the natural dual view.",
    "Open the PNG. Identify the original global view and the sectioned local view, including the cut plane and kept side.",
    "Open the PNG. Locate the target and same-colored decoy by public object ID and projected world location.",
    "Select the specified frame. Open its PNG and report the matching cameras and geometric witnesses.",
    "Move the specified object with the explicit world translation. Report before and after observation, measured gap change and goal result.",
    "Set the specified shape key. Report the actual key readbacks and evaluated before and after clearance with the bound observations.",
)

_METRICS = (
    "max_principal_stretch", "min_principal_stretch", "max_area_strain",
    "max_normal_angle_deg", "max_centroid_displacement", "score",
)
_OFFSET = np.array([0.125, -0.25, 0.5])
_UNIT_BOX = _box((0, 1), (0, 1), (0, 1))


def _oid(case, state, step=0):
    return f"a{case:02d}-{state}-{step}"


def _ids(case):
    return f"O{case:02d}-A", f"O{case:02d}-B"


def _plain_point(point):
    return tuple(map(float, point))


def _number(value):
    return float(value) if isfinite(value) else None


def _measure(cost, name, function, *args, **kwargs):
    start = perf_counter_ns()
    result = function(*args, **kwargs)
    cost[name] = cost.get(name, 0) + perf_counter_ns() - start
    return result


def _bc(meshes, ids):
    return surface_distance(*(SurfaceIndex(meshes[key].world_m, meshes[key].triangles) for key in ids))


def _clearance_truth(meshes, ids, surface, expected, tolerance):
    points = (surface.point_a, surface.point_b)
    triangles = tuple(meshes[key].world_m[meshes[key].triangles].tolist() for key in ids)
    return {
        "target_ids": list(ids),
        "distance_m": _number(surface.distance_m),
        "triangle_a": surface.triangle_a, "triangle_b": surface.triangle_b,
        "point_a": points[0], "point_b": points[1],
        "triangles_a": triangles[0] if points[0] is not None else None,
        "triangles_b": triangles[1] if points[1] is not None else None,
        "analytic_distance_m": expected, "analytic_tol_m": tolerance,
    }


def _object_facts(meshes, generation=1, *, positions=False):
    facts = []
    for key, mesh in meshes.items():
        center = None
        if positions:
            center = _plain_point((mesh.world_m.min(axis=0) + mesh.world_m.max(axis=0)) / 2.0)
        facts.append(ObjectFact(key, generation, center))
    return tuple(facts)


def _observation_truth(observation, *, clearance=None, deformation=None, image=None):
    return {
        "observation_id": observation.observation_id,
        "frame_id": observation.frame_id,
        "objects": {
            obj.object_id: {
                "topology_generation": obj.topology_generation, "center_m": obj.center_m,
            } for obj in observation.objects
        },
        "clearance": clearance, "deformation": deformation, "image": image,
    }


def _with_clearance(case, state, frame, meshes, ids, surface, expected, tolerance,
                    *, step=0, generation=1, image=None):
    observation = ObservationFact(
        _oid(case, state, step), frame, _object_facts(meshes, generation, positions=image is not None),
        ClearanceFact(ids, surface), None, image,
    )
    image_truth = None if image is None else {
        "path": image.path, "metadata": image.rendered.metadata,
        "png_sha256": sha256(image.rendered.png).hexdigest(),
    }
    truth = _observation_truth(
        observation, clearance=_clearance_truth(meshes, ids, surface, expected, tolerance),
        image=image_truth,
    )
    return observation, truth


@contextmanager
def _scene(name, scale, frame):
    scene = bpy.data.scenes.new(name)
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = scale
    scene.frame_set(frame)
    try:
        yield scene
    finally:
        objects = tuple(scene.objects)
        meshes = tuple(obj.data for obj in objects if obj.type == "MESH")
        materials = {material for mesh in meshes for material in mesh.materials}
        bpy.data.scenes.remove(scene)
        for obj in objects:
            bpy.data.objects.remove(obj)
        for mesh in meshes:
            bpy.data.meshes.remove(mesh)
        for material in materials:
            bpy.data.materials.remove(material)


def _native_capture(scene, objects, bridge, changes=None):
    with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
        graph = bpy.context.evaluated_depsgraph_get()
        graph.update()
        scale = scene.unit_settings.scale_length
        return {
            key: bridge.capture(key, obj, graph, scale,
                                MeshChange.NONE if changes is None else changes.get(key, MeshChange.NONE))
            for key, obj in objects.items()
        }


def _parent_case(state, cost):
    ids = _ids(3)
    frame = 3 + state
    with _scene("AO03", 0.001, frame) as scene:
        parent = bpy.data.objects.new("AO03 Parent", None)
        scene.collection.objects.link(parent)
        parent.rotation_euler.z = pi / 2
        parent.location = (10 + state, 20, 30)
        points, faces = _centered_box((0, 0, 0), (1, 1, 1))
        material = _material("AO03", COLOR_A)
        objects = {key: _object(scene, key, points, faces, material, 0) for key in ids}
        for obj in objects.values():
            obj.parent = parent
            obj.scale = (-2, 0.5, 1.25)
        objects[ids[1]].location.x = 3
        meshes = _measure(cost, "rb_ns", _native_capture, scene, objects, BlenderResidentBridge())
        parent_linear = np.array([[0, -0.5, 0], [-2, 0, 0], [0, 0, 1.25]])
        for side, key in enumerate(ids):
            expected = (np.asarray(points) @ parent_linear.T + [10 + state, 20 + 3 * side, 30]) * 0.001
            np.testing.assert_allclose(meshes[key].world_m, expected, rtol=0, atol=4e-9)
        surface = _measure(cost, "bc_ns", _bc, meshes, ids)
        return _with_clearance(3, state, frame, meshes, ids, surface, 0.001, 4e-9)


def _array_case(case, state, cost):
    ids = _ids(1 if case == 8 else case)
    a = _UNIT_BOX
    b = _box((2, 3), (0, 1), (0, 1))
    expected, tolerance = 1.0, 1e-13
    if case == 2:
        b = _box((1 + 4e-7, 2 + 4e-7), (0, 1), (0, 1))
        expected, tolerance = 4e-7, 4e-16
    elif case == 4:
        a = _box((-2, 2), (-2, 2), (-2, 2))
        b = _box((-1, 1), (-1, 1), (-1, 1))
    elif case == 5:
        b = _box((1, 2), (0, 1), (0, 1))
        expected = 0.0
    elif case == 6:
        a = (((0, 0, 0), (2, 0, 0), (0, 2, 0)), ((0, 1, 2),))
        b = (((0.5, 0.5, -1), (0.5, 0.5, 1), (1.25, 0.5, 0)), ((0, 1, 2),))
        expected = 0.0
    elif case == 7:
        b = (b[0], ())
        expected = None
    elif case == 8:
        a = (a[0], np.roll(np.asarray(a[1])[::-1], state, axis=0))
        b = (b[0], np.roll(np.asarray(b[1]), 3 + state, axis=0))
        ids, a, b = ids[::-1], b, a

    bridge = ResidentBridge()
    transform = np.eye(4)
    transform[:3, 3] = _OFFSET * state
    meshes = {
        key: _measure(cost, "rb_ns", bridge.add, key, np.asarray(points, dtype=np.float64),
                      np.asarray(faces, dtype=np.int32).reshape(-1, 3), transform)
        for key, (points, faces) in zip(ids, (a, b))
    }
    surface = _measure(cost, "bc_ns", _bc, meshes, ids)
    generation = 2 + state if case == 8 else 1
    return _with_clearance(case, state, case + state, meshes, ids, surface, expected, tolerance,
                           generation=generation)


def _td_geometry(case):
    ref = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
    tris = np.array([[0, 1, 2]], dtype=np.int32)
    ref_frame, sample_frames, top_k = 7, (8,), 1
    if case == 9:
        frames = (ref * [2, 0.5, 1],)
        analytic = {0: dict(zip(_METRICS[:3], (2.0, 0.5, 0.0)))}
    elif case == 10:
        angle = 2 * pi / 3
        rotation = np.array([[1, 0, 0], [0, cos(angle), -sin(angle)], [0, sin(angle), cos(angle)]])
        frames = (ref @ rotation.T,)
        analytic = {0: dict(zip(_METRICS[:4], (1.0, 1.0, 0.0, 120.0)))}
    elif case == 11:
        frames = (np.full_like(ref, [0.25, 0.25, 0.0]),)
        analytic = {0: {"min_principal_stretch": 0.0, "max_area_strain": 1.0,
                        "max_normal_angle_deg": None}}
    elif case == 12:
        ref[2] = [2, 0, 0]
        frames = (ref + [0, 0, 0.25],)
        analytic = {0: dict(zip(_METRICS, (None, None, None, None, 0.25, None)))}
    elif case == 13:
        origins = np.array([(i, j, 0) for j in range(7) for i in range(10)], dtype=np.float64)
        ref = (origins[:, None, :] + [[0, 0, 0], [3/8, 0, 0], [0, 3/8, 0]]).reshape(-1, 3)
        tris = np.arange(len(ref), dtype=np.int32).reshape(-1, 3)
        frames = (ref + [1/64, 0, 0],)
        top_k = 6
        score = (1 / 64) / ((9 + 3/8)**2 + (6 + 3/8)**2)**0.5
        analytic = {i: dict(zip(_METRICS, (1.0, 1.0, 0.0, 0.0, 1 / 64, score))) for i in range(6)}
    else:
        ref_frame, sample_frames = 3, (7, 11, 19)
        frames = tuple(ref * scales for scales in ((1.25, 0.8, 1), (0.5, 1, 1), (1.5, 1.25, 1)))
        analytic = {0: dict(zip(_METRICS[:4], (1.5, 0.5, 0.875, 0.0)))}
    return ref, tris, ref_frame, frames, sample_frames, top_k, analytic


def _td_case(case, state, cost):
    ref, triangles, ref_frame, frames, sample_frames, top_k, analytic = _td_geometry(case)
    key = _ids(case)[0]
    bridge = ResidentBridge()
    transform = np.eye(4)
    transform[:3, 3] = _OFFSET * state
    start = perf_counter_ns()
    mesh = bridge.add(key, ref, triangles, transform)
    reference_m = mesh.world_m.copy()
    samples_m = tuple(bridge.update_full(key, vertices).world_m.copy() for vertices in frames)
    cost["rb_ns"] = perf_counter_ns() - start
    metrics = _measure(cost, "td_ns", compute_cross_frame_deformation_tensor, samples_m, mesh.triangles,
                       reference_vertices=reference_m, top_k=top_k)
    selected = () if case == 13 else (0,)
    latest = samples_m[-1]
    deformation = DeformationFact(
        key, ref_frame, sample_frames, metrics, mesh.triangles, sample_frames[-1], latest, selected,
    )
    observation = ObservationFact(
        _oid(case, state), sample_frames[-1], (ObjectFact(key, 1, None),), None, deformation, None,
    )
    top_ids = list(map(int, metrics["witness_triangle_ids"]))
    ids = list(dict.fromkeys((*top_ids, *selected)))
    rows = []
    for row in ids:
        vertices = latest[triangles[row]]
        # Match the public mean definition independently of the encoder.
        position = _plain_point(vertices.mean(axis=0))
        rows.append({
            "original_face_id": row, "position_m": position,
            **{metric: _number(metrics[metric][row]) for metric in _METRICS},
        })
    truth = {
        "object_id": key, "reference_frame": ref_frame, "sample_frames": list(sample_frames),
        "reduced_face_count": len(triangles), "top_face_ids": top_ids, "position_kind": "face_centroid",
        "position_frame": sample_frames[-1], "faces": rows,
        "analytic_metrics": {str(row): values for row, values in analytic.items()},
    }
    if case == 13:
        truth["analytic_top_face_ids"] = list(range(6))
        truth["analytic_positions_m"] = {
            str(i): _plain_point(np.array([i + 1/8 + 1/64, 1/8, 0]) + transform[:3, 3])
            for i in range(6)
        }
    return observation, _observation_truth(observation, deformation=truth)


def _tetra_pair(scene, ids, gap, angle=0.0):
    a, b = ids
    points_a = [(S * x, S * y, S * z) for x, y, z in TETRA_POINTS]
    points_b = [(gap - x, y, z) for x, y, z in points_a]
    return {
        a: _object(scene, a, points_a, TETRA_FACES, _material(a, COLOR_A), angle),
        b: _object(scene, b, points_b, tuple((i, k, j) for i, j, k in TETRA_FACES),
                   _material(b, COLOR_B), angle),
    }


class _PublicImages:
    def __init__(self, renderer, public_dir):
        self.renderer = renderer
        self.public_dir = public_dir
        self.counter = 0
        (public_dir / "images").mkdir(parents=True, exist_ok=True)

    def render(self, cost, scene, meshes, surface, ids, mode="NATURAL"):
        prepared = _measure(cost, "vg_prepare_ns", self.renderer.prepare, meshes)
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            rendered = _measure(
                cost, "vg_observe_ns", self.renderer.observe, prepared, surface,
                target_ids=ids, frame_id=scene.frame_current,
                scale_length=scene.unit_settings.scale_length, mode=mode,
            )
        self.counter += 1
        path = f"images/{self.counter:04d}.png"
        _measure(cost, "png_write_ns", (self.public_dir / path).write_bytes, rendered.png)
        return ImageFact(path, rendered)


def _vg_frozen_case(case, state, images, cost):
    fixture_id, family = (0, "F1") if case == 15 else (21, "F6")
    mode = "NATURAL" if case == 15 else "SECTION"
    if state == 0:
        fixture = build_fixture(fixture_id)
    else:
        angle, gap = VARIANTS[1 if case == 15 else 2]
        fixture = _build(fixture_id, family, angle, gap, mode)
    try:
        cost.update({"native_scene_build_ns": fixture.build_ns, "rb_ns": fixture.rb_ns,
                     "bc_ns": fixture.bc_ns})
        image = images.render(cost, fixture.scene, fixture.meshes, fixture.witness, fixture.target_ids, mode)
        return _with_clearance(
            case, state, fixture.frame_id, fixture.meshes, fixture.target_ids, fixture.witness,
            fixture.expected_gap_m, 1e-8, image=image,
        )
    finally:
        fixture.close()


def _decoy_case(state, task, images, cost):
    case, frame = 17, 17 + state
    ids = _ids(case)
    # The decoy is visibly distinct in position and shares A's actual material.
    decoy_id = "O17-C"
    gap = 0.004 + state * 0.002
    with _scene("AO17", 1.0, frame) as scene:
        objects = _tetra_pair(scene, ids, gap)
        points, faces = _centered_box((-0.07, 0.055 + 0.01 * state, 0.035), (0.026, 0.026, 0.026))
        objects[decoy_id] = _object(scene, decoy_id, points, faces, objects[ids[0]].data.materials[0], 0)
        meshes = _measure(cost, "rb_ns", _native_capture, scene, objects, BlenderResidentBridge())
        surface = _measure(cost, "bc_ns", _bc, meshes, ids)
        image = images.render(cost, scene, meshes, surface, ids)
        task.update({"target_id": ids[0], "decoy_id": decoy_id})
        return _with_clearance(case, state, frame, meshes, ids, surface, gap, 1e-8, image=image)


def _sequence_case(state, task, images, cost):
    case = 18
    ids = _ids(case)
    first_gap = 0.001 + state * 0.0005
    shift = 0.003 + state * 0.0005
    task["requested_frame"] = 8
    with _scene("AO18", 1.0, 7) as scene:
        objects = _tetra_pair(scene, ids, first_gap)
        moving = objects[ids[1]]
        moving.keyframe_insert(data_path="location", frame=7)
        moving.location.x = shift
        moving.keyframe_insert(data_path="location", frame=8)
        bridge = BlenderResidentBridge()
        observations, truth = [], []
        for step, frame in enumerate((7, 8)):
            _measure(cost, "host_frame_set_ns", scene.frame_set, frame)
            meshes = _measure(cost, "rb_ns", _native_capture, scene, objects, bridge,
                              {ids[1]: MeshChange.TRANSFORM} if step else None)
            surface = _measure(cost, "bc_ns", _bc, meshes, ids)
            image = images.render(cost, scene, meshes, surface, ids)
            item, expected = _with_clearance(case, state, frame, meshes, ids, surface,
                                             first_gap + step * shift, 1e-8, step=step, image=image)
            observations.append(item)
            truth.append(expected)
        return tuple(observations), truth


def _select_action(payload, task):
    """Select only from an actual public observation and explicit task intent."""
    public = decode_public(payload, public_schema())
    observation, = public["observations"]
    clearance = observation["clearance"]
    ids = tuple(public["object_ids"][index] for index in clearance["target_object_indices"])
    goal = Goal(**task["goal"])
    assert ids == (goal.moving_id, goal.reference_id)
    requested = task["command"]
    if requested["kind"] == "translate":
        command = Translate(tuple(requested["delta_world_m"]))
    else:
        command = SetShapeKey(requested["key_name"], requested["target_value"])
    return Action("act-" + observation["observation_id"], observation["observation_id"], command)


def _outcome_truth(outcome, task):
    action, goal = outcome.action, outcome.goal
    return {
        "action_id": action.action_id,
        "before_observation_id": outcome.before.observation_id,
        "after_observation_id": outcome.after.observation_id,
        "goal": {"moving_id": goal.moving_id, "reference_id": goal.reference_id,
                 "target_distance_m": goal.distance_m, "tolerance_m": goal.tolerance_m},
        "command": task["command"], "control_before": outcome.control_before,
        "control_after": outcome.control_after,
        "distance_before_m": _number(outcome.before.surface.distance_m),
        "distance_after_m": _number(outcome.after.surface.distance_m),
        "measured_delta_m": outcome.measured_delta_m, "predicted_delta_m": action.predicted_delta_m,
        "goal_reached": outcome.goal_reached,
    }


def _action_case(case, state, task, images, cost, encode_baseline):
    ids = _ids(case)
    frame = case + state
    with _scene(f"AO{case}", 1.0, frame) as scene:
        if case == 19:
            initial_gap = 1.0 + 0.125 * state
            translation = 0.025
            target_gap = initial_gap + translation
            boxes = (_UNIT_BOX, _box((1 + initial_gap, 2 + initial_gap), (0, 1), (0, 1)))
            objects = {
                key: _object(scene, key, points, faces, _material(key, color), 0)
                for key, (points, faces), color in zip(ids, boxes, (COLOR_A, COLOR_B))
            }
            control_ids = ids[::-1]
            tolerance = 2e-7
            command = {"kind": "translate", "delta_world_m": [translation, 0.0, 0.0],
                       "key_name": None, "target_value": None}
        else:
            initial_gap = 0.004 + 0.001 * state
            target_gap = initial_gap - 0.0015
            objects = _tetra_pair(scene, ids, initial_gap)
            control_ids = ids
            tolerance = 1e-8
            moving = objects[ids[0]]
            moving.shape_key_add(name="Basis")
            shape = moving.shape_key_add(name="Advance Tip")
            shape.data[0].co.x += 0.003
            shape.value = 0.0
            command = {"kind": "set_shape_key", "delta_world_m": None, "key_name": shape.name,
                       "target_value": 0.5}
        task["goal"] = {"moving_id": control_ids[0], "reference_id": control_ids[1],
                        "distance_m": target_gap, "tolerance_m": tolerance}
        task["command"] = command
        goal = Goal(**task["goal"])
        controller = BlenderControl(scene, objects, goal)
        before = _measure(cost, "action_initial_rb_bc_ns", controller.observe, _oid(case, state))
        meshes = {key: controller.bridge.get(key) for key in ids}
        before_image = images.render(cost, scene, meshes, before.surface, before.target_ids) if case == 20 else None
        before_observation, before_truth = _with_clearance(
            case, state, before.frame_id, meshes, before.target_ids, before.surface,
            initial_gap, tolerance, image=before_image,
        )
        before_package = AffordancePackage((before_observation,), None)
        payload = _measure(cost, "action_delivery_ns", encode, before_package)
        action = _measure(cost, "action_public_select_ns", _select_action, payload, task)
        _measure(cost, "action_evidence_write_ns",
                 (images.public_dir / f"candidate-before-{case:02d}.json").write_bytes, payload)
        if encode_baseline is not None:
            baseline = _measure(cost, "baseline_action_delivery_ns", encode_baseline, before_package)
            assert _measure(cost, "baseline_action_public_select_ns", _select_action, baseline, task) == action
            _measure(cost, "action_evidence_write_ns",
                     (images.public_dir / f"baseline-before-{case:02d}.json").write_bytes, baseline)
        outcome = _measure(cost, "action_write_readback_ns", controller.execute, action, _oid(case, state, 1))
        assert outcome is not None and outcome.goal_reached
        if case == 20:
            assert (outcome.control_before, outcome.control_after) == (0.0, 0.5)
        after = outcome.after
        meshes = {key: controller.bridge.get(key) for key in ids}
        after_image = images.render(cost, scene, meshes, after.surface, after.target_ids) if case == 20 else None
        after_observation, after_truth = _with_clearance(
            case, state, after.frame_id, meshes, after.target_ids, after.surface,
            target_gap, tolerance, step=1, image=after_image,
        )
        assert encode(before_package) == payload, "The old public observation changed after a real RB update"
        return (before_observation, after_observation), [before_truth, after_truth], outcome


def build_state(state, public_dir, *, encode_baseline=None):
    """Return the 20 real packages, public questions, private oracle, costs and GPU environment."""
    if state not in (0, 1):
        raise ValueError("AO accepts exactly the frozen states 0 and 1")
    packages, tasks, oracles, costs = [], [], [], []
    state_start = perf_counter_ns()
    renderer = VGRenderer()
    init_ns = perf_counter_ns() - state_start
    try:
        images = _PublicImages(renderer, public_dir)
        for case, question in enumerate(_QUESTIONS, 1):
            case_start = perf_counter_ns()
            task = {"id": f"{case:02d}", "question": question}
            cost = {"id": task["id"]}
            outcome = None
            if case < 9:
                observation, truth = _parent_case(state, cost) if case == 3 else _array_case(case, state, cost)
            elif case < 15:
                observation, truth = _td_case(case, state, cost)
            elif case < 17:
                observation, truth = _vg_frozen_case(case, state, images, cost)
            elif case == 17:
                observation, truth = _decoy_case(state, task, images, cost)
            elif case == 18:
                observations, oracle = _sequence_case(state, task, images, cost)
            else:
                observations, oracle, outcome = _action_case(case, state, task, images, cost, encode_baseline)
            if case < 18:
                observations, oracle = (observation,), [truth]
            packages.append(AffordancePackage(observations, outcome))
            tasks.append(task)
            oracles.append({"observations": oracle, "outcome": None if outcome is None else _outcome_truth(outcome, task)})
            cost["fixture_case_wall_ns"] = perf_counter_ns() - case_start
            costs.append(cost)
        environment = {
            "gpu_vendor": gpu.platform.vendor_get(), "gpu_renderer": gpu.platform.renderer_get(),
            "gpu_backend": gpu.platform.backend_type_get(), "gpu_version": gpu.platform.version_get(),
            "vg_init_ns": init_ns, "fixture_state_wall_ns": perf_counter_ns() - state_start,
        }
    finally:
        renderer.close()
    return tuple(packages), tasks, oracles, costs, environment
