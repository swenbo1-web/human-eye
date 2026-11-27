"""049 frozen 042-style Yanyite pairs plus post-timing H3 functional reads."""
from __future__ import annotations

import argparse
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from statistics import median
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
VER = HERE.parents[1]
ROOT = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT")
RAW = ROOT/"yanyite"
OLD = ROOT.parent/"M6-041-KERNEL-HOOK"
PLAN = RAW/"PLAN.json"
CYCLE = ROOT.name
CONTRACT = "4929a0c147e78c71f965b8d688174352266cf89f"
PYTHON = Path("D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe")
F_PINS = ROOT/"candidate/PINS.json"
F_SHA = "d30196668038e72c1315c5f9a36825c2197b06a283006244e701594217622567"
ORDERS = (("AF", "FA", "AF", "FA"), ("FA", "AF", "FA", "AF"), ("FA", "AF", "AF", "FA"))
NOW = time.perf_counter_ns


def read(path): return json.loads(Path(path).read_bytes())
def need(value, reason):
    if not value: raise ValueError("049_yanyite_"+reason)
def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream: digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}
def check(ref):
    need(pin(ref["path"]) == ref, "source_changed:"+ref["path"])
    return Path(ref["path"])
def dump(path, value):
    path = Path(path).resolve(); need(path.is_relative_to(RAW.resolve()), "output_scope")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as out:
        json.dump(value, out, indent=2, ensure_ascii=False, allow_nan=False); out.write("\n")
    return pin(path)
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module
def api():
    s1 = load("_049_yanyite_s1", OLD/"s1/s1.py")
    gui, svc = s1.api(); gui.PRIVATE = RAW; gui.CYCLE = CYCLE; svc.CYCLE = CYCLE
    gui.ASSET_SHAS = {"614684bb54bcbea6f2494fe704a0f77dd2a607fdba115a391686abdb362b8a7d": "Yanyite"}
    windows = load("_049_yanyite_windows", VER/"m6_r3_replacement_entry_045/g60_windows.py")
    return s1, gui, svc, windows


def install(ref, role):
    path = check(ref); binding = read(path); site = Path(binding["site_packages"])
    for entry in binding["source_files"]:
        need(pin(site/entry["path"])["sha256"] == entry["sha256"], "installed_source")
    launcher = path.with_name("target_runtime_entry.py")
    need(pin(launcher)["sha256"] == binding["launcher_sha256"], "launcher")
    return {"site_packages": str(site), "source_sha256": binding["identity"]["source_sha256"],
        "version": binding["identity"]["distribution_version"], "role": role,
        "source_count": len(binding["source_files"]), "binding": ref,
        "command_prefix": [binding["dependency_python"], "-I", "-B", str(launcher)]}


def freeze():
    need(pin(F_PINS)["sha256"] == F_SHA, "one_final_candidate")
    f = read(F_PINS); _, _, svc, _ = api(); data = svc.fixture("Yanyite")
    old = read(ROOT.parent/"M6-043-R3-REGION-ATTRIBUTION/live/yanyite/PLAN.json")
    source = read(VER/"m6_same_frame_scoped_batch_034/private/inputs/FROZEN.json")
    high, low = source["requests_A"]
    need(high == old["high_request"] == data["sequence"][0][1], "exact_042_high_request")
    arms = {"A": install(f["baseline_A"], "049 original032 ordinary stdio"),
            "F": install(f["binding"], "049 sole final candidate ordinary stdio")}
    need(arms["A"]["source_count"] == 143 and arms["F"]["source_count"] == 145, "bound_source_counts")
    refs = [*HERE.glob("*.py"), OLD/"s1/s1.py", VER/"m6_post032_profile_036/run.py",
        VER/"m6_post032_profile_036/gui.py", VER/"m6_post032_profile_036/gui_worker.py",
        VER/"m6_post032_profile_036/snapshot.py", VER/"m6_bounded_surface_scan_027/driver.py",
        VER/"m6_r3_replacement_entry_045/g60_windows.py",
        VER/"m6_r3_region_attribution_043/live_checks/observed_entry.py",
        VER/"m6_r3_region_attribution_043/live_checks/check_geometry.py"]
    geometry = {n: pin(ROOT.parent/f"M6-043-R3-REGION-ATTRIBUTION/holdouts/inputs/Yanyite_{n}.json") for n in ("high", "low")}
    plan = {"schema": "m6-049-yanyite-frozen-v1", "cycle_id": CYCLE, "contract": CONTRACT,
        "candidate": pin(F_PINS), "asset": data["asset"], "terminal": data["terminal"],
        "expected": data["expected"], "frame": data["frame"], "subframe": data["subframe"], "scale": data["scale"],
        "support": old["support"], "arms": arms, "requests": {"high": high, "low": low}, "orders": ORDERS,
        "geometry": geometry, "original_032_internal_remainder": pin(RAW/"prep_A_remainder_001/RESULTS.json"),
        "sources": [pin(p) for p in sorted(set(refs))], "request_budget_s": 30.0,
        "primary": "second identical high-box request: start of original stdio write through complete business body decode",
        "denominator": {"GUI": 3, "pairs": 12, "fresh_timed_services": 24, "timed_business_reads": 48},
        "gate": {"absolute_ms_strictly_above": 5, "relative_strictly_above": .05, "positive_host_medians_at_least": 2},
        "resource_scope": "Original boundary process counters outside each business clock; held native process handles for real wrapper/service creation/exit and lifetime CPU. No summed simultaneous peak.",
        "H3_post_timing": {"additional_GUI": 0, "ordinary_services": 2, "observed_only_not_performance": True,
            "A": ["low_first", "low_repeat", "high_first", "high_repeat"],
            "F": ["low_first", "low_repeat", "high_first", "high_repeat", "EDIT", "high_after", "high_after_repeat", "low_after", "low_after_repeat"],
            "edit": "Cube.location.z += 1/64 m, update, save_as_mainfile(copy=True) to a different owned file; source asset and input.blend unchanged",
            "native_return_observer": "frozen043 pure sys.setprofile observer; no replacement of methods/args; original production stdio. Functional only.",
            "acceptance": "Actual new full native geometry/public facts after edit, same F service, unchanged target source rows; preserve actual lease modes without demanding an immediate lease_hit.",
            "offline": "After GUI close replay each actual H3 pre/post high/low capture once per A/F, exact original options; separate from12 paired timing denominator"},
        "independent_failures": "Preserve any bad sample; continue independently safe checks. No formal replacement/retry or second candidate.",
        "no_Blender_until_exclusive_window": True, "model_calls": 0}
    print(dump(PLAN, plan), flush=True)


def client_type(svc):
    class Client(svc.Client):
        def __init__(self, folder, owner, arm):
            self.expected_source_count = arm["source_count"]
            super().__init__(folder, owner, "Yanyite", arm)
        def open(self, name):
            need(name == "Yanyite", "client_scenario")
            hello, timing = self.call("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": CYCLE, "version": "1"}})
            ident = hello["result"]["_meta"]["human_eye"]
            need(ident["source_sha256"] == self.source and ident["distribution_version"] == self.version and
                 ident["source_file_count"] == self.expected_source_count and ident["production_mode"] is True, "negotiated_identity")
            self.call("notifications/initialized", notify=True)
            catalog, tools_time = self.call("tools/list")
            tool, = [t for t in catalog["result"]["tools"] if t["name"] == "human_eye_scene_observe"]
            need("source_region_measurement" in json.dumps(tool), "ordinary_scoped_advertised")
            event, = [e for e in svc.lines(self.audit) if e.get("measurement_scope") == "service_constructor_only"]
            self.server_pid = event["pid"]
            need(event["runtime_identity"]["build_id"] == "sha256:"+self.source and
                event["identity_check"]["compatible"] and event["identity_check"]["actual"]["source_sha256"] == self.source, "constructor_identity")
            dump(self.folder/"STARTUP.json", {"hello": hello, "timing": timing, "catalog": catalog,
                "tools_time": tools_time, "actual_pid": self.server_pid, "startup_trace": event,
                "scoped_mode_advertised": True, "expected_source_count": self.expected_source_count})
    return Client


def begin_client(folder, owner, arm, svc, windows, record):
    # Retain ownership even if the inherited constructor fails after Popen.
    cls = client_type(svc); client = cls.__new__(cls)
    client.worker = client.reader = None
    record["_client"] = client
    record["client_begin"] = windows.mark("client_begin")
    cls.__init__(client, folder, owner, arm)
    client.open("Yanyite")
    record.update(product_pid=client.server_pid, wrapper_pid=client.worker.pid)
    held = {}; record["_held"] = held
    held["wrapper"] = windows.OwnedProcess(client.worker.pid, os.getpid(), arm["command_prefix"][0])
    held["service"] = (held["wrapper"] if client.server_pid == client.worker.pid else
        windows.OwnedProcess(client.server_pid, client.worker.pid, sys._base_executable))
    return client


def end_client(record, svc, windows):
    client = record.pop("_client", None); held = record.pop("_held", {})
    try:
        if client is not None and client.worker is not None:
            record["before_original_close"] = windows.mark("before_original_close")
            code = client.close(); record["after_original_close"] = windows.mark("after_original_close")
            record["close"] = read(client.folder/"CLOSE.json")
            need(code == 0 and record["close"]["method"] == "eof" and not client.reader.is_alive(), "normal_product_EOF")
            processes = {role: p.final() for role, p in held.items()}
            need(set(processes) == {"wrapper", "service"} and all(p["wait_result"] == 0 and p["exit_code"] == 0 for p in processes.values()), "native_process_exits")
            record["processes"] = processes
            record["os_survival_ns"] = (max(p["exit_time_100ns"] for p in processes.values())-
                processes["wrapper"]["creation_time_100ns"])*100
            need(record["os_survival_ns"] > 0, "OS_creation_exit_clock")
            svc.associate(client, "Yanyite", record["rows"])
    finally:
        for p in held.values(): p.release()


def timed_cell(folder, owner, before, arm, plan, data, svc, windows):
    folder.mkdir(); rec = {"arm": arm, "rows": [], "errors": [], "started_ns": NOW()}
    try:
        client = begin_client(folder/"client", owner, plan["arms"][arm], svc, windows, rec)
        for step in ("first_high", "warm_high"):
            usage = svc.transport.counters(client.server_pid)
            row = client.observe(plan["requests"]["high"]); end = NOW()
            row.update(step=step, body_decoded_ns=end, business_ns=end-row["timing"]["started_ns"],
                counters_before=usage, counters_after=svc.transport.counters(client.server_pid))
            rec["rows"].append(row)
            dump(folder/(step+".json"), row)
            svc.verify_answers("Yanyite", data, [row], before, client.source)
        need(svc.binary(rec["rows"][0]["result"]) == svc.binary(rec["rows"][1]["result"]), "first_repeat_public_identity")
    except BaseException: rec["errors"].append(traceback.format_exc())
    finally:
        try: end_client(rec, svc, windows)
        except BaseException: rec["errors"].append(traceback.format_exc())
    rec.update(ended_ns=NOW(), valid=not rec["errors"] and len(rec["rows"]) == 2)
    rec["client_full_ns"] = rec["ended_ns"]-rec["started_ns"]
    dump(folder/"CELL.json", rec); print(folder.name, rec["valid"], flush=True)
    return rec


def raw_snapshot(owner, folder, label):
    rpc = owner.run((VER/"m6_post032_profile_036/snapshot.py").read_text(encoding="utf8"))
    dump(folder/(label+"_RPC.json"), rpc); need(rpc["response"]["status"] == "success", "native_snapshot")
    line, = [s for s in rpc["response"]["result"]["result"].splitlines() if s.startswith("M6_036_SNAPSHOT:")]
    value = json.loads(line.split(":", 1)[1]); need(value["pid"] == owner.pid and value["main_thread"] and not value["background"], "owned_snapshot_identity")
    dump(folder/(label+".json"), value); return value


def edit(owner, folder):
    destination = owner.workspace/"049_reference_edit.blend"
    code = ("import bpy,json,os,hashlib,struct\nobj=bpy.data.objects['Cube']\nz=float(obj.location.z)\n"
        "before=hashlib.sha256(b''.join(struct.pack('<3d',*v.co) for v in obj.data.vertices)).hexdigest()\n"
        "obj.location.z=z+1/64\nbpy.context.view_layer.update()\nbpy.context.preferences.filepaths.save_version=0\n"
        f"saved=bpy.ops.wm.save_as_mainfile(filepath={str(destination)!r},copy=True,check_existing=False)\n"
        "after=hashlib.sha256(b''.join(struct.pack('<3d',*v.co) for v in obj.data.vertices)).hexdigest()\n"
        "print(json.dumps({'pid':os.getpid(),'before_z':z,'after_z':float(obj.location.z),'before_local':before,'after_local':after,'status':sorted(saved),'open_filepath':bpy.data.filepath}))")
    dump(folder/"EDIT_INTENT.json", {"code": code, "destination": str(destination), "at_most_once": True})
    rpc = owner.run(code); dump(folder/"EDIT_RPC.json", rpc)
    need(rpc["response"]["status"] == "success", "actual_edit_reply")
    value = json.loads(rpc["response"]["result"]["result"].strip().splitlines()[-1])
    need(value["pid"] == owner.pid and value["after_z"]-value["before_z"] == 1/64 and value["before_local"] == value["after_local"] and value["status"] == ["FINISHED"], "dyadic_Cube_edit_only")
    ref = {"actual": value, "saved_private_file": pin(destination)}; dump(folder/"EDIT.json", ref); return ref


def functional(folder, owner, before, plan, svc, windows):
    folder.mkdir(); result = {"status": "failed", "arms": {}, "errors": [], "timing_denominator": False}
    checker = load("_049_region_checker", VER/"m6_r3_region_attribution_043/live_checks/check_geometry.py")
    cases = {n: read(check(plan["geometry"][n])) for n in ("high", "low")}
    for arm in ("A", "F"):
        path = folder/arm; path.mkdir(); rec = {"rows": [], "errors": [], "functional_only": True}
        cfg = dict(plan["arms"][arm])
        cfg["command_prefix"] = [str(PYTHON), "-I", "-B", str(VER/"m6_r3_region_attribution_043/live_checks/observed_entry.py"), cfg["command_prefix"][-1]]
        try:
            client = begin_client(path/"client", owner, cfg, svc, windows, rec)
            labels = ["low_first", "low_repeat", "high_first", "high_repeat"]
            if arm == "F": labels += ["high_after", "high_after_repeat", "low_after", "low_after_repeat"]
            for label in labels:
                if label == "high_after":
                    result["actual_edit"] = edit(owner, folder)
                    result["after_edit_snapshot"] = raw_snapshot(owner, folder, "AFTER_EDIT")
                region_name = "low" if label.startswith("low") else "high"
                row = client.observe(plan["requests"][region_name]); row.update(step=label, region=region_name)
                rec["rows"].append(row); dump(path/(label+".json"), row)
                need(not row["tool_error"] and not row["rpc_error"], "functional_public_success:"+label)
        except BaseException: rec["errors"].append(traceback.format_exc())
        finally:
            try: end_client(rec, svc, windows)
            except BaseException: rec["errors"].append(traceback.format_exc())
        try:
            index = read(path/"client/RETURN_OBSERVER/INDEX.json")
            need(index["error"] is None and index["methods_or_arguments_modified"] is False, "pure_return_observer")
            captures = [read(check(ref)) for ref in index["captures"]]
            need(len(captures) == len(rec["rows"]), "one_actual_capture_each_functional_read")
            rec["actual_capture_refs"] = index["captures"]; qualified = []
            for row, captured in zip(rec["rows"], captures):
                shift = Q(1,64) if "after" in row["step"] else Q(0)
                qualified.append(checker.region(captured["capture"], cases[row["region"]], row["result"], reference_shift=shift))
            rec["qualification"] = qualified
            rec["native_cache_observations"] = [{"label": r["step"], "payload_sha256": c["capture"]["payload_sha256"],
                "work": c["capture"]["work"], "lease": c["residency_reply"].get("lease"),
                "native_full_payload": c["residency_reply"].get("capture") is not None} for r,c in zip(rec["rows"], captures)]
            if arm == "F":
                need(captures[3]["capture"]["payload_sha256"] != captures[4]["capture"]["payload_sha256"], "same_service_same_box_edit_invalidated_old_payload")
                need(rec["rows"][3]["result"]["distance_m"] != rec["rows"][4]["result"]["distance_m"], "actual_current_geometry_not_stale")
                result["same_F_service_edit_invalidation"] = True
                for pre, post in ((2,4),(0,6)):
                    result.setdefault("offline_inputs", []).append({"region": rec["rows"][pre]["region"],
                        "before": index["captures"][pre], "after": index["captures"][post], "includes_capture_wrapper": True})
        except BaseException: rec["errors"].append(traceback.format_exc())
        rec["valid"] = not rec["errors"]
        dump(path/"RESULTS.json", rec); result["arms"][arm] = rec
    try:
        final = result["after_edit_snapshot"]
        for name in before["geometry"]:
            a, b = before["geometry"][name], final["geometry"][name]
            if name != "Cube": need(svc.binary(a) == svc.binary(b), "unchanged_non_Cube_source")
            else:
                for key in ("vertices", "triangles", "local_sha256", "triangles_sha256"): need(a[key] == b[key], "Cube_topology_local_unchanged")
                matrix = [list(v) for v in a["matrix"]]; matrix[2][3] += 1/64
                need(matrix == b["matrix"], "Cube_translation_readback")
        result["only_private_reference_transform_changed"] = True
    except BaseException: result["errors"].append(traceback.format_exc())
    result["status"] = "pass" if not result["errors"] and all(v["valid"] for v in result["arms"].values()) else "failed"
    dump(folder/"RESULTS.json", result); return result


def summary(hosts):
    pairs = []
    for h in hosts:
        for index, order in enumerate(ORDERS[h["host"]-1], 1):
            row = {"host": h["host"], "pair": index, "order": order, "valid": False}
            cells = h["cells"].get(str(index), {})
            if all(cells.get(a, {}).get("valid") for a in "AF") and h.get("timed_geometry_preserved"):
                a, f = cells["A"]["rows"], cells["F"]["rows"]
                for j in (0,1): need(a[j]["result"] == f[j]["result"], "paired_full_public_geometry")
                ta, tf = a[1]["business_ns"], f[1]["business_ns"]
                row.update(valid=True, A_warm_ns=ta, F_warm_ns=tf, delta_ms=(tf-ta)/1e6, relative=tf/ta-1,
                    A_first_ns=a[0]["business_ns"], F_first_ns=f[0]["business_ns"])
            pairs.append(row)
    valid = [p for p in pairs if p["valid"]]
    out = {"expected_pairs": 12, "pairs": pairs, "valid_pairs": len(valid), "stable_regression": None}
    if len(valid) == 12 and len(hosts) == 3:
        delta = median(r["delta_ms"] for r in valid); rel = median(r["relative"] for r in valid)
        by_host = [{"host": h, "delta_ms": median(r["delta_ms"] for r in valid if r["host"]==h),
                    "relative": median(r["relative"] for r in valid if r["host"]==h)} for h in (1,2,3)]
        out.update(median_delta_ms=delta, median_relative=rel, by_host=by_host,
            material_regression=delta>5 and rel>.05,
            stable_regression=delta>5 and rel>.05 and sum(h["delta_ms"]>0 for h in by_host)>=2)
    return out


def run(window_path):
    plan = read(PLAN); window = read(window_path)
    need(window["cycle_id"] == CYCLE and window["status"] == "available" and window["token"], "exclusive_window")
    for ref in plan["sources"]: check(ref)
    check(plan["candidate"])
    for a in "AF": need(install(plan["arms"][a]["binding"], plan["arms"][a]["role"]) == plan["arms"][a], "fixed_install")
    _, gui, svc, windows = api(); data = svc.fixture("Yanyite")
    out = RAW/"main_001"; out.mkdir(); hosts = []; started = NOW()
    for host_index, orders in enumerate(ORDERS, 1):
        folder = out/f"H{host_index}"; folder.mkdir(); owner = None
        rec = {"host": host_index, "cells": {}, "errors": [], "started_ns": NOW()}
        try:
            owner = gui.Owned(folder/"native", plan["asset"], plan["support"], window); rec["pid"] = owner.pid
            before, _ = svc.snapshot(owner, data, folder, "BEFORE")
            for index, order in enumerate(orders, 1):
                rec["cells"][str(index)] = {}
                for arm in order:
                    cell = timed_cell(folder/f"P{index}-{arm}", owner, before, arm, plan, data, svc, windows)
                    rec["cells"][str(index)][arm] = cell
                    need(cell.get("close", {}).get("method") == "eof", "prior_service_exit")
            after, _ = svc.snapshot(owner, data, folder, "AFTER_TIMED")
            for key in ("frame", "subframe", "scale", "geometry"):
                need(svc.binary(before[key]) == svc.binary(after[key]), "unchanged_timed_geometry")
            rec["timed_geometry_preserved"] = True
            if host_index == 3: rec["functional"] = functional(folder/"functional", owner, before, plan, svc, windows)
        except BaseException: rec["errors"].append(traceback.format_exc())
        finally:
            if owner is not None:
                try: rec["GUI_close"] = owner.close()
                except BaseException: rec["errors"].append(traceback.format_exc())
        rec.update(ended_ns=NOW()); rec["full_GUI_and_QA_ns"] = rec["ended_ns"]-rec["started_ns"]
        rec["valid"] = not rec["errors"] and rec.get("GUI_close", {}).get("status") == "pass"
        dump(folder/"HOST.json", rec); hosts.append(rec)
    result = {"schema": "m6-049-yanyite-live-result-v1", "plan": pin(PLAN), "window": pin(window_path),
        "hosts": [pin(out/f"H{i}/HOST.json") for i in (1,2,3)], "timing": summary(hosts),
        "complete_window_ns": NOW()-started, "H3_functional": hosts[-1].get("functional", {}).get("status"),
        "all_GUI_cleanup_pass": all(h.get("GUI_close", {}).get("status")=="pass" for h in hosts)}
    result["status"] = "pass" if result["timing"]["valid_pairs"] == 12 and result["all_GUI_cleanup_pass"] and result["H3_functional"] == "pass" else "failed"
    print(dump(out/"RESULTS.json", result), flush=True); return int(result["status"] != "pass")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("action", choices=("freeze", "run")); parser.add_argument("--window", type=Path)
    args = parser.parse_args()
    if args.action == "freeze": freeze()
    else: raise SystemExit(run(args.window))
