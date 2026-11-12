# 全场扫描紧凑事实投递工程候选

2026-11-13。一个候选完成离线语义、隔离构建安装和五次普通 MCP 工程观察。五次均通过，完成 5、失败 0、未运行 0。BASE 的默认和 brief 正文为 **7,911 B**，编辑后的默认正文为 **7,912 B**，均满足固定基准 10 KiB 门。

## 固定身份

| 项目 | 候选身份 |
| --- | --- |
| 产品提交 | `452b44d2dcf231d6675bef54e568db0431a29261` |
| 138 源聚合 SHA256 | `4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6` |
| 隔离发行版本 | `9.7.2+m4.surface.scan.compact.r1` |
| wheel SHA256 | `f71c299926ebb38b1c09a2ca9b26a90416810b2407e3b955a43502ad86a55792` |
| 基线产品 | `c1cb2da32034e056a270384e691a2cde8dddbc0d` |
| 根计划提交 | `5c1a3fbf1b2894e6c1f8d8fa7d7914ea6018b411` |
| 根计划 SHA256 | `0c5b7b58873730b4b324c777bed3954a3cbf1a3d26b21c4b4add97a5cdb864d0` |

唯一产品改动位于 `human_eye_plugin/live_spatial_mcp.py`。SDK base version 与 implementation revision 常量沿用原值，发行版本及完整源摘要标识本候选。构建从固定 Git 提取源码，wheel、隔离安装与源码逐字绑定。现有桌面默认继续由原配置控制，候选安装位置与回执见 `installation/run_01/READY.json`。

## 已实现的展示合同

`surface_scan` 省略 `response_detail` 与显式 `brief` 共用一个纯投影。结果带 `display_encoding="surface-scan-task-table-v1"`，对象 ID 和名称在对象表内记录一次，匹配行保留可读名称、对象表索引、原始 `distance_m` 和派生 `distance_mm`。重复名称按索引恢复身份。

原始米值逐位保持。投影保留匹配顺序与成员、全部顶层状态、覆盖计数、未知项、来源范围、binding、delivery、trace 和权限。公共逐行 metadata 记录一次，差异按行索引合并，保留见证 unknown、原因、方法和未来字段。共同值使用严格 JSON 编码比较，布尔、数字零、signed zero 与字段缺失可分别恢复。

显式 full 继续交付原详细结构与见证坐标，它发起新的当前观察。跨请求组合核对场景与来源 binding。对象表只覆盖已交付匹配端点，当前 BASE 的 22 项端点表与 `coverage.objects=24` 分别表达各自范围。

省略 detail 的扫描输出结构发生兼容变化。旧 JSON 客户端需要识别 display encoding，或显式请求 full。普通工具说明和条件默认已同步。详细合同见 `COMPATIBILITY.md`。

## 离线语义和有限回归

最终 `semantics/attempts/run_03` 通过 180 个 unittest 方法，其中新增候选用例 24 个、既有相关回归 156 个，失败、错误和 skip 均为 0。测试覆盖 scan reducer、普通入口、OPT1 依赖、MCP、task/structure/segment 展示，以及 framing 和 publication isolation。

六个封存响应的 426 行以独立解码恢复对象 ID、名称、顺序和米制浮点位值，全部一致。显式 full 的文本逐字保持原 34,754 B。signed zero、阈值两侧相邻浮点、最小次正规、极大有限数、空集合、partial、unknown、上游截断、同名 Unicode、逐行差异和异常回退均有定向反例。故障化测试删除行、破坏索引、误换米值或将 partial 改成 complete，均被阻止。

极大毫米值使用精确十进制整数字符串。根补用独立高精度 Decimal 核验最大有限值、相邻大值及 `1e306` 的溢出展示，原始米值按位不变，派生字符串精确等于原值乘 1000。最小正数和 signed zero 保留。

另有 13 个实际 schema 正负例由本机已有 Python 3.14.7 / jsonschema 4.26.0 验证。产品与其余测试使用既有 Python 3.12.14。预设 181 方法中的一个旧 schema 方法未在 3.12 执行，其相同输入条件转入导出的实际 schema 验证并单列。35 个旧 segment 方法使用固定 SHA 的外部历史 fixture。依赖、二进制和 fixture 的来源在语义回执中记录。

## 五次实际工程观察

唯一 owned Blender 副本从原资格 BASE 启动，依次执行 default、brief、full。随后应用原登记的 `Obj_008` Z 位移 −0.00075 m，再执行 default、full。数据来自原资格精确真值，原文件继续保留。所有请求、错误和清理记录位于 `engineering/run_01/`。

| 顺序 | 状态与展示 | 匹配数 | 完整正文 B | 请求 ms | 新 kernel | 宿主采集 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | BASE default | 71 | 7,911 | 1761.1765 | 112 | 1 |
| 2 | BASE brief | 71 | 7,911 | 40.6833 | 0 | 1 |
| 3 | BASE full | 71 | 34,754 | 47.0880 | 0 | 1 |
| 4 | EDIT default | 72 | 7,912 | 159.8546 | 10 | 1 |
| 5 | EDIT full | 72 | 35,209 | 42.3963 | 0 | 1 |

每次独立核对全部 276 对处置、阈值成员、距离、身份和完整性。两次 full 共核 286 个表面见证点。同状态默认、brief 和 full 的原字段及匹配事实相同，trace 各自独立。姿态变化后 binding 更新，后续 full 与 EDIT default 的 binding 一致。

BASE 紧凑正文较同状态 full 减少约 **77.237%**，EDIT 减少约 **77.528%**。这组顺序含冷启动和缓存复用，请求耗时用于记录该次运行。正文差值没有转换成模型 token 或任务提速结论。

## 展示成本、采集和生命周期

| 请求 | 纯投影 span ms | 含原值校验及编码的展示 span ms |
| --- | --- | --- |
| BASE default | 0.6506 | 0.9540 |
| BASE brief | 0.6268 | 0.9348 |
| BASE full | — | 0.2425 |
| EDIT default | 0.6347 | 0.9338 |
| EDIT full | — | 0.2465 |

投影 span 嵌套于 `mcp.content_encode`，两者按各自口径记录。完整结果首先进行原严格 JSON 序列化，投影及其编码失败时保留详细交付。相关 deadline 和错误校验继续执行。

五次业务各发生一次宿主采集，五次 host 请求信封合计 104,520 B，响应尝试字节合计 538,172 B，发送完成状态逐项记录。业务之外另有 BASE 快照、登记姿态变更、EDIT 快照和关闭，共 4 次，连同业务合计 9 次宿主 RPC。额外 QA 采集单列，首次 measurement cache 为空，后续计算量符合 112／0／0／10／0。

完整工程会话为 **4.8629929 秒**，涵盖 owned 启动、五次请求、QA 验证、清理及最终业务记录写入关闭。最终关闭发生在原 590 秒期限内，权威成功值为 `FINAL_TIMING.accepted_success=true`。时间回执文件发布另列。隔离构建安装耗时 **4.0945007 秒**，前置协调、离线测试、复核及 Git 推送另属其他区间。

产品 launcher 与实际 runtime、原生后端均有独立关闭确认。保护检查记录配置、原资产及源码的原有字节，候选执行使用 owned 副本。该完整工程会话包含 QA 与启动工作，其口径写在 `FINAL_TIMING` 中。

## 失败、适配和未测项

首轮离线 181 方法中有 38 个 error，全部保留。其中 35 个为历史 fixture 缺失，2 个为验证解释器依赖缺失，1 个发现新投影异常未回退的真实缺口。展示异常回退在候选提交冻结前修复，最终语义测试通过。相关环境适配和原始回执见 `semantics/REPORT.md`。

根预提交检查曾将保留原字节的 CRLF 输入文档按默认规则报告为尾随空白，随后提交命令先于结果复核执行。根补以 `cr-at-eol` 检查该固定提交并通过，重新核源码和输入字节绑定，顺序失误保存在 `ROOT_PREPARATION_CHECK_HISTORY.json`。

根封存脚本初次使用了无效的 `utf8-sig` 编码别名，已改为 `utf-8-sig` 并重新通过全部封存检查，失败记录一并保留。

工程 runner 的 `RUNTIME_PROOF.before_stdin=true` 沿用了通用证明函数的字段。实际归属证明在四次元数据交互之后、首次几何观察之前，scope 文本和单调时间记录支持这个范围。该布尔标签错误，原件继续封存，按时界与更正说明解释，不能据此宣称证明发生在首次 stdin 之前。

本批新增模型消费者和模型 API 调用均为 0。模型内部有效输入、截断、实际 token、往返、任务总成本和重算行为收益留后续同期消费验收。10 KiB 门覆盖当前固定基准，其他规模与外部 JSON 客户端仍按各自输入验收。Agent Learning 仍未绑定，需要宿主重连，任务同步状态另记。

## 交付材料

`CANDIDATE_SOURCE.json`、安装回执、普通 stdio 原件及源摘要对应同一候选。`postcheck.py` 离线执行 2,334 项根检查，核源码、安装、语义回执、五次工程门及原六格 1,974 项封存内容。检查数量表示复核工作量，工程实验分母保持五次观察。

同五原件的质量复核另通过 3,680 项检查，使用独立有理数表面算法核 286 个见证点。来源与生命周期复核通过 1,096 项检查，绑定 138 源、安装、五次 stdio、全部宿主信封和关闭时界。材料分别位于 `audits/quality/` 与 `audits/binding/`。

`COMPATIBILITY.md` 说明结构变化，`semantics/` 保留测试与环境证据，`engineering/` 保留 runner、原请求响应和清理，`installation/` 保留固定构建与安装来源。完成后交管理员独立复审，再由管理员冻结后续模型消费计划。
