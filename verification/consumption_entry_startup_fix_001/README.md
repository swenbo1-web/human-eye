# CONSUMPTION-ENTRY-STARTUP-FIX-001

本批离线启动修复完成，execution_ready=false。旧CONSUMPTION-RUN-001永久保持1error+7not_run，没有续跑、补答或新试验。0 exec消费者、模型评委、Blender、MCP服务、真实RPC、模型API；未读auth/key或全局私密日志，未复制登录存储、设置新CODEX_HOME或改全局权限。

## 已修缺陷与证据边界

根TRANSPORT_PAIR证明固定CLI中仅enabled=false却无command/url的MCP记录会invalid transport；补完整transport且disabled的对照可解析。原失败71B stderr已丢，不能据此恢复原消息、断言它是唯一根因或排除其他启动问题。

新PLAN只移除4条无来源禁用声明：blender、cua_repl、node_repl、agent_learning的mcp_servers.*.enabled。ignore-user-config不再因这些覆盖项创建无transport记录；真实native及P-only human_eye保留完整command/args/cwd/required/允许工具。exec的strict-config和ignore-user-config不移除，插件/注入策略、managed限制仍保留，意外注入/工具必须按实际观察报告。

safe_environment按键名新增排除CODEX_PERMISSION_PROFILE，排除值不读取，采用本批既有共同workspace-write/never。旧父会话/句柄和key排除逻辑保持，登录路径、客户端路由和其他无关env不变。consumer_pid在owned Popen返回后立即记录，早期退出也能保留PID。

普通stderr只保留少量完整匹配模板或规范化配置字段/flag/profile冲突类别；不接受任意Error尾部。单原行≤512字节，全部保留文本≤4096 UTF-8字节，全部原字节数、脱敏/不可用/截断计数保留。敏感key/token、system/developer/hidden reasoning/加密及未知内容不导出。公共事件白名单、终态/回收/未知停止和禁止重试行为不改。未安全保留的诊断明确unavailable，而非捏造原因。

## 当前验证

固定candidate/test字节直接compile的6项mock全部通过，0失败/错误/skip。覆盖env值不读取、PID/普通exit1/一次启动回收、常见配置错误、安全过滤、4096上限及N/P完整transport/strict flags。完整TESTS/STDOUT/STDERR.raw.txt、RESULTS和EXECUTED_BYTES.zip在check_01；没有重跑旧32或几何矩阵。

本批恰好2次固定CLI features list完整候选解析：N36项覆盖、P37项覆盖，native/PHE的完整transport只在解析调用中额外enabled=false，未启动后台。两次均exit0，stderr0B，owned PID9032/14364均已回收；wall分别47.256ms和58.5003ms。每次原stdout13203B，保留200行合法feature表，另1行未知stdout已脱敏且记录字节/SHA。exact argv、原runtime exec argv和必要诊断原件在config_parse_001；没有第三次尝试。

features子命令不支持exec的ignore-user-config/strict-config，因此解析命令继承用户/项目配置，并供给全部候选-c覆盖。它验证此环境下的配置bootstrap，不是实际exec有效性、完全注入隔离、Pro认证/模型可用性、MCP握手/送模schema或图片能力证明；没有因解析通过宣称全入口通过。原71B原因仍未恢复。

## 固定范围与下一步

runner仅增加re导入、上述env/PID/诊断处理；bridge和he_bootstrap与2195ac8原字节相同。模型/provider/effort/tier/登录、产品17db41c/131/01c296b5、四题/真值/资产、180秒、8动作仅观察、非盲数值合同全部保持。MINIMAL.diff仅在展示时把两侧CRLF归一为LF，真实字节及SHA保持，避免将换行显示成整文件修改。

旧材料按固定SHA引用，不复制历史。所有17组件解析路径/SHA通过，PLAN只变候选路径/摘要、当前任务元数据、false及删除4条覆盖。下一真实比较还须根另行冻结新批次/私有目录/精确approval和窗口；旧失败批次的目录与授权不可复用。实际exec/managed上下文/完整工具注册、模型和真实回收条件尚未验证。本任务不授权任何消费者，提交一次回报后结束。
