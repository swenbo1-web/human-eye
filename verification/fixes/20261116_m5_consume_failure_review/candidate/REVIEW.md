# M5消费归档关联候选独立复核

2026-11-16。固定作者交付baf8799d9e1cb411d39da58c28171b00ac76f12f。候选owned_runtime.py的SHA256为371049158c7370a0e29e30992e5b1fe2cd6d6ba726688e77017ca44c27f94318，原运行器为5d2f252d3abba832297547c4087f6f9ffba3b0b429090d028f75060516d50b73。

候选的最小修复方向通过独立纯函数、mock及保存序列复核，未发现阻止真实恢复验收的缺陷。check_candidate.py从候选AST提取correlate_archive及原public_request方法，独立构造输入，没有导入作者checker。最终104项检查通过，原首轮100项结果保存在RESULT_100.json。两轮均无新Blender、MCP、raster、模型或付费调用。

## 根因与候选行为

原RootRuntime将公开请求计数_product_calls同时写成producer_archive_index，并要求最后一条INDEX记录的index等于它。mcp_entry.py的ObservedService.observe在进入service时才递增_archive_counter，前置query校验拒绝不会调用observe。service自身异常也可能消耗计数而未写INDEX。这两个序列具有不同的递增条件。

候选在public_request开始前保存INDEX原字节，返回后保存新字节。correlate_archive先核精确旧前缀、完整行和递增独立index，再要求本次至多一条新增记录。成功回复需要新增记录，前置错误且无新增时保持null。关联记录的producer始末须落在当前原client调用窗，路径必须等于本槽product_full/call_独立index/SERVICE_RESULT.json，内容SHA须一致。

候选public_request直接返回原response对象，错误回复也保留。关联失败时保存原成功response、null索引及post_reply_binding_error，再报告该具体故障。未把缺失或旧归档当成新成功。当前bridge.py的_serve以单线程串行handle实际请求，普通Python批量亦顺序调用，因此一调用一新增归档的前提与现有运行模型相符。

## 独立重放与控制

所有正式已运行槽从原最终INDEX按真实saved_ns与请求窗口派生精确字节前缀，原文件保持原字节。匹配结果如下。

| 槽 | 公开请求数 | 实际独立service归档序列 |
| --- | --- | --- |
| A1 | 4 | 1、null、2、3 |
| B1 | 1 | 1 |
| B2 | 4 | 1、null、2、3 |
| A2 | 5 | 1、null、2、3、4 |
| A3 | 4 | 1、null、2、3 |

每条关联还与独立的begin/returned/saved完整窗口搜索比较，成功原response散列核同。A1序列与所报反例一致。

mock调用原候选public_request，连续两个前置拒绝后observed、partial，再拒绝、再observed，实际索引为null/null/1/2/null/3。另一组service计数消耗但无归档、后续成功及formatter错误已产归档，得到1/null/3/4/5；原response对象、isError和完整日志均保持。

独立负例覆盖成功无新增记录、只有旧记录、前缀改写、半行、重复/倒序/非法index、多条新增、早于请求/晚于响应/倒置时间、缺时间、跨槽路径、错误index目录及错误内容散列。边界时间相等与合法service计数跳号通过。缺归档成功回复在运行器中触发具体异常，同时原成功response和post_reply错误记录完整保留。

这104项属于固定逻辑与保存证据检查，真实恢复链尚待下一批实际MCP验收。没有用回放结果改写原模型采用或收益分母。

## 迁移要求与下一最小验收

当前候选刻意仍使用旧EXTERNAL=D:/he_m5_task_consume_001，NAMESPACE指旧批、HERE指其harness。直接运行该副本会落到旧上下文。下一批应复制所需的最薄运行文件到新的隔离namespace与EXTERNAL，更新相应根路径、输入和source pins后固定。产品安装与源字节可继续使用已接受的A/B版本。

建议零模型真实恢复验收各启动一次A/B。经实际bridge普通Python批量入口，取得观察，然后提交一次可预测的前置校验拒绝，再提交有效objects surface_proximity请求与有效partial请求，最后一次正常ping或有效只读请求。核外层实际交付等于原MCP回复，拒绝关联null，后续有效关联各自真实service序号，距离/见证与当前来源正确。B额外以正常联合请求证明既有入口可用。每次真实请求只发送一次，正常关闭并保留原收尾状态。

缺失、多条、跨窗、跨槽、散列等归档破坏已由离线负例覆盖，可在新namespace按同一纯检查核验。真实验收重点是拒绝之后继续交付，所需现有图片均可按生产者缓存复用，失败图片构造按实际预算计入。该步骤完成后根再决定下一真实能力任务，原五消费者与未启动B3保持收口。
