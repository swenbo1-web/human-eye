# SPATIAL-TASK-ENTRY-001

专用只读任务入口已完成本地离线验收，待根深审，未部署或启动消费者。产品提交 `990c9f7eb3a58c10aa1a566872adc62a8f373e6b`，起点干净 `f5f22371b05ffaeee93350e9111b8df4f8e8c245`。131源摘要 `3b424a7f26abf614949513178e3c295b1658928d6f0eed9234409f818e2e6ec1`，逐一核验 Git blob=磁盘源字节。

仅改 live_spatial_mcp.py、production_server.py 和 live_service.py 一条错误文字。现有 server、stdio 和两个 main 支持 keyword-only `spatial_task_only=False`；两个 CLI 均显式支持 `--spatial-task-only`。默认仍为原四工具，专用模式只公布 `human_eye_spatial_relations`，且在分派前拒绝所有未公布工具（包括 transform/clearance）；默认模式也拒绝新 alias。demo 与专用模式组合明确报错。没有 profile 注册器、配置体系、新服务/模块或部署改动。

新工具只收 target、1..3 candidates、可选 include_aabb（严格 boolean、默认 false），沿用 name OR id 选择器。内部固定 task、closed_solid_relation＋surface_proximity、可选 aabb 和 include_image=false，一次调用公开 service.observe；不递归调用工具、不绕过包装或新造结果。原 task_query 紧凑编码、当前绑定、unknown/完整性、精确并列、缓存与预算保持。trace 映射为 mcp.observe，禁图标记固定 false，MCP ID/原默认 session/发布检查沿用原路径。

| 统一编码对象 | 原件 B | 专用 B |
| --- | ---: | ---: |
| compact ASCII JSON-RPC id=1 正文，无 IPC/换行 | 19203 | 1077 |
| 同正文加一个终止 LF | 19204 | 1078 |
| 单工具 descriptor | 10118（observe） | 1031 |
| inputSchema | 9239（observe，继承冻结核对） | 663 |

按同一 LF 行格式，专用目录下降 **94.3866%**，1078≤1536，达到目录至少92%下降目标；descriptor 单独下降 **89.8102%**。保留两种格式，避免把一字节换行差误作收益。BYTES.json 是首次正文计量（1077），RESULTS.json 最终分列统一正文/行格式。默认四工具目录正文为19527 B，较旧19203 B增加324 B，仅来自必要旧 task schema 对齐；没有第五工具。完整服务器目录和单描述符是不同层次，provider 实际定义曝光仍未知，不能把19KB直接当模型输入或 token。

旧 task 条件现要求显式 include_image=false，拒绝 focal_id/reference_id/goal/scene_delta，错误文字覆盖 objects 与 target/candidates。冻结四反例现为正确false接受、省略/true/额外focal拒绝。MCP 既有 null 拒绝保持；公开 service.observe 的直接 None 调用仍按旧语义工作。其他模式默认图片行为及原工具行为回归通过。

当前54个方法均通过：23个新入口方法（含8个通过 alias 复用的既有语义方法）及31个相关旧回归。原53项综合运行52通过、1个预算测试断言失败；只修测试注入，目标单项通过；再补重复解析1项通过，合为当前54项，未伪称一轮54项全过。历史总执行74次＝73通过＋1失败；19项初测也分列在日志中。40个 runtime 参数例与同40个已安装 Test-Json schema例通过（9接受、31拒绝）。

失败原件 FAILED_ENCODING_TEST.py.txt 与 final_failed_01.log 保留。产品已在原 before_task_publication 正确拒绝到期；测试 patch 随后在终态错误编码中再次要求预算存在，但该原预算已经按设计退出。改为仅在成功结果编码时注入过期后通过，产品源码未因该失败改动。终态错误不续期/重试。两份 stdio 正反例还验证写前期限、initialize/list、合法调用、拒绝旧写工具、坏 JSON 后 ping 和下一合法调用；均为 StringIO 模拟，CLI 测试 mock 构造/传参，无子进程或真实监听。

覆盖一次采集/四唯一 MeshEntity、一次公开 observe/一次结果编码、默认 session、可选 AABB、0/4候选、双选择器、额外参数/非bool、重复解析、缺件/歧义/别名/自配对、开放壳/超域 unknown、接触/穿插/包含、精确并列/同显示值不同真实距离、未变/局部变更缓存、trace禁图及调用方ID。未重放旧模型答案、未跑89项全矩阵；复用 helper 的 OUT 指向本批目录，原42个两批证据文件逐一等于起点 Git。原算法/查询/结果/host/loader/transport/预算源未改。

一名只读协助者审核三份源及证据，不写代码、不导入产品或运行测试；产品仍为单一实施者。一切 handler/host/stdio/CLI 验证均是内存、fake host 或 mock。Blender、真实 MCP/host RPC、模型消费者、网络/API/key、性能试验和部署均0。此批证明了小入口、分派拒绝及合同一致性，**没有证明它解释或消除了 HE0，也没有模型采用、质量、耗时、token或费用的新结论**；诊断中 provider 最终曝光未知仍保留。

机器计量、测试分母/源码/字节身份在 RESULTS.json；schema、目录正文/行、trace、stdio序列、示例结果、到期错误、测试日志及失败原件同目录。任务单 SHA `a4a007af3a02720aff0a65e053d4e6bae374dda02b8f9754ab1e8668f72b1f5b`、诊断 SHA `86c0279af5a9c98c91c2325eb441374c2212835959b3682e2b143e87d1beaf47` 均已核。app turn 起点2026-11-09 00:40:44Z（上海08:40:44），35分钟截止01:15:44Z。RESULTS阶段累计1015473ms；完成回执另报含报告/证据提交的完整累计，不拿数秒测试时间代替工程成本。回执后结束等根深审，不自行追加消费者试验。
