# SURFACE-FACTS-001-A

A 的功能候选已完成，定向测试与隔离安装实际入口均通过。新增显式 `surface_proximity`，在现有 `query.mode='task'`、A→B 两对象选择中返回当前三角表面的非负最小距离、原表面见证、正距离方向及最小拓扑计数。开放表面不再因旧实体支持域而丢失这些可计算事实。这里只交付工程能力；消费者答案、额外付费 API 均为 0，模型补读行为与净收益未测。B 未开始，需协调方独立复核。

候选代码提交：`0acf1faaf6e5db24af7c93370e5622255ebda833`。基线提交：`b579de2d8e806e2618bb11daef29d01317ec9249`。

- 分发版本：`9.7.2+surface.facts.a.1`。
- 固定运行源：131 文件，`0155c5509901ed85dbf255c98a71e81187cbd3b60ef7bd49adcbfa1b663af578`。
- 隔离安装：本目录 `venv`；保留旧 `task_contract_001/engineering_r1/venv`。未改默认安装。
- 核心索引：[EVIDENCE_INDEX.json](EVIDENCE_INDEX.json)；字节复核：[FINAL_SOURCE_VERIFICATION.json](FINAL_SOURCE_VERIFICATION.json)；计量：[MEASUREMENTS.json](MEASUREMENTS.json)。

## 数学与合同

测量对象是本次捕获的求值三角表面、世界坐标、米，不能复原捕获前已损失的坐标。只处理面引用的顶点，以输入 binary64 的精确二进制值做有理相减并建立共同整数坐标系。完整输入、拓扑及退化检查先于零距离提前返回。每个三角对先做双向边穿面及共面相交谓词；无交时比较 6 个点面、18 个含端点的点边、9 个边边内部候选，以精确平方距离选出全局胜者，只为最终胜者构造见证和开平方。[MATH_PLAN.md](MATH_PLAN.md) 给出公式及独立答案来源。

预算是 A+B 总面数 ≤4096、跨对象三角对数 ≤16384、保留整数及约分后有理分子/分母 ≤4096 位。单次乘法、比较、加法与最终舍入的临时量明确允许最多 8193 位；不能将其描述为所有运算均只用 4096 位。不分配完整乘积矩阵；沿现有请求检查点传递取消与期限异常。未引入 BVH、三角 AABB 下界裁剪或永久缓存。

标量距离使用整数平方根与精确中点比较做 binary64 最近偶舍入。正值若小于可交付浮点范围，则给出具体 unknown 原因，绝不吞成接触。世界见证分别检查精确平方欧氏误差、位移误差和发布后点距，误差界 1e-9 米；正距离不发布相同点。已知距离与独立可知方向可在世界见证发布失败时保留，整体 partial。真零距离的方向为 `not_applicable`，事实仍完整。

拓扑只给 A/B 各自边邻接一次及超过两次的计数，零边界不认证实体。严格包含时表面距离可以为正，旧负 escape 语义保持。新增计算有独立算法缓存键；复用时使用本次 binding，更新几何使缓存失效。面数/乘积超限在完整展开前拒绝；大量松散顶点直接走受限数学核，绕开全网格缓存键序列化。旧事实未请求新事实时不新增此计算。

运行源只修改 `live_service.py`、`live_spatial_mcp.py`、`task_query.py` 并新增 `surface_proximity.py`。旧 130 文件中 127 个保持字节相同，`geometry_safety.py`、`surface_geometry.py`、SAT 及动作模块未改。工具说明 959→1214 UTF-8 字节，增加 255 字节中性能力说明；没有模型提示优化。见 [SOURCE_DELTA.json](SOURCE_DELTA.json) 和 [TOOL_DESCRIPTION.json](TOOL_DESCRIPTION.json)。

## 定向验收

正式定向清单只运行一次：124 个唯一方法全部通过，失败/错误/跳过均为 0。其中新方法 41 个，相关旧方法 83 个。方法内的多子用例不另冒充分母；以下“未运行”只针对本次选定清单。[UNIT_RESULT.json](UNIT_RESULT.json)、[GROUP_COVERAGE.json](GROUP_COVERAGE.json) 保留方法 ID 与结果，原始运行输出见 `targeted.stderr.log`。

|组|实际覆盖|通过/分母|失败|未运行|
|---|---|---:|---:|---:|
|1|原 G 开放斜面、混合旧实体 unknown|2/2|0|0|
|2|双向边穿面真零距离|1/1|0|0|
|3|共面分离、点接触、共享边、面积重叠|4/4|0|0|
|4|面/边/端点及双边内部最小值、非轴对齐、交换对象|5/5|0|0|
|5|闭合体分离、穿插、严格包含及旧负 escape|4/4|0|0|
|6|微小正隙、微小相交、平方浮点下溢、细长近平行|4/4|0|0|
|7|大平移、输入已丢细节、世界见证、位数/浮点范围、次正规舍入边界|7/7|0|0|
|8|错误索引、晚出现退化、非流形、重复/面序、松散点|6/6|0|0|
|9|缓存/当前性/更新、旧混合值、单次采集编码、无 SAT、取消/期限、预展开预算|8/8|0|0|
|10|隔离安装实际入口：G 初始、G 更新、边穿面、闭合体控制|4/4 observe|0|0|

相关旧方法来自 task query、selected task query、TASK-CONTRACT-001、TASK-COMPLETE-001，包含已有微重叠、正交、多组件等关键回归。未跑全项目矩阵，未改内核的旧审查通过字节证据复用。

真实缺陷：开发期独立数学审查发现固定 80 位 Decimal 标量开方不能正确区分最小次正规数半程两侧。`s=2^-1074,H=2^300` 的一对真实三角输入，精确距离分别位于 `s/2` 两侧；原实现两侧都返回 s。修复后正侧舍入为 s，负侧明确 `surface_distance_below_float_resolution`。原始修前/修后输出分别保留在 [ROUNDING_BEFORE.json](ROUNDING_BEFORE.json)、[ROUNDING_AFTER.json](ROUNDING_AFTER.json)，另有 9 项正常中点/最近偶/溢出开发检查 [ROUNDING_GENERIC_AFTER.json](ROUNDING_GENERIC_AFTER.json)。此修复发生于最终源冻结、首次正式 suite、唯一构建之前；正式 suite 或 QA 没有失败重跑。Decimal 80 位只用于方向归一化。

## 隔离安装实际入口与工作量

唯一构建、唯一新隔离安装使用本地依赖缓存及 `--no-index`。构建、定向 suite、安装身份和全部实际返回的运行源完全相同；最终离线重新核验 checkout 与安装的全部 131 个文件字节，以及 wheel 哈希。五个 QA helper 中四个保持原字节；本地 `perf010_qualification` 仅将历史固定 130 的校验改为显式 `--source-count`，未改旧 helper。见 [build/BUILD.json](build/BUILD.json)、[INSTALLED_IDENTITY.json](INSTALLED_IDENTITY.json)、[QA_COPIES.json](QA_COPIES.json)。

测试资产均为副本；作者在运行产品前给定解析真值并保存原生构造回读。G 的初始距离为 sqrt(3)/64，唯一顶点更新后为 sqrt(3)/32，方向始终 (1,1,1)/sqrt(3)，各 4 条边界。边穿面为真零，共同见证与方向不适用。闭合控制为 1/16 米分离、+X 方向及各 0 条边界。原始几何、真值与来源在 `author` 和 [ASSET_PROVENANCE.json](ASSET_PROVENANCE.json)。G 新鲜捕获指纹与 revision 均随更新改变。

|实际观察|距离 m|CLI stdout 字节|CLI 进程 wall ms|实际三角对/相交检查|
|---|---:|---:|---:|---:|
|G 初始|0.027063293868263706|1370|267.3708|4/4|
|G 更新|0.05412658773652741|1376|241.4198|4/4|
|边穿面|0|1319|278.8928|1/1|
|闭合分离|0.0625|1305|300.2591|144/144|

共 5370 字节，CLI wall 合计 1087.9425 ms。CLI 计时覆盖 `subprocess.run` 开始至返回并回收，包含进程启动及服务端计数写入；不含响应断言和证据落盘。helper 与 service 的原始内部计时另存 MEASUREMENTS，属于嵌套区间，不能相加。没有隔离数学核计时，也没有用旧 unknown 的低耗时当性能基线。

离线封存脚本首次错误要求旧 helper 的 `finished-start` 与 `elapsed` 完全相等，聚合断言失败；检查旧 helper 源码确认二者分别取时，实际相差 100–300 ns。已保留原始值和逐记录偏差后重新聚合通过。这不是产品运行或 QA 重验，没有增加 observe。

真实包装原函数计数合计：4 次 selected capture、4 次表面求解、4 次 task 编码；旧 strict pair、paired SAT、fallback SAT、full capture 均为 0。准确工作合计：验证 34 面、引用顶点 38 个、153 三角对/相交检查、912 点面、2736 点边、1368 边边，`predicate_steps=144`。此最后字段仅是共面裁剪循环的加权检查数，不是全部标量谓词/整数运算数。计数来自实际 cache miss，历史缓存 result.work 不重计。逐观察原件在 `acceptance/*/*.COUNTS.json`；一次采集与编码也有正式方法验证。

## 配额、边界与交付

已用：1 构建/安装、2 独占 QA 会话、4 observe、1 QA 顶点更新、2 额外非求解原生回读；必要重验 0。资产构造另有一次后台 Blender，产品调用 0。两个会话正常退出并回收，强制清理 0，源文件与受保护文件未变。最终核对 28 条历史进程记录全部不在场，无本批 Python/Blender 遗留进程。见 [CLEANUP.json](CLEANUP.json) 及两会话 close 原件。未改原资产、共享 GUI、默认配置、根工作树或窗口 STATE。

完整 turn 起点为 2026-11-07T05:43:18.566Z，75 分钟截止 06:58:18.566Z；实验结束于 06:11:02.945Z 前。交付前封存耗时及时刻见 [DELIVERY.json](DELIVERY.json)；一次完成回报另附截至回报前的完整累计时间，包含实现、数学审查、构建、QA、整理和提交。路线时钟不重置。一次完成回报后释放本批独占会话与实施窗口，等待协调方独立复核。

剩余优化机会仍是精确三角 AABB 距离下界裁剪；A 对闭合分离实际遍历 144 对，尚未做该裁剪。B 不在本次授权中，未启动。消费者、额外付费 API、模型 token/补读避免率/净收益比较均未运行，不以工程通过推断其收益。
