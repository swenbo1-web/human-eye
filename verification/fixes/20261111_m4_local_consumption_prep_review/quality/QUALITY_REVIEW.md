# 九格消费准备：评分与匿名打包复核

固定准备提交：`169b0be061e91b126f46313478690564ccb2bd60`。本分项发现 **1 个终止交接缺口**；其余目标检查通过。没有导入消费者、actor、产品或 Blender，没有发起真实模型调用，没有改实施文件。

## 需修正：首格失败且零消费者启动时不能生成九格交接

`quality_handoff/pack_quality.py:332–334` 要求至少一个执行记录存在 `consumer_pid>0`。但 `runtime/driver.py:181–249` 可以在首格输入检查、actor 启动或初始快照核对失败时保存真实终止记录：第一格已进入、`consumer=None`，后八格未运行。此时没有 PID 是真实状态。

我用纯合成的完整九格 PLAN/map、共同输入、已绑定的合成 GO/STARTED 和 terminal RUN_RESULT 验证，打包器抛出：

`AssertionError: at least one recorded consumer launcher is required; preparation is not a quality run`

因此 `INDEX.json` 不生成，不能按现合同交付首格 `failed_before_consumer` 加八格 `not_run`。**原 RUN_RESULT 没有被删除或伪造；问题是正式失败交接路径被拒绝。** 现有合成测试仅覆盖完成九格及含已启动消费者的五格前缀，未覆盖这一情况。

建议只补此出口：承认具有正式启动/终止来源的零消费者启动失败前缀，同时继续拒绝仅准备状态；保持真实 null/PID 缺失，不创建虚构消费者。增加一个首格启动前失败的合成案例即可，不需要真实模型或 Blender 验证。修正前，本分项不建议发正式 GO。

复现原件：`ZERO_LAUNCH_COMPLETE_REPRODUCTION.json`，SHA256 `1cd4a5026b9e8097be77d8691904f2f361a7198a519dc981a3d405650c83607c`；全部合成输入在本目录 `zero_launch_complete/e`。合成 GO 仅是测试数据，不是正式运行授权，真实消费者数为零。

## 已通过项目

- 从旧合同原件重新逐字段比较：仅原有 `cycle_id/scope/fixed_sample_policy` 三项样本元数据变化，新增 `sample_metadata`；其他 **17 个顶层字段、86 个叶值完全相等**。旧合同原始字节另存不变。两组六格／禁止第三组的旧冲突已消除，目标、三条件、角色、关系、局部证据、合法原生快捷解及完整正确标准未改变。
- 九格顺序为 `N,P0,P1 / P0,P1,N / P1,N,P0`，每组在三轮各占一次首/中/末位。实际匿名映射结构、唯一性与摘要绑定通过；未展示未来匿名 ID 对照。
- 仅从 driver AST 提取纯 `arm_runtime/go_contract` 与常量验证映射，未导入运行模块。N→内部 N＋P0 公共依赖；P0→内部 P＋P0 安装；P1→内部 P＋P1 安装，保留 external_group，原 slot 不被修改。packager 同时核 consumer 的 cell/task/round、内部 N/P 与外部 N/P0/P1，不能只凭相同内部 P 混用两个版本。
- `quality_handoff/SOURCE.diff` 未修改语义投影函数，仅调整批次、分母和消费者双分组核对。完整 result/error、arguments/code、原字符串与合法嵌套 `condition/profile/group/usage` 保留；仅删除明确传输信封位置的字段。没有递归按字段名删除事实。
- 在根独立输出目录重放作者合成打包测试 **231/231 通过**，外部进程/网络尝试均为零。实际核查九格、五格终止前缀、未运行尾格、失败和缺响应、重复调用、原 final 字节、未确认事件/CLI 文本、不同 final 绑定、False/null、私有原件归档及三组交叉绑定拒绝。它们不是正式答案或质量评分。
- 收益合同与根计划一致：先质量封存，再分别比较 P1/P0 和 P1/N；同质量 3/3，完整单格中位耗时严格下降且累计实际 input+output 不增加。缺 token/成本窗口标 unknown，不宣称对应净收益；不混历史六格、不以最快格或总耗时代替中位数，机制采纳单列。

## 实际执行与边界

独立脚本 `review_prep.py` 输出 `RESULTS.json`：19 项审查中18项通过，一项为上述零启动交接失败；其中另包含对既有231项合成测试的实际重放。完整复现随后补齐输入及绑定 GO/STARTED，仍是同一失败。没有重复安装、构建、真资产采集或任何消费者测试。本文不代替来源/wheel/实际入口及成本审查。

被审打包器 SHA256：`90f07a6b78457bb7ca9a5b93fbb7d78bf3439b547cfb21ff4fbae0b0c76ab0d4`。独立结果 SHA256：`9d234a9f0f850f62f2bba69b8c06e43a26a6c21a0e192b3a2f438e0f43d3421a`。
