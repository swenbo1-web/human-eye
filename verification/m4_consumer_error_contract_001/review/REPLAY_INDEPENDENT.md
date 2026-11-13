# 离线错误合同重放的独立复核

已完成 3107 项只读原件与结果复核，996 份冻结文件保持一致。候选函数、原工具代码字符串与验收矩阵均未在本复核中执行。作者侧复核与管理员终审分别留存。

47 项结果与冻结 CASES 逐项一致，实际 archive/shared 首个拒绝原因和嵌套 matcher 原因均符合登记。每份案例的实际 JSON 快照只包含所登记的形态及单变量变化，archive 原件副本和 ZIP 成员逐字节核对。

6 个真实整槽正例包含15条真实CLI原行与对应owner交易，结果为13 success、2 tool_error。4个owner-style正例是明确派生形态，35个调用链负例与2个直接matcher负例分别列账。旧stdout偏移、原始行哈希、工具名、参数和业务正文全部核对。

两个业务错误正文分别保留 N1 的 SyntaxError 和 N3 的 ValueError。CLI status=failed、error=null及原有content保持，候选分类为tool_error。原样result完全相等但状态错误的成功/业务错误控制均被拒，保留cli_status_mismatch原因。

六槽原答案、usage对象和原执行状态保持原字节与含义，旧结果仍为4 completed、2 failed、0 not_run。N1的新绑定匹配只构成协议候选重放。N3的顶层重连错误继续使事件投影门为false，中断流usage覆盖仍为unknown。

唯一既有矩阵的记录耗时为 4.5351460 秒，截止最终RESULTS发布前。这属于本地协议重放成本。新增Pro、provider、CLI、actor服务、Blender和光栅均记录为0，实际连接指针断言全部通过。

本轮有限47项保留原范围，content-body bool/int单列派生反例未纳入。严格canonicalJSON与类型处理已作源码复核，当前结论限于上述原件及控制，不形成新的真实模型或三配对收益结论。
