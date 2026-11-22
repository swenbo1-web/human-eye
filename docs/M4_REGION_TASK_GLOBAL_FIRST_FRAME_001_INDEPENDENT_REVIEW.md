# M4 区域任务全场首帧独立复核

接受隔离工程 `7e096daf3bb24596905f76abefa5e07a96a9f5d1`，继承 `0b6116d7`，实际运行只改一产品文件。仅当有可信上界且所有几何完整的全场候选均小于 16 时省掉全场构图。阈值 16、未知、无证明走旧流程。跳过后的全场保留几何和来源，实际帧、观察和步骤为空。局部构图和图块以当前真实 scope 重新绑定。 [产品差分](https://github.com/swenbo1-web/human-eye/commit/7e096daf3bb24596905f76abefa5e07a96a9f5d1)

证据 `42ebf86d034fff9cc4bc788f815bd701b8e26eae` 的 Git ZIP 1,251 项、17,211,174 B，逐件 SHA-256、长度和 CRC 全符，ZIP 摘要 `988f175d45f77037480b5eb638509a6dbde3ee1ab6e06bf92df23ef8533a087b`。14 个正式回放槽的 46 条实际双端线包、43 构图和真实退出核过。原冻结评分把新增 `TX_sha256` 与不含该字段的旧客户端收据直接比较，错拒保留。适配从旧原收据复验原字段，并独立用原 TX 字节核新增摘要，错绑失败路径通过；原槽未重跑。基线预飞的 5 槽、17 调用、18 构图单列。 [报告、原拒绝和原件](https://github.com/swenbo1-web/human-eye/tree/42ebf86d034fff9cc4bc788f815bd701b8e26eae/verification/m4_region_task_global_first_frame_001)

主场景七个上界最高 6，三对均 3→2 次冷构图，PNG/NPZ 的两个局部帧逐字节同旧原件，两局部原路径、三片、六向挡片和同代 0.25 m 世界 +Z 点对保留。真实留出 N22 保留全场 SCENE，N10 TOP 8,835／0 对比不足保持，3→3。密集转移 3→2，两局部原图和 0.125 m 世界 +Z 保持。固定 CLI 简报正文字图 180/180、全部原图 276/276。标准 full 保留诊断与实际图的原合同，普通观察原多图也保持。 [原图与时钟](https://github.com/swenbo1-web/human-eye/blob/42ebf86d034fff9cc4bc788f815bd701b8e26eae/verification/m4_region_task_global_first_frame_001/REPORT.md)

原时钟重算主冷 MCP 配对中位下降 28.02%，完整窗 15.43%。新证书中位 1.657 ms，省略旧首帧映射、渲染发布和反馈，图体积 7,918→5,069 B、NPZ 153,396→83,243 B。全场几何索引仍约 383 ms。旧新均为封存宿主回放，零新现场及模型，无法直接估计整题或生产资产收益。密集二维取证优化收口，下一项 [Yanyite 双曲面生产资产迁移](M4_YANYITE_DUAL_CURVED_REGION_NATIVE_001_PLAN.md)。
