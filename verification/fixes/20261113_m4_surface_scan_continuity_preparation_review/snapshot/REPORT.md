# CONTINUITY-001：快照合同独立复核

2026-11-13。交付基线 `a206a96e51ca6293ea555f17960b964ba02f0606`。本复核只读作者树，离线执行候选的 `canonical` / `bind_source_snapshot` 两个 AST 提取函数，以及旧 `encoded` / `bind_snapshot` 两个纯函数；没有执行作者整套 checker、产品、Blender、模型或 API。

父任务 `3a93462f-7821-488b-89b9-ca8d2c0bed0e` revision 1 / write 620。子代理原 AL assignment 已过期，本次未借用父句柄或改父任务。

## 结论

**明确的完整几何投影足以本次固定 unsigned surface truth 与连续观察工程资格；不需要重建 rich QA 或补造来源字段。** 实际采集原件进一步证明本次输入经过固定宿主源码的静态准入，且对应同一份完整几何。候选没有发现阻塞本固定任务的几何、单位或非有限值放行缺陷。

唯一建议是将候选收敛成 **一个 `bind_source_snapshot` 适配函数，在唯一活动 `verify_c_turn` 中替换旧 binder 调用**，保留其余资格规则。候选另复制完整 `verify_c_turn` 没有必要，容易形成两套漂移的验收逻辑。旧冻结文件和原失败保持原样。

## 原失败与独立实测

旧 `verification/m4_surface_scan_001_opt1/engineering/common.py:63` 除 PID/文件路径外直接比较整包；原 `qualification/verify_continuity.py:91` 将 owner 的两字段投影传入它。已独立重现同一报错 `actual geometry or source fields differ from qualified state`。这是来源接口不一致，不能据此认定 scan 结果错，也不能把离线适配成功追记成原工程成功。

本轮 **73 / 73 离线检查通过**，其中 30 个负例均拒绝：单位类型/值/缺失/NaN/Inf；对象缺失、重名、改名、顺序；顶点值/维度/非有限；面索引/数量/类型/维度；矩阵值/维度/非有限；额外窄合同字段以及 rich parent 篡改。真实 INITIAL、FINAL、固定 rich 正例及从真实 capture 独立重构的几何投影都通过。完整原件和输入哈希见同目录 `RESULTS.json`、`INPUT_SHA256.json`，可重跑脚本为 `review_snapshot.py`。

实际 INITIAL = FINAL = capture 投影 = 固定 BASE 几何：24 对象、530 顶点、978 三角面，完整 local vertices、faces、4×4 matrix 和 scale 均精确相等；没有按容差放宽。投影 SHA 为 `3e8221fb17d07509f244af95268b85acdbaf9fcc3c1edca547d054bac8dbe5ee`。

原 C 分母仍为 **planned 3 / attempted 1 / completed 0 / failed 1 / not_run 2**，本复核不改变它。

## 为什么不需要重导出所有 rich 字段

这份固定 oracle 的世界几何由全部 local vertices、完整 matrix、scene scale 与 faces 确定。参考包已固定，canonical JSON 精确比较会拒绝错误形状、非有限值、整数/浮点或布尔替代等实际 JSON 输入差异；因此这里不必再写一套通用几何 validator。它是固定 24 对象 fixture 的资格适配器，不能宣传成一般场景 schema 验证器。

仅凭窄快照不能证明 parent/modifier/animation 等字段不存在。但本次还有实际请求局部的来源证据，而非臆造的默认值：

- 唯一业务 capture 是 `owner/native/WIRE/002`，序号 2 的 worker event 在 BASE 请求时界内；请求代码 SHA 与该 event 一致。
- 已从实际请求中的 base64/zlib 嵌入源离线解码，确认其包含完整 `blender_host.py` 字节；SHA `9a63545aec488cead3be508f97afefc9fa7135beb82e85cff10ca7ad4d3b59e9` 同时等于 capture binding、最终结果 binding 及本次读取源码。不是只核对文件路径。
- 24 条 coverage 均为 `supported` / `evaluated_static`，reason=null、scope_issues=[]；绑定为 world/m、frame 1、scale 1、same_main_thread_read=true。document_epoch 与 directory_sha256 同最终业务结果一致。
- 24 个 resource 引用及 revision/scale 对应真实 resource 数组，其全部 vertices/faces/matrices 独立重构后，与 owner INITIAL/FINAL 和固定 reference 相等。
- 已读宿主 `blender_host.py:813`、`:1344`、`:1649`、`:1738`：supported 之前检查 parent、children、constraints、modifiers、对象/数据 animation、rigid body、shape keys、linked、edit、instance 等限制；采集结束前又检查源码定义的可观察来源、资源 stamp、矩阵、数量、身份、frame 与 scope 未变。静态准入来自这些实际执行字节和采集状态。此轮没有重新做这些 guard 的 Blender 负例回归。

因此可复用当前固定宿主准入，不必为本题导出 material_names、custom_properties、blender_version 等不影响已冻结距离真值的字段。仍须保留候选 `rich_source_metadata_verified=false`：**宿主准入有对应证据，不等于独立记录并逐字段对比过全部 rich 元数据。** `external_edit_history_proven=false` 也不能改成已证明；本结论限本次捕获和固定工程实例。

## 最小后续修复与范围

1. 在新准备版本用一个显式窄合同适配器替换原 binder 接口；rich 输入继续原比较，返回实际 schema 和未记录字段，既不补字段也不把窄合同命名为 rich。
2. 同次 capture 的资源、matrix、unit、host source、document/directory 绑定沿现有原件核对，避免把任意独立快照当业务实际来源。无需增加新来源服务或额外 Blender metadata 导出。
3. 原事实、276 pair、匹配、kernel、单 capture、生命周期条件保持。若 actor/thin/worker/product 字节保持，未发现阻碍复用原 N 工程三轮、只运行唯一新 C 三轮的具体证据。N 复用不能形成新的性能配对样本。

已读根 `M4_SURFACE_SCAN_CONTINUITY_001_FIX1_PLAN.md`：以上边界、一套活动资格函数、真实 consume loop 的 fake CLI 贯通和唯一新 C 均已明确，**没有必改项**。无需追加本轮负例矩阵；真实模型续接仍留正式消费者验证。
