# M1 采样图路径独立复核

2026-11-21，隔离候选 `9b43ecebba66fdc0f1efb1d06be4d5b7cb976266` 通过本批范围验收。232 件源回放原件逐项核对。冷、热实际 stdio 各只增加 `images[0].local_image_path`，正文 7,879→8,062 B。4,015 B 的同一原 PNG 和第 6 调采用的规范路径精确匹配。原样保留 26,212 个选区样本、空完整见证与 `complete_surface_visibility` 未知。固定三头、两阶段的冷热回放合计 12/12。

49 个控制中 45 个整线包同字节。跨槽、换代、大小写和复制到同槽另一 UUID 的同字节图被省略路径。私有 `PNG_bytes` 更改时，实际读取和摘要仍验证 4,015 B，路径可交付。该派生探针仅说明路径使用了实际 PNG 证据。模型、Blender 和额外费用均未发生。

每臂 48 次热回放，stdio 中位增 0.24825 ms，序列化中位增 0.23785 ms，PNG 读取、校验和编码的增量远小于序列化，未单项测量哈希与路径解析。旧第 6 调的 RTT 32.9545 ms 留作原轨迹观测。模型少调用和完整任务收益未测。第 1 调 39,717 B 的无图 full 仍作为另一项成本。

源码复核发现已有可复用的生产者证据。冷路径在交付前深复制同帧与可见性到 `prepared.observation`。同代热路径从这份证据复制，服务层只补量测、运行身份和计量。独立用隔离安装与原数据做内存原型，同帧和可见性直接比较返回同一路径，路径辅助函数本机热中位约 151→105 μs。原型未计真实传输和所有接线成本。下一批只验证 [利用现存生产者记录简化附图路径](M1_SAMPLED_IMAGE_PATH_PRODUCER_REUSE_001_PLAN.md)。

[实施报告、实际回包和分段](https://github.com/swenbo1-web/human-eye/blob/21b9cabb0ba1555a5172f5ff2f09b93646ce2d3f/verification/m1_source_region_sampled_image_path_001/REPORT.md)
