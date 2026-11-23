# 无图选区量测 MCP 验收独立复核

远端候选 ba79e2f1 与证据 2b3c8c28 的提交和树一致，本机 1,507 件逐件核验。正式 4/4 槽关闭、12/12 业务成功，六对的距离、世界方向、显示点对及真实源面一致。通过真实生产 CLI 显式启用 `--source-region-measurement`，在现有 `human_eye_scene_observe` 增加 `source_region_measurement`。默认关闭。独立回包交付闭盒、点对与当前两侧源三角，旧区域引用和有图仍沿原路径。 [报告](https://github.com/swenbo1-web/human-eye/blob/2b3c8c2811c018ab8eda5e7c21b2bc51a442fa10/verification/m1_m2_source_region_scoped_measurement_001/REPORT.md)

调用方正文 5,477–12,041 B→953–1,021 B，MCP 双向下降 75.20%–88.86%。同等首次源码初始化下，装配宿主冷双向 182,436→116,382 B，Yanyite 3,428,921→139,412 B。Yanyite 冷发 27,312 点／53,276 三角→233／313，宿主仍展开两对象全网。候选同区复读均零新几何，换区仍筛原目标，发新选区。旧路径同代已经驻留全场。 [原始分段](https://github.com/swenbo1-web/human-eye/blob/2b3c8c2811c018ab8eda5e7c21b2bc51a442fa10/verification/m1_m2_source_region_scoped_measurement_001/METRICS.json)

Yanyite 三条业务合计少 31.97%，完整窗 8.002→8.426 秒，增加 5.30%。装配完整窗 2.321→2.194 秒。Yanyite 两次热业务均变慢。单资产各一对，阶段时钟含实验守卫且重叠，回包字节与账单/端到端分别计量。零模型和正式构图。两次被旧目录预飞守卫拒绝、双方发生的两项旧单测断言及兼容图证独立保留。下一轮只验证同版显式入口的自然采用和完整任务成本。
