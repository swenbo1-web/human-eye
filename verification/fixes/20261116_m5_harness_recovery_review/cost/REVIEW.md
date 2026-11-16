# M5-HARNESS-RECOVERY-001 独立身份、预算与关闭复核

2026-11-16。固定作者最终c041d4f038f72215aa4107a26fcbfd36aa53dd31，实测前冻结046e1772959af7c3c297ac2678ac3845ae27abc5。独立recompute.py读取Git、wheel、安装和保存运行原件，最终4913项检查通过。实际范围为两次owned恢复会话。

## 身份与原件闭合

- 567个manifest成员加清单自身精确闭合568条Git变化路径，全部位于本批namespace。成员长度、SHA、作者当前字节和固定Git blob逐项相同，作者工作树干净，产品差分为空。
- 384份外部运行原件与归档逐字节相同，共4645843字节。68个直接冻结输入保持，当前namespace中的冻结文件另核到实测前Git。五个旧直接seal、原候选和资产核同，历史大清单展开为0。
- A/B各141源分别与对应Git产品提交、wheel和安装逐文件一致，聚合摘要为776b0f09与7d2d4352。实际initialize返回installed_distribution及相应源摘要。
- 两会话首次加载resident的原native WIRE代码与worker SCRIPT文本相同，worker事件记录代码SHA并确认成功执行，加载前resident为空。独立从实际代码AST解出四份base64/zlib字面payload，逐字节等于A/B安装的blender_host.py和scene_residency.py。

## 原时界与实际操作

| 会话 | 完整恢复会话ms | 外层Python工具 | 内部公开请求 | 归档序列 |
| --- | ---: | ---: | ---: | --- |
| A | 4606.0515 | 4 | 5 | 1、null、2、3、4 |
| B | 4094.1011 | 4 | 5 | 1、null、2、3、4 |

完整时间由各自SLOT_PUBLICATION原发布时间减root开始时刻独立重算，包含实际关闭及RESULT持久化，最后publication标记自身写入另列。所有公开请求、业务结束、清理和发布均处于同一原600秒owned期限内，产品和Blender请求预算均为30秒。旧consumer命名字段的值同为本轮600秒。

十个内部原TX/RX散列、body、错误标记和各自client时间窗与保存PUBLIC_REQUESTS一致，八外层调用计数核同。消费者记录和路径均为null，模型和付费调用为0。这些时长用于记录恢复验收投入，本轮没有性能排名。

实际2次owned、2次raster，八次business_tool是立即计费的准入记录，owned和raster四项operation claim均有绑定结算。原构造audit切片的开始、长度、SHA和实际render事件核同，无待结算操作。

## 退出与墙钟范围

两actor退出0且句柄关闭。MCP由原保留句柄确认退出0，stdio正常关闭、reader停止、管道和句柄关闭，无forced kill或退出错误。两个Blender均实际退出0、wait/reap完成，具体close回复为closed，原资产和受保护文件保持，初末全场几何fingerprint相等。Owner listener及线程关闭成立。通用worker日志原件按原字节保留，真实退出由这些独立具体证据确认。

注册至DECISION为10704.7845358秒，至封存账本为11135.7980813秒。账本明确active_work_ns和interruption_and_idle_ns为null，两段墙钟包含中断和用户继续等待，不能解释为纯工作时长。协调/审查费用仍未测。

## 本轮独立检查器修正

R0误将worker的UTF-8代码字符串SHA与Windows SCRIPT.py的CRLF原字节比较，最终在核原WIRE字符串等于SCRIPT文本后，按实际执行字符串计算SHA。R1误要求立即business准入也有operation settlement，最终分别计八次准入和四次操作结算。R2读取raster证据尾部至最终EOF，最终按原记录的start和tail_bytes切片。三份原版及ERROR_R0/R1/R2说明保留，修正均使用同一原件，产品与作者记录不变。

最终4913项属于文件和字段检查数，两会话分母保持。本轮新增Blender、raster、CLI、模型和API调用均为0。该范围内通过，支持接受同步串行测试桥恢复；M5模型收益仍按原异常消费批保持待证。
