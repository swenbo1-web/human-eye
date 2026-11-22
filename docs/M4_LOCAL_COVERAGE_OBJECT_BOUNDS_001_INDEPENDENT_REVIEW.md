# M4 局部覆盖索引物体粗筛独立复核

接受隔离候选 `0b6116d70af512f81a6ba053dd02a5e924530593`、证据 `c0344dae44a19d2817f344c126aa29b21da007e5`。原世界坐标的精确对象盒通过相同有理屏幕基推导范围。判定只有某轴没有正宽交集才剪掉，对象内三角的顺序、精确视锥及深度、首挡片和全量原栅格保持。全场索引和其它入口的代码路径维持原合同。主场景投影准备 73,920→1,058，留出 4,464→1,008。18 个真实视方向及 50 个合成方向的整索引与精筛有序结果一致。 [产品差分及证据](https://github.com/swenbo1-web/human-eye/commit/0b6116d70af512f81a6ba053dd02a5e924530593)

Git ZIP 746 项、11,339,065 B，长度、SHA-256 和 CRC 全部匹配，ZIP 摘要 `33d36ce796ab833b2b90f3fe7892ff6e63eb92e3c078bcea9d10edf7ccdbf5e7`。八槽 stdout EOF、真实退出 0 和句柄关闭通过。24 份冷／热／无图回包和四对前三帧的 PNG/NPZ 逐件摘要相同。三主对各回图 [3,3,0]、留出 [1,1,0]，热和无图均无新增构图。主两张局部见证、六向遮挡、0.25 m、+Z 和原点对保留。固定 CLI 回放 144/144。原计划终态 SHA 少 `ede`，纠正为 `3cdb270694e6d7096dfd3554b6a19edea5a3891a1ee76d35d204e8713c916a06`，原预检失败保留，实际冻结使用 Git ZIP 与磁盘逐字节相同的 637,460 B 原件。 [原始线包和归档](https://github.com/swenbo1-web/human-eye/tree/c0344dae44a19d2817f344c126aa29b21da007e5/verification/m4_local_coverage_object_bounds_001)

从实际阶段回执复算，局部合计包含一次共享建盒，三对 955.853→27.032、929.774→27.606、912.263→27.018 ms，配对中位减少 **97.04%**。完整 MCP 复放窗配对中位少 **26.34%**，外层少 24.53%。留出局部 94.132→56.512 ms，整窗 2.500→2.474 s。主峰值工作集略低，页文件峰值略高。主回放 8,092 B 正文和历史现场 8,112 B 属不同动态绑定，差值不计作压缩。模式为实际隔离 stdio 加封存宿主，并无当轮 Blender 或模型。 [实装分段和原图](https://github.com/swenbo1-web/human-eye/blob/c0344dae44a19d2817f344c126aa29b21da007e5/verification/m4_local_coverage_object_bounds_001/REPORT.md)

本条局部索引热点收口。现有 `pixel_center_upper_bound` 在同一正式主场景的原相机与同代源上复算：Component_582 六向像素上界依次为 3、6、3、3、6、6，Component_736 只有 LEFT 对该条件几何完整且像素上界 6，Component_417 六向遮挡。全场均无法交付完整见证，首张 SCENE 仍被强制绘制。下一项只做 [全场首帧的精确跳过](M4_REGION_TASK_GLOBAL_FIRST_FRAME_001_PLAN.md)。
