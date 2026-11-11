# M4-DEFAULT-LATENCY-ATTRIBUTION-001：保存原件与 QA 运行语义独立复核

**结论：未发现阻塞本批归因结束的真实产品错绑或记录缺陷。** 四会话原始记录支持作者已收窄的结论：本 QA profiler / 状态检查 / 计数发布链的 ON−OFF 配对差为约 7.49–8.41 ms。它没有查明前批 +1.341 ms 的版本差成因，不能换算成纯 callback 成本、无 QA 的生产性能、复杂任务收益或整版准入。

固定实施 HEAD：`a1b402a434623c82ebcec2a48c7a09f0ca97d7df`。实验使用旧 B=e077/53db 与 C=a81/9f28；不是当前 4eb schema 修复版。全部工作只读原件和源码，零产品导入、零 Blender、零模型、零新增计时样本、零运行源复制。本轮读取并固定 480 个原件/代码文件摘要，写入仅在本审查目录。

## ON/OFF 实际改变什么

已读固定 `entry/qa_instrumentation.py` 和 `entry/qa_native.py`。两模式均创建状态与 callback closure，前后调用 host_work，保留场景指纹、PNG 扫描、文件校验、命令执行及文本落盘。ON 额外安装当前 worker 线程的 `sys.setprofile` callback，逐 Python/C profile 事件分派、采计数，并观察与恢复；OFF 不安装 callback，四类 callback 字段均为 null / not_collected。

ON 的作用范围包围 native worker 的 RPC 处理，包括 QA 的保护和落盘工作；不仅是 capture_task_scene。事件发布位于 profile 恢复之后，ON 计数字典和 OFF null 也改变发布内容及外层耗时。profile_scope 包含 before 采样和 profile 设置、业务及恢复，after_probe 又包含恢复和 after 采样，区间有重叠。故 ON−OFF 是本实验整条 QA 模式链差异，不能将 profile_scope 或配对差当作互斥的纯采集/回调开销。

只有暖请求开启 ON；这 40 次都命中已有结果缓存。几何求解在 cold OFF 完成。本矩阵不度量 solver 被 profiler 影响后的成本。ON 记录三个 capture 路径各一次，C 方法字典均为空；既有 bpy C 回调可见性限制继续成立，空字典不能证明没有 C 工作。

## 本轮从原件重新核对的结果

| 本轮独立读取/重算 | 结果及真实分母 |
|---|---|
| 原始 WORKER_EVENTS 序号与事件 | 4 会话 × 23 = 92，包含 88 业务 + 4 关闭 |
| getprofile 初始 None、最终恢复 None | 92/92；来自原始记录与对应实现语义，不是重新启动后现场观测 |
| ON callback 状态 / OFF 未收集 | 40 ON 字典；52 OFF null，其中 4 次为关闭 |
| 固定请求的 TX/RX、运行源与公开事实 | 88/88；未请求 geometry，原始 wire 与固定请求模板一致 |
| 同会话事实与绑定 | 88/88 完整响应仅移除 trace_id 后相同；未丢弃 context/身份字段 |
| 原始 capture → host residency → compact 公开身份 | 88/88：对象与实例、代次、范围、revision、schema_version/document_epoch 均对应 |
| 会话间事实 | 按原对象名称比较三对关系、证据/距离/方向、sets、coverage、measurement_contracts 均相同；不将各会话临时 ID/源摘要宣称相同 |
| cold 与暖/预热记录 | 4 cold，84 暖/预热；cold 资源 4 个，后续 resources=[]；暖记录只有三个零内核计数与 result_cache_hit=true |
| 原生 SCRIPT/stdout/stderr 落盘关系 | 88 份 SCRIPT、88 份 stdout 需要 LF↔CRLF 转换才能与内存元数据比较；264 份文件均满足往返关系，stderr 均空 |
| 图片与 render | 原记录的 construction 字段为 []，全部 worker 事件无新增 PNG / render 增量 |
| 关闭状态 | 保留 4 条 legacy close status=unknown；分别有 closed 回执、exit0 和未 poison 终态，未改写成 completed |

从记录的 `ended_ns-started_ns` 独立重算四会话配对中位差：01_B=7.71165 ms、02_C=8.41025 ms、03_C=7.49280 ms、04_B=7.81445 ms，与作者报告一致。没有新计时。实验版本比较单位依然只有 4 会话、每版本 2 次；88 不是 88 个独立资产或质量题。

## 缓存字段修正是否合理

独立核对两套实际隔离安装的 `_observe_task` 与 `ReadContext.result` 字节和保存源码片段。每次 `_observe_task` 先初始化 `exact_pair_count/surface_pair_count/closed_solid_pair_count=0`；缓存命中时 `result` 返回 deepcopy(cached)，不调用 compute，随后补 result_cache_hit。因此暖态没有 pair_calls/rank_calls 是该分支真实接口，不是运行时漏记了必须存在的两个零字段。

cold 实际记录的五项计数为 0/3/3/3/1（exact/closed/surface/pair/rank）；三个相关几何关系已求解，不能把 exact_pair_count=0 读成没有精确几何工作。暖态零计数只表示这些受监测计算未新增；不能推出宿主、身份检查、缓存复制或序列化没有成本。

冻结分析器 `ce877249…` 原字节仍在。run_01 的 `KeyError: pair_calls`、部分检查及原脚本保留。派生脚本实际 diff 仅新增暖窄字段 helper、替换暖检查、将未发出的 pair/rank 标注为 not_emitted_on_cache_hit，cold 检查和数值分析规则未改。已重算并比对保存 diff；没有将缺失字段回填零。本批 84 份原始 warm 诊断恰好全部为上述四键，所以修正成立。

## post-run 修正与失败保留

作者第一次 post-run 审查留下 3 个失败项与 pair_calls KeyError。初始 ERROR 摘要与最终回报引用一致；旧脚本也保留。本轮读到的修正分别是：图片 construction 字段从错误的 `==0` 改为实际 `==[]`；SCRIPT/stdout/stderr 按 Windows `Path.write_text` 的换行边界比较；暖字段按真实缓存分支比较，并在额外 pair/rank 字段出现时仍要求零。`qa_native.py:351–364` 明确先以 write_text 落盘，却对内存 code/raw_out/raw_err 计算摘要/长度，故换行修正有代码和逐文件往返证据。

转换仅用于这三类文本与其逻辑元数据的对应；源码、安装和 TX/RX 原始字节没有被全局归一化。PNG 与 warm 修正不涉及更换业务样本。作者的 1502 / 1581 是保存记录的断言数，不能当作独立实验数；本轮没有机械重跑这两套分析器，也没有重跑作者 12 个准备方法或 9 条合成 metadata 变体。

## 本轮审查自身的首轮错误

`RESULTS.json`、`INPUT_PINS.json` 和 `review_saved_runtime_first.py` 保留未改。第一版独立脚本把原始 capture.host_identity 与 compact context.host_identity 直接作全字典比较，产生 88 个失败；这一错误也使该首版的绑定“计数”不能表示成功数。

查阅并固定两套安装 `live_spatial_mcp.py:594–608` 后确认：公开投影将 object_instances 拆到 target/candidates[].instance_id，并去掉与 context.capture_scope 重复的 host 字段。r2 没有删掉身份检查，而是逐项核对整个 object_id 集合、每个 instance_id、原始/公开 scope、revision 和剩余 host_identity。`RESULTS_r2.json` 记录 88/88 对应且失败为空；首次失败文件摘要及明确纠错原因也写入 r2。未发现真实产品错绑。

## 收口与未测

本批可以以“保存原件完整、模式链有可测差异、版本增量原因仍未知”结束；不因未知再开本批补测。不扩产品改动、不据此默认发布。独立几何真值重算、无 QA 生产耗时、跨资产/模型任务收益均未测。原性能未决保留。

实际独立脚本：`review_saved_runtime.py`；当前有效机器证据：`RESULTS_r2.json`、`INPUT_PINS_r2.json`；作者 post-run 前后差异：`POSTRUN_REVIEW.diff`。
