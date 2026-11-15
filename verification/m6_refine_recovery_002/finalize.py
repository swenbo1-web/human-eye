"""Recheck source preservation and produce the bounded recovery delivery."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare import HERE, OLD, ROOT, BASELINE, identity, write


def read(path):
    return json.loads(path.read_bytes())


def main():
    started = time.perf_counter()
    control = read(HERE / "CONTROL_SUMMARY.json")
    actual = read(HERE / "ACTUAL_SUMMARY.json")
    process = read(HERE / "ACTUAL_PROCESS.json")
    binding = read(HERE / "SOURCE_BINDING.json")
    historical = read(OLD / "MANIFEST.json")
    checks = dict(controls_pass=control["status"] == "pass", actual_pass=actual["status"] == "pass",
        monitored_worker_exit_zero=process["returncode"] == 0,
        tested_source_equals_candidate=identity(OLD / "session_api.py")["sha256"] == actual["api_source"]["sha256"] == binding["current_source"]["sha256"],
        old_source_matches_fixed_Git=subprocess.check_output(["git", "show", BASELINE + ":verification/m6_refine_001/session_api.py"], cwd=ROOT) == (HERE / "private/source/session_api_before.py").read_bytes())
    changed = []
    for row in historical["files"]:
        if identity(OLD / row["path"])["sha256"] != row["sha256"]:
            changed.append(row["path"])
    checks["historical_only_authorized_API_changed"] = changed == ["session_api.py"]
    for row in read(OLD / "SOURCES.json")["cases"]:
        checks["original_source_" + row["case_id"]] = identity(row["source_original"])["sha256"] == row["source_identity"]["sha256"]
    for row in actual["copied_runtime_sources"]:
        checks["runtime_" + Path(row["copy"]["path"]).name] = identity(row["source"]["path"])["sha256"] == identity(row["copy"]["path"])["sha256"] == row["source"]["sha256"]
    for path in HERE.glob("*.py"):
        ast.parse(path.read_text(encoding="utf8"))
    ast.parse((OLD / "session_api.py").read_text(encoding="utf8"))
    if not all(checks.values()):
        raise AssertionError(str(checks))
    write(HERE / "VERIFICATION.json", dict(status="pass", checks=checks, passed=len(checks), total=len(checks),
        control_checks=len(control["checks"]), actual_checks=len(actual["checks"]), historical_unchanged_members=len(historical["files"])-1,
        actual_source=identity(OLD / "session_api.py"), wall_s=time.perf_counter()-started))
    costs = dict(prepare_wall_s=binding["wall_s"], controls_wall_s=control["wall_s"],
        actual_monitored_inclusive_wall_s=process["full_process_wall_s"], actual_monitored_tree_CPU_s=process["tree_cpu_s"],
        actual_monitored_tree_peak_RSS_bytes=process["tree_sampled_peak_working_set_bytes"],
        actual_worker_wall_s=actual["wall_s"], actual_worker_parent_CPU_s=actual["parent_cpu_s"],
        nested_Blender_wall_s=actual["nested_Blender_wall_s"], nested_Blender_tree_CPU_s=actual["nested_Blender_tree_CPU_s"],
        actual_Blender_processes=actual["actual_Blender_processes"], actual_Blender_reads=actual["actual_Blender_reads"], actual_Blender_edits=actual["actual_Blender_edits"],
        injected_prelaunch_faults=actual["prelaunch_injected_faults"], output_present_receipt_faults=actual["output_present_receipt_faults"],
        legacy_reserved_labels=actual["legacy_reserved_labels"], Pro_calls=0, training=0, renders=0,
        finalization_failed_attempt=read(HERE / "FINALIZE_RECOVERY.json"),
        allowance_s=1800, accounting="Actual monitored process includes worker and nested Blender. Preparation and mock controls are separate scopes. Blender time is a nested view.",
        unknowns=["root reasoning and source-editing time", "short-lived process descendants missed by50ms monitoring"],
        evidence=[identity(HERE / name) for name in ("SOURCE_BINDING.json", "CONTROL_SUMMARY.json", "ACTUAL_SUMMARY.json", "ACTUAL_PROCESS.json")])
    write(HERE / "COSTS.json", costs)
    patch = subprocess.check_output(["git", "diff", BASELINE, "--", "verification/m6_refine_001/session_api.py"], cwd=ROOT)
    (HERE / "SOURCE_DIFF.patch").write_bytes(patch)
    report = f"""# M6-REFINE-RECOVERY-002 公共回读恢复

`save_readback` 已在 session 锁内、reader 启动前持久化 `next_readback_attempt`。旧 session 缺少字段时从1开始，逐个跳过已有输出目录和已保留的 job 标签。原返回字段继续保留。

## 验证结果

- 旧固定 Git 字节的控制流反例复现了 RuntimeError 后同编号 FileExistsError。新源码的相同故障控制成功分配新编号。
- 控制回归 {len(control['checks'])}/{len(control['checks'])} 通过，覆盖正常读取、预输出失败、已有输出后回执缺失、遗留标签、稀疏目录、已有计数冲突及跨进程锁。
- 真实回归 {len(actual['checks'])}/{len(actual['checks'])} 通过。Yanyite 与 face 均启动新 Blender reader，并将实际坐标、拓扑和矩阵与固定保存证据逐位比较。
- 预启动故障后保留已存 blend，新标签启动真实读取成功。已有输出后回执缺失的原件保留，再次调用也取得新标签。旧 session 没有计数字段且只有遗留 job 时恢复成功。
- 独立读取期间 blend SHA、version 和 operations 保持，读取 attempt 递增。另一个新副本通过 pending 编辑恢复及 operation 幂等回归。
- 原1499个清单成员中1498个逐字节保持，唯一变更为授权的 session_api.py。旧 manifest 继续绑定154ff39a。六个原已保存模型、原会话和来源保持。

## 实际成本

真实 Blender {actual['actual_Blender_processes']} 次，包含 {actual['actual_Blender_reads']} 次读取和 {actual['actual_Blender_edits']} 次独立测试副本编辑。另有 {actual['prelaunch_injected_faults']} 次保留作业标签后预启动故障及 {actual['output_present_receipt_faults']} 次实际输出后回执故障。编辑用于 pending 恢复回归。新 Pro、训练和渲染均为0。

实际父进程监控墙钟 {process['full_process_wall_s']:.6f} 秒，进程树 CPU {process['tree_cpu_s']:.6f} 秒，峰值采样工作集 {process['tree_sampled_peak_working_set_bytes']/1024**2:.2f} MiB。嵌套 Blender 墙钟 {actual['nested_Blender_wall_s']:.6f} 秒，属于上述监控范围。控制回归另计 {control['wall_s']:.6f} 秒，来源核验另计 {binding['wall_s']:.6f} 秒。完整计时见 COSTS.json 和 private 作业日志。

## 原件与复现

源码差异为 SOURCE_DIFF.patch。control_cases.py 从154ff39a真实 Git 字节提取旧函数，与当前函数运行相同故障控制。actual_regression.py 复制七个既有 runtime 文件的原字节到本批，预加载本批模块并将 API 的 HERE 绑定本批，从而将所有新状态、日志和完整模型副本写入本批。身份及重绑定记录见 ACTUAL_SUMMARY.json。

private/source 保留旧新 API 字节和全部历史身份，private/controls 保留旧新反例，private/actual 与 private/jobs、private/processes 保留真实读取、故障和状态原件。旧源码使用固定154ff39a重现。恢复结果绑定于本次测试的当前源码SHA，范围为独立回读编号及既有编辑恢复。

按固定合同回报规划独立复核，下一项由既有循环明确派工。
"""
    (HERE / "REPORT.md").write_text(report, encoding="utf8", newline="\n")
    public = [path.name for path in HERE.iterdir() if path.is_file() and path.name != "MANIFEST.json"]
    rows = [identity(path) for path in sorted(HERE.rglob("*")) if path.is_file() and path.name not in ("MANIFEST.json", "HANDOFF.json")]
    write(HERE / "MANIFEST.json", dict(files=rows, count=len(rows), bytes=sum(row["bytes"] for row in rows), public_files=sorted(public+["MANIFEST.json"]),
        modified_API=identity(OLD / "session_api.py"), exclusions=["MANIFEST self", "postcommit HANDOFF.json"]))
    print("verified", len(checks), "controls", len(control["checks"]), "actual", len(actual["checks"]), "manifest", len(rows))


if __name__ == "__main__":
    main()
