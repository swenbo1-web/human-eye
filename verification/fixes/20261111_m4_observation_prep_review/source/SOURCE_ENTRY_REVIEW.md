来源、安装和预检证据复核已完成，限定范围内通过：84 项静态核对，无新增阻断。

最终记录为 `SOURCE_ENTRY_REVIEW_FINAL_V3.json`，SHA-256 `2871f495bd6b4d087c543259ff553f185521e3a9e9bd173f8005ca67e60358c0`。产品固定于 `107641ec19919d56aa843c1949261590fc338148`，准备提交 `9c85ab9a0518e1fe2369113f59ce308a2d97b8d3`，137 源 canonical 为 `7a3d108bc5658508d76d98fe24b8f3dee4feac2d50856202b2ea7395c3dc9cc1`。

- 独立重算137源清单和 canonical；工作树、两次固定源码副本、隔离安装均与固定 Git blobs 对齐；两份 wheel 的137产品源码及 RECORD 哈希一致。版本目录缩短未改变产品源码。
- 安装 entry/admin 的模板来自固定源码 `examples/agents`。独立复现版本、解释器、身份、137数量和 entry SHA 的文本替换，生成结果逐字节一致；binding 和已记录的 `-I` identity、模块来源相符。此次未重新执行 identity。
- 真实 metadata tools/list 与公开 schema 相等；P 的 initialize 明确返回 installed_distribution / `9.7.2+m4.r2` /137源/7a3d。N 没有产品入口，两组原生工具 schema 相同。
- N 的1次、P的4次公开工具请求和响应与 thin TX/RX 对齐；P 的3次产品查询进一步与实际产品 stdio 对齐。N/P 初终快照逐字节相同，均与固定28网格快照一致；原始及复制输入19项哈希仍相符。
- 两组 thin 本批均有真实 STARTED/EXIT，PID、nonce、请求数及正常退出吻合；另有 actor、原生 worker 与P产品 launcher 的关闭回执。未将历史 PID 不存在作为正常退出证明。
- 后处理依赖的167份原始记录重新哈希一致。主三关系完整原文（包括 scene_revision、fingerprint、epoch、trace）及 nearest 原拒绝原样保留。

失败历史仍保留：安装 run01 的 WinError206、预检 run01 的路径 KeyError、run02 对 nearest 错误码的错误断言。原始 aggregate 仍为失败。实际 nearest 拒绝为 `acquisition_triangle_data_required`；该原资产含四边面/多边面，Decision A 未改变资产以强行通过。后处理仅重新解释同一份已完成回执。

本轮检查器首次误把 admin 模板当成安装包内源码，且误按漂亮格式JSON计算 native 身份、要求通知存在 RX；第二次又误要求生成 entry 与未替换模板完全相同。初版脚本/结果和第二版脚本/结果均保留，最终版按实际格式及精确模板替换核对。它们是复核脚本假设错误，未发现产品对应缺陷。

本次只执行静态哈希、Git和回执绑定脚本，未运行产品、Blender、模型或作者后处理。未读取匿名映射；完整303索引/305Git成员、独立几何真值和质量投影规则由主复核及另一子项负责。图片观测沿原 helper 的 render hook/workspace PNG 范围，不声称通用沙箱证明。本报告不签发正式 GO，不覆盖另已发现的质量包 condition/profile 投影缺陷。
