# 连续消费001：质量封存与接口阻断复核

2026-11-13。固定交付11f944e71bc530822e8741384732529003efc29f、准备a02c4230651b8134539fb4d96595998d8146c75a，根预登记ee1e1111。根本轮没有新增产品、Blender、模型或API运行。

**六份实际首轮答案内容均完整正确；正式连续测试没有通过，仍是6次执行失败、12轮未运行。** 阻断发生在测试消费者的回执比较，连续重查和EDIT没有进入模型。不能由此说引擎答错，也不能说连续性能已获验证。

## 独立质量结果

| 维度 | 结论 |
| --- | --- |
| 计划分母 | 6 episode × 3轮 = 18槽 |
| 实际final | 6份，全部为BASE |
| 内容主项 | 6 complete_correct，12 not_run |
| 本轮状态依据 | 6份均有当前业务事实支持 |
| 逐表核查 | 426条匹配，漏报／误报／重复／距离错误均0 |
| 执行 | 0 completed、6 failed、12 not_run |
| 完整有效episode | 0/6 |
| 真实resume | 0；第二、第三轮消费未测 |
| thin退出回执 | 6份EXIT缺失，仍unknown |

六份均给出全部71对、毫米六位小数和正确完整性说明。额外的对象/三角形数量、阴性数量、零距离、最近阴性与全量复核说法也按原业务代码/输出核查，未发现确定性错误。工具正文能够支持内容判断，完整回执绑定失败则保留在独立执行维度。

已生成[质量seal](../verification/fixes/20261113_m4_surface_scan_continuous_quality_review/QUALITY_SEAL.json)，SHA256 **7f90243826c1a113d0365282517899902cc9aa2f1b163b67c43d6c644d2a51c6**。匿名包c062e993…4939d，真值和距离标准沿固定合同。质量核查员只读公开匿名材料；来源核查员单独核私有原件，根未解封当前成本或匿名映射。业务内容会透露工具路线，这一局限保留。

## 根因及为何漏过了准备检查

14次工具调用的请求和content逐值一致，但表示不同：owner结果有isError=false；真实CLI省略该字段，并在result中增加structured_content=null，工具item为status=completed、error=null。

FIX1的archive_turn要求整个owner.result与CLI.item.result编码相等，因而14次全部产生CLI_result_differs_from_owner。错误在每个首轮收尾归档时使valid_completion=false，三轮协调器依合同停止其后两轮。模型已在此之前给出完整final。

此前fake_cli直接复制owner.result作为CLI.result，构造的是同一种包装，没有覆盖真实转换。更早的冷态独立核查已明确记录content相等而包装不同，这个已知事实未被转成连续链的兼容回归。**这是实施及根复核共同漏掉的接口测试，原件足以提前发现。** 工程thin调用通过或大量同构替身检查，不能替代这一个真实边界。

根还找到同一冻结CLI字节的3份历史真实工具错误：owner isError=true，CLI status=failed且error=null，正文同样完全相同。因此不能改成只比content，也不能从error=null直接推断成功。最小修复是在已证成功形状下允许这两处包装转换，保留请求、业务内容和错误状态。

## 本轮独立核查与边界

- [匿名质量核查](../verification/fixes/20261113_m4_surface_scan_continuous_quality_review/quality/REPORT.md)：自编670项通过，逐276对精确有理数判距与人工语义复核；未调用作者scorer。根另自编交叉核对六表426事实及18槽，见ROOT_CROSSCHECK.json。
- [来源与执行核查](../verification/fixes/20261113_m4_surface_scan_continuous_quality_review/binding/REPORT.md)：196项通过，145交付文件、33准备文件、372复用输入、65公开文件及799档案成员对应。六个真实UUID互异，无resume。所有owned backend和CLI有关闭/reap证据，但不能替代六份缺失thin EXIT。
- [接口核查](../verification/fixes/20261113_m4_surface_scan_continuous_quality_review/interface/REPORT.md)：152项通过，独立核14成功及3历史真实错误；一个窄成功判据的离线原型验证了可行方向，尚不是实施修复验收。未证RPC/transport错误和非空structuredContent的真实映射仍不能当成功兼容。

检查条数不是模型样本数，核查输入有重叠。作者241项打包检查保持作者记录，不计根成绩。根来源脚本首版全对象比较忽略了consumer在写盘后才附加final_timing，曾误报六处；已逐字段证明仅该派生字段不同并绑定其原文件，首版和修正保留。根两次按未展开的路径找评分合同/fake脚本未命中，随后按真实目录读取；不涉及原件修改或运行重试。

本批每集首轮失败后依冻结策略停止本集，仍继续其余既定集，所以同一接口问题影响了六集。下一正式批应对明确共享harness故障使用现有stop_reason结束剩余槽，避免扩散；内容答题失败与这种接线故障分开。旧001不追溯修改分母或执行策略。

## 下一项

执行[最小接口修复计划](M4_SURFACE_SCAN_CONTINUOUS_INTERFACE_FIX_001_PLAN.md)：零新增模型，回放14份成功、3份同CLI真实失败和少量定向变体，接入原消费者循环；不改产品、算法、题目或默认安装。修复提交由根独立复核后，再冻结新的连续批，不能拼接旧首轮与新后两轮。

质量现已封存，允许整理这次失败批次的实际成本账本，所有六首轮消耗保留，不给连续收益结论，不估算未运行轮次。Google/key/503/付费保持暂停。该问题不改变主动扫视的能力规划，但应先结束这处明确接线缺陷，再推进全场发现—补看—覆盖任务。
