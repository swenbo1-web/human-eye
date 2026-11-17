"""Independently audit frozen JSON and the pinned 0.152.1 presentation budget.

Only the Python standard library is used. The checker reads JSON, UTF-8 text,
the saved upstream source, and existing PNG bytes. It has no product imports.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import time


HERE = Path(__file__).resolve().parent
NAMESPACE = HERE.parent
REPOSITORY = NAMESPACE.parent.parent
ORIGINAL = REPOSITORY / "verification/m4_source_region_consumption_001"
SOURCE_REVIEW = Path("D:/hefe/verification/fixes/20261117_source_region_consumption_review")
PUBLIC_COMMIT = "5adb68a49933ae446bf11935662c83dba55a0804"
MANIFEST_SHA256 = "d39c5dd139538f2d702cb17335ce638802454b0331fe34a0b463b2b4a5ce0546"
ORIGINAL_INPUTS_SHA256 = "785212c11d3dc620e2077235513dbae77434e74b14197ce98e2ae019cb241629"
FIXED_FILES = {
    "PROMPT.txt": "661e950eb1d9b27fab91611a4e764ab76d8c0a0ecbbc54e31be1d5b5cc6c4303",
    "TOOL_SCHEMA.json": "3905a7a110f5541f35ebc148d67efb0bddc834e21ebd162dd7259ec611521fdb",
}
ORIGINAL_RESULTS = {
    "S1": "067b8d41cbeab4c56ac1a9cfa336efec30b22139fd5c3972103eca3482af62c8",
    "S2": "e8d40cc6dadaa623b9363364485610f5c2d737f15f2b93d6f8edc088315f2bee",
    "S3": "e05ea3d1144b840e2ea47d57f332a2d7335fa18035204e419c46afa14569b563",
}
# Each anchor is checked inside its SHA-pinned upstream file.
SOURCE_ANCHORS = {
    "codex-rs/models-manager/src/model_info.rs": [
        "pub fn model_info_from_slug(slug: &str) -> ModelInfo",
        "truncation_policy: TruncationPolicyConfig::bytes(/*limit*/ 10_000)",
    ],
    "codex-rs/codex-mcp/src/binding.rs": [
        "pub fn output_token_limit(&self) -> Option<usize>",
        ".get(self.tool_info.tool.name.as_ref())?",
    ],
    "codex-rs/core/src/tools/handlers/mcp.rs": [
        ".and_then(codex_mcp::PreparedMcpCall::output_token_limit)",
        ".unwrap_or(turn.model_info().truncation_policy.into())",
    ],
    "codex-rs/protocol/src/models.rs": [
        "pub const DEFAULT_IMAGE_DETAIL: ImageDetail = ImageDetail::High",
        "pub fn as_function_call_output_payload(&self) -> FunctionCallOutputPayload",
        "if let Some(structured_content) = &self.structured_content",
        "body: FunctionCallOutputBody::ContentItems(content_items)",
        'format!("data:{mime_type};base64,{data}")',
    ],
    "codex-rs/core/src/tools/context.rs": [
        'let header = format!("Wall time: {wall_time_seconds:.4} seconds\\nOutput:")',
        "Some((self.truncation_policy * 1.2).token_budget())",
        "items.insert(0, FunctionCallOutputContentItem::InputText { text: header })",
        "self.truncation_policy * 1.2,",
    ],
    "codex-rs/core/src/context_manager/history.rs": [
        ".and_then(|metadata| metadata.fallback_token_limit_override)",
        ".map(TruncationPolicy::Tokens)",
        "truncate_function_output_payload(output, policy, estimate_audio_token_count)",
    ],
    "codex-rs/utils/output-truncation/src/lib.rs": [
        "pub fn truncate_function_output_items_with_policy(",
        "TruncationPolicy::Bytes(_) => text.len()",
        "TruncationPolicy::Tokens(_) => approx_token_count(text)",
        "FunctionCallOutputContentItem::InputImage { image_url, detail } => {",
        "image_url: image_url.clone()",
    ],
    "codex-rs/utils/string/src/truncate.rs": [
        "const APPROX_BYTES_PER_TOKEN: usize = 4",
        "fn truncate_with_byte_estimate(s: &str, max_bytes: usize, use_tokens: bool)",
        "if char_end <= beginning_bytes",
        "if idx >= tail_start_target",
        'format!("…{removed_count} tokens truncated…")',
        'format!("…{removed_count} chars truncated…")',
    ],
    "codex-rs/protocol/src/protocol.rs": [
        "impl TruncationPolicy {",
        "TruncationPolicy::Bytes((bytes as f64 * multiplier).ceil() as usize)",
    ],
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key " + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite JSON constant " + value)


def parsed(data):
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)


class Audit:
    def __init__(self):
        self.checks = []
        self.pins = {}

    def require(self, condition, name):
        if not condition:
            raise AssertionError(name)
        self.checks.append(name)

    def raw(self, path, expected=None):
        path = Path(path).resolve()
        data = path.read_bytes()
        sha256 = digest(data)
        self.pins[str(path)] = {"sha256": sha256, "bytes": len(data)}
        if expected is not None:
            self.require(sha256 == expected, "fixed SHA " + str(path))
        return data

    def read(self, path, expected=None):
        return parsed(self.raw(path, expected))


def truncate_middle(text, byte_budget, token_mode=False):
    """Port split_string's complete-codepoint prefix and suffix selection."""
    original = text.encode("utf-8")
    if len(original) <= byte_budget:
        return text
    left_budget = byte_budget // 2
    right_budget = byte_budget - left_budget
    prefix = original[:left_budget].decode("utf-8", errors="ignore")
    suffix = original[len(original) - right_budget:].decode("utf-8", errors="ignore")
    removed = len(text) - len(prefix) - len(suffix)
    unit = "chars"
    if token_mode:
        removed = (len(original) - byte_budget + 3) // 4
        unit = "tokens"
    return prefix + "…" + str(removed) + " " + unit + " truncated…" + suffix


def truncate_items(items, budget, token_mode=False):
    """The audited branch contains input_text and input_image items only."""
    output = []
    remaining = budget
    omitted = 0
    for item in items:
        if item["type"] == "input_image":
            output.append(dict(item))
            continue
        text = item["text"]
        if not text:
            continue
        if remaining == 0:
            omitted += 1
            continue
        size = len(text.encode("utf-8"))
        cost = (size + 3) // 4 if token_mode else size
        if cost <= remaining:
            output.append(dict(item))
            remaining -= cost
            continue
        byte_budget = remaining * 4 if token_mode else remaining
        output.append({"type": "input_text", "text": truncate_middle(text, byte_budget, token_mode)})
        remaining = 0
    if omitted:
        output.append({"type": "input_text", "text": "[omitted " + str(omitted) + " text items ...]"})
    return output


def model_items(result, wall_time_sample):
    """Convert this fixed MCP content branch and prepend the separate header."""
    items = [{"type": "input_text", "text": "Wall time: " + wall_time_sample + " seconds\nOutput:"}]
    for item in result["content"]:
        if item["type"] == "text":
            items.append({"type": "input_text", "text": item["text"]})
        else:
            image_url = "data:" + item["mimeType"] + ";base64," + item["data"]
            items.append({"type": "input_image", "image_url": image_url, "detail": "high"})
    return items


def path_byte_span(text, path):
    """Locate a JSON member and its complete value in the actual UTF-8 text."""
    decoder = json.JSONDecoder()
    start, end = 0, len(text)
    for member in path:
        cursor = start + 1
        while cursor < end:
            while text[cursor].isspace() or text[cursor] == ",":
                cursor += 1
            key_start = cursor
            key, cursor = decoder.raw_decode(text, cursor)
            while text[cursor].isspace() or text[cursor] == ":":
                cursor += 1
            value_start = cursor
            _, value_end = decoder.raw_decode(text, value_start)
            if key == member:
                start, end = value_start, value_end
                break
            cursor = value_end
        else:
            raise KeyError(path)
    return {"start": len(text[:key_start].encode("utf-8")), "end": len(text[:end].encode("utf-8"))}


def audit_sources(audit, root):
    reference = root / "delivery/reference"
    manifest = audit.read(reference / "MANIFEST.json", MANIFEST_SHA256)
    audit.require(len(manifest) == 15, "all 15 saved upstream source and license pins")
    source_text = {}
    for row in manifest:
        audit.require("/" + PUBLIC_COMMIT + "/" in row["url"], "official same-commit URL " + row["path"])
        data = audit.raw(row["file"], row["sha256"])
        audit.require(len(data) == row["bytes"], "official source bytes " + row["path"])
        source_text[row["path"]] = data.decode("utf-8")
    anchors = []
    for source, snippets in SOURCE_ANCHORS.items():
        text = source_text[source]
        for snippet in snippets:
            position = text.find(snippet)
            audit.require(position >= 0, "source anchor " + source + " " + snippet)
            anchors.append({"path": source, "line": text.count("\n", 0, position) + 1, "snippet": snippet})
    audit.raw(root / "delivery/review_consumption.py", "02f4edf6289b6d77a6f3b383b139779d9e5b6137c6db65c757d3c05cb7e38a54")
    audit.raw(root / "next/brief_projection_probe.py", "344642159f226ae16b68d5e09b567858d0c031dc786b2bc770fcdfa59644d320")
    return {"public_tag": "rust-v0.152.1", "public_commit": PUBLIC_COMMIT, "manifest": manifest, "anchors": anchors}


def audit_fixed_inputs(audit, inputs, original):
    original_manifest = audit.read(original / "INPUTS.json", ORIGINAL_INPUTS_SHA256)
    rows = []
    for filename, expected in FIXED_FILES.items():
        old_data = audit.raw(original / "inputs" / filename, expected)
        new_data = audit.raw(inputs / filename, expected)
        audit.require(new_data == old_data, "consumer fixed bytes " + filename)
        rows.append({"file": filename, "bytes": len(new_data), "sha256": expected, "original_bytes_equal": True})
    schema = audit.read(inputs / "TOOL_SCHEMA.json")
    audit.require(schema["name"] == "read_observation", "fixed reader tool name")
    audit.require(schema["inputSchema"] == {"type": "object", "properties": {}, "additionalProperties": False}, "fixed reader empty argument schema")
    formal_schema = inputs / "FORMAL_PRODUCT_SCHEMA.json"
    if formal_schema.exists():
        audit.read(formal_schema)
        rows.append({"file": "FORMAL_PRODUCT_SCHEMA.json", **audit.pins[str(formal_schema.resolve())], "check": "valid duplicate-free finite JSON and recorded identity"})
    return original_manifest, rows


def verify_envelope(audit, result, case):
    audit.require(result.get("isError") is False, case + " successful MCP envelope")
    audit.require(result.get("structuredContent") is None and result.get("structured_content") is None, case + " content-items source branch")
    content = result["content"]
    audit.require([item["type"] for item in content] == ["text", "image"], case + " fixed text and native image ordering")
    audit.require(content[0].get("_meta", {}).get("codex/encryptedContent") is not True, case + " plaintext JSON content branch")
    audit.require(content[1]["mimeType"] == "image/png", case + " native PNG MIME")
    return parsed(content[0]["text"])


def audit_original(audit, original, manifest, source_review, case):
    row = next(row for row in manifest["cases"] if row["case_id"] == case)
    result = audit.read(original / "inputs" / case / "TOOL_RESULT.json", ORIGINAL_RESULTS[case])
    audit.require(row["input_sha256"] == ORIGINAL_RESULTS[case], case + " original manifest input identity")
    response = audit.read(row["source_response"], row["source_response_sha256"])
    audit.require(response["result"] == result, case + " original DISPLAY001 producer result")
    value = verify_envelope(audit, result, case + " original")
    original_text = result["content"][0]["text"]
    audit.require(len(original_text.encode("utf-8")) == row["brief_UTF8_bytes"], case + " original text length")
    audit.require(digest(original_text.encode("utf-8")) == row["original_brief_sha256"], case + " original brief identity")
    if case in ("S2", "S3"):
        for sample in ("0.0000", "10.0000"):
            items = model_items(result, sample)
            first = truncate_items(items, 12000)
            second = truncate_items(first, 3000, token_mode=True)
            header = items[0]["text"]
            reference = source_review / "delivery" / (case + "_SAME_TAG_RECONSTRUCTION_HEADER_" + str(len(header)) + ".txt")
            saved = audit.raw(reference).decode("utf-8").replace("\r\n", "\n")
            audit.require(header + "\n" + second[1]["text"] == saved, case + " source port equals saved reconstruction " + str(len(header)))
    return result, value, row


def critical_spans(audit, text, value, case):
    paths = [
        ("status",),
        ("observation_status",),
        ("task_result", "status"),
        ("task_result", "reference"),
        ("task_result", "measurement_scope"),
        ("task_result", "unit"),
        ("task_result", "coordinate_frame"),
        ("task_result", "facts"),
        ("task_result", "source_mapping", "nearest_witness"),
        ("visibility", "selected_surface_pixels"),
        ("visibility", "visible_pixel_bounds"),
        ("visibility", "selected_object_participates"),
        ("visibility", "unknown"),
        ("visibility", "image_ref"),
        ("visibility", "frame_identity"),
        ("images",),
    ]
    if "reason" in value["visibility"]:
        paths.append(("visibility", "reason"))
    spans = {}
    for path in paths:
        name = ".".join(path)
        span = path_byte_span(text, path)
        audit.require(span["end"] <= 4096, case + " complete critical member within first4096 " + name)
        spans[name] = span
    return spans


def audit_case(audit, inputs, original, manifest, source_review, case):
    old_result, old, original_row = audit_original(audit, original, manifest, source_review, case)
    result = audit.read(inputs / case / "TOOL_RESULT.json")
    value = verify_envelope(audit, result, case)
    text = result["content"][0]["text"]
    text_bytes = text.encode("utf-8")
    task, old_task = value["task_result"], old["task_result"]
    audit.require(value["schema"] == "source-region-brief-v2", case + " explicit v2 projection schema")
    audit.require(len(text_bytes) <= 10000, case + " default JSON at most10000 UTF8 bytes")
    for key in ("status", "observation_status", "region_ref", "images", "read_only", "execution_authority"):
        audit.require(value[key] == old[key], case + " original " + key + " preserved")
    for key in ("status", "reference", "measurement_scope", "facts"):
        audit.require(task[key] == old_task[key], case + " original task " + key + " preserved")
    audit.require(task["source_mapping"]["nearest_witness"] == old_task["source_mapping"]["nearest_witness"], case + " original exact source witness preserved")
    for key in ("unit", "coordinate_frame"):
        audit.require(task[key] == old["binding"][key], case + " original " + key + " preserved")
    for key, expected in old["visibility"].items():
        if key not in ("visible_source_triangle_indices", "unseen_source_triangle_indices", "image_scope"):
            audit.require(value["visibility"][key] == expected, case + " original visibility " + key + " preserved")
    audit.require(value["image_scope"] == old["binding"]["image_scope"], case + " actual original display scope preserved")
    for key in ("source_binding_sha256", "binding_sha256"):
        audit.require(value["binding"][key] == old["binding"][key], case + " original capture binding " + key)
    audit.require(result["content"][1] == old_result["content"][1], case + " exact original PNG content block")
    png = base64.b64decode(result["content"][1]["data"], validate=True)
    audit.require(png.startswith(b"\x89PNG\r\n\x1a\n") and png[12:16] == b"IHDR", case + " original PNG signature and IHDR")
    audit.require(struct.unpack(">II", png[16:24]) == (512, 512), case + " original512pixel image extent")
    audit.require(len(png) == original_row["PNG_bytes"] and digest(png) == original_row["PNG_sha256"], case + " original PNG bytes SHA")
    audit.require(value["images"][0]["image_sha256"] == digest(png), case + " image metadata SHA agrees with original PNG")
    spans = critical_spans(audit, text, value, case)
    stages = []
    # One-, two-, and three-digit wall times cover the fixed 600s lifecycle.
    for sample in ("0.0000", "10.0000", "100.0000"):
        items = model_items(result, sample)
        first = truncate_items(items, 12000)
        second = truncate_items(first, 3000, token_mode=True)
        header_bytes = len(items[0]["text"].encode("utf-8"))
        audit.require(first == items, case + " all text and PNG unchanged after MCP1.2 header" + str(header_bytes))
        audit.require(second == items, case + " all text and PNG unchanged after history header" + str(header_bytes))
        audit.require(second[1]["text"].encode("utf-8") == text_bytes, case + " exact entire JSON survives both stages header" + str(header_bytes))
        stages.append({
            "header_sample": items[0]["text"],
            "header_UTF8_bytes": header_bytes,
            "MCP_text_available_bytes": 12000 - header_bytes,
            "history_text_available_tokens": 3000 - (header_bytes + 3) // 4,
            "history_text_available_bytes": (3000 - (header_bytes + 3) // 4) * 4,
            "MCP_output_items_sha256": digest(encoded(first)),
            "history_output_items_sha256": digest(encoded(second)),
            "MCP_all_content_unchanged": True,
            "history_all_content_unchanged": True,
            "entire_JSON_retained": True,
            "native_PNG_url_and_bytes_retained": True,
        })
    return {
        "case": case,
        "input_path": str((inputs / case / "TOOL_RESULT.json").resolve()),
        "text_UTF8_bytes": len(text_bytes),
        "text_sha256": digest(text_bytes),
        "original_text_UTF8_bytes": original_row["brief_UTF8_bytes"],
        "PNG_bytes": len(png),
        "PNG_sha256": digest(png),
        "critical_member_UTF8_ranges_zero_based_half_open": spans,
        "critical_member_end_max": max(span["end"] for span in spans.values()),
        "original_task_facts_and_exact_source_witness": True,
        "original_measurement_and_display_bindings": True,
        "self_contained_v1_region_ref_equal": True,
        "same_tag_budget_reconstruction": stages,
    }


def audit_publication(audit, inputs, cases):
    namespace = inputs.parent
    manifest = audit.read(namespace / "INPUTS.json")
    baseline = audit.read(namespace / "BASELINE.json")
    audit.require([row["case_id"] for row in manifest["cases"]] == ["S1", "S2", "S3"], "published three fixed ordered cases")
    audit.require(manifest["consumer_group"] == "F", "published fresh consumer group F")
    audit.require(manifest["prompt_sha256"] == FIXED_FILES["PROMPT.txt"], "published prompt SHA")
    audit.require(manifest["tool_schema_sha256"] == FIXED_FILES["TOOL_SCHEMA.json"], "published reader schema SHA")
    publications = []
    for summary, row in zip(cases, manifest["cases"]):
        case = row["case_id"]
        prior = next(record for record in baseline["cases"] if record["case_id"] == case)
        case_root = inputs / case
        tool_path = (case_root / "TOOL_RESULT.json").resolve()
        audit.require(Path(row["input_file"]).resolve() == tool_path, case + " published path names reviewed tool input")
        result = audit.read(tool_path, row["input_sha256"])
        brief = audit.raw(case_root / "ORIGINAL_BRIEF.json")
        audit.require(brief == result["content"][0]["text"].encode("utf-8"), case + " reader brief sidecar exact tool JSON bytes")
        audit.require(row["brief_UTF8_bytes"] == summary["text_UTF8_bytes"], case + " published brief byte count")
        png = audit.raw(case_root / "ORIGINAL_IMAGE.png", summary["PNG_sha256"])
        historical = namespace / "historical" / case
        original_png = audit.raw(historical / "ORIGINAL_IMAGE.png", summary["PNG_sha256"])
        audit.require(png == original_png and len(png) == summary["PNG_bytes"], case + " reader native PNG sidecar equals historical PNG bytes")
        audit.raw(historical / "TOOL_RESULT.json", ORIGINAL_RESULTS[case])
        audit.require(prior["original_input_sha256"] == ORIGINAL_RESULTS[case], case + " original historical input manifest identity")
        audit.require(row["historical_full_sha256"] == prior["full_sha256"], case + " published full source identity equals baseline")
        audit.raw(historical / "SERVICE_RESULT.json", row["historical_full_sha256"])
        binding_path = Path(row["projection_source_binding"])
        expected_binding = namespace / (manifest["selected_candidate"] + "_RUN_BINDING.json")
        audit.require(binding_path.resolve() == expected_binding.resolve(), case + " published selected projection run binding path")
        binding = audit.read(binding_path)
        audit.require(binding["source_sha256"] == row["projection_source_sha256"], case + " published projection source SHA equals run binding")
        audit.require(binding["build_id"] == "sha256:" + row["projection_source_sha256"], case + " projection build identity equals source SHA")
        audit.require(row["consumer_group"] == manifest["consumer_group"], case + " published consumer group consistency")
        audit.require(row["PNG_sha256"] == summary["PNG_sha256"], case + " published original PNG SHA")
        publications.append({
            "case": case,
            "consumer_group": row["consumer_group"],
            "historical_full_sha256": row["historical_full_sha256"],
            "projection_source_sha256": row["projection_source_sha256"],
            "projection_source_binding": str(binding_path.resolve()),
            "reader_sidecars_exact": True,
        })
    return {"selected_candidate": manifest["selected_candidate"], "consumer_group": manifest["consumer_group"], "cases": publications}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs-root", type=Path, default=NAMESPACE / "inputs")
    parser.add_argument("--original-root", type=Path, default=ORIGINAL)
    parser.add_argument("--source-review", type=Path, default=SOURCE_REVIEW)
    parser.add_argument("--output", type=Path, default=HERE / "CLIENT_BUDGET_REVIEW.json")
    args = parser.parse_args()
    audit = Audit()
    started_ns = time.perf_counter_ns()
    audit.raw(__file__)
    source = audit_sources(audit, args.source_review)
    manifest, fixed_files = audit_fixed_inputs(audit, args.inputs_root, args.original_root)
    cases = [audit_case(audit, args.inputs_root, args.original_root, manifest, args.source_review, case) for case in ("S1", "S2", "S3")]
    publication = audit_publication(audit, args.inputs_root, cases)
    audit.require(all(digest(Path(path).read_bytes()) == row["sha256"] for path, row in audit.pins.items()), "all read evidence unchanged at completion")
    report = {
        "status": "passed",
        "scope": "three frozen historical-scene projections and the saved public rust-v0.152.1 fallback content-items branch",
        "source": source,
        "policy": {"fallback_bytes": 10000, "MCP_serialization_multiplier": 1.2, "MCP_bytes": 12000, "history_approximate_tokens": 3000, "approximate_bytes_per_token": 4},
        "fixed_consumer_inputs": fixed_files,
        "published_input_bindings": publication,
        "cases": cases,
        "checks": audit.checks,
        "check_count": len(audit.checks),
        "evidence_pins": audit.pins,
        "clock": "time.perf_counter_ns",
        "started_ns": started_ns,
        "completed_ns": time.perf_counter_ns(),
        "limitations": {"actual_provider_payload_capture": False, "installed_binary_reproducible_build_attestation": False, "model_adoption_measured_by_this_check": False, "formal_product_schema_validation": "JSON syntax and identity only when present", "installed_product_source_qualification": "run-binding JSON identity consistency here; installed bytes covered by separate product qualification", "full_output_and_region_ref_roundtrip": "covered by separate product qualification"},
        "operations": {"product_imports": 0, "model_calls": 0, "Blender_calls": 0, "source_captures": 0, "raster_calls": 0, "PNG_construction": 0, "PNG_encoding": 0, "network_requests": 0, "existing_PNG_base64_decodes": 3, "reconstructed_image_data_URL_string_assemblies": 13, "reconstructed_content_items_JSON_serializations": 18},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8") + b"\n")
    print(json.dumps({"status": report["status"], "checks": len(audit.checks), "text_UTF8_bytes": [case["text_UTF8_bytes"] for case in cases], "report": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
