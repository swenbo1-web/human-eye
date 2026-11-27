"""Offline original-receipt audit; no product imports, processes or Blender."""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
import sys

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT/g60_b02")
VER = HERE.parents[1]
sys.path.insert(0, str(HERE))
from lifecycle import validate_lifecycle


def need(ok, why):
    if not ok:
        raise ValueError("049_audit_" + why)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha)


def save(path, data):
    path = Path(path)
    need(path.resolve().is_relative_to(RAW.resolve()), "output_scope")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    return pin(path)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def old045():
    original = VER / "m6_r3_replacement_entry_045/g60_verify.py"
    verifier = load("_049_untouched045_verifier", original)
    raw = RAW.parents[1] / "M6-045-R3-REPLACEMENT-ENTRY/g60/main_001/RESULTS.json"
    value = verifier.audit(raw)
    need(value["status"] == "pass" and value["actual_cells"] == 18 and value["actual_business_reads"] == 54, "old045_complete")
    report = dict(schema="m6-049-reverified-original045-lifecycle-v1", status="pass",
        original_results=pin(raw), untouched_original_verifier=pin(original),
        original_plan=pin(raw.parents[1] / "PLAN.json"),
        reverified=value,
        interpretation="Original 045 receipts re-audited offline, no source repair and no new process/geometry/timing run. Same 100ns Windows creation/exit times; archive and client boundaries remain separate.",
        product_calls=0, Blender=0)
    print(save(RAW / "old045/AUDIT.json", report))


def exact_json(value):
    if type(value) is float:
        return {"f64": value.hex()}
    if isinstance(value, list):
        return [exact_json(x) for x in value]
    if isinstance(value, dict):
        return {k: exact_json(x) for k, x in value.items()}
    return value


def compare_public(body, arm):
    def visit(x, key=None):
        if isinstance(x, dict):
            if key == "runtime_identity" and "source_file_count" in x:
                need(x["source_file_count"] == arm["source_file_count"], "manifest_file_count")
                x = dict(x, source_file_count="validated_manifest_source_file_count")
            if key == "request_trace":
                need(isinstance(x["request_id"], str) and len(x["request_id"]) == 32, "request_trace")
                return {k: ("validated_request_id" if k == "request_id" else visit(v, k)) for k, v in x.items()}
            return {k: visit(v, k) for k, v in x.items()}
        if isinstance(x, list):
            return [visit(v) for v in x]
        if key == "context_text" and isinstance(x, str):
            return visit(json.loads(x))
        if key in ("source_sha256", "runtime_source_sha256"):
            need(x == arm["source_sha256"], "public_source")
            return "validated_source"
        if key == "build_id":
            need(x == "sha256:" + arm["source_sha256"], "public_build")
            return "validated_build"
        if key == "distribution_version":
            need(x == arm["version"], "public_version")
            return "validated_version"
        if key == "trace_id":
            need(isinstance(x, str) and len(x) == 32, "public_trace")
            return "validated_trace"
        return x
    return exact_json(visit(body))


def wire_body(received):
    need("error" not in received and not received["result"].get("isError"), "no_tool_error")
    blocks = received["result"]["content"]
    need(len(blocks) == 1 and blocks[0]["type"] == "text", "one_original_text")
    return received["result"].get("structuredContent", json.loads(blocks[0]["text"]))


def counts(work):
    pairs = list(work.get("pairs", {}).values())
    path, unknown = {}, 0
    totals = {}
    for pair in pairs:
        sw = pair.get("surface_work")
        if sw is None:
            unknown += 1
            continue
        route = sw.get("solver_path", "not_published")
        path[route] = path.get(route, 0) + 1
        for key, value in sw.items():
            if type(value) is int:
                totals[key] = totals.get(key, 0) + value
    return dict(kernel_calls=work.get("kernel_calls"), cache_hits=work.get("cache_hits"),
        pair_rows=len(pairs), surface_work_missing=unknown, solver_paths=path,
        summed_surface_integer_counters=totals, result_cache_hit=work.get("result_cache_hit"),
        cache_before=work.get("measurement_cache_before"), cache_after=work.get("measurement_cache_after"),
        lower_bound_dispositions=len(work.get("bound_pair_dispositions", [])))


def result(family):
    plan_path = RAW / "PLAN.json"
    plan = read(plan_path)
    result_path = RAW / family / ("resume_001/RESULTS.json" if family == "G60" else "main_001/RESULTS.json")
    original = read(result_path)
    need(original["plan"] == pin(plan_path), "same_plan")
    for ref in plan["sources"].values():
        need(pin(ref["path"]) == ref, "held_source")
    case = plan["cases"][family]
    arms = "ABF" if family == "G60" else "AF"
    rows, generations, intervals = [], set(), []
    for ref in original["groups"]:
        group_path = Path(ref["receipt"]["path"])
        need(pin(group_path) == ref["receipt"], "group_hash")
        g = read(group_path)
        folder = Path(g["original_receipt"]["path"]).parent if g.get("metadata_requalification") else group_path.parent
        row = dict(group=g["group"], order=g["order"], valid=g["valid"], cells={}, errors=[])
        rows.append(row)
        if not g["valid"]:
            row["errors"] = g["errors"]
            continue
        need(g["family"] == family and set(g["cells"]) == set(arms) and not g["errors"], "group_complete")
        before = read(folder / "BEFORE.json")
        after_status = "captured_and_equal"
        if g.get("metadata_requalification"):
            need(g["after_snapshot_status"] == "not_acquired_no_replacement_or_fabrication" and not (folder / "AFTER.json").exists(), "honest_missing_after")
            after_status = "unmeasured_G01_comparator_failed_before_capture; source/copy close hashes preserved"
        else:
            after = read(folder / "AFTER.json")
            need(exact_json({k:v for k,v in before.items() if k != "resident"}) == exact_json({k:v for k,v in after.items() if k != "resident"}), "full_scene_preserved")
        for name, expected in case["expected_snapshot"].items():
            need(all(exact_json(before["geometry"][name][k]) == exact_json(v) for k,v in expected.items()), "geometry_source")
        own, spawn = read(folder / "native/OWNERSHIP.json"), read(folder / "native/SPAWN.json")
        need(own["normal_addon_unmodified"] and own["normal_queue_roundtrip_verified"] and own["ready"]["pid"] == g["host_pid"] and
             own["ready"]["background"] is False and "-b" not in spawn["command"] and "--background" not in spawn["command"] and
             spawn["input"] == case["asset"] and spawn["source_refs"] == plan["support"], "ordinary_GUI")
        close = g["gui_close"]
        need(close["status"] == "pass" and close["process_reaped"] and close["exit_code"] == 0 and close["forced"] is None and
             not close["released_port"]["owned_listener"] and not close["released_port"].get("any_listener", False) and
             close["source_unchanged"] and close["owned_copy_unchanged"] and close["original_addon_unchanged"], "all_GUI_released")
        semantics = []
        for arm in arms:
            c = read(folder / arm / "CELL.json")
            need(c == g["cells"][arm] and c["valid"] and not c["errors"], "raw_cell_binding")
            need([r["step"] for r in c["rows"]] == case["steps"], "business_inventory")
            lifecycle = validate_lifecycle(c, folder / arm / "client")
            need(lifecycle == c["lifecycle_audit"], "independent_lifecycle_repeat")
            for generation in lifecycle.get("process_generations", []):
                key = generation["pid"], generation["creation_time_100ns"]
                need(key not in generations, "reused_process_generation")
                generations.add(key)
            logs = [json.loads(x) for x in (folder / arm / "client/AUDIT.jsonl").read_bytes().splitlines() if x]
            semantic, steps = {}, {}
            previous = c["rows"][0]["timing"]["started_ns"]
            for r in c["rows"]:
                step, timing, body = r["step"], r["timing"], r["result"]
                stem = folder / arm / "client" / timing["id"]
                tx, rx = read(stem.with_suffix(".TX.bin")), read(stem.with_suffix(".RX.bin"))
                need(tx["params"] == case["requests"][step] and tx["id"] == rx["id"] == timing["id"] and wire_body(rx) == body, "original_wire")
                need(previous <= timing["started_ns"] <= timing["closed_ns"] <= r["body_decoded_ns"], "serial_business_clock")
                previous = r["body_decoded_ns"]
                event, = [x for x in logs if x.get("event") == "request_trace" and str(x["trace"]["annotations"].get("mcp_request_id")) == timing["id"]]
                trace = event["trace"]
                need(trace == r["telemetry"] and event["pid"] == c["product_pid"] and event["runtime_identity"]["build_id"] == "sha256:"+plan["arms"][arm]["source_sha256"] and
                     event["identity_check"]["compatible"], "actual_telemetry")
                observe, = [x for x in logs if x.get("event") == "observe" and x.get("request_id") == trace["request_id"]]
                need(observe == r["observe"], "original_work")
                semantic[step] = compare_public(body, plan["arms"][arm])
                work = observe.get("task_work")
                steps[step] = dict(original_work_present=work is not None, work=counts(work) if work is not None else None,
                    public_status=body["status"], coverage=body.get("coverage"),
                    stdio_rpc_ns=timing["client_full_ns"], complete_body_ns=r["body_decoded_ns"]-timing["started_ns"],
                    trace_ns=trace["duration_ns"], spans=trace["spans"])
            first, last = c["rows"][0]["timing"]["started_ns"], c["rows"][-1]["body_decoded_ns"]
            need(c["business_ns"] == last-first and c["workflow_ns"] == c["workflow_end_ns"]-c["workflow_start_ns"], "true_continuous_clock")
            row["cells"][arm] = dict(business_ns=c["business_ns"], workflow_ns=c["workflow_ns"], lifecycle=lifecycle, steps=steps,
                product_before=c.get("product_before"), product_after=c.get("product_after"),
                resource_counter_overhead_ns=c.get("resource_before_ns", 0)+c.get("resource_after_ns", 0))
            semantics.append(semantic)
        need(all(s == semantics[0] for s in semantics), "full_same_host_public_parity")
        intervals.append((g["started_ns"], g["ended_ns"]))
        row.update(host_pid=g["host_pid"], gui_close=close, full_GUI_ns=g["full_native_and_QA_lifecycle_ns"], after_snapshot_status=after_status,
            GUI_CPU_business_envelope_s=g["host_after_business"]["cpu_s"]-g["host_before_business"]["cpu_s"])
    need([r["order"] for r in rows] == plan["orders"][family] and len(rows) == 6 and all(r["valid"] for r in rows), "all_six_frozen_groups")
    need(all(a[1] <= b[0] for a,b in zip(intervals,intervals[1:])), "serial_groups")
    need(original["started_ns"] <= intervals[0][0] and intervals[-1][1] <= original["ended_ns"] and original["complete_window_ns"] == original["ended_ns"]-original["started_ns"], "outer_clock")
    result = dict(schema="m6-049-recomputed-live-audit-v1", status="pass", family=family, plan=pin(plan_path),
        original=pin(result_path), groups=rows, actual_hosts=6, actual_services=6*len(arms),
        actual_business_reads=6*len(arms)*len(case["steps"]), process_generations=len(generations),
        original_paired_business=original["business"], original_paired_process=original["process_lifetime"],
        interpretation="All original sources/wires/audits/OS boundaries re-read. No new kernel, timing, Blender or current-PID inference. Counter sums are only actually present integer fields; missing work remains null.",
        audit_source=pin(__file__))
    print(save(RAW / family / "AUDIT.json", result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("old045", "G60", "B02"))
    args = parser.parse_args()
    old045() if args.action == "old045" else result(args.action)
