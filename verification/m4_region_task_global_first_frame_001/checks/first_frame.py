"""Independent exact pixel-centre and region-task first-frame controls."""

import argparse
from base64 import b64decode
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from math import ceil, floor
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch


NS = Path(__file__).resolve().parents[1]
BASELINE = "0b6116d70af512f81a6ba053dd02a5e924530593"
KEEP = ("main", "holdout", "transfer")
EXPECTED_OBSERVED = {
    "main": {"Component_582", "Component_736"},
    "holdout": {"N22"},
    "transfer": {"S021", "S055"},
}
MOD = "human_eye_plugin/active_observation_region_task.py"


def digest(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(path):
    return json.loads(Path(path).read_bytes())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load(binding_path, checkout):
    binding = read(binding_path)
    manifest = {row["path"]: row["sha256"] for row in binding["source_manifest"]}
    installed = Path(binding["install_root"]).resolve(strict=True)
    require(len(manifest) == 143, "isolated manifest must bind exactly 143 sources")
    for name in (MOD, "human_eye_plugin/active_observation.py",
                 "human_eye_plugin/active_observation_host.py"):
        require(digest((installed / name).read_bytes())["sha256"] == manifest[name],
                "installed module differs from binding " + name)
    source = checkout or installed
    sys.path[:0] = [str(source), binding["dependency_root"], str(NS / "harness")]
    from human_eye_plugin import active_observation as geometry
    from human_eye_plugin import active_observation_host as host
    from human_eye_plugin import active_observation_region_task as task
    for module in (task, geometry, host):
        require(Path(module.__file__).resolve().is_relative_to(source),
                "a module escaped the selected source root")
    return geometry, host, task, binding, digest(Path(task.__file__).read_bytes())


def exact_project(point, pose):
    """Use the exact rational values represented by the two binary64 matrices."""
    world = tuple(map(Fraction, point)) + (Fraction(1),)
    camera = tuple(sum(value * Fraction(m) for value, m in zip(world, row, strict=True))
                   for row in pose["view_matrix"])
    clip = tuple(sum(value * Fraction(m) for value, m in zip(camera, row, strict=True))
                 for row in pose["projection_matrix"])
    require(clip[3] == 1 and camera[2] < 0 and all(-1 < x < 1 for x in clip[:3]),
            "exact oracle only accepts the strict orthographic frustum")
    return ((clip[0] + 1) * Fraction(511, 2), (1 - clip[1]) * Fraction(511, 2))


def half_integer_range(values):
    values = tuple(values)
    return range(max(0, ceil(min(values) - Fraction(1, 2))),
                 min(511, floor(max(values) - Fraction(1, 2))) + 1)


def cross_at(a, b, point):
    return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])


def exact_pixel_centres(region, objects, pose):
    vertices, faces, _, _ = objects[region.object_index]
    points = {i: exact_project(vertices[i], pose)
              for face in region.triangle_indices for i in faces[face]}
    triangles = [tuple(points[i] for i in faces[face]) for face in region.triangle_indices]
    rows = half_integer_range(x[0] for x in points.values())
    cols = half_integer_range(x[1] for x in points.values())
    centres = 0
    for x in rows:
        for y in cols:
            point = Fraction(2*x+1, 2), Fraction(2*y+1, 2)
            for a, b, c in triangles:
                signs = cross_at(a, b, point), cross_at(b, c, point), cross_at(c, a, point)
                if min(signs) >= 0 or max(signs) <= 0:
                    centres += 1
                    break
    return {"exact_box_centres": len(rows) * len(cols), "exact_triangle_centres": centres}


def assert_bound(task, region, objects, pose, expected=None):
    truth = exact_pixel_centres(region, objects, pose)
    bound = task.pixel_center_upper_bound(region, objects, pose)
    require(bound["status"] == "bounded" and bound["actual_observation"] is False
            and bound["upper_bound"] >= truth["exact_triangle_centres"],
            "unsafe strict-frustum pixel-centre certificate")
    if expected is not None:
        require(bound["upper_bound"] == truth["exact_box_centres"] == expected,
                "strict threshold case failed")
    return {**truth, "bounded": bound["upper_bound"]}


def real_cases(geometry, task, *, candidate):
    from inputs import sealed_inputs
    results = {}
    for label in KEEP:
        fixture = sealed_inputs(label)
        source = {row["object_id"]: row for row in fixture["terminal"]["objects"]}
        path = Path(fixture["original_slot"]) / "product_full/call_001/SERVICE_RESULT.json"
        producer = read(path)
        require(digest(path.read_bytes()) == {key: next(
            row[key] for row in fixture["source_pins"] if Path(row["path"]) == path)
            for key in ("sha256", "bytes")}, "sealed producer pin differs")
        binding = producer["binding"]
        rows = producer["facts"]["region_task"]["rows"]
        require({row["object_name"] for row in rows if row["complete_witness"] is not None}
                == EXPECTED_OBSERVED[label], "historical witnesses changed")
        scenes = []
        for bound in binding["objects"]:
            obj = source[bound["host_id"]]
            require(obj["name"] == bound["object_name"] and obj["instance_id"] == bound["instance_id"],
                    "historical geometry escaped original binding")
            evaluated = obj["evaluated"]
            scenes.append({"name": obj["name"], "vertices": evaluated["vertices_world_m"],
                           "triangles": evaluated["triangles"]})
        objects, triangles, identity = geometry.geometry({"objects": scenes})
        require(identity == binding["geometry_identity"], "historical geometry digest changed")
        cameras = binding["camera_specification"]
        index, _ = geometry.prepare_coverage_index(objects, triangles, identity, cameras,
            prove_frustum_containment=True, bind_blocker_sources=True)
        require(index.candidate_identity == binding["camera_identity"], "historical cameras changed")
        session = geometry.ActiveObservationSession(objects, triangles, cameras, index, geometry.CoverageState(index))
        relevant = {row["roi_id"] for row in rows}
        independently_relevant = {region.roi_id for region in session.regions
                                  if task.region_matches(region, producer["facts"]["region_task"]["conditions"])}
        require(relevant == independently_relevant and len(relevant) == 3,
                "historical task ROI roster changed")
        directions = []
        for pose in cameras["views"]:
            row = {"view": pose["name"], "geometric_status": {}, "proved_complete": {}}
            for region in session.regions:
                if region.roi_id in relevant:
                    classification = index.classifications[pose["name"]][region.roi_id]
                    row["geometric_status"][region.object_name] = classification["status"]
                    if classification["complete"]:
                        row["proved_complete"][region.object_name] = assert_bound(task, region, objects, pose)
            directions.append(row)
        counts = [value["bounded"] for row in directions for value in row["proved_complete"].values()]
        should_skip = bool(counts) and max(counts) < 16
        require(should_skip == (label != "holdout"), "historical qualification changed " + label)
        if label == "main":
            require(max(counts) == 6 and [x["bounded"] for x in directions[0]["proved_complete"].values()] == [3],
                    "main fixed 3/6 bound changed")
        if label == "holdout":
            require(directions[0]["proved_complete"]["N22"]["exact_triangle_centres"] >= 16,
                    "holdout no longer independently defends original SCENE view")
        if candidate:
            work = {"pixel_bound_region_calls": 0}
            checks = []
            receipts = task._global_first_frame_skips(session, relevant, work, checks.append)
            valid_views = [row["view"] for row in directions if row["proved_complete"]]
            require([row["view_name"] for row in receipts] == (valid_views if should_skip else []),
                    "product certificate directions differ from historical oracle " + label)
            require(work["pixel_bound_region_calls"] == len(checks),
                    "historical certificate work not budgeted per candidate")
            require(not session.state.observed_views and not session.state.covered_mask,
                    "pixel prediction mutated observed coverage state")
        else:
            work = receipts = None
        results[label] = {"source_dimensions": fixture["source_dimensions"],
                          "original_slot": str(fixture["original_slot"]),
                          "directions": directions, "should_skip": should_skip,
                          "checked_upper_bounds": work, "actual_candidate_prediction": receipts}
    return results


IDENTITY = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]


def pose(name, *, x_offset=0., projected_scale=1., size=512, direction=(0, 0, 1)):
    view = deepcopy(IDENTITY)
    view[0][3] = x_offset
    view[2][3] = -0.5
    projection = deepcopy(IDENTITY)
    projection[0][0] = projection[1][1] = projected_scale
    return {"name": name, "direction_rational": list(direction), "size_px": [size, size],
            "projection": "orthographic", "view_matrix": view, "projection_matrix": projection}


def rectangle(name, x, y, z=0.):
    def world(u):
        return float((Fraction(u) - Fraction(511, 2)) * Fraction(2, 511))
    points = [[world(i), -world(j), z] for i, j in ((x[0], y[1]), (x[1], y[1]),
        (x[1], y[0]), (x[0], y[0]))]
    return {"name": name, "vertices": points, "triangles": [[0, 1, 2], [0, 2, 3]]}


def threshold_cases(geometry, task, candidate):
    tiny = rectangle("15", (250.25, 254.75), (251.25, 253.75))
    limit = rectangle("16", (251.25, 254.75), (251.25, 254.75))
    prepared = geometry.geometry({"objects": [tiny, limit]})
    objects, triangles, identity = prepared
    default, other = pose("SCENE"), pose("TOP")
    cameras = {"views": [default, other]}
    index, _ = geometry.prepare_coverage_index(objects, triangles, identity, cameras)
    first = next(region for region in index.regions if region.object_name == "15")
    second = next(region for region in index.regions if region.object_name == "16")
    cases = {"fifteen": assert_bound(task, first, objects, default, 15),
             "sixteen": assert_bound(task, second, objects, default, 16)}
    crossing = pose("TOP", x_offset=1.01)
    for label, tested_pose in (("crossing", crossing), ("unsupported", pose("TOP", size=256))):
        result = task.pixel_center_upper_bound(first, objects, tested_pose)
        require(result["status"] == "unknown" and result["upper_bound"] is None,
                label + " must remain unknown")
        cases[label] = result
    if not candidate:
        return cases
    fake_cls = {name: {region.roi_id: {"complete": True, "status": "complete"}
                      for region in index.regions} for name in ("SCENE", "TOP")}
    one, two = first.roi_id, second.roi_id
    blocked = {"complete": False, "status": "positive_area_occlusion"}
    only_one = {name: {**row, two: blocked} for name, row in fake_cls.items()}
    all_blocked = {name: {one: blocked, two: blocked} for name in fake_cls}
    alternate = {**only_one, "TOP": {one: blocked, two: fake_cls["TOP"][two]}}
    missing_first = {**only_one, "SCENE": all_blocked["SCENE"]}
    table = (
        ("empty", [default, other], fake_cls, set(), (), 0),
        ("all_blocked", [default, other], all_blocked, {one, two}, (), 0),
        ("exactly_sixteen", [default, other], fake_cls, {two}, (), 1),
        ("two_smalls", [default, other], only_one, {one, two}, ("SCENE", "TOP"), 2),
        ("alternate_small", [default, other], missing_first, {one, two}, ("TOP",), 1),
        ("alternate_sixteen", [default, other], alternate, {one, two}, (), 2),
        ("mixed_roi_same_direction", [default, other], fake_cls, {one, two}, (), 2),
        ("crossing_late", [default, crossing], only_one, {one, two}, (), 2),
        ("unsupported_late", [default, pose("TOP", size=256)], only_one, {one, two}, (), 2),
    )
    for label, views, classes, relevant, expected_receipts, expected_calls in table:
        budget = []
        work = {"pixel_bound_region_calls": 0}
        session = SimpleNamespace(regions=(first, second), objects=objects, cameras={"views": views},
                                  index=SimpleNamespace(classifications=classes))
        actual = task._global_first_frame_skips(session, relevant, work, budget.append)
        require(tuple(row["view_name"] for row in actual) == expected_receipts
                and work["pixel_bound_region_calls"] == len(budget) == expected_calls,
                "decision or cap changed " + label)
        require(all(row["actual_observation"] is False and all(
                    0 <= proof["upper_bound"] < 16 and proof["actual_observation"] is False
                    for proof in row["regions"]) for row in actual),
                "prediction misreported as actual evidence " + label)
        cases[label] = {"certified_directions": list(expected_receipts), "actual_calls": len(budget)}
    return cases


def delivery_cases(geometry, host, task, directory):
    # Script pixel feedback only in this scheduling test. Real geometry,
    # session transitions, PNG receipt validation and producer delivery run.
    png = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aIr0AAAAASUVORK5CYII=")
    image_path = directory / "scheduled-feedback-fixture.png"
    with image_path.open("xb") as stream:
        stream.write(png)
    mesh = rectangle("target", (250.25, 254.75), (251.25, 253.75))
    capture = {"unit": "m", "coordinate_frame": "world", "source": "blender", "revision": "test-fixed",
        "host_identity": {"schema_version": "1.0", "capture_scope": "complete_scene_meshes",
                          "document_epoch": "f" * 64, "object_instances": {"target": "instance"}},
        "meshes": [{"object_id": "target", "name": "target", "vertices": mesh["vertices"],
                    "faces": mesh["triangles"]}]}
    cameras = {"directions": ["SCENE", "TOP"], "views": [pose("SCENE"), pose("TOP")]}
    local = {"directions": ["SCENE", "TOP"], "views": [pose("SCENE", projected_scale=5.),
                                                       pose("TOP", projected_scale=5.)]}
    conditions = {"area_min_m2": .0001, "area_max_m2": .001, "normal_z_min": 1.}
    outcome = {}
    sha = digest(png)["sha256"]

    for name, answers, include_image, expected_constructed, expected_delivery in (
        ("first_local_insufficient_then_top", {"SCENE": (64, 0), "TOP": (80, 12)}, True,
         ["SCENE", "TOP"], ["TOP"]),
        ("fallback_first_actual_if_no_witness", {"SCENE": (64, 0), "TOP": (80, 3)}, True,
         ["SCENE", "TOP"], ["SCENE"]),
        ("first_local_readable", {"SCENE": (64, 8)}, True, ["SCENE"], ["SCENE"]),
        ("no_image_no_construction", {}, False, [], []),
    ):
        launches, callbacks = [], []

        class ScriptedImages:
            def __init__(self, session, output, **_):
                self.session = session
                session.state.bind_patch_mapping("scripted")
                require(session.cameras == local, "global image constructor called despite proved bound")
                launches.append(output.name)

            def render_view(self, view):
                require(view in answers, "local view order repeated or exceeded scripted observations")
                return {"view_name": view, "frame_identity": "scripted-" + view,
                        "image_path": str(image_path), "image_sha256": sha, "PNG_bytes": len(png),
                        "compressed_array_file_bytes": 0, "array_payload_bytes": 0,
                        "owner_schema": "scripted", "owner_mapping_identity": "scripted",
                        "patch_mapping_identity": "scripted"}

            def observe_frame(self, frame):
                surface, boundary = answers[frame["view_name"]]
                region, = self.session.regions
                readable = surface >= 16 and boundary >= 4
                receipt = {**frame, "scene_identity": self.session.scene_identity,
                    "candidate_identity": self.session.candidate_identity, "actual_image_delivered": True,
                    "pixel_evidence_scope": "actual_common_depth_owner",
                    "readable_roi_ids": [region.roi_id] if readable else [],
                    "pixel_rows": [{"roi_id": region.roi_id, "object_index": region.object_index,
                        "front_facing": True, "readable": readable, "visible_surface_pixels": surface,
                        "contrasting_boundary_pixels": boundary}]}
                update = self.session.observe(receipt)
                return {"stages": {}, "update": update, "summary": self.session.summary()}

        with patch.object(task, "ActiveObservationImages", ScriptedImages), \
             patch.object(host, "freeze_cameras", return_value=cameras), \
             patch.object(task, "_observation_target_cameras", return_value=local):
            result = task.observe_region_task(capture, directory, conditions, include_image=include_image,
                                              construction_callback=callbacks.append)
        global_ = result["scopes"][0]
        rows = result["facts"]["region_task"]["rows"]
        require(len(rows) == 1 and (not global_["frame_refs"] and not global_["steps"]
                                  and not global_["facts"]["observations"]),
                "empty global scope fabricated a frame " + name)
        constructed = result["constructed_frames"]
        selected = result["frames"]
        require([frame["view_name"] for frame in constructed] == callbacks == expected_constructed
                and [frame["view_name"] for frame in selected] == expected_delivery
                and result["work"]["raster_attempts"] == len(expected_constructed)
                and len(launches) == int(include_image)
                and len(global_["skipped_views"]) == 2 * int(include_image),
                "first local or delivery priority changed " + name)
        witness = rows[0]["complete_witness"]
        expected_witness = name in {"first_local_insufficient_then_top", "first_local_readable"}
        require(bool(witness) == expected_witness, "expected witness state changed " + name)
        if witness:
            frame, = selected
            require(all(witness[key] == frame[key] for key in ("scope_id", "frame_identity", "view_name", "image_ref"))
                    and witness["selected_for_delivery"] is True and witness["pixel_row_index"] == 0,
                    "local witness failed to bind delivered ref " + name)
        outcome[name] = {"constructed": callbacks, "selected": expected_delivery, "witness": witness,
                         "image_constructors": len(launches), "predictive_directions": len(global_["skipped_views"])}
    return outcome


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--binding", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--baseline", action="store_true")
    cli.add_argument("--checkout", type=lambda value: Path(value).resolve(strict=True))
    args = cli.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, "run isolated Python with -IB")
    geometry, host, task, bound, source = load(args.binding, args.checkout)
    require(bool(args.checkout) or (bound["preparation_git"] == BASELINE) == args.baseline,
            "incorrect baseline/candidate binding")
    cases = threshold_cases(geometry, task, not args.baseline)
    results = real_cases(geometry, task, candidate=not args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scheduling = {} if args.baseline else delivery_cases(geometry, host, task, args.output.parent)
    report = {"passed": True, "baseline": args.baseline, "installed": args.checkout is None,
              "binding_git": bound["preparation_git"], "source_file": source,
              "threshold_controls": cases, "historical_cases": results, "scripted_delivery": scheduling,
              "new_Blender": 0, "new_models": 0, "real_new_raster": 0}
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n")
    print("first-frame", len(results), len(cases), len(scheduling), digest(args.output.read_bytes()), flush=True)


if __name__ == "__main__":
    main()
