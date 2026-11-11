# 冻结前设计与 QA 复核

本次复核支持将当前准备材料纳入冻结提交。已识别的 profiler 状态、字段对齐、计时口径和退出判定缺口已收口。实际矩阵由主会在提交合同、输入 pin、固定顺序、分析规则及最终纯检查记录后唯一执行，入口还会核对指定提交的实际文件字节。本复核没有启动产品、Blender、测量或模型消费者。

## 固定版本与唯一变量

实验使用既有隔离安装 B=e077/53db 与 C=a81/9f28，各 137 源。当前实施 checkout 的 4eb schema 修复版本排除在性能矩阵外。准备验证脚本读取安装、原构建 manifest、保存 wheel、入口、binding 与同一 dependency Python executable 的字节，`INPUT_VERIFICATION_01.json` 登记 290 项文件 pin。实际加载身份仍在每个会话 initialize 中核对。

顺序固定为 B、C、C、B。每会话 1 cold OFF、1 warmup OFF、10 个相邻 ON/OFF 配对，共 22 次相同无 geometry 业务请求。每模式在配对第一、第二位置各出现五次。worker 第 23 个请求只用于普通关闭，固定 OFF。四条 metadata stdio 消息要求零 Blender RPC。

新 QA 使用一个受保护的 rpc_scope 承载原有采样和 profiler 开关。保留现有 host_work、指纹、文件保护、时界、事件与退出路径，避免另造采集或计时平台。每次业务请求立即核实际 worker 序号、MCP receipt、profile 状态、事实、捕获代及工作量。多余或缺失 RPC 会停止矩阵。失败会话不会被替换，也不会补业务请求凑满第 23 序号。

## Profiler 状态与异常

OFF 创建同样的状态与 callback closure，保留前后 host 采样，跳过 setprofile。Python/C callback 字段为 null，并声明 not_collected。它们不能表示零宿主工作。

初始 getprofile 非 None 会记录错误并阻止业务进入，已有 profiler 得以保留。ON 只在当前值仍是本 callback 时恢复初始 None。外来替换、callback 消失、callback 异常、安装或恢复失败均记录错误并停止。状态在采样或安装前挂到事件中，因此前置异常仍进入 finally。OFF 后出现外来 profiler 时也会记录不一致并保留其状态。

实际产品与原宿主 source 固定，C 方法通道在旧环境不可观测的限制继续保留。ON 的空 C 计数不能单独证明没有 bpy C 工作，原 residency 与产品 trace 计数提供另一层记录。

## 最终纯检查

读取 `tests/r5/RESULTS.json`，最终 12 个方法全部通过，失败、异常和外部操作尝试为空，真实控制进程的 sys profile 保持原值。它使用实际 QA helper、私有 fake profile API、fake host 采样和静态原函数检查，属于 synthetic 准备验证。结果 SHA-256 为 `cbde14386dab46c5c469392d3c9966c98f9bb3412404cd426d68b26043a06fc7`。

覆盖包括正常 ON/OFF、初始 foreign profiler、业务异常、callback 异常、外来替换、callback 消失、恢复 API 失败、before/after 采样失败及安装完成后抛错。静态检查覆盖原保护、指纹、定时和清理函数。固定 schedule 的纯分析控制确认每会话 22 行、10 个非空配对、ON/OFF 各 10、位置各 5、previous 链和第 23 关闭行，合成版本差及 interaction 与独立期望相符。

最终记录的源 pin 如下。

| 文件 | SHA-256 |
|---|---|
| entry/run_entry.py | `986cd5efcaf9c840b7bd4a08361785cf2447caad0ea3f23c2d1bcad93ebb67c7` |
| entry/qa_instrumentation.py | `a0980cbe8c388fdd0b8bb7c19ac5f8e140fb629474cf8670d7923d651b6a0cff` |
| entry/qa_native.py | `6e419b7cb4d925a2f88cfe6bd560a38b0b1dbc8ebeb2aeb78c382b7b8c483592` |
| analysis/analyze_saved.py | `ce877249d0cbb85ae3edfa4342af6672ebd25256f64fa9a84e747a6ae53c3dff` |
| SCHEDULE.json | `192fc795b2cb94ebb3d98216bfbf4165f76c6a04accafcae17c1c7c313fd2993` |

准备阶段已将暖行 phase 统一为 warm，分析器读取路径也对应真实入口的 INPUT_BINDINGS、FROZEN_COMMIT 与 VALIDATED_INPUTS。最后一次输入核对还发现 critical_git_paths 包含 INPUT_BINDINGS 自身，而 source_files_sha256 为避免自引用不包含自身。分析器原字典取值会产生 KeyError，已在首个测量启动前纠正为逐 critical 路径读取实际字节 SHA 与冻结提交回执精确比较。r5 使用实际 20-critical/31-pin 结构及合成提交回执覆盖这一点，并确认错误 self digest 被拒绝。

最终 INPUT_BINDINGS SHA-256 为 `1a1f292af4336cf99a77d96513b8db85a076460af5c03f6ba6fcbe2d06754ab5`。旧 cfd 输入、r1 至 r4 及修正前分析源码/runner 保留。r5 的 bindings fixture SHA 仍如实登记旧 cfd，验证其相同字段结构；最终重新生成的 pin 另由提交字节检查绑定。该次修正限于测前元数据接口，helper、入口、固定顺序与分析规则语义保持原冻结范围。

## 计时与解释边界

Peer receipt 的 elapsed 在最终 receipt/RPC 日志发布前取值，外层 entry elapsed 包含该发布。请求后立即校验另记 duration，并计入会话总时间。batch 时钟明确从 main 入口至最后源核对，排除解释器 import 与最后结果本次发布的尾部。

新的 before_probe 包含安装及状态检查，after_probe 包含恢复检查，profile_scope 从状态创建起包含 before 采样及执行。这些 inclusive 区间有重叠。分析规则已声明各自边界，不能相加成互斥分解，不能把整个 profile_scope 扣成 observer 独占成本，也不能按相同字段名直接与前批 probe 相减。

ON 生成实际计数字典，OFF 使用 null，事件发布成本也随真实记录内容变化。ON/OFF 对照刻画本 QA profiler 状态及其计数记录链的控制差异。它没有隔离纯 callback 成本，所有外层保护、采样和日志仍在实验范围中。

## 退出与根接手责任

正常关闭联合要求产品 Peer 退出、已证明的实际 runtime 句柄 signaled/exited/exit_code=0 且关闭、Native close 的 response.status=closed 且 error=None、owned Blender exit_code=0、完整终态与原资产保护。已补上关闭回执失败可能被 terminal 文件和零退出掩盖的判定缺口。已补上 runtime exit proof 调用的异常保护，使该处异常继续进入 Native 清理。保存事件还检查新增 PNG 和 render 增量。

严格 seq23 下的提前关闭会被拒绝。原 NativeSession.close 仍在 finally 等待 owned Popen，超时调用原 _kill 再等待，原始错误及额外清理 RPC 保留并使矩阵停止。

如果实际产品 runtime 仍活，借用的 exit proof 会返回未确认并关闭 retained handle。脚本记录 stop 后，主会负责在原清理时界内依据已保存的实际 PID、创建时间和 parent ancestry 重新只读核对归属，再终止这一 owned child，并登记实际清理状态。主会已接受这一异常责任约定。failed stop 本身不作为清理完成证明，清理不会追加业务样本或扩展到共享 GUI。

## 本次冻结判定

没有发现尚未收口的执行设计阻塞。保留一组固定四会话，运行后先核来源、事实、捕获代、状态恢复和工作量，再解释时间。分析以 session 为版本比较单位，每版本仅两个会话。保留所有请求、配对差、位置和 previous-mode 分层，以及冷数据、预热和完整准备/退出成本。

本审查允许准备材料封口，不提前作测量结论。前批默认约 +3.57% 与完整准入未通过的记录继续封存。本批不新增允许百分比，不按显著性宣称等价，不估计稳定 p95，也不会自动授予模型消费或默认发布资格。剩余限制由唯一控制实验的保存结果给出，之后按一次性出口结束。
