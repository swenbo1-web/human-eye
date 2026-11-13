# 接口兼容批：来源保全与失败账本独立复核

固定交付 `b51dc02eb4f25966f983033b42dad3c9cfec9393`，准备 `1adbf71062f5821dbd6b15c9138c58bc05355a45`。本轮来源保全与账本追溯通过；没有发现新增来源或记账缺陷。

自编离线脚本 **206 项核查通过**，记录3,023个输入路径。没有运行作者checker、产品、Blender、模型、API或本地进程回放；没有修改作者树/Git。核查数量不作为实验样本数。

## 文件与回放原件

- 47交付成员加manifest，共 **48个Git文件**，完整集合、大小、SHA256及Git blob均一致。
- **44份准备内容**核固定准备提交；加PREPARATION本身共45文件。520个外部依赖摘要一致。
- 旧001的144成员加manifest，共145文件，逐项核原交付Git字节和摘要。旧001、FIX1/FIX2及产品目录无Git差异；不重复旧通过矩阵。
- 五份ZIP核归档SHA、无重复成员、完整成员集合、逐成员大小/hash及本地原字节：回放818，a01/a02各395，a03/a04各396，合计 **2,400成员**。Git深层目录缺项不被误判丢失，其原件由已跟踪ZIP及成员清单绑定，本地深层文件也完整保留。
- a01–a04的浅层RESULT与原目录RESULT逐字一致，各保存四项预期case。每次实际11个fake CLI记录、11份thin STARTED/EXIT，四批合计44+44个本地fixture进程；最终12槽为10 completed、1 failed、1 not_run。它们不是新正式模型样本。
- a01仅有运行后源码摘要；a02有前后摘要；a03/a04另保留12文件SOURCES.zip，与当次摘要逐项匹配。a04源码快照与最终源码一致。没有把a01升级成已有运行前快照。
- a03测试通过之后的归档失败仍单列：FileNotFoundError、原命令exit1，与a04修正后exit0区分。a01–a03事后补封没有被描述成重新执行消费。a03原exit1的历史来源是作者保留的失败回执及其对原聊天stderr的引用，本轮未取得独立历史进程探针。

## 旧001失败账本

质量seal `7f902438…d2a51c6` 与固定旧交付对应，已允许成本解封。本轮仅核来源，不重评分内容。

- 六行ledger逐项绑定各自原outer FINAL_TIMING、consumer FINAL_TIMING、CONSUMER、events、TOOLS及ATTEMPT；相关短目录原件与原outer ZIP字节一致。
- outer及turn时长都由原始整数结束值减开始值复算；prompt-to-final也独立以原prompt提交与final接收时间相减。三者实际嵌套，scope字符串原样保留，不能相加。原outer通用scope文字含三轮/EDIT字样，不代表三轮实际执行；实际仅首轮，后两轮未运行。
- 14次attempt的名称、耗时、返回状态及字节字段与实际ATTEMPT逐项一致。响应字节独立按原actor的compact JSON RPC序列化复算，并核合计等于wire_tool_bytes。它是owner RPC回执口径，不等于CLI全部输出、模型完整输入或收费token。
- 六个原turn.completed事件的全部usage字段和值与ledger、raw_usage_events、usage_rows完全相同，包括cached、cache_write和reasoning子字段。没有再次加总子字段，也没有据此推算费用。
- 原执行状态仍是 **6 failed、12 not_run、实际resume=0**。12槽elapsed/usage保持null；usage scope unknown、aggregation null。provider请求和fees按原值保留，共享准备、审核、打包、端到端总成本与不可见provider开销仍unknown。
- 六项thin EXIT unknown没有因独立owner close确认而改写。质量正确与执行验收失败分别记录，旧失败没有被新接口回放覆盖。

这份账本可以用于说明旧故障消耗；**不能据此宣布连续性能胜负、真实resume收益或总费用优势**。正式连续消费仍应使用另行冻结的新批。

自身AL handle `eedb2e6559c7410dbf9007536acc04f1` 保持旧assignment write611/current=false；已核父当前write628/revision1，只按明确委派执行本轮离线工作，未借父句柄。
