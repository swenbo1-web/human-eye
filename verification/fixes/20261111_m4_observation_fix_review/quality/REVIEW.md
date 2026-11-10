# M4-PREP-001 投影修复独立复核

结论：**本子项 GO，前次事实投影阻断关闭。** 没有发现需要继续扩大测试或修改产品的缺陷。根完成其负责的冻结索引与 PLAN 不变量核查后，可以派发既定六格；本报告不代替该总 GO。

固定新版提交 `1c110f2b81b148fd85eb58de0cbe39cae4f3c6e5`，旧版 `9c85ab9a0518e1fe2369113f59ce308a2d97b8d3`。审查范围只有 `quality_handoff/pack_quality.py` 差异及规定的 synthetic 投影合同；没有重审已通过的来源、几何或安装矩阵。

## 源码判断

- `audit_projection` 现在只 deepcopy，不解释 JSON 字符串，不按字段名递归删除，也不改写路径文本。原生 stdout 的换行、空格、JSON 文本和未知扩展可完整保留。
- owner 的 RESPONSE/ERROR_RESPONSE 只移除已知 RPC 顶层 `id/jsonrpc/_meta`，完整 result/error 不再进入递归脱敏。public event 的 arguments/result/error/command 等既有公开字段直接 deepcopy，保留全部嵌套内容。
- 行政删除只在调用方明确识别的信封：请求顶层 RPC 与 params/_meta、owner exception 的直接 traceback、worker_closed 的直接 pid/closed_ns/original_deadline_ns。相同键名出现在事实、参数、错误 data、worker 嵌套扩展时不删。
- final 原字节复制、错误状态、重复请求/事件、缺失响应、未运行与启动前失败的区分逻辑未被改写。source_consistency 的 false/null 仍是生产记录，不升级成通过。结果/方法可能揭示路线的有限盲法继续明示。

## 本轮实际执行

先逐段读完 `revisions/M4_PREP_001/tests/run_projection_contract.py`，确认其 fixture 全部由内存中的 synthetic 常量构造，代码和路径字符串为惰性文本；只调用 `handoff_one` 和纯投影函数，未调用正式 packager.main。

从两个固定 Git blob 提取原字节并核对摘要；同一个测试脚本也逐字节绑定固定新版 Git blob。全部复制和输出只位于本报告的 `quality/` 目录。测试文件没有改动，利用副本位于 `quality/tests/` 的布局满足其输出必须位于 REVISION 下的断言。

使用普通 CPython `-I -S -B`，旧/新各运行一次：

| 版本 | 测试数 | 通过 | 断言失败 | errors | 退出码 |
|---|---:|---:|---:|---:|---:|
| 旧版 | 4 | 2 | 2 | 0 | 1 |
| 新版 | 4 | 4 | 0 | 0 | 0 |

旧失败严格是 `test_root_condition_profile_counterexample_retains_exact_text` 与 `test_handoff_owner_and_public_event_semantic_payloads_are_exact` 的语义 AssertionError；没有 Import/IO/运行错误。旧非零退出与原日志均保留，未把错误当成通过。

新版通过后，我另外独立解析保存的 synthetic 原件与实际 public 输出，没有再执行打包器：逐一核对 3 条 owner 请求/响应/异常、3 条 public 事件、final 原字节、CLOSE.errors、worker 扩展，均与预期允许的直接信封删除一致。缺失第三响应、重复 completed 事件、failed 状态、false 与 null 均保留。所有记录的删除 pointer 仅有：`$/id`、`$/jsonrpc`、`$/_meta`、`$/params/_meta`、`$/exception/traceback`、`$/worker_closed/pid`、`$/worker_closed/closed_ns`、`$/worker_closed/original_deadline_ns`。

## 固定摘要与原始记录

- 旧 packager SHA256：`34a0480c318408826404ea76197ac22bfe1083c977fd9a83959de3ac3e10fe33`。
- 新 packager SHA256：`afa802bdb085ad9e174f04c4ba91ff05bdacdbc7b0bb892162a7b7e14d580cbc`。
- 同一测试脚本 SHA256：`c6861fa01a05e4c2e6a44655b11f9fe3e4c66da0c67fb7f18240e552f46bc6b3`。
- `SOURCE_PIN.json`：`67920f11932358e248d0782401ac0867c337cfc8caf81f22d1498506cc72ea8f`。
- `INDEPENDENT_EXECUTION.json`：`315fd13de35ffc378e8fda1963d7311e657013238a58bdafe776fd7ecb1056ac`，记录实际命令、退出码和双版日志/证据摘要。
- 原日志：`baseline/TEST_LOG.txt`、`revised/TEST_LOG.txt`，以及对应 `EVIDENCE.json`、`*.stdout.txt`、`*.stderr.txt`；独立输出再核对见 `SAVED_OUTPUT_RECHECK.json`。

本轮未启动模型、Blender 或产品；没有正式打包运行、没有读取匿名映射，没有修改实施树或旧 M1 证据。通过范围是此修复对实际 handoff 函数的有限 synthetic 合同；正式六消费者的答案质量、交付状态及完整成本仍待实际执行后独立评分。
