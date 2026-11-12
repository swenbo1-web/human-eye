"""Offline binding and timing audit of the six frozen consumer originals.

No product module is imported. Subprocesses are read-only Git queries only.
"""
from collections import Counter
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


OUT = Path(__file__).resolve().parent
BATCH = OUT.parents[1]
ROOT = BATCH.parents[1]
DELIVERY = "e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3"
PREPARATION = "bedcc827ec548e3afab816c0986db0c99eb42bb8"
PRODUCT = "c1cb2da32034e056a270384e691a2cde8dddbc0d"
SOURCE = "c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943"
ADMIN = Path("D:/hefe/verification/fixes/20261112_m4_surface_scan_consumer_quality_review")
SEAL_SHA = "1a205c053d7bfff76e427f83a73749bbb2a04d4ca040b92396254dd12b82942f"
PLAN_SHA = "21d3bb4a1a947a8debfe3db2c5e412359fae58ed6436e0979b6c558c2ac30393"
checks = []


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def read(path):
    return json.loads(path.read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def tree(commit):
    raw = subprocess.check_output(["git", "ls-tree", "-rz", commit], cwd=ROOT)
    return {path.decode(): meta.split()[2].decode()
            for entry in raw.split(b"\0") if entry
            for meta, path in [entry.split(b"\t", 1)]}


def request_projection(value):
    result = {k: v for k, v in value.items() if k not in ("id", "jsonrpc", "_meta")}
    if isinstance(result.get("params"), dict):
        result["params"] = {k: v for k, v in result["params"].items() if k != "_meta"}
    return result


def response_projection(value):
    return {k: v for k, v in value.items() if k not in ("id", "jsonrpc", "_meta")}


def normalized_snapshot(value):
    return {"unit_scale_m": value["unit_scale_m"], "objects": [
        {k: obj[k] for k in ("name", "vertices_local", "matrix_world", "faces")}
        for obj in value["objects"]]}


def main():
    seal_raw = (ADMIN / "QUALITY_SEAL.json").read_bytes()
    check(sha(seal_raw) == SEAL_SHA, "external quality seal SHA")
    seal = json.loads(seal_raw)
    check(sha(Path("D:/hefe/docs/M4_SURFACE_SCAN_CONSUMPTION_001_COST_PLAN.md").read_bytes()) == PLAN_SHA,
          "external cost plan SHA")
    check(seal["delivery_commit"] == DELIVERY and seal["product_commit"] == PRODUCT,
          "sealed delivery and product")
    check(seal["quality"]["complete_correct"] == 6, "sealed six complete-correct answers")
    sealed_answers = {row["anonymous_id"]: row for row in seal["answers"]}

    trees = {commit: tree(commit) for commit in (DELIVERY, PREPARATION, PRODUCT)}
    delivery_manifest = BATCH / "DELIVERY_MANIFEST.json"
    check(git_blob(delivery_manifest.read_bytes()) == trees[DELIVERY][delivery_manifest.relative_to(ROOT).as_posix()],
          "original delivery manifest bytes bound to Git")
    manifest = read(delivery_manifest)
    for row in manifest["files"]:
        path = ROOT / row["path"]
        raw = path.read_bytes()
        check(sha(raw) == row["sha256"] and len(raw) == row["bytes"], "delivery digest " + row["path"])
        check(git_blob(raw) == trees[DELIVERY][row["path"]], "delivery Git bytes " + row["path"])

    plan = read(BATCH / "PLAN.json")
    run = read(BATCH / "RUN_RESULT.json")
    check(sha((BATCH / "PLAN.json").read_bytes()) == read(BATCH / "FREEZE.json")["plan_sha256"]
          == read(BATCH / "GO.json")["plan_sha256"], "freeze GO plan identity")
    for name, expected in plan["dispatch_input_sha256"].items():
        raw = (BATCH / name).read_bytes()
        check(sha(raw) == expected, "dispatch input " + name)
        check(git_blob(raw) == trees[PREPARATION][(BATCH / name).relative_to(ROOT).as_posix()],
              "preparation Git input " + name)
    for name, expected in plan["external_input_sha256"].items():
        check(sha(Path(name).read_bytes()) == expected, "external input " + name)
    for name, expected in read(BATCH / "preflight/PROTECTED_BEFORE.json").items():
        check(sha(Path(name).read_bytes()) == expected, "protected input " + name)

    binding = read(BATCH / "preflight/SOURCE_BINDING.json")
    ready = read(BATCH / "installations/P_READY.json")
    install_receipt = read(Path(ready["receipt"]))
    wheel_path, = Path(install_receipt["bundle"]).glob("*.whl")
    check(sha(wheel_path.read_bytes()) == ready["wheel_sha256"], "wheel archive hash")
    sources = binding["source_manifest"]
    check(len(sources) == 138 and sources == sorted(sources, key=lambda row: row["path"]), "138 sorted source manifest")
    declared_roots = {"human_eye_hook.py", "human_eye_foveated_renderer.py", "native_3d_spatial_scratchpad.py",
                      "module_2_low_token_mcp_scene_bridge.py", "module_3_1_mcp_protocol_ipc_engine.py",
                      "module_3_2_vlm_grounding_closed_loop_agent.py", "module_3_3_closed_loop_control_engine.py"}
    enumerated = declared_roots | {p.relative_to(ROOT).as_posix() for package in ("human_eye_plugin", "human_eye_module1_operators")
                                  for p in (ROOT / package).glob("*.py")}
    check(enumerated == {row["path"] for row in sources}, "complete runtime source enumeration")
    with zipfile.ZipFile(wheel_path) as wheel:
        for row in sources:
            name = row["path"]
            raw = (ROOT / name).read_bytes()
            check(sha(raw) == row["sha256"], "source checkout " + name)
            check((Path(ready["install_root"]) / name).read_bytes() == raw, "source install " + name)
            check(wheel.read(name) == raw, "source wheel " + name)
            for commit in (PRODUCT, PREPARATION, DELIVERY):
                check(git_blob(raw) == trees[commit][name], "source Git " + commit[:8] + " " + name)
    digest_input = dict(base_version="9.7.2", implementation_revision="v26-surface-scan-pair-cache-20261112", files=sources)
    computed_source = sha(json.dumps(digest_input, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())
    check(computed_source == SOURCE == plan["candidate_source_sha256"] == ready["source_sha256"], "source aggregate")
    check(sha(Path(ready["entry"]).read_bytes()) == ready["launcher_sha256"], "installed launcher bytes")

    public = BATCH / "runtime/handoff_01/public"
    private = BATCH / "runtime/handoff_01/private"
    provenance = read(private / "PROVENANCE.json")
    public_files = {p.relative_to(public).as_posix(): sha(p.read_bytes()) for p in public.rglob("*") if p.is_file()}
    check(public_files == provenance["public_files_sha256"] and len(public_files) == 30, "30 public file originals")
    for name, expected in provenance["control_sha256"].items():
        check(sha((BATCH / name).read_bytes()) == expected
              and (private / "control" / name).read_bytes() == (BATCH / name).read_bytes(), "private control " + name)
    index = read(public / "INDEX.json")
    answers = {a["anonymous_id"]: a for a in index["answers"]}
    mapping = read(BATCH / "private/ANON_MAP.json")
    check(mapping["created_before_consumers"] and len(mapping["rows"]) == 6, "six frozen anonymous rows")
    check(sha((BATCH / "private/ANON_MAP.json").read_bytes()) == plan["private_anonymous_map_sha256"], "frozen anonymous map")
    check(set(answers) == set(sealed_answers) == {a["anonymous_id"] for a in mapping["rows"]}, "quality/map/public ID bijection")
    check([r["cell"] for r in plan["sequence"]] == [r["cell"] for r in run["records"]]
          == ["N1", "P1", "P2", "N2", "N3", "P3"], "actual six dispatch order")
    check(run["started_cells"] == run["maximum_consumers"] == 6 and run["all_planned_dispatched"]
          and run["no_replacements"] and run["stop"] is None, "six fixed denominator no replacements")
    baseline = normalized_snapshot(read(BATCH / "scoring/ACTUAL_SNAPSHOT.json"))
    common_native = read(BATCH / "schemas/COMMON_NATIVE.json")
    read_schema = read(BATCH / "schemas/P_PUBLIC_TOOLS.json")
    frozen_settings = read(BATCH / "preflight/CONSUMER_CONFIGURATION.json")["settings"]
    cell_rows, thread_ids, native_pids, owner_pids, runtime_pids = [], [], [], [], []
    counts = Counter()
    last_publication_end = run["batch_started_ns"]
    for slot, recorded in zip(plan["sequence"], run["records"], strict=True):
        cell = slot["cell"]
        folder = BATCH / "cells" / cell
        row = next(r for r in mapping["rows"] if r["cell"] == cell)
        anonymous = answers[row["anonymous_id"]]
        check(all(recorded[k] == slot[k] == row[k] for k in ("cell", "group", "round", "slot", "task")), cell + " slot map")
        consumer = read(folder / "CONSUMER.json")
        check(consumer == recorded["consumer"], cell + " recorded consumer equality")
        final_raw = (folder / "PUBLIC_FINAL.txt").read_bytes()
        check(final_raw == consumer["final"].encode() == (folder / "final.txt").read_bytes()
              == (public / anonymous["directory"] / anonymous["answer_file"]).read_bytes(), cell + " all final byte origins")
        check(sha(final_raw) == sealed_answers[row["anonymous_id"]]["answer_sha256"]
              == anonymous["answer_original_sha256"], cell + " quality seal final hash")
        original_files = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        with zipfile.ZipFile(private / "raw" / (row["anonymous_id"] + ".zip")) as archive:
            check(set(archive.namelist()) == set(original_files), cell + " raw archive file set")
            for name, raw in original_files.items():
                check(archive.read(name) == raw, cell + " raw archive bytes " + name)
        event_lines = (folder / "events.jsonl").read_bytes().splitlines()
        events = [json.loads(line) for line in event_lines]
        starts = [e for e in events if e["event"]["type"] == "thread.started"]
        check(len(starts) == 1 and starts[0]["event"]["thread_id"] == consumer["thread_id"], cell + " original fresh thread event")
        thread_ids.append(consumer["thread_id"])
        model_messages = [{"perf_ns": e["perf_ns"], "id": e["event"]["item"]["id"], "text": e["event"]["item"]["text"]}
                          for e in events if e["event"]["type"] == "item.completed"
                          and e["event"].get("item", {}).get("type") == "agent_message"]
        check(model_messages == consumer["all_public_messages"] and model_messages[-1]["text"].encode() == final_raw,
              cell + " private raw model messages and final")
        tool_events = [{"perf_ns": e["perf_ns"], **e["event"]} for e in events
                       if e["event"].get("item", {}).get("type") == "mcp_tool_call"]
        check(tool_events == consumer["public_events"], cell + " private tool events equality")
        completed = [e for e in tool_events if e["type"] == "item.completed"]
        check(completed == consumer["tool_calls"], cell + " completed tool attempts equality")
        evidence = read(public / anonymous["directory"] / anonymous["evidence_file"])
        projected_events = []
        for line, event in zip(event_lines, events, strict=True):
            item = event["event"].get("item", {})
            if item.get("type") == "mcp_tool_call" and event["event"]["type"] in ("item.started", "item.completed"):
                projected_events.append(dict(order=len(projected_events) + 1, phase=event["event"]["type"],
                    event={k: item[k] for k in ("type", "tool", "server", "arguments", "result", "error", "status", "command") if k in item},
                    source_sha256=sha((folder / "events.jsonl").read_bytes()), source_line_sha256=sha(line)))
        check(projected_events == evidence["public_tool_events"], cell + " exact public model event projection")
        attempts = sorted((folder / "owner").glob("tool_*"), key=lambda p: int(p.name.split("_")[1]))
        check(len(attempts) == len(evidence["owner_attempts"]) == len(completed), cell + " no discarded business attempts")
        for attempt, projected, event in zip(attempts, evidence["owner_attempts"], completed, strict=True):
            request = read(attempt / "REQUEST.json")
            check(request_projection(request) == projected["request"], cell + " public request projection " + attempt.name)
            check(event["item"]["tool"] == request["params"]["name"]
                  and event["item"]["arguments"] == request["params"]["arguments"], cell + " private model request " + attempt.name)
            responses = [p for p in (attempt / "RESPONSE.json", attempt / "ERROR_RESPONSE.json") if p.exists()]
            check(len(responses) == len(projected["responses"]) == 1, cell + " retained response count " + attempt.name)
            response = read(responses[0])
            check(response_projection(response) == projected["responses"][0]["value"], cell + " public response projection " + attempt.name)
            owner_result = response["result"]
            cli_projection = {"content": owner_result["content"],
                              "structured_content": owner_result.get("structuredContent")}
            check(event["item"]["result"] == cli_projection and event["item"]["error"] is None,
                  cell + " exact CLI business content projection " + attempt.name)
            check((event["item"]["status"] == "failed") == bool(owner_result.get("isError")),
                  cell + " MCP isError to CLI failed status " + attempt.name)
            counts["CLI_projection_drops_isError"] += int("isError" in owner_result)
            counts["owner_business_errors_retained_in_content"] += int(owner_result.get("isError") is True)
            counts["business_attempts"] += 1

        cfg = read(folder / "ACTOR_CONFIG.json")
        launch = read(folder / "ACTOR_LAUNCH.json")
        owner = read(folder / "owner/IDENTITY.json")
        native = read(folder / "owner/native/SESSION.json")
        native_config = read(folder / "owner/native/CONFIG.json")
        native_ready = read(folder / "owner/native/READY.json")
        close = read(folder / "owner/CLOSE.json")
        finish = read(folder / "OWNER_FINISH.json")
        check(cfg["group"] == owner["group"] == native["condition"] == slot["group"], cell + " actual loaded group")
        check(owner["asset_sha256"] == native["asset_sha256"] == cfg["asset_sha256"] == plan["inputs"]["scene_sha256"]
              == sha(Path(native["asset"]).read_bytes()) == sha(Path(native["asset_copy"]).read_bytes()), cell + " actual private asset")
        check(Path(native["workspace"]) == folder / "owner/native" and native_config["asset_copy"] == native["asset_copy"],
              cell + " isolated native workspace")
        check(sha(Path(native["blender"]).read_bytes()) == native["blender_sha256"], cell + " current Blender binary binding")
        check(native_ready["pid"] == native["pid"] and native_ready["helper_sha256"] == native["helper_sha256"], cell + " native ready identity")
        native_pids.append(native["pid"])
        owner_pids.append(owner["actor_pid"])
        check(owner["actor_parent_pid"] == launch["pid"] and finish["actor_pid"] == launch["pid"], cell + " owned actor parent/reap binding")
        for label in ("INITIAL", "FINAL"):
            snapshot = read(folder / "owner" / (label + ".json"))
            receipt = read(folder / "owner" / (label + ".json.receipt.json"))
            check(snapshot == normalized_snapshot(snapshot) == baseline, cell + " " + label + " complete mesh snapshot")
            check(json.loads(receipt["response"]["result"]["result"]) == snapshot, cell + " " + label + " actual host response")
            check(receipt["source_file_unchanged"] and receipt["protected_files_unchanged"], cell + " " + label + " source protections")
            counts["snapshots"] += 1
        bridges = list((folder / "attachments").glob("bridge_*"))
        check(len(bridges) == 1, cell + " one recorded thin client")
        check(not (bridges[0] / "EXIT.json").exists(), cell + " actual thin EXIT receipt absent")
        list_replies = []
        bridge_business = []
        for tx in sorted(bridges[0].glob("*/TX.bin")):
            message = json.loads(tx.read_bytes())
            if message.get("method") == "tools/list":
                list_replies.append(read(tx.with_name("RX.bin")))
            if message.get("method") == "tools/call":
                bridge_business.append((message, read(tx.with_name("RX.bin"))))
        check(len(list_replies) == 1, cell + " one actual raw tools-list reply")
        check(len(bridge_business) == len(attempts), cell + " actual bridge business denominator")
        for attempt, (request, response) in zip(attempts, bridge_business, strict=True):
            check(request == read(attempt / "REQUEST.json"), cell + " actual bridge request " + attempt.name)
            response_path = next(p for p in (attempt / "RESPONSE.json", attempt / "ERROR_RESPONSE.json") if p.exists())
            check(response == read(response_path), cell + " actual bridge response " + attempt.name)
        tools = list_replies[0]["result"]["tools"]
        check(tools == [common_native] + ([] if slot["group"] == "N" else read_schema), cell + " full exposed tool declarations")
        check(consumer["expected_tool_names"] == owner["exposed_tool_names"] == [t["name"] for t in tools], cell + " tool exposure agreement")
        check(cfg["read_schemas"] == ([] if slot["group"] == "N" else read_schema), cell + " frozen read schema")
        check(consumer["input_sha256"] == plan["inputs"]["prompt_sha256"] and consumer["input_text_bytes"] == len((BATCH / plan["inputs"]["prompt"]).read_bytes()),
              cell + " common submitted text")
        argv = consumer["argv"]
        settings = [argv[i + 1] for i, v in enumerate(argv[:-1]) if v == "-c"]
        for key, value in frozen_settings.items():
            if isinstance(value, (str, int, bool)):
                check(key + "=" + json.dumps(value, ensure_ascii=False, separators=(",", ":")) in settings,
                      cell + " CLI frozen setting " + key)
        for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral", "--strict-config"):
            check(flag in argv, cell + " CLI " + flag)
        check(consumer["model"] == "gpt-6.1-sol" and consumer["requested_effort"] == "medium"
              and consumer["resolved_effort"] is None and consumer.get("resolved_model") is None,
              cell + " requested/resolved distinction")
        check(consumer["public_image_count"] == consumer["input_image_count"] == 0 and close["zero_new_images_budget_met"], cell + " image scope")
        check(consumer["process_reaped"] and consumer["exit_code"] == 0 and finish["confirmed"]
              and finish["exit_code"] == 0 and finish["close"] == close == recorded["finish"]["close"], cell + " retained owner/consumer closure")
        check(close["native_close"]["process_reaped"] and close["native_close"]["exit_code"] == 0
              and close["worker_closed"]["pid"] == native["pid"] and close["geometry_unchanged"] and close["asset_unchanged"], cell + " native closure/readback")
        check(consumer["bridge_cleanup"]["confirmed"] is None and consumer["bridge_cleanup"]["receipt_status"] == "unknown"
              and consumer["bridge_cleanup"]["missing_exit_count"] == 1, cell + " thin-client EXIT remains unknown")
        check(not owner["private_geometry_warmup"], cell + " declared no private geometry warmup")
        cache_first = None
        if slot["group"] == "N":
            check(owner["runtime_identity"] is None and cfg["entry"] is None and not (folder / "owner/plugin").exists()
                  and close["plugin_close"] is None and close["product_runtime_exit"] is None, cell + " native only no product")
        else:
            identity = owner["runtime_identity"]
            check(identity["source_sha256"] == SOURCE and identity["source_kind"] == "installed_distribution"
                  and identity["distribution_version"] == ready["version"] and identity["source_file_count"] == 138, cell + " actual product identity record")
            proof = read(folder / "owner/PRODUCT_RUNTIME_PROOF.json")
            start = read(folder / "owner/plugin/START.json")
            product_rpc = read(folder / "owner/plugin/RPC.json")
            pre_consumer_rpc = [r for r in product_rpc["requests"] if r["started_ns"] < consumer["started_ns"]]
            check([r["method"] for r in pre_consumer_rpc] == ["initialize", "notifications/initialized", "tools/list", "ping"],
                  cell + " startup product RPC is metadata only")
            check(proof["confirmed"] and proof["runtime_pid"] != proof["launcher_pid"] and proof["launcher_pid"] == start["launcher_pid"], cell + " actual owned runtime")
            check(proof["proved_ns"] < consumer["started_ns"] and native["started_ns"] < start["started_ns"] < consumer["started_ns"],
                  cell + " native product proof precede model")
            runtime_pids.append(proof["runtime_pid"])
            check(close["plugin_close"]["confirmed"] and close["product_runtime_exit"]["confirmed"] and close["product_runtime_exit"]["handle_closed"], cell + " product closure")
            audit = [json.loads(line) for line in (folder / "owner/audit.jsonl").read_bytes().splitlines()]
            observed = [a for a in audit if a["event"] == "observe"]
            work = observed[0]["task_work"]
            cache_first = {k: work[k] for k in ("kernel_calls", "pair_calls", "cache_hits", "continuation_hits", "candidate_pairs", "measurement_cache_before")}
            check(work["measurement_cache_before"]["measurement_entries"] == 0 and work["cache_hits"] == 0
                  and work["pair_calls"] == work["candidate_pairs"] == 112, cell + " first scan cold measurement cache")
        timing = read(folder / "CELL_FINAL_TIMING.json")
        publication = read(folder / "CELL_TIMING_PUBLICATION.json")
        started = recorded["cell_started_ns"]
        check(started == launch["cell_started_ns"] == timing["cell_started_ns"], cell + " original outer start")
        check(last_publication_end <= started <= launch["prepare_started_ns"] <= native["started_ns"] < consumer["started_ns"]
              <= consumer["popen_ns"] <= consumer["prompt_submitted_ns"] < consumer["final_received_ns"]
              <= consumer["turn_completed_ns"] <= consumer["process_exit_ns"] <= consumer["cleanup_end_ns"]
              <= close["ended_ns"] <= recorded["cell_ended_ns"] <= timing["business_receipts_closed_ns"]
              <= publication["timing_receipt_publication_started_ns"] <= publication["timing_receipt_publication_closed_ns"], cell + " entire monotonic time chain")
        check(started + 570 * 10**9 == recorded["worker_deadline_ns"] == launch["worker_deadline_ns"]
              == native["deadline_ns"] == cfg["worker_deadline_ns"], cell + " single outer deadline")
        check(timing["full_cell_wall_ns"] == timing["business_receipts_closed_ns"] - started
              and timing["within_570s"] == (timing["full_cell_wall_ns"] < 570 * 10**9), cell + " authoritative full wall equation")
        check(recorded["full_cell_wall_ns"] == consumer["total_task_wall_ns"] == recorded["cell_ended_ns"] - started,
              cell + " original prefix equation")
        check(publication["business_receipts_closed_ns"] == timing["business_receipts_closed_ns"]
              and publication["timing_receipt_publication_ns"] == publication["timing_receipt_publication_closed_ns"] - publication["timing_receipt_publication_started_ns"],
              cell + " timing receipt publication separate")
        check(close["worker_closed"]["closed_ns"] <= close["ended_ns"], cell + " worker closed before business end")
        if slot["group"] == "P":
            check(close["plugin_close"]["ended_ns"] <= close["ended_ns"]
                  and close["product_runtime_exit"]["observed_ns"] <= close["ended_ns"], cell + " product closed before business end")
        last_publication_end = publication["timing_receipt_publication_closed_ns"]
        cell_rows.append(dict(cell=cell, anonymous_id=row["anonymous_id"], group=slot["group"], thread_id=consumer["thread_id"],
            native_pid=native["pid"], owner_pid=owner["actor_pid"], actual_product_started=slot["group"] == "P",
            tool_attempts=len(attempts), final_sha256=sha(final_raw), private_archive_files=len(original_files),
            provider_cached_input_tokens=consumer["usage"].get("cached_input_tokens"), initial_measurement_cache=cache_first,
            bridge_exit=consumer["bridge_cleanup"], resolved_model=None, resolved_effort=None,
            cell_started_ns=started, business_receipts_closed_ns=timing["business_receipts_closed_ns"],
            full_cell_wall_ns=timing["full_cell_wall_ns"], prefix_wall_ns=recorded["full_cell_wall_ns"],
            timing_publication_ns=publication["timing_receipt_publication_ns"]))
    check(len(set(thread_ids)) == len(set(native_pids)) == len(set(owner_pids)) == 6 and len(set(runtime_pids)) == 3,
          "distinct six model threads six backends six owners three product runtimes")
    check(counts["business_attempts"] == 26 and counts["snapshots"] == 12, "complete original business/snapshot denominator")
    check(last_publication_end <= run["batch_ended_ns"], "all cells close before final batch boundary")
    # Frozen source explains the otherwise unobservable file-close ordering.
    driver_text = (BATCH / "runtime/driver.py").read_text(encoding="utf8")
    driver_ast = ast.parse(driver_text)
    function = next(n for n in driver_ast.body if isinstance(n, ast.FunctionDef) and n.name == "close_cell_accounting")
    code = ast.get_source_segment(driver_text, function)
    check(code.index("save(HERE/'RUN_RESULT.json'") < code.index("business_closed_ns = time.perf_counter_ns()")
          < code.index("save(folder/'CELL_FINAL_TIMING.json'"), "frozen code business receipt close before end sampling")
    save_function = next(n for n in driver_ast.body if isinstance(n, ast.FunctionDef) and n.name == "save")
    check("Path(p).write_text(" in ast.get_source_segment(driver_text, save_function), "frozen save uses standard Path.write_text close")
    result = dict(schema="m4_surface_scan_cost_binding_v1", status="pass", check_count=len(checks),
        verification_script_sha256=sha(Path(__file__).read_bytes()),
        execution_scope="offline read-only originals; Git queries only; no Blender/model/business API calls",
        quality_seal_sha256=SEAL_SHA, cost_plan_sha256=PLAN_SHA, delivery_commit=DELIVERY, preparation_commit=PREPARATION,
        product_commit=PRODUCT, source_sha256=SOURCE, source_count=138, original_delivery_files=len(manifest["files"]) + 1,
        public_files=30, cells=cell_rows, business_attempts=counts["business_attempts"], snapshots=counts["snapshots"],
        independent_rescoring_performed=False, thin_client_exit_unknown_count=6,
        CLI_projection_drops_isError=counts["CLI_projection_drops_isError"],
        owner_business_errors_retained_in_content=counts["owner_business_errors_retained_in_content"],
        cold_scope="fresh consumer thread IDs and separately owned new Blender/product processes; first product scan has empty measurement cache",
        provider_internal_cache_state="uncontrolled and unknown; recorded cached_input_tokens retained, no provider cold-cache claim",
        limitations=["Recorded runtime identities and current bytes do not replay historical process memory.",
            "Initial/final complete mesh readbacks do not detect all reverted transient edits.",
            "Thin-client EXIT receipts remain unknown despite separately confirmed owner/backend closure.",
            "Requested model/effort and tool metadata do not attest actual resolved model version/effort.",
            "Outer receipt closure is buffered write/close; fsync durability is unmeasured.",
            "Timing publication receipt's own write/close and caller/preparation gaps remain outside their stated intervals."],
        checked_labels=checks)
    (OUT / "BINDING_RESULT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("cells", "checked_labels")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
