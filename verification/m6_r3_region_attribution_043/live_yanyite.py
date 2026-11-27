"""Three owned ordinary Blender hosts, with four frozen Yanyite triplets each."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from itertools import permutations
from pathlib import Path
from statistics import median
import time
import traceback

from common import CYCLE, ROOT, check, dump, installation, pin, read

NOW = time.perf_counter_ns
HERE = Path(__file__).resolve().parent
STAGE = ROOT / "live/yanyite"
PLAN = STAGE / "PLAN.json"
OLD = ROOT.parent / "M6-041-KERNEL-HOOK"
OFFLINE = ROOT / "timing/attempt_001/RESULTS.json"
RECOMPUTE = ROOT / "timing/TIMING_RECOMPUTE.json"
ORDERS = ["".join(v) for v in permutations("ABC")] * 2


def old_driver():
    import importlib.util

    p = HERE.parent / "m6_entry_warm_region_042/live_yanyite.py"
    spec = importlib.util.spec_from_file_location("_m6_043_qualification", p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def environment():
    old = old_driver()
    gui, service = old.services()
    gui.PRIVATE = STAGE
    gui.CYCLE = CYCLE
    service.CYCLE = CYCLE
    return old, gui, service


def arms(old, offline):
    orig = old.s1.source_plan()
    candidate_pins = read(ROOT / "candidate/PINS.json")
    c = offline["release_bindings"]["C"]
    assert installation(check(c["binding"])) == c
    command_path = check(candidate_pins["launcher"])
    choices = {"A":orig["032"], "B":orig["r3"], "C":{
        "source_sha256":c["identity"]["source_sha256"],
        "version":c["identity"]["distribution_version"],
        "role":orig["r3"]["role"],
        "site_packages":c["site"],
        "command_prefix":[candidate_pins["dependency_python"],"-I","-B",str(command_path)],
    }}
    for arm in choices:
        bind = offline["release_bindings"][arm]
        assert choices[arm]["source_sha256"] == bind["identity"]["source_sha256"]
        assert choices[arm]["version"] == bind["identity"]["distribution_version"]
        assert choices[arm]["site_packages"] == bind["site"]
        assert installation(check(bind["binding"])) == bind
    return choices


def freeze():
    summary = read(RECOMPUTE)
    assert summary["status"] == "pass" and check(summary["raw_result"]) == OFFLINE.resolve()
    matrix = read(check(read(OFFLINE)["plan"]))
    assert matrix["orders"] == ORDERS
    old, gui, svc = environment()
    fixed = read(OLD / "s1/warm_diagnostic/PLAN.json")
    data = svc.fixture("Yanyite")
    request = fixed["requests"]["Yanyite"]["first_high"]
    assert request == fixed["requests"]["Yanyite"]["warm_high"] == data["sequence"][0][1]
    assert data["asset"] == fixed["asset_pins"]["Yanyite"]
    expected = data["oracle"]["regions"]["high"]
    assert expected["triangle_count"] == 262 and min(expected["source_witness_triangle_ids"]) == 49114
    plan = {
        "cycle_id": CYCLE, "contract": matrix["contract"], "offline": pin(RECOMPUTE),
        "prior": pin(OLD / "s1/warm_diagnostic/PLAN.json"), "candidate": pin(ROOT / "candidate/PINS.json"),
        "asset": data["asset"], "source_geometry": data["terminal"],
        "expected_source": data["expected"], "frame":data["frame"],"subframe":data["subframe"],"scale":data["scale"],
        "high_request": request, "high_expected": expected,
        "origins": [pin(p) for p in sorted({Path(__file__), HERE/"common.py", Path(old.__file__),
                    OLD/"s1/s1.py", *map(Path, read(old.s1.PLAN)["sources"])})],
        "cuts": [ORDERS[0:4], ORDERS[4:8], ORDERS[8:12]],
        "arms": arms(old,matrix), "processors":"same installed CLI and ordinary native add-on on each fresh host",
        "scope": "three independent serial GUI owners; each of 36 children handles exactly two identical no-image high-box requests",
        "measurement": "first and second original stdio write through fully decoded business body; all verification and OS probes outside clock",
        "resource_scope": "native GUI and actual MCP interpreter PID readings at boundaries; redirector reported separately, no aggregate peak inferred",
        "gates": {"C_minus_A_median_absolute_ms_strictly_above":5,
                  "C_minus_A_median_relative_strictly_above":.05, "stable_minimum_positive_hosts":2},
    }
    STAGE.mkdir(parents=True, exist_ok=False)
    plan["support"] = gui.prepare()
    print(dump(PLAN, plan), flush=True)


def active(pid):
    win = ctypes.WinDLL("kernel32", use_last_error=True)
    win.OpenProcess.argtypes = wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
    win.OpenProcess.restype = wintypes.HANDLE
    win.GetExitCodeProcess.argtypes = wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)
    win.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = win.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:
            return False
        raise OSError(error, "Could not verify owned PID exit")
    try:
        status = wintypes.DWORD()
        if not win.GetExitCodeProcess(handle, ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        return status.value == 259
    finally:
        win.CloseHandle(handle)


def counter_scope(svc, pids):
    return {k:{"pid":pid, **svc.transport.counters(pid)} for k,pid in pids.items()}


def cell(folder, owner, before, letter, plan, data, svc):
    folder.mkdir()
    result = {"arm":letter, "host_pid":owner.pid, "rows":[], "errors":[], "start_ns":NOW()}
    client = None
    try:
        client = svc.Client(folder/"client", owner, "Yanyite", plan["arms"][letter])
        result["launcher_pid"] = client.worker.pid
        client.open("Yanyite")
        result.update(ready_ns=NOW(), product_pid=client.server_pid)
        pids = {"host":owner.pid,"product":client.server_pid}
        if client.worker.pid != client.server_pid:
            pids["redirector"] = client.worker.pid
        for step in ("first_high","warm_high"):
            resource_before = counter_scope(svc, pids)
            answer = client.observe(plan["high_request"])
            finished = NOW()
            answer.update(step=step, finished_ns=finished, business_ns=finished-answer["timing"]["started_ns"],
                          resources_before=resource_before,resources_after=counter_scope(svc, pids))
            result["rows"].append(answer)
            dump(folder/(step+".json"),answer)
            svc.verify_answers("Yanyite",data,[answer],before,client.source)
        assert svc.binary(result["rows"][0]["result"]) == svc.binary(result["rows"][1]["result"])
    except Exception:
        result["errors"].append(traceback.format_exc())
    finally:
        if client is not None:
            try:
                exit_code = client.close()
                closed = read(folder/"client/CLOSE.json")
                released = {k:not active(v) for k,v in (
                    ("launcher",client.worker.pid),("actual_product",getattr(client,"server_pid",client.worker.pid)))}
                result.update(close=closed,released=released)
                assert all(released.values()) and exit_code==0 and closed["method"]=="eof"
                assert not client.reader.is_alive()
            except Exception:
                result["errors"].append(traceback.format_exc())
    if client and result["rows"]:
        try:
            # EOF has already flushed the audit. These checks and writes are out of the RTT clock.
            svc.associate(client, "Yanyite", result["rows"])
            result["observed_native_capture_calls"] = sum(
                sum(s["name"]=="host.capture_source_region_pair" for s in r["telemetry"]["spans"])
                for r in result["rows"])
            assert result["observed_native_capture_calls"] == len(result["rows"])
        except Exception:
            result["errors"].append(traceback.format_exc())
    result.update(end_ns=NOW(), valid=not result["errors"] and len(result["rows"])==2)
    result["wall_ns"] = result["end_ns"]-result["start_ns"]
    dump(folder/"CELL.json",result)
    print(folder.name,result["valid"],flush=True)
    return result


def summarize(hosts, svc, started, root):
    groups = []
    cells = []
    for host, orders in zip(hosts, read(PLAN)["cuts"], strict=True):
        for group, order in enumerate(orders, 1):
            received = host["cells"].get(group,{})
            cells.extend(received.values())
            row = {"host":host["host"],"group":group,"order":order,"host_pid":host.get("pid"),
                   "valid":False,"cells":{a:{"valid":v["valid"],"raw":v["raw"]} for a,v in received.items()}}
            if host["valid"] and all(received.get(a,{}).get("valid") for a in "ABC"):
                by_arm = {a:received[a]["rows"] for a in "ABC"}
                same = all(svc.binary(by_arm["A"][k]["result"]) == svc.binary(by_arm[arm][k]["result"])
                           for arm in "BC" for k in (0,1))
                if same:
                    first = {a:by_arm[a][0]["business_ns"]/1e6 for a in "ABC"}
                    warm = {a:by_arm[a][1]["business_ns"]/1e6 for a in "ABC"}
                    row.update(valid=True,first_ms=first,warm_ms=warm,delta_C_vs_A_ms=warm["C"]-warm["A"],
                               relative_C_vs_A=warm["C"]/warm["A"]-1,
                               delta_C_vs_B_ms=warm["C"]-warm["B"],relative_C_vs_B=warm["C"]/warm["B"]-1)
                else:
                    row["error"] = "cross-arm full response changed"
            groups.append(row)
    valid = [row for row in groups if row["valid"]]
    complete = len(valid)==12 and len(cells)==36 and len({h.get("pid") for h in hosts})==3
    summary = {"status":"incomplete","plan":pin(PLAN),"groups":groups,"valid_triplets":len(valid),
               "expected_triplets":12,"actual_cells":len(cells),"valid_cells":sum(c["valid"] for c in cells),
               "first_reads":sum(len(c["rows"])>=1 for c in cells),"warm_reads":sum(len(c["rows"])==2 for c in cells),
               "hosts":[{k:v for k,v in h.items() if k!="cells"} for h in hosts],
               "started_ns":started,"finished_ns":NOW()}
    summary["wall_ns"] = summary["finished_ns"]-started
    if complete:
        d = median(row["delta_C_vs_A_ms"] for row in valid)
        f = median(row["relative_C_vs_A"] for row in valid)
        h = [{"host":n,"delta_C_vs_A_ms":median(row["delta_C_vs_A_ms"] for row in valid if row["host"]==n),
              "relative_C_vs_A":median(row["relative_C_vs_A"] for row in valid if row["host"]==n)} for n in (1,2,3)]
        material = d > 5 and f > .05
        stable = material and sum(row["delta_C_vs_A_ms"]>0 for row in h)>=2
        summary.update(status="fail_warm_gate" if material else "pass",material_regression=material,stable_regression=stable,
                       median_delta_C_vs_A_ms=d,median_relative_C_vs_A=f,by_host=h,
                       median_delta_C_vs_B_ms=median(row["delta_C_vs_B_ms"] for row in valid),
                       median_relative_C_vs_B=median(row["relative_C_vs_B"] for row in valid),
                       first_medians_ms={a:median(row["first_ms"][a] for row in valid) for a in "ABC"},
                       warm_medians_ms={a:median(row["warm_ms"][a] for row in valid) for a in "ABC"})
    print(dump(root/"RESULTS.json",summary),flush=True)


def run(window_ref):
    plan=read(PLAN)
    window=read(window_ref)
    assert window["cycle_id"]==CYCLE and window["status"]=="available" and window["token"]
    for ref in [*plan["origins"], plan["offline"], plan["candidate"], plan["source_geometry"], plan["asset"]]:
        check(ref)
    root=STAGE/"attempt_001"
    root.mkdir()
    dump(root/"WINDOW_REF.json",pin(window_ref))
    old,gui,svc=environment()
    data=svc.fixture("Yanyite")
    assert arms(old,read(check(read(OFFLINE)["plan"])))==plan["arms"]
    assert data["expected"]==plan["expected_source"] and data["sequence"][0][1]==plan["high_request"]
    started=NOW()
    hosts=[]
    for index, orders in enumerate(plan["cuts"],1):
        folder=root/f"H{index}"
        folder.mkdir()
        host={"host":index,"start_ns":NOW(),"errors":[],"cells":{}}
        owner=None
        try:
            owner=gui.Owned(folder/"native",data["asset"],plan["support"],window)
            host["pid"]=owner.pid
            host["ready_ns"]=NOW()
            host["resources_ready"]=counter_scope(svc,{"host":owner.pid})
            before, host["before_snapshot_ns"]=svc.snapshot(owner,data,folder,"BEFORE")
            for count,order in enumerate(orders,1):
                host["cells"][count]={}
                for arm in order:
                    path=folder/f"H{index}-P{count}-{arm}"
                    row=cell(path,owner,before,arm,plan,data,svc)
                    row["raw"]=pin(path/"CELL.json")
                    host["cells"][count][arm]=row
                    assert row.get("released") and all(row["released"].values()), "product tree not confirmed reaped"
            after,host["after_snapshot_ns"]=svc.snapshot(owner,data,folder,"AFTER")
            assert svc.binary(before["geometry"])==svc.binary(after["geometry"])
            assert all(svc.binary(before[k])==svc.binary(after[k]) for k in ("frame","subframe","scale"))
            host["geometry_preserved"]=True
        except Exception:
            host["errors"].append(traceback.format_exc())
        finally:
            if owner is not None:
                try:
                    host["resources_before_close"]=counter_scope(svc,{"host":owner.pid})
                    host["close"]=owner.close()
                    assert not active(owner.pid)
                except Exception:
                    host["errors"].append(traceback.format_exc())
        host.update(end_ns=NOW(),valid=not host["errors"] and host.get("geometry_preserved",False))
        host["wall_ns"]=host["end_ns"]-host["start_ns"]
        path=folder/"HOST.json"
        dump(path,{k:v for k,v in host.items() if k!="cells"})
        host["raw"]=pin(path)
        hosts.append(host)
    summarize(hosts,svc,started,root)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("freeze","run"))
    parser.add_argument("--window",type=Path)
    args=parser.parse_args()
    if args.action=="freeze":
        freeze()
    else:
        run(args.window)

