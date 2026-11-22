"""Measure unchanged installed capture calls and bind them to the actual field wires."""

from contextlib import contextmanager
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import time


HOST_RPC_PREFIX = "HUMAN_EYE_BLENDER_MCP:"


def _clock():
    return time.perf_counter_ns()


def _interval(started, closed):
    return {"started_ns": started, "closed_ns": closed, "elapsed_ns": closed - started}


def _gc_config():
    return {"enabled": gc.isenabled(), "thresholds": list(gc.get_threshold())}


@contextmanager
def observe_installed(evidence_dir, source_sha256):
    """Time original call boundaries. Preserve arguments, outputs and native transport."""
    from human_eye_plugin import blender_mcp_host as connector
    from human_eye_plugin.scene_residency import PROTOCOL as scene_delta_protocol

    host_type = connector.BlenderMCPHost
    decoder_type = connector.SceneDeltaDecoder
    request = host_type._request
    exchange = host_type._exchange
    connect = host_type._connect
    loads = connector._loads
    apply_delta = decoder_type.apply
    config = _gc_config()
    requests, pauses = [], []
    active = None
    pause_start = None
    in_exchange = False

    def collect(phase, info):
        nonlocal pause_start
        if info["generation"] != 2:
            return
        now = _clock()
        if phase == "start":
            pause_start = now
        elif phase == "stop" and pause_start is not None:
            pauses.append({**_interval(pause_start, now), "generation": 2,
                           "collected": info["collected"], "uncollectable": info["uncollectable"]})
            pause_start = None

    def observed_request(host, command, params):
        nonlocal active
        if command != "capture":
            return request(host, command, params)
        if active is not None:
            raise ValueError("unexpected_nested_observed_host_capture")
        row = {"command": command, "stages": {}, "resident_before": host._resident_ready}
        active = row
        started = _clock()
        try:
            result = request(host, command, params)
            row["outcome"] = "success"
            return result
        except BaseException as error:
            row["outcome"] = type(error).__name__
            raise
        finally:
            row["stages"]["host_request"] = _interval(started, _clock())
            row["resident_after"] = host._resident_ready
            requests.append(row)
            active = None

    def observed_exchange(host, payload):
        nonlocal in_exchange
        if active is None:
            return exchange(host, payload)
        active["request_bytes"] = len(payload)
        started = _clock()
        in_exchange = True
        try:
            return exchange(host, payload)
        finally:
            active["stages"]["tcp_exchange_including_outer_json"] = _interval(started, _clock())
            in_exchange = False

    def observed_connect(host, deadline):
        if active is None:
            return connect(host, deadline)
        started = _clock()
        try:
            return connect(host, deadline)
        finally:
            active["stages"]["tcp_connect"] = _interval(started, _clock())

    def observed_loads(data):
        if active is None:
            return loads(data)
        name = "outer_strict_json" if in_exchange else "inner_strict_json"
        started = _clock()
        try:
            value = loads(data)
        finally:
            active["stages"][name] = _interval(started, _clock())
        if name == "inner_strict_json" and isinstance(value, dict):
            active["host_request_id"] = value.get("id")
        return value

    def observed_apply(decoder, packet):
        if active is None:
            return apply_delta(decoder, packet)
        before = decoder.work_totals()
        started = _clock()
        try:
            result = apply_delta(decoder, packet)
        finally:
            active["stages"]["scene_delta_validation_and_materialization"] = _interval(started, _clock())
        after = decoder.work_totals()
        active["decoder"] = {
            "resources_sent": len(packet["resources"]) if packet.get("schema") == scene_delta_protocol else None,
            "capture_state": result.get("capture_state"),
            "coordinate_work": {key: after[key] - before[key] for key in before},
        }
        return result

    scope_started = _clock()
    host_type._request, host_type._exchange, host_type._connect = observed_request, observed_exchange, observed_connect
    connector._loads, decoder_type.apply = observed_loads, observed_apply
    gc.callbacks.append(collect)
    try:
        yield
    finally:
        scope_closed = _clock()
        gc.callbacks.remove(collect)
        host_type._request, host_type._exchange, host_type._connect = request, exchange, connect
        connector._loads, decoder_type.apply = loads, apply_delta
        report = {"pid": os.getpid(), "source_sha256": source_sha256,
                  "timing_scope": _interval(scope_started, scope_closed),
                  "gc_before": config, "gc_after": _gc_config(), "gc_observed_generation": 2,
                  "open_pause": pause_start, "pauses": pauses, "requests": requests}
        path = Path(evidence_dir) / "REAL_HOST_STAGES.json"
        with path.open("x", encoding="utf8") as stream:
            json.dump(report, stream, ensure_ascii=True, indent=2)
            stream.write("\n")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read(path):
    return json.loads(path.read_bytes())


def _rows(path):
    return [json.loads(row) for row in path.read_bytes().splitlines() if row]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _witness(path, raw):
    return {"path": str(path), "sha256": _sha(raw), "bytes": len(raw)}


def _within(inner, outer):
    return outer["started_ns"] <= inner["started_ns"] <= inner["closed_ns"] <= outer["closed_ns"]


def _overlap(first, second):
    return max(0, min(first["closed_ns"], second["closed_ns"]) -
               max(first["started_ns"], second["started_ns"]))


def _raw_stdio(slot, trace):
    directory = slot / "mcp" / ("rpc_" + str(trace["sequence"]).zfill(2))
    tx, rx = directory / "TX.bin", directory / "RX.bin"
    receipt = _read(directory / "RECEIPT.json")
    sent, received = tx.read_bytes(), rx.read_bytes()
    lf = received[:-2] + b"\n" if received.endswith(b"\r\n") else received
    tx_value, rx_value = json.loads(sent), json.loads(received)
    _require(trace["id"] == trace["response_id"] == receipt["id"] == tx_value["id"] == rx_value["id"]
             and trace["method"] == tx_value["method"] == receipt["method"] == "tools/call"
             and trace["TX_bytes"] == receipt["TX_bytes"] == len(sent)
             and trace["TX_sha256"] == _sha(sent)
             and trace["RX_text_UTF8_LF_bytes"] == len(lf) and trace["RX_text_UTF8_LF_sha256"] == _sha(lf)
             and receipt["RX_bytes"] == len(received) and receipt["RX_sha256"] == _sha(received)
             and receipt["error"] is None,
             "actual_production_mcp_wire_binding")
    return {"tx": _witness(tx, sent), "rx": _witness(rx, received),
            "tool": tx_value["params"]["name"], "arguments": tx_value["params"]["arguments"],
            "is_error": rx_value.get("result", {}).get("isError"),
            "worker": _interval(trace["request_received_ns"], trace["reply_completed_ns"]),
            "client": _interval(receipt["started_ns"], receipt["closed_ns"]),
            "client_complete_response_ns": receipt["received_complete_ns"],
            "rasters": trace["raster_actual"]}


def _native_wires(slot):
    wire = slot / "native" / "WIRE"
    events = {r["sequence"]: r for r in _rows(slot / "native" / "WORKER_EVENTS.jsonl") if "m2_work" in r}
    matches = {}
    for row in _read(wire / "INDEX.json"):
        directory = wire / str(row["sequence"]).zfill(3)
        request_path, response_path = directory / "REQUEST.bin", directory / "RESPONSE.bin"
        sent, received = request_path.read_bytes(), response_path.read_bytes()
        request, response = json.loads(sent), json.loads(received)
        if request.get("type") != "execute_code" or response.get("status") != "success":
            continue
        stdout = response.get("result", {}).get("result")
        if not isinstance(stdout, str) or not stdout.startswith(HOST_RPC_PREFIX):
            continue
        outer = json.loads(stdout[len(HOST_RPC_PREFIX):])
        packet = outer.get("result", {})
        if "resources" not in packet or "capture" not in packet:
            continue
        identifier = outer["id"]
        # The production request embeds its JSON as a Python string literal.
        # Bind both command and request ID without evaluating that code.
        script = request["params"]["code"]
        _require(re.fullmatch("[a-f0-9]{32}", identifier) is not None
                 and '"id":"' + identifier + '"' in script and '"command":"capture"' in script
                 and identifier not in matches and row["response_sendall_completed"]
                 and row["request_bytes"] == len(sent) and row["response_attempted_bytes"] == len(received),
                 "actual_native_tcp_capture_wire_binding")
        event = events[row["sequence"]]
        _require(event["status"] == "completed" and event["terminal_geometry_and_file_checks_passed"],
                 "native_capture_did_not_complete")
        matches[identifier] = {"sequence": row["sequence"],
                               "tx": _witness(request_path, sent), "rx": _witness(response_path, received),
                               "owner_execute_and_guards": _interval(event["started_ns"],
                                                                        event["started_ns"] + event["elapsed_ns"]),
                               "m2_work": event["m2_work"], "resources_sent": len(packet["resources"]),
                               "capture_state": packet["capture"]["capture_state"]}
    return matches


def summarize(slot, window=None):
    """Join the four successful live calls after both processes have closed."""
    slot = Path(slot)
    probe_path = slot / "mcp_io" / "REAL_HOST_STAGES.json"
    probe_raw = probe_path.read_bytes()
    probe = json.loads(probe_raw)
    runtime = _read(slot / "mcp_io" / "RUNTIME.json")
    _require(probe["pid"] == runtime["pid"] and probe["source_sha256"] == runtime["source_sha256"]
             and probe["gc_before"] == probe["gc_after"] and probe["gc_before"]["enabled"] is True
             and probe["open_pause"] is None, "actual_production_worker_or_gc_changed")
    worker_rows = {r["id"]: r for r in _rows(slot / "mcp_io" / "MCP_IO.jsonl") if r["method"] == "tools/call"}
    traces = {r["trace"]["trace_id"]: r["trace"] for r in _rows(slot / "product_audit.jsonl")
              if r["event"] == "request_trace"}
    producers = _rows(slot / "product_full" / "INDEX.jsonl")
    captures = probe["requests"]
    native = _native_wires(slot)
    _require(len(producers) == len(captures) == len(native) == 4, "live_capture_or_producer_denominator")
    calls, used = [], set()
    for row, capture in zip(producers, captures, strict=True):
        index = row["index"]
        service_path = slot / "product_full" / f"call_{index:03d}" / "SERVICE_RESULT.json"
        raw = service_path.read_bytes()
        _require(index == len(calls) + 1 and service_path.resolve() == Path(row["path"]).resolve()
                 and _sha(raw) == row["sha256"] and row["new_observations_for_archive"] == 0,
                 "same_producer_record_binding")
        service = json.loads(raw)
        span = service["stages"]
        trace = traces[service["request_trace"]["trace_id"]]
        trace_id = trace["annotations"]["mcp_request_id"]
        wire = _raw_stdio(slot, worker_rows[trace_id])
        _require(trace_id not in used and trace["request_id"] == service["request_trace"]["request_id"]
                 and trace["pid"] == probe["pid"] and trace["outcome"] == "complete"
                 and wire["tool"] == "human_eye_scene_observe"
                 and wire["arguments"]["include_image"] is (index > 2) and wire["is_error"] is False,
                 "actual_service_trace_and_response_binding")
        used.add(trace_id)
        host = capture["stages"]
        decoded = capture["decoder"]
        native_call = native.pop(capture["host_request_id"])
        _require(capture["outcome"] == "success" and capture["request_bytes"] == native_call["tx"]["bytes"]
                 and decoded["capture_state"] == native_call["capture_state"] == service["binding"]["capture_state"]
                 and decoded["resources_sent"] == native_call["resources_sent"]
                 and _within(host["host_request"], span["host_capture"])
                 and _within(span["host_capture"], span["service_total"])
                 and _within(span["service_total"], wire["worker"])
                 and wire["client"]["started_ns"] <= wire["worker"]["started_ns"]
                 and span["service_total"]["closed_ns"] <= wire["client_complete_response_ns"]
                 and _within(native_call["owner_execute_and_guards"], host["tcp_exchange_including_outer_json"]),
                 "timing_native_capture_service_intersection_or_capture_binding")

        transfer = _interval(host["tcp_connect"]["closed_ns"], host["outer_strict_json"]["started_ns"])
        _require(_within(native_call["owner_execute_and_guards"], transfer)
                 and _within(host["inner_strict_json"], host["host_request"])
                 and _within(host["scene_delta_validation_and_materialization"], host["host_request"]),
                 "transport_and_decoder_boundaries_out_of_order")
        host["tcp_send_wait_receive_until_outer_json"] = transfer
        host["tcp_excluding_owner_window_ns"] = transfer["elapsed_ns"] - native_call["owner_execute_and_guards"]["elapsed_ns"]
        # Existing native work counters delimit actual resource creation/array work.
        before = native_call["m2_work"]["before"]
        after = native_call["m2_work"]["after"]
        generation = decoded["capture_state"]
        current = [item for item in after if item["generation"] is not None
                   and all(item["generation"][key] == generation[key] for key in ("instance_id", "epoch", "revision"))]
        _require(len(current) == 1, "missing_native_residency_for_current_capture")
        current = current[0]
        prior = [item for item in before if item["module"] == current["module"]]
        _require(len(prior) <= 1, "duplicate_native_residency_module")
        native_call["residency_work_delta"] = {
            key: current["work"][key] - (prior[0]["work"][key] if prior else 0)
            for key in ("display_read_ns", "resource_builds", "resource_faces_read",
                        "resource_vertices_read", "capture_cache_hits", "to_mesh", "triangulations")
        }

        timing = {s["name"]: s["duration_ns"] for s in trace["spans"]
                  if s["name"] in ("mcp.content_encode", "mcp.wire_encode", "mcp.stdio_write")}
        _require(len(timing) == 3, "production_encoding_trace_missing")
        pauses = [{**event, "in_service_ns": _overlap(event, span["service_total"]),
                   "in_delta_decode_ns": _overlap(event, host["scene_delta_validation_and_materialization"])}
                  for event in probe["pauses"] if _overlap(event, wire["worker"])]
        calls.append({"index": index, "mcp_request_id": trace_id, "mcp": wire, "native": native_call,
                      "host": host, "resources_sent": decoded["resources_sent"],
                      "capture_state": decoded["capture_state"], "coordinate_work": decoded["coordinate_work"],
                      "service_stages": span, "generation_stages": service["generation_stages"],
                      "work": service["work"], "production_phases_ns": timing, "gc_events": pauses,
                      "same_producer_archive_ns": row["saved_ns"] - row["producer_returned_ns"],
                      "producer": _witness(service_path, raw)})
    extras = [_raw_stdio(slot, r) for identity, r in worker_rows.items() if identity not in used]
    _require(len(extras) <= 1 and all(r["rasters"] == 0 for r in extras), "unexpected_extra_product_dispatch")
    close = _read(slot / "mcp" / "HELD_CLOSE.json")
    started = _read(slot / "mcp" / "START.json")
    _require(close["confirmed"] is True and close["production_eof_and_exit_verified"] is True
             and close["exit_code"] == 0 and close["stdout_eof_seen"] is True,
             "closed_real_stdio_window_required")
    return {"calls": calls, "extra_product_calls": extras,
            "dual_no_image_service_ns": sum(r["service_stages"]["service_total"]["elapsed_ns"] for r in calls[:2]),
            "stdio_window": _interval(started["started_ns"], close["closed_ns"]), "stdio_close": close,
            "whole_slot": None if window is None else _interval(*window),
            "gc_config": probe["gc_before"], "probe": _witness(probe_path, probe_raw),
            "scope": {"native": "actual owner request interval includes capture and original read-only guard work",
                      "decoder": "original delta validation, world transforms and mesh-array materialization",
                      "tcp": "actual inclusive exchange shares native execution time; use nested clocks separately",
                      "gc": "only product worker generation 2, observed with stock runtime settings"}}
