"""M6-042 fixed Yanyite GUI/stdio pairs. Existing 036/041 transport and support."""
from __future__ import annotations

import argparse
from pathlib import Path
import statistics
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = Path("D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION")
LIVE = ROOT / "live"
OLD = ROOT.parent / "M6-041-KERNEL-HOOK"
CYCLE = ROOT.name
PLAN = LIVE / "PLAN.json"
ORDERS = (
    ("AB", "BA", "AB", "BA"),
    ("BA", "AB", "BA", "AB"),
    ("BA", "AB", "AB", "BA"),
)
ARMS = {"A": "032", "B": "r3"}
SOURCES = {
    "032": "a72aefd84549c05ec37ee09490354416e06f6451c14e8115f395efb80cf0a62d",
    "r3": "ebd8068712ae70af74d4cfacc6fd8e05f5056e6047334c91c6487f1cd18dff0e",
}
ASSET_SHA = "614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d"
NOW = time.perf_counter_ns


def load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


s1 = load("_m6_042_s1", OLD / "s1/s1.py")
read, dump, pin, need = s1.read, s1.dump, s1.pin, s1.need


def services():
    gui, svc = s1.api()
    gui.PRIVATE = LIVE
    gui.CYCLE = CYCLE
    gui.ASSET_SHAS = {ASSET_SHA: "Yanyite"}
    svc.CYCLE = CYCLE
    return gui, svc


def freeze():
    LIVE.mkdir(parents=True, exist_ok=False)
    gui, svc = services()
    arms = s1.source_plan()
    need({a: v["source_sha256"] for a, v in arms.items()} == SOURCES, "fixed 041 installed identities")
    historic_path = OLD / "s1/warm_diagnostic/PLAN.json"
    historic = read(historic_path)
    data = svc.fixture("Yanyite")
    high = data["oracle"]["regions"]["high"]
    request = historic["requests"]["Yanyite"]["first_high"]
    need(request == historic["requests"]["Yanyite"]["warm_high"] == data["sequence"][0][1], "fixed high request")
    need(data["asset"] == historic["asset_pins"]["Yanyite"] and data["asset"]["sha256"] == ASSET_SHA, "fixed asset SHA")
    need(high["triangle_count"] == 262 and min(high["source_witness_triangle_ids"]) == 49114
         and min(high["cube_witness_triangle_ids"]) == 0, "fixed source rows")
    sources = [Path(__file__), OLD / "s1/s1.py", *map(Path, read(s1.PLAN)["sources"])]
    plan = {
        "cycle_id": CYCLE, "contract": "c7c00d98289fad46e71a4278db7b7a4ea5858d5d",
        "prior_041_plan": pin(historic_path), "prior_041_warm_result": pin(OLD / "s1/warm_diagnostic/RESULTS.json"),
        "asset": data["asset"], "source_geometry": data["terminal"],
        "frame": data["frame"], "subframe": data["subframe"], "scale": data["scale"],
        "expected_source": data["expected"], "support": gui.prepare(), "arms": arms,
        "request": request, "expected_geometry": high, "direction_a_to_b": [0.0, 0.0, 1.0],
        "orders": ORDERS, "sources": [pin(p) for p in sorted(set(sources))],
        "deadline_s": 30, "primary": "start of write through decoded business body, uninstrumented installed stdio",
        "denominator": "three distinct serial ordinary GUIs; four paired blocks each; two fresh services and one first/warm identical high pair per block",
        "gates": {"median_absolute_ms_strictly_above": 5, "median_relative_strictly_above": .05, "minimum_positive_host_medians": 2},
        "extra_capture": "after all timed H3 requests, one same ordinary capture for separate offline attribution",
    }
    dump(PLAN, plan)
    print(pin(PLAN), flush=True)


def cell(folder, host, before, arm, plan, data, svc):
    folder.mkdir()
    report = {"arm": arm, "host_pid": host.pid, "rows": [], "errors": [], "start_ns": NOW()}
    client = None
    try:
        client = svc.Client(folder / "client", host, "Yanyite", plan["arms"][arm])
        client.open("Yanyite")
        report["ready_ns"] = NOW()
        report["product_pid"] = client.server_pid
        for step in ("first_high", "warm_high"):
            usage = svc.transport.counters(client.server_pid)
            answer = client.observe(plan["request"])
            end = NOW()
            answer.update(step=step, end_ns=end, business_ns=end-answer["timing"]["started_ns"],
                          counters_before=usage, counters_after=svc.transport.counters(client.server_pid))
            report["rows"].append(answer)
            dump(folder / (step + ".json"), answer)
            svc.verify_answers("Yanyite", data, [answer], before, client.source)
        need(svc.binary(report["rows"][0]["result"]) == svc.binary(report["rows"][1]["result"]), "first/warm public fields")
    except Exception:
        report["errors"].append(traceback.format_exc())
    finally:
        if client is not None:
            try:
                status = client.close()
                report["close"] = read(folder / "client/CLOSE.json")
                need(status == 0 and report["close"]["method"] == "eof" and not client.reader.is_alive(), "ordinary child EOF close")
            except Exception:
                report["errors"].append(traceback.format_exc())
    if client is not None:
        try:
            svc.associate(client, "Yanyite", report["rows"])
        except Exception:
            report["errors"].append(traceback.format_exc())
    report.update(end_ns=NOW(), valid=not report["errors"] and len(report["rows"]) == 2)
    dump(folder / "CELL.json", report)
    print(folder.name, report["valid"], flush=True)
    return report


def summarise(by_host, svc):
    med = statistics.median
    pairs = []
    for number, orders in enumerate(ORDERS, 1):
        host = by_host[number-1]
        for group, order in enumerate(orders, 1):
            arms = host["cells"].get(group, {})
            row = {"host": number, "host_pid": host.get("pid"), "group": group, "order": order}
            if host["valid"] and all(arms.get(arm, {}).get("valid") for arm in ARMS.values()):
                a, b = (arms[arm]["rows"] for arm in ARMS.values())
                for stage in (0, 1):
                    need(svc.binary(a[stage]["result"]) ==
                         svc.binary(b[stage]["result"]), "same-host across-arm business result")
                t_a, t_b = a[1]["business_ns"], b[1]["business_ns"]
                row.update(valid=True, a_first_ms=a[0]["business_ns"]/1e6, b_first_ms=b[0]["business_ns"]/1e6,
                           a_ms=t_a/1e6, b_ms=t_b/1e6, delta_ms=(t_b-t_a)/1e6, relative=t_b/t_a-1)
            else:
                row["valid"] = False
            pairs.append(row)
    rows = [r for r in pairs if r["valid"]]
    full = len(rows) == 12 and len({h["pid"] for h in by_host if h["valid"]}) == 3
    summary = {"pairs": pairs, "valid_pairs": len(rows), "expected_pairs": 12,
               "hosts": [{k:v for k,v in h.items() if k != "cells"} for h in by_host],
               "primary": "second exact high request, complete ordinary installed stdio reply",
               "plan": pin(PLAN), "complete_three_host_denominator": full}
    cells = [c for h in by_host for group in h["cells"].values() for c in group.values()]
    summary.update(cells_attempted=len(cells), cells_valid=sum(c["valid"] for c in cells),
                   first_reads=sum(len(c["rows"])>=1 for c in cells), warm_reads=sum(len(c["rows"])==2 for c in cells))
    if full:
        d = med(r["delta_ms"] for r in rows)
        f = med(r["relative"] for r in rows)
        h = [dict(host=i, delta_ms=med(r["delta_ms"] for r in rows if r["host"]==i),
                  relative=med(r["relative"] for r in rows if r["host"]==i)) for i in (1,2,3)]
        regression = d > 5 and f > .05
        summary.update(median_delta_ms=d, median_relative=f, by_host=h,
                       material_regression=regression, stable_regression=regression and sum(r["delta_ms"] > 0 for r in h) >= 2)
    return summary


def run(window):
    plan = read(PLAN)
    need(window["cycle_id"] == CYCLE and window["status"] == "available" and window["token"], "042 exclusive relevant workload window")
    need(all(pin(ref["path"]) == ref for ref in plan["sources"]), "frozen driver/support")
    need(s1.source_plan() == plan["arms"], "frozen installed products")
    gui, svc = services()
    data = svc.fixture("Yanyite")
    path = LIVE / "main"
    path.mkdir()
    hosts = []
    for idx, orders in enumerate(ORDERS, 1):
        folder = path / ("H" + str(idx))
        folder.mkdir()
        owner = None
        receipt = {"host": idx, "start_ns": NOW(), "cells": {}, "errors": []}
        try:
            owner = gui.Owned(folder / "native", data["asset"], plan["support"], window)
            receipt["pid"] = owner.pid
            before, receipt["before_snapshot_ns"] = svc.snapshot(owner, data, folder, "BEFORE")
            for count, order in enumerate(orders, 1):
                receipt["cells"][count] = {}
                for letter in order:
                    arm = ARMS[letter]
                    result = cell(folder / (f"H{idx}-P{count}-{arm}"), owner, before, arm, plan, data, svc)
                    receipt["cells"][count][arm] = result
                    need(result.get("close", {}).get("method") == "eof", "confirmed product exit before next arm")
            after, receipt["after_snapshot_ns"] = svc.snapshot(owner, data, folder, "AFTER")
            for key in ("frame", "subframe", "scale", "geometry"):
                need(svc.binary(before[key]) == svc.binary(after[key]), "unchanged geometry and frame")
            receipt["geometry_preserved"] = True
            if idx == 3:
                try:
                    helper = load("_m6_042_same_capture", HERE / "replay/capture.py")
                    high = plan["request"]["arguments"]["query"]
                    receipt["separate_capture"] = helper.capture_current(
                        owner.host, owner.port, ROOT / "replay/capture_01",
                        expected_target=high["region"]["object"]["name"],
                        expected_reference=high["reference"]["name"], box=high["region"]["world_box_m"])
                except Exception:
                    receipt["separate_capture_error"] = traceback.format_exc()
        except Exception:
            receipt["errors"].append(traceback.format_exc())
        finally:
            if owner is not None:
                try:
                    receipt["close"] = owner.close()
                except Exception:
                    receipt["errors"].append(traceback.format_exc())
        receipt.update(end_ns=NOW(), valid=not receipt["errors"] and bool(receipt.get("geometry_preserved")))
        dump(folder / "HOST.json", {k:v for k,v in receipt.items() if k != "cells"})
        hosts.append(receipt)
    summary = summarise(hosts, svc)
    dump(path / "RESULTS.json", summary)
    print({k:v for k,v in summary.items() if k not in ("pairs", "hosts")}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "run"])
    parser.add_argument("--window", type=Path)
    args = parser.parse_args()
    freeze() if args.action == "freeze" else run(read(args.window))
