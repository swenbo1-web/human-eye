# M4-TARGET-ACQUISITION-002 独立身份与成本复核

2026-11-15。复核固定作者交付 `71a505135ecf202c0e8572fb01bbe21c410342e2`、B产品 `c309d7e4302518cd5f7d1c3966e7c7fa338ea128`。独立脚本 `recompute.py` 读取封存文件、Git blob、安装、wheel 与原始时界，结果见 `RESULTS.json`。新增 Blender、raster、消费者模型、API 调用均为0。

## 判定

**已核范围通过，三个冻结工程计时门限均成立。** 8968项为文件和字段核对数，正式性能样本仍为两个固定输入各3对、共12槽。

| 时界 | main B/A配对比值中位 | target-only B/A配对比值中位 |
|---|---:|---:|
| 服务端 request_received→reply_completed | 0.5694043740 | 0.9476120709 |
| 客户端 stdin_flushed→received_complete | 0.5694353365 | 0.9476171002 |
| 完整客户端调用，含回执保存 | 0.5701462158 | 0.9477086038 |
| 完整会话，含准备、固定调用和关闭 | 0.8415417093 | 0.9662045359 |

main服务端3/3配对更快，业务中位≤0.90、完整会话≤1和无排除控制业务≤1.05均通过。服务端与完整会话比值与作者DECISION中的有理分数逐项相等。控制组有限波动不单独归功于剔除算法。

## 独立执行的核查

- 1949个交付成员及清单本身与相对4f8基线的1950个Git变化路径精确闭合。所有成员的字节、SHA256与固定提交Git blob逐项相同，作者工作树clean。
- 1822对runtime原件与归档逐字节相同，清单散列和大小相符。根计划、冻结几何、预登记、正式准入和两个原blend身份匹配。
- A/B各141源分别核对安装、wheel、Git源和清单，重建聚合来源摘要，得到A `9f2c5ca1…a61`、B `776b0f09…25be`。两个wheel散列与绑定一致。
- 12槽按预登记A1/B1/B2/A2/A3/B3顺序串行完成，逐槽原绑定、源摘要、起止时间、原期限、四个实际业务请求和48组原始TX/RX/RECEIPT均核对。四种时界分别从原ns复算，数值为正且位于各自完整调用/会话内。
- 18个正式producer frame对应18条实际render attempt，保存审计报告的实际执行来源分别匹配A/B。MCP正常退出且无forced kill，owned Blender exit0、wait/reap，原文件和受保护状态检查通过。
- 原claims与settlements逐对核散列，39项已结算。19次Blender启动、20个图片请求、资格10 raster、正式18 raster，pending0。正式目录恰为12槽，无额外槽或替换。所有正式模型调用字段为0。

## 时界表述的精确说明

A3_main的主调用中，服务端reply_completed标记比客户端received_complete晚2100ns。`harness/mcp_entry.py`在outgoing.flush返回后记录服务端完成时间，客户端可以先记录收完。因此server和transport应分别描述为由完整客户端调用包围的区间，不能写成二者始终严格嵌套。作者cost_decision.py实际也是分别检查client/server containment，原报告没有明确承诺server严格位于transport内部。建议根报告加此说明，无需修改原时间或重跑。该标记差异不影响1.151秒主窗口和任何冻结门限。

## 限制与本轮检查器修正

完整会话后的保存数据验证有单独postrun_validation字段，按冻结口径未并入session。后台系统/协作进程干扰未量化，真实模型任务、token、费用和总体p95未测。上述工程比值不提供这些指标的结论。原Win32独立句柄字段unknown、旧A01额外runtime unknown与历史清理拒绝按作者保留记录处理。

独立检查器三次准备失败保存在ATTEMPT_01/02/03中。分别修正producer_frames列表长度、server/client采样次序假设、formal目录计数把两个JSON文件误算为槽的问题。最终完整运行exit0，原件和产品均未改变。这些准备失败增加了复核工作，未产生额外产品请求。
