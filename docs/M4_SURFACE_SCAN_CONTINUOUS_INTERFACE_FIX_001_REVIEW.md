# 连续消费接口修复独立复核

2026-11-13。固定准备1adbf71062f5821dbd6b15c9138c58bc05355a45、交付b51dc02eb4f25966f983033b42dad3c9cfec9393。产品452b44d2／138源4067保持。根本轮没有新增模型、provider、Blender或产品运行。

**最小兼容修复通过，可进入新的连续消费002。** 原001六次执行失败继续保留；新的离线回放不能补成真实模型resume，也不能与旧首轮拼接。

## 改动与实际效果

archive_turn只在原整表示不相等时增加一个成功兼容条件。原exact路径保持，故旧同表示错误的回执绑定和后续行为没有被重写。新增条件要求owner无RPC错误、isError为明确false，CLI明确completed且error=null，content整体按类型、顺序、文本和值对应，才接受isError:false省略及structured_content:null插入。

根独立调用实际新旧archive_turn：14份真实成功旧拒新过；3份同CLI字节的历史真实错误旧新均拒；定向缺失、篡改、类型、RPC和结构化数据反例不能经新成功分支通过。同表示错误仍忠实绑定，不因此把工具本身称为成功。旧exact已有的宽度未由本批重新定义，修复也没有宣称解决所有MCP错误表示。

AST逐函数核对确认只增加该条件；实际导入的consume_turn globals指向新archive_turn，coordinator globals指向新transport。原进程循环、原件复制和归档逻辑按固定字节复用。

## 进程接线及下一入口条件

作者定稿a04有4个本地fixture场景、12槽：N/C正常各3轮，真实跨表示错误在第二轮保留失败、第三轮未运行，同表示错误控制沿旧exact继续。合计10completed／1failed／1not_run，是预期fixture状态，不是正式模型成绩。a01–a04共44次fake CLI及44次thin调用实例，不当作全部OS进程总数；a03测试后归档失败及随后幂等路径修正均保留。

下一正式driver仍需明确换到新wrapper并接入共享harness故障停止。这是原修复计划留给新正式批的入口适配，不能仅以纯stop函数表当作已经接通。

根还在实际外层调用中发现一个具体接口差异：新episode wrapper没有pack属性，旧driver结束时调用coordinator.pack.capture_cell。直接换模块路径会在完整归档时失败。002计划已经要求显式复用同字节coordinator.legacy.pack，并在实际wrapper下用无provider依赖替身走完run_one的finish→postclose→outer archive→publish；不以虚构pack属性的假模块掩盖问题。这项在002必要接线中完成，不新增产品模块或另一准备批。

新增全批停止仅用于原owner和CLI都明确成功却仍发生请求／结果绑定故障，复用现有stop_reasons和not_run/break。普通工具错误、内容错误及自纠规则不因这条分支改变；旧001执行策略不追溯重写。

## 本轮证据与作者记录

根[接口独立核查](../verification/fixes/20261113_m4_surface_scan_continuous_interface_fix_review/interface/REPORT.md)749项通过，实际调用94次归档函数：17份真实原件、25个定向变体、5个旧exact／正文控制，各核新旧两路。它们不是94次模型或产品调用。完整回放原件本地保留，以ZIP和逐成员摘要入Git。

根[来源及账本独立核查](../verification/fixes/20261113_m4_surface_scan_continuous_interface_fix_review/binding_accounting/REPORT.md)206项通过、3023输入路径。48个Git文件、44份准备内容（含PREPARATION共45）、520复用来源、5个ZIP及2400成员与固定Git和本地原件一致；旧145文件及FIX1/FIX2、产品字节未变。

根[进程与入口独立核查](../verification/fixes/20261113_m4_surface_scan_continuous_interface_fix_review/integration/REPORT.md)265项通过，从实际记录核四场景、错误语义、身份和归档，并确认上述外层pack适配条件。审查脚本首版误将launcher PID与脚本PID视为相同，并要求串行thin PID不复用，16项误报已按各自关闭凭据及PID＋nonce绑定修正，初版保留。作者381项原件回放、52项纯函数／AST检查及四场景进程执行是作者记录，未并入根独立检查数。相同字节的旧安装、安全和几何矩阵未重复运行。

## 失败账本与收益边界

原001六首轮outer、consumer与prompt至final时间已按原始整数时间点独立复算；14次attempt与RPC响应字节均追溯原件；六份turn.completed原usage逐字段一致。三种时间互相嵌套，响应字节不等于模型输入，cached和reasoning子字段不能重复计入。

旧执行仍0completed／6failed／12not_run，resume0；六份thin EXIT继续unknown，owner关闭不能替代它。准备、审核、完整共享打包、provider实际请求和费用未测项不填0。没有给连续收益排名，也没有估算未运行轮次。

接下来按[002冻结计划](M4_SURFACE_SCAN_CONTINUOUS_CONSUMPTION_002_PLAN.md)直接执行六个全新episode，双方保留上下文和脚本缓存，质量先封，成本后解封。仅做实际有变更的入口、归档和停止接线离线检查，不再重复同题准备与格式优化。Google/key/503/付费、默认、原资产、共享GUI及竞争分支不动。
