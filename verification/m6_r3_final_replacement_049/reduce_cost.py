"""Reduce preserved complete ordinary cells to engine usage and resource scopes."""
from collections import Counter
from statistics import median
from pathlib import Path
import sys
import json

RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT")


def read(path):
    return json.loads(path.read_bytes())


def summarize(paths):
    cells = []
    for path in paths:
        cell = read(path)
        assert cell["valid"] and cell["lifecycle"]["valid"], path
        processes = cell["lifecycle"]["processes"]
        assert all(p["exit_code"] == 0 and p["owned_held_handle"] for p in processes.values())
        route_by_step = {}
        for item in cell["rows"]:
            work = item["observe"].get("task_work", {})
            pair_work = work.get("pairs", {})
            routes = Counter()
            assert isinstance(pair_work,dict)
            for pair in pair_work.values():
                if not (exact := pair.get("surface_work")):
                    continue
                instrumented = exact.get("solver_path")
                route = instrumented or ("032" if cell["arm"]=="A" else "original_r3")
                if cell["arm"]=="F":
                    assert instrumented in ("032","r3")
                assert pair.get("surface_pair_cache_hit") is False
                routes[route] += 1
            route_by_step[item["step"]] = dict(routes)
        metrics = {
            "business_ns":cell["business_ns"],"startup_to_first_write_ns":cell["startup_discovery_ns"],
            "product_os_survival_ns":cell["lifecycle"]["os_survival_ns"],
            "client_with_eof_threads_and_archive_ns":cell["workflow_ns"],
            "client_after_last_business_ns":cell["product_close_and_final_counter_ns"],
            "product_business_cpu_s":cell["product_after"]["cpu_s"]-cell["product_before"]["cpu_s"],
            "product_peak_working_set_bytes_as_of_business_end":cell["product_after"]["peak_working_set_bytes"],
        }
        cells.append({"arm":cell["arm"],"group":path.parent.parent.name,"cell":str(path),
                      "metrics":metrics,"actual_solver_routes":route_by_step})
    summaries = {}
    for arm in sorted({row["arm"] for row in cells}):
        group = [row for row in cells if row["arm"]==arm]
        assert len(group)==6
        actual_routes = Counter()
        for c in group:
            for step in c["actual_solver_routes"].values():
                actual_routes.update(step)
        summaries[arm] = {
            "median":{k:median(c["metrics"][k] for c in group) for k in group[0]["metrics"]},
            "actual_solver_routes":dict(actual_routes),
        }
    return {"by_arm":summaries,"cells":cells}


def main():
    base = RAW/"g60_b02"
    g60 = sorted((base/"G60/main_001").glob("G01-*/*/CELL.json"))
    g60 += sorted((base/"G60/resume_001").glob("G0[2-6]-*/*/CELL.json"))
    b02 = sorted((base/"B02/main_001").glob("G0[1-6]-*/*/CELL.json"))
    assert len(g60)==18 and len(b02)==12
    result = {"G60":summarize(g60),"B02":summarize(b02),"scope":
              "Business CPU is post-initialize to last decoded reply for product service only. "
              "Working set is the product process's lifetime peak sampled at business end. "
              "Operating-system survival is creation to actual wrapper/service exit; not a CLOSE receipt interval. "
              "Client spans separately include parent IO, EOF, reader join and wire archival."}
    with (RAW/"REDUCED_COST.json").open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result,f,indent=2)
        f.write("\n")
    print({k:v["by_arm"] for k,v in result.items() if k!="scope"})


if __name__ == "__main__":
    main()

