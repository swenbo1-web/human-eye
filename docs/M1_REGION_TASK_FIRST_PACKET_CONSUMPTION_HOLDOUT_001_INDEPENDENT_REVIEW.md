# M1 区域任务首包未见消费独立复核

2026-11-22。冻结现场资格启动 1/2、通过 0/2，正式 A1/B1 未运行。QA 完成五条业务、三次构图，正常发布并关闭，随后冻结评分器查表失败。保留原失败、未运行格和原时间记录。 [正式报告](https://github.com/swenbo1-web/human-eye/blob/0b754de85f21e1ec12cb74a08211ac19cfd4fa0d/verification/m1_region_task_first_packet_consumption_holdout_001/REPORT.md)

复核固定证据 `0b754de85f21e1ec12cb74a08211ac19cfd4fa0d`，冻结 SHA-256 `2342ecb10d104ee000999b1d0d67e35545cf2516b50a45ac642a7ed6d54b14fc`。从 Git ZIP 逐件核对 1,000 项唯一成员、长度、CRC 和 SHA-256。ZIP 4,220,434 B，摘要 `e4e1ce943c3a0fdbd96100d8fbcb7269b849f62de4146d5743d4d5dfca75c6aa`。现场 QA 的实际生产进程有同次生命周期与退出码 0，五条客户回包原件均在。 [归档与冻结](https://github.com/swenbo1-web/human-eye/tree/0b754de85f21e1ec12cb74a08211ac19cfd4fa0d/verification/m1_region_task_first_packet_consumption_holdout_001)

冻结 `checks/evidence.py` 第 365 行按见证帧编号查顶层 `facts.observations`。该表只有全场 SCENE。局部 LEFT 和另一个同名 SCENE 各有独立 scope、frame 和原图引用。直接读封存生产记录可在对应作用域找到两行。按原像素行索引核到 ROI，Q 局部 LEFT 为 103,695／1,372，R 局部 SCENE 为 49,929／926，R 全场同名 SCENE 仅 1／1。标准冷全文、热简报与公开回读按原序返回同三张原 PNG（共 7,918 B）。作者闭槽重放通过后续图、源、挡片、点对和同代核验。该后验结果只用于诊断，原准入仍为 0/2。 [查表源码](https://github.com/swenbo1-web/human-eye/blob/0b754de85f21e1ec12cb74a08211ac19cfd4fa0d/verification/m1_region_task_first_packet_consumption_holdout_001/checks/evidence.py#L365-L371) · [闭槽诊断](https://github.com/swenbo1-web/human-eye/blob/0b754de85f21e1ec12cb74a08211ac19cfd4fa0d/verification/m1_region_task_first_packet_consumption_holdout_001/evidence/QA_READONLY_DIAGNOSIS.json)

P 的六个方向仍有正面积遮挡。原具名见证指向有效旧顶盖源三角，独立计算 RIGHT 的新竖板更近，原结果未承诺最近遮挡者。实际 0.25 m、世界 +Z 和两表面点对沿原真值。331,900 B 冷全量与 7,564 B 热简报来自同一标准入口的先后两次调用。固定 CLI 文图分别记录，整题可比耗时、真实模型采用及用量均未测。两个现场资格臂也没有形成完整对照。

下一批只恢复评分取表。按新冻结对同一已关闭 QA 派生资格，保持旧时间与记录，不重开 QA。通过后至多启动尚未运行的 QB、A1、B1。 [恢复方案](M1_REGION_TASK_FIRST_PACKET_CONSUMPTION_HOLDOUT_RECOVERY_001_PLAN.md)
