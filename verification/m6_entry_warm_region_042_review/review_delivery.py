"""Re-score the pinned 042 delivery from original inputs, clocks and protocol messages."""

import hashlib
import json
import runpy
import subprocess
from pathlib import Path
from statistics import median


HERE = Path(__file__).resolve().parent
RUN = Path("D:/HumanEye/runs/M6-042-ENTRY-WARM-REGION")
PRIOR = Path("D:/HumanEye/runs/M6-041-KERNEL-HOOK/delivery")
TERMINAL = Path("D:/he_m1_m2_source_region_scoped_measurement_001/slots/YB/initial_capture/TERMINAL_SOURCE.json")
ASSET = TERMINAL.parents[1] / "native/input.blend"
AUTHOR = Path("C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe")
COMMIT = "74a8e9f7a1194e82afed4fb5bfd92557315acf01"
PARENT = "68858e77740ee72ece80d3f10acb42dc692d59a5"
RAW_HASH = "c8cf1a2cf9dddabbe6a1f7e1b4749fe150979d5e1ca8151fb729de6fdc3c6650"
GEOM = runpy.run_path(str(HERE / "geometry_oracle.py"))
ORDERS = (("AB", "BA", "AB", "BA"), ("BA", "AB", "BA", "AB"), ("BA", "AB", "AB", "BA"))
ARM = {"A": "032", "B": "r3"}


def need(ok, why):
    if not ok:
        raise ValueError(why)


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_equal(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def verify_archive():
    manifest = RUN / "RAW_EVIDENCE.json"
    need(digest(manifest) == RAW_HASH, "raw evidence index SHA")
    doc = read(manifest)
    names = set()
    total = 0
    for record in doc["files"]:
        rel = record["path"]
        path = (RUN / rel).resolve()
        need(path.is_relative_to(RUN.resolve()) and rel not in names, "evidence member path")
        names.add(rel)
        need(path.stat().st_size == record["bytes"] and digest(path) == record["sha256"], rel)
        total += path.stat().st_size
    need(total == doc["bytes"] and len(names) == doc["count"] == 1703, "raw totals")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(AUTHOR), *args])
    need(git("rev-parse", COMMIT + "^").decode().strip() == PARENT, "delivery ancestry")
    changes = git("diff-tree", "--no-commit-id", "-r", "--name-status", "-z", PARENT, COMMIT).split(b"\0")[:-1]
    need(all(x == b"A" for x in changes[::2]), "change to old evidence")
    for name in changes[1::2]:
        rel = name.decode()
        need(rel.startswith("verification/m6_entry_warm_region_042/"), "unexpected delivery directory")
        need(git("show", COMMIT + ":" + rel) == (AUTHOR / rel).read_bytes(), rel)
    return {"commit": COMMIT, "git_members": len(changes)//2, "raw_members": len(names),
            "raw_bytes": total, "raw_manifest_sha256": RAW_HASH}


def snapshot(host, phase):
    receipt = read(host / (phase + "_RPC.json"))
    native = read(Path(receipt["rx"]["path"]))
    need(native == receipt["response"] and native["status"] == "success", "snapshot RPC")
    prefix, payload = native["result"]["result"].strip().split(":", 1)
    value = json.loads(payload)
    need(prefix == "M6_036_SNAPSHOT" and value == read(host / (phase + ".json")), "native snapshot")
    need(value["pid"] == receipt["endpoint"]["pid"] and value["main_thread"] and not value["background"],
         "ordinary Blender host identity")
    return value, receipt["endpoint"]


def score_live(truth):
    root = RUN / "live/main"
    pins = read(PRIOR / "install/PINS.json")
    prior_config = read(PRIOR / "s1/warm_diagnostic/PLAN.json")
    gui_pids, process_pids, trace_ids = set(), set(), set()
    previous_end = 0
    blocks = []
    all_geometry = []
    for host_index, schedule in enumerate(ORDERS, start=1):
        host = root / f"H{host_index}"
        before, endpoint = snapshot(host, "BEFORE")
        after, endpoint_after = snapshot(host, "AFTER")
        meta = read(host / "HOST.json")
        need(endpoint_after == endpoint and before["geometry"] == after["geometry"]
             and digest(Path(before["asset"])) == truth["asset_sha256"], "native geometry/source")
        for key in ("pid", "frame", "subframe", "scale", "scene", "layer", "asset"):
            need(before[key] == after[key], "source frame changed")
        need((before["frame"], before["subframe"], before["scale"]) == (1,0,1), "frame and units")
        need(meta["pid"] == endpoint["pid"] and previous_end <= meta["start_ns"], "host order or pid")
        gui_pids.add(meta["pid"])
        last_cell = meta["start_ns"]
        for number, order in enumerate(schedule, start=1):
            measured = {}
            for letter in order:
                arm = ARM[letter]
                cell_dir = host / f"H{host_index}-P{number}-{arm}"
                cell = read(cell_dir / "CELL.json")
                client = cell_dir / "client"
                launch, boot, close = (read(client / filename) for filename in ("LAUNCH.json","STARTUP.json","CLOSE.json"))
                build = prior_config["arm_sources"][arm]["source_sha256"]
                need(build == pins["identities"][arm]["source_sha256"]
                     and launch["command"][:4] == prior_config["arm_sources"][arm]["command_prefix"],
                     "pinned executable path and original source identity")
                cfg = read(client / "CONFIG.json")["blender"]
                need((cfg["host"],cfg["port"]) == (endpoint["host"],endpoint["port"]), "product/host routing")
                need(cell["arm"] == arm and cell["host_pid"] == meta["pid"] and
                     cell["product_pid"] == boot["actual_pid"] and not cell["errors"], "cell binding")
                need(last_cell <= cell["start_ns"] < cell["ready_ns"] < cell["end_ns"] <= meta["end_ns"], "order")
                last_cell = cell["end_ns"]
                process_pids.update((cell["product_pid"],launch["popen_pid"]))
                logs = [l["trace"] for l in lines(client / "AUDIT.jsonl") if l.get("event") == "request_trace"]
                need([r["step"] for r in cell["rows"]] == ["first_high","warm_high"], "first/warm order")
                same_params = None
                clock = cell["ready_ns"]
                for idx, row in enumerate(cell["rows"], start=4):
                    rid = f"{idx:03}"
                    tx, rx = client / (rid + ".TX.bin"), client / (rid + ".RX.bin")
                    req, resp = read(tx), read(rx)
                    need(req["method"] == "tools/call" and req["id"] == resp["id"] == rid, "wire association")
                    need(row["request"]["sha256"] == digest(tx) and row["response"]["sha256"] == digest(rx), "wire hash")
                    args = req["params"]["arguments"]
                    need(req["params"]["name"] == "human_eye_scene_observe" and args["include_image"] is False
                         and args["query"]["mode"] == "source_region_measurement" and
                         args["query"]["region"]["object"]["name"] == truth["target_name"] and
                         args["query"]["reference"]["name"] == truth["reference_name"] and
                         json_equal(args["query"]["region"]["world_box_m"],truth["expected"]["world_box_m"]) and
                         args["query"]["requested_facts"] == ["surface_proximity"], "business request")
                    if same_params is not None:
                        need(json_equal(same_params, req["params"]), "changed input for repeated read")
                    same_params = req["params"]
                    GEOM["verify_response"](rx, truth)
                    value = json.loads(resp["result"]["content"][0]["text"])
                    need(json_equal(value, row["result"]), "business decode")
                    for role in ("region_object","reference_object"):
                        need(value[role]["instance_id"] == before["geometry"][value[role]["name"]]["instance"], "source instance")
                    timing = row["timing"]
                    need(clock <= timing["started_ns"] <= timing["closed_ns"] <= row["end_ns"] <= cell["end_ns"], "business clocks")
                    clock = row["end_ns"]
                    elapsed = row["end_ns"] - timing["started_ns"]
                    need(elapsed == row["business_ns"] and elapsed > 0, "complete business window")
                    traces = [t for t in logs if t["annotations"].get("mcp_request_id") == rid]
                    need(len(traces) == 1, "unique process trace")
                    t = traces[0]
                    need(t["pid"] == cell["product_pid"] and t["annotations"]["build_id"] == "sha256:" + build and
                         t["annotations"]["delivery"] == "stdio_write_completed" and t["trace_id"] not in trace_ids,
                         "running build, request and real delivery")
                    trace_ids.add(t["trace_id"])
                    capture, = [s for s in t["spans"] if s["name"] == "host.capture_source_region_pair"]
                    cap = capture["duration_ns"]
                    need(0 < cap <= elapsed, "capture span")
                    all_geometry.append((host_index,number,arm,rid))
                    if rid == "005":
                        measured[arm] = (elapsed,cap)
                need(close["method"] == "eof" and close["exit_code"] == 0, "product EOF")
            a, b = measured["032"][0], measured["r3"][0]
            ac, bc = measured["032"][1], measured["r3"][1]
            blocks.append({"host":host_index,"pair":number,"order":order,"base_ms":a/1e6,"r3_ms":b/1e6,
                           "delta_ms":(b-a)/1e6,"pct":100*(b/a-1),"capture_delta_ms":(bc-ac)/1e6,
                           "remainder_delta_ms":((b-bc)-(a-ac))/1e6})
        end = meta["close"]
        need(end["process_reaped"] and end["exit_code"] == 0 and end["forced"] is None and
             end["GUI_close_callback"]["stopped"] and not end["released_port"]["any_listener"], "GUI cleanup")
        previous_end = meta["end_ns"]
    closure = read(RUN / "live/POST_CLOSE.json")
    need(gui_pids | process_pids == set(closure["known_owned_pids"]) and not closure["still_present"], "owned PID table")
    need(len(all_geometry) == len(trace_ids) == 48 and len(gui_pids) == 3 and len(process_pids) == 48, "live denominator")
    host_medians = [{"host":h,"delta_ms":median(b["delta_ms"] for b in blocks if b["host"]==h),
                     "pct":median(b["pct"] for b in blocks if b["host"]==h)} for h in range(1,4)]
    agg = {k:median(b[k] for b in blocks) for k in ("delta_ms","pct","capture_delta_ms","remainder_delta_ms")}
    gate = agg["delta_ms"] > 5 and agg["pct"] > 5
    return {"blocks":blocks,"median":agg,"by_host":host_medians, "r3_faster_pairs":sum(b["delta_ms"] < 0 for b in blocks),
            "geometry_and_wire_traces":len(trace_ids),"cleaned_pids":len(gui_pids | process_pids),
            "pooled_regression":gate,"stable_regression":gate and sum(h["delta_ms"]>0 for h in host_medians)>=2}


def score_replay(truth):
    root = RUN / "replay"
    capture = read(root / "capture_01/CAPTURE.json")
    source = read(TERMINAL)["objects"]
    region, ref = capture["region"], capture["reference"]
    mesh, ref_mesh = (obj["evaluated"] for obj in source)
    box = truth["expected"]["world_box_m"]
    inside = [all(l<=x<=h for x,l,h in zip(v,box["min"],box["max"],strict=True)) for v in mesh["vertices_world_m"]]
    selected = [i for i,row in enumerate(mesh["triangles"]) if all(inside[j] for j in row)]
    need(selected == region["source_triangle_indices"], "restored native rows")
    vertices = region["source_vertex_indices"]
    faces = [mesh["triangles"][i] for i in selected]
    need(set(vertices) == {j for f in faces for j in f} and len(vertices)==len(set(vertices)), "vertex mapping")
    need([[vertices[j] for j in f] for f in region["faces"]] == faces == region["source_triangle_vertices"], "native triangles")
    need(json_equal(region["vertices"], [mesh["vertices_world_m"][j] for j in vertices]) and
         json_equal(ref["vertices"],ref_mesh["vertices_world_m"]) and ref["faces"] == ref_mesh["triangles"], "captured coordinates")
    plan = read(root / "PLAN_02.json")
    need(plan["capture"]["sha256"] == digest(root / "capture_01/CAPTURE.json"), "common packet hash")
    counts, pairs, last_end = {}, [], 0
    for group in range(1,8):
        values = {}
        for arm in ("032","r3") if group%2 else ("r3","032"):
            folder = root / "paired_01" / f"{group:02}_{arm}"
            execution = read(folder / "EXECUTION.json")
            need(execution["returncode"] == 0 and last_end <= execution["started_ns"] < execution["closed_ns"], "replay order")
            last_end = execution["closed_ns"]
            result = read(folder / "RESULT.json")
            need(result["arm"] == arm and result["group"] == group and result["native_calls"] == 0 and
                 result["frozen_packet_reads"] == 4 and result["plan"]["sha256"] == digest(root/"PLAN_02.json"), "replay identity")
            values[arm] = {}
            for phase in ("plain","substages"):
                for label in ("first","repeat"):
                    row = read(folder / f"{phase}_{label}.json")
                    need(all(json_equal(row["public"][k],v) for k,v in truth["expected"].items()), "replay geometry")
                    time = row["timing_ns"]
                    for key, interval in row["stage_intervals"].items():
                        need(interval["closed_ns"]-interval["started_ns"] == interval["elapsed_ns"] == time[key], "stage clock")
                    need(time["replay_pipeline_ns"] == sum(time[k] for k in ("measure_service_call_ns","projection_ns","content_encode_ns","wire_encode_ns")), "pipeline timing")
                    work = row["work"]["task_query"]
                    need(work["surface_pair_count"] == 1 and work["surface_pair_cache_hit"] is False, "real per-call work")
                    measures = {k:work["surface_work"][k] for k in ("narrow_phase_pairs","node_pair_visits","leaf_pair_visits","work_units")}
                    need(counts.setdefault(arm,measures) == measures, "changing replay work")
                    if phase == "substages":
                        inner = [v["closed_ns"]-v["started_ns"] for v in row["observer_intervals"] if v["name"]=="measure_surface_proximity"]
                        need(len(inner) == 1 and inner[0] == time["solver_ns"], "solver timing")
                    values[arm][phase,label] = time
        a, b = (values[arm]["plain","repeat"] for arm in ("032","r3"))
        sa, sb = (values[arm]["substages","repeat"] for arm in ("032","r3"))
        pairs.append({"group":group,"pipeline_delta_ms":(b["replay_pipeline_ns"]-a["replay_pipeline_ns"])/1e6,
                      "pipeline_pct":100*(b["replay_pipeline_ns"]/a["replay_pipeline_ns"]-1),
                      "measurement_delta_ms":(b["task_measurement"]-a["task_measurement"])/1e6,
                      "solver_observed_delta_ms":(sb["solver_ns"]-sa["solver_ns"])/1e6})
    return {"public_results":56,"replay_pairs":pairs,"median":{k:median(b[k] for b in pairs) for k in pairs[0] if k!="group"},
            "repeat_slower_pairs":sum(b["pipeline_delta_ms"]>0 for b in pairs),"work_per_call":counts}


def score_entry_discovery():
    records = []
    hashes = {"H0":set(), "H1":set()}
    for binary in ("desktop","standalone"):
        for arm in hashes:
            p = RUN / "entry" / f"trust_{arm}_{binary}_002"
            tx, rx = lines(p/"TX.bin"), lines(p/"RX.bin")
            need([m["method"] for m in tx] == ["initialize","initialized","hooks/list"], "entry lifecycle")
            run_config = RUN / "entry" / f"trust_{arm}_desktop_002"
            init = next(m["result"] for m in rx if m.get("id")==1)
            need(Path(init["codexHome"]) == run_config/"codex_home", "same configured home across host builds")
            result = next(m["result"] for m in rx if m.get("id")==2)
            cwd, = result["data"]
            hook, = cwd["hooks"]
            need(Path(cwd["cwd"]) == run_config/"workspace" and hook["source"]=="user" and
                 Path(hook["sourcePath"]) == run_config/"codex_home/hooks.json", "actual source layer")
            need(hook["trustStatus"]=="untrusted" and hook["enabled"] and not hook["isManaged"], "trust status")
            definition = read(run_config/"codex_home/hooks.json")
            need(list(definition["hooks"]) == ["UserPromptSubmit"] and
                 definition["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"] == hook["command"], "exact registration")
            warnings = [m["params"]["summary"] for m in rx if m.get("method") == "configWarning"]
            need(any("until the project is trusted" in w and str(run_config/"workspace") in w for w in warnings),
                 "native project-layer warning with matching workspace")
            need(read(run_config/"connector.json")["blender"]["port"] == 9, "preflight connector")
            cleanup = read(p/"RESULT.json")["cleanup"]
            need(cleanup["readers_joined"] and cleanup["accounting"]["active_processes"] == 0, "discovery cleanup")
            identity = next(m["result"]["userAgent"] for m in rx if m.get("id")==1)
            hashes[arm].add(hook["currentHash"])
            records.append({"binary":binary,"arm":arm,"user_agent":identity,"hash":hook["currentHash"],
                            "source":"user","trust":hook["trustStatus"],"events":["UserPromptSubmit"]})
    need(all(len(x)==1 for x in hashes.values()) and hashes["H0"] != hashes["H1"], "arm identities")
    return {"metadata_exchanges":records,"actual_turns_in_these_records":0,"real_automatic_dispatch":"not_run",
            "review_finding":"Only the user-layer prompt-only preflight was discovered. Its connector points at port 9. Final G60 and PostToolUse definitions require a separate preparation artifact before native review."}


if __name__ == "__main__":
    archive = verify_archive()
    ref = GEOM["exact_reference"](TERMINAL, ASSET)
    print(json.dumps({"archive":archive, "live":score_live(ref), "replay":score_replay(ref),
                      "entry_initial":score_entry_discovery()}, indent=2))
