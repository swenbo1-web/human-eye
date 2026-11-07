# BOUND-SOURCE-QA-001：正常 RNA 可达的来源边界

**BOUND_SOURCE_QA_001_COMPLETE：一次有界来源判别完成，不是产品准入。** 普通顶点更新正确刷新 bounds；后续被引用顶点 NaN 和后续面越界索引均能通过本机正常 RNA setter 保留，规范更新后也未归一化。当前采集目录仍将这两个异常对象标为 `enclosed` 并严格排除。由此确认真实数据有效性缺口，不能再只归为假想坏网格；没有证明普通更新存在 stale-bounds bug，也没有运行最终 nearest 消费者或宣称错误 measured 结果。

## 冻结与实际执行

- 固定产品 `aaa7d881e5e369f486ea789fad1cf38b3a2bd594`，131源摘要 `2ef16a5e5b316453fff343ab8d2ff36b7b7c82113580137094f18896f1509664`，产品代码未改。
- 任务书 SHA256 `8eda6f90e041ed155f67787ba0b6d132f49399accc413472307a17a7172b20fb`。
- 复用原 `far_second_degenerate.blend`，SHA256 `9a7671bb202720b09311f313363bc0e5267017f2af155a9167fff4cf2d96d1b6`。只有一个新私有副本和进程，修改只发生在其内存，逐状态恢复；没有保存 blend、改旧资产或操作共享 GUI。
- 既有 NativeSession helper SHA256 `5bc1152aeafab89220c93edeec51cbe32ace458cc07d3e7d0507b6412b816fb3`，只加载原已核字节，没有改执行器。
- `run_01/FREEZE.json` SHA256 `877d4de381c9b4d4c1d2a37d1c4b154179978ce135d92d58ad9aae3775a1d19d`。PLAN、四份实际脚本、controller、worker_body 和预登记文件在启动前绑定；实际 TX 中的 code、worker 记录的编译 code 摘要与冻结值相同。
- 唯一窗口 `BOUND-SOURCE-QA-001-ONLY`，1 NativeSession，4状态 RPC＋1 close，4次产品捕获，0重试/第二session/builder/性能采样/模型消费者/付费API/安装。QA 内存 setter 确实执行；生产代码和默认入口没有变更。

本机一次返回：Blender `5.2.1 LTS`，build branch `blender-v5.2-release`，Release，build date `2026-08-25`，build hash `9e2066aef7ef`。冻结二进制 SHA256 为 `284f4041f98e113f3dc10654a7193ffaaa9bfdfec8b87fa116620a48b5f6d4cb`。这个自报 hash 与既有官方 tag `9e2066aef7ef7e20c142ad7bd3303138a4304c93` 前缀对应；它不是可复现构建、无发行补丁或二进制逐字节等于官方发行包的证明。build 字段只在状态1采集一次。

## 四状态事实

原远对象 `M4_Far_00` 有6顶点、2面、6角；首面 `[0,1,2]` 有限且非退化，后续面原为 `[3,4,5]`。focal 位于 x=0，near 位于 x=2。目录上界四状态均约 `2.000000000000001 m`。以下 oracle 由同一私有进程的完整 native evaluated data 独立读取，不用生产算法生成真值，也没有增加生产 gate。

| 状态 | 实际 API 与 native 事实 | 当前目录结果 | 判定 |
|---|---|---|---|
| 1 原始 baseline | 原远对象 x=100；所有引用坐标有限、索引有效，完整顶点均在 API 盒内 | 远对象 L≈99.9999999999999 > U，`excluded_strict_bound`；保留2对象 | 正常来源及原包络关系成立；未重跑旧 M3 unknown 判定 |
| 2 规范顶点更新 | `vertices[3].co=(.25,.25,.25)`，`mesh.update()`、`view_layer.update()`；新盒 x 最小值 .25，完整有限顶点被包含 | L≈.2499999999999998，远对象 `retained`；捕获3对象 | 正常 setter/dirty/update 路径工作；不是通过故意省更新造缓存问题 |
| 3 正常 RNA NaN | `vertices[3].co.x=NaN` 实际返回，立即读回、规范更新后及求值数据中均保留 NaN；后续面引用顶点3，首面仍正常 | 有限盒仍为 x=100 范围，`bounds_status=enclosed`、`excluded_strict_bound`，无 unresolved bounds/witness；只捕获2对象 | 真实非有限来源可以进入目录且被排除；有限首面/盒不是全对象有限性认证 |
| 4 正常 RNA 越界索引 | `loops[3].vertex_index=13`，6顶点时越界；setter和规范更新均返回，求值面为 `[13,4,5]`，其余计数和首面不变 | 有限盒、`enclosed`、严格排除；只捕获2对象 | 真实非法面引用可达；盒仍可包含所有已存有限顶点，但不存在有效的完整三角表面定义 |

三次构造均未被 API 拒绝，也未被正常更新修复；本轮没有调用 `mesh.validate()` 后换题。异常状态的采集请求确实执行并返回，不是只看 setter 回执。每状态只有一次目录捕获；完整坐标/索引 oracle 只作验证，状态4没有解引用越界坐标或强行对该面做 tessellation。

状态2的点为后续面的真实顶点，其投影 `(0,.25,.25)` 位于 focal 三角形内部；所以该点与 focal 的距离是 .25m，能独立说明保留此对象有意义。此处是简单几何事实，不是本轮执行 M3 的报告。

## 同状态、恢复与记录限制

四状态 capture 前后 graph 指针均为 `2320286589088`；frame、单位、evaluated对象/data指针、面索引及明确非有限标签后的坐标事实一致。每状态最终恢复原坐标和 loop 索引；执行器四次均记录 `terminal_geometry_and_file_checks_passed=true`、无 script error。原件/副本保护以及最终场景指纹相同，worker 未 poisoned。

冻结脚本使用原始 Python 字典比较 oracle。状态3的原始 `same_native_state_before_after_capture=false` 源自 `NaN != NaN`；文件中保留此 false。离线分析比较 `ORACLE_BEFORE.json` 与 `ORACLE_AFTER.json` 的明确 NaN 标签，四状态均相同；这只证明读取字段与非有限类别一致，不声称 NaN 位型认证。没有改 worker 再跑一次。

离线分析器首次错用了 `result_semantics` 字段，实际协议字段为 `result_kind`，退出 KeyError。错误类型、旧分析器摘要和零真实重放记录在 `OFFLINE_INITIAL_ANALYSIS_ERROR.json`。仅修正离线查键后完成核验；冻结 worker/controller、实际脚本和原始结果未改。

关闭事务的 helper 事件序号5保留初始 `status=unknown`，因为原 helper close 分支 break 未设置该字段；原始 RX 为 `status=closed`，owner 持有的 Popen 实际 wait 后退出码0，因此不以这个初始事件字段推断关闭失败或成功。

## 计数、字节和清理

| 项目 | 实际值 |
|---|---:|
| owned进程 / PID | 1 / 33056 |
| 状态RPC / close RPC / 产品capture | 4 / 1 / 4 |
| 发送尝试 / 完成字节（含close） | 114401 / 114401 |
| 接收字节（含close） | 56941 |
| controller墙钟（含启动、四状态及close） | 1.9795115秒 |
| owner close内部耗时 | .1449224秒 |
| worker最终状态 | 未poisoned、指纹相同 |
| owner wait回收 | 已回收、退出码0 |

四条状态 TX 各28596字节；close TX 17字节。原始 TX/RX 文件大小与 metered socket 累计一致，5条请求与4状态/1关闭分母一致。墙钟只是本次作业生命周期记录，**不是完整聊天 turn 耗时，也不是新性能样本或收益结论**；原期限、脚本准备及完整turn截止另保留在任务书/PLAN/STARTED 中。

## 唯一最小建议

为**准备被严格排除的对象**增加一个宿主内只读的完整面引用有效性核验：每个三角角索引在范围内、被引用坐标有限；失败就拒绝该来源或保持未证明，不能继续标为已包络并据此排除。保留现有正常 bounds/dirty 路径，不因本轮另加“所有对象、每请求重算 min/max”的 gate，不调用会编辑数据的 validate，也不建立新缓存/代际平台。

该核验仍需读取该对象的全部面引用和相关坐标，不能拿另一个抽样声称完备；可以流式进行，不必输出完整 JSON、世界变换全部顶点或复制临时 mesh。实际成本和最终结果语义仍待根统一设计，本轮不实施、不重启已关闭的性能路线。本轮证据覆盖固定二进制、一个旧资产及这四个状态，不推广全部 modifier、异常格式或全部更新途径。

结论：正常更新无需为假想并发再加代际层；非有限和非法索引却有真实可达证据，应在“成为排除依据”之前补最小有效性条件。当前 `result_kind=acquisition_only_not_nearest_result`、`M3_qualification_performed=false` 和 `execution_authority=false` 原义保持。
