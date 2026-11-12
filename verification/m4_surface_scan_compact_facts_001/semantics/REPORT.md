# 紧凑事实投递的独立离线语义复核

最终 `run_03` 通过 **180 个 unittest 方法**，其中新增候选用例 24 个、既有回归 156 个，失败、错误和 skip 均为 0。实际候选 `live_spatial_mcp.py` 的 SHA256 为 `6fc5a4b8286130f2e6847ee4d7f4efee94c65a0591940e72b924f24ccd55081f`，测试期间该文件字节稳定。

另有 **13 个实际 schema 样例**，使用本机已有 Python 3.14.7 / jsonschema 4.26.0 验证通过。产品和其余语义运行在既有依赖 Python 3.12.14 上。既有 EntryTests 的一个 schema 方法没有在 3.12 中执行，其原有正负例转入导出的实际 schema 验证，并单列记录。预设总方法数为 181，此项环境适配没有计成原方法通过。

## 恢复和边界

六份封存扫描响应共 **426 条原匹配行**通过独立列名解码。每条恢复原始两对象 ID、name、顺序和 distance_m，距离用 `struct.pack('>d')` 核二进制值。默认和 brief 均为 **7,911 UTF-8 B**，显式 full 均为原 **34,754 B**，完整文本逐字相同。10 KiB 门统计完整 JSON 正文，包含对象表、列说明、公共元数据、来源和 trace。

新增用例还覆盖以下范围。

- signed zero、阈值两侧相邻 binary64、最小次正规、极小正数及最大有限值。独立 Decimal 计算核派生毫米，极大值的十进制字符串保持有限和非零。
- 空匹配、partial、unknown、上游已截短 delivery、未知对象和未来顶层字段。
- 重复名称、Unicode、共享端点和端点附加字段。索引保留唯一 ID，匹配端点表的 22 项与场景覆盖 24 对象分开检查。
- common metadata 与逐行 exceptions 合并恢复，保留字段缺失、witness unknown、原因、方法、布尔与数值零区别、signed zero 及未来字段。
- 原始完整结果的显式 full 字节合同，省略 detail 与 brief 的单一路径，非 scan 的原缺省表示，普通 tools/call 路由与最终预算检查。
- 畸形行与布局键碰撞回退，工具错误原样保留，投影异常和紧凑编码异常回退，以及原始 NaN/Infinity 的严格拒绝。
- 显式 full 重新调用当前观察并使用新的 binding，返回数据和内部 source 的隔离。

故障化解码测试主动删除一行、破坏索引、错误换算原始米值、将 partial 改为 complete，均被独立核对阻止。见证点作为展示省略项，其他逐行元数据均检查可恢复。

## 有限回归和环境适配

回归集合限于 scan reducer、scan 普通入口、OPT1 依赖入口、普通 MCP、task/structure/segment brief，以及 MCP framing 和 publication isolation。没有执行实际持续进程矩阵、Blender 或模型消费者。

旧 segment 的 35 个方法需要本工作树没有的两份历史 wire。测试模块的 `BASELINE` 常量在本次测试进程内指向 D:/hefe 已有原件，两个固定 SHA 分别为 `ecc0bfcfb1f60acfb703b7e24a061872be1c614399f07a536e2856931c655ffd` 和 `82abb05b9ddcb6684b7a3765bb424c365df40c38a540bf9bca5f9e135c0e5411`。原件和旧测试源码保持原字节。

依赖 Python 3.12 没有 jsonschema，本机已有缓存的 rpds 为 cp314 二进制，因此仅导出候选实际 schema 到已有 cp314 验证进程。`run_03/SCHEMA_INPUT.json` 保留完整输入及所有样例。回执记录验证解释器、validator 脚本、原 schema 方法、依赖模块和 rpds 二进制的 SHA256。未安装或下载新依赖。

## 失败记录

首轮 `run_01` 执行 181 方法，38 项 error 均保留原 stdout 与 traceback。其中 35 项来自缺少旧 fixture，2 项来自 jsonschema 缺失，1 项捕获了候选可选投影异常未回退完整结果的真实回归。生产负责人随后补可选展示的异常回退，原完整 JSON 校验继续在回退范围之外。

`run_02` 已通过，`run_03` 进一步补齐导出的 schema、来源摘要和明确的方法分母后再通过。过程中检查依赖时发现 cp314 rpds 无法在 3.12 加载，以及缓存 schema 解释器不含 numpy，最终采用只验证 JSON 的独立进程。终端宽输出曾截断，完整原日志已写入各 attempt 文件。

## 证据及限制

`FINAL_RESULT.json` 汇总最终状态。`attempts/run_03/RESULT.json` 保留实际方法 ID、环境来源、13 个 schema 样例及依赖摘要。`SEALED_RESPONSES.json` 保留六响应的原文和新文本摘要及完整字节数。`run_semantics.py`、`validate_schema.py`、`audit_sealed.py` 可在同一工作区及已有验证环境重放。

本批新增 Blender、模型消费者和业务 API 运行均为 0。离线表示测试验证的是数据合同，实际模型有效输入、token、任务耗时及重算减少收益仍待后续消费对照。`audit_sealed.py` 的单次本地计时包括独立 JSON 解码，只作核验工作量记录。

Agent Learning 为未绑定，host epoch 5，需要宿主重连。当前子任务按既有授权完成，没有借用其他聊天句柄。
