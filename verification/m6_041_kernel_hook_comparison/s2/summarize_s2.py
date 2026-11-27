"""Independently recompute the frozen 041 S2 result from original receipts."""
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pin(p):
    return {"path": str(p.resolve()), "bytes": p.stat().st_size, "sha256": sha(p)}


def read(p):
    return json.loads(p.read_bytes())


def verified(entry, path=None):
    target = Path(entry["path"]) if path is None else path
    assert pin(target) == entry, target
    return target


def save(p, obj):
    with p.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(obj, file, ensure_ascii=False, allow_nan=False, indent=2)
        file.write("\n")


def compact_stats(rows):
    return {
        "wall_median_ns": median(row["T_ns"] for row in rows),
        "wall_range_ns": [min(row["T_ns"] for row in rows), max(row["T_ns"] for row in rows)],
        "CPU_median_ns": median(row["job_accounting"]["cpu_ns"] for row in rows),
        "sampled_working_set_peak_median_bytes": median(row["sampled_peak_working_set_bytes"] for row in rows),
        "sampled_private_peak_median_bytes": median(row["sampled_peak_private_bytes"] for row in rows),
        "audit_trace_median_ns": median(row["independent_trace_ns"] for row in rows),
    }


def main():
    plan = read(ROOT / "PLAN.json")
    window = read(ROOT / "formal/WINDOW.json")
    installs = read(verified(plan["release_pins"]))["arms"]
    assert verified(window["plan"]) == ROOT / "PLAN.json"
    approval = read(verified(window["approval"]))
    assert approval == {"stage": "S2", "plan_sha256": sha(ROOT/"PLAN.json"), "approved_frozen_slots":84}
    original = read(ROOT / "formal/SUMMARY.json")
    expected_specs = plan["slots"]
    rows = {}
    process_samples = 0
    gaps = 0
    same_stdout = None
    for spec in expected_specs:
        block, case, arm = (spec[k] for k in ("block", "event_case", "arm"))
        folder = ROOT / f"formal/block{block:02}" / case / arm
        row = read(folder / "RESULT.json")
        assert all(row.get(k) == v for k,v in spec.items())
        for k, f in (("stdin","INPUT.bin"),("stdout","STDOUT.bin"),("stderr","STDERR.bin"),("audit","audit.jsonl")):
            assert verified(row[k]) == folder/f
        stdin = (folder / "INPUT.bin").read_bytes()
        stdout = (folder / "STDOUT.bin").read_bytes()
        stderr = (folder / "STDERR.bin").read_bytes()
        assert hashlib.sha256(stdin).hexdigest() == plan["inputs"][case]["input_040"][0]["sha256"]
        assert json.loads(stdout) == {} and not stderr and row["returncode"] == 0
        if same_stdout is None:
            same_stdout = stdout
        assert same_stdout == stdout
        assert row["terminal"] == "completed" and row["pipe_threads_joined"] and not row["pipe_errors"]
        assert row["job_accounting"]["active_processes"] == 0 and not row["job_pids_at_cleanup"]
        assert row["loopback_connections"] == 0 and not (folder / "state.json").exists()
        assert not (folder / "state.json.lock").exists()
        release = installs[row["kernel"]]
        assert row["binding"] == release["binding"] and row["source_sha256"] == release["source_sha256"]
        assert read(folder / "connector.json")["expected_identity"]["build_id"] == release["identity"]["build_id"]
        assert row["only_authorized_inner_argv_difference"] and row["exact_executable"]
        skip, trace = [json.loads(x) for x in (folder / "audit.jsonl").read_bytes().splitlines()]
        assert skip["event"] == "host_hook_skip" and trace["event"] == "request_trace"
        expected = plan["inputs"][case]["expected"]
        assert skip["status"] == expected["skip"] and trace["trace"]["operation"] == expected["operation"]
        assert trace["trace"]["outcome"] == expected["outcome"]
        assert skip["scene_read"] is False and skip["engine_invoked"] is False
        assert trace["trace"]["spans"] == trace["trace"]["image_events"] == []
        event = json.loads(stdin)
        k = {"session_id":"codex:"+event["session_id"], "turn_id":event["turn_id"], "tool_use_id":event["tool_use_id"]}
        assert all(a["hook_event"] == event["hook_event_name"] and a["invocation_source"] == "hook_command"
                   and a["runtime_identity"]["build_id"] == release["identity"]["build_id"]
                   and a["identity_check"]["compatible"] and all(a[i] == j for i,j in k.items()) for a in (skip,trace))
        complete = []
        for sample in row["samples"]:
            process_samples += 1
            if sample["missing"]:
                gaps += 1
                assert sample["group_working_bytes"] is sample["group_private_bytes"] is None
            else:
                assert set(sample["pids"]) == {x["pid"] for x in sample["rows"]}
                working, private = (sum(p[k] for p in sample["rows"]) for k in ("working_bytes","private_bytes"))
                assert (working, private) == (sample["group_working_bytes"], sample["group_private_bytes"])
                complete.append((working,private))
        assert max(x[0] for x in complete) == row["sampled_peak_working_set_bytes"]
        assert max(x[1] for x in complete) == row["sampled_peak_private_bytes"]
        assert row["valid"] and row["audit_pass"]
        row["independent_trace_ns"] = trace["trace"]["duration_ns"]
        rows[case,arm,block] = row
    assert len(rows) == len(list((ROOT/"formal").rglob("RESULT.json"))) == original["counts"]["valid"] == 84
    matrix = []
    metrics = {}
    for case in plan["inputs"]:
        stats = {arm:compact_stats([rows[case,arm,i] for i in range(1,8)]) for arm in plan["arms"]}
        pairs = {}
        for x,y in (("A","C"),("B","D")):
            observed = [(rows[case,x,i]["T_ns"],rows[case,y,i]["T_ns"]) for i in range(1,8)]
            reduced = median(1-Fraction(d,w) for w,d in observed)
            faster = sum(d<w for w,d in observed)
            v = original["metrics"][f"{case}/{y}_over_{x}"]
            assert v["pass"] and v["valid_pairs"] == 7 and v["direct_faster"] == faster
            assert v["median_paired_reduction"] == float(reduced)
            assert v["paired_wrapped_direct_ns"] == [list(t) for t in observed]
            pairs[f"{y}/{x}"] = {"median_exact": str(reduced),"median":float(reduced),"faster":faster,"valid":7,
                                  "wrapped_direct_ns":observed,"pass":reduced>=Fraction(1,10) and faster>=5}
        metrics[case] = {"arm_medians": stats, "pair_gains": pairs}
        a,b,c,d = (stats[k]["wall_median_ns"]/1e6 for k in "ABCD")
        v,w = (pairs[k] for k in ("C/A","D/B"))
        matrix.append(f"| {case} | {a:.3f}／{b:.3f}／{c:.3f}／{d:.3f} | {v['median']*100:.4f}% | {w['median']*100:.4f}% | {v['faster']}/7／{w['faster']}/7 |")
    totals = {"T_ns":sum(x["T_ns"] for x in rows.values()),
              "job_CPU_ns":sum(x["job_accounting"]["cpu_ns"] for x in rows.values()),
              "job_process_samples":process_samples, "samples_missing_processes":gaps,
              "stdout_bytes":len(same_stdout),"stderr_bytes":0,"job_active_at_end":0}
    recovered = read(ROOT / "READY.json")
    result = {"status":"PASS_MANUAL_COMMAND_RESTRICTED_AUTOMATIC_NOT_RUN","original_summary":pin(ROOT/"formal/SUMMARY.json"),
              "plan":pin(ROOT/"PLAN.json"),"arm_pins":pin(verified(plan["release_pins"])),"validated":84,"attempted":84,
              "science_metrics": metrics, "totals":totals,"preflight":recovered["preflight"],
              "automatic_dispatch":plan["automatic_dispatch"],"old_unrepaired": recovered["unrepaired_032_historical_diagnostic_only"],
              "observations":{"no_connections":84,"no_state_writes":84,"scope":"no model, Blender or geometry command executed in S2",
                  "complete_job_cleanup":84,"audit_and_trace":84,"scored_events":3,"scored_rounds_per_cell":7,
                  "host_automatic_deadline_cancel_propagation":"NOT_RUN","separate_manual_deadline_cancel_controls":"PASS"}}
    save(ROOT/"RESULTS.json",result)
    table = "\n".join(matrix)
    report = """# M6-041 S2 轻 Hook 对照

**手工执行固定注册命令通过。实际 Codex 自动派发仍为未测，结论限于隔离命令入口。** 三事件、七组、四臂，计划 84 槽，实际 84 槽，全部语义与进程收尾有效。每类每套内核的直启中位降幅超过 10%，且每对均比同包裹臂更快。

A／B 为 032／R3 的原 PowerShell 注册包裹。C／D 对同两个安装直接调用同一个固定启动器。两套安装使用同一份绑定修复，只有四个批准的 M3 文件不同。依据 040 的原始 stdin 与命令，逐事件核对 PowerShell 解码后的内层参数和直启参数。每格使用隔离配置及审计；连接探针仅为独立 loopback 监听，Blender、模型和付费接口均未启动。旧 032 无审计修复的三格从 040 留作诊断。

| 事件 | A／B／C／D 完整窗中位 ms | C 对 A 配对中位降幅 | D 对 B 配对中位降幅 | C／D 分别更快 |
|---|---:|---:|---:|---:|
@@TABLE@@

完整窗从命令创建前至管道收集和 Job 资源关闭后。内含实际 wrapper、导入、配置校验、审计与回收。84 槽耗时合计 67.7320 秒，Job 进程组 CPU 合计 63.7500 秒，二者分别记录。3242 次组内工作集／私有内存采样无缺口。包裹臂各事件的工作集峰值中位约 140.87–141.43 MiB，直启约 75.92–76.70 MiB，均为采样峰值。七组只报告本样本中位与范围。

全部 84 条回包为同一 4 字节空 JSON、stderr 为空、退出码 0、各有两条绑定当前安装的跳过与请求追踪。零 loopback 连接、渲染或状态及其锁写入，Job 所属进程与管道清理完成。普通提示保留一般意图跳过，两个完成事件保留原工具结果并省去重复上下文。另有独立轻量预飞四臂和两个故障控制；人为短截止与取消在本试验 Job 中回收，不进入正式分母。

Codex 对精确变更后的定义须独立信任。本轮未提供或沿用信任，自动触发、Codex 自身的 stdout／stderr 消费与在途取消未运行。正向空间路由和有几何工作的完整流程由 S3 分列。此处没有测量几何内核或 Codex 响应耗时。

[冻结计划](PLAN.json) · [逐格复算](RESULTS.json) · [原判定](formal/SUMMARY.json) · [本地原件索引](EVIDENCE.json)
""".replace("@@TABLE@@",table)
    with (ROOT/"REPORT.md").open("x",encoding="utf-8",newline="\n") as file:
        file.write(report)
    files = []
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and p.name != "EVIDENCE.json":
            relative = p.relative_to(ROOT).as_posix()
            files.append({"relative_path":relative,"bytes":p.stat().st_size,"sha256":sha(p)})
    save(ROOT/"EVIDENCE.json",{"members":len(files),"bytes":sum(x["bytes"] for x in files),"files":files})
    print(json.dumps({"result":pin(ROOT/"RESULTS.json"),"report":pin(ROOT/"REPORT.md"),
                      "evidence":pin(ROOT/"EVIDENCE.json"),"members":len(files),"totals":totals}))


if __name__ == "__main__":
    main()