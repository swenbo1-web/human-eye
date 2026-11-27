"""Fixed D48 and G508 ordinary Blender/MCP spot checks with preserved exits."""
from collections import Counter
from hashlib import file_digest
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT")
OUT = RAW/"spots"
CYCLE = RAW.name
ROOT041 = RAW.parent/"M6-041-KERNEL-HOOK"
S1_REV = "37de6d795f6329e0257a327d862ac87d5131a439"
F_PINS = RAW/"candidate/PINS.json"
A_BIND = ROOT041/"install/032/.human-eye/releases/9.7.2+k041hook032/admin/RUNTIME_BINDING.json"
PLAN = OUT/"PLAN.json"
now = time.perf_counter_ns


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        digest = file_digest(stream,"sha256").hexdigest()
    return {"path":str(path),"bytes":path.stat().st_size,"sha256":digest}


def dump(path,value):
    with path.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write("\n")


def check(item):
    assert pin(item["path"]) == item, item["path"]
    return Path(item["path"])


def load(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def engine(binding_path):
    binding = read(binding_path)
    src = Path(binding["site_packages"])
    for row in binding["source_files"]:
        assert pin(src/row["path"])["sha256"]==row["sha256"]
    launcher = binding_path.parent/"target_runtime_entry.py"
    assert pin(launcher)["sha256"]==binding["launcher_sha256"]
    identity = binding["identity"]
    return {"source_sha256":identity["source_sha256"],"version":identity["distribution_version"],
            "source_file_count":len(binding["source_files"]),"site_packages":str(src),
            "role":"049 ordinary spot check","command_prefix":[binding["dependency_python"],"-I","-B",str(launcher)],
            "binding":pin(binding_path)}


def setup():
    path = OUT/"original_041_s1.py"
    original = load("spot_original_041",path)
    gui,svc = original.api()
    gui.CYCLE = svc.CYCLE = CYCLE
    gui.ASSET_SHAS = {pin(original.ASSETS[name])["sha256"]:name for name in ("D48","G508")}
    return original,gui,svc


def prepare():
    OUT.mkdir(parents=True)
    path = OUT/"original_041_s1.py"
    with path.open("xb") as stream:
        stream.write(subprocess.check_output(["git","show",S1_REV+
                    ":verification/m6_041_kernel_hook_comparison/s1/s1.py"],cwd=HERE))
    original,gui,svc = setup()
    frozen = {"cycle_id":CYCLE,"original_041_s1":pin(path),"driver":pin(__file__),
              "candidate":pin(F_PINS),"arms":{"A":engine(A_BIND),"F":engine(check(read(F_PINS)["binding"]))},
              "assets":{scenario:pin(original.ASSETS[scenario]) for scenario in ("D48","G508")},
              "inputs":{key:pin(original.INPUTS[key]) for key in
                         ("D48","D48_exact","G508","scale_truth","G60_relation")},
              "support":gui.prepare(),"order":[["D48","A"],["D48","F"],["G508","F"],["G508","A"]],
              "requests":{scenario:{label:original.request(scenario,label) for label in original.SEQUENCES[scenario]}
                          for scenario in ("D48","G508")},
              "previous":{scenario:pin(ROOT041/"s1/slots_recovery_01"/(scenario+"_032")/"SLOT.json")
                          for scenario in ("D48","G508")},
              "scope":"Four owned GUI/MCP cells and original 041 sequences. Observed costs are descriptive, no new benchmark gate."}
    src = HERE/"g60_b02"
    frozen["client_sources"] = {name:pin(src/name) for name in ("client.py","g60_windows.py")}
    dump(PLAN,frozen)
    print(pin(PLAN),flush=True)


def stable(value):
    return {key:row for key,row in value.items() if key not in ("trace_id","binding")}


def paths(telemetry):
    counts = Counter()
    for task in telemetry["work"]:
        if task.get("result_cache_hit"):
            counts["result_cache_hit"] += 1
        pairs = task.get("pairs")
        if isinstance(pairs,dict):
            for detail in pairs.values():
                if detail.get("surface_pair_cache_hit"):
                    counts["pair_cache_hit"] += 1
                work = detail.get("surface_work")
                if work:
                    counts[work.get("solver_path","032_baseline")] += 1
        elif isinstance(pairs,list):
            for detail in pairs:
                work = detail.get("surface_work")
                if isinstance(work,dict) and work:
                    counts[work.get("solver_path","032_baseline")] += 1
    return dict(counts)


def execute(original,gui,svc,client_class,plan,current_dir,scenario,arm,window):
    current_dir.mkdir()
    host = client = None
    started = now()
    result = {"scenario":scenario,"arm":arm,"rows":[],"errors":[],"cleanup":{}}
    try:
        host = gui.Owned(current_dir/"native",plan["assets"][scenario],plan["support"],window)
        initial = original.loadsnap(host,"BEFORE",current_dir)
        assert original.check_input(scenario,initial,svc)
        client_started = now()
        client = client_class(svc)(current_dir/"client",host,plan["arms"][arm])
        client.launch()
        # 045 client open's label check only governs catalog class, with the same
        # unchanged stdio initialize, tools/list and audit handshake for either scene.
        client.open("G60")
        result["source_id"] = client.source
        result["host_pid"] = host.pid
        result["product_pid"] = client.server_pid
        expected = {row["label"]:row for row in read(check(plan["previous"][scenario]))["rows"]}
        pre_counters = svc.transport.counters(client.server_pid)
        client.mark("before_first_observe")
        for label,request in plan["requests"][scenario].items():
            rpc = client.observe(request)
            end = now()
            body = rpc["result"]
            audit = original.brief_trace(client,rpc)
            row = {"label":label,"business_ns":end-rpc["timing"]["started_ns"],"body":body,
                   "rpc":rpc,"audit":audit,"actual_path_counts":paths(audit)}
            result["rows"].append(row)
            row["semantic_equals_041_032"] = stable(body)==stable(expected[label]["value"])
            row["binding_checked"] = body["binding"]["runtime_source_sha256"]==client.source
            if not row["semantic_equals_041_032"] or not row["binding_checked"] or rpc["rpc_error"] or rpc["tool_error"]:
                result["errors"].append({"phase":"business_comparison","label":label})
        client.mark("last_business_decode")
        result["startup_through_last_business_ns"] = end-client_started
        result["product_os_before"] = pre_counters
        result["product_os_after"] = svc.transport.counters(client.server_pid)
        result["geometry_preserved"] = original.geokey(original.loadsnap(host,"AFTER",current_dir))==original.geokey(initial)
        assert result["geometry_preserved"]
    except Exception:
        result["errors"].append({"phase":"execute","traceback":traceback.format_exc()})
    finally:
        if client is not None and client.worker is not None:
            try:
                eof = client.close()
                client.mark("client_end")
                result["cleanup"]["product"] = client.lifecycle()
                assert eof==0 and result["cleanup"]["product"]["valid"]
            except Exception:
                result["errors"].append({"phase":"product_close","traceback":traceback.format_exc()})
        if host is not None:
            try:
                result["cleanup"]["gui"] = host.close()
                assert result["cleanup"]["gui"]["status"]=="pass"
            except Exception:
                result["errors"].append({"phase":"gui_close","traceback":traceback.format_exc()})
    result["host_to_cleanup_ns"] = now()-started
    result["status"] = "pass" if not result["errors"] and len(result["rows"])==len(plan["requests"][scenario]) else "fail"
    dump(current_dir/"CELL.json",result)
    print(scenario,arm,result["status"],flush=True)
    return result


def run(window):
    plan = read(PLAN)
    check(plan["driver"])
    for item in (plan["original_041_s1"],plan["candidate"],*plan["assets"].values(),
                 *plan["inputs"].values(),*plan["client_sources"].values()):
        check(item)
    for arm,record in plan["arms"].items():
        assert record == engine(check(record["binding"])), arm
    original,gui,svc = setup()
    sys.path.insert(0,str(HERE/"g60_b02"))
    from client import client_class

    attempt = OUT/"attempt_001"
    attempt.mkdir()
    win = read(window)
    assert win["cycle_id"]==CYCLE and win["status"]=="available" and win["token"]
    dump(attempt/"WINDOW.json",win)
    cells = {}
    for scenario,arm in plan["order"]:
        label = scenario+"_"+arm
        cells[label] = execute(original,gui,svc,client_class,plan,attempt/label,scenario,arm,win)
    comparison = {}
    for name in ("D48","G508"):
        phases = {}
        for arm in "AF":
            cell = cells[name+"_"+arm]
            phases[arm] = {"status":cell["status"],
                           "cell":pin(attempt/(name+"_"+arm)/"CELL.json"),
                           "process_survival_ns":cell["cleanup"].get("product",{}).get("os_survival_ns"),
                           "requests":{row["label"]:{"business_ns":row["business_ns"],"paths":row["actual_path_counts"],
                                                     "equal_prior_032":row["semantic_equals_041_032"]} for row in cell["rows"]}}
        comparison[name] = phases
    dump(attempt/"RESULTS.json",{"plan":pin(PLAN),"status":"pass" if all(c["status"]=="pass" for c in cells.values()) else "fail",
                                "descriptive_comparisons":comparison})
    print(pin(attempt/"RESULTS.json"),flush=True)


if __name__=="__main__":
    prepare() if sys.argv[1]=="prepare" else run(Path(sys.argv[2]))

