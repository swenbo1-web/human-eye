"""Independently audit ordinary Yanyite timing, budgets and release receipts."""
from __future__ import annotations

import argparse
from fractions import Fraction
from itertools import permutations
from pathlib import Path
from statistics import median

from common import check, dump, pin, read


def confirm(folder):
    result = read(folder / "RESULTS.json")
    plan = read(check(result["plan"]))
    assert [order for cuts in plan["cuts"] for order in cuts] == ["".join(x) for x in permutations("ABC")] * 2
    by_host = {}
    all_rows = []
    limits = {"unavailable":[], "sampled_roles":["host","product","redirector"],
              "scope":"request-boundary CPU deltas and per-PID lifetime peak samples"}
    host_pids, product_pids = set(), set()
    last_host_end = result["started_ns"]
    for host in result["hosts"]:
        assert host["host"] not in by_host
        assert last_host_end <= host["start_ns"] <= host["ready_ns"] < host["end_ns"] <= result["finished_ns"]
        last_host_end = host["end_ns"]
        host_folder = check(host["raw"]).parent
        actual = read(host["raw"]["path"])
        assert actual == {k:v for k,v in host.items() if k!="raw"}
        pid = host["pid"]
        host_pids.add(pid)
        assert host["valid"] and host["geometry_preserved"] and host["close"]["process_reaped"]
        assert host["close"]["released_port"]["owned_listener"] is False and host["close"]["source_unchanged"]
        before, after = (read(host_folder/(phase+".json")) for phase in ("BEFORE","AFTER"))
        assert {k:v for k,v in before.items() if k!="resident"} == {k:v for k,v in after.items() if k!="resident"}
        host_rows = []
        last_cell_end = host["ready_ns"]
        for group in (g for g in result["groups"] if g["host"]==host["host"]):
            matched, clocks, info = {}, {}, {}
            for arm in group["order"]:
                ref = group["cells"][arm]
                file = check(ref["raw"])
                cell = read(file)
                assert ref["valid"] and cell["valid"] and (cell["arm"],cell["host_pid"]) == (arm,pid)
                assert last_cell_end <= cell["start_ns"] <= cell["ready_ns"] < cell["end_ns"] <= host["end_ns"]
                last_cell_end = cell["end_ns"]
                assert cell["released"]=={"launcher":True,"actual_product":True} and cell["close"]["method"]=="eof"
                actual_pid = cell["product_pid"]
                product_pids.add(actual_pid)
                startup=read(file.parent/"client/STARTUP.json")
                assert startup["actual_pid"]==actual_pid and startup["scoped_mode_advertised"]
                assert startup["startup_trace"]["identity_check"]["actual"]["source_sha256"]==plan["arms"][arm]["source_sha256"]
                assert cell["observed_native_capture_calls"]==2
                matched[arm] = []
                for expected, row in zip(("first_high","warm_high"),cell["rows"],strict=True):
                    assert row["step"]==expected and not row["tool_error"] and not row["rpc_error"]
                    trace=row["telemetry"]
                    assert trace["pid"]==actual_pid and trace["annotations"]["mcp_native_image_block_count"]==0
                    hosts=[s for s in trace["spans"] if s["name"]=="host.capture_source_region_pair"]
                    assert len(hosts)==1
                    check(row["request"])
                    check(row["response"])
                    assert row["business_ns"]==row["finished_ns"]-row["timing"]["started_ns"]
                    assert cell["ready_ns"]<=row["timing"]["started_ns"]<row["finished_ns"]<=cell["end_ns"]
                    matched[arm].append(row["result"])
                    usage = {}
                    for key, b in row["resources_before"].items():
                        a=row["resources_after"][key]
                        if "cpu_s" in a and "cpu_s" in b:
                            usage[key]={"cpu_delta_s":a["cpu_s"]-b["cpu_s"],"boundary_peak_bytes":a["peak_working_set_bytes"]}
                        else:
                            limits["unavailable"].append([host["host"],group["group"],arm,row["step"],key,b,a])
                    info.setdefault(arm,{})[row["step"]] = usage
                    clocks.setdefault(arm,{})[row["step"]]=row["business_ns"]
            assert matched["A"]==matched["B"]==matched["C"] and matched["A"][0]==matched["A"][1]
            a,b,c=(clocks[arm]["warm_high"] for arm in "ABC")
            row={"host":host["host"],"group":group["group"],"order":group["order"],"clocks_ns":clocks,"usage":info,
                 "delta_C_vs_A_ns":c-a,"relative_C_vs_A":str(Fraction(c-a,a)),
                 "delta_C_vs_B_ns":c-b,"relative_C_vs_B":str(Fraction(c-b,b))}
            host_rows.append(row)
            all_rows.append(row)
        by_host[host["host"]]=median(v["delta_C_vs_A_ns"] for v in host_rows)
    assert (len(all_rows),len(host_pids),len(product_pids))==(12,3,36)
    absolute = median(Fraction(row["delta_C_vs_A_ns"]) for row in all_rows)
    relative = median(Fraction(row["relative_C_vs_A"]) for row in all_rows)
    material = absolute>5_000_000 and relative>Fraction(5,100)
    stable = material and sum(x>0 for x in by_host.values())>=2
    assert (material,stable)==(result["material_regression"],result["stable_regression"])
    return {"status":"fail_warm_gate" if material else "pass","input":pin(folder/"RESULTS.json"),
            "material":material,"stable":stable,"median_C_minus_A_ns":str(absolute),"median_C_minus_A_relative":str(relative),
            "median_C_minus_B_ns":str(median(Fraction(row["delta_C_vs_B_ns"]) for row in all_rows)),
            "processed_ordinary_reads":72,"products_released":len(product_pids),"hosts_released":len(host_pids),
            "host_median_C_minus_A_ns":by_host,"coordinator_wall_ns":result["wall_ns"],
            "resource_evidence":limits,"groups":all_rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    print(dump(a.output,confirm(a.folder)))

