# M4 相机修复：独立来源与完整成本复核

固定 final `4f8c41f89c9b40b3f310cf3f8e8b711bf09864a6`，产品 `691f7b78ed89ccf30df47847fc1e99ad51a1dc64`，基线 `03eb4e2971891dfe0160972cbcf974e3dcf1a21c`。本轮 `/root/camera001_identity_cost` 的 AL assignment `09d119f9-da91-40f9-ab8e-7f8996bfb1d2` current=true，父任务 a7a6442d/rev1/write720；未覆盖父任务。

**检查范围内未发现来源失配、漏记成本或未关闭的本轮进程。报告存在两处计时标签需澄清，以及“主捕获0”应解释为没有成功交付capture，而非没有做几何工作。** 这些澄清不构成新的产品修复，也不证明完整任务提速。

## 本轮实际执行

自编标准库离线 `audit.py` 首次 2042/2042 保存证据断言通过，读取并记录1753个路径。随后仅将原始主请求资源工作计数补入输出，再读同一批材料；没有新增产品、Blender、raster、模型调用，没有执行作者审核器或微测。文件断言数不是功能场景数。

- 768清单条目加清单自身，精确覆盖基线到final的769路径；每项SHA、大小及Git blob与工作区字节一致。
- 141源分别核产品Git、final Git、工作区、wheel、隔离安装五方同字节，按公开规则独立计算聚合 `9f2c5ca150f968841b64f4d4eda89313069453853c877ba21b6a262999e29a61`；旧A安装141源仍等于固定基线。
- wheel整文件摘要 `0956bdeeebcbd5be47f79b0c34f6e3e1dca391b1b88cb4e985c2cb233433dd56` 核对。未将141源检查扩写为wheel所有metadata/RECORD的新一轮全成员审计。
- 681个runtime归档、14961221B与原件逐字节一致。17历史保护pin、5原反例pin不变；未递归重做3723历史内部成员矩阵。
- 每槽实际native请求中的压缩compile源只解码、不执行；scene_residency.py与blender_host.py均精确等于对应旧/新安装字节。实际入口及binding摘要、MCP runtime PID、源身份与持有句柄相互对应。

## 计时口径更正

作者REPORT“主请求RTT”使用的是 `io_audit/MCP_IO.jsonl` 的 `reply_completed_ns-request_received_ns`，是服务端I/O窗口。真正客户端边界在 `stdio/rpc_05/RECEIPT.json`；完整client outer在 `RESULT.requests[0]`。下面全部从原始整数纳秒复算，单位ms。

| 槽 | 服务端请求→回复 | 客户端flush→收到整包 | client call含记录 | 完整client outer | 完整session |
|---|---:|---:|---:|---:|---:|
| OLD extreme | 198.5008 | 198.5356 | 199.4344 | 199.6581 | 2266.3591 |
| NEW extreme | 145.4195 | 145.4711 | 146.5868 | 146.7457 | 2240.6310 |
| OLD origin | 339.5054 | 339.5509 | 340.5500 | 340.6963 | 2471.4940 |
| NEW origin | 315.9316 | 315.9822 | 317.1081 | 317.3139 | 2297.2753 |
| OLD peripheral | 993.2967 | 993.4636 | 994.5412 | 994.7719 | 3301.3959 |
| NEW peripheral | 905.4573 | 905.5095 | 906.5242 | 906.6839 | 2885.1837 |

完整session为started→session_closed，包含启动、初始化、主请求、两次ping、独立AABB回读、预算结算及进程清理。关闭后的保存校验另列，旧新各槽约32.90–58.65ms；资产builder1247.8416ms另列。这些嵌套区间不能相加。每输入每版只有一次，而且extreme工作量变化，不据此称整体提速或尾延迟改善。

**NEW extreme仍做了几何工作。** 第一主请求的原始WORKER_EVENTS保存resource_builds=1、to_mesh=1、triangulations=1，读取4顶点/2面并变换4顶点，之后camera阶段返回numeric_insufficient。它没有交付完整主capture、相机姿态或图片；相关工作已包含在上表时间里，后续READBACK_CAPTURE属于另一请求。

## 冻结微测复算

输入、脚本、旧新源摘要与冻结一致，原7对次序保留，每块512次，总计14336计时调用、64预热调用。以Fraction复算每对完整块时间比，无删除离群值。

| 输入 | 旧/新“块均值的中位” μs | 配对块比值中位 | 逐调用中位 μs |
|---|---|---:|---|
| 4点 | 114.328125 / 121.0337890625 | 1.058652794861282 | 112.3 / 119.3 |
| 289点 | 2153.863671875 / 1320.8583984375 | 0.6133599666732621 | 2122.7 / 1310.9 |

作者114.328/121.034等标签“median”应明确是每块完整时间/512后取中位，含块内记录开销，不是14336逐调用样本合并后的中位。4点增加约6.706μs和配对+5.87%、289点配对−38.66%仍成立；两个统计量不混算。微测与实际MCP窗口分别报告，不能据此宣布大模型任务收益。

## 预算、退出与失败记录

13个claim均有匹配settlement：7次owned启动（builder1+六槽6）均有实际PID；6个图片请求预留36，真实render_attempt合计7，结算保留7，仅释放29个已证未构造预留，无pending。NEW extreme为0图由固定camera错误位置、精确回包和零render事件共同支持，不是仅因出现error就返还构造成本。

六槽MCP retained runtime handle均确认exit0并关闭，stdio reader/pipes/process handle关闭且无强杀。owned Blender持有Popen wait/reap exit0，初末几何指纹、源文件不变；独立Win32句柄关闭字段未记录。生命周期均保留原started+600秒期限；业务和Blender请求30秒未变。请求后两个ping与独立AABB读回均成功。

隔离pure初轮来源检查失败、R1仅runner修复，旧文件与通过输出并存；actual checker初轮可选字段KeyError材料保留，没用新产品观察替换。旧A01 runtime退出unknown和删除拒绝继续是历史状态，本轮没有清理或用新实例补证。协调/复核token、费用和峰值未测。

准备读取中两次误猜不存在的receipt/IO文件名均为只读失败，随后依据实际文件枚举纠正；没有影响产品或原件。证据一致性不替代相机公式/像素质量，由对应独立审查处理。
