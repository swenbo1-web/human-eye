# 错误合同001：统一结果匹配语义独立复核

作者固定提交 `cb5c33a158a9dea06c8151248cc42d2b87c5697b`。本子任务仅核 `result_contract.py` 的语义、47项案例清单与两个真实错误原件，并执行一组有针对性的纯数据补充检查。根及其它子任务负责完整来源、实际函数接线和全部归档，不将其工作计作本子任务执行。

**语义复核通过，未发现需要阻塞下一真实验收的缺陷。** 当前协议问题可以收口；没有理由继续扩类型矩阵、加通用防御层或再修几何算法。

## 源码判断

以下行号相对于候选 `result_contract.py`。

- `:35–57`先识别JSON-RPC result与owner业务标记。顶层JSON-RPC error不会被当成工具业务错误；isError使用真实bool类型，不让0/1混入。
- `:59–67`要求CLI工具类型、明确存在且为null的error字段，再核owner成功对应completed、业务错误对应failed。此检查发生在任何内容比较之前，因此即使两个result完全相等也不能绕过状态一致性。
- `:69–81`仅支持原式content/isError，以及已观察到的CLI content/structured_content=null两种形态。原式继续核isError一致性，投影式不丢弃非null结构化内容或未知字段。
- `:83–94`两类业务结果走同一个完整content比较。匹配失败保留protocol_mismatch；业务错误匹配成功仍分类tool_error，未把工具失败伪装成业务成功。
- `:15–32`以JSON类型检查和canonical JSON序列化比较内容，避免Python的True==1或False==0导致值类型变化被忽略。字典键序规范化而数组顺序保持；文本、图片data及MIME没有单独的宽松比较分支。

matcher仅绑定已经产生的JSON业务结果，不执行数据中的工具代码、不尝试重发，也不负责把顶层网络异常改判为恢复。请求名/参数/ID/attempt和调用顺序仍属调用者验证。完整调用链是否正确接入由根的接线复核另判。

## 两个真实错误及案例清单

直接从FIXTURE_MANIFEST定位原stdout行，读取原始item.completed与owner RESPONSE，核原行SHA和fixture内容，不通过作者matcher判断这两条原件。

| 原件 | owner业务结果 | CLI结果 | 直接核验 |
|---|---|---|---|
| N1_a03 | isError=true，SyntaxError正文951B | failed、error=null、同content、structured_content=null | 内容和已知投影一致 |
| N3_a02 | isError=true，ValueError正文1201B | 同上 | 内容和已知投影一致 |

这证明它们应匹配为业务错误，而非协议损坏。它不修改N1原始完整失败，更不能消除N3另有的顶层流断开和usage覆盖未知。

47项预登记案例与实际记录的case ID集合相同；清单包含6个真实full-slot、4个原式包络正例、35个调用链负例和2个直接matcher负例，实际记录为47通过。**本子任务没有重跑该47项矩阵**；矩阵实际归档/来源和拒绝原因由根的其它审计独立核查。

## 一组实际补充检查

先将候选matcher原字节复制到本目录 `result_contract_snapshot.py`，SHA256为 `5da53bbbfee51f1c07fde32ecf0e1ab1e79a73ef68feff388f709931840cd638`。补充定义及预期在 `PURE_CASES.json` 于调用前固定。只导入该纯函数模块，没有导入候选consumer、driver、archive、作者评分器或回放器。

本次共22次matcher调用，覆盖：

- 成功/业务错误各自的原式和CLI投影式均匹配。
- 两种业务状态、两种包络的相反CLI状态全部拒绝，包含原文完全相等的旧旁路。
- 嵌套body True/1、False/0和数组中的bool/int差别均拒绝。
- 字典成员顺序改变仍匹配；content数组顺序改变拒绝。
- 图片payload或MIME改变均拒绝。
- NaN、会被字符串化的非字符串JSON键、Python tuple均拒绝。
- CLI error=False不被当作null；缺error不被当作隐含null。
- owner/CLI的整数isError均拒绝。

每次调用前后以pickle字节比较输入对象，没有一次修改输入。除纯调用组之外的原件/清单检查合计，**59项检查全部通过**。纯调用窗口0.3462ms仅描述本次小型离线组，不是线上开销或性能基准。候选及原源码在调用后仍保持相同字节。

补充body里的synthetic annotations用于核JSON类型保真，不声称任意自定义字段都是合法MCP内容。这里验证的是绑定函数不能悄悄混淆数据；通用MCP schema审核不是本子任务范围。

## 收口建议与执行范围

可以接受当前统一matcher语义，保留已知CLI形态边界并进入根确定的下一次真实验收。未知包络应明确不匹配；无需为尚未观察到的其它宿主结构继续增加兼容分支。

本轮新模型、Codex CLI、actor服务器、光栅、Blender和provider调用均为0；原tool代码字符串执行0。实际执行只有一次离线审计脚本中的22次纯matcher调用，未运行作者47矩阵、archive或驱动，不改变历史结果。源复制、输入摘要、每项结果及未运行范围见 `RESULTS.json`；SHA256 `ad543ff10a4e7353c0954787cb2bb86a0dd81b0a0faecb4446e4dd5177565053`。
