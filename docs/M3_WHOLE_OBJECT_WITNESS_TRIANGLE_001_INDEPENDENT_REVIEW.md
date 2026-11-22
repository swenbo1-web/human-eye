# M3 整件最近点源三角首包独立复核

2026-11-22。接受隔离候选 `5c77f71a04e580e1e1810d4d72ff6a955cb27a0c`。仅既有证据端点的无图、双整件、单项表面距离调用附来源。线性搜索只在原获胜结果改变时记三角行，BVH 复用已有获胜对。附证前用实际对外点的二进制坐标按精确数核入两条原三角。证据按当前捕获代和 A/B 实例、原行序隔离缓存。无法核严格归属时保留原量测并省略来源。 [产品差分](https://github.com/swenbo1-web/human-eye/commit/5c77f71a04e580e1e1810d4d72ff6a955cb27a0c)

从 Git ZIP 逐件核对 811 个成员、长度、SHA-256 和 CRC。ZIP 2,497,139 B，摘要 `f7fa9e49fbe0c2ea93d49fe298c705dd620f3ffa6bdd66340cc1ada539409189`；冻结摘要 `35ed4d278d5ea697fc255f8853e89bdf3c589466b9e37a322dde9e5467a77ccf`。固定 143 源 `d39b0da9913dc31f55944a10b0299c15acc265a2d4d33d77a39e4798c65cb8c7`、wheel `66be02044ac3c3b364733840f79c4a8c8c6f1260bf145bda2dd09557d15b4984`。 [原始证据索引](https://github.com/swenbo1-web/human-eye/tree/9ac0446cdb5d105d6b56f284e9b36523f766c541/verification/m3_whole_object_witness_triangle_001)

| 原整件请求 | 原正文 → 新正文 | 实际 A/B 源面 |
| --- | ---: | --- |
| P1 M12→M17 | 1,391→1,913 B | 4／0 |
| P2 M19→M15 | 1,440→1,962 B | 0／0 |
| P3 M08→M02 | 1,439→1,961 B | 6／0 |

冷、热六包均保持原距离、点对、方向、单位和场景绑定。按当前捕获的实际求值三角独立验证，12 个公开端点均精确落在所报三角上。每侧报告一条有效来源，其他相邻三角也可能包含该点。三个冷包的候选对 144／144／24 和实际窄相 54／50／16 与基线一致。冷各一次距离求解，热复用同代结果，每次调用均采集当前场景一次。附来源每个冷包增加两次有界检查，工作计数 +2。标准端点原数据和字段顺序兼容，动态标识单列。搜索计数相同，共享内核增加了枚举操作。固定 CLI 36/36。 [实装矩阵](https://github.com/swenbo1-web/human-eye/blob/9ac0446cdb5d105d6b56f284e9b36523f766c541/verification/m3_whole_object_witness_triangle_001/evidence/MATRIX.json)

四组 12 个采用资格的实装进程正常退出，24 份冷/热业务回放。一次 Windows venv 启动因中转 PID 无法绑定持有句柄，原失败保留，采用此前确认的两组同版直启基线。历史单测两版 121/122，同一旧替身参数失败。三例同证据端点 stdio 中位冷 14.179→18.534 ms，热 7.575→12.667 ms，包含回放接线。新 Blender、模型、构图和默认切换均零，模型是否减少补取未知。历史 P2 流失败保持原样。 [报告和完整时钟](https://github.com/swenbo1-web/human-eye/blob/9ac0446cdb5d105d6b56f284e9b36523f766c541/verification/m3_whole_object_witness_triangle_001/REPORT.md)

下一项仅做[整件源三角消费者单对](M3_WHOLE_OBJECT_WITNESS_TRIANGLE_CONSUMPTION_001_PLAN.md)，证实到达首包的有效来源是否被使用及省掉来源补查。
