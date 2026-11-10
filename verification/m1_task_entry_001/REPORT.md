# M1-TASK-ENTRY-001 首版候选

本批完成最小公开任务入口及定向正确性回归，提交管理员独立复审。尚未安装、发布或启动新的模型对照；不宣称质量、耗时或成本收益。

## 候选与范围

- 父提交：`d341bb68a4747d1076d5e332789bee1d5f217cd7`；实际产品基线：`df016079b0265ee327f884c90dd4815c392016b6`。
- 原产品：137源，canonical `3fc2651e108ad7ac252394871d78e1abaee1200c92a018125984b2fc240193bd`。
- 候选：同137源，canonical `347ec4e52b24ff77239c5540caac52cdc6031e3542c0359798f821538ef4e3ea`。
- 产品仅改 `human_eye_plugin/live_spatial_mcp.py` 与 `human_eye_plugin/production_server.py`；其余135源、版本常量、M3内核、采集器及预算与实际产品基线逐字节相同。
- 原004/005证据没有修改。原生fallback、普通目录和旧大接口保持兼容；没有部署、配置修改、模型请求或付费API调用。

现有 `--spatial-task-only` 目录保留原 `human_eye_spatial_relations`，新增 `human_eye_surface_nearest`，只接收 `target:{name|id}`。完整例子为 `{"target":{"name":"Bracket"}}`。内部映射到原 `surface_nearest` 查询并固定无图，沿用当前server的默认session。简洁目录仅这两个任务，不重复暴露旧同义入口。

新入口直接保留原nearest完整事实，含complete/partial/unknown、best-known、unresolved、来源绑定及 `execution_authority=false`。它表示无符号表面距离，不表示穿透深度、最近分离件或移动量。原relations投影保持原合同。本批未做输出摘要压缩、隐藏动作会话或新增缓存。

## 验证与结果

### 定向离线回归

`offline_03/RESULTS.json`：**14/14通过，零跳过，零外部操作**。使用原verified loader及137源字节快照，实际身份为 `unregistered_runtime`；这是源码正确性测试，不是已安装版本验收。

覆盖：目录与dispatch隔离；原relations合同；最小name/id请求；004/005封存错参；额外字段、无效selector；缺失/歧义目标；complete/partial/unknown完整事实；默认session与trace；旧动作账本字节不变；source/host/epoch/revision/selection缓存边界；原期限和stdio错参恢复。使用现有真实采集/几何代码与有限RNA fixture，最终几何事实没有伪造。

早期记录保留：`offline_01` 在测试开始前由原guard拒绝（整个仓库被当作产品根，包含QA `__main__`）；随后使用精确物理源码快照，没有放宽guard。`offline_02` 为11通过、2失败、1错误，原因是新增测试误读已有trace字段、expired状态及目标缺失的unknown合同。只修正新测试预期，产品源码未变。`BASELINE_CONTRACTS.json` 绑定父提交原始Git blob及原合同片段，三个预期均可独立核对。

旧193项矩阵未重跑或改写；其历史191/193及已知合同过时断言继续保留，不能把本批定向通过称为全部历史审计全绿。历史补充检查也有未完成的fixture-origin审计，本批没有将其重新计作成功。

### 两个隔离Blender回归

`blender_equivalence_01/SUMMARY.json`：**两个旧场景均通过，唯一一次执行，无替换样本**。原003只读NativeSession启动各自资产副本；物理137源快照加原pyproject标记，guard核验加载字节，实际身份为 `source_checkout`。原570秒worker期限、30秒RPC期限和128请求上限保持不变。只比较同一service及默认session上的旧入口和简洁入口。

| 场景 | 独立真值核对 | 入口等价 |
|---|---|---|
| 003装配 | Object_02分离约10.000050毫米，Object_03穿透，Object_04分离约39.999961毫米；最近分离集合和穿透集合正确 | 简洁relations与原已接受relations投影逐字段一致 |
| D48非凸齿状资产 | 47候选全部取得有效距离，最近Peer_000，约3.000005905毫米；独立区间外扩误差约6.29e-17米 | nearest完整事实逐字段一致 |

装配两个非零间隙按原真值误差界外扩后，误差均小于1微米；D48使用原独立oracle及replay绑定，不以生产算法输出自定答案。完整初末网格、矩阵、面、单位与原作者快照相符。比较只忽略顶层请求trace_id；来源、实例、epoch、revision、selection、unknown及partial字段均保留。每场景两个采集来源绑定完全一致。

全部RPC及参数、原生执行脚本哈希、结果和发布期限收据保留。每场景四个只读执行脚本（初末快照及两次采集）；零产品setter、零保存、零新增图片，动作state文件前后相同。原资产及保护文件未变，两个拥有的worker均exit=0且已reap；额外进程核验见 `OWNED_WORKER_CLEANUP.json`。未操作用户GUI。

运行约31秒包含大量源码/二进制/证据校验，不是性能基准。不能把这个时长或几何回归通过称为模型收益。

## 可重放材料

- `run_offline.py`、`tests/test_task_entry.py`：定向离线测试；`offline_01/02/03`保存所有失败和最终记录。
- `run_blender_equivalence.py`：两个已有场景的源码快照回归；`blender_equivalence_01`保存来源清单、RPC、真值、初末状态、关闭及发布收据。
- `ARCHITECTURE_REVIEW.md`、`BASELINE_CONTRACTS.json`：架构只读复查与独立旧合同依据。
- `ARTIFACT_INDEX.json`：本批提交文件的逐字节摘要；不包含索引自身和封存文件。
- `CANDIDATE_SEAL.json`：候选源与以上索引绑定。候选提交SHA由外部Git提交及管理员回报绑定，避免自引用。

重复的 `offline_02/engine`、`offline_03/engine`、`blender_equivalence_01/runtime` 与两份 `native/input.blend` 留在本地，未重复提交Git；原资产已在父提交，源码可由候选Git及清单还原。未清除早期失败记录。新执行须使用新的输出目录，不能覆盖本批。

示例（使用现有Python，不创建环境）：

```text
python -I -B -X utf8 verification/m1_task_entry_001/run_offline.py offline_new
python -I -B -X utf8 verification/m1_task_entry_001/run_blender_equivalence.py --expected-source-sha256 347ec4e52b24ff77239c5540caac52cdc6031e3542c0359798f821538ef4e3ea --output blender_equivalence_new
```

以上未另起执行。

## 审核边界与下一步

本候选证明在已支持域中入口更少、参数更少且原事实与来源合同保持，不证明模型自然选择正确、真实消费、减少重复求解或整体收益。新目录依旧是opt-in，正式默认没有改动。其他agent适配、图像入口、未知目标的发现、任意复杂资产及旧AB001完整观察/严格引用任务均未验收。

旧AB001负收益继续有效：旧任务须从图和目录发现目标，模型设置及计量边界也不同，不能用指定对象的两个几何回归声称旧完整任务已解决。

本批到此交管理员深审；先完成一次有证据的针对性精简，再冻结候选与独立答案，才进入已授权但尚未启动的最多27个新Pro消费者。既定N/C/S同核、未见场景、自然选工具、全质量/成本统计及失败不替换规则保持。
