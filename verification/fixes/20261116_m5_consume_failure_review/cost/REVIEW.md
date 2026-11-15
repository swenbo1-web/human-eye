# M5消费异常封存的独立身份、成本与停止边界复核

2026-11-16。固定作者最终提交baf8799d9e1cb411d39da58c28171b00ac76f12f。独立脚本recompute.py读取Git、安装、wheel、原CLI stdout、发布时刻、派发与预算原件，最终11039项检查通过。该通过确认保存事实和停止边界，本批公平收益对照仍无效。

## 身份与原件

- 1642个manifest成员加清单自身，精确闭合相对14c8c6b基线的1643条Git变化路径。成员长度、SHA256、当前作者文件和固定Git blob逐项一致，全部改动位于本批namespace，产品源码差分为空。
- 1311份外部运行原件与归档逐字节相同，共16917573字节，原路径与副本路径边界均核对。928项正式pin保持，当前批内的正式文件还逐份核到99c5ba3e冻结提交。
- A/B各141源分别核Git、安装及wheel成员，重建聚合来源摘要得到776b0f09与7d2d4352，wheel摘要与绑定一致。旧9609历史成员没有机械重跑。

## 实际成本与分母

五个CLI为不同fresh线程，各有唯一原turn.completed usage，保存投影与原stdout一致。完整时界由每槽root启动前至SLOT_RESULT持久化后的发布时间独立重算。各自450秒任务和600秒owned原绝对期限保持，所有最终答案、usage、实际进程关闭及收尾都位于该完整时界内。

| 槽 | 完整槽秒 | 外层工具 | 内部公开请求 | 原input+output | uncached input+output |
| --- | ---: | ---: | ---: | ---: | ---: |
| A1 | 112.8156472 | 5 | 4 | 95450 | 23770 |
| B1 | 78.4476906 | 1 | 1 | 24900 | 16068 |
| B2 | 107.9941198 | 6 | 4 | 91026 | 18578 |
| A2 | 130.8939096 | 7 | 5 | 104991 | 19103 |
| A3 | 115.0210005 | 7 | 4 | 106816 | 19520 |
| B3 | 未运行 | 0 | 0 | 未运行 | 未运行 |

外层TOOLS尝试索引与18条原PUBLIC_REQUESTS逐条对应，实际MCP TX/RX的字节、散列、请求/回复body与时间窗均吻合。发生桥接异常的工具行，其product_requests列表没有交付成功条目，internal_public_call_indices仍保留实际调用。成本使用后者与原PUBLIC_REQUESTS核对，保持错误后的真实请求与恢复开销。

每个实际消费者交付一张4112字节PNG。cached input是input子项，uncached input+output按原字段相减得出，未另加reasoning。供应商turn/session计费范围、现金与图像token保持未测。

完整派发分母为A1/B1/B2/A2/A3/B3六项，实际消费者5，正式尝试1、外层重试0、替换0。原DECISION的pairs为空、totals为null，B质量/联合采用与数值收益门限均未通过。以上原始成本受已确认的harness干扰影响，不能从运行子集产生公平时间排名。

## B3停止与关闭证据

根ROOT_OPERATOR_STOP与B3目录内原件逐字节相同，引用的诊断源SHA均匹配。请求时间位于A3派发之后、自然结束之前，A3完整关闭后dispatcher才尝试B3。B3目录只有这份停止原件，无SLOT_RESULT、SLOT_PUBLICATION、CLI、MCP、Blender或预算claim。

原RUN_RESULT保持B3状态failed、FileExistsError、result_path和publication_path为null。实际状态为启动前停止，不能把这条派发记录解释成已运行失败或补成第六个答案。五个已启动槽按原序串行完成，原记录没有替换样本。

预算原claims与settlements核token、原claim散列和实际结果，7次owned、7次raster、5次消费者，资格raster2、正式5，pending启动/构造结果为0。两资格及五正式会话的actor退出、Blender退出0且reap、MCP保留句柄退出0以及reader/管道关闭分别通过。五CLI主进程退出0，五薄适配器保留句柄确认退出1且关闭，EXIT缺失按原事实保留。

## 独立脚本修正与范围

R0把product_requests当全部内部调用清单，忽略了已实际发出但被桥接阻断的请求；原稿与ERROR_R0.md保留。R1误将DECISION中的原usage字典当成带usage子字段的terminal事件，原稿与ERROR_R1.md保留。最终分别使用原尝试索引、原MCP文件和原stdout事件核对。随后补核18个内部TX/RX与两个资格关闭，最终11039项完整通过。

本轮只写独立脚本、结果与本报告，作者封存和产品保持原字节。新增Blender、raster、CLI、模型及API调用均为0。当前可以继续独立验证最小测试桥修复，旧消费者批维持异常收口。
