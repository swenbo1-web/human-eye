"""Independently audit the three sealed DISPLAY001 consumer inputs.

Only existing files and Git objects are read. PNG inspection checks the original
base64 bytes, signature, chunks, CRCs and IHDR without decoding image pixels.
The brief composition uses lexical spans of the original text block.
"""

import argparse
import base64
from collections import Counter, defaultdict
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tarfile
import time
import traceback
import zlib


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PRIOR = REPO / "verification/m4_source_region_display_001"
RUNTIME = Path("D:/he_m4_source_region_display_001")
PRODUCT_COMMIT = "29f35a771c1d137455602adf28418f45e2788e6a"
PRODUCT_SOURCE = "af7c2cf6715e11f237e878fd6f66047d632b48e528f6b5abe28f6da66b5e232c"
CASES = (("S1", "main", "initial", 1),
         ("S2", "state", "cube_visible", 2),
         ("S3", "state", "target_hidden", 4))
CATEGORIES = ("source_indices", "coordinates", "bindings", "task_facts", "other")
INDEX_FIELDS = {
    "index_domain", "source_triangle_indices", "source_vertex_indices",
    "submesh_to_source_triangle_indices", "submesh_to_source_vertex_indices",
    "triangles_source_vertices", "triangles_submesh_vertices",
    "visible_source_triangle_indices", "unseen_source_triangle_indices",
}
COORDINATE_FIELDS = {
    "vertices_world_m", "bbox_min_world_m", "bbox_max_world_m",
    "common_center_world_m", "direction_rational",
    "target_to_eye_direction_rational", "target_to_eye_unit", "eye_to_scene_unit",
    "eye", "target", "up_seed", "right_unit", "up_unit", "target_world_m",
    "camera_eye_world_m", "view_matrix", "projection_matrix",
    "unpadded_projected_bounds_xy_m", "visible_pixel_bounds", "size_px",
}
BINDING_FIELDS = {
    "binding", "region_ref", "reference", "source_mapping", "image_scope",
    "images", "session_id", "host_id", "instance_id", "object_name",
    "frame_identity", "image_ref",
}
FACT_ROOTS = {
    ("task_result", "facts"), ("visibility",), ("unknowns",),
    ("measurement_scope",), ("task_result", "measurement_scope"),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key/" + key)
        result[key] = value
    return result


def loads(raw):
    return json.loads(raw, object_pairs_hook=no_duplicate_keys)


def pointer(path):
    return "/" + "/".join(str(item).replace("~", "~0").replace("/", "~1") for item in path)


def category_for(path, inherited):
    key = path[-1]
    if key in INDEX_FIELDS:
        return "source_indices"
    witness = path[:-1] == ("task_result", "facts", "surface_proximity", "value", "nearest_witness")
    camera_direction = len(path) >= 2 and path[-2] == "directions" and "camera_policy" in path
    if key in COORDINATE_FIELDS or camera_direction or (witness and key in {"a", "b", "direction_a_to_b"}):
        return "coordinates"
    if key in BINDING_FIELDS:
        return "bindings"
    if path in FACT_ROOTS:
        return "task_facts"
    return inherited


class OriginalTextPartition:
    """Assign every character span once, then count its original UTF-8 bytes."""

    def __init__(self, text):
        self.text = text
        self.decoder = json.JSONDecoder(object_pairs_hook=no_duplicate_keys)
        self.segments = []

    def add(self, start, end, category, path):
        if end > start:
            self.segments.append((start, end, category, pointer(path)))

    def whitespace(self, start):
        end = start
        while end < len(self.text) and self.text[end] in " \r\n\t":
            end += 1
        return end

    def value(self, start, category, path):
        token = self.text[start]
        if token == "{":
            return self.object(start, category, path)
        if token == "[" and category not in {"source_indices", "coordinates"}:
            return self.array(start, category, path)
        _, end = self.decoder.raw_decode(self.text, start)
        self.add(start, end, category, path)
        return end

    def object(self, start, category, path):
        cursor = start + 1
        self.add(start, cursor, category, path)
        while True:
            end = self.whitespace(cursor)
            self.add(cursor, end, category, path)
            cursor = end
            if self.text[cursor] == "}":
                self.add(cursor, cursor + 1, category, path)
                return cursor + 1
            key, key_end = self.decoder.raw_decode(self.text, cursor)
            require(isinstance(key, str), "object_key_string")
            colon = self.whitespace(key_end)
            require(self.text[colon] == ":", "object_field_colon")
            value_start = self.whitespace(colon + 1)
            field_path = path + (key,)
            field_category = category_for(field_path, category)
            self.add(cursor, value_start, field_category, field_path)
            cursor = self.value(value_start, field_category, field_path)
            end = self.whitespace(cursor)
            self.add(cursor, end, category, path)
            cursor = end
            if self.text[cursor] == ",":
                self.add(cursor, cursor + 1, category, path)
                cursor += 1
            else:
                require(self.text[cursor] == "}", "object_closing_delimiter")

    def array(self, start, category, path):
        cursor = start + 1
        self.add(start, cursor, category, path)
        index = 0
        while True:
            end = self.whitespace(cursor)
            self.add(cursor, end, category, path)
            cursor = end
            if self.text[cursor] == "]":
                self.add(cursor, cursor + 1, category, path)
                return cursor + 1
            cursor = self.value(cursor, category, path + (index,))
            index += 1
            end = self.whitespace(cursor)
            self.add(cursor, end, category, path)
            cursor = end
            if self.text[cursor] == ",":
                self.add(cursor, cursor + 1, category, path)
                cursor += 1
            else:
                require(self.text[cursor] == "]", "array_closing_delimiter")

    def review(self):
        loads(self.text)
        start = self.whitespace(0)
        self.add(0, start, "other", ())
        end = self.value(start, "other", ())
        tail = self.whitespace(end)
        self.add(end, tail, "other", ())
        require(tail == len(self.text), "json_partition_trailing_content")
        totals = Counter({category: 0 for category in CATEGORIES})
        contributions = defaultdict(Counter)
        category_hashes = {category: hashlib.sha256() for category in CATEGORIES}
        cursor = 0
        for start, end, category, path in self.segments:
            require(start == cursor, "json_partition_overlap_or_gap")
            raw = self.text[start:end].encode("utf-8")
            totals[category] += len(raw)
            contributions[path][category] += len(raw)
            category_hashes[category].update(raw)
            cursor = end
        total = len(self.text.encode("utf-8"))
        require(cursor == len(self.text) and sum(totals.values()) == total, "json_partition_total")
        return {
            "basis": "original_text_block_utf8_lexical_spans",
            "canonical_reserialization_used": False,
            "total_bytes": total,
            "category_bytes": dict(totals),
            "category_concatenated_span_sha256": {key: value.hexdigest() for key, value in category_hashes.items()},
            "covered_without_overlap_or_gap": True,
            "field_contributions": [
                {"json_pointer": path, "category_bytes": dict(counts)}
                for path, counts in sorted(contributions.items())
            ],
        }


class Audit:
    def __init__(self):
        self.pins = {}
        archive_path = PRIOR / "RUNTIME_ARCHIVE.json"
        manifest = loads(self.read(archive_path, check_archive=False))
        require(manifest["byte_exact"] is True, "original_archive_byte_exact_claim")
        self.archive = {row["relative"]: row for row in manifest["files"]}

    def read(self, path, expected=None, check_archive=True):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = sha(raw)
        require(expected is None or digest == expected, "file_sha256/" + str(path))
        pin = {"path": str(path), "bytes": len(raw), "sha256": digest}
        if check_archive and path.is_relative_to(RUNTIME):
            relative = path.relative_to(RUNTIME).as_posix()
            archived = self.archive[relative]
            require(len(raw) == archived["bytes"] and digest == archived["sha256"], "original_archive_pin/" + relative)
            copy = PRIOR / archived["copy"]
            require(copy.read_bytes() == raw, "original_archive_copy/" + relative)
            pin["sealed_archive_copy"] = str(copy)
        self.pins[str(path)] = pin
        return raw

    def json(self, path, expected=None):
        return loads(self.read(path, expected))

    def jsonl(self, path):
        return [loads(line) for line in self.read(path).splitlines() if line.strip()]


def inspect_png(raw):
    require(raw[:8] == b"\x89PNG\r\n\x1a\n", "png_signature")
    cursor = 8
    chunks = []
    dimensions = None
    while cursor < len(raw):
        length = struct.unpack_from(">I", raw, cursor)[0]
        kind = raw[cursor + 4:cursor + 8]
        end = cursor + 12 + length
        require(end <= len(raw), "png_chunk_bounds")
        data = raw[cursor + 8:cursor + 8 + length]
        crc = struct.unpack_from(">I", raw, cursor + 8 + length)[0]
        require(zlib.crc32(kind + data) & 0xffffffff == crc, "png_chunk_crc")
        if not chunks:
            require(kind == b"IHDR" and length == 13, "png_ihdr_first")
            dimensions = list(struct.unpack_from(">II", data))
        chunks.append(kind.decode("ascii"))
        cursor = end
    require(cursor == len(raw) and chunks[-1] == "IEND" and "IDAT" in chunks, "png_complete_chunks")
    require(dimensions == [512, 512], "png_original_512_square")
    return {"bytes": len(raw), "sha256": sha(raw), "dimensions": dimensions,
            "chunks": chunks, "all_chunk_crcs_valid": True,
            "pixel_decode_count": 0, "image_encode_count": 0}


def review_product(audit):
    binding = audit.json(PRIOR / "R0_RUN_BINDING.json")
    manifest = binding["source_manifest"]
    require(len(manifest) == len({row["path"] for row in manifest}) == 143, "143_unique_product_sources")
    require(binding["preparation_git"] == PRODUCT_COMMIT and binding["source_sha256"] == PRODUCT_SOURCE,
            "fixed_candidate_identity")
    identity = {key: binding[key] for key in ("base_version", "implementation_revision")}
    identity["files"] = manifest
    raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    require(sha(raw) == PRODUCT_SOURCE and binding["build_id"] == "sha256:" + PRODUCT_SOURCE,
            "source_manifest_aggregate_identity")
    names = [row["path"] for row in manifest]
    git = subprocess.run(["git", "archive", "--format=tar", PRODUCT_COMMIT, "--", *names],
                         cwd=REPO, capture_output=True, check=True)
    rows = []
    with tarfile.open(fileobj=io.BytesIO(git.stdout), mode="r:") as archive:
        for row in manifest:
            relative = row["path"]
            committed = archive.extractfile(relative).read()
            require(sha(committed) == row["sha256"], "committed_product_source/" + relative)
            current = audit.read(REPO / relative, row["sha256"])
            installed = audit.read(Path(binding["install_root"]) / relative, row["sha256"])
            require(current == installed == committed, "candidate_source_byte_equality/" + relative)
            rows.append({"path": relative, "bytes": len(committed), "sha256": row["sha256"]})
    schema = audit.json(PRIOR / "public_schema/R0_scene_observe.json")
    return binding, schema, {"product_commit": PRODUCT_COMMIT, "source_sha256": PRODUCT_SOURCE,
        "source_count": 143, "git_working_tree_install_and_prior_archive_equal": True,
        "sources": rows, "original_schema_sha256": sha((PRIOR / "public_schema/R0_scene_observe.json").read_bytes()),
        "original_schema_name": schema["name"],
        "response_detail_schema": schema["inputSchema"]["properties"]["response_detail"]}


def review_case(audit, schema, case):
    case_id, session_name, label, index = case
    session = RUNTIME / "sessions" / session_name
    call = session / "product_calls" / f"call_{index:03d}"
    log = audit.jsonl(session / "PUBLIC_REQUESTS.jsonl")[index - 1]
    require(log["internal_public_call_index"] == index, "public_call_index/" + case_id)
    request_raw = audit.read(call / "REQUEST.json", log["request_sha256"])
    response_raw = audit.read(call / "RESPONSE.json", log["response_sha256"])
    request, response = loads(request_raw), loads(response_raw)
    tx = audit.read(log["actual_TX_path"], log["actual_TX_sha256"])
    rx = audit.read(log["actual_RX_path"], log["actual_RX_sha256"])
    receipt = audit.json(call / "RECEIPT.json")
    require(request == loads(tx) == log["request"], "tx_original_request/" + case_id)
    require(response == loads(rx) == log["response"], "rx_original_response/" + case_id)
    require(receipt == log["receipt"] and receipt["error"] is None, "original_receipt/" + case_id)
    require(receipt["RX_bytes"] == len(rx) and receipt["TX_bytes"] == len(tx)
            and receipt["RX_sha256"] == sha(rx), "original_receipt_bytes/" + case_id)
    require(response["id"] == request["id"] == f"observe-{index}", "original_rpc_ids/" + case_id)
    require(response["result"]["isError"] is False, "original_public_success/" + case_id)
    arguments = request["params"]["arguments"]
    require(request["params"]["name"] == schema["name"]
            and arguments["query"]["mode"] == "source_region"
            and arguments["include_image"] is True
            and "response_detail" not in arguments, "actual_default_brief_request/" + case_id)
    tools = audit.json(session / "MCP_TOOLS.json")["result"]["tools"]
    require(next(item for item in tools if item["name"] == schema["name"]) == schema,
            "original_public_tool_schema/" + case_id)
    content = response["result"]["content"]
    require(len(content) == 2 and content[0]["type"] == "text"
            and content[1]["type"] == "image" and content[1]["mimeType"] == "image/png",
            "one_original_json_and_native_png/" + case_id)
    text = content[0]["text"]
    brief = loads(text)
    require(brief["schema"] == "source-region-brief-v1", "original_brief_schema/" + case_id)
    delivery = audit.json(call / "DELIVERY.json")
    require(delivery["label"] == label and delivery["public_index"] == index
            and delivery["is_error"] is False and delivery["public_result"] == brief,
            "original_delivery_and_brief/" + case_id)
    archive_record = log["producer_archive"]
    producer_raw = audit.read(archive_record["path"], archive_record["sha256"])
    producer = loads(producer_raw)
    before = audit.read(call / "ARCHIVE_BEFORE.bin", log["archive_before_sha256"])
    after = audit.read(call / "ARCHIVE_AFTER.bin", log["archive_after_sha256"])
    require(after.startswith(before), "producer_archive_append/" + case_id)
    require(loads(after[len(before):]) == archive_record, "same_producer_archive_delta/" + case_id)
    require(audit.jsonl(session / "product_full/INDEX.jsonl")[index - 1] == archive_record
            and archive_record["new_observations_for_archive"] == 0,
            "same_producer_index/" + case_id)
    audit.read(archive_record["read_context"])
    require(delivery["started_ns"] <= archive_record["started_ns"]
            <= archive_record["producer_returned_ns"] <= archive_record["saved_ns"]
            <= delivery["returned_ns"], "producer_original_call_window/" + case_id)
    for key in ("task_result", "region_ref", "status", "observation_status"):
        require(brief[key] == producer[key], "producer_public_fact_equality/" + case_id + "/" + key)
    require(brief["measurement_scope"] == producer["task_result"]["measurement_scope"],
            "producer_public_measurement_scope/" + case_id)
    require(brief["region"] == producer["facts"]["region"]
            and brief["visibility"] == producer["facts"]["visibility"], "producer_public_region_visibility/" + case_id)
    for key, value in brief["binding"].items():
        require(value == producer["binding"][key], "producer_public_binding/" + case_id + "/" + key)
    require(brief["binding"]["runtime_source_sha256"] == PRODUCT_SOURCE
            and brief["task_result"]["binding"]["runtime_source_sha256"] == PRODUCT_SOURCE,
            "original_candidate_binding/" + case_id)
    require(len(brief["images"]) == len(delivery["images"]) == len(producer["frames"]) == 1,
            "one_original_frame/" + case_id)
    png = base64.b64decode(content[1]["data"], validate=True)
    image = inspect_png(png)
    saved = delivery["images"][0]
    frame = producer["frames"][0]
    image_ref = brief["images"][0]
    require(png == audit.read(saved["path"], saved["sha256"])
            == audit.read(frame["image_path"], frame["image_sha256"]), "png_original_producer_delivery_equality/" + case_id)
    require(len(png) == saved["bytes"] == frame["PNG_bytes"]
            and image["sha256"] == image_ref["image_sha256"]
            and image_ref["image_block_index"] == 1, "png_original_brief_block_binding/" + case_id)
    for key in ("image_ref", "frame_identity", "host_binding_sha256", "display_identity", "image_scope_identity"):
        require(image_ref[key] == frame[key], "frame_producer_image_binding/" + case_id + "/" + key)
    visibility = brief["visibility"]
    require(visibility["image_ref"] == image_ref["image_ref"]
            and visibility["frame_identity"] == image_ref["frame_identity"]
            and brief["region_ref"] == brief["task_result"]["region_ref"], "brief_internal_source_binding/" + case_id)
    require(brief["region"]["source_triangle_indices"] == arguments["query"]["region"]["source_triangle_indices"]
            == brief["region_ref"]["source_triangle_indices"], "exact_requested_region/" + case_id)
    surface = brief["task_result"]["facts"]["surface_proximity"]
    require(surface["status"] == "measured" and surface["value"]["distance_m"] == 0.37011719389236364,
            "sealed_measurement/" + case_id)
    expected_pixels = 35452 if case_id == "S1" else 0
    expected_reason = {"S1": None, "S2": "selected_region_displayed_without_pixels",
                       "S3": "selected_region_not_displayed"}[case_id]
    require(visibility["selected_surface_pixels"] == expected_pixels
            and visibility.get("reason") == expected_reason, "sealed_case_state/" + case_id)
    require(visibility["selected_object_participates"] is (case_id != "S3"), "sealed_target_display/" + case_id)
    cube = next(item for item in visibility["image_scope"]["objects"] if item["object_name"] == "Cube")
    require(cube["participates"] is (case_id == "S2"), "sealed_cube_display/" + case_id)
    partition = OriginalTextPartition(text).review()
    return {
        "case": case_id, "session": session_name, "state": label, "public_call_index": index,
        "original_request_path": str(call / "REQUEST.json"), "original_response_path": str(call / "RESPONSE.json"),
        "response_file_bytes": len(response_raw), "response_file_sha256": sha(response_raw),
        "original_tx": {"path": log["actual_TX_path"], "bytes": len(tx), "sha256": sha(tx)},
        "original_rx": {"path": log["actual_RX_path"], "bytes": len(rx), "sha256": sha(rx)},
        "producer_archive": archive_record, "producer_archive_bytes": len(producer_raw),
        "text_block_utf8_bytes": len(text.encode("utf-8")), "text_block_utf8_sha256": sha(text.encode("utf-8")),
        "native_content_types": [item["type"] for item in content],
        "original_image_base64_ascii_bytes": len(content[1]["data"].encode("ascii")),
        "original_image_base64_ascii_sha256": sha(content[1]["data"].encode("ascii")),
        "image": image, "original_image_references": brief["images"],
        "region_id": brief["region_ref"]["region_id"],
        "document_epoch": brief["region_ref"]["document_epoch"],
        "capture_generation": brief["region_ref"]["capture_generation"],
        "host_binding_sha256": brief["binding"]["binding_sha256"],
        "display_identity": brief["binding"]["display_identity"],
        "selected_surface_pixels": expected_pixels, "image_reason": expected_reason,
        "byte_composition": partition,
        "original_content_retention": "Root preparation preserves the complete original content. This audit reads and hashes its original text and base64 blocks.",
        "all_input_checks_passed": True,
    }


def review():
    started = time.perf_counter_ns()
    audit = Audit()
    audit.read(__file__)
    _, schema, product = review_product(audit)
    cases = [review_case(audit, schema, case) for case in CASES]
    aggregate = {category: sum(case["byte_composition"]["category_bytes"][category] for case in cases)
                 for category in CATEGORIES}
    return {
        "schema": "m4-source-region-consumption-independent-input-review-v1",
        "task": "M4-SOURCE-REGION-CONSUMPTION-001", "passed_checked_scope": True,
        "started_perf_counter_ns": started, "closed_perf_counter_ns": time.perf_counter_ns(),
        "scope": "Original sealed public default briefs and PNG blocks, original stdio, same producer archives, fixed product sources and original schema.",
        "partition_method": {
            "basis": "Original unmodified text-block JSON string encoded as UTF-8. Outer RESPONSE.json escaping and image base64 are counted separately.",
            "canonical_reserialization_used": False,
            "ownership": "Each field owns its quoted key, colon and following whitespace, its scalar/atomic-array value, and its container delimiters/whitespace. Descendant fields take their own bytes. Commas belong to the containing object/array. Root syntax belongs to other. Empty arrays retain their owning field category.",
            "priority": "An explicit source-index or coordinate field overrides its inherited category. Binding fields then override inherited task facts. Explicit fact roots then set task_facts. All remaining fields inherit their parent category, starting at other.",
            "source_index_field_names": sorted(INDEX_FIELDS),
            "coordinate_field_names": sorted(COORDINATE_FIELDS),
            "additional_coordinate_paths": ["/task_result/facts/surface_proximity/value/nearest_witness/{a,b,direction_a_to_b}", "*/camera_policy/directions/*"],
            "binding_field_names": sorted(BINDING_FIELDS),
            "fact_roots": sorted(pointer(path) for path in FACT_ROOTS),
            "repeated_information": "Each original occurrence contributes once at its actual serialized location. Repeated values across fields remain part of the delivered byte cost.",
            "field_contributions": "JSON Pointer rows report exclusive directly owned bytes. Parent rows exclude all descendant-owned bytes.",
            "category_span_hashes": "SHA-256 of the category's original UTF-8 spans concatenated in original text order.",
        },
        "product": product, "cases": cases,
        "aggregate_text_block_utf8_bytes": sum(case["text_block_utf8_bytes"] for case in cases),
        "aggregate_byte_composition": aggregate,
        "input_pins": sorted(audit.pins.values(), key=lambda item: item["path"]),
        "new_operations": {"model": 0, "CLI_model": 0, "Blender": 0, "product_public_requests": 0,
                           "raster": 0, "PNG_encodes": 0, "NPZ_encodes": 0, "paid_API": 0},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "INPUT_REVIEW.json")
    args = parser.parse_args()
    require(not args.output.exists(), "audit_output_already_exists/" + str(args.output))
    try:
        result = review()
    except Exception as error:
        result = {"schema": "m4-source-region-consumption-independent-input-review-v1",
                  "passed_checked_scope": False, "error_type": type(error).__name__,
                  "error": str(error), "traceback": traceback.format_exc()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed_checked_scope": result["passed_checked_scope"], "output": str(args.output),
                      "error": result.get("error"), "aggregate_bytes": result.get("aggregate_text_block_utf8_bytes")}))
    raise SystemExit(0 if result["passed_checked_scope"] else 1)


if __name__ == "__main__":
    main()
