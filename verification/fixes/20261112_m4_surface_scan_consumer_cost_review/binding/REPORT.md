# 解封后的私有来源与质量绑定：根独立子审

2026-11-13。**1601条本轮独立检查通过，未发现需撤销匿名质量seal的来源错配或隐藏测量预热。** 本审查不重新评分答案、不重算成本门，不运行作者核验器。新增Blender、消费者、产品/API调用均0；实施树和Git未修改。

固定交付 `ab69a99e0ac4c0e925688b10859cdf26da88b83e`，原六格交付 `e5c8afafbcd7cf55307be9e640a3e2ad61e25fd3`，准备 `bedcc827ec548e3afab816c0986db0c99eb42bb8`。父任务AL611的固定assignment以本代理自身句柄核对，未覆盖父任务。

## 复用与新检查的界线

根质量阶段 `91cce49cd83c5dd00bac270b2ae128a2ede5b3ba` 已逐字核过1974项原交付。本轮先核旧manifest摘要、Git原字节，以及旧清单路径在e5c8afa→ab69a99e间没有提交改动，再复用该已有核查；没有重跑1974次Git查询后算作新增证据。当前实际读取的旧原件逐个与旧manifest长度/摘要核对，共584个实际输入记录。

新cost24项内容及manifest共25文件，逐项核长度、SHA256与ab69a99e Git blob。新manifest SHA为 `af1e66c8fc5925072375cf1f2742d9a61923c4b5d751191a8d58bea965ee2263`。根质量seal字节与cost所附副本一致，摘要 `1a205c053d7bfff76e427f83a73749bbb2a04d4ca040b92396254dd12b82942f`。

作者6276项只用于索引材料，没有并入1601条本轮断言。1601是路径、字节、事件和状态绑定检查数，不是新几何或模型样本数。

## 六格和最终答案归属

| 固定顺序 | 格 | 匿名ID后缀 | 实际工具尝试 |
| --- | --- | --- | ---: |
| 1 | N1 | 007886c1beefd7c6 | 4 |
| 2 | P1 | a5958c6899df02aa | 5 |
| 3 | P2 | 16df3f049c011e05 | 4 |
| 4 | N2 | b9ec064a37f1c4a1 | 4 |
| 5 | N3 | 3b74126ed5f72eba | 3 |
| 6 | P3 | 7958cbdd56ce7e5d | 6 |

匿名map、准备PLAN摘要、私有control副本、provenance和根seal六个ID构成一一映射，实际RUN_RESULT顺序相同，全部六格已启动且没有替补。

每格匿名answer、PUBLIC_FINAL、CLI final.txt、CONSUMER.final UTF-8字节及原events.jsonl最后公开agent message完全相同，均绑定seal内的final SHA。全部公开agent message列表也与原事件一致。六个原始ZIP共593成员，集合与原cell目录一致，所有成员字节逐项核旧manifest；没有选取较好final替代原回答。

26次owner请求/响应与薄客户端实际TX/RX相同；事件中的工具名、完整参数与结果content等于owner原件。原events.jsonl重新投影后，与匿名包所有public_tool_events逐字节来源摘要、行摘要及业务字段一致。owner的isError经CLI映射为failed状态，structuredContent映射为structured_content，不要求两层wrapper完全相同。三次工具失败仍在完整26次分母内。

六份source_consistency中的原记录SHA、INITIAL/FINAL文件摘要，均与相应私有原件一致。公开声明不再只依赖包内自洽，而已回接到实际原cell记录。

## 场景、运行身份与冷态范围

六份input.blend均等于冻结BASE摘要。12份初末完整网格回读的单位、对象名称、局部顶点、世界矩阵和面逐值等于BASE；实际host response中的JSON也等于各快照。这里的“完整”针对该表面距离任务的数据合同，不声称覆盖所有Blender数据块。

六个thread.started ID、六个owner PID和六个Blender backend PID分别互异；三P还有各自独立产品runtime PID。N的配置、实际目录与close记录没有启动产品。P实际entry与已核launcher相同，runtime proof在消费者前完成，Windows父进程链把runtime归于对应launcher。历史identity记录中的版本、138源数量及摘要与固定产品一致。

当前138源另核安装/checkout/产品Git字节与完整聚合，来源为 `c1cb2da32034e056a270384e691a2cde8dddbc0d` / `c4832b1a1ced9438f904e25a431e2327c2d7532e2f4efbb34e34ce58a7ed1943`。wheel的既有独立核验复用根质量阶段；本次没有重新打开wheel后重复计数。当前字节及历史identity相符，不等于重演历史进程内存。

三P在消费者之前的产品RPC均只有initialize、initialized、tools/list、ping。首次observe的测量缓存entry=0、hits=0，112个候选对应112次kernel/pair调用，未见把本题测量预填给消费者。

**冷态限定需要保留。** 两组都有消费者前的初始快照QA，actor.py:100明确先读取INITIAL，再初始化产品和发布identity；不能称Blender从未读过几何。首个产品测量缓存空成立。六个provider cached input均非零，因此也不是provider前缀缓存冷态或完全独立的provider内部状态。记录不足以判断provider共享缓存对差额的贡献。

薄客户端实际tools/list RX逐格与共同原生声明及适用完整普通observe声明相同；CLI配置逐项符合冻结settings，ignore-user-config、ignore-rules、ephemeral和strict-config等实际argv保留。共同题面摘要相同。请求模型为gpt-6.1-sol/medium，实际解析版本和effort仍未确认。

## 准备先后与退出的证明范围

准备commit UTC为 `2026-11-12T14:53:32Z`。三个P runtime的Windows FILETIME创建锚点分别为14:56:05.188582Z、14:58:07.376462Z、15:03:57.582314Z，均晚于准备，并在对应消费者启动前完成proof。

FORMAL_PROCESS仅记录结束UTC和起止perf_ns。以该结束UTC减同一单调时长得到整体起点14:54:04.466543Z，晚准备32.466543秒；这是**假设该时段UTC未跳变的推算**，不是六格各自直接采样的UTC启动时间。冻结PLAN/GO/actor/driver/consumer_transport已在准备Git内且未改变，加上实际单调启动顺序支持按冻结版本执行；保留上述时钟观察边界。

六格消费者和owner已回收，原生后端有实际关闭记录；三P产品launcher及被保留句柄追踪的runtime也已退出。清理结束均早于full-cell最后采样。六份薄客户端EXIT.json实际缺失，bridge_cleanup.confirmed=null、receipt_status=unknown、missing_exit_count=1均原样保留。不能由其他进程的成功关闭回填该叶项。

初末几何一致、文件哈希和公开只读代码支持本次只读任务，但不独立排除已恢复的瞬时变化。CLI原事件记录了完整工具结果，尚无provider请求体或宿主最终渲染输入证据；来源绑定不填补这个模型可见性边界。

## 自身检查记录

第一次运行将1974路径作为git diff参数，触发Windows命令长度错误206；改为单次读取全部改变路径并在Python中求交集。原件未改，错误保存在SELF_ISSUES.json。探索时一次用了错误的RUN_RESULT.cells字段，以及两次过宽显示发生截断，均保留。随后脚本通过，扩核实际source_consistency与工具声明/CLI配置后最终1601项通过。

产物：`check_binding.py`、`RESULTS.json`、`CHECKS.json`、`INPUTS.json`、`SELF_ISSUES.json`。脚本只写本binding目录，纯标准库及只读Git查询。原作者数据、产品和Git均未修改。
