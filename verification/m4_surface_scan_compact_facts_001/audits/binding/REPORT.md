# 五次工程原件的来源、传输及关闭复核

这次只离线复核已完成的同一组五次观察，新增 Blender、产品进程、模型和业务 API 实验均为 0。1096 项断言通过，读取 516 个文件并保留其长度与 SHA256。断言数属于核验工作量，实际请求分母保持五次。

## 固定身份

产品提交 `452b44d2dcf231d6675bef54e568db0431a29261`，138 源聚合摘要 `4067c864c3db1ba586cd7179e6430db5acc4d71675b5295416d471632851a9f6`，wheel SHA256 `f71c299926ebb38b1c09a2ca9b26a90416810b2407e3b955a43502ad86a55792`。逐文件核候选 Git、构建提取源码、wheel 和隔离安装一致，并独立重算聚合摘要。普通安装入口和 RUNTIME_BINDING 字节匹配构建回执。

实际 initialize 及六条含启动的 request trace 均绑定同一安装源。Windows 归属证明记录 launcher PID 35288、runtime PID 18108，owned Blender PID 14372。其创建时间及父链符合原记录。工程 controller 按真实 INPUT_BINDINGS 的预记录摘要核当前字节，产品提交未纳入该 controller。

原配置、原资格 asset、private input.blend、固定 pose patch 和当前源字节均核对。安装前后保护回执与当前哈希一致。两份实际完整 BASE/EDIT 快照与已冻结资格快照逐字段一致，路径和 PID 字段按原合同独立处理。

## 五次普通 stdio 请求

普通完整工具目录及条件默认说明已核。实际 stdio 原始 TX/RX、单次 RPC 回执、独立请求文件、RESULTS 业务行、audit trace/observe 和宿主 WIRE/worker event 一一绑定。共四次元数据 RPC 与五次业务 RPC，没有额外业务重试。

| 请求 | 匹配 | 新 kernel | 宿主 capture | 正文 UTF-8 B | 编码 ns | 紧凑投影 ns |
| --- | --- | --- | --- | --- | --- | --- |
| base_default | 71 | 112 | 1 | 7911 | 954000 | 650600 |
| base_brief | 71 | 0 | 1 | 7911 | 934800 | 626800 |
| base_full | 71 | 0 | 1 | 34754 | 242500 | None |
| edit_default | 72 | 10 | 1 | 7912 | 933800 | 634700 |
| edit_full | 72 | 0 | 1 | 35209 | 246500 | None |

默认/brief 的完整正文包含对象表、列说明、状态与全局来源，均小于 10240 B。full 保留逐对见证结构。每次业务恰好一次宿主 capture，kernel 依次为 112/0/0/10/0，初始 measurement cache 为空。BASE 三次 binding 相同，EDIT 两次 binding 相同，pose 前后 binding 已变化。

投影 span 嵌套在 mcp.content_encode 中，表内两列耗时保留各自范围，不能相加为额外总耗时。宿主采集工作计数从实际协议响应解包后与 audit 的 acquisition_work 逐项对应。

## 外部 QA 和生命周期

宿主原始 RPC 共九次，其中业务 capture 五次，另有 BASE 快照、登记 pose、EDIT 快照和关闭各一次。四条外部记录请求合计 9240 B，响应合计 933137 B，独立于业务字节。close worker event 的 script status 仍为 unknown，但其单独 raw close response 为 closed，owned Popen 回收和退出码分别确认。

产品 launcher、加载 runtime、Blender 的关闭顺序及各自原回执已核。完整 RESULTS 写入关闭之后的外层时长为 **4.8629929 秒**，原期限为 590 秒。FINAL_TIMING 的完整关闭期限布尔为 true，accepted_success 为 true。RESULTS 内 passed 保留写入前检查范围，最终有效结果按 FINAL_TIMING。计时文件发布区间另列，其回执自身写入和物理 fsync 到盘未测。

## 范围与修正

RUNTIME_PROOF 的 before_stdin=true 是复用 helper 留下的标签，与真实元数据先后不符。原 scope 文本及单调时序表明，实际证明位于四次元数据之后、首次 QA 几何之前。原件原样保留，本复核按该可证范围解释。

机器可读更正在 `RUNTIME_PROOF_ERRATUM.json`。原 proof SHA256 为 `0fb9ae32c89e84791f80a8172f998beeae184b07299f49cdd8a040872f2e26a2`。最后 metadata 回执结束于 609994166469900 ns，proof 观察／完成分别为 609994171481800／609994181988800 ns，首次 QA 几何请求为 609994186694400 ns，首次业务 capture 为 609994278894500 ns。before_stdin 字段不作为证据。

历史进程内存没有重演，快照与终态检查对已回滚瞬时行为保留原观测范围。实际模型消费、provider 输入与完整任务收益仍属于后续验证。

核验器的探索失败已保存在 CHECKER_CORRECTIONS.json，包括未剥除宿主协议 marker 就解析 JSON、把工程 controller 当作产品提交成员，以及假设 acquisition/result 的 scope 字符串相同。修正为各自明确字段合同后通过，没有修改旧工程原件。

可使用既有 Python 的 `-I -B -X utf8` 运行本目录 verify_binding.py 复算 BINDING_RESULT.json。Agent Learning 仍未绑定，host epoch 为 5，需要宿主重连。
