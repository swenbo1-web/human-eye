"""Read-only recomputation of 043 ordinary G60 wire, sources and clock gates."""
from __future__ import annotations

import argparse
from pathlib import Path
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (ORDERS, STEPS, api, audit_rows, binary, check, need, pin, read)


def audit(result_path):
    result_path = Path(result_path)
    result = read(result_path)
    plan_path = check(result["plan"])
    plan = read(plan_path)
    for ref in (*plan["sources"].values(), *plan["support"].values(), *plan["truth"].values(),
                *plan["release_bindings"].values(), plan["asset"], plan["candidate"], plan["snapshot_fixture"],
                plan["engineering_recovery"]):
        check(ref)
    expected_orders = ("ABC",) if result["phase"].startswith("preflight_") else ORDERS
    need(result["expected_groups"] == len(expected_orders), "audit_denominator")
    s1, _, _ = api()
    triples, pids, products, calls = [], [], [], 0
    for ref, order in zip(result["group_receipts"], expected_orders):
        group_path = check(ref)
        folder = group_path.parent
        group = read(group_path)
        need(group["valid"] and not group["errors"] and group["order"] == order, "audit_complete_group")
        before, after = read(folder / "BEFORE.json"), read(folder / "AFTER.json")
        need(binary({k:v for k,v in before.items() if k != "resident"}) ==
             binary({k:v for k,v in after.items() if k != "resident"}), "audit_scene_custody")
        need(before["pid"] == group["host_pid"] and not before["background"] and before["main_thread"], "audit_normal_GUI")
        need(before["frame"] == plan["frame"] and before["subframe"] == plan["subframe"] and before["scale"] == plan["scale"],
             "audit_frame_units")
        for name, expected in plan["expected_snapshot"].items():
            need(all(binary(before["geometry"][name][key]) == binary(value) for key, value in expected.items()),
                 "audit_native_geometry_" + name)
        ownership = read(folder / "native/OWNERSHIP.json")
        spawn = read(folder / "native/SPAWN.json")
        need(ownership["normal_addon_unmodified"] and ownership["normal_queue_roundtrip_verified"] and
             ownership["ready"]["background"] is False and ownership["ready"]["pid"] == group["host_pid"],
             "audit_actual_addon_queue")
        need("--background" not in spawn["command"] and "-b" not in spawn["command"] and
             spawn["GUI_mode_no_background_flag"], "audit_GUI_launch_flags")
        need(spawn["source_refs"] == plan["support"] and spawn["input"] == plan["asset"], "audit_source_launch")
        close = group["gui_close"]
        need(close["status"] == "pass" and close["process_reaped"] and close["exit_code"] == 0 and
             close["forced"] is None and not close["released_port"]["owned_listener"] and close["source_unchanged"] and
             close["owned_copy_unchanged"] and close["original_addon_unchanged"], "audit_normal_shutdown")
        pids.append(group["host_pid"])
        semantic, times = {}, {}
        for arm in "ABC":
            cell_folder = folder / arm
            cell = read(cell_folder / "CELL.json")
            need(cell["valid"] and not cell["errors"] and cell["host_pid"] == group["host_pid"], "audit_valid_cell")
            need([row["step"] for row in cell["rows"]] == list(STEPS), "audit_sequence")
            semantic[arm] = audit_rows(cell_folder, cell, plan, before)
            need(semantic[arm] == cell["semantic"] == group["cells"][arm]["semantic"], "audit_semantic_receipt")
            products.append(cell["product_pid"])
            first = cell["rows"][0]["timing"]["started_ns"]
            final = cell["rows"][-1]["body_decoded_ns"]
            need(cell["business_ns"] == final-first > 0 and
                 cell["workflow_ns"] == cell["workflow_end_ns"]-cell["workflow_start_ns"] and
                 cell["workflow_start_ns"] <= first < final <= cell["workflow_end_ns"], "audit_primary_clock")
            for row in cell["rows"]:
                need(row["body_decoded_ns"] >= row["timing"]["closed_ns"], "audit_business_decode_after_wire")
                check(row["request"])
                check(row["response"])
            times[arm] = cell["business_ns"] / 1e6
            calls += len(cell["rows"])
        need(semantic["A"] == semantic["B"] == semantic["C"], "audit_same_host_complete_public")
        triples.append(dict(group=group["group"], order=order, business_ms=times,
                            saving_C_vs_A=1-times["C"]/times["A"], relative_C_vs_B=times["C"]/times["B"]-1))
    need(len(triples) == len(expected_orders) == result["valid_groups"] and result["status"] == "pass", "audit_no_missing_groups")
    need(len(set(pids)) == len(pids) and len(set(products)) == len(products), "audit_independent_GUI_products")
    need(result["actual_cells"] == 3*len(triples) and result["actual_business_reads"] == calls == 9*len(triples),
         "audit_actual_denominator")
    out = dict(status="pass", result=pin(result_path), groups=len(triples), gui_pids=pids,
               product_pids=products, business_reads=calls, primary_clock="first overview write to scan complete decode")
    if len(triples) == 6:
        saving, relative = median(x["saving_C_vs_A"] for x in triples), median(x["relative_C_vs_B"] for x in triples)
        faster = sum(x["business_ms"]["C"] < x["business_ms"]["A"] for x in triples)
        gate = saving >= .10 and faster >= 5 and relative <= .05
        need((saving, relative, faster, gate) == (result["median_saving_C_vs_A"], result["median_relative_C_vs_B"],
             result["C_faster_than_A"], result["performance_gate"]), "audit_recomputed_gate")
        out.update(median_saving_C_vs_A=saving, median_relative_C_vs_B=relative,
                   C_faster_than_A=faster, performance_gate=gate)
    return out


if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.result), indent=2))
