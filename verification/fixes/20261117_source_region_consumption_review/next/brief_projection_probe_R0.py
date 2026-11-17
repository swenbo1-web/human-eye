"""Measure a facts-first projection on three frozen public JSON records."""

import copy
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = Path("C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_source_region_consumption_001")


def project(value):
    task = value["task_result"]
    visibility = value["visibility"]
    region = value["region"]
    binding = value["binding"]
    result = {
        "schema": "source-region-brief-v2-probe",
        "status": value["status"],
        "observation_status": value["observation_status"],
        "task_result": {
            "status": task["status"],
            "reference": task["reference"],
            "measurement_scope": task["measurement_scope"],
            "unit": binding["unit"],
            "coordinate_frame": binding["coordinate_frame"],
            "facts": task["facts"],
            "source_mapping": {"nearest_witness": task["source_mapping"]["nearest_witness"]},
        },
        "visibility": {key: item for key, item in visibility.items()
                       if key not in ("visible_source_triangle_indices", "unseen_source_triangle_indices", "image_scope")},
        "region": {key: region[key] for key in (
            "host_id", "instance_id", "object_name", "index_domain", "bbox_min_world_m", "bbox_max_world_m")},
        "images": value["images"],
        "image_scope": binding["image_scope"],
        "binding": {key: binding[key] for key in (
            "document_epoch", "capture_state", "source_binding_sha256", "binding_sha256",
            "ordered_geometry_sha256", "runtime_source_sha256", "source_status", "disk_status")},
        "read_only": value["read_only"],
        "execution_authority": value["execution_authority"],
    }
    result["visibility"].update(
        visible_source_triangle_count=len(visibility["visible_source_triangle_indices"]),
        unseen_source_triangle_count=len(visibility["unseen_source_triangle_indices"]))
    result["region"].update(source_triangle_count=len(region["source_triangle_indices"]),
                            source_vertex_count=len(region["source_vertex_indices"]))
    result["region_ref"] = value["region_ref"]
    return copy.deepcopy(result)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf8")


rows = []
for case in ("S1", "S2", "S3"):
    path = SOURCE / "inputs" / case / "TOOL_RESULT.json"
    original = path.read_bytes()
    content = json.loads(original)["content"]
    text = content[0]["text"]
    value = json.loads(text)
    probe = project(value)
    public = encoded(probe)
    assert probe["task_result"]["facts"] == value["task_result"]["facts"]
    assert probe["task_result"]["source_mapping"]["nearest_witness"] == value["task_result"]["source_mapping"]["nearest_witness"]
    assert probe["region_ref"] == value["region_ref"]
    assert probe["image_scope"] == value["binding"]["image_scope"]
    assert probe["images"] == value["images"]
    assert path.read_bytes() == original
    rows.append({
        "case": case,
        "source_path": str(path),
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "original_text_bytes": len(text.encode("utf8")),
        "probe_text_bytes": len(public),
        "region_ref_bytes": len(encoded(probe["region_ref"])),
        "distance_byte_offset": public.index(b'"distance_m"'),
        "witness_byte_offset": public.index(b'"nearest_witness"'),
        "pixels_byte_offset": public.index(b'"selected_surface_pixels"'),
        "image_ref_byte_offset": public.index(b'"image_ref"'),
        "region_ref_byte_offset": public.index(b'"region_ref"'),
        "all_task_facts_and_witness_unchanged": True,
        "self_contained_v1_ref_and_display_scope_unchanged": True,
    })

result = {"status": "offline_projection_feasible", "cases": rows,
          "product_modified": False, "new_models": 0, "new_images": 0,
          "scope": "one self-contained original region_ref plus compact facts; production implementation and consumer effect unrun"}
(HERE / "BRIEF_PROJECTION_PROBE.json").write_bytes(encoded(result) + b"\n")
print(json.dumps(result, ensure_ascii=False))
