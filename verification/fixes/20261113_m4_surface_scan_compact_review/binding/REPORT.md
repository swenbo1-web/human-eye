# COMPACT-FACTS-001：独立来源、安装、请求与生命周期复核

结论：本范围通过，没有发现阻止候选进入同期消费者对照的来源或请求遗漏。核验对象为产品 `452b44d2dcf231d6675bef54e568db0431a29261`、证据 `6ab4e53409e539c71a377f48708f2f8725db6dde`。本轮独立运行 `check_binding.py`，最终 **1,914 项检查通过、0 项失败，642 个实际读取输入**；这是离线核验工作量，实验分母仍为原有 **5 次工程观察、9 次宿主 RPC**。本轮没有运行产品、Blender、模型或 API，没有修改作者工作树或 Git。

## 本轮实际核对与复用

| 范围 | 本轮实际验证 |
| --- | --- |
| 证据封存 | 本批 329 个清单成员及清单自身逐字对应固定证据 Git blob；成员集合、大小、SHA256、总字节一致，作者树 HEAD 固定且前后干净。 |
| 产品来源 | 独立重算 138 源聚合摘要 `4067c864…851a9f6`；每个成员与产品 Git、构建提取源码、wheel、当前隔离安装逐字一致；基线至候选只有 `live_spatial_mcp.py` 改变，候选至证据提交无产品源变化。 |
| wheel 与入口 | wheel SHA256 `f71c2999…a55792`；145 个 wheel 成员、RECORD 哈希及安装字节一致。入口模板按固定版本、摘要、138 数量生成，admin 仅替换入口摘要，复建字节一致；RUNTIME_BINDING 路径、身份与完整源清单一致。 |
| 实际加载记录 | 隔离 identity 原件、实际 initialize、11 条 audit 的 PID/build/source 身份、普通启动命令与独占端口一致。实际首个宿主代码包内六份压缩源逐一解码后，准确对应候选源文件。 |
| 请求绑定 | 九份 stdio TX/RX 与回执逐字计量；四次 metadata、五次 tools/call，没有额外业务重试。独立请求文件、响应、RESULTS、audit、trace、worker event 与 WIRE 一一对应。 |
| 保护及来源 | 安装前四个保护文件摘要与当前文件一致，安装后记录覆盖同四项；160 个实际输入绑定全部核对。原资产与独占副本字节一致，BASE/EDIT 完整快照除预先声明的路径/PID 外与资格快照相同。 |
| 生命周期 | launcher 35288、实际 runtime 18108、Blender 14372 分开核对。launcher Popen 回收、runtime retained handle 退出、Blender Popen 回收及最终指纹均有相应原件。 |

旧消费者 1,974 项封存没有再次逐文件复跑。已核旧 manifest SHA256 `1ead579f…ce2d` 和根 QUALITY_SEAL `1a205c05…942f` 未变，复用根 `91cce49c` 的既有审核。作者报告中的 2,334 / 3,680 / 1,096 不计入本轮执行数，也未运行作者核验脚本。本轮不负责重复几何真值评分，交由根的语义/质量复核合并判断。

## 请求分母与实际边界

| 业务 | 宿主序号 | 正文 UTF-8 B | 新 kernel |
| --- | ---: | ---: | ---: |
| BASE default | 2 | 7,911 | 112 |
| BASE brief | 3 | 7,911 | 0 |
| BASE full | 4 | 34,754 | 0 |
| EDIT default | 7 | 7,912 | 10 |
| EDIT full | 8 | 35,209 | 0 |

辅助宿主调用准确为 BASE 快照 1、登记的 `qa_advance` 5、EDIT 快照 6、关闭 9。业务宿主信封合计 104,520 B 请求、538,172 B 响应；各项发送完成记录与实际 WIRE 长度一致。五次各一次采集，跨状态 binding 变化，同状态 binding 一致。第一轮 measurement cache 为空，首业务前 resident 为空；此前 QA 快照明确存在，不能称为操作系统冷缓存试验。

候选提交时间 2026-11-13 00:32:01 +08:00，先于工程输入准备 00:34:19.734 +08:00。controller 自身并非产品候选成员，但其原 INPUT_BINDINGS 摘要与固定证据提交/current bytes 一致。后续消费者对照应固定同样的准备与计时口径。

## RuntimeProof 错标的独立判定

原 `before_stdin=true` 无效，不能用于“任何 stdin 前已核验”的结论。原证明 SHA256 与更正文件一致，且时序由原件独立重建：

- 最后 metadata RPC 结束：609994166469900 ns。
- 归属证明观察／完成：609994171481800 / 609994181988800 ns。
- 首 QA 几何请求：609994186694400 ns。
- 首业务 host capture：609994278894500 ns。

这证明其实际范围是“metadata 完成后、首次 QA 和业务几何前的 launcher/runtime 归属证明”。父链 PID、进程创建时间、runtime 的实际 audit PID 一致。根应保留更正，不沿用错误布尔标签。此错标不推翻现有五次业务的同源身份链。

## 关闭、未知和保护范围

最终写入关闭的完整区间独立重算为 4,862,992,900 ns，包含启动、五次观察、QA、清理和 RESULTS 写入关闭；全部早于原 590 秒期限。它不是模型任务时间，也不是 compact/full 的随机配对性能试验。计时回执发布及物理 fsync 不在该已测范围。

宿主关闭 worker event 的 `status=unknown` 原样保留。单独 close 的原始响应为 `closed`，最终指纹记录与 launcher-owned Popen 回收/退出码 0 共同证明正常关闭；不能把通用 event 改写成 completed。runtime 自身另有 retained Windows handle 退出码 0，不能用 launcher 退出代替。

保护证据范围是已记录代码、原资产/配置摘要及几何终态；未重演历史进程内存，不能证明不存在已撤销的瞬时操作。没有本轮模型消费者，所以 provider 实际输入、token、费用、模型信任/重算与完整任务收益仍未测。

## 本轮核验器修正记录

`ATTEMPT_01.json`、`ATTEMPT_02.json` 保留最初失败，不属于产品实验失败：第一次误把生成入口当原模板逐字相等、误读保护后置文件为摘要映射，并错取 audit 的 source 字段；第二次误将 Windows 文本副本的 CRLF 和线缆 LF 直接比较，同时把 QA 类型写成 `qa_advance_pose`。现按原 installer 的登记替换复建入口、按实际字段与原 wire/event 哈希核对。文本副本只做 CRLF→LF 后对应 wire，Git/manifest/source/wheel 原字节从未归一化。最终检查及输入哈希在 `RESULTS.json`、`CHECKS.json`、`INPUTS.json`，详见 `SELF_ISSUES.json`。

AL 自身句柄 `eedb2e6559c7410dbf9007536acc04f1` 的旧 assignment 显示 current=false；未借根句柄、未覆盖父任务。此次范围以根对 COMPACT-FACTS-001 的直接委派记录。本轮产物仅写入指定根复核 binding 目录。
