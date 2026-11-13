# 连续消费正式批次合同审查

## 范围

本审查针对 `M4-SURFACE-SCAN-CONTINUOUS-CONSUMPTION-001` 的准备合同。固定总计划 SHA256 为 `95a334c39672a72ac771beba0f02e6c17735771a5e0f8411203d46e2769feba5`。审查期间只读取项目证据、固定 CLI 发布包和源码，新增内容限于本目录。

`ATTEMPT_01.json` 保留了准备中的首次检查。当时新 driver 尚未落盘，该项为 false。其余十六项准备检查通过。`ATTEMPT_02.json` 保留新 driver 出现后的二十四项检查结果。定稿检查及其源码 SHA256 记录在 `FINAL_CHECK.json`。正式运行的时界、进程归属、实际工具使用和模型答案仍须由本批原件证明。

## 已核对的固定条件

- `PLAN.json` 显式设置 `model_consumer_enabled=true`，序列固定为 N1、C1、C2、N2、N3、C3，每集三个固定槽位。授权沿用原 Pro endpoint 的既有 runtime 配置，当前准备流程无需增加授权交互。
- 七份输入副本的字节数及 SHA256 与工作单一致，原提示词为 405 字节。后两轮均为同一份 435 字节文本，准确增加“请重新检查当前场景。”前缀。
- N 与 C 的 `execute_blender_code` schema 复用原件。C 只增加固定的普通 `human_eye_scene_observe` schema。冻结的 REUSE 文件校验全部匹配。
- 既有 FIX1 consumer 通过显式 UUID resume，移除首轮 ephemeral 标志，每轮复用 work 目录，检查实际 `thread.started` 与预期 UUID。episode coordinator 检查 owner、native endpoint、product runtime 和配置 session 的身份连续性。
- owner 对整集累计工具尝试与响应字节设限，阈值分别为 32 和 1MiB。错误响应也计入实际发出的业务字节。native worker 的非 close 请求上限为 128，包含 QA 请求，单条代码上限为 256KiB。薄客户端结束后保留 owner，到集末只调用一次 finish。
- consumer 维护原始绝对 step deadline，限制进程、读取、cleanup、原件归档和 `CONSUMER.json` 写入关闭。收尾晚于 deadline 会保留答案并标为失败。coordinator 在失败后保留后续 not_run 槽位。
- 固定 runtime 设置沿用 Pro endpoint、`gpt-6.1-sol`、medium、default，关闭额外 hooks、apps、memory、skills、shell 和 web。N 仍可在 native 持久命名空间中保留自行编写的脚本及缓存。
- owner 在独立后台 native 会话加载固定资产，读回 SHA256 与几何，固定 EDIT 的 QA 只允许一次。集末校验预期终态、worker close、product runtime 退出、原文件和零新图片。共享 GUI 的前后状态独立观测保持未测，当前证据范围限于 owned 后台启动、来源和读回。

固定 QA snapshot 有一项已知 namespace 副作用。继承的 `verification/native_plugin_complex_003/actor.py` 中 `SNAPSHOT` 首句为 `import json as _j`，native worker 将该代码执行在本集同一持久 namespace 内。因此 INITIAL、PRE_EDIT、EDIT、FINAL snapshot 会将 `_j` 重新绑定为 json 模块。两组使用相同路径，当前冻结组件继续保留。如真实模型将 `_j` 用作其他缓存，原件分析须标注可能的管理代码 namespace 副作用，不能直接归因于模型丢失缓存。本审查只记录该范围，不新增 RPC 或 namespace 修改。

## CLI usage 语义

固定实际 CLI 为 0.152.1。读取的 executable 为 293056816 字节，SHA256 为 `01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6`。本机发布包只有可执行文件、资源和 package metadata，没有对应实现源码。冻结 help 证实显式 session UUID 的 resume 入口。

二进制含有 `total_token_usage`、`last_token_usage` 和 `turn.completed` 字段字符串，字符串出现无法建立调用关系，不能据此证明输出采用哪种 scope。因此准备阶段 usage scope 保持 unknown，`usage_aggregation` 保持 null。正式后只允许匹配本批白名单 UUID 的必要数值事件，若无法建立 `turn.completed.usage` 与 total/last 的确切绑定，token 总量继续未测。禁止从数值递增推断 scope。

本审查未读取其他聊天、凭据或推理正文。原 consumer 会保留 `turn.completed` 的原始 usage 与错误状态，既有 parser 的 missing_usage 失败条件继续有效。

## 新 outer driver 与质量包审查

已逐段读取新 `runtime/driver.py` 及 `quality_tools` 的 packager、checker、评分合同。

- outer 整集 clock 从输入检查、import、目录创建及 owner 启动之前开始，原期限为 590 秒。原期限传入 actor 和原 coordinator，后者将每 step 的 450 秒上限裁剪到它。outer 依次纳入 sole finish、关闭后来源与终态验证、完整 runtime ZIP 和 `OUTER_RESULT.json` 写入关闭。独立 timing receipt 的发布范围单列。原 coordinator 耗时继续保留自身范围。
- runtime 根目录为 `.m4cc1/<cell>`，每集目录要求首次创建。已按真实 stdio_attach 目录结构核算 REPEAT 的 `bridge_<32hex>/128/RX.bin` 完整路径长度为 159，小于 260。原件在关闭后存入正式目录 ZIP，短路径原件继续保留。
- C 配置为 `current-scene`，使用每集新 runtime 隔离，保留实际 accepted 参数及 `observed_product_session_ids`。driver 没有改写模型参数，也没有将配置 session 当作模型确实使用产品的证明。
- 每集固定 work、thread、native 命名空间和 C runtime，跨集重新创建。普通答案错误按固定顺序继续后续集。服务不可用、owner 关闭未确认、consumer 生命周期或动作状态不明停止剩余集。已发出的错误、最终答案和计数保留，不替补。
- source review 找到的两处 stop 缺口已由 driver 作者修复。已登记 turn 缺 consumer 返回 record 会按生命周期未确认停批，明确拒绝的 thin cleanup 也会停批。既有缺 EXIT 回执的 `confirmed=null` 范围单列保留。终端结构化 401、403、429、503 能进入服务不可用判断，已实际恢复完成的请求继续保留严格执行失败，不再据先前重试提示误判服务仍不可用。
- 质量包保留三轮顺序、最终答案、完整原业务证据、失败及未运行槽，公共材料按匿名 ID 排序。真值及快照只在质量侧交付。主项完整当前列表、上下文展开辅助项、本轮状态依据、执行状态分开记录。成本映射及 usage 封在私有侧。真实工具正文与错误可能透露路线，该匿名边界已在包中明示。
- 质量打包和 checker 绑定正式 PLAN、映射、RUN_RESULT、完整 outer archive、逐文件清单及原 final。缺失业务交付保持未知。代码及评分合同没有对模型答案进行内容打分。

driver 的异常恢复入口已补 `turn_index`。质量包补充了缺 `status_before`、outer archive、manifest 和 authoritative timing 的恢复场景，保留 partial final、原始错误及 owner 归属未知原件，checker 明确报告来源失败。双方作者完成离线反例，最终质量工具二十八项测试通过。本目录 checker 最后一次二十八项检查同样通过，其 `FINAL_CHECK.json` 所记 driver 和两份质量源码 SHA256 与作者最终交付一致。

## 暂定结论

固定输入、复用来源、既有 guard、新 outer 主链及异常交接的准备审查通过。root 统一冻结及复核后执行正式批次。本目录审查文件随准备版本冻结，后续 usage 数值证据另存 `review/actual_usage`。性能、质量、实际同 thread 消费和收益均未在本准备审查中判定。
