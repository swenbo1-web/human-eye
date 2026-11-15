"""Post-quality saved-only runtime and raw-consumer-cost cross-check."""

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import time
import tomllib


HERE = Path(__file__).resolve().parent
RUNTIME = Path("D:/he_m4_target_consume_001")
BASE_REVIEW_SHA256 = "64634c85768f066a0375e057f9ebd06c80405369dc201f1b4831821078e2f4f6"
QUALITY_SHA256 = "1a4f787bf86c90659be0f77d8becfac80f8598141e9e6852428eaddd3048c104"
ORDER = ["N1", "P1", "P2", "N2", "N3", "P3"]
USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def load_base():
    path = HERE / "runtime_review.py"
    if sha(path) != BASE_REVIEW_SHA256:
        raise ValueError("frozen_qualification_runtime_review_changed")
    specification = importlib.util.spec_from_file_location("_target_final_runtime_base", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def configurations(argv):
    values = {}
    for index, value in enumerate(argv[:-1]):
        if value != "-c":
            continue
        key, raw = argv[index + 1].split("=", 1)
        values[key] = tomllib.loads("v=" + raw)["v"]
    return values


def usage_events(raw):
    events = []
    offset = 0
    for line in raw.splitlines(keepends=True):
        try:
            value = json.loads(line)
        except (ValueError, UnicodeError):
            offset += len(line)
            continue
        if value.get("type") == "turn.completed":
            events.append({"byte_start": offset, "byte_end": offset + len(line), "event": value,
                           "original_line_sha256": hashlib.sha256(line).hexdigest()})
        offset += len(line)
    return events


def main():
    started = time.perf_counter_ns()
    seal = read(HERE / "QUALITY_SEAL.json")
    if (seal.get("cost_unlocked") is not True or seal["quality_sha256"] != QUALITY_SHA256
            or sha(HERE / "QUALITY.json") != QUALITY_SHA256 or started <= seal["sealed_ns"]):
        raise ValueError("quality_seal_required_before_cost_read")
    base = load_base()
    review = base.Review()
    review.install()
    for label in ["N_qual", "P_qual"] + ORDER:
        review.slot(label, "qualification" if label.endswith("_qual") else "formal")
    budget = review.budget(False)
    run = read(RUNTIME / "RUN_RESULT.json")
    review.check("formal/one_six_consumer_batch", run["actual_consumers"] == run["consumer_attempts"] == run["planned_slots"] == 6
                 and run["formal_batch_attempts"] == 1 and run["outer_retries"] == run["replacement_samples"] == 0
                 and run["blocker"] is None and len(run["records"]) == 6)
    root_budget = RUNTIME / "budget"
    claims = [read(path) for path in sorted((root_budget / "claims").glob("*.json"))]
    starts = [row for row in claims if row["kind"] == "Blender_start"]
    start_phases = Counter(row["phase"] for row in starts)
    review.check("budget/eight_owned_starts", start_phases == {"qualification": 2, "formal": 6})
    budget.update(owned_start_attempts_by_phase=dict(start_phases), consumer_tasks=run["actual_consumers"],
                  deadline_contract={"consumer_seconds_from_root_start": 450, "owned_seconds_from_same_root_start": 600})
    attempts = [row for row in claims if row["kind"] == "raster_attempt"]
    attempt_outcomes = []
    for claim in attempts:
        path = root_budget / "settlements" / (claim["token"] + ".json")
        settled = read(path) if path.is_file() else None
        attempt_outcomes.append({"phase": claim["phase"], "slot": claim["label"], "token": claim["token"],
            "actual": None if settled is None else settled["actual_attempts"],
            "confirmed_lower": 0 if settled is None else settled["confirmed_attempts_lower_bound"],
            "upper": claim["reserved_upper_bound"] if settled is None or settled["actual_attempts"] is None else settled["actual_attempts"],
            "outcome": "unknown" if settled is None else settled["outcome"]})
    budget["all_attempt_outcomes_including_failures_and_unknown"] = attempt_outcomes
    budget["unknown_attempt_outcomes"] = sum(row["actual"] is None for row in attempt_outcomes)
    budget["failed_native_constructions"] = sum(row["outcome"] == "failed" for row in attempt_outcomes)
    budget["producer_admitted_attempt_scope"] = "Product settlements mark producer attempts before construction. Completed and failed counts additionally remain in each actual producer work report."

    baseline = read(HERE / "BASELINE.json")
    for path, expected in baseline["protected_old_pins"].items():
        review.check("history/" + expected[:10], review.pin(path, "protected previous seal")["sha256"] == expected)
    frozen = read(HERE / "FROZEN.json")
    execution_names = {"owned_runtime.py", "budget.py", "mcp_entry.py", "native_consumer_audit.py", "bridge.py",
                       "native_tools.py", "bootstrap.py", "launcher.py", "run_slot.py", "run_formal.py",
                       "owned_native.py", "stdio_checks.py", "wire_meter.py", "process_proof.py", "verified_bootstrap.py",
                       "DEVICE_CAMERAS.json", "COMMON_TASK.txt", "ANSWER_SCHEMA.json", "PRODUCT_RUN_BINDING.json"}
    for pin in frozen["files"]:
        if Path(pin["path"]).name in execution_names:
            review.check("frozen/execution/" + pin["path"], review.pin(pin["path"], "frozen execution source")["sha256"] == pin["sha256"])
    for name in ("FROZEN.json", "PLAN.json", "QUALITY_SEAL.json", "QUALITY.json", "fixtures/DEVICE_PREPARATION.json",
                 "STATIC_PREPARATION_FAILURES.json", "unexecuted_mcp_recovery_prepare/PREPARATION.json"):
        review.pin(HERE / name, "sealed plan, quality or preparation witness")
    review.pin(RUNTIME / "RUN_RESULT.json", "one closed formal batch")
    review.pin(Path(__file__), "this post-quality audit source")

    consumer_rows = []
    profiles = []
    thin_states = []
    for label in ORDER:
        folder = RUNTIME / "formal" / label
        slot = read(folder / "SLOT_RESULT.json")
        publication = read(folder / "SLOT_PUBLICATION.json")
        path = Path(slot["consumer_record"])
        consumer = read(path)
        review.pin(path, "original consumer report")
        stdout_path = path.parent / "stdout.raw.bin"
        stdout = stdout_path.read_bytes()
        review.check(label + "/original_CLI_stdout", review.pin(stdout_path, "actual CLI stdout bytes")["sha256"] == consumer["stdout_raw_sha256"]
                     and len(stdout) == consumer["stdout_raw_bytes"])
        raw = usage_events(stdout)
        review.check(label + "/single_original_usage_event", len(raw) == 1)
        if len(raw) != 1:
            raise ValueError("one_raw_turn_completed_usage_required:" + label)
        usage = raw[0]["event"]["usage"]
        review.check(label + "/raw_usage_matches_report", usage == consumer["usage"]
                     and consumer["raw_usage_events"] == [usage] and all(type(usage[key]) is int and usage[key] >= 0 for key in USAGE_FIELDS))
        review.check(label + "/usage_subset_bounds", usage["cached_input_tokens"] <= usage["input_tokens"]
                     and usage["reasoning_output_tokens"] <= usage["output_tokens"])
        review.check(label + "/CLI_complete_and_reaped", consumer["valid_completion"] is True and consumer["safe_to_continue"] is True
                     and consumer["status"] == "completed" and consumer["exit_code"] == 0
                     and consumer["process_reaped"] is True and consumer["readers_stopped"] is True
                     and consumer["deadline_timer_fired"] is False and consumer["process_cleanup"]["exit_code"] == 0
                     and consumer["process_cleanup"]["process_handle_closed"] is True
                     and all(consumer["process_cleanup"]["pipes_closed"].values()))
        binding = consumer["runtime_binding"]
        thin = consumer["runtime_exit"]
        review.check(label + "/CLI_and_thin_process_identity", binding["launcher_pid"] == consumer["consumer_pid"]
                     and binding["runtime_pid"] == binding["stdio_STARTED"]["pid"]
                     and binding["launcher_pid"] != binding["runtime_pid"]
                     and binding["confirmed"] is True and thin["confirmed"] is True
                     and thin["exited"] is True and thin["handle_closed"] is True)
        thin_exit = Path(binding["STARTED_path"]).with_name("EXIT.json")
        thin_state = {"slot": label, "CLI_pid": consumer["consumer_pid"], "CLI_Popen_exit_code": consumer["exit_code"],
                      "CLI_cleanup": consumer["process_cleanup"], "thin_Python_pid": binding["runtime_pid"],
                      "thin_actual_held_exit": thin, "thin_EXIT_receipt_present": thin_exit.exists(),
                      "safe_to_continue": consumer["safe_to_continue"],
                      "scope": "CLI Popen and held thin Python stdio adapter are distinct processes. Missing EXIT receipt is preserved under the accepted consumer contract."}
        thin_states.append(thin_state)
        review.pin(binding["STARTED_path"], "actual thin Python identity receipt")
        config = configurations(consumer["argv"])
        profile = {key: value for key, value in config.items() if key != "mcp_servers.arm_engine"}
        profiles.append(profile)
        review.check(label + "/fixed_CLI_profile", consumer["argv"] == consumer["frozen_cli_argv"]
                     and consumer["model"] == config["model"] == "gpt-6.1-sol"
                     and config["model_reasoning_effort"] == consumer["requested_effort"] == "medium"
                     and config["service_tier"] == "default"
                     and config["features.hooks"] is False and config["features.plugins"] is False
                     and config["memories.use_memories"] is False)
        actual_binary = review.pin(consumer["argv"][0], "actual fixed Codex CLI binary")
        preflight = read(HERE / "CLI_PREFLIGHT.json")
        review.check(label + "/CLI_binary_pin", actual_binary["sha256"] == preflight["binary"]["sha256"])
        review.check(label + "/original_task_deadline", consumer["deadline_ns"] == consumer["episode_deadline_ns"] == slot["clocks"]["consumer_deadline_ns"])
        review.check(label + "/consumer_clocks", consumer["wall_ns"] == consumer["cleanup_end_ns"] - consumer["started_ns"]
                     and consumer["prompt_to_final_ns"] == consumer["final_received_ns"] - consumer["prompt_submitted_ns"])
        for item in consumer["MCP_wire_files"]:
            actual = review.pin(path.parent / item["path"], "actual CLI MCP transport wire")
            review.check(label + "/MCP_wire/" + item["path"], actual["sha256"] == item["sha256"] and actual["bytes"] == item["bytes"])
        tx = sum(item["bytes"] for item in consumer["MCP_wire_files"] if Path(item["path"]).name == "TX.bin")
        rx = sum(item["bytes"] for item in consumer["MCP_wire_files"] if Path(item["path"]).name == "RX.bin")
        review.check(label + "/MCP_wire_totals", tx == consumer["MCP_stdio_TX_bytes"] and rx == consumer["MCP_stdio_RX_bytes"])
        owner = read(folder / "owner/METRICS.json")
        source_tools = read(folder / "owner/TOOLS.json")
        tool_rows = source_tools.get("tools", [])
        consumer_rows.append({"slot": label, "group": label[0], "quality_passed": True,
            "complete_slot_ns": publication["complete_slot_ns"], "consumer_wall_ns": consumer["wall_ns"],
            "prompt_to_final_ns": consumer["prompt_to_final_ns"], "raw_usage": usage,
            "raw_input_plus_output": usage["input_tokens"] + usage["output_tokens"],
            "raw_usage_original_line": {key: value for key, value in raw[0].items() if key != "event"},
            "usage_semantics_reported": consumer["usage_semantics"], "usage_aggregation_reported": consumer["usage_aggregation"],
            "requested_model": consumer["model"], "requested_effort": consumer["requested_effort"],
            "resolved_effort": consumer["resolved_effort"], "fees": consumer["fees"],
            "thread_id": consumer["thread_id"], "business_tool_attempts": owner["tool_attempts"],
            "business_tool_names": [row.get("name", row.get("tool")) for row in tool_rows],
            "MCP_stdio_TX_bytes": tx, "MCP_stdio_RX_bytes": rx,
            "CLI_image_blocks": consumer["public_image_count"], "CLI_known_PNG_bytes": consumer["known_PNG_bytes"],
            "public_text_bytes": consumer["public_text_bytes"], "output_text_bytes": consumer["output_text_bytes"],
            "provider_requests": consumer["provider_requests"], "provider_retry_observations": consumer["provider_retry_observations"],
            "tool_records_path": str(folder / "owner/TOOLS.json"), "consumer_path": str(path)})
    review.check("formal/same_common_CLI_configuration", all(profile == profiles[0] for profile in profiles))
    review.check("formal/six_fresh_threads", len({row["thread_id"] for row in consumer_rows}) == 6)
    by_label = {row["slot"]: row for row in consumer_rows}
    pairs = []
    for index in (1, 2, 3):
        N, P = by_label["N" + str(index)], by_label["P" + str(index)]
        ratio = P["complete_slot_ns"] / N["complete_slot_ns"]
        pairs.append({"pair": index, "N_slot": N["slot"], "P_slot": P["slot"],
                      "N_complete_slot_ns": N["complete_slot_ns"], "P_complete_slot_ns": P["complete_slot_ns"],
                      "P_over_N_full_slot": ratio, "N_over_P_full_slot": 1 / ratio,
                      "N_raw_input_plus_output": N["raw_input_plus_output"], "P_raw_input_plus_output": P["raw_input_plus_output"]})
    totals = {group: {key: sum(row["raw_usage"][key] for row in consumer_rows if row["group"] == group) for key in USAGE_FIELDS}
              for group in ("N", "P")}
    for group in totals:
        totals[group]["raw_input_plus_output"] = totals[group]["input_tokens"] + totals[group]["output_tokens"]
    median = statistics.median(row["P_over_N_full_slot"] for row in pairs)
    faster = sum(row["P_over_N_full_slot"] < 1 for row in pairs)
    quality_eligible = seal["N_quality_count"] == seal["P_quality_count"] == seal["P_adoption_count"] == 3
    finite_gate = quality_eligible and median <= .90 and faster >= 2 and totals["P"]["raw_input_plus_output"] <= totals["N"]["raw_input_plus_output"]
    review.check("quality/sealed_before_cost", quality_eligible and seal["quality_denominator"] == 6 and started > seal["sealed_ns"])
    review.check("all_review_inputs_unchanged", all(Path(row["path"]).stat().st_size == row["bytes"]
                 and sha(row["path"]) == row["sha256"] for row in review.pins.values()))
    passed = all(row["passed"] for row in review.checks)
    runtime_report = {"schema": "target-task-final-runtime-review-v1", "passed_checked_scope": passed, "qualification_only": False,
        "check_count": len(review.checks), "checks": review.checks,
        "failed_checks": [row for row in review.checks if not row["passed"]],
        "budget": budget, "records": review.records, "consumer_processes": thin_states,
        "quality_seal_sha256": sha(HERE / "QUALITY_SEAL.json"), "quality_sha256": QUALITY_SHA256,
        "source_scope": "141 installed files and actual transmitted host source subset are checked separately. Source and current frame facts are independently graded elsewhere.",
        "author_association": "Reviewer authored this batch owned runtime, helper adaptation, budget and qualification driver. Root alone performed all actual runs. This associated runtime review reuses the unchanged qualification reviewer.",
        "process_scope": "Actual CLI Popen exit0, held thin Python adapter exit1 with missing EXIT receipt, and Actor/product-MCP/Blender process closures retain their distinct identities. Thin exit1 cause is unmeasured. The accepted safe_to_continue contract is preserved.",
        "wrapper_scope": "NativeSession full-scene terminal fingerprint clocks included. Source-derived whole-scene guard visits remain unmeasured and are separate from returned selected geometry and product selective work counters.",
        "limits": ["No new live product, Blender, model or raster operation.", "This review does not claim every process exited with code0.",
                   "Reported CLI usage scope remains unconfirmed_turn_or_session_scope. Provider billing and fees are unmeasured.",
                   "One fixed mixed synthetic asset, one configured entry and three pairs. No broad-scene or natural-routing claim.",
                   "Root owns archive and final decision."],
        "new_operations": {"owned_starts": 0, "product_observations": 0, "rasters": 0, "consumers": 0},
        "input_pins": sorted(review.pins.values(), key=lambda row: row["path"])}
    cost_report = {"schema": "target-task-consumer-cost-cross-review-v1", "passed_checked_scope": passed,
        "quality_seal_sha256": sha(HERE / "QUALITY_SEAL.json"), "quality_eligible": quality_eligible,
        "consumer_denominator": 6, "formal_batches": 1, "replacement_samples": 0, "outer_retries": 0,
        "rows": consumer_rows, "pairs": pairs, "raw_usage_totals": totals,
        "P_over_N_paired_full_slot_median": median, "P_faster_pairs": faster,
        "P_over_N_total_raw_input_plus_output": totals["P"]["raw_input_plus_output"] / totals["N"]["raw_input_plus_output"],
        "preregistered_finite_raw_counter_gate": finite_gate,
        "gate_scope": "Sealed6/6 quality and P3/3 adoption, same-origin original CLI counters, paired full-slot median<=0.90, at least2/3 faster, P rawinput+rawoutput total<=N. Root independently decides acceptance.",
        "usage_scope": "One original turn.completed event per fresh consumer thread, same CLI binary and requested profile. Raw cached-input and reasoning-output are recorded as subsets, never added to rawinput+rawoutput. CLI turn/session aggregation and provider billing remain unconfirmed.",
        "time_scope": "Full slot starts before checks/startup and ends after CLI/Actor/MCP/Blender cleanup plus SLOT_RESULT fsync. Final SLOT_PUBLICATION marker persistence is separate. Consumer wall, prompt-final and tool clocks are nested and not summed.",
        "preparation": {"device_preparation": read(HERE / "fixtures/DEVICE_PREPARATION.json"),
                        "qualifications": [row for row in review.records if row["phase"] == "qualification"],
                        "source_orchestration_review_cost": "not independently priced; saved review process timing separate"},
        "process_limitation": runtime_report["process_scope"], "fees_or_USD": None,
        "limitations": runtime_report["limits"], "input_pins": runtime_report["input_pins"]}
    save(HERE / "RUNTIME_REVIEW.json", runtime_report)
    save(HERE / "CONSUMER_COST_REVIEW.json", cost_report)
    lines = ["# 最终运行与成本复核", "", f"`passed_checked_scope={str(passed).lower()}`，{len(review.checks)}项检查。", "",
             f"实际8次owned启动，包含2个资格槽和6个模型任务槽。raster逐次准入共{budget['attempts']}次，失败和未知保留在预算原记录。", "",
             "CLI主体的Popen退出码为0。持有的薄Python适配器退出码为1，EXIT回执缺失，已证实退出并关闭句柄，原因未测。Actor、产品MCP与Blender按各自PID及持有回执分别核对。", "",
             "## 三对完整槽", "", "| 配对 | N秒 | P秒 | P/N |", "|---|---:|---:|---:|"]
    for row in pairs:
        lines.append(f"| {row['pair']} | {row['N_complete_slot_ns']/1e9:.6f} | {row['P_complete_slot_ns']/1e9:.6f} | {row['P_over_N_full_slot']:.6f} |")
    lines.extend(["", f"配对P/N中位数为{median:.6f}，P在{faster}/3对中更快。同源CLI原始input+output合计N={totals['N']['raw_input_plus_output']}，P={totals['P']['raw_input_plus_output']}。有限原计数门限为{str(finite_gate).lower()}。", "",
                  "质量先封存，六槽质量及P三槽采用均通过。原始usage从各自stdout的turn.completed行重新提取，cached input与reasoning output作为子项保留，费用与供应商计费口径未测。", "",
                  "完整槽包含启动检查、模型回答、工具工作、所有进程关闭及结果fsync。标记文件发布、准备、资格和审查成本单列。共享device仅原始设备参数，N每槽加载及P实际相机生成保留各自成本。", "",
                  "本复核者同时编写了运行器、预算和资格适配，根执行了全部实测。结论限于一个固定资产、配置好入口和三对任务。归档和最终判定由根独立完成。"])
    with (HERE / "RUNTIME_REVIEW.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    print(json.dumps({"passed_checked_scope": passed, "checks": len(review.checks), "failed_checks": runtime_report["failed_checks"],
        "budget": budget, "pairs": pairs, "raw_usage_totals": totals, "paired_median": median,
        "finite_gate": finite_gate, "runtime_SHA256": sha(HERE / "RUNTIME_REVIEW.json"),
        "cost_SHA256": sha(HERE / "CONSUMER_COST_REVIEW.json"), "markdown_SHA256": sha(HERE / "RUNTIME_REVIEW.md")}))


if __name__ == "__main__":
    main()
