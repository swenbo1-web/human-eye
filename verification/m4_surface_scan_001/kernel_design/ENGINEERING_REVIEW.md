# M4-SURFACE-SCAN-001 工程验收脚本独立复审

本次只读取工程、安装和相关时界实现。未导入产品，未启动 Blender，未执行产品调用或主场景性能测试。候选提交为 `c6355a01a4c6ee204a0d676cd9309f02428fe3ba`，产品来源为 `b3654f6f943c3fb6feff0011397c0a8c20872e41f35973e6baf53e3a5e277314`。

## 需要补验的发现

### 资格真值文件应核对既有冻结哈希

`run_main.py` 把当前真值和快照的 SHA 写入本轮输入绑定，并在每个序列前后检查。它尚未把这些 SHA 与 `QUALIFICATION_READY.json` 的既有对应字段逐项核对。`run_process.py` 对 asset 作了核对，对真值和快照尚缺同类核对。

当前文件已经独立检查。BASE、EDIT 两份真值，两份快照及 `GEOMETRY_FREEZE.json` 的哈希均与资格 READY 一致。两份真值均为 276 行、276 个唯一无序 pair。原始核对结果保存在同目录 `ENGINEERING_REVIEW_INPUTS.json`。

root 已使用独立 `audit_engineering.py` 核对 9 项资格承诺哈希、67 个资格文件、138 份 checkout/install/commit 来源字节，并补验同一组原始结果。复读补验器确认该发现已覆盖。运行绑定中的脚本保持原字节。

### 公共距离需要直接对独立真值验算

`verify_state.py` 已把私有 dispositions 中所有 measured 距离与独立 exact truth 对照。公共 match 部分检查了两见证点确实位于各自表面，并检查公开距离与这两点的距离一致。

公共距离还应直接对其 pair 的独立最小表面距离作比较。否则，选取同两表面上的其他点，并同步修改公共距离，能够满足现有公共见证检查。私有诊断保持正确时，这个错误不会被当前比较发现。还应明确要求当前测试域的 `witness_status == 'measured'`。

root 已在独立 postrun 补验中对 1070 条主序列公共距离、71 条 Process 公共距离逐项核对独立真值，并要求 measured 状态。复读补验器确认该发现已覆盖。

### 汇总需要保留缺失状态的分母

`run_main.py` 固定安排五个序列，每个成功条件都要求恰好三条业务记录且全部通过。异常记录会保留在序列或业务行中，因此错误不会自动成为成功。

`summarize.py` 使用 `next(...)` 查找每个 cold、repeat、edit 行。当启动或准备异常导致某个状态根本没有产生记录时，汇总会抛出 `StopIteration`。后续离线 audit 应显式建立五乘三的计划状态表，检查重复、缺失、已失败和未执行，分别保留实际发送次数及实际 Host RPC。不可用现有行数代替计划分母。

root 补验器已建立完整 15 格状态表，并加入空表、重复和失败行反例。当前五个原始序列均具备恰好 cold、repeat、edit 三行，全部通过，未发生缺行或错误遗漏。原汇总脚本的异常出口仍留作后续脚本加固，本次原始结果已补验。

### 补记 actor 的直接传递依赖

`verification/m1_task_entry_001_eval/actor.py` 顶层加载 `verification/native_plugin_complex_003/actor.py`，实际 `Peer` 复用了后者的 `save` 和 `encoded`。当前 main 输入绑定包含前者，尚未列出后者。

该依赖是仓库中的受跟踪文件。此次已独立比较当前字节与候选提交同路径字节，完全一致，SHA 为 `f8fcb8f3afa44fccbbd3af33cba70bba20700cb8b05999f12d72fe02ebe4b85c`。证据已加入 `ENGINEERING_REVIEW_INPUTS.json`。此次未修改该依赖或运行绑定。

## 已确认的检查

- 阴性 pair 进入逐行验收。276 行 dispositions 检查唯一性、canonical ID、完整集合以及各分区计数。bound exclusion 必须严格大于阈值，且其平方不得超过独立真实距离平方。
- measured match 与 measured nonmatch 均核对独立分类。未知和 deferred 状态会使当前固定输入的完整验收失败。公共 match 集合必须恰好等于所有真匹配，不允许重复或遗漏。
- 实际 BASE、EDIT 快照分别与资格快照逐字段比较，仅忽略 PID 和文件路径。原始响应、快照、请求、audit、wire、内存记录和输入哈希均保留。
- 安装准备从指定提交归档源文件，并检查 checkout 字节一致，按稳定规则复算完整 runtime source digest。安装回执要求源码、提交、wheel 和隔离安装一致，保持默认激活不变。
- main 以独立拥有的 Blender 进程和 stdio 产品进程构成每个序列。元数据阶段要求零 Host RPC。主五序列与额外 ProcessHost 定向测试分别统计。
- 每个业务请求使用原产品期限和客户端时界。业务完整 wall time 包含 `Peer.call` 内的序列化、发送、读取、解析与回执落盘。内存读取在这个业务时界之外，另有 before/after 记录。
- Windows 工作集峰值已明确为进程寿命峰值，未作为请求局部峰值。统计范围固定为五个工程序列，未宣称模型效果或尾部分布。
- 安装命令有独立开始、结束、PID、超时、退出码、输出字节与 SHA。超时仅回收该安装命令拥有的进程树，并保存失败记录。

## 已纠正的复审判断

初看 `_call_tool` 时曾误判 MCP trace 不包含外层 frame 编码和 stdio 写入。继续追到 `run_stdio_mcp_server` 后，确认其外层 trace 覆盖 `mcp.wire_encode` 和 `mcp.stdio_write`，内部 trace 复用当前实例。该疑点已撤销，并已通知 root。

`complete_client_request_ns` 仍应与 service trace 分别阅读，前者额外包含客户端与回执仪器开销。嵌套 span 使用包含时长，不能相加后当作完整请求时长。

## 复审状态

已读 root 补验器及其通过结果，确认资格哈希、公共距离、witness 状态和完整计划分母均有对应检查。

另以本目录 `recheck_engineering.py` 独立离线复算 Seq1 的 cold、repeat、edit 及 ProcessHost base。该复算直接读取原始结果和冻结真值，独立检查 1104 对完整分区、285 条公共距离、570 个表面见证。全部通过，最大公共距离误差约为 `1.0842e-19` 米。该脚本仅使用标准库，未导入产品或复用产品几何算法。

BASE 三行各为 164 对严格排除、71 对匹配、41 对实测不匹配。EDIT 一行为 162 对严格排除、72 对匹配、42 对实测不匹配。每行均为 276 对，无未知、延后或重复。原始结果文件 SHA 和逐行复算结果已加入 `ENGINEERING_REVIEW_INPUTS.json`。

此次未修改工程运行脚本、安装脚本或产品，未增加产品调用。当前补验证据已覆盖复审发现对本轮结果有效性的影响。初版能力范围及已披露的 transport deadline、条件隐藏来源限制，仍应保留在最终报告中。
