# M1-NEAREST-EVIDENCE-001 独立代码复核

结论：在本次三个产品文件的改动范围内，未发现阻断缺陷。可以进入下一项完整任务消费验证；本结论不代表已经测得模型调用次数或端到端收益。

固定候选：`107641ec19919d56aa843c1949261590fc338148`；对比基线：`fa23496e`。实施目录：`C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`。新增产品差异仅 `task_query.py`、`live_service.py`、`live_spatial_mcp.py`，17 行新增、2 行删除。复核者没有修改实施树，没有启动产品、Blender、模型或安装流程。

## 独立代码判断

1. **证据来自原测量，没有第二次采集或求解。** `task_query.py:461–492` 先完成原有 ordered focal/candidate 测量和精确排序，再对 `measurements[oid]` 的见证与方向字段作投影。新增段没有新调用求解器、采集器或实体分类器。距离、排序键和证据共用同一条测量记录。原 `binding` 字段继续由这次有效 capture、场景指纹、目录与运行源身份产生。

2. **完整覆盖与局部最佳保持区别。** `task_query.py:475–507` 的 `complete = bool(best) and not unresolved` 未变。partial 下新增 `best_known_evidence` 仅对应 best-known，`nearest_ids` / `distance_m` 仍为 null，未将局部最佳提升为全局最近。unknown 无 best 时证据为空，公共 method 为 null。

3. **并列、零距和未知按原内核语义交付。** `surface_proximity.py:482–510` 依赖精确平方距离键分组，不按发布浮点值判定并列。新增循环遍历整个最佳组，为每个对象保留自己的有向点对。内核 `surface_proximity.py:543–604` 独立生成 witness/direction 状态：零距方向 `not_applicable`；世界坐标不能可靠发布时点为空且 witness unknown，但方向仍可能 measured。新代码未重算方向、未从 null 点推断方向，也未将距离 complete 误写为见证 measured。

4. **共享 method 当前确实成立。** 本入口所有候选经 `_surface_pair_measurement` 调用同一 `measure_surface_proximity`，其所有返回从同一 `METHOD = exact_binary64_triangle_surface_hulls_v3` 初始化；这里没有混用另一种距离算法或 prepared/boundary 快路。因此从第一个 best 读取共同 method 在固定候选上正确。没有 best 时返回 null，未虚构已完成测量。顶层 `unit=m` 加新增 `coordinate_frame=world`、`pair_order=focal_to_candidate` 明确点对和方向含义。

5. **缓存及名称映射隔离成立。** `scene_cache.py:408–446` 以 ordered pair、参数和算法版本作 key，缓存为序列化字节，命中和未命中均 decode 成独立对象。`read_context.py:69–80` 在保存内部结果后向调用者返回 deepcopy。故新增列表虽引用 query-local measurement 内的坐标列表，不会泄漏到 pair cache；`live_service.py:1324–1337` 的名称映射及调用方修改也不会修改 ReadContext 保存的内部对象。名称从本次 capture 按 object_id 映射，没有按名称重新选择对象或改变方向顺序。

6. **对外说明与行为一致。** `live_spatial_mcp.py:281–286` 只增加已有证据的说明，保留 unsigned、complete/partial 和只读语义，没有新增工具、参数或写能力。

## 本轮实际核查与作者运行记录分开

本轮独立阅读上述代码及依赖；将六个相关源码文件的本地字节与候选 Git blob 逐一比较，全部一致。使用独立标准库 JSON 解析脚本核对保存原件，未执行作者比较器或产品测试：

- `baseline_02/EVIDENCE.json` 与 `candidate_02/EVIDENCE.json` 中 18 条新增定向记录：14 complete、2 partial、2 unknown。
- 仅删除两个新增顶层字段和请求 trace，且分别严格验证两版 runtime source SHA 后替换该版本字段；其余完整 body，包括所有旧状态、覆盖与绑定字段，相等 18/18。
- 所有 18 条保存的测量、采集绑定及工作计数跨版本相等。新增每个 candidate 的坐标、方向、状态、原因与保存的原测量字段逐项一致；两条 warm 记录对照同一冷态原测量。
- 精确正距并列、零距并列、发布值相同但不是精确并列、partial、全 unknown、大坐标 witness unknown/方向 measured、反向 focal、两条 warm 返回修改隔离原件均保持预期语义。
- 保存的累计工作计数每版相同：capture 18、pair 24、kernel 24、rank 16、底层 nearest 20、closed_solid 0。这是原件计数重算，不是本轮重跑。

独立重算明细及输入 SHA：`CODE_REVIEW_CHECKS.json`，SHA-256 `6640debf2e5eea486cef693dc35cfb74b10b0395b0df689e8d09c9a9f09c7363`。原件位于实施目录 `verification/m1_nearest_evidence_001/`。

作者报告的两版各 49/49 离线结果，本轮只读取而未重跑。baseline_01/candidate_01 的同一旧断言失败、compare_01 的重复归一化失败应继续保留；这些不是本次代码复核自行抹除或重判的历史结果。

## 有限通过范围与下一步

本次没有发现需要额外产品补丁的实质缺陷，也没有理由为此次字段投影增加采集、校验层或新求解。已知边界仍是原先的三角表面距离合同，完整距离结果不等于闭体关系或穿透深度；未覆盖的组合不自动构成本次阻断。

本批证据是 guarded-source、fake RNA、真实内核的离线记录，并非安装/真实 Blender/模型消费验收。输出字节增加是否换来少一次后续取证，应在下一项完整任务中测量；不能据本次计数不变就宣称总 token、费用或时间已下降。停止局部字段优化，转向这项有明确终点的消费验证即可。
