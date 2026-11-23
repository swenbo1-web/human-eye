"""Adversarial controls for the offline visual-scope proof on installed ba79."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
OUT = Path("D:/he_m4_source_region_visual_scope_proof_001/CONTROLS.json")
INSTALL_BINDING = (
    HERE.parent / "m1_m2_source_region_scoped_measurement_001"
    / "install" / "PRODUCT_RUN_BINDING.json"
)
COMMIT = "ba79e2f1ca79f4651a3acaef90988fef9a1a9fc6"
VIEWS = ("SCENE", "TOP", "LEFT", "RIGHT", "FRONT", "BACK")
TRIANGLE = ((-.75, -.75, 0.), (.75, -.75, 0.), (0., .75, 0.))
IDENTITY = [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]


def need(value, message):
    if not value:
        raise AssertionError(message)


def must_reject(operation, message=None):
    try:
        operation()
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        need(message is None or message in str(exc), f"unexpected rejection: {exc}")
        return f"{type(exc).__name__}: {exc}"
    raise AssertionError("invalid control was accepted")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime():
    binding = json.loads(INSTALL_BINDING.read_text(encoding="utf-8"))
    need(binding["preparation_git"] == COMMIT, "wrong installed commit")
    installed = Path(binding["install_root"]).resolve(strict=True)
    deps = Path(binding["dependency_root"]).resolve(strict=True)
    for root in (str(deps), str(installed)):
        if root in sys.path:
            sys.path.remove(root)
        sys.path.insert(0, root)
    import numpy as np
    from human_eye_plugin import active_observation_host, active_observation_images
    from human_eye_plugin import attention_raster, blender_host, source_region

    relevant = {}
    source_hashes = {row["path"]: row["sha256"] for row in binding["source_manifest"]}
    for module in (active_observation_host, active_observation_images,
                   attention_raster, blender_host, source_region):
        location = Path(module.__file__).resolve()
        need(location.is_relative_to(installed), f"non-installed module {location}")
        rel = location.relative_to(installed).as_posix()
        measured = sha(location)
        need(measured == source_hashes[rel], f"installed byte mismatch {rel}")
        relevant[rel] = measured
    return np, active_observation_host, active_observation_images, attention_raster, blender_host, source_region, relevant


def cameras(*, y_scale=1.):
    view = deepcopy(IDENTITY)
    view[2][3] = -3.
    projection = deepcopy(IDENTITY)
    projection[1][1] = y_scale
    projection[2][2] = .25
    return {"views": [
        {"name": name, "projection": "orthographic", "size_px": [128, 128],
         "view_matrix": deepcopy(view), "projection_matrix": deepcopy(projection)}
        for name in VIEWS
    ]}


def raster(np, installed_raster, meshes, pose):
    offsets = [0, *np.cumsum([len(mesh.faces) for mesh in meshes])]
    face_ids = tuple(np.arange(start, end, dtype=np.int32)
                     for start, end in zip(offsets[:-1], offsets[1:], strict=True))
    return installed_raster.rasterize_attention(
        meshes, pose["view_matrix"], pose["projection_matrix"], pose["size_px"][0],
        return_owner=True, return_patch_owner=True, face_patch_ids=face_ids,
        object_mask=(True,) * len(meshes),
    )


def mesh(name, key, vertices=TRIANGLE, faces=((0, 1, 2),)):
    return tuple(vertices), tuple(faces), key, name


def moved(vertices, *, dx=0., dz=0.):
    return tuple((x + dx, y, z + dz) for x, y, z in vertices)


def complete_capture(rows):
    meshes = [{"object_id": host_id, "name": obj[3],
               "vertices": [list(v) for v in obj[0]], "faces": [list(face) for face in obj[1]]}
              for host_id, _, obj in rows]
    return {
        "unit": "m", "coordinate_frame": "world", "source": "blender",
        "revision": "synthetic-original", "meshes": meshes,
        "host_identity": {"schema_version": "1.0", "capture_scope": "complete_scene_meshes",
                          "document_epoch": "a" * 64,
                          "object_instances": {host_id: instance for host_id, instance, _ in rows}},
        "capture_state": {"instance_id": "synthetic-host", "epoch": 1,
                          "revision": 2, "selection_key": "complete"},
    }


def bounds_controls(host, proof):
    typical = cameras()
    original = typical["views"][0]
    clear = [[1.125, -.3, 0.], [1.3, .3, 0.]]
    touching = [[1., -.3, 0.], [1.3, .3, 0.]]
    ulp = [[math.nextafter(1., math.inf), -.3, 0.], [1.3, .3, 0.]]
    on_last = deepcopy(typical)
    on_last["views"][-1]["view_matrix"][0][3] = -1.
    branches = {
        "unknown": (None, typical, (False, 0), "unknown"),
        "touch": (touching, typical, (False, 1), "intersecting_or_touching"),
        "one_ulp_separation": (ulp, typical, (False, 1), "intersecting_or_touching"),
        "strict_exclusion": (clear, typical, (True, 6), "outside"),
        "exclude_five_keep_on_last_view": (clear, on_last, (False, 6), "intersecting_or_touching"),
        "nonfinite": ([[1.125, 0., 0.], [math.inf, .3, 0.]], typical, (False, 1), "unknown"),
    }
    results = {}
    for label, (bounds, plan, expected, expected_last_status) in branches.items():
        product_result = host._observation_outside_xy_viewports(bounds, plan)
        certificates = [proof.viewport_certificate(bounds, view) for view in plan["views"]]
        statuses = [item["status"] for item in certificates]
        need(product_result == expected, f"{label}: installed six-view proof differs")
        need(statuses[-1] == expected_last_status, f"{label}: receipt status differs: {statuses}")
        results[label] = {"installed_all_six": list(product_result), "per_view": certificates}

    acquisition_input = list(product((-.15, .15), (-.3, .3), (-.1, .1)))
    old_matrix, new_matrix = deepcopy(IDENTITY), deepcopy(IDENTITY)
    old_matrix[0][3] = 2.
    old_box = host._acquisition_bounds(acquisition_input, old_matrix, 1.)
    new_box = host._acquisition_bounds(acquisition_input, new_matrix, 1.)
    need(host._observation_outside_xy_viewports(old_box, typical) == (True, 6), "old matrix outside")
    need(host._observation_outside_xy_viewports(new_box, typical) == (False, 1), "moved object visible")
    need(host._acquisition_bounds([(-1., -1., -1.)] * 8, IDENTITY, 1.) is None,
         "unknown evaluated bounds sentinel must stay unknown")
    need(host._acquisition_bounds(acquisition_input[:-1], IDENTITY, 1.) is None,
         "missing evaluated corner must stay unknown")
    results["changed_world_matrix"] = {
        "old_bounds": old_box, "new_bounds": new_box,
        "old_status": proof.viewport_certificate(old_box, original)["status"],
        "new_status": proof.viewport_certificate(new_box, original)["status"],
        "unknown_sentinel_and_missing_corner_retained": True,
    }
    need(results["changed_world_matrix"]["old_status"] == "outside"
         and results["changed_world_matrix"]["new_status"] == "intersecting_or_touching",
         "changed world matrix lacked new viewport receipt")
    return results


def overflow_control(np, host, installed_raster, images, proof):
    # The installed all-six predicate can short-circuit after finite X.
    # Orthographic Y projection can still fail on the full raster.
    plan = cameras(y_scale=4.)
    extreme = ((2., 5e307, 0.), (2.3, 5e307, 0.), (2.1, 5e307, .1))
    bounds = [[2., 5e307, 0.], [2.3, 5e307, .1]]
    product_result = host._observation_outside_xy_viewports(bounds, plan)
    need(product_result == (True, 6), "expected installed X short circuit")
    checks = [proof.viewport_certificate(bounds, view) for view in plan["views"]]
    need(all(item["status"] == "unknown" for item in checks), "an overflowing axis was certified")
    meshes = images._meshes_from_objects((mesh("target", "target"), mesh("extreme", "extreme", extreme)))
    full = must_reject(lambda: raster(np, installed_raster, meshes, plan["views"][0]), "numeric range")
    _, _, owners, _ = raster(np, installed_raster, meshes[:1], plan["views"][0])
    pixels = int(np.count_nonzero(owners == 0))
    need(pixels > 0, "incorrectly pruned counterfeit success must actually render")
    return {"installed_short_circuit": list(product_result), "all_axes_receipts": checks,
            "full_replay_rejection": full, "incorrectly_pruned_render_pixels": pixels,
            "proof_result": "unknown_and_no_qualified_equivalence"}


def identity_controls(np, host_binding, source_region, images, installed_raster, proof):
    plan = cameras()
    pose = plan["views"][0]
    original_rows = [
        ("outside", "outside-i", mesh("outside", "outside", moved(TRIANGLE, dx=5.))),
        ("first", "first-i", mesh("same name", "explicit-1")),
        ("second", "second-i", mesh("same name", "explicit-2")),
    ]
    original = complete_capture(original_rows)
    identities = [(row[0], row[1]) for row in original_rows]
    prepare = source_region.prepare_region
    bind = host_binding.source_binding(original)
    ambiguous = must_reject(lambda: prepare(original,
        {"region": {"object": {"name": "same name"}, "source_triangle_indices": [0]}}),
        "object_name_ambiguous")
    pending = prepare(original, {"region": {"object": {"id": "first"}, "source_triangle_indices": [0]}})
    need(pending.binding["objects"][pending.object_index]["instance_id"] == "first-i", "explicit instance")
    original_ref = pending.region_ref
    source_region.validate_region_ref(original, original_ref)
    generation_update = deepcopy(original)
    generation_update["capture_state"]["revision"] += 1
    stale_epoch = must_reject(lambda: source_region.validate_region_ref(generation_update, original_ref),
                              "capture_generation_changed")
    pose_update = deepcopy(original)
    pose_update["meshes"][1]["vertices"][0][0] += .125
    stale_pose = must_reject(lambda: source_region.validate_region_ref(pose_update, original_ref),
                             "ordered_geometry_changed")

    meshes = images._meshes_from_objects(tuple(obj for _, _, obj in original_rows))
    full = raster(np, installed_raster, meshes, pose)
    kept = raster(np, installed_raster, meshes[1:], pose)
    flipped = raster(np, installed_raster, (meshes[2], meshes[1]), pose)
    domain = proof.owner_domain(identities, [1, 1, 1], [1, 2])
    mapped_owner, mapped_ids = proof.restore_owners(kept[2], kept[3], domain)
    need(np.array_equal(full[0], kept[0]) and np.array_equal(full[1].view(np.uint64), kept[1].view(np.uint64)),
         "safe culling changed same-position raster values")
    need(np.array_equal(full[2], mapped_owner) and np.array_equal(full[3], mapped_ids),
         "safe culling did not restore original ordinals and triangle offsets")
    # A raster of two equal-depth, equal-RGB faces looks identical when reversed.
    # The original owner is different. No visual-only equality is sufficient.
    need(np.array_equal(kept[0], flipped[0])
         and np.array_equal(kept[1].view(np.uint64), flipped[1].view(np.uint64)),
         "synthetic equal-depth tie is not equal")
    foreground = full[2] != -1
    count = int(np.count_nonzero(foreground))
    need(count > 0 and np.all(full[2][foreground] == 1) and np.all(full[3][foreground] == 1),
         "raster did not retain the first original occurrence on a tie")
    flipped_owner = np.where(flipped[2] < 0, -1, np.asarray([2, 1], dtype=np.int32)[np.maximum(0, flipped[2])])
    need(np.count_nonzero(full[2] != flipped_owner) == count, "reversed tie error was not observable")

    owner_rule_rejections = {
        "missing_original_row": must_reject(lambda: proof.owner_domain(identities, [1, 1, 1], [1, 3]),
                                            "derived_domain_must_preserve_original_object_order"),
        "missing_original_face_count": must_reject(lambda: proof.owner_domain(identities, [1, 1], [1, 2]),
                                                   "ambiguous_or_missing_current_source_rows"),
        "ambiguous_identity": must_reject(lambda: proof.owner_domain(
            [identities[0], identities[1], identities[1]], [1, 1, 1], [1, 2]),
                                         "ambiguous_or_missing_current_source_rows"),
        "reordered_original_ordinals": must_reject(lambda: proof.owner_domain(identities, [1, 1, 1], [2, 1]),
                                                      "derived_domain_must_preserve_original_object_order"),
        "owner_triangle_disagreement": must_reject(lambda: proof.restore_owners(
            np.array([[0]], dtype=np.int32), np.array([[1]], dtype=np.int32), domain),
                                                   "local_owner_source_triangle_mismatch"),
        "unmatched_background": must_reject(lambda: proof.restore_owners(
            np.array([[-1]], dtype=np.int32), np.array([[0]], dtype=np.int32), domain),
                                            "invalid_local_owner_buffer"),
    }
    capture2 = host_binding.source_binding(generation_update)
    next_plan = deepcopy(plan)
    next_plan["views"][0]["view_matrix"][0][3] += .25
    original_scope = proof.view_fingerprint(bind, plan, domain)
    changed_generation_scope = proof.view_fingerprint(capture2, plan, domain)
    changed_camera_scope = proof.view_fingerprint(bind, next_plan, domain)
    full_scope = proof.view_fingerprint(bind, plan, proof.owner_domain(identities, [1, 1, 1], [0, 1, 2]))
    need(len({original_scope, changed_generation_scope, changed_camera_scope, full_scope}) == 4,
         "scope aliases complete, filtered, different generation or changed camera")
    return {"same_name_rejection": ambiguous, "explicit_host_and_instance": ["first", "first-i"],
            "stale_capture_generation_rejection": stale_epoch, "stale_geometry_pose_rejection": stale_pose,
            "tied_pixels_and_reversed_owner_count": count, "owner_triangle_offsets_recovered": True,
            "equal_depth_and_rgb_mask_reversal": True, "owner_rule_rejections": owner_rule_rejections,
            "scope_identities": {"subset": original_scope, "changed_generation": changed_generation_scope,
                                 "changed_camera": changed_camera_scope, "full_order": full_scope}}


def self_occluder_control(np, installed_raster, images):
    plan = cameras()
    pose = plan["views"][0]
    target = mesh("target", "whole-target", TRIANGLE + moved(TRIANGLE, dz=.5), ((0, 1, 2), (3, 4, 5)))
    incomplete_target = mesh("target", "selected-only-incorrect", TRIANGLE)
    full_meshes = images._meshes_from_objects((target,))
    wrong_meshes = images._meshes_from_objects((incomplete_target,))
    full = raster(np, installed_raster, full_meshes, pose)
    wrong = raster(np, installed_raster, wrong_meshes, pose)
    full_count = int(np.count_nonzero(full[3] == 0))
    wrong_count = int(np.count_nonzero(wrong[3] == 0))
    full_vote = installed_raster.select_sparse_attention_view(
        full_meshes, plan["views"], object_mask=(True,), object_index=0,
        source_triangle_indices=(0,), check_budget=lambda _: None)
    wrong_vote = installed_raster.select_sparse_attention_view(
        wrong_meshes, plan["views"], object_mask=(True,), object_index=0,
        source_triangle_indices=(0,), check_budget=lambda _: None)
    need(full_count == 0 and wrong_count > 0, "source region must retain whole-target self occlusion")
    need(full_vote == ("SCENE", dict.fromkeys(VIEWS, 0))
         and wrong_vote[0] == "SCENE" and wrong_vote[1]["SCENE"] > 0,
         "self occluder removal should cause false sparse-view visibility")
    return {"selected_pixels_with_whole_target": full_count,
            "selected_pixels_after_incorrect_face_pruning": wrong_count,
            "whole_target_sparse": full_vote, "incorrectly_pruned_sparse": wrong_vote}


def sparse_fallback_control(np, installed_raster, images):
    plan = cameras()
    for pose in plan["views"]:
        if pose["name"] == "LEFT":
            cos, sin = .5, math.sqrt(3.) / 2
            pose["view_matrix"] = [[cos, 0., sin, 0.], [0., 1., 0., 0.],
                                   [-sin, 0., cos, -3.], [0., 0., 0., 1.]]
    inputs = (mesh("target", "target"), mesh("external occluder", "occluder", moved(TRIANGLE, dz=.5)))
    meshes = images._meshes_from_objects(inputs)
    chosen, votes = installed_raster.select_sparse_attention_view(
        meshes, plan["views"], object_mask=(True, True), object_index=0,
        source_triangle_indices=(0,), check_budget=lambda _: None)
    need(list(votes) == list(VIEWS) and chosen == "LEFT" and votes["LEFT"] > 0
         and all(count == 0 for view, count in votes.items() if view != "LEFT"),
         "selected visibility should move to LEFT only after the default is blocked")
    scene, left = [raster(np, installed_raster, meshes, plan["views"][i])[3] for i in (0, 2)]
    selected_pixels = [int(np.count_nonzero(ids == 0)) for ids in (scene, left)]
    need(selected_pixels[0] == 0 and selected_pixels[1] > 0,
         "real selected pixels must independently confirm the fallback")
    return {"default_view": "SCENE", "chosen_view": chosen, "votes_in_visited_order": list(votes.items()),
            "selected_pixels_default_and_fallback": selected_pixels}


def run_controls():
    np, binding, images, raster_module, host, source_region, modules = runtime()
    import proof

    return {
        "schema": "m4-source-region-visual-scope-adversarial-controls-v1",
        "kind": "synthetic_input_actual_installed_product_and_offline_proof_checks",
        "installed_commit": COMMIT, "installation_binding_sha256": sha(INSTALL_BINDING),
        "runtime_modules": modules, "proof_sha256": sha(Path(proof.__file__)),
        "controls": {
            "viewports": bounds_controls(host, proof),
            "supernumeric_other_axis_after_x_exclusion": overflow_control(np, host, raster_module, images, proof),
            "source_identity_and_tied_order": identity_controls(np, binding, source_region, images, raster_module, proof),
            "unselected_target_face_self_occlusion": self_occluder_control(np, raster_module, images),
            "sparse_fallback_after_default_occlusion": sparse_fallback_control(np, raster_module, images),
        },
        "live_blender": 0, "model_consumers": 0, "builds": 0, "passed": True,
    }


if __name__ == "__main__":
    # Isolated mode excludes the evidence script's directory by default.
    sys.path.insert(0, str(HERE))
    result = run_controls()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        handle.write("\n")
    print(f"{OUT} {sha(OUT)}")
