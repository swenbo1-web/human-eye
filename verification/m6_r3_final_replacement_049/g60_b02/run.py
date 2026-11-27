"""049 frozen ordinary G60/B02 entry; import/freeze never starts Blender."""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from statistics import median
import sys
import traceback
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from client import client_class
from g60_windows import NOW
from lifecycle import validate_lifecycle

VER = HERE.parents[1]
RAW = Path("D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT/g60_b02")
OLD = RAW.parents[1] / "M6-041-KERNEL-HOOK"
CYCLE = "M6-049-R3-FINAL-REPLACEMENT"
CONTRACT = "4929a0c147e78c71f965b8d688174352266cf89f"
FINAL = RAW.parent / "candidate/PINS.json"
FINAL_SHA = "d30196668038e72c1315c5f9a36825c2197b06a283006244e701594217622567"
G60_PLAN = RAW.parents[1] / "M6-045-R3-REPLACEMENT-ENTRY/g60/PLAN.json"
ORDERS = {"G60": ("ABF", "AFB", "BAF", "BFA", "FAB", "FBA"),
          "B02": ("AF", "FA", "AF", "FA", "AF", "FA")}
PLAN = RAW / "PLAN.json"
_API = None


def need(ok, reason):
    if not ok:
        raise ValueError("049_live_" + reason)


def read(path):
    return json.loads(Path(path).read_bytes())


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return dict(path=str(path), bytes=path.stat().st_size, sha256=digest)


def check(ref):
    need(pin(ref["path"]) == ref, "source_changed:" + ref["path"])
    return Path(ref["path"])


def dump(path, value):
    path = Path(path).resolve()
    need(path.is_relative_to(RAW.resolve()), "output_scope")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return pin(path)


def binary(value):
    if type(value) is float:
        return {"f64": value.hex()}
    if isinstance(value, list):
        return [binary(v) for v in value]
    if isinstance(value, dict):
        return {k: binary(v) for k, v in value.items()}
    return value


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def api():
    global _API
    if _API is None:
        s1 = load("_049_original041_s1", OLD / "s1/s1.py")
        gui, service = s1.api()
        gui.PRIVATE, gui.CYCLE = RAW, CYCLE
        gui.ASSET_SHAS = {pin(s1.ASSETS[name])["sha256"]: name for name in ORDERS}
        service.CYCLE = CYCLE
        comparable = load("_049_original043_compare", VER / "m6_r3_region_attribution_043/live_g60/common.py")
        _API = s1, gui, service, comparable
    return _API


def normalized_arm(arm, binding_ref):
    arm = deepcopy(arm)
    binding = read(check(binding_ref))
    need(binding["identity"]["source_sha256"] == arm["source_sha256"], "arm_identity")
    arm["source_file_count"] = len(binding["source_files"])
    arm["binding"] = binding_ref
    for row in binding["source_files"]:
        need(pin(Path(arm["site_packages"]) / row["path"])["sha256"] == row["sha256"], "installed_file")
    need(pin(arm["command_prefix"][-1])["sha256"] == binding["launcher_sha256"], "installed_launcher")
    return arm


def freeze():
    s1, _, svc, _ = api()
    final = read(FINAL)
    need(pin(FINAL)["sha256"] == FINAL_SHA and final["source_count"] == 145, "single_final_candidate")
    old = read(G60_PLAN)
    baseline = s1.source_plan()
    old_pins = read(s1.PINS)
    arms = {"A": normalized_arm(baseline["032"], old_pins["binding"]["032"]),
            "B": normalized_arm(baseline["r3"], old_pins["binding"]["r3"]),
            "F": normalized_arm(final["arm"], final["binding"])}
    need(arms["A"]["source_sha256"] == old["arms"]["A"]["source_sha256"] and
         arms["B"]["source_sha256"] == old["arms"]["B"]["source_sha256"], "same_045_AB")
    prior = read(OLD / "s1/PLAN_recovery_01.json")
    cases = {}
    for name in ORDERS:
        asset = prior["assets"][name]
        check(asset)
        if name == "G60":
            cases[name] = dict(asset=asset, requests=old["requests"], steps=old["steps"],
                truth=old["truth"], expected_snapshot=old["expected_snapshot"],
                snapshot_fixture=old["snapshot_fixture"], frame=old["frame"], subframe=old["subframe"], scale=old["scale"],
                expected_kernel_calls={"nearest": 11, "scan": 66}, ordinary_source_plan=pin(G60_PLAN))
        else:
            historical = OLD / "s1/slots_recovery_01/B02_032"
            before = read(historical / "BEFORE.json")
            snapshot = {n: {k: r[k] for k in ("local_sha256", "world_sha256", "triangles_sha256", "matrix", "visible")}
                        for n, r in before["geometry"].items() if r["type"] == "MESH"}
            slot = read(historical / "SLOT.json")
            need(slot["completed"] and slot["geometry_binds"] and slot["geometry_preserved"] and not slot["errors"], "old_B02_qualified")
            cases[name] = dict(asset=asset, requests=prior["requests"][name], steps=["nearest", "scan"],
                truth={r["label"]: pin(historical / (r["label"] + ".json")) for r in slot["rows"]},
                truth_public_container="value", expected_snapshot=snapshot,
                snapshot_fixture=prior["inputs"]["B02"], frame=1, subframe=0.0, scale=1.0,
                expected_kernel_calls={"nearest": 10, "scan": 112}, ordinary_source_plan=pin(OLD / "s1/PLAN_recovery_01.json"),
                old_actual_before=pin(historical / "BEFORE.json"), old_actual_slot=pin(historical / "SLOT.json"),
                independent={k: v for k, v in prior["inputs"].items() if k in ("B02_exact", "B02_scan", "B02_bundle")})
    refs = {str(path): pin(path) for path in (
        Path(__file__), HERE / "client.py", HERE / "g60_windows.py", HERE / "lifecycle.py", HERE / "SOURCE_CUSTODY.json",
        HERE / "prepare_sources.py", OLD / "s1/s1.py", VER / "m6_post032_profile_036/gui.py",
        VER / "m6_post032_profile_036/gui_worker.py", VER / "m6_post032_profile_036/snapshot.py",
        VER / "m6_post032_profile_036/run.py", VER / "m6_bounded_surface_scan_027/driver.py",
        VER / "m6_bvh_entry_qualification_024/entry.py", VER / "m6_r3_region_attribution_043/live_g60/common.py",
        VER / "m6_r3_replacement_entry_045/g60_verify.py")}
    for ref in prior["support"].values():
        check(ref)
    for case in cases.values():
        for ref in (*case["truth"].values(), case["snapshot_fixture"], *case.get("independent", {}).values()):
            check(ref)
    plan = dict(schema="m6-049-G60-B02-live-plan-v1", status="frozen_not_launched", cycle_id=CYCLE,
        contract=CONTRACT, final_pins=pin(FINAL), original_045_plan=pin(G60_PLAN), original_041_plan=pin(OLD / "s1/PLAN_recovery_01.json"),
        arms=arms, cases=cases, orders={k: list(v) for k, v in ORDERS.items()}, support=prior["support"], sources=refs,
        expected=dict(G60=dict(hosts=6, services=18, business_reads=54), B02=dict(hosts=6, services=12, business_reads=24)),
        primary="contiguous first business request write through complete final scan business decode",
        business_chains={"G60": "overview -> Target nearest -> 5mm scan", "B02": "Obj_014 nearest -> 2mm scan"},
        lifecycle="045 unchanged memory marks and held Windows process handles: OS creation through max(wrapper/service actual exit); client end/archive reported separately",
        archive_count="5 startup/notification wire files plus 2 per business reply; G60=11/B02=9",
        Hook="Same 041 installed target_runtime_entry serve and configuration as 045: observe_on_prompt false; no new Hook command or automatic dispatch",
        original_budget_s=30.0, ordinary_unmodified_addon=True, extra_business_instrumentation=False,
        initial="Independent fresh private GUI per group, new installed service/state per arm, same-host natural GUI reuse, no OS cache reset",
        gates=dict(G60_business=dict(minimum_F_saving_A=.10, minimum_F_faster_A=5, maximum_F_increase_B=.05),
                   G60_process=dict(F_saving_A_strictly_positive=True, maximum_F_increase_B=.05),
                   B02_business=dict(maximum_F_increase_A=.05)),
        invalid="retain failed sample; no post-result version changes or replacement formal sample",
        no_new_model_turns=True)
    print(dump(PLAN, plan), flush=True)


def current():
    plan = read(PLAN)
    need(plan["cycle_id"] == CYCLE and plan["contract"] == CONTRACT and plan["orders"] == {k: list(v) for k, v in ORDERS.items()}, "frozen_plan")
    for ref in (*plan["sources"].values(), *plan["support"].values(), plan["final_pins"], plan["original_045_plan"], plan["original_041_plan"]):
        check(ref)
    for arm in plan["arms"].values():
        need(normalized_arm(arm, arm["binding"]) == arm, "held_install")
    for case in plan["cases"].values():
        for ref in (case["asset"], case["snapshot_fixture"], *case["truth"].values(), *case.get("independent", {}).values()):
            check(ref)
    api()
    return plan


def public_truth(case, step):
    body = read(case["truth"][step]["path"])
    return body[case["truth_public_container"]] if "truth_public_container" in case else body


def audit_rows(folder, cell, plan, before, family):
    _, _, _, compare = api()
    case, arm = plan["cases"][family], plan["arms"][cell["arm"]]
    folder = Path(folder)
    startup, config, launch, close = [read(folder / "client" / name) for name in ("STARTUP.json", "CONFIG.json", "LAUNCH.json", "CLOSE.json")]
    ident = startup["hello"]["result"]["_meta"]["human_eye"]
    need(ident["source_sha256"] == arm["source_sha256"] and ident["distribution_version"] == arm["version"] and
         ident["source_file_count"] == arm["source_file_count"] and ident["production_mode"], "negotiated_identity")
    need(config["project_root"] == arm["site_packages"] and config["expected_identity"] == {"source_sha256": arm["source_sha256"]} and
         config["request_budget_s"] == config["blender"]["timeout_s"] == 30.0 and
         config["blender"]["host"] == cell["host"] and config["blender"]["port"] == cell["port"], "original_config")
    need(launch["command"] == [*arm["command_prefix"], "serve", "--config", str(folder / "client/CONFIG.json")] and
         startup["actual_pid"] == cell["product_pid"] and close["method"] == "eof" and close["exit_code"] == 0, "ordinary_process")
    logs = [json.loads(line) for line in (folder / "client/AUDIT.jsonl").read_bytes().splitlines() if line]
    semantic = {}
    need([r["step"] for r in cell["rows"]] == case["steps"], "complete_chain")
    for row in cell["rows"]:
        step, body, timing = row["step"], row["result"], row["timing"]
        request_path, response_path = [folder / "client" / (timing["id"] + suffix) for suffix in (".TX.bin", ".RX.bin")]
        sent, received = read(request_path), read(response_path)
        need(sent["params"] == case["requests"][step] and sent["id"] == received["id"] == timing["id"] and
             compare.body_from_response(received) == body and not row["tool_error"] and row["rpc_error"] is None, "original_wire")
        need(timing["tx_bytes"] == request_path.stat().st_size and timing["rx_bytes"] == response_path.stat().st_size and
             timing["wire_wait_ns"] + timing["client_decode_ns"] == timing["client_full_ns"] == timing["closed_ns"]-timing["started_ns"], "wire_clock")
        event, = [e for e in logs if e.get("event") == "request_trace" and str(e["trace"]["annotations"].get("mcp_request_id")) == timing["id"]]
        trace = event["trace"]
        need(event["pid"] == trace["pid"] == cell["product_pid"] and event["runtime_identity"]["build_id"] == "sha256:"+arm["source_sha256"] and
             event["identity_check"]["compatible"] and event["identity_check"]["actual"]["source_sha256"] == arm["source_sha256"], "trace_identity")
        ann = trace["annotations"]
        need(ann["include_image"] is False and ann["mcp_native_image_block_count"] == 0 and ann["delivery"] == "stdio_write_completed" and not trace["image_events"], "ordinary_publication")
        observe, = [e for e in logs if e.get("event") == "observe" and e.get("request_id") == trace["request_id"]]
        need(observe["pid"] == cell["product_pid"], "bound_observe")
        if "trace_id" in body:
            need(body["trace_id"] == trace["trace_id"], "body_trace")
        if "binding" in body:
            need(body["binding"]["runtime_source_sha256"] == arm["source_sha256"] and body["binding"]["scene_revision"] == observe["scene_revision"], "body_source")
        if step == "overview":
            names = sorted(n for n, r in before["geometry"].items() if r["type"] == "MESH")
            need(body["status"] == "overview" and body["query_result"]["status"] == "complete" and body["query_result"]["exact_pair_count"] == 0 and
                 sorted(r["name"] for r in body["objects"]) == names, "complete_overview")
        else:
            need(binary(compare.geometry(body)) == binary(compare.geometry(public_truth(case, step))), "complete_historical_geometry:"+family+":"+step)
            work = observe["task_work"]
            need(body["status"] == "complete" and work["result_cache_hit"] is False and work["kernel_calls"] == case["expected_kernel_calls"][step], "cold_coverage")
            if family == "B02" and step == "nearest":
                truth = read(case["independent"]["B02_exact"]["path"])
                need(body["distance_m"] == truth["global_distance_m"] and [r["name"] for r in body["nearest_objects"]] == truth["nearest_names"] and
                     body["coverage"] == {"targets_excluding_focal": 23, "distance_valid": 10, "strictly_excluded": 13, "unresolved": 0}, "independent_B02_nearest")
            if family == "B02" and step == "scan":
                truth = read(case["independent"]["B02_scan"]["path"])
                exact = {tuple(sorted((r["object_a"], r["object_b"]))): r for r in truth["pairs"]}
                need(len(exact) == 276 and len(body["matches"]) == 71, "independent_scan_denominator")
                for match in body["matches"]:
                    key = tuple(sorted(r["name"] for r in match["objects"]))
                    ref = exact[key]; q = ref["exact_squared_distance_m2"]
                    with localcontext() as ctx:
                        ctx.prec = 100
                        rounded = float((Decimal(q["numerator"])/Decimal(q["denominator"])).sqrt())
                    need(ref["matches_threshold"] and match["distance_m"] == rounded, "independent_scan_scalar")
        row.update(request=pin(request_path), response=pin(response_path), telemetry=trace, observe=observe)
        semantic[step] = compare.comparable(body, arm)
    return semantic


def close_readback(client, rec):
    if client.worker is None:
        if hasattr(client, "stderr"):
            client.stderr.close()
        return
    code = client.close()
    client.mark("close_readback_begin")
    raw = (client.folder / "CLOSE.json").read_bytes()
    rec["product_close"] = json.loads(raw)
    client.read_bytes["close_readback"] = [len(raw)]
    client.mark("close_readback_end")
    need(code == 0 and rec["product_close"]["method"] == "eof" and not client.reader.is_alive(), "normal_EOF")


def cell(folder, host, before, arm, plan, family):
    svc = api()[2]
    folder.mkdir()
    rec = dict(arm=arm, family=family, host_pid=host.pid, host=host.host, port=host.port,
               rows=[], errors=[], started_ns=NOW(), validation_outside_primary=True)
    started = NOW()
    client = client_class(svc)(folder / "client", host, plan["arms"][arm])
    try:
        client.launch(); client.open(family)
        rec.update(product_pid=client.server_pid, wrapper_pid=client.worker.pid, ready_ns=NOW())
        t = NOW(); rec["product_before"] = svc.transport.counters(client.server_pid); rec["resource_before_ns"] = NOW()-t
        client.mark("before_first_observe")
        for step in plan["cases"][family]["steps"]:
            row = client.observe(plan["cases"][family]["requests"][step])
            row.update(step=step, body_decoded_ns=NOW())
            rec["rows"].append(row)
        rec["last_reply_ns"] = rec["rows"][-1]["body_decoded_ns"]
        client.mark("last_business_decode")
        t = NOW(); rec["product_after"] = svc.transport.counters(client.server_pid); rec["resource_after_ns"] = NOW()-t
    except Exception:
        rec["errors"].append(dict(stage="business", traceback=traceback.format_exc()))
    finally:
        try:
            close_readback(client, rec)
        except Exception:
            rec["errors"].append(dict(stage="product_close", traceback=traceback.format_exc()))
    ended = NOW(); client.mark("client_end")
    rec.update(workflow_start_ns=started, workflow_end_ns=ended, workflow_ns=ended-started, lifecycle=client.lifecycle())
    if len(rec["rows"]) == len(plan["cases"][family]["steps"]):
        first = rec["rows"][0]["timing"]["started_ns"]
        rec.update(business_ns=rec["last_reply_ns"]-first, startup_discovery_ns=first-started,
                   through_scan_reply_ns=rec["last_reply_ns"]-started,
                   product_close_and_final_counter_ns=ended-rec["last_reply_ns"])
    if not rec["errors"]:
        try:
            rec["semantic"] = audit_rows(folder, rec, plan, before, family)
            for row in rec["rows"]:
                dump(folder / (row["step"] + ".json"), row)
        except Exception:
            rec["errors"].append(dict(stage="after_EOF_validation", traceback=traceback.format_exc()))
    rec["lifecycle_audit"] = validate_lifecycle(rec, folder / "client")
    rec.update(ended_ns=NOW(), valid=not rec["errors"] and len(rec["rows"]) == len(plan["cases"][family]["steps"]))
    dump(folder / "CELL.json", rec)
    print(family, folder.parent.name, arm, "business", rec["valid"], "OS_lifetime", rec["lifecycle_audit"]["status"], flush=True)
    return rec


def snapshot(host, folder, label, plan, family):
    s1, _, svc, _ = api()
    value = s1.loadsnap(host, label, folder)
    case = plan["cases"][family]
    need(s1.check_input(family, value, svc), "actual_source_geometry")
    need(value["frame"] == case["frame"] and value["subframe"] == case["subframe"] and value["scale"] == case["scale"], "frame_units")
    for name, expected in case["expected_snapshot"].items():
        need(all(binary(value["geometry"][name][key]) == binary(want) for key, want in expected.items()), "actual_native_arrays:"+name)
    return value


def group(folder, index, order, plan, window, family):
    _, gui, svc, _ = api()
    folder.mkdir()
    rec = dict(group=index, order=order, family=family, started_ns=NOW(), cells={}, errors=[])
    host = None
    try:
        host = gui.Owned(folder / "native", plan["cases"][family]["asset"], plan["support"], window)
        rec.update(host_pid=host.pid, port=host.port, gui_ready_ns=NOW())
        t = NOW(); before = snapshot(host, folder, "BEFORE", plan, family); rec["before_snapshot_ns"] = NOW()-t
        rec["host_before_business"] = svc.transport.counters(host.pid)
        for arm in order:
            rec["cells"][arm] = cell(folder / arm, host, before, arm, plan, family)
            need(rec["cells"][arm]["valid"], "invalid_cell_"+arm)
        rec["host_after_business"] = svc.transport.counters(host.pid)
        semantics = [rec["cells"][arm]["semantic"] for arm in order]
        need(all(v == semantics[0] for v in semantics), "same_host_full_public_parity")
        rec["same_host_full_public_parity"] = True
        t = NOW(); after = snapshot(host, folder, "AFTER", plan, family); rec["after_snapshot_ns"] = NOW()-t
        need(binary({k:v for k,v in before.items() if k != "resident"}) == binary({k:v for k,v in after.items() if k != "resident"}), "full_scene_preserved")
        rec["geometry_preserved"] = True
    except BaseException:
        rec["errors"].append(traceback.format_exc())
    finally:
        if host is not None:
            try:
                rec["gui_close"] = host.close()
                need(rec["gui_close"]["status"] == "pass" and rec["gui_close"]["process_reaped"] and rec["gui_close"]["forced"] is None, "normal_GUI_cleanup")
            except BaseException:
                rec["errors"].append("GUI close: " + traceback.format_exc())
    rec.update(ended_ns=NOW(), valid=not rec["errors"] and len(rec["cells"]) == len(order))
    rec["full_native_and_QA_lifecycle_ns"] = rec["ended_ns"]-rec["started_ns"]
    dump(folder / "GROUP.json", rec)
    return rec


def paired(groups, metric, family):
    arms = "ABF" if family == "G60" else "AF"
    out = dict(status="incomplete_or_unmeasured", expected=6, measured=0, gate=None)
    rows = []
    for group in groups:
        if not group["valid"]:
            continue
        values = {}
        for arm in arms:
            cell = group["cells"][arm]
            if metric == "process_ns":
                if cell["lifecycle_audit"]["status"] == "measured":
                    values[arm] = cell["lifecycle_audit"]["os_survival_ns"]
            else:
                values[arm] = cell[metric]
        if set(values) == set(arms):
            rows.append(dict(group=group["group"], order=group["order"], ns=values))
    out["measured"] = len(rows); out["rows"] = rows
    if len(groups) != 6 or len(rows) != 6:
        return out
    out.update(status="measured", median_ns={a: median(r["ns"][a] for r in rows) for a in arms}, pairs={})
    for candidate, baseline in (("F", "A"), ("F", "B"), ("B", "A")) if family == "G60" else (("F", "A"),):
        delta = [r["ns"][candidate]-r["ns"][baseline] for r in rows]
        relative = [Fraction(d, r["ns"][baseline]) for d, r in zip(delta, rows)]
        out["pairs"][candidate+"_vs_"+baseline] = dict(median_delta_ns=median(delta), median_relative_increase=float(median(relative)),
            median_saving=float(median(-v for v in relative)), faster=sum(d < 0 for d in delta), slower=sum(d > 0 for d in delta), equal=sum(d == 0 for d in delta))
    if family == "G60" and metric in ("business_ns", "process_ns"):
        a, b = out["pairs"]["F_vs_A"], out["pairs"]["F_vs_B"]
        out["gate"] = (a["median_saving"] >= .10 and a["faster"] >= 5 if metric == "business_ns" else a["median_saving"] > 0) and b["median_relative_increase"] <= .05
    if family == "B02" and metric == "business_ns":
        out["gate"] = out["pairs"]["F_vs_A"]["median_relative_increase"] <= .05
    return out


def preflight():
    plan = current(); svc = api()[2]
    folder = RAW / "preflight_001"; folder.mkdir()
    client = client_class(svc)(folder / "client", SimpleNamespace(host="127.0.0.1", port=9), plan["arms"]["F"])
    rec = dict(status="failed", plan=pin(PLAN), geometry_requests=0, Blender=0, errors=[])
    started = NOW()
    try:
        client.launch(); client.open("G60")
    except Exception:
        rec["errors"].append(traceback.format_exc())
    finally:
        try:
            close_readback(client, rec)
        except Exception:
            rec["errors"].append(traceback.format_exc())
    ended = NOW(); client.mark("client_end")
    rec.update(workflow_start_ns=started, workflow_end_ns=ended, workflow_ns=ended-started, lifecycle=client.lifecycle())
    rec["lifecycle_audit"] = validate_lifecycle(rec, folder / "client", business=False)
    if not rec["errors"] and rec["lifecycle_audit"]["status"] == "measured":
        rec["status"] = "pass"
    print(dump(folder / "RESULTS.json", rec), flush=True)
    return int(rec["status"] != "pass")


def run(window_path, family):
    plan = current(); window = read(window_path)
    need(window["cycle_id"] == CYCLE and window["status"] == "available" and window.get("token"), "exclusive_window")
    pre = read(RAW / "preflight_001/RESULTS.json")
    need(pre["status"] == "pass" and pre["plan"] == pin(PLAN), "same_source_preflight")
    out = RAW / family / "main_001"; out.mkdir(parents=True)
    dump(out / "WINDOW.json", window)
    start = NOW(); groups = []
    for index, order in enumerate(ORDERS[family], 1):
        record = group(out / f"G{index:02d}-{order}", index, order, plan, window, family)
        groups.append(record)
        if not record["valid"]:
            break
    end = NOW()
    result = dict(schema="m6-049-live-result-v1", status="complete" if len(groups) == 6 and all(g["valid"] for g in groups) else "failed_or_incomplete",
        family=family, plan=pin(PLAN), window=pin(window_path), preflight=pin(RAW / "preflight_001/RESULTS.json"),
        started_ns=start, ended_ns=end, complete_window_ns=end-start,
        groups=[dict(group=g["group"], order=g["order"], valid=g["valid"], receipt=pin(out / f"G{g['group']:02d}-{g['order']}" / "GROUP.json")) for g in groups],
        actual_hosts=len(groups), actual_services=sum(len(g["cells"]) for g in groups),
        actual_business_reads=sum(len(c["rows"]) for g in groups for c in g["cells"].values()),
        business=paired(groups, "business_ns", family), process_lifetime=paired(groups, "process_ns", family), client_full=paired(groups, "workflow_ns", family),
        full_GUI_lifecycles_ns=[g["full_native_and_QA_lifecycle_ns"] for g in groups],
        no_formal_retry=True, timings_describe_same_frozen_source=True)
    print(dump(out / "RESULTS.json", result), flush=True)
    return int(result["status"] != "complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "preflight", "run"))
    parser.add_argument("--family", choices=tuple(ORDERS))
    parser.add_argument("--window", type=Path)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
    else:
        raise SystemExit(preflight() if args.action == "preflight" else run(args.window, args.family))
