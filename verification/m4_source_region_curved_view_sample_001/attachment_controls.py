"""Same-frame attachment proof against the isolated product and sealed bilateral captures."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import sys
from types import MethodType, SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

here = Path(__file__).resolve().parent
project = here.parents[1]
arguments = argparse.ArgumentParser()
arguments.add_argument("--binding", type=Path, default=here / "install/PRODUCT_RUN_BINDING.json")
arguments.add_argument("--output", type=Path, required=True)
args = arguments.parse_args()
root = args.output.resolve()
fixture_path = project / "verification/m1_source_region_world_box_001"
fixture = runpy.run_path(str(fixture_path / "inputs.py"))["load_bilateral"]()
binding_bytes = args.binding.read_bytes()
install = json.loads(binding_bytes)
installed = Path(install["install_root"]).resolve(strict=True)
sys.path[:0] = [str(installed), install["dependency_root"]]
from human_eye_plugin import attention_raster, live_service, live_spatial_mcp, source_region
from human_eye_plugin.read_context import ReadContext
from human_eye_plugin.scene_residency import SceneDeltaDecoder
import numpy as np

source_manifest = {entry["path"]: entry["sha256"] for entry in install["source_manifest"]}
verified_sources = {}
for module in (attention_raster, live_service, live_spatial_mcp, source_region):
    path = Path(module.__file__).resolve(strict=True)
    relative_path = path.relative_to(installed).as_posix()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == source_manifest[relative_path], relative_path
    verified_sources[relative_path] = digest
root.mkdir(exist_ok=False)

decoder = SceneDeltaDecoder()
results = []
for index, slot in enumerate(("left", "right")):
    scene = decoder.apply(fixture["deltas"][index])
    query = fixture["calls"][index]["params"]["arguments"]["query"]
    context = ReadContext()
    context.activate(scene, "source_region")
    producer = SimpleNamespace(_read_context=context)
    for name in ("_matching_source_region_producer", "_source_region_sample_path"):
        setattr(producer, name, MethodType(getattr(live_service.LiveSpatialService, name), producer))
    prepared = source_region.prepare_region(scene, query)
    context.prepared("source_regions", lambda: {"regions": {prepared.region_ref["region_id"]: prepared}})
    image_root = root / slot / "state.json.source_region"
    directory = image_root / uuid4().hex
    measured = source_region.measure_region(prepared, query["reference"], context.scene_cache)
    cold = source_region.observe_region(prepared, directory, include_image=True)
    warm = source_region.observe_region(prepared, directory, include_image=True)
    for result in (cold, warm):
        result.update(session_id="attachment-test-" + slot, task_result=measured)
    frame = cold["frames"][0]
    pixel = cold["facts"]["visibility"]["sampled_pixel"]
    png = Path(frame["image_path"]).read_bytes()
    with np.load(frame["arrays_path"]) as from_disk:
        owners = from_disk["owners"]
        ids = from_disk["triangle_ids"]
        offset = from_disk["face_patch_offsets"][prepared.object_index]
        assert owners[pixel["row"], pixel["column"]] == prepared.object_index
        assert ids[pixel["row"], pixel["column"]] - offset == pixel["source_triangle_index"]
        nonselected = np.argwhere(owners != prepared.object_index)[0]
    no_reads = []
    original_read = Path.read_bytes

    def read_png_only(path):
        assert path.suffix.lower() != ".npz", path
        no_reads.append(str(path))
        return original_read(path)

    def project(value, detail=None):
        with patch.object(Path, "read_bytes", read_png_only):
            result = live_spatial_mcp._active_observation_content(value, is_error=False,
                audit={}, response_detail=detail, source_region_image_root=image_root,
                source_region_sample_path=producer._source_region_sample_path)
        text, image = result["content"]
        assert image["type"] == "image" and base64.b64decode(image["data"]) == png
        return json.loads(text["text"]), len(text["text"].encode("utf-8"))

    tests = {}
    for label, value in (("cold", cold), ("warm", warm)):
        projection, size = project(value)
        row = projection["images"][0]
        assert row["sampled_pixel"] == pixel, (slot, label, projection)
        assert row["local_image_path"] == Path(frame["image_path"]).resolve(strict=True).as_posix()
        assert row["image_block_index"] == 1
        assert "sampled_pixel" not in projection["visibility"] and projection["visibility"]["complete_witness"] is None
        tests[label] = {"sampled_pixel": row["sampled_pixel"], "png_sha256": frame["image_sha256"], "body_bytes": size}
    assert warm["work"]["raster_attempts"] == 0
    full, size = project(cold, "full")
    assert "sampled_pixel" not in full["facts"]["visibility"]
    tests["full_unchanged_shape"] = {"body_bytes": size}
    original = prepared.observation

    def tamper(name, operation, joint=False):
        output = copy.deepcopy(cold)
        backing = copy.deepcopy(original) if joint else None
        operation(output)
        if backing is not None:
            operation(backing)
            prepared.observation = backing
        try:
            text, size = project(output)
            assert not {"sampled_pixel", "local_image_path"} & text["images"][0].keys(), (slot, name, text["images"])
            tests[name] = {"omitted": True, "body_bytes": size}
        finally:
            prepared.observation = original

    def move_cell(value):
        value["facts"]["visibility"]["sampled_pixel"].update(row=int(nonselected[0]), column=int(nonselected[1]))

    def wrong_type(value):
        value["facts"]["visibility"]["sampled_pixel"]["row"] = True

    def wrong_face(value):
        value["facts"]["visibility"]["sampled_pixel"]["source_triangle_index"] = len(prepared.meshes[prepared.object_index].faces)

    def wrong_registered_view(value):
        if index == 0:
            other = "SCENE"
        else:
            other = "LEFT"
        value["facts"]["visibility"]["view_name"] = other
        value["frames"][0]["view_name"] = other

    def wrong_roi(value):
        value["facts"]["visibility"]["image_scope"]["schema"] = "unbound-control"
        value["frames"][0]["image_scope"]["schema"] = "unbound-control"

    another_generation = image_root / uuid4().hex / Path(frame["image_path"]).name
    another_generation.parent.mkdir()
    shutil.copyfile(frame["image_path"], another_generation)

    def alternate_png(value):
        value["frames"][0]["image_path"] = str(another_generation)

    def wrong_task_binding(value):
        value["task_result"]["binding"]["scene_revision"] = -999

    tamper("response_only_wrong_cell", move_cell)
    tamper("response_and_prepared_wrong_cell", move_cell, joint=True)
    tamper("response_and_prepared_boolean_index", wrong_type, joint=True)
    tamper("response_and_prepared_wrong_face", wrong_face, joint=True)
    tamper("response_and_prepared_other_view", wrong_registered_view, joint=True)
    tamper("response_and_prepared_wrong_scope", wrong_roi, joint=True)
    tamper("response_and_prepared_other_generation_same_png", alternate_png, joint=True)
    tamper("response_only_wrong_task_binding", wrong_task_binding)
    scene["capture_state"]["revision"] += 1
    context.activate(scene, "source_region")
    text, size = project(warm)
    assert not {"sampled_pixel", "local_image_path"} & text["images"][0].keys()
    tests["stale_read_generation"] = {"omitted": True, "body_bytes": size}
    results.append({"region": slot, "actual_view": frame["view_name"], "tests": tests,
                    "source_sha256": hashlib.sha256(png).hexdigest(), "png_paths_read": no_reads})
receipt = {"status": "passed", "runtime": "installed_sealed_capture_actual_renderer_and_serializer",
           "product_commit": install["preparation_git"],
           "product_binding_sha256": hashlib.sha256(binding_bytes).hexdigest(),
           "verified_sources": verified_sources,
           "case_count": sum(len(record["tests"]) for record in results),
           "npz_serializer_read_count": 0, "blender_count": 0, "model_count": 0, "results": results}
(root / "RESULT.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: value for key, value in receipt.items() if key != "results"}))



