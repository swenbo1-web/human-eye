# 九格匿名质量包：独立完整性与两字段派生复核

结论：**通过，无包完整性阻塞。** 固定证据提交为 `f5cfcf5e4768b1b6c31127b5d4a6c1227b8d7907`。本轮独立脚本完成 **4,944 项检查，全部通过**。读取 2,336 个不同文件，保留 2,426 条摘要记录；公开深读和批次盲算有重叠，因此摘要记录数不代表独立文件或实验数量。正式消费者分母仍为九格，本轮新增 Blender、产品、模型、API 实验均为零。

## 固定包与 Git 字节

- r2 ZIP：`5d2ca81f18285da1fff1a05b9c0c03deb97966f57db86fa022c8ecc0b091f54f`，295,089 B。
- 最终 42 文件 canonical：`03c566a5438fad7454b1d9f91157c3627a5fbd3740856972b61a353338fec101`。
- 原公开树 canonical：`1b8136e92e8533d6a7b95dddf952165ed58baff206c4551aa473728cbf20b8b2`。

重新按 POSIX 路径排序，以每文件 path/bytes/SHA256 构造 canonical JSON 并计算两个摘要。r2 只有 42 个唯一相对成员，与 `quality/public/` 精确同集合、逐成员同字节，没有额外目录、重复成员或路径越界。PACKAGE_RECEIPT、ADMIN_REDACTION、FORMAL_QUALITY_READY 的最终摘要一致。

整批 2,335 个 manifest 文件只进行字节哈希和 Git blob 比较，全部与固定提交一致；清单自身也核 Git 字节。总计 36,386,952 B，实际文件集合与 manifest 一致。私有文件仅流经哈希，不解码其 JSON、不打开其 ZIP，不输出私有路径与匿名格的对应关系；结果使用序号及路径摘要记录这些检查。工作树前后均干净且 HEAD 未变。

## 两字段 redaction 的独立复算

程序读取原公开 INDEX，在内存中只删除以下两个位置的 `perf_ns`：

1. `$/answers/1/consumer_execution_errors/0/perf_ns`
2. `$/answers/3/consumer_execution_errors/0/perf_ns`

删除后的编码字节与最终 INDEX 完全一致，删除值的 canonical 摘要及完整 error event 摘要与行政回执一致。向最终 INDEX 放回这两个原值后，恢复的字节与原 INDEX 完全一致。原值未打印、未写入本轮结果。其他 41 个公开文件逐字相同，错误 event 和 message、所有其他 INDEX 结构没有改变。

原 INDEX 摘要 `cfa43ad3…0524aa`，最终 INDEX 摘要 `c6e41a0f…a774af` 分开保留。原公开树及历史匿名 ZIP 仍存在并与登记摘要一致；本轮没有打开初始匿名 ZIP，只盲算其原字节摘要。未运行作者 `redact_handoff_admin.py`，只读取该脚本并核其摘要，实际派生比对由本轮脚本独立完成。

## 九份公开交付和失败保留

九个匿名目录完整，每个包含 answer、CLI 文本、source_consistency 和 tool_evidence。九份 answer 与各自 CLI 逐字相同，且匹配 INDEX 中 answer_original_sha256 与 public_final_sha256。共同题面及三份评分材料均匹配登记摘要；没有进行答案内容评分。

INDEX 保留 **7 completed、2 failed、0 未运行**。两条错误均保持原始 `stream disconnected before completion` 的完整 event/message，两格 valid_completion 继续 false，仍交付其最终文本。不存在用回答文件存在来替换执行失败的情况。公开原件保留 27 项业务尝试、54 条工具开始/完成事件；相对于原公开树没有删减、合并或重排其证据文件。

source_consistency 的公开摘要链接与 INDEX 一致，资产摘要在 ACTOR_CONFIG 与 owner_IDENTITY 间一致，初末文件摘要引用、worker 指纹重复字段和零图片记录相互一致。provider_delivery、model_view 等 null 值和说明保留。本轮只验证公开字段之间的关联，**没有把作者的来源字段提升为独立私有运行验证**。

## 交给根的使用范围

可以把此 r2 包固定为匿名质量评审输入。实际工具文本可能暴露路线，匿名仍是有限匿名。九份 final 与真实私有 consumer.final、模型最后消息及运行格的最终映射，应在质量 seal 后检查。运行身份、九线程、新鲜 owned 后端、18 份实际快照、真实退出、usage 与成本也留在解封阶段；本轮未作这些结论。

本轮未解码私有组别/成本、未打开原始完整私有 ZIP、未评分、未改作者证据或 Git。AL 自身旧 assignment 仍为 current=false；未借用根句柄或覆盖父任务。本轮任务依据根对九格匿名包完整性/派生的直接委派。

可复核产物：`check_package.py`、`RESULTS.json`、`CHECKS.json`、`INPUT_HASHES.json`。脚本首轮无失败；仅随后增加独立文件计数，避免将重复摘要记录数误报为独立输入数，复核结果仍为 4,944 项通过。
