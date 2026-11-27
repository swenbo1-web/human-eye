"""Post-run small-JSON cost and clock summary; never starts a host or service."""
from __future__ import annotations

from pathlib import Path
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HERE, RAW, STEPS, check, dump, need, pin, read


def cpu_delta(before, after):
    return after["cpu_s"]-before["cpu_s"] if "cpu_s" in before and "cpu_s" in after else None


def main():
    phases, all_cells, all_groups, wire_total = {}, [], [], {"tx_bytes": 0, "rx_bytes": 0}
    for name in ("preflight_001", "preflight_002", "main_001"):
        result = read(RAW / name / "RESULTS.json")
        groups = [read(check(ref)) for ref in result["group_receipts"]]
        cells = [cell for group in groups for cell in group["cells"].values()]
        all_cells.extend(cells)
        all_groups.extend(groups)
        phases[name] = dict(result=pin(RAW/name/"RESULTS.json"), status=result["status"],
            expected_groups=result["expected_groups"], valid_groups=result["valid_groups"],
            groups_started=len(groups), cells_started=len(cells), individually_valid_cells=sum(c["valid"] for c in cells),
            business_reads=sum(len(c["rows"]) for c in cells), wall_s=result["wall_ns"]/1e9,
            GUI_cleanup_pass=sum(g.get("gui_close", {}).get("status")=="pass" for g in groups),
            product_EOF_pass=sum(c.get("product_close", {}).get("method")=="eof" and
                                 c.get("product_close", {}).get("exit_code")==0 for c in cells))
        for group in groups:
            for arm in group["cells"]:
                folder = RAW/name/(f"G{group['group']:02d}-{group['order']}")/arm/"client"
                wire_total["tx_bytes"] += sum(f.stat().st_size for f in folder.glob("*.TX.bin"))
                wire_total["rx_bytes"] += sum(f.stat().st_size for f in folder.glob("*.RX.bin"))
    main_result = read(RAW/"main_001/RESULTS.json")
    main_audit = read(RAW/"main_001/AUDIT.json")
    need(main_result["status"] == main_audit["status"] == "pass" and main_result["performance_gate"], "completed_gate")
    formal_groups = [read(check(ref)) for ref in main_result["group_receipts"]]
    observations = []
    for group in all_groups:
        for arm, cell in group["cells"].items():
            observations.append(dict(arm=arm, host_pid=group["host_pid"], product_pid=cell["product_pid"],
                wrapper_pid=cell["wrapper_pid"], product_CPU_read_window_s=cpu_delta(cell["product_before"],cell["product_after"]),
                product_peak_working_set_bytes=cell["product_after"].get("peak_working_set_bytes"),
                product_working_set_at_last_business_boundary_bytes=cell["product_after"].get("current_working_set_bytes"),
                resource_snapshots_inside_workflow_ns=cell["resource_before_ns"]+cell["resource_after_ns"]))
    by_arm = {}
    for arm in "ABC":
        cells = [g["cells"][arm] for g in formal_groups]
        by_arm[arm] = dict(median_primary_business_ms=median(c["business_ns"]/1e6 for c in cells),
            median_product_through_EOF_ms=median(c["workflow_ns"]/1e6 for c in cells),
            median_step_stdio_full_decode_ms={step:median(next(r for r in c["rows"] if r["step"]==step)["timing"]["client_full_ns"]/1e6
                                                         for c in cells) for step in STEPS},
            product_CPU_read_window_s=sum(cpu_delta(c["product_before"],c["product_after"]) for c in cells),
            max_observed_product_lifetime_peak_bytes=max(c["product_after"]["peak_working_set_bytes"] for c in cells))
    closeout = read(RAW/"POST_PROCESS_CHECK.json")
    need(closeout["all_expected_pids_absent"] and closeout["all_owned_processes_absent"], "actual_owned_pids_absent")
    out = dict(schema="m6-043-live-g60-closeout-v1", status="pass", phases=phases,
        formal_result=pin(RAW/"main_001/RESULTS.json"), formal_audit=pin(RAW/"main_001/AUDIT.json"),
        final_plan=pin(RAW/"PLAN_03.json"), recovery=pin(RAW/"recovery_01/RECOVERY.json"),
        preflight_audit=pin(RAW/"preflight_002/AUDIT.json"), window=pin(RAW/"WINDOW.json"),
        PID_absence=pin(RAW/"POST_PROCESS_CHECK.json"), analytical_source=pin(Path(__file__)),
        total=dict(ordinary_GUI_launches=len(all_groups), product_service_launches=len(all_cells),
                   actual_business_reads=sum(len(c["rows"]) for c in all_cells),
                   GUI_cleanup_pass=sum(g["gui_close"]["status"]=="pass" for g in all_groups),
                   product_EOF_pass=sum(c["product_close"]["method"]=="eof" and c["product_close"]["exit_code"]==0 for c in all_cells),
                   distinct_observed_GUI_PIDs=len({g["host_pid"] for g in all_groups}),
                   distinct_observed_actual_product_PIDs=len({c["product_pid"] for c in all_cells}),
                   distinct_observed_wrapper_PIDs=len({c["wrapper_pid"] for c in all_cells}),
                   distinct_all_owned_PIDs=len(closeout["expected_owned_pids"]),
                   measured_phase_wall_s=sum(p["wall_s"] for p in phases.values()),
                   actual_product_CPU_read_windows_s=sum(o["product_CPU_read_window_s"] for o in observations),
                   GUI_CPU_group_business_envelopes_s=sum(cpu_delta(g["host_before_business"],g.get("host_after_business",g["host_before_business"]))
                                                        for g in all_groups),
                   model_turns=0, wire_including_initialize_discovery_and_business=wire_total),
        formal_by_arm=by_arm, formal_pairs=main_result["groups"], resources=observations,
        resource_limits="CPU covers the actual product after initialize through final business boundary, and GUI before/after each group's business envelope. It excludes product startup/EOF CPU. Working-set peaks are individual process-lifetime peaks, never summed into a simultaneous process-tree peak. No continuous sampler or total controller CPU was measured.",
        failure_scope="preflight_001 retained all nine successful business answers and all exits; its group failed only the original overview request_trace.request_id comparison. Final source binds that ID to the real audit before normalization. No formal sample was retried.",
        primary_clock=main_result["timing_scope"], performance_gate=main_result["performance_gate"],
        median_saving_C_vs_A=main_result["median_saving_C_vs_A"], C_faster_than_A=main_result["C_faster_than_A"],
        median_relative_C_vs_B=main_result["median_relative_C_vs_B"])
    print(dump(RAW/"CLOSEOUT.json",out))
    # Small repository-facing receipt points to the complete raw evidence.
    summary = {key:out[key] for key in ("schema","status","formal_result","formal_audit","final_plan","PID_absence",
              "total","formal_by_arm","performance_gate","median_saving_C_vs_A","C_faster_than_A","median_relative_C_vs_B")}
    summary["raw_closeout"] = pin(RAW/"CLOSEOUT.json")
    target = HERE/"RESULTS.json"
    import json
    with target.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(summary,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write("\n")
    print(pin(target))


if __name__ == "__main__":
    main()
