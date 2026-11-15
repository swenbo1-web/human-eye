"""At most six fixed Pro consumers using the existing ephemeral CLI transport."""

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
    tools = ["execute_python", "submit_edit", "state", "save_readback"] + (["focus", "resolve_ref"] if route == "facts" else [])
    settings["mcp_servers.task_geometry"] = dict(command=str(python), args=["-I", "-B", "-X", "utf8", str(HERE / "consumer_bridge.py"),
        "--case", str(case), "--session", str(session), "--route", route, "--audit", str(folder / "bridge"),
        "--max-tool-calls", str(config["max_tool_calls"]), "--python-timeout-s", str(config.get("python_timeout_s", 45)),
        "--python-output-chars", str(config.get("python_output_chars", 16000)), "--fact-output-chars", str(config.get("fact_output_chars", 50000))],
        cwd=str(folder / "work"), required=True, startup_timeout_sec=90, tool_timeout_sec=180, enabled_tools=tools,
        tools={name: dict(approval_mode="approve") for name in tools})
    command = [str(EXE), "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--strict-config", "--json",
        "--skip-git-repo-check", "-C", str(folder / "work"), "--color", "never"]
    for key, value in settings.items():
        command += ["-c", key + "=" + legacy.toml(value)]
    return command + ["-m", config["model"], "-o", str(folder / "final.txt"), "-"], tools


def prompt_for(task, config):
    instructions = ("Complete the specified directional nonrigid refinement on your independent Blender copy. "
        "You are authorized to calculate, submit and save the edit through task_geometry tools. "
        "Use the same supplied target, topology, initial normal directions and fixed boundaries. The displacement must be your calculation. "
        "execute_python is an ordinary fresh NumPy/SciPy/standard-library interpreter with current V, initial V0, faces, F_ids, I_ids, C_ids, "
        "B0_ids, B1_ids, n0, h, ell, center, version and task. Source IDs index the complete source mesh. "
        "Use save_edit(ids, values, mode='positions_world' or 'displacements_world') to store your calculated sparse edit. "
        "It returns an opaque payload_id and observed_version. submit_edit applies that exact payload and saves the isolated copy. "
        "Only I_ids are editable. n0 is fixed from initial geometry. Do not write any original asset or unrelated file. "
        "A planning-only answer does not complete this task. Actually submit your edit and obtain an independent saved-mesh readback record. "
        "submit_edit may return that record. Use save_readback when an independent saved-mesh readback is still needed. "
        "If a receipt is missing or ambiguous, query state before any repeated edit. Use operation_id for recovery. "
        "When focus/resolve_ref are available, they provide additional current facts and references. You may compute your own geometry. "
        "Preserve all allowed context and protection constraints, report measured completion honestly, and distinguish engineering targets from artistic acceptance. "
        f"At most {config['max_tool_calls']} tool calls and {config['max_session_seconds']} seconds are available. "
        "Finish with compact JSON using the answer schema below and refer to actual operation/save/readback records.")
    return (instructions + "\n\nAnswer schema\n" + json.dumps(config["answer_schema"], ensure_ascii=False)
        + "\n\nTask\n" + json.dumps(task, ensure_ascii=False) + "\n").encode("utf8")


# The lifecycle/event parser below is copied from the verified previous consumer
# with only the isolated stage output path added. All transport helpers remain reused.

def consume(case,route,stage,config):
    task=read(case/"task.json")
    folder=HERE/"private/consumers"/stage/task["task_id"]/route
    folder.mkdir(parents=True,exist_ok=False)
    work=folder/"work"
    work.mkdir()
    with (folder/"CLAIM.json").open("x",encoding="utf8") as claim:
        json.dump(dict(task_id=task["task_id"],route=route,attempts=1),claim)
    command,tools=argv_for(case,route,folder,config)
    prompt=prompt_for(task,config)
    (folder/"PROMPT.txt").write_bytes(prompt)
    began=time.perf_counter_ns()
    deadline=began+int(config["max_session_seconds"]*1e9)
    record=dict(task_id=task["task_id"],route=route,status="running",model=config["model"],reasoning_effort=config["reasoning_effort"],
        requested_service_tier="default",resolved_model_settings=None,argv=command,CLI_identity=identity(EXE),helper_identity=identity(LEGACY),
        current_input_identity=identity(case/"input.npz"),task_identity=identity(case/"task.json"),prompt_identity=identity(folder/"PROMPT.txt"),
        started_ns=began,deadline_ns=deadline,consumer_pid=None,thread_id=None,turn_completed_ns=None,final_received_ns=None,
        usage=None,usage_rows=[],fees=None,provider_requests=None,provider_retry_observations=[],tool_calls=[],
        public_messages=[],errors=[],unexpected_tool_events=[],valid_completion=False,safe_to_continue=False,
        input_prompt_UTF8_bytes=len(prompt),output_text_UTF8_bytes=None,public_image_count=0,public_image_bytes=0)
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
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=work,env=env,
                                 creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
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
        record["safe_to_continue"]=bool(record["process_cleanup"]["parent_reaped"] and record["readers_stopped"])
        record["current_input_identity_after"]=identity(case/"input.npz")
        record["task_identity_after"]=identity(case/"task.json")
        record["source_unchanged"]=(record["current_input_identity_after"]["sha256"]==record["current_input_identity"]["sha256"]
                                    and record["task_identity_after"]["sha256"]==record["task_identity"]["sha256"])
        record["tool_count"]=len(record["tool_calls"])
        record["tool_round_budget_respected"]=len(bridge.get("calls",[]))<=config["max_tool_calls"]
        record["valid_completion"] = record["valid_completion"] and record["tool_round_budget_respected"] and record["source_unchanged"]
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--stage", choices=("v1", "v2"), required=True)
    parser.add_argument("--task", choices=("s01", "s02"))
    parser.add_argument("--route", choices=("native", "facts"))
    args = parser.parse_args()
    if bool(args.task) != bool(args.route):
        raise ValueError("task_and_route_selected_together")
    verify_frozen(HERE / "PLAN_FREEZE.json")
    verify_frozen(HERE / ("TOOL_FREEZE_v2.json" if args.stage == "v2" else "TOOL_FREEZE.json"))
    config = read(HERE / "PLAN.json")["consumer"]
    if config["max_tool_calls"] != 10 or config["max_session_seconds"] != 480:
        raise ValueError("fixed10calls480seconds_required")
    sequence = [("s01", "native"), ("s01", "facts"), ("s02", "facts"), ("s02", "native")]
    if args.stage == "v2":
        if not (HERE / "OPTIMIZATION_BINDING.json").exists():
            raise ValueError("optimization_binding_required_for_v2")
        for task_id, route in sequence:
            receipt = read(HERE / "private/consumers/v1" / task_id / route / "CONSUMER.json")
            if receipt["status"] == "running":
                raise ValueError("all_four_initial_results_required_before_optimization")
        sequence = [("s02", "facts"), ("s01", "facts")]
    if args.task:
        sequence = [(task_id, route) for task_id, route in sequence if task_id == args.task and route == args.route]
        if len(sequence) != 1:
            raise ValueError("selected_task_route_not_in_fixed_stage")
    receipts, blocked = [], []
    for position, (task_id, route) in enumerate(sequence):
        if len(list((HERE / "private/consumers").glob("*/*/*/CLAIM.json"))) >= 6:
            raise ValueError("maximum_six_consumer_sessions_already_claimed")
        case = HERE / "private/consumer_cases" / task_id
        receipt = consume(case, route, args.stage, config)
        receipt["stage"] = args.stage
        save(HERE / "private/consumers" / args.stage / task_id / route / "CONSUMER.json", receipt)
        brief = dict(stage=args.stage, task_id=task_id, route=route, status=receipt["status"], wall_s=receipt["wall_s"],
                     usage=receipt["usage"], tool_count=receipt["tool_count"])
        receipts.append(brief)
        print(json.dumps(brief), flush=True)
        if not receipt["safe_to_continue"]:
            break
        stderr_path = HERE / "private/consumers" / args.stage / task_id / route / "stderr.raw.bin"
        failure = json.dumps(receipt["errors"]).lower() + stderr_path.read_text(encoding="utf8", errors="replace").lower()
        unavailable = not receipt.get("final") and not receipt["tool_calls"] and bool(receipt["errors"]) and any(
            word in failure for word in ("401", "403", "unauthorized", "authentication", "login required", "failed to connect", "failed to send request", "429", "503", "rate limit", "usage limit", "quota", "model_not_found"))
        if unavailable:
            blocked = [dict(stage=args.stage, task_id=ident, route=other, status="blocked_by_same_entrypoint") for ident, other in sequence[position+1:]]
            break
    save(HERE / "private" / ("CONSUMERS_" + args.stage + "_LAST.json"), dict(stage=args.stage, receipts=receipts,
        blocked_by_same_entrypoint=blocked, total_claims=len(list((HERE / "private/consumers").glob("*/*/*/CLAIM.json"))),
        actual_provider_replacement=False, prompt_replays=0))


if __name__ == "__main__":
    main()
