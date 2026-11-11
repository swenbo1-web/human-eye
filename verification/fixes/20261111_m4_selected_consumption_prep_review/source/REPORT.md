# M4-SELECTED-GEOMETRY-CONSUMPTION-001 来源与 smoke 独立复核

**本子审通过，没有阻止本轮唯一 GO 的来源、安装或 smoke 缺口。** 本结论只覆盖准备证据，不代表正式质量、模型使用效果或净收益通过。固定 HEAD：`13f3b279f2a57581e3cebd032d64ec9e2bfdb0ae`；PLAN SHA：`bd8af1e9619ccf9dad8c43a3ecf17eb240843f5b76f4ca9390b8a283ecc00096`。

独立脚本 [audit.py](audit.py) 只读取 Git、现有安装、原始 JSON/stdio 与源码 AST，输出 [audit.json](audit.json)。68 项必要聚合核查通过；没有启动产品、安装器、Blender、模型或性能采样，也没有重跑旧矩阵。

| 项目 | 本审实际核查 |
|---|---|
| 固定证据 | 401 索引文件 + 2 自引用 = 403 文件；Git blob、磁盘、索引 SHA/大小/集合完全一致。索引内 22,883,875 B。实施工作区审前后清洁。 |
| 当前产品 | 137 个运行源与 `00b13060` 的 Git 字节一致；准备期产品改动 0。 |
| G 安装 | `9.7.2+sg.r1`，137 源，canonical 独立重算为 `4ebc3910…f76c`；Git、解包 source、wheel、安装文件逐项一致；wheel RECORD 全部有摘要项重新核验通过。 |
| P 复用 | READY 与原 `e077fce3` / `lr.r1` 一致；原 137 文件的 Git/manifest/当前安装字节相符。没有为 P 新启动 smoke。 |
| 真实入口 | G initialize 为 installed_distribution / sg.r1 / 137 / 4eb；306 输入 pin 的实际哈希及执行前后记录一致。31 个正式派发 pin 也一致。 |
| 唯一 smoke | 3 业务请求 OFF→vertices→full，另 1 close；4 条 metadata stdio + 3 tools/call，无额外读取。业务记录没有 QA profiler，图片构造为零。 |
| 关闭 | product 实际运行身份的 exit0、reap 与 Blender closed/exit0、未 poison、终态指纹与文件保护均通过。legacy close 事件 unknown 保留，用独立终态回执确认退出。 |

几何复核从同三次 RPC 的原始 stdout 读取 capture envelope，保留首次 4 个资源、检查后两次资源 delta 为 0，并按 resource ID/revision、capture_state、场景 revision、对象及 instance ID 回绑。没有把作者的 `expected_objects_from_actual_capture` 当作真值。

本审使用原始局部顶点、矩阵和单位缩放，按精确有理数仿射计算再转回浮点，结果与交付坐标严格相等。N16 为 16 顶点/32 三角面，N28 为 24 顶点/44 三角面，合计 **40 顶点、76 三角面**；坐标、矩阵、缩放有限，三角索引合法。vertices 只发顶点，full 的同顶点与捕获三角索引一致。移除 trace 与可选 geometry 后，三次 core 严格相同；结果缓存 false/true/true，暖态已发三项内核计数为零。该证据证明本次同捕获交付正确，不是新增性能收益测量。

共同输入的 9 个复用文件与原正式消费链逐字节一致，包括原资产、13,998 B 题面、1,185,069 B 的 1200×900 初图、目录/方向/相机与来源快照。actor、consumer_transport 为原字节；CLI 当前 SHA 与冻结值相符。14 个共同预算参数和旧 PLAN 一致，统一 `gpt-6.1-sol / medium`、ChatGPT 登录路径及 `openai_http` provider；Hooks/memory 等共同设置不变。这里只确认配置和可用字节，实际权益、resolved model、provider 初图接收与模型理解仍待正式派发，未冒称已验证。

成本范围准确：G 构建安装程序 **3.8376324 s**；唯一 smoke 程序由起止原始计时重算为 **1.9181463 s**。准备协调窗口 **2,422.735965 s** 与这两个程序窗口重叠，不能相加或称为产品每次成本。正式消费者、正式九格、新图和付费 API 均为零；协调模型 token/费用与正式任务收益未测。

旧归因/选择证据目录未改写，旧性能未决仍保留。独立读取器首次将 dispatch pin 路径误按仓库根解析；错误与原脚本留在 [EXECUTION_NOTES.json](EXECUTION_NOTES.json)，修正为批目录后通过，没有任何运行重试。此子审建议在另外两项最小差异复核通过后，对上述固定 PLAN 发唯一正式 GO；正式模型结果按质量先封存、之后成本解盲的原顺序处理。
