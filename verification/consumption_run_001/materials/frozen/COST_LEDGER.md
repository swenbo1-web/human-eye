# 完整成本账本预登记（当前只有静态/既有审查示例）

使用现有工具轨迹、原始TX/RX、进程owner回执、公开usage数值和文件stat；不改生产代码建新遥测平台。每行保留run/task/匿名arm/event_id/parent_id、状态、source/ref及clock_domain。失败、重试、取消、排队和回退也占真实分母。缺值用null＋原因，不填0或从Pro订阅反推美元。

同时保留 `final_answer_ready`、`cleanup_done` 和 `collection_done` 终点：用户等待到终答与完整冷链到关链分别报告，close/wait/清理失败不因先发终答而漏账。持续链只在实际生命周期末尾关链，不能重复或隐去摊销；跨时钟不能拼造这些时间。

每段另标 `product_required` / `experiment_management` / `unseparated`。产品不可省的校验保留；独立评分/制作答案和fixture特有审计单列，不能把两臂试验helper调用频率差伪装成已证明的生产净省。完整实验墙钟仍原样报告，拆不开的产品端到端净成本记未测。

| 边界/分段 | 字段与取证方式 |
|---|---|
| 调度/初始化 | accepted/start/scene_ready/final时间；新进程启动、装载、schema说明、版本核对、ID发现、策略代码准备分别留span。用户消息到终答为同一观察者时钟；冷启动到终答另保留，不用离散阶段拼造 |
| 采集/验证/求解 | 物理RPC尝试/发送完成/接收字节，host/source身份，读取对象/顶点/面、内部资格/求解/排名/审计回退；只有已有可得计数才填，无字段不推测 |
| 数据位置 | RPC TX、RX、共享文件写/读、静态检索、CLI stdout、临时文件分栏；同一payload走两边就记录两次边界。backend接收字节不是模型收到字节 |
| 内部缓存 | hit/miss、建库/加载/失效/驱逐时间，内部存储字节、可得的分配/RSS指标及各自定义；文件大小不能冒充驻留cache bytes。没有既有指标则null，不为账本加生产平台 |
| 实际模型文本 | 精确公共prompt/tool定义、实际未截断tool消息、失败stderr/后续重读/审查上下文的UTF-8字节与hash。记录投递次数；只存档未投递不计入。宿主只给截断摘要时标未核，不以artifact或helper自报等同模型看见 |
| 图片 | 是否实际送模、每次投递的分辨率/MIME/字节/hash/缩放裁剪；重送也计，不用源PNG尺寸替代实际图。图像token只取实际usage，不按像素猜价格 |
| token/模型往返 | 从宿主公开数值token_count/usage事件取增量，核last和累计差；input_cached是input子集、reasoning是output子集，不重复加总。模型任务回答数、工具轮数、实际可得provider请求数分开；不可得则null |
| 失败/回退 | 参数错误、失败RPC、补查、重试、来源重读、模型质疑、native补证和超时都算当前臂；成功之前的代价不能删 |
| 墙钟 | 端到端优先；父子span不重复加，重叠不相加，跨时钟不相减。单独记派发排队、消费者活动、fixture启动和收集/关链；p95样本不足就未测 |
| 实际费用 | 只有实际账单/usage可归属费用才填；费用币种、计价期、证据ref。字节不等于token；token不等于已知Pro美元。工程准备/审计模型耗用另账，不能声称零费用 |

P/N开始时初始信息均只有同题、工具说明和当前私有场景；完整blend不是自动进上下文。N可在Blender/Python内聚合后只返必要事实，不强制传完整几何给模型。P的说明、初始化、内部工作及native回退也计入，不能只比一次solver或RX。

已有无模型示例在 `admin/COST_EXAMPLE.json`，只转录根已接受集成审查，不是本批新作业或M1生产成本：TX84368B、RX20509B之外，另有26911B共享CAPTURE交付；不能省掉或叫完整MCP返包。完整命令3.313021秒和内部begun段2.1408113秒是嵌套指标，不能相加；差额未归因。该QA没有任务消费者，实际消费token/费用和内部cache bytes未测。示例字段标明review-reported，并未在本批重数原始RPC。

冷试验不跨臂共享场景事实/cache/答案；通用且已有的高效native脚本库可按同hash向两臂开放，不故意剥夺N。若未来测持续使用，按总方案另登记共同生命周期、脚本复用和局部变化，不能把本批冷段冒充暖段收益。
