"""Read the two completed local controls. No candidate or service invocation."""

from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
BATCH = HERE.parent
CHECKS = 0
INPUTS = {}
FINAL_LAUNCHER_SHA = "e417a231f7db68d552a56db3f0b94527514c49afdee56a629bbb2f4056ca750c"


def check(value, label):
    global CHECKS
    CHECKS += 1
    if not value:
        raise ValueError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    INPUTS[str(path)] = sha(raw)
    return raw


def load(path):
    return json.loads(read(path))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def same(left, right, label):
    check(canonical(left) == canonical(right), label)


def held_cleanup(value, pid, label):
    check(value["pid"] == pid and value["confirmed"] is True and value["reaped"] is True and
          value["process_handle_closed"] is True and value["exit_code"] == 0 and
          value["kill_requested"] is False and value["errors"] == [], label + " held exit0 without kill")
    check(value["pipes_closed"] == {"stdin": True, "stdout": True, "stderr": True}, label + " all pipes")
    check(value["closed_ns"] - value["started_ns"] == value["elapsed_ns"] >= 0, label + " clock")


def archive_check(descriptor, base, fields):
    raw = read(descriptor[fields[0]])
    check(sha(raw) == descriptor[fields[1]] and len(raw) == descriptor[fields[2]], "actual archive bytes/hash")
    wanted = descriptor[fields[3]]
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        check(len(names) == len(set(names)) and set(names) == set(wanted), "complete archive inventory")
        for name, expected in wanted.items():
            original = read(base / name)
            check(sha(original) == expected and archive.read(name) == original, "archive member byte identity")


def group_check(group, frozen):
    parent = BATCH / "local" / (group + "1")
    result = load(parent / "LOCAL_RESULT.json")
    row = result["route"]
    route = Path(row["folder"])
    consumer_directory = Path(row["consumer_output"])
    owner = Path(row["owner_output"])
    consumer = load(consumer_directory / "CONSUMER.json")
    fixture = load(consumer_directory / "LOCAL_FIXTURE.json")
    metrics = load(owner / "METRICS.json")
    observations = load(owner / "OBSERVATIONS.json")
    check(result["group"] == group and result["attempt"] == 1 and result["passed"] is True and
          result["readback_error"] is None, group + " first actual local pass")
    check(result["source_unchanged"] is True and result["pointer_chain_unchanged"] is True,
          group + " source and pointers preserved")
    launcher_path = str((BATCH / "launcher.py").resolve())
    check(result["execution_sources_sha256"][launcher_path] == FINAL_LAUNCHER_SHA == frozen["files_sha256"][launcher_path],
          group + " actual local used final launcher source")
    for path, expected in result["execution_sources_sha256"].items():
        check(frozen["files_sha256"][path] == expected and sha(read(path)) == expected,
              group + " source matches current formal freeze")
    before = load(parent / "POINTERS_BEFORE.json")
    after = load(parent / "POINTERS_AFTER.json")
    same(before, after, group + " same actual runtime pointers")
    check(before["checks"] and all(before["checks"].values()), group + " actual candidate pointer checks")
    check(consumer["execution_kind"] == row["execution_kind"] == "synthetic_local_process" and
          Path(consumer["argv"][3]).resolve() == BATCH / "fake_cli.py", group + " actual fake Python command")
    check(row["outer_valid_completion"] is True and row["consumer_valid_completion"] is True and
          row["consumer_safe_to_continue"] is True and row["common_image_faults"] == row["errors"] == [] and
          consumer["valid_completion"] is True and consumer["safe_to_continue"] is True and consumer["errors"] == [],
          group + " archive and outer actual completion")
    deadline = row["deadline_ns"]
    check(deadline - row["started_ns"] == 450 * 10**9 and fixture["original_deadline_ns"] ==
          consumer["deadline_ns"] == consumer["episode_deadline_ns"] == deadline, group + " unchanged absolute deadline")
    raw_stdout = read(consumer_directory / "stdout.raw.bin")
    events = [json.loads(line) for line in raw_stdout.splitlines()]
    check(len(raw_stdout) == consumer["stdout_bytes"] == consumer["stdout_raw_bytes"] and
          sha(raw_stdout) == consumer["stdout_raw_sha256"], group + " literal stdout")
    actual_tools = [event["item"] for event in events if event["type"] == "item.completed" and
                    event.get("item", {}).get("type") == "mcp_tool_call"]
    same(actual_tools, [call["item"] for call in consumer["tool_calls"]], group + " raw CLI tool projection")
    check(len(actual_tools) == metrics["tool_attempts"] == 2 and len(fixture["tool_results"]) == 2,
          group + " exactly two common Python tools")
    expected_codes = ["raise ValueError('newlocal_m4_active_coverage_consumption_002_value_error')", "print(6 * 7)"]
    contracts = load(consumer_directory / "BUSINESS_SOURCE_BINDING.json")
    check(contracts["binding_errors"] == [] and
          [value["classification"] for value in contracts["result_contracts"]] == ["tool_error", "success"] and
          all(value["matched"] is True for value in contracts["result_contracts"]), group + " true unified error/success binding")
    same(contracts["result_contracts"], consumer["archive"]["result_contracts"], group + " archive classifications")
    for number, item in enumerate(actual_tools, 1):
        folder = owner / ("tool_" + str(number).zfill(2))
        request = load(folder / "REQUEST.json")
        response = load(folder / "RESPONSE.json")
        check(request["params"]["name"] == item["tool"] == "execute_python" and
              request["params"]["arguments"] == item["arguments"] == {"code": expected_codes[number - 1]},
              group + " only new harmless literal Python")
        check(type(response["result"]["isError"]) is bool and response["result"]["isError"] is (number == 1),
              group + " actual owner error/success flag")
        check(item["status"] == ("failed" if number == 1 else "completed") and "error" in item and item["error"] is None and
              set(item["result"]) == {"content", "structured_content"} and item["result"]["structured_content"] is None,
              group + " actual observed CLI result envelope")
        same(item["result"]["content"], response["result"]["content"], group + " complete unchanged business content")
        same(fixture["tool_results"][number - 1]["CLI_item"], item, group + " fixture actual event journal")
        body = json.loads(response["result"]["content"][0]["text"])
        if number == 1:
            same(body["error"], {"type": "ValueError", "message": "newlocal_m4_active_coverage_consumption_002_value_error"},
                 group + " actual requested ValueError")
        else:
            check(body["stdout"] == "42\n" and body["error"] is None, group + " actual recovery 42")
        for name in ("REQUEST.json", "RESPONSE.json", "RECEIPT.json"):
            check(read(folder / name) == read(consumer_directory / "owner_turn" / folder.name / name),
                  group + " actual original business archive copy")
    bridges = list((consumer_directory / "attachments").glob("bridge_*"))
    check(len(bridges) == 1, group + " one actual held stdio")
    bridge = bridges[0]
    rpc_folders = sorted(folder for folder in bridge.iterdir() if folder.is_dir())
    check(len(rpc_folders) == len(fixture["RPC"]) == 4, group + " initialize/list/two-tool RPC count")
    for folder, rpc in zip(rpc_folders, fixture["RPC"]):
        tx, rx = read(folder / "TX.bin"), read(folder / "RX.bin")
        same(json.loads(tx), rpc["request"], group + " actual transmitted request")
        same(json.loads(rx), rpc["response"], group + " actual received response")
        check(len(tx) == rpc["request_bytes"] and len(rx) == rpc["response_bytes"], group + " actual RPC byte observations")
    check(fixture["passed"] is True and fixture["error"] is None and fixture["normal_EOF_requested"] is True and
          fixture["normal_exit_observed"] is True and fixture["runtime_binding_confirmed"] is True and
          fixture["thin_wait_exit_code"] == 0, group + " actual EOF recovery fixture completion")
    check(consumer["final"] == "LOCAL_RECOVERED_42" and read(consumer_directory / "final.txt") ==
          read(consumer_directory / "PUBLIC_FINAL.txt") == b"LOCAL_RECOVERED_42", group + " actual final after recovery")
    binding = load(consumer_directory / "RUNTIME_BINDING.json")
    same(binding, fixture["runtime_binding"], group + " same live binding proof")
    same(binding, consumer["runtime_binding"], group + " consumer retained original proof")
    started = load(bridge / "STARTED.json")
    exited = load(bridge / "EXIT.json")
    thin_pid = fixture["thin_pid"]
    check(thin_pid == binding["runtime_pid"] == started["pid"] == exited["pid"] and fixture["pid"] ==
          consumer["consumer_pid"] == binding["launcher_pid"], group + " original process identity")
    check(binding["confirmed"] is True and binding["after_stdio_STARTED"] is True and
          started["started_ns"] <= binding["proved_ns"] <= binding["actual_image_checked_ns"] <=
          fixture["normal_EOF_requested_ns"] <= exited["ended_ns"], group + " live proof precedes ordinary EOF")
    check(binding["actual_executable"] == binding["expected_executable"] and
          binding["actual_executable_sha256"] == binding["expected_executable_sha256"], group + " actual base interpreter")
    check(exited["normal_exit"] is True and consumer["bridge_cleanup"]["confirmed"] is True,
          group + " thin normal EXIT receipt")
    held_cleanup(fixture["thin_cleanup"], thin_pid, group + " fake-owned thin handle")
    held_cleanup(consumer["process_cleanup"], fixture["pid"], group + " consumer-owned fake CLI handle")
    held_cleanup(row["owner_process_cleanup"], row["owner_pid"], group + " original actor handle")
    held_exit = consumer["runtime_exit"]
    check(held_exit["confirmed"] is True and held_exit["exited"] is True and held_exit["handle_closed"] is True and
          held_exit["exit_code"] == 0 and held_exit["original_deadline_ns"] == deadline,
          group + " independently retained thin handle exit0")
    check(row["owner_close_confirmed"] is True and row["input_readback_unchanged"] is True,
          group + " actor close/source readback")
    zero_fields = ("constructed_image_blocks", "failed_image_constructions", "post_construction_failures",
        "constructed_PNG_bytes", "constructed_base64_chars", "server_socket_sent_image_blocks", "new_renders")
    check(all(metrics[field] == 0 for field in zero_fields) and metrics["common"]["render_attempts"] == 0 and
          metrics["common"]["runtime_faults"] == [] and observations["render_attempts"] == observations["frames"] == [] and
          observations["active"] is None, group + " actual zero image/render/active attempts")
    traces = [json.loads(line) for line in read(owner / "TRACE.jsonl").splitlines()]
    check(not any(event["event"] in ("render_attempt", "image_constructed") for event in traces), group + " no hidden render/image trace")
    check(consumer["public_image_count"] == consumer["public_image_bytes"] == 0 and
          result["new_Pro_sessions"] == result["new_renders"] == result["new_image_constructions"] == 0,
          group + " observed local budget")
    usage = [event["usage"] for event in events if event["type"] == "turn.completed"]
    check(len(usage) == 1 and all(value == 0 for value in usage[0].values()), group + " synthetic usage zero")
    archive = load(consumer_directory / "ARCHIVE.json")
    archive_check(archive, consumer_directory, ("archive", "archive_sha256", "archive_bytes", "source_files_sha256"))
    archive_check(row["originals"], route, ("path", "sha256", "bytes", "members_sha256"))
    return {"group": group, "attempt": 1, "passed": True, "actual_launcher_sha256": FINAL_LAUNCHER_SHA,
        "new_tool_codes": expected_codes, "classifications": ["tool_error", "success"], "final": "LOCAL_RECOVERED_42",
        "CLI_statuses": ["failed", "completed"], "CLI_error_values": [None, None],
        "normal_EOF": True, "normal_thin_exit_code": 0, "thin_pid": thin_pid,
        "fake_CLI_pid": fixture["pid"], "actor_pid": row["owner_pid"],
        "original_handle_cleanup_confirmed": True, "runtime_live_binding_and_retained_exit": True,
        "new_Pro_sessions": 0, "image_constructions": 0, "render_attempts": 0}


def main():
    frozen_raw = read(BATCH / "FROZEN.json")
    check(sha(frozen_raw) == "1f9527f844b58a3e9719a2c0130c1cd1ad19c05a815bb39b975fb256b2a6680e", "actual formal freeze")
    frozen = json.loads(frozen_raw)
    check(len(frozen["files_sha256"]) == 188, "188 execution/scoring source closure")
    for path, wanted in frozen["files_sha256"].items():
        check(sha(read(path)) == wanted, "frozen source remains unchanged")
    check(sha(read(BATCH / "launcher.py")) == FINAL_LAUNCHER_SHA, "final corrected launcher")
    groups = [group_check(group, frozen) for group in ("N", "P")]
    check(not (BATCH / "local/N2").exists() and not (BATCH / "local/P2").exists(), "both controls passed on first invocation")
    result = {"schema": "active-coverage-consumption-002-local-independent-v1", "status": "passed",
        "review_role": "Fixture implementation agent performing read-only source/RPC/archive/lifecycle recount.",
        "checks_passed": CHECKS, "frozen_file_count": 188, "freeze_sha256": sha(frozen_raw),
        "actual_final_launcher_sha256": FINAL_LAUNCHER_SHA, "groups": groups,
        "local_denominator": {"planned": 2, "completed": 2, "failed": 0, "not_run": 0},
        "actual_local_tool_calls": 4, "actual_local_fake_CLI_processes": 2,
        "actual_local_stdio_processes": 2, "actual_local_actor_processes": 2,
        "new_Pro_sessions": 0, "new_render_attempts": 0, "new_image_constructions": 0,
        "candidate_or_local_reexecuted_by_reviewer": False,
        "formal_answers_quality_or_cost_accessed": False,
        "source_revision_scope": "Both actual local controls recorded final e417 launcher after its local-only static corrections. Frozen actor/common/image/lifecycle source dependencies remain inherited.",
        "script_sha256": sha(Path(__file__).read_bytes()), "inputs_sha256": dict(sorted(INPUTS.items()))}
    (HERE / "LOCAL_INDEPENDENT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 两路本地错误恢复检查的独立回读", "",
        f"只读复核通过 {CHECKS} 项，188份冻结来源保持一致。N1、P1均在第一次实际本地调用通过，未发生本地复测。本次复核仅查看已存本地资料，正式答案、质量和成本未在本复核读取。", "",
        "两路实际使用最终修正后的 launcher，SHA256均为 `" + FINAL_LAUNCHER_SHA + "`。该来源同时存在于每路执行来源记录、当前文件和正式冻结清单。末尾局部静态修正已纳入这两次实际控制。", "",
        "每路实际提交两条新写的普通Python。第一条raise带newlocal消息的ValueError，owner真实返回isError=true，CLI原行status=failed、error=null，content完整保留并附structured_content=null。第二条print(6*7)真实得到42，owner返回isError=false，CLI完成状态正确。候选archive分类依次为tool_error与success，业务绑定、共同故障和outer记录全部通过。", "",
        "四次实际MCP RPC为initialize、tools/list及两次工具请求。stdio TX/RX、fake RPC记录、owner请求/响应、CLI原stdout、business副本和两级ZIP逐份核对。最终LOCAL_RECOVERED_42由真实工具stdout产生，两路原始usage均为合成0。", "",
        "两路均在真实STARTED与Windows运行时绑定证明之后正常关闭stdio stdin。正常EXIT回执存在，thin exit0，fixture持有的thin Popen、consumer持有的fake CLI Popen、launcher持有的actor Popen均以原句柄回收，kill_requested=false，三管道与句柄关闭。consumer另持有的只读thin句柄也确认exit0并关闭。原450秒绝对期限贯穿，未重置。", "",
        "本地共有2个fake CLI、2个stdio和2个actor进程，实际工具4次。真实Pro、光栅、图片构造与交付均为0。owner完整账本、空render_attempts/frames和TRACE再次核对了零尝试。该记录验证接线与恢复，后续正式六槽依原冻结任务单独验收。", ""]
    (HERE / "LOCAL_INDEPENDENT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"checks": CHECKS, "local_groups": 2, "all_passed": True, "new_Pro": 0,
                      "new_render_or_image_construct": 0, "actual_launcher": "e417a231"}))


if __name__ == "__main__":
    main()
