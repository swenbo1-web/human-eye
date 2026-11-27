"""Recompute 043 paired offline gate from process clocks and raw replay rows."""
from __future__ import annotations

from argparse import ArgumentParser
from fractions import Fraction
from itertools import permutations
from pathlib import Path
from statistics import median
import math

from common import check, dump, pin, read


def recompute(folder):
    result = read(folder / "RESULTS.json")
    plan = read(check(result["plan"]))
    assert plan["orders"] == ["".join(x) for x in permutations("ABC")] * 2
    assert len(result["groups"]) == 12 and result["cells_started"] == 36
    pairs = []
    pids = set()
    end = None
    for index, order in enumerate(plan["orders"], 1):
        assert result["groups"][index-1]["group"] == index
        full = {}
        for arm in order:
            slot = folder/f"{index:02d}_{arm}"
            summary = result["groups"][index-1]["cells"][arm]
            p = read(check(summary["process"]))
            assert check(p["cell"]) == (slot/"CELL.json").resolve()
            assert p["reaped"] and p["launcher_pid"] not in pids
            assert p["lifecycle_ns"] == p["closed_ns"]-p["start_ns"]
            assert end is None or end <= p["start_ns"]
            end=p["closed_ns"]
            pids.add(p["launcher_pid"])
            if not summary["valid"]:
                continue
            assert p["exit"] == 0
            cell = read(slot/"CELL.json")
            assert cell["status"]=="pass" and cell["group"]==index and cell["arm"]==arm
            assert cell["actual_identity"]["source_sha256"] == plan["release_bindings"][arm]["identity"]["source_sha256"]
            assert cell["host_calls"] == 0 and not cell["mechanism_observer"]
            assert cell["restored_capture_calls"] == 2
            for expected, row in zip(("first", "repeat"), cell["rows"], strict=True):
                assert row["step"] == expected
                actual=read(check(row["raw"]))
                assert actual["public"]==plan["expected_public"]
                clock=actual["full_ns"]
                assert clock == actual["finished_ns"]-actual["started_ns"] == row["full_ns"]
                assert clock == sum(actual[x] for x in ("service_ns","projection_ns","content_encode_ns","wire_encode_ns"))
                assert p["start_ns"] <= actual["started_ns"] < actual["finished_ns"] <= p["closed_ns"]
                if expected=="repeat":
                    full[arm]=clock
        if len(full)==3:
            a,b,c=(full[x] for x in "ABC")
            pairs.append({"group":index,"order":order,"repeat_ns":full,"save_B_ns":b-c,
                          "delta_A_ns":c-a,"ratio_delta_A":str(Fraction(c-a,a))})
    assert len(pairs)==result["valid_triplets"]
    summary={"status":"incomplete","valid_triplets":len(pairs),"distinct_child_pids":len(pids),
             "raw_result":pin(folder/"RESULTS.json"),"pairs":pairs}
    if len(pairs)==12:
        gain=median(Fraction(p["save_B_ns"]) for p in pairs)
        faster=sum(p["save_B_ns"]>0 for p in pairs)
        extra=median(Fraction(p["delta_A_ns"]) for p in pairs)
        relative=median(Fraction(p["ratio_delta_A"]) for p in pairs)
        g,n,d,f=result["paired_median_saving_C_vs_B_ms"],result["C_faster_than_B"],result["paired_median_delta_C_vs_A_ms"],result["paired_median_relative_C_vs_A"]
        assert math.isclose(g,float(gain)/1e6,abs_tol=1e-9)
        assert math.isclose(d,float(extra)/1e6,abs_tol=1e-9)
        assert math.isclose(f,float(relative),abs_tol=1e-12)
        assert faster==n
        yes=gain>=750000 and faster>=9 and extra<=750000 and relative<=Fraction(5,100)
        assert yes==(result["status"]=="pass")
        summary.update(status="pass" if yes else "fail_timing_gate",
            median_save_vs_B_exact_ns=str(gain),faster_vs_B=faster,
            median_extra_vs_A_exact_ns=str(extra),median_relative_vs_A_exact=str(relative))
    return summary


if __name__=="__main__":
    p=ArgumentParser(description=__doc__)
    p.add_argument("folder",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    print(dump(a.output,recompute(a.folder)))
