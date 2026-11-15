"""Read saved M2 records without importing or invoking product/host code."""

from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
SOURCE = Path("C:/Users/Administrator/.codex/worktrees/m1-source-face-binding-001/hefe/verification/m2_tight_directory_001")
PLAN = Path("D:/hefe/docs/M2_DIRECTORY_RESOURCE_REUSE_001_PLAN.md")
PLAN_SHA256 = "19c991d42ac17d0b8e38cfe7286c2c4c28fc4dd554c2e25c29fd52cc41d2cf21"
INVENTORY_SHA256 = "160bb51671b16075298f228affb18b9b334c6e3144cdb0cb8e75a2c65363e254"
BASELINE = "8f2a739e789b777358d84a168154bc7c50b929e5"


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def inventory():
    rows = []
    aggregate = hashlib.sha256()
    for path in sorted((p for p in SOURCE.rglob("*") if p.is_file()),
                       key=lambda p: p.relative_to(SOURCE).as_posix()):
        blob = path.read_bytes()
        row = {"path": path.relative_to(SOURCE).as_posix(),
               "bytes": len(blob), "sha256": digest(blob)}
        rows.append(row)
        aggregate.update((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())
    return rows, aggregate.hexdigest()


def compact_packet(body):
    binding = body.get("binding", {})
    identity = binding.get("host_identity", body.get("host_identity", {}))
    state = body.get("capture_state", {})
    return {"cache_hit": body.get("cache_hit"),
            "capture_state": state,
            "host_identity": identity,
            "directory_sha256": body.get("directory_sha256"),
            "host_source_sha256": binding.get("host_source_sha256"),
            "frame": binding.get("frame"), "subframe": binding.get("subframe"),
            "scale_length": binding.get("scale_length"),
            "scene_transport_target": body.get("scene_transport", {}).get("target"),
            "resource_stamp_observed": False,
            "resource_pose_observed": False}


def inner_request(code):
    match = re.search(r"_request = _json.loads\((.+)\)\n", code)
    return json.loads(ast.literal_eval(match.group(1))) if match else None


def review_measurements(errors):
    cases = []
    stats = Counter()
    for path in sorted((SOURCE / "measurement").rglob("RESULTS.json")):
        result = load(path)
        if not result.get("rows"):
            continue
        root = path.parent
        relative = root.relative_to(SOURCE).as_posix()
        session = load(root / "native/SESSION.json")
        events = [json.loads(line) for line in
                  (root / "native/WORKER_EVENTS.jsonl").read_text().splitlines() if line.strip()]
        records = []
        for row in result["rows"]:
            selected_events = [event for event in events if
                               row["started_ns"] <= event.get("started_ns", -1) <= row["ended_ns"]]
            if selected_events != row.get("work_events"):
                errors.append(relative + "/row_event_mismatch/" + str(row.get("index")))
            actual_commands = []
            actual_work = []
            for event in selected_events:
                wire_path = root / "native/WIRE" / f"{event['sequence']:03}" / "REQUEST.bin"
                request = load(wire_path)
                code = request["params"]["code"]
                hash_ok = digest(code.encode()) == event["script_sha256"]
                stats["raw_wire_code_hash_matches"] += hash_ok
                if not hash_ok:
                    errors.append(str(wire_path) + "/code_hash")
                actual = inner_request(code)
                command = actual["command"] if actual else "native_execute_code_directory"
                actual_commands.append(command)
                stats["actual_host_command_" + command] += 1
                work = event.get("m2_work", {})
                actual_work.append({"sequence": event["sequence"],
                                    "started_ns": event.get("started_ns"),
                                    "script_sha256": event.get("script_sha256"),
                                    "raw_wire_path": wire_path.relative_to(SOURCE).as_posix(),
                                    "m2_work": work})
            query = row.get("request", {}).get("params", {}).get("arguments", {}).get("query", {})
            mode = query.get("mode", "native_directory")
            body = row.get("body", {})
            if mode == "directory":
                classification = "already_cached" if body.get("cache_hit") is True else "first_directory_before_resources"
                stats["product_directory_records"] += 1
                stats["product_directory_cache_hit"] += body.get("cache_hit") is True
                stats["product_directory_cache_miss"] += body.get("cache_hit") is False
            elif mode == "native_directory":
                classification = "separate_native_directory_implementation"
            else:
                classification = "resource_capture_without_later_product_directory"
            record = {"index": row.get("index"), "phase": row.get("phase"),
                      "query": query, "mode": mode,
                      "started_ns": row["started_ns"], "ended_ns": row["ended_ns"],
                      "tool_ns": row.get("tool_ns"), "classification": classification,
                      "actual_host_commands": actual_commands, "packet": compact_packet(body),
                      "actual_work": actual_work}
            records.append(record)
            stats["business_records"] += 1
        stats["sessions"] += 1
        stats["formal_sessions" if relative.startswith("measurement/run_01/") else "preflight_sessions"] += 1
        stats["worker_events_including_shutdown"] += len(events)
        stats["raw_wire_requests_including_shutdown"] += len(list((root / "native/WIRE").glob("*/REQUEST.bin")))
        stats["lane_" + result.get("lane", "baseline_old")] += 1
        cases.append({"case": relative, "result_path": path.relative_to(SOURCE).as_posix(),
                      "lane": result.get("lane", "baseline_old"), "asset": result.get("asset"),
                      "passed": result.get("passed"), "two_step": result.get("two_step", False),
                      "host": {key: session.get(key) for key in
                               ("pid", "host", "port", "started_ns", "asset_sha256", "helper_sha256")},
                      "natural_task": False,
                      "provenance": "measurement/sample.py or probe.py fixed scripted engineering sequence",
                      "source_script": "measurement/probe.py" if relative == "measurement/baseline_01" else "measurement/sample.py",
                      "classification": "scripted_engineering_measurement",
                      "session_wall_ns": result.get("session_wall_ns"),
                      "continuous_request_window_ns": result.get("continuous_request_window_ns"),
                      "sequence": records})
    return cases, stats


def review_entry(name, errors):
    root = SOURCE / "correctness" / name
    result = load(root / "RESULTS.json")
    start = load(root / "BLENDER_START.json")
    records = []
    for row in result["records"]:
        label = row["label"]
        request = load(root / (label + ".REQUEST.json"))
        response = load(root / (label + ".RESPONSE.json"))
        body = json.loads(response["result"]["content"][0]["text"])
        if body != row["body"]:
            errors.append(name + "/saved_response_mismatch/" + label)
        mode = request["params"]["arguments"]["query"]["mode"]
        if mode == "directory":
            if body.get("cache_hit") is True:
                classification = "already_cached"
            elif label.startswith("changed_"):
                classification = "scripted_freshness_mutation"
            else:
                classification = "first_directory_before_resources"
        else:
            classification = "scripted_resource_capture_after_directory"
        oracle = root / (label + ".ORACLE.json")
        records.append({"label": label, "mode": mode,
                        "started_ns": row["started_ns"], "ended_ns": row["ended_ns"],
                        "request_path": request_path(root, label + ".REQUEST.json"),
                        "response_path": request_path(root, label + ".RESPONSE.json"),
                        "classification": classification, "packet": compact_packet(body),
                        "current_pose_oracle_path": oracle.relative_to(SOURCE).as_posix() if oracle.exists() else None,
                        "resource_compatibility": "unknown_without_resource_stamp_and_pose_snapshot"})
    return {"case": "correctness/" + name, "passed": result["passed"],
            "host": {"pid": start["pid"], "started_ns": start["started_ns"]},
            "natural_task": False, "classification": "scripted_correctness_sequence",
            "source_script": "correctness/run_entry.py",
            "failed_attempt_retained": name == "entry_01", "sequence": records}


def request_path(root, filename):
    return (root / filename).relative_to(SOURCE).as_posix()


def review_typed():
    root = SOURCE / "correctness/typed_01"
    requests = load(root / "REQUESTS.json")
    identity = load(root / "WORKER_IDENTITY.json")
    labels = ["directory_cold", "directory_hot", "selected", "directory_after_selected", "full", "shutdown"]
    records = []
    for index, (request, label) in enumerate(zip(requests, labels, strict=True)):
        response = request["response"]
        body = response.get("capture", response)
        mode = request["command"]
        classification = "scripted_resource_capture_after_directory"
        if mode == "capture_directory":
            classification = "already_cached" if body.get("cache_hit") is True else "first_directory_before_resources"
        elif mode == "shutdown":
            classification = "shutdown"
        records.append({"index": index, "label": label, "mode": mode,
                        "classification": classification, "packet": compact_packet(body),
                        "time_boundary": "ordered_request_log_without_per_request_timestamps",
                        "source_path": "correctness/typed_01/REQUESTS.json"})
    cold = load(root / "directory_cold.json")
    hot = load(root / "directory_hot.json")
    after = load(root / "directory_after_selected.json")
    return {"case": "correctness/typed_01", "passed": load(root / "RESULTS.json")["passed"],
            "host": identity["process_proof"], "natural_task": False,
            "classification": "scripted_typed_correctness_sequence",
            "source_script": "correctness/typed_01/run_typed.py",
            "sequence": records,
            "after_selected_byte_identical_to_hot": (root / "directory_hot.json").read_bytes() == (root / "directory_after_selected.json").read_bytes(),
            "directory_states_equal": cold["capture_state"] == hot["capture_state"] == after["capture_state"]}


def main():
    errors = []
    plan_sha = digest(PLAN.read_bytes())
    pins, inventory_sha = inventory()
    if plan_sha != PLAN_SHA256 or inventory_sha != INVENTORY_SHA256 or len(pins) != 4702:
        raise RuntimeError("frozen_input_mismatch_before_analysis")
    cases, measurement_stats = review_measurements(errors)
    cases.extend(review_entry(name, errors) for name in ("entry_01", "entry_02"))
    cases.append(review_typed())
    all_records = [record for case in cases for record in case["sequence"]]
    directories = [record for record in all_records if record["mode"] in ("directory", "capture_directory")]
    classification_counts = Counter(record["classification"] for record in all_records)
    product_directory_states = Counter("hit" if record["packet"]["cache_hit"] is True else "miss" for record in directories)
    mutation_records = [record for record in all_records if record["classification"] == "scripted_freshness_mutation"]
    same_host_cached_candidates = []
    for case in cases:
        for record in case["sequence"]:
            if record.get("label") in ("directory_after_full", "directory_after_selected"):
                same_host_cached_candidates.append({"case": case["case"], "record": record})
    initial_new_directory_records = [case["sequence"][0] for case in cases
                                    if case["sequence"][0]["mode"] == "directory" and
                                    case["case"].startswith("measurement/")]
    first_resource_counts = []
    for record in initial_new_directory_records:
        first_resource_counts.append(sum(len(before.get("resources", {})) for work in record["actual_work"]
                                         for before in work["m2_work"].get("before", [])))
    if len(cases) != 42 or len(initial_new_directory_records) != 12 or any(first_resource_counts):
        errors.append("session_denominator_or_first_directory_resources_changed")
    if len(same_host_cached_candidates) != 3 or any(record["record"]["packet"]["cache_hit"] is not True
                                                   for record in same_host_cached_candidates):
        errors.append("cached_candidate_validation_failed")
    after_pins, after_sha = inventory()
    if pins != after_pins or after_sha != inventory_sha:
        errors.append("saved_source_changed_during_review")
    report = {
        "task": "M2-DIRECTORY-RESOURCE-REUSE-001", "review": "bounded_saved_M2_trace_qualification",
        "reviewer": "/root/m1_binding_tests", "baseline_commit": BASELINE,
        "association": "Reviewer authored prior M1 directed checks, A normalization and runtime review. Reviewer did not author the saved M2 product/trajectory producers. This review script is reviewer-authored and receives parent independent review.",
        "decision": "not_actionable" if not errors else "review_error",
        "natural_task_hit_count": 0,
        "scope": "all saved live-host task/directory records in m2_tight_directory_001 only; other M4 archives reviewed by parent/another reviewer",
        "plan": {"path": str(PLAN), "sha256": plan_sha},
        "source_inventory": {"root": str(SOURCE), "files": len(pins),
                             "bytes": sum(row["bytes"] for row in pins),
                             "sha256": inventory_sha, "unchanged_after_review": pins == after_pins,
                             "normalization": "sorted relative POSIX path; JSON object bytes/path/sha256 sorted keys compact separators plus LF", "pins": pins},
        "denominators": {"actual_host_task_sessions": len(cases),
                         "measurement": dict(measurement_stats),
                         "correctness_MCP_sessions": 2, "typed_worker_sessions": 1,
                         "ordered_records_including_one_typed_shutdown": len(all_records),
                         "read_business_records": len(all_records) - 1,
                         "product_directory_records": len(directories),
                         "product_directory_cache": dict(product_directory_states),
                         "classification_counts": dict(classification_counts),
                         "scripted_freshness_mutation_directory_records": len(mutation_records),
                         "natural_task_sessions": 0,
                         "same_host_resource_then_later_cached_directory_candidates": len(same_host_cached_candidates),
                         "new_directory_first_business_measurement_sessions": len(initial_new_directory_records),
                         "resource_counts_before_first_new_directory": first_resource_counts},
        "candidates": same_host_cached_candidates,
        "cases": cases,
        "non_task_and_non_host_exclusions": [
            {"path": "measurement/BUILD_INPUTS_PROCESS.json", "kind": "one real Blender asset builder; no directory/task trajectory"},
            {"path": "correctness/unit_01, correctness/unit_02", "kind": "offline fake bpy/unregistered runtime"},
            {"path": "measurement/NATIVE_CACHE_CHECK_01.json", "kind": "16 fake bpy notification cases; no live host"},
            {"path": "measurement/NATIVE_FORWARD_CHECK_01.json, measurement/NATIVE_FORWARD_CHECK_02.json", "kind": "fixed-input pure arithmetic"},
            {"path": "measurement/analysis_preflight_01", "kind": "reanalysis of two saved real preflight receipts; no additional session"},
            {"path": "installation", "kind": "build/install source snapshots; no task trajectory"}],
        "limitations": [
            "All 42 saved live hosts are scripted engineering/correctness episodes; actual Blender execution does not establish natural task demand.",
            "MCP functional archives retain public calls and current evaluated-coordinate oracles, without a full internal host RPC/resource stamp/pose snapshot. Unlogged internal calls and per-object compatibility are unknown.",
            "The 26 scripted freshness-mutation directories follow resource capture but include pose/geometry/unit/frame/name/instance/scene changes. Their current-resource compatibility is not inferred from shared document identity.",
            "The two directory_after_full records and typed directory_after_selected are already served by the existing directory cache.",
            "A native direct-code directory uses a separate implementation and cannot establish reuse of the product resident mesh resource.",
            "No CAPTURE_REPLAY archive contributes to live-host denominator.",
            "No claim is made that resource-first directory reuse is unreachable; no qualifying naturally required sequence is established by this bounded archive."],
        "operations": {"new_Blender_starts": 0, "product_imports": 0, "model_calls": 0,
                       "rasters": 0, "evaluators": 0, "product_edits": 0,
                       "old_tree_writes": 0, "installation_edits": 0},
        "errors": errors,
    }
    (HERE / "M2_TRACE_REVIEW.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = f"""# M2 既有真实宿主轨迹资格复核

本轮结论为 `{report['decision']}`，自然任务命中数为 0。仅覆盖旧 M2 归档，其他 M4 轨迹由根及其他复核人覆盖。

## 固定来源

计划 SHA 为 `{plan_sha}`，固定起点为 `{BASELINE}`。审查前固定旧 M2 全部 {len(pins)} 个文件，共 {report['source_inventory']['bytes']:,} 字节，清单摘要为 `{inventory_sha}`。分析后逐文件复核一致。完整相对路径、字节数和 SHA 均在 JSON 中。

## 分母与实际顺序

- 共 42 个真实 Blender 任务宿主，其中正式测量 36 个、测前检查 3 个、MCP 正确性 2 个、typed worker 1 个。
- 测量保存 321 条业务记录，逐条对应实际 WORKER_EVENTS 与原始 WIRE 请求。321 份代码 SHA 均一致，含清理的宿主事件及 WIRE 请求各为 360 条。
- 测量正式 27 个目录类会话各执行 cold 加 10 warm，另有 9 个目录类读取得 selected task 的会话。旧路用 overview，原生路执行独立目录代码，新产品路用 directory。
- 全部归档共 {len(all_records) - 1} 条业务读取，另有 1 条 typed shutdown。显式产品目录共 {len(directories)} 条，其中缓存命中 {product_directory_states['hit']} 条、未命中 {product_directory_states['miss']} 条。
- 新产品目录测量有 12 个宿主，首次业务请求均为目录，原始宿主事件显示此前驻留资源数全为 0。后续 selected task 后没有追加目录。

## 可疑序列的排除依据

`entry_01` 与 `entry_02` 的真实顺序均为 directory cold → directory warm → selected task → full overview → directory after full。最后一次目录明确 `cache_hit=true`，其 instance、epoch、revision 与前面的目录保持一致。两次分别处于独立 Blender 宿主。`entry_01` 的最终清理失败仍保留在分母和报告中。

typed 顺序为 directory cold → directory hot → capture task → directory after selected → full capture → shutdown。任务后的目录与 hot 保存文件逐字节相同，目录状态保持一致，明确命中缓存。

两次 MCP 正确性中另有 26 条人工场景变更后的目录读取。原请求由固定 QA 脚本产生，涉及姿态、几何、单位、帧、命名、替换、撤销、重做、场景和重载。当前矩阵 oracle 可读，旧资源 stamp/pose 快照缺失，逐对象兼容性为 unknown。它们没有构成自然资源先取、随后首次目录的任务证据。

## 排除范围与限制

资产构建另有 1 个实际 Blender 进程，执行任务目录请求为 0。离线 fake bpy、固定输入算术、对旧回执再分析和安装快照均单列。CAPTURE_REPLAY 的计入数为 0。

42 个宿主均来自脚本化工程测量或正确性验收。共享 host 或 document 身份不足以证明资源 stamp 与 pose 匹配。MCP 功能档只保留公开调用与当前 evaluated oracle，内部未记录调用和资源兼容性保留 unknown。

本次新增 Blender 启动、模型、raster、evaluator、产品导入、产品修改、旧树写入和安装改动均为 0。按计划可结束这部分资格，不据此生成产品候选或性能矩阵。

## 复核关联

复核人此前编写 M1 定向测试、A 归一化和运行复核，本次审查脚本也由复核人编写。旧 M2 产品与轨迹生产脚本由其他实施人产生，本报告交根独立复核。

错误数为 {len(errors)}。具体输入绑定、完整逐 case 顺序、原始请求路径、宿主 PID、缓存状态、计数与 unknown 均在 JSON 中。
"""
    (HERE / "M2_TRACE_REVIEW.md").write_text(text, encoding="utf-8")
    print(json.dumps({"decision": report["decision"], "hit_count": 0,
                      "cases": len(cases), "business_records": len(all_records) - 1,
                      "product_directory_records": len(directories),
                      "errors": errors,
                      "outputs": {name: digest((HERE / name).read_bytes()) for name in
                                  ("m2_trace_review.py", "M2_TRACE_REVIEW.json", "M2_TRACE_REVIEW.md")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
