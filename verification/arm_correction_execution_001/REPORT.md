# ARM-CORRECTION-EXECUTION-001：产品执行首版与验收记录

本批完成限定域内的实际产品闭环：显式 arm task 经现有调度器与 owned worker，在一次宿主调用内读取当前来源、预览、赋值中间及末端两根骨骼，再读取实际结果并持久化回执。固定八项原生 Blender 任务全部符合预定结果；最终 CPU 回归 47/47；独立原件审核 7739 项检查通过。待管理员审核，不把实现方通过记录写成管理员准入结论。

基线提交为 `159c243c26576129830bea7eed16ec79207f7ffa`，分支为 `codex/architecture-arm-correction`。本报告与源码、失败尝试和原始证据一起提交；`EVIDENCE_INDEX.json` 绑定每份文件的字节。

## 实现范围

只修改五个既有核心文件：

| 文件 | 本批职责 |
| --- | --- |
| goal_scheduler.py | 在同一 run 锁内分流不可变 ArmAxialTaskSpec；保留原 ClearanceTaskSpec 路径 |
| goal_execution.py | 校验并冻结任务；先保存 pending，再单次派发；保存实际计数、结果、冲突及未知状态 |
| blender_process.py | 默认 verified worker 的单条 correct_arm_axial RPC；严格核对回执，未知后隔离进程 |
| blender_worker.py | 协商有限执行协议，调用既有宿主；序列化失败仍尽量返回已知 setter 计数 |
| blender_host.py | 扩展同一私有依赖快照；实际来源绑定、一次预览、两次绝对 basis 赋值与实际反馈 |

数学预览、source、expert、weights、数据集均未改。没有新 MCP 工具、新调度器、新批准表单、通用授权框架或另一套计时/预算服务。

任务不接受任意候选矩阵。首末端完整姿态由 worker 第一次实际采集固定，控制端没有为提供端姿多发 capture。正例一次 before、一次 after；after 同时用于目标、端姿、保护点、中心线和候选一致性判断。原始几何复用 bound static，避免立即导出再复制整份 patch。骨 basis 平移从米转换为 Blender 单位，非 1 单位比例由 CPU 反例覆盖。

当前写入域只允许 owned、background、固定帧、无约束/动画/driver 的完整三骨 LBS 网格。选择必须覆盖该网格全部顶点；拒绝共享数据、其它引用该 rig 的 mesh modifier、域外骨标志及有 modifier/shape key 的 sentinel。写入前后检查对象/data incarnation、静态来源、单位、帧、骨标志及独立 sentinel。旧 motion/episode 不得并行占用。没有保存、切帧、关键帧或权重编辑命令。

## 真实行动与不确定性

中骨和末骨是两次独立 setter。产品分别记录 attempted 和 returned；不把未收到回执解释为零写入。

- 同 event、同任务重放返回历史结果，零新 RPC；同 event 不同任务为冲突。
- 派发前 pending 已保存；重启读到 pending/unknown 不再次执行。有限事件账本最多 64 项，不靠淘汰旧事件解除幂等约束。
- 第一次 setter 抛错可为 attempted=1、returned=0、executed=unknown；第二次失败保留已经返回的第一次写入。
- 两次写入后读取、传输或序列化失败保留已知计数和未决结果，停止该进程的后续派发；没有自动重试或虚构回滚。
- 最终保存失败时，内存保留已知回执；磁盘 pending 继续阻止重启后重复执行。无法承诺磁盘已经保存没有成功提交的完整回执。
- 正常结果的目标与 area tolerance 使用任务的 `.4`、`1e-6`，独立 QA 的 `2e-5` 面积比较门限不替代产品目标。

这些失败由确定性 CPU doubles/真实 Python worker loop 检查；没有为了故障验收对原生 Blender 新增破坏试次。

## 固定八任务的实际结果

`native_01/RESULT.json`、`case_01.json` 至 `case_08.json` 保存本次唯一原生运行。J 是各登记截面相对静态面积的最大损失 `max(0, 1-min(area_after/area_rest))`，不是完整体积或损伤指标。表中 after 为独立原始 RNA 重算，域外一行仅是 QA 几何记录，不是产品认可该域可测。

| 任务 | 状态 | 实际 J：前 → 后 | returned setter |
| --- | --- | --- | --- |
| round_120 | satisfied | .750000025 → .250000191 | 2 |
| round_minus150 | satisfied | .933012698 → .370590546 | 2 |
| elliptic_120 | satisfied | .749999994 → .250000158 | 2 |
| elliptic_minus150 | satisfied | .933012701 → .370590442 | 2 |
| balanced_120 | no_op | .250000124 → .250000124 | 0 |
| small_twist_30 | no_op | .066987401 → .066987401 | 0 |
| unreachable_120 | unreachable | .750000025 → .750000025 | 0 |
| noncoaxial | not_applicable | .748129649 → .748129649（QA only） | 0 |

合计：8 条 mutation RPC、8 attempted / 8 returned 产品赋值、8 次预览、12 次产品 source capture、0 次模型调用。前四项各两次赋值；后四项零候选写入，原生坐标逐点不变。不可达项的预测最优不能冒充实际改善。另一次同事件重放没有派发新 RPC。

每项留存产品实际消费的完整 source/static/resolved-task/proposal、原生 before/after 顶点、姿态、保护点、静态字段和 sentinel。首末端原生完整姿态、194 个保护点、环中心、heads/tails 均由独立标准库审核重算，不导入生产算法作答案。

独立审核最大误差：LBS 约 `2.49e-7 m`、保护点 `1.79e-7 m`、端姿平移 `6.15e-8 m`、端姿角 `1.56e-5°`，均小于预定 `5e-6 m` / `.001°` 门限；静态与 sentinel 保持。`INDEPENDENT_NATIVE_AUDIT.json` 记录 7739 项断言及输入 SHA；这次审核没有新增效果资产、产品调用或 Blender 运行。

## QA 与产品的边界

实际入口是 OwnedGoalScheduler → 默认 BlenderProcessHost → 固定 verified worker → 原产品 BlenderSceneHost 方法。控制器在既有 owned 启动参数之前插入 QA 初始化表达式，没有改 worker_path 或关闭 SourceGuard。

启动 QA 创建 8 个生成副本，24 次 basis 赋值只用于初始姿态；QA 候选赋值为 0。只读 observer 包装原方法一次调用，前后独立读取原生 RNA，写原件档案。启动 profiler 仅用于取得宿主，产品任务开始前已移除。`OBSERVER_READY.json` 记录原方法文件、行号、源码和代码对象 SHA；产品方法 SHA 与本批五文件冻结一致。此为受控软件见证，不是外部硬件证明。

8 项 QA 共 16 次独立 native read，不计作产品 source capture。QA 的读、JSON 归档和协议耗时包含在入口/RPC 测量中，不能宣传为无插桩的用户延迟。RPC_TX/RX 是管道文本 API 记录，不是内核原始字节抓包。

使用原有生成 fixture.blend 作 owned 启动文件，初始化后不保存；原文件运行前后 SHA 相同。没有编辑用户 GUI 场景或角色。PID 19220 正常退出、关闭并回收，owned 对象/mesh/rig 清理，宿主回调恢复到启动基线，profile=None。基线 load_post 的 3 个既有 handler 保持，不能称所有全局 handler 都清零。最终进程检查没有残留该 owned worker 或测试 Python worker。

## CPU 回归、兼容与保留的失败

`cpu_final_03/RESULT.json` 与 TESTS.log：47 项方法、0 failure、0 error、0 skip；测试前后绑定同一最终产品字节。

| 组 | 方法数 | 内容 |
| --- | --- | --- |
| host | 11 | 正常两写、单位换算、首次/中途 setter 失败、after 失败、零写、sentinel/元数据/全网格守卫 |
| goal | 15 | pending/save、重放/冲突、未知/重启、最终保存失败、计数一致性，含旧 clearance 成功及未知路径 |
| transport | 9 | 实际 Python 子进程 worker loop、严格回执、丢失/无效/序列化结果、进程隔离 |
| read compatibility | 2 | 旧四依赖只读缓存与 read observe 转发保持；未额外做模型推理 |
| 既有 ProcessHost | 10 | 原有 owned process 路径回归 |

失败尝试保留：最初 transport 因 Windows venv redirector PID 与直接子进程 PID 不同而 9 error，测试改用 sys._base_executable 后通过，未改产品来绕过 PID 合同。`transport_tests.json/.log` 保留原失败，后续 _02/_03/_04 保留阶段结果。

sentinel NODES/shape key 的真实 red 测试揭示旧候选会错误执行；`host_sentinel_red_01` 保留两项失败，`development/host_pre_sentinel.py` 保留当时实际源码及 SHA。修复后拒绝，再补全网格、after 元数据变化等守卫，最终 11 项 host 通过。早期 CPU/host/goal 阶段结果不冒充最终版本结果；最终依据仅 cpu_final_03、native_01 和独立审核。goal_execution 的 CRLF→LF 为 AST 等价转换，LINE_ENDINGS.json 保留阶段绑定。两份原始失败日志含 unittest 输出的尾随空格，局部 .gitattributes 仅关闭其文本 diff，保留原始字节及索引 SHA。

## 原始时界与后续取舍依据

这是一次固定功能验收，不是尾部延迟分布或正式 A/B 收益比较。所有时间段嵌套，不能相加成“总成本”。

| 时界 | 实测 |
| --- | --- |
| owned 启动（含 QA 建场景、verified worker） | 1020.64 ms |
| 首次完整 entry | 432.62 ms |
| 后续三个正例 entry | 62.67 / 63.86 / 64.16 ms |
| 四个零候选 entry | 49.73 / 50.69 / 50.70 / 49.78 ms |
| 首次宿主步骤 | 405.75 ms，其中 scope/首次依赖加载 375.93 ms |
| 后续正例宿主步骤 | 27.71–27.98 ms |
| 热 before source | 约 10.84–10.94 ms |
| 正例 after source | 约 9.51–9.70 ms |
| 热正例 solve | 约 4.70–4.82 ms |
| 两次 basis 赋值合计 | 约 .016–.019 ms |
| 正例 feedback | 约 1.74–1.87 ms |
| 每项 QA 原件归档（另有前后独立读） | 6.63–9.18 ms |
| 16 次 service_save 总计 | 59.45 ms |
| 原 runtime 构造 8 次 / export 16 次 / import 7 次 | 总计 .361 / .227 / .170 ms |
| close / 整体控制器 | 111.05 / 2011.64 ms |

state_lock_restore 除首次外约 8–10 ms，不等同于 runtime 构造成本；内部 IO、校验与测量时界要分清。RPC 包含 QA 读和归档，不能把与宿主的差值全部归因于管道。首次 scope 包含私有依赖/NumPy 加载，把它移到启动只会改变时界，不能直接声称消除成本。

实际 source 仍有 12 次 static read、8 次 static preparation；正例 before/after 各读一次静态。source 模型推理为 0，但准备特征不等于零工作。总计 4824 个 rest/current/weight 顶点读取、36 个 rest/pose 骨读取、12 次 topology 校验。后续可优先评估几何执行路径未消费的 8 次 expert preparation；本批没有对其独立计时，不能预先承诺节省值，也未在验收后追加优化。

## 冻结与未覆盖范围

137 个运行源码的 canonical SHA 为 `e224f445a310c8b799b49d6f3f30184fa9b76b569cfa9ff1e79707c0291115b0`，native 运行前后相同。最终五产品字节与 CPU、原生和独立审计交叉绑定。SEAL.py 只检查档案和写索引，不执行产品、模型或 Blender；`EVIDENCE_INDEX.json` 排除自身，保留其余完整文件的大小与 SHA。

本批没有证明任意角色、动画、多骨 IK、非同轴求解、DQ、完整体积/自交、连续路径安全或学习收益；不宣称 Codex 当前聊天已获得新 MCP 动作，也未切换正式安装配置、付费调用或上传云端。新增方法只面向显式 owned 任务，不能当成任意场景的通用写权限。

下一步由管理员审核本提交，在实际成本中选择一个必要优化后再收口该限定域闭环。本批到此结束。
