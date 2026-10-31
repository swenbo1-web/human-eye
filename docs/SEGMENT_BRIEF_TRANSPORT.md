# 动作段终态观察的紧凑传输

版本：`v21-segment-endpoint-brief-20261030`。作用范围仅为 `human_eye_clearance_segment` 的 MCP 显示返回。默认 `response_detail=full`；调用方可显式选择 `response_detail=brief`。此选项不进入目标请求、执行服务或持久化动作账本，不增加执行权限。

## 返回语义

在满足已识别合同的新鲜 `satisfied` 或 `review_required` 结果中，紧凑格式保留所有原始非 routing 回执字段，包括完整 request、steps、residual、预算、原因、指标、身份及关联信息。原来的 `routing.context_text` 严格解析后放到同一结果的 `endpoint_observation`，routing 以 `context_observation_ref: "#/endpoint_observation"` 指向它。

重复字典可表示为同一工具结果内的 `$ref` JSON Pointer。首次出现的字典保留物理位置，引用指向前面的字典，不访问其他消息或网络。可选 `object_id` 同级值只补充既有字典中缺少的对象身份。解码必须处理指针转义、拒绝循环和外部引用，保留 null、false、0、缺失字段的区别。

`segment_brief` 标记说明编码修订、同结果引用范围及 `omitted_diagnostics=[]`。**该动作段格式不删除诊断内容**，包括注意力 proposal/state、相机和画布字段。精确等价指解析后的事实值，不承诺恢复嵌入 JSON 字符串原有空格和键排列字节。

原生 PNG 继续放在单独的 MCP image 内容块，字节不变。标签、可见性限制、测量及未知信息全部保留；它们不产生几何认证或新的执行权。

## 回退与历史结果

历史回执、重放、未知写入、错误、未识别合同、已有保留编码键、非法 JSON、冲突副本等保持完整格式。解析、投影或收益判断失败也保留原始完整返回。只有实际节省至少256字节且至少10%时才使用紧凑表示；没有紧凑标记不能推断信息缺失。

历史请求不会为显示需要重新观察或重执行，也不重新交付过去的 PNG。`response_detail=full` 不代表取回某次过去观察的完整图像；需要当前场景事实时应另作只读观察，并保留新的修订与范围。

观察工具原有的 `response_detail=brief` 仍使用其既有命名诊断省略策略。动作段的无删减引用编码是独立合同，不能把两种格式混为一谈。

## 部署与验证状态

候选默认完整格式与旧接口兼容；已安装生产 v20 的磁盘注册不会因修改源码或构建候选 wheel 自动更新。实际激活、当前聊天加载及真实用户入口分别验收。

数据量以实际 MCP 文本 UTF-8 字节计算；PNG 单独计量。字节节省不等于 token、账单、模型速度或模型质量收益。后者需要正式模型任务对照。

本地磁盘注册已切到v21，新固定进程的动作段brief与实际读取通过。重启后当前聊天已核验相同v21身份，并完成当前只读观察brief及原生图像读取；没有为此重放动作段。安装证据见[安装报告](../verification/fixes/20261030_v21_activation/REPORT.md)，当前聊天加载及观察证据见[重载报告](../verification/fixes/20261030_v21_reload/REPORT.md)。
