# M1 选区量测默认简报的入口说明

**文案候选通过隔离工程验收。** 实装 `tools/list` 的唯一变化是 `human_eye_scene_observe.description` 中的源选区说明。它明确默认简报包含距离、最近表面点、对应源面和 `region_ref`，并注明详细面映射与诊断使用显式 `response_detail=full`。说明从 3,254 B 增到 3,287 B。五个工具的输入 schema 及其余定义一致。 [实装目录](evidence) · [源码与构建身份](install/BUILD_INSTALL.json)

## 同一次真实无图量测的三种回包

原 `007de68c` P1 第 1 调指定 Obj_07 的求值三角 0–3 到 Obj_05 整件。历史内部 MCP、外层和 CLI `item_3` 的正文均为 39,717 B。父 `binding` 与 `task_result.binding` 实际逐字节相同，各 16,230 B。`region_ref` 原回包也有两份，每份 549 B。 [封存实证](checks/HISTORY_BOUNDARY.json)

| 请求 | 实装 A/B 正文 | 实际端点验证 |
| --- | ---: | --- |
| 显式 `full` | 39,717 B | A/B 线包相同，内容与历史真回包相同。 |
| 显式 `brief` | 7,042 B | A/B 线包相同。 |
| 省略 `response_detail` | 7,042 B | A/B 线包相同，正文与显式 `brief` 逐字节相同。 |

默认简报保留 7.318640584152224 m、世界点对 `(4.75, 4, 1)` 与 `(12, 4, 0)`、各点对应源三角 `[0]` 与 `[3]`、有效的顶层 `region_ref` 和 `image_not_requested` 状态。使用 33、34、35 B 工具头、12,000 B 结果阶段与 3,000 近似 token 历史阶段，默认、显式简报合计 **12/12** 保留完整正文。历史 `full` 原文的六次固定裁剪均落掉距离、点对和顶层 `region_ref`。实装重放的归档 producer 按存档顺序输出，完整内容等同且六次裁剪仍丢顶层引用。固定裁剪与原 CLI 全文分别记录，供应商内部实际上下文未测。 [实装测量与裁剪](checks/MEASUREMENT_ENTRY.json)

28 对象的 N15 历史边界另记。`PERF050-SOURCE-REGION-ACTIVE-VIEW-P2` 第 5 调的无图简报为 12,032 B，实际 CLI `item_7` 公开全文。固定预算六次均截断 `image_scope.objects[11]` 的对象名、实例和参与字段，距离、世界点对、源面及 `region_ref` 保留。本轮未改投影或预算。 [历史边界与两阶段原件](checks/HISTORY_BOUNDARY.json)

## 兼容、身份与封存

三种量测入口共 6 次实装请求。额外 **62/62** 实装 A/B 业务回包逐字节一致，含 52 个成功回包和 10 个预期错误。60 项覆盖原采样 PNG、原完整见证、无图、隐藏／零样本／未知、矩形回退、目标／全场／普通及错误。两条旧过期引用以实际安装的服务和封存 host 源复验，由原校验按相同原因拒绝，回包与各自历史原件同字节。原图块和关闭行为均保留。 [回归矩阵](checks/COMPATIBILITY.json)

方案 `2b995925703b27fa281d33aeb400252f5caeeb54`，基线 `8e3129c09e147bd996da2b6f45126be36ba5fcde`，候选 `1cb43fd35e680169c0a6275b52e47513de638624`。143 件工作源 `73e28f8e9b334a386c95b785aa3698e5171795fae9bffc9ea4e73403344f33b4`，wheel `e011c0b917cc64713004d63dccc6358cc14e68d552f20f8e9a32ffb81990a3e6`。仅一次隔离构建和安装，Git、wheel、安装逐件核验。新增模型、Blender、构图、替补、资产重建、Google、额外 API 和费用为零，默认配置未切换。旧排序、N15、M09 和 Far00 未重跑。模型是否选简报、减少调用或 token 均未测。 [原件索引](RAW_INDEX.json)
