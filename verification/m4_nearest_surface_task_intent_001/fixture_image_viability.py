"""Check fixture PNG and finite source-owner pixels through the fixed installed raster."""

import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(value, indent=2, allow_nan=False)+"\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReplayHost:
    """Supply sealed real evaluated rows under a distinct offline-only identity."""

    def __init__(self, source):
        rows = [{"object_id": f"replay-object-{i}", "name": obj["name"],
                 "vertices": obj["vertices"], "faces": obj["faces"]}
                for i, obj in enumerate(source["objects"])]
        instances = {mesh["object_id"]: str(i+1000) for i, mesh in enumerate(rows)}
        snapshot = {
            "schema": "blender-viewport-display-v1", "scope": "active_view_layer", "status": "captured",
            "view_layer": {"name": source["view_layer"], "instance_id": "1"},
            "objects": [{"host_id": row["object_id"], "instance_id": instances[row["object_id"]],
                         "visible_get": obj["displayed"]}
                        for row, obj in zip(rows, source["objects"], strict=True)],
        }
        source_hash = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                                                 separators=(",", ":")).encode()).hexdigest()
        self.data = {
            "unit": "m", "coordinate_frame": "world", "source": "blender",
            "revision": "task-intent-offline:1", "meshes": rows,
            "host_identity": {"schema_version": "1.0", "document_epoch": source["asset_sha256"],
                              "capture_scope": "complete_scene_meshes", "object_instances": instances},
            "capture_state": {"instance_id": "task-intent-offline", "epoch": 1, "revision": 1,
                              "selection_key": "scene"},
            "display_snapshot": dict(snapshot, sha256=source_hash),
        }

    def capture_scene(self):
        return copy.deepcopy(self.data)


def finite_owner_counts(frame_npz, object_index, face_indices, pixel=None):
    with np.load(frame_npz, allow_pickle=False) as data:
        mask = (data["owners"] == object_index) & np.isfinite(data["depth"])
        local = data["triangle_ids"]-data["face_patch_offsets"][object_index]
        if pixel is not None:
            coordinate = (pixel["row"], pixel["column"])
            assert mask[coordinate] and local[coordinate] == pixel["source_triangle_index"]
        return {row: int((mask & (local == row)).sum()) for row in face_indices}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("installation", type=Path)
    args = parser.parse_args()
    root, install = [path.resolve(strict=True) for path in (args.fixture, args.installation)]
    sys.path.insert(0,str(install))
    from human_eye_plugin.live_service import LiveSpatialService
    from human_eye_plugin.live_spatial_mcp import LiveSpatialMCPServer
    from human_eye_plugin.source_region import _capture_region_frame, _region_image_store, prepare_region

    loaded = Path(sys.modules[LiveSpatialService.__module__].__file__).resolve(strict=True)
    if not loaded.is_relative_to(install):
        raise RuntimeError("wrong installed product")
    source_path = root/"EVALUATED_SOURCE.json"
    source = json.loads(source_path.read_bytes())
    truth = json.loads((root/"TARGET_TRUTH.json").read_bytes())
    assert truth["asset_sha256"] == digest(root/"main.blend") == source["asset_sha256"]
    assert truth["evaluated_source_sha256"] == digest(source_path)
    out = root/"image_viability"
    out.mkdir()
    config = out/"config.json"
    write_json(config, {"schema_version":"1.0", "enabled": True, "project_root": str(out),
                       "state_file":"state.json", "audit_file":"audit.jsonl"})
    host = ReplayHost(source)
    service = LiveSpatialService(config, host)
    server = LiveSpatialMCPServer(service, default_session_id="fixture-image-viability-offline")
    target = truth["target_name"]
    cases = {}
    for seq, (label, case) in enumerate(truth["cases"].items(),1):
        arguments = {
            "query":{"mode":"active_observation","objects":[{"name":target}],
                     "focus":{"task_region":{"reference":{"name":case["reference_name"]},
                                             "relation":"nearest_surface"}}},
            "include_image":True,"response_detail":"brief",
        }
        message = {"jsonrpc":"2.0","id":seq,"method":"tools/call","params":{
            "name":"human_eye_scene_observe","arguments":arguments}}
        reply = server.handle_jsonrpc_message(message)
        write_json(out/f"{label}.MCP_RESULT.json",reply)
        result = reply["result"]
        assert not result["isError"], result
        text, item = result["content"]
        brief = json.loads(text["text"])
        frame, = brief["frames"]
        focus = brief["facts"]["focus"]
        near = focus["nearest_surface"]
        assert near["status"] == "measured" and focus["stop_reason"] == "sample_target_met"
        assert len(focus["views"]) == 1 and frame["view_name"] == "SCENE"
        primary = near["witness"]["a"]["source_triangle_index"]
        assert primary in case["closest_target_source_triangle_indices"]
        assert near["witness"]["b"]["source_triangle_index"] in case["closest_reference_source_triangle_indices"]
        png = Path(frame["image_path"]).resolve(strict=True)
        assert png.is_relative_to(out) and item["mimeType"] == "image/png"
        assert base64.b64decode(item["data"],validate=True) == png.read_bytes()
        assert frame["image_sha256"] == digest(png)
        pixel = focus["sample"]["sampled_pixel"]
        assert pixel["source_triangle_index"] == primary
        indices = case["nearest_source_triangle_indices"]
        counts = finite_owner_counts(png.with_suffix(".npz"),focus["object"]["object_index"],indices,pixel)
        assert counts[primary] == focus["sample"]["selected_surface_pixels"] >= 16
        cases[label] = {"source_triangle_index": primary, "counts": counts, "first_view":"SCENE",
                       "sampled_pixel":pixel, "png_sha256":digest(png), "png":str(png.relative_to(out)),
                       "npz_sha256":digest(png.with_suffix(".npz"))}

    all_rows = sorted(row for group in truth["target_components"] for row in group)
    captured = host.capture_scene()
    displayed_region = prepare_region(captured,{"region":{"object":{"name":target},"source_triangle_indices":all_rows}})
    display = displayed_region.binding["image_scope"]
    displayed_region.images = _region_image_store(displayed_region,out/"top",display)
    work = dict.fromkeys(("raster_attempts","raster_completed","PNG_bytes","NPZ_bytes","array_payload_bytes",
                          "local_verified_images","temporary_encoded_archive_bytes"),0)
    frame,_ = _capture_region_frame(displayed_region,"TOP",None,display,work,{},None,lambda _:None,
                                     sampled_pixel=True)
    assert frame["image_sha256"] == digest(Path(frame["image_path"]))
    counts = finite_owner_counts(frame["arrays_path"],displayed_region.object_index,all_rows)
    assert all(n>=16 for n in counts.values())
    png = Path(frame["image_path"]).resolve(strict=True)
    summary = {
        "schema":"human-eye-nearest-surface-task-intent-fixture-image-viability-v1", "source_sha256":digest(source_path),
        "asset_sha256":source["asset_sha256"], "installed_service":str(loaded),
        "mode":"offline replay of independently reopened evaluated geometry; real original PNG and NPZ",
        "first_fitted":cases, "first_fitted_pngs_distinct":cases["K"]["png_sha256"] != cases["T"]["png_sha256"],
        "whole_target_TOP":{"counts":counts,"png":str(png.relative_to(out)),"png_sha256":digest(png)},
        "offline_software_raster_calls":3, "blender_processes":0, "models":0, "formal_calls":0,
    }
    write_json(out/"IMAGE_VIABILITY.json",summary)
    print(json.dumps(summary,allow_nan=False))


if __name__=="__main__":
    main()

