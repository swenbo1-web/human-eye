# TASK-RUNTIME-CLEANUP-001

唯一产品候选 `201fccc4de85c64e3c0ddb11dfeb3489c976661c` 已完成离线验证。固定父基线 `aca915f45d57b5e5a3d75e9f8a0beb1e64e8f8c6`；131 源摘要由 `3b424a7f26abf614949513178e3c295b1658928d6f0eed9234409f818e2e6ec1` 更新为 `9df00f3f3327d221b9b36d9e52995cbff6fb7311a7520d27191bbc124c0e3735`。本批只改 live_service.py、host_runtime.py、auto_router.py；每份131运行源的磁盘字节、测试加载身份、固定 Git blob 均已核对，旧三批68个证据文件逐字节不变。

## 实现与语义

task 分支原为删除当前 prepared 而执行 export→过滤→import 整个 runtime。现在调用锁内 `_discard_prepared_session`：按原 host→router 锁顺序清理受信内存中的观察状态，再删除当前 host prepared。router 的新 helper 是原 import 清理段逐句搬移，顺序和各处时钟调用不变：attention_retry 校验/清除、observation 合同/指纹/TTL 失效、refill_retry 校验/清除。首次磁盘 import 仍先验证全部历史 scene/fingerprint，再调用同一 helper；最终 `_save`、预算和发布位置未变。没有吞异常、第二个状态层、可信参数通道或新框架。

当前 task 不产生执行授权；当前 host prepared 删除，router 同名会话保留，其他 prepared、pending、quarantine、历史 frames/blobs 和进程内 measurement memo 保留。attention/refill 的30秒 episode 边界仍包含，retry_at 已到且 episode 未过仍保留；TTL120秒边界包含，121秒清 observation；时钟倒退使可选记录失效。清理完成后才 pop prepared。编码或发布失败发生于保存之后，磁盘不会恢复已失效的 prepared，也不重做 host 动作。

surface_nearest 分支未改。选择器、schema、窄工具目录、来源检查、求解算法、unknown/精度和支持域均未改。source identity 随实际代码字节自然更新。唯一实施者负责所有产品写入；一名只读协助者核对清理语义、diff、计时设计和证据，未运行测试、导入产品、写文件或调用 host。

## 正确性与完整分母

候选15个新方法通过；相同脚本在固定 baseline 源上14通过、1项新方法专属检查跳过。另26个既有相关方法通过，候选当前共41个不同方法通过。完整历史是86次 unittest 方法执行＝82通过、2失败、2跳过：首次候选14/15通过、首次基线13通过/1失败/1跳过，fixture修正后候选15/15、基线14通过/1跳过，相关回归26/26。没有把基线与候选执行当作独立产品覆盖，也没有把修正后的通过覆盖历史失败。

两个失败均来自测试误以为 preview 会持久化 pending；实际 preview 使用隔离 router。测试改为用公开 router before_action 事件形成合法 pending，未调用 host mutation，产品无改动。完整失败源及原日志/JSON保存于 failed_01 文件。另有三个比较/脚本设置错误（未归一化 UUID/缓存耗时、shell转义、isolated模式导入路径）；详情与原始差异在 HARNESS_NOTES.md、equivalence_preflight_01.json，不计入 unittest 或性能样本分母。

根的固定三历史场景 fixture 通过公开 service.observe 建立。稳定时钟与 task求解后1000→1121两例重现；每请求历史几何验证 **6→3**，runtime import **2→1**、export **2→1**，当前 capture_validate、host capture、task_result 仍各1。初次来源/指纹恢复拒绝、TTL恰好120/超过、attention/refill有效/已到重试时点/恰好30/超过/倒退、pending、隔离/inflight阻断、cache对象与已有memo、保存后编码/发布失败均有断言。默认与窄入口、禁图/隐藏工具拒绝、原预算、旧恢复、retry恢复回归通过。

12组基线/候选完整终态及事实结果跨进程对照一致。跨进程比较排除配置指纹、源码摘要、trace和缓存估计耗时，对随机 observation UUID 做一致重命名，并解析嵌套 context JSON；pending引用关系随同一映射保留。比较器另排除预期不同的counts，该计数在两侧分别严格断言。每个进程内部仍核对解析后的完整保存状态（dict/list相等），仅有预期 prepared 删除和可选 TTL/retry 失效，未把其他实际差异归一化掉。EQUIVALENCE.json保留结果。

## 一次冻结计时

正确性通过后，仅执行一次冻结的20对、40次完整公开 service.observe，AB/BA交替各10对，固定相同三历史会话及当前 task。TIMING_PLAN 固定脚本SHA与两侧131摘要；每个子进程检查摘要。所有40个样本和配对状态/结果一致，无失败/丢弃/补跑/挑选批次。

| 完整 observe，20个全样本/侧 | 基线 | 候选 |
| --- | ---: | ---: |
| median ms | 28.0714 | 26.1882 |
| p95 ms（nearest rank，排序第19/20） | 30.3064 | 28.0866 |
| 历史场景验证总数 | 120 | 60 |
| runtime import/export总数，各 | 40 | 20 |
| 当前 capture/task_result总数，各 | 20 | 20 |

median下降6.7086%（1.8832 ms），p95下降7.3245%；pair 9略慢（28.0541→28.2855 ms），该样本保留。完整计时批次23,670.622 ms。计时边界包含公开 observe 的来源检查、加载/首次恢复、捕获/校验、task事实、清理、保存和audit；没有只计几何核。两侧使用相同轻量计数装饰。40次子进程每次独立准备合法状态；完整process_wall_ms、imports_ms（含脚本前置/导入，并非精确纯启动）、preparation_ms分列在原始样本，未混入observe数值。全部排序样本、原始顺序、stdout/stderr/退出码与计数均保留。

| 独立列示的进程/准备 median ms | 基线 | 候选 |
| --- | ---: | ---: |
| 整个子进程 wall | 701.988 | 474.545 |
| 脚本前置及模块导入 | 421.565 | 210.247 |
| 配置及三次历史观察准备 | 93.637 | 81.602 |

两侧源码位于不同固定目录（基线D盘副本、候选C盘工作树）；这些进程导入与准备差异不归因为本产品优化，也不拿它们宣称完整消费流程收益。中位数不可直接相加为另一个中位数。

这是单个小型内存fixture上的本地离线结果，无法推广为生产或模型端到端耗时收益。结构证据是避免一次全历史几何恢复；性能没有做显著性或更大历史规模外推。没有启动 Blender、真实 MCP/host RPC、模型、API、GPU或网络请求，也未部署。本候选不混入WACQ冻结990的采用率对照，不能解释此前HE0或声称解决模型总成本。

## 身份、边界与交付

任务单SHA `ef873a47689b66f3e98542374f83ed8c26c81b2ac576afbd9d37088d64adb949`；根反例result SHA `7caa49c0fce4160a2ab8a0b4ba9bab230bdf7fe88d348c5b2145b11352e53257`，均已核。基线采用根固定副本review_990/source，131源逐字节等于aca915f Git基线。源码校验与旧证据结果在SOURCE_AUDIT.json，原始测试、样本、计划及SHA在本目录。

app本轮起点2026-11-09 01:18:43 UTC（上海09:18:43），35分钟截止01:53:43 UTC。RESULTS记录装配阶段累计耗时，最终回执另报含证据提交/校验/发送准备的完整累计，避免拿1.5秒测试或23.7秒计时批次冒充工程耗时。产品提交与最终证据HEAD分开固定。完成回报TASK_RUNTIME_CLEANUP_001_COMPLETE后结束，等待根独立深审；不轮询、不自行下批。
