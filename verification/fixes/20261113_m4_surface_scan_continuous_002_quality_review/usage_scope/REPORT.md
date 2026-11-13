# 连续消费002：usage范围独立复核

结论：**本批 `per_turn_CLI_invocation_observed` 成立。** 质量封存后，可以对本批每个CLI invocation取唯一终值，再作不重叠求和。此结论只确认计量范围，不解封成本，不表示任何收益门已通过。

固定交付a798caf982e2d7eefe0bf52b739b9bef88526be4。作者NUMERIC_PROOF SHA为`ec7e56a39f6d4632aee174a4c4ff19b8f4d9109d3d3da43ee9320de57590f2f1`。独立脚本未导入作者检查器，也未以ALL_RESULT的通过状态作为依据；从限定原件重建投影和数值等式，**1234/1234检查通过**。

实际范围为六个授权测试UUID、十八个CLI invocation、十二次显式resume。来源哈希、同批关闭记录、白名单、consumer绑定、CLI thread.started与预期UUID对应。会话读取严格使用这六个精确路径，不枚举其他聊天，不接触凭据。只投影session_meta、task_started、token_count、task_complete的必要字段；消息正文、任务完成携带的最后消息、base instructions和rate limits不进入分析或输出。CLI只使用线程身份与唯一终态usage。

独立核对的关键事实：

- 每个UUID有三段按序闭合且不重叠的task窗口；token_count全部落入对应窗口，十八个task ID互不重复。
- 每轮首个累计total等于首个last，resume首状态不是前轮终态继续累加；本轮后续每个不同计量状态都满足total＝前一total＋last。
- 终态逐字段等于本轮last增量之和；唯一CLI turn.completed usage、consumer usage、usage_rows和raw_usage_events逐字段一致，并对应本轮终态。
- 核查了相邻重复计量状态。本批没有实际重复numeric snapshot，不能声称本批实测了重复事件消除；累计快照本身也不能逐条相加。
- total_tokens等于input＋output；cached input、cache write和reasoning分别满足记录内的子集边界。计算总量时cached不再加到input上，reasoning不再加到output上。

因此不应把三轮终值误认为会话累计后再差分，也不应对每个token_count累计快照求和。每轮重新提交旧历史所产生的input属于该轮实际reported input，不能因为文本相同而人工扣除。该结论针对此次固定CLI及原件，不能外推所有版本或所有重连情形。

仍未证明：provider侧弃流、隐藏重试的计量覆盖；实际费用或订阅扣账；实际解析模型及完整token化输入可见性。这些继续unknown。报告、RESULTS与CHECKS均不包含组别映射、各轮/各组token数值、成本汇总或winner；费用判断和收益门等待质量seal后的另一次成本解封。

独立脚本首版将原行行尾去掉后计算SHA，导致六项整投影比对失败，所有数值等式当时已通过。核明原记录SHA包含行尾后修正并复算；首版RESULTS/CHECKS/INPUT_HASHES以ATTEMPT_01保留。这是复核脚本的行字节口径修正，不是作者计量错误或被删除的业务失败。

新增模型、API、Blender及产品运行均为0；未修改作者树、未提交Git。父AL任务3046b71e/r1已核，自身旧子assignment保持，不借父句柄写任务。
