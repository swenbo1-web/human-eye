# M1-TASK-ENTRY-001 一次校验去重候选

完成管理员深审后指定的唯一精简，提交独立复核。只减少普通观察适配层中确定的重复校验；没有测量或宣称模型耗时、质量、成本收益。

## 固定改动

- 基线提交：`b296bae6f6e9f5fddda19f0fd6dc9eadcabee1f3`，137源，canonical `347ec4e52b24ff77239c5540caac52cdc6031e3542c0359798f821538ef4e3ea`。
- 新候选：137源，canonical `0005ab437c8f330ed277bd49133348389fe7222bda3087f16450dce55ec9c05a`。
- 唯一产品文件：`human_eye_plugin/live_spatial_mcp.py`，SHA256 `babbb88e4ee044e753798c81f78866aaa193642d7408ac4cd7c6ea7216e65928`，+6/-5行。
- AST复核只有 `_validate_arguments` 变化；其他136源逐字节相同。`SOURCE_REVIEW.json` 保存完整前后清单及核对结果。

显式query仍在原位置首次校验并保存 `selected_query`；缺省query仍在include_image类型检查之后归一化。随后的mode、alignment和task限制复用局部结果。没有改原输入、S映射、返回合同、service独立校验、M3内核、预算、来源、缓存或动作语义，也没有新参数、哨兵、trusted标记或平台层。

## 实际验收

`offline_01/RESULTS.json`：原首版14项正确性回归 **14/14通过，无跳过、无外部操作**。原测试字节完全相同；新 `run_regression.py` 与旧runner仅有一处候选产品SHA常量差异，记录在 `REGRESSION_RUNNER_BINDING.json`。测试和原guard实际运行，身份为 `unregistered_runtime` 源码快照，不是安装验收。

`compare_02/RESULTS.json`：固定前后版本分别用137源快照和原guard在独立Python进程运行，**各30项检查通过**：24参数案例、5真实service代表、1独立service拒绝。29条配对结果以及独立service检查相等；两个子进程exit=0、guard校验通过，产品源未变，子进程内额外进程/网络/信号尝试为零。

| 参数路径 | 基线MCP局部校验次数 | 候选次数 |
|---|---:|---:|
| 显式overview / 普通nearest / task | 4 | 1 |
| 缺省query | 3 | 1 |
| surface_nearest（selector或旧focal形式） | 5 | 1 |
| 简洁relations / surface-nearest | 1 | 1 |

所有5个真实service代表均仍调用一次 `service.observe`、一次service层 `validate_query`。overview代表采用disabled service，采集为0；另外4个task/nearest代表均采集1次、零动作setter，实际内核得到独立解析的2米间隙。overview没有进行完整几何验收。直接绕过MCP传入坏query仍由service独立拒绝，校验1次且采集0次。

参数案例核对准确的异常类型、消息与先后，以及输入不变：显式坏query先于坏image，缺省query遇坏image不进入query校验，null保持原归一化；session错误、selector互斥、缺会话、额外字段、未知工具、alignment限制和非observe短路均保持。失败前的已发生校验次数也按固定合同核对，不把所有拒绝机械算作一次。

## 首次比较器失败与修正

`compare_01` 原记录及首跑脚本 `qa_history/compare_validation_01.py` 均保留；脚本SHA为 `4bbc2c5b27839ad1f454028091e31c78c43b9359be486bb5aaa3fa812dc34eae`。两版本各自30项检查全部通过，但跨进程比较器判定3条输出不同：disabled overview的随机request/trace关联ID，以及两个nearest夹具空namespace产生的随机文档epoch及其派生revision/fingerprint。不能将该首次聚合结果写成通过。

QA修正没有改产品、参数案例、预期异常、计数或几何答案。nearest夹具在真实采集前预置由固定case_id生成的合法32位hex epoch，并核验采集后未变；所有来源绑定字段仍完整比较。仅归一化明确的runtime source/build与trace/request关联ID，新增 `raw_output` 保留未改的实际MCP结果，记录每个被归一化ID与固定夹具值。没有删除document_epoch、scene_revision、scene_fingerprint、未知或部分结果以使测试通过。

修正后runner SHA：`4eae40867c41ab9ee87b7029c1a7d65f1f5e6ddab02ec0d69273ba0c670523d0`。只执行一次新的 `compare_02`；原 `compare_01` 没有覆盖。此为测试环境配对修正，不是替换模型样本或修改产品准入。

## 封存与边界

首版 `verification/m1_task_entry_001` 的225索引成员及index/seal共227份原件核对未变，004/005没有修改。新材料全部位于本目录；精确engine复制留本地而不重复提交Git，源码由对应Git提交及清单还原。`ARTIFACT_INDEX.json` 绑定提交证据字节，`CANDIDATE_SEAL.json` 绑定源摘要、索引和结论；提交SHA由外部Git和管理员回报关联，避免自引用。

本轮没有启动Blender、模型、安装或CLI验证，没有重跑193历史矩阵，没有修改正式配置、GUI、资产、竞争分支或Google/API状态。首版两场景Blender记录仍只属于 `b296bae6`，不冒称新候选实机验收。既有安装/CLI/完整overview、模型自然选工具与实际收益边界继续保留。

新执行必须使用新输出目录，例如：

```text
python -I -B -X utf8 verification/m1_task_entry_001_optimize/run_regression.py offline_new
python -I -B -X utf8 verification/m1_task_entry_001_optimize/compare_validation.py compare_new
```

到此结束唯一精简批次，交管理员复核后再固定对照：N普通原生，C为最终候选ordinary大入口控制，S为同一候选spatial-task-only。C/S共享源码、内核、预算、事实及本次微优化；C不是旧安装版。最多27个新Pro消费者尚未启动，须先冻结未见场景、独立答案和计量。旧AB001完整视觉发现/证据交付负收益未关闭，不由本轮局部校验减少推出收益结论。
