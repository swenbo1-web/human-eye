# 工具错误合同的静态复核

当前接线、冻结案例和原始资料的静态核对具备进入根冻结离线矩阵的条件。候选函数与矩阵尚未执行。该复核由 matcher 实现代理检查其他代理编写的接线和案例，管理员终审独立进行。

## 结果绑定和实际接线

统一 matcher 先核 owner 正常 JSON-RPC 结果、合法 ID 形状和真实 bool，再核 CLI 工具状态及显式 null error，最后检查两种已观测结果包络与完整 canonical JSON content。状态矛盾、非空结构化结果、未知结果键及内容变化都会走协议不一致分支。原样结果相等不会跳过这些检查。

consumer.consume_turn 保留原 code、defaults、closure 和 kwdefaults，独立 globals 将 archive_turn 指向候选实现。driver.run_route 的独立 globals 同时指向新 consumer 与共同检查，run_batch 指向候选 route。原模块 globals 保持原绑定。两条业务检查均调用同一 matcher，原成功专用匹配函数及结果相等的 OR 放行已移除。

工具名、完整参数、owner/CLI 数量、attempt 连续顺序、JSON-RPC request/response 类型和值仍由实际外层核对。safe_environment 的既有函数别名已补齐，避免继承 run_route 访问缺失模块属性。

## 原件与有限案例

15 个真实工具原件按原 stdout 的实际字节偏移逐行核对，其中13个成功、2个工具错误。原 owner 文件、六槽答案、usage、状态及夹具副本哈希一致，旧冻结图的176份来源保持原字节。

47 项由6个真实整槽正例、4个明确派生的 owner-style 正例、35个外层调用链负例和2个直接 matcher 非法ID负例组成。单变量负例分别登记状态、isError、CLI error、结构化/未知包络、正文、图片数据/MIME、content顺序、工具身份、参数、attempt顺序和缺项的预期原因。真实CLI投影和派生形态分别计数。

当前有限案例未单列 content-body 的 bool→int 派生反例。源码通过严格JSON类型和同一canonical序列化处理该边界，根已决定保留本轮47项范围。运行时函数指针/原函数code对象不变等断言留待根冻结后的 harness 核验。

## 完成门与旧证据

原 consume_turn 对顶层 error/turn.failed 的收集、原 summarize_turn、safe_to_continue、持有句柄、原始stdout和完成门代码沿用原对象。新绑定只改变工具结果核对。N3原顶层重连错误继续独立保留，usage口径与中断流覆盖仍为unknown。

原正式结果继续为4 completed、2 failed、0 not_run。候选重放只会发布新的协议判断，旧执行状态、质量分母及收益准入沿原记录。

本次操作为文件/AST/哈希静态核对，新增模型、provider、CLI、actor服务、Blender和光栅均为0。
