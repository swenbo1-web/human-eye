# M3-SUFFICIENT-SEPARATION-001 integration review

结论：本轮没有发现阻断交付的接线缺陷。新 `spatial_relation` 的证明范围、旧 `closed_solid_relation`、集合完整性与 memo 版本保持分离；建议停止继续打磨同一 G508 算法，转入固定版本的模型消费资格验收。当前不能声称模型已经发现或正确使用新事实，也不能把内核计时收益换算成模型端收益。

## 固定来源与本轮实际执行

- evidence `189ecdb84185d96c3ed0d75ca268bc16d6d4999b`；product `e836e03f4b3821f869c72ac3e50df5204f28b50f`；137 源摘要 `2c453e56f3abf83a49f9c8ef37a3a77728dd8f05168db4fd5217d3bad465c390`。
- 审阅根计划、作者 REPORT、四个产品修改文件和现有 `scene_cache`。独立脚本先核对工作树 137 源字节与固定 product Git，再用经核验的 `verified_source_loader` 从同一字节快照执行，实际加载 51 个引擎模块；使用已有依赖 Python，不安装依赖。
- `review_integration.py` 的 **7 个独立检查组全部通过**，完整输入构造、断言、输出与工作计数见脚本和 `RESULTS.json`。未调用 Blender、消费者或 API；未修改产品、安装或资产。
- 作者报告的 230 项回归、60 次计时、实际 MCP/Blender 结果仅作为阅读证据，不计作我运行的检查。没有运行完整 JSON Schema 引擎、真实期限时钟或外部编辑/断连试验；本轮使用检查点异常验证取消传播，未声称宿主重连已复验。
- AL 自有句柄已核对，返回 `parent_read_only` / `assignment.current=false`；未借父句柄、未写父 task。

## 接线审查与独立结果

1. **显式版本与证明范围。** `task_query.py:59–91` 允许 target/candidates 的 `surface_proximity + spatial_relation`、旧 closed 组合及 mixed；`task_query.py:505–523` 只有显式新事实升为 `task-query-set-v2` 并带 `relation_fact`。单对旧 v3 envelope 不改变。`surface_proximity.py:841–890` 成功支持证书的 scope 是引用三角形并集及其引用顶点凸包；fallback 原样发布真正执行的 closed method/scope/certificate。我的两个相距 1 m 的开三角形通过新事实；mixed 的 closed 返回 `closed_solid_too_few_faces`，整体 `partial`，没有推断闭壳健康。

2. **集合不会隐去未知。** `task_query.py:422–523` 以显式 `relation_fact` 汇总，未解析候选、自配对、重复候选都进入 unknown；只有全关系已知且所有分离对象距离可排序才宣称 nearest complete。独立加入一个缺失候选后，已有 1 m 结果仍是 best-known，`nearest_separated_ids/distance_m=null`、complete=false。mixed 中新关系已全知但 closed 未知时，nearest 可以 complete，顶层仍 partial；这是明示空间关系下的距离完整性，不是全部事实完整或资产健康。这一层级区别需要下一轮消费者实测。

3. **缓存与来源。** `task_query.py:327–348` 独立使用 `task-spatial-relation-strict-support-v1`，key 包含 source、世界米制及 exact-rank 保留选项。`scene_cache.py:408–446` 只有 bundle.measurement_valid=true 入 memo，返回 JSON 脱离副本。独立验证了 mixed warm 新 bundle 命中时 closed unknown 仍重算、旧 v1 在新 memo 后仍独立执行、source 改变和同名几何改变都重新求值且距离更新。`scene_cache.py:177–180` 已有 resident 快径仍依赖私有 owner 绑定的 read-resource-version；本轮没有扩成跨捕获的 prepared tree 缓存，也未改变该不变性合同。

4. **prepared pair/tree 的复用边界。** `surface_proximity.py:210–264` 保留完整引用坐标，未只保留降维三角形极点；`surface_proximity.py:719–755` 每次 holder 清理并重新绑定。`surface_geometry.py:729–773` 新增 tree 复用要求 exact pair 对象与两个 prepared triangle arrays 的身份均相同。独立使用两个各 36 面的细分包含盒体，确认复用 tree 与全新准备产生相同 penetrating 结果，且计数真实记录 pair/tree reuse；将旧 pair/tree 传给数值相同但重新规范化的另一对象对，两个复用位都为 false，结果不变。mixed 包含场景只调用一次旧 closed，surface gap 为 not_applicable。

5. **取消与有限工作。** 新支持求值使用已有 surface Work；资源停止标志由 bundle 传至 mixed，不为显式 closed 再开一套预算（源码核查，作者有相应断言）。独立在 cold `spatial_relation_complete` 抛取消异常，异常透传且次次正常调用仍计算一次，证明未缓存未完成 bundle；在 warm `after_spatial_pair_measurement` 抛取消，缓存命中也未绕过请求检查点。未将检查点模拟冒充真实时钟/宿主取消实验。

6. **MCP 入参保持显式。** `live_spatial_mcp.py:75–114` 的声明与受理分支允许新/旧/mixed；独立实际 `_validate_arguments` + `validate_query` 接受四个合法组合，拒绝缺 surface、缺 relation、重复 fact 三个非法组合。task 请求仍需 `include_image=false`。本轮未声称覆盖任意 JSON Schema 输入。

## 下一项的实际接点

唯一建议是**固定现产品，做模型消费资格验收**：先看自然业务问法下模型是否从真实工具声明找到所需空间事实，并用输出正确作出结论；成功后才评估端到端相对原生的成本。不要再把同一 G508 改轴/阈值/树或追加封闭合法性证明作为下一优化。

可见的接口限制是：`live_spatial_mcp.py:293–326` 的 compact `human_eye_spatial_relations` **仍硬编码旧 closed+surface**，无 requested_facts 参数；`_project_spatial_relations` 仅投影旧 v1。它不可能让模型调用到本次支持证书。当前可用新事实的真实入口是 generic `human_eye_scene_observe`，模型须选 `include_image=false` 和显式 `spatial_relation + surface_proximity`；工具主例仍展示旧 closed+surface（158 行），159 行才描述 opt-in。这个现状是刻意兼容，不是本批实现偏差，但消费试验必须记录真实工具集和实际请求，不能把旧 compact 路径测成新版能力。

最薄消费检查应直接记录：是否发现并选择新事实、是否把 mixed partial 的闭壳未知正确解释、是否把未解析候选留为未完成、是否将包含/穿入时 unsigned surface distance 错称间隙、是否需要再读原生数据，以及完整调用轮次/数据/token/耗时。可用原固定业务任务加简单及未知控制，不把已知答案写进提示，也不将支持证书当闭壳健康证明。必要时依据真实选择失败再修一个接口接点；目前只凭源码不能决定模型必然不理解，更没有证据再引入一个新的工具或协议层。

## 运行记录

脚本首次运行在执行任何产品模块前，因审查脚本把 manifest 列表本身当成总体 source digest 而失败；已按 `runtime_identity` 的版本元数据+files 结构修正。第二次已通过前六组，最后一组因审查脚本遗漏 task 必需 `include_image=false` 被产品正确拒绝；修正测试调用后完整 7 组通过。两个错误均为审查 harness，原始错误摘要保留在 `RUN_HISTORY.md`，未修改产品或测试预期以回避失败。
