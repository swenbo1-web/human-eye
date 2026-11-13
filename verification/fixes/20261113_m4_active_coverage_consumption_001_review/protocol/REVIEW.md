# 覆盖消费001：错误包络、账本与进程终态独立复核

作者固定提交 `52d9a838fd52074f3df157aba97e29a5c0cde924`。本子任务自写离线解析器读取94个原文件，233项检查全部通过。没有运行作者引擎、评分器、validator、CLI、actor、模型、光栅或Blender；没有查询或终止当前进程。已对旧成功匹配条件和当前直接相等分支做纯数据重建，不导入作者执行模块。

**确认一处协议适配缺陷；本轮账本修正和进程终态接线已有充分原件支持。唯一建议下一项是错误结果投影的最小修复及原件重放资格，不新增模型样本。**

## 两个失败分别是什么

| 原槽 | 工具业务事件 | CLI保留内容 | 其它事件 | 原完整资格 |
|---|---|---|---|---|
| N1 | tool03原生代码SyntaxError，正文951B | item.status=failed，error=null；content逐字节相同；result省isError，增structured_content=null | 后续工具恢复并最终作答；没有顶层error | 失败，唯一consumer错误是CLI_result_differs_from_owner |
| N3 | tool02原生代码ValueError，正文1201B | 同样的错误结果投影，content未丢失 | 另有真实顶层流断开/响应正文解码错误及Reconnecting 1/5；之后最终作答 | 失败，包络绑定与顶层流错误两项 |
| 其余13次工具（分布于六槽） | 成功业务结果 | 与旧成功投影匹配 | N3流错误仍按所属槽另计 | N2、P1、P2、P3四槽整体通过 |

以上15次工具调用的请求名称/参数、响应ID、业务content、实际stdout MCP completed事件与CONSUMER存档都一致。两个错误之后确有后续工具调用和最终回答；普通原生代码错误不是工具结果丢失。N3的流错误独立于工具错误，不能通过修包络或删除一次error事件使原槽变为完整合格。原4 completed/2 failed和所有失败成本必须保留。

这个结论只解释协议与终态。六份答案是否正确由根的质量复核负责；即使答案正确，也不把当前未满足的三配对门追溯改成已通过。

## 缺陷的准确位置

以下路径相对于实施checkout。

- `verification/m4_active_coverage_consumption_001/consumer.py:143–163` 的archive_turn先检查owner/CLI result完全相等，否则只调用successful_result_matches。
- `verification/m4_surface_scan_continuous_interface_fix_001/compatibility.py:10–30`明确只接受owner.isError=false与CLI.status=completed。真实错误返回的等价归一化包络不在规则内，因此content完全保留仍被判CLI_result_differs_from_owner。
- `consumer.py:427–430`将该误判写进business_original_binding并否决完整资格。N1只有这一项consumer错误；N3还保留独立的顶层error。
- `driver.py:141–152`的共同图片绑定也有直接相等/成功matcher分支。下一实现应与archive_turn共用同一结果语义规则，不能只修其中一处；本轮两个实际错误是文本响应，没有在图片专用分支触发。
- `driver.py:407–418`的ordinary_tool_error准备控制把owner result原样放进模拟CLI，并且只执行common_image_faults；它既没有真实CLI的structured_content投影，也没有经过archive_turn。因此49项准备检查不能覆盖本次实际边界。

还有同一处匹配逻辑的潜在状态旁路：直接result相等分支没有同时要求CLI status与owner.isError一致。独立纯数据控制证明，owner.isError=true、完全相同result但CLI.status=completed会被现有绑定条件放过。这不是本轮真实发生的错误接受，但说明下一修复不能只再添加一个error matcher的OR；必须把业务状态与包络匹配合在同一处。

## 已修的计量与终态无需重新开批

`image_content.py:130–138`在base64/image块构造完成后立即写constructed并调用on_constructed，随后才执行roundtrip、JSON及最后期限检查。`actor.py:200–207`将这笔成本加入单调构造列表和记录；`:234–241`将已构造后的异常另记post_construction_failures，构造总量不撤回。

独立从准备控制的RESULT与METRICS核对正常、编码后超时、构造后序列化失败、构造后发送失败四项：各保持1个已构造块、同原PNG/base64字节，网络发送为0；编码后超时仍保留构造，序列化未知字节另列，发送失败单列。未重新执行这些控制，也未新增构造成本。控制是明确注入异常，没有把无socket控制说成真实网络断线测试。

`driver.py:172–180`外层门现已包含consumer_safe_to_continue、共同图像故障、输入回读和CLI/owner/runtime实际退出。局部正常EOF与无EXIT退出控制的原记录都证明实际runtime句柄已退出并关闭；原来遗漏的完成/继续条件接线已补。

六个真实stdio运行时均在STARTED后只绑定一次：实际base路径/SHA、创建时间和最多4条父链匹配持有的CLI Popen，记录after_stdio_STARTED且没有伪称before_stdin。根所需全部六个实际runtime退出都在原450秒期限内经保留句柄确认并关闭，**实际退出码都是1**。CLI/actor都是exit0且原句柄关闭。

六个stdio EXIT文件仍缺失，正常EOF、退出触发原因保持unknown。exit1不等于没有退出，也不能声称正常EOF。`runtime_handle.py:56–98`使用原期限剩余时间等待已有只读句柄；未使用事后PID不存在、没有裸PID杀进程。当前已获实际退出证据，足以关闭上一轮“统计终点是否仍有thin运行”的缺口，无需为了得到EXIT文件再烧模型轮次。

## 唯一最小后续建议

在新的隔离修复目录建立一个统一的纯结果投影函数，并让archive绑定及共同图片绑定使用同一规则：

1. 分别表达业务成功、业务错误和协议/传输未知。owner.isError=false必须对应completed；true必须对应failed。匹配表示错误结果被如实送达，不把业务错误改成成功。
2. 只支持已观察的两种结果形状：原content/isError，以及CLI content/structured_content=null。content逐项完整相同；结构化值非null、内容变更、缺失字段或状态矛盾不得靠忽略字段通过。
3. 原请求名称/参数/响应ID及调用顺序继续绑定。顶层JSON-RPC error、CLI非null error、缺失completed或无法对应的调用保持协议失败/未知；顶层stream/turn.failed仍独立进入会话终态，不由业务投影规则吞掉。
4. 用本批15个实际工具原件做只读重放：13成功和2业务错误分别正确绑定；再加有限负例覆盖内容改变、状态翻转、非null structured_content、非null CLI error、JSON-RPC error、缺失/重复/错配调用。当前直接相等旁路的状态矛盾也必须拒绝。
5. 重放两个原完整consumer序列到新候选报告：N1的错误响应绑定可归为兼容，N3修包络后仍带流错误，严格终态不能自动成功。原六槽文件、原门、原失败状态一字不改，候选解释单列。再检查成功图块完全保留以及账本/实际退出字段不被改写即可。

最小矩阵应在候选执行前固定，建议以下组：15个实际正例（13成功/2错误）；成功和错误各一份原形包络正例；两种包络下分别翻转status或isError的矛盾负例；文本/图片单字节改变；structured_content非null；CLI error非null；JSON-RPC顶层error；缺失completed、重复completed、请求参数/顺序错配。除纯matcher外，至少通过真实archive_turn和共同图片绑定两个调用位置重放，证明调用方没有残留的直接相等旁路。原N3顶层流错误是额外会话层保留控制，不将其重新定义成可忽略告警。

这项无需新Pro、光栅、Blender或付费API，不修改core/相机/像素阈值/题面，不扩大成一般协议重构。修复并独立复核后，由根决定是否有必要另开新分母；不能为获得漂亮的三对而即时补跑原失败槽。

## 本审计自身记录

第一次离线脚本因多一个闭括号在解析阶段退出，未读取作者原件或执行实验；`audit_protocol_initial.py`与`INITIAL_PARSE_ERROR.json`保留。只修复该语法错误后完成94文件/233项检查，0失败。完整输入摘要见INPUTS.json，结果见RESULTS.json。
