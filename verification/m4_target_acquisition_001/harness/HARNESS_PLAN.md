# 目标采集工程接线与固定对照

本框架仅由根执行。子代理完成静态代码和来源准备，新增 Blender 启动及 raster 均为 0。权威计划 SHA 为 `fd82d81865574f9c9401f82f7cfa9dd2c856f6ef3fb2ccd0cb21b9b75eaca43b`。

## 输入冻结

原始文件、旧 INPUTS 与 BASELINE_FROZEN、派生规则和目标在 fixtures/INPUT_PLAN.json 中固定。该文件 SHA 为 `64098d18be20d56a88e6e73f2a00d893eb78985d87da65d670992ba0c376813a`。

- peripheral 保持 14 对象、3474 顶点、6146 多边形，目标固定 M4_Far_00。文件仅按字节复制。
- focal_only 从固定 simple_boxes 的 owned 副本删除其他对象，保留 M4_Focal 的原局部点、面、矩阵、单位及保存帧。
- rack 按固定 rational JSON 原顺序创建全部 12 对象，保持点、三角面、单位和布局，目标为 LowerRearUnit。每个输入点必须能由 binary32 精确表示。

一个根启动的 Blender builder 完成两个派生文件，启动计入总额。builder 不导入产品、不构造图片、不修改原件。ASSETS.json 固定派生文件实际 SHA 和 geometry 文件 SHA。资产覆盖是三个有限工程输入。

## 普通入口与时间边界

A 与 B 使用各自已安装的真实 LiveSpatialService 和标准 run_stdio_mcp_server。算法、capture、准备器和 renderer 的 monkeypatch 数为 0。受控 bootstrap 校验 source_manifest 后加载产品，MCP 子进程使用 binding 中的 dependency_root。实际 Python、NumPy 与 Pillow 位置和版本保存在每槽 io_audit/RUNTIME.json。

标准 server 的 input_stream/output_stream 扩展点承载纯 I/O 审计，原始请求与回复字节照常转发。业务连续窗口起于完整请求读取完成，止于原 stdout flush 完成。该窗口包括输入审计解析、预算预留、首次宿主源码传输、全部产品处理及实际回复。它不包含回复后的预算结算。

完整会话起于控制器首次来源核查之前，包含 owned Blender 启动、MCP 启动、元数据核查、业务请求、回复后预算结算、两个持有进程的退出与清理。启动前来源核查和清理不会从窗口中扣除。事后只读 raw wire 解码、来源绑定与独立评分各自单列，嵌套子段不相加。

公共 request_budget_s 和 Blender timeout_s 固定为 30 秒，其原始已接受 M2 config 路径及 SHA 已存 INPUT_PLAN。owned lifecycle 最多 600 秒，用于启动和清理，公共请求期限持续保持 30 秒。

元数据仅 initialize、initialized、tools/list、ping，之后检查宿主 WORKER_EVENTS 为空，避免隐含几何预热。源验证、实际进程身份和退出证明沿既有接线。

## 固定公开请求

每个正式槽只有一条 human_eye_scene_observe 请求，query.mode 为 active_observation，objects 为包含指定目标 name 的单元素数组，include_image 为 true，response_detail 省略。session_id 和请求 ID 在 A/B 间相同。

新目标功能 A 先全采，B 才选择性采集。A 的实际 excluded_count 为 0 属于全采定义。主输入是否具有可排除几何，需要根据同相机粗界资格或 B 的实际路径确认。目标 unsupported、没有完整可读见证或没有可实现的排除机会应记录 not_realized，保留原目标、布局及相机，停止正式性能矩阵。

资格中的 full 诊断、默认 brief 无 fallback、include_image=false、未变图像复用及旧全场入口分别登记实际请求。run_case 的 passed 表示来源、传输和生命周期检查完成，质量状态始终由独立验收决定，公开业务错误保持原件。

## 持久化总账

全部 owned Blender 启动尝试上限 24，包含资产 builder、失败及修复重验。资格 raster 上限 48，正式上限 72，总上限 120。每个图像请求按有限六视图预留最多 6 次，预留量和实际构造次数分列。

公开回复完成后，使用产品原有 active_observation_render_attempt 事件结算。成功请求或有同步失败完成事件的请求可给出实际次数。仅有已证实未发生的预留量可以释放。已构造后失败的尝试持续计数，未确认结果保留原预留上界。进程被中断时 claim 仍留在磁盘，不依赖内存队列。账本采用内核文件锁和独占 claim/settlement 文件，进程退出自动释放锁。

预算操作属于实验接线开销，两臂相同。不能把 reserve=6 写成 actual=6，也不能将 unknown 上界冒充成功构造。阶段额度独立，资格无法借用正式份额。

## 固定一次正式顺序

peripheral 及 focal_only 各执行 A1、B1、B2、A2、A3、B3，共 12 槽。每槽 fresh owned Blender 与 fresh MCP，保持输入、公开请求、图像交付、依赖及配置相同。rack 只参与资格遮挡质量核查。

matrix 需要根封存的准入文件绑定 A/B source SHA、ASSETS 文件 SHA 和资格证据 pins。开始前检查余量，并独占创建整批 FORMAL_ONCE.json。每槽派发一次，失败保留，重试与替补均为 0。不可派发的剩余槽明确列为未运行。

质量先通过。peripheral 三对业务时间比中位数 B/A 不超过 0.90，至少两对更快，完整会话中位 B 不高于 A。focal_only 业务时间比中位数不超过 1.05，质量保持。matrix 只输出工程时间事实，独立质量仍需验收后由根决定准入。

## 来源与像素对照

继承的 NativeSession 保存原 TCP 请求与响应、宿主工作事件、临时资源数组计数及原始 source bootstrap。事后静态解码只接受真实 HUMAN_EYE_BLENDER_MCP 标记回包。对实际传输的压缩源码解压求 SHA，并核对当前安装 manifest。

每槽 retained capture 逐对象核对固定资产局部点、矩阵、单位和源面顺序，再确认当前宿主对象实例。通过后才生成资产 object_id 顺序与原全局面偏移对应表。不同 fresh 会话的 instance 与 document_epoch 保持原值，不要求跨槽相等。缺少资源、局部顺序不符或来源不一致直接保留错误。

OWNER_BINDING.json 提供已核准的 asset_manifest、source_proof 和实际 capture 路径。公开 brief、图片块、原 PNG/NPZ、actualcamera plan 和 view classification 审计供独立质量模块核验。RGB/depth 先比实际数组，owner/triangle IDs 在上述源核验后按原资产对应关系归一。无法公开取得的子阶段标为 unknown，不能用另一次 observe 来补正式分段。

本批实验模型消费者、Google/API 调用均为 0。字节事实不换算为模型 token 收益。协调与审核未暴露的模型费用保持未测。
