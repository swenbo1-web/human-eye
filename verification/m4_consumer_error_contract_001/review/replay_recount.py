"""Read existing replay artifacts only. Never import or invoke the candidate."""

import copy
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
OUTPUT = BATCH / "offline/a01"
CHECKS = 0
INPUTS = {}


def check(value, label):
    global CHECKS
    CHECKS += 1
    if not value:
        raise ValueError(label)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    INPUTS[str(path)] = digest(raw)
    return raw


def load(path):
    return json.loads(read(path))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def same(left, right, label):
    check(canonical(left) == canonical(right), label)


def baseline(case, manifest):
    fixtures = [row for row in manifest["records"] if row["slot"] == case["slot"]]
    root = BATCH / "fixtures/slots" / case["slot"]
    calls = [{"perf_ns": row["CLI_perf_ns"], "type": "item.completed",
              "item": load(BATCH / "fixtures" / row["CLI_completed"])["item"]} for row in fixtures]
    responses = [load(BATCH / "fixtures" / row["response"]) for row in fixtures]
    tools = load(root / "owner/TOOLS.json")
    index = next((position for position, row in enumerate(fixtures) if row["fixture_id"] == case["fixture_id"]), 0)
    if case["variant"] == "owner_style":
        calls[index]["item"]["result"] = {"content": copy.deepcopy(calls[index]["item"]["result"]["content"]),
                                         "isError": responses[index]["result"]["isError"]}
    else:
        check(case["variant"] == "real", "known explicit representation baseline")
    return {"calls": calls, "responses": responses, "tools": tools}, fixtures, index


def expected_snapshot(state, operation, index):
    """Describe the registered data-only transformation for artifact comparison."""
    value = copy.deepcopy(state)
    item = value["calls"][index]["item"]
    response = value["responses"][index]
    simple = {
        "owner_flag_integer": (response["result"], "isError", 1),
        "cli_error_nonnull": (item, "error", {"message": "registered_non_null_error"}),
        "structured_nonnull": (item["result"], "structured_content", {}),
        "cli_extra_result": (item["result"], "unregistered_field", True),
        "owner_extra_result": (response["result"], "unregistered_field", True),
        "owner_wrong_rpc": (response, "jsonrpc", "1.0"),
        "owner_top_error": (response, "error", {"code": -32603, "message": "registered_RPC_error"}),
        "cli_wrong_type": (item, "type", "function_call"),
        "owner_content_string": (response["result"], "content", "registered_non_array"),
        "cli_content_string": (item["result"], "content", "registered_non_array"),
        "owner_id_bool": (response, "id", True),
        "owner_id_object": (response, "id", {}),
        "cli_tool_name": (item, "tool", "scene_data"),
    }
    if operation == "none":
        return value
    if operation in simple:
        parent, key, replacement = simple[operation]
        parent[key] = replacement
    elif operation == "flip_cli_status":
        item["status"] = "failed" if item["status"] == "completed" else "completed"
    elif operation == "flip_owner_flag":
        response["result"]["isError"] = not response["result"]["isError"]
    elif operation == "cli_error_missing":
        del item["error"]
    elif operation == "cli_flag_integer":
        item["result"]["isError"] = 1
    elif operation == "flip_cli_flag":
        item["result"]["isError"] = not item["result"]["isError"]
    elif operation == "change_text":
        block = next(block for block in item["result"]["content"] if block["type"] == "text")
        block["text"] += "!"
    elif operation == "change_image_data":
        block = next(block for block in item["result"]["content"] if block["type"] == "image")
        block["data"] = ("A" if block["data"][0] != "A" else "B") + block["data"][1:]
    elif operation == "change_image_mime":
        next(block for block in item["result"]["content"] if block["type"] == "image")["mimeType"] = "image/jpeg"
    elif operation == "swap_content_order":
        content = item["result"]["content"]
        content[0], content[1] = content[1], content[0]
    elif operation == "cli_arguments":
        item["arguments"]["code"] += "\n"
    elif operation == "swap_cli_order":
        value["calls"][0], value["calls"][1] = value["calls"][1], value["calls"][0]
    elif operation == "swap_owner_order":
        tools = value["tools"]["tools"]
        tools[0], tools[1] = tools[1], tools[0]
    elif operation == "owner_attempt_boolean":
        value["tools"]["tools"][0]["attempt"] = True
    elif operation == "drop_owner_last":
        value["tools"]["tools"].pop()
    elif operation == "drop_cli_last":
        value["calls"].pop()
    elif operation == "extra_cli_last":
        value["calls"].append(copy.deepcopy(value["calls"][-1]))
    elif operation == "delete_owner_response":
        value["responses"][index] = None
    elif operation == "response_id_value":
        response["id"] += 1
    elif operation == "response_id_float":
        response["id"] = float(response["id"])
    else:
        raise ValueError("unknown frozen mutation " + operation)
    return value


def verify_archive(folder, result):
    archive = load(folder / "consumer/ARCHIVE.json")
    binding = load(folder / "consumer/BUSINESS_SOURCE_BINDING.json")
    same(result["archive"], archive, "per-case published archive matches recorded return")
    same(result["result_contracts"], archive["result_contracts"], "actual archived result contracts")
    same(result["result_contracts"], binding["result_contracts"], "actual business result contracts")
    same(result["archive_errors"], archive["business_binding_errors"], "actual archive errors")
    same(result["archive_errors"], binding["binding_errors"], "actual business errors")
    for source in binding["sources"]:
        raw = read(source["original"])
        copied = read(folder / "consumer" / source["copy"])
        check(raw == copied and len(raw) == source["bytes"] and digest(raw) == source["sha256"],
              "case original-to-archive byte binding")
    raw_zip = read(archive["archive"])
    check(digest(raw_zip) == archive["archive_sha256"] and len(raw_zip) == archive["archive_bytes"], "archive physical ZIP")
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as bundle:
        names = bundle.namelist()
        check(len(names) == len(set(names)) and set(names) == set(archive["source_files_sha256"]), "exact archived members")
        for name, wanted in archive["source_files_sha256"].items():
            raw = read(folder / "consumer" / name)
            check(bundle.read(name) == raw and digest(raw) == wanted, "archive member source hash")


def main():
    frozen_raw = read(BATCH / "FROZEN.json")
    freeze_sha = digest(frozen_raw)
    check(freeze_sha == "76a163b53771564a86ac95460e89f986468c58bd36f0527f236b44e3b1e06083", "root frozen identity")
    frozen = json.loads(frozen_raw)
    check(len(frozen["files_sha256"]) == 996, "996 frozen files")
    for path, wanted in frozen["files_sha256"].items():
        check(digest(read(path)) == wanted, "frozen byte identity " + path)
    manifest = load(BATCH / "FIXTURE_MANIFEST.json")
    cases = load(BATCH / "CASES.json")
    results = load(OUTPUT / "RESULTS.json")
    check(results["freeze_sha256"] == freeze_sha, "recorded replay freeze")
    check([row["case_id"] for row in results["cases"]] == [row["case_id"] for row in cases["cases"]] and
          len(results["cases"]) == len(cases["cases"]) == 47, "complete frozen case order")
    expected_reasons = []
    mutations = []
    by_fixture = {row["fixture_id"]: row for row in manifest["records"]}
    for case, recorded in zip(cases["cases"], results["cases"]):
        folder = OUTPUT / "cases" / case["case_id"]
        actual_result = load(folder / "RESULT.json")
        same(recorded, actual_result, "aggregate and per-case result equality")
        check(recorded["exception"] is None and recorded["passed"] is True, "case actually completed")
        check(recorded["closed_ns"] - recorded["started_ns"] == recorded["elapsed_ns"] >= 0, "case time subtraction")
        same(load(folder / "consumer/TRANSFORMATION.json"), case, "actual case identity")
        initial, fixtures, index = baseline(case, manifest)
        expected_state = expected_snapshot(initial, case["mutation"], index)
        responses = []
        for fixture in fixtures:
            path = folder / "owner" / ("tool_" + str(fixture["attempt"]).zfill(2)) / "RESPONSE.json"
            responses.append(load(path) if path.exists() else None)
        actual_state = {"calls": load(folder / "consumer/CANDIDATE_CLI_ITEMS.json"),
                        "responses": responses, "tools": load(folder / "owner/TOOLS.json")}
        same(actual_state, expected_state, "only registered representation and variable changed")
        original_lines = b"".join(read(BATCH / "fixtures" / row["CLI_completed"]) for row in fixtures)
        check(read(folder / "consumer/ORIGINAL_CLI_COMPLETED_RAW.jsonl") == original_lines, "raw original CLI lines retained")
        for fixture in fixtures:
            source_folder = (BATCH / "fixtures" / fixture["response"]).parent
            target_folder = folder / "owner" / source_folder.name
            for filename in ("REQUEST.json", "RECEIPT.json"):
                check(read(target_folder / filename) == read(source_folder / filename), "request/code data and receipt unchanged")
        wanted = case["expected"]
        if case["scope"] == "matcher":
            binding = recorded["matcher"]
            check(binding["matched"] is False and binding["classification"] == "protocol_mismatch" and
                  binding["reason"] == wanted["matcher_reason"], "direct rejection actual reason")
            actual_reason = binding["reason"]
        else:
            verify_archive(folder, recorded)
            errors, faults = recorded["archive_errors"], recorded["shared_faults"]
            check(recorded["pipeline_matched"] is wanted["pipeline_matched"] and
                  recorded["pipeline_matched"] is (not errors and not faults), "pipeline outcome from actual errors")
            if wanted["primary_archive_reason"] is not None:
                check(bool(errors) and errors[0]["reason"] == wanted["primary_archive_reason"], "exact first archive reason")
            if wanted["primary_shared_reason"] is not None:
                check(bool(faults) and faults[0]["reason"] == wanted["primary_shared_reason"], "exact first shared reason")
            if wanted["matcher_reason"] is not None:
                binding = next(row for row in recorded["result_contracts"] if row["attempt"] == fixtures[index]["attempt"])
                check(binding["matched"] is False and binding["classification"] == "protocol_mismatch" and
                      binding["reason"] == wanted["matcher_reason"], "nested rejection actual reason")
            if wanted["pipeline_matched"]:
                check([row["classification"] for row in recorded["result_contracts"]] ==
                      [row["expected_classification"] for row in fixtures] and
                      all(row["matched"] is True for row in recorded["result_contracts"]), "positive classifications complete")
            actual_reason = None if not errors else errors[0]["reason"]
        expected_reasons.append({"case_id": case["case_id"], "scope": case["scope"],
            "expected_matcher_reason": wanted["matcher_reason"], "actual_primary_reason": actual_reason,
            "reason_checked": True})
        mutations.append({"case_id": case["case_id"], "variant": case["variant"], "mutation": case["mutation"],
                          "entire_stored_state_matches_only_registered_change": True})

    fixture_results = {row["fixture_id"]: row for row in results["real_fixture_results"]}
    check(len(fixture_results) == len(manifest["records"]) == 15, "15 unique original transactions")
    error_bodies = []
    for fixture in manifest["records"]:
        raw_line = read(BATCH / "fixtures" / fixture["CLI_completed"])
        raw_stdout = read(fixture["CLI_stdout_source"])
        offset = fixture["CLI_raw_byte_offset"]
        check(digest(raw_stdout) == fixture["CLI_stdout_sha256"] and digest(raw_line) == fixture["CLI_raw_line_sha256"] and
              raw_stdout[offset:offset + len(raw_line)] == raw_line, "true original CLI source/offset/hash")
        request = load(BATCH / "fixtures" / fixture["request"])
        response = load(BATCH / "fixtures" / fixture["response"])
        item = json.loads(raw_line)["item"]
        check(request["params"]["name"] == item["tool"], "original tool identity")
        same(request["params"]["arguments"], item["arguments"], "full original arguments")
        same(response["result"]["content"], item["result"]["content"], "original business body unchanged")
        actual = fixture_results[fixture["fixture_id"]]
        check(actual["binding"]["matched"] is True and actual["binding"]["classification"] ==
              fixture["expected_classification"], "real classification matches frozen fixture")
        if fixture["owner_isError"]:
            check(response["result"]["isError"] is True and item["status"] == "failed" and item["error"] is None,
                  "real business failure status preserved")
            body = response["result"]["content"]
            error = json.loads(body[0]["text"])["error"]
            error_bodies.append({"fixture_id": fixture["fixture_id"], "error_type": error["type"],
                "content_sha256": digest(canonical(body).encode("utf-8")),
                "content_UTF8_bytes": sum(len(block["text"].encode("utf-8")) for block in body if block["type"] == "text")})
    check(Counter(row["binding"]["classification"] for row in fixture_results.values()) ==
          {"success": 13, "tool_error": 2}, "13 successful and 2 business-error classifications")
    exact_controls = []
    for case_id in ("exact_success_status_wrong", "exact_error_status_wrong"):
        case = next(row for row in cases["cases"] if row["case_id"] == case_id)
        folder = OUTPUT / "cases" / case_id
        fixture = by_fixture[case["fixture_id"]]
        item = next(row["item"] for row in load(folder / "consumer/CANDIDATE_CLI_ITEMS.json")
                    if row["item"]["id"] == fixture["CLI_item_id"])
        response = load(folder / "owner" / ("tool_" + str(fixture["attempt"]).zfill(2)) / "RESPONSE.json")
        same(item["result"], response["result"], "exact-body control really has equal raw result envelopes")
        check(load(folder / "RESULT.json")["pipeline_matched"] is False, "state mismatch rejects identical raw envelope")
        exact_controls.append({"case_id": case_id, "raw_result_equal": True, "rejected": True})

    original_run = load(BATCH / "fixtures/RUN_RESULT_ORIGINAL.json")
    old_rows = {row["slot"]: row for row in original_run["records"]}
    state_rows = {row["slot"]: row for row in results["historical_invariants"]["slots"]}
    histories = []
    for state in manifest["slots"]:
        slot = state["slot"]
        consumer = load(BATCH / "fixtures/slots" / slot / "CONSUMER_ORIGINAL.json")
        same(state["usage"], consumer["usage"], "original usage dictionary unchanged")
        same(state["raw_usage_events"], consumer["raw_usage_events"], "original raw usage events unchanged")
        check(state["original_execution_state"] == old_rows[slot]["execution_state"] == state_rows[slot]["original_execution_state"] and
              state["interrupted_stream_usage_coverage"] == consumer["summary"]["interrupted_stream_usage_coverage"] ==
              state_rows[slot]["interrupted_stream_usage_coverage"], "original state and unknown usage boundary")
        same(state["top_level_errors"], state_rows[slot]["top_level_errors_preserved"], "actual stream errors preserved")
        check(digest(read(BATCH / "fixtures/slots" / slot / "PUBLIC_FINAL.txt")) == state["final_sha256"], "old final unchanged")
        histories.append({"slot": slot, "state": state["original_execution_state"],
            "usage": state["usage"], "interrupted_stream_usage_coverage": state["interrupted_stream_usage_coverage"]})
    check(Counter(row["state"] for row in histories) == {"completed": 4, "failed": 2}, "old 4/2 remains")
    check(state_rows["N3"]["candidate_event_projection_only_valid"] is False and
          state_rows["N3"]["top_level_errors_preserved"] and
          state_rows["N3"]["interrupted_stream_usage_coverage"] == "unknown", "N3 strict stream gate preserved")
    check(results["connections"] and all(value is True for value in results["connections"].values()), "actual connection assertions recorded true")
    check(results["forbidden_operation_attempts"] == [] and results["new_Pro_provider_CLI_actor_Blender_raster_calls"] == 0 and
          results["original_tool_code_executed"] is False, "data-only replay boundaries")
    check(results["closed_before_result_publication_ns"] - results["started_ns"] == results["elapsed_ns"], "local replay elapsed subtraction")
    report = {"schema": "consumer-error-contract-001-independent-replay-review-v1", "status": "passed",
        "review_role": "Author-side independent artifact recount. Candidate matcher implementation agent reviewing other agents' replay and connections.",
        "checks_passed": CHECKS, "source_files_unchanged": 996, "freeze_sha256": freeze_sha,
        "candidate_or_matrix_executed_by_reviewer": False, "reviewer_new_online_renderer_calls": 0,
        "observed_case_counts": {"passed": 47, "failed": 0, "not_run": 0},
        "real_original_transactions": {"count": 15, "success": 13, "tool_error": 2},
        "case_groups": {"real_full_slot_positive": 6, "derived_owner_style_positive": 4,
                        "pipeline_negative": 35, "direct_matcher_negative": 2},
        "actual_error_bodies_preserved": error_bodies, "identical_result_status_rejections": exact_controls,
        "case_reason_review": expected_reasons, "transformation_review": mutations,
        "historical_slots_unchanged": histories, "old_execution_counts": {"completed": 4, "failed": 2, "not_run": 0},
        "N3_top_level_stream_rejection_preserved": True,
        "recorded_local_replay_elapsed_ns": results["elapsed_ns"],
        "limitations": ["This review reads stored artifacts and frozen source. It does not invoke the candidate or rerun any case.",
            "Derived owner-style controls remain distinct from15 original CLI transactions.",
            "The47-case finite scope has no separate derived content-body bool/int mutation. CanonicalJSON handling is source-reviewed.",
            "Historical execution, interrupted usage coverage and the closed three-pair benefit gate remain unchanged."],
        "script_sha256": digest(Path(__file__).read_bytes()), "inputs_sha256": dict(sorted(INPUTS.items()))}
    (HERE / "REPLAY_INDEPENDENT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 离线错误合同重放的独立复核", "",
        f"已完成 {CHECKS} 项只读原件与结果复核，996 份冻结文件保持一致。候选函数、原工具代码字符串与验收矩阵均未在本复核中执行。作者侧复核与管理员终审分别留存。", "",
        "47 项结果与冻结 CASES 逐项一致，实际 archive/shared 首个拒绝原因和嵌套 matcher 原因均符合登记。每份案例的实际 JSON 快照只包含所登记的形态及单变量变化，archive 原件副本和 ZIP 成员逐字节核对。", "",
        "6 个真实整槽正例包含15条真实CLI原行与对应owner交易，结果为13 success、2 tool_error。4个owner-style正例是明确派生形态，35个调用链负例与2个直接matcher负例分别列账。旧stdout偏移、原始行哈希、工具名、参数和业务正文全部核对。", "",
        "两个业务错误正文分别保留 N1 的 SyntaxError 和 N3 的 ValueError。CLI status=failed、error=null及原有content保持，候选分类为tool_error。原样result完全相等但状态错误的成功/业务错误控制均被拒，保留cli_status_mismatch原因。", "",
        "六槽原答案、usage对象和原执行状态保持原字节与含义，旧结果仍为4 completed、2 failed、0 not_run。N1的新绑定匹配只构成协议候选重放。N3的顶层重连错误继续使事件投影门为false，中断流usage覆盖仍为unknown。", "",
        f"唯一既有矩阵的记录耗时为 {results['elapsed_ns']/1e9:.7f} 秒，截止最终RESULTS发布前。这属于本地协议重放成本。新增Pro、provider、CLI、actor服务、Blender和光栅均记录为0，实际连接指针断言全部通过。", "",
        "本轮有限47项保留原范围，content-body bool/int单列派生反例未纳入。严格canonicalJSON与类型处理已作源码复核，当前结论限于上述原件及控制，不形成新的真实模型或三配对收益结论。", ""]
    (HERE / "REPLAY_INDEPENDENT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "passed", "checks": CHECKS, "cases": 47, "real_transactions": 15,
                      "classifications": {"success": 13, "tool_error": 2}, "candidate_executed": False}))


if __name__ == "__main__":
    main()
