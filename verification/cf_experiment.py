"""Native stages for the frozen CF experiment. Invoked by the benchmark driver."""

from contextlib import contextmanager
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
from io import BytesIO
from pathlib import Path
from struct import unpack
from time import perf_counter_ns
from zipfile import ZIP_STORED, ZipFile

import bpy
import gpu
import numpy as np

from human_eye_fast.cerebellar_flash import view_features
from human_eye_fast.fast_affordance_out import AffordancePackage, encode, public_schema
from human_eye_fast.raycast_saccade_gpu import VGRenderer
from verification.cf_fixtures import SEEDS, CommandSpec, EpisodeSpec, build_fixture
from verification.cf_native import ActionEpisode, ViewEpisode, materialize, observation
from verification.cf_training import load_candidates, load_frozen
from verification.cf_visual_acceptance import PillowWorker, VisualAudit, negative_controls, observe
from verification.test_bc_acceptance import surface_tolerance
from verification.test_blender_control import _assert_witness
from verification.test_fast_affordance_out import decode_public


def _json(value):
    def convert(item):
        if isinstance(item, np.generic):
            return item.item()
        if isinstance(item, np.ndarray):
            return item.tolist()
        raise TypeError(type(item))
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=convert)


def write_json(path, value):
    path.write_text(_json(value) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_bytes())


def _digest(data):
    return sha256(data).hexdigest()


class Inputs:
    """Record each actual benchmark data open, before use."""

    def __init__(self, out):
        self.path = out / "reads.jsonl"

    def track(self, path):
        path = Path(path)
        data = path.read_bytes()
        with self.path.open("a", encoding="utf-8") as log:
            log.write(_json({"path": str(path.resolve()), "sha256": _digest(data),
                             "bytes": len(data)}) + "\n")
        return data

    def specs(self, path, seed, split):
        rows = json.loads(self.track(path))["episodes"]
        result = {"V": [], "A": []}
        for row in rows:
            assert (row["seed"], row["split"]) == (seed, split)
            cmd = row["command"]
            row["command"] = CommandSpec(**cmd) if cmd else None
            result[row["head"]].append(EpisodeSpec(**row))
        return result

    def candidates(self, path):
        self.track(path)
        return load_candidates(path)

    def frozen(self, path):
        self.track(path)
        self.track(path.with_suffix(".json"))
        return load_frozen(path)


@contextmanager
def evidence(out):
    with ZipFile(out / "media.zip", "w", compression=ZIP_STORED) as media:
        with gzip.open(out / "records.jsonl.gz", "wt", encoding="utf-8", compresslevel=3) as raw:
            yield media, raw


def _record(raw, value):
    raw.write(_json(value) + "\n")
    raw.flush()


def _env():
    import os
    import platform
    return {"pid": os.getpid(), "blender": bpy.app.version_string,
            "build": bpy.app.build_hash.decode(), "numpy": np.__version__,
            "platform": platform.platform(), "cpu": platform.processor(),
            "gpu": gpu.platform.renderer_get(), "driver": gpu.platform.version_get(),
            "backend": gpu.platform.backend_type_get(),
            "threads": {name: os.environ.get(name) for name in (
                "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")}}


def _spec_summary(spec):
    return {"id": spec.episode_id, "group": spec.group_id, "family": spec.family,
            "mode": spec.mode, "scale_m": spec.scale_m}


class ViewAuditEpisode:
    def __init__(self, scene, renderer):
        self.scene = scene
        self.renderer = renderer
        self.meshes, self.surface = scene.capture()
        native = scene.native
        self.audit = VisualAudit(native.snapshot(), native.targets, native.scene.frame_current,
                                 native.fixture.mode, native.scale_length, self.surface)
        self.prepared = renderer.prepare(self.meshes)

    @property
    def spec(self):
        return self.scene.native.fixture.spec

    def forced(self, index, scorer, media, raw, key_sink=None):
        callback = None
        if key_sink is not None:
            context = tuple((mesh.world_m, mesh.triangles) for key, mesh in self.meshes.items()
                            if key not in self.scene.native.targets)

            def callback(directions):
                key_sink.append(view_features(self.surface.point_a, self.surface.point_b, directions,
                                              context, section=self.spec.mode == "SECTION"))
                return (index,)

        image, audit = observe(self.renderer, self.prepared, self.audit, rank_directions=callback,
                               canonical_order=(index,))
        return self.save(image, audit, f"forced-{index:02d}", scorer, media, raw)

    def arm(self, arm, model, scorer, media, raw, *, display=None):
        rank, features = self.scene.ranker(self.meshes, self.surface, model, arm)
        image, audit = observe(self.renderer, self.prepared, self.audit, rank_directions=rank)
        row = self.save(image, audit, arm if display is None else display, scorer, media, raw)
        return row, image, features

    def save(self, image, audit, arm, scorer, media, raw):
        start = perf_counter_ns()
        scored = scorer.score(image.png, audit)
        score_ns = perf_counter_ns() - start
        base = f"{self.spec.episode_id}/{arm}"
        media.writestr(f"{base}.png", image.png)
        selected = audit["candidate"]
        selected_rays = audit.get("selected_rays")
        if selected_rays is None:
            selected_rays = sum(ray["candidate"] == selected for ray in audit["trace"])
        row = {**_spec_summary(self.spec), "arm": arm, "rays": audit["ray_count"],
               "success": scored["passed"], "safe": scored["safe"], "candidate": selected,
               "selected_rays": selected_rays, "native_stop": audit["native_stop"],
               "png_sha256": _digest(image.png), "score_ns": score_ns,
               "frame_id": image.metadata["frame_id"], "targets": image.metadata["target_ids"],
               "witness": image.metadata["witness"]}
        _record(raw, {**row, "media": f"{base}.png", "audit": audit, "score": scored})
        return row


def _check_action_wire(before, after, result, native):
    old, new = after["observations"]
    outcome = after["outcome"]
    ids = tuple(after["object_ids"])
    expected = result.outcome
    if ids != native.targets or before["observations"] != [old]:
        raise ValueError("Action observation identity or binding")
    if old["observation_id"] != expected.before.observation_id or (
            new["observation_id"] != expected.after.observation_id):
        raise ValueError("Wrong action observation ID")
    if old["frame_id"] != expected.before.frame_id or new["frame_id"] != expected.after.frame_id:
        raise ValueError("Wrong action frame")
    if outcome["before_observation_id"] != old["observation_id"] or (
            outcome["after_observation_id"] != new["observation_id"]):
        raise ValueError("Wrong outcome reference")
    if (ids[outcome["goal"]["moving_object_index"]], ids[outcome["goal"]["reference_object_index"]]) != native.targets:
        raise ValueError("Wrong action target")
    if (outcome["control_before"], outcome["control_after"]) != (
        list(expected.control_before) if isinstance(expected.control_before, tuple) else expected.control_before,
        list(expected.control_after) if isinstance(expected.control_after, tuple) else expected.control_after,
    ):
        raise ValueError("Wrong measured control")
    if (outcome["distance_before_m"], outcome["distance_after_m"], outcome["measured_delta_m"],
        outcome["predicted_delta_m"]) != (expected.before.surface.distance_m,
                                          expected.after.surface.distance_m,
                                          expected.measured_delta_m, result.prediction):
        raise ValueError("Wrong action distance or result")
    for row, readback, image in zip((old, new), (expected.before, expected.after),
                                    (result.before_png, result.after_png)):
        if tuple(ids[i] for i in row["clearance"]["target_object_indices"]) != native.targets:
            raise ValueError("Wrong clearance targets")
        clearance = row["clearance"]
        for key, face, point in (("witness_a", readback.surface.triangle_a, readback.surface.point_a),
                                 ("witness_b", readback.surface.triangle_b, readback.surface.point_b)):
            if clearance[key]["original_face_id"] != face or clearance[key]["point_m"] != list(point):
                raise ValueError("Wrong action witness")
        if image is not None:
            fact = row["image"]
            if (fact["path"] != f"{row['observation_id']}.png" or fact["mode"] != "NATURAL" or
                    tuple(ids[i] for i in fact["target_object_indices"]) != native.targets or
                    image.metadata["frame_id"] != row["frame_id"] or
                    tuple(image.metadata["target_ids"]) != native.targets or
                    image.metadata["witness"]["distance_m"] != readback.surface.distance_m):
                raise ValueError("Wrong action image binding")
            if image.png[:8] != b"\x89PNG\r\n\x1a\n" or unpack(">II", image.png[16:24]) != (
                fact["width_px"], fact["height_px"],
            ):
                raise ValueError("Wrong native PNG dimensions")


def _verify_action(result, native, *, negatives=False):
    from copy import deepcopy
    schema = public_schema()
    old = decode_public(result.before_payload, schema)
    new = decode_public(result.after_payload, schema)
    _check_action_wire(old, new, result, native)
    outcome = result.outcome
    assert outcome.measured_delta_m == outcome.after.surface.distance_m - outcome.before.surface.distance_m
    tolerances = []
    for observed, snapshot in ((outcome.before, result.native_before), (outcome.after, result.native_after)):
        a, b = (snapshot[key] for key in native.targets)
        tolerances.append(surface_tolerance(*a, *b))
        as_rows = {key: {"world_vertices_m": vertices, "triangles": triangles}
                   for key, (vertices, triangles) in snapshot.items()}
        _assert_witness(observed, as_rows, observed.surface.distance_m, tolerances[-1])
    command = native.fixture.command
    if native.key is not None:
        assert abs(outcome.control_before - command.control_before) <= np.finfo(np.float32).eps
        assert native.key.value == outcome.control_after
        if native.fixture.spec.family == "shape-readback-clamp":
            assert abs(outcome.control_after - command.target_value) > np.finfo(np.float32).eps
        else:
            assert abs(outcome.control_after - command.target_value) <= np.finfo(np.float32).eps
    if native.fixture.expected_delta_m is not None:
        maximum = max(native.fixture.spec.scale_m, *(np.linalg.norm(mesh.vertices_m, axis=1).max()
                       for mesh in native.fixture.meshes))
        budget = sum(tolerances) + 64 * np.finfo(np.float32).eps * maximum
        assert abs(outcome.measured_delta_m - native.fixture.expected_delta_m) <= budget
        assert abs(result.comparison["G"] - native.fixture.expected_delta_m) <= budget
    checks = {}
    if negatives:
        for name in ("frame", "object", "control", "measured_delta", "observation"):
            forged = deepcopy(new)
            if name == "frame":
                forged["observations"][1]["frame_id"] += 1
            elif name == "object":
                forged["outcome"]["goal"]["moving_object_index"] = 1
            elif name == "control":
                forged["outcome"]["control_after"] = forged["outcome"]["control_before"]
            elif name == "measured_delta":
                forged["outcome"]["measured_delta_m"] += .02
            else:
                forged["outcome"]["after_observation_id"] = "before"
            try:
                _check_action_wire(old, forged, result, native)
            except ValueError:
                checks[name] = True
            else:
                raise AssertionError(f"Accepted forged action evidence {name}")
    return float(sum(tolerances)), checks


def _action_data(spec, renderer, media, raw, *, model=None, constant=None, shuffle=None,
                 negatives=False, label_only=False):
    with materialize(build_fixture(spec)) as native:
        episode = ActionEpisode(native)
        arm = ("L" if model else "G") if not label_only else None
        result = episode.run(renderer, arm, model=model, constant=constant, shuffle=shuffle,
                             collect=True, snapshots=True)
        budget, checks = _verify_action(result, native, negatives=negatives)
        outcome = result.outcome
        base = spec.episode_id
        media.writestr(f"{base}/before.json", result.before_payload)
        media.writestr(f"{base}/after.json", result.after_payload)
        for name, image in (("before", result.before_png), ("after", result.after_png)):
            if image is not None:
                media.writestr(f"{base}/{name}.png", image.png)
        row = {**_spec_summary(spec), "sign": spec.command.sign, "amplitude": spec.command.amplitude,
               "measured_delta_m": outcome.measured_delta_m, "delta_budget_m": budget,
               "comparison": result.comparison, "contact": outcome.after.surface.distance_m == 0,
               "control_before": outcome.control_before, "control_after": outcome.control_after,
               "distance_before_m": outcome.before.surface.distance_m,
               "distance_after_m": outcome.after.surface.distance_m,
               "feature_scale_m": result.meters, "success": True, "negative_controls": checks}
        _record(raw, {**row, "features": result.features, "group_key": result.group,
                      "outcome": asdict(outcome), "native_before": result.native_before,
                      "native_after": result.native_after})
        return row, result


def collect(specs, renderer, scorer, out):
    started = perf_counter_ns()
    v_keys, v_feedback, a_keys, a_scales, a_labels, a_groups = [], [], [], [], [], []
    with evidence(out) as (media, raw):
        media.writestr("ao-schema.json", _json(public_schema()))
        for i, spec in enumerate(specs["V"]):
            with materialize(build_fixture(spec)) as native, native.context():
                episode = ViewAuditEpisode(ViewEpisode(native), renderer)
                keys = []
                scores = [episode.forced(j, scorer, media, raw, keys if j == 0 else None)
                          for j in range(16)]
                v_keys.append(keys[0])
                v_feedback.append([(int(row["safe"]), row["rays"]) for row in scores])
            if i % 12 == 11:
                print(f"{spec.seed} {spec.split} V labels {i + 1}/{len(specs['V'])}", flush=True)
        for i, spec in enumerate(specs["A"]):
            row, result = _action_data(spec, None, media, raw, label_only=True)
            a_keys.append(result.features)
            a_scales.append(result.meters)
            a_labels.append(row["measured_delta_m"])
            a_groups.append(result.group)
            if i % 30 == 29:
                print(f"{spec.seed} {spec.split} A labels {i + 1}/{len(specs['A'])}", flush=True)
    np.savez(out / "view.npz", keys=v_keys, feedback=v_feedback)
    np.savez(out / "action.npz", keys=a_keys, scales=a_scales, labels_m=a_labels, groups=a_groups)
    write_json(out / "provenance.json", {"view": [s.episode_id for s in specs["V"]],
                                         "action": [s.episode_id for s in specs["A"]]})
    write_json(out / "summary.json", {"elapsed_ns": perf_counter_ns() - started,
                                     "environment": _env()})


def validate(specs, renderer, scorer, out, candidates):
    arms = {"F": None, "R": candidates.session()}
    arms.update({f"L{i}": candidates.session(view=i) for i in range(4)})
    rows = {arm: [] for arm in arms}
    with evidence(out) as (media, raw):
        for spec in specs["V"]:
            with materialize(build_fixture(spec)) as native, native.context():
                episode = ViewAuditEpisode(ViewEpisode(native), renderer)
                for arm, model in arms.items():
                    row, *_ = episode.arm(arm if arm in ("F", "R") else "L", model, scorer,
                                          media, raw, display=arm)
                    rows[arm].append(row)
    write_json(out / "views.json", rows)


def _control_view(spec, renderer, scorer, media, raw):
    with materialize(build_fixture(spec)) as native, native.context():
        scene = ViewEpisode(native)
        if spec.family == "empty":
            meshes, surface = scene.capture()
            assert np.isinf(surface.distance_m) and surface.point_a is None and surface.point_b is None
            payload = encode(AffordancePackage((observation(native, meshes, surface, "empty", None),)))
            decoded = decode_public(payload, public_schema())["observations"][0]
            assert decoded["image"] is None and decoded["clearance"]["status"] == "empty_surface"
            media.writestr(f"{spec.episode_id}/empty.json", payload)
            return {**_spec_summary(spec), "success": True, "rays": 0}
        episode = ViewAuditEpisode(scene, renderer)
        row, _, _ = episode.arm("F", None, scorer, media, raw)
        if spec.family == "contact":
            passed = row["success"] and row["rays"] == 0 and episode.surface.distance_m == 0
        elif spec.family == "enclosed":
            passed = not row["success"] and not row["native_stop"]
        else:
            passed = row["success"] and row["native_stop"] and row["candidate"] == 0
        return {**row, "pixel_success": row["success"], "success": passed}


def _prequential(v_specs, a_specs, renderer, scorer, out, frozen):
    # Own deployment object. Freeze/eval/timing sessions never query this one.
    from time import perf_counter_ns
    model = frozen.session()
    rows = []
    with evidence(out) as (media, raw):
        for index, (v, a) in enumerate(zip(v_specs[:2], a_specs[:2])):
            start = perf_counter_ns()
            before_counts = (model.views.writes, model.actions.writes)
            view_weights = model.view_head.weights.copy()
            action_weights = model.action_head.weights.copy()
            with materialize(build_fixture(v)) as native, native.context():
                episode = ViewAuditEpisode(ViewEpisode(native), renderer)
                result, _, features = episode.arm("L", model, scorer, media, raw)
            assert model.views.writes == before_counts[0]
            model.learn_view(features[0], result["candidate"], result["safe"], result["selected_rays"])
            action, outcome = _action_data(a, renderer, media, raw, model=model,
                                           constant=frozen.reference)
            assert model.actions.writes == before_counts[1]
            model.learn_action(outcome.features, outcome.meters, action["measured_delta_m"])
            assert (model.views.writes, model.actions.writes) == (before_counts[0] + 1, before_counts[1] + 1)
            changes = [float(np.linalg.norm(model.view_head.weights - view_weights)),
                       float(np.linalg.norm(model.action_head.weights - action_weights))]
            assert min(changes) > 0
            rows.append({"step": index, "view": result, "action": action, "before_writes": before_counts,
                         "weight_change": changes, "elapsed_ns": perf_counter_ns() - start,
                         "success": True})
    return rows


def _completed_main(specs, encoded_rows):
    """Read the already emitted main rows after the known control-only transport failure."""
    views = {arm: [] for arm in ("F", "R", "L", "zero", "shuffle")}
    actions = []
    forced = {}
    for line in gzip.GzipFile(fileobj=BytesIO(encoded_rows)):
        row = json.loads(line)
        if row["id"].startswith("V-"):
            arm = row["arm"]
            if arm.startswith("forced-"):
                forced.setdefault(row["id"], []).append(row["success"])
            else:
                views[arm].append({key: value for key, value in row.items()
                                   if key not in ("audit", "score", "media")})
        else:
            actions.append({key: value for key, value in row.items() if key not in (
                "features", "group_key", "outcome", "native_before", "native_after")})
    view_ids = [spec.episode_id for spec in specs["V"]]
    assert all([row["id"] for row in rows] == view_ids for rows in views.values())
    assert [row["id"] for row in actions] == [spec.episode_id for spec in specs["A"]]
    for i, view_id in enumerate(view_ids):
        rows = [arm[i] for arm in views.values()]
        any_success = any(row["success"] for row in rows)
        if not any_success:
            assert len(forced[view_id]) == 16
        for row in rows:
            row["solvable"] = any_success or any(forced[view_id])
    return views, actions


def evaluate(specs, control, diagnostic, renderer, scorer, out, frozen, *, completed_main=None):
    model = frozen.session()
    zero = frozen.session(view="zero")
    shuffle = frozen.session(view="shuffle", action="shuffle")
    views = {arm: [] for arm in ("F", "R", "L", "zero", "shuffle")}
    actions, controls, diagnostics = [], [], []
    negatives = {"V": _visual_negatives(renderer, scorer, out / "visual-negatives")}
    with evidence(out) as (media, raw):
        media.writestr("ao-schema.json", _json(public_schema()))
        if completed_main is not None:
            views, actions = completed_main
        else:
            for spec in specs["V"]:
                with materialize(build_fixture(spec)) as native, native.context():
                    episode = ViewAuditEpisode(ViewEpisode(native), renderer)
                    for arm, active in (("F", None), ("R", model), ("L", model), ("zero", zero), ("shuffle", shuffle)):
                        row, _, _ = episode.arm(
                            arm if arm in ("F", "R") else "L", active, scorer, media, raw, display=arm)
                        views[arm].append(row)
                    solvable = any(rows[-1]["success"] for rows in views.values())
                    if not solvable:
                        forced = [episode.forced(j, scorer, media, raw) for j in range(16)]
                        solvable = any(item["success"] for item in forced)
                    for rows in views.values():
                        rows[-1]["solvable"] = solvable
            for i, spec in enumerate(specs["A"]):
                row, _ = _action_data(spec, renderer, media, raw, model=model, constant=frozen.reference,
                                      shuffle=shuffle, negatives=(i == 0))
                actions.append(row)
        negatives["A"] = actions[0]["negative_controls"]
        controls.extend(_control_view(spec, renderer, scorer, media, raw) for spec in control["V"])
        for spec in control["A"]:
            row, _ = _action_data(spec, renderer, media, raw, constant=frozen.reference)
            controls.append(row)
        paired = {}
        for spec in diagnostic["A"]:
            row, _ = _action_data(spec, renderer, media, raw, model=model, constant=frozen.reference)
            diagnostics.append(row)
            paired.setdefault(spec.group_id, []).append(row)
        for pair in paired.values():
            if len(pair) == 2:
                assert pair[0]["distance_before_m"] == pair[1]["distance_before_m"]
                assert pair[0]["control_before"] == pair[1]["control_before"]
                assert pair[0]["control_after"] != pair[1]["control_after"]
    assert model.views.writes == model.actions.writes == 240
    prequential_dir = out / "prequential"
    prequential_dir.mkdir()
    prequential = _prequential(specs["V"], specs["A"], renderer, scorer, prequential_dir, frozen)
    write_json(out / "summary.json", {"views": views, "actions": actions, "controls": controls,
                                     "diagnostic": diagnostics, "prequential": prequential,
                                     "negative_controls": negatives, "environment": _env()})


_ORDERS = (("F", "R", "L"), ("R", "L", "F"), ("L", "F", "R"),
           ("L", "R", "F"), ("F", "L", "R"), ("R", "F", "L"))


def _check_feedback(image, feedback):
    assert _digest(image.png) == feedback["png_sha256"]
    assert image.metadata["frame_id"] == feedback["frame_id"]
    assert image.metadata["target_ids"] == feedback["targets"]
    assert image.metadata["witness"] == feedback["witness"]
    assert image.metadata["mode"] == feedback["mode"]
    assert image.metadata["selection"]["ray_count"] == feedback["rays"]


def performance(specs, renderer, out, frozen, scored, seed):
    initialization = perf_counter_ns()
    model = frozen.session()
    shadow_r, shadow_l = model.clone(), model.clone()
    init_ns = perf_counter_ns() - initialization
    rows = []
    stages = []
    actions = scored["actions"]
    views = scored["views"]
    raw = out / "timing.jsonl"
    for i, (v, a) in enumerate(zip(specs["V"], specs["A"])):
        with materialize(build_fixture(v)) as scene_v, materialize(build_fixture(a)) as scene_a:
            view, action = ViewEpisode(scene_v), ActionEpisode(scene_a)
            episode = {"ordinal": i, "view_id": v.episode_id, "view_family": v.family,
                       "action_id": a.episode_id, "action_family": a.family, "samples": []}
            assert actions[i]["id"] == a.episode_id
            for repeat in range(10):
                order = _ORDERS[(SEEDS.index(seed) + i + repeat) % len(_ORDERS)]
                sample = {"repeat": repeat, "warmup": repeat < 5, "order": order, "arms": {}}
                for arm in order:
                    feedback = views[arm][i]
                    assert feedback["id"] == v.episode_id
                    action.reset()
                    shadow = shadow_r if arm == "R" else shadow_l
                    shadow.views.writes = model.views.writes
                    shadow.actions.writes = model.actions.writes
                    if arm == "L":
                        np.copyto(shadow.view_head.weights, model.view_head.weights)
                        np.copyto(shadow.action_head.weights, model.action_head.weights)

                    start = perf_counter_ns()
                    image, _, features = view.run(renderer, model, arm)
                    if arm != "F":
                        shadow.learn_view(features[0], feedback["candidate"], feedback["safe"],
                                          feedback["selected_rays"], update_model=(arm == "L"))
                    midpoint = perf_counter_ns()
                    outcome = action.run(renderer, "L" if arm == "L" else frozen.reference_arm,
                                         model=model if arm == "L" else None, constant=frozen.reference)
                    if arm == "L":
                        shadow.learn_action(outcome.features, outcome.meters, outcome.outcome.measured_delta_m)
                    end = perf_counter_ns()

                    _check_feedback(image, feedback)
                    assert outcome.outcome.measured_delta_m == actions[i]["measured_delta_m"]
                    sample["arms"][arm] = {"total_ns": end - start, "V_ns": midpoint - start,
                                           "A_ns": end - midpoint}
                episode["samples"].append(sample)
            rows.append(episode)
            with raw.open("a", encoding="utf-8") as stream:
                _record(stream, episode)
        if i % 10 == 9:
            print(f"{seed} timing {i + 1}/{len(specs['V'])}", flush=True)
    # Stage clocks are deliberately collected after the gate intervals.
    with materialize(build_fixture(specs["V"][0])) as scene_v, materialize(build_fixture(specs["A"][0])) as scene_a:
        view, action = ViewEpisode(scene_v), ActionEpisode(scene_a)
        for arm in ("F", "R", "L"):
            action.reset()
            shadow = model.clone()
            timestamps = {"start": perf_counter_ns()}
            image, _, features = view.run(renderer, model, arm, timestamps)
            if arm != "F":
                feedback = views[arm][0]
                shadow.learn_view(features[0], feedback["candidate"], feedback["safe"],
                                  feedback["selected_rays"], update_model=(arm == "L"))
            timestamps["feedback_written"] = perf_counter_ns()
            result = action.run(renderer, "L" if arm == "L" else frozen.reference_arm,
                                model=model if arm == "L" else None, constant=frozen.reference, stages=True)
            if arm == "L":
                shadow.learn_action(result.features, result.meters, result.outcome.measured_delta_m)
            result.stages_ns["feedback_written"] = perf_counter_ns()
            _check_feedback(image, views[arm][0])
            stages.append({"arm": arm, "view_timestamps_ns": timestamps,
                           "action_timestamps_ns": result.stages_ns})
    write_json(out / "timing.json", {"seed": seed, "episodes": rows, "initialization_ns": init_ns,
                                    "environment": _env(), "separate_stage_probe": stages})


def smoke(specs, renderer, scorer, out):
    with evidence(out) as (media, raw):
        for spec in specs["V"][:2]:
            with materialize(build_fixture(spec)) as native, native.context():
                episode = ViewAuditEpisode(ViewEpisode(native), renderer)
                row, _, _ = episode.arm("F", None, scorer, media, raw)
                assert row["success"]
                forced = episode.forced(row["candidate"], scorer, media, raw)
                assert forced["success"]
        _action_data(specs["A"][0], renderer, media, raw, negatives=True)
    negatives = _visual_negatives(renderer, scorer, out / "visual-negatives")
    write_json(out / "summary.json", {"success": True, "environment": _env(),
                                     "visual_negatives": negatives})


def _visual_negatives(renderer, scorer, out):
    """Use the separately frozen VG shell for observable wrong-plane forgeries."""
    from verification.test_raycast_saccade_gpu import _native_meshes
    from verification.vg_fixtures import build_fixture as build_vg_fixture

    shell = build_vg_fixture(20)
    try:
        with bpy.context.temp_override(scene=shell.scene, view_layer=shell.scene.view_layers[0]):
            audit = VisualAudit(_native_meshes(shell), shell.target_ids, shell.frame_id,
                                shell.mode, shell.scale_length, shell.witness)
            prepared = renderer.prepare(shell.meshes)
            image, record = observe(renderer, prepared, audit)
            assert scorer.score(image.png, record)["passed"]
            return negative_controls(renderer, prepared, audit, scorer, image, record, out=out)
    finally:
        shell.close()


def run(args):
    assert bpy.app.background
    inputs = Inputs(args.out)
    specs = inputs.specs(args.manifest, args.seed, args.split)
    if args.stage == "validate":
        model = inputs.candidates(args.model)
    elif args.stage in ("evaluate", "evaluation-completion", "performance"):
        model = inputs.frozen(args.model)
    renderer = VGRenderer()
    start = perf_counter_ns()
    try:
        if args.stage == "performance":
            feedback = json.loads(inputs.track(args.feedback))
            performance(specs, renderer, args.out, model, feedback, args.seed)
        else:
            with PillowWorker(args.python) as scorer:
                if args.stage == "collect":
                    collect(specs, renderer, scorer, args.out)
                elif args.stage == "validate":
                    validate(specs, renderer, scorer, args.out, model)
                elif args.stage in ("evaluate", "evaluation-completion"):
                    control = inputs.specs(args.control, args.seed, "control")
                    diagnostic = inputs.specs(args.diagnostic, args.seed, "diagnostic")
                    completed = None
                    if args.stage == "evaluation-completion":
                        receipt = json.loads(inputs.track(args.original_receipt))
                        recorded = inputs.track(args.original_records)
                        assert receipt["exit_code"] != 0 and receipt["inputs_stable"] and receipt["sources_stable"]
                        assert receipt["outputs"]["records.jsonl.gz"]["sha256"] == _digest(recorded)
                        completed = _completed_main(specs, recorded)
                        write_json(args.out / "continuation.json", {
                            "original_records": str(args.original_records.resolve()),
                            "sha256": _digest(recorded), "replayed_main_episodes": 0,
                            "retained_main": {"V_per_arm": len(completed[0]["F"]), "A": len(completed[1])},
                            "scope": "controls, sealed diagnostics, and separate prequential",
                        })
                    evaluate(specs, control, diagnostic, renderer, scorer, args.out, model,
                             completed_main=completed)
                else:
                    smoke(specs, renderer, scorer, args.out)
    finally:
        renderer.close()
    write_json(args.out / "run-complete.json", {"stage": args.stage, "split": args.split,
                                               "seed": args.seed, "wall_ns": perf_counter_ns() - start,
                                               "environment": _env()})
