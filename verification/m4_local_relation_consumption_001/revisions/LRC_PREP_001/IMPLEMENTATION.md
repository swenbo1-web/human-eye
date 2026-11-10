# LRC-PREP-001：正式零启动失败前缀的交接修正

范围仅为匿名打包器的归档准入；本轮实现未执行模型、CLI、产品、Blender、安装或测试。原固定准备与根复现保存在 original_169b0be0/、repro_zero_launch.py 和 ZERO_LAUNCH_REPRO.json。

原正 PID 判定表达式完全保留。存在正整数 consumer_pid 的既有路径不新增 GO 或 STARTED 要求。仅当所有记录都没有正 PID 时，新 validate_zero_launch_failure 核对以下窄合同：

- 当前 cycle 的 GO：authorized 为 true、max_consumers 为 9，且 plan_sha256 等于已冻结 PLAN 的原字节 SHA。
- STARTED：同 PLAN SHA、max_consumers 为 9，started_ns 为正整数。不要求运行器未发出的 cycle、task 或 PID 字段。
- terminal RUN_RESULT：只有固定计划的第一格，started_cells=1、maximum_consumers=9、all_planned_dispatched=false、no_replacements=true，保留非空停止原因。原计划、匿名映射、唯一前缀核对继续执行。
- 时序均为正整数并满足 batch_started <= STARTED.started <= cell_started <= cell_ended <= batch_ended；batch/cell wall 等于各自起止差，within_570s 与实际 cell wall 自洽。不固定 stop 文案、不要求 finish 成功或存在来源目录。
- 两个真实失败出口：consumer=null 且外层 errors 含异常；或 consumer 为 failed、valid_completion=false、PID 缺失/null、thread_id/final 为 null，且 consumer.errors 含异常。后者允许外层 errors 为空。异常列表至少保留一条具有字符串 type/message 的原记录。

零 PID 路径将 GO.json 与 STARTED.json 原字节加入现有 control 字典，复用 private/control 原件复制、PROVENANCE.control_sha256 及结束前逐字节防变化检查。缺控制、错绑定、未终止、非失败、错误时界或单纯准备继续拒绝。不会添加 PID、模型答案、成功状态或替代消费者；完整九格交接保留第一格真实失败与八格 not_run。

所有原 payload/administrative projection、handoff_one、source_consistency、capture_cell 等函数的 AST 与 169b0be0 相同；答案、代码、嵌套 JSON 字符串、错误和重复请求的投影不变。控制 SHA 是现有文件来源绑定，不声称提供加密身份认证或模型已经启动的证明。

pack_quality.py SHA256：3b960695d5308ac64c5512191d7c0dc4e854a72b5fa07b97ccb5dfe0c0b3c365。

静态核对已完成 AST/不执行 compile、原函数相等、原正 PID 表达式相等及 git diff whitespace 检查。首个摘要脚本在任何写入之前因误用 ast.Assert.value 失败，修正为 test 后通过；该事实写入 SOURCE_REUSE_FIX.json。定向合成与旧合成回归由独立测试代理执行，其结果另存；本说明不预先声称其通过。PACK_FIX.diff 保存 169b0be0 到本候选的最小差异；quality_handoff/SOURCE.diff 保存旧 M4 baseline 到当前完整复用差异。当前 SOURCE_REUSE.json 已更新新 SHA，历史原件不改。
