# M2-DIRECTORY-RESOURCE-REUSE-001 独立轨迹复核

结论：支持在本次有界旧档范围内返回 **not_actionable**。三项 M2 资源后目录都已缓存；M4 保留一项真实宿主技术机会，但它是预登记兼容回归，未建立自然任务的目录需求或完整净收益。这个结论足以结束本批候选资格，不表示不存在其他自然使用需求。

审查目标为作者提交 `fde0e9ab` 的轨迹材料。本轮标准库脚本读取 190 个相关文件，其中 187 个逐项与作者已固定来源 SHA 对照；另 3 个是读取后独立记录 SHA 的复核索引。没有重做旧档全部 4702/1622 文件的哈希扫描，没有导入作者分析脚本或产品。0 新产品、实验模型、Blender、raster 调用。

## 实际原件核查

| 项目 | 独立核查结果 |
|---|---|
| M2 entry_01、entry_02 | 原始 RESULTS 与独立 REQUEST/RESPONSE 对应。前五步为冷目录、暖目录、selected task、full overview、目录；末次 `cache_hit=true`，与前目录的 capture state 相同。 |
| M2 typed_01 | 原始 REQUESTS 顺序为冷目录、热目录、task、目录、full、shutdown。task 后目录为 hit，保存文件与 hot 文件逐字节相同。 |
| 26 次变更后目录 | 两个实际正确性脚本各有 13 个显式修改步骤，随后读取目录。当前回包与 ORACLE 没有旧资源 stamp/pose 快照；不能仅以同宿主或同文档认定资源可复用。继续标 unknown。 |
| M4 唯一技术例 | 实际 rpc_05 到 rpc_08 为 nonplanar_source、bad_active_query、ping、old_readonly_regression。capture 与目录同 instance/epoch/revision/document，目录为 miss，原 nonplanar 状态仍为 unknown。qa_005/006 原始代码使用同 resident module/tag/host 引用。 |
| M4 请求目的 | HARNESS_PROTOCOL 预登记兼容回归；实际运行器第 222 行发出目录，第 225 行只断言成功与纯文本。后续没有读取该目录结果的业务代码，实际 stdio 序列也以该调用结束。 |
| M4 资源数量说明 | 实际 qa_005 resource 为 4 个 vertices_local、2 个 faces；29 是该资源 revision，不能写成 29 个驻留资源。私有 stamp 和目录入口内部 mesh 身份没有直接侧录，本轮不补成已测事实。 |
| 14 文件 JSONL 补充 | 独立确认恰为原 M4 inventory 的 14 个整文件 JSON 解码失败路径；逐非空行解析得到 79 条消息、37 条 tools/call，0 解码错误、0 显式 directory 查询、0 capture_directory 字符串命中。原文件 SHA 与逐消息 ID 顺序一致。 |

脚本 `review_r2.py` 的 **337/337** 核对项通过，原始结果为 `RESULT_R2.json`。它独立读取原始请求、回包、任务结果和兼容回归源代码，而非执行作者 scorer。

## 分母及结论边界

从实际 M2 RESULTS/REQUESTS 重新计数：39 个测量会话记录（含预检）加 2 个 MCP 正确性和 1 个 typed，共 42；368 次业务读取另加 1 次 typed shutdown。产品目录 139 次，98 hit、41 miss。321 条测量业务记录包含于 368，不能重复相加。三个候选与 26 次变更读取也属于上述记录，不是新增会话。

M4 的 47 个 namespace、1201 literal TX 和 300 映射 TX 是作者盘点范围和文件单位，有副本重叠；不能充当独立任务或资产数量。14 文件补充没有创造 14 个新宿主，其 79 消息也含初始化、通知和工具列表。作者的 26 个有限工程宿主/重复资产范围继续保留，本轮没有重新逐宿主验证这 26 条全部历史。

本轮直接核查了决定出口的全部三项 M2 候选、26 个变更读取、M4 唯一技术例及 JSONL 缺口。自然任务命中为“所查范围没有已建立的合格命中”；覆盖范围外的需求频率继续 unknown。私有资源兼容性、可删除时延、完整任务收益和产品新版本表现均未补测。没有把技术机会改写成自然收益，也没有以工程测试的身份否认调用确实发生。

## 方法修订与任务归属

首次探索辅助命令将测量 `rows` 误称 `records`，只读时触发 KeyError。正式独立脚本首版将资源 `faces` 误写为 `triangles`，报错及脚本保留在 `review.py`、`attempt01_stdout.txt`。

R1 正确读取资源字段后发现会话计数 41/44，而原始 RESULTS 中有两个仅含 `cases` 的汇总文件。R2 显式识别 `analysis_preflight_01/RESULTS.json` 与 `run_01/RESULTS.json` 为汇总、不是宿主，得到 39/42。R1 两个失败断言及全部结果保留在 `RESULT_R1.json`、`r1_stdout.txt`；没有改旧原件或删除首次失败。这些是独立检查器假设错误，不是产品失败。

当前自身 AL 句柄 `5b6db88db9e241e18c182d58b5074d3d` 的 assignment `abcff986-3a32-4470-835c-7e2ae81f715c` 仍归旧任务 `95de6bf0`，`current=false`。本批由父任务 `f2ac3511-ed05-469e-9a8b-710340bd4bed` 明确重新委派，并明确允许继续标准库离线核对及写本目录；没有冒用其他句柄、修改父任务或声称 AL 已续绑。实际工具未返回执行保护拒绝。
