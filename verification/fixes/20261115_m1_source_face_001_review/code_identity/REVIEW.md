# M1-SOURCE-FACE-BINDING-001 源码及身份独立复核

结论：本范围未发现候选产品缺陷或来源不一致。最小源码改动、正式 A/B 接线和封存身份支持本批工程验收；不据此宣称总体任务收益达标。完整消费质量及成本由父复核另行合并。

本轮实际执行仅标准库离线读文件、Git 读取、AST 解析、ZIP 成员比较和哈希核对。新增产品调用、模型、Blender、raster 均为 0；没有导入或执行产品源文件，没有重跑作者验收。输出仅写入本目录。

## 固定身份

- 作者 HEAD：`8f2a739e789b777358d84a168154bc7c50b929e5`，分支 `codex/m1-source-face-binding-001`，本轮读取时工作树干净。
- 差异基线：`1f3db153d4a46363ed3e64103d495bbc5ee65864`。
- B 安装：`D:/he_source_face_001/product`，141 源总摘要 `3748d88b618db7de1347d632f2a68f3ed82a2ebb8a6321586fe756be07ea8148`。
- A 安装：`D:/he_view_reuse_001/product`，来源 Git `d12c7ab248452ff253452007d0635f2d662f0191`，141 源总摘要 `d8ad7003397d0c0611f54d128c0d0ad3433865b8d9f69b8b0519123752fe9f02`。
- B wheel SHA-256：`257f8e298853c1f1437ef5bf8f6791f2a2eff6c509678ded7308b07abb71391f`。
- 产品文件 `human_eye_plugin/live_spatial_mcp.py` SHA-256：`2be839c39ffcc5bde5fa92d7b028f8f9e5e8ab34d65aed90a51037f1a74503f5`。

## 本轮独立执行所得

有效结果为 `RESULT_R1.json`：11,628 条离线断言无失败，4,615 个唯一文件去重哈希。断言数是身份、文件和结构核查数，不是产品测试数量。

1. 1,117 条实际 Git 差异与清单完全一致，1,116 个清单内容以及全部 1,117 Git blob 与磁盘一致。产品仅上述文件 19 增 6 删，其余新增均在本批 namespace。
2. 2,708 条 FROZEN、126 条 QUALIFICATION_SEAL、4,526 条 QUALITY_SEAL、9 个旧保护清单、970 条运行原文件与归档、20 条 FINAL_AUDIT 引用均核对通过。
3. A、B 各 141 源与各自固定 Git 及安装一致；B 141 源也与当前作者树、wheel 成员一致。wheel 的 148 成员计数和 147 条非空 RECORD 校验项通过。
4. AST 比较仅两个函数发生变化：`_project_active_patch_support`、`project_active_observation_brief`。完整响应、图像内容交付、渲染、几何、预算、持久状态等函数未变。
5. B1、B2、B3 的实际公共简报为 v5；各 61 行，共 183 个区域，将闭区间独立展开后，与各自保存的 full 源面 mapping 逐项相等，每槽映射 122 个源三角形。A 三槽仍为 v4。
6. 固定六槽 A1/B1/B2/A2/A3/B3，六个不同 fresh thread，所有实际 prompt SHA 相同；五工具 schema 相同，调用权限均已批准，首调均为 active_observation。配置只改变相应槽的 MCP 接线，模型 `gpt-6.1-sol`、medium、default 相同，hooks/memories/apps/multi_agent/goals/skills 均关闭。
7. 每槽共同原期限为启动后 450 秒，consumer 与 worker 沿用同一绝对期限；上限分别为 12 工具、6 raster、正式 36 raster、全批 48 raster。现场仅一项 Q01、六个正式槽；保存的接线代码仅按固定顺序运行，无自动补样循环。
8. 六槽 `METRICS.common.audit` 的禁止旧证据读取、旧路径写入和禁止产品调用均为空/0。所有 consumer/owner 清理和进程回收记录通过。thin held-process 的真实退出码 1 与缺失 self-EXIT 回执 unknown 均保留，不能改述为 thin 正常退出。
9. freeze 在 qualification seal 之前，qualification seal 在正式 batch 之前。旧保护摘要一致。

补充结果 `SUPPLEMENT_R1.json`：63 条核对无失败。Q01 A/B 的 SCENE、LEFT、BACK 三视图 PNG 字节相同，39 个对应 NPZ 内 NPY 成员字节相同，full patch source map 相同；这是保存数据的比较，不是新渲染。资格次数字段确为 Q01，历史尝试列表为空、外层重试 0、6 raster、0 model。

## 源码判断

新增区间取自已有且通过完整分区验证的 `triangle_indices`，使用对象内、零起点、闭区间语义，不按 ROI 排序推导面号。排序加相邻归并保留稀疏编号。已有对象身份、region 对齐、整数且非 bool、面范围、重复和重叠、supported/unsupported 完整分区验证仍在，投影返回前完成；异常仍回落原路径。

只有真实 patch_support 源 mapping 存在时增加 v5 与语义字段；没有 mapping 的旧响应继续原 schema 路径。完整 `full` 和内容交付函数未改。私有 helper 仅一个内部调用者，返回 tuple 的变更同步更新了该处。当前产品中未发现另一个硬编码 v4 消费者。

追加优化是实质但有限的：候选 01 另走一次 mapping 生成范围；候选 02 在已有验证循环顺便生成，减少一次完整遍历并合并 region 行追加。它没有去掉逐区域排序，作者记录的排序总调用仍为 63 次；不能把这一优化表述为已经测得显著耗时下降。它没有新增缓存、几何准备或新求解器。

## 作者记录与本轮执行分开

作者定向记录最终 04 为 1,284 断言、16 案例；保存 01/03 runner 失败和 02 中间通过结果。本轮阅读夹具/断言逻辑与输出，没有重跑。覆盖包含自建四三角形矩形、稀疏 source IDs、对象/面/region 重排、缺 mapping、错误对象/ROI、bool/负数/越界/重复/重叠、分区错误和 legacy v1/v3/v4/full/image 内容。其范围是此简报投影和现有映射合同，不应扩写成任意来源、任意网格或新空间求解能力。

作者两个候选和一轮追加优化记录均核对；主审脚本用保存的 formal full mapping 作为 exact-source 比较来源，独立验证的是“公共交付绑定有没有丢失或错绑”，不等同于重新证明底层几何来源构建算法。

AL 状态必须准确：父复核 task `95de6bf0-582e-412b-888b-c8e5ac70796b` 已登记，本子任务 own context 为 `d92066a03b624a7a832bc2e4e11670e6`、parent_read_only；作者本批仍为 `pending_current_chat_host_binding`，completion context 未绑定。父复核登记不追认作者已登记。

## 复核脚本更正及保留项

- `review_R0.py` / `RESULT.json` 原先六条 isolation 断言读错 METRICS 键并带 True 默认值，不构成证据。本轮主动识别后改为直接读取 `common.audit` 全部实际字段；`review.py` / `RESULT_R1.json` 重新执行同批离线核对，六槽通过。其余原结果保留。
- `supplement_R0.py` / `SUPPLEMENT.json` 把资格编号/历史列表误当整数，导致一条检查失败。查明实际字段是 `"Q01"` 和 `[]`，修正为精确类型/值，`supplement.py` / `SUPPLEMENT_R1.json` 全过。该失败属于本轮核查脚本 schema 假设错误，并非产品或作者失败。
- provider resolved effort、未暴露的费用不能由本轮推导；只核对实际请求参数。thin self-EXIT unknown 继续保留。
- 不触碰 M6、竞争分支、原资产或正式运行配置；无 Git 修改/提交。
