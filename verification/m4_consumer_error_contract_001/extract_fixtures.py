"""Copy the fifteen original tool exchanges without executing any tool code."""
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "verification/m4_active_coverage_consumption_001/r"
SLOTS = ("N1", "P1", "P2", "N2", "N3", "P3")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def main():
    output = HERE / "fixtures"
    output.mkdir(exist_ok=False)
    sources = {}
    copies = {}

    def snapshot(source, relative):
        raw = source.read_bytes()
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        sources[str(source.resolve())] = digest(raw)
        copies[relative.as_posix()] = digest(raw)
        return raw

    outer_raw = snapshot(SOURCE / "RUN_RESULT.json", Path("RUN_RESULT_ORIGINAL.json"))
    outer = json.loads(outer_raw)
    states = {row["slot"]: row for row in outer["records"]}
    records = []
    slot_records = []
    for slot in SLOTS:
        original = SOURCE / slot
        relative = Path("slots") / slot
        consumer_raw = snapshot(original / "c/CONSUMER.json", relative / "CONSUMER_ORIGINAL.json")
        consumer = json.loads(consumer_raw)
        snapshot(original / "c/PUBLIC_FINAL.txt", relative / "PUBLIC_FINAL.txt")
        snapshot(original / "c/events.jsonl", relative / "PUBLIC_EVENTS_ORIGINAL.jsonl")
        snapshot(original / "o/TOOLS.json", relative / "owner/TOOLS.json")
        snapshot(original / "o/METRICS.json", relative / "owner/METRICS.json")
        stream_path = original / "c/stdout.raw.bin"
        stream = stream_path.read_bytes()
        sources[str(stream_path.resolve())] = digest(stream)
        tool_events = []
        selected_lines = []
        top_errors = []
        offset = 0
        for line_number, line in enumerate(stream.splitlines(keepends=True), 1):
            event = json.loads(line)
            kind = event.get("type")
            if kind in ("thread.started", "turn.started", "turn.completed", "turn.failed", "error"):
                selected_lines.append(line)
            if kind in ("error", "turn.failed"):
                top_errors.append(event)
            item = event.get("item", {})
            if kind == "item.completed" and item.get("type") == "mcp_tool_call":
                tool_events.append((line, event, line_number, offset))
            offset += len(line)
        selected_path = output / relative / "CLI_SLOT_EVENTS.jsonl"
        selected_path.write_bytes(b"".join(selected_lines))
        copies[(relative / "CLI_SLOT_EVENTS.jsonl").as_posix()] = digest(selected_path.read_bytes())
        owner_tools = read(original / "o/TOOLS.json")["tools"]
        if len(owner_tools) != len(tool_events) or len(tool_events) != len(consumer["tool_calls"]):
            raise ValueError("original_tool_count_binding:" + slot)
        for owner_row, raw_event, public in zip(owner_tools, tool_events, consumer["tool_calls"]):
            line, event, line_number, byte_offset = raw_event
            attempt = owner_row["attempt"]
            folder_name = "tool_" + str(attempt).zfill(2)
            tool_relative = relative / "owner" / folder_name
            request_raw = snapshot(original / "o" / folder_name / "REQUEST.json", tool_relative / "REQUEST.json")
            response_raw = snapshot(original / "o" / folder_name / "RESPONSE.json", tool_relative / "RESPONSE.json")
            snapshot(original / "o" / folder_name / "RECEIPT.json", tool_relative / "RECEIPT.json")
            request, response = json.loads(request_raw), json.loads(response_raw)
            item = event["item"]
            if item != public["item"]:
                raise ValueError("raw_CLI_and_consumer_item_binding:" + slot)
            if request["params"]["name"] != item["tool"] or request["params"]["arguments"] != item["arguments"]:
                raise ValueError("original_request_binding:" + slot)
            cli_relative = relative / "CLI" / (folder_name + ".json")
            cli_path = output / cli_relative
            cli_path.parent.mkdir(exist_ok=True)
            cli_path.write_bytes(line)
            copies[cli_relative.as_posix()] = digest(line)
            records.append({
                "fixture_id": slot + "_a" + str(attempt).zfill(2), "slot": slot, "attempt": attempt,
                "tool": item["tool"], "CLI_item_id": item["id"], "CLI_perf_ns": public["perf_ns"],
                "request": (tool_relative / "REQUEST.json").as_posix(),
                "response": (tool_relative / "RESPONSE.json").as_posix(),
                "CLI_completed": cli_relative.as_posix(),
                "request_sha256": digest(request_raw), "response_sha256": digest(response_raw),
                "CLI_raw_line_sha256": digest(line), "CLI_stdout_source": str(stream_path.resolve()),
                "CLI_stdout_sha256": digest(stream), "CLI_raw_line_number": line_number,
                "CLI_raw_byte_offset": byte_offset,
                "arguments": {"source": (tool_relative / "REQUEST.json").as_posix(),
                              "json_pointer": "/params/arguments",
                              "canonical_sha256": digest(json.dumps(item["arguments"], sort_keys=True,
                                  separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8"))},
                "owner_isError": response["result"]["isError"], "CLI_status": item["status"],
                "CLI_error": item["error"],
                "expected_classification": "tool_error" if response["result"]["isError"] else "success",
            })
        state = {"slot": slot, "original_execution_state": states[slot]["execution_state"],
                 "consumer_status": consumer["status"], "raw_usage_events": consumer["raw_usage_events"],
                 "usage": consumer["usage"], "usage_semantics": consumer["usage_semantics"],
                 "interrupted_stream_usage_coverage": consumer["summary"]["interrupted_stream_usage_coverage"],
                 "original_usage_aggregation": consumer["usage_aggregation"],
                 "top_level_errors": top_errors, "consumer_errors": consumer["errors"],
                 "final_sha256": digest((output / relative / "PUBLIC_FINAL.txt").read_bytes()),
                 "scope": "Source values copied without promotion, aggregation or usage inference."}
        state_path = output / relative / "SLOT_STATE.json"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        copies[(relative / "SLOT_STATE.json").as_posix()] = digest(state_path.read_bytes())
        slot_records.append(state)
    classifications = [row["expected_classification"] for row in records]
    if len(records) != 15 or classifications.count("success") != 13 or classifications.count("tool_error") != 2:
        raise ValueError("fifteen_original_classifications")
    manifest = {"schema": "consumer-error-contract-001-original-fixtures-v1", "records": records,
                "slots": slot_records, "original_sources_sha256": sources, "fixture_files_sha256": copies,
                "fixture_count": 15, "success_count": 13, "tool_error_count": 2,
                "tool_code_executed": False, "new_process_model_renderer_calls": 0}
    (HERE / "FIXTURE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fixtures": 15, "success": 13, "tool_error": 2,
                      "original_slots": {row["slot"]: row["original_execution_state"] for row in slot_records},
                      "tool_code_executed": False}))


if __name__ == "__main__":
    main()
