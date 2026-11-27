"""Frozen ordinary G60 overview -> nearest -> 5 mm scan, six ABC rotations."""
from __future__ import annotations

import argparse
from pathlib import Path
from statistics import median
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (HERE, RAW, ROOT, OLD, VER, CYCLE, PYTHON, CONTRACT, ORDERS, STEPS,
                    ASSET_SHA, api, arms, audit_rows, binary, check, dump, need, pin, read, requests)

NOW = time.perf_counter_ns
DEFAULT_PLAN = RAW / "PLAN_03.json"


def freeze(plan_path=DEFAULT_PLAN):
    RAW.mkdir(parents=True, exist_ok=True)
    s1, gui, service = api()
    prior = read(OLD / "s1/PLAN_recovery_01.json")
    installed = arms()
    asset = prior["assets"]["G60"]
    need(check(asset) and asset["sha256"] == ASSET_SHA, "asset_pin")
    support = prior["support"]
    for ref in support.values():
        check(ref)
    data = service.fixture("G60")
    need(data["asset"] == asset, "same_source_fixture")
    gate_path = ROOT / "timing/attempt_001/RESULTS.json"
    gate = read(gate_path)
    need(gate["status"] == "pass" and gate["valid_triplets"] == gate["expected_triplets"] == 12,
         "offline_gate_before_live")
    sources = {str(p): pin(p) for p in (HERE / "common.py", Path(__file__), HERE / "audit.py",
                OLD / "s1/s1.py", *map(Path, prior["sources"]),
                VER / "m6_post032_profile_036/inputs.py", VER / "m6_same_frame_scoped_batch_034/inputs.py")}
    truth = {key: pin(s1.INPUTS["G60_040_" + key]) for key in ("nearest", "scan")}
    baseline_pins = read(s1.PINS)
    bindings = {"A": baseline_pins["binding"]["032"], "B": baseline_pins["binding"]["r3"],
                "C": read(ROOT / "candidate/PINS.json")["binding"]}
    for ref in bindings.values():
        check(ref)
    plan = dict(schema="m6-043-live-g60-v1", status="frozen_not_launched", cycle_id=CYCLE,
        contract=CONTRACT, offline_gate=pin(gate_path), prior_041_plan=pin(OLD / "s1/PLAN_recovery_01.json"),
        candidate=pin(ROOT / "candidate/PINS.json"), arms=installed, release_bindings=bindings,
        asset=asset, support=support, sources=sources, truth=truth,
        snapshot_fixture=pin(s1.INPUTS["G60"]), expected_snapshot=data["expected"],
        frame=data["frame"], subframe=data["subframe"], scale=data["scale"], requests=requests(),
        orders=list(ORDERS), steps=list(STEPS), expected=dict(groups=6, independent_guis=6, cells=18, business_reads=54),
        preflight=dict(groups=1, order="ABC", independent_gui=True, business_reads=9,
                       timing_eligibility="correctness only; excluded from the six formal groups"),
        primary="contiguous first overview write through complete scan business decode, including all normal chain overhead and original transport boundary counters; no external QA/audit polling",
        workflow_envelope="normal installed product creation through initialize/discovery, business chain and confirmed EOF; not substituted for the primary business comparison",
        resources="Actual GUI and actual product-interpreter CPU/working-set boundary snapshots; wrapper PID separately retained. Product peak is process-lifetime peak at final business boundary. No sampled simultaneous process-tree peak is claimed.",
        budget="Original 30s per product request and original GUI-owner deadline; no renewal or additional model/Hook path",
        initial_condition="One fresh ordinary private GUI per triple group. Each arm has a new installed service/state/audit. Host naturally remains warm across that group's arms. OS caches are not reset.",
        comparison="Same-host exact public outputs after validating source/trace and normalizing only runtime identity and trace IDs; host revisions/instances retained. Historical 040 complete nearest and scan fields independently compared except their binding/trace.",
        gate=dict(minimum_median_saving_C_vs_A=.10, minimum_C_faster_than_A=5,
                  maximum_median_relative_C_vs_B=.05, expected_triplets=6),
        engineering_recovery=pin(RAW / "recovery_01/RECOVERY.json"),
        no_automatic_retry=True, no_new_candidate=True, model_turns=0)
    print(dump(plan_path, plan), flush=True)


def validate_plan(plan_path):
    plan = read(plan_path)
    need(plan["cycle_id"] == CYCLE and plan["contract"] == CONTRACT and plan["orders"] == list(ORDERS), "fixed_plan")
    for ref in (*plan["sources"].values(), *plan["support"].values(), *plan["truth"].values(),
                *plan["release_bindings"].values(), plan["asset"], plan["candidate"], plan["offline_gate"],
                plan["snapshot_fixture"], plan["prior_041_plan"], plan["engineering_recovery"]):
        check(ref)
    need(arms() == plan["arms"] and requests() == plan["requests"], "fixed_current_sources_and_requests")
    return plan


def snapshot(host, folder, label, plan):
    s1, _, service = api()
    mark = NOW()
    value = s1.loadsnap(host, label, folder)
    need(s1.check_input("G60", value, service), "actual_source_geometry")
    need(value["frame"] == plan["frame"] and value["subframe"] == plan["subframe"] and
         value["scale"] == plan["scale"], "current_frame_units")
    for name, expected in plan["expected_snapshot"].items():
        need(all(binary(value["geometry"][name][key]) == binary(want) for key, want in expected.items()),
             "actual_world_local_face_matrix:" + name)
    return value, NOW() - mark


def cell(folder, host, before, arm, plan):
    _, _, service = api()
    folder.mkdir()
    record = dict(arm=arm, host_pid=host.pid, host=host.host, port=host.port,
                  rows=[], errors=[], started_ns=NOW(), validation_outside_primary=True)
    client = None
    workflow_start = NOW()
    try:
        client = service.Client(folder / "client", host, "G60", plan["arms"][arm])
        client.open("G60")
        record.update(product_pid=client.server_pid, wrapper_pid=client.worker.pid, ready_ns=NOW())
        resource_start = NOW()
        record["product_before"] = service.transport.counters(client.server_pid)
        record["resource_before_ns"] = NOW() - resource_start
        for step in STEPS:
            row = client.observe(plan["requests"][step])
            row.update(step=step, body_decoded_ns=NOW())
            record["rows"].append(row)
        record["last_reply_ns"] = record["rows"][-1]["body_decoded_ns"]
        resource_start = NOW()
        record["product_after"] = service.transport.counters(client.server_pid)
        record["resource_after_ns"] = NOW() - resource_start
    except BaseException:
        record["errors"].append(dict(stage="business", traceback=traceback.format_exc()))
    finally:
        if client is not None:
            try:
                result = client.close()
                record["product_close"] = read(folder / "client/CLOSE.json")
                need(result == 0 and record["product_close"]["method"] == "eof" and not client.reader.is_alive(),
                     "confirmed_product_exit")
            except BaseException:
                record["errors"].append(dict(stage="product_close", traceback=traceback.format_exc()))
    end = NOW()
    record.update(workflow_start_ns=workflow_start, workflow_end_ns=end, workflow_ns=end-workflow_start)
    if len(record["rows"]) == 3:
        first_write = record["rows"][0]["timing"]["started_ns"]
        record.update(through_scan_reply_ns=record["last_reply_ns"]-workflow_start,
                      business_ns=record["last_reply_ns"]-first_write,
                      startup_discovery_ns=first_write-workflow_start,
                      product_close_and_final_counter_ns=end-record["last_reply_ns"])
    if not record["errors"]:
        try:
            record["semantic"] = audit_rows(folder, record, plan, before)
            for row in record["rows"]:
                dump(folder / (row["step"] + ".json"), row)
        except BaseException:
            record["errors"].append(dict(stage="after_eof_validation", traceback=traceback.format_exc()))
    record.update(ended_ns=NOW(), valid=not record["errors"] and len(record["rows"]) == 3)
    dump(folder / "CELL.json", record)
    print(folder.name, record["valid"], flush=True)
    return record


def group(folder, index, order, plan, window):
    _, gui, service = api()
    folder.mkdir()
    host = None
    receipt = dict(group=index, order=order, started_ns=NOW(), cells={}, errors=[])
    try:
        host = gui.Owned(folder / "native", plan["asset"], plan["support"], window)
        receipt.update(host_pid=host.pid, port=host.port, gui_ready_ns=NOW())
        before, receipt["before_snapshot_ns"] = snapshot(host, folder, "BEFORE", plan)
        receipt["host_before_business"] = service.transport.counters(host.pid)
        for arm in order:
            receipt["cells"][arm] = cell(folder / arm, host, before, arm, plan)
            need(receipt["cells"][arm]["valid"], "invalid_cell_" + arm)
        receipt["host_after_business"] = service.transport.counters(host.pid)
        values = [receipt["cells"][arm]["semantic"] for arm in "ABC"]
        need(values[0] == values[1] == values[2], "same_live_host_complete_public_outputs")
        receipt["three_arm_same_host_equal"] = True
        after, receipt["after_snapshot_ns"] = snapshot(host, folder, "AFTER", plan)
        # Resident cache counters can change; the complete scene remains fixed.
        need(binary({k:v for k,v in before.items() if k != "resident"}) ==
             binary({k:v for k,v in after.items() if k != "resident"}), "unchanged_live_scene")
        receipt["geometry_preserved"] = True
    except BaseException:
        receipt["errors"].append(traceback.format_exc())
    finally:
        if host is not None:
            try:
                receipt["gui_close"] = host.close()
                need(receipt["gui_close"]["status"] == "pass" and receipt["gui_close"]["process_reaped"] and
                     receipt["gui_close"]["forced"] is None, "normal_gui_cleanup")
            except BaseException:
                receipt["errors"].append("GUI close: " + traceback.format_exc())
    receipt.update(ended_ns=NOW(), valid=not receipt["errors"] and len(receipt["cells"]) == 3)
    receipt["full_native_and_QA_lifecycle_ns"] = receipt["ended_ns"] - receipt["started_ns"]
    dump(folder / "GROUP.json", receipt)
    return receipt


def summary(groups, plan_path, phase, started, expected):
    paired = []
    for g in groups:
        row = dict(group=g["group"], order=g["order"], valid=g["valid"])
        if g["valid"]:
            t = {arm:g["cells"][arm]["business_ns"] / 1e6 for arm in "ABC"}
            row.update(business_ms=t, saving_C_vs_A=1-t["C"]/t["A"], delta_C_vs_B_ms=t["C"]-t["B"],
                       relative_C_vs_B=t["C"]/t["B"]-1,
                       workflow_ms={a:g["cells"][a]["workflow_ns"]/1e6 for a in "ABC"},
                       step_ms={a:{r["step"]:r["timing"]["client_full_ns"]/1e6 for r in g["cells"][a]["rows"]} for a in "ABC"})
        paired.append(row)
    valid = [r for r in paired if r["valid"]]
    out = dict(schema="m6-043-live-g60-result-v1", status="pass" if len(valid)==expected else "incomplete_or_failed",
               phase=phase, plan=pin(plan_path), expected_groups=expected, valid_groups=len(valid), groups=paired,
               actual_cells=sum(len(g["cells"]) for g in groups),
               actual_business_reads=sum(len(c["rows"]) for g in groups for c in g["cells"].values()),
               wall_ns=NOW()-started, complete_source_and_cleanup_gate=len(valid)==expected,
               group_receipts=[pin(RAW / phase / (f"G{g['group']:02d}-{g['order']}") / "GROUP.json") for g in groups],
               timing_scope="primary first overview write through scan complete business decode; startup/EOF envelope and GUI/QA lifecycle separate; no Hook or model")
    if len(valid) == expected and expected == 6:
        savings = [r["saving_C_vs_A"] for r in valid]
        relative = [r["relative_C_vs_B"] for r in valid]
        quicker = sum(r["business_ms"]["C"] < r["business_ms"]["A"] for r in valid)
        out.update(median_saving_C_vs_A=median(savings), C_faster_than_A=quicker,
                   median_relative_C_vs_B=median(relative),
                   performance_gate=median(savings)>=.10 and quicker>=5 and median(relative)<=.05)
    return out


def run(plan_path, window_path, phase, preflight_path=None):
    need(Path(phase).name == phase and phase.startswith(("preflight_", "main_")) and
         all(c.isalnum() or c == "_" for c in phase), "fresh_phase_name")
    plan = validate_plan(plan_path)
    window = read(window_path)
    need(window["cycle_id"] == CYCLE and window["status"] == "available" and window.get("token"), "fresh_exclusive_window")
    if phase.startswith("main_"):
        need(preflight_path is not None, "independent_preflight_required")
        preflight = read(preflight_path)
        need(preflight["status"] == "pass" and preflight["phase"].startswith("preflight_") and
             preflight["valid_groups"] == 1 and preflight["plan"] == pin(plan_path), "passed_same_source_preflight")
    output = RAW / phase
    output.mkdir()
    dump(output / "WINDOW.json", window)
    started = NOW()
    groups = []
    orders = ("ABC",) if phase.startswith("preflight_") else ORDERS
    for index, order in enumerate(orders, 1):
        result = group(output / (f"G{index:02d}-{order}"), index, order, plan, window)
        groups.append(result)
        if not result["valid"]:
            break  # Retain the failed denominator; no replacement or candidate tuning.
    out = summary(groups, plan_path, phase, started, len(orders))
    print(dump(output / "RESULTS.json", out), flush=True)
    return int(out["status"] != "pass")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "preflight", "run"))
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--window", type=Path)
    parser.add_argument("--phase")
    parser.add_argument("--preflight", type=Path)
    args = parser.parse_args()
    if args.mode == "freeze":
        freeze(args.plan)
    else:
        need(args.window is not None, "window_argument")
        phase = args.phase or ("preflight_001" if args.mode == "preflight" else "main_001")
        need(phase.startswith("preflight_") if args.mode == "preflight" else phase.startswith("main_"), "phase_mode")
        raise SystemExit(run(args.plan, args.window, phase, args.preflight))
