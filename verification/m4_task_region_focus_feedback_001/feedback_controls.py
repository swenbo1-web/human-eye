"""Run synthetic real-raster task-region and isolated feedback threshold controls."""

import argparse
import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

if not __debug__:
    raise RuntimeError("Run without optimization so assertions stay active")

parser = argparse.ArgumentParser()
parser.add_argument("product_path", type=Path)
parser.add_argument("verification_checkout", type=Path)
args = parser.parse_args()
product = args.product_path.resolve(strict=True)
verification = args.verification_checkout.resolve(strict=True)
sys.path[:0] = [str(product), str(verification)]
from verification.test_directed_observation_focus import DirectedFocusTests, set_display
from human_eye_plugin import observation_focus, source_region
from human_eye_plugin import live_spatial_mcp, query_policy

implementations = {}
for module in (observation_focus, source_region, live_spatial_mcp, query_policy):
    implementation = Path(module.__file__).resolve(strict=True)
    if not implementation.is_relative_to(product):
        raise RuntimeError(f"wrong installed implementation: {implementation}")
    implementations[module.__name__] = str(implementation)

results = {}

def setup():
    t = DirectedFocusTests()
    t.setUp()
    ref = copy.deepcopy(t.host.data["meshes"][0])
    ref.update(object_id="reference", name="Reference",
               vertices=(np.array(ref["vertices"]) + [3, 0, 0]).tolist())
    t.host.data["meshes"].append(ref)
    t.host.data["host_identity"]["object_instances"]["reference"] = "102"
    set_display(t.host.data)
    return t


def policy(z):
    return {"task_region": {"reference": {"name": "Reference"},
                            "world_box_m": {"min": [-1, -1, z], "max": [1, 1, z]}}}


def exact_pixels(packet, rows):
    focus = packet["facts"]["focus"]
    sample = focus["sample"]
    pixel = sample["sampled_pixel"]
    with np.load(packet["frames"][0]["arrays_path"], allow_pickle=False) as original:
        owners, triangles, depth = (original[k] for k in ("owners", "triangle_ids", "depth"))
        mask = (owners == 0) & np.isin(triangles, rows) & np.isfinite(depth)
        primary = mask & (triangles == focus["primary_source_triangle_index"])
        assert int(mask.sum()) == sample["selected_surface_pixels"]
        assert int(primary.sum()) == sample["primary_surface_pixels"]
        assert mask[pixel["row"], pixel["column"]]
        assert triangles[pixel["row"], pixel["column"]] == pixel["source_triangle_index"]
    return focus


t = setup()
try:
    bottom = t.result(policy(-1), detail="full")
    focus = exact_pixels(bottom, [0, 1])
    assert focus["task_source_triangle_indices"] == [0, 1]
    assert focus["views"][0]["verified_pixels"] == 0
    assert focus["views"][1]["verified_pixels"] >= 16
    assert t.rasters == ["SCENE", "FOCUS"]
    results["first_view_zero_then_corrective"] = {
        "source_rows": focus["task_source_triangle_indices"],
        "views": focus["views"], "stop_reason": focus["stop_reason"],
        "original_npz_verified": True, "original_png_verified": True,
    }
    assert focus["stop_reason"] == "sample_target_met"
    assert t.result(policy(-1), detail="full")["frames"] == bottom["frames"]
    assert t.rasters == ["SCENE", "FOCUS"]
    top = t.result(policy(1), detail="full")
    focus = exact_pixels(top, [2, 3])
    assert focus["task_source_triangle_indices"] == [2, 3]
    assert t.rasters == ["SCENE", "FOCUS", "SCENE"]
    results["first_view_sufficient"] = {
        "source_rows": focus["task_source_triangle_indices"],
        "views": focus["views"], "stop_reason": focus["stop_reason"],
        "original_npz_verified": True, "original_png_verified": True,
    }
    assert focus["stop_reason"] == "sample_target_met"
    empty = t.result(policy(0), detail="full")
    assert empty["facts"]["focus"]["stop_reason"] == "no_source_triangles_in_task_world_box"
    assert empty["facts"]["focus"]["sample"] is None and not empty["frames"]
    assert len(t.rasters) == 3
    t.host.data["capture_state"]["revision"] += 1
    new = t.service.observe("focus-test", query=dict(t.query, focus=policy(1)))
    assert new["facts"]["focus"]["region_ref"] != top["facts"]["focus"]["region_ref"]
    assert len(t.rasters) == 4
    new["facts"]["focus"]["views"][0]["primary_verified_pixels"] += 1
    try:
        observation_focus.validate_focus_delivery(new, new["frames"])
    except ValueError as exc:
        assert str(exc) == "focus_task_region_pixel_binding_mismatch"
    else:
        raise AssertionError("mismatched pixel count was accepted")
    results.update(empty_no_raster=True, warm_reuse_without_raster=True,
                   changed_generation_builds_and_rebinds=True, corrupt_view_count_rejected=True)
finally:
    t.doCleanups()


# Isolate the threshold using controlled counts after the ordinary raster path.
# These two checks do not assert the injected counts were measured in the image.
original = observation_focus._capture_region_frame
boundary = []
for controlled_count, expected_views in ((15, ["SCENE", "FOCUS"]), (16, ["SCENE"])):
    t = setup()
    try:
        def controlled_frame(*args, **kwargs):
            frame, sample = original(*args, **kwargs)
            if args[1] == "SCENE":
                sample["selected_surface_pixels"] = controlled_count
                sample["primary_surface_pixels"] = 0
            return frame, sample
        with patch.object(observation_focus, "_capture_region_frame", side_effect=controlled_frame):
            packet = t.result(policy(1), detail="full")
        assert [v["view_name"] for v in packet["facts"]["focus"]["views"]] == expected_views
        assert t.rasters == expected_views
        boundary.append({"injected_first_view_count": controlled_count, "constructed_views": t.rasters,
                         "stop_reason": packet["facts"]["focus"]["stop_reason"]})
    finally:
        t.doCleanups()

results["threshold_decision_injection"] = boundary
print(json.dumps({"status": "passed", "installed_modules": implementations,
                  "software_raster_cases": results, "blender_starts": 0, "model_calls": 0},
                 indent=2, allow_nan=False))

