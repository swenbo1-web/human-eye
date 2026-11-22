# M1 无图选区量测消费独立复核

2026-11-22。固定 `1535d08a`／`34372f04` 同证据端点，QA/QB 2/2，正式 A1/B1 2/2。两份原答 7/7、两个槽原件与现有 Pro 请求一致，无图且未构图。两模型自然以相同业务参数发起显式无图 `full` 选区量测，首包 **47,571→9,877 B**，B 实际消费首包中的数值、点对、源面和阈值判断。 [正式报告](https://github.com/swenbo1-web/human-eye/blob/51327cf97ef0db6b03dd40283e0d75b892d4e7d8/verification/m1_source_region_no_image_measurement_consumption_001/REPORT.md)

Git ZIP 的 1,210 个唯一成员逐件通过长度、摘要和 CRC。ZIP 2,957,703 B、SHA-256 `78a23482552e10a7637a70414c5d6d1ff5fb34194cb3add17af7f604e92df758`。冻结 747 项、SHA-256 `51aa108e7212c12d761db9dd98d59c5128bfc62b4277cc6170d956c355680375`。逐条取原始请求剔除会话追踪层后核专业参数。A 第二次在同一选区和参考对象上明确改为简报，量测缓存命中，仍做一次宿主捕获；两包实测结果、点对及源归属完全相等，均支持 A 原答。B 原答的选区结果只从其第一包获得。两臂另有合法整件测量和增加 M15 整件侧源面依据的普通复核。 [原件索引](https://github.com/swenbo1-web/human-eye/blob/51327cf97ef0db6b03dd40283e0d75b892d4e7d8/verification/m1_source_region_no_image_measurement_consumption_001/RAW_INDEX.json) · [证据采用](https://github.com/swenbo1-web/human-eye/blob/51327cf97ef0db6b03dd40283e0d75b892d4e7d8/verification/m1_source_region_no_image_measurement_consumption_001/evidence/QUALITY_AND_ADOPTION.json)

| 指标 | A → B |
| --- | ---: |
| 同范围重复取数／业务调用 | 1→0／4→3 |
| 总工具文字／外层线包 | 59,018→11,525 B／64,062→12,857 B |
| CLI 输入加输出 | 65,238→39,912（−38.82%） |
| CLI 输入扣 cached 后加输出 | 16,598→22,120（+5,522） |
| 完整独占窗口 | 57.603→52.486 s（−8.88%） |

首工具往返多 20.669 ms，累计工具派发至 CLI 仅少 11.046 ms。外层完整窗口含首工具前和工具间波动，原答前时钟和成答增加均按原账本记录。单对确证一项重复取数及原始传输减少，无法证明可泛化提速、供应商计费或内部时钟。原答选区 √153/4 m 达到 2 m，整件 √13/4 m 未达到；按封存实际对的点与面复核，允许等距解。 [原始分段和用量](https://github.com/swenbo1-web/human-eye/blob/51327cf97ef0db6b03dd40283e0d75b892d4e7d8/verification/m1_source_region_no_image_measurement_consumption_001/evidence/PAIR_TRACE.json)

接受本题单对消费，保留默认配置。下一项单独做[新题原生三对](M1_SOURCE_REGION_NO_IMAGE_NATIVE_TRANSFER_001_PLAN.md)，核不同真值下同质量和完整成本门。
