# M6-REFINE-RECOVERY-002 公共回读恢复

`save_readback` 已在 session 锁内、reader 启动前持久化 `next_readback_attempt`。旧 session 缺少字段时从1开始，逐个跳过已有输出目录和已保留的 job 标签。原返回字段继续保留。

## 验证结果

- 旧固定 Git 字节的控制流反例复现了 RuntimeError 后同编号 FileExistsError。新源码的相同故障控制成功分配新编号。
- 控制回归 63/63 通过，覆盖正常读取、预输出失败、已有输出后回执缺失、遗留标签、稀疏目录、已有计数冲突及跨进程锁。
- 真实回归 50/50 通过。Yanyite 与 face 均启动新 Blender reader，并将实际坐标、拓扑和矩阵与固定保存证据逐位比较。
- 预启动故障后保留已存 blend，新标签启动真实读取成功。已有输出后回执缺失的原件保留，再次调用也取得新标签。旧 session 没有计数字段且只有遗留 job 时恢复成功。
- 独立读取期间 blend SHA、version 和 operations 保持，读取 attempt 递增。另一个新副本通过 pending 编辑恢复及 operation 幂等回归。
- 原1499个清单成员中1498个逐字节保持，唯一变更为授权的 session_api.py。旧 manifest 继续绑定154ff39a。六个原已保存模型、原会话和来源保持。

## 实际成本

真实 Blender 8 次，包含 7 次读取和 1 次独立测试副本编辑。另有 2 次保留作业标签后预启动故障及 1 次实际输出后回执故障。编辑用于 pending 恢复回归。新 Pro、训练和渲染均为0。

实际父进程监控墙钟 23.835379 秒，进程树 CPU 20.937500 秒，峰值采样工作集 426.21 MiB。嵌套 Blender 墙钟 10.192468 秒，属于上述监控范围。控制回归另计 0.492287 秒，来源核验另计 0.491195 秒。完整计时见 COSTS.json 和 private 作业日志。

## 原件与复现

源码差异为 SOURCE_DIFF.patch。control_cases.py 从154ff39a真实 Git 字节提取旧函数，与当前函数运行相同故障控制。actual_regression.py 复制七个既有 runtime 文件的原字节到本批，预加载本批模块并将 API 的 HERE 绑定本批，从而将所有新状态、日志和完整模型副本写入本批。身份及重绑定记录见 ACTUAL_SUMMARY.json。

private/source 保留旧新 API 字节和全部历史身份，private/controls 保留旧新反例，private/actual 与 private/jobs、private/processes 保留真实读取、故障和状态原件。旧源码使用固定154ff39a重现。恢复结果绑定于本次测试的当前源码SHA，范围为独立回读编号及既有编辑恢复。

按固定合同回报规划独立复核，下一项由既有循环明确派工。
