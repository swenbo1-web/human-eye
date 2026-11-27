"""049 offline lifecycle proof; extracted from the frozen 045 verifier."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

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
             archive["files"] == len(actual) == (5 + 2*len(record["rows"]) if business else 5) and
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
