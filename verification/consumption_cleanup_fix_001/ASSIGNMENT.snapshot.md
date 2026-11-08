# CLEANUP-RECEIPT-FIX-001 — 有界离线修复

根已核002的47Git/46seal/17组件/131产品和计数，旧结果保持。当前真实MCP工具审批未解决，不启动新模型、CLI、MCP服务、Blender、RPC或付费API，也不改审批配置/工具注释。W-ENTRY只做可独立的退出证据修复，基线63dd07f；在本人工作树verification/consumption_cleanup_fix_001新目录完成，旧证据不覆盖，产品不变。

已确认问题：registered_tree_cleanup先process_exited(pid)再硬读EXIT；缺EXIT会进入except并丢掉先前OS wait观察。区分process_stopped与graceful_exit_receipt，保留STARTED与本槽ledger绑定。native没有自建子进程，受控OS证据确定其停止时，不应单因可选EXIT文件缺失将其改成未知。拒绝访问、无法取得进程状态、缺STARTED或绑定不符仍不能标确认。不要捕获错误后默认True，也不把最终扫描改写旧收据。

HE必须单独覆盖自建子进程，不能只看到bridge停止就通过。用已有HE_CHILD_STARTED/HE_CHILD_EXIT和现有PID检查，缺少应有child身份或仍存活/未知均保守；不得另建全局守护器、重试管理层或任意进程扫描。保持未知动作不重试、原期限、预算及旧状态；cleanup可确认不等于答案正确或工具获准。

最多6个固定字节离线测试组：native已停止缺EXIT；有EXIT控制；native存活/访问拒绝/缺绑定；HE bridge停止但child存活/未知；HE已知child停止但正常回执缺失；无法确认分支仍阻止后续槽。可用模拟OS接口，禁止真实启动/终止进程。只改最少的既有函数，复用原结构；若静态核查否定方向，交证据停止，不引入框架。

本轮直接修复、定向验证、提交到本线并一次CLEANUP_RECEIPT_FIX_001_COMPLETE回报根。附源码diff/SHA、实际方法分母/失败、原件不变、已知限制。不能因回执缺失伪造exit0。不要读取评分truth或进行新消费；用户具体工具信任另由根处理。
