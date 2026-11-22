# 区域发现简报客户端试验

**本轮集成资格未通过。** 唯一一次冻结试验启动了 A 的实装 MCP，实装身份与原工具目录核对成功。随后原图设备加载失败，A、B 的 Owner 均未开始接收业务。集成业务请求与产品业务派发均为 0。实装 MCP 正常结束，原失败工件及退出收据已归档。未重跑、未启动模型。 [失败原件](evidence/TRIAL_FAILURE.json) · [实装退出](evidence/INTEGRATED_STOCK_CLOSE.json)

## 本地已验证的两层

**CLI 注册层。** 实际 Codex CLI `0.152.1` 通过本批实际 thin stdio 和独立本地回放后端注册了六项历史工具。六个定义完整保留，`human_eye_scene_observe` 唯一增量是追加 `allOf/if/then` 条件。条件只在 `query.mode=active_observation` 且存在 `query.region_task` 时限制 `response_detail` 为 `brief` 或省略。声明增加 **218 B**。目录查询 100.524 ms，RPC 回包 24,020 B。15 个离线条件边界检查覆盖全量、缺省、简报、非目标模式和错误形状。CLI 目录探测结束后，app-server 退出码为 0，Windows 持有的句柄确认同一 thin 子进程退出码为 1。当次没有 thin 正常 EOF 收据。 [真实注册与退出](evidence/STARTUP_AND_REGISTRY_REVIEW.json)

**实装 MCP 投影层。** 固定 `8cf3fabc`、143 源 `65bd1ec8`、wheel `97053290`。在真实实装 stdio 上以封存生产者和原图重放，P2、P3 的全量正文 **335,181／335,179 B** 与各自原文逐字节相等。显式简报和省略参数均为 **7,521 B**，各保留原顺序的三张 PNG、三片区域、两份局部完整见证、六向具名挡片、当轮绑定与同名 SCENE 的不同作用域。固定的三个 CLI 工具头与两个保全阶段合计 12/12。六个同长度的来源、作用域、图像或未知篡改反例均被正确拒绝。占比差只适用于实际历史回包，尚无正式 token 数据。 [黄金证据与序列化耗时](evidence/GOLDEN_REFERENCE.json) · [实装 stdio 原件和数据](evidence/PRODUCT_DIRECT_REVIEW.json)

实装直连还保留选区量测 full、选区无图、遮挡未知、无图预测和其他观察。选区量测 full 会重新生成 `request_id` 和 `trace_id`，其余值相符。部分兼容控制使用旧封存生产者与当前投影。真实实装的过期预算请求返回 `live_request_expired`，零图并正常退出。 [兼容及实装预算收据](evidence/PRODUCT_DIRECT_REVIEW.json)

## 未完成的集成证据

本批桥包装漏导出保留设备依赖的 `SOURCE_REGION`，`frame_device.py` 的导入在第一项报错。静态核对还发现同一导入行所需的 `load` 同样缺失。独立 CLI 原型的后端不加载该设备，产品直连预飞也不经过这一层，因此两项预飞都未覆盖这次启动失配。完整试验仍缺 B 对明确 full 的拒绝与零派发、下一请求恢复、相同视角名的公共原图回读、Owner 尝试预算以及逐请求额外开销。生产 MCP 的诊断能力保留，未改写任何请求。提供方对条件的支持、模型自然调用及费用均未观测。 [分层结论及分母](evidence/STARTUP_AND_REGISTRY_REVIEW.json)

历史 `f56108e5` 的六个正式槽和其综合未通过判定保持。当前冻结 `739493875`，285 项输入，SHA-256 `5a2a91b24b6415d520c75a35e4f24fd5bba95595c0c919bd62b87013326802ff`。本轮产品差分、构建安装、配置切换、场景改动、Blender、模型、构图、额外 API、Google 和付费均为 0。两项独立通过与集成失败分别保留。 [输入冻结](FROZEN.json) · [原件索引](RAW_INDEX.json) · [原始线包](ORIGINAL_RUNTIME.zip)
