# 连续消费001：工具返回包装独立复核

结论：本轮阻断是新增逐轮归档校验把两个不同协议层的包装要求为完全相同，不是正文被损坏。可以只修这一处兼容投影；不需产品修改、provider预试或新计量平台。正式六集失败及后续未运行状态保持原样，不能用本复核倒改为连续消费成功。

## 实际核验

独立脚本 `recheck.py`，152/152检查通过。新模型、Blender、产品和API运行均为0。当前批只读取匿名公开工具证据与诊断摘要，未读当前私有映射、各格成本或usage。历史错误检索只核工具请求/返回及对应CLI工具事件；不使用历史成本数据。

- 当前14次请求的工具名、参数和逐值正文完全一致。14个owner result均只有`content`、`isError:false`；14个CLI result均只有`content`、`structured_content:null`，CLI item均`status:completed`且`error:null`。
- 原整包相等判断14/14都不成立。新复核的窄成功投影14/14接受，17个缺失/篡改/错误/非空结构化数据反例均拒绝成功匹配。
- 找到同冻结CLI版本的3个历史真实tool error：owner为`isError:true`，CLI为`status:failed,error:null`，仍有同一正文及`structured_content:null`。三个真实错误均不能通过成功投影。
- 当前14对核验基于公开业务投影，原件SHA已记录；本报告不替代根的原归档/Git来源绑定审计。脚本未导入或执行作者验证器，也未验收尚未提交的修复代码。

## 为什么之前没有抓住

FIX1 `runtime/consumer_transport.py:92` 的 `archive_turn` 比较 `response.get('result')` 与 `item.get('result')` 的完整编码。它是连续链新增检查，不能因为冷态消费者曾通过就视为已经覆盖。

FIX1 `consumer/fake_cli.py:76` 将`answer['result']`原样作为模拟CLI result；未复现真实CLI对isError的转换、structured_content字段，也未生成真实completed/error状态字段。模拟输入和被测错误假设相同，因此集成测试通过不能证明真实边界兼容。

根旧冷态独立成本复核 `verification/fixes/20261113_m4_surface_scan_compact_cost_review/accounting/recheck.py:106–110` 已明确使用正文相等加不同包装条件，也保留了首版错误等同的失败记录。这条已知事实没有转成连续适配器的真实记录回放。实施与独立复核均漏了这个交叉检查；此次不归咎模型、provider或引擎。后续只需将旧真实成功包装及本轮14对作为固定边界回归输入。

## 最小修复及验收

1. 请求仍逐工具名、参数、次数和顺序绑定。返回正文按类型和逐值比较，不仅拼接text，也不忽略其他content成员。
2. 成功分支先检查owner无RPC error、业务isError为明确false，CLI明确completed且error为null，再允许本轮实证的`isError:false`省略及`structured_content:null`插入。缺省isError若要支持，应有明确规范/固定实现依据；本批14次均明确false，不需要靠放宽缺省值修复。
3. owner真错误、RPC error、CLI/transport error、未知非空字段不得进入成功归一化。非空structuredContent若支持，必须比较完整结构及明确的camel/snake字段对应；否则标不支持/不匹配，不能仅比较content后丢掉它。当前零调用修复可直接不扩此范围。
4. 对3个已证tool error，可核正文保真及`isError:true → status:failed`，但必须保留它们的失败语义。**记录被忠实传递、动作是否执行、是否允许后续自纠或重试是不同判断**；本批不改变原失败分类、自纠、重试和执行不明处理政策。复核脚本的false仅指“不属于成功包装”，不表示新设整episode终止规则。
5. 在实际修复后的`archive_turn`路径回放14个真实成功及3个真实失败，再加请求/正文缺失和篡改、RPC/transport错误、非空结构数据的定向反例；核原始文件仍保留，错误未被标成成功。应复用原件，不让新的fake CLI再自行发明错误包装以证明自身。无需新provider调用。

未找到同固定CLI版本真实RPC/transport错误及非空structuredContent转换例；这两个映射保持未证，不阻塞只接受已证成功形状的最小修复。17个合成反例只证明窄谓词拒绝它们，不冒充真实CLI错误转换证明。

## 历史真实错误输入索引

以下路径均相对于实施树 `C:/Users/Administrator/.codex/worktrees/m4-single-pass-acquisition/hefe`，属于旧已解封批，不是本轮分组映射。请求、返回和CLI原事件定位及完整SHA亦见`RESULTS.json`。

| 旧原件 | SHA256 |
| --- | --- |
| `verification/m4_surface_scan_consumption_001/cells/P1/owner/tool_03/RESPONSE.json` | `ed7236af2a3ef5080b2de78eb30a746f0d8652efc2fd8c339c4a6a08bfe13ef1` |
| 同目录 `REQUEST.json` | `bf387b430ef2754a53049c94478a41c263265d08553216c86ff10c58cc85868e` |
| `verification/m4_surface_scan_consumption_001/cells/P1/events.jsonl` | `ee2538b6e9c640c4948d088a81e58c61f919d2d8304ac30eb3dfb6c9305ab6d8` |
| 对应完成事件原行 | `c1ae2acc2a476e614a2ee1d2a1fa22a3587a75e5afce04152128019e33686dd7` |
| `verification/m4_surface_scan_consumption_001/cells/P3/owner/tool_03/RESPONSE.json` | `ed7236af2a3ef5080b2de78eb30a746f0d8652efc2fd8c339c4a6a08bfe13ef1` |
| 同目录 `REQUEST.json` | `400d302d77c2f78d66f6d8c60842601d83874ab3902cb42b51aa73bc1f575a5d` |
| `verification/m4_surface_scan_consumption_001/cells/P3/events.jsonl` | `46e67ef11b0189c16bbd90828261eb0d256d76847d4c9d88a8128d9dd6e8e0cb` |
| tool_03对应完成事件原行 | `c8f6c6d9dcf091b6702a8c8bb75983bdf903dfa574449d2b57df6622786dd0d6` |
| `verification/m4_surface_scan_consumption_001/cells/P3/owner/tool_04/RESPONSE.json` | `16fc3b405b84c0f717020760983cafcadb40b8eb23a1c8844b4c76153e6272b3` |
| 同目录 `REQUEST.json` | `fb0ad0cb740b6774b740fb64d09e7b9b36942d0ab964e311816cc7585ceebfa4` |
| tool_04对应完成事件原行（同上述P3事件文件） | `15a0a07b628f68e973f986810bf6c22f04017b4e689bbb0a19147b535a58d535` |

旧`PLAN.json` SHA为`7e3567f1ea8b528c13d36078abe2a659ba7ff74d02342cca86c1bff3dfedcb3f`，固定CLI 0.152.1字节SHA为`01b0fd4167393e004b9174c77ae5f8570486118e19dc4216cfc62a62a74b6ee6`，与本轮一致。旧`runtime/driver.py:229`运行前断言该SHA；该driver SHA为`29f8c2ccd360b71c410c98818f865c74fa19d65a1548de571197d14c6a7c8bce`。本次未重启CLI，不新增二进制行为证明。

## 批次停止与边界

六集均尝试首轮来自原冻结“单集失败不取消其余集”的策略，不能事后删除失败或重写分母。下一formal可仅增加一项明确的harness基础故障`stop_reason`：首次发现包装/原件绑定的共享基础故障，关闭当前owner并将尚未开始的固定槽列not_run，交根复核；不要把模型答错或正常tool error泛化为共享故障。不需另建调度层或自动修复重跑。

父任务d5c646fe/r1已由session_context核实；自身子assignment仍指旧任务，未借父句柄写入。输出仅此独立复核目录，不改实施树、不发实施消息。
