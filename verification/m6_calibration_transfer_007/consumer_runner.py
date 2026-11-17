"""One image-conditioned Pro consumer using the frozen CLI transport."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
CONSUMER_CWD = HERE.parents[1]
sys.path.insert(0, str(HERE))
from image_inputs import image_inputs
from consumer_bridge import public_value, verify_cli_image_event, verify_image_response
LEGACY = HERE.parent / "plugin_version_llm_ab_001/run_consumers.py"
spec = importlib.util.spec_from_file_location("_refine_pro_helpers", LEGACY)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
EXE = legacy.EXE
USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "total_tokens", "reasoning_tokens", "reasoning_output_tokens")


def read(path):
    return json.loads(Path(path).read_bytes())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".next")
    temporary.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    os.replace(temporary, path)


def identity(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def argv_for(case, route, folder, config):
    python = Path(config.get("python_executable", HERE.parent / "m6_shape_train_001/private/venv/Scripts/python.exe"))
    stage = folder.parent.parent.name
    task_id = read(case / "task.json")["task_id"]
    session = HERE / "private/sessions" / (stage + "_" + task_id + "_" + route)
    if not (session / "session.json").exists():
        raise ValueError("isolated_edit_session_not_prepared")
    settings = legacy.settings()
    settings.update(model=config["model"], model_reasoning_effort=config["reasoning_effort"])
    tools = ["images", "execute_python", "submit_edit", "state", "save_readback"] + (["focus", "resolve_ref"] if route == "facts" else [])
    settings["mcp_servers.task_geometry"] = dict(command=str(python), args=["-I", "-B", "-X", "utf8", str(HERE / "consumer_bridge.py"),
        "--case", str(case), "--session", str(session), "--route", route, "--audit", str(folder / "bridge"),
        "--max-tool-calls", str(config["max_tool_calls"]), "--python-timeout-s", str(config.get("python_timeout_s", 45)),
        "--python-output-chars", str(config.get("python_output_chars", 5000)), "--fact-output-chars", str(config.get("fact_output_chars", 18000))],
        cwd=str(CONSUMER_CWD), required=True, startup_timeout_sec=90, tool_timeout_sec=360, enabled_tools=tools,
        tools={name: dict(approval_mode="approve") for name in tools})
    command = [str(EXE), "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--strict-config", "--json",
        "--skip-git-repo-check", "-C", str(CONSUMER_CWD), "--color", "never"]
    for key, value in settings.items():
        command += ["-c", key + "=" + legacy.toml(value)]
    if config.get("image_transport", "mcp") == "cli":
        for row in image_inputs(case):
            command += ["--image", row["path"]]
    return command + ["-m", config["model"], "-o", str(folder / "final.txt"), "-"], tools


def prompt_for(task, config):
    task = public_value(task, [Path(row["path"]).resolve().parent for row in task["images"]])
    image_instruction = ("Your first tool call must be images() to receive the actual PNG image blocks described by task.images. "
        "Inspect those images before making a geometry decision. The initial prompt supplies their identities and roles. "
        if config.get("image_transport", "mcp") == "mcp" else
        "The PNG files described by task.images are attached as actual CLI image inputs. Inspect their visual content. ")
    instructions = ("Repair the local depression in the supplied target region so it approaches the supplied normal PNG reference, and submit one calibratable sparse proposal. Name the visible part from the images yourself. "
        "You are authorized to calculate, submit and save an evidence-supported edit through task_geometry tools. "
        + image_instruction +
        "Normal-reference and damaged-current views share pose, camera, scale, material and lighting. "
        "Use the whole-object and three local views to relate visible shape to current source vertices. The inherited view-name aliases do not identify an anatomical part. All lengths are source_native with unlabelled physical scale. "
        "The full current saved geometry, topology and a broad target domain are available. Choose your own active subset and transition within I_ids. "
        "execute_python provides fresh NumPy/SciPy numerical computation with current V, damaged initial V0, faces, F_ids, I_ids, "
        "protected_ids, source_ids, version, task, G and geometry. Optional n0/normals are measured from current damaged geometry. "
        "Source IDs index the complete source mesh. Full numerical arrays are accessible through variables and packet_path. "
        "Both routes may call read_image_pixels(role) for the same bound normal/current uint8 RGB pixels. image_roles lists the eight roles; "
        "image_cameras[role] contains the orthographic projection, image coordinates and camera matrix. "
        "Use this data to audit image-to-source correspondence and select fitting support outside the suspected affected surface, including needed neighbors outside I. "
        "Record actual fitting inputs with save_fit_diagnostics(fit_target_ids, fit_offsets, fit_source_ids, fit_design_rank, fit_estimated_amplitude_m, **extra_arrays). "
        "The integer offsets delimit each target's flattened source support IDs. Rank and signed estimated normal amplitude in source_native units are per target. The inherited diagnostic suffix _m denotes source_native values in this case. Correspondence support radius .032 and all legacy _m lengths use source_native. "
        "A single global fit may use target -1. Optional numeric arrays for spatial/normal coverage use fit_ prefixes. "
        "If amplitudes are estimated along another direction, pass fit_normals[M,3] containing those actual estimate axes. "
        "Retain the actual design/support diagnostics used by the solver and include the returned diagnostic descriptor in the final answer. "
        "File access is enforced for the current numerical packet, bound PNGs, delivered references and your own payload files. Print compact task-relevant facts. "
        "Use save_edit(ids, values, mode='positions_world' or 'displacements_world') to store your calculated sparse edit. "
        "It returns an opaque payload_id and observed_version. submit_edit applies that exact payload and saves the isolated copy. "
        "Only I_ids are editable. Preserve protected vertices, topology and finite coordinates, using the operation and cumulative displacement budgets in task. "
        "Calculate one final sparse proposal from the PNGs and current geometry, make one final submission, and inspect actual independent saved readback and saved-model preview. Retain the actual code and calculation diagnostics used. "
        "If you retain the damaged copy, call save_readback and report the repair as incomplete with concrete remaining issues. "
        "Obtain an independent saved-mesh readback record for the actual edited or retained copy before finishing. "
        "submit_edit may return that record. Use save_readback when an independent saved-mesh readback is still needed. "
        "If a receipt is missing or ambiguous, query state before any repeated edit. Use operation_id for recovery. "
        "When focus/resolve_ref are available, they provide current-geometry facts, matched-image correspondence and stable region references. "
        "The focus result provides region references and directly readable registered packets for activity, low-difference outer fitting support and full-mesh fitting exclusions. "
        "Transition and unobserved region arrays are available through resolve_ref. "
        "You may compute your own geometry. "
        "Preserve all allowed context and protection constraints, report measured completion honestly, and distinguish engineering targets from artistic acceptance. "
        f"At most {config['max_tool_calls']} tool calls and {config['max_session_seconds']} seconds are available. "
        "Finish with compact JSON using the answer schema below. Refer to active-region and actual operation/save/readback records. "
        "Record execution completion and your visual task assessment with its basis separately. Independent target scoring is performed outside this session. "
        "Summarize the visible target result and remaining issues. Keep full arrays and detailed metric tables in their recorded files.")
    return (instructions + "\n\nAnswer schema\n" + json.dumps(config["answer_schema"], ensure_ascii=False)
        + "\n\nTask\n" + json.dumps(task, ensure_ascii=False) + "\n").encode("utf8")


# The lifecycle/event parser below is copied from the verified previous consumer
# with only the isolated stage output path added. All transport helpers remain reused.

def consume(case,route,stage,config):
    preparation_started=time.perf_counter()
    task=read(case/"task.json")
    folder=HERE/"private/consumers"/stage/task["task_id"]/route
    # Validate local configuration and assets before reserving a real session.
    command,tools=argv_for(case,route,folder,config)
    prompt=prompt_for(task,config)
    images=image_inputs(case)
    folder.mkdir(parents=True,exist_ok=False)
    work=folder/"work"
    work.mkdir()
    claim_record=dict(task_id=task["task_id"],route=route,attempts=1,launch_state="prepared")
    save(folder/"CLAIM.json",claim_record)
    (folder/"PROMPT.txt").write_bytes(prompt)
    began=time.perf_counter_ns()
    deadline=began+int(config["max_session_seconds"]*1e9)
    record=dict(task_id=task["task_id"],route=route,status="running",model=config["model"],reasoning_effort=config["reasoning_effort"],
        requested_service_tier="default",resolved_model_settings=None,argv=command,CLI_identity=identity(EXE),helper_identity=identity(LEGACY),
        current_input_identity=identity(case/"input.npz"),task_identity=identity(case/"task.json"),prompt_identity=identity(folder/"PROMPT.txt"),
        started_ns=began,deadline_ns=deadline,consumer_pid=None,thread_id=None,turn_completed_ns=None,final_received_ns=None,
        usage=None,usage_rows=[],fees=None,provider_requests=None,provider_retry_observations=[],tool_calls=[],
        public_messages=[],errors=[],unexpected_tool_events=[],valid_completion=False,safe_to_continue=False,
        input_prompt_UTF8_bytes=len(prompt),output_text_UTF8_bytes=None,
        available_image_inputs=images,image_transport=config.get("image_transport","mcp"),
        initial_image_inputs=images if config.get("image_transport","mcp")=="cli" else [],
        initial_image_transport="CLI --image attachments" if config.get("image_transport","mcp")=="cli" else "MCP images() required as first tool",
        pre_session_prepare_wall_s=time.perf_counter()-preparation_started,
        initial_image_count=len(images) if config.get("image_transport","mcp")=="cli" else 0,
        initial_image_bytes=sum(row["bytes"] for row in images) if config.get("image_transport","mcp")=="cli" else 0,
        public_image_count=len(images) if config.get("image_transport","mcp")=="cli" else 0,
        public_image_bytes=sum(row["bytes"] for row in images) if config.get("image_transport","mcp")=="cli" else 0)
    save(folder/"CONSUMER.json",record)
    events=queue.Queue()
    readers=[]
    process=None
    fired=threading.Event()
    closed=0

    def reader(stream,label):
        try:
            for raw in iter(stream.readline,b""):
                events.put((label,raw,time.perf_counter_ns()))
        except BaseException as error:
            events.put(("reader_error",str(error).encode("utf8"),time.perf_counter_ns()))
        finally:
            events.put((label,None,time.perf_counter_ns()))

    def expire():
        fired.set()
        if process is not None and process.poll() is None:
            legacy.kill_owned_tree(process)

    timer=threading.Timer(config["max_session_seconds"],expire)
    timer.daemon=True
    try:
        timer.start()
        env=legacy.safe_environment(os.environ)
        for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
            env[name]="1"
        env["PYTHONDONTWRITEBYTECODE"]="1"
        claim_record["launch_state"]="launching"
        save(folder/"CLAIM.json",claim_record)
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=CONSUMER_CWD,env=env,
                                 creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        claim_record.update(launch_state="launched",pid=process.pid)
        save(folder/"CLAIM.json",claim_record)
        record["consumer_pid"]=process.pid
        for label,stream in (("stdout",process.stdout),("stderr",process.stderr)):
            thread=threading.Thread(target=reader,args=(stream,label),daemon=True)
            thread.start()
            readers.append(thread)
        record["prompt_submitted_ns"]=time.perf_counter_ns()
        process.stdin.write(prompt)
        process.stdin.close()
        with (folder/"events.jsonl").open("w",encoding="utf8",newline="\n") as log, (folder/"stderr.raw.bin").open("wb") as stderr:
            while closed<2:
                remaining=(deadline-time.perf_counter_ns())/1e9
                if remaining<=0 or fired.is_set():
                    raise TimeoutError("fixed_consumer_deadline")
                try:
                    label,raw,received=events.get(timeout=min(.1,remaining))
                except queue.Empty:
                    continue
                if raw is None:
                    closed+=1
                    continue
                if label=="reader_error":
                    raise RuntimeError("consumer_pipe_reader_failed")
                if label=="stderr":
                    stderr.write(raw)
                    stderr.flush()
                    text=raw.decode("utf8",errors="replace")
                    if any(word in text.lower() for word in ("retry","reconnect","429","503","rate limit","quota","usage limit")):
                        record["provider_retry_observations"].append(dict(perf_ns=received,text=text))
                    continue
                try:
                    event=json.loads(raw)
                except (ValueError,UnicodeError):
                    (folder/"malformed_stdout.bin").write_bytes(raw)
                    raise ValueError("non_JSON_CLI_line_retained")
                kind,item=event.get("type"),event.get("item",{})
                public=event
                if item.get("type") in ("reasoning","analysis"):
                    public=dict(type=kind,item=dict(type=item["type"],redacted=True),raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest())
                log.write(json.dumps(dict(perf_ns=received,event=public),ensure_ascii=True)+"\n")
                log.flush()
                if kind=="thread.started":
                    record["thread_id"]=event.get("thread_id")
                if kind in ("error","turn.failed"):
                    record["errors"].append(dict(perf_ns=received,event=event))
                if kind=="turn.completed":
                    record["turn_completed_ns"]=received
                    usage=event.get("usage")
                    if isinstance(usage,dict):
                        measured={key:usage[key] for key in USAGE_FIELDS if key in usage}
                        if any(type(value) is not int or value<0 for value in measured.values()):
                            raise ValueError("invalid_usage_count")
                        record["usage"]=measured
                        record["usage_rows"].append(measured)
                if kind=="item.completed":
                    if item.get("type")=="agent_message":
                        text=item.get("text","")
                        record["public_messages"].append(dict(perf_ns=received,text=text))
                        record["final"]=text
                        record["final_received_ns"]=received
                    elif item.get("type")=="mcp_tool_call":
                        record["tool_calls"].append(dict(perf_ns=received,item=item))
                        if item.get("server")!="task_geometry" or item.get("tool") not in tools:
                            record["unexpected_tool_events"].append(item)
                    elif item.get("type") in legacy.KNOWN_TOOL_TYPES:
                        record["unexpected_tool_events"].append(item)
            process.wait(timeout=max(.01,(deadline-time.perf_counter_ns())/1e9))
        record["valid_completion"]=bool(process.returncode==0 and record["thread_id"] and record["turn_completed_ns"]
            and record["final_received_ns"] and not fired.is_set() and not record["errors"] and not record["unexpected_tool_events"])
    except BaseException as error:
        if process is None:
            claim_record.update(launch_state="local_launch_failed",error=dict(type=type(error).__name__,message=str(error)))
            save(folder/"CLAIM.json",claim_record)
        record["errors"].append(dict(type=type(error).__name__,message=str(error)))
    finally:
        timer.cancel()
        timer.join(timeout=5)
        record["process_cleanup"]=legacy.kill_owned_tree(process)
        for thread in readers:
            thread.join(timeout=1)
        record["readers_stopped"]=all(not thread.is_alive() for thread in readers)
        record["exit_code"]=None if process is None else process.poll()
        record["deadline_timer_fired"]=fired.is_set()
        bridge_path=folder/"bridge/BRIDGE_RESULT.json"
        bridge=read(bridge_path) if bridge_path.exists() else {}
        record["bridge"]=bridge
        record["MCP_image_count"]=sum(call.get("public_image_count",0) for call in bridge.get("calls",[]))
        record["MCP_image_bytes"]=sum(call.get("public_image_bytes",0) for call in bridge.get("calls",[]))
        image_deliveries = []
        for call in bridge.get("calls", []):
            if call["name"] != "images":
                continue
            try:
                image_deliveries.append(verify_image_response(folder / "bridge" / ("tool_" + str(call["index"]).zfill(2)), task, images,
                    HERE / "private/sessions" / (stage + "_" + task["task_id"] + "_" + route)))
            except BaseException as error:
                image_deliveries.append(dict(index=call["index"], exact_source_PNG_bytes=False, error=str(error)))
        completed_image_items = [row["item"] for row in record["tool_calls"] if row.get("item", {}).get("tool") == "images"]
        completed_image_events = len(completed_image_items)
        for position, delivery in enumerate(image_deliveries):
            try:
                directory = folder / "bridge" / ("tool_" + str(delivery["index"]).zfill(2))
                delivery["CLI_event"] = verify_cli_image_event(completed_image_items[position], directory)
            except (ValueError, IndexError, KeyError, OSError) as error:
                delivery["CLI_event"] = dict(metadata_SHA256_verified=False, error=str(error))
        record["image_delivery_audit"] = image_deliveries
        record["actual_image_delivery_verified"] = bool(
            (record["initial_image_count"] or any(row.get("delivery_kind") == "frozen_initial" for row in image_deliveries))
            and all(row.get("exact_source_PNG_bytes") for row in image_deliveries)
            and all(row.get("CLI_event", {}).get("metadata_SHA256_verified") for row in image_deliveries)
            and completed_image_events >= len(image_deliveries))
        preview_deliveries = [row for row in image_deliveries if row.get("delivery_kind") == "saved_version_preview" and row.get("exact_source_PNG_bytes")]
        record["saved_version_preview_count"] = len(preview_deliveries)
        record["saved_version_preview_versions"] = sorted({row["version"] for row in preview_deliveries})
        record["saved_version_preview_render_calls"] = sum(bool(row.get("preview", {}).get("render_invoked")) for row in preview_deliveries)
        record["first_tool_images"]=bool(bridge.get("calls") and bridge["calls"][0]["name"]=="images")
        readbacks=[]
        for call in bridge.get("calls",[]):
            result_path=folder/"bridge"/("tool_"+str(call["index"]).zfill(2))/"COMPLETE_RESULT.json"
            if call["name"] in ("submit_edit","save_readback") and result_path.exists():
                result=read(result_path)
                if result.get("independently_reopened"):
                    readbacks.append(dict(tool_index=call["index"],tool=call["name"],record=identity(result_path)))
        record["independent_saved_readback_evidence"]=readbacks
        record["actual_readback_obtained"]=bool(readbacks)
        record["public_image_count"]+=record["MCP_image_count"]
        record["public_image_bytes"]+=record["MCP_image_bytes"]
        record["initial_image_inputs_after"]=image_inputs(case)
        record["images_unchanged"]=record["initial_image_inputs_after"]==images
        record["safe_to_continue"]=bool(record["process_cleanup"]["parent_reaped"] and record["readers_stopped"])
        record["current_input_identity_after"]=identity(case/"input.npz")
        record["task_identity_after"]=identity(case/"task.json")
        record["source_unchanged"]=(record["current_input_identity_after"]["sha256"]==record["current_input_identity"]["sha256"]
                                    and record["task_identity_after"]["sha256"]==record["task_identity"]["sha256"])
        record["tool_count"]=len(record["tool_calls"])
        record["tool_round_budget_respected"]=len(bridge.get("calls",[]))<=config["max_tool_calls"]
        record["valid_completion"] = bool(record["valid_completion"] and record["tool_round_budget_respected"] and record["source_unchanged"] and record["images_unchanged"] and record["actual_image_delivery_verified"] and record["actual_readback_obtained"]
            and (config.get("image_transport", "mcp") == "cli" or record["first_tool_images"]))
        record["wall_s"]=(time.perf_counter_ns()-began)/1e9
        record["prompt_to_final_s"]=(record["final_received_ns"]-record["prompt_submitted_ns"])/1e9 if record["final_received_ns"] else None
        final=record.get("final")
        if final is not None:
            (folder/"PUBLIC_FINAL.txt").write_text(final,encoding="utf8",newline="\n")
            record["output_text_UTF8_bytes"]=len(final.encode("utf8"))
        record["status"]="completed" if record["valid_completion"] else "failed"
        record["measurement_scope"]="actual public CLI events, bridge and bounded local Python receipts. Provider-internal requests, resolved effort, hidden retries and monetary fees unmeasured."
        save(folder/"CONSUMER.json",record)
    return record


def verify_frozen(path):
    frozen = read(path)
    for row in frozen["files"]:
        source = Path(row["path"])
        if not source.is_absolute():
            source = HERE / source
        if identity(source)["sha256"] != row["sha256"]:
            raise ValueError("frozen_consumer_source_changed_" + str(source))


def started_sessions():
    claims = [read(path) for path in (HERE / "private/consumers").glob("*/*/*/CLAIM.json")]
    return sum(claim.get("launch_state", "launching") in ("launching", "launched") for claim in claims)


def validate_config(config):
    for field in ("model", "reasoning_effort", "max_tool_calls", "max_session_seconds", "answer_schema"):
        if field not in config:
            raise ValueError("PLAN_consumer_missing_" + field)
    if config["max_tool_calls"] != 12 or config["max_session_seconds"] != 600:
        raise ValueError("fixed12calls600seconds_required")
    if config["model"] != "gpt-6.1-sol" or config["reasoning_effort"] != "medium":
        raise ValueError("fixed_model_and_reasoning_effort_required")
    if config.get("image_transport", "mcp") not in ("mcp", "cli"):
        raise ValueError("image_transport_requires_mcp_or_cli")
    if not isinstance(config["answer_schema"], dict):
        raise ValueError("answer_schema_object_required")


def fixed_sequence(plan):
    expected = [dict(stage="raw", task_id="sample_07", route="facts")]
    if plan.get("sequence") != expected:
        raise ValueError("fixed_one_consumer_sequence_required")
    return expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", required=True)
    args = parser.parse_args()
    verify_frozen(HERE / "CONSUMER_INPUT_FREEZE.json")
    verify_frozen(HERE / "CONSUMER_TOOL_FREEZE.json")
    plan = read(HERE / "CONSUMER_PLAN.json")
    config = plan["consumer"]
    validate_config(config)
    if read(HERE / "CONSUMER_PREFLIGHT.json").get("status") != "pass":
        raise ValueError("consumer_preflight_pass_required")
    fixed_sequence(plan)
    if started_sessions() >= 1:
        raise ValueError("one_consumer_session_already_claimed")
    receipt = consume(HERE / "private/consumer_cases/sample_07", "facts", "raw", config)
    receipt["stage"] = "raw"
    save(HERE / "private/consumers/raw/sample_07/facts/CONSUMER.json", receipt)
    print(json.dumps({key: receipt.get(key) for key in ("status", "wall_s", "usage", "tool_count", "safe_to_continue")}))


if __name__ == "__main__":
    main()
