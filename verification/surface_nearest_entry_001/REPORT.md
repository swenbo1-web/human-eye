# SURFACE-NEAREST-ENTRY-001

COMPLETE。既有 human_eye_scene_observe 已接入明确的 `query.mode="surface_nearest"`；真实生产 connector 返回完整候选包的缺口已关闭。唯一产品候选为 `17db41c481397965a9bae3f4571c59a5a80939c9`，131 源身份为 `01c296b5dac9c8733670b7b82886fe774fb6e50222d1b935d6ac27efa04760de`，revision `v24-surface-nearest-observe-20261107`。

从已接受的 `497a9dfb88e7ca114bc6706f40eb7e513da82062` 开始，仅改 query_policy、live_service、live_spatial_mcp、runtime_identity 四个产品文件。host、connector、协议、M3、normalizer 和 cache 字节均保持基线。未增加产品模块、部署或默认配置。

入口要求显式 session_id、已知 focal_id、include_image=false，query 只能有 mode；拒绝 reference、goal、scene_delta 和图片组合。沿用现有只读上下文、锁、loaded-generation 来源校验、父请求期限和 pair cache。一次候选 capture 进入已接受 summarizer，名称只来自同包 retained meshes；complete 返回全局 nearest，partial 仅返回 best_known 并列明未决对象及原因。保留距离与 witness/direction 未知的独立说明。模型收到单份紧凑 JSON 文本，无 geometry、私有精确键、排除长 ID 清单或重复 structuredContent。旧 nearest/top1/task 及默认 include_image 不变。

## 验证

`offline_run_02` 使用原 verified_source_loader 从已冻结的131源实际执行，guard.verify_loaded=true；12组新入口测试加87项回归，共99项通过。覆盖 mode/schema、预先参数拒绝、真实 fake-bpy host 捕获到原 summarizer、当前名称、并列/partial/unknown、cache hit、来源拒绝、捕获前后和编码发布期限、只读 history、旧 nearest/top1/task。原外部 CLI help 子进程测试被明确排除，因为其不能共享本次字节 loader。fake-bpy 不作为真实 Blender 证据。

唯一真实批次于 2026-11-07T16:06:29.081235Z 启动，16:06:34.244811Z 完成：1个原 neutral NativeSession、1个持久 stdio MCP 进程、3次产品 capture、6次准备/恢复 control 加 close，总10 RPC。原600秒绝对期限未延长，0重试、0第二会话。initialize、initialized notification、tools/list、一次坏参数拒绝、ping 和3次正常调用共8个 stdio 帧，全部计费为传输字节。

真实链为 stdio → 既有 LiveService → 原 BlenderMCPHost socket/execute_code → 实际 bpy 原 host 方法 → 原生产响应解析 → 原 summarizer → MCP。原始 socket RX 的3包完整包含 capture/coverage/binding，总紧凑 packet JSON 14,038字节；worker 执行 code SHA、stdout、socket nonce/envelope 和返回正文逐项核对一致。没有共享 CAPTURE 文件补包，没有修改 connector._request。审计脚本只读取已产生证据，不新增产品调用。

| 私有三态 | 实际公开结果 | 覆盖（有效/排除/未决） |
| --- | --- | --- |
| baseline Far 晚面退化且严格排除 | complete，M4_Near 2m | 1 / 1 / 0 |
| Far 顶点3变为 (.25,.25,.25) | complete，M4_Far_00 .25m | 2 / 0 / 0 |
| Far 晚面 x=1、y=2/3/4，仍共线 | partial，best_known M4_Near 2m，全局距离为空；Far 原因 surface_degenerate_triangle | 1 / 0 / 1 |

第三态独立几何距离 Far sqrt(2)<Near2，不能报 Near 为全局最近；该要求实际满足。QA 采用一次性 bpy profile fixture，在原 capture 函数 call 前修改私有网格、return/异常展开时恢复，并通过独立 restore RPC finally 再恢复；未替换产品方法或 neutral helper。profile 正常/异常的6个 stdlib standin 仿真另存，只证明夹具逻辑。

## 实际成本

| 边界 | TX 字节 | RX 字节 |
| --- | ---: | ---: |
| 3个生产 connector socket | 11,562 | 15,550 |
| 7个 QA control/close RPC | 141,875 | 14,980 |
| 全10 RPC | 153,437 | 30,530 |
| 全 stdio（含 schema、拒绝等） | 1,504 | 26,687 |

三次结果正文合计4,138 UTF-8字节；相应完整 JSON-RPC 回复合计4,772字节，0图片。各层含相同数据跨边界传递，不将它们相加冒充单次模型输出。原始 TX/RX 与每次 wall 在 qa_prepare/run_01 保存。

完整 controller 子进程（含解释器启动、来源检查、host启动、调用、清理）5.1633576秒；controller 主测量段4.5189626秒；其中 owned host startup3.1073119秒，持久 stdio 生命周期1.11609秒。三个正常 stdio调用合计165.075毫秒。QA prepare 的观察墙钟5.0327009秒，另列 PREPARE_COMMAND.json，不混为产品算法速度。

实际5次 pair、3次 kernel、2次 _nearest、3次 rank、2次 cache hit；实际展开8个 mesh、30个 vertex、10个 face；候选目录每态3对象。QA oracle12次扫描、144个顶点记录（每记录同时构造 local/world 坐标），不计为产品捕获；fixture/profile/cost attribution 均标为 QA 成本。profile计数仅归因匹配回调部分，不含忽略事件过滤或 fixture 写盘；完整所有开销仍包含在上述 RPC/stdio/command 墙钟。

## 保留失败与清理

首轮 offline_run_01 因测试引用不存在的 validate_tool_arguments 而在导入阶段失败，0测试方法；改为真实 _validate_arguments 后只重跑离线，产品身份未变。原失败 RESULTS、原测试字节和说明保留。QA准备另有两次 PATH python 指向 WindowsApps stub 的 exit1，0产品导入/Blender/RPC；换为既有工程 venv 后语法与仿真通过。独立只读复核曾用过宽 substring 误识别 coverage.strictly_excluded，修正该审计断言后通过，未重跑产品或真实批次。

Native worker9个 execute_code 均 completed、终态检查通过，close 事件保留原 unknown 状态；独立 closed response、WORKER_CLOSED 和 owner wait/reap exit0 共同确认关闭。Blender PID12256、stdio PID13240、controller PID24856 已结束；poison=false，最终几何 fingerprint=初始 fingerprint。原资产、私有 input.blend、helper 和131产品源哈希保持一致；0保存原资产、0渲染，state sessions/history frames 均0。默认端口、共享GUI和正式release未使用。

未新增模型消费者、外部付费 API、Google key、503 或正式性能 A/B。真实 token、金额及模型收益未测；已知 ID 由预登记夹具提供，本批未计入未来消费者的 ID 发现成本。这三态只证明入口和实际交付成本。

证据索引 EVIDENCE_INDEX.json 排除自身；重复 engine/source 快照和 input.blend 已由 ZIP 保存精确字节，未重复提交展开目录。原 helper 和私有输入也封入 QA ZIP。索引记录本 turn 的 host id/start epoch 和截至封存的经过时间；完整最终 turn duration 应在交付后读取 host completedAt，不能用5.163秒真实批次替代整轮成本。授权任务书和根复核的 SHA 保存在 SOURCE_ASSIGNMENT.json。
