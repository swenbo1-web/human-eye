# 区域发现简报客户端恢复

**恢复接线预飞通过，唯一一次正式本地资格仍未通过。** `SOURCE_REGION` 和 `load` 已从原桥透传，恢复批两臂均实际成功装配 ReplayRuntime、原 FrameDevice、Owner 和原装 MCP。QA 的 Codex CLI 0.152.1 经真实 thin 向 Owner 取回了全部六项原定义。随后探测器无法取得该次 CLI thin 的 Windows 进程句柄，关闭取证未达门槛。正式 QB CLI 注册、两臂业务和辅助 P2 回放均未运行。 [预飞收据](evidence/PREFLIGHT.json) · [正式原始失败与闭槽核验](evidence/FORMAL_FAILURE_REVIEW.json)

## 真实装配预飞

先用固定解释器的新进程复现原 `SOURCE_REGION` 导入失败，旧根保持只读。恢复预飞使用与正式相同的 ReplayRuntime、Owner、thin 与实装 stdio。A 发送 7 次业务尝试，7 次派发实装。B 经 thin 发送 13 次业务尝试，8 次派发实装。B 明确给出 `full` 或 `null` 时均返回原格式参数错误，无下游请求，也不改写参数。其后简报以及普通工具请求均成功。A 的原 `full` 可原样交付，B 显式简报和省略参数逐字节相同。六项兼容对照通过，选区量测 full 仅允许请求追踪的两个新 ID 变化。其他模式、无图预测及遮挡未知延续原投影与证据。 [逐请求预飞线包和耗时](evidence/PREFLIGHT_WIRE_REVIEW.json)

P3 原生产者在预飞中交付 **335,179 B** 全量正文，显式简报与省略参数均为 **7,521 B**，各保留同序 3 张原 PNG，共 8,671 B。正文下降约 **97.76%**。黄金对照核对三个候选、两个局部完整见证、六向具名挡片、当轮来源及固定 CLI 6/6 文字与图片保全。两个 `SCENE` 分别绑定全场与局部引用，公共 `read_images` 实际交付各自原 PNG，另交付原 LEFT。没有新增构图。原批独立验证的 P2 结果保持，恢复批正式辅助 P2 槽未运行。 [预飞原图作用域与原文核对](evidence/PREFLIGHT_WIRE_REVIEW.json)

预飞中第 13 次 thin 尝试在到达 Owner 前拒绝。随后用独立的实际 loopback 调用把第 13 次送达 Owner，也得到原预算错误，且零实装派发。两臂的预飞业务 thin 均留下正常 EOF，实装 MCP 均正常退出，Owner 均确认关闭。 [两层预算与关闭](evidence/PREFLIGHT.json) · [原始线包](ORIGINAL_RUNTIME.zip)

## 正式停止位置与分层开销

正式试验 1 次，0 次通过，0 次替补。两套 Owner 的实际目录唯一差异为原条件增加 **218 B**，每臂原图设备均注册 3 个独立原图引用。QA 的实际 CLI 注册回包为 **23,817 B**，目录内容与 QA Owner 精确相同。该次 tools/list 的 thin 输入至 stdout 刷出为 **2.878 ms**。app-server 退出 0，读线程和监控线程均结束。监控器的 `OpenProcess` 返回空句柄，原实现未记 Windows 错误码。该次 thin 有 `STARTED` 收据，缺正常 EOF 及可绑定的退出码。两臂实装 MCP 各退出 0，Owner 均正常关闭。正式业务与产品观察派发均为 0，未生成正式业务成本。 [正式注册和进程原件](evidence/FORMAL_FAILURE_REVIEW.json)

预飞已测 B 的 10 次实际条件检查，范围 **0.5–2.1 µs**，中位 **1.0 µs**。A 的一次 full 外层／实装往返为 **71.508 / 34.517 ms**，B 的一次 brief 为 **51.611 / 19.323 ms**，省略参数为 **24.719 / 16.589 ms**。相应 full 与简报的单次实装投影和图像编码分别约 **9.759 ms**、**7.501–7.507 ms**。这些是单次预飞样本，传输和编码时钟有嵌套。正式 QB 的真实 CLI 注册、提供方条件支持、自然模型采用及 token 收益未测。 [预飞原始开销](evidence/PREFLIGHT_WIRE_REVIEW.json)

原批 `6778775f3` 的 0/1、A 退出和 B 未开保持。恢复冻结 `f7db1dd00` 包含 835 项输入，SHA-256 `7d28244640492fd9550701f05202384f3da707564a586dde57f6244f13b18abc`。产品 `8cf3fabc`、143 源 `65bd1ec8`、wheel `97053290`，正式历史 `f56108e5` 原样保留。产品改动、构建安装、默认配置改动、场景改动、Blender、模型、构图、额外 API、Google 和费用均为零。 [冻结](FROZEN.json) · [原件索引](RAW_INDEX.json)
