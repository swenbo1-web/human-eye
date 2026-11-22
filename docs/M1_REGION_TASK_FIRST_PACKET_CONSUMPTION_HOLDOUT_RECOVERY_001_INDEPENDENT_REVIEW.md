# M1 区域任务首包未见消费恢复独立复核

2026-11-22。旧资格 0/2 保留，旧 QA 派生、新 QB 1/1、正式 A1/B1 2/2。两答均 7/7、关闭后原图均 2/2。B1 表中的 Q 面积曾写错一位，原答随后明确更正为 0.0049591064453125 m²，按冻结规则评分。A1 自然请求简报，B1 自然请求全量并实际触发候选投影，两端首包均为 7,564 B、三张同序同字节原图 7,918 B。确认了自然显式全量可使用该投影。本对未形成首包体积差，整题收益未证，原生三对未启动。 [封存报告](https://github.com/swenbo1-web/human-eye/blob/19c4333ccf0e135db24edc593edd8a10d78908eb/verification/m1_region_task_first_packet_consumption_holdout_recovery_001/REPORT.md)

从 Git ZIP 核对 1,202 个唯一成员的长度、SHA-256 和 CRC。ZIP 4,916,719 B，SHA-256 `a61668ab58b0bf8160eb15838930137547cdb55f29b52d4186c9cea42f5064e7`，新冻结 1,038 项、SHA-256 `71059af94b9c01bd7f3f8998a01401114873e9e647b8066c58ad2b0da880281a`。确认各臂七条公开业务、三次构图、一个模型和正常退出。首个业务参数分别为显式 `brief` 与 `full`，实际产品调用原样。 [顺序与原件索引](https://github.com/swenbo1-web/human-eye/tree/19c4333ccf0e135db24edc593edd8a10d78908eb/verification/m1_region_task_first_packet_consumption_holdout_recovery_001)

完整槽 A/B 112.316／113.361 s，CLI 输入加输出 140,728／139,830。两边第 2/3 次请求同为无图选区量测，正文 48,037／9,686 B，第二次复用了相同量测，点对与源归属相同。完整回包另有顶点和映射诊断，普通调用也补到了实际源顶点与排除信息。两路 `read_images` 各重交同两张原图，增加 5,069 B 原 PNG 与 912 B 公开正文，每组唯一新增的任务证据为两条最终原图路径。外部计费和模型内部时间未测。 [完整分段](https://github.com/swenbo1-web/human-eye/blob/19c4333ccf0e135db24edc593edd8a10d78908eb/verification/m1_region_task_first_packet_consumption_holdout_recovery_001/evidence/COSTS.json)

复核发现恢复评分器仍接受一种公开层错绑。将真实 QB 简报的 R 见证从局部 SCENE 改指同名全场 SCENE，保持正文 7,564 B、生产记录、公开图块及计数原样，旧检查仍给通过。原 26/26 控制继续有效，其范围在生产记录和像素绑定。独立重新逐项核对 QB/A1/B1 实际公开见证索引、生产者 scope/frame/ref/view、像素行和原图块摘要，六条真实见证均正确。故保留实际质量结果，新路径资格须拒绝此等长公开错绑。 [恢复检查源码](https://github.com/swenbo1-web/human-eye/blob/19c4333ccf0e135db24edc593edd8a10d78908eb/verification/m1_region_task_first_packet_consumption_holdout_recovery_001/checks/evidence.py)

本对收口。下一项仅做[首包同源原图路径](M1_REGION_TASK_WITNESS_IMAGE_PATH_001_PLAN.md)，先验证实际交付与错绑反例。暂无新模型调用。
