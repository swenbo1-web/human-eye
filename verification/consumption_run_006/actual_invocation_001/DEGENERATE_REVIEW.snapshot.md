# DEGENERATE-SURFACE-001 独立复核

接受产品候选0ad59befeee43c2fad752e3bad2ee69f87af3136，最终交付b24e277ceb315289ed1028913e1dc61972651f7b。131源摘要82dbf9b3a68e0c21d085ac8289ca0e504da567b4cce7300ce697d602c2e4f0c6。每个三点面的闭凸包可保留为面、线段或点；原T04已在真实公开入口返回complete、唯一M4_Near、0.004000000189989805m。该工程缺口关闭，不需要机械再开候选。

根核248个Git变化＝2产品源＋3相关旧测试＋243新增证据。247封存成员8,248,386B全部与Git/磁盘相符；独立枚举131源码并重算canonical，与offline engine和136成员执行ZIP一致；206成员RAW_ORIGINALS.zip共2,285,654B逐项匹配。原产品函数仅_integer_frame、_nearest、_witness变化，新增_segment_face_contact，task_query仅两类cache版本改变；其余原核函数不变。根未重复运行83测试。

数学子审tc1_geometry_review确认：精确零法向才降维；共线点的字典序极值是实际凸包端点，重复点不产生零长边。点点描述符独立；点线/点面、线线内部和端点特征完备。新增线穿面判据将分母归正，使用齐次重心条件u≥0、v≥0、u+v≤|n|²D；端点/共面/平行接触仍由原闭特征覆盖。正常非零瘦面仍为面，不能按容差压成线。原admission、位宽、严格AABB、exact-world排名、发布/见证逻辑保持；新运算也经过_bounded，期限/取消异常继续传播。见证发布不足不丢已知距离/精确排名，零距离方向仍not_applicable。普通与rank缓存都换版本且互相分开。

独立oracle是Fraction支持集枚举与KKT消元，另有解析距离和见证归属检查，没有调用产品特征生成真值。作者日志逐行确认19入口＋12新数学＋41surface＋11pruning/cache＝83方法首遍通过，无失败、错误、跳过或省略。旧退化拒绝断言改为正确距离；partial/unknown改用真实位宽超限，晚出现坏索引仍在零距离提前返回前拒绝。原测试变更有对应合同原因，没有删去未知路径。

独立子审额外仅执行8次纯kernel调用，固定b24e277的surface_proximity.py字节SHA 4c4bd1df00a63d6a7b3ae6259cedd45d3f60064f98174df374e2a0b6d515f34a，先核hash再compile同一字节。8/8精确距离和见证通过：反法向斜面内部穿越、三角外穿平面、端点接触、共面沿边重叠、非x轴lex极端、异面线内部最小、重复索引点点、非零瘦面。这与作者83方法分列；没有作者测试重跑、产品导入链、Blender或模型调用。

QA独立审查approval_gaps读取真实帧、capture、脚本/events/guard及owner原件。唯一1session/3RPC＝name observe、返回focal.id的legacy observe、close。两capture相同，焦点是x=0线段，目标为恒x三角形；独立平方距离下界x²在y=z=0达界，最近x=8589935/2147483648。两公开结果仅trace_id不同，4valid/0excluded/0unresolved；真实样本无tie或prune，不能扩大现场覆盖。57加载模块guard与generation一致，脚本事件hash匹配；实际kernel/cache为4/0→0/4，不以冷暖时间推导模型收益。

outer34568、stdio35128、Native18584有各自owner退出回执；controller self35356仅OS stopped，未虚构direct wait。close-event unknown原样保留，另有closed response与Native owner证据。原期限、几何、资产/helper保持。首审71项中4false与修正75/75均保留：两SCRIPT和stdout精确满足LF→CRLF存储变换，事件SHA仍对应逻辑字节；修正复用同一原件及PID观察，没有QA重跑或二次进程查询。作者离线2条既有bbox RuntimeWarning、未独立捕获离线外层stdout/stderr原始日志等缺测保留。

正常三角的特征计数仍intersection1/point-face6/point-edge18/edge-edge9，但新增维数门控和len索引是实际工作；CPU/heap未测，不能称零开销或整体更快。QA外层2.4100212s、controller2.1658552s、prepare5.5251984s等按嵌套边界保留。根从完成read_thread补完整作者turn1,646,721ms（01a1bad7-b54f-75a0-8da5-840c0aa9994c），不与内部QA相加；作者/评审token费用未知。

下一项仅是一次固定新源的消费验证：以T04的unknown是否消除、后续原生补查是否减少为主要假设，T01—T03作本次通用kernel变化的控制。原四题/八槽、同模型及原能力预算保持，不改说明或加教程。若已完整的事实仍被逐一原生复查，不再为这四题微调入口或堆输出字段；不得将单次时间波动当稳定净收益。Google付费、写域、原资产、竞争分支、正式部署边界保持。
