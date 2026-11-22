# M1 无图选区量测首包独立复核

2026-11-22。接受隔离候选 `34372f04143535b6990a45956aa74d210e726b29`，固定 `1535d08a` 上只改公开 MCP。仅既有证据端点的显式无图、单事实、完整实测、有实际点对和源归属、零帧选区量测走已有简报。实参、计算和量测域原样，标准全文和范围外照旧。原冻结评分的兼容判定仍为失败，同端点派生复核通过，无额外执行。 [工程报告](https://github.com/swenbo1-web/human-eye/blob/9ea9e6f9e27b69741a345564ea7c1c914d7cf3ed/verification/m1_source_region_no_image_measurement_packet_001/REPORT.md)

从 Git ZIP 核对 3,098 个唯一成员的长度、SHA-256 和 CRC。ZIP 共 10,640,691 B，SHA-256 `131f23fa7d110fcec60d1f6949edd5b5cbd77e5e82e4b149f1284e2fb494af16`。冻结清单摘要 `0770672ee40da7788258a366ff81400b7170abaa0124edbda59862c2f413d162`，143 个运行源 `338f4841654335fb6b567ae3ccba214bf370717925c6abe5592984c23b2905ac`，wheel `481c873cc061de4a3a5e99562609ba4e27574b44240b5b6429f97131d65d867c`。 [冻结与原件索引](https://github.com/swenbo1-web/human-eye/tree/9ea9e6f9e27b69741a345564ea7c1c914d7cf3ed/verification/m1_source_region_no_image_measurement_packet_001)

三份实际生产回放的全量→隔离正文为 **48,037→9,711 B** 两例、**39,717→7,067 B** 一例。标准两版的正文扣原追踪标识后相同。逐值核对完整 `region_ref`、参考、选区到整件范围、距离方向、两表面点和源三角归属。前两例均为 0.25 m、世界 +Z，第三例为 √857/4 m。三组 36/36 固定 CLI 阶段保全，另六个合法引用和恢复路径 36/36。36 个实装进程正常 EOF、退出 0 和句柄回收。两版单测各 48/53，原有五条旧 schema 断言共同失败。 [派生资格](https://github.com/swenbo1-web/human-eye/blob/9ea9e6f9e27b69741a345564ea7c1c914d7cf3ed/verification/m1_source_region_no_image_measurement_packet_001/evidence/QUALIFICATION.json)

原评分器把标准端点的区域预测全文与隔离端点本来就有的区域简报作了跨端点比较。直接比较实际原 RX，标准基线/候选各 **393,750 B** 且逐字节相同，隔离基线预飞/候选各 **6,873 B** 且逐字节相同。保持原失败、后验同端点结论与五条历史单测分栏。该问题属于验收配对，范围外接口未出现相应产品差分。 [原冻结失败](https://github.com/swenbo1-web/human-eye/blob/9ea9e6f9e27b69741a345564ea7c1c914d7cf3ed/verification/m1_source_region_no_image_measurement_packet_001/evidence/ORIGINAL_GATE_FAILURE.json)

本机三份全量请求中位内容编码 1.746→0.626 ms，线包编码 1.588→0.351 ms，外层 RTT 8.404→5.603 ms，限原件回放。无新增 Blender、模型或构图。下一批用新任务核自然完整请求的量测消费、重复补查和整题成本。产品候选未升正式默认。
