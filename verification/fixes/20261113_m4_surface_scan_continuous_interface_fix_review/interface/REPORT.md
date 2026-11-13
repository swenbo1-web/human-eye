# 连续消费接口修复：独立实现验收

2026-11-13。固定实施交付 `b51dc02eb4f25966f983033b42dad3c9cfec9393`，准备提交 `1adbf71062f5821dbd6b15c9138c58bc05355a45`。本轮判断：**最小接口修复通过，可直接进入连续消费002的合同冻结与单批执行；无需再开独立准备批。** 新正式批仍须把共享基础故障停止条件接入实际调度分支，该接线尚未由此修复交付实现。

## 本轮实际执行

独立编写并运行本目录 `recheck.py`，未运行作者整体checker。直接导入提交中的新旧 `archive_turn`，对真实原件在根隔离目录执行归档。共 **94次真实归档函数调用，749/749检查通过**：

| 范围 | 实际结果 |
| --- | --- |
| 当前14次真实成功的原始请求/返回/CLI工具事件 | 旧绑定14次拒绝；新绑定14次通过 |
| 同冻结CLI的3次历史真实tool error | 旧新均拒绝成功包装；原失败状态保留 |
| 自行构造25个参数、类型、正文、错误、结构边界变体 | 新旧均拒绝绑定；适用的新成功判据不放行 |
| 旧exact及嵌套正文5个控制 | 与预期完全一致，见下文 |

17个真实案例加30个变体/控制，各调用old/new一次，即94次；不是94个模型样本。每次实际产生归档和原件拷贝并逐字节核对。真实成功来自原六 `ORIGINALS.zip` 的请求/响应和对应CLI完成事件，不以作者replay输出替代输入。历史错误仍用上轮已定位的3个原件；原路径、成员名、SHA和逐案结果见 `RESULTS.json`。

没有启动模型、provider、Blender或产品进程；只导入函数并进行本地归档。未重新运行作者44个fake/44个thin历史进程，这部分由其他复核负责；本轮不能冒称已独立重跑完整consumer进程循环。

本次已生成的 `run_01` 完整封入浅层 `RUN_01_ORIGINALS.zip`，共1172成员，逐成员字节数和SHA均回读核对；原目录仍本地保留。ZIP SHA为`a19c4a631c97ab082eda61a76d18186abfbf83d7d3ec3d846ce31e97cd9adad4`。成员清单和打包回执在根目录，Git只需收浅层交付及完整ZIP，不递归stage深层原件。打包没有重跑archive_turn或其他测试。

## 源码和函数接线

- AST比较证实 `archive_turn` 仅将原`encoded(owner_result) != encoded(CLI_result)`条件扩为再检查`not successful_result_matches(...)`，其余函数AST相同。没有改变请求比对、选取尝试、拷贝、归档或失败回执流程。
- `consume_turn`确实复用原函数对象，其`__globals__['archive_turn']`指向新函数；新函数的`compatibility`也绑定新模块。
- `episode.run_episode`确实复用原协调器函数，其globals.transport指向新transport；沿此transport再检查到新archive函数。不是只给模块挂一个新名字、旧函数仍引用旧globals的假接线。
- 工作树HEAD前后均为固定交付。26个直接记录输入前后摘要相同；关键实际源码身份单列 `LOADED_SOURCE_IDENTITIES.json`。完整Git/封存来源验证由根另一子审负责，不将本轮函数核验扩大成全仓重新审计。

关键源码SHA：compatibility为`ad41521eccb2be5e61ca24d37e7e985128267cf959d818a1dd87cd84545d30c4`；transport为`675d0d855635a3586fd60f90c73a70d0bf0968e2b8bf193d2446e77fc5849a5f`；episode为`e3bef0c338e6f6078e74a64a2b3fd5fc6ea92de0f34ade94410d7b9a10768757`。

## 新扩展的确切边界

新分支只接受owner result精确字段`content,isError`且明确`isError is False`；CLI明确completed且error字段存在并为null；两端content均是list。CLI允许同表示`content,isError:false`或已实证`content,structured_content:null`。正文JSON编码逐值比较，类型、列表顺序、文本及嵌套同名字段均保留。

定向调用实际archive验证：true/0/null/缺省错误位，failed/缺省status，error对象/false/缺省，RPC错误，缺result/content，正文追加或类型/顺序变化，参数和工具名变化，非空structuredContent/structured_content及未知额外字段均未新增放行。参数变体的helper本身仍可能为true，但archive的独立请求比对拒绝它，符合职责边界。

5个控制包括：旧exact真错误、旧exact RPC-null、旧exact非空结构、旧exact成功、含isError/structured_content同名业务字段的正文。前三个旧exact分支原有的宽度继续保留，helper均false；本次没有把它们改成成功语义，也不把已有行为当成本补丁新增缺陷。含同名业务字段的正文在真实成功包装转换中完整保留，未发生递归删字段。

此处“绑定通过”不等于工具执行成功。旧exact错误控制原有绑定行为、错误状态和后续自纠处理保持原样；本修复不扩业务重试，也不重写此前六failed/十二not_run。

## 002只需补上的可执行停止接线

`review/stop_recommendation.py`是可执行纯函数，目前没有正式driver导入。它仅识别请求/结果绑定故障，且owner与CLI都明确成功时建议停批；原14次包装故障均命中，3个真实工具错误、无绑定故障与普通答案错误不命中。这一窄条件足以防止本次已知基础错误再扩散，无需新调度框架。

002冻结时应完成以下小接线，并在同批准备自检后直接正式执行：

1. 在现有唯一finish、归档及失败记录之后，按具体attempt将 `business_binding_errors` 对应到owner和CLI原记录，调用该谓词；只有命中才加入已有`stop_reasons`。
2. 复用旧driver `run_batch`已有的`if row['stop_reasons']`、剩余固定槽`not_run`及`break`，不重开owner、线程或替补样本。新停止原因只增加一项明确harness故障，不把普通模型答错和tool error扩大成停批。
3. 用一次本地调度路径替身证明：成功包装仍失配→当前收尾一次→下一个episode未启动→固定余槽not_run；普通答案错误/真实tool error不命中新原因。只验证纯helper表格不足以宣称调度已接通；无需模型、Blender预试或另交准备批。

根另明确了外层归档接线：新的episode wrapper只导出run_episode等绑定，没有旧coordinator的pack属性。002 driver必须显式复用`coordinator.legacy.pack`，并用**实际wrapper**走outer run_one归档/发布替身；不能给假coordinator临时添加pack后称真实接线已通过。该项与上述小接线同批完成，不另开准备阶段。

作者本批明确把该条件交为建议、没有声称已接正式driver，因此这不是修复交付不合格项，而是002冻结前必须兑现的小范围接线。

## 记录边界

本轮最初按惯例读取了两个不存在的候选路径，已按目录实际位置改读；不涉及运行失败或原件变化。父AL任务a22c631e/r1经session_context核实，自身旧子assignment保留，未借父句柄写状态。输出仅根复核目录，没有修改实施树或产品，没有向实施聊天另派任务。
