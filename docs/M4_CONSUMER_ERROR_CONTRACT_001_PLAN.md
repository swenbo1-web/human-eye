# M4-CONSUMER-ERROR-CONTRACT-001：统一成功与工具错误的结果绑定

只修一个确定缺陷：工具正常报告错误后，CLI已知包络转换被成功专用matcher误判，导致可恢复的原生代码错误被混成协议损坏。修复实际消费调用链，用现有原件离线验收；本批不执行新模型或重跑性能样本。

基线 `52d9a838fd52074f3df157aba97e29a5c0cde924`。只在实施分支新增 `verification/m4_consumer_error_contract_001/`，旧001源码/结果、产品/默认/资产/竞争分支只读。Google/key/503/付费保持暂停。

## 固定反例与正常控制

从 `verification/m4_active_coverage_consumption_001/r/` 精确提取全部15个owner REQUEST/RESPONSE及对应实际CLI completed事件，保留原文件SHA、槽位、attempt、tool名和参数。其中13个成功、2个业务错误。

- N1第3次：SyntaxError，owner result为content与isError=true；CLI item.status=failed、error=null，result保留完全相同content、去掉isError并增加structured_content=null。
- N3第2次：ValueError，同样投影。该槽另有顶层stream/reconnect事件，独立保留，不能通过包络修复把它消掉。

旧正确结果、代码错误正文、图片字节和全部原执行记录不改。新产物叫候选协议重放，不把候选判断写回旧4completed/2failed或追溯补成三对收益。

## 最小实现

建立一个统一的结果绑定函数，明确返回成功匹配、业务错误匹配或协议不一致（可用简单结构，不引入新状态管理层）。两种正常业务结果使用同一content核对和已知包络规则。

1. owner必须是可识别的正常JSON-RPC result，isError为真实bool；有顶层JSON-RPC error时不套用工具业务错误映射。
2. owner成功对应CLI工具completed；owner业务错误对应CLI工具failed。CLI工具error字段为null才适用当前已观测content结果投影；缺失/非null或状态矛盾不得被原文相等旁路放行。
3. 只兼容已观察的owner式content/isError以及CLI式content/structured_content=null；业务content的顺序、每个文本字符、图片MIME/data以及其它内容字段完整相同。未知结构、非null结构化数据不默默丢弃。用同一序列化/比较函数，避免两套逻辑漂移。
4. 取消archive中“result完全相等便跳过状态核对”的前置OR。即使原包络完全相等，也要通过状态与error一致性判断。成功/错误两个通道都不能把正文相等当成全部条件。
5. 最小接入真实consumer.archive_turn及driver的同类业务/图片原件核查，复用原tool名、参数、attempt/顺序绑定。不要只修一个未被实际调用的helper。候选可少量派生旧文件并显式绑定只读依赖；不修改旧冻结文件，不复制整套新平台。

普通代码错误保持工具失败事实，但不单凭这个事实把完成后恢复出的答案判为协议损坏。顶层stream/error/turn.failed、缺最终回答、身份/来源不一致、未知动作或退出、真content变化继续按原合同处理。本批不改网络重连策略、调用次数预算、评分门、模型设置或几何算法。

## 一次有限离线验收

在开始前固定候选源码、原件目录及正负案例清单。允许修复本地实现错误后保留失败记录，不新增模型来制造fixture。测试仅读/复制既有JSON、PNG字节，禁止执行原生tool代码字符串。

验收至少包含：

- 15个真实工具原件走候选实际archive绑定链，13成功/2工具错误均匹配且分类正确；2个错误仍保留原业务失败正文。全部六份原答案/usage/运行状态不变，候选重放不叫实际重新运行。
- 原样包络与已知CLI投影两种形态，分别覆盖成功和业务错误；正常图片与文本内容都核验。
- 单变量拒绝：成功/失败状态对调、isError反转或非bool、CLI error非null或缺失、结构化字段非null/未知结构、content文字改一字、图片data/MIME改变、content顺序改变；每项仅改一个字段，不能通过笼统忽略状态而过关。
- 实际上层调用链控制：tool名/参数/attempt顺序不匹配、缺owner或缺CLI项不能被统一matcher遮蔽；通过原件快照副本调用真实archive/共同核查，输出另存。不要再用直接复制owner当CLI的synthetic控制替代真实投影。
- N1原错误绑定可在候选重放中匹配，但旧原失败不改；N3顶层流错误仍被独立记录并按原严格门拒绝，不能通过工具结果匹配把整槽提升为通过。
- 已修构造账本/完成门/stdio持有句柄代码保持字节或明确最小必要导入差异。没有新进程生命周期或几何能力需要另开测试矩阵。

全程新增Pro、provider、CLI、actor服务器、Blender、光栅为0；纯函数与本地archive读取/输出允许。不得启动旧driver --run-models，不回放请求到活动服务，不重发原错误动作。记录本地重放读取/输出与运行时间即可，不把它混进旧实际消费成本。

## 交付与收口

交付候选统一matcher、实际调用链接线、原件映射/摘要、预登记案例及全部通过/失败/未运行、最小使用例。列明原本哪些误拒已关闭、哪些真实网络/usage未知仍保留，不发布“三对正式收益已达标”。

修复通过便停止，不继续改提示词、阈值、空间core、网络容错或重新烧模型样本。提交实施分支，向根 `local/01a1971f-eef5-7a23-a1b1-2352beb80a77` 回报 **M4-CONSUMER-ERROR-CONTRACT-001_READY**，附Git/manifest、实际重放分母及剩余限制，然后结束等根独立复核。
