# MCP-ENTRY-001：部分验证，完整验收未完成

状态 **BLOCKED（QA 驱动错误导致 S 序列提前结束）**。已取得隔离已安装生产服务的真实 stdio 初始化、tools/list、一次正确参数拒绝和一次 G mixed 成功返回；S 的同连接 ping 与合法 surface_proximity 未运行，不能宣称完整通过。

源树 [perf000_scene_tool.py](../../../../perf000_scene_tool.py) 仅新增 task 模式 help：query-literal 只放 mode/objects/requested_facts，文本 CLI 自动在外层设置 include_image=false，legacy query 模式继续支持。解析和校验未改。实际 [observe --help](observe_help.stdout.bin) 退出0；[正确 MCP 参数示例](CORRECT_CALL_EXAMPLE.json) 来自 G 的实际发送帧。

## 真实分母与错误

- 两个 owned 会话实际均已启动；原计划3次 tools/call，实际2次：**1成功、1预期拒绝、1未运行**。另 S 的 ping 未运行。
- S 原 `04.rx.bin` 正确返回 isError，错误为 `task query requires only mode, objects and requested_facts`。我的 QA 断言错误要求其中包含 `include_image`，因而在拒绝已发生后抛错并进入 finally，提前关闭 stdio 和 worker。不是产品校验缺陷。原失败 [S/RESULT.json](S/RESULT.json)、初版驱动、首次 PROCESS/RESULT/日志和原帧完整保留。
- 该拒绝前后没有执行几何 worker；S 的唯一 worker 事件发生于 stdio 结束后的 owner close。离线根据原帧确认预期拒绝，不重发该调用或重写原失败计数。
- 仅修正 QA 断言并继续原未启动的 G 会话，没有重开 S 或重试任何已用调用。G 正确请求 surface_proximity+solid_relation，实际返回 partial：距离0、共同见证、方向 not_applicable、实体 unknown/unsupported_solid_geometry；当前来源和 trace 均保留。G 有1次实际 selected capture。

汇总见 [FINAL_RESULT.json](FINAL_RESULT.json)，原帧与时间在各会话 `01..04.tx.bin/rx.bin` 及 RESULT.frames。初始化通知没有响应；实际 tools/list 的原返回与提取的 ACTUAL_OBSERVE_TOOL 均保存。共8发送帧、6预期响应帧；协议字节不是模型 token。本批0模型消费者、图片、资产构造/更新、安装或API调用。

## 入口、源码和回收

`launch_verified.py` 先按既有 B 身份核131源并冻结字节，以原 verified_source_loader.install 和其已支持的 namespace 接入，再调用未改 production_server.main，最终进入原 run_stdio_mcp_server。bootstrap 本身是薄受控 QA 入口，不是正式 release 启动器。原 loader 负责实际引擎导入的源码执行见证，未以 -B 或路径检查替代它；退出记录分别为56/58个已加载引擎模块的执行/namespace见证及 compatible 的 bound-generation 检查。

两个 LiveSpatialService 均为 production_mode，连接各自 NativeSession 的 **worker execute_code 地址**，未经过 broker；因此按真实 stdio 帧与 WORKER_EVENTS 计量，不冒称 broker 公开调用账本。固定 B 131源 `fb5a4485c935512c1521b160c55e6034a30ae8177e2662b6a132fec5d85a4509`、既有隔离安装和五个已安装 helper 未改。源码/旧证据 Git差异与字节检查见 [SOURCE_CHECK.json](SOURCE_CHECK.json)。

两个 stdio 进程均关闭 stdin 后 EOF 正常退出0，两个原 owner 均回收 worker、退出0，源资产及受保护文件未变，无强制清理。原绝对 worker 期限各180秒；成功请求保持正常20秒预算。进程核对见 [CLEANUP.json](CLEANUP.json)。

实际 tools/list 有 surface_proximity 及1214字节原说明，include_image 为外层参数。此处仅验证隔离真实 MCP 交付；桌面宿主是否注册新版、模型看到并选择新 schema、默认切换均未测。费用、模型 usage 未测，不把帧字节写成模型 token。

本批绝对实施截止10:01:37Z，路线10:16:37Z不重置。未扩修产品、source guard 或通用 MCP 架构，未增加会话/调用刷通过。新索引见 [EVIDENCE_INDEX.json](EVIDENCE_INDEX.json)。提交后一次 BLOCKED 回报，由根独立深审。
