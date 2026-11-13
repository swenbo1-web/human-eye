"""Replay this batch's existing JSON/image/archive evidence without any calls."""
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
READS = {}
CHECKS = []
ANSWER_SHA = {
    "N": "80ac30c930400311f7e40fde63f74fa9cee4a8a121ab1a3e6549633c2744116b",
    "P": "d1e6b9630e7477da4e6af25f630906ac6577fac17a2bbd4661d55cd16c1002c3",
}


def raw(path):
    path = Path(path).resolve()
    value = path.read_bytes()
    READS[str(path)] = hashlib.sha256(value).hexdigest()
    return value


def read(path):
    return json.loads(raw(path).decode("utf-8-sig"))


def need(name, value):
    CHECKS.append({"check": name, "passed": bool(value)})
    if not value:
        raise ValueError(name)


def images(content):
    return [block for block in content if block.get("type") == "image"]


def check_archive(specification, path_key, member_key, label):
    path = Path(specification[path_key])
    need(label + " ZIP SHA", hashlib.sha256(raw(path)).hexdigest() == specification[
        "sha256" if path_key == "path" else "archive_sha256"])
    expected = specification[member_key]
    with zipfile.ZipFile(path) as archive:
        need(label + " exact member set", len(archive.namelist()) == len(expected)
             and set(archive.namelist()) == set(expected))
        need(label + " all member SHA", all(hashlib.sha256(archive.read(name)).hexdigest() == wanted
             for name, wanted in expected.items()))


def main():
    frozen = read(BATCH / "FROZEN.json")
    plan = read(BATCH / "PLAN.json")
    started = read(BATCH / "FORMAL_STARTED.json")
    result = read(BATCH / "r/RUN_RESULT.json")
    manifest = read(BATCH / "inputs/IMAGES.json")["images"]
    prompt = BATCH / "inputs/PROMPT.txt"
    need("24 frozen sources", len(frozen["runtime_sources"]) == 24)
    need("frozen source bytes unchanged", all(hashlib.sha256(raw(path)).hexdigest() == wanted
         for path, wanted in frozen["runtime_sources"].items()))
    need("formal reservation binds freeze", started["source_freeze_sha256"] == READS[str((BATCH / "FROZEN.json").resolve())])
    need("two routes and single turns", result["planned_routes"] == result["planned_user_turns"]
         == result["actual_routes"] == 2 and plan["sequence"] == ["N", "P"])
    expected_hashes = [row["sha256"] for row in manifest]
    need("opaque manifest order", [row["ref"] for row in manifest] == ["view-a", "view-b"])
    route_reviews = []
    route_blocks = []
    for outer in result["records"]:
        group = outer["group"]
        folder = BATCH / "r" / group
        consumer = read(folder / "c/CONSUMER.json")
        events = [json.loads(line)["event"] for line in raw(folder / "c/events.jsonl").splitlines()]
        timing = read(folder / "FINAL_TIMING.json")
        consumer_timing = read(folder / "c/FINAL_TIMING.json")
        metrics = read(folder / "o/METRICS.json")
        event_counts = Counter(event["type"] for event in events)
        tools = [event["item"] for event in events if event["type"] == "item.completed"
                 and event.get("item", {}).get("type") == "mcp_tool_call"]
        need(group + " accepted execution", outer["execution_state"] == "completed"
             and outer["outer_valid_completion"] and consumer["valid_completion"]
             and not outer["errors"] and not consumer["errors"] and not outer["common_image_faults"])
        need(group + " one fresh thread and turn", event_counts["thread.started"] == event_counts["turn.started"]
             == event_counts["turn.completed"] == 1 and consumer["turn_index"] == 1
             and consumer["expected_thread_id"] is None and "resume" not in consumer["argv"])
        need(group + " no top-level failure", not any(event["type"] in ("error", "turn.failed") for event in events))
        expected_tools = ["read_image", "read_image"] if group == "N" else ["human_eye_image_observe"]
        need(group + " image tools only", [item["tool"] for item in tools] == expected_tools
             and len(tools) == outer["actual_tool_calls"] <= 4 and not consumer["unexpected_tool_deviations"])
        expected_arguments = [{"ref": "view-a"}, {"ref": "view-b"}] if group == "N" else [{"refs": ["view-a", "view-b"]}]
        need(group + " requested opaque order", [item["arguments"] for item in tools] == expected_arguments)
        need(group + " common prompt source", outer["input_sources_sha256"][str(prompt.resolve())]
             == frozen["runtime_sources"][str(prompt.resolve())])
        owner_blocks = []
        for number, item in enumerate(tools, 1):
            request = read(folder / "o" / ("tool_" + str(number).zfill(2)) / "REQUEST.json")
            response = read(folder / "o" / ("tool_" + str(number).zfill(2)) / "RESPONSE.json")
            need(group + " original request " + str(number), request["params"]["name"] == item["tool"]
                 and request["params"]["arguments"] == item["arguments"])
            need(group + " original/CLI content " + str(number), response["result"]["isError"] is False
                 and item["status"] == "completed" and item.get("error") is None
                 and response["result"]["content"] == item["result"]["content"])
            owner_blocks.extend(images(response["result"]["content"]))
        wire_blocks = []
        for path in sorted((folder / "c/attachments").glob("bridge_*/[0-9]*/RX.bin")):
            wire_blocks.extend(images(read(path).get("result", {}).get("content", [])))
        cli_blocks = [block for item in tools for block in images(item["result"]["content"])]
        need(group + " actual owner/stdio/CLI image equality", owner_blocks == wire_blocks == cli_blocks and len(cli_blocks) == 2)
        payloads = [base64.b64decode(block["data"], validate=True) for block in cli_blocks]
        need(group + " original image bytes and order", [hashlib.sha256(value).hexdigest() for value in payloads] == expected_hashes
             and all(value == raw(BATCH / "inputs" / spec["file"]) for value, spec in zip(payloads, manifest))
             and all(block["mimeType"] == "image/png" for block in cli_blocks))
        need(group + " construction and delivery counts", metrics["constructed_image_blocks"] == metrics["server_socket_sent_image_blocks"]
             == consumer["public_image_count"] == 2 and metrics["failed_image_constructions"] == 0
             and metrics["constructed_PNG_bytes"] == metrics["server_socket_sent_PNG_bytes"] == consumer["public_image_bytes"] == 6699)
        need(group + " CLI and actor held-handle cleanup", outer["owner_close_confirmed"]
             and outer["owner_process_cleanup"]["confirmed"] and outer["consumer_process_cleanup"]["confirmed"])
        need(group + " original 450s through readback", outer["deadline_ns"] - outer["started_ns"] == 450_000_000_000
             and timing["accepted_success"] and consumer_timing["accepted_success"]
             and timing["result_closed_ns"] < outer["deadline_ns"])
        bridge = consumer["bridge_cleanup"]
        need(group + " thin EOF unknown preserved", bridge["confirmed"] is None and bridge["missing_exit_count"] == 1)
        warnings = [event["item"] for event in events if event.get("item", {}).get("type") == "error"]
        need(group + " two warning items preserved", len(warnings) == 2
             and any("skip_host_skill_discovery" in warning["message"] for warning in warnings)
             and any("fallback metadata" in warning["message"] for warning in warnings))
        answer = consumer["final"].encode("utf-8")
        need(group + " reviewed answer unchanged", hashlib.sha256(answer).hexdigest() == ANSWER_SHA[group]
             and raw(folder / "c/PUBLIC_FINAL.txt") == answer and raw(folder / "c/final.txt") == answer)
        check_archive(outer["originals"], "path", "members_sha256", group + " outer")
        check_archive(consumer["archive"], "archive", "source_files_sha256", group + " consumer")
        route_blocks.append(cli_blocks)
        route_reviews.append({
            "group": group, "thread_id": consumer["thread_id"], "user_turns": 1,
            "tools": expected_tools, "tool_count": len(tools), "image_count": 2, "PNG_bytes": 6699,
            "construction_layer": "passed", "actual_CLI_image_layer": "passed",
            "answer_matches_original_images": True, "model_python_pixel_computation": False,
            "observed_visual_consumption_qualification": "passed",
            "answer": consumer["final"], "answer_sha256": ANSWER_SHA[group],
            "warnings": warnings, "thin_stdio_graceful_EOF": "unknown", "bridge_cleanup": bridge,
            "CLI_actor_handle_cleanup_confirmed": True, "full_route_elapsed_ns": timing["elapsed_ns"],
            "raw_terminal_usage": consumer["raw_usage_events"], "usage_scope": consumer["usage_semantics"],
            "provider_internal_wire": "unobserved", "actual_resolved_model": "unobserved", "image_tokens": None,
        })
    need("distinct fresh threads", len({row["thread_id"] for row in route_reviews}) == 2)
    need("same N/P actual image blocks", route_blocks[0] == route_blocks[1])
    raw(__file__)
    report = {
        "schema": "active-image-consumption-001-final-review-v1", "decision": "observed_image_consumption_qualification_passed",
        "reviewer_role": "Author-side independent evidence review. Administrator final review pending.",
        "checks": CHECKS, "all_checks_passed": all(row["passed"] for row in CHECKS),
        "frozen_source_count": 24, "routes": route_reviews,
        "totals": {"real_fresh_threads": 2, "user_turns": 2, "tool_calls": 3, "image_blocks": 4, "original_PNG_bytes": 13398},
        "manual_image_review": "The reviewer opened both registered original PNGs. view-a has an almost uniform dark background and a tiny central mark. view-b has a broad arrangement of light grey diamond-shaped silhouettes. Both bound final answers match these observations.",
        "limitations": ["Two warning items per real CLI are retained. They are item-level warnings, not top-level turn failures.",
                        "Thin clients lack EXIT receipts. Graceful stdio EOF remains unknown despite confirmed CLI/actor handles.",
                        "Provider-internal requests, actual resolved model and image-token attribution are unobserved.",
                        "This engineering qualification establishes no comparative model-quality or plugin-benefit result."],
        "reviewer_new_model_renderer_API_calls": 0,
        "inputs_sha256": dict(sorted(READS.items())),
    }
    (HERE / "FINAL_REVIEW.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_checks_passed": report["all_checks_passed"], "checks": len(CHECKS),
                      "source_count": 24, "routes": 2, "images": 4, "thin_EOF": "unknown"}))


if __name__ == "__main__":
    main()
