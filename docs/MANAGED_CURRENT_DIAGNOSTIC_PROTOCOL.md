# 托管常驻增量超门：一次限定归因诊断

2026-11-06，主干在任何新诊断运行前冻结。本任务补查 `formal_cost_001` 的托管常驻问题，不重新验收时延，不重新优化算法，也不把诊断中的较好读数替换正式失败。

## 已有事实与问题

原三 seed 的 72 个对应热窗中，256 KiB current 门在 `hot_outputs_held` 有 9 点超限、`hot_outputs_released` 有 12 点超限、`hot_reference_replaced` 有 12 点超限。最大 I−B 为 488751 B；原窗口 peak 最大差 513429 B，未超过其独立 1 MiB 门。原报告因 `_bpy_types.Object` 不在冻结分类器中而将 current 标为 UNVERIFIED；漏分类不消除这些数值超门。

所有对应有根保留点的 NumPy 底层存储和公开 bytes 字节差均为零，不能据此排除 Python 对象或验证者存活分配。差异跨案例跳变：seed 310519 的 ordinal 7（I-single-panel-3）在 t4 held 为 −149869 B，proof/释放后为 +487784 B。原资源轮没有 GC 事件或分配栈，不能从此推断 GC、泄漏或某一具体生产对象已被证明为根因。

## 固定执行范围

- 只用 seed **310519**，B、I 各一个全新后台 Blender 进程，按原顺序 **B 后 I** 串行执行；不接触用户已打开的 Blender，不并发 GPU。
- 原 79f8bcc 生产源码、正式 B、部署、场景、反馈、掩码及配置全部保持。原 `formal_cost_001` 所有源与证据只读。新诊断脚本与输出放 `artifacts/integration/managed_current_diagnostic_001`；运行前登记实际命令、源快照、输入摘要和阶段配置。
- 按原方式导入并加载完整 24 案例工作负载；执行顺序固定为 **ordinal 0…7**。前 7 例保留原 5 预热、复位、1 热链、参考替换及关闭/重开轨迹，不能裁掉会影响下一例分配状态的工作。
- ordinal 7 也完成原 5 预热、复位和 1 热链，终止观察点固定为 `hot_outputs_released` 的原 current 读取之后、其 census/报告以及参考替换/关闭重开之前。保存终点分配快照后正常清理资源，不再把后续读数作为门。
- 共两个进程、一次尝试。未复现也保留结果并回传，不自动延长到 ordinal 11、换 seed、加 GC、改变次序或重复到通过。

## 唯一新增观测

1. GC 始终保持正常启用，不主动 collect、不改变 threshold。回调仅写预分配的固定容量数值缓冲；缓冲在 tracemalloc 开始之前建立，保存 generation、start/stop、collected/uncollectable、QPC 与静态阶段编号。不要在回调中 append 字典或写 JSON。容量、实际记录数、溢出和回调异常如实报告。
2. 每例保留原读数；额外只记录固定阶段的轻量 QPC/current：原 t4 读数、held census 完成、proof_summary 完成、删除 outputs 后的原 released 读数。说明新观测本身开销，不把新阶段当新的合格门。
3. 每进程只在上述 ordinal 7 终点原读数之后取 **一张** tracemalloc snapshot，并保存原始 snapshot 和完整按 traceback/文件/行的统计。不要提前创建或保留快照，避免改变后续读数；终点快照和报告的分配不计入原终点读数。
4. 快照之后可核查仍活跃的 renderer.cameras 的真实类型、MRO、`isinstance(obj, bpy.types.Object)`、相机及 data 对应关系，解释 `_bpy_types.Object` 的归属。不得将未知 native 大小填零或把它加算到已经包含相关分配的 traced current；逻辑原生资源与 OS 门仍独立。

## 诊断判定与后续权限

报告两臂相同点的绝对值和差值、每阶段增减、GC 与阶段的时间关系，以及终点 traceback 差异。按生产源码、验证/报告源码、NumPy、宿主及无法归因分栏，保留完整明细，不能只挑一个有利栈。单张快照差异和 GC 同时发生只能提供相应强度的证据，不自动证明原正式轮根因。

不改变 262144 B current 门、1048576 B peak 门，不以冷起点相减或 NumPy 字节相等代替原 current，不删除原 33 个失败点。诊断不授予整机 PASS。

- 若明确证明验证者残留或仪器故障，提交具体源行、持有链及受影响范围，由主干先审定有限仪器修正，再决定必要资源复核；不能顺带重跑已通过时延或旧 CF 质量。
- 若证据指向生产常驻增量，提交最小定点修复或回退方案，再由主干决定；不启动整模块新一轮优化。
- 若现象未复现或无法归因，保留未决，不能自动追加实验。

完成这两个诊断进程或遇到具体执行故障后一次性回传，主动唤醒主干。主干不轮询等待实施聊天。
