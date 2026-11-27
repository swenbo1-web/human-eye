"""Independent, offline audit of the frozen 045 ordinary G60 entry experiment.

No product modules, subprocesses, sockets, process inspection or clocks are used.
Raw observations are never repaired. Business validity and OS-lifetime evidence
are separate, and all six predeclared rounds are required for either gate.
"""
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
RAW = Path("D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY")
CONTRACT = "3e9e06ea381d3ad3669f7ac14e5ba25e4ba245f0"
INHERITED_PLAN = "ca14c4f0147da180d330e947689cd411ac56310e5e860d1c197e78e9ab5f585e"
SOURCES = {
    "A": "a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d",
    "B": "ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e",
    "C": "b8c8bcd770a17f422789d3034bef608f4ada7aba90293397b83e3524b5a9402e",
}
ORDERS = ("ABC", "ACB", "BAC", "BCA", "CAB", "CBA")
STEPS = ("overview", "nearest", "scan")
PARENT_CLOCK = "parent_perf_counter_ns"
PROCESS_CLOCK = "Windows GetProcessTimes FILETIME 100 ns UTC"
OS_BRACKET_100NS = 320_000
DRIFT_TOLERANCE_NS = 2_000_000
IO_NAMES = ("config", "launch_receipt", "constructor_audit", "startup_receipt",
            "close_receipt", "close_readback")
MAIN_ORDER = (
    "client_begin", "config_begin", "config_end", "popen_begin", "popen_end",
    "launch_receipt_begin", "launch_receipt_end", "reader_start_begin", "reader_start_end",
    "initialize_write", "initialize_wire_decode", "catalog_write", "catalog_wire_decode",
    "constructor_audit_begin", "constructor_audit_end", "handle_bind_begin", "handle_bind_end",
    "startup_receipt_begin", "startup_receipt_end", "before_first_observe", "last_business_decode",
    "stdin_close_begin", "stdin_close_end", "wrapper_wait_begin", "wrapper_wait_end",
    "reader_join_begin", "reader_join_end", "stderr_close_begin", "stderr_close_end",
    "archive_begin", "archive_end", "close_receipt_begin", "close_receipt_end",
    "close_readback_begin", "close_readback_end", "client_end",
)


def need(condition, reason):
    if not condition:
        raise ValueError("045_g60_" + reason)


def integer(value, label, *, positive=False):
    need(type(value) is int and value >= (1 if positive else 0), label)
    return value


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}


class Files:
    """A single audit hashes each immutable file once, without changing it."""
    def __init__(self):
        self.checked = {}

    def check(self, ref):
        need(isinstance(ref, dict) and {"path", "bytes", "sha256"} <= ref.keys(), "file_descriptor")
        path = Path(ref["path"]).resolve(strict=True)
        if path not in self.checked:
            self.checked[path] = pin(path)
        actual = self.checked[path]
        need(actual["bytes"] == ref["bytes"] and actual["sha256"] == ref["sha256"], "changed:" + str(path))
        return path


def original_audit():
    # This module's top level is stdlib-only. Do not invoke its api()/arms().
    path = HERE.parent / "m6_r3_region_attribution_043/live_g60/common.py"
    spec = importlib.util.spec_from_file_location("_045_readonly_043_semantics", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def exact_json(value):
    if type(value) is float:
        return {"binary64": value.hex()}
    if isinstance(value, list):
        return [exact_json(x) for x in value]
    if isinstance(value, dict):
        return {k: exact_json(v) for k, v in value.items()}
    return value


def union_length(intervals):
    """Measure a union, so nested experiment spans are never added twice."""
    merged = []
    for start, end in sorted(intervals):
        need(type(start) is int and type(end) is int and start <= end, "interval")
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged)


def clipped_union(intervals, lower, upper):
    return union_length([(max(a, lower), min(b, upper)) for a, b in intervals
                         if max(a, lower) <= min(b, upper)])


def paired_summary(rounds, metric, *, gate=None):
    """Ratios and differences are paired first; no incomplete-round median."""
    values, missing = [], []
    for row in rounds:
        item = row.get(metric)
        if not (isinstance(item, dict) and set(item) == set("ABC") and
                all(type(v) is int and v > 0 for v in item.values())):
            missing.append(row["group"])
            continue
        pairs = {}
        for candidate, reference in (("B", "A"), ("C", "A"), ("C", "B")):
            delta = item[candidate] - item[reference]
            pairs[candidate + "_vs_" + reference] = {
                "delta_ns": delta,
                "relative_increase": Fraction(delta, item[reference]),
                "saving": Fraction(-delta, item[reference]),
                "faster": delta < 0, "equal": delta == 0,
            }
        values.append({"group": row["group"], "order": row["order"], "ns": item, "pairs": pairs})
    out = {"status": "unmeasured_or_incomplete", "planned_rounds": 6, "measured_rounds": len(values),
           "missing_rounds": missing, "rounds": json_numbers(values), "gate": None}
    if len(rounds) != 6 or len(values) != 6 or [r["order"] for r in rounds] != list(ORDERS):
        return out
    out.update(status="measured", medians_ns={a: float(median(r["ns"][a] for r in values)) for a in "ABC"}, pairs={})
    for pair in ("B_vs_A", "C_vs_A", "C_vs_B"):
        entries = [r["pairs"][pair] for r in values]
        out["pairs"][pair] = {
            "median_delta_ns": float(median(e["delta_ns"] for e in entries)),
            "median_relative_increase": float(median(e["relative_increase"] for e in entries)),
            "median_saving": float(median(e["saving"] for e in entries)),
            "faster_rounds": sum(e["faster"] for e in entries),
            "equal_rounds": sum(e["equal"] for e in entries),
            "slower_rounds": sum(not e["faster"] and not e["equal"] for e in entries),
        }
    c_a = [r["pairs"]["C_vs_A"] for r in values]
    c_b = [r["pairs"]["C_vs_B"] for r in values]
    saving = median(e["saving"] for e in c_a)
    relative = median(e["relative_increase"] for e in c_b)
    if gate == "business":
        out["gate"] = saving >= Fraction(1, 10) and sum(e["faster"] for e in c_a) >= 5 and relative <= Fraction(1, 20)
    elif gate == "lifetime":
        out["gate"] = saving > 0 and relative <= Fraction(1, 20)
    return out


def json_numbers(value):
    if isinstance(value, Fraction):
        return float(value)
    if isinstance(value, list):
        return [json_numbers(x) for x in value]
    if isinstance(value, dict):
        return {k: json_numbers(v) for k, v in value.items()}
    return value


def verify_plan(plan, files):
    need(plan["contract"] == CONTRACT and plan["cycle_id"] == "M6-045-R3-REPLACEMENT-ENTRY", "contract")
    inherited_path = files.check(plan["inherited"])
    need(plan["inherited"]["sha256"] == INHERITED_PLAN, "inherited_plan")
    inherited = read(inherited_path)
    for key in ("orders", "steps", "requests", "arms", "asset", "support", "truth", "release_bindings", "expected_snapshot"):
        need(exact_json(plan[key]) == exact_json(inherited[key]), "inherited_" + key)
    need(plan["orders"] == list(ORDERS) and plan["steps"] == list(STEPS), "frozen_orders")
    need(plan["clocks"]["wall_clock_tolerance_ns"] == DRIFT_TOLERANCE_NS and
         plan["clocks"]["os_exit_bracket_100ns"] == OS_BRACKET_100NS, "frozen_clock_tolerance")
    need(plan["lifecycle_gate"] == {"minimum_saving_C_vs_A_strictly_above": 0,
         "maximum_relative_C_vs_B": .05, "expected_triplets": 6}, "frozen_lifecycle_gate")
    for refs in (plan["sources"], plan["source_045"], plan["support"], plan["truth"], plan["release_bindings"]):
        for ref in refs.values():
            files.check(ref)
    for name in ("asset", "candidate", "snapshot_fixture"):
        files.check(plan[name])
    bindings = {}
    for arm in "ABC":
        release = plan["arms"][arm]
        binding_path = files.check(plan["release_bindings"][arm])
        binding = read(binding_path)
        identity = binding["identity"]
        need(identity["source_sha256"] == SOURCES[arm] == release["source_sha256"], "source_" + arm)
        need(identity["distribution_version"] == release["version"] and
             Path(binding["site_packages"]).resolve() == Path(release["site_packages"]).resolve(), "release_" + arm)
        source_files = binding["source_files"]
        need(len(source_files) == 143 and len({r["path"] for r in source_files}) == 143, "source_inventory_" + arm)
        for entry in source_files:
            path = Path(release["site_packages"]) / entry["path"]
            need(path.resolve().is_relative_to(Path(release["site_packages"]).resolve()), "source_path_scope")
            actual = pin(path)
            need(actual["sha256"] == entry["sha256"], "installed_bytes_" + arm)
            files.checked[path.resolve()] = actual
        digest_input = {"base_version": identity["base_version"], "implementation_revision": identity["implementation_revision"],
                        "files": source_files}
        digest = hashlib.sha256(json.dumps(digest_input, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        need(digest == SOURCES[arm], "source_digest_" + arm)
        launcher = Path(release["command_prefix"][-1])
        need(pin(launcher)["sha256"] == binding["launcher_sha256"], "launcher_" + arm)
        need(pin(binding_path.parent / "installed_release.py")["sha256"] == binding["admin_sha256"], "admin_" + arm)
        bindings[arm] = {"binding": plan["release_bindings"][arm], "source_sha256": digest, "files": 143}
    return bindings


def event_map(lifecycle, *, business):
    events = lifecycle["events"]
    need(isinstance(events, list) and events, "events")
    need(len({e["name"] for e in events}) == len(events), "duplicate_event")
    by = {e["name"]: e for e in events}
    ordered = [n for n in MAIN_ORDER if business or n not in ("before_first_observe", "last_business_decode")]
    need(set(ordered) | {"reader_receive_return"} == set(by), "event_inventory")
    stamps = [integer(by[n]["at_ns"], n, positive=True) for n in ordered]
    need(stamps == sorted(stamps), "main_thread_order")
    need(by["stdin_close_begin"]["at_ns"] <= by["reader_receive_return"]["at_ns"] <= by["reader_join_end"]["at_ns"],
         "reader_return_join")
    anchors = sorted((e for e in events if "filetime_100ns" in e), key=lambda e: e["at_ns"])
    need(anchors[0]["name"] == "client_begin" and anchors[-1]["name"] == "client_end", "clock_anchor_scope")
    first = anchors[0]
    drifts, spans = [], []
    for event in anchors:
        start, after = event["at_ns"], integer(event["filetime_observation_after_ns"], "clock_after", positive=True)
        ft = integer(event["filetime_100ns"], "filetime", positive=True)
        need(start <= after, "clock_observation_bracket")
        span = (after-start) + (first["filetime_observation_after_ns"]-first["at_ns"])
        drift = (ft-first["filetime_100ns"])*100 - (start-first["at_ns"])
        need(abs(drift) <= DRIFT_TOLERANCE_NS+span, "filetime_monotonic_consistency:" + event["name"])
        drifts.append(drift)
        spans.append(after-start)
    return by, {"clock_pair_samples": len(anchors), "maximum_absolute_drift_ns": max(map(abs, drifts)),
                "timestamp_call_brackets_sum_ns": sum(spans), "timestamp_call_bracket_max_ns": max(spans),
                "no_probe_duration_subtracted": True}


def validate_lifecycle(record, folder, *, business=True, expected_wrapper_image=None, expected_service_image=None):
    """Return measured or unmeasured; invalid OS proof never becomes a duration.

    Uses only captured clocks and held-handle records. It never consults file
    modification times or queries a current process that may have reused a PID.
    """
    folder = Path(folder)
    lc = record.get("lifecycle", {})
    out = {"status": "unmeasured", "errors": [], "raw_declared_valid": lc.get("valid")}
    try:
        need(lc.get("valid") is True and not lc.get("errors"), "declared_lifecycle")
        need(lc["clock"] == {"kind": PARENT_CLOCK, "process_clock": PROCESS_CLOCK}, "clock_names")
        by, probes = event_map(lc, business=business)
        processes = lc["processes"]
        need(set(processes) == {"wrapper", "service"}, "two_process_roles")
        wrapper, service = processes["wrapper"], processes["service"]
        need(wrapper["pid"] == record.get("wrapper_pid", record["product_close"]["pid"]), "wrapper_pid")
        startup = read(folder / "STARTUP.json")
        need(service["pid"] == record.get("product_pid", startup["actual_pid"]) == startup["actual_pid"], "service_pid")
        launch = read(folder / "LAUNCH.json")
        need(wrapper["pid"] == launch["popen_pid"], "launch_pid")
        need(Path(wrapper["image"]).resolve() == Path(expected_wrapper_image or launch["command"][0]).resolve(), "wrapper_image")
        if expected_service_image is not None:
            need(Path(service["image"]).resolve() == Path(expected_service_image).resolve(), "service_image")
        controller = integer(lc["controller_pid"], "controller_pid", positive=True)
        need(wrapper["parent_pid"] == controller and service["parent_pid"] ==
             (controller if service["pid"] == wrapper["pid"] else wrapper["pid"]), "process_ancestry")
        unique = {}
        for role, process in processes.items():
            pid = integer(process["pid"], role+"_pid", positive=True)
            creation = integer(process["creation_time_100ns"], role+"_creation", positive=True)
            exit_time = integer(process["exit_time_100ns"], role+"_exit", positive=True)
            need(process["alive_at_bind"] and process["owned_held_handle"] and process["wait_result"] == 0 and
                 process["exit_code"] == 0 and creation < exit_time, "held_handle_normal_exit_" + role)
            bind = process["bind_times"]
            need(bind["creation_time_100ns"] == creation and bind["exit_time_100ns"] == 0, "handle_generation_" + role)
            integer(process["kernel_100ns"], "kernel_cpu")
            integer(process["user_100ns"], "user_cpu")
            need(process["kernel_100ns"] >= bind["kernel_100ns"] and
                 process["user_100ns"] >= bind["user_100ns"], "cpu_monotonic")
            observed = process["exit_observation"]
            need(len(observed) == 2 and observed[0]["at_ns"] <= observed[1]["at_ns"] and
                 by["client_end"]["at_ns"] <= observed[0]["at_ns"], "post_workflow_handle_read")
            need(exit_time <= observed[1]["filetime_100ns"]+OS_BRACKET_100NS, "exit_before_observation")
            key = (pid, creation)
            if key in unique:
                previous = unique[key]
                need(all(process[k] == previous[k] for k in ("pid", "parent_pid", "image", "creation_time_100ns",
                     "exit_time_100ns", "exit_code", "wait_result", "kernel_100ns", "user_100ns")), "same_pid_conflicting_record")
            unique[key] = process
        need(service["pid"] != wrapper["pid"] or service["creation_time_100ns"] == wrapper["creation_time_100ns"],
             "same_pid_two_generations")
        need(startup["startup_trace"]["pid"] == service["pid"], "constructor_pid")
        created = wrapper["creation_time_100ns"]
        need(by["popen_begin"]["filetime_100ns"]-OS_BRACKET_100NS <= created <=
             by["popen_end"]["filetime_100ns"]+OS_BRACKET_100NS, "creation_popen_bracket")
        need(created <= service["creation_time_100ns"] <= by["handle_bind_end"]["filetime_100ns"]+OS_BRACKET_100NS,
             "service_creation_bracket")
        need(all(p["exit_time_100ns"] <= by["client_end"]["filetime_100ns"]+OS_BRACKET_100NS for p in unique.values()),
             "exit_before_client_end")
        at_wait = lc["exit_at_wrapper_wait"]
        need(at_wait["wrapper"] == 0 and at_wait["service"] in (0, 258), "original_wait_result")
        if at_wait["service"] == 0:
            need(max(p["exit_time_100ns"] for p in unique.values()) <=
                 by["archive_begin"]["filetime_100ns"]+OS_BRACKET_100NS, "archive_after_process_exit")
        lifetime = (max(p["exit_time_100ns"] for p in unique.values())-created)*100
        need(lc["os_survival_ns"] == lifetime > 0, "os_survival_recomputed")
        reader = lc["reader"]
        need(reader["pid"] == controller and reader["receive_return_observed"] and reader["joined_and_inactive"], "reader_inactive")
        integer(reader["native_tid"], "reader_native_tid", positive=True)
        spans = lc["experiment_io"]
        need([s["name"] for s in spans] == list(IO_NAMES), "experiment_io_inventory")
        for span in spans:
            name = span["name"]
            need(span["started_ns"] == by[name+"_begin"]["at_ns"] and span["closed_ns"] == by[name+"_end"]["at_ns"],
                 "io_boundary_" + name)
            need(span["files"] == span["wrote_files"]+span["read_files"], "io_file_accounting")
            integer(span["bytes"], "io_bytes")
        span_by = {s["name"]: s for s in spans}
        written = {"config": "CONFIG.json", "launch_receipt": "LAUNCH.json", "startup_receipt": "STARTUP.json",
                   "close_receipt": "CLOSE.json", "close_readback": "CLOSE.json"}
        for name, filename in written.items():
            count = 4 if name == "launch_receipt" else 1
            size = (folder / filename).stat().st_size
            if name == "launch_receipt":
                size += sum(launch[k]["bytes"] for k in ("python", "entry", "config"))
            need(span_by[name]["files"] == count and span_by[name]["bytes"] == size, "io_actual_size_" + name)
        audit_bytes = (folder / "AUDIT.jsonl").read_bytes()
        prefix_size = span_by["constructor_audit"]["bytes"]
        need(span_by["constructor_audit"]["files"] == 1 and prefix_size <= len(audit_bytes), "constructor_audit_prefix_size")
        prefix = audit_bytes[:prefix_size]
        need(not prefix or prefix.endswith(b"\n"), "constructor_audit_line_boundary")
        events = [json.loads(line) for line in prefix.splitlines() if line]
        constructors = [e for e in events if e.get("measurement_scope") == "service_constructor_only"]
        need(len(constructors) == 1 and constructors[0] == startup["startup_trace"], "constructor_prefix_binding")
        archive = lc["archive"]
        need(archive["name"] == "archive" and archive["started_ns"] == by["archive_begin"]["at_ns"] and
             archive["closed_ns"] == by["archive_end"]["at_ns"], "archive_boundaries")
        entries = archive["entries"]
        actual = {p.name: p.stat().st_size for pattern in ("*.TX.bin", "*.RX.bin") for p in folder.glob(pattern)}
        need(len(entries) == len({e["path"] for e in entries}) and
             {e["path"]: e["bytes"] for e in entries} == actual and
             archive["files"] == len(actual) == (11 if business else 5) and
             archive["bytes"] == sum(actual.values()), "archive_actual_inventory")
        need(record["product_close"]["method"] == "eof" and record["product_close"]["exit_code"] == 0, "normal_original_close")
        startup_times = (("initialize", startup["timing"]), ("catalog", startup["tools_time"]))
        for name, timing in startup_times:
            need(by[name+"_write"]["at_ns"] == timing["started_ns"] and
                 by[name+"_wire_decode"]["at_ns"] == timing["closed_ns"], "startup_wire_clock")
            key = timing["id"]
            sent, received = read(folder / (key+".TX.bin")), read(folder / (key+".RX.bin"))
            need(sent["id"] == received["id"] == key and sent["method"] ==
                 ("initialize" if name == "initialize" else "tools/list"), "startup_wire_method")
            need(received == startup["hello" if name == "initialize" else "catalog"], "startup_wire_response")
            need(timing["tx_bytes"] == (folder / (key+".TX.bin")).stat().st_size and
                 timing["rx_bytes"] == (folder / (key+".RX.bin")).stat().st_size, "startup_wire_size")
        intervals = [(s["started_ns"], s["closed_ns"]) for s in spans]
        io_before_business = None
        if business:
            first = record["rows"][0]["timing"]["started_ns"]
            final = record["rows"][-1]["body_decoded_ns"]
            need(by["before_first_observe"]["at_ns"] <= first < final <= by["last_business_decode"]["at_ns"] <=
                 by["stdin_close_begin"]["at_ns"], "business_lifecycle_binding")
            io_before_business = clipped_union(intervals, by["client_begin"]["at_ns"], first)
        phases = {name: by[end]["at_ns"]-by[start]["at_ns"] for name, start, end in (
            ("client_full_ns", "client_begin", "client_end"),
            ("config_ns", "config_begin", "config_end"),
            ("popen_ns", "popen_begin", "popen_end"),
            ("initialize_rpc_ns", "initialize_write", "initialize_wire_decode"),
            ("catalog_rpc_ns", "catalog_write", "catalog_wire_decode"),
            ("handle_bind_ns", "handle_bind_begin", "handle_bind_end"),
            ("stdin_close_ns", "stdin_close_begin", "stdin_close_end"),
            ("wrapper_wait_ns", "wrapper_wait_begin", "wrapper_wait_end"),
            ("reader_join_ns", "reader_join_begin", "reader_join_end"),
            ("archive_ns", "archive_begin", "archive_end"),
            ("close_receipt_ns", "close_receipt_begin", "close_receipt_end"),
            ("close_readback_ns", "close_readback_begin", "close_readback_end"),
        )}
        # The inherited workflow end precedes client_end's light timestamp; it
        # is not silently extended to include the later held-handle report.
        need(record["workflow_ns"] == record["workflow_end_ns"]-record["workflow_start_ns"] > 0, "workflow_clock")
        need(record["workflow_end_ns"] <= by["client_end"]["at_ns"], "client_end_after_original_workflow")
        phases.update(experiment_io_union_ns=union_length(intervals),
                      experiment_io_and_archive_union_ns=union_length(intervals+[(archive["started_ns"], archive["closed_ns"])]),
                      experiment_io_before_business_ns=io_before_business)
        if business:
            phases.update(client_to_first_write_ns=first-by["client_begin"]["at_ns"],
                          last_decode_to_stdin_ns=by["stdin_close_begin"]["at_ns"]-final,
                          last_decode_to_client_end_ns=by["client_end"]["at_ns"]-final)
        out.update(status="measured", os_survival_ns=lifetime, phases=phases, clock_quality=probes,
                   process_generations=[{"pid": pid, "creation_time_100ns": creation} for pid, creation in unique],
                   process_records=processes,
                   CPU_total_100ns=sum(p["kernel_100ns"]+p["user_100ns"] for p in unique.values()),
                   service_alive_at_wrapper_wait=at_wait["service"] == 258,
                   archive_files=archive["files"], archive_bytes=archive["bytes"],
                   exit_before_archive_same_clock_100ns=by["archive_begin"]["filetime_100ns"]-max(p["exit_time_100ns"] for p in unique.values()),
                   attribution="Parent monotonic phase durations and OS FILETIME survival are separate. Clock proximity alone proves no cause.")
    except (KeyError, ValueError, TypeError, OSError, AssertionError) as exc:
        out["errors"].append(type(exc).__name__+": "+str(exc))
    return out


def verify_preflight(ref, plan_ref, files):
    path = files.check(ref)
    data = read(path)
    need(data["plan"] == plan_ref and data["status"] == "pass" and not data["errors"] and
         data["geometry_requests"] == data["Blender"] == 0, "private_clock_preflight")
    proof = validate_lifecycle(data, path.parent / "client", business=False)
    need(proof["status"] == "measured", "independent_preflight:" + repr(proof["errors"]))
    recorded = data["lightweight_timestamp_probes"]
    probes = proof["clock_quality"]
    need(recorded["count"] == probes["clock_pair_samples"] and
         recorded["within_bracket_ns_sum"] == probes["timestamp_call_brackets_sum_ns"] and
         recorded["within_bracket_ns_max"] == probes["timestamp_call_bracket_max_ns"] and
         recorded["excluded_from_reduction"] is False, "preflight_probe_accounting")
    return {"status": "pass", "raw": ref, "proof": proof}


def verify_gui(group, folder, plan):
    before, after = read(folder / "BEFORE.json"), read(folder / "AFTER.json")
    need(exact_json({k: v for k, v in before.items() if k != "resident"}) ==
         exact_json({k: v for k, v in after.items() if k != "resident"}), "scene_custody")
    need(before["pid"] == group["host_pid"] and before["background"] is False and before["main_thread"], "ordinary_GUI")
    need(before["frame"] == plan["frame"] and before["subframe"] == plan["subframe"] and before["scale"] == plan["scale"], "frame_units")
    for name, expected in plan["expected_snapshot"].items():
        need(all(exact_json(before["geometry"][name][k]) == exact_json(v) for k, v in expected.items()), "native_geometry_" + name)
    ownership, spawn = read(folder / "native/OWNERSHIP.json"), read(folder / "native/SPAWN.json")
    need(ownership["normal_addon_unmodified"] and ownership["normal_queue_roundtrip_verified"] and
         ownership["ready"]["background"] is False and ownership["ready"]["pid"] == group["host_pid"], "addon_queue")
    need("--background" not in spawn["command"] and "-b" not in spawn["command"] and
         spawn["GUI_mode_no_background_flag"] and spawn["source_refs"] == plan["support"] and spawn["input"] == plan["asset"], "ordinary_launch")
    close = group["gui_close"]
    need(close["status"] == "pass" and close["process_reaped"] and close["exit_code"] == 0 and close["forced"] is None and
         not close["released_port"]["owned_listener"] and not close["released_port"].get("any_listener", False) and
         close["source_unchanged"] and close["owned_copy_unchanged"] and close["original_addon_unchanged"], "GUI_normal_shutdown")
    callback = read(folder / "native/GUI_CLOSED.json")
    need(callback == close["GUI_close_callback"] and callback["pid"] == close["pid"] == group["host_pid"] and
         callback["stopped"] and close["released_port"]["expected_pid"] == group["host_pid"], "GUI_callback_release_binding")
    need(group["full_native_and_QA_lifecycle_ns"] == group["ended_ns"]-group["started_ns"] > 0, "GUI_window")
    cells = [group["cells"][a] for a in group["order"]]
    need(all(group["started_ns"] <= c["started_ns"] < c["ended_ns"] <= group["ended_ns"] for c in cells) and
         all(a["ended_ns"] <= b["started_ns"] for a, b in zip(cells, cells[1:])), "actual_serial_arm_order")
    return before


def business_cell(cell, folder, plan, before, original):
    need(cell["valid"] and not cell["errors"] and [r["step"] for r in cell["rows"]] == list(STEPS), "valid_business_cell")
    rows = cell["rows"]
    semantics = original.audit_rows(folder, deepcopy(cell), plan, before)
    need(semantics == cell["semantic"], "semantic_receipt")
    first, final = rows[0]["timing"]["started_ns"], rows[-1]["body_decoded_ns"]
    need(cell["business_ns"] == final-first > 0 and cell["last_reply_ns"] == final, "primary_business_clock")
    need(cell["workflow_ns"] == cell["workflow_end_ns"]-cell["workflow_start_ns"] and
         cell["workflow_start_ns"] <= first < final <= cell["workflow_end_ns"], "inherited_workflow_clock")
    previous = first
    for row in rows:
        timing = row["timing"]
        need(previous <= timing["started_ns"] <= timing["closed_ns"] <= row["body_decoded_ns"], "sequential_complete_decodes")
        previous = row["body_decoded_ns"]
    need(cell["startup_discovery_ns"] == first-cell["workflow_start_ns"] and
         cell["through_scan_reply_ns"] == final-cell["workflow_start_ns"] and
         cell["product_close_and_final_counter_ns"] == cell["workflow_end_ns"]-final, "original_clock_components")
    return {"status": "measured", "business_ns": final-first, "workflow_ns": cell["workflow_ns"], "semantic": semantics,
            "steps": {r["step"]: {"stdio_rpc_ns": r["timing"]["client_full_ns"],
                                  "complete_body_ns": r["body_decoded_ns"]-r["timing"]["started_ns"],
                                  "body_after_rpc_decode_ns": r["body_decoded_ns"]-r["timing"]["closed_ns"]} for r in rows}}


def compare_runner_summary(actual, computed, label):
    need(actual["complete_groups"] == computed["measured_rounds"] and actual["planned_groups"] == 6, label+"_counts")
    if computed["status"] != "measured":
        need(actual["status"] == "incomplete_or_unmeasured", label+"_unmeasured")
        return
    # Root's calculation uses binary64 ratios. Repeat that representation here
    # for exact raw-field congruence, alongside the rational gate above.
    rounds = [r["ns"] for r in computed["rounds"]]
    need(actual["median_saving_C_vs_A"] == median(1-r["C"]/r["A"] for r in rounds) and
         actual["median_delta_C_vs_B"] == median(r["C"]/r["B"]-1 for r in rounds) and
         actual["median_saving_B_vs_A"] == median(1-r["B"]/r["A"] for r in rounds), label+"_paired_values")
    need(actual["C_faster_A"] == sum(r["C"] < r["A"] for r in rounds) and
         actual["C_faster_B"] == sum(r["C"] < r["B"] for r in rounds) and
         actual["B_faster_A"] == sum(r["B"] < r["A"] for r in rounds), label+"_directions")
    need(actual["medians_ns"] == {a: median(r[a] for r in rounds) for a in "ABC"}, label+"_medians")
    if computed["gate"] is not None:
        need(actual["status"] == ("pass" if computed["gate"] else "fail"), label+"_gate")


def closeout_summary(rounds):
    cells = [c for r in rounds for c in r["cells"].values()]
    lifecycles = [c["lifecycle"] for c in cells if c["lifecycle"]["status"] == "measured"]
    measured_by_arm = {a: [r["cells"][a] for r in rounds if a in r["cells"]] for a in "ABC"}
    by_arm = {}
    for arm, observations in measured_by_arm.items():
        lives = [c["lifecycle"] for c in observations if c["lifecycle"]["status"] == "measured"]
        sampled = [c for c in observations if c.get("product_after") and c.get("product_before")]
        by_arm[arm] = {
            "measured_process_lifetimes": len(lives),
            "owned_wrapper_and_service_CPU_s": sum(c["CPU_total_100ns"] for c in lives)/1e7,
            "original_product_business_boundary_CPU_s": sum(c["product_after"]["cpu_s"]-c["product_before"]["cpu_s"] for c in sampled),
            "maximum_observed_product_lifetime_peak_working_set_bytes": max((c["product_after"]["peak_working_set_bytes"] for c in sampled), default=None),
            "maximum_product_working_set_at_last_business_boundary_bytes": max((c["product_after"]["current_working_set_bytes"] for c in sampled), default=None),
            "resource_boundary_probe_ns_total": sum(c["resource_boundary_overhead_ns"] for c in observations),
        }
    return {
        "GUI_normal_exits": len([r for r in rounds if r["status"] == "pass"]),
        "original_EOF_product_exits": len(cells),
        "measured_lifecycle_cells": len(lifecycles),
        "owned_process_generations": sum(len(c["process_generations"]) for c in lifecycles),
        "all_measured_roles_normal_exit": all(p["exit_code"] == 0 and p["wait_result"] == 0
                                              for c in lifecycles for p in c["process_records"].values()),
        "both_roles_already_exited_before_original_reader_join_archive": sum(not c["service_alive_at_wrapper_wait"] for c in lifecycles),
        "raw_archive_files": sum(c["archive_files"] for c in lifecycles),
        "raw_archive_bytes": sum(c["archive_bytes"] for c in lifecycles),
        "clock_pairs": sum(c["clock_quality"]["clock_pair_samples"] for c in lifecycles),
        "timestamp_probe_brackets_ns_total": sum(c["clock_quality"]["timestamp_call_brackets_sum_ns"] for c in lifecycles),
        "maximum_absolute_clock_drift_ns": max((c["clock_quality"]["maximum_absolute_drift_ns"] for c in lifecycles), default=None),
        "maximum_timestamp_probe_bracket_ns": max((c["clock_quality"]["timestamp_call_bracket_max_ns"] for c in lifecycles), default=None),
        "GUI_lifecycle_ns": [r.get("full_gui_ns") for r in rounds],
        "GUI_CPU_business_envelope_s": sum(r.get("GUI_CPU_business_envelope_s", 0) for r in rounds),
        "ports": [r.get("released_port") for r in rounds],
        "by_arm": by_arm,
        "limits": "CPU from held handles covers each owned process lifetime; business-boundary CPU is a separate original sample. Product memory peaks are sampled after the last business reply, not final process-exit peaks. Individual peaks are never summed into a simultaneous tree peak. Controller CPU, total machine CPU and continuous memory are unmeasured. No current PID lookup or port probe is performed by this verifier.",
    }


def audit(result_path):
    """Audit a sealed RESULTS.json; all reads, including source hashes, are untimed."""
    result_path = Path(result_path).resolve(strict=True)
    files = Files()
    result = read(result_path)
    out = {"schema": "m6-045-g60-independent-verification-v1", "status": "failed", "result": pin(result_path),
           "verifier": pin(__file__), "errors": [], "rounds": [], "no_product_or_host_calls": True,
           "scope": "Independent recomputation of preserved raw wire, source identity, semantics, clocks, native exits and paired gates; no new measurements."}
    try:
        plan_path = files.check(result["plan"])
        plan = read(plan_path)
        out["plan"] = result["plan"]
        out["bindings"] = verify_plan(plan, files)
        out["preflight"] = verify_preflight(result["preflight"], result["plan"], files)
        original = original_audit()
        groups = result["groups"]
        need(result["planned"] == list(ORDERS) and len(groups) <= 6, "planned_rounds")
        expected_dirs = {f"G{i:02d}-{order}" for i, order in enumerate(ORDERS, 1)}
        observed_dirs = {p.name for p in result_path.parent.glob("G*-*") if p.is_dir()}
        need(observed_dirs <= expected_dirs, "unexpected_or_replacement_round")
        referenced_dirs = {Path(g["raw"]["path"]).parent.name for g in groups}
        need(len(referenced_dirs) == len(groups) and observed_dirs == referenced_dirs, "round_inventory")
        generations = set()
        group_clock_intervals = []
        for index, record in enumerate(groups, 1):
            order = ORDERS[index-1]
            raw_path = files.check(record["raw"])
            folder = raw_path.parent
            group = read(raw_path)
            row = {"group": index, "order": order, "raw": record["raw"], "errors": [], "cells": {}}
            out["rounds"].append(row)
            try:
                need(record["group"] == group["group"] == index and record["order"] == group["order"] == order and
                     folder.name == f"G{index:02d}-{order}", "fixed_round_order")
                need(folder.parent == result_path.parent, "current_result_round_scope")
                need(record["valid"] and group["valid"] and not group["errors"] and set(group["cells"]) == set("ABC"), "valid_group")
                before = verify_gui(group, folder, plan)
                need(record["full_gui_ns"] == group["full_native_and_QA_lifecycle_ns"], "GUI_summary_clock")
                row["full_gui_ns"] = record["full_gui_ns"]
                row["host_pid"] = group["host_pid"]
                row["released_port"] = group["gui_close"]["released_port"]
                row["GUI_CPU_business_envelope_s"] = group["host_after_business"]["cpu_s"]-group["host_before_business"]["cpu_s"]
                group_clock_intervals.append((group["started_ns"], group["ended_ns"]))
                business_times, workflows, lifetimes, client_full = {}, {}, {}, {}
                semantic = {}
                for arm in "ABC":
                    cell_folder = folder / arm
                    cell = read(cell_folder / "CELL.json")
                    need(cell == group["cells"][arm] and cell["arm"] == arm and cell["host_pid"] == group["host_pid"], "cell_group_binding")
                    proof = business_cell(cell, cell_folder, plan, before, original)
                    semantic[arm] = proof.pop("semantic")
                    lifecycle = validate_lifecycle(cell, cell_folder / "client", expected_wrapper_image=plan["arms"][arm]["command_prefix"][0],
                                                   expected_service_image=out["preflight"]["proof"]["process_records"]["service"]["image"])
                    row["cells"][arm] = {"business": proof, "lifecycle": lifecycle,
                        "product_pid": cell["product_pid"], "wrapper_pid": cell["wrapper_pid"],
                        "product_before": cell.get("product_before"), "product_after": cell.get("product_after"),
                        "post_workflow_handle_report_ns": cell["lifecycle"].get("post_workflow_handle_report_ns"),
                        "resource_boundary_overhead_ns": cell.get("resource_before_ns", 0)+cell.get("resource_after_ns", 0)}
                    business_times[arm], workflows[arm] = proof["business_ns"], proof["workflow_ns"]
                    if lifecycle["status"] == "measured":
                        lifetimes[arm] = lifecycle["os_survival_ns"]
                        client_full[arm] = lifecycle["phases"]["client_full_ns"]
                        for generation in lifecycle["process_generations"]:
                            key = (generation["pid"], generation["creation_time_100ns"])
                            need(key not in generations, "process_generation_reused_between_cells")
                            generations.add(key)
                need(semantic["A"] == semantic["B"] == semantic["C"], "same_host_full_answers")
                need(record["business_ns"] == business_times and record["workflow_ns"] == workflows, "raw_summary_clocks")
                row.update(business_ns=business_times, workflow_ns=workflows)
                if len(lifetimes) == 3:
                    row["process_ns"] = lifetimes
                    row["client_ns"] = client_full
                    need(record["lifetime_valid"] and record["process_ns"] == lifetimes, "lifetime_summary")
                else:
                    row["lifecycle_qualification_note"] = "Independent lifecycle qualification is incomplete; business results are retained."
                row["status"] = "pass"
            except (ValueError, KeyError, TypeError, OSError, AssertionError) as exc:
                row["status"] = "invalid"
                row["errors"].append(type(exc).__name__+": "+str(exc))
        need(len(groups) == 6 and observed_dirs == expected_dirs and all(r["status"] == "pass" for r in out["rounds"]), "six_original_complete_rounds")
        out["business"] = paired_summary(out["rounds"], "business_ns", gate="business")
        out["process_lifetime"] = paired_summary(out["rounds"], "process_ns", gate="lifetime")
        out["workflow"] = paired_summary(out["rounds"], "workflow_ns")
        out["client_full"] = paired_summary(out["rounds"], "client_ns")
        phases = set.intersection(*(set(c["lifecycle"]["phases"]) for r in out["rounds"] for c in r["cells"].values()
                                    if c["lifecycle"]["status"] == "measured")) if any(r.get("process_ns") for r in out["rounds"]) else set()
        phase_comparisons = {}
        for name in sorted(phases):
            phase_rounds = []
            for row in out["rounds"]:
                values = {a: row["cells"][a]["lifecycle"].get("phases", {}).get(name) for a in "ABC"}
                phase_rounds.append({"group": row["group"], "order": row["order"], "metric": values})
            phase_comparisons[name] = paired_summary(phase_rounds, "metric")
        out["phase_comparisons"] = phase_comparisons
        out["phase_accounting"] = "Phase medians are descriptive paired comparisons, never added together. Experiment I/O uses interval unions; archive is separate. OS exit times are never replaced by CLOSE receipt, reader return or archive completion."
        compare_runner_summary(result["business"], out["business"], "business")
        if out["process_lifetime"]["status"] == "measured":
            compare_runner_summary(result["process_lifetime"], out["process_lifetime"], "process_lifetime")
        compare_runner_summary(result["client_full_descriptive"], out["workflow"], "workflow")
        out.update(status="pass", business_status=out["business"]["status"], lifecycle_status=out["process_lifetime"]["status"],
                   actual_cells=18, actual_business_reads=54, process_generations=len(generations),
                   complete_window_ns=result["complete_window_ns"],
                   interpretation="Performance gates are scientific outcomes, separate from audit validity. No default replacement decision follows from this file alone.")
        need(all(a[1] <= b[0] for a, b in zip(group_clock_intervals, group_clock_intervals[1:])), "serial_GUI_groups")
        need(result["complete_window_ns"] >= group_clock_intervals[-1][1]-group_clock_intervals[0][0], "complete_window_lower_bound")
        out["complete_window_provenance"] = {"recorded_duration_ns": result["complete_window_ns"],
            "independently_recomputed_first_GUI_start_to_last_GUI_end_ns": group_clock_intervals[-1][1]-group_clock_intervals[0][0],
            "limit": "The raw top-level receipt has a duration but no absolute start/end stamps; only its lower bound can be checked independently."}
        out["closeout"] = closeout_summary(out["rounds"])
    except (ValueError, KeyError, TypeError, OSError, AssertionError) as exc:
        out["status"] = "failed"
        out["errors"].append(type(exc).__name__+": "+str(exc))
    out["hashed_file_count"] = len(files.checked)
    return out


def self_test():
    """Small arithmetic/admission checks; no service, input mesh or timer used."""
    checks = []
    def test(name, value):
        need(value, "self_test_"+name)
        checks.append(name)
    test("nested_union", union_length([(0, 100), (20, 30), (90, 120), (150, 160)]) == 130)
    test("clipped_union", clipped_union([(0, 100), (20, 30), (90, 120)], 25, 105) == 80)
    rounds = [{"group": i, "order": order, "x": {"A": 100, "B": 90, "C": 85}} for i, order in enumerate(ORDERS, 1)]
    s = paired_summary(rounds, "x", gate="business")
    test("business_gate", s["gate"] is True and s["pairs"]["C_vs_A"]["faster_rounds"] == 6)
    test("missing_round_not_filtered", paired_summary(rounds[:-1], "x", gate="business")["gate"] is None)
    bad = deepcopy(rounds)
    bad[2].pop("x")
    test("unmeasured_not_five_of_six", paired_summary(bad, "x", gate="lifetime")["gate"] is None)
    equality = deepcopy(rounds)
    for row in equality:
        row["x"] = {"A": 100, "B": 100, "C": 100}
    test("lifetime_net_gain_strict", paired_summary(equality, "x", gate="lifetime")["gate"] is False)
    boundary = deepcopy(rounds)
    for row in boundary:
        row["x"] = {"A": 1000, "B": 800, "C": 840}
    test("relative_five_percent_inclusive", paired_summary(boundary, "x", gate="business")["gate"] is True)
    for row in boundary:
        row["x"]["C"] = 841
    test("relative_over_five_percent", paired_summary(boundary, "x", gate="business")["gate"] is False)
    reversals = deepcopy(rounds)
    reversals[0]["x"]["C"] = 110
    test("reversal_retained", paired_summary(reversals, "x", gate="business")["pairs"]["C_vs_A"]["slower_rounds"] == 1)
    shuffled = deepcopy(rounds)
    shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
    test("order_not_substituted", paired_summary(shuffled, "x", gate="business")["gate"] is None)
    failed = validate_lifecycle({"lifecycle": {"valid": False, "errors": ["missing exit"], "os_survival_ns": 1}}, HERE)
    test("invalid_exit_never_duration", failed["status"] == "unmeasured" and "os_survival_ns" not in failed)
    names = [n for n in MAIN_ORDER if n not in ("before_first_observe", "last_business_decode")]
    fake_events = [{"name": name, "at_ns": (i+1)*1000} for i, name in enumerate(names)]
    for e in fake_events:
        e.update(filetime_100ns=10**12+e["at_ns"]//100, filetime_observation_after_ns=e["at_ns"]+10)
    by = {e["name"]: e for e in fake_events}
    fake_events.append({"name": "reader_receive_return", "at_ns": by["reader_join_begin"]["at_ns"]+100,
                        "filetime_100ns": 10**12+(by["reader_join_begin"]["at_ns"]+100)//100,
                        "filetime_observation_after_ns": by["reader_join_begin"]["at_ns"]+110})
    mapped, _ = event_map({"events": fake_events}, business=False)
    test("reader_can_return_during_join", mapped["reader_receive_return"]["at_ns"] < mapped["reader_join_end"]["at_ns"])
    for label, modified in (("duplicate_event_rejected", fake_events+[fake_events[0]]),
                            ("clock_discontinuity_rejected", deepcopy(fake_events))):
        if label.startswith("clock"):
            modified[-1]["filetime_100ns"] += 10**7
        try:
            event_map({"events": modified}, business=False)
        except ValueError:
            test(label, True)
        else:
            test(label, False)
    return {"status": "pass", "checks": checks, "count": len(checks), "product_calls": 0, "timed_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    value = self_test() if args.self_test else audit(args.result or RAW / "g60/main_001/RESULTS.json")
    if args.output is not None:
        target = args.output.resolve()
        need(target.is_relative_to(RAW.resolve()) or target.is_relative_to(HERE.resolve()), "output_scope")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        print(json.dumps(pin(target)))
    else:
        print(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))
    return int(value["status"] != "pass")


if __name__ == "__main__":
    raise SystemExit(main())
