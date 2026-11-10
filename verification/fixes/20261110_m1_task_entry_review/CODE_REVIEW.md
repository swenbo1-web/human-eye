# M1-TASK-ENTRY-001 独立代码复核

结论：固定首版未发现阻断候选后续验收的实质代码缺陷。新增入口是既有 MCP 内的参数适配，没有增加求解/路由/重试层，没有绕过 service、真实采集、预算或发布检查。可以继续处理根已授权的下一阶段；本结论不代表模型收益、安装验收或全部历史测试通过。

## 固定范围与执行事实

- 候选 Git：`b296bae6f6e9f5fddda19f0fd6dc9eadcabee1f3`；父 `d341bb68a4747d1076d5e332789bee1d5f217cd7`；产品基线 `df016079b0265ee327f884c90dd4815c392016b6`。
- 审查工作树：`C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`。审查前后 HEAD 固定，工作树干净。未使用根 `D:/hefe` 的旧运行源码。
- 独立执行了 Git diff、源码与测试/验收文件读取及字节摘要；未导入/运行产品、测试、模型或 Blender，未修改产品或默认配置。唯一新增文件是本报告。
- 自身 AL 句柄 `eac86c7db1a945e7866e39e806737e4c` 已读 session_context：parent_read_only，旧 assignment 504、父当前任务 523。未借父句柄、未写父任务、未把旧 assignment 当新执行许可。
- `git diff df016079 b296bae6 -- human_eye_plugin` 只涉及下列两个文件。原内核、采集、查询语义、读缓存及预算模块没有产品 diff。

## 目录、映射与语义

1. `live_spatial_mcp.py:269–293` 保留原 relations，新增只收一个 target selector 的 surface-nearest。新工具不提供 mode、requested_facts、session、图像或候选列表选择；其描述明确 unsigned surface distance、完整/部分结果与全场覆盖。`production_server.py:102` 只更新已有 flag 的帮助文案，默认 opt-in 与 `--demo` 互斥逻辑未变（103–106、121–122）。
2. `live_spatial_mcp.py:799–810` 用简洁目录名字集合维持两种 profile 隔离，参数白名单 `336–359` 再拒绝未知名称/字段。S 只接受两项简洁任务；ordinary 拒绝隐藏的 S 名字；未知名不会落到 service.status 的末尾分支。`tools/list` 在 `883–884` 按同一 profile 返回对应目录的深拷贝。普通目录定义没有 diff。
3. `live_spatial_mcp.py:297–300、808–829` 只是把 target 编为既有 `surface_nearest/objects` query，固定 include_image=false，随后调用原 `service.observe` 一次。`spatial_relations` 标志只对原 relations 生效；nearest 不经过 relations 投影（848–850），沿旧 nearest 状态/isError 规则（830–832）及单次事实 JSON 编码（648–658）。没有自动 native fallback、答案补全、额外重试或第二套缓存。
4. `live_spatial_mcp.py:736–743、814` 沿用持久 server 原有默认 session；模型传入 session 等隐藏字段会被白名单拒绝。trace 登记 `mcp.observe`、无图及原 RPC ID（751–773），不新建默认全局 session。`live_service.py:1046–1060` 仍验证并分派到原只读路径；其 source/host/epoch/revision/selection ReadContext（341–355、1280–1376）及旧动作 session 语义未变。
5. 外层 `_call_tool` 的请求预算（776–783）、service 内原来源/采集/几何处理、编码与 `before_task_publication`（855–856）继续存在。新 nearest 名称没有改变 result_kind 或另调用私有内核绕过这些边界。`nearest_witness` 的歧义通过无需选择 requested_facts 消除，而没有把旧 strict-clearance witness 静默改成 surface_proximity。

## 验证证据的范围

作者 `offline_03/RESULTS.json` 报告 14/14，零跳过、外部操作；本复核阅读了对应测试实现，没有重跑。测试覆盖目录/dispatch、name/id 映射、004/005 旧错参保留、隐藏字段与非法 selector、complete/partial/unknown 全事实等价、缺失/歧义目标、动作日志不触碰、默认 session/trace、缓存代际、来源拒绝、原期限及 stdio 错参后恢复。

关键测试位置：`tests/test_task_entry.py:104–148` 目录/原 schema/单次 service 调用；`150–205` 封存错误与完整/部分/未知输出；`207–246` 目标与 relations 事实；`271–294` session/trace；`298–347` 缓存/来源；`349–388` 期限/恢复。目录测试比较 ordinary schema 与封存005目录，并验证返回目录修改不污染内部常量。测试通过不能证明模型自然选择成功，27 个消费者仍属于下一阶段。

早期 offline_01 引导失败和 offline_02 测试预期失败继续保留。历史193项没有由本复核重跑或变更结论。两个旧场景 Blender 回归是作者已有证据，本复核未重新执行或将它们计为独立运行成绩。

## 唯一建议：合并 ordinary 适配层重复 query 校验（可选微优化）

有代码证据的重复集中在 `live_spatial_mcp.py:_validate_arguments`：371、375、376、383、407 行。合法 ordinary surface_nearest 的适配层会调用 validate_query 五次；显式 task 一般四次。新 S relations/nearest 在 355/358 行校验后早返回，适配层本来就各一次。因此这不是新入口的正确性缺陷，也不是预期模型收益的主要来源。

最小做法是在同一次 `_validate_arguments` 中保存一次规范化 query，供 mode/alignment 判断复用。保留 `LiveSpatialService.observe:1046` 的独立边界校验；不加入 trusted/validated 标志、不把规范化结果绕过 service、不给新入口另建路由层。必须保持错误先后：显式 query 仍在 include_image 类型检查之前验证；缺省 query 则仍在该类型检查之后归一化。不要修改原输入字典或改变非 observe 名称的字段处理。

如果实施，只需定向等价检查 ordinary 的 overview/task/surface_nearest、缺省/显式 null query、非法 query 与非法 include_image 同时出现的原错误先后、旧显式 session 及目标互斥、额外字段与未知工具。复用已有 S 最小请求/完整结果/stdio 恢复测试，确认 host 调用和 service 调用不增加。可用一次受控计数记录证明重复归一化消除，无需新性能矩阵或重跑 Blender。不得承诺可观秒级收益；微优化未实施不构成本候选的发布阻断。

没有提出第二项架构/算法改动。尤其不需要预建工具注册器、通用 profile 路由器、第二层 schema 系统或人为改动满足“一次优化”。

## 文件摘要

- `human_eye_plugin/live_spatial_mcp.py`：`3748b57d63f8a1ebe901b3e2cb555b658ad7673ad7318431155af6a29d9e73d9`
- `human_eye_plugin/production_server.py`：`57afb43c9d081da23807fa79ecb32e89b79dd619270d9bebe03facfc8e2fc609`
- `verification/m1_task_entry_001/tests/test_task_entry.py`：`bff257e4e1f762a830b8350a8f067fa265348e1ea54d8282e8ffa41096bcff65`
- `verification/m1_task_entry_001/offline_03/RESULTS.json`：`e56d6533cf7e6f9e672463a989cabe19c2f6a5a14d80c409e51480a900f37995`

## 根后续方案的口径补充

根另行回报在固定隔离副本重跑 14/14 通过；这是根的独立执行结果，不是本子审查者执行。

若采纳唯一微优化，最小局部写法是保留现有校验位置：

```python
if "query" in arguments:
    selected_query = validate_query(arguments["query"])
if name == "human_eye_scene_observe":
    # 原 include_image 类型检查仍在这里。
    if "query" not in arguments:
        selected_query = validate_query(None)
    # 原 mode / alignment / task 判断复用 selected_query。
```

后面的 task 判断仍用原 `name == ... and ...` 短路边界，局部变量只在 observe 路径被读取。无哨兵、无新路由器、无新返回合同，仍把原始 query 交给 service 独立校验。显式坏 query 保持先于 include_image 错误，缺省 query 保持后于 include_image 类型检查。

该修改比复用一次小型 mapping 字典更有依据：普通 nearest 是5次归一化降至1次、task通常4次降至1次；S原本1次。mapping 的重复只构造小字典，若跨 `_validate_arguments` 复用还要改变其原 None 返回合同，改面和复核成本高于已知收益。因此不建议同时改 mapping；本轮收益口径仍是维护和微小计算开销，不是模型耗时改善。

后续对照必须让 C/S 由同一最终候选源字节分别启动 ordinary/S profile：C明确命名为“大入口控制”，不是旧安装版。共有的 query 去重、内核、预算及 source 都相同，才把消费差异归因于目录与参数呈现。已安装 df016079/3fc137 与004/005的历史标签仍独立保留，不能把这轮 C 重新描述为005原安装 C。
