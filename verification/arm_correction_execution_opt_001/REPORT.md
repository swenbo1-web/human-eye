# ARM-CORRECTION-EXECUTION-OPT-001：限定执行模块单轮收口

基线为管理员已接受的 `a3a72b929f55c40f195ff5e1a9f64ceb303b6360`。本轮只消除几何执行未消费的专家准备，以及同锁内重复的账本验证。三处核心文件变更，既有 solver、模型、权重、动作目标、写入域及不确定性合同均不变。

最终 CPU 62/62；唯一一次顺序原生配对中，两版各八任务全部符合合同。8 项完整 native before/after、实际消费 input_patch 和 resolved_task 逐字段完全相同。工作计数达到预期，但完整入口耗时没有证明加速；以下保留混合结果，交管理员判断是否接受本次收口。没有重刷样本。

## 最小实现

`arm_twist_source.py`：现有 capture 增 private `_prepare_expert=True`。默认行为继续准备专家。只有几何执行的两处 capture 传 False；静态变化仍执行同一个 `_parse_patch(dynamic=False)`，保留 schema、IDs、权重、刚性 rest 和闭合截面拓扑准入，不缓存解析数组、不另造来源合同。

检测静态变化时先清旧 prepared。需要专家且 prepared 缺失时，从当前静态数据构造一次，即使当前 capture 的 static_changed=False；默认/analyze 不会漏掉延迟准备或复用已被判定变化的旧统计。static_revision 仍只随成功提交的实际静态变化增加。preparations 在实际构造成功时计数，之后 LBS/版本检查失败也不再隐藏已发生工作，这是计量修正。

`blender_host.py`：仅 before/after 两次 capture 增 `_prepare_expert=False`。实际来源、逐点 LBS、拓扑、预览、两个绝对 basis setter、实际回读和保护约束均保持。

`goal_execution.py`：只删 run_arm_axial_step 锁内第二次 validate_arm_axial_ledger(value)。真实 service._locked 已在 yield 前调用 validate_segment_ledger→arm validator；持久加载的检查、进程回执校验和未知状态屏障均保留。不是账本缓存或削减不同信任边界。

| 文件 | 最终 SHA256 |
| --- | --- |
| arm_twist_source.py | 9579805b0894b1505a46cf977a1715ab80155d53a97f469f448276059d8535ee |
| blender_host.py | 10f2b59c00699d1b8cd7b946ff58f0986cbc55fc3af11ad2feaaa9212674af60 |
| goal_execution.py | 89b23b2f902bf3c790749f2a47fa82dc79a5a32e8184813ec071f48b20e566bc |

## 验证与失败保留

`cpu_final_02`：62 方法，0 failure/error/skip，产品、测试及 QA 源码前后 SHA 不变。

| 组 | 方法数 | 关键覆盖 |
| --- | --- | --- |
| OPT host | 12 | 封存旧11项，另加管理员 ignored-write 反例：setter返回两次但实际几何不变时必须 feedback_failed；prepare=0 |
| OPT goal | 19 | 封存旧15项经明确 lock adapter 运行；新增 pending 落盘后丢确认、每次load一次验证、真实持久状态损坏拒绝等 |
| OPT source | 10 | 默认、延迟、静态变化、真实冻结模型输出一致，失败/unsupported、unknown及计数 |
| 旧 transport | 9 | 真实 Python worker loop、丢失/无效/序列化回执、进程隔离 |
| 旧 read compatibility | 2 | 四源只读缓存与原 observe 转发 |
| 既有 ProcessHost | 10 | 原有 owned 进程生命周期及协议 |

旧封存测试/证据未改。新 ValidatedService 测试 adapter 在真实线程锁中调用同一 validate_segment_ledger 再 yield；两项另走真实 LiveSpatialService 文件锁、GuardedRuntime 构造/import/export 和原子状态文件，只有 identity rejection 固定为 None 来隔离测试中源文件变化。原生配对另有真正 verified source/配置绑定，不能用该测试替身代替来源验证。

corrupt state 实际加载一次、验证一次，在新 RPC 前拒绝；pending 已提交但保存确认丢失时，原调用、重放、重启均零派发。ignored-write 返回 executed=true、2/2，但 task_succeeded=false，保持实际结果与调用返回计数分离，无重试。

默认诊断以同字节 Git 旧 source 与候选比较，使用既有 402 点 RNA fixture 及冻结真实模型。最终统一套件有 14 次显式诊断 predict 请求（旧/新各7），其中两个非平面参考返回 unknown；不能算成几何任务的模型调用。source_01（8方法/10预测）、source_02（10/14）、cpu_final_01（62/14）、cpu_final_02（62/14）各自保留，本批所有这些确定性测试共52次本地诊断预测请求；付费/API模型调用0，全部原生几何任务模型调用0。默认 model=None 路径使用计数 proxy 解析并委托真实冻结模型，没有改模型参数。

首次统一 CPU 的1项失败属于新增测试误将原生静态读取次数用于 double。封存 double 的 transform-only 通知不改 dirty，after 可复用 static，因此真实期望是 static/topology读取1次、rest402、current804；原生实际静态读取另计。cpu_final_01 保留失败日志、原 TEST_HOST.py 及绑定；修正这一测试期望后其余产品不变，最终62项通过。没有用一次错误测试结果宣称产品退化，也没有删除失败。

## 唯一一次原生配对

materialize_baseline.py 从 Git 基线精确提取137运行源及 pyproject 到专用临时目录，不切换任何分支。BASELINE_MATERIALIZATION.json 绑定每个字节。两版使用同一原 blend 路径、原始402点输入、cases/oracle、同一新版 native_initializer/controller。先 baseline_01，关闭回收后再 candidate_01；每版一个全新 owned Blender 进程。未修改运行后的候选、目标或插桩来追求更快结果。

基线 canonical source：`e224f445a310c8b799b49d6f3f30184fa9b76b569cfa9ff1e79707c0291115b0`。
候选 canonical source：`a50e34c9169e9384047b29fa8bda8a072f96681f64610334ccec367d8597589b`。
两版各自在运行前后保持自己的相同137源快照。

| 任务 | 两版相同状态 | 实际 after J | 每版 returned setter |
| --- | --- | --- | --- |
| round_120 | satisfied | .250000190839 | 2 |
| round_minus150 | satisfied | .370590545741 | 2 |
| elliptic_120 | satisfied | .250000158497 | 2 |
| elliptic_minus150 | satisfied | .370590442434 | 2 |
| balanced_120 | no_op | .250000123990 | 0 |
| small_twist_30 | no_op | .066987401256 | 0 |
| unreachable_120 | unreachable | .750000025216 | 0 |
| noncoaxial | not_applicable | 产品不推断该域 | 0 |

J 是登记截面的最大相对面积损失，不是体积/损伤。四正例实际目标 `.4 + 1e-6` 达成；后四项零候选写入，原生数据保持。不可达预测最优不是实际改善。两版每版均为8 mutation RPC、8 attempted/returned产品赋值、8preview、12capture、0model；同event内存重放零新RPC。

| 实际工作 | 旧版 | 候选 |
| --- | --- | --- |
| source preparations | 8 | 0 |
| source static parse | 8 | 8 |
| arm ledger validation | 16 | 8 |
| static/native topology reads | 12 / 12 | 12 / 12 |
| rest/current/weights 顶点读取（各） | 4824 | 4824 |
| rest/pose 骨读取（各） | 36 | 36 |
| 持久保存 | 16 | 16 |

QA 只做每版24次起始 basis 初始化、0候选写入、16次独立 native read。原方法文件/行号/代码与源 SHA、完整实际消费 source、before/after RNA、RPC与持久账本均有原件。实际首末姿态仍从 worker 第一采集解析，无控制端额外 capture。

## 分段成本：移除工作不等于整任务已经更快

单位 ms；本表是一组固定顺序的工程对照，不是分布、p95或因果收益证明。source/state/QA包含在更外层时界，不能相加。不同 runtime 路径、固定顺序、OS缓存/调度都可能影响耗时。这里的“启动/首次”指新进程，不声称清空 OS 文件缓存。

| 时界/总量 | 旧版 | 候选 |
| --- | --- | --- |
| 新进程启动（含QA建场景） | 1000.6645 | 952.4152 |
| 首次 entry | 107.9430 | 115.5551 |
| 首次 scope/依赖加载 | 51.3721 | 52.2096 |
| 后续3个正例 entry | 62.8652 / 63.9206 / 64.9688 | 65.5330 / 68.7865 / 66.2204 |
| 后续正例 entry 中位 | 63.9206 | 66.2204 |
| 8项 entry 合计 | 496.2025 | 513.4797 |
| 所有完整 source before/after 合计 | 127.5037 | 133.9462 |
| prepare inclusive（含内部parse） | 11.5804 | 0 |
| 原parse / 保留parse | 9.0124（嵌于prepare） | 9.9485 |
| 旧prepare扣除内部parse | 2.5680 | 不再执行 |
| arm ledger validation合计 | 7.3001（16次） | 4.1218（8次） |
| state_lock_restore合计 | 68.7442 | 65.5534 |
| service_save合计 | 57.1235 | 62.0821 |
| 原runtime构造合计 | .2548 | .2880 |
| QA before读取合计 | 15.4490 | 15.8251 |
| QA after读取合计 | 13.5886 | 15.1902 |
| QA 原件归档合计 | 61.1392 | 63.9023 |
| close | 112.7152 | 117.9953 |
| controller全部 | 1700.0204 | 1674.8283 |

prepare 的11.58ms不能全部当成删除收益，因为约9.01ms静态解析仍必须保留。可定位的旧版特征统计等 exclusive 工作合计约2.57ms；重复验证少了8次，实际校验总时间也降了约3.18ms，但不是把整段状态恢复8–10ms清零。

完整 entry 合计反而增加约17.28ms；三个热正例中位本次增加约3.60%。总 controller 下降约25.19ms主要受启动段差异影响，不能据此宣传产品整体加速。source、保存、QA等段都有混合变化，原始单次对照不足以分离系统抖动与其它成本。确定成立的是未消费准备与重复校验不再执行、功能原件保持；没有达到可宣称全链路速度收益的证据，不追加第三轮调优。

新插桩在既有 loader 返回后才包装同一实际 expert prepare/_parse，未提前移动依赖加载；每个 wrapper 调用原函数一次，并留原函数源码位置与code SHA。prepare计时包含其内部parse，两者明确嵌套；preview已在导入时绑定的dynamic parser不算成source静态parse。两版共用相同插桩，但wrapper记录仍有成本，RPC包含QA读取、归档与文本记录，均不是无插桩用户延迟。

## 独立审核、冻结和边界

`INDEPENDENT_PAIR_AUDIT.json` 最终16218项断言通过。独立标准库审核复算原始RNA面积、LBS、完整首末姿态、194保护点、环中心及heads/tails，核对两版实际消费来源、静态/sentinel、来源快照、RPC、账本、重放及完整时界；同时独立核对COST_COMPARISON的每个分段与最终CPU/probe记录。它没有导入producer、运行模型、发产品命令或另启Blender。marshal code SHA为同解释器受控原函数见证，未跨Python版本独立重建；属于受控软件证据，不是硬件证明。本报告不将实现方或子代理审核冒充管理员正式接受。

audit_pair.py SHA：`24ce5d81ff38ff997c4525a1c7a7af1a054711acf2f3ea571f475d491eef58bf`；最终独立审核JSON SHA：`a745da64eb361cd770e6bb6597027cc1b2798beab8165e0ec411b804c07ebc40`。历史中间审核保留，不代替本次最终绑定。

两个owned进程 PID43204 / PID27924 均exit0、closed/reaped，最终查询无残留。各自owned对象/mesh/rig已移除，宿主回调回到启动基线，profile=None；同一原blend运行前后与收口当前SHA相同，未保存。独立审核完成后，cleanup_baseline.ps1先验证绝对目标仍位于本工作区、无reparse point、138文件逐个符合Git材料清单，再移除唯一临时旧运行目录。CLEANUP.json保留路径、校验与清理状态；不提交重复runtime副本。可在隔离审核副本用materialize_baseline.py恢复固定Git材料，再运行标准库audit_pair.py；不需要新Blender试次。

不新增模型训练、MCP工具、正式配置切换、用户原资产编辑、保存或云端上传。当前写入域仍是完整生成三骨、固定帧、有限同轴LBS与指定sentinel；不扩展通用角色、动画、IK、连续路径、自交或体积判断。准备对象是独立统计快照，直接持有它不构成当前来源准入；产品analyze始终先capture。和旧合同一样，在_inspect/_read_static失败、尚未算出changed时prepared属性可以仍指向旧快照，但analyze会因capture失败退出，不消费它；本轮未新增专门覆盖该属性残留的序列测试，不声称所有失败都清空属性。

本批到固定提交、一次完成回报后结束。管理员审核后关闭该限定三骨执行闭环，不自行开展另一轮性能或新模块。
