"""043 G60 ordinary-entry helpers; no host starts during import or freeze."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-043-R3-REGION-ATTRIBUTION/live/g60")
ROOT = RAW.parents[1]
OLD = ROOT.parent / "M6-041-KERNEL-HOOK"
VER = HERE.parents[1]
CYCLE = "M6-043-R3-REGION-ATTRIBUTION"
PYTHON = Path("D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe")
CONTRACT = "46ae148425541e11280812b0a85a3de72d8f45b7"
CANDIDATE_SHA = "b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e"
ORDERS = ("ABC", "ACB", "BAC", "BCA", "CAB", "CBA")
STEPS = ("overview", "nearest", "scan")
ASSET_SHA = "9bba515e72bcbd307d3b41b42d426e253d9da56b1723c0da21663b3653bb7cd8"


def need(value, reason):
    if not value:
        raise ValueError("043_g60_" + reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest)


def check(ref):
    need(pin(ref["path"]) == ref, "source_changed:" + ref["path"])
    return Path(ref["path"])


def dump(path, value):
    path = Path(path).resolve()
    need(path.is_relative_to(RAW.resolve()), "output_scope")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return pin(path)


def binary(value):
    if type(value) is float:
        return {"binary64": value.hex()}
    if isinstance(value, list):
        return [binary(x) for x in value]
    if isinstance(value, dict):
        return {k: binary(v) for k, v in value.items()}
    return value


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_API = None


def api():
    global _API
    if _API is None:
        s1 = load("_043_g60_original_s1", OLD / "s1/s1.py")
        gui, service = s1.api()
        gui.PRIVATE, gui.CYCLE = RAW, CYCLE
        gui.ASSET_SHAS = {ASSET_SHA: "G60_D12"}
        service.CYCLE = CYCLE
        _API = s1, gui, service
    return _API


def arms():
    s1, _, _ = api()
    baseline = s1.source_plan()
    candidate_ref = ROOT / "candidate/PINS.json"
    c = read(candidate_ref)
    check(c["binding"])
    binding = read(c["binding"]["path"])
    need(c["source_sha256"] == CANDIDATE_SHA == binding["identity"]["source_sha256"], "fixed_candidate")
    site = Path(c["site"])
    need(len(binding["source_files"]) == 143, "candidate_manifest")
    for row in binding["source_files"]:
        need(pin(site / row["path"])["sha256"] == row["sha256"], "candidate_source")
    check(c["launcher"])
    check(c["admin"])
    candidate = dict(source_sha256=c["source_sha256"], version=c["identity"]["distribution_version"],
                     role="043 installed ordinary stdio, unchanged transport", site_packages=c["site"],
                     command_prefix=[c["dependency_python"], "-I", "-B", c["launcher"]["path"]])
    return {"A": baseline["032"], "B": baseline["r3"], "C": candidate}


def requests():
    return {step: {"name": "human_eye_scene_observe", "arguments": {
        "session_id": "m6-043-g60-ordinary", "include_image": False, "response_detail": "full",
        "query": ({"mode": "overview"} if step == "overview" else
                  {"mode": "surface_nearest", "objects": [{"name": "Target"}]} if step == "nearest" else
                  {"mode": "surface_scan", "threshold_m": .005})}} for step in STEPS}


def geometry(value):
    result = deepcopy(value)
    result.pop("trace_id", None)
    result.pop("binding", None)
    return result


def comparable(value, arm):
    """Keep same-host business fields; normalize only validated runtime/trace identity.

    Host document/revision/instance fields are deliberately retained. Their
    disagreement is a failed comparison, rather than silently deleted data.
    """
    def visit(item, key=None):
        if isinstance(item, dict):
            if key == "request_trace":
                need(isinstance(item.get("request_id"), str) and len(item["request_id"]) == 32,
                     "public_request_trace_id")
                return {k: ("validated_request_id" if k == "request_id" else visit(v, k))
                        for k, v in item.items()}
            return {k: visit(v, k) for k, v in item.items()}
        if isinstance(item, list):
            return [visit(v) for v in item]
        if key == "context_text" and isinstance(item, str):
            return visit(json.loads(item))
        if key in ("source_sha256", "runtime_source_sha256"):
            need(item == arm["source_sha256"], "public_runtime_source")
            return "validated_runtime_source"
        if key == "build_id":
            need(item == "sha256:" + arm["source_sha256"], "public_build")
            return "validated_build"
        if key == "distribution_version":
            need(item == arm["version"], "public_distribution")
            return "validated_distribution"
        if key == "trace_id":
            need(isinstance(item, str) and len(item) == 32, "public_trace")
            return "validated_request_trace"
        return item
    return binary(visit(value))


def body_from_response(wire):
    need("error" not in wire and not wire["result"].get("isError"), "successful_tool_response")
    result = wire["result"]
    blocks = result.get("content", [])
    need(len(blocks) == 1 and blocks[0].get("type") == "text", "one_text_no_image")
    value = result.get("structuredContent")
    return json.loads(blocks[0]["text"]) if value is None else value


def audit_rows(folder, cell, plan, before):
    """Run after EOF: actual audit is complete without polling in the clock."""
    folder = Path(folder)
    startup = read(folder / "client/STARTUP.json")
    configured = read(folder / "client/CONFIG.json")
    launch = read(folder / "client/LAUNCH.json")
    close = read(folder / "client/CLOSE.json")
    arm = plan["arms"][cell["arm"]]
    identity = startup["hello"]["result"]["_meta"]["human_eye"]
    need(identity["source_sha256"] == arm["source_sha256"] and identity["distribution_version"] == arm["version"]
         and identity["source_file_count"] == 143 and identity["production_mode"] is True, "negotiated_identity")
    need(configured["project_root"] == arm["site_packages"] and configured["expected_identity"] == {
        "source_sha256": arm["source_sha256"]}, "config_identity")
    need(configured["blender"]["host"] == cell["host"] and configured["blender"]["port"] == cell["port"]
         and configured["request_budget_s"] == configured["blender"]["timeout_s"] == 30.0, "endpoint_original_budget")
    need(launch["command"] == [*arm["command_prefix"], "serve", "--config", str(folder / "client/CONFIG.json")],
         "unchanged_installed_serve")
    need(close["method"] == "eof" and close["exit_code"] == 0, "normal_eof")
    need(startup["actual_pid"] == cell["product_pid"], "actual_interpreter")
    logs = [json.loads(x) for x in (folder / "client/AUDIT.jsonl").read_bytes().splitlines() if x]
    need([r["step"] for r in cell["rows"]] == list(STEPS), "request_inventory")
    truth = {step: read(check(plan["truth"][step])) for step in ("nearest", "scan")}
    semantic = {}
    expected_names = sorted(name for name, row in before["geometry"].items() if row["type"] == "MESH")
    for row in cell["rows"]:
        step, body, timing = row["step"], row["result"], row["timing"]
        key = timing["id"]
        request_path, response_path = folder / "client" / (key + ".TX.bin"), folder / "client" / (key + ".RX.bin")
        request, response = read(request_path), read(response_path)
        need(request["method"] == "tools/call" and request["params"] == plan["requests"][step], "exact_request")
        need(request["id"] == response["id"] == key and body_from_response(response) == body, "wire_body")
        need(not row["tool_error"] and row["rpc_error"] is None, "no_rpc_error")
        need(timing["wire_wait_ns"] + timing["client_decode_ns"] == timing["client_full_ns"] ==
             timing["closed_ns"] - timing["started_ns"] > 0, "actual_response_clock")
        need(timing["tx_bytes"] == request_path.stat().st_size and timing["rx_bytes"] == response_path.stat().st_size,
             "wire_bytes")
        traces = [r for r in logs if r.get("event") == "request_trace" and
                  str(r["trace"]["annotations"].get("mcp_request_id")) == key]
        need(len(traces) == 1, "one_actual_trace")
        event = traces[0]
        trace = event["trace"]
        need(event["pid"] == trace["pid"] == cell["product_pid"] and
             event["runtime_identity"]["build_id"] == "sha256:" + arm["source_sha256"] and
             event["identity_check"]["compatible"] and
             event["identity_check"]["actual"]["source_sha256"] == arm["source_sha256"], "trace_identity")
        need(trace["annotations"]["include_image"] is False and trace["annotations"]["mcp_native_image_block_count"] == 0
             and trace["annotations"]["delivery"] == "stdio_write_completed" and not trace["image_events"], "ordinary_text_publication")
        if "trace_id" in body:
            need(body["trace_id"] == trace["trace_id"], "body_trace_binding")
        if "request_trace" in body:
            need(body["request_trace"]["trace_id"] == trace["trace_id"] and
                 body["request_trace"]["request_id"] == trace["request_id"], "body_request_trace_binding")
        observes = [r for r in logs if r.get("event") == "observe" and r.get("request_id") == trace["request_id"]]
        need(len(observes) == 1 and observes[0]["pid"] == cell["product_pid"], "one_bound_observe")
        observe = observes[0]
        if "binding" in body:
            need(body["binding"]["runtime_source_sha256"] == arm["source_sha256"] and
                 body["binding"]["scene_revision"] == observe["scene_revision"], "current_scene_binding")
        if step == "overview":
            need(body["status"] == "overview" and body["query_result"]["mode"] == "overview" and
                 body["query_result"]["status"] == "complete" and body["query_result"]["exact_pair_count"] == 0,
                 "overview_complete_without_pair")
            need(sorted(obj["name"] for obj in body["objects"]) == expected_names and "Target" in expected_names,
                 "overview_current_inventory")
            need(body["runtime_identity"]["source_sha256"] == arm["source_sha256"], "overview_runtime")
            facts = json.loads(body["routing"]["context_text"])
            need(sorted(obj["name"] for obj in facts["objects"]) == expected_names and facts["unit"] == "m" and
                 facts["coordinate_frame"] == "world" and facts["scene_revision"] == observe["scene_revision"],
                 "overview_world_directory")
        else:
            need(binary(geometry(body)) == binary(geometry(truth[step])), "full_historical_geometry_" + step)
            work = observe["task_work"]
            need(body["status"] == "complete" and work["result_cache_hit"] is False and
                 work["kernel_calls"] == (11 if step == "nearest" else 66), "actual_cold_calls_" + step)
            if step == "nearest":
                need([x["name"] for x in body["nearest_objects"]] == ["Peer_000"] and body["coverage"] == {
                    "targets_excluding_focal": 11, "distance_valid": 11, "strictly_excluded": 0, "unresolved": 0},
                     "nearest_full_coverage")
            else:
                need(body["coverage"]["total_pairs"] == 66 and body["coverage"]["measured_match"] == 57 and
                     body["coverage"]["measured_nonmatch"] == 9 and body["coverage"]["unknown"] ==
                     body["coverage"]["deferred"] == 0, "scan_full_coverage")
        row.update(request=pin(request_path), response=pin(response_path), telemetry=trace, observe=observe)
        semantic[step] = comparable(body, arm)
    return semantic
