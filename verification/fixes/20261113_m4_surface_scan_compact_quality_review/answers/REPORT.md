# 九格匿名最终回答独立复核

2026-11-13。本次只读取公开质量目录与根消费方案，没有读取组别映射、成本、usage、其他评分结果，也没有调用作者评分器或运行 Blender、模型、API。

**最终执行保留分类：7 complete_correct，2 execution_failure，固定分母 9。** 九份现存 final 的内容均满足题目要求；两份执行失败不因此升级为成功。

本轮最终结果为 **`RESULTS.json`**：九份记录的 `manual_semantic_review_pending` 均为 false，并分别给出 `content_classification` 与 `final_classification`。`NUMERIC_RESULTS.json` 是前序数值检查记录，其中 pending=true 只表示当时人工语义审尚未封存，不能替代最终结果。

| 匿名回答 | final 内容分类 | 执行保留主分类 |
| --- | --- | --- |
| answer_11a4c8ec025d6a16 | complete_correct | complete_correct |
| answer_3990a6a4bf660eee | complete_correct | execution_failure |
| answer_4a4a77418ce1424c | complete_correct | complete_correct |
| answer_4c4c0fa03baa1ee8 | complete_correct | execution_failure |
| answer_89dab9e90194dcbf | complete_correct | complete_correct |
| answer_9297e204cfb1d7f7 | complete_correct | complete_correct |
| answer_9ee63c86af8ff66d | complete_correct | complete_correct |
| answer_bb2c246d257d7867 | complete_correct | complete_correct |
| answer_dccb27e1bc47c94f | complete_correct | complete_correct |

## 数值与呈现

独立解析器支持本包出现的三种明确表述：逐对三列表、A 对应多个 B 的零距离组表、A 对应 B:距离的合并表。人工逐份确认组表语义后再展开；无序端点排序仅用于集合比较，不合并重复记录。

九份 final 均为 **71 个唯一匹配对象对**，漏报、误报、重复均为 0；全部距离落在冻结精确平方距离的容差区间内。误差界为 **0.000500001 mm**，使用有理数比较平方区间，未拿四舍五入后的 oracle 开平方值充当真值。匹配成员按 binary64 `0.002 m` 的精确有理数平方确认。

九份均明确使用 mm；非零值显示三位或六位小数，满足至少 0.001 mm 的分辨率，真实零可写 0。零距离 43 对、正距离 28 对正确。未发现把微小正距离写成零的情况。

## 人工语义与额外陈述

逐份阅读了九份完整 final，均有明确且正确的完整性陈述，没有把表面距离误称实体穿入、包含、穿透深度或无碰撞保证。报告中的 24 个网格对象、276 对、71 匹配、205 不匹配与公开真值一致。提及三角形数量的回答使用 978，与冻结实际快照一致。

提及最小不匹配距离的两份回答，其约 **2.250 mm** 与真值一致；其中 `answer_3990…` 指定 `Obj_002–Obj_008`，也确为唯一最近不匹配对象对。43 零距离与 28 正距离拆分正确。

`answer_11a4…` 的公开业务记录中存在一个中间 70 行输出，后续修正为 71 行；其 final 与真值及完整业务记录一致。该中间记录保留，不当成 final，也没有删除历史失败或用另一格替代。

两份执行失败 `answer_3990…`、`answer_4c4c…` 的公开 INDEX 均记录流连接中断错误，`consumer_valid_completion=false`、执行 failed。本轮只判定其现存 final 内容正确，主分类仍为 execution_failure。

## 公开业务证据关联

每份回答都有至少一条公开业务记录给出完整正确的匹配事实。独立核对了结构化表面事实或原生数值输出，并将 owner 响应的 `content` 与公开消费者工具事件的 `content` 做精确比对。最终 `RESULTS.json` 按匿名 ID 和公开业务 order 给出对应关系，不汇总采用率或归因某个组别。

涉及全 276 对复核、112 候选/164 包围界排除、未知为 0、退化/有限坐标检查和表面相交算法的陈述，都能在相应公开代码及业务输出中找到依据。本轮未发现额外确定性错误。最终事实与公开证据相符不证明模型内部唯一使用哪条信息链；也不证明 provider 渲染输入完整。

公开来源记录显示共同资产绑定、初末记录相同、asset/geometry unchanged。它们是原生产者证据；本轮没有将初末相同外推为所有瞬时操作均已独立证明只读。包与原始私有封存绑定由根其他独立核查处理，本评分不进入私有材料。

## 材料与复跑

- `RESULTS.json`：最终分类、逐份人工理由、数值结果及公开业务证据关联。
- `NUMERIC_RESULTS.json`：独立展开的 639 行匹配、集合/精度检查及额外真值参考；属于中间记录。
- `INPUT_HASHES.json`：公开读取材料、根方案及复跑脚本 SHA256。
- `review_answers.py`：独立解析和有理数数值检查；不导入作者评分器。
- `finalize_review.py`：人工语义决定及公开业务内容支持核对。
- `REVIEW_CHECK_HISTORY.json`：保留本复核脚本首次将不同外层封装直接比较导致断言失败的记录。已改为精确比较业务 content，不将此记作产品或回答失败。

```powershell
& 'D:\hefe\.human-eye\releases\9.7.2+20261028.support.discovery.r1\.venv\Scripts\python.exe' -I -B -X utf8 'D:\hefe\verification\fixes\20261113_m4_surface_scan_compact_quality_review\answers\review_answers.py'
& 'D:\hefe\.human-eye\releases\9.7.2+20261028.support.discovery.r1\.venv\Scripts\python.exe' -I -B -X utf8 'D:\hefe\verification\fixes\20261113_m4_surface_scan_compact_quality_review\answers\finalize_review.py'
```

本轮不评价时间、token、费用、组别胜负或采用率。质量结果已封存，未新增测试。
