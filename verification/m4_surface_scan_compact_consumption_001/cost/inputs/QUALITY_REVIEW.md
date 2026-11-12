# 同期三路九格：匿名质量复核

2026-11-13。固定准备 `3a1ba86c5fce2fe125671cc68a84b14031d318cb`，正式交付 `f5cfcf5e4768b1b6c31127b5d4a6c1227b8d7907`。本阶段只看匿名业务材料和精确答案，尚未解封私有组别、耗时、usage 或成本。

## 判定

九份最终内容均完整正确，合计 **639/639 匹配距离**通过，没有遗漏、误报、重复或距离超差。按冻结执行合同，主分类仍为 **7 complete_correct、2 execution_failure、0 incomplete、0 incorrect、0 not_run**；内容质量分另记 9 complete_correct。不能将这写成九格执行全部通过。

九份最终回答均有各自完整清单、毫米距离、足够显示精度和明确完整性说明，未把三角表面距离误当实体穿入或包含判据。六份逐行表、两份“零距离聚合＋正距离表”、一份按 A 聚合 B:distance 的表采用同一对象对标准，不能因表格行数不同误计遗漏；反向排列的对象对按无序 pair 核对。

执行和内容分开。公开 INDEX 保留 `answer_3990a6a4bf660eee` 与 `answer_4c4c0fa03baa1ee8` 两格 failed、valid_completion=false，其他七格 completed，九份 final 都存在。两格的原 CLI reconnect/response-body decoding error 仍在，随后有最终回答不会自动改写冻结执行合同，也不补跑。

## 输入和评分依据

共同题面 SHA256 `6a78e38a474647c0c0c49558be215864cb672932273b3e15ca6ba7f9fa02b4fc`；BASE 快照 `f8a578f78004a21e611c76d47506c5290f6015e7343e67b3b094a9e54da9884b`，精确 truth `a0f14b1a48601590445ce5e2d13bb34f56647caa2acedf3eeac97b32e8a656c7`。使用原 276 对有理平方距离和 `binary64(0.002 m)` 阈值判成员；显示距离以原 `0.000500001 mm` 误差门检验，没有因新格式放宽标准。

复用已独立核过的固定几何真值，不重做全三角求解。九 final 的读法由两个互不读取对方输出的子审分别实现；根另逐份读完文本，记录于 ROOT_MANUAL_REVIEW.md。检查完整性、未知处理、额外确定错误和表达单位，不要求消费者使用指定算法或重复工具清单。

数值子审 453 项检查通过；另一子审独立解析全部 639 行并逐份人工封定语义、按公开业务 content 关联证据。根交叉比较两套展开后的全部 pair/十进制数值、最终内容分类、执行分类和公开 final SHA。中间 NUMERIC_RESULTS 的 pending=true 不是最终判定，最终使用 answers/RESULTS 中九个 pending=false 的封定结果。

最近阴性距离约 2.250 mm、24 网格/978 三角、43 零距离和 28 正距离等额外声明与公开几何及精确 truth 交叉核对。初末来源公开字段只说明记录的快照/资产一致，完整私有加载和调用链绑定留 seal 后解封，不能把生产者自报当已重演历史执行。

匿名 11a4… 业务记录曾输出 70 行，后续修正为 71；最终清单完整，中间记录和额外调用成本保留。根核验器过程也保留：一份解析器初次漏识“扫描状态为完整”同义表达，另一份初次比较了不同外层封装；均按原文本/业务 content 修正，不作为模型答错或删除原 attempt。

## 匿名包及派生修正

最终使用 `quality/SURFACE_SCAN_COMPACT_ANONYMOUS_QUALITY_001_r2.zip`，SHA256 `5d2ca81f18285da1fff1a05b9c0c03deb97966f57db86fa022c8ecc0b091f54f`，42 文件 canonical `03c566a5438fad7454b1d9f91157c3627a5fbd3740856972b61a353338fec101`。初始包存在两条错误信封的行政 perf_ns；r2 仅剥离这两字段，原 error event/message 与其他结构保留，其余 41 文件逐字不变。原件、冻结打包器和初始 ZIP 仍保留。

独立包核验 4,944 项通过：42 公开文件与 r2 ZIP、canonical 和固定 Git 一致；九份 final 与 CLI 公开文本及声明 SHA 对应；27 项业务尝试/54 公开工具事件保留。全批 2,335 内容文件仅盲算摘要和 Git 字节，未解码私有组别/成本或原始 ZIP；私有运行与匿名映射的内容对应留 seal 后验证。两处精确 redaction 可恢复原 INDEX 字节，两个 canonical 不混用。

这属于有限匿名：工具名称、内容和 incidental 业务输出可能暴露路线或带计时文字，不对这些文本做关键词清洗；评分者不读取私有组别/成本，不用偶然见到的时间作质量判断。正式成本解释留下一阶段。

## 后续唯一事项

封存 QUALITY_SEAL 后只解封同九格成本，执行 [成本计划](M4_SURFACE_SCAN_COMPACT_CONSUMPTION_001_COST_PLAN.md)。严格保留原执行状态和质量前提，九格全部计入账本，不删错误、不补样。可描述九份正确内容对应的实际成本，但不得将此替换原正式有效完成门。

若某比较的双方未满足原各 3/3 有效完整正确前提，则正式门不能记通过；仍以完整证据判断格式是否减少重算、token 和耗时，不把连接错误混成几何错误或忽略已有答案。实际 provider 输入、版本解析、费用等不可得项继续未测。本阶段新增 Blender、模型及 API 调用均为零，没有改产品、默认或原资产。

独立材料：[数值评分](../verification/fixes/20261113_m4_surface_scan_compact_quality_review/numeric/REPORT.md)、[逐答语义](../verification/fixes/20261113_m4_surface_scan_compact_quality_review/answers/REPORT.md)、[公开包与派生](../verification/fixes/20261113_m4_surface_scan_compact_quality_review/package/REPORT.md)、[质量 seal](../verification/fixes/20261113_m4_surface_scan_compact_quality_review/QUALITY_SEAL.json)。子 Agent 的旧 AL assignment 状态按各报告保留，未借句柄补造归属；根已在委派前登记本阶段。
